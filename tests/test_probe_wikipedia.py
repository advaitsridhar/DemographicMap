"""The global Wikipedia probe's verdict, which decides where a reader is worth writing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

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
