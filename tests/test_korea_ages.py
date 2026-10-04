"""Korea's register ages: reading, the sums, binding by shape id, offline.

The table is synthetic but laid out as jumin.mois.go.kr's downloadCsvAge.do
answers: 행정구역 (code), then 계/남/여 x 총인구수, 연령구간인구수, 0세..100세
이상. Every district the crosswalk knows gets a row, with Yeonggwang (no
polygon) and one city's own district beside them.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import korea_ages as ka  # noqa: E402
from scripts.fetch_census.korea_nationality import (  # noqa: E402
    DISTRICTS, DRAWN_ELSEWHERE, UNDRAWN,
)

PROVINCE_KO = {
    "Seoul": "서울특별시", "Busan": "부산광역시", "Daegu": "대구광역시", "Incheon": "인천광역시",
    "Gwangju": "광주광역시", "Daejeon": "대전광역시", "Ulsan": "울산광역시",
    "Sejong": "세종특별자치시", "Gyeonggi": "경기도", "Gangwon": "강원특별자치도",
    "North Chungcheong": "충청북도", "South Chungcheong": "충청남도",
    "North Jeolla": "전북특별자치도", "South Jeolla": "전라남도",
    "North Gyeongsang": "경상북도", "South Gyeongsang": "경상남도", "Jeju": "제주특별자치도",
}


def header():
    cols = ["행정구역"]
    for sex in ("계", "남", "여"):
        cols += [f"2025년12월_{sex}_총인구수", f"2025년12월_{sex}_연령구간인구수"]
        cols += [f"2025년12월_{sex}_{a}세" for a in range(100)] + [f"2025년12월_{sex}_100세 이상"]
    return cols


def pyramid(scale):
    """Men and women by single year: flat to 60, thinning after."""
    men = [scale * (10 if a < 60 else max(1, 10 - (a - 60) // 4)) for a in range(101)]
    women = [m + (scale if a > 50 else 0) for a, m in enumerate(men)]
    return men, women


def row(area, code, men, women):
    out = [f"{area} ({code})"]
    for ages in ([m + w for m, w in zip(men, women)], men, women):
        total = sum(ages)
        out += [f"{total:,}", f"{total:,}"] + [f"{n:,}" for n in ages]
    return out


def fixture():
    table = [header()]
    admin1 = [{"id": f"P-{p}", "name": p} for p in PROVINCE_KO]
    admin2 = []
    pcode = 10
    for province, ko in PROVINCE_KO.items():
        pcode += 1
        words = [w for w in DISTRICTS[province] if not (province == "North Gyeongsang"
                                                        and w == "군위군")]
        if province == "South Jeolla":
            words.append("영광군")
        rows, men_sum, women_sum = [], [0] * 101, [0] * 101
        for i, word in enumerate(words):
            men, women = pyramid(i % 5 + 1)
            men_sum = [a + b for a, b in zip(men_sum, men)]
            women_sum = [a + b for a, b in zip(women_sum, women)]
            area = ko if province == "Sejong" else f"{ko} {word}"
            code = f"{pcode}{i + 1:03d}00000"
            rows.append(row(area, code, men, women))
            if province == "Gyeonggi" and word == "수원시":
                # A city's own district, listed beside the city.
                rows.append(row(f"{ko} 수원시 장안구", f"{pcode}9{i:02d}00000", men, women))
        table.append(row(ko, f"{pcode}00000000", men_sum, women_sum))
        table += rows
        for word, name in DISTRICTS[province].items():
            if province == "North Gyeongsang" and word == "군위군":
                continue
            under = DRAWN_ELSEWHERE.get((province, name), province)
            parent = f"P-{under}" if under else "KOR"
            admin2.append({"id": f"S-{province}-{name}", "name": name, "parent": parent})
    return table, admin1, admin2


class Build(unittest.TestCase):
    def setUp(self):
        self.table, self.admin1, self.admin2 = fixture()
        self.records = ka.build(self.table, self.admin1, self.admin2)
        self.by_shape = {r["shape_id"]: r for r in self.records}

    def test_every_unit_once(self):
        levels = [r["level"] for r in self.records]
        self.assertEqual(levels.count("admin1"), 17)
        self.assertEqual(levels.count("admin2"), 228)
        self.assertEqual(len(self.by_shape), 245)

    def test_median_and_sex_ratio(self):
        r = self.by_shape["S-Seoul-Jongno-gu"]
        men, women = pyramid(1)
        self.assertEqual(r["sex_ratio"]["value"], round(100 * sum(men) / sum(women), 1))
        self.assertEqual(r["sex_ratio"]["unit"], "males_per_100_females")
        self.assertEqual(r["median_age"]["unit"], "years")
        self.assertTrue(30 < r["median_age"]["value"] < 60)
        self.assertEqual(r["match_by"], "shape_id")
        self.assertEqual(r["language"]["status"], "not_collected")
        self.assertEqual(r["population"]["status"], "not_available")

    def test_drawn_elsewhere_is_said(self):
        r = self.by_shape["S-Daegu-Gunwi-gun"]
        self.assertIn("North Gyeongsang", r["median_age_note"])
        r = self.by_shape["S-Incheon-Ongjin-gun"]
        self.assertIn("the country itself", r["sex_ratio_note"])

    def test_province(self):
        r = self.by_shape["P-Jeju"]
        self.assertEqual(r["level"], "admin1")
        self.assertIn("this province", r["median_age_note"])


class Refusals(unittest.TestCase):
    def test_ages_must_add_up(self):
        table, a1, a2 = fixture()
        table[3][5] = "999,999"
        with self.assertRaises(SystemExit):
            ka.build(table, a1, a2)

    def test_districts_must_add_to_province(self):
        table, a1, a2 = fixture()
        del table[2]                      # a Seoul district gone
        with self.assertRaises(SystemExit):
            ka.build(table, a1, a2)

    def test_unknown_district(self):
        table, a1, a2 = fixture()
        table[2][0] = table[2][0].replace("종로구", "새로구")
        with self.assertRaises(SystemExit):
            ka.build(table, a1, a2)

    def test_drawn_unit_without_a_row(self):
        table, a1, a2 = fixture()
        a2.append({"id": "S-extra", "name": "Nowhere-gun", "parent": "P-Seoul"})
        with self.assertRaises(SystemExit):
            ka.build(table, a1, a2)

    def test_wrong_month(self):
        table, a1, a2 = fixture()
        table[0] = [h.replace("2025년12월", "2025년11월") for h in table[0]]
        with self.assertRaises(SystemExit):
            ka.build(table, a1, a2)

    def test_undrawn_county_counts_only_in_its_province(self):
        table, a1, a2 = fixture()
        self.assertIn(("South Jeolla", "영광군"), UNDRAWN)
        records = ka.build(table, a1, a2)
        self.assertFalse(any("Yeonggwang" in r["name"] for r in records))


if __name__ == "__main__":
    unittest.main()
