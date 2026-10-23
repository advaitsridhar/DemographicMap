"""Tests for the Uganda crosswalk's tests of a polygon (no boundary files needed)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import uganda_crosswalk as ux  # noqa: E402


class RefusalsTest(unittest.TestCase):
    def test_a_sliver_along_the_line_is_not_a_misfit(self):
        # Kira Municipality's 16% inside the Kampala polygon, none of it deeper
        # than 2 km: two drawings of one line.
        stats = {"kira": {"share": 0.16, "deep_in": 0.0, "deep_out": 0.84},
                 "rubaga": {"share": 0.83, "deep_in": 0.5, "deep_out": 0.0}}
        self.assertEqual(ux.refusals(stats, {"rubaga"}), [])

    def test_a_neighbours_ground_deep_inside_refuses_the_polygon(self):
        # Kagoma North County: 24% of its points inside Butembe, 10% deeper
        # than 2 km.
        stats = {"kagoma north": {"share": 0.24, "deep_in": 0.10},
                 "butembe": {"share": 0.87, "deep_in": 0.6, "deep_out": 0.0}}
        self.assertEqual(ux.refusals(stats, {"butembe"}), [("kagoma north", "in")])

    def test_a_quarter_of_a_neighbour_inside_refuses_it_however_shallow(self):
        stats = {"x": {"share": 0.25, "deep_in": 0.0}}
        self.assertEqual(ux.refusals(stats, set()), [("x", "in")])

    def test_an_own_unit_deep_beyond_the_line_refuses_it(self):
        stats = {"kazo": {"share": 0.78, "deep_in": 0.5, "deep_out": 0.16}}
        self.assertEqual(ux.refusals(stats, {"kazo"}), [("kazo", "out")])

    def test_crossing_names_units_with_a_tenth_inside_or_deep_points(self):
        stats = {"a": {"share": 0.24, "deep_in": 0.048}, "b": {"share": 0.11, "deep_in": 0.0},
                 "c": {"share": 0.05, "deep_in": 0.0}, "own": {"deep_out": 0.06}}
        self.assertEqual(ux.crossing(stats, {"own"}), ["a", "b", "own"])


class NamesTest(unittest.TestCase):
    def test_names_fold_as_the_tables_and_outlines_spell_them(self):
        self.assertEqual(ux.fold("Bugembe Town Council"), ux.fold("BUGEMBE TC"))
        self.assertEqual(ux.fold("Mpumudde Division"), ux.fold("MPUMUDDE"))
        self.assertEqual(ux.district_key("JINJA CITY"), ux.district_key("Jinja"))


if __name__ == "__main__":
    unittest.main()
