"""Honduras's 2013 census on REDATAM: the two identity questions made one composition."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import honduras_census as hn  # noqa: E402


def table(rows, na=None):
    return {"area": "0101", "name": "LA CEIBA", "title": "x", "rows": rows,
            "total": sum(n for _, n in rows), "na": na}


def unit():
    people = table([("Garífuna", 4), ("Lenca", 4), ("Otro", 2)], 90)
    people["cells"] = {"Indígena": {"Lenca": 4, "Garífuna": 0, "Otro": 1},
                       "AfroHondureño": {"Lenca": 0, "Garífuna": 2, "Otro": 1},
                       "Negro (a)": {"Lenca": 0, "Garífuna": 2, "Otro": 0}}
    return {
        "sex": table([("Hombre", 48), ("Mujer", 52)]),
        "age": table([("edad", 10), ("1", 20), ("30", 70)]),
        "identity": table([("Indígena", 5), ("AfroHondureño", 3), ("Negro (a)", 2),
                           ("Mestizo (a)", 80), ("Blanco (a)", 8), ("Otro", 2)]),
        "people": people,
    }


CROSSTAB = ("<table>"
            "<tr><td>AREA # 0101</td><td>LA CEIBA</td></tr>"
            "<tr><td>Auto_identificación</td><td>Pueblo indígena</td></tr>"
            "<tr><td></td><td>Lenca</td><td>Garífuna</td><td>Otro</td><td>Total</td></tr>"
            "<tr><td>Indígena</td><td>4</td><td>-</td><td>1</td><td>5</td></tr>"
            "<tr><td>AfroHondureño</td><td>-</td><td>2</td><td>1</td><td>3</td></tr>"
            "<tr><td>Negro (a)</td><td>-</td><td>2</td><td>-</td><td>2</td></tr>"
            "<tr><td>Total</td><td>4</td><td>4</td><td>2</td><td>10</td></tr>"
            "<tr><td>No Aplica : 90</td></tr></table>")


class Crosstab(unittest.TestCase):
    def test_a_crosstab_by_area_is_read_and_checked(self):
        from scripts.fetch_census import isthmus
        (found,) = isthmus.crosstabs(CROSSTAB)
        self.assertEqual((found["area"], found["name"], found["na"]), ("0101", "LA CEIBA", 90))
        self.assertEqual(found["cells"]["AfroHondureño"],
                         {"Lenca": 0, "Garífuna": 2, "Otro": 1, "Total": 3})
        with self.assertRaises(SystemExit):
            isthmus.crosstabs(CROSSTAB.replace("<td>4</td><td>4</td><td>2</td><td>10</td>",
                                               "<td>4</td><td>5</td><td>2</td><td>11</td>"))

    def test_the_crosstab_must_agree_with_both_questions(self):
        from scripts.fetch_census import isthmus
        tables = unit()
        out = {q: {"0101": t} for q, t in tables.items()}
        hn.attach(out, isthmus.crosstabs(CROSSTAB))
        self.assertEqual(out["people"]["0101"]["cells"]["Indígena"],
                         {"Lenca": 4, "Garífuna": 0, "Otro": 1})
        out["identity"]["0101"] = table([("Indígena", 6), ("AfroHondureño", 3), ("Negro (a)", 2),
                                         ("Mestizo (a)", 79), ("Blanco (a)", 8), ("Otro", 2)])
        with self.assertRaises(SystemExit):
            hn.attach(out, isthmus.crosstabs(CROSSTAB))


class Units(unittest.TestCase):
    def test_a_consistent_municipio_passes(self):
        hn.check_unit(unit(), "La Ceiba")

    def test_p06_must_count_those_p05_sends_to_it(self):
        tables = unit()
        tables["people"] = table([("Garífuna", 4), ("Lenca", 5)], 91)
        with self.assertRaises(SystemExit):
            hn.check_unit(tables, "La Ceiba")

    def test_departments_must_be_the_sum_of_their_municipios(self):
        deps = {q: {"01": table([("x", 5)])} for q in hn.QUESTIONS}
        muns = {q: {"0101": table([("x", 2)]), "0102": table([("x", 3)])} for q in hn.QUESTIONS}
        hn.nest(deps, muns)
        muns["age"]["0103"] = table([("x", 1)])
        with self.assertRaises(SystemExit):
            hn.nest(deps, muns)


class Fields(unittest.TestCase):
    def test_age_zero_is_the_row_labelled_edad(self):
        self.assertEqual(hn.ages_of([("edad", 3), ("1", 2)]), {0: 3, 1: 2})
        with self.assertRaises(SystemExit):
            hn.ages_of([("1", 2), ("edad", 3)])

    def test_peoples_and_the_rest_of_p05_make_one_composition(self):
        out = hn.fields(unit())
        groups = {g["group"]: g["count"] for g in out["ethnicity"]}
        self.assertEqual(groups, {"Garifuna": 4, "Lenca": 4, "Other indigenous people": 1,
                                  "Afro-Honduran or Black (no people listed)": 1,
                                  "Mestizo": 80, "White": 8, "Other": 2})
        self.assertEqual(sum(groups.values()), 100)
        self.assertEqual(out["sex_ratio"]["value"], 923)
        self.assertEqual(out["median_age"]["value"], 30.3)

    def test_every_label_is_placed_or_waits_on_the_proposed_tree_entry(self):
        import group_tree
        waiting = {"Lenca", "Tolupan", "Pech", "Tawahka", "English-speaking Black (Honduras)",
                   "Afro-Honduran or Black (no people listed)"}
        for label in [*hn.PEOPLES.values(), *hn.IDENTITY.values(), *hn.OTHER.values()]:
            if label in waiting:
                continue
            self.assertIsNotNone(group_tree.parent_of("ethnicity", label), label)


if __name__ == "__main__":
    unittest.main()
