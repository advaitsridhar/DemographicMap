"""Tests for the eastern adapters' national median check, no network."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_census import east_checks  # noqa: E402


def published(values):
    """A stand-in for Eurostat: {year: median}."""
    def lookup(geo, year):
        if year in values:
            return values[year], "Eurostat demo_pjanind"
        return None, f"no median for {geo} on 1 January {year}"
    return lookup


class CheckMedianTest(unittest.TestCase):
    def test_the_same_year_within_the_bound_passes(self):
        with mock.patch.object(east_checks, "published_median", published({2017: 40.5})):
            line = east_checks.check_median("UA", 2017, 40.5, "ukraine")
        self.assertIn("bound 0.3", line)

    def test_a_tenth_of_float_noise_at_the_bound_is_not_a_fault(self):
        # 37.7 - 37.4 is 0.30000000000000426 in floating point.
        with mock.patch.object(east_checks, "published_median", published({2015: 37.4})):
            east_checks.check_median("GE", 2015, 37.7, "georgia")

    def test_years_apart_stop_the_run(self):
        with mock.patch.object(east_checks, "published_median", published({2024: 33.7})):
            with self.assertRaises(SystemExit):
                east_checks.check_median("AM", 2024, 39.1, "armenia")

    def test_the_year_before_widens_the_bound(self):
        with mock.patch.object(east_checks, "published_median", published({2025: 35.1})):
            line = east_checks.check_median("AZ", 2026, 35.7, "azerbaijan")
            self.assertIn("1 January 2025", line)
            with self.assertRaises(SystemExit):
                east_checks.check_median("AZ", 2026, 36.0, "azerbaijan")

    def test_nothing_published_is_said_and_passes(self):
        with mock.patch.object(east_checks, "published_median", published({})):
            line = east_checks.check_median("AM", 2026, 39.9, "armenia")
        self.assertIn("none to check it against", line)


if __name__ == "__main__":
    unittest.main()
