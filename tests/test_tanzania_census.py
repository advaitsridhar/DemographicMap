"""Tests for the Tanzania 2022 census adapter's age tables (Volume 2a), no network."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import tanzania_census as tc  # noqa: E402


def age_table(name, per_year, number=1):
    """The lines of one Volume 2a table: single years 0-79, 80+ and the total, men and women
    half and half (odd counts give the extra person to women)."""
    lines = [f"Table 02. {number}: {name}: Population Distribution by Age, Sex and Rural-Urban "
             "Residence"]
    total = men = 0
    for age in range(80):
        n = per_year(age)
        lines.append(f"{age} {n:,} {n // 2:,} {n - n // 2:,} 0 0")
        total, men = total + n, men + n // 2
    lines.append("80+ 0 0 0 0 0")
    lines.append(f"Total {total:,} {men:,} {total - men:,} 0 0")
    return lines, {"total": total, "men": men, "women": total - men}


class ParseAgesTest(unittest.TestCase):
    def test_a_council_table_and_a_region_table_are_read_and_checked(self):
        council, _ = age_table("Mtama District Council", lambda a: 10 if a < 40 else 0)
        region, _ = age_table("Lindi Region", lambda a: 20 if a < 40 else 0, 2)
        ages = tc.parse_ages(council + region)
        self.assertIn("mtama district", ages["councils"])
        self.assertIn("lindi", ages["regions"])
        self.assertEqual(tc.age_median([ages["councils"]["mtama district"]]), 20.0)

    def test_a_table_short_of_single_years_is_left_out_and_named(self):
        lines, _ = age_table("Kongwa District Council", lambda a: 10)
        ages = tc.parse_ages(lines[:30] + lines[-1:])
        self.assertNotIn("kongwa district", ages["councils"])
        self.assertTrue(any("Kongwa" in u for u in ages["unread"]))


class CheckAgesTest(unittest.TestCase):
    def setUp(self):
        self.lines, self.counts = [], {}
        for i, (name, n) in enumerate((("Mtama District Council", 10),
                                       ("Kilwa District Council", 30)), 1):
            lines, counts = age_table(name, lambda a, n=n: n if a < 40 else 0, i)
            self.lines += lines
            self.counts[tc.council_key(name)] = counts
        k = self.counts
        self.table = {
            "regions": {"lindi": {"name": "Lindi Region",
                                  **{f: k["mtama district"][f] + k["kilwa district"][f]
                                     for f in ("total", "men", "women")}}},
            "councils": {"lindi district": {"name": "Lindi District Council", "region": "lindi",
                                            **k["mtama district"]},
                         "kilwa district": {"name": "Kilwa District Council", "region": "lindi",
                                            **k["kilwa district"]}}}

    def test_a_renamed_council_joins_and_the_region_is_its_councils_added_up(self):
        ages = tc.parse_ages(self.lines)
        report = tc.check_ages(ages, self.table)
        self.assertIn("lindi district", ages["councils"])
        summed = ages["regions"]["lindi"]
        # Named as Volume 1a names them, as the population notes do.
        self.assertEqual(summed["parts"], ["Lindi District Council", "Kilwa District Council"])
        self.assertEqual(ages["councils"]["lindi district"]["name"], "Lindi District Council")
        self.assertEqual(summed["total"], self.table["regions"]["lindi"]["total"])
        self.assertTrue(any("councils' tables added up" in line for line in report))
        note = tc.fields(self.table["regions"]["lindi"], "x", [summed])["median_age_note"]
        self.assertIn("its 2 councils' counts added up", note)

    def test_a_median_of_two_councils_names_them_as_volume_1a_does(self):
        busekelo = {"name": "Busekelo District Council"}
        table = {"regions": {}, "councils": {
            "busokelo district": {"name": "Busokelo District Council", "region": "mbeya",
                                  "total": 3, "men": 1, "women": 2}}}
        ages = {"regions": {}, "councils": {"busekelo district": {
            **busekelo, "total": 3, "men": 1, "women": 2, "ages": {}}}}
        tc.check_ages(ages, table)
        self.assertEqual(ages["councils"]["busokelo district"]["name"],
                         "Busokelo District Council")

    def test_a_table_counting_other_people_is_dropped(self):
        self.table["councils"]["kilwa district"]["total"] += 1
        self.table["councils"]["kilwa district"]["women"] += 1
        ages = tc.parse_ages(self.lines)
        report = tc.check_ages(ages, self.table)
        self.assertNotIn("kilwa district", ages["councils"])
        self.assertNotIn("lindi", ages["regions"])
        self.assertTrue(any("left out" in line for line in report))


if __name__ == "__main__":
    unittest.main()
