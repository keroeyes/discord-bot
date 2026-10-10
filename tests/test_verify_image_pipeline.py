import unittest
from unittest.mock import AsyncMock, patch
from scripts.verify_image_pipeline import verify


class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_comparison_is_read_only_and_does_not_generate_by_default(self):
        outputs = [
            'White car on a road lined with cherry blossoms, realistic photograph',
            'Two cats holding a red umbrella, watercolor',
            'Blue bicycle behind a black car, night, anime'] * 2
        with patch('scripts.verify_image_pipeline.ImagePrompt') as converter, patch('scripts.verify_image_pipeline.LocalImages') as images:
            converter.return_value.backend = 'marian'
            converter.return_value.prepare = AsyncMock(side_effect=outputs)
            report = await verify()
        images.assert_not_called()
        self.assertEqual(len(report['results']), 6)
        self.assertTrue(all(row['positive_matches'] and not row['probe_issues'] for row in report['results']))
        self.assertIn('unverified', report['running_worker_backend'])

    async def test_unavailable_model_is_not_reported_as_success(self):
        with patch('scripts.verify_image_pipeline.ImagePrompt') as converter:
            converter.return_value.prepare = AsyncMock(side_effect=RuntimeError('private fixture'))
            report = await verify()
        self.assertTrue(all(row['error_type'] == 'RuntimeError' for row in report['results']))
        self.assertNotIn('private fixture', str(report))
