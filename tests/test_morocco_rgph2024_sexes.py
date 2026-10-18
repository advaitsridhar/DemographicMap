"""Morocco's 2024 sexes and mother tongues by region and province, from HCP's
results dashboard's data service."""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import morocco_rgph2024_sexes as ms  # noqa: E402


def rows(*spec):
    """(region, province, commune, sex, value) -> the data service's rows."""
    return [{"libelle_fr": r, "libelle_prov": p, "libelle_commune": c, "Sexe": s, "v": v}
            for r, p, c, s, v in spec]


ROWS = rows(("Royaume du Maroc", None, None, "Masculin", 30.0),
            ("Royaume du Maroc", None, None, "Féminin", 33.0),
            ("Oriental", None, None, "Masculin", 30.0), ("Oriental", None, None, "Féminin", 33.0),
            ("Oriental", "Oujda-Angad", None, "Masculin", 10.0),
            ("Oriental", "Oujda-Angad", None, "Féminin", 11.0),
            ("Oriental", "Nador", None, "Masculin", 20.0),
            ("Oriental", "Nador", None, "Féminin", 22.0),
            ("Oriental", "Nador", None, "Ensemble", 42.0))
TABLE = {"regions": {2: {"name": "Région de l'Oriental", "code": 2}},
         "provinces": {2381: {"name": "Préfecture d'Oujda-Angad", "code": 2381},
                       2411: {"name": "Province de Nador", "code": 2411}}}


class Sexes(unittest.TestCase):
    def test_the_whole_population_by_sex_at_each_level(self):
        chart = ms.read_sexes(ROWS)
        self.assertEqual({k: chart["kingdom"][k] for k in ("men", "women")},
                         {"men": 30, "women": 33})
        self.assertEqual(chart["regions"]["oriental"]["women"], 33)
        self.assertEqual(chart["provinces"][("oriental", "nador")]["men"], 20)
        ms.check(chart, TABLE)

    def test_provinces_that_do_not_make_their_region_stop_the_run(self):
        bad = [dict(r, v=21.0) if r["libelle_prov"] == "Nador" and r["Sexe"] == "Masculin"
               else r for r in ROWS]
        with self.assertRaises(SystemExit):
            ms.check(ms.read_sexes(bad), TABLE)

    def test_a_province_not_answered_stops_the_run(self):
        table = {**TABLE, "provinces": {**TABLE["provinces"],
                                        1: {"name": "Province de Berkane", "code": 1}}}
        with self.assertRaises(SystemExit):
            ms.check(ms.read_sexes(ROWS), table)


GUELMIM = rows(("Royaume du Maroc", None, None, "Masculin", 100.0),
               ("Royaume du Maroc", None, None, "Féminin", 100.0),
               ("Guelmim-Oued Noun", None, None, "Masculin", 100.0),
               ("Guelmim-Oued Noun", None, None, "Féminin", 100.0),
               ("Guelmim-Oued Noun", "Assa-Zag", None, "Masculin", 40.0),
               ("Guelmim-Oued Noun", "Assa-Zag", None, "Féminin", 30.0),
               ("Guelmim-Oued Noun", "Guelmim", None, "Masculin", 60.0),
               ("Guelmim-Oued Noun", "Guelmim", None, "Féminin", 70.0),
               ("Guelmim-Oued Noun", "Assa-Zag", "Al Mahbass", "Masculin", 10.0),
               ("Guelmim-Oued Noun", "Assa-Zag", "Al Mahbass", "Féminin", 0.0))
GTABLE = {"regions": {10: {"name": "Guelmim-Oued Noun", "code": 10}},
          "provinces": {10151: {"name": "Province d'Assa-Zag", "code": 10151},
                        10261: {"name": "Guelmim", "code": 10261}}}
ARABIC, AMAZIGH = list(ms.TONGUES)


class AcrossTheLine(unittest.TestCase):
    def build(self):
        chart = ms.read_sexes(GUELMIM)
        ms.check(chart, GTABLE)
        tongues = ms.read_tongues([
            {"libelle_fr": "Guelmim-Oued Noun", "libelle_prov": "Assa-Zag",
             "libelle_commune": None, "Titre de l'indicateur": ARABIC, "v": 80.0},
            {"libelle_fr": "Guelmim-Oued Noun", "libelle_prov": "Assa-Zag",
             "libelle_commune": None, "Titre de l'indicateur": AMAZIGH, "v": 20.0},
            {"libelle_fr": "Guelmim-Oued Noun", "libelle_prov": "Assa-Zag",
             "libelle_commune": "Al Mahbass", "Titre de l'indicateur": ARABIC, "v": 100.0},
            {"libelle_fr": "Guelmim-Oued Noun", "libelle_prov": "Assa-Zag",
             "libelle_commune": "Al Mahbass", "Titre de l'indicateur": AMAZIGH, "v": 0.0}])
        bound = [{"level": "admin1", "name": "Guelmim-Oued Noun", "shape_id": "R",
                  "codes": {"hcp": "10"}, "population": {"value": 200}},
                 {"level": "admin2", "name": "Assa-Zag Province", "shape_id": "A",
                  "codes": {"hcp": "10151"}, "population": {"value": 70}}]
        with mock.patch.object(ms.legal, "build", return_value=(bound, [])):
            records, _ = ms.build(chart, GTABLE, [], [], tongues)
        return {r["shape_id"]: r for r in records}

    def test_the_commune_across_the_line_is_taken_out(self):
        by = self.build()
        self.assertEqual(by["A"]["sex_ratio"]["value"], 1000)         # 30 men, 30 women
        self.assertIn("without the commune of Al Mahbass", by["A"]["sex_ratio_note"])
        self.assertEqual(by["R"]["sex_ratio"]["value"], 900)          # 90 men, 100 women
        self.assertIn("(10 people, in the Province d'Assa-Zag), which lies south",
                      by["R"]["sex_ratio_note"])
        self.assertNotIn("province)", by["R"]["sex_ratio_note"])

    def test_mother_tongues_without_the_commune(self):
        by = self.build()
        shares = {g["group"]: g["pct"] for g in by["A"]["language"]}
        # 70 people, 56 Arabic and 14 Amazigh; less Al Mahbass's 10 Arabic speakers.
        self.assertEqual(shares, {"Arabic": 76.7, "Amazigh": 23.3})
        self.assertEqual(by["A"]["language_basis"], "mother tongue")
        # The line has no mother tongue: the commune is named after the languages.
        self.assertIn("Tamazight or Tarifit), without the commune of Al Mahbass (10 people), "
                      "which lies south of the Western Sahara line. The two",
                      by["A"]["language_note"])
        self.assertEqual(by["R"]["language"], {"status": "not_available"})   # none answered


class Building(unittest.TestCase):
    def test_bound_units_take_their_sexes_and_gaps_are_left_alone(self):
        chart = ms.read_sexes(ROWS)
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

    def test_two_shares_past_a_hundred_stop_the_run(self):
        with self.assertRaises(SystemExit):
            ms.read_tongues([{"libelle_fr": "Oriental", "Titre de l'indicateur": ARABIC,
                              "v": 70.0},
                             {"libelle_fr": "Oriental", "Titre de l'indicateur": AMAZIGH,
                              "v": 40.0}])


if __name__ == "__main__":
    unittest.main()
