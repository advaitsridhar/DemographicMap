"""The Nordic gap round: origin as ethnicity, the churches' membership, and the small fixes.

No network: every test runs on the readers' own helpers with small made-up
tables, and on the map's unit files where a test needs the drawn shapes.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import (estonia, iceland, nordic_church as church,  # noqa: E402
                                  nordic_origin as origin, norway)


def stat2(dims: list[tuple[str, list[str]]], values: list[float]) -> dict:
    """A json-stat2 body over the given dimensions, row-major."""
    return {"id": [d for d, _ in dims], "size": [len(codes) for _, codes in dims],
            "dimension": {d: {"category": {"index": {c: i for i, c in enumerate(codes)},
                                           "label": {c: c for c in codes}}}
                          for d, codes in dims},
            "value": values}


class OriginLabels(unittest.TestCase):
    def test_an_office_name_is_its_peoples_adjective_with_or_without_a_title(self):
        self.assertEqual(origin.label_of("Republic of North Macedonia"), "North Macedonian")
        self.assertEqual(origin.label_of("The Gambia"), "Gambian")
        self.assertEqual(origin.label_of("Congo, Democratic Republic of the"), "Congolese")
        self.assertEqual(origin.label_of("", "SE"), "Swedish")

    def test_residual_rows_are_residuals_and_an_unknown_name_is_none(self):
        self.assertEqual(origin.label_of("Stateless"), origin.STATELESS)
        self.assertEqual(origin.label_of("Unknown country of birth"), origin.UNKNOWN)
        self.assertEqual(origin.label_of("Other countries"), origin.OTHER)
        self.assertIsNone(origin.label_of("Atlantis"))

    def test_an_unlabelled_row_folds_into_other_when_small_and_stops_the_run_when_not(self):
        names = {"1": "Sweden", "2": "Atlantis"}
        got = origin.code_labels({"1": 1000, "2": 5}, names, lambda c, n: origin.label_of(n),
                                 100, "test")
        self.assertEqual(got, {"1": "Swedish", "2": origin.OTHER})
        with self.assertRaises(SystemExit):
            origin.code_labels({"1": 1000, "2": 500}, names,
                               lambda c, n: origin.label_of(n), 100, "test")

    def test_the_named_countries_are_the_home_row_and_those_over_the_floor(self):
        national = {"Finnish": 990, "Estonian": 5, "Russian": 0.5, origin.OTHER: 10,
                    origin.UNKNOWN: 2}
        self.assertEqual(origin.named_labels(national, 1000, "Finnish"), {"Finnish", "Estonian"})
        made = origin.compose({"Finnish": 50, "Russian": 3, origin.UNKNOWN: 2, origin.OTHER: 1,
                               "Estonian": 0}, {"Finnish", "Estonian"})
        self.assertEqual(made, {"Finnish": 50, origin.OTHER: 4, origin.UNKNOWN: 2})

    def test_a_block_whose_labels_miss_the_total_stops_and_a_good_one_keeps_its_note(self):
        source = {"field": "ethnicity", "name": "test", "url": "u", "year": 2026}
        with self.assertRaises(SystemExit):
            origin.ethnicity_block({"Danish": 90}, 100, year=2026, basis="b", note="n.",
                                   source=source)
        block = origin.ethnicity_block({"Danish": 90, origin.OTHER: 10}, 100, year=2026,
                                       basis="ancestry", note="Ancestry.", source=source)
        self.assertEqual([g["group"] for g in block["ethnicity"]], ["Danish", origin.OTHER])
        self.assertEqual(block["ethnicity_note"], "Ancestry.")
        self.assertNotIn("owner", block["ethnicity_note"])
        self.assertEqual(block["ethnicity_basis"], "ancestry")


class OriginOffices(unittest.TestCase):
    def test_danish_origin_is_one_row_whatever_country_folk1c_writes_beside_it(self):
        rows = [
            {"OMRÅDE": "101", "HERKOMST": "TOT", "IELAND": "0000", "INDHOLD": "100"},
            {"OMRÅDE": "101", "HERKOMST": origin.DANISH_ORIGIN, "IELAND": "5100",
             "INDHOLD": "60"},
            {"OMRÅDE": "101", "HERKOMST": origin.DANISH_ORIGIN, "IELAND": "5999",
             "INDHOLD": "10"},
            {"OMRÅDE": "101", "HERKOMST": origin.IMMIGRANTS, "IELAND": "5120",
             "INDHOLD": "20"},
            {"OMRÅDE": "101", "HERKOMST": origin.DESCENDANTS, "IELAND": "5120",
             "INDHOLD": "7"},
            {"OMRÅDE": "101", "HERKOMST": origin.IMMIGRANTS, "IELAND": "5100", "INDHOLD": "3"},
        ]
        counts, totals, odd = origin.dst_counts(rows)
        self.assertEqual(totals, {"101": 100.0})
        self.assertEqual(counts["101"], {"DK": 70.0, "5120": 27.0, "5100": 3.0})
        self.assertEqual(len(odd), 1)
        self.assertEqual(origin.dst_label("DK", ""), "Danish")
        self.assertEqual(origin.dst_label("5100", "Denmark"), origin.OTHER)
        self.assertEqual(origin.dst_label("5103", "Stateless"), origin.STATELESS)
        self.assertEqual(origin.dst_label("5999", "Not stated"), origin.UNKNOWN)

    def test_ssb_protected_cells_pass_within_a_person_or_two_and_a_misread_does_not(self):
        dims = [("Region", ["0709", "0301"]), ("Landbakgrunn", ["999", "VES", "1", "2"])]
        body = stat2(dims, [6100, 4000, 4001, 2100, 900, 600, 600, 300])
        counts, totals = origin.ssb_counts(body)
        self.assertEqual(totals["0709"], 6101)        # the countries' own sum
        self.assertEqual(counts["0709"], {"1": 4001, "2": 2100})
        broken = stat2(dims, [6100, 4000, 4001, 2000, 900, 600, 600, 300])
        with self.assertRaises(SystemExit):
            origin.ssb_counts(broken)

    def test_statfin_withheld_cells_are_counted_and_a_large_shortfall_stops_the_run(self):
        dims = [("alue", ["KU020", "KU005"]), ("valtio", ["SSS", "EUR", "246", "233"])]
        body = stat2(dims, [16429, 400, 15000, 1331, 9000, 50, 9000, 0])
        counts, totals = origin.statfin_counts(body, "alue", "valtio")
        self.assertEqual(counts["KU020"], {"246": 15000, "233": 1331})
        withheld = origin.withheld_cells(counts, totals, ["KU020", "KU005"])
        self.assertEqual(withheld, {"KU020": 98})
        with self.assertRaises(SystemExit):     # a third of the people unaccounted for
            origin.withheld_cells({"KU1": {"246": 600}}, {"KU1": 1000}, ["KU1"])
        with self.assertRaises(SystemExit):     # more itemised than the total
            origin.withheld_cells({"KU1": {"246": 1010}}, {"KU1": 1000}, ["KU1"])
        with self.assertRaises(SystemExit):     # no total at all
            origin.withheld_cells({}, {}, ["KU1"])
        self.assertEqual(origin.statfin_label("246", "Finland"), "Finnish")
        self.assertEqual(origin.statfin_label("X", "Unknown"), origin.UNKNOWN)
        self.assertEqual(origin.statfin_label("991", "Stateless"), origin.STATELESS)

    def test_todays_municipalities_are_placed_only_where_the_map_years_unit_holds_them(self):
        key = {"099": "0405", "214": "0405", "005": "1401"}
        self.assertEqual(origin.place_current(["214", "005"], key, "t"),
                         {"214": "0405", "005": "1401"})
        with self.assertRaises(SystemExit):          # gone, successor elsewhere
            origin.place_current(["214", "005"], {**key, "214": "1401"}, "t")
        with self.assertRaises(SystemExit):          # a code the key does not know
            origin.place_current(["214", "005", "999"], key, "t")

    def test_finlands_regions_are_the_drawn_ones(self):
        import json
        drawn = {u["name"] for u in json.loads(
            (ROOT / "site" / "data" / "admin1" / "FIN.units.json").read_text())}
        self.assertEqual(set(origin.FIN_REGIONS.values()), drawn)


class IcelandToday(unittest.TestCase):
    def test_a_municipality_keeps_renumbers_or_loses_its_number_by_name_and_count(self):
        units = ["1000", "2000", "3000", "4000"]
        totals = {"1000": 1000, "2000": 500, "3000": 300, "4000": 80}
        names = {"1000": "Akureyrarbær", "2000": "Borgarbyggð", "3000": "Dalabyggð",
                 "4000": "Eyjafjarðarsveit"}
        then = {"1000": 1010, "2000": 900, "3500": 305}
        now_totals = {"1000": 1100, "2000": 1000, "3500": 320}
        now_names = {"1000": "Akureyrarbaer", "2000": "Borgarbyggd", "3500": "Dalabyggd"}
        today, kept = iceland.unchanged_since(units, totals, names, then, now_totals, now_names)
        self.assertEqual(today, {"1000": "1000", "3000": "3500"})
        self.assertEqual(len(kept), 1)
        self.assertIn("Borgarbyggð 2000", kept[0])


class SwedishChurch(unittest.TestCase):
    def test_digit_groups_make_a_number_only_as_thousands(self):
        self.assertEqual(church.numbers(["1", "007", "123"]), 1007123)
        self.assertIsNone(church.numbers(["12", "34"]))
        self.assertIsNone(church.numbers(["0", "123"]))

    def test_the_counts_are_split_by_the_printed_ratio_and_a_code_is_passed_over(self):
        self.assertEqual(church.population_and_members(
            "66 430 43 928 66,0% 66,1% 0,11% 0,22% 1,04%"), (66430, 43928, 66.0))
        self.assertEqual(church.population_and_members(
            "(999999) 17 847 5 935 33,2% 33,3% 0,99% 0,50% 1,92%"), (17847, 5935, 33.2))
        with self.assertRaises(SystemExit):
            church.population_and_members("12 345 * *")

    def test_kommuner_and_lan_are_read_and_parishes_left(self):
        lines = ["Blekinge län 158 854 103 376 65,1% 65,1% 0,11% 0,20% 0,98%",
                 "Karlskrona kommun 66 430 43 928 66,0% 66,1% 0,11% 0,22% 1,04%",
                 "Aspö församling (108004) 556 399 76,4% 71,8% 0,00% 0,00% 1,25%",
                 "På kommunen skrivna (999999) 17 847 5 935 33,2% 33,3% 0,99% 0,50% 1,92%"]
        kommuner, lan, nowhere = church.svk_rows(lines)
        self.assertEqual(kommuner, {"Karlskrona": (66430, 43928, 66.0)})
        self.assertEqual(lan, {"Blekinge": (158854, 103376, 65.1)})
        self.assertEqual(nowhere, (17847, 5935, 33.2))
        with self.assertRaises(SystemExit):
            church.svk_rows(lines + lines[-1:])
        with self.assertRaises(SystemExit):
            church.svk_rows(lines[:2] + lines[1:2])

    def test_genitive_names_find_scbs_codes(self):
        scb = {"1082": "Karlshamn", "1490": "Borås", "2080": "Falun"}
        self.assertEqual(church.match_names(["Karlshamns", "Borås", "Faluns"], scb),
                         {"Karlshamns": "1082", "Borås": "1490", "Faluns": "2080"})
        with self.assertRaises(SystemExit):
            church.match_names(["Atlantis"], scb)
    def test_a_parish_across_two_kommuner_is_found_and_nothing_else_is_excused(self):
        names = {"1762": "Munkfors", "1763": "Forshaga"}
        lines = ["Forshaga kommun 15 269 10 693 70,0% 70,0% 0,13% 0,31% 0,91%",
                 "Forshaga-Munkfors församling (176301) 15 269 10 693 70,0% 70,0% 0,13% 0,31% "
                 "0,91%"]
        self.assertEqual(church.joined_kommuner(["1762"], {"1763"}, names, lines),
                         {"1762": ("1763", "Forshaga-Munkfors")})
        with self.assertRaises(SystemExit):
            church.joined_kommuner(["1762"], {"1763"}, names, lines[:1])

    def test_genitive_names_find_scbs_codes_spelled_before_folded(self):
        # Folded, Håbo and Habo are one name; spelled, they are two kommuner.
        self.assertEqual(church.match_names(["Håbo", "Habo"], {"0305": "Håbo", "0643": "Habo"}),
                         {"Håbo": "0305", "Habo": "0643"})


# Finland's religion is read from the population register now
# (finland_religion.py, tests/test_church.py), not from the Lutheran church's
# economic units, so the church reader's Finnish helpers and their tests are gone.


class SmallFixes(unittest.TestCase):
    def test_a_norwegian_piece_says_why_it_has_no_figures(self):
        shapes = [{"id": "a", "name": "Frogn nor", "parent": "P"},
                  {"id": "b", "name": "Frogn nor", "parent": "P"}]
        records = norway.piece_records([shapes[1]], shapes, {"0215": "a"}, {"0215": "Frogn"})
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["shape_id"], "b")
        for field in norway.PIECE_FIELDS:
            self.assertEqual(records[0][field]["status"], "not_available")
            self.assertIn("detached piece of Frogn kommune", records[0][field]["note"])
        with self.assertRaises(SystemExit):
            norway.piece_records([shapes[1]], shapes, {}, {})

    def test_estonias_protected_cells_pass_within_twenty_people(self):
        rows = []
        for i in range(25):
            code = f"{100 + i}"
            rows += [({"Elukoht": (code, code), "Usk": ("899", "Total")}, 1000),
                     ({"Elukoht": (code, code), "Usk": ("1", "Lutheran")}, 1000)]
        rows += [({"Elukoht": ("257", "257"), "Usk": ("899", "Total")}, 1236),
                 ({"Elukoht": ("257", "257"), "Usk": ("1", "Lutheran")}, 1218),
                 ({"Elukoht": ("999", "999"), "Usk": ("899", "Total")}, 1000),
                 ({"Elukoht": ("999", "999"), "Usk": ("1", "Lutheran")}, 970)]
        out = estonia.composition(rows, "Elukoht", "Usk", "899", set(), lambda t: t)
        self.assertIn("257", out)                 # 18 short of 1,236
        self.assertNotIn("999", out)              # 30 short of 1,000


if __name__ == "__main__":
    unittest.main()
