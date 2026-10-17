"""Tests for the Uganda 2024 census adapter (the dashboard's layers onto the drawn counties),
no network."""

import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import uganda_census as uc  # noqa: E402
from scripts.fetch_census import uganda_counties  # noqa: E402

SITE = Path(__file__).resolve().parent.parent / "site" / "data"


def feature(code, name, male, female, region="1", district="102"):
    pop = {"code": code, "name": name, "district_code": district, "region_code": region,
           "male_popn": male, "female_popn": female,
           "total_popn": None if male is None else str(male + female)}
    return {"type": "Feature", "properties": {"population_data": pop}, "geometry": None}


AGES = {"age_0_4": 150, "age_0_17": 500, "age_15_plus": 600, "age_15_24": 200,
        "age_18_30": 250, "age_18_plus": 500, "age_60_plus": 50, "age_65_plus": 30,
        "age_80_plus": 5}


class AgeGroupsTest(unittest.TestCase):
    def test_overlapping_groups_made_disjoint(self):
        groups = uc.age_groups(1000, AGES, "x")
        self.assertEqual(sum(n for _, _, n in groups), 1000)
        self.assertEqual(groups[1], (5, 14, 250))
        self.assertEqual(groups[2], (15, 17, 100))

    def test_children_and_adults_must_make_the_total(self):
        with self.assertRaises(ValueError):
            uc.age_groups(1000, {**AGES, "age_18_plus": 499}, "x")


class LayerTest(unittest.TestCase):
    def test_a_sliver_drawn_twice_is_one_unit_and_a_unit_without_figures_is_left_out(self):
        data = {"geojson": {"features": [
            feature("1025", "RUBAGA DIVISION", 233934, 176466),
            feature("1025", "RUBAGA DIVISION", 233934, 176466, region="2"),
            feature("3111", "CHEKWI COUNTY", None, None, region="3", district="311")]}}
        with mock.patch.object(uc, "fetch_json", return_value=data):
            units = uc.layer("county")
        self.assertEqual(list(units), ["1025"])
        self.assertEqual(units["1025"]["total"], 410400)

    def test_a_unit_drawn_twice_with_two_counts_stops_the_run(self):
        data = {"geojson": {"features": [feature("1025", "RUBAGA", 1, 2),
                                         feature("1025", "RUBAGA", 1, 3)]}}
        with mock.patch.object(uc, "fetch_json", return_value=data), \
                self.assertRaises(SystemExit):
            uc.layer("county")

    def test_sexes_that_do_not_make_the_total_stop_the_run(self):
        bad = feature("1021", "X", 10, 10)
        bad["properties"]["population_data"]["total_popn"] = "21"
        with mock.patch.object(uc, "fetch_json", return_value={"geojson": {"features": [bad]}}), \
                self.assertRaises(SystemExit):
            uc.layer("county")


class BuildTest(unittest.TestCase):
    def test_regions_from_districts_counties_placed_and_straddling(self):
        admin1 = [{"id": f"R{c}", "name": n} for c, n in uc.REGION_NAMES.items()]
        admin2 = [{"id": "P1", "name": "Kampala"}, {"id": "P2", "name": "Mityana"}]
        groups = uc.age_groups(1000, AGES, "x")
        districts = [{"code": f"{c}01", "name": f"D{c}", "region": c, "male": 480,
                      "female": 520, "total": 1000, "groups": groups}
                     for c in uc.REGION_NAMES]
        units = [{"code": "1021", "name": "CENTRAL DIVISION", "region": "1", "male": 480,
                  "female": 520, "total": 1000, "groups": groups},
                 {"code": "1022", "name": "KAWEMPE DIVISION", "region": "1", "male": 480,
                  "female": 520, "total": 1000, "groups": groups}]
        fake = types.ModuleType("scripts.fetch_census.uganda_counties")
        fake.PLACED = {"P1": ["1021", "1022"]}
        fake.STRADDLING = {"P2": ["BUSUJJU COUNTY"]}
        with mock.patch.dict(sys.modules, {"scripts.fetch_census.uganda_counties": fake}):
            records, report = uc.build(districts, units, admin1, admin2)
        by = {r["name"]: r for r in records}
        self.assertEqual(by["Central Region"]["population"]["value"], 1000)
        self.assertIn("1 districts", by["Central Region"]["population_note"])
        self.assertEqual(by["Kampala"]["population"]["value"], 2000)
        self.assertEqual(by["Kampala"]["sex_ratio"]["value"], 923)
        self.assertIn("Busujju County crosses its line", by["Mityana"]["population"]["note"])
        self.assertIn("median_age", by["Kampala"])


class CrosswalkDataTest(unittest.TestCase):
    def test_placed_and_straddling_are_drawn_counties_and_disjoint(self):
        ids = {u["id"] for u in json.loads((SITE / "admin2" / "UGA.units.json").read_text())}
        self.assertFalse(set(uganda_counties.PLACED) - ids)
        self.assertFalse(set(uganda_counties.STRADDLING) - ids)
        self.assertFalse(set(uganda_counties.PLACED) & set(uganda_counties.STRADDLING))
        codes = [c for cs in uganda_counties.PLACED.values() for c in cs]
        self.assertEqual(len(codes), len(set(codes)))


if __name__ == "__main__":
    unittest.main()
