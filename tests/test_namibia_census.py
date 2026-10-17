"""Namibia's 2023 census by region: count, sex ratio and median age from the
Main Report's Tables 2.2 to 2.4 (scripts/fetch_census/namibia_census)."""

import unittest
from unittest import mock

from scripts.fetch_census import namibia_census as nm

# Three regions and the country as the report's text layer prints them; the
# country here is the three regions' sum.
TEXT = """Table 2.2: Population and percent distribution by sex and area
Namibia 469 172 232 315 236 857 49.5 50.5
//Kharas 109 893 55 670 54 223 50.7 49.3
Kavango East 218 421 102 310 116 111 46.8 53.2
Kavango West 140 858 74 335 66 523 52.8 47.2
Table 2.3: Percent distribution of population by major age group and area
Namibia 469 172 14.6 25.0 33.0 21.0 6.4
//Kharas 109 893 10.9 18.6 36.6 27.9 6.0
Kavango East 218 421 15.8 27.3 33.3 17.4 6.2
Kavango West 140 858 16.7 28.8 30.9 16.4 7.2
Table 2.4: Percent Distribution of the Youth (15-34 years) Population
Namibia 155 027 30.0 25.0 23.0 22.0
//Kharas 40 246 19.8 23.7 28.9 27.6
Kavango East 72 837 33.5 24.8 21.8 19.9
Kavango West 43 523 36.4 26.2 20.0 17.4"""


class NamibiaCensusTest(unittest.TestCase):
    def table(self):
        with mock.patch.object(nm, "REGIONS", ("//Kharas", "Kavango East", "Kavango West")), \
                mock.patch.object(nm, "NATIONAL", 469_172):
            return nm.parse(TEXT)

    def test_sexes_are_split_where_men_and_women_make_the_total(self):
        self.assertEqual(nm.sex_split("3 022 401 1 474 224 1 548 177"),
                         (3_022_401, 1_474_224, 1_548_177))

    def test_the_countrys_median_from_the_real_shares(self):
        row = {"total": 3_022_401, "shares": [13.7, 23.3, 34.1, 22.0, 6.8], "youth": 1_030_935,
               "youth_shares": [27.0, 25.4, 24.5, 23.1]}
        self.assertEqual(nm.median_of(nm.bands(row)), 22.2)

    def test_regions_and_kavangos_two_halves(self):
        table = self.table()
        admin1 = [{"id": "K", "name": "Karas"}, {"id": "V", "name": "Kavango"}]
        with mock.patch.object(nm, "REGIONS", ("//Kharas", "Kavango East", "Kavango West")):
            recs = {r["shape_id"]: r for r in nm.build(table, admin1)}
        self.assertEqual(recs["V"]["population"]["value"], 218_421 + 140_858)
        self.assertIn("Kavango East and Kavango West added together",
                      recs["V"]["population_note"])
        self.assertEqual(recs["K"]["sex_ratio"]["value"], round(1000 * 55_670 / 54_223))
        self.assertIn("drawn here as Karas", recs["K"]["population_note"])
        self.assertGreater(recs["K"]["median_age"]["value"], recs["V"]["median_age"]["value"])

    def test_a_youth_count_unlike_its_share_is_refused(self):
        broken = TEXT.replace("//Kharas 40 246", "//Kharas 45 246")
        with mock.patch.object(nm, "REGIONS", ("//Kharas", "Kavango East", "Kavango West")), \
                mock.patch.object(nm, "NATIONAL", 469_172), self.assertRaises(SystemExit):
            nm.parse(broken)


if __name__ == "__main__":
    unittest.main()
