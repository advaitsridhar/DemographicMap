"""Vanuatu's 2020 census Basic Tables: reading the PDF's text, checking it, pairing panels.

The fixtures are page texts in the shape pypdf gives them, cut down to a few
regions; no network.
"""

import unittest

from scripts.fetch_census import vanuatu_census as vc

ORDER = ["VANUATU", "URBAN", "Port Vila", "Luganville", "RURAL", "TORBA", "Torres",
         "Ureparapara", "Central Pentecost 1", "Canal - Fanafo"]


class LabelledRows(unittest.TestCase):
    def test_a_row_is_its_name_and_its_figures_with_dashes_for_none(self):
        page = ("Table 1.1: Total population by region, sex, and number of people\n"
                "Region Total Male Female\n"
                "Torres 1,190 597 593 208 1,185 595 590 207 5 3 2 1\n"
                "Ureparapara 466 243 223 93 466 243 223 93 - - - 0\n")
        rows = vc.read_table([page], "1.1")
        self.assertEqual(rows["Torres"][12][:3], [1190, 597, 593])
        self.assertEqual(rows["Ureparapara"][12][-4:], [0, 0, 0, 0])

    def test_a_name_ending_in_a_number_keeps_it(self):
        page = ("Table 1.1: Total population\n"
                "Central Pentecost 1 3,521 1,771 1,750 767 3,405 1,710 1,696 765 116 61 54 2\n"
                "Canal - Fanafo 5,792 3,044 2,747 1,273 5,731 3,006 2,724 1,267 61 38 23 6\n")
        rows = vc.read_table([page], "1.1")
        self.assertIn("Central Pentecost 1", rows)
        self.assertEqual(rows["Central Pentecost 1"][12][0], 3521)
        self.assertIn("Canal - Fanafo", rows)

    def test_rows_under_another_tables_title_are_not_this_tables(self):
        page = ("Table 6.16: first language learnt to speak\n"
                "Torres 1,082 545 537 15 8 8 - - -\n"
                " Table 6.15: ability to write Vernacular language\n"
                "Ureparapara 9 9 9 9 9 9 9 9 9\n")
        rows = vc.read_table([page], "6.16", ORDER)
        self.assertIn("Torres", rows)
        self.assertNotIn("Ureparapara", rows)

    def test_a_row_printed_twice_differently_stops_the_run(self):
        page = ("Table 3.1: ethnic origin\n"
                "Torres 1,185 1,184 1 - - - - - -\n"
                "Torres 1,185 1,180 5 - - - - - -\n")
        with self.assertRaises(SystemExit):
            vc.read_table([page], "3.1", ORDER)


class NamesFirstPanels(unittest.TestCase):
    PANEL = ("Table 3.5: Total population in private households by religion and region\n"
             "Region\nTORBA\nTorres\nUreparapara\n"
             "Apostolic\nLatter Day\nSaints\n"
             "39 99 649 4 3 -\n - - 7 3 - -\n2 - 1 - - -\nReligion\n"
             "Table 3.5: Total population in private households by religion and region\n")

    def test_names_listed_apart_are_paired_with_the_rows_after_them(self):
        rows = vc.read_table([self.PANEL], "3.5", ORDER)
        self.assertEqual(rows["TORBA"][6], [39, 99, 649, 4, 3, 0])
        self.assertEqual(rows["Ureparapara"][6], [2, 0, 1, 0, 0, 0])

    def test_a_name_missing_from_the_list_is_read_in_order(self):
        panel = self.PANEL.replace("Ureparapara\n", "")
        rows = vc.read_table([panel], "3.5", ORDER)
        self.assertEqual(rows["Ureparapara"][6], [2, 0, 1, 0, 0, 0])

    def test_a_list_with_no_rows_is_dropped(self):
        page = ("Table 6.16: first language\nRegion\nTORBA\nTorres\nNot stated\n"
                "Table 6.16: first language\nTorres 1,082 545 537 15 8 8 - - -\n")
        rows = vc.read_table([page], "6.16", ORDER)
        self.assertEqual(list(rows), ["Torres"])

    def test_more_rows_than_regions_left_stops_the_run(self):
        panel = ("Table 3.5: religion\nRegion\nCanal - Fanafo\n"
                 "1 2 3 4 5 6\n1 2 3 4 5 6\n")
        with self.assertRaises(SystemExit):
            vc.read_table([panel], "3.5", ORDER)


class Towns(unittest.TestCase):
    PEOPLE = {"Port Vila": {"private": 48461}, "Luganville": {"private": 17407},
              "Torres": {"private": 1185}}
    SPOKEN = {"Port Vila": {"total": 34802}, "Luganville": {"total": 10824},
              "Torres": {"total": 1082}}

    def test_rows_printed_under_each_others_names_are_exchanged(self):
        aged = {"Port Vila": 15978, "Luganville": 44856, "Torres": 1092}
        swapped = vc.settle_towns(aged, self.SPOKEN, self.PEOPLE)
        self.assertEqual(aged["Port Vila"], 44856)
        self.assertEqual(swapped, ["Port Vila", "Luganville"])

    def test_rows_that_fit_are_left_alone(self):
        aged = {"Port Vila": 44856, "Luganville": 15978, "Torres": 1092}
        self.assertEqual(vc.settle_towns(aged, self.SPOKEN, self.PEOPLE), [])

    def test_a_count_that_fits_neither_way_stops_the_run(self):
        aged = {"Port Vila": 44856, "Luganville": 15978, "Torres": 1000}
        with self.assertRaises(SystemExit):
            vc.settle_towns(aged, self.SPOKEN, self.PEOPLE)


class Provinces(unittest.TestCase):
    def test_a_province_adds_its_town(self):
        table = {"SHEFA": {"total": 10, "counts": {"Presbyterian": 6, "Catholic": 4}},
                 "Port Vila": {"total": 5, "counts": {"Presbyterian": 1, "Catholic": 4}}}
        got = vc.with_town("SHEFA", table)
        self.assertEqual(got, {"total": 15, "counts": {"Presbyterian": 7, "Catholic": 8}})
        self.assertEqual(vc.with_town("SHEFA", {"SHEFA": 3.0, "Port Vila": 2.0}), 5.0)
        self.assertEqual(vc.with_town("TORBA", {"TORBA": [1, 2]}), [1, 2])


class Language(unittest.TestCase):
    def test_shares_are_of_everyone_aged_three_and_over(self):
        fields = vc.fields_for({"total": 100, "male": 50, "female": 50}, [10] * 15,
                               {"total": 90, "counts": {"Catholic": 90}},
                               {"total": 90, "counts": {"Ni-Vanuatu": 90}},
                               {"total": 60, "counts": {"Bislama": 20, vc.VERNACULAR: 40}},
                               aged=80)
        shares = {x["group"]: x["pct"] for x in fields["language"]}
        self.assertEqual(shares, {vc.VERNACULAR: 50.0, "Bislama": 25.0})
        self.assertIn("60 of the 80", fields["language_note"])

    def test_a_council_with_no_row_says_why(self):
        fields = vc.fields_for({"total": 100, "male": 50, "female": 50}, [10] * 15,
                               {"total": 90, "counts": {"Catholic": 90}},
                               {"total": 90, "counts": {"Ni-Vanuatu": 90}}, None, None)
        self.assertEqual(fields["language"]["status"], "not_available")


if __name__ == "__main__":
    unittest.main()
