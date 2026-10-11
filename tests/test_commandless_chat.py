"""Synthetic Discord routing; no live messages or provider requests."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import discord
import test_bot as fixtures
from main import bank_for


class CommandlessChat(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.BotTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await fixtures.BotTests.asyncTearDown(self)

    def sdk_message(self, text, *, guild=True, reference=None, resolved='absent'):
        channel = fixtures.message('').channel
        channel.guild = NS(id=20) if guild else None
        payload = {'id': '99', 'type': 19 if reference else 0, 'content': text,
                   'author': {'id': '10', 'username': 'synthetic',
                              'discriminator': '0', 'avatar': None, 'bot': False},
                   'mentions': [], 'mention_roles': [], 'attachments': [],
                   'embeds': [], 'components': []}
        if reference:
            payload['message_reference'] = reference
        if resolved != 'absent':
            payload['referenced_message'] = resolved
        return discord.Message(state=self.bot._connection, channel=channel, data=payload)

    async def test_real_sdk_dm_and_mention_messages(self):
        await self.bot.on_message(self.sdk_message('synthetic-dm', guild=False))
        await self.bot.on_message(self.sdk_message('<@123> synthetic-guild'))
        self.assertEqual(self.ai.chat.completions.create.await_count, 2)
        prompt = self.ai.chat.completions.create.call_args.kwargs['messages']
        self.assertEqual(prompt[-1]['content'], 'synthetic-guild')
        self.assertNotIn('synthetic-dm', str(prompt))

    async def test_real_sdk_reply_and_deleted_reference(self):
        original = {'id': '42', 'type': 0, 'content': 'synthetic-other-body',
                    'author': {'id': '123', 'username': 'synthetic-bot',
                               'discriminator': '0', 'avatar': None, 'bot': True}}
        ref = {'message_id': '42', 'channel_id': '30', 'guild_id': '20', 'type': 0}
        await self.bot.on_message(self.sdk_message('synthetic-reply', reference=ref,
                                                   resolved=original))
        prompt = self.ai.chat.completions.create.call_args.kwargs['messages']
        self.assertNotIn('synthetic-other-body', str(prompt))
        self.assertEqual(prompt[-1]['content'], 'synthetic-reply')
        await self.bot.on_message(self.sdk_message('synthetic-deleted', reference=ref,
                                                   resolved=None))
        self.assertEqual(self.ai.chat.completions.create.await_count, 1)

    async def test_real_sdk_uncached_reply_fetch(self):
        ref = {'message_id': '42', 'channel_id': '30', 'guild_id': '20'}
        msg = self.sdk_message('synthetic-reply', reference=ref)
        original = self.sdk_message('synthetic-bot-body')
        original.author = self.bot.user
        msg.channel.fetch_message = AsyncMock(return_value=original)
        await self.bot.on_message(msg)
        msg.channel.fetch_message.assert_awaited_once_with(42)
        self.ai.chat.completions.create.assert_awaited_once()

    async def test_subscription_plain_chat_keeps_context_and_wire_contract(self):
        self.bot.answer_provider = 'subscription'
        self.bot.subscription = NS(answer=AsyncMock(return_value='synthetic-answer'))
        await self.bot.on_message(fixtures.message('synthetic-first', guild=None))
        await self.bot.on_message(fixtures.message('synthetic-followup', guild=None))
        query, facts = self.bot.subscription.answer.call_args.args
        self.assertIn('synthetic-first', query)
        self.assertIn('synthetic-answer', query)
        self.assertTrue(query.endswith('synthetic-followup'))
        self.assertLessEqual(len(query), 6000)
        self.assertEqual(facts, ['버킷은 18L'])
        self.ai.chat.completions.create.assert_not_awaited()
        self.memory.save.assert_not_awaited()

    async def test_hindsight_plain_chat_keeps_context_without_auto_save(self):
        self.bot.answer_provider = 'hindsight'
        self.memory.reflect = AsyncMock(return_value='synthetic-answer')
        await self.bot.on_message(fixtures.message('synthetic-first', guild=None))
        await self.bot.on_message(fixtures.message('synthetic-followup', guild=None))
        bank, query = self.memory.reflect.call_args.args
        self.assertIn('synthetic-first', query)
        self.assertIn('synthetic-answer', query)
        self.assertTrue(query.endswith('synthetic-followup'))
        self.assertEqual(bank, bank_for(fixtures.message('', guild=None), 123))
        self.ai.chat.completions.create.assert_not_awaited()
        self.memory.save.assert_not_awaited()

    def reply(self, *, author=123, resolved=True):
        msg = fixtures.message('synthetic-followup')
        original = Mock(spec=discord.Message)
        original.author = NS(id=author)
        msg.reference = NS(type=discord.MessageReferenceType.reply,
                           channel_id=msg.channel.id, message_id=42,
                           resolved=original if resolved else None)
        msg.channel.fetch_message = AsyncMock(return_value=original)
        return msg

    async def test_dm_followup_keeps_context_without_saving(self):
        await self.bot.on_message(fixtures.message('synthetic-first', guild=None))
        await self.bot.on_message(fixtures.message('synthetic-followup', guild=None))
        prompt = self.ai.chat.completions.create.call_args.kwargs['messages']
        self.assertEqual([x['content'] for x in prompt[-3:]],
                         ['synthetic-first', '18L예요.', 'synthetic-followup'])
        self.memory.save.assert_not_awaited()

    async def test_mentions_strip_only_this_bot(self):
        for text in ('<@123> synthetic <@456>', '<@!123> synthetic <@456>'):
            await self.bot.on_message(fixtures.message(text))
            prompt = self.ai.chat.completions.create.call_args.kwargs['messages']
            self.assertEqual(prompt[-1]['content'], 'synthetic <@456>')

    async def test_ordinary_channel_messages_and_commands_are_ignored(self):
        for text, guild in [('synthetic', 20), ('<@456> synthetic', 20),
                            ('!그림 synthetic', None), ('!unknown', None), (' ', None)]:
            await self.bot.on_message(fixtures.message(text, guild=guild))
        self.ai.chat.completions.create.assert_not_awaited()

    async def test_reply_resolves_cached_and_uncached_bot_messages(self):
        for cached in (True, False):
            msg = self.reply(resolved=cached)
            await self.bot.on_message(msg)
            self.assertEqual(msg.channel.fetch_message.await_count, 0 if cached else 1)
        self.assertEqual(self.ai.chat.completions.create.await_count, 2)

    async def test_reply_does_not_import_another_users_context(self):
        await self.bot.on_message(fixtures.message('!질문 synthetic-private'))
        msg = self.reply()
        msg.author.id = 11
        await self.bot.on_message(msg)
        prompt = self.ai.chat.completions.create.call_args.kwargs['messages']
        self.assertNotIn('synthetic-private', str(prompt))

    async def test_other_author_deleted_forward_and_cross_channel_are_ignored(self):
        msg = self.reply(author=456)
        await self.bot.on_message(msg)
        msg = self.reply(resolved=False)
        msg.channel.fetch_message.side_effect = discord.NotFound(
            NS(status=404, reason='Not Found'), 'synthetic')
        await self.bot.on_message(msg)
        msg = self.reply()
        msg.reference.type = discord.MessageReferenceType.forward
        await self.bot.on_message(msg)
        msg = self.reply()
        msg.reference.channel_id = 31
        await self.bot.on_message(msg)
        self.ai.chat.completions.create.assert_not_awaited()

    async def test_mention_only_returns_help_and_bot_messages_are_ignored(self):
        msg = fixtures.message('<@123>')
        await self.bot.on_message(msg)
        msg.channel.send.assert_awaited_once()
        await self.bot.on_message(fixtures.message('synthetic', guild=None, bot=True))
        self.ai.chat.completions.create.assert_not_awaited()

    async def test_guild_restriction_and_length_limit_remain(self):
        self.bot.allowed_guilds = {21}
        await self.bot.on_message(fixtures.message('<@123> synthetic'))
        self.bot.allowed_guilds = set()
        await self.bot.on_message(fixtures.message('s' * 6001, guild=None))
        self.ai.chat.completions.create.assert_not_awaited()

    async def test_cooldown_shared_with_commands_and_private_delivery(self):
        self.bot.user_cooldown = 30
        self.bot.private_memory_replies = True
        msg = fixtures.message('<@123> synthetic')
        await self.bot.on_message(msg)
        msg.author.send.assert_awaited_once()
        msg.channel.send.assert_not_awaited()
        await self.bot.on_message(fixtures.message('!질문 synthetic', guild=None))
        self.assertEqual(self.ai.chat.completions.create.await_count, 1)
        self.assertEqual(len(self.bot.recent.messages(bank_for(msg, 123))), 2)

    async def test_failed_dm_delivery_does_not_keep_context(self):
        msg = fixtures.message('synthetic', guild=None)
        msg.channel.send.side_effect = [discord.Forbidden(
            NS(status=403, reason='Forbidden'), 'synthetic'), None]
        with self.assertLogs('main', level='WARNING'):
            await self.bot.on_message(msg)
        self.assertEqual(self.bot.recent.messages(bank_for(msg, 123)), [])
