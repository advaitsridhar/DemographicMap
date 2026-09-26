"""Saint Lucia: the report's wrapped tables, the 2010 settlements and their binding."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import lucia_census as lc  # noqa: E402

TOTALS = [100, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]
D2 = ["District", "Religion Anse La Canari Soufrie", "Saint Lucia",
      "Total " + " ".join(str(n) for n in TOTALS),
      "Roman Catholic 60 6 6 6 6 6 6 6 6 6 6",
      "Atheist - Do not believe in 20 2 2 2 2 2 2 2 2 2 2",
      "God",
      "Hinduism 10 1 1 1 1 1 1 1 1 1 1",
      "Hindu 10 1 1 1 1 1 1 1 1 1 1",
      "82"]
A9 = ["Households Population", "Total Total Male Female",
      "Saint Lucia 40 171,834 84,716 87,118",
      "Castries City 10 60,614 30,000 30,614",
      "Castries 5 30,000 15,000 15,000",
      "Hill 20 5 30,614 15,000 15,614",
      "Soufriere District 30 111,220 54,716 56,504",
      "Morne Caca Cochon/Mardis 10 111,220 54,716 56,504",
      "Gras/Derniere",
      "Riviere"]


def shape(sid: str, name: str, parent: str) -> dict:
    return {"id": sid, "name": name, "parent": parent}


SHAPES = [shape("a", "Monkey Town/Ciceron", "C"), shape("b", "Ciceron", "C"),
          shape("c", "Belle Vue", "C"), shape("d", "Belle Vue", "C"),
          shape("e", "Derniere Riviere/Morne Caca Cochon/Mardis Gras", "S"),
          shape("f", "Hill 20/Babonneau", "C")]
DISTRICT_OF = {"C": "Castries", "S": "Soufriere"}


class Report(unittest.TestCase):
    def test_religion_rows_wrap_and_two_hindu_lines_are_one(self):
        out = lc.religion_by_district(D2[:-1], island=100)
        self.assertEqual(out["Castries"], {"Roman Catholic": 6, "Atheist": 2, "Hindu": 2,
                                           "_total": 10})

    def test_a_religion_short_of_its_district_stops_the_run(self):
        lines = list(D2)
        lines[4] = "Roman Catholic 60 26 6 6 6 6 6 6 6 6 6"
        with self.assertRaises(SystemExit):
            lc.religion_by_district(lines, island=100)

    def test_settlements_group_by_district_and_keep_numbers_in_names(self):
        out = lc.settlements_2022(A9)
        self.assertEqual([r["name"] for r in out["Castries"]], ["Castries", "Hill 20"])
        self.assertEqual(out["Soufriere"][0]["name"],
                         "Morne Caca Cochon/Mardis Gras/Derniere Riviere")

    def test_settlements_short_of_their_district_stop_the_run(self):
        lines = list(A9)
        lines[4] = "Castries 5 20,000 10,000 10,000"
        with self.assertRaises(SystemExit):
            lc.settlements_2022(lines)


class Binding(unittest.TestCase):
    def test_2010_names_bind_within_the_district_and_duplicates_are_left_out(self):
        bound, left = lc.bind_2010(["MONKEY TOWN/CICERON - CASTRIES", "CICERON - CASTRIES",
                                    "BELLE VUE - CASTRIES", "HILL 20/BABONNEAU - CASTRIES",
                                    "CICERON - SOUFRIERE"], SHAPES, DISTRICT_OF)
        self.assertEqual(bound, {"MONKEY TOWN/CICERON - CASTRIES": "a",
                                 "CICERON - CASTRIES": "b",
                                 "HILL 20/BABONNEAU - CASTRIES": "f"})
        self.assertEqual(left, ["BELLE VUE - CASTRIES", "CICERON - SOUFRIERE"])

    def test_2022_names_bind_by_their_parts_in_any_order(self):
        rows = {"Castries": [{"name": "Ciceron/Monkey Town", "population": 5},
                             {"name": "Belle Vue - Castries", "population": 5}],
                "Soufriere": [{"name": "Morne Caca Cochon/Mardis Gras/Derniere Riviere",
                               "population": 5}]}
        out = lc.bind_2022(rows, SHAPES, DISTRICT_OF)
        self.assertEqual(sorted(out), ["a", "e"])

    def test_ages_are_read_by_place_when_a_label_is_wrong(self):
        self.assertEqual(lc.ages_of(["0 years", "1 year", "68 years", "3 years", "Not stated"]),
                         [0, 1, 2, 3, None])
        with self.assertRaises(SystemExit):
            lc.ages_of(["0 years", "2 years", "3 years", "4 years"])

    def test_a_district_suffix_is_split_off(self):
        self.assertEqual(lc.split_settlement("COOLIE TOWN - VIEUX-FORT"),
                         ("COOLIE TOWN", "Vieux Fort"))
        self.assertEqual(lc.split_settlement("CASTRIES"), ("CASTRIES", None))


if __name__ == "__main__":
    unittest.main()
