"""The Nordic and Baltic adapters: binding to the drawn vintage, ages, and the offices' quirks.

No network: every test runs on the adapters' own helpers and the map's unit
files, which are in the repository.
"""
from __future__ import annotations

import json
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import (denmark, estonia, finland, iceland, latvia,  # noqa: E402
                                  lithuania, norway, nordic_common as nc, pxweb, sweden)


def units(iso3: str, level: str) -> list[dict]:
    return json.loads((ROOT / "site" / "data" / level / f"{iso3}.units.json").read_text())


class Ages(unittest.TestCase):
    def test_median_is_interpolated_within_the_single_year(self):
        ages = nc.AgeSex()
        for age in range(10):
            ages.add(age, "m", 10)
            ages.add(age, "f", 10)
        # 200 people, 20 a year: the 100th falls exactly at the end of age 4.
        self.assertEqual(ages.median(), 5.0)

    def test_sex_ratio_is_males_per_hundred_females(self):
        self.assertEqual(nc.sex_ratio(1039, 1000), 103.9)
        self.assertIsNone(nc.sex_ratio(5, 0))

    def test_fields_carry_unit_year_and_source(self):
        ages = nc.AgeSex()
        ages.add(30, "m", 50)
        ages.add(40, "f", 50)
        out = ages.fields(year=2026, source="Office", url="u", date="1 January 2026")
        self.assertEqual(out["population"]["value"], 100)
        self.assertEqual(out["sex_ratio"]["unit"], "males_per_100_females")
        self.assertEqual(out["median_age"]["year"], 2026)
        self.assertEqual(out["sources"][0]["field"], "population/median age/sex ratio")

    def test_parts_must_make_the_whole(self):
        nc.check_parts({"a": 10, "b": 20}, 30, "ok", 0)
        with self.assertRaises(SystemExit):
            nc.check_parts({"a": 10, "b": 20}, 40, "short", 0)


class Pieces(unittest.TestCase):
    def test_a_small_piece_of_a_kommune_is_set_aside_not_given_a_copy(self):
        big = {"id": "1", "name": "Frogn", "parent": "V", "bbox": [0, 0, 1, 1]}
        islet = {"id": "2", "name": "Frogn", "parent": "V", "bbox": [0, 0, 0.1, 0.1]}
        kept, pieces = nc.split_pieces([big, islet])
        self.assertEqual([s["id"] for s in kept], ["1"])
        self.assertEqual([s["id"] for s in pieces], ["2"])

    def test_two_places_of_one_name_and_size_are_both_kept(self):
        a = {"id": "1", "name": "Nes", "parent": "V", "bbox": [0, 0, 1, 1]}
        b = {"id": "2", "name": "Nes", "parent": "V", "bbox": [5, 5, 5.8, 5.9]}
        kept, pieces = nc.split_pieces([a, b])
        self.assertEqual(len(kept), 2)
        self.assertEqual(pieces, [])


class Denmark(unittest.TestCase):
    def test_every_drawn_kommune_binds_by_statbanks_names(self):
        shapes = units("DNK", "admin2")
        parents = nc.parent_names("DNK")
        rows = {str(i): ({"Vesthimmerland": "Vesthimmerlands", "Nordfyn": "Nordfyns"}
                         .get(s["name"], s["name"]), parents[s["parent"]])
                for i, s in enumerate(shapes)}
        bound, missing, left, _ = nc.bind_rows("DNK", "admin2", rows, aliases=denmark.ALIASES)
        self.assertEqual((len(bound), missing, left), (98, [], []))

    def test_regions_are_read_from_statbanks_order(self):
        meta = {"variables": [{"id": "OMRÅDE", "values": [
            {"id": "000", "text": "All Denmark"}, {"id": "084", "text": "Region Hovedstaden"},
            {"id": "101", "text": "Copenhagen"}, {"id": "085", "text": "Region Sjælland"},
            {"id": "253", "text": "Greve"}]}]}
        names, region_of = denmark.areas(meta, "OMRÅDE")
        self.assertEqual(region_of, {"101": "084", "253": "085"})

    def test_a_non_member_is_not_filed_as_protestant(self):
        self.assertEqual(nc.unplaced("religion", [denmark.CHURCH]), [])
        self.assertNotIn("Protestantism",
                         __import__("group_tree").ancestry("religion", denmark.OUTSIDE))


class Norway(unittest.TestCase):
    def test_boundary_file_tags_and_quotes_come_off(self):
        self.assertEqual(norway.map_name({"name": '"Evje og Hornnes" nor'}), "Evje og Hornnes")
        self.assertEqual(norway.map_name({"name": "Guovdageaidnu sme 1"}), "Guovdageaidnu")
        self.assertEqual(norway.map_name({"name": "Kåfjord nor 2"}), "Kåfjord")

    def test_office_names_split_languages_and_drop_the_span(self):
        self.assertEqual(norway.office_names("Sandefjord (2017-2019)"), ["Sandefjord"])
        self.assertEqual(norway.office_names("Kautokeino - Guovdageaidnu"),
                         ["Kautokeino", "Guovdageaidnu"])
        self.assertIn("Våler", norway.office_names("Våler (Østfold)"))

    def test_renumbering_survives_and_a_merger_does_not(self):
        changes = {"codeChanges": [
            {"oldCode": "0101", "newCode": "3001", "changeOccurred": "2020-01-01"},
            {"oldCode": "3001", "newCode": "3101", "changeOccurred": "2024-01-01"},
            {"oldCode": "0722", "newCode": "3811", "changeOccurred": "2018-01-01"},
            {"oldCode": "0723", "newCode": "3811", "changeOccurred": "2018-01-01"},
            {"oldCode": "1141", "newCode": "1103", "changeOccurred": "2020-01-01"},
        ]}
        with mock.patch.object(norway, "request_json", return_value=changes):
            out = norway.successors(["0101", "0722", "0723", "0301", "1103", "1141"],
                                    "2017-01-02", "2026-01-01")
        self.assertEqual(out, {"0101": "3101", "0301": "0301"})

    def test_no_members_outside_the_church_is_not_a_count_of_none(self):
        self.assertIsNone(norway.religion({"KOSmedlemmerdnk0000": 300000,
                                           "KOSmedltroslivs0000": 0,
                                           "KOSpersoneralle0000": 700000}, 2025, "Oslo"))
        faith = norway.religion({"KOSmedlemmerdnk0000": 60, "KOSmedltroslivs0000": 10,
                                 "KOSpersoneralle0000": 100}, 2017, "X")
        self.assertEqual(sum(g["count"] for g in faith["religion"]), 100)

    def test_a_fylke_splits_the_other_communities_only_when_the_tables_agree(self):
        counts = {"KOSmedlemmerdnk0000": 60, "KOSmedltroslivs0000": 10,
                  "KOSpersoneralle0000": 100}
        kinds = {"999": 10, "400": 4, "600": 5, "900": 1}
        faith = norway.religion_by_kind(counts, kinds, 2020, "X")
        got = {g["group"]: g["count"] for g in faith["religion"]}
        self.assertEqual(got[norway.NONE], 30)
        self.assertEqual(got["Islam"], 4)
        self.assertNotIn(norway.OTHER, got)
        self.assertEqual(sum(got.values()), 100)
        with self.assertRaises(SystemExit):
            norway.religion_by_kind(counts, {**kinds, "999": 12}, 2020, "X")

    def test_the_religions_outside_the_church_are_placed(self):
        self.assertEqual(nc.unplaced("religion", norway.KINDS.values()), [])


class Finland(unittest.TestCase):
    def test_every_drawn_sub_region_has_a_name_in_the_classification(self):
        drawn = {u["name"] for u in units("FIN", "admin2")}
        self.assertEqual(drawn, set(finland.DRAWN))

    def test_a_bilingual_classification_name_is_found_by_its_part(self):
        found, missing = finland.match({"001": "Åboland-Turunmaa", "002": "Kotka-Hamina"})
        self.assertEqual(found["Turunmaan seutukunta"], "001")
        self.assertEqual(found["Kotkan–Haminan seutukunta"], "002")


class Iceland(unittest.TestCase):
    def test_regions_by_the_first_digit_cover_the_drawn_regions(self):
        drawn = {u["name"] for u in units("ISL", "admin1")}
        self.assertEqual(set(iceland.REGION.values()), drawn)

    def test_an_ascii_name_finds_its_icelandic_spelling(self):
        # MAN02005 answers "Sveitarfelagid Hornafjordur" for MAN09000's
        # "Sveitarfélagið Hornafjörður", renumbered 7708 -> 8401 in 2021.
        self.assertEqual(iceland.stem("Sveitarfelagid Hornafjordur"),
                         iceland.stem("Sveitarfélagið Hornafjörður"))
        self.assertEqual(iceland.stem("Sveitarfélagið Hornafjörður"), "hornaf")
        self.assertEqual(iceland.stem("Kopavogsbaer"), iceland.stem("Kópavogsbær"))

    def test_a_merger_under_its_own_name_is_not_a_renumbering(self):
        self.assertIn("5200", iceland.MERGED_RENUMBERED)     # Skagafjörður + Akrahreppur
        self.assertIn("3711", iceland.MERGED_RENUMBERED)     # Stykkishólmur + Helgafellssveit
        self.assertTrue(set(iceland.MERGED_RENUMBERED).isdisjoint(iceland.ABSORBED))


class Estonia(unittest.TestCase):
    def test_kind_words_come_off(self):
        self.assertEqual(estonia.split("Keila city"), ("Keila", "linn"))
        self.assertEqual(estonia.split("Voru vald"), ("Voru", "vald"))
        self.assertEqual(estonia.split("Vändra rural municipality (town)"), ("Vändra", "alev"))
        self.assertEqual(estonia.split("Kõue rural municipality*"), ("Kõue", "vald"))

    def test_municipalities_are_read_at_their_indentation(self):
        values = ["1", "6", "7", "8", "9", "23", "24", "35"]
        texts = ["Whole country", "HARJU COUNTY", "Harju county: cities", "..Tallinn",
                 "....Haabersti city district", "..Aegviidu rural municipality",
                 "....Aegviidu town", "..Kõue rural municipality*"]
        found, counties = estonia.units_of(values, texts)
        self.assertEqual(set(found), {"8", "23", "35"})
        self.assertEqual(found["8"]["kind"], "linn")
        self.assertTrue(found["35"]["gone"])
        self.assertEqual(counties, {"37": "6"})

    def test_every_discontinued_unit_has_a_known_successor_in_the_drawn_county(self):
        for (base, kind), (succ, skind) in estonia.SUCCESSOR.items():
            self.assertIn(skind, ("vald", "linn"))

    def test_the_relabelled_polygon_is_bound_only_as_the_last_of_its_county(self):
        drawn = {u["name"] for u in units("EST", "admin2")}
        self.assertTrue(set(estonia.DRAWN) <= drawn)
        self.assertIn("Maidla vald", estonia.RELABELLED)
        shapes = [{"id": "m", "name": "Maidla vald"}, {"id": "k", "name": "Kivi"}]
        units_ = {"1": {"name": "Lüganuse vald", "base": "Lüganuse", "kind": "vald",
                        "county": "44", "gone": False},
                  "2": {"name": "Kiviõli linn", "base": "Kiviõli", "kind": "linn",
                        "county": "44", "gone": False}}
        county = {"m": "44", "k": "44"}
        bound = {"k": "2"}
        notes = estonia.bind_relabelled(shapes, bound, units_, ["1", "2"], county)
        self.assertEqual(bound["m"], "1")
        self.assertIn("Lüganuse", notes["m"])
        # Two units left in the county: nothing decides, so nothing is bound.
        bound = {}
        estonia.bind_relabelled(shapes, bound, units_, ["1", "2"], county)
        self.assertNotIn("m", bound)
        # The unit is bound elsewhere already: the polygon stays a gap.
        bound = {"k": "1"}
        estonia.bind_relabelled(shapes, bound, units_, ["1"], county)
        self.assertNotIn("m", bound)

    def test_faiths_are_filed_by_their_tradition(self):
        tree = __import__("group_tree")
        self.assertIn("Orthodoxy", tree.ancestry("religion", estonia.labels_religion("Old Believer")))
        self.assertIn("Pagan and neo-pagan",
                      tree.ancestry("religion", estonia.labels_religion("..Earth Believer")))
        self.assertIn("Pagan and neo-pagan",
                      tree.ancestry("religion", estonia.labels_religion("Taara Beliver")))

    def test_shares_are_of_what_the_categories_hold(self):
        # Alajõe's religions hold 312 of the 302 people RL0452 counts there.
        block = estonia.census_block("religion", "RL0452", {"Orthodox": 180, "No religion": 132},
                                     302, ["Alajõe"], 2011)
        self.assertAlmostEqual(sum(g["pct"] for g in block["religion"]), 100.0, delta=0.2)
        self.assertIn("312 of the 302", block["religion_note"])

    def test_pxweb_withholds_the_eleven_redrawn_counties(self):
        table = pxweb.INSTANCES["EST"]["tables"][0]
        self.assertEqual(len(table.withhold), 11)
        self.assertNotIn("37", table.withhold)


class Latvia(unittest.TestCase):
    def test_a_parish_belongs_to_its_municipality_and_a_state_city_to_itself(self):
        self.assertEqual(latvia.municipality_of("LV0035400"), "LV0035000")
        self.assertEqual(latvia.municipality_of("LV0001000"), "LV0001000")

    def test_merged_madona_is_withheld_from_pxweb(self):
        self.assertIn("LV0038001", pxweb.INSTANCES["LVA"]["tables"][0].withhold)

    def test_ethnicity_labels_are_placed(self):
        self.assertEqual(nc.unplaced("ethnicity", set(latvia.ETHNICITY.values())), [])

    def test_every_residual_is_other_or_not_stated(self):
        self.assertEqual(latvia.ethnic_label(
            "Other ethnicities excluding Latvians, Russians, Belarusians, Ukrainians, Poles, "
            "Lithuanians, including not selected and not indicated ethnicity"),
            "Other or not stated")
        self.assertEqual(latvia.ethnic_label("Roma"), "Romani")


class Lithuania(unittest.TestCase):
    def test_office_abbreviations_are_written_out(self):
        self.assertEqual(lithuania.expand_lt("Tauragės r. sav."), "Tauragės rajono savivaldybė")
        self.assertEqual(lithuania.expand_en("Alytus d. mun."), "Alytus District Municipality")

    def test_genitive_city_names_find_their_code(self):
        names = {"21": "Klaipėda c. mun.", "55": "Klaipėda d. mun.", "27": "Panevėžys c. mun.",
                 "66": "Panevėžys d. mun."}
        out = lithuania.match_rows(["Klaipėdos c. mun.", "Klaipėdos d. mun",
                                    "Panevėžio c.mun.", "Panevėžys d. mun."], names, list(names))
        self.assertEqual(out, {"Klaipėdos c. mun.": "21", "Klaipėdos d. mun": "55",
                               "Panevėžio c.mun.": "27", "Panevėžys d. mun.": "66"})

    def test_a_withheld_cell_is_not_a_zero(self):
        self.assertIsNone(lithuania.cell("●"))
        self.assertIsNone(lithuania.cell(""))
        self.assertEqual(lithuania.cell(0.0), 0.0)

    def test_a_2011_county_is_read_with_its_parts_and_a_city_is_its_own_part(self):
        values = ["LV", "LV006", "LV0010000", "LV0320200", "LV0320201", "LV0320244"]
        texts = ["Latvija", "Rīgas reģions", "Rīga", "Aizkraukles novads", "..Aizkraukle",
                 "..Aizkraukles pagasts"]
        self.assertEqual(latvia.census_units(values, texts),
                         {"LV0010000": ["Rīga"],
                          "LV0320200": ["Aizkraukle", "Aizkraukles pagasts"]})

    def test_a_2011_county_goes_where_its_decisive_parts_are(self):
        new = {"a": ("Aizkraukle", "M1"), "b": ("Aizkraukles pagasts", "M1"),
               "c": ("Pilskalnes pagasts", "M1"), "d": ("Pilskalnes pagasts", "M2"),
               "e": ("Carnikavas pagasts", "M3"), "f": ("Rīga", "M4")}
        placed, single, divided = latvia.place_census_units(
            {"old1": ["Aizkraukle", "Pilskalnes pagasts"], "old2": ["Carnikavas pagasts"],
             "old3": ["Rīga"]}, new)
        self.assertEqual(placed, {"old1": "M1", "old2": "M3", "old3": "M4"})
        self.assertEqual(single, {"old2": "e", "old3": "f"})
        self.assertEqual(divided, {})
        # The nine cities of 2011 are today's seven state cities and three towns.
        self.assertEqual(set(latvia.OLD_CITIES.values()),
                         set(latvia.STATE_CITIES) | set(latvia.CITY_TOWNS) - {"LV0040010"})
        # A county of one parish, listed with nothing beneath it.
        self.assertEqual(latvia.place_census_units({"old": ["Carnikavas novads"]}, new),
                         ({"old": "M3"}, {"old": "e"}, {}))
        # A county the reform divided: every part found, in two municipalities.
        self.assertEqual(latvia.place_census_units(
            {"old": ["Aizkraukle", "Carnikavas pagasts"]}, new), ({}, {}, {"old": ["M1", "M3"]}))
        with self.assertRaises(SystemExit):     # parts in two, and one not found
            latvia.place_census_units({"old": ["Aizkraukle", "Carnikavas pagasts", "X", "Y",
                                               "Z"]}, new)
        with self.assertRaises(SystemExit):     # only a shared name: nothing decides
            latvia.place_census_units({"old": ["Pilskalnes pagasts"]}, new)

    def test_census_labels_are_placed(self):
        self.assertEqual(nc.unplaced("religion", lithuania.RELIGION_2011.values()), [])
        self.assertEqual(nc.unplaced("ethnicity", lithuania.ETHNIC_2011.values()), [])


def cell(region: str, age: str, sex: str) -> dict:
    return {"Region": (region, region), "Alder": (age, age), "Kon": (sex, sex)}


class Sweden(unittest.TestCase):
    def test_the_open_class_is_a_hundred_and_tot1_is_the_total(self):
        cells = [(cell("0114", "0", "1"), 10), (cell("0114", "99", "2"), 5),
                 (cell("0114", "100+1", "1"), 3), (cell("0114", "TOT1", "1"), 13),
                 (cell("0114", "TOT1", "2"), 5)]
        people, published = sweden.read_cells(cells)
        self.assertEqual(people["0114"].males[100], 3)
        self.assertEqual(people["0114"].females[99], 5)
        self.assertEqual(published["0114"], 18)
        self.assertEqual(people["0114"].total, 18)

    def test_a_band_or_another_total_stops_the_run(self):
        for age in ("0-4", "TOT", "TOT2"):
            with self.assertRaises(SystemExit):
                sweden.read_cells([(cell("0114", age, "1"), 10)])

    def test_cell_key_noise_passes_and_a_misread_does_not(self):
        people = {"0114": nc.AgeSex()}
        people["0114"].add(30, "m", 11_614)
        # Vaxholm's single years came to 11,614 against a published 11,635.
        self.assertLess(sweden.check_cells(people, {"0114": 11_635}), 0.002)
        with self.assertRaises(SystemExit):
            sweden.check_cells(people, {"0114": 12_614})
        with self.assertRaises(SystemExit):
            sweden.check_cells(people, {})

    def test_every_kommun_binds_by_scbs_names_goteborg_included(self):
        shapes = units("SWE", "admin2")
        lan = {u["id"]: u["name"] for u in units("SWE", "admin1")}
        codes = {pid: f"{i + 1:02d}" for i, pid in enumerate(sorted(lan))}
        sv = {code: lan[pid] for pid, code in codes.items()}
        kommuner = []
        for i, s in enumerate(sorted(shapes, key=lambda s: s["id"])):
            code = codes[s["parent"]] + f"{i:02d}"[-2:]
            while code in sv:                  # keep the codes unique within a län
                code = codes[s["parent"]] + f"{int(code[2:]) + 1:02d}"[-2:]
            sv[code] = {"Gothenburg": "Göteborg"}.get(s["name"], s["name"])
            kommuner.append(code)
        self.assertIn("Göteborg", sv.values())
        bound = sweden.bind_kommuner(sv, kommuner)
        self.assertEqual(len(set(bound.values())), 290)

    def test_every_lan_binds_by_its_swedish_name(self):
        names = ["Stockholms län", "Uppsala län", "Södermanlands län", "Östergötlands län",
                 "Jönköpings län", "Kronobergs län", "Kalmar län", "Gotlands län",
                 "Blekinge län", "Skåne län", "Hallands län", "Västra Götalands län",
                 "Värmlands län", "Örebro län", "Västmanlands län", "Dalarnas län",
                 "Gävleborgs län", "Västernorrlands län", "Jämtlands län",
                 "Västerbottens län", "Norrbottens län"]
        sv = {f"{i:02d}": n for i, n in enumerate(names, 1)}
        bound = sweden.bind_lan(sv, sorted(sv))
        self.assertEqual(len({s["id"] for s in bound.values()}), 21)
        with self.assertRaises(SystemExit):
            sweden.bind_lan({**sv, "99": "Nowhere län"}, sorted(sv) + ["99"])


class NationalMedian(unittest.TestCase):
    def test_a_median_off_the_published_one_stops_the_run(self):
        with mock.patch.object(nc, "published_median", return_value=(41.0, "Eurostat")):
            nc.check_national_median("SE", 2026, 41.2, "x")
            with self.assertRaises(SystemExit):
                nc.check_national_median("SE", 2026, 41.5, "x")

    def test_a_year_not_yet_published_is_checked_against_the_year_before(self):
        answers = {2026: (None, "not yet"), 2025: (41.0, "Eurostat")}
        with mock.patch.object(nc, "published_median", side_effect=lambda g, y: answers[y]):
            nc.check_national_median("SE", 2026, 41.6, "x")      # within 0.7
            with self.assertRaises(SystemExit):
                nc.check_national_median("SE", 2026, 41.8, "x")

    def test_small_groups_fold_into_other_and_zero_rows_go(self):
        counts = {"Finnish": 9_000, "Swedish": 990, "Sami": 1, "Wolof": 4, "Zulu": 0,
                  "Other language": 5}
        out, n, people = nc.fold_small(counts, 10_000, "Other language",
                                       keep=("Finnish", "Swedish", "Sami"))
        self.assertEqual(out, {"Finnish": 9_000, "Swedish": 990, "Sami": 1,
                               "Other language": 9})
        self.assertEqual((n, people), (1, 4))


class NorwayVintage(unittest.TestCase):
    CHANGES = {"codeChanges": [
        {"oldCode": "1662", "newCode": "5030", "changeOccurred": "2018-01-01"},
        {"oldCode": "5030", "newCode": "5001", "changeOccurred": "2020-01-01"},
        {"oldCode": "5001", "newCode": "5001", "changeOccurred": "2020-01-01"},
        {"oldCode": "0714", "newCode": "0715", "changeOccurred": "2018-01-01"},
        {"oldCode": "0702", "newCode": "0715", "changeOccurred": "2018-01-01"},
        {"oldCode": "1141", "newCode": "1103", "changeOccurred": "2020-01-01"},
        {"oldCode": "0101", "newCode": "3001", "changeOccurred": "2020-01-01"},
        {"oldCode": "3001", "newCode": "3101", "changeOccurred": "2024-01-01"},
    ]}

    def lines(self):
        with mock.patch.object(norway, "request_json", return_value=self.CHANGES):
            return norway.lineage(["1662", "0714", "0702", "1103", "0101"],
                                  "2017-01-02", "2026-01-02")

    def test_a_merged_kommune_is_counted_at_its_last_whole_year_under_its_number_then(self):
        lines = self.lines()
        hist, ended = lines["1662"]                     # Klæbu, into Trondheim in 2020
        self.assertEqual(ended, "2020-01-01")
        year = norway.last_whole_year(ended)
        self.assertEqual(year, 2019)
        self.assertEqual(norway.code_on(hist, f"{year}-01-01"), "5030")
        self.assertEqual(norway.last_whole_year(lines["0714"][1]), 2017)   # Hof, 2018
        self.assertEqual(norway.code_on(lines["0714"][0], "2017-01-01"), "0714")

    def test_a_kommune_that_kept_its_number_while_others_joined_it_ends_too(self):
        self.assertEqual(self.lines()["1103"][1], "2020-01-01")     # Stavanger

    def test_a_renumbered_kommune_goes_on_under_its_new_number(self):
        hist, ended = self.lines()["0101"]
        self.assertIsNone(ended)
        self.assertEqual(norway.code_on(hist, "2026-01-01"), "3101")
        self.assertEqual(norway.code_on(hist, "2020-12-31"), "3001")

    def test_a_change_during_the_year_leaves_that_january_whole(self):
        self.assertEqual(norway.last_whole_year("2020-07-01"), 2020)

    def test_klepp_and_time_are_withheld_and_a_remainder_under_three_percent_is_not_kept(self):
        self.assertEqual(set(norway.SPLIT_PARISH.values()), {"Klepp", "Time"})
        self.assertIn("Frøyland and Orstad", norway.SPLIT_PARISH_NOTE)
        klepp = {"KOSmedlemmerdnk0000": 17_139, "KOSmedltroslivs0000": 2_588,
                 "KOSpersoneralle0000": 19_848}
        self.assertIsNone(norway.religion(klepp, 2020, "Klepp"))
        time_ = {"KOSmedlemmerdnk0000": 11_374, "KOSmedltroslivs0000": 1_911,
                 "KOSpersoneralle0000": 19_106}
        self.assertIn("parish", norway.religion(time_, 2020, "Time")["religion_note"])


class IcelandVintage(unittest.TestCase):
    NAMES = {"2503": "Sandgerðisbær", "2504": "Sveitarfélagið Garður", "2510": "Suðurnesjabær",
             "7300": "Fjarðabyggð", "7613": "Breiðdalshreppur", "7708": "Hornafjörður",
             "8401": "Hornafjörður", "7000": "Seyðisfjarðarkaupstaður", "7400": "Múlaþing",
             "0000": "Reykjavíkurborg"}

    def series(self, **extra):
        base = {
            2017: {"2503": 1785, "2504": 1599, "7300": 4780, "7613": 183, "7708": 2300,
                   "7000": 674, "0000": 120_000},
            2018: {"2510": 3450, "7300": 5000, "7708": 2320, "7000": 670, "0000": 122_000},
            2019: {"2510": 3500, "7300": 5010, "7708": 2340, "7000": 675, "0000": 124_000},
            2020: {"2510": 3550, "7300": 5020, "8401": 2350, "7400": 690, "0000": 125_000},
        }
        base.update(extra)
        return base

    def test_each_merged_municipality_keeps_its_own_last_count(self):
        last = iceland.last_counts(["2503", "2504", "7300", "7613", "7708", "7000", "0000"],
                                   self.series(), self.NAMES)
        self.assertEqual(last["2503"], (2017, "2503"))          # into Suðurnesjabær, 2018
        self.assertEqual(last["7613"], (2017, "7613"))          # into Fjarðabyggð, 2018
        self.assertEqual(last["7300"], (2017, "7300"))          # took Breiðdalshreppur in
        self.assertEqual(last["7000"], (2019, "7000"))          # into Múlaþing, 2020
        self.assertEqual(last["7708"], (2020, "8401"))          # renumbered, not merged
        self.assertEqual(last["0000"], (2020, "0000"))

    def test_people_who_vanish_without_reappearing_stop_the_run(self):
        broken = self.series()
        broken[2018] = {k: v for k, v in broken[2018].items() if k != "2510"}
        with self.assertRaises(SystemExit):
            iceland.last_counts(["2503", "2504", "7300", "7613", "7708", "7000", "0000"],
                                broken, self.NAMES)

    def test_grindavik_note_names_the_evacuation(self):
        note = iceland.EVACUATED["2300"].format(now=819, year="2026", then=3669)
        self.assertIn("evacuated on 10 November 2023", note)
        self.assertIn("819", note)

    def test_a_region_names_the_municipality_renumbered_out_of_it_in_icelandic(self):
        # Hornafjörður: 7708 in the East in 2017, 8401 in the South today, and
        # drawn in the East. MAN02005 spells it in ASCII; the notes do not.
        drawn_in = {"8401": "Eastern Region", "7300": "Eastern Region",
                    "8000": "Southern Region"}
        spelled = {"8401": "Sveitarfélagið Hornafjörður", "7300": "Fjarðabyggð",
                   "8000": "Vestmannaeyjabær"}
        east = iceland.region_note("Eastern Region", drawn_in, spelled)
        south = iceland.region_note("Southern Region", drawn_in, spelled)
        self.assertIn("includes Sveitarfélagið Hornafjörður", east)
        self.assertIn("leaves out Sveitarfélagið Hornafjörður (drawn in the Eastern Region)",
                      south)
        self.assertNotIn("Fjarðabyggð", east)
        self.assertEqual(iceland.region_note("Westfjords", drawn_in, spelled),
                         " Summed from the municipalities the map draws in the region.")


class PxwebLabels(unittest.TestCase):
    def test_the_baltic_registers_labels_are_placed(self):
        for iso in ("EST", "LVA"):
            table = pxweb.INSTANCES[iso]["tables"][0]
            self.assertEqual(nc.unplaced("ethnicity", table.relabel.values()), [], iso)

    def test_latvias_two_readers_of_ire031_use_the_same_words(self):
        table = pxweb.INSTANCES["LVA"]["tables"][0]
        for office, ours in table.relabel.items():
            self.assertEqual(latvia.ethnic_label(office), ours)

    def test_a_relabelled_category_is_summed_under_its_new_name(self):
        table = pxweb.INSTANCES["EST"]["tables"][0]
        payload = {"id": ["Maakond", "Rahvus"], "size": [1, 3],
                   "dimension": {"Maakond": {"category": {"index": {"37": 0},
                                                          "label": {"37": "Harju county"}}},
                                 "Rahvus": {"category": {
                                     "index": {"1": 0, "2": 1, "9": 2},
                                     "label": {"1": "Total", "2": "Estonians",
                                               "9": "Ethnic nationality unknown"}}}},
                   "value": [10, 8, 2]}
        with mock.patch.object(pxweb, "variables", return_value={}), \
                mock.patch.object(pxweb, "build_query", return_value={}), \
                mock.patch.object(pxweb, "http_json", return_value=payload):
            areas, _ = pxweb.fetch("base", table)
        self.assertEqual(areas["37"]["counts"], {"Estonian": 8, "Not stated": 2})

    def test_finlands_long_tail_of_languages_is_folded_and_its_shares_make_the_total(self):
        table = pxweb.INSTANCES["FIN"]["tables"][0]
        # A region of 100,000: the national languages, Sami among them however
        # few, three languages under 0.05% each, the register's unknowns, and a
        # language nobody here speaks.
        counts = {"Finnish": 90_000, "Swedish": 8_000, "Sami": 10, "Russian": 1_500,
                  "Other language": 440, "Wolof": 20, "Zulu": 15, "Tamil": 5,
                  "Unknown": 10, "Ainu": 0}
        rows, note = pxweb.composition(table, counts, 100_000)
        got = {r["group"]: r["count"] for r in rows}
        self.assertEqual(got, {"Finnish": 90_000, "Swedish": 8_000, "Sami": 10,
                               "Russian": 1_500, "Other language": 490})
        self.assertAlmostEqual(sum(r["pct"] for r in rows), 100.0, delta=0.2)
        self.assertIn("also counts the 3 languages each under 0.05%", note)
        self.assertIn("the 10 recorded as unknown -- 50 people in all", note)

    def test_a_table_that_does_not_fold_only_loses_its_empty_rows(self):
        table = pxweb.INSTANCES["LVA"]["tables"][0]
        rows, note = pxweb.composition(table, {"Latvian": 900, "Romani": 1, "Jewish": 0},
                                       901)
        self.assertEqual([r["group"] for r in rows], ["Latvian", "Romani"])
        self.assertEqual(note, table.note)


class Lithuania2021(unittest.TestCase):
    HEAD = ["Administrative territory", "Total", "Lithuanians", "Poles", "Russians",
            "Belarusians", "Ukrainians", "Other", "Not indicated"]

    def test_perturbed_rows_pass_within_the_slack_and_a_misread_does_not(self):
        rows = [["Title"], self.HEAD,
                ["Elektrėnų sav.", 23376, 19651, 1572, 1163, 235, 178, 170, 408]]
        out, totals = lithuania.parse_perturbed(rows, lithuania.ETHNIC_2021, "t")
        self.assertEqual(out["Elektrėnų sav."]["Polish"], 1572)
        self.assertEqual(totals["Elektrėnų sav."], 23376)
        rows[2][2] = 29651
        with self.assertRaises(SystemExit):
            lithuania.parse_perturbed(rows, lithuania.ETHNIC_2021, "t")
        with self.assertRaises(SystemExit):
            lithuania.parse_perturbed([["x"], self.HEAD + ["Martians"]],
                                      lithuania.ETHNIC_2021, "t")

    def test_a_city_is_its_municipality_only_where_the_census_counts_the_same_people(self):
        names = {"10": {"lt": "Vilniaus apskritis", "en": "Vilnius county"},
                 **{str(20 + i): {"lt": f"M{i} sav.", "en": f"M{i} mun."} for i in range(8)},
                 "40": {"lt": "Kauno m. sav.", "en": "Kaunas c. mun."},
                 "41": {"lt": "Visagino sav.", "en": "Visaginas mun."},
                 "42": {"lt": "Kauno r. sav.", "en": "Kaunas d. mun."}}
        munis = [str(20 + i) for i in range(8)] + ["40", "41", "42"]
        vil_rows = {"Vilniaus apskr.": {"Lithuanian": 80}, **{
            f"M{i} sav.": {"Lithuanian": 10} for i in range(8)}}
        vil_tot = {k: 80 if k.startswith("Vilniaus") else 10 for k in vil_rows}
        urban = ({"Kaunas": {"Lithuanian": 298_753}, "Visaginas": {"Russian": 17_000}},
                 {"Kaunas": 298_753, "Visaginas": 17_000})
        out = lithuania.ethnicity_2021((vil_rows, vil_tot), urban, names, munis, ["10"],
                                       {"40": 298_753, "41": 18_000, "42": 90_000})
        self.assertEqual(out["40"][2], "urban")
        self.assertNotIn("41", out)            # the town is not all of the municipality
        self.assertNotIn("42", out)            # a district municipality is never the city
        self.assertEqual(out["10"][2], "vilnius")


if __name__ == "__main__":
    unittest.main()
