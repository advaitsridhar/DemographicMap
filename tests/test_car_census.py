"""The Central African Republic's 2021 census mapping and 2016 ages, on small sheets (no network)."""

import unittest

from scripts.fetch_census import car_census as cc
from scripts.fetch_census.binding import fold


def uscb(rows):
    """A USCB sheet: field names, then aliases, then data."""
    head = list(rows[0].keys())
    return cc.table([head, head] + [[r.get(k) for k in head] for r in rows])


class Sheets(unittest.TestCase):
    def test_uscb_and_ocha_layouts(self):
        rows = uscb([{"ADM_LEVEL": 1, "AREA_NAME": "Lobaye", "POP_BTOTL": 10, "POP_MTOTL": 5,
                      "POP_FTOTL": 5}])
        self.assertEqual(rows[0]["AREA_NAME"], "Lobaye")
        ocha = cc.plain([["Pcode3", "T_TL"], ["CF111", 12.4], [None, None]])
        self.assertEqual(ocha, [{"Pcode3": "CF111", "T_TL": 12.4}])

    def test_prev_communes(self):
        rows = [{"Pcode1": "CF11", "PrevPréfecture": "Lobaye", "Pcode2": "CF111",
                 "PrevSous-préfecture": "Mbaïki", "Pcode3": "CF1111", "PrevCommune": "Mbaïki",
                 "T_TL": 100.4, "M_TL": 49.2, "F_TL": 51.2},
                {"Pcode3": "", "T_TL": 5}]
        out = cc.prev_communes(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["total"], 100)


class Crosswalk(unittest.TestCase):
    def c21(self):
        def unit(pref, sp, name, total):
            return {"name": name, "pref": pref, "sp": sp, "total": total,
                    "men": round(total * 0.49), "women": total - round(total * 0.49)}
        return {"country": None, "prefectures": {}, "sps": {},
                "communes": [unit("Lobaye", "Mbaïki", "Mbaïki", 100),
                             unit("Lobaye", "Mbaïki", "Nouvelle commune", 40),
                             unit("Bangui", "Bangui", "Bégoua", 60),
                             unit("Lim-Pendé", "Paoua", "Paoua", 70)]}

    def test_names_siblings_and_placed(self):
        g03 = [("lobaye", "mbaiki", "mbaiki"), ("ouhampende", "paoua", "paoua"),
               ("ombellampoko", "bimbo", "bimbo")]
        held, problems = cc.own_crosswalk(self.c21(), g03)
        self.assertEqual(problems, [])
        # The new commune goes with its sibling; Bégoua to Bimbo as placed; Paoua
        # under the prefecture it was in before 2020.
        self.assertEqual(sum(u["total"] for u in held[("lobaye", "mbaiki")]), 140)
        self.assertEqual(held[("ombellampoko", "bimbo")][0]["name"], "Bégoua")
        self.assertEqual(held[("ouhampende", "paoua")][0]["total"], 70)

    def test_fixed_split_is_counted(self):
        c21 = self.c21()
        self.assertEqual(cc.fixed_split(c21), 0)
        c21["communes"][0]["men"] = 60
        self.assertEqual(cc.fixed_split(c21), 1)

    def test_seat_reason_names_no_process(self):
        self.assertIn("seats", cc.SEAT_GAP)
        for word in ("read", "fetch", "adapter", "build"):
            self.assertNotIn(word, cc.SEAT_GAP.lower())

    def test_suspect_duplicate(self):
        self.assertIn(fold("Dédé-Mokouba"), cc.SUSPECT)
        self.assertIn("23,708", cc.SUSPECT[fold("Dédé-Mokouba")])
        self.assertEqual(cc.spelled("Dede-Makouba"), "Dédé-Mokouba")


class Ages(unittest.TestCase):
    def row(self, name, shares, men=490, women=510):
        row = {"ADM_LEVEL": 1, "AREA_NAME": name, "MTOTL": men, "FTOTL": women,
               "BTOTL": men + women}
        for i, low in enumerate(range(0, 80, 5)):
            row[f"B{low:02d}{low + 4:02d}"] = shares[i]
        row["B80PL"] = shares[16]
        return row

    def test_age_table_and_copies(self):
        young = [150, 140, 120, 100, 90, 80, 70, 60, 50, 40, 30, 25, 20, 10, 8, 5, 2]
        old = [100, 95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 25, 20, 5]
        ages = cc.age_table([self.row("Vakaga", young), self.row("Bangui", old),
                             self.row("Kémo", young)])
        self.assertEqual(ages["vakaga"]["groups"][-1], [80, None, 2])
        own, report = cc.own_structures(ages)
        # Vakaga and Kémo share one structure: neither is taken for its own.
        self.assertEqual(own, {"bangui"})
        self.assertTrue(any("share one structure" in line for line in report))


if __name__ == "__main__":
    unittest.main()
