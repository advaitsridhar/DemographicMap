#!/usr/bin/env python3
"""China's counties from the provinces' own 2020 census yearbooks, where the drawn polygon is still the county.

The National Bureau of Statistics' census yearbook stops at the province
(``china_census``). Several provincial statistics bureaus publish their own
2020 census yearbook in the same tabulation format, and theirs go down to the
county: Table 1-1 (各地区户数、人口数和性别比), Table 1-4 (各地区分性别、民族的人口)
and Table 1-5 (各地区分年龄、性别的人口), each by prefecture and by every
district, county, county-level city and special zone inside it. The three are
read for the provinces in ``PROVINCES``, from the bureau's own site where it
answers and from the Internet Archive's capture of the same file where it does
not.

**What the map draws.** China's 2,370 second-level polygons are a county
division of the mid-1990s, so a 2020 county row belongs on a polygon only where
the polygon is still that one county. Five tests, all of which must pass:

1. the row is a county, autonomous county, banner or county-level city -- its
   GB/T 2260 code ends 21 or higher -- never a district (区), whose ground the
   cities have redrawn, and never a development zone;
2. its prefecture lists no development zone, scenic area or other special
   unit: the yearbooks count those apart from the counties whose ground they
   were cut from (Jilin's Changbai Mountain zones hold 61,146 people taken from
   Antu, Fusong and Changbai), so a county row beside one may be short of its
   ground. ``CUT_FROM`` names the prefectures a unit listed outside every
   prefecture was cut from;
3. ``data/processed/code_shapes.json`` binds the code to the polygon -- the
   code's Wikidata item stands inside it and its name is the polygon's;
4. the polygon holds that county's seat and no other current county-level
   seat (``data/raw/wikidata_points/CHN_P442_seats.json``, from ``china_seats``): one
   holding two is a county a later district was cut from, or a city;
5. where the map already carries an older population for the polygon, the 2020
   count is within ``DRIFT`` of it: a county that lost or gained ground since
   would show as a jump no ten years of migration explain.

Wikidata names no figure here. It is only the bridge from a yearbook's Chinese
county name to its GB/T 2260 code (``--fetch-names`` writes
data/raw/wikidata_points/CHN_P442_zh.json) and, through code_shapes, to the
polygon.

**Checks**, each a refusal: the three tables list the same areas and count the
same people in each; age groups and nationalities add up to every area's
total; every prefecture's counties and zones add up to the prefecture, the
prefectures and the units the province administers directly to the province,
and the province to the National Bureau's own 2020 count for it
(``china_census_province.json``).

Fields: population, sex ratio (males per 100 females), the median age
interpolated within the five-year group that holds the middle person (Table
1-5 prints no single years below the nation), and the 56 nationalities, a
nationality too small to show at one decimal joining 'Other ethnic groups'.
Language is not asked by the census (``china_census.LANGUAGE_NOTE``).

Usage:
    python -m scripts.fetch_census.china_county_census --fetch-names   # runner, once
    python -m scripts.fetch_census.china_county_census
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from collections import Counter
from typing import Any

from ._shared import NOT_COLLECTED, PROCESSED, RAW, gap, http_get, log, measure, record, write_json
from .china_census import (LANGUAGE_NOTE, compact, grouped, number, pooled, read_a0101, read_a0104,
                           read_a0105)
from .china_wiki import RESIDUAL
from .east_asia_common import drawn, hundred, sex_ratio

OUT = "china_county_census.json"
YEAR = 2020
NAMES = RAW / "wikidata_points" / "CHN_P442_zh.json"
SEATS = RAW / "wikidata_points" / "CHN_P442_seats.json"
CODE_SHAPES = PROCESSED / "code_shapes.json"
PROVINCE_FILE = PROCESSED / "china_census_province.json"
CDX = "https://web.archive.org/cdx/search/cdx"
REPLAY = "https://web.archive.org/web/{stamp}id_/{url}"
TABLES = {"A0101": "Table 1-1: households, population and sex ratio by area",
          "A0104": "Table 1-4: population by sex and nationality (民族), by area",
          "A0105": "Table 1-5: population by age and sex, by area"}
DRIFT = (0.6, 1.6)            # 2020 count against an older figure for the same polygon
LICENCE = "Official statistics of the provincial bureau of statistics, cited as published"

# The provinces whose 2020 census yearbook prints the three tables by county,
# in the National Bureau's own format (zk/html/A0101.xls ...).
PROVINCES: dict[str, dict[str, str]] = {
    "22": {"name": "Jilin Province", "zh": "吉林",
           "base": "http://tjj.jl.gov.cn/tjsj/qwfb/jlsdqcqgrkpcnj/zk/html/",
           "bureau": "Jilin Provincial Bureau of Statistics",
           "book": "吉林省第七次全国人口普查年鉴 (census yearbook of Jilin's seventh national census)"},
    "32": {"name": "Jiangsu Province", "zh": "江苏",
           "base": "https://tj.jiangsu.gov.cn/2020pcnj/zk/html/",
           "bureau": "Jiangsu Provincial Bureau of Statistics",
           "book": "江苏省2020年人口普查年鉴 (Jiangsu population census yearbook 2020)"},
    "63": {"name": "Qinghai Province", "zh": "青海",
           "base": "http://tjj.qinghai.gov.cn/nj/rkpc/zk/html/",
           "bureau": "Qinghai Provincial Bureau of Statistics",
           "book": "青海省2020年人口普查年鉴 (Qinghai population census yearbook 2020)"},
}

# The special units a yearbook lists outside every prefecture, and the
# prefectures whose counties they were cut from: those counties' rows are short
# of the ground their polygons draw. A province listing such a unit not named
# here is refused until someone says where it came from.
CUT_FROM: dict[str, tuple[tuple[str, ...], str]] = {
    "长白山管委会": (("2206", "2224"), (
        "the Changbai Mountain Protection and Development Zone's three districts (池北区, "
        "池西区, 池南区) were cut from Antu county in Yanbian and from Fusong and Changbai "
        "counties in Baishan")),
}

POPULATION_NOTE = (
    "The 2020 census count of this county, {book}, Table 1-1, read for the polygon because the "
    "polygon is still this one county: it holds the county's seat and no other county-level "
    "seat of today, and its name is the county's.")
AGE_NOTE = ("Interpolated within the age group (0, 1-4, then five-year groups to 95-99, and 100 "
            "and over) that holds the middle person, from Table 1-5 of the same yearbook, which "
            "prints no single years below the nation.")


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def archived(url: str) -> str | None:
    query = urllib.parse.urlencode({"url": url, "output": "json", "filter": "statuscode:200",
                                    "fl": "timestamp", "limit": "-1"})
    rows = json.loads(http_get(f"{CDX}?{query}", cache=False, retries=2, timeout=120) or "[]")
    return rows[-1][0] if len(rows) > 1 else None


def fetch_table(base: str, table: str) -> tuple[list[list[Any]], str]:
    """A yearbook workbook's rows, and the address they were read from: the
    bureau's own file, or the Internet Archive's newest capture of it."""
    import xlrd
    url = f"{base}{table}.xls"
    tried = []
    for source in ("live", "archive"):
        try:
            if source == "live":
                where = url
                blob = http_get(url, binary=True, cache=True, retries=1, timeout=60)
            else:
                stamp = archived(url)
                if not stamp:
                    tried.append("no capture in the Internet Archive")
                    continue
                where = REPLAY.format(stamp=stamp, url=url)
                blob = http_get(where, binary=True, cache=True, retries=3, timeout=180)
            assert isinstance(blob, bytes)
            sheet = xlrd.open_workbook(file_contents=blob).sheet_by_index(0)
            return [sheet.row_values(i) for i in range(sheet.nrows)], where
        except Exception as exc:  # noqa: BLE001 - the next source is tried, then refused
            tried.append(f"{source}: {type(exc).__name__}: {str(exc)[:120]}")
    raise SystemExit(f"china_county_census: {url} could not be read ({'; '.join(tried)})")


NAME_QUERY = """
SELECT ?code ?zh WHERE {
  ?item wdt:P442 ?code ; wdt:P17 wd:Q148 .
  FILTER(REGEX(STR(?code), "^[0-9]{2} ?[0-9]{2} ?[0-9]{2}$"))
  FILTER NOT EXISTS { ?item wdt:P576 ?gone . }
  ?item rdfs:label ?zh . FILTER(LANG(?zh) IN ("zh", "zh-hans", "zh-cn"))
}
"""


def fetch_names() -> int:
    """{six-figure GB/T 2260 code: [its current Chinese names]}, from Wikidata."""
    from fetch_wikidata import sparql, value  # noqa: PLC0415 (scripts/ is on the path)
    names: dict[str, set[str]] = {}
    for row in sparql(NAME_QUERY, cache=False, retries=2):
        code = re.sub(r"\s", "", value(row, "code") or "")
        if re.fullmatch(r"\d{6}", code) and value(row, "zh"):
            names.setdefault(code, set()).add(compact(value(row, "zh")))
    NAMES.parent.mkdir(parents=True, exist_ok=True)
    NAMES.write_text(json.dumps({c: sorted(v) for c, v in sorted(names.items())},
                                ensure_ascii=False, separators=(",", ":")) + "\n",
                     encoding="utf-8")
    log(f"china_county_census: {len(names)} codes with Chinese names -> {NAMES}")
    return 0


# ---------------------------------------------------------------------------
# Reading a provincial yearbook
# ---------------------------------------------------------------------------

def area_rows(rows: list[list[Any]]) -> dict[int, list[Any]]:
    """Every area row in the table's own order, keyed by its position: the
    rows below the 地区 header whose label is not blank and whose first
    figure is a number, the province first. A provincial table can repeat a
    name (two 朝阳区 in one province), so the order is the key."""
    out: dict[int, list[Any]] = {}
    started = False
    for row in rows:
        if not row:
            continue
        label = compact(row[0])
        if not started:
            started = label == "地区"
            continue
        if label and len(row) > 1 and number(row[1]) is not None:
            out[len(out)] = row
    if not out:
        raise SystemExit("china_county_census: a table has no area rows below its 地区 header")
    return out


def labels_of(rows: list[list[Any]]) -> list[str]:
    return [compact(r[0]) for r in area_rows(rows).values()]


SUFFIX = re.compile(r"(自治县|自治旗|县|旗|市|区|特区|林区|行政委员会|行委)$")


def stem(name: str) -> str:
    return SUFFIX.sub("", name)


def code_of(name: str, prefix: str, names: dict[str, list[str]],
            level: str) -> str | None:
    """The one current code under ``prefix`` whose Chinese name is ``name``
    (exactly, or failing that by stem, so a county made a district since the
    census still meets its own row), at the prefecture level or below it."""
    def candidates(match) -> list[str]:
        out = []
        for code, zh in names.items():
            if not code.startswith(prefix):
                continue
            if level == "prefecture" and not (code.endswith("00") and not code.endswith("0000")):
                continue
            if level == "county" and code.endswith("00"):
                continue
            if any(match(z) for z in zh):
                out.append(code)
        return out
    exact = candidates(lambda z: z == name)
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None
    by_stem = candidates(lambda z: stem(z) == stem(name) and stem(name))
    return by_stem[0] if len(by_stem) == 1 else None


def closes(totals: list[float], start: int, whole: float, stop: set[int]) -> int | None:
    """The last row of the run starting at ``start`` that adds up to exactly
    ``whole``, stopping at a row in ``stop``; None if no run does."""
    run = 0.0
    for j in range(start, len(totals)):
        if j in stop:
            return None
        run += totals[j]
        if abs(run - whole) < 0.5:
            return j
        if run > whole + 0.5:
            return None
    return None


def hierarchy(labels: list[str], totals: list[float], code: str,
              names: dict[str, list[str]]) -> list[dict[str, Any]]:
    """The province's rows as areas: {index, label, kind, code, prefecture, head}.

    The first row is the province. Below it, a row that names one of the
    province's prefectures heads the rows after it until they add up to its
    total; a county-level row outside every prefecture is one the province
    administers directly (Jilin's Meihekou); and any other row heads a special
    unit (a development zone, a management committee), with the rows after it
    that add up to it. A row inside a prefecture that names none of its
    counties is a special unit of that prefecture."""
    if len(labels) < 2:
        raise SystemExit("china_county_census: a table with no areas below the province")
    prefs = {i: code_of(labels[i], code, names, "prefecture") for i in range(1, len(labels))}
    heads = {i for i, p in prefs.items() if p}
    out = [{"index": 0, "label": labels[0], "kind": "province", "code": f"{code}0000",
            "prefecture": None, "head": None}]
    i = 1
    while i < len(labels):
        if prefs[i]:
            end = closes(totals, i + 1, totals[i], heads - {i})
            if end is None:
                raise SystemExit(f"china_county_census: {labels[i]}'s areas do not add up to it")
            out.append({"index": i, "label": labels[i], "kind": "prefecture", "code": prefs[i],
                        "prefecture": None, "head": None})
            prefix = prefs[i][:4]
            for j in range(i + 1, end + 1):
                county = code_of(labels[j], prefix, names, "county")
                out.append({"index": j, "label": labels[j],
                            "kind": "county" if county else "special", "code": county,
                            "prefecture": prefs[i], "head": None})
            i = end + 1
            continue
        county = code_of(labels[i], code, names, "county")
        if county:
            out.append({"index": i, "label": labels[i], "kind": "direct", "code": county,
                        "prefecture": None, "head": None})
            i += 1
            continue
        end = closes(totals, i + 1, totals[i], heads)
        out.append({"index": i, "label": labels[i], "kind": "special", "code": None,
                    "prefecture": None, "head": None})
        for j in range(i + 1, (end or i) + 1):
            out.append({"index": j, "label": labels[j], "kind": "special", "code": None,
                        "prefecture": None, "head": i})
        i = (end or i) + 1
    return out


def read_province(code: str, tables: dict[str, list[list[Any]]],
                  names: dict[str, list[str]]) -> tuple[list[dict[str, Any]], dict, dict, dict]:
    """The areas, and the three tables' figures keyed by row position."""
    labels = labels_of(tables["A0101"])
    for table in ("A0104", "A0105"):
        if labels_of(tables[table]) != labels:
            raise SystemExit(f"china_county_census: {code}: {table} lists other areas than 1-1")
    a0101 = read_a0101(tables["A0101"], area_rows)
    a0104 = read_a0104(tables["A0104"], area_rows)
    a0105 = read_a0105(tables["A0105"], area_rows)
    totals = [a0101[i]["total"] for i in range(len(labels))]
    areas = hierarchy(labels, totals, code, names)
    check(code, areas, a0101, a0104, a0105)
    return areas, a0101, a0104, a0105


def check(code: str, areas: list[dict[str, Any]], a0101: dict, a0104: dict, a0105: dict) -> None:
    where = PROVINCES.get(code, {}).get("name", code)
    for i, row in a0101.items():
        for what in ("total", "men", "women"):
            if not (row[what] == a0104[i][what] == a0105[i][what]):
                raise SystemExit(f"china_county_census: {where} row {i} {what}: the tables differ")
        if row["men"] + row["women"] != row["total"]:
            raise SystemExit(f"china_county_census: {where} row {i}: men and women miss the total")
        for name, table in (("1-4", a0104), ("1-5", a0105)):
            if sum(table[i]["groups"].values()) != table[i]["total"]:
                raise SystemExit(f"china_county_census: {where} row {i}: {name}'s groups miss "
                                 "the total")
    prefectures = [a for a in areas if a["kind"] == "prefecture"]
    if not prefectures:
        raise SystemExit(f"china_county_census: {where}: no prefecture recognised")
    for pref in prefectures:
        kids = [a for a in areas if a["prefecture"] == pref["code"]]
        for what in ("total", "men", "women"):
            summed = sum(a0101[a["index"]][what] for a in kids)
            if summed != a0101[pref["index"]][what]:
                raise SystemExit(f"china_county_census: {where}: {pref['label']}'s areas make "
                                 f"{summed:,.0f} {what} against its {a0101[pref['index']][what]:,.0f}")
    top = [a for a in areas if a["kind"] in ("prefecture", "direct", "special")
           and a["prefecture"] is None and a["head"] is None]
    for what in ("total", "men", "women"):
        summed = sum(a0101[a["index"]][what] for a in top)
        if summed != a0101[0][what]:
            raise SystemExit(f"china_county_census: {where}: the prefectures make {summed:,.0f} "
                             f"{what} against the province's {a0101[0][what]:,.0f}")


# ---------------------------------------------------------------------------
# Binding and records
# ---------------------------------------------------------------------------

def bind(code: str, areas: list[dict[str, Any]], a0101: dict, code_shapes: dict[str, Any],
         seats: dict[str, list[str]], units: dict[str, dict[str, Any]]
         ) -> tuple[dict[int, str], Counter]:
    """{row position: shape id} for the county rows that pass all five tests,
    and why the others did not."""
    zoned = {a["prefecture"] for a in areas if a["kind"] == "special" and a["prefecture"]}
    cut: set[str] = set()
    for area in areas:
        if area["kind"] == "special" and area["prefecture"] is None and area["head"] is None:
            if area["label"] not in CUT_FROM:
                raise SystemExit(f"china_county_census: {area['label']} is listed outside every "
                                 "prefecture and CUT_FROM does not say whose ground it holds")
            cut.update(f"{p}00" for p in CUT_FROM[area["label"]][0])
    bound: dict[int, str] = {}
    why: Counter = Counter()
    used: set[str] = set()
    for area in areas:
        if area["kind"] not in ("county", "direct"):
            continue
        unit_code = area["code"]
        if int(unit_code[4:]) < 21:
            why["a district"] += 1
            continue
        pref = area["prefecture"] or unit_code[:4] + "00"
        if pref in zoned:
            why["a zone in its prefecture"] += 1
            continue
        if pref in cut:
            why["a zone outside it cut from its prefecture"] += 1
            continue
        entry = code_shapes.get(unit_code)
        if not entry:
            why["no polygon bound to its code"] += 1
            continue
        shape = entry["shape_id"]
        if seats.get(shape) != [unit_code]:
            why["its polygon holds other seats"] += 1
            continue
        older = (units.get(shape) or {}).get("population") or {}
        if isinstance(older.get("value"), (int, float)) and (older.get("year") or 0) < YEAR:
            ratio = a0101[area["index"]]["total"] / older["value"]
            if not DRIFT[0] <= ratio <= DRIFT[1]:
                why["a jump from the polygon's older figure"] += 1
                log(f"    {area['label']} ({unit_code}): {a0101[area['index']]['total']:,.0f} "
                    f"against {older['value']:,} ({older.get('year')}), not bound")
                continue
        if shape in used:
            raise SystemExit(f"china_county_census: {shape} would be bound twice")
        used.add(shape)
        bound[area["index"]] = shape
    return bound, why


def county_record(code: str, area: dict[str, Any], shape: str, unit: dict[str, Any],
                  parents: dict[str, str], a0101: dict, a0104: dict, a0105: dict,
                  urls: dict[str, str]) -> dict[str, Any]:
    province = PROVINCES[code]
    book = f"{province['bureau']}, {province['book']}"
    i = area["index"]
    counts, small, small_people = pooled(a0104[i]["groups"])
    residual = int(a0104[i]["groups"].get(RESIDUAL, 0))
    parts = []
    if residual:
        parts.append(f"the {residual:,} people whose nationality is not identified (未定族称) "
                     "and naturalised citizens (入籍)")
    if small:
        parts.append(f"the {small_people:,} people of the {small} nationalities too few to "
                     "show at one decimal")
    other = (" 'Other ethnic groups' is " + " and ".join(parts) + ".") if parts else ""
    sources = [{"field": "population/sex_ratio", "name": f"{book}, {TABLES['A0101']}",
                "url": urls["A0101"], "year": YEAR, "license": LICENCE},
               {"field": "ethnicity", "name": f"{book}, {TABLES['A0104']}",
                "url": urls["A0104"], "year": YEAR, "license": LICENCE},
               {"field": "median_age", "name": f"{book}, {TABLES['A0105']}",
                "url": urls["A0105"], "year": YEAR, "license": LICENCE}]
    return record(
        f"CHN-{shape}", unit["name"], level="admin2",
        parent=parents.get(unit.get("parent"), "CHN"), country="CHN",
        match_by="shape_id", shape_id=shape, aliases=[area["label"]],
        codes={"gb2260": area["code"]},
        population=measure(int(a0101[i]["total"]), year=YEAR, source=f"{book}, Table 1-1"),
        population_note=POPULATION_NOTE.format(book=book),
        sex_ratio=sex_ratio(a0101[i]["men"], a0101[i]["women"], year=YEAR,
                            source=f"{book}, Table 1-1"),
        sex_ratio_note=f"{int(a0101[i]['men']):,} men and {int(a0101[i]['women']):,} women.",
        median_age=measure(grouped(a0105[i]["groups"]), unit="years", year=YEAR,
                           source=f"{book}, Table 1-5"),
        median_age_note=AGE_NOTE,
        ethnicity=hundred(counts), ethnicity_year=YEAR,
        ethnicity_note=(
            f"2020 census, Table 1-4 of {book}: the 56 nationalities (民族) of all "
            f"{int(a0104[i]['total']):,} residents.{other}"),
        language=gap(NOT_COLLECTED, LANGUAGE_NOTE),
        sources=sources)


def build(code: str, tables: dict[str, list[list[Any]]], names: dict[str, list[str]],
          code_shapes: dict[str, Any], seats: dict[str, list[str]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          national: float | None = None, urls: dict[str, str] | None = None
          ) -> list[dict[str, Any]]:
    areas, a0101, a0104, a0105 = read_province(code, tables, names)
    where = PROVINCES[code]["name"]
    urls = urls or {t: f"{PROVINCES[code]['base']}{t}.xls" for t in TABLES}
    if national is not None and a0101[0]["total"] != national:
        raise SystemExit(f"china_county_census: {where}'s yearbook counts {a0101[0]['total']:,.0f}"
                         f" and the National Bureau's {national:,.0f}")
    units = {u["id"]: u for u in admin2}
    parents = {u["id"]: f"CHN-{u['name']}" for u in admin1}
    bound, why = bind(code, areas, a0101, code_shapes, seats, units)
    out = [county_record(code, area, bound[area["index"]], units[bound[area["index"]]], parents,
                         a0101, a0104, a0105, urls)
           for area in areas if area["index"] in bound]
    kinds = Counter(a["kind"] for a in areas)
    log(f"  {where}: {kinds['prefecture']} prefectures, {kinds['county'] + kinds['direct']} "
        f"county-level areas, {kinds['special']} special; {len(out)} bound; not bound: "
        f"{dict(why)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch-names", action="store_true",
                    help="write the GB/T 2260 codes' Chinese names from Wikidata, and stop")
    args = ap.parse_args()
    if args.fetch_names:
        return fetch_names()
    for path in (NAMES, SEATS, CODE_SHAPES):
        if not path.exists():
            raise SystemExit(f"china_county_census: {path} is missing")
    names = json.loads(NAMES.read_text(encoding="utf-8"))
    seats = json.loads(SEATS.read_text(encoding="utf-8"))
    code_shapes = json.loads(CODE_SHAPES.read_text(encoding="utf-8"))["CHN"]
    nbs = {}
    if PROVINCE_FILE.exists():
        nbs = {r["name"]: r["population"]["value"]
               for r in json.loads(PROVINCE_FILE.read_text(encoding="utf-8"))
               if isinstance(r.get("population"), dict) and "value" in r["population"]}
    admin1, admin2 = drawn("CHN", "admin1"), drawn("CHN", "admin2")
    records: list[dict[str, Any]] = []
    for code, province in PROVINCES.items():
        log(f"china_county_census: {province['bureau']}, {province['book']}")
        tables, urls = {}, {}
        for table in TABLES:
            tables[table], urls[table] = fetch_table(province["base"], table)
        records += build(code, tables, names, code_shapes, seats, admin1, admin2,
                         nbs.get(province["name"]), urls)
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} county records to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
