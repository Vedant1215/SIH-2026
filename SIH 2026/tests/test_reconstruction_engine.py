"""
Unit and Integration tests for Stage 2 3D Photogrammetric Reconstruction Engine.
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import open3d as o3d

from reconstruction.camera_calib import CameraCalibrationManager
from reconstruction.colmap_runner import ColmapRunner
from reconstruction.dense_builder import DenseBuilder
from reconstruction.georeferencer import Georeferencer, wgs84_to_utm_approx
from reconstruction.mesher import SurfaceMesher
from reconstruction.state_manager import ReconstructionStateManager
from reconstruction.texturer import ModelTexturer
from metadata.models import ImageRecord


class TestReconstructionEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.colmap_runner = ColmapRunner()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_colmap_binary_available(self):
        """Verify COLMAP binary is discovered and callable."""
        self.assertTrue(self.colmap_runner.is_available(), "COLMAP binary should be detected")
        success, out = self.colmap_runner.run_command(["help"])
        self.assertTrue(success)
        self.assertIn("COLMAP 4.2.0", out)

    def test_camera_calibration_autel_xt705(self):
        """Verify physical optics math for Autel XT705 1-inch sensor."""
        mgr = CameraCalibrationManager(
            camera_make="Autel Robotics",
            camera_model="XT705",
            focal_length_mm=10.57,
            image_width=5472,
            image_height=3648,
        )
        intrinsics = mgr.calculate_intrinsics()
        self.assertEqual(intrinsics["camera_model"], "OPENCV")
        self.assertAlmostEqual(intrinsics["pixel_pitch_um"], 2.412, delta=0.01)
        self.assertAlmostEqual(intrinsics["fx_pixels"], 4381.7, delta=1.0)
        self.assertAlmostEqual(intrinsics["fy_pixels"], 4381.7, delta=1.0)
        self.assertEqual(intrinsics["cx_pixels"], 2736.0)
        self.assertEqual(intrinsics["cy_pixels"], 1824.0)

    def test_reconstruction_state_manager(self):
        """Verify 10-stage lifecycle state management and restartability."""
        state_file = self.temp_path / "reconstruction_state.json"
        sm = ReconstructionStateManager(state_file)

        sm.start_pipeline(total_images=176)
        self.assertEqual(sm.state["status"], "RUNNING")
        self.assertEqual(sm.state["statistics"]["total_images"], 176)

        sm.update_stage(2, "Feature extraction started")
        self.assertEqual(sm.state["current_stage_code"], "FEATURE_EXTRACTION")
        self.assertEqual(sm.state["progress_percent"], 10)
        self.assertTrue(sm.is_stage_completed("PREPARING_WORKSPACE"))

        sm.complete_stage("FEATURE_EXTRACTION", {"features_extracted": 50000})
        self.assertTrue(sm.is_stage_completed("FEATURE_EXTRACTION"))

        sm.complete_pipeline()
        self.assertEqual(sm.state["status"], "COMPLETED")
        self.assertEqual(sm.state["progress_percent"], 100)

        # Verify disk persistence
        reloaded = ReconstructionStateManager(state_file)
        self.assertEqual(reloaded.state["status"], "COMPLETED")

    def test_georeferencer_utm_and_ref_file(self):
        """Verify UTM conversion and ref_images.txt format."""
        # Coordinates near Helenenschacht
        x, y = wgs84_to_utm_approx(47.6435, 16.4760)
        self.assertGreater(x, 600000)
        self.assertGreater(y, 5200000)

        geo = Georeferencer(self.colmap_runner)
        ref_file = self.temp_path / "ref_images.txt"
        dummy_records = [
            ImageRecord(
                image_id="MAX_0002",
                filename="MAX_0002.JPG",
                filepath="/path/MAX_0002.JPG",
                relative_path="images/MAX_0002.JPG",
                latitude=47.64368,
                longitude=16.47592,
                altitude_ellipsoidal=512.99,
            )
        ]
        cnt = geo.prepare_ref_images_file(dummy_records, ref_file)
        self.assertEqual(cnt, 1)
        self.assertTrue(ref_file.exists())
        line = ref_file.read_text().strip()
        self.assertTrue(line.startswith("MAX_0002.JPG"))

    def test_surface_meshing_and_texturing_pipeline(self):
        """Verify point cloud -> Poisson surface mesh -> GLB texturing."""
        # Create synthetic 3D point cloud with colors
        num_pts = 1000
        pts = np.random.uniform(-10, 10, (num_pts, 3))
        colors = np.random.uniform(0, 1, (num_pts, 3))
        normals = np.zeros_like(pts)
        normals[:, 2] = 1.0  # Upward normals

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pts)
        pcd.colors = o3d.utility.Vector3dVector(colors)
        pcd.normals = o3d.utility.Vector3dVector(normals)

        pcd_path = self.temp_path / "synthetic_fused.ply"
        o3d.io.write_point_cloud(str(pcd_path), pcd)

        mesher = SurfaceMesher(self.colmap_runner)
        mesh_ply = self.temp_path / "model.ply"
        mesh_obj = self.temp_path / "model.obj"
        success, out = mesher.reconstruct_mesh_poisson(pcd_path, mesh_ply, depth=6)
        self.assertTrue(success)
        self.assertTrue(mesh_ply.exists())

        obj_ok = mesher.export_obj_format(mesh_ply, mesh_obj)
        self.assertTrue(obj_ok)
        self.assertTrue(mesh_obj.exists())

        texturer = ModelTexturer()
        model_glb = self.temp_path / "model.glb"
        tex_ok, tex_msg = texturer.texture_mesh_from_point_cloud(mesh_ply, pcd_path, model_glb)
        self.assertTrue(tex_ok)
        self.assertTrue(model_glb.exists())
        self.assertGreater(model_glb.stat().st_size, 100)


if __name__ == "__main__":
    unittest.main()
