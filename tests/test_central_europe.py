"""Readers for the central European offices: the parts that do not need the network."""

from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_census import netherlands_gemeente as nld  # noqa: E402
from fetch_census import slovakia as svk  # noqa: E402


def cell(area: str, sex: str, age: str, value: float):
    return ({"om7009rr_vuc": (area, f"District of {area}"), "om7009rr_poh": (sex, sex),
             "om7009rr_vek": (age, age)}, value)


class SlovakDataCube(unittest.TestCase):
    def test_sex_totals_are_read_from_the_all_ages_cells_only(self):
        rows = [cell("SK0101", "SPOLU", "Spolu", 30.0), cell("SK0101", "1", "Spolu", 14.0),
                cell("SK0101", "2", "Spolu", 16.0), cell("SK0101", "1", "Y5", 3.0)]
        sexes, names = svk.by_sex(rows)
        self.assertEqual(sexes, {"SK0101": {"SPOLU": 30.0, "1": 14.0, "2": 16.0}})
        self.assertEqual(names["SK0101"], "District of SK0101")

    def test_the_open_group_below_the_last_single_year_is_a_subtotal_and_left_out(self):
        rows = [cell("SK0", "1", "Y0", 10.0), cell("SK0", "2", "Y0", 10.0),
                cell("SK0", "1", "Y1", 5.0), cell("SK0", "2", "Y1", 5.0),
                # 1+ is the sum of the single years 1 and the open 2+
                cell("SK0", "1", "Y_GE1", 7.0), cell("SK0", "1", "Y_GE2", 2.0),
                cell("SK0", "SPOLU", "Y0", 20.0), cell("SK0", "1", "Spolu", 17.0)]
        self.assertEqual(svk.national_ages(rows), Counter({0: 20.0, 1: 10.0, 2: 2.0}))

    def test_an_age_code_it_does_not_know_stops_the_run(self):
        with self.assertRaises(SystemExit):
            svk.national_ages([cell("SK0", "1", "Y0T4", 1.0)])


class DutchKeyFiguresFromTheWfs(unittest.TestCase):
    def feature(self, code, name, men, women, water="NEE"):
        return {"properties": {"gemeentecode": code, "gemeentenaam": name, "mannen": men,
                               "vrouwen": women, "water": water, "jaar": 2022}}

    def test_abroad_and_the_placeholders_are_left_out(self):
        payload = {"features": [self.feature("GM0998", "Buitenland", -99999999, -99999999, "B"),
                                self.feature("GM0363", "Amsterdam", 430000, 440000)]}
        out = nld.features(payload)
        self.assertEqual(list(out), ["GM0363"])
        self.assertEqual(out["GM0363"]["total"], 870000.0)

    def test_a_gemeente_met_twice_must_carry_the_same_counts(self):
        same = {"features": [self.feature("GM0003", "Appingedam", 5800, 6000),
                             self.feature("GM0003", "Appingedam", 5800, 6000, "JA")]}
        self.assertEqual(len(nld.features(same)), 1)
        differ = {"features": [self.feature("GM0003", "Appingedam", 5800, 6000),
                               self.feature("GM0003", "Appingedam", 5801, 6000, "JA")]}
        with self.assertRaises(SystemExit):
            nld.features(differ)


if __name__ == "__main__":
    unittest.main()
