"""Synthetic overload and status checks; no live providers or Discord sends."""
import asyncio
import os
import unittest
from unittest.mock import patch

import test_bot as fixtures
from main import deployment_revision


class AdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.BotTests.asyncSetUp(self)

    async def asyncTearDown(self):
        await fixtures.BotTests.asyncTearDown(self)

    async def test_saturation_rejects_without_provider_call_or_cooldown(self):
        release = asyncio.Event()
        started = asyncio.Event()
        running = 0

        async def recall(*args):
            nonlocal running
            running += 1
            if running == 4:
                started.set()
            await release.wait()
            return []

        self.memory.recall.side_effect = recall
        self.bot.user_cooldown = 30
        tasks = [asyncio.create_task(self.bot.on_message(
            fixtures.message('!질문 synthetic', user=100 + i))) for i in range(4)]
        try:
            await asyncio.wait_for(started.wait(), 1)
            excess = fixtures.message('!질문 synthetic', user=200)
            await asyncio.wait_for(self.bot.on_message(excess), 1)
            self.assertIn('현재 요청이 많아', excess.channel.send.call_args.args[0])
            self.assertNotIn(200, self.bot.cooldown_until)
            self.assertEqual(self.memory.recall.await_count, 4)
            self.ai.chat.completions.create.assert_not_awaited()
            status = fixtures.message('!봇상태', user=300)
            await asyncio.wait_for(self.bot.on_message(status), 1)
            self.assertIn('현재 처리: 4/4', status.channel.send.call_args.args[0])
        finally:
            release.set()
            await asyncio.gather(*tasks)
        self.assertEqual(self.bot.active_requests, 0)
        await self.bot.on_message(fixtures.message('!질문 synthetic', user=200))
        self.assertEqual(self.ai.chat.completions.create.await_count, 5)

    async def test_cancelled_request_releases_slot_and_scope(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def recall(*args):
            started.set()
            await release.wait()
            return []

        self.memory.recall.side_effect = recall
        task = asyncio.create_task(self.bot.on_message(fixtures.message('!질문 synthetic')))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.bot.active_requests, 0)
        self.memory.recall.side_effect = None
        self.memory.recall.return_value = []
        await asyncio.wait_for(self.bot.on_message(fixtures.message('!질문 retry')), 1)
        self.ai.chat.completions.create.assert_awaited_once()

    async def test_generation_error_releases_slot(self):
        self.ai.chat.completions.create.side_effect = RuntimeError('synthetic-secret')
        await self.bot.on_message(fixtures.message('!질문 synthetic'))
        self.assertEqual(self.bot.active_requests, 0)
        self.assertFalse(self.bot.capacity.locked())

    async def test_status_displays_commit_and_configuration_without_service_calls(self):
        self.bot.private_memory_replies = True
        with patch.dict(os.environ, RAILWAY_GIT_COMMIT_SHA='a' * 40):
            status = fixtures.message('!봇상태')
            await self.bot.on_message(status)
        text = status.channel.send.call_args.args[0]
        for expected in ['배포 커밋: ' + 'a' * 12, '현재 처리: 0/4', '답변 전송: DM',
                         '정상 동작을 보증하지 않습니다']:
            self.assertIn(expected, text)
        self.assertNotIn('봇 버전: subscription-search-v3', text)
        self.memory.recall.assert_not_awaited()
        self.ai.chat.completions.create.assert_not_awaited()

    def test_untrusted_revision_is_never_echoed(self):
        for value in ['', 'secret-token', 'b' * 39, 'c' * 41, 'd' * 40 + '\nprivate']:
            with self.subTest(value=len(value)), patch.dict(os.environ, RAILWAY_GIT_COMMIT_SHA=value):
                self.assertEqual(deployment_revision(), '미확인')
