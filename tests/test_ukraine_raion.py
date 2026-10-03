import unittest

from shapely.geometry import box

from scripts.fetch_census import ukraine_raion as u


class Names(unittest.TestCase):
    def test_base_drops_the_oblast_the_bureau_adds(self):
        self.assertEqual(u.base("VOLODARSKYI RAION (DONETSKA OBLAST)"), "VOLODARSKYI RAION")
        self.assertEqual(u.base("VOLODARSKYI RAION (DONETSKA OBLAST"), "VOLODARSKYI RAION")

    def test_renamed_is_scoped_by_oblast_where_the_name_repeats(self):
        self.assertEqual(u.renamed("Donetsk Oblast", "VOLODARSKYI RAION (DONETSKA OBLAST)"),
                         "Nikolske")
        self.assertIsNone(u.renamed("Kyiv Oblast", "VOLODARSKYI RAION (KYIVSKA OBLAST)"))
        self.assertEqual(u.renamed("Donetsk Oblast", "ARTEMIVSKYI RAION"), "Bakhmut")

    def test_skeleton_agrees_across_vowel_shifts(self):
        self.assertTrue(u.skeleton_agrees("MEZHIVSKYI RAION", "Mezhova"))
        self.assertTrue(u.skeleton_agrees("CHORNOBAIVSKYI RAION", "Chornobai"))
        self.assertFalse(u.skeleton_agrees("LUTSKYI RAION", "Kivertsi"))

    def test_likeness_tells_namesakes_apart(self):
        self.assertGreater(u.likeness("SKOLIVSKYI RAION", "Skole"),
                           u.likeness("SKOLIVSKYI RAION", "Sokal") + u.LIKE_MARGIN)
        self.assertGreater(u.likeness("SOKALSKYI RAION", "Sokal"),
                           u.likeness("SOKALSKYI RAION", "Skole") + u.LIKE_MARGIN)
        self.assertGreater(u.likeness("HORODYSHCHENSKYI RAION", "Horodysche"), u.LIKE)

    def test_bind_raions_refuses_a_tie_and_binds_the_rest(self):
        shapes = {"Lviv Oblast": [{"id": "a", "name": "Skole"}, {"id": "b", "name": "Sokal"},
                                  {"id": "c", "name": "Busk"}]}
        rows = [(("L’VIVS’KA OBLAST’", "x"), {"nso": "SKOLIVSKYI RAION"}),
                (("L’VIVS’KA OBLAST’", "y"), {"nso": "SOKALSKYI RAION"}),
                (("L’VIVS’KA OBLAST’", "z"), {"nso": "BUSKYI RAION"})]
        bound, _ = u.bind_raions(rows, shapes)
        self.assertEqual({k[1]: v["id"] for k, v in bound.items()},
                         {"x": "a", "y": "b", "z": "c"})


class Figures(unittest.TestCase):
    def test_add_sums_rows_group_by_group(self):
        a = {"total": 10, "men": 4, "women": 6, "unstated": 0,
             "groups": [(0, 4, 5.0), (5, None, 5.0)]}
        b = {"total": 6, "men": 3, "women": 3, "unstated": 0,
             "groups": [(0, 4, 1.0), (5, None, 5.0)]}
        got = u.add([a, b])
        self.assertEqual(got["total"], 16)
        self.assertEqual(got["groups"], [(0, 4, 6.0), (5, None, 10.0)])

    def test_age_fields_reads_the_median_and_ratio(self):
        row = {"total": 100, "men": 40, "women": 60, "unstated": 0,
               "groups": [(0, 9, 50.0), (10, 19, 50.0), (20, None, 0.0)]}
        got = u.age_fields(row, 2001, "src", "")
        self.assertEqual(got["median_age"]["value"], 10.0)
        self.assertEqual(got["sex_ratio"]["value"], 66.7)

    def test_a_refused_polygon_says_why_on_every_census_field(self):
        got = u.refused_record("S1", "Zmiiv", "Chuhuiv lies in it.")
        for field in ("population", "median_age", "sex_ratio", "ethnicity", "language"):
            self.assertEqual(got[field], {"status": "not_available",
                                          "note": "Chuhuiv lies in it."}, field)
        # Religion is the country's collection policy's to explain.
        self.assertNotIn("note", got["religion"])
        self.assertEqual((got["match_by"], got["shape_id"]), ("shape_id", "S1"))


class Placing(unittest.TestCase):
    """Two raions, Umanskyi and Khrystynivskyi, drawn coarsely, and the city of Uman."""

    OB = "CHERKAS’KA OBLAST’"

    def setUp(self):
        self.level2 = {
            (self.OB, "a"): {"nso": "UMANSKYI RAION", "match": "UKR_01_01"},
            (self.OB, "b"): {"nso": "KHRYSTYNIVSKYI RAION", "match": "UKR_01_02"},
            (self.OB, "c"): {"nso": "M. UMAN", "match": "UKR_01_03"},
            (self.OB, "d"): {"nso": "M. VATUTINE", "match": "UKR_01_04"},
        }
        self.by_match = {r["match"]: k for k, r in self.level2.items()}
        self.site = {"U": {"id": "U", "name": "Uman"}, "K": {"id": "K", "name": "Khrystynivka"},
                     "Z": {"id": "Z", "name": "Zvenyhorodka"}}
        self.shapes = {"Cherkasy Oblast": list(self.site.values()), "Sevastopol": []}
        self.named = {(self.OB, "a"): self.site["U"], (self.OB, "b"): self.site["K"]}

    def run_place(self, lies):
        return u.place(self.level2, self.by_match, self.named, lies,
                       set(self.by_match), self.shapes, self.site)

    def test_name_and_largest_share_agree_however_coarse(self):
        got = self.run_place({"UKR_01_01": [("U", 0.6), ("K", 0.4)],
                              "UKR_01_02": [("K", 0.55), ("U", 0.45)],
                              "UKR_01_03": [("K", 0.7), ("U", 0.3)],
                              "UKR_01_04": [("Z", 0.95)]})
        self.assertEqual(got["home"][(self.OB, "a")], "U")
        self.assertEqual(got["home"][(self.OB, "b")], "K")
        # Most of the seat's area lies next door: the outline has drawn the
        # city in Khrystynivka's polygon, so it goes nowhere, and both
        # polygons holding a quarter of it are refused.
        self.assertNotIn((self.OB, "c"), got["home"])
        self.assertIn((self.OB, "c"), got["undrawn"])
        self.assertEqual(got["outside"][(self.OB, "a")], ("M. UMAN", 0.3))
        self.assertIn("U", got["refused"])
        self.assertIn("K", got["refused"])
        self.assertEqual(got["home"][(self.OB, "d")], "Z")

    def test_a_seat_goes_with_its_raion_where_its_polygon_holds_most_of_it(self):
        got = self.run_place({"UKR_01_01": [("U", 0.6), ("K", 0.4)],
                              "UKR_01_02": [("K", 0.55), ("U", 0.45)],
                              "UKR_01_03": [("U", 0.4), ("K", 0.1)],
                              "UKR_01_04": [("Z", 0.95)]})
        self.assertEqual(got["home"][(self.OB, "c")], "U")
        self.assertEqual(got["how"][(self.OB, "c")], "seat")
        self.assertEqual(got["refused"], {})

    def test_a_quarter_of_a_seat_next_door_refuses_that_polygon(self):
        got = self.run_place({"UKR_01_01": [("U", 0.9)], "UKR_01_02": [("K", 0.9)],
                              "UKR_01_03": [("U", 0.6), ("K", 0.3)],
                              "UKR_01_04": [("Z", 0.95)]})
        self.assertEqual(got["home"][(self.OB, "c")], "U")
        self.assertIn("K", got["refused"])
        self.assertNotIn("U", got["refused"])

    def test_a_seat_drawn_little_anywhere_leaves_its_raion_alone(self):
        # A fifth of the city in a neighbour's polygon and the rest in none
        # the overlay counts (Kyiv's, or water): the raion keeps its own count.
        got = self.run_place({"UKR_01_01": [("U", 0.9)], "UKR_01_02": [("K", 0.9)],
                              "UKR_01_03": [("K", 0.2)],
                              "UKR_01_04": [("Z", 0.95)]})
        self.assertIn((self.OB, "c"), got["undrawn"])
        self.assertEqual(got["home"][(self.OB, "a")], "U")
        self.assertEqual(got["refused"], {})

    def test_a_name_on_a_neighbours_outline_refuses_the_polygon(self):
        got = self.run_place({"UKR_01_01": [("K", 0.7), ("U", 0.3)],
                              "UKR_01_02": [("K", 0.9)],
                              "UKR_01_03": [("U", 0.9)],
                              "UKR_01_04": [("Z", 0.95)]})
        self.assertIn((self.OB, "a"), got["undrawn"])
        self.assertIn("U", got["refused"])
        # Umanskyi's area placed nowhere reaches into Khrystynivka's polygon.
        self.assertIn("K", got["refused"])

    def test_a_city_split_between_polygons_refuses_the_other(self):
        got = self.run_place({"UKR_01_01": [("U", 0.9)], "UKR_01_02": [("K", 0.9)],
                              "UKR_01_03": [("U", 0.9)],
                              "UKR_01_04": [("Z", 0.6), ("K", 0.4)]})
        self.assertEqual(got["home"][(self.OB, "d")], "Z")
        self.assertIn("K", got["refused"])
        self.assertIn("Z", got["refused"])

    def test_seat_of_needs_one_clear_raion(self):
        raions = [("a", "UMANSKYI RAION"), ("b", "KHRYSTYNIVSKYI RAION")]
        self.assertEqual(u.seat_of("M. UMAN", raions), "a")
        self.assertIsNone(u.seat_of("M. VATUTINE", raions))
        self.assertEqual(u.city_name("BILA TSERKVA (MISKRADA)"), "Bila Tserkva")


class Overlay(unittest.TestCase):
    def test_shares_are_of_the_area_counted(self):
        polys = {"west": box(0, 0, 1, 1), "east": box(1, 0, 2, 1)}
        units = {"UKR_01_01": box(0.2, 0, 1.2, 1), "UKR_01_02": box(1.5, 0.5, 1.6, 0.6)}
        got = u.overlay(units, polys)
        self.assertEqual(got["UKR_01_01"][0][0], "west")
        self.assertAlmostEqual(got["UKR_01_01"][0][1], 0.8)
        self.assertEqual([h[0] for h in got["UKR_01_02"]], ["east"])


if __name__ == "__main__":
    unittest.main()
