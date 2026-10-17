"""South Sudan's 2008 census reader: age groups, counties and the Abyei Area."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import south_sudan_census as ss  # noqa: E402


def names():
    out = ["AREA_NAME", "ADM1_NAME", "ADM_LEVEL", "GEO_MATCH", "BTOTL", "MTOTL", "FTOTL"]
    for sex in "BMF":
        out += [f"{sex}{lo:02d}{lo + 4:02d}" for lo in range(0, 65, 5)]
        out += [f"{sex}65PL"]
        out += [f"{sex}{lo:02d}{lo + 4:02d}" for lo in range(65, 95, 5)] + [f"{sex}95PL"]
    return out


def row(cols, name, state, level, m_per, f_per):
    values = {"AREA_NAME": name, "ADM1_NAME": state, "ADM_LEVEL": level, "GEO_MATCH": name}
    for sex, per in (("M", m_per), ("F", f_per), ("B", m_per + f_per)):
        for lo in range(0, 95, 5):
            values[f"{sex}{lo:02d}{lo + 4:02d}"] = per
        values[f"{sex}95PL"] = per
        values[f"{sex}65PL"] = per * 7
    groups = 20
    values.update(BTOTL=(m_per + f_per) * groups, MTOTL=m_per * groups, FTOTL=f_per * groups)
    return [values.get(c) for c in cols]


class Partition(unittest.TestCase):
    def test_the_finest_run_leaves_the_coarse_sum_out(self):
        run = ss.partition(names(), "B")
        self.assertEqual(run[0][:2], (0, 4))
        self.assertEqual(run[-1][:2], (95, None))
        self.assertEqual(len(run), 20)

    def test_the_coarse_run_stops_at_65(self):
        run = ss.partition(names(), "B", finest=False)
        self.assertEqual(run[-1][:2], (65, None))
        self.assertEqual(len(run), 14)


class Building(unittest.TestCase):
    def table(self):
        cols = names()
        rows = [cols, cols,
                row(cols, "WARRAP", "WARRAP", 1, 3, 3),
                row(cols, "TWIC", "WARRAP", 2, 1, 2),
                row(cols, "ABYEI", "WARRAP", 2, 2, 1),
                row(cols, "LAKES", "LAKES", 1, 1, 1),
                row(cols, "LOPA", "LAKES", 2, 1, 1)]
        return ss.read(rows)

    def test_warrap_is_written_without_abyei_and_abyei_not_at_all(self):
        table = self.table()
        admin1 = [{"id": "W", "name": "Warrap"}, {"id": "L", "name": "Lakes"}]
        admin2 = [{"id": "T", "name": "Twic", "parent": "W"},
                  {"id": "F", "name": "Lafon", "parent": "L"}]
        records, report = ss.build(table, admin1, admin2)
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(set(by), {"W", "L", "T", "F"})
        self.assertEqual(by["W"]["sex_ratio"]["value"], 500)      # Twic's 1 man to 2 women
        self.assertIn("without Abyei County", by["W"]["sex_ratio_note"])
        self.assertTrue(any("Abyei" in line and "not written" in line for line in report))
        self.assertEqual(by["F"]["name"], "Lafon")


if __name__ == "__main__":
    unittest.main()
