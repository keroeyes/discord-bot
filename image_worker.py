"""Run ONLY on the GPU PC; existing server bot keeps handling text commands."""
import asyncio
import io
import logging
import os

import discord
from image_access import ImageAccess, load_access
from local_images import LocalImages
from image_prompt import ImagePrompt, PromptTranslationError

log = logging.getLogger(__name__)


class ImageWorker(discord.Client):
    def __init__(self, images, owner_id, prompt_converter=None, access=None, **kwargs):
        super().__init__(**kwargs)
        self.images = images
        self.owner_id = owner_id
        self.prompt_converter = prompt_converter or ImagePrompt()
        self.busy = False
        self.access = access if access is not None else ImageAccess()

    async def reply(self, target, text):
        await target.send(text, allowed_mentions=discord.AllowedMentions.none())

    async def on_message(self, message):
        if message.author.bot:
            return
        parts = message.content.strip().split(maxsplit=1)
        if not parts or parts[0] != '!그림':
            return
        # Always DM outputs and notices; never publish a private image fallback.
        target = message.author
        try:
            guild_id = message.guild.id if message.guild is not None else None
            if not self.access.authorized(message.author.id, guild_id):
                await self.reply(target, '접근 권한이 없어 이미지 요청을 허용하지 않습니다.')
                return
            if len(parts) < 2 or not parts[1].strip() or len(parts[1]) > 2000:
                await self.reply(target, '사용법: `!그림 설명` (2,000자 이하). 결과는 DM으로 보내요.')
                return
            if self.busy:
                await self.reply(target, '다른 이미지 생성이 진행 중입니다. 완료 후 다시 요청해주세요.')
                return
            status, wait = self.access.reserve(message.author.id)
            if status == 'cooldown':
                await self.reply(target, f'사용자별 호출 제한: {wait}초 후 다시 요청해주세요.')
                return
            if status == 'daily':
                await self.reply(target, '사용자별 일일 생성량 제한에 도달했습니다. 한국시간 자정 이후 다시 요청해주세요.')
                return
            self.busy = True
            try:
                await self.reply(target, 'PC에서 이미지 1장을 생성합니다.')
                try:
                    prompt = await self.prompt_converter.prepare(parts[1])
                except PromptTranslationError:
                    await self.reply(target, '한국어 설명을 번역하지 못해 생성을 중단했어요. PC에서 번역 모델 준비를 확인하거나 짧은 영어 설명으로 요청해주세요.')
                    return
                if prompt != parts[1].strip():
                    backend = getattr(self.prompt_converter, 'backend', 'unknown')
                    await self.reply(target, f'모델에 전달하는 영어 설명 (번역기: {backend}):\n' + prompt)
                data = await self.images.generate(prompt)
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
    try:
        access = load_access()
    except Exception:
        raise SystemExit('이미지 접근 설정 또는 사용량 DB를 확인해주세요.') from None
    worker = ImageWorker(images, int(owner), access=access, intents=intents)
    # discord.py INFO logs can contain identifiers; keep this standalone worker quiet.
    logging.basicConfig(level=logging.WARNING)
    worker.run(token, log_handler=None)


if __name__ == '__main__':
    main()
