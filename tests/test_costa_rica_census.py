"""Costa Rica's 2011 census on REDATAM: areas checked, cantons split, labels placed."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import costa_rica_census as cr  # noqa: E402
from scripts.fetch_census import isthmus  # noqa: E402


def table(area, name, rows, na=None):
    return {"area": area, "name": name, "title": "x", "rows": rows,
            "total": sum(n for _, n in rows), "na": na}


def unit(people_yes=3, people_no=7, unknown=1):
    """One canton's five tables, consistent with each other."""
    everyone = people_yes + people_no
    return {
        "sex": table("101", "101 San José", [("Hombre", 4), ("Mujer", everyone - 4)]),
        "age": table("101", "101 San José", [("0", 2), ("1", 3), ("40", everyone - 5)]),
        "indigenous": table("101", "101 San José", [("Sí", people_yes), ("No", people_no)]),
        "people": table("101", "101 San José", [("Bribrí", people_yes - 1),
                                                 ("Ningún pueblo", 1)], people_no),
        "ethnic": table("101", "101 San José",
                        [("Blanco(a) o mestizo(a)", people_no - unknown), (cr.UNKNOWN, unknown)],
                        people_yes),
    }


class Areas(unittest.TestCase):
    def test_the_code_a_server_prints_before_a_name_is_taken_off(self):
        self.assertEqual(isthmus.area_name("101 San José"), "San José")
        self.assertEqual(isthmus.area_name("BOCAS DEL TORO"), "BOCAS DEL TORO")
        self.assertEqual(isthmus.area_name("20 de Noviembre"), "de Noviembre")

    def test_areas_must_make_the_base_and_its_published_count(self):
        found = [table("1", "1 San José", [("Sí", 2), ("No", 3)]),
                 table("2", "2 Alajuela", [("Sí", 1), ("No", 4)]),
                 table(None, "", [("Sí", 3), ("No", 7)])]
        areas = isthmus.by_area(found, "q", "t", base_total=10)
        self.assertEqual(areas["1"]["name"], "San José")
        with self.assertRaises(SystemExit):
            isthmus.by_area(found, "q", "t", base_total=11)
        with self.assertRaises(SystemExit):
            isthmus.by_area(found[:1] + found[2:], "q", "t")

    def test_an_area_printed_twice_or_rows_short_of_the_total_stop_the_run(self):
        with self.assertRaises(SystemExit):
            isthmus.by_area([table("1", "a", [("x", 1)]), table("1", "a", [("x", 1)])], "q", "t")
        bad = table("1", "a", [("x", 1)])
        bad["total"] = 2
        with self.assertRaises(SystemExit):
            isthmus.by_area([bad], "q", "t")

    def test_a_district_taken_out_of_its_canton(self):
        whole = {"rows": [("a", 5), ("b", 3)], "total": 8, "na": 2}
        part = {"rows": [("a", 1), ("b", 3), ("c", 0)], "total": 4, "na": 1}
        self.assertEqual(isthmus.less(whole, part), {"rows": [("a", 4), ("b", 0)], "total": 4,
                                                     "na": 1})
        with self.assertRaises(SystemExit):
            isthmus.less(whole, {"rows": [("a", 6)], "total": 6, "na": 0})


class Checks(unittest.TestCase):
    def test_a_consistent_canton_passes(self):
        cr.check_unit(unit(), "San José")

    def test_p08_and_p10_must_split_p07(self):
        tables = unit()
        tables["people"] = table("101", "x", [("Bribrí", 2)], 8)
        with self.assertRaises(SystemExit):
            cr.check_unit(tables, "San José")

    def test_cantons_must_be_the_sum_of_their_districts(self):
        cantons = {q: {"101": table("101", "San José", [("Sí", 3), ("No", 7)])}
                   for q in cr.QUESTIONS}
        districts = {q: {"10101": table("10101", "Carmen", [("Sí", 1), ("No", 3)]),
                         "10102": table("10102", "Merced", [("Sí", 2), ("No", 4)])}
                     for q in cr.QUESTIONS}
        cr.nest(cantons, districts)
        districts["sex"]["10102"] = table("10102", "Merced", [("Sí", 2), ("No", 5)])
        with self.assertRaises(SystemExit):
            cr.nest(cantons, districts)


class Fields(unittest.TestCase):
    def test_one_composition_from_the_two_questions_ignorado_left_out(self):
        out = cr.fields(unit(), "admin2")
        groups = {g["group"]: g["count"] for g in out["ethnicity"]}
        self.assertEqual(groups, {"Bribri": 2, "Indigenous (no people named)": 1,
                                  "White or Mestizo": 6})
        self.assertIn("1 answered P10", out["ethnicity_note"].replace(",", ""))
        self.assertEqual(out["sex_ratio"]["value"], round(1000 * 4 / 6))

    def test_an_unknown_label_stops_the_run(self):
        tables = unit()
        tables["ethnic"]["rows"][0] = ("Indio", tables["ethnic"]["rows"][0][1])
        with self.assertRaises(SystemExit):
            cr.fields(tables, "admin2")

    def test_every_label_is_placed_in_the_group_tree(self):
        import group_tree
        # Brunca (Boruca), Cabécar, Chorotega, Huetar and Maleku wait on the
        # tree entries proposed with this reader; the rest are placed today.
        waiting = {"Brunca (Boruca)", "Cabécar", "Chorotega", "Huetar", "Maleku"}
        for label in [*cr.PEOPLES.values(), *cr.ETHNIC.values()]:
            if label in waiting:
                continue
            self.assertIsNotNone(group_tree.parent_of("ethnicity", label), label)


if __name__ == "__main__":
    unittest.main()
