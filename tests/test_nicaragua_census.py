"""Nicaragua's 2005 census on REDATAM: identity, religion and the checks that tie them."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import nicaragua_census as ni  # noqa: E402


def table(rows, na=None):
    return {"area": "0505", "name": "Jalapa", "title": "x", "rows": rows,
            "total": sum(n for _, n in rows), "na": na}


def unit():
    return {
        "sex": table([("Hombres", 50), ("Mujeres", 50)]),
        "age": table([("0", 6), ("4", 4), ("20", 90)]),
        "indigenous": table([("Si", 12), ("No", 85), ("No declarado", 3)]),
        "people": table([("Miskitu", 7), ("Creole(Kriol)", 3), ("No sabe", 1), ("Ignorado", 1)],
                        88),
        "religion": table([("Católica", 60), ("Evangélica", 20), ("Morava", 5),
                           ("Ninguna", 5)], 10),
    }


class Units(unittest.TestCase):
    def test_a_consistent_municipio_passes(self):
        ni.check_unit(unit(), "Jalapa")

    def test_religion_must_leave_out_exactly_the_under_fives(self):
        tables = unit()
        tables["religion"] = table([("Católica", 91)], 9)
        with self.assertRaises(SystemExit):
            ni.check_unit(tables, "Jalapa")

    def test_p07_must_count_those_p06_calls_indigenous(self):
        tables = unit()
        tables["people"] = table([("Miskitu", 11)], 89)
        with self.assertRaises(SystemExit):
            ni.check_unit(tables, "Jalapa")


class Fields(unittest.TestCase):
    def test_the_composition_and_what_is_left_out(self):
        out = ni.fields(unit())
        groups = {g["group"]: g["count"] for g in out["ethnicity"]}
        self.assertEqual(groups, {"Miskito": 7, "Creole": 3, "Indigenous (people not stated)": 2,
                                  "Not indigenous": 85})
        self.assertIn("3 did not answer P06", out["ethnicity_note"])
        faiths = {g["group"]: g["count"] for g in out["religion"]}
        self.assertEqual(faiths, {"Catholic": 60, "Evangelical": 20, "Moravian Church": 5,
                                  "No religion": 5})
        self.assertEqual(out["population"]["value"], 100)

    def test_the_boundary_files_municipio_wrappers_come_off(self):
        self.assertEqual(ni.unwrapped("Municipio de Jinotega"), "Jinotega")
        self.assertEqual(ni.unwrapped("Moyagalpa (Muncipio)"), "Moyagalpa")
        self.assertEqual(ni.unwrapped("Muncipio San Sebastián de Yalí"), "San Sebastián de Yalí")
        self.assertEqual(ni.unwrapped("Corn Island"), "Corn Island")

    def test_every_label_is_placed_or_waits_on_the_proposed_tree_entry(self):
        import group_tree
        waiting = {"Rama", "Mayangna", "Ulwa", "Xiu-Sutiaba", "Nahoa-Nicarao",
                   "Chorotega-Nahua-Mange", "Cacaopera-Matagalpa",
                   "Other indigenous people or ethnic community"}
        for field, labels in (("ethnicity", [*ni.PEOPLES.values(), ni.NOT_INDIGENOUS]),
                              ("religion", ni.RELIGION.values())):
            for label in labels:
                if label in waiting:
                    continue
                placed = (group_tree.parent_of(field, label) is not None
                          or label in group_tree.tier1_names(field))
                self.assertTrue(placed, label)


if __name__ == "__main__":
    unittest.main()
