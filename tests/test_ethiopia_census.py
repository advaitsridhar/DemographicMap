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


def zones_module(names, placed, accepted, shares=None):
    module = types.ModuleType("scripts.fetch_census.ethiopia_zones")
    module.NAMES, module.PLACED, module.ACCEPTED = names, placed, frozenset(accepted)
    module.UNPLACED = []
    module.SHARES = shares or {}
    return module


class ProjectionTest(unittest.TestCase):
    """Two drawn zones in Tigray (A and B) and one in Afar (C)."""

    admin1 = [{"id": "T", "name": "Tigray"}, {"id": "F", "name": "Afar"}]
    admin2 = [{"id": "A", "name": "North", "parent": "T"},
              {"id": "B", "name": "Southern", "parent": "T"},
              {"id": "C", "name": "Zone 1", "parent": "F"}]
    regions = {"tigray": {"name": "Tigray", "total": 1000}, "afar": {"name": "Afar", "total": 50}}

    def run_with(self, weredas, names, placed, accepted, shares=None):
        with mock.patch.dict(sys.modules, {"scripts.fetch_census.ethiopia_zones":
                                           zones_module(names, placed, accepted, shares)}), \
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

    def test_the_same_code_under_a_spelling_alike_is_the_outline(self):
        weredas = {"ET010306": {"name": "Kelete Awelallo", "zone": "ET0103", "total": 117},
                   "ET010307": {"name": "Atsbi", "zone": "ET0103", "total": 50},
                   "ET010308": {"name": "Gimeba town", "zone": "ET0103", "total": 9}}
        # ET010308's outline is another wereda's under its code: not alike.
        names = {"ET010306": "Kilte Awulaelo", "ET010307": "Atsbi", "ET010308": "Tulu Awlia"}
        by, report = self.run_with(weredas, names, {"A": ["ET010306", "ET010307"],
                                                    "B": ["ET010308"]}, set())
        # Kelete Awelallo is its code's outline; Gimeba town, under a code whose
        # outline is another wereda's, goes with its zone's others, all in A.
        self.assertEqual(by["North"]["population"]["value"], 176)
        self.assertFalse(any("Kelete" in line for line in report if "no outline" in line))
        self.assertTrue(any("Gimeba" in line for line in report if "no outline" in line))
        self.assertNotIn("Southern", by)

    def test_a_zone_straddled_by_a_sliver_is_written_naming_it(self):
        weredas = {"ET010101": {"name": "Asgede", "zone": "ET0101", "total": 1000},
                   "ET010102": {"name": "Laelay", "zone": "ET0101", "total": 1000},
                   "ET010201": {"name": "Gonje", "zone": "ET0102", "total": 100}}
        names = {"ET010101": "Asgede", "ET010102": "Laelay", "ET010201": "Gonje"}
        placed = {"A": ["ET010101"], "B": ["ET010102"]}
        # Gonje straddles: 30% of it in A, 70% in B, so placed in neither.
        shares = {"ET010201": {"B": 0.7, "A": 0.3}}
        by, report = self.run_with(weredas, names, placed, set(), shares)
        north = by["North"]
        self.assertEqual(north["population"]["value"], 1000)
        self.assertIn("also takes in part of Gonje wereda, whose people are not in this figure",
                      north["population_note"])
        # B would leave out 70 of its 1,070: more than one in twenty.
        self.assertNotIn("Southern", by)
        self.assertTrue(any(line.startswith("Southern: not written") for line in report))

    def test_a_zone_whose_weredas_spill_beyond_its_line_is_not_written(self):
        weredas = {"ET010101": {"name": "Asgede", "zone": "ET0101", "total": 1000},
                   "ET010102": {"name": "Laelay", "zone": "ET0101", "total": 1000}}
        names = {"ET010101": "Asgede", "ET010102": "Laelay"}
        placed = {"A": ["ET010101", "ET010102"]}
        shares = {"ET010102": {"A": 0.8, "B": 0.2}}
        by, _ = self.run_with(weredas, names, placed, set(), shares)
        self.assertNotIn("North", by)       # 200 of 2,000 lie beyond its line

    def test_a_zone_found_nowhere_blocks_its_region(self):
        weredas = {"ET010101": {"name": "Asgede", "zone": "ET0101", "total": 100},
                   "ET010901": {"name": "Lost", "zone": "ET0109", "total": 5},
                   "ET020101": {"name": "Afambo", "zone": "ET0201", "total": 40}}
        names = {"ET010101": "Asgede", "ET020101": "Afambo"}
        by, _ = self.run_with(weredas, names, {"A": ["ET010101"], "C": ["ET020101"]},
                              {"A", "C"})
        self.assertNotIn("North", by)
        self.assertIn("Zone 1", by)


class PlanTest(unittest.TestCase):
    """The 2007 rows: special weredas, Bahir Dar's note, the seats."""

    def setUp(self):
        def area(total):
            men = total // 2
            return {"total": total, "men": men, "women": total - men,
                    "groups": [(0, 14, total // 2), (15, None, total - total // 2)]}
        self.admin1 = json.loads((SITE / "admin1" / "ETH.units.json").read_text())
        self.admin2 = json.loads((SITE / "admin2" / "ETH.units.json").read_text())
        self.table = {"regions": {}, "zones": {}, "labels": {}}
        for shape in self.admin1:
            for key in ec.REGIONS[shape["name"].strip()]:
                self.table["regions"][key] = area(1000)
                self.table["labels"][key] = shape["name"]
        region_of = {s["id"]: ec.REGIONS[s["name"].strip()] for s in self.admin1}
        for shape in self.admin2:
            label = shape["name"].strip()
            if label in ec.WHOLE:
                continue
            zone = ec.ZONES.get(label, ec.fold(label))
            region = region_of[shape["parent"]][0]
            self.table["zones"][(region, zone)] = area(500)
            for extra in ec.SPECIAL.get(label, []):
                self.table["zones"][(region, extra)] = area(50)
        self.table["zones"][("amara", "bahirdarspecialwereda")] = area(221_991)
        self.records, self.report = ec.plan(self.table, self.admin1, self.admin2)
        self.by = {(r["level"], r["name"]): r for r in self.records}

    def test_mao_komo_is_added_to_asosa(self):
        asosa = self.by[("admin2", "Asosa")]
        self.assertEqual(asosa["population"]["value"], 550)
        self.assertIn("the Mao-Komo special wereda added", asosa["population_note"])

    def test_bahir_dar_is_said_to_be_in_neither_zone(self):
        for zone, other in (("West Gojam", "North Gonder"), ("North Gonder", "West Gojam")):
            note = self.by[("admin2", zone)]["population_note"]
            self.assertIn("Bahir Dar, which the census counted apart (221,991 people)", note)
            self.assertIn(f"nor {other}'s", note)
            self.assertIn("most of its area in West Gojam", note)

    def test_the_chartered_cities_and_snnpr_have_seats(self):
        self.assertEqual(self.by[("admin1", "Addis Ababa")]["capital"], "Addis Ababa")
        self.assertEqual(self.by[("admin2", "Region 14")]["capital"], "Addis Ababa")
        self.assertEqual(self.by[("admin1", "Dire Dawa")]["capital"], "Dire Dawa")
        self.assertEqual(self.by[("admin2", "Hareri")]["capital"], "Harar")
        snnpr = self.by[("admin1", "SNNPR")]
        self.assertEqual(snnpr["capital"], "Hawassa")
        self.assertIn("until the region was divided in 2023", snnpr["capital_note"])
        self.assertTrue(any(s["field"] == "capital" for s in snnpr["sources"]))
        self.assertIsInstance(self.by[("admin1", "Afar")]["capital"], dict)


class DataTest(unittest.TestCase):
    """The constants and the generated placement name the map's real units."""

    def test_zone_labels_are_drawn_zones(self):
        labels = {u["name"].strip() for u in
                  json.loads((SITE / "admin2" / "ETH.units.json").read_text())}
        for table in (ec.ZONES, ec.WHOLE, ec.SPECIAL, ec.PROJECTION_WHOLE):
            self.assertFalse(set(table) - labels, table)
        for zones in ec.UNPLACED_ON.values():
            self.assertFalse(set(zones) - labels)
        regions = {u["name"].strip() for u in
                   json.loads((SITE / "admin1" / "ETH.units.json").read_text())}
        for level, label in ec.CAPITALS:
            self.assertIn(label, labels if level == "admin2" else regions)

    def test_shares_name_drawn_zones(self):
        ids = {u["id"] for u in json.loads((SITE / "admin2" / "ETH.units.json").read_text())}
        for code, shares in ethiopia_zones.SHARES.items():
            self.assertFalse(set(shares) - ids, code)
            self.assertLessEqual(sum(shares.values()), 1.03, code)

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
