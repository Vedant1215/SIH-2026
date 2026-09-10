"""
3D Texturing and WebGL GLB Model Exporter for SIH 2026 Drone Reconstruction System.
Transfers photographic RGB colors from drone points to the 3D surface mesh
and exports standard web-friendly binary GLB (glTF 2.0) models for Three.js.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

import open3d as o3d
import numpy as np

logger = logging.getLogger(__name__)


class ModelTexturer:
    """Projects colors from photographic dense point clouds onto 3D meshes and exports GLB."""

    def texture_mesh_from_point_cloud(
        self,
        mesh_path: Path,
        dense_pcd_path: Path,
        output_glb_path: Path,
    ) -> Tuple[bool, str]:
        """
        Transfers photographic colors from dense point cloud to mesh vertices via KDTree
        and exports a standalone, web-optimized binary GLB (glTF 2.0) file.
        """
        try:
            output_glb_path.parent.mkdir(parents=True, exist_ok=True)

            if not mesh_path.exists():
                return False, f"Mesh file not found: {mesh_path}"
            if not dense_pcd_path.exists():
                return False, f"Dense point cloud not found: {dense_pcd_path}"

            logger.info("Loading mesh and dense point cloud for texturing...")
            mesh = o3d.io.read_triangle_mesh(str(mesh_path))
            pcd = o3d.io.read_point_cloud(str(dense_pcd_path))

            if not pcd.has_colors():
                logger.warning("Dense point cloud lacks RGB colors; generating height-gradient colors.")
                # Compute elevation-based natural terrain gradient if points lack color
                pts = np.asarray(pcd.points)
                z = pts[:, 2]
                z_norm = (z - z.min()) / (z.max() - z.min() + 1e-6)
                colors = np.zeros_like(pts)
                colors[:, 0] = 0.2 + 0.5 * z_norm  # Red/Terrain
                colors[:, 1] = 0.5 + 0.3 * (1 - z_norm) # Green/Vegetation
                colors[:, 2] = 0.2
                pcd.colors = o3d.utility.Vector3dVector(colors)

            # Build KDTree on point cloud to transfer true photographic colors to mesh vertices
            logger.info("Projecting photographic colors to %d mesh vertices...", len(mesh.vertices))
            kdtree = o3d.geometry.KDTreeFlann(pcd)
            mesh_colors = []
            pcd_colors = np.asarray(pcd.colors)

            for vertex in mesh.vertices:
                [_, idx, _] = kdtree.search_knn_vector_3d(vertex, 1)
                mesh_colors.append(pcd_colors[idx[0]])

            mesh.vertex_colors = o3d.utility.Vector3dVector(np.asarray(mesh_colors))

            # Compute smooth vertex normals for lighting
            mesh.compute_vertex_normals()

            # Export binary GLB
            success = o3d.io.write_triangle_mesh(str(output_glb_path), mesh)
            if success:
                logger.info("Successfully exported textured GLB model (%d vertices, %d faces) -> %s", len(mesh.vertices), len(mesh.triangles), output_glb_path)
                return True, f"GLB exported: {len(mesh.vertices)} vertices, {len(mesh.triangles)} faces"
            return False, "Failed to write GLB file"

        except Exception as e:
            msg = f"Error during model texturing: {e}"
            logger.error(msg)
            return False, msg
