"""The Gambia's census tables, as the runner reads GBoS's reports.

The page texts below are copied from the runner's logs: the directory of
settlements and the 2024 preliminary report as the words' positions put them
back together (probe_pdf --layout), the 2013 spatial report's annexes as its
text layer gives them. Annex H's tables are cut to their title, heading,
first row and Total row, which is all the reader takes from them.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import gambia_census as g  # noqa: E402

DIRECTORY_PAGE_5 = """Name BOTH SEXES FEMALE
LGA/District /
Settlement Total <1 1-2 3-4 5-6 7-14 15-49 50-59 60+ NS Total <1 1-2 3-4 5-6 7-14 15-49 50-59 60+ NS
The Gambia
1,857,181 53,351 109,092 129,411 122,353377,858 902,933 72,169 88,353 1,661 943,426 26,142 53,561 64,399 60,438 188,005 471,542 34,323 43,378 763
Banjul
31,054 756 1,312 1,388 1,284 4,567 18,302 1,739 1,683 23 14,251 369 619 687 625 2,272 8,099 731 835 14
Banjul Central 11,562 319 499 506 482 1,726 6,632 721 665 12 5,501 154 233 264 239 857 3,087 340 319 8
Banjul North 11,285 239 452 479 470 1,633 6,941 538 533 - 4,898 121 214 233 228 819 2,815 216 252 -
Banjul South 8,207 198 361 403 332 1,208 4,729 480 485 11 3,852 94 172 190 158 596 2,197 175 264 6
Kanifing
377,134 9,838 18,752 21,533 19,620 64,601 210,956 15,326 15,312 1,196 187,973 4,809 9,134 10,729 9,850 33,605 104,709 7,091 7,535 511
Abuko 15,811 460 855 998 924 2,830 8,472 685 586 1 7,814 223 418 460 464 1,440 4,252 289 267 1
Bakau New Town 25,265 562 1,084 1,255 1,176 4,021 14,480 1,289 1,398 - 12,551 280 517 644 582 2,068 7,155 632 673 -
Bakau Wasulun 3,545 81 139 173 161 503 1,958 192 206 132 1,732 50 55 90 70 250 979 91 108 39
Bakoteh 16,924 426 832 968 859 2,968 9,462 685 724 - 8,546 197 395 502 453 1,553 4,779 313 354 -
Bundunka Kunda 55,360 1,593 2,960 3,321 3,077 9,582 30,901 1,948 1,977 1 27,424 780 1,478 1,622 1,566 5,008 15,102 917 951 -
Dippa Kunda 17,654 435 934 1,031 897 2,936 9,952 708 761 - 8,513 199 433 536 448 1,510 4,651 338 398 -
Ebo Town 22,789 639 1,224 1,444 1,296 4,201 12,286 875 824 - 11,279 333 602 715 633 2,132 6,078 404 382 -
Faji Kunda 38,121 1,088 2,069 2,376 2,092 6,747 21,098 1,288 1,363 - 19,149 519 1,003 1,164 1,065 3,638 10,510 591 659 -
Kololi 7,257 151 238 313 285 932 3,974 376 338 650 3,533 76 119 162 136 493 1,963 145 160 279
Kotu 16,358 355 752 906 805 2,636 9,135 729 641 399 8,249 175 373 427 407 1,356 4,670 336 317 188
Kanifing 14,296 281 546 653 567 2,120 8354 884 891 - 7,446 135 257 344 286 1,145 4,361 482 436 -
Pipeline 4,317 73 129 210 192 715 2,512 230 256 - 2,043 37 54 104 89 307 1,202 120 130 -
Latri Kunda
German 19,765 459 963 1,020 1,020 3,214 11,283 863 941 2 9,863 194 493 496 500 1,640 5,629 403 507 1
Latri Kunda
Sabiji 15,619 452 833 938 852 2,734 8,629 606 575 - 7,864 222 382 454 414 1,476 4,352 277 287 -
Manjai Kunda 18,601 549 944 1,095 1,013 3,387 10,300 692 621 - 9,326 282 471 557 510 1,738 5,153 309 306 -
New Jeshwang 17,394 451 866 1,021 895 3,051 9,730 662 718 - 8,691 225 417 510 435 1,586 4,810 332 376 -
Old Jeshwang 7,552 139 345 386 376 1,509 4,162 324 311 - 3,866 60 173 208 184 766 2,167 147 161 -
Sere Kunda 19,944 500 990 1,085 964 3,212 11,519 841 822 11 9,758 243 490 533 513 1,686 5,501 360 429 3
Talinding 40,562 1,144 2,049 2,340 2,169 7,303 22,749 1,449 1,359 - 20,326 579 1,004 1,201 1,095 3,813 11,395 605 634 -
"""

PRELIMINARY_PAGE_20 = """Table 8: Distribution of Ethnic Groups by LGA
LGA Mandinka Fula Wollof Jola Sarahule
Population
The Gambia 34.4 25.0 15.4 9.5 8.2
Banjul 20.2
24.7 24.5 5.5 2.9
Kanifing 31.5
18.5 14.1 14.8 9.5
Brikama 40.3
21.0 12.0 14.8 4.4
Mansakonko 50.6
35.8 6.4 1.1 3.7
Kerewan 27.2
22.5 34.6 0.7 0.6
Kuntaur 21.9
41.7 34.5 0.2 0.2
Janjanbureh 22.8
41.5 27.5 0.5 6.1
Basse 28.3
32.6 0.6 0.3 37.1
LGA Serere Krio/Aku Marabou Manjago BambSarearere other ethnicS egrreorueps
Population
The Gambia 2.9 0.4 1.7 1.2 1.3
Banjul 11.9 3.8 1.1 3.8
1.7
Kanifing 4.5 1.4 2.8 1.1
2.0
Brikama 2.5 0.4 2.3 0.7
1.7
Mansakonko 0.6 0.1 0.7 0.6
0.5
Kerewan 7.8 0.1 0.8 5.0
0.8
Kuntaur 0.4 0.0 0.1 0.5
0.5
Janjanbureh 0.4 0.0 0.2 0.5
0.5
Basse 0.2 0.0 0.1 0.6
0.3
LGA Total
Population
The Gambia 2,306,066
Banjul 21,982
Kanifing 341,915
Brikama 1,095,708
Mansakonko 88,251
Kerewan 242,024
Kuntaur 116,164
Janjanbureh 145,133
Basse 254,889
PAGE 13
GAMBIA BUREAU OF STATISTICS
[163 words in 52 rows]
"""

TABLE_12 = """Table 12: Population Distribution by Sex and LGA
Male Female Total
LGA Count Per cent Count Per cent Count Per cent
Population
Total 1,186,293 49.0 1,236,419 51.0 2,422,712 100.0
Banjul 14,192 53.6 12,269 46.4
26,461 100.0
Kanifing 185,138 48.8 194,210 51.2
379,348 100.0
Brikama 570,310 49.5 580,818 50.5 1,151,128 100.0
Mansakonko 44,309 48.9 46,315 51.1 90,624 100.0
Kerewan 119,651 48.2 128,824 51.9 248,475 100.0
Kuntaur 56,938 48.2 61,166 51.8 118,104 100.0
Janjanbureh 71,494 48.5 75,918 51.5 147,412 100.0
Basse 47.6 136,899 52.4 261,160 100.0
124,261
PAGE 15
GAMBIA BUREAU OF STATISTICS
[195 words in 52 rows]
"""

ANNEX_F_BANJUL = """32
Table F.2: Population by sex and five-year age group (Banjul)
 Age group Male Female Both Sexes
0-4 1,781 1,675 3,456
5-9 1,522 1,544 3,066
10-14 1,432 1,353 2,785
15-19 1,617 1,610 3,227
20-24 1,783 1,760 3,543
25-29 1,860 1,458 3,318
30-34 1,690 1,189 2,879
35-39 1,314 840 2,154
40-44 1,089 681 1,770
45-49 850 561 1,411
50-54 621 452 1,073
55-59 387 279 666
60-64 329 238 567
65-69 208 164 372
70-74 142 157 299
75-79 78 89 167
80-84 52 89 141
85+ 39 98 137
Not stated 9 14 23
Total 16,803 14,251 31,054
"""

ANNEX_F_KEREWAN = """36
Table F.6: Population by residence, sex and five-year age group (Kerewan)
  Total
Urban
Rural
Age group Male Female Both sexes
Male Female Both sexes
Male Female Both sexes
0-4 19,002 18,693 37,695
3,829 3,760 7,589
15,173 14,933 30,106
5-9 19,058 18,211 37,269
3,652 3,653 7,305
15,406 14,558 29,964
10-14 14,716 13,701 28,417
2,988 2,926 5,914
11,728 10,775 22,503
15-19 11,935 13,187 25,122
2,869 3,292 6,161
9,066 9,895 18,961
20-24 8,027 10,251 18,278
2,291 2,718 5,009
5,736 7,533 13,269
25-29 6,887 8,829 15,716
2,228 2,129 4,357
4,659 6,700 11,359
30-34 5,314 7,083 12,397
1,589 1,684 3,273
3,725 5,399 9,124
35-39 4,278 5,496 9,774
1,195 1,306 2,501
3,083 4,190 7,273
40-44 3,586 4,401 7,987
1,001 1,032 2,033
2,585 3,369 5,954
45-49 2,786 3,320 6,106
758 772 1,530
2,028 2,548 4,576
50-54 2,702 3,095 5,797
676 663 1,339
2,026 2,432 4,458
55-59 1,700 1,518 3,218
436 344 780
1,264 1,174 2,438
60-64 1,958 2,090 4,048
458 393 851
1,500 1,697 3,197
65-69 1,233 1,091 2,324
300 219 519
933 872 1,805
70-74 1,079 1,285 2,364
205 212 417
874 1,073 1,947
75-79 609 619 1,228
99 103 202
510 516 1,026
80-84 530 682 1,212
93 119 212
437 563 1,000
85+ 509 609 1,118
72 123 195
437 486 923
Not stated 3 7 10
1 0 1
2 7 9
Total 105,912 114,168 220,080
24,740 25,448 50,188
81,172 88,720 169,892
"""

ANNEX_H_1 = """Table H.1: Population by five-year age group and religion (The Gambia-Both sexes)
Age group Islam Christianity Traditional Other Not stated Total
0-4 283,757 7,757 127 110 103 291,854
5-9 271,733 8,043 103 102 85 280,066
10-14 212,485 7,411 88 104 57 220,145
15-19 206,276 7,737 110 75 66 214,264
20-24 176,432 7,182 113 141 71 183,939
25-29 152,553 6,448 125 160 70 159,356
30-34 116,454 5,422 87 143 63 122,169
35-39 89,563 4,738 67 143 55 94,566
40-44 68,880 3,920 51 135 43 73,029
45-49 52,416 3,026 36 104 28 55,610
50-54 43,047 2,366 25 111 24 45,573
55-59 24,934 1,521 25 90 26 26,596
60-64 28,738 1,437 25 75 23 30,298
65-69 17,188 920 14 50 25 18,197
70-74 14,914 600 15 18 11 15,558
75-79 8,317 361 5 12 5 8,700
80-84 7,522 285 6 3 5 7,821
85+ 7,464 303 6 4 2 7,779
Not stated 186 161 0 1,106 208 1,661
Total 1,782,859 69,638 1,028 2,686 970 1,857,181
"""

ANNEX_H_LGAS = """Table H.4: Population by five-year age group and religion (Banjul-Both sexes)
Age group Islam Christianity Traditional Other Not stated Total
0-4 3,361 84 0 2 9 3,456
Total 29,423 1,504 12 64 51 31,054
Table H.7: Population by five-year age group and religion (Kanifing-Both sexes)
Age group Islam Christianity Traditional Other Not stated Total
0-4 47,035 2,991 29 43 25 50,123
Total 345,546 29,036 309 1,996 247 377,134
Table H.10: Population by five-year age group and religion (Brikama-Both sexes)
Age group Islam Christianity Tradition Other Not stated Total
0-4 103,159 4,008 88 31 33 107,319
Total 654,198 33,168 602 329 447 688,744
Table H.19: Population by five-year age group and religion (Mansakonko-Both sexes)
Age group Islam Christianity Tradition Other Not stated Total
0-4 13,076 65 0 1 5 13,147
Total 80,434 540 9 39 20 81,042
Table H.28: Population by five-year age group and religion (Kerewan-Both sexes)
Age group Islam Christianity Traditional Other Not stated Total
0-4 7,500 73 1 1 14 7,589
Total 49,223 897 9 10 49 50,188
Table H.29: Population by five-year age group and religion (Kerewan-Male)
Age group Islam Christianity Traditional Other Not stated Total
0-4 18,839 153 0 2 8 19,002
Total 104,446 1,414 12 16 24 105,912
Table H.30: Population by five-year age group and religion (Kerewan-Female)
Age group Islam Christianity Traditional Other Not stated Total
0-4 18,557 119 2 7 8 18,693
Total 112,745 1,349 20 16 38 114,168
Table H.37: Population by five-year age group and religion (Kuntaur-Both sexes)
Age group Islam Christianity Traditional Other Not stated Total
0-4 17,348 89 0 0 3 17,440
Total 95,992 673 3 7 28 96,703
Table H.38: Population by five-year age group and religion (Kuntaur-Male)
Age group Islam Christianity Other Not stated Total
0-4 8,694 42 0 3 8,739
Total 45,338 330 4 13 45,685
Table H.46: Population by five-year age group and religion (Janjanbureh-Both sexes)
Age group Islam Christianity Traditional Other Not stated Total
0-4 21,039 100 2 4 5 21,150
Total 124,254 817 25 34 74 125,204
Table H.55: Population by five-year age group and religion (Basse-Both sexes)
Age group Islam Christianity Traditional Other
Not
stated Total
0-4 41,343 148 6 20 7 41,524
Total 235,821 1,137 36 185 41 237,220
"""

LGA_2013 = {"Banjul": (31_054, 14_251), "Kanifing": (377_134, 187_973),
            "Brikama": (688_744, 344_123), "Mansakonko": (81_042, 42_270),
            "Kerewan": (220_080, 114_168), "Kuntaur": (96_703, 51_018),
            "Janjanbureh": (125_204, 65_204), "Basse": (237_220, 124_419)}
DIRECTORY_2013 = {lga: {"total": total} for lga, total in LGA_2013.items()}


class DirectoryTest(unittest.TestCase):
    def test_rows_join_broken_names_and_skip_the_country(self):
        rows = g.directory_rows([DIRECTORY_PAGE_5])
        self.assertEqual(rows[0], ("Banjul", 31_054, 14_251))
        self.assertIn(("Latri Kunda German", 19_765, 9_863), rows)
        self.assertNotIn("The Gambia", [name for name, _, _ in rows])
        self.assertEqual(len(rows), 1 + 3 + 1 + 19)

    def test_districts_by_name_and_the_lga_named_like_its_settlement(self):
        with mock.patch.object(g, "LGAS", ("Banjul", "Kanifing")), \
                mock.patch.object(g, "NATIONAL_2013", 31_054 + 377_134):
            d = g.districts_2013(g.directory_rows([DIRECTORY_PAGE_5]))
        self.assertEqual(d["Banjul"]["districts"],
                         {"Banjul Central": (11_562, 5_501), "Banjul North": (11_285, 4_898),
                          "Banjul South": (8_207, 3_852)})
        self.assertEqual(d["Kanifing"]["districts"], {"Kanifing": (377_134, 187_973)})
        self.assertEqual(d["Kanifing"]["settled"]["Kanifing"], 377_134)

    def test_settlements_may_come_near_their_district(self):
        self.assertTrue(g.close_enough(17_810, 16_034))
        self.assertFalse(g.close_enough(16_034 + 14_990, 16_034))


class PreliminaryTest(unittest.TestCase):
    def test_table_12_takes_the_men_by_their_share(self):
        t = g.table12([TABLE_12])
        self.assertEqual(t["Banjul"], (26_461, 14_192, 12_269))
        # Basse's row prints its men's count last, on a line of its own.
        self.assertEqual(t["Basse"], (261_160, 124_261, 136_899))
        self.assertEqual(sum(v[0] for v in t.values()), 2_422_712)

    def test_table_8_reads_both_halves(self):
        t = g.table8([PRELIMINARY_PAGE_20])
        gambians, shares = t["Basse"]
        self.assertEqual(gambians, 254_889)
        self.assertEqual(shares["Sarahule"], 37.1)
        self.assertEqual(t["Kerewan"][1]["Wollof"], 34.6)
        self.assertEqual(t["Kerewan"][1]["Bambara"], 5.0)
        self.assertEqual(sum(v[0] for v in t.values()), 2_306_066)


class AnnexTest(unittest.TestCase):
    def test_annex_f_medians(self):
        with mock.patch.object(g, "LGAS", ("Banjul", "Kerewan")):
            ages = g.annex_f([ANNEX_F_BANJUL, ANNEX_F_KEREWAN], DIRECTORY_2013)
        self.assertEqual(ages["Banjul"][0], 3_456)
        self.assertEqual(g.median(ages["Banjul"]), 24.2)
        self.assertEqual(g.median(ages["Kerewan"]), 16.3)

    def test_annex_f_checks_the_directory(self):
        wrong = dict(DIRECTORY_2013, Banjul={"total": (31_055, 14_251)})
        with mock.patch.object(g, "LGAS", ("Banjul", "Kerewan")), \
                self.assertRaises(SystemExit):
            g.annex_f([ANNEX_F_BANJUL, ANNEX_F_KEREWAN], wrong)

    def test_annex_h_mends_kerewan_from_its_men_and_women(self):
        religion, unused = g.annex_h([ANNEX_H_1, ANNEX_H_LGAS], DIRECTORY_2013)
        self.assertEqual(religion["Kerewan"], [217_191, 2_763, 32, 32, 62])
        self.assertEqual(unused, {"Kerewan": 50_188})
        self.assertEqual(religion["Basse"], [235_821, 1_137, 36, 185, 41])
        self.assertEqual(religion["Brikama"][2], 602)

    def test_annex_h_columns(self):
        self.assertEqual(g.columns("Islam Christianity Other Not stated Total"),
                         ["Islam", "Christianity", "Other", "Not stated", "Total"])
        self.assertEqual(g.columns("Islam Christianity Tradition Other\nNot\nstated Total")[2],
                         "Traditional")
        self.assertIsNone(g.columns("Islam Hindu Total"))


class BindTest(unittest.TestCase):
    def tables(self):
        with mock.patch.object(g, "LGAS", ("Banjul", "Kerewan")):
            ages = g.annex_f([ANNEX_F_BANJUL, ANNEX_F_KEREWAN], DIRECTORY_2013)
        religion, unused = g.annex_h([ANNEX_H_1, ANNEX_H_LGAS], DIRECTORY_2013)
        return {"population": g.table12([TABLE_12]),
                "ethnicity": g.table8([PRELIMINARY_PAGE_20]), "ages": ages,
                "religion": religion, "religion_unused": unused}

    def test_lgas(self):
        admin1 = [{"id": "b", "name": "Banjul"}, {"id": "k", "name": "Kerewan"}]
        tables = self.tables()
        with mock.patch.object(g, "LGAS", ("Banjul", "Kerewan")):
            records = {r["name"]: r for r in g.bind_lgas(admin1, tables)}
        banjul, kerewan = records["Banjul"], records["Kerewan"]
        self.assertEqual(banjul["population"]["value"], 26_461)
        self.assertEqual(banjul["sex_ratio"]["value"], 115.7)
        self.assertEqual(banjul["median_age"]["value"], 24.2)
        self.assertEqual(banjul["ethnicity"][0], {"group": "Fula", "pct": 24.7})
        self.assertIn("21,982 Gambian nationals", banjul["ethnicity_note"])
        self.assertEqual(kerewan["religion"][0]["count"], 217_191)
        self.assertIn("(50,188)", kerewan["religion_note"])
        self.assertNotIn("repeats", banjul["religion_note"])

    def test_districts_and_kanifing_parts(self):
        admin1 = [{"id": n[:3], "name": n} for n in g.LGAS]
        admin2 = [{"id": "x1", "name": "Banjul Central", "parent": "Ban"},
                  {"id": "x2", "name": "Bakau", "parent": "Kan"}]
        d2013 = {lga: {"total": total, "districts": {}} for lga, total in LGA_2013.items()}
        d2013["Banjul"]["districts"] = {"Banjul Central": (11_562, 5_501)}
        central, bakau = g.bind_districts(d2013, admin1, admin2)
        self.assertEqual(central["population"]["value"], 11_562)
        self.assertEqual(central["sex_ratio"]["value"], 110.2)
        self.assertIn("by local government area", central["religion"]["note"])
        self.assertIn("377,134", bakau["population"]["note"])
        self.assertNotIn("value", bakau["sex_ratio"])
        # The part's reasons cite the directory they rest on, and every
        # district's reasons for its ages, religion and ethnicity their reports.
        cited = {s["field"]: s["name"] for s in bakau["sources"]}
        self.assertIn("Directory of Settlements", cited["population/sex_ratio"])
        self.assertIn("Spatial Distribution", cited["median_age/religion/ethnicity"])
        self.assertTrue(any(s["field"] == "religion/ethnicity" and "2024" in s["name"]
                            for s in central["sources"]))


if __name__ == "__main__":
    unittest.main()
