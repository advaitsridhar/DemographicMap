"""Tests for the cross-country group table in scripts/canonical_groups.py.

A global filter stands or falls on this table: if "Muslim" and "Islam" are not
known to be one answer, a world map of Islam omits whichever spelling loses.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import canonical_groups as cg  # noqa: E402


def rows(*pairs):
    return [{"group": g, "pct": p} for g, p in pairs]


class Synonyms(unittest.TestCase):
    def test_the_same_religion_under_two_names_is_one_group(self):
        got = cg.canonicalise(rows(("Muslim", 10.0)), "religion")
        self.assertEqual(got, {"Islam": 10.0})
        self.assertEqual(cg.canonicalise(rows(("Islam", 10.0)), "religion"), got)

    def test_denominations_roll_up_into_their_religion(self):
        # The US reports traditions where Australia reports "Christianity".
        got = cg.canonicalise(rows(("Protestant", 30.0), ("Catholic", 15.0),
                                   ("Orthodox Christian", 2.0),
                                   ("Latter-day Saints", 1.0)), "religion")
        self.assertEqual(got, {"Christianity": 48.0})

    def test_unmapped_labels_keep_their_own_name(self):
        # Nothing is dropped for want of a mapping: an unlisted group stays
        # filterable under exactly the name its census used.
        got = cg.canonicalise(rows(("Espírita", 2.0), ("Zoroastrian", 0.1)),
                              "religion")
        self.assertEqual(got["Zoroastrian"], 0.1)
        self.assertEqual(got["Spiritism and Afro-Brazilian religions"], 2.0)

    def test_an_ambiguity_is_not_folded_into_a_certainty(self):
        # "Unaffiliated or not reported" mixes people who belong to nothing with
        # members of bodies that did not report. Counting it as "No religion"
        # would turn "we cannot tell" into a measurement.
        got = cg.canonicalise(rows(("Unaffiliated or not reported", 51.0)),
                              "religion")
        self.assertNotIn("No religion", got)

    def test_ethnicity_is_never_merged_across_countries(self):
        # Brazil's cor ou raça, the UK's tick-boxes and China's 56 nationalities
        # are not subdivisions of one another.
        self.assertEqual(cg.TABLES["ethnicity"], {})
        got = cg.canonicalise(rows(("White", 5.0), ("Branca", 4.0)), "ethnicity")
        self.assertEqual(got, {"White": 5.0, "Branca": 4.0})


class DoubleCounting(unittest.TestCase):
    def test_parent_beside_its_own_child_is_reported(self):
        # If a source ever published both levels, rolling up would double it.
        bad = cg.check_no_double_counting(
            rows(("Christianity", 60.0), ("Catholic", 25.0)), "religion")
        self.assertEqual(bad, ["Christianity"])

    def test_the_same_label_twice_is_not_a_conflict(self):
        # The Factbook lists Bissa twice for Burkina Faso. Summing is right.
        self.assertEqual(
            cg.check_no_double_counting(rows(("Bissa", 5.4), ("Bissa", 1.5)),
                                        "ethnicity"), [])
        got = cg.canonicalise(rows(("Bissa", 5.4), ("Bissa", 1.5)), "ethnicity")
        self.assertAlmostEqual(got["Bissa"], 6.9)


if __name__ == "__main__":
    unittest.main()


class CaseFolding(unittest.TestCase):
    def test_capitalisation_is_not_a_distinction(self):
        # The Factbook writes "no religion", a census writes "No religion".
        got = cg.canonicalise(rows(("no religion", 10.0), ("No religion", 5.0)),
                              "religion")
        self.assertEqual(got, {"No religion": 15.0})

    def test_a_parent_beside_its_child_is_still_caught_across_cases(self):
        bad = cg.check_no_double_counting(
            rows(("christianity", 60.0), ("Catholic", 25.0)), "religion")
        self.assertEqual(bad, ["Christianity"])

    def test_the_same_label_in_two_cases_is_not_a_conflict(self):
        self.assertEqual(
            cg.check_no_double_counting(rows(("Bissa", 5.4), ("bissa", 1.5)),
                                        "ethnicity"), [])
