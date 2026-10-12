"""Isolated GPU subprocess; no Discord credentials or document text logging."""
from pathlib import Path
import sys
import tempfile

MODEL = 'baidu/Unlimited-OCR'
REVISION = '07dea832e22aefee32ad281d4b80551282e1c168'


def prepare_pages(source, directory):
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 20_000_000
    if source.suffix.lower() != '.pdf':
        with Image.open(source) as image:
            if image.width * image.height > Image.MAX_IMAGE_PIXELS:
                raise ValueError('Image too large')
            path = directory / 'page-1.png'
            oriented = ImageOps.exif_transpose(image)
            # Composite transparency onto a document-like white background.
            # Dropping alpha alone can erase black text on transparent PNGs.
            rgba = oriented.convert('RGBA')
            background = Image.new('RGBA', rgba.size, 'white')
            Image.alpha_composite(background, rgba).convert('RGB').save(path)
            return [path]
    import fitz
    with fitz.open(source) as doc:
        if doc.needs_pass or not 1 <= len(doc) <= 10:
            raise ValueError('PDF limit or encrypted PDF')
        paths = []
        for number, page in enumerate(doc):
            if page.rect.width <= 0 or page.rect.height <= 0:
                raise ValueError('Invalid page')
            scale = min(2, 2048 / max(page.rect.width, page.rect.height))
            path = directory / f'page-{number + 1}.png'
            page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).save(path)
            paths.append(path)
        return paths


def run(source, output):
    import torch
    from transformers import AutoModel, AutoTokenizer
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required')
    with tempfile.TemporaryDirectory(prefix='pages-', dir=output.parent) as directory:
        root = Path(directory)
        pages = prepare_pages(source, root)
        # Cache must be prepared explicitly. Runtime never downloads new remote code.
        kwargs = dict(revision=REVISION, trust_remote_code=True, local_files_only=True)
        tokenizer = AutoTokenizer.from_pretrained(MODEL, **kwargs)
        model = AutoModel.from_pretrained(MODEL, use_safetensors=True,
                                         torch_dtype=torch.bfloat16, **kwargs).eval().cuda()
        results = []
        for number, page in enumerate(pages):
            # eval_mode returns text before the upstream visualization/eval code.
            text = model.infer(tokenizer, prompt='<image>document parsing.',
                               image_file=str(page), output_path=str(root / f'out-{number}'),
                               base_size=1024, image_size=640, crop_mode=True,
                               eval_mode=True, save_results=False, max_length=32768,
                               no_repeat_ngram_size=35, ngram_window=128)
            if not isinstance(text, str) or not text.strip():
                raise RuntimeError('Empty page result')
            results.append(f'--- 페이지 {number + 1} ---\n{text.strip()}')
        result = '\n\n'.join(results)
        if len(result.encode('utf-8')) > 2 * 1024 * 1024:
            raise ValueError('Output limit')
        output.write_text(result, encoding='utf-8')


if __name__ == '__main__':
    try:
        run(Path(sys.argv[1]), Path(sys.argv[2]))
    except Exception:
        raise SystemExit(1) from None
