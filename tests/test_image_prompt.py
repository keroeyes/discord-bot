import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import discord
from image_prompt import ImagePrompt, PromptTranslationError
from image_worker import ImageWorker


class PromptTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, decoded='a white car', length=12, end=0):
        converter = ImagePrompt()
        converter.tokenizer = Mock(return_value={'input_ids': SimpleNamespace(shape=(1, length))})
        converter.tokenizer.decode.return_value = decoded
        converter.model = SimpleNamespace(config=SimpleNamespace(eos_token_id=0),
                                          generate=Mock(return_value=[[1, end]]))
        return converter

    def test_deterministic_translation_without_added_style(self):
        converter = self.fixture()
        with patch.dict('sys.modules', torch=SimpleNamespace(inference_mode=nullcontext)):
            self.assertEqual(converter.translate('흰색 자동차'), 'a white car')
        self.assertFalse(converter.model.generate.call_args.kwargs['do_sample'])

    def test_bad_or_incomplete_translation_is_rejected(self):
        for decoded, end in [('', 0), ('고양이', 0), ('a car', 5), ('a' * 2001, 0)]:
            converter = self.fixture(decoded=decoded, end=end)
            with patch.dict('sys.modules', torch=SimpleNamespace(inference_mode=nullcontext)):
                with self.assertRaises(PromptTranslationError):
                    converter.translate('합성 테스트')

    def test_long_request_is_rejected_without_truncation(self):
        converter = self.fixture(length=513)
        with patch.dict('sys.modules', torch=SimpleNamespace(inference_mode=nullcontext)):
            with self.assertRaises(PromptTranslationError):
                converter.translate('합성 테스트')
        converter.model.generate.assert_not_called()

    async def test_english_does_not_load_translation_model(self):
        converter = ImagePrompt()
        with patch.object(converter, 'load', side_effect=AssertionError('unexpected load')):
            self.assertEqual(await converter.prepare(' a white car '), 'a white car')

    async def test_missing_model_fails_without_raw_input(self):
        converter = ImagePrompt()
        with patch.object(converter, 'load', side_effect=RuntimeError('private synthetic detail')):
            with self.assertRaises(PromptTranslationError) as error:
                await converter.prepare('합성 테스트')
        self.assertNotIn('private', str(error.exception))

    async def test_translation_is_forwarded_and_preview_is_private(self):
        converter = SimpleNamespace(prepare=AsyncMock(return_value='a white car on a cherry blossom road'))
        images = SimpleNamespace(generate=AsyncMock(return_value=b'fixture'))
        worker = ImageWorker(images, 1, prompt_converter=converter, intents=discord.Intents.none())
        author = SimpleNamespace(id=2, bot=False, send=AsyncMock())
        message = SimpleNamespace(author=author, content='!그림 벚꽃길 위의 흰색 자동차',
                                  guild=object(), channel=SimpleNamespace(send=AsyncMock()))
        await worker.on_message(message)
        converter.prepare.assert_awaited_once_with('벚꽃길 위의 흰색 자동차')
        images.generate.assert_awaited_once_with('a white car on a cherry blossom road')
        message.channel.send.assert_not_awaited()
        self.assertEqual(author.send.await_count, 3)
        self.assertFalse(worker.busy)

    async def test_translation_failure_never_generates_untranslated_image(self):
        converter = SimpleNamespace(prepare=AsyncMock(side_effect=PromptTranslationError()))
        images = SimpleNamespace(generate=AsyncMock())
        worker = ImageWorker(images, 1, prompt_converter=converter, intents=discord.Intents.none())
        author = SimpleNamespace(id=2, bot=False, send=AsyncMock())
        message = SimpleNamespace(author=author, content='!그림 고양이', guild=None,
                                  channel=SimpleNamespace(send=AsyncMock()))
        await worker.on_message(message)
        images.generate.assert_not_awaited()
        self.assertFalse(worker.busy)
        self.assertIn('중단', message.channel.send.await_args.args[0])
