"""Philippines: median age and sex ratio by province and region, 2020 census.

No network: barangay rows are built here in the workbook's own layout (six
label columns, then Total and every single year for MF, M and F).
"""

import unittest
from collections import Counter

from scripts.fetch_census import philippines_age as p

AGES = ["Under 1"] + [str(a) for a in range(1, 80)] + ["80 and over"]
HEADER = (["Region", "Province", "Mun", "Bgy", "BgyCode_new", "BgyCode_old"]
          + [f"{a}_{s}" for s in ("MF", "M", "F") for a in ["Total"] + AGES])


def row(region: str, province: str, bgy: str, males: list[int], females: list[int]) -> list:
    both = [m + f for m, f in zip(males, females)]
    return ([region, province, "Mun", bgy, "PH0", "PH0"]
            + [sum(both)] + both + [sum(males)] + males + [sum(females)] + females)


def flat(n: int) -> list[int]:
    return [n] * len(AGES)


ADMIN1 = [{"id": "R1", "name": "NCR"}, {"id": "R2", "name": "Davao Region"}]
ADMIN2 = [{"id": "S1", "name": "NCR, Second District", "parent": "R1"},
          {"id": "S2", "name": "Compostela Valley", "parent": "R2"},
          {"id": "S3", "name": "Davao del Sur", "parent": "R2"}]


class ColumnsTest(unittest.TestCase):
    def test_single_years_to_an_open_top_class(self):
        cols = p.columns(HEADER)
        self.assertEqual(cols["top"], 80)
        self.assertEqual(len(cols["ages"]["MF"]), 81)
        self.assertEqual(cols["ages"]["F"][(0, 0)], HEADER.index("Under 1_F"))

    def test_a_missing_year_refuses(self):
        header = [h for h in HEADER if h not in ("40_MF", "40_M", "40_F")]
        with self.assertRaises(SystemExit):
            p.columns(header)

    def test_an_unknown_age_label_refuses(self):
        header = [h.replace("80 and over_M", "eighty_M") for h in HEADER]
        with self.assertRaises(SystemExit):
            p.columns(header)


class AggregateTest(unittest.TestCase):
    def test_suffix_dropped_and_barangays_added(self):
        cols = p.columns(HEADER)
        rows = [row("NCR", "NCR, Second District (Not a Province)", "B1", flat(2), flat(1)),
                row("NCR", "NCR, Second District (Not a Province)", "B2", flat(1), flat(1))]
        units = p.aggregate(rows, cols)
        u = units[("NCR", "NCR, Second District")]
        self.assertEqual(u["barangays"], 2)
        self.assertEqual(u["totals"]["M"], 3 * 81)
        self.assertEqual(u["ages"]["MF"][0], 5)

    def test_a_barangay_whose_ages_miss_its_total_refuses(self):
        cols = p.columns(HEADER)
        bad = row("NCR", "X", "B1", flat(1), flat(1))
        bad[6] += 1                      # Total_MF one more than its ages
        with self.assertRaises(SystemExit):
            p.aggregate([bad], cols)


class BuildTest(unittest.TestCase):
    def units(self):
        cols = p.columns(HEADER)
        rows = [row("NCR", "NCR, Second District (Not a Province)", "B1", flat(10), flat(10)),
                row("Region XI", "Davao de Oro", "B2", flat(10), flat(12)),
                row("Region XI", "Davao del Sur", "B3", flat(12), flat(10))]
        return p.aggregate(rows, cols)

    def test_alias_and_region_sum(self):
        recs = p.build(self.units(), 80, ADMIN1, ADMIN2)
        by = {r["shape_id"]: r for r in recs}
        self.assertEqual(set(by), {"S1", "S2", "S3", "R1", "R2"})
        self.assertEqual(by["S2"]["aliases"], ["Davao de Oro"])
        # 81 equal single years from 0 to 80+: the middle person is in the year 40.
        self.assertEqual(by["S1"]["median_age"]["value"], 40.5)
        self.assertEqual(by["S2"]["sex_ratio"]["value"], round(100 * 10 / 12, 1))
        self.assertEqual(by["R2"]["sex_ratio"]["value"], 100.0)
        self.assertEqual(by["S2"]["population"]["value"], 22 * 81)
        self.assertIsNone(by["R2"]["population"].get("value"))
        self.assertEqual(by["R1"]["level"], "admin1")

    def test_a_province_with_no_polygon_refuses(self):
        units = self.units()
        units[("Region XI", "Nowhere")] = {**units[("Region XI", "Davao del Sur")],
                                           "province": "Nowhere"}
        with self.assertRaises(SystemExit):
            p.build(units, 80, ADMIN1, ADMIN2)

    def test_a_region_with_an_unbound_province_is_not_written(self):
        admin2 = ADMIN2 + [{"id": "S4", "name": "Davao Oriental", "parent": "R2"}]
        recs = p.build(self.units(), 80, ADMIN1, admin2)
        self.assertNotIn("R2", {r["shape_id"] for r in recs})


class NationalTest(unittest.TestCase):
    def test_far_from_the_proclaimed_total_refuses(self):
        units = {("A", "B"): {"ages": {"MF": Counter({20: 10, 30: 10})}}}
        with self.assertRaises(SystemExit):
            p.check_national(units, 80)


if __name__ == "__main__":
    unittest.main()
