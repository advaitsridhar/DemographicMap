"""Saudi Arabia's 2022 census by region, read from a COD-PS table built in memory."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import saudi_census as sc  # noqa: E402

BANDS = [(a, a + 4) for a in range(0, 100, 5)]


def row(name, pcode, men_groups, women_groups):
    out = {"year": "2022", "ISO3": "SAU", "ADM0_EN": "Saudi Arabia", "ADM0_PCODE": "SA",
           "ADM1_EN": name, "ADM1_PCODE": pcode,
           "F_TL": str(sum(women_groups)), "M_TL": str(sum(men_groups)),
           "T_TL": str(sum(men_groups) + sum(women_groups))}
    for (low, high), m, w in zip(BANDS, men_groups, women_groups):
        out[f"F_{low:02d}_{high:02d}"] = str(w)
        out[f"M_{low:02d}_{high:02d}"] = str(m)
        out[f"T_{low:02d}_{high:02d}"] = str(m + w)
    return out


def groups(scale):
    return [scale * (20 - i) for i in range(20)]


ADMIN1 = [{"id": "r1", "name": "Riyadh Region", "parent": "SAU"},
          {"id": "r2", "name": "Hayel Region", "parent": "SAU"},
          {"id": "r3", "name": "Makkah Region", "parent": "SAU"}]


def rows():
    return [row("Riyadh", "SA01", groups(30), groups(20)),
            row("Hail", "SA06", groups(3), groups(3)),
            row("Makkah Al Mukarramah", "SA02", groups(25), groups(20))]


class TheReader(unittest.TestCase):
    def setUp(self):
        self.saved = sc.NATIONAL
        sc.NATIONAL = sum(float(r["T_TL"]) for r in rows())

    def tearDown(self):
        sc.NATIONAL = self.saved

    def test_every_region_is_bound_by_name_or_declared_alias(self):
        out = {r["shape_id"]: r for r in sc.build(rows(), ADMIN1)}
        self.assertEqual(sorted(out), ["r1", "r2", "r3"])
        self.assertEqual(out["r2"]["codes"], {"pcode": "SA06"})
        self.assertEqual(out["r3"]["aliases"], ["Makkah Al Mukarramah"])

    def test_population_sex_ratio_and_median(self):
        out = {r["shape_id"]: r for r in sc.build(rows(), ADMIN1)}
        r1 = out["r1"]
        self.assertEqual(r1["population"]["value"], 50 * 210)
        self.assertEqual(r1["sex_ratio"]["value"], 150.0)
        self.assertEqual(r1["sex_ratio"]["unit"], "males_per_100_females")
        self.assertEqual(r1["median_age"]["year"], 2022)
        self.assertGreater(r1["median_age"]["value"], 0)

    def test_regions_that_miss_the_kingdom_stop_the_run(self):
        sc.NATIONAL += 1
        with self.assertRaises(SystemExit):
            sc.build(rows(), ADMIN1)

    def test_age_groups_that_miss_the_total_stop_the_run(self):
        broken = rows()
        broken[0]["T_TL"] = str(float(broken[0]["T_TL"]) + 500)
        broken[0]["M_TL"] = str(float(broken[0]["M_TL"]) + 500)
        with self.assertRaises(SystemExit):
            sc.build(broken, ADMIN1)

    def test_a_drawn_region_left_unbound_stops_the_run(self):
        with self.assertRaises(SystemExit):
            sc.build(rows(), ADMIN1 + [{"id": "r4", "name": "Tabuk Region", "parent": "SAU"}])


if __name__ == "__main__":
    unittest.main()
