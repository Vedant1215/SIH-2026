"""
Unit tests for CsvMetadataParser and GCPParser.
"""

import unittest
from pathlib import Path
from backend.config import settings
from metadata.csv_parser import CsvMetadataParser
from metadata.gcp_parser import GCPParser


class TestCsvAndGcpParser(unittest.TestCase):
    def setUp(self):
        self.csv_parser = CsvMetadataParser()
        self.gcp_parser = GCPParser()
        self.dataset_path = settings.dataset_root

    def test_parse_mrk_telemetry(self):
        """Verify parsing of 101FTASK_Timestamp.mrk."""
        mrk_path = self.dataset_path / "RTK_Data" / "101FTASK_Timestamp.mrk"
        if not mrk_path.exists():
            self.skipTest(f"MRK file not found: {mrk_path}")

        records = self.csv_parser.parse_mrk_file(mrk_path)
        # Should match "MAX_0002", "MAX_0002.JPG", etc.
        self.assertIn("MAX_0002", records)
        rec2 = records["MAX_0002"]
        self.assertEqual(rec2.match_method, "INDEX_SEQUENCE")
        self.assertAlmostEqual(rec2.latitude, 47.643687, delta=0.001)
        self.assertAlmostEqual(rec2.longitude, 16.475927, delta=0.001)
        self.assertEqual(rec2.rtk_flag, 50)
        self.assertAlmostEqual(rec2.rtk_std_lat, 0.014391, delta=0.001)

    def test_parse_gcp_csv(self):
        """Verify parsing of latlon-easting_northing.csv."""
        gcp_csv = self.dataset_path / "GCP" / "latlon-easting_northing.csv"
        if not gcp_csv.exists():
            self.skipTest(f"GCP CSV not found: {gcp_csv}")

        points = self.gcp_parser.parse_gcp_csv(gcp_csv)
        self.assertEqual(len(points), 5)
        self.assertIn("1", points)
        pt1 = points["1"]
        self.assertAlmostEqual(pt1.latitude, 47.64350399, delta=0.0001)
        self.assertAlmostEqual(pt1.longitude, 16.47592207, delta=0.0001)
        self.assertAlmostEqual(pt1.elevation, 463.662, delta=0.1)

    def test_parse_gcp_list(self):
        """Verify parsing of ODM gcp_list.txt."""
        gcp_txt = self.dataset_path / "GCP" / "gcp_list.txt"
        if not gcp_txt.exists():
            self.skipTest(f"GCP list not found: {gcp_txt}")

        ties = self.gcp_parser.parse_gcp_list(gcp_txt)
        self.assertGreater(len(ties), 30)
        gcps_for_29 = self.gcp_parser.get_gcps_for_image("MAX_0029.JPG")
        self.assertIn("1", gcps_for_29)

    def test_filename_matching_priority(self):
        """Verify matching priority logic on synthetic CSV rows."""
        sample_rows = [
            {"filename": "MAX_0002.JPG", "lat": "47.123", "lon": "16.456", "alt": "500"},
            {"filename": "OTHER_0003.JPG", "lat": "48.123", "lon": "17.456", "alt": "520"},
        ]
        match = self.csv_parser.match_image_to_csv("MAX_0002.JPG", None, sample_rows, "test.csv")
        self.assertIsNotNone(match)
        self.assertEqual(match.match_method, "EXACT_FILENAME")
        self.assertEqual(match.match_confidence, 1.0)
        self.assertAlmostEqual(match.latitude, 47.123)


if __name__ == "__main__":
    unittest.main()
