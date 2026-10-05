"""Maldives 2022: the Bureau's atoll indicator sheet, read, checked and bound.

The fixture is the sheet's layout with fewer columns: a title, the two header
rows, the Republic, Malé and Atolls rows, the all-localities block, the
inhabited-islands block and the resorts and industrial islands, every figure
adding up the way the real sheet's do. The units are the map's, cut down to
what binding needs. No workbook, no network.
"""

import unittest

from scripts.fetch_census import maldives_census as mv

CODES = list(mv.ATOLLS)
HEAD = [None, None, "Resident Population", None, None, "Resident Maldivians", None,
        None, "Resident Foreigners", None, None, "Median Age", None, None]
SUB = [None, None, "Both sexes", "Male", "Female", "Both sexes", "Male", "Female",
       "Both sexes", "Male", "Female", "Resident Population", "Resident Maldivian",
       "Resident Foreign"]


def line(label, males, females, f_males, f_females, median=None):
    """A sheet row from resident and foreign males and females."""
    return [None, label, males + females, males, females,
            males + females - f_males - f_females, males - f_males,
            females - f_females, f_males + f_females, f_males, f_females,
            median, median, median]


def atoll(i, inhabited=False):
    """Atoll i: its inhabited islands hold all but 50 foreign men and 5 women."""
    males, females, f_males, f_females = 1000 + 10 * i, 900 + 7 * i, 100 + i, 10 + i
    if inhabited:
        males, females, f_males, f_females = males - 50, females - 5, f_males - 50, f_females - 5
    return males, females, f_males, f_females


def sheet():
    label = {code: f"Atoll {code} ({code})" for code in CODES}
    every = [atoll(i) for i in range(20)]
    lived = [atoll(i, True) for i in range(20)]
    total = lambda rows: [sum(r[k] for r in rows) for k in range(4)]  # noqa: E731
    atolls = total(every)
    city = (5000, 4000, 1500, 200)
    rows = [["POPULATION- Atoll Level Indicator Sheet"], [], HEAD, SUB, [], []]
    rows.append(line("Republic", *[a + c for a, c in zip(atolls, city)], 31))
    rows.append(line("Male' (including Villimale and Hulhumale)", *city, 31))
    rows.append(line("Atolls", *atolls, 31))
    rows.append([])
    rows.append([None, "Administrative Islands & Non-administrative Islands"])
    rows += [line("    " + label[c], *every[i], 30 + (i % 4) * 0.5)
             for i, c in enumerate(CODES)]
    rows.append([])
    rows.append(line("Administrative Islands", *total(lived), 30))
    rows += [line("    " + label[c], *lived[i], 30) for i, c in enumerate(CODES)]
    rows.append([])
    rows.append(line("Non Administrative Islands", 1000, 100, 1000, 100, 30))
    rows.append(line("Resorts", 800, 80, 800, 80, 30))
    rows.append(line("Industrial Islands", 200, 20, 200, 20, 30))
    rows += [[None, "Non Administrative Islands"], [None, "Resorts"]]
    return rows


def unit(uid, name, parent="MDV", bbox=(72.9, 2.0, 73.1, 2.2)):
    return {"id": uid, "name": name, "site_name": name, "parent": parent,
            "bbox": list(bbox)}


def units():
    first = [unit("A1-" + c, mv.ATOLLS[c][0]) for c in ("HA", "K", "S", "R")]
    second = [unit("A2-" + c, mv.ATOLLS[c][1], parent=("A1-" + c if c in ("HA", "S") else "MDV"))
              for c in CODES if mv.ATOLLS[c][1] and c != "K"]
    second.append(unit("A2-K", "Male'", bbox=(73.447, 3.941, 73.717, 4.976)))
    second.append(unit("A2-sliver", "Male'", bbox=(73.5096, 4.1823, 73.5099, 4.1824)))
    return first, second


class Sheet(unittest.TestCase):
    def test_the_sheet_is_read_and_reconciles(self):
        got = mv.read(sheet())
        mv.check(got)
        self.assertEqual(set(got["all"]), set(CODES))
        self.assertEqual(got["all"]["HA"]["residents"], (1900, 1000, 900))
        self.assertEqual(got["totals"]["Male'"]["median"], 31.0)

    def test_a_row_whose_sexes_do_not_make_its_total_is_refused(self):
        rows = sheet()
        at = next(i for i, r in enumerate(rows) if len(r) > 1 and r[1] == "    Atoll N (N)")
        rows[at][3] += 1
        with self.assertRaises(SystemExit):
            mv.check(mv.read(rows))

    def test_an_atoll_moved_between_blocks_breaks_the_totals(self):
        rows = sheet()
        at = next(i for i, r in enumerate(rows) if len(r) > 1 and r[1] == "    Atoll N (N)")
        rows[at] = mv_line_plus(rows[at], 7)
        with self.assertRaises(SystemExit):
            mv.check(mv.read(rows))

    def test_a_median_no_census_would_print_is_refused(self):
        rows = sheet()
        at = next(i for i, r in enumerate(rows) if len(r) > 1 and r[1] == "    Atoll V (V)")
        rows[at][11] = 30.3
        with self.assertRaises(SystemExit):
            mv.check(mv.read(rows))


def mv_line_plus(row, n):
    """The same row with n more Maldivian men: its own sums still hold."""
    row = list(row)
    row[2] += n
    row[3] += n
    row[5] += n
    row[6] += n
    return row


class Binding(unittest.TestCase):
    def test_atolls_bind_by_code_and_male_takes_kaafu_and_the_city(self):
        got = mv.read(sheet())
        mv.check(got)
        first, second = units()
        main, nat = mv.build(got, first, second)
        by_id = {r["shape_id"]: r for r in main}
        self.assertEqual(by_id["A1-HA"]["population"]["value"], 1900)
        self.assertEqual(by_id["A1-HA"]["sex_ratio"]["unit"], "males_per_100_females")
        self.assertEqual(by_id["A1-HA"]["median_age"]["value"], 30.0)
        # Kaafu at the first level is the atoll alone.
        k = CODES.index("K")
        males, females, _fm, _ff = atoll(k)
        self.assertEqual(by_id["A1-K"]["population"]["value"], males + females)
        self.assertIn("not in this figure", by_id["A1-K"]["population_note"])
        # The Male' polygon is Kaafu and the city together, with no median.
        self.assertEqual(by_id["A2-K"]["population"]["value"], males + females + 9000)
        self.assertEqual(by_id["A2-K"]["median_age"]["status"], "not_available")
        self.assertEqual(by_id["A2-K"]["sex_ratio"]["value"],
                         round(100 * (males + 5000) / (females + 4000), 1))
        # The fragment gets its reason, and nothing else.
        self.assertEqual(by_id["A2-sliver"]["population"]["status"], "not_available")
        self.assertIn("count them twice", by_id["A2-sliver"]["population"]["note"])
        # Gnaviyani has no polygon and is placed nowhere.
        self.assertNotIn("MDV-ATOLL-Gn", {r["id"] for r in main})
        shares = {g["group"]: g["count"] for g in
                  next(r for r in nat if r["shape_id"] == "A1-HA")["ethnicity"]}
        self.assertEqual(shares, {"Maldivian": 1790, "Foreigner": 110})
        self.assertEqual(nat[0]["ethnicity_basis"], "nationality")

    def test_a_second_male_that_is_not_a_fragment_needs_a_decision(self):
        got = mv.read(sheet())
        first, second = units()
        second[-1]["bbox"] = [73.40, 4.10, 73.60, 4.30]
        with self.assertRaises(SystemExit):
            mv.build(got, first, second)

    def test_a_polygon_inside_another_atoll_is_refused(self):
        got = mv.read(sheet())
        first, second = units()
        raa = next(u for u in second if u["name"] == "North Maalhosmadulu")
        raa["parent"] = "A1-HA"
        with self.assertRaises(SystemExit):
            mv.build(got, first, second)


if __name__ == "__main__":
    unittest.main()
