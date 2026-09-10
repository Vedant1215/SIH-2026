"""
Camera Calibration Physics and Model Generator for SIH 2026 Drone Ingestion System.
Calculates metric sensor dimensions, pixel pitch, and focal length priors for Autel XT705.
Configures COLMAP camera models (OPENCV: fx, fy, cx, cy, k1, k2, p1, p2).
"""

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Known physical sensor specifications
SENSOR_DATABASE = {
    "XT705": {
        "sensor_name": "Sony 1-inch CMOS (20MP)",
        "sensor_width_mm": 13.2,
        "sensor_height_mm": 8.8,
        "native_width_px": 5472,
        "native_height_px": 3648,
    }
}


class CameraCalibrationManager:
    """Computes photogrammetric intrinsic camera parameters from physical optics."""

    def __init__(
        self,
        camera_make: str = "Autel Robotics",
        camera_model: str = "XT705",
        focal_length_mm: float = 10.57,
        image_width: int = 5472,
        image_height: int = 3648,
    ):
        self.camera_make = camera_make
        self.camera_model = camera_model
        self.focal_length_mm = focal_length_mm
        self.width = image_width
        self.height = image_height

        self.sensor_info = SENSOR_DATABASE.get(
            camera_model,
            {
                "sensor_name": "Generic 1-inch CMOS",
                "sensor_width_mm": 13.2,
                "sensor_height_mm": 8.8,
                "native_width_px": image_width,
                "native_height_px": image_height,
            },
        )

    def calculate_intrinsics(self) -> Dict[str, Any]:
        """
        Calculates metric focal lengths, principal points, and pixel pitch.
        Focal length in pixels: fx = F_mm / (sensor_w_mm / img_w)
        """
        sw = self.sensor_info["sensor_width_mm"]
        sh = self.sensor_info["sensor_height_mm"]

        # Pixel pitch in millimeters
        pixel_pitch_x = sw / self.width
        pixel_pitch_y = sh / self.height

        # Focal lengths in pixels
        fx = self.focal_length_mm / pixel_pitch_x
        fy = self.focal_length_mm / pixel_pitch_y

        # Principal point (image center prior)
        cx = self.width / 2.0
        cy = self.height / 2.0

        # Model OPENCV parameters: fx, fy, cx, cy, k1, k2, p1, p2
        opencv_params = [round(fx, 3), round(fy, 3), round(cx, 3), round(cy, 3), 0.0, 0.0, 0.0, 0.0]
        params_str = ",".join(str(p) for p in opencv_params)

        logger.info(
            "Computed camera calibration for %s %s: fx=%.2f, fy=%.2f, cx=%.2f, cy=%.2f (sensor: %.1fx%.1f mm, pitch: %.2f um)",
            self.camera_make,
            self.camera_model,
            fx,
            fy,
            cx,
            cy,
            sw,
            sh,
            pixel_pitch_x * 1000.0,
        )

        return {
            "camera_model": "OPENCV",
            "camera_make": self.camera_make,
            "camera_model_name": self.camera_model,
            "sensor_name": self.sensor_info["sensor_name"],
            "sensor_width_mm": sw,
            "sensor_height_mm": sh,
            "pixel_pitch_um": round(pixel_pitch_x * 1000.0, 3),
            "focal_length_mm": self.focal_length_mm,
            "fx_pixels": round(fx, 3),
            "fy_pixels": round(fy, 3),
            "cx_pixels": round(cx, 3),
            "cy_pixels": round(cy, 3),
            "colmap_params_str": params_str,
            "distortion_prior": [0.0, 0.0, 0.0, 0.0],
            "is_refined_in_bundle_adjustment": True,
        }
