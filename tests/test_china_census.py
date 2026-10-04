"""China's provinces from the census yearbook's own workbooks, offline.

The four tables are synthetic but laid out as the yearbook's .xls files are:
a title, a header row of three-column blocks whose labels are spaced out
("合 计", "汉 族"), the 全国 row and the 31 regions with their names spaced
("内 蒙 古"), blank rows between groups.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import china_census as cc  # noqa: E402

NAMES = list(cc.province_names())
AGE_HEADS = ["0岁", "1-4岁"] + [f"{a}-{a + 4}岁" for a in range(5, 100, 5)] + ["100岁及以上"]
# One nationality per column block, in the yearbook's order, then the two
# rows that are not a nationality.
NATIONS = ["汉族", "蒙古族", "回族", "藏族", "维吾尔族", "苗族", "彝族", "壮族", "布依族", "朝鲜族",
           "满族", "侗族", "瑶族", "白族", "土家族", "哈尼族", "哈萨克族", "傣族", "黎族", "傈僳族",
           "佤族", "畲族", "高山族", "拉祜族", "水族", "东乡族", "纳西族", "景颇族", "柯尔克孜族",
           "土族", "达斡尔族", "仫佬族", "羌族", "布朗族", "撒拉族", "毛南族", "仡佬族", "锡伯族",
           "阿昌族", "普米族", "塔吉克族", "怒族", "乌孜别克族", "俄罗斯族", "鄂温克族", "德昂族",
           "保安族", "裕固族", "京族", "塔塔尔族", "独龙族", "鄂伦春族", "赫哲族", "门巴族",
           "珞巴族", "基诺族", "未定族称人口", "入籍"]


def spaced(text):
    return " ".join(text)


def sexes(i):
    """(men, women) by age group for region i: young, ageing gently."""
    men = [(i + 1) * (50 + (10 if a < 12 else 22 - a)) for a in range(len(AGE_HEADS))]
    women = [(i + 1) * (48 + (10 if a < 12 else 24 - a)) for a in range(len(AGE_HEADS))]
    return [max(m, 1) for m in men], [max(w, 1) for w in women]


def regions():
    out = {}
    for i, name in enumerate(NAMES):
        out[name] = sexes(i)
    men = [sum(out[n][0][k] for n in NAMES) for k in range(len(AGE_HEADS))]
    women = [sum(out[n][1][k] for n in NAMES) for k in range(len(AGE_HEADS))]
    out[cc.NATIONAL] = (men, women)
    return out


def blocks_row(label, parts):
    """A row: the label, then (both, men, women) per block."""
    row = [label]
    for men, women in parts:
        row += [float(men + women), float(men), float(women)]
    return row


def a0105(data):
    header = ["地 区", "合 计", "", ""] + sum([[spaced(h), "", ""] for h in AGE_HEADS], [])
    rows = [["1-5 各地区分年龄、性别的人口"], [""], ["", "单位：人"], header,
            [""] + ["合计", "男", "女"] * (len(AGE_HEADS) + 1), [""]]
    for name in [cc.NATIONAL, *NAMES]:
        men, women = data[name]
        parts = [(sum(men), sum(women))] + list(zip(men, women))
        rows.append(blocks_row(spaced(name), parts))
        rows.append([""])
    return rows


def a0104(data):
    header = ["地 区", "合 计", "", ""] + sum([[spaced(h), "", ""] for h in NATIONS], [])
    rows = [["1-4 各地区分性别、民族的人口"], [""], ["", "单位：人"], header, [""]]
    for name in [cc.NATIONAL, *NAMES]:
        men, women = sum(data[name][0]), sum(data[name][1])
        # Nine in ten are Han, a twentieth Mongol, the rest unidentified.
        split = [(men * 9 // 10, women * 9 // 10), (men // 20, women // 20)]
        rest = (men - sum(m for m, _ in split), women - sum(w for _, w in split))
        parts = [(men, women)] + split + [(0, 0)] * (len(NATIONS) - 3) + [rest]
        rows.append(blocks_row(spaced(name), parts))
    return rows


def a0101(data):
    rows = [["1-1 各地区户数、人口数和性别比"], [""], [""], ["地 区"], [""], [""], [""], [""]]
    for name in [cc.NATIONAL, *NAMES]:
        men, women = sum(data[name][0]), sum(data[name][1])
        rows.append([spaced(name), 1.0, 1.0, 0.0, float(men + women), float(men), float(women),
                     round(100 * men / women, 2)])
    return rows


def a0301(data):
    men, women = data[cc.NATIONAL]
    rows = [["3-1 全国分年龄、性别的人口"], [""], [""], ["年 龄"], [""], [""]]
    for k, head in enumerate(AGE_HEADS):
        if head == "100岁及以上":
            rows.append([head, float(men[k] + women[k]), float(men[k]), float(women[k])])
            continue
        low, width = (0, 1) if head == "0岁" else (1, 4) if head == "1-4岁" else (
            int(head.split("-")[0]), 5)
        rows.append([head, float(men[k] + women[k]), 0.0, 0.0])
        both = men[k] + women[k]
        for age in range(low, low + width):
            share = both // width + (both % width if age == low + width - 1 else 0)
            rows.append([str(age) if age == 0 else f"{age}.0", float(share), 0.0, 0.0])
    return rows


def tables():
    data = regions()
    return {"A0101": a0101(data), "A0104": a0104(data), "A0105": a0105(data),
            "A0301": a0301(data)}


def admin1():
    units = [{"id": f"S-{n}", "name": n} for _, n in cc.province_names().items()]
    return units + [{"id": "S-HK", "name": cc.HK_NAME}, {"id": "S-MO", "name": cc.MO_NAME}]


HK_ROWS = [["主要統計數字"], ["Key Statistics"],
           ["人口特徵", "", "", "", "", "", "", "", 2011, "", 2016, "", 2021],
           ["", "年齡中位數", "", "", "", "", "", "", 41.7, "", 43.4, "", 46.3],
           ["", "Median age"],
           ["", "性別比率（每千名女性的男性人數）", "", "", "", "", "", "", 876, "", 852, "", 839],
           ["", "Sex ratio (number of males per 1,000 females)", "", "", "", "", "", "", 939,
            "[2]", 925, "[2]", 910]]
MO_TEXT = ("The median age of the total population went up from 33.3 in 2001 and 37.0 in "
           "2011 to 38.4 in 2021, reflecting ... In terms of gender, there were 320,285 males "
           "and 361,785 females, accounting for 47.0%")


class Build(unittest.TestCase):
    def setUp(self):
        self.records = {r["shape_id"]: r for r in cc.build(tables(), admin1(), HK_ROWS, MO_TEXT)}

    def test_every_unit(self):
        self.assertEqual(len(self.records), 33)

    def test_a_province(self):
        r = self.records["S-Inner Mongolia Autonomous Region"]
        men, women = sexes(NAMES.index("内蒙古"))
        self.assertEqual(r["population"]["value"], sum(men) + sum(women))
        self.assertEqual(r["sex_ratio"]["value"], round(100 * sum(men) / sum(women), 1))
        self.assertIn("1-5", r["median_age_note"])
        groups = {g["group"]: g["pct"] for g in r["ethnicity"]}
        self.assertEqual(groups["Han Chinese"], 90.0)
        self.assertEqual(groups["Mongol"], 5.0)
        self.assertIn(cc.RESIDUAL, groups)
        self.assertAlmostEqual(sum(groups.values()), 100.0, places=6)
        self.assertEqual(r["language"]["status"], "not_collected")

    def test_the_sars(self):
        hk, mo = self.records["S-HK"], self.records["S-MO"]
        self.assertEqual(hk["median_age"]["value"], 46.3)
        self.assertEqual(hk["sex_ratio"]["value"], 83.9)
        self.assertEqual(mo["median_age"]["value"], 38.4)
        self.assertEqual(mo["sex_ratio"]["value"], round(100 * 320285 / 361785, 1))


def admin2():
    """Three county polygons, an island drawn under the country, and the SARs."""
    return [{"id": "C-1", "name": "Panyushi", "parent": "S-Guangdong"},
            {"id": "C-2", "name": "Akesaihashakezuzizhixian", "parent": "S-Gansu Province"},
            {"id": "C-3", "name": "Changhaixian", "parent": "CHN"},
            {"id": "C-HK", "name": "Xianggang", "parent": "S-HK"},
            {"id": "C-MO", "name": "C-MO", "parent": "S-MO"}]


class Counties(unittest.TestCase):
    def setUp(self):
        provinces = cc.build(tables(), admin1(), HK_ROWS, MO_TEXT)
        self.records = {r["shape_id"]: r for r in cc.county_records(admin1(), admin2(), provinces)}

    def test_every_polygon(self):
        self.assertEqual(sorted(self.records), ["C-1", "C-2", "C-3", "C-HK", "C-MO"])
        self.assertTrue(all(r["level"] == "admin2" and r["match_by"] == "shape_id"
                            for r in self.records.values()))

    def test_a_mainland_county_carries_its_reasons(self):
        r = self.records["C-1"]
        self.assertEqual(r["language"]["status"], "not_collected")
        for field in ("population", "median_age", "sex_ratio", "ethnicity"):
            self.assertEqual(r[field], {"status": "not_available", "note": cc.COUNTY_NOTE})
        self.assertEqual(r["parent"], "CHN-Guangdong")
        self.assertEqual(self.records["C-3"]["parent"], "CHN")

    def test_the_sars_take_their_own_figures(self):
        hk = self.records["C-HK"]
        self.assertEqual(hk["median_age"]["value"], 46.3)
        self.assertEqual(hk["sex_ratio"]["value"], 83.9)
        self.assertEqual(hk["language"], {"status": "not_available"})
        self.assertEqual(self.records["C-MO"]["median_age"]["value"], 38.4)

    def test_a_sar_drawn_in_two_is_refused(self):
        provinces = cc.build(tables(), admin1(), HK_ROWS, MO_TEXT)
        units = admin2() + [{"id": "C-HK2", "name": "Lantau", "parent": "S-HK"}]
        with self.assertRaises(SystemExit):
            cc.county_records(admin1(), units, provinces)


class Refusals(unittest.TestCase):
    def test_tables_must_agree(self):
        t = tables()
        t["A0101"][9][4] += 1.0
        t["A0101"][9][5] += 1.0
        with self.assertRaises(SystemExit):
            cc.build(t, admin1())

    def test_age_groups_must_add_up(self):
        t = tables()
        t["A0105"][8][7] += 5.0
        with self.assertRaises(SystemExit):
            cc.build(t, admin1())

    def test_an_unknown_nationality(self):
        t = tables()
        t["A0104"][3][7] = "火星族"
        with self.assertRaises(SystemExit):
            cc.build(t, admin1())

    def test_a_missing_province(self):
        t = tables()
        t["A0101"] = [r for r in t["A0101"] if not r or "".join(str(r[0]).split()) != "海南"]
        with self.assertRaises(SystemExit):
            cc.build(t, admin1())

    def test_macau_must_add_up(self):
        with self.assertRaises(SystemExit):
            cc.macau(MO_TEXT.replace("320,285", "320,286"), "S-MO")


if __name__ == "__main__":
    unittest.main()
