"""The Central Africa probe's own helpers (no network)."""

import unittest

from scripts.fetch_census import central_africa_probe as cap


class Pages(unittest.TestCase):
    def test_page_ranges(self):
        self.assertEqual(cap.pages_of("3-5,9", 20), [3, 4, 5, 9])
        self.assertEqual(cap.pages_of("18-30", 20), [18, 19, 20])
        self.assertEqual(cap.pages_of("0,25", 20), [])

    def test_unknown_mode_is_said(self):
        lines = []
        original = cap.say
        cap.say = lines.append
        try:
            cap.probe("nonsense:https://example.org/")
        finally:
            cap.say = original
        self.assertTrue(any("unknown mode" in line for line in lines))


class Outlines(unittest.TestCase):
    def test_zip_of_geojson(self):
        import io
        import json
        import zipfile
        square = {"type": "Polygon", "coordinates": [[[13.123456, -8.0], [13.5, -8.0],
                                                      [13.5, -8.5], [13.123456, -8.5],
                                                      [13.123456, -8.0]]]}
        data = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": square,
             "properties": {"ADM2_PT": "Lobito", "ADM2_PCODE": "AO0705", "AREA": 3.1}}]}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("ago_admin2.geojson", json.dumps(data))
            z.writestr("ago_admin1.geojson", json.dumps({"features": []}))
        lines = []
        original = cap.say
        cap.say = lines.append
        try:
            cap.outlines(buf.getvalue(), "admin2", 0.01)
        finally:
            cap.say = original
        self.assertIn("  F ADM2_PT=Lobito | ADM2_PCODE=AO0705", lines)
        geometry = next(line for line in lines if line.startswith("  G "))
        self.assertIn("13.1234 -8", geometry)
        self.assertFalse(any("admin1" in line and "features" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
