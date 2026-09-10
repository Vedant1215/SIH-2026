"""
Unit tests for ImageQualityAnalyzer.
"""

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from validation.quality import ImageQualityAnalyzer


class TestImageQuality(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.analyzer = ImageQualityAnalyzer(thumbnails_dir=self.temp_path / "thumbs")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sharp_image_classified_good(self):
        """Verify sharp, well-exposed image gets GOOD status."""
        # Create a balanced exposure checkerboard with sharp edges and mean brightness ~130
        sharp_img = np.full((400, 400, 3), 70, dtype=np.uint8)
        for i in range(0, 400, 40):
            for j in range(0, 400, 40):
                if (i // 40 + j // 40) % 2 == 0:
                    sharp_img[i:i+40, j:j+40] = 190

        file_path = self.temp_path / "sharp.jpg"
        cv2.imwrite(str(file_path), sharp_img)

        metrics, status, reason, thumb = self.analyzer.analyze_image(file_path)
        self.assertEqual(status, "GOOD")
        self.assertFalse(metrics.is_corrupted)
        self.assertGreater(metrics.blur_score, 300.0)

    def test_blurred_image_classified_warning_or_bad(self):
        """Verify heavily blurred image is classified as WARNING or BAD."""
        img = np.random.randint(0, 256, (300, 300, 3), dtype=np.uint8)
        # Apply heavy blur
        blurred = cv2.GaussianBlur(img, (45, 45), 20)

        file_path = self.temp_path / "blurred.jpg"
        cv2.imwrite(str(file_path), blurred)

        metrics, status, reason, thumb = self.analyzer.analyze_image(file_path)
        self.assertIn(status, ["WARNING", "BAD"])
        self.assertTrue("blur" in reason.lower())

    def test_dark_image_detected(self):
        """Verify pitch black image detected as underexposed."""
        dark_img = np.full((300, 300, 3), 10, dtype=np.uint8)
        file_path = self.temp_path / "dark.jpg"
        cv2.imwrite(str(file_path), dark_img)

        metrics, status, reason, thumb = self.analyzer.analyze_image(file_path)
        self.assertIn(status, ["WARNING", "BAD"])
        self.assertTrue("dark" in reason.lower() or "blur" in reason.lower())

    def test_corrupt_file_handling(self):
        """Verify non-image corrupt file handled gracefully."""
        corrupt_path = self.temp_path / "corrupt.jpg"
        with open(corrupt_path, "wb") as f:
            f.write(b"NOT_A_REAL_IMAGE_DATA_CORRUPT")

        metrics, status, reason, thumb = self.analyzer.analyze_image(corrupt_path)
        self.assertEqual(status, "BAD")
        self.assertTrue(metrics.is_corrupted)


if __name__ == "__main__":
    unittest.main()
