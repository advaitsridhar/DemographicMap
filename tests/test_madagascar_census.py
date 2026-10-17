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


T5_LEFT = "1 748 565 1 945 898 3 694 463 1 370 326 1 532 171 2 902 497 1 117 634 1 244 013 2 361 647"
T5_RIGHT = "3 456 309 3 620 781 7 077 090 660 873 654 131 1 315 004"
T6_LEFT = "7 333 914 7 741 875 15 075 789 6 425 945 6 805 588 13 231 533 4 677 380"
T6_RIGHT = "4 859 690 9 537 070 1 296 239 1 317 246 2 613 485 560 198 584 778 1 144 976"


T4_LEFT = ("1 703 839 1 661 622 3 365 461 3 242 739 3 299 794 6 542 533 4 360 373 4 543 807 "
           "8 904 180 907 969")
T4_RIGHT = ("936 287 1 844 256 1 538 900 1 638 172 3 177 072 2 656 534 2 882 185 5 538 719 "
            "6 112 843 6 502 966 12 615 809")


def age_pages():
    names = ["MADAGASCAR"] + list(mg.REGION_NAMES)
    t4 = "Tableau 4. Effectif\n10-14 ans\n" + "\n".join(f"{n} {T4_LEFT}" for n in names)
    t4r = "15- 17 ans\n" + "\n".join(T4_RIGHT for _ in names) + "\nDECEMBRE 2020 13"
    t5 = "Tableau 5. Effectif\n18-24 ans 19-24 ans\n" + "\n".join(f"{n} {T5_LEFT}" for n in names)
    t5r = "25- 49 ans 50- 59 ans\n" + "\n".join(T5_RIGHT for _ in names) + "\nDECEMBRE 2020 15"
    t6 = "Tableau 6. Effectif\n15 ans et plus\n" + "\n".join(f"{n} {T6_LEFT}" for n in names)
    t6r = "25 ans et plus\n" + "\n".join(T6_RIGHT for _ in names) + "\nDECEMBRE 2020 17"
    return [t4, t4r, t5, t5r, t6, t6r]


class MadagascarAgesTest(unittest.TestCase):
    def test_triples_are_read_where_every_one_adds_up(self):
        got = mg.triples((T6_LEFT + " " + T6_RIGHT).split())
        self.assertEqual(got[2], (4_677_380, 4_859_690, 9_537_070))
        self.assertEqual(len(got), 5)

    def test_the_countrys_median_falls_where_instat_puts_it(self):
        ages = mg.region_ages(age_pages())
        self.assertEqual(ages["MADAGASCAR"]["19"], 9_537_070 + 2_902_497)
        self.assertEqual(mg.median_from(25_674_196, ages["MADAGASCAR"]), 18.5)
        self.assertIn("Haute Matsiatra", ages)
        self.assertEqual(ages["MADAGASCAR"]["10"], 15_075_789 + 3_365_461)
        # A region younger than 15 at the median is read between 10 and 15.
        young = {"10": 600, "15": 430, "18": 380, "19": 350, "20": 330, "25": 260}
        self.assertEqual(mg.median_from(900, young), 14.4)

    def test_a_median_outside_the_bands_is_refused(self):
        with self.assertRaises(SystemExit):
            mg.median_from(100, {"15": 99, "18": 90, "19": 80, "20": 70, "25": 60})


if __name__ == "__main__":
    unittest.main()
