"""Offline tests for the Balkan census readers: parsing, labels, sums, medians."""

import unittest
from collections import Counter

from scripts.fetch_census import balkans_common as common
from scripts.fetch_census import croatia, montenegro, moldova_age, north_macedonia, romania_census


class CommonTest(unittest.TestCase):
    def test_grouped_median_interpolates_within_the_group(self):
        # 10 people 0-4, 10 people 5-9: the middle person is at the 5-9 boundary.
        self.assertEqual(common.grouped_median([(0, 5, 10), (5, 5, 10)]), 5.0)
        self.assertEqual(common.grouped_median([(0, 5, 10), (5, 5, 30), (10, None, 1)]), 6.8)

    def test_median_in_the_open_group_is_refused(self):
        with self.assertRaises(SystemExit):
            common.grouped_median([(0, 5, 1), (5, None, 10)])

    def test_single_year_median(self):
        self.assertEqual(common.median_age(Counter({30: 1, 31: 1})), 31.0)

    def test_fold_drops_diacritics_and_dj(self):
        self.assertEqual(common.fold("Mađari Čair"), "madaricair")

    def test_match_names_is_one_to_one_and_reports_both_sides(self):
        shapes = [{"id": "a", "name": "Bar Municipality"}, {"id": "b", "name": "Budva Municipality"},
                  {"id": "c", "name": "Kotor Municipality"}]
        bound, left, spare = common.match_names({"1": "Bar", "2": "Budva", "3": "Tivat"}, shapes,
                                                strip=["Municipality"], who="test")
        self.assertEqual(bound, {"1": "a", "2": "b"})
        self.assertEqual(left, ["Tivat (3)"])
        self.assertEqual(spare, ["Kotor Municipality"])

    def test_check_sum_refuses_a_mismatch(self):
        common.check_sum(100, 100, "same")
        with self.assertRaises(SystemExit):
            common.check_sum(99, 100, "short")


class NorthMacedoniaTest(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(north_macedonia.label_of("ethnicity", "Albanians"), "Albanian")
        self.assertEqual(north_macedonia.label_of(
            "religion", "Persons for whom data are taken from administrative sources"),
            "No religion data")

    def test_single_year_labels(self):
        self.assertEqual(north_macedonia.age_of("37"), 37)
        self.assertEqual(north_macedonia.age_of("100+"), 100)
        self.assertIsNone(north_macedonia.age_of("Age - TOTAL"))

    def test_five_year_groups_take_sexes_from_the_all_ages_row(self):
        groups = {"Age group - TOTAL": Counter({"male": 6, "female": 5, "sex - total": 11}),
                  "0-4": Counter({"male": 3, "female": 2}), "5-9": Counter({"male": 3, "female": 3}),
                  "90+": Counter()}
        rows, men, women = north_macedonia.five_year(groups)
        self.assertEqual((men, women), (6, 5))
        self.assertIn((0.0, 5.0, 5), rows)
        self.assertIn((90.0, None, 0), rows)

    def test_ts_and_c_are_one_letter(self):
        self.assertEqual(north_macedonia.key("Vraneshtitsa"), north_macedonia.key("Vraneshtica"))


class RomaniaTest(unittest.TestCase):
    def test_prefixes_and_i_hat(self):
        self.assertEqual(romania_census.bare("ORAȘ TÂRGU FRUMOS"), "TÂRGU FRUMOS")
        self.assertEqual(romania_census.fold("COVĂSÂNȚ", True), romania_census.fold("COVASINT"))
        self.assertEqual(romania_census.fold("CÂMPENI"), romania_census.fold("CAMPENI"))

    def test_labels_take_the_longest_prefix(self):
        self.assertEqual(romania_census.label_for("religion", "Ortodoxa Sarba"), "Serbian Orthodox")
        self.assertEqual(romania_census.label_for("religion", "Ortodoxa (Biserica Ortodoxa Romana)"),
                         "Orthodox")
        self.assertEqual(romania_census.label_for("ethnicity", "Romi"), "Roma")
        self.assertEqual(romania_census.label_for("ethnicity", "Români"), "Romanian")

    def test_suppressed_cells(self):
        self.assertIsNone(romania_census.number("*"))
        self.assertIsNone(romania_census.number("**"))
        self.assertEqual(romania_census.number("-"), 0.0)

    def test_what_the_stars_hide_is_one_bar(self):
        row = {"name": "ALBAC", "total": 1846.0, "groups": {"Romanian": 1693.0, "Roma": 64.0},
               "stars": 2}
        romania_census.check_row(row, "ethnicity")
        self.assertEqual(row["groups"][romania_census.SUPPRESSED], 89.0)
        with self.assertRaises(SystemExit):
            romania_census.check_row({"name": "X", "total": 10.0, "groups": {"a": 9.0},
                                      "stars": 0}, "ethnicity")
        with self.assertRaises(SystemExit):
            romania_census.check_row({"name": "X", "total": 10.0, "groups": {"a": 11.0},
                                      "stars": 1}, "ethnicity")

    def test_uat_rows_open_counties_and_read_ages(self):
        rows = [
            ["JUDET", "POPULATIA", "G R U P A", ""],
            ["", "", "0 - 4", "5 ani si peste"],
            ["", "", "ani", ""],
            ["A", "1.0", "2.0", "3.0"],
            ["ALBA", 200000.0, 50000.0, 150000.0],
            ["MUNICIPIUL ALBA IULIA", 150000.0, 40000.0, 110000.0],
            ["ALBAC", 50000.0, 10000.0, 40000.0],
        ]
        labels, data = romania_census.uat_rows(rows, {"alba"}, None)
        self.assertEqual(labels, [(0.0, 5.0), (5.0, None)])
        self.assertEqual([u["name"] for u in data["alba"]["uats"]],
                         ["MUNICIPIUL ALBA IULIA", "ALBAC"])
        self.assertEqual(data[""]["total"], 200000.0)


class MontenegroTest(unittest.TestCase):
    def test_protected_cells(self):
        self.assertIsNone(montenegro.number("z"))
        self.assertEqual(montenegro.number("-"), 0.0)
        self.assertEqual(montenegro.number(1234), 1234.0)

    def test_settle_keeps_the_hidden_people_apart(self):
        out = montenegro.settle("ethnicity", "Andrijevica", 100, {"Serbian": 90}, 1)
        self.assertEqual(out[montenegro.SUPPRESSED], 10)
        with self.assertRaises(SystemExit):
            montenegro.settle("ethnicity", "Andrijevica", 100, {"Serbian": 90}, 0)

    def test_labels(self):
        self.assertEqual(montenegro.label("ethnicity", "Crnogorci-Srbi"), "Montenegrin-Serbian")
        self.assertEqual(montenegro.label("language", "Srpsko-Hrvatski"), "Serbo-Croatian")
        self.assertEqual(montenegro.label("religion", "Ne želi da se izjasni"), "Not declared")


class MoldovaTest(unittest.TestCase):
    def test_floating_sums_round(self):
        self.assertEqual(moldova_age.persons(39562.9999999999), 39563.0)
        self.assertEqual(moldova_age.persons("-"), 0.0)


class CroatiaAgeTest(unittest.TestCase):
    def test_sheet_20_reads_the_all_settlements_rows(self):
        header = ("Županija", "", "", "", "Grad/općina", "Tip naselja", "", "Spol", "Sex",
                  "Ukupno\nTotal", "0 – 4", "5 i više")
        rows = [("20.",), header,
                ("Istarska", "Grad", "Istria", "Town", "Pula", "Ukupno", "Total", "sv.", "All", 10, 6, 4),
                ("Istarska", "Grad", "Istria", "Town", "Pula", "Ukupno", "Total", "m", "M", 5, 2, 3),
                ("Istarska", "Grad", "Istria", "Town", "Pula", "Ukupno", "Total", "ž", "W", 5, 2, 3),
                ("Istarska", "Grad", "Istria", "Town", "Pula", "U gradskim naseljima", "", "sv.", "All",
                 9, 4, 5)]
        ages = croatia.parse_ages(rows)
        unit = ages[("Istarska", "Grad", "Pula")]
        self.assertEqual((unit["total"], unit["men"], unit["women"]), (10, 5, 5))
        fields = croatia.age_fields(unit)
        self.assertEqual(fields["sex_ratio"]["value"], 100.0)
        self.assertEqual(fields["median_age"]["value"], 4.2)


if __name__ == "__main__":
    unittest.main()
