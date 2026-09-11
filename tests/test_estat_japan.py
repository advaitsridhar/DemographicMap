"""Japan: the e-Stat figures that refuse to become a composition.

Every number here is what e-Stat's API served a GitHub Actions runner, which is
the only place in this project with egress to ``api.e-stat.go.jp``. Nothing is
mocked and nothing is rounded:

* ``BELIEVERS`` is 信者数, all systems, from statsDataId **0003282963** --
  宗教統計調査 (00401101, Agency for Cultural Affairs), 全国社寺教会等宗教団体・
  教師・信者数（２）都道府県別, at 2025年度, which is 31 December 2024. Read with
  ``cdCat02=140`` (計), ``cdCat03=110`` (信者), ``cdCat04=100`` (総数).
* ``TOKYO``, ``KANAGAWA`` and ``KYOTO`` are the same table's 宗教系統 split for
  those three prefectures, read in one call with ``cdCat01=13000,14000,26000``,
  and the four ``*_NATIONAL`` figures are its 全国 row read the same way.
  ``BUDDHIST_PREFECTURES`` is the sum of its 47 仏教系 rows, taken from the
  Agency's yearbook workbook for the same table and the same date because the
  API answer was read a page at a time; the two agree on every row compared,
  which is 富山 through 沖縄 plus the three prefectures above.
* ``POPULATION`` is 総人口 from statsDataId **0000010101**, 社会・人口統計体系
  都道府県データ, item ``A1101``, at 2024年度. Published to the nearest thousand,
  which is why its national row and the sum of its prefectures differ by 1,000.
* ``CATALOGUE_ENTRY`` is one ``TABLE_INF`` record exactly as ``getStatsList``
  returned it, printed by ``probe_estat --raw``.

The point of pinning them is that Japan's ``religion`` declaration now rests on
this table rather than on a questionnaire, and a declaration resting on numbers
has to keep the numbers. If a later reader wants to publish 宗教統計調査 by
prefecture, these tests say exactly what stops it: 175 million believers in a
country of 124 million, distributed by where a religious corporation is
registered rather than by where anyone lives.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import scripts.probe_estat as probe_estat  # noqa: E402
from scripts.fetch_census._shared import shares  # noqa: E402

BELIEVERS = {
    0: 175054047,      # 全国, the table's own national row
    1: 5800989,     # Hokkaido 北海道
    2: 1077144,     # Aomori 青森
    3: 2187853,     # Iwate 岩手
    4: 2733511,     # Miyagi 宮城
    5: 1009614,     # Akita 秋田
    6: 2010209,     # Yamagata 山形
    7: 1577495,     # Fukushima 福島
    8: 2921941,     # Ibaraki 茨城
    9: 2476922,     # Tochigi 栃木
    10: 1801852,     # Gunma 群馬
    11: 5990586,     # Saitama 埼玉
    12: 3503964,     # Chiba 千葉
    13: 43771635,    # Tokyo 東京
    14: 4962846,     # Kanagawa 神奈川
    15: 2901150,     # Niigata 新潟
    16: 2403005,     # Toyama 富山
    17: 2233286,     # Ishikawa 石川
    18: 1225060,     # Fukui 福井
    19: 2042510,     # Yamanashi 山梨
    20: 5944077,     # Nagano 長野
    21: 3791312,     # Gifu 岐阜
    22: 4320946,     # Shizuoka 静岡
    23: 6853384,     # Aichi 愛知
    24: 3008039,     # Mie 三重
    25: 1960021,     # Shiga 滋賀
    26: 8042777,     # Kyoto 京都
    27: 9211833,     # Osaka 大阪
    28: 7622979,     # Hyogo 兵庫
    29: 1523411,     # Nara 奈良
    30: 1113630,     # Wakayama 和歌山
    31: 501529,      # Tottori 鳥取
    32: 1822929,     # Shimane 島根
    33: 2345353,     # Okayama 岡山
    34: 3673559,     # Hiroshima 広島
    35: 2106124,     # Yamaguchi 山口
    36: 608372,      # Tokushima 徳島
    37: 1309615,     # Kagawa 香川
    38: 1677104,     # Ehime 愛媛
    39: 561292,      # Kochi 高知
    40: 4364012,     # Fukuoka 福岡
    41: 1165499,     # Saga 佐賀
    42: 1785925,     # Nagasaki 長崎
    43: 1681524,     # Kumamoto 熊本
    44: 1677838,     # Oita 大分
    45: 947335,      # Miyazaki 宮崎
    46: 1896516,     # Kagoshima 鹿児島
    47: 895540,      # Okinawa 沖縄
}

POPULATION = {
    0: 123802000,      # 全国
    1: 5043000,     # Hokkaido
    2: 1165000,     # Aomori
    3: 1145000,     # Iwate
    4: 2248000,     # Miyagi
    5: 897000,      # Akita
    6: 1011000,     # Yamagata
    7: 1743000,     # Fukushima
    8: 2806000,     # Ibaraki
    9: 1885000,     # Tochigi
    10: 1890000,     # Gunma
    11: 7332000,     # Saitama
    12: 6251000,     # Chiba
    13: 14178000,    # Tokyo
    14: 9225000,     # Kanagawa
    15: 2099000,     # Niigata
    16: 997000,      # Toyama
    17: 1098000,     # Ishikawa
    18: 739000,      # Fukui
    19: 791000,      # Yamanashi
    20: 1987000,     # Nagano
    21: 1916000,     # Gifu
    22: 3527000,     # Shizuoka
    23: 7460000,     # Aichi
    24: 1711000,     # Mie
    25: 1402000,     # Shiga
    26: 2520000,     # Kyoto
    27: 8757000,     # Osaka
    28: 5337000,     # Hyogo
    29: 1285000,     # Nara
    30: 880000,      # Wakayama
    31: 531000,      # Tottori
    32: 642000,      # Shimane
    33: 1831000,     # Okayama
    34: 2714000,     # Hiroshima
    35: 1281000,     # Yamaguchi
    36: 685000,      # Tokushima
    37: 917000,      # Kagawa
    38: 1276000,     # Ehime
    39: 656000,      # Kochi
    40: 5092000,     # Fukuoka
    41: 788000,      # Saga
    42: 1252000,     # Nagasaki
    43: 1697000,     # Kumamoto
    44: 1085000,     # Oita
    45: 1033000,     # Miyazaki
    46: 1532000,     # Kagoshima
    47: 1466000,     # Okinawa
}

# The four 宗教系統 as 0003282963 gives them, for the three prefectures that
# show what the systems do to a composition.
TOKYO = {"Shinto": 7214991, "Buddhist": 35352899,
         "Christian": 878497, "Other": 325248}
KANAGAWA = {"Shinto": 2393960, "Buddhist": 1762105,
            "Christian": 298669, "Other": 508112}
KYOTO = {"Shinto": 6211472, "Buddhist": 1521269,
         "Christian": 21693, "Other": 288343}

# The four systems' 全国 rows from the same table (``cdCat01=00000``), and the
# sum of the 47 仏教系 prefecture rows read in the call beside them. The first
# is the denominator for "43.9% of every Buddhist in Japan"; the pair is where
# the table's own ten-thousand discrepancy lives.
SHINTO_NATIONAL = 86359612
BUDDHIST_NATIONAL = 80463918
CHRISTIAN_NATIONAL = 1872320
OTHER_NATIONAL = 6358197
BUDDHIST_PREFECTURES = 80453918

# One catalogue record, verbatim. Its shape is the thing under test: e-Stat
# writes a labelled code as an object and an unlabelled one as a bare string,
# in the same record.
CATALOGUE_ENTRY = json.loads("""{
  "@id": "0003282942",
  "STAT_NAME": {"@code": "00401101", "$": "\u5b97\u6559\u7d71\u8a08\u8abf\u67fb"},
  "GOV_ORG": {"@code": "00401", "$": "\u6587\u5316\u5e81"},
  "STATISTICS_NAME": "\u5b97\u6559\u7d71\u8a08\u8abf\u67fb",
  "TITLE": {"@no": "1", "$": "\u5b97\u6559\u6cd5\u4eba\u6570\u7dcf\u62ec\u8868"},
  "CYCLE": "-",
  "SURVEY_DATE": "202404-202503",
  "OPEN_DATE": "2025-12-24",
  "SMALL_AREA": 0,
  "COLLECT_AREA": "\u8a72\u5f53\u306a\u3057",
  "OVERALL_TOTAL_NUMBER": 1617,
  "UPDATED_DATE": "2026-01-14",
  "TITLE_SPEC": {"TABLE_NAME": "\u5b97\u6559\u6cd5\u4eba\u6570\u7dcf\u62ec\u8868"}
}""")

PREFECTURES = [code for code in BELIEVERS if code]


class TheTableDoesNotPartitionAPopulation(unittest.TestCase):
    """The whole of Japan's religion refusal, in four numbers."""

    def test_there_are_forty_seven_prefectures_and_one_national_row(self):
        self.assertEqual(len(PREFECTURES), 47)
        self.assertEqual(sorted(PREFECTURES), list(range(1, 48)))
        self.assertEqual(sorted(POPULATION), sorted(BELIEVERS))

    def test_believers_outnumber_people_by_forty_one_per_cent(self):
        ratio = BELIEVERS[0] / POPULATION[0]
        self.assertAlmostEqual(ratio, 1.414, places=3)
        # And it is not an artefact of the national row: the prefecture rows
        # say the same thing on their own.
        summed = sum(BELIEVERS[c] for c in PREFECTURES) / sum(
            POPULATION[c] for c in PREFECTURES)
        self.assertAlmostEqual(summed, 1.414, places=3)

    def test_the_national_row_is_ten_thousand_above_its_own_prefectures(self):
        """The table does not even sum to itself, and the gap is Buddhist."""
        self.assertEqual(BELIEVERS[0] - sum(BELIEVERS[c] for c in PREFECTURES),
                         10000)
        # The same table read by 宗教系統: its 全国 Buddhist row and its 47
        # Buddhist prefecture rows are the same ten thousand apart, and the
        # other three systems agree to the person. So the discrepancy is one
        # unallocated round number in one system rather than noise everywhere.
        self.assertEqual(BUDDHIST_NATIONAL - BUDDHIST_PREFECTURES, 10000)
        self.assertEqual(BELIEVERS[0],
                         SHINTO_NATIONAL + BUDDHIST_NATIONAL
                         + CHRISTIAN_NATIONAL + OTHER_NATIONAL)

    def test_the_excess_is_uneven_enough_to_redraw_the_map(self):
        """A uniform 1.41 would only be a scale error. This is not uniform."""
        ratios = {c: BELIEVERS[c] / POPULATION[c] for c in PREFECTURES}
        low = min(ratios, key=ratios.get)
        high = max(ratios, key=ratios.get)
        self.assertEqual((low, high), (14, 26))            # Kanagawa, Kyoto
        self.assertAlmostEqual(ratios[low], 0.54, places=2)
        self.assertAlmostEqual(ratios[high], 3.19, places=2)
        self.assertGreater(ratios[high] / ratios[low], 5.5)
        # Tokyo, where the head temples are registered.
        self.assertAlmostEqual(ratios[13], 3.09, places=2)

    def test_one_prefecture_holds_two_fifths_of_the_buddhists(self):
        """Registration, not residence: the reason the spread exists."""
        tokyo_share = TOKYO["Buddhist"] / BUDDHIST_NATIONAL
        kanagawa_share = KANAGAWA["Buddhist"] / BUDDHIST_NATIONAL
        people = sum(POPULATION[c] for c in PREFECTURES)
        self.assertAlmostEqual(tokyo_share, 0.439, places=3)
        self.assertAlmostEqual(POPULATION[13] / people, 0.115, places=3)
        self.assertAlmostEqual(kanagawa_share, 0.022, places=3)
        self.assertAlmostEqual(POPULATION[14] / people, 0.075, places=3)
        # Kyoto's excess is Shinto, not Buddhist -- the same artefact from the
        # other side, which is why "Tokyo is just big" does not explain it.
        self.assertLess(KYOTO["Buddhist"] / BUDDHIST_NATIONAL, 0.02)
        self.assertGreater(KYOTO["Shinto"], 4 * KYOTO["Buddhist"])

    def test_shares_of_it_would_describe_head_offices_not_belief(self):
        """What the project's own helper would make of these rows."""
        tokyo = {row["group"]: row["pct"] for row in shares(TOKYO)}
        kyoto = {row["group"]: row["pct"] for row in shares(KYOTO)}
        kanagawa = {row["group"]: row["pct"] for row in shares(KANAGAWA)}
        self.assertEqual(tokyo["Buddhist"], 80.8)
        self.assertEqual(kyoto["Buddhist"], 18.9)
        self.assertEqual(kanagawa["Buddhist"], 35.5)
        # Each set sums to 100 because shares() normalises by its own total --
        # which is exactly the trap. The denominator is believers, not people,
        # and nothing downstream would notice.
        for composition in (tokyo, kyoto, kanagawa):
            self.assertLess(abs(sum(composition.values()) - 100.0), 0.2)

    def test_as_a_share_of_people_it_does_not_fit_in_a_hundred(self):
        """The check any adapter would have to pass, and this table fails."""
        for code in (13, 26, 20, 32):
            counted = BELIEVERS[code] / POPULATION[code] * 100
            self.assertGreater(counted, 100.0)


class TheKeyNeverReachesTheLog(unittest.TestCase):
    """A probe whose product is a committed log has to scrub its own output."""

    def test_scrub_removes_the_key_from_anything_printed(self):
        with mock.patch.dict("os.environ", {"ESTAT_API": "s3cr3t-app-id"}):
            line = ("getStatsList?appId=s3cr3t-app-id&searchWord=x "
                    "failed: HTTP 403 for s3cr3t-app-id")
            scrubbed = probe_estat.scrub(line)
        self.assertNotIn("s3cr3t-app-id", scrubbed)
        self.assertEqual(scrubbed.count("<ESTAT_API>"), 2)

    def test_a_printed_request_never_carries_the_credential(self):
        shown = probe_estat.shown_call("getStatsList", {"searchWord": "宗教"})
        self.assertNotIn("appId", shown)

    def test_a_missing_key_names_the_variable_and_echoes_nothing(self):
        with mock.patch.dict("os.environ", {"ESTAT_API": ""}):
            with self.assertRaises(SystemExit) as raised:
                probe_estat.app_id()
        message = str(raised.exception)
        self.assertIn("ESTAT_API", message)
        self.assertIn("e-stat.go.jp", message)


class ReadingWhatTheCatalogueSays(unittest.TestCase):
    """The record shape, against the bytes rather than against a guess."""

    def test_a_labelled_code_and_a_bare_string_read_the_same_way(self):
        self.assertEqual(probe_estat.text_of(CATALOGUE_ENTRY["STAT_NAME"]),
                         "宗教統計調査")
        self.assertEqual(probe_estat.code_of(CATALOGUE_ENTRY["STAT_NAME"]),
                         "00401101")
        self.assertEqual(probe_estat.text_of(CATALOGUE_ENTRY["STATISTICS_NAME"]),
                         "宗教統計調査")
        self.assertEqual(probe_estat.code_of(CATALOGUE_ENTRY["STATISTICS_NAME"]), "")

    def test_one_line_names_the_table_its_agency_and_its_geography(self):
        line = probe_estat.one_line(CATALOGUE_ENTRY)
        self.assertIn("0003282942", line)
        self.assertIn("00401101", line)
        self.assertIn("文化庁", line)
        self.assertIn("宗教法人数総括表", line)
        self.assertIn("survey 202404-202503", line)
        # The geography is the field that decides usefulness, so it is
        # translated rather than passed through.
        self.assertIn("該当なし (no area dimension)", line)

    def test_one_of_a_thing_and_several_of_it_read_alike(self):
        """e-Stat gives an object for one row and an array for many."""
        self.assertEqual(probe_estat.listed(CATALOGUE_ENTRY), [CATALOGUE_ENTRY])
        self.assertEqual(probe_estat.listed([CATALOGUE_ENTRY, CATALOGUE_ENTRY]),
                         [CATALOGUE_ENTRY, CATALOGUE_ENTRY])
        self.assertEqual(probe_estat.listed(None), [])

    def test_an_empty_answer_is_an_answer_and_not_a_failure(self):
        """status 1 is e-Stat saying the word matches nothing, which is the
        finding this probe most wants: 信徒 matched 0 tables."""
        empty = {"GET_STATS_LIST": {"RESULT": {
            "STATUS": 1,
            "ERROR_MSG": "正常に終了しましたが、該当データはありませんでした。"}}}
        status, message, _ = probe_estat.result_of(empty, "GET_STATS_LIST")
        self.assertEqual(status, 1)
        self.assertIn("該当データはありません", message)

    def test_a_transport_failure_is_told_apart_from_an_api_refusal(self):
        broken = {"__error__": "URLError: timed out"}
        status, message, inner = probe_estat.result_of(broken, "GET_STATS_LIST")
        self.assertEqual(status, -1)
        self.assertIn("URLError", message)
        self.assertEqual(inner, {})


if __name__ == "__main__":
    unittest.main()
