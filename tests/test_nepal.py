"""Nepal NPHC 2021: the annex parser and the checks that gate it.

The fixtures are the report's own layout, taken from the published tables:
an area name alone on a line, a total row, then one row per group with three
figures. pypdf is not needed here -- text extraction is the one part of the
adapter that touches it, and these tests start from the lines it would return.
"""

import unittest

from scripts.fetch_census import nepal


ETHNICITY = """
Annex 1: Population by caste/ethnicity and sex, NPHC 2021
Caste/ethinicity Area
Population Total Male Female
Nepal
All Castes 29164578 14253551 14911027
Kshetri 4796995 2308120 2488875
Brahman - Hill 3292373 1607450 1684923
Magar 2013498 949105 1064393
Tharu 1807124 880513 926611
Tamang 1639866 800763 839103
Everyone else 15614722 7707697 7907025
37
Koshi
All Castes 4961412 2417328 2544084
Kshetri 744076 359283 384793
Everyone else 4217336 2058045 2159291
41
Taplejung
All Castes 120590 60773 59817
Yakthung/Limbu 51372 25887 25485
Sherpa 14443 7074 7369
Everyone else 54775 27812 26963
""".strip().splitlines()

RELIGION = """
Annex 9: Population by religion and sex, NPHC 2021
Area
Religion Population Total Male Female
Nepal
All Religions 29164578 14253551 14911027
Hindu 23677744 11500000 12177744
Bouddha 2393549 1150000 1243549
Islam 1483066 730000 753066
Kirat 924204 450000 474204
Christian 512313 250000 262313
Other 173702 173551 151
Taplejung
All Religions 120590 60773 59817
Kirat 60000 30000 30000
Hindu 55590 28000 27590
Bouddha 5000 2773 2227
""".strip().splitlines()


class Parsing(unittest.TestCase):
    def test_areas_and_counts(self):
        got = nepal.parse_annex(ETHNICITY, nepal.ANNEXES["ethnicity"])
        self.assertEqual(set(got), {"Nepal", "Koshi", "Taplejung"})
        self.assertEqual(got["Nepal"]["_total"], 29164578)
        self.assertEqual(got["Nepal"]["Kshetri"], 4796995)
        self.assertEqual(got["Taplejung"]["Yakthung/Limbu"], 51372)

    def test_a_bare_page_number_is_not_an_area(self):
        got = nepal.parse_annex(ETHNICITY, nepal.ANNEXES["ethnicity"])
        self.assertNotIn("37", got)
        self.assertNotIn("41", got)

    def test_only_the_named_annex_is_read(self):
        # Both annexes in one stream: asking for religion must not pick up
        # caste rows, which is what a title-blind parser would do.
        got = nepal.parse_annex(ETHNICITY + RELIGION, nepal.ANNEXES["religion"])
        self.assertEqual(set(got), {"Nepal", "Taplejung"})
        self.assertEqual(got["Nepal"]["Hindu"], 23677744)
        self.assertNotIn("Kshetri", got["Nepal"])

    def test_an_unknown_area_name_is_refused(self):
        lines = list(ETHNICITY)
        lines.insert(-1, "Some Place That Is Not In Nepal")
        got = nepal.parse_annex(lines, nepal.ANNEXES["ethnicity"])
        self.assertNotIn("Some Place That Is Not In Nepal", got)

    def test_the_boundary_files_spelling_reaches_the_census_name(self):
        self.assertEqual(nepal.canonical_area("Chitawan"), "Chitwan")
        self.assertEqual(nepal.canonical_area("Rukum_E"), "Rukum East")
        self.assertEqual(nepal.canonical_area("Province 1"), "Koshi")


class Checks(unittest.TestCase):
    def test_the_published_national_figures_are_required(self):
        areas = nepal.parse_annex(ETHNICITY, nepal.ANNEXES["ethnicity"])
        nepal.check_national("ethnicity", areas)   # does not raise

    def test_a_changed_edition_stops_the_run(self):
        areas = nepal.parse_annex(ETHNICITY, nepal.ANNEXES["ethnicity"])
        areas["Nepal"]["Kshetri"] = 4_000_000
        with self.assertRaises(SystemExit):
            nepal.check_national("ethnicity", areas)

    def test_a_dropped_row_is_caught_by_the_printed_total(self):
        # The shares would still sum to 100%, because they are computed from
        # what was read. Only the annex's own total notices.
        areas = nepal.parse_annex(ETHNICITY, nepal.ANNEXES["ethnicity"])
        del areas["Taplejung"]["Sherpa"]
        with self.assertRaises(SystemExit):
            nepal.check_sums("ethnicity", areas)

    def test_an_annex_with_no_nepal_row_is_refused(self):
        with self.assertRaises(SystemExit):
            nepal.check_national("ethnicity", {"Koshi": {"_total": 1}})


class Composition(unittest.TestCase):
    def test_shares_are_of_the_printed_total(self):
        areas = nepal.parse_annex(ETHNICITY, nepal.ANNEXES["ethnicity"])
        got = nepal.compose(areas["Taplejung"], min_pct=0.1)
        by_name = {row["group"]: row["pct"] for row in got}
        self.assertAlmostEqual(by_name["Yakthung/Limbu"], 42.6, places=1)
        self.assertAlmostEqual(sum(r["pct"] for r in got), 100.0, places=0)


class Withholding(unittest.TestCase):
    def test_the_districts_with_no_trustworthy_shape_are_named(self):
        # Not a judgement call at build time: these are the districts whose
        # territory the boundary file puts inside a differently-named polygon,
        # or whose name it carries twice.
        for district in ("Rupandehi", "Dailekh", "Siraha", "Parsa",
                         "Bara", "Saptari", "Nawalpur"):
            self.assertIn(district, nepal.UNJOINABLE)

    def test_every_district_belongs_to_exactly_one_province(self):
        seen = [d for names in nepal.DISTRICTS.values() for d in names]
        self.assertEqual(len(seen), 77)
        self.assertEqual(len(set(seen)), 77)

    def test_every_withheld_district_is_a_real_district(self):
        known = {d for names in nepal.DISTRICTS.values() for d in names}
        self.assertTrue(set(nepal.UNJOINABLE) <= known)


if __name__ == "__main__":
    unittest.main()
