"""Compare local translators using only fixed synthetic inputs; optional GPU A/B."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from image_prompt import ImagePrompt
from local_images import LocalImages, workflow
from scripts.image_translation_checks import CASES, issues


async def verify(generate=False, output_dir=None, checkpoint=None, port=8188):
    report = {'configured_backend': ImagePrompt().backend,
              'running_worker_backend': 'unverified; restart worker after configuration changes',
              'gpu_images_require_visual_review': True, 'results': []}
    if generate:
        if not checkpoint or output_dir is None:
            raise ValueError('GPU check requires checkpoint and output directory')
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    for backend in ('marian', 'ollama'):
        converter = ImagePrompt(backend=backend)
        for index, (source, _) in enumerate(CASES):
            row = {'backend': backend, 'case': index + 1, 'source': source}
            report['results'].append(row)
            try:
                translated = await converter.prepare(source)
                row['translation'] = translated
                row['probe_issues'] = issues(index, translated)
                graph = workflow(translated, checkpoint or 'synthetic.safetensors', 12345 + index)
                positive = graph['5']['inputs']['positive'][0]
                row['positive_matches'] = graph[positive]['inputs']['text'] == translated
                if generate:
                    # Same seed/settings/checkpoint per case across both translators.
                    image = await LocalImages(checkpoint, port=port).generate(translated, seed=12345 + index)
                    name = f'{backend}-case-{index + 1}.png'
                    (output_dir / name).write_bytes(image)
                    row['image'] = name
                    row['gpu_status'] = 'generated; visual review pending'
            except Exception as exc:
                # Never print raw errors, credentials or operational identifiers.
                row['error_type'] = type(exc).__name__
    if generate:
        (output_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generate', action='store_true', help='Explicitly generate six synthetic GPU images')
    parser.add_argument('--checkpoint')
    parser.add_argument('--port', type=int, default=8188)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    if args.generate and (not args.checkpoint or args.output_dir is None):
        parser.error('--generate requires --checkpoint and --output-dir')
    try:
        report = asyncio.run(verify(args.generate, args.output_dir, args.checkpoint, args.port))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return int(any(row.get('error_type') or row.get('probe_issues') or not row.get('positive_matches')
                       for row in report['results']))
    except Exception as exc:
        print(json.dumps({'error_type': type(exc).__name__}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
