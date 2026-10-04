#!/usr/bin/env python3
"""The Netherlands: religion by gemeente, from CBS's 2010-2015 survey table (a survey estimate).

The Netherlands has had no questionnaire census since 1971 and no register
records religion. From 2010 to 2015 CBS asked it in the Labour Force Survey
(Enquête Beroepsbevolking, EBB), whose sample is large enough for gemeenten,
and published the pooled answers by gemeente twice:

* "Religie en kerkbezoek naar gemeente 2010-2014" (maatwerk, 13 May 2015):
  the gemeenten of 2014, about 460,000 adults;
* "Kerkelijke gezindte en kerkbezoek naar gemeenten 2010/2015" (December
  2016), the table behind CBS's paper "De religieuze kaart van Nederland,
  2010-2015" (Hans Schmeets): the gemeenten of 2016, the six years 2010 to
  2015 that "more than 600 thousand" people answered.

The second is newer, larger and drawn on a later division, so it is the one
read; the first is read only to measure the union method below against
CBS's own figures. Both give the share of adults (18 and over, in private
households) who count themselves to a church denomination or
philosophy-of-life group, and which, weighted by CBS; CBS prints a gemeente
only when at least 150 respondents stand behind it, and not the number. Its
later religion surveys (Sociale samenhang en welzijn, about 7,500 a year)
are published by province and COROP region only (``netherlands_religion.py``),
so this is CBS's latest table by gemeente.

**Vintage.** The table counts the gemeenten of 1 January 2016 (390); the map
draws those of 2022 after Weesp joined Amsterdam (344). What happened in
between is CBS's own record, StatLine 70739ned ("Gebieden; overzicht vanaf
1830"), whose explanation of every gemeente lists each merger, dissolution and
boundary change with the inhabitants it moved. Those transfers are followed
from 2016 to 2022, so each drawn gemeente is known as shares of 2016
gemeenten, and

* a gemeente that is one 2016 gemeente takes that gemeente's figure;
* a gemeente that is a union of whole 2016 gemeenten takes their mean,
  weighted by their population aged 18 and over on 1 January 2016 (StatLine
  03759ned), every part resting on CBS's 150 respondents or more
  (``--no-unions`` leaves these out, with a gap saying so);
* a gemeente holding part of a 2016 gemeente that was divided
  (Littenseradiel in 2018, Winsum in 2019 and Haaren in 2021 were shared out
  between several; Slochteren gave 1,033 inhabitants to Groningen in 2017
  before it merged), or that gave or took more than a boundary correction,
  takes nothing, because a gemeente's figure is never split. Its record says
  so, with the transfers, in place of a bare gap; so does a gemeente CBS
  suppressed.

A boundary change moving at most ``TOLERANCE`` (2%) of a gemeente's people is
a correction, not a different unit; every one is named in the log and the
note. ``--tolerance`` sets another share.

**Checks.** The categories make CBS's total within rounding for every
gemeente, the Protestant churches make CBS's Protestant subtotal, and the
religious and the rest make 100; the twelve gemeenten CBS's release of 22
December 2016 printed at 10% Muslims or more are the table's, to the tenth,
and there are no others; the table's gemeenten are 70739ned's of
1 January 2016, by code and name, and their 2016 populations make the
country's; every 2016 gemeente's inhabitants end up in the 2022 gemeenten
exactly once; every transfer a recipient records is the one its donor
records. The gemeenten's estimates, weighted by their adults, land within
``NATIONAL_TOLERANCE`` points of the table's own national row, and within
``PARENT_TOLERANCE`` of CBS's province figures from the same survey (StatLine
83288NED, 2010-2015). And the union method is measured: the 2014 table's
gemeenten, carried to 2016 the same way, land within ``UNION_TOLERANCE``
points of CBS's own figures for the gemeenten merged in 2015 and 2016. A miss
stops the run.

Usage:
    python -m scripts.fetch_census.netherlands_religion_gemeente [--no-unions] [--tolerance 0.02]
"""

from __future__ import annotations

import argparse
import io
import json
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, http_json, log, record, write_json
from .central_ages import SITE, fold, units
from .netherlands_gemeente import read_ages

# Published with the paper in week 51 of 2016: CBS's news release of 22 December 2016
# linked it ("Kerkelijke gezindte en kerkbezoek naar gemeenten"); the release is in the
# Wayback Machine (20161223043731), and the paper's page now links only its PDF.
WORKBOOK = ("https://www.cbs.nl/-/media/_excel/2016/51/"
            "kerkelijke-gezindte-en-kerkbezoek-naar-gemeenten.xlsx")
TITLE = "Kerkelijke gezindte en kerkbezoek naar gemeenten 2010/2015"
NEWS = "https://www.cbs.nl/nl-nl/nieuws/2016/51/helft-nederlanders-is-kerkelijk-of-religieus"
# That release printed every gemeente with at least 10% Muslims over 2010-2015.
MUSLIM_TENTH = {"Leerdam": 18.6, "'s-Gravenhage": 14.7, "Rotterdam": 13.7, "Bergen op Zoom": 13.0,
                "Schiedam": 12.4, "Maassluis": 12.1, "Amsterdam": 12.1, "Tiel": 11.5,
                "Gorinchem": 10.9, "Helmond": 10.5, "Vlaardingen": 10.4, "Gouda": 10.2}
SOURCE = (f"CBS, {TITLE} (December 2016, the table behind De religieuze kaart van Nederland, "
          "2010-2015), from the Enquête Beroepsbevolking")
# The table before it, read only to measure the union method (``check_unions``).
OLD_WORKBOOK = ("https://www.cbs.nl/-/media/imported/documents/2015/20/"
                "religie-en-kerkbezoek-naar-gemeente-2010-2014.xls")
LICENCE = "CC BY 4.0 (CBS)"
OUT = PROCESSED / "netherlands_religion_gemeente_survey.json"
YEAR = 2015
SPAN = "2010-2015"
BASIS = "survey estimate: self-identification, adults 18+ in private households"

HISTORY = "https://opendata.cbs.nl/ODataApi/odata/70739ned/{path}?$format=json"
PROVINCE_TABLE = "https://opendata.cbs.nl/ODataApi/odata/83288NED/{path}?$format=json"
START, STOP = "20160101", "20221231"      # the table's division; the drawn one (after 24 March 2022)
VINTAGE = START[:4]
OLD_START = "20140101"                    # the 2010-2014 table's division
PLACEHOLDERS = {"GM0996", "GM0998", "GM0999"}   # IJsselmeerpolders, abroad, not assigned
AGE_PERIOD, OLD_AGE_PERIOD = "2016JJ00", "2014JJ00"
SURVEY_YEARS = ("2010JJ00", "2011JJ00", "2012JJ00", "2013JJ00", "2014JJ00", "2015JJ00")

# Respondents. The table says only that "more than 600 thousand" answered; the
# paper gives each year's sample, 606,189 in all, and the 2010-2014 table counted
# "circa 460 thousand" adults among the first five years' 508,224. The adults
# among all six are taken in that proportion: about 549,000.
YEARLY_SAMPLE = (108_463, 77_110, 130_529, 98_195, 93_927, 97_965)
OLD_ADULTS = 460_000
RESPONDENTS = int(round(OLD_ADULTS * sum(YEARLY_SAMPLE) / sum(YEARLY_SAMPLE[:5]), -3))
MINIMUM = 150                # the table's "minstens 150 personen per gemeente"
LOW_PRECISION = 300          # BRIEF_EU_SURVEYS: say so below 300 respondents
EXPECTED, OLD_EXPECTED = 390, 403   # gemeenten on 1 January 2016 and 2014
DRAWN = 344
TOLERANCE = 0.02             # a boundary change this small (of either side) is a correction
SUM_TOLERANCE = 0.1          # nine categories at two decimals, against a total at two
OLD_SUM_TOLERANCE = 0.5      # the 2014 table: nine at one decimal, against a total at one
SUBTOTAL_TOLERANCE = 0.05    # CBS's Protestant subtotal and its 100 are formulas
NATIONAL_TOLERANCE = 0.5     # points: the gemeenten against the table's own national row
PARENT_TOLERANCE = 1.5       # points: 18+ pooled against 83288NED's 15+ by year
UNION_TOLERANCE = 3.0        # points: a union of 2014 gemeenten against CBS's figure for it

NO_RELIGION = "No religion"
OTHER = "Other or unspecified religion"
# The map's labels (netherlands_religion.py's where it has one), in the table's order.
LABELS = ("Roman Catholic", "Dutch Reformed", "Reformed (Gereformeerd)",
          "Protestant Church in the Netherlands", "Islam", "Judaism", "Hinduism", "Buddhism", OTHER)
PROTESTANT = ("Dutch Reformed", "Reformed (Gereformeerd)", "Protestant Church in the Netherlands")
# The 2016 workbook's headings (how each begins, lower case) -> the labels.
HEADS = (("rooms-katholiek", "Roman Catholic"), ("nederlands hervormd", "Dutch Reformed"),
         ("gereformeerde kerken", "Reformed (Gereformeerd)"),
         ("protestantse kerk nederland", "Protestant Church in the Netherlands"),
         ("islam", "Islam"), ("joods", "Judaism"), ("hindoe", "Hinduism"),
         ("boeddhist", "Buddhism"), ("anders", OTHER))
TOTAL_HEAD, NONE_HEAD = "wel kerkelijke gezindte", "geen kerkelijke gezindte"
PROTESTANT_HEAD = "protestants"           # CBS's sum of the three Protestant columns
GEMEENTE = re.compile(r"GM\d{4}")
# What the record will say about the table, read from the table.
CLAIMS = (r"2010 tot en met 2015", rf"minstens {MINIMUM} personen per gemeente",
          r"Enqu.te beroepsbevolking", r"18\+ populatie", r"600 duizend personen")
# The 2014 workbook's columns -> the labels.
OLD_COLUMNS = {"Katholiek": "Roman Catholic", "Hervormd": "Dutch Reformed",
               "Gereformeerd": "Reformed (Gereformeerd)",
               "PKN": "Protestant Church in the Netherlands", "Islam": "Islam", "Joods": "Judaism",
               "Hindoe": "Hinduism", "Boeddhist": "Buddhism", "Anders": OTHER}
OLD_TOTAL_HEAD = "Kerkelijke gezindte of"   # "... of levensbeschouwelijke groepering", not the title
OLD_CLAIMS = (r"Gemeentelijke indeling 2014", rf"minimaal {MINIMUM} waarnemingen",
              r"460 duizend volwassen personen \(18 jaar of ouder\)", r"Enqu.te Beroepsbevolking")
# 83288NED's measures, as sums of the labels, for the parent check.
PROVINCE_MEASURES = {
    "TotaalKerkelijkeGezindte_2": ("total",), "RoomsKatholiek_3": ("Roman Catholic",),
    "ProtestantseKerkInNederland_4": ("Protestant Church in the Netherlands",),
    "NederlandsHervormd_5": ("Dutch Reformed",), "Gereformeerd_6": ("Reformed (Gereformeerd)",),
    "Islam_7": ("Islam",), "OverigeGezindte_8": ("Judaism", "Hinduism", "Buddhism", OTHER),
}
PROVINCE_NAMES = {"Fryslân": "Friesland"}   # 70739ned's spelling -> 83288NED's


# ---------------------------------------------------------------------------
# The tables
# ---------------------------------------------------------------------------

def cell_text(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split())


def number(value: Any) -> float | None:
    """A share, or None where CBS printed "." (too few respondents)."""
    text = cell_text(value)
    if text in (".", ""):
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        raise SystemExit(f"netherlands_religion_gemeente: {text!r} is not a share")


def gemeente_code(value: Any) -> str:
    text = cell_text(value)
    if not re.fullmatch(r"\d+(?:\.0+)?", text):
        raise SystemExit(f"netherlands_religion_gemeente: gemeente code {text!r}")
    return f"GM{int(float(text)):04d}"


def listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"


def header_columns(head_rows: list[list[str]]) -> dict[str, int]:
    """{label, "total", "none" or "protestant": column} from the rows above the
    first gemeente: each heading found exactly once, wherever its row."""
    column: dict[str, int] = {}

    def put(key: str, at: int) -> None:
        if key in column:
            raise SystemExit(f"netherlands_religion_gemeente: two columns headed {key!r}")
        column[key] = at

    for row in head_rows:
        for at, text in enumerate(row):
            key = " ".join(text.lower().split())
            for start, label in HEADS:
                if key.startswith(start):
                    put(label, at)
            if key.startswith(TOTAL_HEAD):
                put("total", at)
            elif key.startswith(NONE_HEAD):
                put("none", at)
            elif key == PROTESTANT_HEAD:
                put("protestant", at)
    missing = [k for k in (*LABELS, "total", "none", "protestant") if k not in column]
    if missing:
        raise SystemExit(f"netherlands_religion_gemeente: no column headed {missing}")
    return column


def read_row(row: list[Any], column: dict[str, int], name: str) -> dict[str, Any]:
    total, none = number(row[column["total"]]), number(row[column["none"]])
    parts = {label: number(row[column[label]]) for label in LABELS}
    if total is None:
        # CBS's Protestant subtotal is a formula, and reads 0 where its terms are ".".
        if none is not None or any(v is not None for v in parts.values()):
            raise SystemExit(f"netherlands_religion_gemeente: {name}: no total but shares")
        return {"name": name, "total": None, "none": None, "parts": {}, "protestant": None}
    protestant = number(row[column["protestant"]])
    if none is None or protestant is None or any(v is None for v in parts.values()):
        raise SystemExit(f"netherlands_religion_gemeente: {name}: a total but a share missing")
    return {"name": name, "total": total, "none": none, "parts": parts, "protestant": protestant}


def parse_table(rows: list[list[Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """({GM code: {name, total, none, parts{label: share}, protestant}}, the national row)
    from the 2016 workbook's sheet; a gemeente CBS suppressed has total None and no parts.

    The headings are found, not assumed: they sit on three rows above the first
    gemeente, which is the first row opening with a GM code.
    """
    texts = [[cell_text(c) for c in row] for row in rows]
    first = next((i for i, t in enumerate(texts) if t and GEMEENTE.fullmatch(t[0])), None)
    if first is None:
        raise SystemExit("netherlands_religion_gemeente: no row opens with a gemeente code")
    column = header_columns(texts[:first])
    width = max(column.values()) + 1
    national: dict[str, Any] | None = None
    out: dict[str, dict[str, Any]] = {}
    for at, (row, text) in enumerate(zip(rows, texts)):
        if len(text) < width:
            continue
        if at < first:
            if len(text) > 1 and text[1].lower().startswith("nederland"):
                national = read_row(row, column, text[1])
            continue
        if not GEMEENTE.fullmatch(text[0]):
            continue
        code = text[0]
        if text[2] and gemeente_code(text[2]) != code:
            raise SystemExit(f"netherlands_religion_gemeente: {text[1]}: codes {code} and {text[2]}")
        if code in out:
            raise SystemExit(f"netherlands_religion_gemeente: {code} appears twice")
        out[code] = read_row(row, column, text[1])
    if national is None or national["total"] is None:
        raise SystemExit("netherlands_religion_gemeente: no national row above the gemeenten")
    return out, national


def parse_table_2014(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """{GM code: {name, province, total, parts{label: share}}} from the 2010-2014
    table's sheet; a gemeente CBS suppressed has total None and no parts.

    The header is found, not assumed: the row naming every category, the row
    above it naming the total, and the row naming the gemeente columns.
    """
    texts = [[cell_text(c) for c in row] for row in rows]
    labels_at = next((i for i, row in enumerate(texts) if all(k in row for k in OLD_COLUMNS)), None)
    if labels_at is None:
        raise SystemExit("netherlands_religion_gemeente: no row names the nine categories (2014)")
    column = {k: texts[labels_at].index(k) for k in OLD_COLUMNS}
    total_at = next((j for i in range(labels_at) for j, c in enumerate(texts[i])
                     if c.startswith(OLD_TOTAL_HEAD)), None)
    head_at = next((i for i, row in enumerate(texts) if "Gemeente" in row and "Gemcode" in row), None)
    if total_at is None or head_at is None:
        raise SystemExit("netherlands_religion_gemeente: the 2014 total or gemeente columns are missing")
    head = texts[head_at]
    at_province, at_name, at_code = head.index("Provincie"), head.index("Gemeente"), head.index("Gemcode")
    out: dict[str, dict[str, Any]] = {}
    for row, text in zip(rows[head_at + 1:], texts[head_at + 1:]):
        if len(text) <= max(column.values()) or not text[at_name] or not text[at_code]:
            continue
        code = gemeente_code(row[at_code])
        total = number(row[total_at])
        parts = {OLD_COLUMNS[k]: number(row[i]) for k, i in column.items()}
        if total is None:
            if any(v is not None for v in parts.values()):
                raise SystemExit(f"netherlands_religion_gemeente: {text[at_name]}: no total but shares")
            parts = {}
        elif any(v is None for v in parts.values()):
            raise SystemExit(f"netherlands_religion_gemeente: {text[at_name]}: a total but a share "
                             f"missing")
        if code in out:
            raise SystemExit(f"netherlands_religion_gemeente: {code} appears twice")
        out[code] = {"name": text[at_name], "province": text[at_province], "total": total,
                     "parts": parts}
    return out


def check_table(table: dict[str, dict[str, Any]], tolerance: float = SUM_TOLERANCE) -> None:
    """Every share a share, the categories make the total, and -- where the
    table gives them -- the religious and the rest make 100 and the
    Protestant churches make CBS's Protestant subtotal."""
    worst = Counter()
    where: dict[str, str] = {}

    def note(kind: str, value: float, name: str, limit: float, text: str) -> None:
        if value > limit:
            raise SystemExit(f"netherlands_religion_gemeente: {name}: {text}")
        if value >= worst[kind]:
            worst[kind], where[kind] = value, name

    for code, g in table.items():
        if g["total"] is None:
            continue
        values = [g["total"], *g["parts"].values()]
        if g.get("none") is not None:
            values.append(g["none"])
        if any(v < 0 or v > 100 for v in values):
            raise SystemExit(f"netherlands_religion_gemeente: {g['name']}: a share outside 0-100")
        made = sum(g["parts"].values())
        note("categories", abs(made - g["total"]), f"{g['name']} ({code})", tolerance,
             f"the categories make {made:.2f}, the total is {g['total']}")
        if g.get("none") is not None:
            note("hundred", abs(g["none"] + g["total"] - 100), g["name"], SUBTOTAL_TOLERANCE,
                 f"religious {g['total']} and none {g['none']} do not make 100")
        if g.get("protestant") is not None:
            churches = sum(g["parts"][k] for k in PROTESTANT)
            note("protestant", abs(churches - g["protestant"]), g["name"], SUBTOTAL_TOLERANCE,
                 f"the Protestant churches make {churches:.2f}, CBS's subtotal is {g['protestant']}")
    log("  " + "; ".join(f"{kind}: largest difference {worst[kind]:.2f} ({where[kind]})"
                         for kind in worst))


def check_release(table: dict[str, dict[str, Any]], printed: dict[str, float] = MUSLIM_TENTH) -> None:
    """The table against what CBS's release printed from it: the gemeenten
    with at least 10% Muslims, each to the tenth, and no others."""
    islam = {fold(g["name"]): (g["name"], g["parts"]["Islam"]) for g in table.values()
             if g["total"] is not None}
    wrong = [f"{name}: the table {islam[fold(name)][1] if fold(name) in islam else 'nothing'}, "
             f"the release {value}" for name, value in printed.items()
             if fold(name) not in islam or abs(islam[fold(name)][1] - value) > 0.051]
    listed_ = {fold(name) for name in printed}
    unlisted = sorted(f"{name} {share_:.2f}" for key, (name, share_) in islam.items()
                      if share_ >= 9.95 and key not in listed_)
    if wrong or unlisted:
        raise SystemExit(f"netherlands_religion_gemeente: the table and CBS's release of 22 December "
                         f"2016 differ: {wrong}; at 10% Muslims or more but not in the release: "
                         f"{unlisted}")
    log(f"  the {len(printed)} gemeenten CBS's release printed at 10% Muslims or more: the table "
        f"gives each to the tenth, and no other")


def workbook_rows(blob: bytes) -> dict[str, list[list[Any]]]:
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in book.worksheets}


def read_table() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    sheets = workbook_rows(http_get(WORKBOOK, binary=True, timeout=300))
    notes = " ".join(cell_text(c) for rows in sheets.values() for row in rows for c in row
                     if isinstance(c, str))
    for claim in CLAIMS:
        if not re.search(claim, notes):
            raise SystemExit(f"netherlands_religion_gemeente: the workbook no longer says {claim!r}")
    if TITLE not in notes:
        raise SystemExit(f"netherlands_religion_gemeente: the workbook is no longer titled {TITLE!r}")
    found = [rows for rows in sheets.values()
             if any(row and GEMEENTE.fullmatch(cell_text(row[0])) for row in rows)]
    if len(found) != 1:
        raise SystemExit(f"netherlands_religion_gemeente: {len(found)} sheets list gemeenten")
    return parse_table(found[0])


def read_table_2014() -> dict[str, dict[str, Any]]:
    import xlrd
    book = xlrd.open_workbook(file_contents=http_get(OLD_WORKBOOK, binary=True, timeout=300))
    sheet = book.sheet_by_name("Tabel")
    rows = [sheet.row_values(r) for r in range(sheet.nrows)]
    notes = " ".join(cell_text(c) for row in rows for c in row if isinstance(c, str))
    notes += " " + " ".join(cell_text(c) for r in range(book.sheet_by_name("Toelichting").nrows)
                            for c in book.sheet_by_name("Toelichting").row_values(r))
    for claim in OLD_CLAIMS:
        if not re.search(claim, notes):
            raise SystemExit(f"netherlands_religion_gemeente: the 2014 workbook no longer says {claim!r}")
    return parse_table_2014(rows)


# ---------------------------------------------------------------------------
# CBS's record of gemeente changes (70739ned)
# ---------------------------------------------------------------------------

@dataclass
class Event:
    kind: str
    date: str                     # yyyymmdd
    direction: str                # out, in, renamed_to, renamed_from, other
    entries: list[tuple[str, str, int | None]] = field(default_factory=list)  # (name, code, inhabitants)


# Any kind CBS writes ("Opgeheven", "Grenswijziging", "Gemeentelijke herindeling",
# "Naamswijziging", "Ontstaan", ...), so that one not listed cannot run on into
# the event before it; only "Opgeheven" is read as an end.
EVENT = re.compile(r"([A-Z][a-z]+(?:\s[a-z]+)?)\s+per\s+(\d{2})-(\d{2})-(\d{4})")
DIRECTIONS = (("overgegaan naar", "out"), ("ontvangen van", "in"),
              ("nieuwe naam", "renamed_to"), ("oude naam", "renamed_from"))


def parse_events(description: str) -> list[Event]:
    """A 70739ned explanation as its events, newest first as CBS writes them."""
    text = " ".join(str(description or "").split())
    marks = list(EVENT.finditer(text))
    events = []
    for n, m in enumerate(marks):
        body = text[m.end(): marks[n + 1].start() if n + 1 < len(marks) else len(text)]
        body = re.split(r"\s+Begindatum\b", body)[0]
        direction = "other"
        for phrase, name in DIRECTIONS:
            if re.match(rf"\s*,?\s*{phrase}\s*:", body):
                direction = name
                break
        event = Event(m.group(1), f"{m.group(4)}{m.group(3)}{m.group(2)}", direction)
        if direction in ("renamed_to", "renamed_from"):
            hit = re.search(r":\s*(.+?)\s*\((GM\d{4})\)", body)
            if hit:
                event.entries.append((hit.group(1), hit.group(2), None))
        elif direction in ("out", "in"):
            for piece in re.split(r"(?:^|\s)-\s+", body.split(":", 1)[1] if ":" in body else body):
                hit = re.search(r"^(.+?)\s*\((GM\d{4})\)", piece.strip())
                if not hit:
                    continue
                people = re.search(r"(\d+)\s+inwoners?\b", piece)
                event.entries.append((hit.group(1).strip(), hit.group(2),
                                      int(people.group(1)) if people else None))
        events.append(event)
    return events


def odata_rows(url: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    next_url: str | None = url
    while next_url:
        payload = http_json(next_url, timeout=300)
        out += payload.get("value", [])
        next_url = payload.get("odata.nextLink")
    return out


def read_history() -> dict[str, dict[str, Any]]:
    """{GM code: {title, begin, end, province, events}} for every gemeente since 1830."""
    described = {r["Key"].strip(): r for r in odata_rows(HISTORY.format(path="RegioS"))}
    out: dict[str, dict[str, Any]] = {}
    for r in odata_rows(HISTORY.format(path="TypedDataSet")):
        code = str(r.get("RegioS") or "").strip()
        if not code.startswith("GM"):
            continue
        meta = described.get(code, {})
        out[code] = {"title": cell_text(meta.get("Title")),
                     "begin": cell_text(r.get("BegindatumSorteerveld_6")),
                     "end": cell_text(r.get("EinddatumSorteerveld_7")),
                     "province": cell_text(r.get("Provincie_4")),
                     "events": parse_events(meta.get("Description") or "")}
    return out


def in_being(history: dict[str, dict[str, Any]], day: str) -> set[str]:
    return {c for c, g in history.items() if c not in PLACEHOLDERS
            and g["begin"] <= day and (not g["end"] or g["end"] > day)}


@dataclass
class Transfer:
    day: str
    donor: str
    to: str
    people: int
    kind: str


@dataclass
class Crosswalk:
    content: dict[str, Counter]       # code in being on the stop date -> {start code: share of it}
    identity: dict[str, Counter]      # the same for every code's own territory -> {code: share of it}
    transfers: list[Transfer]         # every transfer of people followed, in order


def follow(history: dict[str, dict[str, Any]], population: dict[str, float],
           start: str = START, stop: str = STOP) -> Crosswalk:
    """Each gemeente in being on ``stop`` as shares of the gemeenten of ``start``.

    The donors' records are followed in date order: a dissolution hands its
    territory to its successors in proportion to the inhabitants CBS says went
    to each, a boundary change moves the share of the donor's people it names,
    a change of name moves everything. ``population`` (people on the start
    date, by code) sizes a donor for its boundary changes. The same moves are
    applied to every code's own territory, so that where each one ended up is
    known too. The recipients' records are checked against the donors', and
    every start gemeente must end up placed exactly once.
    """
    first = in_being(history, start)
    content: dict[str, Counter] = {c: Counter({c: 1.0}) for c in first}
    touched = {c for c, g in history.items()
               if g["begin"] <= stop and (not g["end"] or g["end"] > start)}
    identity: dict[str, Counter] = {c: Counter({c: 1.0}) for c in touched}
    moves: dict[str, list[tuple[str, str, str, Event]]] = {}
    received: list[tuple[str, str, str, int | None]] = []
    for code, g in history.items():
        for e in g["events"]:
            if not (start < e.date <= stop):
                continue
            if e.direction in ("out", "renamed_to"):
                moves.setdefault(e.date, []).append((e.kind, code, e.direction, e))
            elif e.direction == "in":
                received += [(e.date, code, donor, people) for _, donor, people in e.entries]

    def size(code: str) -> float:
        return sum(f * population.get(i, 0.0) for i, f in content.get(code, Counter()).items())

    def move(source: str, target: str, part: float, *, empty: bool = False) -> None:
        for state in (content, identity):
            here = state.setdefault(source, Counter())
            there = state.setdefault(target, Counter())
            for i, f in list(here.items()):
                there[i] += f * part
                here[i] = 0.0 if empty else f * (1 - part)
            if empty:
                state.pop(source, None)

    sent = Counter()
    transfers: list[Transfer] = []
    order = {"Grenswijziging": 0, "Wijziging": 0, "Opgeheven": 1, "Naamswijziging": 2}
    for day in sorted(moves):
        for kind, code, direction, e in sorted(moves[day], key=lambda t: (order.get(t[0], 1), t[1])):
            if direction == "renamed_to":
                for _, new, _ in e.entries:
                    move(code, new, 1.0, empty=True)
                continue
            if any(people is None for *_, people in e.entries):
                raise SystemExit(f"netherlands_religion_gemeente: {code} {kind} {day}: a transfer "
                                 f"without its inhabitants")
            for _, to, people in e.entries:
                sent[(day, code, to)] += people
                if people:
                    transfers.append(Transfer(day, code, to, people, kind))
            if kind == "Opgeheven":
                whole = sum(people for *_, people in e.entries)
                if whole <= 0:
                    raise SystemExit(f"netherlands_religion_gemeente: {code} dissolved with nobody")
                if history[code]["end"] != day:
                    raise SystemExit(f"netherlands_religion_gemeente: {code} dissolved on {day} but "
                                     f"ends {history[code]['end']}")
                kept = {s: Counter(state.get(code, Counter())) for s, state in
                        (("content", content), ("identity", identity))}
                for _, to, people in e.entries:
                    for name, state in (("content", content), ("identity", identity)):
                        there = state.setdefault(to, Counter())
                        for i, f in kept[name].items():
                            there[i] += f * people / whole
                content.pop(code, None)
                identity.pop(code, None)
            else:
                for _, to, people in e.entries:
                    if not people:
                        continue
                    donor = size(code)
                    part = people / donor if donor else 1.0
                    if part > 1:
                        raise SystemExit(f"netherlands_religion_gemeente: {code} gives {people} of "
                                         f"{donor:,.0f} on {day}")
                    move(code, to, part)
    # The recipients' records must be the donors', both ways.
    got = Counter()
    for day, to, donor, people in received:
        if donor == to:
            continue
        got[(day, donor, to)] += people if people is not None else 0
        if sent.get((day, donor, to)) != people:
            raise SystemExit(f"netherlands_religion_gemeente: {to} records {people} inhabitants from "
                             f"{donor} on {day}, {donor} records {sent.get((day, donor, to))}")
    unrecorded = [f"{donor}->{to} {day} ({people})" for (day, donor, to), people in sent.items()
                  if people and to not in PLACEHOLDERS and (day, donor, to) not in got]
    if unrecorded:
        raise SystemExit(f"netherlands_religion_gemeente: transfers the recipient does not record: "
                         f"{unrecorded}")
    last = in_being(history, stop)
    stray = sorted(c for c in content if c not in last and c not in PLACEHOLDERS
                   and any(f > 1e-9 for f in content[c].values()))
    if stray:
        raise SystemExit(f"netherlands_religion_gemeente: territory left on gemeenten not in being "
                         f"on {stop}: {stray}")
    for i in first:
        placed = sum(content[c].get(i, 0.0) for c in content if c in last or c in PLACEHOLDERS)
        if abs(placed - 1.0) > 1e-6:
            raise SystemExit(f"netherlands_religion_gemeente: {i} is placed {placed:.4f} times")
    return Crosswalk({c: content.get(c, Counter()) for c in last},
                     {c: identity.get(c, Counter()) for c in last}, transfers)


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def composition(parts: dict[str, float], total: float) -> list[dict[str, Any]]:
    """The map's rows: each category, "No religion" as the rest; zeros left out."""
    rows = dict(parts)
    rows[NO_RELIGION] = 100.0 - total
    out = [{"group": g, "pct": round(v, 1)} for g, v in rows.items() if round(v, 1) > 0]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    if abs(sum(r["pct"] for r in out) - 100.0) > 1.0:
        raise SystemExit(f"netherlands_religion_gemeente: shares make {sum(r['pct'] for r in out):.1f}")
    return out


def blend(table: dict[str, dict[str, Any]], weights: dict[str, float]) -> tuple[float, dict[str, float]]:
    """The weighted mean of several gemeenten's total and categories."""
    whole = sum(weights.values())
    total = sum(table[i]["total"] * w for i, w in weights.items()) / whole
    parts = {k: sum(table[i]["parts"][k] * w for i, w in weights.items()) / whole for k in LABELS}
    return total, parts


@dataclass
class Unit:
    code: str                          # the drawn gemeente's CBS code
    whole: dict[str, float]            # start gemeenten (nearly) wholly in it -> the share it holds
    foreign: dict[str, float]          # parts of other start gemeenten -> the share it holds
    moved: float                       # share of its people (start terms) not from its whole parts,
                                       # or lost by them -- the larger
    events: list[str]                  # the transfers that touched it, in words
    reason: str | None                 # why it takes no figure, or None
    kind: str = ""                     # "changed", "suppressed" or "union" when it takes none


def share(x: float) -> str:
    return "less than 0.1%" if x < 0.0005 else f"{100 * x:.1f}%"


def say_day(day: str) -> str:
    months = ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]
    return f"{int(day[6:])} {months[int(day[4:6]) - 1]} {day[:4]}"


def classify(code: str, walk: Crosswalk, population: dict[str, float],
             table: dict[str, dict[str, Any]], titles: dict[str, str],
             tolerance: float = TOLERANCE, unions: bool = True, vintage: str = VINTAGE,
             span: str = SPAN) -> Unit:
    """Whether the drawn gemeente ``code`` is a gemeente of the table's
    vintage, or a union of whole ones, to within ``tolerance`` of its people
    either way; ``unions`` False takes only the first."""
    held = {i: f for i, f in walk.content[code].items() if f > 1e-9}
    people = {i: f * population[i] for i, f in held.items()}
    total = sum(people.values())
    whole = {i: f for i, f in held.items() if f >= 1 - tolerance}
    foreign = {i: f for i, f in held.items() if i not in whole}
    gained = sum(people[i] for i in foreign) / total if total else 1.0
    lost = max((1 - f for f in whole.values()), default=0.0)
    # This gemeente's own line: itself, and every code whose territory is all here.
    line = {code} | {c for c, f in walk.identity[code].items() if f >= 1 - tolerance}
    events: list[str] = []
    dissolved: set[str] = set()               # gemeenten dissolved into it, not wholly
    for t in walk.transfers:
        a, b, day = titles.get(t.donor, t.donor), titles.get(t.to, t.to), say_day(t.day)
        if t.to in line and t.donor not in line:
            if t.kind == "Opgeheven":
                events.append(f"it received {t.people:,} of the inhabitants of {a} when {a} was "
                              f"dissolved on {day}")
                dissolved.add(t.donor)
            else:
                events.append(f"it received {t.people:,} inhabitants from {a} on {day}")
        elif t.donor in line and t.to not in line:
            who = "it" if t.donor == code else f"{a}, now part of it,"
            events.append(f"{who} gave {t.people:,} inhabitants to {b} on {day}")
    # Where the rest of a dissolved gemeente it took part of went, then or before.
    for t in walk.transfers:
        if t.donor in dissolved and t.to not in line:
            events.append(f"{titles.get(t.donor, t.donor)} gave {t.people:,} inhabitants to "
                          f"{titles.get(t.to, t.to)} on {say_day(t.day)}")
    events = list(dict.fromkeys(events))
    moved = max(gained, lost)
    if gained > tolerance or not whole:
        return Unit(code, whole, foreign, moved, events, (
            f"is not a {vintage} gemeente or a union of whole ones: since {vintage}, "
            f"{'; '.join(events) or f'it holds only parts of {vintage} gemeenten'} (CBS StatLine "
            f"70739ned) -- {share(moved)} of its people, more than the {100 * tolerance:.0f}% a "
            f"boundary correction may move -- and a gemeente's figure is never split"), "changed")
    names = sorted(table[i]["name"] for i in whole)
    dark = sorted(table[i]["name"] for i in whole if table[i]["total"] is None)
    if dark:
        if len(names) > 1:
            text = (f"covers what in {vintage} were the gemeenten {listed(names)}, and CBS printed "
                    f"no figure for {' or '.join(dark)}, with fewer than {MINIMUM} respondents in "
                    f"{span}, so their union has none")
        else:
            text = (f"is the gemeente of {vintage}, for which CBS printed no figure: it had fewer "
                    f"than {MINIMUM} respondents in {span}")
        return Unit(code, whole, foreign, moved, events, text, "suppressed")
    if not unions and len(whole) > 1:
        return Unit(code, whole, foreign, moved, events, (
            f"covers what in {vintage} were the gemeenten {listed(names)}; CBS printed a figure for "
            f"each but none for their union, and this reading carries a figure to a drawn gemeente "
            f"only from one gemeente of {vintage}"), "union")
    return Unit(code, whole, foreign, moved, events, None)


# ---------------------------------------------------------------------------
# Checks against CBS's own aggregates
# ---------------------------------------------------------------------------

def measure(g: dict[str, Any], columns: tuple[str, ...]) -> float:
    return sum(g["total"] if k == "total" else g["parts"][k] for k in columns)


def weighted(table: dict[str, dict[str, Any]], adults: dict[str, float], codes: Iterable[str],
             columns: tuple[str, ...]) -> float:
    codes = list(codes)
    return sum(adults[c] * measure(table[c], columns) for c in codes) / sum(adults[c] for c in codes)


def check_national(table: dict[str, dict[str, Any]], adults: dict[str, float],
                   national: dict[str, Any], tolerance: float = NATIONAL_TOLERANCE) -> float:
    """The printed gemeenten, weighted by their adults, against the table's own
    national row: the religious and every category. Returns the largest gap."""
    printed = [c for c, g in table.items() if g["total"] is not None]
    worst = (0.0, "")
    for columns in [("total",), *((k,) for k in LABELS)]:
        mine = weighted(table, adults, printed, columns)
        theirs = measure(national, columns)
        if abs(mine - theirs) > tolerance:
            raise SystemExit(f"netherlands_religion_gemeente: {columns[0]}: the gemeenten make "
                             f"{mine:.2f}, the table's national row {theirs:.2f}")
        if abs(mine - theirs) >= worst[0]:
            worst = (abs(mine - theirs), f"{columns[0]} {mine:.2f} / {theirs:.2f}")
    log(f"  gemeenten against the table's national row: largest difference {worst[0]:.2f} points "
        f"({worst[1]})")
    return worst[0]


def province_means() -> dict[str, dict[str, float]]:
    """{region title without "(PV)": {measure: mean 2010-2015}} from 83288NED."""
    titles = {r["Key"].strip(): re.sub(r"\s*\(PV\)\s*$", "", cell_text(r["Title"]))
              for r in odata_rows(PROVINCE_TABLE.format(path="RegioS"))}
    sums: dict[str, Counter] = {}
    counts: dict[str, Counter] = {}
    for r in odata_rows(PROVINCE_TABLE.format(path="TypedDataSet")):
        key, period = r["RegioS"].strip(), r["Perioden"].strip()
        if period not in SURVEY_YEARS or not (key.startswith("PV") or key == "NL01"):
            continue
        for name in PROVINCE_MEASURES:
            if r.get(name) is not None:
                sums.setdefault(titles[key], Counter())[name] += float(r[name])
                counts.setdefault(titles[key], Counter())[name] += 1
    return {region: {m: sums[region][m] / counts[region][m] for m in sums[region]
                     if counts[region][m] == len(SURVEY_YEARS)} for region in sums}


def check_parents(table: dict[str, dict[str, Any]], adults: dict[str, float],
                  provinces: dict[str, str], published: dict[str, dict[str, float]]) -> None:
    """The gemeenten's estimates, weighted by their adults, against CBS's own
    province and national figures from the same survey and years."""
    groups: dict[str, list[str]] = {}
    for code, g in table.items():
        if g["total"] is not None:
            groups.setdefault(provinces[code], []).append(code)
            groups.setdefault("Nederland", []).append(code)
    if set(groups) - set(published):
        raise SystemExit(f"netherlands_religion_gemeente: no CBS figure for "
                         f"{sorted(set(groups) - set(published))}")
    worst = (0.0, "")
    for region, codes in sorted(groups.items()):
        for name, columns in PROVINCE_MEASURES.items():
            mine = weighted(table, adults, codes, columns)
            theirs = published[region].get(name)
            if theirs is None:
                raise SystemExit(f"netherlands_religion_gemeente: 83288NED lacks {name} for {region}")
            if abs(mine - theirs) > PARENT_TOLERANCE:
                raise SystemExit(f"netherlands_religion_gemeente: {region} {name}: the gemeenten "
                                 f"make {mine:.1f}, CBS publishes {theirs:.1f} (2010-2015 mean)")
            if abs(mine - theirs) > worst[0]:
                worst = (abs(mine - theirs), f"{region} {name} {mine:.1f} / {theirs:.1f}")
        log(f"  {region}: {len(codes)} gemeenten, religious "
            f"{weighted(table, adults, codes, ('total',)):.1f}% against CBS's "
            f"{published[region]['TotaalKerkelijkeGezindte_2']:.1f}%")
    log(f"  gemeenten against CBS's provinces and country (83288NED, 15+): largest difference "
        f"{worst[0]:.2f} points ({worst[1]})")


def gap_of(table: dict[str, dict[str, Any]], code: str, total: float,
           parts: dict[str, float]) -> float:
    """The largest difference, in points, between an estimate and the table's row."""
    g = table[code]
    return max(abs(total - g["total"]), *(abs(parts[k] - g["parts"][k]) for k in LABELS))


def compare_unions(old: dict[str, dict[str, Any]], walk: Crosswalk, population: dict[str, float],
                   adults: dict[str, float], table: dict[str, dict[str, Any]],
                   titles: dict[str, str]) -> tuple[list[tuple[float, str, int]],
                                                    list[tuple[float, str, int]]]:
    """The 2014 table carried to the table's gemeenten by the union method,
    against CBS's own figure for each: ([(largest gap, name, parts)] for the
    unions, [...] for the gemeenten that are one gemeente of 2014)."""
    unions, same = [], []
    for code in sorted(walk.content):
        if code not in table or table[code]["total"] is None:
            continue
        unit = classify(code, walk, population, old, titles, vintage=OLD_START[:4],
                        span="2010-2014")
        if unit.reason:
            continue
        weights = {i: adults[i] * f for i, f in unit.whole.items()}
        total, parts = blend(old, weights)
        row = (gap_of(table, code, total, parts), table[code]["name"], len(unit.whole))
        (unions if len(unit.whole) > 1 else same).append(row)
    return unions, same


def check_unions(history: dict[str, dict[str, Any]], table: dict[str, dict[str, Any]],
                 tolerance: float = UNION_TOLERANCE) -> None:
    """The union method, measured: the 2010-2014 table's gemeenten, carried to
    the gemeenten of 2016 as this reader carries 2016 to 2022 (the adult-weighted
    mean of whole parts), against CBS's own 2010-2015 figures for the gemeenten
    merged in 2015 and 2016. The gemeenten that did not change show what a
    sixth year alone moves."""
    old = read_table_2014()
    if len(old) != OLD_EXPECTED:
        raise SystemExit(f"netherlands_religion_gemeente: the 2014 table has {len(old)} gemeenten")
    check_table(old, OLD_SUM_TOLERANCE)
    if in_being(history, OLD_START) != set(old):
        raise SystemExit("netherlands_religion_gemeente: 70739ned's gemeenten of 2014 differ from "
                         "the 2014 table's")
    ages = read_ages(sorted(old), period=OLD_AGE_PERIOD)
    population = {c: float(ages[c]["total"]) for c in old}
    adults = {c: float(sum(n for a, n in ages[c]["m"].items() if a >= 18)
                       + sum(n for a, n in ages[c]["f"].items() if a >= 18)) for c in old}
    walk = follow(history, population, OLD_START, START)
    titles = {c: plain(g["title"]) for c, g in history.items()}
    unions, same = compare_unions(old, walk, population, adults, table, titles)
    if not unions:
        raise SystemExit("netherlands_religion_gemeente: no union of 2014 gemeenten to measure")
    for gap_, name, parts in sorted(unions, key=lambda r: r[1]):
        log(f"  union of {parts} gemeenten of 2014 against CBS's own figure for {name}: largest "
            f"difference {gap_:.2f} points")
    gaps = sorted(g for g, *_ in same)
    log(f"  the {len(same)} gemeenten that are one gemeente of 2014, the same way: median "
        f"{statistics.median(gaps):.2f}, 95th percentile {gaps[int(0.95 * (len(gaps) - 1))]:.2f}, "
        f"largest {gaps[-1]:.2f} points ({max(same)[1]})")
    bad = [f"{name} {gap_:.2f}" for gap_, name, _ in unions if gap_ > tolerance]
    if bad:
        raise SystemExit(f"netherlands_religion_gemeente: unions of 2014 gemeenten miss CBS's own "
                         f"figures by more than {tolerance} points: {bad}")


def low_precision_cut(table: dict[str, dict[str, Any]], adults: dict[str, float],
                      rate: float) -> float:
    """The estimated respondents below which a note says "low precision": 300,
    raised by as much as the national rate overestimates the gemeenten CBS
    suppressed -- each had fewer than 150, whatever the rate puts it at."""
    dark = sorted((rate * adults[c], g["name"]) for c, g in table.items() if g["total"] is None)
    if not dark:
        return float(LOW_PRECISION)
    estimate, name = dark[-1]
    factor = max(1.0, estimate / MINIMUM)
    cut = LOW_PRECISION * factor
    said = (f"CBS had fewer than {MINIMUM} for {name}, so an estimate can run "
            f"{100 * (factor - 1):.0f}% high" if factor > 1 else
            f"none is put at {MINIMUM} or more")
    log(f"  suppressed gemeenten at the national rate: "
        + ", ".join(f"{n} {e:.0f}" for e, n in dark)
        + f"; {said}, and low precision is said below an estimated {cut:.0f}")
    return cut


# ---------------------------------------------------------------------------
# Binding and records
# ---------------------------------------------------------------------------

def plain(name: str) -> str:
    """A gemeente name without StatLine's "(gemeente)" and a province qualifier."""
    name = re.sub(r"\s*\((?:gemeente|gem\.)\)\s*$", "", cell_text(name), flags=re.I)
    return re.sub(r"\s*\([A-Za-z]{1,4}\.?\)\s*$", "", name)


def same_place(a: str, b: str) -> bool:
    return fold(plain(a)) == fold(plain(b)) or fold(a) == fold(b)


def bind(codes: Iterable[str], titles: dict[str, str],
         shapes: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """{drawn CBS code: shape} by the code the build bound to each polygon,
    checked against the polygon's label; by label alone where it has none."""
    by_code: dict[str, list[dict[str, Any]]] = {}
    for s in shapes:
        code = (s.get("codes") or {}).get("cbs_gemeente")
        if code:
            by_code.setdefault(code, []).append(s)
    out: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for code in sorted(codes):
        hits = by_code.get(code) or [s for s in shapes if same_place(titles[code], s["name"])]
        if len(hits) != 1:
            problems.append(f"{titles[code]} ({code}): {len(hits)} polygons")
            continue
        shape = hits[0]
        if not any(same_place(titles[code], label)
                   for label in [shape["name"], *(shape.get("aliases") or [])]):
            problems.append(f"{titles[code]} ({code}) is bound to a polygon labelled {shape['name']!r}")
            continue
        out[code] = shape
    if len({s["id"] for s in out.values()}) != len(out):
        problems.append("two gemeenten on one polygon")
    return out, problems


NOTE = (
    f"CBS survey estimate, pooled over {SPAN} ({TITLE}, December 2016, the table behind CBS's paper "
    f"De religieuze kaart van Nederland, {SPAN}), from the Enquête Beroepsbevolking, the Labour "
    f"Force Survey, whose {SPAN} rounds asked about religion: the share of adults aged 18 and over "
    "in private households who count themselves to a church denomination or philosophy-of-life "
    "group, and which, weighted by CBS. More than 600,000 people answered over the six years; CBS "
    f"prints a gemeente only when at least {MINIMUM} respondents stand behind it and does not print "
    "the number. The question offered Roman Catholic, Dutch Reformed (Nederlands Hervormd), Reformed "
    "(Gereformeerde kerken), the Protestant Church in the Netherlands (PKN, formed from both in 2004; "
    "many of its members still name the church they came from), Islam, Judaism, Hinduism, Buddhism "
    f"and another group; '{OTHER}' is that last answer, any other church, religion or philosophy of "
    f"life, which CBS does not divide. '{NO_RELIGION}' is everyone who counts themselves to none. The "
    "Netherlands has had no questionnaire census since 1971 and no register records religion; this "
    "is CBS's latest table by gemeente (its 2021-2025 survey is published by province and COROP "
    "region only).")


def unit_note(unit: Unit, name: str, table: dict[str, dict[str, Any]], respondents: float,
              tolerance: float = TOLERANCE, cut: float = LOW_PRECISION) -> str:
    parts = sorted(unit.whole, key=lambda i: table[i]["name"])
    if parts == [unit.code]:
        what = f" {name} is the gemeente of {VINTAGE} itself."
    elif len(parts) == 1:
        what = f" {name} is the gemeente of {VINTAGE} {table[parts[0]]['name']} (renamed since)."
    else:
        what = (f" {name} covers what in {VINTAGE} were the gemeenten "
                f"{listed([table[i]['name'] for i in parts])} (CBS's record of gemeente changes, "
                f"StatLine 70739ned); their estimates are averaged, weighted by their population "
                f"aged 18 and over on 1 January {VINTAGE} (StatLine 03759ned), and each rests on at "
                f"least {MINIMUM} respondents.")
    if unit.events:
        what += (f" Since {VINTAGE}, {'; '.join(unit.events)} (70739ned): {share(unit.moved)} of its "
                 f"people, within the {100 * tolerance:.0f}% a boundary correction may move.")
    low = respondents < cut
    what += (f" {'Low precision: ' if low else ''}CBS does not print the number of respondents; at "
             f"the survey's national rate (about {RESPONDENTS:,} adults over the six years) this "
             f"gemeente's adults would give about {respondents:,.0f}")
    if low and respondents >= LOW_PRECISION:
        what += (", and that estimate runs high for the gemeenten CBS suppressed, so fewer than "
                 f"{LOW_PRECISION} is possible.")
    else:
        what += "."
    return NOTE + what


def build(tolerance: float = TOLERANCE, unions: bool = True) -> list[dict[str, Any]]:
    log(f"netherlands_religion_gemeente: CBS, {TITLE}")
    table, national = read_table()
    printed = {c for c, g in table.items() if g["total"] is not None}
    log(f"  {len(table)} gemeenten of {VINTAGE}, {len(printed)} printed; suppressed: "
        + ", ".join(sorted(g["name"] for g in table.values() if g["total"] is None)))
    if len(table) != EXPECTED:
        raise SystemExit(f"netherlands_religion_gemeente: {len(table)} gemeenten, not {EXPECTED}")
    check_table({**table, "NL01": national})
    check_release(table)

    history = read_history()
    first = in_being(history, START)
    if first != set(table):
        raise SystemExit(f"netherlands_religion_gemeente: 70739ned's gemeenten of {START} differ: "
                         f"{sorted(first ^ set(table))}")
    misnamed = [f"{g['name']} / {history[c]['title']}" for c, g in table.items()
                if not same_place(g["name"], history[c]["title"])]
    if misnamed:
        raise SystemExit(f"netherlands_religion_gemeente: names differ: {misnamed}")

    ages = read_ages(sorted(table) + ["NL01"], period=AGE_PERIOD)
    missing = sorted(set(table) - set(ages))
    if missing:
        raise SystemExit(f"netherlands_religion_gemeente: 03759ned has no {VINTAGE} ages for {missing}")
    population = {c: float(ages[c]["total"]) for c in table}
    adults = {c: float(sum(n for a, n in ages[c]["m"].items() if a >= 18)
                       + sum(n for a, n in ages[c]["f"].items() if a >= 18)) for c in table}
    whole_country = float(ages["NL01"]["total"])
    if abs(sum(population.values()) - whole_country) > 0.5:
        raise SystemExit(f"netherlands_religion_gemeente: the {VINTAGE} gemeenten make "
                         f"{sum(population.values()):,.0f}, the country {whole_country:,.0f}")
    log(f"  {VINTAGE} gemeenten against the country (03759ned, 1 January {VINTAGE}): "
        f"{sum(population.values()):,.0f} = {whole_country:,.0f}; adults {sum(adults.values()):,.0f}")
    check_national(table, adults, national)
    # 70739ned gives one province per gemeente; the two that changed province after 2016
    # (Leerdam and Zederik, to Utrecht in 2019) are some 27,000 adults, within the tolerance.
    provinces = {c: PROVINCE_NAMES.get(history[c]["province"], history[c]["province"]) for c in table}
    check_parents(table, adults, provinces, province_means())
    check_unions(history, table)

    walk = follow(history, population)
    last = set(walk.content)
    log(f"  70739ned: {len(walk.transfers)} transfers of people between {START} and {STOP}; "
        f"{len(last)} gemeenten on {STOP}")
    if len(last) != DRAWN:
        raise SystemExit(f"netherlands_religion_gemeente: {len(last)} gemeenten on {STOP}, not {DRAWN}")
    titles = {c: plain(g["title"]) for c, g in history.items()}
    rate = RESPONDENTS / sum(adults.values())
    cut = low_precision_cut(table, adults, rate)

    raw = {u["id"]: u for u in json.loads((SITE / "admin2" / "NLD.units.json").read_text())}
    shapes = units("NLD", "admin2")
    bound, problems = bind(last, titles, shapes)
    left = sorted(s["name"] for s in shapes if s["id"] not in {b["id"] for b in bound.values()})
    if problems or left:
        raise SystemExit(f"netherlands_religion_gemeente: binding: {problems}; polygons left {left}")

    records, filled, joined, corrected, low, why = [], 0, 0, 0, 0, Counter()
    for code in sorted(last):
        shape = bound[code]
        unit = classify(code, walk, population, table, titles, tolerance, unions)
        name = raw[shape["id"]]["name"]
        base = dict(level="admin2", parent=shape["parent"], country="NLD", match_by="shape_id",
                    shape_id=shape["id"], aliases=[shape["name"]] if shape["name"] != name else [])
        if unit.reason:
            why[unit.kind] += 1
            said = f"{name} {unit.reason}"
            log(f"  {name} ({code}): no figure -- {said}")
            records.append(record(
                f"NLD-CBS-EBB-REL-{code}", name, codes={"cbs_gemeente": code}, **base,
                religion=gap(NOT_AVAILABLE, (
                    f"CBS's latest table of religion by gemeente ({TITLE}, from the Enquête "
                    f"Beroepsbevolking) counts the gemeenten of {VINTAGE}, and {said}. CBS's later "
                    "religion surveys are published by province and COROP region only; the "
                    "Netherlands has had no questionnaire census since 1971 and no register records "
                    "religion."))))
            continue
        weights = {i: adults[i] * f for i, f in unit.whole.items()}
        total, parts = blend(table, weights)
        respondents = rate * sum(weights.values())
        joined += len(unit.whole) > 1
        corrected += bool(unit.events)
        low += respondents < cut
        if unit.events:
            log(f"  {name} ({code}): {'; '.join(unit.events)} -- {share(unit.moved)}, a correction")
        records.append(record(
            f"NLD-CBS-EBB-REL-{code}", name,
            codes={"cbs_gemeente": code, f"cbs_gemeenten_{VINTAGE}": ",".join(sorted(unit.whole))},
            **base,
            religion=composition(parts, total), religion_year=YEAR, religion_basis=BASIS,
            religion_note=unit_note(unit, name, table, respondents, tolerance, cut),
            sources=[{"field": "religion", "name": SOURCE, "url": WORKBOOK, "license": LICENCE,
                      "year": YEAR}]))
        filled += 1
    log(f"  {filled} of {len(last)} gemeenten take a figure ({joined} as unions of {VINTAGE} "
        f"gemeenten, {corrected} after boundary corrections, {low} of low precision); none for "
        f"{why['changed']} changed since {VINTAGE}, {why['suppressed']} that CBS suppressed"
        + (f" and {why['union']} unions left out (--no-unions)" if why["union"] else ""))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tolerance", type=float, default=TOLERANCE,
                    help="largest share of a gemeente's people a boundary change may move and "
                         "leave it the same unit (default %(default)s)")
    ap.add_argument("--no-unions", action="store_true",
                    help="carry a figure only to a drawn gemeente that is one gemeente of the "
                         "table's; a union of whole ones gets a gap saying so")
    args = ap.parse_args()
    records = build(args.tolerance, unions=not args.no_unions)
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
