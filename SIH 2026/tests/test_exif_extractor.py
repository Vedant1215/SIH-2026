"""
Unit tests for ExifExtractor.
"""

import unittest
from pathlib import Path
from backend.config import settings
from metadata.exif_extractor import ExifExtractor


class TestExifExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = ExifExtractor()
        self.dataset_path = settings.dataset_root
        self.sample_image = self.dataset_path / "images" / "MAX_0002.JPG"

    def test_extract_single_real_image(self):
        """Verify EXIF extraction on real image MAX_0002.JPG."""
        if not self.sample_image.exists():
            self.skipTest(f"Sample image not found: {self.sample_image}")

        data = self.extractor.extract_single(self.sample_image)
        self.assertEqual(data["filename"], "MAX_0002.JPG")
        self.assertEqual(data["image_id"], "MAX_0002")
        self.assertEqual(data["camera_make"], "Autel Robotics")
        self.assertEqual(data["camera_model"], "XT705")
        self.assertAlmostEqual(data["focal_length_mm"], 10.57, delta=0.5)

        # GPS coordinates check (Austria Burgenland)
        self.assertIsNotNone(data["latitude"])
        self.assertIsNotNone(data["longitude"])
        self.assertAlmostEqual(data["latitude"], 47.64368, delta=0.01)
        self.assertAlmostEqual(data["longitude"], 16.47592, delta=0.01)

        # RTK and altitude
        self.assertIsNotNone(data["altitude_ellipsoidal"])
        self.assertAlmostEqual(data["altitude_ellipsoidal"], 512.99, delta=1.0)
        self.assertEqual(data["rtk_flag"], 50)
        self.assertEqual(data["rtk_status"], "FIXED")

    def test_batch_extraction(self):
        """Verify batch extraction across multiple images."""
        img_dir = self.dataset_path / "images"
        if not img_dir.exists():
            self.skipTest("Images directory not found")

        images = sorted(list(img_dir.glob("*.JPG")))[:5]
        batch_results = self.extractor.extract_batch(images)
        self.assertEqual(len(batch_results), 5)
        for img_p in images:
            self.assertIn(img_p.name, batch_results)
            self.assertEqual(batch_results[img_p.name]["camera_make"], "Autel Robotics")


if __name__ == "__main__":
    unittest.main()
