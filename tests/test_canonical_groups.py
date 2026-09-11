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

    def test_denominations_keep_their_own_name_and_roll_up(self):
        # The US reports traditions where Australia reports "Christianity", and
        # the map has to answer both questions off these rows: which of these
        # people are Catholic, and how many are Christian at all.
        got = cg.canonicalise(rows(("Protestant", 30.0), ("Catholic", 15.0),
                                   ("Orthodox Christian", 2.0),
                                   ("Latter-day Saints", 1.0)), "religion")
        self.assertEqual(got, {"Protestantism": 30.0, "Catholicism": 15.0,
                               "Orthodoxy": 2.0, "Latter-day Saints": 1.0})
        self.assertEqual(cg.share_of(got, "religion", "Christianity"), 48.0)
        self.assertEqual(cg.share_of(got, "religion", "Catholicism"), 15.0)

    def test_a_family_label_beside_a_tradition_sums_rather_than_doubles(self):
        """"Christian" next to "Roman Catholic" is two disjoint answers.

        Afrobarometer offers "Christian only" to a respondent who names no
        denomination, so Tanzania's Mbeya carries Christian 39.4 beside Roman
        Catholic 29.1 and nine other churches. Both are answers one person
        gave once, and the region's Christian share is their sum.
        """
        got = cg.canonicalise(rows(("Christian", 39.4), ("Roman Catholic", 29.1),
                                   ("Lutheran", 2.7)), "religion")
        self.assertAlmostEqual(cg.share_of(got, "religion", "Christianity"), 71.2)

    def test_a_group_rolls_up_through_every_level(self):
        # A Mandarin speaker is a Sinitic speaker and a Sino-Tibetan one, and
        # asking for any of the three must work.
        got = cg.canonicalise(rows(("Mandarin", 12.0), ("Cantonese", 3.0)),
                              "language")
        self.assertEqual(cg.share_of(got, "language", "Mandarin"), 12.0)
        self.assertEqual(
            cg.share_of(got, "language", "Sinitic languages"), 15.0)
        self.assertEqual(
            cg.share_of(got, "language", "Sino-Tibetan languages"), 15.0)

    def test_unmapped_labels_keep_their_own_name(self):
        # Nothing is dropped for want of a mapping: an unlisted group stays
        # filterable under exactly the name its census used. "Kirat" is one
        # deliberately -- a living tradition with 924,204 adherents that only
        # Nepal's census counts, and that dropping into a residual would erase.
        got = cg.canonicalise(rows(("Espírita", 2.0), ("Kirat", 3.2)),
                              "religion")
        self.assertEqual(got["Kirat"], 3.2)
        self.assertEqual(got["Spiritism and Afro-Brazilian religions"], 2.0)

    def test_an_ambiguity_is_not_folded_into_a_certainty(self):
        # "Unaffiliated or not reported" mixes people who belong to nothing with
        # members of bodies that did not report. Counting it as "No religion"
        # would turn "we cannot tell" into a measurement.
        got = cg.canonicalise(rows(("Unaffiliated or not reported", 51.0)),
                              "religion")
        self.assertNotIn("No religion", got)

    def test_ethnicity_folds_only_spellings_and_the_same_people(self):
        # Ethnicity categories are made by states rather than found in the
        # world, so the table holds two kinds of entry and no others: one
        # people spelled two ways, and one population two sources name
        # differently.
        got = cg.canonicalise(rows(("Maori", 5.0), ("Māori", 4.0)), "ethnicity")
        self.assertEqual(got, {"Māori": 9.0})
        got = cg.canonicalise(
            rows(("Afro-Mexican or Afro-descendant", 2.0)), "ethnicity")
        self.assertEqual(got, {"Afro-descendant": 2.0})

    def test_ethnicity_categories_states_define_differently_stay_apart(self):
        # Brazil's cor ou raça, the UK's tick-boxes and China's 56
        # nationalities are not subdivisions of one another, and neither are
        # these. Folding them would invent a worldwide category no census
        # asked about.
        for a, b in (("White", "European"), ("Black", "African"),
                     ("Mestizo", "Mixed"), ("Indian", "East Indian")):
            got = cg.canonicalise(rows((a, 5.0), (b, 4.0)), "ethnicity")
            self.assertEqual(sorted(got), sorted({a, b}),
                             f"{a} and {b} must not be merged")

    def test_an_unmapped_ethnicity_still_groups_across_countries(self):
        # Nothing needs a table entry to be filterable worldwide: an unmapped
        # label keys on itself, so the "White" of 27 countries is already one
        # group.
        got = cg.canonicalise(rows(("White", 5.0), ("White", 4.0)), "ethnicity")
        self.assertEqual(got, {"White": 9.0})


class DoubleCounting(unittest.TestCase):
    def test_two_labels_for_one_group_in_one_record_are_reported(self):
        # Reaching one canonical name by its own name and by a second label
        # that folds into it means the source published a group twice, and
        # summing would double it.
        bad = cg.check_no_double_counting(
            rows(("Catholicism", 60.0), ("Roman Catholic", 25.0)), "religion")
        self.assertEqual(bad, ["Catholicism"])

    def test_the_same_label_twice_is_not_a_conflict(self):
        # The Factbook lists Bissa twice for Burkina Faso. Summing is right.
        self.assertEqual(
            cg.check_no_double_counting(rows(("Bissa", 5.4), ("Bissa", 1.5)),
                                        "ethnicity"), [])
        got = cg.canonicalise(rows(("Bissa", 5.4), ("Bissa", 1.5)), "ethnicity")
        self.assertAlmostEqual(got["Bissa"], 6.9)

    def test_two_offices_catch_alls_are_not_a_conflict(self):
        """A residual has no children, so it is never a parent.

        NISRA writes "Other Religions" where the ONS writes "Other religion",
        and the United Kingdom's rolled-up record carries one row from each.
        Adding two catch-alls is right -- there is no third figure they are
        both part of -- but the NISRA spelling lowercases to the canonical name
        exactly, which used to stop the build.
        """
        self.assertEqual(
            cg.check_no_double_counting(
                rows(("Other religion", 0.5), ("Other Religions", 0.1)),
                "religion"), [])
        got = cg.canonicalise(
            rows(("Other religion", 0.5), ("Other Religions", 0.1)), "religion")
        self.assertAlmostEqual(got["Other religions"], 0.6)

    def test_a_real_duplicate_is_still_caught_when_a_residual_is_present(self):
        # Two catch-alls in one record are fine; a group published twice in
        # the same record is not, and the residual must not mask it.
        bad = cg.check_no_double_counting(
            rows(("Catholicism", 60.0), ("Roman Catholic", 25.0),
                 ("Other religion", 0.5), ("Other Religions", 0.1)), "religion")
        self.assertEqual(bad, ["Catholicism"])


if __name__ == "__main__":
    unittest.main()


class CaseFolding(unittest.TestCase):
    def test_capitalisation_is_not_a_distinction(self):
        # The Factbook writes "no religion", a census writes "No religion".
        got = cg.canonicalise(rows(("no religion", 10.0), ("No religion", 5.0)),
                              "religion")
        self.assertEqual(got, {"No religion": 15.0})

    def test_a_duplicated_group_is_still_caught_across_cases(self):
        bad = cg.check_no_double_counting(
            rows(("catholicism", 60.0), ("Roman Catholic", 25.0)), "religion")
        self.assertEqual(bad, ["Catholicism"])

    def test_the_same_label_in_two_cases_is_not_a_conflict(self):
        self.assertEqual(
            cg.check_no_double_counting(rows(("Bissa", 5.4), ("bissa", 1.5)),
                                        "ethnicity"), [])
