"""Tuvalu: the 2022 report's island tables and the 2017 village and faith tables.

The report fixture is Tables 3 and 6 as pypdf reads them (kerning and all);
the workbook rows follow the 2017 tables' layout -- an island's row, its
villages indented beneath, figures in Total / Tuvalu / Other-country triples
-- cut down to a few rows. No network.
"""

import unittest

from scripts.fetch_census import tuvalu_census as tv
from scripts.fetch_census.oceania_common import load_units

REPORT = """Table 3.  Distribution and growth rate of resident population by island of enumeration, 2002–2022
Population Intercensal growth rate (% per annum)
2002 2012 2017 2022 2002–2012 2012–2017 2017–2022
Funafuti 3,962  5,436  6 , 611   6,602 3.2 3.9 0.0
Nanumea  855  612  495  610 -3.3 -4.2 4.2
Nui  610  729  494  514 1.8 -7. 8 0.8
Vaitupu 1,310  1,542  1,190  1,007 1.6 -5.2 -3.3
Nukufetau  701  666  531  581 -0.5 -4.5 1.8
Tuvalu 9,359 10,640 10,507 10,632 1.3 1.3 0.2
Table 4.  Size and growth rate of resident population by home island, 2002–2022
Table 6.  Resident population by broad age group, dependency ratio, sex ratio and median age, 2022
0–14 15–59 60+ Total Male Female
Funafuti 2,233 3,802 567 74 109 24 23 26
Outer Islands 1,383 2,144 503 88 105 25 24 26
Nanumea 211 323 76 89 108 26 24 28
Nanumaga 132 214 45 83 122 24 22 28
Niutao 184 302 64 82 98 26 23 28
Nui 165 269 80 91 100 26 27 26
Vaitupu 340 538 129 87 108 26 24 28
Nukufetau 210 302 69 92 106 23 22 25
Nukulaelae 126 179 36 91 84 22 28 19
Niulakita 15 17 4 112 125 26 20 31
Total 3,616 5,946 1,070 79 107 24 23 26
For the country as a whole, the dependency ratio shows about 79 dependents
"""


def triple(t, m, f):
    return [t, m, f]


def village_rows():
    """Table 2 in the 2017 layout, with every island and the drawn villages."""
    rows = [["Table 2: Total population by village"], ["Island by Village"],
            [None, "Total", None, None, "Tuvalu", None, None, "Other country"],
            [None, "T", "M", "F", "T", "M", "F", "T", "M", "F"],
            ["Total", 10645, 5486, 5159, 10507, 5403, 5104, 138, 83, 55]]
    islands = {
        "Nanumea": [("Hauma", 66, 32, 34), ("Matagi", 11, 6, 5)],
        "Nanumaga": [("Tonga", 198, 117, 81)],
        "Niutao": [("Kulia", 306, 147, 159)],
        "Nui": [("Manutalake", 204, 106, 98), ("Alamoni", 290, 140, 150)],
        "Vaitupu": [("Asau", 173, 85, 88), ("Temotu", 11, 9, 2), ("Saniuta", 205, 110, 95),
                    ("Matagi", 36, 19, 17), ("Motufoua", 326, 127, 199)],
        "Nukufetau": [("Aulotu", 329, 166, 163), ("Maneapa", 202, 98, 104)],
        "Funafuti": [("Fakaifou", 1327, 658, 669)],
        "Nukulaelae": [("Pepesala", 173, 91, 82)],
        "Niulakita": [("Niulakita", 43, 32, 11)],
    }
    for island, villages in islands.items():
        t = sum(v[1] for v in villages)
        m = sum(v[2] for v in villages)
        rows.append([island, t, m, t - m, t, m, t - m, "-", "-", "-"])
        for name, vt, vm, vf in villages:
            rows.append(["       " + name, vt, vm, vf, vt, vm, vf, "-", "-", "-"])
    return rows


def by_island_rows(groups, blocks):
    """Table 13 or 14: a header of groups in triples, then an island's block."""
    header = [None, "Total", None, None]
    for g in groups:
        header += [g, None, None]
    rows = [["Table"], ["Age Group"], header, [None] + ["T", "M", "F"] * (len(groups) + 1)]
    for island, counts in blocks.items():
        rows.append(["    " + island])
        row = ["Total", sum(counts), None, None]
        for c in counts:
            row += [c if c else "-", None, None]
        rows.append(row)
        rows.append(["0-4", 1, None, None])
    return rows


ETHNIC_GROUPS = ["Tuvaluan", "Tuvaluan / I-Kiribati", "Tuvaluan / Other", "Other"]
FAITHS = ["EKT", "SDA", "Jehovah's Witness", "Bahaii", "Brethren", "AOG", "Catholic", "LDS",
          "Other", "None", "Refused"]
ETHNIC = {"Tuvalu": [10193, 166, 83, 65], "Nui": [552, 46, 7, 5],
          "Vaitupu": [1044, 9, 5, 3], "Nukufetau": [576, 9, 5, 7]}
FAITH = {"Tuvalu": [9023, 266, 155, 157, 296, 155, 53, 92, 270, 26, 14],
         "Nui": [603, 3, 0, 2, 1, 1, 0, 0, 0, 0, 0],
         "Vaitupu": [1019, 1, 12, 2, 1, 4, 13, 2, 7, 0, 0],
         "Nukufetau": [559, 1, 5, 19, 1, 4, 0, 1, 5, 1, 1]}


class TheReport(unittest.TestCase):
    def test_each_island_reads_its_count_sex_ratio_and_median(self):
        read = tv.read_report([REPORT])
        self.assertEqual(read["Nui"], {"population": 514, "sex_ratio": 100, "median": 26})
        self.assertEqual(read["Vaitupu"]["population"], 1_007)
        self.assertEqual(read["Nukufetau"]["median"], 23)

    def test_a_table_6_that_does_not_make_tuvalu_stops_the_run(self):
        with self.assertRaises(SystemExit):
            tv.read_report([REPORT.replace("Nui 165 269 80", "Nui 165 269 81")])


class TheTables(unittest.TestCase):
    def test_villages_keep_their_island(self):
        read = tv.read_villages(village_rows())
        self.assertEqual(read[("Vaitupu", "Matagi")], (36, 19, 17))
        self.assertEqual(read[("Nanumea", "Matagi")], (11, 6, 5))
        self.assertEqual(read[("Vaitupu", "Motufoua")], (326, 127, 199))

    def test_villages_that_do_not_make_their_island_stop_the_run(self):
        rows = village_rows()
        for row in rows:
            if row[0] == "       Alamoni":
                row[4] = 291
                row[5] = 141
        with self.assertRaises(SystemExit):
            tv.read_villages(rows)

    def test_faiths_and_ethnic_groups_by_island(self):
        faith = tv.read_by_island(by_island_rows(FAITHS, FAITH), tv.RELIGIONS, "Table 14")
        ethnic = tv.read_by_island(by_island_rows(ETHNIC_GROUPS, ETHNIC), tv.ETHNIC, "Table 13")
        self.assertEqual(faith["Nui"]["Church of Tuvalu"], 603)
        self.assertEqual(faith["Nukufetau"]["Refused to answer"], 1)
        self.assertEqual(ethnic["Nui"]["Tuvaluan and I-Kiribati"], 46)

    def test_an_unknown_denomination_stops_the_run(self):
        with self.assertRaises(SystemExit):
            tv.read_by_island(by_island_rows(FAITHS[:-1] + ["Muslim"], FAITH), tv.RELIGIONS,
                              "Table 14")


class TheRecords(unittest.TestCase):
    def setUp(self):
        faith = tv.read_by_island(by_island_rows(FAITHS, FAITH), tv.RELIGIONS, "Table 14")
        ethnic = tv.read_by_island(by_island_rows(ETHNIC_GROUPS, ETHNIC), tv.ETHNIC, "Table 13")
        self.records = tv.build(tv.read_report([REPORT]), tv.read_villages(village_rows()),
                                faith, ethnic, load_units("TUV", "admin1"),
                                load_units("TUV", "admin2"))

    def named(self, name):
        return next(r for r in self.records if r["name"] == name)

    def test_every_drawn_island_and_village_has_a_record(self):
        self.assertEqual(sum(r["level"] == "admin1" for r in self.records), 3)
        self.assertEqual(sum(r["level"] == "admin2" for r in self.records), 6)

    def test_an_island_carries_2022_ages_and_2017_faiths(self):
        nui = self.named("Nui")
        self.assertEqual(nui["median_age"]["year"], 2022)
        self.assertEqual(nui["religion_year"], 2017)
        self.assertEqual(nui["religion"][0]["group"], "Church of Tuvalu")
        self.assertEqual(nui["language"]["status"], "not_available")

    def test_a_village_carries_its_count_and_says_what_it_lacks(self):
        motufoua = self.named("Motufoua")
        self.assertEqual(motufoua["population"]["value"], 326)
        self.assertEqual(motufoua["sex_ratio"]["value"], 63.8)
        self.assertEqual(motufoua["religion"]["status"], "not_available")
        self.assertEqual(motufoua["parent_name"], "Vaitupu")

    def test_a_village_of_eleven_people_has_no_sex_ratio(self):
        temotu = self.named("Temotu")
        self.assertEqual(temotu["population"]["value"], 11)
        self.assertEqual(temotu["sex_ratio"]["status"], "not_available")
        self.assertIn("11 people (9 men and 2 women)", temotu["sex_ratio"]["note"])
        self.assertNotIn("sex_ratio_note", temotu)


if __name__ == "__main__":
    unittest.main()
