"""
Multi-View Stereo (MVS) Dense Reconstruction Builder for SIH 2026 Drone System.
Executes image undistortion, PatchMatch Stereo depth estimation, and stereo fusion into a dense 3D point cloud.
"""

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from reconstruction.colmap_runner import ColmapRunner

logger = logging.getLogger(__name__)


class DenseBuilder:
    """Orchestrates COLMAP dense MVS reconstruction steps."""

    def __init__(self, colmap_runner: ColmapRunner):
        self.runner = colmap_runner

    def undistort_images(
        self,
        image_path: Path,
        sparse_model_path: Path,
        dense_workspace_path: Path,
        max_image_size: int = 2000,
        log_file: Optional[Path] = None,
    ) -> Tuple[bool, str]:
        """
        Runs colmap image_undistorter.
        Prepares undistorted images, camera calibration, and depth map folders in dense workspace.
        """
        dense_workspace_path.mkdir(parents=True, exist_ok=True)
        args = [
            "image_undistorter",
            "--image_path", str(image_path),
            "--input_path", str(sparse_model_path),
            "--output_path", str(dense_workspace_path),
            "--output_type", "COLMAP",
            "--max_image_size", str(max_image_size),
        ]
        return self.runner.run_command(args, log_file=log_file)

    def run_patch_match_stereo(
        self,
        dense_workspace_path: Path,
        use_gpu: bool = True,
        log_file: Optional[Path] = None,
    ) -> Tuple[bool, str]:
        """
        Runs colmap patch_match_stereo.
        Computes dense depth and normal maps using PatchMatch.
        """
        args = [
            "patch_match_stereo",
            "--workspace_path", str(dense_workspace_path),
            "--workspace_format", "COLMAP",
            "--PatchMatchStereo.geom_consistency", "true",
            "--PatchMatchStereo.max_image_size", "2000",
            "--PatchMatchStereo.gpu_index", "0" if use_gpu else "-1",
        ]
        return self.runner.run_command(args, log_file=log_file)

    def run_stereo_fusion(
        self,
        dense_workspace_path: Path,
        output_ply_path: Path,
        log_file: Optional[Path] = None,
    ) -> Tuple[bool, str]:
        """
        Runs colmap stereo_fusion.
        Fuses depth and normal maps into a unified dense 3D point cloud (.ply).
        """
        output_ply_path.parent.mkdir(parents=True, exist_ok=True)
        args = [
            "stereo_fusion",
            "--workspace_path", str(dense_workspace_path),
            "--workspace_format", "COLMAP",
            "--input_type", "geometric",
            "--output_path", str(output_ply_path),
        ]
        return self.runner.run_command(args, log_file=log_file)

    def count_ply_points(self, ply_path: Path) -> int:
        """Reads PLY header to extract exact vertex count."""
        if not ply_path.exists():
            return 0
        try:
            with open(ply_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("element vertex"):
                        return int(line.split()[2])
                    if "end_header" in line:
                        break
        except Exception as e:
            logger.warning("Could not read PLY vertex count from %s: %s", ply_path, e)
        return 0

    def densify_from_sparse(
        self,
        sparse_ply_path: Path,
        output_ply_path: Path,
    ) -> bool:
        """
        Creates a high-density, normal-oriented point cloud from sparse geometry using Open3D.
        Used when PatchMatch Stereo is constrained by headless GPU/OpenGL driver contexts.
        """
        try:
            import open3d as o3d
            import numpy as np

            if not sparse_ply_path.exists():
                logger.error("Sparse PLY not found for densification: %s", sparse_ply_path)
                return False

            pcd = o3d.io.read_point_cloud(str(sparse_ply_path))
            if not pcd.has_points() or len(pcd.points) == 0:
                logger.error("Sparse PLY has 0 points: %s", sparse_ply_path)
                return False

            logger.info("Computing normals and densifying point cloud from %d sparse points...", len(pcd.points))
            pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=2.0, max_nn=30))
            pcd.orient_normals_consistent_tangent_plane(15)

            pts = np.asarray(pcd.points)
            colors = np.asarray(pcd.colors) if pcd.has_colors() else None
            normals = np.asarray(pcd.normals)

            kdtree = o3d.geometry.KDTreeFlann(pcd)
            interpolated_pts = []
            interpolated_colors = []
            interpolated_normals = []

            sample_size = min(len(pts), 25000)
            sample_indices = np.random.choice(len(pts), size=sample_size, replace=False)
            for i in sample_indices:
                [k, idx, _] = kdtree.search_knn_vector_3d(pts[i], 4)
                for neighbor_idx in idx[1:]:
                    mid_pt = 0.5 * (pts[i] + pts[neighbor_idx])
                    interpolated_pts.append(mid_pt)
                    if colors is not None and len(colors) > 0:
                        interpolated_colors.append(0.5 * (colors[i] + colors[neighbor_idx]))
                    interpolated_normals.append(0.5 * (normals[i] + normals[neighbor_idx]))

            if interpolated_pts:
                all_pts = np.vstack([pts, np.array(interpolated_pts)])
                pcd_dense = o3d.geometry.PointCloud()
                pcd_dense.points = o3d.utility.Vector3dVector(all_pts)
                if colors is not None and len(colors) > 0:
                    all_colors = np.vstack([colors, np.array(interpolated_colors)])
                    pcd_dense.colors = o3d.utility.Vector3dVector(all_colors)
                all_normals = np.vstack([normals, np.array(interpolated_normals)])
                norm_lens = np.linalg.norm(all_normals, axis=1, keepdims=True)
                norm_lens[norm_lens == 0] = 1.0
                pcd_dense.normals = o3d.utility.Vector3dVector(all_normals / norm_lens)
            else:
                pcd_dense = pcd

            output_ply_path.parent.mkdir(parents=True, exist_ok=True)
            o3d.io.write_point_cloud(str(output_ply_path), pcd_dense)
            logger.info("Densified point cloud written to %s (%d points)", output_ply_path, len(pcd_dense.points))
            return True
        except Exception as e:
            logger.error("Failed to densify point cloud: %s", e)
            return False

