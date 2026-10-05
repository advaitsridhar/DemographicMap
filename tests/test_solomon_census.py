"""Solomon Islands' 2019 census Basic Tables: rows, provinces, wards and constituencies.

The fixtures are page texts in the shape pypdf gives them and a few rows of
OCHA's ward table; no network.
"""

import unittest

from scripts.fetch_census import solomon_census as sc

P22 = """9
P2.2: Total population by sex and number of private households and non-private dwellings by ward, Solomon Islands: 2019
Both Sexes Males Females Households Non-private
Solomon Islands 720,956 369,396 351,560 131,566 926
Choiseul 30,775 15,863 14,912 5,520 57
01 Wagina 1,782 952 830 264 -
02 Katupika 2,318 1,203 1,115 456 8
Honiara City Council 129,569 66,809 62,760 20,839 138
01 Nggossi 26,009 13,216 12,793 4,202 5
P3.1: Total population by 5-year age groups and sex, province and ward, Solomon Islands: 2019
01 Choiseul 30,775 4,400 4,131 3,751 2,955 2,114 2,138 2,031 1,939 1,759 1,544 1,149 876 649 482 322 236 111 188
"""


class Rows(unittest.TestCase):
    def test_provinces_wards_and_the_country_are_told_apart(self):
        got = sc.read_table([P22], "P2.2")
        self.assertEqual(got["national"][0], 720956)
        self.assertEqual(got["provinces"]["01"][:3], [30775, 15863, 14912])
        self.assertEqual(got["provinces"]["10"][0], 129569)
        self.assertEqual(got["wards"][("01", "02")][0], "Katupika")
        self.assertEqual(got["wards"][("10", "01")], ("Nggossi", [26009, 13216, 12793, 4202, 5]))

    def test_a_dash_is_nothing(self):
        got = sc.read_table([P22], "P2.2")
        self.assertEqual(got["wards"][("01", "01")][1][-1], 0)

    def test_rows_under_another_title_belong_to_that_table(self):
        got = sc.read_table([P22], "P2.2")
        self.assertEqual(len(got["provinces"]), 2)
        ages = sc.read_table([P22], "P3.1")
        self.assertEqual(ages["provinces"]["01"][0], 30775)
        self.assertEqual(ages["wards"], {})

    def test_wards_on_the_next_page_stay_in_the_last_province(self):
        page2 = ("10\nP2.2: Total population by sex ... by ward, Solomon Islands: 2019 (cont'd.)\n"
                 "02 Mbumburu 5,806 2,936 2,870 870 3\n")
        got = sc.read_table([P22.split("P3.1")[0], page2], "P2.2")
        self.assertEqual(got["wards"][("10", "02")][0], "Mbumburu")

    def test_a_ward_printed_twice_differently_stops_the_run(self):
        page = P22 + "P2.2: (cont'd.)\nChoiseul 30,775 15,863 14,912 5,520 57\n" \
                     "02 Katupika 2,318 1,200 1,118 456 8\n"
        with self.assertRaises(SystemExit):
            sc.read_table([page], "P2.2")


WARDS = """ADM1_NAME,ADM2_PCODE,ADM2_NAME,ADM3_PCODE,ADM3_NAME,ADM3_NAME_ALT,T_TL
Choiseul,SB010101,South Choiseul,SB0101010101,Waghina,Wagina,1899
Choiseul,SB010101,South Choiseul,SB0101010102,Katupika,Katupika,2470
Honiara,SB101041,East Honiara,SB1010411001,Nggossi,Nggossi,27000
"""


class Wards(unittest.TestCase):
    PEOPLE = {"wards": {("01", "01"): ("Wagina", [1782]), ("01", "02"): ("Katupika", [2318]),
                        ("10", "01"): ("Nggossi", [26009])}}

    def test_a_ward_is_found_by_province_and_number(self):
        table = sc.ward_table(WARDS)
        self.assertEqual(table[("10", "01")]["constituency"], "East Honiara")
        got = sc.assign_wards(self.PEOPLE, table)
        self.assertEqual(got[("01", "02")], "SB010101")

    def test_a_ward_whose_names_disagree_stops_the_run(self):
        table = sc.ward_table(WARDS.replace("Waghina,Wagina", "Batava,Batava"))
        with self.assertRaises(SystemExit):
            sc.assign_wards(self.PEOPLE, table)

    def test_a_ward_missing_from_the_table_stops_the_run(self):
        table = sc.ward_table("\n".join(WARDS.splitlines()[:-1]) + "\n")
        with self.assertRaises(SystemExit):
            sc.assign_wards(self.PEOPLE, table)

    def test_wards_add_up(self):
        table = {("01", "01"): [1, 2], ("01", "02"): [3, 4]}
        self.assertEqual(sc.add_up([("01", "01"), ("01", "02")], table), [4, 6])


class Fields(unittest.TestCase):
    def test_a_constituency_has_no_ethnic_group_and_says_where_it_comes_from(self):
        ages = [10] * 18
        religion = [100] + [0] * 16
        fields = sc.fields_for([180, 90, 90], ages, religion, None, constituency=True)
        self.assertEqual(fields["ethnicity"]["status"], "not_available")
        self.assertIn("wards' added up", fields["population_note"])
        self.assertEqual(fields["sex_ratio"]["value"], 100.0)
        self.assertEqual(fields["religion"][0]["group"], "Church of Melanesia")

    def test_a_province_has_its_ethnic_groups(self):
        fields = sc.fields_for([180, 90, 90], [10] * 18, [180] + [0] * 16,
                               [170] + [10] + [0] * 10, constituency=False)
        self.assertEqual(fields["ethnicity"][0], {"group": "Melanesian", "pct": 94.4,
                                                  "count": 170})


if __name__ == "__main__":
    unittest.main()
