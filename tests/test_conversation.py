"""Standard-library offline tests; production method bodies with SDK boundaries mocked.
This is not a Discord/OpenAI/Hindsight SDK integration test.
"""
import ast
from contextlib import nullcontext
import hashlib
import json
import logging
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock
from conversation import RecentConversation, contextual_query


class RecentTests(unittest.TestCase):
    def test_isolated_snapshots_cannot_mutate_store(self):
        store = RecentConversation()
        store.add('one', '버킷을 골랐어', '20L 버킷입니다')
        self.assertEqual(store.messages('two'), [])
        copy = store.messages('one')
        copy[0]['content'] = 'changed'
        self.assertEqual(store.messages('one')[0]['content'], '버킷을 골랐어')
        store.clear('two')
        self.assertEqual(len(store.messages('one')), 2)
        store.clear('one')
        self.assertEqual(store.messages('one'), [])

    def test_turn_and_character_limits_keep_complete_pairs(self):
        store = RecentConversation(max_turns=2, max_chars=8)
        for q in ('a', 'b', 'c'):
            store.add('one', q, '123')
        self.assertEqual([m['content'] for m in store.messages('one')], ['b', '123', 'c', '123'])
        store.add('one', 'oversized', '123')
        store.add('one', 'query', '')
        self.assertEqual(len(store.messages('one')), 4)

    def test_ttl_expires_each_turn_even_in_active_scope(self):
        now = [0]
        store = RecentConversation(ttl_seconds=10, clock=lambda: now[0])
        store.add('one', 'old', 'answer')
        now[0] = 9
        store.add('one', 'new', 'answer')
        now[0] = 10
        self.assertEqual(store.messages('one')[0]['content'], 'new')
        now[0] = 19
        self.assertEqual(store.messages('one'), [])
        self.assertEqual(len(store._scopes), 0)

    def test_scope_limit_evicts_least_recently_updated(self):
        store = RecentConversation(max_scopes=2)
        for key in ('a', 'b', 'a', 'c'):
            store.add(key, 'q', 'a')
        self.assertEqual(store.messages('b'), [])
        self.assertEqual(len(store._scopes), 2)

    def test_provider_query_preserves_current_and_json_budget(self):
        store = RecentConversation()
        store.add('a', 'quoted "query"\n', 'answer')
        history = store.messages('a')
        enriched = contextual_query('그중 첫 번째는?', history)
        self.assertIn('quoted \\"query\\"', enriched)
        self.assertTrue(enriched.endswith('현재 사용자 질문:\n그중 첫 번째는?'))
        self.assertLessEqual(len(enriched), 6000)
        self.assertEqual(contextual_query('q' * 6000, history), 'q' * 6000)
        self.assertEqual(contextual_query('q', []), 'q')
        long_history = history * 200
        self.assertLessEqual(len(contextual_query('q', long_history)), 6000)


# Load exact production definitions without importing unavailable SDK packages.
# All external methods are AsyncMocks; no network/model/Discord call can occur.
def handler_namespace():
    source = Path(__file__).resolve().parents[1] / 'main.py'
    tree = ast.parse(source.read_text())
    names = {'Bot', 'bank_for', 'memory_facts_json', 'send_text'}
    selected = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    class HTTPException(Exception):
        pass
    namespace = dict(discord=NS(Client=object, HTTPException=HTTPException,
                               AllowedMentions=NS(none=lambda: None)),
                     hashlib=hashlib, json=json, RecentConversation=RecentConversation,
                     contextual_query=contextual_query, stage=lambda *args: nullcontext(),
                     record_memory=lambda *args: None, mark_delivery_failed=lambda: None,
                     log=logging.getLogger('offline-conversation-test'))
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace


class HandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ns = handler_namespace()
        self.bot = self.ns['Bot'].__new__(self.ns['Bot'])
        self.bot.recent = RecentConversation()
        self.bot.answer_provider = 'openai'
        self.bot.private_memory_replies = False
        self.bot.model = 'mock-only'
        self.bot.memory = NS(enabled=False, reflect=AsyncMock(return_value='20L입니다'),
                             delete=AsyncMock(), recall=AsyncMock(return_value=[]))
        self.bot.subscription = NS(answer=AsyncMock(return_value='20L입니다'))
        self.create = AsyncMock(return_value=NS(choices=[NS(message=NS(content='20L입니다'))]))
        self.bot.ai = NS(chat=NS(completions=NS(create=self.create)))
        self.msg = NS(guild=NS(id=20), channel=NS(id=30, send=AsyncMock()),
                      author=NS(id=10, send=AsyncMock()), id=99)
        self.bank = self.ns['bank_for'](self.msg, 123)

    async def test_followup_uses_successful_turn_in_actual_openai_path(self):
        await self.bot.handle(self.msg, '!질문', '어떤 버킷?', self.bank)
        await self.bot.handle(self.msg, '!질문', '그 용량은?', self.bank)
        prompt = self.create.call_args.kwargs['messages']
        self.assertEqual(prompt[-3:], [dict(role='user', content='어떤 버킷?'),
                                     dict(role='assistant', content='20L입니다'),
                                     dict(role='user', content='그 용량은?')])
        self.bot.memory.recall.assert_not_awaited()

    async def test_subscription_and_reflect_get_context_without_protocol_change(self):
        for provider in ('subscription', 'hindsight'):
            self.bot.answer_provider = provider
            self.bot.recent.clear(self.bank)
            await self.bot.handle(self.msg, '!질문', '어떤 버킷?', self.bank)
            await self.bot.handle(self.msg, '!질문', '그 용량은?', self.bank)
            call = (self.bot.subscription.answer.call_args if provider == 'subscription'
                    else self.bot.memory.reflect.call_args)
            query = call.args[0 if provider == 'subscription' else 1]
            self.assertIn('어떤 버킷?', query)
            self.assertIn('20L입니다', query)
            self.assertTrue(query.endswith('그 용량은?'))
            self.assertLessEqual(len(query), 6000)

    async def test_generation_empty_and_delivery_failures_do_not_store_turns(self):
        self.create.side_effect = RuntimeError('synthetic failure')
        with self.assertRaises(RuntimeError):
            await self.bot.handle(self.msg, '!질문', 'q', self.bank)
        self.assertEqual(self.bot.recent.messages(self.bank), [])
        self.create.side_effect = None
        self.create.return_value.choices[0].message.content = ''
        with self.assertRaises(ValueError):
            await self.bot.handle(self.msg, '!질문', 'q', self.bank)
        self.assertEqual(self.bot.recent.messages(self.bank), [])
        self.create.return_value.choices[0].message.content = 'a' * 2000
        self.msg.channel.send.side_effect = [None, RuntimeError('second chunk failed')]
        with self.assertRaises(RuntimeError):
            await self.bot.handle(self.msg, '!질문', 'q', self.bank)
        self.assertEqual(self.bot.recent.messages(self.bank), [])

    async def test_private_delivery_failure_never_stores_or_publicly_exposes_answer(self):
        self.bot.private_memory_replies = True
        self.msg.author.send.side_effect = self.ns['discord'].HTTPException('synthetic')
        await self.bot.handle(self.msg, '!질문', 'q', self.bank)
        self.assertEqual(self.bot.recent.messages(self.bank), [])
        self.assertNotIn('20L', self.msg.channel.send.call_args.args[0])

    async def test_scope_separates_bot_user_guild_channel_and_dm(self):
        await self.bot.handle(self.msg, '!질문', 'private context', self.bank)
        for attr, value in [('author', NS(id=11)), ('guild', NS(id=21)),
                            ('channel', NS(id=31)), ('guild', None)]:
            msg = NS(**vars(self.msg))
            setattr(msg, attr, value)
            bank = self.ns['bank_for'](msg, 123)
            self.assertNotEqual(bank, self.bank)
            self.assertEqual(self.bot.recent.messages(bank), [])
        self.assertEqual(self.bot.recent.messages(self.ns['bank_for'](self.msg, 124)), [])

    async def test_explicit_delete_resets_only_after_success(self):
        self.bot.recent.add(self.bank, 'q', 'a')
        self.bot.memory.delete.side_effect = RuntimeError('failed')
        with self.assertRaises(RuntimeError):
            await self.bot.handle(self.msg, '!기억삭제', '확인', self.bank)
        self.assertEqual(len(self.bot.recent.messages(self.bank)), 2)
        self.bot.memory.delete.side_effect = None
        await self.bot.handle(self.msg, '!기억삭제', '확인', self.bank)
        self.assertEqual(self.bot.recent.messages(self.bank), [])
