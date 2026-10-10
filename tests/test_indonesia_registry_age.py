"""Indonesia: median age and sex ratio from provincial civil-register age structures.

No network: the STRUKTUR UMUR sheet is built here in the registry's layout.
"""

import unittest

from scripts.fetch_census import indonesia_registry_age as r

BANDS = [f"{a:02d}-{a + 4:02d}" for a in range(0, 75, 5)] + [">75"]


def grid(rows, sexes=("L", "P", "JML")):
    """rows: (code, name, men per band, women per band)."""
    head = ["NO", "WILAYAH", "KODE"] + [f"{b} ({s})" for b in BANDS for s in sexes]
    out = [["STRUKTUR UMUR"], head]
    for i, (code, name, m, f) in enumerate(rows):
        out.append([i or None, name, code] + [v for _ in BANDS for v in (m, f, m + f)])
    return out


SOURCE = r.Source("test", "West Sumatra", "13", "u", "p", 2023, "the end of 2023", "Title")
ADMIN1 = [{"id": "P13", "name": "West Sumatra"}]
ADMIN2 = [{"id": "A", "name": "Kota Sawah Lunto", "parent": "P13"},
          {"id": "B", "name": "Dharmasraya", "parent": "P13"},
          {"id": "L", "name": "Danau", "parent": "P13"}]


def rows(extra_men=0):
    return [(13, "SUMATERA BARAT", 30 + extra_men, 30), (13.73, "KOTA SAWAHLUNTO", 10, 10),
            (13.1, "DHARMASRAYA", 20, 20)]


class ReadTest(unittest.TestCase):
    def test_codes_names_and_sexes(self):
        got = r.read(grid(rows()), "t")
        self.assertEqual([x["code"] for x in got], ["13", "13.73", "13.10"])
        self.assertEqual(got[1]["groups"][(75, None)], {"M": 10, "F": 10, "T": 20})

    def test_the_lk_pr_spelling(self):
        got = r.read(grid(rows(), sexes=("LK", "PR", "JML")), "t")
        self.assertEqual(got[2]["groups"][(0, 4)]["M"], 20)

    def test_sexes_that_do_not_make_both_refuse(self):
        g = grid(rows())
        g[3][5] += 1
        with self.assertRaises(SystemExit):
            r.read(g, "t")


class BuildTest(unittest.TestCase):
    def test_records_bind_by_name_inside_the_province(self):
        recs = {x["shape_id"]: x for x in r.build(SOURCE, grid(rows()), ADMIN1, ADMIN2)}
        self.assertEqual(set(recs), {"P13", "A", "B"})       # the lake takes nothing
        # 16 equal groups to an open 75+: the middle person ends the 35-39 group.
        self.assertEqual(recs["A"]["median_age"]["value"], 40.0)
        self.assertEqual(recs["B"]["sex_ratio"]["value"], 100.0)
        self.assertIn("Kota Sawahlunto (13.73)", recs["A"]["median_age_note"])
        self.assertIn("not a census", recs["P13"]["median_age_note"])
        self.assertEqual(recs["P13"]["level"], "admin1")
        self.assertNotIn("value", recs["A"]["population"])

    def test_regencies_that_do_not_make_the_province_refuse(self):
        with self.assertRaises(SystemExit):
            r.build(SOURCE, grid(rows(extra_men=1)), ADMIN1, ADMIN2)

    def test_a_polygon_with_no_row_refuses(self):
        admin2 = ADMIN2 + [{"id": "C", "name": "Agam", "parent": "P13"}]
        with self.assertRaises(SystemExit):
            r.build(SOURCE, grid(rows()), ADMIN1, admin2)


class UnreadTest(unittest.TestCase):
    def test_every_other_unit_but_water_says_why(self):
        admin1 = ADMIN1 + [{"id": "P11", "name": "Aceh"}]
        admin2 = ADMIN2 + [{"id": "Z", "name": "Danau Toba", "parent": "P12"},
                           {"id": "Y", "name": "Aceh Besar", "parent": "P11"}]
        recs = {x["shape_id"]: x for x in r.unread(admin1, admin2, {"P13", "A", "B"})}
        self.assertEqual(set(recs), {"P11", "Y"})
        self.assertIn("HTTP 403", recs["Y"]["median_age"]["note"])
        self.assertNotIn("value", recs["P11"]["sex_ratio"])


if __name__ == "__main__":
    unittest.main()
