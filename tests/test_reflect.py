import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import discord
from aiohttp import web

from main import Bot, Memory, answer_provider_config, bank_for, main
from test_bot import message


class ReflectRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {
            'ANSWER_PROVIDER': 'hindsight', 'USER_COOLDOWN_SECONDS': '',
            'ALLOWED_GUILD_IDS': '', 'PRIVATE_MEMORY_REPLIES': '',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.memory = NS(enabled=True, reflect=AsyncMock(return_value='18L예요.'),
                         save=AsyncMock(), recall=AsyncMock(), close=AsyncMock())
        self.bot = Bot(None, self.memory, intents=discord.Intents.default())
        self.bot._connection.user = NS(id=123)

    async def asyncTearDown(self):
        await self.bot.close()

    async def test_question_uses_scoped_bank_without_auto_save(self):
        for msg in [message('!질문 내 버킷?'), message('!질문 내 버킷?', guild=None),
                    message('!질문 내 버킷?', user=11, channel=31)]:
            await self.bot.on_message(msg)
            self.memory.reflect.assert_awaited_with(bank_for(msg, 123), '내 버킷?')
            self.assertEqual(msg.channel.send.call_args.args[0], '18L예요.')
        self.memory.save.assert_not_awaited()
        self.memory.recall.assert_not_awaited()
        self.assertIsNone(self.bot.ai)

    async def test_error_does_not_fallback_to_paid_client_or_leak_details(self):
        self.bot.ai = NS(chat=NS(completions=NS(create=AsyncMock())), close=AsyncMock())
        self.memory.reflect.side_effect = RuntimeError('secret-token')
        msg = message('!질문 안녕')
        await self.bot.on_message(msg)
        self.assertIn('처리하지 못했', msg.channel.send.call_args.args[0])
        self.assertNotIn('secret-token', msg.channel.send.call_args.args[0])
        self.bot.ai.chat.completions.create.assert_not_awaited()
        self.memory.recall.assert_not_awaited()
        self.memory.save.assert_not_awaited()

    async def test_private_reply_keeps_original_bank(self):
        self.bot.private_memory_replies = True
        msg = message('!질문 버킷')
        await self.bot.on_message(msg)
        self.memory.reflect.assert_awaited_once_with(bank_for(msg, 123), '버킷')
        msg.channel.send.assert_not_awaited()
        self.assertEqual(msg.author.send.call_args.args[0], '18L예요.')

    async def test_private_reply_failure_never_publishes_answer(self):
        self.bot.private_memory_replies = True
        msg = message('!질문 버킷')
        msg.author.send.side_effect = discord.Forbidden(NS(status=403, reason='Forbidden'), 'private-secret')
        await self.bot.on_message(msg)
        output = msg.channel.send.call_args.args[0]
        self.assertIn('DM', output)
        self.assertNotIn('18L', output)
        self.assertNotIn('private-secret', output)

    async def test_status_names_actual_answer_route(self):
        msg = message('!봇상태')
        await self.bot.on_message(msg)
        output = msg.channel.send.call_args.args[0]
        self.assertIn('답변 경로: hindsight', output)
        self.assertNotIn('gpt-4o', output)

    def test_configuration_rejects_invalid_or_missing_server(self):
        with patch.dict(os.environ, ANSWER_PROVIDER='other'):
            with self.assertRaises(ValueError):
                answer_provider_config()
        with patch.dict(os.environ, ANSWER_PROVIDER=''):
            self.assertEqual(answer_provider_config(), 'openai')
        with self.assertRaises(ValueError):
            Bot(None, Memory(), intents=discord.Intents.default())

    def test_startup_does_not_require_or_construct_openai_client(self):
        with patch.dict(os.environ, {'DISCORD_TOKEN': 'fake-token', 'OPENAI_API_KEY': '',
                                    'HINDSIGHT_URL': 'http://test.invalid'}):
            with patch('main.AsyncOpenAI') as openai_client, patch('main.Bot') as bot:
                main()
                openai_client.assert_not_called()
                self.assertIsNone(bot.call_args.kwargs['ai'])
                bot.return_value.run.assert_called_once_with('fake-token')


class ReflectSDKTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.answer = '18L예요.'
        async def handle(request):
            self.requests.append((request.method, request.path, await request.json(),
                                  request.headers.get('Authorization')))
            return web.json_response({'text': self.answer})
        app = web.Application()
        app.router.add_post('/{path:.*}', handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.memory = Memory(f'http://127.0.0.1:{port}', api_key='fake-test-key')

    async def asyncTearDown(self):
        await self.memory.close()
        await self.runner.cleanup()

    async def test_sdk_uses_reflect_endpoint_and_does_not_retain(self):
        self.assertEqual(await self.memory.reflect('isolated-bank', '내 버킷?'), '18L예요.')
        self.assertEqual(len(self.requests), 1)
        method, path, body, auth = self.requests[0]
        self.assertEqual(method, 'POST')
        self.assertTrue(path.endswith('/banks/isolated-bank/reflect'))
        self.assertTrue(body['query'].endswith('사용자 질문:\n내 버킷?'))
        self.assertEqual(body['budget'], 'low')
        self.assertEqual(body['max_tokens'], 2000)
        self.assertEqual(auth, 'Bearer fake-test-key')

    async def test_empty_response_is_failure(self):
        self.answer = ' '
        with self.assertRaises(ValueError):
            await self.memory.reflect('isolated-bank', '내 버킷?')
