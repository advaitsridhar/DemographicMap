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

    def test_a_place_an_adapter_named_without_its_figure_gets_none(self):
        # Jerusalem District: the adapter names the city and says why no
        # figure is given (every published one counts East Jerusalem, which
        # the map draws in the West Bank). GeoNames' whole-city 971,800 for
        # the same point must not be attached by any later pass.
        why = "The city's population is not shown: it counts East Jerusalem."
        entity = {"id": "ISR-J", "name": "Jerusalem District", "country": "ISR",
                  "level": "admin1", "largest_settlement": {"status": "not_available"},
                  "population": {"status": "not_available", "note": "Not this shape's."},
                  "sources": []}
        build_entities.merge_adapter(entity, {
            "id": "ISR-CBS-J", "level": "admin1", "name": "Jerusalem District",
            "_source": "israel_cbs.json", "largest_settlement": "Jerusalem",
            "largest_settlement_note": why,
            "sources": [{"field": "largest settlement", "name": "GeoNames"}]})
        self.fill(entity, {"ISR-J": {"name": "Jerusalem", "population": 971800}})
        build_entities.settle_settlement_figures({"ISR": [entity]}, {})
        self.assertEqual(entity["largest_settlement"], "Jerusalem")
        self.assertEqual(entity["largest_settlement_note"], why)
        self.assertNotIn("largest_settlement_population", entity)
        self.assertEqual(len(entity["sources"]), 1)


class NaturalEarthPlaces(unittest.TestCase):
    """Natural Earth files a place under a first-level unit by the unit's name;
    the place's point decides whether it is that unit's."""

    def setUp(self):
        from shapely.geometry import box
        from shapely.strtree import STRtree
        # Daegu, a small polygon, and North Gyeongsang around it to the east.
        self.daegu = {"name": "Daegu", "_geom": box(0, 0, 1, 1)}
        self.gyeongbuk = {"name": "North Gyeongsang", "_geom": box(1, 0, 3, 1)}
        self.city = {"name": "Seoul Special City", "_geom": box(-1, 0, 0, 1)}
        rows = [self.daegu, self.gyeongbuk, self.city]
        self.held = (STRtree([r["_geom"] for r in rows]), rows)

    def why(self, name, x, y):
        return build_entities.natural_earth_elsewhere(
            {"name": name, "coordinates": [x, y]}, self.daegu, self.held)

    def test_a_place_inside_the_unit_stands(self):
        self.assertIsNone(self.why("Daegu", 0.5, 0.5))

    def test_a_place_well_inside_another_unit_is_that_unit_s(self):
        # Pohang, filed under Daegu, 60 km into North Gyeongsang.
        self.assertEqual(self.why("Pohang", 1.6, 0.5), "inside North Gyeongsang")

    def test_a_place_just_across_a_simplified_border_stands(self):
        # Neuquén's point sits 0.11 degrees into Río Negro's polygon.
        self.assertIsNone(self.why("Riverside", 1.1, 0.5))

    def test_a_place_drawn_as_a_unit_of_its_own_is_that_unit_s(self):
        self.assertEqual(self.why("Seoul", -0.05, 0.5),
                         "drawn as a unit of its own, Seoul Special City")

    def test_a_place_in_no_polygon_stands(self):
        # Fortaleza, off a simplified coast.
        self.assertIsNone(self.why("Harbour", 0.5, 1.05))

    def test_a_metropolitan_or_autonomous_district_is_drawn_for_its_city(self):
        from shapely.geometry import box
        from shapely.strtree import STRtree
        lagunes = {"group": "CIV", "name": "Lagunes", "_geom": box(0, 0, 1, 1)}
        for name, city in (("District Autonome D'Abidjan", "Abidjan"),
                           ("District Autonome D’Abidjan", "Abidjan"),
                           ("Municipalidad Metropolitana de Lima", "Lima")):
            district = {"name": name, "_geom": box(1, 0, 2, 1)}
            rows = [lagunes, district]
            held = (STRtree([r["_geom"] for r in rows]), rows)
            # 0.05 degrees across the line: too close for the distance alone.
            self.assertEqual(build_entities.natural_earth_elsewhere(
                {"name": city, "coordinates": [1.05, 0.5]}, lagunes, held),
                f"drawn as a unit of its own, {name}")
        # The join's own reading is unchanged: a metropolitan area is a
        # different place from the city inside it.
        self.assertFalse(build_entities.related(
            build_entities.name_forms("Lisboa"),
            build_entities.name_forms("Area Metropolitana de Lisboa")))
        self.assertFalse(build_entities.drawn_for("Abidjan", "District Autonome De Yamoussoukro"))
        self.assertFalse(build_entities.drawn_for("Lima", "Callao"))

    def test_a_place_filed_under_its_neighbour_is_refused_by_name(self):
        # Tirana, filed under Durrës, 0.11 degrees inside Tiranë; and only
        # that place: Durrës's own town is not refused.
        durres = {"group": "ALB", "name": "Durrës", "_geom": self.daegu["_geom"]}
        why = build_entities.natural_earth_elsewhere(
            {"name": "Tirana", "coordinates": [1.1, 0.5]}, durres, self.held)
        self.assertEqual(why, "a place of Tiranë")
        self.assertIsNone(build_entities.natural_earth_elsewhere(
            {"name": "Durrës", "coordinates": [0.5, 0.5]}, durres, self.held))
        for (iso3, unit, place), where in build_entities.NATURAL_EARTH_MISFILED.items():
            self.assertNotEqual(unit, where.split(",")[0], (iso3, unit, place))


if __name__ == "__main__":
    unittest.main()
