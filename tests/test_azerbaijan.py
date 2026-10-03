"""Tests for the Azstat reader: table 1.23's layout and the figures made from it, no network."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import azerbaijan as az  # noqa: E402


ROWS = [
    ["", "1.23. ...", "", "", "", ""],
    ["", "İqtisadi rayonlar", "Cəmi", "o cümlədən", "", ""],
    ["", "", "", "0-4", "5-9", "10+"],
    ["", "C ə m i - h ə r i k i c i n", "", "", "", ""],
    ["", "Azərbaycan Respublikası üzrə - cəmi", 30.0, 10.0, 10.0, 10.0],
    ["", "Bakı şəhəri - cəmi", 12.0, 4.0, 4.0, 4.0],
    ["", "o cümlədən:", "", "", "", ""],
    ["", "Xızı rayonu", 18.0, 6.0, 6.0, 6.0],
]


class TableTest(unittest.TestCase):
    def test_rows_are_named_as_the_unit_and_the_groups_read_in_order(self):
        got = az.age_table(ROWS)
        self.assertEqual(set(got), {az.COUNTRY, "Bakı şəhəri", "Xızı rayonu"})
        self.assertEqual(got["Xızı rayonu"]["groups"], [(0, 4, 6.0), (5, 9, 6.0), (10, None, 6.0)])

    def test_a_table_without_an_open_top_group_is_refused(self):
        rows = [list(r) for r in ROWS]
        rows[2][5] = "10-14"
        with self.assertRaises(SystemExit):
            az.age_table(rows)

    def test_fields(self):
        unit = {"total": 30, "men": 14, "women": 16,
                "groups": [(0, 4, 10), (5, 9, 10), (10, None, 10)]}
        got = az.fields(unit, 2026)
        self.assertEqual(got["median_age"]["value"], 7.5)
        self.assertEqual(got["sex_ratio"]["value"], 87.5)
        self.assertEqual(got["population"]["value"], 30)

    def test_every_unread_field_says_why(self):
        for field in ("ethnicity", "language", "religion"):
            self.assertEqual(az.UNREAD[field]["status"], "not_available")
            self.assertIn("rayon", az.UNREAD[field]["note"])
        # The contested units' note no longer says what the figure is made of.
        self.assertNotIn("registered", az.CONTESTED_NOTE)

    def test_every_polygon_named_once(self):
        names = list(az.POLYGON.values()) + [c for _, c, _ in az.SPLIT.values()] + \
            [r for _, _, r in az.SPLIT.values() if r]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
