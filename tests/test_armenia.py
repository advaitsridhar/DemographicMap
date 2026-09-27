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


if __name__ == "__main__":
    unittest.main()
