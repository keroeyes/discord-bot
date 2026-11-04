"""Offline regression tests; no MCP server, models or credentials."""
import unittest
import json
from types import SimpleNamespace
from serena_result import tool_failed, query_failure


def result(payload, **flags):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(payload))],
                           **(flags or {"is_error": False}))


class ResultCompatibilityTests(unittest.TestCase):
    def test_both_sdk_field_names(self):
        for field in ("isError", "is_error"):
            for failed in (False, True):
                with self.subTest(field=field, failed=failed):
                    self.assertIs(tool_failed(SimpleNamespace(**{field: failed})), failed)

    def test_unknown_and_malformed_fail_closed(self):
        for result in (object(), SimpleNamespace(is_error=None),
                       SimpleNamespace(isError=0), SimpleNamespace(is_error="false")):
            with self.subTest(result=result):
                self.assertTrue(tool_failed(result))

    def test_conflicting_aliases_do_not_hide_failure(self):
        self.assertTrue(tool_failed(SimpleNamespace(is_error=False, isError=True)))
        self.assertTrue(tool_failed(SimpleNamespace(is_error=True, isError=False)))
        self.assertFalse(tool_failed(SimpleNamespace(is_error=False, isError=False)))


class QueryResultTests(unittest.TestCase):
    def test_pinned_grouped_symbol_and_reference_results(self):
        self.assertIsNone(query_failure("get_symbols_overview", result({"Function": ["main"]})))
        self.assertIsNone(query_failure("find_referencing_symbols", result({
            "main.py": {"Method": [{"name_path": "Bot/on_message"}]}})))

    def test_success_flag_does_not_hide_empty_or_unrelated_results(self):
        for payload in ({}, {"Function": []}, {"Function": ["other"]}):
            self.assertEqual(query_failure("get_symbols_overview", result(payload)), "expected_symbol_missing")
        for payload in ({}, {"main.py": {}}, {"other.py": {"Method": [{"name_path": "Bot/on_message"}]}}):
            self.assertEqual(query_failure("find_referencing_symbols", result(payload)), "expected_reference_missing")

    def test_error_or_malformed_content_is_rejected(self):
        self.assertEqual(query_failure("get_symbols_overview", result({"Function": ["main"]}, isError=True)), "tool_error")
        for content in (None, [], [object()],
                        [SimpleNamespace(type="text", text="synthetic-private-detail")],
                        [SimpleNamespace(type="text", text="x" * 262145)]):
            self.assertEqual(query_failure("get_symbols_overview", SimpleNamespace(
                is_error=False, content=content)), "invalid_result")
        for payload in (None, [], "main", 1):
            self.assertEqual(query_failure("get_symbols_overview", result(payload)), "invalid_result")


if __name__ == "__main__":
    unittest.main()
