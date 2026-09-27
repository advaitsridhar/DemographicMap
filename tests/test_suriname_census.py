"""Suriname: ressort names across sources, the two-abreast age tables, the 2004 profile."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import suriname_census as s  # noqa: E402

AGES = ["Tabel 9.1: Paramaribo Tabel 9.2: Brokopondo",
        "Ressort Weg naar Zee Ressort Centrum",
        "Leeftijds Geslacht Leeftijds Geslacht",
        "0 - 4 10 5 5 0 - 4 4 2 2",
        "85+ 6 3 3 85+ 2 1 1",
        "Onbekend 2 1 1 Onbekend 0 0 0",
        "Totaal 18 9 9 Totaal 6 3 3"]


class Names(unittest.TestCase):
    def test_the_sources_and_the_map_spell_one_ressort(self):
        for a, b in (("Weg Naar See", "Weg naar Zee"), ("Almaar", "Alkmaar"),
                     ("Marchallkreeek", "Marshallkreek"), ("Brokopondo Centrum", "Centrum"),
                     ("Welgelegen (Coronie)", "Welgelegen"), ("Para Zuid", "Zuid"),
                     ("Nw. Amsterdam", "Nieuw Amsterdam"), ("Coeroenie", "Coeroeni")):
            self.assertEqual(s.key(a), s.key(b), (a, b))


class Ages(unittest.TestCase):
    def test_two_tables_abreast_are_read_apart(self):
        out = s.age_tables(AGES)
        self.assertEqual(out[("Paramaribo", "wegnaarzee")]["groups"],
                         [(0, 4, 10), (85, None, 6)])
        self.assertEqual(out[("Brokopondo", "centrum")]["total"], 6)

    def test_ages_short_of_the_total_stop_the_run(self):
        lines = list(AGES)
        lines[-1] = "Totaal 19 10 9 Totaal 6 3 3"
        with self.assertRaises(SystemExit):
            s.age_tables(lines)


class Districts(unittest.TestCase):
    def test_table_10_names_its_districts_on_their_first_line(self):
        lines = []
        for first, second in zip(s.DISTRICTS[0::2], s.DISTRICTS[1::2]):
            lines += [f"{first} 0 - 4 1,000 500 500 {second} 0 - 4 10 5 5",
                      "85+ 100 40 60 85+ 2 1 1", "Onbekend 1 1 0 Onbekend 0 0 0",
                      "Totaal 1,101 541 560 Totaal 12 6 6"]
        old = s.NATIONAL_2012
        s.NATIONAL_2012 = 5 * 1_101 + 5 * 12
        try:
            out = s.table_10(lines)
        finally:
            s.NATIONAL_2012 = old
        self.assertEqual(out["Wanica"]["groups"], [(0, 4, 10), (85, None, 2)])
        self.assertEqual(out["Paramaribo"]["total"], 1_101)


class Profile(unittest.TestCase):
    ROWS = [["", "Tabel"], [3.0, "Variabele", "Total", "Flora", "Kwatta"],
            [5.0, "Religion"], ["", "Total", 10.0, 6.0, 4.0],
            ["", "Christianity", 7.0, 5.0, 2.0], ["", "No religion", 3.0, 1.0, 2.0],
            [10.0, "Heads of Households"], ["", "Number of Households", 4.0, 3.0, 1.0],
            [11.0, "Most Spoken Language in the household", "Dutch", "Dutch", "Sarnami"],
            ["", "Dutch", 3.0, 3.0, 0.0], ["", "Sarnami", 1.0, 0.0, 1.0]]

    def test_religion_and_household_language_by_ressort(self):
        rows = [list(r) for r in self.ROWS]
        rows[1] = ["NR", "Variabele", "Total", "Flora", "Kwatta"]
        out = s.profile(rows)
        self.assertEqual(out["Kwatta"]["language"]["Sarnami Hindustani"], 1)
        self.assertEqual(out["Flora"]["religion"]["Christianity"], 5)

    def test_an_unknown_language_stops_the_run(self):
        rows = [list(r) for r in self.ROWS]
        rows[1] = ["NR", "Variabele", "Total", "Flora", "Kwatta"]
        rows[-1][1] = "Klingon"
        with self.assertRaises(SystemExit):
            s.profile(rows)


class Binding(unittest.TestCase):
    def test_a_ressort_the_map_files_elsewhere_binds_when_unique(self):
        shapes = [{"id": "a", "name": "Kwatta", "parent": "S"},
                  {"id": "b", "name": "Centrum", "parent": "P"},
                  {"id": "c", "name": "Centrum", "parent": "B"}]
        district_of = {"S": "Saramacca", "P": "Paramaribo", "B": "Brokopondo"}
        bound, left, across = s.bind([("Wanica", "kwatta"), ("Paramaribo", "centrum"),
                                      ("Brokopondo", "centrum"), ("Paramaribo", "latour")],
                                     shapes, district_of)
        self.assertEqual({k: v["id"] for k, v in bound.items()},
                         {("Wanica", "kwatta"): "a", ("Paramaribo", "centrum"): "b",
                          ("Brokopondo", "centrum"): "c"})
        self.assertEqual(across, [("Wanica", "kwatta")])
        self.assertEqual(left, [("Paramaribo", "latour")])


if __name__ == "__main__":
    unittest.main()
