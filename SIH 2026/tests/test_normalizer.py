"""
Unit tests for MetadataNormalizer.
"""

import unittest
from pathlib import Path
from backend.config import settings
from metadata.normalizer import MetadataNormalizer
from metadata.csv_parser import CsvMetadataRecord


class TestMetadataNormalizer(unittest.TestCase):
    def setUp(self):
        self.dataset_path = settings.dataset_root
        self.normalizer = MetadataNormalizer(self.dataset_path)

    def test_normalization_fuses_sources(self):
        """Verify normalizer combines EXIF and MRK telemetry properly."""
        dummy_path = self.dataset_path / "images" / "MAX_0002.JPG"
        exif_sample = {
            "image_id": "MAX_0002",
            "filename": "MAX_0002.JPG",
            "image_width": 5472,
            "image_height": 3648,
            "latitude": 47.64368,
            "longitude": 16.47592,
            "altitude_ellipsoidal": 512.99,
            "camera_make": "Autel Robotics",
            "camera_model": "XT705",
            "focal_length_mm": 10.57,
            "timestamp": "2022:05:25 12:17:49",
            "drone_yaw": -148.96,
            "rtk_status": "FIXED",
        }
        mrk_sample = CsvMetadataRecord(
            raw_data={},
            source_file="101FTASK_Timestamp.mrk",
            match_method="INDEX_SEQUENCE",
            match_confidence=0.98,
            latitude=47.6436873208,
            longitude=16.4759271684,
            altitude=512.998,
            rtk_flag=50,
            rtk_std_lat=0.014,
            rtk_std_lon=0.013,
            rtk_std_hgt=0.029,
        )

        record = self.normalizer.normalize(
            image_path=dummy_path,
            exif_data=exif_sample,
            csv_record=mrk_sample,
            associated_gcps=["1"],
        )

        self.assertEqual(record.image_id, "MAX_0002")
        self.assertIn("EXIF", record.metadata_sources)
        self.assertIn("101FTASK_Timestamp.mrk", record.metadata_sources)
        self.assertIn("GCP_LIST", record.metadata_sources)
        self.assertAlmostEqual(record.gps_accuracy_h, 0.0135, places=4)
        self.assertEqual(record.rtk_status, "FIXED")
        self.assertGreaterEqual(record.metadata_completeness, 0.95)

    def test_missing_data_not_fabricated(self):
        """Ensure unavailable fields remain None and are not fabricated."""
        dummy_path = Path("test_empty.jpg")
        record = self.normalizer.normalize(
            image_path=dummy_path,
            exif_data={},
            csv_record=None,
            associated_gcps=[],
        )
        self.assertIsNone(record.latitude)
        self.assertIsNone(record.longitude)
        self.assertIsNone(record.altitude_ellipsoidal)
        self.assertIsNone(record.camera_make)
        self.assertIsNone(record.focal_length_mm)
        self.assertEqual(record.rtk_status, "UNKNOWN")
        self.assertEqual(record.metadata_completeness, 0.0)


if __name__ == "__main__":
    unittest.main()
