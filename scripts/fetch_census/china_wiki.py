#!/usr/bin/env python3
"""China: ethnicity by province, from the census tables Wikipedia transcribes.

China's census records the 56 official nationalities (minzu) and the
National Bureau of Statistics publishes the composition of every
first-level division in the census tabulations. Those tabulations sit on
``stats.gov.cn`` and in provincial communiques on hosts this project has
not been able to open from a build machine, and a province's Wikipedia
article transcribes the table -- under "Demographics" or "Ethnic groups",
captioned like "Ethnic groups in Guangxi, 2020 census", a row per
nationality with its population and share. That is what is read here,
through the MediaWiki API, one article per division, the way
``wiki_census.py`` reads Kazakhstan and Cambodia; the record names the
census as its source and the article as the copy it was read from.

What the reader does with an article:

* it looks at every table in the article and keeps those whose first
  column (or, in a transposed table, first row) is nationalities -- a
  table is an ethnic-composition table when it names Han and at least one
  other of the 56 -- and among those prefers the one captioned or headed
  with the latest census year, so an article that carries both 2010 and
  2020 yields 2020 and ``ethnicity_year`` says which;
* where every row prints a count and the table also prints its total or
  its remainder ("Others"), the shares are computed from the counts,
  because a transcribed share is where the slips are (Shandong's table
  gives its 310,738 "other" as 0.003%); otherwise the shares are read as
  printed, and a shortfall from 100 of up to five points, in a table that
  stops after the largest groups, is written as the remainder;
* the shares are re-rounded to one decimal by largest remainder so a
  composition is a whole population (they must add to 100 within 0.3
  before that, or the division is refused with the sum in the log);
* labels are the ethnonym as the table prints it, singular and without the
  word "people"; the census's residual row -- "Others", "other ethnic
  groups" -- is written as "Other ethnic groups".

A division whose article holds no such table is logged with the reason and
not written. Nothing is estimated from a national figure.

**Cross-check.** Beijing's own 2010 communique (the Beijing Municipal
Bureau of Statistics, 4 May 2011; a second release on the ethnic detail on
9 January 2012 -- both through the Internet Archive, the URLs are in the
record's note) gives a resident population of 19,612,000, Han 18,811,000
(95.9%), all minorities 801,000 (4.1%), Manchu 336,000, Hui 249,000,
Mongol 77,000, Korean 37,000, Tujia 24,000. When Beijing is read from a
2010 table, the Han share must come out at 95.9 and the Manchu and Hui
counts must agree with the communique within rounding, or the run refuses;
when it is read from 2020 the communique's figures are printed beside the
2020 ones so a reader can compare a decade's change.

Usage:
    python -m scripts.fetch_census.china_wiki
    python -m scripts.fetch_census.china_wiki --only Beijing --only Guangxi
    python -m scripts.fetch_census.china_wiki --inspect            # show the tables
    python -m scripts.fetch_census.china_wiki --inspect --raw      # and the sections
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_json, log, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import REF, plain  # noqa: E402

OUT = "china_wiki_province.json"
SOURCE_2020 = ("National Bureau of Statistics of China, Seventh National Population "
               "Census (2020), population by ethnic group")
SOURCE_2010 = ("National Bureau of Statistics of China, Sixth National Population "
               "Census (2010), population by ethnic group")
SOURCE_2000 = ("National Bureau of Statistics of China, Fifth National Population "
               "Census (2000), population by ethnic group")
SOURCES = {2020: SOURCE_2020, 2010: SOURCE_2010, 2000: SOURCE_2000}
LICENCE = "Official statistics; compilation CC BY-SA 4.0"
RESIDUAL = "Other ethnic groups"
TOLERANCE = 0.3
SHORTFALL = 5.0     # a table that stops after the largest groups

# The 31 first-level divisions the boundary file draws (Hong Kong and Macau
# are SARs with censuses of their own and are not read here), each with the
# English and Chinese Wikipedia articles that carry its census table. The
# shape name is exactly as ``site/data/admin1/CHN.json`` prints it;
# "Guangdong" is bare because CGAZ drew the province under its capital's
# name and common.py renames it to the bare province.
DIVISIONS: list[tuple[str, str, str]] = [
    ("Beijing Municipality", "Beijing", "北京市"),
    ("Tianjin Municipality", "Tianjin", "天津市"),
    ("Hebei Province", "Hebei", "河北省"),
    ("Shanxi Province", "Shanxi", "山西省"),
    ("Inner Mongolia Autonomous Region", "Inner Mongolia", "内蒙古自治区"),
    ("Liaoning Province", "Liaoning", "辽宁省"),
    ("Jilin Province", "Jilin", "吉林省"),
    ("Heilongjiang Province", "Heilongjiang", "黑龙江省"),
    ("Shanghai Municipality", "Shanghai", "上海市"),
    ("Jiangsu Province", "Jiangsu", "江苏省"),
    ("Zhejiang Province", "Zhejiang", "浙江省"),
    ("Anhui Province", "Anhui", "安徽省"),
    ("Fujian Province", "Fujian", "福建省"),
    ("Jiangxi Province", "Jiangxi", "江西省"),
    ("Shandong Province", "Shandong", "山东省"),
    ("Henan Province", "Henan", "河南省"),
    ("Hubei Province", "Hubei", "湖北省"),
    ("Hunan Province", "Hunan", "湖南省"),
    ("Guangdong", "Guangdong", "广东省"),
    ("Guangxi Zhuang Autonomous Region", "Guangxi", "广西壮族自治区"),
    ("Hainan Province", "Hainan", "海南省"),
    ("Chongqing Municipality", "Chongqing", "重庆市"),
    ("Sichuan Province", "Sichuan", "四川省"),
    ("Guizhou Province", "Guizhou", "贵州省"),
    ("Yunnan Province", "Yunnan", "云南省"),
    ("Tibet Autonomous Region", "Tibet Autonomous Region", "西藏自治区"),
    ("Shaanxi Province", "Shaanxi", "陕西省"),
    ("Gansu Province", "Gansu", "甘肃省"),
    ("Qinghai Province", "Qinghai", "青海省"),
    ("Ningxia Hui Autonomous Region", "Ningxia", "宁夏回族自治区"),
    ("Xinjiang Uyghur Autonomous Region", "Xinjiang", "新疆维吾尔自治区"),
]

# Beijing's 2010 communique, for the cross-check: resident population and
# the five largest nationalities, in persons, as the bureau printed them
# (in 万, ten-thousands, so each figure is to the nearest thousand).
BEIJING_2010 = {
    "population": 19_612_000, "Han Chinese": 18_811_000, "minorities": 801_000,
    "Han share": 95.9, "Manchu": 336_000, "Hui": 249_000, "Mongol": 77_000,
    "Korean": 37_000, "Tujia": 24_000,
}
BEIJING_URLS = (
    "https://web.archive.org/web/20140219080018/http://www.bjstats.gov.cn/xwgb/tjgb/"
    "pcgb/201105/t20110504_201364.htm",
    "https://web.archive.org/web/20140203152457/http://www.bjstats.gov.cn/lhzl/rkpc/"
    "201201/t20120109_218572.htm",
)

# The 56 nationalities, in the spellings English and Chinese tables use,
# mapped to the label written. The label is the English ethnonym, singular,
# without "people"; a second spelling of the same nationality is folded
# onto the first so one people is one group across the 31 divisions.
# Nothing here is a classification -- "Kirgiz" and "Kyrgyz" are two
# romanisations of one census code, and 柯尔克孜族 is its Chinese name.
NATIONALITIES: dict[str, str] = {}
for _row in (
    ("Han Chinese", "Han", "汉族", "汉"),
    ("Zhuang", "壮族"), ("Hui", "回族"), ("Manchu", "满族"),
    ("Uyghur", "Uighur", "Uygur", "维吾尔族"),
    ("Miao", "Hmong", "苗族"), ("Yi", "彝族"), ("Tujia", "土家族"),
    ("Tibetan", "Zang", "藏族"), ("Mongol", "Mongolian", "蒙古族"),
    ("Dong", "Kam", "侗族"), ("Bouyei", "Buyei", "Buyi", "布依族"),
    ("Yao", "瑶族"), ("Bai", "白族"), ("Korean", "Chaoxian", "Joseon", "朝鲜族"),
    ("Hani", "哈尼族"), ("Li", "黎族"), ("Kazakh", "Kazak", "哈萨克族"),
    ("Dai", "Tai", "傣族"), ("She", "畲族"), ("Lisu", "傈僳族"),
    ("Dongxiang", "东乡族"), ("Gelao", "Gelo", "仡佬族"), ("Lahu", "拉祜族"),
    ("Wa", "Va", "佤族"), ("Sui", "Shui", "水族"), ("Nakhi", "Naxi", "纳西族"),
    ("Qiang", "羌族"), ("Tu", "Monguor", "土族"), ("Mulao", "Mulam", "仫佬族"),
    ("Xibe", "Sibe", "Xibo", "锡伯族"), ("Kyrgyz", "Kirgiz", "Kirghiz", "柯尔克孜族"),
    ("Jingpo", "Kachin", "景颇族"), ("Daur", "达斡尔族"), ("Salar", "撒拉族"),
    ("Blang", "Bulang", "布朗族"), ("Maonan", "毛南族"), ("Tajik", "塔吉克族"),
    ("Pumi", "普米族"), ("Achang", "阿昌族"), ("Nu", "怒族"),
    ("Evenk", "Ewenki", "Evenki", "鄂温克族"), ("Gin", "Jing", "Kinh", "京族"),
    ("Jino", "基诺族"), ("De'ang", "Deang", "Palaung", "德昂族"),
    ("Bonan", "Baoan", "保安族"), ("Russian", "俄罗斯族"),
    ("Yugur", "Yughur", "裕固族"), ("Uzbek", "乌孜别克族"),
    ("Monba", "Monpa", "Moinba", "门巴族"), ("Oroqen", "鄂伦春族"),
    ("Derung", "Drung", "独龙族"), ("Hezhen", "Nanai", "赫哲族"),
    ("Gaoshan", "高山族"), ("Lhoba", "珞巴族"), ("Tatar", "塔塔尔族"),
):
    for _spelling in _row:
        NATIONALITIES[_spelling.lower()] = _row[0]

RESIDUAL_WORDS = re.compile(
    r"^(others?|other ethnic groups?|other nationalit(y|ies)|other minorit(y|ies)|"
    r"other ethnicit(y|ies)|other minority groups?|all others?|other groups?|"
    r"其他|其他民族|其它|其它民族)$", re.I)
TOTAL_WORDS = re.compile(r"^(total|all|population|total population|合计|总计|总人口|全部)$", re.I)
SUBTOTAL_WORDS = re.compile(
    r"^((all |ethnic |national )?minorit(y|ies)( nationalities| groups| ethnic groups)?|"
    r"non-han|non han|少数民族|各少数民族)$", re.I)
# Rows a census table carries beside the 56 that are people counted and
# not a nationality: those whose nationality is not among the 56, and
# naturalised citizens. Both fold into the residual.
UNLISTED_WORDS = re.compile(
    r"^(unrecogni[sz]ed|undistinguished|unclassified|other unlisted|unidentified|"
    r"naturali[sz]ed|foreign(ers)?( naturalised)?|未识别|未识别民族|外国人加入中国籍|"
    r"入籍)(\s.*)?$", re.I)

# Where a table is written on one line, its row and caption markers sit
# mid-line; they are put at line starts before parsing.
INLINE_ROW = re.compile(r"\s*\|-\s*(?=[|!]|$)")
INLINE_CAPTION = re.compile(r"(?<=\S)\s+(?=\|\+)")
INLINE_END = re.compile(r"\s+(?=\|\}\s*$)")
# A cell's attributes before its pipe, unquoted -- ``colspan=3 |`` -- which
# probe_wikitable's cleaner leaves in place (it strips the quoted form).
BARE_ATTRS = re.compile(r'^(?:[\w-]+=(?:"[^"]*"|[^\s|]+)\s*)+\|\s*')


def cell_text(cell: str) -> str:
    return BARE_ATTRS.sub("", plain(cell))


# ---------------------------------------------------------------------------
# Wikitext tables, with the text that names them
# ---------------------------------------------------------------------------

def lines_of(wikitext: str) -> list[str]:
    out: list[str] = []
    for line in wikitext.split("\n"):
        line = INLINE_ROW.sub("\n|-\n", line)
        line = INLINE_CAPTION.sub("\n", line)
        line = INLINE_END.sub("\n", line)
        out.extend(line.split("\n"))
    return out


def tables_with_context(wikitext: str) -> list[dict[str, Any]]:
    """Every top-level table, with its caption, section and preceding prose.

    ``probe_wikitable.tables`` drops the caption, and for these tables the
    caption is where the census year lives ("Ethnic groups in Guangxi,
    2020 census"). So this is that parser again, keeping the ``|+`` line,
    the ``==`` heading the table sits under, and the last non-empty lines
    of prose before it, which is where an uncaptioned table says its year.
    A table whose first row is one title cell spanning the width -- "Ethnic
    groups in Hebei, 2000 census" as a header cell -- has that row moved
    into the caption.
    """
    out: list[dict[str, Any]] = []
    depth, rows, caption = 0, None, ""
    section = ""
    prose: list[str] = []
    for line in lines_of(wikitext):
        s = line.strip()
        if depth == 0 and s.startswith("=") and s.endswith("="):
            section = s.strip("= ").strip()
            prose = []
            continue
        if s.startswith("{|"):
            depth += 1
            if depth == 1:
                rows, caption = [], ""
            continue
        if s.startswith("|}"):
            depth -= 1
            if depth == 0 and rows is not None:
                rows = [r for r in rows if r]
                while rows and len(rows[0]) == 1 and len(rows) > 1 and len(rows[1]) > 1:
                    caption = (caption + " " + rows[0][0]).strip()
                    rows = rows[1:]
                out.append({"caption": caption, "section": section,
                            "prose": " ".join(prose[-3:]), "rows": rows})
                rows = None
            continue
        if depth == 0:
            if s and not s.startswith(("{{", "}}", "[[File", "[[Image", "<!--", "|")):
                prose.append(plain(s)[:200])
            continue
        if depth != 1 or rows is None:
            continue
        if s.startswith("|+"):
            caption = cell_text(s[2:])
            continue
        if s.startswith("|-"):
            rows.append([])
            continue
        if s.startswith("!") or s.startswith("|"):
            marker = s[0]
            cells = re.split(r"!!|\|\|", s[1:]) if marker == "!" else s[1:].split("||")
            if not rows:
                rows.append([])
            rows[-1].extend(cell_text(c) for c in cells)
    return out


def ethnonym(cell: str) -> str | None:
    """The written label for a first-column cell, or None if it is not one.

    A table prints "Han Chinese", "Han", "Zhuang people", "Hui (Muslim)",
    "Tibetans", "Uyghurs" or "Zang (Tibetan)"; all are found in the
    spelling list after the parenthesis, the word "people" and a plural
    -s are taken off -- and the parenthesis is tried too, for "Zang
    (Tibetan)".
    """
    inner = re.findall(r"\((.*?)\)", cell)
    text = re.sub(r"\(.*?\)", "", cell).strip()
    text = re.sub(r"\s+(people|peoples|ethnic group|nationality)$", "", text, flags=re.I)
    text = text.strip(" *:")
    for candidate in (text, text.rstrip("s"), text.replace("Chinese", "").strip(), *inner):
        if candidate:
            hit = NATIONALITIES.get(candidate.lower())
            if hit:
                return hit
    return None


def kind(cell: str) -> str:
    """What a label cell is: a nationality, the residual, a total, or prose."""
    text = re.sub(r"\(.*?\)", "", cell).strip(" *:")
    if ethnonym(cell):
        return "group"
    if RESIDUAL_WORDS.match(text) or UNLISTED_WORDS.match(text):
        return "residual"
    if TOTAL_WORDS.match(text):
        return "total"
    if SUBTOTAL_WORDS.match(text):
        return "subtotal"
    return "other"


def number(cell: str) -> float | None:
    """A printed count or share, or None where the cell holds neither."""
    text = re.sub(r"\s*(percent|per cent|％|%)\s*$", "", cell.strip(), flags=re.I)
    text = text.replace(",", "").replace(" ", "").replace(" ", "").replace(" ", "")
    if text in ("", "-", "—", "–", "n/a", "N/A"):
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def oriented(rows: list[list[str]]) -> list[list[str]]:
    """Rows with the nationalities down the first column.

    Heilongjiang's and Guangxi's tables run the other way -- nationalities
    across the header, "Population" and "Percentage" as the rows -- and are
    transposed here so one reader serves both.
    """
    if not rows or not rows[0]:
        return rows
    down = sum(1 for r in rows if r and ethnonym(r[0]))
    across = sum(1 for c in rows[0] if ethnonym(c))
    if across > down and across >= 2:
        width = max(len(r) for r in rows)
        padded = [r + [""] * (width - len(r)) for r in rows]
        return [list(col) for col in zip(*padded)]
    return rows


def is_ethnic_table(t: dict[str, Any]) -> bool:
    """Han and at least one other nationality down the first column."""
    rows = oriented(t["rows"])
    names = {ethnonym(r[0]) for r in rows if r}
    return "Han Chinese" in names and len(names - {None}) >= 2


def year_of(t: dict[str, Any]) -> int | None:
    """The census year the table says it is, from its caption, header or prose."""
    for text in (t["caption"], " ".join(t["rows"][0]) if t["rows"] else "",
                 t["section"], t["prose"]):
        years = [int(y) for y in re.findall(r"(?<!\d)(19[89]\d|20[012]\d)(?!\d)", text)]
        if years:
            return max(years)
    return None


# ---------------------------------------------------------------------------
# Reading one table
# ---------------------------------------------------------------------------

def columns(header: list[str], year: int | None) -> tuple[int | None, int | None]:
    """(count column, share column) from the header row.

    A table with both years side by side ("Population 2010 | % 2010 |
    Population 2020 | % 2020") yields the columns of the chosen year;
    otherwise the first "population"/"number"/"total" column and the first
    "%"/"percent"/"share"/"proportion" column. "Male" and "Female" are
    neither.
    """
    counts, shares = [], []
    for i, cell in enumerate(header):
        c = cell.lower()
        if "%" in c or "percent" in c or "share" in c or "proportion" in c or "比例" in c or "占" in c:
            shares.append(i)
        elif any(w in c for w in ("population", "number", "persons", "people", "count",
                                  "total", "人口", "人数")) \
                or re.fullmatch(r"(19|20)\d\d(\s+census)?", c):
            counts.append(i)
    if year and len(counts) > 1:
        dated = [i for i in counts if str(year) in header[i]]
        counts = dated or counts
    if year and len(shares) > 1:
        dated = [i for i in shares if str(year) in header[i]]
        shares = dated or shares
    return (counts[0] if counts else None, shares[0] if shares else None)


def read_table(t: dict[str, Any], where: str) -> dict[str, Any]:
    """One ethnic table -> {"groups": {label: (count, pct)}, "total": ...}.

    Refuses rather than guesses: a header with no share and no count column,
    a group row printing neither, a nationality listed twice.
    """
    rows = oriented(t["rows"])
    header = rows[0]
    year = year_of(t)
    ci, si = columns(header, year)
    if ci is None and si is None:
        raise SystemExit(f"china_wiki: {where}: the ethnic table's header "
                         f"{header} has no population or share column")
    groups: dict[str, tuple[float | None, float | None]] = {}
    residual_count, residual_pct, saw_residual = 0.0, 0.0, False
    total_count: float | None = None
    for row in rows[1:]:
        if not row:
            continue
        what = kind(row[0])
        count = number(row[ci]) if ci is not None and ci < len(row) else None
        pct = number(row[si]) if si is not None and si < len(row) else None
        if what == "group":
            if count is None and pct is None:
                raise SystemExit(f"china_wiki: {where}: {row[0]!r} prints neither a "
                                 f"count nor a share: {row}")
            label = ethnonym(row[0]) or row[0]
            if label in groups:
                raise SystemExit(f"china_wiki: {where}: {label!r} appears twice in the table")
            groups[label] = (count, pct)
        elif what == "residual":
            saw_residual = True
            residual_count += count or 0.0
            residual_pct += pct or 0.0
        elif what == "total":
            total_count = count
        # A subtotal ("minorities") and a prose row are neither counted nor
        # refused: the subtotal is the sum of what follows it.
    if not groups:
        raise SystemExit(f"china_wiki: {where}: no nationality rows under {header}")
    if saw_residual:
        groups[RESIDUAL] = (residual_count if ci is not None else None,
                            residual_pct if si is not None else None)
    return {"groups": groups, "total": total_count, "year": year,
            "has_counts": ci is not None, "has_shares": si is not None}


def whole_hundred(shares: list[tuple[str, float]]) -> list[float]:
    """Shares to one decimal that sum to exactly 100.0, by largest remainder.

    The same rule ``build_entities.whole_hundred`` applies, written here
    because an adapter does not import the build.
    """
    total = sum(max(v, 0.0) for _, v in shares)
    tenths = [max(v, 0.0) / total * 1000 for _, v in shares]
    floors = [int(v) for v in tenths]
    order = sorted(range(len(tenths)), key=lambda i: -(tenths[i] - floors[i]))
    for i in order[:1000 - sum(floors)]:
        floors[i] += 1
    return [f / 10 for f in floors]


def composition(read: dict[str, Any], where: str) -> tuple[list[dict[str, Any]], str]:
    """The rows written -- group, pct (whole hundred), count where printed --
    and a sentence saying which figures they came from."""
    groups = dict(read["groups"])
    counts_complete = (read["has_counts"]
                       and all(c is not None for c, _ in groups.values())
                       and (read["total"] is not None or RESIDUAL in groups))
    if counts_complete:
        raw = [(g, c) for g, (c, _) in groups.items()]
        summed = sum(c for _, c in raw)
        if read["total"] is not None and abs(summed - read["total"]) / read["total"] > 0.005:
            raise SystemExit(f"china_wiki: {where}: counts add to {summed:,.0f} against "
                             f"a printed total of {read['total']:,.0f}")
        # A printed share that disagrees with its own count is a slip in the
        # transcription; it is logged, and the count is what is written.
        for g, (c, p) in groups.items():
            if p is not None and abs(100.0 * c / summed - p) > 0.1:
                log(f"  {where}: {g} is printed at {p}% but its count is "
                    f"{100.0 * c / summed:.3f}% of the total; the count is used")
        how = ("Shares computed from the printed counts, which add to the printed total"
               if read["total"] is not None else
               "Shares computed from the printed counts, which the table's remainder "
               "row completes")
    elif read["has_shares"] and all(p is not None for _, p in groups.values()):
        raw = [(g, p) for g, (_, p) in groups.items()]
        summed = sum(p for _, p in raw)
        if abs(summed - 100.0) <= TOLERANCE:
            how = "Shares as printed, re-rounded to one decimal so they sum to 100"
        elif RESIDUAL not in groups and 0 < 100.0 - summed <= SHORTFALL:
            rest = round(100.0 - summed, 3)
            raw.append((RESIDUAL, rest))
            groups[RESIDUAL] = (None, rest)
            how = (f"Shares as printed; the table stops after the groups it names, "
                   f"and the {rest:.2f}% it leaves unprinted is written as "
                   f"{RESIDUAL!r}")
        else:
            raise SystemExit(f"china_wiki: {where}: shares add to {summed:.2f}, "
                             f"not 100 within {TOLERANCE}")
    else:
        raise SystemExit(f"china_wiki: {where}: neither every share nor every count is printed")
    rounded = whole_hundred(raw)
    out = []
    for (g, _), pct in zip(raw, rounded):
        row: dict[str, Any] = {"group": g, "pct": pct}
        count = groups[g][0]
        if count is not None:
            row["count"] = int(round(count))
        out.append(row)
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out, how


def choose(found: list[dict[str, Any]], where: str) -> dict[str, Any] | None:
    """The ethnic table of the latest census year the article carries."""
    ethnic = [t for t in found if is_ethnic_table(t)]
    if not ethnic:
        return None
    ethnic.sort(key=lambda t: (year_of(t) or 0, len(t["rows"])), reverse=True)
    for t in ethnic:
        log(f"  {where}: ethnic table under {t['section']!r}, caption {t['caption']!r}, "
            f"year {year_of(t)}, {len(t['rows'])} rows")
    return ethnic[0]


# ---------------------------------------------------------------------------
# The cross-check, the records, the fetch
# ---------------------------------------------------------------------------

def check_beijing(rows: list[dict[str, Any]], year: int) -> None:
    by = {r["group"]: r for r in rows}
    ref = BEIJING_2010
    if year == 2010:
        han = by.get("Han Chinese", {})
        if han.get("pct") != ref["Han share"]:
            raise SystemExit(f"china_wiki: Beijing 2010 Han share {han.get('pct')} "
                             f"against the communique's {ref['Han share']}")
        for g in ("Manchu", "Hui"):
            count = by.get(g, {}).get("count")
            if count is not None and abs(count - ref[g]) > 1000:
                raise SystemExit(f"china_wiki: Beijing 2010 {g} {count:,} against the "
                                 f"communique's {ref[g]:,}")
        log("  Beijing: 2010 Han share and Manchu/Hui counts agree with the "
            "municipal communique")
    else:
        log(f"  Beijing: read from {year}; the 2010 communique gave Han "
            f"{ref['Han share']}% ({ref['Han Chinese']:,}), Manchu {ref['Manchu']:,}, "
            f"Hui {ref['Hui']:,}, Mongol {ref['Mongol']:,}, Korean {ref['Korean']:,}, "
            f"Tujia {ref['Tujia']:,} of {ref['population']:,}; {year} reads "
            + ", ".join(f"{g} {by[g]['pct']}%"
                        + (f" ({by[g]['count']:,})" if "count" in by[g] else "")
                        for g in ("Han Chinese", "Manchu", "Hui", "Mongol", "Korean", "Tujia")
                        if g in by))


def build_one(name: str, title: str, lang: str, wikitext: str) -> dict[str, Any] | None:
    found = tables_with_context(wikitext)
    t = choose(found, name)
    if t is None:
        log(f"  {name}: no ethnic-composition table in [{lang}] {title!r} "
            f"({len(found)} tables; none names Han and another nationality)")
        return None
    read = read_table(t, name)
    year = read["year"]
    if year not in SOURCES:
        raise SystemExit(f"china_wiki: {name}: cannot tell which census the table "
                         f"is from (caption {t['caption']!r}, section {t['section']!r}, "
                         f"year read {year})")
    rows, how = composition(read, name)
    if name == "Beijing Municipality":
        check_beijing(rows, year)
    from common import slugify
    source = SOURCES[year]
    url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
    edition = {"en": "English", "zh": "Chinese"}.get(lang, lang)
    note = (f"{source}, resident population of {name}. Read from the {edition} "
            f"Wikipedia article {title!r}, which transcribes the census table"
            + (f" captioned {t['caption']!r}" if t["caption"] else "")
            + f". {how}"
            + ("; counts as printed" if read["has_counts"] else "") + ". "
            + (f"{RESIDUAL!r} is the census's own remainder row. "
               if RESIDUAL in read["groups"] else ""))
    if name == "Beijing Municipality":
        note += ("Corroborated against the Beijing Municipal Bureau of Statistics' "
                 "2010 census communiques, which give Han 18,811,000 (95.9%) of "
                 "19,612,000 residents, Manchu 336,000, Hui 249,000, Mongol 77,000, "
                 f"Korean 37,000, Tujia 24,000: {BEIJING_URLS[0]} and {BEIJING_URLS[1]}. ")
    log(f"  {name}: {year}, {len(rows)} groups, leading "
        + ", ".join(f"{r['group']} {r['pct']}%" for r in rows[:3]))
    return record(
        f"CHN-{slugify(name)}", name, level="admin1", parent="CHN", country="CHN",
        sources=[{"field": "ethnicity", "name": source, "url": url, "license": LICENCE}],
        ethnicity=rows, ethnicity_year=year, ethnicity_note=note.strip())


def fetch(title: str, lang: str = "en") -> str:
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext",
                                "format": "json", "formatversion": "2", "redirects": "1"})
    parsed = http_json(f"https://{lang}.wikipedia.org/w/api.php?{q}", timeout=90).get("parse") or {}
    text = parsed.get("wikitext") or ""
    log(f"  [{lang}] {title!r}: {len(text):,} bytes of wikitext")
    return text


SECTION_WORDS = re.compile(r"demograph|ethnic|population|people|minorit|民族|人口", re.I)
PARAM_WORDS = re.compile(r"ethnic|demograph|民族", re.I)


def inspect(name: str, title: str, lang: str, wikitext: str, rows_shown: int,
            raw: bool) -> None:
    found = tables_with_context(wikitext)
    log(f"== {name} ([{lang}] {title!r}): {len(found)} tables")
    flagged = 0
    for n, t in enumerate(found):
        if not t["rows"]:
            continue
        flag = is_ethnic_table(t)
        flagged += flag
        log(f"  {'ETHNIC' if flag else '      '} table {n}: {len(t['rows'])} rows; "
            f"section {t['section']!r}; caption {t['caption']!r}; year {year_of(t)}")
        log(f"         header: {[c[:30] for c in t['rows'][0]]}")
        if flag:
            log(f"         prose : {t['prose'][-240:]!r}")
            for row in oriented(t["rows"])[1:1 + rows_shown]:
                log(f"         row   : {[c[:30] for c in row]}")
    if not raw:
        return
    # Infobox parameters about ethnicity, and the demographic sections'
    # own wikitext -- where a composition sits when it is not a table:
    # a chart template, a list, or prose with figures.
    body = REF.sub("", wikitext)
    head, _, rest = body.partition("\n==")
    for line in head.split("\n"):
        if line.lstrip().startswith("|") and PARAM_WORDS.search(line):
            log(f"   infobox: {line.strip()[:300]}")
    for m in re.finditer(r"\n(==+)\s*([^=\n]+?)\s*\1[^\n]*\n(.*?)(?=\n==|\Z)", "\n" + body, re.S):
        heading, text = m.group(2), m.group(3)
        if not SECTION_WORDS.search(heading):
            continue
        log(f"   section {heading!r}:")
        shown = 0
        for line in text.split("\n"):
            s = line.strip()
            if not s or shown >= 45:
                continue
            if flagged and not re.search(r"\d|\{\{|\{\||^\||^!", s):
                continue
            log(f"      {s[:260]}")
            shown += 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", action="append", default=[], metavar="ARTICLE",
                    help="read only these articles (by English title); repeatable")
    ap.add_argument("--lang", default="en", choices=("en", "zh"),
                    help="which edition's article to read")
    ap.add_argument("--inspect", action="store_true",
                    help="print every table of each article -- flagged when it "
                         "names Han and another nationality -- instead of writing")
    ap.add_argument("--raw", action="store_true",
                    help="with --inspect, also print the infobox's ethnicity "
                         "parameters and the demographic sections' wikitext")
    ap.add_argument("--rows", type=int, default=60, help="rows shown per flagged table")
    args = ap.parse_args()

    chosen = [(n, en, zh) for n, en, zh in DIVISIONS if not args.only or en in args.only]
    if args.only and len(chosen) != len(args.only):
        raise SystemExit(f"china_wiki: --only names an article not in DIVISIONS: {args.only}")
    log(f"china_wiki: {len(chosen)} divisions from the {args.lang} Wikipedia "
        f"through the MediaWiki API")
    records, refused = [], []
    for name, en, zh in chosen:
        title = en if args.lang == "en" else zh
        text = fetch(title, args.lang)
        if args.inspect:
            inspect(name, title, args.lang, text, args.rows, args.raw)
            continue
        rec = build_one(name, title, args.lang, text)
        if rec is None:
            refused.append(name)
        else:
            records.append(rec)
    if args.inspect:
        return 0
    log(f"  {len(records)} divisions written, {len(refused)} without a table: {refused}")
    if not records:
        raise SystemExit("china_wiki: nothing read")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
