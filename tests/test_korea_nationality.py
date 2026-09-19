"""Korea's nationality file: the Ministry of Justice's district table as the
runner read it, the resident register beside it, and what the composition
promises.

The Ministry's file is synthetic here but shaped as the runner's inspect
run printed it (data/processed/last-run.log of 19 September 2026): 시도,
시군구 (그룹), 성별, 총합계, then the nationalities from 한국계중국인 to 기타,
two rows per unit, a city's districts listed as "수원시 장안구".
"""

import csv
import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import canonical_groups as cg  # noqa: E402
import common  # noqa: E402
from scripts import build_entities as be  # noqa: E402
from scripts.fetch_census import korea_nationality as m  # noqa: E402

NATIONALITY_COLUMNS = ["한국계중국인", "베트남", "중국", "네팔", "우즈베키스탄", "미국",
                       "루마니아", "기타"]


def moj_rows(units):
    """A Ministry table over ``units``: {(sido, sigungu): [male counts, female
    counts]} per nationality column, the total written as their sum."""
    header = [m.COL_SIDO, "시군구 (그룹)", m.COL_SEX, m.COL_TOTAL] + NATIONALITY_COLUMNS
    table = [header]
    for (sido, gu), (male, female) in units.items():
        for sex, counts in (("남성", male), ("여성", female)):
            table.append([sido, gu, sex, f"{sum(counts)} "] + [f"{c} " for c in counts])
    return table


def every_unit(male_scale=1):
    """One row pair for every district the boundary table knows, plus the
    undrawn Yeonggwang-gun, with small distinct counts."""
    units = {}
    korean_of = {v: k for k, v in m.SIDO.items() if k not in ("강원도", "전라북도")}
    i = 0
    for province, table in m.DISTRICTS.items():
        for word, shape in table.items():
            if word == "세종시" or (word == "군위군" and province == "North Gyeongsang"):
                continue
            i += 1
            counts = [30 + i, 20, 10, 5, 4, 3, 1, 2]
            units[(korean_of[province], word)] = ([c * male_scale for c in counts],
                                                  [c for c in counts])
    units[("전라남도", "영광군")] = ([10, 5, 3, 1, 1, 1, 0, 1], [8, 4, 2, 1, 1, 0, 0, 1])
    return units


def register_for(units):
    """A resident register with 10,000 Koreans per unit and the provinces'
    rows as the exact sums."""
    out = {}
    for (sido, gu), _ in units.items():
        out[(m.SIDO[sido], gu.split()[0])] = 10_000
    for province in set(m.SIDO.values()):
        out[(province, "")] = sum(v for (p, w), v in out.items() if p == province and w)
    return out


class ReadingTheMinistrysFile(unittest.TestCase):
    def test_sexes_are_summed_and_a_citys_districts_fold_into_the_city(self):
        table = moj_rows({
            ("경기도", "수원시 장안구"): ([1, 2, 3, 0, 0, 0, 0, 1], [1, 1, 1, 0, 0, 0, 0, 0]),
            ("경기도", "수원시 권선구"): ([5, 0, 0, 0, 0, 0, 0, 0], [0, 5, 0, 0, 0, 0, 0, 0]),
            ("강원특별자치도", "고성군"): ([1, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 1]),
        })
        units = m.read_moj(table)
        self.assertEqual(set(units), {("Gyeonggi", "수원시"), ("Gangwon", "고성군")})
        suwon = units[("Gyeonggi", "수원시")]
        self.assertEqual(suwon["한국계중국인"], 7)
        self.assertEqual(suwon["베트남"], 8)
        self.assertEqual(suwon["__total__"], 20)

    def test_a_row_whose_nationalities_do_not_make_its_total_is_refused(self):
        table = moj_rows({("서울특별시", "종로구"): ([1, 1, 1, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0, 0])})
        table[1][3] = "99 "
        with self.assertRaises(SystemExit):
            m.read_moj(table)

    def test_an_unknown_province_is_refused(self):
        table = moj_rows({("평안남도", "평양시"): ([1, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0])})
        with self.assertRaises(SystemExit):
            m.read_moj(table)

    def test_a_zip_with_cp949_member_names_is_opened(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("2023 table.csv", "시도,시군구,성별,총합계\r\n".encode("cp949"))
        found = m.members(buf.getvalue())
        self.assertEqual(list(found), ["2023 table.csv"])
        self.assertEqual(m.rows_of(found["2023 table.csv"])[0],
                         ["시도", "시군구", "성별", "총합계"])

    def test_a_bare_csv_is_one_member(self):
        self.assertEqual(list(m.members(b"a,b\r\n1,2\r\n")), ["-"])


class ReadingTheRegister(unittest.TestCase):
    """The resident register's CSVs as jumin.mois.go.kr's form answers them:
    the province listing, then a province's districts with the districts
    of a city listed beside the city."""

    HEADER = ["행정구역", "2023년12월_총인구수", "2023년12월_세대수"]

    def test_provinces_and_the_national_row(self):
        table = [self.HEADER,
                 ["전국  (1000000000)", "51,325,329", "23,914,851"],
                 ["서울특별시  (1100000000)", "9,386,034", "4,469,417"],
                 ["강원특별자치도  (5100000000)", "1,527,807", "760,635"]]
        out = m.read_register([table])
        self.assertEqual(out[("", "")], 51_325_329)
        self.assertEqual(out[("Seoul", "")], 9_386_034)
        self.assertEqual(out[("Gangwon", "")], 1_527_807)

    def test_a_citys_own_districts_are_skipped_and_a_gu_with_an_odd_code_is_not(self):
        gyeonggi = [self.HEADER,
                    ["경기도  (4100000000)", "13,630,821", "5,978,724"],
                    ["경기도 수원시 (4111000000)", "1,190,000", "1"],
                    ["경기도 수원시 장안구 (4111100000)", "270,000", "1"],
                    ["경기도 수원시 권선구 (4111300000)", "370,000", "1"],
                    ["경기도 가평군 (4182000000)", "62,000", "1"]]
        seoul = [self.HEADER,
                 ["서울특별시  (1100000000)", "9,386,034", "1"],
                 ["서울특별시 광진구 (1121500000)", "335,000", "1"],
                 ["서울특별시 종로구 (1111000000)", "140,000", "1"]]
        out = m.read_register([gyeonggi, seoul])
        self.assertEqual(out[("Gyeonggi", "수원시")], 1_190_000)
        self.assertNotIn(("Gyeonggi", "장안구"), out)
        self.assertEqual([k for k in out if k[1] == "권선구"], [])
        self.assertEqual(out[("Gyeonggi", "가평군")], 62_000)
        self.assertEqual(out[("Seoul", "광진구")], 335_000)
        self.assertEqual(out[("Seoul", "종로구")], 140_000)

    def test_a_row_without_a_code_is_ignored_and_an_unknown_province_refused(self):
        table = [self.HEADER, ["합계", "1", "1"], ["평안남도 평양시 (9911000000)", "1", "1"]]
        with self.assertRaises(SystemExit):
            m.read_register([table])
        self.assertEqual(m.read_register([[self.HEADER, ["합계", "1", "1"]]]), {})

    def test_the_form_fields_name_the_month_and_the_level(self):
        fields = dict(m.register_fields("4100000000"))
        self.assertEqual(fields["sltOrgLvl1"], "4100000000")
        self.assertEqual(fields["sltOrgLvl2"], "A")
        self.assertEqual((fields["searchYearStart"], fields["searchMonthStart"]), ("2023", "12"))
        self.assertEqual((fields["searchYearEnd"], fields["searchMonthEnd"]), ("2023", "12"))

    def test_the_provinces_must_sum_to_the_national_row(self):
        units = every_unit()
        table = m.read_moj(moj_rows(units))
        register = register_for(units)
        register[("", "")] = sum(v for (p, w), v in register.items() if p and not w) + 1
        with self.assertRaises(SystemExit):
            m.build(table, register)


class TheDistrictTable(unittest.TestCase):
    def test_every_shape_is_named_once_and_nothing_else_is(self):
        shapes = json.loads((ROOT / "site" / "data" / "admin2" / "KOR.json").read_text())
        parents = {r["id"]: r["name"] for r in
                   json.loads((ROOT / "site" / "data" / "admin1" / "KOR.json").read_text())}
        parents["KOR"] = ""
        drawn = {(parents[r["parent"]], r["name"]) for r in shapes}
        mapped = set()
        for province, table in m.DISTRICTS.items():
            for shape in table.values():
                mapped.add((m.DRAWN_ELSEWHERE.get((province, shape), province), shape))
        self.assertEqual(len(shapes), 228)
        self.assertEqual(drawn, mapped)

    def test_the_seventeen_provinces_are_the_shape_names(self):
        provinces = {r["name"] for r in
                     json.loads((ROOT / "site" / "data" / "admin1" / "KOR.json").read_text())}
        self.assertEqual(set(m.SIDO.values()), provinces)

    def test_every_nationality_label_is_placed_in_the_tree(self):
        for label in set(m.NATIONALITIES.values()) | {m.KOREAN, m.OTHER}:
            self.assertGreater(len(cg.ancestry("ethnicity", label)), 1, label)


class TheComposition(unittest.TestCase):
    def test_shares_make_exactly_100_with_koreans_first(self):
        foreign = {"한국계중국인": 300, "중국": 100, "베트남": 50, "루마니아": 7, "기타": 3,
                   "__total__": 460}
        shares = m.composition(foreign, 9_540, ["한국계중국인", "중국", "베트남"])
        self.assertEqual(shares[0], {"group": "Korean", "pct": 95.4, "count": 9_540})
        self.assertEqual(sum(r["pct"] for r in shares), 100.0)
        by = {r["group"]: r for r in shares}
        self.assertEqual(by["Korean-Chinese"]["count"], 300)
        self.assertEqual(by["Other nationalities"]["count"], 10)
        self.assertNotIn("Romanian", by)

    def test_a_zero_group_is_dropped(self):
        foreign = {"한국계중국인": 0, "중국": 10, "__total__": 10}
        groups = [r["group"] for r in m.composition(foreign, 90, ["한국계중국인", "중국"])]
        self.assertEqual(groups, ["Korean", "Chinese"])

    def test_naming_follows_the_national_threshold(self):
        national = {"한국계중국인": 500_000, "중국": 200_000, "베트남": 200_000,
                    "미국": 50_000, "네팔": 9_999, "우즈베키스탄": 20_000, "루마니아": 5,
                    "기타": 100, "__total__": 980_104}
        self.assertEqual(m.named(national), ["한국계중국인", "중국", "베트남", "미국", "우즈베키스탄"])

    def test_a_large_nationality_with_no_label_is_refused(self):
        national = {"한국계중국인": 1, "중국": 1, "베트남": 1, "미국": 1, "루마니아": 20_000,
                    "기타": 0, "__total__": 20_004}
        with self.assertRaises(SystemExit):
            m.named(national)


class TheRecords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        units = every_unit()
        cls.units = m.read_moj(moj_rows(units))
        cls.register = register_for(units)
        saved = dict(m.PUBLISHED)
        m.PUBLISHED.clear()
        try:
            cls.records = m.build(cls.units, cls.register)
        finally:
            m.PUBLISHED.update(saved)

    def test_seventeen_provinces_and_228_districts(self):
        levels = [r["level"] for r in self.records]
        self.assertEqual(levels.count("admin1"), 17)
        self.assertEqual(levels.count("admin2"), 228)

    def test_every_record_is_a_nationality_count(self):
        for r in self.records:
            self.assertEqual(r["ethnicity_basis"], "nationality", r["name"])
            self.assertEqual(r["ethnicity_year"], 2023)
            self.assertEqual(r["ethnicity"][0]["group"], "Korean", r["name"])
            self.assertAlmostEqual(sum(s["pct"] for s in r["ethnicity"]), 100.0, places=6)
            self.assertTrue(r["ethnicity_note"].startswith("Registered foreign residents"))
            self.assertIn("not ethnicity", r["ethnicity_note"])
            self.assertIn("F-4", r["ethnicity_note"])
            self.assertFalse(common.is_estimate(r["ethnicity"]))

    def test_a_district_drawn_under_another_province_says_so(self):
        by = {(r["parent_name"], r["name"]): r for r in self.records if r["level"] == "admin2"}
        eunpyeong = by[("Gyeonggi", "Eunpyeong-gu")]
        self.assertEqual(eunpyeong["parent"], "KOR-seoul")
        self.assertIn("draws Eunpyeong-gu under Gyeonggi", eunpyeong["ethnicity_note"])
        self.assertIn("district of Seoul", eunpyeong["ethnicity_note"])
        # A shape the boundary file draws under the country itself keeps its
        # own province as parent_name: the join finds it as the one
        # Yeongdo-gu in the country, and the note says where it is drawn.
        yeongdo = by[("Busan", "Yeongdo-gu")]
        self.assertIn("under the country itself", yeongdo["ethnicity_note"])
        self.assertNotIn("draws", by[("Seoul", "Jongno-gu")]["ethnicity_note"])

    def test_the_undrawn_county_counts_in_its_province(self):
        names = {r["name"] for r in self.records}
        self.assertNotIn("Yeonggwang-gun", names)
        jeonnam = next(r for r in self.records if r["name"] == "South Jeolla")
        by = {s["group"]: s["count"] for s in jeonnam["ethnicity"]}
        expected = sum(v["한국계중국인"] for (p, _), v in self.units.items() if p == "South Jeolla")
        self.assertEqual(by["Korean-Chinese"], expected)

    def test_the_province_is_the_sum_of_its_units(self):
        gyeonggi = next(r for r in self.records if r["name"] == "Gyeonggi")
        koreans = next(s["count"] for s in gyeonggi["ethnicity"] if s["group"] == "Korean")
        self.assertEqual(koreans, self.register[("Gyeonggi", "")])
        self.assertEqual(gyeonggi["population"]["value"],
                         koreans + sum(v["__total__"] for (p, _), v in self.units.items()
                                       if p == "Gyeonggi"))

    def test_a_missing_shape_row_is_refused(self):
        units = dict(self.units)
        del units[("Jeju", "서귀포시")]
        with self.assertRaises(SystemExit):
            m.build(units, self.register)

    def test_a_district_the_register_lacks_is_refused(self):
        register = dict(self.register)
        del register[("Jeju", "서귀포시")]
        with self.assertRaises(SystemExit):
            m.build(self.units, register)

    def test_the_published_total_is_enforced(self):
        saved = dict(m.PUBLISHED)
        m.PUBLISHED.clear()
        m.PUBLISHED.update({"foreign": 1, "koreans": 1})
        try:
            with self.assertRaises(SystemExit):
                m.build(self.units, self.register)
        finally:
            m.PUBLISHED.clear()
            m.PUBLISHED.update(saved)


class Integration(unittest.TestCase):
    def test_registered_right_after_the_korea_survey(self):
        files = be.ADAPTER_FILES
        self.assertEqual(files[files.index("korea_survey_province.json") + 1],
                         "korea_nationality.json")

    def test_korea_no_longer_declares_ethnicity_uncollected(self):
        # The owner's decision of 19 September 2026: the declaration's
        # substance is in every row's note, and an entry here would make the
        # build refuse the file.
        self.assertNotIn("KOR", common.NOT_COLLECTED_POLICY)
        self.assertIsNone(common.collection_gap("KOR", "ethnicity"))

    def test_the_build_script_and_the_hint_name_it(self):
        text = (ROOT / "scripts" / "build_all.sh").read_text()
        self.assertIn("scripts.fetch_census.korea_nationality", text)
        self.assertIn("korea_nationality", be.adapter_hint("KOR"))


if __name__ == "__main__":
    unittest.main()
