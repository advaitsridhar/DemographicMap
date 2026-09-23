"""Regression checks for failures that previously produced misleading builds."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class BuildGuards(unittest.TestCase):
    def test_cocos_and_cook_islands_do_not_share_a_code(self):
        import fetch_factbook

        self.assertEqual(fetch_factbook.MANUAL_CODE_ISO["ck"], "CCK")

    def test_secondary_territory_profiles_are_retained(self):
        import build_entities

        rows = [
            {"id": "PSE", "name": "Gaza", "codes": {"iso3": "PSE"}},
            {"id": "PSE-WE", "name": "West Bank", "codes": {"iso3": "PSE"}},
        ]
        primary = build_entities.primary_country_profiles(rows)
        kept = build_entities.geometryless_profiles(rows, primary, {"PSE"})
        self.assertEqual([row["id"] for row in kept], ["PSE-WE"])
        self.assertEqual(kept[0]["codes"]["iso3"], "PSE")

    def test_a_secondary_profile_owns_no_subdivisions(self):
        """The Coral Sea Islands must not be handed Australia's 547 districts."""
        import build_entities

        primary = {"id": "AUS", "country": "AUS", "name": "Australia"}
        secondary = {"id": "AUS-CR", "country": "AUS", "name": "Coral Sea Islands"}
        self.assertEqual(build_entities.subdivision_owner(primary), "AUS")
        self.assertIsNone(build_entities.subdivision_owner(secondary))

    def test_a_geometryless_primary_still_owns_its_subdivisions(self):
        """Having no polygon is not the same as being a secondary profile."""
        import build_entities

        hong_kong = {"id": "HKG", "country": "HKG", "name": "Hong Kong"}
        self.assertEqual(build_entities.subdivision_owner(hong_kong), "HKG")

    def test_the_frontend_only_loads_children_for_a_primary_profile(self):
        source = (ROOT / "site" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('record.country === record.id', source)
        self.assertNotIn('loadLevel(record.country || record.id, 1)', source)

    def test_tile_failure_is_fatal_to_the_pipeline(self):
        source = (ROOT / "scripts" / "build_all.sh").read_text(encoding="utf-8")
        self.assertIn("scripts/build_tiles.sh || exit 1", source)

    def test_tippecanoe_does_not_disable_compression_with_a_value(self):
        source = (ROOT / "scripts" / "build_tiles.sh").read_text(encoding="utf-8")
        self.assertNotIn("--no-tile-compression", source)

    def test_commit_checkbox_is_used_as_a_boolean(self):
        source = (ROOT / ".github" / "workflows" / "run-adapter.yml").read_text(encoding="utf-8")
        self.assertIn("if: always() && inputs.commit\n", source)
        self.assertNotIn("inputs.commit != 'false'", source)

    def test_pmtiles_download_is_pinned_and_fails_on_http_errors(self):
        source = (ROOT / ".github" / "workflows" / "refresh-data.yml").read_text(encoding="utf-8")
        self.assertIn("PMTILES_VERSION: \"1.31.2\"", source)
        self.assertIn("curl --fail", source)
        self.assertIn("Linux_x86_64.tar.gz", source)


if __name__ == "__main__":
    unittest.main()


class APolygonTheBoundaryFileMislabels(unittest.TestCase):
    """Belarus labels Minsk Region's polygon plain "Minsk"."""

    def setUp(self):
        import build_entities
        self.b = build_entities
        self.shapes = [{"id": "region", "name": "Minsk"},
                       {"id": "city", "name": "Minsk City"},
                       {"id": "brest", "name": "Brest"}]

    def test_the_city_s_row_goes_to_the_city_s_polygon(self):
        row = self.b.placed("BLR", {"name": "Minsk", "wikidata": "Q2280"}, self.shapes)
        self.assertEqual((row["match_by"], row["shape_id"]), ("shape_id", "city"))
        # Named as the polygon is, so the binding never relabels a shape.
        self.assertEqual(row["name"], "Minsk City")
        self.assertIn("Minsk", row["aliases"])

    def test_the_region_s_row_goes_to_the_region_s_polygon(self):
        row = self.b.placed("BLR", {"name": "Minsk region", "wikidata": "Q192959"},
                            self.shapes)
        self.assertEqual(row["shape_id"], "region")

    def test_every_other_row_is_left_alone(self):
        for row in ({"name": "Brest", "wikidata": "Q173822"},
                    {"name": "Minsk"},
                    {"name": "Minsk", "wikidata": "Q2280", "country": "UKR"}):
            iso3 = row.get("country", "BLR")
            self.assertIs(self.b.placed(iso3, row, self.shapes), row)

    def test_a_label_no_longer_drawn_stops_the_build(self):
        with self.assertRaises(SystemExit):
            self.b.placed("BLR", {"name": "Minsk", "wikidata": "Q2280"},
                          [{"id": "x", "name": "Minsk"}])


class APolygonDrawnAtBothLevels(unittest.TestCase):
    """Malta's 68 localities are drawn at admin1 and admin2 under one id."""

    def setUp(self):
        import build_entities
        self.b = build_entities
        self.a1 = {"id": "83640313B93037213409403", "level": "admin1", "name": "Attard"}
        self.a2 = {"id": "83640313B93037213409403", "level": "admin2", "name": "Attard"}
        self.nepal = {"id": "NPL-ADM2-7", "level": "admin2", "name": "Bara"}
        entities = [self.a1, self.a2, self.nepal]
        self.by_shape = {e["id"]: e for e in entities}
        self.by_level = {(e["level"], e["id"]): e for e in entities}

    def test_a_first_level_row_lands_on_the_first_level(self):
        got = self.b.bound(self.by_shape, self.by_level, self.a1["id"], "admin1")
        self.assertIs(got, self.a1)

    def test_a_second_level_row_lands_on_the_second_level(self):
        got = self.b.bound(self.by_shape, self.by_level, self.a1["id"], "admin2")
        self.assertIs(got, self.a2)

    def test_an_id_drawn_at_one_level_is_found_whatever_the_row_says(self):
        # What a binding meant before, and still means for Nepal's.
        for level in ("admin2", "admin1", None):
            self.assertIs(self.b.bound(self.by_shape, self.by_level,
                                       "NPL-ADM2-7", level), self.nepal)

    def test_an_id_not_drawn_at_all_is_none(self):
        self.assertIsNone(self.b.bound(self.by_shape, self.by_level, "nope", "admin1"))


class AnEncyclopaediaNeverReplacesACount(unittest.TestCase):
    """Viet Nam's 2019 census, overwritten by Wikidata's post-merger figures."""

    def setUp(self):
        import build_entities
        self.b = build_entities
        self.census = {"value": 1908352, "year": 2019,
                       "source": "General Statistics Office of Viet Nam"}

    def entity(self):
        return {"population": dict(self.census),
                "sources": [{"field": "population", "name": "GSO"}]}

    def test_wikidata_fills_nothing_that_is_already_counted(self):
        e = self.entity()
        self.b.merge_adapter(e, {
            "_source": "wikidata_admin1.json", "capital": "Long Xuyen",
            "population": {"value": 3679300, "year": 2024, "source": "Wikidata (CC0)"},
            "sources": [{"field": "population/capital/coordinates", "name": "Wikidata"},
                        {"field": "population", "name": "Wikidata"}]})
        self.assertEqual(e["population"], self.census)
        # The census citation stays, and a citation for a figure that was
        # held back is not added.
        self.assertIn({"field": "population", "name": "GSO"}, e["sources"])
        self.assertNotIn({"field": "population", "name": "Wikidata"}, e["sources"])
        # Everything else Wikidata says still lands.
        self.assertEqual(e["capital"], "Long Xuyen")

    def test_wikidata_still_fills_a_gap(self):
        e = {"population": {"status": "not_available"}, "sources": []}
        pop = {"value": 3679300, "year": 2024, "source": "Wikidata (CC0)"}
        self.b.merge_adapter(e, {"_source": "wikidata_admin1.json", "population": pop})
        self.assertEqual(e["population"], pop)

    def test_the_wikipedia_reader_is_held_to_the_same_rule(self):
        e = self.entity()
        self.b.merge_adapter(e, {"_source": "wiki_population_admin1.json",
                                 "population": {"value": 1, "source": "English Wikipedia, X"}})
        self.assertEqual(e["population"], self.census)

    def test_a_census_file_still_replaces_a_census_file(self):
        e = self.entity()
        newer = {"value": 1950000, "year": 2024, "source": "GSO"}
        self.b.merge_adapter(e, {"_source": "vietnam_province.json", "population": newer})
        self.assertEqual(e["population"], newer)
