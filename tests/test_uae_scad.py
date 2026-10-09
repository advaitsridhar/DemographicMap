"""Abu Dhabi's census figures, read from a page built in memory like SCAD's."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import uae_scad as us  # noqa: E402

# 2024 then 2023 R1, as the page draws them: the emirate, then each region.
EMIRATE = [(2767060, 1368925), (2560240, 1287345)]
REGIONS = {"AbuDhabi": [(1881460, 941880), (1724010, 871380)],
           "AlAin": [(622295, 364615), (597190, 348415)],
           "AlDhafra": [(263305, 62430), (239040, 67550)]}


def chart(city, men, women):
    return (f'chart.data = [{{ "city": "{city}", "male": {men}, "female": {women}, }}]; '
            f'// Create axes var categoryAxis = ')


def page(emirate=EMIRATE, regions=REGIONS, sentence="4.14 million in 2024",
         al_ain="986,910"):
    parts = ["<html><h2>Abu Dhabi&#8217;s population reached " + sentence + ", marking a "
             "7.5% increase from 2023. The population distribution is 68.3% (2,823,340), "
             f"Al Ain 23.9% ({al_ain}), and Al Dhafra 7.9% (325,735).</h2>"]
    parts += [chart("AbuDhabi", m, f) for m, f in emirate]
    for city, years in regions.items():
        parts += [chart(city, m, f) for m, f in years]
    parts.append('chart.data = [{ "city": "AbuDhabi", "male": "2762715" }];')
    parts.append("var population_2011 ='Abu Dhabi&#39;s population reached 3.85 million in the "
                 "2023 R1 update. Al Ain 24.6% (945,605), and Al Dhafra 7.9% (306,590).';")
    return "\n".join(parts)


DRAWN = [{"id": "e1", "name": "Abu Dhabi", "parent": "ARE"},
         {"id": "e2", "name": "Dubai", "parent": "ARE"}]


class TheReader(unittest.TestCase):
    def test_the_latest_year_is_written_at_both_levels(self):
        rows = us.build(us.read(page()), DRAWN, [{"id": "e1", "name": "Abu Dhabi",
                                                    "parent": "e1"}])
        self.assertEqual([r["level"] for r in rows], ["admin1", "admin2"])
        first = rows[0]
        self.assertEqual(first["shape_id"], "e1")
        self.assertEqual(first["population"]["value"], 4135985)
        self.assertEqual(first["population"]["year"], 2024)
        self.assertEqual(first["sex_ratio"]["value"], round(100 * 2767060 / 1368925, 1))
        self.assertIn("3,847,585", first["population"]["note"])
        self.assertEqual(rows[1]["population"], first["population"])
        for field in ("median_age", "ethnicity", "religion", "language"):
            self.assertEqual(first[field]["status"], "not_available", field)
            self.assertIn("census.scad.gov.ae", first[field]["note"], field)

    def test_regions_that_miss_the_emirate_stop_the_run(self):
        regions = dict(REGIONS, AlAin=[(622296, 364615), (597190, 348415)])
        with self.assertRaises(SystemExit):
            us.read(page(regions=regions))

    def test_a_total_unlike_the_sentence_stops_the_run(self):
        with self.assertRaises(SystemExit):
            us.read(page(sentence="4.15 million in 2024"))

    def test_a_region_unlike_the_sentence_stops_the_run(self):
        with self.assertRaises(SystemExit):
            us.read(page(al_ain="986,911"))

    def test_a_missing_chart_stops_the_run(self):
        with self.assertRaises(SystemExit):
            us.read(page(emirate=EMIRATE[:1]))


if __name__ == "__main__":
    unittest.main()
