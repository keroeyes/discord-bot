"""Run ONLY on the GPU PC; existing server bot keeps handling text commands."""
import asyncio
import io
import logging
import os
from time import monotonic

import discord
from local_images import LocalImages

log = logging.getLogger(__name__)


class ImageWorker(discord.Client):
    def __init__(self, images, owner_id, **kwargs):
        super().__init__(**kwargs)
        self.images = images
        self.owner_id = owner_id
        self.busy = False
        self.next_request = 0

    async def reply(self, target, text):
        await target.send(text, allowed_mentions=discord.AllowedMentions.none())

    async def on_message(self, message):
        if message.author.bot or message.author.id != self.owner_id:
            return
        parts = message.content.strip().split(maxsplit=1)
        if not parts or parts[0] != '!그림':
            return
        # Always DM outputs and notices; never publish a private image fallback.
        target = message.author if message.guild is not None else message.channel
        try:
            if len(parts) < 2 or not parts[1].strip() or len(parts[1]) > 2000:
                await self.reply(target, '사용법: `!그림 설명` (2,000자 이하). 결과는 DM으로 보내요.')
                return
            if self.busy or monotonic() < self.next_request:
                await self.reply(target, '이미지 생성 중이거나 대기시간이 남아 있어요. 잠시 후 다시 요청해주세요.')
                return
            self.busy = True
            self.next_request = monotonic() + 30
            try:
                await self.reply(target, 'PC에서 이미지 1장을 생성합니다.')
                data = await self.images.generate(parts[1])
                file = discord.File(io.BytesIO(data), filename='keroro.png')
                try:
                    await target.send(file=file, allowed_mentions=discord.AllowedMentions.none())
                finally:
                    file.close()
            finally:
                self.busy = False
        except (Exception, asyncio.TimeoutError) as exc:
            log.warning('Image request failed: %s', type(exc).__name__)
            try:
                await self.reply(target, '이미지 생성 또는 DM 전송에 실패했어요. PC의 ComfyUI와 DM 수신 설정을 확인해주세요. 자동 재시도하지 않습니다.')
            except discord.HTTPException:
                pass


def main():
    token = os.getenv('DISCORD_TOKEN', '').strip()
    owner = os.getenv('IMAGE_OWNER_ID', '').strip()
    checkpoint = os.getenv('COMFYUI_CHECKPOINT', '').strip()
    if not token or not owner.isascii() or not owner.isdecimal() or int(owner) <= 0 or not checkpoint:
        raise SystemExit('DISCORD_TOKEN, IMAGE_OWNER_ID, COMFYUI_CHECKPOINT 설정이 필요합니다.')
    images = LocalImages(checkpoint, port=int(os.getenv('COMFYUI_PORT', '8188')))
    intents = discord.Intents.default()
    intents.message_content = True
    worker = ImageWorker(images, int(owner), intents=intents)
    # discord.py INFO logs can contain identifiers; keep this standalone worker quiet.
    logging.basicConfig(level=logging.WARNING)
    worker.run(token, log_handler=None)


if __name__ == '__main__':
    main()
