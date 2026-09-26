"""Saint Vincent: districts summed into parishes, and 2023 divisions only where whole."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts.fetch_census import vincent_census as v  # noqa: E402

HEAD = ["AREA_NAME", "ADM1_NAME", "ADM_LEVEL", "PARISH", "BTOTL", "B0004", "B05PL",
        "MTOTL", "FTOTL"]


def age_rows(first_ed: int = 60) -> list[list]:
    return [HEAD, ["alias"] * len(HEAD),
            ["SVG", "", 0, "", 109_188, 0, 0, 0, 0],
            ["KINGSTOWN", "KINGSTOWN", 1, "", 100, 0, 0, 0, 0],
            ["LAYOU", "LAYOU", 1, "", 109_088, 0, 0, 0, 0],
            ["ED 1", "KINGSTOWN", 2, "Saint George", first_ed, 20, first_ed - 20, 30,
             first_ed - 30],
            ["ED 2", "KINGSTOWN", 2, "Saint Andrew", 40, 10, 30, 20, 20],
            ["ED 3", "LAYOU", 2, "Saint Andrew", 109_088, 9_088, 100_000, 54_544, 54_544]]


class Workbook(unittest.TestCase):
    def test_districts_sum_into_parishes_and_divisions_record_their_parishes(self):
        ages, spread = v.ages_by_parish(age_rows())
        self.assertEqual(ages["Saint Andrew"]["total"], 109_128)
        self.assertEqual(ages["Saint George"]["groups"], {(0, 4): 20, (5, None): 40})
        self.assertEqual(spread, {"kingstown": {"Saint George", "Saint Andrew"},
                                  "layou": {"Saint Andrew"}})

    def test_districts_short_of_their_division_stop_the_run(self):
        with self.assertRaises(SystemExit):
            v.ages_by_parish(age_rows(first_ed=61))


class Report(unittest.TestCase):
    LINES = ["Major Ethnic Grouping", "Census African Indigenous White/ East Mixed",
             "Division Descent People Caucasian Indian Stated", "/Indian"] + [
        f"{name} 1 1 1 1 1 1 1 1 8" if " " not in name else
        f"{name.split(' ', 1)[0]}\n{name.split(' ', 1)[1]} 1 1 1 1 1 1 1 1 8"
        for name in v.DIVISIONS]

    def lines(self, total: int) -> list[str]:
        out = "\n".join(self.LINES).splitlines()
        n = len(v.DIVISIONS)
        return out + [f"Total {n} {n} {n} {n} {n} {n} {n} {n} {total}"]

    def test_wrapped_division_names_are_read_whole(self):
        old = v.HOUSEHOLD_2023
        v.HOUSEHOLD_2023 = 8 * len(v.DIVISIONS)
        try:
            out = v.table_2_6(self.lines(8 * len(v.DIVISIONS)))
        finally:
            v.HOUSEHOLD_2023 = old
        self.assertEqual(set(out), set(v.DIVISIONS))
        self.assertEqual(out["Suburbs of Kingstown"]["_total"], 8)

    def test_a_wrong_total_stops_the_run(self):
        with self.assertRaises(SystemExit):
            v.table_2_6(self.lines(8 * len(v.DIVISIONS)))

    def test_a_split_division_keeps_its_parishes_on_2012(self):
        spread = {"kingstown": {"Saint George", "Saint Andrew"}, "layou": {"Saint Andrew"},
                  "calliaqua": {"Saint George"}, "georgetown": {"Charlotte"}}
        divisions = {"Kingstown": {"_total": 5}, "Layou": {"_total": 6},
                     "Calliaqua": {"_total": 7}, "Georgetown": {"_total": 8}}
        self.assertEqual(v.parishes_2023(spread, divisions), {"Charlotte": {"_total": 8}})


if __name__ == "__main__":
    unittest.main()
