"""Senegal's 2023 regional census reports as the runner printed their pages."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import senegal_regional_reports as sr  # noqa: E402

DAKAR = '\x0c\nRGPH-5 :Rapport de présentation des résultats\n  Région de Dakar\n9\n9\nII.2.2.3. Age moyen et âge médian\nLa moitié de la population  de la région a moins de 24 ans. Cette situation témoigne ainsi de\nsa jeunesse, avec un âge médian similaire aussi bien chez les femmes que chez les hommes.\nL’âge moyen s’établit à 27 ans et ne varie pas selon le sexe dans la région de Dakar.\nTableau II-5 : Age moyen et âge médian de la population selon le sexe et le milieu de résidence\nIndicateurs de tendance\nCentrale\nUrbain Total\nMasculin Féminin Ensemble Masculin Féminin Total\nMoyenne 27 27 27 27 27 27\nMédiane 24 24 24 24 24 24\nSource : ANSD. RGPH-5, 2023\nII.2.2.4. Grands groupes d’âges et Rapport de dépendance\ndémographique\nDans la région, le département de Dakar est le plus peuplé, avec un effectif de 1 278 471\nhabitants. Il est suivi par les départements de Rufisque (818  337 habitants), de Keur Massar\n(770 314 habitants), et de Pikine (764 596 habitants). Guédiawaye demeure le département\nle moins peuplé de la région, avec 372 708 habitants.\nLa répartition par grand groupe d’âge montre que 70,4% de la population du département de\nDakar est âgé entre 15 et 64 ans,  66,0% pour Pikine, 61,5% pour Rufisque,  66,2% pour\nGuédiawaye et 63,3% pour Keur Massar . En revanche, les proportions les plus faibles sont\nobservées dans le groupe d’âge des 65 ans et plus quel que soit le département.\nEn plus , le poids démographique des moins de 15 ans est assez important dans le\ndépartement de Rufisque avec un plus du tiers (34,7%).\nLe rapport de dépendance démographique est relativement faible dans tous les départements.\nAinsi, il est observé 51,6 personnes inactives pour 100 personnes en âge de travailler dans la\nrégion même si tous ceux qui sont potentiellement actifs ne travaillent pas forcément. La même\nsituation est notée à l’échelle départementale où le rapport de dépendance démographique se\nsitue presque sur les mêmes ordres de grandeurs à l’exception des  départements de Dakar\n(42,1) et de Rufisque (62,7) qui se distingue des autres.\nTableau II-6 : Répartition de la population résidente par groupes d’âges selon le département\nGroupe d’âge DAKAR PIKINE RUFISQUE GUEDIAWAYE KEUR MASSAR Région DAKAR\nMoins de 15 ans 316 887 229 982 284 128 109 787 255 658 1 196 442\n15-64 ans 899 852 504 876 502 987 246 656 487 557 2 641 928\n65 ans et plus  61 732 29 739 31 222 16 264 27 098 166 055\nTotal 1 278 471 764 596 818 337 372 708 770 314 4 004 426\nMoins de 15 ans 24,8 30,1 34,7 29,5 33,2 29,87799\n15-64 ans 70,4 66 61,5 66,2 63,3 66\n65 ans et plus  4,8 3,9 3,8 4,4 3,5 4,1\nTotal 100 100 100 100 100 100\n Rapport de dépendance 42,1 51,4 62,7 51,1 58 51,6\nSource : ANSD. RGPH-5, 2023\n\n\x0c\nRGPH-5 :Rapport de présentation des résultats\n  Région de Dakar\n13\n13\nSEXE\n Masculin Féminin Total\nEffectif % Effectif % Effectif %\nApatride 492 0,0 494 0,0 986 0,0\nND 105 0,0 20 0,0 125 0,0\nTotal 2 018 761 100 1 985 666 100 4 004 426 100\nSource : ANSD. RGPH-5, 2023\n PRINCIPALE LANGUE COURAMMENT PARLEE\nDans la région de Dakar, 68,7% des habitants âgés de 3 ans et plus utilisent souvent la langue\nWolof, soit un effectif de 2  478 174 résidents. En plus, le Wolof est une  langue quasiment\nparlée par le même nombre d’hommes ( 68,5%) et de femmes ( 68,9%) de la région.  T andis\nque le Pulaar est utilisé le plus souvent par 15,7% des habitants de Dakar, le Sereer (5,7%),\nle Joola (3,0%), le Français (1,8%) et le Soninké (1,2%) . Les autres langues sont utilisées\ndans la région de Dakar par moins de 1% de la population.\nTableau II-11 : Répartition de la population résidente de 3 ans ou plus par principale langue couramment\nparlée selon le sexe\nSEXE\nMasculin Féminin Total\nEffectif % Effectif % Effectif %\nLangage des signes (Sourd-Muet) 2 079 0,1 1 982 0,1 4 061 0,1\nWolof 1 228 269 68,5 1 249 905 68,9 2 478 174 68,7\nPulaar 292 351 16,3 275 472 15,2 567 823 15,7\nSereer 95 596 5,3 109 674 6,0 205 270 5,7\nJoola 53 214 3,0 56 753 3,1 109 967 3,0\nMàndienka 16 891 0,9 17 329 1,0 34 220 0,9\nSóninke 21 395 1,2 22 457 1,2 43 852 1,2\nhasaniya (maure) 568 0,0 447 0,0 1 014 0,0\nBalant 3 896 0,2 4 143 0,2 8 039 0,2\nMànkaañ 4 588 0,3 4 928 0,3 9 516 0,3\nMànjaku 11 389 0,6 13 523 0,7 24 912 0,7\nMënik 635 0,0 631 0,0 1 266 0,0\nOniyan 117 0,0 130 0,0 247 0,0\nGuñuun 130 0,0 121 0,0 251 0,0\nKanjad 51 0,0 50 0,0 101 0,0\nJalunga 92 0,0 105 0,0 197 0,0\nBayot 192 0,0 191 0,0 383 0,0\nWomey 29 0,0 32 0,0 61 0,0\nautres langues africaines 16 890 0,9 16 048 0,9 32 938 0,9\nTourka 88 0,0 75 0,0 163 0,0\nlangues étrangères 4933 0,3 3270 0,2 8203 0,2\nFrançais 34462 1,9 32078 1,8 66541 1,8\nautres langues étrangères non africaines 5672 0,3 5197 0,3 10869 0,3\nTotal 1793526 100 1814541 100 3608067 100\nSource : ANSD. RGPH-5, 2023\n\n'

KAOLACK = "II.2.2.3. Ages moyen et âge médian\nIl ressort des résultats du RGPH-5 que l’âge médian des résidents de la région de Kaolack est\nde 17 ans. Autrement dit, la moitié de la population de Kaolack a moins de 17 ans en 2023.\nCe qui confirme la jeunesse de la population de cette région. L’âge médian est plus faible chez\nles hommes (16 ans) que chez les femmes (18 ans) et quel que soit le milieu de r ésidence.\nL’âge médian noté en milieu urbain (19 ans) dépasse de trois ans celui observé en milieu rural\n(16 ans).\nPar ailleurs, l’âge moyen de la population, qui s’établit à 22 ans, est également plus élevé chez\nles femmes (23 ans) que chez les hommes (21 ans).\nTableau II-4: Age moyen et âge médian de la population selon le sexe et le milieu de résidence\nIndicateurs\nde tendance\ncentrale\nUrbain Rural Total\nMasculin Féminin Total Masculin Féminin Total Masculin Féminin Total\nMoyenne 23 25 24 20 21 21 21 23 22\nMédiane 18 20 19 15 16 16 16 18 17\nSource : ANSD. RGPH-5, 2023\n\n\x0c\nRGPH-5 :Rapport de présentation des résultats\n  Région de Kaolack\n33\nII.2.2.4. Grands groupes d’âges et Rapport de dépendance\ndémographique\nLa majorité de la population de la région a entre 15 et 64 ans, représentant 53,1% au niveau\nrégional. Ce groupe est plus présent en milieu urbain (57,7%) qu'en milieu rural (50,3%). Une\nanalyse par département montre une proportion des 15- 64 ans plus élev ée dans le\ndépartement de Kaolack (55,1%) par rapport à ceux de Nioro et de Guinguinéo, où elles\nreprésentent respectivement 50,6% et 53,0%.\nEn outre, les personnes âgées de 65 ans et plus, quel que soit le milieu de résidence ou le\ndépartement, représentent moins de 5,0% de la population. Leur proportion est plus élevée en\nmilieu urbain (3,9%) et dans le département de Guinguinéo (4,0%).\nPar conséquent, un rapport de dépendance démographique de 88 ,2% est observé dans la\nrégion. Autrement dit, il est recensé en moyenne 88 personnes âgées de 0 – 14 ans ou de 65\nans et plus pour 100 personnes âgées de 15 – 64 ans. Il traduit ainsi une dépendance\ndémographique relativement forte au sein de la population. Le rapport de dépendance\ndémographique est plus faible dans le département de Kaolack (81,6%), tandis que Nioro en\naffiche le niveau le plus élevé (97,5%).\nTableau II-5: Répartition de la population résidente par groupes d’âges selon le département et le milieu de\nrésidence (en %)\nGroupe d'âges\nKAOLACK NIORO GUINGUINEO Région\nUrba\nin\nRura\nl\nEnsem\nble\nUrbain\nRura\nl\nEnse\nmble\nUrba\nin\nRura\nl\nEnsem\nble\nUrbain Rural\nEnse\nmble\nMoins de 15\nans\n37,3 46,6 41,2 42,8 47,4 46,7 39,9 44,2 43,0 38,4 46,7 43,5\n15-64 ans 58,6 50,2 55,1 54,2 49,9 50,6 55,8 52 53 ?à 57,7 50,3 53,1\n65 ans et plus 4,1 3,2 3,7 2,9 2,7 2,7 4,3 3,8 4,0 3,9 3 3,3\nTotal 100 100 100 100 100 100 100 100 100 100 100 100\nRapport de\ndépendance\ndémographique\n    81,6     97,5     88,6     88,2\nSource : ANSD. RGPH-5, 2023\n"

KAOLACK_LANGUAGE = """Tableau II -13: Répartition (%) de la population résidente de 3 ans ou plus par principale langue
couramment parlée selon le sexe
SEXE
Masculin Féminin Total
Wolof 82,0 82,4 82,2
Pulaar 8,1 7,9 8,0
Sereer 5,6 5,7 5,6
Màndienka 2,0 1,9 2,0
autres langues africaines 1,4 1,3 1,4
Français 0,9 0,8 0,8
Total 100 100 100
Source : ANSD. RGPH-5, 2023
"""

ADMIN1 = [{'id': '71046170B16569890219484', 'name': 'Dakar', 'parent': 'SEN'}, {'id': '71046170B89912390768536', 'name': 'Diourbel', 'parent': 'SEN'}, {'id': '71046170B84527172065489', 'name': 'Fatick', 'parent': 'SEN'}, {'id': '71046170B9856693808493', 'name': 'Kaffrine', 'parent': 'SEN'}, {'id': '71046170B19471834738959', 'name': 'Kaolack', 'parent': 'SEN'}, {'id': '71046170B5066698136661', 'name': 'Kedougou', 'parent': 'SEN'}, {'id': '71046170B66864032803639', 'name': 'Kolda', 'parent': 'SEN'}, {'id': '71046170B63374102885919', 'name': 'Louga', 'parent': 'SEN'}, {'id': '71046170B85295751834134', 'name': 'Matam', 'parent': 'SEN'}, {'id': '71046170B37999982332216', 'name': 'Saint Louis', 'parent': 'SEN'}, {'id': '71046170B19178449543377', 'name': 'Sedhiou', 'parent': 'SEN'}, {'id': '71046170B85662395344337', 'name': 'Tambacounda', 'parent': 'SEN'}, {'id': '71046170B89315153043645', 'name': 'Thies', 'parent': 'SEN'}, {'id': '71046170B26251724010642', 'name': 'Ziguinchor', 'parent': 'SEN'}]

ADMIN2 = [{'id': '50182788B16013842146029', 'name': 'Bakel', 'parent': '71046170B85662395344337'}, {'id': '50182788B75300917140294', 'name': 'Bambey', 'parent': '71046170B89912390768536'}, {'id': '50182788B19391387689457', 'name': 'Bignona', 'parent': '71046170B26251724010642'}, {'id': '50182788B56779252201559', 'name': 'Birkelane', 'parent': '71046170B9856693808493'}, {'id': '50182788B68388966372963', 'name': 'Bounkiling', 'parent': '71046170B19178449543377'}, {'id': '50182788B94177495754038', 'name': 'Dagana', 'parent': '71046170B37999982332216'}, {'id': '50182788B18539004609148', 'name': 'Dakar', 'parent': '71046170B16569890219484'}, {'id': '50182788B22549322426328', 'name': 'Diourbel', 'parent': '71046170B89912390768536'}, {'id': '50182788B55839740763416', 'name': 'Fatick', 'parent': '71046170B84527172065489'}, {'id': '50182788B85341589150678', 'name': 'Foundiougne', 'parent': '71046170B84527172065489'}, {'id': '50182788B90737446104605', 'name': 'Gossas', 'parent': '71046170B84527172065489'}, {'id': '50182788B18390590381778', 'name': 'Goudiry', 'parent': '71046170B85662395344337'}, {'id': '50182788B48951494587639', 'name': 'Goudomp', 'parent': '71046170B19178449543377'}, {'id': '50182788B55211093773925', 'name': 'Guediawaye', 'parent': '71046170B16569890219484'}, {'id': '50182788B97054679922117', 'name': 'Guinguineo', 'parent': '71046170B19471834738959'}, {'id': '50182788B43046627101076', 'name': 'Kaffrine', 'parent': '71046170B9856693808493'}, {'id': '50182788B72122084264725', 'name': 'Kanel', 'parent': '71046170B85295751834134'}, {'id': '50182788B15645681951695', 'name': 'Kaolack', 'parent': '71046170B19471834738959'}, {'id': '50182788B60047071387499', 'name': 'Kebemer', 'parent': '71046170B63374102885919'}, {'id': '50182788B85082652306110', 'name': 'Kedougou', 'parent': '71046170B5066698136661'}, {'id': '50182788B77977720497228', 'name': 'Kolda', 'parent': '71046170B66864032803639'}, {'id': '50182788B60464160168835', 'name': 'Koumpentoum', 'parent': '71046170B85662395344337'}, {'id': '50182788B42114348275286', 'name': 'Koungheul', 'parent': '71046170B9856693808493'}, {'id': '50182788B14678638932037', 'name': 'Linguere', 'parent': '71046170B63374102885919'}, {'id': '50182788B22933374767599', 'name': 'Louga', 'parent': '71046170B63374102885919'}, {'id': '50182788B13883389428586', 'name': 'Malem Hodar', 'parent': '71046170B9856693808493'}, {'id': '50182788B95113260184043', 'name': 'Matam', 'parent': '71046170B85295751834134'}, {'id': '50182788B63857747785645', 'name': 'Mbacke', 'parent': '71046170B89912390768536'}, {'id': '50182788B56533800648606', 'name': 'Mbour', 'parent': '71046170B89315153043645'}, {'id': '50182788B71056203552440', 'name': 'Medina Yoroufoula', 'parent': '71046170B66864032803639'}, {'id': '50182788B29473400533502', 'name': 'Nioro Du Rip', 'parent': '71046170B19471834738959'}, {'id': '50182788B11051302290888', 'name': 'Oussouye', 'parent': '71046170B26251724010642'}, {'id': '50182788B8601261498481', 'name': 'Pikine', 'parent': '71046170B16569890219484'}, {'id': '50182788B66510054428140', 'name': 'Podor', 'parent': '71046170B37999982332216'}, {'id': '50182788B34306626760019', 'name': 'Ranerou', 'parent': '71046170B85295751834134'}, {'id': '50182788B16861669195445', 'name': 'Rufisque', 'parent': '71046170B16569890219484'}, {'id': '50182788B94115130730188', 'name': 'Saint Louis', 'parent': '71046170B37999982332216'}, {'id': '50182788B75788529380727', 'name': 'Salemata', 'parent': '71046170B5066698136661'}, {'id': '50182788B8770711358016', 'name': 'Saraya', 'parent': '71046170B5066698136661'}, {'id': '50182788B34006486463131', 'name': 'Sedhiou', 'parent': '71046170B19178449543377'}, {'id': '50182788B74600736318601', 'name': 'Tambacounda', 'parent': '71046170B85662395344337'}, {'id': '50182788B65872214095625', 'name': 'Thies', 'parent': '71046170B89315153043645'}, {'id': '50182788B62483410284412', 'name': 'Tivaoune', 'parent': '71046170B89315153043645'}, {'id': '50182788B9780593325351', 'name': 'Velingara', 'parent': '71046170B66864032803639'}, {'id': '50182788B19119296887329', 'name': 'Ziguinchor', 'parent': '71046170B26251724010642'}]


class SenegalRegionalReports(unittest.TestCase):
    def test_dakar(self):
        self.assertEqual(sr.parse_median(DAKAR), (24, "Tableau II-5"))
        language, kind, table = sr.parse_language(DAKAR)
        self.assertEqual((kind, table), ("count", "Tableau II-11"))
        self.assertEqual(language["Wolof"], 2_478_174)
        self.assertEqual(language["Sign language"], 4_061)
        self.assertEqual(language["French"], 66_541)
        self.assertLessEqual(abs(sum(language.values()) - 3_608_067), 2)
        self.assertTrue(sr.departments_in_broad_groups(DAKAR))

    def test_kaolack(self):
        self.assertEqual(sr.parse_median(KAOLACK), (17, "Tableau II-4"))
        self.assertTrue(sr.departments_in_broad_groups(KAOLACK))
        language, kind, _ = sr.parse_language(KAOLACK_LANGUAGE)
        self.assertEqual(kind, "pct")
        self.assertEqual(language["Mandinka"], 2.0)

    def test_wrapped_label(self):
        # Tambacounda's table as the runner printed it, cut after three rows,
        # with a total row made from them.
        table = """Tableau II-13 : Répartition (%) de la population résidente de 3 ans ou plus par principale langue couramment parlée selon
le sexe
Principale langue
couramment parlée
SEXE
Masculin Féminin Ensemble
Effectif % Effectif % Effectif %
Langage des signes
(Sourd-Muet)
2813 0,7 2894 0,7 5707 0,7
wolof 60226 13,9 56873 13,3 117099 13,6
pulaar 254514 58,9 250391 58,5 504905 58,7
Ensemble 317553 100 310158 100 627711 100
Source : ANSD. RGPH-5, 2023
"""
        language, kind, number = sr.parse_language(table)
        self.assertEqual((kind, number), ("count", "Tableau II-13"))
        self.assertEqual(language, {"Sign language": 5707.0, "Wolof": 117099.0,
                                    "Pulaar": 504905.0})

    def test_build(self):
        reports = [sr.parsed("Dakar", DAKAR, "u1"),
                   sr.parsed("Kaolack", KAOLACK + "\f" + KAOLACK_LANGUAGE, "u2")]
        records, report = sr.build(reports, ADMIN1, ADMIN2)
        by = {(r["level"], r["name"]): r for r in records}
        dakar = by[("admin1", "Dakar")]
        self.assertEqual(dakar["median_age"]["value"], 24)
        self.assertEqual(dakar["language"][0]["group"], "Wolof")
        self.assertEqual(dakar["language"][0]["pct"], 68.7)
        kaolack = by[("admin1", "Kaolack")]
        self.assertNotIn("count", kaolack["language"][0])
        depts = [r for r in records if r["level"] == "admin2"]
        # Dakar: the four departments drawn (Keur Massar, made in 2021, is not).
        self.assertEqual(len(depts), 4 + 3)
        self.assertIn("three broad age groups", depts[0]["median_age"]["note"])
        self.assertEqual(len(report), 12)


if __name__ == "__main__":
    unittest.main()
