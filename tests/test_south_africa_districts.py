"""South Africa's Census 2022 districts: population group, median age and the
reasons religion and language are empty (scripts/fetch_census/south_africa_districts)."""

import unittest

from scripts.fetch_census import south_africa_districts as za


def ages_of(counts):
    """{age group: (men, women)} from eighteen totals, split evenly."""
    return {i + 1: (n // 2, n - n // 2) for i, n in enumerate(counts)}


AGES = ages_of([100, 100, 100, 100, 100, 50, 50, 50, 50, 50, 50, 50, 50, 25, 25, 25, 15, 10])
GROUPS = {1: 90, 2: 5, 3: 2, 4: 2, 5: 1}


class SouthAfricaDistrictAgesTest(unittest.TestCase):
    def test_median_is_interpolated_in_its_five_year_group(self):
        total = sum(sum(v) for v in AGES.values())               # 1,000
        self.assertEqual(total, 1000)
        # 500 people are under 25: the median is the top of the 20-24 group.
        self.assertEqual(za.median_of(AGES), 25.0)
        skewed = ages_of([300, 300] + [25] * 16)
        self.assertEqual(za.median_of(skewed), round(5 + 5 * (500 - 300) / 300, 1))

    def test_open_top_group_may_not_hold_the_median(self):
        with self.assertRaises(SystemExit):
            za.median_of(ages_of([0] * 17 + [10]))

    def test_numbering_is_checked_against_the_services_own_summary(self):
        main = {"ageYoungPeople0to14Percentage": 30.0, "ageElderly65PlusPercentage": 10.0}
        za.check_numbering("x", AGES, main)                       # 300 young, 100 old
        with self.assertRaises(SystemExit):
            za.check_numbering("x", AGES, {"ageYoungPeople0to14Percentage": 40.0})

    def test_groups_and_ages_make_the_total_less_the_unstated(self):
        za.check_parts("x", 1000, 995, "groups")
        za.check_parts("x", 1000, 1002, "groups")                 # rounding
        with self.assertRaises(SystemExit):
            za.check_parts("x", 1000, 980, "groups")
        with self.assertRaises(SystemExit):
            za.check_parts("x", 1000, 1010, "groups")

    def test_group_numbering_must_put_the_western_capes_coloured_first(self):
        provinces = {"Western Cape": {"groups": {1: 39, 2: 42, 3: 1, 4: 16, 5: 2}},
                     "KwaZulu-Natal": {"groups": {1: 87, 2: 1, 3: 7, 4: 4, 5: 1}},
                     "Gauteng": {"groups": {1: 84, 2: 3, 3: 3, 4: 9, 5: 1}}}
        za.check_groups(provinces)
        swapped = {k: dict(v) for k, v in provinces.items()}
        swapped["Western Cape"] = {"groups": {1: 42, 2: 39, 3: 1, 4: 16, 5: 2}}
        with self.assertRaises(SystemExit):
            za.check_groups(swapped)


class SouthAfricaDistrictRecordsTest(unittest.TestCase):
    ADMIN1 = [{"id": "K", "name": "KwaZulu-Natal"}]
    ADMIN2 = [{"id": "u", "name": "Uthungulu", "parent": "K"}]

    def table(self):
        return {"districts": [{"code": "DC28", "name": "King Cetshwayo",
                               "province": "KwaZulu-Natal", "men": 480, "women": 520,
                               "total": 1003, "groups": GROUPS, "ages": AGES}],
                "provinces": {"KwaZulu-Natal": {"id": 5, "total": 1003, "groups": GROUPS,
                                                "ages": AGES}}}

    def test_district_carries_groups_median_and_stated_reasons(self):
        recs = za.records_of(self.table(), self.ADMIN1, self.ADMIN2)
        district = [r for r in recs if r["level"] == "admin2"][0]
        eth = {g["group"]: g for g in district["ethnicity"]}
        self.assertEqual(eth["Black African"]["count"], 90)
        self.assertEqual(eth["Black African"]["pct"], 90.0)
        self.assertIn("the 100 people whose group the census recorded, of the 1,003",
                      district["ethnicity_note"])
        self.assertEqual(district["median_age"]["value"], 25.0)
        self.assertEqual(district["median_age"]["year"], 2022)
        self.assertEqual(district["religion"]["status"], "not_available")
        self.assertIn("by province only", district["religion"]["note"])
        self.assertIn("Table 2.9", district["language"]["note"])
        self.assertTrue(any(s["field"] == "ethnicity" for s in district["sources"]))

    def test_province_gets_its_median_and_nothing_else(self):
        recs = za.records_of(self.table(), self.ADMIN1, self.ADMIN2)
        province = [r for r in recs if r["level"] == "admin1"][0]
        self.assertEqual(province["shape_id"], "K")
        self.assertEqual(province["median_age"]["value"], 25.0)
        self.assertEqual(province["population"]["status"], "not_available")
        self.assertEqual(province["ethnicity"]["status"], "not_available")
        self.assertNotIn("note", province["ethnicity"])

    def test_visitor_notes_say_nothing_about_how_the_map_is_made(self):
        recs = za.records_of(self.table(), self.ADMIN1, self.ADMIN2)
        for r in recs:
            for field in ("religion", "language"):
                note = (r.get(field) or {}).get("note") or ""
                for word in ("adapter", "fetched", "pipeline", "build", "scraped"):
                    self.assertNotIn(word, note)


if __name__ == "__main__":
    unittest.main()
