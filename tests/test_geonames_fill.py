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


class GeoNamesPlacesElsewhere(unittest.TestCase):
    """A GeoNames place that belongs to the unit beside its polygon is not named."""

    def test_chosica_is_not_named_for_the_region_around_lima(self):
        lima = {"id": "L", "name": "Lima", "largest_settlement": {"status": "not_available"}}
        callao = {"id": "C", "name": "Callao", "largest_settlement": {"status": "not_available"}}
        towns = {"L": {"name": "Chosica", "population": 88_606},
                 "C": {"name": "Callao", "population": 813_264}}
        with mock.patch.object(build_entities, "read_json", return_value=towns):
            filled = build_entities.fill_settlements_from_geonames({"PER": [lima, callao]}, {})
        self.assertEqual(filled, 1)
        self.assertEqual(callao["largest_settlement"], "Callao")
        self.assertEqual(lima["largest_settlement"]["status"], "not_available")
        self.assertIn("Chosica (88,606), is part of Lima Province (Metropolitan Lima)",
                      lima["largest_settlement"]["note"])
        self.assertNotIn("largest_settlement_population", lima)


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


class OwnSeats(unittest.TestCase):
    """A GeoNames seat in the polygon drawn for it is that polygon's place."""

    def seats(self, *places):
        from shapely import STRtree
        from shapely.geometry import Point
        rows = [{"geonameid": str(i), "name": n, "lon": x, "lat": y, "code": c,
                 "iso3": iso3, "population": pop}
                for i, (n, x, y, c, iso3, pop) in enumerate(places)]
        return STRtree([Point(r["lon"], r["lat"]) for r in rows]), rows

    def test_a_seat_counts_in_the_polygon_drawn_for_it(self):
        from shapely.geometry import box
        seats = self.seats(("Minsk", 0.5, 0.5, "PPLC", "BLR", 1_742_124),
                           ("Barysaw", 2.5, 0.5, "PPLA2", "BLR", 133_700))
        city, region = box(0, 0, 1, 1), box(1, 0, 3, 1)
        seat = build_entities.seat_drawn_for(city, "BLR", "Minsk City", seats)
        self.assertEqual((seat["name"], seat["population"]), ("Minsk", 1_742_124))
        lima = self.seats(("Lima", 0.5, 0.5, "PPLC", "PER", 7_737_002))
        self.assertEqual(build_entities.seat_drawn_for(
            city, "PER", "Municipalidad Metropolitana de Lima", lima)["name"], "Lima")
        # Not a polygon named for something else, nor another country's seat.
        self.assertIsNone(build_entities.seat_drawn_for(region, "BLR", "Vitebsk", seats))
        self.assertIsNone(build_entities.seat_drawn_for(city, "RUS", "Minsk City", seats))

    def test_the_seat_replaces_a_smaller_place_only(self):
        seat = {"name": "Minsk", "population": 1_742_124, "geonameid": "625144"}
        village = {"name": "Syenitsa", "population": 5_000, "geonameid": "622274"}
        self.assertIs(build_entities.with_own_seat(village, seat, set()), seat)
        bigger = {"name": "Big", "population": 2_000_000, "geonameid": "1"}
        self.assertIs(build_entities.with_own_seat(bigger, seat, set()), bigger)
        # A place more than the unit carries no figure: it stands.
        unfigured = {"name": "Big", "geonameid": "1"}
        self.assertIs(build_entities.with_own_seat(unfigured, seat, set()), unfigured)
        empty = {"none": "GeoNames lists no populated place that can be shown to stand "
                         "in this unit"}
        self.assertIs(build_entities.with_own_seat(empty, seat, set()), seat)
        # A refusal for a larger place stands; one for a smaller place gives way.
        larger = {"none": "Sarajevo (2,000,000) is more than the unit (413,593): x"}
        smaller = {"none": "Vogosca (900,000) is more than the unit (413,593): x"}
        self.assertIs(build_entities.with_own_seat(larger, seat, set()), larger)
        self.assertIs(build_entities.with_own_seat(smaller, seat, set()), seat)
        # A seat another unit of the level already holds is that unit's.
        self.assertIs(build_entities.with_own_seat(village, seat, {"625144"}), village)

    def test_fill_names_the_seat_of_its_own_unit(self):
        city = {"id": "M", "name": "Minsk City",
                "largest_settlement": {"status": "not_available"}}
        region = {"id": "R", "name": "Minsk",
                  "largest_settlement": {"status": "not_available"}}
        towns = {"M": {"name": "Syenitsa", "population": 5_000, "geonameid": "622274"},
                 "R": {"name": "Barysaw", "population": 133_700, "geonameid": "630429"}}
        seats = {"M": {"name": "Minsk", "population": 1_742_124, "geonameid": "625144",
                       "source": "GeoNames (CC BY 4.0)"}}
        with mock.patch.object(build_entities, "read_json", return_value=towns):
            filled = build_entities.fill_settlements_from_geonames(
                {"BLR": [city, region]}, {}, seats)
        self.assertEqual(filled, 2)
        self.assertEqual(city["largest_settlement"], "Minsk")
        self.assertEqual(city["largest_settlement_population"]["value"], 1_742_124)
        self.assertEqual(region["largest_settlement"], "Barysaw")

    def test_a_seat_another_unit_holds_is_not_counted_twice(self):
        city = {"id": "T", "name": "Tashkent", "largest_settlement": {"status": "not_available"}}
        region = {"id": "TR", "name": "Tashkent Region",
                  "largest_settlement": {"status": "not_available"}}
        towns = {"T": {"name": "Tashkent", "population": 2_500_000, "geonameid": "1512569"},
                 "TR": {"name": "Angren", "population": 126_957, "geonameid": "1514588"}}
        seats = {"TR": {"name": "Tashkent", "population": 2_500_000, "geonameid": "1512569"}}
        with mock.patch.object(build_entities, "read_json", return_value=towns):
            build_entities.fill_settlements_from_geonames({"UZB": [city, region]}, {}, seats)
        self.assertEqual(region["largest_settlement"], "Angren")


class PlacesMovedToTheirOwnUnit(unittest.TestCase):
    def test_hwawon_is_dalseong_gun_s_not_dalseo_gu_s(self):
        dalseo = {"id": "D1", "name": "Dalseo-gu",
                  "largest_settlement": {"status": "not_available"}}
        dalseong = {"id": "D2", "name": "Dalseong-gun",
                    "largest_settlement": {"status": "not_available"}}
        towns = {"D1": {"name": "Hwawŏn", "population": 64_718, "geonameid": "1925943"},
                 "D2": {"none": "GeoNames lists no populated place that can be shown to "
                                "stand in this unit"}}
        with mock.patch.object(build_entities, "read_json", return_value=towns):
            filled = build_entities.fill_settlements_from_geonames(
                {}, {"KOR": [dalseo, dalseong]})
        self.assertEqual(filled, 1)
        self.assertEqual(dalseong["largest_settlement"], "Hwawŏn")
        self.assertEqual(dalseong["largest_settlement_population"]["value"], 64_718)
        self.assertEqual(dalseo["largest_settlement"]["status"], "not_available")
        self.assertIn("Hwawŏn (64,718), is part of Dalseong-gun",
                      dalseo["largest_settlement"]["note"])

    def test_a_unit_whose_reason_is_not_geonames_keeps_it(self):
        dalseo = {"id": "D1", "name": "Dalseo-gu",
                  "largest_settlement": {"status": "not_available"}}
        dalseong = {"id": "D2", "name": "Dalseong-gun",
                    "largest_settlement": {"status": "not_available",
                                           "note": "The census names none."}}
        towns = {"D1": {"name": "Hwawŏn", "population": 64_718, "geonameid": "1925943"},
                 "D2": {"none": "no place with a population"}}
        with mock.patch.object(build_entities, "read_json", return_value=towns):
            build_entities.fill_settlements_from_geonames({}, {"KOR": [dalseo, dalseong]})
        self.assertEqual(dalseong["largest_settlement"]["note"], "The census names none.")


class OwnNameInAnotherSpelling(unittest.TestCase):
    """A town that is its own unit under another spelling or script keeps its name."""

    def unit(self, name, people, parent="P"):
        return {"id": name, "name": name, "parent": parent,
                "population": {"value": people, "year": 2020}}

    def stands(self, town, people, unit, *others):
        units = [unit, *others]
        return build_entities.town_stands(town, people, unit["population"]["value"], unit,
                                          build_entities.drawn_apart(units))

    def test_spellings_and_scripts_of_the_unit_s_own_name(self):
        for town, people, name, unit_people in (
                ("Qui Nhon", 519_208, "Quy Nhon", 290_053),
                ("Thành Phố Bà Rịa", 235_192, "Ba Ria", 108_701),
                ("Thành phố Sông Công", 128_357, "Song Cong", 69_382),
                ("Quận Mười", 399_000, "Quan 10", 234_819),
                ("Quận Mười Một", 332_536, "Quan 11", 209_867),
                ("Lankaran", 89_300, "Lənkəran şəhəri", 51_600),
                ("Yevlakh", 127_400, "Yevlax şəhəri", 65_800),
                ("Zaozërsk", 13_429, "ЗАТО Заозёрск", 7_762),
                ("Ostrovnoy", 4_746, "ЗАТО Островной", 1_508),
                ("Khorramshahr", 330_606, "Khoramshahr", 170_976)):
            self.assertTrue(self.stands(town, people, self.unit(name, unit_people)), name)

    def test_a_town_unit_keeps_its_town_beside_a_unit_named_for_it(self):
        okrug = self.unit("городской округ Слободской", 29_469)
        district = self.unit("Slobodskoy District", 31_891, parent="Q")
        self.assertTrue(self.stands("Slobodskoy", 32_361, okrug, district))
        raduzhny = self.unit("городской округ Радужный", 43_577)
        vladimir = self.unit("Raduzhny", 17_569, parent="V")
        self.assertTrue(self.stands("Raduzhny", 47_679, raduzhny, vladimir))
        mukalla = self.unit("Al Mukalla City", 184_635)
        beside = self.unit("Al Mukalla", 16_748, parent="Q")
        self.assertTrue(self.stands("Mukalla", 594_951, mukalla, beside))
        # Ho Chi Minh City's District 3 is not Hà Giang's Quản Bạ.
        quan3 = self.unit("Quan 3", 190_375)
        quan_ba = self.unit("Quan Ba", 53_476, parent="HG")
        self.assertTrue(self.stands("Quận Ba", 220_375, quan3, quan_ba))
        # Quan 11 is not Quan 1.
        self.assertNotEqual(build_entities.own_key("Quận Mười Một"),
                            build_entities.own_key("Quan 1"))

    def test_a_district_beside_its_city_and_a_part_of_a_city_are_still_refused(self):
        termez = self.unit("Termez", 106_700)
        city = self.unit("Termez city", 213_000, parent="Q")
        self.assertFalse(self.stands("Tirmiz", 182_800, termez, city))
        bukhara = self.unit("Bukhara", 185_000)
        bcity = self.unit("Bukhara city", 280_187, parent="Q")
        self.assertFalse(self.stands("Bukhara", 560_374, bukhara, bcity))
        for town, people, name, unit_people in (
                ("Bratislava", 423_737, "Bratislava I", 47_896),
                ("Jakarta", 8_540_121, "Kota Jakarta Selatan", 2_226_812),
                ("Abeokuta", 735_000, "Abeokuta South", 193_165),
                ("Kano", 4_910_000, "Kano Municipal", 295_605),
                ("Kep", 35_990, "Kaeb", 21_748)):
            self.assertFalse(self.stands(town, people, self.unit(name, unit_people)), name)


class UrbanAreaFigures(unittest.TestCase):
    def test_a_natural_earth_urban_area_says_so(self):
        haifa = {"id": "H", "name": "Haifa", "largest_settlement": "Haifa",
                 "largest_settlement_population": {
                     "value": 1_011_000, "source": "Natural Earth populated places (CC0)"}}
        bern = {"id": "B", "name": "Bern", "largest_settlement": "Bern",
                "largest_settlement_population": {
                    "value": 125_000, "source": "Natural Earth populated places (CC0)"}}
        towns = {"H": {"name": "Haifa", "population": 285_316},
                 "B": {"name": "Bern", "population": 121_631}}
        with mock.patch.object(build_entities, "read_json", return_value=towns):
            noted = build_entities.note_urban_area_figures({"ISR": [haifa], "CHE": [bern]})
        self.assertEqual(noted, 1)
        self.assertEqual(haifa["largest_settlement_population"]["value"], 1_011_000)
        self.assertIn("urban area", haifa["largest_settlement_note"])
        self.assertIn("GeoNames gives Haifa 285,316 people", haifa["largest_settlement_note"])
        self.assertNotIn("largest_settlement_note", bern)
