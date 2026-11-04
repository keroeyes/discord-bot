"""Verify a local Serena MCP connection without changing client configuration."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from serena_result import query_failure

QUERIES = (
    ("get_symbols_overview", {"relative_path": "main.py", "depth": 0}),
    ("find_referencing_symbols", {"name_path": "request_trace", "relative_path": "observability.py"}),
)


async def query_project(session):
    available = {tool.name for tool in (await session.list_tools()).tools}
    for name, _ in QUERIES:
        if name not in available:
            print(json.dumps({"tool": name, "status": "failed", "reason": "missing_tool"}))
            return 1
    for name, arguments in QUERIES:
        result = await session.call_tool(name, arguments)
        reason = query_failure(name, result)
        if reason:
            print(json.dumps({"tool": name, "status": "failed", "reason": reason}))
            return 1
        print(json.dumps({"tool": name, "status": "ok"}))
    return 0


async def check(args):
    # Keep the offline worker tests independent of the optional MCP installation.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    home = str(Path(args.cache_home).resolve())
    os.makedirs(home, exist_ok=True)
    if args.uv_bin:
        os.environ["PATH"] = str(Path(args.uv_bin).resolve()) + os.pathsep + os.environ.get("PATH", "")
    # MCP stdio inherits only a small environment allowlist. Use Serena's
    # platform-independent home setting and forward only uv cache controls;
    # never copy the host environment (which may contain API credentials).
    server_env = {"SERENA_HOME": home, "UV_CACHE_DIR": str(Path(home) / "uv-cache"),
                  "SERENA_USAGE_REPORTING": "false"}
    for name in ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_PYTHON_DOWNLOADS"):
        if name in os.environ:
            server_env[name] = os.environ[name]
    boot = "from serena.cli import top_level; top_level()"
    params = StdioServerParameters(command=sys.executable, env=server_env, args=[
        "-c", boot, "start-mcp-server", "--project", str(Path(__file__).resolve().parents[1]),
        "--context", "codex", "--enable-web-dashboard", "false",
        "--open-web-dashboard", "false", "--enable-gui-log-window", "false",
        "--log-level", "ERROR"])
    # Server stderr and raw exceptions can contain source or private paths.
    # Report only fixed failure codes; never upload the Serena home/logs.
    with open(os.devnull, "w") as errlog:
        try:
            async with asyncio.timeout(180):
                async with stdio_client(params, errlog=errlog) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        await session.initialize()
                        return await query_project(session)
        except TimeoutError:
            reason = "timeout"
        except Exception:
            reason = "mcp_connection_error"
    print(json.dumps({"tool": "mcp", "status": "failed", "reason": reason}))
    return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-home", required=True)
    parser.add_argument("--uv-bin", help="Directory containing uv/uvx if absent from PATH")
    sys.exit(asyncio.run(check(parser.parse_args())))
