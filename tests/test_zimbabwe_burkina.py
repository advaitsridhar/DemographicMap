"""Zimbabwe's and Burkina Faso's tables as the runner printed them."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import burkina, zimbabwe  # noqa: E402

ZWE = """121
   Table 2.14(c): Distribution of Population by Province and Religion
Province
Christian Islam Judaism Hinduism None Other Total
Bulawayo 15,953 56,517 134,560 141,335 165,766 87,723 2,174 134 506 51,733 9,551 665,952
Manicaland 97,876 98,381 312,977 1,023,813 292,168 98,772 10,610 1,105 217 92,401 9,383 2,037,703
Mashonaland Central 121,454 44,029 102,251 738,690 145,711 45,824 15,380 538 97 167,074 3,843 1,384,891
Mashonaland East 84,340 108,621 206,735 795,356 285,802 77,974 12,737 218 208 152,451 6,731 1,731,173
Mashonaland West 115,820 98,529 231,719 793,337 303,112 86,799 20,736 297 326 229,803 13,106 1,893,584
Matabeleland North 58,392 50,142 87,548 284,238 135,723 109,471 552 129 111 85,508 15,831 827,645
Matabeleland South 47,918 28,150 96,869 246,166 95,533 122,507 820 286 72 102,631 19,393 760,345
Midlands 76,860 149,747 300,203 724,510 262,800 150,372 5,565 2,578 238 121,641 17,391 1,811,905
Masvingo 65,031 124,522 183,566 705,097 205,120 254,650 2,954 994 99 80,868 15,627 1,638,528
Harare 79,016 216,850 433,307 659,961 690,830 143,421 17,100 566 1,551 171,468 13,161 2,427,231
Total 762,660 975,488 2,089,735 6,112,503 2,582,565 1,177,513 88,628 6,845 3,425 1,255,578 124,017 15,178,957
\f123
       Table 2.17: Distribution of Population by Mother Tongue and Province
Mother
South Midlands Masvingo Harare Total
Shona 194,608 1,497,197 1,240,364 1,560,987 1,659,614 63,746 102,791 1,402,206 1,361,210 2,169,011 11,251,734
Ndebele 384,447 5,777 3,819 8,438 16,594 489,320 445,820 202,217 15,198 27,694 1,599,324
English 9,802 1,642 568 2,039 2,157 1,348 847 2,343 865 22,298 43,909
Kalanga 5,981 2,897 559 729 2,059 2,683 32,742 1,988 1,432 1,226 52,296
Koisan 8 17 12 30 56 46 19 43 31 43 305
Nambya 2,279 474 173 207 539 32,254 1,135 560 208 473 38,302
Ndau 962 334,578 1,119 2,646 3,093 426 791 3,943 19,461 5,588 372,607
Chibarwe 49 1,817 198 455 189 60 24 93 144 269 3,298
Shangani 435 5,722 153 281 543 312 5,598 1,437 100,113 539 115,133
Chewa 2,376 675 3,798 2,821 10,167 5,353 880 4,088 784 4,875 35,817
Sign Language 92 157 128 208 114 130 146 211 215 219 1,620
Sotho 3,467 127 60 124 189 1,086 32,758 648 350 346 39,155
Tonga 13,431 300 480 818 21,263 157,302 6,628 28,747 577 1,613 231,159
Tswana 293 62 33 76 95 181 1,011 170 125 201 2,247
Venda 1,169 164 98 168 279 522 65,039 806 2,962 440 71,647
Xhosa 1,189 71 32 141 332 6,494 1,556 996 106 387 11,304
Other 3,671 9,694 4,924 2,281 7,981 1,581 2,818 2,275 342 7,829 43,396
Total 624,259 1,861,371 1,256,518 1,582,449 1,725,264 762,844 700,603 1,652,771 1,504,123 2,243,051 13,913,253
"""

BFA = """LISTE DES TABLEAUX
Tableau I.22 : Répartition (en%) de la population résidente au Burkina Faso par région selon la religion ....... 18
\f18 | INSD
Tableau I.22 : Répartition (en%) de la population résidente au Burkina Faso par région selon la
religion
Région Animiste Musulman Catholique Protestant Autre Sans religion Ensemble
Boucle du Mouhoun 9,5 64,9 18,6 6 0,2 0,8 1 762 146
Cascades 8,5 81,6 6,1 1,7 0,2 1,9    764 447
Centre 0,3 61,2 31,3 6,9 0,2 0,1 2 693 142
Centre-Est 1,7 77,1 19,0 1,9 0,1 0,2 1 428 222
Centre-Nord 13,8 67,3 15,6 3,1 0,0 0,2 1 424 407
Centre-Ouest 8,9 45,8 35,7 8,5 0,2 0,9 1 562 559
Centre-Sud 7,6 54,1 28,9 8,9 0,2 0,3    744 251
Est 20,3 34,6 22,3 21 0,4 1,4 1 578 981
Hauts-Bassins 6,4 76,2 12,3 3,9 0,2 1,0 2 046 973
Nord 6,0 82,6 8,4 2,7 0,0 0,3 1 582 561
Plateau Central 4,1 66,1 25,6 4,1 0,0 0,1    922 488
Sahel 0,5 97,4 1,0 0,7 0,0 0,4    836 374
Sud-Ouest 48,1 19,4 23,1 7,0 0,4 2,0    825 200
Burkina Faso 9,0 63,8 20,1 6,2 0,2 0,7 18 171 751
"""


class ZimbabweReadsBothTables(unittest.TestCase):
    def test_build(self):
        records = zimbabwe.build(ZWE)
        self.assertEqual(len(records), 10)
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Harare"]["religion"][0], {"group": "Pentecostal", "pct": 28.5, "count": 690830})
        self.assertEqual(by["Matabeleland North"]["language"][0]["group"], "Ndebele")
        self.assertEqual(by["Matabeleland North"]["language"][1], {"group": "Tonga", "pct": 20.6, "count": 157302})
        self.assertNotIn("ethnicity_year", by["Harare"])
        with self.assertRaises(SystemExit):
            zimbabwe.build(ZWE.replace("Harare 79,016", "Harare 79,017"))


class BurkinaReadsSharesOfAStatedPopulation(unittest.TestCase):
    def test_build(self):
        records = burkina.build(BFA)
        self.assertEqual(len(records), 13)
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Sud-Ouest"]["religion"][0], {"group": "Animist", "pct": 48.1, "count": 396921})
        self.assertEqual(by["Est"]["religion"][2], {"group": "Protestant", "pct": 21.0, "count": 331586})
        self.assertEqual(sum(b["count"] for b in by["Sahel"]["religion"]) // 1000, 836)
        with self.assertRaises(SystemExit):
            burkina.build(BFA.replace("Sahel 0,5 97,4", "Sahel 5,0 97,4"))


if __name__ == "__main__":
    unittest.main()
