"""
GCP Parser for SIH 2026 Drone Ingestion System.
Parses Ground Control Point coordinate tables (CSV) and
OpenDroneMap GCP tie-point lists (gcp_list.txt).
Links GCP observations to specific drone images.
"""

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from metadata.models import GCPPoint, GCPImageTie

logger = logging.getLogger(__name__)


class GCPParser:
    """Parses GCP definitions and image tie points."""

    def __init__(self):
        self.points: Dict[str, GCPPoint] = {}
        self.image_ties: List[GCPImageTie] = []
        self.image_to_gcps: Dict[str, List[str]] = {}

    def parse_gcp_csv(self, csv_path: Path) -> Dict[str, GCPPoint]:
        """
        Parses GCP coordinates table (e.g. latlon-easting_northing.csv).
        Supports semicolon or comma delimited columns:
        Name;Easting;Northing;Elevation;Longitude;Latitude
        """
        if not csv_path.exists():
            return self.points

        try:
            with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
                first_line = f.readline()
                delimiter = ";" if ";" in first_line else ","
                f.seek(0)
                reader = csv.DictReader(f, delimiter=delimiter)

                for row in reader:
                    clean = {
                        k.strip().lstrip("\ufeff"): v.strip()
                        for k, v in row.items()
                        if k and v
                    }
                    name = clean.get("Name") or clean.get("ID") or clean.get("gcp")
                    if not name:
                        continue

                    easting = float(clean["Easting"]) if "Easting" in clean else None
                    northing = float(clean["Northing"]) if "Northing" in clean else None
                    elevation = (
                        float(clean["Elevation"])
                        if "Elevation" in clean
                        else (float(clean["Altitude"]) if "Altitude" in clean else None)
                    )
                    lon = float(clean.get("Longitude") or clean.get("Lon") or 0.0)
                    lat = float(clean.get("Latitude") or clean.get("Lat") or 0.0)

                    self.points[name] = GCPPoint(
                        name=name,
                        easting=easting,
                        northing=northing,
                        elevation=elevation,
                        longitude=lon,
                        latitude=lat,
                        associated_images=[],
                    )
            logger.info("Parsed %d GCP definitions from %s", len(self.points), csv_path.name)
        except Exception as e:
            logger.error("Error reading GCP CSV %s: %s", csv_path.name, e)

        return self.points

    def parse_gcp_list(self, txt_path: Path) -> List[GCPImageTie]:
        """
        Parses OpenDroneMap gcp_list.txt.
        Format:
        EPSG:4326
        [lon] [lat] [elevation] [pixel_x] [pixel_y] [image_filename] [gcp_id]
        """
        if not txt_path.exists():
            return self.image_ties

        try:
            with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [l.strip() for l in f if l.strip()]

            if not lines:
                return self.image_ties

            # First line is usually CRS (e.g., EPSG:4326)
            coord_lines = lines[1:] if lines[0].upper().startswith("EPSG") else lines

            for line in coord_lines:
                parts = line.split()
                if len(parts) >= 7:
                    try:
                        lon = float(parts[0])
                        lat = float(parts[1])
                        elev = float(parts[2])
                        px = float(parts[3])
                        py = float(parts[4])
                        img_fn = parts[5]
                        gcp_id = parts[6]

                        tie = GCPImageTie(
                            gcp_name=gcp_id,
                            image_filename=img_fn,
                            pixel_x=px,
                            pixel_y=py,
                            longitude=lon,
                            latitude=lat,
                            elevation=elev,
                        )
                        self.image_ties.append(tie)

                        # Update bidirectional link
                        if img_fn not in self.image_to_gcps:
                            self.image_to_gcps[img_fn] = []
                        if gcp_id not in self.image_to_gcps[img_fn]:
                            self.image_to_gcps[img_fn].append(gcp_id)

                        # Update point model if exists
                        if gcp_id in self.points:
                            if img_fn not in self.points[gcp_id].associated_images:
                                self.points[gcp_id].associated_images.append(img_fn)
                        else:
                            # Register point from tie file
                            self.points[gcp_id] = GCPPoint(
                                name=gcp_id,
                                elevation=elev,
                                longitude=lon,
                                latitude=lat,
                                associated_images=[img_fn],
                            )
                    except ValueError as ve:
                        logger.warning("Skipping malformed GCP line: %s (%s)", line, ve)

            logger.info("Parsed %d GCP image tie points from %s", len(self.image_ties), txt_path.name)
        except Exception as e:
            logger.error("Error reading GCP list file %s: %s", txt_path.name, e)

        return self.image_ties

    def get_gcps_for_image(self, image_filename: str) -> List[str]:
        """Returns list of GCP names referenced in this image."""
        return self.image_to_gcps.get(image_filename, [])
