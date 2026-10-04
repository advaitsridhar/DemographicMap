"""Tonga's 2021 census tables: reading them, checking them and binding them.

The fixtures are the workbooks' layout cut down to two divisions' worth of
rows, with the real header rows; no network.
"""

import unittest

from scripts.fetch_census import tonga_census as tc


class Sheet:
    def __init__(self, rows):
        self.rows = rows

    def iter_rows(self, values_only=True):
        return iter(self.rows)


class Book(dict):
    def __getitem__(self, name):
        return Sheet(dict.__getitem__(self, name))


def g1(rows):
    head = [["Table G 1"], ["Division/District", "2021 Population"], ["", "Total", "Male", "Female"]]
    return head + [[name, t, m, f] for name, t, m, f in rows]


# A Tonga of two divisions is not Tonga, so the national check is the one
# thing the small fixture cannot pass; the readers below it are tested apart.
POPULATION = [
    ("TONGA", 100179, 48749, 51430),
    ("Tongatapu", 74320, 35959, 38361),
    ("Kolofo'ou", 17274, 8352, 8922),
    ("Kolomotu'a", 16868, 8111, 8757),
    ("Vaini", 13199, 6418, 6781),
    ("Tatakamotonga", 7192, 3454, 3738),
    ("Lapaha", 7309, 3607, 3702),
    ("Nukunuku", 8177, 3970, 4207),
    ("Kolovai", 4301, 2047, 2254),
    ("Vava'u", 14182, 7044, 7138),
    ("Neiafu", 5345, 2635, 2710),
    ("Pangaimotu", 1206, 577, 629),
    ("Hahake", 2151, 1070, 1081),
    ("Leimatu'a", 2855, 1461, 1394),
    ("Hihifo", 1969, 973, 996),
    ("Motu", 656, 328, 328),
    ("Ha'apai", 5665, 2787, 2878),
    ("Pangai", 2042, 979, 1063),
    ("Foa", 1340, 662, 678),
    ("Lulunga", 723, 354, 369),
    ("Mu'omu'a", 488, 245, 243),
    ("Ha`ano", 456, 234, 222),
    ("'Uiha", 616, 313, 303),
    ("'Eua", 4864, 2386, 2478),
    ("Eua Motu'a", 2740, 1353, 1387),
    ("Eua Fo'ou", 2124, 1033, 1091),
    ("Ongo Niua", 1148, 573, 575),
    ("Niuatoputapu", 718, 354, 364),
    ("Niuafo'ou", 430, 219, 211),
    ("Urban", 21185, 10229, 10956),
]


class Population(unittest.TestCase):
    def test_divisions_and_districts_are_read_and_add_up(self):
        people, tree = tc.read_population(g1(POPULATION))
        self.assertEqual(people["Kolofo'ou"]["total"], 17274)
        self.assertEqual(tree["Ongo Niua"], ["Niuatoputapu", "Niuafo'ou"])
        self.assertNotIn("Urban", people)

    def test_districts_that_miss_their_division_stop_the_run(self):
        rows = [r if r[0] != "Motu" else ("Motu", 600, 300, 300) for r in POPULATION]
        with self.assertRaises(SystemExit):
            tc.read_population(g1(rows))

    def test_sexes_that_miss_the_total_stop_the_run(self):
        rows = [r if r[0] != "Foa" else ("Foa", 1340, 600, 678) for r in POPULATION]
        with self.assertRaises(SystemExit):
            tc.read_population(g1(rows))


class Ages(unittest.TestCase):
    def test_a_district_median_comes_from_its_own_row_not_its_villages(self):
        head = [["Table G 5"],
                ["Division/District", "Total", "0-4", "5-9", "10-14", "15-19", "20-24",
                 "25-29", "30-34", "35-39", "40-44", "45-50", "51-54", "55-59", "60-64",
                 "65-69", "70-74", "75+"], [""]]
        district = ["Foa", 100] + [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 0, 0, 0, 0, 0, 0]
        village = ["Foa", 40] + [10, 10, 10, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        people = {"Foa": {"total": 100}}
        got = tc.district_medians(head + [village[:2] + [0] * 16, district, village],
                                  ["Foa"], people)
        self.assertEqual(got["Foa"], 25.0)

    def test_single_years_give_the_division_median(self):
        header = ["Age", "TONGA", "", "", "Tongatapu", "", "", "Vava'u", "", "", "Ha'apai",
                  "", "", "Eua", "", "", "Ongo Niua", "", ""]
        rows = [["Table G 6"], header, [""], ["Total"] + [4] * 18]
        for age in ("<1", "1", "2+"):
            rows.append([age] + ([1] * 18 if age != "2+" else [2] * 18))
        people = {d: {"total": 4} for d in tc.DIVISIONS + ("TONGA",)}
        got = tc.division_medians(rows, people)
        self.assertEqual(got["Tongatapu"], 2.0)


class Religion(unittest.TestCase):
    HEADER = ["Division / District", "Total", "FWC", "RC", "LDS", "NO Rel", "REF", "Other"]

    def test_abbreviations_become_the_tables_own_names(self):
        rows = [["Table G 19"], self.HEADER, ["Foa", 100, 50, 20, 20, 5, 3, 2]]
        got = tc.read_religion(rows, ["Foa"])["Foa"]["counts"]
        self.assertEqual(got["Free Wesleyan Church"], 50)
        self.assertEqual(got["Church of Jesus Christ of Latter-day Saints"], 20)
        self.assertEqual(got["Not stated"], 3)

    def test_an_unknown_abbreviation_stops_the_run(self):
        rows = [["Table G 19"], self.HEADER + ["XYZ"], ["Foa", 100, 50, 20, 20, 5, 3, 2, 0]]
        with self.assertRaises(SystemExit):
            tc.read_religion(rows, ["Foa"])

    def test_denominations_that_miss_the_total_stop_the_run(self):
        rows = [["Table G 19"], self.HEADER, ["Foa", 100, 50, 20, 20, 5, 3, 1]]
        with self.assertRaises(SystemExit):
            tc.read_religion(rows, ["Foa"])


class Ethnicity(unittest.TestCase):
    def test_origins_are_multiple_and_district_rows_are_found_before_villages(self):
        header = ["Division/ District/ Village", "Tongan", "European", "Other"]
        rows = [["Table G 12"], [""], header,
                ["Ha'apai", 5624, 18, 30],
                ["Foa", 1330, 15, 0],      # the district: 1,345 origins for 1,340 people
                ["Foa", 400, 0, 0]]        # a village of the same name
        people = {"Ha'apai": {"total": 5665}, "Foa": {"total": 1340}}
        got = tc.read_ethnicity(rows, ["Ha'apai"], ["Foa"], people)
        self.assertEqual(got["Foa"], {"Tongan": 1330, "European": 15, "Other": 0})


def g50(rows):
    head = [["Table G 50: Population (5 years +) language use at home by age, sex and division"],
            [""],
            ["Age / Division", "Total", "", "", "Tongan language only", "", "",
             "Tongan and other language(s)", "", "", "Tongan language is not used at home"],
            ["", "Total", "Male", "Female", "Total", "Male", "Female", "Total", "Male",
             "Female", "Total", "Male", "Female"]]
    return head + rows


# Volume 1's Table G 48, which is the workbook's G 50.
LANGUAGE = [
    ["Tonga", 89254, 42991, 46263, 75828, 37010, 38818, 12420, 5444, 6976, 1006, 537, 469],
    ["5-9", 12644, 6564, 6080, 11152, 5858, 5294, 1406, 668, 738, 86, 38, 48],
    ["Tongatapu", 66295, 31764, 34531, 55105, 26807, 28298, 10298, 4492, 5806, 892, 465, 427],
    ["Vava'u", 12550, 6179, 6371, 11343, 5634, 5709, 1133, 498, 635, 74, 47, 27],
    ["Ha'apai", 5027, 2424, 2603, 4677, 2268, 2409, 327, 142, 185, 23, 14, 9],
    ["'Eua", 4342, 2096, 2246, 3721, 1800, 1921, 605, 286, 319, 16, 10, 6],
    ["Ongo Niua", 1040, 528, 512, 982, 501, 481, 57, 26, 31, 1, 1, 0],
]


class Language(unittest.TestCase):
    def test_the_three_answers_are_read_for_each_division(self):
        got = tc.read_language(g50(LANGUAGE))
        self.assertEqual(got["Tongatapu"]["total"], 66295)
        self.assertEqual(got["'Eua"]["counts"], {"Tongan only": 3721,
                                                 "Tongan and other languages": 605,
                                                 "Other languages": 16})

    def test_answers_that_miss_the_total_stop_the_run(self):
        rows = [r if r[0] != "Ha'apai" else
                ["Ha'apai", 5027, 2424, 2603, 4677, 2268, 2409, 300, 142, 158, 23, 14, 9]
                for r in LANGUAGE]
        with self.assertRaises(SystemExit):
            tc.read_language(g50(rows))

    def test_a_missing_division_stops_the_run(self):
        with self.assertRaises(SystemExit):
            tc.read_language(g50([r for r in LANGUAGE if r[0] != "Ongo Niua"]))

    def test_a_district_says_why_it_has_no_language(self):
        fields = tc.fields_for("Foa", {"total": 100, "male": 50, "female": 50}, 20.0,
                               {"total": 100, "counts": {"Roman Catholic": 100}},
                               {"Tongan": 100}, "five-year group", tc.DISTRICT_LANGUAGE)
        self.assertEqual(fields["language"]["status"], "not_available")
        self.assertIn("division only", fields["language"]["note"])


if __name__ == "__main__":
    unittest.main()
