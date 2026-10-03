"""NUTS-1 outlines from their NUTS-2 regions; coarse outlines placed only when alone."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import nuts_crosswalk as nc  # noqa: E402
from shapely import STRtree  # noqa: E402
from shapely.geometry import box  # noqa: E402


def region(code, geom):
    return {"id": code, "cntr": code[:2], "geom": geom}


def unit(sid, geom, level="admin2", name=None):
    return {"id": sid, "level": level, "group": "ESP", "name": name or sid, "geom": geom}


class Nuts1(unittest.TestCase):
    def test_a_nuts1_region_is_the_union_of_its_nuts2_regions(self):
        level2 = [region("FRK1", box(0, 0, 1, 1)), region("FRK2", box(1, 0, 2, 1)),
                  region("FRL0", box(5, 5, 6, 6))]
        out = {r["id"]: r for r in nc.nuts1_from(level2)}
        self.assertEqual(sorted(out), ["FRK", "FRL"])
        self.assertAlmostEqual(out["FRK"]["geom"].area, 2.0)
        self.assertEqual(out["FRK"]["cntr"], "FR")


class Alone(unittest.TestCase):
    def place(self, target, shapes, others=()):
        regions = [(3, target)] + [(3, r) for r in others]
        tree = STRtree([s["geom"] for s in shapes])
        return nc.alone(target, regions, 3, tree, shapes, "ESP")

    def test_an_exclave_drawn_coarsely_is_its_one_polygon(self):
        # Ceuta: the outline covers under half of the map's polygon and
        # touches nothing else of the country.
        ceuta = unit("ceuta", box(0, 0, 1, 1))
        spain = unit("spain", box(10, 10, 20, 20))
        found = self.place(region("ES630", box(0, 0, 0.45, 1)), [ceuta, spain])
        self.assertIsNotNone(found)
        self.assertEqual(found[0]["id"], "ceuta")

    def test_part_of_a_unit_is_not_the_unit(self):
        # Gran Canaria lies only on Las Palmas, but so do Lanzarote and
        # Fuerteventura: it is a part of the province, not the province.
        palmas = unit("palmas", box(0, 0, 3, 1))
        found = self.place(region("ES705", box(0, 0, 1.4, 1)), [palmas],
                           others=[region("ES708", box(1.5, 0, 3, 1))])
        self.assertIsNone(found)

    def test_a_region_on_two_units_is_not_placed(self):
        a, b = unit("a", box(0, 0, 1, 1)), unit("b", box(1, 0, 2, 1))
        self.assertIsNone(self.place(region("ES111", box(0.5, 0, 1.5, 1)), [a, b]))

    def test_a_small_outline_inside_a_large_unit_is_not_that_unit(self):
        big = unit("big", box(0, 0, 10, 10))
        self.assertIsNone(self.place(region("ES999", box(0, 0, 1, 1)), [big]))


if __name__ == "__main__":
    unittest.main()
