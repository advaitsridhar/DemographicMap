"""Tests for the US Census Bureau Age-Sex reader: groups, medians and joined units, no network."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import uscb_age_sex as ua  # noqa: E402

NAMES = ["BTOTL", "MTOTL", "FTOTL", "B0004", "B0509", "B1014", "B15PL"]
AT = {n: i for i, n in enumerate(NAMES)}


def unit(name, parent, counts, men):
    row = [sum(counts), men, sum(counts) - men, *counts]
    median, m, w, total = ua.figures(row, AT, name)
    return {"code": name, "name": name, "nso": "", "parent": parent, "median": median,
            "men": m, "women": w, "total": total, "groups": ua.groups_of(row, AT)}


class FiguresTest(unittest.TestCase):
    def test_groups_come_youngest_first_with_the_open_one_last(self):
        row = [10, 5, 5, 1, 2, 3, 4]
        self.assertEqual(ua.groups_of(row, AT), [(0, 4, 1), (5, 9, 2), (10, 14, 3), (15, None, 4)])

    def test_groups_that_miss_the_total_stop_the_run(self):
        with self.assertRaises(SystemExit):
            ua.figures([11, 5, 6, 1, 2, 3, 4], AT, "x")

    def test_sexes_that_miss_the_total_stop_the_run(self):
        with self.assertRaises(SystemExit):
            ua.figures([10, 5, 6, 1, 2, 3, 4], AT, "x")

    def test_the_median_is_interpolated_in_its_group(self):
        median, *_ = ua.figures([20, 10, 10, 10, 10, 0, 0], AT, "x")
        self.assertEqual(median, 5.0)


class JoinTest(unittest.TestCase):
    def test_a_joined_unit_adds_its_groups_and_sexes_to_its_host(self):
        units = [unit("PEDERNALES", "P", [10, 10, 0, 0], 10),
                 unit("OVIEDO", "P", [0, 0, 10, 10], 8),
                 unit("OTHER", "Q", [5, 5, 5, 5], 10)]
        out = ua.join(units, (("OVIEDO", "PEDERNALES"),))
        self.assertEqual([u["name"] for u in out], ["PEDERNALES", "OTHER"])
        host = out[0]
        self.assertEqual((host["total"], host["men"], host["women"]), (40, 18, 22))
        self.assertEqual(host["groups"], [(0, 4, 10), (5, 9, 10), (10, 14, 10), (15, None, 10)])
        self.assertEqual(host["median"], 10.0)
        self.assertEqual(host["joined"], ["OVIEDO"])

    def test_a_host_in_another_parent_stops_the_run(self):
        units = [unit("PEDERNALES", "Q", [10, 10, 0, 0], 10),
                 unit("OVIEDO", "P", [0, 0, 10, 10], 8)]
        with self.assertRaises(SystemExit):
            ua.join(units, (("OVIEDO", "PEDERNALES"),))

    def test_a_joined_polygon_must_be_its_parents_only_one(self):
        host = {"code": "1", "name": "PEDERNALES", "joined": ["OVIEDO"]}
        alone = [{"id": "a", "parent": "p"}, {"id": "b", "parent": "q"}]
        ua.sole_polygons([host], {"1": "a"}, [{**s, "name": s["id"]} for s in alone])
        beside = alone + [{"id": "c", "parent": "p"}]
        with self.assertRaises(SystemExit):
            ua.sole_polygons([host], {"1": "a"}, [{**s, "name": s["id"]} for s in beside])
        with self.assertRaises(SystemExit):
            ua.sole_polygons([host], {}, [{**s, "name": s["id"]} for s in alone])

    def test_the_dominican_republic_joins_oviedo_to_pedernales(self):
        self.assertIn(("OVIEDO", "PEDERNALES"), ua.COUNTRIES[0].joined)


def district(name, of, parent, counts, men):
    return {**unit(name, parent, counts, men), "unit": of}


class CarveTest(unittest.TestCase):
    def test_a_district_is_taken_out_of_its_unit_and_stands_alone(self):
        units = [unit("HIGÜEY", "LA ALTAGRACIA", [10, 10, 10, 10], 20)]
        below = [district("LAS LAGUNAS DE NISIBÓN", "HIGÜEY", "LA ALTAGRACIA", [0, 0, 10, 10], 8),
                 district("VERÓN", "HIGÜEY", "LA ALTAGRACIA", [5, 5, 0, 0], 5)]
        out = ua.carve(units, below, (("HIGÜEY", "LAS LAGUNAS DE NISIBÓN",
                                       "La Laguna de Nisibón"),))
        host, own = out
        self.assertEqual((host["total"], host["men"], host["women"]), (20, 12, 8))
        self.assertEqual(host["groups"], [(0, 4, 10), (5, 9, 10), (10, 14, 0), (15, None, 0)])
        self.assertEqual(host["median"], 5.0)
        self.assertEqual(host["carved"], ["La Laguna de Nisibón"])
        self.assertEqual((own["name"], own["nso"], own["total"], own["district_of"]),
                         ("LA LAGUNA DE NISIBÓN", "La Laguna de Nisibón", 20, "HIGÜEY"))
        self.assertEqual(own["parent"], "LA ALTAGRACIA")

    def test_a_district_not_found_stops_the_run_and_names_what_there_is(self):
        units = [unit("HIGÜEY", "LA ALTAGRACIA", [10, 10, 10, 10], 20)]
        below = [district("VERÓN", "HIGÜEY", "LA ALTAGRACIA", [5, 5, 0, 0], 5)]
        with self.assertRaisesRegex(SystemExit, "VERÓN"):
            ua.carve(units, below, (("HIGÜEY", "NISIBÓN", "Nisibón"),))

    def test_a_district_bigger_than_its_unit_in_a_group_stops_the_run(self):
        units = [unit("HIGÜEY", "LA ALTAGRACIA", [10, 10, 0, 20], 20)]
        below = [district("NISIBÓN", "HIGÜEY", "LA ALTAGRACIA", [0, 0, 10, 10], 8)]
        with self.assertRaises(SystemExit):
            ua.carve(units, below, (("HIGÜEY", "NISIBÓN", "Nisibón"),))


if __name__ == "__main__":
    unittest.main()
