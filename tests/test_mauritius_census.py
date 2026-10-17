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
        with mock.patch.object(mu, "UNITS", {"portlouis": "portlouis", "rodrigues": "rodrigues"}), \
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


if __name__ == "__main__":
    unittest.main()
