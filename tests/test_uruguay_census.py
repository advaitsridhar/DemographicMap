"""Uruguay's 2023 census microdata: ancestry read, tables checked, municipios placed."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import uruguay_census as uc  # noqa: E402


def person(pid: str, dept: str = "11", sex: str = "1", age: str = "30",
           yes: tuple[int, ...] = (3,), main: str = "7777", weight: str = "1.5",
           municipio: str = "PIEDRAS COLORADAS", missing: str | None = None,
           group: str = "30-34", pais: str = "Piedras Coloradas") -> dict[str, str]:
    row = {"ID_CENSO": pid, "DEPARTAMENTO": dept, "PERPH02": sex, "PERNA01": age,
           "PERER02": main, "W": weight, "MUNICIPIO_136": municipio,
           "PERNA01_TRAMO": group, "MUNICIPIO_PAIS": pais}
    for k in uc.ANCESTRIES:
        row[f"PERER01_{k}"] = missing or ("1" if k in yes else "2")
    return row


class Ancestry(unittest.TestCase):
    def test_one_yes_is_that_ancestry(self):
        self.assertEqual(uc.principal(person("a", yes=(1,))), "Afro or Black")

    def test_several_take_the_principal_named(self):
        self.assertEqual(uc.principal(person("a", yes=(1, 3), main="1")), "Afro or Black")

    def test_several_and_no_principal_are_mixed(self):
        self.assertEqual(uc.principal(person("a", yes=(1, 4), main="6")), uc.MIXED)

    def test_no_to_all_five(self):
        self.assertEqual(uc.principal(person("a", yes=())), uc.NONE_OF_THEM)

    def test_the_unasked_and_the_silent_are_told_apart(self):
        self.assertEqual(uc.principal(person("a", missing="8888")), uc.NOT_ASKED)
        self.assertEqual(uc.principal(person("a", missing="9898")), uc.NO_ANSWER)

    def test_a_principal_the_person_did_not_say_yes_to_is_no_answer(self):
        self.assertEqual(uc.principal(person("a", yes=(1, 3), main="4")), uc.NO_ANSWER)


def cuadro_1_rows(change: dict[str, tuple[int, int, int]] | None = None) -> list[list[str]]:
    people = {c: (100_000 + i, 50_000, 50_000 + i) for i, c in enumerate(uc.DEPARTMENTS)}
    people.update(change or {})
    rest = sum(p for p, _, _ in people.values())
    people["01"] = (uc.NATIONAL - rest + people["01"][0], 0, 0)
    people["01"] = (people["01"][0], people["01"][0] // 2, people["01"][0] - people["01"][0] // 2)
    rows = [["CUADRO 1"], ["Departamento", "Total", "Hombres", "Mujeres"],
            ["Total", str(uc.NATIONAL), "1", str(uc.NATIONAL - 1)]]
    rows += [[uc.DEPARTMENTS[c], str(p), str(m), str(w)] for c, (p, m, w) in people.items()]
    return rows


class Tables(unittest.TestCase):
    def test_cuadro_1_is_read_by_department(self):
        found = uc.cuadro_1(cuadro_1_rows())
        self.assertEqual(len(found), 19)
        self.assertEqual(found["02"], (100_001, 50_000, 50_001))

    def test_a_department_not_its_men_and_women_stops_the_run(self):
        with self.assertRaises(SystemExit):
            uc.cuadro_1(cuadro_1_rows({"02": (100_001, 50_000, 40_000)}))

    def test_cuadro_14_keys_rows_by_department_and_name(self):
        rows = [["Departamento", "Nombre municipio", "Población Total"],
                ["Total", "", str(uc.NATIONAL)],
                ["Montevideo", "MUNICIPIO A", str(uc.NATIONAL - 10)],
                ["Montevideo", "Sin dato de Municipio", "10"]]
        found = uc.cuadro_14(rows)
        self.assertEqual(found[("01", uc.UNKNOWN)], 10)
        self.assertEqual(found[("01", "municipioa")], uc.NATIONAL - 10)
        with self.assertRaises(SystemExit):
            uc.cuadro_14(rows + [["Montevideo", "Municipio A", "0"]])


class Tallies(unittest.TestCase):
    def setUp(self):
        self.rows = [person("a", age="20", group="20-24"),
                     person("b", dept="12", sex="2", age="40", group="40-44"),
                     person("c", sex="2", age="60", yes=(1, 3), main="1", group="60-64",
                            pais="Sin Municipio"),
                     person("d", missing="8888", municipio="SIN MUNICIPIO", group="80+",
                            pais="Sin Municipio")]

    def test_july_weighs_people_by_department_and_its_own_municipios(self):
        departments, series = uc.july(self.rows)
        self.assertEqual(departments["11"].people, 4.5)
        self.assertEqual(departments["12"].women, 1.5)
        self.assertEqual(series[("11", "piedrascoloradas")], 3.0)
        self.assertEqual(departments["11"].median_age(), 30.5)

    def test_february_counts_people_by_municipio_in_five_year_groups(self):
        municipios = uc.february(self.rows)
        rest = municipios[("11", "Sin Municipio")]
        self.assertEqual((rest.rows, rest.people, rest.width), (2, 2.0, 5))
        self.assertEqual(rest.ancestry["Afro or Black"], 1.0)
        self.assertEqual(rest.median_age(), 65.0)

    def test_the_grouped_median_is_interpolated_within_its_group(self):
        self.assertEqual(uc.grouped_median({0: 10, 5: 10, 10: 20}), 10.0)
        self.assertEqual(uc.grouped_median({0: 10, 5: 30}), 6.7)
        self.assertEqual(uc.age_group("05-09"), 5)
        self.assertEqual(uc.age_group("80+"), 80)
        with self.assertRaises(SystemExit):
            uc.age_group("5555")

    def test_a_february_department_far_from_cuadro_1_stops_the_run(self):
        municipios = {(c, "Sin Municipio"): uc.Tally(5) for c in uc.DEPARTMENTS}
        for unit in municipios.values():
            unit.rows = 100_000
        municipios[("01", "Sin Municipio")].rows = uc.NATIONAL - 1_800_000
        published = {c: (u.rows, 0, 0) for (c, _), u in municipios.items()}
        self.assertEqual(uc.check_february(municipios, published)["02"], 100_000)
        published["02"] = (99_000, 0, 0)
        with self.assertRaises(SystemExit):
            uc.check_february(municipios, published)

    def test_departments_that_do_not_make_cuadro_1_stop_the_run(self):
        departments, _ = uc.july(self.rows)
        with self.assertRaises(SystemExit):
            uc.check_departments(departments, {"11": (5, 2, 3), "12": (1, 0, 1)})

    def test_the_ethnicity_note_counts_who_is_left_out(self):
        departments, _ = uc.july(self.rows)
        fields = uc.ethnicity_fields(departments["11"])
        self.assertEqual({r["group"]: r["count"] for r in fields["ethnicity"]},
                         {"White": 2, "Afro or Black": 2})
        self.assertIn("50.0% of the", fields["ethnicity_note"])
        self.assertIn("Left out: 2 people", fields["ethnicity_note"])


ADMIN1 = [{"id": "P", "name": "Paysandú"}, {"id": "R", "name": "Río Negro"},
          {"id": "F", "name": "Flores"}]


def shape(sid: str, name: str, parent: str) -> dict:
    return {"id": sid, "name": name, "parent": parent, "point": [0.0, 0.0]}


class Placing(unittest.TestCase):
    def setUp(self):
        self.admin2 = [shape("s1", "Piedras Coloradas", "P"), shape("s2", "Young", "R"),
                       shape("URY-REST-P", "Paysandú, outside any municipio", "P"),
                       shape("URY-REST-R", "Río Negro, outside any municipio", "R"),
                       shape("URY-REST-F", "Flores, outside any municipio", "F")]
        self.pairs = [("11", "Piedras Coloradas"), ("11", "Sin Municipio"),
                      ("12", "Piedras Coloradas"), ("12", "Young"), ("12", "Sin Municipio"),
                      ("07", "Sin Municipio"), ("07", "Ismael Cortinas"), ("12", "9898")]

    def test_each_pair_goes_to_its_polygon_or_is_left_with_the_reason(self):
        placed, left, why = uc.polygons(self.pairs, ADMIN1, self.admin2)
        self.assertEqual(placed[("12", "Piedras Coloradas")], "s1")
        self.assertEqual(placed[("07", "Ismael Cortinas")], "URY-REST-F")
        self.assertEqual(placed[("12", "Sin Municipio")], "URY-REST-R")
        self.assertEqual(left, [("12", "9898")])
        self.assertIn("Ismael Cortinas", why["URY-REST-F"])

    def test_a_drawn_polygon_no_municipio_reaches_stops_the_run(self):
        with self.assertRaises(SystemExit):
            uc.polygons([p for p in self.pairs if p[1] != "Young"], ADMIN1, self.admin2)

    def test_a_municipio_with_no_polygon_stops_the_run(self):
        with self.assertRaises(SystemExit):
            uc.polygons(self.pairs + [("12", "Nuevo Berlín")], ADMIN1, self.admin2)


if __name__ == "__main__":
    unittest.main()
