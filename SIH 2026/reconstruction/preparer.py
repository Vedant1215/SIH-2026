"""
3D Reconstruction Preparation Service for SIH 2026 Drone Ingestion System.
Prepares and validates drone dataset for subsequent photogrammetry stages (COLMAP / OpenMVS).
Generates standard reconstruction manifest with camera intrinsics, georeferencing, and orientation.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from metadata.models import ImageRecord, ReconstructionManifest, GCPPoint, ValidationSummary

logger = logging.getLogger(__name__)


class ReconstructionPreparer:
    """Validates readiness and builds COLMAP/SfM photogrammetry manifests."""

    def __init__(self, manifests_dir: Path):
        self.manifests_dir = Path(manifests_dir)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    def prepare_manifest(
        self,
        dataset_name: str,
        dataset_path: str,
        records: List[ImageRecord],
        gcps: Optional[List[GCPPoint]] = None,
        validation_summary: Optional[ValidationSummary] = None,
    ) -> ReconstructionManifest:
        """
        Validates photogrammetry readiness and outputs a reconstruction manifest.
        """
        total = len(records)
        valid_reconstruction_images = [
            r for r in records if r.validation_status != "INVALID" and r.quality_status != "BAD"
        ]

        # Check camera intrinsics
        sample_img = records[0] if records else None
        camera_make = sample_img.camera_make if sample_img else "Unknown"
        camera_model = sample_img.camera_model if sample_img else "Unknown"
        focal_mm = sample_img.focal_length_mm if sample_img else None
        focal_35 = sample_img.focal_length_35mm if sample_img else None
        width = sample_img.image_width if sample_img else None
        height = sample_img.image_height if sample_img else None

        camera_profile = {
            "make": camera_make,
            "model": camera_model,
            "focal_length_mm": focal_mm,
            "focal_length_35mm": focal_35,
            "sensor_width_px": width,
            "sensor_height_px": height,
            "camera_model_type": "PINHOLE / RADIAL",
            "principal_point": [round(width / 2.0, 2), round(height / 2.0, 2)] if width and height else None,
        }

        # Check readiness checklist
        gps_count = sum(1 for r in records if r.latitude is not None and r.longitude is not None)
        cam_count = sum(1 for r in records if r.camera_make and r.focal_length_mm)
        rtk_count = sum(1 for r in records if r.rtk_status in ("FIXED", "FLOAT"))

        checklist = {
            "sufficient_images": total >= 3,
            "valid_gps_coverage": gps_count >= max(1, int(total * 0.8)),
            "camera_profile_complete": cam_count >= max(1, int(total * 0.9)),
            "no_severe_corruption": (validation_summary.corrupt_images == 0) if validation_summary else True,
            "survey_grade_georeferencing": rtk_count > 0 or (gcps is not None and len(gcps) > 0),
        }

        ready_for_colmap = all(
            [
                checklist["sufficient_images"],
                checklist["camera_profile_complete"],
                checklist["no_severe_corruption"],
            ]
        )

        image_manifest_entries: List[Dict[str, Any]] = []
        for r in records:
            image_manifest_entries.append(
                {
                    "image_id": r.image_id,
                    "filename": r.filename,
                    "filepath": r.filepath,
                    "relative_path": r.relative_path,
                    "dimensions": [r.image_width, r.image_height],
                    "gps": {
                        "latitude": r.latitude,
                        "longitude": r.longitude,
                        "altitude_ellipsoidal": r.altitude_ellipsoidal,
                        "altitude_relative": r.altitude_relative,
                        "accuracy_h_meters": r.gps_accuracy_h,
                        "accuracy_v_meters": r.gps_accuracy_v,
                    },
                    "orientation": {
                        "drone_yaw": r.drone_yaw,
                        "drone_pitch": r.drone_pitch,
                        "drone_roll": r.drone_roll,
                        "camera_yaw": r.camera_yaw,
                        "camera_pitch": r.camera_pitch,
                        "camera_roll": r.camera_roll,
                    },
                    "camera": {
                        "make": r.camera_make,
                        "model": r.camera_model,
                        "focal_length_mm": r.focal_length_mm,
                        "aperture": r.aperture_fnumber,
                        "iso": r.iso,
                        "exposure_time_s": r.exposure_time_s,
                    },
                    "rtk_status": r.rtk_status,
                    "quality_status": r.quality_status,
                    "quality_metrics": r.quality_metrics.model_dump() if r.quality_metrics else None,
                    "validation_status": r.validation_status,
                    "ready_for_reconstruction": r.validation_status != "INVALID" and r.quality_status != "BAD",
                }
            )

        manifest = ReconstructionManifest(
            manifest_version="1.0.0",
            created_at=datetime.now(timezone.utc).isoformat(),
            dataset_name=dataset_name,
            dataset_path=dataset_path,
            total_images=total,
            valid_reconstruction_images=len(valid_reconstruction_images),
            camera_intrinsics_available=cam_count > 0,
            camera_profile=camera_profile,
            gps_reference_system="EPSG:4326 (WGS84)",
            vertical_reference="Ellipsoidal Height (m)",
            rtk_used=rtk_count > 0,
            gcp_count=len(gcps) if gcps else 0,
            gcp_list=gcps or [],
            images=image_manifest_entries,
            readiness_checklist=checklist,
            ready_for_colmap=ready_for_colmap,
        )

        # Save manifest to output directory
        self.save_manifest(manifest)
        return manifest

    def save_manifest(self, manifest: ReconstructionManifest) -> Path:
        """Saves manifest JSON to disk."""
        out_file = self.manifests_dir / "reconstruction_manifest.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(manifest.model_dump(), f, indent=2)
        logger.info("Saved 3D Reconstruction Manifest to %s", out_file)
        return out_file
