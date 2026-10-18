"""Mauritius' 2022 census by district and island, from Statistics Mauritius'
Volume II workbook, Tables D2, D6 and D9 (scripts/fetch_census/mauritius_census)."""

import unittest
from unittest import mock

from scripts.fetch_census import mauritius_census as mu

AGE_HEAD = ["Country, District, Municipal Ward/Village Council Area and Sex", "All ages", "<1",
            "1 - 4"] + [f"{a} - {a + 4}" for a in range(5, 75, 5)] + ["75+"]
SHARE = [1, 4, 6, 7, 8, 8, 8, 8, 7, 7, 7, 6, 6, 6, 5, 4, 2]   # of every 100, 17 groups


def ages(n):
    out = [n * s // 100 for s in SHARE]
    out[5] += n - sum(out)
    return out


def d2(units):
    rows = [["Table D2 - Resident population by geographical location, age and sex"],
            ["Table of Contents"], AGE_HEAD, [None]]
    for label, men, women in units:
        rows.append([label])
        am, aw = ages(men), ages(women)
        rows.append(["Both sexes", men + women] + [x + y for x, y in zip(am, aw)])
        rows.append(["Male", men] + am)
        rows.append(["Female", women] + aw)
    return rows


def comp(units, head):
    rows = [["Table D6"], ["Table of Contents"], ["Country, District", "Total", head[0]],
            [None, None] + head[1]]
    for label, counts in units:
        rows.append([label, sum(counts)] + counts)
    return rows


RELIGION_HEAD = ("Religious group", ["Buddhist/ Chinese", "Roman Catholic",
                                     "Tamil/ Tamil Hindu", "Hindu & Other Hindu", "Islam",
                                     "Not stated"])
LANGUAGE_HEAD = ("Language usually spoken at home", ["Bhojpuri 1", "Creole 1", "French 1",
                                                     "Other & Not stated"])


class MauritiusCensusTest(unittest.TestCase):
    def test_blocks_heads_and_the_hindu_groups(self):
        a = mu.read_d2(d2([("REPUBLIC OF MAURITIUS", 900, 1000),
                           ("PORT LOUIS DISTRICT-Whole District", 450, 500),
                           ("Town of Port Louis-Ward 1", 50, 60),
                           ("ISLAND OF RODRIGUES", 450, 500)]))
        self.assertEqual(sorted(a), ["portlouis", "rodrigues"])
        self.assertEqual(a["portlouis"]["total"], 950)
        self.assertGreater(mu.grouped_median(a["portlouis"]["ages"]), 20)
        r = mu.read_composition(comp([("PORT LOUIS DISTRICT-Whole District",
                                       [10, 300, 100, 200, 330, 10])], RELIGION_HEAD), "D6",
                                mu.religion_of)
        self.assertEqual(r["portlouis"]["counts"]["Hindu"], 300)
        self.assertEqual(r["portlouis"]["unstated"], 10)
        g = mu.read_composition(comp([("PORT LOUIS DISTRICT-Whole District",
                                       [100, 800, 40, 10])], LANGUAGE_HEAD), "D9",
                                mu.language_of)
        self.assertEqual(g["portlouis"]["counts"]["Mauritian Creole"], 800)

    def test_parts_that_do_not_make_the_total_are_refused(self):
        rows = comp([("PORT LOUIS DISTRICT", [10, 300, 100, 200, 330, 10])], RELIGION_HEAD)
        rows[-1][1] += 1
        with self.assertRaises(SystemExit):
            mu.read_composition(rows, "D6", mu.religion_of)

    def test_both_levels_get_the_same_figures(self):
        units = [("PORT LOUIS DISTRICT-Whole", 450, 500), ("ISLAND OF RODRIGUES", 20, 21)]
        tables = {"D2": mu.read_d2(d2(units)),
                  "D6": mu.read_composition(comp([("PORT LOUIS DISTRICT-Whole",
                                                   [10, 300, 100, 200, 330, 10]),
                                                  ("ISLAND OF RODRIGUES", [1, 30, 0, 0, 10, 0])],
                                                 RELIGION_HEAD), "D6", mu.religion_of),
                  "D9": mu.read_composition(comp([("PORT LOUIS DISTRICT-Whole",
                                                   [100, 800, 40, 10]),
                                                  ("ISLAND OF RODRIGUES", [0, 40, 1, 0])],
                                                 LANGUAGE_HEAD), "D9", mu.language_of)}
        with mock.patch.object(mu, "UNITS", {"portlouis": ("portlouis",),
                                             "rodrigues": ("rodrigues",)}), \
                mock.patch.object(mu, "NATIONAL", 991):
            recs = mu.build(tables, [{"id": "P", "name": "Port Louis"},
                                     {"id": "R", "name": "Rodrigues"}],
                            [{"id": "p", "name": "Port Louis", "parent": "P"},
                             {"id": "r", "name": "Rodrigues", "parent": "R"}])
        by = {r["shape_id"]: r for r in recs}
        self.assertEqual(by["P"]["population"], by["p"]["population"])
        self.assertEqual(by["P"]["religion"][0]["group"], "Islam")
        self.assertIn("five Hindu groups", by["p"]["religion_note"])
        self.assertEqual(by["r"]["sex_ratio"]["value"], round(1000 * 20 / 21))

    def test_rodrigues_carries_nationality_and_the_districts_say_why_not(self):
        d4 = [["Table D4 - Population present on Census night and resident population"],
              ["Table of Contents"],
              ["Country, Island and Nationality", "Present population", None, None,
               "Resident population"],
              [None, "Both sexes", "Male", "Female", "Both sexes", "Male", "Female"],
              ["ISLAND OF MAURITIUS"], ["Total", 10, 5, 5, 10, 5, 5],
              ["ISLAND OF RODRIGUES"], ["Total", 43, 20, 23, 41, 20, 21],
              ["Mauritian", 38, 18, 20, 38, 19, 19], ["By birth", 38, 18, 20, 38, 19, 19],
              ["Non-Mauritian", 5, 2, 3, 3, 1, 2], ["Africa", 1, 0, 1, 1, 0, 1],
              ["Madagascar", 1, 0, 1, 1, 0, 1], ["Europe", 4, 2, 2, 2, 1, 1],
              ["France", 3, 2, 1, 2, 1, 1], ["Other", 1, 0, 1, 0, 0, 0],
              ["Other / Not stated", 0, 0, 0, 0, 0, 0]]
        nat = mu.read_d4(d4)
        self.assertEqual((nat["rodrigues"]["mauritian"], nat["rodrigues"]["foreign"]), (38, 3))
        units = [("PORT LOUIS DISTRICT-Whole", 450, 500), ("ISLAND OF RODRIGUES", 20, 21)]
        tables = {"D2": mu.read_d2(d2(units)), "D4": nat,
                  "D6": mu.read_composition(comp([("PORT LOUIS DISTRICT-Whole",
                                                   [10, 300, 100, 200, 330, 10]),
                                                  ("ISLAND OF RODRIGUES", [1, 30, 0, 0, 10, 0])],
                                                 RELIGION_HEAD), "D6", mu.religion_of),
                  "D9": mu.read_composition(comp([("PORT LOUIS DISTRICT-Whole",
                                                   [100, 800, 40, 10]),
                                                  ("ISLAND OF RODRIGUES", [0, 40, 1, 0])],
                                                 LANGUAGE_HEAD), "D9", mu.language_of)}
        with mock.patch.object(mu, "UNITS", {"portlouis": ("portlouis",),
                                             "rodrigues": ("rodrigues",)}), \
                mock.patch.object(mu, "NATIONAL", 991):
            recs = mu.build(tables, [{"id": "P", "name": "Port Louis"},
                                     {"id": "R", "name": "Rodrigues"}], [])
        by = {r["shape_id"]: r for r in recs}
        self.assertEqual(by["R"]["ethnicity"][0], {"group": "Mauritian nationals", "pct": 92.7,
                                                   "count": 38})
        self.assertEqual(by["R"]["ethnicity_basis"], "nationality")
        self.assertIn("Rodrigues' residents", by["R"]["ethnicity_note"])
        self.assertIn("by island (Volume II, Table D4), not by district",
                      by["P"]["ethnicity"]["note"])
        self.assertTrue(any(s["field"] == "ethnicity note" for s in by["P"]["sources"]))

    def test_d4_countries_must_make_their_region(self):
        d4 = [["Table D4"], ["Table of Contents"],
              ["Country, Island and Nationality", "Present population", None, None,
               "Resident population"],
              [None, "Both sexes", "Male", "Female", "Both sexes", "Male", "Female"],
              ["ISLAND OF RODRIGUES"], ["Total", 43, 20, 23, 41, 20, 21],
              ["Mauritian", 38, 18, 20, 38, 19, 19], ["Non-Mauritian", 5, 2, 3, 3, 1, 2],
              ["Europe", 4, 2, 2, 3, 1, 2], ["France", 3, 2, 1, 2, 1, 1]]
        with self.assertRaises(SystemExit):
            mu.read_d4(d4)

    def test_the_abbreviated_district_and_the_outer_islands(self):
        self.assertEqual(mu.unit_of("R. DU REMPART DISTRICT"), "rivieredurempart")
        self.assertEqual(mu.unit_of("RIVIERE DU REMPART DISTRICT"), "rivieredurempart")
        self.assertIsNone(mu.unit_of("Rivière du Rempart VCA"))
        tables = {"D2": {}, "D6": {}, "D9": {}}
        with mock.patch.object(mu, "UNITS", {}), mock.patch.object(mu, "NATIONAL", 0):
            recs = mu.build(tables, [{"id": "A", "name": "Agaléga"}], [])
        self.assertEqual(recs[0]["median_age"]["status"], "not_available")
        self.assertIn("Agaléga has no line", recs[0]["median_age"]["note"])
        self.assertNotIn("value", recs[0]["population"])


if __name__ == "__main__":
    unittest.main()
