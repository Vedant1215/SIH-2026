"""
Unit tests for ReconstructionPreparer.
"""

import tempfile
import unittest
from pathlib import Path

from reconstruction.preparer import ReconstructionPreparer
from metadata.models import ImageRecord, GCPPoint


class TestReconstructionPreparer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.preparer = ReconstructionPreparer(manifests_dir=self.temp_path / "manifests")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_manifest_generation_and_readiness(self):
        """Verify reconstruction manifest structure and readiness check."""
        sample_records = [
            ImageRecord(
                image_id=f"MAX_{i:04d}",
                filename=f"MAX_{i:04d}.JPG",
                filepath=f"/path/MAX_{i:04d}.JPG",
                relative_path=f"images/MAX_{i:04d}.JPG",
                filesize_bytes=1000000,
                image_width=5472,
                image_height=3648,
                latitude=47.643 + (i * 0.0001),
                longitude=16.475 + (i * 0.0001),
                altitude_ellipsoidal=512.0,
                camera_make="Autel Robotics",
                camera_model="XT705",
                focal_length_mm=10.57,
                drone_yaw=100.0,
                rtk_status="FIXED",
                quality_status="GOOD",
                validation_status="VALID",
            )
            for i in range(2, 10)
        ]
        gcp_sample = [
            GCPPoint(name="1", latitude=47.643, longitude=16.475, elevation=463.0)
        ]

        manifest = self.preparer.prepare_manifest(
            dataset_name="TestDataset",
            dataset_path="/dummy/path",
            records=sample_records,
            gcps=gcp_sample,
            validation_summary=None,
        )

        self.assertEqual(manifest.total_images, 8)
        self.assertTrue(manifest.ready_for_colmap)
        self.assertEqual(manifest.camera_profile["make"], "Autel Robotics")
        self.assertEqual(manifest.gcp_count, 1)

        # Check manifest file written to disk
        out_file = self.temp_path / "manifests" / "reconstruction_manifest.json"
        self.assertTrue(out_file.exists())


if __name__ == "__main__":
    unittest.main()
