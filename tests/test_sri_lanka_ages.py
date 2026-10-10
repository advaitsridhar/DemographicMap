"""Sri Lanka 2024: the five-year age table and the checks that gate it.

The fixtures follow the Department's workbook: two title rows, a header naming
the id columns and "Age Group", a row naming Total and the groups, then the
nation, each district, and the district's divisions under it. No network.
"""

import unittest

from scripts.fetch_census import sri_lanka as lk

GROUPS = ["0 - 4", "5 - 9", "10-14", "15-19", "20-24", "25-29", "30-34",
          "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65-69",
          "70-74", "75-79", "80-84", "85-89", "90-94", "95+"]


def table(districts: dict[str, list[int]], *, national: list[int] | None = None):
    rows = [("Census of Population and Housing 2024",) + (None,) * 26,
            ("Population by five year age group",) + (None,) * 26,
            ("District Code", "District  Name", "DSD Code", "DSD Name",
             "GND Code", "GND Name", "Age Group") + (None,) * 20,
            (None,) * 6 + ("Total", *GROUPS)]
    if national is None:
        national = [sum(column) for column in zip(*districts.values())]
    rows.append(("Sri Lanka", None, None, None, None, None, sum(national), *national))
    for code, (name, groups) in enumerate(districts.items(), 11):
        rows.append((code, name + " ", None, None, None, None, sum(groups), *groups))
        # A division's own row, which must not be read as the district.
        rows.append((None, None, 3, name, None, None, sum(groups), *groups))
        rows.append((code, name, 3, name, 5, "Somewhere", 7, *([0] * 19 + [7])))
    return rows


def young(scale: int) -> list[int]:
    """Fewer people in each older group."""
    return [scale * (20 - i) for i in range(20)]


class AgeTable(unittest.TestCase):
    def test_the_district_rows_are_read_and_the_divisions_are_not(self):
        got = lk.read_age_groups(table({"Colombo": young(10), "Kandy": young(5)}))
        self.assertEqual(set(got), {"Sri Lanka", "Colombo", "Kandy"})
        self.assertEqual(got["Colombo"]["total"], sum(young(10)))
        self.assertEqual(got["Colombo"]["groups"][0], (0, 4, 200))
        self.assertEqual(got["Colombo"]["groups"][-1], (95, None, 10))

    def test_a_group_label_that_reads_neither_way_stops_the_run(self):
        rows = table({"Colombo": young(10)})
        rows[3] = rows[3][:-1] + ("Not stated",)
        with self.assertRaises(SystemExit):
            lk.read_age_groups(rows)

    def test_checks_against_a1_and_the_nation(self):
        ages = lk.read_age_groups(table({"Colombo": young(10), "Monaragala": young(5)}))
        units = {"Sri Lanka": {"population": sum(young(15))},
                 "Colombo": {"population": sum(young(10))},
                 "Moneragala": {"population": sum(young(5))}}
        old = lk.NATIONAL_CONTROLS["_total"]
        lk.NATIONAL_CONTROLS["_total"] = sum(young(15))
        try:
            got = lk.check_ages(ages, units)
        finally:
            lk.NATIONAL_CONTROLS["_total"] = old
        # The boundary file's spelling reaches the census's district.
        self.assertIn("Moneragala", got)

    def test_a_district_that_is_not_a1s_population_is_refused(self):
        ages = lk.read_age_groups(table({"Colombo": young(10)}))
        units = {"Sri Lanka": {"population": sum(young(10))},
                 "Colombo": {"population": sum(young(10)) + 1}}
        with self.assertRaises(SystemExit):
            lk.check_ages(ages, units)

    def test_districts_that_do_not_make_the_nation_are_refused(self):
        # The same total, with one person moved from the first group to the
        # second: only the group-by-group check can see it.
        national = young(10)
        national[0] -= 1
        national[1] += 1
        ages = lk.read_age_groups(table({"Colombo": young(10)}, national=national))
        units = {"Sri Lanka": {"population": sum(young(10))},
                 "Colombo": {"population": sum(young(10))}}
        old = lk.NATIONAL_CONTROLS["_total"]
        lk.NATIONAL_CONTROLS["_total"] = sum(young(10))
        try:
            with self.assertRaises(SystemExit):
                lk.check_ages(ages, units)
        finally:
            lk.NATIONAL_CONTROLS["_total"] = old

    def test_the_median_is_interpolated_within_its_group(self):
        groups = [(0, 4, 100), (5, 9, 100), (10, 14, 100), (15, None, 100)]
        fields = lk.age_fields(groups)
        # 400 people: the 200th is the last of 5-9, at 10.0.
        self.assertEqual(fields["median_age"]["value"], 10.0)
        self.assertIn("five-year group", fields["median_age_note"])

    def test_a_median_in_the_open_group_is_not_given(self):
        self.assertEqual(lk.age_fields([(0, 4, 1), (5, None, 100)]), {})


if __name__ == "__main__":
    unittest.main()
