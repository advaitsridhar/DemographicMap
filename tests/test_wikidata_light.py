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


def _unit(qid: str, parent: str = "Q1") -> dict:
    return {"unit": {"value": f"http://www.wikidata.org/entity/{qid}"},
            "unitLabel": {"value": qid},
            "parent": {"value": f"http://www.wikidata.org/entity/{parent}"},
            "parentLabel": {"value": parent}}


class NeitherDescentCoversACountryAlone(unittest.TestCase):
    """The probe of 22 September measured both, and neither wins outright.

    P131 with the class walk loses Austria and Australia entirely; the P150
    descent loses 62% of Angola, 63% of Belgium and all of Azerbaijan. So the
    sweep asks both and unions them.
    """

    def test_the_union_keeps_the_primary_row_for_a_unit_found_twice(self) -> None:
        rich = dict(_unit("Q10"), pop={"value": "5000"})
        united = m.union_by_unit([rich], [_unit("Q10")])
        self.assertEqual(len(united), 1, "a unit found both ways appears once")
        self.assertIn("pop", united[0],
                      "the primary carries the population; the descent does not")

    def test_the_descent_adds_units_the_primary_missed(self) -> None:
        united = m.union_by_unit([_unit("Q10")], [_unit("Q10"), _unit("Q11")])
        self.assertEqual([r["unitLabel"]["value"] for r in united], ["Q10", "Q11"])

    def test_a_country_the_primary_cannot_answer_falls_back_to_the_descent(self) -> None:
        def sparql(query, **kwargs):
            if "P279" in query:
                raise RuntimeError("answer truncated at byte 1244867")
            return [_unit("Q10"), _unit("Q11")]

        with mock.patch.object(m, "sparql", sparql), \
             mock.patch.object(m.time, "sleep", lambda _s: None):
            rows, reached = m.admin2_rows("Q40", m.ADMIN2_QUERY, 0.0)
        self.assertEqual(len(rows), 2, "Austria is served by the descent")
        self.assertEqual(reached, "descent only",
                         "a country served by the cheap query must say so")

    def test_a_country_served_only_by_the_descent_still_raises_if_that_fails_too(self) -> None:
        with mock.patch.object(m, "sparql", mock.Mock(side_effect=RuntimeError("no"))), \
             mock.patch.object(m.time, "sleep", lambda _s: None), \
             self.assertRaises(RuntimeError):
            m.admin2_rows("Q40", m.ADMIN2_QUERY, 0.0)

    def test_a_failed_descent_does_not_discard_a_good_primary_answer(self) -> None:
        def sparql(query, **kwargs):
            if "P279" in query:
                return [_unit("Q10")]
            raise RuntimeError("descent broke")

        with mock.patch.object(m, "sparql", sparql), \
             mock.patch.object(m.time, "sleep", lambda _s: None):
            rows, reached = m.admin2_rows("Q916", m.ADMIN2_QUERY, 0.0)
        self.assertEqual(len(rows), 1, "Azerbaijan's 191 units are not thrown away")
        self.assertEqual(reached, "primary only")

    def test_the_report_counts_what_the_descent_contributed(self) -> None:
        def sparql(query, **kwargs):
            return [_unit("Q10")] if "P279" in query else [_unit("Q10"), _unit("Q11")]

        with mock.patch.object(m, "sparql", sparql), \
             mock.patch.object(m.time, "sleep", lambda _s: None):
            rows, reached = m.admin2_rows("Q1", m.ADMIN2_QUERY, 0.0)
        self.assertEqual(len(rows), 2)
        self.assertEqual(reached, "1 added by descent")


class ADeterministicFailureIsNotReAskedFourTimes(unittest.TestCase):
    def test_one_retry_by_default(self) -> None:
        import inspect
        default = inspect.signature(m.sparql).parameters["retries"].default
        self.assertEqual(default, 1,
                         "both of Austria's attempts returned byte-identical "
                         "bodies; a second 90-second ask buys nothing")


class TheFallbackPaysForItself(unittest.TestCase):
    def test_the_primary_is_asked_once_because_a_descent_follows_it(self) -> None:
        asked: list[int] = []

        def sparql(query, **kwargs):
            if "P279" in query:
                asked.append(kwargs.get("retries", 1))
                raise RuntimeError("answer truncated at byte 1244867")
            return []

        with mock.patch.object(m, "sparql", sparql), \
             mock.patch.object(m.time, "sleep", lambda _s: None):
            m.admin2_rows("Q40", m.ADMIN2_QUERY, 0.0)
        self.assertEqual(asked, [0],
                         "re-asking a deterministic truncation costs 90 "
                         "seconds and returns the same bytes")


def uri(qid):
    return {"type": "uri", "value": f"http://www.wikidata.org/entity/{qid}"}


def lit(v):
    return {"type": "literal", "value": str(v)}


def stmt(qid, pop, year=None, rank="NormalRank", coord=None):
    row = {"unit": uri(qid), "pop": lit(pop),
           "rank": uri(f"http://wikiba.se/ontology#{rank}")}
    row["rank"] = {"type": "uri", "value": f"http://wikiba.se/ontology#{rank}"}
    if year:
        row["popTime"] = lit(f"{year}-01-01T00:00:00Z")
    if coord:
        row["coord"] = lit(coord)
    return row


class BestStatement(unittest.TestCase):
    def test_preferred_beats_a_later_normal(self):
        rows = [stmt("Q1", 100, 2021, "PreferredRank"), stmt("Q1", 90, 2023)]
        self.assertEqual(m.best_statement(rows), (100, 2021))

    def test_latest_year_among_equals(self):
        rows = [stmt("Q1", 100, 2011), stmt("Q1", 120, 2021), stmt("Q1", 80)]
        self.assertEqual(m.best_statement(rows), (120, 2021))

    def test_deprecated_and_empty_are_ignored(self):
        rows = [stmt("Q1", 500, 2024, "DeprecatedRank"), stmt("Q1", 0, 2020)]
        self.assertIsNone(m.best_statement(rows))


class Hydrate(unittest.TestCase):
    def test_fills_only_what_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wd.json"
            rows = [
                {"id": "ROU-WD-Q1", "wikidata": "Q1", "country": "ROU", "name": "Abram",
                 "population": {"status": "not_available"},
                 "coordinates": {"status": "not_available"}},
                {"id": "ROU-WD-Q2", "wikidata": "Q2", "country": "ROU", "name": "Kept",
                 "population": {"value": 7, "year": 2011}, "coordinates": [1.0, 2.0]},
                {"id": "ROU-WD-Q3", "wikidata": "Q3", "country": "ROU", "name": "Bare",
                 "population": {"status": "not_available"},
                 "coordinates": {"status": "not_available"}},
            ]
            path.write_text(json.dumps(rows))
            answer = [stmt("Q1", 3100, 2021, coord="Point(22.4 47.2)"),
                      {"unit": uri("Q3")}]
            with mock.patch.object(m, "sparql", return_value=answer) as asked, \
                 mock.patch.object(m, "blank_items", return_value={"Q1", "Q2", "Q3"}), \
                 mock.patch.object(m.time, "sleep"):
                m.hydrate(path, None, 0)
            query = asked.call_args[0][0]
            self.assertIn("wd:Q1", query)
            self.assertNotIn("wd:Q2", query, "a row with a population is not asked for")
            out = {r["name"]: r for r in json.loads(path.read_text())}
            self.assertEqual(out["Abram"]["population"]["value"], 3100)
            self.assertEqual(out["Abram"]["population"]["year"], 2021)
            self.assertEqual(out["Abram"]["coordinates"], [22.4, 47.2])
            self.assertEqual(out["Kept"]["population"]["value"], 7)
            self.assertEqual(out["Bare"]["population"]["status"], "not_available")
            self.assertEqual(out["Bare"]["population"]["note"], m.ASKED_BY_ID)
            # A second run does not ask again for what has been asked.
            with mock.patch.object(m, "sparql", return_value=[]) as again, \
                 mock.patch.object(m, "blank_items", return_value={"Q1", "Q2", "Q3"}), \
                 mock.patch.object(m.time, "sleep"):
                m.hydrate(path, None, 0)
            again.assert_not_called()

    def test_stops_at_its_budget_and_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wd.json"
            path.write_text(json.dumps([
                {"id": "X-WD-Q9", "wikidata": "Q9", "country": "X", "name": "N",
                 "population": {"status": "not_available"}}]))
            with mock.patch.object(m, "sparql") as asked, \
                 mock.patch.object(m, "blank_items", return_value={"Q9"}):
                m.hydrate(path, None, 0, budget_minutes=-1)
            asked.assert_not_called()
            self.assertTrue(path.exists())


class Enrich(unittest.TestCase):
    def test_local_names_become_aliases_for_unjoined_rows_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wd.json"
            path.write_text(json.dumps([
                {"id": "LVA-WD-Q1", "wikidata": "Q1", "country": "LVA",
                 "name": "Abava Parish", "population": {"status": "not_available"}},
                {"id": "LVA-WD-Q2", "wikidata": "Q2", "country": "LVA",
                 "name": "Joined", "population": {"status": "not_available"}},
                {"id": "XYZ-WD-Q3", "wikidata": "Q3", "country": "XYZ",
                 "name": "No languages", "population": {"status": "not_available"}},
            ]))
            labels = [{"unit": uri("Q1"), "label": lit("Abavas pagasts")},
                      {"unit": uri("Q1"), "label": lit("Abava Parish")}]
            calls = []

            def answer(query, **_):
                calls.append(query)
                return labels if "rdfs:label" in query else [stmt("Q1", 950, 2021)]

            with mock.patch.object(m, "sparql", side_effect=answer), \
                 mock.patch.object(m, "joined_items", return_value={"Q2"}), \
                 mock.patch.object(m.time, "sleep"):
                m.enrich(path, None, 0)
            self.assertIn('"lv"', calls[0])
            self.assertNotIn("wd:Q2", calls[0], "a joined row needs no second name")
            out = {r["wikidata"]: r for r in json.loads(path.read_text())}
            self.assertEqual(out["Q1"]["aliases"], ["Abavas pagasts"])
            self.assertEqual(out["Q1"]["population"]["value"], 950)
            self.assertNotIn("aliases", out["Q2"])
            self.assertNotIn("aliases", out["Q3"])


class ClassSweep(unittest.TestCase):
    def test_adds_missing_items_and_never_replaces_a_population(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wd.json"
            path.write_text(json.dumps([
                {"id": "NLD-WD-Q1", "wikidata": "Q1", "country": "NLD", "name": "Aalten",
                 "population": {"value": 27000, "year": 2020}},
            ]))
            answer = [
                dict(stmt("Q1", 99999, 2024), unitLabel=lit("Aalten")),
                dict(stmt("Q2", 25000, 2024, coord="Point(6.1 52.9)"),
                     unitLabel=lit("Aa en Hunze"), parent=uri("Q772"),
                     parentLabel=lit("Drenthe")),
            ]
            with mock.patch.object(m, "sparql", return_value=answer), \
                 mock.patch.object(m, "country_qids", return_value={"NLD": "Q55"}):
                m.class_sweep(path, ["NLD:Q2039348"])
            out = {r["wikidata"]: r for r in json.loads(path.read_text())}
            self.assertEqual(out["Q1"]["population"]["value"], 27000)
            self.assertEqual(out["Q2"]["name"], "Aa en Hunze")
            self.assertEqual(out["Q2"]["parent_name"], "Drenthe")
            self.assertEqual(out["Q2"]["population"]["value"], 25000)
            self.assertEqual(out["Q2"]["coordinates"], [6.1, 52.9])
