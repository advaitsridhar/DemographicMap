"""Benin's 2013 census: the Borgou leaflet's first table as the runner printed it,
and a constructed workbook in the shape of INSAE's principal indicators."""

import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import benin_census as bc  # noqa: E402

BORGOU = "REPUBLIQUE DU BENIN\n-------------------\nMINISTERE DU PLAN ET DU DEVELOPPEMENT\n-------------------\nInstitut National de la Statistique et de l’Analyse Economique\n1- Etat et structure de la population du Borgou\nEvolution de la population du Borgou de 2002 à 2013\nDIVISIONS\nADMINISTRATIVES\nRGPH4-2013 RGPH3-2002\nTaux\nd'accroissement\nintercensitaire\nen % (2002-2013)\nPoids\ndémographiqu\ne en % en 2013\nTotal Masculin Féminin Total Masculin Féminin\nBENIN 10 008 749 4 887 820 5 120 929 6 769 914 3 284 119 3 485 795 3,52\nBORGOU 1 214 249 607 013 607 236 724 171 361 336 362 835 4,68 12,1\nBembèrèkè 131 255 66 270 64 985 94 580 46 944 47 636 2,94 10,8\nKalalé 168 882 84 078 84 804 100 026 49 649 50 377 4,74 13,9\nN'Dali 113 604 57 643 55 961 67 379 33 895 33 484 4,73 9,4\nNikki 151 232 75 339 75 893 99 251 49 632 49 619 3,80 12,5\nParakou 255 478 127 328 128 150 149 819 75 080 74 739 4,84 21,0\nPèrèrè 78 988 39 139 39 849 42 891 21 307 21 584 5,55 6,5\nSinendé 91 672 45 640 46 032 63 373 31 666 31 707 3,32 7,5\nTchaourou 223 138 111 576 111 562 106 852 53 163 53 689 6,73 18,4\n"

COMMUNES = ["Bembereke", "Kalale", "N'dali", "Nikki", "Parakou", "Perere", "Sinende",
            "Tchaourou"]


def workbook(departments):
    """A workbook with the two sheets read: {name: (total, women %, [age % by group])}."""
    import openpyxl

    book = openpyxl.Workbook()
    ages = book.active
    ages.title = "STRUCTURE_POPULATION (2)"
    names = list(departments)
    ages.append(["STRUCTURE DE LA POPULATION"])
    ages.append(["Total"] + names)
    ages.append([None] + [departments[n][0] for n in names])
    ages.append(["Groupe d'âge"])
    labels = ["00-04 ans", "05-09 ans", "10-14 ans", "15-19 ans", "20-24 ans", "25-29 ans",
              "30-34 ans", "35-39 ans", "40 ans et +"]
    for i, label in enumerate(labels):
        ages.append([label] + [departments[n][2][i] for n in names])
    state = book.create_sheet("ETAT_POPULATION (2)")
    state.append(["Indicateurs"] + names)
    state.append(["Effectif de population (habitants)"] + [departments[n][0] for n in names])
    state.append(["Femmes"])
    state.append(["Proportion de la population de sexe féminin (%)"]
                 + [departments[n][1] for n in names])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


YOUNG = [20, 18, 14, 11, 9, 7, 6, 5, 10]
OLDER = [14, 13, 11, 10, 10, 10, 9, 8, 15]


class BeninCensus(unittest.TestCase):
    def test_leaflet(self):
        rows = dict(bc.leaflet_rows(BORGOU))
        self.assertEqual(rows["BORGOU"], (1_214_249, 607_013, 607_236))
        self.assertEqual(rows["Pèrèrè"], (78_988, 39_139, 39_849))
        self.assertEqual(rows["BENIN"], (10_008_749, 4_887_820, 5_120_929))
        found = {bc.match(n, COMMUNES): v for n, v in rows.items() if bc.match(n, COMMUNES)}
        self.assertEqual(sorted(found), sorted(COMMUNES))
        self.assertEqual(sum(v[0] for v in found.values()), 1_214_249)

    def test_names(self):
        self.assertEqual(bc.match("Dogbo-Tota", ["Dogbo", "Lalo"]), "Dogbo")
        self.assertEqual(bc.match("Akpro-Missérété", ["Akpo-Misserete", "Adjarra"]),
                         "Akpo-Misserete")
        self.assertIsNone(bc.match("Djakotomey", ["Dogbo", "Lalo"]))

    def test_workbook(self):
        saved = bc.NATIONAL
        bc.NATIONAL = 300
        try:
            deps = bc.departments(workbook({"Bénin": (300, 51.0, [16, 14.33, 12, 10.33, 9.33,
                                                                  8, 7, 6, 17.01]),
                                            "Alibori": (100, 50.0, YOUNG),
                                            "Atacora": (200, 52.0, OLDER)}))
        finally:
            bc.NATIONAL = saved
        self.assertEqual(sorted(deps), ["alibori", "atacora"])
        self.assertEqual(deps["alibori"]["median"], bc.grouped_median(
            [(0, 4, 20), (5, 9, 18), (10, 14, 14), (15, 19, 11), (20, 24, 9), (25, 29, 7),
             (30, 34, 6), (35, 39, 5), (40, None, 10)]))
        self.assertEqual(deps["atacora"]["women_pct"], 52.0)

    def test_departments_must_make_the_country(self):
        with self.assertRaises(SystemExit):
            bc.departments(workbook({"Bénin": (300, 51.0, YOUNG), "Alibori": (100, 50.0, YOUNG),
                                     "Atacora": (150, 52.0, OLDER)}))


if __name__ == "__main__":
    unittest.main()
