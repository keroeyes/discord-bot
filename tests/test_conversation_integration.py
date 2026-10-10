"""Bot SDK-loaded integration tests with synthetic, mocked provider and Discord I/O."""
import asyncio
import unittest
from unittest.mock import AsyncMock
from types import SimpleNamespace as NS
import discord
import test_bot as fixtures
from main import bank_for


class ConversationIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.BotTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await fixtures.BotTests.asyncTearDown(self)

    async def test_two_requests_keep_context_without_retaining_to_memory(self):
        first = fixtures.message('!질문 합성 버킷을 골라줘')
        second = fixtures.message('!질문 그 용량은?')
        await self.bot.on_message(first)
        await self.bot.on_message(second)
        prompt = self.ai.chat.completions.create.call_args.kwargs['messages']
        self.assertEqual(prompt[-3:], [dict(role='user', content='합성 버킷을 골라줘'),
                                     dict(role='assistant', content='18L예요.'),
                                     dict(role='user', content='그 용량은?')])
        self.memory.save.assert_not_awaited()

    async def test_actual_message_routing_isolates_other_scopes(self):
        await self.bot.on_message(fixtures.message('!질문 synthetic-private-context'))
        for scope in (dict(user=11), dict(guild=21), dict(channel=31), dict(guild=None)):
            await self.bot.on_message(fixtures.message('!질문 다른 질문', **scope))
            prompt = self.ai.chat.completions.create.call_args.kwargs['messages']
            self.assertNotIn('synthetic-private-context', str(prompt))

    async def test_failed_private_partial_delivery_is_not_retained(self):
        self.bot.private_memory_replies = True
        self.ai.chat.completions.create.return_value.choices[0].message.content = 'x' * 2000
        msg = fixtures.message('!질문 synthetic')
        msg.author.send.side_effect = [None, discord.Forbidden(NS(status=403, reason='Forbidden'), 'synthetic')]
        await self.bot.on_message(msg)
        self.assertEqual(self.bot.recent.messages(bank_for(msg, 123)), [])
        self.assertNotIn('x' * 100, msg.channel.send.call_args.args[0])

    async def test_cancelled_generation_is_not_retained(self):
        self.ai.chat.completions.create.side_effect = asyncio.CancelledError
        msg = fixtures.message('!질문 synthetic')
        with self.assertRaises(asyncio.CancelledError):
            await self.bot.on_message(msg)
        self.assertEqual(self.bot.recent.messages(bank_for(msg, 123)), [])
        msg.channel.send.assert_not_awaited()

    async def test_subscription_followup_retains_wire_contract_and_budget(self):
        self.bot.answer_provider = 'subscription'
        self.bot.subscription = NS(answer=AsyncMock(return_value='합성 20L입니다'))
        await self.bot.on_message(fixtures.message('!질문 합성 버킷'))
        await self.bot.on_message(fixtures.message('!질문 그 용량은?'))
        query, facts = self.bot.subscription.answer.call_args.args
        self.assertIn('합성 버킷', query)
        self.assertIn('합성 20L입니다', query)
        self.assertTrue(query.endswith('그 용량은?'))
        self.assertLessEqual(len(query), 6000)
        self.assertEqual(facts, ['버킷은 18L'])

    async def test_existing_subscription_extension_accepts_context_unchanged(self):
        import os
        from unittest.mock import patch
        import test_subscription_extension as extension_fixtures
        from conversation import contextual_query
        from subscription import SearchEvidence
        extension = extension_fixtures.load_extension()
        endpoint = extension.SubscriptionExtension().get_router(None).endpoints['/answers']
        history = [dict(role='user', content='합성 버킷'),
                   dict(role='assistant', content='합성 20L입니다')]
        query = contextual_query('그 용량은?', history)
        body = extension.AnswerRequest(query=query, facts=[])
        provider = NS(call=AsyncMock(return_value=NS(content='합성 답변')),
                      cleanup=AsyncMock(), evidence=SearchEvidence())
        with patch.object(extension, 'SearchModel', return_value=provider) as model, patch.dict(
                os.environ, HINDSIGHT_API_LLM_CODEX_HOME='synthetic-home'):
            result = await endpoint(body)
        self.assertEqual(result['version'], 'subscription-search-v3')
        self.assertEqual(provider.call.call_args.kwargs['messages'][-1],
                         dict(role='user', content=query))
        self.assertEqual(model.call_args.kwargs['extra_body'], {'tools': [{'type': 'web_search'}]})
        # Maximum-length current questions still fit the unchanged server schema.
        long_query = contextual_query('q' * 6000, history)
        self.assertEqual(extension.AnswerRequest(query=long_query, facts=[]).query, 'q' * 6000)
