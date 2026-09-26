"""Barbados's 2021 parish tables and 2010 resident population, read and checked."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import barbados_census as bb  # noqa: E402

ETHNIC = [["Table 02.04"], ["Parish", "Sex", None, "Ethnic origin"],
          [None, None, "Total", "Black", "White", "Mixed", "Not Stated"],
          [None, None, "Count", "Count", "Count", "Count", "Count"],
          ["Barbados", "Total", 30, 24, 2, 3, 1],
          [None, "0 - 4", 10, 8, 0, 1, 1],
          ["St. Michael", "Total", 20, 16, 1, 2, 1],
          [None, "0 - 4", 5, 4, 0, 1, 0],
          ["St. Lucy", "Total", 10, 8, 1, 1, 0]]

AGES = [["Table 01.02"], ["Parish", "5 Year Age Groups", None, "Both Sexes", "Male", "Female"],
        ["St. Lucy", "Total", 10, 4, 6], [None, "0 - 4", 3, 1, 2], [None, "5 - 9", 3, 1, 2],
        [None, "85 and over", 4, 2, 2]]


class Tables(unittest.TestCase):
    def test_a_parish_line_is_its_total_row_and_its_categories_make_it(self):
        out = bb.compositions(ETHNIC, bb.ETHNICITY, "Total", "ethnicity")
        self.assertEqual(sorted(out), ["barbados", "saintlucy", "saintmichael"])
        self.assertEqual(out["saintmichael"]["counts"],
                         {"Black": 16, "White": 1, "Mixed": 2, "Not stated": 1})

    def test_categories_short_of_the_total_stop_the_run(self):
        rows = [list(r) for r in ETHNIC]
        rows[6][3] = 15
        with self.assertRaises(SystemExit):
            bb.compositions(rows, bb.ETHNICITY, "Total", "ethnicity")

    def test_an_unknown_category_stops_the_run(self):
        rows = [list(r) for r in ETHNIC]
        rows[2][5] = "Martian"
        with self.assertRaises(SystemExit):
            bb.compositions(rows, bb.ETHNICITY, "Total", "ethnicity")

    def test_age_groups_read_with_the_open_group_last(self):
        out = bb.ages(AGES)
        self.assertEqual(out["saintlucy"]["groups"][-1], (85, None, 4))
        self.assertEqual((out["saintlucy"]["men"], out["saintlucy"]["women"]), (4, 6))

    def test_st_and_saint_are_one_parish(self):
        self.assertEqual(bb.parish_key("St. Michael"), bb.parish_key("Saint Michael"))
        self.assertEqual(bb.parish_key("Christ Church"), "christchurch")


if __name__ == "__main__":
    unittest.main()
