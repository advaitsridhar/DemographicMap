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
