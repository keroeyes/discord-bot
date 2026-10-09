import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
import discord
from aiohttp import web
from main import Bot, bank_for, main
from subscription import SearchEvidence, SubscriptionAnswers
from test_bot import message


class EvidenceTests(unittest.TestCase):
    def test_requires_actual_completed_search_and_url_annotations(self):
        evidence = SearchEvidence()
        evidence.observe({'type': 'response.web_search_call.searching'})
        self.assertEqual(evidence.result('검색했다고 주장', 'model')['search_count'], 0)
        search = {'id': 'ws1', 'type': 'web_search_call', 'status': 'completed'}
        answer = {'type': 'message', 'content': [{'annotations': [
            {'type': 'url_citation', 'url': 'https://example.com/news'},
            {'type': 'url_citation', 'url': 'javascript:alert(1)'},
            {'type': 'url_citation', 'url': 'https://example.com/news'},
        ]}]}
        evidence.observe({'type': 'response.output_item.done', 'item': search})
        evidence.observe({'type': 'response.output_item.done', 'item': answer})
        evidence.observe({'type': 'response.completed', 'response': {'output': [search, answer]}})
        result = evidence.result('답변 citeturn0search0', 'model')
        self.assertEqual(result['search_count'], 1)
        self.assertEqual(result['sources'], ['https://example.com/news'])
        self.assertIn('<https://example.com/news>', result['text'])
        self.assertNotIn('', result['text'])

    def test_empty_answer_is_error_and_search_without_sources_is_labeled(self):
        evidence = SearchEvidence()
        with self.assertRaises(ValueError):
            evidence.result(' ', 'model')
        evidence.observe({'type': 'response.output_item.done', 'item': {
            'id': 's', 'type': 'web_search_call', 'status': 'completed'}})
        self.assertIn('출처를 확보하지 못', evidence.result('답변', 'model')['text'])


class SubscriptionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, ANSWER_PROVIDER='subscription',
                              PRIVATE_MEMORY_REPLIES='', USER_COOLDOWN_SECONDS='', ALLOWED_GUILD_IDS='')
        self.env.start()
        self.addCleanup(self.env.stop)
        self.memory = NS(enabled=True, url='http://private.invalid', api_key=None,
                         recall=AsyncMock(return_value=[]), reflect=AsyncMock(),
                         save=AsyncMock(), close=AsyncMock())
        self.bot = Bot(None, self.memory, intents=discord.Intents.default())
        self.bot.subscription = NS(answer=AsyncMock(return_value='검색으로 확인한 답변 https://example.com'))
        self.bot._connection.user = NS(id=123)

    async def asyncTearDown(self):
        await self.bot.close()

    async def test_reported_general_questions_never_use_reflect_or_require_memory(self):
        for question in ['분당쪽 잘하는 갈비집 추천해줘', '아이폰 현재 문제가 뭐지']:
            msg = message('!질문 ' + question)
            await self.bot.on_message(msg)
            self.bot.subscription.answer.assert_awaited_with(question, [])
            self.memory.recall.assert_awaited_with(bank_for(msg, 123), question)
            self.assertIn('https://example.com', msg.channel.send.call_args.args[0])
        self.memory.reflect.assert_not_awaited()
        self.memory.save.assert_not_awaited()
        self.assertIsNone(self.bot.ai)

    async def test_memory_is_optional_reference_and_recall_failure_is_disclosed(self):
        self.memory.recall.return_value = ['버킷은 18L']
        await self.bot.on_message(message('!질문 내 버킷?'))
        self.bot.subscription.answer.assert_awaited_with('내 버킷?', ['버킷은 18L'])
        self.memory.recall.side_effect = RuntimeError('secret')
        msg = message('!질문 안녕')
        await self.bot.on_message(msg)
        self.bot.subscription.answer.assert_awaited_with('안녕', [])
        self.assertIn('기억 없이', msg.channel.send.call_args.args[0])
        self.assertNotIn('secret', msg.channel.send.call_args.args[0])

    async def test_private_reply_and_failed_dm_never_publish_answer(self):
        self.bot.private_memory_replies = True
        msg = message('!질문 내 버킷?')
        await self.bot.on_message(msg)
        msg.channel.send.assert_not_awaited()
        msg.author.send.assert_awaited_once()
        self.memory.recall.assert_awaited_with(bank_for(msg, 123), '내 버킷?')
        msg = message('!질문 내 버킷?')
        msg.author.send.side_effect = discord.Forbidden(NS(status=403, reason='Forbidden'), 'secret')
        await self.bot.on_message(msg)
        self.assertNotIn('example.com', msg.channel.send.call_args.args[0])

    async def test_answer_error_never_falls_back_to_paid_api(self):
        self.bot.ai = NS(chat=NS(completions=NS(create=AsyncMock())), close=AsyncMock())
        self.bot.subscription.answer.side_effect = RuntimeError('secret')
        msg = message('!질문 현재 이슈')
        await self.bot.on_message(msg)
        self.bot.ai.chat.completions.create.assert_not_awaited()
        self.memory.reflect.assert_not_awaited()
        self.assertIn('처리하지 못', msg.channel.send.call_args.args[0])
        self.assertNotIn('secret', msg.channel.send.call_args.args[0])

    def test_subscription_startup_needs_no_api_key(self):
        with patch.dict(os.environ, DISCORD_TOKEN='fake', OPENAI_API_KEY='',
                        HINDSIGHT_URL='http://private.invalid'):
            with patch('main.AsyncOpenAI') as paid, patch('main.Bot') as bot:
                main()
                paid.assert_not_called()
                self.assertIsNone(bot.call_args.kwargs['ai'])


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_http_serialization_and_failure_validation(self):
        requests = []
        result = {'version': 'subscription-search-v3', 'text': '답변',
                  'search_count': 1, 'sources': ['https://example.com']}
        async def handle(request):
            requests.append((request.path, await request.json(), request.headers.get('Authorization')))
            return web.json_response(result)
        app = web.Application()
        app.router.add_post('/ext/answers', handle)
        runner = web.AppRunner(app)
        await runner.setup()
        try:
            site = web.TCPSite(runner, '127.0.0.1', 0)
            await site.start()
            port = site._server.sockets[0].getsockname()[1]
            client = SubscriptionAnswers(f'http://127.0.0.1:{port}', 'fake-key')
            self.assertEqual(await client.answer('질문', ['기억']), '답변')
            self.assertEqual(requests, [('/ext/answers', {'query': '질문', 'facts': ['기억']}, 'Bearer fake-key')])
            result['text'] = ''
            with self.assertRaises(ValueError):
                await client.answer('질문', [])
        finally:
            await runner.cleanup()
