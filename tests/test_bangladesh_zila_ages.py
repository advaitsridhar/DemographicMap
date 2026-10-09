"""Bangladesh's zilas: the 2011 census's five-year age groups (USCB extraction).

A synthetic workbook in the Bureau's two-header-row layout -- eight divisions
of eight zilas -- and drawn units for them. No network.
"""

import unittest
from unittest import mock

from scripts.fetch_census import bangladesh_zila_ages as bz

DIVISIONS = ["BARISHAL", "CHATTOGRAM", "DHAKA", "KHULNA", "MYMENSINGH",
             "RĀJSHĀHI", "RANGPUR", "SYLHET"]
DRAWN_DIVISION = {"BARISHAL": "Barisal", "CHATTOGRAM": "Chittagong",
                  "RĀJSHĀHI": "Rajshani"}


def groups(scale: int) -> list[int]:
    """Seventeen five-year groups, fewer at each older age."""
    return [scale * (20 - i) for i in range(17)]


def header() -> list[list[str]]:
    names = ["AREA_NAME", "ADM1_NAME", "ADM2_NAME", "ADM_LEVEL", "NSO_CODE"]
    for sex in "BMF":
        names += [f"{sex}TOTL"] + [f"{sex}{stem}" for _lo, _hi, stem in bz.GROUPS]
    return [names, list(names)]


def row(name: str, division: str, level: int, males: list[int], females: list[int]) -> list:
    both = [m + f for m, f in zip(males, females)]
    cells = [name, division, name if level == 2 else "", level, ""]
    for counts in (both, males, females):
        cells += [sum(counts)] + counts
    return cells


def workbook():
    """Rows, drawn admin1 and admin2 units, and the nation's total."""
    rows = header()
    units1, units2 = [], []
    division_rows, nation_m, nation_f = [], [0] * 17, [0] * 17
    for d, division in enumerate(DIVISIONS):
        did = f"D{d}"
        units1.append({"id": did, "name": DRAWN_DIVISION.get(division, division.title()),
                       "aliases": []})
        div_m, div_f = [0] * 17, [0] * 17
        for k in range(8):
            name = f"ZILA{d}X{k}"
            drawn = name
            if (d, k) == (1, 0):
                name, drawn = "CHATTOGRAM", "Chittagong"    # renamed in 2018
            if (d, k) == (1, 1):
                name, drawn = "BRĀHMANBĀRIA", "Brahamanbaria"
            m, f = groups(d + k + 1), groups(d + k + 2)
            rows.append(row(name, division, 2, m, f))
            units2.append({"id": f"{did}Z{k}", "name": drawn, "parent": did,
                           "aliases": [], "population": {"value": int(1.2 * (sum(m) + sum(f)))}})
            div_m = [a + b for a, b in zip(div_m, m)]
            div_f = [a + b for a, b in zip(div_f, f)]
        division_rows.append(row(division, division, 1, div_m, div_f))
        nation_m = [a + b for a, b in zip(nation_m, div_m)]
        nation_f = [a + b for a, b in zip(nation_f, div_f)]
    rows[2:2] = [row("BANGLADESH", "", 0, nation_m, nation_f), *division_rows]
    return rows, units1, units2, sum(nation_m) + sum(nation_f)


class ZilaAges(unittest.TestCase):
    def test_every_zila_is_bound_by_shape_id_with_its_2011_median(self):
        rows, units1, units2, total = workbook()
        with mock.patch.object(bz, "NATION_2011", total):
            records = bz.build(rows, units2, units1)
        self.assertEqual(len(records), 64)
        self.assertEqual({r["shape_id"] for r in records}, {u["id"] for u in units2})
        renamed = next(r for r in records if r["shape_id"] == "D1Z0")
        self.assertEqual(renamed["name"], "Chittagong")
        self.assertEqual(renamed["median_age"]["year"], 2011)
        self.assertEqual(renamed["match_by"], "shape_id")
        # 0-4 holds 20 parts in 189: the middle person is in the 20-24 group
        # or below, never the open top one.
        self.assertLess(renamed["median_age"]["value"], 40)
        self.assertIn("five-year", renamed["median_age_note"])

    def test_a_zila_whose_groups_miss_its_total_is_refused(self):
        rows, units1, units2, total = workbook()
        rows[12][6] += 1                            # one zila's 0-4, both sexes
        with mock.patch.object(bz, "NATION_2011", total), self.assertRaises(SystemExit):
            bz.build(rows, units2, units1)

    def test_a_drawn_population_unlike_the_2011_count_refuses_the_binding(self):
        rows, units1, units2, total = workbook()
        units2[5]["population"]["value"] = 10      # not the same place
        with mock.patch.object(bz, "NATION_2011", total), self.assertRaises(SystemExit):
            bz.build(rows, units2, units1)

    def test_a_nation_other_than_the_census_count_is_refused(self):
        rows, units1, units2, total = workbook()
        with mock.patch.object(bz, "NATION_2011", total + 1), self.assertRaises(SystemExit):
            bz.build(rows, units2, units1)

    def test_renamed_zilas_reach_the_boundary_files_spelling(self):
        self.assertIn("Chittagong", bz.zila_names("CHATTOGRAM"))
        self.assertIn("Brahamanbaria", bz.zila_names("BRĀHMANBĀRIA"))
        self.assertIn("Rajshani", bz.division_names("RĀJSHĀHI"))

    def test_the_median_is_interpolated_within_its_group(self):
        area = {"B": (100, [50, 50] + [0] * 15)}
        self.assertEqual(bz.median_of(area), 5.0)


if __name__ == "__main__":
    unittest.main()
