"""
COLMAP Process Execution Runner for SIH 2026 Drone Ingestion & Reconstruction System.
Safely executes COLMAP CLI commands with CUDA support, capturing stdout/stderr into
persistent logs and handling paths with spaces on Windows.
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ColmapRunner:
    """Encapsulates execution of native COLMAP CLI binary."""

    def __init__(self, colmap_dir: Optional[Path] = None):
        if colmap_dir is None:
            # Default to tools/colmap inside project root
            colmap_dir = Path(__file__).resolve().parent.parent / "tools" / "colmap"

        self.colmap_dir = Path(colmap_dir)
        self.bat_path = self.colmap_dir / "COLMAP.bat"
        self.bin_colmap = self.colmap_dir / "bin" / "colmap.exe"
        self._check_installation()

    def _check_installation(self) -> bool:
        """Verifies if COLMAP executable exists."""
        if self.bin_colmap.exists():
            logger.info("Found COLMAP binary at %s", self.bin_colmap)
            return True
        if self.bat_path.exists():
            logger.info("Found COLMAP.bat at %s", self.bat_path)
            return True
        logger.warning("COLMAP executable not found at %s", self.colmap_dir)
        return False

    def is_available(self) -> bool:
        """Returns True if COLMAP binary is present."""
        return self.bin_colmap.exists() or self.bat_path.exists()

    def run_command(
        self,
        command_args: List[str],
        log_file: Optional[Path] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Executes a COLMAP command, e.g.:
        run_command(['feature_extractor', '--database_path', '...'])
        """
        if not self.is_available():
            err = f"COLMAP executable not found in {self.colmap_dir}. Please verify installation."
            logger.error(err)
            return False, err

        # Prepare environment with bin in PATH
        env = os.environ.copy()
        bin_dir = str(self.colmap_dir / "bin")
        env["PATH"] = f"{bin_dir};{env.get('PATH', '')}"
        env["QT_PLUGIN_PATH"] = str(self.colmap_dir / "plugins")

        cmd = [str(self.bin_colmap)] + command_args

        # Ensure parent log directory exists
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_handle = open(log_file, "a", encoding="utf-8", errors="replace")
        else:
            log_handle = None

        log_msg = f"[COLMAP EXEC] {' '.join(str(c) for c in cmd)}\n"
        if log_handle:
            log_handle.write(log_msg)
            log_handle.flush()
        logger.info(log_msg.strip())

        output_lines: List[str] = []
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                bufsize=1,
                universal_newlines=True,
            )

            for line in process.stdout:
                output_lines.append(line)
                if log_handle:
                    log_handle.write(line)
                    log_handle.flush()
                if progress_callback:
                    progress_callback(line.strip())

            process.wait(timeout=timeout_seconds)
            success = process.returncode == 0
            full_output = "".join(output_lines)
            if not success:
                logger.error("COLMAP command failed with code %d", process.returncode)
            return success, full_output

        except subprocess.TimeoutExpired:
            process.kill()
            msg = f"COLMAP process timed out after {timeout_seconds}s"
            logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"Error executing COLMAP: {e}"
            logger.error(msg)
            return False, msg
        finally:
            if log_handle:
                log_handle.close()
