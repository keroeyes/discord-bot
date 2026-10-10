import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import Mock, patch
from contextlib import nullcontext
import json
from image_prompt import ImagePrompt
from aiohttp import web
import discord
from image_worker import ImageWorker
from local_images import LocalImages, workflow


class LocalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mode = 'ok'
        self.submitted = []
        app = web.Application()
        app.router.add_post('/prompt', self.submit)
        app.router.add_get('/history/{id}', self.history)
        app.router.add_get('/view', self.view)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await self.site.start()
        port = self.site._server.sockets[0].getsockname()[1]
        self.client = LocalImages('test.safetensors', port, timeout=0.2)

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def submit(self, request):
        self.submitted.append(await request.json())
        if self.mode == 'reject':
            return web.json_response({'error': 'bad workflow'})
        return web.json_response({'prompt_id': 'abcd-1234'})

    async def history(self, request):
        if self.mode == 'timeout':
            return web.json_response({})
        if self.mode == 'error':
            return web.json_response({'abcd-1234': {'status': {'status_str': 'error'}}})
        return web.json_response({'abcd-1234': {'outputs': {'7': {'images': [{'filename': 'test.png', 'type': 'output', 'subfolder': ''}]}}}})

    async def view(self, request):
        return web.Response(body=b'invalid' if self.mode == 'invalid' else b'\x89PNG\r\n\x1a\nfixture')

    async def test_http_generation(self):
        self.assertTrue((await self.client.generate('synthetic car')).startswith(b'\x89PNG'))
        graph = self.submitted[0]['prompt']
        self.assertEqual(graph['2']['inputs']['text'], 'synthetic car')
        self.assertEqual(graph['4']['inputs']['batch_size'], 1)

    async def test_korean_ollama_worker_to_http_positive_path(self):
        english = 'blue bicycle behind a black car, night, anime'
        response = Mock()
        response.read.return_value = json.dumps({'done': True, 'done_reason': 'stop',
            'response': json.dumps({'translations': ['blue bicycle behind a black car', 'night', 'anime']})}).encode()
        opener = Mock()
        opener.open.return_value = nullcontext(response)
        worker = ImageWorker(self.client, 1, prompt_converter=ImagePrompt(backend='ollama'), intents=discord.Intents.none())
        author = SimpleNamespace(id=2, bot=False, send=AsyncMock())
        message = SimpleNamespace(author=author, content='!그림 검은 자동차 뒤에 파란 자전거, 밤, 애니메이션 그림',
            guild=SimpleNamespace(id=10), channel=SimpleNamespace(send=AsyncMock()))
        with patch('image_prompt.build_opener', return_value=opener):
            await worker.on_message(message)
        graph = self.submitted[0]['prompt']
        positive = graph['5']['inputs']['positive'][0]
        self.assertEqual(graph[positive]['inputs']['text'], english)
        self.assertEqual(graph['3']['inputs']['text'], 'blurry, low quality, watermark')
        self.assertIn(english, author.send.await_args_list[1].args[0])
        self.assertIn('번역기: ollama', author.send.await_args_list[1].args[0])
        message.channel.send.assert_not_awaited()
        self.assertIn('file', author.send.await_args.kwargs)

    async def test_fixed_seed_for_synthetic_comparison(self):
        await self.client.generate('synthetic', seed=12345)
        self.assertEqual(self.submitted[0]['prompt']['5']['inputs']['seed'], 12345)
        for seed in [-1, 2 ** 63, True, '12345']:
            with self.assertRaises(ValueError):
                await self.client.generate('synthetic', seed=seed)

    async def test_failure_and_no_retry(self):
        for mode, exception in [('reject', RuntimeError), ('error', RuntimeError), ('invalid', ValueError), ('timeout', TimeoutError)]:
            self.mode = mode
            self.submitted.clear()
            with self.assertRaises(exception):
                await self.client.generate('synthetic')
            self.assertEqual(len(self.submitted), 1)

    def test_validation(self):
        for prompt, checkpoint in [('', 'test'), ('a' * 2001, 'test'), ('valid', '../test')]:
            with self.assertRaises(ValueError):
                workflow(prompt, checkpoint, 1)


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def make(self, owner=1, content='!그림 synthetic', guild=True):
        images = SimpleNamespace(generate=AsyncMock(return_value=b'fixture'))
        worker = ImageWorker(images, 1, intents=discord.Intents.none())
        author = SimpleNamespace(id=owner, bot=False, send=AsyncMock())
        message = SimpleNamespace(author=author, content=content, guild=SimpleNamespace(id=10) if guild else None, channel=SimpleNamespace(send=AsyncMock()))
        return worker, images, message

    async def test_command_filter(self):
        for owner, text in [(1, '!질문 synthetic'), (2, '!질문 synthetic')]:
            worker, images, message = self.make(owner, text)
            await worker.on_message(message)
            images.generate.assert_not_awaited()

    async def test_dm_delivery_and_cooldown(self):
        worker, images, message = self.make()
        await worker.on_message(message)
        self.assertEqual(message.author.send.await_count, 2)
        self.assertIn('file', message.author.send.await_args.kwargs)
        message.channel.send.assert_not_awaited()
        self.assertFalse(worker.busy)
        await worker.on_message(message)
        self.assertEqual(images.generate.await_count, 1)

    async def test_failed_delivery_never_public(self):
        worker, images, message = self.make()
        message.author.send.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason='blocked'), 'blocked')
        await worker.on_message(message)
        images.generate.assert_not_awaited()
        message.channel.send.assert_not_awaited()
        self.assertFalse(worker.busy)

    async def test_generation_failure_releases_busy(self):
        worker, images, message = self.make()
        images.generate.side_effect = RuntimeError('private synthetic input')
        with self.assertLogs('image_worker', level='WARNING') as logs:
            await worker.on_message(message)
        self.assertNotIn('private synthetic input', str(logs.output))
        self.assertFalse(worker.busy)
        message.channel.send.assert_not_awaited()

    async def test_other_user_receives_image_in_own_dm(self):
        worker, images, message = self.make(owner=2)
        await worker.on_message(message)
        images.generate.assert_awaited_once_with('synthetic')
        self.assertIn('file', message.author.send.await_args.kwargs)
        message.channel.send.assert_not_awaited()

    async def test_bot_requests_are_ignored(self):
        worker, images, message = self.make(owner=2)
        message.author.bot = True
        await worker.on_message(message)
        images.generate.assert_not_awaited()
