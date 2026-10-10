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


# 2015 tables 6 and 7, for one municipality (Ermera) with two posts.
def six_row(name, g):
    """g: (0-14, 15-64, 65+, 17-60, 60+) for males; females the same."""
    return [name] + [2 * v for v in g] + list(g) + list(g)


def seven_row(name, g):
    """g: (3-5, 6-11, 12-14, 15-17, 18-21, 22-24, 25-29) for males; females the same."""
    return [name] + [2 * v for v in g] + list(g) + list(g)


YOUNG = ((50, 40, 10, 35, 15), (8, 16, 8, 8, 10, 6, 10))   # middle person under 30
OLD = ((10, 70, 20, 60, 25), (2, 4, 2, 2, 3, 2, 4))         # middle person 30-64


def tables_2015(old=OLD, extra=0):
    labels6 = ["0 - 14", "15 - 64", "65+", "17-60", "60+"] * 3
    labels7 = ["3 - 5", "6 - 11", "12-14", "15 - 17", "18 - 21", "22-24", "25-29"] * 3
    add = lambda a, b: tuple(x + y for x, y in zip(a, b))  # noqa: E731
    mun6, mun7 = add(YOUNG[0], old[0]), add(YOUNG[1], old[1])
    grid6 = [["Table 6 Child..."], [""], ["Municipality", "Population/Age"],
             ["", "Total", "", "", "", "", "Male"], [""] + labels6,
             [float(i) for i in range(1, 17)], [""],
             six_row("TIMOR-LESTE", mun6), [""],
             six_row("ERMERA", add(mun6, (extra, 0, 0, 0, 0))),
             six_row("Hatulia", YOUNG[0]), six_row("Ermera", old[0]), [""],
             ["1Special Administrative Region"]]
    grid7 = [["Table 7 Popu..."], [""], ["Municipality", "Population/Age"],
             ["", "Total"], [""] + labels7, [float(i) for i in range(1, 23)], [""],
             seven_row("TIMOR-LESTE", mun7), [""], seven_row("ERMERA", mun7),
             seven_row("Hatulia", YOUNG[1]), seven_row("Ermera", old[1]), [""]]
    return grid6, grid7


class Posts2015Test(unittest.TestCase):
    def test_ten_groups_and_the_median(self):
        units = t.read_2015_groups(*tables_2015())
        hatulia = next(u for u in units.values() if u["name"] == "Hatulia")
        groups = hatulia["groups"]["T"]
        self.assertEqual(groups[0], (0, 2, 2 * (50 - 8 - 16 - 8)))       # 0-2 from table 6
        self.assertEqual(groups[-2], (30, 64, 2 * (40 - 8 - 10 - 6 - 10)))  # 30-64
        self.assertEqual(sum(n for *_, n in groups), 2 * 100)
        # 200 people: 36 + 16 + 32 + 16 = 100 by age 14, so the middle is the
        # 14/15 boundary.
        self.assertEqual(t.fine_median(groups), 15.0)
        medians = t.post_medians_2015(units, [{"id": "1", "name": "Hatolia"},
                                             {"id": "2", "name": "Ermera"}])
        self.assertEqual(medians["Hatolia"]["median_age"]["value"], 15.0)
        self.assertEqual(medians["Hatolia"]["median_age"]["year"], 2015)
        # Ermera's middle person is in 30-64: a stated gap, not a guess.
        self.assertEqual(medians["Ermera"]["median_age"]["status"], "not_available")

    def test_parts_must_make_their_municipality(self):
        with self.assertRaises(SystemExit):
            t.read_2015_groups(*tables_2015(extra=1))

    def test_school_ages_beyond_the_broad_group_refuse(self):
        bad = ((10, 70, 20, 60, 25), (20, 4, 2, 2, 3, 2, 4))      # 3-14 over 0-14
        with self.assertRaises(SystemExit):
            t.read_2015_groups(*tables_2015(old=bad))

    def test_a_polygon_with_no_2015_post_refuses(self):
        units = t.read_2015_groups(*tables_2015())
        with self.assertRaises(SystemExit):
            t.post_medians_2015(units, [{"id": "1", "name": "Hatolia"},
                                        {"id": "2", "name": "Ermera"},
                                        {"id": "3", "name": "Railaco"}])

    def test_table_5_single_years_skip_the_column_numbers(self):
        grid = [["Table 5.1a Population by age and sex, Aileu"], [""],
                ["Age", "Total", "Sex"], ["", "", "Male", "Female"],
                [1.0, 2.0, 3.0, 4.0], [""], ["Total", 10.0, 5.0, 5.0],
                ["Under 1", 3.0, 1.0, 2.0], [1.0, 3.0, 2.0, 1.0], ["0 - 4", 6.0, 3.0, 3.0],
                ["85+", 4.0, 2.0, 2.0]]
        ages, total = t.read_2015_single(grid, "test")
        self.assertEqual(total, 10.0)
        self.assertEqual(dict(ages), {0: 3.0, 1: 3.0, 85: 4.0})

    def test_single_years_check_the_groups(self):
        units = t.read_2015_groups(*tables_2015())
        country = next(u for u in units.values() if u["kind"] == "country")
        ages = t.Counter()
        for lo, hi, n in country["groups"]["T"]:
            top = 85 if hi is None else hi
            for a in range(lo, top + 1):
                ages[a] += n / (top - lo + 1)
        singles = {"country": ages, "Ermera": ages}
        t.check_2015_groups(units, singles)          # the groups' own spread: agrees
        skew = t.Counter({0: sum(ages.values())})
        with self.assertRaises(SystemExit):
            t.check_2015_groups(units, {"country": skew, "Ermera": skew})


if __name__ == "__main__":
    unittest.main()
