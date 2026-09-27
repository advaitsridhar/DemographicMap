"""Ages and sexes from the Bureau's Caribbean workbooks, with people of unstated age."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import caribbean_uscb as cu  # noqa: E402

NAMES = ["AREA_NAME", "ADM_LEVEL", "BTOTL", "B0004", "B0509", "B10PL", "B_UNSTATED",
         "MTOTL", "M0004", "M0509", "M10PL", "M_UNSTATED",
         "FTOTL", "F0004", "F0509", "F10PL", "F_UNSTATED"]


def rows(*areas):
    return [NAMES, ["alias"] * len(NAMES), *areas]


WHOLE = ["COUNTRY", 0, 101, 40, 40, 20, 1, 51, 20, 20, 10, 1, 50, 20, 20, 10, 0]
EAST = ["EAST", 1, 60, 20, 30, 9, 1, 31, 10, 15, 5, 1, 29, 10, 15, 4, 0]
WEST = ["WEST", 1, 41, 20, 10, 11, 0, 20, 10, 5, 5, 0, 21, 10, 5, 6, 0]
TEST = cu.Country(iso3="XXX", dataset="", year=2011, census="", level=1, national=101,
                  out="", population=True)


class AgeSex(unittest.TestCase):
    def test_the_unstated_make_the_total_and_stay_out_of_the_median(self):
        units = cu.read(TEST, rows(WHOLE, EAST, WEST))
        self.assertEqual(units["EAST"]["unstated"], 1)
        # 59 people of known age: the 29.5th is in 5-9, 9.5 into its 30.
        self.assertEqual(units["EAST"]["median"], 6.6)
        self.assertEqual((units["EAST"]["men"], units["EAST"]["women"]), (31, 29))

    def test_groups_that_miss_the_total_are_refused(self):
        bad = list(EAST)
        bad[3] = 25
        with self.assertRaises(SystemExit):
            cu.read(TEST, rows(WHOLE, bad, WEST))

    def test_areas_must_make_the_published_country(self):
        with self.assertRaises(SystemExit):
            cu.read(TEST, rows(WHOLE, EAST))

    def test_the_bahamas_binds_only_islands_the_map_draws_whole(self):
        bahamas = cu.COUNTRIES["BHS"]
        bound = dict(bahamas.units)
        self.assertNotIn("ABACO", bound)
        self.assertNotIn("EXUMA AND CAYS", bound)
        self.assertEqual(len(bound) + len(bahamas.skip), 18)


if __name__ == "__main__":
    unittest.main()
