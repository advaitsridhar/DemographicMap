"""The pure-Python tiler folds units too small for a zoom instead of dropping them."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import make_pmtiles as m  # noqa: E402
from shapely.geometry import box  # noqa: E402


def feature(shape_id, group, geometry):
    return {"geometry": geometry, "properties": {"shapeID": shape_id, "shapeGroup": group}}


class SmallUnitsAreFoldedNotDropped(unittest.TestCase):
    def test_a_sliver_joins_its_nearest_large_neighbour(self):
        out = m.coalesce_small([feature("A", "ROU", box(0, 0, 10, 10)),
                                feature("B", "ROU", box(20, 0, 30, 10)),
                                feature("a", "ROU", box(10, 0, 10.5, 1))], 1.0)
        areas = {o["properties"]["shapeID"]: round(o["geometry"].area, 2) for o in out}
        self.assertEqual(areas, {"A": 100.5, "B": 100.0})

    def test_the_ground_is_all_still_covered(self):
        units = [feature(f"c{i}", "ROU", box(i, 0, i + 0.1, 0.1)) for i in range(60)]
        out = m.coalesce_small(units, 1.0)
        self.assertAlmostEqual(sum(o["geometry"].area for o in out), 60 * 0.01)
        self.assertEqual(len(out), 1)

    def test_nothing_crosses_a_border(self):
        out = m.coalesce_small([feature("A", "ROU", box(0, 0, 10, 10)),
                                feature("m", "MDA", box(10, 0, 10.5, 1))], 1.0)
        self.assertEqual(sorted(o["properties"]["shapeID"] for o in out), ["A", "m"])


if __name__ == "__main__":
    unittest.main()
