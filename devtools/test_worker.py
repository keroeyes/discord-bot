import os
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from worker import build_graph, test_in_e2b

COMMIT = "a" * 40

class WorkerTests(unittest.TestCase):
    def test_resume_after_restart_and_bounded_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            db = directory + "/state.sqlite"
            config = {"configurable": {"thread_id": "test"}}
            calls = []
            def fail(commit):
                calls.append(commit)
                return "failed"
            with SqliteSaver.from_conn_string(db) as saver:
                graph = build_graph(saver, fail)
                graph.invoke({"commit": "", "attempts": 0, "status": "awaiting_commit", "result": ""}, config)
                self.assertEqual(graph.get_state(config).next, ("await_commit",))
            with SqliteSaver.from_conn_string(db) as saver:
                graph = build_graph(saver, fail)
                result = graph.invoke(Command(resume=COMMIT), config)
                self.assertEqual(result["status"], "retry")
                self.assertEqual(graph.get_state(config).next, ("await_commit",))
                result = graph.invoke(Command(resume=COMMIT), config)
                self.assertEqual(result["status"], "exhausted")
                self.assertEqual(graph.get_state(config).next, ())
                self.assertEqual(len(calls), 2)

    def test_success_stops_before_pr_or_merge(self):
        with SqliteSaver.from_conn_string(":memory:") as saver:
            graph = build_graph(saver, lambda commit: "passed")
            config = {"configurable": {"thread_id": "success"}}
            graph.invoke({"commit": "", "attempts": 0, "status": "awaiting_commit", "result": ""}, config)
            result = graph.invoke(Command(resume=COMMIT), config)
            self.assertEqual(result["status"], "ready_for_pr")
            self.assertEqual(result["attempts"], 1)
            self.assertEqual(graph.get_state(config).next, ())

    def test_missing_key_does_not_create_sandbox(self):
        with patch.dict(os.environ, {"E2B_API_KEY": ""}):
            self.assertEqual(test_in_e2b(COMMIT, lambda **kw: self.fail("sandbox created")), "missing_credentials")

    def test_sandbox_cleanup_and_no_host_env_upload(self):
        killed, created, commands = [], [], []
        sandbox = SimpleNamespace(
            commands=SimpleNamespace(run=lambda command, **kw: commands.append((command, kw)) or SimpleNamespace(exit_code=0)),
            kill=lambda: killed.append(True))
        def factory(**kw):
            created.append(kw)
            return sandbox
        with patch.dict(os.environ, {"E2B_API_KEY": "synthetic-test-key"}):
            self.assertEqual(test_in_e2b(COMMIT, factory), "passed")
        self.assertEqual(killed, [True])
        self.assertNotIn("envs", created[0])
        self.assertEqual(created[0]["timeout"], 300)
        self.assertEqual(commands[0][1]["timeout"], 240)

    def test_cleanup_on_error_and_no_raw_exception(self):
        def fail(*args, **kwargs):
            raise RuntimeError("synthetic-private-message")
        killed=[]
        sandbox=SimpleNamespace(commands=SimpleNamespace(run=fail), kill=lambda: killed.append(True))
        with patch.dict(os.environ, {"E2B_API_KEY": "synthetic-test-key"}):
            self.assertEqual(test_in_e2b(COMMIT, lambda **kw: sandbox), "execution_error")
        self.assertEqual(killed, [True])

    def test_nonzero_command_exit_is_failed_and_cleaned_up(self):
        from e2b import CommandExitException
        def fail(*args, **kwargs):
            raise CommandExitException("synthetic-error", "", 1, None)
        killed = []
        sandbox = SimpleNamespace(commands=SimpleNamespace(run=fail), kill=lambda: killed.append(True))
        with patch.dict(os.environ, {"E2B_API_KEY": "synthetic-test-key"}):
            self.assertEqual(test_in_e2b(COMMIT, lambda **kw: sandbox), "failed")
        self.assertEqual(killed, [True])

    def test_rejects_shell_injection_before_sandbox_creation(self):
        with self.assertRaises(ValueError):
            test_in_e2b("abc; echo unsafe", lambda **kw: self.fail("sandbox created"))

if __name__ == "__main__":
    unittest.main()
