"""Micronesia: the census workbooks' layouts, cut down to a few rows. No network.

The fixtures follow what the office's workbooks print: 2023's tables set the
sexes off by BOTH GENDER / MALE / FEMALE rows and Yap's two municipality
blocks one above the other; 2010's put the men's and women's totals on their
"Male" and "Female" rows and Yap's two blocks side by side, each with its own
label column; ethnicity's single groups, then the mixed answers by main
ethnicity, each split beneath by the other group.
"""

import unittest

from scripts.fetch_census import micronesia_census as fm
from scripts.fetch_census.oceania_common import bind_level, load_units


def b1_2023(blocks):
    """Table B1, 2023 layout: blocks of {unit: (total, male, female, median, groups)}."""
    rows = [["POPULATION TABLES"]]
    for units in blocks:
        names = list(units)
        rows += [["Table B1. Age and Sex by Municipality, 2023"],
                 ["Age group", "TOTAL", "Total"] + ["   " + n for n in names]]
        for sex, index in (("BOTH GENDER", 0), ("MALE", 1), ("FEMALE", 2)):
            rows.append([sex])
            rows.append(["Total", None, None] + [units[n][index] for n in names])
            if index == 0:
                for i, (lo, hi) in enumerate(((0, 14), (15, 29), (30, 44), (45, None))):
                    label = f"{lo}-{hi}" if hi is not None else f"{lo}+"
                    rows.append([label, None, None] + [units[n][4][i] for n in names])
            rows.append(["Median age", None, None] + [units[n][3] for n in names])
    rows.append(["Table B2. Relationship"])
    return rows


class Layouts(unittest.TestCase):

    def test_2023_blocks_one_above_the_other(self):
        rows = b1_2023([
            {"Gagil": (854, 418, 436, 31.4, (200, 200, 200, 254)),
             "Rull": (2080, 1007, 1073, 31.0, (520, 500, 500, 560))},
            {"Woleai": (838, 359, 478, 26.1, (250, 250, 170, 168)),
             "Ulithi": (704, 332, 371, 26.4, (200, 200, 150, 154))},
        ])
        got = fm.age_sex(rows, ("Gagil", "Rull", "Woleai", "Ulithi"))
        self.assertEqual(got["Woleai"]["total"], 838)
        self.assertEqual((got["Woleai"]["male"], got["Woleai"]["female"]), (359, 478))
        self.assertEqual(got["Rull"]["median_both"], 31.0)
        self.assertEqual(got["Gagil"]["groups"][0], (0, 14, 200))
        fm.check_age("Gagil", got["Gagil"], 2023)

    def test_a_printed_median_far_from_the_groups_stops_the_run(self):
        rows = b1_2023([{"Gagil": (854, 418, 436, 50.0, (200, 200, 200, 254)),
                         "Rull": (2080, 1007, 1073, 31.0, (520, 500, 500, 560))}])
        got = fm.age_sex(rows, ("Gagil", "Rull"))
        with self.assertRaises(SystemExit):
            fm.check_age("Gagil", got["Gagil"], 2023)

    def test_2010_side_by_side_blocks_with_their_sexes_on_their_own_rows(self):
        head = ["Age Group", "Total", "Yap Proper", "Gagil", "Rull", "Age Group",
                "Yap Outer Islands", "Woleai", "Ulithi"]
        rows = [["Table B01.  Age and Sex by Municipality"], head,
                ["Total", 3000, 2000, 900, 1100, "Total", 1000, 600, 400],
                ["Less than 5 years", 300, 200, 90, 110, "Less than 5 years", 100, 60, 40],
                ["Median", 25, 26.5, 26.3, 27.6, "Median", 22.3, 22.1, 21.1],
                ["75+", 30, 20, 9, 11, "75+", 10, 6, 4],
                ["   Male", 1500, 1000, 450, 550, "   Male", 500, 300, 200],
                ["Median", 24, 25, 25.6, 28.3, "Median", 19.2, 18.8, 19.6],
                ["   Female", 1500, 1000, 450, 550, "   Female", 500, 300, 200],
                ["Table B02. Household type"]]
        got = fm.age_sex(rows, ("Gagil", "Rull", "Woleai", "Ulithi"))
        self.assertEqual((got["Woleai"]["total"], got["Woleai"]["male"]), (600, 300))
        self.assertEqual(got["Ulithi"]["median_both"], 21.1)
        self.assertEqual(got["Rull"]["median_male"], 28.3)
        # Chuuk's "75+" row under the median repeats groups already read.
        self.assertEqual(got["Gagil"]["groups"], [(0, 4, 90)])

    def test_a_municipality_nobody_listed_breaks_the_state_sum(self):
        got = {name: {"total": 10} for name in fm.MUNICIPALITIES["Kosrae"]}
        fm.add_up("Kosrae", got, 40, 2023)
        with self.assertRaises(SystemExit):
            fm.add_up("Kosrae", got, 52, 2023)
        del got["Utwe"]
        with self.assertRaises(SystemExit):
            fm.add_up("Kosrae", got, 30, 2023)

    def test_a_name_broken_over_two_header_rows_is_joined(self):
        rows = [["Table B1. Age and Sex by Municipality"],
                [None, None, "Madole-", None, "Mwoak-"],
                ["Age group", "Total", "nihmw", "U", "illoa"],
                ["BOTH GENDER"], ["Total", 6603, 4129, 2413, 61]]
        flat = fm.flat_rows(rows, ("Madolenihmw", "U", "Mwoakilloa"))
        self.assertEqual(flat[-1][2], {"Madolenihmw": 4129, "U": 2413, "Mwoakilloa": 61})

    def test_regions_and_totals_are_read_past(self):
        rows = [["Table B01."], ["Age Group", "Total", "Chuuk Lagoon", "Northern Namoneas",
                                 "Weno", "Fono", "Faichuk", "Tol"],
                ["Total", 100, 60, 50, 40, 10, 10, 10]]
        flat = fm.flat_rows(rows, ("Weno", "Fono", "Tol"))
        self.assertEqual(flat[0][2], {"Weno": 40, "Fono": 10, "Tol": 10})


class Compositions(unittest.TestCase):

    def test_suppressed_religion_cells_are_left_out_and_said(self):
        rows = [["Table B6. Religion by Municipality"],
                ["Religion", "TOTAL", "Total", "Gagil", "Rull"],
                ["BOTH GENDER"], ["Total", 2934, 2934, 854, 2080]]
        counts = {"Roman Catholic": (639, 1463), "Congregation/Protestant": (17, 170),
                  "Assembly of God": ("*", "*"), "Pentecostal": ("*", 17),
                  "Apostolic": ("*", "*"), "Baptist": (37, 56), "SDA": ("*", 29),
                  "Mormon": (18, 42), "Jehovah's Witness": ("*", 28),
                  "Other religion": (70, 217), "No religion/Refused": (56, 48)}
        for label, (gagil, rull) in counts.items():
            rows.append([label, None, None, gagil, rull])
        rows += [["MALE"], ["Total", 1, 1, 418, 1007], ["Roman Catholic", 1, 1, 319, 713],
                 ["Source: 2023 FSM Population and Housing Census"], ["Table H1."]]
        got = fm.religion_2023(rows, ("Gagil", "Rull"))
        self.assertIsNone(got["Gagil"]["counts"]["Seventh-day Adventist"])
        shares, note = fm.religion_note(2023, 854, got["Gagil"]["counts"], "Gagil")
        self.assertEqual(shares[0]["group"], "Roman Catholic")
        self.assertEqual(shares[0]["count"], 639)
        self.assertIn("17 people in those cells", note)
        self.assertLess(sum(s["pct"] for s in shares), 100)

    def test_unsuppressed_religion_must_add_up(self):
        counts = {"Roman Catholic": 600, "Baptist": 100}
        with self.assertRaises(SystemExit):
            fm.religion_note(2023, 854, counts, "Gagil")

    def test_ethnicity_takes_leaves_and_mixed_answers_by_main_group(self):
        head = ["Ethnicity", "Total", "Pohnpei Proper", "Kolonia", "Nett"]
        rows = [["Table B08. Single and Multiple Ethnicity"], head,
                ["All Persons", 0, 0, 1000, 500],
                ["Single ethnicity", 0, 0, 800, 450],
                ["Pohnpeian", 0, 0, 600, 400], ["Chuukese", 0, 0, 100, 20],
                ["Caucasian / White", 0, 0, 30, 10],
                ["    U.S. American", 0, 0, 20, 10], ["    Other Caucasian / White", 0, 0, 10, 0],
                ["Asian", 0, 0, 60, 20], ["    Filipino", 0, 0, 60, 20],
                ["Other", 0, 0, 10, 0],
                ["Multiple Ethnicity", 0, 0, 200, 50],
                ["Pohnpeian as main ethnicity and", 0, 0, 120, 30],
                ["    Chuukese", 0, 0, 100, 30], ["    Other", 0, 0, 20, 0],
                ["Other as main ethnicity and", 0, 0, 30, 0], ["    Pohnpeian", 0, 0, 30, 0],
                ["Multiple Pohnpeian localities", 0, 0, 50, 20],
                ["Source: 2010 FSM Census"], ["Table B08A. Male"]]
        got = fm.ethnicity_2010(rows, ("Kolonia", "Nett"))
        self.assertEqual(got["Kolonia"]["Pohnpeian"], 600)
        self.assertEqual(got["Kolonia"]["Chuukese"], 100)
        self.assertEqual(got["Kolonia"]["U.S. American"], 20)
        self.assertNotIn("Caucasian / White", got["Kolonia"])
        self.assertEqual(got["Kolonia"]["Pohnpeian and another ethnicity"], 120)
        self.assertEqual(got["Kolonia"]["Two or more Pohnpei State ethnicities"], 50)
        self.assertEqual(sum(got["Kolonia"].values()), 1000)
        self.assertEqual(sum(got["Nett"].values()), 500)
        fm.composition_2010(got["Nett"], 500, "Nett's ethnicity")
        with self.assertRaises(SystemExit):
            fm.composition_2010(got["Nett"], 501, "Nett's ethnicity")

    def test_language_rows_follow_their_total_and_must_add_up(self):
        rows = [["Table B10A."], ["Literacy", "Total", "Lelu", "Malem"],
                ["Language mainly spoken at  home 3+ years", 3214, 1996, 1218],
                ["English", 57, 50, 7], ["Kosraean", 3080, 1887, 1193], ["Pohnpeian", 12, 12, 0],
                ["Filipino", 35, 35, 0], ["Chinese / Taiwanese", 6, 6, 0],
                ["Other Pacific Island Languages", 24, 6, 18],
                ["Source: 2010 FSM Census"]]
        flat = fm.flat_rows(rows, ("Lelu", "Malem"))
        got = fm.section(flat, "languagemainlyspoken", fm.LANGUAGE, "language")
        self.assertEqual(got["Lelu"]["total"], 1996)
        self.assertEqual(got["Lelu"]["counts"]["Chinese"], 6)
        rows[4][2] = 1886
        with self.assertRaises(SystemExit):
            fm.section(fm.flat_rows(rows, ("Lelu", "Malem")), "languagemainlyspoken",
                       fm.LANGUAGE, "language")


class Binding(unittest.TestCase):

    def test_every_drawn_municipality_is_a_census_one(self):
        admin1, admin2 = load_units("FSM", "admin1"), load_units("FSM", "admin2")
        if not admin2:
            self.skipTest("no FSM units in this checkout")
        rows = fm.municipal_rows(admin2)
        self.assertEqual(len(rows), len(admin2))
        bound = bind_level(rows, admin2, {u["id"]: u["name"] for u in admin1}, fm.ALIASES)
        self.assertEqual(bound["Chuuk-Piherarh"]["name"], "Piherech")
        parents = {u["id"]: u["name"] for u in admin1}
        for key, unit in bound.items():
            self.assertEqual(parents[unit["parent"]], key.split("-", 1)[0], key)


if __name__ == "__main__":
    unittest.main()
