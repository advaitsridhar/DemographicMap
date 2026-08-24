"""Tests for the 2020 U.S. Religion Census reader in scripts/fetch_census/us_acs.py.

Every case here is a way the workbook can be read wrongly without complaining.
The doubling one is not hypothetical: summing the adherents column without
excluding the whole-country row reports 97% of the United States as religiously
adherent, and every county's own shares stay correct while it does.
"""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census.us_acs import (  # noqa: E402
    REMAINDER, attach_religion, check_national, read_group_detail, to_traditions,
)

HEADER = ["FIPS", "State Name", "County Name", "Group Code", "Group Name",
          "Congregations", "Adherents", "Adherents as % of Total Adherents",
          "Adherents as % of Total Population"]


def sheet(rows) -> Path:
    """Write a county-sheet CSV and return its path."""
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="")
    writer = csv.writer(handle)
    writer.writerow(HEADER)
    writer.writerows(rows)
    handle.close()
    return Path(handle.name)


def county(fips, group, adherents, pop):
    return [fips, "Somewhere", "Some County", "001", group, 1, adherents,
            "", adherents / pop]


class WholeCountryRow(unittest.TestCase):
    def test_it_is_not_read_as_a_county(self):
        path = sheet([county("01001", "Catholic Church", 300, 1000),
                      county("01003", "Catholic Church", 700, 2000),
                      ["Total", "", "", "", "", 2, 1000, 1, 1000 / 3000]])
        areas, populations, national = read_group_detail(path, "county")
        self.assertEqual(sorted(areas), ["01001", "01003"])
        self.assertEqual(national, 1000)
        self.assertAlmostEqual(populations["01001"], 1000)
        check_national(areas, national, "county")   # reconciles, so does not raise

    def test_absent_control_is_refused(self):
        # Without it the detail rows have nothing independent to check against,
        # and a doubled country reads as a valid table.
        path = sheet([county("01001", "Catholic Church", 300, 1000)])
        areas, _, national = read_group_detail(path, "county")
        self.assertEqual(national, 0)
        with self.assertRaises(SystemExit):
            check_national(areas, national, "county")

    def test_doubling_is_caught(self):
        # What reading the whole-country row as a county produces.
        areas = {"01001": {"Catholic Church": 300.0},
                 "Total": {"all": 1000.0}}
        with self.assertRaises(SystemExit) as caught:
            check_national(areas, 1000.0, "county")
        self.assertIn("%", str(caught.exception))

    def test_the_marker_is_spelled_both_ways(self):
        # The county sheet keys it "Total" and the state sheet "Totals". An
        # exact match on either one silently misses the other sheet.
        for marker in ("Total", "Totals"):
            path = sheet([county("01001", "Catholic Church", 300, 1000),
                          [marker, "", "", "", "", 1, 300, 1, 0.3]])
            areas, _, national = read_group_detail(path, "county")
            self.assertEqual(list(areas), ["01001"], marker)
            self.assertEqual(national, 300, marker)


class Denominator(unittest.TestCase):
    def test_rows_disagreeing_on_population_are_refused(self):
        # The area's population is recovered by inverting the published share
        # column. If the rows are not on one denominator that inversion is
        # meaningless, and every share but the first would be wrong.
        path = sheet([county("01001", "Catholic Church", 300, 1000),
                      county("01001", "Southern Baptist Convention", 400, 5000)])
        with self.assertRaises(SystemExit) as caught:
            read_group_detail(path, "county")
        self.assertIn("denominator", str(caught.exception))


class Traditions(unittest.TestCase):
    def test_orthodox_in_a_name_does_not_mean_orthodox(self):
        # Both are Protestant. Keyword matching puts them under Orthodox
        # Christian, and nothing downstream would notice.
        got = to_traditions({"Orthodox Presbyterian Church": 10.0,
                             "Orthodox Mennonite Church": 5.0})
        self.assertEqual(got, {"Protestant": 15.0})

    def test_catholic_in_a_name_does_not_mean_roman_catholic(self):
        got = to_traditions({"Catholic Church": 100.0,
                             "Polish National Catholic Church": 7.0})
        self.assertEqual(got, {"Catholic": 100.0, "Other Christian": 7.0})

    def test_movements_of_one_religion_are_summed(self):
        got = to_traditions({"Orthodox Judaism": 3.0, "Reform Judaism": 2.0,
                             "Conservative Judaism": 1.0})
        self.assertEqual(got, {"Judaism": 6.0})

    def test_unlisted_bodies_default_to_protestant(self):
        got = to_traditions({"Some Church Founded Last Tuesday": 4.0})
        self.assertEqual(got, {"Protestant": 4.0})


if __name__ == "__main__":
    unittest.main()


class Remainder(unittest.TestCase):
    """The share the study does not account for is named, not scaled away.

    Coverage runs from 27.3% of New Hampshire to 76.2% of Utah. Rescaling each
    area to 100% would make them look equally religious.
    """

    def attach(self, adherents, pop):
        path = sheet([county("01001", "Catholic Church", adherents, pop),
                      ["Total", "", "", "", "", 1, adherents, 1, adherents / pop]])
        records = [{"codes": {"geoid": "01001"}, "sources": [],
                    "religion": {"status": "not_collected"}}]
        attach_religion(records, path, "county")
        return records[0]["religion"]

    def test_shortfall_becomes_a_named_group(self):
        got = {row["group"]: row["pct"] for row in self.attach(300, 1000)}
        self.assertEqual(got["Catholic"], 30.0)
        self.assertEqual(got[REMAINDER], 70.0)
        self.assertAlmostEqual(sum(got.values()), 100.0)

    def test_coverage_differences_are_preserved(self):
        # The whole point: two areas with the same single body but different
        # coverage must not come out looking the same.
        low = {r["group"]: r["pct"] for r in self.attach(300, 1000)}
        high = {r["group"]: r["pct"] for r in self.attach(760, 1000)}
        self.assertNotEqual(low["Catholic"], high["Catholic"])
        self.assertEqual(high["Catholic"], 76.0)

    def test_no_negative_remainder(self):
        # 30 counties report more adherents than residents, because rural
        # congregations draw members from outside them. King County, Texas
        # reports 452%. A negative remainder is not a group of people.
        got = {row["group"]: row["pct"] for row in self.attach(4525, 1000)}
        self.assertNotIn(REMAINDER, got)
