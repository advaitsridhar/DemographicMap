"""Tests for the text parsing and gap semantics in scripts/common.py.

Every case here is a real string that broke an earlier version of the parser.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import common  # noqa: E402


class ParseComposition(unittest.TestCase):
    def test_plain_shares(self):
        got = common.parse_composition(
            "Roman Catholic 24.8%, Protestant 22.6%, Muslim 3.7%, none 43.8% (2022 est.)")
        self.assertEqual(
            got,
            [{"group": "Roman Catholic", "pct": 24.8},
             {"group": "Protestant", "pct": 22.6},
             {"group": "Muslim", "pct": 3.7},
             {"group": "none", "pct": 43.8}])

    def test_commas_inside_parentheses_do_not_split_groups(self):
        # A naive split(",") invents a group called "Jewish".
        got = common.parse_composition(
            "Muslim (official; predominantly Sunni) 99%, "
            "other (includes Christian, Jewish, Ahmadi Muslim, Shia Muslim) <1% (2012 est.)")
        self.assertEqual([row["group"] for row in got], ["Muslim", "other"])

    def test_semicolon_inside_parentheses_does_not_truncate(self):
        got = common.parse_composition(
            "Muslim (official; predominantly Sunni) 99%, other <1%")
        self.assertEqual(len(got), 2)

    def test_trailing_parenthetical_is_not_a_group(self):
        got = common.parse_composition(
            "Muslim 90%, Christian 10% (majority Coptic Orthodox, other Christians "
            "include Armenian Apostolic, Catholic, Maronite, and Anglican) (2015 est.)")
        self.assertEqual([row["group"] for row in got], ["Muslim", "Christian"])

    def test_inequality_is_kept_as_a_bound(self):
        got = common.parse_composition("Muslim 99%, other <1%")
        self.assertEqual(got[1]["bound"], "<")
        self.assertEqual(got[1]["pct"], 1.0)

    def test_no_percentages_returns_none(self):
        self.assertIsNone(common.parse_composition(
            "Evangelical Lutheran, traditional Inuit spiritual beliefs"))

    def test_empty_input(self):
        self.assertIsNone(common.parse_composition(None))
        self.assertIsNone(common.parse_composition(""))

    def test_trailing_note_is_dropped(self):
        got = common.parse_composition(
            "German 85.4%, Turkish 1.8% note: data represent population by nationality")
        self.assertEqual([row["group"] for row in got], ["German", "Turkish"])

    def test_two_compositions_in_one_field(self):
        # The Factbook separates independent surveys with <br><br>. Reading them
        # as one list put Uruguay at 158.2% with Roman Catholic counted twice.
        # The dated block is the current estimate and the one that should win.
        got = common.parse_composition(
            "Roman Catholic 36.5%, Protestant 5%, other 1%, none 47.3%"
            "<br><br>Roman Catholic 42%, Protestant 15%, other 6%, "
            "agnostic 3%, atheist 10%, unspecified 24% (2023 est.)")
        self.assertEqual(len(got), 6)
        self.assertAlmostEqual(sum(r["pct"] for r in got), 100.0)
        self.assertEqual(got[0], {"group": "Roman Catholic", "pct": 42.0})

    def test_trailing_prose_blocks_are_not_mistaken_for_data(self):
        # The World entry ends with three note blocks. Taking the last block
        # would return a sentence about how many languages exist.
        got = common.parse_composition(
            "<strong>most-spoken language: </strong>English 18.8%, "
            "Mandarin Chinese 13.8% (2023 est.)"
            "<br><br><strong>note 1:</strong> the six UN languages are widely used"
            "<br><br><strong>note 2:</strong> there are 7,168 living languages")
        self.assertEqual([r["group"] for r in got], ["English", "Mandarin Chinese"])


class SplitTopLevel(unittest.TestCase):
    def test_respects_nesting(self):
        self.assertEqual(
            common._split_top_level("a, b (c, d), e"),
            ["a", " b (c, d)", " e"])

    def test_unbalanced_closing_paren_does_not_go_negative(self):
        self.assertEqual(common._split_top_level("a), b"), ["a)", " b"])


class Numbers(unittest.TestCase):
    def test_parse_number_strips_separators(self):
        self.assertEqual(common.parse_number("84,012,284 (2025 est.)"), 84012284)
        self.assertEqual(common.parse_number("46.9 years"), 46.9)
        self.assertIsNone(common.parse_number("no data"))

    def test_parse_year_takes_the_last_year(self):
        self.assertEqual(common.parse_year("1.05 male(s)/female (2025 est.)"), 2025)
        # "2020-25" is a period, not two vintages: the two-digit tail is not a
        # year, so the start of the range is the right answer.
        self.assertEqual(common.parse_year("(2020-25 est.)"), 2020)
        self.assertIsNone(common.parse_year("no vintage here"))


class Gaps(unittest.TestCase):
    def test_gap_requires_a_known_status(self):
        with self.assertRaises(ValueError):
            common.gap("dunno")

    def test_is_gap(self):
        self.assertTrue(common.is_gap(None))
        self.assertTrue(common.is_gap(common.gap(common.NOT_COLLECTED, "because")))
        self.assertFalse(common.is_gap(common.measure(5)))
        self.assertFalse(common.is_gap([{"group": "a", "pct": 1}]))

    def test_measure_carries_provenance(self):
        got = common.measure(1084, unit="females_per_1000_males", year=2011, source="X")
        self.assertEqual(got, {"value": 1084, "unit": "females_per_1000_males",
                               "year": 2011, "source": "X"})

    def test_measure_of_none_is_none(self):
        self.assertIsNone(common.measure(None, year=2011))


if __name__ == "__main__":
    unittest.main()
