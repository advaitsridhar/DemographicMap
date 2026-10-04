"""Mongolia's soum ages: json-stat2 reading, the sums, binding, offline.

Two aimags -- Arkhangai with two soums, and Khuvsgul (drawn "Hovsgel") with
one -- and the capital with one district, laid out as data.1212.mn's PxWeb
answers DT_NSO_0300_067V2 and DT_NSO_0300_068V2 in json-stat2.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import mongolia_ages as ma  # noqa: E402

GROUPS = [f"    {a}-{a + 4}" for a in range(0, 70, 5)] + ["    70+"]
EN = {"0": "Total", "1": "Khangai region", "165": "Arkhangai", "16501": "Erdenebulgan",
      "16513": "Ikhtamir", "167": "Khuvsgul", "16701": "Murun", "511": "Ulaanbaatar",
      "51101": "Bayanzurkh"}
MN = {"0": "Улсын дүн", "1": "Хангайн бүс", "165": "Архангай", "16501": "Эрдэнэбулган",
      "16513": "Их тамир", "167": "Хөвсгөл", "16701": "Мөрөн", "511": "Улаанбаатар",
      "51101": "Баянзүрх"}
SOUMS = {"16501": 3, "16513": 1, "16701": 2, "51101": 10}


def counts(scale):
    """Men and women by group, a young population."""
    men = [scale * (100 - 5 * i) for i in range(15)]
    women = [m + scale * i for i, m in enumerate(men)]
    return men, women


def tables():
    by_area = {}
    for code, scale in SOUMS.items():
        by_area[code] = counts(scale)
    for aimag in ("165", "167", "511"):
        parts = [by_area[c] for c in SOUMS if c.startswith(aimag)]
        by_area[aimag] = tuple([sum(x) for x in zip(*[p[i] for p in parts])] for i in (0, 1))
    region = ["165", "167"]
    by_area["1"] = tuple([sum(x) for x in zip(*[by_area[a][i] for a in region])] for i in (0, 1))
    nation = ["165", "167", "511"]
    by_area["0"] = tuple([sum(x) for x in zip(*[by_area[a][i] for a in nation])] for i in (0, 1))
    return by_area


def payload(var, var_labels, by_area, cell):
    areas = list(EN)
    first = list(var_labels)
    values = []
    for v in first:
        for a in areas:
            values.append(cell(v, by_area[a]))
    return {"id": [var, ma.REGION, ma.YEAR_VAR], "size": [len(first), len(areas), 1],
            "dimension": {
                var: {"category": {"index": {c: i for i, c in enumerate(first)},
                                   "label": var_labels}},
                ma.REGION: {"category": {"index": {c: i for i, c in enumerate(areas)},
                                         "label": EN}},
                ma.YEAR_VAR: {"category": {"index": {"2025": 0}, "label": {"2025": "2025"}}}},
            "value": values}


def sex_payload(by_area):
    def cell(v, mw):
        men, women = sum(mw[0]), sum(mw[1])
        return {"0": men + women, "1": men, "2": women}[v]
    return payload(ma.SEX_VAR, {"0": "Total", "1": " Male", "2": " Female"}, by_area, cell)


def age_payload(by_area):
    labels = {"0": "Total", **{str(i + 1): g for i, g in enumerate(GROUPS)}}

    def cell(v, mw):
        if v == "0":
            return sum(mw[0]) + sum(mw[1])
        i = int(v) - 1
        return mw[0][i] + mw[1][i]
    return payload(ma.AGE_VAR, labels, by_area, cell)


def drawn():
    admin1 = [{"id": "A-ark", "name": "Arkhangai"}, {"id": "A-hov", "name": "Hovsgel"},
              {"id": "A-ub", "name": "Ulaanbaatar"}]
    admin2 = [{"id": "S1", "name": "Erdenebulgan", "parent": "A-ark"},
              {"id": "S2", "name": "Ixtamir", "parent": "A-ark"},
              {"id": "S3", "name": "Mo'ron", "parent": "A-hov"},
              {"id": "S4", "name": "Bayanzu'rx", "parent": "A-ub"}]
    return admin1, admin2


def build(by_area=None, admin=None):
    by_area = by_area or tables()
    admin1, admin2 = admin or drawn()
    return ma.build(sex_payload(by_area), age_payload(by_area), EN, MN, admin1, admin2)


class Build(unittest.TestCase):
    def setUp(self):
        self.records = {r["shape_id"]: r for r in build()}

    def test_every_unit(self):
        self.assertEqual(sorted(self.records), ["A-ark", "A-hov", "A-ub", "S1", "S2", "S3", "S4"])

    def test_values(self):
        r = self.records["S2"]
        men, women = counts(1)
        self.assertEqual(r["population"]["value"], sum(men) + sum(women))
        self.assertEqual(r["sex_ratio"]["value"], round(100 * sum(men) / sum(women), 1))
        self.assertEqual(r["population"]["year"], 2025)
        self.assertIn("five-year group", r["median_age_note"])
        self.assertTrue(0 < r["median_age"]["value"] < 70)
        self.assertEqual(r["match_by"], "shape_id")

    def test_capital_district(self):
        self.assertIn("this district", self.records["S4"]["median_age_note"])
        self.assertEqual(self.records["A-hov"]["level"], "admin1")


class Refusals(unittest.TestCase):
    def test_soums_must_make_the_aimag(self):
        by_area = tables()
        by_area["16513"] = counts(2)
        with self.assertRaises(SystemExit):
            build(by_area)

    def test_unmatched_soum(self):
        admin1, admin2 = drawn()
        admin2[1]["name"] = "Somewhere"
        with self.assertRaises(SystemExit):
            build(admin=(admin1, admin2))

    def test_drawn_soum_the_office_does_not_list(self):
        admin1, admin2 = drawn()
        admin2.append({"id": "S5", "name": "Tariat", "parent": "A-ark"})
        with self.assertRaises(SystemExit):
            build(admin=(admin1, admin2))

    def test_group_bounds(self):
        self.assertEqual(ma.group_bounds("    65-69"), (65, 5))
        self.assertEqual(ma.group_bounds("    70+"), (70, None))
        self.assertIsNone(ma.group_bounds("Total"))


if __name__ == "__main__":
    unittest.main()
