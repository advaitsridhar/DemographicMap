"""Burkina Faso's 2019 census monograph of the Boucle du Mouhoun as the runner
printed its page (one token a line), and its list of tables."""

import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import burkina_provinces as bp  # noqa: E402

CONTENTS = 'Tableau 2.3: Répartition (%) des effectifs de la population par province selon le sexe\n................................ 13\n'

PAGE = 'La répartition des effectifs de population\npar\nprovince indique que l\na province du\nMouhoun est la\nplus peuplée avec 391 561 habitants\n,\ntandis que le Nayala demeure la moins peuplée avec 223 151\nhabitants.\nA l’image de la région,\nles femmes sont plus nombreuses que les hommes au niveau des différentes\nprovinces à l’exception de la Kossi où le rapport de masculinité indique 103 hommes pour 100\nfemmes.\nLa province du Sourou compte autant d’hommes que de femmes.\nAu niveau régional, ce\nrapport est de 99 hommes pour 100 femmes (tableau 2.3).\nTableau\n2\n.\n3\n: Répartition (%) des effectifs de la population par province selon le sexe\nProvince\nSexe\nPoids de chaque\nProvince (%)\nRapport de\nmasculini\nté\nHomme\nFemme\nEnsemble\nBalé\n148\n040\n149\n428\n297\n468\n15,6\n99\nBanwa\n169\n820\n177\n169\n346\n989\n18,3\n96\nKossi\n180\n802\n176\n287\n357\n089\n18,8\n103\nMouhoun\n194\n617\n196\n944\n391\n561\n20,6\n99\nNayala\n110\n674\n112\n477\n223\n151\n11,7\n98\nSourou\n142\n230\n142\n781\n285\n011\n15,0\n100\nEnsemble\n946\n183\n955\n086\n1\n901\n269\n100\n99\nAu niveau des communes, Solenzo demeure la plus peuplée avec une proportion de 8,4% de la\npopulation\nde\nla région. Elle est suivie de Dédougou avec 6,5% de la population. Son\no\net Madouba\nsont les communes les moins peuplées de la région\navec un poids démographique de 0,5%.\nLes rapports de masculinité varient d’une commune à l’autre et se situent à 99 hommes pour 100\nfemmes dans l’ensemble de la région (tableau 2.4).\n\n'


class BurkinaProvinces(unittest.TestCase):
    def test_table(self):
        names = ["Bale", "Banwa", "Kossi", "Mouhoun", "Nayala", "Sourou"]
        table = bp.province_table(CONTENTS + PAGE, names)
        self.assertEqual(table["Bale"], (148_040, 149_428, 297_468))
        self.assertEqual(table["Sourou"], (142_230, 142_781, 285_011))
        self.assertEqual(sum(v[2] for v in table.values()), 1_901_269)

    def test_missing_province(self):
        with self.assertRaises(SystemExit):
            bp.province_table(PAGE, ["Bale", "Tapoa"])

    def test_total_row_must_agree(self):
        # The Boucle's table with Sourou's women made one more: the provinces
        # no longer make the Ensemble row, and nothing is taken.
        names = ["Bale", "Banwa", "Kossi", "Mouhoun", "Nayala", "Sourou"]
        altered = PAGE.replace("Sourou\n142\n230\n142\n781\n285\n011",
                               "Sourou\n142\n230\n142\n782\n285\n012")
        with self.assertRaises(SystemExit):
            bp.province_table(CONTENTS + altered, names)

    def test_close_spelling(self):
        # Constructed: a province the table spells otherwise than the map,
        # taken because its label is close and the rows make the total.
        text = ("Tableau 2.3 : Répartition des effectifs de la population par province "
                "selon le sexe Province Homme Femme Ensemble "
                "Gnagna 1 000 1 200 2 200 Komondjoari 500 600 1 100 "
                "Ensemble 1 500 1 800 3 300")
        table = bp.province_table(text, ["Gnagna", "Komonjdjari"])
        self.assertEqual(table["Komonjdjari"], (500, 600, 1_100))

    def test_no_total_row(self):
        # Constructed: a table without its total row is taken when its
        # provinces make the region's own count, and refused otherwise.
        text = ("Tableau 2.3 : Répartition des effectifs de la population par province "
                "selon le sexe Province Homme Femme Ensemble "
                "Ioba 130 361 135 595 265 956 Poni 168 544 188 374 356 918 "
                "Au niveau des communes")
        names = ["Ioba", "Poni"]
        table = bp.province_table(text, names, (298_905, 323_969, 622_874))
        self.assertEqual(table["Poni"], (168_544, 188_374, 356_918))
        with self.assertRaises(SystemExit):
            bp.province_table(text, names, (298_905, 323_970, 622_875))
        with self.assertRaises(SystemExit):
            bp.province_table(text, names)

    def test_regional_total(self):
        # The Centre monograph's list of tables, then its Tableau 2.1 as the
        # runner printed it (title wrapped before the year; narrow spaces
        # between the thousands).
        text = ("Tableau 2.1 : Répartition de l’effectif de population par milieu de "
                "résidence selon le sexe en 2019  ............  8 \n"
                "Tableau 2.2 : Répartition (%) des effectifs de la population par commune "
                "selon le sexe  ..........................  9 \n"
                "Tableau 2.1 : Répartition de l’effectif de population par milieu de "
                "résidence selon le sexe en\n2019\n"
                "Milieu de résidence Sexe Masculin Féminin Ensemble\n"
                "Urbain        1 183 557        1 231 709        "
                "2 415 266\n"
                "Rural           305 955            309 163            615 118\n"
                "Ensemble        1 489 512        1 540 872        "
                "3 030 384\n")
        self.assertEqual(bp.regional_total(text), (1_489_512, 1_540_872, 3_030_384))


# The runner's text of four monographs' pages (--dump=composition1): the
# Cascades' chart of religions by province, the Centre-Est's table of languages
# by province, the Boucle du Mouhoun's, whose figures the text breaks around
# their commas, and the Centre-Nord's page where the chart is a picture.
CASCADES_CHART = 'Graphique  \n3\n.\n2\n: Répartition (%) de la population des communautés religieuses par province\n \n \n \n \n9,3\n6,0\n8,5\n79,2\n89,7\n81,5\n7,3\n2,0\n6,1\n1,9\n1,2\n1,7\n0,3\n0,1\n0,2\n2,1\n1,1\n1,9\n0\n10\n20\n30\n40\n50\n60\n70\n80\n90\n100\nCOMOE\nLERABA\nEnsemble\nProportion\nProvince\nAnimiste\nMusulman\nCatholique\nProtestant\nAutre\nSans religion'

CENTRE_EST_TABLE = 'Tableau 3.3: Répartition (%) de la population de 3 ans ou plus selon les principales langues parlées \npar sexe et la province \n  BOULGOU KOURITTENGA KOULPÉLOGO TOTAL Principales langues parlées \n  H F H+F H F H+F H F H+F H F H+F \nMooré 23,5 21,9 22,7 92 92,5 92,3 66,4 67,7 67,1 53,9 53,0 53,4 \nBissa 63,6 67 65,5 1,3 1,4 1,4 10,6 10,6 10,6 33,1 35,5 34,4 \nFulfuldé (ou peulh) 7,9 6,9 7,3 4,9 4,6 4,7 7,3 6,8 7 6,9 6,1 6,5 \nMoba 0,1 0 0 0 0 0 7,8 7,4 7,6 1,6 1,5 1,5 \nKoussassé 2,3 2,1 2,2 0 0 0 0 0 0 1,1 1 1,1 \nFrançais 1,1 0,8 0,9 1 0,9 0,9 0,3 0,2 0,2 0,9 0,7 0,8 \nGourmantché (ou gulmancéma) 0,1 0,1 0,1 0,3 0,2 0,2 3,2 3 3,1 0,8 0,7 0,7 \nKusaal 0,5 0,5 0,5 0 0 0 0 0 0 0,2 0,2 0,2 \nDioula (ou bambara) 0,2 0,1 0,2 0,1 0,1 0,1 0,1 0,1 0,1 0,1 0,1 0,1 \nBirifor 0,1 0,1 0,1 0 0 0 0,1 0,1 0,1 0,1 0,1 0,1 \nAutres langues  0,6 0,5 0,5 0,4 0,3 0,4 4,2 4,1 4,2 1,3 1,1 1,2 \nEnsemble 100 100 100 100 100 100 100 100 100 100 100 100'

BDM_TABLE = 'Tableau \n3\n.\n3\n: Répartition (%) de la population de 3 ans ou plus selon les principales langues parlées \npar sexe et la province\n \nPrincipales langues \nparlées\n \nBalé\n \nBanwa\n \nKossi\n \nMouhoun\n \nM\n \nF\n \nM+F\n \nM\n \nF\n \nM+F\n \nM\n \nF\n \nM+F\n \nM\n \nF\n \nM+F\n \nMooré\n \n29\n,0\n \n29,4\n \n29,2\n \n50,6\n \n52,5\n \n51,5\n \n8,3\n \n8,6\n \n8,4\n \n29,5\n \n31,4\n \n30,4\n \nMarka (ou Dafing)\n \n17\n,0\n \n16\n,0\n \n16,5\n \n5,9\n \n5,4\n \n5,6\n \n15,3\n \n14,6\n \n14,9\n \n27,4\n \n25,4\n \n26,4\n \nBwamu (ou \nbwamou)\n \n24,8\n \n26\n,0\n \n25,4\n \n10,4\n \n9,8\n \n10,1\n \n29,6\n \n29,6\n \n29,6\n \n16,9\n \n16,6\n \n16,7\n \nSan (samogho ou \nsamo)\n \n0,2\n \n0,\n1\n \n0,1\n \n3,7\n \n3,6\n \n3,6\n \n1,6\n \n1,6\n \n1,6\n \n0,9\n \n0,9\n \n0,9\n \nDioula (ou bambara)\n \n3,5\n \n3,7\n \n3,6\n \n3,7\n \n3,5\n \n3,6\n \n23,2\n \n23,2\n \n23,2\n \n7,3\n \n8,2\n \n7,7\n \nFulfudé (ou peulh)\n \n7,2\n \n6,8\n \n7\n,0\n \n5,4\n \n5,2\n \n5,3\n \n9,6\n \n9,6\n \n9,6\n \n6,5\n \n6,3\n \n6,4\n \nBobo\n \n0,9\n \n0,9\n \n0,9\n \n16,6\n \n16,7\n \n16,7\n \n0,7\n \n0,7\n \n0,7\n \n0,5\n \n0,5\n \n0,5\n \nNuni (nounouma)\n \n4,1\n \n4,1\n \n4,1\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n7,9\n \n7,9\n \n7,9\n \nDogon (ou kaado)\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0,8\n \n0,8\n \n0,8\n \n8,1\n \n8,8\n \n8,4\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \nKo\n \n6,4\n \n6,4\n \n6,4\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0,1\n \n0,1\n \n0,1\n \nAutres \nl\nangues\n \n6,8\n \n6,4\n \n6,6\n \n3\n \n2,7\n \n2,8\n \n3,5\n \n3,5\n \n3,5\n \n3,1\n \n2,7\n \n2,9\n \nTotal\n \n100,\n0\n \n100,\n0\n \n100,\n0\n \n100\n,\n0\n \n100,\n0\n \n100,\n0\n \n100,\n0\n \n100,\n0\n \n100,\n0\n \n100,\n0\n \n100,\n0\n \n100,\n0\n \n \nPrincipales langues \nparlées\n \nNayala\n \nSourou\n \nEnsemble\n \nM\n \nF\n \nM + F\n \nM\n \nF\n \nM + F\n \nM\n \nF\n \nM + F\n \nMooré\n \n21,5\n \n24\n,0\n \n22,8\n \n22,2\n \n23,4\n \n22,8\n \n27,3\n \n28,9\n \n28,1\n \nMarka (ou Dafing)\n \n19,1\n \n17,8\n \n18,4\n \n8,3\n \n7,7\n \n8\n,0\n \n15,8\n \n14,7\n \n15,3\n \nBwamu \n(ou bwamou)\n \n0,1\n \n0,1\n \n0,1\n \n0,1\n \n0,1\n \n0,1\n \n14,8\n \n14,7\n \n14,8\n \nSan (samogho ou samo)\n \n47,5\n \n45,7\n \n46,6\n \n51,1\n \n50,7\n \n50,9\n \n14,4\n \n14\n,0\n \n14,2\n \nDioula (ou bambara)\n \n1,2\n \n1,2\n \n1,2\n \n9,1\n \n9,1\n \n9,1\n \n8,5\n \n8,6\n \n8,5\n \nFulfudé (ou peulh)\n \n3,6\n \n3,5\n \n3,5\n \n5,7\n \n5,6\n \n5,7\n \n6,5\n \n6,3\n \n6,4\n \nBobo\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0,1\n \n0,\n1\n \n0,1\n \n3,4\n \n3,5\n \n3,5\n \nNuni (nounouma)\n \n0,6\n \n0,6\n \n0,6\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n2,4\n \n2,4\n \n2,4\n \nDogon (ou kaado)\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0,1\n \n0,1\n \n0,1\n \n1,6\n \n1,7\n \n1,7\n \nKo\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n0\n,0\n \n1,1\n \n1,1\n \n1,1\n \nAutres Langues\n \n6,5\n \n7,2\n \n6,9\n \n3,4\n \n3,1\n \n3,2\n \n4,2\n \n4\n,0\n \n4,1\n \nTotal\n \n100,0\n \n100,0\n \n100,0\n \n100,0\n \n100,0\n \n10\n0,0\n \n100,0\n \n100,0\n \n100,0\n \n'

CENTRE_NORD_CHARTLESS = 'i, les musulmans représentent 71,7% en \nmilieu urbain contre 66,7% en milieu rural. Comme l’islam, le catholicisme est plus adopté en milieu \nurbain (22,9%) contre 14,5% en milieu rural. À l’opposé, l’animisme est plus adopté en milieu rural \n(15,7 %) contre 0,5% en milieu urbain (graphique 3.1). \nGraphique 3.1 : Répartition (%) de la population par religion selon le milieu de résidence \nLa religion musulmane reste la plus dominante dans les trois (03) provinces de la région du Centre-\nNord. Toutefois, la communauté musulmane est plus représentée dans le Bam que dans le \nSanmatenga et le Namentenga. En effet, plus de 78,4% de la population du Bam sont des \nmusulmans tandis que dans le Sanmatenga et le N amentenga, ceux-ci sont respectivement de \n66,6% et 60,8%.  Par contre, pour l’animisme, le catholicisme et le protestantisme la situation varie \nd’une province à l’autre. Ainsi, la province du Namentenga regorge plus d’animistes (24,3%). Quant \naux catholiques, ils sont plus représentés dans la province du Bam (19,4%) et les protestants bien \nque minoritaires se rencontrent plus dans la province du Sanmatenga (3,9%). \n0,5\n15,7 13,8\n71,7\n66,7 67,3\n22,9\n14,5 15,6\n4,9 2,8 3,10,0 0,0 0,00,1 0,3 0,2\n0\n10\n20\n30\n40\n50\n60\n70\n80\nUrbain Rural Ensemble\nAnimiste Musulman Catholique Protestant Autre Sans religion\n\x0c\n____________________________________________________________________________\nRGPH 2019 -Monographie du Centre Nord  | 17  \nGraphique 3.2 : Répartition (%) de la population des communautés religieuses par province \n3.2. CARACTERISTIQUES DE LA POPULATION SELON LES \nLANGUES PARLEES \nLa langue parlée, en tant que moyen de communication et d’échanges, est un élément de \nrapprochement entre individus, groupes de personnes, communau tés, nations, etc. Elle constitue \négalement u'


class ReligionAndLanguageByProvince(unittest.TestCase):
    def test_chart_series_by_series(self):
        out = bp.religion_charts(CASCADES_CHART, ["Comoe", "Leraba"])
        self.assertEqual(sorted(out.pop("_seen")), ["Comoe", "Ensemble", "Leraba"])
        self.assertEqual(out["Comoe"], dict(zip(bp.RELIGIONS, [9.3, 79.2, 7.3, 1.9, 0.3, 2.1])))
        self.assertEqual(out["Leraba"]["Islam"], 89.7)
        self.assertEqual(out["Ensemble"]["No religion"], 1.9)

    def test_chart_that_is_a_picture(self):
        out = bp.religion_charts(CENTRE_NORD_CHARTLESS, ["Bam", "Namentenga", "Sanmatenga"])
        self.assertEqual(out, {"_seen": {}})

    def test_glued_figures(self):
        self.assertEqual(bp.tokens_of("22,320,5 0,40,9 29 ,0 0, 1 100 , 0"),
                         ["22,3", "20,5", "0,4", "0,9", "29,0", "0,1", "100,0"])

    def test_table_with_a_region_column(self):
        names = ["Boulgou", "Koulpelogo", "Kouritenga"]
        out = bp.language_table(CENTRE_EST_TABLE, names)
        self.assertEqual(sorted(out), ["Boulgou", "Ensemble", "Koulpelogo", "Kouritenga"])
        self.assertEqual(out["Boulgou"]["Bissa"], 65.5)
        self.assertEqual(out["Kouritenga"]["Mooré"], 92.3)
        self.assertEqual(out["Ensemble"]["Mooré"], 53.4)
        self.assertEqual(out["Koulpelogo"]["Koussassé"], 0.0)
        for col in out.values():
            self.assertAlmostEqual(sum(col.values()), 100, delta=1.5)

    def test_table_in_two_blocks_with_broken_figures(self):
        names = ["Bale", "Banwa", "Kossi", "Mouhoun", "Nayala", "Sourou"]
        out = bp.language_table(BDM_TABLE, names)
        self.assertEqual(sorted(out), sorted(names + ["Ensemble"]))
        self.assertEqual(out["Bale"]["Mooré"], 29.2)            # "29 ,0 29,4 29,2"
        self.assertEqual(out["Nayala"]["Samo"], 46.6)
        self.assertEqual(out["Ensemble"]["Mooré"], 28.1)
        self.assertEqual(out["Bale"]["Ko"], 6.4)

    def test_row_figures_broken_elsewhere(self):
        self.assertEqual(bp.row_values("3 2,7 2,8".split(), 3), [3.0, 2.7, 2.8])
        # "10 0,0" is 100,0 broken: joining it is the one reading that fits.
        self.assertEqual(bp.row_values("10 0,0 100,0 100,0".split(), 3), [100.0, 100.0, 100.0])
        self.assertIsNone(bp.row_values("1,0 2,0 9,0".split(), 3))   # both sexes off

    def test_records(self):
        shapes = [{"id": "b", "name": "Boulgou"}, {"id": "k", "name": "Koulpelogo"},
                  {"id": "t", "name": "Kouritenga"}]
        with unittest.mock.patch.object(bp, "log"):
            recs = bp.region_records("Centre-Est", shapes, {"id": "ce", "name": "Centre-Est"},
                                     "u", CENTRE_EST_TABLE + "\f" + CENTRE_NORD_CHARTLESS)
        by = {(r["level"], r["name"]): r for r in recs}
        boulgou = by[("admin2", "Boulgou")]
        self.assertEqual(boulgou["language"][0], {"group": "Bissa", "pct": 65.5})
        self.assertEqual(boulgou["language_year"], 2019)
        # No chart labels these provinces: the reason says the chart is a picture.
        self.assertIn("without printing the figures", boulgou["religion"]["note"])
        region = by[("admin1", "Centre-Est")]
        self.assertEqual(region["language"][0], {"group": "Mooré", "pct": 53.4})
        self.assertNotIn("value", boulgou["sex_ratio"])   # no Tableau 2.3 in this text

    def test_heading_repeated_over_a_page(self):
        # Constructed from Sud-Ouest's second block as run 4 logged it: the
        # heading stands again before the rows the next page carries.
        text = ("Tableau 3.3: Répartition (%) de la population de 3 ans ou plus selon les "
                "principales langues parlées par sexe et la province Principales langues "
                "parlées Noumbiel Ensemble M F M + F M F M + F Dagara 60,0 60,0 60,0 "
                "50,0 50,0 50,0 Principales langues par- lées Noumbiel Ensemble M F M + F "
                "M F M + F Dyan 40,0 40,0 40,0 50,0 50,0 50,0 Ensemble 100,0 100,0 100,0 "
                "100,0 100,0 100,0")
        out = bp.language_table(text, ["Noumbiel", "Poni"])
        self.assertEqual(out["Noumbiel"], {"Dagara": 60.0, "Dyan": 40.0})

    def test_region_tables_after_the_list_of_tables(self):
        listing = ("Tableau 3.1: Répartition (%) de la population par religion selon le sexe "
                   "....... 17 Tableau 3.2: Répartition (%) de la population de 3 ans ou plus "
                   "par principale langue parlée selon le milieu de résidence ...... 19 ")
        body = ("Tableau 3.1: Répartition (%) de la population par religion selon le sexe "
                "Religion Masculin Féminin Ensemble Animiste 0,4 0,2 0,3 Musulman 61,9 60,5 "
                "61,2 Catholique 30,7 31,8 31,3 Protestant 6,7 7,2 6,9 Autre 0,2 0,1 0,2 "
                "Sans religion 0,2 0,1 0,1 Ensemble 100,0 100,0 100,0 ")
        self.assertEqual(bp.region_religion(listing + body)["Islam"], 61.2)

    def test_every_label_is_named(self):
        for label in ("Fulfudé (ou peulh)", "Fulfudé/peulh", "Kasséna (ou kassem)",
                      "San (ou samogho ou samo)", "Autres l angues", "Haoussa", "Gourounsi"):
            self.assertIsNotNone(bp.language_name(label), label)


if __name__ == "__main__":
    unittest.main()
