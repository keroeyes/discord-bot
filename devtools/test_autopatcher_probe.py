import unittest
from unittest.mock import patch, MagicMock
from autopatcher_probe import synthetic, preflight, main, e2b_test

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

    def test_e2b_nonzero_exit_is_test_failure(self):
        from e2b import CommandExitException
        sandbox = MagicMock()
        sandbox.commands.run.side_effect = CommandExitException(
            stdout='', stderr='synthetic failure', exit_code=1, error=None)
        with patch('e2b.Sandbox.create', return_value=sandbox):
            self.assertEqual(e2b_test([]), 'failed')
        sandbox.kill.assert_called_once()

    def test_e2b_connection_error_is_not_test_failure(self):
        with patch('e2b.Sandbox.create', side_effect=RuntimeError('offline')):
            self.assertEqual(e2b_test([]), 'execution_error')

    def test_model_requires_remote_isolation_before_any_execution(self):
        with patch('autopatcher_probe.local_test') as local, \
             patch('autopatcher_probe.e2b_test') as remote, \
             patch('autopatcher.CodexGenerator.__call__') as model:
            with self.assertRaises(ValueError):
                synthetic(live_codex=True)
        local.assert_not_called()
        remote.assert_not_called()
        model.assert_not_called()

    def test_e2b_requires_cost_approval(self):
        with patch('sys.argv', ['probe', '--synthetic', '--live-e2b']), \
             patch('autopatcher_probe.synthetic') as run, self.assertRaises(SystemExit):
            main()
        run.assert_not_called()
