"""Why Bangladesh's sixty-four zilas carry no mother tongue, and what was read.

The gap itself is asserted elsewhere -- that every zila carries a stated reason
rather than a blank panel, and that the reason names the survey. What is
asserted here is the **evidence behind it**, because that is the part a later
edit can quietly delete without any test going red.

The question "no zila level language?" was put again and attacked rather than
restated, across five routes:

1. the Census 2022 admin-2 workbook -- **all forty-two sheets** listed by name
   and their headers read, not only the three the adapter opens;
2. the Census 2022 *National Report (Volume I)* -- all 520 pages swept, and all
   239 of its distinct table headings counted by the geography they name;
3. the 2011 **Zila Report** series -- Rangamati, the most linguistically
   various district in the country;
4. the 2011 **Community Report** series -- Rangpur;
5. **MICS 2019**, which is district-representative, plus its District Summary
   Findings Report.

None of them has a mother-tongue table. MICS is the sharpest of the five,
because it does not merely omit the question: it asks it (HC1B) with two
printed answers, BANGLA and OTHER LANGUAGE, and then tabulates it nowhere. The
2023 survey the adapter does read codes it the same way. That is a fact about
how Bangladesh asks, not about one report -- which is why the shape of the
answer, a named language against an unnamed rest, is the thing that keeps a
composition out of reach rather than the level it is published at.

Two limits are asserted too, because a sweep that overstates itself is worse
than one that found nothing. Sixty-three Zila Reports were not read, and the
2011 Socio-Economic and Demographic Report is a scan with no text layer, so
its zero hits are silence and not evidence.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import bangladesh as bd  # noqa: E402

SOURCE = (ROOT / "scripts" / "fetch_census" / "bangladesh.py").read_text()
# Prose wraps, and a claim that moves to the next line is the same claim. Every
# assertion about what the module *says* runs against this rather than against
# the file, so re-flowing a paragraph cannot turn a passing test red and, more
# to the point, cannot be what someone tries in order to make one green.
FLAT = " ".join(SOURCE.split())
BUILT = ROOT / "data" / "processed" / "bangladesh_district.json"


class WhatWasActuallyRead(unittest.TestCase):
    """The adapter records the sweep, not just its conclusion.

    A conclusion with no evidence under it is indistinguishable from a guess,
    and the next person to ask "no zila level language?" deserves the list of
    what was opened rather than an assurance that somebody once looked.
    """

    def test_the_whole_workbook_was_enumerated_not_only_the_sheets_read(self):
        # Three sheets are opened by name. A sheet nobody asks for is a sheet
        # nobody can report missing, so the claim rests on listing all of them.
        self.assertIn("forty-two sheets", FLAT)
        self.assertIn("all forty-two were listed by name", FLAT)

    def test_the_two_sheets_that_look_like_language_are_named_and_dismissed(self):
        # Both match on "Bangla" and neither is a tongue: they carry
        # Bangladeshi *National*, which is citizenship.
        self.assertIn("Population_District", FLAT)
        self.assertIn("citizenship, not a tongue", FLAT)

    def test_the_national_report_sweep_is_quantified(self):
        # "I looked and found nothing" is not checkable; a count is.
        self.assertIn("520 pages the phrase \"mother tongue\" occurs **zero** "
                      "times", FLAT)
        self.assertIn("239 distinct table headings", FLAT)
        self.assertIn("not one names a language", FLAT)

    def test_the_2011_district_volumes_were_opened(self):
        self.assertIn("2011 Zila Report for Rangamati", FLAT)
        self.assertIn("2011 Community Report for Rangpur", FLAT)

    def test_mics_asks_the_question_and_publishes_no_table(self):
        # The strongest single finding, and the easiest to lose in a tidy-up:
        # a district-representative survey that collects mother tongue in two
        # categories and tabulates it nowhere.
        self.assertIn("HC1B", FLAT)
        self.assertIn("OTHER LANGUAGE", FLAT)
        self.assertIn("District Summary Findings", FLAT)


class WhatTheSweepDoesNotShow(unittest.TestCase):
    """The limits, kept in writing next to the finding.

    Both of these are ways this conclusion could be wrong, and a reader who is
    not told them cannot weigh it. The scanned volume is the dangerous one: it
    returns zero for every term including ones certainly in it, and a zero
    from a page with no text layer is silence, not an answer.
    """

    def test_the_unread_zila_reports_are_admitted(self):
        self.assertIn("Sixty-three of the sixty-four 2011 Zila Reports were "
                      "not read", FLAT)

    def test_the_scanned_volume_is_marked_as_proving_nothing(self):
        self.assertIn("scan with no text layer", FLAT)
        self.assertIn("which proves nothing", FLAT)

    def test_the_legacy_host_is_recorded_as_unreachable(self):
        # Not a mystery to rediscover: the Bureau still links to it and it
        # times out, which is why those three came through a mirror.
        self.assertIn("203.112.218.65:8008", FLAT)
        self.assertIn("Internet Archive", FLAT)


class TheDivisionFiguresStillHold(unittest.TestCase):
    """The one place a mother tongue is published, checked as typed.

    These eight pairs are the only figures in this adapter transcribed from a
    report rather than parsed out of one, so they are the only ones a typo can
    reach. ``check_report`` re-checks them on every run; this checks them
    without a network.
    """

    def test_every_division_has_a_pair_that_reaches_a_hundred(self):
        self.assertEqual(len(bd.MOTHER_TONGUE), 8)
        for where, (bangla, others) in bd.MOTHER_TONGUE.items():
            self.assertAlmostEqual(bangla + others, 100.00, places=2, msg=where)
            self.assertGreaterEqual(others, 0.0, where)

    def test_chattogram_is_the_least_bangla_speaking_division(self):
        # The hill districts are in it, and it is the row a transcription error
        # would most likely flatten.
        least = min(bd.MOTHER_TONGUE, key=lambda w: bd.MOTHER_TONGUE[w][0])
        self.assertEqual(least, "Chattogram")
        self.assertEqual(bd.MOTHER_TONGUE["Chattogram"], (97.11, 2.89))

    def test_the_year_is_the_survey_and_not_the_census(self):
        self.assertEqual(bd.TONGUE_YEAR, 2023)
        self.assertNotEqual(bd.TONGUE_YEAR, bd.YEAR)


class NoZilaInventsOne(unittest.TestCase):
    """A gap, not a composition, and not a division's figure copied down.

    Copying Chattogram's 97.11/2.89 onto its eleven districts would be the
    quietest possible way to publish a number nobody measured -- it would look
    right, sum right, and be wrong in Rangamati by whatever the hill districts
    actually speak.
    """

    def setUp(self):
        if not BUILT.exists():  # pragma: no cover - built output may be absent
            self.skipTest("bangladesh_district.json has not been built")
        self.rows = json.loads(BUILT.read_text())

    def test_no_zila_carries_a_language_composition(self):
        zilas = [r for r in self.rows if r["level"] == "admin2"]
        self.assertEqual(len(zilas), 64)
        for row in zilas:
            self.assertIsInstance(row["language"], dict, row["name"])
            self.assertTrue(row["language"].get("note"), row["name"])
            self.assertNotIn("language_year", row, row["name"])

    def test_the_divisions_are_the_only_units_with_one(self):
        with_language = [r for r in self.rows
                         if isinstance(r["language"], list)]
        self.assertEqual({r["level"] for r in with_language}, {"admin1"})
        self.assertEqual(len(with_language), 8)


if __name__ == "__main__":
    unittest.main()
