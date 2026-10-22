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


# The age tables as the runner printed them (dump fix1, 5f564f4): Centre-Nord's
# Tableau 2.5 with figures broken across lines ("152 10" then "2"), the Boucle's
# with a two-digit figure broken ("7" then "1" for 71), the Centre's Tableau 2.3.
CENTRE_NORD_AGES = "Tableau 2.5: Effectif de la population par groupe d'âge selon le milieu de résidence et le sexe  \nGroupe \nd'âge \nRural Urbain Ensemble \nMasc. Fém. Ens. Mas. Fém. Ens. Masc. Fém. Ens. \n0-4 152\u202f10\n2\n151\u202f16\n9\n303\u202f271 14\u202f324 14 733 29 057 166 426 165 902 332 328 \n5-9 149\u202f08\n8\n146\u202f48\n1\n295\u202f569 13\u202f643 14 238 27 881 162 731 160 719 323 450 \n10-14 115\u202f41\n0\n112\u202f97\n8\n228\u202f388 12\u202f091 13 273 25 364 127 501 126 251 253 752 \n15-19 78 188 92 084 170\u202f272 11\u202f129 13 513 24 642 89 317 105 597 194 914 \n20-24 53 330 73 671 127\u202f001 9\u202f298 11 541 20 839 62 628 85 212 147 840 \n25-29 44 833 62 707 107\u202f540 7\u202f495 8 700 16 195 52 328 71 407 123 735 \n30-34 40 180 54 476 94\u202f656 6\u202f939 6 970 13 909 47 119 61 446 108 565 \n35-39 32 793 43 342 76\u202f135 5\u202f658 5 086 10 744 38 451 48 428 86\u202f879 \n40-44 27 447 35 790 63\u202f237 4\u202f284 3 816 8 100 31 731 39 606 71\u202f337 \n45-49 20 410 26 152 46\u202f562 2\u202f970 2 758 5 728 23 380 28 910 52\u202f290 \n50-54 19 652 23 776 43\u202f428 2\u202f431 2 325 4 756 22 083 26 101 48\u202f184 \n55-59 15 107 16 740 31\u202f847 1\u202f708 1 885 3 593 16 815 18 625 35\u202f440 \n60-64 13 431 14 644 28\u202f075 1\u202f446 1 538 2 984 14 877 16 182 31\u202f059 \n65-69 9 809 8 940 18\u202f749 934 1 063 1 997 10 743 10 003 20\u202f746 \n70-74 8 591 8 925 17\u202f516 797 909 1 706 9\u202f388 9\u202f834 19\u202f222 \n75-79 4 630 4 343 8\u202f973 415 511 926 5\u202f045 4\u202f854 9\u202f899 \n80-84 2 926 3 265 6\u202f191 259 387 646 3\u202f185 3\u202f652 6\u202f837 \n85-89 1 544 1 596 3\u202f140 110 178 288 1\u202f654 1\u202f774 3\u202f428 \n90-94 880 1 227 2\u202f107 67 131 198 947 1\u202f358 2\u202f305 \n95 ou + 965 1 250 2\u202f215 100 144 244 1\u202f065 1\u202f394 2\u202f459 \nTotal 791\u202f31\n6\n883\u202f55\n6\n1\u202f674\u202f872 96 098 103 699 199 79\n7\n887 414 987 255 1 874\u202f669 \nAge moyen 20,0 21,3 20,7 22,0 21,9 21,9 20,2 21,3 20,8 \nAge médian 13,0 16,7 15,3 18,6 18,7 18,6 14,4 16,0 15,6 \n"
BOUCLE_AGES = "Tableau \n2\n.\n5\n: Effectif de la po\npulation par groupe d'âge selon le milieu de résidence et le sexe\n \nGroupe d'âge\n \nRural\n \nUrbain\n \nEnsemble\n \nM\n \nF\n \nM+F\n \nM\n \nF\n \nM+F\n \nM\n \nF\n \nM+F\n \n0\n-\n4 \n \n144\n\u202f\n950\n \n142\n\u202f\n651\n \n287\n\u202f\n601\n \n11\n\u202f\n061\n \n11\n\u202f\n187\n \n22\n\u202f\n248\n \n156\n\u202f\n011\n \n153\n\u202f\n838\n \n309\n\u202f\n849\n \n5\n-\n9\n \n151\n\u202f\n448\n \n145\n\u202f\n015\n \n296\n\u202f\n463\n \n11\n\u202f\n080\n \n11\n\u202f\n597\n \n22\n\u202f\n677\n \n162\n\u202f\n528\n \n156\n\u202f\n612\n \n319\n\u202f\n140\n \n10\n-\n14\n \n123\n\u202f\n163\n \n109\n\u202f\n065\n \n232\n\u202f\n228\n \n10\n\u202f\n929\n \n12\n\u202f\n324\n \n23\n\u202f\n253\n \n134\n\u202f\n092\n \n121\n\u202f\n389\n \n255\n\u202f\n481\n \n15\n-\n19 \n \n90\n\u202f\n536\n \n79\n\u202f\n344\n \n169\n\u202f\n880\n \n11\n\u202f\n787\n \n12\n\u202f\n992\n \n24\n\u202f\n779\n \n102\n\u202f\n323\n \n92\n\u202f\n336\n \n194\n\u202f\n659\n \n20\n-\n24  \n \n62\n\u202f\n941\n \n70\n\u202f\n118\n \n133\n\u202f\n059\n \n10\n\u202f\n388\n \n10\n\u202f\n523\n \n20\n\u202f\n911\n \n73\n\u202f\n329\n \n80\n\u202f\n641\n \n153\n\u202f\n970\n \n25\n-\n29 \n \n53\n\u202f\n408\n \n63\n\u202f\n510\n \n116\n\u202f\n918\n \n7\n\u202f\n214\n \n7\n\u202f\n576\n \n14\n\u202f\n790\n \n60\n\u202f\n622\n \n71\n\u202f\n086\n \n131\n\u202f\n708\n \n30\n-\n34 \n \n49\n\u202f\n738\n \n56\n\u202f\n208\n \n105\n\u202f\n946\n \n6\n\u202f\n633\n \n6\n\u202f\n359\n \n12\n\u202f\n992\n \n56\n\u202f\n371\n \n62\n\u202f\n567\n \n118\n\u202f\n938\n \n35\n-\n39\n \n \n40\n\u202f\n924\n \n45\n\u202f\n196\n \n86\n\u202f\n120\n \n5\n\u202f\n262\n \n5\n\u202f\n018\n \n10\n\u202f\n280\n \n46\n\u202f\n186\n \n50\n\u202f\n214\n \n96\n\u202f\n400\n \n40\n-\n44 \n \n32\n\u202f\n553\n \n36\n\u202f\n071\n \n68\n\u202f\n624\n \n4\n\u202f\n246\n \n3\n\u202f\n640\n \n7\n\u202f\n886\n \n36\n\u202f\n799\n \n39\n\u202f\n711\n \n76\n\u202f\n510\n \n45\n-\n49 \n \n25\n\u202f\n891\n \n27\n\u202f\n955\n \n53\n\u202f\n846\n \n3\n\u202f\n275\n \n2\n\u202f\n803\n \n6\n\u202f\n078\n \n29\n\u202f\n166\n \n30\n\u202f\n758\n \n59\n\u202f\n924\n \n50\n-\n54 \n \n22\n\u202f\n151\n \n24\n\u202f\n323\n \n46\n\u202f\n474\n \n2\n\u202f\n529\n \n2\n\u202f\n461\n \n4\n\u202f\n990\n \n24\n\u202f\n680\n \n26\n\u202f\n784\n \n51\n\u202f\n464\n \n55\n-\n59 \n \n17\n\u202f\n483\n \n18\n\u202f\n444\n \n35\n\u202f\n927\n \n1\n\u202f\n904\n \n1\n\u202f\n848\n \n3\n\u202f\n752\n \n19\n\u202f\n387\n \n20\n\u202f\n292\n \n39\n\u202f\n679\n \n60\n-\n64 \n \n13\n\u202f\n912\n \n15\n\u202f\n594\n \n29\n\u202f\n506\n \n1\n\u202f\n480\n \n1\n\u202f\n509\n \n2\n\u202f\n989\n \n15\n\u202f\n392\n \n17\n\u202f\n103\n \n32\n\u202f\n495\n \n65\n-\n69 \n \n9\n\u202f\n977\n \n9\n\u202f\n799\n \n19\n\u202f\n776\n \n968\n \n1\n\u202f\n066\n \n2\n\u202f\n034\n \n10\n\u202f\n945\n \n10\n\u202f\n865\n \n21\n\u202f\n810\n \n70\n-\n74 \n \n7\n\u202f\n646\n \n8\n\u202f\n195\n \n15\n\u202f\n841\n \n733\n \n899\n \n1\n\u202f\n632\n \n8\n\u202f\n37\n9\n \n9\n\u202f\n094\n \n17\n\u202f\n473\n \n75\n-\n79 \n \n4\n\u202f\n293\n \n4\n\u202f\n515\n \n8\n\u202f\n808\n \n369\n \n510\n \n879\n \n4\n\u202f\n662\n \n5\n\u202f\n025\n \n9\n\u202f\n687\n \n80\n-\n84 \n \n2\n\u202f\n432\n \n3\n\u202f\n136\n \n5\n\u202f\n568\n \n220\n \n336\n \n556\n \n2\n\u202f\n652\n \n3\n\u202f\n472\n \n6\n\u202f\n124\n \n85\n-\n89 \n \n1\n\u202f\n071\n \n1\n\u202f\n312\n \n2\n\u202f\n383\n \n108\n \n141\n \n249\n \n1\n\u202f\n179\n \n1\n\u202f\n453\n \n2\n\u202f\n632\n \n90\n-\n94 \n \n568\n \n695\n \n1\n\u202f\n263\n \n31\n \n87\n \n118\n \n599\n \n782\n \n1\n\u202f\n381\n \n95 ou +\n \n826\n \n993\n \n1\n\u202f\n819\n \n55\n \n7\n1\n \n126\n \n881\n \n1\n\u202f\n064\n \n1\n\u202f\n945\n \nTotal\n \n855\n\u202f\n911\n \n862\n\u202f\n139\n \n1\n\u202f\n718\n\u202f\n05\n90\n\u202f\n272\n \n92\n\u202f\n947\n \n183\n\u202f\n21\n946\n\u202f\n183\n \n955\n\u202f\n086\n \n1\n\u202f\n901\n\u202f\n26\nAge moyen\n \n20,7\n \n21,8\n \n21,3\n \n23,2\n \n22,9\n \n23,1\n \n21\n \n21,9\n \n21,4\n \nAge médian\n \n14,3\n \n16,0\n \n15,0\n \n19,0\n \n18,3\n \n18,7\n \n15,0\n \n16,5\n \n15,5\n \n"
CENTRE_AGES = "Tabl\neau \n2\n.\n3\n \n: Effectif de la population par groupe d'âge selon le milieu de résidence et le sexe\n \nGroupe d'âge\n \nRural\n \nUrbain\n \nEnsemble\n \nMasculin\n \nFéminin\n \nEnsemble\n \nMasculin\n \nFéminin\n \nEnsemble\n \nMasculin\n \nFéminin\n \nEnsemble\n \n0\n-\n4 \n \n48 342\n \n47 296\n \n95 638\n \n156 611\n \n155 533\n \n312 144\n \n204 953\n \n202 829\n \n407 782\n \n5\n-\n9\n \n42 102\n \n43 074\n \n85 176\n \n135 165\n \n142 921\n \n278 086\n \n177 267\n \n185 995\n \n363 262\n \n10\n-\n14\n \n35 829\n \n36 454\n \n72 283\n \n118 096\n \n138 183\n \n256 279\n \n153 925\n \n174 637\n \n328 562\n \n15\n-\n19 \n \n27 420\n \n31 560\n \n58 980\n \n108 919\n \n152 382\n \n261 301\n \n136 339\n \n183 942\n \n320 281\n \n20\n-\n24  \n \n23 695\n \n32 191\n \n55 886\n \n115 539\n \n142 336\n \n257 875\n \n139 234\n \n174 527\n \n313 761\n \n25\n-\n29 \n \n25 424\n \n30 131\n \n55 555\n \n115 615\n \n126 166\n \n241 781\n \n141 039\n \n156 297\n \n297 336\n \n30\n-\n34 \n \n28 026\n \n24 637\n \n52 663\n \n111 725\n \n104 013\n \n215 738\n \n139 751\n \n128 650\n \n268 401\n \n35\n-\n39 \n \n23 385\n \n17 591\n \n40 976\n \n90 824\n \n76 845\n \n167 669\n \n114 209\n \n94 436\n \n208 645\n \n40\n-\n44 \n \n17 063\n \n11 404\n \n28 467\n \n69 816\n \n53 021\n \n122 837\n \n86 879\n \n64 425\n \n151 304\n \n45\n-\n49 \n \n10 597\n \n7 929\n \n18 526\n \n49 005\n \n37 238\n \n86 243\n \n59 602\n \n45 167\n \n104 769\n \n50\n-\n54 \n \n7 551\n \n6 743\n \n14 294\n \n36 163\n \n29 763\n \n65 926\n \n43 714\n \n36 506\n \n80 220\n \n55\n-\n59 \n \n4 953\n \n5 215\n \n10 168\n \n25 965\n \n23 434\n \n49 399\n \n30 918\n \n28 649\n \n59 567\n \n60\n-\n64 \n \n4 008\n \n4 742\n \n8 750\n \n20 369\n \n17 760\n \n38 129\n \n24 377\n \n22 502\n \n46 879\n \n65\n-\n69 \n \n2 602\n \n3 161\n \n5 763\n \n12 654\n \n11 309\n \n23 963\n \n15 256\n \n14 470\n \n29 \n726\n \n70\n-\n74 \n \n2 242\n \n2 859\n \n5 101\n \n8 394\n \n8 839\n \n17 233\n \n10 636\n \n11 698\n \n22 334\n \n75\n-\n79 \n \n1 283\n \n1 617\n \n2 900\n \n4 102\n \n4 874\n \n8 976\n \n5 385\n \n6 491\n \n11 876\n \n80\n-\n84 \n \n708\n \n1 196\n \n1 904\n \n2 094\n \n3 449\n \n5 543\n \n2 802\n \n4 645\n \n7 447\n \n85\n-\n89 \n \n323\n \n579\n \n902\n \n818\n \n1 508\n \n2 326\n \n1 141\n \n2 087\n \n3 228\n \n90\n-\n94 \n \n147\n \n372\n \n519\n \n347\n \n858\n \n1 205\n \n494\n \n1 230\n \n1 724\n \n95 ou +\n \n255\n \n412\n \n667\n \n1 336\n \n1 277\n \n2 613\n \n1 591\n \n1 689\n \n3 280\n \nEnsemble\n \n305 955\n \n309 163\n \n615 118\n \n1 183 557\n \n1 231 709\n \n2 415 266\n \n1 489 512\n \n1 540 872\n \n3 030 384\n \nAge moyen\n \n22,6\n \n22,1\n \n22,3\n \n24,5\n \n23,1\n \n23,8\n \n24,1\n \n22,9\n \n23,5\n \nAge \nmédian\n \n19\n \n19,4\n \n19,6\n \n19\n \n20,8\n \n21\n \n22,5\n \n20,5\n \n21,3\n \n \n"
# Constructed in Tableau 2.1's words, with the regions' counts the age tables total.
CENTRE_NORD_COUNT = ("Tableau 2.1 : Répartition de la population par milieu de résidence selon "
                     "le sexe en 2019 Milieu de résidence Masculin Féminin Ensemble Urbain "
                     "96 098 103 699 199 797 Rural 791 316 883 556 1 674 872 Ensemble 887 414 "
                     "987 255 1 874 669")
CENTRE_COUNT = ("Tableau 2.1 : Répartition de la population par milieu de résidence selon le "
                "sexe en 2019 Milieu de résidence Masculin Féminin Ensemble Urbain 1 183 557 "
                "1 231 709 2 415 266 Rural 305 955 309 163 615 118 Ensemble 1 489 512 "
                "1 540 872 3 030 384")

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
# their commas, and the Centre-Nord's caption of its chart, whose labels the
# text keeps after the next caption.
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

    def test_caption_apart_from_its_labels(self):
        # Centre-Nord's caption of Graphique 3.2 with no labels by it: the text
        # keeps them after the next caption (CENTRE_NORD_LABELS below).
        out = bp.religion_charts(CENTRE_NORD_CHARTLESS, ["Bam", "Namentenga", "Sanmatenga"])
        self.assertEqual(out, {"_seen": {}})

    def test_another_chart_of_the_provinces_is_not_the_religions(self):
        # Constructed: a literacy chart by province (no religion legend by it)
        # beside the caption of the religions' chart.
        literacy = (" 45,1 30,2 38,0 0 10 20 30 40 50 BAM NAMENTENGA SANMATENGA Taux "
                    "d'alphabétisation (%) ")
        out = bp.religion_charts(CENTRE_NORD_CHARTLESS + literacy,
                                 ["Bam", "Namentenga", "Sanmatenga"])
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
        # No chart labels these provinces: the reason says the chart prints none.
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


# The labels of the religions' charts (Graphique 3.2) of Centre-Nord,
# Centre-Ouest, Centre-Sud and Nord as the runner's text keeps them
# (--dump=composition1): after the next caption, with the region's column
# named Total or for the region, ticks by 20 or with a decimal.
CENTRE_NORD_LABELS = 'Graphique 3.3 : Répartition (%) de la population de 3 ans ou plus selon les principales langues parlées \n1,0\n24,3\n12,2 13,8\n78,4\n60,8\n66,6 67,3\n19,4\n11,4\n16,9 15,6\n1,0 3,3 3,9 3,1\n0,0\n0,0\n0,1 0,0\n0,1 0,2 0,3 0,2\n0\n10\n20\n30\n40\n50\n60\n70\n80\n90\nBAM NAMENTENGA SANMATENGA TOTAL\nAnimiste Musulman Catholique Protestant Autre Sans religion\n88,2\n7,9\n2,1 1,8\n0,0\n10,0\n20,0\n30,0\n40,0\n50,0\n60,0\n70,0'

CENTRE_OUEST_CHART = 'Ouest parle principalement le Français. Le reste de la population (2,1%) ont déclaré d’autres \nlangues comme langues principalement parlées. \n  \n7,1\n12,7 9,6 7,0 8,9\n38,2\n24,9\n68,2 70,0\n45,845,4 48,9\n14,7 16,3\n35,7\n8,9 11,0 6,7 6,1 8,5\n0,1 0,4 0,1 0,0 0,20,3 2,1 0,7 0,6 0,9\n0,0\n10,0\n20,0\n30,0\n40,0\n50,0\n60,0\n70,0\n80,0\nBOULKIEMDE SANGUIE SISSILI ZIRO Ensemble\nProportion\nAnimiste Musulman Catholique Protestant Autre Sans religion'

CENTRE_SUD_CHART = 'parlées sont très faibles (par moins de 1% de la population) (graphique 3.3). \n  \n3,4 \n24,4 \n0,9 \n7,6 \n53,2 \n33,4 \n68,1 \n54,2 \n37,9 \n17,8 \n27,8 28,9 \n5,4 \n23,1 \n3,1 \n8,9 \n0,0 0,6 0,0 0,2 0,1 0,8 0,1 0,3 \n0\n10\n20\n30\n40\n50\n60\n70\n80\nBAZEGA NAHOURI ZOUNDWEOGO Centre-Sud\nProportion\nProvince\nAnimiste Musulman Catholique Protestant Autre Sans religion'

NORD_CHART = 'population de la région (graphique 3.3). \n  \n20,1\n0,3 0,1 2,2\n49,4\n96,5 97,8\n88,5\n22,5\n2,2 1,4 7,77,7\n0,6\n0,5\n1,30,1\n0,0 0,0 0,00,2\n0,3 0,2\n0,3\n0\n20\n40\n60\n80\n100\n120\nPASSORE YATENGA LOROUM ZONDOMA\nAnimiste Musulman Catholique Protestant Autre Sans religion'


class ReligionChartsOfFourRegions(unittest.TestCase):
    def test_region_column_named_total(self):
        out = bp.religion_charts(CENTRE_NORD_LABELS, ["Bam", "Namentenga", "Sanmatenga"],
                                 "Centre-Nord")
        self.assertEqual(sorted(out.pop("_seen")), ["Bam", "Ensemble", "Namentenga", "Sanmatenga"])
        self.assertEqual(out["Bam"], dict(zip(bp.RELIGIONS, [1.0, 78.4, 19.4, 1.0, 0.0, 0.1])))
        self.assertEqual(out["Namentenga"]["Animist"], 24.3)
        self.assertEqual(out["Sanmatenga"]["Protestant"], 3.9)
        self.assertEqual(out["Ensemble"]["Islam"], 67.3)

    def test_ticks_with_a_decimal_and_glued_figures(self):
        out = bp.religion_charts(CENTRE_OUEST_CHART,
                                 ["Boulkiemde", "Sanguie", "Sissili", "Ziro"], "Centre-Ouest")
        self.assertEqual(out["Boulkiemde"]["Catholic"], 45.4)       # "45,845,4"
        self.assertEqual(out["Sanguie"], dict(zip(bp.RELIGIONS, [12.7, 24.9, 48.9, 11.0, 0.4, 2.1])))
        self.assertEqual(out["Ziro"]["Islam"], 70.0)
        self.assertEqual(out["Ensemble"]["No religion"], 0.9)

    def test_region_column_named_for_the_region(self):
        out = bp.religion_charts(CENTRE_SUD_CHART, ["Bazega", "Nahouri", "Zoundweogo"],
                                 "Centre-Sud")
        self.assertEqual(sorted(out.pop("_seen")), ["Bazega", "Ensemble", "Nahouri", "Zoundweogo"])
        self.assertEqual(out["Nahouri"], dict(zip(bp.RELIGIONS, [24.4, 33.4, 17.8, 23.1, 0.6, 0.8])))
        self.assertEqual(out["Zoundweogo"]["Islam"], 68.1)
        self.assertEqual(out["Bazega"]["Catholic"], 37.9)

    def test_ticks_by_twenty(self):
        out = bp.religion_charts(NORD_CHART, ["Loroum", "Passore", "Yatenga", "Zondoma"], "Nord")
        self.assertEqual(out.pop("_seen"), dict.fromkeys(["Passore", "Yatenga", "Loroum",
                                                          "Zondoma"], 1.0))
        self.assertEqual(out["Passore"], dict(zip(bp.RELIGIONS, [20.1, 49.4, 22.5, 7.7, 0.1, 0.2])))
        self.assertEqual(out["Loroum"]["Islam"], 97.8)
        self.assertEqual(out["Zondoma"]["Catholic"], 7.7)            # "7,77,7"

    def test_axis_ticks(self):
        self.assertEqual(bp.ticks_end("5 0 20 40 60 80 x".split(), 1), 6)
        self.assertEqual(bp.ticks_end("0,0 10,0 20,0 30,0 Mooré".split(), 0), 4)
        self.assertEqual(bp.ticks_end("0 10 20 x".split(), 0), 0)        # too few
        self.assertEqual(bp.ticks_end("0 3 6 9 12".split(), 0), 0)       # not an axis's step

    def test_records_of_a_region_whose_column_is_named_for_it(self):
        shapes = [{"id": "b", "name": "Bazega"}, {"id": "n", "name": "Nahouri"},
                  {"id": "z", "name": "Zoundweogo"}]
        with unittest.mock.patch.object(bp, "log"):
            recs = bp.region_records("Centre-Sud", shapes, None, "u", CENTRE_SUD_CHART)
        by = {r["name"]: r for r in recs}
        self.assertEqual(sorted(by), ["Bazega", "Nahouri", "Zoundweogo"])
        self.assertEqual(by["Nahouri"]["religion"][0], {"group": "Islam", "pct": 33.4})
        self.assertIn("charts them by province", by["Nahouri"]["religion_note"])


    def test_age_table_with_figures_broken_across_lines(self):
        got = bp.age_table(CENTRE_NORD_AGES)
        self.assertEqual(len(got["groups"]), 20)
        self.assertEqual(got["groups"][0], (0, 4, 332_328))
        self.assertEqual(got["groups"][-1], (95, None, 2_459))
        self.assertEqual((got["men"], got["women"]), (887_414, 987_255))
        self.assertEqual(sum(g[2] for g in got["groups"]), 1_874_669)
        self.assertEqual(got["printed"], 15.6)
        self.assertEqual(got["table"], "Tableau 2.5")
        self.assertEqual(bp.grouped_median(got["groups"]), 15.7)

    def test_age_table_with_a_two_digit_figure_broken(self):
        got = bp.age_table(BOUCLE_AGES)
        self.assertEqual(got["groups"][-1], (95, None, 1_945))   # 55 + 71 urban
        self.assertEqual(got["groups"][14], (70, 74, 17_473))    # "8 37 9" is 8 379
        self.assertEqual((got["men"], got["women"]), (946_183, 955_086))
        self.assertEqual(got["printed"], 15.5)
        # Boucle du Mouhoun's table prints 15.5; its own groups give 16.7.
        median = bp.grouped_median(got["groups"])
        self.assertEqual(median, 16.7)
        self.assertEqual(bp.printed_median(got, median),
                         " The table itself prints a median of 15.5, which its own counts by "
                         "five-year age group do not bear out.")
        self.assertEqual(bp.printed_median({"printed": None}, median), "")

    def test_region_figures_and_the_communes_not_enumerated(self):
        shapes = [{"id": "b", "name": "Bam"}, {"id": "n", "name": "Namentenga"},
                  {"id": "s", "name": "Sanmatenga"}]
        with unittest.mock.patch.object(bp, "log"):
            recs = bp.region_records("Centre-Nord", shapes, {"id": "cn", "name": "Centre-Nord"},
                                     "u", CENTRE_NORD_COUNT + "\f" + CENTRE_NORD_AGES)
        region = next(r for r in recs if r["level"] == "admin1")
        self.assertEqual(region["sex_ratio"]["value"], round(1000 * 887_414 / 987_255))
        self.assertEqual(region["sex_ratio"]["year"], 2019)
        self.assertEqual(region["median_age"]["value"], 15.7)
        self.assertIn("Tableau 2.5", region["median_age_note"])
        # What the table prints is said beside the figure (15.6 against 15.7:
        # within what single years can move it, so not disputed).
        self.assertIn("The table itself prints a median of 15.6.", region["median_age_note"])
        self.assertIn("de l'Habitation (RGPH) 2019", region["sources"][0]["name"])
        # Six communes of Bam and Sanmatenga were not enumerated, two in part.
        self.assertIn("Barsalogho", region["sex_ratio_note"])
        self.assertIn("part of Bourzanga and Pissila", region["median_age_note"])
        self.assertEqual(sorted(s["field"] for s in region["sources"]),
                         ["median_age", "sex_ratio"])
        # No province table in this text: no province takes a figure by sex.
        self.assertFalse(any("value" in (r.get("sex_ratio") or {})
                             for r in recs if r["level"] == "admin2"))
        self.assertEqual(bp.coverage_note(["Namentenga"], "shares"), "")
        self.assertIn("these shares are of the residents it enumerated",
                      bp.coverage_note(["Soum"], "shares"))

    def test_the_centre_is_kadiogo(self):
        # The Centre is the one province of Kadiogo: both carry the census's
        # count by sex and the median of its age groups.
        with unittest.mock.patch.object(bp, "log"):
            recs = bp.region_records("Centre", [{"id": "k", "name": "Kadiogo"}],
                                     {"id": "c", "name": "Centre"}, "u",
                                     CENTRE_COUNT + "\f" + CENTRE_AGES)
        by = {r["level"]: r for r in recs}
        for level in ("admin1", "admin2"):
            self.assertEqual(by[level]["sex_ratio"]["value"], round(1000 * 1_489_512 / 1_540_872))
            self.assertEqual(by[level]["median_age"]["value"], 21.5)
        self.assertIn("this one province", by["admin2"]["median_age_note"])
        self.assertIn("Tableau 2.3", by["admin1"]["median_age_note"])

if __name__ == "__main__":
    unittest.main()
