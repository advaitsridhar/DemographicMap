"""Timor-Leste: median age and sex ratio from the 2022 census's basic tables.

No network: tables 4.05 and 4.01 are built here in the workbook's layout.
"""

import unittest

from scripts.fetch_census import timor_age as t

MUNIS = ["Aileu", "Ainaro", "Atauro", "Baucau", "Bobonaro", "Covalima", "Dili", "Ermera",
         "Lautém", "Liquiçá", "Manatuto", "Manufahi", "Oecusse", "Viqueque"]


def table_405(per_year=10, top=5):
    """Ages 0..top-1 single, then an open top+, every cell ``per_year`` (M = F)."""
    units = ["Timor-Leste"] + MUNIS
    head = [""]
    for u in units:
        head += [u, "", ""]
    sexes = [""] + ["Total", "Male", "Female"] * len(units)
    rows = [["Table 4.05: Population..."], [""], head, sexes,
            [str(i) for i in range(1, len(sexes) + 1)]]
    n = len(MUNIS)

    def line(label, value, country_value):
        row = [label, country_value, country_value // 2, country_value // 2]
        for _ in MUNIS:
            row += [value, value // 2, value // 2]
        return row
    total = per_year * (top + 1)
    rows.append(line("Total", total, total * n))
    rows.append(line("0-4", per_year * 5, per_year * 5 * n))
    for age in range(top):
        rows.append(line(str(age), per_year, per_year * n))
    rows.append(line(f"{top}+", per_year, per_year * n))
    rows.append(line("Urban", 1, n))
    rows.append(line("0", 999, 999))
    return rows


def table_401():
    rows = [["Table 4.01"], ["Municipality, administrative post, suco", "", "", "Urban"],
            ["", "", "", "Total", "", "", "Urban"],
            ["", "", "", "Total", "Male", "Female", "Total", "Male", "Female"],
            ["1", "2", "3", "4", "5", "6"],
            ["Timor-Leste", "", "", 600, 310, 290],
            ["Ermera", "", "", 300, 160, 140],
            ["", "Hatulia A", "", 100, 60, 40],
            ["", "", "Some suco", 50, 30, 20],
            ["", "Hatulia B", "", 100, 50, 50],
            ["", "Ermera", "", 100, 50, 50],
            ["Lautém", "", "", 300, 150, 150],
            ["", "Lospalos", "", 200, 100, 100],
            ["", "Lore", "", 100, 50, 50]]
    return rows


class AgesTest(unittest.TestCase):
    def test_single_years_of_the_total_block(self):
        units = t.read_ages(table_405())
        self.assertEqual(units["aileu"]["top"], 5)
        self.assertEqual(sum(units["aileu"]["ages"]["T"].values()), 60)
        self.assertNotIn(999, units["aileu"]["ages"]["T"].values())

    def test_a_municipality_whose_years_miss_its_total_refuses(self):
        rows = table_405()
        rows[5][4] = 61                     # Aileu's total one too many
        with self.assertRaises(SystemExit):
            t.read_ages(rows)

    def test_a_dash_whose_row_shows_people_is_the_difference(self):
        rows = table_405()
        rows[8][11] = "-"                   # Atauro's men of age 1: total 10, women 5
        units = t.read_ages(rows)
        self.assertEqual(units["atauro"]["ages"]["M"][1], 5)
        self.assertEqual(sum(units["atauro"]["ages"]["M"].values()), 30)

    def test_two_dashes_in_a_short_row_refuse(self):
        rows = table_405()
        rows[8][11] = "-"
        rows[8][12] = "-"
        with self.assertRaises(SystemExit):
            t.read_ages(rows)

    def test_dili_takes_in_atauro(self):
        units = t.read_ages(table_405())
        recs = t.municipality_records(units, [{"id": "D", "name": "Dili"},
                                              {"id": "A", "name": "Aileu"}])
        by = {r["shape_id"]: r for r in recs}
        self.assertIn("Atauro", by["D"]["median_age_note"])
        self.assertEqual(by["A"]["sex_ratio"]["value"], 100.0)
        # six equal years 0..4 and 5+: the middle person ends the year 2.
        self.assertEqual(by["A"]["median_age"]["value"], 3.0)


class PostsTest(unittest.TestCase):
    def test_joined_polygons_and_sums(self):
        posts = t.read_posts(table_401())
        self.assertEqual(set(posts), {"hatuliaa", "hatuliab", "ermera", "lospalos", "lore"})
        recs = t.post_records(posts, [{"id": "1", "name": "Hatolia"},
                                      {"id": "2", "name": "Ermera"},
                                      {"id": "3", "name": "Lospalos"}])
        by = {r["shape_id"]: r for r in recs}
        self.assertEqual(by["1"]["sex_ratio"]["value"], round(100 * 110 / 90, 1))
        self.assertEqual(by["1"]["population"]["value"], 200)
        self.assertIsNone(by["2"]["population"].get("value"))
        self.assertEqual(by["3"]["population"]["value"], 300)
        self.assertEqual(by["2"]["median_age"]["status"], "not_available")

    def test_a_post_left_on_no_polygon_refuses(self):
        posts = t.read_posts(table_401())
        with self.assertRaises(SystemExit):
            t.post_records(posts, [{"id": "1", "name": "Hatolia"}])


if __name__ == "__main__":
    unittest.main()
