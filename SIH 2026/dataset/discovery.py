"""
Dataset Discovery Service for SIH 2026 Drone Ingestion System.
Recursively scans dataset directory for image files, CSV files,
telemetry files (MRK/OBS), GCP definitions, and metadata specifications.
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

from metadata.models import DatasetDiscoveryReport

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".dng", ".bmp"}
CSV_EXTENSIONS: Set[str] = {".csv", ".tsv"}
METADATA_EXTENSIONS: Set[str] = {".txt", ".json", ".xml", ".mrk", ".obs", ".yaml", ".yml", ".pos", ".nav"}


class DatasetDiscoveryService:
    """Discovers all images and metadata files in a given dataset directory."""

    def __init__(self, dataset_path: Path):
        self.dataset_path = Path(dataset_path)

    def scan(self) -> Tuple[List[Path], List[Path], List[Path], List[Path]]:
        """
        Recursively discovers all image files, CSV files, metadata files, and other files.
        Returns (image_paths, csv_paths, metadata_paths, other_paths).
        """
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Configured dataset path does not exist: {self.dataset_path}")
        if not self.dataset_path.is_dir():
            raise NotADirectoryError(f"Configured dataset path is not a directory: {self.dataset_path}")

        image_files: List[Path] = []
        csv_files: List[Path] = []
        metadata_files: List[Path] = []
        other_files: List[Path] = []

        for root, dirs, files in os.walk(self.dataset_path):
            # Sort files for deterministic ordering
            for file_name in sorted(files):
                file_path = Path(root) / file_name
                ext = file_path.suffix.lower()

                if ext in IMAGE_EXTENSIONS:
                    image_files.append(file_path)
                elif ext in CSV_EXTENSIONS:
                    csv_files.append(file_path)
                elif ext in METADATA_EXTENSIONS:
                    metadata_files.append(file_path)
                else:
                    other_files.append(file_path)

        logger.info(
            "Scan complete: %d images, %d CSVs, %d metadata files, %d other files",
            len(image_files),
            len(csv_files),
            len(metadata_files),
            len(other_files),
        )
        return image_files, csv_files, metadata_files, other_files

    def generate_report(
        self,
        image_files: List[Path],
        csv_files: List[Path],
        metadata_files: List[Path],
        other_files: List[Path],
        exif_available_count: int = 0,
        exif_missing_count: int = 0,
        gps_available_count: int = 0,
        gps_missing_count: int = 0,
        rtk_status: str = "Available",
        gcp_status: str = "Available",
    ) -> DatasetDiscoveryReport:
        """Constructs a structured DatasetDiscoveryReport."""
        image_formats: Dict[str, int] = {}
        for img in image_files:
            fmt = img.suffix.upper().lstrip(".")
            image_formats[fmt] = image_formats.get(fmt, 0) + 1

        dirs_found = sorted(
            list(
                {
                    str(p.parent.relative_to(self.dataset_path))
                    for p in (image_files + csv_files + metadata_files)
                }
            )
        )

        report = DatasetDiscoveryReport(
            dataset_name=self.dataset_path.name,
            dataset_path=str(self.dataset_path),
            discovered_at=datetime.now(timezone.utc).isoformat(),
            total_files=len(image_files) + len(csv_files) + len(metadata_files) + len(other_files),
            image_count=len(image_files),
            image_formats=image_formats,
            csv_count=len(csv_files),
            csv_files=[str(p.relative_to(self.dataset_path)) for p in csv_files],
            metadata_files=[str(p.relative_to(self.dataset_path)) for p in metadata_files],
            other_files=[str(p.relative_to(self.dataset_path)) for p in other_files],
            directories_found=dirs_found,
            exif_available_count=exif_available_count,
            exif_missing_count=exif_missing_count,
            gps_available_count=gps_available_count,
            gps_missing_count=gps_missing_count,
            rtk_status_summary=rtk_status,
            gcp_status_summary=gcp_status,
        )
        return report

    def format_text_report(self, report: DatasetDiscoveryReport) -> str:
        """Formats the discovery report as human-readable markdown text."""
        return f"""============================================================
DATASET DISCOVERY REPORT: {report.dataset_name}
============================================================
Dataset Path: {report.dataset_path}
Timestamp:    {report.discovered_at}

Summary:
- Total Files Found:     {report.total_files}
- Total Images:          {report.image_count} ({', '.join(f'{k}: {v}' for k, v in report.image_formats.items())})
- CSV Files:             {report.csv_count}
- Metadata/Telemetry:    {len(report.metadata_files)}

Metadata Files:
{chr(10).join(f'  • {f}' for f in report.metadata_files) if report.metadata_files else '  (None)'}

CSV Files:
{chr(10).join(f'  • {f}' for f in report.csv_files) if report.csv_files else '  (None)'}

Images with EXIF:        {report.exif_available_count}
Images without EXIF:     {report.exif_missing_count}

Images with GPS:         {report.gps_available_count}
Images without GPS:      {report.gps_missing_count}

RTK Information:         {report.rtk_status_summary}
GCP Information:         {report.gcp_status_summary}
============================================================
"""
