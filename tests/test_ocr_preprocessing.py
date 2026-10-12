"""GPU-free input regressions; optional OCR libraries are required."""
import tempfile
import unittest
from pathlib import Path

from scripts.unlimited_ocr_run import prepare_pages

try:
    from PIL import Image
except ImportError:
    Image = None
try:
    import fitz
except ImportError:
    fitz = None


@unittest.skipIf(Image is None, 'Pillow is an optional OCR dependency')
class ImagePreprocessingTests(unittest.TestCase):
    def test_transparent_black_text_keeps_contrast(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = Image.new('RGBA', (20, 20), (0, 0, 0, 0))
            image.putpixel((10, 10), (0, 0, 0, 255))
            source = root / 'fixture.png'
            image.save(source)
            with Image.open(prepare_pages(source, root)[0]) as result:
                self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
                self.assertEqual(result.getpixel((10, 10)), (0, 0, 0))

    def test_palette_transparency_keeps_contrast(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = Image.new('P', (20, 20), 0)
            image.putpalette([0, 0, 0, 0, 0, 0] + [0] * 762)
            image.putpixel((10, 10), 1)
            source = root / 'fixture.png'
            image.save(source, transparency=0)
            with Image.open(prepare_pages(source, root)[0]) as result:
                self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
                self.assertEqual(result.getpixel((10, 10)), (0, 0, 0))

    def test_opaque_rgb_preserves_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'fixture.png'
            Image.new('RGB', (20, 10), (25, 50, 75)).save(source)
            with Image.open(prepare_pages(source, root)[0]) as result:
                self.assertEqual(result.size, (20, 10))
                self.assertEqual(result.getpixel((0, 0)), (25, 50, 75))

    def test_exif_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'fixture.jpg'
            image = Image.new('RGB', (20, 10), 'white')
            exif = image.getexif()
            exif[274] = 6
            image.save(source, exif=exif)
            with Image.open(prepare_pages(source, root)[0]) as result:
                self.assertEqual(result.size, (10, 20))


@unittest.skipIf(Image is None or fitz is None, 'Optional PDF OCR libraries required')
class PDFPreprocessingTests(unittest.TestCase):
    def test_two_pages_and_render_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'fixture.pdf'
            with fitz.open() as document:
                for _ in range(2):
                    document.new_page(width=3000, height=4000)
                document.save(source)
            pages = prepare_pages(source, root)
            self.assertEqual(len(pages), 2)
            for page in pages:
                with Image.open(page) as result:
                    self.assertLessEqual(max(result.size), 2048)

    def test_long_pdfs_up_to_fifty_pages_accepted(self):
        for count in (33, 50):
            with self.subTest(pages=count), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'fixture.pdf'
                with fitz.open() as document:
                    for _ in range(count):
                        document.new_page(width=20, height=20)
                    document.save(source)
                self.assertEqual(len(prepare_pages(source, root)), count)

    def test_fifty_one_pages_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'fixture.pdf'
            with fitz.open() as document:
                for _ in range(51):
                    document.new_page()
                document.save(source)
            with self.assertRaises(ValueError):
                prepare_pages(source, root)

    def test_encrypted_pdf_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'fixture.pdf'
            with fitz.open() as document:
                document.new_page()
                document.save(source, encryption=fitz.PDF_ENCRYPT_AES_256,
                              owner_pw='synthetic-owner', user_pw='synthetic-user')
            with self.assertRaises(ValueError):
                prepare_pages(source, root)
