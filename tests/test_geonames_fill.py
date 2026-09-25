"""GeoNames' seats and settlements: what the build takes, and what it says when it takes nothing."""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_entities  # noqa: E402
import fetch_geonames  # noqa: E402

KALTENG = "IDN-B1"


def unit(**fields):
    return {"id": KALTENG, "name": "Central Kalimantan", "country": "IDN",
            "level": "admin1", **fields}


class Capitals(unittest.TestCase):
    SEATS = {KALTENG: {"refutes": "Banjarmasin", "seat": "Palangkaraya"}}

    def fill(self, entity, seats):
        with mock.patch.object(build_entities, "read_json", return_value=seats):
            build_entities.fill_capitals_from_geonames({"IDN": [entity]}, {})
        return entity

    def test_a_refuted_capital_is_replaced_and_kept_for_the_next_placement(self):
        entity = self.fill(unit(capital="Banjarmasin"), self.SEATS)
        self.assertEqual(entity["capital"], "Palangkaraya")
        self.assertEqual(entity["capital_refuted"], "Banjarmasin")
        self.assertIn("Banjarmasin", entity["capital_note"])

    def test_the_placement_still_refutes_it_after_a_build_corrected_it(self):
        # The built unit now says Palangkaraya; judged on that alone there is
        # nothing to refute, and the next build would restore Banjarmasin.
        built = unit(capital="Palangkaraya", capital_refuted="Banjarmasin")
        inside = {KALTENG: [{"name": "Palangkaraya", "code": "PPLA"},
                            {"name": "Sampit", "code": "PPLA2"}]}
        places = [{"iso3": "IDN", "name": "Banjarmasin"}, {"iso3": "IDN", "name": "Palangkaraya"}]
        with mock.patch.object(fetch_geonames, "site_units", return_value=({KALTENG: built}, {})):
            out = fetch_geonames.refuted("ADM1", inside, places)
        self.assertEqual(out, {KALTENG: {"refutes": "Banjarmasin", "seat": "Palangkaraya"}})

    def test_a_bare_wikidata_id_is_replaced_and_a_named_capital_is_not(self):
        seats = {KALTENG: {"name": "Palangkaraya"}}
        self.assertEqual(self.fill(unit(capital="Q139491508"), seats)["capital"], "Palangkaraya")
        self.assertEqual(self.fill(unit(capital="Sampit"), seats)["capital"], "Sampit")


class Settlements(unittest.TestCase):
    def fill(self, entity, towns):
        with mock.patch.object(build_entities, "read_json", return_value=towns):
            build_entities.fill_settlements_from_geonames({"IDN": [entity]}, {})
        return entity

    def test_a_unit_with_no_place_named_says_why(self):
        why = "Hangzhou (11,936,010) is more than the unit (1,170,000): a city it is part of"
        entity = self.fill(unit(largest_settlement={"status": "not_available"}),
                           {KALTENG: {"none": why}})
        self.assertEqual(entity["largest_settlement"]["status"], "not_available")
        self.assertIn(why, entity["largest_settlement"]["note"])

    def test_a_reason_already_given_is_kept(self):
        held = {"status": "not_available", "note": "the census names none"}
        entity = self.fill(unit(largest_settlement=dict(held)), {KALTENG: {"none": "no place"}})
        self.assertEqual(entity["largest_settlement"], held)

    def test_a_named_place_fills_the_gap(self):
        entity = self.fill(unit(largest_settlement={"status": "not_available"}),
                           {KALTENG: {"name": "Palangkaraya", "population": 293457}})
        self.assertEqual(entity["largest_settlement"], "Palangkaraya")
        self.assertEqual(entity["largest_settlement_population"]["value"], 293457)


if __name__ == "__main__":
    unittest.main()
