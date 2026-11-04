"""Offline MCP query regressions; no server, network, models or credentials."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from serena_check import QUERIES, check, query_project
from test_serena_result import result


class QueryCheckTests(unittest.IsolatedAsyncioTestCase):
    async def run_query(self, names, results):
        session = SimpleNamespace(
            list_tools=AsyncMock(return_value=SimpleNamespace(
                tools=[SimpleNamespace(name=name) for name in names])),
            call_tool=AsyncMock(side_effect=results))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = await query_project(session)
        return code, session, output.getvalue()

    async def test_repl_default_is_reported_before_calling_missing_tools(self):
        code, session, output = await self.run_query(["serena_repl"], [])
        self.assertEqual(code, 1)
        session.call_tool.assert_not_awaited()
        self.assertEqual(json.loads(output)["reason"], "missing_tool")

    async def test_both_real_queries_must_return_expected_results(self):
        code, session, output = await self.run_query([name for name, _ in QUERIES], [
            result({"Function": ["main"]}),
            result({"main.py": {"Method": [{"name_path": "Bot/on_message"}]}})])
        self.assertEqual(code, 0)
        self.assertEqual(session.call_tool.await_count, 2)
        self.assertEqual([json.loads(line)["status"] for line in output.splitlines()], ["ok", "ok"])

    async def test_reference_failure_cannot_pass_after_successful_overview(self):
        code, _, output = await self.run_query([name for name, _ in QUERIES], [
            result({"Function": ["main"]}), result({})])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.splitlines()[-1])["reason"], "expected_reference_missing")

    async def test_raw_server_error_is_not_printed(self):
        code, session, output = await self.run_query([name for name, _ in QUERIES], [
            result("synthetic-private-detail", is_error=True)])
        self.assertEqual(code, 1)
        self.assertEqual(session.call_tool.await_count, 1)
        self.assertNotIn("synthetic-private-detail", output)
        self.assertEqual(json.loads(output)["reason"], "tool_error")

    async def test_transport_failure_hides_exception_and_host_secrets(self):
        params = Mock()
        transport = Mock(side_effect=RuntimeError("synthetic-private-detail"))
        modules = {
            "mcp": SimpleNamespace(ClientSession=Mock(), StdioServerParameters=params),
            "mcp.client.stdio": SimpleNamespace(stdio_client=transport),
        }
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as home, \
             patch.dict(sys.modules, modules), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-private-detail"}), \
             contextlib.redirect_stdout(output):
            self.assertEqual(await check(SimpleNamespace(cache_home=home, uv_bin=None)), 1)
        self.assertNotIn("OPENAI_API_KEY", params.call_args.kwargs["env"])
        self.assertEqual(params.call_args.kwargs["env"]["SERENA_USAGE_REPORTING"], "false")
        self.assertEqual(transport.call_args.kwargs["errlog"].name, os.devnull)
        self.assertNotIn("synthetic-private-detail", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["reason"], "mcp_connection_error")
