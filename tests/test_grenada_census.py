"""Grenada: labels wrapped above and below their figures, and the age blocks."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import grenada_census as g  # noqa: E402

PARISH = (lambda label: g.parish_key(label) is not None)
RELIGION = (lambda label: g.fold(label) in {g.fold(k) for k in g.RELIGION})


class Labels(unittest.TestCase):
    def test_a_label_above_and_below_its_figures(self):
        lines = ["2021 2011", "PARISH", "MALE FEMALE TOTAL MALE FEMALE TOTAL", "REST OF",
                 "1 1 2 1 1 2", "ST.GEORGE", "TOWN OF", "1 1 2 1 1 2", "ST.GEORGE",
                 "CARRIACOU AND", "PETITE 1 1 2 1 1 2", "MARTINǪUE", "TOTAL", "3 3 6 3 3 6"]
        out = g.rows(lines, 6, PARISH)
        self.assertEqual([g.parish_key(label) for label, _ in out],
                         ["rest of st george", "town of st george", "carriacou", "total"])

    def test_religions_run_on_below_their_figures(self):
        lines = ["PARISH TOWN OF U& TOTAL", "ANGLICAN 1 1 2", "ROMAN", "1 1 2", "CATHOLIC",
                 "SALVATION 1 1 2", "ARMY", "SEVENTH DAY", "1 1 2", "ADVENTIST",
                 "NO", "1 1 2", "RELIGIOUS", "AFFILIATIO", "N", "OTHER 1 1 2", "(SPECIFY)"]
        out = [label for label, _ in g.rows(lines, 3, RELIGION)]
        self.assertEqual([g.fold(label) for label in out],
                         ["anglican", "romancatholic", "salvationarmy", "seventhdayadventist",
                          "noreligiousaffiliation", "otherspecify"])

    def test_an_unknown_label_stops_the_run(self):
        with self.assertRaises(SystemExit):
            g.rows(["ATLANTIS 1 1 2"], 3, RELIGION)


class Ages(unittest.TestCase):
    def block(self, total: str = "20 20 40") -> list[str]:
        lines = []
        for lo, hi in g.AGES:
            label = "80-89" if lo == 80 else (f"{lo}-{hi}" if hi else f"{lo}+")
            lines += ([f"CARRIACOU& {label} 1 1 2"] if lo == 45 else [label, "1 1 2"])
        return lines + ["TOTAL", total]

    def test_groups_are_read_by_place_and_make_the_total(self):
        out = g.age_blocks(self.block())
        self.assertEqual(out[0]["total"], (20, 20, 40))
        self.assertEqual(out[0]["groups"][16], (80, 84, 2))

    def test_a_block_short_of_its_total_stops_the_run(self):
        with self.assertRaises(SystemExit):
            g.age_blocks(self.block("20 21 41"))


if __name__ == "__main__":
    unittest.main()
