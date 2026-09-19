"""China's provincial ethnicity tables, in the layouts the articles print them.

The fixtures are the shapes the runner's inspections found in the English
and Chinese articles: a plain three-column table, one transposed
(nationalities across the header), one written on a single line, one whose
rows end in HTML's </tr>, one carrying its title as a header cell, one
whose shares are spelled "percent", a Chinese one in traditional
characters, one preceded by a template that ends "|}}", a time series that
must not be mistaken for a composition, and Shandong's, whose printed share
for "Other ethnic groups" is a slip its own count exposes.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.fetch_census import china_wiki as cw  # noqa: E402


PLAIN = """== Demographics ==
{| class="wikitable"
|+ Ethnic groups in Inner Mongolia, 2010 census
! Ethnicity !! Population !! Percentage
|-
| [[Han Chinese|Han]] || 19,650,687 || 79.54%
|-
| [[Mongols|Mongol]] || 4,226,093 || 17.11%
|-
| [[Manchu]] || 452,765 || 1.83%
|-
| [[Daur people|Daur]] || 121,483 || 0.49%
|-
| [[Evenks]] || 26,139 || 0.11%
|-
| [[Oroqen people]] || 8,464 || 0.07%
|}
"""

TRANSPOSED = """== Ethnic groups ==
{| class="wikitable"
|+ Ethnic composition of Heilongjiang Province (Seventh National Population Census, 2020)
! Ethnic group !! [[Han Chinese]] !! [[Manchu]] !! [[Koreans in China|Korean]] !! Other minorities
|-
| Population || 30,000,000 || 500,000 || 250,000 || 250,000
|-
| Percentage || 96.77% || 1.61% || 0.81% || 0.81%
|}
"""

ONE_LINE = """== Demographics ==
{| class="wikitable"
|+ Ethnic groups in Jilin (2000 census) |- ! Ethnic Groups !! Population !! Percentage |- | Han Chinese || 24,348,815 || 90.85% |- | Koreans || 1,145,688 || 4.27% |- | Manchu || 993,112 || 3.71% |- | Mongol || 172,026 || 0.64% |- | Hui || 125,620 || 0.47% |}
"""

HTML_ROWS = """== Demographics ==
{| class="wikitable" style="text-align:right;"
!colspan="3"| Ethnic groups in Jilin (2000 census)</tr>
! [[Nationalities of China|Ethnic Groups]] !! Population !! Percentage</tr>
|align="left"| [[Han Chinese]]    || 24,348,815 || 90.85%</tr>
|align="left"| [[Koreans]] || 1,145,688 || 4.27%</tr>
|align="left"| [[Manchu]]         ||    993,112 ||  3.71%</tr>
|align="left"| [[Mongol]]         ||    172,026 ||  0.64%</tr>
|align="left"| [[Hui people|Hui]] ||    125,620 ||  0.47%</tr>
|}
"""

TITLE_IN_CELL = """== Demographics ==
{| class="wikitable"
! colspan=3 | Ethnic groups in Hebei, 2000 census
|-
! Nationality !! Population !! Percentage
|-
| [[Han Chinese]] || 63,781,603 || 95.65%
|-
| [[Manchu]] || 2,118,711 || 3.18%
|-
| [[Hui people|Hui]] || 542,639 || 0.78%
|-
| [[Mongols|Mongol]] || 169,887 || 0.26%
|-
| [[Zhuang people|Zhuang]] || 20,832 || 0.031%
|}
"""

AFTER_TEMPLATE = """== Demographics ==
{{Historical populations
|type=China
|1953|2693831
|2020|13866009
|footnote = Population size may be affected by changes on administrative divisions.
|}}
The majority of Tianjin residents are [[Han Chinese]].
{| class="wikitable"
|-
! style="text-align:center;" colspan="3"| Ethnic groups in Tianjin, 2000 census
|-
! [[List of ethnic groups in China|Ethnicity]] !! Population !! Percentage
|-
| [[Han Chinese|Han]] || 9,581,775 || 97.29%
|-
| [[Hui people|Hui]] || 172,357 || 1.75%
|-
| [[Manchu people|Manchu]] || 56,548 || 0.57%
|-
| [[Mongols]] || 11,331 || 0.12%
|}
The graph above excludes members of the [[People's Liberation Army]] in active service.
"""

SHANDONG = """== Ethnicity ==
{| class="wikitable"
|+ Ethnic groups in Shandong according to the 2020 Chinese census
! Ethnicity !! Male !! Female !! Total population !! Percentage
|-
| Han || 50,981,231 || 49,641,263 || 100,622,494 || 99.109%
|-
| Hui || 279,413 || 272,802 || 552,215 || 0.544%
|-
| Mongol || 19,360 || 18,294 || 37,654 || 0.037%
|-
| Zang (Tibetan) || 1,851 || 2,501 || 4,352 || 0.004%
|-
| Other ethnic groups || 151,076 || 159,662 || 310,738 || 0.003%
|-
| Total || 51,432,931 || 50,094,522 || 101,527,453 || 100%
|}
"""

PERCENT_WORD = """== Demographics ==
{| class="wikitable"
|+ Ethnic groups in Xinjiang
! colspan=3 | 2020 Chinese census
|-
! Nationality !! Population !! Percentage
|-
| Uyghur || 11,624,257 || 44.96 percent
|-
| Han || 10,920,098 || 42.24 percent
|-
| Kazakh || 1,539,636 || 5.96 percent
|-
| Hui || 1,102,928 || 4.27 percent
|-
| Other || 665,426 || 2.57 percent
|}
"""

TRADITIONAL = """== 民族 ==
{| class="wikitable"
|+ 遼寧省民族構成（2020年第七次全國人口普查）
! 民族名稱 !! 漢族 !! 滿族 !! 蒙古族 !! 朝鮮族 !! 瑤族 !! 其他民族
|-
! 人口數
| 36,169,617 || 5,085,984 || 677,760 || 229,158 || 20,000 || 45,348
|-
! 佔總人口比例（%）
| 84.92 || 11.94 || 1.59 || 0.54 || 0.05 || 0.11
|-
! 佔少數民族人口比例（%）
| － || 79.20 || 10.55 || 3.57 || 0.3 || 0.71
|}
"""

UNLISTED = """== 民族 ==
{| class="wikitable"
|+ 贵州省民族构成（2020年第七次全国人口普查）
! 民族名称 !! 人口数 !! 占总人口比例（%）
|-
| 汉族 || 24,511,882 || 63.56
|-
| 苗族 || 4,506,912 || 11.69
|-
| 布依族 || 2,710,606 || 7.03
|-
| 未定族称人口 || 698,234 || 1.81
|-
| 其他民族 || 6,134,514 || 15.91
|}
"""

SERIES = """== Demographics ==
By 2020, the percentage of Han Chinese had dropped to 78.7%.
{| class="wikitable sortable"
|+
!Year!!Population
!colspan=2|[[Han Chinese]]
!colspan=2|[[Mongols in China|Mongol]]
|-
!1953
| 6,100,104 || 5,119,928 || 83.9% || 888,235 || 14.6%
|-
!2010
| 24,706,321 || 19,650,687 || 79.5% || 4,226,093 || 17.1%
|}
"""

SAMPLE_2015 = """== 民族 ==
{| class="wikitable"
|+ 新疆民族分佈（2015） 根据2015年底人口抽查统计
! 民族 !! 人口數 !! 百分比
|-
| 维吾尔族 || 11,303,300 || 48.0%
|-
| 汉族 || 8,600,000 || 36.5%
|-
| 其他 || 3,650,000 || 15.5%
|}
"""


def read(wikitext: str, name: str = "X", lang: str = "en") -> dict:
    rec = cw.build_one(name, [(lang, "X", wikitext)])
    assert rec is not None
    return rec


def by_group(rec: dict) -> dict[str, dict]:
    return {r["group"]: r for r in rec["ethnicity"]}


class ThePlainTable(unittest.TestCase):
    def test_shares_as_printed_with_the_shortfall_as_the_remainder(self):
        rec = read(PLAIN)
        self.assertEqual(rec["ethnicity_year"], 2010)
        rows = by_group(rec)
        # 79.54 + 17.11 + 1.83 + 0.49 + 0.11 + 0.07 = 99.15: the table stops
        # after six groups and the rest is written as the remainder.
        self.assertEqual(rows["Han Chinese"]["pct"], 79.5)
        self.assertEqual(rows["Han Chinese"]["count"], 19_650_687)
        self.assertEqual(rows["Other ethnic groups"]["pct"], 0.9)
        self.assertNotIn("count", rows["Other ethnic groups"])
        self.assertAlmostEqual(sum(r["pct"] for r in rec["ethnicity"]), 100.0, places=6)
        self.assertIn("leaves unprinted", rec["ethnicity_note"])

    def test_labels_are_the_ethnonym_singular_without_people(self):
        rows = by_group(read(PLAIN))
        self.assertIn("Evenk", rows)
        self.assertIn("Oroqen", rows)
        self.assertNotIn("Evenks", rows)
        self.assertNotIn("Oroqen people", rows)

    def test_the_record_is_the_shape_under_china(self):
        rec = read(PLAIN, "Inner Mongolia Autonomous Region")
        self.assertEqual(rec["level"], "admin1")
        self.assertEqual(rec["parent"], "CHN")
        self.assertEqual(rec["country"], "CHN")
        self.assertEqual(rec["name"], "Inner Mongolia Autonomous Region")
        self.assertEqual(rec["sources"][0]["field"], "ethnicity")
        self.assertIn("Sixth National Population Census (2010)", rec["sources"][0]["name"])
        self.assertTrue(rec["sources"][0]["url"].startswith("https://en.wikipedia.org/wiki/"))

    def test_the_note_is_short(self):
        note = read(PLAIN)["ethnicity_note"]
        self.assertLessEqual(note.count(". "), 3)
        self.assertTrue(note.startswith("National Bureau of Statistics of China"))


class TheOtherLayouts(unittest.TestCase):
    def test_a_transposed_table_is_read_down_its_header(self):
        rec = read(TRANSPOSED)
        self.assertEqual(rec["ethnicity_year"], 2020)
        rows = by_group(rec)
        self.assertEqual(rows["Han Chinese"]["count"], 30_000_000)
        self.assertEqual(rows["Korean"]["pct"], 0.8)
        self.assertEqual(rows["Other ethnic groups"]["count"], 250_000)

    def test_a_table_on_one_line_is_split_at_its_row_markers(self):
        rec = read(ONE_LINE)
        self.assertEqual(rec["ethnicity_year"], 2000)
        rows = by_group(rec)
        self.assertEqual(rows["Korean"]["count"], 1_145_688)
        self.assertEqual(len(rows), 5)

    def test_rows_that_end_in_html_tr_are_rows(self):
        rec = read(HTML_ROWS)
        self.assertEqual(rec["ethnicity_year"], 2000)
        rows = by_group(rec)
        self.assertEqual(rows["Manchu"]["count"], 993_112)
        self.assertEqual(rows["Han Chinese"]["pct"], 90.9)   # 90.85 of a printed 99.94
        self.assertEqual(len(rows), 5)

    def test_a_title_in_a_header_cell_becomes_the_caption_and_the_year(self):
        rec = read(TITLE_IN_CELL)
        self.assertEqual(rec["ethnicity_year"], 2000)
        self.assertIn("Ethnic groups in Hebei, 2000 census", rec["ethnicity_note"])
        self.assertNotIn("colspan", rec["ethnicity_note"])
        # 0.031% rounds to 0.0 and is kept: below 0.05% is a measurement.
        self.assertEqual(by_group(rec)["Zhuang"], {"group": "Zhuang", "pct": 0.0, "count": 20_832})

    def test_a_template_ending_in_pipe_braces_does_not_close_a_table(self):
        # Tianjin: {{Historical populations ... |}} precedes the table, and
        # a reader that took "|}}" for a table end lost the table.
        rec = read(AFTER_TEMPLATE)
        self.assertEqual(rec["ethnicity_year"], 2000)
        rows = by_group(rec)
        self.assertEqual(rows["Hui"]["count"], 172_357)
        self.assertIn("Ethnic groups in Tianjin, 2000 census", rec["ethnicity_note"])

    def test_percent_spelled_out_is_still_a_share(self):
        self.assertEqual(cw.number("44.96 percent"), 44.96)
        self.assertEqual(cw.number("0.080 percent"), 0.08)
        self.assertEqual(cw.number("11,624,257"), 11_624_257)
        self.assertIsNone(cw.number("—"))
        self.assertIsNone(cw.number("－"))
        rec = read(PERCENT_WORD)
        self.assertEqual(by_group(rec)["Uyghur"]["pct"], 45.0)


class TheChineseEdition(unittest.TestCase):
    def test_traditional_characters_name_the_same_nationalities(self):
        rec = read(TRADITIONAL, "Liaoning Province", "zh")
        self.assertEqual(rec["ethnicity_year"], 2020)
        rows = by_group(rec)
        self.assertEqual(rows["Han Chinese"]["count"], 36_169_617)
        self.assertEqual(rows["Korean"]["count"], 229_158)
        self.assertEqual(rows["Manchu"]["pct"], 12.0)   # 5,085,984 of the 42,227,867 counted
        self.assertEqual(rows["Other ethnic groups"]["count"], 45_348)
        self.assertIn("Yao (China)", rows)
        self.assertEqual(set(rows), {"Han Chinese", "Manchu", "Mongol", "Korean",
                                     "Yao (China)", "Other ethnic groups"})
        self.assertIn("Chinese Wikipedia article", rec["ethnicity_note"])
        self.assertTrue(rec["sources"][0]["url"].startswith("https://zh.wikipedia.org/wiki/"))

    def test_the_undetermined_row_folds_into_the_remainder_and_the_note_says_so(self):
        rec = read(UNLISTED, "Guizhou Province", "zh")
        rows = by_group(rec)
        self.assertNotIn("未定族称人口", rows)
        self.assertEqual(rows["Other ethnic groups"]["count"], 698_234 + 6_134_514)
        self.assertIn("未定族称人口", rec["ethnicity_note"])
        self.assertIn("folded in", rec["ethnicity_note"])

    def test_the_later_census_wins_whichever_edition_carries_it(self):
        rec = cw.build_one("Hebei Province", [("en", "Hebei", TITLE_IN_CELL),
                                              ("zh", "河北省", UNLISTED)])
        self.assertEqual(rec["ethnicity_year"], 2020)
        self.assertIn("zh.wikipedia.org", rec["sources"][0]["url"])
        # The same year: the table naming more nationalities is read...
        rec = cw.build_one("X", [("en", "X", TRANSPOSED), ("zh", "X", TRADITIONAL)])
        self.assertIn("zh.wikipedia.org", rec["sources"][0]["url"])
        # ...and on a full tie the English article is.
        rec = cw.build_one("X", [("zh", "X", TRANSPOSED), ("en", "X", TRANSPOSED)])
        self.assertIn("en.wikipedia.org", rec["sources"][0]["url"])


class CountsBeatPrintedShares(unittest.TestCase):
    def test_shandong_other_is_its_count_not_its_printed_share(self):
        rec = read(SHANDONG)
        rows = by_group(rec)
        # Printed 0.003%; 310,738 of 101,527,453 is 0.306%.
        self.assertEqual(rows["Other ethnic groups"]["pct"], 0.3)
        self.assertEqual(rows["Han Chinese"]["pct"], 99.1)
        self.assertEqual(rows["Tibetan"]["count"], 4_352)
        self.assertNotIn("Zang (Tibetan)", rows)
        self.assertIn("computed from the printed counts", rec["ethnicity_note"])

    def test_counts_that_miss_the_printed_total_are_refused(self):
        wrong = SHANDONG.replace("101,527,453", "111,527,453")
        with self.assertRaises(SystemExit):
            read(wrong)


class Refusals(unittest.TestCase):
    def test_shares_past_the_tolerance_are_refused(self):
        wrong = PLAIN.replace("79.54%", "70.54%")   # 90.15: not a whole population
        with self.assertRaises(SystemExit):
            read(wrong)

    def test_an_article_without_the_table_is_not_written(self):
        self.assertIsNone(cw.build_one("X", [("en", "X", "== Demographics ==\nProse only.\n")]))

    def test_a_time_series_is_not_a_composition(self):
        self.assertIsNone(cw.build_one("X", [("en", "X", SERIES)]))

    def test_a_table_that_is_not_a_census_is_passed_over(self):
        self.assertIsNone(cw.build_one("X", [("zh", "X", SAMPLE_2015)]))

    def test_a_nationality_listed_twice_is_refused(self):
        twice = PLAIN.replace("[[Manchu]] || 452,765 || 1.83%", "[[Mongols|Mongol]] || 452,765 || 1.83%")
        with self.assertRaises(SystemExit):
            read(twice)

    def test_a_figure_under_an_unknown_label_is_refused(self):
        unknown = PLAIN.replace("[[Daur people|Daur]]", "Taranchis")
        with self.assertRaises(SystemExit):
            read(unknown)
        # A footnote row with no figure is not a refusal.
        note = PLAIN.replace("|}", "|-\n| colspan=3 | Excludes members of the PLA.\n|}")
        self.assertEqual(len(read(note)["ethnicity"]), 7)


class TheBeijingCrossCheck(unittest.TestCase):
    GOOD = """{| class="wikitable"
|+ Ethnic groups in Beijing, 2010 census
! Ethnicity !! Population !! Percentage
|-
| Han || 18,811,000 || 95.9%
|-
| Manchu || 336,000 || 1.7%
|-
| Hui || 249,000 || 1.3%
|-
| Others || 216,000 || 1.1%
|}
"""

    def test_agreement_with_the_communique_is_in_the_note(self):
        rec = read(self.GOOD, "Beijing Municipality")
        self.assertEqual(by_group(rec)["Han Chinese"]["pct"], 95.9)
        self.assertIn("Agrees with", rec["ethnicity_note"])
        for url in cw.BEIJING_URLS:
            self.assertIn(url, rec["ethnicity_note"])

    def test_disagreement_is_published_with_one_sentence(self):
        off = self.GOOD.replace("336,000", "436,000").replace("216,000", "116,000")
        rec = read(off, "Beijing Municipality")
        self.assertIn("against Manchu 436,000 here", rec["ethnicity_note"])
        self.assertNotIn("Agrees", rec["ethnicity_note"])
        for url in cw.BEIJING_URLS:
            self.assertIn(url, rec["ethnicity_note"])

    def test_a_2020_row_carries_the_2010_figures_for_comparison(self):
        rec = read(self.GOOD.replace("2010 census", "2020 census"), "Beijing Municipality")
        self.assertEqual(rec["ethnicity_year"], 2020)
        self.assertIn("For comparison", rec["ethnicity_note"])


class WholeHundred(unittest.TestCase):
    def test_largest_remainder_sums_to_exactly_one_hundred(self):
        out = cw.whole_hundred([("a", 33.33), ("b", 33.33), ("c", 33.34)])
        self.assertAlmostEqual(sum(out), 100.0, places=9)
        self.assertEqual(sorted(out), [33.3, 33.3, 33.4])


class TheShapeNames(unittest.TestCase):
    def test_thirty_one_divisions_named_as_the_boundary_file_names_them(self):
        names = [n for n, _, _ in cw.DIVISIONS]
        self.assertEqual(len(names), 31)
        self.assertEqual(len(set(names)), 31)
        self.assertIn("Guangdong", names)
        self.assertIn("Ningxia Hui Autonomous Region", names)
        self.assertNotIn("Hong Kong Special Administrative Region", names)

    def test_every_label_the_reader_can_write_is_placed_in_the_group_tree(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import canonical_groups as cg
        unplaced = sorted({label for label in cw.NATIONALITIES.values()
                           if len(cg.ancestry("ethnicity", label)) < 2})
        # The two the tree deliberately leaves: the Yugur speak a Turkic and
        # a Mongolic language by half, and the Gaoshan are Formosan.
        self.assertEqual(unplaced, ["Gaoshan", "Yugur"])
        self.assertEqual(cg.ancestry("ethnicity", "Yao (China)")[1],
                         "Mainland Southeast Asian peoples")


if __name__ == "__main__":
    unittest.main()
