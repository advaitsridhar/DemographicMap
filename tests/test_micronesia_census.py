"""Micronesia: the census workbooks' layouts, cut down to a few rows. No network.

The fixtures follow what the office's workbooks print: 2023's tables set the
sexes off by BOTH GENDER / MALE / FEMALE rows and Yap's two municipality
blocks one above the other; 2010's put the men's and women's totals on their
"Male" and "Female" rows and Yap's two blocks side by side, each with its own
label column; ethnicity's single groups, then the mixed answers by main
ethnicity, each split beneath by the other group.
"""

import unittest

from scripts.fetch_census import micronesia_census as fm
from scripts.fetch_census.oceania_common import bind_level, load_units


def b1_2023(blocks):
    """Table B1, 2023 layout: blocks of {unit: (total, male, female, median, groups)}."""
    rows = [["POPULATION TABLES"]]
    for units in blocks:
        names = list(units)
        rows += [["Table B1. Age and Sex by Municipality, 2023"],
                 ["Age group", "TOTAL", "Total"] + ["   " + n for n in names]]
        for sex, index in (("BOTH GENDER", 0), ("MALE", 1), ("FEMALE", 2)):
            rows.append([sex])
            rows.append(["Total", None, None] + [units[n][index] for n in names])
            if index == 0:
                for i, (lo, hi) in enumerate(((0, 14), (15, 29), (30, 44), (45, None))):
                    label = f"{lo}-{hi}" if hi is not None else f"{lo}+"
                    rows.append([label, None, None] + [units[n][4][i] for n in names])
            rows.append(["Median age", None, None] + [units[n][3] for n in names])
    rows.append(["Table B2. Relationship"])
    return rows


# Table P1-4A/B of the 2000 census's National Detailed Tables as pypdf reads its
# two pages: the heading in glyph codes, then every line of figures.
P1_4_RULE = '/G47/G47 /G3C/G44/G53-/G47 /G3C/G44/G53/G47/G26/G4B/G58/G58/G4E-/G47/G30/G52/G55/G57-/G47/G33/G52/G4B/G51-/G47/G32/G58/G57/G48/G55/G47/G2E/G52/G56-/G47/G32/G57/G4B/G48/G55/G47/G29/G4C/G4F/G4C-/G47/G32/G57/G4B/G48/G55/G47/G47'
P1_4_NAMES = ('Municipality        /G47/G37/G52/G57/G44/G4F/G47 /G48/G56/G4'
              '8/G47/G32/G11/G2C/G56/G11/G47 /G48/G56/G48/G47/G4F/G52/G46/G4E/G47/G53/G48/G4C/G44/G51/G47/G2C/G56/G4F/G44/G51/G47/G47/G55/G44/G48/G44/G51/G47/G33/G44/G46/G2C/G56/G47/G53/G4Cno/G47/G24/G56/G4C/G44/G51/G47/G38/G36/G24/G47/G32/G57/G4B/G48/G55')
P1_4_ROWS_A = """
     Total          107,008  5,992  4,490 46,660  9,693 25,290  4,867  7,657    455    715   625   384   180
Yap                  11,241  5,711  4,452    215      8     31      2      4    175    157   393    62    31
  Yap Proper          7,391  5,702    813     21      6     29      2      3    174    157   392    61    31
    Rumung              126    126      -      -      -      -      -      -      -      -     -     -     -
    Maap                592    578      1      1      -      -      -      -      2      -     5     5     -
    Gagil               734    708      3      -      3      3      1      -      -      3     -    10     3
    Tomil             1,023    895     71      2      2      4      -      1      8     16     9    14     1
    Fanif               547    529      -      4      1      3      -      -      5      2     2     1     -
    Weloy             1,197    916    200      6      -      -      -      -     10     39     7     7    12
    Rull              2,019  1,187    538      4      -     17      1      1    129     93    14    20    15
    Gilman              233    225      -      -      -      1      -      -      5      -     -     2     -
    Kanifay             275    273      -      -      -      -      -      -      -      -     -     2     -
    Dalipebinaw         645    265      -      4      -      1      -      1     15      4   355     -     -
  Outer Islands       3,850      9  3,639    194      2      2      -      1      1      -     1     1     -
    Ulithi              773      8    760      3      1      1      -      -      -      -     -     -     -
    Fais                215      -    214      -      -      -      -      -      -      -     -     1     -
    Ngulu                26      -     26      -      -      -      -      -      -      -     -     -     -
    Woleai              975      -    973      2      -      -      -      -      -      -     -     -     -
    Eauripik            113      -    113      -      -      -      -      -      -      -     -     -     -
    Ifalik              561      -    560      -      -      -      -      1      -      -     -     -     -
    Faraulap            221      -    221      -      -      -      -      -      -      -     -     -     -
    Elato                96      -     95      -      -      1      -      -      -      -     -     -     -
    Lamotrek            339      -    158    181      -      -      -      -      -      -     -     -     -
    Satawal             531      1    519      8      1      -      -      -      1      -     1     -     -
Pohnpei              34,486    225     31    515  2,287 25,074  4,817    347    152    467   211   242   118
  Pohnpei Island     32,395    224     31    515  2,286 24,440  3,363    347    152    467   211   241   118
    Madolenihmw       5,420     28      1     43     14  5,205     46     11     42      7     4    15     4
    U                 2,685      3      -     15     11  2,613     11      2      2      5     2    19     2
    Nett              6,158     47      -    130    135  4,968    215     91     27    252    78   153    62
    Sokehs            6,444     70     11    221  1,978  2,271  1,652     97     27     33    56    13    15
    Kitti             6,007      4      1      9     11  5,928     21      4      6      5     7    10     1
    Kolonia           5,681     72     18     97    137  3,455  1,418    142     48    165    64    31    34
  Outer Islands       2,091      1      -      -      1    634  1,454      -      -      -     -     1     -
    Mwoakilloa          177      -      -      -      -      1    175      -      -      -     -     1     -
    Pingelap            438      -      -      -      -      -    438      -      -      -     -     -     -
    Sapwuahfik          640      1      -      -      1    632      6      -      -      -     -     -     -
    Nukuoro             362      -      -      -      -      1    361      -      -      -     -     -     -
    Kapingamarangi      474      -      -      -      -      -    474      -      -      -     -     -     -
Kosrae                7,686     29      -     55     11    100     35  7,281     76     40    13    37     9
  Lelu                2,591      8      -      7      4     39      4  2,434     33     22     7    29     4
  Malem               1,571     12      -      9      -     13      7  1,489     26      6     1     4     4
  Utwe                1,067      2      -      2      -     13      4  1,043      1      2     -     -     -
  Tafunsak            2,457      7      -     37      7     35     20  2,315     16     10     5     4     1
"""
P1_4_ROWS_B = """
Chuuk                53,595     27      7 45,875  7,387     85     13     25     52     51     8    43    22
  Northern Namoneas  14,722     22      4 13,752    693     79      8     17     46     47     7    31    16
    Weno             13,802     22      4 12,834    691     79      8     17     46     47     7    31    16
    Piis-Paneu          523      -      -    523      -      -      -      -      -      -     -     -     -
    Fono                397      -      -    395      2      -      -      -      -      -     -     -     -
  Southern Namoneas  11,694      3      2 11,675      -      1      1      1      3      4     1     3     -
    Tonoas            3,910      2      2  3,898      -      -      -      1      2      4     1     -     -
    Fefen             4,062      1      -  4,059      -      1      -      -      -      -     -     1     -
    Siis                490      -      -    489      -      -      -      -      -      -     -     1     -
    Uman              2,847      -      -  2,846      -      -      -      -      -      -     -     1     -
    Parem               385      -      -    383      -      -      1      -      1      -     -     -     -
  Faichuk            14,049      2      - 14,026      2      2      -      -      2      -     -     9     6
    Eot                 382      1      -    381      -      -      -      -      -      -     -     -     -
    Udot              1,774      -      -  1,773      -      -      -      -      -      -     -     1     -
    Romanum           1,011      -      -  1,011      -      -      -      -      -      -     -     -     -
    Fanapanges          681      -      -    681      -      -      -      -      -      -     -     -     -
    Wonei             1,271      -      -  1,271      -      -      -      -      -      -     -     -     -
    Paata             1,950      -      -  1,947      1      -      -      -      -      -     -     2     -
    Tol               5,129      1      -  5,113      1      2      -      -      -      -     -     6     6
    Polle             1,851      -      -  1,849      -      -      -      -      2      -     -     -     -
  Mortlocks           6,911      -      -    214  6,692      2      2      -      1      -     -     -     -
    Nama                995      -      -    130    864      -      1      -      -      -     -     -     -
    Losap               448      -      -      7    441      -      -      -      -      -     -     -     -
    Piis-Emwar          427      -      -      1    424      2      -      -      -      -     -     -     -
    Namoluk             407      -      -      8    399      -      -      -      -      -     -     -     -
    Ettal               267      -      -      4    263      -      -      -      -      -     -     -     -
    Lekinioch           927      -      -      2    924      -      1      -      -      -     -     -     -
    Oneop               505      -      -      2    503      -      -      -      -      -     -     -     -
    Satowan             955      -      -      2    953      -      -      -      -      -     -     -     -
    Kuttu               873      -      -     57    816      -      -      -      -      -     -     -     -
    Moch                854      -      -      1    852      -      -      -      1      -     -     -     -
    Ta                  253      -      -      -    253      -      -      -      -      -     -     -     -
  Oksoritod           6,219      -      1  6,208      -      1      2      7      -      -     -     -     -
    Houk                451      -      1    450      -      -      -      -      -      -     -     -     -
    Polowat           1,015      -      -  1,015      -      -      -      -      -      -     -     -     -
    Pollap              905      -      -    904      -      1      -      -      -      -     -     -     -
    Tamatam             365      -      -    365      -      -      -      -      -      -     -     -     -
    Makur               156      -      -    155      -      -      1      -      -      -     -     -     -
    Onoun               598      -      -    597      -      -      1      -      -      -     -     -     -
    Onou                182      -      -    182      -      -      -      -      -      -     -     -     -
    Unanu               178      -      -    178      -      -      -      -      -      -     -     -     -
    Piherarh            227      -      -    227      -      -      -      -      -      -     -     -     -
    Nomwin              711      -      -    710      -      -      -      1      -      -     -     -     -
    Fananu              355      -      -    355      -      -      -      -      -      -     -     -     -
    Ruo                 469      -      -    468      -      -      -      1      -      -     -     -     -
    Murillo             607      -      -    602      -      -      -      5      -      -     -     -     -
"""


def p1_4_pages(rows_a=None, rows_b=None, rule=None):
    head = ("[For definitions of terms and meanings of symbols, see text]\n"
            f"                    {rule or P1_4_RULE}\n"
            f"{P1_4_NAMES}\n")
    return ["Table P1-4A. Population in Municipalities by First Ethnicity, Federated "
            "States of Micronesia: 2000\n" + head + (rows_a or P1_4_ROWS_A)
            + "Source: 2000 FSM Census",
            "Table P1-4B. Population in Municipalities by First Ethnicity, Federated "
            "States of Micronesia: 2000\n[For definitions] - continued\n" + head
            + (rows_b or P1_4_ROWS_B) + "Source: 2000 FSM Census",
            "Table P2-9. Ethnicity by Usual Residence, Federated States of Micronesia: 2000",
            # The contents page names the table too, running on to its page number.
            "Table P1-4A. Population in Municipalities by First Ethnicity, Federated States of "
            "Micronesia: 2000......7\nTable P1-5A1. Population in Municipality by Place of birth"]


class Layouts(unittest.TestCase):

    def test_2023_blocks_one_above_the_other(self):
        rows = b1_2023([
            {"Gagil": (854, 418, 436, 31.8, (200, 200, 200, 254)),
             "Rull": (2080, 1007, 1073, 31.0, (520, 500, 500, 560))},
            {"Woleai": (838, 359, 478, 26.1, (250, 250, 170, 168)),
             "Ulithi": (704, 332, 371, 26.4, (200, 200, 150, 154))},
        ])
        got = fm.age_sex(rows, ("Gagil", "Rull", "Woleai", "Ulithi"))
        self.assertEqual(got["Woleai"]["total"], 838)
        self.assertEqual((got["Woleai"]["male"], got["Woleai"]["female"]), (359, 478))
        self.assertEqual(got["Rull"]["median_both"], 31.0)
        self.assertEqual(got["Gagil"]["groups"][0], (0, 14, 200))
        fm.check_age("Gagil", got["Gagil"], 2023)

    def test_a_printed_median_far_from_the_groups_stops_the_run(self):
        rows = b1_2023([{"Gagil": (854, 418, 436, 50.0, (200, 200, 200, 254)),
                         "Rull": (2080, 1007, 1073, 31.0, (520, 500, 500, 560))}])
        got = fm.age_sex(rows, ("Gagil", "Rull"))
        with self.assertRaises(SystemExit):
            fm.check_age("Gagil", got["Gagil"], 2023)

    def test_a_printed_median_outside_its_middle_persons_group_stops_the_run(self):
        # 426 of 854 are under 30, so the middle person is 30 or over: 29.7 is
        # another row's, though it is within half a year of the groups' 30.1.
        rows = b1_2023([{"Gagil": (854, 418, 436, 29.7, (200, 226, 200, 228)),
                         "Rull": (2080, 1007, 1073, 31.0, (520, 500, 500, 560))}])
        got = fm.age_sex(rows, ("Gagil", "Rull"))
        self.assertEqual(fm.middle_group(sorted(got["Gagil"]["groups"]))[0], 30)
        with self.assertRaises(SystemExit) as caught:
            fm.check_age("Gagil", got["Gagil"], 2023)
        self.assertIn("middle person", str(caught.exception))

    def test_a_printed_median_more_than_half_a_year_from_its_groups_stops_the_run(self):
        # The groups give 32.0, and 32.6 lies inside the middle person's 30-44.
        rows = b1_2023([{"Gagil": (854, 418, 436, 32.6, (200, 200, 200, 254)),
                         "Rull": (2080, 1007, 1073, 31.0, (520, 500, 500, 560))}])
        got = fm.age_sex(rows, ("Gagil", "Rull"))
        with self.assertRaises(SystemExit) as caught:
            fm.check_age("Gagil", got["Gagil"], 2023)
        self.assertIn("its five-year groups give 32.0", str(caught.exception))

    def test_a_printed_median_within_half_a_year_of_its_groups_passes(self):
        rows = b1_2023([{"Gagil": (854, 418, 436, 32.4, (200, 200, 200, 254)),
                         "Rull": (2080, 1007, 1073, 31.0, (520, 500, 500, 560))}])
        got = fm.age_sex(rows, ("Gagil", "Rull"))
        fm.check_age("Gagil", got["Gagil"], 2023)

    def test_2010_side_by_side_blocks_with_their_sexes_on_their_own_rows(self):
        head = ["Age Group", "Total", "Yap Proper", "Gagil", "Rull", "Age Group",
                "Yap Outer Islands", "Woleai", "Ulithi"]
        rows = [["Table B01.  Age and Sex by Municipality"], head,
                ["Total", 3000, 2000, 900, 1100, "Total", 1000, 600, 400],
                ["Less than 5 years", 300, 200, 90, 110, "Less than 5 years", 100, 60, 40],
                ["Median", 25, 26.5, 26.3, 27.6, "Median", 22.3, 22.1, 21.1],
                ["75+", 30, 20, 9, 11, "75+", 10, 6, 4],
                ["   Male", 1500, 1000, 450, 550, "   Male", 500, 300, 200],
                ["Median", 24, 25, 25.6, 28.3, "Median", 19.2, 18.8, 19.6],
                ["   Female", 1500, 1000, 450, 550, "   Female", 500, 300, 200],
                ["Table B02. Household type"]]
        got = fm.age_sex(rows, ("Gagil", "Rull", "Woleai", "Ulithi"))
        self.assertEqual((got["Woleai"]["total"], got["Woleai"]["male"]), (600, 300))
        self.assertEqual(got["Ulithi"]["median_both"], 21.1)
        self.assertEqual(got["Rull"]["median_male"], 28.3)
        # Chuuk's "75+" row under the median repeats groups already read.
        self.assertEqual(got["Gagil"]["groups"], [(0, 4, 90)])

    def test_a_municipality_nobody_listed_breaks_the_state_sum(self):
        got = {name: {"total": 10} for name in fm.MUNICIPALITIES["Kosrae"]}
        fm.add_up("Kosrae", got, 40, 2023)
        with self.assertRaises(SystemExit):
            fm.add_up("Kosrae", got, 52, 2023)
        del got["Utwe"]
        with self.assertRaises(SystemExit):
            fm.add_up("Kosrae", got, 30, 2023)

    def test_a_name_broken_over_two_header_rows_is_joined(self):
        rows = [["Table B1. Age and Sex by Municipality"],
                [None, None, "Madole-", None, "Mwoak-"],
                ["Age group", "Total", "nihmw", "U", "illoa"],
                ["BOTH GENDER"], ["Total", 6603, 4129, 2413, 61]]
        flat = fm.flat_rows(rows, ("Madolenihmw", "U", "Mwoakilloa"))
        self.assertEqual(flat[-1][2], {"Madolenihmw": 4129, "U": 2413, "Mwoakilloa": 61})

    def test_regions_and_totals_are_read_past(self):
        rows = [["Table B01."], ["Age Group", "Total", "Chuuk Lagoon", "Northern Namoneas",
                                 "Weno", "Fono", "Faichuk", "Tol"],
                ["Total", 100, 60, 50, 40, 10, 10, 10]]
        flat = fm.flat_rows(rows, ("Weno", "Fono", "Tol"))
        self.assertEqual(flat[0][2], {"Weno": 40, "Fono": 10, "Tol": 10})


class Compositions(unittest.TestCase):

    def test_suppressed_religion_cells_are_left_out_and_said(self):
        rows = [["Table B6. Religion by Municipality"],
                ["Religion", "TOTAL", "Total", "Gagil", "Rull"],
                ["BOTH GENDER"], ["Total", 2934, 2934, 854, 2080]]
        counts = {"Roman Catholic": (639, 1463), "Congregation/Protestant": (17, 170),
                  "Assembly of God": ("*", "*"), "Pentecostal": ("*", 17),
                  "Apostolic": ("*", "*"), "Baptist": (37, 56), "SDA": ("*", 29),
                  "Mormon": (18, 42), "Jehovah's Witness": ("*", 28),
                  "Other religion": (70, 217), "No religion/Refused": (56, 48)}
        for label, (gagil, rull) in counts.items():
            rows.append([label, None, None, gagil, rull])
        rows += [["MALE"], ["Total", 1, 1, 418, 1007], ["Roman Catholic", 1, 1, 319, 713],
                 ["Source: 2023 FSM Population and Housing Census"], ["Table H1."]]
        got = fm.religion_2023(rows, ("Gagil", "Rull"))
        self.assertIsNone(got["Gagil"]["counts"]["Seventh-day Adventist"])
        shares, note = fm.religion_note(2023, 854, got["Gagil"]["counts"], "Gagil")
        self.assertEqual(shares[0]["group"], "Roman Catholic")
        self.assertEqual(shares[0]["count"], 639)
        self.assertIn("17 people in those cells", note)
        self.assertLess(sum(s["pct"] for s in shares), 100)

    def test_unsuppressed_religion_must_add_up(self):
        counts = {"Roman Catholic": 600, "Baptist": 100}
        with self.assertRaises(SystemExit):
            fm.religion_note(2023, 854, counts, "Gagil")

    def test_ethnicity_takes_leaves_and_mixed_answers_by_main_group(self):
        head = ["Ethnicity", "Total", "Pohnpei Proper", "Kolonia", "Nett"]
        rows = [["Table B08. Single and Multiple Ethnicity"], head,
                ["All Persons", 0, 0, 1000, 500],
                ["Single ethnicity", 0, 0, 800, 450],
                ["Pohnpeian", 0, 0, 600, 400], ["Chuukese", 0, 0, 100, 20],
                ["Caucasian / White", 0, 0, 30, 10],
                ["    U.S. American", 0, 0, 20, 10], ["    Other Caucasian / White", 0, 0, 10, 0],
                ["Asian", 0, 0, 60, 20], ["    Filipino", 0, 0, 60, 20],
                ["Other", 0, 0, 10, 0],
                ["Multiple Ethnicity", 0, 0, 200, 50],
                ["Pohnpeian as main ethnicity and", 0, 0, 120, 30],
                ["    Chuukese", 0, 0, 100, 30], ["    Other", 0, 0, 20, 0],
                ["Other as main ethnicity and", 0, 0, 30, 0], ["    Pohnpeian", 0, 0, 30, 0],
                ["Multiple Pohnpeian localities", 0, 0, 50, 20],
                ["Source: 2010 FSM Census"], ["Table B08A. Male"]]
        got = fm.ethnicity_2010(rows, ("Kolonia", "Nett"))
        self.assertEqual(got["Kolonia"]["Pohnpeian"], 600)
        self.assertEqual(got["Kolonia"]["Chuukese"], 100)
        self.assertEqual(got["Kolonia"]["U.S. American"], 20)
        self.assertNotIn("Caucasian / White", got["Kolonia"])
        self.assertEqual(got["Kolonia"]["Pohnpeian and another ethnicity"], 120)
        self.assertEqual(got["Kolonia"]["Two or more Pohnpei State ethnicities"], 50)
        self.assertEqual(sum(got["Kolonia"].values()), 1000)
        self.assertEqual(sum(got["Nett"].values()), 500)
        fm.composition_2010(got["Nett"], 500, "Nett's ethnicity")
        with self.assertRaises(SystemExit):
            fm.composition_2010(got["Nett"], 501, "Nett's ethnicity")

    def test_language_rows_follow_their_total_and_must_add_up(self):
        rows = [["Table B10A."], ["Literacy", "Total", "Lelu", "Malem"],
                ["Language mainly spoken at  home 3+ years", 3214, 1996, 1218],
                ["English", 57, 50, 7], ["Kosraean", 3080, 1887, 1193], ["Pohnpeian", 12, 12, 0],
                ["Filipino", 35, 35, 0], ["Chinese / Taiwanese", 6, 6, 0],
                ["Other Pacific Island Languages", 24, 6, 18],
                ["Source: 2010 FSM Census"]]
        flat = fm.flat_rows(rows, ("Lelu", "Malem"))
        got = fm.section(flat, "languagemainlyspoken", fm.LANGUAGE, "language")
        self.assertEqual(got["Lelu"]["total"], 1996)
        self.assertEqual(got["Lelu"]["counts"]["Chinese"], 6)
        rows[4][2] = 1886
        with self.assertRaises(SystemExit):
            fm.section(fm.flat_rows(rows, ("Lelu", "Malem")), "languagemainlyspoken",
                       fm.LANGUAGE, "language")


class FirstEthnicity2000(unittest.TestCase):

    def test_every_municipality_and_sum(self):
        eth = fm.ethnicity_2000(p1_4_pages())
        self.assertEqual(len(eth), 75)
        weno = eth[("Chuuk", "Weno")]
        self.assertEqual(weno["total"], 13_802)
        self.assertEqual(weno["counts"]["Chuukese"], 12_834)
        self.assertEqual(weno["counts"]["Yap Outer Islander"], 4)
        self.assertEqual(eth[("Kosrae", "Lelu")]["counts"]["Kosraean"], 2_434)
        self.assertEqual(eth[("Chuuk", "Piherarh")]["counts"], {**dict.fromkeys(
            fm.P1_4_GROUPS, 0), "Chuukese": 227})

    def test_a_misread_figure_stops_the_run(self):
        with self.assertRaises(SystemExit):     # the line's groups no longer make it
            fm.ethnicity_2000(p1_4_pages(rows_b=P1_4_ROWS_B.replace(
                "Polowat           1,015", "Polowat           1,016")))
        with self.assertRaises(SystemExit):     # the region's municipalities no longer make it
            fm.ethnicity_2000(p1_4_pages(rows_b=P1_4_ROWS_B.replace(
                "Polowat           1,015      -      -  1,015",
                "Polowat           1,016      -      -  1,016")))

    def test_a_missing_municipality_stops_the_run(self):
        rows = "\n".join(line for line in P1_4_ROWS_B.splitlines()
                         if not line.strip().startswith("Makur"))
        with self.assertRaises(SystemExit):
            fm.ethnicity_2000(p1_4_pages(rows_b=rows + "\n"))

    def test_columns_out_of_their_order_stop_the_run(self):
        def swap(text):                      # Yapese and Chuukese exchanged on every line
            out = []
            for line in text.splitlines():
                m = fm.P1_4_ROW.match(line)
                if not m:
                    out.append(line)
                    continue
                cells = m.group(2).split()
                cells[1], cells[3] = cells[3], cells[1]
                out.append(m.group(1) + "  " + "  ".join(cells))
            return "\n".join(out) + "\n"
        with self.assertRaises(SystemExit):
            fm.ethnicity_2000(p1_4_pages(swap(P1_4_ROWS_A), swap(P1_4_ROWS_B)))

    def test_a_heading_that_reads_otherwise_stops_the_run(self):
        with self.assertRaises(SystemExit):
            fm.ethnicity_2000(p1_4_pages(rule=P1_4_RULE.replace("/G3C/G44/G53-", "/G3C/G44-")))

    def test_chuuk_and_kosrae_take_it_with_its_year_and_why(self):
        eth = fm.ethnicity_2000(p1_4_pages())
        fields = fm.ethnicity_2000_fields("Chuuk", "Piherarh", eth)
        self.assertEqual(fields["ethnicity"], [{"group": "Chuukese", "pct": 100.0,
                                                "count": 227}])
        self.assertEqual(fields["ethnicity_year"], 2000)
        self.assertIn("first", fields["ethnicity_note"])
        nema = fm.ethnicity_2000_fields("Chuuk", "Nema", eth)   # spelled Nama in 2000
        self.assertEqual(sum(g["count"] for g in nema["ethnicity"]), 995)
        lelu = fm.ethnicity_2000_fields("Kosrae", "Lelu", eth)
        self.assertIn("Kosrae State tabulation", lelu["ethnicity_note"])


class Binding(unittest.TestCase):

    def test_every_drawn_municipality_is_a_census_one(self):
        admin1, admin2 = load_units("FSM", "admin1"), load_units("FSM", "admin2")
        if not admin2:
            self.skipTest("no FSM units in this checkout")
        rows = fm.municipal_rows(admin2)
        self.assertEqual(len(rows), len(admin2))
        bound = bind_level(rows, admin2, {u["id"]: u["name"] for u in admin1}, fm.ALIASES)
        self.assertEqual(bound["Chuuk-Piherarh"]["name"], "Piherech")
        parents = {u["id"]: u["name"] for u in admin1}
        for key, unit in bound.items():
            self.assertEqual(parents[unit["parent"]], key.split("-", 1)[0], key)


if __name__ == "__main__":
    unittest.main()
