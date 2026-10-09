#!/usr/bin/env python3
"""Viet Nam: religion by province, from the 2009 census's Completed Results.

The 2019 census asked religion and published it for the whole country only
(``vietnam_district.RELIGION_GAP``). Its predecessor published it by province:
*Tổng điều tra dân số và nhà ở Việt Nam năm 2009: Kết quả toàn bộ* -- *The
2009 Vietnam Population and Housing Census: Completed Results* (Central
Population and Housing Census Steering Committee, June 2010), 901 pages, on
the statistics office's host:

    https://www.nso.gov.vn/wp-content/uploads/2019/03/KQ-toan-bo-1.pdf

Two of its sixteen tables are read:

* **Table 7** -- population by urban/rural residence, sex, religion,
  socio-economic region and province/city (printed pages 281-312): for the
  country, the six regions and the 63 provinces, the followers of each of the
  thirteen religions the state recognised in 2009 and those whose religion was
  not determined, each with Total, Male and Female for the whole, urban and
  rural population.
* **Table 1** -- population by urban/rural residence, sex, region and
  province (pages 3-5): each province's whole population.

**What the table counts.** Table 7 lists followers only: its rows add up to
15,651,467 people in the country, against 85,846,997 counted in all. Everyone
else answered that they follow no religion -- the census's "không tôn giáo",
the answer of 81.7% of the country, which the volume does not print as a
row. A province's "No religion" here is its Table 1 population less its Table
7 total: the same census's two counts of the same people, subtracted, not
estimated. The province code the volume prints in both tables (01 Hà Nội ...
96 Cà Mau) joins them, and the name binds the province to the map's polygon.

**Labels.** Phật giáo "Buddhism", Công giáo "Catholicism", Tin lành
"Protestantism", Hồi giáo "Islam", Cao Đài "Caodaism", Phật giáo Hòa Hảo
"Hoa Hao Buddhism", Tôn giáo Baha'i "Baha'i", Bà La Môn -- the Cham Balamon,
a Hindu tradition -- "Balamon Hinduism", Tịnh độ cư sĩ Phật hội Việt Nam (a
Pure Land lay Buddhist association) "Pure Land Buddhism (Tinh Do Cu Si)",
and Đạo Tứ Ân Hiếu Nghĩa and Bửu Sơn Kỳ Hương under their own names. Minh
Sư Đạo and Minh Lý Đạo, 709 and 366 followers in the whole country, are
counted together as "Other religions", and so is any other religion below
0.05% of a province; each record's note names what that row holds. "Không
xác định" is "Not stated".

**Checks**, each a refusal: in every row Male + Female make Total for the
whole, urban and rural, and urban + rural make the whole; every unit's
religion rows make its own total in all nine columns; the provinces make
their regions and the regions the country, religion by religion; the country
is 15,651,467 followers and 85,846,997 people; both tables name the same 63
provinces, each once; no province has more followers than people.

Usage:
    python -m scripts.fetch_census.vietnam_religion
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from typing import Any

from . import vietnam as vn
from ._shared import NOT_AVAILABLE, PROCESSED, RAW, download, gap, log, record, write_json
from .sea_common import drawn

OUT = "vietnam_religion.json"
YEAR = 2009
PDF = "https://www.nso.gov.vn/wp-content/uploads/2019/03/KQ-toan-bo-1.pdf"
PAGE = ("https://www.nso.gov.vn/en/data-and-statistics/2019/03/"
        "the-2009-vietnam-population-and-housing-census-completed-results/")
SOURCE = ("Central Population and Housing Census Steering Committee (General Statistics "
          "Office of Viet Nam), The 2009 Vietnam Population and Housing Census: Completed "
          "Results (2010), Table 7: population by urban/rural residence, sex, religion, "
          "socio-economic region and province, and Table 1: population by province")
NATIONAL_FOLLOWERS = 15_651_467
NATIONAL_POPULATION = 85_846_997
PROVINCE_COUNT = 63
REGION_COUNT = 6
MIN_SHARE = 0.05                    # below this a religion joins "Other religions"
OTHER = "Other religions"
NOT_STATED = "Not stated"
NONE = "No religion"
# The thirteen religion codes of Table 7, with a word each label must carry
# (folded), so a misread row cannot pass as another religion.
RELIGIONS: dict[str, tuple[str, str]] = {
    "01": ("Buddhism", "phatgiao"),
    "02": ("Catholicism", "conggiao"),
    "03": ("Hoa Hao Buddhism", "hoahao"),
    "04": ("Islam", "hoigiao"),
    "05": ("Caodaism", "caodai"),
    "06": (OTHER, "minhsudao"),
    "07": (OTHER, "minhlydao"),
    "08": ("Protestantism", "tinlanh"),
    "09": ("Pure Land Buddhism (Tinh Do Cu Si)", "tinhdocusi"),
    "10": ("Tu An Hieu Nghia", "tuanhieunghia"),
    "11": ("Buu Son Ky Huong", "buusonkyhuong"),
    "12": ("Baha'i", "baha"),
    "13": ("Balamon Hinduism", "balamon"),
}
NUMBER = r"(?:\d{1,3}(?:\.\d{3})*|-)"
TAIL = rf"(?P<tail>(?:{NUMBER}\s+){{8}}{NUMBER})"
PROVINCE_ROW = re.compile(rf"^\s*(?P<code>\d{{1,2}})\.?\s+(?P<name>[^\d]+?)\s+{TAIL}\s*$")
RELIGION_ROW = re.compile(rf"^\s*(?P<code>\d{{2}})\s+(?P<label>[^\d]+?)\s+{TAIL}\s*$")
TOTAL_ROW = re.compile(rf"^\s*Tổng số\s*-\s*Total\s+{TAIL}\s*$")
NOT_STATED_ROW = re.compile(rf"^\s*Không xác định tôn giáo\s*-\s*Not stated\s+{TAIL}\s*$")
COUNTRY_ROW = re.compile(rf"^\s*TOÀN QUỐC\s*-\s*ENTIRE COUNTRY(?:\s+{TAIL})?\s*$")
REGION_HEAD = re.compile(r"^\s*V(?P<code>[1-6])\.?\s+\S")


def numbers(tail: str, where: str) -> list[int]:
    """Nine figures, '.' the thousands separator and '-' a zero, their sums checked."""
    n = [0 if t == "-" else int(t.replace(".", "")) for t in tail.split()]
    if len(n) != 9 or not (n[0] == n[1] + n[2] and n[3] == n[4] + n[5] and n[6] == n[7] + n[8]
                           and n[0] == n[3] + n[6]):
        raise SystemExit(f"vietnam_religion: {where}: {tail!r} is not Total = Male + Female "
                         f"and whole = urban + rural")
    return n


def table_pages(pages: list[str], number: int) -> list[tuple[int, str]]:
    mark = re.compile(rf"Biểu\s*-\s*Table\s*{number}(?!\d)")
    return [(i, p) for i, p in enumerate(pages, 1) if mark.search(p)]


def read_populations(pages: list[str]) -> tuple[int, dict[str, dict[str, Any]]]:
    """Table 1: the country's population and each province's, keyed by its code."""
    country = None
    provinces: dict[str, dict[str, Any]] = {}
    for number, page in table_pages(pages, 1):
        for line in page.splitlines():
            if m := COUNTRY_ROW.match(line):
                if m.group("tail"):
                    country = numbers(m.group("tail"), "Table 1 country")[0]
                continue
            m = PROVINCE_ROW.match(line)
            if not m:
                continue                 # regions ("V1 ...") and headings
            kind, name = vn.classify(m.group("name"))
            if kind != "province":
                continue
            code = m.group("code").zfill(2)
            if code in provinces:
                raise SystemExit(f"vietnam_religion: Table 1 prints province code {code} twice")
            provinces[code] = {"name": name, "label": m.group("name").strip(),
                               "population": numbers(m.group("tail"), f"Table 1 {name}")[0]}
    if country != NATIONAL_POPULATION:
        raise SystemExit(f"vietnam_religion: Table 1's country is {country}, not "
                         f"{NATIONAL_POPULATION:,}")
    if len(provinces) != PROVINCE_COUNT or sum(p["population"] for p in provinces.values()) \
            != NATIONAL_POPULATION:
        raise SystemExit(f"vietnam_religion: Table 1 reads {len(provinces)} provinces making "
                         f"{sum(p['population'] for p in provinces.values()):,}")
    log(f"  Table 1: {len(provinces)} provinces making the country's {country:,}")
    return country, provinces


def read_religions(pages: list[str]) -> list[dict[str, Any]]:
    """Table 7's units in order: kind, code, name, total row, and {code: row}."""
    units: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    unread = []
    for number, page in table_pages(pages, 7):
        for line in page.splitlines():
            if m := COUNTRY_ROW.match(line):
                current = {"kind": "country", "code": "", "name": "the country", "total": None,
                           "rows": {}}
                units.append(current)
                if m.group("tail"):
                    current["total"] = numbers(m.group("tail"), "Table 7 country")
                continue
            if m := REGION_HEAD.match(line):
                current = {"kind": "region", "code": "V" + m.group("code"),
                           "name": line.strip(), "total": None, "rows": {}}
                units.append(current)
                continue
            if m := TOTAL_ROW.match(line):
                if current is None or current["total"] is not None:
                    raise SystemExit(f"vietnam_religion: page {number}: a total row outside a "
                                     f"unit's head")
                current["total"] = numbers(m.group("tail"), f"Table 7 {current['name']}")
                continue
            if m := NOT_STATED_ROW.match(line):
                if current is None:
                    raise SystemExit(f"vietnam_religion: page {number}: 'Not stated' before "
                                     f"any unit")
                current["rows"]["--"] = numbers(m.group("tail"), f"{current['name']} not stated")
                continue
            if (m := PROVINCE_ROW.match(line)) and re.match(r"^\s*\d{1,2}\.\s", line):
                kind, name = vn.classify(m.group("name"))
                if kind != "province":
                    unread.append(line.strip()[:60])
                    continue
                current = {"kind": "province", "code": m.group("code").zfill(2), "name": name,
                           "label": m.group("name").strip(),
                           "total": numbers(m.group("tail"), f"Table 7 {name}"), "rows": {}}
                units.append(current)
                continue
            if m := RELIGION_ROW.match(line):
                code = m.group("code")
                if code not in RELIGIONS:
                    raise SystemExit(f"vietnam_religion: page {number}: religion code {code}")
                if RELIGIONS[code][1] not in vn.fold(m.group("label")):
                    raise SystemExit(f"vietnam_religion: page {number}: code {code} reads "
                                     f"{m.group('label')!r}")
                if current is None or code in current["rows"]:
                    raise SystemExit(f"vietnam_religion: page {number}: religion {code} outside "
                                     f"a unit, or twice in {current and current['name']}")
                current["rows"][code] = numbers(m.group("tail"), f"{current['name']} {code}")
    if unread:
        raise SystemExit(f"vietnam_religion: Table 7 rows of no known province: {unread}")
    return units


def check(units: list[dict[str, Any]], populations: dict[str, dict[str, Any]]) -> None:
    for u in units:
        if u["total"] is None or not u["rows"]:
            raise SystemExit(f"vietnam_religion: {u['name']} has no total or no rows")
        made = [sum(r[i] for r in u["rows"].values()) for i in range(9)]
        if made != u["total"]:
            raise SystemExit(f"vietnam_religion: {u['name']}'s religions make {made[0]:,}, "
                             f"against its total {u['total'][0]:,}")
    country = [u for u in units if u["kind"] == "country"]
    regions = [u for u in units if u["kind"] == "region"]
    provinces = [u for u in units if u["kind"] == "province"]
    if len(country) != 1 or country[0]["total"][0] != NATIONAL_FOLLOWERS:
        raise SystemExit(f"vietnam_religion: the country's followers are not "
                         f"{NATIONAL_FOLLOWERS:,}")
    if len(regions) != REGION_COUNT or len(provinces) != PROVINCE_COUNT:
        raise SystemExit(f"vietnam_religion: {len(regions)} regions and {len(provinces)} "
                         f"provinces read")
    codes = Counter(p["code"] for p in provinces)
    if set(codes) != set(populations) or max(codes.values()) != 1:
        raise SystemExit(f"vietnam_religion: Tables 1 and 7 name different provinces: "
                         f"{sorted(set(codes) ^ set(populations))}")
    for p in provinces:
        if p["name"] != populations[p["code"]]["name"]:
            raise SystemExit(f"vietnam_religion: code {p['code']} is {p['name']} in Table 7 "
                             f"and {populations[p['code']]['name']} in Table 1")
        if p["total"][0] > populations[p["code"]]["population"]:
            raise SystemExit(f"vietnam_religion: {p['name']} has more followers than people")

    def by_religion(parts: list[dict[str, Any]]) -> Counter:
        c: Counter = Counter()
        for part in parts:
            for code, row in part["rows"].items():
                c[code] += row[0]
        return c
    # Regions are printed before their provinces, in the volume's order of
    # V1-V6; a province belongs to the region its code's place says, so the
    # provinces are summed whole and compared with the regions' sum, and the
    # regions with the country.
    if by_religion(provinces) != by_religion(regions) or \
            by_religion(regions) != by_religion(country):
        raise SystemExit("vietnam_religion: provinces, regions and the country do not make "
                         "one another religion by religion")
    log(f"  Table 7: {len(provinces)} provinces and {len(regions)} regions making the country's "
        f"{NATIONAL_FOLLOWERS:,} followers, religion by religion and in all nine columns")


def composition(unit: dict[str, Any], population: int) -> tuple[list[dict[str, Any]], str]:
    counts: dict[str, int] = defaultdict(int)
    minor: dict[str, int] = defaultdict(int)
    for code, row in unit["rows"].items():
        label = NOT_STATED if code == "--" else RELIGIONS[code][0]
        counts[label] += row[0]
    none = population - unit["total"][0]
    counts[NONE] += none
    out: dict[str, int] = {}
    for label, n in counts.items():
        if label in (NONE, NOT_STATED) or label == OTHER or 100.0 * n / population >= MIN_SHARE:
            out[label] = out.get(label, 0) + n
        else:
            minor[label] += n
    if minor:
        out[OTHER] = out.get(OTHER, 0) + sum(minor.values())
    named = [f"{k} {v:,}" for k, v in sorted(minor.items())]
    named += [f"{name} {unit['rows'][c][0]:,}" for c, name in (("06", "Minh Su Dao"),
                                                               ("07", "Minh Ly Dao"))
              if c in unit["rows"] and unit["rows"][c][0]]
    ordered = sorted(((g, c) for g, c in out.items() if c > 0), key=lambda kv: (-kv[1], kv[0]))
    shares = vn.whole_hundred([100.0 * c / population for _, c in ordered])
    rows = [{"group": g, "pct": p, "count": c} for (g, c), p in zip(ordered, shares)]
    return rows, ", ".join(named)


def build(units: list[dict[str, Any]], populations: dict[str, dict[str, Any]],
          admin1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = {vn.fold(u["name"]): u for u in admin1}
    out = []
    used = set()
    for p in (u for u in units if u["kind"] == "province"):
        name = p["name"]
        shape = next((keys[vn.fold(k)] for k in [name, *vn.PROVINCES[name]]
                      if vn.fold(k) in keys), None)
        if shape is None or shape["id"] in used:
            raise SystemExit(f"vietnam_religion: {name} binds {'no' if shape is None else 'a'} "
                             f"polygon{'' if shape is None else ' twice'}")
        used.add(shape["id"])
        population = populations[p["code"]]["population"]
        rows, other = composition(p, population)
        followers = p["total"][0]
        note = (f"Religion as the 2009 census counted it in {name} (province code {p['code']}): "
                f"the followers of each religion, from Table 7 of the census's Completed Results "
                f"({followers:,} people), and everyone else in the province's Table 1 count "
                f"({population:,}) as \"No religion\" -- the answer the volume does not print as "
                f"a row, so the province's {population - followers:,} who followed none are its "
                f"two counts subtracted. The census counted followers of the thirteen religions "
                f"the state recognised; ancestor worship and folk practice are not a religion in "
                f"its question. The 2019 census asked religion too and published it for the "
                f"whole country only.")
        if other:
            note += f" \"Other religions\" here: {other}."
        out.append(record(
            f"VNM-REL2009-{p['code']}", shape["name"], level="admin1", parent="VNM",
            country="VNM", match_by="shape_id", shape_id=shape["id"],
            religion=rows, religion_year=YEAR, religion_note=note,
            sources=[{"field": "religion", "name": SOURCE, "url": PAGE, "year": YEAR,
                      "license": vn.LICENCE}]))
    left = sorted(u["name"] for u in admin1 if u["id"] not in used)
    log(f"  {len(out)} provinces bound; polygons left without a province: {left}")
    # Côn Đảo is a district of Bà Rịa-Vũng Tàu drawn at the first level: the
    # province's figure is not copied onto it, and it says so.
    for u in admin1:
        if u["id"] in used:
            continue
        out.append(record(
            f"VNM-REL2009-{vn.fold(u['name'])}", u["name"], level="admin1", parent="VNM",
            country="VNM", match_by="shape_id", shape_id=u["id"],
            religion=gap(NOT_AVAILABLE, (
                f"{u['name']} is not a province: the boundary file draws a district at the first "
                f"level here. The 2009 census publishes religion by province and above (Completed "
                f"Results, Table 7) and the 2019 census for the country only, so no count reaches "
                f"the district, and its province's figure is not copied onto it."))))
    return out


def page_texts(path) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    log(f"  {len(reader.pages)} pages")
    return [(page.extract_text() or "") for page in reader.pages]


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log(f"vietnam_religion: {SOURCE}")
    path = download(PDF, RAW / "vietnam" / "KQ-toan-bo-2009.pdf")
    pages = page_texts(path)
    _, populations = read_populations(pages)
    units = read_religions(pages)
    check(units, populations)
    records = build(units, populations, drawn("VNM", "admin1"))
    for r in records:
        if isinstance(r["religion"], list):
            top = ", ".join(f"{g['group']} {g['pct']}" for g in r["religion"][:3])
            log(f"    {r['name']:18} {top}")
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
