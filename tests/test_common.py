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

    def test_a_ranged_share_is_kept_not_dropped(self):
        # These rows matched nothing before, so Greece lost its Orthodox
        # majority and the slivers that remained still read as a whole
        # composition.
        got = common.parse_composition(
            "Greek Orthodox 81-90%, Muslim 2%, other 3% (2015 est.)")
        self.assertEqual(got[0], {"group": "Greek Orthodox", "pct": 85.5,
                                  "range": [81.0, 90.0]})
        self.assertEqual(got[1]["group"], "Muslim")

    def test_a_sub_split_inside_an_aside_is_not_the_group_share(self):
        # Iraq: the parenthesised Shia/Sunni split must not be read as the
        # Muslim share. The top-level range is the figure.
        got = common.parse_composition(
            "Muslim (official) 95-98% (Shia 61-64%, Sunni 29-34%), Christian 1%")
        self.assertEqual(got[0]["group"], "Muslim")
        self.assertEqual(got[0]["pct"], 96.5)

    def test_no_share_outside_an_aside_listing_several_figures(self):
        # Saudi Arabia publishes no overall share: the only figures describe how
        # its Muslim citizens divide. Inventing one from them would be worse
        # than the gap.
        got = common.parse_composition(
            "Muslim (official; citizens are 85-90% Sunni and 10-12% Shia), other")
        self.assertIsNone(got)

    def test_a_lone_share_inside_an_aside_is_used(self):
        # Sudan states the group's own share there and nowhere else.
        got = common.parse_composition("Sudanese Arab (approximately 70%), Fur, Beja")
        self.assertEqual(got, [{"group": "Sudanese Arab", "pct": 70.0}])

    def test_a_qualifier_is_a_bound_not_part_of_the_name(self):
        # "Han Chinese more than 95%" is not a group called "Han Chinese more
        # than"; it is Han Chinese, bounded below.
        got = common.parse_composition("Han Chinese more than 95%, other 2.3%")
        self.assertEqual(got[0], {"group": "Han Chinese", "pct": 95.0, "bound": ">"})

    def test_a_range_written_with_two_signs(self):
        got = common.parse_composition("English (spoken by only 1%-2% of the population)")
        self.assertEqual(got[0]["group"], "English")
        self.assertEqual(got[0]["pct"], 1.5)


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


class RepairNames(unittest.TestCase):
    """UTF-8 bytes that a boundary file stored as latin-1.

    The round trip is self-checking, which is the whole reason it is safe to
    apply to every name: a string that really is latin-1 does not survive it.
    """

    def test_utf8_read_as_latin1_comes_back(self):
        self.assertEqual(common.repair("RegiÃ³n Metropolitana"),
                         "Región Metropolitana")
        self.assertEqual(common.repair("BRAGANÃ\x87A"), "BRAGANÇA")

    def test_maori_macrons_are_covered(self):
        # The first version guessed at the visible lead characters and missed
        # these: a macron encodes from 0xC4 and 0xC5, not the 0xC3 that most
        # Western European accents use.
        self.assertEqual(common.repair("KaipÄ\x81tiki"), "Kaipātiki")
        self.assertEqual(common.repair("Å\x8cpÅ\x8dtiki"), "Ōpōtiki")

    def test_a_name_that_really_is_latin1_is_left_alone(self):
        # "Cañete" encodes to bytes that are not valid UTF-8, so the decode
        # raises and the name is returned untouched.
        self.assertEqual(common.repair("Cañete"), "Cañete")

    def test_names_needing_no_repair_are_untouched(self):
        for name in ("Kathmandu", "Ōpōtiki District", "", "Wellington City"):
            self.assertEqual(common.repair(name), name)

    def test_repair_is_idempotent(self):
        once = common.repair("RegiÃ³n Metropolitana")
        self.assertEqual(common.repair(once), once)
