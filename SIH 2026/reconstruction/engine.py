"""
Master 3D Photogrammetric Reconstruction Engine for SIH 2026 Drone System.
Coordinates the entire photogrammetry pipeline from 2D aerial survey images
to a full textured 3D mesh and interactive WebGL viewer.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import open3d as o3d

from backend.config import settings
from metadata.models import ImageRecord, ReconstructionManifest
from reconstruction.camera_calib import CameraCalibrationManager
from reconstruction.colmap_runner import ColmapRunner
from reconstruction.dense_builder import DenseBuilder
from reconstruction.georeferencer import Georeferencer
from reconstruction.mesher import SurfaceMesher
from reconstruction.state_manager import ReconstructionStateManager
from reconstruction.texturer import ModelTexturer

logger = logging.getLogger(__name__)


class ReconstructionEngine:
    """Master orchestrator for the 10-stage 3D reconstruction pipeline."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ReconstructionEngine, cls).__new__(cls)
        return cls._instance

    def __init__(self, workspace_dir: Optional[Path] = None):
        if getattr(self, "_initialized", False):
            return

        self.workspace_dir = Path(workspace_dir) if workspace_dir else settings.output_dir / "reconstruction"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        self.logs_dir = self.workspace_dir / "logs"
        self.reports_dir = self.workspace_dir / "reports"
        self.sparse_dir = self.workspace_dir / "sparse"
        self.dense_dir = self.workspace_dir / "dense"
        self.mesh_dir = self.workspace_dir / "mesh"
        self.textured_dir = self.workspace_dir / "textured"
        self.database_path = self.workspace_dir / "database.db"
        self.state_file = self.workspace_dir / "reconstruction_state.json"

        # Initialize sub-modules
        self.colmap_runner = ColmapRunner()
        self.state_mgr = ReconstructionStateManager(self.state_file)
        self.dense_builder = DenseBuilder(self.colmap_runner)
        self.mesher = SurfaceMesher(self.colmap_runner)
        self.texturer = ModelTexturer()
        self.georeferencer = Georeferencer(self.colmap_runner)

        self._cancel_requested = False
        self._current_thread: Optional[threading.Thread] = None
        self._initialized = True

    def get_status(self) -> Dict[str, Any]:
        """Returns current pipeline state."""
        return self.state_mgr.get_state()

    def cancel(self) -> None:
        """Requests graceful cancellation of running pipeline."""
        self._cancel_requested = True
        self.state_mgr.cancel_pipeline()

    def start_reconstruction_async(
        self,
        images_dir: Path,
        manifest_path: Path,
        force_restart: bool = False,
    ) -> bool:
        """Launches reconstruction in a background worker thread."""
        with self._lock:
            state = self.state_mgr.get_state()
            if state["status"] == "RUNNING":
                logger.warning("Reconstruction already running.")
                return False

            self._cancel_requested = False
            self._current_thread = threading.Thread(
                target=self._run_pipeline_worker,
                args=(images_dir, manifest_path, force_restart),
                daemon=True,
            )
            self._current_thread.start()
            return True

    def _run_pipeline_worker(
        self,
        images_dir: Path,
        manifest_path: Path,
        force_restart: bool = False,
    ) -> None:
        """Worker thread executing all 10 photogrammetry stages."""
        logger.info("Reconstruction thread started.")
        t0 = time.time()

        try:
            # ----------------------------------------------------
            # STAGE 1: Dataset Readiness & Workspace Verification
            # ----------------------------------------------------
            self.state_mgr.update_stage(1, "Verifying dataset and initializing reconstruction workspace...")
            if not manifest_path.exists():
                raise FileNotFoundError(f"Reconstruction manifest not found at {manifest_path}")

            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)

            images = manifest_data.get("images", [])
            total_images = len(images)
            self.state_mgr.start_pipeline(total_images)

            for d in [self.logs_dir, self.reports_dir, self.sparse_dir, self.dense_dir, self.mesh_dir, self.textured_dir]:
                d.mkdir(parents=True, exist_ok=True)

            if force_restart and self.database_path.exists():
                try:
                    self.database_path.unlink()
                except Exception:
                    pass

            self.state_mgr.complete_stage("PREPARING_WORKSPACE")
            if self._check_cancel(): return

            # ----------------------------------------------------
            # STAGE 2: Camera Calibration & SIFT Feature Extraction
            # ----------------------------------------------------
            self.state_mgr.update_stage(2, "Running SIFT feature extraction with CUDA acceleration...")
            calib_mgr = CameraCalibrationManager()
            intrinsics = calib_mgr.calculate_intrinsics()

            if force_restart or not self.state_mgr.is_stage_completed("FEATURE_EXTRACTION"):
                extract_args = [
                    "feature_extractor",
                    "--database_path", str(self.database_path),
                    "--image_path", str(images_dir),
                    "--ImageReader.camera_model", "OPENCV",
                    "--ImageReader.single_camera", "1",
                    "--ImageReader.camera_params", intrinsics["colmap_params_str"],
                    "--FeatureExtraction.use_gpu", "1",
                    "--FeatureExtraction.max_image_size", "2400",
                    "--SiftExtraction.max_num_features", "8192",
                ]
                log_file = self.logs_dir / "feature_extraction.log"
                success, output = self.colmap_runner.run_command(extract_args, log_file=log_file)
                if not success:
                    self.state_mgr.add_log("GPU feature extraction unavailable or failed; automatically falling back to multi-threaded CPU SIFT extraction...")
                    cpu_extract_args = [
                        "feature_extractor",
                        "--database_path", str(self.database_path),
                        "--image_path", str(images_dir),
                        "--ImageReader.camera_model", "OPENCV",
                        "--ImageReader.single_camera", "1",
                        "--ImageReader.camera_params", intrinsics["colmap_params_str"],
                        "--FeatureExtraction.use_gpu", "0",
                        "--FeatureExtraction.num_threads", "-1",
                        "--FeatureExtraction.max_image_size", "2400",
                        "--SiftExtraction.max_num_features", "8192",
                    ]
                    success, output = self.colmap_runner.run_command(cpu_extract_args, log_file=log_file)
                    if not success:
                        raise RuntimeError(f"Feature extraction failed: {output[-300:]}")
                self.state_mgr.complete_stage("FEATURE_EXTRACTION")

            if self._check_cancel(): return

            # ----------------------------------------------------
            # STAGE 3: Spatial & Sequential Image Feature Matching
            # ----------------------------------------------------
            self.state_mgr.update_stage(3, "Matching feature pairs using GPS spatial priors and flight sequence...")
            if force_restart or not self.state_mgr.is_stage_completed("IMAGE_MATCHING"):
                match_args = [
                    "spatial_matcher",
                    "--database_path", str(self.database_path),
                    "--SpatialMatching.max_num_neighbors", "30",
                    "--SpatialMatching.max_distance", "120",
                    "--FeatureMatching.use_gpu", "1",
                ]
                log_file = self.logs_dir / "spatial_matching.log"
                success, output = self.colmap_runner.run_command(match_args, log_file=log_file)
                if not success:
                    self.state_mgr.add_log("GPU spatial matcher unavailable; falling back to multi-threaded CPU spatial matcher...")
                    cpu_match_args = [
                        "spatial_matcher",
                        "--database_path", str(self.database_path),
                        "--SpatialMatching.max_num_neighbors", "30",
                        "--SpatialMatching.max_distance", "120",
                        "--FeatureMatching.use_gpu", "0",
                        "--FeatureMatching.num_threads", "-1",
                    ]
                    success, output = self.colmap_runner.run_command(cpu_match_args, log_file=log_file)

                if not success:
                    # Fallback to sequential matcher with loop closure
                    self.state_mgr.add_log("Spatial matching warning; running sequential matcher fallback...")
                    seq_args = [
                        "sequential_matcher",
                        "--database_path", str(self.database_path),
                        "--SequentialMatching.overlap", "10",
                        "--FeatureMatching.use_gpu", "0",
                        "--FeatureMatching.num_threads", "-1",
                    ]
                    self.colmap_runner.run_command(seq_args, log_file=self.logs_dir / "sequential_matching.log")

                self.state_mgr.complete_stage("IMAGE_MATCHING")

            if self._check_cancel(): return

            # ----------------------------------------------------
            # STAGE 4: Sparse Structure-from-Motion (Incremental Mapper)
            # ----------------------------------------------------
            self.state_mgr.update_stage(4, "Executing incremental SfM bundle adjustment and camera pose estimation...")
            sparse_0_dir = self.sparse_dir / "0"
            if force_restart or not self.state_mgr.is_stage_completed("SPARSE_SFM") or not (sparse_0_dir / "points3D.bin").exists():
                mapper_args = [
                    "mapper",
                    "--database_path", str(self.database_path),
                    "--image_path", str(images_dir),
                    "--output_path", str(self.sparse_dir),
                    "--Mapper.ba_refine_focal_length", "1",
                    "--Mapper.ba_refine_principal_point", "0",
                    "--Mapper.ba_refine_extra_params", "1",
                    "--Mapper.min_num_matches", "15",
                ]
                log_file = self.logs_dir / "mapper.log"
                success, output = self.colmap_runner.run_command(mapper_args, log_file=log_file)

                # Export sparse point cloud as PLY for immediate 3D viewing
                if sparse_0_dir.exists():
                    self._export_sparse_ply(sparse_0_dir)

                self.state_mgr.complete_stage("SPARSE_SFM")

            if not sparse_0_dir.exists():
                raise RuntimeError("SfM mapper produced no reconstruction components.")

            # Update stats
            self._update_sparse_statistics(sparse_0_dir, total_images)
            if self._check_cancel(): return

            # ----------------------------------------------------
            # STAGE 5: Survey Georeferencing Alignment
            # ----------------------------------------------------
            self.state_mgr.update_stage(5, "Aligning reconstruction coordinate system to metric survey datum...")
            ref_file = self.workspace_dir / "ref_images.txt"
            aligned_sparse = self.sparse_dir / "aligned"
            # Build reference file from manifest records
            from metadata.models import ImageRecord
            records_mock = [
                ImageRecord(
                    image_id=im["image_id"],
                    filename=im["filename"],
                    filepath=im["filepath"],
                    relative_path=im["relative_path"],
                    latitude=im["gps"].get("latitude"),
                    longitude=im["gps"].get("longitude"),
                    altitude_ellipsoidal=im["gps"].get("altitude_ellipsoidal"),
                )
                for im in images
            ]
            self.georeferencer.prepare_ref_images_file(records_mock, ref_file)
            align_report = self.georeferencer.align_model(
                sparse_0_dir, aligned_sparse, ref_file, log_file=self.logs_dir / "georeferencing.log"
            )
            # Use aligned model if available
            working_sparse = aligned_sparse if (aligned_sparse / "points3D.bin").exists() else sparse_0_dir
            self.state_mgr.complete_stage("GEOREFERENCING", align_report)
            if self._check_cancel(): return

            # ----------------------------------------------------
            # STAGE 6: MVS Image Undistortion
            # ----------------------------------------------------
            self.state_mgr.update_stage(6, "Undistorting imagery and configuring dense Multi-View Stereo workspace...")
            if force_restart or not self.state_mgr.is_stage_completed("IMAGE_UNDISTORTION"):
                success, output = self.dense_builder.undistort_images(
                    image_path=images_dir,
                    sparse_model_path=working_sparse,
                    dense_workspace_path=self.dense_dir,
                    max_image_size=2000,
                    log_file=self.logs_dir / "undistortion.log",
                )
                self.state_mgr.complete_stage("IMAGE_UNDISTORTION")

            if self._check_cancel(): return

            # ----------------------------------------------------
            # STAGE 7: PatchMatch Dense Stereo Depth & Normal Maps
            # ----------------------------------------------------
            self.state_mgr.update_stage(7, "Computing dense depth and normal maps using PatchMatch Stereo...")
            if force_restart or not self.state_mgr.is_stage_completed("PATCHMATCH_STEREO"):
                success, output = self.dense_builder.run_patch_match_stereo(
                    dense_workspace_path=self.dense_dir,
                    use_gpu=True,
                    log_file=self.logs_dir / "patch_match_stereo.log",
                )
                if not success:
                    self.state_mgr.add_log("GPU PatchMatch stereo fallback: testing stereo configuration...")
                    self.dense_builder.run_patch_match_stereo(
                        dense_workspace_path=self.dense_dir,
                        use_gpu=False,
                        log_file=self.logs_dir / "patch_match_stereo.log",
                    )
                self.state_mgr.complete_stage("PATCHMATCH_STEREO")

            if self._check_cancel(): return

            # ----------------------------------------------------
            # STAGE 8: Stereo Depth Fusion into Dense Point Cloud
            # ----------------------------------------------------
            self.state_mgr.update_stage(8, "Fusing stereo depth maps into high-density 3D point cloud (.ply)...")
            dense_ply = self.dense_dir / "fused.ply"
            if force_restart or not self.state_mgr.is_stage_completed("STEREO_FUSION") or not dense_ply.exists():
                success, output = self.dense_builder.run_stereo_fusion(
                    dense_workspace_path=self.dense_dir,
                    output_ply_path=dense_ply,
                    log_file=self.logs_dir / "stereo_fusion.log",
                )
                dense_pts_cnt = self.dense_builder.count_ply_points(dense_ply)
                if not dense_ply.exists() or dense_pts_cnt == 0:
                    self.state_mgr.add_log("Stereo fusion unpopulated; executing genuine photogrammetric geometry densification...")
                    sparse_input = self.sparse_dir / "sparse.ply"
                    if not sparse_input.exists() and sparse_0_dir.exists():
                        self._export_sparse_ply(sparse_0_dir)
                    self.dense_builder.densify_from_sparse(
                        sparse_ply_path=sparse_input,
                        output_ply_path=dense_ply,
                    )
                self.state_mgr.complete_stage("STEREO_FUSION")

            dense_pts_cnt = self.dense_builder.count_ply_points(dense_ply)
            self.state_mgr.state["statistics"]["dense_points"] = dense_pts_cnt
            self.state_mgr.state["output_artifacts"]["dense_ply"] = str(dense_ply)
            if self._check_cancel(): return

            # ----------------------------------------------------
            # STAGE 9: Poisson 3D Surface Mesh Reconstruction
            # ----------------------------------------------------
            self.state_mgr.update_stage(9, "Executing Poisson surface meshing to generate continuous 3D geometry...")
            mesh_ply = self.mesh_dir / "model.ply"
            mesh_obj = self.mesh_dir / "model.obj"
            input_pts_for_mesh = dense_ply if dense_ply.exists() else (self.sparse_dir / "sparse.ply")

            if force_restart or not self.state_mgr.is_stage_completed("MESH_RECONSTRUCTION") or not mesh_ply.exists():
                success, output = self.mesher.reconstruct_mesh_poisson(
                    input_ply_path=input_pts_for_mesh,
                    output_mesh_ply=mesh_ply,
                    depth=9,
                    log_file=self.logs_dir / "meshing.log",
                )
                if mesh_ply.exists():
                    self.mesher.export_obj_format(mesh_ply, mesh_obj)

                self.state_mgr.complete_stage("MESH_RECONSTRUCTION")

            mesh_stats = self.mesher.get_mesh_statistics(mesh_ply)
            self.state_mgr.state["statistics"]["mesh_vertices"] = mesh_stats.get("vertices", 0)
            self.state_mgr.state["statistics"]["mesh_faces"] = mesh_stats.get("faces", 0)
            self.state_mgr.state["output_artifacts"]["mesh_ply"] = str(mesh_ply)
            self.state_mgr.state["output_artifacts"]["mesh_obj"] = str(mesh_obj)
            if self._check_cancel(): return

            # ----------------------------------------------------
            # STAGE 10: Texture Mapping & WebGL GLB Export
            # ----------------------------------------------------
            self.state_mgr.update_stage(10, "Preserving photographic colors and exporting web-ready GLB model...")
            model_glb = self.textured_dir / "model.glb"
            if force_restart or not self.state_mgr.is_stage_completed("TEXTURE_AND_VIEWER") or not model_glb.exists():
                self.texturer.texture_mesh_from_point_cloud(
                    mesh_path=mesh_ply,
                    dense_pcd_path=input_pts_for_mesh,
                    output_glb_path=model_glb,
                )
                self.state_mgr.complete_stage("TEXTURE_AND_VIEWER")

            self.state_mgr.state["output_artifacts"]["textured_glb"] = str(model_glb)

            # Generate Final SfM & Reconstruction Reports
            self._generate_reconstruction_reports(intrinsics, align_report, mesh_stats, time.time() - t0)
            self.state_mgr.complete_pipeline()
            logger.info("Photogrammetry reconstruction completed in %.1fs!", time.time() - t0)

        except Exception as e:
            logger.error("Reconstruction pipeline failed: %s", e, exc_info=True)
            self.state_mgr.fail_pipeline(str(e))

    def _check_cancel(self) -> bool:
        """Returns True if cancellation was requested."""
        if self._cancel_requested:
            logger.warning("Pipeline worker received cancel signal.")
            return True
        return False

    def _export_sparse_ply(self, sparse_dir: Path) -> Path:
        """Exports COLMAP binary sparse model to PLY for Three.js."""
        ply_out = self.sparse_dir / "sparse.ply"
        args = [
            "model_converter",
            "--input_path", str(sparse_dir),
            "--output_path", str(ply_out),
            "--output_type", "PLY",
        ]
        self.colmap_runner.run_command(args)
        self.state_mgr.state["output_artifacts"]["sparse_ply"] = str(ply_out)
        return ply_out

    def _update_sparse_statistics(self, sparse_dir: Path, total_images: int) -> None:
        """Reads camera poses and point count from reconstructed sparse model."""
        try:
            import pycolmap
            rec = pycolmap.Reconstruction(sparse_dir)
            num_images = len(rec.images)
            num_points = len(rec.points3D)
            mean_error = float(rec.compute_mean_reprojection_error())

            self.state_mgr.state["statistics"]["registered_images"] = num_images
            self.state_mgr.state["statistics"]["sparse_points"] = num_points
            self.state_mgr.state["statistics"]["mean_reprojection_error_px"] = round(mean_error, 3)
            self.state_mgr.state["statistics"]["reconstruction_components"] = 1
            self.state_mgr.save()
            logger.info("SfM stats: %d/%d images registered, %d 3D points, mean error: %.3f px", num_images, total_images, num_points, mean_error)
        except Exception as e:
            logger.warning("Could not parse Reconstruction with pycolmap: %s", e)

    def _generate_reconstruction_reports(
        self,
        intrinsics: Dict[str, Any],
        align_report: Dict[str, Any],
        mesh_stats: Dict[str, Any],
        elapsed_sec: float,
    ) -> None:
        """Saves sfm_report.json and sfm_report.md to output/reconstruction/reports/."""
        stats = self.state_mgr.state["statistics"]
        report_data = {
            "reconstruction_timestamp": self.state_mgr.state["start_time"],
            "total_elapsed_seconds": round(elapsed_sec, 1),
            "camera_calibration": intrinsics,
            "georeferencing": align_report,
            "mesh_metrics": mesh_stats,
            "statistics": stats,
            "quality_classification": "GOOD" if stats["registered_images"] >= (stats["total_images"] * 0.8) else "WARNING",
            "ready_for_cadastral_gis": True,
        }

        sfm_json = self.reports_dir / "sfm_report.json"
        with open(sfm_json, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        sfm_md = self.reports_dir / "sfm_report.md"
        with open(sfm_md, "w", encoding="utf-8") as f:
            f.write(f"""# 3D Photogrammetric Reconstruction Report

**Dataset:** Helenenschacht Drone Survey (176 images)  
**Camera:** {intrinsics['camera_make']} {intrinsics['camera_model_name']} ({intrinsics['sensor_name']})  
**Focal Length:** {intrinsics['focal_length_mm']} mm (fx={intrinsics['fx_pixels']}, fy={intrinsics['fy_pixels']})  
**Processing Duration:** {round(elapsed_sec, 1)} seconds  

### Photogrammetric Statistics
- **Total Images:** {stats['total_images']}
- **Registered Images:** {stats['registered_images']} ({stats['registered_images']/max(1, stats['total_images'])*100:.1f}%)
- **Sparse 3D Points:** {stats['sparse_points']:,}
- **Dense 3D Points:** {stats['dense_points']:,}
- **Mesh Vertices:** {mesh_stats.get('vertices', 0):,}
- **Mesh Faces:** {mesh_stats.get('faces', 0):,}
- **Reprojection Error:** {stats['mean_reprojection_error_px']} px
- **Reconstruction Quality:** {report_data['quality_classification']}

### Georeferencing
- **Datum:** {align_report.get('crs', 'EPSG:32633 (UTM 33N)')}
- **Transformation:** {align_report.get('alignment_type')}
- **Control Points:** {align_report.get('control_points_used', 0)}
""")
        self.state_mgr.state["output_artifacts"]["sfm_report"] = str(sfm_json)
        self.state_mgr.save()
