"""Senegal's 2023 census by department: the polygons Keur Massar was cut from."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import senegal_rgph5 as sn  # noqa: E402

# The 2023 counts of the three departments, as the workbook gives them.
TABLE = {"departments": {
    "pikine": {"name": "Pikine", "total": 764_597, "men": 381_000, "women": 383_597},
    "rufisque": {"name": "Rufisque", "total": 818_337, "men": 410_000, "women": 408_337},
    "keurmassar": {"name": "Keur Massar", "total": 770_314, "men": 385_000, "women": 385_314},
}}


class Redrawn(unittest.TestCase):
    def test_the_reason_cites_the_census_as_its_source(self):
        rec = sn.redrawn(TABLE, {"name": "Pikine", "id": "SEN-pikine"})
        for field in ("population", "sex_ratio"):
            self.assertEqual(rec[field]["status"], "not_available")
            self.assertIn("Keur Massar 770,314", rec[field]["note"])
        # The fields are empty: the census is cited for the note, not for a figure.
        self.assertEqual([s["field"] for s in rec["sources"]],
                         ["population note/sex_ratio note"])


if __name__ == "__main__":
    unittest.main()
