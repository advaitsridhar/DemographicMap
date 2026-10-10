"""India: two union territories the 2011 census counted apart, drawn as one.

Dadra and Nagar Haveli and Daman and Diu were merged in 2020 and the boundary
file draws one first-level shape for them. The state records must be one
record summed from both, never one territory's row on the whole shape.
"""

import unittest

from scripts.fetch_census import india_census


def row(code, state, district, population, hindus, muslims):
    males = population // 2
    rest = population - hindus - muslims
    return {"District code": code, "State name": state, "District name": district,
            "Population": str(population), "Male": str(males),
            "Female": str(population - males), "Hindus": str(hindus),
            "Muslims": str(muslims), "Christians": str(rest), "Sikhs": "0",
            "Buddhists": "0", "Jains": "0", "Others_Religions": "0",
            "Religion_Not_Stated": "0", "SC": "0", "ST": "0"}


ROWS = [
    row("496", "DADRA AND NAGAR HAVELI", "Dadra and Nagar Haveli", 343709, 322857, 12922),
    row("495", "DAMAN AND DIU", "Daman", 191173, 170000, 18000),
    row("494", "DAMAN AND DIU", "Diu", 52074, 47000, 4000),
]


class TheMergedTerritory(unittest.TestCase):
    def setUp(self):
        self.records = {r["name"]: r for r in india_census.states(ROWS)}

    def test_one_record_for_the_merged_shape(self):
        self.assertIn("Dadra and Nagar Haveli and Daman and Diu", self.records)
        self.assertNotIn("Dadra and Nagar Haveli", self.records)
        self.assertNotIn("Daman and Diu", self.records)

    def test_the_count_is_both_territories(self):
        got = self.records["Dadra and Nagar Haveli and Daman and Diu"]
        self.assertEqual(586_956, got["population"]["value"])
        self.assertEqual(586_956, sum(r["count"] for r in got["religion"]))

    def test_the_note_names_both_and_the_year(self):
        note = self.records["Dadra and Nagar Haveli and Daman and Diu"]["population_note"]
        self.assertIn("Dadra and Nagar Haveli (343,709)", note)
        self.assertIn("Daman and Diu (243,247)", note)
        self.assertIn("2020", note)


if __name__ == "__main__":
    unittest.main()
