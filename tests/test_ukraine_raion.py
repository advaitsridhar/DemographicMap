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
