"""Sudan's 2008 census reader: the retabulated sexes, Table P01's ages, claimed ground."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import sudan_census as sc  # noqa: E402

RETAB = ["AREA_NAME", "ADM1_NAME", "ADM_LEVEL", "GEO_MATCH", "M", "F", "T"]
RETAB_ALIASES = ["Area", "State", "Level", "Code",
                 "Male Population, institutional and non-institutional population",
                 "Female Population, institutional and non-institutional population",
                 "Total Population, institutional and non-institutional population"]


def retab(extra_men=0):
    rows = [RETAB, RETAB_ALIASES,
            ["SUDAN", "", 0, "SD", 1300, 1200, 2500],
            ["RED SEA", "RED SEA", 1, "SD01", 700, 600, 1300],
            ["PORT SUDAN", "RED SEA", 2, "SD01001", 400 + extra_men, 300, 700],
            ["HALAIB", "RED SEA", 2, "SD01002", 300, 300, 600],
            ["SINNAR", "SINNAR", 1, "SD02", 600, 600, 1200],
            ["SINJA", "SINNAR", 2, "SD02001", 600, 600, 1200]]
    return rows


def p01(total, groups):
    names = ["AREA_NAME", "ADM_LEVEL", "BTOTL", "MTOTL", "FTOTL"]
    for sex in "BMF":
        names += [f"{sex}0004", f"{sex}0509", f"{sex}10PL"]
    row = ["SINNAR", 1, total, total // 2, total - total // 2]
    for sex, share in (("B", 1.0), ("M", 0.5), ("F", 0.5)):
        row += [int(g * share) for g in groups]
    return [names, names, row]


class Retabulation(unittest.TestCase):
    def test_a_person_of_rounding_is_allowed_and_more_is_not(self):
        table = sc.read_retab(retab())
        self.assertEqual(table["states"]["redsea"]["total"], 1300)
        rows = retab()
        rows[4][6] = 701                         # one person of rounding
        rows[3][6] = 1301
        rows[2][6] = 2501
        self.assertEqual(sc.read_retab(rows)["states"]["redsea"]["total"], 1301)
        with self.assertRaises(SystemExit):
            sc.read_retab(retab(extra_men=5))


class Ages(unittest.TestCase):
    def test_a_few_people_of_no_stated_age_are_left_out(self):
        ages = sc.read_ages(p01(1200, [500, 500, 150]))
        self.assertEqual(ages["sinnar"]["unstated"], 50)
        self.assertEqual(sc.grouped_median(ages["sinnar"]["groups"]), 5.8)

    def test_rounding_is_not_counted_as_unstated(self):
        ages = sc.read_ages(p01(1200, [600, 400, 199]))
        self.assertEqual(ages["sinnar"]["unstated"], 0)

    def test_too_many_without_an_age_stops_the_run(self):
        with self.assertRaises(SystemExit):
            sc.read_ages(p01(1200, [400, 400, 100]))


class Building(unittest.TestCase):
    def test_claimed_ground_is_never_written_and_unchanged_states_get_a_median(self):
        table = sc.read_retab(retab())
        ages = sc.read_ages(p01(1200, [500, 500, 200]))
        admin1 = [{"id": "S1", "name": "Red Sea"}, {"id": "S2", "name": "Sinnar"}]
        admin2 = [{"id": "L1", "name": "Port Sudan", "parent": "S1"},
                  {"id": "L2", "name": "Hala'ib", "parent": "S1"},
                  {"id": "L3", "name": "Sinja", "parent": "S2"}]
        records, report = sc.build(table, ages, admin1, admin2)
        by = {r["shape_id"]: r for r in records}
        self.assertNotIn("L2", by)
        self.assertEqual(by["L1"]["sex_ratio"]["value"], 1333)
        self.assertEqual(by["S2"]["median_age"]["value"], 6.0)
        self.assertIsNone((by["S1"].get("median_age") or {}).get("value"))
        # Red Sea without Halaib's 300 men and 300 women.
        self.assertEqual(by["S1"]["sex_ratio"]["value"], 1333)
        self.assertIn("leaves out the locality of Halaib (600 people)", by["S1"]["sex_ratio_note"])
        self.assertTrue(any("without the claimed" in line for line in report))

    def test_a_state_whose_localities_were_divided_since_gets_none(self):
        table = sc.read_retab(retab())
        ages = sc.read_ages(p01(1200, [500, 500, 200]))
        admin1 = [{"id": "S1", "name": "Red Sea"}, {"id": "S2", "name": "Sinnar"}]
        admin2 = [{"id": "L1", "name": "Port Sudan", "parent": "S1"},
                  {"id": "L3", "name": "Sinja", "parent": "S2"},
                  {"id": "L4", "name": "Sinja East", "parent": "S2"}]
        records, report = sc.build(table, ages, admin1, admin2)
        self.assertEqual({r["shape_id"] for r in records}, {"S1", "S2", "L1"})
        self.assertTrue(any("divided since" in line for line in report))

    def test_a_state_counted_far_apart_in_the_two_tables_gets_no_median(self):
        table = sc.read_retab(retab())
        ages = sc.read_ages(p01(1300, [520, 540, 240]))       # 1,300 against 1,200
        admin1 = [{"id": "S2", "name": "Sinnar"}]
        records, _ = sc.build(table, ages, admin1, [])
        self.assertIsNone((records[0].get("median_age") or {}).get("value"))


if __name__ == "__main__":
    unittest.main()
