import asyncio
import json
import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import discord
from aiohttp import web
from hindsight_client_api.exceptions import ApiException

from main import Bot, Memory, bank_for, cost_protection_config, memory_facts_json, parse_command, private_memory_config, send_text


class Typing:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def message(text, user=10, guild=20, channel=30, bot=False):
    return NS(content=text, id=99, author=NS(id=user, bot=bot, send=AsyncMock()),
              guild=NS(id=guild) if guild is not None else None,
              channel=NS(id=channel, send=AsyncMock(), typing=Typing))


class BotTests(unittest.IsolatedAsyncioTestCase):
    def test_memory_budget_keeps_whole_json_and_facts(self):
        facts = ['가\\"'*1600, '새 버킷은 20L', '예전 버킷은 18L']
        encoded = memory_facts_json(facts)
        self.assertLessEqual(len(encoded), 6000)
        self.assertEqual(json.loads(encoded), facts[1:])
        self.assertEqual(len(json.loads(memory_facts_json(['기억']*12))), 10)

    def test_invalid_memory_is_rejected_not_empty(self):
        for facts in [None, '문자열', [None], [123], [' '], ['내용', {}], ['가'*6000]]:
            with self.subTest(facts=type(facts).__name__):
                with self.assertRaises(ValueError):
                    memory_facts_json(facts)

    async def test_malformed_memory_question_falls_back(self):
        self.memory.recall.return_value = ['내용', None]
        msg = message('!질문 버킷')
        await self.bot.on_message(msg)
        prompt = self.ai.chat.completions.create.call_args.kwargs['messages']
        self.assertEqual(len(prompt), 2)
        self.assertIn('기억 없이', msg.channel.send.call_args.args[0])

    async def test_malformed_memory_search_does_not_claim_no_memory(self):
        self.memory.recall.return_value = ['내용', None]
        msg = message('!기억검색 버킷')
        await self.bot.on_message(msg)
        self.assertIn('처리하지 못했', msg.channel.send.call_args.args[0])
        self.assertNotIn('관련 기억이 없', msg.channel.send.call_args.args[0])
        self.ai.chat.completions.create.assert_not_awaited()

    async def test_large_memory_prompt_is_valid_json(self):
        self.memory.recall.return_value = ['가'*4000, '나'*4000, '버킷은 20L']
        await self.bot.on_message(message('!질문 버킷'))
        prompt = self.ai.chat.completions.create.call_args.kwargs['messages']
        encoded = prompt[1]['content'].split('\n', 1)[1]
        self.assertEqual(json.loads(encoded), ['가'*4000, '버킷은 20L'])
        self.assertLessEqual(len(encoded), 6000)

    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {'USER_COOLDOWN_SECONDS': '', 'ALLOWED_GUILD_IDS': '', 'PRIVATE_MEMORY_REPLIES': '', 'ANSWER_PROVIDER': ''})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.ai = NS(chat=NS(completions=NS(create=AsyncMock(
            return_value=NS(choices=[NS(message=NS(content='18L예요.'))])))), close=AsyncMock())
        self.memory = NS(enabled=True, save=AsyncMock(), recall=AsyncMock(return_value=['버킷은 18L']),
                         delete=AsyncMock(), close=AsyncMock())
        self.bot = Bot(self.ai, self.memory, intents=discord.Intents.default())
        self.bot._connection.user = NS(id=123)

    async def asyncTearDown(self):
        await self.bot.close()

    def test_exact_command_and_whitespace(self):
        self.assertIsNone(parse_command('!질문입니다'))
        self.assertEqual(parse_command('!질문\n 내 버킷?'), ('!질문', '내 버킷?'))
        self.assertEqual(parse_command('!질문'), ('!질문', ''))

    def test_scope_isolation(self):
        base = bank_for(message(''), 123)
        for msg, bot_id in [(message('', user=11),123), (message('', guild=21),123),
                            (message('', channel=31),123), (message('', guild=None),123),
                            (message(''),124)]:
            self.assertNotEqual(base, bank_for(msg, bot_id))
        self.assertEqual(base, bank_for(message(''),123))

    async def test_question_uses_memory_without_auto_save(self):
        msg = message('!질문 내 버킷?')
        await self.bot.on_message(msg)
        self.memory.recall.assert_awaited_once_with(bank_for(msg,123), '내 버킷?')
        self.memory.save.assert_not_awaited()
        prompt = self.ai.chat.completions.create.call_args.kwargs['messages']
        self.assertIn('18L', prompt[1]['content'])
        self.assertEqual(prompt[-1]['content'], '내 버킷?')

    async def test_explicit_save(self):
        msg = message('!기억 버킷은 18L')
        await self.bot.on_message(msg)
        self.memory.save.assert_awaited_once_with(bank_for(msg,123), '버킷은 18L',99)
        self.ai.chat.completions.create.assert_not_awaited()

    async def test_delete_requires_literal_confirmation(self):
        msg = message('!기억삭제 버킷')
        await self.bot.on_message(msg)
        self.memory.delete.assert_not_awaited()
        msg = message('!기억삭제 확인')
        await self.bot.on_message(msg)
        self.memory.delete.assert_awaited_once_with(bank_for(msg,123))

    async def test_disabled_memory_preserves_question(self):
        self.memory.enabled = False
        await self.bot.on_message(message('!질문 안녕'))
        self.ai.chat.completions.create.assert_awaited_once()
        self.memory.recall.assert_not_awaited()
        msg = message('!기억 테스트')
        await self.bot.on_message(msg)
        self.assertIn('HINDSIGHT_URL', msg.channel.send.call_args.args[0])
        self.memory.save.assert_not_awaited()

    async def test_recall_failure_falls_back_and_never_leaks_exception(self):
        self.memory.recall.side_effect = RuntimeError('secret-token')
        msg = message('!질문 내 버킷?')
        await self.bot.on_message(msg)
        self.ai.chat.completions.create.assert_awaited_once()
        output = msg.channel.send.call_args.args[0]
        self.assertIn('기억 없이',output)
        self.assertNotIn('secret-token',output)

    async def test_failed_save_does_not_claim_success(self):
        self.memory.save.side_effect = TimeoutError('secret-token')
        msg = message('!기억 내용')
        await self.bot.on_message(msg)
        output = msg.channel.send.call_args.args[0]
        self.assertIn('확인하지 못했',output)
        self.assertNotIn('secret-token',output)

    async def test_ignores_bots_and_empty_question(self):
        await self.bot.on_message(message('!질문 안녕',bot=True))
        await self.bot.on_message(message('!질문'))
        self.ai.chat.completions.create.assert_not_awaited()

    async def test_long_output_preserves_content_and_disables_mentions(self):
        channel = message('').channel
        text = '@everyone ' + '가'*5000
        await send_text(channel,text)
        sent = channel.send.call_args_list
        self.assertEqual(''.join(x.args[0] for x in sent),text)
        for call in sent:
            self.assertLessEqual(len(call.args[0]),1900)
            self.assertFalse(call.kwargs['allowed_mentions'].everyone)


    def test_cost_config(self):
        self.assertEqual(cost_protection_config(), (0, set()))
        with patch.dict(os.environ, USER_COOLDOWN_SECONDS=' 2.5 ', ALLOWED_GUILD_IDS='20, 21,20'):
            self.assertEqual(cost_protection_config(), (2.5, {20, 21}))
        for value in ['-1', 'nan', 'inf', 'oops']:
            with patch.dict(os.environ, USER_COOLDOWN_SECONDS=value):
                with self.assertRaises(ValueError):
                    cost_protection_config()
        for value in ['20,', '0', '-20', 'oops']:
            with patch.dict(os.environ, ALLOWED_GUILD_IDS=value):
                with self.assertRaises(ValueError):
                    cost_protection_config()

    async def test_allowed_guild_and_dm_preserve_banks(self):
        self.bot.allowed_guilds = {20}
        for msg in [message('!기억 내용'), message('!기억 내용', guild=None)]:
            await self.bot.on_message(msg)
            self.memory.save.assert_awaited_with(bank_for(msg, 123), '내용', 99)
        self.assertEqual(self.memory.save.await_count, 2)

    async def test_disallowed_guild_blocks_all_commands_without_api(self):
        self.bot.allowed_guilds = {21}
        for command in ['!질문 내용', '!기억 내용', '!기억검색 내용', '!기억삭제 확인', '!봇상태']:
            msg = message(command)
            await self.bot.on_message(msg)
            self.assertIn('이 서버', msg.channel.send.call_args.args[0])
        self.ai.chat.completions.create.assert_not_awaited()
        self.memory.save.assert_not_awaited()
        self.memory.recall.assert_not_awaited()
        self.memory.delete.assert_not_awaited()
        self.assertFalse(self.bot.cooldown_until)

    async def test_shared_user_cooldown_and_expiry(self):
        self.bot.user_cooldown = 10
        with patch('main.monotonic', return_value=100):
            await self.bot.on_message(message('!기억 내용'))
            for command in ['!질문 내용', '!기억 내용', '!기억검색 내용']:
                msg = message(command, guild=None, channel=31)
                await self.bot.on_message(msg)
                self.assertIn('10초', msg.channel.send.call_args.args[0])
            await self.bot.on_message(message('!기억검색 내용', user=11))
        self.ai.chat.completions.create.assert_not_awaited()
        self.assertEqual(self.memory.save.await_count, 1)
        self.assertEqual(self.memory.recall.await_count, 1)
        with patch('main.monotonic', return_value=110):
            await self.bot.on_message(message('!질문 내용'))
        self.ai.chat.completions.create.assert_awaited_once()
        self.assertNotIn(11, self.bot.cooldown_until)

    async def test_status_delete_and_invalid_requests_do_not_use_cooldown(self):
        self.bot.user_cooldown = 10
        for content in ['!질문', '!질문 ' + '가'*6001, '!봇상태', '!기억삭제 확인']:
            await self.bot.on_message(message(content))
        self.assertFalse(self.bot.cooldown_until)
        with patch('main.monotonic', return_value=100):
            await self.bot.on_message(message('!질문 내용'))
            await self.bot.on_message(message('!봇상태'))
            await self.bot.on_message(message('!기억삭제 확인'))
        self.assertEqual(self.memory.delete.await_count, 2)
        self.ai.chat.completions.create.assert_awaited_once()

    async def test_concurrent_channels_only_one_cost_request(self):
        self.bot.user_cooldown = 10
        with patch('main.monotonic', return_value=100):
            await asyncio.gather(
                self.bot.on_message(message('!질문 내용', channel=30)),
                self.bot.on_message(message('!기억 내용', channel=31)),
                self.bot.on_message(message('!기억검색 내용', guild=None, channel=32)),
            )
        self.assertEqual(self.ai.chat.completions.create.await_count, 1)
        self.memory.save.assert_not_awaited()
        self.assertEqual(self.memory.recall.await_count, 1)

    async def test_failed_api_request_keeps_cooldown(self):
        self.bot.user_cooldown = 10
        self.memory.save.side_effect = TimeoutError()
        with patch('main.monotonic', return_value=100):
            await self.bot.on_message(message('!기억 내용'))
            await self.bot.on_message(message('!기억 내용', channel=31))
        self.memory.save.assert_awaited_once()

    async def test_unconfigured_memory_does_not_consume_cooldown(self):
        self.bot.user_cooldown = 10
        self.memory.enabled = False
        await self.bot.on_message(message('!기억 내용'))
        await self.bot.on_message(message('!기억검색 내용'))
        self.assertFalse(self.bot.cooldown_until)
        await self.bot.on_message(message('!질문 내용'))
        self.ai.chat.completions.create.assert_awaited_once()

    def test_private_reply_config(self):
        self.assertFalse(private_memory_config())
        for value in ['true', '1', 'YES', ' on ']:
            with patch.dict(os.environ, PRIVATE_MEMORY_REPLIES=value):
                self.assertTrue(private_memory_config())
                bot = Bot(self.ai, self.memory, intents=discord.Intents.default())
                self.assertTrue(bot.private_memory_replies)
        for value in ['', 'false', '0', 'NO', ' off ']:
            with patch.dict(os.environ, PRIVATE_MEMORY_REPLIES=value):
                self.assertFalse(private_memory_config())
        with patch.dict(os.environ, PRIVATE_MEMORY_REPLIES='oops'):
            with self.assertRaises(ValueError):
                private_memory_config()

    async def test_public_results_by_default(self):
        for command, expected in [('!기억검색 버킷', '버킷은 18L'), ('!질문 버킷', '18L예요.')]:
            msg = message(command)
            await self.bot.on_message(msg)
            self.assertIn(expected, msg.channel.send.call_args.args[0])
            msg.author.send.assert_not_awaited()

    async def test_private_results_keep_original_bank(self):
        self.bot.private_memory_replies = True
        for command, expected in [('!기억검색 버킷', '버킷은 18L'), ('!질문 버킷', '18L예요.')]:
            msg = message(command)
            await self.bot.on_message(msg)
            self.assertIn(expected, msg.author.send.call_args.args[0])
            self.memory.recall.assert_awaited_with(bank_for(msg, 123), '버킷')
            msg.channel.send.assert_not_awaited()
            self.assertFalse(msg.author.send.call_args.kwargs['allowed_mentions'].everyone)
        self.memory.save.assert_not_awaited()

    async def test_private_mode_preserves_dm_bank_and_channel(self):
        self.bot.private_memory_replies = True
        for command in ['!기억검색 버킷', '!질문 버킷']:
            msg = message(command, guild=None)
            await self.bot.on_message(msg)
            msg.channel.send.assert_awaited_once()
            msg.author.send.assert_not_awaited()
            self.memory.recall.assert_awaited_with(bank_for(msg, 123), '버킷')
            self.assertNotEqual(bank_for(msg, 123), bank_for(message(command), 123))

    async def test_dm_failures_never_publish_content(self):
        self.bot.private_memory_replies = True
        for exception in [discord.Forbidden(NS(status=403, reason='Forbidden'), 'private-secret'),
                          discord.HTTPException(NS(status=500, reason='Failure'), 'private-secret')]:
            for command in ['!기억검색 버킷', '!질문 버킷']:
                msg = message(command)
                msg.author.send.side_effect = exception
                await self.bot.on_message(msg)
                msg.channel.send.assert_awaited_once()
                output = msg.channel.send.call_args.args[0]
                self.assertIn('DM', output)
                for secret in ['18L', 'private-secret', '버킷']:
                    self.assertNotIn(secret, output)

    async def test_partial_dm_failure_never_falls_back_publicly(self):
        self.bot.private_memory_replies = True
        self.memory.recall.return_value = ['private-secret' * 400]
        msg = message('!기억검색 버킷')
        msg.author.send.side_effect = [None, discord.Forbidden(NS(status=403, reason='Forbidden'), 'secret')]
        await self.bot.on_message(msg)
        self.assertEqual(msg.author.send.await_count, 2)
        msg.channel.send.assert_awaited_once()
        self.assertNotIn('private-secret', msg.channel.send.call_args.args[0])

    async def test_private_empty_memory_and_question_fallbacks(self):
        self.bot.private_memory_replies = True
        self.memory.recall.return_value = []
        msg = message('!기억검색 버킷')
        await self.bot.on_message(msg)
        self.assertEqual(msg.author.send.call_args.args[0], '관련 기억이 없어요.')
        msg.channel.send.assert_not_awaited()
        for state in ['empty', 'failed', 'disabled']:
            self.memory.enabled = state != 'disabled'
            self.memory.recall.side_effect = RuntimeError('secret') if state == 'failed' else None
            msg = message('!질문 버킷')
            await self.bot.on_message(msg)
            self.assertIn('18L예요.', msg.author.send.call_args.args[0])
            if state == 'failed':
                self.assertIn('기억 없이', msg.author.send.call_args.args[0])
            msg.channel.send.assert_not_awaited()

    async def test_private_mode_preserves_save_delete_and_generic_errors(self):
        self.bot.private_memory_replies = True
        for command in ['!기억 내용', '!기억삭제 확인', '!봇상태', '!질문']:
            msg = message(command)
            await self.bot.on_message(msg)
            msg.channel.send.assert_awaited_once()
            msg.author.send.assert_not_awaited()
        self.memory.recall.side_effect = RuntimeError('private-secret')
        msg = message('!기억검색 버킷')
        await self.bot.on_message(msg)
        self.assertNotIn('private-secret', msg.channel.send.call_args.args[0])



class SDKTests(unittest.IsolatedAsyncioTestCase):
    """실제 설치한 Hindsight SDK의 HTTP 직렬화·응답 파싱을 로컬 서버로 확인."""
    async def asyncSetUp(self):
        self.requests = []
        self.status = 200
        self.success = True
        async def handle(request):
            body = await request.json() if request.method == 'POST' else None
            self.requests.append((request.method,request.path,body,request.headers.get('Authorization')))
            if self.status != 200:
                return web.json_response({'detail':'failure'},status=self.status)
            if request.method == 'POST' and request.path.endswith('/memories'):
                return web.json_response({'success':self.success,'bank_id':'test','items_count':1,'async':False})
            if request.path.endswith('/recall'):
                return web.json_response({'results':[{'id':'1','text':'18L 버킷','type':'world'}]})
            return web.json_response({'success':True})
        app = web.Application()
        app.router.add_route('*','/{path:.*}',handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner,'127.0.0.1',0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.memory = Memory(f'http://127.0.0.1:{port}',api_key='fake-test-key')

    async def asyncTearDown(self):
        await self.memory.close()
        await self.runner.cleanup()

    async def test_sdk_save_recall_delete(self):
        await self.memory.save('test','18L 버킷',99)
        self.assertEqual(await self.memory.recall('test','버킷?'),['18L 버킷'])
        await self.memory.delete('test')
        self.assertEqual([r[0] for r in self.requests],['POST','POST','DELETE'])
        self.assertTrue(self.requests[0][1].endswith('/banks/test/memories'))
        self.assertEqual(self.requests[0][2]['items'][0]['content'],'18L 버킷')
        self.assertEqual(self.requests[0][2]['items'][0]['document_id'],'discord-99')
        self.assertEqual(self.requests[0][3],'Bearer fake-test-key')
        self.assertTrue(self.requests[-1][1].endswith('/banks/test'))

    async def test_not_found_is_empty_but_unauthorized_is_error(self):
        self.status = 404
        self.assertEqual(await self.memory.recall('test','버킷'),[])
        await self.memory.delete('test')
        self.status = 401
        with self.assertRaises(ApiException):
            await self.memory.recall('test','버킷')

    async def test_false_success_is_not_saved(self):
        self.success = False
        with self.assertRaises(RuntimeError):
            await self.memory.save('test','18L 버킷',99)


if __name__ == '__main__':
    unittest.main()

