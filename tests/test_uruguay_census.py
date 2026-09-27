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
           municipio: str = "PIEDRAS COLORADAS", missing: str | None = None) -> dict[str, str]:
    row = {"DIRECCION_ID": pid, "DEPARTAMENTO": dept, "PERPH02": sex, "PERNA01": age,
           "PERER02": main, "W": weight, "MUNICIPIO_136": municipio}
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
        self.where = {"a": ("11", "Piedras Coloradas"), "b": ("12", "Piedras Coloradas"),
                      "c": ("11", "Sin Municipio")}
        self.rows = [person("a", age="20"), person("b", dept="12", sex="2", age="40"),
                     person("c", sex="2", age="60", yes=(1, 3), main="1"),
                     person("d", missing="8888", municipio="SIN MUNICIPIO")]

    def test_people_are_weighed_by_department_and_by_february_municipio(self):
        departments, municipios, series, unplaced = uc.tally(self.rows, self.where)
        self.assertEqual(departments["11"].people, 4.5)
        self.assertEqual(municipios[("12", "Piedras Coloradas")].women, 1.5)
        self.assertEqual(unplaced["rows"], 1)
        self.assertEqual(series[("11", "piedrascoloradas")], 3.0)
        self.assertEqual(municipios[("11", "Sin Municipio")].ancestry["Afro or Black"], 1.5)

    def test_an_address_the_february_file_puts_in_two_municipios_places_no_one(self):
        rows = [{"DIRECCION_ID": "a", "DEPARTAMENTO": "11", "MUNICIPIO_PAIS": "Guichón"},
                {"DIRECCION_ID": "a", "DEPARTAMENTO": "11", "MUNICIPIO_PAIS": "Guichón"},
                {"DIRECCION_ID": "b", "DEPARTAMENTO": "11", "MUNICIPIO_PAIS": "Guichón"},
                {"DIRECCION_ID": "b", "DEPARTAMENTO": "11", "MUNICIPIO_PAIS": "Tambores"},
                {"DIRECCION_ID": "", "DEPARTAMENTO": "11", "MUNICIPIO_PAIS": "Tambores"}]
        where, counts, stats = uc.placements(rows)
        self.assertEqual(where, {"a": ("11", "Guichón"), "b": None})
        self.assertEqual(counts[("11", "Tambores")], 2)
        self.assertEqual(stats["no address"], 1)
        self.assertEqual(stats["address in two municipios"], 1)

    def test_too_many_people_the_february_file_does_not_have_stop_the_run(self):
        _, _, _, unplaced = uc.tally(self.rows, self.where)
        with self.assertRaises(SystemExit):
            uc.check_placements(unplaced, len(self.rows))

    def test_departments_that_do_not_make_cuadro_1_stop_the_run(self):
        departments, _, _, _ = uc.tally(self.rows, self.where)
        with self.assertRaises(SystemExit):
            uc.check_departments(departments, {"11": (5, 2, 3), "12": (1, 0, 1)})

    def test_the_ethnicity_note_counts_who_is_left_out(self):
        departments, _, _, _ = uc.tally(self.rows, self.where)
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
