"""Endpoint lifecycle unit tests; no Hindsight service or model calls.

Only route registration and optional Hindsight imports are stubbed. These are
not HTTP integration tests; the actual answer coroutine and Pydantic input run.
"""
import asyncio
import importlib.util
import os
from pathlib import Path
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch


class RouterStub:
    def __init__(self):
        self.endpoints = {}

    def get(self, path):
        return self.post(path)

    def post(self, path):
        def register(endpoint):
            self.endpoints[path] = endpoint
            return endpoint
        return register


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def load_extension():
    stubs = {
        'fastapi': NS(APIRouter=RouterStub, HTTPException=HTTPError),
        'hindsight_api': NS(),
        'hindsight_api.extensions': NS(),
        'hindsight_api.extensions.http': NS(HttpExtension=object),
        'hindsight_api.engine': NS(),
        'hindsight_api.engine.providers': NS(),
        'hindsight_api.engine.providers.codex_llm': NS(CodexLLM=object),
    }
    spec = importlib.util.spec_from_file_location(
        'extension_under_test', Path(__file__).resolve().parents[1] / 'subscription_extension.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict('sys.modules', stubs):
        spec.loader.exec_module(module)
    return module


class CleanupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.extension = load_extension()
        self.answer = self.extension.SubscriptionExtension().get_router(None).endpoints['/answers']
        self.body = self.extension.AnswerRequest(query='synthetic question')
        self.provider = NS(call=AsyncMock(return_value=NS(content='synthetic answer')),
                           cleanup=AsyncMock(side_effect=RuntimeError('private-cleanup-token')))
        from subscription import SearchEvidence
        self.provider.evidence = SearchEvidence()
        self.env = patch.dict(os.environ, HINDSIGHT_API_LLM_CODEX_HOME='synthetic-home')
        self.env.start()
        self.addCleanup(self.env.stop)

    async def test_cleanup_failure_preserves_answer_and_releases_capacity(self):
        with patch.object(self.extension, 'SearchModel', return_value=self.provider), \
             patch.object(self.extension.log, 'warning') as logged:
            # More requests than the two slots detect a leaked semaphore permit.
            for _ in range(3):
                result = await asyncio.wait_for(self.answer(self.body), timeout=1)
                self.assertEqual(result['text'], 'synthetic answer')
        self.assertEqual(self.provider.cleanup.await_count, 3)
        self.assertNotIn('private-cleanup-token', str(logged.call_args_list))

    async def test_cleanup_failure_preserves_sanitized_generation_error(self):
        self.provider.call.side_effect = ValueError('private-generation-token')
        with patch.object(self.extension, 'SearchModel', return_value=self.provider), \
             patch.object(self.extension.log, 'warning') as logged:
            for _ in range(3):
                with self.assertRaises(HTTPError) as caught:
                    await asyncio.wait_for(self.answer(self.body), timeout=1)
                self.assertEqual(caught.exception.status_code, 503)
                self.assertEqual(caught.exception.detail,
                                 'Subscription answer temporarily unavailable')
        self.assertNotIn('private-generation-token', str(logged.call_args_list))
        self.assertNotIn('private-cleanup-token', str(logged.call_args_list))

    async def test_cancellation_is_not_suppressed_and_releases_capacity(self):
        self.provider.cleanup.side_effect = asyncio.CancelledError()
        with patch.object(self.extension, 'SearchModel', return_value=self.provider):
            for _ in range(3):
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(self.answer(self.body), timeout=1)
