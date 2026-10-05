"""Marshall Islands, 2021 Census: the basic tables and the analytical report, as read.

The fixtures are the PDFs' own text as pypdf gives it -- Tables 3, 7, 9 and
10 of the basic tables, Tables 2.4 and 3.3 of the analytical report -- with
the kerning that splits "1,140" into "1,14 0" left in. No network.
"""

import unittest

from scripts.fetch_census import marshall_census as mh
from scripts.fetch_census.oceania_common import load_units

TABLES = """Table 3.  Population by Urban/Rural and atoll by sex – RMI Census 2021
Atoll by Urban/Rural Sex
Total Male Female
Urban / Rural area
Total 42,418 21,728 20,690
Rural 9,473 4,962 4,511
Urban 32,945 16,766 16,179
Atoll  / island
Total 42,418 21,728 20,690
1–Ailinglaplap 1,175 599 576
2–Ailuk 235 117 118
3–Arno 1,141 619 522
4–Aur 317 172 145
5–Bikini 0 0 0
6–Ebon 469 260 209
7–Enewetak 296 159 137
8–Jabat 75 41 34
9–Jaluit 1,409 721 688
10–Kili 415 226 189
11–Kwajalein 9,789 5,096 4,693
12–Lae 133 69 64
13–Lib 156 74 82
14–Likiep 228 114 114
15–Majuro 23,156 11,670 11,486
16–Maloelap 395 219 176
17–Mejit 230 119 111
18–Mili 497 272 225
19–Namdrik 299 155 144
20–Namu 525 284 241
21–Rongelap 0 0 0
22–Ujae 310 153 157
24–Utirik 264 131 133
25–Wotho 88 44 44
26–Wotje 816 414 402
11
Republic of the Marshall Islands 2021 Census report
Volume 1: Basic tables and administrative report 
Table 4.  Population by Urban/Rural and atoll by citizenship
Table 7.  Population by Urban/Rural and atoll by HH type by sex – RMI Census 2021
Atoll by Urban/Rural
Household_Type
Total Private HH Institutions
Total Male Female Total Male Female Total Male Female
Urban / Rural area 
Total 42,418 21,728 20,690 41,575 21,250 20,325 843 478 365
Rural 9,473 4,962 4,511 8,963 4,714 4,249 510 248 262
Urban 32,945 16,766 16,179 32,612 16,536 16,076 333 230 103
Atoll  / Island 
Total 42,418 21,728 20,690 41,575 21,250 20,325 843 478 365
1–Ailinglaplap 1,175 599 576 1,172 596 576 3 3 0
2–Ailuk 235 117 118 235 117 118 0 0 0
3–Arno 1,141 619 522 1,14 0 618 522 1 1 0
4–Aur 317 172 145 317 172 145 0 0 0
5–Bikini 0 0 0 0 0 0 0 0 0
6–Ebon 469 260 209 469 260 209 0 0 0
7–Enewetak 296 159 137 296 159 137 0 0 0
8–Jabat 75 41 34 75 41 34 0 0 0
9–Jaluit 1,409 721 688 1,058 561 497 351 160 191
10–Kili 415 226 189 415 226 189 0 0 0
11–Kwajalein 9,789 5,096 4,693 9,739 5,053 4,686 50 43 7
12–Lae 133 69 64 133 69 64 0 0 0
13–Lib 156 74 82 156 74 82 0 0 0
14–Likiep 228 114 114 228 114 114 0 0 0
15–Majuro 23,156 11,670 11,486 22,873 11,483 11,390 283 187 96
16–Maloelap 395 219 176 395 219 176 0 0 0
17–Mejit 230 119 111 230 119 111 0 0 0
18–Mili 497 272 225 497 272 225 0 0 0
19–Namdrik 299 155 144 299 155 144 0 0 0
20–Namu 525 284 241 525 284 241 0 0 0
21–Rongelap 0 0 0 0 0 0 0 0 0
22–Ujae 310 153 157 310 153 157 0 0 0
24–Utirik 264 131 133 264 131 133 0 0 0
25–Wotho 88 44 44 88 44 44 0 0 0
26–Wotje 816 414 402 661 330 331 155 84 71
17
Republic of the Marshall Islands 2021 Census report
Volume 1: Basic tables and administrative report 
Table 8.  Population by Urban/Rural and atoll and HH size
Table 9.  Population by Urban/Rural and atoll by religion – RMI Census 2021
Atoll by 
Urban/Rural
Religion
Total
United 
Church 
of Christ
Roman 
Catholic
Assembly 
of God
Jehovah’s 
Witness
Reformed 
Congres-
sional 
Church
Mormon
Seventh 
Day 
Adventist
Bukot 
Nan 
Jesus
None Full 
Gospel
Salvation 
Army
Other 
(specify)
Protes-
tant 
Church
New 
Beginning 
Church
Baptist 
Church
Batkan 
Light 
House 
Church
Urban / Rural area
Total 41,575 19,920 3,863 5,864 538 930 2,363 720 1,246 444 2,086 954 1,128 515 593 162 249
Rural 8,963 5,664 529 1,263 6 190 94 148 171 42 279 194 65 166 146 6 0
Urban 32,612 14,256 3,334 4,601 532 740 2,269 572 1,075 402 1,807 760 1,063 349 447 156 249
Atoll  / island
Total 41,575 19,920 3,863 5,864 538 930 2,363 720 1,246 444 2,086 954 1,128 515 593 162 249
1–Ailinglaplap 1,172 728 88 98 1 33 13 37 38 0 0 1 7 0 128 0 0
2–Ailuk 235 168 1 66 0 0 0 0 0 0 0 0 0 0 0 0 0
3–Arno 1,14 0 445 26 342 2 0 2 3 81 11 148 71 9 0 0 0 0
4–Aur 317 250 1 17 0 48 0 0 0 1 0 0 0 0 0 0 0
5–Bikini 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
6–Ebon 469 397 1 0 0 0 1 6 36 1 0 0 15 0 12 0 0
7–Enewetak 296 228 5 59 1 0 0 0 0 2 0 0 0 0 0 1 0
8–Jabat 75 75 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
9–Jaluit 1,058 691 125 2 0 88 2 8 5 0 0 122 10 0 0 5 0
10–Kili 415 276 2 68 0 0 0 0 0 0 0 0 1 68 0 0 0
11–Kwajalein 9,739 4,915 988 1,094 117 258 789 127 352 26 458 148 94 39 295 39 0
12–Lae 133 77 0 0 0 19 37 0 0 0 0 0 0 0 0 0 0
13–Lib 156 156 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
14–Likiep 228 37 162 25 0 0 0 0 0 0 4 0 0 0 0 0 0
15–Majuro 22,873 9,341 2,346 3,507 415 482 1,480 445 723 376 1,349 612 969 310 152 117 249
16–Maloelap 395 350 1 44 0 0 0 0 0 0 0 0 0 0 0 0 0
19
Republic of the Marshall Islands 2021 Census report
Volume 1: Basic tables and administrative report 
Atoll by 
Urban/Rural
Religion
Total
United 
Church 
of Christ
Roman 
Catholic
Assembly 
of God
Jehovah’s 
Witness
Reformed 
Congres-
sional 
Church
Mormon
Seventh 
Day 
Adventist
Bukot 
Nan 
Jesus
None Full 
Gospel
Salvation 
Army
Other 
(specify)
Protes-
tant 
Church
New 
Beginning 
Church
Baptist 
Church
Batkan 
Light 
House 
Church
17–Mejit 230 139 0 66 1 0 0 0 6 6 0 0 6 0 6 0 0
18–Mili 497 318 1 137 1 0 16 0 0 12 0 0 12 0 0 0 0
19–Namdrik 299 153 83 51 0 2 5 0 4 0 0 0 1 0 0 0 0
20–Namu 525 409 0 31 0 0 0 83 0 1 0 0 1 0 0 0 0
21–Rongelap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
22–Ujae 310 248 0 58 0 0 4 0 0 0 0 0 0 0 0 0 0
24–Utirik 264 126 0 71 0 0 1 0 0 0 59 0 2 5 0 0 0
25–Wotho 88 80 1 7 0 0 0 0 0 0 0 0 0 0 0 0 0
26–Wotje 661 313 32 121 0 0 13 11 1 8 68 0 1 93 0 0 0
 
20
Republic of the Marshall Islands 2021 Census report
Volume 1: Basic tables and administrative report 
Table 10.  Population by Urban/Rural and atoll by ethnicity – RMI Census 2021
Atoll by 
Urban/Rural
Ethnicity
Total Marshall 
Islands FSM Palau Kiribati Tuvalu Taiwan, 
ROC China, PRC Japan South 
Korea
Philip-
pines USA New 
Zealand Australia Fiji Other 
ethnicity
Solomon 
Islands
Urban / Rural area
Total 41,575 39,735 135 0 327 82 24 110 33 0 441 294 0 0 197 153 44
Rural 8,963 8,909 8 0 11 2 0 4 2 0 8 4 0 0 5 10 0
Urban 32,612 30,826 127 0 316 80 24 106 31 0 433 290 0 0 192 143 44
Atoll  / island
Total 41,575 39,735 135 0 327 82 24 110 33 0 441 294 0 0 197 153 44
1–Ailinglaplap 1,172 1,166 2 0 1 0 0 0 0 0 0 1 0 0 0 2 0
2–Ailuk 235 234 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0
3–Arno 1,14 0 1,136 0 0 1 0 0 0 1 0 1 0 0 0 0 1 0
4–Aur 317 317 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
5–Bikini 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
6–Ebon 469 469 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
7–Enewetak 296 291 0 0 0 0 0 1 0 0 1 0 0 0 1 2 0
8–Jabat 75 75 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
9–Jaluit 1,058 1,054 1 0 1 1 0 0 0 0 0 0 0 0 1 0 0
10–Kili 415 409 1 0 0 0 0 0 0 0 3 0 0 0 0 2 0
11–Kwajalein 9,739 9,467 48 0 38 2 4 7 1 0 58 63 0 0 31 16 4
12–Lae 133 133 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
13–Lib 156 156 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
14–Likiep 228 226 0 0 1 0 0 0 0 0 0 1 0 0 0 0 0
15–Majuro 22,873 21,359 79 0 278 78 20 99 30 0 375 227 0 0 161 127 40
16–Maloelap 395 395 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
17–Mejit 230 229 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0
18–Mili 497 494 0 0 0 0 0 0 1 0 0 0 0 0 1 1 0
21
Republic of the Marshall Islands 2021 Census report
Volume 1: Basic tables and administrative report 
Atoll by 
Urban/Rural
Religion
Total Marshall 
Islands FSM Palau Kiribati Tuvalu Taiwan, 
ROC China, PRC Japan South 
Korea
Philip-
pines USA New 
Zealand Australia Fiji Other 
ethnicity
Solomon 
Islands
19–Namdrik 299 297 1 0 1 0 0 0 0 0 0 0 0 0 0 0 0
20–Namu 525 525 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
21–Rongelap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
22–Ujae 310 308 0 0 0 1 0 1 0 0 0 0 0 0 0 0 0
24–Utirik 264 262 0 0 0 0 0 1 0 0 0 0 0 0 0 1 0
25–Wotho 88 87 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0
26–Wotje 661 646 2 0 6 0 0 1 0 0 3 0 0 0 2 1 0
22
Republic of the Marshall Islands 2021 Census report
Volume 1: Basic tables and administrative report 
Table 1 1.  Population by Urban/Rural by 5-year age group by ethnicity
"""

AGES = """Table 2.4.   Population by age group, median age, dependency and sex ratio, RMI, 2021
Atoll/
island
Age group distribution (%) Total 
pop.
Dependency ratio Median 
age
Sex 
ratioUnder 
15 15–24 25–34 35–54 55–64  65+ Total Y outh Aged
Total RMI 34.1 20.1 13.0 23.1 6.0 3.7 42,418 60.7 54.8 5.9 22 105
Urban 32.6 21.0 13.1 23.5 6.0 3.7 32,945 57. 0 51.2 5.8 22 104
Rural 39.2 16.6 12.8 21.9 5.9 3.7 9473 74.9 68.5 6.4 20 110
Ailinglaplap 45.1 9.8 11.9 22.3 6.5 4.4 1175 98.1 89.4 8.8 21 104
Ailuk 43.4 9.4 9.8 26.0 7.7 3.8 235 89.5 82.3 7. 3 20 99
Arno 39.4 15.3 14.5 23.2 4.5 3.0 1141 73.7 68.5 5.2 22 119
Aur 42.0 8.5 12.6 26.2 6.0 4.7 317 87. 6 78.7 8.9 24 119
Ebon 39.0 8.7 11.9 24.5 7. 0 8.7 469 91.4 74.7 16.7 28 124
Enewetak 44.9 8.4 13.2 24.3 5.7 3.4 296 93.5 86.9 6.5 20 116
Jabat 48.0 4.0 13.3 25.3 8.0 1.3 75 97.4 94.7 2.6 20 121
Jaluit 30.0 35.9 9.7 15.3 5.5 3.5 1409 50.5 45.2 5.3 17 105
Kili 42.4 6.7 13.7 28.0 5.3 3.9 415 86.1 78.9 7. 2 25 120
Kwajalein 36.3 18.8 12.9 23.1 5.9 2.9 9789 64.6 59.8 4.8 21 109
Lae 33.8 14.3 15.8 27.1 6.8 2.3 133 56.5 52.9 3.5 26 108
Lib 47.4 16.7 17. 3 15.4 3.2 0.0 156 90.2 90.2 0.0 29 90
Likiep 43.0 7.9 11. 0 21.1 11. 8 5.3 228 93.2 83.1 10.2 22 100
Majuro 31.0 22.0 13.2 23.7 6.1 4.0 23,156 54.0 47. 8 6.2 23 102
Maloelap 40.5 12.7 16.7 21.3 5.8 3.0 395 77.1 71.7 5.4 22 124
Mejit 41.7 10.9 14.8 21.3 6.5 4.8 230 87. 0 78.0 8.9 22 107
Mili 39.8 15.3 14.7 24.3 3.2 2.6 497 73.8 69.2 4.5 21 121
Namdrik 41.8 10.7 13.7 21.4 8.7 3.7 299 83.4 76.7 6.7 23 108
Namu 36.8 11. 4 15.0 25.1 8.0 3.6 525 67.7 61.7 6.1 26 118
Ujae 41.9 12.9 16.8 21.0 5.5 1.9 310 78.2 74.7 3.4 22 97
Utirik 41.7 8.7 16.7 23.9 7. 2 1.9 264 77. 2 73.8 3.4 24 98
Wotho 45.5 15.9 8.0 21.6 4.5 4.5 88 100.0 90.9 9.1 22 100
Wotje 33.6 30.8 8.8 19.4 4.5 2.9 816 57. 5 52.9 4.6 17 103
Over the years since the first census was conducted
"""

SPOKEN = """Table 3.3.   Languages spoken by age, sex and location, RMI, 2021
 All ages 
over 5
Age 
5–14
Age 
15–29
Age 
30–44
Age 
45–59
Age 
60–74
Age 
75+
Total pop. (number) 36,808 9,636 10,422 8,579 5,522 2,328 321
Speaks Marshallese (%) 96.0 96.3 97. 5 95.6 94.6 93.9 92.2
Speaks other languages (%) 23.9 20.5 24.3 24.7 26.5 26.4 30.1
Urban 28,992 7,125 8,745 6,641 4,406 1,828 247
Speaks Marshallese (%) 95.4 95.7 97. 3 94.8 93.6 92.8 91.1
Speaks other languages (%) 27. 3 24.3 25.7 28.7 29.4 29.2 32.2 
Rural 7,816 2,511 1,677 1,938 1,116 500 74
Speaks Marshallese (%) 98.3 98.1 98.6 98.5 98.3 97. 6 95.9
Speaks other languages (%) 11. 5 9.8 13.3 11.9 11.9 11. 2 10.8
Majuro 20,470 4,785 6,333 4,685 3,120 1,345 202
Speaks Marshallese (%) 94.7 95.4 96.9 93.7 92.4 91.5 89.6
Speaks other languages (%) 28.6 25.9 27. 6 30.0 31.1 31.3 39.1
Kwajalein 8,522 2,340 2,412 1,956 1,286 483 45
Speaks Marshallese (%) 97. 2 96.4 98.3 97.4 96.7 96.5 97. 8
Speaks other languages (%) 24.0 21.0 23.5 24.6 28.1 28.4 21.7
Females 18,025 4,637 5,101 4,317 2,666 1,127 177
Speaks Marshallese (%) 95.1 96.2 97. 6 95.7 95.2 94.0 93.2
Speaks other languages (%) 23.9 21.1 24.7 24.3 25.9 25.3 21.9
Males 18,783 4,999 5,321 4,262 2,856 1,201 144
Speaks Marshallese (%) 97. 0 96.4 97.4 95.5 94.0 93.8 91.0
Speaks other languages (%) 24.0 20.0 24.0 25.0 27.1 27.4 40.3
Overall, percentages of males and females speaking languages
"""


class Kerning(unittest.TestCase):
    def test_a_split_thousand_and_a_split_decimal_are_put_back(self):
        self.assertEqual(mh.tokens("1,14 0 445 26"), ["1,140", "445", "26"])
        self.assertEqual(mh.tokens("57. 0 51.2 7. 3 20"), ["57.0", "51.2", "7.3", "20"])

    def test_a_row_of_the_wrong_width_stops_the_run(self):
        with self.assertRaises(SystemExit):
            mh.counts("1,175 599", 3, "test")


class BasicTables(unittest.TestCase):
    def setUp(self):
        self.read = mh.read_tables([TABLES])

    def test_every_atoll_is_read_and_adds_up(self):
        self.assertEqual(len(self.read["people"]), 25)
        self.assertEqual(self.read["people"]["Majuro"], [23_156, 11_670, 11_486])
        self.assertEqual(self.read["people"]["Arno"][0], 1_141)

    def test_religion_and_ethnicity_count_private_households(self):
        self.assertEqual(self.read["private"]["Jaluit"], 1_058)
        self.assertEqual(sum(self.read["religion"]["Jaluit"].values()), 1_058)
        self.assertEqual(self.read["religion"]["Likiep"]["Roman Catholic"], 162)
        self.assertEqual(self.read["ethnicity"]["Majuro"]["Marshallese"], 21_359)

    def test_a_row_that_does_not_add_up_stops_the_run(self):
        broken = TABLES.replace("2–Ailuk 235 168 1 66", "2–Ailuk 235 168 1 67")
        with self.assertRaises(SystemExit):
            mh.read_tables([broken])

    def test_a_contents_line_is_not_taken_for_the_table(self):
        contents = ("Table 3.  Population by Urban/Rural and atoll by sex - RMI Census 2021 "
                    ".......10\n")
        self.assertEqual(mh.read_tables([contents + TABLES])["people"]["Ebon"][0], 469)


class AnalyticalReport(unittest.TestCase):
    def setUp(self):
        self.people = mh.read_tables([TABLES])["people"]
        self.read = mh.read_report([AGES + SPOKEN], self.people)

    def test_every_peopled_atoll_has_its_printed_median(self):
        self.assertEqual(self.read["medians"]["Ebon"], (28, 124))
        self.assertEqual(self.read["medians"]["Jaluit"], (17, 105))
        self.assertNotIn("Bikini", self.read["medians"])

    def test_languages_for_the_two_atolls_the_report_names(self):
        self.assertEqual(self.read["language"]["Majuro"],
                         {"Marshallese": 94.7, "Other languages": 28.6})
        self.assertEqual(self.read["language"]["Kwajalein"]["Marshallese"], 97.2)

    def test_a_median_row_counting_other_people_stops_the_run(self):
        with self.assertRaises(SystemExit):
            mh.read_report([AGES.replace(" 469 91.4", " 470 91.4") + SPOKEN], self.people)


class Records(unittest.TestCase):
    def setUp(self):
        tables = mh.read_tables([TABLES])
        report = mh.read_report([AGES + SPOKEN], tables["people"])
        self.records = mh.build(tables, report, load_units("MHL", "admin1"),
                                load_units("MHL", "admin2"))

    def test_both_levels_draw_the_same_twenty_two_atolls(self):
        for level in ("admin1", "admin2"):
            self.assertEqual(sum(r["level"] == level for r in self.records), 22)

    def test_an_outer_atoll_says_why_it_has_no_language(self):
        ebon = next(r for r in self.records if r["name"] == "Ebon")
        self.assertEqual(ebon["language"]["status"], "not_available")
        self.assertEqual(ebon["median_age"]["value"], 28)
        self.assertEqual(ebon["sex_ratio"]["value"], 124.4)

    def test_an_atoll_with_boarders_says_who_its_shares_leave_out(self):
        jaluit = next(r for r in self.records if r["name"] == "Jaluit")
        self.assertIn("351", jaluit["religion_note"])


if __name__ == "__main__":
    unittest.main()
