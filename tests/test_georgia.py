import unittest

from scripts.fetch_census import georgia as g


class Names(unittest.TestCase):
    def test_fold_brings_city_and_municipality_together(self):
        self.assertEqual(g.fold("C. Telavi*"), "telavi")
        self.assertEqual(g.fold("Telavi Municipality"), "telavi")
        self.assertEqual(g.fold("Eredvi Municipality**"), "eredvi")
        self.assertEqual(g.fold("Adjara A.R."), "adjara")

    def test_fold_reads_geostats_spellings_as_the_boundary_files(self):
        self.assertEqual(g.fold("Tqibuli Municipality"), g.fold("Tkibuli"))
        self.assertEqual(g.fold("Dedoplistsqaro Municipality"), g.fold("Dedoplis Tskaro"))
        self.assertEqual(g.fold("Tetritsqaro Municipality"), g.fold("Tetri Sqaro"))
        self.assertEqual(g.fold("Kvareli Municipality"), g.fold("Qvareli"))


class Ages(unittest.TestCase):
    def test_age_band(self):
        self.assertEqual(g.age_band("0-4"), (0, 4))
        self.assertEqual(g.age_band("85 and over"), (85, None))
        self.assertEqual(g.age_band("85+"), (85, None))

    def test_age_values_checks_the_sums(self):
        row = {"groups": {"0-4": 50.0, "5-9": 50.0, "10 and over": 0.0},
               "sex": {"Both sexes": 100.0, "Males": 40.0, "Females": 60.0}}
        got = g.age_values(row, "x")
        self.assertEqual(got["median_age"]["value"], 5.0)
        self.assertEqual(got["sex_ratio"]["value"], 66.7)
        row["sex"]["Males"] = 41.0
        with self.assertRaises(SystemExit):
            g.age_values(row, "x")


class Numbers(unittest.TestCase):
    def test_suppressed_cells_read_as_none(self):
        self.assertIsNone(g.number(".."))
        self.assertIsNone(g.number("…"))
        self.assertEqual(g.number("1 234"), 1234.0)


if __name__ == "__main__":
    unittest.main()
