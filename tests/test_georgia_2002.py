import unittest
from unittest import mock

from scripts.fetch_census import georgia as g

class Table22(unittest.TestCase):
    def setUp(self):
        # A table of three regions: a country, a region with a name over two
        # lines and a raion whose name straddles its figures.
        self.raions = {"qedis": "Keda", "dedofliswyaros": "Dedoplis Tskaro",
                       "q. Tbilisis meria": "Tbilisi"}
        self.regions = {"saqarTvelo - sul": "Georgia", "aWaris ar": "Adjara",
                        "raWa-leCxumi da qvemo svaneTi": "Racha"}
        self.lines = [
            "cxrili #22", "mxareebi azerbai- ukrai-",
            "saqarTvelo - sul 60 50 0 0 0 0 0 0 0 0 5",
            "q. Tbilisis meria 20 20 - - - - - - - - -",
            "aWaris ar 25 20 0 0 0 0 0 0 0 0 5",
            "qedis raioni 25 20 - - - - - - - - 5",
            "raWa-leCxumi da",
            "qvemo svaneTi 15 10 0 0 0 0 0 0 0 0 0",
            "dedofliswyaros",
            "15 10 0 0 0 0 0 0 0 0 0",
            "raioni",
        ]

    def parse(self, lines):
        with mock.patch.object(g, "RAION_2002", self.raions), \
                mock.patch.object(g, "REGIONS_2002", self.regions):
            return g.parse_table22(lines)

    def test_rows_and_split_names(self):
        got = self.parse(self.lines)
        self.assertEqual(got["qedis"]["counts"]["Yazidi"], 5)
        self.assertEqual(got["qedis"]["counts"]["Other"], 0)
        self.assertEqual(got["dedofliswyaros"]["total"], 15)
        self.assertEqual(got["raWa-leCxumi da qvemo svaneTi"]["counts"]["Other"], 5)

    def test_a_region_that_is_not_its_rows_stops_the_run(self):
        lines = list(self.lines)
        lines[5] = "qedis raioni 24 20 - - - - - - - - 4"
        with self.assertRaises(SystemExit):
            self.parse(lines)


if __name__ == "__main__":
    unittest.main()
