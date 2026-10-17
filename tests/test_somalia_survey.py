"""Tests for the Somalia PESS 2014 adapter (median age and sex ratio by region), no network."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import somalia_survey as ss  # noqa: E402

SITE = Path(__file__).resolve().parent.parent / "site" / "data"

# The two tables as the report's text layer gives them (pages 34 and 53).
CONTENTS = """Table A. 2:  Median age by type of residence and region, 39
Table A. 3:   Sex ratio by age group and type of residence 40
"""
TABLE_2 = """Region Percent distribution by sex Percent distribution by regionMale Female
Awdal 51.8 48.2 5.5
W. Galbeed 49.8 50.2 10.1
Togdheer 50.1 49.9 5.9
Sool 52.8 47.2 2.7
Sanaag 52.0 48.0 4.4
Bari 50.5 49.5 5.8
Nugaal 50.8 49.2 3.2
Mudug 50.7 49.3 5.8
Galgaduud 49.9 50.1 4.6
Hiraan 53.1 46.9 4.2
M. Shabelle 52.4 47.6 4.2
Banadir 49.3 50.7 13.4
L. Shabelle 50.3 49.7 9.8
Bay 50.8 49.2 6.4
Bakool 52.9 47.1 3.0
Gedo 49.2 50.8 4.1
M. Juba 52.3 47.7 2.9
L. Juba 50.6 49.4 4.0
All Regions 50.7 49.3 100
Table 2:  Population by region and sex
"""
TABLE_A2 = """Table A. 2: Median age by type of residence and region,
Variable Male Female Total
Type of residence
Rural 15 16 16
Urban 17 18 17
IDP Camps 13 14 13
Nomadic 17 17 17
Region
Awdal 20 20 20
Woqooyi Galbeed 18 19 19
Togdheer 17 18 18
Sool 18 18 18
Sanaag 19 19 19
Bari 18 19 18
Nugaal 15 16 15
Mudug 14 15 15
Galgaduud 14 14 14
Hiraan 12 13 12
Middle Shabelle 15 16 15
Banadir 14 15 14
Lower Shabelle 14 14 14
Bay 16 18 16
Bakool 14 14 14
Gedo 14 14 14
Middle Juba 30 18 19
Lower Juba 16 16 16
Total 16 17 16
"""
TEXT = CONTENTS + "\nSome other page\nTotal 1 2 3\n" + TABLE_2 + "\nAppendix\n" + TABLE_A2


class TablesTest(unittest.TestCase):
    def test_both_tables_give_the_eighteen_regions(self):
        shares, medians = ss.read_shares(TEXT), ss.read_medians(TEXT)
        self.assertEqual(len(shares), 18)
        self.assertEqual(set(shares), set(medians))
        self.assertEqual(shares["woqooyigalbeed"]["male"], 49.8)
        self.assertEqual(medians["middleshebelle"]["total"], 15)
        self.assertEqual(medians["hiiraan"]["male"], 12)

    def test_sexes_that_do_not_make_a_hundred_stop_the_run(self):
        with self.assertRaises(SystemExit):
            ss.read_shares(TEXT.replace("Awdal 51.8 48.2", "Awdal 51.8 47.2"))

    def test_a_missing_region_stops_the_run(self):
        with self.assertRaises(SystemExit):
            ss.read_medians(TEXT.replace("Bakool 14 14 14\n", ""))


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.admin1 = json.loads((SITE / "admin1" / "SOM.units.json").read_text())
        self.records = {r["name"]: r for r in ss.build(ss.read_shares(TEXT),
                                                        ss.read_medians(TEXT), self.admin1)}

    def test_every_region_the_map_draws_is_written(self):
        self.assertEqual(len(self.records), 18)
        self.assertEqual(len(self.admin1), 18)

    def test_a_region_carries_the_survey_median_and_sex_ratio(self):
        awdal = self.records["Awdal"]
        self.assertEqual(awdal["median_age"]["value"], 20)
        self.assertEqual(awdal["sex_ratio"], {"value": 1075, "unit": "males_per_1000_females",
                                              "year": 2014, "source": ss.SOURCE})
        self.assertTrue(awdal["median_age_basis"].startswith("survey estimate"))
        self.assertIn("51.8% and 48.2%", awdal["sex_ratio_note"])
        self.assertIn("men 20, women 20", awdal["median_age_note"])

    def test_middle_juba_says_why_it_has_neither(self):
        juba = self.records["Middle Juba"]
        self.assertEqual(juba["median_age"]["status"], "not_available")
        self.assertIn("inaccessible", juba["sex_ratio"]["note"])

    def test_the_districts_each_say_why(self):
        admin2 = json.loads((SITE / "admin2" / "SOM.units.json").read_text())
        rows = ss.districts(admin2)
        self.assertEqual(len(rows), len(admin2))
        self.assertTrue(all(r["population"]["status"] == "not_available" for r in rows))
        self.assertIn("by region only", rows[0]["median_age"]["note"])

    def test_notes_name_no_file_or_pipeline(self):
        banned = ("adapter", "pipeline", "fetched", "scraped", "this project", ".json",
                  "boundary file", "build")
        for r in self.records.values():
            for field in ("median_age_note", "sex_ratio_note"):
                text = (r.get(field) or "").lower()
                self.assertFalse([w for w in banned if w in text], (r["name"], text))


if __name__ == "__main__":
    unittest.main()
