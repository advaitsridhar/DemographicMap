"""Tests for the join logic in scripts/build_entities.py.

These cover the two bugs that produced wrong *data* rather than a crash: a
dependency overwriting its parent country, and a curated row matching the wrong
shape.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_entities as be  # noqa: E402
import common  # noqa: E402


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
