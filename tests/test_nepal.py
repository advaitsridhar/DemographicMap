"""Nepal NPHC 2021: the annex parser and the checks that gate it.

The fixtures are the report's own layout, taken from the published tables:
an area name alone on a line, a total row, then one row per group with three
figures. pypdf is not needed here -- text extraction is the one part of the
adapter that touches it, and these tests start from the lines it would return.
"""

import unittest

from scripts.fetch_census import nepal


ETHNICITY = """
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

# Annex 5 is a wide cross-tab, not a long table: a header naming the ten
# religions, the area in capitals, then Total, Male and Female rows.
RELIGION = """
Annex 5:  Population by Religion and sex,  NPHC 2021
Hindu Bouddha Islam Kirat Christian Prakriti Bon Jain Bahai Sikha
NEPAL
Total 29164578 23677744 2393549 1483066 924204 512313 102048 67223 2398 537 1496
Male 14253551 11587529 1159790 732006 451193 240206 48527 31968 1239 234 859
Female 14911027 12090215 1233759 751060 473011 272107 53521 35255 1159 303 637
TAPLEJUNG
Total 120590 36717 26496 112 53328 3134 10 792 1 0 0
Male 60773 18726 13053 112 26933 1556 5 387 1 0 0
Female 59817 17991 13443 0 26395 1578 5 405 0 0 0
""".strip().splitlines()

# Annex 2, which shares annex 1's shape but opens each area differently.
LANGUAGE = """
Nepal
All MTongues 29164578 14253551 14911027
Nepali 13084457 6300000 6784457
Maithili 3222389 1580000 1642389
Bhojpuri 1820795 900000 920795
Tharu 1714091 840000 874091
Tamang 1423075 700000 723075
Everyone else 7899771 3933551 3966220
Taplejung
All MTongues 120590 60773 59817
Yakthung/Limbu 60000 30000 30000
Nepali 40590 20773 19817
Everyone else 20000 10000 10000
""".strip().splitlines()


class Parsing(unittest.TestCase):
    def test_areas_and_counts(self):
        got = nepal.parse_long(ETHNICITY)["ethnicity"]
        self.assertEqual(set(got), {"Nepal", "Koshi", "Taplejung"})
        self.assertEqual(got["Nepal"]["_total"], 29164578)
        self.assertEqual(got["Nepal"]["Kshetri"], 4796995)
        self.assertEqual(got["Taplejung"]["Yakthung/Limbu"], 51372)

    def test_a_bare_page_number_is_not_an_area(self):
        got = nepal.parse_long(ETHNICITY)["ethnicity"]
        self.assertNotIn("37", got)
        self.assertNotIn("41", got)

    def test_the_two_long_annexes_do_not_bleed_into_each_other(self):
        # Which annex a row belongs to is decided by the total label above it,
        # not by the page heading, which the extractor emits after its rows.
        got = nepal.parse_long(ETHNICITY + LANGUAGE)
        self.assertEqual(got["ethnicity"]["Nepal"]["Kshetri"], 4796995)
        self.assertNotIn("Kshetri", got["language"]["Nepal"])
        self.assertEqual(got["language"]["Nepal"]["Nepali"], 13084457)
        self.assertNotIn("Nepali", got["ethnicity"]["Nepal"])

    def test_rows_after_an_annex_ends_are_not_absorbed(self):
        # Annexes 3 and 4 have no "All ..." row, so their rows used to pile
        # onto whichever area annex 2 ended on.
        trailing = LANGUAGE + ["Taplejung", "Total 120590 60773 59817",
                               "Nepali 99999 50000 49999"]
        got = nepal.parse_long(trailing)["language"]
        self.assertEqual(got["Taplejung"]["Nepali"], 40590)

    def test_an_unknown_area_name_is_refused(self):
        lines = list(ETHNICITY)
        lines.insert(-1, "Some Place That Is Not In Nepal")
        got = nepal.parse_long(lines)["ethnicity"]
        self.assertNotIn("Some Place That Is Not In Nepal", got)

    def test_the_boundary_files_spelling_reaches_the_census_name(self):
        self.assertEqual(nepal.canonical_area("Chitawan"), "Chitwan")
        self.assertEqual(nepal.canonical_area("Rukum_E"), "Rukum East")
        self.assertEqual(nepal.canonical_area("Province 1"), "Koshi")

    def test_the_census_own_names_for_the_split_districts(self):
        self.assertEqual(
            nepal.canonical_area("Nawalparasi (Bardaghat Susta East)"),
            "Nawalpur")
        self.assertEqual(
            nepal.canonical_area("Nawalparasi (Bardaghat Susta West)"),
            "Parasi")


class ReligionCrossTab(unittest.TestCase):
    def test_the_header_gives_the_column_order(self):
        got = nepal.parse_religion(RELIGION)
        self.assertEqual(set(got), {"Nepal", "Taplejung"})
        self.assertEqual(got["Nepal"]["Hindu"], 23677744)
        self.assertEqual(got["Nepal"]["Sikha"], 1496)
        self.assertEqual(got["Nepal"]["_total"], 29164578)

    def test_kirat_is_the_largest_religion_in_taplejung(self):
        got = nepal.parse_religion(RELIGION)
        self.assertEqual(got["Taplejung"]["Kirat"], 53328)

    def test_male_and_female_rows_are_not_read_as_areas(self):
        got = nepal.parse_religion(RELIGION)
        self.assertEqual(got["Nepal"]["_total"], 29164578)
        self.assertNotIn("Male", got)


class LetterSpacing(unittest.TestCase):
    """Rows the extractor justified glyph by glyph.

    "T h a r u 9 47 12 3" is "Tharu 94 71 23". Read naively the row parser
    takes the last three runs -- 47, 12 and 3 -- which is a wrong number that
    looks like a right one, and only the area's printed total notices.
    """

    def test_a_justified_row_is_recognised(self):
        self.assertTrue(nepal.letter_spaced("T h a r u 9 47 12 3"))
        self.assertFalse(nepal.letter_spaced("Tharu 94 71 23"))
        self.assertFalse(nepal.letter_spaced("Brahman - Hill 3292373 1 2"))

    def test_the_figures_come_back_from_total_equals_male_plus_female(self):
        self.assertEqual(nepal.split_figures("947123"), (94, 71, 23))
        self.assertEqual(nepal.split_figures("463115"), (46, 31, 15))
        self.assertEqual(nepal.split_figures("713734"), (71, 37, 34))

    def test_an_ambiguous_run_is_refused_rather_than_guessed(self):
        # 110 = 100 + 10 and 11 = 1 + 10 both hold for "1101 0"; refusing is
        # the only safe answer, and the caller stops the run.
        self.assertIsNone(nepal.split_figures("110100"))

    def test_a_justified_row_is_restored_with_its_ordinary_spelling(self):
        lines = ETHNICITY + ["Panchthar", "All Castes 300 200 100",
                             "B r a h m a n - H i l l 3 00 20 0 10 0"]
        got = nepal.parse_long(lines)["ethnicity"]["Panchthar"]
        self.assertIn("Brahman - Hill", got)
        self.assertEqual(got["Brahman - Hill"], 300)


class Checks(unittest.TestCase):
    def test_the_published_national_figures_are_required(self):
        areas = nepal.parse_long(ETHNICITY)["ethnicity"]
        nepal.check_national("ethnicity", areas)   # does not raise

    def test_a_changed_edition_stops_the_run(self):
        areas = nepal.parse_long(ETHNICITY)["ethnicity"]
        areas["Nepal"]["Kshetri"] = 4_000_000
        with self.assertRaises(SystemExit):
            nepal.check_national("ethnicity", areas)

    def test_a_dropped_row_is_caught_by_the_printed_total(self):
        # The shares would still sum to 100%, because they are computed from
        # what was read. Only the annex's own total notices.
        areas = nepal.parse_long(ETHNICITY)["ethnicity"]
        del areas["Taplejung"]["Sherpa"]
        with self.assertRaises(SystemExit):
            nepal.check_sums("ethnicity", areas)

    def test_an_annex_with_no_nepal_row_is_refused(self):
        with self.assertRaises(SystemExit):
            nepal.check_national("ethnicity", {"Koshi": {"_total": 1}})


class Composition(unittest.TestCase):
    def test_shares_are_of_the_printed_total(self):
        areas = nepal.parse_long(ETHNICITY)["ethnicity"]
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
