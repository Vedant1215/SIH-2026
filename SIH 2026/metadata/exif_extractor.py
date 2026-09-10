"""
EXIF/XMP Metadata Extraction Service for SIH 2026 Drone Ingestion System.
Extracts drone camera telemetry, GPS, orientation, and survey RTK tags.
Uses ExifTool for high-precision metadata decoding with normalized outputs.
"""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ExifExtractor:
    """Extracts and normalizes EXIF and XMP metadata from drone images."""

    def __init__(self, exiftool_path: str = "exiftool"):
        self.exiftool_path = exiftool_path
        self._exiftool_available = self._check_exiftool()

    def _check_exiftool(self) -> bool:
        """Verifies if exiftool is callable."""
        try:
            res = subprocess.run(
                [self.exiftool_path, "-ver"],
                capture_output=True,
                text=True,
                check=False,
            )
            available = res.returncode == 0
            if available:
                logger.info("ExifTool verified (version %s)", res.stdout.strip())
            return available
        except Exception as e:
            logger.warning("ExifTool not found in PATH: %s", e)
            return False

    def extract_batch(self, image_paths: List[Path]) -> Dict[str, Dict[str, Any]]:
        """
        Extracts EXIF metadata for multiple images in a single batch call.
        Returns a dictionary mapping image filename to normalized metadata dict.
        """
        if not image_paths:
            return {}

        results: Dict[str, Dict[str, Any]] = {}

        if self._exiftool_available:
            try:
                # Use exiftool in batch mode with -json -n (numeric output)
                cmd = [self.exiftool_path, "-json", "-n", "-q"] + [str(p) for p in image_paths]
                res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if res.returncode == 0 and res.stdout.strip():
                    raw_records = json.loads(res.stdout)
                    for raw in raw_records:
                        normalized = self._normalize_exif_record(raw)
                        results[normalized["filename"]] = normalized
                    return results
            except Exception as e:
                logger.error("Batch ExifTool extraction failed: %s", e)

        # Fallback to individual extraction if batch fails
        for path in image_paths:
            try:
                rec = self.extract_single(path)
                results[rec["filename"]] = rec
            except Exception as e:
                logger.error("Failed to extract metadata for %s: %s", path.name, e)
        return results

    def extract_single(self, image_path: Path) -> Dict[str, Any]:
        """Extracts and normalizes metadata for a single image."""
        if self._exiftool_available:
            try:
                cmd = [self.exiftool_path, "-json", "-n", "-q", str(image_path)]
                res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if res.returncode == 0 and res.stdout.strip():
                    raw_records = json.loads(res.stdout)
                    if raw_records:
                        return self._normalize_exif_record(raw_records[0])
            except Exception as e:
                logger.error("Single ExifTool extraction failed for %s: %s", image_path.name, e)

        # Minimal fallback if exiftool not available or fails
        return self._fallback_extraction(image_path)

    def _normalize_exif_record(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Maps raw vendor-specific tags to normalized keys."""
        source_file = raw.get("SourceFile", "")
        filename = raw.get("FileName") or Path(source_file).name
        image_id = Path(filename).stem

        # Dimensions
        width = raw.get("ImageWidth") or raw.get("ExifImageWidth")
        height = raw.get("ImageHeight") or raw.get("ExifImageHeight")

        # Coordinates
        lat = raw.get("GPSLatitude")
        lon = raw.get("GPSLongitude")
        alt = raw.get("GPSAltitude")
        rel_alt = raw.get("RelativeAltitude")

        # Orientation
        # Autel / DJI stores gimbal and flight yaw
        drone_yaw = raw.get("FlightYawDegree") or raw.get("GPSImgDirection")
        drone_pitch = raw.get("FlightPitchDegree")
        drone_roll = raw.get("FlightRollDegree")
        camera_yaw = raw.get("GimbalYawDegree")
        camera_pitch = raw.get("GimbalPitchDegree")
        camera_roll = raw.get("GimbalRollDegree")

        # RTK / Survey information
        rtk_flag = raw.get("RtkFlag")
        rtk_std_lat = raw.get("RtkStdLat")
        rtk_std_lon = raw.get("RtkStdLon")
        rtk_std_hgt = raw.get("RtkStdHgt")

        # Translate RTK status
        rtk_status = "UNKNOWN"
        if rtk_flag is not None:
            # 50 in Autel EVO II RTK indicates RTK Fixed solution
            if int(rtk_flag) == 50:
                rtk_status = "FIXED"
            elif int(rtk_flag) in (16, 34):
                rtk_status = "FLOAT"
            elif int(rtk_flag) > 0:
                rtk_status = f"FLAG_{rtk_flag}"
            else:
                rtk_status = "NONE"

        # Timestamp
        date_str = raw.get("DateTimeOriginal") or raw.get("CreateDate") or raw.get("ModifyDate")

        # Camera calibration
        make = raw.get("Make")
        model = raw.get("Model")
        focal_length = raw.get("FocalLength")
        focal_35mm = raw.get("FocalLengthIn35mmFormat")
        f_number = raw.get("FNumber") or raw.get("Aperture")
        iso = raw.get("ISO")
        exp_time = raw.get("ExposureTime")

        # Convert exposure time fraction if represented as float or string
        if isinstance(exp_time, str) and "/" in exp_time:
            try:
                num, den = exp_time.split("/")
                exp_time = float(num) / float(den)
            except ValueError:
                exp_time = None

        return {
            "image_id": image_id,
            "filename": filename,
            "filepath": str(Path(source_file).resolve()) if source_file else "",
            "filesize_bytes": raw.get("FileSize") if isinstance(raw.get("FileSize"), int) else (
                Path(source_file).stat().st_size if source_file and Path(source_file).exists() else 0
            ),
            "file_format": raw.get("FileType", "JPEG"),
            "timestamp": str(date_str) if date_str else None,
            "image_width": int(width) if width is not None else None,
            "image_height": int(height) if height is not None else None,
            "latitude": float(lat) if lat is not None else None,
            "longitude": float(lon) if lon is not None else None,
            "altitude_ellipsoidal": float(alt) if alt is not None else None,
            "altitude_relative": float(rel_alt) if rel_alt is not None else None,
            "drone_yaw": float(drone_yaw) if drone_yaw is not None else None,
            "drone_pitch": float(drone_pitch) if drone_pitch is not None else None,
            "drone_roll": float(drone_roll) if drone_roll is not None else None,
            "camera_yaw": float(camera_yaw) if camera_yaw is not None else None,
            "camera_pitch": float(camera_pitch) if camera_pitch is not None else None,
            "camera_roll": float(camera_roll) if camera_roll is not None else None,
            "rtk_status": rtk_status,
            "rtk_flag": int(rtk_flag) if rtk_flag is not None else None,
            "rtk_std_lat": float(rtk_std_lat) if rtk_std_lat is not None else None,
            "rtk_std_lon": float(rtk_std_lon) if rtk_std_lon is not None else None,
            "rtk_std_hgt": float(rtk_std_hgt) if rtk_std_hgt is not None else None,
            "camera_make": str(make) if make else None,
            "camera_model": str(model) if model else None,
            "focal_length_mm": float(focal_length) if focal_length is not None else None,
            "focal_length_35mm": float(focal_35mm) if focal_35mm is not None else None,
            "aperture_fnumber": float(f_number) if f_number is not None else None,
            "iso": int(iso) if iso is not None else None,
            "exposure_time_s": float(exp_time) if exp_time is not None else None,
            "raw_exif": {k: v for k, v in raw.items() if not str(v).startswith("(Binary")},
        }

    def _fallback_extraction(self, image_path: Path) -> Dict[str, Any]:
        """Fallback extraction when ExifTool is not available."""
        file_size = image_path.stat().st_size if image_path.exists() else 0
        return {
            "image_id": image_path.stem,
            "filename": image_path.name,
            "filepath": str(image_path.resolve()),
            "filesize_bytes": file_size,
            "file_format": image_path.suffix.upper().lstrip("."),
            "timestamp": None,
            "image_width": None,
            "image_height": None,
            "latitude": None,
            "longitude": None,
            "altitude_ellipsoidal": None,
            "altitude_relative": None,
            "drone_yaw": None,
            "drone_pitch": None,
            "drone_roll": None,
            "camera_yaw": None,
            "camera_pitch": None,
            "camera_roll": None,
            "rtk_status": "UNKNOWN",
            "rtk_flag": None,
            "rtk_std_lat": None,
            "rtk_std_lon": None,
            "rtk_std_hgt": None,
            "camera_make": None,
            "camera_model": None,
            "focal_length_mm": None,
            "focal_length_35mm": None,
            "aperture_fnumber": None,
            "iso": None,
            "exposure_time_s": None,
            "raw_exif": {},
        }
