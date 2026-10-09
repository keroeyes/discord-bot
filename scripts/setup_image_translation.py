"""Activate local Ollama translation only after synthetic content checks."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from image_prompt import CONFIG, ImagePrompt


def configure():
    converter = ImagePrompt(backend='ollama')
    cases = [
        ('벚꽃이 핀 나무들이 늘어선 도로 위의 흰색 자동차, 실사 사진',
         [('white',), ('car',), ('road',), ('cherry',), ('blossom',), ('lined', 'rows', 'lining'),
          ('photograph', 'photo')]),
        ('빨간 우산을 든 고양이 두 마리, 수채화',
         [('red',), ('umbrella',), ('cat',), ('two', '2'), ('watercolor', 'watercolour')]),
        ('검은 자동차 뒤에 파란 자전거, 밤, 애니메이션 그림',
         [('black',), ('car',), ('blue',), ('bicycle', 'bike'), ('behind',), ('night',),
          ('anime', 'animation', 'animated')])]
    for index, (source, concepts) in enumerate(cases, 1):
        output = converter.translate(source)
        print(f'Synthetic check {index}: {output}')
        if not all(any(term in output.lower() for term in group) for group in concepts):
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
