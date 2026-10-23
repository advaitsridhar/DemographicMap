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
        za.check_parts("Nkangala", 1_588_684, 1_588_777, "age groups")  # weighting
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


# Report 03-01-84, Table 2.3, as its text layer gives it (p. 9).
TABLE_2_3 = """Table 2.3 - Percentage distribution of population by language spoken in the household and Metropolitan Area, Census 2022
City of Cape City of City of Nelson City of
Language Buffalo City Town Ekurhuleni EThekwini Johannesburg Mangaung Mandela Bay Tshwane Non-Metros
Afrikaans 5,3 26,1 7,3 0,8 3,8 10,8 24,7 12,1 10,6
English 10,1 30,6 8,9 28,6 13,7 1,7 13,3 6,9 8,7
IsiNdebele 0,1 0,2 1,7 0,1 3,6 0,1 0,1 5,0 1,7
IsiXhosa 82,4 37,4 8,5 3,1 7,0 7,4 59,5 2,2 16,3
IsiZulu 0,3 0,5 35,7 65,6 28,9 0,6 0,3 9,0 24,4
Sepedi 0,0 0,1 12,3 0,0 7,9 0,2 0,0 24,4 10,0
Sesotho 0,3 0,8 10,2 0,6 11,9 64,0 0,2 5,0 7,8
Setswana 0,0 0,2 2,6 0,0 7,7 14,3 0,0 17,8 8,3
Sign language 0,0 0,0 0,0 0,0 0,0 0,0 0,0 0,0 0,0
SiSwati 0,0 0,0 1,2 0,0 0,6 0,1 0,0 1,3 2,8
Tshivenda 0,0 0,1 1,7 0,0 3,5 0,0 0,0 2,5 2,5
Xitsonga 0,1 0,2 6,7 0,0 7,4 0,1 0,1 9,2 4,7
Other 1,3 3,8 3,3 1,1 4,0 0,7 1,6 4,5 2,1
Total 100,0 100,0 100,0 100,0 100,0 100,0 100,0 100,0 100,0"""


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
        self.assertIn("for each province", district["religion"]["note"])
        self.assertIn("not for its districts or metros", district["religion"]["note"])
        self.assertIn("Table 2.9", district["language"]["note"])
        self.assertIn("eight metropolitan municipalities", district["language"]["note"])
        self.assertTrue(any(s["field"] == "ethnicity" for s in district["sources"]))
        # Note-only citations name no figure field: the release, the province's
        # profile and the report on cultural dynamics.
        notes = [s for s in district["sources"] if s["field"] == "religion note/language note"]
        self.assertEqual(len(notes), 3)
        self.assertIn("Report-03-01-74", notes[1]["url"])

    def test_a_metro_carries_table_2_3s_languages(self):
        table = self.table()
        table["districts"][0].update(code="ETH", name="eThekwini")
        metros = za.metro_languages(TABLE_2_3)
        recs = za.records_of(table, self.ADMIN1, [{"id": "e", "name": "eThekwini",
                                                    "parent": "K"}], metros)
        metro = [r for r in recs if r["level"] == "admin2"][0]
        self.assertEqual(metro["language"][:2], [{"group": "isiZulu", "pct": 65.6},
                                                 {"group": "English", "pct": 28.6}])
        self.assertEqual(metro["language_year"], 2022)
        self.assertIn("Report 03-01-84, Table 2.3", metro["language_note"])
        self.assertEqual(metro["religion"]["status"], "not_available")
        self.assertTrue(any(s["field"] == "language" and "03-01-84" in s["url"]
                            for s in metro["sources"]))
        self.assertFalse(any("language note" in s["field"] for s in metro["sources"]))

    def test_table_2_3_columns_must_make_100(self):
        self.assertEqual(len(za.metro_languages(TABLE_2_3)), 8)
        with self.assertRaises(SystemExit):
            za.metro_languages(TABLE_2_3.replace("English 10,1 30,6", "English 15,1 30,6"))

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
