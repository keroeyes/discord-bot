import unittest
from unittest.mock import patch
from autopatcher_probe import synthetic, preflight, main

class ProbeTests(unittest.TestCase):
    def test_real_local_regression(self):
        result = synthetic()
        self.assertTrue(result['baseline_failed'])
        self.assertTrue(result['synthetic_passed'])
        self.assertEqual(result['production_operation'], 'not_checked')

    def test_live_requires_explicit_gate(self):
        with patch('sys.argv', ['probe', '--synthetic', '--live-codex']), self.assertRaises(SystemExit):
            main()

    def test_model_cannot_replace_oracle(self):
        with patch('autopatcher_probe.e2b_test', return_value='failed'), patch('autopatcher.CodexGenerator.__call__', return_value={'files': [
            {'path': 'tests/test_synthetic_math.py', 'content': 'VALUE=1'}]}), self.assertRaises(ValueError):
            synthetic(live_codex=True, live_e2b=True)

    def test_preflight_does_not_claim_connections(self):
        with patch('autopatcher_probe.command_ok', return_value=False):
            result = preflight()
        self.assertEqual(result['e2b_connection'], 'not_checked')
        self.assertEqual(result['model_call'], 'not_checked')
