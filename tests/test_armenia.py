import unittest

from scripts.fetch_census import armenia as a


def sheet(men_yerevan=3.0):
    head = ["Age", "Yerevan", "Geghar kunik", "RA"]
    rows = [["Age and Sex distribution", "", "", ""], ["", "Total Population", "", ""],
            ["", "", "", "persons"], head,
            [0.0, 2.0, 1.0, 3.0], ["1-4", 4.0, 2.0, 6.0], ["85+", 4.0, 1.0, 5.0],
            ["Total Population", 10.0, 4.0, 14.0],
            ["", "Male", "", ""], head,
            [0.0, 1.0, 1.0, 2.0], ["1-4", 2.0, 1.0, 3.0], ["85+", men_yerevan - 3.0 + 2.0, 0.0, 2.0],
            ["Total", 5.0, 2.0, 7.0],
            ["Female", "", "", ""], head,
            [0.0, 1.0, 0.0, 1.0], ["1-4", 2.0, 1.0, 3.0], ["85+", 2.0, 1.0, 3.0],
            ["Total", 5.0, 2.0, 7.0]]
    return rows


class Reading(unittest.TestCase):
    def test_blocks_columns_and_bands(self):
        got = a.read_sheet(sheet())
        self.assertEqual(set(got), {"Yerevan", "Gegharkunik", "RA"})
        self.assertEqual(got["Yerevan"]["total"]["groups"],
                         [(0, 0, 2.0), (1, 4, 4.0), (85, None, 4.0)])
        self.assertEqual(got["Gegharkunik"]["women"]["all"], 2.0)

    def test_checked_refuses_a_block_that_does_not_add_up(self):
        table = a.read_sheet(sheet(men_yerevan=4.0))
        with self.assertRaises(SystemExit):
            a.checked(table, "x")

    def test_sheet_date(self):
        self.assertEqual(a.sheet_date("01.01.2026").year, 2026)
        self.assertIsNone(a.sheet_date("Sheet1"))


class SecondLevel(unittest.TestCase):
    """The map's raions of before 1995 say why they are empty; Yerevan is the city."""

    ADMIN2 = [{"id": "Y2", "name": "Yerevan", "parent": "Y1"},
              {"id": "R1", "name": "Ararat", "parent": "A1"},
              {"id": "R2", "name": "Masis", "parent": "A1"}]
    CITY = {"population": {"value": 1100000, "year": 2026, "source": "s"},
            "population_note": "Armstat's permanent population."}

    def test_yerevan_takes_the_citys_row_and_the_raions_say_why(self):
        got = a.second_level(self.ADMIN2, "Y1", self.CITY, [])
        city = next(r for r in got if r["shape_id"] == "Y2")
        self.assertEqual(city["population"]["value"], 1100000)
        self.assertTrue(city["population_note"].endswith("the city's own row."))
        for r in got:
            if r["shape_id"] == "Y2":
                continue
            for field in a.FIELDS:
                self.assertEqual(r[field]["status"], "not_available")
                self.assertIn("before the 1995 reform", r[field]["note"])

    def test_a_missing_or_doubled_yerevan_stops_the_run(self):
        with self.assertRaises(SystemExit):
            a.second_level(self.ADMIN2[1:], "Y1", self.CITY, [])
        with self.assertRaises(SystemExit):
            a.second_level(self.ADMIN2 + [dict(self.ADMIN2[0], id="Y3")], "Y1", self.CITY, [])


if __name__ == "__main__":
    unittest.main()
