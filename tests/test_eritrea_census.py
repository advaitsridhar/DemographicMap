"""Tests for the Eritrea adapter's stated reasons, no network."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import eritrea_census as ec  # noqa: E402

SITE = Path(__file__).resolve().parent.parent / "site" / "data"


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.units = {level: json.loads((SITE / level / "ERI.units.json").read_text())
                      for level in ("admin1", "admin2")}
        self.records = ec.build(self.units)

    def test_every_unit_says_why_and_carries_no_figure(self):
        self.assertEqual(len(self.records), len(self.units["admin1"]) + len(self.units["admin2"]))
        for r in self.records:
            for field in ("median_age", "sex_ratio"):
                self.assertEqual(r[field]["status"], "not_available")
                self.assertIn("never taken a national census", r[field]["note"])
            self.assertNotIn("value", r["population"])

    def test_each_level_names_itself(self):
        by_level = {r["level"]: r for r in self.records}
        self.assertIn("this region's", by_level["admin1"]["median_age"]["note"])
        self.assertIn("this sub-region's", by_level["admin2"]["median_age"]["note"])


if __name__ == "__main__":
    unittest.main()
