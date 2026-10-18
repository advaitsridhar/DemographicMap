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

    def test_the_publisher_is_whole_before_the_first_comma(self):
        self.assertEqual(ss.SOURCE.split(",")[0],
                         "Southern Sudan Centre for Census Statistics and Evaluation (SSCCSE)")


ESTIMATES = [
    ["Admin1", "Admin1_Pcode", "Admin2", "Admin2_Alternate_Name", "Admin2_Pcode",
     "Population - 2025"],
    ["Abyei Administrative Area", "SS00", "Abyei Administrative Area", "", "SS0001", "145358"],
    ["Warrap", "SS08", "Twic", "", "SS0801", "300000.4"],
    ["Lakes", "SS04", "Lafon", "Lopa/Lafon", "SS0499", "120000.6"]]


class Estimates(unittest.TestCase):
    def test_the_abyei_row_is_never_read(self):
        got = ss.read_estimates(ESTIMATES)
        self.assertEqual(sorted(got), ["SS0499", "SS0801"])
        self.assertEqual(got["SS0801"]["population"], 300000)

    def test_counties_take_the_2025_estimate_by_p_code_or_name(self):
        table = Building().table()
        admin1 = [{"id": "W", "name": "Warrap"}, {"id": "L", "name": "Lakes"}]
        admin2 = [{"id": "T", "name": "Twic", "parent": "W", "codes": {"pcode": "SS0801"}},
                  {"id": "F", "name": "Lafon", "parent": "L", "codes": {"pcode": "SS0402"}}]
        records, report = ss.build(table, admin1, admin2, ss.read_estimates(ESTIMATES))
        by = {r["shape_id"]: r for r in records}
        self.assertEqual(by["T"]["population"], {"value": 300000, "year": 2025,
                                                 "source": ss.SOURCE_2025})
        self.assertEqual(by["F"]["population"]["value"], 120001)       # bound by name
        self.assertIn("for 2025; the 2008 census counted 40.", by["F"]["population_note"])
        self.assertNotIn("value", by["W"]["population"])     # the states are summed by the map
        self.assertEqual(ss.SOURCE_2025.split(",")[0], "OCHA")
        self.assertTrue(any("bound by name" in line for line in report))

    def test_a_county_without_an_estimate_stops_the_run(self):
        admin2 = [{"id": "X", "name": "Nowhere", "parent": "W", "codes": {"pcode": "SS0999"}}]
        with self.assertRaises(SystemExit):
            ss.bind_estimates(ss.read_estimates(ESTIMATES), admin2, [])

    def test_counties_that_do_not_make_their_state_stop_the_run(self):
        estimates = ss.read_estimates(ESTIMATES)
        self.assertEqual(ss.check_states(estimates, [["State", "Sum"], ["Warrap", 300000.4],
                                                     ["Abyei Administrative Area", 145358],
                                                     ["Grand Total", 1]]), 1)
        with self.assertRaises(SystemExit):
            ss.check_states(estimates, [["State", "Sum"], ["Warrap", 310000]])


if __name__ == "__main__":
    unittest.main()
