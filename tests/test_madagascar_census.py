"""Madagascar's 2018 census by district and region, from INSTAT's Tome 2
Tableau 8 (scripts/fetch_census/madagascar_census)."""

import unittest
from unittest import mock

from scripts.fetch_census import madagascar_census as mg

PAGE_1 = """RÉSULTATS GLOBAUX DU RGPH-3 DE 2018 DE MADAGASCAR, INSTAT-CCER
Tableau 8. Répartition de la population résidente par sexe selon la région, le District et densité, poids démo-
graphique, rapport de masculinité et pourcentage de femmes
Effectif Poids Proportion Densité
Région District démo- RM de femmes (Hab./
Homme Femme Ensemble graphique Km²)
26 DECEMBRE 2020
agnamalanA
Total Région 1 777 869 1 846 056 3 623 925 14,1 96,3 50,9 208,9
Antananarivo 615 659 658 566 1 274 225 5,0 93,5 51,7 15000,4
Renivohitra
Ankazobe 97 546 95 880 193 426 0,8 101,7 49,6 26,3
Antananarivo 1 064 664 1 091 610 2 156 274 1,8 96,8 50,8 773,1
Avaradrano
avalognoB Total Région 340 841 330 152 670 993 2,6 103,2 49,2 37,1
Tsiroanomandidy 249 168 241 331 490 499 1,9 103,2 49,2 46,5
Fenoarivobe 91 673 88 821 180 494 0,7 103,2 49,2 23,9"""
PAGE_2 = """RÉSULTATS GLOBAUX DU RGPH-3 DE 2018 DE MADAGASCAR, INSTAT-CCER
DECEMBRE 2020 27
anaferdnA
omistA
Total Région 80 015 88 741 168 756 0,7 90,2 52,6 5257,8
Toliara-I 80 015 88 741 168 756 0,7 90,2 52,6 5257,8
MADAGASCAR 2 198 725 2 264 949 4 463 674 100,0 97,3 50,7 43,4
Source : MDG, INSTAT - rGPH2018"""
PAGE_3 = "Tableau 9. Effectif de la population recensée dans les ménages ordinaires"
NATIONAL = 1_777_869 + 1_846_056 + 340_841 + 330_152 + 80_015 + 88_741

ADMIN1 = [{"id": "A", "name": "Analamanga"}, {"id": "B", "name": "Bongolava"},
          {"id": "T", "name": "Atsimo-Andrefana"}]
ADMIN2 = ([{"id": f"arr{i}", "name": f"{i}e Arrondissement", "parent": "A"} for i in range(2, 7)]
          + [{"id": "arr1", "name": "1er Arrondissement", "parent": "A"},
             {"id": "ank", "name": "Ankazobe", "parent": "A"},
             {"id": "ava", "name": "Antananarivo Avaradrano", "parent": "A"},
             {"id": "tsi", "name": "Tsiroanomandidy", "parent": "B"},
             {"id": "fen", "name": "Fenoarivobe", "parent": "B"},
             {"id": "tol", "name": "Toliary-I", "parent": "T"}])


class MadagascarCensusTest(unittest.TestCase):
    def table(self, pages=(PAGE_1, PAGE_2, PAGE_3)):
        with mock.patch.object(mg, "NATIONAL", NATIONAL + 0):
            text = [p.replace("2 198 725 2 264 949 4 463 674",
                              f"{self.group(1_777_869 + 340_841 + 80_015)} "
                              f"{self.group(1_846_056 + 330_152 + 88_741)} "
                              f"{self.group(NATIONAL)}") for p in pages]
            return mg.parse(list(text))

    @staticmethod
    def group(n):
        return f"{n:,}".replace(",", " ")

    def test_counts_are_told_apart_by_men_and_women_making_the_total(self):
        self.assertEqual(mg.splits("1 777 869 1 846 056 3 623 925"),
                         [(1_777_869, 1_846_056, 3_623_925)])
        self.assertEqual(mg.reading("97 546 95 880 193 426", "101,7"), (97_546, 95_880, 193_426))

    def test_names_split_over_two_lines_and_rotated_region_names(self):
        t = self.table()
        names = [d["name"] for r in t["regions"] for d in r["districts"]]
        self.assertEqual(names, ["Antananarivo Renivohitra", "Ankazobe",
                                 "Antananarivo Avaradrano", "Tsiroanomandidy", "Fenoarivobe",
                                 "Toliara-I"])

    def test_records_and_the_arrondissements(self):
        recs = {r["shape_id"]: r for r in mg.build(self.table(), ADMIN1, ADMIN2)}
        self.assertEqual(recs["ank"]["population"]["value"], 193_426)
        self.assertEqual(recs["ank"]["sex_ratio"]["value"], round(1000 * 97_546 / 95_880))
        self.assertEqual(recs["tol"]["population"]["value"], 168_756)
        self.assertEqual(recs["arr3"]["population"]["status"], "not_available")
        self.assertIn("1,274,225 people", recs["arr3"]["population"]["note"])
        self.assertEqual(recs["A"]["population"]["value"], 3_623_925)
        self.assertEqual(recs["B"]["sex_ratio"]["value"], round(1000 * 340_841 / 330_152))

    def test_districts_must_make_their_region(self):
        broken = PAGE_1.replace("Ankazobe 97 546 95 880 193 426", "Ankazobe 97 546 95 881 193 427")
        with self.assertRaises(SystemExit):
            self.table((broken, PAGE_2, PAGE_3))


if __name__ == "__main__":
    unittest.main()
