"""Offline regression tests; no MCP server, models or credentials."""
import unittest
from types import SimpleNamespace
from serena_result import tool_failed


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


if __name__ == "__main__":
    unittest.main()
