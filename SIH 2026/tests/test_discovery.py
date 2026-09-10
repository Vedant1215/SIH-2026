"""
Unit tests for DatasetDiscoveryService.
"""

import unittest
from pathlib import Path
from backend.config import settings
from dataset.discovery import DatasetDiscoveryService


class TestDatasetDiscovery(unittest.TestCase):
    def setUp(self):
        self.dataset_path = settings.dataset_root
        self.service = DatasetDiscoveryService(self.dataset_path)

    def test_scan_real_dataset(self):
        """Verify discovery on the local Helenenschacht dataset."""
        if not self.dataset_path.exists():
            self.skipTest(f"Dataset path does not exist: {self.dataset_path}")

        images, csvs, metadata, others = self.service.scan()
        self.assertEqual(len(images), 176, "Expected exactly 176 drone survey images")
        self.assertGreaterEqual(len(csvs), 1, "Expected at least 1 CSV file")
        self.assertGreaterEqual(len(metadata), 2, "Expected MRK and GCP metadata files")

    def test_nonexistent_path_raises_error(self):
        """Verify graceful error when dataset path is invalid."""
        invalid_service = DatasetDiscoveryService(Path("C:/nonexistent_dataset_folder_xyz"))
        with self.assertRaises(FileNotFoundError):
            invalid_service.scan()

    def test_generate_report(self):
        """Verify generation of DatasetDiscoveryReport."""
        if not self.dataset_path.exists():
            self.skipTest("Dataset not available")

        images, csvs, metadata, others = self.service.scan()
        report = self.service.generate_report(
            images, csvs, metadata, others,
            exif_available_count=176,
            gps_available_count=176,
        )
        self.assertEqual(report.image_count, 176)
        self.assertIn("JPG", report.image_formats)
        self.assertEqual(report.image_formats["JPG"], 176)


if __name__ == "__main__":
    unittest.main()
