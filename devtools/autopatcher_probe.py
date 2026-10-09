"""Development-only checks. Never creates issues, branches, PRs or deployments."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

SOURCE = 'def add(a, b):\n    return a - b\n'
TEST = '''import unittest
from synthetic_math import add
class Regression(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add(-2, 3), 1)
'''
FIX = 'def add(a, b):\n    return a + b\n'


def command_ok(args):
    try:
        return subprocess.run(args, capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def preflight():
    # No auth files are read and no credential values or raw child output are returned.
    return {
        'platform': platform.system(),
        'python_311': sys.version_info >= (3, 11),
        'git_available': bool(shutil.which('git')),
        'gh_authenticated': command_ok(['gh', 'auth', 'status', '--hostname', 'github.com']),
        'codex_authenticated': command_ok(['codex', 'login', 'status']),
        'codex_available': bool(shutil.which('codex')),
        'e2b_sdk_installed': importlib.util.find_spec('e2b') is not None,
        'e2b_key_present': bool(os.environ.get('E2B_API_KEY')),
        'e2b_connection': 'not_checked',
        'windows_executor': 'available' if os.name == 'nt' else 'not_checked',
        'powershell_available': bool(shutil.which('pwsh') or shutil.which('powershell')),
        'model_call': 'not_checked',
        'production_operation': 'not_checked',
    }


def local_test(files):
    # Only used for the deterministic built-in fixture, never arbitrary model output.
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for item in files:
            path = root / item['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(item['content'], encoding='utf-8')
        return command_ok([sys.executable, '-I', '-c',
            'import os,sys,unittest; os.chdir(sys.argv[1]); sys.path.insert(0,sys.argv[1]); '
            'r=unittest.TextTestRunner().run(unittest.defaultTestLoader.discover("tests")); '
            'sys.exit(not r.wasSuccessful())', str(root)])


def e2b_test(files):
    from e2b import Sandbox
    sandbox = None
    try:
        sandbox = Sandbox.create(timeout=60, secure=True)
        for item in files:
            sandbox.files.write('/tmp/probe/' + item['path'], item['content'])
        result = sandbox.commands.run('cd /tmp/probe && python -m unittest discover -s tests', timeout=20)
        return 'passed' if result.exit_code == 0 else 'failed'
    except Exception:
        return 'execution_error'
    finally:
        if sandbox is not None:
            sandbox.kill()


def synthetic(live_codex=False, live_e2b=False):
    if live_codex and not live_e2b:
        raise ValueError('Model-generated code requires E2B isolation')
    from autopatcher import CodexGenerator, validate_patch
    baseline = [{'path': 'synthetic_math.py', 'content': SOURCE},
                {'path': 'tests/test_synthetic_math.py', 'content': TEST}]
    baseline_result = e2b_test(baseline) if live_e2b else ('passed' if local_test(baseline) else 'failed')
    baseline_failed = baseline_result == 'failed'
    if live_codex:
        value = CodexGenerator()({'number': 0, 'title': 'Fix add in synthetic_math.py',
            'body': 'add must return the sum. Preserve the supplied regression tests.'},
            {'instructions': 'Synthetic fixture only; change only synthetic_math.py.',
             'sources': {f['path']: f['content'] for f in baseline}}, '')
    else:
        value = {'files': [{'path': 'synthetic_math.py', 'content': FIX}]}
    files = validate_patch(value)
    # The oracle is immutable; changing tests or adding unrelated files is rejected.
    if len(files) != 1 or files[0]['path'] != 'synthetic_math.py':
        raise ValueError('Fixture scope exceeded')
    candidate = files + [baseline[1]]
    result = e2b_test(candidate) if live_e2b else ('passed' if local_test(candidate) else 'failed')
    return {'baseline_failed': baseline_failed,
            'patch_source': 'real_codex' if live_codex else 'deterministic_fixture',
            'test_backend': 'real_e2b' if live_e2b else 'local_fixture',
            'candidate_result': result,
            'synthetic_passed': baseline_failed and result == 'passed',
            'github_publication': 'not_attempted', 'production_operation': 'not_checked'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--synthetic', action='store_true')
    parser.add_argument('--live-codex', action='store_true')
    parser.add_argument('--live-e2b', action='store_true')
    parser.add_argument('--approve-external-cost', action='store_true')
    args = parser.parse_args()
    if (args.live_codex or args.live_e2b) and not (args.synthetic and args.approve_external_cost):
        parser.error('Live checks require --synthetic and explicit external-cost approval')
    if args.preflight:
        print(json.dumps(preflight()))
    if args.synthetic:
        result = synthetic(args.live_codex, args.live_e2b)
        print(json.dumps(result))
        return 0 if result['synthetic_passed'] else 1
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        print(json.dumps({'status': 'blocked_or_failed', 'production_operation': 'not_checked'}))
        sys.exit(1)
