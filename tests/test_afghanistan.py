"""Afghan district ethnicity: what the ministry's plans state, and no more."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import afghanistan as a  # noqa: E402


class TheProseThatStatesShares(unittest.TestCase):
    """Every string here came from a province article, not from invention."""

    def test_the_share_may_follow_the_name(self) -> None:
        self.assertEqual(
            a.shares("Pashtun 70%, Tajik 20%, Uzbek 10%"),
            [{"group": "Pashtun", "pct": 70.0}, {"group": "Tajik", "pct": 20.0},
             {"group": "Uzbek", "pct": 10.0}])

    def test_the_share_may_precede_it(self) -> None:
        got = a.shares("60% Uzbek, 20% Tajik, 10% Hazara, 10% Pashtun")
        self.assertEqual([p["group"] for p in got],
                         ["Uzbek", "Tajik", "Hazara", "Pashtun"])
        self.assertEqual(sum(p["pct"] for p in got), 100.0)

    def test_a_village_count_in_front_is_not_a_share(self) -> None:
        self.assertEqual(a.shares("51 villages. 100% Tajik."),
                         [{"group": "Tajik", "pct": 100.0}])

    def test_a_single_group_at_one_hundred_is_a_composition(self) -> None:
        self.assertTrue(a.usable(a.shares("100% Tajik"), "x"))


class TheProseThatDoesNot(unittest.TestCase):
    """A district that says "majority" is a gap, and must stay one.

    Turning majority and minority into numbers would invent the figures, and
    an invented composition is indistinguishable on the map from a measured
    one -- which is the whole reason this map prefers a visible hole.
    """

    def test_majority_and_minority_are_not_numbers(self) -> None:
        self.assertEqual(a.shares("Majority Turkmen, minority Tajik"), [])

    def test_predominantly_and_few_are_not_numbers(self) -> None:
        self.assertEqual(
            a.shares("Predominantly Pamiris (Ishkashimi), few Tajik"), [])

    def test_a_bare_group_name_is_not_a_composition(self) -> None:
        self.assertEqual(a.shares("Tajik"), [])

    def test_an_empty_cell_is_refused(self) -> None:
        self.assertFalse(a.usable(a.shares(""), "x"))


class WhatIsRefusedOnArithmetic(unittest.TestCase):
    def test_shares_that_overrun_are_dropped(self) -> None:
        # Over 100 means a group counted twice; the arithmetic then describes
        # nobody, so the district keeps its gap.
        self.assertFalse(
            a.usable([{"group": "Tajik", "pct": 80.0},
                      {"group": "Uzbek", "pct": 40.0}], "x"))

    def test_shares_that_fall_far_short_are_dropped(self) -> None:
        self.assertFalse(a.usable([{"group": "Tajik", "pct": 20.0}], "x"))

    def test_shares_that_fall_a_little_short_are_kept(self) -> None:
        # The plans list the groups they list; 90% of a district described is
        # a reading, not a fault.
        self.assertTrue(
            a.usable([{"group": "Pashtun", "pct": 70.0},
                      {"group": "Tajik", "pct": 20.0}], "x"))

    def test_a_group_named_twice_keeps_the_first_figure(self) -> None:
        got = a.shares("Tajik 60%, Uzbek 30%, 10% Tajik")
        self.assertEqual([p["group"] for p in got], ["Tajik", "Uzbek"])
        self.assertEqual(got[0]["pct"], 60.0)


class TheCellIsStrippedBeforeItIsRead(unittest.TestCase):
    def test_markup_alignment_and_references_come_out(self) -> None:
        self.assertEqual(
            a.clean("align=right| 145 villages. Majority [[Tajiks|Tajik]]."
                    "<ref name=x/>"),
            "145 villages. Majority Tajik.")

    def test_a_link_without_a_label_keeps_its_target(self) -> None:
        self.assertEqual(a.clean("[[Hazara]] 40%, [[Pashtun]] 60%"),
                         "Hazara 40%, Pashtun 60%")


class TheColumnIsFoundByShapeNotOneSpelling(unittest.TestCase):
    """Baghlan heads it "Notes"; Badakhshan runs two headings into one cell."""

    def test_notes(self) -> None:
        self.assertEqual(
            a.notes_column(["District", "Capital", "Population", "Notes"]), 3)

    def test_villages_and_ethnic_groups_run_together(self) -> None:
        self.assertEqual(
            a.notes_column(["District", "Population", "Villages Ethnic groups"]), 2)

    def test_a_table_with_no_such_column_is_passed_over(self) -> None:
        self.assertIsNone(a.notes_column(["District", "Capital", "Area"]))

    def test_the_district_column_is_found_by_name(self) -> None:
        self.assertEqual(a.name_column(["No.", "District", "Capital"]), 1)


class ThePolicyNoLongerForbidsIt(unittest.TestCase):
    def test_ethnicity_is_writable_and_the_other_two_are_not(self) -> None:
        from common import NOT_COLLECTED_POLICY               # noqa: PLC0415
        afg = NOT_COLLECTED_POLICY["AFG"]
        self.assertNotIn("ethnicity", afg,
                         "the owner's decision of 22 September 2026: where a "
                         "source exists it is read")
        self.assertIn("religion", afg, "no source was found for these two")
        self.assertIn("language", afg)


class AHeaderSplitByItsOwnCitation(unittest.TestCase):
    """Badghis heads a column "Area" and hangs a {{Cite web}} on it.

    The table parser splits cells on "|" and the template carries its own, so
    seven header cells were counted where every data row had six. The ethnic
    column's index came out one too high and all fifteen rows were skipped for
    being too short -- the province reported nothing rather than a refusal.
    """

    BADGHIS = ["District", "Capital", "Population",
               "Area {{Cite web|url=https://www.fao.org/|website=www.fao.org"
               "|accessdate=16 February 2024",
               "title=Food and Agriculture Organization}}",
               "Pop. density", "Ethnic categories"]

    def test_the_fragments_are_rejoined(self) -> None:
        self.assertEqual(len(a.repair_header(self.BADGHIS)), 6)

    def test_the_column_index_then_matches_the_data_rows(self) -> None:
        self.assertEqual(a.notes_column(a.repair_header(self.BADGHIS)), 5)
        self.assertEqual(a.notes_column(self.BADGHIS), 6,
                         "unrepaired, it points one past where the note is")

    def test_a_header_with_no_templates_is_unchanged(self) -> None:
        plain = ["District", "Capital", "Population", "Notes"]
        self.assertEqual(a.repair_header(plain), plain)

    def test_a_template_that_never_closes_does_not_swallow_the_rest(self) -> None:
        # Better one long cell than an exception or a silent drop.
        got = a.repair_header(["District", "Area {{Cite", "Notes"])
        self.assertEqual(got[0], "District")
        self.assertEqual(len(got), 2)
