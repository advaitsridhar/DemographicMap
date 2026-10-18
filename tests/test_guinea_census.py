"""Guinea's two censuses as the runner printed their pages."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import guinea_census as gc  # noqa: E402

TABLEAU_1 = """    Source : RGPH-4/INS/MPCID/GUINEE/2025
Tableau 1 : Répartition de la population par Région administrative selon le sexe
Résultats préliminaires du RGPH-4 de la Guinée 26
Population
totale
Région
administrative Effectif Effectif       % Effectif       %
Ensemble 17 521 167 8 452 911 48,2 9 068 256 51,8 93
Boké 1 628 656 798 788 49,0 829 868 51,0 96
Conakry 3 407 327 1 653 256 48,5 1 754 071 51,5 94
Faranah 1 460 931 696 247 47,7 764 684 52,3 91
Kankan 4 110 215 2 063 029 50,2 2 047 186 49,8 101
Kindia 2 275 620 1 096 242 48,2 1 179 378 51,8 93
Labé 1 239 897 540 277 43,6 699 620 56,4 77
Mamou 916 535 405 732 44,3 510 803 55,7 79
Nzérékoré 2 481 986 1 199 340 48,3 1 282 646 51,7 94
Masculin Féminin Rapport de
masculinité
"""

PREFECTURES = """ Répartition de la population par préfecture selon le sexe
Résultats préliminaires du RGPH-4 de la Guinée
Population
totale
Pourcent Pourcent
(%) (%)
Ensemble 8 452 911 48,2 9 068 256 51,8 17 521 167 93
Région de
Boké 798 788 49,0 829 868 51,0 1 628 656 96
Boffa 144 798 50,3 142 850 49,7 287 648 101
Boké 385 522 49,6 391 579 50,4 777 101 98
Fria 61 852 49,0 64 353 51,0 126 205 96
Gaoual 120 281 46,7 137 047 53,3 257 328 88
Koundara 86 335 47,9 94 039 52,1 180 374 92
Région de
Conakry 1 653 256 48,5 1 754 071 51,5 3 407 327 94
Conakry 1 653 256 48,5 1 754 071 51,5 3 407 327 94
Région de
Faranah 696 247 47,7 764 684 52,3 1 460 931 91
Dabola 140 588 47,6 155 025 52,4 295 613 91
Dinguiraye 157 640 48,1 170 301 51,9 327 941 93
Faranah 210 813 47,5 233 227 52,5 444 040 90
Kissidougou 187 206 47,6 206 131 52,4 393 337 91
Région de
Kankan 2 063 029 50,2 2 047 186 49,8 4 110 215 101
Kankan 414 895 49,3 427 074 50,7 841 969 97
Kerouane 146 693 49,2 151 242 50,8 297 935 97
Kouroussa 221 545 49,1 229 660 50,9 451 205 96
Mandiana 405 378 50,6 395 581 49,4 800 959 102
Siguiri 874 518 50,9 843 629 49,1 1 718 147 104
Région de
Kindia 1 096 242 48,2 1 179 378 51,8 2 275 620 93
Coyah 169 603 49,2 175 138 50,8 344 741 97
Dubreka 240 410 49,2 248 159 50,8 488 569 97
Forecariah 203 387 48,9 212 508 51,1 415 895 96
Kindia 326 207 47,9 354 428 52,1 680 635 92
Telimelé 156 635 45,3 189 145 54,7 345 780 83
Région de
Labé 540 277 43,6 699 620 56,4 1 239 897 77
Koubia 56 969 45,4 68 432 54,6 125 401 83
Labé 212 879 44,7 263 082 55,3 475 961 81
Lelouma 71 852 40,1 107 532 59,9 179 384 67
Mali 135 502 43,3 177 617 56,7 313 119 76
Tougué 63 075 43,2 82 957 56,8 146 032 76
Région de
Mamou 405 732 44,3 510 803 55,7 916 535 79
Dalaba 74 141 43,9 94 928 56,1 169 069 78
Mamou 211 613 45,9 249 173 54,1 460 786 85
Pita 119 978 41,9 166 702 58,1 286 680 72
Région de
Nzérékoré 1 199 340  1 282 646 51,7 2 481 986 94
Beyla 249 508 48,8 261 587 51,2 511 095 95
Guéckedou 177 560 47,1 199 325 52,9 376 885 89
Lola 129 035 48,2 138 834 51,8 267 869 93
Macenta 196 110 48,0 212 304 52,0 408 414 92
Nzérékoré 350 104 48,8 367 016 51,2 717 120 95
Yomou 97 023 48,4 103 580 51,6 200 603 94
"""

COMMUNES = """Sous préfecture
Masculin Féminin Population
totale
48,5 51,5 94 6,7
DIXINN 91 470 49,0 95 083 51,0 186 553 96 31 127 6
GBESSIA 252 672 48,6 267 612 51,4 520 284 94 79 119 7
KAGBELEN 193 521 48,9 201 849 51,1 395 370 96 57 440 7
KALOUM 23 474 47,6 25 890 52,4 49 364 91 8 380 6
KASSA 4 696 50,7 4 561 49,3 9 257 103 1 502 6
LAMBANYI 185 687 48,1 200 197 51,9 385 884 93 58 070 7
MANEAH 114 133 49,0 118 603 51,0 232 736 96 32 422 7
MATAM 85 990 48,5 91 281 51,5 177 271 94 27 514 6
MATOTO 122 661 47,7 134 365 52,3 257 026 91 35 370 7
\fSous préfecture
RATOMA 90 457 48,3 96 808 51,7 187 265 93 29 585 6
SANOYAH 156 513 48,5 165 906 51,5 322 419 94 44 950 7
SONFONIA 150 428 48,5 160 046 51,5 310 474 94 46 522 7
TOMBOLIA 181 554 48,6 191 870 51,4 373 424 95 53 358 7
"""

LAYOUT = """       Tableau 2 : Age moyen et âge médian de la population par Région administrative selon le sexe
                            Age moyen                       Age médian
                 Ensemble                      Ensemble
                         Masculin Féminin Urbain Rural Masculin Féminin Urbain Rural
         Guinée    22,2   22,0 22,4  22,3  22,2  17,0   17,0  18,0 18,0  17,0
         Boke      22,5   22,4 22,6  22,9  22,4  18,0   17,0  18,0 19,0  17,0
         Conakry   22,9   23,3 22,6  22,9  --    19,0   20,0  19,0 19,0   --
         Faranah   21,8   21,3 22,2  21,7  21,8  16,0   15,0  17,0 16,0  15,0
         Kankan    19,5   19,9 19,2  19,7  19,5  15,0   15,0  15,0 16,0  15,0
         Kindia    22,2   21,9 22,4  22,1  22,2  17,0   16,0  18,0 18,0  17,0
         Labé      25,5   23,9 26,6  22,9  26,2  18,0   15,0  20,0 17,0  18,0
         Mamou     26,7   25,4 27,7  24,1  27,2  19,0   16,0  22,0 18,0  19,0
         N'Zérékoré 22,5  22,1 22,8  21,9  22,6  17,0   16,0  18,0 17,0  17,0
"""

T2014 = """LISTE DES TABLEAUX
Tableau 2.07: Effectif et répartition (%) de la population résidente par sexe selon la région de résidence, rang ... 34
Tableau 3.06: Age moyen et âge médian de la population par milieu et par région de résidence selon le sexe .......... 63
\fTableau 2.07: Effectif et répartition (%) de la pop ulation résidente par sexe selon la région de résid ence,  rang
démographique de la région et pourcentage des femmes
Régions
Sexe
Rang % de femmes Masculin
Féminin
Effectif
Effectif %
Boké 526 919 556 228 1 083 147 10,3 5 51,4
Conakry 833 755 827 218 1 660 973 15,8 2 49,8
Faranah 450 823 490 731 941 554 8,9 7 52,1
Kankan 980 449 992 088 1 972 537 18,7 1 50,3
Kindia 749 192 812 144 1 561 336 14,8 4 52,0
Labé 448 859 545 599 994 458 9,5 6 54,9
Mamou 332 008 399 180 731 188 6,9 8 54,6
N’Zérékoré 76 2 301 815 767 1 578 068 15,0 3 51,7
Ensemble 5 084 306 5 438 955 10 523 261 100,0 - 51, 7
\fTableau 3.06: Age moyen et âge médian de la population par milieu et par région de résidence selon le sexe
Lieu de
résidence
Âge moyen Âge médian
Masculin Féminin Total Masculin Féminin Total
Milieu de résidence
Urbain 22,2 21,5 21,9 18,2 17,7 17,9
Rural 21,2 22,3 21,8 13,3 17,0 14,9
Région de résidence
Boké 21,2 21,7 21,5 14,7 17,2 16,0
Conakry 23,0 21,6 22,3 19,9 18,6 19,3
Faranah 21,2 21,8 21,5 13,5 16,3 14,7
Kankan 19,7 19,8 19,8 13,5 14,9 14,2
Kindia 21,2 21,6 21,4 14,5 17,2 15,8
Labé 22,7 24,9 23,9 14,1 18,8 16,5
Mamou 24,1 25,9 25,1 14,3 19,7 17,3
N'Zérékoré 21,4 22,1 21,8 14,7 17,3 16,0
Ensemble 21,6 22,0 21,8 15,0 17,3 16,3
\fTableau 5.08: Répartition de la population résidente de plus de 15 ans par région de résidence selon la langue
principale parlée
Langue parlée
Région de résidence
Boké Conakry  Faranah  Kankan Kindia Labé Mamou N'Zéré -koré Total
Aucune 0,2 0,2 0,2 0,2 0,2 0,2 0,1 0,1 0,2
Soussou 32,2 37,0 0,4 0,3 54,9 0,3 1,9 0,3 17,7
Poular 45,8 34,0 27,9 3,9 35,2 94,5 92,4 3,5 34,6
Maninka 2,0 18,7 36,3 87,1 5,3 0,9 4,3 9,2 24,9
Diakanka 5,8 1,3 0,2 0,1 0,5 1,7 0,2 0,1 1,1
Baga 2,3 0,5 0,0 0,0 0,1 0,0 0,0 0,0 0,3
Nalou 0,4 0,0 0,0 0,0 0,0 0,0 0,0 0,0 0,1
Mikiforè 2,0 0,2 0,0 0,0 0,0 0,0 0,1 0,0 0,2
Landouma 3,9 0,2 0,0 0,0 0,0 0,0 0,0 0,0 0,5
Badiaranké 0,8 0,0 0,0 0,0 0,0 0,0 0,0 0,0 0,1
Bassari 0,7 0,0 0,0 0,0 0,0 0,0 0,0 0,1 0,1
Koniagui 0,8 0,4 0,0 0,1 0,1 0,0 0,0 0,4 0,2
Djalonké 0,3 0,5 6,7 0,2 0,2 1,2 0,0 0,1 0,9
Sarakolé/Marak 0,5 0,1 0,0 0,0 0,2 0,7 0,0 0,0 0,2
Kouranko 0,0 0,2 12,1 3,9 0,1 0,0 0,0 0,3 1,9
Kissi 0,3 1,7 13,2 0,6 1,0 0,1 0,2 15,4 4,1
Lélé 0,0 0,1 2,3 0,1 0,1 0,0 0,0 0,9 0,4
Toma 0,2 0,8 0,2 0,2 0,4 0,0 0,0 7,8 1,4
Koniaka 0,1 1,6 0,1 2,6 0,3 0,0 0,0 24,4 4,5
Tomamania 0,0 0,1 0,0 0,2 0,0 0,0 0,0 4,5 0,7
Kpèlè 0,3 1,4 0,3 0,3 0,7 0,2 0,2 23,4 4,0
Mano 0,1 0,2 0,0 0,1 0,1 0,0 0,0 4,0 0,7
Kono 0,1 0,3 0,0 0,1 0,2 0,0 0,1 4,9 0,8
Autre langue
nationale  1,1 0,6 0,1 0,1 0,2 0,0 0,4 0,6 0,4
Total 100 100 100 100 100 100 100 100 100
\fTableau 5.10: Répartition de la population résidente par région de résidence  selon la religion
Région
administrative
Sans
religion Musulmane Chrétienne Animiste Autre s religions Ensemble
Boké 0,3 96,8 2,8 0,1 0,0 100,0
Conakry 0,3 94,8 4,8 0,0 0,1 100,0
Faranah 0,8 89,1 9,7 0,1 0,2 100,0
Kankan 0,2 98,7 1,1 0,0 0,0 100,0
Kindia 0,5 97,2 2,3 0,0 0,0 100,0
Labé 0,2 99,4 0,4 0,0 0,0 100,0
Mamou 0,1 99,4 0,5 0,0 0,0 100,0
N'Zérékoré 14,2 46,7 28,1 10,4 0,6 100,0
Ensemble 2,4 89,1 6,8 1,6 0,1 100,0
"""

T2025 = TABLEAU_1 + "\f" + PREFECTURES + "\f" + COMMUNES


def shapes():
    admin1, admin2 = [], []
    for i, (region, prefectures) in enumerate(gc.PREFECTURES.items()):
        rid = f"R{i}"
        admin1.append({"id": rid, "name": region.replace("é", "e"), "parent": "GIN"})
        for j, prefecture in enumerate(prefectures):
            admin2.append({"id": f"P{i}{j}", "name": prefecture, "parent": rid})
    return admin1, admin2


class GuineaReads(unittest.TestCase):
    def test_tables_2025(self):
        regions = gc.parse_regions_2025(T2025)
        self.assertEqual(regions["Nzérékoré"], (1_199_340, 1_282_646, 2_481_986))
        table = gc.parse_prefectures_2025(T2025)
        self.assertEqual(table["regions"]["Nzérékoré"], (1_199_340, 1_282_646, 2_481_986))
        self.assertEqual(table["prefectures"][("Kindia", "Coyah")], (169_603, 175_138, 344_741))
        communes = gc.parse_communes_2025(T2025)
        self.assertEqual(communes["Kagbelen"], (193_521, 201_849, 395_370))
        gc.check_2025(regions, table, communes)
        drawn = gc.drawn_ground(regions, table, communes)
        self.assertEqual(drawn["prefectures"]["Conakry"][2], 2_456_802)
        self.assertEqual(drawn["prefectures"]["Coyah"][2], 344_741 + 232_736 + 322_419)
        self.assertEqual(drawn["prefectures"]["Dubreka"][2], 488_569 + 395_370)
        self.assertEqual(drawn["regions"]["Kindia"][2], 2_275_620 + 950_525)

    def test_medians_and_2014(self):
        medians = gc.parse_medians_2025(LAYOUT)
        self.assertEqual(medians["Boké"], 18.0)
        self.assertEqual(medians["Nzérékoré"], 17.0)
        self.assertEqual(len(medians), 8)
        old = gc.parse_2014(T2014)
        self.assertEqual(old["population"]["Nzérékoré"], (762_301, 815_767, 1_578_068))
        self.assertEqual(old["median"]["Kindia"], 15.8)
        self.assertEqual(old["religion"]["Nzérékoré"]["Islam"], 46.7)
        self.assertAlmostEqual(sum(old["language"]["Boké"].values()), 99.9, places=1)
        self.assertEqual(old["language"]["Nzérékoré"]["Konyanka"], 24.4)
        self.assertIn("Other national language", old["language"]["Boké"])

    def test_build(self):
        admin1, admin2 = shapes()
        records, report = gc.build(T2025, LAYOUT, T2014, admin1, admin2)
        self.assertEqual(report, [])
        by = {(r["level"], r["name"]): r for r in records}
        self.assertEqual(len(records), 8 + 34)
        conakry = by[("admin2", "Conakry")]
        self.assertEqual(conakry["population"]["value"], 2_456_802)
        self.assertIn("other ten communes", conakry["population_note"])
        kindia = by[("admin1", "Kindia")]
        self.assertEqual(kindia["median_age"]["value"], 15.8)
        self.assertEqual(kindia["median_age"]["year"], 2014)
        boke = by[("admin1", "Boke")]
        self.assertEqual(boke["median_age"]["value"], 18.0)
        self.assertEqual(boke["religion"][0]["group"], "Islam")
        self.assertEqual(boke["sex_ratio"]["value"], round(1000 * 798_788 / 829_868))
        nz = by[("admin1", "Nzerekore")]
        self.assertEqual(nz["language"][0]["group"], "Konyanka")
        # The shares as Tableaux 5.08 and 5.10 print them, not rescaled.
        self.assertEqual(nz["language"][0]["pct"], 24.4)
        self.assertNotIn("count", nz["language"][0])
        self.assertEqual(nz["religion"][0], {"group": "Islam", "pct": 46.7,
                                             "count": int(46.7 * 1_578_068 / 100)})
        # The prefecture of Conakry is the region: its median too.
        region = by[("admin1", "Conakry")]
        self.assertEqual(conakry["median_age"], region["median_age"])
        self.assertEqual(conakry["median_age"]["year"], 2014)
        self.assertIn("this one prefecture", conakry["median_age_note"])
        self.assertIn("median_age", [s["field"] for s in conakry["sources"]])
        self.assertNotIn("value", by[("admin2", "Coyah")]["median_age"])


if __name__ == "__main__":
    unittest.main()
