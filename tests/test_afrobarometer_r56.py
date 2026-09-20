"""Rounds 5 and 6 are read for two countries, and every rule that narrows them
to two is a rule that could silently stop working.

The round is chosen per field rather than per country, the choice is measured
from the extract rather than declared, and three things are refused: Egypt's
one-valued language variable, Egypt's never-asked ethnicity and Algeria
entirely. Each of those is a decision this file holds to.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import afrobarometer_r56 as ab  # noqa: E402


def row(round_, country, region, **fields):
    base = {"round": round_, "country": country, "region": region,
            "religion": "", "ethnicity": "", "language": "",
            "weight": "1.0", "year": "2014"}
    base.update(fields)
    return base


class ChoosingTheRound(unittest.TestCase):
    """The newest round that *asks*, which is not the newest round."""

    def test_a_field_the_newer_round_drops_falls_back_to_the_older(self):
        rows = ([row("R6", "Burundi", "Gitega", ethnicity="Not asked in country")] * 4
                + [row("R5", "Burundi", "Gitega", ethnicity="Hutu")] * 3
                + [row("R5", "Burundi", "Gitega", ethnicity="Tutsi")])
        self.assertEqual(ab.choose(rows)[("Burundi", "ethnicity")], "R5")

    def test_the_newer_round_wins_when_both_ask(self):
        rows = ([row("R6", "Burundi", "Gitega", religion="Roman Catholic")] * 2
                + [row("R6", "Burundi", "Gitega", religion="Muslim only")]
                + [row("R5", "Burundi", "Gitega", religion="Roman Catholic")] * 2
                + [row("R5", "Burundi", "Gitega", religion="Muslim only")])
        self.assertEqual(ab.choose(rows)[("Burundi", "religion")], "R6")

    def test_one_distinct_answer_is_not_a_measurement(self):
        """Egypt's language: 2,388 respondents, one value, in both rounds.

        A variable the field team filled with a constant looks exactly like a
        composition until it is counted, and publishing it would paint a
        country uniform on a survey's authority.
        """
        rows = ([row("R6", "Egypt", "Cairo", language="Egyptian Arabic")] * 40
                + [row("R5", "Egypt", "Cairo", language="Arabic")] * 40)
        self.assertIsNone(ab.choose(rows)[("Egypt", "language")])

    def test_a_field_no_round_asks_is_chosen_from_neither(self):
        rows = ([row("R6", "Egypt", "Cairo", religion="NOT ASKED IN THIS COUNTRY")] * 5
                + [row("R5", "Egypt", "Cairo", ethnicity="")] * 5)
        self.assertIsNone(ab.choose(rows)[("Egypt", "ethnicity")])


class ReadingAnAnswer(unittest.TestCase):

    def test_not_asked_is_not_an_answer(self):
        for text in ("Not asked in country", "NOT ASKED IN THIS COUNTRY"):
            self.assertIsNone(ab.answer(text))

    def test_a_declined_answer_is_not_a_zero(self):
        for text in ("Refused", "Don't know", "Missing", ""):
            self.assertIsNone(ab.answer(text))

    def test_naming_no_ethnic_group_is_an_answer(self):
        """Both releases' punctuation of the same answer must be recognised."""
        for text in ('National identity only, or "doesn\'t think of self in '
                     'those terms"',
                     "National identity only, or 'doesnt think of self in "
                     "those terms'"):
            self.assertEqual(ab.answer(text), "No ethnic group")

    def test_the_codebooks_only_suffix_is_dropped(self):
        self.assertEqual(ab.answer("Muslim only"), "Muslim")
        self.assertEqual(ab.answer("Christian only"), "Christian")


class TheRegionTable(unittest.TestCase):

    def test_the_two_bujumburas_do_not_collide(self):
        """The city and the province around it are different shapes.

        The round calls the rural province "Bujumbura" and the city
        "Bujumbura Marie" -- its own misspelling of Mairie. Matching either on
        the bare name would put the capital's figures on the countryside, and
        nothing on the map would look wrong.
        """
        self.assertEqual(ab.REGIONS[("BDI", "Bujumbura")], "Bujumbura Rural")
        self.assertEqual(ab.REGIONS[("BDI", "Bujumbura Marie")],
                         "Bujumbura Mairie")
        self.assertNotEqual(ab.REGIONS[("BDI", "Bujumbura")],
                            ab.REGIONS[("BDI", "Bujumbura Marie")])

    def test_the_red_sea_governorates_two_names_are_one_shape(self):
        """Round 5 codes it in Arabic and in English, 20 interviews each."""
        self.assertEqual(ab.REGIONS[("EGY", "Al Bahr al Ahmar")],
                         ab.REGIONS[("EGY", "Red Sea")])

    def test_algeria_is_refused(self):
        self.assertIn("DZA", ab.REFUSED)
        self.assertFalse([k for k in ab.REGIONS if k[0] == "DZA"])

    def test_rumonge_carries_a_reason_and_not_a_figure(self):
        why = ab.UNSAMPLED[("BDI", "Rumonge")]
        self.assertIn("26 March 2015", why)
        self.assertNotIn(("BDI", "Rumonge"), ab.REGIONS.values())


if __name__ == "__main__":
    unittest.main()
