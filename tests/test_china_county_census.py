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


def figures(records):
    """The shapes given a count, apart from those only told why not."""
    return sorted(s for s, r in records.items() if "value" in r["population"])


def without_zone(table):
    """A table with Haixi's development zone taken out of it and out of the
    prefecture's and the province's totals, so Haixi's counties are
    candidates."""
    zone = next(r for r in table if r and r[0] == "海西经济开发区")
    out = []
    for row in table:
        if row and row[0] == "海西经济开发区":
            continue
        if row and row[0] in ("海西蒙古族藏族自治州", "全省"):
            row = [row[0]] + [a - b if isinstance(a, float) else a
                              for a, b in zip(row[1:], zone[1:])]
        out.append(row)
    return out


class Binding(unittest.TestCase):
    def build(self, code_shapes=None, seat_names=None, cut=None, tables_=None, ground=None,
              towns=None, **changes):
        admin1, admin2 = units()
        for unit in admin2:
            unit.update(changes.get(unit["id"], {}))
        cut = cut or {"长白山管委会": (("6326",), "the test's zone, cut from Golog")}
        saved = dict(cc.CUT_FROM)
        cc.CUT_FROM.clear()
        cc.CUT_FROM.update(cut)
        try:
            return {r["shape_id"]: r for r in cc.build(
                "63", tables_ or tables(), NAMES,
                CODE_SHAPES if code_shapes is None else code_shapes, SEATS, admin1, admin2,
                seat_names=seat_names, ground=ground, towns=towns)}
        finally:
            cc.CUT_FROM.clear()
            cc.CUT_FROM.update(saved)

    # Test 6: Datong's own townships and Chengdong's, placed.
    TOWNS = {"630121": {"name": "大通回族土族自治县",
                        "townships": [["630121100", "桥头镇", "S-DATONG", ["S-DATONG"]],
                                      ["630121101", "城关镇", "S-DATONG", ["S-DATONG"]],
                                      ["630121200", "新庄镇"]]},
             "630123": {"name": "湟源县",
                        "townships": [["630123100", "城关镇", "S-HUANGYUAN", ["S-HUANGYUAN"]]]},
             "630102": {"name": "城东区",
                        "townships": [["630102001", "东关大街街道", "S-CHENGDONG",
                                       ["S-CHENGDONG"]]]}}

    def towns(self):
        return {k: {"name": v["name"], "townships": [list(r) for r in v["townships"]]}
                for k, v in self.TOWNS.items()}

    def test_a_polygon_holding_its_own_townships_only_is_bound(self):
        records = self.build(towns=self.towns())
        self.assertEqual(figures(records), ["S-DATONG", "S-HUANGYUAN"])
        self.assertIn("its townships of 2020 stand in it and no other unit's does (2 of its 3 "
                      "townships", records["S-DATONG"]["population_note"])

    def test_another_unit_s_township_deep_inside_refuses_the_polygon(self):
        towns = self.towns()
        towns["630102"]["townships"].append(["630102101", "韵家口镇", "S-DATONG", ["S-DATONG"]])
        records = self.build(towns=towns)
        self.assertEqual(figures(records), ["S-HUANGYUAN"])
        note = records["S-DATONG"]["population"]["note"]
        self.assertIn("韵家口镇, which the codes list under 城东区 (630102), stands inside it", note)
        # Near the line, where the boundary file's generalisation could have
        # put it on either side, it proves nothing.
        towns["630102"]["townships"][-1][3] = ["S-CHENGDONG", "S-DATONG"]
        self.assertEqual(figures(self.build(towns=towns)), ["S-DATONG", "S-HUANGYUAN"])

    def test_its_own_township_far_outside_refuses_the_polygon(self):
        towns = self.towns()
        towns["630123"]["townships"].append(["630123101", "大华镇", "S-DATONG", ["S-DATONG"]])
        records = self.build(towns=towns)
        self.assertNotIn("S-HUANGYUAN", figures(records))
        self.assertIn("its own township 大华镇 stands more than 3 km outside it",
                      records["S-HUANGYUAN"]["population"]["note"])
        # Huangyuan's township deep inside Datong refuses Datong too.
        self.assertNotIn("S-DATONG", figures(records))

    def test_a_county_the_codes_still_number_otherwise_is_found_by_name(self):
        # The 2020 codes kept the county's old code; its own townships are
        # still its own under it, and a stray one still refuses it.
        towns = self.towns()
        towns["630199"] = towns.pop("630121")
        records = self.build(towns=towns)
        self.assertIn("(2 of its 3 townships", records["S-DATONG"]["population_note"])
        towns["630102"]["townships"].append(["630102101", "韵家口镇", "S-DATONG", ["S-DATONG"]])
        self.assertNotIn("S-DATONG", figures(self.build(towns=towns)))

    def test_only_counties_that_are_still_their_polygon(self):
        records = self.build()
        # Datong and Huangyuan pass; Chengdong is a district; Golmud and
        # Delingha share Haixi with a development zone; Golog's counties are
        # in the prefecture the province-level zone was cut from.
        self.assertEqual(figures(records), ["S-DATONG", "S-HUANGYUAN"])

    def test_a_polygon_refused_for_a_zone_says_why(self):
        records = self.build()
        golmud = records["S-GOLMUD"]
        self.assertEqual(golmud["population"]["status"], "not_available")
        self.assertIn("海西经济开发区", golmud["population"]["note"])
        self.assertIn("格尔木市 (632801)", golmud["population"]["note"])
        self.assertEqual(golmud["ethnicity"], golmud["population"])
        self.assertIn("cut from Golog", records["S-BAIMA"]["median_age"]["note"])
        # A district's polygon and one holding two seats are told nothing:
        # whose reason would it be?
        self.assertNotIn("S-CHENGDONG", records)
        self.assertNotIn("S-MAQEN", records)

    def test_the_drift_is_measured_against_the_province_s_counties(self):
        # Five comparable counties: four lost the province's usual 30 per
        # cent since their polygon's figure, Huangyuan lost three-fifths --
        # far outside its province, though inside an absolute band wide
        # enough for the north-east's decline.
        totals = {name: sum(m) + sum(w) for name, (m, w) in areas()}
        labels = {"S-DATONG": "大通回族土族自治县", "S-HUANGYUAN": "湟源县",
                  "S-GOLMUD": "格尔木市", "S-DELINGHA": "德令哈市", "S-BAIMA": "班玛县"}
        older = {sid: {"population": {"value": round(totals[label] / (0.4 if sid == "S-HUANGYUAN"
                                                                       else 0.7)),
                                      "year": 2010, "source": "Wikidata (CC0)"}}
                 for sid, label in labels.items()}
        records = self.build(cut={"长白山管委会": (("6399",), "elsewhere")},
                             tables_={k: without_zone(v) for k, v in tables().items()}, **older)
        self.assertEqual(figures(records), ["S-BAIMA", "S-DATONG", "S-DELINGHA", "S-GOLMUD"])
        self.assertIn("0.57 of the median ratio", records["S-HUANGYUAN"]["population"]["note"])
        self.assertIn("1.00 of the median ratio of the province's 5 comparable counties",
                      records["S-DATONG"]["population_note"])

    def test_a_lone_seat_named_in_pinyin_is_bound_without_code_shapes(self):
        shapes = {k: v for k, v in CODE_SHAPES.items() if k != "630121"}
        named = {"S-DATONG": {"code": "630121", "label": "Datonghuizutuzuzizhixian",
                              "zh": "大通回族土族自治县", "agreement": 0.98}}
        records = self.build(code_shapes=shapes, seat_names=named)
        self.assertIn("S-DATONG", figures(records))
        self.assertIn("Datonghuizutuzuzizhixian is 大通回族土族自治县 in pinyin",
                      records["S-DATONG"]["population_note"])
        weak = {"S-DATONG": {**named["S-DATONG"], "agreement": 0.85}}
        self.assertNotIn("S-DATONG", figures(self.build(code_shapes=shapes, seat_names=weak)))
        self.assertNotIn("S-DATONG", figures(self.build(code_shapes=shapes)))

    def test_a_misspelling_checked_by_hand_is_bound(self):
        self.assertEqual(cc.MISSPELT["220382"][0], "Suanliaoxian")
        lone = {"220382": ("S-X", {"code": "220382", "label": "Suanliaoxian", "zh": "双辽市",
                                   "agreement": 0.889})}
        shape, how = cc.polygon_for("220382", {}, lone)
        self.assertEqual(shape, "S-X")
        self.assertIn("Shuangliao", how)
        lone = {"653229": ("S-Y", {"code": "653229", "label": "Hetianxian", "zh": "和安县",
                                   "agreement": 0.889})}
        self.assertIsNone(cc.polygon_for("653229", {}, lone)[0])
        # Henan's polygon carries a copy of Banma's label; it is Henan's
        # only under that exact label.
        lone = {"632324": ("S-Z", {"code": "632324", "label": "Banmaxian",
                                   "zh": "河南蒙古族自治县", "agreement": 0.452})}
        shape, how = cc.polygon_for("632324", {}, lone)
        self.assertEqual(shape, "S-Z")
        self.assertIn("a copy of its neighbour Banma's", how)
        lone["632324"][1]["label"] = "Banmashi"
        self.assertIsNone(cc.polygon_for("632324", {}, lone)[0])

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
        self.assertEqual(r["language"]["status"], "not_available")

    def test_a_province_without_its_age_table_keeps_the_rest(self):
        # Inner Mongolia's Table 1-5: the bureau answers 403 and the Archive
        # never captured it. Tables 1-1 and 1-4 still bind; the median age
        # is a stated gap naming who refused.
        admin1, admin2 = units()
        cut = {"长白山管委会": (("6326",), "the test's zone, cut from Golog")}
        saved = dict(cc.CUT_FROM)
        cc.CUT_FROM.clear()
        cc.CUT_FROM.update(cut)
        why = ("china_county_census: http://x/A0105.xls could not be read (live: HTTPError: "
               "HTTP Error 403: Forbidden; no capture in the Internet Archive)")
        try:
            records = {r["shape_id"]: r for r in cc.build(
                "63", {k: v for k, v in tables().items() if k != "A0105"}, NAMES, CODE_SHAPES,
                SEATS, admin1, admin2, missing={"A0105": why})}
        finally:
            cc.CUT_FROM.clear()
            cc.CUT_FROM.update(saved)
        self.assertEqual(figures(records), ["S-DATONG", "S-HUANGYUAN"])
        r = records["S-DATONG"]
        self.assertIsNotNone(r["population"]["value"])
        self.assertEqual(r["median_age"]["status"], "not_available")
        self.assertIn("the bureau's server refused it (HTTP 403) and the Internet Archive holds "
                      "no capture of it", r["median_age"]["note"])
        self.assertEqual([s["field"] for s in r["sources"]], ["population/sex_ratio", "ethnicity"])

    def test_a_jump_from_an_older_figure_is_not_bound(self):
        # One comparable county: the absolute band.
        records = self.build(**{"S-DATONG": {"population": {"value": 20_000, "year": 2010}}})
        self.assertNotIn("S-DATONG", figures(records))
        self.assertIn("0.51 times", records["S-DATONG"]["population"]["note"])
        records = self.build(**{"S-DATONG": {"population": {"value": 9_000, "year": 2010}}})
        self.assertIn("S-DATONG", figures(records))
        self.assertIn("1.12 times the polygon's 2010 figure",
                      records["S-DATONG"]["population_note"])

    def test_a_polygon_holding_two_seats_is_not_bound(self):
        cut = {"长白山管委会": (("6399",), "elsewhere")}
        admin1, admin2 = units()
        saved = dict(cc.CUT_FROM)
        cc.CUT_FROM.clear()
        cc.CUT_FROM.update(cut)
        try:
            records = figures({r["shape_id"]: r for r in cc.build(
                "63", tables(), NAMES, CODE_SHAPES, SEATS, admin1, admin2)})
        finally:
            cc.CUT_FROM.clear()
            cc.CUT_FROM.update(saved)
        self.assertIn("S-BAIMA", records)
        self.assertNotIn("S-MAQEN", records)

    @staticmethod
    def ground(*townships):
        """china_zones' placement of Haixi's development zone: one entry per
        township, (name, the polygon it stands in, the polygons near it), a
        township without a polygon having no point."""
        out = []
        for name, shape, near in townships:
            entry = {"code": "632871100", "name": name, "how": "its code"}
            if shape is not None:
                entry.update(lon=95.0, lat=36.0, shape=shape, near=near)
            out.append(entry)
        return {"632871": {"name": "海西经济开发区", "listing": "the codes, 2020 edition",
                           "townships": out}}

    def test_a_placed_zone_refuses_only_the_polygon_it_stands_on(self):
        ground = self.ground(("察尔汗镇", "S-GOLMUD", ["S-GOLMUD"]),
                             ("工业园街道", "S-GOLMUD", ["S-GOLMUD"]))
        records = self.build(ground=ground)
        self.assertEqual(figures(records), ["S-DATONG", "S-DELINGHA", "S-HUANGYUAN"])
        golmud = records["S-GOLMUD"]["population"]["note"]
        self.assertIn("海西经济开发区's townships 察尔汗镇、工业园街道 stand on it", golmud)
        note = records["S-DELINGHA"]["population_note"]
        self.assertIn("no special unit the yearbook counts apart stands on it: the 2 townships "
                      "of 海西经济开发区 (the codes, 2020 edition), each placed", note)

    def test_a_township_near_a_polygon_refuses_it_too(self):
        ground = self.ground(("察尔汗镇", "S-GOLMUD", ["S-DELINGHA", "S-GOLMUD"]))
        self.assertEqual(figures(self.build(ground=ground)), ["S-DATONG", "S-HUANGYUAN"])

    def test_a_zone_with_a_township_that_has_no_point_refuses_the_prefecture(self):
        ground = self.ground(("察尔汗镇", "S-GOLMUD", ["S-GOLMUD"]), ("新区街道", None, None))
        records = self.build(ground=ground)
        self.assertEqual(figures(records), ["S-DATONG", "S-HUANGYUAN"])
        note = records["S-DELINGHA"]["population"]["note"]
        self.assertIn("1 of 海西经济开发区's 2 townships has no point to place it by (新区街道)",
                      note)

    def test_a_zone_the_codes_do_not_list_refuses_the_prefecture(self):
        ground = self.ground(("察尔汗镇", "S-GOLMUD", ["S-GOLMUD"]))
        ground["632871"]["name"] = "柴达木循环经济试验区"
        records = self.build(ground=ground)
        self.assertEqual(figures(records), ["S-DATONG", "S-HUANGYUAN"])
        self.assertIn("is not among the units the statistical division codes list",
                      records["S-DELINGHA"]["population"]["note"])

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


class BlankNationalities(unittest.TestCase):
    """Inner Mongolia's Table 1-4 leaves a nationality nobody in an area
    belongs to blank."""

    @staticmethod
    def blanked(drop_people=False):
        t = tables()
        for row in t["A0104"]:
            if row and row[0] == "西宁市":
                # Every zero cell left empty; with drop_people, a cell of
                # people too, which the groups' sum must then refuse.
                for k in range(4, len(row)):
                    if row[k] == 0.0:
                        row[k] = ""
                if drop_people:
                    row[13] = ""
        return t

    def test_an_empty_cell_is_nobody(self):
        areas, _, a0104, _ = cc.read_province("63", self.blanked(), NAMES)
        xining = next(a for a in areas if a["label"] == "西宁市")["index"]
        self.assertEqual(sum(a0104[xining]["groups"].values()), a0104[xining]["total"])

    def test_an_empty_cell_of_people_is_refused(self):
        with self.assertRaises(SystemExit):
            cc.read_province("63", self.blanked(drop_people=True), NAMES)


class OnlyTableOneByCounty(unittest.TestCase):
    """Hebei's yearbook: Table 1-1 by county, Tables 1-4 and 1-5 by
    prefecture only, and a subtotal row for a prefecture without the city the
    province administers itself."""

    def test_population_and_sex_ratio_with_the_other_fields_said_why(self):
        rows = a0101()
        at = next(k for k, r in enumerate(rows) if r and r[0] == "西宁市")
        subtotal = list(rows[at])
        subtotal[0] = "西宁市①"
        subtotal[4] -= 5.0
        rows.insert(at + 1, subtotal)
        admin1, admin2 = units()
        saved = dict(cc.CUT_FROM)
        cc.CUT_FROM.clear()
        cc.CUT_FROM.update({"长白山管委会": (("6326",), "the test's zone, cut from Golog")})
        try:
            records = {r["shape_id"]: r for r in cc.build(
                "63", {"A0101": rows}, NAMES, CODE_SHAPES, SEATS, admin1, admin2,
                missing={"A0104": cc.PREFECTURE_ONLY, "A0105": cc.PREFECTURE_ONLY})}
        finally:
            cc.CUT_FROM.clear()
            cc.CUT_FROM.update(saved)
        datong = records["S-DATONG"]
        totals = {name: sum(m) + sum(w) for name, (m, w) in areas()}
        self.assertEqual(datong["population"]["value"], totals["大通回族土族自治县"])
        self.assertIn("value", datong["sex_ratio"])
        for field, table in (("ethnicity", "1-4"), ("median_age", "1-5")):
            self.assertEqual(datong[field]["status"], "not_available")
            self.assertIn(f"(Table {table}) by prefecture only", datong[field]["note"])
        self.assertEqual([s["field"] for s in datong["sources"]], ["population/sex_ratio"])


class ZoneNames(unittest.TestCase):
    def test_the_province_and_the_word_city_are_left_out(self):
        self.assertEqual(cc.zone_norm("江苏无锡经济开发区", "江苏"), "无锡经济开发区")
        self.assertEqual(cc.zone_norm("江苏省常州市经济开发区", "江苏"), "常州经济开发区")

    def test_a_yearbook_name_meets_the_codes_name(self):
        ground = {"320471": {"name": "常州经济开发区"}, "320571": {"name": "苏州工业园区"},
                  "320671": {"name": "南通经济技术开发区"}}
        self.assertEqual(cc.zone_for("江苏省常州市经济开发区", "320400", "江苏", ground), "320471")
        self.assertIsNone(cc.zone_for("苏州工业园区", "320400", "江苏", ground))
        self.assertEqual(cc.zone_for("苏州工业园区", "320500", "江苏", ground), "320571")


class Kinds(unittest.TestCase):
    def test_what_a_row_below_a_prefecture_is(self):
        self.assertEqual(cc.kind_of("南关区", "220102"), "district")
        # An autonomous prefecture numbers its county-level cities from 01.
        self.assertEqual(cc.kind_of("延吉市", "222401"), "county")
        self.assertEqual(cc.kind_of("长春经济技术开发区", "220171"), "zone")
        self.assertEqual(cc.kind_of("长春莲花山生态旅游度假区", None), "zone")
        self.assertEqual(cc.kind_of("神农架林区", "429021"), "county")
        self.assertEqual(cc.kind_of("大通回族土族自治县", "630121"), "county")


class Residual(unittest.TestCase):
    def test_a_residual_too_small_to_show_is_said_and_not_drawn(self):
        # Guinan: 20 people of 9 nationalities, 0.03% even together.
        from scripts.fetch_census.china_wiki import RESIDUAL
        groups = {"Han Chinese": 99_980.0, "Hui": 10.0, RESIDUAL: 10.0}
        row = {"total": 100_000.0, "men": 50_000.0, "women": 50_000.0}
        area = {"index": 0, "label": "某县", "code": "630121", "how": "test"}
        r = cc.county_record("63", area, "S-X", {"name": "X", "parent": None}, {},
                             {0: row}, {0: {**row, "groups": groups}}, None,
                             {"A0101": "u1", "A0104": "u4"}, "live: HTTP Error 403")
        self.assertEqual(r["ethnicity"], [{"group": "Han Chinese", "pct": 100.0,
                                           "count": 99_980}])
        self.assertIn("the 10 people of the one nationality too few to show",
                      r["ethnicity_note"])
        self.assertIn("Together they are 20 people, too few to show at one decimal "
                      "themselves: they are counted in the base but not drawn.",
                      r["ethnicity_note"])


class Adding(unittest.TestCase):
    def test_a_province_read_replaces_its_records_and_the_others_stay(self):
        def rec(code, tag):
            return {"id": f"CHN-{code}", "codes": {"gb2260": code}, "tag": tag}
        current = [rec("220322", "old"), rec("320123", "old"), rec("150121", "old")]
        out = cc.merged(current, [rec("150122", "new"), rec("370123", "new")], {"15", "37"})
        # Jilin and Jiangsu kept as they were, Inner Mongolia's old record
        # gone, the new ones in, in the order of PROVINCES.
        self.assertEqual([(r["codes"]["gb2260"], r["tag"]) for r in out],
                         [("220322", "old"), ("320123", "old"), ("150122", "new"),
                          ("370123", "new")])

    def test_a_province_not_read_keeps_its_old_records(self):
        current = [{"id": "CHN-a", "codes": {"gb2260": "630121"}}]
        self.assertEqual(cc.merged(current, [], {"15"}), current)


class Names(unittest.TestCase):
    def test_a_county_made_a_district_since_meets_its_row_by_stem(self):
        names = {"630100": ["西宁市"], "630122": ["湟中区"]}
        self.assertEqual(cc.code_of("湟中县", "6301", names, "county"), "630122")

    def test_an_ambiguous_name_binds_nothing(self):
        names = {"630102": ["城东区"], "630103": ["城东区"]}
        self.assertIsNone(cc.code_of("城东区", "6301", names, "county"))


if __name__ == "__main__":
    unittest.main()
