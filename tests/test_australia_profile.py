"""Australia's 2021 Census profile: median age, sex ratio and ancestry by unit.

The fixtures are rows in the shape ``abs.unpack`` gives them, cut down to two
LGAs in one state: no network. The arithmetic and the binding are the parts
that can be wrong, and they are what is tested.
"""

import unittest

from scripts.fetch_census import australia_profile as ap


def g01(region, persons, male, female, name=None):
    return [({"SEXP_CODE": code, "PCHAR_CODE": "P_1", "REGION_CODE": region,
              "REGION": name or region}, value)
            for code, value in (("3", persons), ("1", male), ("2", female))]


def g01_chars(region, working, other, non_private):
    """G01's age and dwelling rows, each argument a (males, females) pair split evenly."""
    rows = []
    for codes, (male, female) in ((ap.WORKING_AGES, working), (ap.OTHER_AGES, other),
                                  ((ap.NON_PRIVATE,), non_private)):
        for i, code in enumerate(codes):
            share = (1 if i == 0 else 0) if len(codes) == 1 else 1 / len(codes)
            for sex, value in (("1", male), ("2", female), ("3", male + female)):
                rows.append(({"SEXP_CODE": sex, "PCHAR_CODE": code, "REGION_CODE": region},
                             value * share))
    return rows


def g02(region, median):
    return [({"MEDAVG_CODE": "1", "REGION_CODE": region}, median),
            ({"MEDAVG_CODE": "2", "REGION_CODE": region}, 805.0)]


def g08(region, parts, persons=None):
    # The table's own total row counts persons, not responses: Albury's G08
    # total is 56,093, its population, beside some 73,000 responses.
    persons = persons if persons is not None else round(sum(parts.values()) / 1.3)
    rows = [({"ANCP_CODE": "_T", "ANCP": "Total", "BPPP_CODE": "_T",
              "REGION_CODE": region}, persons)]
    for i, (label, value) in enumerate(parts.items()):
        rows.append(({"ANCP_CODE": str(i), "ANCP": label, "BPPP_CODE": "_T",
                      "REGION_CODE": region}, value))
        # The parents'-birthplace columns, which must never be added in.
        rows.append(({"ANCP_CODE": str(i), "ANCP": label, "BPPP_CODE": "1",
                      "REGION_CODE": region}, value / 2))
    return rows


class Persons(unittest.TestCase):
    def test_the_three_sexes_are_read_from_total_persons(self):
        got = ap.persons(g01("10050", 56093, 27416, 28677))
        self.assertEqual(got["10050"], {"persons": 56093, "male": 27416, "female": 28677})

    def test_sexes_that_do_not_make_the_persons_stop_the_run(self):
        with self.assertRaises(SystemExit):
            ap.persons(g01("10050", 56093, 20000, 28677))

    def test_the_perturbation_of_small_cells_is_allowed(self):
        got = ap.persons(g01("10050", 120, 70, 60))
        self.assertEqual(got["10050"]["persons"], 120)


class Ancestry(unittest.TestCase):
    def test_only_the_total_responses_column_is_read(self):
        parts, people = ap.ancestries(g08("10050", {"English": 20000, "Australian": 18000,
                                                    "Not stated": 4000}, 32000))["10050"]
        self.assertEqual(parts, {"English": 20000, "Australian": 18000, "Not stated": 4000})
        self.assertEqual(people, 32000)

    def test_shares_are_of_people_and_may_pass_100(self):
        rows = ap.ancestry_shares({"English": 30000, "Australian": 28000, "Irish": 9000},
                                  people=50000)
        self.assertEqual([r["group"] for r in rows], ["English", "Australian", "Irish"])
        self.assertEqual(rows[0]["pct"], 60.0)
        self.assertGreater(sum(r["pct"] for r in rows), 100)

    def test_more_than_two_responses_a_person_stop_the_run(self):
        with self.assertRaises(SystemExit):
            ap.ancestries(g08("10050", {"English": 20000, "Australian": 18000}, 15000))

    def test_fewer_responses_than_people_stop_the_run(self):
        with self.assertRaises(SystemExit):
            ap.ancestries(g08("10050", {"English": 20000, "Australian": 18000}, 60000))


def unit(uid, name, code, parent, population, language=None):
    return {"id": uid, "name": name, "parent": parent, "codes": {"asgs": code},
            "population": {"value": population},
            "language": language if language is not None
            else [{"group": "English only", "pct": 90.0}]}


STATE = unit("S1", "New South Wales", "1", "AUS", 8072171)
ALBURY = unit("A1", "Albury", "10050", "S1", 56093)
BAYSIDE = unit("A2", "Bayside", "10500", "S1", 175184)


class Binding(unittest.TestCase):
    def test_units_are_bound_by_the_code_they_carry(self):
        got = ap.bind([ALBURY, BAYSIDE], "admin2", {"S1": STATE})
        self.assertEqual(got["10050"]["id"], "A1")
        self.assertEqual(got["10500"]["id"], "A2")

    def test_a_unit_in_the_wrong_state_stops_the_run(self):
        victoria = unit("S2", "Victoria", "2", "AUS", 6503503)
        with self.assertRaises(SystemExit):
            ap.bind([ALBURY], "admin2", {"S1": victoria})

    def test_two_units_with_one_code_stop_the_run(self):
        twin = unit("A3", "Albury twin", "10050", "S1", 1)
        with self.assertRaises(SystemExit):
            ap.bind([ALBURY, twin], "admin2", {"S1": STATE})


class Record(unittest.TestCase):
    def test_the_record_carries_the_published_median_and_the_ratio(self):
        people = {"persons": 56093, "male": 27416, "female": 28677}
        rec = ap.unit_record("10050", "Albury", ALBURY, "admin2", people=people,
                             median=39.0, ancestry=({"English": 20000, "Not stated": 4000},
                                                    56093.0),
                             parent_name="New South Wales")
        self.assertEqual(rec["median_age"]["value"], 39)
        self.assertIsInstance(rec["median_age"]["value"], int)
        self.assertEqual(rec["sex_ratio"]["value"], 95.6)
        self.assertEqual(rec["match_by"], "shape_id")
        self.assertEqual(rec["shape_id"], "A1")
        self.assertEqual(rec["ethnicity_basis"], "ancestry (multi-response)")
        self.assertEqual(rec["ethnicity"][0], {"group": "English", "pct": 35.7, "count": 20000})
        # Nothing the tables do not carry is claimed: population stays the map's.
        self.assertEqual(rec["population"]["status"], "not_available")

    def test_an_unusual_ratio_says_where_it_lies(self):
        # Menzies' 2021 totals, 394 males and 128 females; the split by age and
        # dwelling is made up for the test.
        people = {"persons": 522, "male": 394, "female": 128}
        # Non-private dwellings can hold more people on census night than live
        # in the place: the count is of where people were.
        chars = ap.characteristics(g01_chars("51540", working=(318, 83), other=(76, 45),
                                             non_private=(1021, 204)))["51540"]
        context = ap.ratio_context("Menzies", people, chars)
        self.assertIn("Among those aged 20 to 64, 383.1 males per 100 females "
                      "(318 males, 83 females); at other ages, 168.9.", context)
        self.assertIn("held 1,225 people (1,021 males, 204 females), a count of where people "
                      "were that night, whether or not they live here.", context)
        self.assertNotIn("of the people", context)
        self.assertNotIn("private dwellings the ratio", context)
        rec = ap.unit_record("51540", "Menzies", ALBURY, "admin2", people=people, median=None,
                             ancestry=None, parent_name=None, context=context)
        self.assertTrue(rec["sex_ratio_note"].endswith(context))
        # A usual ratio says nothing more; nor does a unit with few non-private dwellers.
        self.assertEqual(ap.ratio_context("Albury", {"persons": 200, "male": 100,
                                                     "female": 100}, chars), "")
        few = ap.characteristics(g01_chars("1", working=(318, 83), other=(76, 45),
                                           non_private=(2, 0)))["1"]
        self.assertNotIn("non-private", ap.ratio_context("Menzies", people, few))

    def test_age_groups_that_do_not_make_the_sexes_stop_the_run(self):
        people = {"persons": 522, "male": 394, "female": 128}
        chars = ap.characteristics(g01_chars("1", working=(218, 83), other=(76, 45),
                                             non_private=(0, 0)))["1"]
        with self.assertRaises(SystemExit):
            ap.ratio_context("Menzies", people, chars)

    def test_the_multi_response_sentence_follows_the_numbers(self):
        # Albury: responses exceed the people, so the shares pass 100.
        people = {"persons": 56093, "male": 27416, "female": 28677}
        rec = ap.unit_record("10050", "Albury", ALBURY, "admin2", people=people, median=39.0,
                             ancestry=({"English": 40000, "Australian": 33000}, 56093.0),
                             parent_name=None)
        self.assertIn("the 73,000 responses exceed the people, so the shares sum to more "
                      "than 100", rec["ethnicity_note"])
        # Maralinga Tjarutja: 87 responses for 96 people, the shares sum to 90.6.
        small = {"persons": 96, "male": 50, "female": 46}
        rec = ap.unit_record("4", "Maralinga Tjarutja", ALBURY, "admin2", people=small,
                             median=None, ancestry=({"Australian Aboriginal": 66,
                                                     "Not stated": 8, "English": 13}, 96.0),
                             parent_name=None)
        note = rec["ethnicity_note"]
        self.assertNotIn("exceed", note)
        self.assertNotIn("more than 100,", note)
        self.assertIn("leaves 87 responses for 96 people, so the shares sum to 90.6 rather than "
                      "more than 100", note)
        self.assertAlmostEqual(sum(g["pct"] for g in rec["ethnicity"]), 90.6, places=1)
        # Belyuen: as many responses as people.
        self.assertIn("so the shares sum to 100 rather than", ap.multi_response(149, 149))

    def test_g08_and_g01_disagreeing_about_the_people_stop_the_run(self):
        people = {"persons": 1000, "male": 500, "female": 500}
        with self.assertRaises(SystemExit):
            ap.unit_record("10050", "Albury", ALBURY, "admin2", people=people, median=39,
                           ancestry=({"English": 2500}, 2000.0), parent_name=None)


RELIGIONS = (("Total", "_T"), ("Christianity Total", "2_T"), ("Catholic", "207"),
             ("Secular Beliefs and Other Spiritual Beliefs and No Religious Affiliation Total",
              "7_T"), ("No Religion, so described", "7101"),
             ("Religious affiliation not stated", "_N"))


def g14(region, total):
    # Christianity 43.9% and the Secular branch 40%, with a child under each.
    values = (total, 0.439 * total, 0.2 * total, 0.4 * total, 0.389 * total, 0.161 * total)
    return [({"RELP": label, "RELP_CODE": code, "SEXP": "Persons", "SEXP_CODE": "3",
              "REGION": region, "REGION_CODE": region}, value)
            for (label, code), value in zip(RELIGIONS, values)]


LANGUAGES = (("Total", "_T"), ("Speaks English only", "1"), ("Other Languages Total", "O_T"),
             ("Italian", "3103"), ("Other", "_O"), ("Not stated", "_N"))


def g13(region, total):
    # English only 72%, other languages 23% (Italian 3%, the rest 20%), not stated 5%.
    values = (total, 0.72 * total, 0.23 * total, 0.03 * total, 0.2 * total, 0.05 * total)
    return [({"LANP": label, "LANP_CODE": code, "ENGLP": "Total", "ENGLP_CODE": "_T",
              "SEXP": "Persons", "SEXP_CODE": "3", "REGION": region, "REGION_CODE": region},
             value)
            for (label, code), value in zip(LANGUAGES, values)]


def g13_coarse(region, total, english, other, indigenous, not_stated):
    return [({"LANP_CODE": code, "ENGLP_CODE": "_T", "REGION_CODE": region}, value)
            for code, value in (("_T", total), ("1", english), ("O_T", other),
                                ("8", indigenous), ("_N", not_stated))]


class CoarseLanguage(unittest.TestCase):
    def test_east_arnhem_partitions_at_the_coarse_level(self):
        # G13's own East Arnhem figures: 8,778 people, 504 English only, 7,803
        # another language of whom 7,676 an Indigenous one, 469 not stated.
        got = ap.coarse_language(g13_coarse("71300", 8778, 504, 7803, 7676, 469))["71300"]
        self.assertEqual(got, {"English only": 504, "Australian Indigenous Languages": 7676,
                               "Other languages": 127, "Not stated": 469})

    def test_a_coarse_partition_that_misses_the_total_stops_the_run(self):
        with self.assertRaises(SystemExit):
            ap.coarse_language(g13_coarse("71300", 8778, 504, 5000, 4000, 469))

    def test_more_indigenous_than_other_languages_stops_the_run(self):
        with self.assertRaises(SystemExit):
            ap.coarse_language(g13_coarse("71300", 8778, 504, 7803, 8500, 469))


class StateCompositions(unittest.TestCase):
    def test_the_outermost_level_is_read_and_checked(self):
        religion, language = ap.state_compositions(g14("AUS", 25_422_788) + g14("1", 1000),
                                                   g13("AUS", 25_422_788) + g13("1", 1000))
        groups = {r["group"]: r["pct"] for r in religion["AUS"]}
        self.assertEqual(groups["Christianity"], 43.9)
        self.assertNotIn("Catholic", groups)
        self.assertEqual({r["group"]: r["pct"] for r in language["1"]}["English only"], 72.0)

    def test_a_different_national_figure_stops_the_run(self):
        rows = g14("AUS", 25_422_788)
        rows[1] = (rows[1][0], 0.3 * 25_422_788)
        rows[2] = (rows[2][0], 0.1 * 25_422_788)
        rows[5] = (rows[5][0], 0.3 * 25_422_788)
        with self.assertRaises(SystemExit):
            ap.state_compositions(rows, g13("AUS", 25_422_788))

    @staticmethod
    def g13_indigenous(region, total, indigenous):
        """G13 with its "Other" (code _O) holding the Indigenous languages (code 8)."""
        return g13(region, total) + [(
            {"LANP": "Australian Indigenous Languages", "LANP_CODE": "8", "ENGLP": "Total",
             "ENGLP_CODE": "_T", "SEXP": "Persons", "SEXP_CODE": "3", "REGION": region,
             "REGION_CODE": region}, indigenous)]

    def test_the_indigenous_languages_come_out_of_other_and_are_named(self):
        # The Northern Territory's shape: "Other" 20% of whom 15 points Indigenous.
        _, language = ap.state_compositions(
            g14("AUS", 25_422_788) + g14("7", 1000),
            g13("AUS", 25_422_788) + self.g13_indigenous("7", 1000, 150))
        groups = {r["group"]: r["pct"] for r in language["7"]}
        self.assertEqual(groups["Australian Indigenous Languages"], 15.0)
        self.assertEqual(groups["Other"], 5.0)
        self.assertEqual(groups["English only"], 72.0)
        self.assertAlmostEqual(sum(groups.values()), 100.0, places=1)
        self.assertNotIn("Australian Indigenous Languages",
                         {r["group"] for r in language["AUS"]})

    def test_more_indigenous_speakers_than_other_holds_stops_the_run(self):
        with self.assertRaises(SystemExit):
            ap.state_compositions(g14("AUS", 25_422_788) + g14("7", 1000),
                                  g13("AUS", 25_422_788) + self.g13_indigenous("7", 1000, 400))


class Build(unittest.TestCase):
    NSW = 25_422_788 - 8 * 1000

    def tables(self, rest_of_nsw=None):
        rest = self.NSW - 56093 - 175184 if rest_of_nsw is None else rest_of_nsw
        national = g01("AUS", 25_422_788, 12_545_154, 12_877_634)
        states, lgas = [], []
        for code in "123456789":
            persons = self.NSW if code == "1" else 1000
            states += g01(code, persons, persons // 2, persons - persons // 2)
            if code != "1":
                lgas += g01(f"{code}0010", 1000, 500, 500)
        # NSW's people outside the two drawn LGAs, under a code no polygon has.
        lgas += g01("19399", rest, rest // 2, rest - rest // 2, "Unincorporated NSW")
        top_ancestry = g08("AUS", {"English": 8_389_400, "Australian": 7_601_400,
                                   "Other": 16_000_000}, 25_422_788)
        for code in "123456789":
            people = self.NSW if code == "1" else 1000
            top_ancestry += g08(code, {"English": 0.33 * people, "Australian": 0.3 * people,
                                       "Other": 0.7 * people}, people)
        return {
            ("G01", "LGA"): g01("10050", 56093, 27416, 28677, "Albury")
            + g01("10500", 175184, 85000, 90184, "Bayside (NSW)") + lgas,
            ("G01", "SA2"): national + states,
            ("G02", "LGA"): g02("10050", 39.0) + g02("10500", 38.0),
            ("G02", "SA2"): g02("AUS", 38.0) + [r for c in "123456789" for r in g02(c, 40.0)],
            ("G08", "LGA"): g08("10050", {"English": 20000, "Australian": 19000,
                                         "Other": 30000}, 56093)
            + g08("10500", {"English": 50000, "Australian": 40000, "Other": 130000}, 175184),
            ("G08", "SA2"): top_ancestry,
            ("G14", "SA2"): g14("AUS", 25_422_788)
            + [r for c in "123456789" for r in g14(c, self.NSW if c == "1" else 1000)],
            ("G13", "SA2"): g13("AUS", 25_422_788)
            + [r for c in "123456789" for r in g13(c, self.NSW if c == "1" else 1000)],
            ("G13", "LGA"): g13_coarse("10050", 56093, 48000, 5000, 100, 3093),
        }

    def admin1(self):
        return [STATE] + [unit(f"S{c}", f"State {c}", c, "AUS", 1000) for c in "23456789"]

    def test_a_state_and_its_lgas_are_written(self):
        records = ap.build(self.tables(), self.admin1(), [ALBURY, BAYSIDE])
        names = {r["name"]: r for r in records}
        self.assertEqual(names["Bayside (NSW)"]["shape_id"], "A2")
        self.assertEqual(names["Albury"]["median_age"]["value"], 39)
        self.assertEqual(len([r for r in records if r["level"] == "admin1"]), 9)
        self.assertEqual(len([r for r in records if r["level"] == "admin2"]), 2)
        nsw = next(r for r in records if r["shape_id"] == "S1")
        self.assertEqual(nsw["population"]["value"], self.NSW)
        self.assertEqual({r["group"]: r["pct"] for r in nsw["religion"]}["Christianity"], 43.9)
        # Albury's language is the map's (abs.py's): it is written only where
        # the map has none.
        self.assertEqual(names["Albury"]["language"]["status"], "not_available")

    def test_the_census_file_decides_not_the_built_map(self):
        # The built map carries this file's own coarse partition from the run
        # before; read from it, a re-run would see a language and write none.
        built = dict(ALBURY, language=[{"group": "English only", "pct": 85.6}])
        records = ap.build(self.tables(), self.admin1(), [built, BAYSIDE], listed={"10000"})
        albury = {r["name"]: r for r in records}["Albury"]
        self.assertIn("coarsest level", albury["language_note"])
        records = ap.build(self.tables(), self.admin1(), [built, BAYSIDE], listed={"10050"})
        self.assertEqual({r["name"]: r for r in records}["Albury"]["language"]["status"],
                         "not_available")

    def test_an_lga_with_no_language_takes_the_coarse_partition(self):
        mute = dict(ALBURY, language={"status": "not_available"})
        records = ap.build(self.tables(), self.admin1(), [mute, BAYSIDE])
        albury = next(r for r in records if r["name"] == "Albury")
        self.assertEqual({r["group"] for r in albury["language"]},
                         {"English only", "Australian Indigenous Languages",
                          "Other languages", "Not stated"})
        self.assertIn("coarsest level", albury["language_note"])

    def test_lgas_that_do_not_make_their_state_stop_the_run(self):
        with self.assertRaises(SystemExit):
            ap.build(self.tables(rest_of_nsw=10), self.admin1(), [ALBURY, BAYSIDE])

    def test_a_drawn_lga_the_tables_lack_stops_the_run(self):
        ghost = unit("A9", "Nowhere", "19999", "S1", 10)
        with self.assertRaises(SystemExit):
            ap.build(self.tables(), self.admin1(), [ALBURY, BAYSIDE, ghost])

    def test_a_population_far_from_the_maps_stops_the_run(self):
        wrong = unit("A1", "Albury", "10050", "S1", 90000)
        with self.assertRaises(SystemExit):
            ap.build(self.tables(), self.admin1(), [wrong, BAYSIDE])


if __name__ == "__main__":
    unittest.main()
