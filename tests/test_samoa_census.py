"""Samoa's 2021 census by the 2016 census's villages: nesting, matching, columns.

The fixtures are rows in the workbooks' shape -- names indented four spaces a
level -- cut down to a few villages; no network.
"""

import unittest

from scripts.fetch_census import samoa_census as sm


class Places(unittest.TestCase):
    def test_depth_is_the_indent(self):
        rows = [["Samoa", 10], ["    Savaii", 10], ["        Salega 1", 10],
                ["            Sagone", 4], [None, None]]
        got = sm.places(rows, 0)
        self.assertEqual([(d, n) for d, n, _ in got],
                         [(0, "Samoa"), (4, "Savaii"), (8, "Salega 1"), (12, "Sagone")])


OLD = [(("Rest of Upolu", "Safata"), "Fusi", 738), (("Rest of Upolu", "Safata"), "Lotofaga", 300),
       (("Rest of Upolu", "Safata"), "Saanapu Tai", 500),
       (("Rest of Upolu", "Lotofaga"), "Lotofaga", 900),
       (("Rest of Upolu", "Lotofaga"), "Vavau", 400),
       (("Rest of Upolu", "Anoamaa West"), "Fusi", 396),
       (("Apia Urban Area", "Faleata East"), "Tuanaimato East", 493),
       (("Apia Urban Area", "Faleata East"), "Moamoa", 1396)]


class Villages(unittest.TestCase):
    def test_a_renamed_village_finds_its_2016_district(self):
        new = [("Safata 2", "Fusi Safata", [833]), ("Anoamaa 2", "Fusi Anoamaa", [428])]
        placed, _ = sm.place_villages(OLD, new)
        self.assertEqual(placed[("Safata 2", "Fusi Safata")], ("Rest of Upolu", "Safata"))
        self.assertEqual(placed[("Anoamaa 2", "Fusi Anoamaa")], ("Rest of Upolu", "Anoamaa West"))

    def test_a_shared_name_goes_with_its_constituency(self):
        new = [("Safata 1", "Saanapu Tai", [500]), ("Safata 1", "Lotofaga", [310]),
               ("Lotofaga", "Vavau", [410]), ("Lotofaga", "Lotofaga", [950])]
        placed, _ = sm.place_villages(OLD, new)
        self.assertEqual(placed[("Safata 1", "Lotofaga")], ("Rest of Upolu", "Safata"))
        self.assertEqual(placed[("Lotofaga", "Lotofaga")], ("Rest of Upolu", "Lotofaga"))

    def test_a_new_village_goes_with_its_constituency_and_is_named(self):
        new = [("Faleata 1", "Moamoa", [1442]), ("Faleata 1", "Tunaimato West", [59])]
        placed, fresh = sm.place_villages(OLD, new)
        self.assertEqual(placed[("Faleata 1", "Tunaimato West")],
                         ("Apia Urban Area", "Faleata East"))
        self.assertEqual(len(fresh), 1)

    def test_a_village_with_nothing_to_go_by_stops_the_run(self):
        with self.assertRaises(SystemExit):
            sm.place_villages(OLD, [("Nowhere 1", "Unheard Of", [5])])


class Columns(unittest.TestCase):
    def test_ages_and_the_unknown_column(self):
        header = ["Place", "Total", None, None, "age 0", None, None, "age 1", None, None,
                  "DK", None, None]
        ages, unknown = sm.age_columns(header)
        self.assertEqual(ages, [(0, 4), (1, 7)])
        self.assertEqual(unknown, 10)

    def test_ages_that_skip_a_year_stop_the_run(self):
        with self.assertRaises(SystemExit):
            sm.age_columns(["Place", "Total", None, None, "age 0", None, None, "age 2"])

    def test_denominations_are_named_and_kept_apart(self):
        header = ["Place", "TOTAL", None, None, "CONGREGATIONAL CHRISTIAN CHURCH", None, None,
                  "LATTER  DAY SAINTS", None, None, "CONGREGATIONAL CHRISTIAN CHURCH", None,
                  None, "MUSLIM"]
        got = sm.religion_columns(header)
        self.assertEqual([n for n, _ in got],
                         ["Congregational Christian Church",
                          "Church of Jesus Christ of Latter-day Saints",
                          "Congregational Christian Church (2)", "Islam"])
        self.assertEqual([i for _, i in got], [4, 7, 10, 13])


# Table 8a's national row and Moataa's as the 2021 workbook prints them; the rest of
# the country is one village here, so that every sum the reader checks holds.
SAMOA_8A = [205557, 104853, 100704, 200508, 102245, 98263, 3127, 1572, 1555, 704, 364, 340,
            1218, 672, 546]
MOATAA_8A = [1420, 715, 705, 1383, 691, 692, 27, 16, 11, 8, 6, 2, 2, 2, 0]
HEADING_8A = ["Place of residence", "Total", None, None,
              "YES BORN IN SAMOA WITH CITIZEN PARENT(S)", None, None,
              "YES BORN ABROAD OF SAMOA WITH CITIZEN PARENT(S)", None, None,
              "YES SAMOA  CITIZEN BY NATURALISATION", None, None,
              "NO NOT A CITIZEN OF SAMOA", None, None]


def table_8a(national=SAMOA_8A, moataa=MOATAA_8A, heading=HEADING_8A):
    rest = [n - m for n, m in zip(national, moataa)]
    return [["Table 8a. Total population by sex, Samoan citizenship status and place of "
             "residence,2021"], [None], heading,
            [None] + ["Total", "MALE", "FEMALE"] * 5,
            ["Samoa"] + national, ["    Apia Urban Area"] + national,
            ["        Vaimauga 2"] + national, ["            Moataa"] + moataa,
            ["            Everywhere else"] + rest]


class Citizenship(unittest.TestCase):
    def test_the_answers_add_up_and_become_two_groups(self):
        got = sm.read_citizenship(table_8a())
        moataa = next(v for _, name, v in got["villages"] if name == "Moataa")
        fields = sm.citizenship_fields([moataa[i] for i in (0, 3, 6, 9, 12)])
        self.assertEqual(fields["ethnicity"], [
            {"group": "Samoan", "pct": 99.9, "count": 1418},
            {"group": "Foreign nationals", "pct": 0.1, "count": 2}])
        self.assertEqual(fields["ethnicity_basis"], "nationality")
        self.assertEqual(fields["ethnicity_year"], 2021)
        self.assertIn("not ethnicity", fields["ethnicity_note"])

    def test_answers_headed_out_of_order_stop_the_run(self):
        heading = list(HEADING_8A)
        heading[7], heading[10] = heading[10], heading[7]
        with self.assertRaises(SystemExit):
            sm.read_citizenship(table_8a(heading=heading))

    def test_answers_that_miss_their_total_stop_the_run(self):
        moataa = list(MOATAA_8A)
        moataa[12] += 1                       # one more non-citizen, the total unchanged
        moataa[13] += 1
        with self.assertRaises(SystemExit):
            sm.read_citizenship(table_8a(moataa=moataa))

    def test_a_country_the_fact_sheet_counts_otherwise_stops_the_run(self):
        national = list(SAMOA_8A)             # one non-citizen read as naturalised
        national[9] += 1
        national[10] += 1
        national[12] -= 1
        national[13] -= 1
        with self.assertRaises(SystemExit):
            sm.read_citizenship(table_8a(national=national))


class NationalMedians(unittest.TestCase):
    """Table 1's single years against the Bureau's own medians for the sexes."""

    @staticmethod
    def table(male_ages, female_ages):
        """(sub-header, the country's figures, ages_at) in Table 1's layout."""
        top = max(male_ages + female_ages)
        header = ["Place of residence", "Total", "", ""]
        sub = ["", "Total", "MALE", "FEMALE"]
        nation = [0, 0, 0]
        for age in range(top + 1):
            header += [f"age {age}", "", ""]
            sub += ["Total", "MALE", "FEMALE"]
            males = 10 if age in male_ages else 0
            females = 10 if age in female_ages else 0
            nation += [males + females, males, females]
        ages_at, _ = sm.age_columns(header)
        return sub, nation, ages_at

    def test_the_sexes_agree_with_the_bureaus_whole_years(self):
        # Ten a year: males 0-40 (median 20.5), females 0-42 (median 21.5).
        sub, nation, ages_at = self.table(list(range(41)), list(range(43)))
        account = sm.national_medians(sub, nation, ages_at)
        self.assertIn("males 20.5 (printed 20)", account)
        self.assertIn("females 21.5 (printed 21)", account)
        self.assertIn("outside the sexes'", account)

    def test_a_sex_a_year_and_more_away_stops_the_run(self):
        sub, nation, ages_at = self.table(list(range(41)), list(range(45)))   # females 22.5
        with self.assertRaises(SystemExit):
            sm.national_medians(sub, nation, ages_at)

    def test_columns_that_are_not_total_male_female_stop_the_run(self):
        sub, nation, ages_at = self.table(list(range(41)), list(range(43)))
        sub[5], sub[6] = "FEMALE", "MALE"
        with self.assertRaises(SystemExit):
            sm.national_medians(sub, nation, ages_at)


if __name__ == "__main__":
    unittest.main()
