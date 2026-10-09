"""Nauru: the 2021 workbook's district sheets and Persons Tabulations Table 19. No network.

The sheets follow the workbook's layout -- a title, a "Sex" or "Ethnicity"
row, a header whose second cell is "Total", the country's row, then each
district as "N-Name" -- with every district present and small figures; the
Table 19 lines are as pypdf reads them.
"""

import unittest

from scripts.fetch_census import nauru_census as nr
from scripts.fetch_census.oceania_common import load_units

PEOPLE = {1: (803, 398, 405), 2: (845, 417, 428), 3: (1258, 655, 603), 4: (969, 490, 479),
          5: (348, 171, 177), 6: (724, 368, 356), 7: (341, 174, 167), 8: (523, 259, 264),
          9: (537, 260, 277), 10: (795, 408, 387), 11: (565, 283, 282), 12: (276, 136, 140),
          13: (373, 183, 190), 14: (1797, 916, 881), 15: (1526, 775, 751)}
CITIZENS = {1: 787, 2: 828, 3: 1202, 4: 932, 5: 322, 6: 719, 7: 337, 8: 521, 9: 513,
            10: 788, 11: 547, 12: 268, 13: 358, 14: 1731, 15: 1362}
SPELLED = {**nr.DISTRICTS, 5: "Denigomod"}


def label(code):
    return f"     {code}-{SPELLED[code]}"


def sheets():
    g1 = [[None], ["Table G-1: Total population by district and sex"], [None, "Sex"],
          [None, "Total", "Male", "Female"], ["TOTAL", 11680, 5893, 5787], ["District"]]
    g1 += [[label(c), *PEOPLE[c]] for c in PEOPLE]
    i1 = [[None], ["Table I-1"], [None, "Ethnicity"],
          [None, "Total", "Nauruan", "Kiribati", "Fijian", "Other ethnicity"],
          ["TOTAL", 11680, 0, 0, 0, 0], ["District"]]
    for c, (t, _, _) in PEOPLE.items():
        i1.append([label(c), t, t - 30, 10, 15, 5])
    h1 = [[None], ["Table H-1"], [None, "Citizenship"],
          [None, "Total", "1 - Citizens", "2 - Non-citizens", "3 - Status unknown"],
          ["TOTAL", 11680, 11215, 424, 41], ["District"]]
    h1 += [[label(c), PEOPLE[c][0], CITIZENS[c], PEOPLE[c][0] - CITIZENS[c], 0] for c in PEOPLE]
    m1 = [[None], ["Table M-1"], [None, "District"],
          [None, "Total"] + [f"{c}-{nr.DISTRICTS[c]}" for c in PEOPLE], ["TOTAL"],
          ["Age (5-year age bands)"]]
    bands = ["15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54",
             "55-59", "60-64", "65+"]
    # 61.5% of each district aged 15 and over, as in the country, spread like it.
    shares = [0.0878, 0.0842, 0.0827, 0.0847, 0.0762, 0.0556, 0.0422, 0.0318, 0.0277,
              0.0205, 0.0220]
    for band, share in zip(bands, shares):
        m1.append(["     " + band, None] + [round(PEOPLE[c][0] * share) for c in PEOPLE])
    g7 = [[None], ["Table G-7: Total population by religious affiliation and sex"],
          [None, "Sex"], [None, "Total", "Male", "Female"], ["TOTAL", 11680, 5893, 5787],
          ["Religion"]]
    for name, n in (("No Religion", 157), ("Nauruan Congregational", 4001), ("Catholic", 3959),
                    ("Assemblies of God (AOG)", 1365), ("Nauru Independent", 410),
                    ("Pacific Light House", 706), ("Seven Day Adventist", 168),
                    ("Baptist", 175), ("Do not wish to answer", 57), ("Protestant", 126),
                    ("Shalosh Pentecostal Church", 186), (" Fishers of Men Church", 57),
                    ("Brethren Church", 47), ("FOM Pentecostal Church", 81),
                    ("Christ Embassy", 48), ("Hinduism", 6),
                    ("Fundamental Christian Church", 15), ("Methodist Church", 18),
                    ("Other religion", 98)):
        g7.append(["     " + name, n, None, None])
    return {"G-1": g1, "I-1": i1, "H-1": h1, "M-1": m1, "G-7": g7}


def table19():
    """As pypdf reads the pages: each page's figures first, its title after them."""
    total = "Total 11,215 142 3,889 3,797 1,301 403 704 146 168 126 34 - - - 468 37"
    age = ["   Total", "         " + total, "         0 - 4 1,436 15 498 486 167 52 90 19 "
           "22 16 4 - - - 60 7", "Table 18.  Nauruan Population (citizen/dual) by Sex by Five "
           "Year Age Groups by Religion"]
    lines = ["Total No ", "Religion", "Do not ", "wish to ", "answer", "   Total",
             "         " + total]
    for c, n in CITIZENS.items():
        rest = n - 100
        lines.append(f"         {c}-{nr.DISTRICTS[c]} {n:,} 1 {rest:,} 90 - - - - - - - "
                     f"- - - 9 -")
    lines += ["District by Sex", "Religion",
              "Table 19.  Nauruan Population (citizen/dual) by Sex by District by Religion"]
    male = ["   Male 0", "         Total 5,644 76 1,960 1,918 638 206 362 68 87 66 12 - - - "
            "227 24", "         1-Yaren 392 3 49 224 36 18 36 - - - - - - - 25 1",
            "Table 19.  Nauruan Population (citizen/dual) by Sex by District by Religion",
            "Table 20.  Population by Citizenship"]
    return ["\n".join(age), "\n".join(lines), "\n".join(male)]


class Reading(unittest.TestCase):

    def test_tables_add_up_and_location_joins_denigomodu(self):
        tables = nr.read_tables(sheets())
        self.assertEqual(tables["people"][8], [523, 259, 264])
        self.assertEqual(tables["ethnic_groups"],
                         ["Nauruan", "I-Kiribati", "Fijian", "Other ethnicity"])
        self.assertEqual(nr.merged(5, tables["people"]), [1874, 946, 928])
        religion = nr.read_religion(table19(), tables["citizens"])
        self.assertEqual(religion[3]["Nauru Congregational Church"], 1102)
        fields = nr.fields_for(5, tables, religion)
        self.assertEqual(fields["population"]["value"], 1874)
        self.assertIn("1,526 of Location", fields["population_note"])
        self.assertNotIn("population_note", nr.fields_for(4, tables, religion))
        self.assertEqual(fields["religion"][0]["group"], "Nauru Congregational Church")
        self.assertIn("Shalosh Pentecostal Church, Fishers of Men Church", fields["religion_note"])
        self.assertIn("(387 people in all)", fields["religion_note"])
        self.assertEqual(fields["language"]["status"], "not_available")
        self.assertTrue(18 <= fields["median_age"]["value"] <= 25)

    def test_a_district_whose_groups_do_not_add_up_stops_the_run(self):
        bad = sheets()
        bad["I-1"][8][2] -= 1
        with self.assertRaises(SystemExit):
            nr.read_tables(bad)

    def test_religion_must_count_the_district_citizens(self):
        tables = nr.read_tables(sheets())
        tables["citizens"][4] += 1
        with self.assertRaises(SystemExit):
            nr.read_religion(table19(), tables["citizens"])

    def test_a_median_in_the_under_fifteens_is_not_placed(self):
        self.assertIsNone(nr.median_of(100, [(15, 19, 20), (20, None, 20)]))
        self.assertIsNotNone(nr.median_of(100, [(15, 19, 30), (20, None, 30)]))


class Binding(unittest.TestCase):

    def test_both_levels_bind_every_district(self):
        admin1, admin2 = load_units("NRU", "admin1"), load_units("NRU", "admin2")
        if not admin1:
            self.skipTest("no NRU units in this checkout")
        tables = nr.read_tables(sheets())
        religion = nr.read_religion(table19(), tables["citizens"])
        tables["ages15"] = {c: [(lo, hi, n) for lo, hi, n in g]
                            for c, g in tables["ages15"].items()}
        records = nr.build(tables, religion, admin1, admin2)
        self.assertEqual(len(records), len(admin1) + len(admin2))
        names = {r["name"] for r in records}
        self.assertIn("Baiti", names)
        self.assertNotIn("Location", names)


if __name__ == "__main__":
    unittest.main()
