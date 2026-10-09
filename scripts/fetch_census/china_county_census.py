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

1. the row is a county, autonomous county, banner or county-level city, never
   a district (a name ending 区), whose ground the cities have redrawn, and
   never a development zone (a GB/T 2260 code ending 71 to 80, or no code);
2. no development zone, scenic area or other special unit the yearbook counts
   apart stands on its polygon: the yearbooks count those apart from the
   counties whose ground they were cut from (Jilin's Changbai Mountain zones
   hold 61,146 people taken from Antu, Fusong and Changbai), so a county row
   beside one may be short of its ground. Each special unit of a prefecture is
   placed township by township (``china_zones``: its townships in the
   statistical division codes, each at its Wikidata point), and a polygon
   any of those townships stands in, or within about 3 km of, is refused. A
   prefecture with a special unit that cannot be placed -- not in the codes
   under its name, or a township of it without a point -- has every county
   refused, as all were before the zones could be placed. ``CUT_FROM`` names
   the prefectures a unit listed outside every prefecture was cut from;
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
Language is not asked by the census (``china_census.LANGUAGE_NOTE``). Where
a province's Table 1-5 cannot be read (Inner Mongolia's: the bureau refuses
the runner and the Internet Archive holds no capture of it), its counties
carry the other fields and a stated gap for the median age.

Usage:
    python -m scripts.fetch_census.china_county_census --fetch-names   # runner, once
    python -m scripts.fetch_census.china_county_census
    python -m scripts.fetch_census.china_county_census --only 15,37    # read, write nothing
    python -m scripts.fetch_census.china_county_census --add 15,37     # read these, keep the rest

``--add`` is for a runner whose time runs out before every province's
workbooks are read: the provinces named are read and written in place of
what the current output holds for them, and every other province's records
stay as the last run wrote them (a province that could not be read keeps
its old records too).
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
from collections import Counter
from typing import Any

from ._shared import PROCESSED, RAW, gap, http_get, log, measure, record, write_json
from .china_census import (LANGUAGE_NOTE, LANGUAGE_STATUS, compact, grouped, number, pooled,
                           read_a0101, read_a0104, read_a0105)
from .china_wiki import RESIDUAL
from .east_asia_common import drawn, hundred, sex_ratio, unshown

OUT = "china_county_census.json"
YEAR = 2020
NAMES = RAW / "wikidata_points" / "CHN_P442_zh.json"
SEATS = RAW / "wikidata_points" / "CHN_P442_seats.json"
SEAT_NAMES = RAW / "wikidata_points" / "CHN_P442_seat_names.json"
ZONE_GROUND = RAW / "wikidata_points" / "CHN_zone_ground.json"
CODE_SHAPES = PROCESSED / "code_shapes.json"
PROVINCE_FILE = PROCESSED / "china_census_province.json"
CDX = "https://web.archive.org/cdx/search/cdx"
REPLAY = "https://web.archive.org/web/{stamp}id_/{url}"
TABLES = {"A0101": "Table 1-1: households, population and sex ratio by area",
          "A0104": "Table 1-4: population by sex and nationality (民族), by area",
          "A0105": "Table 1-5: population by age and sex, by area"}
# Test 5. A county's 2020 count over the older figure its polygon carries,
# against the median of that ratio over the province's other comparable
# counties (the same year's figures): a universe the older figures share (a
# register's count rather than a census's) and the province's own growth or
# decline divide out, and what is left is the county's own departure. A
# province with fewer than PEERS comparable counties is held to the absolute
# band instead.
DRIFT = (0.8, 1.25)
DRIFT_FEW = (0.75, 1.33)
PEERS = 5
AGREE = 0.9                   # a lone seat's Chinese name against the polygon's label
PAUSE = 5                     # seconds between two requests to the Internet Archive
LICENCE = "Official statistics of the provincial bureau of statistics, cited as published"

# Polygons whose label misspells the one county whose seat they hold, beyond
# what AGREE accepts, each checked by hand: the label is that county's name
# (or the name it had when the polygon was drawn) with a letter or two wrong,
# or a misreading of one character, and no other county's. {code: (the
# label, why)}. A label below AGREE that is another place's name is here only
# where that place has a polygon of its own holding its own seat, so the
# label is a copy: Henan's polygon repeats Banma's. 和安县 is not here: its
# seat stands alone in "Hetianxian", but 和安 was cut from 和田县 in 2020, so
# the polygon is 和田县's old ground and not 和安's.
MISSPELT: dict[str, tuple[str, str]] = {
    "220382": ("Suanliaoxian", "双辽, Shuangliao, spelt 'Suanliao' by the boundary file"),
    "220621": ("Wushongxian", "抚松, Fusong, spelt 'Wushong' by the boundary file"),
    "370724": ("Linjuxian", "临朐, Linqu, spelt 'Linju' by the boundary file"),
    "371481": ("Leningshi", "乐陵, Leling, spelt 'Lening' by the boundary file"),
    "371623": ("Wulixian", "无棣, Wudi, spelt 'Wuli' by the boundary file"),
    "371726": ("Zhenchengxian", "鄄城, Juancheng, whose first character the boundary file "
                                "reads as 甄 (zhen)"),
    "371324": ("Changshangxian", "苍山, Cangshan, spelt 'Changshang' by the boundary file: the "
                                 "county has been called 兰陵 (Lanling) since 2014"),
    "632324": ("Banmaxian", "a copy of its neighbour Banma's: the boundary file draws Banma "
                            "(班玛县) as a polygon of its own holding Banma's seat, about 210 km "
                            "to the south-west, and this one holds the seat of 河南 (Henan) "
                            "alone"),
}

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
    "15": {"name": "Inner Mongolia Autonomous Region", "zh": "内蒙古",
           "base": "https://tj.nmg.gov.cn/files_pub/content/PAGEPACK/zk2020/html/",
           "bureau": "Inner Mongolia Autonomous Region Bureau of Statistics",
           "book": "内蒙古自治区2020年人口普查年鉴 (Inner Mongolia population census yearbook "
                   "2020)"},
    # Hebei's yearbook prints Table 1-1 by county and Tables 1-4 and 1-5 by
    # prefecture only, and under Shijiazhuang and Baoding a subtotal for the
    # city without Xinji and Dingzhou, which the province administers itself.
    "13": {"name": "Hebei Province", "zh": "河北",
           "base": "http://tjj.hebei.gov.cn/extra/col20/rkpc2020/zk/html/",
           "by_county": ("A0101",),
           "bureau": "Hebei Provincial Bureau of Statistics",
           "book": "河北省2020年人口普查年鉴 (Hebei population census yearbook 2020)"},
    # Shandong's workbooks sit under two paths: the Internet Archive holds
    # Tables 1-1 and 1-4 under pcmj/ and Table 1-5 under pcsj/.
    "37": {"name": "Shandong Province", "zh": "山东",
           "base": "http://tjj.shandong.gov.cn/pcmj/2020/zk/html/",
           "tables": {"A0105": "http://tjj.shandong.gov.cn/pcsj/2020/zk/html/"},
           "bureau": "Shandong Provincial Bureau of Statistics",
           "book": "山东省2020年人口普查年鉴 (Shandong population census yearbook 2020)"},
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
    "seat of today ({how}), {zones}, and {drift}")
NO_ZONE = "its prefecture lists no development zone counted apart"
ZONES_CLEAR = (
    "no special unit the yearbook counts apart stands on it: the {towns} townships of {names} "
    "({listing}), each placed at its Wikidata point, stand at least 3 km outside it")
NO_OLDER = ("the polygon carries no older figure to compare the count with, so a change of "
            "ground too small to move a seat would not show.")
DRIFT_NOTE = (
    "the count is {ratio:.2f} times the polygon's {year} figure ({source}), {relative:.2f} of "
    "the median ratio of the province's {peers} comparable counties ({median:.2f}), within the "
    "{low}-{high} this map accepts; a transfer of a township or two since the polygon was "
    "drawn would not show in such a test.")
DRIFT_FEW_NOTE = (
    "the count is {ratio:.2f} times the polygon's {year} figure ({source}), within the "
    "{low}-{high} this map accepts where too few counties can be compared; a transfer of a "
    "township or two since the polygon was drawn would not show in such a test.")
REFUSED_NOTE = {
    "zone": ("{book} counts {label} ({code}) in 2020, but its figures are not put on this "
             "polygon: its prefecture also lists {what}, which the yearbook counts apart from "
             "the counties whose ground they hold, and they cannot be placed ({why}), so this "
             "county's row may be short of the ground drawn here."),
    "held": ("{book} counts {label} ({code}) in 2020, but its figures are not put on this "
             "polygon: {what}, and the yearbook counts that unit apart from the counties whose "
             "ground it holds, so this county's row may be short of the ground drawn here."),
    "cut": ("{book} counts {label} ({code}) in 2020, but its figures are not put on this "
            "polygon: {what}, and the yearbook counts that zone apart, so the county's row is "
            "short of the ground drawn here."),
    "drift": ("{book} counts {label} ({code}) at {total:,} in 2020, but its figures are not put "
              "on this polygon: that is {what}, a departure no decade of migration explains, so "
              "the county's ground has likely changed since the polygon was drawn."),
}
AGE_NOTE = ("Interpolated within the age group (0, 1-4, then five-year groups to 95-99, and 100 "
            "and over) that holds the middle person, from Table 1-5 of the same yearbook, which "
            "prints no single years below the nation.")
AGE_UNREAD = ("{book} prints ages by county in Table 1-5, but that workbook could not be read: "
              "{why}. No median age is given for the county here.")
# A province whose Table 1-5 cannot be read is still read for its
# population, sex ratio and nationalities, which Tables 1-1 and 1-4 carry;
# its counties' median age is a stated gap. Table 1-1 is always required,
# and Table 1-4 wherever the yearbook prints it by county.
OPTIONAL = {"A0105"}
# A yearbook that prints only Table 1-1 by county (Hebei's: its Tables 1-4
# and 1-5 stop at the prefecture) gives its counties population and sex
# ratio, and says of the other two fields that the yearbook has no county
# figure. PREFECTURE_ONLY is that table's ``missing`` reason.
PREFECTURE_ONLY = "printed by prefecture only"
BY_PREFECTURE = ("{book} prints {what} (Table {table}) by prefecture only, not by county, and "
                 "no other table of its census yearbook gives the county's figure.")
# A subtotal a yearbook prints under a prefecture for the city without the
# county-level city the province administers directly (Hebei's "石家庄市①",
# Shijiazhuang without Xinji): the rows after it add up to the prefecture
# with that city, so the subtotal is left out of the area rows.
SUBTOTAL = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]$")


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def archived(url: str) -> str | None:
    query = urllib.parse.urlencode({"url": url, "output": "json", "filter": "statuscode:200",
                                    "fl": "timestamp", "limit": "-1"})
    rows = json.loads(http_get(f"{CDX}?{query}", cache=False, retries=5, timeout=90) or "[]")
    return rows[-1][0] if len(rows) > 1 else None


def unread(reason: str) -> str:
    """fetch_table's refusal as a clause for a note: who refused, in words."""
    parts = []
    if "HTTP Error 403" in reason:
        parts.append("the bureau's server refused it (HTTP 403)")
    elif "live:" in reason:
        parts.append("the bureau's server did not answer")
    if "no capture" in reason:
        parts.append("the Internet Archive holds no capture of it")
    elif "archive:" in reason or "nearest:" in reason:
        parts.append("the Internet Archive did not serve its capture")
    return " and ".join(parts) or "it could not be reached"


def fetch_table(base: str, table: str) -> tuple[list[list[Any]], str]:
    """A yearbook workbook's rows, and the address they were read from: the
    bureau's own file, or the Internet Archive's newest capture of it. When
    the Archive's index refuses, its replay is asked for the capture nearest
    to now, which it redirects to without consulting the index."""
    import xlrd
    url = f"{base}{table}.xls"
    tried = []
    for source in ("live", "archive", "nearest"):
        try:
            if source == "live":
                where = url
                # One try: a bureau that does not answer the runner in 45
                # seconds does not answer it at all (Inner Mongolia's server
                # let the handshake time out), and the runner has 45 minutes
                # for every province's workbooks.
                blob = http_get(url, binary=True, cache=True, retries=0, timeout=45)
            elif source == "archive":
                stamp = archived(url)
                if not stamp:
                    tried.append("no capture in the Internet Archive")
                    continue
                where = REPLAY.format(stamp=stamp, url=url)
                time.sleep(PAUSE)
                blob = http_get(where, binary=True, cache=True, retries=5, timeout=90)
            else:
                if any(t.startswith("no capture") for t in tried):
                    continue
                where = REPLAY.format(stamp=str(YEAR + 6), url=url)
                time.sleep(PAUSE)
                blob = http_get(where, binary=True, cache=True, retries=5, timeout=90)
            assert isinstance(blob, bytes)
            sheet = xlrd.open_workbook(file_contents=blob).sheet_by_index(0)
            return [sheet.row_values(i) for i in range(sheet.nrows)], where
        except Exception as exc:  # noqa: BLE001 - the next source is tried, then refused
            tried.append(f"{source}: {type(exc).__name__}: {str(exc)[:120]}")
    raise SystemExit(f"china_county_census: {url} could not be read ({'; '.join(tried)})")


NAME_QUERY = """
SELECT ?code ?zh WHERE {
  ?item wdt:P442 ?code ; wdt:P17 wd:Q148 .
  FILTER(REGEX(STR(?code), "^[0-9]{2}( ?[0-9]{2}){0,2}$"))
  FILTER NOT EXISTS { ?item wdt:P576 ?gone . }
  ?item rdfs:label ?zh . FILTER(LANG(?zh) IN ("zh", "zh-hans", "zh-cn"))
}
"""


def fetch_names() -> int:
    """{six-figure GB/T 2260 code: [its current Chinese names]}, from Wikidata.
    Wikidata writes a province's code in two figures ("63") and a prefecture's
    in four ("63 01"); both are padded to the six the yearbooks' codes use."""
    from fetch_wikidata import sparql, value  # noqa: PLC0415 (scripts/ is on the path)
    names: dict[str, set[str]] = {}
    for row in sparql(NAME_QUERY, cache=False, retries=2):
        code = re.sub(r"\s", "", value(row, "code") or "")
        code = code + "0" * (6 - len(code)) if len(code) in (2, 4) else code
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
        if SUBTOTAL.search(label):
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
    """The one current code under ``prefix`` whose Chinese name is ``name``,
    at the prefecture level or below it: exactly, or for a county failing that
    by its stem, so a county made a district since the census still meets its
    own row."""
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
    if exact or level == "prefecture":
        # A prefecture is named in full: by its stem alone, 通化县 would be
        # taken for 通化市.
        return None
    by_stem = candidates(lambda z: stem(z) == stem(name) and stem(name))
    return by_stem[0] if len(by_stem) == 1 else None


def kind_of(label: str, code: str | None) -> str:
    """'zone', 'district' or 'county' for a row below a prefecture. A
    development zone carries a code ending 71 to 80 where it carries one at
    all; a district's name ends 区 (a forest district 林区 and a special
    district 特区 are county-level, as counties are). An autonomous
    prefecture's county-level cities are numbered from 01 like a city's
    districts (Yanbian's Yanji is 222401), so the number alone cannot say."""
    if code is None or 71 <= int(code[4:]) <= 80:
        return "zone"
    if label.endswith("区") and not label.endswith(("林区", "特区")):
        return "district"
    return "county"


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
                kind = "special" if kind_of(labels[j], county) == "zone" else "county"
                out.append({"index": j, "label": labels[j], "kind": kind, "code": county,
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
                  names: dict[str, list[str]]
                  ) -> tuple[list[dict[str, Any]], dict, dict | None, dict | None]:
    """The areas, and the tables' figures keyed by row position. Table 1-5
    is None where it could not be read (``OPTIONAL``), and Tables 1-4 and
    1-5 where the yearbook prints them by prefecture only."""
    labels = labels_of(tables["A0101"])
    for table in ("A0104", "A0105"):
        if table in tables and labels_of(tables[table]) != labels:
            raise SystemExit(f"china_county_census: {code}: {table} lists other areas than 1-1")
    a0101 = read_a0101(tables["A0101"], area_rows)
    a0104 = read_a0104(tables["A0104"], area_rows) if "A0104" in tables else None
    a0105 = read_a0105(tables["A0105"], area_rows) if "A0105" in tables else None
    totals = [a0101[i]["total"] for i in range(len(labels))]
    areas = hierarchy(labels, totals, code, names)
    check(code, areas, a0101, a0104, a0105)
    return areas, a0101, a0104, a0105


def check(code: str, areas: list[dict[str, Any]], a0101: dict, a0104: dict | None,
          a0105: dict | None) -> None:
    where = PROVINCES.get(code, {}).get("name", code)
    for i, row in a0101.items():
        for what in ("total", "men", "women"):
            if any(table is not None and table[i][what] != row[what] for table in (a0104, a0105)):
                raise SystemExit(f"china_county_census: {where} row {i} {what}: the tables differ")
        if row["men"] + row["women"] != row["total"]:
            raise SystemExit(f"china_county_census: {where} row {i}: men and women miss the total")
        for name, table in (("1-4", a0104), ("1-5", a0105)):
            if table is not None and sum(table[i]["groups"].values()) != table[i]["total"]:
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

def lone_seats(seat_names: dict[str, dict[str, Any]]) -> dict[str, tuple[str, dict[str, Any]]]:
    """{code: (shape id, what china_seats --names measured)} for every polygon
    holding exactly one current county-level seat."""
    return {info["code"]: (shape, info) for shape, info in seat_names.items()}


def polygon_for(code: str, code_shapes: dict[str, Any],
                lone: dict[str, tuple[str, dict[str, Any]]]) -> tuple[str | None, str]:
    """(shape id, how it was found) for a county code, or (None, why not).

    First code_shapes: the code's Wikidata item stands inside the polygon and
    its English name agrees with the label. Failing that, a polygon in which
    the county's seat stands alone, when the label is the county's Chinese
    name in pinyin (agreement AGREE or better, every reading tried) or a
    misspelling of it checked by hand (MISSPELT). Test 4 still requires the
    polygon to hold that seat and no other."""
    entry = code_shapes.get(code)
    if entry:
        return entry["shape_id"], f"its Wikidata item stands in it and names it ({entry.get('name')})"
    if code not in lone:
        return None, "no polygon holds its seat alone or names it"
    shape, info = lone[code]
    if info["agreement"] >= AGREE:
        return shape, (f"its seat stands alone in it and the label {info['label']} is "
                       f"{info['zh']} in pinyin (agreement {info['agreement']:.2f})")
    if code in MISSPELT and MISSPELT[code][0] == info["label"]:
        return shape, f"its seat stands alone in it, and the label is {MISSPELT[code][1]}"
    return None, (f"its seat stands alone in {info['label']}, whose label is not {info['zh']} "
                  f"(agreement {info['agreement']:.2f})")


def zone_norm(name: str, province_zh: str) -> str:
    """A special unit's name as the yearbook and the statistical division
    codes both reduce to: without the province's name in front ("江苏无锡经济
    开发区"), without 市 ("常州市经济开发区"), and without spaces."""
    name = compact(name)
    for prefix in (f"{province_zh}省", f"{province_zh}自治区", province_zh):
        if province_zh and name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name.replace("市", "")


def zone_for(label: str, prefecture: str, province_zh: str,
             ground: dict[str, dict[str, Any]]) -> str | None:
    """The code of the one zone of the prefecture that the statistical
    division codes list under the yearbook's name for it: the same name, or
    failing that the one whose name holds the other's."""
    mine = {code: zone_norm(z.get("name", ""), province_zh) for code, z in ground.items()
            if code[:4] == prefecture[:4]}
    want = zone_norm(label, province_zh)
    exact = [c for c, n in mine.items() if n == want]
    if len(exact) == 1:
        return exact[0]
    if exact or not want:
        return None
    loose = [c for c, n in mine.items() if n and (n in want or want in n)]
    return loose[0] if len(loose) == 1 else None


def zone_places(code: str, areas: list[dict[str, Any]], ground: dict[str, dict[str, Any]]
                ) -> tuple[dict[str, str], dict[str, list[tuple[str, str]]], dict[str, Any]]:
    """Where the special units the yearbook counts apart stand.

    Returns (unplaced, held, placed): ``unplaced`` {prefecture code: why its
    special units cannot all be placed}; ``held`` {shape id: [(unit,
    township)]} for every polygon a placed township of a special unit stands
    in or within ``china_zones.NEAR`` of; ``placed`` {prefecture code: {"units":
    [labels], "towns": n, "listing": the codes' edition}} for the prefectures
    whose units are all placed."""
    zh = PROVINCES.get(code, {}).get("zh", "")
    special: dict[str, list[str]] = {}
    for a in areas:
        if a["kind"] == "special" and a["prefecture"]:
            special.setdefault(a["prefecture"], []).append(a["label"])
    unplaced: dict[str, str] = {}
    held: dict[str, list[tuple[str, str]]] = {}
    placed: dict[str, Any] = {}
    for pref, labels in special.items():
        problems, towns, listings = [], 0, set()
        for label in labels:
            zone_code = zone_for(label, pref, zh, ground)
            if zone_code is None:
                problems.append(f"{label} is not among the units the statistical division "
                                "codes list for the prefecture")
                continue
            zone = ground[zone_code]
            townships = zone.get("townships") or []
            missing = [t["name"] for t in townships if t.get("lon") is None]
            if zone.get("error") or not townships:
                problems.append(f"{label}'s townships could not be read")
            elif missing:
                one = len(missing) == 1
                problems.append(f"{len(missing)} of {label}'s {len(townships)} townships "
                                f"{'has' if one else 'have'} no point to place "
                                f"{'it' if one else 'them'} by ({'、'.join(missing[:4])})")
            for t in townships:
                for shape in {t.get("shape"), *(t.get("near") or [])} - {None}:
                    held.setdefault(shape, []).append((label, t["name"]))
            towns += len(townships)
            listings.add(zone.get("listing") or "the statistical division codes")
        if problems:
            unplaced[pref] = "; ".join(problems)
        else:
            placed[pref] = {"units": labels, "towns": towns, "listing": " and ".join(
                sorted(listings))}
    return unplaced, held, placed


def bind(code: str, areas: list[dict[str, Any]], a0101: dict, code_shapes: dict[str, Any],
         seats: dict[str, list[str]], units: dict[str, dict[str, Any]],
         lone: dict[str, tuple[str, dict[str, Any]]] | None = None,
         ground: dict[str, dict[str, Any]] | None = None,
         ) -> tuple[dict[int, str], Counter]:
    """{row position: shape id} for the county rows that pass all five tests,
    and why the others did not. Each county-level area carries its own
    outcome as ``why`` for the log; one refused although its polygon is known
    (tests 2 and 5) also carries ``refused`` (the shape and the reason), so
    the polygon can say why; one bound carries ``drift`` and ``zones`` for its
    note. ``ground`` is ``china_zones``' placement of the special units."""
    lone = lone or {}
    zoned: dict[str, list[str]] = {}
    for a in areas:
        if a["kind"] == "special" and a["prefecture"]:
            zoned.setdefault(a["prefecture"], []).append(a["label"])
    unplaced, held, placed = zone_places(code, areas, ground or {})
    cut: dict[str, str] = {}
    for area in areas:
        if area["kind"] == "special" and area["prefecture"] is None and area["head"] is None:
            if area["label"] not in CUT_FROM:
                raise SystemExit(f"china_county_census: {area['label']} is listed outside every "
                                 "prefecture and CUT_FROM does not say whose ground it holds")
            for p in CUT_FROM[area["label"]][0]:
                cut[f"{p}00"] = CUT_FROM[area["label"]][1]
    bound: dict[int, str] = {}
    why: Counter = Counter()
    used: set[str] = set()

    def refuse(area: dict[str, Any], reason: str, detail: str = "") -> None:
        why[reason] += 1
        area["why"] = f"{reason}{': ' + detail if detail else ''}"

    # Tests 1, 3 and 4: the row is a county, and a polygon is that county.
    candidates: list[tuple[dict[str, Any], str, str]] = []
    for area in areas:
        if area["kind"] not in ("county", "direct"):
            continue
        unit_code = area["code"]
        if kind_of(area["label"], unit_code) == "district":
            refuse(area, "a district")
            continue
        shape, how = polygon_for(unit_code, code_shapes, lone)
        if shape is None:
            refuse(area, "no polygon is this county", how)
            continue
        if seats.get(shape) != [unit_code]:
            refuse(area, "its polygon holds other seats",
                   f"{(units.get(shape) or {}).get('name')} holds {seats.get(shape)}")
            continue
        candidates.append((area, shape, how))

    # Test 5's yardstick: the median ratio of the comparable counties.
    def older_of(shape: str) -> dict[str, Any] | None:
        older = (units.get(shape) or {}).get("population") or {}
        if isinstance(older.get("value"), (int, float)) and older["value"] > 0 \
                and (older.get("year") or YEAR) < YEAR:
            return older
        return None
    years = Counter(o["year"] for _, s, _ in candidates if (o := older_of(s)))
    modal = years.most_common(1)[0][0] if years else None
    ratios = sorted(a0101[a["index"]]["total"] / o["value"] for a, s, _ in candidates
                    if (o := older_of(s)) and o["year"] == modal)
    median = ratios[len(ratios) // 2] if len(ratios) % 2 else (
        (ratios[len(ratios) // 2 - 1] + ratios[len(ratios) // 2]) / 2 if ratios else None)
    few = len(ratios) < PEERS

    for area, shape, how in candidates:
        unit_code = area["code"]
        pref = area["prefecture"] or unit_code[:4] + "00"
        if pref in zoned and pref in unplaced:
            refuse(area, "a zone in its prefecture", unplaced[pref])
            area["refused"] = (shape, "zone", (zoned[pref], unplaced[pref]))
            continue
        if shape in held:
            hits = held[shape]
            refuse(area, "a zone stands on its polygon",
                   "; ".join(f"{unit}: {town}" for unit, town in hits[:4]))
            area["refused"] = (shape, "held", hits)
            continue
        area["zones"] = placed.get(pref)
        if pref in cut:
            refuse(area, "a zone outside it cut from its prefecture")
            area["refused"] = (shape, "cut", cut[pref])
            continue
        total = a0101[area["index"]]["total"]
        older = older_of(shape)
        drift = None
        if older:
            ratio = total / older["value"]
            if few or older["year"] != modal or not median:
                low, high = DRIFT_FEW
                drift = {"ratio": ratio, "older": older, "relative": None, "band": DRIFT_FEW}
                ok = low <= ratio <= high
            else:
                relative = ratio / median
                drift = {"ratio": ratio, "older": older, "relative": relative,
                         "median": median, "peers": len(ratios), "band": DRIFT}
                ok = DRIFT[0] <= relative <= DRIFT[1]
            if not ok:
                refuse(area, "a jump from the polygon's older figure",
                       f"{total:,.0f} against {older['value']:,} ({older.get('year')}), "
                       f"ratio {ratio:.2f}" + (f", {drift['relative']:.2f} of the median "
                                               f"{median:.2f}" if drift["relative"] else ""))
                area["refused"] = (shape, "drift", drift)
                continue
        if shape in used:
            raise SystemExit(f"china_county_census: {shape} would be bound twice")
        used.add(shape)
        bound[area["index"]] = shape
        area["drift"] = drift
        area["how"] = how
        area["why"] = f"bound to {(units.get(shape) or {}).get('name')} ({shape})" + (
            f", ratio {drift['ratio']:.2f}" + (f" ({drift['relative']:.2f} of the median)"
                                               if drift["relative"] else "") if drift else "")
    return bound, why


def nationalities(a0104: dict[str, Any], book: str) -> dict[str, Any]:
    """The ethnicity fields from one area's Table 1-4 row."""
    counts, small, small_people = pooled(a0104["groups"])
    residual = int(a0104["groups"].get(RESIDUAL, 0))
    parts = []
    if residual:
        parts.append(f"the {residual:,} people whose nationality is not identified (未定族称) "
                     "and naturalised citizens (入籍)")
    if small:
        parts.append(f"the {small_people:,} people of the "
                     f"{'one nationality' if small == 1 else f'{small} nationalities'} too few "
                     "to show at one decimal")
    other = (" 'Other ethnic groups' is " + " and ".join(parts) + ".") if parts else ""
    left = unshown(counts)
    if left:
        # Only the residual can be too small to show once pool_small is done.
        other += (f" Together they are {left:,} people, too few to show at one decimal "
                  "themselves: they are counted in the base but not drawn.")
    return {"ethnicity": hundred(counts), "ethnicity_year": YEAR,
            "ethnicity_note": (f"2020 census, Table 1-4 of {book}: the 56 nationalities (民族) "
                               f"of all {int(a0104['total']):,} residents.{other}")}


def county_record(code: str, area: dict[str, Any], shape: str, unit: dict[str, Any],
                  parents: dict[str, str], a0101: dict, a0104: dict | None, a0105: dict | None,
                  urls: dict[str, str], ages_unread: str = "") -> dict[str, Any]:
    province = PROVINCES[code]
    book = f"{province['bureau']}, {province['book']}"
    i = area["index"]
    sources = [{"field": "population/sex_ratio", "name": f"{book}, {TABLES['A0101']}",
                "url": urls["A0101"], "year": YEAR, "license": LICENCE}]
    if a0104 is not None:
        sources.append({"field": "ethnicity", "name": f"{book}, {TABLES['A0104']}",
                        "url": urls["A0104"], "year": YEAR, "license": LICENCE})
        ethnicity = nationalities(a0104[i], book)
    else:
        ethnicity = {"ethnicity": gap("not_available", BY_PREFECTURE.format(
            book=book, what="nationality", table="1-4"))}
    if a0105 is not None:
        sources.append({"field": "median_age", "name": f"{book}, {TABLES['A0105']}",
                        "url": urls["A0105"], "year": YEAR, "license": LICENCE})
        ages: dict[str, Any] = {
            "median_age": measure(grouped(a0105[i]["groups"]), unit="years", year=YEAR,
                                  source=f"{book}, Table 1-5"),
            "median_age_note": AGE_NOTE}
    elif ages_unread == PREFECTURE_ONLY:
        ages = {"median_age": gap("not_available", BY_PREFECTURE.format(
            book=book, what="age", table="1-5"))}
    else:
        ages = {"median_age": gap("not_available", AGE_UNREAD.format(
            book=book, why=unread(ages_unread)))}
    drift = area.get("drift")
    if not drift:
        drift_text = NO_OLDER
    else:
        older = drift["older"]
        fields = {"ratio": drift["ratio"], "year": older.get("year"),
                  "source": older.get("source") or "of unstated source",
                  "low": drift["band"][0], "high": drift["band"][1]}
        drift_text = (DRIFT_NOTE.format(relative=drift["relative"], median=drift["median"],
                                        peers=drift["peers"], **fields)
                      if drift["relative"] else DRIFT_FEW_NOTE.format(**fields))
    zones = area.get("zones")
    zones_text = NO_ZONE if not zones else ZONES_CLEAR.format(
        towns=zones["towns"], names=", ".join(zones["units"]), listing=zones["listing"])
    return record(
        f"CHN-{shape}", unit["name"], level="admin2",
        parent=parents.get(unit.get("parent"), "CHN"), country="CHN",
        match_by="shape_id", shape_id=shape, aliases=[area["label"]],
        codes={"gb2260": area["code"]},
        population=measure(int(a0101[i]["total"]), year=YEAR, source=f"{book}, Table 1-1"),
        population_note=POPULATION_NOTE.format(book=book, how=area.get("how", ""),
                                               zones=zones_text, drift=drift_text),
        sex_ratio=sex_ratio(a0101[i]["men"], a0101[i]["women"], year=YEAR,
                            source=f"{book}, Table 1-1"),
        sex_ratio_note=f"{int(a0101[i]['men']):,} men and {int(a0101[i]['women']):,} women.",
        **ages, **ethnicity,
        language=gap(LANGUAGE_STATUS, LANGUAGE_NOTE),
        sources=sources)


def refused_record(code: str, area: dict[str, Any], unit: dict[str, Any],
                   parents: dict[str, str], a0101: dict) -> dict[str, Any]:
    """The reason a county the yearbook counts is not drawn on the polygon
    that is its own, on that polygon: a gap with a note, which displaces
    china_census_county's general one and no figure."""
    shape, kind, detail = area["refused"]
    province = PROVINCES[code]
    book = f"{province['bureau']}, {province['book']}"
    why = ""
    if kind == "zone":
        labels, why = detail
        what = "the special units " + ", ".join(labels)
    elif kind == "held":
        by_zone: dict[str, list[str]] = {}
        for zone, town in detail:
            by_zone.setdefault(zone, []).append(town)
        what = "; ".join(
            f"{zone}'s {'township' if len(towns) == 1 else 'townships'} {'、'.join(towns[:4])}"
            f"{' and others' if len(towns) > 4 else ''} "
            f"{'stands' if len(towns) == 1 else 'stand'} on it or within about 3 km of it"
            for zone, towns in by_zone.items())
    elif kind == "cut":
        what = detail
    else:
        what = (f"{detail['ratio']:.2f} times the polygon's {detail['older'].get('year')} "
                f"figure of {detail['older']['value']:,}"
                + (f", {detail['relative']:.2f} of the median ratio of the province's "
                   f"comparable counties" if detail["relative"] else ""))
    note = REFUSED_NOTE[kind].format(book=book, label=area["label"], code=area["code"],
                                     what=what, why=why,
                                     total=int(a0101[area["index"]]["total"]))
    reason = gap("not_available", note)
    return record(
        f"CHN-{shape}", unit["name"], level="admin2",
        parent=parents.get(unit.get("parent"), "CHN"), country="CHN",
        match_by="shape_id", shape_id=shape, aliases=[area["label"]],
        codes={"gb2260": area["code"]},
        population=reason, median_age=reason, sex_ratio=reason, ethnicity=reason)


def build(code: str, tables: dict[str, list[list[Any]]], names: dict[str, list[str]],
          code_shapes: dict[str, Any], seats: dict[str, list[str]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          national: float | None = None, urls: dict[str, str] | None = None,
          explain: bool = False,
          seat_names: dict[str, dict[str, Any]] | None = None,
          missing: dict[str, str] | None = None,
          ground: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The province's county records. ``missing`` is {table: why it could
    not be read} for an OPTIONAL table that was not; ``ground`` is where
    ``china_zones`` placed the special units' townships."""
    missing = missing or {}
    areas, a0101, a0104, a0105 = read_province(code, tables, names)
    where = PROVINCES[code]["name"]
    urls = urls or {t: f"{PROVINCES[code].get('tables', {}).get(t, PROVINCES[code]['base'])}{t}.xls"
                    for t in TABLES}
    if national is not None and a0101[0]["total"] != national:
        raise SystemExit(f"china_county_census: {where}'s yearbook counts {a0101[0]['total']:,.0f}"
                         f" and the National Bureau's {national:,.0f}")
    units = {u["id"]: u for u in admin2}
    parents = {u["id"]: f"CHN-{u['name']}" for u in admin1}
    bound, why = bind(code, areas, a0101, code_shapes, seats, units,
                      lone_seats(seat_names or {}), ground)
    out = [county_record(code, area, bound[area["index"]], units[bound[area["index"]]], parents,
                         a0101, a0104, a0105, urls, missing.get("A0105", ""))
           for area in areas if area["index"] in bound]
    out += [refused_record(code, area, units[area["refused"][0]], parents, a0101)
            for area in areas if area.get("refused")]
    if explain:
        for area in areas:
            log(f"    {area['kind']:10} {area['label']:24} {area['code'] or '-':6} "
                f"{area.get('why', '')}")
    kinds = Counter(a["kind"] for a in areas)
    refused = sum(1 for a in areas if a.get("refused"))
    log(f"  {where}: {kinds['prefecture']} prefectures, {kinds['county'] + kinds['direct']} "
        f"county-level areas, {kinds['special']} special; {len(bound)} bound; not bound: "
        f"{dict(why)}; {refused} polygons told why")
    return out


def merged(current: list[dict[str, Any]], records: list[dict[str, Any]],
           read: set[str]) -> list[dict[str, Any]]:
    """``records`` for the provinces read in this run, and the current
    output's records for every other province, in the order of PROVINCES."""
    def province(r: dict[str, Any]) -> str:
        return r["codes"]["gb2260"][:2]
    out = [r for r in current if province(r) not in read] + records
    order = list(PROVINCES)
    return sorted(out, key=lambda r: order.index(province(r)) if province(r) in order
                  else len(order))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch-names", action="store_true",
                    help="write the GB/T 2260 codes' Chinese names from Wikidata, and stop")
    ap.add_argument("--explain", action="store_true",
                    help="log every area of every province and what became of it")
    ap.add_argument("--only", help="province codes (15,37): read and log these, write nothing")
    ap.add_argument("--add", help="province codes (15,37): read these and keep the current "
                                  "output's records for the others")
    args = ap.parse_args()
    if args.fetch_names:
        return fetch_names()
    for path in (NAMES, SEATS, SEAT_NAMES, CODE_SHAPES):
        if not path.exists():
            raise SystemExit(f"china_county_census: {path} is missing")
    names = json.loads(NAMES.read_text(encoding="utf-8"))
    seats = json.loads(SEATS.read_text(encoding="utf-8"))
    seat_names = json.loads(SEAT_NAMES.read_text(encoding="utf-8"))
    code_shapes = json.loads(CODE_SHAPES.read_text(encoding="utf-8"))["CHN"]
    # Where china_zones placed the special units' townships; without it every
    # county in a prefecture listing one is refused, as before.
    ground = (json.loads(ZONE_GROUND.read_text(encoding="utf-8"))
              if ZONE_GROUND.exists() else {})
    nbs = {}
    if PROVINCE_FILE.exists():
        nbs = {r["name"]: r["population"]["value"]
               for r in json.loads(PROVINCE_FILE.read_text(encoding="utf-8"))
               if isinstance(r.get("population"), dict) and "value" in r["population"]}
    admin1, admin2 = drawn("CHN", "admin1"), drawn("CHN", "admin2")
    records: list[dict[str, Any]] = []
    only = set(args.only.split(",")) if args.only else None
    add = set(args.add.split(",")) if args.add else None
    for chosen in (only, add):
        if chosen and chosen - set(PROVINCES):
            raise SystemExit("china_county_census: no yearbook is known for "
                             f"{sorted(chosen - set(PROVINCES))}")
    read: set[str] = set()
    for code, province in PROVINCES.items():
        if (only and code not in only) or (add and code not in add):
            continue
        log(f"china_county_census: {province['bureau']}, {province['book']}")
        tables, urls, missing = {}, {}, {}
        try:
            for table in TABLES:
                if table not in province.get("by_county", TABLES):
                    missing[table] = PREFECTURE_ONLY
                    continue
                base = province.get("tables", {}).get(table, province["base"])
                try:
                    tables[table], urls[table] = fetch_table(base, table)
                except SystemExit as exc:
                    if table not in OPTIONAL:
                        raise
                    missing[table] = str(exc)
                    log(f"  {province['name']}: {TABLES[table]} not read, its counties' median "
                        f"age is left out: {exc}")
        except SystemExit as exc:
            # The bureau refusing and the Archive busy is a gap for this run,
            # not a fault in the figures: its counties keep china_census's
            # reasons, and the log says why.
            log(f"  {province['name']} skipped: {exc}")
            continue
        records += build(code, tables, names, code_shapes, seats, admin1, admin2,
                         nbs.get(province["name"]), urls, args.explain, seat_names, missing,
                         ground)
        read.add(code)
    if only:
        log(f"  --only: {len(records)} records read, nothing written")
        return 0
    if add:
        current = (json.loads((PROCESSED / OUT).read_text(encoding="utf-8"))
                   if (PROCESSED / OUT).exists() else [])
        kept = len(merged(current, [], read))
        records = merged(current, records, read)
        log(f"  --add: {len(records) - kept} records read for {sorted(read)}; {kept} kept from "
            f"the current {OUT}")
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} county records to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
