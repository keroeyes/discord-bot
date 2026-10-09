import asyncio
import json
import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

import discord
from aiohttp import web
import observability as obs
from main import Bot
from subscription import SubscriptionAnswers, SearchEvidence, validate_answer, valid_source_url
from test_bot import message


class BotTraceCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, ANSWER_PROVIDER='subscription',
                              PRIVATE_MEMORY_REPLIES='', USER_COOLDOWN_SECONDS='',
                              ALLOWED_GUILD_IDS='', BOT_LANGFUSE_ENABLED='')
        self.env.start()
        self.addCleanup(self.env.stop)
        self.memory = NS(enabled=True, url='http://private.invalid', api_key=None,
                         recall=AsyncMock(return_value=[]), reflect=AsyncMock(),
                         save=AsyncMock(), delete=AsyncMock(), close=AsyncMock())
        self.bot = Bot(None, self.memory, intents=discord.Intents.default())
        self.bot._connection.user = NS(id=123)
        self.bot.subscription = NS(answer=AsyncMock(return_value='synthetic-answer'))
        self.client_patch = patch('observability._get_client', return_value=None)
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)

    async def asyncTearDown(self):
        await self.bot.close()

    async def capture(self, msg):
        with patch('observability.log.info') as logged:
            await self.bot.on_message(msg)
        self.assertEqual(logged.call_count, 1)
        return json.loads(logged.call_args.args[1])


class TraceTests(BotTraceCase):
    async def test_private_payload_and_error_are_never_logged(self):
        self.memory.recall.side_effect = RuntimeError('secret-token-private-memory')
        trace = await self.capture(message('!질문 personal-secret@example.com'))
        self.assertEqual(trace['status'], 'degraded')
        self.assertEqual(trace['search_state'], 'not_observed')
        self.assertIsNone(trace['memory_count'])
        encoded = json.dumps(trace)
        for secret in ['secret-token', 'personal-secret', 'private-memory', 'private.invalid']:
            self.assertNotIn(secret, encoded)

    async def test_empty_memory_is_distinct_from_failed_recall(self):
        trace = await self.capture(message('!질문 hello'))
        self.assertEqual(trace['memory_count'], 0)
        self.assertEqual(trace['status'], 'completed')
        self.assertEqual(trace['delivery'], 'completed')

    async def test_dm_failure_is_not_completed_and_no_public_answer(self):
        self.bot.private_memory_replies = True
        msg = message('!질문 hello')
        msg.author.send.side_effect = discord.Forbidden(NS(status=403, reason='Forbidden'), 'secret')
        trace = await self.capture(msg)
        self.assertEqual(trace['status'], 'delivery_failed')
        self.assertEqual(trace['stages'][-1]['status'], 'failed')
        self.assertNotIn('synthetic-answer', msg.channel.send.call_args.args[0])

    async def test_generation_failure_does_not_claim_completion(self):
        self.bot.subscription.answer.side_effect = TimeoutError('private-token')
        trace = await self.capture(message('!질문 hello'))
        self.assertEqual(trace['status'], 'failed')
        self.assertEqual(trace['delivery'], 'not_attempted')
        self.memory.reflect.assert_not_awaited()
        self.assertNotIn('private-token', json.dumps(trace))

    async def test_failed_save_is_not_completed(self):
        self.memory.save.side_effect = TimeoutError('private-token')
        trace = await self.capture(message('!기억 synthetic-memory'))
        self.assertEqual(trace['status'], 'failed')
        self.assertEqual(trace['stages'][0]['name'], 'memory_save')

    async def test_concurrent_requests_keep_separate_context(self):
        async def work(command, count):
            with obs.request_trace(command, 'subscription'):
                obs.record_memory(count)
                await asyncio.sleep(0)
                obs.record_search(count, count)
        with patch('observability.log.info') as logged:
            await asyncio.gather(work('!질문', 1), work('!기억검색', 2))
        traces = [json.loads(call.args[1]) for call in logged.call_args_list]
        self.assertEqual(len({t['request_id'] for t in traces}), 2)
        self.assertEqual({(t['memory_count'], t['search_count']) for t in traces}, {(1, 1), (2, 2)})

    async def test_http_evidence_and_size_limits(self):
        result = {'version': 'subscription-search-v3', 'text': 'synthetic-answer',
                  'search_count': 1, 'sources': ['https://example.com/source']}
        async def handle(request):
            return web.json_response(result)
        app = web.Application()
        app.router.add_post('/ext/answers', handle)
        runner = web.AppRunner(app)
        await runner.setup()
        try:
            server = web.TCPSite(runner, '127.0.0.1', 0)
            await server.start()
            port = server._server.sockets[0].getsockname()[1]
            self.bot.subscription = SubscriptionAnswers(f'http://127.0.0.1:{port}',
                                                         evidence_callback=obs.record_search)
            trace = await self.capture(message('!질문 synthetic question'))
            self.assertEqual(trace['search_state'], 'sources_present')
            self.assertEqual(trace['search_count'], 1)
            self.assertNotIn('example.com', json.dumps(trace))
            result['sources'] = []
            trace = await self.capture(message('!질문 another question'))
            self.assertEqual(trace['search_state'], 'sources_missing')
            result['search_count'] = True
            trace = await self.capture(message('!질문 invalid count'))
            self.assertEqual(trace['status'], 'failed')
            result['search_count'] = 0
            result['text'] = 'x' * 262145
            trace = await self.capture(message('!질문 oversized response'))
            self.assertEqual(trace['status'], 'failed')
        finally:
            await runner.cleanup()


class ContractTests(unittest.TestCase):
    def test_invalid_metadata_is_rejected(self):
        valid = {'version': 'subscription-search-v3', 'text': 'answer', 'search_count': 0, 'sources': []}
        cases = [('search_count', True), ('search_count', -1), ('search_count', '1'),
                 ('text', ' '), ('sources', [None]), ('sources', ['https://u:p@example.com']),
                 ('sources', ['https://[broken']), ('sources', ['javascript:alert(1)']),
                 ('sources', ['https://example.com'] * 9)]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    validate_answer(dict(valid, **{key: value}))

    def test_malformed_events_do_not_invent_search(self):
        evidence = SearchEvidence()
        for event in [None, [], {'type': 'response.completed', 'response': None},
                      {'type': 'response.output_item.done', 'item': None},
                      {'type': 'response.output_item.done', 'item': {
                          'type': 'web_search_call', 'status': 'completed', 'id': []}},
                      {'type': 'response.completed', 'response': {'output': 'bad'}}]:
            evidence.observe(event)
        self.assertEqual(evidence.result('answer', 'model')['search_count'], 0)
        with self.assertRaises(ValueError):
            evidence.result('citeturn0search0', 'model')

    def test_urls_reject_credentials_controls_and_invalid_ports(self):
        for url in ['https://u:p@example.com', 'https://[bad', 'https://example.com:99999',
                    'https://example.com/\nsecret', 'file:///etc/passwd']:
            self.assertFalse(valid_source_url(url))
        self.assertTrue(valid_source_url('https://example.com/article?q=test'))

    def test_langfuse_receives_only_allowlisted_metadata(self):
        root = Mock()
        child = Mock()
        root.start_observation.return_value = child
        client = Mock()
        client.start_observation.return_value = root
        with patch('observability._get_client', return_value=client), patch('observability.log.info'):
            with obs.request_trace('!질문', 'subscription'):
                with obs.stage('answer_generation'):
                    pass
                obs.record_search(1, 2)
        self.assertNotIn('input', client.start_observation.call_args.kwargs)
        self.assertNotIn('output', root.update.call_args.kwargs)
        root.end.assert_called_once()
        child.end.assert_called_once()

    def test_telemetry_outage_does_not_mask_application_exception(self):
        client = Mock()
        client.start_observation.side_effect = RuntimeError('secret')
        with patch('observability._get_client', return_value=client), patch('observability.log.info'):
            with self.assertRaisesRegex(ValueError, 'original'):
                with obs.request_trace('!질문', 'subscription'):
                    with obs.stage('answer_generation'):
                        raise ValueError('original')

    def test_missing_configuration_does_not_import_or_send(self):
        with patch.dict(os.environ, BOT_LANGFUSE_ENABLED='true', LANGFUSE_PUBLIC_KEY='',
                        LANGFUSE_SECRET_KEY='', LANGFUSE_BASE_URL=''), \
             patch.object(obs, '_client_attempted', False), patch.object(obs, '_client', None):
            self.assertIsNone(obs._get_client())
