"""Zambia's 2022 census: median ages of the provinces (Table 5.1) and of the
districts whose middle person falls in a band the district tables split
(scripts/fetch_census/zambia_census)."""

import unittest

from scripts.fetch_census import zambia_census as zc

AGES_51 = """TABLE 5.1:
ZAMBIA
Total 1,000 480 520 600 290 310 400 190 210
0 - 4 160 80 80 100 50 50 60 30 30
5 - 9 150 75 75 90 45 45 60 30 30
10 - 14 140 70 70 85 42 43 55 28 27
15 - 19 120 60 60 70 35 35 50 25 25
20 - 24 100 50 50 60 30 30 40 20 20
25 - 29 330 145 185 195 88 107 135 57 78
WESTERN PROVINCE
Total 1,000 480 520 600 290 310 400 190 210
0 - 4 160 80 80 100 50 50 60 30 30
5 - 9 150 75 75 90 45 45 60 30 30
10 - 14 140 70 70 85 42 43 55 28 27
15 - 19 120 60 60 70 35 35 50 25 25
20 - 24 100 50 50 60 30 30 40 20 20
25 - 29 320 145 175 195 88 107 125 57 68
95+ 10 0 10 0 0 0 10 0 10""".splitlines()


def band_lines(n_zambia, n_district):
    return ["TABLE 5.3:",
            f"ZAMBIA TOTAL {n_zambia} 1 1 1 1 1 1 1 1",
            f"WESTERN PROVINCE {n_zambia} 1 1 1 1 1 1 1 1",
            f"SENANGA DISTRICT {n_district} 1 1 1 1 1 1 1 1",
            f"SHANG'OMBO DISTRICT {n_zambia - n_district} 1 1 1 1 1 1 1 1"]


class ZambiaAgesTest(unittest.TestCase):
    def test_province_medians_from_five_year_groups(self):
        ages = zc.parse_ages(AGES_51)
        self.assertEqual(sorted(ages), ["western", "zambia"])
        # 450 under 15, 570 under 20: the middle person is in 15-19.
        self.assertEqual(zc.grouped_median(ages["zambia"]), round(15 + 5 * 50 / 120, 1))

    def test_a_group_list_that_misses_its_total_is_refused(self):
        broken = [ln.replace("0 - 4 160", "0 - 4 161") for ln in AGES_51]
        with self.assertRaises(SystemExit):
            zc.parse_ages(broken)

    def test_band_medians_and_the_bands_the_tables_do_not_split(self):
        # 1,000 people: 440 under 16, 520 under 18, 560 under 19.
        self.assertEqual(zc.band_median(1000, 560, 560, 480), (round(16 + 2 * 60 / 80, 1), ""))
        # 500 under 18 exactly: the middle person is 18.
        self.assertEqual(zc.band_median(1000, 540, 560, 500), (18.0, ""))
        self.assertEqual(zc.band_median(1000, 700, 400, 300), (None, "under16"))
        self.assertEqual(zc.band_median(1000, 450, 700, 600), (None, "from19"))
        with self.assertRaises(SystemExit):
            zc.band_median(1000, 400, 700, 450)            # under 19 fewer than under 18

    def test_band_tables_must_add_up(self):
        got = zc.parse_counts(band_lines(300, 120), "Table 5.3")
        self.assertEqual(got["districts"], {"senanga": 120, "shangombo": 180})
        broken = band_lines(300, 120)
        broken[3] = "SENANGA DISTRICT 121 1 1 1 1 1 1 1 1"
        with self.assertRaises(SystemExit):
            zc.parse_counts(broken, "Table 5.3")

    def test_district_records_carry_a_median_or_a_reason(self):
        table = {"districts": {"senanga": {"total": 1000}, "shangombo": {"total": 1000}},
                 "bands": {"under19": {"districts": {"senanga": 560, "shangombo": 700}},
                           "from16": {"districts": {"senanga": 560, "shangombo": 400}},
                           "from18": {"districts": {"senanga": 480, "shangombo": 300}}}}
        self.assertEqual(zc.median_fields(table, "admin2", "senanga")["median_age"]["value"],
                         17.5)
        reason = zc.median_fields(table, "admin2", "shangombo")["median_age"]
        self.assertEqual(reason["status"], "not_available")
        self.assertIn("more than half of this district's people are under 16", reason["note"])
        self.assertEqual(zc.median_fields({}, "admin2", "senanga"), {})


if __name__ == "__main__":
    unittest.main()
