import asyncio
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import discord
from image_access import ImageAccess, load_access
from image_worker import ImageWorker


class AccessTests(unittest.TestCase):
    def test_access_matrix_and_no_owner_exemption(self):
        a = ImageAccess(allowed_users=[2], allowed_guilds=[10], allow_dm=False)
        for user, guild, expected in [(2,10,True),(1,10,False),(2,11,False),(2,None,False)]:
            self.assertEqual(a.authorized(user,guild),expected)
        self.assertTrue(ImageAccess().authorized(5,None))
        self.assertTrue(ImageAccess().authorized(5,10))
        self.assertTrue(ImageAccess(allowed_guilds=[10]).authorized(5,None))

    def test_cooldown_daily_reset_and_restart(self):
        now = [datetime.fromisoformat('2026-10-10T23:59:40+09:00').timestamp()]
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d)/'usage.sqlite3')
            a = ImageAccess(daily_limit=1,state_path=path,clock=lambda:now[0])
            self.assertEqual(a.reserve(2),('ok',0))
            self.assertEqual(a.reserve(2),('cooldown',30))
            self.assertEqual(a.reserve(3),('ok',0))
            a.db.close()
            a = ImageAccess(daily_limit=1,state_path=path,clock=lambda:now[0])
            now[0] += 21
            self.assertEqual(a.reserve(2),('cooldown',9))
            now[0] += 9
            self.assertEqual(a.reserve(2),('ok',0))
            now[0] += 30
            self.assertEqual(a.reserve(2),('daily',0))
            a.db.close()

    def test_invalid_and_disabled_settings(self):
        for kwargs in [dict(cooldown=-1),dict(cooldown=float('nan')),dict(daily_limit=-1),dict(daily_limit=True),dict(allowed_users=['2']),dict(allowed_guilds=[0]),dict(allow_dm='false')]:
            with self.assertRaises(ValueError): ImageAccess(**kwargs)
        a = ImageAccess(cooldown=0,daily_limit=0)
        for _ in range(25): self.assertEqual(a.reserve(2),('ok',0))

    def test_environment_settings_fail_closed(self):
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ',{'LOCALAPPDATA':d,'IMAGE_ALLOWED_USER_IDS':'2,3','IMAGE_ALLOWED_GUILD_IDS':'10','IMAGE_ALLOW_DM':'false','IMAGE_DAILY_LIMIT':'5','IMAGE_USER_COOLDOWN_SECONDS':'10'},clear=True):
            a=load_access()
            self.assertTrue(a.authorized(2,10))
            self.assertFalse(a.authorized(2,None))
            self.assertEqual(a.daily_limit,5)
            a.db.close()
        with patch.dict('os.environ',{'IMAGE_ALLOW_DM':'typo'},clear=True):
            with self.assertRaises(ValueError): load_access()


class WorkerAccessTests(unittest.IsolatedAsyncioTestCase):
    def make(self,access):
        images=SimpleNamespace(generate=AsyncMock(return_value=b'fixture'))
        converter=SimpleNamespace(prepare=AsyncMock(side_effect=lambda text:text))
        w=ImageWorker(images,1,access=access,prompt_converter=converter,intents=discord.Intents.none())
        return w,images,converter

    def message(self,user=2,guild=10):
        return SimpleNamespace(author=SimpleNamespace(id=user,bot=False,send=AsyncMock()),guild=SimpleNamespace(id=guild) if guild else None,content='!그림 synthetic private',channel=SimpleNamespace(send=AsyncMock()))

    async def test_denial_and_limit_are_distinct_private_and_pre_translation(self):
        w,images,converter=self.make(ImageAccess(allowed_users=[2],daily_limit=1,cooldown=0))
        denied=self.message(1)
        await w.on_message(denied)
        self.assertIn('접근 권한',denied.author.send.await_args.args[0])
        converter.prepare.assert_not_awaited()
        good=self.message(2)
        await w.on_message(good)
        limited=self.message(2)
        await w.on_message(limited)
        self.assertIn('일일',limited.author.send.await_args.args[0])
        self.assertEqual(images.generate.await_count,1)
        for m in (denied,good,limited): m.channel.send.assert_not_awaited()

    async def test_users_have_independent_cooldown_and_private_delivery(self):
        w,images,_=self.make(ImageAccess())
        a,b=self.message(2),self.message(3)
        await w.on_message(a)
        await w.on_message(b)
        self.assertEqual(images.generate.await_count,2)
        for m in (a,b):
            self.assertIn('file',m.author.send.await_args.kwargs)
            m.channel.send.assert_not_awaited()
        await w.on_message(a)
        self.assertIn('사용자별 호출 제한',a.author.send.await_args.args[0])
        self.assertEqual(images.generate.await_count,2)

    async def test_busy_is_atomic_and_does_not_consume_other_users_budget(self):
        w,images,_=self.make(ImageAccess(daily_limit=1,cooldown=0))
        entered,release=asyncio.Event(),asyncio.Event()
        async def generate(prompt):
            entered.set()
            await release.wait()
            return b'fixture'
        images.generate.side_effect=generate
        task=asyncio.create_task(w.on_message(self.message(2)))
        await entered.wait()
        other=self.message(3)
        await w.on_message(other)
        self.assertIn('진행 중',other.author.send.await_args.args[0])
        release.set()
        await task
        await w.on_message(other)
        self.assertEqual(images.generate.await_count,2)
        self.assertFalse(w.busy)

    async def test_failure_consumes_budget_without_prompt_logging(self):
        w,images,_=self.make(ImageAccess(daily_limit=1,cooldown=0))
        images.generate.side_effect=TimeoutError('synthetic private token')
        m=self.message()
        with self.assertLogs('image_worker',level='WARNING') as logs: await w.on_message(m)
        self.assertNotIn('synthetic private',str(logs.output))
        await w.on_message(m)
        self.assertIn('일일',m.author.send.await_args.args[0])
        images.generate.assert_awaited_once()
        m.channel.send.assert_not_awaited()

    async def test_closed_usage_db_blocks_generation(self):
        a=ImageAccess();a.db.close()
        w,images,_=self.make(a)
        with self.assertLogs('image_worker',level='WARNING'): await w.on_message(self.message())
        images.generate.assert_not_awaited()
        self.assertFalse(w.busy)
