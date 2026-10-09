"""Bahrain's 2020 census by governorate, read from portal records built in memory."""

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import bahrain_census as bc  # noqa: E402

GROUP_NAMES = list(bc.LABELS)


def tables():
    groups, totals = [], []
    for g_i, gov in enumerate(bc.GOVERNORATES):
        for sex in bc.SEXES:
            own = 0
            others = 0
            for n_i, name in enumerate(GROUP_NAMES):
                people = 100 * (g_i + 1) + 10 * n_i + (5 if sex == "Male" else 0)
                groups.append({"governorate": gov, "nationality_groups": name, "sex": sex,
                               "population": people})
                if name == "Bahraini":
                    own += people
                else:
                    others += people
            totals.append({"governorate": gov, "nationality": "Bahraini", "sex": sex,
                           "population": own})
            totals.append({"governorate": gov, "nationality": "Non-Bahraini", "sex": sex,
                           "population": others})
    kingdom = sum(r["population"] for r in groups)
    ages = [{"age_groups": "0 - 4", "nationality": "Bahraini", "sex": "Male",
             "population": kingdom - 10},
            {"age_groups": "5 - 9", "nationality": "Bahraini", "sex": "Male", "population": 10}]
    return groups, totals, ages


ADMIN1 = [{"id": f"g{i}", "name": f"{g} Governorate", "parent": "BHR"}
          for i, g in enumerate(bc.GOVERNORATES)]


class TheReader(unittest.TestCase):
    def test_every_governorate_gets_population_sex_ratio_and_nationality(self):
        out = {r["shape_id"]: r for r in bc.build(*tables(), ADMIN1)}
        self.assertEqual(sorted(out), ["g0", "g1", "g2", "g3"])
        capital = out["g0"]
        men = sum(100 + 10 * i + 5 for i in range(len(GROUP_NAMES)))
        women = sum(100 + 10 * i for i in range(len(GROUP_NAMES)))
        self.assertEqual(capital["population"]["value"], men + women)
        self.assertEqual(capital["sex_ratio"]["value"], round(100 * men / women, 1))
        self.assertEqual(capital["ethnicity_basis"], "nationality")
        labels = {s["group"] for s in capital["ethnicity"]}
        self.assertEqual(labels, set(bc.LABELS.values()))

    def test_a_governorate_drawn_at_both_levels_is_written_at_both(self):
        admin2 = [{"id": "g1", "name": "Muharraq Governorate", "parent": "g1"}]
        rows = bc.build(*tables(), ADMIN1, admin2)
        twins = [r for r in rows if r["level"] == "admin2"]
        self.assertEqual([r["shape_id"] for r in twins], ["g1"])
        first = next(r for r in rows if r["level"] == "admin1" and r["shape_id"] == "g1")
        self.assertEqual(twins[0]["population"], first["population"])
        self.assertEqual(twins[0]["ethnicity"], first["ethnicity"])
        self.assertNotEqual(twins[0]["id"], first["id"])
        self.assertEqual(twins[0]["parent_name"], first["name"])

    def test_median_age_and_religion_say_why_they_are_not_published(self):
        capital = bc.build(*tables(), ADMIN1)[0]
        self.assertEqual(capital["median_age"]["status"], "not_available")
        self.assertIn("whole kingdom", capital["median_age"]["note"])
        self.assertIn("religion", capital["religion"]["note"])
        self.assertEqual(capital["language"]["status"], "not_available")
        self.assertIn("none is by language", capital["language"]["note"])

    def test_tabulations_that_disagree_stop_the_run(self):
        groups, totals, ages = tables()
        totals = copy.deepcopy(totals)
        totals[1]["population"] += 1
        with self.assertRaises(SystemExit):
            bc.build(groups, totals, ages, ADMIN1)

    def test_governorates_that_miss_the_kingdom_stop_the_run(self):
        groups, totals, ages = tables()
        ages[0]["population"] += 1
        with self.assertRaises(SystemExit):
            bc.build(groups, totals, ages, ADMIN1)

    def test_an_unknown_drawn_governorate_stops_the_run(self):
        admin1 = ADMIN1[:3] + [{"id": "x", "name": "Central Governorate", "parent": "BHR"}]
        with self.assertRaises(SystemExit):
            bc.build(*tables(), admin1)


if __name__ == "__main__":
    unittest.main()
