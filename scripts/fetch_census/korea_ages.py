#!/usr/bin/env python3
"""South Korea: median age and sex ratio for every district and province, from the register.

The Ministry of the Interior and Safety publishes the resident register's
population by single year of age and sex every month, for every province,
city, county and district (주민등록 인구통계, 연령별 인구현황). One form posted
to ``downloadCsvAge.do`` with ``state=2`` (전체시군구현황) answers a cp949 CSV
of every 시도 and 시군구 at once: ``행정구역 (ten-digit code)``, then for each of
계 (both sexes), 남 (men) and 여 (women) the 총인구수, the 연령구간인구수 and
one column per year of age from 0세 to 100세 이상. That is what this reads,
for the register at the end of December 2025 -- the register's year-end
figure.

**What it counts.** Everyone on the resident register: Korean nationals,
including those whose whereabouts are unknown (거주불명자) and nationals
living abroad who keep a registration (재외국민), the register's own
headline total. Foreigners are not on it -- they register with the
immigration office -- so the median and the sex ratio are those of the
registered Korean population; registered foreigners are about 5 per cent
of the people in the country and younger, so an all-residents median would
run a little lower. Every note says so. The population the map shows for
these units is ``korea_nationality``'s (Koreans plus registered foreigners)
and this file does not write one.

**The median** is interpolated within the single year of age that holds the
middle person (``east_asia_common.single_year_median``); the open class of
100 and over never holds it. **The sex ratio** is men per hundred women.

**Binding.** Every district is bound to its polygon by shape id, through the
crosswalk ``korea_nationality`` already keeps -- the register's Korean name
under its province to the boundary file's romanised name, and the province
the boundary file draws it under where that is not its own (twenty of the
228 are drawn under a neighbour, three under the country). A city's own
districts (수원시 장안구) are listed beside the city and are skipped: the city
is what the boundary file draws. Jeonnam's Yeonggwang-gun has no polygon
and counts only towards its province.

**Checks**, each a refusal: in every row the years of age add up to the
연령구간인구수 and that to the 총인구수, for both sexes and each sex; men and
women add up to both sexes; every province's districts add up to the
province, and the provinces to the national row; every one of the 228 drawn
polygons and 17 provinces gets a row, and no polygon gets two.

**Language** is not asked by Korea's census -- its questionnaires ask
nationality and, in years ending in 5, religion, and nothing about the
language a person speaks -- and no survey measures it by district; every
record says so.

Usage:
    python -m scripts.fetch_census.korea_ages            # reads the kept CSV, or asks for it
    python -m scripts.fetch_census.korea_ages --fetch-only
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ._shared import NOT_COLLECTED, PROCESSED, gap, log, measure, record, write_json
from .east_asia_common import drawn, sex_ratio, single_year_median
from .korea_nationality import (
    AREA, DISTRICTS, DRAWN_ELSEWHERE, KEEP, MOJ_LICENCE, SIDO, UNDRAWN, number, post_csv,
)

OUT = "korea_ages.json"
YEAR, MONTH = 2025, 12
AS_OF = "31 December 2025"
URL = "https://jumin.mois.go.kr/downloadCsvAge.do?searchYearMonth=month&xlsStats=2"
PAGE = "https://jumin.mois.go.kr/ageStatMonth.do"
SOURCE = ("Ministry of the Interior and Safety, resident registration population by single "
          "year of age and sex, every city, county and district, December 2025 "
          "(주민등록 인구통계, 연령별 인구현황, jumin.mois.go.kr)")
LICENCE = MOJ_LICENCE
KEPT = KEEP / f"jumin_age_{YEAR}{MONTH:02d}_sigungu.json"   # the parsed CSV
TOP = 100                       # the open class, 100세 이상

# The form's fields, as ageStatMonth.do's own download form posts them (the
# runner's probe printed its inputs): every province and district at once
# (state 2, 전체시군구현황), by sex, single years from 0 to 100 and over, the
# register's default of every registered person (sltUndefType blank).
FIELDS: list[tuple[str, str]] = [
    ("sltOrgType", "1"), ("sltOrgLvl1", "A"), ("sltOrgLvl2", ""),
    ("gender", "gender"), ("sum", "sum"), ("sltUndefType", ""),
    ("searchYearStart", str(YEAR)), ("searchMonthStart", f"{MONTH:02d}"),
    ("searchYearEnd", str(YEAR)), ("searchMonthEnd", f"{MONTH:02d}"),
    ("sltOrderType", "1"), ("sltOrderValue", "ASC"), ("sltArgTypes", "1"),
    ("sltArgTypeA", "0"), ("sltArgTypeB", str(TOP)), ("category", "month"), ("state", "2"),
]

SEXES = {"계": "all", "남": "men", "여": "women"}
OFFICE = "출장소"
COLUMN = re.compile(r"^\s*(\d{4})년\s*(\d{1,2})월_(계|남|여)_(.+?)\s*$")
AGE = re.compile(r"^(\d+)세(\s*이상)?$")

LANGUAGE_NOTE = (
    "Korea's census does not ask language: its questionnaires ask nationality and, in the "
    "years ending in 5, religion, and no question about the language a person speaks; no "
    "register or survey measures it by province or district.")


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def layout(header: list[str]) -> dict[int, tuple[str, str | int]]:
    """{column: (sex, what)} where what is "total", "ranged" or an age; the
    year and month in every header must be the ones asked for."""
    out: dict[int, tuple[str, str | int]] = {}
    for i, head in enumerate(header):
        found = COLUMN.match(head)
        if not found:
            continue
        year, month, sex, what = found.groups()
        if (int(year), int(month)) != (YEAR, MONTH):
            raise SystemExit(f"korea_ages: column {head!r} is not {YEAR}-{MONTH:02d}")
        if what == "총인구수":
            out[i] = (SEXES[sex], "total")
        elif what == "연령구간인구수":
            out[i] = (SEXES[sex], "ranged")
        else:
            age = AGE.match(what)
            if not age:
                raise SystemExit(f"korea_ages: a column the reader does not know: {head!r}")
            if age.group(2) and int(age.group(1)) != TOP:
                raise SystemExit(f"korea_ages: the open class is {head!r}, not {TOP}")
            out[i] = (SEXES[sex], int(age.group(1)))
    for sex in SEXES.values():
        ages = sorted(w for s, w in out.values() if s == sex and isinstance(w, int))
        if ages != list(range(TOP + 1)):
            raise SystemExit(f"korea_ages: {sex} has ages {ages[:3]}..{ages[-3:]}, "
                             f"not 0 to {TOP}")
    return out


def read(table: list[list[str]]) -> dict[str, tuple[str, dict[str, Any]]]:
    """{ten-digit code: (area as the register writes it, {sex: {"total",
    "ranged", age: people}})} for every row, after checking that each row adds
    up."""
    cols = layout(table[0])
    out: dict[str, tuple[str, dict[str, Any]]] = {}
    for row in table[1:]:
        if not row or not row[0].strip():
            continue
        found = AREA.match(row[0].strip())
        if not found:
            continue
        area, code = " ".join(found.group(1).split()), found.group(2)
        by_sex: dict[str, Any] = {s: {"ages": Counter()} for s in SEXES.values()}
        for i, (sex, what) in cols.items():
            n = number(row[i]) if i < len(row) else 0
            if isinstance(what, int):
                by_sex[sex]["ages"][what] += n
            else:
                by_sex[sex][what] = n
        for sex, cell in by_sex.items():
            summed = sum(cell["ages"].values())
            if not (summed == cell["ranged"] == cell["total"]):
                raise SystemExit(f"korea_ages: {area} ({sex}): the years of age add to "
                                 f"{summed:,}, the ranged count is {cell['ranged']:,}, the "
                                 f"total {cell['total']:,}")
        if by_sex["men"]["total"] + by_sex["women"]["total"] != by_sex["all"]["total"]:
            raise SystemExit(f"korea_ages: {area}: men and women do not make the total")
        if any(by_sex["men"]["ages"][a] + by_sex["women"]["ages"][a] != by_sex["all"]["ages"][a]
               for a in range(TOP + 1)):
            raise SystemExit(f"korea_ages: {area}: men and women do not make an age's total")
        if code in out:
            raise SystemExit(f"korea_ages: {code} appears twice")
        out[code] = (area, by_sex)
    return out


def classify(rows: dict[str, tuple[str, dict[str, Any]]]
             ) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]],
                        dict[tuple[str, str], dict[str, Any]], int]:
    """(the national row or None, {province: row}, {(province, district word):
    row}, city districts skipped). The rules are korea_nationality's
    read_register: a city's own districts name three levels and are skipped;
    Sejong, a province that is one city, repeats its own name a level down."""
    national = None
    provinces: dict[str, dict[str, Any]] = {}
    districts: dict[tuple[str, str], dict[str, Any]] = {}
    skipped = 0
    offices = 0
    for code, (area, by_sex) in rows.items():
        words = area.split()
        if words[0] == "전국":
            national = by_sex
            continue
        # A branch office (출장소: 인천광역시 중구영종출장소, 북부출장소) is listed
        # with nobody registered to it -- its residents are its district's.
        # One with people in it would be counted twice, and is a refusal.
        if area.endswith(OFFICE):
            if by_sex["all"]["total"]:
                raise SystemExit(f"korea_ages: the branch office {area} lists "
                                 f"{by_sex['all']['total']:,} people")
            offices += 1
            continue
        if words[0] not in SIDO:
            raise SystemExit(f"korea_ages: {area!r} names no province")
        province = SIDO[words[0]]
        if code[2:] == "00000000":
            if province in provinces:
                raise SystemExit(f"korea_ages: two rows for {province}")
            provinces[province] = by_sex
            continue
        if code[5:] != "00000":
            raise SystemExit(f"korea_ages: {area} ({code}) is below a district")
        if len(words) > 2:
            skipped += 1
            continue
        if len(words) < 2 and province != "Sejong":
            raise SystemExit(f"korea_ages: {area!r} names no district")
        key = (province, words[1] if len(words) > 1 else words[0])
        if key in districts:
            raise SystemExit(f"korea_ages: two rows for {key}")
        districts[key] = by_sex
    if offices:
        log(f"  {offices} branch offices (출장소) listed with nobody registered, skipped")
    return national, provinces, districts, skipped


def check_sums(national: dict[str, Any] | None, provinces: dict[str, dict[str, Any]],
               districts: dict[tuple[str, str], dict[str, Any]]) -> None:
    """Every province's districts add up to it, sex by sex and age by age, and
    the provinces to the national row where the file has one."""
    if len(provinces) != 17:
        raise SystemExit(f"korea_ages: {len(provinces)} provinces, not 17")
    for province, row in provinces.items():
        for sex in SEXES.values():
            summed: Counter = Counter()
            for (p, _), cell in districts.items():
                if p == province:
                    summed.update(cell[sex]["ages"])
            if summed != row[sex]["ages"]:
                total = sum(summed.values())
                raise SystemExit(f"korea_ages: {province}'s districts hold {total:,} "
                                 f"{sex} against its {row[sex]['total']:,}")
    if national is not None:
        for sex in SEXES.values():
            summed = sum(row[sex]["total"] for row in provinces.values())
            if summed != national[sex]["total"]:
                raise SystemExit(f"korea_ages: the provinces hold {summed:,} {sex}, the "
                                 f"national row {national[sex]['total']:,}")
    total = sum(row["all"]["total"] for row in provinces.values())
    log(f"  {len(provinces)} provinces and {len(districts)} districts add up, age by age; "
        f"{total:,} registered people"
        + ("" if national is not None else " (the file prints no national row)"))


# ---------------------------------------------------------------------------
# Binding and records
# ---------------------------------------------------------------------------

def shape_ids(admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
              ) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """({province: shape id}, {(province the boundary file draws it under, or
    "" for the country; drawn name): shape id}) from the drawn units."""
    provinces = {u["name"]: u["id"] for u in admin1}
    names = {u["id"]: u["name"] for u in admin1}
    out: dict[tuple[str, str], str] = {}
    for u in admin2:
        key = (names.get(u.get("parent"), ""), u["name"])
        if key in out:
            raise SystemExit(f"korea_ages: two drawn units are {key}")
        out[key] = u["id"]
    return provinces, out


def note_for(cell: dict[str, Any], where: str) -> tuple[str, str]:
    men, women = cell["men"]["total"], cell["women"]["total"]
    base = (f"The resident register at {AS_OF} (Ministry of the Interior and Safety): "
            f"{cell['all']['total']:,} registered people of {where}, Korean nationals including "
            "those of unknown whereabouts and nationals abroad who keep a registration; "
            "foreigners register with the immigration office and are not counted.")
    return (f"{base} Interpolated within the single year of age that holds the middle person.",
            f"{base} {men:,} men and {women:,} women.")


def unit_record(rid: str, name: str, *, level: str, parent: str, shape: str,
                cell: dict[str, Any], where: str, extra_note: str = "") -> dict[str, Any]:
    median_note, sex_note = note_for(cell, where)
    if extra_note:
        median_note, sex_note = f"{median_note} {extra_note}", f"{sex_note} {extra_note}"
    return record(
        rid, name, level=level, parent=parent, country="KOR",
        match_by="shape_id", shape_id=shape,
        median_age=measure(single_year_median(dict(cell["all"]["ages"])), unit="years",
                           year=YEAR, source=SOURCE),
        median_age_note=median_note,
        sex_ratio=sex_ratio(cell["men"]["total"], cell["women"]["total"], year=YEAR,
                            source=SOURCE),
        sex_ratio_note=sex_note,
        language=gap(NOT_COLLECTED, LANGUAGE_NOTE),
        sources=[{"field": "median_age/sex_ratio", "name": SOURCE, "url": PAGE, "year": YEAR,
                  "license": LICENCE}])


def build(table: list[list[str]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = read(table)
    national, provinces, districts, skipped = classify(rows)
    log(f"  {len(rows)} rows: {len(provinces)} provinces, {len(districts)} districts, "
        f"{skipped} districts of cities skipped (their city carries them)")
    check_sums(national, provinces, districts)
    province_shapes, district_shapes = shape_ids(admin1, admin2)
    records: list[dict[str, Any]] = []
    for province, cell in sorted(provinces.items()):
        if province not in province_shapes:
            raise SystemExit(f"korea_ages: no drawn province called {province!r}")
        records.append(unit_record(f"KOR-{province}", province, level="admin1", parent="KOR",
                                   shape=province_shapes[province], cell=cell,
                                   where="this province"))
    bound: dict[str, tuple[str, str]] = {}
    unknown: list[str] = []
    for (province, word), cell in sorted(districts.items()):
        name = DISTRICTS.get(province, {}).get(word)
        if name is None:
            if (province, word) in UNDRAWN:
                log(f"  {province} {word} ({UNDRAWN[(province, word)]}): no polygon; counted in "
                    "its province only")
                continue
            unknown.append(f"{province} {word}")
            continue
        under = DRAWN_ELSEWHERE.get((province, name), province)
        shape = district_shapes.get((under, name))
        if shape is None:
            raise SystemExit(f"korea_ages: no drawn unit {name!r} under {under or 'KOR'!r}")
        if shape in bound:
            raise SystemExit(f"korea_ages: {shape} is bound to {bound[shape]} and "
                             f"{(province, word)}")
        bound[shape] = (province, word)
        extra = ""
        if under != province:
            extra = (f"The boundary file draws {name} under {under or 'the country itself'}; "
                     f"it is a district of {province}.")
        records.append(unit_record(f"KOR-{province}-{name}", name, level="admin2",
                                   parent=f"KOR-{province}", shape=shape, cell=cell,
                                   where="this district", extra_note=extra))
    if unknown:
        raise SystemExit(f"korea_ages: districts the crosswalk does not know: {unknown}")
    missing = sorted(set(district_shapes.values()) - set(bound))
    if missing:
        raise SystemExit(f"korea_ages: drawn districts with no row: "
                         f"{[k for k, v in district_shapes.items() if v in missing]}")
    medians = [r["median_age"]["value"] for r in records if r["level"] == "admin2"]
    nation: Counter = Counter()
    for cell in provinces.values():
        nation.update(cell["all"]["ages"])
    log(f"  {len(records)} records: 17 provinces, {len(medians)} districts; district medians "
        f"{min(medians):.1f}-{max(medians):.1f}; the register's national median "
        f"{single_year_median(dict(nation)):.1f}")
    return records


def fetch() -> list[list[str]]:
    table = post_csv(URL, FIELDS, keep=None)
    if len(table) < 250:
        raise SystemExit(f"korea_ages: the register answered {len(table)} rows")
    KEPT.parent.mkdir(parents=True, exist_ok=True)
    with KEPT.open("w", encoding="utf-8", newline="") as fh:
        json.dump(table, fh, ensure_ascii=False)
    log(f"  kept {KEPT.name} ({KEPT.stat().st_size / 1e3:.0f} kB, {len(table)} rows)")
    return table


def load() -> list[list[str]]:
    if KEPT.exists() and KEPT.stat().st_size > 0:
        log(f"  reading the kept {KEPT.name}")
        return json.loads(KEPT.read_text(encoding="utf-8"))
    return fetch()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch-only", action="store_true", help="fetch the CSV and stop")
    args = ap.parse_args()
    log(f"korea_ages: {SOURCE}")
    if args.fetch_only:
        fetch()
        return 0
    records = build(load(), drawn("KOR", "admin1"), drawn("KOR", "admin2"))
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
