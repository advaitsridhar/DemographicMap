"""Tests for the Ethiopia adapter: the 2007 census rows and the 2022 projection by zone, no
network."""

import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import ethiopia_census as ec  # noqa: E402
from scripts.fetch_census import ethiopia_zones  # noqa: E402

SITE = Path(__file__).resolve().parent.parent / "site" / "data"
HEAD = ["ADM_LEVEL", "ADM1_NAME", "ADM2_NAME", "BTOTL", "MTOTL", "FTOTL", "B0004", "B0509",
        "B10PL"]


class RowsTest(unittest.TestCase):
    def at(self):
        return {n: i for i, n in enumerate(HEAD)}

    def test_a_row_checks_its_groups_and_sexes(self):
        row = [2, "Afar", "Zone 1", 100, 55, 45, 30, 30, 40]
        got = ec.area(row, self.at(), "Afar, Zone 1")
        self.assertEqual(got["groups"], [(0, 4, 30), (5, 9, 30), (10, None, 40)])
        with self.assertRaises(SystemExit):
            ec.area([2, "Afar", "Zone 1", 100, 55, 44, 30, 30, 40], self.at(), "x")

    def test_a_negative_total_is_the_missing_marker(self):
        self.assertTrue(ec.missing([2, "Oromiya", "Finfinne", -999, 0, 0, 0, 0, 0], self.at()))
        self.assertFalse(ec.missing([2, "Afar", "Zone 1", 5, 3, 2, 1, 1, 3], self.at()))

    def test_areas_add_group_by_group(self):
        a = ec.area([2, "", "", 10, 5, 5, 4, 3, 3], self.at(), "a")
        b = ec.area([2, "", "", 20, 9, 11, 8, 6, 6], self.at(), "b")
        self.assertEqual(ec.added([a, b])["groups"], [(0, 4, 12), (5, 9, 9), (10, None, 9)])


class BareTest(unittest.TestCase):
    def test_labels_and_brackets_go_but_a_town_stays_a_town(self):
        self.assertEqual(ec.bare("Tembaro Special"), "tembaro")
        self.assertEqual(ec.bare("Basketo SP Woreda"), "basketo")
        self.assertEqual(ec.bare("Awra (TG)"), "awra")
        self.assertEqual(ec.bare("Sebeta town"), "sebetatown")


def zones_module(names, placed, accepted):
    module = types.ModuleType("scripts.fetch_census.ethiopia_zones")
    module.NAMES, module.PLACED, module.ACCEPTED = names, placed, frozenset(accepted)
    module.UNPLACED = []
    return module


class ProjectionTest(unittest.TestCase):
    """Two drawn zones in Tigray (A and B) and one in Afar (C)."""

    admin1 = [{"id": "T", "name": "Tigray"}, {"id": "F", "name": "Afar"}]
    admin2 = [{"id": "A", "name": "North", "parent": "T"},
              {"id": "B", "name": "Southern", "parent": "T"},
              {"id": "C", "name": "Zone 1", "parent": "F"}]
    regions = {"tigray": {"name": "Tigray", "total": 1000}, "afar": {"name": "Afar", "total": 50}}

    def run_with(self, weredas, names, placed, accepted):
        with mock.patch.dict(sys.modules, {"scripts.fetch_census.ethiopia_zones":
                                           zones_module(names, placed, accepted)}), \
                mock.patch.object(ec, "PROJECTION_REGIONS",
                                  {"Tigray": ["tigray"], "Afar": ["afar"]}), \
                mock.patch.object(ec, "PROJECTION_WHOLE", {}):
            records, report = ec.projection_records(self.regions, weredas, "https://page",
                                                    self.admin1, self.admin2)
        return {r["name"]: r for r in records}, report

    def test_weredas_matched_by_code_name_and_bare_name_are_summed_into_their_zone(self):
        weredas = {"ET010101": {"name": "Asgede", "zone": "ET0101", "total": 100},
                   "ET010102": {"name": "Tahtay Koraro", "zone": "ET0101", "total": 50},
                   "ET010103": {"name": "Tsegede (TG)", "zone": "ET0101", "total": 30},
                   "ET020101": {"name": "Afambo", "zone": "ET0201", "total": 40}}
        names = {"ET010101": "Asgede Tsimbla", "ET010199": "Tahtay Koraro",
                 "ET990105": "Tsegede", "ET020101": "Afambo"}
        placed = {"A": ["ET010101", "ET010199", "ET990105"], "C": ["ET020101"]}
        by, _ = self.run_with(weredas, names, placed, {"A", "C"})
        self.assertEqual(by["North"]["population"]["value"], 180)
        self.assertIn("3 weredas", by["North"]["population_note"])
        self.assertEqual(by["Zone 1"]["population"]["value"], 40)
        self.assertEqual(by["Tigray"]["population"]["value"], 1000)

    def test_an_unmatched_wereda_goes_with_its_zone_when_the_zone_lies_in_one_drawn_zone(self):
        weredas = {"ET010101": {"name": "Asgede", "zone": "ET0101", "total": 100},
                   "ET010108": {"name": "New town", "zone": "ET0101", "total": 7}}
        names = {"ET010101": "Asgede"}
        by, report = self.run_with(weredas, names, {"A": ["ET010101"]}, {"A"})
        self.assertEqual(by["North"]["population"]["value"], 107)
        self.assertTrue(any("placed with the zone's other weredas" in line for line in report))

    def test_a_zone_split_between_drawn_zones_blocks_both_when_a_wereda_is_unmatched(self):
        weredas = {"ET010101": {"name": "Asgede", "zone": "ET0101", "total": 100},
                   "ET010102": {"name": "Laelay", "zone": "ET0101", "total": 60},
                   "ET010108": {"name": "New town", "zone": "ET0101", "total": 7}}
        names = {"ET010101": "Asgede", "ET010102": "Laelay"}
        by, report = self.run_with(weredas, names, {"A": ["ET010101"], "B": ["ET010102"]},
                                   {"A", "B"})
        self.assertNotIn("North", by)
        self.assertNotIn("Southern", by)

    def test_a_wholly_unmatched_zone_is_found_by_its_code(self):
        weredas = {"ET010401": {"name": "Alamata", "zone": "ET0104", "total": 90},
                   "ET010701": {"name": "Mekelle", "zone": "ET0107", "total": 186}}
        names = {"ET010401": "Alamata", "ET010702": "Hadnet", "ET010703": "Ayder"}
        by, _ = self.run_with(weredas, names, {"B": ["ET010401", "ET010702", "ET010703"]},
                              {"B"})
        self.assertEqual(by["Southern"]["population"]["value"], 276)

    def test_a_zone_found_nowhere_blocks_its_region(self):
        weredas = {"ET010101": {"name": "Asgede", "zone": "ET0101", "total": 100},
                   "ET010901": {"name": "Lost", "zone": "ET0109", "total": 5},
                   "ET020101": {"name": "Afambo", "zone": "ET0201", "total": 40}}
        names = {"ET010101": "Asgede", "ET020101": "Afambo"}
        by, _ = self.run_with(weredas, names, {"A": ["ET010101"], "C": ["ET020101"]},
                              {"A", "C"})
        self.assertNotIn("North", by)
        self.assertIn("Zone 1", by)


class DataTest(unittest.TestCase):
    """The constants and the generated placement name the map's real units."""

    def test_zone_labels_are_drawn_zones(self):
        labels = {u["name"].strip() for u in
                  json.loads((SITE / "admin2" / "ETH.units.json").read_text())}
        for table in (ec.ZONES, ec.WHOLE, ec.SPECIAL, ec.PROJECTION_WHOLE):
            self.assertFalse(set(table) - labels, table)

    def test_regions_are_drawn_regions(self):
        names = {u["name"].strip() for u in
                 json.loads((SITE / "admin1" / "ETH.units.json").read_text())}
        self.assertEqual(set(ec.PROJECTION_REGIONS), names)
        self.assertEqual(set(ec.REGIONS), names)
        self.assertEqual(set(ec.REGION_CODES), names)

    def test_placement_is_of_drawn_zones(self):
        ids = {u["id"] for u in json.loads((SITE / "admin2" / "ETH.units.json").read_text())}
        self.assertFalse(set(ethiopia_zones.PLACED) - ids)
        self.assertTrue(set(ethiopia_zones.ACCEPTED) <= set(ethiopia_zones.PLACED))


if __name__ == "__main__":
    unittest.main()
