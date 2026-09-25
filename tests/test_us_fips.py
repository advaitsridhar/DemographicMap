"""US counties: pinned by FIPS where the polygon is known, and named without their state where not."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import _shared, us_acs  # noqa: E402

SHAPES = {"USA": {"51683": {"shape_id": "S-MANASSAS", "level": "admin2", "name": "Manassas"}}}


def row(name, geoid, state="Virginia"):
    return {"name": name, "parent_name": state, "codes": {"geoid": geoid}}


class BindByFips(unittest.TestCase):
    def bind(self, records):
        with mock.patch.object(_shared, "read_json", return_value=SHAPES):
            return us_acs.bind_by_fips(records)

    def test_a_known_code_pins_the_row_and_takes_the_polygon_name(self):
        records = [row("Manassas city, Virginia", "51683")]
        self.assertEqual(self.bind(records), 1)
        self.assertEqual(records[0]["shape_id"], "S-MANASSAS")
        self.assertEqual(records[0]["name"], "Manassas")

    def test_an_unknown_code_keeps_its_name_without_the_state(self):
        records = [row("Manassas Park city, Virginia", "51685")]
        self.assertEqual(self.bind(records), 0)
        self.assertEqual(records[0]["name"], "Manassas Park city")
        self.assertNotIn("match_by", records[0])

    def test_a_name_that_does_not_end_in_its_state_is_left_alone(self):
        records = [row("St. Croix", "78010", state="United States Virgin Islands")]
        self.bind(records)
        self.assertEqual(records[0]["name"], "St. Croix")


if __name__ == "__main__":
    unittest.main()
