"""The Bahamas' island reports: single years, wrapped religions, race by sex."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import bahamas_census as b  # noqa: E402

AGES = ["TABLE4.5 ACKLINS", "LAST BIRTHDAY TOTAL MALE FEMALE", "ALLAGES 10 6 4",
        "0-4 4 2 2", "UNDERONEYEAR 1 1 0", "1 1 0 1", "2 1 1 0", "3 0 0 0", "4 1 0 1",
        "TABLE4.5CONT'D ACKLINS", "5-9YEARS 3 2 1", "5 3 2 1", "90YEARSANDOVER 2 1 1",
        "NOTSTATED 1 1 0", "TABLE 5.0 ACKLINS", "SINGLE 99 50 49"]
RELIGION = ["TABLE 7.0 ACKLINS", "AGE-GROUP", "RELIGIONANDSEX TOTAL 0 -4 5-14 NOT STATED",
            "TOTAL 10 1 1 1 1 1 1 1 3", "MALE 6 1 1 1 1 1 1 0 0", "FEMALE 4 0 0 0 0 0 0 1 3",
            "ANGLICAN 4 1 1 1 1 0 0 0 0", "MALE 2 1 1 0 0 0 0 0 0",
            "TOTAL POPULATIONBY SEX, AGEGROUPANDRELIGION", "TABLE 7.0 CONT'D ACKLINS",
            "OTHERCHRISTIAN", "DENOMINATION 6 0 0 0 0 1 1 1 3", "MALE 3 0 0 0 0 1 1 1 0"]
RACE = ["TABLE 8.0 ACKLINS", "TOTAL 10 1 1 1 1 1 1 1 1 1 1", "BLACK 9 1 1 1 1 1 1 1 1 1 0",
        "WHITE 1 0 0 0 0 0 0 0 0 0 1", "MALE 6 1 1 1 1 1 1 0 0 0 0",
        "BLACK 5 1 1 1 1 1 0 0 0 0 0"]


class Report(unittest.TestCase):
    def test_single_years_are_read_and_make_the_total(self):
        out = b.table_4_5(AGES)
        self.assertEqual(out["ages"], {0: 1, 1: 1, 2: 1, 3: 0, 4: 1, 5: 3, 90: 2})
        self.assertEqual((out["total"], out["unstated"]), (10, 1))

    def test_single_years_short_of_their_group_stop_the_run(self):
        lines = list(AGES)
        lines[3] = "0-4 5 3 2"
        with self.assertRaises(SystemExit):
            b.table_4_5(lines)

    def test_religions_over_pages_and_a_wrapped_label(self):
        total, counts = b.composition(RELIGION, "TABLE7.0", b.RELIGION, 9)
        self.assertEqual((total, counts), (10, {"Anglican": 4, "Other Christian": 6}))

    def test_races_stop_at_the_mens_rows(self):
        total, counts = b.composition(RACE, "TABLE8.0", b.RACE, 11)
        self.assertEqual(counts, {"Black": 9, "White": 1})

    def test_a_neighbours_table_and_a_joint_table_are_not_the_islands(self):
        lines = ["TABLE4.17 RUMCAY", "ALLAGES 3 2 1", "0-4 3 2 1", "1 3 2 1",
                 "TABLE4.18 SANSALVADOR", "ALLAGES 5 3 2", "0-4 1 1 0", "UNDER1YEAR 1 1 0",
                 "90-YEARS&OVER 4 2 2", "TABLE 7.0 SANSALVADOR&RUMCAY", "ANGLICAN 8"]
        self.assertEqual(b.table_4_5(lines, "SANSALVADOR")["ages"], {0: 1, 90: 4})
        self.assertEqual(b.table_4_5(lines, "RUMCAY")["ages"], {1: 3})
        self.assertEqual(b.after(lines, "TABLE7.0", "SANSALVADOR"), [])
        self.assertEqual(b.after(lines, "TABLE7.0", "RUMCAY"), [])

    def test_table_2_0_rows_without_thousands_commas(self):
        out = b.table_2_0(["TABLE2.0", "NORTHANDROS 3898 1943 1955 1189",
                           "ACKLINS 565 320 245 209"])
        self.assertEqual(out["northandros"], (3898, 1943, 1955))


if __name__ == "__main__":
    unittest.main()
