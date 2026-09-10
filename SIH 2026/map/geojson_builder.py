"""
GeoJSON Builder for SIH 2026 Drone Ingestion System.
Transforms normalized ImageRecords and GCP points into standard GeoJSON structures.
Provides image markers, flight trajectory polyline, heading vectors, and GCP features.
"""

import math
from typing import Any, Dict, List, Optional
from metadata.models import ImageRecord, GCPPoint


class GeoJsonBuilder:
    """Constructs GeoJSON feature collections for geospatial drone flight visualization."""

    def build_features(
        self,
        records: List[ImageRecord],
        gcps: Optional[List[GCPPoint]] = None,
    ) -> Dict[str, Any]:
        """
        Builds a comprehensive GeoJSON structure containing:
        - Image camera points
        - Drone trajectory flight path (LineString)
        - Ground Control Points (GCPs)
        - Dataset bounding box and flight center coordinates
        """
        image_features: List[Dict[str, Any]] = []
        trajectory_coords: List[List[float]] = []

        valid_lats: List[float] = []
        valid_lons: List[float] = []

        # Sort records by timestamp or filename for continuous trajectory
        sorted_records = sorted(
            records,
            key=lambda r: (r.timestamp or "", r.filename),
        )

        for rec in sorted_records:
            if rec.latitude is None or rec.longitude is None:
                continue

            lat = rec.latitude
            lon = rec.longitude
            alt = rec.altitude_ellipsoidal or 0.0

            valid_lats.append(lat)
            valid_lons.append(lon)
            trajectory_coords.append([lon, lat, alt])

            # Calculate camera heading: prefer gimbal yaw, fallback to flight yaw
            heading = rec.camera_yaw if rec.camera_yaw is not None else rec.drone_yaw
            # Normalize heading to 0 - 360
            heading_deg = (heading % 360.0 + 360.0) % 360.0 if heading is not None else None

            # Construct Point feature
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat, alt],
                },
                "properties": {
                    "image_id": rec.image_id,
                    "filename": rec.filename,
                    "timestamp": rec.timestamp,
                    "latitude": lat,
                    "longitude": lon,
                    "altitude_ellipsoidal": rec.altitude_ellipsoidal,
                    "altitude_relative": rec.altitude_relative,
                    "heading": heading_deg,
                    "drone_yaw": rec.drone_yaw,
                    "drone_pitch": rec.drone_pitch,
                    "drone_roll": rec.drone_roll,
                    "camera_yaw": rec.camera_yaw,
                    "camera_pitch": rec.camera_pitch,
                    "camera_roll": rec.camera_roll,
                    "rtk_status": rec.rtk_status,
                    "rtk_accuracy_h": rec.gps_accuracy_h,
                    "rtk_accuracy_v": rec.gps_accuracy_v,
                    "camera_make": rec.camera_make,
                    "camera_model": rec.camera_model,
                    "focal_length_mm": rec.focal_length_mm,
                    "aperture": rec.aperture_fnumber,
                    "iso": rec.iso,
                    "exposure_time": f"1/{int(round(1/rec.exposure_time_s))}" if rec.exposure_time_s and rec.exposure_time_s > 0 and rec.exposure_time_s < 1 else rec.exposure_time_s,
                    "metadata_completeness": rec.metadata_completeness,
                    "validation_status": rec.validation_status,
                    "quality_status": rec.quality_status,
                    "quality_reason": rec.quality_reason,
                    "blur_score": rec.quality_metrics.blur_score if rec.quality_metrics else None,
                    "thumbnail_url": f"/api/thumbnails/{rec.image_id}.jpg" if rec.thumbnail_path else None,
                    "associated_gcps": rec.associated_gcps,
                },
            }
            image_features.append(feature)

        # Build trajectory LineString
        trajectory_feature = None
        if len(trajectory_coords) > 1:
            trajectory_feature = {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": trajectory_coords,
                },
                "properties": {
                    "name": "Drone Flight Trajectory",
                    "waypoint_count": len(trajectory_coords),
                },
            }

        # Build GCP features
        gcp_features: List[Dict[str, Any]] = []
        if gcps:
            for gcp in gcps:
                gcp_features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [gcp.longitude, gcp.latitude, gcp.elevation or 0.0],
                        },
                        "properties": {
                            "name": gcp.name,
                            "type": "GCP",
                            "elevation": gcp.elevation,
                            "easting": gcp.easting,
                            "northing": gcp.northing,
                            "associated_images_count": len(gcp.associated_images),
                            "associated_images": gcp.associated_images,
                        },
                    }
                )

        # Compute Bounding Box & Center
        bounds = None
        center = [0.0, 0.0]
        if valid_lats and valid_lons:
            bounds = {
                "min_lat": min(valid_lats),
                "max_lat": max(valid_lats),
                "min_lon": min(valid_lons),
                "max_lon": max(valid_lons),
            }
            center = [
                sum(valid_lats) / len(valid_lats),
                sum(valid_lons) / len(valid_lons),
            ]

        return {
            "type": "FeatureCollection",
            "features": image_features,
            "trajectory": trajectory_feature,
            "gcps": gcp_features,
            "bounds": bounds,
            "center": center,
            "total_plotted": len(image_features),
        }
