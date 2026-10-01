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


class Tbilisi(unittest.TestCase):
    """The municipality polygon of Tbilisi takes the 2014 region rows, not 2002's."""

    def test_region_2014_gives_the_census_year_for_every_field(self):
        ages = {"C. Tbilisi": {"groups": {"0-4": 50.0, "5-9": 50.0, "10 and over": 0.0},
                               "sex": {"Both sexes": 100.0, "Males": 45.0,
                                       "Females": 55.0}}}
        row = {"counts": {"Georgian": 90.0, "Armenian": 10.0}, "total": 100.0, "hidden": 0}
        comps = {field: {"C. Tbilisi": row} for field in g.T_COMP}
        values, cites = g.region_2014(ages, comps, "C. Tbilisi", "Tbilisi")
        for field in g.T_COMP:
            self.assertEqual(values[f"{field}_year"], 2014)
            self.assertEqual(values[field][0], {"group": "Georgian", "pct": 90.0, "count": 90})
        self.assertEqual(values["median_age"]["year"], 2014)
        self.assertEqual({c["field"] for c in cites},
                         {"median_age", "sex_ratio", *g.T_COMP})

    def test_the_municipal_gap_says_why(self):
        note = g.BY_REGION_ONLY.format(what="religion", table="22", old="29")
        self.assertIn("by region only", note)
        self.assertIn("table 29", note)


class MunicipalAges(unittest.TestCase):
    """The 2014 census's five-year groups by unit, as OCHA's COD-PS relays them."""

    COLUMNS = (["YEAR", "ADM1_EN", "ADM2_EN", "ADM2TYPE_EN", "F_TL", "M_TL", "T_TL"]
               + [f"{s}_{a:02d}_{a + 4:02d}" for s in "FMT" for a in range(0, 85, 5)]
               + ["F_85Plus", "M_85Plus", "T_85Plus"])

    def row(self, name, kind, per_group):
        out = {"YEAR": "2014", "ADM1_EN": "Kakheti", "ADM2_EN": name, "ADM2TYPE_EN": kind}
        for a in range(0, 85, 5):
            out[f"F_{a:02d}_{a + 4:02d}"] = str(per_group // 2)
            out[f"M_{a:02d}_{a + 4:02d}"] = str(per_group - per_group // 2)
            out[f"T_{a:02d}_{a + 4:02d}"] = str(per_group)
        out["F_85Plus"] = out["M_85Plus"] = out["T_85Plus"] = "0"
        out["F_TL"] = str(17 * (per_group // 2))
        out["M_TL"] = str(17 * (per_group - per_group // 2))
        out["T_TL"] = str(17 * per_group)
        return out

    def test_the_tables_cities_and_spellings_meet_the_boundary_files(self):
        self.assertEqual(g.cod_key("c. Telavi"), g.cod_key("Telavi"))
        self.assertEqual(g.cod_key("c. Batumi"), "batumi")
        self.assertEqual(g.cod_key("Tskaltubo"), g.fold("Tsqaltubo"))
        self.assertEqual(g.cod_key("Tetritskaro"), g.fold("Tetri Sqaro"))
        self.assertEqual(g.cod_key("Ozurgeti "), "ozurgeti")

    def test_a_city_and_its_municipality_make_one_median(self):
        from scripts.fetch_census import cod_ps_age
        cols = cod_ps_age.age_columns(self.COLUMNS)
        self.assertEqual(cols["sexes"], "T")
        rows = [self.row("c. Telavi", "city", 10), self.row("Telavi", "municipality", 30)]
        total, median = g.census_ages(rows, cols, "Telavi")
        self.assertEqual(total, 17 * 40)
        self.assertEqual(median, 42.5)
        self.assertEqual(g.unit_label(rows[0]), "Telavi (city)")

    def test_ages_that_do_not_make_the_total_stop_the_run(self):
        from scripts.fetch_census import cod_ps_age
        cols = cod_ps_age.age_columns(self.COLUMNS)
        bad = self.row("Telavi", "municipality", 30)
        bad["T_TL"] = "999"
        with self.assertRaises(SystemExit):
            g.census_ages([bad], cols, "Telavi")


class Numbers(unittest.TestCase):
    def test_suppressed_cells_read_as_none(self):
        self.assertIsNone(g.number(".."))
        self.assertIsNone(g.number("…"))
        self.assertEqual(g.number("1 234"), 1234.0)


if __name__ == "__main__":
    unittest.main()
