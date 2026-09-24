"""Eurostat's NUTS-3 rows land only where NUTS-3 is the map's second level."""
import unittest
from unittest import mock

from scripts.fetch_census import eurostat


class SecondLevelOnly(unittest.TestCase):
    def test_a_country_whose_nuts3_is_the_first_level_is_left_out(self):
        rows = [{"country": "FRA", "name": "Ain"}, {"country": "SWE", "name": "Stockholms län"}]
        levels = {"FRA": ("admin2", "fits"), "SWE": ("admin1", "fits")}
        with mock.patch("scripts.fetch_census.cod_ps.which_level",
                        side_effect=lambda iso3, names: levels[iso3]):
            kept = eurostat.second_level_only(rows)
        self.assertEqual([r["name"] for r in kept], ["Ain"])

    def test_a_country_fitting_neither_level_is_left_out(self):
        with mock.patch("scripts.fetch_census.cod_ps.which_level",
                        return_value=(None, "no fit")):
            self.assertEqual(eurostat.second_level_only([{"country": "PRT", "name": "Alto Minho"}]), [])


if __name__ == "__main__":
    unittest.main()
