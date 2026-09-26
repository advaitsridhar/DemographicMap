"""Pinned polygons: every pin names a polygon the map draws, in its own country."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census.pins import PINS, UNDRAWN, pin  # noqa: E402


class Pins(unittest.TestCase):
    def test_every_pin_is_a_drawn_polygon(self):
        for iso3, table in PINS.items():
            drawn = {u["id"] for level in ("admin1", "admin2")
                     for u in json.loads((ROOT / "site" / "data" / level / f"{iso3}.units.json")
                                         .read_text())}
            for code, shape in table.items():
                self.assertIn(shape, drawn, f"{iso3} {code} pins a polygon the map does not draw")

    def test_no_polygon_pinned_twice(self):
        for iso3, table in PINS.items():
            self.assertEqual(len(set(table.values())), len(table), iso3)

    def test_undrawn_is_never_pinned(self):
        for iso3, codes in UNDRAWN.items():
            self.assertFalse(codes & set(PINS.get(iso3, {})), iso3)
            for code in codes:
                self.assertEqual(pin(iso3, code), {"no_shape": True})

    def test_pin_fields(self):
        self.assertEqual(pin("COL", "08001"),
                         {"match_by": "shape_id", "shape_id": PINS["COL"]["08001"]})
        self.assertEqual(pin("COL", "05001"), {})
        self.assertEqual(pin("XXX", "1"), {})


if __name__ == "__main__":
    unittest.main()
