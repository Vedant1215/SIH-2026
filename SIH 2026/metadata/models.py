"""
Normalized data models for SIH 2026 Drone Ingestion System.
Defines ImageRecord, QualityMetrics, GCP models, Validation, and Manifest models.
Uses Pydantic v2 for data validation and JSON serialization.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class QualityMetrics(BaseModel):
    """Image quality assessment metrics based on OpenCV analysis."""
    blur_score: float = Field(..., description="Laplacian variance (higher means sharper)")
    mean_brightness: float = Field(..., description="Mean grayscale intensity (0-255)")
    contrast_std: float = Field(..., description="Standard deviation of pixel intensities")
    is_corrupted: bool = Field(default=False, description="Whether the image failed to decode")
    is_duplicate: bool = Field(default=False, description="Whether identical image content was detected")
    duplicate_of: Optional[str] = Field(default=None, description="Image ID of original if duplicate")
    file_hash_md5: Optional[str] = Field(default=None, description="MD5 hash of image file")


class GCPPoint(BaseModel):
    """Ground Control Point survey record."""
    name: str
    easting: Optional[float] = None
    northing: Optional[float] = None
    elevation: Optional[float] = None
    longitude: float
    latitude: float
    associated_images: List[str] = Field(default_factory=list)


class GCPImageTie(BaseModel):
    """Tie point linking a GCP to a 2D image pixel coordinate."""
    gcp_name: str
    image_filename: str
    pixel_x: float
    pixel_y: float
    longitude: float
    latitude: float
    elevation: float


class ImageRecord(BaseModel):
    """
    Normalized internal data model representing a single drone survey image.
    Never fabricates missing data; defaults to None/unknown.
    """
    # Core Identification
    image_id: str = Field(..., description="Unique image identifier, e.g., MAX_0002")
    filename: str = Field(..., description="Filename, e.g., MAX_0002.JPG")
    filepath: str = Field(..., description="Absolute filesystem path")
    relative_path: str = Field(..., description="Relative path from dataset root")
    filesize_bytes: int = Field(default=0, description="File size in bytes")
    file_format: str = Field(default="JPEG", description="File extension / MIME format")

    # Temporal Information
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp or original EXIF date string")
    gps_time_of_week: Optional[float] = Field(default=None, description="GPS Time of Week (seconds)")
    gps_week: Optional[int] = Field(default=None, description="GPS Week number")

    # Dimensions
    image_width: Optional[int] = Field(default=None, description="Width in pixels")
    image_height: Optional[int] = Field(default=None, description="Height in pixels")

    # Spatial Position (WGS-84)
    latitude: Optional[float] = Field(default=None, description="Latitude in decimal degrees")
    longitude: Optional[float] = Field(default=None, description="Longitude in decimal degrees")
    altitude_ellipsoidal: Optional[float] = Field(default=None, description="GPS ellipsoidal altitude in meters")
    altitude_relative: Optional[float] = Field(default=None, description="Flight altitude relative to takeoff (m)")
    gps_accuracy_h: Optional[float] = Field(default=None, description="Horizontal accuracy (m)")
    gps_accuracy_v: Optional[float] = Field(default=None, description="Vertical accuracy (m)")

    # Orientation & Telemetry
    drone_yaw: Optional[float] = Field(default=None, description="Drone flight heading/yaw in degrees")
    drone_pitch: Optional[float] = Field(default=None, description="Drone pitch in degrees")
    drone_roll: Optional[float] = Field(default=None, description="Drone roll in degrees")
    camera_yaw: Optional[float] = Field(default=None, description="Gimbal yaw in degrees")
    camera_pitch: Optional[float] = Field(default=None, description="Gimbal pitch in degrees (e.g. -80 to -90)")
    camera_roll: Optional[float] = Field(default=None, description="Gimbal roll in degrees")

    # Survey & RTK
    rtk_status: str = Field(default="UNKNOWN", description="RTK status: FIXED, FLOAT, SINGLE, NONE, or UNKNOWN")
    rtk_flag: Optional[int] = Field(default=None, description="Raw RTK quality flag, e.g., 50")
    rtk_std_lat: Optional[float] = Field(default=None, description="RTK standard deviation latitude (m)")
    rtk_std_lon: Optional[float] = Field(default=None, description="RTK standard deviation longitude (m)")
    rtk_std_hgt: Optional[float] = Field(default=None, description="RTK standard deviation height (m)")
    associated_gcps: List[str] = Field(default_factory=list, description="GCP names visible in this image")

    # Camera Calibration / Optics
    camera_make: Optional[str] = Field(default=None, description="Camera manufacturer, e.g., Autel Robotics")
    camera_model: Optional[str] = Field(default=None, description="Camera model, e.g., XT705")
    focal_length_mm: Optional[float] = Field(default=None, description="Focal length in mm")
    focal_length_35mm: Optional[float] = Field(default=None, description="35mm equivalent focal length in mm")
    aperture_fnumber: Optional[float] = Field(default=None, description="Aperture f-number, e.g., 2.8")
    iso: Optional[int] = Field(default=None, description="ISO sensitivity")
    exposure_time_s: Optional[float] = Field(default=None, description="Exposure time in seconds")

    # Provenance & Completeness
    metadata_sources: List[str] = Field(default_factory=list, description="Sources: EXIF, MRK, GCP_LIST, CSV")
    metadata_completeness: float = Field(default=0.0, description="Completeness score 0.0 to 1.0")
    match_method: Optional[str] = Field(default=None, description="EXACT_FILENAME, INDEX_SEQUENCE, TIMESTAMP")
    match_confidence: float = Field(default=1.0, description="Confidence in metadata match (0.0 to 1.0)")

    # Validation & Quality
    validation_status: str = Field(default="VALID", description="VALID, WARNING, or INVALID")
    validation_flags: List[str] = Field(default_factory=list, description="Validation issues detected")
    quality_status: str = Field(default="GOOD", description="GOOD, WARNING, or BAD")
    quality_metrics: Optional[QualityMetrics] = Field(default=None, description="Detailed quality metrics")
    quality_reason: Optional[str] = Field(default=None, description="Explanation for quality status")
    thumbnail_path: Optional[str] = Field(default=None, description="Relative path to cached thumbnail")


class DatasetDiscoveryReport(BaseModel):
    """Summary of discovered files in dataset."""
    dataset_name: str
    dataset_path: str
    discovered_at: str
    total_files: int
    image_count: int
    image_formats: Dict[str, int]
    csv_count: int
    csv_files: List[str]
    metadata_files: List[str]
    other_files: List[str]
    directories_found: List[str]
    exif_available_count: int
    exif_missing_count: int
    gps_available_count: int
    gps_missing_count: int
    rtk_status_summary: str
    gcp_status_summary: str


class ValidationSummary(BaseModel):
    """Aggregated validation and quality report."""
    total_images: int
    valid_images: int
    warning_images: int
    invalid_images: int
    corrupt_images: int
    duplicate_images: int

    gps_available: int
    gps_missing: int

    altitude_available: int
    altitude_missing: int

    orientation_available: int
    orientation_missing: int

    rtk_available: int
    rtk_missing: int

    camera_metadata_complete: int
    camera_metadata_partial: int

    quality_breakdown: Dict[str, int]  # GOOD, WARNING, BAD
    validation_issues: Dict[str, int]
    average_completeness: float
    dataset_ready_for_reconstruction: bool
    readiness_notes: List[str]


class ReconstructionManifest(BaseModel):
    """
    Photogrammetry preparation manifest.
    Ready for ingestion by COLMAP, OpenMVS, or Open3D.
    """
    manifest_version: str = "1.0.0"
    created_at: str
    dataset_name: str
    dataset_path: str
    total_images: int
    valid_reconstruction_images: int
    camera_intrinsics_available: bool
    camera_profile: Dict[str, Any]
    gps_reference_system: str = "EPSG:4326"
    vertical_reference: str = "Ellipsoidal (WGS84)"
    rtk_used: bool
    gcp_count: int
    gcp_list: List[GCPPoint] = Field(default_factory=list)
    images: List[Dict[str, Any]] = Field(default_factory=list)
    readiness_checklist: Dict[str, bool]
    ready_for_colmap: bool
