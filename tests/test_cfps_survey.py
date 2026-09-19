"""The five CFPS 2012 provinces, transcribed from a PDF nothing can parse."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.fetch_census import cfps_survey  # noqa: E402


class CfpsSurvey(unittest.TestCase):
    def test_every_column_is_a_whole_population(self):
        for name, _, shares, n in cfps_survey.TABLE:
            with self.subTest(province=name):
                self.assertAlmostEqual(sum(shares), 100.0, delta=cfps_survey.TOLERANCE)
                self.assertGreater(n, 2000)

    def test_shanghai_as_the_paper_prints_it(self):
        rows = {r["name"]: r for r in cfps_survey.build()}
        sh = rows["Shanghai Municipality"]["religion"]
        self.assertEqual(sh[0], {"group": "No religion", "pct": 86.7})
        self.assertEqual(sh[1], {"group": "Buddhism", "pct": 10.4})
        # A group printed at 0.0% is not a row: Shanghai's Islam.
        self.assertNotIn("Islam", {r["group"] for r in sh})
        self.assertEqual(rows["Shanghai Municipality"]["religion_year"], 2012)
        self.assertIn("2,362 respondents", rows["Shanghai Municipality"]["religion_note"])
        self.assertIn("not a census", rows["Shanghai Municipality"]["religion_note"])

    def test_only_the_five_self_representative_provinces(self):
        names = {r["name"] for r in cfps_survey.build()}
        self.assertEqual(names, {"Shanghai Municipality", "Liaoning Province",
                                 "Henan Province", "Gansu Province", "Guangdong"})

    def test_a_column_that_does_not_sum_is_refused(self):
        with self.assertRaises(SystemExit):
            cfps_survey.check("X", [50.0, 0, 0, 0, 0, 40.0, 0])
