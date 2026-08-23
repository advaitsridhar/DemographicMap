"""Tests for the join logic in scripts/build_entities.py.

These cover the two bugs that produced wrong *data* rather than a crash: a
dependency overwriting its parent country, and a curated row matching the wrong
shape.
"""

import collections
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_entities as be  # noqa: E402
import common  # noqa: E402

sys.path.insert(0, str(ROOT))


class Normalisation(unittest.TestCase):
    def test_strips_generic_administrative_words(self):
        self.assertEqual(be.norm("Tibet Autonomous Region"), be.norm("Tibet"))
        self.assertEqual(be.norm("Harris County"), be.norm("Harris"))

    def test_strips_diacritics(self):
        self.assertEqual(be.norm("Mahārāshtra"), be.norm("Maharashtra"))

    def test_distinct_names_stay_distinct(self):
        self.assertNotEqual(be.norm("Punjab"), be.norm("Haryana"))


class CuratedMatching(unittest.TestCase):
    def setUp(self):
        self.lookup = {
            be.norm("Tibet Autonomous Region"): {"name": "Tibet Autonomous Region"},
            be.norm("Xinjiang Uyghur Autonomous Region"): {"name": "Xinjiang Uyghur Autonomous Region"},
            be.norm("ARMM"): {"name": "ARMM"},
            be.norm("Kerala"): {"name": "Kerala"},
        }

    def test_exact_name(self):
        entity, how = be.match_name({"name": "Kerala"}, self.lookup)
        self.assertEqual(entity["name"], "Kerala")
        self.assertEqual(how, "name")

    def test_alias(self):
        row = {"name": "Bangsamoro Autonomous Region in Muslim Mindanao", "aliases": ["ARMM"]}
        entity, how = be.match_name(row, self.lookup)
        self.assertEqual(entity["name"], "ARMM")
        self.assertEqual(how, "alias")

    def test_unique_prefix(self):
        entity, how = be.match_name({"name": "Xinjiang"}, self.lookup)
        self.assertEqual(entity["name"], "Xinjiang Uyghur Autonomous Region")
        self.assertEqual(how, "prefix")

    def test_ambiguous_prefix_refuses_to_guess(self):
        lookup = {be.norm("Amazonas Norte"): {}, be.norm("Amazonas Sul"): {}}
        entity, how = be.match_name({"name": "Amazonas"}, lookup)
        self.assertIsNone(entity)
        self.assertEqual(how, "unmatched")

    def test_unknown_name_is_unmatched(self):
        entity, how = be.match_name({"name": "Atlantis"}, self.lookup)
        self.assertIsNone(entity)
        self.assertEqual(how, "unmatched")


class AdapterMerge(unittest.TestCase):
    def test_a_gap_never_overwrites_a_value(self):
        entity = {"population": common.measure(100, year=2020, source="census")}
        be.merge_adapter(entity, {"population": common.gap(common.NOT_AVAILABLE)})
        self.assertEqual(entity["population"]["value"], 100)

    def test_a_value_overwrites_a_gap(self):
        entity = {"population": common.gap(common.NOT_AVAILABLE)}
        be.merge_adapter(entity, {"population": common.measure(100)})
        self.assertEqual(entity["population"]["value"], 100)

    def test_identity_fields_are_not_overwritten(self):
        entity = {"id": "shape-1", "name": "Kerala", "level": "admin1", "parent": "IND"}
        be.merge_adapter(entity, {"id": "other", "name": "KERALA", "parent": "XXX"})
        self.assertEqual(entity["id"], "shape-1")
        self.assertEqual(entity["name"], "Kerala")
        self.assertEqual(entity["parent"], "IND")

    def test_sources_accumulate(self):
        entity = {"sources": [{"name": "a"}]}
        be.merge_adapter(entity, {"sources": [{"name": "b"}]})
        self.assertEqual([s["name"] for s in entity["sources"]], ["a", "b"])


class FieldState(unittest.TestCase):
    def test_states(self):
        self.assertEqual(be.field_state([{"group": "a", "pct": 1}]), "present")
        self.assertEqual(be.field_state([]), common.NOT_AVAILABLE)
        self.assertEqual(be.field_state(None), common.NOT_AVAILABLE)
        self.assertEqual(be.field_state(common.gap(common.NOT_COLLECTED, "x")),
                         common.NOT_COLLECTED)
        self.assertEqual(be.field_state(common.measure(5)), "present")


class AdapterHints(unittest.TestCase):
    def test_known_country_gets_its_own_adapter(self):
        self.assertIn("us_acs", be.adapter_hint("USA"))
        self.assertIn("ibge_sidra", be.adapter_hint("BRA"))

    def test_eu_country_falls_back_to_eurostat(self):
        self.assertIn("eurostat", be.adapter_hint("PRT"))

    def test_everything_else_falls_back_to_wikidata(self):
        hint = be.adapter_hint("MNG")
        self.assertIn("fetch_wikidata", hint)
        self.assertIn("MNG", hint)


class CuratedSeed(unittest.TestCase):
    """The curated file is data, so guard its shape the way an adapter is guarded."""

    def test_every_row_names_a_country_with_provenance(self):
        payload = common.read_json(ROOT / "data" / "curated" / "admin1_seed.json", {})
        provenance = payload.get("_provenance", {})
        self.assertTrue(payload.get("rows"))
        for row in payload["rows"]:
            self.assertIn("country", row, row)
            self.assertIn("name", row, row)
            self.assertIn(row["country"], provenance,
                          f"{row['country']} has no _provenance entry")
            self.assertIn("source", provenance[row["country"]])
            self.assertIn("year", provenance[row["country"]])

    def test_composition_shares_are_plausible(self):
        payload = common.read_json(ROOT / "data" / "curated" / "admin1_seed.json", {})
        for row in payload["rows"]:
            for field in ("religion", "language", "ethnicity"):
                for share in row.get(field, []):
                    self.assertIn("group", share)
                    self.assertGreaterEqual(share["pct"], 0)
                    self.assertLessEqual(share["pct"], 100)
                total = sum(s["pct"] for s in row.get(field, []))
                self.assertLessEqual(total, 101.0, f"{row['name']} {field} sums to {total}")


if __name__ == "__main__":
    unittest.main()


class ContainmentMatching(unittest.TestCase):
    """The pass added after the first live run: unique substring containment."""

    def test_official_long_form_matches_short_shape_name(self):
        lookup = {be.norm("Zurich"): {"name": "Zurich"},
                  be.norm("Bern"): {"name": "Bern"}}
        entity, how = be.match_name({"name": "Canton of Zurich"}, lookup)
        self.assertEqual(entity["name"], "Zurich")
        self.assertEqual(how, "contains")

    def test_suffixed_source_name(self):
        lookup = {be.norm("Stockholm"): {"name": "Stockholm"},
                  be.norm("Uppsala"): {"name": "Uppsala"}}
        entity, how = be.match_name({"name": "Stockholms lan"}, lookup)
        self.assertEqual(entity["name"], "Stockholm")

    def test_ambiguous_containment_refuses(self):
        lookup = {be.norm("Northern"): {}, be.norm("Northern Cape"): {}}
        entity, how = be.match_name({"name": "North"}, lookup)
        self.assertIsNone(entity)

    def test_short_keys_never_containment_match(self):
        # "Oued Fes" contains "fes" mid-string (so the prefix pass cannot fire),
        # but a 3-character key is too little evidence for containment.
        lookup = {be.norm("Fes"): {"name": "Fes"}}
        entity, how = be.match_name({"name": "Oued Fes"}, lookup)
        self.assertIsNone(entity)


class CollectionPolicyPropagation(unittest.TestCase):
    """A country that does not collect a field does not collect it in its regions."""

    def test_not_available_becomes_not_collected(self):
        entity = {"ethnicity": common.gap(common.NOT_AVAILABLE)}
        applied = common.apply_collection_policy(entity, "IND")
        self.assertEqual(applied, ["ethnicity"])
        self.assertEqual(entity["ethnicity"]["status"], common.NOT_COLLECTED)
        self.assertIn("Scheduled Caste", entity["ethnicity"]["note"])

    def test_a_real_value_is_never_overwritten(self):
        # A region may publish what its national census declines to ask.
        shares = [{"group": "Some group", "pct": 42.0}]
        entity = {"ethnicity": shares}
        self.assertEqual(common.apply_collection_policy(entity, "IND"), [])
        self.assertEqual(entity["ethnicity"], shares)

    def test_untouched_fields_stay_untouched(self):
        # India collects religion; only ethnicity carries a policy.
        entity = {"religion": common.gap(common.NOT_AVAILABLE),
                  "ethnicity": common.gap(common.NOT_AVAILABLE)}
        common.apply_collection_policy(entity, "IND")
        self.assertEqual(entity["religion"]["status"], common.NOT_AVAILABLE)
        self.assertEqual(entity["ethnicity"]["status"], common.NOT_COLLECTED)

    def test_country_without_a_policy_is_a_no_op(self):
        entity = {"ethnicity": common.gap(common.NOT_AVAILABLE)}
        self.assertEqual(common.apply_collection_policy(entity, "BRA"), [])

    def test_unknown_country_is_a_no_op(self):
        entity = {"ethnicity": common.gap(common.NOT_AVAILABLE)}
        self.assertEqual(common.apply_collection_policy(entity, None), [])

    def test_every_policy_entry_carries_a_reason(self):
        for iso3, fields in common.NOT_COLLECTED_POLICY.items():
            self.assertRegex(iso3, r"^[A-Z]{3}$")
            for field, reason in fields.items():
                self.assertIn(field, ("religion", "ethnicity", "language"))
                self.assertGreater(len(reason), 30, f"{iso3}/{field} reason is too thin")


class AbsDimensionDetection(unittest.TestCase):
    """The ABS names its dimensions differently per dataflow, so they are found,
    not assumed -- the first live run returned every LGA with no data attached
    because the characteristic dimension was being looked up under a guess."""

    def setUp(self):
        from fetch_census import abs as abs_adapter
        self.abs = abs_adapter
        self.rows = [
            ({"REGION": "Albury", "REGION_CODE": "10050",
              "RELIGP": "Catholic", "TIME_PERIOD": "2021"}, 5.0),
            ({"REGION": "Albury", "REGION_CODE": "10050",
              "RELIGP": "No religion", "TIME_PERIOD": "2021"}, 7.0),
            ({"REGION": "Bland", "REGION_CODE": "10250",
              "RELIGP": "Anglican", "TIME_PERIOD": "2021"}, 3.0),
        ]

    def test_finds_the_characteristic_dimension_by_hint(self):
        self.assertEqual(self.abs.pick_dimension(self.rows, "religion"), "RELIGP")

    def test_finds_the_region_dimension(self):
        self.assertEqual(self.abs.pick_region_dimension(self.rows), "REGION")

    def test_falls_back_to_the_widest_non_region_dimension(self):
        rows = [({"ASGS_2021": "Albury", "ASGS_2021_CODE": "1", "XYZ": "Catholic"}, 5.0),
                ({"ASGS_2021": "Albury", "ASGS_2021_CODE": "1", "XYZ": "Buddhism"}, 2.0)]
        self.assertEqual(self.abs.pick_dimension(rows, "religion"), "XYZ")

    def test_never_picks_region_or_time_as_the_characteristic(self):
        rows = [({"REGION": "Albury", "TIME_PERIOD": "2021"}, 1.0),
                ({"REGION": "Bland", "TIME_PERIOD": "2021"}, 2.0)]
        self.assertIsNone(self.abs.pick_dimension(rows, "religion"))

    def test_grouping_sums_by_region(self):
        grouped = self.abs.group_by_region(self.rows, "RELIGP", "REGION")
        self.assertEqual(grouped["10050"], {"Catholic": 5.0, "No religion": 7.0})
        self.assertEqual(grouped["10250"], {"Anglican": 3.0})


class IndiaCensusValidation(unittest.TestCase):
    """The India extract is a community redistribution, so it is checked against
    the Registrar General's published totals before any of it is used."""

    def setUp(self):
        from fetch_census import india_census
        self.india = india_census

    def _rows(self, n=640, population=1_210_854_977):
        # One synthetic district carrying the national totals, padded to count.
        head = {"District name": "Test", "State name": "TEST", "District code": "1",
                "Population": str(population), "Male": "620000000", "Female": "590000000",
                "Hindus": str(int(population * 0.7980)),
                "Muslims": str(int(population * 0.1423)),
                "Christians": str(int(population * 0.0230)),
                "Sikhs": str(int(population * 0.0172)),
                "Buddhists": str(int(population * 0.0070)),
                "Jains": str(int(population * 0.0037)),
                "Others_Religions": "0", "Religion_Not_Stated": "0", "SC": "0", "ST": "0"}
        pad = dict(head, Population="0", Hindus="0", Muslims="0", Christians="0",
                   Sikhs="0", Buddhists="0", Jains="0", Male="0", Female="0")
        return [head] + [dict(pad) for _ in range(n - 1)]

    def test_accepts_an_extract_matching_the_published_totals(self):
        self.india.validate(self._rows())  # must not raise

    def test_rejects_a_wrong_population(self):
        with self.assertRaises(SystemExit) as ctx:
            self.india.validate(self._rows(population=1_000_000_000))
        self.assertIn("population", str(ctx.exception))

    def test_rejects_a_wrong_district_count(self):
        with self.assertRaises(SystemExit) as ctx:
            self.india.validate(self._rows(n=600))
        self.assertIn("600 districts", str(ctx.exception))

    def test_rejects_drifted_religion_shares(self):
        rows = self._rows()
        rows[0]["Hindus"] = str(int(1_210_854_977 * 0.50))
        with self.assertRaises(SystemExit) as ctx:
            self.india.validate(rows)
        self.assertIn("Hindus", str(ctx.exception))

    def test_subdivided_districts_are_never_given_invented_figures(self):
        for parent, successors in self.india.SUBDIVIDED_SINCE_2011.items():
            self.assertGreater(len(successors), 1, parent)

    def test_post_2011_states_carry_a_reason(self):
        for name, reason in self.india.FORMED_AFTER_2011.items():
            self.assertGreater(len(reason), 80, name)
            self.assertIn("2011 census", reason)


class AbsHierarchyCollapse(unittest.TestCase):
    """ABS classifications nest: summing a parent and its children counts every
    person twice and halves every share. Albury came out 25.4% Christian in the
    first populated run; the real figure is about 50%."""

    def setUp(self):
        from fetch_census import abs as abs_adapter
        self.abs = abs_adapter
        self.albury = {
            "Christianity Total": 53856, "Catholic": 24671, "Anglican": 14166,
            "Uniting Church": 3446,
            "Secular Other Spiritual and No Religious Affiliation Total": 44444,
            "No Religion, so described": 44059,
            "Religious affiliation not stated": 7948, "Total": 106248,
        }

    def test_keeps_only_the_top_level(self):
        out = self.abs.collapse_hierarchy(self.albury)
        self.assertIn("Christianity", out)
        for child in ("Catholic", "Anglican", "Uniting Church", "No Religion, so described"):
            self.assertNotIn(child, out)

    def test_drops_the_grand_total(self):
        self.assertNotIn("Total", self.abs.collapse_hierarchy(self.albury))

    def test_shares_sum_to_one_hundred(self):
        out = self.abs.collapse_hierarchy(self.albury)
        total = sum(out.values())
        self.assertAlmostEqual(sum(100 * v / total for v in out.values()), 100.0, places=6)

    def test_christianity_is_about_half(self):
        out = self.abs.collapse_hierarchy(self.albury)
        total = sum(out.values())
        self.assertGreater(100 * out["Christianity"] / total, 45)

    def test_keeps_not_stated_beside_the_totals(self):
        self.assertIn("Religious affiliation not stated",
                      self.abs.collapse_hierarchy(self.albury))

    def test_a_flat_classification_is_untouched(self):
        # Ancestry has no hierarchy, so nothing may be dropped.
        flat = {"English": 44455, "Australian": 42905, "Irish": 14000}
        self.assertEqual(self.abs.collapse_hierarchy(flat), flat)

    def test_sex_dimension_is_restricted_to_persons(self):
        rows = [({"REGION": "A", "SEXP": "Persons", "RELP": "Christianity Total"}, 10.0),
                ({"REGION": "A", "SEXP": "Males", "RELP": "Christianity Total"}, 4.0),
                ({"REGION": "A", "SEXP": "Females", "RELP": "Christianity Total"}, 6.0)]
        self.assertEqual(self.abs.sole_sex_dimension(rows), ("SEXP", "Persons"))
        grouped = self.abs.group_by_region(rows, "RELP", "REGION")
        self.assertEqual(grouped["A"]["Christianity"], 10.0)

    def test_no_sex_dimension_is_harmless(self):
        rows = [({"REGION": "A", "RELP": "Christianity Total"}, 10.0)]
        self.assertIsNone(self.abs.sole_sex_dimension(rows))
        self.assertEqual(self.abs.group_by_region(rows, "RELP", "REGION")["A"],
                         {"Christianity": 10.0})


class C16MotherTongue(unittest.TestCase):
    """India's C-16 workbooks: hierarchy, geography and the published controls."""

    def setUp(self):
        from scripts.fetch_census import india_language as il
        self.il = il

    def test_group_labels_lose_their_index(self):
        self.assertEqual(self.il.clean_group("6 HINDI"), "Hindi")
        self.assertEqual(self.il.clean_group("22 URDU"), "Urdu")
        self.assertEqual(self.il.clean_group("14 BHILI/BHILODI"), "Bhili/Bhilodi")

    def test_the_census_residual_is_not_our_trimmed_tail(self):
        # C-16 has an "OTHERS" group of its own, and in Zunheboto it is 95.6% of
        # the district with no breakdown published beneath it. Calling that
        # "other small languages" would describe a long tail of minor tongues --
        # the opposite of what it is.
        self.assertEqual(self.il.clean_group("124 OTHERS"), self.il.CENSUS_RESIDUAL)
        self.assertNotEqual(self.il.CENSUS_RESIDUAL, self.il.REMAINDER)

    def test_a_dominant_census_residual_survives_trimming(self):
        counts = collections.Counter({f"L{i}": 1 for i in range(40)})
        counts[self.il.CENSUS_RESIDUAL] = 9_960
        rows = self.il.composition(counts)
        top = rows[0]
        self.assertEqual(top["group"], self.il.CENSUS_RESIDUAL)
        self.assertGreater(top["pct"], 99.0)

    def test_the_note_says_which_kind_of_other_it_is(self):
        rows = [{"group": self.il.CENSUS_RESIDUAL, "pct": 95.6, "count": 1},
                {"group": self.il.REMAINDER, "pct": 4.4, "count": 1}]
        note = self.il.language_note(rows, 60)
        self.assertIn("catch-all", note)
        self.assertIn("summed into", note)

    def test_tail_is_summed_not_dropped(self):
        counts = collections.Counter({f"L{i}": 1 for i in range(40)})
        counts["Hindi"] = 9_960
        rows = self.il.composition(counts)
        self.assertLessEqual(len(rows), self.il.MAX_GROUPS + 1)
        self.assertEqual(sum(r["count"] for r in rows), sum(counts.values()))
        self.assertIn(self.il.REMAINDER, [r["group"] for r in rows])

    def test_hierarchy_check_catches_a_doubled_unit(self):
        # The bug this check exists for: every state's row appears in both the
        # all-India workbook and its own, so accumulating instead of assigning
        # doubles it -- and the shares still add to 100%.
        units = {("09", "000"): {"name": "UTTAR PRADESH",
                                 "counts": collections.Counter({"Hindi": 200})}}
        with self.assertRaises(SystemExit) as caught:
            self.il.check_levels(units, {("09", "000"): 100})
        self.assertIn("2.00x", str(caught.exception))

    def test_hierarchy_check_passes_when_the_levels_agree(self):
        units = {("09", "000"): {"name": "UTTAR PRADESH",
                                 "counts": collections.Counter({"Hindi": 100})}}
        self.il.check_levels(units, {("09", "000"): 100})

    def test_refuses_a_workbook_that_misses_the_published_totals(self):
        counts = collections.Counter(self.il.NATIONAL_CONTROLS)
        del counts["_total"]
        counts["Hindi"] -= 1_000_000          # a mirror that has drifted
        with self.assertRaises(SystemExit) as caught:
            self.il.validate({("00", "000"): {"name": "INDIA", "counts": counts}})
        self.assertIn("Hindi", str(caught.exception))


class Admin2Disambiguation(unittest.TestCase):
    """Two shapes, one name: the row must land on the right one or on neither."""

    def shapes(self):
        return {
            be.norm("Hamirpur"): [
                {"id": "HP-HAM", "name": "Hamirpur", "parent": "S-HP"},
                {"id": "UP-HAM", "name": "Hamirpur", "parent": "S-UP"},
            ],
            be.norm("Agra"): [{"id": "UP-AGR", "name": "Agra", "parent": "S-UP"}],
        }

    def admin1(self):
        # Keyed the way build_entities keys the real lookup, so the fixture
        # cannot pass under a normalisation the pipeline does not use.
        return {be.norm(name): {"id": eid, "name": name} for eid, name in
                (("S-HP", "Himachal Pradesh"), ("S-UP", "Uttar Pradesh"))}

    def test_the_state_picks_the_right_twin(self):
        entity, how = be.match_admin2(
            {"name": "Hamirpur", "parent_name": "Himachal Pradesh"},
            self.shapes(), self.admin1())
        self.assertEqual(entity["id"], "HP-HAM")
        self.assertIn("state", how)

    def test_the_other_twin_is_reachable_too(self):
        entity, _ = be.match_admin2(
            {"name": "Hamirpur", "parent_name": "Uttar Pradesh"},
            self.shapes(), self.admin1())
        self.assertEqual(entity["id"], "UP-HAM")

    def test_an_ambiguous_name_with_no_state_is_refused(self):
        # Silently keeping whichever shape was seen last is how a district ends
        # up wearing its namesake's figures. An unmatched row is visible; a
        # mis-matched one is not.
        entity, how = be.match_admin2(
            {"name": "Hamirpur", "parent_name": None}, self.shapes(), self.admin1())
        self.assertIsNone(entity)
        self.assertEqual(how, "ambiguous")

    def test_unique_names_still_match_without_a_state(self):
        entity, _ = be.match_admin2(
            {"name": "Agra", "parent_name": None}, self.shapes(), self.admin1())
        self.assertEqual(entity["id"], "UP-AGR")

    def test_an_unresolvable_state_falls_back_rather_than_failing(self):
        entity, _ = be.match_admin2(
            {"name": "Agra", "parent_name": "Atlantis"}, self.shapes(), self.admin1())
        self.assertEqual(entity["id"], "UP-AGR")


class SriLanka2024(unittest.TestCase):
    """The 2024 census workbooks: trilingual labels, and the source's own check."""

    def setUp(self):
        from scripts.fetch_census import sri_lanka as lk
        self.lk = lk

    def test_english_is_the_ascii_half_of_a_trilingual_cell(self):
        self.assertEqual(self.lk.english("නුවරඑළිය நுவெரலியா Nuwara Eliya"), "Nuwara Eliya")
        self.assertEqual(self.lk.english("කොළඹ கொழும்பு Colombo"), "Colombo")

    def test_published_shares_catch_a_column_read_off_by_one(self):
        # A row read one cell to the left still sums to 100%, so only the
        # Department's own printed percentages can catch it.
        labels = ["Buddhist", "Hindu"]
        printed = [None, None, 70.0, 30.0]
        shifted = {"Buddhist": 30.0, "Hindu": 70.0}      # the two swapped
        drift = self.lk.check_published_shares("Kandy", shifted, 100.0, printed, labels, {})
        self.assertEqual(len(drift), 2)
        self.assertIn("Kandy", drift[0])

    def test_published_shares_accept_agreeing_figures(self):
        labels = ["Buddhist", "Hindu"]
        printed = [None, None, 70.0, 30.0]
        counts = {"Buddhist": 70.0, "Hindu": 30.0}
        self.assertEqual(
            self.lk.check_published_shares("Kandy", counts, 100.0, printed, labels, {}), [])

    def test_the_rename_map_is_applied_on_both_sides(self):
        # The counts are keyed by display name and the printed row by the
        # Department's spelling; checking one against the other without the
        # rename reported every share as 0%.
        labels = ["Sinhalees"]
        printed = [None, None, 74.1]
        counts = {"Sinhalese": 74.1}
        self.assertEqual(
            self.lk.check_published_shares("Sri Lanka", counts, 100.0, printed,
                                           labels, self.lk.ETHNIC_LABELS), [])

    def test_every_district_belongs_to_exactly_one_province(self):
        members = [d for ds in self.lk.PROVINCES.values() for d in ds]
        self.assertEqual(len(members), 25)
        self.assertEqual(len(set(members)), 25)

    def test_refuses_workbooks_that_miss_the_published_totals(self):
        country = {"population": self.lk.NATIONAL_CONTROLS["_total"],
                   "religion": {k: v for k, v in self.lk.NATIONAL_CONTROLS.items()
                                if k != "_total"},
                   "ethnicity": {}}
        country["religion"]["Buddhist"] -= 5_000
        with self.assertRaises(SystemExit) as caught:
            self.lk.validate({"Sri Lanka": country})
        self.assertIn("Buddhist", str(caught.exception))


class SingaporeGroupedMedian(unittest.TestCase):
    """The one derived figure in the Singapore adapter, and the series parsing."""

    def setUp(self):
        from scripts.fetch_census import singstat
        self.ss = singstat

    def test_median_lands_inside_the_band_holding_the_midpoint(self):
        bands = {"0 - 4 Years": 100, "5 - 9 Years": 100, "10 - 14 Years": 100}
        # 300 people, midpoint at 150, which falls halfway through the 5-9 band.
        self.assertEqual(self.ss.median_from_bands(bands), 7.5)

    def test_a_single_band_interpolates_to_its_middle(self):
        self.assertEqual(self.ss.median_from_bands({"40 - 44 Years": 1000}), 42.5)

    def test_the_open_ended_band_is_given_a_nominal_width(self):
        # "90 Years & Over" has no upper bound; it is treated as five years wide
        # rather than being dropped, which would bias the median downwards.
        self.assertIsNotNone(self.ss.median_from_bands({"90 Years & Over": 10}))

    def test_empty_or_unparseable_bands_yield_nothing_rather_than_a_guess(self):
        self.assertIsNone(self.ss.median_from_bands({}))
        self.assertIsNone(self.ss.median_from_bands({"All ages": 500}))
        self.assertIsNone(self.ss.median_from_bands({"0 - 4 Years": 0}))

    def test_age_bands_attach_to_the_region_not_to_a_sex_split(self):
        # Bands hang off whichever top-level series precedes them. Letting the
        # "(Male)" series claim them would halve every count behind the median.
        payload = {"Data": {"row": [
            {"seriesNo": "1", "rowText": "North Region",
             "columns": [{"key": "2025", "value": "300"}]},
            {"seriesNo": "1.1", "rowText": "0 - 4 Years",
             "columns": [{"key": "2025", "value": "300"}]},
            {"seriesNo": "2", "rowText": "North Region (Male)",
             "columns": [{"key": "2025", "value": "150"}]},
            {"seriesNo": "2.1", "rowText": "0 - 4 Years",
             "columns": [{"key": "2025", "value": "150"}]},
        ]}}
        year, regions = self.ss.parse(payload)
        self.assertEqual(year, "2025")
        self.assertEqual(regions["North Region"]["bands"], {"0 - 4 Years": 300.0})
        self.assertEqual(regions["North Region"]["male"], 150.0)

    def test_the_most_recent_period_is_the_one_used(self):
        rows = [{"seriesNo": "1", "rowText": "West Region",
                 "columns": [{"key": "2019", "value": "1"}, {"key": "2025", "value": "2"}]}]
        self.assertEqual(self.ss.latest_year(rows), "2025")

    def test_an_empty_response_fails_loudly(self):
        with self.assertRaises(SystemExit):
            self.ss.series_rows({"Data": {"row": []}})


class SingaporePlanningAreas(unittest.TestCase):
    """Suppressed cells, and three tables that must not be conflated."""

    def setUp(self):
        from scripts.fetch_census import singapore_areas
        self.sa = singapore_areas

    def test_na_is_missing_and_dash_is_nil(self):
        # Reading "na" as zero turns "we are not telling you" into "nobody lives
        # here", which for an industrial planning area is a different claim.
        self.assertIsNone(self.sa.cell("na"))
        self.assertIsNone(self.sa.cell(""))
        self.assertEqual(self.sa.cell("-"), 0.0)
        self.assertEqual(self.sa.cell("1,234"), 1234.0)
        self.assertEqual(self.sa.cell(" 90 "), 90.0)

    def test_a_wholly_suppressed_breakdown_is_not_a_reconciliation_failure(self):
        # Lim Chu Kang publishes 90 residents and suppresses every category.
        self.sa.check("ethnicity", {"Lim Chu Kang": {}}, {"Lim Chu Kang": 90.0},
                      self.sa.CONTROLS["ethnicity"])

    def test_categories_that_miss_their_row_total_still_fail(self):
        with self.assertRaises(SystemExit) as caught:
            self.sa.check("religion", {"Bedok": {"Buddhist": 10.0}},
                          {"Bedok": 1000.0}, self.sa.CONTROLS["religion"])
        self.assertIn("Bedok", str(caught.exception))

    def test_a_wrong_national_total_is_refused(self):
        with self.assertRaises(SystemExit):
            self.sa.check("language", {}, {}, 1)

    def test_the_three_tables_keep_separate_years(self):
        # 2015 survey, 2020 census aged 15+, 2020 census aged 5+. Sharing one
        # year would imply a single profile of a single population.
        self.assertEqual(set(self.sa.CONTROLS), {"ethnicity", "religion", "language"})
        self.assertNotEqual(self.sa.CONTROLS["religion"], self.sa.CONTROLS["language"])
        self.assertIn("aged 15 and over", self.sa.NOTES["religion"])
        self.assertIn("aged 5 and over", self.sa.NOTES["language"])

    def test_the_language_categories_are_exhaustive(self):
        # The six top-level languages partition the base; Tamil is split out of
        # Indian languages, so the seven must still cover everyone.
        self.assertIn("IndianLanguages_Tamil_Total1", self.sa.LANGUAGE_COLUMNS)
        self.assertIn("IndianLanguages_OtherIndianLanguages_Total1",
                      self.sa.LANGUAGE_COLUMNS)
        self.assertNotIn("IndianLanguages_Total", self.sa.LANGUAGE_COLUMNS)
