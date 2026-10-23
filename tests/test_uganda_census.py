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
    def build(self, units, placed, settled=None, straddling=None, subcounties=None,
              admin2=None):
        admin1 = [{"id": f"R{c}", "name": n} for c, n in uc.REGION_NAMES.items()]
        groups = uc.age_groups(1000, AGES, "x")
        districts = [{"code": f"{c}01", "name": f"D{c}", "region": c, "male": 480,
                      "female": 520, "total": 1000, "groups": groups}
                     for c in uc.REGION_NAMES]
        districts += [{"code": "105", "name": "MASAKA", "region": "1", "male": 1, "female": 1,
                       "total": 2, "groups": None},
                      {"code": "124", "name": "LWENGO", "region": "1", "male": 1, "female": 1,
                       "total": 2, "groups": None}]
        fake = types.ModuleType("scripts.fetch_census.uganda_counties")
        fake.PLACED, fake.SETTLED, fake.STRADDLING = placed, settled or {}, straddling or {}
        with mock.patch.dict(sys.modules, {"scripts.fetch_census.uganda_counties": fake}):
            records, report = uc.build(districts[:4], units, admin1, admin2 or [],
                                       subcounties)
        return {r["name"]: r for r in records}, report

    def unit(self, code, name, male=480, female=520, district="101"):
        return {"code": code, "name": name, "region": "1", "district": district, "male": male,
                "female": female, "total": male + female,
                "groups": uc.age_groups(male + female, {k: v * (male + female) // 1000
                                                        for k, v in AGES.items()}, name)}

    def test_regions_from_districts_counties_placed_and_straddling(self):
        admin2 = [{"id": "P1", "name": "Busiro"}, {"id": "P2", "name": "Mityana"},
                  {"id": "P3", "name": "Kampala"}]
        units = [self.unit("1021", "CENTRAL DIVISION"), self.unit("1022", "KAWEMPE DIVISION"),
                 self.unit("1131", "BUSIRO COUNTY")]
        by, _ = self.build(units, {"P1": ["1131"], "P3": ["1021", "1022"]},
                           straddling={"P2": ["BUSUJJU COUNTY"]}, admin2=admin2)
        self.assertEqual(by["Central Region"]["population"]["value"], 1000)
        self.assertIn("1 districts", by["Central Region"]["population_note"])
        self.assertEqual(by["Kampala"]["population"]["value"], 2000)
        self.assertEqual(by["Kampala"]["sex_ratio"]["value"], 923)
        mityana = by["Mityana"]["population"]["note"]
        self.assertIn("Busujju County crosses its line", mityana)
        self.assertIn("and for their sub-counties", mityana)
        self.assertIn("its sub-counties cannot all be shown to lie on one side", mityana)
        self.assertIn("median_age", by["Kampala"])
        note = by["Kampala"]["median_age_note"]
        self.assertIn("overlapping age groups it publishes (0-4, 0-17, 15 and over", note)
        self.assertIn("differenced into disjoint ones", note)
        # Every county says why it has no religion or ethnicity, cited for the notes,
        # but a county that was a district of its own in 2002 leaves religion to
        # uganda_2002.json.
        for name in ("Busiro", "Mityana"):
            self.assertIn("2002 census by district", by[name]["religion"]["note"])
            self.assertIn("this county", by[name]["ethnicity"]["note"])
            cited = [s["field"] for s in by[name]["sources"] if s["name"] == uc.REPORT]
            self.assertEqual(cited, ["religion note/ethnicity note"])
        self.assertNotIn("note", by["Kampala"]["religion"])
        self.assertEqual([s["field"] for s in by["Kampala"]["sources"] if s["name"] == uc.REPORT],
                         ["ethnicity note"])
        self.assertEqual([s["field"] for s in by["Mityana"]["sources"] if s["name"] == uc.SOURCE],
                         ["population note/median_age note/sex_ratio note"])
        central = by["Central Region"]
        self.assertIn("this region", central["ethnicity"]["note"])
        self.assertNotIn("note", central["religion"])
        self.assertEqual([s["field"] for s in central["sources"] if s["name"] == uc.REPORT],
                         ["ethnicity note"])

    def test_two_units_of_one_name_are_named_with_their_districts(self):
        admin2 = [{"id": "P1", "name": "Bukuto"}]
        units = [self.unit("1051", "BUKOTO COUNTY", district="105"),
                 self.unit("1241", "BUKOTO COUNTY", district="124"),
                 self.unit("1271", "KIMAANYA-KABONERA DIVISION", district="127")]
        districts = {"105": "MASAKA", "124": "LWENGO"}
        names = uc.named([units[0], units[1], units[2]],
                         {k: uc.title(v) for k, v in districts.items()})
        self.assertEqual(names, ["Bukoto County (Masaka District)",
                                 "Bukoto County (Lwengo District)",
                                 "Kimaanya-Kabonera Division"])

    def test_a_settled_polygon_adds_whole_units_and_sub_counties(self):
        admin2 = [{"id": "P4", "name": "Buhweju"}]
        units = [self.unit("4201", "BUHWEJU COUNTY")]
        kid = {"level": "subcounty", "district": "RUBIRIZI", "county": "KATERERA COUNTY",
               "name": "KYABAKARA", "male": 100, "female": 100, "total": 200,
               "ages": {k: v // 5 for k, v in AGES.items()}}
        by, _ = self.build(units, {}, settled={"P4": {
            "counties": ["4201"], "subcounties": [["RUBIRIZI", "KATERERA COUNTY", "KYABAKARA"]]}},
            subcounties=[kid], admin2=admin2)
        buhweju = by["Buhweju"]
        self.assertEqual(buhweju["population"]["value"], 1200)
        self.assertIn("Buhweju County and Kyabakara, a sub-county of Katerera County, added up",
                      buhweju["population_note"])
        self.assertIn(uc.WORKBOOK_SOURCE, [s["name"] for s in buhweju["sources"]])
        self.assertIn("median_age", buhweju)

    def test_a_sex_ratio_far_from_the_countrys_says_it_is_the_census_figure(self):
        admin2 = [{"id": "P5", "name": "Bujjumba"}, {"id": "P6", "name": "Busiro"}]
        units = [self.unit("1011", "BUJUMBA COUNTY", male=600, female=400),
                 self.unit("1131", "BUSIRO COUNTY")]
        by, _ = self.build(units, {"P5": ["1011"], "P6": ["1131"]}, admin2=admin2)
        note = by["Bujjumba"]["sex_ratio_note"]
        self.assertIn("The census's own figures, 600 men and 400 women", note)
        self.assertIn("Kalangala's islands counted far more men than women in 2002 too", note)
        self.assertNotIn("sex_ratio_note", by["Busiro"])


class CrosswalkDataTest(unittest.TestCase):
    def test_placed_and_straddling_are_drawn_counties_and_disjoint(self):
        ids = {u["id"] for u in json.loads((SITE / "admin2" / "UGA.units.json").read_text())}
        self.assertFalse(set(uganda_counties.PLACED) - ids)
        self.assertFalse(set(uganda_counties.STRADDLING) - ids)
        self.assertFalse(set(uganda_counties.PLACED) & set(uganda_counties.STRADDLING))
        self.assertFalse(set(uganda_counties.SETTLED) - ids)
        self.assertFalse(set(uganda_counties.SETTLED) & (set(uganda_counties.PLACED)
                                                         | set(uganda_counties.STRADDLING)))
        codes = [c for cs in uganda_counties.PLACED.values() for c in cs]
        codes += [c for e in uganda_counties.SETTLED.values() for c in e["counties"]]
        self.assertEqual(len(codes), len(set(codes)))
        # Butembe's polygon holds parts of Jinja North Division and Kagoma North
        # County, beyond 2 km of its line: it is not Butembe County alone.
        self.assertIn("47994165B27757339786209", uganda_counties.STRADDLING)
        self.assertIn("JINJA NORTH DIVISION",
                      uganda_counties.STRADDLING["47994165B27757339786209"])

    def test_settled_sub_counties_are_the_tables_own(self):
        rows = json.loads((Path(__file__).resolve().parent.parent / "data" / "processed"
                           / "uganda_subcounties.json").read_text())
        keys = {(r["district"], r["county"], r["name"]) for r in rows
                if r["level"] == "subcounty"}
        for entry in uganda_counties.SETTLED.values():
            for part in entry["subcounties"]:
                self.assertIn(tuple(part), keys)


if __name__ == "__main__":
    unittest.main()
