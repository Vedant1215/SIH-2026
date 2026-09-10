"""
3D Surface Meshing Engine for SIH 2026 Drone Reconstruction System.
Converts dense point clouds into triangular 3D surface meshes using Poisson surface reconstruction
and Open3D geometry processing. Exports standard PLY and OBJ formats.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import open3d as o3d
import numpy as np

from reconstruction.colmap_runner import ColmapRunner

logger = logging.getLogger(__name__)


class SurfaceMesher:
    """Generates 3D surface mesh from reconstructed point clouds."""

    def __init__(self, colmap_runner: ColmapRunner):
        self.runner = colmap_runner

    def reconstruct_mesh_poisson(
        self,
        input_ply_path: Path,
        output_mesh_ply: Path,
        depth: int = 10,
        log_file: Optional[Path] = None,
    ) -> Tuple[bool, str]:
        """
        Executes Poisson surface reconstruction using COLMAP or Open3D.
        """
        output_mesh_ply.parent.mkdir(parents=True, exist_ok=True)

        # Attempt native colmap poisson_mesher first
        if self.runner.is_available():
            args = [
                "poisson_mesher",
                "--input_path", str(input_ply_path),
                "--output_path", str(output_mesh_ply),
                "--PoissonMeshing.depth", str(depth),
                "--PoissonMeshing.trim", "1.0",
            ]
            success, output = self.runner.run_command(args, log_file=log_file)
            if success and output_mesh_ply.exists() and output_mesh_ply.stat().st_size > 1000:
                logger.info("COLMAP Poisson meshing succeeded -> %s", output_mesh_ply)
                return True, output

        # Open3D Poisson reconstruction fallback / alternative
        try:
            logger.info("Running Open3D Poisson surface reconstruction on %s...", input_ply_path)
            pcd = o3d.io.read_point_cloud(str(input_ply_path))
            if not pcd.has_points():
                return False, "Input point cloud is empty"

            if not pcd.has_normals():
                pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.5, max_nn=30))
                pcd.orient_normals_consistent_tangent_plane(10)

            mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=depth)

            # Crop low density noise
            vertices_to_remove = densities < np.quantile(densities, 0.05)
            mesh.remove_vertices_by_mask(vertices_to_remove)
            mesh.remove_degenerate_triangles()
            mesh.remove_duplicated_triangles()
            mesh.remove_duplicated_vertices()
            mesh.remove_non_manifold_edges()

            o3d.io.write_triangle_mesh(str(output_mesh_ply), mesh)
            logger.info("Open3D Poisson meshing wrote %d vertices, %d faces to %s", len(mesh.vertices), len(mesh.triangles), output_mesh_ply)
            return True, f"Open3D Poisson completed: {len(mesh.vertices)} vertices, {len(mesh.triangles)} faces"

        except Exception as e:
            msg = f"Error during Open3D surface meshing: {e}"
            logger.error(msg)
            return False, msg

    def export_obj_format(self, mesh_ply_path: Path, output_obj_path: Path) -> bool:
        """Converts PLY mesh to Wavefront OBJ format."""
        try:
            output_obj_path.parent.mkdir(parents=True, exist_ok=True)
            mesh = o3d.io.read_triangle_mesh(str(mesh_ply_path))
            return o3d.io.write_triangle_mesh(str(output_obj_path), mesh)
        except Exception as e:
            logger.error("Failed to export OBJ mesh: %s", e)
            return False

    def get_mesh_statistics(self, mesh_path: Path) -> Dict[str, Any]:
        """Calculates vertex count, face count, and 3D bounding box dimensions."""
        if not mesh_path.exists():
            return {"vertices": 0, "faces": 0, "bounds": None}
        try:
            mesh = o3d.io.read_triangle_mesh(str(mesh_path))
            bbox = mesh.get_axis_aligned_bounding_box()
            extent = bbox.get_extent()
            return {
                "vertices": len(mesh.vertices),
                "faces": len(mesh.triangles),
                "has_vertex_colors": mesh.has_vertex_colors(),
                "dimensions_meters": [round(float(extent[0]), 2), round(float(extent[1]), 2), round(float(extent[2]), 2)],
                "bounding_box_min": [round(float(bbox.min_bound[i]), 2) for i in range(3)],
                "bounding_box_max": [round(float(bbox.max_bound[i]), 2) for i in range(3)],
            }
        except Exception as e:
            logger.warning("Error reading mesh statistics: %s", e)
            return {"vertices": 0, "faces": 0, "bounds": None}
