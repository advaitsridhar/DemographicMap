"""Trinidad and Tobago's Demographic Report: wrapped labels, dashes and age tables."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import tto_census as t  # noqa: E402

UNITS = {t.key(u) for u in t.UNITS}
LEFT = """TABLE 2a
TOTAL POPULATION BY SEX, AGE GROUP AND MUNICIPALITY
BOTH SEXES
ALL 0 - 4 5 - 9 10 - 14 15 - 19 20 - 24 25 - 29 30 - 34 35 - 39
AGES
(1) (2) (3) (4) (5) (6) (7) (8) (9)
City of 100 10 10 10 10 10 10 10 10
San Fernando
Borough of Arima 50 5 5 5 5 5 5 5 5
TRINIDAD AND TOBAGO 2011 POPULATION AND HOUSING CENSUS
46""".splitlines()
RIGHT = """TABLE 2a
BOTH SEXES
40 - 44 45 - 49 50 - 54 55 - 59 60 - 64 65 - 69 70 - 74 75 - 79 80+ Not
(10) (11) (12) (13) (14) (15) (16) (17) (18) (19)
2 2 2 2 2 2 2 2 2 2 City of
San Fernando
1 1 1 1 1 1 1 1 1 1 Borough of Arima
TRINIDAD AND TOBAGO 2011 POPULATION AND HOUSING CENSUS""".splitlines()
RELIGION = """TABLE 8
BOTH SEXES
All Ages 0 - 4 5 - 9
(1) (2) (3)
Borough of Arima 50 1 1
Orisha 10 1 1
Pentecostal/ Evangelical/
30 - -
Full Gospel
Presbyterian/
10 - -
Congregational
DEMOGRAPHIC REPORT""".splitlines()


class Parsing(unittest.TestCase):
    def test_a_dash_is_a_zero_among_figures_and_a_word_in_a_label(self):
        self.assertEqual(t.split("Mixed - Other 200 - 3"), ("Mixed - Other", [200, 0, 3]))
        self.assertEqual(t.split("- 1 1 Portuguese"), ("Portuguese", [0, 1, 1]))
        self.assertEqual(t.split("Mixed - African/ East"), ("Mixed - African/ East", []))
        self.assertEqual(t.split("Indigenous - - -"), ("Indigenous", [0, 0, 0]))

    def test_a_label_wrapped_around_its_figures_is_read_whole(self):
        known = UNITS | {t.key(c) for c in t.ETHNICITY}
        lines = ["(1) (2) (3)", "Borough of Arima 50 1 1", "Mixed - African/ East",
                 "40 - 1", "Indian", "Mixed - Other 10 1 -"]
        self.assertEqual(t.rows(lines, known)[1], ("Mixed - African/ East Indian", [40, 0, 1]))

    def test_wrapped_labels_are_put_back_together(self):
        known = UNITS | {t.key(c) for c in t.RELIGION}
        table = t.rows(RELIGION, known)
        self.assertEqual([label for label, _ in table],
                         ["Borough of Arima", "Orisha", "Pentecostal/ Evangelical/ Full Gospel",
                          "Presbyterian/ Congregational"])
        counts = t.blocks(table, UNITS, t.RELIGION)[t.key("Borough of Arima")]
        self.assertEqual(counts["Pentecostal/Evangelical/Full Gospel"], 30)

    def test_age_pages_join_and_must_make_the_total(self):
        ages = t.ages(t.rows(LEFT, UNITS), t.rows(RIGHT, UNITS))
        sf = ages[t.key("City of San Fernando")]
        self.assertEqual(sf["unstated"], 2)
        self.assertEqual(sf["groups"][-1], (80, None, 2))
        bad = list(LEFT)
        bad[6] = "City of 200 10 10 10 10 10 10 10 10"
        with self.assertRaises(SystemExit):
            t.ages(t.rows(bad, UNITS), t.rows(RIGHT, UNITS))

    def test_an_unknown_label_stops_the_run(self):
        with self.assertRaises(SystemExit):
            t.rows(["(1)", "Atlantis 5 5"], UNITS)

    def test_the_map_s_tunapuna_piarco_holds_arima_too(self):
        self.assertEqual(t.POLYGONS["Tunapuna-Piarco"], ("Tunapuna/ Piarco", "Borough of Arima"))
        held = [u for units in t.POLYGONS.values() for u in units]
        self.assertEqual(sorted(held), sorted(t.MUNICIPALITIES + ("TOBAGO",)))


if __name__ == "__main__":
    unittest.main()
