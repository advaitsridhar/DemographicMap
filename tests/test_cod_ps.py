"""COD-PS: the licence test, the column shapes, and which level a file names."""

from __future__ import annotations

import sys
import unittest
from unittest import mock
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
    """There is no one schema, so the column is recognised by its shape.

    The first version matched ^ADM2_[A-Z]{2}$ and refused fifteen files whose
    only fault was spelling. Every pattern below was taken from the run log of
    21 September 2026, not invented.
    """

    SCHEMAS = [
        (["ADM2_EN", "ADM2_RO", "ADM2_PCODE", "T_TL"], "ADM2_EN"),
        (["ADM2_RO", "ADM2_PCODE"], "ADM2_RO"),
        (["ADM2_NAME", "ADM2_PCODE"], "ADM2_NAME"),
        (["admin2Name_en", "admin2Pcode", "admin1Name_en"], "admin2Name_en"),
        (["admin2Name_fr", "admin2Pcode", "admin2RefName",
          "admin2AltName1_fr"], "admin2Name_fr"),
        (["Adm2_name", "Adm2_Pcode"], "Adm2_name"),
        (["adm2_Pcode", "adm2_Name"], "adm2_Name"),
        (["district_code", "district_name", "province_name"], "district_name"),
        (["ADM2_NAME", "ADM2_NAME_SI", "ADM2_NAME_TA",
          "ADM2_PCODE"], "ADM2_NAME"),
        (["admin2Name_ru", "admin2Name_en", "admin2Type_ru"], "admin2Name_en"),
    ]

    def test_every_schema_the_catalogue_actually_uses(self):
        for columns, want in self.SCHEMAS:
            with self.subTest(columns=columns[0]):
                self.assertEqual(m.name_column(columns, "2"), want)

    def test_english_wins_where_a_file_carries_several_languages(self):
        # Kyrgyzstan carries Russian and English; Sri Lanka carries Sinhala
        # and Tamil beside an unqualified name that is already English. A
        # transliteration where the boundary file has English joins nothing.
        self.assertEqual(
            m.name_column(["ADM1_EN", "ADM1_NAME_SI", "ADM1_NAME_TA"], "1"),
            "ADM1_EN")

    def test_a_code_or_a_type_or_an_alternate_is_never_the_name(self):
        self.assertIsNone(m.name_column(["ADM2_PCODE", "T_TL"], "2"))
        self.assertIsNone(m.name_column(["admin2Type_ru", "admin2Pcode"], "2"))
        self.assertIsNone(m.name_column(["admin2RefName"], "2"))

    def test_the_levels_are_not_confused_with_each_other(self):
        columns = ["ADM1_EN", "ADM2_EN"]
        self.assertEqual(m.name_column(columns, "1"), "ADM1_EN")
        self.assertEqual(m.name_column(columns, "2"), "ADM2_EN")

    def test_the_total_is_T_TL_or_the_written_out_form(self):
        self.assertEqual(m.total_column(["ADM2_EN", "T_TL"]), "T_TL")
        self.assertEqual(m.total_column(["population_total"]), "population_total")
        self.assertIsNone(m.total_column(["F_TL", "M_TL"]))

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


class DistrictTablesByName(unittest.TestCase):
    def test_admpop2_is_a_district_table(self):
        from scripts.fetch_census import cod_ps
        res = cod_ps.adm2_resource({"resources": [
            {"name": "CMR_admpop_adm1_2025.csv"}, {"name": "CMR_admpop2_2025.csv"}]})
        self.assertEqual(res["name"], "CMR_admpop2_2025.csv")

    def test_a_workbook_when_there_is_no_district_csv(self):
        from scripts.fetch_census import cod_ps
        res = cod_ps.adm2_resource({"resources": [
            {"name": "KEN_AdminBoundaries_TabularData.xlsx"},
            {"name": "ken_admpop_2019.xlsx"}, {"name": "ken_admpop_adm1_2019.csv"}]})
        self.assertEqual(res["name"], "ken_admpop_2019.xlsx")

    def test_the_district_sheet_is_read(self):
        import io
        import openpyxl
        from scripts.fetch_census import cod_ps
        book = openpyxl.Workbook()
        book.active.title = "ken_admpop_adm1_2019"
        book.active.append(["ADM1_EN", "T_TL"])
        sheet = book.create_sheet("ken_admpop_adm2_2019")
        sheet.append(["ADM2_EN", "ADM2_PCODE", "ADM1_EN", "T_TL"])
        sheet.append(["Ainabkoi", "KE027144", "Uasin Gishu", 138_192])
        sheet.append([None, None, None, None])
        buf = io.BytesIO()
        book.save(buf)
        columns, rows, title = cod_ps.workbook_rows(buf.getvalue())
        self.assertEqual(title, "ken_admpop_adm2_2019")
        self.assertEqual(columns, ["ADM2_EN", "ADM2_PCODE", "ADM1_EN", "T_TL"])
        self.assertEqual(rows, [{"ADM2_EN": "Ainabkoi", "ADM2_PCODE": "KE027144",
                                 "ADM1_EN": "Uasin Gishu", "T_TL": "138192"}])


class OneLevelDown(unittest.TestCase):
    def test_the_next_table_is_asked_when_the_district_table_is_not_the_maps(self):
        from scripts.fetch_census import cod_ps
        package = {"name": "cod-ps-slv", "groups": [{"name": "slv"}],
                   "license_id": "cc-by-igo", "license_title": "CC BY-IGO",
                   "resources": [{"name": "slv_admpop_adm2_2024.csv", "url": "a"},
                                 {"name": "slv_admpop_adm3_2024.csv", "url": "b"}]}
        tables = {
            "a": (["ADM2_ES", "ADM1_ES", "T_TL"],
                  [{"ADM2_ES": "La Libertad Sur", "ADM1_ES": "La Libertad", "T_TL": "5"}],
                  "slv_admpop_adm2_2024.csv"),
            "b": (["ADM3_ES", "ADM1_ES", "T_TL"],
                  [{"ADM3_ES": "Acajutla", "ADM1_ES": "Sonsonate", "T_TL": "52000"}],
                  "slv_admpop_adm3_2024.csv"),
        }
        with mock.patch.object(cod_ps, "read_table", side_effect=lambda r: tables[r["url"]]), \
             mock.patch.object(cod_ps, "shape_names",
                               side_effect=lambda code, level: {"acajutla"} if level == "admin2" else set()), \
             mock.patch.object(cod_ps, "MIN_LEVEL_NAMES", 1):
            out = cod_ps.country_records(package)
        self.assertEqual([(r["name"], r["level"]) for r in out], [("Acajutla", "admin2")])
        self.assertEqual(out[0]["population"], {"value": 52000, "year": 2024,
                                                "source": out[0]["population"]["source"]})

    def test_a_single_year_reference_period_supplies_a_missing_year(self):
        from scripts.fetch_census import cod_ps
        self.assertEqual(cod_ps.dataset_year(
            {"dataset_date": "[2018-01-01T00:00:00 TO 2018-12-31T23:59:59]"}), 2018)
        self.assertIsNone(cod_ps.dataset_year(
            {"dataset_date": "[2015-01-01T00:00:00 TO 2020-12-31T23:59:59]"}))


class LevelNeedsEvidence(unittest.TestCase):
    def test_a_tie_or_a_handful_is_refused(self):
        from scripts.fetch_census import cod_ps
        names = {"admin1": {"a", "b"}, "admin2": {"c", "d"}}
        with mock.patch.object(cod_ps, "shape_names", side_effect=lambda c, l: names[l]):
            self.assertIsNone(cod_ps.which_level("KGZ", ["a", "b", "c", "d"])[0])
        # Half of eight is above the 40% bar and still only four names.
        names = {"admin1": set(), "admin2": {"a", "b", "c", "d"}}
        with mock.patch.object(cod_ps, "shape_names", side_effect=lambda c, l: names[l]):
            self.assertIsNone(cod_ps.which_level("KGZ", list("abcdefgh"))[0])
            # A table of three that all match is a small country, not a handful.
            self.assertEqual(cod_ps.which_level("KGZ", ["a", "b", "c"])[0], "admin2")
