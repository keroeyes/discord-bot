import json
import unittest
from unittest.mock import Mock, patch
from contextlib import nullcontext
from image_prompt import ImagePrompt, PromptTranslationError, OLLAMA_URL
from scripts.setup_image_translation import configure

class OllamaTests(unittest.TestCase):
    def run_response(self, items, done=True, reason='stop'):
        response = Mock()
        response.read.return_value = json.dumps({'done': done, 'done_reason': reason,
            'response': json.dumps({'translations': items})}).encode()
        opener = Mock()
        opener.open.return_value = nullcontext(response)
        with patch('image_prompt.build_opener', return_value=opener):
            result = ImagePrompt(backend='ollama').translate('흰색 자동차, 실사 사진')
        return result, opener

    def test_items_and_request_options(self):
        result, opener = self.run_response(['a white car', 'realistic photograph'])
        self.assertEqual(result, 'a white car, realistic photograph')
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, OLLAMA_URL)
        payload = json.loads(request.data)
        self.assertEqual(json.loads(payload['prompt'])['items'], ['흰색 자동차', '실사 사진'])
        self.assertEqual(payload['keep_alive'], 0)
        self.assertFalse(payload['think'])
        self.assertFalse(payload['stream'])
        self.assertEqual(payload['options']['temperature'], 0)
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 120)

    def test_bad_or_incomplete_items(self):
        for items, done, reason in [(['car'], True, 'stop'), (['car', '사진'], True, 'stop'),
            (['car', ''], True, 'stop'), (['car', '<think>photo'], True, 'stop'),
            (['car', 2], True, 'stop'), (['car', 'photo'], False, 'stop'),
            (['car', 'photo'], True, 'length')]:
            with self.subTest(items=items, done=done, reason=reason):
                with self.assertRaises(PromptTranslationError):
                    self.run_response(items, done, reason)

    def test_failure_without_marian_fallback_or_raw_error(self):
        converter = ImagePrompt(backend='ollama')
        opener = Mock()
        opener.open.side_effect = RuntimeError('private fixture')
        with patch('image_prompt.build_opener', return_value=opener), patch.object(converter, 'load') as load:
            with self.assertRaises(PromptTranslationError) as error:
                converter.translate('합성 테스트')
        load.assert_not_called()
        self.assertNotIn('private', str(error.exception))

    def test_english_bypass(self):
        with patch('image_prompt.build_opener', side_effect=AssertionError):
            self.assertEqual(ImagePrompt(backend='ollama').translate('white car'), 'white car')

    def test_too_many_items(self):
        with patch('image_prompt.build_opener') as opener:
            with self.assertRaises(PromptTranslationError):
                ImagePrompt(backend='ollama').translate(','.join(['고양이'] * 17))
        opener.assert_not_called()

    def test_setup_failure_keeps_old_configuration(self):
        with patch('scripts.setup_image_translation.ImagePrompt') as converter, patch('scripts.setup_image_translation.CONFIG') as config:
            converter.return_value.translate.return_value = 'A car.'
            with self.assertRaises(RuntimeError):
                configure()
        config.with_suffix.assert_not_called()

    def test_invalid_config_is_rejected(self):
        with patch('image_prompt.CONFIG') as config:
            config.exists.return_value = True
            config.read_text.return_value = '{"backend":"remote"}'
            with self.assertRaises(PromptTranslationError):
                ImagePrompt()

    def test_setup_accepts_equivalent_followed_by_relation(self):
        outputs = [
            'White car on a road lined with cherry blossoms, realistic photograph',
            'Two cats holding a red umbrella, watercolor',
            'Black car followed by blue bicycle, Night, Animation painting']
        with patch('scripts.setup_image_translation.ImagePrompt') as converter, patch('scripts.setup_image_translation.CONFIG') as config:
            converter.return_value.translate.side_effect = outputs
            configure()
        config.with_suffix.return_value.replace.assert_called_once_with(config)

    def test_setup_rejects_reversed_spatial_direction(self):
        outputs = [
            'White car on a road lined with cherry blossoms, realistic photograph',
            'Two cats holding a red umbrella, watercolor',
            'Black car behind blue bicycle, night, anime']
        with patch('scripts.setup_image_translation.ImagePrompt') as converter, patch('scripts.setup_image_translation.CONFIG') as config:
            converter.return_value.translate.side_effect = outputs
            with self.assertRaises(RuntimeError):
                configure()
        config.with_suffix.assert_not_called()

    def test_probe_accepts_direction_and_rejects_missing_count_or_color(self):
        from scripts.image_translation_checks import issues
        self.assertEqual(issues(2, 'Blue bicycle behind a black car, night, anime'), [])
        self.assertEqual(issues(2, 'Black car in front of a blue bicycle, night, anime'), [])
        self.assertIn('two', issues(1, 'Cats holding a red umbrella, watercolor'))
        self.assertIn('red', issues(1, 'Two cats holding an umbrella, watercolor'))
