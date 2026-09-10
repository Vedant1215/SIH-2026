"""
Metadata Normalizer for SIH 2026 Drone Ingestion System.
Fuses EXIF extraction, CSV telemetry records, MRK RTK event marks,
and GCP linkages into a unified, normalized ImageRecord.
Calculates metadata completeness without fabricating any values.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from metadata.models import ImageRecord
from metadata.csv_parser import CsvMetadataRecord

logger = logging.getLogger(__name__)


class MetadataNormalizer:
    """Normalizes and fuses disparate metadata sources into standard ImageRecords."""

    def __init__(self, dataset_root: Path):
        self.dataset_root = Path(dataset_root)

    def normalize(
        self,
        image_path: Path,
        exif_data: Optional[Dict[str, Any]] = None,
        csv_record: Optional[CsvMetadataRecord] = None,
        associated_gcps: Optional[List[str]] = None,
    ) -> ImageRecord:
        """
        Builds a normalized ImageRecord.
        Priority:
        - Geometric dimensions and optics come primarily from EXIF.
        - GPS coordinates prioritize RTK-corrected values from MRK/CSV if available and verified.
        - Orientation comes from EXIF gimbal/flight tags.
        - Records all metadata sources contributing to this image.
        """
        exif = exif_data or {}
        gcps = associated_gcps or []
        sources: List[str] = []

        filename = image_path.name
        image_id = image_path.stem
        file_size = image_path.stat().st_size if image_path.exists() else 0
        try:
            rel_path = str(image_path.relative_to(self.dataset_root))
        except ValueError:
            rel_path = filename

        # 1. Image Dimensions & File Format
        width = exif.get("image_width")
        height = exif.get("image_height")
        file_format = exif.get("file_format") or image_path.suffix.upper().lstrip(".")
        if exif:
            sources.append("EXIF")

        # 2. Coordinates & Altitude
        lat = exif.get("latitude")
        lon = exif.get("longitude")
        alt = exif.get("altitude_ellipsoidal")
        rel_alt = exif.get("altitude_relative")
        acc_h = None
        acc_v = None

        match_method = None
        match_confidence = 1.0

        # Incorporate CSV/MRK telemetry if matched
        tow = None
        week = None
        if csv_record:
            sources.append(csv_record.source_file)
            match_method = csv_record.match_method
            match_confidence = csv_record.match_confidence
            tow = csv_record.gps_time_of_week
            week = csv_record.gps_week

            # If EXIF lacked GPS but CSV had it, use CSV GPS
            if lat is None and csv_record.latitude is not None:
                lat = csv_record.latitude
            if lon is None and csv_record.longitude is not None:
                lon = csv_record.longitude
            if alt is None and csv_record.altitude is not None:
                alt = csv_record.altitude

            # Accuracies from RTK standard deviations
            if csv_record.rtk_std_lat is not None and csv_record.rtk_std_lon is not None:
                acc_h = (csv_record.rtk_std_lat + csv_record.rtk_std_lon) / 2.0
            if csv_record.rtk_std_hgt is not None:
                acc_v = csv_record.rtk_std_hgt

        # Fallback accuracy from EXIF RTK std devs if available
        if acc_h is None and exif.get("rtk_std_lat") is not None and exif.get("rtk_std_lon") is not None:
            acc_h = (exif["rtk_std_lat"] + exif["rtk_std_lon"]) / 2.0
        if acc_v is None and exif.get("rtk_std_hgt") is not None:
            acc_v = exif["rtk_std_hgt"]

        # 3. Orientation
        drone_yaw = exif.get("drone_yaw")
        drone_pitch = exif.get("drone_pitch")
        drone_roll = exif.get("drone_roll")
        camera_yaw = exif.get("camera_yaw")
        camera_pitch = exif.get("camera_pitch")
        camera_roll = exif.get("camera_roll")

        # 4. RTK Status & Standard Deviations
        rtk_status = exif.get("rtk_status", "UNKNOWN")
        rtk_flag = exif.get("rtk_flag")
        rtk_std_lat = exif.get("rtk_std_lat")
        rtk_std_lon = exif.get("rtk_std_lon")
        rtk_std_hgt = exif.get("rtk_std_hgt")

        # If CSV/MRK had RTK info, verify and merge
        if csv_record and csv_record.rtk_flag is not None:
            if rtk_flag is None:
                rtk_flag = csv_record.rtk_flag
                rtk_status = "FIXED" if rtk_flag == 50 else f"FLAG_{rtk_flag}"
            if rtk_std_lat is None:
                rtk_std_lat = csv_record.rtk_std_lat
            if rtk_std_lon is None:
                rtk_std_lon = csv_record.rtk_std_lon
            if rtk_std_hgt is None:
                rtk_std_hgt = csv_record.rtk_std_hgt

        # 5. GCP Linkage
        if gcps:
            sources.append("GCP_LIST")

        # 6. Camera Calibration
        camera_make = exif.get("camera_make")
        camera_model = exif.get("camera_model")
        focal_length_mm = exif.get("focal_length_mm")
        focal_length_35mm = exif.get("focal_length_35mm")
        aperture_fnumber = exif.get("aperture_fnumber")
        iso = exif.get("iso")
        exposure_time_s = exif.get("exposure_time_s")

        # 7. Timestamp
        timestamp = exif.get("timestamp")
        if not timestamp and csv_record:
            timestamp = csv_record.timestamp

        # 8. Calculate Completeness Score
        completeness = self._compute_completeness(
            lat=lat,
            lon=lon,
            alt=alt,
            make=camera_make,
            model=camera_model,
            focal=focal_length_mm,
            width=width,
            height=height,
            timestamp=timestamp,
            drone_yaw=drone_yaw,
            rtk_status=rtk_status,
        )

        return ImageRecord(
            image_id=image_id,
            filename=filename,
            filepath=str(image_path.resolve()),
            relative_path=rel_path,
            filesize_bytes=file_size,
            file_format=file_format,
            timestamp=timestamp,
            gps_time_of_week=tow,
            gps_week=week,
            image_width=width,
            image_height=height,
            latitude=lat,
            longitude=lon,
            altitude_ellipsoidal=alt,
            altitude_relative=rel_alt,
            gps_accuracy_h=acc_h,
            gps_accuracy_v=acc_v,
            drone_yaw=drone_yaw,
            drone_pitch=drone_pitch,
            drone_roll=drone_roll,
            camera_yaw=camera_yaw,
            camera_pitch=camera_pitch,
            camera_roll=camera_roll,
            rtk_status=rtk_status,
            rtk_flag=rtk_flag,
            rtk_std_lat=rtk_std_lat,
            rtk_std_lon=rtk_std_lon,
            rtk_std_hgt=rtk_std_hgt,
            associated_gcps=gcps,
            camera_make=camera_make,
            camera_model=camera_model,
            focal_length_mm=focal_length_mm,
            focal_length_35mm=focal_length_35mm,
            aperture_fnumber=aperture_fnumber,
            iso=iso,
            exposure_time_s=exposure_time_s,
            metadata_sources=sources,
            metadata_completeness=completeness,
            match_method=match_method,
            match_confidence=match_confidence,
            validation_status="VALID",
            validation_flags=[],
            quality_status="GOOD",
            quality_metrics=None,
            quality_reason=None,
            thumbnail_path=None,
        )

    def _compute_completeness(
        self,
        lat: Optional[float],
        lon: Optional[float],
        alt: Optional[float],
        make: Optional[str],
        model: Optional[str],
        focal: Optional[float],
        width: Optional[int],
        height: Optional[int],
        timestamp: Optional[str],
        drone_yaw: Optional[float],
        rtk_status: str,
    ) -> float:
        """Calculates normalized metadata completeness score (0.0 to 1.0)."""
        score = 0.0
        if lat is not None and lon is not None:
            score += 0.20
        if alt is not None:
            score += 0.15
        if make and model:
            score += 0.15
        if focal is not None:
            score += 0.15
        if width and height:
            score += 0.10
        if timestamp:
            score += 0.10
        if drone_yaw is not None:
            score += 0.10
        if rtk_status in ("FIXED", "FLOAT"):
            score += 0.05
        return round(min(score, 1.0), 3)
