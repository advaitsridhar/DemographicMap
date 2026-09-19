"""Taiwan's counties under the owner's decision: what is read, what is
modelled, and what the arithmetic promises.

The language rows are Table 2-5 of the DGBAS 2020 census release as the
runner's probe printed them (data/processed/last-run.log of that run), cut
to the rows the reader uses; the Hakka rows are Figure 8 and Table 4-1 of
the Hakka Affairs Council's 2021 report the same way. The register counts
and the building counts are synthetic, built so their national rows are
the sum of their counties.
"""

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import canonical_groups as cg  # noqa: E402
import common  # noqa: E402
from scripts.fetch_census import taiwan as m  # noqa: E402

LANGUAGE_PAGE = """- 32 -
表 2-5 6 歲以上本國籍常住人口使用語言情形
                                            民國 109 年                         單位：%
總計 目前主要使用語言 目前次要使用語言
總計 21 784 369 100.0 66.4 31.7 1.5 0.2 0.2 30.4 54.3 4.0 0.9 2.0 8.4
北部地區 10 366 596 100.0 80.2 18.2 1.3 0.1 0.2 18.1 61.4 5.7 0.7 3.0 11.1
新北市 4 055 599 100.0 78.0 21.6 0.2 0.0 0.2 20.5 67.3 1.3 0.3 2.3 8.2
臺北市 2 388 957 100.0 84.1 15.4 0.2 0.0 0.3 14.3 65.2 1.7 0.2 4.8 13.8
桃園市 2 176 570 100.0 84.8 12.5 2.4 0.1 0.2 13.7 55.7 12.4 1.4 2.8 14.0
基隆市  345 649 100.0 69.7 29.9 0.1 0.2 0.1 28.0 62.4 0.5 0.7 1.2 7.2
新竹市  446 737 100.0 85.0 13.2 1.6 0.0 0.2 13.5 62.0 8.5 0.3 3.1 12.6
宜蘭縣  394 287 100.0 52.6 46.7 0.0 0.3 0.3 43.4 47.6 0.3 1.8 1.0 5.9
新竹縣  558 797 100.0 83.7 4.3 11.5 0.3 0.2 14.6 33.3 33.0 1.7 3.8 13.6
臺中市 2 748 097 100.0 66.8 32.2 0.8 0.1 0.2 30.7 61.5 1.6 0.4 1.4 4.5
苗栗縣  468 167 100.0 62.9 18.5 18.1 0.3 0.2 33.2 28.1 30.4 0.9 0.9 6.6
彰化縣 1 061 247 100.0 39.7 60.1 0.0 0.0 0.1 54.0 38.5 0.2 0.1 0.6 6.6
南投縣  393 818 100.0 45.5 52.7 0.8 0.7 0.2 49.5 41.0 0.9 2.7 0.6 5.3
雲林縣  537 327 100.0 36.2 63.3 0.3 0.0 0.2 53.2 35.1 0.4 0.1 0.5 10.6
臺南市 1 715 534 100.0 49.5 50.3 0.0 0.0 0.2 45.8 46.7 0.3 0.1 1.0 6.2
高雄市 2 527 744 100.0 55.5 43.2 1.0 0.1 0.2 40.7 51.6 1.0 0.4 1.0 5.4
嘉義市  234 885 100.0 51.7 48.1 0.1 0.0 0.1 45.2 49.6 0.3 0.1 0.7 4.1
嘉義縣  427 516 100.0 32.8 66.7 0.0 0.1 0.2 58.4 31.3 0.3 0.5 0.7 8.9
屏東縣  702 009 100.0 40.5 51.5 6.4 1.4 0.2 52.4 33.3 4.4 3.5 0.6 5.9
澎湖縣  74 333 100.0 52.3 47.6 0.0 0.0 0.1 42.6 49.2 0.4 0.4 0.7 6.7
臺東縣  176 353 100.0 69.6 23.0 0.7 6.4 0.4 28.2 45.9 2.1 15.8 1.2 6.8
花蓮縣  278 530 100.0 77.5 15.8 2.3 4.1 0.3 20.1 48.4 5.3 12.9 1.7 11.7
金門縣  61 014 100.0 64.9 34.9 0.0 0.0 0.2 31.5 60.3 0.4 0.7 0.8 6.3
連江縣  11 199 100.0 91.6 3.1 0.0 0.1 5.2 7.5 41.4 2.2 2.9 36.0 10.1
註：其他語言包括手語、各地方言及外國語言等。
"""

HAKKA_COUNTY_PAGE = """(11)
圖8  各縣市設籍人口總數、推估客家人口與成長率
戶籍地
105 年市話調查結果 110 年市話調查結果
客家基本法定義之客家人 設籍人口
推估設籍客家人口百分比(%)
總計 23,492,074 19.31 4,536,794 23,561,236 19.82 4,669,192 0.29  2.92
縣市別
新北市 3,970,644 16.04 636,984 4,030,954 16.68 672,337 1.52  5.55
臺北市 2,704,810 17.49 472,947 2,602,418 17.44 453,770 -3.79  -4.05
桃園市 2,105,780 40.53 853,450 2,268,807 39.91 905,385 7.74  6.09
臺中市 2,744,445 17.58 482,584 2,820,787 17.48 493,030 2.78  2.16
臺南市 1,885,541 5.96 112,320 1,874,917 7.06 132,394 -0.56  17.87
高雄市 2,778,918 12.63 351,089 2,765,932 14.72 407,262 -0.47  16.00
宜蘭縣 458,117 7.17 32,855 453,087 7.65 34,681 -1.10  5.56
新竹縣 542,042 73.56 398,751 570,775 67.83 387,132 5.30  -2.91
苗栗縣 563,912 64.27 362,443 542,590 62.53 339,274 -3.78  -6.39
彰化縣 1,289,072 6.35 81,859 1,266,670 7.84 99,321 -1.74  21.33
南投縣 509,490 15.20 77,423 490,832 12.28 60,285 -3.66  -22.14
雲林縣 699,633 8.26 57,782 676,873 8.50 57,512 -3.25  -0.47
嘉義縣 519,839 6.40 33,291 499,481 8.30 41,460 -3.92  24.54
屏東縣 841,253 25.31 212,936 812,658 23.11 187,796 -3.40  -11.81
臺東縣 222,452 19.81 44,076 215,261 20.55 44,239 -3.23  0.37
花蓮縣 331,945 32.39 107,503 324,372 34.23 111,048 -2.28  3.30
澎湖縣* 102,304 5.23 5,354 105,952 9.48 10,042 - -
基隆市 372,105 7.68 28,566 367,577 12.50 45,964 -1.22  60.90
新竹市 434,060 34.54 149,943 451,412 30.28 136,692 4.00  -8.84
嘉義市 270,366 6.95 18,791 266,005 9.11 24,240 -1.61  29.00
金門縣* 132,799 11.58 15,381 140,597 16.51 23,208 - -
連江縣* 12,547 3.71 466 13,279 15.97 2,121 - -
"""

HAKKA_NATIONAL_PAGE = """表4-1  臺灣主要族群人口消長歷年比較-單一自我認定
單位：%、萬人
臺閩地區 100.0 2,316.2 100.0 2,337.4 100.0 2,349.2 100.0 2,356.1 - 6.9
客家人 14.2 329.0 14.3 333.1 16.2 381.5 15.7 369.8 -0.5 -11.7
福老人 67.5 1,564.2 66.4 1,551.6 69.0 1,620.1 71.3 1,680.9 2.3 60.8
大陸各省市人 7.1 165.1 7.0 164.0 5.5 129.6 5.0 118.8 -0.5 -10.8
原住民 1.8 40.9 1.8 43.0 2.7 63.5 3.0 70.7 0.3 7.2
臺灣人 7.5 174.7 8.3 195.1 5.3 124.9 3.8 89.1 -1.5 -35.8
其他族群 0.5 10.8 0.8 18.9 0.3 6.0 0.1 3.4 -0.2 -2.6
不知道/拒答 1.4 31.5 1.4 31.7 1.0 23.6 1.0 23.4 - -0.2
"""

HAKKA_TEXT = m.PAGE_BREAK.join(["cover", HAKKA_COUNTY_PAGE, HAKKA_NATIONAL_PAGE])
LANGUAGE_TEXT = m.PAGE_BREAK.join(["cover", LANGUAGE_PAGE])


def quiet(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


class Language(unittest.TestCase):
    def test_the_22_counties_and_the_national_row_are_read(self):
        table = quiet(m.read_language, LANGUAGE_TEXT)
        self.assertEqual(len(table), 23)
        self.assertEqual(table["總計"]["base"], 21_784_369)
        self.assertEqual(table["新竹縣"]["main"]["Hakka"], 11.5)
        self.assertEqual(table["連江縣"]["main"]["Other languages"], 5.2)
        self.assertEqual(table["基隆市"]["base"], 345_649)   # a base with a double space

    def test_a_region_row_is_not_a_county(self):
        table = quiet(m.read_language, LANGUAGE_TEXT)
        self.assertNotIn("北部地區", table)

    def test_a_county_whose_base_does_not_add_up_refuses(self):
        bad = LANGUAGE_TEXT.replace("連江縣  11 199", "連江縣  11 299")
        with self.assertRaises(SystemExit) as cm:
            quiet(m.read_language, bad)
        self.assertIn("sum to", str(cm.exception))

    def test_a_row_that_does_not_sum_to_100_refuses(self):
        bad = LANGUAGE_TEXT.replace("100.0 91.6 3.1 0.0 0.1 5.2", "100.0 81.6 3.1 0.0 0.1 5.2")
        with self.assertRaises(SystemExit):
            quiet(m.read_language, bad)

    def test_a_missing_county_refuses(self):
        bad = LANGUAGE_TEXT.replace("金門縣", "金馬縣")
        with self.assertRaises(SystemExit) as cm:
            quiet(m.read_language, bad)
        self.assertIn("金門縣", str(cm.exception))


class Hakka(unittest.TestCase):
    def test_the_county_shares_and_populations_are_read(self):
        table = quiet(m.read_hakka, HAKKA_TEXT)
        self.assertEqual(table["新竹縣"], {"population": 570_775, "pct": 67.83, "hakka": 387_132})
        self.assertEqual(table["連江縣"]["pct"], 15.97)     # the starred island rows read too
        self.assertEqual(table["總計"]["population"], 23_561_236)

    def test_the_identity_shares_are_the_2021_column(self):
        identity = quiet(m.read_identity, HAKKA_TEXT)
        self.assertEqual(identity[m.HOKLO], 71.3)
        self.assertEqual(identity[m.MAINLANDER], 5.0)
        self.assertEqual(identity[m.HAKKA], 15.7)
        self.assertLess(abs(sum(identity.values()) - 100.0), 0.3)   # printed to one decimal

    def test_counties_that_do_not_sum_to_the_national_row_refuse(self):
        bad = HAKKA_TEXT.replace("連江縣* 12,547 3.71 466 13,279", "連江縣* 12,547 3.71 466 14,279")
        with self.assertRaises(SystemExit):
            quiet(m.read_hakka, bad)


class Compose(unittest.TestCase):
    IDENTITY = {m.HOKLO: 71.3, m.MAINLANDER: 5.0}

    def test_the_rest_is_split_in_the_national_ratio_and_sums_to_100(self):
        out = m.compose_ethnicity(2.5, 19.8, self.IDENTITY)
        self.assertEqual(out[m.INDIGENOUS], 2.5)
        self.assertEqual(out[m.HAKKA], 19.8)
        self.assertAlmostEqual(out[m.HOKLO] / out[m.MAINLANDER], 71.3 / 5.0)
        self.assertAlmostEqual(sum(out.values()), 100.0)

    def test_a_county_with_no_room_for_the_rest_refuses(self):
        with self.assertRaises(ValueError):
            m.compose_ethnicity(60.0, 50.0, self.IDENTITY)


class Tilt(unittest.TestCase):
    PRIOR = {"Buddhism": 28.0, "Taoism": 24.0, "Christianity": 7.0, "Other religions": 12.0}
    NATIONAL = {"Buddhism": 20.0, "Taoism": 60.0, "Christianity": 15.0, "Other religions": 5.0}

    def test_a_signal_map_tilts_by_temples_and_churches(self):
        # Churches are 40 of 100 here against 20 of 100 nationally.
        national = {m.TEMPLES: 80.0, m.CHURCHES: 20.0}
        unit = {m.TEMPLES: 60.0, m.CHURCHES: 40.0}
        shares, ratios, _ = m.tilt(self.PRIOR, 29.0, national, unit, caps={}, signal=m.SIGNAL)
        self.assertAlmostEqual(ratios[m.CHURCHES], 2.0)
        self.assertAlmostEqual(ratios[m.TEMPLES], 0.75)
        self.assertAlmostEqual(shares["Buddhism"] / shares["Taoism"], 28.0 / 24.0)
        self.assertGreater(shares["Christianity"], 7.0)
        self.assertAlmostEqual(sum(shares.values()), 100.0)

    def test_a_unit_with_the_national_pattern_is_the_prior(self):
        shares, ratios, held = m.tilt(self.PRIOR, 29.0, self.NATIONAL, dict(self.NATIONAL),
                                      caps={})
        for g in self.PRIOR:
            self.assertAlmostEqual(ratios[g], 1.0)
            self.assertAlmostEqual(shares[g], self.PRIOR[g])
        self.assertEqual(shares["No religion"], 29.0)
        self.assertEqual(held, [])

    def test_the_tilt_is_relative_and_keeps_the_affiliated_total(self):
        # Christianity is 30 of 100 here against 15 of 100 nationally.
        unit = {"Buddhism": 20.0, "Taoism": 45.0, "Christianity": 30.0, "Other religions": 5.0}
        shares, ratios, _ = m.tilt(self.PRIOR, 29.0, self.NATIONAL, unit, caps={})
        self.assertAlmostEqual(ratios["Christianity"], 2.0)
        self.assertAlmostEqual(ratios["Taoism"], 0.75)
        self.assertAlmostEqual(sum(shares[g] for g in self.PRIOR), 71.0)
        self.assertAlmostEqual(sum(shares.values()), 100.0)

    def test_the_ratio_is_clipped(self):
        unit = {"Buddhism": 1.0, "Taoism": 1.0, "Christianity": 98.0, "Other religions": 0.0}
        _, ratios, _ = m.tilt(self.PRIOR, 29.0, self.NATIONAL, unit, bound=3.0, caps={})
        self.assertEqual(ratios["Christianity"], 3.0)
        self.assertAlmostEqual(ratios["Taoism"], 1 / 3)
        self.assertAlmostEqual(ratios["Other religions"], 1 / 3)

    def test_a_cap_holds_the_share_and_rescales_the_rest(self):
        unit = {"Buddhism": 1.0, "Taoism": 1.0, "Christianity": 98.0, "Other religions": 0.0}
        shares, _, held = m.tilt(self.PRIOR, 29.0, self.NATIONAL, unit, bound=10.0,
                                 caps={"Christianity": 25.0})
        self.assertEqual(held, ["Christianity"])
        self.assertAlmostEqual(shares["Christianity"], 25.0)
        self.assertAlmostEqual(sum(shares[g] for g in self.PRIOR), 71.0)
        self.assertGreater(shares["Buddhism"], 0)

    def test_the_prior_leaves_out_the_dont_knows_and_sums_to_100(self):
        prior, none = m.prior_shares()
        self.assertAlmostEqual(sum(prior.values()) + none, 100.0)
        self.assertAlmostEqual(none / sum(prior.values()), m.PRIOR_NONE / sum(m.PRIOR.values()))

    def test_a_signal_with_no_buildings_cannot_tilt(self):
        with self.assertRaises(ValueError):
            m.tilt(self.PRIOR, 29.0, self.NATIONAL, {g: 0.0 for g in self.PRIOR})


class Hundred(unittest.TestCase):
    def test_rounds_to_exactly_100(self):
        rows = m.hundred({"a": 1 / 3, "b": 1 / 3, "c": 1 / 3})
        self.assertAlmostEqual(sum(r["pct"] for r in rows), 100.0)
        self.assertEqual([r["pct"] for r in rows], [33.4, 33.3, 33.3])


def synthetic_register():
    """Population and indigenous counts by county whose totals are their sums."""
    population = {c: 100_000 + 1_000 * i for i, c in enumerate(m.COUNTIES)}
    indigenous = {c: 500 + 10 * i for i, c in enumerate(m.COUNTIES)}
    indigenous["花蓮縣"] = 30_000        # a fifth of the county, as in life
    population[m.NATIONAL] = sum(population.values())
    indigenous[m.NATIONAL] = sum(indigenous.values())
    return population, indigenous


def synthetic_buildings():
    """Temples and churches by county: Hualien and Taitung church-heavy, the
    west temple-heavy, Hsinchu City an artefact of many small churches."""
    out = {}
    for i, c in enumerate(m.COUNTIES):
        out[c] = {m.TEMPLES: 500.0 + 4 * i, m.CHURCHES: 60.0}
    out["花蓮縣"][m.CHURCHES] = 400.0
    out["臺東縣"][m.CHURCHES] = 350.0
    out["新竹市"][m.CHURCHES] = 2000.0
    out[m.NATIONAL] = {k: sum(out[c][k] for c in m.COUNTIES) for k in (m.TEMPLES, m.CHURCHES)}
    return out


def register_grid(month_line, name_col, head_rows, rows):
    """A sheet the way statis.moi.gov.tw writes one: a title, the month, the
    header rows, then one row per area with its name in ``name_col``."""
    grid = [["1.1-title"], [month_line]] + head_rows
    for name, figures in rows:
        row = [""] * (name_col + 1)
        row[name_col] = name
        grid.append(row + figures)
    return grid


POPULATION_ROWS = [("總計  Total", ["36197", "368", "7781", "143598", "9923990", "23224721", "100"]),
                   ("臺 灣 省 Taiwan Province", ["25110", "200", "3530", "58999", "2800523",
                                              "6837917", "29.44"])]
POPULATION_ROWS += [(f"{c} X", ["1", "1", "1", "1", "1", str(1_000_000 + i), "1"])
                    for i, c in enumerate(m.COUNTIES)]
POPULATION_ROWS[0] = ("總計  Total", ["36197", "368", "7781", "143598", "9923990",
                                     str(sum(1_000_000 + i for i in range(22))), "100"])
POPULATION_GRID = register_grid(
    "中華民國115年8月底 End of  Aug. 2026", 0,
    [["區域別", "土地面積 (平方公里)", "鄉鎮市區數", "村里數", "編組鄰數", "戶數", "人口數",
      "占總人口比率(%)", "男性人口數"],
     ["Locality", "Area(Km²)", "Townships", "Villages", "Neighborhoods", "Households",
      "Persons", "Proportion", "Male"]],
    POPULATION_ROWS)

INDIGENOUS_ROWS = [("總計  Total", [str(sum(1000 + i for i in range(22))), "1", "1"]),
                   ("臺 灣 省 Taiwan Province", ["5", "1", "1"])]
INDIGENOUS_ROWS += [(f"{c} X", [str(1000 + i), "1", "1"]) for i, c in enumerate(m.COUNTIES)]
INDIGENOUS_GRID = register_grid(
    "中華民國115年8月底 End of  Aug. 2026", 1,
    [["區域別\n Locality", "", "原住民人數 Grand-Total", "", "", "平地原住民人數 In Plains"],
     ["", "", "合計", "男性", "女性", "合計"],
     ["", "", "Total", "Male", "Female", "Total"],
     ["115年 1 -12月"]],
    INDIGENOUS_ROWS)

BUILDINGS_GRID = [["06-01 臺閩地區各宗教教務概況"], [""], ["單位：個；人"],
                  ["年底及區域別", "", "寺廟教(會)堂數\nNo. of temple", "", "",
                   "信徒人數(依各宗教皈依之規定)\nNo. of"],
                  ["", "", "合計", "寺廟", "教(會)堂", "信徒人數"],
                  ["End of Year & Locality", "", "Total", "Temples", "Churches", "Followers"],
                  ["一一四年 2025", "15252", "15252", str(22 * 500), str(22 * 130), "932735"],
                  ["臺 灣 省", "Taiwan Prov.", "7783", "6434", "1349", "474941"]]
BUILDINGS_GRID += [[c, "X", "630", "500", "130", "1"] for c in m.COUNTIES]


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        language = quiet(m.read_language, LANGUAGE_TEXT)
        hakka = quiet(m.read_hakka, HAKKA_TEXT)
        identity = quiet(m.read_identity, HAKKA_TEXT)
        population, indigenous = synthetic_register()
        cls.records = quiet(m.build, language, hakka, identity, population, indigenous,
                            (2026, 7), synthetic_buildings(), 2025)
        cls.by_name = {r["name"]: r for r in cls.records}

    def test_22_records_named_for_the_shapes_with_aliases(self):
        self.assertEqual(len(self.records), 22)
        self.assertIn("Matsu Islands", self.by_name)
        self.assertIn("Lienchiang County", self.by_name["Matsu Islands"]["aliases"])
        self.assertIn("Taipei County", self.by_name["New Taipei"]["aliases"])
        for r in self.records:
            self.assertEqual(r["country"], "TWN")
            self.assertEqual(r["level"], "admin1")

    def test_language_is_a_list_and_the_estimates_are_estimates(self):
        for r in self.records:
            self.assertIsInstance(r["language"], list, r["name"])
            self.assertTrue(common.is_estimate(r["ethnicity"]), r["name"])
            self.assertTrue(common.is_estimate(r["religion"]), r["name"])
            self.assertNotIn("backtest", r["ethnicity"])
            self.assertNotIn("backtest", r["religion"])
            self.assertEqual(r["language_year"], 2020)
            self.assertIn("aged 6 and over", r["language_basis"])

    def test_every_composition_sums_to_100(self):
        for r in self.records:
            self.assertLess(abs(sum(x["pct"] for x in r["language"]) - 100.0), 0.31, r["name"])
            for field in ("ethnicity", "religion"):
                total = sum(x["pct"] for x in r[field]["estimate"])
                self.assertAlmostEqual(total, 100.0, places=6, msg=f"{r['name']} {field}")

    def test_the_ethnicity_arithmetic_is_the_registers_and_the_surveys(self):
        hualien = self.by_name["Hualien County"]["ethnicity"]
        shares = {x["group"]: x["pct"] for x in hualien["estimate"]}
        population, indigenous = synthetic_register()
        self.assertAlmostEqual(shares[m.INDIGENOUS],
                               round(indigenous["花蓮縣"] / population["花蓮縣"] * 100, 1), 0)
        self.assertAlmostEqual(shares[m.HAKKA], 34.2, delta=0.11)
        self.assertGreater(shares[m.HOKLO], shares[m.MAINLANDER])
        self.assertEqual(hualien["method"], m.ETHNICITY_METHOD)

    def test_the_church_heavy_counties_are_tilted_towards_christianity_within_the_bound(self):
        hualien = {x["group"]: x["pct"] for x in self.by_name["Hualien County"]["religion"]["estimate"]}
        changhua = {x["group"]: x["pct"] for x in self.by_name["Changhua County"]["religion"]["estimate"]}
        self.assertGreater(hualien["Christianity"], changhua["Christianity"])
        self.assertLessEqual(hualien["Christianity"], m.CAPS["Christianity"] + 0.05)
        prior, none = m.prior_shares()
        self.assertAlmostEqual(hualien["No religion"], none, delta=0.11)   # one rounding step

    def test_a_bound_is_recorded_when_hit(self):
        hsinchu = self.by_name["Hsinchu"]["religion"]
        self.assertIn("Christianity", hsinchu.get("capped", []))
        self.assertLessEqual({x["group"]: x["pct"] for x in hsinchu["estimate"]}["Christianity"],
                             m.CAPS["Christianity"] + 0.05)
        self.assertEqual(hsinchu["tilt"][m.CHURCHES], m.TILT_BOUND)
        self.assertIn("2,000 churches", hsinchu["note"])

    def test_the_temple_traditions_move_together(self):
        changhua = {x["group"]: x["pct"] for x in self.by_name["Changhua County"]["religion"]["estimate"]}
        prior, _ = m.prior_shares()
        self.assertAlmostEqual(changhua["Buddhism"] / changhua["Taoism"],
                               prior["Buddhism"] / prior["Taoism"], delta=0.02)

    def test_notes_open_with_what_the_figure_is_and_stay_short(self):
        for r in self.records:
            self.assertTrue(r["ethnicity"]["note"].startswith("Modelled from"))
            self.assertTrue(r["religion"]["note"].startswith("Modelled from"))
            self.assertTrue(r["language_note"].startswith("2020 census"))
            self.assertLess(len(r["religion"]["note"]), 1100, r["name"])
            self.assertLess(len(r["ethnicity"]["note"]), 900, r["name"])

    def test_the_decision_and_the_sources_are_on_every_record(self):
        for r in self.records:
            self.assertIn(m.DECISION, r["ethnicity"]["note"])
            fields = {s["field"] for s in r["sources"]}
            self.assertEqual(fields, {"language", "ethnicity", "ethnicity/population", "religion"})


class Workbooks(unittest.TestCase):
    def test_sheets_are_named_for_a_month_or_a_year(self):
        self.assertEqual(m.sheet_date(" 2025"), (2025, 12))
        self.assertEqual(m.sheet_date(" Aug., 2026"), (2026, 8))
        self.assertIsNone(m.sheet_date("年月monthly"))
        self.assertIsNone(m.sheet_date("2025(區域別)"))

    def test_the_latest_month_wins_over_the_latest_year(self):
        grids = {"年月monthly": [], " Aug., 2026": [["a"]], " 2025": [["b"]], " 2024": [["c"]]}
        name, grid, when = m.latest_sheet(grids)
        self.assertEqual((name, grid, when), (" Aug., 2026", [["a"]], (2026, 8)))

    def test_the_yearbook_county_sheet_is_selected_by_pattern(self):
        grids = {"歷年Yearly": [], "2025(區域別)": [["a"]], "2025(宗教別)": [["b"]],
                 "2024(區域別)": [["c"]]}
        name, _, when = m.latest_sheet(grids, m.COUNTY_SHEET)
        self.assertEqual((name, when), ("2025(區域別)", (2025, 12)))
        with self.assertRaises(SystemExit):
            m.latest_sheet({"歷年Yearly": [], "2025(宗教別)": []}, m.COUNTY_SHEET)

    def test_the_population_sheet_reads_人口數_and_not_男性人口數(self):
        table = m.read_columns(POPULATION_GRID, {"value": "人口數"}, "population")
        self.assertEqual(table["新北市"]["value"], 1_000_000)
        self.assertEqual(table["連江縣"]["value"], 1_000_021)
        self.assertEqual(table[m.NATIONAL]["value"], sum(1_000_000 + i for i in range(22)))
        self.assertNotIn("臺灣省", table)
        self.assertEqual(m.sheet_month(POPULATION_GRID, "x"), (2026, 8))

    def test_the_indigenous_sheet_names_its_areas_in_the_second_column(self):
        table = m.read_columns(INDIGENOUS_GRID, {"value": "原住民人數"}, "indigenous")
        self.assertEqual(table["臺北市"]["value"], 1001)
        self.assertEqual(len(table), 23)

    def test_the_yearbook_sheet_reads_temples_and_churches_with_the_year_row_as_the_nation(self):
        table = m.read_columns(BUILDINGS_GRID, {m.TEMPLES: "寺廟", m.CHURCHES: "教(會)堂"},
                               "buildings", year_row_is_national=True)
        self.assertEqual(table["新北市"], {m.TEMPLES: 500, m.CHURCHES: 130})
        self.assertEqual(table[m.NATIONAL], {m.TEMPLES: 11000, m.CHURCHES: 2860})

    def test_counties_that_do_not_sum_to_the_total_refuse(self):
        grid = [row[:] for row in BUILDINGS_GRID]
        grid[6][3] = "10999"
        with self.assertRaises(SystemExit) as cm:
            m.read_columns(grid, {m.TEMPLES: "寺廟"}, "buildings", year_row_is_national=True)
        self.assertIn("sums to", str(cm.exception))

    def test_a_missing_column_refuses(self):
        with self.assertRaises(SystemExit):
            m.read_columns(BUILDINGS_GRID, {"x": "佛教"}, "buildings", year_row_is_national=True)


class Placement(unittest.TestCase):
    def test_every_label_the_adapter_writes_is_placed_in_the_tree(self):
        for label in m.LANGUAGE_COLUMNS:
            self.assertGreater(len(cg.ancestry("language", label)), 1, label)
        for label in (m.INDIGENOUS, m.HAKKA, m.HOKLO, m.MAINLANDER):
            self.assertGreater(len(cg.ancestry("ethnicity", label)), 1, label)
        for label in list(m.PRIOR) + ["No religion"]:
            trail = cg.ancestry("religion", label)
            self.assertTrue(len(trail) > 1 or label == "No religion", label)

    def test_taiwan_has_no_collection_policy_that_would_refuse_the_estimates(self):
        for field in ("religion", "ethnicity", "language"):
            self.assertIsNone(common.collection_gap("TWN", field), field)


if __name__ == "__main__":
    unittest.main()
