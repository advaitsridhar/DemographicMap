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
