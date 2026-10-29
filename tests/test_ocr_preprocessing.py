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
    def test_partial_alpha_composites_on_white(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'fixture.png'
            image = Image.new('RGBA', (3, 1))
            image.putdata([(0, 0, 0, 0), (0, 0, 0, 128), (0, 0, 0, 255)])
            image.save(source)
            with Image.open(prepare_pages(source, root)[0]) as result:
                self.assertEqual(result.mode, 'RGB')
                self.assertEqual([result.getpixel((x, 0)) for x in range(3)],
                                 [(255, 255, 255), (127, 127, 127), (0, 0, 0)])

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

    def test_all_exif_orientations_preserve_pixel_positions(self):
        # Asymmetric lossless fixture: independent expected rows detect wrong
        # rotations and mirrored orientations, not just swapped dimensions.
        expected_rows = {
            1: ((1, 2, 3), (4, 5, 6)),
            2: ((3, 2, 1), (6, 5, 4)),
            3: ((6, 5, 4), (3, 2, 1)),
            4: ((4, 5, 6), (1, 2, 3)),
            5: ((1, 4), (2, 5), (3, 6)),
            6: ((4, 1), (5, 2), (6, 3)),
            7: ((6, 3), (5, 2), (4, 1)),
            8: ((3, 6), (2, 5), (1, 4)),
        }
        for orientation, rows in expected_rows.items():
            with self.subTest(orientation=orientation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'fixture.png'
                image = Image.new('RGB', (3, 2))
                image.putdata([(value * 30, 0, 0) for value in range(1, 7)])
                exif = image.getexif()
                exif[274] = orientation
                image.save(source, exif=exif)
                with Image.open(prepare_pages(source, root)[0]) as result:
                    self.assertEqual(result.mode, 'RGB')
                    self.assertEqual(result.size, (len(rows[0]), len(rows)))
                    self.assertNotIn(274, result.getexif())
                    for y, row in enumerate(rows):
                        for x, value in enumerate(row):
                            self.assertEqual(result.getpixel((x, y)), (value * 30, 0, 0))


@unittest.skipIf(Image is None or fitz is None, 'Optional PDF OCR libraries required')
class PDFPreprocessingTests(unittest.TestCase):
    def test_pdf_page_content_order_and_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'fixture.pdf'
            colors = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
            with fitz.open() as document:
                for index, color in enumerate(colors):
                    page = document.new_page(width=60, height=40)
                    page.draw_rect(fitz.Rect(10, 10, 50, 30), color=None, fill=color)
                    if index == 1:
                        page.set_rotation(90)
                document.save(source)
            pages = prepare_pages(source, root)
            self.assertEqual([page.name for page in pages],
                             ['page-1.png', 'page-2.png', 'page-3.png'])
            for index, path in enumerate(pages):
                with self.subTest(page=index + 1), Image.open(path) as result:
                    self.assertEqual(result.mode, 'RGB')
                    self.assertEqual(result.size, (80, 120) if index == 1 else (120, 80))
                    self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
                    center = (result.width // 2, result.height // 2)
                    self.assertEqual(result.getpixel(center),
                                     tuple(component * 255 for component in colors[index]))

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
