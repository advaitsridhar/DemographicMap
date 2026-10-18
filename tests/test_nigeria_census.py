"""Nigeria's 2006 Table DS5, as pypdf reads the National Population Commission's Volume IV.

The excerpts below are the volume's own text layer, copied from the runner's
log: every glitch the reader handles is one the volume actually has.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import nigeria_census as n  # noqa: E402

HEAD = ("Table DS5:  Population by Five Year Age Groups and Sex                     127\n"
        "Table DS5: Distribution of Population by Five Year Age\nGroups and Sex\n"
        "Age Groups Total\nSex\nMales Females\n")

# Enugu North: the total is broken over three lines.
ENUGU_NORTH = HEAD + """ENUGU NORTH
TOTAL 242,14
0
118,895 123,245
0 - 4 25,559 13,221 12,338
5 - 9 22,660 11,341 11,319
10 - 14 26,147 12,123 14,024
15 - 19 27,278 12,050 15,228
20 - 24 38,036 16,862 21,174
25 - 29 27,972 13,430 14,542
30 - 34 15,797 7,513 8,284
35 - 39 12,948 6,158 6,790
40 - 44 11,220 5,838 5,382
45 - 49 10,018 5,836 4,182
50 - 54 8,332 4,875 3,457
55 - 59 5,270 3,384 1,886
60 - 64 3,985 2,329 1,656
65 - 69 2,474 1,440 1,034
70 - 74 1,911 1,126 785
75 - 79 959 561 398
80 - 84 846 435 411
85+ 728 373 355
"""

# Kogi: a heading word broken in two above the name, and figures broken at
# the line's end in the total and in the first age group.
KOGI = """Table DS5: Distribution of Population by Five Year Age
Groups and Sex
Age Groups Total
Sex
Males Femal
es
KOGI
TOTAL 115,100 58,864 56,23
6
0 - 4 22,581 11,647 10,93
4
5 - 9 17,731 9,355 8,376
10 - 14 13,216 7,136 6,080
15 - 19 11,597 6,000 5,597
20 - 24 9,962 4,444 5,518
25 - 29 9,397 4,050 5,347
30 - 34 7,518 3,523 3,995
35 - 39 5,604 2,813 2,791
40 - 44 4,904 2,624 2,280
45 - 49 3,281 1,912 1,369
50 - 54 3,136 1,834 1,302
55 - 59 1,235 663 572
60 - 64 1,778 943 835
65 - 69 719 444 275
70 - 74 880 550 330
75 - 79 506 309 197
80 - 84 492 266 226
85+ 563 351 212
"""

# Kebbi: a spreadsheet turned 5-9 and 10-14 into dates.
ALEIRO = HEAD + """ALEIRO
TOTAL 67,078 34,368 32,710
0 - 4 13,382 6,873 6,509
05-Sep 11,575 5,993 5,582
Oct-14 8,002 4,433 3,569
15 - 19 6,633 3,452 3,181
20 - 24 5,487 2,416 3,071
25 - 29 5,289 2,239 3,050
30 - 34 4,315 2,032 2,283
35 - 39 2,981 1,543 1,438
40 - 44 2,755 1,469 1,286
45 - 49 1,539 885 654
50 - 54 1,780 1,033 747
55 - 59 667 437 230
60 - 64 1,135 684 451
65 - 69 360 215 145
70 - 74 548 330 218
75 - 79 164 89 75
80 - 84 283 137 146
85+ 183 108 75
"""

# The Federal Capital Territory: labels without dashes.
ABAJI = HEAD + """ABAJI
TOTAL 58,642 28,860 29,782
0 4 10,769 5,303 5,466
5 9 9,030 4,483 4,547
1014 7,151 3,447 3,704
15 19 6,332 2,885 3,447
20 24 5,054 2,133 2,921
25 29 5,092 2,168 2,924
30 34 3,998 1,960 2,038
35 39 3,216 1,783 1,433
40 44 2,360 1,377 983
45 49 1,572 970 602
50 54 1,304 787 517
55 59 619 359 260
60 64 679 393 286
65 69 382 202 180
70 74 392 227 165
75 79 186 126 60
80 84 231 121 110
85+ 275 136 139
"""

# Babura: the 20-24 row's label is garbled over two lines.
BABURA = HEAD + """BABURA
TOTAL 212,955 106,373 106,582
0 - 4 42,550 21,976 20,574
5 - 9 34,753 18,027 16,726
10 - 14 23,132 12,055 11,077
15 - 19 20,267 9,815 10,452
G23720 -
24
17,598 6,983 10,615
25 - 29 16,299 6,631 9,668
30 - 34 14,153 6,508 7,645
35 - 39 9,524 4,748 4,776
40 - 44 9,800 5,141 4,659
45 - 49 5,371 3,015 2,356
50 - 54 6,776 3,804 2,972
55 - 59 1,858 1,051 807
60 - 64 3,922 2,308 1,614
65 - 69 1,023 590 433
70 - 74 2,530 1,607 923
75 - 79 562 346 216
80 - 84 1,745 1,071 674
85+ 1,092 697 395
"""

# Taraba: people counted in disputed areas, between the state's page of single
# years and its five-year table; and Zing, whose total is not printed.
TARABA_SINGLE = ("Distribution of Population by Single Years of Age and Sex\nTARABA STATE\nAGE\n"
                 "Single Years BOTH SEXES MALE FEMALE\nTOTAL 2,294,800 1,171,931 1,122,869\n"
                 "0 53,346 29,470 23,876\n")
TARABA = """*DISPUTED
AREAS
TOTAL
19,964 10,106 9,858
0 - 4 3,804 1,950 1,854
5 - 9 3,074 1,604 1,470
10 - 14 2,298 1,218 1,080
15 - 19 2,016 1,021 995
20 - 24 1,740 755 985
25 - 29 1,637 679 958
30 - 34 1,291 630 661
35 - 39 920 495 425
40 - 44 846 423 423
45 - 49 535 290 245
50 - 54 558 340 218
55 - 59 230 118 112
60 - 64 361 196 165
65 - 69 186 86 100
70 - 74 185 108 77
75 - 79 55 30 25
80 - 84 132 94 38
85+ 96 69 27
""" + HEAD + """TARABA
TOTAL 2,294,800 1,171,931 1,122,869
0 - 4 428,318 220,428 207,890
5 - 9 356,962 185,884 171,078
10 - 14 263,096 138,978 124,118
15 - 19 235,034 117,621 117,413
20 - 24 204,760 89,971 114,789
25 - 29 193,470 85,346 108,124
30 - 34 152,377 73,552 78,825
35 - 39 114,092 60,512 53,580
40 - 44 98,195 53,549 44,646
45 - 49 64,897 38,621 26,276
50 - 54 58,772 33,936 24,836
55 - 59 26,721 16,237 10,484
60 - 64 33,873 19,280 14,593
65 - 69 14,934 8,576 6,358
70 - 74 18,875 11,213 7,662
75 - 79 8,538 5,303 3,235
80 - 84 10,870 6,176 4,694
85+ 11,016         6,748 4,268
""" + HEAD + """ZING
TOTAL  64,759 62,926
0 - 4 22,854 11,723 11,131
5 - 9 20,049 10,428 9,621
10 - 14 14,958 7,959 6,999
15 - 19 13,237 6,709 6,528
20 - 24 11,358 4,976 6,382
25 - 29 10,763 4,674 6,089
30 - 34 8,304 3,931 4,373
35 - 39 6,339 3,269 3,070
40 - 44 5,348 2,823 2,525
45 - 49 3,719 2,174 1,545
50 - 54 3,296 1,820 1,476
55 - 59 1,571 917 654
60 - 64 1,948 1,047 901
65 - 69 935 509 426
70 - 74 1,144 678 466
75 - 79 571 324 247
80 - 84 625 362 263
85+ 666 436 230
"""

VOL3_KADUNA = """21
Map Showing LGAs in Kaduna State
2006 CENSUS POPULATION DISTRIBUTION BY LGA
KADUNA STATE
S/No. Local Government AREA Senatorial District Land Size Klm2 Male Female Both Sexes
12 KAJURU B 2904.298 54506 55304 109810
13 KAURA C 499.102 88565 86061 174626
14 KAURU C 2545.844 111119 110157 221276
18 MAKARFI A 562.39 73292 73282 146574
19 SABON-GARI A 273.779 149111 142247 291358
 KADUNA STATE  45,711.188 3,090,438 3,023,065 6,113,503
"""


def one(text):
    tables = n.parse_tables([text])
    assert len(tables) == 1, [t["name"] for t in tables]
    return tables[0]


class ParseTest(unittest.TestCase):
    def test_total_broken_over_lines(self):
        t = one(ENUGU_NORTH)
        self.assertEqual(t["name"], "ENUGU NORTH")
        self.assertEqual(t["total"], (242140, 118895, 123245))
        self.assertEqual(n.problems(t), [])
        self.assertEqual(n.median(t["groups"]), 22.6)

    def test_heading_word_broken_and_figures_mended(self):
        t = one(KOGI)
        self.assertEqual(t["name"], "KOGI")
        self.assertEqual(t["total"], (115100, 58864, 56236))
        self.assertEqual(t["groups"][0], (0, 4, 22581, 11647, 10934))
        self.assertEqual(n.problems(t), [])

    def test_date_labels(self):
        t = one(ALEIRO)
        self.assertEqual(n.problems(t), [])
        self.assertNotIn("misprints", t)
        self.assertEqual(t["groups"][1][:3], (5, 9, 11575))

    def test_labels_without_dashes(self):
        t = one(ABAJI)
        self.assertEqual(n.problems(t), [])
        self.assertNotIn("misprints", t)

    def test_garbled_label_read_by_position(self):
        t = one(BABURA)
        self.assertEqual(n.problems(t), [])
        self.assertEqual(t["groups"][4], (20, 24, 17598, 6983, 10615))
        self.assertEqual(t["misprints"], ["24 for 20-24"])

    def test_disputed_areas_and_restored_total(self):
        nigeria = ("Distribution of Population by Single Years of Age and Sex\nNIGERIA\n"
                   "TOTAL 1 1 0\n")
        five = "Total Males Females\nNIGERIA\nTOTAL 140,431,790 71,345,488 69,086,302\n"
        tables = n.parse_tables([nigeria, five, TARABA_SINGLE, TARABA])
        book = n.organise(tables)
        self.assertEqual(book["nation"]["total"], n.NATIONAL)
        (state,) = book["states"]
        self.assertEqual(state["table"]["name"], "TARABA")
        names = [(a["name"], bool(a.get("unplaced"))) for a in state["areas"]]
        self.assertEqual(names, [("*DISPUTED AREAS", True), ("ZING", False)])
        zing = state["areas"][1]
        self.assertEqual(zing["total"], (127685, 64759, 62926))
        self.assertEqual(n.problems(zing), [])

    def test_volume_three_names_and_supplies_missing_area(self):
        vol3 = n.parse_vol3([VOL3_KADUNA])
        self.assertEqual(vol3["kaduna"][1], ("KAURA", 88565, 86061, 174626))
        mislabelled = {"name": "MAKARFI", "total": (291358, 149111, 142247), "groups": []}
        makarfi = {"name": "MAKARFI", "total": (146574, 73292, 73282), "groups": []}
        others = [{"name": nm, "total": t, "groups": []}
                  for nm, t in (("KAJURU", (109810, 54506, 55304)),
                                ("KAURU", (221276, 111119, 110157)))]
        book = {"states": [{"table": {"name": "KADUNA STATE"},
                            "areas": [*others, makarfi, mislabelled]}]}
        said = n.name_from_vol3(book, vol3)
        self.assertEqual(mislabelled["vol3"], "SABON-GARI")
        self.assertEqual(makarfi["vol3"], "MAKARFI")
        kaura = [a for a in book["states"][0]["areas"] if a.get("from_vol3")]
        self.assertEqual([(a["name"], a["total"]) for a in kaura],
                         [("KAURA", (174626, 88565, 86061))])
        self.assertTrue(any("SABON-GARI" in line for line in said))
        fields = n.fields(kaura[0], None, "note")
        self.assertEqual(fields["sex_ratio"]["value"], 102.9)
        self.assertEqual(fields["median_age"]["status"], "not_available")


class NameTest(unittest.TestCase):
    def test_keys(self):
        self.assertIn("ibadannortheast", n.keys("IBADAN CENTRAL [IBADAN NORTH EAST]"))
        self.assertIn("abujamunicipal", n.keys("ABUJA MUNICIPAL [AMAC]"))
        self.assertEqual(n.key("Aba North LGA"), "abanorth")
        self.assertEqual(n.state_key("FCT ABUJA"), "abujafederalcapitalterritory")

    def test_notes_name_the_census_spelling(self):
        a = {"name": "EGBADO NORTH", "vol3": "EGBADO NORTH"}
        self.assertEqual(n.area_note(a, "Yewa North"),
                         "The 2006 census's count for this area, which it names Egbado North.")
        b = {"name": "OBIO/AKPOR", "vol3": None}
        self.assertEqual(n.area_note(b, "Obio/Akpor"), "The 2006 census's count for Obio/Akpor.")

    def test_aliases_are_census_spellings(self):
        for (state, drawn), census in n.ALIASES.items():
            self.assertIn(state, n.STATE_KEYS)
            self.assertNotEqual(drawn, census)


class StateTest(unittest.TestCase):
    """A state carries the census's count, sex ratio and median age; Cross
    River's are its table less Bakassi's."""

    TABLE = {"name": "LAGOS", "total": (400, 210, 190),
             "groups": [(0, 4, 160, 85, 75), (5, 9, 120, 62, 58), (10, 14, 80, 42, 38),
                        (15, 19, 40, 21, 19)] + [(a, a + 4, 0, 0, 0) for a in range(20, 85, 5)]
             + [(85, None, 0, 0, 0)]}
    BAKASSI = {"name": "BAKASSI", "total": (40, 24, 16),
               "groups": [(0, 4, 20, 12, 8), (5, 9, 10, 6, 4), (10, 14, 10, 6, 4)]
               + [(a, a + 4, 0, 0, 0) for a in range(15, 85, 5)] + [(85, None, 0, 0, 0)]}

    def test_the_count_and_the_figures(self):
        f = n.state_fields(self.TABLE, None, "lagos", 0, None, {})
        self.assertEqual(f["population"]["value"], 400)
        self.assertEqual(f["population"]["year"], 2006)
        self.assertEqual(f["population_note"], "The 2006 census's count for Lagos State.")
        self.assertEqual(f["sex_ratio"]["value"], 110.5)
        self.assertEqual(f["median_age"]["value"], 6.7)
        self.assertEqual(f["sources"][0]["field"], "population/sex_ratio/median_age")
        self.assertNotIn("sex_ratio_note", f)
        fct = n.state_fields(dict(self.TABLE, name="FCT ABUJA"), None,
                             "abujafederalcapitalterritory", 0, None, {})
        self.assertEqual(fct["population_note"],
                         "The 2006 census's count for the Federal Capital Territory.")

    def test_what_the_count_includes_rides_on_every_figure(self):
        f = n.state_fields(dict(self.TABLE, name="TARABA"), None, "taraba", 19_964, None, {})
        for note in ("population_note", "sex_ratio_note"):
            self.assertIn("19,964 people", f[note])
        self.assertTrue(f["median_age_note"].startswith(n.MEDIAN_NOTE))
        self.assertIn("19,964 people", f["median_age_note"])

    def test_cross_river_less_bakassi(self):
        table = dict(self.TABLE, name="CROSS RIVER")
        f = n.state_fields(table, None, "crossriver", 0, self.BAKASSI, {})
        self.assertEqual(f["population"]["value"], 360)
        self.assertEqual(f["sex_ratio"]["value"], round(100 * 186 / 174, 1))
        self.assertIn("less Bakassi local government area, whose 40 people",
                      f["population_note"])
        self.assertIn("24 men and 16 women", f["sex_ratio_note"])
        self.assertIn("less Bakassi", f["median_age_note"])
        # The groups are subtracted one by one: the median moves.
        self.assertEqual(f["median_age"]["value"], n.median(n.without(table, self.BAKASSI)
                                                           ["groups"]))
        self.assertNotEqual(f["median_age"]["value"], 6.7)

    def test_bakassi_that_does_not_add_up_stops_the_run(self):
        with self.assertRaises(SystemExit):
            n.state_fields(dict(self.TABLE, name="CROSS RIVER"), None, "crossriver", 0,
                           self.BAKASSI, {id(self.BAKASSI): ["men and women do not add up"]})


if __name__ == "__main__":
    unittest.main()
