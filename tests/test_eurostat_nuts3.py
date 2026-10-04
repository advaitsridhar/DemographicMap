"""Eurostat's NUTS-3 rows land at the level their names are; grouped regions nowhere."""
import unittest
from unittest import mock

from scripts.fetch_census import eurostat


class ByLevel(unittest.TestCase):
    def test_each_country_is_kept_at_the_level_its_names_are(self):
        rows = [{"country": "FRA", "name": "Ain"}, {"country": "SWE", "name": "Stockholms län"}]
        levels = {"FRA": ("admin2", "fits"), "SWE": ("admin1", "fits")}
        with mock.patch("scripts.fetch_census.cod_ps.which_level",
                        side_effect=lambda iso3, names: levels[iso3]):
            kept = eurostat.by_level(rows)
        self.assertEqual([(r["name"], r["level"]) for r in kept],
                         [("Ain", "admin2"), ("Stockholms län", "admin1")])

    def test_a_country_fitting_neither_level_is_left_out(self):
        with mock.patch("scripts.fetch_census.cod_ps.which_level",
                        return_value=(None, "no fit")):
            self.assertEqual(eurostat.by_level([{"country": "PRT", "name": "Alto Minho"}]), [])


class LevelFromOutlines(unittest.TestCase):
    def test_a_tied_country_takes_the_level_its_outlines_placed(self):
        # Albania: names tie between levels; 11 placed at admin1, Lezhe left.
        placed = [{"id": f"EU-AL0{i}", "country": "ALB", "level": "admin1"} for i in range(11)]
        left = [{"id": "EU-AL014", "country": "ALB", "level": "admin2"}]
        with mock.patch.object(eurostat, "log"):
            out = eurostat.level_from_outlines(placed, left, {})
        self.assertEqual(out, {"EU-AL014": "admin1"})

    def test_a_decided_row_keeps_its_level(self):
        placed = [{"id": "EU-X1", "country": "ESP", "level": "admin2"}]
        left = [{"id": "EU-X2", "country": "ESP", "level": "admin2"}]
        self.assertEqual(eurostat.level_from_outlines(placed, left, {"EU-X2": "admin1"}),
                         {"EU-X2": "admin1"})

    def test_too_few_placed_or_mixed_levels_settle_nothing(self):
        few = [{"id": "EU-P1", "country": "PRT", "level": "admin1"}]
        left = [{"id": f"EU-P{i}", "country": "PRT", "level": "admin2"} for i in range(2, 4)]
        self.assertEqual(eurostat.level_from_outlines(few, left, {}), {})
        mixed = [{"id": "EU-M1", "country": "MKD", "level": "admin1"},
                 {"id": "EU-M2", "country": "MKD", "level": "admin2"},
                 {"id": "EU-M3", "country": "MKD", "level": "admin1"}]
        self.assertEqual(eurostat.level_from_outlines(mixed, [{"id": "EU-M4", "country": "MKD",
                                                               "level": "admin2"}], {}), {})


class JoinedUnits(unittest.TestCase):
    def test_a_region_holding_a_drawn_unit_and_more_is_left_out(self):
        from scripts.fetch_census import cod_ps
        names = {cod_ps.level_key(n) for n in (
            "Aberdeen City", "Aberdeenshire", "Perth and Kinross", "Stirling",
            "Dumfries and Galloway", "Brighton and Hove", "Edinburgh")}
        rows = [{"country": "GBR", "level": "admin2", "name": n} for n in (
            "Aberdeen City and Aberdeenshire (NUTS 2021)",
            "Perth & Kinross and Stirling (NUTS 2021)",
            "Dumfries & Galloway (NUTS 2021)", "Brighton and Hove (NUTS 2021)",
            "Edinburgh, City of (NUTS 2021)", "Lancaster & Wyre (NUTS 2021)")]
        with mock.patch("scripts.fetch_census.cod_ps.shape_names", return_value=names):
            kept = [r["name"] for r in eurostat.joined_units(rows)]
        self.assertEqual(kept, ["Dumfries & Galloway (NUTS 2021)",
                                "Brighton and Hove (NUTS 2021)",
                                "Edinburgh, City of (NUTS 2021)",
                                "Lancaster & Wyre (NUTS 2021)"])


    def test_a_region_of_several_provinces_is_not_its_first(self):
        # TRC2 read as Sanliurfa gave the province Diyarbakir's people too.
        from scripts.fetch_census import cod_ps
        names = {cod_ps.level_key(n) for n in ("Şanlıurfa", "Diyarbakır", "İstanbul")}
        rows = [{"country": "TUR", "level": "admin1", "name": n}
                for n in ("Şanlıurfa, Diyarbakır", "İstanbul")]
        with mock.patch("scripts.fetch_census.cod_ps.shape_names", return_value=names):
            kept = [r["name"] for r in eurostat.joined_units(rows)]
        self.assertEqual(kept, ["İstanbul"])


class WholeCountry(unittest.TestCase):
    def test_a_countrys_only_region_is_not_a_division(self):
        for geo in ("LU00", "LU000", "MT00", "CY000"):
            self.assertTrue(eurostat.whole_country(geo), geo)

    def test_a_region_is(self):
        for geo in ("FR10", "PT11", "ES300", "NL00A", "LU"):
            self.assertFalse(eurostat.whole_country(geo), geo)


if __name__ == "__main__":
    unittest.main()
