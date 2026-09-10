"""
Reconstruction State and Restartability Manager for SIH 2026 Drone System.
Maintains pipeline progress, stage completion, output artifact paths,
and enables resuming long-running photogrammetry tasks.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STAGES = [
    ("1/10", "PREPARING_WORKSPACE", "Preparing reconstruction workspace and images"),
    ("2/10", "FEATURE_EXTRACTION", "Extracting SIFT features and descriptors (GPU/CUDA)"),
    ("3/10", "IMAGE_MATCHING", "Spatial & sequential image feature matching with GPS priors"),
    ("4/10", "SPARSE_SFM", "Incremental Structure-from-Motion (bundle adjustment & camera poses)"),
    ("5/10", "GEOREFERENCING", "Survey coordinate alignment with RTK priors and GCP targets"),
    ("6/10", "IMAGE_UNDISTORTION", "Undistorting cameras and preparing MVS stereo pairs"),
    ("7/10", "PATCHMATCH_STEREO", "PatchMatch dense stereo depth and normal map computation"),
    ("8/10", "STEREO_FUSION", "Stereo depth map fusion into dense 3D point cloud"),
    ("9/10", "MESH_RECONSTRUCTION", "Poisson surface reconstruction and mesh filtering"),
    ("10/10", "TEXTURE_AND_VIEWER", "Texture mapping and web-ready GLB model export"),
]


class ReconstructionStateManager:
    """Manages persistent state across the 10 reconstruction stages."""

    def __init__(self, state_file: Path):
        self.state_file = Path(state_file)
        self.state: Dict[str, Any] = self._load_or_create()

    def _load_or_create(self) -> Dict[str, Any]:
        """Loads existing state or initializes default structure."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Could not read existing state file %s: %s", self.state_file, e)

        initial = {
            "pipeline_version": "2.0.0",
            "status": "IDLE",  # IDLE, RUNNING, COMPLETED, FAILED, CANCELLED
            "current_stage_index": 0,
            "current_stage_code": "NOT_STARTED",
            "current_stage_name": "Not started",
            "progress_percent": 0,
            "start_time": None,
            "end_time": None,
            "elapsed_seconds": 0,
            "error_message": None,
            "completed_stages": [],
            "stage_details": {},
            "statistics": {
                "total_images": 0,
                "registered_images": 0,
                "sparse_points": 0,
                "dense_points": 0,
                "mesh_vertices": 0,
                "mesh_faces": 0,
                "mean_reprojection_error_px": 0.0,
                "reconstruction_components": 0,
                "gcp_count": 0,
                "georeferencing_status": "PENDING",
            },
            "output_artifacts": {
                "database": None,
                "sparse_model": None,
                "sparse_ply": None,
                "dense_ply": None,
                "mesh_ply": None,
                "mesh_obj": None,
                "textured_glb": None,
                "sfm_report": None,
            },
            "logs": [],
        }
        return initial

    def save(self) -> None:
        """Persists current state to JSON file."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error("Error saving reconstruction state: %s", e)

    def start_pipeline(self, total_images: int) -> None:
        """Marks pipeline as running."""
        self.state["status"] = "RUNNING"
        self.state["start_time"] = datetime.now(timezone.utc).isoformat()
        self.state["end_time"] = None
        self.state["error_message"] = None
        self.state["statistics"]["total_images"] = total_images
        self.save()

    def update_stage(self, stage_idx: int, log_line: Optional[str] = None) -> None:
        """Updates stage progress (1 to 10)."""
        if 1 <= stage_idx <= len(STAGES):
            prefix, code, name = STAGES[stage_idx - 1]
            self.state["current_stage_index"] = stage_idx
            self.state["current_stage_code"] = code
            self.state["current_stage_name"] = f"[{prefix}] {name}"
            self.state["progress_percent"] = int((stage_idx - 1) / len(STAGES) * 100)

            if code not in self.state["completed_stages"] and stage_idx > 1:
                prev_code = STAGES[stage_idx - 2][1]
                if prev_code not in self.state["completed_stages"]:
                    self.state["completed_stages"].append(prev_code)

            if log_line:
                self.add_log(log_line)
            self.save()

    def complete_stage(self, stage_code: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Marks a stage as completed with metadata."""
        if stage_code not in self.state["completed_stages"]:
            self.state["completed_stages"].append(stage_code)
        if details:
            self.state["stage_details"][stage_code] = details
        self.save()

    def is_stage_completed(self, stage_code: str) -> bool:
        """Checks if a stage is already finished for restartability."""
        return stage_code in self.state.get("completed_stages", [])

    def complete_pipeline(self) -> None:
        """Marks pipeline as successfully finished."""
        self.state["status"] = "COMPLETED"
        self.state["progress_percent"] = 100
        self.state["current_stage_index"] = 10
        self.state["current_stage_code"] = "COMPLETE"
        self.state["current_stage_name"] = "3D Reconstruction Complete"
        self.state["end_time"] = datetime.now(timezone.utc).isoformat()
        for _, code, _ in STAGES:
            if code not in self.state["completed_stages"]:
                self.state["completed_stages"].append(code)
        self.save()

    def fail_pipeline(self, error_message: str) -> None:
        """Marks pipeline as failed with clear diagnostics."""
        self.state["status"] = "FAILED"
        self.state["error_message"] = error_message
        self.state["end_time"] = datetime.now(timezone.utc).isoformat()
        self.add_log(f"ERROR: {error_message}")
        self.save()

    def cancel_pipeline(self) -> None:
        """Marks pipeline as cancelled."""
        self.state["status"] = "CANCELLED"
        self.state["end_time"] = datetime.now(timezone.utc).isoformat()
        self.add_log("Pipeline execution was cancelled by user.")
        self.save()

    def add_log(self, message: str) -> None:
        """Appends message to circular log buffer."""
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        self.state["logs"].append(entry)
        if len(self.state["logs"]) > 250:
            self.state["logs"] = self.state["logs"][-250:]

    def get_state(self) -> Dict[str, Any]:
        """Returns snapshot of current state."""
        return self.state
