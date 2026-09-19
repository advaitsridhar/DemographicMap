"""Singapore's planning areas, the regions summed from them, and the empty ones."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_census import singapore_areas as sg  # noqa: E402


def table(rows: dict[str, tuple[float | None, dict[str, float]]], *,
          national: float, others: float | None = None) -> sg.Table:
    """A Table from {area: (total, {group: count})}; a None total is 'na'."""
    out = sg.Table()
    out.national, out.others = national, others
    for name, (total, parts) in rows.items():
        if total:
            out.totals[name] = total
            out.counts[name] = dict(parts)
    return out


# The East Region is the small one: Bedok, Changi, Changi Bay, Pasir Ris,
# Paya Lebar and Tampines. Here Bedok and Tampines carry every table, Changi
# only the ethnic-group table and the 2010 census, Paya Lebar a count with no
# breakdown, and Changi Bay nothing at all.
PEOPLE = {
    "Bedok": (1000, {"Chinese": 700, "Malay": 200, "Indian": 100}),
    "Tampines": (3000, {"Chinese": 2000, "Malay": 800, "Indian": 200}),
    "Changi": (100, {"Chinese": 60, "Malay": 30, "Indian": 10}),
    "Paya Lebar": (40, {}),
    "Changi Bay": (None, {}),
}
CENSUS = {
    "Bedok": (800, {"Buddhist": 400, "Muslim": 200, "No religion": 200}),
    "Tampines": (2400, {"Buddhist": 1200, "Muslim": 800, "No religion": 400}),
}
# The 2010 census listed Changi, which the 2020 release folds into "Others".
CENSUS_2010 = {
    "Bedok": (700, {"Buddhist": 350, "Muslim": 200, "No religion": 150}),
    "Changi": (80, {"Buddhist": 40, "Muslim": 30, "No religion": 10}),
}


def east_tables() -> dict[str, sg.Table]:
    return {"ethnicity": table(PEOPLE, national=4140),
            "religion": table(CENSUS, national=3320, others=120),
            "language": table(CENSUS, national=3320, others=120),
            "religion_2010": table(CENSUS_2010, national=3000),
            "language_2010": table(CENSUS_2010, national=3000)}


class TheRegions(unittest.TestCase):
    def test_the_five_regions_hold_the_55_shapes_once_each(self):
        areas = [a for areas in sg.REGIONS.values() for a in areas]
        self.assertEqual(len(areas), 55)
        self.assertEqual(len(set(areas)), 55)
        self.assertEqual(sorted(sg.REGIONS), ["Central Region", "East Region",
                                              "North Region", "North-East Region",
                                              "West Region"])

    def test_a_region_is_the_sum_of_its_areas_over_their_own_totals(self):
        tables = east_tables()
        field = sg.region_field("East Region", "ethnicity", tables["ethnicity"],
                                tables["ethnicity"], short=0.0)
        by_group = {row["group"]: row for row in field["ethnicity"]}
        self.assertEqual(by_group["Chinese"]["count"], 2760)
        # Paya Lebar's 40 are in the base with no group of their own.
        self.assertEqual(by_group["Chinese"]["pct"], round(100 * 2760 / 4140, 1))
        self.assertEqual(field["ethnicity_year"], 2020)
        note = field["ethnicity_note"]
        self.assertTrue(note.startswith("Summed from the Census of Population "
                                        "2020 rows of the 3 planning areas"), note)
        self.assertIn("Paya Lebar (40 residents) has a count but no published "
                      "breakdown", note)
        self.assertIn("Changi Bay and Pasir Ris have no published residents.", note)
        self.assertNotIn("Nationally", note)

    def test_an_area_the_census_folds_into_others_is_named_and_measured(self):
        tables = east_tables()
        field = sg.region_field("East Region", "religion", tables["religion"],
                                tables["ethnicity"], short=0.0)
        by_group = {row["group"]: row for row in field["religion"]}
        self.assertEqual(by_group["Buddhist"]["count"], 1600)
        self.assertEqual(by_group["Buddhist"]["pct"], 50.0)
        note = field["religion_note"]
        self.assertIn("shares of adults", note)
        # 140 of the region's 4,140 residents sit in the Others row.
        self.assertIn("folds Changi and Paya Lebar into an 'Others' row", note)
        self.assertIn("140 residents in 2020, 3.4% of the region", note)
        self.assertLessEqual(note.count(". "), 3, "a note is three sentences at most")

    def test_a_small_national_shortfall_is_said_not_refused(self):
        tables = east_tables()
        field = sg.region_field("East Region", "religion", tables["religion"],
                                tables["ethnicity"], short=7.0)
        self.assertIn("fall 7 short of the published total", field["religion_note"])

    def test_a_region_with_no_listed_area_is_a_gap(self):
        empty = table({}, national=0)
        field = sg.region_field("North Region", "religion", empty, empty, short=0.0)
        self.assertEqual(field["religion"]["status"], sg.NOT_AVAILABLE)

    def test_region_rows_carry_no_population_of_their_own(self):
        rows = sg.region_rows(east_tables(), {"ethnicity": 0.0, "religion": 0.0,
                                              "language": 0.0})
        self.assertEqual([r["name"] for r in rows],
                         ["Central Region", "East Region", "North Region",
                          "North-East Region", "West Region"])
        east = rows[1]
        self.assertEqual(east["level"], "admin1")
        self.assertEqual(east["id"], "SGP-R-East-Region")
        self.assertEqual(east["population"]["status"], sg.NOT_AVAILABLE)
        self.assertIsInstance(east["language"], list)


class ThePartition(unittest.TestCase):
    def test_the_areas_and_the_others_row_must_reach_the_national_row(self):
        short = sg.partition_gap("religion", table(CENSUS, national=3320, others=120))
        self.assertEqual(short, 0.0)

    def test_a_shortfall_within_the_limit_is_returned(self):
        self.assertEqual(sg.partition_gap("religion", table(CENSUS, national=3330,
                                                             others=120)), 10.0)

    def test_a_large_shortfall_refuses_the_regions(self):
        with self.assertRaises(SystemExit) as caught:
            sg.partition_gap("religion", table(CENSUS, national=4000, others=120))
        self.assertIn("do not partition", str(caught.exception))


class TheEmptyAreas(unittest.TestCase):
    def setUp(self):
        self.rows = {r["name"]: r for r in sg.area_rows(east_tables())}

    def test_every_shape_gets_a_record(self):
        self.assertEqual(len(self.rows), 55)
        self.assertEqual(self.rows["Bedok"]["codes"]["planning_region"], "East Region")

    def test_a_count_with_no_breakdown_says_how_few(self):
        row = self.rows["Paya Lebar"]
        self.assertEqual(row["population"]["value"], 40)
        self.assertIn("counted 40 residents here, too few", row["ethnicity"]["note"])
        self.assertIn("this one (40 residents in 2020) is among the 53 it folds into "
                      "an 'Others' row of 120 residents aged 15 and over",
                      row["religion"]["note"])

    def test_an_area_with_no_count_anywhere_invents_none(self):
        row = self.rows["Changi Bay"]
        for field in ("population", "ethnicity", "religion", "language"):
            self.assertEqual(row[field]["status"], sg.NOT_AVAILABLE)
            self.assertIn("marks it '-'", row[field]["note"])

    def test_an_area_the_2020_release_folds_away_falls_back_to_2010(self):
        # Changi has no 2020 religion row and a 2010 one. A decade-old count is
        # a count, and it is stamped 2010 rather than passed off as the census
        # beside it.
        row = self.rows["Changi"]
        self.assertIsInstance(row["ethnicity"], list)
        self.assertIsInstance(row["religion"], list)
        self.assertEqual(row["religion_year"], 2010)
        self.assertIn("Census 2010", row["religion_note"])
        self.assertIn("folds this area into its 'Others' row", row["religion_note"])
        by_group = {r["group"]: r["pct"] for r in row["religion"]}
        self.assertEqual(by_group["Buddhist"], 50.0)
        self.assertEqual(row["sources"][-1]["year"], 2010)

    def test_an_area_no_census_ever_listed_says_so(self):
        # Pasir Ris is in no table here: no 2020 row, no 2010 row, but the
        # ethnic-group table would have counted it.
        rows = {r["name"]: r for r in sg.area_rows(east_tables())}
        note = rows["Pasir Ris"]["religion"]["note"]
        self.assertIn("marks it '-'", note)


class TheExtracts(unittest.TestCase):
    def test_an_area_in_no_region_is_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "religion.csv"
            path.write_text("Number,Total,Buddhism\nTotal,10,10\nAtlantis,10,10\n")
            with self.assertRaises(SystemExit) as caught:
                sg.read(path, {"Buddhism": "Buddhist"}, areas_only=False)
            self.assertIn("Atlantis", str(caught.exception))

    def test_the_others_row_is_read_not_joined(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "religion.csv"
            path.write_text("Number,Total,Buddhism\nTotal,30,30\nBedok,20,20\n"
                            "Others,10,10\n")
            got = sg.read(path, {"Buddhism": "Buddhist"}, areas_only=False)
            self.assertEqual(got.others, 10)
            self.assertEqual(set(got.totals), {"Bedok"})

    def test_the_2010_tables_are_not_summed_into_a_region(self):
        # A region is one census. The 2010 rows fill areas the 2020 release
        # folds away; summing them into a region would mix two censuses in one
        # composition and double-count Bedok.
        rows = sg.region_rows(east_tables(), {"ethnicity": 0.0, "religion": 0.0,
                                              "language": 0.0})
        east = next(r for r in rows if r["name"] == "East Region")
        self.assertEqual(east["religion_year"], 2020)
        self.assertIn("2 planning areas", east["religion_note"])

    def test_the_committed_extracts_partition_the_country(self):
        if not sg.ETHNICITY_CSV.exists():
            self.skipTest("extracts not present")
        rows = sg.build()
        regions = [r for r in rows if r["level"] == "admin1"]
        self.assertEqual(len(regions), 5)
        for region in regions:
            for field in ("ethnicity", "religion", "language"):
                self.assertIsInstance(region[field], list, f"{region['name']} {field}")
                total = sum(row["pct"] for row in region[field])
                self.assertGreater(total, 99.0, f"{region['name']} {field}")
                self.assertLessEqual(round(total, 1), 100.2, f"{region['name']} {field}")
        areas = [r for r in rows if r["level"] == "admin2"]
        self.assertEqual(len(areas), 55)
        # The sum of the regions is the country: every published count lands
        # in exactly one region. The 2010 tables fill areas, not regions, so
        # they are not part of this.
        for field in sg.MAIN:
            control = sg.CONTROLS[field]
            summed = sum(row["count"] for region in regions for row in region[field])
            self.assertLess(control - summed, 0.01 * control, field)


if __name__ == "__main__":
    unittest.main()
