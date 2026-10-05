"""China's counties from a provincial census yearbook, offline.

A Qinghai-like province laid out as the yearbooks' .xls files are: a title, a
地 区 header, the province, then each prefecture followed by its districts,
counties and (in one) a development zone, and a unit the province lists
outside every prefecture with the rows it is made of.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import china_county_census as cc  # noqa: E402

AGE_HEADS = ["0岁", "1-4岁"] + [f"{a}-{a + 4}岁" for a in range(5, 100, 5)] + ["100岁及以上"]
NATIONS = ["汉族", "蒙古族", "回族", "藏族", "维吾尔族", "苗族", "彝族", "壮族", "布依族", "朝鲜族",
           "满族", "侗族", "瑶族", "白族", "土家族", "哈尼族", "哈萨克族", "傣族", "黎族", "傈僳族",
           "佤族", "畲族", "高山族", "拉祜族", "水族", "东乡族", "纳西族", "景颇族", "柯尔克孜族",
           "土族", "达斡尔族", "仫佬族", "羌族", "布朗族", "撒拉族", "毛南族", "仡佬族", "锡伯族",
           "阿昌族", "普米族", "塔吉克族", "怒族", "乌孜别克族", "俄罗斯族", "鄂温克族", "德昂族",
           "保安族", "裕固族", "京族", "塔塔尔族", "独龙族", "鄂伦春族", "赫哲族", "门巴族",
           "珞巴族", "基诺族", "未定族称人口", "入籍"]

# (label, scale): every county's men and women by age are its scale times a
# fixed profile, so prefectures and the province add up by construction.
LEAVES = [("城东区", 5), ("大通回族土族自治县", 4), ("湟源县", 1),
          ("格尔木市", 3), ("德令哈市", 2), ("海西经济开发区", 1),
          ("玛沁县", 2), ("班玛县", 1),
          ("池北区", 1), ("池西区", 1)]
LAYOUT = [("全省", None), ("西宁市", ["城东区", "大通回族土族自治县", "湟源县"]),
          ("海西蒙古族藏族自治州", ["格尔木市", "德令哈市", "海西经济开发区"]),
          ("果洛藏族自治州", ["玛沁县", "班玛县"]),
          ("长白山管委会", ["池北区", "池西区"])]
NAMES = {"630000": ["青海省"], "630100": ["西宁市"], "630102": ["城东区"],
         "630121": ["大通回族土族自治县"], "630123": ["湟源县"],
         "632800": ["海西蒙古族藏族自治州"], "632801": ["格尔木市"], "632802": ["德令哈市"],
         "632600": ["果洛藏族自治州"], "632621": ["玛沁县"], "632622": ["班玛县"]}
CODE_SHAPES = {"630102": {"shape_id": "S-CHENGDONG"}, "630121": {"shape_id": "S-DATONG"},
               "630123": {"shape_id": "S-HUANGYUAN"}, "632801": {"shape_id": "S-GOLMUD"},
               "632802": {"shape_id": "S-DELINGHA"}, "632621": {"shape_id": "S-MAQEN"},
               "632622": {"shape_id": "S-BAIMA"}}
SEATS = {"S-CHENGDONG": ["630102"], "S-DATONG": ["630121"], "S-HUANGYUAN": ["630123"],
         "S-GOLMUD": ["632801"], "S-DELINGHA": ["632802"], "S-MAQEN": ["632621", "632623"],
         "S-BAIMA": ["632622"]}


def sexes(scale):
    men = [scale * (50 + (10 if a < 12 else 22 - a)) for a in range(len(AGE_HEADS))]
    women = [scale * (48 + (10 if a < 12 else 24 - a)) for a in range(len(AGE_HEADS))]
    return [max(m, 1) for m in men], [max(w, 1) for w in women]


def summed(labels):
    parts = [sexes(dict(LEAVES)[name]) for name in labels]
    men = [sum(p[0][k] for p in parts) for k in range(len(AGE_HEADS))]
    women = [sum(p[1][k] for p in parts) for k in range(len(AGE_HEADS))]
    return men, women


def areas():
    """[(label, (men, women))] in the yearbook's order."""
    every = [name for name, _ in LEAVES]
    out = [("全省", summed(every))]
    for head, kids in LAYOUT[1:]:
        out.append((head, summed(kids)))
        out += [(kid, sexes(dict(LEAVES)[kid])) for kid in kids]
    return out


def spaced(text):
    return " ".join(text)


def a0101():
    rows = [["1-1 各地区户数、人口数和性别比"], [""], [""],
            ["地 区", "户 数", "", "", "合 计"], ["", "合计", "家庭户", "集体户", "合 计"],
            ["", "", "", "", "合计", "男", "女", "性别比"], [""]]
    for name, (men, women) in areas():
        m, w = sum(men), sum(women)
        rows.append([name, 1.0, 1.0, 0.0, float(m + w), float(m), float(w), round(100 * m / w, 2)])
    return rows


def a0105():
    header = ["地 区", "合 计", "", ""] + sum([[spaced(h), "", ""] for h in AGE_HEADS], [])
    rows = [["1-5 各地区分年龄、性别的人口"], [""], [""], header,
            [""] + ["小计", "男", "女"] * (len(AGE_HEADS) + 1)]
    for name, (men, women) in areas():
        row = [name, float(sum(men) + sum(women)), float(sum(men)), float(sum(women))]
        for m, w in zip(men, women):
            row += [float(m + w), float(m), float(w)]
        rows.append(row)
    return rows


def a0104():
    header = ["地 区", "合 计", "", ""] + sum([[spaced(h), "", ""] for h in NATIONS], [])
    rows = [["1-4 各地区分性别、民族的人口"], [""], [""], header]
    for name, (men, women) in areas():
        m, w = sum(men), sum(women)
        # Nine in ten Han, a twentieth Tibetan, the rest Hui.
        split = [(m * 9 // 10, w * 9 // 10), (0, 0), (0, 0), (m // 20, w // 20)]
        rest = (m - sum(a for a, _ in split), w - sum(b for _, b in split))
        split[2] = rest
        parts = [(m, w)] + split + [(0, 0)] * (len(NATIONS) - 4)
        row = [name]
        for a, b in parts:
            row += [float(a + b), float(a), float(b)]
        rows.append(row)
    return rows


def tables():
    return {"A0101": a0101(), "A0104": a0104(), "A0105": a0105()}


def units():
    admin1 = [{"id": "P-QH", "name": "Qinghai Province"}]
    admin2 = [{"id": sid, "name": f"drawn {sid[2:].title()}", "parent": "P-QH"}
              for sid in SEATS]
    return admin1, admin2


class Hierarchy(unittest.TestCase):
    def setUp(self):
        self.areas, self.a0101, _, _ = cc.read_province("63", tables(), NAMES)
        self.by_label = {a["label"]: a for a in self.areas}

    def test_kinds(self):
        kinds = {a["label"]: a["kind"] for a in self.areas}
        self.assertEqual(kinds["全省"], "province")
        self.assertEqual(kinds["西宁市"], "prefecture")
        self.assertEqual(kinds["大通回族土族自治县"], "county")
        self.assertEqual(kinds["海西经济开发区"], "special")
        self.assertEqual(kinds["长白山管委会"], "special")
        self.assertEqual(self.by_label["池北区"]["head"], self.by_label["长白山管委会"]["index"])

    def test_codes(self):
        self.assertEqual(self.by_label["湟源县"]["code"], "630123")
        self.assertEqual(self.by_label["湟源县"]["prefecture"], "630100")
        self.assertIsNone(self.by_label["海西经济开发区"]["code"])

    def test_a_prefecture_that_does_not_add_up_is_refused(self):
        t = tables()
        for table in t.values():
            for row in table:
                if row and row[0] == "湟源县":
                    row[1] = row[1] + 1
                    if table is t["A0101"]:
                        row[4] += 1
                        row[5] += 1
        with self.assertRaises(SystemExit):
            cc.read_province("63", t, NAMES)

    def test_tables_must_list_the_same_areas(self):
        t = tables()
        t["A0105"] = [r for r in t["A0105"] if not r or r[0] != "班玛县"]
        with self.assertRaises(SystemExit):
            cc.read_province("63", t, NAMES)


class Binding(unittest.TestCase):
    def build(self, **changes):
        admin1, admin2 = units()
        for unit in admin2:
            unit.update(changes.get(unit["id"], {}))
        cut = {"长白山管委会": (("6326",), "the test's zone, cut from Golog")}
        saved = dict(cc.CUT_FROM)
        cc.CUT_FROM.clear()
        cc.CUT_FROM.update(cut)
        try:
            return {r["shape_id"]: r for r in cc.build("63", tables(), NAMES, CODE_SHAPES, SEATS,
                                                      admin1, admin2)}
        finally:
            cc.CUT_FROM.clear()
            cc.CUT_FROM.update(saved)

    def test_only_counties_that_are_still_their_polygon(self):
        records = self.build()
        # Datong and Huangyuan pass; Chengdong is a district; Golmud and
        # Delingha share Haixi with a development zone; Golog's counties are
        # in the prefecture the province-level zone was cut from.
        self.assertEqual(sorted(records), ["S-DATONG", "S-HUANGYUAN"])

    def test_a_record(self):
        r = self.build()["S-DATONG"]
        men, women = sexes(4)
        self.assertEqual(r["population"]["value"], sum(men) + sum(women))
        self.assertEqual(r["sex_ratio"]["value"], round(100 * sum(men) / sum(women), 1))
        self.assertEqual(r["sex_ratio"]["unit"], "males_per_100_females")
        self.assertIsNotNone(r["median_age"]["value"])
        self.assertEqual(r["codes"], {"gb2260": "630121"})
        self.assertEqual(r["aliases"], ["大通回族土族自治县"])
        self.assertEqual(r["match_by"], "shape_id")
        self.assertEqual(r["parent"], "CHN-Qinghai Province")
        groups = {g["group"]: g["pct"] for g in r["ethnicity"]}
        self.assertEqual(groups["Han Chinese"], 90.0)
        self.assertAlmostEqual(sum(groups.values()), 100.0, places=6)
        self.assertEqual(sum(g["count"] for g in r["ethnicity"]), r["population"]["value"])
        self.assertEqual(r["language"]["status"], "not_collected")

    def test_a_jump_from_an_older_figure_is_not_bound(self):
        records = self.build(**{"S-DATONG": {"population": {"value": 20_000, "year": 2010}}})
        self.assertNotIn("S-DATONG", records)
        records = self.build(**{"S-DATONG": {"population": {"value": 9_000, "year": 2010}}})
        self.assertIn("S-DATONG", records)

    def test_a_polygon_holding_two_seats_is_not_bound(self):
        cut = {"长白山管委会": (("6399",), "elsewhere")}
        admin1, admin2 = units()
        saved = dict(cc.CUT_FROM)
        cc.CUT_FROM.clear()
        cc.CUT_FROM.update(cut)
        try:
            records = {r["shape_id"] for r in cc.build("63", tables(), NAMES, CODE_SHAPES, SEATS,
                                                      admin1, admin2)}
        finally:
            cc.CUT_FROM.clear()
            cc.CUT_FROM.update(saved)
        self.assertIn("S-BAIMA", records)
        self.assertNotIn("S-MAQEN", records)

    def test_an_unexplained_zone_outside_every_prefecture_is_refused(self):
        admin1, admin2 = units()
        saved = dict(cc.CUT_FROM)
        cc.CUT_FROM.clear()
        try:
            with self.assertRaises(SystemExit):
                cc.build("63", tables(), NAMES, CODE_SHAPES, SEATS, admin1, admin2)
        finally:
            cc.CUT_FROM.update(saved)

    def test_the_province_must_be_the_national_bureau_s_count(self):
        admin1, admin2 = units()
        with self.assertRaises(SystemExit):
            cc.build("63", tables(), NAMES, CODE_SHAPES, SEATS, admin1, admin2, national=1.0)


class Kinds(unittest.TestCase):
    def test_what_a_row_below_a_prefecture_is(self):
        self.assertEqual(cc.kind_of("南关区", "220102"), "district")
        # An autonomous prefecture numbers its county-level cities from 01.
        self.assertEqual(cc.kind_of("延吉市", "222401"), "county")
        self.assertEqual(cc.kind_of("长春经济技术开发区", "220171"), "zone")
        self.assertEqual(cc.kind_of("长春莲花山生态旅游度假区", None), "zone")
        self.assertEqual(cc.kind_of("神农架林区", "429021"), "county")
        self.assertEqual(cc.kind_of("大通回族土族自治县", "630121"), "county")


class Names(unittest.TestCase):
    def test_a_county_made_a_district_since_meets_its_row_by_stem(self):
        names = {"630100": ["西宁市"], "630122": ["湟中区"]}
        self.assertEqual(cc.code_of("湟中县", "6301", names, "county"), "630122")

    def test_an_ambiguous_name_binds_nothing(self):
        names = {"630102": ["城东区"], "630103": ["城东区"]}
        self.assertIsNone(cc.code_of("城东区", "6301", names, "county"))


if __name__ == "__main__":
    unittest.main()
