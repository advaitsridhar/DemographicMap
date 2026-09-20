"""The Atlas of the Languages of Iran reader: the rules it must not lose.

Six of these tests are about a decision that, got wrong, would be invisible on
the map -- a province summed over nested rows, a settlement weighted by a
population that is not its own, a shahrestan joined to the wrong polygon, a
share string half-understood. The fixtures are built from the real header and
from rows shaped like the ones in data/raw/iran, small enough that the
arithmetic can be done by hand in the assertion.

The rest read the committed output and check it against the world: Kordestān
is Central Kurdish, Khuzestān has a large Arabic-speaking population, and no
record anywhere claims that a census said so.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts import build_entities as be  # noqa: E402
from scripts.fetch_census import iran_ali as m  # noqa: E402

COLUMNS = ["Attribution", "Nunaliit_ID", "Nunaliit_revision_code",
           "ALI_unique_ID_place", "province_Persian", "province_roman",
           "shahrestan_Persian", "shahrestan_roman", "bakhsh_Persian",
           "bakhsh_roman", "city_Persian", "city_roman", "dehestan_Persian",
           "dehestan_roman", "settlement_Persian", "settlement_roman",
           "local_name", "local_name_source", "population_2011_census",
           "population_2011_comment", "population_2016_census",
           "population_2016_comment", "language_distribution_estimate",
           "language_distribution_source", "latitude", "longitude", "notes"]

PROCESSED = ROOT / "data" / "processed" / "iran_ali_language.json"
RAW = ROOT / "data" / "raw" / "iran"


def line(**cells) -> str:
    """One CSV row, given by column name."""
    return ",".join('"{}"'.format(str(cells.get(c, "")).replace('"', '""'))
                    for c in COLUMNS)


def csv_text(rows) -> str:
    head = ",".join(f'"{c}"' for c in COLUMNS)
    licence = line(Attribution=m.LICENCE)
    return "\n".join([head, licence, *rows]) + "\n"


CITATION = {
    "provinces": [
        {"csv_province_roman": "Kordestān", "shape_name": "Kurdistan",
         "year": 2016, "authors": "Mohammadirad, Masoud, Erik Anonby, et al.",
         "title": "Language distribution in Kordestan Province, Iran",
         "url": "http://iranatlas.net/module/language-distribution.kordestan"},
    ],
}


def province_rows(**over):
    """A province the way a file gives one: four nested totals and two villages.

    The province, the shahrestan, the bakhsh and the dehestan each print a
    population, and each of those populations already contains the one below
    it. Only the two settlements are people; everything above them is the same
    people counted again.
    """
    return [
        line(ALI_unique_ID_place="1120000", province_roman="Kordestān",
             population_2011_census="1000"),
        line(ALI_unique_ID_place="1120001", province_roman="Kordestān",
             shahrestan_roman="Marivān", population_2011_census="1000"),
        line(ALI_unique_ID_place="1120002", province_roman="Kordestān",
             shahrestan_roman="Marivān", bakhsh_roman="Sar Shiv",
             population_2011_census="1000"),
        line(ALI_unique_ID_place="1120003", province_roman="Kordestān",
             shahrestan_roman="Marivān", bakhsh_roman="Sar Shiv",
             dehestan_roman="Sar Shiv", local_name="Sar Shiv",
             population_2011_census="1000"),
        line(ALI_unique_ID_place="1120004", province_roman="Kordestān",
             shahrestan_roman="Marivān", bakhsh_roman="Sar Shiv",
             dehestan_roman="Sar Shiv", settlement_roman="Āgjeh",
             population_2011_census=over.get("first_2011", "800"),
             population_2016_census=over.get("first_2016", ""),
             language_distribution_estimate=over.get(
                 "first_language", "Central Kurdish 100%"),
             language_distribution_source="Masoud Mohammadirad, field notes 2015"),
        line(ALI_unique_ID_place="1120005", province_roman="Kordestān",
             shahrestan_roman="Marivān", bakhsh_roman="Sar Shiv",
             dehestan_roman="Sar Shiv", settlement_roman="Bābārshāni",
             population_2011_census=over.get("second_2011", "200"),
             language_distribution_estimate=over.get(
                 "second_language", "Turkic 80%; Southern Kurdish 20%"),
             language_distribution_source="Erik Anonby, field notes 2014"),
    ]


def build(rows, citation=CITATION):
    """Run the reader over one made-up province file, quietly."""
    with tempfile.TemporaryDirectory() as folder:
        where = Path(folder)
        (where / "Language_Distribution_Kordestan_20260921.csv").write_text(
            csv_text(rows), encoding="utf-8")
        (where / m.CITATIONS).write_text(json.dumps(citation), encoding="utf-8")
        log = io.StringIO()
        with redirect_stderr(log):
            records, tally = m.build(where)
        return records, tally, log.getvalue()


def only(records, name):
    found = [r for r in records if r["name"] == name]
    return found[0] if found else None


class TheNestingRule(unittest.TestCase):
    """The one mistake that would be invisible: adding a hierarchy up."""

    def test_a_province_is_its_settlements_and_not_its_own_total_row(self):
        records, _, _ = build(province_rows())
        province = only(records, "Kurdistan")
        shares = {r["group"]: r["pct"] for r in province["language"]["estimate"]}
        # 800 people all Central Kurdish, 200 people 80% Turkic and 20%
        # Southern Kurdish, out of a province of 1,000.
        self.assertEqual(shares, {"Central Kurdish": 80.0, "Turkic": 16.0,
                                  "Southern Kurdish": 4.0})
        self.assertEqual(province["language"]["settlements"], 2)
        self.assertEqual(province["language"]["coverage_pct"], 100.0)

    def test_an_aggregate_row_with_a_local_name_is_still_an_aggregate(self):
        """The weaker leaf rule this module rejected, held out.

        The dehestan row in the fixture carries a local name of its own, and
        20 real rows do. A rule that took "has a local name" for a settlement
        would count those 1,000 people twice and read the province as 200%
        covered.
        """
        records, _, _ = build(province_rows())
        province = only(records, "Kurdistan")
        self.assertEqual(province["language"]["coverage_pct"], 100.0)
        self.assertIn("1,000 that the atlas's own total",
                      province["language"]["note"])

    def test_the_province_total_is_the_row_with_the_atlas_id_not_the_biggest(self):
        """Kohgiluyeh va Boyer Ahmad's file has no province row at all.

        Taking the largest population instead put its biggest county on the
        province, a denominator two and a half times too small. Here the
        province row is deliberately *smaller* than the shahrestan row above
        it, which only an id-based rule survives.
        """
        rows = province_rows()
        rows[0] = line(ALI_unique_ID_place="1120000", province_roman="Kordestān",
                       population_2011_census="1000")
        rows[1] = line(ALI_unique_ID_place="1120001", province_roman="Kordestān",
                       shahrestan_roman="Marivān", population_2011_census="9999")
        records, _, _ = build(rows)
        self.assertIn("1,000 that the atlas's own total",
                      only(records, "Kurdistan")["language"]["note"])


class TheShareParser(unittest.TestCase):
    def test_a_single_language_and_a_split_one(self):
        self.assertEqual(m.parse_shares("Central Kurdish 100%"),
                         ({"Central Kurdish": 100.0}, ""))
        self.assertEqual(m.parse_shares("Turkic 80%; Southern Kurdish 20%"),
                         ({"Turkic": 80.0, "Southern Kurdish": 20.0}, ""))

    def test_the_double_space_the_file_really_writes(self):
        shares, why = m.parse_shares("Rāji  80%; Tehrāni type Persian 20%")
        self.assertEqual(why, "")
        self.assertEqual(shares["Rāji"], 80.0)

    def test_a_rounding_scale_extra_is_accepted_and_normalised(self):
        """Anzali: a 0.04% Armenian presence on top of a partition of 100."""
        text = ("Standard type Persian 70%; Western Gilaki 20%; Turkic 10%; "
                "Armenian 0.04%")
        shares, why = m.parse_shares(text)
        self.assertEqual(why, "")
        self.assertAlmostEqual(sum(shares.values()), 100.04, places=3)

    def test_the_string_it_must_refuse_is_refused_with_a_reason(self):
        """Rasht's own estimate, which accounts for 90% of the city.

        Nothing here knows what the other 10% speak, and the refusal is the
        only honest answer: normalising it up would hand the missing tenth to
        Persian, Gilaki and Turkic in the proportions of the nine tenths that
        were measured, which is a guess wearing a measurement's clothes.
        """
        text = ("Standard type Persian 50%; Western Gilaki 30%; Turkic 10%; "
                "Armenian 0.01%")
        shares, why = m.parse_shares(text)
        self.assertEqual(shares, {})
        self.assertIn("90.01", why)
        self.assertIn("not to 100", why)

    def test_a_string_that_is_not_shares_at_all_is_refused(self):
        shares, why = m.parse_shares("mostly Kurdish")
        self.assertEqual(shares, {})
        self.assertIn("is not", why)

    def test_a_refused_settlement_counts_against_coverage_rather_than_vanishing(self):
        records, _, _ = build(province_rows(
            second_language="Turkic 60%; Southern Kurdish 20%"))
        province = only(records, "Kurdistan")
        # The 200-person village is refused, so 800 of 1,000 are covered and
        # the record says which village and why.
        self.assertEqual(province["language"]["coverage_pct"], 80.0)
        self.assertEqual(province["language"]["settlements_refused"], 1)
        self.assertIn("Bābārshāni (200 people)", province["language"]["note"])
        self.assertIn("add to 80%", province["language"]["note"])


class TheWeights(unittest.TestCase):
    def test_2016_wins_where_there_is_one_and_2011_is_the_fallback(self):
        self.assertEqual(m.weight_of({"population_2016_census": "120",
                                      "population_2011_census": "100"}),
                         (120, 2016))
        self.assertEqual(m.weight_of({"population_2016_census": "",
                                      "population_2011_census": "100"}),
                         (100, 2011))
        self.assertEqual(m.weight_of({"population_2016_census": "",
                                      "population_2011_census": ""}),
                         (None, None))

    def test_the_newer_figure_is_what_the_composition_is_weighted_by(self):
        records, _, _ = build(province_rows(first_2011="800", first_2016="1800"))
        shares = {r["group"]: r["pct"]
                  for r in only(records, "Kurdistan")["language"]["estimate"]}
        # 1,800 Central Kurdish against 200 in the other village, not 800.
        self.assertEqual(shares["Central Kurdish"], 90.0)

    def test_a_settlement_with_no_population_is_excluded_and_counted(self):
        records, _, _ = build(province_rows(second_2011=""))
        province = only(records, "Kurdistan")
        shares = {r["group"]: r["pct"] for r in province["language"]["estimate"]}
        self.assertEqual(shares, {"Central Kurdish": 100.0})
        self.assertEqual(province["language"]["settlements_unweighted"], 1)
        self.assertIn("no population in either census year",
                      province["language"]["note"])
        self.assertEqual(province["language"]["coverage_pct"], 80.0)


class TheRomanisations(unittest.TestCase):
    """Reconciled from a table that can be read, never from how alike two
    strings look."""

    def test_the_four_provinces_the_boundary_file_spells_differently(self):
        shapes = {m.fold(s["name"]): s for s in m.shapes("admin1")}
        for roman, expected in [("Kordestān", "Kurdistan"),
                                ("Esfahān", "Isfahan"),
                                ("Chahār Mahāl va Bakhtiāri",
                                 "Chaharmahal and Bakhtiari"),
                                ("Kohgiluyeh va Boyer Ahmad",
                                 "Kohgiluyeh and Boyer-Ahmad")]:
            self.assertEqual(m.province_shape(roman, shapes)["name"], expected)

    def test_a_province_that_differs_only_by_diacritics_needs_no_alias(self):
        shapes = {m.fold(s["name"]): s for s in m.shapes("admin1")}
        for roman in ("Gilān", "Hamadān", "Hormozgān", "Ilām", "Kermānshāh",
                      "Khuzestān", "Lorestān", "Bushehr"):
            self.assertNotIn(roman, m.PROVINCE_ALIASES)
            self.assertIsNotNone(m.province_shape(roman, shapes))

    def test_an_unknown_province_is_refused_rather_than_guessed_at(self):
        shapes = {m.fold(s["name"]): s for s in m.shapes("admin1")}
        # Iran has a Fars and a Qom; "Fārs va Qom" is neither, and nothing
        # here may quietly hand it one of them.
        self.assertIsNone(m.province_shape("Fārs va Qom", shapes))

    def test_a_county_alias_reaches_the_boundary_files_spelling(self):
        shapes = {m.fold(s["name"]): s for s in m.shapes("admin2")}
        self.assertEqual(m.county_shape("Kurdistan", "Qorveh", shapes)["name"],
                         "Ghorveh")
        self.assertEqual(m.county_shape("Bushehr", "Dayyer", shapes)["name"],
                         "Deyr")

    def test_the_shahrestan_of_esfahan_is_the_county_and_not_the_city(self):
        """Isfahan province has two shapes that fold to one name.

        "Isfahan" is a 0.2-degree polygon over the city; "Isfahan County" is
        the 1.7-degree one around it. The shahrestan's figures belong to the
        county, and putting them on the city would be the mis-match that looks
        exactly like a right answer.
        """
        shapes = {s["name"]: s for s in m.shapes("admin2")}
        self.assertIn("Isfahan", shapes)
        self.assertIn("Isfahan County", shapes)
        self.assertEqual(m.SHAHRESTAN_ALIASES["Isfahan"]["Esfahān"],
                         "Isfahan County")
        written = {r["name"] for r in json.loads(PROCESSED.read_text("utf-8"))
                   if r["level"] == "admin2"}
        self.assertIn("Isfahan County", written)
        self.assertNotIn("Isfahan", written)

    def test_one_county_spelled_two_ways_is_read_as_one(self):
        """Gilān writes "Rudsar" on 357 rows and "Rud Sar" on the town's own.

        Keeping them apart left the county reading 73.6% covered when its
        settlements and its town together cover 99.4% of it.
        """
        rows = province_rows()
        rows.append(line(ALI_unique_ID_place="1120006",
                         province_roman="Kordestān", shahrestan_roman="Marivan",
                         bakhsh_roman="Markazi", city_roman="Marivān",
                         population_2011_census="100",
                         language_distribution_estimate="Hōrāmi 100%",
                         language_distribution_source="Erik Anonby, field notes 2014"))
        records, _, _ = build(rows)
        counties = [r for r in records if r["level"] == "admin2"]
        self.assertEqual(len(counties), 1)
        self.assertEqual(counties[0]["language"]["settlements"], 3)


class TheLicence(unittest.TestCase):
    def test_it_is_carried_verbatim_onto_every_record(self):
        for row in json.loads(PROCESSED.read_text("utf-8")):
            for source in row["sources"]:
                self.assertEqual(source["license"], m.LICENCE)

    def test_it_is_the_string_the_files_actually_carry(self):
        for path in sorted(RAW.glob(m.FILE_GLOB)):
            _, stated = m.read_file(path)
            self.assertEqual(stated, m.LICENCE, path.name)

    def test_a_file_that_does_not_state_it_is_not_read(self):
        text = csv_text(province_rows()).replace(m.LICENCE, "All rights reserved")
        with tempfile.TemporaryDirectory() as folder:
            where = Path(folder)
            (where / "Language_Distribution_X_20260921.csv").write_text(
                text, encoding="utf-8")
            (where / m.CITATIONS).write_text(json.dumps(CITATION), encoding="utf-8")
            log = io.StringIO()
            with redirect_stderr(log):
                records, _ = m.build(where)
        self.assertEqual(records, [])
        self.assertIn("does not carry the licence", log.getvalue())


class TheCoverageThreshold(unittest.TestCase):
    def test_a_unit_the_settlements_barely_reach_is_a_gap_with_a_reason(self):
        rows = province_rows()
        rows[0] = line(ALI_unique_ID_place="1120000", province_roman="Kordestān",
                       population_2011_census="100000")
        records, tally, log = build(rows)
        self.assertEqual([r for r in records if r["level"] == "admin1"], [])
        self.assertIn("Kurdistan", [name for name, _ in tally["gaps"]])
        self.assertIn("1.0% of the province's 100,000 people", log)

    def test_kermanshah_is_that_case_in_the_committed_file(self):
        """Its module covers five of fourteen counties and 18.6% of the people.

        The five counties are written and the province is not: a figure for
        Kermanshah province built on a fifth of it would be a statement about
        Kermanshah city, which the module does not reach at all.
        """
        rows = json.loads(PROCESSED.read_text("utf-8"))
        names = {r["name"] for r in rows if r["level"] == "admin1"}
        self.assertNotIn("Kermanshah", names)
        counties = {r["name"] for r in rows
                    if r.get("parent_name") == "Kermanshah"}
        self.assertEqual(len(counties), 5)

    def test_rasht_is_the_same_case_one_level_down(self):
        rows = json.loads(PROCESSED.read_text("utf-8"))
        self.assertNotIn("Rasht", {r["name"] for r in rows})
        gilan = [r for r in rows if r["name"] == "Gilan"][0]
        self.assertIn("Rasht (679,995 people)", gilan["language"]["note"])


class WhatWasWritten(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads(PROCESSED.read_text("utf-8"))

    def test_eleven_provinces_and_ninety_six_counties(self):
        levels = [r["level"] for r in self.rows]
        self.assertEqual(levels.count("admin1"), 11)
        self.assertEqual(levels.count("admin2"), 96)

    def test_every_record_is_an_estimate_and_never_a_composition(self):
        for row in self.rows:
            self.assertIn(row["language"]["status"], ("modelled", "derived"))
            self.assertNotIsInstance(row["language"], list)
            # A year beside a gap would fall through merge_adapter onto
            # somebody else's figures, so it travels inside the estimate.
            self.assertNotIn("language_year", row)

    def test_no_record_claims_a_census_asked(self):
        for row in self.rows:
            note = row["language"]["note"]
            self.assertIn("not a census", note)
            self.assertIn("Iran's census does not ask language", note)

    def test_each_province_carries_its_own_modules_year(self):
        """Twelve modules, 2015 to 2024. One date over the twelve would say
        that Hormozgān and Khuzestān were looked at together."""
        years = {r["name"]: r["language"]["year"]
                 for r in self.rows if r["level"] == "admin1"}
        self.assertEqual(years["Hormozgan"], 2015)
        self.assertEqual(years["Kurdistan"], 2016)
        self.assertEqual(years["Khuzestan"], 2024)
        self.assertEqual(years["Kohgiluyeh and Boyer-Ahmad"], 2024)
        self.assertGreater(len(set(years.values())), 4)

    def test_a_county_carries_the_year_of_the_province_it_is_in(self):
        for row in self.rows:
            if row["level"] != "admin2":
                continue
            parent = [r for r in self.rows
                      if r["level"] == "admin1"
                      and r["name"] == row["parent_name"]]
            if parent:
                self.assertEqual(row["language"]["year"],
                                 parent[0]["language"]["year"], row["name"])

    def test_the_fieldwork_is_named_beside_the_module(self):
        kurdistan = [r for r in self.rows if r["name"] == "Kurdistan"][0]
        note = kurdistan["language"]["note"]
        self.assertIn("Mohammadirad, Masoud, Erik Anonby, et al. (2016)", note)
        self.assertIn("field notes 2015", note)

    def test_a_module_published_long_after_its_fieldwork_says_so(self):
        """Kermānshāh's module is 2022 and every row in it cites 2017."""
        dalahu = [r for r in self.rows if r["name"] == "Dalahu"][0]
        self.assertIn("The module is dated 2022", dalahu["language"]["note"])
        self.assertIn("field notes of 2017", dalahu["language"]["note"])

    def test_the_three_files_with_no_county_names_produce_no_counties(self):
        """Khuzestān, Lorestān and Kohgiluyeh va Boyer Ahmad leave every column
        below the province blank, so their settlements cannot be placed in a
        county. A county record from them would be invented."""
        for province in ("Khuzestan", "Lorestan", "Kohgiluyeh and Boyer-Ahmad"):
            self.assertIn(province,
                          {r["name"] for r in self.rows if r["level"] == "admin1"})
            self.assertEqual([], [r["name"] for r in self.rows
                                  if r.get("parent_name") == province])

    def test_every_county_names_the_province_it_is_in(self):
        """match_admin2 scopes a district row to the admin-1 it names, and
        Iran has a Gilan-e-Gharb in Kermanshah and a Gilan province."""
        for row in self.rows:
            if row["level"] == "admin2":
                self.assertTrue(row.get("parent_name"), row["name"])


class AgainstTheWorld(unittest.TestCase):
    """If these fail, the reader is wrong -- not the world."""

    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads(PROCESSED.read_text("utf-8"))

    def shares(self, name):
        row = [r for r in self.rows if r["name"] == name][0]
        return {s["group"]: s["pct"] for s in row["language"]["estimate"]}

    def test_kordestan_is_overwhelmingly_central_kurdish(self):
        shares = self.shares("Kurdistan")
        self.assertGreater(shares["Central Kurdish"], 70.0)
        self.assertGreater(shares["Hōrāmi"], 1.0)
        self.assertGreater(shares["Southern Kurdish"], 1.0)
        self.assertGreater(shares["Turkic"], 1.0)

    def test_khuzestan_carries_a_large_arabic_speaking_population(self):
        shares = self.shares("Khuzestan")
        self.assertGreater(shares["Khuzestāni Arabic"], 25.0)
        self.assertGreater(shares["Bakhtiāri"], 10.0)
        self.assertGreater(shares["Standard type Persian"], 10.0)

    def test_gilan_is_the_atlass_own_reading_and_not_a_tidied_one(self):
        """ALI's Gilān module puts Standard type Persian ahead of Gilaki in
        almost every settlement -- 60% against 40% in the villages, 50% to 70%
        in the towns. That is what its authors recorded, and this map prints
        it rather than the expectation it contradicts; the Gilaki varieties
        are still the largest thing after it.
        """
        shares = self.shares("Gilan")
        gilaki = sum(pct for group, pct in shares.items() if "Gilaki" in group)
        self.assertGreater(shares["Standard type Persian"], 50.0)
        self.assertGreater(gilaki, 20.0)

    def test_every_composition_is_a_partition(self):
        for row in self.rows:
            total = sum(s["pct"] for s in row["language"]["estimate"])
            self.assertAlmostEqual(total, 100.0, delta=m.SUM_TOLERANCE,
                                   msg=f"{row['name']} adds to {total}")


class ItIsRegistered(unittest.TestCase):
    def test_the_build_reads_the_file(self):
        self.assertIn("iran_ali_language.json", be.ADAPTER_FILES)

    def test_it_sits_below_every_census_file_and_above_none_of_them(self):
        """It is a research atlas, so it belongs among the models and surveys.
        Nothing else in the list writes an Iranian unit, so the position
        cannot overwrite anybody: it is a statement of kind."""
        files = be.ADAPTER_FILES
        self.assertLess(files.index("iran_ali_language.json"),
                        files.index("india_state.json"))
        self.assertGreater(files.index("iran_ali_language.json"),
                           files.index("clear_global_language.json"))

    def test_iran_keeps_a_reason_rather_than_a_command(self):
        """Nineteen provinces have no module yet, and a reader clicking one is
        owed the reason. ADAPTER_GAPS is prose and must stay prose."""
        reason = be.ADAPTER_GAPS["IRN"]
        self.assertNotIn("python", reason)
        self.assertNotIn("scripts.", reason)
        self.assertIn("Atlas of the Languages of Iran", reason)
        self.assertIn("twelve of the thirty-one", reason)
        self.assertNotIn("IRN", be.ADAPTER_HINTS)

    def test_language_is_not_in_the_policy_table_but_the_fact_still_is(self):
        """The fact and the table mean different things, and only one moved.

        NOT_COLLECTED_POLICY does not say "the census does not ask" -- it says
        *no value may ever be written here*, and
        check_no_estimate_on_policy_field makes that fatal. A language entry
        for Iran therefore refused the atlas outright, which is why it is gone
        (owner's decision, 20 September 2026). What must not go with it is the
        fact itself: Iran's census really does not ask language, and a reader
        who is shown a figure is owed that. So this pins both halves -- the
        table is silent, and every record still says it.
        """
        import common
        self.assertNotIn("language", common.NOT_COLLECTED_POLICY["IRN"])
        # Ethnicity is untouched: nobody has measured it independently, so
        # the stronger declaration is still the right one there.
        self.assertIn("ethnicity", common.NOT_COLLECTED_POLICY["IRN"])
        self.assertIn("no Iranian census has ever asked it",
                      be.ADAPTER_GAPS["IRN"])
        records = json.loads(PROCESSED.read_text())
        self.assertTrue(records)
        for record in records:
            with self.subTest(unit=record["name"]):
                self.assertIn("Iran's census does not ask language",
                              record["language"]["note"])


class TheSourceFilesAreCommitted(unittest.TestCase):
    """data/raw has silently un-tracked a source before now.

    There is no host to re-fetch these from: they were exported by hand from
    the atlas's own site, and without them the adapter reads nothing.
    """

    def test_twelve_province_files_and_their_citations(self):
        files = sorted(RAW.glob(m.FILE_GLOB))
        self.assertEqual(len(files), 12)
        self.assertTrue((RAW / m.CITATIONS).exists())

    def test_every_file_is_cited(self):
        cited = m.citations(RAW)
        for path in sorted(RAW.glob(m.FILE_GLOB)):
            rows, _ = m.read_file(path)
            roman, _ = m.province_of(rows)
            self.assertIn(roman, cited, path.name)

    def test_a_province_with_no_citation_is_not_written(self):
        records, _, log = build(province_rows(), citation={"provinces": []})
        self.assertEqual(records, [])
        self.assertIn("carries no citation", log)


if __name__ == "__main__":
    unittest.main()


class EveryLabelHasAFamily(unittest.TestCase):
    """A variety with no family renders in the "not yet classified" colour.

    This is not caught by ``check_classified``: that walks site/data and its
    ``leader`` skips an estimate-shaped value, so a whole country of modelled
    compositions is invisible to it. Iran was invisible that way -- correct
    on the map and grey on it -- until the atlas's labels were placed.
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import group_tree
        cls.gt = group_tree
        cls.labels = sorted({
            share["group"]
            for record in json.loads(PROCESSED.read_text())
            for share in record["language"]["estimate"]})

    def test_every_label_the_adapter_writes_carries_a_hue(self):
        unplaced = [name for name in self.labels
                    if not self.gt.hue("language", name)]
        self.assertEqual(
            unplaced, [],
            f"{len(unplaced)} of {len(self.labels)} ALI labels have no family "
            f"and would render unclassified")

    def test_the_varieties_land_under_Iranian_and_not_somewhere_convenient(self):
        # A label placed in the wrong family is worse than one left out: it
        # would colour a Kurdish county as though it spoke something else.
        for name in ("Kalhuri", "Hōrāmi", "Bakhtiāri", "Northern Lori",
                     "Dashtesuni", "Banderi of Bandar Abbās", "Laki",
                     "Central Tāleshi", "Boyerahmadi"):
            with self.subTest(name=name):
                self.assertIn("Iranian languages",
                              self.gt.ancestry("language", name))

    def test_the_four_that_are_not_Iranian_are_not_filed_as_Iranian(self):
        # Ghashghāi is Turkic and Kholosi Indo-Aryan, both spoken inside the
        # atlas's Iranian survey area; "mixed" and "unknown" are answers.
        self.assertIn("Turkic languages", self.gt.ancestry("language", "Ghashghāi"))
        self.assertIn("Indo-Aryan languages", self.gt.ancestry("language", "Kholosi"))
        for name in ("mixed", "unknown"):
            with self.subTest(name=name):
                trail = self.gt.ancestry("language", name)
                self.assertIn("Unclassified language answers", trail)
                self.assertNotIn("Iranian languages", trail)
