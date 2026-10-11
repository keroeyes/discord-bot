import unittest
import sys
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from unittest.mock import AsyncMock
import discord
from image_worker import ImageWorker
from image_access import ImageAccess
from local_ocr import LocalOCR, attachment_suffix


class OCRTests(unittest.IsolatedAsyncioTestCase):
    def make(self):
        backend = SimpleNamespace(extract=AsyncMock(return_value='합성 OCR 결과'))
        worker = ImageWorker(SimpleNamespace(generate=AsyncMock()), 1,
                             ocr=backend, intents=discord.Intents.none())
        author = SimpleNamespace(id=1, bot=False, send=AsyncMock())
        attachment = SimpleNamespace(filename='fixture.pdf', size=100, read=AsyncMock())
        message = SimpleNamespace(content='!OCR', author=author, guild=None,
                                  attachments=[attachment], channel=SimpleNamespace(send=AsyncMock()))
        return worker, backend, message

    async def test_extract_delivered_only_to_dm(self):
        worker, backend, message = self.make()
        await worker.on_message(message)
        backend.extract.assert_awaited_once_with(message.attachments[0])
        self.assertIn('file', message.author.send.await_args.kwargs)
        message.channel.send.assert_not_awaited()
        self.assertFalse(worker.busy)
        await worker.on_message(message)
        self.assertEqual(backend.extract.await_count, 1)

    async def test_rejection_before_model(self):
        for mode in ('disabled', 'busy', 'denied', 'missing', 'multiple', 'oversize', 'extension'):
            worker, backend, message = self.make()
            if mode == 'disabled': worker.ocr = None
            if mode == 'busy': worker.busy = True
            if mode == 'denied': worker.access = ImageAccess(allowed_users=[2])
            if mode == 'missing': message.attachments = []
            if mode == 'multiple': message.attachments *= 2
            if mode == 'oversize': message.attachments[0].size = 9 * 1024 * 1024
            if mode == 'extension': message.attachments[0].filename = 'fixture.exe'
            await worker.on_message(message)
            backend.extract.assert_not_awaited()
            message.channel.send.assert_not_awaited()

    async def test_model_failure_private_and_unlocks(self):
        worker, backend, message = self.make()
        backend.extract.side_effect = RuntimeError('PRIVATE DOCUMENT')
        with self.assertLogs('local_ocr', level='WARNING') as logs:
            await worker.on_message(message)
        self.assertNotIn('PRIVATE DOCUMENT', str(logs.output))
        self.assertFalse(worker.busy)
        message.channel.send.assert_not_awaited()

    async def test_dm_block_prevents_processing(self):
        worker, backend, message = self.make()
        message.author.send.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason='blocked'), 'blocked')
        await worker.on_message(message)
        backend.extract.assert_not_awaited()
        self.assertFalse(worker.busy)
        message.channel.send.assert_not_awaited()

    def test_filename_never_used_as_path(self):
        self.assertEqual(attachment_suffix(SimpleNamespace(filename='../../fixture.PDF', size=100)), '.pdf')

    async def test_subprocess_result_and_temp_cleanup(self):
        worker, backend, message = self.make()
        message.attachments[0].read.return_value = b'fixture'
        seen = []

        async def launch(*args, **kwargs):
            seen.append(Path(args[2]).parent)
            Path(args[3]).write_text('합성 결과', encoding='utf-8')
            self.assertEqual(kwargs['stdout'], -3)
            self.assertEqual(kwargs['stderr'], -3)
            self.assertNotIn('DISCORD_TOKEN', kwargs['env'])
            return SimpleNamespace(wait=AsyncMock(return_value=0), returncode=0)

        with patch('local_ocr.asyncio.create_subprocess_exec', side_effect=launch), patch.dict('os.environ', {'DISCORD_TOKEN': 'synthetic'}):
            result = await LocalOCR(sys.executable).extract(message.attachments[0])
        self.assertEqual(result, '합성 결과')
        self.assertFalse(seen[0].exists())

    async def test_timeout_kills_subprocess_and_cleans_up(self):
        import asyncio
        worker, backend, message = self.make()
        message.attachments[0].read.return_value = b'fixture'
        from unittest.mock import Mock
        process = SimpleNamespace(wait=AsyncMock(side_effect=[asyncio.TimeoutError(), 0]),
                                  returncode=None, kill=Mock())
        with patch('local_ocr.asyncio.create_subprocess_exec', AsyncMock(return_value=process)):
            with self.assertRaises(TimeoutError):
                await LocalOCR(sys.executable).extract(message.attachments[0])
        process.kill.assert_called_once()
