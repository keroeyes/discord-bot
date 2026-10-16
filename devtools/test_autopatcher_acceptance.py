"""Offline security/acceptance contracts; no generated code executed here."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from autopatcher import build_graph, verify_final_candidate, worker_lock, main, isolated_test, CodexGenerator
from langgraph.checkpoint.sqlite import SqliteSaver
from test_autopatcher import BASE, PATCH, INITIAL, CONFIG, FakeGitHub


class AcceptanceTests(unittest.TestCase):
    def test_lock_excludes_another_process_and_releases_after_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            script = ('from autopatcher import worker_lock; import sys; '
                      'lock=worker_lock(sys.argv[1]); lock.__enter__()')
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).parent.resolve()))
            def contender():
                return subprocess.run([sys.executable, '-c', script, directory],
                                      capture_output=True, env=env, timeout=10)
            with worker_lock(directory):
                self.assertNotEqual(contender().returncode, 0)
            self.assertEqual(contender().returncode, 0)
            # Previous child exited without __exit__: kernel releases ownership.
            self.assertEqual(contender().returncode, 0)

    def test_exception_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError):
                with worker_lock(directory):
                    raise RuntimeError('synthetic')
            with worker_lock(directory):
                pass

    def test_busy_main_never_opens_database_or_calls_services(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('sys.argv', ['worker', '--state-dir', directory, '--job', 'other']), \
                 patch('autopatcher.worker_lock', side_effect=BlockingIOError), \
                 patch('autopatcher.SqliteSaver.from_conn_string') as db, \
                 patch('autopatcher.GitHub') as github, \
                 patch('autopatcher.CodexGenerator') as model:
                with self.assertRaises(BlockingIOError):
                    main()
            db.assert_not_called()
            github.assert_not_called()
            model.assert_not_called()

    def test_main_lock_scope_is_independent_of_job_and_state_directory(self):
        scopes = []
        for job in ('one', 'two'):
            with tempfile.TemporaryDirectory() as directory, \
                 patch('sys.argv', ['worker', '--state-dir', directory, '--job', job]), \
                 patch('autopatcher.worker_lock', side_effect=BlockingIOError) as lock:
                with self.assertRaises(BlockingIOError):
                    main()
                scopes.append(lock.call_args.args[0])
        self.assertEqual(scopes[0], scopes[1])

    def run_candidate(self, candidate, gh=None, tester=None):
        gh = gh or FakeGitHub()
        with tempfile.TemporaryDirectory() as directory:
            with SqliteSaver.from_conn_string(':memory:') as saver:
                graph = build_graph(saver, directory, gh, lambda *args: candidate,
                                    tester or (lambda *args: 'passed'))
                result = graph.invoke(INITIAL, CONFIG)
        return result, gh

    def test_passing_generated_tests_without_new_regression_cannot_publish(self):
        result, gh = self.run_candidate({'files': [PATCH['files'][0]]})
        self.assertEqual(result['status'], 'blocked_verification')
        self.assertEqual(result['attempts'], 1)
        self.assertFalse(gh.published)

    def test_replacing_existing_test_is_blocked_even_when_tests_pass(self):
        gh = FakeGitHub()
        original = gh.api
        gh.api = lambda endpoint: ({'tree': [{'type': 'blob', 'path':
            'tests/test_new_behavior.py'}]} if endpoint.startswith('git/trees/') else original(endpoint))
        result, gh = self.run_candidate(PATCH, gh)
        self.assertEqual(result['status'], 'blocked_verification')
        self.assertFalse(gh.published)

    def test_final_tree_failure_is_closed_without_exception_disclosure(self):
        for tree in ({'truncated': True, 'tree': []}, {'tree': None}):
            gh = FakeGitHub()
            original = gh.api
            gh.api = lambda endpoint: tree if endpoint.startswith('git/trees/') else original(endpoint)
            result, gh = self.run_candidate(PATCH, gh)
            self.assertEqual(result['status'], 'blocked_verification')
            self.assertFalse(gh.published)
        gh = FakeGitHub()
        original = gh.api
        def api(endpoint):
            if endpoint.startswith('git/trees/'):
                raise RuntimeError('synthetic-secret')
            return original(endpoint)
        gh.api = api
        result, gh = self.run_candidate(PATCH, gh)
        self.assertEqual(result['status'], 'blocked_verification')
        self.assertNotIn('synthetic-secret', str(result))
        self.assertFalse(gh.published)

    def test_bare_function_is_not_a_discoverable_unittest(self):
        candidate = copy.deepcopy(PATCH)
        candidate['files'][1]['content'] = 'def test_fake():\n    assert True\n'
        result, gh = self.run_candidate(candidate)
        self.assertEqual(result['status'], 'blocked_verification')
        self.assertFalse(gh.published)

    def test_disk_tampering_after_isolated_tests_blocks_publication(self):
        gh = FakeGitHub()
        with tempfile.TemporaryDirectory() as directory:
            def tester(*args):
                import json
                altered = copy.deepcopy(PATCH)
                altered['files'][0]['content'] = 'VALUE = 999\n'
                next(Path(directory).glob('issue-*.json')).write_text(json.dumps(altered))
                return 'passed'
            with SqliteSaver.from_conn_string(':memory:') as saver:
                result = build_graph(saver, directory, gh, lambda *args: PATCH,
                                     tester).invoke(INITIAL, CONFIG)
        self.assertEqual(result['status'], 'blocked_verification')
        self.assertFalse(gh.published)

    def test_verified_checkpoint_requires_matching_hash_before_publish(self):
        for digest in ('', 'different'):
            gh = FakeGitHub()
            with tempfile.TemporaryDirectory() as directory:
                with SqliteSaver.from_conn_string(':memory:') as saver:
                    graph = build_graph(saver, directory, gh, lambda *args: PATCH,
                                        lambda *args: 'passed')
                    graph.update_state(CONFIG, dict(INITIAL, issue=7, base=BASE,
                        candidate_hash='candidate', verified_hash=digest, status='publishing'), as_node='verify')
                    result = graph.invoke(None, CONFIG)
            self.assertEqual(result['status'], 'blocked_verification')
            self.assertFalse(gh.published)

    def test_interrupted_generation_is_not_reissued_on_checkpoint_resume(self):
        class Interrupted(BaseException):
            pass
        gh = FakeGitHub()
        calls = []
        def generator(*args):
            calls.append(1)
            raise Interrupted()
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / 'jobs.sqlite')
            with SqliteSaver.from_conn_string(database) as saver:
                graph = build_graph(saver, directory, gh, generator, lambda *args: 'passed')
                with self.assertRaises(Interrupted):
                    graph.invoke(INITIAL, CONFIG)
            with SqliteSaver.from_conn_string(database) as saver:
                graph = build_graph(saver, directory, gh, generator, lambda *args: 'passed')
                result = graph.invoke(None, CONFIG)
            self.assertEqual(result['status'], 'blocked_generation_recovery')
        self.assertEqual(len(calls), 1)
        self.assertFalse(gh.published)

    def test_interrupted_isolated_test_is_not_reissued_on_resume(self):
        class Interrupted(BaseException):
            pass
        gh = FakeGitHub()
        calls = []
        def tester(*args):
            calls.append(1)
            raise Interrupted()
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / 'jobs.sqlite')
            with SqliteSaver.from_conn_string(database) as saver:
                graph = build_graph(saver, directory, gh, lambda *args: PATCH, tester)
                with self.assertRaises(Interrupted):
                    graph.invoke(INITIAL, CONFIG)
            with SqliteSaver.from_conn_string(database) as saver:
                graph = build_graph(saver, directory, gh, lambda *args: self.fail('regenerated'), tester)
                result = graph.invoke(None, CONFIG)
            self.assertEqual(result['status'], 'blocked_test_recovery')
        self.assertEqual(len(calls), 1)
        self.assertFalse(gh.published)

    def test_retry_success_still_has_only_two_generation_calls(self):
        gh = FakeGitHub()
        results = iter(['failed', 'passed'])
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            with SqliteSaver.from_conn_string(':memory:') as saver:
                def generator(*args):
                    calls.append(1)
                    return PATCH
                result = build_graph(saver, directory, gh, generator,
                    lambda *args: next(results)).invoke(INITIAL, dict(CONFIG, recursion_limit=16))
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['status'], 'draft_pr_created')
        self.assertEqual(result['verified_hash'], result['candidate_hash'])

    def test_e2b_stays_secure_without_host_environment_and_cleans_up(self):
        sandbox = MagicMock()
        sandbox.commands.run.return_value.exit_code = 0
        with patch('e2b.Sandbox.create', return_value=sandbox) as create:
            self.assertEqual(isolated_test(BASE, PATCH['files']), 'passed')
        create.assert_called_once_with(timeout=300, secure=True)
        for call in sandbox.commands.run.call_args_list:
            self.assertNotIn('envs', call.kwargs)
        sandbox.kill.assert_called_once()
        sandbox.reset_mock()
        sandbox.commands.run.side_effect = RuntimeError('synthetic-secret')
        with patch('e2b.Sandbox.create', return_value=sandbox):
            self.assertEqual(isolated_test(BASE, PATCH['files']), 'execution_error')
        sandbox.kill.assert_called_once()

    def test_generator_keeps_credential_filter_and_read_only_sandbox(self):
        import json
        observed = []
        def run(command, **kwargs):
            if command[0] == 'codex':
                observed.append((command, kwargs))
                Path(command[command.index('-o') + 1]).write_text(json.dumps(PATCH))
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'synthetic-secret',
                        'E2B_API_KEY': 'synthetic-secret', 'OPENAI_API_KEY': 'synthetic-secret'}), \
             patch('autopatcher.subprocess.run', side_effect=run):
            CodexGenerator()({'number': 7}, {}, '')
        command, kwargs = observed[0]
        self.assertEqual(command[command.index('--sandbox') + 1], 'read-only')
        for key in ('GITHUB_TOKEN', 'E2B_API_KEY', 'OPENAI_API_KEY'):
            self.assertNotIn(key, kwargs['env'])
        self.assertNotIn('synthetic-secret', kwargs['input'])

    def test_verification_is_separate_and_never_executes_candidate(self):
        candidate = copy.deepcopy(PATCH)
        candidate['files'][1]['content'] = ('raise RuntimeError("must not execute")\n'
            'import unittest\nclass Regression(unittest.TestCase):\n'
            '    def test_example(self):\n        self.assertTrue(True)\n')
        # Static acceptance only. The real E2B test would fail this module.
        self.assertTrue(verify_final_candidate(FakeGitHub(), BASE, candidate['files']))
