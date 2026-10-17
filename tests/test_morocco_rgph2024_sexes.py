"""Morocco's 2024 sexes by region and province, from HCP's results dashboard."""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import morocco_rgph2024_sexes as ms  # noqa: E402


def body(rows):
    data = [{"Zone": z, "Milieu": m, "Sexe": s, "Titre de l'indicateur": "Population municipale",
             "Valeurs de l'indicateur": v} for z, m, s, v in rows]
    return {"result": [{"colnames": ["Zone", "Milieu", "Sexe", "Titre de l'indicateur",
                                     "Valeurs de l'indicateur"], "data": data}]}


ROWS = [("Royaume du Maroc", "Ensemble", "Masculin", 30.0),
        ("Royaume du Maroc", "Ensemble", "Féminin", 33.0),
        ("Royaume du Maroc", "Urbain", "Masculin", 20.0),
        ("Oriental", "Ensemble", "Masculin", 30.0), ("Oriental", "Ensemble", "Féminin", 33.0),
        ("Oriental -> Oujda-Angad", "Ensemble", "Masculin", 10.0),
        ("Oriental -> Oujda-Angad", "Ensemble", "Féminin", 11.0),
        ("Oriental -> Nador", "Ensemble", "Masculin", 20.0),
        ("Oriental -> Nador", "Ensemble", "Féminin", 22.0),
        ("Oriental -> Nador", "Rural", "Féminin", None),
        ("Oriental -> Nador -> Zeghanghane", "Ensemble", "Masculin", 2.0)]
TABLE = {"regions": {2: {"name": "Région de l'Oriental", "code": 2}},
         "provinces": {2381: {"name": "Préfecture d'Oujda-Angad", "code": 2381},
                       2411: {"name": "Province de Nador", "code": 2411}}}


class Chart(unittest.TestCase):
    def test_the_whole_population_by_sex_at_each_level(self):
        chart = ms.read_chart(body(ROWS))
        self.assertEqual(chart["kingdom"], {"men": 30, "women": 33})
        self.assertEqual(chart["regions"]["oriental"]["women"], 33)
        self.assertEqual(chart["provinces"][("oriental", "nador")]["men"], 20)
        ms.check(chart, TABLE)

    def test_provinces_that_do_not_make_their_region_stop_the_run(self):
        rows = [r if r[0] != "Oriental -> Nador" or r[2] != "Masculin" else
                ("Oriental -> Nador", "Ensemble", "Masculin", 21.0) for r in ROWS]
        with self.assertRaises(SystemExit):
            ms.check(ms.read_chart(body(rows)), TABLE)

    def test_a_province_across_the_line_may_be_missing(self):
        rows = ROWS + [("Dakhla-Oued Ed-Dahab", "Ensemble", "Masculin", 9.0),
                       ("Dakhla-Oued Ed-Dahab", "Ensemble", "Féminin", 8.0),
                       ("Dakhla-Oued Ed-Dahab -> Oued Ed-Dahab", "Ensemble", "Masculin", 8.0),
                       ("Dakhla-Oued Ed-Dahab -> Oued Ed-Dahab", "Ensemble", "Féminin", 8.0)]
        rows = [r if r[0] != "Royaume du Maroc" or r[1] != "Ensemble" else
                (r[0], r[1], r[2], r[3] + (9.0 if r[2] == "Masculin" else 8.0)) for r in rows]
        table = {"regions": {**TABLE["regions"], 12: {"name": "Dakhla-Oued Ed-Dahab"}},
                 "provinces": {**TABLE["provinces"], 12391: {"name": "Province d'Aousserd"}}}
        ms.check(ms.read_chart(body(rows)), table)

    def test_a_province_missing_from_the_chart_stops_the_run(self):
        table = {**TABLE, "provinces": {**TABLE["provinces"],
                                        1: {"name": "Province de Berkane", "code": 1}}}
        with self.assertRaises(SystemExit):
            ms.check(ms.read_chart(body(ROWS)), table)


class Building(unittest.TestCase):
    def test_bound_units_take_their_sexes_and_gaps_are_left_alone(self):
        chart = ms.read_chart(body(ROWS))
        bound = [{"level": "admin1", "name": "Oriental", "shape_id": "R",
                  "codes": {"hcp": "2"}, "population": {"value": 63}},
                 {"level": "admin2", "name": "Province de Nador", "shape_id": "N",
                  "codes": {"hcp": "2411"}, "population": {"value": 42}},
                 {"level": "admin2", "name": "a piece", "shape_id": "X",
                  "codes": {}, "population": {"status": "not_available"}}]
        with mock.patch.object(ms.legal, "build", return_value=(bound, [])):
            records, _ = ms.build(chart, TABLE, [], [])
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(set(by), {"R", "N"})
        self.assertEqual(by["N"]["sex_ratio"]["value"], 909)
        self.assertIn("municipal population", by["R"]["sex_ratio_note"])


if __name__ == "__main__":
    unittest.main()
