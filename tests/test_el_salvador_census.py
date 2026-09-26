"""El Salvador's 2024 census tables: layouts read, identity questions joined, slivers set aside."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import el_salvador_census as sv  # noqa: E402

DEPT, MUN, DIST = "01 - Ahuachapán", "01 - Ahuachapán Centro", "02 - Apaneca"
POB = [
    ["", "#VALUE!", "VII CENSO DE POBLACIÓN", "", "", "", "", ""],
    ["", "", "Población total por departamento", "", "", "", "", ""],
    ["", "Departamento de residencia", "Municipio de residencia", "Distrito de residencia",
     "Edades simples", "Total", "Sexo", ""],
    ["", "", "", "", "", "", "1. Hombre", "2. Mujer"],
    ["", DEPT, "TOTAL", "TOTAL", "TOTAL", 10, 4, 6],
    ["", DEPT, "TOTAL", "TOTAL", "0", 4, 2, 2],
    ["", DEPT, "TOTAL", "TOTAL", "30", 6, 2, 4],
    ["", DEPT, MUN, DIST, "TOTAL", 10, 4, 6],
    ["", DEPT, MUN, DIST, "0", 4, 2, 2],
    ["", DEPT, MUN, DIST, "30", 6, 2, 4],
]
ETNIA2 = [
    ["#VALUE!", "VII CENSO", "", "", "", "", ""],
    ["", "Población por departamento, municipio, distrito", "", "", "", "", ""],
    ["Departamento de residencia", "Municipio de residencia", "Distrito de residencia",
     "Edad Quinquenal", "Identificación de pueblo indígena", "", ""],
    ["", "", "", "", "1. Si", "2. No", "9. No sabe/No responde"],
    [DEPT, MUN, DIST, "TOTAL", 2, 7, 1],
    [DEPT, MUN, DIST, "0 a 4 años", 1, 3, ""],
]
ETNIA3 = [
    ["#VALUE!", "VII CENSO", "", "", "", "", "", "", "", ""],
    ["", "Población afrodescendiente por departamento", "", "", "", "", "", "", "", ""],
    ["Departamento de residencia", "Municipio de residencia", "Distrito de residencia",
     "Edad Quinquenal", "1. Si", "", "2. No", "", "9. No sabe/No responde", ""],
    ["", "", "", "", "1. Hombre", "2. Mujer", "1. Hombre", "2. Mujer", "1. Hombre", "2. Mujer"],
    [DEPT, MUN, DIST, "TOTAL", 1, "", 4, 4, "", 1],
]


class Layout(unittest.TestCase):
    def test_single_years_by_sex_are_read_and_checked(self):
        with mock.patch.object(sv, "rows_of", return_value=POB):
            tables, title = sv.read("population", ages=True)
        self.assertIn("Población total", title)
        pop = sv.population(tables)
        unit = pop[(DEPT, MUN, DIST)]
        self.assertEqual((unit["people"], unit["men"], unit["women"]), (10, 4, 6))
        self.assertEqual(unit["ages"], {0: 4, 30: 6})
        sv.nest(pop, "population", ("people", "men", "women"))

    def test_ages_that_do_not_make_the_total_stop_the_run(self):
        rows = [list(r) for r in POB]
        rows[-1][5] = 7
        with mock.patch.object(sv, "rows_of", return_value=rows):
            tables, _ = sv.read("population", ages=True)
        with self.assertRaises(SystemExit):
            sv.population(tables)

    def test_the_answer_is_found_over_or_under_the_sexes(self):
        self.assertEqual(sv.answer_of("Identificación de pueblo indígena|9. No sabe/No responde"),
                         "unknown")
        self.assertEqual(sv.answer_of("1. Si|2. Mujer"), "yes")
        with self.assertRaises(SystemExit):
            sv.answer_of("3. Tal vez|1. Hombre")


class Identity(unittest.TestCase):
    def tables(self):
        peoples = {(DEPT, MUN, DIST): {"": {"1. Lenca|1. Hombre": 1, "1. Lenca|2. Mujer": 0,
                                            "10. otro|1. Hombre": 1, "Total Indígenas": 2}}}
        with mock.patch.object(sv, "rows_of", return_value=ETNIA2):
            indigenous, _ = sv.read("indigenous")
        with mock.patch.object(sv, "rows_of", return_value=ETNIA3):
            afro, title = sv.read("afro")
        self.assertIn("afro", sv.fold(title))
        return sv.identity(peoples, indigenous, afro)

    def test_the_two_questions_and_the_remainder(self):
        unit = self.tables()[(DEPT, MUN, DIST)]
        out = sv.ethnicity(unit, 10)
        groups = {g["group"]: g["count"] for g in out["ethnicity"]}
        self.assertEqual(groups, {"Lenca": 1, "Other indigenous people": 1, sv.AFRO: 1,
                                  sv.REST: 6})
        self.assertIn("1 did not know", out["ethnicity_note"])

    def test_overlap_past_the_population_falls_back_to_the_indigenous_question(self):
        unit = self.tables()[(DEPT, MUN, DIST)]
        unit["afro"]["yes"] = 8
        groups = {g["group"]: g["count"] for g in sv.ethnicity(unit, 10)["ethnicity"]}
        self.assertEqual(groups, {"Lenca": 1, "Other indigenous people": 1,
                                  sv.NOT_INDIGENOUS: 7})

    def test_peoples_must_make_the_questions_yes(self):
        peoples = {(DEPT, MUN, DIST): {"": {"1. Lenca|1. Hombre": 3}}}
        with mock.patch.object(sv, "rows_of", return_value=ETNIA2):
            indigenous, _ = sv.read("indigenous")
        with mock.patch.object(sv, "rows_of", return_value=ETNIA3):
            afro, _ = sv.read("afro")
        with self.assertRaises(SystemExit):
            sv.identity(peoples, indigenous, afro)


class Shapes(unittest.TestCase):
    def test_a_sliver_sharing_a_districts_name_is_set_aside(self):
        shapes = [{"id": "a", "name": "Chilanga", "parent": "m", "bbox": [-88.2, 13.69, -88.1, 13.78]},
                  {"id": "b", "name": "Chilanga", "parent": "m",
                   "bbox": [-88.1998, 13.7805, -88.1995, 13.781]},
                  {"id": "c", "name": "Null", "parent": "u", "bbox": [-88.5, 13.2, -88.49, 13.21]}]
        self.assertEqual(sv.slivers(shapes), {"b"})

    def test_every_label_is_placed_or_waits_on_the_proposed_tree_entry(self):
        import group_tree
        waiting = {"Lenca", "Kakawira (Cacaopera)", "Mixe", "Alagüilac", "Mangue"}
        for label in [*sv.PEOPLES.values(), sv.AFRO, sv.REST, sv.NOT_INDIGENOUS]:
            if label in waiting:
                continue
            self.assertIsNotNone(group_tree.parent_of("ethnicity", label), label)


if __name__ == "__main__":
    unittest.main()
