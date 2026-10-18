"""Guinea-Bissau's 2009 thematic reports as the runner printed their pages."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import guinea_bissau_census as gb  # noqa: E402

QUADRO_9B = 'entre 16,3 e 20,2 anos. N as regiões de  Quinara, Bafa tá e Gabú, metade da\npopulação possui menos de 17  anos, valores inferiores ao  nível nacional (18,2\nanos). O SAB é o sector que apresenta o maoir valor ( 20,2 anos).\nQuadro 9 B\nIdade mediana da população por  região\nRegião Tombali Quínara Oio Biombo B/Bijagós Bafará Gabu Cacheu SAB\nIdade mediana 17,9 16,8 17,4 17,9 18,7 16,6 16,3 18,8 20,2'

ANNEX = '\x0c\n70\n   Quadro 2\nPopulação de nacionalidade guineense segundo\nregião por etnia\n                      Região\nEtnia Guiné-Bissau Tombali Quinara Oio Biombo B.Bijagos Bafatá Gabú Cacheu SAB\nEfectivos % Efectivos % Efectivos % Efectivos % Efectivos % Efectivos % Efectivos % Efectivos % Efectivos %\nTotal 1442227 90128 6,2 60624 4,2 214791 14,9 92665 6,4 32140 2,2 200242 13,9 204814 14,2 184124 12,8 362699 25,1\nSemEtnia 32098 1215 3,8 505 1,6 1097 3,4 612 1,9 602 1,9 2909 9,1 3237 10,1 3783 11,8 18138 56,5\nBalanta 323948 42276 13,1 21329 6,6 93737 28,9 17983 5,6 1403 0,4 16094 5,0 3734 1,2 53072 16,4 74320 22,9\nFula 410560 18861 4,6 4788 1,2 2980 0,7 4065 1,0 1154 0,3 120183 29,3 162970 39,7 9142 2,2 65417 15,9\nMandinga 212269 4386 2,1 3041 1,4 70739 33,3 1503 0,7 1462 0,7 45818 21,6 29017 13,7 1460 0,7 44843 21,1\nManjaco 119808 1042 0,9 1650 1,4 6561 5,5 2487 2,1 893 0,7 4498 3,8 916 0,8 67726 56,5 34035 28,4\nMancanha 44829 280 0,6 749 1,7 1391 3,1 2539 5,7 1676 3,7 788 1,8 452 1,0 8304 18,5 28650 63,9\nPapel 130651 1437 1,1 2088 1,6 1587 1,2 59995 45,9 1805 1,4 2191 1,7 526 0,4 4206 3,2 56816 43,5\nBijagos 30294 1165 3,8 1491 4,9 147 0,5 849 2,8 20670 68,2 202 0,7 395 1,3 260 0,9 5115 16,9\nBeafada 50543 5156 10,2 22231 44,0 2186 4,3 451 0,9 2004 4,0 2567 5,1 613 1,2 744 1,5 14591 28,9\nFelupe 24892 58 0,2 63 0,3 158 0,6 930 3,7 110 0,4 145 0,6 55 0,2 16713 67,1 6660 26,8\nMansoanca 20456 711 3,5 2215 10,8 8029 39,3 708 3,5 60 0,3 1878 9,2 904 4,4 1049 5,1 4902 24,0\nBalantaMane 14460 148 1,0 17 0,1 4530 31,3 151 1,0 5 0,0 555 3,8 153 1,1 7064 48,9 1837 12,7\nNalu 13420 10498 78,2 218 1,6 55 0,4 149 1,1 69 0,5 159 1,2 253 1,9 109 0,8 1910 14,2\nSussu 5318 2700 50,8 175 3,3 112 2,1 60 1,1 122 2,3 257 4,8 206 3,9 106 2,0 1580 29,7\nSaracule 7407 128 1,7 47 0,6 437 5,9 75 1,0 55 0,7 1920 25,9 1331 18,0 286 3,9 3128 42,2\nND 1274 67 5,3 17 1,3 45 3,5 108 8,5 50 3,9 78 6,1 52 4,1 100 7,8 757 59,4\n\n\x0c\n71\nQuadro nº 3\n          Distribuição percentual da população de nacionalidade guineense segundo  região por religião\nReligião\nREGIÃO\nGUINE-BISSAU Tombali Quinara Oio Biombo B. Bijagós Bafatá Gabú Cacheu SAB\nEfectivos % Efectivo % Efectivo % Efectivo % Efectivo % Efectivo % Efectivo % Efectivo % Efectivo % Efectiv %\nTOTAL 1442227 100,0 90128 100,0 60624 100,0 214791 100,0 92665\n100,\n0 32140 100,0 200242 100,0 204814 100,0 184124 100,0 362699\n10\n0,0\nAnimista 215130 14,9 21748 24,1 3767 6,2 44683 20,8 37193 40,1 7897 24,6 7814 3,9 654 0,3 62670 34,0 28704\n7,\n9\nMuçulmana 650402 45,1 38722 43,0 27753 45,8 90341 42,1 5828 6,3 4773 14,9 154402 77,1 177265 86,5 27218 14,8 124100\n34\n,2\nCristão 318021 22,1 13225 14,7 11752 19,4 33904 15,8 27997 30,2 9864 30,7 13670 6,8 5361 2,6 56597 30,7 145651\n40\n,2\nOutra religião 414 0,0 44 0,0 2 0,0 26 0,0 6 0,0 1 0,0 6 0,0 5 0,0 279 0,2 45\n0,\n0\nSem religião 29542 2,0 369 0,4 4289 7,1 1829 0,9 2346 2,5 1340 4,2 1739 0,9 120 0,1 5507 3,0 12003\n3,\n3\nND 228718 15,9 16020 17,8 13061 21,5 44008 20,5 19295 20,8 8265 25,7 22611 11,3 21409 10,5 31853 17,3 52196\n14\n,4\n\n'


class GuineaBissauThematic(unittest.TestCase):
    def test_tables(self):
        thematic = gb.thematic_tables(QUADRO_9B, ANNEX)
        self.assertEqual(thematic["median"]["Bissau"], 20.2)
        self.assertEqual(thematic["median"]["Bafatá"], 16.6)
        self.assertEqual(thematic["ethnicity"]["Biombo"]["Papel"], 59_995)
        self.assertEqual(thematic["religion"]["Gabú"]["Islam"], 177_265)
        self.assertEqual(sum(thematic["religion"]["Bissau"].values()), 362_699)
        # Two cells the table misprints, each a row and a region short by the same amount.
        self.assertEqual(thematic["ethnicity"]["Oio"]["Fula"], 23_980)
        self.assertEqual(thematic["ethnicity"]["Cacheu"]["Mandinga"], 11_460)
        self.assertEqual(sorted(thematic["corrections"]["ethnicity"]),
                         [("Fula", "Oio", 2_980, 23_980), ("Mandinga", "Cacheu", 1_460, 11_460)])
        self.assertIn("prints the Fula of Oio as 2,980",
                      gb.thematic_fields("Oio", thematic)["ethnicity_note"])

    def test_region_fields(self):
        thematic = gb.thematic_tables(QUADRO_9B, ANNEX)
        fields = gb.thematic_fields("Bolama", thematic)
        self.assertEqual(fields["ethnicity"][0]["group"], "Bijago")
        self.assertEqual(fields["median_age"]["value"], 18.7)
        self.assertIn("ethnic group and by urban or rural", fields["language"]["note"])
        self.assertEqual(len(fields["extra_sources"]), 2)


class AutonomousSector(unittest.TestCase):
    """The Autonomous Sector of Bissau is the region and its one sector polygon."""

    def test_the_region_fields_stand_on_its_one_polygon(self):
        thematic = gb.thematic_tables(QUADRO_9B, ANNEX)
        spec = gb.REGIONS["Bissau"]
        sectors = {k: {"name": k, "total": 1000 * (i + 1), "men": 500 * (i + 1),
                       "women": 500 * (i + 1)} for i, k in enumerate(spec["sectors"])}
        total = sum(r["total"] for r in sectors.values())
        tables = {"Bissau": {"region": (total, total // 2, total - total // 2),
                             "sectors": sectors}}
        admin1 = [{"id": spec["polygon"], "name": "Bissau", "parent": "GNB"}]
        sid = next(iter(spec["sectors"].values()))
        admin2 = [{"id": sid, "name": "Bissau Autonomous Sector", "parent": spec["polygon"]}]
        records, _ = gb.build(tables, admin1, admin2, thematic)
        by = {r["level"]: r for r in records}
        sector = by["admin2"]
        self.assertEqual(sector["median_age"]["value"], 20.2)
        self.assertIn("which is this one polygon", sector["median_age_note"])
        self.assertEqual(sector["religion"], by["admin1"]["religion"])
        self.assertTrue(sector["ethnicity_note"].endswith("The region is this one polygon."))
        self.assertEqual(sector["language"]["status"], "not_available")
        self.assertEqual([s["field"] for s in sector["sources"]],
                         ["population/sex_ratio", "median_age", "religion/ethnicity"])

if __name__ == "__main__":
    unittest.main()
