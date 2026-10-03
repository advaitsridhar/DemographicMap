"""Austria's district reader, on a two-district, two-Land table (no network)."""

import unittest
from collections import Counter
from unittest import mock

from scripts.fetch_census import austria, central_ages


def rows(year=2026):
    out = []
    for commune, n in (("10101", 3), ("10201", 1), ("90101", 2), ("92301", 2)):
        for sex in ("C11-1", "C11-2"):
            for age in range(1, 102):
                out.append({"C-A10-0": f"A10-{year}", "C-C11-0": sex,
                            "C-GRGEMAKT-0": f"GRGEMAKT-{commune}",
                            "C-GALTEJ112-0": f"GALTEJ112-{age}",
                            "F-ISIS-1": str(n + (1 if sex == "C11-1" and age < 30 else 0))})
    return out


AGES = [{"code": f"GALTEJ112-{i}", "name": f"{i - 1} Jahre"} for i in range(1, 101)] + \
       [{"code": "GALTEJ112-101", "name": "100 Jahre und älter"}]
SHAPES = [{"id": "a", "name": "Eisenstadt(Stadt)", "parent": "B"},
          {"id": "b", "name": "Rust(Stadt)", "parent": "B"},
          {"id": "c", "name": "Wien(Stadt)", "parent": "W"}]
LAENDER = [{"id": "B", "name": "Burgenland"}, {"id": "W", "name": "Wien"}]


class AustriaTest(unittest.TestCase):
    def run_build(self):
        def table(year, part=""):
            return AGES if part == "_C-GALTEJ112-0" else rows(year)

        def units(iso3, level):
            return SHAPES if level == "admin2" else LAENDER

        with mock.patch.object(austria, "table", table), \
                mock.patch.object(austria, "districts",
                                  lambda: {"101": "Eisenstadt(Stadt)", "102": "Rust(Stadt)"}), \
                mock.patch.object(austria, "units", units), \
                mock.patch.object(austria, "EXPECTED", 3), \
                mock.patch.object(central_ages, "eurostat_median", lambda geo, year: None):
            return austria.build(2026)

    def test_vienna_is_one_district_and_fields_are_computed(self):
        records = {r["shape_id"]: r for r in self.run_build()}
        self.assertEqual(set(records), {"a", "b", "c"})
        vienna = records["c"]
        self.assertEqual(vienna["population"]["value"], 2 * (2 * 2 * 101) + 2 * 29)
        self.assertEqual(vienna["sex_ratio"]["unit"], central_ages.SEX_RATIO_UNIT)
        self.assertGreater(vienna["sex_ratio"]["value"], 100)
        self.assertAlmostEqual(records["a"]["median_age"]["value"], 49.0, delta=2)
        self.assertEqual(records["a"]["match_by"], "shape_id")


class MedianOfGroupsTest(unittest.TestCase):
    def test_interpolates_within_the_group(self):
        groups = [(0, 4, 10), (5, 9, 10), (10, None, 0)]
        self.assertEqual(central_ages.median_of_groups(groups), 5.0)

    def test_open_group_stops(self):
        with self.assertRaises(SystemExit):
            central_ages.median_of_groups([(0, 4, 1), (85, None, 10)])


if __name__ == "__main__":
    unittest.main()
