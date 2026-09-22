"""The global Wikipedia probe's verdict, which decides where a reader is worth writing."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import probe_wikipedia as p  # noqa: E402


class WhatAnArticleCarries(unittest.TestCase):

    DUTCH = ("{{Infobox provincie\n| naam = Groningen\n"
             "| religie = 68,4% geen gezindte\n}}\n== Religie ==\nProza.\n")
    SLOVAK = ("== Náboženské zloženie ==\n{| class=wikitable\n|-\n"
              "| Rímskokatolícka | 54.77\n|}\n")

    def test_an_infobox_is_never_shadowed_by_a_heading(self):
        # The Netherlands is why. Its province articles have a "Religie"
        # heading with prose under it and the figures in the infobox. A probe
        # that stopped at the heading would call that "section only" and the
        # country would read as having nothing -- the exact mistake that left
        # twelve Dutch provinces empty.
        kind, words = p.verdict(self.DUTCH)
        self.assertEqual(kind, "section+infobox")
        self.assertIn("religie", [w.strip().lower() for w in words])

    def test_a_heading_with_a_table_under_it_is_the_readable_case(self):
        self.assertEqual(p.verdict(self.SLOVAK)[0], "section+table")

    def test_both_together_rank_highest(self):
        both = ("{{Infobox\n| religie = x\n}}\n== Religie ==\n"
                "{| class=wikitable\n| a | 1\n|}\n")
        self.assertEqual(p.verdict(both)[0], "section+table+infobox")

    def test_a_heading_with_only_prose_says_so(self):
        self.assertEqual(p.verdict("== Religion ==\nProse.\n")[0], "section only")

    def test_an_article_about_rivers_carries_nothing(self):
        kind, words = p.verdict("== Geography ==\nRivers.\n")
        self.assertEqual((kind, words), ("nothing", []))

    def test_the_words_are_matched_in_the_language_the_article_is_written_in(self):
        # Every one of these is a heading a reader in this repository already
        # meets: Slovak, Bulgarian, Serbian, Indonesian, Dutch, Czech.
        for heading in ("Náboženské zloženie", "Религия", "Национални састав",
                        "Agama", "Godsdienst", "Národnostní složení",
                        "Composition ethnique", "Mother tongue"):
            with self.subTest(heading=heading):
                self.assertTrue(p.WANTED.search(heading), heading)

    def test_a_heading_about_something_else_is_not_matched(self):
        for heading in ("Geografie", "Economy", "Transport", "History"):
            with self.subTest(heading=heading):
                self.assertFalse(p.WANTED.search(heading), heading)


class TheReportMergesRatherThanReplaces(unittest.TestCase):
    """52,573 units will not probe in one 45-minute job, so it runs in batches.

    A wholesale write would mean every batch discarding the one before it.
    """

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.out = Path(self.dir.name) / "probe.json"

    def _run(self, units, results):
        """Drive main() with the network stubbed out."""
        wikidata = [dict(u, wikidata=u["id"].upper()) for u in units]

        def sitelinks(chunk):
            return {q: {"enwiki": q} for q in chunk}

        def wikitexts(lang, titles):
            return {t: results.get(t, "") for t in titles}

        with mock.patch.object(p, "read_json", side_effect=self._read(wikidata)), \
             mock.patch.object(p, "sitelinks", sitelinks), \
             mock.patch.object(p, "wikitexts", wikitexts), \
             mock.patch.object(p.time, "sleep", lambda _s: None), \
             mock.patch.object(sys, "argv",
                               ["x", "--level", "admin1", "--out", str(self.out)]):
            self.assertEqual(p.main(), 0)
        return json.loads(self.out.read_text())

    def _read(self, wikidata):
        real = p.read_json

        def reader(path, default=None):
            if "wikidata_" in str(path):
                return wikidata
            return real(path, default)
        return reader

    def test_a_second_batch_keeps_the_first_batch_countries(self) -> None:
        self._run([{"id": "nld-1", "country": "NLD", "level": "admin1",
                    "name": "Utrecht"}],
                  {"NLD-1": "== Religie ==\n{| class=wikitable\n|}"})
        report = self._run([{"id": "bel-1", "country": "BEL", "level": "admin1",
                             "name": "Liege"}],
                           {"BEL-1": "== Religion ==\n{| class=wikitable\n|}"})
        self.assertIn("NLD", report["per_country"],
                      "the first batch's country must survive the second")
        self.assertIn("BEL", report["per_country"])
        self.assertEqual({r["country"] for r in report["units"]}, {"NLD", "BEL"})

    def test_re_running_a_country_replaces_it_rather_than_doubling_it(self) -> None:
        unit = [{"id": "nld-1", "country": "NLD", "level": "admin1",
                 "name": "Utrecht"}]
        self._run(unit, {"NLD-1": "== Religie ==\n{| class=wikitable\n|}"})
        report = self._run(unit, {"NLD-1": "== Religie ==\n{| class=wikitable\n|}"})
        self.assertEqual(len(report["units"]), 1,
                         "a country asked about twice appears once")


class AUnitWithNoEnglishArticleIsStillProbed(unittest.TestCase):
    """English is a preference, not a guarantee.

    The first real run raised KeyError('enwiki') 2,000 units in: "enwiki" was
    appended to the list of editions to read whether or not the unit had one.
    """

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.out = Path(self.dir.name) / "probe.json"

    def _probe(self, sitelinks_by_qid):
        units = [{"id": f"XXX-{i}", "country": "XXX", "level": "admin2",
                  "name": f"unit {i}", "wikidata": q}
                 for i, q in enumerate(sitelinks_by_qid)]
        real = p.read_json

        def reader(path, default=None):
            return units if "wikidata_" in str(path) else real(path, default)

        with mock.patch.object(p, "read_json", side_effect=reader), \
             mock.patch.object(p, "sitelinks",
                               lambda chunk: {q: sitelinks_by_qid[q] for q in chunk}), \
             mock.patch.object(p, "wikitexts",
                               lambda lang, titles: {t: "== Religion ==\n{| \n|}"
                                                     for t in titles}), \
             mock.patch.object(p.time, "sleep", lambda _s: None), \
             mock.patch.object(sys, "argv",
                               ["x", "--level", "admin2", "--out", str(self.out)]):
            self.assertEqual(p.main(), 0)
        return json.loads(self.out.read_text())

    def test_an_article_in_one_language_only(self) -> None:
        report = self._probe({"Q1": {"fawiki": "شهرستان"}})
        self.assertEqual(len(report["units"]), 1,
                         "a unit written up only in Persian is still probed")
        self.assertEqual(report["units"][0]["wiki"], "fa")

    def test_english_and_another_edition_are_both_read(self) -> None:
        report = self._probe({"Q1": {"enwiki": "Utrecht", "nlwiki": "Utrecht"}})
        self.assertEqual(len(report["units"]), 1)

    def test_a_unit_with_no_article_anywhere_is_counted_as_such(self) -> None:
        report = self._probe({"Q1": {}})
        self.assertEqual(report["units"], [])
        self.assertEqual(report["per_country"]["XXX"], {"admin2:no article": 1})
