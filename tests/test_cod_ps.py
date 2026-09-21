"""COD-PS: the licence test, the column shapes, and which level a file names."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_census import cod_ps as m  # noqa: E402


class TheLicenceTest(unittest.TestCase):
    """Counted by what the licence says, never by CKAN's isopen flag.

    The first probe reported "8 of 148 carry an open licence" off that flag.
    132 of the 148 are CC BY-IGO, which HDX marks isopen=False only because
    CKAN's registry does not list it; this map has read cod-ps-png under it
    since before this file existed.
    """

    def test_cc_by_igo_is_readable_although_hdx_calls_it_not_open(self):
        self.assertTrue(m.is_usable({"license_id": "cc-by-igo", "isopen": False}))

    def test_cc_by_is_readable(self):
        self.assertTrue(m.is_usable({"license_id": "cc-by", "isopen": True}))

    def test_humanitarian_use_only_is_refused(self):
        # cod-ps-idn and four others. This is the one that taught the project
        # to read the licence of every dataset on every run.
        self.assertFalse(m.is_usable({"license_id": "hdx-other",
                                      "license_other": "humanitarian use only"}))

    def test_a_dataset_with_no_licence_is_refused(self):
        self.assertFalse(m.is_usable({"license_id": None}))
        self.assertFalse(m.is_usable({}))


class TheColumns(unittest.TestCase):
    """The name column carries its language, so it is matched by shape."""

    def test_english_is_preferred_where_a_file_has_both(self):
        columns = ["ADM1_EN", "ADM1_PCODE", "ADM2_RO", "ADM2_EN", "T_TL"]
        self.assertEqual(m.name_column(columns, "2"), "ADM2_EN")

    def test_another_language_is_taken_when_there_is_no_english(self):
        # Romania writes ADM2_RO and nothing else.
        self.assertEqual(m.name_column(["ADM2_RO", "ADM2_PCODE"], "2"), "ADM2_RO")

    def test_a_pcode_is_not_a_name(self):
        self.assertIsNone(m.name_column(["ADM2_PCODE", "T_TL"], "2"))

    def test_the_year_comes_from_the_column_or_the_filename(self):
        rows = [{"year": "2022"}, {"year": "2022"}]
        self.assertEqual(m.reference_year(["year"], rows, "x.csv"), 2022)
        # Iran's file states it only in its own name.
        self.assertEqual(
            m.reference_year([], [], "irn_admpop_adm2_2016_v2.csv"), 2016)

    def test_a_file_whose_rows_disagree_about_the_year_states_none(self):
        rows = [{"year": "2022"}, {"year": "2019"}]
        self.assertIsNone(m.reference_year(["year"], rows, "x.csv"))


class WhichLevelTheFileNames(unittest.TestCase):
    """Romania is the case: its cod-ps "adm2" is this map's first level.

    42 judete against 3,235 communes. Written as districts they would mostly
    find no shape -- survivable -- but Romanian communes are often named after
    the county town, so some would find the wrong shape and wear a county's
    population. So the level is measured against this map's own names.
    """

    def setUp(self):
        self._real = m.shape_names
        m.shape_names = lambda code, level: {
            ("XXX", "admin1"): {"alpha", "beta", "gamma"},
            ("XXX", "admin2"): {"one", "two", "three", "four", "five"},
        }.get((code, level), set())

    def tearDown(self):
        m.shape_names = self._real

    def test_names_that_match_the_districts_are_written_as_districts(self):
        level, why = m.which_level("XXX", ["One", "Two", "Three", "Four"])
        self.assertEqual(level, "admin2")
        self.assertIn("admin2", why)

    def test_names_that_match_the_first_level_are_written_there(self):
        level, _ = m.which_level("XXX", ["Alpha", "Beta", "Gamma"])
        self.assertEqual(level, "admin1")

    def test_a_file_matching_neither_is_refused_rather_than_guessed(self):
        level, why = m.which_level("XXX", ["Nowhere", "Elsewhere", "Somewhere"])
        self.assertIsNone(level)
        self.assertIn("too few of either", why)

    def test_accents_and_case_do_not_decide_it(self):
        level, _ = m.which_level("XXX", ["ÓNE", "TWÖ", "Thrée"])
        self.assertEqual(level, "admin2")
