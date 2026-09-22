"""The light Wikidata query, and the guard that stops it eating a full answer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


class ATruncatedAnswerIsNotAnAnswer(unittest.TestCase):
    """WDQS answers 200, streams, and abandons the stream at its own timeout.

    The body is then valid JSON up to some byte and then nothing. http_get
    sees a 200 and caches it, so the failure that matters is not the first
    parse error -- it is every retry afterwards being served the same broken
    bytes from disk.
    """

    def setUp(self) -> None:
        self.calls: list[str] = []
        self.forgotten: list[str] = []
        self.bodies: list[str] = []

    def _patched(self):
        def http_get(url, **kwargs):
            self.calls.append(url)
            return self.bodies[min(len(self.calls) - 1, len(self.bodies) - 1)]

        return mock.patch.object(m, "http_get", http_get), \
            mock.patch.object(m, "forget", self.forgotten.append), \
            mock.patch.object(m.time, "sleep", lambda _s: None)

    def test_a_whole_answer_is_parsed_and_the_cache_left_alone(self) -> None:
        self.bodies = ['{"results": {"bindings": [{"unit": {"value": "Q1"}}]}}']
        get, forgotten, slept = self._patched()
        with get, forgotten, slept:
            rows = m.sparql("SELECT * WHERE {}")
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.calls and len(self.calls), 1)
        self.assertEqual(self.forgotten, [],
                         "a body that parsed must stay in the cache")

    def test_a_truncated_body_is_forgotten_before_it_is_re_asked(self) -> None:
        whole = '{"results": {"bindings": [{"unit": {"value": "Q1"}}]}}'
        self.bodies = ['{"results": {"bindings": [{"unit": {"val', whole]
        get, forgotten, slept = self._patched()
        with get, forgotten, slept:
            rows = m.sparql("SELECT * WHERE {}")
        self.assertEqual(len(rows), 1, "the second ask succeeded")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(self.forgotten), 1,
                         "the truncation must be dropped from the cache, or "
                         "the re-ask is served the same bytes")
        self.assertEqual(self.forgotten[0], self.calls[0])

    def test_a_body_that_never_parses_raises_rather_than_reporting_no_units(self) -> None:
        self.bodies = ['{"results": {"bindings": [{"unit": {"val']
        get, forgotten, slept = self._patched()
        with get, forgotten, slept, self.assertRaises(RuntimeError) as caught:
            m.sparql("SELECT * WHERE {}", retries=2)
        self.assertIn("truncated", str(caught.exception))
        self.assertEqual(len(self.calls), 3, "one attempt plus two retries")
        self.assertEqual(len(self.forgotten), 3)


class TheTwoDescentsAreBothAsked(unittest.TestCase):
    """--probe exists to measure, so it must actually run both shapes."""

    def test_the_descent_query_walks_down_and_does_not_walk_the_class_tree(self) -> None:
        descent = m.ADMIN2_DESCENT_QUERY
        self.assertIn("?parent wdt:P150 ?unit", descent,
                      "the cheap shape descends by declared subdivision")
        self.assertNotIn("P279", descent,
                         "walking the class tree is the expense this avoids")
        self.assertNotIn("wdt:P131", descent)

    def test_probe_asks_every_country_both_ways(self) -> None:
        asked: list[str] = []

        def sparql(query, **kwargs):
            asked.append("descent" if "?parent wdt:P150 ?unit" in query else "p131")
            return []

        with mock.patch.object(m, "sparql", sparql), \
             mock.patch.object(m.time, "sleep", lambda _s: None):
            m.probe(["AUT", "AGO"], {"AUT": "Q40", "AGO": "Q916"}, 0.0)
        self.assertEqual(asked, ["p131", "descent", "p131", "descent"])

    def test_a_shape_that_fails_does_not_stop_the_comparison(self) -> None:
        def sparql(query, **kwargs):
            if "P279" in query:
                raise RuntimeError("answer truncated at byte 458736")
            return []

        with mock.patch.object(m, "sparql", sparql), \
             mock.patch.object(m.time, "sleep", lambda _s: None):
            m.probe(["AUT"], {"AUT": "Q40"}, 0.0)

    def test_probe_writes_nothing_even_without_countries(self) -> None:
        with mock.patch.object(sys, "argv",
                               ["x", "--level", "admin2", "--light", "--probe"]):
            self.assertEqual(m.main(), 1,
                             "a probe with no countries is not a sweep")
