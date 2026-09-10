"""
Unit tests for DatasetValidator.
"""

import unittest
from validation.validator import DatasetValidator
from metadata.models import ImageRecord


class TestDatasetValidator(unittest.TestCase):
    def setUp(self):
        self.validator = DatasetValidator()

    def test_valid_image_record(self):
        """Verify clean record passes validation."""
        rec = ImageRecord(
            image_id="IMG_0001",
            filename="IMG_0001.JPG",
            filepath="/dummy/IMG_0001.JPG",
            relative_path="images/IMG_0001.JPG",
            filesize_bytes=1024000,
            image_width=5472,
            image_height=3648,
            latitude=47.643,
            longitude=16.475,
            altitude_ellipsoidal=512.0,
            altitude_relative=50.0,
            drone_yaw=120.0,
            camera_make="Autel Robotics",
            camera_model="XT705",
            focal_length_mm=10.57,
            rtk_status="FIXED",
        )
        status, flags = self.validator.validate_image_record(rec)
        self.assertEqual(status, "VALID")
        self.assertEqual(len(flags), 0)

    def test_invalid_coordinates_detected(self):
        """Verify invalid latitude bounds flag error."""
        rec = ImageRecord(
            image_id="IMG_0002",
            filename="IMG_0002.JPG",
            filepath="/dummy/IMG_0002.JPG",
            relative_path="images/IMG_0002.JPG",
            filesize_bytes=1024000,
            image_width=5472,
            image_height=3648,
            latitude=147.643, # Invalid (> 90)
            longitude=16.475,
            altitude_ellipsoidal=512.0,
            camera_make="Autel",
            camera_model="XT705",
            focal_length_mm=10.57,
        )
        status, flags = self.validator.validate_image_record(rec)
        self.assertEqual(status, "INVALID")
        self.assertTrue(any("INVALID_LATITUDE" in f for f in flags))

    def test_null_island_detected(self):
        """Verify (0,0) Null Island coordinates flagged as suspicious."""
        rec = ImageRecord(
            image_id="IMG_0003",
            filename="IMG_0003.JPG",
            filepath="/dummy/IMG_0003.JPG",
            relative_path="images/IMG_0003.JPG",
            filesize_bytes=1024000,
            image_width=5472,
            image_height=3648,
            latitude=0.0,
            longitude=0.0,
            altitude_ellipsoidal=512.0,
            camera_make="Autel",
            camera_model="XT705",
            focal_length_mm=10.57,
        )
        status, flags = self.validator.validate_image_record(rec)
        self.assertEqual(status, "WARNING")
        self.assertIn("SUSPICIOUS_NULL_ISLAND_COORDINATES", flags)


if __name__ == "__main__":
    unittest.main()
