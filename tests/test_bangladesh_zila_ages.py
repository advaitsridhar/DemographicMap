"""Bangladesh's zilas: the 2022 census's Community Series, Tables C-01 and C-02.

Synthetic sheets in the Bureau's layout -- title rows, a heading row, a row of
sub-headings or age bands, a row of column numbers, then the zila and its
parts -- and drawn units for them. No workbook and no network.
"""

import unittest
from unittest import mock

from scripts.fetch_census import bangladesh_zila_ages as bz

DIVISIONS = ["Barishal", "Chattogram", "Dhaka", "Khulna", "Mymensingh",
             "Rajshahi", "Rangpur", "Sylhet"]
DRAWN_DIVISION = {"Barishal": "Barisal", "Chattogram": "Chittagong",
                  "Rajshahi": "Rajshani"}


def c01_rows(name: str, population: int, males: int, females: int, hijra: int,
             *, blank: int = 0) -> list[list]:
    """C-01 as Barishal's prints it, with ``blank`` extra rows on top (Feni's)."""
    width = 19
    rows = [[None] * width for _ in range(1 + blank)]
    rows.append([None, "Table C-01: Household and Population by Administrative Unit"]
                + [None] * (width - 2))
    rows.append([None] * width)
    rows.append([None, None, "District", "City Corporation", "Upazila/Thana",
                 "Paurashava", "Union/Ward", "Mauza", "Village/Mahalla",
                 "Administrative Unit", "Household (Except Floating)", None, None, None,
                 "Population (Including Floating)", None, None, None, "Sex Ratio"])
    rows.append([None] * 10 + ["Total", "General", "Institutional", "Others",
                               "Total", "Male", "Female", "Hijra", None])
    rows.append([None, None] + list(range(1, width - 1)))
    rows.append([None, None, "06", None, None, None, None, None, None, name,
                 100, 90, 5, 5, population, males, females, hijra,
                 round(100 * males / females, 2)])
    rows.append([None, None, "06", None, None, None, None, None, None, "Rural",
                 60, 55, 3, 2, population // 2, males // 2, females // 2, 0, 99.0])
    return rows


def c02_rows(name: str, groups: list[int], *, misprint: bool = False) -> list[list]:
    labels = list(bz.LABELS)
    if misprint:
        labels[11] = "50-59"
    width = 4 + len(labels)
    rows = [[None] * width, [None] * width,
            [None, None, "Table C-02: Population by Age Group"] + [None] * (width - 3),
            [None] * width,
            [None, None, "Administrative Unit", "Total", "Age Group (in Years)"]
            + [None] * (width - 5),
            [None] * 4 + labels,
            [None, None] + list(range(1, width - 1)),
            [None, None, name, sum(groups)] + groups,
            [None, None, "Rural", sum(groups) // 2] + [g // 2 for g in groups]]
    return rows


def groups_of(scale: int) -> list[int]:
    """Seventeen groups, fewer at each older age."""
    return [scale * (40 - 2 * i) for i in range(17)]


def zila(division: str, name: str, scale: int, hijra: int = 3) -> dict:
    groups = groups_of(scale)
    groups[4] += hijra                  # the hijra are all aged 20-24 here
    population = sum(groups)
    females = (population - hijra) // 2
    males = population - hijra - females
    return {"name": name, "population": population, "males": males,
            "females": females, "hijra": hijra, "groups": groups,
            "division": division, "label": name.upper(), "url": f"https://x/{name}.xlsx"}


def country() -> tuple[list, dict, list, list, dict]:
    """64 zilas, Table P03 for them, drawn units and the district populations."""
    zilas, units1, units2, populations = [], [], [], {}
    for d, division in enumerate(DIVISIONS):
        did = f"D{d}"
        units1.append({"id": did, "name": DRAWN_DIVISION.get(division, division),
                       "aliases": []})
        for k in range(8):
            name = f"Zila{d}x{k}"
            drawn = name
            if (d, k) == (1, 0):
                name, drawn = "Chattogram", "Chittagong"          # renamed in 2018
            if (d, k) == (6, 0):
                name, drawn = "Chapainawabganj", "Nawabganj"
            z = zila(division, name, d + k + 1)
            zilas.append(z)
            units2.append({"id": f"{did}Z{k}", "name": drawn, "parent": did,
                           "aliases": []})
            populations[bz.fold(name)] = z["population"]
    p03 = {}
    for division in DIVISIONS:
        mine = [z for z in zilas if z["division"] == division]
        groups = [sum(z["groups"][i] for z in mine) for i in range(17)]
        groups[4] -= sum(z["hijra"] for z in mine)
        males = sum(z["males"] for z in mine)
        females = sum(z["females"] for z in mine)
        p03[division] = {"total": (males + females, males, females, 100.0),
                         "groups": [(lo, hi, n, 0, 0) for (lo, hi), n
                                    in zip(bz.GROUPS, groups)]}
    national = [sum(p03[d]["groups"][i][2] for d in DIVISIONS) for i in range(17)]
    p03["National"] = {"total": (sum(national), 0, 0, 100.0),
                       "groups": [(lo, hi, n, 0, 0) for (lo, hi), n
                                  in zip(bz.GROUPS, national)]}
    return zilas, p03, units1, units2, populations


class Sheets(unittest.TestCase):
    def test_c01_reads_the_zila_row_under_its_headings(self):
        got = bz.read_c01(c01_rows("Feni", 1000, 495, 503, 2, blank=2), "Feni")
        self.assertEqual(got, {"name": "Feni", "population": 1000, "males": 495,
                               "females": 503, "hijra": 2})

    def test_c01_whose_sexes_miss_the_population_is_refused(self):
        with self.assertRaises(SystemExit):
            bz.read_c01(c01_rows("Feni", 1000, 495, 503, 3), "Feni")

    def test_c02_reads_seventeen_groups_and_forgives_the_known_misprint(self):
        groups = groups_of(3)
        got = bz.read_c02(c02_rows("Rangamati", groups, misprint=True), "Rangamati")
        self.assertEqual(got["groups"], groups)
        self.assertEqual(got["population"], sum(groups))

    def test_c02_with_other_headings_is_refused(self):
        rows = c02_rows("Rangamati", groups_of(3))
        rows[5][4 + 3] = "15-24"
        with self.assertRaises(SystemExit):
            bz.read_c02(rows, "Rangamati")

    def test_c02_whose_groups_miss_its_total_is_refused(self):
        rows = c02_rows("Rangamati", groups_of(3))
        rows[7][4] += 1
        with self.assertRaises(SystemExit):
            bz.read_c02(rows, "Rangamati")

    def test_a_workbook_the_page_gives_the_wrong_name_is_refused(self):
        groups = groups_of(2)
        n = sum(groups)
        c01 = c01_rows("Barishal", n, n // 2, n - n // 2, 0)
        with self.assertRaises(SystemExit):
            bz.read_zila(c01, c02_rows("Barishal", groups), "Barishal", "BHOLA", "u")
        got = bz.read_zila(c01, c02_rows("Barishal", groups), "Barishal", "BARISHAL", "u")
        self.assertEqual(got["groups"], groups)

    def test_the_pages_misspelt_labels_name_their_zilas(self):
        groups = groups_of(2)
        n = sum(groups)
        c01 = c01_rows("Patuakhali", n, n // 2, n - n // 2, 0)
        got = bz.read_zila(c01, c02_rows("Patuakhali", groups), "Barishal",
                           "PATUAKHAL", "u")
        self.assertEqual(got["name"], "Patuakhali")


class Country(unittest.TestCase):
    def setUp(self):
        self.zilas, self.p03, self.units1, self.units2, self.pops = country()
        self.nation = mock.patch.object(bz, "NATION_2022",
                                        sum(z["population"] for z in self.zilas))
        self.nation.start()

    def tearDown(self):
        self.nation.stop()

    def test_every_zila_is_bound_by_shape_id_with_its_2022_median(self):
        bz.check_divisions(self.zilas, self.p03)
        bz.check_nation(self.zilas, self.p03, None)
        records = bz.build(self.zilas, self.units2, self.units1, self.pops)
        self.assertEqual(len(records), 64)
        self.assertEqual({r["shape_id"] for r in records}, {u["id"] for u in self.units2})
        renamed = next(r for r in records if r["shape_id"] == "D1Z0")
        self.assertEqual(renamed["name"], "Chittagong")
        self.assertEqual(renamed["parent_name"], "Chittagong")
        self.assertEqual(renamed["median_age"]["year"], 2022)
        self.assertIn("five-year", renamed["median_age_note"])
        self.assertTrue(any(r["shape_id"] == "D6Z0" for r in records))

    def test_a_zila_whose_columns_are_shifted_fails_its_division(self):
        z = self.zilas[3]
        z["groups"][5], z["groups"][6] = z["groups"][6], z["groups"][5]
        with self.assertRaises(SystemExit):
            bz.check_divisions(self.zilas, self.p03)

    def test_a_division_whose_excess_is_not_its_hijra_is_refused(self):
        self.zilas[0]["hijra"] += 1
        with self.assertRaises(SystemExit):
            bz.check_divisions(self.zilas, self.p03)

    def test_a_nation_other_than_the_census_count_is_refused(self):
        with mock.patch.object(bz, "NATION_2022", 1), self.assertRaises(SystemExit):
            bz.check_divisions(self.zilas, self.p03)

    def test_a_population_unlike_the_district_workbooks_is_refused(self):
        self.pops[bz.fold("Zila2x3")] += 1
        with self.assertRaises(SystemExit):
            bz.build(self.zilas, self.units2, self.units1, self.pops)

    def test_two_workbooks_of_one_zila_bind_neither(self):
        self.zilas[1]["name"] = self.zilas[0]["name"]
        with self.assertRaises(SystemExit):
            bz.build(self.zilas, self.units2, self.units1, self.pops)


class Median(unittest.TestCase):
    def test_the_median_is_interpolated_within_its_group(self):
        self.assertEqual(bz.median_of([50, 50] + [0] * 15), 5.0)

    def test_eighty_and_over_is_the_last_group_of_table_p03_too(self):
        p03 = [(lo, lo + 4, 1, 0, 0) for lo in range(0, 100, 5)] + [(100, None, 1, 0, 0)]
        self.assertEqual(bz.collapse(p03), [1] * 16 + [5])


if __name__ == "__main__":
    unittest.main()
