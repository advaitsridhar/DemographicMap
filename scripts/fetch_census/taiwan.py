#!/usr/bin/env python3
"""Taiwan: 22 counties and cities resolved from official sources, by the owner's decision.

Taiwan's census asks the language used at home and nothing about ethnicity
or religion, and for as long as this map read censuses only, its 22
first-level units carried nothing at all -- 23.6 million people, the
largest wholly blank country on the map. On 19 September 2026 the map's
owner decided that Taiwan, like Japan, should carry what official and
secondary sources can say, each figure labelled for what it is: a count as
a composition, everything else as a ``modelled`` estimate that no reader
can mistake for a census figure. This module is that decision, in three
parts that are three different kinds of thing.

**Language is read.** The 2020 Population and Housing Census (109年人口及住宅
普查) asked every resident their main and secondary language, and the
DGBAS's results release of 30 November 2022 prints Table 2-5, 6歲以上本國籍
常住人口使用語言情形, by county and city: the *main* language currently
used (目前主要使用語言) as a single-answer composition -- Mandarin, Taiwanese
Hokkien, Hakka, indigenous languages, other -- of the resident population
of ROC nationality aged 6 and over. That is the newer of the two censuses
that asked (the 2010 census published a multiple-response table, which
cannot be a composition), and it is written as a list, with
``language_basis`` saying whose main language it is. The reader rebuilds
the national row from the 22 counties weighted by their printed base
populations and refuses the table if they disagree by more than half a
point.

**Ethnicity is modelled from official counts.** No Taiwanese census asks
ethnicity. Two official figures exist by county and one national survey
ratio, and they are composed under a stated assumption:

1. *Indigenous*: the Council of Indigenous Peoples' monthly count of
   registered indigenous people by county (台閩縣市原住民族人口-按性別族別),
   which is the household register's count of people holding indigenous
   status, against the Ministry of the Interior's registered population of
   the same month. A real count, on the register's definition.
2. *Hakka*: the Hakka Affairs Council's 110年全國客家人口暨語言基礎資料調查
   (2021), which estimates the share of each county's registered
   population meeting the Hakka Basic Act's definition (Hakka descent or
   connection, and self-identification as Hakka) from 63,111 telephone
   interviews. A survey share.
3. *The rest* is split between Hoklo and mainlander (waishengren) in the
   same survey's national single-identification ratio (福老人 71.3 : 大陸各省
   市人 5.0), applied to every county alike. That split is uniform and
   therefore an assumption: it says nothing about where mainlanders
   actually settled, and it is the reason every record is ``modelled`` and
   not a list even though two of its four parts are official figures.

**Religion is modelled.** No census or register counts religious
affiliation by county. The national prior is Pew Research Center's 2023
survey of Taiwanese adults (Buddhist 28%, Daoist 24%, Christian 7%, other
12%, no religion 27%, don't know 2%). The county signal is the Ministry of
the Interior's registry of religious buildings from the 內政統計年報 (table
06-01, 宗教教務概況): registered temples and churches by county. The
yearbook splits temples by tradition (道教, 佛教, 一貫道 ...) only
nationally, and the registry that would do it by county
(religion.moi.gov.tw) answers nothing, so the signal is two-way: churches
tilt Christianity, temples tilt Buddhism, Taoism and the other traditions
together. It is used only *relatively*: a county's church (temple) share
of its registered buildings over the nation's, clipped to a threefold
ratio, scales the survey's share; the affiliated shares are rescaled to the
survey's affiliated total and "no religion" is held at the national figure,
because nothing gives it by county. Absolute bounds stop the signal's
artefacts passing through -- a city with few temples for its size has a
high church share whether or not it has many Christians. **No backtest is
possible** -- no county-level self-identification figure exists to score
against -- so the estimate carries no ``backtest`` key and says so.

Every per-unit note is short, by the owner's instruction: what the figure
is and where from, then the caveat. The method is written out here and in
``docs/SOURCES.md`` ("Taiwan, resolved by the owner's decision"), not on
every row.

Usage:
    python -m scripts.fetch_census.taiwan
    python -m scripts.fetch_census.taiwan --language-text dump.txt --hakka-text dump.txt \\
        --indigenous-xls file.xls --population-xls file.xls --buildings-xls file.xls
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, measure, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import MODELLED, estimate, http_get, slugify  # noqa: E402
from probe_pdf import PAGE_BREAK, fetch_text  # noqa: E402

OUT = "taiwan_county.json"
ISO3 = "TWN"
DECISION = "19 September 2026"

# ---------------------------------------------------------------------------
# The 22 units: the official name, the boundary file's name, and the other
# names a source or a reader may use (the pre-2010 counties that merged into
# the special municipalities, and the "City"/"County" forms the shapes drop).
# ---------------------------------------------------------------------------
COUNTIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "新北市": ("New Taipei", ("New Taipei City", "Taipei County")),
    "臺北市": ("Taipei", ("Taipei City",)),
    "桃園市": ("Taoyuan", ("Taoyuan City", "Taoyuan County")),
    "臺中市": ("Taichung", ("Taichung City", "Taichung County")),
    "臺南市": ("Tainan", ("Tainan City", "Tainan County")),
    "高雄市": ("Kaohsiung", ("Kaohsiung City", "Kaohsiung County")),
    "基隆市": ("Keelung", ("Keelung City",)),
    "新竹市": ("Hsinchu", ("Hsinchu City",)),
    "嘉義市": ("Chiayi", ("Chiayi City",)),
    "宜蘭縣": ("Yilan County", ("Yilan",)),
    "新竹縣": ("Hsinchu County", ()),
    "苗栗縣": ("Miaoli County", ("Miaoli",)),
    "彰化縣": ("Changhua County", ("Changhua",)),
    "南投縣": ("Nantou County", ("Nantou",)),
    "雲林縣": ("Yunlin County", ("Yunlin",)),
    "嘉義縣": ("Chiayi County", ()),
    "屏東縣": ("Pingtung County", ("Pingtung",)),
    "臺東縣": ("Taitung County", ("Taitung",)),
    "花蓮縣": ("Hualien County", ("Hualien",)),
    "澎湖縣": ("Penghu", ("Penghu County",)),
    "金門縣": ("Kinmen", ("Kinmen County",)),
    "連江縣": ("Matsu Islands", ("Lienchiang County", "Lienchiang", "Matsu")),
}
NATIONAL = "總計"


def official(name: str) -> str:
    """A county name as the sources print it: 台 read as 臺, footnote marks dropped."""
    return name.replace("台", "臺").rstrip("*※ ").strip()


# ---------------------------------------------------------------------------
# Language: the 2020 census, Table 2-5 of the DGBAS results release.
# ---------------------------------------------------------------------------
LANGUAGE_YEAR = 2020
LANGUAGE_URL = ("https://ws.dgbas.gov.tw/Download.ashx?u=LzAwMS9VcGxvYWQvNDYzL3JlbGZpbGUvMTA5ODAv"
                "MjMwMTYyL2M5NWE5ZWU5LWI1OTEtNGNkMS04YzAwLTI3NTkyYjJhOGRlNC5wZGY%3d&n=MTA55bm05Lq6"
                "5Y%2bj5Y%2bK5L2P5a6F5pmu5p%2bl57i95aCx5ZGK57Wx6KiI57WQ5p6cLeaWsOiBnueovy5wZGY%3d")
LANGUAGE_PAGE_URL = "https://www.dgbas.gov.tw/News_Content.aspx?n=3602&s=230162"
LANGUAGE_SOURCE = ("DGBAS, 109年人口及住宅普查總報告統計結果 (2020 Population and Housing Census, "
                   "final results release, 30 November 2022), Table 2-5: main language "
                   "currently used, resident population of ROC nationality aged 6 and over, "
                   "by county and city")
LANGUAGE_LICENCE = "Open Government Data License, Taiwan (version 1.0)"
LANGUAGE_BASIS = ("main language currently used (目前主要使用語言), resident population of ROC "
                  "nationality aged 6 and over")
# The five main-language columns, in the table's order, in the map's words.
LANGUAGE_COLUMNS = ("Mandarin", "Taiwanese Hokkien", "Hakka",
                    "Taiwanese indigenous languages", "Other languages")
LANGUAGE_MARKS = ("表 2-5", "目前主要使用語言", "6 歲以上本國籍常住人口")
LANGUAGE_ROW_TOLERANCE = 0.3     # points, a printed row against 100
LANGUAGE_NATIONAL_TOLERANCE = 0.5  # points, the national row rebuilt from the counties
NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")


def language_page(text: str) -> str:
    for page in text.split(PAGE_BREAK):
        flat = re.sub(r"\s+", "", page)
        if all(re.sub(r"\s+", "", m) in flat for m in LANGUAGE_MARKS):
            return page
    raise SystemExit("taiwan: no page of the census release carries Table 2-5 (language)")


def read_language(text: str) -> dict[str, dict[str, Any]]:
    """{official name: {"base": persons aged 6+, "main": {language: pct}}} for the
    22 counties and the 總計 row, checked against each other."""
    out: dict[str, dict[str, Any]] = {}
    for line in language_page(text).splitlines():
        tokens = line.split()
        if not tokens:
            continue
        name = official(tokens[0])
        if name not in COUNTIES and name != NATIONAL:
            continue
        try:
            at = tokens.index("100.0")
        except ValueError:
            continue
        digits = "".join(tokens[1:at])
        cells = tokens[at + 1:at + 6]
        if not digits.isdigit() or len(cells) < 5 or not all(NUMBER.match(c) for c in cells):
            raise SystemExit(f"taiwan: language row for {name} is not five shares after a base")
        main = dict(zip(LANGUAGE_COLUMNS, (float(c) for c in cells)))
        total = sum(main.values())
        if abs(total - 100.0) > LANGUAGE_ROW_TOLERANCE:
            raise SystemExit(f"taiwan: {name}: main-language shares sum to {total:.1f}")
        out[name] = {"base": int(digits), "main": main}
    missing = [c for c in COUNTIES if c not in out]
    if missing or NATIONAL not in out:
        raise SystemExit(f"taiwan: Table 2-5 lacks rows for {missing or [NATIONAL]}")
    # The national row rebuilt from the counties, weighted by their base.
    base = sum(out[c]["base"] for c in COUNTIES)
    if base != out[NATIONAL]["base"]:
        raise SystemExit(f"taiwan: the 22 counties' base populations sum to {base:,} against "
                         f"the table's own {out[NATIONAL]['base']:,}")
    worst = 0.0
    for language in LANGUAGE_COLUMNS:
        rebuilt = sum(out[c]["main"][language] * out[c]["base"] for c in COUNTIES) / base
        worst = max(worst, abs(rebuilt - out[NATIONAL]["main"][language]))
    if worst > LANGUAGE_NATIONAL_TOLERANCE:
        raise SystemExit(f"taiwan: the national language row rebuilt from the counties is "
                         f"{worst:.2f} points from the printed one")
    log(f"  language: 22 counties read; national row rebuilt from them within {worst:.2f} "
        f"points (Mandarin {out[NATIONAL]['main']['Mandarin']:.1f}, Hokkien "
        f"{out[NATIONAL]['main']['Taiwanese Hokkien']:.1f}, Hakka "
        f"{out[NATIONAL]['main']['Hakka']:.1f})")
    return out


# ---------------------------------------------------------------------------
# Hakka: the Hakka Affairs Council's 2021 survey report.
# ---------------------------------------------------------------------------
HAKKA_YEAR = 2021
HAKKA_URL = "https://www.hakka.gov.tw/File/Attach/37585/File_96737.pdf"
HAKKA_SOURCE = ("Hakka Affairs Council, 110年全國客家人口暨語言基礎資料調查研究 (2021 National "
                "Survey of Hakka Population and Language, report of May 2022): share of each "
                "county's registered population meeting the Hakka Basic Act definition "
                "(Figure 8), and the national single self-identification of ethnic group "
                "(Table 4-1); 63,111 telephone interviews, 15 March to 6 November 2021, "
                "weighted to the December 2020 register")
HAKKA_LICENCE = "Hakka Affairs Council report, cited for research with attribution"
HAKKA_COUNTY_MARKS = ("客家基本法定義之客家人", "推估設籍", "縣市別")
HAKKA_NATIONAL_MARKS = ("表4-1", "單一自我認定", "臺閩地區")
# Table 4-1's rows, in the report's words, and the map's.
IDENTITY_ROWS: dict[str, str] = {
    "客家人": "Hakka", "福老人": "Hoklo Taiwanese", "大陸各省市人": "Mainland Chinese (waishengren)",
    "原住民": "Taiwanese indigenous peoples", "臺灣人": "Taiwanese only",
    "其他族群": "Other", "不知道/拒答": "Don't know or refused",
}
HAKKA_COUNT_TOLERANCE = 0.002    # relative, the counties' Hakka counts against the total


def page_with(text: str, marks: tuple[str, ...], what: str) -> str:
    for page in text.split(PAGE_BREAK):
        flat = re.sub(r"\s+", "", page)
        if all(re.sub(r"\s+", "", m) in flat for m in marks):
            return page
    raise SystemExit(f"taiwan: no page of the Hakka report carries {what}")


def numbers(tokens: list[str]) -> list[float]:
    out = []
    for tok in tokens:
        clean = tok.replace(",", "")
        if NUMBER.match(clean):
            out.append(float(clean))
        elif clean in ("-", "－"):
            out.append(float("nan"))
        else:
            break
    return out


def read_hakka(text: str) -> dict[str, dict[str, Any]]:
    """{official name: {"population": Dec-2020 registered, "pct": 2021 Hakka share,
    "hakka": estimated Hakka people}} plus the 總計 row, checked."""
    out: dict[str, dict[str, Any]] = {}
    for line in page_with(text, HAKKA_COUNTY_MARKS, "the county table (Figure 8)").splitlines():
        tokens = line.split()
        if not tokens:
            continue
        name = official(tokens[0])
        if name not in COUNTIES and name != NATIONAL:
            continue
        values = numbers(tokens[1:])
        # 2016 population, 2016 share, 2016 count, 2020 population, 2021 share,
        # 2021 count, then the two growth rates (dashes for the islands).
        if len(values) < 7:
            raise SystemExit(f"taiwan: Hakka row for {name} has {len(values)} figures, not 8")
        out[name] = {"population": int(values[3]), "pct": values[4], "hakka": int(values[5])}
    missing = [c for c in COUNTIES if c not in out]
    if missing or NATIONAL not in out:
        raise SystemExit(f"taiwan: the Hakka county table lacks {missing or [NATIONAL]}")
    population = sum(out[c]["population"] for c in COUNTIES)
    if population != out[NATIONAL]["population"]:
        raise SystemExit(f"taiwan: the counties' registered populations sum to {population:,} "
                         f"against the report's {out[NATIONAL]['population']:,}")
    hakka = sum(out[c]["hakka"] for c in COUNTIES)
    drift = abs(hakka - out[NATIONAL]["hakka"]) / out[NATIONAL]["hakka"]
    if drift > HAKKA_COUNT_TOLERANCE:
        raise SystemExit(f"taiwan: the counties' Hakka counts sum to {hakka:,} against the "
                         f"report's {out[NATIONAL]['hakka']:,}")
    for c in COUNTIES:
        implied = out[c]["hakka"] / out[c]["population"] * 100
        if abs(implied - out[c]["pct"]) > 0.05:
            raise SystemExit(f"taiwan: {c}: Hakka count over population is {implied:.2f}, "
                             f"printed {out[c]['pct']}")
    log(f"  hakka: 22 counties read; {out[NATIONAL]['hakka']:,} of "
        f"{out[NATIONAL]['population']:,} ({out[NATIONAL]['pct']}%) nationally")
    return out


def read_identity(text: str) -> dict[str, float]:
    """The 2021 single self-identification shares from Table 4-1, in the map's words."""
    out: dict[str, float] = {}
    for line in page_with(text, HAKKA_NATIONAL_MARKS, "Table 4-1 (self-identification)").splitlines():
        tokens = line.split()
        if not tokens or tokens[0] not in IDENTITY_ROWS:
            continue
        values = numbers(tokens[1:])
        # Four rounds, each a share and a count in ten-thousands, then the change:
        # the 2021 share is the seventh figure.
        if len(values) < 8:
            continue
        out[IDENTITY_ROWS[tokens[0]]] = values[6]
    lacking = [v for v in IDENTITY_ROWS.values() if v not in out]
    if lacking:
        raise SystemExit(f"taiwan: Table 4-1 lacks rows for {lacking}")
    total = sum(out.values())
    if abs(total - 100.0) > 0.3:
        raise SystemExit(f"taiwan: the 2021 self-identification shares sum to {total:.1f}")
    log("  identity (2021, single answer): " + ", ".join(f"{k} {v}" for k, v in out.items()))
    return out


# ---------------------------------------------------------------------------
# The register: the Ministry of the Interior's monthly bulletin, two tables
# from the same month -- 1.1 (households and registered population by
# county) and 1.4 (registered indigenous persons by county). Each workbook
# has one sheet per year, the latest carrying the latest month, and the
# sheet's second row says which month.
# ---------------------------------------------------------------------------
# The Ministry's statistics site lists its tables from a script; each is a
# static file under micst/report/, named by the report type (32 monthly, 33
# yearly) and id, which is what the menu's linkreprot() opens.
MOI_REPORTS = "https://statis.moi.gov.tw/micst/report/"
POPULATION_PAGE_URL = "https://statis.moi.gov.tw/micst/webMain.aspx?k=menum"
INDIGENOUS_PAGE_URL = POPULATION_PAGE_URL
POPULATION_URL = MOI_REPORTS + "321010.xlsx"      # 1.1-土地面積、村里鄰、戶數暨現住人口數
INDIGENOUS_URL = MOI_REPORTS + "321040.xlsx"      # 1.4-現住原住民人口數
MOI_LICENCE = "Open Government Data License, Taiwan (version 1.0)"
POPULATION_SOURCE = ("Ministry of the Interior, 內政統計月報 (monthly bulletin), table 1.1 "
                     "土地面積、村里鄰、戶數暨現住人口: registered population by county and city")
INDIGENOUS_SOURCE = ("Ministry of the Interior, 內政統計月報 (monthly bulletin), table 1.4 "
                     "現住原住民人數: registered indigenous persons by county and city")
ROC_MONTH = re.compile(r"中華民國\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月")
CHINESE = re.compile(r"[一-鿿]+")


def county_of(cell: Any) -> str:
    """'新 北 市 New Taipei City' -> '新北市'; '總計 Total' -> '總計'."""
    return official("".join(CHINESE.findall(str(cell))))


Grid = list[list[str]]
XML_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
XML_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
XML_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def column_index(ref: str) -> int:
    """'A' -> 0, 'AB' -> 27, from a cell reference like 'AB12'."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def xlsx_grids(blob: bytes) -> dict[str, Grid]:
    """Every sheet of an .xlsx as rows of text, read from the package itself.

    statis.moi.gov.tw writes its workbooks with a style attribute ('xxid')
    that openpyxl refuses, so the sheets are read straight from the zip: the
    shared strings, the workbook's sheet list, and each sheet's cells.
    """
    import xml.etree.ElementTree as ET
    import zipfile
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = set(z.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{XML_MAIN}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{XML_MAIN}t")))
        rels = {rel.get("Id"): rel.get("Target")
                for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).iter(
                    f"{XML_PKG}Relationship")}
        out: dict[str, Grid] = {}
        for sheet in ET.fromstring(z.read("xl/workbook.xml")).iter(f"{XML_MAIN}sheet"):
            target = rels[sheet.get(f"{XML_REL}id")]
            if target.startswith("/"):
                path = target.lstrip("/")
            elif target.startswith("xl/"):
                path = target
            else:
                path = "xl/" + target
            grid: Grid = []
            for row in ET.fromstring(z.read(path)).iter(f"{XML_MAIN}row"):
                cells: list[str] = []
                for c in row.iter(f"{XML_MAIN}c"):
                    at = column_index(c.get("r", ""))
                    kind = c.get("t")
                    v = c.find(f"{XML_MAIN}v")
                    if kind == "s" and v is not None and v.text is not None:
                        text = shared[int(v.text)]
                    elif kind == "inlineStr":
                        text = "".join(t.text or "" for t in c.iter(f"{XML_MAIN}t"))
                    else:
                        text = v.text if v is not None and v.text is not None else ""
                    while len(cells) <= at:
                        cells.append("")
                    cells[at] = text.strip()
                grid.append(cells)
            out[sheet.get("name", "")] = grid
        return out


def xls_grids(blob: bytes) -> dict[str, Grid]:
    import xlrd
    book = xlrd.open_workbook(file_contents=blob)
    return {s.name: [[str(s.cell_value(r, c)).strip() for c in range(s.ncols)]
                     for r in range(s.nrows)] for s in book.sheets()}


def grids_of(blob: bytes) -> dict[str, Grid]:
    """A workbook's sheets as text grids, whichever format it is in."""
    return xlsx_grids(blob) if blob[:2] == b"PK" else xls_grids(blob)


MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
                                      "sep", "oct", "nov", "dec"), 1)}
SHEET_YEAR = re.compile(r"^\s*(\d{4})\s*$")
SHEET_MONTH = re.compile(r"^\s*([A-Za-z]{3})[A-Za-z]*\.?,?\s*(\d{4})\s*$")


def sheet_date(name: str) -> tuple[int, int] | None:
    """' 2025' -> (2025, 12); ' Aug., 2026' -> (2026, 8); anything else None.

    The monthly bulletin's workbooks carry one sheet per year of December
    figures and one for the latest month, named that way; 'monthly' is the
    national series and is never a sheet of counties.
    """
    found = SHEET_YEAR.match(name)
    if found:
        return int(found.group(1)), 12
    found = SHEET_MONTH.match(name)
    if found and found.group(1).lower() in MONTHS:
        return int(found.group(2)), MONTHS[found.group(1).lower()]
    return None


def latest_sheet(grids: dict[str, Grid], select: re.Pattern[str] | None = None
                 ) -> tuple[str, Grid, tuple[int, int]]:
    """The sheet for the latest month or year among those named for one, with
    that date. ``select`` narrows the names to a pattern whose first group is
    the year (the yearbook names its county sheets '2025(區域別)')."""
    dated: dict[str, tuple[int, int]] = {}
    for name in grids:
        if select is not None:
            found = select.match(name)
            if found:
                dated[name] = (int(found.group(1)), 12)
        else:
            when = sheet_date(name)
            if when:
                dated[name] = when
    if not dated:
        raise SystemExit(f"taiwan: the MOI workbook has no sheet named for a month or year "
                         f"among {list(grids)}")
    name = max(dated, key=lambda n: dated[n])
    return name, grids[name], dated[name]


def sheet_month(grid: Grid, name: str) -> tuple[int, int]:
    """(year, month) the sheet's heading says it is the end of, Gregorian."""
    for row in grid[:8]:
        for cell in row[:6]:
            found = ROC_MONTH.search(cell)
            if found:
                return int(found.group(1)) + 1911, int(found.group(2))
    raise SystemExit(f"taiwan: sheet {name!r} does not say which month it is")


CJK = re.compile(r"[一-鿿]")
ROC_YEAR_ROW = re.compile(r"^[一二三四五六七八九○〇零\d]+\s*年")


def area_of(row: list[str]) -> str:
    """The county a row is for: its Chinese name sits in the first cell, or in
    the second when the first is blank (table 1.4) or English (the yearbook)."""
    return county_of(" ".join(row[:2]))


def heads_and_body(grid: Grid, what: str) -> tuple[list[list[str]], list[list[str]]]:
    """The header rows (from the one naming 區域別 to the first row of figures)
    and the rows after them.

    The bulletin's headers span one to three rows: the population table puts
    區域別 and 人口數 on one line, the indigenous table puts 原住民人數 above
    合計 above Total, the yearbook 年底及區域別 above 合計/寺廟/教(會)堂.
    """
    top = next((i for i, row in enumerate(grid[:12]) if any("區域別" in cell for cell in row)),
               None)
    if top is None:
        raise SystemExit(f"taiwan: the {what} sheet has no header row naming 區域別")
    end = next((i for i in range(top + 1, len(grid))
                if area_of(grid[i]) in COUNTIES or area_of(grid[i]) == NATIONAL
                or ROC_YEAR_ROW.match(grid[i][0] if grid[i] else "")), len(grid))
    return grid[top:end], grid[end:]


def column_headed(heads: list[list[str]], mark: str, what: str) -> int:
    """The first column with a header cell that is ``mark``, or ``mark``
    followed by something other than a Chinese character (an English
    rendering, a newline, a parenthesis): 人口數 and not 男性人口數, 寺廟 and
    not 寺廟教(會)堂數."""
    width = max(len(row) for row in heads)
    for col in range(width):
        for row in heads:
            cell = re.sub(r"\s+", "", row[col]) if col < len(row) else ""
            if cell == mark or (cell.startswith(mark) and not CJK.match(cell[len(mark)])):
                return col
    raise SystemExit(f"taiwan: the {what} sheet has no column headed {mark!r}")


def read_columns(grid: Grid, columns: dict[str, str], what: str, *,
                 year_row_is_national: bool = False) -> dict[str, dict[str, int]]:
    """{official name: {key: figure}} for the 22 counties and 總計, each key
    the first column headed as ``columns`` says, the counties checked to sum
    to the total. The yearbook writes its national row against the year
    ('一一四年 2025') rather than 總計."""
    heads, body = heads_and_body(grid, what)
    cols = {key: column_headed(heads, mark, what) for key, mark in columns.items()}
    out: dict[str, dict[str, int]] = {}
    for row in body:
        if not row:
            continue
        area = area_of(row)
        if year_row_is_national and ROC_YEAR_ROW.match(row[0]):
            area = NATIONAL
        if (area in COUNTIES or area == NATIONAL) and area not in out:
            figures: dict[str, int] = {}
            for key, col in cols.items():
                try:
                    figures[key] = int(float(row[col].replace(",", "")))
                except (IndexError, ValueError):
                    raise SystemExit(f"taiwan: {what}: {area} has no figure under "
                                     f"{columns[key]!r}")
            out[area] = figures
    missing = [c for c in COUNTIES if c not in out]
    if missing or NATIONAL not in out:
        raise SystemExit(f"taiwan: the {what} sheet lacks {missing or [NATIONAL]}")
    for key in columns:
        summed = sum(out[c][key] for c in COUNTIES)
        if summed != out[NATIONAL][key]:
            raise SystemExit(f"taiwan: {what}: {columns[key]} sums to {summed:,} over the "
                             f"counties against the sheet's own {out[NATIONAL][key]:,}")
    return out


def read_by_county(blob: bytes, column: str, what: str) -> tuple[dict[str, int], tuple[int, int]]:
    """{official name: value in the first column headed ``column``} for the 22
    counties and 總計 from the latest sheet, and the month it is for."""
    name, grid, _ = latest_sheet(grids_of(blob))
    when = sheet_month(grid, name)
    table = read_columns(grid, {"value": column}, what)
    return {area: figures["value"] for area, figures in table.items()}, when


def read_population(blob: bytes) -> tuple[dict[str, int], tuple[int, int]]:
    return read_by_county(blob, "人口數", "population")


def read_indigenous(blob: bytes) -> tuple[dict[str, int], tuple[int, int]]:
    """Table 1.4's 原住民人數 (Grand-Total) is every registered indigenous
    person; the plains, mountain and Pingpu counts follow it."""
    return read_by_county(blob, "原住民人數", "indigenous")


def inspect(urls: list[str], rows: int) -> None:
    """Print each workbook's sheets and first rows; a probe, for a workbook
    probe_xlsx cannot open."""
    for url in urls:
        blob = http_get(url, binary=True)
        assert isinstance(blob, bytes)
        log(f"inspect: {url} ({len(blob):,} bytes)")
        for name, grid in grids_of(blob).items():
            log(f"  -- {name!r}: {len(grid)} rows")
            for row in grid[:rows]:
                log("     " + " | ".join(cell[:22] for cell in row[:26]))


# ---------------------------------------------------------------------------
# Religion: the prior, the signal, and the tilt.
# ---------------------------------------------------------------------------
BUILDINGS_PAGE_URL = "https://statis.moi.gov.tw/micst/webMain.aspx?k=menuy"
BUILDINGS_URL = MOI_REPORTS + "331030.xlsx"       # 內政統計年報 6-01 宗教教務概況
BUILDINGS_SOURCE = ("Ministry of the Interior, 內政統計年報 (statistical yearbook), table 06-01 "
                    "宗教教務概況: registered temples and churches by county and city")
TEMPLES, CHURCHES = "Temples", "Churches"
# Which building count moves which tradition. The yearbook counts temples by
# tradition only nationally (its 宗教別 sheet: 道教 9,824 of 12,397 in 2025,
# 佛教 2,277, 一貫道 243 ...), so by county the signal is temples against
# churches, and the three temple traditions move together.
SIGNAL: dict[str, str] = {"Buddhism": TEMPLES, "Taoism": TEMPLES, "Other religions": TEMPLES,
                          "Christianity": CHURCHES}
COUNTY_SHEET = re.compile(r"^\s*(\d{4})\s*\(區域別\)\s*$")


def read_buildings(blob: bytes) -> tuple[dict[str, dict[str, float]], int]:
    """{official name: {"Temples": n, "Churches": n}} for the 22 counties and
    總計 from the yearbook's latest county sheet ('2025(區域別)'), and its year.

    The sheet has one row per county with the registered buildings in three
    columns, 合計, 寺廟 and 教(會)堂, and a followers column that counts temple
    followers only; the national row is written against the year. The 宗教別
    sheet beside it splits the national totals by tradition and is not read.
    """
    name, grid, (year, _) = latest_sheet(grids_of(blob), COUNTY_SHEET)
    table = read_columns(grid, {TEMPLES: "寺廟", CHURCHES: "教(會)堂"}, "buildings",
                         year_row_is_national=True)
    out = {area: {k: float(v) for k, v in figures.items()} for area, figures in table.items()}
    for area, figures in out.items():
        if figures[TEMPLES] + figures[CHURCHES] <= 0:
            raise SystemExit(f"taiwan: buildings: {area} has no registered temple or church")
    log(f"  buildings (sheet {name!r}, end of {year}): {out[NATIONAL][TEMPLES]:,.0f} temples, "
        f"{out[NATIONAL][CHURCHES]:,.0f} churches")
    return out, year


PRIOR_YEAR = 2023
PRIOR_URL = ("https://www.pewresearch.org/religion/2024/06/17/"
             "religious-landscape-and-change-in-east-asia/")
PRIOR_SOURCE = ("Pew Research Center, 'Religion and Spirituality in East Asian Societies' "
                "(17 June 2024), religious composition of Taiwanese adults surveyed in 2023")
PRIOR_LICENCE = "(c) Pew Research Center; figures cited for research with attribution"
# Self-identified affiliation of adults, whole percentages as the report
# prints them: Buddhist 28, Daoist 24, Christian 7, other religion 12, no
# religion 27, don't know 2 (left out and the rest scaled to 100).
PRIOR: dict[str, float] = {"Buddhism": 28.0, "Taoism": 24.0, "Christianity": 7.0,
                           "Other religions": 12.0}
PRIOR_NONE = 27.0
PRIOR_NO_ANSWER = 2.0

TILT_BOUND = 3.0
# Absolute bounds on the two traditions whose buildings are many and small:
# a county of village churches and one-room Yiguandao halls must not come
# out mostly Christian or mostly "other" on the strength of a building count.
CAPS: dict[str, float] = {"Christianity": 25.0, "Other religions": 25.0}
RELIGION_METHOD = "tier1-national-prior-tilted-by-religious-buildings"
ETHNICITY_METHOD = "tier1-register-counts-plus-survey-share-plus-uniform-split"


def hundred(shares: dict[str, float]) -> list[dict[str, Any]]:
    """Shares to one decimal summing to exactly 100.0, largest remainder,
    largest first, name breaking a tie; a zero share is dropped."""
    total = sum(v for v in shares.values() if v > 0)
    if total <= 0:
        return []
    items = [(g, v / total * 1000) for g, v in shares.items() if v > 0]
    floors = [int(v) for _, v in items]
    order = sorted(range(len(items)), key=lambda i: -(items[i][1] - floors[i]))
    for i in order[:1000 - sum(floors)]:
        floors[i] += 1
    out = [{"group": g, "pct": floors[i] / 10} for i, (g, _) in enumerate(items)]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out


def prior_shares() -> tuple[dict[str, float], float]:
    """The survey prior with the don't-knows left out and the rest scaled to 100."""
    answered = sum(PRIOR.values()) + PRIOR_NONE
    scale = 100.0 / answered
    return {g: v * scale for g, v in PRIOR.items()}, PRIOR_NONE * scale


def tilt(prior: dict[str, float], none: float, national: dict[str, float],
         unit: dict[str, float], *, bound: float = TILT_BOUND,
         caps: dict[str, float] | None = None, signal: dict[str, str] | None = None
         ) -> tuple[dict[str, float], dict[str, float], list[str]]:
    """The prior's affiliated part, tilted by a unit's signal relative to the nation's.

    ``prior`` is the survey's affiliated shares, ``none`` its no-religion
    share; ``national`` and ``unit`` are building counts, by the prior's
    groups or, with ``signal`` mapping each group to a count, by whatever the
    counts are of (temples and churches). Returns the tilted shares
    (affiliated groups plus "No religion", summing to ``sum(prior) + none``),
    the clipped ratios by count, and the groups a cap held.
    """
    caps = CAPS if caps is None else caps
    keys = list(dict.fromkeys((signal or {}).get(g, g) for g in prior))
    nat_total = sum(national[k] for k in keys)
    unit_total = sum(unit[k] for k in keys)
    if nat_total <= 0 or unit_total <= 0:
        raise ValueError("a signal with no buildings cannot tilt anything")
    ratios: dict[str, float] = {}
    for k in keys:
        nat_share = national[k] / nat_total
        unit_share = unit[k] / unit_total
        raw = (unit_share / nat_share) if nat_share > 0 else 1.0
        ratios[k] = min(max(raw, 1.0 / bound), bound)
    target = sum(prior.values())
    raw_shares = {g: prior[g] * ratios[(signal or {}).get(g, g)] for g in prior}
    scale = target / sum(raw_shares.values())
    shares = {g: v * scale for g, v in raw_shares.items()}
    held: list[str] = []
    for _ in range(len(caps) + 1):
        over = [g for g in shares if g in caps and g not in held and shares[g] > caps[g] + 1e-9]
        if not over:
            break
        for g in over:
            shares[g] = caps[g]
            held.append(g)
        free = [g for g in shares if g not in held]
        remaining = target - sum(shares[g] for g in held)
        free_total = sum(shares[g] for g in free)
        for g in free:
            shares[g] = shares[g] / free_total * remaining if free_total > 0 else 0.0
    shares["No religion"] = none
    return shares, ratios, held


def distance(a: dict[str, float], b: dict[str, float]) -> float:
    """Total variation between two share dicts, in points."""
    keys = set(a) | set(b)
    return sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys) / 2


# ---------------------------------------------------------------------------
# Ethnicity: the composition
# ---------------------------------------------------------------------------
INDIGENOUS = "Taiwanese indigenous peoples"
HAKKA = "Hakka"
HOKLO = "Hoklo Taiwanese"
MAINLANDER = "Mainland Chinese (waishengren)"


def compose_ethnicity(indigenous_pct: float, hakka_pct: float, identity: dict[str, float]
                      ) -> dict[str, float]:
    """Indigenous and Hakka as given, the rest split Hoklo : mainlander in the
    national single-identification ratio. Sums to 100."""
    if indigenous_pct < 0 or hakka_pct < 0 or indigenous_pct + hakka_pct > 100:
        raise ValueError(f"indigenous {indigenous_pct} and Hakka {hakka_pct} do not fit in 100")
    hoklo, mainlander = identity[HOKLO], identity[MAINLANDER]
    if hoklo <= 0 or mainlander < 0:
        raise ValueError("the identity ratio must be positive")
    rest = 100.0 - indigenous_pct - hakka_pct
    return {INDIGENOUS: indigenous_pct, HAKKA: hakka_pct,
            HOKLO: rest * hoklo / (hoklo + mainlander),
            MAINLANDER: rest * mainlander / (hoklo + mainlander)}


# ---------------------------------------------------------------------------
# Estimates and records
# ---------------------------------------------------------------------------
LANGUAGE_NOTE = (
    f"{LANGUAGE_YEAR} census (DGBAS results release, Table 2-5): the main language "
    "currently used, one answer per person, for residents of ROC nationality aged 6 and "
    "over. The census also recorded a secondary language, which is not read: Hokkien is "
    "the second language of about half the country. Written by the map owner's decision "
    f"of {DECISION}.")


def ethnicity_estimate(name: str, indigenous: int, population: int, when: tuple[int, int],
                       hakka: dict[str, Any], identity: dict[str, float]
                       ) -> dict[str, Any]:
    indigenous_pct = indigenous / population * 100
    shares = compose_ethnicity(indigenous_pct, hakka["pct"], identity)
    year, month = when
    note = (
        f"Modelled from three official figures: the household register's {indigenous:,} "
        f"people of indigenous status among {population:,} registered residents at the end "
        f"of {month}/{year} (Ministry of the Interior), the Hakka Affairs Council's {HAKKA_YEAR} "
        f"survey estimate that {hakka['pct']:.1f}% of the county meets the Hakka Basic Act "
        "definition, and the same survey's national single-identification ratio of Hoklo to "
        f"mainlander ({identity[HOKLO]:.1f} : {identity[MAINLANDER]:.1f}), which splits the "
        "rest of every county alike. No Taiwanese census asks ethnicity, so this is a model, "
        "not a count: the Hoklo-mainlander split is a national assumption, the Hakka share is "
        "a survey of registered residents, and a person can be both Hakka and indigenous. "
        f"Written by the map owner's decision of {DECISION}.")
    return estimate(MODELLED, hundred(shares), method=ETHNICITY_METHOD,
                    inputs=[f"moi-register-indigenous-{name}-{year}-{month:02d}",
                            f"moi-register-population-{name}-{year}-{month:02d}",
                            f"hakka-survey-{HAKKA_YEAR}-{name}",
                            f"hakka-survey-{HAKKA_YEAR}-identity-national"],
                    note=note)


def religion_estimate(name: str, buildings: dict[str, dict[str, float]], year: int
                      ) -> tuple[dict[str, Any], float, list[str], dict[str, float]]:
    prior, none = prior_shares()
    national, unit = buildings[NATIONAL], buildings[name]
    shares, ratios, held = tilt(prior, none, national, unit, signal=SIGNAL)
    rows = hundred(shares)
    moved = distance(shares, dict(prior, **{"No religion": none}))
    held_text = ("" if not held else
                 f"; {' and '.join(held)} came out above the bound of "
                 f"{', '.join(f'{CAPS[g]:.0f}%' for g in held)} and "
                 f"{'were' if len(held) > 1 else 'was'} held there, the rest rescaled")
    note = (
        f"Modelled from Pew Research Center's {PRIOR_YEAR} survey of Taiwanese adults "
        f"(Buddhist {PRIOR['Buddhism']:.0f}%, Daoist {PRIOR['Taoism']:.0f}%, Christian "
        f"{PRIOR['Christianity']:.0f}%, other {PRIOR['Other religions']:.0f}%, no religion "
        f"{PRIOR_NONE:.0f}%, don't know {PRIOR_NO_ANSWER:.0f}% left out) tilted by the Ministry "
        f"of the Interior's count of this county's {unit[TEMPLES]:,.0f} registered temples and "
        f"{unit[CHURCHES]:,.0f} churches at the end of {year}. No census or survey gives "
        "religion by county, so this is a model, not a count: the county's church share of "
        "its buildings over the nation's scales the survey's Christian share and its temple "
        "share the Buddhist, Daoist and other shares together (the register splits temples by "
        f"tradition only nationally), each clipped to 1/{TILT_BOUND:.0f}-{TILT_BOUND:.0f} "
        f"(temples x{ratios[TEMPLES]:.2f}, churches x{ratios[CHURCHES]:.2f}), and no religion "
        f"is held at the national figure{held_text}. It sits {moved:.1f} points from the prior; "
        "no backtest is possible, because no county-level self-identification figure exists. "
        f"Written by the map owner's decision of {DECISION}.")
    est = estimate(MODELLED, rows, method=RELIGION_METHOD,
                   inputs=[f"pew-east-asia-{PRIOR_YEAR}-taiwan",
                           f"moi-religious-buildings-{name}-{year}",
                           f"moi-religious-buildings-national-{year}"],
                   note=note)
    est["tilt"] = {k: round(v, 3) for k, v in ratios.items()}
    if held:
        est["capped"] = held
    return est, moved, held, shares


def build(language: dict[str, dict[str, Any]], hakka: dict[str, dict[str, Any]],
          identity: dict[str, float], population: dict[str, int], indigenous: dict[str, int],
          when: tuple[int, int], buildings: dict[str, dict[str, float]], buildings_year: int,
          ) -> list[dict[str, Any]]:
    year, month = when
    prior, none = prior_shares()
    log(f"  prior (don't know left out): no religion {none:.1f}, "
        + ", ".join(f"{g} {v:.1f}" for g, v in prior.items()))
    log(f"  register: {indigenous[NATIONAL]:,} indigenous of {population[NATIONAL]:,} "
        f"({indigenous[NATIONAL] / population[NATIONAL] * 100:.2f}%) at the end of {month}/{year}")
    sources = [
        {"field": "language", "name": LANGUAGE_SOURCE, "url": LANGUAGE_PAGE_URL,
         "year": LANGUAGE_YEAR, "license": LANGUAGE_LICENCE},
        {"field": "ethnicity", "name": INDIGENOUS_SOURCE, "url": INDIGENOUS_PAGE_URL,
         "year": year, "license": MOI_LICENCE},
        {"field": "ethnicity/population", "name": POPULATION_SOURCE, "url": POPULATION_PAGE_URL,
         "year": year, "license": MOI_LICENCE},
        {"field": "ethnicity", "name": HAKKA_SOURCE, "url": HAKKA_URL, "year": HAKKA_YEAR,
         "license": HAKKA_LICENCE},
        {"field": "religion", "name": PRIOR_SOURCE, "url": PRIOR_URL, "year": PRIOR_YEAR,
         "license": PRIOR_LICENCE},
        {"field": "religion", "name": BUILDINGS_SOURCE, "url": BUILDINGS_PAGE_URL,
         "year": buildings_year, "license": MOI_LICENCE},
    ]
    records = []
    moved: list[tuple[float, str, list[str], dict[str, float]]] = []
    for chinese, (name, aliases) in COUNTIES.items():
        rows = [{"group": g, "pct": p} for g, p in language[chinese]["main"].items() if p > 0]
        rows.sort(key=lambda r: (-r["pct"], r["group"]))
        religion, dist, held, tilted = religion_estimate(chinese, buildings, buildings_year)
        moved.append((dist, name, held, tilted))
        records.append(record(
            f"{ISO3}-{slugify(name)}", name, level="admin1", parent=ISO3, country=ISO3,
            aliases=list(aliases), sources=sources,
            population=measure(population[chinese], year=year, source=POPULATION_SOURCE,
                               note=f"registered population at the end of {month}/{year}"),
            language=rows, language_year=LANGUAGE_YEAR, language_basis=LANGUAGE_BASIS,
            language_note=LANGUAGE_NOTE,
            ethnicity=ethnicity_estimate(chinese, indigenous[chinese], population[chinese],
                                         when, hakka[chinese], identity),
            religion=religion,
        ))
    moved.sort(key=lambda m: -m[0])
    log("  religion: the five counties the tilt moves furthest from the national prior:")
    for dist, name, held, tilted in moved[:5]:
        top = ", ".join(f"{g} {tilted[g]:.1f}" for g in PRIOR)
        signal = buildings[next(c for c, (n, _) in COUNTIES.items() if n == name)]
        log(f"      {name:18} {dist:5.1f} points  {top}  "
            f"({signal[TEMPLES]:.0f} temples, {signal[CHURCHES]:.0f} churches)"
            + (f"  (held at the bound: {', '.join(held)})" if held else ""))
    capped = [name for _, name, held, _ in moved if held]
    log(f"  religion: {len(capped)} counties hit a bound"
        + (f": {', '.join(capped)}" if capped else ""))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--language-text", default=None,
                    help="a saved probe_pdf dump of the census release instead of the PDF")
    ap.add_argument("--hakka-text", default=None,
                    help="a saved probe_pdf dump of the Hakka report instead of the PDF")
    ap.add_argument("--population-xls", default=None, help="a saved copy of MOI table 1.1")
    ap.add_argument("--indigenous-xls", default=None, help="a saved copy of MOI table 1.4")
    ap.add_argument("--buildings-xls", default=None,
                    help="a saved copy of the yearbook's 宗教教務概況 workbook")
    ap.add_argument("--inspect", nargs="*", default=None, metavar="URL",
                    help="print the sheets and first rows of these workbooks and stop")
    ap.add_argument("--rows", type=int, default=14, help="rows to print per sheet with --inspect")
    args = ap.parse_args()
    if args.inspect is not None:
        inspect(args.inspect or [POPULATION_URL, INDIGENOUS_URL, BUILDINGS_URL], args.rows)
        return 0
    log(f"taiwan: language from the {LANGUAGE_YEAR} census, ethnicity and religion modelled, "
        f"by the owner's decision of {DECISION}")

    def text_of(saved: str | None, url: str, *, aia: bool = False) -> str:
        if saved:
            return Path(saved).read_text(encoding="utf-8")
        return fetch_text(url, aia=aia)

    def blob_of(saved: str | None, url: str) -> bytes:
        if saved:
            return Path(saved).read_bytes()
        blob = http_get(url, binary=True)
        assert isinstance(blob, bytes)
        return blob

    # ws.dgbas.gov.tw sends its leaf certificate without the intermediate, which
    # the AIA repair supplies; see probe_pdf.fetch_blob.
    language = read_language(text_of(args.language_text, LANGUAGE_URL, aia=True))
    hakka_text = text_of(args.hakka_text, HAKKA_URL)
    hakka = read_hakka(hakka_text)
    identity = read_identity(hakka_text)
    population, when = read_population(blob_of(args.population_xls, POPULATION_URL))
    indigenous, when_indigenous = read_indigenous(blob_of(args.indigenous_xls, INDIGENOUS_URL))
    if when != when_indigenous:
        raise SystemExit(f"taiwan: population is for {when} and the indigenous count for "
                         f"{when_indigenous}; the two must be the same month")
    buildings, buildings_year = read_buildings(blob_of(args.buildings_xls, BUILDINGS_URL))
    records = build(language, hakka, identity, population, indigenous, when, buildings,
                    buildings_year)
    if len(records) != 22:
        raise SystemExit(f"taiwan: expected 22 counties and cities, built {len(records)}")
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} records to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
