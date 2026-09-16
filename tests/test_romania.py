"""Romania's census tables, and the shape of them that nearly went out wrong."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_census import romania as ro  # noqa: E402


def block(county: str, total: str, ortho: str, catholic: str) -> list[list[str]]:
    """One county's four rows in the religion table's layout."""
    return [
        [county] + [""] * 23,
        ["Ambele sexe", total, ortho, catholic] + ["0"] * 20,
        ["Masculin", "1", "1", "0"] + ["0"] * 20,
        ["Feminin", "1", "1", "0"] + ["0"] * 20,
    ]


class TheRepeatedTable(unittest.TestCase):
    """The religion table prints its county list three times -- total, urban,
    rural -- and taking the last pass published the rural population as the
    county. Harghita came to 178,447 people against a census county of
    310,867, and nothing about the output looked wrong: it summed to 100%,
    named the right confessions, and sat in a believable range."""

    def rows(self) -> list[list[str]]:
        head = [["12. POPULATIA PE SEXE"] + [""] * 23,
                ["JUDETUL SEXUL", "POPULATIA"] + [""] * 22,
                ["", ""] + ["Ortodoxa", "Romano- catolica"] + [""] * 21,
                ["A", "1.0"] + [""] * 23]
        return (head
                + block("ALBA", "300", "200", "100")     # total
                + block("ALBA", "180", "120", "60")      # urban
                + block("ALBA", "120", "80", "40"))      # rural

    def test_the_first_block_is_the_one_read(self):
        out, printed = ro.read_religion(self.rows())
        self.assertEqual(printed["ALBA"], 300.0)
        self.assertEqual(out["ALBA"]["Orthodox Christianity"], 200.0)

    def test_a_later_block_never_replaces_the_total(self):
        out, _ = ro.read_religion(self.rows())
        self.assertNotEqual(out["ALBA"]["Orthodox Christianity"], 80.0,
                            "the rural pass was published as the county")

    def test_the_total_check_catches_a_wrong_block(self):
        # What the guard is for: a rural-only composition still sums to 100%
        # and still names the right groups. Only the head count disagrees.
        with self.assertRaises(SystemExit) as caught:
            ro.check_totals("religion", {"ALBA": {"Orthodox Christianity": 80.0}},
                            {"ALBA": 300.0})
        self.assertIn("wrong block", str(caught.exception))

    def test_a_composition_that_does_add_up_passes(self):
        ro.check_totals("religion", {"ALBA": {"Orthodox Christianity": 200.0,
                                              "Roman Catholic": 100.0}},
                        {"ALBA": 300.0})


class TheCensusOwnMarks(unittest.TestCase):
    def test_a_dash_is_a_stated_zero(self):
        self.assertEqual(ro.count("-"), 0.0)

    def test_an_asterisk_is_suppressed_and_not_a_zero(self):
        # Reading a suppressed count as zero would claim nobody there
        # answered, which is a different thing from the office withholding
        # a handful of people.
        self.assertIsNone(ro.count("*"))

    def test_a_row_of_dashes_is_not_a_composition(self):
        rows = [["MUNICIPIUL BUCURESTI"] + [""] * 23,
                ["Ambele sexe"] + ["-"] * 23]
        out, printed = ro.read_religion(rows)
        self.assertEqual(out, {})
        self.assertEqual(printed, {})


class TheFootnoteMarkers(unittest.TestCase):
    """Ilfov was carved back out of Bucharest in 1997, so the ethnicity table
    hangs a superscript four off both names and the religion table does not.
    One read 42 counties and the other 40 until the marker came off."""

    def test_a_marker_comes_off_the_name(self):
        self.assertEqual(ro.clean("ILFOV ⁴"), "ILFOV")
        self.assertEqual(ro.clean("MUNICIPIUL BUCURESTI ⁴"), "MUNICIPIUL BUCURESTI")

    def test_both_spellings_reach_the_same_county(self):
        self.assertIn(ro.clean("ILFOV ⁴"), ro.SHAPE_NAMES)
        self.assertIn(ro.clean("MUNICIPIUL BUCURESTI ⁴"), ro.SHAPE_NAMES)

    def test_every_county_is_named(self):
        # Forty-one counties and the capital.
        self.assertEqual(len(ro.SHAPE_NAMES), 42)


class TheGroupsResolve(unittest.TestCase):
    def test_every_label_this_adapter_writes_reaches_the_tree(self):
        import group_tree as gt
        for field, columns in (("ethnicity", ro.ETHNIC_COLUMNS),
                               ("religion", ro.RELIGION_COLUMNS)):
            for label in set(columns.values()):
                with self.subTest(field=field, label=label):
                    self.assertTrue(
                        gt.hue(field, label) or gt.parent_of(field, label)
                        or gt.tier(field, label) > 1,
                        f"{label!r} would lead a unit with no colour")


if __name__ == "__main__":
    unittest.main()
