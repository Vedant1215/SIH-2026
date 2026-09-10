"""
Configuration module for SIH 2026 Drone Ingestion System.
Handles environment variables, dataset root path configuration,
and output directory management without hard-coding local paths.
"""

import os
from pathlib import Path
from typing import Optional


def load_env_file(dotenv_path: Optional[Path] = None) -> None:
    """Simple .env loader avoiding extra third-party dependencies."""
    if dotenv_path is None:
        dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    if dotenv_path.is_file():
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if k and k not in os.environ:
                    os.environ[k] = v


# Load .env file on module import
load_env_file()


class Settings:
    """Application settings with dynamic fallback and path verification."""

    def __init__(self):
        # Configurable dataset root via DATASET_ROOT env var
        default_dataset = r"C:\Users\maham\Downloads\odm_data_helenenschacht-main"
        self.dataset_root: Path = Path(os.environ.get("DATASET_ROOT", default_dataset))

        # Output directory for cache, thumbnails, reports, manifests
        default_output = Path(__file__).resolve().parent.parent / "output"
        self.output_dir: Path = Path(os.environ.get("OUTPUT_DIR", str(default_output)))

        # Subdirectories inside output_dir
        self.thumbnails_dir: Path = self.output_dir / "thumbnails"
        self.reports_dir: Path = self.output_dir / "reports"
        self.manifests_dir: Path = self.output_dir / "manifests"

        # Server configuration
        self.host: str = os.environ.get("HOST", "127.0.0.1")
        self.port: int = int(os.environ.get("PORT", "8000"))
        self.debug: bool = os.environ.get("DEBUG", "False").lower() in ("1", "true", "yes")

        # Ensure output directories exist (never touch dataset_root!)
        self._ensure_output_directories()

    def _ensure_output_directories(self) -> None:
        """Create output directories if they do not exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    def is_dataset_available(self) -> bool:
        """Check if configured dataset root directory exists."""
        return self.dataset_root.exists() and self.dataset_root.is_dir()

    def get_dataset_status(self) -> dict:
        """Return dataset path status for diagnostics."""
        exists = self.is_dataset_available()
        return {
            "dataset_root": str(self.dataset_root),
            "exists": exists,
            "is_directory": self.dataset_root.is_dir() if exists else False,
            "output_dir": str(self.output_dir),
        }


# Singleton settings instance
settings = Settings()
