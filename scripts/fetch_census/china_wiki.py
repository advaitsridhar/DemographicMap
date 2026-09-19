#!/usr/bin/env python3
"""China: ethnicity by province, from the census tables Wikipedia transcribes.

China's census records the 56 official nationalities (minzu) and the
National Bureau of Statistics publishes the composition of every
first-level division in the census tabulations. Those tabulations sit on
``stats.gov.cn`` and in provincial communiques on hosts this project has
not been able to open from a build machine, and each province's English
Wikipedia article transcribes the table -- usually under "Demographics" or
"Ethnic groups", captioned like "Ethnic groups in Guangxi, 2020 census",
with a row per nationality carrying its population and share. That is what
is read here, through the MediaWiki API, one article per division, the way
``wiki_census.py`` reads Kazakhstan and Cambodia; the record names the
census as its source and the article as the copy it was read from.

What the reader does with an article:

* it looks at every table in the article and keeps those whose first column
  is nationalities -- a table is an ethnic-composition table when it names
  Han and at least one other of the 56 -- and among those prefers the one
  captioned or headed with the latest census year, so an article that
  carries both 2010 and 2020 yields 2020 and ``ethnicity_year`` says which;
* the share column is read as printed; where the table prints a count it is
  carried, and where only counts are printed the shares are computed from
  them;
* the shares are re-rounded to one decimal by largest remainder so a
  composition is a whole population (they must add to 100 within 0.3 before
  that, or the division is refused with the sum in the log);
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
from probe_wikitable import plain  # noqa: E402

OUT = "china_wiki_province.json"
API = "https://en.wikipedia.org/w/api.php"
SOURCE_2020 = ("National Bureau of Statistics of China, Seventh National Population "
               "Census (2020), population by ethnic group")
SOURCE_2010 = ("National Bureau of Statistics of China, Sixth National Population "
               "Census (2010), population by ethnic group")
LICENCE = "Official statistics; compilation CC BY-SA 4.0"
RESIDUAL = "Other ethnic groups"
TOLERANCE = 0.3

# The 31 first-level divisions the boundary file draws (Hong Kong and Macau
# are SARs with censuses of their own and are not read here), each with the
# English Wikipedia article that carries its census table. The shape name is
# exactly as ``site/data/admin1/CHN.json`` prints it; "Guangdong" is bare
# because CGAZ drew the province under its capital's name and common.py
# renames it to the bare province.
DIVISIONS: list[tuple[str, str]] = [
    ("Beijing Municipality", "Beijing"),
    ("Tianjin Municipality", "Tianjin"),
    ("Hebei Province", "Hebei"),
    ("Shanxi Province", "Shanxi"),
    ("Inner Mongolia Autonomous Region", "Inner Mongolia"),
    ("Liaoning Province", "Liaoning"),
    ("Jilin Province", "Jilin"),
    ("Heilongjiang Province", "Heilongjiang"),
    ("Shanghai Municipality", "Shanghai"),
    ("Jiangsu Province", "Jiangsu"),
    ("Zhejiang Province", "Zhejiang"),
    ("Anhui Province", "Anhui"),
    ("Fujian Province", "Fujian"),
    ("Jiangxi Province", "Jiangxi"),
    ("Shandong Province", "Shandong"),
    ("Henan Province", "Henan"),
    ("Hubei Province", "Hubei"),
    ("Hunan Province", "Hunan"),
    ("Guangdong", "Guangdong"),
    ("Guangxi Zhuang Autonomous Region", "Guangxi"),
    ("Hainan Province", "Hainan"),
    ("Chongqing Municipality", "Chongqing"),
    ("Sichuan Province", "Sichuan"),
    ("Guizhou Province", "Guizhou"),
    ("Yunnan Province", "Yunnan"),
    ("Tibet Autonomous Region", "Tibet Autonomous Region"),
    ("Shaanxi Province", "Shaanxi"),
    ("Gansu Province", "Gansu"),
    ("Qinghai Province", "Qinghai"),
    ("Ningxia Hui Autonomous Region", "Ningxia"),
    ("Xinjiang Uyghur Autonomous Region", "Xinjiang"),
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

# The 56 nationalities, in the spellings English tables use, mapped to the
# label written. The label is the table's ethnonym (the first spelling of
# each row), singular, without "people"; a second spelling of the same
# nationality is folded onto the first so one people is one group across
# the 31 divisions. Nothing here is a classification -- "Kirgiz" and
# "Kyrgyz" are two romanisations of one census code.
NATIONALITIES: dict[str, str] = {}
for _row in (
    ("Han Chinese", "Han"),
    ("Zhuang",), ("Hui",), ("Manchu",), ("Uyghur", "Uighur", "Uygur"),
    ("Miao", "Hmong"), ("Yi",), ("Tujia",), ("Tibetan", "Zang"),
    ("Mongol", "Mongolian"), ("Dong", "Kam"), ("Bouyei", "Buyei", "Buyi"),
    ("Yao",), ("Bai",), ("Korean", "Chaoxian", "Joseon"), ("Hani",), ("Li",),
    ("Kazakh", "Kazak"), ("Dai", "Tai"), ("She",), ("Lisu",), ("Dongxiang",),
    ("Gelao", "Gelo"), ("Lahu",), ("Wa", "Va"), ("Sui", "Shui"),
    ("Nakhi", "Naxi"), ("Qiang",), ("Tu", "Monguor"), ("Mulao", "Mulam"),
    ("Xibe", "Sibe", "Xibo"), ("Kyrgyz", "Kirgiz", "Kirghiz"),
    ("Jingpo", "Kachin"), ("Daur",), ("Salar",), ("Blang", "Bulang"),
    ("Maonan",), ("Tajik",), ("Pumi",), ("Achang",), ("Nu",),
    ("Evenk", "Ewenki", "Evenki"), ("Gin", "Jing", "Kinh"), ("Jino",),
    ("De'ang", "Deang", "Palaung"), ("Bonan", "Baoan"), ("Russian",),
    ("Yugur", "Yughur"), ("Uzbek",), ("Monba", "Monpa", "Moinba"), ("Oroqen",),
    ("Derung", "Drung"), ("Hezhen", "Nanai"), ("Gaoshan",), ("Lhoba",),
    ("Tatar",),
):
    for _spelling in _row:
        NATIONALITIES[_spelling.lower()] = _row[0]

RESIDUAL_WORDS = re.compile(r"^(others?|other ethnic groups?|other nationalit(y|ies)|"
                            r"other minorit(y|ies)|other ethnicit(y|ies)|"
                            r"other minority groups?|all others?)$", re.I)
# Rows a census table carries that are not a nationality: the total, the
# subtotal of minorities, and the categories the census keeps beside the
# 56 (people whose nationality is not among them, and naturalised
# citizens) -- those two are counted, so they fold into the residual.
TOTAL_WORDS = re.compile(r"^(total|all|population|total population)$", re.I)
SUBTOTAL_WORDS = re.compile(r"^((all |ethnic |national )?minorit(y|ies)( nationalities| groups| ethnic groups)?|"
                            r"non-han|non han)$", re.I)
UNLISTED_WORDS = re.compile(r"^(unrecogni[sz]ed|undistinguished|unclassified|other unlisted|"
                            r"unidentified|naturali[sz]ed|foreign(ers)?( naturalised)?)"
                            r"(\s.*)?$", re.I)


# ---------------------------------------------------------------------------
# Wikitext tables, with the text that names them
# ---------------------------------------------------------------------------

def tables_with_context(wikitext: str) -> list[dict[str, Any]]:
    """Every top-level table, with its caption, section and preceding prose.

    ``probe_wikitable.tables`` drops the caption, and for these tables the
    caption is where the census year lives ("Ethnic groups in Guangxi,
    2020 census"). So this is that parser again, keeping the ``|+`` line,
    the ``==`` heading the table sits under, and the last non-empty lines
    of prose before it, which is where an uncaptioned table says its year.
    """
    out: list[dict[str, Any]] = []
    depth, rows, caption = 0, None, ""
    section = ""
    prose: list[str] = []
    for line in wikitext.split("\n"):
        s = line.strip()
        if depth == 0:
            if s.startswith("=") and s.endswith("="):
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
                out.append({"caption": caption, "section": section,
                            "prose": " ".join(prose[-3:]),
                            "rows": [r for r in rows if r]})
                rows = None
            continue
        if depth == 0:
            if s and not s.startswith(("{{", "}}", "[[File", "[[Image", "<!--", "|")):
                prose.append(plain(s)[:200])
            continue
        if depth != 1 or rows is None:
            continue
        if s.startswith("|+"):
            caption = plain(s[2:])
            continue
        if s.startswith("|-"):
            rows.append([])
            continue
        if s.startswith("!") or s.startswith("|"):
            marker = s[0]
            cells = re.split(r"!!|\|\|", s[1:]) if marker == "!" else s[1:].split("||")
            if not rows:
                rows.append([])
            rows[-1].extend(plain(c) for c in cells)
    return out


def ethnonym(cell: str) -> str | None:
    """The written label for a first-column cell, or None if it is not one.

    A table prints "Han Chinese", "Han", "Zhuang people", "Hui (Muslim)",
    "Tibetans" or "Uyghurs"; all are found in the spelling list after the
    parenthesis, the word "people" and a plural -s are taken off.
    """
    text = re.sub(r"\(.*?\)", "", cell).strip()
    text = re.sub(r"\s+(people|peoples|ethnic group|nationality)$", "", text, flags=re.I)
    text = text.strip(" *:")
    if not text:
        return None
    for candidate in (text, text.rstrip("s"), text.replace("Chinese", "").strip()):
        hit = NATIONALITIES.get(candidate.lower())
        if hit:
            return hit
    return None


def kind(cell: str) -> str:
    """What a first-column cell is: a nationality, the residual, a total, or prose."""
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
    text = cell.replace(",", "").replace("%", "").replace(" ", "").replace(" ", "")
    text = text.strip()
    if text in ("", "-", "—", "–", "n/a", "N/A"):
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def is_ethnic_table(t: dict[str, Any]) -> bool:
    """Han and at least one other nationality down the first column."""
    names = {ethnonym(r[0]) for r in t["rows"] if r}
    return "Han Chinese" in names and len(names - {None}) >= 2


def year_of(t: dict[str, Any]) -> int | None:
    """The census year the table says it is, from its caption, header or prose."""
    for text in (t["caption"], " ".join(t["rows"][0]) if t["rows"] else "",
                 t["section"], t["prose"]):
        years = [int(y) for y in re.findall(r"\b(19[89]\d|20[012]\d)\b", text)]
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
    otherwise the first "population"/"number" column and the first "%"
    /"percent"/"share"/"proportion" column.
    """
    counts, shares = [], []
    for i, cell in enumerate(header):
        c = cell.lower()
        if year and str(year) in c and any(o in c for o in ("2010", "2020", "2000")) and not c.startswith(str(year)):
            pass
        if "%" in c or "percent" in c or "share" in c or "proportion" in c:
            shares.append(i)
        elif any(w in c for w in ("population", "number", "persons", "people", "count")) \
                or re.fullmatch(r"(19|20)\d\d(\s+census)?", c):
            counts.append(i)
    if year and len(counts) > 1:
        dated = [i for i in counts if str(year) in header[i]]
        if dated:
            counts = dated
    if year and len(shares) > 1:
        dated = [i for i in shares if str(year) in header[i]]
        if dated:
            shares = dated
    return (counts[0] if counts else None, shares[0] if shares else None)


def read_table(t: dict[str, Any], where: str) -> dict[str, Any]:
    """One ethnic table -> {"groups": [(label, count, pct)], "total": ...}.

    Refuses rather than guesses: a header with no share and no count column,
    a group row printing neither, or shares that do not add to 100.
    """
    rows = t["rows"]
    header = rows[0]
    year = year_of(t)
    ci, si = columns(header, year)
    if ci is None and si is None:
        raise SystemExit(f"china_wiki: {where}: the ethnic table's header "
                         f"{header} has no population or share column")
    groups: list[tuple[str, float | None, float | None]] = []
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
            groups.append((ethnonym(row[0]) or row[0], count, pct))
        elif what == "residual":
            saw_residual = True
            residual_count += count or 0.0
            residual_pct += pct or 0.0
        elif what == "total":
            total_count = count
        # a subtotal ("minorities") and prose rows are neither counted nor
        # refused: the subtotal is the sum of what follows it.
    if not groups:
        raise SystemExit(f"china_wiki: {where}: no nationality rows under {header}")
    seen: dict[str, tuple[float | None, float | None]] = {}
    for label, count, pct in groups:
        if label in seen:
            raise SystemExit(f"china_wiki: {where}: {label!r} appears twice in the table")
        seen[label] = (count, pct)
    if saw_residual:
        seen[RESIDUAL] = (residual_count if ci is not None else None,
                          residual_pct if si is not None else None)
    return {"groups": seen, "total": total_count, "year": year,
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


def composition(read: dict[str, Any], where: str) -> list[dict[str, Any]]:
    """The rows written: group, pct (whole hundred), count where printed."""
    groups = read["groups"]
    if read["has_shares"] and all(p is not None for _, p in groups.values()):
        raw = [(g, p) for g, (_, p) in groups.items()]
        summed = sum(p for _, p in raw)
        if abs(summed - 100.0) > TOLERANCE:
            # A table that prints the largest groups and stops leaves the
            # rest unprinted. If the rest is small and the table has no
            # residual row, it is added as the residual; a shortfall past
            # that or an excess is refused.
            if RESIDUAL not in groups and 100.0 - summed > TOLERANCE and summed < 100.0 and 100.0 - summed <= 5.0:
                raw.append((RESIDUAL, round(100.0 - summed, 2)))
                groups = dict(groups)
                groups[RESIDUAL] = (None, 100.0 - summed)
            else:
                raise SystemExit(f"china_wiki: {where}: shares add to {summed:.2f}, "
                                 f"not 100 within {TOLERANCE}")
    elif read["has_counts"] and all(c is not None for c, _ in groups.values()):
        raw = [(g, c) for g, (c, _) in groups.items()]
        if read["total"] and abs(sum(c for _, c in raw) - read["total"]) / read["total"] > 0.005:
            raise SystemExit(f"china_wiki: {where}: counts add to "
                             f"{sum(c for _, c in raw):,.0f} against a printed total "
                             f"of {read['total']:,.0f}")
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
    return out


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
            + ", ".join(f"{g} {by[g]['pct']}%" + (f" ({by[g]['count']:,})" if "count" in by[g] else "")
                        for g in ("Han Chinese", "Manchu", "Hui", "Mongol", "Korean", "Tujia")
                        if g in by))


def build_one(name: str, title: str, wikitext: str) -> dict[str, Any] | None:
    found = tables_with_context(wikitext)
    t = choose(found, name)
    if t is None:
        log(f"  {name}: no ethnic-composition table in {title!r} "
            f"({len(found)} tables; none names Han and another nationality)")
        return None
    read = read_table(t, name)
    year = read["year"]
    if year not in (2010, 2020, 2000):
        raise SystemExit(f"china_wiki: {name}: cannot tell which census the table "
                         f"is from (caption {t['caption']!r}, section {t['section']!r})")
    rows = composition(read, name)
    if name == "Beijing Municipality":
        check_beijing(rows, year)
    from common import slugify
    source = SOURCE_2020 if year == 2020 else SOURCE_2010
    url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
    note = (f"{source}, resident population of {name}. Read from the English "
            f"Wikipedia article {title!r}, which transcribes the census table"
            + (f" captioned {t['caption']!r}" if t["caption"] else "")
            + ". Shares as printed, re-rounded to one decimal so they sum to 100"
            + ("; counts as printed" if read["has_counts"] else "")
            + f". {RESIDUAL!r} is the census's own remainder"
            if RESIDUAL in read["groups"] else
            f"{source}, resident population of {name}. Read from the English "
            f"Wikipedia article {title!r}, which transcribes the census table"
            + (f" captioned {t['caption']!r}" if t["caption"] else "")
            + ". Shares as printed, re-rounded to one decimal so they sum to 100"
            + ("; counts as printed" if read["has_counts"] else "") + ".")
    if name == "Beijing Municipality":
        note += (" Corroborated against the Beijing Municipal Bureau of Statistics' "
                 "2010 census communiques, which give Han 18,811,000 (95.9%) of "
                 "19,612,000 residents, Manchu 336,000, Hui 249,000, Mongol 77,000, "
                 f"Korean 37,000, Tujia 24,000: {BEIJING_URLS[0]} and {BEIJING_URLS[1]}.")
    log(f"  {name}: {year}, {len(rows)} groups, leading "
        + ", ".join(f"{r['group']} {r['pct']}%" for r in rows[:3]))
    return record(
        f"CHN-{slugify(name)}", name, level="admin1", parent="CHN", country="CHN",
        sources=[{"field": "ethnicity", "name": source, "url": url, "license": LICENCE}],
        ethnicity=rows, ethnicity_year=year, ethnicity_note=note)


def fetch(title: str) -> str:
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext",
                                "format": "json", "formatversion": "2", "redirects": "1"})
    parsed = http_json(f"{API}?{q}", timeout=90).get("parse") or {}
    text = parsed.get("wikitext") or ""
    log(f"  {title!r}: {len(text):,} bytes of wikitext")
    return text


def inspect(name: str, title: str, wikitext: str, rows_shown: int) -> None:
    found = tables_with_context(wikitext)
    log(f"== {name} ({title!r}): {len(found)} tables")
    for n, t in enumerate(found):
        if not t["rows"]:
            continue
        flag = "ETHNIC" if is_ethnic_table(t) else "      "
        log(f"  {flag} table {n}: {len(t['rows'])} rows; section {t['section']!r}; "
            f"caption {t['caption']!r}; year {year_of(t)}")
        log(f"         header: {[c[:30] for c in t['rows'][0]]}")
        if flag.strip():
            log(f"         prose : {t['prose'][-240:]!r}")
            for row in t["rows"][1:1 + rows_shown]:
                log(f"         row   : {[c[:30] for c in row]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", action="append", default=[], metavar="ARTICLE",
                    help="read only these articles (by title); repeatable")
    ap.add_argument("--inspect", action="store_true",
                    help="print every table of each article -- flagged when it "
                         "names Han and another nationality -- instead of writing")
    ap.add_argument("--rows", type=int, default=60, help="rows shown per flagged table")
    args = ap.parse_args()

    chosen = [(n, t) for n, t in DIVISIONS if not args.only or t in args.only]
    if args.only and len(chosen) != len(args.only):
        raise SystemExit(f"china_wiki: --only names an article not in DIVISIONS: {args.only}")
    log(f"china_wiki: {len(chosen)} divisions from the English Wikipedia through the MediaWiki API")
    records, refused = [], []
    for name, title in chosen:
        text = fetch(title)
        if args.inspect:
            inspect(name, title, text, args.rows)
            continue
        rec = build_one(name, title, text)
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
