"""Guyana: Table 2.3's cut figures made whole, and the tables' checks."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import guyana_census as g  # noqa: E402

CUT = ["Ethnic Regio Regio Region",
       "African / 635 5,891 22,774 126,37 16,47 23,383 2,135 858 353 19,60 218,48",
       "Black 8 2 4 3",
       "Chinese 14 41 192 737 44 178 25 9 10 127 1,377"]


class Tables(unittest.TestCase):
    def test_cut_figures_take_the_digits_below_them_in_order(self):
        out = g.table_2_3(CUT)
        self.assertEqual(out["African / Black"],
                         [635, 5891, 22774, 126378, 16472, 23383, 2135, 858, 353, 19604, 218483])
        self.assertEqual(out["Chinese"][-1], 1377)

    def test_too_few_digits_below_stop_the_run(self):
        lines = list(CUT)
        lines[2] = "Black 8 2 4"
        with self.assertRaises(SystemExit):
            g.table_2_3(lines)

    def test_religion_labels_wrap_below_their_figures(self):
        lines = ["Religious", "Region Region", "1 2 3 4 5 6 7 8 9 10",
                 "Seventh 941 3,792 2,899 14,262 2,896 5,670 3,182 293 505 5,934 40,374",
                 "Day", "Adventist",
                 "Total 941 3,792 2,899 14,262 2,896 5,670 3,182 293 505 5,934 40,374"]
        out = g.table_2_19(lines)
        self.assertEqual(list(out), ["Seventh Day Adventist", "Total"])

    def test_a_grid_that_does_not_add_up_stops_the_run(self):
        rows = {"Mixed": [1] * 10 + [10], "Total": [1] * 10 + [11]}
        with self.assertRaises(SystemExit):
            g.check_grid(rows, "test")

    def test_median_ages_take_the_region_number_from_the_line_below(self):
        lines = []
        for r in range(1, 11):
            lines += [f"Region 1.0 1.0 1.0 1.0 1.0 1.0 1.0 1.0 {r}.5", str(r)]
        self.assertEqual(g.table_2_13(lines)[10], 10.5)


if __name__ == "__main__":
    unittest.main()
