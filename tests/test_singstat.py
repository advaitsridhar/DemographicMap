"""Singapore's planning regions from SingStat table M810771: the committed payload.

No network: the payload saved under data/raw/singapore is read as the runner reads it.
"""

import json
import unittest
from pathlib import Path

from scripts.fetch_census import singstat as s

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "data" / "raw" / "singapore" / "M810771.json"


class RegionNoteTest(unittest.TestCase):
    """Finding: the note said every other median on the map is a published figure,
    while Singapore's own planning areas, among many, are interpolated too."""

    @classmethod
    def setUpClass(cls):
        cls.rows = s.build(*s.parse(json.loads(PAYLOAD.read_text())))

    def test_five_regions_with_an_interpolated_median(self):
        self.assertEqual(len(self.rows), 5)
        for row in self.rows:
            self.assertIn("value", row["median_age"])
            note = row["median_age_note"]
            self.assertTrue(note.startswith("Interpolated from the five-year age bands"))
            self.assertIn("residents only", note)

    def test_no_claim_about_the_rest_of_the_map(self):
        for row in self.rows:
            self.assertNotIn("Elsewhere on this map", row["median_age_note"])
            self.assertNotIn("like for like", row["median_age_note"])

    def test_the_figures_are_the_committed_ones(self):
        committed = {r["id"]: r for r in json.loads(
            (ROOT / "data" / "processed" / "singapore_region.json").read_text())}
        for row in self.rows:
            old = committed[row["id"]]
            for field in ("population", "median_age", "sex_ratio"):
                self.assertEqual(row[field], old[field], (row["id"], field))


if __name__ == "__main__":
    unittest.main()
