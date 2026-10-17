"""Togo's 2022 census leaflet as the runner printed it."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import togo_census as tc  # noqa: E402

LEAFLET = 'Population des préfectures par sexe Population des villes du Togo\nSexe\nRégion / Préfecture Ensemble\nMasculin Féminin REPUBLIQUE TOGOLAISE\nGrand Lomé 1 060 504 1 127 872 2 188 376\nMinistère de la Planification du\nGolfe 631 567 674 114 1 305 681\nDéveloppement et de la Coopération\nAgoè-Nyivé 428 937 453 758 882 695\nMaritime sans Grand\n642 876 703 739 1 346 615\nLomé\nZio 242 367 257 665 500 032\nYoto 82 859 91 992 174 851\nBas-Mono 44 366 50 494 94 860\n5ème RECENSEMENT GENERAL DE LA POPULATION ET DE L’HABITAT\nLacs 115 468 125 779 241 247\nVo 104 485 119 926 224 411 (RGPH-5)\nAvé 53 331 57 883 111 214\nPlateaux 806 154 829 792 1 635 946\nOgou 124 073 129 394 253 467\nMoyen-Mono 41 413 49 092 90 505\nHaho 148 029 157 067 305 096\nRésultats définitifs\nAgou 42 449 43 344 85 793\nKloto 71 161 74 825 145 986\ndu RGPH-5 de\nKpélé 40 129 40 810 80 939\nDanyi 20 512 19 728 40 240 Novembre 2022\nWawa 51 383 49 917 101 300\nAkébou 37 236 36 594 73 830\nAmou 56 543 57 629 114 172\nNous sommes\nAnié 89 897 90 261 180 158\nEst-Mono 83 329 81 131 164 460 8 095 498\nCentrale 397 336 398 193 795 529\nTchaoudjo 119 126 121 234 240 360\nhabitants au Togo\nTchamba 100 980 99 605 200 585\nBlitta 81 602 81 670 163 272\nSotouboua 69 140 69 724 138 864\nMô 26 488 25 960 52 448\nKara 488 225 497 287 985 512\nKozah 141 188 142 550 283 738\nAssoli 33 246 33 148 66 394\nBassar 76 235 75 830 152 065\nDankpen 91 567 94 095 185 662\nKéran 63 731 64 956 128 687\nDoufelgou 40 973 43 794 84 767\nBinah 41 285 42 914 84 199\nInstitut National de la Statistique et des Etudes\nSavanes 549 415 594 105 1 143 520\nEconomiques et Démographiques (INSEED)\nTône 185 480 203 295 388 775\nCinkassé 62 574 66 385 128 959\n59 rue de la Kozah, Immeuble INSEED/CENETI,\nKpendjal-Ouest 58 175 65 155 123 330\nBP 118 Lomé Togo\nKpendjal 43 035 45 330 88 365\nOti-Sud 73 332 77 044 150 376 Tél. : (228) 22 21 62 24 / (228) 22 21 27 75\nOti 60 638 64 210 124 848\nEmail : inseed@inseed.tg\nTandjoaré 66 181 72 686 138 867\nSite web : www.inseed.tg\nTogo 3 944 510 4 150 988 8 095 498\n[433 words in 65 rows]\n\n\n(Hbts/Km2)\nPopulation par sexe Population par région et par sexe Densité de population\nSexe\n8 095 498 habitants Région Ensemble\nMasculin Féminin\nGrand Lomé 1 060 504 1 127 872 2 188 376\nDensité au niveau national :\nMaritime sans\n143 hbts/km2\n642 876 703 739 1 346 615\nGrand Lomé\nPlateaux 806 154 829 792 1 635 946\nCentrale 397 336 398 193 795 529\n3 944 510 hommes 4 150 988 femmes\nKara 488 225 497 287 985 512\n(48,7 %) (51,3 %)\nSavanes 549 415 594 105 1 143 520\nTogo 3 944 510 4 150 988 8 095 498\nTaux d’urbanisation par région\nPopulation par milieu de résidence\nUrbain Rural\n3473792 4621706\n43% 57%\nEvolution de la population de 1960 à 2022\nPopulation par milieu de résidence et sexe\nSexe\nMilieu de\nEnsemble\nrésidence\nMasculin Féminin\nUrbain 1 689 674 1 784 118 3 473 792\nRural 2 254 836 2 366 870 4 621 706\nTogo 3 944 510 4 150 988 8 095 498\nEntre 2010 et 2022, la population togolaise s’est accrue en moyenne de 2,3% par année. A ce rythme, elle doublera dans 31 ans\n[193 words in 34 rows]\n'

ADMIN1 = [{'id': '44829518B22237151485853', 'name': 'Centrale Region', 'parent': 'TGO'}, {'id': '44829518B37847489557890', 'name': 'Kara Region', 'parent': 'TGO'}, {'id': '44829518B32493797453601', 'name': 'Maritime Region', 'parent': 'TGO'}, {'id': '44829518B26250432968900', 'name': 'Plateaux Region', 'parent': 'TGO'}, {'id': '44829518B73084759902551', 'name': 'Savanes Region', 'parent': 'TGO'}]

ADMIN2 = [{'id': '56601680B98633254865748', 'name': 'Agou', 'parent': '44829518B26250432968900'}, {'id': '56601680B49010054481747', 'name': 'Akébou', 'parent': '44829518B26250432968900'}, {'id': '56601680B97066679611380', 'name': 'Amou', 'parent': '44829518B26250432968900'}, {'id': '56601680B95177776630805', 'name': 'Anié', 'parent': '44829518B26250432968900'}, {'id': '56601680B59731994726086', 'name': 'Assoli', 'parent': '44829518B37847489557890'}, {'id': '56601680B41562196478781', 'name': 'Ave', 'parent': '44829518B32493797453601'}, {'id': '56601680B95494992900514', 'name': 'Bas-Mono', 'parent': '44829518B32493797453601'}, {'id': '56601680B12598387573686', 'name': 'Bassar', 'parent': '44829518B37847489557890'}, {'id': '56601680B44914344892125', 'name': 'Binah', 'parent': '44829518B37847489557890'}, {'id': '56601680B83789166363061', 'name': 'Blitta', 'parent': '44829518B22237151485853'}, {'id': '56601680B64387003159978', 'name': 'Cinkassé', 'parent': '44829518B73084759902551'}, {'id': '56601680B12249670822801', 'name': 'Dankpen', 'parent': '44829518B37847489557890'}, {'id': '56601680B28886338508193', 'name': 'Danyi', 'parent': '44829518B26250432968900'}, {'id': '56601680B89390870579143', 'name': 'Doufelgou', 'parent': '44829518B37847489557890'}, {'id': '56601680B43372711183576', 'name': 'Est-Mono', 'parent': '44829518B26250432968900'}, {'id': '56601680B59402294179516', 'name': 'Golfe', 'parent': '44829518B32493797453601'}, {'id': '56601680B64184766281932', 'name': 'Haho', 'parent': '44829518B26250432968900'}, {'id': '56601680B30245465113687', 'name': 'Keran', 'parent': '44829518B37847489557890'}, {'id': '56601680B4042875560778', 'name': 'Kloto', 'parent': '44829518B26250432968900'}, {'id': '56601680B44378348729827', 'name': 'Kozah', 'parent': '44829518B37847489557890'}, {'id': '56601680B9516770320708', 'name': 'Kpendjal', 'parent': '44829518B73084759902551'}, {'id': '56601680B91306020007274', 'name': 'Kpélé', 'parent': '44829518B26250432968900'}, {'id': '56601680B61332506890313', 'name': 'Lacs', 'parent': '44829518B32493797453601'}, {'id': '56601680B89691125732498', 'name': 'Lome Commune', 'parent': '44829518B32493797453601'}, {'id': '56601680B67578860005589', 'name': 'Moyen-Mono', 'parent': '44829518B26250432968900'}, {'id': '56601680B48471181858151', 'name': 'Ogou', 'parent': '44829518B26250432968900'}, {'id': '56601680B17683608517106', 'name': 'Oti', 'parent': '44829518B73084759902551'}, {'id': '56601680B47682688566924', 'name': 'Plaine de Mô', 'parent': '44829518B22237151485853'}, {'id': '56601680B24632394959352', 'name': 'Sotouboua', 'parent': '44829518B22237151485853'}, {'id': '56601680B89112535430785', 'name': 'Tandjouare', 'parent': '44829518B73084759902551'}, {'id': '56601680B17532793096074', 'name': 'Tchamba', 'parent': '44829518B22237151485853'}, {'id': '56601680B14222633765071', 'name': 'Tchaoudjo', 'parent': '44829518B22237151485853'}, {'id': '56601680B4810153335262', 'name': 'Tone', 'parent': '44829518B73084759902551'}, {'id': '56601680B43007755983133', 'name': 'Vo', 'parent': '44829518B32493797453601'}, {'id': '56601680B48376088277440', 'name': 'Wawa', 'parent': '44829518B26250432968900'}, {'id': '56601680B13855645397073', 'name': 'Yoto', 'parent': '44829518B32493797453601'}, {'id': '56601680B44610096966608', 'name': 'Zio', 'parent': '44829518B32493797453601'}]


class TogoLeaflet(unittest.TestCase):
    def test_table(self):
        table = tc.parse(LEAFLET)
        self.assertEqual(table["Golfe"], (631_567, 674_114, 1_305_681))
        # The line carries the leaflet's headline figure after its own three.
        self.assertEqual(table["Est-Mono"], (83_329, 81_131, 164_460))
        self.assertEqual(table["Danyi"], (20_512, 19_728, 40_240))
        self.assertEqual(table["Togo"], tc.NATIONAL)
        regions = tc.check(table)
        self.assertEqual(regions["Maritime sans Grand Lomé"], (642_876, 703_739, 1_346_615))
        self.assertEqual(regions["Plateaux"], (806_154, 829_792, 1_635_946))

    def test_build(self):
        records, report = tc.build(LEAFLET, ADMIN1, ADMIN2)
        by = {(r["level"], r["name"]): r for r in records}
        self.assertEqual(sum(1 for r in records if r["level"] == "admin1"), 5)
        self.assertEqual(sum(1 for r in records if r["level"] == "admin2"), 35)
        maritime = by[("admin1", "Maritime Region")]
        self.assertEqual(maritime["population"]["value"], 2_188_376 + 1_346_615)
        self.assertIn("Grand Lomé (2,188,376) included", maritime["population_note"])
        kpendjal = by[("admin2", "Kpendjal")]
        self.assertEqual(kpendjal["population"]["value"], 88_365 + 123_330)
        self.assertEqual(kpendjal["sex_ratio"]["value"],
                         round(1000 * (43_035 + 58_175) / (45_330 + 65_155)))
        self.assertEqual(by[("admin2", "Plaine de Mô")]["population"]["value"], 52_448)
        self.assertEqual(by[("admin2", "Tandjouare")]["population"]["value"], 138_867)
        self.assertNotIn(("admin2", "Golfe"), by)
        self.assertNotIn(("admin2", "Lome Commune"), by)
        self.assertEqual(len(report), 2)
        for r in records:
            self.assertEqual(r["match_by"], "shape_id")


if __name__ == "__main__":
    unittest.main()
