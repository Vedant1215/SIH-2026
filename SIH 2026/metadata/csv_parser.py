"""
CSV and MRK Telemetry Parser for SIH 2026 Drone Ingestion System.
Parses CSV files, MRK shutter timestamp files, and telemetry logs.
Implements a robust multi-tier matching engine between drone images and metadata records:
1. Exact filename matching (confidence: 1.0)
2. Image identifier / sequence matching (confidence: 0.95)
3. Timestamp proximity matching (confidence: 0.85)
Does not perform unsafe fuzzy matching.
"""

import csv
import io
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CsvMetadataRecord:
    """Represents a matched metadata row from CSV or MRK."""

    def __init__(
        self,
        raw_data: Dict[str, Any],
        source_file: str,
        match_method: str,
        match_confidence: float,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        altitude: Optional[float] = None,
        timestamp: Optional[str] = None,
        gps_time_of_week: Optional[float] = None,
        gps_week: Optional[int] = None,
        rtk_flag: Optional[int] = None,
        rtk_std_lat: Optional[float] = None,
        rtk_std_lon: Optional[float] = None,
        rtk_std_hgt: Optional[float] = None,
    ):
        self.raw_data = raw_data
        self.source_file = source_file
        self.match_method = match_method
        self.match_confidence = match_confidence
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.timestamp = timestamp
        self.gps_time_of_week = gps_time_of_week
        self.gps_week = gps_week
        self.rtk_flag = rtk_flag
        self.rtk_std_lat = rtk_std_lat
        self.rtk_std_lon = rtk_std_lon
        self.rtk_std_hgt = rtk_std_hgt


class CsvMetadataParser:
    """Discovers, parses, and matches CSV and telemetry records with images."""

    def __init__(self):
        self.parsed_sources: Dict[str, List[Dict[str, Any]]] = {}

    def sniff_delimiter(self, file_path: Path) -> str:
        """Determines whether a file uses comma, semicolon, or tab delimiter."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            first_lines = [f.readline() for _ in range(5)]
            sample = "".join(l for l in first_lines if l.strip())

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            return dialect.delimiter
        except Exception:
            # Fallback heuristic
            if ";" in sample and "," not in sample:
                return ";"
            if "\t" in sample:
                return "\t"
            return ","

    def parse_mrk_file(self, mrk_path: Path) -> Dict[str, CsvMetadataRecord]:
        """
        Parses Autel/DJI MRK timestamp event log file (e.g., 101FTASK_Timestamp.mrk).
        Lines have format:
        [Index] [GPS_TOW] [Week] [Offsets N,E,V] [Lat,Lat] [Lon,Lon] [Ellh,Ellh] [StdDevs] [Q,Q]
        Matches index (e.g. 2) to image identifiers (e.g. MAX_0002).
        """
        matched_records: Dict[str, CsvMetadataRecord] = {}

        if not mrk_path.exists():
            return matched_records

        try:
            with open(mrk_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    parts = line.split("\t")
                    if len(parts) < 8:
                        # Fallback space split
                        parts = re.split(r"\s{2,}", line)

                    if len(parts) < 7:
                        continue

                    try:
                        idx_str = parts[0].strip()
                        idx_int = int(idx_str)
                    except ValueError:
                        continue

                    # Parse coordinates
                    lat, lon, alt = None, None, None
                    std_lat, std_lon, std_hgt = None, None, None
                    rtk_flag = None
                    tow = None
                    week = None

                    try:
                        tow = float(parts[1].strip())
                    except (ValueError, IndexError):
                        pass

                    try:
                        week_str = parts[2].strip().strip("[]")
                        week = int(week_str)
                    except (ValueError, IndexError):
                        pass

                    # Look for Lat, Lon, Ellh columns
                    for p in parts:
                        p_clean = p.strip()
                        if p_clean.endswith(",Lat"):
                            try:
                                lat = float(p_clean.replace(",Lat", ""))
                            except ValueError:
                                pass
                        elif p_clean.endswith(",Lon"):
                            try:
                                lon = float(p_clean.replace(",Lon", ""))
                            except ValueError:
                                pass
                        elif p_clean.endswith(",Ellh"):
                            try:
                                alt = float(p_clean.replace(",Ellh", ""))
                            except ValueError:
                                pass
                        elif p_clean.endswith(",Q"):
                            try:
                                rtk_flag = int(p_clean.replace(",Q", ""))
                            except ValueError:
                                pass
                        elif "," in p_clean and len(p_clean.split(",")) == 3:
                            # Standard deviations e.g. 0.014391, 0.013698, 0.029694
                            dev_parts = [dp.strip() for dp in p_clean.split(",")]
                            try:
                                std_lat = float(dev_parts[0])
                                std_lon = float(dev_parts[1])
                                std_hgt = float(dev_parts[2])
                            except ValueError:
                                pass

                    record = CsvMetadataRecord(
                        raw_data={"line": line, "parts": parts},
                        source_file=mrk_path.name,
                        match_method="INDEX_SEQUENCE",
                        match_confidence=0.98,
                        latitude=lat,
                        longitude=lon,
                        altitude=alt,
                        gps_time_of_week=tow,
                        gps_week=week,
                        rtk_flag=rtk_flag,
                        rtk_std_lat=std_lat,
                        rtk_std_lon=std_lon,
                        rtk_std_hgt=std_hgt,
                    )

                    # Keys to match: e.g. "MAX_0002", "MAX_0002.JPG", "2"
                    img_prefix = f"MAX_{idx_int:04d}"
                    matched_records[img_prefix] = record
                    matched_records[f"{img_prefix}.JPG"] = record
                    matched_records[str(idx_int)] = record

            logger.info("Parsed %d MRK records from %s", len(matched_records) // 3, mrk_path.name)
        except Exception as e:
            logger.error("Error reading MRK file %s: %s", mrk_path.name, e)

        return matched_records

    def parse_csv_file(self, csv_path: Path) -> List[Dict[str, Any]]:
        """Reads generic CSV file with auto-detected delimiter and original column headers."""
        rows: List[Dict[str, Any]] = []
        if not csv_path.exists():
            return rows

        delimiter = self.sniff_delimiter(csv_path)
        try:
            with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                for row in reader:
                    # Strip whitespace and BOM from keys and values
                    clean_row = {
                        k.strip().lstrip("\ufeff"): v.strip()
                        for k, v in row.items()
                        if k is not None and v is not None
                    }
                    rows.append(clean_row)
            logger.info("Read %d rows from CSV %s (delimiter: '%s')", len(rows), csv_path.name, delimiter)
        except Exception as e:
            logger.error("Error reading CSV file %s: %s", csv_path.name, e)
        return rows

    def match_image_to_csv(
        self,
        image_filename: str,
        image_timestamp: Optional[str],
        csv_rows: List[Dict[str, Any]],
        csv_filename: str,
    ) -> Optional[CsvMetadataRecord]:
        """
        Matches a drone image with a CSV record using strict hierarchical priority:
        1. Exact filename match
        2. Image identifier match (stem or numeric sequence)
        3. Timestamp match
        """
        image_stem = Path(image_filename).stem.upper()
        image_fn_upper = image_filename.upper()

        # Potential column names for filenames and identifiers
        filename_cols = ["FILENAME", "FILE", "IMAGE_NAME", "IMAGE", "NAME", "PHOTO", "IMG"]
        lat_cols = ["LATITUDE", "LAT", "Y", "NORTHING", "GPSLATITUDE"]
        lon_cols = ["LONGITUDE", "LON", "LONG", "X", "EASTING", "GPSLONGITUDE"]
        alt_cols = ["ALTITUDE", "ALT", "ELEVATION", "ELEV", "Z", "HEIGHT", "ELLIPSOIDAL"]
        time_cols = ["TIMESTAMP", "TIME", "DATE", "DATETIME", "UTC"]

        # PASS 1: Exact filename match
        for row in csv_rows:
            for k, v in row.items():
                k_upper = k.upper()
                if any(k_upper == col for col in filename_cols):
                    val_str = str(v).strip()
                    if val_str.upper() == image_fn_upper or val_str.upper() == image_stem:
                        return self._create_record_from_row(
                            row, csv_filename, "EXACT_FILENAME", 1.0, lat_cols, lon_cols, alt_cols, time_cols
                        )

        # PASS 2: Image identifier / numeric sequence match
        # Extract number from image e.g. "MAX_0042" -> 42
        num_match = re.search(r"(\d+)", image_stem)
        if num_match:
            img_num = int(num_match.group(1))
            for row in csv_rows:
                for k, v in row.items():
                    k_upper = k.upper()
                    if any(k_upper == col for col in filename_cols):
                        val_str = str(v).strip()
                        row_num_match = re.search(r"(\d+)", val_str)
                        if row_num_match and int(row_num_match.group(1)) == img_num:
                            return self._create_record_from_row(
                                row, csv_filename, "IMAGE_IDENTIFIER", 0.95, lat_cols, lon_cols, alt_cols, time_cols
                            )

        # PASS 3: Timestamp match (if timestamp available and unambiguous)
        if image_timestamp:
            norm_img_ts = self._normalize_timestamp(image_timestamp)
            if norm_img_ts:
                for row in csv_rows:
                    for k, v in row.items():
                        if any(k.upper() == col for col in time_cols):
                            norm_row_ts = self._normalize_timestamp(str(v))
                            if norm_row_ts and norm_row_ts == norm_img_ts:
                                return self._create_record_from_row(
                                    row, csv_filename, "TIMESTAMP_EXACT", 0.85, lat_cols, lon_cols, alt_cols, time_cols
                                )

        # No safe match found
        return None

    def _normalize_timestamp(self, ts: str) -> Optional[str]:
        """Normalizes various date-time formats to YYYY-MM-DD HH:MM:SS."""
        ts = ts.strip().replace("/", "-")
        # Format 2022:05:25 12:17:49 -> 2022-05-25 12:17:49
        if re.match(r"^\d{4}:\d{2}:\d{2}", ts):
            ts = ts[:10].replace(":", "-") + ts[10:]
        try:
            return ts[:19]
        except Exception:
            return None

    def _create_record_from_row(
        self,
        row: Dict[str, Any],
        source_file: str,
        match_method: str,
        confidence: float,
        lat_cols: List[str],
        lon_cols: List[str],
        alt_cols: List[str],
        time_cols: List[str],
    ) -> CsvMetadataRecord:
        """Extracts spatial attributes from a matched row."""
        lat, lon, alt, ts = None, None, None, None

        for k, v in row.items():
            k_upper = k.upper()
            if any(k_upper == c for c in lat_cols) and lat is None:
                try:
                    lat = float(v)
                except ValueError:
                    pass
            elif any(k_upper == c for c in lon_cols) and lon is None:
                try:
                    lon = float(v)
                except ValueError:
                    pass
            elif any(k_upper == c for c in alt_cols) and alt is None:
                try:
                    alt = float(v)
                except ValueError:
                    pass
            elif any(k_upper == c for c in time_cols) and ts is None:
                ts = str(v)

        return CsvMetadataRecord(
            raw_data=row,
            source_file=source_file,
            match_method=match_method,
            match_confidence=confidence,
            latitude=lat,
            longitude=lon,
            altitude=alt,
            timestamp=ts,
        )
