"""Kuwait's 2021 register-based census, read from workbook rows built in memory."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import kuwait_census as kc  # noqa: E402

GOVS = list(kc.GOVERNORATES)
# Per governorate: Kuwaiti men/women, other men/women.
PEOPLE = {g: (100 + i, 110 + i, 300 + 10 * i, 100 + 5 * i) for i, g in enumerate(GOVS)}


def gov_label(g):
    return f"{g} Governorate"


def t1():
    rows = [[None, "x", "Kuwaiti", None, None, "Non-Kuwaiti"]]
    tot = [0] * 9
    for g in GOVS:
        km, kf, nm, nf = PEOPLE[g]
        cells = [km, kf, km + kf, nm, nf, nm + nf, km + nm, kf + nf, km + kf + nm + nf]
        tot = [a + b for a, b in zip(tot, cells)]
        rows.append([None, "عربي"] + cells + [gov_label(g)])
    rows.append([None, "الجملة"] + tot + ["Total"])
    return rows, tot[8]


BANDS = [f"{a}-{a + 4}" for a in range(0, 85, 5)] + ["> 84"]


def split(total, parts):
    base = [total // parts] * parts
    base[-1] += total - sum(base)
    return base


def t2():
    rows = [[None, "x", "x", "The Capital Governorate"]]
    per = {g: (split(sum(PEOPLE[g][0::2]), len(BANDS)), split(sum(PEOPLE[g][1::2]), len(BANDS)))
           for g in GOVS}
    for i, band in enumerate(BANDS):
        men = [per[g][0][i] for g in GOVS]
        women = [per[g][1][i] for g in GOVS]
        rows.append([None, band, "ذكر"] + men + [0, sum(men), "Male", band])
        rows.append([None, None, "انثى"] + women + [0, sum(women), "Female"])
        both = [m + w for m, w in zip(men, women)]
        rows.append([None, None, "الجملة"] + both + [0, sum(both), "Total"])
    return rows


def t6():
    rows = [[None, "x", "x", "Gulf", "Arabic", "Asian", "African", "European",
             "North America", "South America", "Australian", "Total"]]
    for g in GOVS:
        km, kf, nm, nf = PEOPLE[g]
        total = km + kf + nm + nf
        groups = [km + kf + 5, nm + nf - 5 - 3, 1, 1, 1, 0, 0, 0]
        rows.append([None, "عربي", "ذكر"] + [0] * 9 + ["Male", gov_label(g)])
        rows.append([None, None, "الجملة"] + groups + [total, "Total"])
    rows.append([None, "غير مبين", "ذكر"] + [0] * 9 + ["Male", "Not Stated"])
    rows.append([None, None, "الجملة"] + [0] * 9 + ["Total"])
    return rows


AREAS = {"The Capital": ["DASMAN", "AL-SHARQ"], "Hawalli": ["HAWALLI"],
         "Al-Ahmadi": ["AL-FAHAHEEL"], "Al-Jahra": ["AL-JAHRA", "AL-NAHDA"],
         "Al-Farwaniya": ["KHAITAN"], "Mubarak Al-Kabeer": ["AL-ADAN"]}


def t52(break_sum=False):
    rows = [[None, "Kuwaiti", None, None, "Non-Kuwaiti"]]
    for g in GOVS:
        km, kf, nm, nf = PEOPLE[g]
        names = AREAS[g]
        for j, name in enumerate(names):
            share = 1 if len(names) == 1 else (2 if j == 0 else None)
            if share == 1:
                parts = (km, kf, nm, nf)
            elif share == 2:
                parts = (km // 2, kf // 2, nm // 2, nf // 2)
            else:
                parts = (km - km // 2, kf - kf // 2, nm - nm // 2, nf - nf // 2)
            a, b, c, d = parts
            if break_sum and name == "DASMAN":
                a += 1
                cells = [a, b, a + b, c, d, c + d, a + c, b + d, a + b + c + d]
            else:
                cells = [a, b, a + b, c, d, c + d, a + c, b + d, a + b + c + d]
            rows.append(["عربي"] + cells + [name])
    rows.append(["غير مبين", 0, 0, 0, 0, 0, 0, 0, 0, 0, "NOT STATED"])
    return rows


ADMIN1 = [{"id": f"g{i}", "name": lab, "parent": "KWT"}
          for i, lab in enumerate(kc.GOVERNORATES.values())]
PARENTS = {u["id"]: u["name"] for u in ADMIN1}
ADMIN2 = [{"id": "a1", "name": "Dasman", "parent": "g0"},
          {"id": "a2", "name": "Sharq", "parent": "g0"},
          {"id": "a3", "name": "Hawalli", "parent": "g1"},
          {"id": "a4", "name": "Elnahda_Shark_Elsolybekhat", "parent": "g0"},
          {"id": "a5", "name": "Mina_Doha", "parent": "g0"},
          {"id": "a6", "name": "Mina_Doha", "parent": "g0"}]


class TheReader(unittest.TestCase):
    def setUp(self):
        self.saved = (kc.NATIONAL, kc.AREAS)
        rows, total = t1()
        kc.NATIONAL = total
        kc.AREAS = {"Dasman": "DASMAN", "Sharq": "AL-SHARQ", "Hawalli": "HAWALLI",
                    "Elnahda_Shark_Elsolybekhat": "AL-NAHDA"}

    def tearDown(self):
        kc.NATIONAL, kc.AREAS = self.saved

    def run_it(self, **kw):
        return kc.build(t1()[0], t2(), t6(), t52(**kw), ADMIN1, ADMIN2, PARENTS)

    def test_governorates_carry_population_sex_age_and_nationality(self):
        out = {r["shape_id"]: r for r in self.run_it()}
        cap = out["g0"]
        km, kf, nm, nf = PEOPLE["The Capital"]
        self.assertEqual(cap["population"]["value"], km + kf + nm + nf)
        self.assertEqual(cap["sex_ratio"]["value"], round(100 * (km + nm) / (kf + nf), 1))
        self.assertIsNotNone(cap["median_age"])
        groups = {s["group"]: s["count"] for s in cap["ethnicity"]}
        self.assertEqual(groups["Kuwaiti"], km + kf)
        self.assertEqual(groups["GCC nationals"], 5)

    def test_areas_are_bound_by_the_declared_table(self):
        out = {r["shape_id"]: r for r in self.run_it()}
        self.assertIn("a1", out)
        self.assertEqual(out["a1"]["ethnicity_basis"], "nationality")
        self.assertNotIn("a5", out)
        self.assertIn("counts the area in Jahra", out["a4"]["population"]["note"])

    def test_an_area_whose_cells_do_not_add_up_stops_the_run(self):
        with self.assertRaises(SystemExit):
            self.run_it(break_sum=True)

    def test_an_area_drawn_in_another_governorate_stops_the_run(self):
        kc.AREAS = dict(kc.AREAS, Hawalli="AL-FAHAHEEL")
        with self.assertRaises(SystemExit):
            self.run_it()

    def test_a_national_total_that_does_not_match_stops_the_run(self):
        kc.NATIONAL += 1
        with self.assertRaises(SystemExit):
            self.run_it()


if __name__ == "__main__":
    unittest.main()
