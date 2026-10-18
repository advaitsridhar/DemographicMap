"""Côte d'Ivoire's 2021 census regional page (Gbêkê) as the runner printed it."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import cote_divoire_census as cc  # noqa: E402

GBEKE = "Région GBEKE - RGPH Accueil Publications Data visualisation Cartographie des indicateurs Groupe d’âge national Archives RGP 1975 RGPH 1988 RGPH 1998 Contacts Accueil Publications Data visualisation Cartographie des indicateurs Groupe d’âge national Archives RGP 1975 RGPH 1988 RGPH 1998 Contacts RGPH Accueil Publications Data visualisation Cartographie des indicateurs Groupe d’âge national Archives RGP 1975 RGPH 1988 RGPH 1998 Contacts Gbêkê Région du Gbêkê - Monographies Presentation La région de Gbêkê est l’une des trente-et-une régions de Côte d’Ivoire . Sa capitale est Bouaké. CHEF LIEU DE DEPARTEMENT : BEOUMI, BOTRO, SAKASSOU CHEF LIEU DE REGION : BOUAKE POPULATION : 1 352 900 Gbeke - Tableau Synoptique de la région Indicateurs National 2021 Gbêkê 2021 Gbêkê 1998 Population totale 29 389 150 1352900 811 274 Population masculine 15 344 990 699816 395 737 Population féminine 14 044 160 653084 415 537 Rapport de masculinité 109,3 107,2 95,2 Taux d'Accroissement Moyen Annuel (%) 2,9 2,2 - Densité moyenne (habitants/km²) 91,1 150,8 90,9 Poids (%) de la région dans la population nationale - 4,6 5,3 Femmes en âge de procréer (15-49 ans) 7 407 671 325986 193 413 Enfants âgés de moins de 5 ans (0-4 ans) 3 696 301 167511 106 377 Enfants âgés de moins de 15 ans (0-14 ans) 11 225 273 512645 348 586 Population âgée de 0-17 ans 13 174 947 605175 406 607 Age moyen de la population 23 26 - Population âgée de 6-14 ans 6 670 555 307388 218 333 Population âgée de 15-64 ans 17 385 410 783611 428 782 Population âgée de 15-59 ans 16 910 080 757378 412 950 Population âgée de 60 ans et plus 1 229 791 82878 49 684 Population âgée de 65 ans et plus 754 461 56645 33 852 Rapport de dépendance démographique démographique (%) 69 72,6 89,2 Population scolarisable au primaire (6-11 ans) 4 570 055 207862 150 068 Population de scolarité obligatoire (6-16 ans) 8 043 085 372114 258 453 Population scolarisable au secondaire (12-17 ans) 4 050 175 192056 126 286 Population non déclarée à l’Etat-civil 1 781 386 45 862 - Enfant de moins de 5 ans dont la naissance a été déclarée à l‘état civil (%) 84,5 89,4 - Taux de chômage (%) 3,3 2,6 - Taux de chômage chez les jeunes (%) 4,9 3,3 - Taux de chômage au regard du handicap (%) 1,7 2,1 - % des jeunes de 15-24 ans ni dans le système éducatif, ni dans l’emploi 28,6 25,1 - Population rurale 13 677 716 512 065 296 134 Population urbaine 15 711 434 834 431 515 140 Taux d’urbanisation (%) 53,5 62 63,5 Ménage ayant un accès à l’électricité (CIE) (%) 73,5 80,6 50,7 Ménage ayant accès à des installations sanitaires améliorées (%) (%) 56,5 56,6 59,6 Ménage déféquant à l’air libre (%) 14,9 16,3 33,3 Ménage possédant un téléphone cellulaire (%) 77,3 80,8 - Ménage propriétaire de leur logement (%) 51,8 48,6 49,2 Indice synthétique de fécondité 4,4 4,8 - Espérance de vie à la naissance 61,2 61,7 - Quotient de mortalité infantile (‰) 58,5 40,7 - Age moyen au mariage 30,9 28,9 - Proportion de mariage polygamique (%) 10,2 6,7 - MONOGRAPHIE GBEKE Le document est une monographie complète de la région du GBEKE , issue du dernier Recensement Général de la Population et de l’Habitat (RGPH) 2021. Il dresse un état des lieux exhaustif de la situation démographique, sociale et économique de la région. Démographie Population totale : La région compte 1 352 900 habitants soit 4,60% de la population Ivoirienne. Équilibre des sexes : La proportion des personnes de sexe masculin vivant dans les ménages ordinaires est de 51,6% et est supérieure à celle des femmes qui est de 48,4%. Nationalité : La population est composée à 91,1% d’Ivoiriens et 8,9% non ivoiriens. Urbanisation et Habitat Taux d’urbanisation : La région affiche un taux d’urbanisation de 62% . Précarité résidentielle : L’indice de précarité résidentielle est faible au niveau de la région, s’établissant à 0,2% . Il est légèrement plus marqué à Sakassou (1,5%). Nous vous en souhaitons une bonne utilisation. 2023 RGPH - All Rights Reserved"

ADMIN1 = [{'id': '83157122B96959932745266', 'name': 'Bas-Sassandra', 'parent': 'CIV'}, {'id': '83157122B96325295181308', 'name': 'Comoe', 'parent': 'CIV'}, {'id': '83157122B12160353323799', 'name': 'Denguele', 'parent': 'CIV'}, {'id': '83157122B76853064397847', 'name': "District Autonome D'Abidjan", 'parent': 'CIV'}, {'id': '83157122B30232425959699', 'name': 'District Autonome De Yamoussoukro', 'parent': 'CIV'}, {'id': '83157122B34711482467037', 'name': 'Goh-Djiboua', 'parent': 'CIV'}, {'id': '83157122B20352934117266', 'name': 'Lacs', 'parent': 'CIV'}, {'id': '83157122B73612976130091', 'name': 'Lagunes', 'parent': 'CIV'}, {'id': '83157122B69310198422077', 'name': 'Montagnes', 'parent': 'CIV'}, {'id': '83157122B74959515955757', 'name': 'Sassandra-Marahoue', 'parent': 'CIV'}, {'id': '83157122B28791092437733', 'name': 'Savanes', 'parent': 'CIV'}, {'id': '83157122B62906982633778', 'name': 'Valle Du Bandama', 'parent': 'CIV'}, {'id': '83157122B58892240487392', 'name': 'Woroba', 'parent': 'CIV'}, {'id': '83157122B79983119233374', 'name': 'Zanzan', 'parent': 'CIV'}]

ADMIN2 = [{'id': '98640826B52449815511854', 'name': 'Agneby-Tiassa', 'parent': '83157122B73612976130091'}, {'id': '98640826B37750272367318', 'name': 'Bafing', 'parent': '83157122B58892240487392'}, {'id': '98640826B26044148659027', 'name': 'Bagoue', 'parent': '83157122B28791092437733'}, {'id': '98640826B5123145245776', 'name': 'Belier', 'parent': '83157122B20352934117266'}, {'id': '98640826B43857880322183', 'name': 'Bere', 'parent': '83157122B58892240487392'}, {'id': '98640826B90856530326373', 'name': 'Bounkani', 'parent': '83157122B79983119233374'}, {'id': '98640826B42717034718743', 'name': 'Cavally', 'parent': '83157122B69310198422077'}, {'id': '98640826B76853064397847', 'name': "District Autonome D'Abidjan", 'parent': '83157122B76853064397847'}, {'id': '98640826B30232425959699', 'name': 'District Autonome De Yamoussoukro', 'parent': '83157122B30232425959699'}, {'id': '98640826B69523806833990', 'name': 'Folon', 'parent': '83157122B12160353323799'}, {'id': '98640826B94469137469464', 'name': 'Gbeke', 'parent': '83157122B62906982633778'}, {'id': '98640826B37905317988050', 'name': 'Gbokle', 'parent': '83157122B96959932745266'}, {'id': '98640826B83650084589555', 'name': 'Goh', 'parent': '83157122B34711482467037'}, {'id': '98640826B5040161076408', 'name': 'Gontougo', 'parent': '83157122B79983119233374'}, {'id': '98640826B83353125268201', 'name': 'Grands Ponts', 'parent': '83157122B73612976130091'}, {'id': '98640826B22329502030217', 'name': 'Guemon', 'parent': '83157122B69310198422077'}, {'id': '98640826B80955316471767', 'name': 'Hambol', 'parent': '83157122B62906982633778'}, {'id': '98640826B13622385448205', 'name': 'Haut-Sassandra', 'parent': '83157122B74959515955757'}, {'id': '98640826B12556457947993', 'name': 'Iffou', 'parent': '83157122B20352934117266'}, {'id': '98640826B87987908031267', 'name': 'Indenie-Djuablin', 'parent': '83157122B96325295181308'}, {'id': '98640826B2974603948771', 'name': 'Kabadougou', 'parent': '83157122B12160353323799'}, {'id': '98640826B50838995581112', 'name': 'Loh-Djiboua', 'parent': '83157122B34711482467037'}, {'id': '98640826B99867209198649', 'name': 'Marahoue', 'parent': '83157122B74959515955757'}, {'id': '98640826B88194950838049', 'name': 'Me', 'parent': '83157122B73612976130091'}, {'id': '98640826B53162767921513', 'name': 'Moronou', 'parent': '83157122B20352934117266'}, {'id': '98640826B73875625736421', 'name': "N'Zi", 'parent': '83157122B20352934117266'}, {'id': '98640826B56207519899242', 'name': 'Nawa', 'parent': '83157122B96959932745266'}, {'id': '98640826B2900878653745', 'name': 'Poro', 'parent': '83157122B28791092437733'}, {'id': '98640826B43081365176028', 'name': 'San Pedro', 'parent': '83157122B96959932745266'}, {'id': '98640826B87421109468433', 'name': 'Sud-Comoe', 'parent': '83157122B96325295181308'}, {'id': '98640826B18937667882346', 'name': 'Tchologo', 'parent': '83157122B28791092437733'}, {'id': '98640826B98350089255378', 'name': 'Tonkpi', 'parent': '83157122B69310198422077'}, {'id': '98640826B81277132888560', 'name': 'Worodougou', 'parent': '83157122B58892240487392'}]


class CoteDivoire(unittest.TestCase):
    def test_page(self):
        f = cc.page_facts(GBEKE)
        self.assertEqual((f["men"], f["women"], f["total"]), (699_816, 653_084, 1_352_900))
        self.assertEqual(f["seat"], "Bouaké")
        self.assertEqual(f["mean"], "26")
        self.assertEqual(f["ivorian"], (91.1, 8.9))

    def test_grouped_digits(self):
        text = GBEKE.replace("1352900", "1 352 900").replace("699816", "699 816").replace(
            "653084", "653 084")
        f = cc.page_facts(text)
        self.assertEqual((f["men"], f["women"], f["total"]), (699_816, 653_084, 1_352_900))

    def test_seat_before_departments(self):
        # Constructed from Gbêkê's page: a heading that names the region's seat
        # before its departments' seats, as Gbôklé's does, and no sentence.
        text = GBEKE.replace("Sa capitale est Bouaké.", "").replace(
            "CHEF LIEU DE DEPARTEMENT : BEOUMI, BOTRO, SAKASSOU CHEF LIEU DE REGION : BOUAKE",
            "CHEF LIEU DE REGION : BOUAKE CHEF LIEU DE DEPARTEMENT : BEOUMI, BOTRO, SAKASSOU")
        self.assertEqual(cc.page_facts(text)["seat"], "Bouake")

    def test_shares_worded_otherwise(self):
        # Constructed sentences in the wordings the regional pages use.
        for sentence, want in [
            ("Nationalité : La population est composée de 76,5 % d’Ivoiriens et de 23,5 % "
             "de non-Ivoiriens. Urbanisation", (76.5, 23.5)),
            ("Nationalité : 59,9% d'Ivoiriens contre 40,1% de non Ivoiriens.", (59.9, 40.1)),
            ("Nationalité : La population est composée à 92% d’Ivoiriens et 8% non "
             "ivoiriens.", (92.0, 8.0)),
            ("Nationalité : La population compte 12,0% de non-ivoiriens et 88,0% "
             "d'ivoiriens.", (88.0, 12.0)),
            ("Nationalité : 59,9% d'Ivoiriens et 41,1% de non Ivoiriens.", None),
        ]:
            self.assertEqual(cc.shares("x " + sentence), want, sentence)

    def test_build(self):
        f = cc.page_facts(GBEKE)
        hambol = dict(f, men=300_000, women=290_000, total=590_000, seat="Katiola")
        facts = {"region-gbeke-mono": f, "region-hambol-mono": hambol}
        records, report = cc.build(facts, ADMIN1, ADMIN2)
        by = {(r["level"], r["name"]): r for r in records}
        gbeke = by[("admin2", "Gbeke")]
        self.assertEqual(gbeke["population"]["value"], 1_352_900)
        self.assertEqual(gbeke["sex_ratio"]["value"], round(1000 * 699_816 / 653_084))
        self.assertEqual(gbeke["capital"], "Bouaké")
        self.assertEqual(gbeke["ethnicity_basis"], "nationality")
        self.assertIn("mean age (26 years)", gbeke["median_age"]["note"])
        district = by[("admin1", "Valle Du Bandama")]
        self.assertEqual(district["population"]["value"], 1_352_900 + 590_000)
        # The table's seat for the district, Bouaké, is also Gbêkê's on its page.
        self.assertEqual(district["capital"], "Bouaké")
        self.assertIn("also the seat of the Gbeke region", district["capital_note"])
        self.assertIn("Décret n° 2011-263", district["capital_note"])
        self.assertEqual([s["field"] for s in district["sources"]],
                         ["population/sex_ratio", "capital"])
        self.assertTrue(district["sources"][1]["url"].endswith("/Districts_of_Ivory_Coast"))
        self.assertEqual(len(report), 31 + 13)  # 31 regions unread; 13 districts not whole
        # A seat that is none of the district's regions' seats is not written.
        facts["region-gbeke-mono"] = dict(f, seat="Sakassou")
        records, report = cc.build(facts, ADMIN1, ADMIN2)
        district = {(r["level"], r["name"]): r for r in records}[("admin1", "Valle Du Bandama")]
        self.assertIn("Gbeke (seat Sakassou) and Hambol (seat Katiola)",
                      district["capital"]["note"])
        self.assertEqual([s["field"] for s in district["sources"]], ["population/sex_ratio"])
        self.assertEqual(len(report), 31 + 13 + 1)

    def test_lagunes_and_an_autonomous_district(self):
        # Lagunes: Dabou, the seat of Grands Ponts; Abidjan: the city its page names.
        f = cc.page_facts(GBEKE)
        facts = {"region-agneby-tiassa-mono": dict(f, seat="Agboville"),
                 "region-grands-ponts-mono": dict(f, seat="DABOU".title()),
                 "region-la-me-mono": dict(f, seat="Adzopé"),
                 "district-autonome-abidjan-mono": dict(f, seat="Abidjan")}
        records, _ = cc.build(facts, ADMIN1, ADMIN2)
        by = {(r["level"], r["name"]): r for r in records}
        lagunes = by[("admin1", "Lagunes")]
        self.assertEqual(lagunes["capital"], "Dabou")
        self.assertIn("seat of the Grands Ponts region", lagunes["capital_note"])
        abidjan = by[("admin1", "District Autonome D'Abidjan")]
        self.assertEqual(abidjan["capital"], "Abidjan")
        self.assertNotIn("capital_note", abidjan)
        self.assertEqual([s["field"] for s in abidjan["sources"]],
                         ["population/sex_ratio/capital"])


# Run 3's log: excerpts of the regional pages where they were not yet read.
MORONOU = "Tableau Synoptique de la région Indicateurs National 2021 Moronou 2021 Moronou 1998 Population totale 29 276 660,00 439755 247 635 Population masculine 15 266 032 237458 122 464 Population féminine 14 010 628 202297 125 171 Rapport de masculinité 109,0 117,4 97,80 Taux d'accroissance moyen annuelle (%) 2,90 3,90 - Densité moyenne (habitants/km²) 91,00 79,9 45,00 Poids (%) de la région dans la population nationale - 1,50 1,6 Femmes en âge de procréer (15-49 ans) 7 385 550 103699 55 195,00 Enfants âgés de moins de 5 ans (0-4 ans) 3 692 273 47 723 36 709 Enfants âgés de moins de 15 ans (0-14 ans) 11 206 299 152 972 114 911 Population âgée de 0-17 ans 13 174 947 182 020 130 541,00 Age moyen de l"

NZI = "Tableau Synoptique de la région Indicateurs National 2021 N’Zi 2021 N’Zi 1998 Population totale 29 389 150,00 254623 165 197 Population masculine 15 344 990 129386 79 832 Population féminine 14 044 160 125237 85 365 Rapport de masculinité 109,30 103,3 93,50 Taux d'accroissance annuelle moyen (%) 2,90 1,9 - Densité moyenne (habitants/km²) 91,10 52,9 34,60 Poids (%) de la région dans la population nationale - 0,9 1,10 Femmes en âge de procréer (15-49 ans) 7 407 671 54 491 34 885 Enfants âgés de moins de 5 ans (0-4 ans) 3 696 301 32 373 24 372 Enfants âgés de moins de 15 ans (0-14 ans) 11 225 273 101 275 77 151 Population âgée de 0-17 ans 13 174 947 117 290 87 531 Age moyen de la population 23 "

GUEMON = 'Tableau Synoptique de la région Indicateurs National 2021 Guémon 2021 Guémon 1998 Population totale 29 389150 930 873 440 646 Population masculine 15 344 990 503 870 230 135 Population féminine 14 044 160 427 003 210 511 Rapport de masculinité 109 118 109 Taux d’Accroissement Moyen Annuel 2,9 3,3 - Densité moyenne (habitants/km²) 91,1 125,0 59,4 Poids (%) de la région dans la population nationale 3,2 2,9 - Femmes en âge de procréer (15-49 ans) 7 407 671 218 077 101 646 Enfants âgés de moins de 5 ans (0-4 ans) 3 696 301 122 903 74 429 Enfants âgés de moins de 15 ans (0-14 ans) 11 225 273 381 378 190 778 Population âgée de 0-17ans 13 174 947 445 468 215 373 Age moyen de la population 23 23 - P'

HAMBOL = "Tableau Synoptique de la région Indicateurs Côte d’Ivoire 2021 Hambol 2021 Hambol 1998 Population totale 29389150 61 2029 269 235 Population masculine 15 344 990 321 767 135 318 Population féminine 14 044 160 290 262 133 917 Rapport de masculinité 109,3 109,6 101 Taux d'accroissance annuelle moyen (%) 2,9 3,6 - Densité moyenne (habitants/km²) 91,1 31,4 13,8 Poids (%) de la région dans la population nationale - 2,1 1,8 Femmes en âge de procréer (15-49 ans) 7 407 671 14 4613 58 708 Enfants âgés de moins de 5 ans (0-4 ans) 3 696 301 79 342 43 219 Enfants âgés de moins de 15 ans (0-14 ans) 11 225 273 244 889 122 949 Population âgée de 0-17 ans 13 174 947 286 403 139 275 Age moyen de la populatio"

ABIDJAN_HEAD = "inclinée rattachée à une immense croix. CHEF LIEU : ABIDJAN POPULATION : 6 321 017 District d'Abidjan - Tableau Synoptique de la région Indicateurs National 2021 DAA 2021 DAA 1998 Population totale 29 389 150 6 321 017 3 125 890 Population masculine 15 344 990 3 210 983 1 578 462 Population féminine"

YAMOUSSOUKRO_HEAD = 'vitraux et son dôme dominant l’édifice. CHEF LIEU REGION : YAMOUSSOUKRO CHEF LIEU DE DEPARTEMENT : ATTIEGOUAKRO POPULATION : 422 072 Yamoussoukro- Tableau Synoptique de la région Indicateurs National 2021 Yakro 2021 Yakro 1998 Population totale 29 389 150 422072 248 032 Population masculine 15 344 9'

SUD_COMOE_HEAD = 'a , Tiapoum et Maféré. DISTRICT : COMOE CHEF LIEU DE DEPARTEMENT : GRAND-BASSAM, ADIAKE, TIAPOUM CHEF LIEU DE REGION : ABOISSO Sud Comoe - Tableau Synoptique de la région Indicateurs National 2021 Sud-Comoé 2021 Sud-Comoé 1998 Population totale 29389150 784893 459487 Population masculine 15 344 990'

BELIER_HEAD = 'ar la réforme territoriale de 2011. Son chef-lieu est Toumodi . CHEF LIEU DE DEPARTEMENT : TIEBISSOU, DIDIEVI, DJEKANOU CHEF LIEU DE REGION : TOUMODI SUPERFICIE : 6 809 km² POPULATION : 415 593 Bélier - Tableau Synoptique de la région Indicateurs National 2021 BELIER 2021 BELIER 1998 Population tota'

AGNEBY_HEAD = 're située dans le district des Lagunes. Sa capitale est Agboville . CHEF LIEU DE DEPARTEMENT : TAABO, TIASSALE, SIKENSI CHEF LIEU DE REGION : AGBOVILLE SUPERFICIE : 8 110 km² POPULATION : 865 951 Agneby Tiassa - Tableau Synoptique de la région Indicateurs National 2021 Agneby-Tiassa 2021 Agneby-Tias'

GOH_AGES = 'de 0-17 ans 13 174 947 474 792 270 805 Age moyen de la population (ans) 23 23 - Population âgée de 6-14 ans 6 670 555 244 823 133 363 Population âgée de 15-64 ans 17 385 410 554 597 289 717 Population âgée de 15-59 ans 16 910 080 537 616 279 749 Population âgée de 60 ans et plus 1 229 791 43820 26 7'


class CoteDivoireRun3(unittest.TestCase):
    def test_national_figure_misprinted(self):
        # "29 276 660,00", "29 389 150,00" and "29 389150" for the country.
        for text, want in [(MORONOU, (237_458, 202_297, 439_755)),
                           (NZI, (129_386, 125_237, 254_623)),
                           (GUEMON, (503_870, 427_003, 930_873))]:
            f = cc.synoptic(text)
            self.assertEqual((f["men"], f["women"], f["total"]), want)

    def test_region_figure_with_its_space_misplaced(self):
        f = cc.synoptic(HAMBOL)
        self.assertEqual((f["men"], f["women"], f["total"]), (321_767, 290_262, 612_029))

    def test_seat_headings(self):
        def seat(head):
            head = head.split("Tableau Synoptique")[0]   # the page's own table follows
            return cc.page_facts(GBEKE.replace(
                "Sa capitale est Bouaké. CHEF LIEU DE DEPARTEMENT : BEOUMI, BOTRO, SAKASSOU "
                "CHEF LIEU DE REGION : BOUAKE POPULATION : 1 352 900", head))["seat"]
        self.assertEqual(seat(ABIDJAN_HEAD), "Abidjan")
        self.assertEqual(seat(YAMOUSSOUKRO_HEAD), "Yamoussoukro")
        self.assertEqual(seat(SUD_COMOE_HEAD), "Aboisso")
        self.assertEqual(seat(BELIER_HEAD), "Toumodi")
        self.assertEqual(seat(AGNEBY_HEAD), "Agboville")

    def test_mean_age_in_years(self):
        text = GBEKE.replace("Age moyen de la population 23 26 -",
                             GOH_AGES[GOH_AGES.index("Age moyen"):][:45])
        self.assertEqual(cc.page_facts(text)["mean"], "23")


class PageMemory(unittest.TestCase):
    """A page the archive refuses keeps the figures an earlier run read from it."""

    def test_a_reading_comes_back_as_it_was_read(self):
        memory = {}
        f = cc.page_facts(GBEKE)
        cc.remember(memory, "region-gbeke-mono", f, "https://example.org/gbeke", "2026-10-17")
        self.assertEqual(memory["region-gbeke-mono"]["read"], "2026-10-17")
        back = cc.recalled(json_roundtrip(memory), "region-gbeke-mono")
        self.assertEqual(back, {k: f[k] for k in ("men", "women", "total", "mean", "seat",
                                                  "ivorian")})

    def test_a_reading_whose_sexes_do_not_make_its_total_is_not_used(self):
        memory = {"region-x-mono": {"men": 300_000, "women": 290_000, "total": 600_000,
                                    "mean": "22", "seat": None, "ivorian": None}}
        self.assertIsNone(cc.recalled(memory, "region-x-mono"))
        self.assertIsNone(cc.recalled(memory, "region-y-mono"))
        self.assertIsNone(cc.recalled({"region-x-mono": "garbled"}, "region-x-mono"))


def json_roundtrip(value):
    import json
    return json.loads(json.dumps(value))


if __name__ == "__main__":
    unittest.main()
