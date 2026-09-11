"""Hankook Research's residence-region page as a PDF reader prints it."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from scripts.fetch_census import korea_survey  # noqa: E402

# Page 8 of weekly report No. 358-3 as the runner's PDF reader printed it
# (it drops the spaces inside Korean phrases: "개신교신자"), the
# residence-region block and the rows around it.
PAGE = """한국리서치 주간리포트
8
(단위: %, %포인트)
종교인구비율49%, 전년과동일
주요종교별신자비율도지난해와동일
개신교신자 천주교신자 불교신자 믿는종교있음 믿는종교없음
‘24년 ‘25년
차이
(25년-
24년)
전체 20 20 - 11 11 - 16 16 - 49 49 - 51 51 -
성별
남자 18 18 - 10 10 - 16 16 - 45 45 - 55 55 -
여자 22 22 - 12 12 - 17 17 - 53 53 - 47 47 -
연령
18-29세 13 13 - 7 5 -2 8 8 - 30 28 -2 70 72 +2
거주지역
서울 22 22 - 13 13 - 13 13 - 50 49 -1 50 51 +1
인천/경기 22 21 -1 12 12 - 12 12 - 48 47 -1 52 53 +1
대전/세종/충청 21 21 - 10 10 - 16 15 -1 48 47 -1 52 53 +1
광주/전라 25 25 - 10 11 +1 11 11 - 49 49 - 51 51 -
대구/경북 15 17 +2 10 10 - 24 23 -1 51 51 - 49 49 -
부산/울산/경남 14 13 -1 7 7 - 29 29 - 52 51 -1 48 49 +1
강원/제주 17 16 -1 10 16 +6 19 18 -1 48 51 +3 52 49 -3
"""
OTHER_PAGE = "한국리서치 주간리포트\n9\n천주교 신자 50%, 개신교 신자 44%\n"


class Reading(unittest.TestCase):
    def test_the_2025_column_is_read_and_other_is_the_remainder(self):
        table = korea_survey.read(OTHER_PAGE + "\f" + PAGE)
        self.assertEqual(len(table), 7)
        self.assertEqual(table["Seoul"], {"Protestant": 22.0, "Roman Catholic": 13.0,
                                          "Buddhism": 13.0, "Other religions": 1.0,
                                          "No religion": 51.0})
        self.assertEqual(table["Busan/Ulsan/Gyeongnam"]["Buddhism"], 29.0)
        self.assertEqual(table["Busan/Ulsan/Gyeongnam"]["Other religions"], 2.0)
        self.assertEqual(table["Gangwon/Jeju"]["Roman Catholic"], 16.0)

    def test_a_reader_that_keeps_the_spaces_in_the_heads_also_reads(self):
        page = PAGE.replace("개신교신자 천주교신자 불교신자 믿는종교있음 믿는종교없음",
                            "개신교 신자 천주교 신자 불교 신자 믿는 종교 있음 믿는 종교 없음")
        self.assertEqual(korea_survey.read(page)["Seoul"]["Protestant"], 22.0)

    def test_a_row_split_over_lines_still_reads(self):
        page = PAGE.replace("서울 22 22 - 13 13 -", "서울 22 22 -\n13 13 -")
        self.assertEqual(korea_survey.read(page)["Seoul"]["Roman Catholic"], 13.0)

    def test_each_province_carries_its_grouping(self):
        records = korea_survey.build(PAGE)
        self.assertEqual(len(records), 17)
        by_name = {r["name"]: r for r in records}
        self.assertEqual(by_name["Sejong"]["religion"],
                         by_name["North Chungcheong"]["religion"])
        self.assertEqual(by_name["Sejong"]["religion"][0], {"group": "No religion", "pct": 53.0})
        self.assertIn("one of the 4 provinces", by_name["Sejong"]["religion_note"])
        self.assertIn("the only province", by_name["Seoul"]["religion_note"])
        self.assertEqual(by_name["Seoul"]["religion_year"], 2025)
        self.assertEqual(by_name["Ulsan"]["id"], "KOR-ulsan")
        self.assertEqual({r["parent"] for r in records}, {"KOR"})


class Refusals(unittest.TestCase):
    def test_has_and_none_must_sum_to_100(self):
        page = PAGE.replace("서울 22 22 - 13 13 - 13 13 - 50 49 -1 50 51 +1",
                            "서울 22 22 - 13 13 - 13 13 - 50 48 -2 50 51 +1")
        with self.assertRaises(SystemExit):
            korea_survey.read(page)

    def test_the_named_faiths_may_not_exceed_has_religion(self):
        page = PAGE.replace("서울 22 22 - 13 13 - 13 13 - 50 49 -1 50 51 +1",
                            "서울 22 32 - 13 13 - 13 13 - 50 49 -1 50 51 +1")
        with self.assertRaises(SystemExit):
            korea_survey.read(page)

    def test_the_national_row_must_agree_with_the_weighted_regions(self):
        page = PAGE.replace("전체 20 20 - 11 11 -", "전체 20 25 - 11 11 -")
        with self.assertRaises(SystemExit):
            korea_survey.read(page)

    def test_a_missing_region_refuses(self):
        page = PAGE.replace("강원/제주 17 16 -1 10 16 +6 19 18 -1 48 51 +3 52 49 -3", "")
        with self.assertRaises(SystemExit):
            korea_survey.read(page)

    def test_a_short_row_refuses(self):
        page = PAGE.replace("강원/제주 17 16 -1 10 16 +6 19 18 -1 48 51 +3 52 49 -3",
                            "강원/제주 17 16 -1 10 16 +6 19 18 -1 48 51 +3 52")
        with self.assertRaises(SystemExit):
            korea_survey.read(page)


if __name__ == "__main__":
    unittest.main()
