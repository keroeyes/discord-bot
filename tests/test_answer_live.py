"""Live evaluator orchestration is tested offline with synthetic provider replies."""
import contextlib
import io
import logging
import os
import unittest
from unittest.mock import AsyncMock, patch
from answer_evals.official import parse_snapshot
from scripts import answer_content_live as live

PAGE = '<a href="/downloads/release/python-3148/">Python 3.14.8</a>'


def response(text, sources=None, count=0):
    return dict(text=text, sources=sources or [], search_count=count)


class LiveGates(unittest.TestCase):
    def test_explicit_run_and_endpoint_are_required_before_any_request(self):
        with patch.object(live, 'run') as run, patch.dict(os.environ, {}, clear=True):
            for argv in ([], ['--run']):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    live.main(argv)
                self.assertEqual(error.exception.code, 2)
            run.assert_not_called()


class LiveOrchestration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        disabled = logging.root.manager.disable
        self.addCleanup(logging.disable, disabled)

    async def test_only_fixed_synthetic_and_public_inputs_and_summary_output(self):
        snapshot = parse_snapshot(PAGE)
        provider = AsyncMock(side_effect=[
            response('물의 화학식은 H2O입니다.'), response('현재 버킷은 20L입니다.'),
            response('차량 번호 정보가 없어 알 수 없습니다.'),
            response('최신 정식 버전은 Python 3.14.8입니다. ' + snapshot.url, [snapshot.url], 1),
        ])
        output = io.StringIO()
        with patch.object(live, 'request_answer', provider), patch.object(
                live, 'fetch_snapshot', return_value=snapshot), patch(
                'socket.socket.connect', side_effect=AssertionError('Network forbidden')), contextlib.redirect_stdout(output):
            self.assertEqual(await live.run(), 0)
        self.assertEqual(provider.await_count, 4)
        for call, case in zip(provider.await_args_list[:3], (live.CASES[0], live.CASES[2], live.CASES[3])):
            self.assertEqual(call.args, (case.query, list(case.facts)))
        self.assertEqual(provider.await_args_list[-1].args, (live.LATEST_QUERY, []))
        for private in (live.CASES[2].query, live.CASES[2].facts[0], 'H2O', snapshot.url):
            self.assertNotIn(private, output.getvalue())
        self.assertEqual(output.getvalue().count('PASS'), 4)

    async def test_source_failure_skips_current_model_and_raw_error(self):
        provider = AsyncMock(return_value=response('bad synthetic answer'))
        output = io.StringIO()
        with patch.object(live, 'request_answer', provider), patch.object(live, 'fetch_snapshot',
                side_effect=RuntimeError('synthetic-private-exception')), contextlib.redirect_stdout(output):
            self.assertEqual(await live.run(), 1)
        self.assertEqual(provider.await_count, 3)
        self.assertNotIn('synthetic-private-exception', output.getvalue())
        self.assertIn('official_latest ERROR', output.getvalue())
