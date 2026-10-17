"""Algeria's 2008 census reader: two wilayas side by side, and their checks."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import algeria_census as ac  # noqa: E402

PAGE = """Population résidente par age, par sexe et par wilaya
Adrar  (1)  Chlef  (2)
Groupe d’âge Masculin Féminin Total
0-4 Ans 24567 23287 47854  0-4 Ans 51186 48293 99479
5-9 ans 22351 21253 43604  5-9 ans 44003 42433 86436
50-54ans 5912 5533 11445  50-54ans 18239 18459 36698
85 ans &  + 640 639 1279  85 ans &  + 1360 1547 2907
ND 31 39 70  ND 560 846 1406
Total 53501 50751 104252  Total 115348 111578 226926
"""


class Parsing(unittest.TestCase):
    def test_two_wilayas_per_block(self):
        table = ac.parse([PAGE])
        self.assertEqual(sorted(table), [1, 2])
        self.assertEqual(table[1]["name"], "Adrar")
        self.assertEqual(table[2]["name"], "Chlef")
        self.assertEqual(table[1]["groups"][0], (0, 4, 47854))
        self.assertEqual(table[1]["groups"][2], (50, 54, 11445))
        self.assertEqual(table[1]["groups"][-1], (85, None, 1279))
        self.assertEqual(table[2]["nd"], 1406)
        self.assertEqual(table[2]["total"], 226926)

    def test_men_and_women_must_make_the_total(self):
        bad = PAGE.replace("24567 23287 47854", "24567 23287 47855")
        with self.assertRaises(SystemExit):
            ac.parse([bad])

    def test_the_check_wants_all_48_and_unbroken_groups(self):
        with self.assertRaises(SystemExit):
            ac.check(ac.parse([PAGE]))


class Binding(unittest.TestCase):
    def test_by_iso_code_and_by_name_where_uncoded(self):
        table = {n: {"name": f"W{n}"} for n in range(1, 49)}
        admin1 = [{"id": f"S{n}", "name": f"W{n}", "iso_3166_2": f"DZ-{n:02d}"}
                  for n in range(1, 49) if n != 42]
        admin1.append({"id": "S42", "name": "Tipaza", "iso_3166_2": None})
        table[42]["name"] = "Tipaza"
        bound = ac.bind(table, admin1)
        self.assertEqual(bound[42]["id"], "S42")
        self.assertEqual(bound[7]["id"], "S7")


class Median(unittest.TestCase):
    def test_interpolates_within_the_group(self):
        self.assertEqual(ac.grouped_median([(0, 4, 50), (5, 9, 50), (10, None, 0)]), 5.0)


if __name__ == "__main__":
    unittest.main()
