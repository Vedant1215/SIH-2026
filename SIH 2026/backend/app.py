"""
FastAPI Application for SIH 2026 Drone Ingestion System.
Provides RESTful APIs for dataset discovery, image metadata, quality diagnostics,
GeoJSON map layers, cached thumbnail streaming, and 3D reconstruction readiness.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from services.pipeline_service import PipelineService

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

# Pipeline Service Singleton
pipeline_service = PipelineService()

# Paths
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"
TEMPLATES_DIR = FRONTEND_DIR / "templates"

# Mount static assets if they exist
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def startup_event():
    """Run pipeline on startup if dataset exists."""
    logger.info("Initializing SIH 2026 Ingestion System...")
    if settings.is_dataset_available():
        # Trigger pipeline in background or synchronously
        try:
            pipeline_service.run_pipeline(force_refresh=False)
        except Exception as e:
            logger.error("Startup pipeline run failed: %s", e)
    else:
        logger.warning("Dataset root does not exist: %s", settings.dataset_root)


# ============================================================
# Web UI Endpoints
# ============================================================

@app.get("/", response_class=HTMLResponse)
def index():
    """Serves the main dashboard application."""
    index_path = TEMPLATES_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>SIH 2026 Frontend template not found. Please build frontend.</h1>", status_code=404)
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ============================================================
# API Endpoints
# ============================================================

@app.get("/api/status")
def get_system_status():
    """Returns dataset configuration status and pipeline processing state."""
    return {
        "dataset_root": str(settings.dataset_root),
        "dataset_exists": settings.is_dataset_available(),
        "is_processing": pipeline_service.is_processing,
        "processing_error": pipeline_service.processing_error,
        "total_images_loaded": len(pipeline_service.image_records),
        "dataset_ready": (
            pipeline_service.validation_summary.dataset_ready_for_reconstruction
            if pipeline_service.validation_summary
            else False
        ),
    }


@app.post("/api/pipeline/run")
def trigger_pipeline(force: bool = Query(default=True)):
    """Triggers or forces a re-run of the ingestion pipeline."""
    if not settings.is_dataset_available():
        raise HTTPException(
            status_code=404,
            detail=f"Configured dataset path does not exist: {settings.dataset_root}",
        )
    success = pipeline_service.run_pipeline(force_refresh=force)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed: {pipeline_service.processing_error}",
        )
    return {
        "status": "success",
        "total_images": len(pipeline_service.image_records),
        "message": "Dataset ingestion, validation, and thumbnail caching complete.",
    }


@app.get("/api/discovery")
def get_discovery_report():
    """Returns the dataset discovery report."""
    if not pipeline_service.discovery_report:
        if settings.is_dataset_available():
            pipeline_service.run_pipeline()
        else:
            raise HTTPException(status_code=404, detail="Dataset root not found")

    if not pipeline_service.discovery_report:
        raise HTTPException(status_code=404, detail="Discovery report not available")
    return pipeline_service.discovery_report


@app.get("/api/validation")
def get_validation_summary():
    """Returns the dataset validation summary."""
    if not pipeline_service.validation_summary:
        if settings.is_dataset_available():
            pipeline_service.run_pipeline()
        else:
            raise HTTPException(status_code=404, detail="Dataset root not found")

    if not pipeline_service.validation_summary:
        raise HTTPException(status_code=404, detail="Validation summary not available")
    return pipeline_service.validation_summary


@app.get("/api/images")
def get_images(
    gps_status: Optional[str] = Query(None, description="available | missing"),
    rtk_status: Optional[str] = Query(None, description="FIXED | FLOAT | UNKNOWN"),
    quality_status: Optional[str] = Query(None, description="GOOD | WARNING | BAD"),
    validation_status: Optional[str] = Query(None, description="VALID | WARNING | INVALID"),
    sort_by: str = Query("image_id", description="Field to sort by"),
    sort_desc: bool = Query(False, description="Sort descending"),
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
):
    """Returns filtered and paginated list of ImageRecords."""
    filtered = pipeline_service.filter_records(
        gps_status=gps_status,
        rtk_status=rtk_status,
        quality_status=quality_status,
        validation_status=validation_status,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )
    total_matching = len(filtered)
    page_records = filtered[offset : offset + limit]

    return {
        "total_total": len(pipeline_service.image_records),
        "total_filtered": total_matching,
        "offset": offset,
        "limit": limit,
        "records": page_records,
    }


@app.get("/api/images/{image_id}")
def get_image_details(image_id: str):
    """Returns full metadata for a single image."""
    record = pipeline_service.get_image(image_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Image {image_id} not found")
    return record


@app.get("/api/images/{image_id}/full")
def get_original_image(image_id: str):
    """Streams original image file directly from dataset (read-only)."""
    record = pipeline_service.get_image(image_id)
    if not record or not Path(record.filepath).exists():
        raise HTTPException(status_code=404, detail=f"Image file not found for {image_id}")
    return FileResponse(record.filepath, media_type="image/jpeg")


@app.get("/api/thumbnails/{filename}")
def get_thumbnail(filename: str):
    """Serves a cached image thumbnail from output/thumbnails."""
    thumb_path = settings.thumbnails_dir / filename
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail=f"Thumbnail {filename} not found")
    return FileResponse(thumb_path, media_type="image/jpeg")


@app.get("/api/map/geojson")
def get_map_geojson():
    """Returns GeoJSON features (points, trajectory line, GCPs, bounds)."""
    if not pipeline_service.geojson_data:
        if settings.is_dataset_available():
            pipeline_service.run_pipeline()
        else:
            raise HTTPException(status_code=404, detail="Dataset root not found")

    if not pipeline_service.geojson_data:
        raise HTTPException(status_code=404, detail="GeoJSON data not available")
    return pipeline_service.geojson_data


@app.post("/api/reconstruction/prepare")
def prepare_3d_reconstruction():
    """
    Task 9 endpoint: Validates dataset photogrammetry readiness,
    generates reconstruction manifest, and reports readiness for COLMAP/SfM.
    """
    if not pipeline_service.image_records:
        pipeline_service.run_pipeline()

    manifest = pipeline_service.reconstruction_preparer.prepare_manifest(
        dataset_name=pipeline_service.dataset_path.name,
        dataset_path=str(pipeline_service.dataset_path),
        records=pipeline_service.image_records,
        gcps=pipeline_service.gcps,
        validation_summary=pipeline_service.validation_summary,
    )
    pipeline_service.reconstruction_manifest = manifest

    return {
        "status": "ready" if manifest.ready_for_colmap else "review_required",
        "manifest": manifest,
        "message": (
            "DATASET READY FOR 3D RECONSTRUCTION"
            if manifest.ready_for_colmap
            else "Dataset requires review before photogrammetric reconstruction."
        ),
    }


@app.get("/api/reconstruction/manifest")
def download_reconstruction_manifest():
    """Downloads the generated 3D reconstruction manifest JSON."""
    manifest_path = settings.manifests_dir / "reconstruction_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Reconstruction manifest has not been generated yet.")
    return FileResponse(
        manifest_path,
        media_type="application/json",
        filename="reconstruction_manifest.json",
    )


# ============================================================
# Stage 2: Actual 3D Photogrammetry Reconstruction Endpoints
# ============================================================
from reconstruction.engine import ReconstructionEngine

reconstruction_engine = ReconstructionEngine()


@app.post("/api/reconstruction/start")
def start_reconstruction(force_restart: bool = Query(default=False)):
    """
    Triggers the 10-stage photogrammetric 3D reconstruction pipeline in background:
    Feature Extraction -> Spatial Matching -> Sparse SfM -> Georeferencing ->
    Undistortion -> PatchMatch Stereo -> Fusion -> Poisson Meshing -> GLB Texturing.
    """
    # Ensure dataset is ready
    if not pipeline_service.image_records:
        pipeline_service.run_pipeline()

    manifest_path = settings.manifests_dir / "reconstruction_manifest.json"
    if not manifest_path.exists():
        pipeline_service.reconstruction_preparer.prepare_manifest(
            dataset_name=pipeline_service.dataset_path.name,
            dataset_path=str(pipeline_service.dataset_path),
            records=pipeline_service.image_records,
            gcps=pipeline_service.gcps,
            validation_summary=pipeline_service.validation_summary,
        )

    images_dir = settings.dataset_root / "images"
    if not images_dir.exists():
        # Fallback to dataset root if images folder not separate
        images_dir = settings.dataset_root

    success = reconstruction_engine.start_reconstruction_async(
        images_dir=images_dir,
        manifest_path=manifest_path,
        force_restart=force_restart,
    )

    if not success:
        current_state = reconstruction_engine.get_status()
        return {
            "status": "already_running",
            "message": "Reconstruction pipeline is already executing.",
            "state": current_state,
        }

    return {
        "status": "started",
        "message": "3D reconstruction pipeline started in background.",
        "state": reconstruction_engine.get_status(),
    }


@app.get("/api/reconstruction/status")
def get_reconstruction_status():
    """Returns real-time 10-stage progress, statistics, and artifact paths."""
    return reconstruction_engine.get_status()


@app.get("/api/reconstruction/logs")
def get_reconstruction_logs(limit: int = Query(default=100)):
    """Returns recent log messages from the reconstruction pipeline."""
    state = reconstruction_engine.get_status()
    logs = state.get("logs", [])
    return {
        "status": state.get("status"),
        "current_stage": state.get("current_stage_name"),
        "logs": logs[-limit:],
    }


@app.post("/api/reconstruction/cancel")
def cancel_reconstruction():
    """Cancels a running photogrammetry reconstruction."""
    reconstruction_engine.cancel()
    return {"status": "cancelling", "message": "Cancellation requested."}


@app.get("/api/reconstruction/report")
def get_reconstruction_report():
    """Returns SfM photogrammetry analysis report JSON."""
    report_file = settings.output_dir / "reconstruction" / "reports" / "sfm_report.json"
    if not report_file.exists():
        raise HTTPException(status_code=404, detail="SfM report not generated yet. Run reconstruction first.")
    with open(report_file, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/reconstruction/model")
@app.get("/api/reconstruction/model/glb")
def get_textured_model_glb():
    """Streams the final textured 3D model (.glb) for the Three.js WebGL viewer."""
    glb_path = settings.output_dir / "reconstruction" / "textured" / "model.glb"
    if not glb_path.exists():
        raise HTTPException(status_code=404, detail="Textured 3D model (model.glb) not generated yet.")
    return FileResponse(glb_path, media_type="model/gltf-binary", filename="model.glb")


@app.get("/api/reconstruction/sparse")
@app.get("/api/reconstruction/sparse/ply")
def get_sparse_point_cloud():
    """Streams the sparse 3D point cloud (.ply)."""
    sparse_ply = settings.output_dir / "reconstruction" / "sparse" / "sparse.ply"
    if not sparse_ply.exists():
        raise HTTPException(status_code=404, detail="Sparse point cloud (sparse.ply) not generated yet.")
    return FileResponse(sparse_ply, media_type="application/octet-stream", filename="sparse.ply")


@app.get("/api/reconstruction/dense")
@app.get("/api/reconstruction/dense/ply")
def get_dense_point_cloud():
    """Streams the fused dense 3D point cloud (.ply)."""
    dense_ply = settings.output_dir / "reconstruction" / "dense" / "fused.ply"
    if not dense_ply.exists():
        raise HTTPException(status_code=404, detail="Dense point cloud (fused.ply) not generated yet.")
    return FileResponse(dense_ply, media_type="application/octet-stream", filename="fused.ply")


@app.get("/api/reconstruction/mesh")
def get_surface_mesh():
    """Streams the 3D surface mesh (.ply or .obj)."""
    mesh_obj = settings.output_dir / "reconstruction" / "mesh" / "model.obj"
    if mesh_obj.exists():
        return FileResponse(mesh_obj, media_type="text/plain", filename="model.obj")
    mesh_ply = settings.output_dir / "reconstruction" / "mesh" / "model.ply"
    if mesh_ply.exists():
        return FileResponse(mesh_ply, media_type="application/octet-stream", filename="model.ply")
    raise HTTPException(status_code=404, detail="3D mesh not generated yet.")

