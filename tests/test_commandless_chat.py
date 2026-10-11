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
