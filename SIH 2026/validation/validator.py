"""
Dataset Validation Service for SIH 2026 Drone Ingestion System.
Performs comprehensive data integrity, coordinate bounds, altitude sanity,
camera metadata, and completeness checks.
Generates an aggregated validation summary and diagnostics report.
"""

import logging
from typing import Dict, List, Set, Tuple
from metadata.models import ImageRecord, ValidationSummary

logger = logging.getLogger(__name__)


class DatasetValidator:
    """Validates individual ImageRecords and entire dataset integrity."""

    def __init__(
        self,
        min_altitude_m: float = -500.0,
        max_altitude_m: float = 9000.0,
        min_image_dimension: int = 640,
    ):
        self.min_altitude = min_altitude_m
        self.max_altitude = max_altitude_m
        self.min_dim = min_image_dimension

    def validate_image_record(self, record: ImageRecord) -> Tuple[str, List[str]]:
        """
        Validates a single ImageRecord.
        Returns (status, flags) where status is 'VALID', 'WARNING', or 'INVALID'.
        """
        flags: List[str] = []
        is_invalid = False

        # 1. File existence & size
        if record.filesize_bytes <= 0:
            flags.append("CORRUPT_EMPTY_FILE")
            is_invalid = True

        # 2. Dimensions check
        if record.image_width is None or record.image_height is None:
            flags.append("MISSING_DIMENSIONS")
            flags.append("EXIF_UNREADABLE")
        elif record.image_width < self.min_dim or record.image_height < self.min_dim:
            flags.append("SUSPICIOUS_LOW_RESOLUTION")

        # 3. GPS Coordinate Bounds & Validity
        if record.latitude is None or record.longitude is None:
            flags.append("MISSING_GPS")
        else:
            if not (-90.0 <= record.latitude <= 90.0):
                flags.append(f"INVALID_LATITUDE_{record.latitude}")
                is_invalid = True
            if not (-180.0 <= record.longitude <= 180.0):
                flags.append(f"INVALID_LONGITUDE_{record.longitude}")
                is_invalid = True
            # Null Island check (0, 0)
            if abs(record.latitude) < 0.0001 and abs(record.longitude) < 0.0001:
                flags.append("SUSPICIOUS_NULL_ISLAND_COORDINATES")

        # 4. Altitude Sanity
        if record.altitude_ellipsoidal is None:
            flags.append("MISSING_ALTITUDE")
        else:
            if not (self.min_altitude <= record.altitude_ellipsoidal <= self.max_altitude):
                flags.append(f"SUSPICIOUS_ALTITUDE_{record.altitude_ellipsoidal:.1f}M")

        # 5. Relative Altitude Sanity (if available)
        if record.altitude_relative is not None:
            if record.altitude_relative < -10.0 or record.altitude_relative > 2000.0:
                flags.append(f"SUSPICIOUS_RELATIVE_ALTITUDE_{record.altitude_relative:.1f}M")

        # 6. Orientation Sanity
        if record.drone_yaw is None and record.camera_yaw is None:
            flags.append("MISSING_ORIENTATION")

        # 7. Camera Optics / Calibration
        if record.camera_make is None or record.camera_model is None:
            flags.append("MISSING_CAMERA_PROFILE")
        if record.focal_length_mm is None or record.focal_length_mm <= 0:
            flags.append("MISSING_FOCAL_LENGTH")

        # 8. RTK Status
        if record.rtk_status == "UNKNOWN" or record.rtk_status == "NONE":
            flags.append("NO_RTK_FIX")

        # Determine overall validation status
        if is_invalid or "CORRUPT_EMPTY_FILE" in flags:
            status = "INVALID"
        elif any(
            f in flags
            for f in (
                "MISSING_GPS",
                "SUSPICIOUS_NULL_ISLAND_COORDINATES",
                "MISSING_DIMENSIONS",
                "MISSING_FOCAL_LENGTH",
            )
        ):
            status = "WARNING"
        elif len(flags) > 0:
            status = "WARNING"
        else:
            status = "VALID"

        return status, flags

    def validate_dataset(self, records: List[ImageRecord]) -> ValidationSummary:
        """
        Performs dataset-wide integrity checks:
        - Validates every record
        - Checks for duplicate filenames or IDs
        - Aggregates overall coverage statistics
        """
        total = len(records)
        valid_cnt = 0
        warning_cnt = 0
        invalid_cnt = 0
        corrupt_cnt = 0
        duplicate_cnt = 0

        gps_avail = 0
        alt_avail = 0
        orient_avail = 0
        rtk_avail = 0
        cam_complete = 0
        cam_partial = 0

        quality_breakdown: Dict[str, int] = {"GOOD": 0, "WARNING": 0, "BAD": 0}
        issues_tally: Dict[str, int] = {}
        completeness_sum = 0.0

        seen_ids: Set[str] = set()
        seen_coords: Set[Tuple[float, float]] = set()

        for rec in records:
            status, flags = self.validate_image_record(rec)
            rec.validation_status = status
            rec.validation_flags = flags

            # Duplicate ID check
            if rec.image_id in seen_ids:
                flags.append("DUPLICATE_IMAGE_ID")
                rec.validation_status = "WARNING"
                duplicate_cnt += 1
            else:
                seen_ids.add(rec.image_id)

            if rec.validation_status == "VALID":
                valid_cnt += 1
            elif rec.validation_status == "WARNING":
                warning_cnt += 1
            else:
                invalid_cnt += 1

            if "CORRUPT_EMPTY_FILE" in flags or (rec.quality_metrics and rec.quality_metrics.is_corrupted):
                corrupt_cnt += 1

            if rec.latitude is not None and rec.longitude is not None:
                gps_avail += 1
            if rec.altitude_ellipsoidal is not None:
                alt_avail += 1
            if rec.drone_yaw is not None or rec.camera_yaw is not None:
                orient_avail += 1
            if rec.rtk_status in ("FIXED", "FLOAT") or rec.rtk_flag is not None:
                rtk_avail += 1

            if rec.camera_make and rec.camera_model and rec.focal_length_mm:
                cam_complete += 1
            else:
                cam_partial += 1

            q_stat = rec.quality_status or "GOOD"
            quality_breakdown[q_stat] = quality_breakdown.get(q_stat, 0) + 1

            for flag in flags:
                issues_tally[flag] = issues_tally.get(flag, 0) + 1

            completeness_sum += rec.metadata_completeness

        avg_comp = round(completeness_sum / total, 3) if total > 0 else 0.0

        # Readiness evaluation
        notes: List[str] = []
        is_ready = True

        if total < 3:
            notes.append("Insufficient images for 3D reconstruction (minimum 3 required).")
            is_ready = False
        if gps_avail < total * 0.8:
            notes.append(f"Only {gps_avail}/{total} images have GPS coordinates.")
        if cam_complete < total * 0.9:
            notes.append(f"{total - cam_complete} images lack complete camera focal length or model.")
        if invalid_cnt > 0:
            notes.append(f"{invalid_cnt} invalid/corrupt images detected.")
            is_ready = False

        if is_ready:
            notes.append(f"Dataset passed all core photogrammetry checks ({total} images ready).")

        return ValidationSummary(
            total_images=total,
            valid_images=valid_cnt,
            warning_images=warning_cnt,
            invalid_images=invalid_cnt,
            corrupt_images=corrupt_cnt,
            duplicate_images=duplicate_cnt,
            gps_available=gps_avail,
            gps_missing=total - gps_avail,
            altitude_available=alt_avail,
            altitude_missing=total - alt_avail,
            orientation_available=orient_avail,
            orientation_missing=total - orient_avail,
            rtk_available=rtk_avail,
            rtk_missing=total - rtk_avail,
            camera_metadata_complete=cam_complete,
            camera_metadata_partial=cam_partial,
            quality_breakdown=quality_breakdown,
            validation_issues=issues_tally,
            average_completeness=avg_comp,
            dataset_ready_for_reconstruction=is_ready,
            readiness_notes=notes,
        )

    def format_text_report(self, summary: ValidationSummary) -> str:
        """Formats the validation summary into human-readable text."""
        return f"""============================================================
DATASET VALIDATION & QUALITY REPORT
============================================================
TOTAL IMAGES: {summary.total_images}

Validation Status:
- Valid Images:          {summary.valid_images}
- Warning Images:        {summary.warning_images}
- Invalid Images:        {summary.invalid_images}
- Corrupted Images:      {summary.corrupt_images}
- Duplicate Images:      {summary.duplicate_images}

GPS Coverage:
- Available:             {summary.gps_available} ({summary.gps_available/summary.total_images*100:.1f}%)
- Missing:               {summary.gps_missing}

Altitude Coverage:
- Available:             {summary.altitude_available}
- Missing:               {summary.altitude_missing}

Orientation Coverage:
- Available:             {summary.orientation_available}
- Missing:               {summary.orientation_missing}

Survey / RTK Coverage:
- Available:             {summary.rtk_available}
- Missing:               {summary.rtk_missing}

Camera Telemetry:
- Complete:              {summary.camera_metadata_complete}
- Partial/Missing:       {summary.camera_metadata_partial}

Image Quality Classification:
- GOOD:                  {summary.quality_breakdown.get('GOOD', 0)}
- WARNING:               {summary.quality_breakdown.get('WARNING', 0)}
- BAD:                   {summary.quality_breakdown.get('BAD', 0)}

Average Completeness:    {summary.average_completeness * 100:.1f}%

Issues Detected:
{chr(10).join(f'  • {k}: {v}' for k, v in summary.validation_issues.items()) if summary.validation_issues else '  (None)'}

Readiness Assessment:
- Ready for 3D SfM:      {'YES - PASSED' if summary.dataset_ready_for_reconstruction else 'NO - ATTENTION REQUIRED'}
{chr(10).join(f'  • {n}' for n in summary.readiness_notes)}
============================================================
"""
