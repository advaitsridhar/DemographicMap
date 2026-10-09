"""The East Asian readers' shared arithmetic: shares, and pooling small groups."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import east_asia_common as ea  # noqa: E402


class Pooling(unittest.TestCase):
    def test_small_groups_join_the_residual_and_every_person_is_shown(self):
        counts = {"Japanese": 98_000, "Korean": 1_000, "Chinese": 900, "Thai": 40, "Nepalese": 30,
                  "Other nationalities": 30}
        pooled, moved, people = ea.pool_small(counts, "Other nationalities")
        self.assertEqual(sorted(moved), ["Nepalese", "Thai"])
        self.assertEqual(people, 70)
        self.assertEqual(pooled["Other nationalities"], 100)
        shares = ea.hundred(pooled)
        self.assertEqual(sum(r["count"] for r in shares), 100_000)
        self.assertAlmostEqual(sum(r["pct"] for r in shares), 100.0, places=6)
        self.assertEqual(ea.unshown(pooled), 0)

    def test_a_residual_too_small_to_show_is_counted_for_the_note(self):
        pooled, moved, people = ea.pool_small({"A": 99_990, "B": 10}, "Other")
        self.assertEqual(moved, ["B"])
        self.assertEqual(ea.unshown(pooled), 10)
        self.assertEqual([r["group"] for r in ea.hundred(pooled)], ["A"])

    def test_nothing_small_nothing_moved(self):
        pooled, moved, people = ea.pool_small({"A": 600, "B": 400}, "Other")
        self.assertEqual((moved, people), ([], 0))
        self.assertEqual(pooled, {"A": 600, "B": 400})


if __name__ == "__main__":
    unittest.main()
