"""The central European readers' parsers and checks, on small tables (no network).

One class a reader: Austria's religion survey, Switzerland's 2000 census, its
religion and language surveys and its districts, Liechtenstein, Poland,
Czechia, Slovakia's census, Hungary, Slovenia, the Netherlands' religion
survey and Luxembourg. Each fixture copies the layout the probes found.
"""

from __future__ import annotations

import io
import unittest
from collections import Counter
from unittest import mock

from scripts.fetch_census import (austria_religion, czechia_ages, hungary, liechtenstein, luxembourg,
                                  netherlands_religion, poland_ages, slovakia, slovakia_census, slovenia,
                                  switzerland, switzerland_ages, switzerland_census, switzerland_religion)


def xlsx(sheets: dict[str, list[list]]) -> bytes:
    """An .xlsx workbook's bytes, one sheet per name, rows as given."""
    import openpyxl
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


class AustrianReligionSurvey(unittest.TestCase):
    def test_thousands_are_read_with_a_decimal_comma(self):
        self.assertEqual(austria_religion.thousands("194,1"), 194100.0)

    def test_groups_below_the_offices_threshold_are_withheld_and_named(self):
        counts = {"Roman Catholic": 194100.0, "No religion": 49900.0, "Islam": 6400.0,
                  "Orthodox": 5000.0, "Other religion": 2100.0}
        kept, note = austria_religion.screen(counts, 296300.0, 8935800.0, "Burgenland")
        self.assertNotIn("Other religion", kept)
        self.assertIn("Other religion", note)
        self.assertIn("not interpretable", note)
        self.assertIn("Very uncertain", note)          # Orthodox, below 6,000
        self.assertIn("Orthodox", note.split("Very uncertain")[1])
        # 27,656 spread as the population is: Burgenland about 917
        self.assertIn("about 917 of the 27,656", note)

    def test_a_land_too_small_for_a_hundred_respondents_stops_the_run(self):
        with self.assertRaises(SystemExit):
            austria_religion.screen({"No religion": 1000.0}, 1000.0, 8935800.0, "Nowhere")


class SwissCensus2000(unittest.TestCase):
    class Sheet:
        def __init__(self, rows):
            self.rows = rows
            self.nrows = len(rows)

        def row_values(self, i):
            return self.rows[i]

    def read(self, rows):
        book = mock.Mock()
        book.sheet_by_index.return_value = self.Sheet(rows)
        with mock.patch.object(switzerland_census, "http_get", return_value=b""), \
                mock.patch("xlrd.open_workbook", return_value=book):
            return switzerland_census.read("religion")

    def header(self):
        labels = list(switzerland_census.RELIGION)
        return ["", "Total", *labels]

    def test_communes_are_read_by_their_number_and_the_country_apart(self):
        labels = list(switzerland_census.RELIGION)
        row = [1.0] * len(labels)
        rows = [self.header(), ["Schweiz", float(len(labels)), *row],
                ["1 Aeugst am Albis", float(len(labels)), *row]]
        communes, national, names = self.read(rows)
        self.assertEqual(list(communes), ["1"])
        self.assertEqual(names["1"], "Aeugst am Albis")
        self.assertEqual(national["Total"], float(len(labels)))

    def test_a_commune_whose_categories_miss_its_total_stops_the_run(self):
        labels = list(switzerland_census.RELIGION)
        rows = [self.header(), ["1 Aeugst am Albis", 999.0, *([1.0] * len(labels))]]
        with self.assertRaises(SystemExit):
            self.read(rows)

    def test_a_dash_is_nobody_and_an_apostrophe_a_thousands_mark(self):
        self.assertEqual(switzerland_census.number("-"), 0.0)
        self.assertEqual(switzerland_census.number("1'234"), 1234.0)


class SwissReligionSurvey(unittest.TestCase):
    STRATA = [["Schichtung Personen Strukturerhebung 2024"],
              [None, "Schicht", "Berücksichtigte Bevölkerung", "Stichprobenanteil"],
              [None, "AI00", 13808, 0.0277375435],
              [None, "ZH00", 884470, 0.0276414124], [None, "ZHZH", 363283, 0.0266211191]]

    def test_the_sample_drawn_is_population_times_rate_summed_over_a_cantons_strata(self):
        with mock.patch.object(switzerland_religion, "CANTONS", {"AI": "Appenzell Innerrhoden",
                                                                 "ZH": "Zürich"}):
            drawn = switzerland_religion.read_strata(self.STRATA)
        self.assertAlmostEqual(drawn["Appenzell Innerrhoden"], 383.0, delta=0.5)
        self.assertAlmostEqual(drawn["Zürich"], 884470 * 0.0276414124 + 363283 * 0.0266211191)

    def test_a_canton_missing_from_the_strata_stops_the_run(self):
        with self.assertRaises(SystemExit):
            switzerland_religion.read_strata(self.STRATA)

    def test_suppressed_cells_are_none_and_intervals_sit_beside_their_estimate(self):
        rows = [["Religionszugehörigkeit"],
                [None, "Total", "Römisch-katholisch", None, "Andere Religionsgemeinschaften", None],
                [None, "Anzahl", "Anzahl", "± in %", "Anzahl", "± in %"],
                ["Uri", 31000, 25000, 2.5, "X", "X"]]
        blob = xlsx({"2024": rows})
        with mock.patch.object(switzerland_religion, "http_get", return_value=blob):
            table = switzerland_religion.read(2024)
        self.assertEqual(table["Uri"]["Römisch-katholisch"], (25000.0, 2.5))
        self.assertEqual(table["Uri"]["Andere Religionsgemeinschaften"][0], None)


class SwissLanguageSurvey(unittest.TestCase):
    CANTON = {"name": "Uri", "total": 37000.0, "counts": {"German": 35000.0}, "dropped": []}

    def test_it_is_written_as_a_survey_estimate_and_writes_no_population(self):
        (rec,) = switzerland.build([self.CANTON], {"Uri": 904.0})
        self.assertTrue(rec["language_basis"].startswith("survey estimate"))
        self.assertIn("about 904 people", rec["language_note"])
        self.assertEqual(rec["population"].get("status"), "not_available")
        self.assertTrue(str(switzerland.OUT).endswith("_survey.json"))

    def test_a_canton_with_under_a_hundred_drawn_stops_the_run(self):
        with self.assertRaises(SystemExit):
            switzerland.build([self.CANTON], {"Uri": 90.0})


class SwissDistrictsByYear(unittest.TestCase):
    def sheet(self, national=300.0):
        return [["su-d-01.02.04.07", "Bilanz"],
                [None, "Bevölkerungs-", None, None, None, None, None, None, None, "Bevölkerungs-"],
                [None, "stand am", None, None, None, None, None, None, None, "stand am"],
                [None, "1. Januar", None, None, None, None, None, None, None, "31. Dezember"],
                ["Schweiz 2", 1, 0, 0, 0, 0, 0, 0, 0, national],
                ["- Bern / Berne", 1, 0, 0, 0, 0, 0, 0, 0, 300.0],
                [">> Verwaltungskreis Thun", 1, 0, 0, 0, 0, 0, 0, 0, 300.0],
                ["......0942 Thun", 1, 0, 0, 0, 0, 0, 0, 0, 200.0],
                ["934 Oberhofen am Thunersee", 1, 0, 0, 0, 0, 0, 0, 0, 100.0]]

    def test_communes_are_read_in_both_layouts_and_districts_are_not(self):
        communes, national = switzerland_ages.balance_sheet(self.sheet())
        self.assertEqual(communes, {"0942": 200.0, "0934": 100.0})
        self.assertEqual(national, 300.0)

    def test_communes_that_do_not_make_the_country_stop_the_run(self):
        with self.assertRaises(SystemExit):
            switzerland_ages.balance_sheet(self.sheet(national=301.0))

    def test_a_district_takes_the_latest_year_its_communes_nest(self):
        # In 2024 commune 0942 holds a predecessor from outside the district;
        # in 2023 it does not.
        blob = xlsx({"2024": self.sheet(), "2023": self.sheet()})
        registers = {
            "2024": [{"InitialCode": "942", "TerminalCode": "942", "TerminalName": "Thun"},
                     {"InitialCode": "999", "TerminalCode": "942", "TerminalName": "Thun"},
                     {"InitialCode": "934", "TerminalCode": "934", "TerminalName": "Oberhofen"}],
            "2023": [{"InitialCode": "942", "TerminalCode": "942", "TerminalName": "Thun"},
                     {"InitialCode": "934", "TerminalCode": "934", "TerminalName": "Oberhofen"}],
        }

        def agvch(query):
            end = query.split("endPeriod=")[1].split("&")[0]      # "31-12-2024" or "01-01-2025"
            return registers["2024" if end[-4:] in ("2024", "2025") else "2023"]
        with mock.patch.object(switzerland_ages, "http_get", return_value=blob), \
                mock.patch.object(switzerland_ages, "agvch", side_effect=agvch):
            out = switzerland_ages.older_population([("Thun", {"942", "934"})], 2024)
        self.assertEqual(out["Thun"], (2023, 300.0, 2))


class Liechtenstein(unittest.TestCase):
    def test_place_labels_lose_their_marks_and_codes(self):
        self.assertEqual(liechtenstein.gemeinde_name("....Vaduz"), "Vaduz")
        self.assertEqual(liechtenstein.gemeinde_name("7001 Vaduz"), "Vaduz")

    def test_the_total_is_the_one_value_named_so(self):
        self.assertEqual(liechtenstein.total_code({"Total": "0", "Männer": "1"}), "0")
        with self.assertRaises(SystemExit):
            liechtenstein.total_code({"Männer": "1", "Frauen": "2"})

    def census(self, rows):
        var = {"Stichtag": {"31.12.2020": "s"}, "Religion": {"x": "r"},
               "Geschlecht": {"Total": "t"}, "Gemeinde": {"Vaduz": "v"}}

        def post(key, query):
            return [({"Religion": ("r", label), "Gemeinde": ("v", "Vaduz")}, value)
                    for label, value in rows.items()]
        with mock.patch.object(liechtenstein, "meta", return_value=var), \
                mock.patch.object(liechtenstein, "post", side_effect=post):
            return liechtenstein.census("religion", liechtenstein.RELIGION)

    def test_the_protestant_subtotal_is_dropped_when_its_children_are_there(self):
        parent = liechtenstein.RELIGION_PARENT
        out = self.census({"Total": 100.0, "Römisch-katholisch": 80.0, parent: 20.0,
                           "Evangelisch-reformiert": 15.0, "Evangelisch-lutherisch": 5.0})
        self.assertEqual(out["Vaduz"]["_total"], 100.0)
        self.assertNotIn(parent, out["Vaduz"])

    def test_rows_that_make_the_total_neither_way_stop_the_run(self):
        with self.assertRaises(SystemExit):
            self.census({"Total": 100.0, "Römisch-katholisch": 90.0,
                         liechtenstein.RELIGION_PARENT: 20.0})


class PolandDefinition(unittest.TestCase):
    def test_the_note_measures_gus_against_eurostat(self):
        with mock.patch.object(poland_ages, "eurostat_population", return_value=36_497_495.0):
            note = poland_ages.population_definition(37_332_510.0, 2025)
        self.assertIn("36,497,495", note)
        self.assertIn("2.3% larger", note)

    def test_a_gap_beyond_the_two_definitions_stops_the_run(self):
        with mock.patch.object(poland_ages, "eurostat_population", return_value=30_000_000.0):
            with self.assertRaises(SystemExit):
                poland_ages.population_definition(37_332_510.0, 2025)

    def test_every_voivodeship_is_written_not_only_masovia(self):
        self.assertFalse(hasattr(poland_ages, "LACKING_ADMIN1"))


class CzechAges(unittest.TestCase):
    CSV = ("idhod,hodnota,stapro_kod,pohlavi_cis,pohlavi_kod,vek_cis,vek_kod,vek_txt,uzemi_cis,uzemi_kod,"
           "obdobi,uzemi_txt\n"
           "1,30,x,,,,,,101,40924,2024-12-31,Benešov\n"
           "2,10,x,102,1,,,0,101,40924,2024-12-31,Benešov\n"
           "3,20,x,102,2,,,1,101,40924,2024-12-31,Benešov\n"
           "4,30,x,,,,,5,101,40924,2024-12-31,Benešov\n")

    def test_totals_sexes_and_ages_are_read_apart(self):
        with mock.patch.object(czechia_ages, "http_get", return_value=self.CSV.encode()):
            out = czechia_ages.read(2024)
        unit = out[("101", "Benešov")]
        self.assertEqual(unit["total"], 30)
        self.assertEqual(unit["m"], Counter({0: 10}))
        self.assertEqual(unit["f"], Counter({1: 20}))

    def test_a_file_for_another_date_stops_the_run(self):
        with mock.patch.object(czechia_ages, "http_get",
                               return_value=self.CSV.replace("2024-12-31", "2023-12-31").encode()):
            with self.assertRaises(SystemExit):
                czechia_ages.read(2024)


class SlovakNames(unittest.TestCase):
    def test_datacube_labels_are_written_as_the_name_is(self):
        self.assertEqual(slovakia.district_name("Dunajská\xa0Streda"), "Dunajská Streda")
        self.assertEqual(slovakia.district_name("Śaľa"), "Šaľa")
        self.assertEqual(slovakia.district_name("District of Spišská\xa0Nová Ves"), "Spišská Nová Ves")


class SlovakCensus(unittest.TestCase):
    def test_answers_are_named_by_the_start_of_their_alias(self):
        self.assertEqual(slovakia_census.english("religion", "Rímskokatolícka cirkev"), "Roman Catholic")
        self.assertEqual(slovakia_census.english("language", "ostatné"), slovakia_census.OTHER)
        self.assertIsNone(slovakia_census.english("language", "klingonský"))

    def layer(self, attributes):
        info = {"fields": [{"name": "cv_1", "alias": "slovenský"}, {"name": "cv_2", "alias": "ostatné"},
                           {"name": "cv_1p", "alias": "slovenský %"}]}
        replies = [info, {"features": [{"attributes": attributes}]}]
        with mock.patch.object(slovakia_census, "http_json", side_effect=replies):
            return slovakia_census.layer("language", "admin2")

    def test_a_unit_whose_answers_make_its_population_is_kept(self):
        out = self.layer({"uzemie": "SK0101", "nazov": "Bratislava I", "spolu": 100, "cv_1": 90,
                          "cv_2": 10, "cv_1p": 90.0})
        self.assertEqual(out["SK0101"]["counts"], {"Slovak": 90, slovakia_census.OTHER: 10})

    def test_answers_that_miss_the_population_stop_the_run(self):
        with self.assertRaises(SystemExit):
            self.layer({"uzemie": "SK0101", "nazov": "Bratislava I", "spolu": 100, "cv_1": 90,
                        "cv_2": 5})


class HungaryDrawnIn2013(unittest.TestCase):
    TABLE = [["Helység", "", "", "Megye megnevezése", "Kistérség", "", "", "Járás", "", ""],
             ["megnevezése", "KSH kódja", "jogállása", "", "kódja", "neve", "székhelye", "kódja", "neve",
              "székhelye"],
             ["Polgárdi", "17525", "város", "Fejér", 3707.0, "Székesfehérvári", "Székesfehérvár", "083 1",
              "Polgárdi", "Polgárdi"],
             ["Enying", "02802", "város", "Fejér", 3708.0, "Enyingi", "Enying", "079 1", "Enyingi", "Enying"],
             ["Aba", 17376.0, "város", "Fejér", 3708.0, "Abai", "Aba", "085 0", "Székesfehérvári",
              "Székesfehérvár"],
             ["Abaliget", "12548", "község", "Baranya", 3207.0, "Pécsi", "Pécs", "028 0", "Pécsi", "Pécs"],
             ["Bicsérd", "13453", "község", "Baranya", 3207.0, "Pécsi", "Pécs", "029 0", "Szentlőrinci",
              "Szentlőrinc"]]

    def test_the_gazetteer_is_read_by_its_two_header_rows(self):
        out = hungary.read_gazetteer(self.TABLE)
        self.assertEqual(out["17525"], ("Polgárdi", "083", "Polgárdi"))
        self.assertEqual(out["17376"][1], "085")               # a number read as a code

    COUNTY = {"079": "HU211", "083": "HU211", "085": "HU211", "028": "HU231", "029": "HU231",
              "030": "HU232"}

    def test_every_district_a_settlement_left_or_joined_is_rebuilt_from_2014(self):
        old = hungary.read_gazetteer(self.TABLE)
        now = {"17525": "085", "02802": "079", "17376": "085", "12548": "028", "13453": "029"}
        # Polgárdi's settlement went to Székesfehérvár: 083 and 085 change, 079 and 028 do not.
        self.assertEqual(hungary.members_2014(old, now, self.COUNTY),
                         {"083": ["17525"], "085": ["17376"]})
        # A move within a county elsewhere is rebuilt too, on both sides.
        moved = hungary.members_2014(old, {**now, "12548": "029"}, self.COUNTY)
        self.assertEqual((moved["028"], moved["029"]), (["12548"], ["13453"]))

    def test_a_move_between_counties_stops_the_run(self):
        old = hungary.read_gazetteer(self.TABLE)
        now = {"17525": "085", "02802": "079", "17376": "085", "12548": "030"}
        with self.assertRaises(SystemExit):
            hungary.members_2014(old, now, self.COUNTY)

    def test_a_settlement_the_gazetteer_lacks_in_a_changed_district_stops_the_run(self):
        old = hungary.read_gazetteer(self.TABLE)
        now = {"17525": "085", "02802": "079", "17376": "085", "99999": "085"}
        with self.assertRaises(SystemExit):
            hungary.members_2014(old, now, self.COUNTY)

    def unit(self, share):
        cells = {"VALLAS_V1": 1000.0, "M": 490.0, "F": 510.0, "RE_C": 400.0, "RE_RC": 400.0,
                 "RE_NOT": 300.0, "RE_NA": 300.0, "EG": 1000.0, "EG_HU": 1000.0, "MT": 1000.0,
                 "MT_HU": 1000.0}
        return {"cells": cells, "settlements": ["A", "B"], "codes": ["1", "2"], "blanked": 0,
                "name": "Bicskei", "differ": [("C", 1000.0 * share, False)], "share": share}

    def test_the_2022_median_is_kept_only_where_the_two_differ_by_two_percent_or_less(self):
        shape = {"id": "s", "name": "Bicske", "parent": "p"}
        median = {"median_age": {"value": 44.0}, "median_age_note": "Interpolated."}
        close = hungary.drawn_record("077", self.unit(0.015), shape, "KSH", "Fejér", median)
        self.assertEqual(close["median_age"], {"value": 44.0})
        self.assertIn("differs from the drawn one by 1.5%", close["median_age_note"])
        far = hungary.drawn_record("077", self.unit(0.05), shape, "KSH", "Fejér", median)
        self.assertEqual(far["median_age"]["status"], "not_available")
        self.assertEqual(far["population"]["value"], 1000)
        self.assertEqual(far["sex_ratio"]["value"], 96.1)

    def test_a_settlement_whose_sexes_miss_its_people_stops_the_run(self):
        cells = {"17525": {"VALLAS_V1": 10.0, "M": 4.0, "F": 5.0}}
        with self.assertRaises(SystemExit):
            hungary.sum_settlements(["17525"], cells, {"17525": "Polgárdi"})

    def test_blanked_settlement_cells_widen_the_partition_check_by_a_few_each(self):
        c = {"VALLAS_V1": 1000.0, "RE_C": 400.0, "RE_RC": 380.0, "RE_GC": 10.0, "RE_NOT": 300.0,
             "RE_NA": 270.0, "EG": 1000.0, "EG_HU": 1000.0, "MT": 1000.0, "MT_HU": 1000.0}
        with self.assertRaises(SystemExit):
            hungary.composition(c, "x")                         # 30 short
        out = hungary.composition(c, "x", blanked=10)
        self.assertIn("religion", out)


class SlovenianOutliers(unittest.TestCase):
    def test_a_lopsided_sex_ratio_names_its_settlement(self):
        meta = {"MUNICIPALITY/SETTLEMENT": {"text": "MUNICIPALITY/SETTLEMENT",
                                            "values": ["211", "211015", "211017"]},
                "YEAR": {"text": "YEAR", "values": ["2025", "2026"]},
                "MEASURES": {"text": "MEASURES", "values": ["1", "2"],
                             "valueTexts": ["Population - Men", "Population - Women"]}}
        cells = [({"MUNICIPALITY/SETTLEMENT": ("211015", "211015 Slovenska vas"), "MEASURES": ("1", "")}, 416.0),
                 ({"MUNICIPALITY/SETTLEMENT": ("211015", "211015 Slovenska vas"), "MEASURES": ("2", "")}, 58.0),
                 ({"MUNICIPALITY/SETTLEMENT": ("211017", "211017 Šentrupert"), "MEASURES": ("1", "")}, 150.0),
                 ({"MUNICIPALITY/SETTLEMENT": ("211017", "211017 Šentrupert"), "MEASURES": ("2", "")}, 166.0)]
        with mock.patch.object(slovenia, "meta", return_value=meta), \
                mock.patch.object(slovenia, "query", return_value=cells):
            text = slovenia.lopsided_settlement("211", "Šentrupert", 2026)
        self.assertIn("Slovenska vas counts 416 men and 58 women", text)
        self.assertIn("Dob", text)

    def test_the_oldest_municipality_says_how_many_are_old(self):
        records = [{"codes": {"surs_obcina": "1"}, "name": "Osilnica",
                    "sex_ratio": {"value": 100.0}, "median_age": {"value": 60.1},
                    "median_age_note": "m.", "sex_ratio_note": "r."},
                   {"codes": {"surs_obcina": "2"}, "name": "Ljubljana",
                    "sex_ratio": {"value": 96.0}, "median_age": {"value": 43.0},
                    "median_age_note": "m.", "sex_ratio_note": "r."}]
        ages = {"1": Counter({30: 40, 70: 60}), "2": Counter({40: 1})}
        slovenia.explain_outliers(records, ages, 2026)
        self.assertIn("60% of its 100 people are 65 or older; the highest median",
                      records[0]["median_age_note"])
        self.assertEqual(records[1]["median_age_note"], "m.")


class DutchReligionSurvey(unittest.TestCase):
    ROWS = [["Tabel 2"],
            [None, None, "Totaal gelovig", "Rooms-kaholiek", "Protestants", "Islam", "Ander geloof"],
            *[[p, "Totaal", 40.0, 10.0, 15.0, 7.0, 8.0] for p in netherlands_religion.PROVINCES],
            ["Nederland", "Totaal", 40.0, 10.0, 15.0, 7.0, 8.0]]

    def test_ander_geloof_is_the_residual_and_not_a_non_abrahamic_religion(self):
        blob = xlsx({"Tabel 2": self.ROWS})
        with mock.patch.object(netherlands_religion, "http_get", return_value=blob):
            records = netherlands_religion.build()
        groups = {r["group"]: r["pct"] for r in records[0]["religion"]}
        self.assertEqual(groups[netherlands_religion.OTHER], 8.0)
        self.assertNotIn("Other religion", groups)
        self.assertEqual(groups["No religion"], 60.0)
        self.assertIn("other Christian groups", records[0]["religion_note"])
        self.assertIn("at least 300", records[0]["religion_note"])
        self.assertTrue(records[0]["religion_basis"].startswith("survey estimate"))


class LuxembourgBeforeTheMergers(unittest.TestCase):
    POPCOM = [["POPULATION PAR COMMUNE"],
              ["Code LAU2", "Commune", "1-1-2016", "1-1-2017"],
              ["1007", "Rosport", 2222, 2293], ["1006", "Mompach", 1283, 1303],
              ["Total", None, 3505, 3596]]
    AGES = [["RP2011"], ["Commune", "Groupe d'âges quinquénaux"],
            [None, "0 à 4 ans", "5 à 9 ans", *[f"{a} à {a + 4} ans" for a in range(10, 100, 5)],
             "100 et plus", "Total"],
            ["Rosport", 10, 10, *([0] * 18), 0, 20], ["Total", 10, 10, *([0] * 18), 0, 20]]

    def test_the_2017_column_is_read_and_checked_against_the_total(self):
        out, total = luxembourg.read_popcom(self.POPCOM)
        self.assertEqual(out, {"Rosport": 2293.0, "Mompach": 1303.0})
        self.assertEqual(total, 3596.0)
        bad = [*self.POPCOM[:-1], ["Total", None, 3505, 3597]]
        with self.assertRaises(SystemExit):
            luxembourg.read_popcom(bad)

    def test_the_2011_age_groups_make_each_communes_total(self):
        ages = luxembourg.read_rp2011_ages(self.AGES)
        self.assertEqual(ages["Rosport"][(0, 4)], 10.0)
        self.assertEqual(ages["Rosport"][(100, None)], 0.0)
        broken = [*self.AGES[:3], ["Rosport", 10, 10, *([0] * 18), 0, 21]]
        with self.assertRaises(SystemExit):
            luxembourg.read_rp2011_ages(broken)

    def test_the_2011_sexes_make_each_communes_total(self):
        rows = [["Commune", "Sexe"], [None, "Masculin", "Féminin", "Total"], ["Rosport", 1035, 1041, 2076]]
        self.assertEqual(luxembourg.read_rp2011_sexes(rows), {"Rosport": (1035.0, 1041.0)})
        with self.assertRaises(SystemExit):
            luxembourg.read_rp2011_sexes([*rows[:2], ["Rosport", 1035, 1041, 2077]])


if __name__ == "__main__":
    unittest.main()
