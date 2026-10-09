"""Qatar's 2020 census by municipality, read from portal rows built in memory."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import qatar_census as qc  # noqa: E402

BANDS = ["0", "1 - 4"] + [f"{a} - {a + 4}" for a in range(5, 75, 5)] + ["75+"]


def rows(municipality, scale, *, year="2020", skip=None):
    out = []
    for i, band in enumerate(BANDS):
        if band == skip:
            continue
        out.append({"years": year, "age_groups_in_years": band, "municipality": municipality,
                    "value": float(scale * (len(BANDS) - i))})
    return out


ADMIN1 = [{"id": "m1", "name": "Doha", "parent": "QAT"},
          {"id": "m2", "name": "Umm Slal", "parent": "QAT"}]


def tables(**kw):
    men = rows("Doha", 30, **kw) + rows("Umm Salal", 5) + rows("Doha", 99, year="2019")
    women = rows("Doha", 20) + rows("Umm Salal", 5)
    return men, women


class TheReader(unittest.TestCase):
    def setUp(self):
        self.saved = qc.NATIONAL
        men, women = tables()
        qc.NATIONAL = round(sum(r["value"] for r in men + women if r["years"] == "2020"))

    def tearDown(self):
        qc.NATIONAL = self.saved

    def test_census_year_rows_are_read_and_bound(self):
        out = {r["shape_id"]: r for r in qc.build(*tables(), ADMIN1)}
        self.assertEqual(sorted(out), ["m1", "m2"])
        self.assertEqual(out["m2"]["aliases"], ["Umm Salal"])
        self.assertEqual(out["m1"]["population"]["year"], 2020)
        self.assertEqual(out["m1"]["sex_ratio"]["value"], 150.0)
        self.assertIsNotNone(out["m1"]["median_age"])

    def test_compositions_say_why_they_are_empty(self):
        rec = qc.build(*tables(), ADMIN1)[0]
        for field in ("religion", "ethnicity", "language"):
            self.assertEqual(rec[field]["status"], "not_available", field)
            self.assertIn("data.gov.qa", rec[field]["note"], field)
        self.assertIn("nationality", rec["ethnicity"]["note"])

    def test_a_missing_age_group_stops_the_run(self):
        men, women = tables(skip="5 - 9")
        with self.assertRaises(SystemExit):
            qc.build(men, women, ADMIN1)

    def test_a_national_total_that_does_not_match_stops_the_run(self):
        qc.NATIONAL += 10
        with self.assertRaises(SystemExit):
            qc.build(*tables(), ADMIN1)

    def test_age_labels(self):
        self.assertEqual(qc.band("0"), (0, 0))
        self.assertEqual(qc.band("1 - 4"), (1, 4))
        self.assertEqual(qc.band("75+"), (75, None))
        with self.assertRaises(SystemExit):
            qc.band("unknown")


if __name__ == "__main__":
    unittest.main()
