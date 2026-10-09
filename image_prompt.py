"""Local Korean-to-English translation; no prompt expansion or hosted inference."""
import asyncio
import re
import threading

MODEL = 'Helsinki-NLP/opus-mt-ko-en'
REVISION = 'e42d1f41b66194e6d10512f8a27bebc1f4f5097e'
KOREAN = re.compile('[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3]')


class PromptTranslationError(RuntimeError):
    pass


class ImagePrompt:
    def __init__(self):
        self.tokenizer = None
        self.model = None
        self.lock = threading.Lock()

    def load(self, download=False):
        # Download only in the explicit preparation command, never on requests.
        from transformers import MarianMTModel, MarianTokenizer
        options = dict(revision=REVISION, local_files_only=not download)
        self.tokenizer = MarianTokenizer.from_pretrained(MODEL, **options)
        self.model = MarianMTModel.from_pretrained(MODEL, **options).to('cpu').eval()

    def translate(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise PromptTranslationError('Invalid description')
        if not KOREAN.search(text):
            return text.strip()
        try:
            with self.lock:
                if self.model is None:
                    self.load()
                import torch
                encoded = self.tokenizer(text, return_tensors='pt', truncation=False)
                if encoded['input_ids'].shape[-1] > 512:
                    raise PromptTranslationError('Description too long')
                with torch.inference_mode():
                    result = self.model.generate(**encoded, do_sample=False, num_beams=4,
                                                 max_new_tokens=256, renormalize_logits=True)
                # Refuse capped output instead of silently losing the rest of a request.
                if int(result[0][-1]) != self.model.config.eos_token_id:
                    raise PromptTranslationError('Translation incomplete')
                translated = self.tokenizer.decode(result[0], skip_special_tokens=True).strip()
                if not translated or len(translated) > 2000 or KOREAN.search(translated):
                    raise PromptTranslationError('Invalid translation')
                return translated
        except PromptTranslationError:
            raise
        except Exception:
            raise PromptTranslationError('Local translation unavailable') from None

    async def prepare(self, text):
        return await asyncio.to_thread(self.translate, text)


if __name__ == '__main__':
    import sys
    try:
        converter = ImagePrompt()
        converter.load(download=True)
        print('Translation model downloaded. Synthetic translation check:')
        print(converter.translate('벚꽃길 위의 흰색 자동차'))
    except Exception as exc:
        print(f'Translation preparation failed ({type(exc).__name__}).')
        sys.exit(1)
