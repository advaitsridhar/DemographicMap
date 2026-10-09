#!/usr/bin/env python3
"""China's provinces from the 2020 census's own tables, and the two SARs' ages from theirs.

The National Bureau of Statistics publishes the tabulation volumes of the
Seventh National Population Census (中国人口普查年鉴-2020) on its site as one
workbook per table (www.stats.gov.cn/sj/pcsj/rkpc/7rp/zk/html/A....xls).
Four are read, each by the 31 provinces, autonomous regions and
municipalities and the 全国 row:

* **1-1** (A0101) 各地区户数、人口数和性别比 -- the population, men, women and
  the printed sex ratio;
* **1-4** (A0104) 各地区分性别、民族的人口 -- the 56 nationalities (民族), the
  people whose nationality is not identified (未定族称人口) and naturalised
  citizens (入籍), by sex: the ethnicity composition, the Bureau's own table
  where ``china_wiki`` reads the provinces' Wikipedia transcriptions of it;
* **1-5** (A0105) 各地区分年龄、性别的人口 -- five-year age groups (with 0 and
  1-4 apart, and 100 and over) by sex: the median age, **interpolated within
  the five-year group** that holds the middle person, because the national
  volumes print single years only for the country (3-1); the note says so;
* **3-1** (A0301) 全国分年龄、性别的人口 -- the nation by single year, only to
  check the grouped method: the national median from 3-1's single years and
  from 1-5's groups must agree within ``NATIONAL_TOLERANCE``.

**Checks**, each a refusal: in every province the three tables count the
same people and the same men and women; the age groups and the nationalities
add up to the total; the provinces add up to the 全国 row in each table; the
sex ratio recomputed from the counts is the one printed.

**Hong Kong and Macau** are first-level units of this map and their censuses
are their own: Hong Kong's 2021 Population Census key statistics (median age
46.3, 839 males per 1,000 females, in the Main Results workbook's KeyStat1
sheet) and Macau's 2021 census Detailed Results (median age 38.4 of the total
population, and 320,285 males and 361,785 females) are read from the same
files ``hongkong_census`` and ``macau_census`` read, for those two fields.

**Language.** The census asks no question about language: its long and
short forms record 民族 (nationality) and no language, and none of the
yearbook's volumes -- 概要, 民族, 年龄, 教育, ... -- carries a table of
it. Every province's record says so. Religion the census does not ask
either, and every record says so in its own words (``PROVINCE_RELIGION_NOTE``,
``COUNTY_RELIGION_NOTE``): the China policy's sentence names the China Family
Panel Studies' 2012 wave where the five provinces it reaches carry the 2016
one. Hong Kong and Macau take their own censuses, which do not ask religion
either, and their records say that instead (``HK_RELIGION_NOTE``,
``MO_RELIGION_NOTE``).

**The county polygons** (``china_census_county.json``). The yearbook's
tables stop at the province, and the 2,370 second-level polygons the map
draws follow a county division older than 2000 -- Guangdong's Panyu,
Huadu, Nanhai and Shunde are drawn as the county-level cities they were
before they became districts in 2000 and 2002 -- so no 2020 county table is
laid on them here. Every mainland polygon gets its reasons instead:
language is not collected (as above), and the population, median age, sex
ratio and nationality, which the census did count by county, are a stated
gap saying where the figures are and why they are not drawn. A population
another file gives a polygon is not touched: a gap never displaces a
figure.

**The SARs' second-level polygons.** The boundary file draws one second-level
polygon inside each SAR, and only one of them is the SAR. Measured against
the SAR's own first-level polygon in the CGAZ files the map is built from
(``SAR_COVERAGE``): "Xianggang" covers 441 of Hong Kong's 561 km², 79%, and is
Hong Kong drawn again; Macau's is an unnamed 1.4 km² fragment of southern
Coloane, 4% of Macau's 35.8 km². A polygon that covers at least ``WHOLE`` of
its SAR takes the SAR's median age and sex ratio; any other is a fragment and
says so, because a whole SAR's figure on a part of it is a region's figure on
its child. A SAR polygon this table has not measured stops the run.

Usage:
    python -m scripts.fetch_census.china_census
"""

from __future__ import annotations

import argparse
import io
import re
from collections import Counter
from typing import Any, Callable

from ._shared import NOT_COLLECTED, PROCESSED, gap, http_get, log, measure, record, write_json
from .china_wiki import DIVISIONS, NATIONALITIES, RESIDUAL
from .east_asia_common import (drawn, grouped_median, hundred, pool_small, sex_ratio,
                               single_year_median)

OUT = "china_census_province.json"
OUT_COUNTY = "china_census_county.json"
YEAR = 2020
BASE = "https://www.stats.gov.cn/sj/pcsj/rkpc/7rp/zk/html/{table}.xls"
INDEX = "https://www.stats.gov.cn/sj/pcsj/rkpc/7rp/zk/indexch.htm"
NBS = "National Bureau of Statistics of China"
YEARBOOK = f"{NBS}, China Population Census Yearbook 2020 (中国人口普查年鉴-2020)"
SOURCES = {
    "A0101": f"{YEARBOOK}, Table 1-1: households, population and sex ratio by region",
    "A0104": f"{YEARBOOK}, Table 1-4: population by sex and nationality (民族), by region",
    "A0105": f"{YEARBOOK}, Table 1-5: population by age and sex, by region",
    "A0301": f"{YEARBOOK}, Table 3-1: national population by single year of age and sex",
}
LICENCE = "Official statistics of the National Bureau of Statistics of China, cited as published"
NATIONAL_TOLERANCE = 0.3      # years, single-year national median against the grouped one
RATIO_TOLERANCE = 0.006       # the printed sex ratio has two decimals
NATIONAL = "全国"
UNIDENTIFIED = ("未定族称人口", "入籍")

LANGUAGE_NOTE = (
    "China's census asks no question about language: the 2020 census forms record "
    "nationality (民族) and nothing about the language a person speaks, and no volume of the "
    "census yearbook -- 概要, 民族, 年龄, 教育 and the rest -- carries a table of it. Language "
    "use has been measured once nationally, by the State Language Commission's survey "
    "(中国语言文字使用情况调查, fielded 1998-2000), whose provincial tables are printed in a "
    "book (中国语言文字使用情况调查资料, 2006) and published nowhere as data; this map has not "
    "read them, so the field is not available rather than never collected.")
# Not "not_collected": a survey did measure it (BRIEF: that status is only for
# a field nothing measures).
LANGUAGE_STATUS = "not_available"

# Religion, said on every unit this file writes rather than left to the China
# policy's sentence, which names the survey's 2012 wave where the five
# provinces carry its 2016 one, and which is about the mainland's census --
# the SARs take their own censuses, which do not ask it either.
PROVINCE_RELIGION_NOTE = (
    "China's census does not ask religion; it records the 56 official nationalities (民族) "
    "instead. The China Family Panel Studies, a national survey, asks it, and its 2016 wave "
    "supports province-level figures for five provinces (Shanghai, Liaoning, Henan, Gansu, "
    "Guangdong), which carry them; for the other provinces its sample is not drawn to be read "
    "by province.")
COUNTY_RELIGION_NOTE = (
    "China's census does not ask religion; it records the 56 official nationalities (民族) "
    "instead, and no survey measures religion by county. The China Family Panel Studies' 2016 "
    "wave supports province-level figures for five provinces (Shanghai, Liaoning, Henan, Gansu, "
    "Guangdong), which carry them.")
HK_RELIGION_NOTE = (
    "Hong Kong's own census does not ask religion: the 2021 Population Census, like the "
    "censuses and by-censuses before it, asks ethnicity, language and place of birth but no "
    "question on religion, and the mainland's census, which does not ask it either, is not "
    "taken in the Special Administrative Region. The Hong Kong Yearbook gives the religious "
    "bodies' own estimates of their followers, which are not a count of residents.")
MO_RELIGION_NOTE = (
    "Macau's own census does not ask religion: neither the 2021 Population Census's Detailed "
    "Results nor the 2016 By-census's mentions it, and the mainland's census, which does not "
    "ask it either, is not taken in the Special Administrative Region.")

COUNTY_NOTE = (
    "The 2020 census counted every county's people by age, sex and nationality (民族). The "
    "National Bureau of Statistics' census yearbook (中国人口普查年鉴-2020) publishes its "
    "tables by province, and the province carries them. Some provinces' own census yearbooks "
    "print every county, and china_county_census writes those counts on a polygon only where "
    "it is still the one county counted: the boundary file's county polygons are a division "
    "of the mid-1990s (Guangdong's Panyu, Huadu, Nanhai and Shunde are drawn as the "
    "county-level cities they were before becoming districts in 2000 and 2002), and a 2020 "
    "county's figure on a polygon whose ground has changed would be another place's. No 2020 "
    "county count has been placed on this polygon: its province's yearbook has not been read, "
    "or the polygon is not one county of today.")

# The second-level polygons drawn inside the SARs, measured once against the
# SAR's first-level polygon in the CGAZ files the map is built from
# (geoBoundariesCGAZ_ADM1/ADM2.gpkg): the area of the polygon that lies inside
# its SAR, over the SAR's own area (km² on a cosine-of-latitude projection,
# which at 22°N is within a fraction of a per cent of the ellipsoid's). Shape
# ids are the boundary file's, so a new boundary release brings new ids and the
# run stops until they are measured again. {shape id: (coverage, what it is)}.
SAR_COVERAGE: dict[str, tuple[float, str]] = {
    "17275852B66204891178522": (0.786, (
        "This polygon is Hong Kong as the boundary file's second level draws it "
        "('Xianggang'), and these are the whole SAR's 2021 census figures, the same as on the "
        "first level. The boundary file draws Hong Kong without Hong Kong Island and Lantau at "
        "both levels: the first-level polygon is 561 km² of the SAR's 1,110 or so km² of land, "
        "and this one 441 km² of it, about two-fifths of the SAR's land, though Kowloon and "
        "the New Territories it covers hold most of its people.")),
    "17275852B34966799109471": (0.039, (
        "This polygon is not Macau: it is an unnamed fragment of southern Coloane in the "
        "boundary file, about 1.4 km² of the SAR's 35.8 km² (4%), and the only second-level "
        "polygon the file draws inside Macau. No census counts it as an area of its own, and "
        "a whole SAR's figure is not put on a part of it; Macau's 2021 census figures are on "
        "the first level.")),
}
WHOLE = 0.75            # a polygon covering this much of its SAR is the SAR drawn again
# Why the SAR drawn again carries the SAR's median, sex ratio and shares
# (hongkong_census writes those) but not its count.
SAR_COUNT_NOTE = (
    "This polygon is Hong Kong as the boundary file's second level draws it ('Xianggang'): "
    "441 km² of the SAR's 1,110 or so km² of land, without Hong Kong Island and Lantau. It "
    "carries the SAR's own median age, sex ratio and shares, which describe the SAR's people, "
    "most of whom it holds; the SAR's count is on the first-level polygon and is not written "
    "here, where it would be read as the people inside this polygon, and Hong Kong Island "
    "and Lantau are home to many of them. No census area of Hong Kong follows the polygon's "
    "edge, so no count of its own exists.")

# Hong Kong and Macau: their own 2021 censuses.
HK_URL = "https://www.census2021.gov.hk/doc/pub/21c-main-results.xlsx"
HK_SOURCE = ("Census and Statistics Department, Hong Kong SAR, 2021 Population Census: Main "
             "Results (December 2022), Key Statistics")
HK_LICENCE = ("Hong Kong Government; reproduction permitted with acknowledgement of the "
              "Census and Statistics Department as the source")
HK_NAME = "Hong Kong Special Administrative Region"
MO_URL = ("https://www.dsec.gov.mo/getAttachment/6cb29f2f-524a-488f-aed3-4d7207bb109e/"
          "E_CEN_PUB_2021_Y.aspx")
MO_SOURCE = ("Statistics and Census Service (DSEC), Macao SAR, Detailed Results of 2021 "
             "Population Census (revised, October 2022)")
MO_LICENCE = "Statistics and Census Service, Macao SAR; cited as published"
MO_NAME = "Macau Special Administrative Region"
MO_TOTAL = 682_070
MO_MEDIAN = re.compile(r"median age of the total population went up from [\d.]+ in 2001 and "
                       r"[\d.]+ in 2011 to ([\d.]+) in 2021")
MO_SEXES = re.compile(r"there were ([\d,]+) males and ([\d,]+) females")


# ---------------------------------------------------------------------------
# The yearbook's workbooks
# ---------------------------------------------------------------------------

def compact(cell: Any) -> str:
    return "".join(str(cell).split())


def number(cell: Any) -> float | None:
    if isinstance(cell, (int, float)):
        return float(cell)
    text = compact(cell).replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def province_names() -> dict[str, str]:
    """{the yearbook's short name ("内蒙古"): the drawn name}."""
    out = {}
    for drawn_name, _, chinese in DIVISIONS:
        short = re.sub(r"(壮族|回族|维吾尔)?(自治区|省|市)$", "", chinese)
        out[short] = drawn_name
    return out


def region_rows(rows: list[list[Any]]) -> dict[str, list[Any]]:
    """{region as printed, spaces removed: the row} for 全国 and the 31."""
    names = province_names()
    out = {}
    for row in rows:
        if not row:
            continue
        label = compact(row[0])
        if label == NATIONAL or label in names:
            if label in out:
                raise SystemExit(f"china_census: {label} appears twice in a table")
            out[label] = row
    missing = [n for n in [NATIONAL, *names] if n not in out]
    if missing:
        raise SystemExit(f"china_census: a table lacks rows for {missing}")
    return out


def headed_blocks(header: list[Any]) -> list[tuple[int, str]]:
    """(first column, label) of every three-column block in a header row."""
    return [(i, compact(cell)) for i, cell in enumerate(header) if i > 0 and compact(cell)]


def header_row(rows: list[list[Any]], first: str) -> list[Any]:
    for row in rows[:8]:
        if row and len(row) > 1 and compact(row[1]) == first:
            return row
    raise SystemExit(f"china_census: no header row whose first block is {first!r}")


# What picks a table's rows: the national yearbook's 全国 and 31 provinces by
# name, or (china_county_census) a provincial yearbook's every area in order.
Regions = Callable[[list[list[Any]]], dict[Any, list[Any]]]


def read_a0101(rows: list[list[Any]], regions: Regions | None = None
               ) -> dict[Any, dict[str, float]]:
    """{region: {"total", "men", "women", "printed_ratio"}}: the population
    block of 1-1 is columns 4-7 (合计, 男, 女, 性别比)."""
    out = {}
    for label, row in (regions or region_rows)(rows).items():
        total, men, women, ratio = (number(row[i]) for i in (4, 5, 6, 7))
        if None in (total, men, women, ratio):
            raise SystemExit(f"china_census: 1-1's {label} row is not four figures at 4-7")
        out[label] = {"total": total, "men": men, "women": women, "printed_ratio": ratio}
    return out


AGE_LABEL = re.compile(r"^(\d+)(?:-(\d+))?岁(及以上)?$")


def read_a0105(rows: list[list[Any]], regions: Regions | None = None
               ) -> dict[Any, dict[str, Any]]:
    """{region: {"total", "men", "women", "groups": {(lower, width): both sexes}}}."""
    blocks = headed_blocks(header_row(rows, "合计"))
    if blocks[0][1] != "合计":
        raise SystemExit("china_census: 1-5's first block is not 合计")
    groups: list[tuple[int, tuple[int, int | None]]] = []
    for column, label in blocks[1:]:
        found = AGE_LABEL.match(label)
        if not found:
            raise SystemExit(f"china_census: 1-5 has an age block {label!r} it cannot read")
        low = int(found.group(1))
        if found.group(3):
            width = None
        elif found.group(2):
            width = int(found.group(2)) - low + 1
        else:
            width = 1
        groups.append((column, (low, width)))
    out = {}
    for label, row in (regions or region_rows)(rows).items():
        total, men, women = (number(row[i]) for i in (1, 2, 3))
        by_group = {bounds: number(row[c]) for c, bounds in groups}
        if None in (total, men, women) or None in by_group.values():
            raise SystemExit(f"china_census: 1-5's {label} row has a blank figure")
        out[label] = {"total": total, "men": men, "women": women, "groups": by_group}
    return out


BLANK = {"", "-", "—", "–"}


def read_a0104(rows: list[list[Any]], regions: Regions | None = None, blanks: bool = False
               ) -> dict[Any, dict[str, Any]]:
    """{region: {"total", "men", "women", "groups": {label: people}}}.

    ``blanks``: a nationality's cell left empty or dashed is nobody, as a
    provincial yearbook prints a nationality none of an area's people
    belong to (Inner Mongolia's does); the area's groups must still add up
    to its total, which the caller checks. The National Bureau's own table
    prints every zero, so for it a blank is a fault."""
    blocks = headed_blocks(header_row(rows, "合计"))
    if blocks[0][1] != "合计":
        raise SystemExit("china_census: 1-4's first block is not 合计")
    columns: list[tuple[int, str]] = []
    for column, label in blocks[1:]:
        if label in UNIDENTIFIED:
            columns.append((column, RESIDUAL))
            continue
        name = NATIONALITIES.get(label.lower())
        if name is None:
            raise SystemExit(f"china_census: 1-4 has a nationality {label!r} it does not know")
        columns.append((column, name))
    named = {n for _, n in columns if n != RESIDUAL}
    if len(named) != 56:
        raise SystemExit(f"china_census: 1-4 names {len(named)} nationalities, not 56")
    out = {}
    for label, row in (regions or region_rows)(rows).items():
        total, men, women = (number(row[i]) for i in (1, 2, 3))
        counts: Counter = Counter()
        for column, name in columns:
            value = number(row[column]) if column < len(row) else None
            if value is None and blanks and compact(row[column] if column < len(row) else "") \
                    in BLANK:
                value = 0.0
            if value is None:
                raise SystemExit(f"china_census: 1-4's {label} row has a blank figure")
            counts[name] += value
        out[label] = {"total": total, "men": men, "women": women, "groups": dict(counts)}
    return out


SINGLE = re.compile(r"^(\d+)(?:\.0)?(岁)?$")
TOP = re.compile(r"^(\d+)岁及以上$")


def read_a0301(rows: list[list[Any]]) -> dict[int, float]:
    """{age: both sexes} for the nation, single years, the open top last."""
    out: dict[int, float] = {}
    for row in rows:
        if not row:
            continue
        label = compact(row[0])
        found = SINGLE.match(label) or TOP.match(label)
        if not found:
            continue
        value = number(row[1])
        if value is None:
            raise SystemExit(f"china_census: 3-1's {label} row has no total")
        out[int(found.group(1))] = value
    if sorted(out) != list(range(len(out))) or len(out) < 100:
        raise SystemExit(f"china_census: 3-1 has ages {sorted(out)[:3]}..{sorted(out)[-3:]}")
    return out


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check(a0101: dict[str, dict[str, float]], a0104: dict[str, dict[str, Any]],
          a0105: dict[str, dict[str, Any]], single: dict[int, float]) -> None:
    for label, row in a0101.items():
        for what in ("total", "men", "women"):
            if not (row[what] == a0104[label][what] == a0105[label][what]):
                raise SystemExit(f"china_census: {label} {what}: 1-1 {row[what]:,.0f}, 1-4 "
                                 f"{a0104[label][what]:,.0f}, 1-5 {a0105[label][what]:,.0f}")
        if row["men"] + row["women"] != row["total"]:
            raise SystemExit(f"china_census: {label}: men and women do not make the total")
        ratio = 100 * row["men"] / row["women"]
        if abs(ratio - row["printed_ratio"]) > RATIO_TOLERANCE:
            raise SystemExit(f"china_census: {label}: the sex ratio is {ratio:.3f} from the "
                             f"counts, printed {row['printed_ratio']}")
        for table, rows in (("1-4", a0104), ("1-5", a0105)):
            summed = sum(rows[label]["groups"].values())
            if summed != rows[label]["total"]:
                raise SystemExit(f"china_census: {label}: {table}'s groups make {summed:,.0f} "
                                 f"against {rows[label]['total']:,.0f}")
    provinces = [k for k in a0101 if k != NATIONAL]
    for what in ("total", "men", "women"):
        summed = sum(a0101[k][what] for k in provinces)
        if summed != a0101[NATIONAL][what]:
            raise SystemExit(f"china_census: the provinces hold {summed:,.0f} {what}, the 全国 "
                             f"row {a0101[NATIONAL][what]:,.0f}")
    if sum(single.values()) != a0101[NATIONAL]["total"]:
        raise SystemExit(f"china_census: 3-1's single years make {sum(single.values()):,.0f}, "
                         f"1-1's nation {a0101[NATIONAL]['total']:,.0f}")
    by_years = single_year_median(single)
    by_groups = grouped(a0105[NATIONAL]["groups"])
    if abs(by_years - by_groups) > NATIONAL_TOLERANCE:
        raise SystemExit(f"china_census: the national median is {by_years} from single years "
                         f"and {by_groups} from the groups")
    log(f"  31 provinces: the three tables agree on every count, every composition adds up, "
        f"the provinces make the nation's {a0101[NATIONAL]['total']:,.0f}; national median "
        f"{by_years} from single years, {by_groups} from the groups")


def grouped(groups: dict[tuple[int, int | None], float]) -> float | None:
    return grouped_median((low, width, n) for (low, width), n in groups.items())


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def sources() -> list[dict[str, Any]]:
    url = BASE.format
    return [
        {"field": "population/sex_ratio", "name": SOURCES["A0101"], "url": url(table="A0101"),
         "year": YEAR, "license": LICENCE},
        {"field": "ethnicity", "name": SOURCES["A0104"], "url": url(table="A0104"),
         "year": YEAR, "license": LICENCE},
        {"field": "median_age", "name": SOURCES["A0105"], "url": url(table="A0105"),
         "year": YEAR, "license": LICENCE},
    ]


def pooled(groups: dict[str, float]) -> tuple[dict[str, float], int, int]:
    """The nationalities as ``hundred`` shows them, every one too small to show
    at one decimal added to 'Other ethnic groups' rather than dropped, so the
    counts shown are all the people: (counts, how many nationalities were
    pooled, how many people they are). Only a group under 0.1% can fail to
    show -- one of 0.1% or more keeps at least that after rounding -- and
    pooling one can move the rounding of another, so it repeats until every
    group left shows."""
    counts, moved, people = pool_small(groups, RESIDUAL)
    return counts, len(moved), people


def province_record(label: str, shape: str, name: str, a0101: dict[str, float],
                    a0104: dict[str, Any], a0105: dict[str, Any]) -> dict[str, Any]:
    counts, small, small_people = pooled(a0104["groups"])
    composition = hundred(counts)
    residual = a0104["groups"].get(RESIDUAL, 0)
    shown = sum(row["count"] for row in composition)
    if shown < a0104["total"] * 0.9995:
        raise SystemExit(f"china_census: {label}'s nationalities shown count {shown:,} of "
                         f"{a0104['total']:,.0f}")
    tail = (f", and the {small_people:,} people of the {small} nationalities too few to show "
            "at one decimal (each under 0.1% of the province)" if small else "")
    return record(
        f"CHN-{name}", name, level="admin1", parent="CHN", country="CHN",
        match_by="shape_id", shape_id=shape,
        population=measure(int(a0101["total"]), year=YEAR, source=SOURCES["A0101"]),
        sex_ratio=sex_ratio(a0101["men"], a0101["women"], year=YEAR, source=SOURCES["A0101"]),
        sex_ratio_note=f"{int(a0101['men']):,} men and {int(a0101['women']):,} women.",
        median_age=measure(grouped(a0105["groups"]), unit="years", year=YEAR,
                           source=SOURCES["A0105"]),
        median_age_note=("Interpolated within the age group (0, 1-4, then five-year groups to "
                         "95-99, and 100 and over) that holds the middle person, from Table 1-5 "
                         "of the census yearbook, which prints single years only for the "
                         "nation."),
        ethnicity=composition, ethnicity_year=YEAR,
        ethnicity_note=(
            "2020 census, Table 1-4 of the census yearbook: the 56 nationalities (民族) the "
            f"census records, of all {int(a0104['total']):,} residents. 'Other ethnic groups' "
            f"is the {int(residual):,} people whose nationality is not identified (未定族称) "
            f"and naturalised citizens (入籍){tail}."),
        language=gap(LANGUAGE_STATUS, LANGUAGE_NOTE),
        religion=gap(NOT_COLLECTED, PROVINCE_RELIGION_NOTE),
        sources=sources())


def hong_kong(rows: list[list[Any]], shape: str) -> dict[str, Any]:
    """The KeyStat1 sheet: the median age and the males per 1,000 females
    (the first sex ratio row, which counts foreign domestic helpers) for 2021."""
    year_col = None
    found: dict[str, float] = {}
    for i, row in enumerate(rows):
        cells = [compact(c) for c in row]
        if year_col is None and "2021" in cells and "2016" in cells:
            year_col = cells.index("2021")
            continue
        if year_col is None:
            continue
        nxt = " ".join(compact(c) for c in rows[i + 1]) if i + 1 < len(rows) else ""
        if "年齡中位數" in cells and "Medianage" in nxt:
            found["median"] = number(row[year_col])
        if any(c.startswith("性別比率") for c in cells) and "sex" not in found:
            found["sex"] = number(row[year_col])
    if set(found) != {"median", "sex"} or None in found.values():
        raise SystemExit(f"hong kong: KeyStat1 gave {found}")
    return record(
        "CHN-Hong Kong", HK_NAME, level="admin1", parent="CHN", country="CHN",
        match_by="shape_id", shape_id=shape,
        median_age=measure(found["median"], unit="years", year=2021, source=HK_SOURCE),
        median_age_note="The Census and Statistics Department's own median, 2021 census.",
        sex_ratio=measure(round(found["sex"] / 10, 1), unit="males_per_100_females", year=2021,
                          source=HK_SOURCE),
        sex_ratio_note=(f"{found['sex']:.0f} males per 1,000 females, foreign domestic helpers "
                        "included, as the 2021 census's key statistics print it."),
        religion=gap(NOT_COLLECTED, HK_RELIGION_NOTE),
        sources=[{"field": "median_age/sex_ratio", "name": HK_SOURCE, "url": HK_URL,
                  "year": 2021, "license": HK_LICENCE}])


def macau(text: str, shape: str) -> dict[str, Any]:
    flat = " ".join(text.split())
    median = MO_MEDIAN.search(flat)
    sexes = MO_SEXES.search(flat)
    if not median or not sexes:
        raise SystemExit("macau: the Detailed Results no longer state the median age or the "
                         "males and females in the words this reads")
    men, women = (int(sexes.group(i).replace(",", "")) for i in (1, 2))
    if men + women != MO_TOTAL:
        raise SystemExit(f"macau: {men:,} males and {women:,} females are not {MO_TOTAL:,}")
    return record(
        "CHN-Macau", MO_NAME, level="admin1", parent="CHN", country="CHN",
        match_by="shape_id", shape_id=shape,
        median_age=measure(float(median.group(1)), unit="years", year=2021, source=MO_SOURCE),
        median_age_note=("DSEC's own median of the total population, 2021 census (39.7 for the "
                         "local population, which leaves out non-resident workers and "
                         "non-local students)."),
        sex_ratio=sex_ratio(men, women, year=2021, source=MO_SOURCE),
        sex_ratio_note=f"{men:,} males and {women:,} females, the whole population.",
        religion=gap(NOT_COLLECTED, MO_RELIGION_NOTE),
        sources=[{"field": "median_age/sex_ratio", "name": MO_SOURCE, "url": MO_URL,
                  "year": 2021, "license": MO_LICENCE}])


def build(tables: dict[str, list[list[Any]]], admin1: list[dict[str, Any]],
          hk_rows: list[list[Any]] | None = None, mo_text: str | None = None
          ) -> list[dict[str, Any]]:
    a0101 = read_a0101(tables["A0101"])
    a0104 = read_a0104(tables["A0104"])
    a0105 = read_a0105(tables["A0105"])
    single = read_a0301(tables["A0301"])
    check(a0101, a0104, a0105, single)
    shapes = {u["name"]: u["id"] for u in admin1}
    records = []
    for label, name in province_names().items():
        if name not in shapes:
            raise SystemExit(f"china_census: no drawn province called {name!r}")
        records.append(province_record(label, shapes[name], name, a0101[label], a0104[label],
                                       a0105[label]))
    if hk_rows is not None:
        records.append(hong_kong(hk_rows, shapes[HK_NAME]))
    if mo_text is not None:
        records.append(macau(mo_text, shapes[MO_NAME]))
    medians = sorted((r["median_age"]["value"], r["name"]) for r in records)
    log(f"  {len(records)} first-level records; medians {medians[0]} .. {medians[-1]}")
    return records


def bbox_share(unit: dict[str, Any], parent: dict[str, Any]) -> float | None:
    """The part of the parent's bounding box the unit's own box covers: a check
    on ``SAR_COVERAGE`` that the units files carry with them, so a polygon the
    table calls whole cannot be a speck in the box of the SAR it is under."""
    a, b = unit.get("bbox"), parent.get("bbox")
    if not a or not b:
        return None
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    area = (b[2] - b[0]) * (b[3] - b[1])
    return max(width, 0) * max(height, 0) / area if area > 0 else None


def sar_polygon(unit: dict[str, Any], parent: dict[str, Any], sar: dict[str, Any],
                name: str) -> dict[str, Any]:
    """A second-level polygon inside a SAR: the SAR's median age and sex ratio
    if it is the SAR drawn again, its reason if it is a fragment."""
    if unit["id"] not in SAR_COVERAGE:
        raise SystemExit(f"china_census: {unit['id']} ({unit['name']!r}) is drawn inside "
                         f"{name} and SAR_COVERAGE has not measured how much of it it covers")
    coverage, what = SAR_COVERAGE[unit["id"]]
    boxed = bbox_share(unit, parent)
    if coverage >= WHOLE and boxed is not None and boxed < 0.5:
        raise SystemExit(f"china_census: {unit['id']} is measured to cover {coverage:.0%} of "
                         f"{name} but its box covers {boxed:.0%} of the SAR's")
    common = dict(level="admin2", parent=f"CHN-{name}", country="CHN",
                  match_by="shape_id", shape_id=unit["id"],
                  religion=gap(NOT_COLLECTED, HK_RELIGION_NOTE if name == HK_NAME
                               else MO_RELIGION_NOTE))
    if coverage < WHOLE:
        return record(f"CHN-{unit['id']}", unit["name"], **common,
                      **{field: gap("not_available", what) for field in
                         ("population", "median_age", "sex_ratio", "ethnicity", "language")})
    return record(f"CHN-{unit['id']}", unit["name"], **common,
                  population=gap("not_available", SAR_COUNT_NOTE),
                  median_age=sar["median_age"],
                  median_age_note=f"{what} {sar['median_age_note']}",
                  sex_ratio=sar["sex_ratio"],
                  sex_ratio_note=f"{what} {sar['sex_ratio_note']}",
                  sources=sar["sources"])


def county_records(admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
                   provinces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A record for every second-level polygon: the reasons for the mainland's;
    inside a SAR, the SAR's median age and sex ratio for the polygon that is
    the SAR drawn again, and its reason for a fragment of one."""
    names = {u["id"]: u["name"] for u in admin1}
    first = {u["id"]: u for u in admin1}
    sars = {r["shape_id"]: r for r in provinces if r["name"] in (HK_NAME, MO_NAME)}
    if len(sars) != 2:
        raise SystemExit(f"china_census: {len(sars)} SAR records to draw on, not 2")
    out: list[dict[str, Any]] = []
    inside: list[dict[str, Any]] = []
    for unit in admin2:
        parent_shape = unit.get("parent")
        if parent_shape in sars:
            inside.append(sar_polygon(unit, first[parent_shape], sars[parent_shape],
                                      names[parent_shape]))
            out.append(inside[-1])
            continue
        parent = f"CHN-{names[parent_shape]}" if parent_shape in names else "CHN"
        out.append(record(
            f"CHN-{unit['id']}", unit["name"], level="admin2", parent=parent, country="CHN",
            match_by="shape_id", shape_id=unit["id"],
            population=gap("not_available", COUNTY_NOTE),
            median_age=gap("not_available", COUNTY_NOTE),
            sex_ratio=gap("not_available", COUNTY_NOTE),
            ethnicity=gap("not_available", COUNTY_NOTE),
            language=gap(LANGUAGE_STATUS, LANGUAGE_NOTE),
            religion=gap(NOT_COLLECTED, COUNTY_RELIGION_NOTE)))
    whole = [r["name"] for r in inside if "value" in (r.get("median_age") or {})]
    log(f"  {len(out)} second-level polygons: {len(out) - len(inside)} mainland ones with "
        f"their reasons; inside the SARs, {whole} with the SAR's own median age and sex ratio "
        f"and {len(inside) - len(whole)} fragment(s) with theirs")
    return out


def fetch_book(url: str) -> list[list[Any]]:
    import xlrd
    blob = http_get(url, binary=True, cache=False, retries=2, timeout=120)
    assert isinstance(blob, bytes)
    sheet = xlrd.open_workbook(file_contents=blob).sheet_by_index(0)
    return [sheet.row_values(i) for i in range(sheet.nrows)]


def fetch_hk() -> list[list[Any]]:
    import openpyxl
    blob = http_get(HK_URL, binary=True, timeout=300)
    assert isinstance(blob, bytes)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    return [list(r) for r in book["KeyStat1"].iter_rows(values_only=True)]


def fetch_mo() -> str:
    from pypdf import PdfReader
    blob = http_get(MO_URL, binary=True, timeout=300)
    assert isinstance(blob, bytes)
    reader = PdfReader(io.BytesIO(blob))
    return "\n".join((reader.pages[i].extract_text() or "") for i in range(min(20, len(reader.pages))))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log(f"china_census: {YEARBOOK}")
    tables = {t: fetch_book(BASE.format(table=t)) for t in SOURCES}
    admin1 = drawn("CHN", "admin1")
    records = build(tables, admin1, fetch_hk(), fetch_mo())
    write_json(PROCESSED / OUT, records)
    write_json(PROCESSED / OUT_COUNTY, county_records(admin1, drawn("CHN", "admin2"), records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
