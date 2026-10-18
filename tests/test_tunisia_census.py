"""Tunisia's 2024 census reader: sectors added up, delegations bound, new ones put back."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import tunisia_census as tc  # noqa: E402

HEADER = ["Code_Département", "District", "الإقليم", "Code_Gouvernorat", "Gouvernorat", "الولاية",
          "Code_Delegation", "Délégations", "المعتمدية", "Code_secteur_D", "Secteurs", "العمادة",
          "Code_Secteur_Secteur", "رمز العمادة_العمادة", "ID_Sexe", "Sexe", "الجنس",
          "Classe_Age", "Tranche d'âge", "الفئة العمرية", "Population"]
AGES = ["00-04", "05-09", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44",
        "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+"]


def rows_for(sectors):
    """sectors: [(gov code, gov fr, gov ar, del code, del fr, del ar, sec code, sec fr, per_group)]."""
    rows = [HEADER]
    for g, gfr, gar, d, dfr, dar, s, sfr, n in sectors:
        for sex in ("M", "F"):
            for i, age in enumerate(AGES, 1):
                rows.append([1, "D", "", g, gfr, gar, d, dfr, dar, s, sfr, "", "", "", sex, "", "",
                             i, age, age, n])
    return rows


class Folding(unittest.TestCase):
    def test_arabic_forms_and_marks_fold_alike(self):
        self.assertEqual(tc.fold("‫الصخیرة‬"), tc.fold("الصخيرة"))
        self.assertEqual(tc.fold("مدنين االجنوبية"), tc.fold("مدنين الجنوبية"))
        self.assertEqual(tc.fold("حمام  الأنف"), tc.fold("حمام الانف"))

    def test_french_names_lose_their_kind_word(self):
        self.assertEqual(tc.latin("Délégation de Carthage"), "carthage")

    def test_the_two_censuses_names_join_without_articles(self):
        self.assertEqual(tc.place_key("Gouvernorat du Kef"), tc.place_key("Le Kef"))
        self.assertEqual(tc.place_key("Gouvernorat de l'Ariana"), tc.place_key("Ariana"))
        self.assertEqual(tc.place_key("Délégation d'El Faouar"), "faouar")

    def test_open_age_group(self):
        self.assertEqual(tc.bounds("80+"), (80, None))
        self.assertEqual(tc.bounds("05-09"), (5, 9))


class Reading(unittest.TestCase):
    def setUp(self):
        self.national = tc.NATIONAL
        tc.NATIONAL = 2 * 17 * (10 + 20 + 5)

    def tearDown(self):
        tc.NATIONAL = self.national

    def table(self):
        return tc.read(rows_for([
            ("11", "Tunis", "تونس", "1151", "Carthage", "قرطاج", "115151", "Sidi bou said", 10),
            ("11", "Tunis", "تونس", "1152", "La medina", "المدينة", "115251", "Medina", 20),
            ("11", "Tunis", "تونس", "1172", "Nouvelle", "جديدة", "117251", "Amilcar", 5),
        ]))

    def test_sectors_add_up_to_delegations_and_governorates(self):
        t = self.table()
        self.assertEqual(t["governorates"]["11"]["total"], tc.NATIONAL)
        self.assertEqual(t["delegations"]["1151"]["M"], 170)
        self.assertEqual(len(t["groups"]), 17)
        self.assertEqual(t["delegations"]["1152"]["groups"][0], (0, 4, 40))

    def test_a_total_that_is_not_the_national_count_stops_the_run(self):
        tc.NATIONAL += 1
        with self.assertRaises(SystemExit):
            self.table()

    def test_a_new_delegation_goes_back_on_its_2014_polygon(self):
        t = self.table()
        admin1 = [{"id": "G1", "name": "Tunis"}]
        admin2 = [{"id": "P1", "name": "Carthage", "parent": "G1"},
                  {"id": "P2", "name": "المدينة", "parent": "G1"}]
        sectors_2014 = {"tunis": {"sidibousaid": "carthage", "amilcar": "carthage",
                                  "medina": "medina"}}
        saved = dict(tc.DELEGATIONS)
        tc.DELEGATIONS.clear()
        try:
            records, report = tc.build(t, admin1, admin2, sectors_2014)
        finally:
            tc.DELEGATIONS.update(saved)
        by_shape = {r["shape_id"]: r for r in records if r["level"] == "admin2"}
        # Carthage's polygon holds Carthage and the sector made a delegation since.
        self.assertEqual(by_shape["P1"]["population"]["value"], 2 * 17 * 15)
        self.assertIn("added together", by_shape["P1"]["population_note"])
        self.assertEqual(by_shape["P2"]["population"]["value"], 2 * 17 * 20)
        self.assertEqual(by_shape["P2"]["sex_ratio"]["value"], 1000)
        self.assertTrue(any("made since 2014" in line for line in report))

    def test_a_new_delegation_split_between_two_polygons_says_which_part(self):
        tc.NATIONAL = 2 * 17 * (10 + 20 + 5 + 3)
        t = tc.read(rows_for([
            ("11", "Tunis", "تونس", "1151", "Carthage", "قرطاج", "115151", "Sidi bou said", 10),
            ("11", "Tunis", "تونس", "1152", "La medina", "المدينة", "115251", "Medina", 20),
            ("11", "Tunis", "تونس", "1172", "Nouvelle", "جديدة", "117251", "Amilcar", 5),
            ("11", "Tunis", "تونس", "1172", "Nouvelle", "جديدة", "117252", "Souk", 3),
        ]))
        admin1 = [{"id": "G1", "name": "Tunis"}]
        admin2 = [{"id": "P1", "name": "Carthage", "parent": "G1"},
                  {"id": "P2", "name": "المدينة", "parent": "G1"}]
        sectors_2014 = {"tunis": {"sidibousaid": "carthage", "amilcar": "carthage",
                                  "medina": "medina", "souk": "medina"}}
        saved = dict(tc.DELEGATIONS)
        tc.DELEGATIONS.clear()
        try:
            records, _ = tc.build(t, admin1, admin2, sectors_2014)
        finally:
            tc.DELEGATIONS.update(saved)
        by_shape = {r["shape_id"]: r for r in records if r["level"] == "admin2"}
        self.assertIn(f"the part of Nouvelle ({2 * 17 * 5:,} people) that had been Carthage's",
                      by_shape["P1"]["population_note"])
        self.assertIn(f"the part of Nouvelle ({2 * 17 * 3:,} people) that had been La Medina's",
                      by_shape["P2"]["population_note"])
        self.assertIn("Nouvelle was made a delegation since", by_shape["P2"]["population_note"])
        # The men and women counted are the polygon's, said before the parts.
        men = by_shape["P2"]["population"]["value"] // 2
        self.assertTrue(by_shape["P2"]["population_note"].startswith(
            f"The 2024 census count of the delegation of La Medina as drawn in 2014: {men:,} men "
            f"and {men:,} women. The 2024 census counts this ground as La Medina and the part"))
        self.assertTrue(by_shape["P2"]["population_note"].endswith("since."))

    def test_a_name_cut_at_twenty_characters_is_written_whole(self):
        self.assertEqual(tc.FRENCH["3166"], "Zaouia-Ksiba-Thrayet")

    def test_a_new_delegation_that_cannot_be_placed_stops_the_run(self):
        t = self.table()
        admin1 = [{"id": "G1", "name": "Tunis"}]
        admin2 = [{"id": "P1", "name": "Carthage", "parent": "G1"},
                  {"id": "P2", "name": "المدينة", "parent": "G1"}]
        saved = dict(tc.DELEGATIONS)
        tc.DELEGATIONS.clear()
        try:
            with self.assertRaises(SystemExit):
                tc.build(t, admin1, admin2, {"tunis": {"medina": "medina"}})
        finally:
            tc.DELEGATIONS.update(saved)

    def test_a_declared_home_places_a_delegation_the_2014_table_does_not_name(self):
        t = self.table()
        admin1 = [{"id": "G1", "name": "Tunis"}]
        admin2 = [{"id": "P1", "name": "Carthage", "parent": "G1"},
                  {"id": "P2", "name": "المدينة", "parent": "G1"}]
        saved, homes = dict(tc.DELEGATIONS), dict(tc.HOMES_2014)
        tc.DELEGATIONS.clear()
        tc.HOMES_2014.clear()
        tc.HOMES_2014["1172"] = "medina"
        try:
            records, report = tc.build(t, admin1, admin2, {"tunis": {"medina": "medina"}})
        finally:
            tc.DELEGATIONS.update(saved)
            tc.HOMES_2014.clear()
            tc.HOMES_2014.update(homes)
        by_shape = {r["shape_id"]: r for r in records if r["level"] == "admin2"}
        self.assertEqual(by_shape["P2"]["population"]["value"], 2 * 17 * 25)
        self.assertTrue(any("whose outline holds it" in line for line in report))


class Medians(unittest.TestCase):
    def test_grouped_median(self):
        groups = [(0, 4, 10), (5, 9, 10), (10, None, 0)]
        self.assertEqual(tc.grouped_median(groups), 5.0)

    def test_a_median_in_the_open_group_is_none(self):
        self.assertIsNone(tc.grouped_median([(0, 4, 1), (5, None, 10)]))


if __name__ == "__main__":
    unittest.main()
