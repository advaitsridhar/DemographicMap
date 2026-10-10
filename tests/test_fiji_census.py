"""Fiji: the 2017 age table and the 2007 Table P01-3, and the guards on reading them.

The age rows are the COD-PS table's own (Kadavu and Lau); Table P01-3 is page
one of the Bureau's PDF as pypdf reads it, its relationship rows other than
the total left out. No network.
"""

import unittest

from scripts.fetch_census import fiji_census as fj
from scripts.fetch_census.oceania_common import load_units

HEADER = ("ADM2_PCODE,ADM2_EN,ADM1_PCODE,ADM1_EN,ADM0_PCODE,ADM0_EN,"
          + ",".join(f"{s}_{lo:02d}_{lo + 4:02d}" for lo in range(0, 95, 5) for s in "MFT")
          + ",M_95Plus,F_95Plus,T_95Plus,M_TL,F_TL,T_TL")
KADAVU = ("FJ304,Kadavu,FJ3,Eastern,FJ,Fiji Islands,772,680,1452,683,671,1354,603,545,1148,"
          "411,294,705,400,252,652,475,390,865,452,393,845,429,332,761,329,247,576,285,193,"
          "478,277,241,518,265,183,448,213,164,377,151,121,272,119,87,206,59,52,111,32,35,67,"
          "13,18,31,0,3,3,0,0,0,5968,4901,10869")
LAU = ("FJ305,Lau,FJ3,Eastern,FJ,Fiji Islands,567,527,1094,658,616,1274,570,501,1071,351,254,"
       "605,276,224,500,332,287,619,336,284,620,325,297,622,255,194,449,278,268,546,319,253,"
       "572,271,216,487,197,142,339,146,128,274,92,86,178,73,74,147,37,43,80,27,23,50,5,5,"
       "10,2,0,2,5117,4422,9539")
TABLE = "\n".join([HEADER, KADAVU, LAU]) + "\n"

P013 = """Table P01-3. Relationship, Ethnicity, and Religion by Province of Enumeration, Fiji: 2007
─────────────────┬─────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬───────┬───────┬─────┬──────┬───────┬──────┬──────┬──────
Relation, Ethnic-│     │      │      │Cakau-│      │      │Lomai-│   Ma-│Nadroga│   Nai-│ Nam-│      │       │      │  Tai-│  Rot-
ity and Religion │Total│    Ba│   Bua│ drove│Kadavu│   Lau│  viti│ cuata│ Navosa│ tasiri│  osi│    Ra│   Rewa│ Serua│  levu│   uma
─────────────────┴─────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴───────┴───────┴─────┴──────┴───────┴──────┴──────┴──────
RELATIONSHIP
   Total . . . .837,271 231,760 14,176 49,344 10,167 10,683 16,253 72,441  58,387 160,760 6,898 29,464 100,995 18,249 55,692 2,002
ETHNICITY
   Total . . . .837,271 231,760 14,176 49,344 10,167 10,683 16,253 72,441  58,387 160,760 6,898 29,464 100,995 18,249 55,692 2,002
Fijian . . . . .475,739  96,852 11,183 35,978  9,964 10,540 14,822 28,197  35,075  93,124 6,159 20,259  62,173 11,138 40,186    89
Indian . . . . .313,801 126,142  2,367  7,929     49     88    494 42,550  22,140  58,496   514  8,888  24,082  5,830 14,212    20
Full/Part-Chines  4,704     884      7    127     17      5     53    197      95     915     6     34   2,130     89    137     8
European . . . .  2,953     876      1    201     12      8     38     62     139     320    10     37   1,068    132     46     3
Part-European. . 10,771   2,400    479  1,479     96      7    284    681     243   1,557    77     61   2,607    517    271    12
Rotuman. . . . . 10,335   1,991     10    129      6     18     68    121     169   2,860    53     48   2,678    150    182 1,852
Other Pacific Is  6,659     868     27  2,598      4      5     33    429     260   1,179    24     53     680    203    295     1
Others . . . . . 12,309   1,747    102    903     19     12    461    204     266   2,309    55     84   5,577    190    363    17
RELIGION
   Total . . . .837,271 231,760 14,176 49,344 10,167 10,683 16,253 72,441  58,387 160,760 6,898 29,464 100,995 18,249 55,692 2,002
Christian. . . .543,588 113,765 11,859 42,478 10,132 10,576 15,864 32,470  37,491 106,937 6,430 20,853  78,347 12,525 41,863 1,998
  Anglican . . .  6,328     739    134    602     14      2    345    659     177   1,542     3    108   1,622    313     55    13
  Apostolic. . .  5,089   1,327     27    310    150     42     41    459     343     782   126    343     661     89    388     1
  Assembly of Go 47,873  13,434    596  2,126    330    281    433  3,250   4,411  10,356   359  1,882   5,573    977  3,794    71
  All Nation Chr 13,294   2,147    128    554    206    177    272    528     596   3,719   218    473   2,593    331  1,351     1
  Baptist. . . .  1,772     555      3     53      7      -     12     46     166     500    32     28     267     11     88     4
  Catholic . . . 76,603  14,026  1,631 12,879    296    365  2,189  4,663   3,248  12,556 3,399  2,331  12,579  2,963  2,776   702
  Christ Mis Flw 14,180   2,641    485  1,034    204    136    243  1,595   1,294   3,511    24    234   1,881    283    615     -
  Church of Chri  1,356     152     21      7      -      7      5     33      14     268     4      3     737      -    104     1
  Gospel . . . .  2,835     983      4    179      2      -     28    223     309     451     2     77     369     26    182     -
  Jehovah's Witn  8,450   2,658     81    461     87     36    196    423     650   1,444    28    202   1,496    263    365    60
  Latter Day Sai  5,126     806      9    350     16      7     38    194     141   1,283     3     48   1,618    114    474    25
  Methodist. . .290,555  56,213  7,864 19,255  8,302  8,945 11,104 16,876  20,782  57,448 1,285 11,471  37,729  5,855 26,452   974
  Penticostal. . 15,326   3,680     67    626      9     41     66    599     717   3,004    22    628   4,959     86    819     3
  Presbyterian .  2,907     952     11    158      2      -      -    387     318     475     4     48     342     63    147     -
  Salvation Army  1,144     429      3     72      -      2      5    103      53     197     -      3     247      8     22     -
  Seventh Day Ad 32,370   7,183    426  2,354    285    459    411    872   2,926   5,741   868  2,157   4,845    553  3,148   142
  United Penteco  1,361     227     22     84      -      7    151    188      68     258     -    110      44      9    193     -
  Other Christia 17,019   5,613    347  1,374    222     69    325  1,372   1,278   3,402    53    707     785    581    890     1
Hindu. . . . . .232,103  92,014  1,847  5,172     20     45    259 32,061  16,388  43,009   316  7,667  17,199  4,901 11,205     -
Sikh . . . . . .  2,548   1,359      -      8      -      -      -     96     164     555     9     41     188     11    117     -
Moslem . . . . . 52,594  23,022    415  1,499      5      3     51  7,279   4,106   9,173   120    854   3,361    524  2,182     -
Other religion .  1,294     240      1     12      3      1      5    195      25     228     -       4     512     42     26     -
No religion. . .  4,249   1,216     51    136      5      3     69    265     200     695    17     43   1,072    232    241     4
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Source: 2007 Census of Fiji, Bureau of Statistics
"""


class TheAgeTable(unittest.TestCase):
    def setUp(self):
        self.rows = fj.age_rows(TABLE, "ADM2_EN", "ADM1_EN")

    def test_a_row_is_read_with_its_sexes_and_groups(self):
        kadavu = self.rows["Kadavu"]
        self.assertEqual((kadavu["total"], kadavu["male"], kadavu["female"]),
                         (10_869, 5_968, 4_901))
        self.assertEqual(kadavu["parent"], "Eastern")
        self.assertEqual(kadavu["groups"][0], (0, 4, 1452))
        self.assertEqual(kadavu["groups"][-1], (95, None, 0))

    def test_its_median_falls_in_the_group_that_holds_the_middle_person(self):
        median = fj.median_from_groups(self.rows["Lau"]["groups"])
        self.assertTrue(20 <= median < 30, median)

    def test_groups_that_do_not_make_the_printed_total_stop_the_run(self):
        with self.assertRaises(SystemExit):
            fj.age_rows(TABLE.replace(",5968,4901,10869", ",5969,4901,10870"),
                        "ADM2_EN", "ADM1_EN")

    def test_sexes_that_do_not_make_a_groups_total_stop_the_run(self):
        with self.assertRaises(SystemExit):
            fj.age_rows(TABLE.replace("772,680,1452", "772,680,1453"), "ADM2_EN", "ADM1_EN")

    def test_a_missing_age_group_stops_the_run(self):
        header = HEADER.replace("M_45_49,F_45_49,T_45_49", "M_45_50,F_45_50,T_45_50")
        with self.assertRaises(SystemExit):
            fj.age_rows("\n".join([header, KADAVU]) + "\n", "ADM2_EN", "ADM1_EN")


class TableP013(unittest.TestCase):
    def setUp(self):
        self.read = fj.read_p013(["cover", P013])

    def test_every_province_is_read_at_its_2007_count(self):
        self.assertEqual(set(self.read), set(fj.PROVINCES))
        self.assertEqual(self.read["Ba"]["total"], 231_760)
        self.assertEqual(self.read["Rotuma"]["total"], 2_002)

    def test_ethnic_groups_carry_todays_names(self):
        ba = self.read["Ba"]["ethnicity"]
        self.assertEqual(ba["Indo-Fijian"], 126_142)
        self.assertEqual(ba["Fijian (iTaukei)"], 96_852)
        self.assertEqual(self.read["Rotuma"]["ethnicity"]["Rotuman"], 1_852)

    def test_denominations_are_kept_and_the_unprinted_counted(self):
        namosi = self.read["Namosi"]["religion"]
        self.assertEqual(namosi["Roman Catholic"], 3_399)
        self.assertEqual(namosi["Hinduism"], 316)
        self.assertNotIn("Christian", namosi)
        self.assertEqual(sum(p["unprinted"] for p in self.read.values()), 895)

    def test_a_figure_read_wrong_stops_the_run(self):
        with self.assertRaises(SystemExit):
            fj.read_p013([P013.replace("96,852 11,183", "96,825 11,183")])

    def test_an_unknown_religion_row_stops_the_run(self):
        with self.assertRaises(SystemExit):
            fj.read_p013([P013.replace("Sikh . . . . . .", "Bahai. . . . . .")])

    def test_a_page_for_one_ethnic_group_is_not_the_table(self):
        with self.assertRaises(SystemExit):
            fj.read_p013([P013.replace("Table P01-3.", "Table P01-3F.")])


def scaled_tables(rows):
    """Every province given Kadavu's age shape at its own 2017 size."""
    provinces = {}
    for division, members in fj.DIVISIONS.items():
        for name in members:
            k = fj.COUNT_2017[name] / rows["Kadavu"]["total"]
            groups = [(lo, hi, round(n * k)) for lo, hi, n in rows["Kadavu"]["groups"]]
            total = sum(n for _, _, n in groups)
            male = round(rows["Kadavu"]["male"] * k)
            provinces[name] = {"parent": division, "groups": groups, "total": total,
                               "male": male, "female": total - male}
    divisions = {}
    for division, members in fj.DIVISIONS.items():
        groups = {}
        for name in members:
            for lo, hi, n in provinces[name]["groups"]:
                groups[(lo, hi)] = groups.get((lo, hi), 0) + n
        divisions[division] = {
            "parent": "", "groups": [(lo, hi, n) for (lo, hi), n in groups.items()],
            "total": sum(provinces[m]["total"] for m in members),
            "male": sum(provinces[m]["male"] for m in members),
            "female": sum(provinces[m]["female"] for m in members)}
    return provinces, divisions


class TheRecords(unittest.TestCase):
    def setUp(self):
        provinces, divisions = scaled_tables(fj.age_rows(TABLE, "ADM2_EN", "ADM1_EN"))
        saved = (fj.NATIONAL_2017, fj.MEDIAN_2017)
        fj.NATIONAL_2017 = sum(u["total"] for u in provinces.values())
        fj.MEDIAN_2017 = fj.median_from_groups(provinces["Kadavu"]["groups"])
        try:
            self.records = fj.build(provinces, divisions, fj.read_p013([P013]),
                                    load_units("FJI", "admin1"), load_units("FJI", "admin2"))
        finally:
            fj.NATIONAL_2017, fj.MEDIAN_2017 = saved
        self.provinces = provinces

    def named(self, level, name):
        return next(r for r in self.records if r["level"] == level and r["name"] == name)

    def test_every_drawn_unit_has_a_record(self):
        self.assertEqual(sum(r["level"] == "admin1" for r in self.records), 4)
        self.assertEqual(sum(r["level"] == "admin2" for r in self.records), 15)

    def test_the_eastern_polygon_carries_kadavu_and_says_so(self):
        eastern, kadavu = self.named("admin1", "Eastern"), self.named("admin2", "Kadavu")
        self.assertEqual(eastern["population"]["value"], self.provinces["Kadavu"]["total"])
        self.assertEqual(eastern["ethnicity"], kadavu["ethnicity"])
        self.assertEqual(eastern["median_age"], kadavu["median_age"])
        self.assertIn("Kadavu alone", eastern["population_note"])

    def test_a_drawn_division_adds_its_provinces_and_leaves_its_population_alone(self):
        central = self.named("admin1", "Central")
        self.assertEqual(central["population"]["status"], "not_available")
        self.assertEqual(central["religion_year"], 2007)
        self.assertIn("Naitasiri, Namosi, Rewa, Serua, Tailevu", central["religion_note"])

    def test_compositions_are_dated_2007_and_ages_2017(self):
        ba = self.named("admin2", "Ba")
        self.assertEqual(ba["ethnicity_year"], 2007)
        self.assertEqual(ba["median_age"]["year"], 2017)
        self.assertEqual(ba["sex_ratio"]["unit"], "males_per_100_females")
        self.assertEqual(ba["ethnicity"][0]["group"], "Indo-Fijian")
        self.assertEqual(ba["language"]["status"], "not_available")
        self.assertIn("1946", ba["language"]["note"])


if __name__ == "__main__":
    unittest.main()
