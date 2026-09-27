"""The Caribbean's stated gaps: every one carries its reason."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import caribbean_gaps as g  # noqa: E402


class Gaps(unittest.TestCase):
    def test_every_language_reason_is_written(self):
        for iso, note in g.LANGUAGE.items():
            self.assertTrue(note and len(note) > 80, iso)

    def test_a_gap_record_binds_by_shape_and_carries_its_notes(self):
        rec = g.gaps("KNA", "admin1", {"id": "x1", "name": "Saint Anne Sandy Point"},
                     {"religion": g.KITTS})
        self.assertEqual((rec["match_by"], rec["shape_id"]), ("shape_id", "x1"))
        self.assertEqual(rec["religion"], {"status": "not_available", "note": g.KITTS})
        self.assertEqual(rec["population"]["status"], "not_available")
        self.assertNotIn("note", rec["population"])

    def test_redonda_is_not_applicable(self):
        rec = g.gaps("ATG", "admin1", {"id": "r", "name": "Redonda"}, {"median_age": g.REDONDA},
                     status=g.NOT_APPLICABLE)
        self.assertEqual(rec["median_age"]["status"], "not_applicable")


if __name__ == "__main__":
    unittest.main()
