"""
Pipeline Orchestrator for SIH 2026 Drone Ingestion System.
Coordinates Discovery, EXIF Extraction, CSV/MRK Matching, GCP Parsing,
Normalization, Validation, Quality Assessment, and 3D Reconstruction Manifest generation.
Maintains in-memory thread-safe state for fast API responses and reports export.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import settings
from dataset.discovery import DatasetDiscoveryService
from metadata.exif_extractor import ExifExtractor
from metadata.csv_parser import CsvMetadataParser, CsvMetadataRecord
from metadata.gcp_parser import GCPParser
from metadata.normalizer import MetadataNormalizer
from metadata.models import (
    ImageRecord,
    GCPPoint,
    DatasetDiscoveryReport,
    ValidationSummary,
    ReconstructionManifest,
)
from validation.validator import DatasetValidator
from validation.quality import ImageQualityAnalyzer
from map.geojson_builder import GeoJsonBuilder
from reconstruction.preparer import ReconstructionPreparer

logger = logging.getLogger(__name__)


class PipelineService:
    """Master service controlling the ingestion, analysis, and reporting workflow."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(PipelineService, cls).__new__(cls)
        return cls._instance

    def __init__(self, dataset_path: Optional[Path] = None, output_dir: Optional[Path] = None):
        # Initialize only once
        if getattr(self, "_initialized", False):
            return

        self.dataset_path = Path(dataset_path) if dataset_path else settings.dataset_root
        self.output_dir = Path(output_dir) if output_dir else settings.output_dir

        self.discovery_service = DatasetDiscoveryService(self.dataset_path)
        self.exif_extractor = ExifExtractor()
        self.csv_parser = CsvMetadataParser()
        self.gcp_parser = GCPParser()
        self.normalizer = MetadataNormalizer(self.dataset_path)
        self.validator = DatasetValidator()
        self.quality_analyzer = ImageQualityAnalyzer(thumbnails_dir=settings.thumbnails_dir)
        self.geojson_builder = GeoJsonBuilder()
        self.reconstruction_preparer = ReconstructionPreparer(manifests_dir=settings.manifests_dir)

        # In-memory cached state
        self.image_records: List[ImageRecord] = []
        self.image_records_map: Dict[str, ImageRecord] = {}
        self.gcps: List[GCPPoint] = []
        self.discovery_report: Optional[DatasetDiscoveryReport] = None
        self.validation_summary: Optional[ValidationSummary] = None
        self.reconstruction_manifest: Optional[ReconstructionManifest] = None
        self.geojson_data: Optional[Dict[str, Any]] = None
        self.is_processing: bool = False
        self.processing_error: Optional[str] = None

        self._initialized = True

    def run_pipeline(self, force_refresh: bool = False) -> bool:
        """
        Executes complete ingestion and validation pipeline.
        Returns True if successful, False otherwise.
        """
        with self._lock:
            if self.image_records and not force_refresh:
                logger.info("Pipeline already run; returning cached state.")
                return True

            self.is_processing = True
            self.processing_error = None

        try:
            logger.info("Starting drone dataset ingestion from %s", self.dataset_path)
            if not self.dataset_path.exists():
                raise FileNotFoundError(f"Configured dataset path does not exist: {self.dataset_path}")

            # 1. Discovery
            image_files, csv_files, metadata_files, other_files = self.discovery_service.scan()

            # 2. GCP Parsing
            for f in csv_files + metadata_files:
                if "gcp" in f.name.lower() or "latlon" in f.name.lower():
                    if f.suffix.lower() in (".csv", ".tsv"):
                        self.gcp_parser.parse_gcp_csv(f)
                    elif f.suffix.lower() == ".txt":
                        self.gcp_parser.parse_gcp_list(f)

            self.gcps = list(self.gcp_parser.points.values())

            # 3. CSV & MRK Telemetry Parsing
            matched_telemetry: Dict[str, CsvMetadataRecord] = {}
            for f in metadata_files:
                if f.suffix.lower() == ".mrk":
                    mrk_records = self.csv_parser.parse_mrk_file(f)
                    matched_telemetry.update(mrk_records)

            for f in csv_files:
                if "gcp" not in f.name.lower() and "latlon" not in f.name.lower():
                    rows = self.csv_parser.parse_csv_file(f)
                    for img_p in image_files:
                        matched = self.csv_parser.match_image_to_csv(
                            img_p.name, None, rows, f.name
                        )
                        if matched:
                            matched_telemetry[img_p.name] = matched
                            matched_telemetry[img_p.stem] = matched

            # 4. EXIF Extraction (Batch)
            exif_map = self.exif_extractor.extract_batch(image_files)

            # 5. Normalization
            records: List[ImageRecord] = []
            for img_p in image_files:
                exif_data = exif_map.get(img_p.name)
                telemetry = matched_telemetry.get(img_p.name) or matched_telemetry.get(img_p.stem)
                gcp_links = self.gcp_parser.get_gcps_for_image(img_p.name)

                record = self.normalizer.normalize(
                    image_path=img_p,
                    exif_data=exif_data,
                    csv_record=telemetry,
                    associated_gcps=gcp_links,
                )
                records.append(record)

            # 6. Quality Analysis (Multithreaded OpenCV)
            records = self.quality_analyzer.analyze_batch(records)

            # 7. Validation & Aggregation
            validation_summary = self.validator.validate_dataset(records)

            # 8. Discovery Report Generation
            exif_avail = sum(1 for r in records if "EXIF" in r.metadata_sources)
            gps_avail = sum(1 for r in records if r.latitude is not None and r.longitude is not None)
            rtk_avail = sum(1 for r in records if r.rtk_status in ("FIXED", "FLOAT") or r.rtk_flag is not None)

            rtk_summary_str = "Available (Fixed RTK)" if rtk_avail == len(records) and rtk_avail > 0 else (
                "Partial" if rtk_avail > 0 else "Not Available"
            )
            gcp_summary_str = f"Available ({len(self.gcps)} GCPs)" if self.gcps else "Not Available"

            discovery_report = self.discovery_service.generate_report(
                image_files=image_files,
                csv_files=csv_files,
                metadata_files=metadata_files,
                other_files=other_files,
                exif_available_count=exif_avail,
                exif_missing_count=len(records) - exif_avail,
                gps_available_count=gps_avail,
                gps_missing_count=len(records) - gps_avail,
                rtk_status=rtk_summary_str,
                gcp_status=gcp_summary_str,
            )

            # 9. Reconstruction Manifest Preparation
            manifest = self.reconstruction_preparer.prepare_manifest(
                dataset_name=self.dataset_path.name,
                dataset_path=str(self.dataset_path),
                records=records,
                gcps=self.gcps,
                validation_summary=validation_summary,
            )

            # 10. GeoJSON Construction
            geojson_data = self.geojson_builder.build_features(records, self.gcps)

            # 11. Save Reports to Output Directory
            self._save_reports(discovery_report, validation_summary)

            # Update in-memory state
            with self._lock:
                self.image_records = records
                self.image_records_map = {r.image_id: r for r in records}
                self.discovery_report = discovery_report
                self.validation_summary = validation_summary
                self.reconstruction_manifest = manifest
                self.geojson_data = geojson_data
                self.is_processing = False

            logger.info("Pipeline completed successfully for %d images", len(records))
            return True

        except Exception as e:
            logger.error("Pipeline failure: %s", e, exc_info=True)
            with self._lock:
                self.processing_error = str(e)
                self.is_processing = False
            return False

    def _save_reports(
        self,
        discovery: DatasetDiscoveryReport,
        validation: ValidationSummary,
    ) -> None:
        """Writes JSON and Markdown reports to settings.reports_dir."""
        # Discovery Reports
        disc_json = settings.reports_dir / "discovery_report.json"
        with open(disc_json, "w", encoding="utf-8") as f:
            json.dump(discovery.model_dump(), f, indent=2)

        disc_md = settings.reports_dir / "discovery_report.md"
        with open(disc_md, "w", encoding="utf-8") as f:
            f.write(self.discovery_service.format_text_report(discovery))

        # Validation Reports
        val_json = settings.reports_dir / "validation_report.json"
        with open(val_json, "w", encoding="utf-8") as f:
            json.dump(validation.model_dump(), f, indent=2)

        val_md = settings.reports_dir / "validation_report.md"
        with open(val_md, "w", encoding="utf-8") as f:
            f.write(self.validator.format_text_report(validation))

        logger.info("Saved discovery and validation reports to %s", settings.reports_dir)

    def get_image(self, image_id: str) -> Optional[ImageRecord]:
        """Lookup single image record by stem ID or filename."""
        clean_id = Path(image_id).stem
        return self.image_records_map.get(clean_id)

    def filter_records(
        self,
        gps_status: Optional[str] = None,
        rtk_status: Optional[str] = None,
        quality_status: Optional[str] = None,
        validation_status: Optional[str] = None,
        sort_by: str = "image_id",
        sort_desc: bool = False,
    ) -> List[ImageRecord]:
        """Filters and sorts records for the gallery view."""
        res = self.image_records

        if gps_status == "available":
            res = [r for r in res if r.latitude is not None and r.longitude is not None]
        elif gps_status == "missing":
            res = [r for r in res if r.latitude is None or r.longitude is None]

        if rtk_status:
            res = [r for r in res if r.rtk_status.upper() == rtk_status.upper()]

        if quality_status:
            res = [r for r in res if r.quality_status.upper() == quality_status.upper()]

        if validation_status:
            res = [r for r in res if r.validation_status.upper() == validation_status.upper()]

        # Sorting
        def sort_key(rec: ImageRecord):
            val = getattr(rec, sort_by, None)
            if val is None:
                return "" if isinstance(sort_by, str) else -999999
            return val

        try:
            res = sorted(res, key=sort_key, reverse=sort_desc)
        except Exception:
            pass

        return res
