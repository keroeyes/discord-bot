"""Activate local Ollama translation only after synthetic content checks."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from image_prompt import CONFIG, ImagePrompt
from scripts.image_translation_checks import CASES, issues


def configure():
    converter = ImagePrompt(backend='ollama')
    for index, (source, _) in enumerate(CASES):
        output = converter.translate(source)
        print(f'Synthetic check {index + 1}: {output}')
        if issues(index, output):
            raise RuntimeError('Synthetic content check failed')
    # Config contains only backend choice, no prompts, credentials or identifiers.
    temporary = CONFIG.with_suffix('.tmp')
    temporary.write_text('{"backend": "ollama"}\n', encoding='utf-8')
    temporary.replace(CONFIG)
    print('Ollama translation enabled. Restart the image worker.')


if __name__ == '__main__':
    try:
        configure()
    except Exception as exc:
        print(f'Setup failed ({type(exc).__name__}). Existing configuration kept.')
        sys.exit(1)
