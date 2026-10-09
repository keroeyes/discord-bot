import copy
import tempfile
import unittest
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from autopatcher import build_graph, select_issue, validate_patch

ISSUE = {"number": 7, "state": "open", "user": {"login": "keroeyes"},
         "title": "Synthetic regression", "body": "synthetic issue",
         "labels": [{"name": "agent-ready"}]}
BASE = "a" * 40
PATCH = {"files": [{"path": "main.py", "content": "VALUE = 2\n"}]}
INITIAL = {"issue": 0, "base": "", "attempts": 0, "candidate_hash": "",
           "result": "", "status": "starting", "pr": 0}
CONFIG = {"configurable": {"thread_id": "synthetic"}}

class FakeGitHub:
    def __init__(self, issue=ISSUE):
        self.issue = copy.deepcopy(issue)
        self.published = []
    def select(self):
        return select_issue([self.issue] if self.issue else [], set())
    def base(self):
        return BASE
    def api(self, endpoint):
        return self.issue
    def context(self, issue, base):
        return {"instructions": "synthetic rules", "sources": {"main.py": "VALUE = 1\n"}}
    def publish(self, number, base, files):
        self.published.append((number, base, files))
        return 42

class AutopatcherTests(unittest.TestCase):
    def run_graph(self, github, generator, tester):
        with tempfile.TemporaryDirectory() as directory:
            with SqliteSaver.from_conn_string(":memory:") as saver:
                graph = build_graph(saver, directory, github, generator, tester)
                result = graph.invoke(INITIAL, CONFIG)
                return result

    def test_select_only_opted_in_owner_issues_and_skip_duplicates(self):
        other = copy.deepcopy(ISSUE)
        other["user"]["login"] = "external"
        pr = copy.deepcopy(ISSUE)
        pr["pull_request"] = {}
        unlabelled = copy.deepcopy(ISSUE)
        unlabelled["labels"] = []
        self.assertIsNone(select_issue([other, pr, unlabelled], set()))
        self.assertIsNone(select_issue([ISSUE], {7}))
        self.assertEqual(select_issue([ISSUE], set())["number"], 7)

    def test_no_issue_means_no_model_or_sandbox_or_publish(self):
        gh = FakeGitHub(None)
        def forbidden(*args):
            self.fail("unexpected call")
        result = self.run_graph(gh, forbidden, forbidden)
        self.assertEqual(result["status"], "no_eligible_issue")
        self.assertEqual(gh.published, [])

    def test_generated_patch_passes_test_then_draft_publisher(self):
        gh = FakeGitHub()
        seen = []
        def tester(base, files):
            seen.append((base, files))
            return "passed"
        result = self.run_graph(gh, lambda *args: PATCH, tester)
        self.assertEqual(result["status"], "draft_pr_created")
        self.assertEqual(result["pr"], 42)
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(len(gh.published), 1)
        self.assertEqual(seen[0][1][0]["content"], "VALUE = 2\n")
        self.assertNotIn("synthetic issue", str(result))
        self.assertNotIn("VALUE = 2", str(result))

    def test_two_failures_stop_without_publishing(self):
        gh = FakeGitHub()
        calls = []
        def generator(*args):
            calls.append(args[-1])
            return PATCH
        result = self.run_graph(gh, generator, lambda *args: "failed")
        self.assertEqual(result["status"], "exhausted")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(calls, ["", "failed"])
        self.assertEqual(gh.published, [])

    def test_model_failure_is_blocked_without_raw_exception(self):
        def fail(*args):
            raise RuntimeError("synthetic-secret")
        gh = FakeGitHub()
        result = self.run_graph(gh, fail, lambda *args: self.fail("sandbox called"))
        self.assertEqual(result["status"], "blocked_generation")
        self.assertEqual(result["attempts"], 1)
        self.assertNotIn("synthetic-secret", str(result))
        self.assertEqual(gh.published, [])

    def test_label_withdrawn_before_publish_stops(self):
        gh = FakeGitHub()
        def tester(*args):
            gh.issue["labels"] = []
            return "passed"
        result = self.run_graph(gh, lambda *args: PATCH, tester)
        self.assertEqual(result["status"], "withdrawn")
        self.assertEqual(gh.published, [])

    def test_reject_credential_workflow_and_traversal_paths(self):
        for path in [".env", ".github/workflows/tests.yml", "../main.py", "/main.py",
                     "requirements.txt", "tests/../../main.py", "C:\\auth.json"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_patch({"files": [{"path": path, "content": "VALUE = 1"}]})
        with self.assertRaises(ValueError):
            validate_patch({"files": [PATCH["files"][0], PATCH["files"][0]]})

    def test_checkpoint_restart_does_not_repeat_completed_work(self):
        with tempfile.TemporaryDirectory() as directory:
            db = directory + "/jobs.sqlite"
            gh = FakeGitHub()
            with SqliteSaver.from_conn_string(db) as saver:
                graph = build_graph(saver, directory, gh, lambda *args: PATCH, lambda *args: "passed")
                graph.invoke(INITIAL, CONFIG)
            with SqliteSaver.from_conn_string(db) as saver:
                graph = build_graph(saver, directory, gh, lambda *args: self.fail("regenerated"))
                state = graph.get_state(CONFIG)
                self.assertEqual(state.values["pr"], 42)
                self.assertEqual(state.next, ())
            self.assertEqual(len(gh.published), 1)

if __name__ == "__main__":
    unittest.main()
