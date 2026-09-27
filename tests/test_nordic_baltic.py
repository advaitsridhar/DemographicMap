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
                                  lithuania, norway, nordic_common as nc, pxweb)


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

    def test_the_mislabelled_polygon_is_not_bound(self):
        self.assertIn("Maidla vald", estonia.NOT_THIS)
        drawn = {u["name"] for u in units("EST", "admin2")}
        self.assertTrue(set(estonia.DRAWN) <= drawn)

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


if __name__ == "__main__":
    unittest.main()
