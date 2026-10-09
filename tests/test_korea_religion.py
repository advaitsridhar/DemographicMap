"""Korea's 2015 census religion by province and district, offline.

The table is synthetic but laid out as KOSIS's bulk file for DT_1PM1502 is:
a title, a blank line, the header, then one row per area, sex and age, the
codes written with a leading apostrophe. Every district the crosswalk knows
gets a row, with Yeonggwang (no polygon), Incheon's Nam-gu under its 2015
name, Sejong as 세종시 and one city's own districts beside the city.
"""

import csv
import io
import sys
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_census import korea_religion as kr  # noqa: E402
from scripts.fetch_census.korea_nationality import (  # noqa: E402
    DISTRICTS, DRAWN_ELSEWHERE, UNDRAWN,
)

# 2015's spellings of the provinces, as the table writes them.
PROVINCE_KO = {
    "Seoul": ("11", "서울특별시"), "Busan": ("21", "부산광역시"), "Daegu": ("22", "대구광역시"),
    "Incheon": ("23", "인천광역시"), "Gwangju": ("24", "광주광역시"),
    "Daejeon": ("25", "대전광역시"), "Ulsan": ("26", "울산광역시"),
    "Sejong": ("29", "세종특별자치시"), "Gyeonggi": ("31", "경기도"), "Gangwon": ("32", "강원도"),
    "North Chungcheong": ("33", "충청북도"), "South Chungcheong": ("34", "충청남도"),
    "North Jeolla": ("35", "전라북도"), "South Jeolla": ("36", "전라남도"),
    "North Gyeongsang": ("37", "경상북도"), "South Gyeongsang": ("38", "경상남도"),
    "Jeju": ("39", "제주특별자치도"),
}
HEADER = ["C행정구역별(시군구)", "행정구역별(시군구)", "C성별", "성별", "C연령별", "연령별",
          "시점", "계", "종교있음-계", "불교", "기독교(개신교)", "기독교(천주교)", "원불교", "유교",
          "천도교", "대순진리회", "대종교", "기타", "종교없음-계"]


def counts(scale):
    """[계, 종교있음, nine religions..., 종교없음] for one area."""
    religions = [30 * scale, 40 * scale, 15 * scale, 2 * scale, 1 * scale, 1 * scale,
                 scale, 0, 2 * scale]
    with_one = sum(religions)
    none = 120 * scale
    return [with_one + none, with_one, *religions, none]


def line(code, name, values, sex="0", age="000"):
    return [f"'{code}", name, f"'{sex}", "계", f"'{age}", "합계", "2015",
            *[f"{v}.0000" for v in values]]


def add(*rows):
    return [sum(col) for col in zip(*rows)]


def fixture():
    """The kept rows (header and both-sexes, all-ages rows), the drawn units,
    and the national counts the table adds up to."""
    rows = [HEADER]
    admin1 = [{"id": f"P-{p}", "name": p} for p in PROVINCE_KO]
    admin2 = []
    body = []
    provinces = []
    for province, (pcode, ko) in PROVINCE_KO.items():
        districts = []
        words = dict(DISTRICTS[province])
        if province == "Daegu":
            words.pop("군위군")                     # Gyeongbuk's in 2015
        for i, (word, drawn_name) in enumerate(sorted(words.items())):
            under = DRAWN_ELSEWHERE.get((province, drawn_name), province)
            if province == "North Gyeongsang" and drawn_name == "Gunwi-gun":
                under = "North Gyeongsang"
            if not (province == "North Gyeongsang" and drawn_name == "Gunwi-gun"):
                admin2.append({"id": f"S-{province}-{drawn_name}", "name": drawn_name,
                               "parent": f"P-{under}" if under else None})
            if (province, word) == ("Incheon", "미추홀구"):
                word = "남구"
            if (province, word) == ("Sejong", "세종특별자치시"):
                word = "세종시"
            code = f"{pcode}{(i + 1) * 10:03d}"
            values = counts(i + 1)
            if word == "수원시":
                parts = [counts(1), counts(i)]
                values = add(*parts)
                body.append(line(code, f" {word}", values))
                body += [line(f"{pcode}{(i + 1) * 10 + 1 + k:03d}", f" 구{k}", part)
                         for k, part in enumerate(parts)]
            else:
                body.append(line(code, f" {word}", values))
            districts.append(values)
        if province == "North Gyeongsang":
            # Gunwi, drawn under North Gyeongsang (the shape the crosswalk
            # keeps for Daegu's 2025 Gunwi).
            admin2.append({"id": "S-Daegu-Gunwi-gun", "name": "Gunwi-gun",
                           "parent": "P-North Gyeongsang"})
        for (p, word), _ in UNDRAWN.items():
            if p == province:
                values = counts(7)
                body.append(line(f"{pcode}990", f" {word}", values))
                districts.append(values)
        whole = add(*districts)
        provinces.append(whole)
        rows.append(line(pcode, ko, whole))
        rows += [line(f"{pcode}{k:03d}", f" {n}", v) for k, n, v in
                 ((3, "동부", whole), (4, "읍부", [0] * len(whole)), (5, "면부", [0] * len(whole)))]
        rows += body
        body = []
    nation = add(*provinces)
    rows.insert(1, line("00", "전국", nation))
    rows.insert(2, line("03", "동부", nation))
    rows.insert(3, line("04", "읍부", [0] * len(nation)))
    rows.insert(4, line("05", "면부", [0] * len(nation)))
    national = {kr.TOTAL: nation[0], kr.RELIGIOUS: nation[1], kr.NONE: nation[-1]}
    # A province's 동부 is the whole province here; the reader must not count
    # it as a district.
    return rows, admin1, admin2, national


def build(rows=None):
    table, a1, a2, national = fixture()
    with mock.patch.object(kr, "NATIONAL", national):
        return kr.build(rows or table, a1, a2)


class Reads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = build()
        cls.by_shape = {r["shape_id"]: r for r in cls.records}

    def test_every_drawn_unit_once(self):
        _, a1, a2, _ = fixture()
        self.assertEqual(len(self.records), len(a1) + len(a2))
        self.assertEqual(set(self.by_shape), {u["id"] for u in a1} | {u["id"] for u in a2})

    def test_shares_and_labels(self):
        r = self.by_shape["S-Seoul-Jongno-gu"]
        shares = {g["group"]: g["pct"] for g in r["religion"]}
        self.assertAlmostEqual(sum(shares.values()), 100.0, places=6)
        self.assertEqual(set(shares), {"No religion", "Protestant", "Buddhism", "Roman Catholic",
                                       "Won Buddhism", "Confucianism", "Cheondoism",
                                       "Other religions"})
        self.assertEqual(r["religion_year"], 2015)
        self.assertEqual(r["religion_basis"], "self-identification")
        self.assertEqual(r["match_by"], "shape_id")

    def test_the_two_unplaced_religions_join_other(self):
        r = self.by_shape["S-Sejong-Sejong-si"]          # the fixture's scale 1
        other = next(g for g in r["religion"] if g["group"] == "Other religions")
        self.assertEqual(other["count"], counts(1)[-2] + counts(1)[-4])
        self.assertIn("Daesun Jinrihoe", r["religion_note"])
        self.assertNotIn("Daejongism", r["religion_note"])     # none counted here

    def test_counts_add_up_to_the_table(self):
        r = self.by_shape["S-Sejong-Sejong-si"]
        self.assertEqual(sum(g["count"] for g in r["religion"]), counts(1)[0])

    def test_2015_names(self):
        self.assertIn("S-Incheon-Michuhol-gu [Nam-gu]", self.by_shape)
        self.assertIn("S-Sejong-Sejong-si", self.by_shape)

    def test_gunwi_is_north_gyeongsangs_in_2015(self):
        r = self.by_shape["S-Daegu-Gunwi-gun"]
        self.assertEqual(r["parent"], "KOR-North Gyeongsang")

    def test_drawn_elsewhere_is_said(self):
        r = self.by_shape["S-Incheon-Ongjin-gun"]
        self.assertIn("the country itself", r["religion_note"])

    def test_province(self):
        r = self.by_shape["P-Jeju"]
        self.assertEqual(r["level"], "admin1")
        self.assertEqual(sum(g["count"] for g in r["religion"]),
                         counts(1)[0] + counts(2)[0])


class Refusals(unittest.TestCase):
    def test_religions_must_add_to_the_religious(self):
        table, *_ = fixture()
        table[1][9] = "1.0000"
        with self.assertRaises(SystemExit):
            build(table)

    def test_a_province_must_be_its_districts(self):
        table, *_ = fixture()
        i = next(i for i, r in enumerate(table) if r[0] == "'11010")
        # One more person with a religion, a Buddhist: the row still adds up.
        table[i][7:] = [f"{int(float(v)) + 1}.0000" if k in (0, 1, 2) else v
                        for k, v in enumerate(table[i][7:])]
        with self.assertRaises(SystemExit):
            build(table)

    def test_the_nation_must_be_the_published_one(self):
        table, a1, a2, national = fixture()
        with mock.patch.object(kr, "NATIONAL", {**national, kr.TOTAL: 1}):
            with self.assertRaises(SystemExit):
                kr.build(table, a1, a2)

    def test_a_drawn_district_without_a_row_is_refused(self):
        table, a1, a2, national = fixture()
        a2 = a2 + [{"id": "S-extra", "name": "Nowhere-gun", "parent": "P-Jeju"}]
        with mock.patch.object(kr, "NATIONAL", national):
            with self.assertRaises(SystemExit):
                kr.build(table, a1, a2)


class Download(unittest.TestCase):
    def test_keeps_the_both_sexes_all_ages_rows(self):
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["성, 연령 및 종교별 인구-시군구"])
        w.writerow([])
        w.writerow(HEADER)
        w.writerow(line("00", "전국", counts(1)))
        w.writerow(line("00", "전국", counts(1), sex="1"))
        w.writerow(line("00", "전국", counts(1), age="005"))
        blob = io.BytesIO()
        with zipfile.ZipFile(blob, "w") as zf:
            zf.writestr("101_DT_1PM1502_F_2015.csv", out.getvalue().encode("cp949"))
        rows = kr.totals_rows(blob.getvalue())
        self.assertEqual(rows[0], HEADER)
        self.assertEqual(len(rows), 2)

    def test_not_a_zip(self):
        with self.assertRaises(SystemExit):
            kr.totals_rows(b"<html>")


if __name__ == "__main__":
    unittest.main()
