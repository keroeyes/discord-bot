"""Optional local OCR, sharing the image worker's GPU lock and access budget."""
import asyncio
import io
import logging
import os
from pathlib import Path
import tempfile

import discord

MAX_BYTES = 8 * 1024 * 1024
MAX_RESULT = 2 * 1024 * 1024
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.pdf'}


def attachment_suffix(attachment):
    suffix = Path(attachment.filename).suffix.lower()
    if suffix not in EXTENSIONS or not 0 < attachment.size <= MAX_BYTES:
        raise ValueError('Unsupported attachment')
    return suffix


class LocalOCR:
    def __init__(self, python, timeout=600):
        self.python = str(Path(python).resolve(strict=True))
        self.timeout = timeout

    async def extract(self, attachment):
        suffix = attachment_suffix(attachment)
        with tempfile.TemporaryDirectory(prefix='keroro-ocr-') as directory:
            root = Path(directory)
            async with asyncio.timeout(60):
                data = await attachment.read()
            if not 0 < len(data) <= MAX_BYTES:
                raise ValueError('Attachment exceeds budget')
            source = root / ('input' + suffix)
            source.write_bytes(data)
            output = root / 'result.txt'
            script = Path(__file__).with_name('scripts') / 'unlimited_ocr_run.py'
            process = await asyncio.create_subprocess_exec(
                self.python, str(script), str(source), str(output),
                env={key: value for key, value in os.environ.items()
                     if not any(part in key.upper() for part in ('TOKEN', 'SECRET', 'API_KEY', 'HINDSIGHT', 'LANGFUSE'))},
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            try:
                async with asyncio.timeout(self.timeout):
                    code = await process.wait()
                if code or not output.is_file() or output.stat().st_size > MAX_RESULT:
                    raise RuntimeError('OCR failed')
                result = output.read_text(encoding='utf-8').strip()
                if not result:
                    raise RuntimeError('OCR empty result')
                return result
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()


async def handle_ocr(worker, message):
    target = message.author
    try:
        guild_id = message.guild.id if message.guild is not None else None
        if not worker.access.authorized(target.id, guild_id):
            await worker.reply(target, '접근 권한이 없어 OCR 요청을 허용하지 않습니다.')
            return
        if worker.ocr is None:
            await worker.reply(target, 'PC에 OCR 모델이 아직 설정되지 않았습니다.')
            return
        attachments = getattr(message, 'attachments', [])
        if len(attachments) != 1:
            await worker.reply(target, '사용법: 사진 또는 PDF 한 개를 첨부하고 `!OCR` (8MB 이하, PDF 최대 10쪽).')
            return
        attachment_suffix(attachments[0])
        if worker.busy:
            await worker.reply(target, 'PC에서 이미지 생성 또는 OCR이 진행 중입니다. 완료 후 다시 요청해주세요.')
            return
        status, wait = worker.access.reserve(target.id)
        if status != 'ok':
            await worker.reply(target, f'요청 제한: {wait}초 후 다시 요청해주세요.' if status == 'cooldown'
                               else '일일 요청 제한에 도달했습니다. 한국시간 자정 이후 다시 요청해주세요.')
            return
        worker.busy = True
        try:
            await worker.reply(target, 'PC에서 문서를 읽습니다. 결과는 DM으로 보내며, OCR 오류는 원문과 대조해주세요.')
            text = await worker.ocr.extract(attachments[0])
            file = discord.File(io.BytesIO(text.encode('utf-8')), filename='ocr-result.txt')
            try:
                await target.send(file=file, allowed_mentions=discord.AllowedMentions.none())
            finally:
                file.close()
        finally:
            worker.busy = False
    except Exception as exc:
        logging.getLogger(__name__).warning('OCR request failed: %s', type(exc).__name__)
        try:
            await worker.reply(target, 'OCR 또는 DM 전송에 실패했습니다. 파일 형식·용량·PDF 쪽수·PC 모델 설정을 확인해주세요. 자동 재시도하지 않습니다.')
        except discord.HTTPException:
            pass
