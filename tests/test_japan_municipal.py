"""Japan's municipalities: binding, unions, slivers and the self-checks, offline.

The tables are synthetic but shaped exactly as e-Stat serves them: area codes
with e-Stat's levels, 0004019309's age classes 00-21 by sex, 0003445244's 国籍
codes. Every prefecture holds one city, except Gunma, whose two municipalities
the boundary file draws as one polygon (the Numata case), and Okinawa, whose
city is bound by the hand table rather than by code_shapes.
"""

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import japan_municipal as jm  # noqa: E402
from scripts.fetch_census.japan import NATIONALITY_CODES, PREFECTURES  # noqa: E402

NATIONAL = "00000"
AGES = [f"{i:02d}" for i in range(1, 22)]


def age_rows(scale: int) -> dict[str, dict[str, int]]:
    """Men and women by five-year group: a gently ageing pyramid."""
    out = {}
    for sex, tilt in (("1", 0), ("2", 1)):
        row = {a: scale * (10 + (i if i < 14 else 27 - i)) + tilt * scale * (i > 15)
               for i, a in enumerate(AGES)}
        row["21"] = scale
        row["00"] = sum(row[a] for a in AGES)
        out[sex] = row
    return out


def nat_row(total: int) -> dict[str, int]:
    foreign = {c: 0 for c in NATIONALITY_CODES if c != "2"}
    foreign["101"], foreign["102"], foreign["111"] = total // 100, total // 50, total // 200
    unknown = total // 40
    japanese = total - sum(foreign.values()) - unknown
    return {"0": total, "1": sum(foreign.values()), "2": japanese, "3": unknown, **foreign}


def add(rows):
    out = copy.deepcopy(rows[0])
    for r in rows[1:]:
        for sex in ("1", "2"):
            for k, v in r[sex].items():
                out[sex][k] += v
    return out


def add_nat(rows):
    return {k: sum(r[k] for r in rows) for k in rows[0]}


def fixture():
    ages, nat, median, levels = {}, {}, {}, {NATIONAL: ("1", "全国")}
    code_shapes, admin1, admin2 = {}, [], []
    for pref, (jp, name) in PREFECTURES.items():
        admin1.append({"id": f"P{pref}", "name": name})
        levels[pref] = ("2", jp)
        if pref == "10000":
            parts = {"10206": ("4", "沼田市", 3), "10448": ("6", "昭和村", 1)}
        else:
            parts = {pref[:2] + "201": ("4", f"{jp}市", 2)}
        for code, (level, jname, scale) in parts.items():
            levels[code] = (level, jname)
            ages[code] = age_rows(scale)
            nat[code] = nat_row(ages[code]["1"]["00"] + ages[code]["2"]["00"])
            median[code] = jm.grouped(ages, (code,))
            if pref not in ("10000", "47000"):
                code_shapes[code] = {"shape_id": f"S{code}", "level": "admin2",
                                     "name": f"Muni{code}"}
                admin2.append({"id": f"S{code}", "name": f"Muni{code}"})
        ages[pref] = add([ages[c] for c in parts])
        nat[pref] = add_nat([nat[c] for c in parts])
        median[pref] = jm.grouped(ages, (pref,))
    prefs = [p for p in PREFECTURES]
    ages[NATIONAL] = add([ages[p] for p in prefs])
    nat[NATIONAL] = add_nat([nat[p] for p in prefs])
    median[NATIONAL] = sorted(median[p] for p in prefs)[23]
    admin2 += [{"id": "SNUMATA", "name": "Numata"}, {"id": "SSLIVER", "name": "SSLIVER"},
               {"id": "SNAHA", "name": "Nahaa"}]
    extra = {"SNAHA": ("47201", "Naha")}
    unions = {"SNUMATA": (("10206", "10448"), "Numata", "Numata takes in Showa.")}
    slivers = {"SSLIVER": "A sliver, no census area."}
    return dict(median=median, ages=ages, nat=nat, levels=levels, code_shapes=code_shapes,
                admin1=admin1, admin2=admin2, extra=extra, unions=unions, slivers=slivers)


def build(f):
    return jm.build(f["median"], f["ages"], f["nat"], f["levels"], f["code_shapes"],
                    f["admin1"], f["admin2"], extra=f["extra"], unions=f["unions"],
                    slivers=f["slivers"])


class Build(unittest.TestCase):
    def setUp(self):
        self.f = fixture()
        self.records = build(self.f)
        self.by_shape = {r.get("shape_id"): r for r in self.records}

    def test_counts(self):
        levels = [r["level"] for r in self.records]
        self.assertEqual(levels.count("admin1"), 47)
        self.assertEqual(levels.count("admin2"), len(self.f["admin2"]))

    def test_union_sums_and_interpolates(self):
        r = self.by_shape["SNUMATA"]
        ages = self.f["ages"]
        total = sum(ages[c][s]["00"] for c in ("10206", "10448") for s in "12")
        self.assertEqual(r["population"]["value"], total)
        men = ages["10206"]["1"]["00"] + ages["10448"]["1"]["00"]
        women = ages["10206"]["2"]["00"] + ages["10448"]["2"]["00"]
        self.assertEqual(r["sex_ratio"]["value"], round(100 * men / women, 1))
        self.assertEqual(r["sex_ratio"]["unit"], "males_per_100_females")
        self.assertEqual(r["median_age"]["value"], jm.grouped(ages, ("10206", "10448")))
        self.assertIn("Showa", r["median_age_note"])
        self.assertEqual(r["codes"]["jis"], "10206+10448")
        self.assertEqual(r["aliases"], ["沼田市", "昭和村"])

    def test_nationality_is_a_composition(self):
        r = self.by_shape["S01201"]
        self.assertEqual(r["ethnicity_basis"], "nationality")
        self.assertAlmostEqual(sum(g["pct"] for g in r["ethnicity"]), 100.0, places=6)
        groups = {g["group"] for g in r["ethnicity"]}
        self.assertIn("Japanese", groups)
        self.assertIn("Korean", groups)
        self.assertIn("left out", r["ethnicity_note"])
        self.assertEqual(r["religion"]["status"], "not_collected")
        self.assertEqual(r["language"]["status"], "not_collected")

    def test_published_median_is_used(self):
        r = self.by_shape["S01201"]
        self.assertEqual(r["median_age"]["value"], self.f["median"]["01201"])
        self.assertNotIn("median_age_note", r)

    def test_hand_binding_renames_and_keeps_the_label(self):
        r = self.by_shape["SNAHA"]
        self.assertEqual(r["name"], "Naha")
        self.assertEqual(r["aliases"][0], "Nahaa")
        self.assertEqual(r["match_by"], "shape_id")

    def test_sliver_is_a_stated_gap(self):
        r = self.by_shape["SSLIVER"]
        self.assertEqual(r["population"]["status"], "not_available")
        self.assertIn("sliver", r["population"]["note"])

    def test_prefectures_carry_age_and_sex_only(self):
        r = self.by_shape["P13000"]
        self.assertEqual(r["level"], "admin1")
        self.assertEqual(r["median_age"]["value"], self.f["median"]["13000"])
        self.assertEqual(r["population"]["status"], "not_available")


class Refusals(unittest.TestCase):
    def test_code_bound_twice(self):
        f = fixture()
        f["extra"]["SNAHA"] = ("01201", "Sapporo")
        with self.assertRaises(SystemExit):
            build(f)

    def test_extra_contradicting_code_shapes(self):
        f = fixture()
        f["extra"]["S01201"] = ("01999", "Nowhere")
        with self.assertRaises(SystemExit):
            build(f)

    def test_unbound_polygon(self):
        f = fixture()
        f["admin2"].append({"id": "SLOST", "name": "Lost"})
        with self.assertRaises(SystemExit):
            build(f)

    def test_age_groups_must_add_up(self):
        f = fixture()
        f["ages"]["02201"]["1"]["05"] += 1
        with self.assertRaises(SystemExit):
            build(f)

    def test_nationalities_must_add_up(self):
        f = fixture()
        f["nat"]["03201"]["102"] += 1
        with self.assertRaises(SystemExit):
            build(f)

    def test_municipalities_must_add_to_prefecture(self):
        f = fixture()
        f["levels"]["04201"] = ("5", "区")      # read as a ward, so not counted
        with self.assertRaises(SystemExit):
            build(f)

    def test_a_ward_is_not_a_municipality(self):
        f = fixture()
        f["levels"]["05201"] = ("5", "区")
        f["levels"]["05202"] = ("4", "x")
        f["nat"]["05202"] = f["nat"]["05201"]
        with self.assertRaises(SystemExit):
            build(f)

    def test_grouped_median_must_track_the_bureau(self):
        f = fixture()
        for code in list(f["median"]):
            if not code.endswith("000"):
                f["median"][code] += 2.0
        with self.assertRaises(SystemExit):
            build(f)

    def test_undrawn_bound_shape(self):
        f = fixture()
        f["admin2"] = [u for u in f["admin2"] if u["id"] != "S02201"]
        with self.assertRaises(SystemExit):
            build(f)


class Helpers(unittest.TestCase):
    def test_grouped_median(self):
        groups = {"1": {a: 0 for a in AGES}, "2": {a: 0 for a in AGES}}
        groups["1"]["01"] = 10          # 0-4
        groups["1"]["02"] = 10          # 5-9
        groups["1"]["00"] = 20
        groups["2"]["00"] = 0
        self.assertEqual(jm.grouped({"x": groups}, ("x",)), 5.0)

    def test_area_levels(self):
        payload = {"GET_META_INFO": {"RESULT": {"STATUS": 0}, "METADATA_INF": {"CLASS_INF": {
            "CLASS_OBJ": [{"@id": "cat01", "CLASS": []},
                          {"@id": "area", "CLASS": [
                              {"@code": "01100", "@name": "札幌市", "@level": "4"},
                              {"@code": "01101", "@name": "札幌市中央区", "@level": "5"}]}]}}}}
        self.assertEqual(jm.area_levels(payload),
                         {"01100": ("4", "札幌市"), "01101": ("5", "札幌市中央区")})

    def test_extra_table_is_one_to_one(self):
        codes = [c for c, _ in jm.EXTRA_SHAPES.values()]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(len(jm.EXTRA_SHAPES), 144)
        for shape in jm.UNIONS:
            self.assertNotIn(shape, jm.EXTRA_SHAPES)


if __name__ == "__main__":
    unittest.main()
