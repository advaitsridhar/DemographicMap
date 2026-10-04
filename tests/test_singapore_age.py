"""Singapore: median age and sex ratio by planning area, Census of Population 2020.

No network: the data.gov.sg extract is written here in its own layout (sex
first, then the age group: Total_Total, Total_0_4 ... Females_90andOver).
"""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.fetch_census import singapore_age as sg

AGES = [f"{lo}_{lo + 4}" for lo in range(0, 90, 5)] + ["90andOver"]


def header():
    return ["Number"] + [f"{sex}_{age}" for sex in ("Total", "Males", "Females")
                         for age in ["Total", *AGES]]


def line(name, males, females):
    """``males``/``females``: a count per group (19 of them), or '-' for all."""
    out = [name]
    if males == "-":
        return out + ["40"] + ["-"] * 19 + ["-"] * 20 + ["-"] * 20
    total = [m + f for m, f in zip(males, females)]
    for groups in (total, males, females):
        out += [str(sum(groups))] + [str(n) for n in groups]
    return out


AMK_M = [100] * 19
AMK_F = [120] * 19
SMALL_M = [10] + [0] * 18
SMALL_F = [10] + [0] * 18


class SingaporeAgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "age.csv"
        national_m = [a + b for a, b in zip(AMK_M, SMALL_M)]
        national_f = [a + b for a, b in zip(AMK_F, SMALL_F)]
        with self.path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(header())
            w.writerow(line("Total", national_m, national_f))
            w.writerow(line("Ang Mo Kio - Total", AMK_M, AMK_F))
            w.writerow(line("Ang Mo Kio Town Centre", AMK_M, AMK_F))
            w.writerow(line("Changi Bay - Total", SMALL_M, SMALL_F))
            w.writerow(line("Boon Lay - Total", "-", "-"))
        self.national = sum(national_m) + sum(national_f) + 40

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, median=47.5):
        with mock.patch.object(sg, "NATIONAL", self.national - 40), \
                mock.patch.object(sg, "NATIONAL_MEDIAN", median):
            return sg.read(self.path)

    def test_areas_and_their_groups(self):
        areas, national = self.read()
        self.assertEqual(set(areas), {"Ang Mo Kio", "Changi Bay", "Boon Lay"})
        self.assertEqual(areas["Ang Mo Kio"]["total"], 19 * 220)
        self.assertTrue(areas["Boon Lay"]["withheld"])

    def test_a_national_median_off_the_census_refuses(self):
        with self.assertRaises(SystemExit):
            self.read(median=30.0)

    def test_records(self):
        areas, _ = self.read()
        admin2 = [{"id": "AMK", "name": "ANG MO KIO"}, {"id": "CB", "name": "CHANGI BAY"},
                  {"id": "BL", "name": "BOON LAY"}]
        recs = {r["shape_id"]: r for r in sg.build(areas, admin2)}
        self.assertEqual(recs["AMK"]["sex_ratio"]["value"], round(100 * 100 / 120, 1))
        # equal groups 0-89 and 90+: the middle person ends the 45-49 group's first half.
        self.assertEqual(recs["AMK"]["median_age"]["value"], 47.5)
        self.assertNotIn("value", recs["CB"]["median_age"])
        self.assertIn("fewer than", recs["CB"]["median_age"]["note"])
        self.assertIn("withheld", recs["BL"]["median_age"]["note"])
        self.assertNotIn("value", recs["BL"]["sex_ratio"])

    def test_an_area_without_a_polygon_refuses(self):
        areas, _ = self.read()
        with self.assertRaises(SystemExit):
            sg.build(areas, [{"id": "AMK", "name": "ANG MO KIO"}])


if __name__ == "__main__":
    unittest.main()
