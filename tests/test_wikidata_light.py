"""The light Wikidata query, and the guard that stops it eating a full answer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_wikidata as m  # noqa: E402


class TheLightQuery(unittest.TestCase):
    """Stripped to what resolves a Wikipedia article: the unit and its parent.

    The full query's three OPTIONAL blocks -- population with its point in
    time, capital, coordinates -- are what made a sweep of all 218 countries
    unrunnable on 21 September 2026: cancelled at the job's 45-minute limit
    having reached about 25, with Wikidata answering 502, 504 and read-timeout
    on most of them.
    """

    def test_it_asks_for_no_population_capital_or_coordinates(self):
        for level in ("admin1", "admin2"):
            with self.subTest(level=level):
                query = m.light_query(level)
                for expensive in ("P1082", "P36", "P625", "OPTIONAL"):
                    self.assertNotIn(expensive, query)

    def test_it_still_asks_for_the_unit_and_its_label(self):
        for level in ("admin1", "admin2"):
            with self.subTest(level=level):
                query = m.light_query(level)
                self.assertIn("?unit", query)
                self.assertIn("?unitLabel", query)

    def test_the_second_level_still_walks_down_through_the_first(self):
        # country -> P150 -> parent -> P131 -> unit. Without that the query
        # would return the first level again under a second-level name.
        query = m.light_query("admin2")
        self.assertIn("wdt:P150", query)
        self.assertIn("wdt:P131", query)


class TheGuard(unittest.TestCase):
    """A light answer must never replace a full one."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "wikidata_admin2.json"
        self.path.write_text(json.dumps([
            {"id": "MEX-WD-Q1", "country": "MEX", "name": "A",
             "population": {"value": 100}},
            {"id": "THA-WD-Q2", "country": "THA", "name": "B",
             "population": {"value": 200}}]))

    def tearDown(self):
        self.dir.cleanup()

    def test_a_country_already_answered_in_full_is_refused_by_name(self):
        with self.assertRaises(SystemExit) as caught:
            m.refuse_light_overwrite(self.path, "admin2", ["MEX"])
        self.assertIn("MEX", str(caught.exception))

    def test_asking_for_everything_is_refused_too(self):
        # This is the dangerous one: --light with no --countries would sweep
        # every country and quietly empty the ones already complete.
        with self.assertRaises(SystemExit) as caught:
            m.refuse_light_overwrite(self.path, "admin2", None)
        self.assertIn("MEX", str(caught.exception))
        self.assertIn("THA", str(caught.exception))

    def test_a_country_not_in_the_file_passes(self):
        m.refuse_light_overwrite(self.path, "admin2", ["ROU", "TUR"])

    def test_an_empty_file_never_blocks_anything(self):
        empty = Path(self.dir.name) / "none.json"
        empty.write_text("[]")
        m.refuse_light_overwrite(empty, "admin2", None)
