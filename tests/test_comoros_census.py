"""Comoros' 2017 census by island and prefecture, from INSEED's Tableau A.2
(scripts/fetch_census/comoros_census)."""

import unittest
import unittest.mock

from scripts.fetch_census import comoros_census as km

# Tableau A.2 as the report's text layer gives it (Résultats globaux, pp. 77-78).
TEXT = """Tableau A.2: Effectifs de la population selon les divisions administratives
DIVISIONS ADMINITRATIVES Total Masculin Féminin
Union des Comores 758316 381 813 376 503
MWALI 51 567 26 621 24 946
Préfecture de FOMBONI 30 835 15 979 14 856
Commune de FOMBONI 17 292 8 931 8 361
Commune de MOILI MDJINI 7 410 3 892 3 518
Commune de MOINBASSA 6 133 3 156 2 977
Préfecture de NIOUMACHOUA 11 384 5 882 5 502
Commune de MOIMBAO 3 470 1 750 1 720
Commune de MLEDJELE 7 914 4 132 3 782
Préfecture de DJANDO 9 348 4 760 4 588
Commune de DJANDO 9 348 4 760 4 588
Ile de NDZUWANI 327382 165 110 162 272
Préfecture de MUTSAMUDU 63 828 32 486 31 342
Commune de MUTSAMUDU 34 940 17 813 17 127
Commune de MIRONTSI 11 954 6 237 5 717
Commune de BANDRANI YA CHIRONKAMBA 9 732 4 840 4 892
Commune de BANDRANI YA MITSANGANI 7 202 3 596 3 606
Préfecture de OUANI 68 886 35 082 33 804
Commune de OUANI 22 500 11 325 11 175
Commune de BAZIMINI 18 469 9 386 9 083
Commune de BAMBAO MTROUNI 27 917 14 371 13 546
Préfecture de DOMONI 69 905 34 989 34 916
Commune de DOMONI 15 623 7 755 7 868
Commune de NGADZALE 10 139 5 061 5 078
Commune de KONI 18 883 9 398 9 485
Commune de BAMBAO MSTANGA 13 779 7 024 6 755
Commune de JIMLIME 11 481 5 751 5 730
Préfecture de MREMANI 65 449 32 350 33 099
Commune de ADDA 21 482 10 736 10 746
Commune de MREMANI 15 806 7 831 7 975
Commune de ONGOJOU 11 206 5 437 5 769
Commune de SHAWENI 7 393 3 713 3 680
Commune de MRAMANI 9 562 4 633 4 929
Préfecture de SIMA 35 174 17 728 17 446
Commune de SIMA 18 415 9 110 9 305
Commune de VOUANI 16 759 8 618 8 141
Préfecture de MOYA 24 140 12 475 11 665
Commune de MOYA 24 140 12 475 11 665
Ile de NGAZIDJA 379367 190 082 189 285
Préfecture de MORONI BAMBAO 121236 61 867 59 369
Commune de MORONI 74 747 38 507 36 240
Commune de BAMBAO YA DJOU 13 526 6 658 6 868
Commune de BAMBAO YA HARI 20 855 10 707 10 148
Commune de BAMBAO YA MBOINI 12 108 5 995 6 113
Préfecture de HAMBOU 22 777 11 406 11 371
Commune de TSINIMOIPANGUA 13 443 6 726 6 717
Commune de DJOUMOIPANGUA 9 334 4 680 4 654
Préfecture de MBADJINI OUEST 23 599 11 598 12 001
Commune de NGOUENGOE 9 244 4 457 4 787
Commune de NIOUMAGAMA 14 355 7 141 7 214
Préfecture de MBADJINI EST 35 312 17 402 17 910
Commune de ITSAHIDI 15 225 7 385 7 840
Commune de DOMBA 8 164 3 972 4 192
Commune de PIMBA 11 923 6 045 5 878
Préfecture de OICHILI DIMANI 26 298 12 909 13 389
Commune de OICHILI YADJOU 8 859 4 371 4 488
Commune de OICHILI YABOINI 6 025 2 914 3 111
Commune de DIMANI 11 414 5 624 5 790
Préfecture de HAMAHAMET MBOINKOU 36 648 18 044 18 604
Commune de NYUMA MSIRU 13 630 6 710 6 920
Commune de NYUMA MRO 11 445 5 492 5 953
Commune de MBOINKOU 11 573 5 842 5 731
Préfecture de MITSAMIOULI 31 821 15 832 15 989
Commune de CEMBENOI LAC SALE 7 925 3 930 3 995
Commune de CEMBENOI SADA DJOULAMLIMA 6 374 3 231 3 143
Commune de MITSAMIOULI 9 907 4 836 5 071
Commune de NYUMA KOMO 7 615 3 835 3 780
Préfecture de MBOUDE 24 341 12 181 12 160
Commune de NYUMAMRO KIBLANI 12 089 6 149 5 940
Commune de NYUMAMRO SOUHEILI 12 252 6 032 6 220
Préfecture de ITSANDRA HAMANVOU 57 335 28 843 28 492
Commune de HAMANVOU 13 789 6 778 7 011
Commune de MBADANI 8 469 4 227 4 242
Commune de BANGAANI 19 355 9 906 9 449
Commune de DJOUMOICHONGO 7 442 3 755 3 687
Commune de ISAHARI 8 280 4 177 4 103"""

# Tableaux 3 and 4 as the report's text layer gives them (pp. 23-24).
TABLES = """Tableau 3 : Répartition de la population résidente étrangère par nationalité et selon les îles
Iles (effectifs) Comores Poids île %
Nationalité
Mwali Ndzouani Ngazidja Effectif % Mwali Ndzouani Ngazidja
Afrique Australe 90 658 503 1251 33,7 7,2 52,6 40,2
Afrique Centrale 9 72 60 141 3,8 6,4 51,1 42,6
Afrique de l'Est 0 11 72 83 2,2 0,0 13,3 86,7
Afrique de l'Ouest 8 29 63 100 2,7 8,0 29,0 63,0
Afrique du Nord 6 42 52 100 2,7 6,0 42,0 52,0
Amérique du Nord 0 2 19 21 0,6 0,0 9,5 90,5
Amérique du Sud 0 0 4 4 0,1 0,0 0,0 100,0
Asie 14 69 111 194 5,2 7,2 35,6 57,2
Europe 8 138 383 529 14,3 1,5 26,1 72,4
Moyen/proche orient 0 1 14 15 0,4 0,0 6,7 93,3
Océan Indien 71 251 946 1268 34,2 5,6 19,8 74,6
Océanie 1 0 1 2 0,1 50,0 0,0 50,0
Ensemble des Étrangers 207 1 273 2 228 3 708 100,0 5,6 34,3 60,1
Source : RGPH-2017
Tableau 4 : Proportions de la population résidente selon la langue parlée et l'île de résidence
Langue
Ensemble Mwali Ndzuwani Ngazidja
parlée
Shicomor 677 246 45 808 291 870 339 569
Français 254 813 19 074 91 453 144 285
Arabe 50 117 2 901 17 729 29 487
Anglais 33 951 2 243 11 297 20 411
Malgache 18 641 920 5 158 12 563
Swahili 4 370 292 871 3 207
Source : RGPH-2017"""

ADMIN1 = [{"id": "M", "name": "Moheli"}, {"id": "A", "name": "Anjouan"},
          {"id": "G", "name": "Grande Comore"}]
ADMIN2 = [{"id": n, "name": n, "parent": p} for n, p in (
    ("Djando", "M"), ("Fomboni", "M"), ("Nioumachioi", "M"), ("Domoni", "A"),
    ("Mrémani", "A"), ("Mutsamudu", "A"), ("Ouani", "A"), ("Sima", "A"),
    ("Hamahamet-Mboinkou", "G"), ("Hambou", "G"), ("Itsandra-Hamanvou", "G"), ("Kartala", "G"),
    ("Mbadjini Est", "G"), ("Mbadjini Ouest", "G"), ("Mitsamiouli-Mboudé", "G"),
    ("Moroni-Bambao", "G"), ("Oichili-Dimani", "G"))]


class ComorosCensusTest(unittest.TestCase):
    def test_counts_are_split_where_men_and_women_make_the_total(self):
        self.assertEqual(km.splits("327382 165 110 162 272".split()),
                         [(327_382, 165_110, 162_272)])
        self.assertEqual(km.splits("9 348 4 760 4 588".split()), [(9_348, 4_760, 4_588)])

    def test_the_table_adds_up(self):
        t = km.parse(TEXT)
        self.assertEqual(len(t["prefectures"]), 18)
        self.assertEqual(t["islands"]["ngazidja"]["total"], 379_367)

    def test_polygons_get_their_prefectures(self):
        recs = {r["shape_id"]: r for r in km.build(km.parse(TEXT), ADMIN1, ADMIN2)}
        self.assertEqual(recs["Sima"]["population"]["value"], 35_174 + 24_140)
        self.assertIn("Sima and Moya", recs["Sima"]["population_note"])
        self.assertEqual(recs["Mitsamiouli-Mboudé"]["population"]["value"], 31_821 + 24_341)
        self.assertEqual(recs["Nioumachioi"]["population"]["value"], 11_384)
        self.assertEqual(recs["Kartala"]["population"]["status"], "not_available")
        self.assertIn("Karthala", recs["Kartala"]["population"]["note"])
        self.assertEqual(recs["M"]["sex_ratio"]["value"], round(1000 * 26_621 / 24_946))
        self.assertIn("Mwali (Mohéli)", recs["M"]["population_note"])

    def test_the_islands_carry_nationality_and_languages_spoken(self):
        table = km.parse(TEXT)
        with unittest.mock.patch.object(km, "log"):
            islands = km.compositions(TABLES, table)
        recs = {r["shape_id"]: r for r in km.build(table, ADMIN1, ADMIN2, islands)}
        mwali = recs["M"]
        self.assertEqual(mwali["ethnicity"][0], {"group": "Comorian nationals", "pct": 99.6,
                                                 "count": 51_567 - 207})
        self.assertEqual(mwali["ethnicity_basis"], "nationality")
        self.assertIn("90 from southern Africa", mwali["ethnicity_note"])
        self.assertEqual(mwali["language"][1], {"group": "French", "pct": 37.0,
                                                "count": 19_074})
        self.assertEqual(mwali["language_basis"], km.LANGUAGE_BASIS)
        self.assertIn("more than 100", mwali["language_note"])
        self.assertEqual(recs["G"]["language"][1]["pct"], 38.0)
        self.assertEqual(mwali["religion"]["status"], "not_available")
        # A prefecture says the two tables are by island only.
        self.assertIn("by island (Tableau 4)", recs["Fomboni"]["language"]["note"])
        self.assertIn("by island (Tableau 3)", recs["Fomboni"]["ethnicity"]["note"])
        self.assertTrue(any(src["field"] == "language note/ethnicity note"
                            for src in recs["Fomboni"]["sources"]))

    def test_digit_groups_read_as_three_islands_and_their_total(self):
        self.assertEqual(km.readings("207 1 273 2 228 3 708".split(), total_first=False),
                         [(207, 1_273, 2_228, 3_708)])
        # Shicomor's islands miss the printed total by one person.
        self.assertEqual(km.readings("677 246 45 808 291 870 339 569".split(),
                                     total_first=True),
                         [(45_808, 291_870, 339_569, 677_246)])
        with self.assertRaises(SystemExit):
            with unittest.mock.patch.object(km, "log"):
                km.compositions(TABLES.replace("Europe 8 138 383 529", "Europe 8 139 383 530"),
                                km.parse(TEXT))

    def test_a_table_that_does_not_add_up_is_refused(self):
        with self.assertRaises(SystemExit):
            km.parse(TEXT.replace("Préfecture de SIMA 35 174 17 728 17 446",
                                  "Préfecture de SIMA 35 175 17 729 17 446"))


if __name__ == "__main__":
    unittest.main()
