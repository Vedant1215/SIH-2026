"""
Image Quality Analysis Service for SIH 2026 Drone Ingestion System.
Analyzes drone imagery using OpenCV for blur, brightness, contrast, and corruption.
Generates lightweight cached thumbnails for responsive web visualization.
Classifies images as GOOD, WARNING, or BAD with clear human-readable explanations.
"""

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from metadata.models import ImageRecord, QualityMetrics

logger = logging.getLogger(__name__)


class ImageQualityAnalyzer:
    """Computes computer vision quality metrics and generates thumbnails."""

    def __init__(
        self,
        thumbnails_dir: Optional[Path] = None,
        blur_bad_threshold: float = 100.0,
        blur_warn_threshold: float = 300.0,
        dark_threshold: float = 35.0,
        bright_threshold: float = 225.0,
        contrast_threshold: float = 18.0,
        thumbnail_width: int = 400,
    ):
        self.thumbnails_dir = Path(thumbnails_dir) if thumbnails_dir else None
        if self.thumbnails_dir:
            self.thumbnails_dir.mkdir(parents=True, exist_ok=True)

        self.blur_bad_threshold = blur_bad_threshold
        self.blur_warn_threshold = blur_warn_threshold
        self.dark_threshold = dark_threshold
        self.bright_threshold = bright_threshold
        self.contrast_threshold = contrast_threshold
        self.thumbnail_width = thumbnail_width
        self.seen_hashes: Dict[str, str] = {}  # hash -> image_id

    def compute_file_hash(self, file_path: Path) -> str:
        """Computes MD5 hash for exact duplicate detection."""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def analyze_image(
        self,
        image_path: Path,
        image_id: Optional[str] = None,
        generate_thumbnail: bool = True,
    ) -> Tuple[QualityMetrics, str, Optional[str], Optional[str]]:
        """
        Analyzes a single image file.
        Returns (QualityMetrics, status, reason, thumbnail_rel_path).
        """
        img_id = image_id or image_path.stem

        # 1. MD5 File Hash
        try:
            file_hash = self.compute_file_hash(image_path)
        except Exception:
            file_hash = None

        is_duplicate = False
        duplicate_of = None
        if file_hash:
            if file_hash in self.seen_hashes:
                is_duplicate = True
                duplicate_of = self.seen_hashes[file_hash]
            else:
                self.seen_hashes[file_hash] = img_id

        # 2. Read Image via OpenCV
        img = cv2.imread(str(image_path))
        if img is None or img.size == 0:
            metrics = QualityMetrics(
                blur_score=0.0,
                mean_brightness=0.0,
                contrast_std=0.0,
                is_corrupted=True,
                is_duplicate=is_duplicate,
                duplicate_of=duplicate_of,
                file_hash_md5=file_hash,
            )
            return metrics, "BAD", "Corrupt image file; failed to decode image pixels", None

        # 3. Compute Metrics
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        mean_brightness = float(np.mean(gray))
        contrast_std = float(np.std(gray))

        # 4. Generate & Cache Thumbnail
        thumb_rel_path = None
        if generate_thumbnail and self.thumbnails_dir:
            thumb_name = f"{img_id}.jpg"
            thumb_path = self.thumbnails_dir / thumb_name
            if not thumb_path.exists():
                h, w = img.shape[:2]
                new_w = self.thumbnail_width
                new_h = int(h * (new_w / w))
                thumb_img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                cv2.imwrite(str(thumb_path), thumb_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            thumb_rel_path = f"thumbnails/{thumb_name}"

        metrics = QualityMetrics(
            blur_score=round(blur_score, 2),
            mean_brightness=round(mean_brightness, 2),
            contrast_std=round(contrast_std, 2),
            is_corrupted=False,
            is_duplicate=is_duplicate,
            duplicate_of=duplicate_of,
            file_hash_md5=file_hash,
        )

        # 5. Classify Quality (GOOD / WARNING / BAD)
        status, reason = self._classify_quality(metrics)
        return metrics, status, reason, thumb_rel_path

    def _classify_quality(self, m: QualityMetrics) -> Tuple[str, Optional[str]]:
        """Categorizes image into GOOD, WARNING, BAD with detailed reasoning."""
        reasons: List[str] = []

        if m.is_corrupted:
            return "BAD", "Image file is corrupt"

        # Duplicate check
        if m.is_duplicate:
            reasons.append(f"Identical duplicate of {m.duplicate_of}")

        # Blur analysis
        if m.blur_score < self.blur_bad_threshold:
            reasons.append(f"Severe blur detected (Laplacian score {m.blur_score:.1f} < {self.blur_bad_threshold})")
        elif m.blur_score < self.blur_warn_threshold:
            reasons.append(f"Moderate blur detected (Laplacian score {m.blur_score:.1f} < {self.blur_warn_threshold})")

        # Brightness analysis
        if m.mean_brightness < self.dark_threshold:
            reasons.append(f"Very dark / underexposed (brightness {m.mean_brightness:.1f} < {self.dark_threshold})")
        elif m.mean_brightness > self.bright_threshold:
            reasons.append(f"Very bright / overexposed (brightness {m.mean_brightness:.1f} > {self.bright_threshold})")

        # Contrast analysis
        if m.contrast_std < self.contrast_threshold:
            reasons.append(f"Low contrast (std dev {m.contrast_std:.1f} < {self.contrast_threshold})")

        if not reasons:
            return "GOOD", "Optimal sharp exposure and contrast"

        # Determine severity
        is_bad = (
            m.blur_score < self.blur_bad_threshold
            or m.mean_brightness < (self.dark_threshold / 2)
            or m.mean_brightness > 245.0
        )
        if is_bad:
            return "BAD", "; ".join(reasons)
        return "WARNING", "; ".join(reasons)

    def analyze_batch(
        self,
        records: List[ImageRecord],
        max_workers: int = 8,
    ) -> List[ImageRecord]:
        """Runs parallel quality analysis across image records."""
        logger.info("Starting multithreaded image quality analysis for %d images", len(records))

        def process_one(rec: ImageRecord) -> ImageRecord:
            try:
                metrics, status, reason, thumb_path = self.analyze_image(
                    Path(rec.filepath), image_id=rec.image_id
                )
                rec.quality_metrics = metrics
                rec.quality_status = status
                rec.quality_reason = reason
                rec.thumbnail_path = thumb_path
            except Exception as e:
                logger.error("Error analyzing image %s: %s", rec.filename, e)
                rec.quality_status = "WARNING"
                rec.quality_reason = f"Analysis error: {e}"
            return rec

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            records = list(executor.map(process_one, records))

        logger.info("Quality analysis complete for %d images", len(records))
        return records
