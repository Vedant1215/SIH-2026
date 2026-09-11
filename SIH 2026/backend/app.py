"""
FastAPI Application for SIH 2026 Drone Ingestion System.
Vercel-safe version: heavy reconstruction modules are loaded only when needed.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SIH 2026 — 3D ULPIN Drone Ingestion & Pre-Reconstruction System",
    description="Milestone 1: Automated Dataset Discovery, EXIF/RTK/GCP Normalization, Quality Validation, and Map Visualization",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy-loaded services
pipeline_service = None
reconstruction_engine = None


def get_pipeline_service():
    global pipeline_service

    if pipeline_service is None:
        from services.pipeline_service import PipelineService
        pipeline_service = PipelineService()

    return pipeline_service


def get_reconstruction_engine():
    global reconstruction_engine

    if reconstruction_engine is None:
        from reconstruction.engine import ReconstructionEngine
        reconstruction_engine = ReconstructionEngine()

    return reconstruction_engine


# Paths
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"
TEMPLATES_DIR = FRONTEND_DIR / "templates"

# Mount static assets
if STATIC_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="static",
    )


@app.on_event("startup")
def startup_event():
    """
    Keep startup lightweight for Vercel.
    Heavy pipeline is intentionally NOT started automatically.
    """
    logger.info("SIH 2026 application started.")
    logger.info("Heavy ingestion/reconstruction services will load only when required.")


# ============================================================
# Web UI
# ============================================================

@app.get("/", response_class=HTMLResponse)
def index():
    """Serves the main dashboard application."""
    index_path = TEMPLATES_DIR / "index.html"

    if not index_path.exists():
        return HTMLResponse(
            "<h1>SIH 2026 Frontend template not found.</h1>",
            status_code=404,
        )

    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ============================================================
# API Endpoints
# ============================================================

@app.get("/api/status")
def get_system_status():
    """Returns dataset configuration and pipeline status."""
    service = get_pipeline_service()

    return {
        "dataset_root": str(settings.dataset_root),
        "dataset_exists": settings.is_dataset_available(),
        "is_processing": service.is_processing,
        "processing_error": service.processing_error,
        "total_images_loaded": len(service.image_records),
        "dataset_ready": (
            service.validation_summary.dataset_ready_for_reconstruction
            if service.validation_summary
            else False
        ),
    }


@app.post("/api/pipeline/run")
def trigger_pipeline(force: bool = Query(default=True)):
    """Triggers or forces a pipeline run."""
    service = get_pipeline_service()

    if not settings.is_dataset_available():
        raise HTTPException(
            status_code=404,
            detail=f"Configured dataset path does not exist: {settings.dataset_root}",
        )

    success = service.run_pipeline(force_refresh=force)

    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed: {service.processing_error}",
        )

    return {
        "status": "success",
        "total_images": len(service.image_records),
        "message": "Dataset ingestion, validation, and thumbnail caching complete.",
    }


@app.get("/api/discovery")
def get_discovery_report():
    """Returns dataset discovery report."""
    service = get_pipeline_service()

    if not service.discovery_report:
        if settings.is_dataset_available():
            service.run_pipeline()
        else:
            raise HTTPException(
                status_code=404,
                detail="Dataset root not found",
            )

    if not service.discovery_report:
        raise HTTPException(
            status_code=404,
            detail="Discovery report not available",
        )

    return service.discovery_report


@app.get("/api/validation")
def get_validation_summary():
    """Returns dataset validation summary."""
    service = get_pipeline_service()

    if not service.validation_summary:
        if settings.is_dataset_available():
            service.run_pipeline()
        else:
            raise HTTPException(
                status_code=404,
                detail="Dataset root not found",
            )

    if not service.validation_summary:
        raise HTTPException(
            status_code=404,
            detail="Validation summary not available",
        )

    return service.validation_summary


@app.get("/api/images")
def get_images(
    gps_status: Optional[str] = Query(None),
    rtk_status: Optional[str] = Query(None),
    quality_status: Optional[str] = Query(None),
    validation_status: Optional[str] = Query(None),
    sort_by: str = Query("image_id"),
    sort_desc: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
):
    """Returns filtered and paginated image records."""
    service = get_pipeline_service()

    filtered = service.filter_records(
        gps_status=gps_status,
        rtk_status=rtk_status,
        quality_status=quality_status,
        validation_status=validation_status,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )

    total_matching = len(filtered)
    page_records = filtered[offset:offset + limit]

    return {
        "total_total": len(service.image_records),
        "total_filtered": total_matching,
        "offset": offset,
        "limit": limit,
        "records": page_records,
    }


@app.get("/api/images/{image_id}")
def get_image_details(image_id: str):
    """Returns metadata for one image."""
    service = get_pipeline_service()

    record = service.get_image(image_id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"Image {image_id} not found",
        )

    return record


@app.get("/api/images/{image_id}/full")
def get_original_image(image_id: str):
    """Streams original image."""
    service = get_pipeline_service()

    record = service.get_image(image_id)

    if not record or not Path(record.filepath).exists():
        raise HTTPException(
            status_code=404,
            detail=f"Image file not found for {image_id}",
        )

    return FileResponse(
        record.filepath,
        media_type="image/jpeg",
    )


@app.get("/api/thumbnails/{filename}")
def get_thumbnail(filename: str):
    """Serves cached thumbnail."""
    thumb_path = settings.thumbnails_dir / filename

    if not thumb_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Thumbnail {filename} not found",
        )

    return FileResponse(
        thumb_path,
        media_type="image/jpeg",
    )


@app.get("/api/map/geojson")
def get_map_geojson():
    """Returns GeoJSON map data."""
    service = get_pipeline_service()

    if not service.geojson_data:
        if settings.is_dataset_available():
            service.run_pipeline()
        else:
            raise HTTPException(
                status_code=404,
                detail="Dataset root not found",
            )

    if not service.geojson_data:
        raise HTTPException(
            status_code=404,
            detail="GeoJSON data not available",
        )

    return service.geojson_data


@app.post("/api/reconstruction/prepare")
def prepare_3d_reconstruction():
    """Prepares dataset for 3D reconstruction."""
    service = get_pipeline_service()

    if not service.image_records:
        service.run_pipeline()

    manifest = service.reconstruction_preparer.prepare_manifest(
        dataset_name=service.dataset_path.name,
        dataset_path=str(service.dataset_path),
        records=service.image_records,
        gcps=service.gcps,
        validation_summary=service.validation_summary,
    )

    service.reconstruction_manifest = manifest

    return {
        "status": (
            "ready"
            if manifest.ready_for_colmap
            else "review_required"
        ),
        "manifest": manifest,
        "message": (
            "DATASET READY FOR 3D RECONSTRUCTION"
            if manifest.ready_for_colmap
            else "Dataset requires review before photogrammetric reconstruction."
        ),
    }


@app.get("/api/reconstruction/manifest")
def download_reconstruction_manifest():
    """Downloads reconstruction manifest."""
    manifest_path = (
        settings.manifests_dir /
        "reconstruction_manifest.json"
    )

    if not manifest_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Reconstruction manifest has not been generated yet.",
        )

    return FileResponse(
        manifest_path,
        media_type="application/json",
        filename="reconstruction_manifest.json",
    )


# ============================================================
# Stage 2: Actual 3D Reconstruction
# ============================================================

@app.post("/api/reconstruction/start")
def start_reconstruction(
    force_restart: bool = Query(default=False),
):
    """Starts 3D reconstruction."""
    service = get_pipeline_service()
    engine = get_reconstruction_engine()

    if not service.image_records:
        service.run_pipeline()

    manifest_path = (
        settings.manifests_dir /
        "reconstruction_manifest.json"
    )

    if not manifest_path.exists():
        service.reconstruction_preparer.prepare_manifest(
            dataset_name=service.dataset_path.name,
            dataset_path=str(service.dataset_path),
            records=service.image_records,
            gcps=service.gcps,
            validation_summary=service.validation_summary,
        )

    images_dir = settings.dataset_root / "images"

    if not images_dir.exists():
        images_dir = settings.dataset_root

    success = engine.start_reconstruction_async(
        images_dir=images_dir,
        manifest_path=manifest_path,
        force_restart=force_restart,
    )

    if not success:
        current_state = engine.get_status()

        return {
            "status": "already_running",
            "message": "Reconstruction pipeline is already executing.",
            "state": current_state,
        }

    return {
        "status": "started",
        "message": "3D reconstruction pipeline started in background.",
        "state": engine.get_status(),
    }


@app.get("/api/reconstruction/status")
def get_reconstruction_status():
    """Returns reconstruction status."""
    engine = get_reconstruction_engine()
    return engine.get_status()


@app.get("/api/reconstruction/logs")
def get_reconstruction_logs(
    limit: int = Query(default=100),
):
    """Returns reconstruction logs."""
    engine = get_reconstruction_engine()

    state = engine.get_status()
    logs = state.get("logs", [])

    return {
        "status": state.get("status"),
        "current_stage": state.get("current_stage_name"),
        "logs": logs[-limit:],
    }


@app.post("/api/reconstruction/cancel")
def cancel_reconstruction():
    """Cancels reconstruction."""
    engine = get_reconstruction_engine()

    engine.cancel()

    return {
        "status": "cancelling",
        "message": "Cancellation requested.",
    }


@app.get("/api/reconstruction/report")
def get_reconstruction_report():
    """Returns reconstruction report."""
    report_file = (
        settings.output_dir /
        "reconstruction" /
        "reports" /
        "sfm_report.json"
    )

    if not report_file.exists():
        raise HTTPException(
            status_code=404,
            detail="SfM report not generated yet. Run reconstruction first.",
        )

    with open(report_file, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/reconstruction/model")
@app.get("/api/reconstruction/model/glb")
def get_textured_model_glb():
    """Streams final GLB model."""
    glb_path = (
        settings.output_dir /
        "reconstruction" /
        "textured" /
        "model.glb"
    )

    if not glb_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Textured 3D model (model.glb) not generated yet.",
        )

    return FileResponse(
        glb_path,
        media_type="model/gltf-binary",
        filename="model.glb",
    )


@app.get("/api/reconstruction/sparse")
@app.get("/api/reconstruction/sparse/ply")
def get_sparse_point_cloud():
    """Streams sparse point cloud."""
    sparse_ply = (
        settings.output_dir /
        "reconstruction" /
        "sparse" /
        "sparse.ply"
    )

    if not sparse_ply.exists():
        raise HTTPException(
            status_code=404,
            detail="Sparse point cloud (sparse.ply) not generated yet.",
        )

    return FileResponse(
        sparse_ply,
        media_type="application/octet-stream",
        filename="sparse.ply",
    )


@app.get("/api/reconstruction/dense")
@app.get("/api/reconstruction/dense/ply")
def get_dense_point_cloud():
    """Streams dense point cloud."""
    dense_ply = (
        settings.output_dir /
        "reconstruction" /
        "dense" /
        "fused.ply"
    )

    if not dense_ply.exists():
        raise HTTPException(
            status_code=404,
            detail="Dense point cloud (fused.ply) not generated yet.",
        )

    return FileResponse(
        dense_ply,
        media_type="application/octet-stream",
        filename="fused.ply",
    )


@app.get("/api/reconstruction/mesh")
def get_surface_mesh():
    """Streams 3D surface mesh."""
    mesh_obj = (
        settings.output_dir /
        "reconstruction" /
        "mesh" /
        "model.obj"
    )

    if mesh_obj.exists():
        return FileResponse(
            mesh_obj,
            media_type="text/plain",
            filename="model.obj",
        )

    mesh_ply = (
        settings.output_dir /
        "reconstruction" /
        "mesh" /
        "model.ply"
    )

    if mesh_ply.exists():
        return FileResponse(
            mesh_ply,
            media_type="application/octet-stream",
            filename="model.ply",
        )

    raise HTTPException(
        status_code=404,
        detail="3D mesh not generated yet.",
    )
