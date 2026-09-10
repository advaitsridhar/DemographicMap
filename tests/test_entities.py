"""Tests for the join logic in scripts/build_entities.py.

These cover the two bugs that produced wrong *data* rather than a crash: a
dependency overwriting its parent country, and a curated row matching the wrong
shape.
"""

import json
import collections
import pathlib
import re
import sys
import tempfile
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
        lookup = {be.norm("Amazonas Norte"): {"name": "Amazonas Norte"},
                  be.norm("Amazonas Sul"): {"name": "Amazonas Sul"}}
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
        lookup = {be.norm("Northern"): {"name": "Northern"},
                  be.norm("Northern Cape"): {"name": "Northern Cape"}}
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
        grouped, _ = self.abs.group_by_region(self.rows, "RELIGP", "REGION")
        self.assertEqual(grouped["10050"], {"Catholic": 5.0, "No religion": 7.0})
        self.assertEqual(grouped["10250"], {"Anglican": 3.0})


class AbsPopulation(unittest.TestCase):
    """Where the LGA population comes from.

    All 565 LGAs shipped with none. The docstring promised table C21_G01 and the
    code never fetched it -- while the religion table it did fetch carried the
    region's own total, which `collapse_hierarchy` correctly drops as a
    denominator and which was then thrown away.
    """

    def setUp(self):
        from fetch_census import abs as abs_adapter
        self.abs = abs_adapter

    def rows(self, counts, region="10050"):
        return [({"REGION": "Albury", "REGION_CODE": region, "RELIGP": label}, value)
                for label, value in counts.items()]

    def test_the_published_total_is_the_population(self):
        counts = {"Christianity Total": 53856, "Catholic": 24671,
                  "Secular Total": 44444, "Religious affiliation not stated": 7948,
                  "Total": 106248}
        grouped, totals = self.abs.group_by_region(self.rows(counts), "RELIGP", "REGION")
        self.assertEqual(totals["10050"], 106248)
        # ...and it is still not offered as a category to shade the map by.
        self.assertNotIn("Total", grouped["10050"])

    def test_without_a_total_row_the_categories_are_summed(self):
        # Religion is voluntary, but a blank answer is coded "not stated" rather
        # than dropped, so the collapsed categories partition the population.
        counts = {"Christianity Total": 60, "Catholic": 25,
                  "Religious affiliation not stated": 40}
        _, totals = self.abs.group_by_region(self.rows(counts), "RELIGP", "REGION")
        self.assertEqual(totals["10050"], 100)

    def test_a_flat_classification_still_totals(self):
        # Ancestry has no "... Total" rows, so collapse_hierarchy passes it
        # through. Its total counts responses rather than people -- up to two
        # per person -- which is why the adapter uses only religion's.
        counts = {"English": 70, "Australian": 65, "Irish": 20}
        grouped, totals = self.abs.group_by_region(self.rows(counts), "RELIGP", "REGION")
        self.assertEqual(grouped["10050"], counts)
        self.assertEqual(totals["10050"], 155)

    def test_the_sexes_are_not_added_to_the_persons_total(self):
        rows = [({"REGION_CODE": "1", "SEX": "Persons", "RELIGP": "Total"}, 100.0),
                ({"REGION_CODE": "1", "SEX": "Males", "RELIGP": "Total"}, 49.0),
                ({"REGION_CODE": "1", "SEX": "Females", "RELIGP": "Total"}, 51.0)]
        _, totals = self.abs.group_by_region(rows, "RELIGP", "REGION")
        self.assertEqual(totals["1"], 100.0)


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
        grouped, _ = self.abs.group_by_region(rows, "RELP", "REGION")
        self.assertEqual(grouped["A"]["Christianity"], 10.0)

    def test_no_sex_dimension_is_harmless(self):
        rows = [({"REGION": "A", "RELP": "Christianity Total"}, 10.0)]
        self.assertIsNone(self.abs.sole_sex_dimension(rows))
        self.assertEqual(self.abs.group_by_region(rows, "RELP", "REGION")[0]["A"],
                         {"Christianity": 10.0})


class AbsUnpackCarriesCodes(unittest.TestCase):
    """A dimension's code is what says which categories nest inside which.

    Series dimensions were carrying theirs and observation dimensions were not,
    and the religion classification lives in the observation dimensions -- so
    the code tree never saw a single code and always fell back.
    """

    def setUp(self):
        from fetch_census import abs as abs_adapter
        self.abs = abs_adapter

    def payload(self):
        return {"data": {
            "structures": [{"dimensions": {
                "series": [{"id": "REGION", "values": [{"id": "10050", "name": "Albury"}]}],
                "observation": [{"id": "RELP", "values": [{"id": "1", "name": "Buddhism"},
                                                          {"id": "2", "name": "Christianity"}]}],
            }}],
            "dataSets": [{"series": {"0": {"observations": {"0": [615.0], "1": [11480.0]}}}}],
        }}

    def test_both_kinds_of_dimension_carry_a_code(self):
        rows = self.abs.unpack(self.payload())
        self.assertEqual(len(rows), 2)
        by_label = {lab["RELP"]: lab for lab, _ in rows}
        self.assertEqual(by_label["Buddhism"]["RELP_CODE"], "1")
        self.assertEqual(by_label["Christianity"]["RELP_CODE"], "2")
        self.assertEqual(by_label["Buddhism"]["REGION_CODE"], "10050")


class AbsOutermostLevel(unittest.TestCase):
    """Which level of a nested classification is one whole population.

    Australia's religion breakdown shipped with four categories. Buddhism,
    Hinduism, Islam and Judaism have no sub-levels, so the ABS publishes them
    with no "... Total" marker, and the marker was the only thing being looked
    for -- 2,213,332 people dropped, against those four religions' published
    national totals of 2,213,173. A difference of 159.
    """

    def setUp(self):
        from fetch_census import abs as abs_adapter
        self.abs = abs_adapter
        # Verbatim from a live run: LGA 10650, every code and count as the ABS
        # serves them. The tree is not uniform -- "2" carries no marker while
        # "6_T" and "7_T" do, and the children of "7_T" are numbered from "7".
        self.coded = {
            ("Total", "_T"): 8665,
            ("Christianity Total", "2"): 4644,
            ("Secular Other Spiritual and No Religious Affiliation Total", "7_T"): 2961,
            ("No Religion, so described", "7101"): 2947,
            ("Catholic", "207"): 2040,
            ("Anglican", "201"): 1311,
            ("Religious affiliation not stated", "_N"): 948,
            ("Uniting Church", "233"): 540,
            ("Presbyterian and Reformed", "225"): 422,
            ("Christian, nfd", "200"): 116,
            ("Latter-day Saints", "215"): 48,
            ("Other Religions Total", "6_T"): 39,
            ("Lutheran", "217"): 34,
            ("Baptist", "203"): 26,
            ("Other Religious Groups", "6_O"): 25,
            ("Hinduism", "3"): 25,
            ("Buddhism", "1"): 22,
            ("Islam", "4"): 17,
            ("Sikhism", "6151"): 13,
        }
        self.published = 8665

    def test_the_code_tree_keeps_the_religions_the_marker_missed(self):
        kept, how = self.abs.top_level(self.coded, self.published)
        self.assertEqual(how, "code tree")
        for religion in ("Buddhism", "Hinduism", "Islam"):
            self.assertIn(religion, kept)
        self.assertIn("Christianity", kept)          # marker stripped
        self.assertNotIn("Christianity Total", kept)

    def test_no_child_survives_beside_its_parent(self):
        kept, _ = self.abs.top_level(self.coded, self.published)
        for child in ("Anglican", "Catholic", "Uniting Church", "Lutheran",
                      "Sikhism", "Other Religious Groups",
                      "No Religion, so described"):
            self.assertNotIn(child, kept)

    def test_a_branch_whose_children_are_numbered_from_its_stem(self):
        # "7101" sits under "7_T", not under a code called "7101"'s prefix
        # "7_T" -- the marker has to come off before the prefix test.
        kept, _ = self.abs.top_level(self.coded, self.published)
        self.assertIn("Secular Other Spiritual and No Religious Affiliation", kept)
        self.assertNotIn("No Religion, so described", kept)

    def test_the_kept_level_is_the_whole_population(self):
        kept, _ = self.abs.top_level(self.coded, self.published)
        # Nine people apart from the published total, which is the ABS's own
        # perturbation of small counts, not a missing category.
        self.assertLessEqual(abs(sum(kept.values()) - self.published), 12)
        self.assertNotIn("Total", kept)

    def test_the_suffix_rule_alone_loses_them(self):
        # The behaviour being replaced, pinned so the regression is visible.
        flat = {label: value for (label, _), value in self.coded.items()}
        kept = self.abs.collapse_hierarchy(flat)
        for religion in ("Buddhism", "Hinduism", "Islam"):
            self.assertNotIn(religion, kept)
        self.assertLess(sum(kept.values()), self.published)

    def test_a_small_region_is_judged_on_people_not_percent(self):
        # Leonora, 1,588 people, was 53 short of its published total -- the
        # ABS's perturbation, not a missing religion. A half-percent bound is
        # eight people there, and rejected a partition that was right.
        small = {("Christianity Total", "2"): 900, ("Catholic", "207"): 400,
                 ("Buddhism", "1"): 12, ("Islam", "4"): 9,
                 ("Religious affiliation not stated", "_N"): 614,
                 ("Total", "_T"): 1588}
        kept, how = self.abs.top_level(small, 1588)
        self.assertEqual(how, "code tree")
        self.assertIn("Islam", kept)
        self.assertEqual(sum(kept.values()), 1535)     # 53 short, and accepted

    def test_a_missing_category_is_still_caught_in_a_small_region(self):
        # The floor must not be wide enough to hide one. Christianity is 900 of
        # 1,588 people; dropping it is nothing like a perturbation.
        small = {("Buddhism", "1"): 12, ("Islam", "4"): 9,
                 ("Religious affiliation not stated", "_N"): 614,
                 ("Total", "_T"): 1588}
        _, how = self.abs.top_level(small, 1588)
        self.assertIn("nothing summed", how)

    def test_an_answer_that_does_not_add_up_is_not_used(self):
        # The published total is the judge. A level missing a category is out by
        # far more than the ABS's small-cell perturbation.
        broken = dict(self.coded)
        del broken[("Christianity Total", "2")]
        _, how = self.abs.top_level(broken, self.published)
        self.assertNotEqual(how, "code tree")
        self.assertIn("nothing summed", how)

    def test_the_grand_total_is_nobody_s_parent(self):
        # "_T" loses its marker and becomes the empty string, which prefixes
        # every code there is. Left in, it excluded every category.
        kept = self.abs.outermost_by_code(self.coded)
        self.assertTrue(kept)
        self.assertGreater(sum(kept.values()), 0)

    def test_without_codes_it_falls_back_to_the_marker(self):
        uncoded = {(label, ""): value for (label, _), value in self.coded.items()}
        _, how = self.abs.top_level(uncoded, None)
        self.assertIn("suffix", how)

    def test_a_flat_classification_is_taken_whole(self):
        # Ancestry: no hierarchy, no totals, nothing to strip.
        coded = {("English", "1"): 70, ("Australian", "2"): 65, ("Irish", "3"): 20}
        kept, _ = self.abs.top_level(coded, 155)
        self.assertEqual(kept, {"English": 70, "Australian": 65, "Irish": 20})


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


class NameNormalisation(unittest.TestCase):
    """What survives norm(), and what used to be deleted by it."""

    def test_a_letter_that_does_not_decompose_is_folded_not_dropped(self):
        # NFKD cannot take "o-slash" apart, because it is its own letter rather
        # than an o plus a mark. Deleting it left "stfold", a substring of
        # "vestfoldogtelemark", and Norway's Ostfold was joined to Vestfold og
        # Telemark.
        self.assertEqual(be.norm("Østfold"), "ostfold")
        self.assertNotIn(be.norm("Østfold"), be.norm("Vestfold og Telemark"))

    def test_a_non_latin_name_keeps_its_own_letters(self):
        # 693 boundary names normalised to the empty string -- 352 Russian and
        # 256 Tunisian second-level units among them -- so they were
        # unmatchable, and all collided on one key.
        for name in ("городской округ Канск", "إقليم الخميسات", "高雄市"):
            self.assertTrue(be.norm(name), f"{name} normalised to nothing")
        self.assertNotEqual(be.norm("городской округ Канск"), be.norm("إقليم الخميسات"))

    def test_ascii_names_are_unchanged(self):
        self.assertEqual(be.norm("Zürich"), "zurich")
        self.assertEqual(be.norm("Canton of Zurich"), "cantonzurich")
        self.assertEqual(be.norm("São Paulo"), "saopaulo")

    def test_a_modifier_letter_is_not_a_word_break(self):
        self.assertEqual(be.norm("Dar'a"), be.norm("Dara"))
        # Sanʿaʾ has one "a" where Sanaa has two, so the folded names are not
        # equal -- but neither is split into pieces that line up with nothing.
        self.assertEqual(be.norm("Sanʿaʾ"), "sana")
        self.assertTrue(be.related(be.name_forms("Sanʿaʾ Governorate"),
                                   be.name_forms("Sanaa Governorate")))


class LooseNameMatching(unittest.TestCase):
    """The prefix and containment passes, which compare words rather than a
    squashed run of letters.

    On the squashed string a substring test reads straight across the gap
    between two words: "Anta" sits inside "santacruz", so Argentina's Santa
    Cruz was joined to a department called Anta 406 km away, and Santa Anita to
    the same shape 817 km away.
    """

    def related(self, a, b, at_start=False):
        return be.related(be.name_forms(a), be.name_forms(b), at_start=at_start)

    def test_a_word_cannot_start_inside_another_word(self):
        for other in ("Santa Cruz", "Santa Anita", "Santa Fe"):
            self.assertFalse(self.related("Anta", other), other)

    def test_a_long_official_form_still_finds_the_short_one(self):
        self.assertTrue(self.related("Canton of Zurich", "Zurich"))
        self.assertTrue(self.related("Emirate of Sharjah", "Sharjah"))
        self.assertTrue(self.related("Provincia de Bocas del Toro", "Bocas del Toro"))

    def test_an_inflected_ending_is_the_same_word(self):
        self.assertTrue(self.related("Stockholms lan", "Stockholm"))
        self.assertTrue(self.related("Plzeňský kraj", "Plzeň Region"))
        self.assertTrue(self.related("Northeastern Region", "Northeast"))

    def test_but_not_a_different_word_that_starts_the_same(self):
        # "Tala" is a prefix of "Talampaya", 835 km away.
        self.assertFalse(self.related("Talampaya National Park", "Tala"))

    def test_a_hyphen_is_read_both_ways(self):
        # Joined: the other side spells it as one word.
        self.assertTrue(self.related("Región del Bío-Bío", "Biobío Region"))
        self.assertTrue(self.related("Oe-Cusse Ambeno", "Oecusse"))
        # Split: the other side leaves an article off.
        self.assertTrue(self.related("Al-Basrah", "Basra Governorate"))
        self.assertTrue(self.related("An-Najaf", "Najaf Governorate"))

    def test_a_short_word_only_counts_where_the_match_is_anchored(self):
        # "Lae Atoll" to "Lae" starts at the first word, which is evidence.
        self.assertTrue(self.related("Lae Atoll", "Lae", at_start=True))
        # "Fes" three letters into "Oued Fes" is not: they are different
        # communes, and the match would start partway through the name.
        self.assertFalse(self.related("Oued Fes", "Fes"))
        self.assertFalse(self.related("Oued Fes", "Fes", at_start=True))
        self.assertFalse(self.related("San", "Santa Cruz"))

    def test_a_part_is_not_its_whole(self):
        # Each of these was a live mis-join.
        self.assertFalse(self.related("Budapest", "Pest"))
        self.assertFalse(self.related("Oberbayern", "Bayern"))
        self.assertFalse(self.related("Rheinhessen-Pfalz", "Hessen"))

    def test_the_prefix_pass_is_anchored(self):
        # "Mymensingh Division" to "Mymensingh" starts at the first word;
        # "Bocas del Toro" inside "Provincia de Bocas del Toro" does not, and
        # is the containment pass's job.
        self.assertTrue(self.related("Mymensingh Division", "Mymensingh", at_start=True))
        self.assertFalse(self.related("Provincia de Bocas del Toro", "Bocas del Toro",
                                      at_start=True))


class RivalRowsForOneShape(unittest.TestCase):
    """Several rows of one adapter reaching the same boundary.

    Nothing stopped it, and whichever came last silently overwrote the rest.
    England's East, Mid, North and West Devon all reached a shape called Devon
    -- the source has no plain "Devon" row at all -- so Devon wore West Devon's
    figures and the other three vanished. Texas's Jackson County reached a shape
    called Jack. 1,324 rows were being lost this way.
    """

    def claims(self, *rows):
        """(row, entity, how) triples, all from one adapter file."""
        return [({"name": name, "_source": "x.json"}, {"id": eid, "name": shape}, how)
                for name, eid, shape, how in rows]

    def test_an_outright_match_owns_the_shape(self):
        # "Rotherham" says its own name; "Rother" arrives through the prefix
        # pass. Only one of them is the shape's.
        dropped, notes = be.resolve_collisions(self.claims(
            ("Rotherham", "E1", "Rotherham", "name"),
            ("Rother", "E1", "Rotherham", "prefix")))
        self.assertEqual(dropped, {1})
        self.assertIn("Rotherham", notes[0])

    def test_nothing_to_separate_them_means_nobody_gets_it(self):
        # Four Devons and no way to tell which is the shape's: a visible gap
        # beats an invisible guess.
        dropped, _ = be.resolve_collisions(self.claims(
            ("East Devon", "E2", "Devon", "contains"),
            ("Mid Devon", "E2", "Devon", "contains"),
            ("North Devon", "E2", "Devon", "contains"),
            ("West Devon", "E2", "Devon", "contains")))
        self.assertEqual(dropped, {0, 1, 2, 3})

    def test_a_resolved_parent_outweighs_a_country_wide_guess(self):
        dropped, _ = be.resolve_collisions(self.claims(
            ("Jack County, Texas", "E3", "Jack", "prefix+state"),
            ("Jackson County, Texas", "E3", "Jack", "prefix")))
        self.assertEqual(dropped, {1})

    def test_two_outright_matches_are_a_duplicated_row_not_a_rivalry(self):
        # Wikidata carries both "Ancasti" and "Ancasti Department", and
        # "Department" is a word norm() drops, so both are the same name
        # reaching the same shape. Refusing them would lose Ancasti to a
        # duplicate rather than to a mistake.
        dropped, notes = be.resolve_collisions(self.claims(
            ("Ancasti", "E4", "Ancasti", "name"),
            ("Ancasti Department", "E4", "Ancasti", "name")))
        self.assertEqual(dropped, set())
        self.assertEqual(notes, [])

    def test_an_outright_match_still_evicts_the_loose_ones_beside_it(self):
        dropped, _ = be.resolve_collisions(self.claims(
            ("Dhaka", "E5", "Dhaka", "name"),
            ("Dhaka District", "E5", "Dhaka", "name"),
            ("Dhaka North City Corporation", "E5", "Dhaka", "contains"),
            ("Dhaka-21", "E5", "Dhaka", "prefix")))
        self.assertEqual(dropped, {2, 3})

    def test_rows_from_different_files_are_not_rivals(self):
        # India's C-01 and C-16 both describe Kargil, and both should land.
        rows = [({"name": "Kargil", "_source": "india_district.json"},
                 {"id": "K", "name": "Kargil"}, "name"),
                ({"name": "Kargil", "_source": "india_language_district.json"},
                 {"id": "K", "name": "Kargil"}, "name")]
        dropped, _ = be.resolve_collisions(rows)
        self.assertEqual(dropped, set())

    def test_one_row_per_shape_is_never_touched(self):
        dropped, notes = be.resolve_collisions(self.claims(
            ("Kerala", "A", "Kerala", "contains"),
            ("Goa", "B", "Goa", "prefix")))
        self.assertEqual(dropped, set())
        self.assertEqual(notes, [])


class Admin2Disambiguation(unittest.TestCase):
    """Two shapes, one name: the row must land on the right one or on neither."""

    def shapes(self):
        # Boxes are west-to-east: Himachal around x=0, Uttar Pradesh around x=10.
        return {
            be.norm("Hamirpur"): [
                {"id": "HP-HAM", "name": "Hamirpur", "parent": "S-HP",
                 "bbox": [0, 0, 2, 2]},
                {"id": "UP-HAM", "name": "Hamirpur", "parent": "S-UP",
                 "bbox": [10, 0, 12, 2]},
            ],
            be.norm("Agra"): [{"id": "UP-AGR", "name": "Agra", "parent": "S-UP",
                               "bbox": [10, 0, 12, 2]}],
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


class TwoFirstOrderShapesUnderOneName(unittest.TestCase):
    """CGAZ draws both "Kyiv" and "Kyiv Oblast", and norm() drops "Oblast".

    The admin-1 lookup was a dict comprehension keyed on the normalised name,
    so one of them silently overwrote the other and a capital of 2.95 million
    or the region around it was unreachable -- whichever the boundary file
    listed first. Ukraine's census names both, which is how this surfaced.
    """

    def shapes(self):
        return {be.norm("Kyiv"): [
            {"id": "UA-30", "name": "Kyiv"},
            {"id": "UA-32", "name": "Kyiv Oblast"},
        ]}

    def test_the_city_and_the_region_each_reach_their_own_shape(self):
        city = be.match_name({"name": "Misto Kyyiv", "aliases": ["Kyiv"]},
                             be.settle(self.shapes(), ["Misto Kyyiv", "Kyiv"]))
        self.assertEqual(city[0]["id"], "UA-30")
        oblast = be.match_name(
            {"name": "Kyyivs’Ka Oblast’", "aliases": ["Kyiv Oblast"]},
            be.settle(self.shapes(), ["Kyyivs’Ka Oblast’", "Kyiv Oblast"]))
        self.assertEqual(oblast[0]["id"], "UA-32")

    def test_neither_is_reachable_without_an_exact_name(self):
        entity, _how = be.match_name({"name": "Kyyiv", "aliases": []},
                                     be.settle(self.shapes(), ["Kyyiv"]))
        self.assertIsNone(entity)


class RivalRowsThatDisagree(unittest.TestCase):
    """Two outright matches are one place written twice only if they agree.

    norm() drops "Region", "Oblast", "City" and "Department" alike, so a
    capital and the region named after it reach one key exactly as a duplicate
    listing does. 113 shapes were resolving that way in favour of whichever row
    came last: Moscow's 13.3 million on Moscow Oblast against the oblast's 8.6,
    Kyiv's 2.95 on Kyiv Oblast against 1.80, Morogoro city's on the region 150
    km around it -- each of them a wrong answer that looked exactly like a
    right one.
    """

    def rows(self, one, two):
        return [({"name": one[0], "_source": "wikidata_admin1.json",
                  "population": one[1]}, {"id": "S1", "name": "Shape"}, "name"),
                ({"name": two[0], "_source": "wikidata_admin1.json",
                  "population": two[1]}, {"id": "S1", "name": "Shape"}, "name")]

    def test_agreeing_duplicates_keep_the_exemption(self):
        # Wikidata's two Ancasti items publish the same 3,302 people, so
        # whichever wins the map is right and refusing would lose the place to
        # a duplicate rather than to a mistake.
        pop = {"value": 3302, "year": 2022}
        dropped, _ = be.resolve_collisions(
            self.rows(("Ancasti", pop), ("Ancasti Department", dict(pop))))
        self.assertEqual(dropped, set())

    def test_disagreeing_rivals_are_both_refused(self):
        dropped, notes = be.resolve_collisions(
            self.rows(("Kyiv", {"value": 2952301}),
                      ("Kyiv Oblast", {"value": 1795079})))
        self.assertEqual(dropped, {0, 1})
        self.assertIn("nothing to separate them", notes[0])

    def test_a_gap_is_not_a_disagreement(self):
        # One row without a figure is what merge_adapter is for; the figure
        # survives either order, so this is still a duplicate listing.
        dropped, _ = be.resolve_collisions(
            self.rows(("Belén", {"value": 1234}),
                      ("Belén Department", {"status": "not_available"})))
        self.assertEqual(dropped, set())

    def test_identity_alone_is_not_a_disagreement(self):
        # Every Wikidata item has its own Q-id. Counting that as a difference
        # would make every rivalry a conflict and the test useless.
        rows = self.rows(("Ancasti", {"value": 3302}),
                         ("Ancasti Department", {"value": 3302}))
        rows[0][0]["wikidata"] = "Q1"
        rows[1][0]["wikidata"] = "Q2"
        self.assertEqual(be.conflicting([r for r, _e, _h in rows]), [])
        self.assertEqual(be.resolve_collisions(rows)[0], set())

    def test_the_shapes_own_name_does_not_break_a_row_tie(self):
        # It settles a tie between two shapes and inverts between two rows:
        # CGAZ's Argentine ADM2 is the departments and names them without the
        # word, so the exactly-named rival is the town.
        rows = self.rows(("Andalgalá", {"value": 3300}),
                         ("Andalgalá Department", {"value": 17000}))
        for row, entity, _how in rows:
            entity["name"] = "Andalgalá"
        self.assertEqual(be.resolve_collisions(rows)[0], {0, 1})

    def test_rivals_from_different_files_are_not_rivals(self):
        # India's C-01 and C-16 both describe Kargil, and that is normal.
        rows = self.rows(("Kargil", {"value": 1}), ("Kargil", {"value": 2}))
        rows[1][0]["_source"] = "india_c16.json"
        self.assertEqual(be.resolve_collisions(rows)[0], set())


class TwoShapesOneNameInsideOneParent(unittest.TestCase):
    """Same name, same parent: settled by an exact name or not at all.

    norm() drops the word "city", so geoBoundaries' "Cotabato" and "Cotabato
    City" -- a province and the enclave city, both drawn inside Soccsksargen --
    arrived under one key and were both thrown away as ambiguous. The province
    was then handed South Cotabato by the containment pass, 900,000 people
    wearing a neighbour's figures, and the only thing that caught it was the
    collision pass refusing both. What the map showed was a gap where a census
    of 1.4 million people should have been.
    """

    def shapes(self):
        return {
            be.norm("Cotabato"): [
                {"id": "PH-COT", "name": "Cotabato", "parent": "R-12",
                 "bbox": [0, 0, 2, 2]},
                {"id": "PH-COC", "name": "Cotabato City", "parent": "R-12",
                 "bbox": [1, 1, 1.2, 1.2]},
            ],
            be.norm("South Cotabato"): [
                {"id": "PH-SCO", "name": "South Cotabato", "parent": "R-12",
                 "bbox": [0, -3, 2, -1]}],
        }

    def admin1(self):
        return {be.norm("Soccsksargen"): {"id": "R-12", "name": "Soccsksargen"}}

    def test_an_exact_name_settles_the_tie(self):
        entity, how = be.match_admin2(
            {"name": "Province Of Cotabato", "aliases": ["Cotabato"],
             "parent_name": "Soccsksargen"}, self.shapes(), self.admin1())
        self.assertEqual(entity["id"], "PH-COT")
        self.assertIn("state", how)

    def test_the_city_reaches_its_own_shape(self):
        entity, _ = be.match_admin2(
            {"name": "Cotabato City", "parent_name": "Soccsksargen"},
            self.shapes(), self.admin1())
        self.assertEqual(entity["id"], "PH-COC")

    def test_nothing_weaker_than_an_exact_name_settles_it(self):
        # "Cotabato Province" is neither shape's name, so the tie stands and
        # this pass hands back nothing. What happens to the row afterwards is
        # the containment pass's business, tested elsewhere; the point here is
        # that neither tied shape may be reached on a shared prefix.
        entity, _ = be.match_admin2(
            {"name": "Cotabato Province", "parent_name": "Soccsksargen"},
            self.shapes(), self.admin1())
        self.assertNotIn(entity and entity["id"], ("PH-COT", "PH-COC"))

    def test_a_tie_with_nothing_else_in_reach_is_refused_outright(self):
        tied = {k: v for k, v in self.shapes().items()
                if k != be.norm("South Cotabato")}
        entity, how = be.match_admin2(
            {"name": "Cotabato Province", "parent_name": "Soccsksargen"},
            tied, self.admin1())
        self.assertIsNone(entity)
        self.assertEqual(how, "ambiguous")


class Admin2ContradictsItself(unittest.TestCase):
    """A row that names one state and matches a shape in another.

    Before this was refused, 274 rows across nine countries wore another unit's
    figures: Vietnam's An Bien, a ward of Haiphong at 20.85N, carried the
    population of the An Bien district of Kien Giang, 1,200 km south.
    """

    def shapes(self):
        return {
            # Only Uttar Pradesh has an Agra; Himachal has none.
            be.norm("Agra"): [{"id": "UP-AGR", "name": "Agra", "parent": "S-UP",
                               "bbox": [10, 0, 12, 2]}],
        }

    def admin1(self):
        return {be.norm(name): {"id": eid, "name": name} for eid, name in
                (("S-HP", "Himachal Pradesh"), ("S-UP", "Uttar Pradesh"))}

    def test_coordinates_outside_the_shape_refuse_the_match(self):
        entity, how = be.match_admin2(
            {"name": "Agra", "parent_name": "Himachal Pradesh", "point": [1, 1]},
            self.shapes(), self.admin1())
        self.assertIsNone(entity)
        self.assertEqual(how, "outside_parent")

    def test_coordinates_inside_the_shape_keep_it(self):
        # Bogota under Cundinamarca, Lima under Lima Department: the parent is
        # named historically, and the shape is still the right one.
        entity, how = be.match_admin2(
            {"name": "Agra", "parent_name": "Himachal Pradesh", "point": [11, 1]},
            self.shapes(), self.admin1())
        self.assertEqual(entity["id"], "UP-AGR")
        self.assertTrue(how.endswith("+point"))

    def test_without_coordinates_nothing_is_refused(self):
        # India's 2011 districts name the states of 2011: Adilabad says Andhra
        # Pradesh where the boundary file says Telangana, and that match is
        # correct. With no coordinates there is no evidence, and a rule with no
        # evidence behind it must not be the one deciding.
        entity, _ = be.match_admin2(
            {"name": "Agra", "parent_name": "Himachal Pradesh"},
            self.shapes(), self.admin1())
        self.assertEqual(entity["id"], "UP-AGR")


class RowPointAndBox(unittest.TestCase):
    """Reading a coordinate off a row, and testing it against a box."""

    def test_a_gap_marker_is_not_a_coordinate(self):
        # Wikidata writes P625 and its absence into the same field.
        self.assertIsNone(be.row_point({"coordinates": {"status": "not_available"}}))
        self.assertIsNone(be.row_point({"coordinates": [1.0]}))
        self.assertIsNone(be.row_point({}))
        self.assertEqual(be.row_point({"coordinates": [1, 2]}), [1.0, 2.0])
        self.assertEqual(be.row_point({"point": [3, 4]}), [3.0, 4.0])

    def test_a_missing_box_never_confirms(self):
        self.assertFalse(be.within_bbox([1, 1], None))
        self.assertFalse(be.within_bbox(None, [0, 0, 2, 2]))
        self.assertFalse(be.within_bbox([1, 1], [0, 0, 2]))

    def test_edges_count_as_inside(self):
        self.assertTrue(be.within_bbox([0, 0], [0, 0, 2, 2]))
        self.assertTrue(be.within_bbox([1, 1], [0, 0, 2, 2]))
        self.assertFalse(be.within_bbox([3, 1], [0, 0, 2, 2]))


class RollUpToTheCountry(unittest.TestCase):
    """Summing a country from its first-level divisions.

    Unlike the level below, this never fills a gap -- every country record
    already carries a Factbook composition -- so every sum here replaces a
    published figure, and the thing it replaced has to survive.
    """

    def country(self, population=1000, language=None):
        return {"id": "XXX", "codes": {"iso3": "XXX"}, "name": "Somewhere",
                "population": {"value": population, "year": 2025, "source": "Estimate"},
                "language": language if language is not None
                else [{"group": "Alpha", "pct": 90.0, "count": 900},
                      {"group": "other", "pct": 10.0, "count": 100}],
                "sources": []}

    def region(self, name, pop, groups):
        total = sum(groups.values())
        return {"id": name, "name": name, "parent": "XXX",
                "population": {"value": pop, "year": 2025, "source": "Register"},
                "language": [{"group": g, "pct": round(100 * c / total, 1), "count": c}
                             for g, c in groups.items()],
                "sources": [{"field": "population/language", "name": "Register"}]}

    def regions(self):
        return [self.region("North", 600, {"Alpha": 500, "Beta": 100}),
                self.region("South", 400, {"Alpha": 300, "Beta": 100})]

    def roll(self, country, regions):
        be.roll_up_countries([country], {"XXX": regions})
        return country

    def test_a_country_is_summed_from_a_complete_set_of_regions(self):
        country = self.roll(self.country(), self.regions())
        self.assertEqual([(g["group"], g["count"]) for g in country["language"]],
                         [("Alpha", 800), ("Beta", 200)])

    def test_the_displaced_published_figure_is_kept_in_the_note(self):
        # It is the only independent statement about the country, so
        # overwriting it silently would destroy the sum's only check.
        country = self.roll(self.country(), self.regions())
        note = country["language_note"]
        self.assertIn("first-level", note)
        self.assertIn("Replaces a separately published figure", note)
        self.assertIn("Alpha 90.0%", note)

    def test_a_stale_census_against_a_current_estimate_is_refused(self):
        # The regions sum to 1,000 and the country's own estimate is 1,100:
        # a vintage gap, and still outside the bound this has been tested at.
        country = self.roll(self.country(population=1100), self.regions())
        self.assertEqual([g["group"] for g in country["language"]], ["Alpha", "other"])

    def test_a_region_missing_the_field_refuses_the_whole_sum(self):
        # Partial coverage is the dangerous case: the sum would look whole and
        # describe only part of the country.
        regions = self.regions()
        regions[1]["language"] = {"status": "not_available"}
        country = self.roll(self.country(), regions)
        self.assertEqual([g["group"] for g in country["language"]], ["Alpha", "other"])

    def test_a_country_that_does_not_ask_is_left_alone(self):
        country = self.country(language={"status": "not_collected",
                                         "note": "France asks no such question"})
        self.roll(country, self.regions())
        self.assertEqual(country["language"]["status"], "not_collected")


class RollUpFromChildren(unittest.TestCase):
    """Summing a parent whose every constituent part is measured.

    Ladakh is the case: a union territory since 2019, so the 2011 census that
    supplies India's district figures never published a row for it, while
    publishing both of its districts.
    """

    def parent(self, population=1000):
        return {"id": "P", "name": "Ladakh",
                "population": {"value": population, "year": 2011, "source": "Wikidata"},
                "religion": {"status": "not_available"}, "sources": []}

    def child(self, name, pop, groups):
        total = sum(groups.values())
        return {"id": name, "name": name, "parent": "P",
                "population": {"value": pop, "year": 2011, "source": "Census"},
                "religion": [{"group": g, "pct": round(100 * c / total, 1), "count": c}
                             for g, c in groups.items()],
                "religion_year": 2011,
                "sources": [{"field": "population/religion", "name": "Census"}]}

    def kids(self):
        return [self.child("Leh", 600, {"Buddhist": 400, "Muslim": 200}),
                self.child("Kargil", 400, {"Muslim": 300, "Buddhist": 100})]

    def test_a_complete_set_of_children_is_summed(self):
        parent = self.parent()
        self.assertIsNone(be.roll_up_field(parent, self.kids(), "religion"))
        # Equal counts, so the name breaks the tie and the order is stable.
        self.assertEqual([(g["group"], g["pct"], g["count"]) for g in parent["religion"]],
                         [("Buddhist", 50.0, 500), ("Muslim", 50.0, 500)])
        self.assertIn("Summed from all 2", parent["religion_note"])
        self.assertEqual(parent["religion_year"], 2011)

    def test_the_source_travels_with_the_figure(self):
        # Keyed on name and field: a record carries one census several times.
        parent = self.parent()
        parent["sources"] = [{"field": "note", "name": "Census"}]
        be.roll_up_field(parent, self.kids(), "religion")
        self.assertIn(("population/religion", "Census"),
                      {(s.get("field"), s.get("name")) for s in parent["sources"]})

    def test_a_partial_set_of_children_is_refused(self):
        # The dangerous case: the sum would look whole and cover part of the
        # territory. Nine of England's 150 children have no religion.
        parent = self.parent()
        kids = self.kids()
        kids[1]["religion"] = {"status": "not_available"}
        why = be.roll_up_field(parent, kids, "religion")
        self.assertIn("1 of 2", why)
        self.assertNotIsInstance(parent["religion"], list)

    def test_children_that_do_not_add_up_are_refused(self):
        # Wales' 22 children sum to 3,107,513 against a published 1,168,000.
        parent = self.parent(population=3000)
        why = be.roll_up_field(parent, self.kids(), "religion")
        self.assertIn("children sum to", why)
        self.assertNotIsInstance(parent["religion"], list)

    def test_children_without_population_are_refused(self):
        # Australia's LGAs carry religion and no population, so weighting them
        # would weight by nothing at all.
        parent = self.parent()
        kids = self.kids()
        for kid in kids:
            kid["population"] = {"status": "not_available"}
        self.assertIn("no population", be.roll_up_field(parent, kids, "religion"))
        self.assertNotIsInstance(parent["religion"], list)

    def test_a_parent_with_no_population_cannot_be_checked(self):
        parent = self.parent()
        parent["population"] = {"status": "not_available"}
        self.assertIn("no published population",
                      be.roll_up_field(parent, self.kids(), "religion"))

    def test_a_real_value_is_never_overwritten(self):
        parent = self.parent()
        parent["religion"] = [{"group": "Buddhist", "pct": 100.0, "count": 1000}]
        self.assertIsNone(be.roll_up_field(parent, self.kids(), "religion"))
        self.assertEqual(parent["religion"][0]["pct"], 100.0)

    def test_not_collected_is_a_statement_and_stands(self):
        parent = self.parent()
        parent["religion"] = {"status": "not_collected",
                              "note": "France records no religion."}
        self.assertIsNone(be.roll_up_field(parent, self.kids(), "religion"))
        self.assertEqual(parent["religion"]["status"], "not_collected")

    def test_the_denominator_comes_from_the_shares_not_the_population(self):
        # New Zealand's ethnicity responses outnumber its people, and Mexico
        # reports language shares of the population aged three and over. A sum
        # against total population would restate both as something else.
        parent = self.parent()
        kids = [{"id": "A", "name": "A", "parent": "P",
                 "population": {"value": 1000, "year": 2020, "source": "S"},
                 "religion": [{"group": "Maori", "pct": 60.0, "count": 480},
                              {"group": "European", "pct": 70.0, "count": 560}],
                 "sources": []}]
        self.assertIsNone(be.roll_up_field(parent, kids, "religion"))
        # 480/800 and 560/800: the basis the child used, carried through.
        self.assertEqual([g["pct"] for g in parent["religion"]], [70.0, 60.0])


class ImpliedTotal(unittest.TestCase):
    def test_the_largest_group_sets_the_denominator(self):
        # A category at 0.0% would imply any denominator at all.
        rows = [{"group": "A", "pct": 80.0, "count": 800},
                {"group": "B", "pct": 0.0, "count": 1}]
        self.assertAlmostEqual(be.implied_total(rows), 1000.0)

    def test_shares_without_counts_imply_nothing(self):
        self.assertIsNone(be.implied_total([{"group": "A", "pct": 80.0}]))
        self.assertIsNone(be.implied_total([]))


class PxWebUnstack(unittest.TestCase):
    """json-stat2 arrives as one flat array; position is the only record of
    which cell is which."""

    def setUp(self):
        from fetch_census import pxweb
        self.px = pxweb

    def payload(self):
        # Two counties x three ethnicities, row-major over ["Maakond","Rahvus"].
        return {
            "class": "dataset",
            "id": ["Maakond", "Rahvus"],
            "size": [2, 3],
            "dimension": {
                "Maakond": {"category": {
                    "index": {"37": 0, "39": 1},
                    "label": {"37": "Harju county", "39": "Hiiu county"}}},
                "Rahvus": {"category": {
                    "index": {"1": 0, "2": 1, "3": 2},
                    "label": {"1": "Total", "2": "Estonians", "3": "Russians"}}},
            },
            "value": [600, 350, 250, 100, 90, 10],
        }

    def test_each_cell_keeps_its_own_categories(self):
        cells = dict((tuple(sorted((k, v[0]) for k, v in key.items())), value)
                     for key, value in self.px.unstack(self.payload()))
        self.assertEqual(cells[(("Maakond", "37"), ("Rahvus", "2"))], 350)
        self.assertEqual(cells[(("Maakond", "39"), ("Rahvus", "3"))], 10)

    def test_a_missing_cell_is_skipped_not_shifted(self):
        payload = self.payload()
        payload["value"][1] = None
        codes = [tuple(sorted((k, v[0]) for k, v in key.items()))
                 for key, _ in self.px.unstack(payload)]
        self.assertNotIn((("Maakond", "37"), ("Rahvus", "2")), codes)
        # ...and everything after it still lands where it belongs.
        cells = dict((tuple(sorted((k, v[0]) for k, v in key.items())), value)
                     for key, value in self.px.unstack(payload))
        self.assertEqual(cells[(("Maakond", "39"), ("Rahvus", "3"))], 10)


class PxWebLevels(unittest.TestCase):
    """A PxWeb geography variable holds several levels, and often two vintages
    of one of them."""

    def setUp(self):
        from fetch_census import pxweb
        self.px = pxweb

    def table(self, **kw):
        return self.px.Table(path="p", field="ethnicity", geo="AREA",
                             group="ETHNICITY", **kw)

    def test_code_length_pins_the_level(self):
        # Latvia: country "LV", statistical regions "LV00A", municipalities
        # "LV0001000" -- and the regions come in a pre-2024 and a post-2024
        # set that overlap each other.
        table = self.table(geo_len=9)
        self.assertTrue(self.px.wanted_area("LV0001000", "Riga", table))
        self.assertFalse(self.px.wanted_area("LV00A", "Riga region", table))
        self.assertFalse(self.px.wanted_area("LV", "Latvia", table))

    def test_a_named_total_is_never_a_unit(self):
        table = self.table()
        self.assertFalse(self.px.wanted_area("00", "Whole country", table))
        self.assertFalse(self.px.wanted_area("X", "Total", table))

    def test_a_child_row_is_not_a_unit(self):
        # Estonia writes Tallinn as "..Tallinn" because it sits inside Harju.
        table = self.table()
        self.assertFalse(self.px.wanted_area("784", "..Tallinn", table))
        self.assertTrue(self.px.wanted_area("37", "Harju county", table))

    def test_explicit_drops_win(self):
        table = self.table(drop=("unk",))
        self.assertFalse(self.px.wanted_area("unk", "County unknown", table))


class PxWebPartition(unittest.TestCase):
    """The one control a single table offers: the categories must add up to the
    total the table itself publishes."""

    def setUp(self):
        from fetch_census import pxweb
        self.px = pxweb
        self.table = self.px.Table(path="p", field="ethnicity", geo="AREA",
                                   group="E")

    def test_categories_summing_to_the_total_pass(self):
        self.px.check("EST", self.table,
                      {"37": {"name": "Harju", "total": 600,
                              "counts": {"Estonians": 350, "Russians": 250}}})

    def test_a_kept_sub_level_is_caught(self):
        # Keeping "Other" and its children too is the mistake this catches.
        with self.assertRaises(SystemExit) as caught:
            self.px.check("EST", self.table,
                          {"37": {"name": "Harju", "total": 600,
                                  "counts": {"Estonians": 350, "Other": 250,
                                             "Ukrainians": 200}}})
        self.assertIn("Harju", str(caught.exception))

    def test_a_unit_with_no_published_total_is_not_judged(self):
        self.px.check("EST", self.table,
                      {"37": {"name": "Harju", "total": None,
                              "counts": {"Estonians": 350}}})

    def test_units_must_also_add_up_to_the_country(self):
        # Every Latvian municipality's own categories added up perfectly while
        # three towns were counted twice, once alone and once inside the
        # municipality holding them. Only the national row shows that.
        units = {"a": {"name": "Jekabpils municipality", "total": 38134,
                       "counts": {"Latvians": 38134}},
                 "b": {"name": "Jekabpils", "total": 20685,
                       "counts": {"Latvians": 20685}}}
        with self.assertRaises(SystemExit) as caught:
            self.px.check("LVA", self.table, units, national=38134)
        self.assertIn("inside another", str(caught.exception))

    def test_units_that_do_add_up_to_the_country_pass(self):
        units = {"a": {"name": "A", "total": 600, "counts": {"X": 600}},
                 "b": {"name": "B", "total": 400, "counts": {"X": 400}}}
        self.px.check("LVA", self.table, units, national=1000)


class FinlandLevels(unittest.TestCase):
    """Finland says the level in the code, and repeats the code in the label."""

    def setUp(self):
        from fetch_census import pxweb
        self.px = pxweb
        self.table = pxweb.INSTANCES["FIN"]["tables"][0]

    def test_the_level_is_a_prefix_not_a_width(self):
        # "MK" is maakunta. A width rule would separate these by luck -- every
        # MK code happens to be one character longer than every aggregate --
        # and would break the day an aggregate got a fourth character.
        self.assertTrue(self.px.wanted_area("MK01", "MK01 Uusimaa", self.table))
        self.assertTrue(self.px.wanted_area("MK21", "MK21 Åland", self.table))
        self.assertFalse(self.px.wanted_area("MA1", "MA1 MAINLAND FINLAND", self.table))

    def test_aland_is_not_counted_twice(self):
        # "MA2 ÅLAND" is "MK21 Åland" under another name: an aggregate of one.
        # Keeping both would add the whole province a second time.
        self.assertFalse(self.px.wanted_area("MA2", "MA2 ÅLAND", self.table))
        self.assertEqual(self.px.reject_reason("MA2", "MA2 ÅLAND", self.table),
                         "code does not start 'MK'")

    def test_the_country_row_is_the_control_not_a_unit(self):
        self.assertFalse(self.px.wanted_area("SSS", "WHOLE COUNTRY", self.table))
        self.assertEqual(self.px.reject_reason("SSS", "WHOLE COUNTRY", self.table),
                         "the country itself")

    def test_the_code_is_stripped_off_the_label(self):
        # No boundary file has heard of a place called "MK13 Central Finland".
        self.assertEqual(self.px.place_name("MK13 Central Finland", "MK13"),
                         "Central Finland")
        self.assertEqual(self.px.place_name("MK19 Lapland", "MK19"), "Lapland")

    def test_only_the_rows_own_code_is_stripped(self):
        self.assertEqual(self.px.place_name("A1 Something", "B2"), "A1 Something")

    def test_the_exonyms_geoboundaries_uses_are_declared(self):
        # Six regions are named there with older English exonyms that neither
        # the Finnish label nor Statistics Finland's English one reaches.
        # Nothing infers "Finland Proper" from "Varsinais-Suomi".
        declared = self.px.INSTANCES["FIN"]["aliases"]
        self.assertEqual(declared["MK02"], ("Finland Proper",))
        self.assertEqual(declared["MK05"], ("Tavastia Proper",))
        self.assertEqual(declared["MK17"], ("Northern Ostrobothnia",))

    def test_the_two_language_parents_are_dropped(self):
        # "01 NATIONAL LANGUAGES, TOTAL" holds Finnish, Swedish and Sami; "02
        # FOREIGN LANGUAGES, TOTAL" holds the other 163. Neither label is a
        # word is_total() knows, so keeping them would count most of the
        # country twice while every check still passed.
        self.assertIn("01", self.table.drop)
        self.assertIn("02", self.table.drop)
        self.assertFalse(self.px.is_total("NATIONAL LANGUAGES, TOTAL"))

    def test_age_and_sex_are_pinned_to_their_totals(self):
        # Unpinned, every resident is counted once per age band.
        self.assertEqual(self.table.keep["ikaryhma_10_20180101"], "SSS")
        self.assertEqual(self.table.keep["sukupuoli_9_20180101"], "SSS")


class BalticPlurals(unittest.TestCase):
    """One people written two ways is one group, not two."""

    def setUp(self):
        import canonical_groups
        self.cg = canonical_groups
        self.lookup = canonical_groups.lookup("ethnicity")

    def canonical(self, label):
        return self.lookup.get(self.cg.key(label), label)

    def test_a_plural_is_the_same_people_as_its_singular(self):
        # The Baltic registers write "Russians"; every other source in this
        # dataset writes "Russian". Unmapped they were two entries for one
        # people, and neither was the filter anyone wanted.
        for plural, singular in (("Russians", "Russian"),
                                 ("Latvians", "Latvian"),
                                 ("Estonians", "Estonian"),
                                 ("Ukrainians", "Ukrainian"),
                                 ("Belarusians", "Belarusian")):
            self.assertEqual(self.canonical(plural), singular)
            self.assertEqual(self.canonical(singular), singular)

    def test_a_noun_and_its_adjective_are_one_group(self):
        self.assertEqual(self.canonical("Poles"), self.canonical("Polish"))
        self.assertEqual(self.canonical("Jews"), self.canonical("Jewish"))

    def test_both_offices_residuals_are_named_as_residuals(self):
        # Estonia's "unknown" is a non-response; its "other" is an answer
        # outside the named list. They are different and both must show.
        self.assertEqual(self.canonical("Ethnic nationality unknown"),
                         "Ethnicity not stated")
        self.assertEqual(self.canonical("Other ethnic nationalities"),
                         "Other ethnicity")
        self.assertTrue(self.cg.is_residual(self.canonical("Other ethnic nationalities")))

    def test_latvias_residual_holds_two_things_and_is_not_split(self):
        # It is "other", "selected none" and "did not indicate" in one cell.
        # Nothing can separate them, so it goes with "other" and the record's
        # note says what is inside it.
        self.assertEqual(
            self.canonical("Other ethnicities, including not selected and "
                           "not indicated ethnicity"),
            "Other ethnicity")

    def test_a_category_that_is_not_a_spelling_is_left_alone(self):
        # The table admits one name spelled two ways, not two states'
        # categories folded together.
        self.assertEqual(self.canonical("White"), "White")
        self.assertEqual(self.canonical("Mestizo"), "Mestizo")


class PxWebNestedLevels(unittest.TestCase):
    """Code length alone does not always pin a level."""

    def setUp(self):
        from fetch_census import pxweb
        self.px = pxweb

    def table(self):
        return self.px.Table(path="p", field="ethnicity", geo="AREA",
                             group="E", geo_len=9, geo_stem=6)

    def test_a_town_is_dropped_because_its_municipality_stands_beside_it(self):
        # Latvia's towns are the same width as their municipalities and differ
        # only in the tail: "LV0031000" holds "LV0031010".
        nested = self.px.drop_nested(
            ["LV0031000", "LV0031010", "LV0003000"], self.table())
        self.assertEqual(nested, {"LV0031010": "LV0031000"})

    def test_an_odd_tail_alone_in_its_family_is_a_unit_not_a_child(self):
        # Madona after the July 2025 merge is "LV0038001". A rule that refused
        # every tail but "000" took it out and lost 29,466 people; nothing
        # contains it, so nothing should.
        nested = self.px.drop_nested(
            ["LV0038001", "LV0031000", "LV0031010"], self.table())
        self.assertNotIn("LV0038001", nested)

    def test_containment_needs_the_whole_set(self):
        # One code at a time cannot tell the two cases apart, so the rule is
        # not asked to: with no municipality present the town is kept.
        self.assertTrue(self.px.wanted_area("LV0031010", "Jekabpils", self.table()))
        self.assertEqual(self.px.drop_nested(["LV0031010"], self.table()), {})

    def test_the_language_segment_of_a_base_url_is_swappable(self):
        # The join key is the office's own local name, because that is what the
        # boundary file carries. Every instance seen puts the language in the
        # path and serves the same tables under each one.
        self.assertEqual(
            self.px.in_language("https://data.stat.gov.lv/api/v1/en/OSP_PUB", "lv"),
            "https://data.stat.gov.lv/api/v1/lv/OSP_PUB")
        self.assertEqual(
            self.px.in_language("https://andmed.stat.ee/api/v1/en/stat", "et"),
            "https://andmed.stat.ee/api/v1/et/stat")

    def test_only_the_language_segment_is_swapped(self):
        # "en" appears in host names and dataset names too; only the segment
        # right after the version is the language.
        self.assertEqual(
            self.px.in_language("https://x.en.example/api/v1/en/en_DATA", "lv"),
            "https://x.en.example/api/v1/lv/en_DATA")

    def test_a_redrawn_units_vintage_is_not_part_of_its_name(self):
        # The office distinguishes vintages in the label. A shape file has
        # never heard of "Madona municipality (from 01.07.2025.)".
        self.assertEqual(self.px.place_name("Madona municipality (from 01.07.2025.)"),
                         "Madona municipality")
        self.assertEqual(self.px.place_name("Valka municipality (until 30.06.2021.)"),
                         "Valka municipality")

    def test_a_parenthesis_that_is_part_of_a_name_stays(self):
        self.assertEqual(self.px.place_name("Saint-Denis (Reunion)"),
                         "Saint-Denis (Reunion)")

    def test_no_stem_means_no_containment_rule(self):
        table = self.px.Table(path="p", field="ethnicity", geo="AREA",
                              group="E", geo_len=9)
        self.assertEqual(
            self.px.drop_nested(["LV0031000", "LV0031010"], table), {})


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


class SwitzerlandMainLanguages(unittest.TestCase):
    """A sample survey where a person may name up to three languages."""

    def setUp(self):
        from scripts.fetch_census import switzerland
        self.ch = switzerland

    def test_bilingual_canton_names_map_to_the_boundary_spelling(self):
        self.assertEqual(self.ch.clean("Bern / Berne"), "Bern")
        self.assertEqual(self.ch.clean("Valais / Wallis"), "Valais")
        # The workbook's sheet tabs space the two names instead of slashing
        # them; the Canton sheet does not, so only the slashed form is aliased.
        self.assertEqual(self.ch.clean("Fribourg / Freiburg"), "Fribourg")
        self.assertEqual(self.ch.clean("Zürich"), "Zürich")

    def test_suppressed_cells_are_missing_not_zero(self):
        # 'X' marks fewer than five observations behind the estimate.
        self.assertIsNone(self.ch.number("X"))
        self.assertIsNone(self.ch.number(None))
        self.assertEqual(self.ch.number(87.4), 87.4)

    def test_the_national_row_must_be_present_to_check_against(self):
        # Without it the canton sum is compared with itself and cannot fail.
        with self.assertRaises(SystemExit) as caught:
            self.ch.check([{"name": "Uri", "total": 1.0, "counts": {}, "dropped": []}],
                          {"name": "Total", "total": 1.0, "counts": {}})
        self.assertIn("no language columns", str(caught.exception))

    def test_cantons_must_reproduce_the_national_total(self):
        with self.assertRaises(SystemExit) as caught:
            self.ch.check([{"name": "Uri", "total": 100.0, "counts": {}, "dropped": []}],
                          {"name": "Total", "total": 999.0, "counts": {"German": 1.0}})
        self.assertIn("cantons sum to", str(caught.exception))

    def test_the_note_says_shares_exceed_one_hundred_percent(self):
        self.assertIn("more than 100%", self.ch.NOTE)
        self.assertIn("estimate", self.ch.NOTE)


class PakistanCells(unittest.TestCase):
    """Table 9 is read by what it prints, not by where it prints it.

    The coordinates below are real, off page 1 of each province's file, read
    with probe_pdf --boxes. Both provinces are here because every rule tried
    on position passed against one file and failed the other.

    Only the reconciliation announces a misread. A column read one place to
    the left still sums to something, and the reason Pakistan has not shipped
    wrong is that the table prints its own denominator beside every row.
    """

    # Khyber Pakhtunkhwa breaks 36 into "3" and "6"; Punjab breaks a leading
    # digit off almost every figure; and the last row of each has the office's
    # dash where a religion is absent.
    KP = [
        "ALL[49-60] SEXES[62-83] 40,641,120[146-177] 40,486,153[195-226] "
        "134,884[252-275] 5,473[306-321] 951[356-366] 629[411-421] "
        "4,050[441-456] 3[490-494] 6[494-497] 8,944[516-532]",
        "MALE[49-66] 20,742,619[146-177] 20,668,933[195-226] 63,685[256-275] "
        "2,721[306-321] 475[356-366] 330[411-421] 2,084[441-456] 2[490-494] "
        "0[494-497] 4,371[516-532]",
        "TRANSGENDER[49-97] 1,117[161-177] 1,098[210-226] 9[271-275] "
        "-[312-314] -[357-359] 1[418-421] 2[453-456] -[488-490] 7[528-532]",
    ]
    PUNJAB = [
        "ALL[49-60] SEXES[62-83] 127,333,305[138-173] 1[186-190] "
        "24,462,897[190-221] 2[241-244] ,458,924[244-268] 2[297-300] "
        "28,559[300-319] 1[349-352] 40,512[352-371] 2[416-419] 1,157[419-435] "
        "5[455-459] ,649[459-471] 3[495-499] 58[499-506] 15,249[529-548]",
        "MALE[49-66] 65,277,723[142-173] 6[190-193] 3,825,580[193-221] "
        "1[241-244] ,242,198[244-268] 1[297-300] 17,671[300-319] 6[352-356] "
        "9,941[356-371] 1[416-419] 1,058[419-435] 2[455-459] ,975[459-471] "
        "1[495-499] 99[499-506] 8,101[533-548]",
        "TRANSGENDER[49-97] 3,246[157-173] 3[206-209] ,180[209-221] "
        "5[262-265] 7[265-268] 4[316-319] 1[368-371] -[426-428] 2[467-471] "
        "-[497-499] 2[545-548]",
    ]
    # The same district row as Khyber Pakhtunkhwa's page 1 prints it: no
    # thousands separators, and set two points right of the province rows.
    ABBOTTABAD = ("ALL[47-58] SEXES[60-81] 1397587[155-179] 1391394[204-228] "
                  "5818[263-277] 97[316-323] 21[361-368] 17[416-423] "
                  "43[451-458] 6[496-499] 191[523-534]")

    @staticmethod
    def row(spec):
        """A row written as it came off the page: text[x0-x1] ..."""
        cells = []
        for part in spec.split():
            text, span = part.rsplit("[", 1)
            x0, x1 = span.rstrip("]").split("-")
            cells.append((float(x0), float(x1), text))
        return cells

    def setUp(self):
        from scripts.fetch_census import pakistan
        self.pk = pakistan

    def read(self, spec):
        return dict(zip(self.pk.COLUMNS,
                        self.pk.values(self.row(spec), "test", "row")))

    def test_every_row_of_both_provinces_has_nine_cells(self):
        for spec in self.KP + self.PUNJAB + [self.ABBOTTABAD]:
            self.assertEqual(len(self.pk.printed(self.row(spec))), 9, spec[:40])

    def test_a_figure_split_across_words_is_rejoined(self):
        # 36 Parsis as "3" and "6"; 124,462,897 as "1" and "24,462,897".
        self.assertEqual(self.read(self.KP[0])["Parsi"], 36)
        self.assertEqual(self.read(self.PUNJAB[0])["Muslim"], 124_462_897)

    def test_a_leading_zero_is_a_place_not_a_magnitude(self):
        # Punjab writes 1,071,693 as "1" and ",071,693"; read as a magnitude
        # the zero is lost and the figure comes out ten times too small.
        self.assertEqual(self.pk.printed(self.row("1[186-190] ,071,693[190-221]")),
                         [1_071_693])

    def test_words_a_column_apart_are_not_joined(self):
        # The gap inside a value is 0 points and between columns never less
        # than 13, in both files.
        self.assertEqual(self.pk.printed(self.row("951[356-366] 629[411-421]")),
                         [951, 629])

    def test_the_dash_is_a_cell_and_counts_as_one(self):
        # This is what makes counting sound where position is not: the office
        # writes a dash rather than leaving a cell empty, so nothing is ever
        # missing from a row and the cells cannot slip out of step.
        got = self.read(self.KP[2])
        self.assertEqual(got["Ahmadi"], 0)
        self.assertEqual(got["Parsi"], 0)
        self.assertEqual(got["Other religion"], 7)

    def test_position_is_not_used(self):
        # Page 2 of Khyber Pakhtunkhwa carries two horizontal offsets at once,
        # 37 rows at one and 12 at the other, so the same row shifted bodily
        # sideways must read the same.
        shifted = " ".join(
            f"{t}[{x0 - 20:.0f}-{x1 - 20:.0f}]"
            for x0, x1, t in self.row(self.ABBOTTABAD))
        self.assertEqual(self.read(self.ABBOTTABAD), self.read(shifted))

    def test_every_row_of_both_provinces_reconciles(self):
        for spec in self.KP + self.PUNJAB + [self.ABBOTTABAD]:
            got = self.read(spec)
            total = got.pop("TOTAL")
            self.assertEqual(sum(got.values()), total, spec[:40])

    def test_abbottabad_reads_as_the_page_prints_it(self):
        got = self.read(self.ABBOTTABAD)
        self.assertEqual(got["TOTAL"], 1_397_587)
        self.assertEqual(got["Muslim"], 1_391_394)
        self.assertEqual(got["Parsi"], 6)

    def test_a_row_with_the_wrong_number_of_cells_is_refused(self):
        # Refused rather than padded or truncated: guessing which end to trim
        # is how a district ends up with another district's religions while
        # every total still adds up.
        with self.assertRaises(SystemExit) as caught:
            self.pk.values(self.row("40,641,120[146-177] 951[356-366]"),
                           "test", "ABBOTTABAD")
        self.assertIn("2 cells where the table has 9", str(caught.exception))

    def reconciling(self):
        counts = [2_133_005, 0, 13_286, 457, 175, 44, 7, 69, 115]
        counts[1] = counts[0] - sum(counts[2:])
        return dict(zip(self.pk.COLUMNS, counts))

    def province(self, total):
        return [total] + [0] * (len(self.pk.COLUMNS) - 1)

    def test_a_district_that_reconciles_passes(self):
        self.pk.check("Punjab", {"ATTOCK": self.reconciling()},
                      self.province(2_133_005))

    def test_a_column_read_one_place_to_the_left_is_refused(self):
        shifted = self.reconciling()
        shifted["TOTAL"], shifted["Muslim"] = 0, shifted["TOTAL"]
        with self.assertRaises(SystemExit) as caught:
            self.pk.check("Punjab", {"ATTOCK": shifted}, self.province(1))
        self.assertIn("no total", str(caught.exception))

    def test_religions_that_do_not_add_up_are_refused(self):
        wrong = self.reconciling()
        wrong["Christian"] += 50_000
        with self.assertRaises(SystemExit) as caught:
            self.pk.check("Punjab", {"ATTOCK": wrong}, self.province(1))
        self.assertIn("religions sum to", str(caught.exception))

    def test_districts_that_do_not_add_up_to_their_province_are_refused(self):
        # The dangerous case, because it is not a wrong number anywhere: a
        # district this reader never noticed is a hole, and every other check
        # passes over it in silence. Khyber Pakhtunkhwa read 34 districts that
        # each reconciled perfectly and were 825,377 people short.
        with self.assertRaises(SystemExit) as caught:
            self.pk.check("Khyber Pakhtunkhwa", {"ATTOCK": self.reconciling()},
                          self.province(2_133_005 + 825_377))
        self.assertIn("+825,377", str(caught.exception))

    def test_a_unit_that_is_not_called_a_district_is_still_a_unit(self):
        # Khyber Pakhtunkhwa's thirty-sixth is "MALAKAND PROTECTED AREA", and
        # it went missing without producing one wrong figure: 825,377 people,
        # 34 districts that each reconciled, and nothing to notice.
        self.assertEqual(
            self.pk.DISTRICT.match("MALAKAND PROTECTED AREA").group(1),
            "MALAKAND")
        self.assertEqual(
            self.pk.DISTRICT.match("ABBOTTABAD DISTRICT").group(1),
            "ABBOTTABAD")
        self.assertIsNone(self.pk.DISTRICT.match("ABBOTTABAD TEHSIL"))

    def test_a_province_with_no_row_of_its_own_is_refused(self):
        # Without it nothing says whether the districts read are all of them.
        with self.assertRaises(SystemExit) as caught:
            self.pk.check("Punjab", {"ATTOCK": self.reconciling()}, [])
        self.assertIn("no province row", str(caught.exception))

    def cell(self, total):
        return dict(zip(self.pk.COLUMNS,
                        [total, total - 3, 1, 1, 0, 0, 1, 0, 0]))

    def test_districts_sharing_one_shape_are_summed(self):
        # geoBoundaries draws one Chitral where the census counts two. Summed,
        # because matching either half to the whole shape puts a fraction of
        # the people on all of it.
        found = {"LOWER CHITRAL": self.cell(318_234),
                 "UPPER CHITRAL": self.cell(195_161)}
        assembled = self.pk.merge("Khyber Pakhtunkhwa", found)
        self.assertEqual(set(found), {"CHITRAL"})
        self.assertEqual(found["CHITRAL"]["TOTAL"], 513_395)
        self.assertEqual(assembled["CHITRAL"],
                         ("LOWER CHITRAL", "UPPER CHITRAL"))

    def test_summing_only_some_of_the_parts_is_refused(self):
        # The dangerous case: it would put a fraction of the people on the
        # whole shape and look entirely normal.
        with self.assertRaises(SystemExit) as caught:
            self.pk.merge("Khyber Pakhtunkhwa",
                          {"LOWER CHITRAL": self.cell(318_234)})
        self.assertIn("only LOWER CHITRAL were read", str(caught.exception))

    def test_a_whole_that_is_also_printed_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            self.pk.merge("Khyber Pakhtunkhwa",
                          {"CHITRAL": self.cell(1), "LOWER CHITRAL": self.cell(1),
                           "UPPER CHITRAL": self.cell(1)})
        self.assertIn("counted twice", str(caught.exception))

    def test_karachis_seven_districts_are_one_shape(self):
        found = {part: self.cell(1_000_000)
                 for part in self.pk.MERGED["KARACHI"]}
        self.pk.merge("Sindh", found)
        self.assertEqual(found["KARACHI"]["TOTAL"], 7_000_000)

    def test_a_renamed_district_is_declared_not_inferred(self):
        # Nothing infers "Nawabshah" from "Shaheed Benazirabad": the district
        # was renamed and the two share no word.
        self.assertEqual(self.pk.ALIASES["Shaheed Benazirabad"], ("Nawabshah",))

    def test_the_four_provinces_are_required_and_the_territories_are_not(self):
        # Azad Jammu and Kashmir and Gilgit-Baltistan are enumerated apart from
        # the census proper, so their absence is a fact about what Pakistan
        # publishes. The four provinces are 240 of its 241 million people.
        required = {slug for slug, (_n, req, _u) in self.pk.PROVINCES.items() if req}
        self.assertEqual(required, {"kp", "punjab", "sindh", "balochistan"})


class BangladeshZila(unittest.TestCase):
    """Two sheets that have to agree to the person, and one that does not.

    Barguna's figures are real, off the published workbook.
    """

    BARGUNA = {
        "name": "Barguna", "population": 1_010_531, "hijra": 70,
        "counts": {"Muslim": 937_495, "Hindu": 69_481, "Christian": 252,
                   "Buddhist": 3_185, "Other religion": 48},
        "sexed": {"Muslim": (457_588, 479_907), "Hindu": (34_436, 35_045),
                  "Christian": (117, 135), "Buddhist": (2_564, 621),
                  "Other religion": (33, 15)},
    }

    def setUp(self):
        from scripts.fetch_census import bangladesh
        self.bd = bangladesh

    def row(self, **changes):
        row = {k: (dict(v) if isinstance(v, dict) else v)
               for k, v in self.BARGUNA.items()}
        row.update(changes)
        return row

    def test_the_published_figures_pass(self):
        self.bd.check([self.row()])

    def test_the_religions_plus_the_hijra_are_the_population_exactly(self):
        # Two separate sheets agreeing to the person. 1,010,461 classified by
        # religion, 70 hijra whom the religion table does not classify, and a
        # published 1,010,531.
        classified = sum(self.BARGUNA["counts"].values())
        self.assertEqual(classified, 1_010_461)
        self.assertEqual(classified + self.BARGUNA["hijra"],
                         self.BARGUNA["population"])

    def test_a_religion_total_must_match_its_own_sexes(self):
        # The sheet states each figure twice, and the two agreeing is what
        # makes the column headings trustworthy rather than assumed.
        counts = dict(self.BARGUNA["counts"], Muslim=900_000)
        with self.assertRaises(SystemExit) as caught:
            self.bd.check([self.row(counts=counts)])
        self.assertIn("by sex", str(caught.exception))

    def test_one_person_out_is_refused(self):
        # Exact, not approximate. A tolerance wide enough to admit a hijra
        # count is wide enough to hide the merged sheet's transpositions.
        with self.assertRaises(SystemExit) as caught:
            self.bd.check([self.row(population=1_010_532)])
        self.assertIn("against a published", str(caught.exception))

    def test_another_districts_population_is_refused(self):
        # What the merged sheet actually does: Cumilla carries Cox's Bazar's
        # population, and every religion in it still adds up by sex.
        with self.assertRaises(SystemExit) as caught:
            self.bd.check([self.row(population=6_212_216)])
        self.assertIn("against a published 6,212,216", str(caught.exception))

    def test_a_column_is_found_by_a_prefix_when_it_is_unique(self):
        row = {"Population_Total": 1_010_531, "Population_Hijra": 70,
               "Population_rural_Total": 779_670, "Population_rural_Male": 381_325}
        self.assertEqual(self.bd.pick(row, "Population_Hijra"), 70)
        self.assertEqual(self.bd.pick(row, "Population_Tot"), 1_010_531)

    def test_an_ambiguous_prefix_is_refused_rather_than_taking_the_first(self):
        row = {"Population_rural_Total": 779_670, "Population_rural_Male": 381_325}
        with self.assertRaises(SystemExit) as caught:
            self.bd.pick(row, "Population_rural")
        self.assertIn("matches 2 columns", str(caught.exception))

    def test_the_shares_are_of_what_the_table_classifies(self):
        counts = self.BARGUNA["counts"]
        got = {g["group"]: g["pct"]
               for g in self.bd.shares(counts, total=sum(counts.values()))}
        self.assertEqual(got["Muslim"], 92.8)
        self.assertEqual(got["Hindu"], 6.9)

    def test_the_sheet_name_is_matched_with_its_leading_space_ignored(self):
        class Book:
            sheetnames = [" Population by Religion, Sex",
                          " Population by Sex, Dist & Loca"]
            def __getitem__(self, name):
                return name
        self.assertEqual(self.bd.sheet(Book(), self.bd.RELIGION_SHEET),
                         " Population by Religion, Sex")

    def test_a_missing_sheet_names_what_the_workbook_has(self):
        class Book:
            sheetnames = ["Merged_All_Table"]
            def __getitem__(self, name):
                return name
        with self.assertRaises(SystemExit) as caught:
            self.bd.sheet(Book(), self.bd.RELIGION_SHEET)
        self.assertIn("Merged_All_Table", str(caught.exception))

    def test_the_merged_sheet_is_not_read(self):
        # It flattens the forty-two sheets and transposes at least three
        # districts' figures while their geocodes stay correct.
        source = pathlib.Path(
            ROOT / "scripts" / "fetch_census" / "bangladesh.py").read_text()
        body = source.split('"""', 2)[2]
        self.assertNotIn("Merged_All_Table", body)

    def test_the_respelled_districts_are_declared(self):
        # Bangladesh respelled several districts in English in 2018 and the
        # boundary file still carries the older forms. "Nawabganj" and
        # "Chapainababganj" share no word, so nothing infers it.
        self.assertEqual(self.bd.ALIASES["Chattogram"], ("Chittagong",))
        self.assertIn("Nawabganj", self.bd.ALIASES["Chapainababganj"])
        self.assertEqual(len(self.bd.ALIASES), 8)

    def test_the_note_says_whose_shares_these_are(self):
        self.assertIn("hijra", self.bd.NOTE)
        self.assertIn("male and female", self.bd.NOTE)


class RollUpVintage(unittest.TestCase):
    """Two figures of different dates differ; that is not the same as a fault.

    The population gate is a proxy for "are these all the children". It refuses
    a set that falls short. But a census and a later estimate of the same
    territory are the same people counted at different times, and the gap
    between them is growth: Bangladesh's divisions carry 2011 figures and its
    districts the 2022 census, so the children exceed their parents by a tenth
    and every division was refused.
    """

    def kid(self, count, year=2022, group="Muslim"):
        return {"religion": [{"group": group, "pct": 100.0, "count": count}],
                "population": {"value": count, "year": year}}

    def test_the_same_year_gets_the_base_tolerance(self):
        self.assertEqual(be.allowance(2022, 2022, 100.0, 110.0),
                         be.ROLLUP_TOLERANCE)

    def test_children_newer_and_larger_are_allowed_to_have_grown(self):
        # Bangladesh: 2011 parents, 2022 children, about a tenth larger.
        self.assertGreater(be.allowance(2011, 2022, 100.0, 110.0), 0.15)

    def test_children_older_and_smaller_are_allowed_to_have_grown_since(self):
        # The other direction: a 2022 census under a 2025 estimate.
        self.assertGreater(be.allowance(2025, 2022, 100.0, 95.0),
                           be.ROLLUP_TOLERANCE)

    def test_a_difference_pointing_the_wrong_way_gets_no_allowance(self):
        # Children below an older parent is shrinkage, which is exactly what a
        # missing child looks like.
        self.assertEqual(be.allowance(2011, 2022, 100.0, 90.0),
                         be.ROLLUP_TOLERANCE)
        self.assertEqual(be.allowance(2025, 2022, 100.0, 110.0),
                         be.ROLLUP_TOLERANCE)

    def test_the_allowance_is_capped(self):
        # Wales' children exceed its parent by 166%, which is two different
        # things being counted, and no gap of dates excuses it.
        self.assertLessEqual(be.allowance(1900, 2022, 100.0, 999.0),
                             be.ROLLUP_TOLERANCE + be.ROLLUP_DRIFT_CAP)
        parent = {"population": {"value": 1_168_000, "year": 2011}}
        why = be.roll_up_field(parent, [self.kid(3_107_513)], "religion")
        self.assertIn("children sum to", why)

    def test_the_set_is_read_by_its_commonest_year_not_its_newest(self):
        # New Zealand's authorities are 2023 but for the Chatham Islands, whose
        # population this very function had rebuilt from its children and
        # stamped 2025. Read as 2025 the direction inverted and the country was
        # refused.
        kids = [self.kid(100, 2023) for _ in range(16)] + [self.kid(100, 2025)]
        self.assertEqual(be.common_year(kids), 2023)

    def test_a_parent_without_a_population_is_filled_when_the_country_is_whole(self):
        # Chittagong and Rajshahi publish no population at all. Every one of
        # Bangladesh's 64 districts joins, so the shapes partition the country
        # and these are certainly all of the division's children.
        parent = {}
        self.assertIsNone(be.roll_up_field(parent, [self.kid(1_000)], "religion",
                                           whole_country=True))
        self.assertEqual(parent["religion"][0]["group"], "Muslim")
        self.assertIn("every division at this level", parent["religion_note"])

    def test_a_parent_without_a_population_is_refused_when_it_is_not(self):
        why = be.roll_up_field({}, [self.kid(1_000)], "religion")
        self.assertIn("no published population", why)

    def test_a_disagreeing_parent_is_overridden_only_when_the_country_is_whole(self):
        # Dhaka carries a 2011 population of 49,729,000 and lost Mymensingh out
        # of it in 2015, so its 44,215,759 people in 2022 are not a shortfall.
        dhaka = {"population": {"value": 49_729_000, "year": 2011}}
        self.assertIsNone(be.roll_up_field(dhaka, [self.kid(44_215_759)],
                                           "religion", whole_country=True))
        self.assertIn("disagrees with that by", dhaka["religion_note"])
        # The same numbers without complete coverage stay refused.
        why = be.roll_up_field({"population": {"value": 49_729_000, "year": 2011}},
                               [self.kid(44_215_759)], "religion")
        self.assertIn("children sum to", why)

    def test_a_filled_parent_takes_its_children_population_and_says_what_it_replaced(self):
        parent = {"population": {"value": 8_325_666, "year": 2011}}
        be.roll_up_field(parent, [self.kid(9_100_104)], "religion",
                         whole_country=True)
        self.assertEqual(parent["population"]["value"], 9_100_104)
        self.assertEqual(parent["population"]["year"], 2022)
        self.assertIn("8,325,666", parent["population_note"])

    def test_a_same_year_published_population_gives_way_to_the_children(self):
        # Finland's nineteen regions total 5,652,881 for 2025 from Statistics
        # Finland's register; the country carried 5,550,449 for 2025 from the
        # Factbook. An itemised count against a general estimate, with the
        # language shares already taken from the register.
        parent = {"population": {"value": 5_550_449, "year": 2025}}
        be.roll_up_field(parent, [self.kid(5_652_881, 2025)], "religion",
                         whole_country=True)
        self.assertEqual(parent["population"]["value"], 5_652_881)
        self.assertIn("5,550,449", parent["population_note"])

    def test_a_population_the_children_agree_with_is_left_alone(self):
        # Ladakh's Leh and Kargil sum to exactly the 274,289 Wikidata gives it.
        # Restamping that as "summed from 2 divisions" trades a named source
        # for a derivation and tells a reader less about the same figure.
        parent = {"population": {"value": 274_289, "year": 2011,
                                 "source": "Wikidata (CC0)"}}
        be.roll_up_field(parent, [self.kid(274_289, 2011)], "religion",
                         whole_country=True)
        self.assertEqual(parent["population"]["source"], "Wikidata (CC0)")
        self.assertNotIn("population_note", parent)

    def test_a_newer_published_population_is_not_replaced(self):
        parent = {"population": {"value": 9_500_000, "year": 2025},
                  "religion": None}
        be.roll_up_field(parent, [self.kid(9_100_104)], "religion",
                         whole_country=True)
        self.assertEqual(parent["population"]["value"], 9_500_000)
        self.assertNotIn("population_note", parent)


class ProbeLinksPaths(unittest.TestCase):
    """Both ways of reading a page, because only one of them was exercised.

    --find was added with an `import re` inside its own branch, which made the
    name local to the whole function and left the anchor scan -- every call
    that does not pass --find -- raising UnboundLocalError. It reached main and
    broke the first probe run after it.
    """

    HTML = '<a href="/a.pdf">Report</a><a href="/b.csv">Data</a>'

    def setUp(self):
        import argparse
        sys.path.insert(0, str(ROOT / "scripts"))
        import probe_links
        self.probe = probe_links
        self.real_fetch = probe_links.fetch
        probe_links.fetch = lambda url, accept="", timeout=25: self.HTML
        self.args = argparse.Namespace(accept="", timeout=25, find="", raw=0,
                                       match="pdf", limit=10, check=0, head=False)

    def tearDown(self):
        self.probe.fetch = self.real_fetch

    def out(self):
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.probe.page("https://example.org/", self.args)
        return buf.getvalue()

    def test_the_anchor_scan_runs_without_find(self):
        printed = self.out()
        self.assertIn("1 matching link(s)", printed)
        self.assertIn("https://example.org/a.pdf", printed)

    def test_find_prints_only_what_matched(self):
        self.args.find = "[a-z]+[.]pdf"
        printed = self.out()
        self.assertIn("1 distinct match(es)", printed)
        self.assertIn("a.pdf", printed)
        self.assertNotIn("matching link(s)", printed)


class ProbePdfPages(unittest.TestCase):
    """Naming pages, because searching for a term cannot read a long table.

    Table 2.4 of the South African census release puts "Coloured" in its header
    and nine provinces beneath it; every excerpt centred on the term stopped
    three provinces short, and the context that would have reached them applied
    to twenty other pages too.
    """

    TEXT = "alpha one\n\fbeta two\n\fgamma three\n"

    def setUp(self):
        import argparse
        sys.path.insert(0, str(ROOT / "scripts"))
        import probe_pdf
        self.probe = probe_pdf
        self.path = Path(tempfile.mkdtemp()) / "pages.txt"
        self.path.write_text(self.TEXT, encoding="utf-8")
        self.args = ["scripts/probe_pdf.py", str(self.path)]
        self.parse = argparse
        del argparse

    def out(self, *extra):
        import contextlib, io
        buf = io.StringIO()
        argv = sys.argv
        sys.argv = self.args + list(extra)
        try:
            # stderr: common.log writes there, so the probe's whole report is
            # on that stream and redirecting stdout captures nothing.
            with contextlib.redirect_stderr(buf):
                self.probe.main()
        finally:
            sys.argv = argv
        return buf.getvalue()

    def test_named_pages_print_whole(self):
        printed = self.out("--pages", "2,3")
        self.assertIn("beta two", printed)
        self.assertIn("gamma three", printed)
        self.assertNotIn("alpha one", printed)

    def test_a_page_past_the_end_is_said_rather_than_guessed(self):
        printed = self.out("--pages", "9")
        self.assertIn("outside a document of 3 pages", printed)

    def test_terms_still_work_when_no_pages_are_named(self):
        printed = self.out("--terms", "beta", "--contents", "0")
        self.assertIn("1 mention", printed)
        self.assertIn("beta two", printed)


class SouthAfricaRows(unittest.TestCase):
    """Reading a table whose thousands separator is a space.

    Every row below is copied from the release: five population groups and a
    total, printed as a stream of digit fragments with nothing marking where
    one number ends. The arithmetic is what settles it, and Gauteng is the row
    that shows why nothing else would -- its coloured column is printed
    "44 3857", with the space in the wrong place, so no rule about gaps or
    digit counts reads it as 443,857.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from fetch_census import south_africa
        self.za = south_africa

    def test_a_row_of_fragments_resolves_to_one_reading(self):
        row = "2 884 511 3 124 757 84 363 1 217 807 115 235 7 426 673".split()
        self.assertEqual(
            self.za.counted(row, "Western Cape"),
            [2884511, 3124757, 84363, 1217807, 115235, 7426673])

    def test_a_misplaced_space_is_still_read(self):
        row = "12 765 312 44 3857 329 736 1 509 800 35 890 15 084 595".split()
        self.assertEqual(self.za.counted(row, "Gauteng")[1], 443857)

    def test_a_three_digit_value_is_not_swallowed_by_its_neighbour(self):
        # Mpumalanga's "Other" is 440, the same shape as a thousands group.
        row = "4 898 063 32 100 25 882 185 731 440 5 142 216".split()
        self.assertEqual(self.za.counted(row, "Mpumalanga"),
                         [4898063, 32100, 25882, 185731, 440, 5142216])

    def test_a_row_that_does_not_add_up_is_refused(self):
        # The release's own national row: its five groups come to 61,988,316
        # against a printed 61,988,314, so it is read only under the stated
        # allowance and refused without one.
        row = ("50 486 856 5 052 349 1 697 506 4 504 252 247 353 "
               "61 988 314").split()
        with self.assertRaises(SystemExit) as caught:
            self.za.counted(row, "South Africa")
        self.assertIn("adding up to the total", str(caught.exception))
        self.assertEqual(
            self.za.counted(row, "South Africa",
                            slack=self.za.NATIONAL_SLACK)[0], 50486856)

    def test_a_leading_zero_is_not_a_number_of_its_own(self):
        self.assertIsNone(self.za.value(["063"]))
        self.assertEqual(self.za.value(["4", "898", "063"]), 4898063)
        self.assertEqual(self.za.value(["0"]), 0)

    def test_a_province_split_over_two_lines_still_matches(self):
        self.assertIn(self.za.flat("KwaZulu-Natal"),
                      self.za.flat("KwaZulu- Natal"))


class SouthAfricaTables(unittest.TestCase):
    """The four readers, against the rows the release actually prints."""

    # Table 2.2's shape: a name, four censuses, and a percentage change after
    # each of the last three. Only the 2022 column is read, and it is the run
    # of digits between the second and third percentages -- so the earlier
    # censuses here are filler and the 2022 figures are the published ones.
    LATEST = {
        "Western Cape": "7 433 019", "Eastern Cape": "7 230 204",
        "Northern Cape": "1 355 946", "Free State": "2 964 412",
        "KwaZulu-Natal": "12 423 907", "North West": "3 804 548",
        "Gauteng": "15 099 422", "Mpumalanga": "5 143 324",
        "Limpopo": "6 572 721", "South Africa": "62 027 503",
    }

    def population_rows(self, national=None):
        rows = [["Province", "1996", "2001", "2011", "2022"]]
        for name, latest in self.LATEST.items():
            if name == "South Africa" and national:
                latest = national
            rows.append(name.split() + "1 000 000 1 100 000".split() + ["10,0"]
                        + "1 200 000".split() + ["9,1"] + latest.split()
                        + ["8,3"])
        return rows

    SHARES = [
        ["Language", "WC", "EC", "NC", "FS", "KZN", "NW", "GP", "MP", "LP", "SA"],
        ["Afrikaans", "41,2", "9,6", "54,6", "10,3", "1,0", "5,2", "7,7",
         "3,2", "2,3", "10,6"],
        ["Khoi,", "Nama", "&"],
        ["San", "languages", "58,8", "90,4", "45,4", "89,7", "99,0", "94,8",
         "92,3", "96,8", "97,7", "89,4"],
        ["Total", "100,0", "100,0", "100,0", "100,0", "100,0", "100,0",
         "100,0", "100,0", "100,0", "100,0"],
    ]

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from fetch_census import south_africa
        self.za = south_africa

    def quiet(self, call, *args):
        import contextlib, io
        with contextlib.redirect_stderr(io.StringIO()):
            return call(*args)

    def test_the_2022_column_is_the_one_between_the_last_two_percentages(self):
        found = self.quiet(self.za.population, self.population_rows())
        self.assertEqual(found["Western Cape"], 7433019)
        self.assertEqual(found["KwaZulu-Natal"], 12423907)
        self.assertEqual(found["South Africa"], 62027503)

    def test_provinces_that_miss_the_national_total_are_refused(self):
        rows = self.population_rows(national="62 027 999")
        with self.assertRaises(SystemExit) as caught:
            self.quiet(self.za.population, rows)
        self.assertIn("against a printed South Africa of 62,027,999",
                      str(caught.exception))

    def test_a_wrapped_category_name_joins_up(self):
        found = self.quiet(self.za.percentages, self.SHARES, "Table 2.9:",
                           "language")
        self.assertEqual(sorted(found["WC"]),
                         ["Afrikaans", "Khoi, Nama & San languages"])
        self.assertEqual(found["KZN"]["Afrikaans"], 1.0)

    def test_a_column_that_does_not_reach_its_printed_total_is_refused(self):
        rows = [list(r) for r in self.SHARES]
        rows[1][1] = "31,2"                       # ten points missing from WC
        with self.assertRaises(SystemExit) as caught:
            self.quiet(self.za.percentages, rows, "Table 2.9:", "language")
        self.assertIn("against a printed 100.0%", str(caught.exception))

    def test_a_contents_entry_is_passed_over_for_the_real_table(self):
        contents = [["Table", "2.9:", "Percentage", "distribution", "......", "23"]]
        document = [contents, [["Table", "2.9:", "Language"]] + self.SHARES]
        found = self.quiet(
            self.za.read, document, "Table 2.9:",
            lambda rows: self.za.percentages(rows, "Table 2.9:", "language"))
        self.assertEqual(found["SA"]["Afrikaans"], 10.6)


class SouthAfricaLabels(unittest.TestCase):
    """The census's names and the Factbook's, for the same country."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import canonical_groups
        self.cg = canonical_groups

    def name(self, field, label):
        return self.cg.lookup(field).get(self.cg.key(label))

    def test_the_census_spelling_and_the_factbook_compound_agree(self):
        for label in ("IsiZulu", "isiZulu", "Zulu", "isiZulu or Zulu"):
            self.assertEqual(self.name("language", label), "isiZulu")
        self.assertEqual(self.name("ethnicity", "Colored"), "Coloured")
        self.assertEqual(self.name("ethnicity", "Coloured"), "Coloured")

    def test_two_ambiguous_bare_names_are_left_alone(self):
        # Northern Ndebele (Zimbabwe) and Southern Ndebele (South Africa) are
        # different languages, and "Sotho" is used for both Sesotho and Sepedi.
        self.assertIsNone(self.name("language", "Ndebele"))
        self.assertIsNone(self.name("language", "Sotho"))

    def test_the_boundary_files_misspelling_is_declared(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from fetch_census import south_africa
        # geoBoundaries writes "Nothern Cape". Without the alias the province
        # matches no shape at all.
        self.assertEqual(south_africa.ALIASES["Northern Cape"],
                         ("Nothern Cape",))

    def test_a_published_zero_is_kept(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from fetch_census import south_africa
        # 0,0 in these tables means "below 0.05%", which is a measurement.
        out = south_africa.composition({"Judaism": 0.0, "Islam": 1.9}, {})
        self.assertEqual([r["group"] for r in out], ["Islam", "Judaism"])

    def test_the_traditional_african_column_folds_with_the_rest(self):
        self.assertEqual(self.name("religion", "Traditional African"),
                         "Folk and traditional religion")
        for label in ("Atheism", "Agnosticism", "No religious affiliation"):
            self.assertEqual(self.name("religion", label), "No religion")


class GapReasons(unittest.TestCase):
    """Countries where naming a script would be a false promise.

    The hint panel renders its text as a command to run. For a country that
    never published the figures, that says the gap is this build's doing --
    so those carry a reason instead, and never both.
    """

    def annotate(self, iso3):
        entity = {}
        be.mark_disputed_or_hint(entity, iso3)
        return entity

    def test_a_gap_country_gets_a_reason_and_no_command(self):
        entity = self.annotate("VNM")
        self.assertIn("by province", entity["gap_reason"])
        self.assertNotIn("adapter_hint", entity)

    def test_an_ordinary_country_gets_a_command_and_no_reason(self):
        entity = self.annotate("USA")
        self.assertIn("us_acs", entity["adapter_hint"])
        self.assertNotIn("gap_reason", entity)

    def test_a_country_with_an_adapter_keeps_its_command(self):
        self.assertIn("us_acs", be.adapter_hint("USA"))
        self.assertNotIn("USA", be.ADAPTER_GAPS)

    def test_the_three_documented_gaps_carry_a_reason(self):
        for iso3 in ("IDN", "VNM", "THA"):
            self.assertIn(iso3, be.ADAPTER_GAPS)
            self.assertGreater(len(be.ADAPTER_GAPS[iso3]), 40)

    def test_a_gap_reason_is_prose_rather_than_a_command(self):
        # A hint is rendered inside <code> and run; a reason is not.
        for reason in be.ADAPTER_GAPS.values():
            self.assertNotIn("python", reason)
            self.assertNotIn("scripts.", reason)

    def test_the_two_never_apply_to_the_same_country(self):
        self.assertFalse(set(be.ADAPTER_GAPS) & set(be.ADAPTER_HINTS))


class SiteFreshness(unittest.TestCase):
    """Whether the map still reflects the adapter output beside it.

    South Africa's provinces were correct in data/processed and absent from
    site/data for a week, because an adapter run and a site build are separate
    acts and nothing compared them. These cover the comparison that now does.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import check_site_fresh
        self.check = check_site_fresh
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "a.json").write_text('["a"]', encoding="utf-8")
        (self.dir / "b.json").write_text('["b"]', encoding="utf-8")
        self.files = ["a.json", "b.json"]
        self.stamp = {f: self.check.digest(self.dir / f) for f in self.files}

    def test_an_unchanged_tree_is_current(self):
        self.assertEqual(self.check.compare(self.stamp, self.dir, self.files),
                         ([], [], []))

    def test_an_adapter_that_never_reached_the_map_is_named(self):
        stamp = {"a.json": self.stamp["a.json"]}       # b built after the site
        added, changed, removed = self.check.compare(stamp, self.dir, self.files)
        self.assertEqual(added, ["b.json"])
        self.assertEqual((changed, removed), ([], []))

    def test_a_rerun_adapter_is_named(self):
        (self.dir / "a.json").write_text('["a","more"]', encoding="utf-8")
        added, changed, removed = self.check.compare(self.stamp, self.dir, self.files)
        self.assertEqual(changed, ["a.json"])
        self.assertEqual((added, removed), ([], []))

    def test_a_stamp_from_before_this_check_is_not_called_current(self):
        # None means "unknown", which must not be reported as "unchanged":
        # asserting freshness on no evidence is the bug this guards against.
        self.assertEqual(self.check.compare(None, self.dir, self.files),
                         ([], [], []))

    def test_the_build_stamps_every_adapter_file_it_can_see(self):
        stamped = be.adapter_digests()
        for filename in ("south_africa_province.json", "pakistan_district.json"):
            if (be.PROCESSED / filename).exists():
                self.assertIn(filename, stamped)
                self.assertEqual(len(stamped[filename]), 12)


class BoundaryMisspellings(unittest.TestCase):
    """geoBoundaries names that are simply wrong, corrected by declaration."""

    def test_the_declared_misspelling_is_corrected(self):
        self.assertEqual(common.respell("Nothern Cape", "ZAF"), "Northern Cape")

    def test_a_correction_cannot_reach_another_country(self):
        self.assertEqual(common.respell("Nothern Cape", "USA"), "Nothern Cape")
        self.assertEqual(common.respell("Nothern Cape"), "Nothern Cape")

    def test_an_unlisted_name_is_untouched(self):
        for name in ("Western Cape", "Eastern Cape", "Limpopo"):
            self.assertEqual(common.respell(name, "ZAF"), name)

    def test_every_correction_normalises_to_something_different(self):
        """A declaration that norm() folds away anyway is doing nothing.

        norm() drops accents, case, spacing and the administrative words, so a
        correction that only changes those was never needed -- the join already
        matched. Each entry here has to survive that folding to be worth its
        line, which is also the check that catches an entry added against the
        wrong spelling: Arez keeps its z through norm(), and "Arês" does not
        become "Arez" by any rule.
        """
        for (group, wrong), right in common.MISSPELLED.items():
            with self.subTest(group=group, wrong=wrong):
                self.assertNotEqual(
                    be.norm(wrong), be.norm(right),
                    f"{group} {wrong!r} -> {right!r} survives norm() unchanged, "
                    f"so the join matched it already and the declaration is "
                    f"either redundant or aimed at the wrong name")

    def test_guangdong_is_reachable_from_the_shape_that_names_a_city(self):
        """126 million people, behind the wrong name.

        geoBoundaries draws China's most populous province as "Guangzhou
        Province". Guangzhou is its capital city. Nothing that says Guangdong
        -- Wikidata included -- can reach a shape that says Guangzhou, so the
        province carried a polygon and no figures at all.
        """
        self.assertEqual(be.norm(common.respell("Guangzhou Province", "CHN")),
                         be.norm("Guangdong"))


class UscbReader(unittest.TestCase):
    """The reader for the U.S. Census Bureau's subnational census series.

    Every one of these covers something that went wrong against a real
    workbook, in the order it went wrong.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from fetch_census import uscb
        self.uscb = uscb

    # -- the sentinel -----------------------------------------------------
    def test_a_negative_is_not_a_count_of_people(self):
        # Ethiopia writes -999 where a figure is unavailable, undocumented,
        # and openpyxl hands it over as an ordinary number. Taken at face
        # value it would have put a negative population on the map.
        self.assertIsNone(self.uscb.number(-999))
        self.assertIsNone(self.uscb.number(-1))
        self.assertEqual(self.uscb.number(0), 0.0)
        self.assertEqual(self.uscb.number("1,234"), 1234.0)

    def test_a_boolean_is_not_a_count_either(self):
        # bool is a subclass of int; True would otherwise read as one person.
        self.assertIsNone(self.uscb.number(True))

    # -- the shape of a sheet, asked rather than declared ------------------
    SEXED = (["AREA_NAME", "ADM_LEVEL", "RLG_ORDX_B", "RLG_ORDX_F",
              "RLG_ORDX_M", "RLG_ISL_B", "RLG_ISL_F", "RLG_ISL_M"],
             ["Area", "Administrative level", "Orthodox, both sexes",
              "Orthodox, females", "Orthodox, males", "Islamic, both sexes",
              "Islamic, females", "Islamic, males"])
    FLAT = (["AREA_NAME", "ADM_LEVEL", "RLG_HPOP", "RLG_NONE", "RLG_RC"],
            ["Area", "Administrative level", "Household population",
             "Non-religious", "Roman Catholic"])

    def test_a_sexed_sheet_is_recognised_and_a_flat_one_is_not(self):
        self.assertTrue(self.uscb.sexed(self.SEXED[0]))
        self.assertFalse(self.uscb.sexed(self.FLAT[0]))

    def test_the_group_label_drops_the_sex_it_was_measured_by(self):
        names, aliases = self.SEXED
        found = self.uscb.groups(names, aliases, None, True)
        self.assertEqual(sorted(found.values()), ["Islamic", "Orthodox"])

    def test_groups_are_whatever_is_not_geography(self):
        # The first version carried a per-topic column prefix and was wrong on
        # its second file: Ethiopia's ethnic-group columns are not "ETH_".
        names = ["AREA_NAME", "ADM_LEVEL", "ETHN_AFAR", "XYZ_OROMO"]
        aliases = ["Area", "Administrative level", "Affar", "Oromo"]
        found = self.uscb.groups(names, aliases, None, False)
        self.assertEqual(sorted(found.values()), ["Affar", "Oromo"])

    def test_the_denominator_is_found_by_its_alias(self):
        names, aliases = self.FLAT
        total = self.uscb.denominator(names, aliases)
        self.assertEqual(aliases[total], "Household population")
        self.assertNotIn(total, self.uscb.groups(names, aliases, total, False))

    def test_a_sheet_with_no_denominator_says_so(self):
        # Ethiopia publishes none; returning an index anyway would promote a
        # group column to stand in for everyone.
        self.assertIsNone(self.uscb.denominator(*self.SEXED))

    # -- a shortfall is judged by its shape -------------------------------
    def areas(self, shortfalls):
        # Keyed by (parent, name), as the reader keys them: Ethiopia has a
        # North Shewa in two different regions, and a name alone let one
        # overwrite the other.
        return {("REGION", f"area{i}"): {"published": 1_000_000.0,
                                         "summed": 1_000_000.0 * (1 - s),
                                         "level": 1, "parent": "REGION",
                                         "name": f"area{i}", "counts": {}}
                for i, s in enumerate(shortfalls)}

    def quiet(self, call, *args):
        import contextlib, io
        with contextlib.redirect_stderr(io.StringIO()):
            return call(*args)

    def test_a_few_areas_falling_short_are_kept_and_named(self):
        # MIMAROPA and its two Mindoro provinces, 0.6% to 1.3% short of the
        # census's own household population: a hole in the source, and the map
        # draws the remainder as unaccounted rather than normalising it away.
        topic = self.uscb.Topic("Ethnicity", "ethnicity")
        areas = self.areas([0.013, 0.012, 0.006] + [0.0] * 128)
        self.quiet(self.uscb.check_total, self.uscb.PHILIPPINES, topic, areas)

    def test_one_area_far_short_is_refused(self):
        topic = self.uscb.Topic("Ethnicity", "ethnicity")
        with self.assertRaises(SystemExit) as caught:
            self.quiet(self.uscb.check_total, self.uscb.PHILIPPINES, topic,
                       self.areas([0.30] + [0.0] * 130))
        self.assertIn("too much to be a suppressed group", str(caught.exception))

    def test_a_shortfall_everywhere_is_refused_as_a_misreading(self):
        topic = self.uscb.Topic("Ethnicity", "ethnicity")
        with self.assertRaises(SystemExit) as caught:
            self.quiet(self.uscb.check_total, self.uscb.PHILIPPINES, topic,
                       self.areas([0.02] * 100))
        self.assertIn("misunderstood the sheet", str(caught.exception))

    def test_two_zones_of_one_name_are_kept_apart(self):
        # geoBoundaries calls them North Shewa(R3) and North Shewa(R4); the
        # census calls both North Shewa. Keying on the name alone wrote 92
        # Ethiopian zones where the sheet lists 93.
        keys = {("AMHARA", "NORTH SHEWA"), ("OROMIYA", "NORTH SHEWA")}
        self.assertEqual(len(keys), 2)

    def test_the_declared_aliases_reach_the_boundary_names(self):
        # Most Ethiopian regions reach the map only by declaration: folding
        # diacritics does not turn "Sumalē" into "Somali".
        for census, boundary in (("Oromīya", "Oromia"), ("Sumalē", "Somali"),
                                 ("Yedebub Bihēroch Bihēreseboch Na Hizboch",
                                  "SNNPR")):
            self.assertIn(boundary, self.uscb.ETHIOPIA.aliases[census])
        for census, boundary in (("National Capital Region", "NCR"),
                                 ("Davao De Oro", "Compostela Valley")):
            self.assertIn(boundary, self.uscb.PHILIPPINES.aliases[census])

    # -- what the boundary file has no shape for --------------------------
    def test_a_folded_city_is_declared_rather_than_left_to_the_matcher(self):
        # "Cebu City" and "Province Of Cebu" both normalise to "cebu" and both
        # matched outright, so the collision pass read them as one place listed
        # twice and let the last one win: a city of 964,000 wearing a
        # province's figures, or the reverse, with nothing on the map to show
        # it. Three of those were live (Cebu, Iloilo, Quezon City).
        for parent, city in (("Central Visayas", "Cebu City"),
                             ("Western Visayas", "Iloilo City"),
                             ("National Capital Region", "Quezon")):
            self.assertIn((parent, city), self.uscb.PHILIPPINES.no_shape)

    def test_a_city_with_a_shape_of_its_own_is_not_declared_away(self):
        # geoBoundaries draws the City of Manila (as NCR's first district) and
        # Basketo, so declaring them absent would suppress a real match.
        self.assertNotIn(("National Capital Region", "Manila"),
                         self.uscb.PHILIPPINES.no_shape)
        self.assertFalse([p for p in self.uscb.ETHIOPIA.no_shape
                          if p[1].startswith("Basketo")])

    def test_a_province_the_boundary_file_merely_lacks_is_left_visible(self):
        # Sultan Kudarat is a province with no CGAZ shape at all and Sidama a
        # region created after CGAZ's Ethiopian vintage. Those are upstream
        # omissions a later release could fix; declaring them here would turn
        # into a lie that suppresses the match when it does.
        self.assertNotIn(("Soccsksargen", "Sultan Kudarat"),
                         self.uscb.PHILIPPINES.no_shape)
        self.assertFalse([p for p in self.uscb.ETHIOPIA.no_shape
                          if p[1].startswith("Sīdama")])

    def test_a_parent_is_addressed_with_its_own_aliases(self):
        # Every Ethiopian region with a macron in it is spelled differently by
        # the boundary file, so without the parent's aliases no zone could be
        # scoped inside its region -- and the two North Shewas, which only
        # their regions tell apart, were both refused as ambiguous.
        self.assertIn("Amhara", self.uscb.ETHIOPIA.aliases["Āmara"])
        self.assertIn("Oromia", self.uscb.ETHIOPIA.aliases["Oromīya"])

    def test_every_declared_absence_names_a_parent(self):
        # A name alone is not an address: the Philippines has a Quezon that is
        # a province and a Quezon that is a city 130 km away, and only one of
        # them is folded into another shape.
        for country in self.uscb.COUNTRIES.values():
            for pair in country.no_shape:
                self.assertEqual(len(pair), 2)
                self.assertTrue(pair[0] and pair[1], pair)

    # -- finding the workbook ---------------------------------------------
    def hdx(self, resources):
        return {"success": True, "result": {"resources": resources}}

    def resolved(self, body):
        """workbook_url with HDX's answer supplied rather than fetched."""
        real = self.uscb.http_json
        self.uscb.http_json = lambda url, **kw: body
        try:
            return self.uscb.workbook_url("some-dataset-id")
        finally:
            self.uscb.http_json = real

    def test_the_resource_is_resolved_not_pinned(self):
        # A resource id is a snapshot. HDX issues a new one when the Bureau
        # publishes a new extraction and leaves the old serving last year's
        # figures until it 404s -- the failure mode being that nothing fails.
        url = self.resolved(self.hdx([
            {"name": "phl_admgz_adm_itos.gdb.zip", "url": "http://x/gdb"},
            {"name": "philippines_uscb_202402.xlsx", "url": "http://x/book"},
        ]))
        self.assertEqual(url, "http://x/book")

    def test_the_dataset_is_named_because_it_cannot_be_derived(self):
        # cod-ps-<iso3> is HDX's population collection, a different thing:
        # UNFPA and OCHA projections, carrying no USCB workbook for any of the
        # 146 countries in it. Deriving the dataset from the ISO3 code found
        # nothing for the two countries that demonstrably have tables.
        for country in self.uscb.COUNTRIES.values():
            self.assertTrue(country.dataset)
            self.assertNotIn("cod-ps", country.dataset)
        self.assertEqual(self.uscb.dataset_url("abc-123"),
                         "https://data.humdata.org/dataset/abc-123")

    def test_two_extractions_take_the_later_one(self):
        url = self.resolved(self.hdx([
            {"name": "philippines_uscb_202402.xlsx", "url": "http://x/old"},
            {"name": "philippines_uscb_202511.xlsx", "url": "http://x/new"},
        ]))
        self.assertEqual(url, "http://x/new")

    def test_a_dataset_with_no_workbook_says_what_it_has(self):
        with self.assertRaises(SystemExit) as caught:
            self.resolved(self.hdx([{"name": "phl_pop_adm1.csv",
                                     "url": "http://x/csv"}]))
        self.assertIn("no USCB workbook", str(caught.exception))
        self.assertIn("phl_pop_adm1.csv", str(caught.exception))

    def test_a_workbook_must_be_a_workbook(self):
        # "uscb" appears in the documentation PDF's name too.
        with self.assertRaises(SystemExit):
            self.resolved(self.hdx([{"name": "philippines_uscb_notes.pdf",
                                     "url": "http://x/pdf"}]))

    # -- a topic's provenance is its own ----------------------------------
    def test_a_topic_may_override_the_country_year_and_source(self):
        # Burma's Age-Sex sheet is the 2014 census; its Ethnicity sheet is the
        # Department of Population's 2018 Township Profiles, reference date
        # 2017, because the 2014 census's ethnicity tables were withheld.
        eth = next(t for t in self.uscb.MYANMAR.topics if t.field == "ethnicity")
        self.assertEqual(self.uscb.MYANMAR.year, 2014)
        self.assertEqual(eth.year, 2017)
        self.assertIn("Township Profiles", eth.source)
        self.assertIn("never released", eth.note)

    def test_a_topic_without_its_own_provenance_takes_the_country_s(self):
        for country in self.uscb.COUNTRIES.values():
            for topic in country.topics:
                self.assertTrue(topic.year or country.year)
                self.assertTrue(topic.source or country.source)

    # -- building a blank level out of the one below -----------------------
    class Book:
        """Just enough of an openpyxl workbook for read() to walk."""

        def __init__(self, rows):
            self.sheetnames = ["Language"]
            self._rows = rows

        def __getitem__(self, name):
            rows = self._rows

            class Sheet:
                @staticmethod
                def iter_rows(values_only=True):
                    return iter(rows)
            return Sheet()

    SUMMED = [
        ["AREA_NAME", "ADM1_NAME", "ADM_LEVEL", "LNG_A", "LNG_B", "LNG_TPOP"],
        ["Area", "Oblast", "Level", "Ukrainian", "Russian", "Total Population"],
        ["UKRAINE", None, 0, 90, 60, 150],
        ["KYIV OBLAST", None, 1, None, None, None],
        ["ALPHA RAYON", "KYIV OBLAST", 2, 40, 10, 50],
        ["BETA RAYON", "KYIV OBLAST", 2, 30, 20, 55],
        ["GAMMA RAYON", "KYIV OBLAST", 2, None, None, 20],
    ]

    def summed(self):
        country = self.uscb.Country(
            iso3="UKR", name="Ukraine", year=2001, source="s", licence="l",
            dataset="d", out="o.json", levels={1: "admin1", 2: "admin2"},
            topics=(self.uscb.Topic("Language", "language"),), note="n",
            sum_into=1, refuse_area=1.0, refuse_share=1.0)
        book = self.Book(self.SUMMED)
        return self.quiet(self.uscb.read, book, country,
                          country.topics[0]) if hasattr(self, "quiet") \
            else self.uscb.read(book, country, country.topics[0])

    def test_a_blank_parent_is_built_from_its_children(self):
        out = self.summed()
        oblast = out[("", "KYIV OBLAST")]
        self.assertEqual(oblast["counts"], {"Ukrainian": 70, "Russian": 30})
        self.assertEqual(oblast["level"], 1)

    def test_the_built_denominator_counts_children_that_have_no_figures(self):
        # Gamma publishes a population and no languages. Leaving it out of the
        # denominator would hide the hole; including it draws the remainder as
        # an unaccounted share, which is what it is.
        oblast = self.summed()[("", "KYIV OBLAST")]
        self.assertEqual(oblast["published"], 125)
        self.assertEqual(oblast["summed"], 100)

    def test_the_children_are_still_their_own_records(self):
        out = self.summed()
        self.assertIn(("KYIV OBLAST", "ALPHA RAYON"), out)
        self.assertIn(("KYIV OBLAST", "BETA RAYON"), out)

    def test_an_area_publishing_its_own_figures_is_not_overwritten(self):
        # Kyiv city and Sevastopol carry theirs directly and must keep them.
        rows = [r[:] for r in self.SUMMED]
        rows[3] = ["KYIV OBLAST", None, 1, 5, 5, 999]
        country = self.uscb.Country(
            iso3="UKR", name="Ukraine", year=2001, source="s", licence="l",
            dataset="d", out="o.json", levels={1: "admin1", 2: "admin2"},
            topics=(self.uscb.Topic("Language", "language"),), note="n",
            sum_into=1, refuse_area=1.0, refuse_share=1.0)
        out = self.uscb.read(self.Book(rows), country, country.topics[0])
        self.assertEqual(out[("", "KYIV OBLAST")]["published"], 999)

    def test_a_level_can_feed_its_parent_without_being_published(self):
        # Ukraine's rayons are the only place the figures exist and the only
        # level that does not join, so they are summed and not emitted.
        country = self.uscb.Country(
            iso3="UKR", name="Ukraine", year=2001, source="s", licence="l",
            dataset="d", out="o.json", levels={1: "admin1"},
            topics=(self.uscb.Topic("Language", "language"),), note="n",
            sum_into=1, refuse_area=1.0, refuse_share=1.0)
        out = self.uscb.read(self.Book(self.SUMMED), country,
                             country.topics[0])
        self.assertEqual(list(out), [("", "KYIV OBLAST")])
        self.assertEqual(out[("", "KYIV OBLAST")]["counts"],
                         {"Ukrainian": 70, "Russian": 30})

    # -- a third level whose parent is the first ---------------------------
    THIRD = [
        ["AREA_NAME", "ADM1_NAME", "ADM2_NAME", "ADM_LEVEL",
         "LNG_A", "LNG_TPOP"],
        ["Area", "Province", "Division", "Level", "Urdu", "Total Population"],
        ["PAKISTAN", None, None, 0, 90, 100],
        ["SINDH", None, None, 1, 40, 50],
        ["KARACHI DIVISION", "SINDH", None, 2, 25, 30],
        ["KARACHI EAST DISTRICT", "SINDH", "KARACHI DIVISION", 3, 12, 15],
    ]

    def third(self, levels):
        country = self.uscb.Country(
            iso3="PAK", name="Pakistan", year=2017, source="s", licence="l",
            dataset="d", out="o.json", levels=levels,
            topics=(self.uscb.Topic("Language", "language", prefix="LNG_"),),
            note="n", refuse_area=1.0, refuse_share=1.0)
        return self.uscb.read(self.Book(self.THIRD), country,
                              country.topics[0])

    def test_a_third_level_row_is_scoped_by_the_first_not_the_second(self):
        # Pakistan's districts sit at level 3 with 36 divisions at level 2,
        # and geoBoundaries draws the districts directly under the provinces.
        # Taking the level above would scope a district inside a division no
        # boundary file has -- a parent that can never match.
        out = self.third({1: "admin1", 3: "admin2"})
        self.assertIn(("SINDH", "KARACHI EAST DISTRICT"), out)
        self.assertNotIn(("KARACHI DIVISION", "KARACHI EAST DISTRICT"), out)

    def test_the_second_level_still_takes_the_first_as_its_parent(self):
        # The generalisation must leave every country already reading level 2
        # exactly where it was.
        out = self.third({1: "admin1", 2: "admin2"})
        self.assertIn(("SINDH", "KARACHI DIVISION"), out)

    def test_a_first_order_row_has_no_parent_of_its_own(self):
        out = self.third({1: "admin1", 3: "admin2"})
        self.assertIn(("", "SINDH"), out)

    def test_pakistan_reads_districts_and_not_divisions(self):
        self.assertEqual(self.uscb.COUNTRIES["PAK"].levels,
                         {1: "admin1", 3: "admin2"})

    def test_pakistan_does_not_republish_the_religion_it_already_has(self):
        # scripts/fetch_census/pakistan.py publishes religion from the same
        # census table. Two files claiming one shape with figures that
        # disagree at all would send both to a gap under the agreement rule.
        fields = [t.field for t in self.uscb.COUNTRIES["PAK"].topics]
        self.assertEqual(fields, ["language"])

    def test_ukraine_publishes_oblasts_only(self):
        self.assertEqual(self.uscb.UKRAINE.levels, {1: "admin1"})

    def test_ukraine_builds_its_oblasts_by_addition(self):
        # The 2001 language table is published by rayon and the 25 oblast rows
        # above them are blank, so the first order carried nothing at all.
        self.assertIn("UKR", self.uscb.COUNTRIES)
        self.assertEqual(self.uscb.UKRAINE.sum_into, 1)

    def test_only_ukraine_sums_a_level(self):
        summing = [c.iso3 for c in self.uscb.COUNTRIES.values()
                   if c.sum_into is not None]
        self.assertEqual(summing, ["UKR"])

    def test_ukraine_reads_the_flat_language_sheet(self):
        # Language comes from the flat sheet. Nationality-Language is the
        # cross-tabulation of the two, 1,619 columns, and only its first
        # block -- the whole population of each nationality, NL_ETH_* -- is
        # read, by prefix; the cells of the cross-tabulation are not a field
        # this map has.
        topics = {t.field: t for t in self.uscb.UKRAINE.topics}
        self.assertEqual(topics["language"].sheet, "Language")
        self.assertEqual(topics["language"].prefix, "")
        self.assertEqual(topics["ethnicity"].sheet, "Nationality-Language")
        self.assertEqual(topics["ethnicity"].prefix, "NL_ETH_")
        self.assertEqual(topics["ethnicity"].label_prefix, "Ethnicity/nationality,")
        self.assertTrue(self.uscb.mine("NL_ETH_UKR", "NL_ETH_"))
        self.assertFalse(self.uscb.mine("NL_RUS_UKR", "NL_ETH_"))

    def test_every_ukrainian_oblast_is_declared(self):
        # The Bureau romanises from Ukrainian and geoBoundaries uses English
        # exonyms, so all 27 need declaring: "Cherkas'ka Oblast'" and
        # "Cherkasy Oblast" share no word norm() leaves standing.
        self.assertEqual(len(self.uscb.UKRAINE.aliases), 27)
        self.assertIn("Kyiv", self.uscb.UKRAINE.aliases["Misto Kyyiv"])
        self.assertIn("Kyiv Oblast",
                      self.uscb.UKRAINE.aliases["Kyyivs’Ka Oblast’"])

    def test_myanmar_states_need_no_aliases_because_norm_drops_state(self):
        # The census writes "KACHIN STATE" and geoBoundaries "Kachin", so the
        # 15 first-order areas need nothing declared. Only the districts do,
        # where both sides romanise from Burmese and neither is wrong.
        self.assertEqual(be.norm("Kachin State"), be.norm("Kachin"))
        for state in ("Kachin State", "Shan State", "Ayeyarwady"):
            self.assertNotIn(state, self.uscb.MYANMAR.aliases)
        self.assertIn("Hakha", self.uscb.MYANMAR.aliases["Haka"])

    # -- one sheet, two topics --------------------------------------------
    HEADER = [["AREA_NAME", "ADM_LEVEL", "ETH_A", "ETH_B", "ETH_TPOP",
               "RLG_A", "RLG_B", "RLG_TPOP"],
              ["Area", "Level", "Bamar", "Karen", "Total population, ethnicity",
               "Buddhist", "Christian", "Total population, religion"],
              ["BURMA", 0, 70, 30, 100, 90, 20, 110]]

    def test_a_prefix_splits_a_sheet_that_holds_two_questions(self):
        # Burma's sheet is called "Ethnicity" and carries religion beside it.
        # Read together the shares came to 3.05 times the population.
        names, aliases = self.uscb.columns(self.HEADER)
        eth = self.uscb.groups(names, aliases,
                               self.uscb.denominator(names, aliases, "ETH_"),
                               False, "ETH_")
        rlg = self.uscb.groups(names, aliases,
                               self.uscb.denominator(names, aliases, "RLG_"),
                               False, "RLG_")
        self.assertEqual(sorted(eth.values()), ["Bamar", "Karen"])
        self.assertEqual(sorted(rlg.values()), ["Buddhist", "Christian"])

    def test_each_topic_takes_its_own_denominator(self):
        # Two different populations in one sheet: 47.8 million of ethnicity
        # against 49.0 million of religion.
        names, aliases = self.uscb.columns(self.HEADER)
        self.assertEqual(names[self.uscb.denominator(names, aliases, "ETH_")],
                         "ETH_TPOP")
        self.assertEqual(names[self.uscb.denominator(names, aliases, "RLG_")],
                         "RLG_TPOP")

    def test_no_prefix_still_means_everything_that_is_not_geography(self):
        # Which is what keeps Ethiopia working: its ethnic-group columns are
        # not named "ETH_", so a prefix cannot be the general rule.
        names, aliases = self.uscb.columns(self.HEADER)
        found = self.uscb.groups(names, aliases, None, False)
        self.assertEqual(len(found), 6)

    def test_a_prefix_that_matches_nothing_is_refused_by_name(self):
        names, aliases = self.uscb.columns(self.HEADER)
        self.assertEqual(self.uscb.groups(names, aliases, None, False, "LNG_"),
                         {})

    def test_myanmar_reads_both_questions_out_of_the_one_sheet(self):
        sheets = {t.field: (t.sheet, t.prefix)
                  for t in self.uscb.MYANMAR.topics}
        self.assertEqual(sheets["ethnicity"], ("Ethnicity", "ETH_"))
        self.assertEqual(sheets["religion"], ("Ethnicity", "RLG_"))

    def test_ukraine_widens_only_the_bound_its_evidence_supports(self):
        # The size bound was widened to 8% on rayon evidence -- 105 of 663
        # short by up to 6.9%. Those rayons are no longer published, so it
        # went back. The worst oblast is 0.7% short against a 5% refusal.
        self.assertEqual(self.uscb.UKRAINE.refuse_area, self.uscb.REFUSE_AREA)
        self.assertGreater(self.uscb.UKRAINE.refuse_share,
                           self.uscb.REFUSE_SHARE)

    def test_a_widened_bound_is_a_claim_that_needs_its_evidence(self):
        # Ukraine is the only country that widens them, and the module's
        # defaults stay where they are for everyone else.
        self.assertEqual(self.uscb.REFUSE_AREA, 0.05)
        self.assertEqual(self.uscb.REFUSE_SHARE, 0.10)
        widened = [c.iso3 for c in self.uscb.COUNTRIES.values()
                   if c.refuse_area != self.uscb.REFUSE_AREA
                   or c.refuse_share != self.uscb.REFUSE_SHARE]
        self.assertEqual(widened, ["UKR"])

    def test_every_country_carries_its_own_census_year(self):
        # Ethiopia's tables are the 2007 census -- the last it completed -- and
        # the file's own 2023 extraction date must not stand in for it.
        self.assertEqual(self.uscb.ETHIOPIA.year, 2007)
        self.assertEqual(self.uscb.PHILIPPINES.year, 2020)
        for country in self.uscb.COUNTRIES.values():
            self.assertIn(str(country.year), country.note)


class AliasKeysAreNamesTheSourceUses(unittest.TestCase):
    """An alias keyed on a name no row carries is dead, and silently so.

    The keys are the *source's* spelling and the values geoBoundaries', which
    is easy to write backwards: the pairs are discovered by reading the two
    lists of leftovers side by side, and either column will look plausible as
    a key. A backwards alias raises nothing, matches nothing and leaves the
    gap exactly as it was -- the fix appears to be applied and is not.

    Pakistan's nine were written that way the first time. Its file names the
    areas "BATAGRAM DISTRICT", the reader titles that to "Batagram District",
    and keys reading "Batagram" reached none of them.

    So every alias key must be a name that country's own committed output
    actually carries, which is checkable here because the output is in git.
    """

    def test_every_alias_key_names_a_row_in_the_committed_output(self):
        # uscb.py imports from ._shared, so it has to arrive as part of its
        # package rather than as a loose module on sys.path.
        import importlib
        sys.path.insert(0, str(ROOT / "scripts"))
        uscb = importlib.import_module("fetch_census.uscb")

        checked = 0
        for country in uscb.COUNTRIES.values():
            if not country.aliases:
                continue
            path = ROOT / "data" / "processed" / country.out
            if not path.exists():
                continue
            rows = json.loads(path.read_text())
            names = {row.get("name") for row in rows}
            names |= {row.get("parent_name") for row in rows}
            names.discard(None)
            for key in country.aliases:
                checked += 1
                self.assertIn(
                    key, names,
                    f"{country.iso3}: alias key {key!r} matches no row in "
                    f"{country.out}. The key is the source's own name for "
                    f"the area, not the boundary file's.")
        self.assertGreater(checked, 0, "no alias keys were checked")


class SurveyFiguresAreNotPopulationCounts(unittest.TestCase):
    """The two things the DRC's survey needed the reader to be able to say.

    Its sheet is the first here whose figures are not people. They are the
    31,755 heads of household the Enquête 1-2-3 reached, for a country of 119
    million, and the column holding that number is called "Sample size" --
    which denominator() cannot find, because it looks for the word
    "population" and this universe is not one.

    Both failures are silent. An unnamed denominator becomes a group, and
    since it is the sum of every other group it becomes the largest "tribe" in
    the country. A published count becomes a number in the same field as
    Pakistan's census counts, with nothing to say one is a sample.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import importlib
        self.uscb = importlib.import_module("fetch_census.uscb")

    def test_the_sample_size_is_the_universe_and_not_a_tribe(self):
        names = ["AREA_NAME", "ADM_LEVEL", "TRB_SSIZE", "TRB_NNB", "TRB_LUA"]
        aliases = ["Area", "Level", "Sample size", "Nande", "Luba-Lulua"]
        # Left to the alias search there is no denominator at all, so every
        # column including the sample size is read as a group.
        found = self.uscb.groups(
            names, aliases, self.uscb.denominator(names, aliases, "TRB_"),
            False, "TRB_")
        self.assertIn("Sample size", found.values())
        # Named outright, it is the total and the groups are the tribes.
        total = names.index("TRB_SSIZE")
        found = self.uscb.groups(names, aliases, total, False, "TRB_")
        self.assertNotIn("Sample size", found.values())
        self.assertEqual(sorted(found.values()), ["Luba-Lulua", "Nande"])

    def test_a_denominator_named_but_absent_is_refused_by_name(self):
        drc = self.uscb.COUNTRIES["COD"]
        self.assertTrue(all(t.denominator == "TRB_SSIZE" for t in drc.topics))

    def test_the_country_that_counts_households_publishes_no_count(self):
        drc = self.uscb.COUNTRIES["COD"]
        self.assertFalse(drc.counts_are_people)
        # Every other country here counts people and says so by default.
        others = [c.iso3 for c in self.uscb.COUNTRIES.values()
                  if c.iso3 != "COD"]
        self.assertTrue(others)
        for iso3 in others:
            self.assertTrue(self.uscb.COUNTRIES[iso3].counts_are_people, iso3)

    def test_the_drc_is_read_at_one_level_only(self):
        # 31,755 households over 26 provinces is about 1,200 each; over the
        # 164 districts the file also carries it is about 194, which is not a
        # basis for a published composition.
        self.assertEqual(self.uscb.COUNTRIES["COD"].levels, {1: "admin1"})

    def test_mali_shares_are_of_the_population_the_table_counts(self):
        # The columns sum to 11.1 million against a census of about 14.5, and
        # the source's own title says why: aged 6 and over. The note has to
        # carry that, because the shares cannot.
        note = self.uscb.COUNTRIES["MLI"].note
        self.assertIn("6 and over", note)
        self.assertIn("11,109,312", note)


class MatchingOnACodeRatherThanARomanisation(unittest.TestCase):
    """Russia is the first source whose names cannot be matched at all.

    Its sheets are Cyrillic, the boundary file is English, and norm() keeps
    Cyrillic as Cyrillic deliberately -- a transliteration invented in this
    code would be a guess about a name, and the guesses that look right are
    the dangerous ones. An ISO 3166-2 code is the one key both sides carry
    without anybody romanising anything.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import importlib
        self.ru = importlib.import_module("fetch_census.russia")

    def test_every_sheet_is_either_a_subject_or_skipped_for_a_reason(self):
        # 88 sheets: 83 subjects, 4 named skips, and the country's own row.
        self.assertEqual(len(self.ru.SUBJECTS), 83)
        self.assertEqual(len(self.ru.SKIP), 4)
        self.assertEqual(len(self.ru.SUBJECTS) + len(self.ru.SKIP) + 1, 88)
        for sheet, why in self.ru.SKIP.items():
            self.assertTrue(why, f"{sheet} is skipped without a reason")
            self.assertNotIn(sheet, self.ru.SUBJECTS)

    def test_the_overlapping_forms_are_the_ones_skipped(self):
        # Reading a combined subject beside its parts counts about four
        # million people twice, and nothing in the figures would show it.
        self.assertIn("Архангельская область", self.ru.SKIP)
        self.assertIn("Архангельская область без АО", self.ru.SUBJECTS)
        self.assertIn("Ненецкий автономный округ", self.ru.SUBJECTS)
        self.assertIn("Тюменская область", self.ru.SKIP)
        self.assertIn("Тюменская область без АО", self.ru.SUBJECTS)

    def test_crimea_and_sevastopol_are_not_published_from_this_source(self):
        # Ukraine's 2001 census already publishes these shapes on this map,
        # and geoBoundaries draws neither inside Russia.
        self.assertIn("Республика Крым", self.ru.SKIP)
        self.assertIn("г. Севастополь", self.ru.SKIP)

    def test_every_configured_code_is_one_a_shape_can_be_found_by(self):
        """Asked of Wikidata, which is where a shape's code comes from.

        Asking the built site file instead measures nothing: this adapter
        writes its own iso_3166_2 onto every shape it matches, so once the
        join works every shape has a code and the answer is 83 whatever
        Wikidata holds. That is what made the earlier version of this test
        pass while the join was producing one subject out of 83.
        """
        rows = json.loads(
            (ROOT / "data" / "processed" / "wikidata_admin1.json").read_text())
        codes = {r.get("iso_3166_2") for r in rows
                 if r.get("country") == "RUS"
                 and isinstance(r.get("iso_3166_2"), str)}
        missing = set(self.ru.SUBJECTS.values()) - codes
        self.assertFalse(
            missing, f"no Wikidata code for {sorted(missing)}, so those "
                     "subjects can only be reached by name")

    def test_the_join_reaches_every_subject(self):
        """The measurement the code pass exists for, on the built file.

        It read 1 of 83 for as long as the code index was built before any
        adapter row was merged -- the codes are not on the shapes, they
        arrive from Wikidata, and nothing had merged them yet. Cyrillic
        against English, 82 subjects landed nowhere, and the build reported
        success.
        """
        shapes = json.loads(
            (ROOT / "site" / "data" / "admin1" / "RUS.json").read_text())
        for field in ("ethnicity", "language"):
            joined = [s for s in shapes if isinstance(s.get(field), list)]
            self.assertEqual(
                len(joined), len(self.ru.SUBJECTS),
                f"{len(joined)} of {len(self.ru.SUBJECTS)} subjects carry "
                f"{field}; the rest read as a census that did not ask")

    def test_the_proficiency_table_is_not_the_one_read(self):
        # Table 5 is ВЛАДЕНИЕ ЯЗЫКАМИ -- which languages a person knows, of
        # which they may know several. Table 6 is РОДНОМУ ЯЗЫКУ, which
        # partitions. Reading 5 would publish a composition summing past 100%,
        # which is what Thailand's file was refused for.
        self.assertIn("tab6", self.ru.TABLE["language"])
        self.assertNotIn("tab5", "".join(self.ru.TABLE.values()))

    def test_a_group_name_stops_before_its_self_designations(self):
        self.assertEqual(self.ru.label("Аварцы"), "Аварцы")
        self.assertEqual(
            self.ru.label("Башкиры (башкирцы, башкорт, мин)"), "Башкиры")
        self.assertEqual(self.ru.label("   Андийцы  "), "Андийцы")
        self.assertEqual(self.ru.label(None), "")

    def test_the_group_level_is_the_commonest_indent_not_the_smallest(self):
        """Three readings of this, two of them wrong, both caught by the sums.

        Leading whitespace missed every real sub-group and fired on Русские in
        Воронежская область, dropping the largest group in a region of 2.2
        million and leaving the sheet at 13.55% of its published total.

        "Indented at all" was wrong the other way: Rosstat indents the whole
        list one level under "в том числе:", so Чукотский автономный округ read
        94 of 95 rows as nested and kept 446 people out of 47,044.

        A sheet has one row per ethnicity and a handful of sub-groups, so the
        commonest indent is the top of the list by construction.
        """
        # The shape of a real sheet: a shallow sibling, many groups one level
        # in, and two constituent peoples one level deeper again.
        rows = [("не указана", 446, 0),
                ("Русские", 1_881_129, 1),
                ("Украинцы", 44_000, 1),
                ("Аварцы", 594, 1),
                ("Андийцы", 1, 2),
                ("Ахвахцы", 3, 2)]
        kept = dict(self.ru.parents(rows))
        self.assertIn("Русские", kept)
        self.assertIn("Аварцы", kept)
        # The deeper rows are counted inside Аварцы already.
        self.assertNotIn("Андийцы", kept)
        self.assertNotIn("Ахвахцы", kept)
        # And the shallower row is not a member of the list at all. It is the
        # people who stated nothing, and the universe this reconciles against
        # is those who did state -- counting them took ХМАО to 135% of its own
        # published total.
        self.assertNotIn("не указана", kept)

    def test_the_indent_is_a_style_and_not_leading_whitespace(self):
        class Cell:
            def __init__(self, depth):
                self.alignment = type("A", (), {"indent": depth})()

        self.assertEqual(self.ru.indent(Cell(0)), 0)
        self.assertEqual(self.ru.indent(Cell(2)), 2)
        # A cell with no alignment at all is at the top level.
        self.assertEqual(self.ru.indent(object()), 0)
        # Whitespace in the value is not indentation and never was.
        self.assertEqual(self.ru.label("   Русские"), "Русские")

    def test_an_em_dash_is_absence_and_not_a_number(self):
        for absent in ("-", "–", "—", "", "   ", None):
            self.assertIsNone(self.ru.number(absent), repr(absent))
        self.assertEqual(self.ru.number("3 888 216"), 3888216.0)
        self.assertEqual(self.ru.number(4004809), 4004809.0)


class ASubjectPresentInOneTableAndAbsentFromAnother(unittest.TestCase):
    """Russia's two tables do not spell every subject the same way.

    Table 1 writes ХМАО and ЯНАО; table 6 writes them out in full. Read under
    their own names those sheets are unknown, and the two regions come out
    with ethnicity and no language -- which on the map is indistinguishable
    from a census that did not ask them the question.

    It passed the first completeness check because that check looked at one
    table. Two point three million people would have carried a silent gap.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import importlib
        self.ru = importlib.import_module("fetch_census.russia")

    def test_the_alternate_spellings_resolve_to_a_configured_subject(self):
        for spelling, canonical in self.ru.ALSO_KNOWN_AS.items():
            self.assertNotIn(spelling, self.ru.SUBJECTS,
                             f"{spelling} should be an alias, not a subject")
            self.assertIn(canonical, self.ru.SUBJECTS)

    def test_every_table_is_checked_and_present_is_not_enough(self):
        """Two ways to come out empty, and both must refuse rather than gap.

        A sheet can be missing, as ХМАО's was from the language table under
        that name. Or it can be present and yield nothing, as Ингушетия's was
        when its pivot-table key column shifted the labels one place right.
        Both read on the map as a census that did not ask the question.
        """
        source = (ROOT / "scripts" / "fetch_census" / "russia.py").read_text()
        body = source.split("def main(")[1]
        self.assertIn("for field in TABLE:", body)
        # Checked on the counts, not on the key being present.
        self.assertIn('.get("counts")', body)

    def test_the_label_and_count_columns_are_found_not_assumed(self):
        source = (ROOT / "scripts" / "fetch_census" / "russia.py").read_text()
        self.assertIn("def layout(", source)
        # Ингушетия and Красноярский край keep the pivot table's member keys
        # in column 0, so the label is in column 1 and the count in column 2.
        self.assertIn("at_name, at_value = where", source)
        self.assertNotIn("label(row[0].value)", source)


class AGroupTheSourceNamesWithoutAShare(unittest.TestCase):
    """The Factbook writes Mali's plurality language as "Bambara (official)".

    No figure, so the parser dropped the part -- and then presented the eleven
    remaining languages as Mali's whole language composition. They sum to
    70.9%, and the map showed a country in which the language half of it
    speaks did not appear at all. Our own regional data for the same 2009
    census puts Bambara at 51.8%.

    A dropped member is the worst of the three outcomes. A named member with
    a stated gap says what the source says; a wrong share would be visible;
    silence reads as though the question was never asked.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from common import parse_composition
        self.parse = parse_composition

    MALI = ("Bambara (official), French 17.2%, Peuhl/Foulfoulbe/Fulani 9.4%, "
            "Dogon 7.2%, Maraka/Soninke 6.4%, Malinke 5.6%, Sonrhai/Djerma "
            "5.6%, Minianka 4.3%, Tamacheq 3.5%, Senoufo 2.6%, Bobo 2.1%, "
            "other 6.3%, unspecified 0.7% (2009 est.)")

    def test_bambara_survives_with_its_share_recorded_as_a_gap(self):
        rows = self.parse(self.MALI)
        first = rows[0]
        self.assertEqual(first["group"], "Bambara")
        self.assertIsNone(first["pct"])
        self.assertEqual(first["pct_status"], "not_available")

    def test_the_members_that_do_have_shares_are_untouched(self):
        rows = self.parse(self.MALI)
        shares = {r["group"]: r["pct"] for r in rows if r["pct"] is not None}
        self.assertEqual(shares["French"], 17.2)
        self.assertEqual(shares["Dogon"], 7.2)
        self.assertEqual(len(shares), 12)

    def test_a_run_closed_by_or_or_including_is_one_name_not_several(self):
        """The comma split tears enumerated names apart.

        South Africa's "ancestral, tribal, animist, or other traditional
        African religions 5.4%" is one group whose share sits on the last
        fragment, and Botswana's bare "other" belongs to the "including
        Kgalagadi ... 7%" that follows it. Keeping the fragments would invent
        groups no census counted.
        """
        za = self.parse("Christian 86%, ancestral, tribal, animist, or other "
                        "traditional African religions 5.4%, Muslim 1.9%, "
                        "other 1.5%, nothing in particular 5.2% (2015 est.)")
        names = {r["group"] for r in za}
        for fragment in ("ancestral", "tribal", "animist"):
            self.assertNotIn(fragment, names)
        bw = self.parse("Tswana (or Setswana) 79%, Kalanga 11%, Basarwa 3%, "
                        "other, including Kgalagadi and people of European "
                        "ancestry 7%")
        self.assertNotIn("other", {r["group"] for r in bw})

    def test_commentary_and_counts_of_languages_are_not_groups(self):
        lr = self.parse("English 20% (official) and 27 indigenous languages, "
                        "including Liberian English variants")
        self.assertEqual([r["group"] for r in lr], ["English"])
        sb = self.parse("Melanesian pidgin (lingua franca in much of the "
                        "country), English (official but spoken by only "
                        "1%-2% of the population), 120 indigenous languages")
        self.assertNotIn("120 indigenous languages", {r["group"] for r in sb})

    def test_a_qualifier_left_behind_by_the_figure_is_not_a_group(self):
        """Cutting at the digit can leave only the word that introduced it."""
        td = self.parse("French (official) 12%, Arabic (official), Sara, "
                        "more than 120 languages")
        names = {r["group"] for r in td}
        self.assertNotIn("more than", names)
        self.assertIn("Arabic", names)

    def test_a_list_with_no_figures_at_all_is_left_to_its_own_path(self):
        """A name-only list is not a composition missing one member.

        parse_languages already renders those as the whole field being
        unquantified. Reading them here turned the EU's 24 official languages
        into 24 gaps in a chart nobody asked for.
        """
        self.assertIsNone(self.parse("Bulgarian, Croatian, Czech, Danish, "
                                     "Dutch, English, Estonian, Finnish"))


class OneLanguageUnderTwoSpellings(unittest.TestCase):
    """Mali is described by two sources at once, and they disagree on spelling.

    The Factbook covers the country, the 2009 census (via the US Census
    Bureau) covers the nine regions. Unmapped, each label keys on itself, so
    the world filter offered "Tamasheq" over nine Malian regions beside
    "Tamacheq" over Mali entire -- the same census, split in half.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import canonical_groups
        self.cg = canonical_groups
        self.table = canonical_groups.lookup("language")

    def canonical(self, label):
        return self.table.get(self.cg.key(label), label)

    def test_the_two_spellings_of_each_malian_language_agree(self):
        for census, factbook in (("Fula/fulfulbe", "Peuhl/Foulfoulbe/Fulani"),
                                 ("Maraka/soninke", "Maraka/Soninke"),
                                 ("Sonrai/djerma", "Sonrhai/Djerma"),
                                 ("Tamasheq", "Tamacheq"),
                                 ("Senufo", "Senoufo")):
            self.assertEqual(self.canonical(census), self.canonical(factbook),
                             f"{census} and {factbook} are one language")

    def test_the_central_african_republic_is_left_alone(self):
        """Fulah and Peulh look foldable into Fula, and are not.

        CAR's census lists Fulah, Fulata and Peulh as separate rows of the
        same prefecture, so its classification distinguishes them; folding
        would sum categories the source chose to keep apart.
        """
        for label in ("Fulah", "Fulata", "Peulh"):
            self.assertEqual(self.canonical(label), label)

    def test_no_record_carries_two_labels_that_now_fold_together(self):
        """Folding is only safe while no one record holds both spellings."""
        import json
        added = {"Fula", "Maraka/Soninke", "Sonrhai/Djerma", "Tamasheq",
                 "Senufo"}
        files = sorted((ROOT / "data" / "processed").glob("*.json"))
        admin0 = ROOT / "site" / "data" / "admin0.json"
        if admin0.exists():
            files.append(admin0)
        for path in files:
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(rows, list):
                continue
            for record in rows:
                if not isinstance(record, dict):
                    continue
                values = record.get("language")
                if not isinstance(values, list):
                    continue
                seen = {}
                for row in values:
                    label = self.cg.key(row.get("group", ""))
                    name = self.table.get(label, row.get("group", ""))
                    if name in added:
                        seen.setdefault(name, set()).add(label)
                for name, labels in seen.items():
                    self.assertEqual(
                        len(labels), 1,
                        f"{path.name}: {record.get('name')} carries "
                        f"{sorted(labels)}, which would be summed into {name}")


class TheCodeIndexIsBuiltAfterTheRowsThatCarryTheCodes(unittest.TestCase):
    """Russia joined 1 subject of 83, and every check passed.

    The ISO 3166-2 index was built from the entities at the top of the
    matching loop. But the codes are not on the shapes -- geoBoundaries
    publishes shapeName, shapeID, shapeGroup and shapeType and nothing else --
    they arrive from the Wikidata adapter, whose rows are in the same list and
    are merged only after that loop finishes. So the index was empty at
    exactly the moment it was read, all 83 Cyrillic sheet names fell through
    to a name pass against English shapes, and 82 landed nowhere.

    The one that matched did so on its declared alias, which is what made a
    total failure look like a near miss.
    """

    def setUp(self):
        self.source = (ROOT / "scripts" / "build_entities.py").read_text()

    def test_the_code_pass_runs_after_the_merge(self):
        # Everything before "resolve_collisions" is the name pass, and the
        # entities carry no adapter values until after it.
        before, _, after = self.source.partition("dropped, notes = resolve_collisions")
        self.assertNotIn("a1_by_code", before,
                         "the code index is read before any row is merged, "
                         "which is when it is empty")
        self.assertIn("a1_by_code", after)

    def test_a_code_that_is_not_a_string_is_not_looked_up(self):
        """Every METADATA field becomes {"status": ...} when a row lacks it.

        188 Wikidata admin-1 rows hold that dict in iso_3166_2, and a dict is
        unhashable: "code in a1_by_code" raised TypeError rather than missing.
        It killed the whole join, and because build_all.sh runs without
        set -e the refresh went on to report success.
        """
        self.assertIn('isinstance(code, str)', self.source)

    def test_two_rows_may_not_answer_one_question_about_one_shape(self):
        """But two rows answering different questions is the ordinary case.

        Guarding per shape rather than per field refuses every code match
        there is: Wikidata gives almost every shape in the world a
        population, so every shape looks answered already.
        """
        self.assertIn("def value_fields(", self.source)
        self.assertIn("clash = value_fields(row) & bearing[id(entity)]",
                      self.source)


class TheJoinMayNotFailQuietly(unittest.TestCase):
    """The refresh ran every adapter, crashed joining them, and said success.

    build_all.sh runs without "set -e" on purpose, so an adapter behind a
    blocked host can be skipped and still leave a working site. That also made
    a crash in the join survivable: site/data kept the previous build's
    contents, the script exited 0 from its closing echo, and the workflow
    opened a data PR. Russia's 83 subjects sat in data/processed and were
    absent from the map, with nothing anywhere saying so.
    """

    def test_the_join_step_is_fatal(self):
        script = (ROOT / "scripts" / "build_all.sh").read_text()
        self.assertNotIn("set -e\n", script,
                         "the soft-step design depends on set -e being off")
        line = [l for l in script.splitlines()
                if l.strip().startswith("python3 scripts/build_entities.py")]
        self.assertEqual(len(line), 1)
        self.assertTrue(line[0].strip().endswith("|| exit 1"),
                        f"the join must stop the build: {line[0]!r}")

    def test_the_join_is_not_a_soft_step(self):
        script = (ROOT / "scripts" / "build_all.sh").read_text()
        self.assertNotIn("soft python3 scripts/build_entities.py", script)


class ACodeIsEvidenceThatTwoRowsAreTwoPlaces(unittest.TestCase):
    """iso_3166_2 was added to METADATA, and METADATA is the exclusion list
    conflicting() uses to decide whether two rows landing on one shape are one
    place written twice or two different places.

    A Wikidata Q-id is excluded because it is unique per item, so counting it
    as a difference would make every rivalry look like a conflict. An ISO
    3166-2 code is the opposite: shared and standard, so two rows holding
    different codes are two different official units by definition. Excluding
    it deleted the strongest evidence the function had.

    What followed was the mis-match this project ranks below a gap. Lithuania's
    Alytus County had two rivals -- "Alytus City Municipality" (LT-02) and
    "Alytus District Municipality" (LT-03) -- which the collision pass used to
    refuse outright because nothing separated them. With the codes invisible
    they read as one place listed twice, the exemption applied, and the shape
    took the district municipality's 25,356 people in place of the county's
    hundred and forty thousand. Laos' Vientiane took Vientiane Province's
    388,833 over the prefecture's the same way. Nothing on the map would have
    said either number was wrong.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_entities
        self.be = build_entities

    def test_a_code_is_not_excluded_from_the_conflict_test(self):
        self.assertNotIn("iso_3166_2", self.be.METADATA)

    def test_two_rows_with_different_codes_conflict(self):
        rows = [{"name": "Alytus City Municipality", "iso_3166_2": "LT-02"},
                {"name": "Alytus District Municipality", "iso_3166_2": "LT-03"}]
        self.assertIn("iso_3166_2", self.be.conflicting(rows))

    def test_one_place_written_twice_still_does_not_conflict(self):
        """The case METADATA exists for must keep working.

        Wikidata carries both "Ancasti" and "Ancasti Department" with their own
        Q-ids; that is a duplicated source row, not a rivalry.
        """
        rows = [{"name": "Ancasti", "wikidata": "Q1", "id": "a"},
                {"name": "Ancasti Department", "wikidata": "Q2", "id": "b"}]
        self.assertEqual(self.be.conflicting(rows), [])

    def test_a_missing_code_is_a_gap_not_a_difference(self):
        rows = [{"name": "X", "iso_3166_2": "LT-03"},
                {"name": "X", "iso_3166_2": {"status": "not_available"}}]
        self.assertEqual(self.be.conflicting(rows), [])


class TheRussianCensusNamesItsGroupsInRussian(unittest.TestCase):
    """83 subjects read "Русские 90.2%", and the world filter had two answers.

    Rosstat publishes 147 nationalities and 176 native languages in Cyrillic.
    Left alone, every label keyed on itself, so "Русские" sat in the picker
    beside the "Russian" already there from Estonia, Latvia and Lithuania --
    the same people, counted by four censuses, split across two alphabets.

    Translating a *group* is allowed where romanising a *shape* was refused,
    and the difference is what a wrong entry can do. A guessed place name
    attaches real figures to the wrong region and nothing shows it. A group
    label is the name a bar carries, declared here one at a time rather than
    transliterated by rule. The one thing a wrong entry can still do is merge
    two peoples, because rows reaching one name are summed -- which is what
    the collision test below exists for.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import canonical_groups
        self.cg = canonical_groups
        self.rows = json.loads(
            (ROOT / "data" / "processed" / "russia_subject.json")
            .read_text(encoding="utf-8"))

    FIELDS = ("ethnicity", "language")

    def test_the_adapter_translates_rather_than_the_index(self):
        """The index alone was half a fix.

        canonical_groups reaches the group picker; the name a bar carries
        comes from the record. Folding the Cyrillic into the tables left the
        picker saying "Russian" while Tatarstan still read "Русские 40.3%".
        """
        source = (ROOT / "scripts" / "fetch_census" / "russia.py").read_text()
        self.assertIn("def englished(", source)
        self.assertIn("canonical_groups.translate_russian", source)

    def test_no_cyrillic_reaches_a_record(self):
        for record in self.rows:
            for field in self.FIELDS:
                for row in record.get(field) or []:
                    if not isinstance(row, dict):
                        continue
                    self.assertFalse(
                        any("Ѐ" <= ch <= "ӿ" for ch in row.get("group", "")),
                        f"{record.get('name')} {field}: {row.get('group')!r}")

    def test_an_untranslated_label_stops_the_run(self):
        """Rather than letting one Cyrillic row through a translated chart."""
        source = (ROOT / "scripts" / "fetch_census" / "russia.py").read_text()
        body = source.split("def englished(")[1].split("\ndef ")[0]
        self.assertIn("raise SystemExit", body)
        self.assertIn("if name is None:", body)

    def test_no_two_labels_in_one_record_become_one_group(self):
        """The only way a translation can change a figure.

        Two of a subject's own categories folding together would quietly add
        two of the census's bars into one. Checked on the translation table
        against the sheets, because the adapter's output has already applied
        it -- a collision there would show as a lost row, not a doubled one.
        """
        for field in self.FIELDS:
            table = self.cg.RUSSIAN[field]
            seen = {}
            for label, name in table.items():
                seen.setdefault(name, []).append(label)
            for name, labels in seen.items():
                self.assertEqual(
                    len(labels), 1,
                    f"{field}: {sorted(labels)} all become {name!r}, and any "
                    f"subject listing two of them would have them summed")

    def test_no_translation_lands_on_a_name_that_is_itself_an_alias(self):
        """Resolution is one pass, so a target must be a canonical name.

        Молдавский -> "Moldovan" was exactly this: "Moldovan" was an alias of
        "Romanian", so the label would have resolved half way and stood as its
        own group beside the one it was supposed to join.
        """
        for field in self.FIELDS:
            table = self.cg.lookup(field)
            for label, target in self.cg.RUSSIAN[field].items():
                onward = table.get(self.cg.key(target))
                self.assertIn(
                    onward, (None, target),
                    f"{field}: {label} -> {target!r}, an alias of {onward!r}")

    def test_moldovan_is_not_folded_into_romanian_as_a_language(self):
        """Rosstat lists both, in 80 of 83 subjects.

        A source naming two categories side by side in one record is
        distinguishing them, and folding would sum what it kept apart -- the
        same evidence that keeps the Central African Republic's Fulah, Fulata
        and Peulh separate. The fold cost nothing to drop: no source in this
        dataset has ever emitted "Moldovan" as a language label.
        """
        self.assertNotIn("Moldovan", self.cg.LANGUAGE["Romanian"])
        self.assertEqual(self.cg.RUSSIAN["language"]["Молдавский"], "Moldovan")
        self.assertEqual(self.cg.RUSSIAN["language"]["Румынский"], "Romanian")

    def test_the_table_holds_nothing_that_never_arrives(self):
        """An entry for a label the census does not publish is an unchecked
        guess. Both tables are sized by the sheets themselves."""
        self.assertEqual(len(self.cg.RUSSIAN["ethnicity"]), 147)
        self.assertEqual(len(self.cg.RUSSIAN["language"]), 176)


class AnAdapterWhoseOutputIsNeverReadJoinsNothing(unittest.TestCase):
    """Colombia's first build matched 0 of 1,155 areas and reported success.

    The adapter was right: 33 departments and 1,122 municipalities, every one
    reaching its published total, both levels reconciling exactly. The file
    was written to data/processed and then never opened, because
    build_entities reads a named list and colombia_department.json was not on
    it.

    Nothing failed. The country's log line even said "adapter rows matched
    1085", which was true and was the Wikidata rows -- the same shape as
    Russia's join reading one subject of 83, where a real number sat in the
    log beside no data on the map. A file that is written and not read is the
    quietest failure this pipeline has.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_entities
        self.be = build_entities

    def test_every_uscb_country_has_its_output_read(self):
        from fetch_census.uscb import COUNTRIES
        registered = set(self.be.ADAPTER_FILES)
        for iso3, country in sorted(COUNTRIES.items()):
            self.assertIn(
                country.out, registered,
                f"{iso3} writes {country.out} and build_entities never reads "
                f"it, so every area it carries joins nothing")

    def test_the_list_names_each_file_once(self):
        """A name twice is a file read twice, and the second read wins.

        This replaces a test that claimed to check the other direction --
        that every registered name is one some script writes -- and did not.
        It scanned all of scripts/ for quoted .json names, and ADAPTER_FILES
        lives in scripts/build_entities.py, so every entry matched its own
        definition and the test passed on any input.

        The direction is not checkable by grep in any case: adapters name
        their outputs with f-strings, ibge_sidra writing
        f"brazil_{args.level}.json", so a literal search finds nothing. Nor is
        "the file exists in data/processed" the invariant -- eurostat_nuts3,
        brazil_municipality, canada_province and canada_census_division are
        registered ahead of adapters that produce them on demand, and a
        forward registration is not a typo. What matters is the direction that
        broke Colombia, and the test above checks it.
        """
        self.assertEqual(len(self.be.ADAPTER_FILES),
                         len(set(self.be.ADAPTER_FILES)))


class ADistrictAdapterWithRepeatedNamesMustNameItsParent(unittest.TestCase):
    """The 525 Brazilian municipalities that were about to read as gaps.

    match_admin2 scopes a district row to the admin-1 it names, and matches
    country-wide only when the row names none -- where it then refuses any name
    that is not unique, because an unmatched row is a visible gap and a
    mis-matched one is invisible. That refusal is correct and is tested above.

    What this checks is the other side of the same contract: an adapter that
    knows which state a district is in has to say so, or it hands the join an
    ambiguity it invented itself. Brazil is the case that found it. Its first
    municipality run wrote 5,570 rows carrying no parent_name at all, and 242
    of its names are shared -- five Bom Jesus, five Sao Domingos, four Bonito --
    so 525 real places would have been correctly refused while the adapter held
    the answer in the same loop that dropped it.

    A parent_name that names nothing is no better than none, so the state has
    to resolve against the state file. Comparison is by norm(), which folds the
    accents CGAZ drops: IBGE's "Sao Paulo" and the boundary file's are one key.
    """

    def rows(self, name):
        path = ROOT / "data" / "processed" / name
        if not path.exists():
            self.skipTest(f"{name} has not been fetched")
        return json.loads(path.read_text())

    def test_brazils_shared_municipality_names_all_name_a_state(self):
        municipalities = self.rows("brazil_municipality.json")
        states = {be.norm(row["name"]) for row in self.rows("brazil_state.json")}
        self.assertEqual(len(states), 27, "Brazil has 27 federative units")

        counts = collections.Counter(be.norm(row["name"]) for row in municipalities)
        shared = [row for row in municipalities if counts[be.norm(row["name"])] > 1]
        self.assertGreater(len(shared), 0,
                           "no municipality name repeats -- the premise is gone")

        nameless = [row["name"] for row in shared if not row.get("parent_name")]
        self.assertEqual(
            nameless, [],
            f"{len(nameless)} municipalities share their name with another and "
            f"name no state, so the join can only refuse them: "
            f"{sorted(set(nameless))[:6]}")

        unresolvable = sorted({
            row["parent_name"] for row in shared
            if be.norm(row["parent_name"]) not in states})
        self.assertEqual(
            unresolvable, [],
            f"parent_name given but matching no federative unit: {unresolvable}")


class GermanysThreeCategoriesMustSumToItsPublishedTotal(unittest.TestCase):
    """What the Zensus reader may not quietly get wrong.

    Zensus 2022 publishes religion by Land in three categories -- Roman
    Catholic, Protestant, and everyone else -- because it is counting
    membership of a public-law corporation and only those two churches are
    ones. Being exhaustive is the whole basis for reading them as shares, so
    the reader checks them against the table's own Insgesamt row rather than
    letting shares() fall back on its own sum, which would divide by whatever
    survived and paper a dropped category over.

    The other half is the ffcsv shape. Every figure appears twice, once as a
    percentage and once as a count, and only the counts may be read: a share
    rebuilt from a rounded percentage is out by thousands of people and carries
    no sign that it was never counted. A reader that took the percentage rows
    would produce totals near 100 and look entirely plausible.
    """

    HEADER = ("statistics_code;statistics_label;time_code;time_label;time;"
              "1_variable_code;1_variable_label;1_variable_attribute_code;"
              "1_variable_attribute_label;2_variable_code;2_variable_label;"
              "2_variable_attribute_code;2_variable_attribute_label;value;"
              "value_unit;value_variable_code;value_variable_label")

    def setUp(self):
        import importlib
        sys.path.insert(0, str(ROOT / "scripts"))
        self.germany = importlib.import_module("fetch_census.germany")

    def row(self, code, name, group_code, label, value, unit):
        return (f"1000A;Bevolkerung;STAG;Stichtag;2022-05-15;GEOBL1;"
                f"Bundeslander;{code};{name};RELZG2;Religion;{group_code};"
                f"{label};{value};{unit};PRS018;Personen")

    def table(self, code, name, catholic, protestant, other, total=None):
        total = sum((catholic, protestant, other)) if total is None else total
        return "\n".join([
            self.HEADER,
            self.row(code, name, "REL-RK-OR", "Romisch-katholische", catholic, "Anzahl"),
            self.row(code, name, "REL-RK-OR", "Romisch-katholische", "31,5", "%"),
            self.row(code, name, "REL-EV-OR", "Evangelische", protestant, "Anzahl"),
            self.row(code, name, "REL-SONST-X", "Sonstige, keine", other, "Anzahl"),
            self.row(code, name, "", "Insgesamt", total, "Anzahl"),
            self.row(code, name, "", "Insgesamt", "100,0", "%"),
        ])

    def test_counts_are_read_and_percentage_twins_ignored(self):
        parsed = self.germany.parse(self.table("11", "Berlin", 250000, 509885, 2837114))
        self.assertEqual(set(parsed), {"11"})
        entry = parsed["11"]
        self.assertEqual(entry["name"], "Berlin")
        self.assertEqual(entry["total"], 3596999)
        self.assertEqual(sum(entry["counts"].values()), entry["total"])
        self.assertEqual(set(entry["counts"]),
                         {"Roman Catholic", "Protestant",
                          "Other, none, or not stated"})

    def test_a_category_this_build_has_never_seen_stops_the_run(self):
        text = "\n".join([
            self.HEADER,
            self.row("11", "Berlin", "REL-NEU", "Etwas Neues", 5, "Anzahl")])
        with self.assertRaises(SystemExit) as caught:
            self.germany.parse(text)
        self.assertIn("REL-NEU", str(caught.exception))

    def test_the_published_labels_are_declared_not_guessed(self):
        self.assertEqual(
            set(self.germany.RELIGION),
            {"REL-RK-OR", "REL-EV-OR", "REL-SONST-X"},
            "the three RELZG2 codes the table publishes")

    def test_the_regierungsbezirk_prefix_is_stripped_to_the_shape_name(self):
        """"Reg.-Bez. Arnsberg" is the source's prefix, not a misspelling.

        The GEORB1 cut labels every row "Reg.-Bez. X" where the boundary file
        says "X". That is a prefix one geography carries on all its rows, so it
        is stripped in the reader rather than declared in MISSPELLED, which is
        for names somebody got wrong. The Laender that stand as one region --
        Berlin, Saarland, Schleswig-Holstein -- carry no prefix and must come
        through untouched.
        """
        for label, want in (("Reg.-Bez. Arnsberg", "Arnsberg"),
                            ("Reg.-Bez. Gießen", "Gießen"),
                            # Saxony renamed its Regierungsbezirke, and Lower
                            # Saxony abolished its own in 2004 and reports
                            # statistische Regionen instead. Three prefixes for
                            # one variable, which is what the slash in
                            # "Regierungsbezirke/Statistische Regionen" means.
                            ("Direktionsbezirk Chemnitz", "Chemnitz"),
                            ("Statistische Region Weser-Ems", "Weser-Ems"),
                            ("Statistische Region Hannover", "Hannover"),
                            ("Berlin", "Berlin"),
                            ("Schleswig-Holstein", "Schleswig-Holstein")):
            self.assertEqual(self.germany.shape_name(label), want)

    def test_a_second_geography_is_read_from_the_same_table(self):
        """One table code, more than one geography, and the reader must say which.

        1000A-1018 is published cut by Bundeslaender, Regierungsbezirke,
        Landkreise and Gemeinden. parse() takes the region variable it is
        reading, so rows of another cut in the same file are skipped rather
        than counted -- asking for GEOBL1 and being handed GEORB1 rows would
        otherwise produce a composition for the wrong places.
        """
        laender = "\n".join([
            self.HEADER,
            self.row("11", "Berlin", "REL-RK-OR", "Katholisch", 250000, "Anzahl"),
        ])
        bezirke = laender.replace("GEOBL1", "GEORB1")
        self.assertEqual(set(self.germany.parse(laender, "GEOBL1")), {"11"})
        self.assertEqual(self.germany.parse(laender, "GEORB1"), {},
                         "GEOBL1 rows must not be read as a GEORB1 cut")
        self.assertEqual(set(self.germany.parse(bezirke, "GEORB1")), {"11"})
        self.assertEqual(self.germany.parse(bezirke, "GEOBL1"), {},
                         "GEORB1 rows must not be read as a GEOBL1 cut")

    def test_the_whole_land_regions_are_nine_and_exclude_rhineland_palatinate(self):
        """Ten Laender have no GEORB1 row and only nine may be filled.

        Nine of them are drawn by geoBoundaries as one ADM2 shape carrying the
        Land's own name, so the shape is the Land and the Land's figures are
        that shape's figures. The tenth is Rhineland-Palatinate, which
        abolished its Regierungsbezirke in 2000 while the boundary file still
        draws Koblenz, Trier and Rheinhessen-Pfalz -- its single figure would
        have to be split three ways and cannot be.

        So this is a declaration and not the rule "a Land with no GEORB1 row",
        which would catch the one case that must stay empty.
        """
        self.assertEqual(len(self.germany.WHOLE_LAND_REGIONS), 9)
        self.assertNotIn("07", self.germany.WHOLE_LAND_REGIONS,
                         "Rhineland-Palatinate is drawn as three abolished "
                         "Regierungsbezirke and cannot take one Land figure")
        self.assertEqual(
            set(self.germany.WHOLE_LAND_REGIONS.values()),
            {"Schleswig-Holstein", "Hamburg", "Bremen", "Saarland", "Berlin",
             "Brandenburg", "Mecklenburg-Vorpommern", "Sachsen-Anhalt",
             "Thüringen"})

    def test_a_whole_land_key_is_a_land_key_not_a_region_key(self):
        """Two digits, because these are Laender standing in for a region.

        GEORB1's own codes are three digits and open with their Land's -- 059
        is Arnsberg in 05. A three-digit key in this table would mean the
        declaration had been written against a region that does exist, which is
        the case main() refuses outright rather than double-counting.
        """
        for code in self.germany.WHOLE_LAND_REGIONS:
            self.assertEqual(len(code), 2, f"{code!r} is not a Land key")
            self.assertTrue(code.isdigit())

    def test_the_note_says_the_residual_is_not_only_the_irreligious(self):
        note = self.germany.NOTE.lower()
        for word in ("public law", "muslim", "not stated", "belief"):
            self.assertIn(word, note,
                          f"religion_note must say {word!r}: the third category "
                          f"is the largest bar in every Land and the least "
                          f"informative one")


class ACountyAbolishedBetweenCensusAndBoundaryFile(unittest.TestCase):
    """England and Wales were each one child short of a complete set.

    The roll-up fills a parent only from a complete set of children, so a
    single unreachable district is enough to leave a whole country's admin1
    record empty -- which is why England (149 of 150) and Wales (21 of 22)
    both carried no composition while their districts were 99% filled.
    """

    def table(self):
        from scripts.fetch_census import uk_nomis
        return uk_nomis, {
            "E06000061": {"name": "North Northamptonshire",
                          "counts": {"Christian": 172329.0, "No religion": 152998.0},
                          "total": 359523.0},
            "E06000062": {"name": "West Northamptonshire",
                          "counts": {"Christian": 210553.0, "No religion": 162751.0},
                          "total": 425723.0},
            "W06000016": {"name": "Rhondda Cynon Taff",
                          "counts": {"Christian": 100.0}, "total": 100.0},
        }

    def test_the_two_successor_authorities_are_added_up_into_the_county(self):
        uk_nomis, table = self.table()
        out = uk_nomis.reconcile(table)
        merged = out["E06000061+E06000062"]
        self.assertEqual(merged["name"], "Northamptonshire")
        self.assertEqual(merged["total"], 785246.0)
        self.assertEqual(merged["counts"]["Christian"], 382882.0)

    def test_the_parts_do_not_survive_alongside_the_whole(self):
        """Leaving both would double-count the county's people."""
        uk_nomis, table = self.table()
        out = uk_nomis.reconcile(table)
        self.assertNotIn("E06000061", out)
        self.assertNotIn("E06000062", out)

    def test_a_partial_set_is_refused_rather_than_published(self):
        """Half a county under the county's name is worse than an empty shape."""
        uk_nomis, table = self.table()
        del table["E06000062"]
        out = uk_nomis.reconcile(table)
        self.assertNotIn("E06000061+E06000062", out)
        self.assertIn("E06000061", out)

    def test_the_source_spelling_is_corrected_towards_the_shape(self):
        """geoBoundaries has the council's own spelling; Nomis has the variant.

        The mirror of MISSPELLED, which corrects the boundary file. Declaring
        this one there would rewrite a correct Welsh name into ONS's spelling.
        """
        uk_nomis, table = self.table()
        out = uk_nomis.reconcile(table)
        self.assertEqual(out["W06000016"]["name"], "Rhondda Cynon Taf")

    def test_both_corrected_names_are_names_geoboundaries_actually_draws(self):
        path = ROOT / "site" / "data" / "admin2" / "GBR.json"
        shapes = {r["name"] for r in json.loads(path.read_text(encoding="utf-8"))}
        self.assertIn("Rhondda Cynon Taf", shapes)
        self.assertIn("Northamptonshire", shapes)

    def test_a_merged_row_does_not_claim_a_single_ons_code(self):
        from scripts.fetch_census import uk_nomis
        name, parts = uk_nomis.MERGED_AUTHORITIES["E06000061+E06000062"]
        self.assertEqual(parts, ("E06000061", "E06000062"))


class ASurveyIsNotACount(unittest.TestCase):
    """Afrobarometer is the first sampled source on this map.

    A census figure and a survey estimate look identical once they are both a
    percentage, so the rules that keep them apart are the ones worth pinning
    down: what is too thin to publish, what was never asked, and which source
    wins where both have something to say.
    """

    def adapter(self):
        from scripts.fetch_census import afrobarometer
        return afrobarometer

    def rows(self):
        path = ROOT / "data" / "processed" / "afrobarometer_region.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_no_region_thinner_than_the_suppression_threshold_is_published(self):
        """25 is the DHS threshold, and a note must say how thin a cell is."""
        ab = self.adapter()
        self.assertEqual(ab.MIN_SAMPLE, 25)
        for row in self.rows():
            note = row.get("religion_note") or row.get("ethnicity_note") or ""
            found = re.search(r"This region: (\d+) respondents", note)
            if found:
                self.assertGreaterEqual(int(found.group(1)), ab.MIN_SAMPLE)

    def test_a_thin_region_says_so_rather_than_reading_as_precise(self):
        marked = 0
        for row in self.rows():
            note = row.get("religion_note") or row.get("ethnicity_note") or ""
            found = re.search(r"This region: (\d+) respondents", note)
            if found and int(found.group(1)) < 50:
                self.assertIn("imprecise", note)
                marked += 1
        self.assertGreater(marked, 0, "no low-precision region found to check")

    def test_a_question_never_asked_is_not_collected_and_never_a_composition(self):
        """Mauritania was not asked about religion; it must not acquire one."""
        for row in self.rows():
            if row["parent"] == "MRT":
                self.assertEqual(row["religion"], {"status": "not_collected"})
                self.assertIsInstance(row["ethnicity"], list)
        for iso in ("SDN", "TUN", "SYC"):
            for row in self.rows():
                if row["parent"] == iso:
                    self.assertEqual(row["ethnicity"], {"status": "not_collected"})

    def test_every_record_states_that_it_is_a_survey_estimate(self):
        for row in self.rows():
            notes = [row.get(f"{f}_note", "") for f in ("religion", "ethnicity")]
            joined = " ".join(n for n in notes if n)
            if any(isinstance(row.get(f), list) for f in ("religion", "ethnicity")):
                self.assertIn("survey estimates, not", joined)

    def test_the_survey_ranks_below_every_census_adapter(self):
        """A 40-respondent estimate must never overwrite a counted figure."""
        self.assertEqual(be.ADAPTER_FILES[0], "afrobarometer_region.json")

    def test_congo_brazzaville_is_not_the_other_congo(self):
        ab = self.adapter()
        self.assertEqual(ab.ISO3["8"], "COG")
        self.assertNotIn("COD", ab.ISO3.values())

    def test_the_committed_extract_is_actually_committed(self):
        """data/raw/* has silently un-tracked a source before now.

        Twenty of the Census of India workbooks were missing for exactly this
        reason and a clean checkout rebuilt mother tongue from sixteen states
        without saying so. A negation the adapter depends on is worth a test.
        """
        import subprocess
        for name in ("r9_extract.csv.gz", "r9_labels.json"):
            path = f"data/raw/afrobarometer/{name}"
            listed = subprocess.run(["git", "ls-files", "--error-unmatch", path],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(listed.returncode, 0,
                             f"{path} is not tracked; a clean checkout loses it")

    def test_the_brotherhoods_reach_islam(self):
        """A filter for Islam that omits Senegal's orders shows a false map."""
        import canonical_groups as cg
        table = cg.lookup("religion")
        for label in ("Muslim only", "Sunni only", "Tijaniya Brotherhood",
                      "Mouridiya Brotherhood", "Qadiriya", "Ismaeli"):
            self.assertEqual(table.get(cg.key(label)), "Islam", label)

    def test_the_named_churches_reach_christianity(self):
        import canonical_groups as cg
        table = cg.lookup("religion")
        for label in ("Christian only", "Zionist Christian Church", "Coptic",
                      "New Apostolic Church", "Dutch Reformed"):
            self.assertEqual(table.get(cg.key(label)), "Christianity", label)


class ScotlandsCensusNestsAndAsksThreeQuestions(unittest.TestCase):
    """Two ways to read Scotland's key statistics wrong, both silent.

    KS201SC publishes six ethnic groups and eighteen columns of detail beneath
    them, and both levels sum to the population; adding them together counts
    4.4 million White Scottish people as White as well. KS206SC asks three
    different questions of the same people, and only one of them partitions
    anything.
    """

    def rows(self):
        path = ROOT / "data" / "processed" / "scotland_council.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_all_thirty_two_council_areas_are_present(self):
        self.assertEqual(len(self.rows()), 32)

    def test_no_composition_double_counts_its_own_parent(self):
        for row in self.rows():
            for field in ("religion", "ethnicity", "language"):
                value = row.get(field)
                if not isinstance(value, list) or not value:
                    continue
                total = sum(g["pct"] for g in value)
                self.assertAlmostEqual(
                    total, 100.0, delta=1.0,
                    msg=f"{row['name']} {field} sums to {total}, not ~100")

    def test_ethnicity_reads_the_leaves_not_the_headings(self):
        """"White" alone says nothing about Scotland; the split is the point."""
        glasgow = next(r for r in self.rows() if r["name"] == "Glasgow City")
        groups = {g["group"] for g in glasgow["ethnicity"]}
        self.assertIn("Scottish", groups)
        self.assertNotIn("White", groups)

    def test_language_reads_the_one_block_that_is_a_composition(self):
        """Proficiency and "can speak Gaelic" are other questions entirely."""
        western = next(r for r in self.rows() if r["name"] == "Na h-Eileanan Siar")
        groups = {g["group"]: g["pct"] for g in western["language"]}
        self.assertIn("English only", groups)
        self.assertNotIn("Speaks well or very well", groups)
        # The Gaelic heartland: if this is small the wrong block was read.
        self.assertGreater(groups.get("Gaelic", 0), 30.0)

    def test_every_figure_is_stamped_2011_and_says_so(self):
        """England and Wales are 2021; a reader comparing them must be told."""
        for row in self.rows():
            self.assertEqual(row["population"]["year"], 2011)
            self.assertIn("2011", row["religion_note"])
            self.assertIn("spans ten years", row["religion_note"])

    def test_the_two_renamed_councils_match_shapes_that_exist(self):
        shapes = {r["name"] for r in
                  json.loads((ROOT / "site" / "data" / "admin2" / "GBR.json")
                             .read_text(encoding="utf-8"))}
        for name in ("City of Edinburgh", "Na h-Eileanan Siar"):
            self.assertIn(name, shapes)
            self.assertIn(name, {r["name"] for r in self.rows()})


class NorthernIrelandAsksTwoReligionQuestions(unittest.TestCase):
    """NISRA publishes ten MS-B tables and three of them are compositions.

    The rest are traps of two kinds. Knowledge of Irish, knowledge of
    Ulster-Scots and proficiency in English count an *ability*, so a person can
    appear in two of them or in none -- Scotland's KS206SC mixed the same three
    kinds of question in one sheet. And MS-B23/B24 report **religion or
    religion brought up in**, the community-background figure most quoted about
    Northern Ireland, which is a different question from the one every other
    country's religion field answers.
    """

    def rows(self):
        path = ROOT / "data" / "processed" / "northern_ireland_district.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_all_eleven_districts_are_present(self):
        self.assertEqual(len(self.rows()), 11)

    def test_every_composition_partitions_its_universe_once(self):
        for row in self.rows():
            for field in ("religion", "ethnicity", "language"):
                value = row.get(field)
                self.assertIsInstance(value, list, f"{row['name']} {field}")
                total = sum(g["pct"] for g in value)
                self.assertAlmostEqual(
                    total, 100.0, delta=1.0,
                    msg=f"{row['name']} {field} sums to {total}, not ~100")

    def test_religion_is_the_one_held_not_the_one_brought_up_in(self):
        """B20 and B23 disagree by design, and the map carries B20.

        Belfast is 43.5% Catholic and 21.7% of no religion by B20, and 48.7%
        Catholic and 11.6% of none by B23, because everyone raised in a church
        is returned to it. Reading B23 into a field labelled "religion" would
        put a number against Belfast that answers a question Birmingham was
        never asked.
        """
        belfast = next(r for r in self.rows() if r["name"] == "Belfast")
        groups = {g["group"]: g["pct"] for g in belfast["religion"]}
        self.assertAlmostEqual(groups["Catholic"], 43.5, delta=0.2)
        self.assertGreater(groups["No religion"], 20.0)
        self.assertIn("brought up in", belfast["religion_note"])

    def test_language_is_main_language_not_knowledge_of_irish(self):
        """MS-B05 counts anyone with any Irish; MS-B12 is the composition.

        12.4% of Northern Ireland aged 3 and over has some ability in Irish and
        0.3% give it as their main language -- 0.8% in Belfast, the highest of
        the eleven. If this reads much above that, MS-B05 was summed into a
        field that has to add to a hundred.
        """
        rows = self.rows()
        irish = {r["name"]: {g["group"]: g["pct"] for g in r["language"]}
                 .get("Irish", 0.0) for r in rows}
        self.assertLess(max(irish.values()), 2.0, irish)
        for row in rows:
            groups = {g["group"] for g in row["language"]}
            self.assertIn("English", groups)
            self.assertNotIn("Understands but does not read, write or speak Irish",
                             groups)
            self.assertIn("aged 3 and over", row["language_note"])

    def test_the_denominations_reach_christianity(self):
        """Unfolded, Northern Ireland reads as a country of no Christians.

        Its four largest churches are named in no other source this map reads,
        so each would be a one-country group and a filter for Christianity
        would show the province at roughly the Catholic share alone.
        """
        import canonical_groups as cg
        table = cg.lookup("religion")
        for label in ("Presbyterian Church in Ireland", "Church of Ireland",
                      "Methodist Church in Ireland", "Free Presbyterian",
                      "Brethren", "Non-denominational Christian",
                      "Mixed Catholic / Protestant",
                      "Other Christian denominations"):
            self.assertEqual(table.get(cg.key(label)), "Christianity", label)
        belfast = next(r for r in self.rows() if r["name"] == "Belfast")
        folded = cg.canonicalise(belfast["religion"], "religion")
        self.assertGreater(folded["Christianity"], 70.0)
        self.assertEqual(cg.check_no_double_counting(belfast["religion"],
                                                     "religion"), [])

    def test_every_district_name_reaches_a_shape(self):
        """Unlike Scotland's councils, none of the eleven needs an alias."""
        shapes = {r["name"] for r in
                  json.loads((ROOT / "site" / "data" / "admin2" / "GBR.json")
                             .read_text(encoding="utf-8"))}
        for row in self.rows():
            self.assertIn(row["name"], shapes)

    def test_the_committed_workbooks_are_actually_committed(self):
        """data/raw/* has silently un-tracked a source before now."""
        import subprocess
        for name in ("census2021msb01.xlsx", "census2021msb12.xlsx",
                     "census2021msb20.xlsx"):
            path = f"data/raw/northern_ireland/{name}"
            listed = subprocess.run(["git", "ls-files", "--error-unmatch", path],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(listed.returncode, 0,
                             f"{path} is not tracked; a clean checkout loses it")


class TheUKCensusPublishesEthnicityAtTwoLevels(unittest.TestCase):
    """Read whole, TS021 counts everyone twice.

    Nomis returns the broad groups and the detail beneath them in one response,
    both summing to the population, and for a long time every England and Wales
    record shipped at ~200%: Bradford carried "White" 61.1% beside "White:
    English, Welsh, Scottish, Northern Irish or British" 56.7%. Neither label
    is in the canonical index, so nothing downstream noticed -- the group
    filter simply treated them as two unrelated groups.
    """

    def rows(self, name):
        return json.loads((ROOT / "data" / "processed" / name)
                          .read_text(encoding="utf-8"))

    def test_no_english_or_welsh_record_counts_its_people_twice(self):
        for name in ("uk_lad.json", "uk_county.json"):
            for row in self.rows(name):
                for field in ("religion", "ethnicity"):
                    value = row.get(field)
                    if not isinstance(value, list) or not value:
                        continue
                    total = sum(g["pct"] for g in value)
                    self.assertAlmostEqual(
                        total, 100.0, delta=1.0,
                        msg=f"{name} {row['name']} {field} sums to {total}")

    def test_the_broad_headings_are_gone_and_the_detail_is_kept(self):
        bradford = next(r for r in self.rows("uk_lad.json")
                        if r["name"] == "Bradford")
        groups = {g["group"] for g in bradford["ethnicity"]}
        self.assertNotIn("White", groups)
        self.assertNotIn("Asian, Asian British or Asian Welsh", groups)
        self.assertIn("Asian, Asian British or Asian Welsh: Pakistani", groups)

    def test_the_rule_is_shared_with_the_other_two_uk_adapters(self):
        """One nesting rule, so a third census cannot be read a fourth way."""
        from fetch_census._shared import leaves
        self.assertEqual(
            leaves(["White", "White: Irish", "Other ethnic group"]),
            ["White: Irish", "Other ethnic group"])
        # A group with no detail keeps its own row rather than vanishing.
        self.assertEqual(leaves(["Chinese", "Roma"]), ["Chinese", "Roma"])


class IrelandsSeatCountIsNotItsName(unittest.TestCase):
    """geoBoundaries writes "ADARE-RATHKEALE LEA-6" and the CSO writes
    "Adare-Rathkeale, Limerick". The 6 is how many councillors the area
    returns; left in the comparison, all 166 rows miss their shape.
    """

    def test_the_seat_count_is_stripped_from_both_sides(self):
        self.assertEqual(be.norm("ADARE-RATHKEALE LEA-6"),
                         be.norm("Adare-Rathkeale"))
        self.assertEqual(be.norm("BALLINAMORE-LEA-6"), be.norm("Ballinamore"))
        self.assertEqual(be.norm("GRAIGUECULLEN -PORTARLINGTON-LEA-6"),
                         be.norm("Graiguecullen -Portarlington"))

    def test_a_place_actually_called_lea_survives(self):
        """The rule is LEA followed by digits, not the word on its own.

        There is one real Lea among the world's shapes, a township in the
        United States, and a rule that ate it would be trading 166 matches for
        a silent deletion.
        """
        self.assertEqual(be.norm("Lea"), "lea")
        self.assertEqual(be.norm("Leamington"), "leamington")
        self.assertEqual(be.norm("Lea County"), "lea")

    def test_every_irish_shape_name_still_identifies_one_place(self):
        """Stripping a suffix can merge two names, and here it merges one pair.

        Athlone straddles the Shannon, so the town has two local electoral
        areas either side of a county boundary. That collision is real and is
        handled by the province each row states; what this checks is that it is
        the *only* one, because a second undetected pair would silently give
        one area another's figures.
        """
        shapes = json.loads((ROOT / "site" / "data" / "admin2" / "IRL.json")
                            .read_text(encoding="utf-8"))
        keys: dict[str, list[str]] = {}
        for shape in shapes:
            keys.setdefault(be.norm(shape["name"]), []).append(shape["name"])
        shared = {k: v for k, v in keys.items() if len(v) > 1}
        self.assertEqual(sorted(shared), ["athlone"], shared)

    def test_ireland_declares_why_it_has_no_language(self):
        """Asked, and not as a composition -- which is not the same as unasked."""
        import common
        reason = common.collection_policy("IRL", "language")
        self.assertIsNotNone(reason)
        self.assertIn("foreign languages", reason)
        self.assertIn("counts an ability", reason)
        # Religion and ethnicity come from the same census and must not be
        # declared away with it.
        self.assertIsNone(common.collection_policy("IRL", "religion"))
        self.assertIsNone(common.collection_policy("IRL", "ethnicity"))

    def test_the_four_way_religion_cost_is_stated_on_every_record(self):
        """Catholic is the only Christian denomination the CSO names here.

        At local electoral area the classification is Catholic / Other
        religion / No religion / Not stated, so "Other religion" holds the
        Church of Ireland, Presbyterians, Orthodox and Muslims together and a
        filter for Christianity reads an Irish area at its Catholic share. That
        is a real understatement and belongs on the record, not in a commit
        message nobody reading the map will see.
        """
        path = ROOT / "data" / "processed" / "ireland_lea.json"
        if not path.exists():
            self.skipTest("ireland_lea.json needs a network run to exist")
        rows = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 166)
        for row in rows:
            self.assertIn("Catholic share alone", row["religion_note"])
            groups = {g["group"] for g in row["religion"]}
            self.assertEqual(groups, {"Catholic", "Other religion",
                                      "No religion", "Not stated"}, row["name"])
            total = sum(g["pct"] for g in row["religion"])
            self.assertAlmostEqual(total, 100.0, delta=1.0, msg=row["name"])


class MalaysiaKeepsTheNonCitizenRow(unittest.TestCase):
    """OpenDOSM's ethnicity dimension has six categories, and one of them is
    citizenship. Dropping it would hand a fifth of Sabah's east coast to the
    other five bars; the adapter keeps it, named for what it is, and reads the
    latest year of a series that runs from 2020.
    """

    ROWS = [
        {"state": "Johor", "district": "Batu Pahat", "date": date, "sex": sex,
         "age": "overall", "ethnicity": eth, "population": value}
        for date in ("2020-01-01", "2024-01-01")
        for sex, scale in (("both", 1.0), ("male", 0.5))
        for eth, value in (("overall", "49.0"), ("bumi_malay", "29.4"),
                           ("bumi_other", "0.4"), ("chinese", "12.1"),
                           ("indian", "0.6"), ("other_citizen", "0.3"),
                           ("other_noncitizen", "6.1"))
    ]

    def test_latest_year_both_sexes_all_ages_in_persons(self):
        from scripts.fetch_census import malaysia
        date, comps = malaysia.compositions(self.ROWS, ("state", "district"))
        self.assertEqual(date, "2024-01-01")
        counts = comps[("Johor", "Batu Pahat")]
        self.assertEqual(counts["__total__"], 49000)
        self.assertEqual(counts["Non-Malaysian citizen"], 6100)
        self.assertEqual(malaysia.check("Batu Pahat", counts), 49000)
        self.assertNotIn("overall", counts)

    def test_an_unknown_category_stops_the_run(self):
        from scripts.fetch_census import malaysia
        rows = self.ROWS + [dict(self.ROWS[-1], sex="both", ethnicity="orang_asli")]
        with self.assertRaises(SystemExit):
            malaysia.compositions(rows, ("state", "district"))


class CzechiaReadsTheOpenDataLong(unittest.TestCase):
    """ČSÚ's open data is one long CSV per table: the territory's kind in
    uzemi_cis, a row with no category for its population, and a category
    label per row. Religion partitions the population and a row absent from
    the table stops the build; the single-mother-tongue file leaves the
    two-language and other-language people as the total less its rows, kept
    as one bar; a district is filed under its kraj by the adapter's own
    table, with the boundary file's English spelling as an alias.
    """

    HEADER = ("idhod,hodnota,ukaz_kod,vira_cis,vira_kod,uzemi_cis,uzemi_kod,"
              "sldb_rok,sldb_datum,ukaz_txt,vira_txt,uzemi_txt")

    def rows(self, label_column="vira_txt", cis="101", kod="40924", name="Praha-východ",
             extra=()):
        header = self.HEADER.replace("vira_txt", label_column)
        lines = [header,
                 f"1,1000,3162,,,{cis},{kod},2021,2021-03-26,Počet,,{name}",
                 f"2,5,3162,3078,2,43,500011,2021,2021-03-26,Počet,Apoštolská církev,Želechovice"]
        for i, (label, n) in enumerate(extra, 10):
            lines.append(f"{i},{n},3162,3078,{i},{cis},{kod},2021,2021-03-26,Počet,{label},{name}")
        return "\n".join(lines).encode("utf-8")

    def test_only_kraje_and_okresy_are_read_and_the_blank_row_is_the_total(self):
        from scripts.fetch_census import czechia
        czechia.http_get = lambda url, **kw: self.rows(
            extra=[("Bez náboženské víry", 600), ("Církev římskokatolická", 100),
                   ("katolická víra (katolík)", 50), ("ateismus", 10), ("Neuvedeno", 240)])
        units = czechia.read_table("religion")
        self.assertEqual(list(units), [("101", "40924")])
        unit = units[("101", "40924")]
        self.assertEqual(unit["total"], 1000)
        groups = czechia.religion(unit["rows"], unit["total"], unit["name"])
        self.assertEqual(groups["No religion"], 610)        # the written atheism joins it
        self.assertEqual(groups["Roman Catholic"], 100)
        self.assertEqual(groups["Catholic (unspecified)"], 50)  # and stays apart

    def test_a_religion_row_outside_the_table_is_other_and_a_bad_sum_stops_the_build(self):
        from scripts.fetch_census import czechia
        groups = czechia.religion({"Bez náboženské víry": 600, "Církev jedi rytířů": 400},
                                  1000, "x")
        self.assertEqual(groups["Other religion"], 400)
        self.assertEqual(czechia.UNNAMED["religion"]["Církev jedi rytířů"], 400)
        with self.assertRaises(SystemExit):
            czechia.religion({"Bez náboženské víry": 600, "Neuvedeno": 100}, 1000, "x")

    def test_language_remainder_is_one_labelled_bar(self):
        from scripts.fetch_census import czechia
        groups = czechia.language({"Český jazyk": 800, "Slovenský jazyk": 50, "Nezjištěno": 100,
                                   "Osoby se dvěma mateřskými jazyky": 25, "Jiný jazyk": 5,
                                   "Klingonský jazyk": 20},
                                  1000, "x")
        self.assertEqual(groups["Two mother tongues"], 25)
        self.assertEqual(groups[czechia.LANGUAGE_REMAINDER], 5 + 20)   # the unnamed 20 join it
        self.assertNotIn("Klingonský jazyk", groups)
        self.assertEqual(groups["Not stated"], 100)
        with self.assertRaises(SystemExit):        # more rows than people
            czechia.language({"Český jazyk": 1100}, 1000, "x")

    def test_nationality_drops_celkem_and_keeps_every_group(self):
        from scripts.fetch_census import czechia
        groups = czechia.nationality({"Česká celkem": 700, "Moravská celkem": 100,
                                      "Jiná celkem": 5})
        self.assertEqual(groups, {"Czech": 700, "Moravian": 100, "Other": 5})
        self.assertEqual(czechia.nationality({"Marťanská celkem": 1}), {"Other": 1})

    def test_every_okres_has_a_kraj_and_the_english_spellings_are_aliases(self):
        from scripts.fetch_census import czechia
        self.assertEqual(sum(len(v) for v in czechia.OKRES_KRAJ.values()), 77)
        self.assertEqual(len(czechia.KRAJ_OF), 77)
        self.assertEqual(czechia.KRAJ_OF["Praha-východ"], "Středočeský kraj")
        self.assertEqual(czechia.OKRES_ALIASES["Brno-město"], ["Brno-City"])
        for okres in czechia.OKRES_ALIASES:
            self.assertIn(okres, czechia.KRAJ_OF)


class CroatiaReadsTheBilingualHeader(unittest.TestCase):
    """DZS's census workbook names each category in a bilingual header cell
    (Croatian over English) with a count and a percent column per category;
    the categories are read from the header, the percent columns skipped, a
    dash is zero, the country row is skipped, and a county's own row is the
    one with no unit type. A row that does not sum to its total stops the
    build.
    """

    ROWS = [
        ("1.",), ("STANOVNIŠTVO PREMA NARODNOSTI",), (None,), (None,), (None,), (None,), (None,),
        ("Županija", "Jedinica lokalne samouprave", "County of", "Local self-government unit",
         "Grad/općina\nTown/Municipality", "Ukupno\nTotal", "Ukupno, %\nTotal, %",
         "Hrvati\nCroats", "Hrvati, %\nCroats, %", "Srbi\nSerbs", "Srbi, %\nSerbs, %",
         "Ostali\nOther", "Ostali, %\nOther, %", "Nepoznato\nUnknown", "Nepoznato, %\nUnknown, %"),
        ("Republika Hrvatska", None, "Republic of Croatia", None, None, 100, 100, 90, 90, 5, 5, 3, 3, 2, 2),
        ("Zagrebačka", None, "Zagreb", None, None, 100, 100, 90, 90, 5, 5, 3, 3, 2, 2),
        ("Zagrebačka", "Grad", "Zagreb", "Town", "Dugo Selo", 60, 100, 55, 91.7, "-", "-", 3, 5, 2, 3.3),
        ("Zagrebačka", "Općina", "Zagreb", "Municipality", "Bibinje", 40, 100, 35, 87.5, 5, 12.5, "-", "-", "-", "-"),
        ("1) Footnote under the table", None, None, None, None, None),
    ]

    def test_labels_units_and_dashes(self):
        from scripts.fetch_census import croatia
        labels, units = croatia.parse_sheet(self.ROWS)
        self.assertEqual(labels, ["Croats", "Serbs", "Other", "Unknown"])
        self.assertEqual(len(units), 3)                 # the footnote is not a unit
        self.assertEqual(croatia.english("Ostali kršćani1)\nOther Christians1)"), "Other Christians")
        self.assertEqual(croatia.bars("religion", {"county": "x", "name": None, "total": 10,
                                                   "counts": {"Jews": 10}})[0]["group"], "Judaism")
        self.assertEqual([(u["type"], u["name"]) for u in units],
                         [(None, None), ("Grad", "Dugo Selo"), ("Općina", "Bibinje")])
        self.assertEqual(units[1]["counts"]["Serbs"], 0)
        bars = croatia.bars("ethnicity", units[1])
        self.assertEqual(bars[0], {"group": "Croatian", "pct": 91.7, "count": 55})
        self.assertEqual([b["group"] for b in bars], ["Croatian", "Other", "Not stated"])

    def test_a_row_that_does_not_sum_stops_the_build(self):
        from scripts.fetch_census import croatia
        _, units = croatia.parse_sheet(self.ROWS)
        units[2]["counts"]["Croats"] = 10
        with self.assertRaises(SystemExit):
            croatia.bars("ethnicity", units[2])

    def test_every_county_is_named_for_the_boundary_file(self):
        from scripts.fetch_census import croatia
        self.assertEqual(len(croatia.COUNTIES), 21)
        self.assertEqual(croatia.COUNTIES["Grad Zagreb"], "City of Zagreb")
        self.assertEqual(croatia.unit_aliases("Grad Buje – Buie"), ["Grad Buje"])
        self.assertEqual(croatia.unit_aliases("Grad Cres"), ["Otok Cres"])


class ThailandReadsTheTranscribedReports(unittest.TestCase):
    """The Wikipedia table transcribes each province's 2000 final report: a
    header row separated by "||", a province link with a <ref> citing the
    NSO PDF, shares with and without their "%", and N/A where the report gave
    nothing. The three shares leave a remainder that is published as one group;
    a faith the report did not give is absent; a changed column order refuses.
    """

    WIKITEXT = (
        "intro\n{| class=\"wikitable sortable\"\n|+\'\'\'caption\'\'\'\n|-\n"
        "!province name||% [[Thai nationality law|Thai nationals]] in 1970||% Thai nationals in 2000"
        "||[[Buddhist]] % in 1990||[[Buddhist]] % in 2000||[[Muslim]] % in 1990||Muslim % in 2000"
        "||[[Christianity|Christian]] % in 1990||Christian % in 2000"
        "||Linguistic minorities in 1990||Linguistic minorities in 2000\n|-\n"
        "|[[Yala province|Yala]]<ref>{{cite web|url=http://web.nso.go.th/pop2000/finalrep/yalafn.pdf "
        "|title=Data}}</ref>||97.3%||99.8%||35.9%||31.0%||63.8%||68.9%||N/A||N/A||Malay (62.4%)||Malay (66.1%)\n|-\n"
        "|[[Sisaket province|Sisaket]]<ref>{{cite web |url=http://web.nso.go.th/pop2000/finalrep/sisaketfn.pdf "
        "|archive-url=https://web.archive.org/x }}</ref>||[[N/A]]||99.5||99.6%||99.5||0.1%||0.1%||N/A||0.3||N/A||N/A\n|-\n"
        "|[[Bangkok]]<ref>{{cite web|url=http://web.nso.go.th/pop2000/finalrep/bangkok1.pdf}}</ref>"
        "||94.8%||99.0%||95.1%||94.5%||4.0%||4.1%||0.7%||1.0%||English (0.1%)||English (0.7%)\n"
        "|}\nafter"
    )

    def test_shares_remainder_names_and_the_cited_report(self):
        from scripts.fetch_census import thailand
        records = thailand.build(self.WIKITEXT)
        by = {r["name"]: r for r in records}
        self.assertEqual(sorted(by), ["Bangkok", "Sisaket Province", "Yala Province"])
        yala = by["Yala Province"]
        self.assertEqual(yala["religion"], [{"group": "Islam", "pct": 68.9},
                                            {"group": "Buddhism", "pct": 31.0},
                                            {"group": "Other or not stated", "pct": 0.1}])
        self.assertEqual(yala["sources"][0]["url"], "http://web.nso.go.th/pop2000/finalrep/yalafn.pdf")
        self.assertEqual(yala["aliases"], ["Yala"])
        self.assertEqual(by["Bangkok"]["aliases"], [])
        self.assertIn("Si Sa Ket Province", by["Sisaket Province"]["aliases"])
        sisaket = {b["group"]: b["pct"] for b in by["Sisaket Province"]["religion"]}
        self.assertEqual(sisaket, {"Buddhism": 99.5, "Islam": 0.1, "Christianity": 0.3,
                                   "Other or not stated": 0.1})
        self.assertNotIn("Christianity", {b["group"] for b in yala["religion"]})
        self.assertEqual(thailand.percent("[[N/A]]"), None)
        self.assertEqual(thailand.plain("% [[Buddhist]] % in 1990<ref>x</ref>"), "Buddhist in 1990")

    def test_a_reordered_table_refuses(self):
        from scripts.fetch_census import thailand
        swapped = self.WIKITEXT.replace("[[Buddhist]] % in 2000||[[Muslim]] % in 1990",
                                        "[[Muslim]] % in 1990||[[Buddhist]] % in 2000")
        with self.assertRaises(SystemExit):
            thailand.build(swapped)
        with self.assertRaises(SystemExit):
            thailand.build(self.WIKITEXT.replace("||35.9%||31.0%||63.8%||68.9%",
                                                 "||35.9%||81.0%||63.8%||68.9%"))


class BosniaReadsBookTwo(unittest.TestCase):
    """BHAS Book 2 tables carry a bilingual header (the English row starts
    "Level"), three rows per territory, a dash for zero, and the territory's
    Bosnian name over its English one. The Total row is read, entities go to
    both levels, cantons under the Federation, 'Islamska' and 'Muslimanska'
    are summed, and an unknown territory or a row off its total refuses.
    """

    def rows(self):
        def t(level, name, tot, *c):
            return (level, name, "Ukupno/\nTotal", tot, *c)
        return [
            ("", "5. Stanovništvo prema vjeroispovijesti i spolu"),
            ("Nivo", "Teritorija", "Spol", "Ukupno", "Islamska", "Pravoslavna", "Muslimanska",
             "Bošnjačka", "Ostali", "Nepoznato"),
            ("Level", "Area", "Sex", "Total", "Islam", "Orthodox", "Muslim", "Bosniak",
             "Others", "Unknown"),
            t(0, "BOSNA I HERCEGOVINA\nBOSNIA AND HERZEGOVINA", 100, 50, 30, 10, 0, 5, 5),
            (0, "BOSNA I HERCEGOVINA\nBOSNIA AND HERZEGOVINA", "Muški/\nMale", 50, 25, 15, 5, 0, 3, 2),
            t(1, "FEDERACIJA BOSNE I HERCEGOVINE\nFEDERATION OF BOSNIA AND HERZEGOVINA",
              60, 40, 5, 10, 1, 2, 2),
            t(2, "KANTON 10\nCANTON 10", 20, "-", 18, 1, 0, 1, "-"),
            t(1, "REPUBLIKA SRPSKA\nREPUBLIKA SRPSKA", 30, 5, 24, "-", 0, "1", 0),
            t(1, "BRČKO DISTRIKT BOSNE I HERCEGOVINE\nBRČKO DISTRICT", 10, 5, 1, 0, 0, 4, 0),
        ]

    def test_levels_merge_and_labels(self):
        from scripts.fetch_census import bosnia
        labels, units = bosnia.parse_table(self.rows())
        self.assertEqual(labels, ["Islam", "Orthodox", "Muslim", "Bosniak", "Others", "Unknown"])
        self.assertEqual([(u["level"], u["native"]) for u in units],
                         [(0, "BOSNA I HERCEGOVINA"), (1, "FEDERACIJA BOSNE I HERCEGOVINE"),
                          (2, "KANTON 10"), (1, "REPUBLIKA SRPSKA"),
                          (1, "BRČKO DISTRIKT BOSNE I HERCEGOVINE")])
        out = bosnia.build({"religion": {u["native"]: u for u in units}})
        self.assertEqual(sorted(r["name"] for r in out["admin1"]),
                         ["Brčko District", "Federation of Bosnia and Herzegovina", "Republika Srpska"])
        self.assertEqual(sorted(r["name"] for r in out["admin2"]),
                         ["Brčko District", "Canton 10", "Republika Srpska"])
        fed = next(r for r in out["admin1"] if r["name"].startswith("Federation"))
        self.assertEqual(fed["religion"][0], {"group": "Islam", "pct": 83.3, "count": 50})
        self.assertIn({"group": "Bosniak (written as religion)", "pct": 1.7, "count": 1},
                      fed["religion"])
        canton = next(r for r in out["admin2"] if r["name"] == "Canton 10")
        self.assertEqual(canton["parent"], fed["id"])
        self.assertEqual(canton["religion"][0]["group"], "Orthodox")
        self.assertNotIn("Unknown", {b["group"] for b in canton["religion"]})   # the dash
        brcko = next(r for r in out["admin2"] if r["name"] == "Brčko District")
        self.assertIn("Brcko District", brcko["aliases"])
        self.assertNotEqual(brcko["id"], next(r for r in out["admin1"] if r["name"] == "Brčko District")["id"])

    def test_an_unknown_territory_or_a_bad_total_refuses(self):
        from scripts.fetch_census import bosnia
        rows = self.rows()
        rows.append((2, "NOVI KANTON\nNEW CANTON", "Ukupno/\nTotal", 5, 5, 0, 0, 0, 0, 0))
        _, units = bosnia.parse_table(rows)
        with self.assertRaises(SystemExit):
            bosnia.build({"religion": {u["native"]: u for u in units}})
        _, units = bosnia.parse_table(self.rows())
        units[2]["counts"]["Orthodox"] = 5
        with self.assertRaises(SystemExit):
            bosnia.bars("religion", units[2])


class WikiCensusReadsATranscribedTable(unittest.TestCase):
    """A census table reaching the project as a Wikipedia transcription: the
    table is found by its first header cells, the header rows skipped, the
    percent columns read, the total row dropped, aliases attached, a short
    row given its remainder, and a reordered or overflowing table refused.
    """

    KAZ = (
        "{| class=\"wikitable\"\n|-\n"
        "! rowspan=\"2\" |Region !! colspan=\"2\" |Islam !! colspan=\"2\" |Christianity"
        " !! colspan=\"2\" |Other !! colspan=\"2\" |No Religion !! colspan=\"2\" |Undeclared\n|-\n"
        "! # !! % !! # !! % !! # !! % !! # !! % !! # !! %\n|-\n"
        "|Total||13,297,775||69.31||3,297,550||17.19||45,897||0.24||432,140||2.25||2,112,653||11.01\n|-\n"
        "|[[Akmola Region]]||362,070||46.24||287,619||36.73||1,481||0.19||14,578||1.86||117,247||14.97\n|-\n"
        "|Atyrau Region||563,53||83.66||29,513||4.38||870||0.13||6,395||0.95||73,284||10.88\n|}"
    )
    KHM = (
        "{| class=\"wikitable sortable\"\n"
        "! rowspan=\"2\" | Province !! colspan=\"2\" | Buddhism !! colspan=\"2\" | Islam"
        " !! colspan=\"2\" | Christianity !! colspan=\"2\" | Others\n|-\n"
        "! 2008 !! 2019 !! 2008 !! 2019 !! 2008 !! 2019 !! 2008 !! 2019\n|-\n"
        "| [[Banteay Meanchey]] || 99.2 || 99.3 || 0.5 || 0.4 || 0.3 || 0.2 || 0.0 || 0.0\n|-\n"
        "| Mondulkiri || 54.7 || 70.4 || 5.5 || 4.4 || 4.4 || 4.0 || 35.5 || 21.2\n|-\n"
        "| Total || 96.9 || 97.1 || 1.9 || 2.0 || 0.4 || 0.3 || 0.8 || 0.5\n|}"
    )

    def test_kazakhstan_and_cambodia(self):
        from scripts.fetch_census import wiki_census as w
        kaz = w.build("KAZ", w.SPECS["KAZ"], "intro\n" + self.KAZ)
        self.assertEqual([r["name"] for r in kaz], ["Akmola Region", "Atyrau Region"])
        self.assertEqual(kaz[0]["religion"][0], {"group": "Islam", "pct": 46.24})
        self.assertEqual({b["group"] for b in kaz[1]["religion"]},
                         {"Islam", "Christianity", "Other religions", "No religion", "Not stated"})
        khm = w.build("KHM", w.SPECS["KHM"], self.KHM)
        self.assertEqual([r["name"] for r in khm], ["Banteay Meanchey", "Mondulkiri"])
        self.assertEqual(khm[0]["aliases"], ["Bantey Meanchey"])
        self.assertEqual(khm[0]["religion"][0], {"group": "Buddhism", "pct": 99.3})   # 2019, not 2008
        self.assertIn({"group": "Other religions", "pct": 0.0}, khm[0]["religion"])  # a printed 0.0 is kept
        self.assertEqual(khm[1]["religion"][1], {"group": "Other religions", "pct": 21.2})

    def test_a_short_row_gets_a_remainder_and_a_bad_table_refuses(self):
        from scripts.fetch_census import wiki_census as w
        short = self.KHM.replace("|| 0.0 || 0.0", "|| 0.0 || N/A").replace("99.2 || 99.3", "99.2 || 97.0")
        khm = w.build("KHM", w.SPECS["KHM"], short)
        self.assertIn({"group": "Other or not stated", "pct": 2.4}, khm[0]["religion"])
        with self.assertRaises(SystemExit):
            w.build("KHM", w.SPECS["KHM"], self.KHM.replace("Province !!", "Area !!"))
        with self.assertRaises(SystemExit):
            w.build("KHM", w.SPECS["KHM"], self.KHM.replace("|| 70.4 ||", "|| 90.4 ||"))


class KazakhstanSumsTheNewRegionsBack(unittest.TestCase):
    """The Bureau's workbook has 20 regions in the 2022 layout; the map draws
    16 in the 2017 one. The four carved-out regions are summed back into the
    ones they came from, a column is checked against its own total, the
    city columns' two spellings are one city, and a district keeps its
    Cyrillic name with a transliteration and any renamed shape as aliases.
    """

    def test_parse_merge_and_names(self):
        from scripts.fetch_census import kazakhstan as k
        rows = [("2.Численность",), (None, None, None, None, None, "человек"),
                ("№", "Код", "Этносы", "Республика", "В том числе"),
                (None, None, None, None, "Абай", "Восточно-Казахстанская", "г. Астана"),
                (1, "000", "Всего", 130, 30, 70, 30),
                (2, "005", "Казахи", 100, 20, 60, 20),
                (3, "001", "Русские", 25, 10, 8, 7),
                (4, "190", "Не указавшие", 5, "-", 2, 3)]
        units, counts = k.parse_sheet(rows)
        self.assertEqual(units, ["Абай", "Восточно-Казахстанская", "г.Астана"])
        self.assertEqual(counts["Абай"], {"Всего": 30, "Казахи": 20, "Русские": 10, "Не указавшие": 0})
        merged = k.merged({**{c: {"Всего": 1, "Казахи": 1} for c in k.REGIONS}, **counts})
        self.assertEqual(merged["East Kazakhstan Region"]["Всего"], 100)
        self.assertEqual(merged["East Kazakhstan Region"]["Казахи"], 80)
        self.assertEqual(len(merged), 16)
        bars = k.bars("x", counts["Восточно-Казахстанская"])
        self.assertEqual(bars[0], {"group": "Kazakh", "pct": 85.7, "count": 60})
        self.assertEqual([b["group"] for b in bars], ["Kazakh", "Russian", "Not stated"])
        with self.assertRaises(SystemExit):
            k.bars("x", {"Всего": 100, "Казахи": 50})
        self.assertEqual(k.transliterate(k.bare("Щербактинский район")), "Shcherbaktinskiy")
        self.assertEqual(k.transliterate(k.bare("Кокшетау г.а.")), "Kokshetau")
        self.assertEqual(k.RENAMED["район Бәйтерек"], ["Zelenovskiy"])
        self.assertEqual(k.label("Саха(Якуты)"), "Yakut")


class ParentIsResolvedByExactNameFirst(unittest.TestCase):
    """norm() drops "Region", so "Almaty Region" and the city "Almaty" share a
    key; a district row naming the region as its parent must be scoped to the
    region, not to whichever of the two was keyed last.
    """

    def test_region_and_city_of_one_name(self):
        region = {"id": "R", "name": "Almaty Region"}
        city = {"id": "C", "name": "Almaty"}
        admin1 = {}                                   # the ambiguous key was dropped
        exact = {"almaty region": region, "almaty": city}
        shapes = {be.norm("Aksuskiy"): [{"id": "a1", "name": "Aksuskiy", "parent": "R"},
                                        {"id": "a2", "name": "Aksuskiy", "parent": "P"}]}
        entity, how = be.match_admin2({"name": "Аксуский район", "aliases": ["Aksuskiy"],
                                       "parent_name": "Almaty Region"}, shapes, admin1, exact)
        self.assertEqual((entity or {}).get("id"), "a1")
        self.assertTrue(how.endswith("+state"))


class PolandCutsTheReligionTreeOnce(unittest.TestCase):
    """GUS publishes religion as a seven-level classification tree, and the
    composition is one cut through it: Christian branches at level 5, other
    religions at level 4, no religion at level 3, the non-response at level
    2. Reading any other level as well double-counts; reading none of the
    level-2 rows renormalises away a fifth of Poland.
    """

    def rows(self):
        def tr(voiv, powiat, code, level, label, count):
            r = [voiv, powiat, code, str(level)] + [""] * 5 + [str(count), "1", "x", "x"]
            r[4 + min(level - 1, 4)] = label
            return tuple(r)
        return [
            ("Województwo", "Powiat", "Kod powiatu", "Poziom klasyfikacji",
             "", "", "", "", "Grupa wyznań", "W liczbach", "", "", ""),
            tr("DOLNOŚLĄSKIE", "bolesławiecki", "0201", 1, "Ogółem", 88435),
            tr("", "", "0201", 2, "Udzielający odpowiedzi na pytanie o wyznanie", 69320),
            tr("", "", "0201", 3, "należący do wyznania w tym:", 63683),
            tr("", "", "0201", 4, "chrześcijaństwo", 63636),
            tr("", "", "0201", 5, "katolicyzm", 63071),
            tr("", "", "0201", 6, "Kościół katolicki", 63045),
            tr("", "", "0201", 5, "protestantyzm i tradycja protestancka", 171),
            tr("", "", "0201", 4, "islam", 10),
            tr("", "", "0201", 3, "nienależący do żadnego wyznania", 5637),
            tr("", "", "0201", 2, "Odmawiający odpowiedzi na pytanie o wyznanie", 19075),
            tr("", "", "0201", 2, "Nie ustalono", 40),
            tr("", "dzierżoniowski", "0202", 1, "Ogółem", 97721),
            tr("", "", "0202", 5, "katolicyzm", 68363),
        ]

    def test_one_cut_and_the_non_response_kept(self):
        from scripts.fetch_census import poland
        rows = self.rows()

        class Sheet:
            def iter_rows(self, values_only=True):
                return iter(rows)
        poland.workbook = lambda field: {"TABL.4": Sheet()}
        units = poland.units_tree("admin2")
        first = units[("DOLNOŚLĄSKIE", "bolesławiecki")]
        self.assertEqual(first["__total__"], 88435)
        self.assertEqual(first["Catholic"], 63071)          # level 5, not 6 or 4
        self.assertNotIn("Other Christian", first)
        self.assertEqual(first["Not stated"], 19075 + 40)   # both level-2 rows
        self.assertEqual(first["No religion"], 5637)
        # The second powiat inherits the voivodeship its column left blank.
        self.assertIn(("DOLNOŚLĄSKIE", "dzierżoniowski"), units)

    def test_powiat_names_follow_the_boundary_file(self):
        from scripts.fetch_census import poland
        self.assertEqual(poland.powiat_names("DOLNOŚLĄSKIE", "bolesławiecki"),
                         ("powiat bolesławiecki", []))
        self.assertEqual(poland.powiat_names("ŚLĄSKIE", "bielski"),
                         ("powiat bielski", ["Bielsko County"]))
        self.assertEqual(poland.powiat_names("PODLASKIE", "bielski"),
                         ("powiat bielski", []))
        self.assertEqual(poland.powiat_names("DOLNOŚLĄSKIE", "m. Wrocław"), ("Wrocław", []))
        self.assertEqual(poland.powiat_names("MAZOWIECKIE", "m. st. Warszawa"), ("Warszawa", []))


class AbsLanguageTableListsAParentBesideItsChildren(unittest.TestCase):
    """G13 puts "Other Languages Total" (code O_T) beside every language under
    it, and O_T is no prefix of "3103" Italian, so the code tree cannot see the
    parent. Arithmetic can: the set over-counts the total by exactly that row.
    """

    def test_the_duplicated_parent_is_dropped_and_nothing_else(self):
        from scripts.fetch_census import abs as abs_
        coded = {("Total", "_T"): 1000, ("Speaks English only", "1"): 700,
                 ("Other Languages Total", "O_T"): 250, ("Not stated", "_N"): 50,
                 ("Italian", "3103"): 100, ("Chinese: Total", "71"): 150,
                 ("Chinese: Mandarin", "7104"): 120}
        kept, how = abs_.top_level(coded, 1000)
        self.assertEqual(how, "code tree less a duplicated parent")
        self.assertEqual(kept, {"Speaks English only": 700, "Not stated": 50,
                                "Italian": 100, "Chinese": 150})

    def test_a_small_region_short_of_a_category_is_not_rescued(self):
        from scripts.fetch_census import abs as abs_
        small = {("Buddhism", "1"): 12, ("Islam", "4"): 9,
                 ("Religious affiliation not stated", "_N"): 614, ("Total", "_T"): 1588}
        _, how = abs_.top_level(small, 1588)
        self.assertIn("nothing summed", how)


class AngolaReadsFiguresByPosition(unittest.TestCase):
    """The census report prints "34 492 888" with spaces and wraps each table
    over two pages, so a row is read from word coordinates: digit groups
    closer than a few points are one figure, a page counts for a column group
    only when all 21 province rows carry exactly that group's number of
    figures, the two groups must agree on the province's total, the 21
    report provinces sum into the map's 18, and a mis-slotted column fails
    the partition check rather than shipping.
    """

    @staticmethod
    def row(name, figures, x=200):
        words, nx = [], 100
        for part in name.split():
            words.append(f"{part}[{nx}-{nx + 5 * len(part)}]")
            nx += 5 * len(part) + 3
        for n in figures:
            text = f"{n:,}".replace(",", " ")
            for part in text.split(" "):
                words.append(f"{part}[{x}-{x + 4 * len(part)}]")
                x += 4 * len(part) + 2            # 2 pt between digit groups
            x += 20                                # 20 pt between columns
        return " ".join(words)

    def page(self, labels, values):
        from scripts.fetch_census import angola as a
        lines = ["Província[100-140] e[142-146] área[148-160]"]
        lines.append(self.row("Angola", [sum(v) for v in zip(*values.values())]))
        lines.append("Províncias[100-140]")
        for p in a.PROVINCES:
            lines.append(self.row(p, values[p]))
        lines.append("Urbana[100-130]")
        for p in a.PROVINCES:
            lines.append(self.row(p, [v // 2 for v in values[p]]))
        return "\n".join(lines)

    def test_parse_row_joins_digit_groups(self):
        from scripts.fetch_census import angola as a
        line = ("Cuanza-Norte[107-151] 619[226-238] 011[240-252] 356[278-290] 190[292-304] "
                "15[342-350] 814[352-364] 754[414-426] 5[462-466] 614[468-480] 198[521-533] "
                "210[575-587]")
        self.assertEqual(a.parse_row(line),
                         ("Cuanza-Norte", [619011, 356190, 15814, 754, 5614, 198, 210]))

    def test_tables_merge_and_check(self):
        from scripts.fetch_census import angola as a
        pages = []
        for field, spec in a.TABLES.items():
            pages.append(f"{spec['heading']} - População por província")
            per_province = {}
            for i, p in enumerate(a.PROVINCES):
                total = 10000 * (i + 1)
                counts = {}
                for labels in spec["groups"]:
                    for j, label in enumerate(labels):
                        if label != "TOTAL":
                            counts[label] = 10 * (j + 1)
                rest = total - sum(counts.values())
                counts["Other" if "Other" in counts else "Not stated"] += rest
                per_province[p] = (total, counts)
            for labels in spec["groups"]:
                pages.append(self.page(labels, {
                    p: [t if l == "TOTAL" else c[l] for l in labels]
                    for p, (t, c) in per_province.items()}))
        text = a.PAGE_BREAK.join(pages)
        records = a.build(text)
        self.assertEqual(len(records), 18)
        by = {r["name"]: r for r in records}
        luanda = by["Luanda"]
        # Luanda (5th, 50000) + Icolo e Bengo (20th, 200000)
        self.assertEqual(sum(b["count"] for b in luanda["religion"]), 250000)
        self.assertIn("Luanda and Icolo e Bengo", luanda["religion_note"])
        self.assertEqual(by["Cuanza Norte"]["aliases"], ["Cuanza-Norte"])
        self.assertEqual(sum(b["count"] for b in by["Cabinda"]["ethnicity"]), 10000)
        self.assertNotIn("TOTAL", [b["group"] for b in by["Cabinda"]["language"]])
        # A column read into the wrong slot breaks the partition and refuses.
        with self.assertRaises(SystemExit):
            a.bars("religion", "Bengo", {"TOTAL": 1000, "Catholic": 600, "Islam": 300})
        # Totals that disagree between the two column groups refuse too.
        first = pages.index(next(p for p in pages if p.startswith("Quadro 6.2"))) + 2
        cabinda = next(l for l in pages[first].splitlines() if l.startswith("Cabinda"))
        pages[first] = pages[first].replace(cabinda, cabinda.replace("10[", "11[", 1), 1)
        with self.assertRaises(SystemExit):
            a.build(a.PAGE_BREAK.join(pages))
