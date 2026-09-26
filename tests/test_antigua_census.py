"""Antigua and Barbuda: Table 5.1 read and checked, and the base's labels."""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import antigua_census as ag  # noqa: E402

TABLE = """Parishes Census 2001 Census 2011
Total Male Female Total Male Female
Total 76,886 36,109 40,777 85,567 40,986 44,581
St. John City 24,451 11,400 13,051 22,219 10,697 11,522
St. John Rural 20,895 9,754 11,141 29,518 14,095 15,423
St. George 6,673 3,166 3,507 8,055 3,826 4,229
St. Peter 5,439 2,595 2,844 5,325 2,538 2,787
St. Philip 3,462 1,643 1,819 3,347 1,579 1,768
St. Paul 7,848 3,652 4,196 8,128 3,857 4,271
St. Mary 6,793 3,212 3,581 7,341 3,533 3,808
Barbuda 1,325 687 638 1,634 861 773
Institutional population is included in these figures (See page 1)
Table 5.2: Inter-Censual Changes in Total Population by Parish""".splitlines()


class Book(unittest.TestCase):
    def test_table_5_1_reads_2011_by_parish(self):
        out = ag.table_5_1(TABLE)
        self.assertEqual(out["St. John Rural"], (29_518, 14_095, 15_423))
        self.assertEqual(len(out), 8)

    def test_parishes_short_of_the_total_stop_the_run(self):
        lines = list(TABLE)
        lines[4] = "St. John Rural 20,895 9,754 11,141 29,517 14,094 15,423"
        with self.assertRaises(SystemExit):
            ag.table_5_1(lines)


class Base(unittest.TestCase):
    def test_single_years_and_unstated(self):
        known, unstated = ag.ages(Counter({"0": 5, "1": 3, "999": 2, "Not stated": 1}))
        self.assertEqual(known, Counter({0: 5, 1: 3}))
        self.assertEqual(unstated, 3)

    def test_an_unknown_category_stops_the_run(self):
        with self.assertRaises(SystemExit):
            ag.mapped(Counter({"Martian": 1}), ag.RELIGION, "religion")
        self.assertEqual(ag.mapped(Counter({"Adventist": 2, "Anglican": 1}), ag.RELIGION, "r"),
                         {"Seventh-day Adventist": 2, "Anglican": 1})

    def test_saint_john_is_the_city_and_the_rest(self):
        self.assertEqual(ag.PARISHES["Saint John"][0], ("St. John City", "St. John Rural"))


if __name__ == "__main__":
    unittest.main()
