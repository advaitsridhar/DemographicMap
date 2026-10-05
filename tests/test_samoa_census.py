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


if __name__ == "__main__":
    unittest.main()
