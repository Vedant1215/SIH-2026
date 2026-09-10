"""
Main Entrypoint for SIH 2026 Problem Statement 26011.
"3D ULPIN Generation and Vertical Property Mapping System"
Milestone 1: Drone Ingestion, Metadata Normalization, Validation, & Visualization.

Usage:
  python main.py                 # Starts Web Dashboard & API server
  python main.py --cli           # Headless discovery, validation & manifest generation
  python main.py --dataset PATH  # Override dataset path
"""

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

from backend.config import settings
from services.pipeline_service import PipelineService

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SIH2026")


def run_cli_pipeline(dataset_path: Path):
    """Executes headless dataset ingestion and prints reports."""
    logger.info("Starting headless CLI ingestion pipeline for: %s", dataset_path)
    pipeline = PipelineService(dataset_path=dataset_path)
    success = pipeline.run_pipeline(force_refresh=True)

    if not success:
        logger.error("Pipeline failed: %s", pipeline.processing_error)
        sys.exit(1)

    # Print Discovery Report
    if pipeline.discovery_report:
        print("\n" + pipeline.discovery_service.format_text_report(pipeline.discovery_report))

    # Print Validation Report
    if pipeline.validation_summary:
        print("\n" + pipeline.validator.format_text_report(pipeline.validation_summary))

    # Print Reconstruction Manifest Summary
    if pipeline.reconstruction_manifest:
        m = pipeline.reconstruction_manifest
        print("============================================================")
        print("3D RECONSTRUCTION PREPARATION SUMMARY")
        print("============================================================")
        print(f"Total Images:               {m.total_images}")
        print(f"Valid for Reconstruction:   {m.valid_reconstruction_images}")
        print(f"Camera Make/Model:          {m.camera_profile.get('make')} {m.camera_profile.get('model')}")
        print(f"Focal Length:               {m.camera_profile.get('focal_length_mm')} mm")
        print(f"RTK Used:                   {m.rtk_used}")
        print(f"GCPs Available:             {m.gcp_count}")
        print(f"Readiness Checklist:        {m.readiness_checklist}")
        print("------------------------------------------------------------")
        if m.ready_for_colmap:
            print(">>> [ DATASET READY FOR 3D RECONSTRUCTION ] <<<")
        else:
            print(">>> [ REVIEW REQUIRED BEFORE 3D RECONSTRUCTION ] <<<")
        print("============================================================\n")


def run_web_server(host: str, port: int):
    """Starts FastAPI application with Uvicorn."""
    logger.info("============================================================")
    logger.info("SIH 2026 — 3D ULPIN Drone Ingestion & Mapping System")
    logger.info("============================================================")
    logger.info("Configured DATASET_ROOT: %s", settings.dataset_root)
    logger.info("Configured OUTPUT_DIR:   %s", settings.output_dir)
    logger.info("Starting Web Dashboard on: http://%s:%d", host, port)
    logger.info("API Documentation:        http://%s:%d/docs", host, port)
    logger.info("============================================================")

    uvicorn.run(
        "backend.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


def main():
    parser = argparse.ArgumentParser(description="SIH 2026 Drone Ingestion & Visualization System")
    parser.add_argument("--cli", action="store_true", help="Run in headless CLI mode and generate reports")
    parser.add_argument("--dataset", type=str, default=None, help="Path to drone dataset directory")
    parser.add_argument("--host", type=str, default=settings.host, help="Host to bind server")
    parser.add_argument("--port", type=int, default=settings.port, help="Port to bind server")
    args = parser.parse_args()

    dataset_path = Path(args.dataset) if args.dataset else settings.dataset_root

    if not dataset_path.exists():
        logger.error("Configured dataset path does not exist: %s", dataset_path)
        logger.error("Please configure DATASET_ROOT in .env or pass --dataset PATH")
        sys.exit(1)

    if args.cli:
        run_cli_pipeline(dataset_path)
    else:
        run_web_server(args.host, args.port)


if __name__ == "__main__":
    main()
