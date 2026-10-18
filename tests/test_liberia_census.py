"""Liberia's 2022 census tables, as the runner reads LISGIS's two reports.

The page texts below are copied from the runner's logs of the Internet
Archive's captures, as the words' positions put them back together
(probe_pdf --layout).
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import liberia_census as lb  # noqa: E402

FINAL_PAGE_72 = """AAPPPPEENNDDIIXX
##
Appendix A: Tables for Charts
Table A1: Population Trend (1962–2022)
Index 1962 1974 1984 2008 2022
Population 1,016,443 1,503,368 2,101,628 3,476,608 5,250,187
Population Change - 486,925 598,260 1,387,444 1,773,579
Average Annual Increase - 40,577 59,826 57,810 138,745
Percentage Increase - 47.9 39.7 65.5 51.0
Annual Rate Of Growth - 3.3 3.4 2.1 3.0
Table A2: Distribution of Regular Household Population and Non-Household Population by Sex
Regular Institutional Floating / Homeless Total
Number Regular Number Institutional Number Floating/ Number
Homeless
Liberia 5,178,484 98.6 50,223 1.0 21,480 0.4 5,250,187
Male 2,599,721 98.3 28,499 1.1 15,807 0.6 2,644,027
Female 2,578,763 98.9 21,724 0.8 5,673 0.2 2,606,160
Table A3: Distribution of the Population by Sex and County
Total Male Percent Female Percent
Liberia 5,250,187 2,644,027 50.4 2,606,160 49.6
Bomi 133,705 68,574 51.3 65,131 48.7
Bong 467,561 235,208 50.3 232,353 49.7
Gbarpolu 95,995 51,121 53.3 44,874 46.7
Grand Bassa 293,689 150,280 51.2 143,409 48.8
Grand Cape Mount 178,867 96,757 54.1 82,110 45.9
Grand Gedeh 216,692 115,295 53.2 101,397 46.8
Grand Kru 109,342 56,999 52.1 52,343 47.9
Lofa 367,376 183,100 49.8 184,276 50.2
Margibi 304,946 152,699 50.1 152,247 49.9
Maryland 172,587 86,867 50.3 85,720 49.7
Montserrado 1,920,965 942,559 49.1 978,406 50.9
Nimba 621,841 312,018 50.2 309,823 49.8
Rivercess 90,819 47,717 52.5 43,102 47.5
River Gee 124,653 65,471 52.5 59,182 47.5
Sinoe 151,149 79,362 52.5 71,787 47.5
72
2022 Liberia Population and Housing Census
[229 words in 37 rows]
"""

FINAL_PAGE_75 = """Table A7: Distribution of the Population by Sex and Ethnic Affiliation
Total Male Female Percent
Number Number
Liberia 5,250,187 2,644,027 2,606,160 100
Bassa 714,035 356,735 357,300 13.6
Belle 36,536 18,606 17,930 0.7
Dey 16,070 8,203 7,867 0.3
Gbandi 154,335 76,508 77,827 2.9
Gio 413,772 207,389 206,383 7.9
Gola 199,593 101,425 98,168 3.8
Grebo 517,194 258,583 258,611 9.9
Kpelle 1,062,102 525,667 536,435 20.2
Kissi 227,654 112,796 114,858 4.3
Krahn 238,514 122,611 115,903 4.5
Kru 286,922 142,738 144,184 5.5
Lorma 253,728 123,712 130,016 4.8
Mandingo 220,168 117,939 102,229 4.2
Mano 377,436 187,870 189,566 7.2
Mende 87,972 47,130 40,842 1.7
Sapo 55,011 27,889 27,122 1.0
Vai 200,725 101,303 99,422 3.8
Other Liberian Ethnic Group 21,949 11,808 10,141 0.4
Table A8: Distribution of the Population Density by County (2008 & 2022)
Population Surface area Density
(km2)
2008 2022 2008 2022
Liberia 3,476,608 5,250,187 37,482 92.8 140.1
Bomi 84,119 133,705 750 112.2 178.3
Bong 333,481 467,561 3,387 98.5 138
Gbarpolu 83,388 95,995 3,741 22.3 25.7
Grand Bassa 221,693 293,689 3,064 72.4 95.9
Grand Cape Mount 127,076 178,867 1,993 63.8 89.7
Grand Gedeh 125,258 216,692 4,048 30.9 53.5
Grand Kru 57,913 109,342 1,504 38.5 72.7
Lofa 276,863 367,376 3,854 71.8 95.3
Margibi 209,923 304,946 1,010 207.8 301.9
Maryland 135,938 172,587 887 153.3 194.6
Montserrado 1,118,241 1,920,965 737 1517.3 2606.5
Nimba 462,026 621,841 4,460 103.6 139.4
Rivercess 71,509 90,819 2,160 33.1 42
River Gee 66,789 124,653 1,974 33.8 63.1
Sinoe 102,391 151,149 3,914 26.2 38.6
FINAL RESULTS 75
[241 words in 43 rows]
"""

FINAL_PAGE_84 = """APPENDIX
#
Appendix B: District Tables
Table B1: Population Distribution by County, Administrative District, and Sex
Total Male Female
Bomi County 133,705 68,574 65,131
Klay 25,720 13,238 12,482
Suehn Mecca 16,219 8,577 7,642
Senjeh 52,740 26,905 25,835
Dowein 28,371 14,495 13,876
Tehr 10,655 5,359 5,296
Table B2: Population Distribution by County, Administrative District, and Sex
Total Male Female
Gbarpolu County 95,995 51,121 44,874
Kongba 11,508 6,208 5,300
Belleh 15,214 7,980 7,234
Bokomu 13,684 7,257 6,427
Bopolu 23,758 12,619 11,139
Gbarma 13,845 7,544 6,301
Table B3: Population Distribution by County, Administrative District, and Sex
Total Male Female
Grand Cape Mount County 178,867 96,757 82,110
Garwula 33,403 17,072 16,331
Golakonneh 45,798 25,489 20,309
Porkpa 51,131 28,980 22,151
Commonwealth 14,057 7,138 6,919
Robertsport
Tewor 34,478 18,078 16,400
Gounwolaila 17,986 9,513 8,473
84
2022 Liberia Population and Housing Census
[135 words in 31 rows]
"""

FINAL_PAGE_85 = """Table B4: Population Distribution by County, Administrative District, and Sex
Total Male Female
Grand Bassa County 293,689 150,280 143,409
District Number 1 (Dianblae) 30,223 16,003 14,220
District Number 2 (Glarkon) 32,565 16,957 15,608
St. John River City 14,273 7,446 6,827
Neekreen 62,883 31,193 31,690
Commonwealth 35,740 17,719 18,021
District Number 3 (Wee) 62,421 31,965 30,456
District Number 4 (Kpaoegbarn) 41,162 21,606 19,556
Table B5: Population Distribution by County, Administrative District, and Sex
Total Male Female
Margibi County 304,946 152,699 152,247
Farmington 54,257 27,507 26,750
Gibi 15,380 7,837 7,543
Kakata 123,840 61,873 61,967
Mambahn Kabah 37,787 18,903 18,884
Kabah Administrative 73,682 36,579 37,103
Gounwolaila 17,986 9,513 8,473
Table B6: Population Distribution by County, Administrative District, and Sex
Total Male Female
Montserrado County 1,920,965 942,559 978,406
Careysburg 55,284 27,611 27,673
West Point Township 30,847 15,915 14,932
St. Paul River 172,384 85,174 87,210
Todee 49,361 25,754 23,607
Borough of New Kru Town 71,739 35,724 36,015
Gardnersville Township 127,566 62,270 65,296
Barnersville Township 65,493 31,254 34,239
Lousana Township 26,057 13,033 13,024
Paynesville Township 617,492 298,858 318,634
Congo Town Township 91,632 44,161 47,471
New georgia Township 99,845 49,017 50,828
Caldwell Township 112,166 54,055 58,111
Greater Monrovia 161,891 81,659 80,232
Garglohn Township 126,281 63,432 62,849
Johnsonville Township 112,927 54,642 58,285
FINAL RESULTS 85
[207 words in 38 rows]
"""

THEMATIC_PAGE_39 = """Thematic report | Population size, distribution and structure 39
Table 4.1: Population by ethnic groups and county, 2022
Grand
Grand Grand Grand River River
Ethnic group Bomi Bong Gbarpolu Cape Lofa Margibi Maryland Montserrado Nimba Sinoe Total
Bassa Gedeh Kru Cess Gee
Mount
Bassa 0.6 2.3 0.2 31.9 0.6 0.5 0.1 0.1 9.7 0.3 41.4 0.9 10.8 0.1 0.7 100.0
Belle 2.1 5.1 32.4 3.5 1.8 1.5 0.4 0.8 5.9 0.4 43.4 1.0 0.6 0.3 1.0 100.0
Dey 38.1 0.9 1.2 0.9 3.0 1.3 0.3 1.0 3.8 0.3 46.6 1.3 0.1 0.2 1.0 100.0
Gbandi 1.0 1.0 1.8 0.4 1.0 0.3 0.1 55.2 4.6 0.1 33.3 0.8 0.1 0.1 0.2 100.0
Gio 0.4 0.6 0.6 0.4 0.5 0.8 0.5 0.1 2.5 0.1 21.4 70.8 0.3 0.5 0.5 100.0
Gola 31.9 0.7 6.6 0.3 21.7 0.3 0.3 0.1 2.0 0.3 34.5 0.6 0.1 0.4 0.2 100.0
Grebo 0.5 0.8 0.2 0.6 0.3 2.3 12.8 0.1 1.6 27.4 29.0 0.6 0.1 21.2 2.5 100.0
Kpelle 1.9 36.6 4.4 3.3 0.8 0.4 0.1 3.0 12.6 0.2 35.0 1.1 0.2 0.1 0.4 100.0
Kissi 3.2 1.5 0.8 1.3 1.7 1.0 0.2 42.0 6.2 0.2 40.4 0.7 0.2 0.1 0.4 100.0
Krahn 0.2 0.2 0.2 0.2 0.2 69.2 0.3 0.1 1.7 0.4 20.4 5.3 0.1 0.4 1.0 100.0
Kru 0.5 0.5 0.1 1.1 0.8 0.7 11.4 0.3 1.7 5.2 48.6 0.4 1.3 0.5 26.8 100.0
Lorma 1.2 3.5 1.0 0.8 0.8 0.5 0.1 33.0 6.3 0.2 50.9 1.1 0.2 0.1 0.4 100.0
Mandingo 1.5 5.4 1.5 1.2 2.3 2.8 0.3 16.0 2.9 0.9 60.6 2.8 0.2 0.6 1.0 100.0
Mano 0.3 3.7 0.2 0.8 0.3 0.4 0.2 0.1 2.5 0.1 21.6 69.2 0.2 0.1 0.3 100.0
Mende 2.3 1.0 3.1 0.8 27.7 0.3 0.1 28.1 2.9 0.1 31.8 1.0 0.2 0.1 0.5 100.0
Sapo 0.2 0.1 0.1 0.2 1.2 5.2 0.1 0.1 0.7 0.4 27.0 0.2 0.1 0.1 64.2 100.0
Vai 5.8 1.2 0.6 0.6 34.5 0.2 0.1 0.2 2.7 0.1 52.9 0.4 0.2 0.1 0.4 100.0
Other Liberian 0.3 0.6 0.4 3.0 1.2 1.2 0.2 0.9 1.9 1.5 55.5 32.3 0.2 0.2 0.7 100.0
ethnic group
Other African 1.6 5.0 1.9 4.3 4.0 5.8 1.5 4.8 3.5 3.6 50.3 6.7 1.3 2.9 2.7 100.0
tribe
[371 words in 28 rows]
"""

THEMATIC_PAGE_41 = """Thematic report | Population size, distribution and structure 41
Figure 4.1: Religious affiliation, 2008 and 2022
2008 2022
Christian 85.6 Christian 84.9
Islam 12.2 Islam 12.0
Traditional African Religion 0.6 Traditional African Religion 0.5
Other religion 00..22 Other religion 0.1
No religion 1.5 No religion 2.6
0.0 20.0 40.0 60.0 80.0 100.0 0.0 20.0 40.0 60.0 80.0 100.0
Table 4.3 shows that the proportion of the population areas (2.0 per cent). In 15 out of the 16 counties,
which practice the Christian religion in urban areas Christianity dominates the religious groups. The
(85.5 per cent) is higher than those in rural (84.2 proportion ranges from 96.5 per cent in River Cess
per cent) by 1.3 percentage points. Similarly, the County to 58.5 per cent in Bomi County. The only
proportions of Muslims in urban areas (12.3 per cent) exception county was the Grand Cape, where a higher
are higher than those in rural areas (11.6 per cent). proportion of the population were Muslims (73.1 per
The population which indicated to have no religion cent).
is higher in rural areas (3.2 per cent) than urban
Table 4.3: Religious affiliation by type of residence and county, 2022
Traditional
County Christian Muslim African Other religion No religion Total
Religion
Total Country 84.9 12.0 0.5 0.1 2.6 100.0
Urban 85.5 12.3 0.1 0.1 2.0 100.0
Rural 84.2 11.6 0.9 0.1 3.2 100.0
Bomi 58.5 39.4 0.1 0.0 2.0 100.0
Bong 93.8 3.3 0.4 0.0 2.4 100.0
Grand Bassa 95.9 1.4 0.4 0.1 2.2 100.0
Grand Cape Mount 24.6 73.1 0.1 0.1 2.2 100.0
Grand Gedeh 91.1 5.0 0.7 0.2 3.0 100.0
Grand Kru 94.6 1.3 0.9 0.1 3.1 100.0
Lofa 64.6 30.3 1.8 0.0 3.2 100.0
Margibi 94.7 3.5 0.1 0.0 1.6 100.0
Maryland 94.8 1.9 0.6 0.0 2.7 100.0
Montserrado 84.6 13.3 0.1 0.1 2.0 100.0
Nimba 92.7 1.2 1.5 0.1 4.6 100.0
River Cess 96.5 1.1 0.1 0.0 2.3 100.0
[318 words in 36 rows]
"""

THEMATIC_PAGE_42 = """Thematic report | Population size, distribution and structure 42
Traditional
County Christian Muslim African Other religion No religion Total
Religion
Sinoe 95.0 2.3 0.3 0.1 2.4 100.0
River Gee 94.3 2.1 0.4 0.0 3.2 100.0
Gbarpolu 78.9 18.4 0.3 0.0 2.4 100.0
Total 84.9 12.0 0.5 0.1 2.6 100.0
4.5 Nationality Liberians had decreased significantly. This decline
may be due to improved stability and economic
Figure 4.2 shows that the proportion of Liberians conditions in neighbouring countries, leading to the
increased from 95.4 per cent in 1984 to 98.0 per cent return of many migrants to their home countries.
in 2008. Furthermore, it slightly increased to a peak The 2022 data shows a further slight decrease in the
of 98.1 per cent in 2022. The proportion of the non- proportion of non-Liberians. This continued decline
Liberians has fallen to 2.7 percentage points between suggests that Liberia has become more homogenous
1984 and 2022. By 2008, the percentage of non- in terms of nationality over the past few decades.
Figure 4.2: Population by nationality, 1984, 2008 and 2022
Liberians Non-Liberians
Percent
120.0
98.0
95.4 98.1
100.0
80.0
60.0
40.0
20.0
4.6
2.0 1.9
0.0
1984 2008 2022
Year
The proportions of the Liberian population increased areas (2.9 per cent) is more than three times (3.2)
from 95.4 per cent in 1984 to 98 per cent in 2008, higher than their counterparts in rural (0.8 per cent),
before hitting a peak of 98.1 per cent in 2022. The The higher proportions of non-Liberians residing in
non-Liberian population in 2022 constitute about 2 urban areas may be for employment, easy access to
per cent. The proportion of non-Liberians in urban facilities such as education, health, transport, etc.
[284 words in 37 rows]
"""

THEMATIC_PAGE_59 = """Thematic report | Population size, distribution and structure 59
Appendix 4a: Distribution of population by age, sex and residence - Bomi
Urban Rural Total
Age
Male Female Total Male Female Total Male Female Total
0-4 1,874 1,730 3,604 5,677 5,644 11,321 7,551 7,374 14,925
5-9 2,040 1,949 3,989 6,407 5,459 11,866 8,447 7,408 15,855
10-14 2,181 2,243 4,424 6,075 4,739 10,814 8,256 6,982 15,238
15-19 2,295 2,195 4,490 5,134 5,259 10,393 7,429 7,454 14,883
20-24 1,882 2,002 3,884 4,347 5,387 9,734 6,229 7,389 13,618
25-29 1,313 1,449 2,762 3,275 3,623 6,898 4,588 5,072 9,660
30-34 1,359 1,371 2,730 4,052 4,168 8,220 5,411 5,539 10,950
35-39 1,031 1,066 2,097 2,945 3,213 6,158 3,976 4,279 8,255
40-44 1,150 907 2,057 3,791 3,246 7,037 4,941 4,153 9,094
45-49 623 559 1,182 2,111 1,902 4,013 2,734 2,461 5,195
50-54 593 441 1,034 2,522 1,831 4,353 3,115 2,272 5,387
55-59 284 187 471 1,217 812 2,029 1,501 999 2,500
60-64 309 253 562 1,295 1,070 2,365 1,604 1,323 2,927
65-69 164 132 296 745 591 1,336 909 723 1,632
70-74 111 127 238 765 556 1,321 876 683 1,559
75-79 63 42 105 306 317 623 369 359 728
80+ 126 115 241 512 546 1,058 638 661 1,299
Total 17,398 16,768 34,166 51,176 48,363 99,539 68,574 65,131 133,705
[214 words in 23 rows]
"""


class LiberiaTest(unittest.TestCase):
    def test_counties(self):
        counties = lb.read_counties([FINAL_PAGE_72])
        self.assertEqual(counties["liberia"], lb.NATIONAL)
        self.assertEqual(counties["bomi"], (133_705, 68_574, 65_131))
        self.assertEqual(counties[lb.key("River Cess")], (90_819, 47_717, 43_102))

    def test_a_name_may_hold_a_figure(self):
        self.assertEqual(lb.rows("Karluway Number 1 12,345 6,000 6,345", 3),
                         [("Karluway Number 1", [12_345.0, 6_000.0, 6_345.0])])
        self.assertEqual(lb.key("District Number 1 (Dianblae)"), "no1")

    def test_districts_and_the_row_printed_under_two_wrong_counties(self):
        districts = lb.read_districts([FINAL_PAGE_84, FINAL_PAGE_85])
        self.assertIn(("Commonwealth Robertsport", (14_057, 7_138, 6_919)),
                      districts["grandcapemount"]["rows"])
        said = lb.place_strays(districts)
        gounwolaila = ("Gounwolaila", (17_986, 9_513, 8_473))
        self.assertIn(gounwolaila, districts["gbarpolu"]["rows"])
        self.assertNotIn(gounwolaila, districts["grandcapemount"]["rows"])
        self.assertNotIn(gounwolaila, districts["margibi"]["rows"])
        self.assertEqual(len(said), 2)
        for c in ("gbarpolu", "grandcapemount", "margibi"):
            made = tuple(sum(t[i] for _, t in districts[c]["rows"]) for i in range(3))
            self.assertEqual(made, districts[c]["total"])
        # Grand Bassa prints seven districts, 14,422 people short of its total.
        d = districts["grandbassa"]
        self.assertEqual(d["total"][0] - sum(t[0] for _, t in d["rows"]), 14_422)

    def test_ages_and_median(self):
        ages = lb.read_ages([THEMATIC_PAGE_59])
        groups = ages["bomi"]
        self.assertEqual(len(groups), 17)
        self.assertEqual(tuple(sum(g[i] for g in groups) for i in (2, 3, 4)),
                         (133_705, 68_574, 65_131))
        self.assertEqual(lb.median(groups), 22.2)

    def test_religion_over_two_pages(self):
        religion = lb.read_religion([THEMATIC_PAGE_41, THEMATIC_PAGE_42])
        self.assertEqual(len(religion), 15)
        self.assertEqual(religion["grandcapemount"]["Muslim"], 73.1)
        self.assertEqual(religion["gbarpolu"]["Christian"], 78.9)

    def test_ethnic_composition_from_the_spread_and_the_national_counts(self):
        counties = lb.read_counties([FINAL_PAGE_72])
        shares, other_african = lb.ethnic_shares(lb.read_ethnic_spread([THEMATIC_PAGE_39]),
                                                 lb.read_ethnic_counts([FINAL_PAGE_75]),
                                                 counties)
        self.assertEqual(other_african, 155971)
        # 34.5% of the 200,725 Vai, over Grand Cape Mount's 178,867 people.
        self.assertAlmostEqual(shares["grandcapemount"]["Vai"], 34.5 * 200_725 / 178_867, 6)
        for c, groups in shares.items():
            self.assertLess(abs(sum(groups.values()) - 100), 3, c)

    def test_district_fields(self):
        f = lb.district_fields("Klay", (25_720, 13_238, 12_482), "Bomi County", None)
        self.assertEqual(f["population"]["value"], 25_720)
        self.assertEqual(f["sex_ratio"]["value"], 106.1)
        gap = lb.district_fields("Kpi", None, "Grand Kru County", "why")
        self.assertEqual(gap["population"]["note"], "why")
        self.assertIn("by county, not by district", gap["religion"]["note"])
        # Every reason cites the publication it rests on.
        cited = {s["field"]: s["name"] for s in gap["sources"]}
        self.assertIn("Thematic Report", cited["median_age/religion/ethnicity"])
        self.assertIn("Appendix B", cited["population/sex_ratio"])

    def test_a_district_further_from_2008_than_a_population_moves(self):
        f = lb.district_fields("Potupo", (31_533, 16_390, 15_143), "River Gee County", None,
                               then=7_337)
        self.assertIn("4.3 times the 2008 census's 7,337", f["population_note"])
        self.assertIn("rise of 11.0% a year", f["population_note"])
        self.assertTrue(any(s["field"] == "population note" and s["url"] == lb.STATOIDS
                            for s in f["sources"]))
        down = lb.change_note("Gwelekpoken", "Maryland County", 10_060, 4_366)
        self.assertIn("43% of the 2008 census's 10,060", down)
        self.assertIn("fall of 5.8% a year", down)
        # Within what a population does: the plain note, and no 2008 source.
        f = lb.district_fields("Harper", (53_091, 26_752, 26_339), "Maryland County", None,
                               then=38_024)
        self.assertEqual(f["population_note"], "The 2022 census's count for Harper, in Maryland "
                                               "County.")
        self.assertFalse(any(s["field"] == "population note" for s in f["sources"]))

    def test_owensgrove_is_the_county_less_its_printed_districts(self):
        districts = lb.read_districts([FINAL_PAGE_85])
        d = districts["grandbassa"]
        short = tuple(d["total"][i] - sum(t[i] for _, t in d["rows"]) for i in range(3))
        self.assertEqual(short, (14_422, 7_391, 7_031))
        f = lb.district_fields("Owensgrove", short, "Grand Bassa County", None, note="n")
        self.assertEqual(f["population"]["value"], 14_422)
        self.assertEqual(f["sex_ratio"]["value"], 105.1)
        self.assertEqual(f["population_note"], "n")

    def test_printed_names_lose_a_kept_line_break(self):
        page = ("Table B11: Population Distribution by County, Administrative District, and Sex\n"
                "Total Male Female\nMaryland County 172,587 86,867 85,720\n"
                "Pleebo/ Sodoken 85,287 42,249 43,038\n")
        rows = lb.read_districts([page])["maryland"]["rows"]
        self.assertEqual(rows, [("Pleebo/Sodoken", (85_287, 42_249, 43_038))])

    def test_the_2008_list(self):
        rows = "".join(f"<tr><td>D{i}</td><td>LR.BG.{chr(65 + i // 26)}{chr(65 + i % 26)}</td>"
                       f"<td>{n:,}</td></tr>" for i, n in enumerate([25_563] * 135 + [25_603]))
        got = lb.read_2008(f"<table><tr><th>District</th><th>HASC</th><th>Population</th></tr>"
                           f"{rows}</table>")
        self.assertEqual(len(got["bong"]), 136)
        with self.assertRaises(SystemExit):
            lb.read_2008(f"<table>{rows[:-40]}</table>")


if __name__ == "__main__":
    unittest.main()
