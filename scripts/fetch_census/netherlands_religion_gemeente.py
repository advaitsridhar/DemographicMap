#!/usr/bin/env python3
"""The Netherlands: religion by gemeente, from CBS's 2010-2014 survey table (a survey estimate).

The Netherlands has had no questionnaire census since 1971 and no register
records religion. From 2010 to 2015 CBS asked it in the Labour Force Survey
(Enquête Beroepsbevolking, EBB), whose sample is large enough for gemeenten,
and published the pooled answers of 2010-2014 by gemeente as a maatwerk
table, "Religie en kerkbezoek naar gemeente 2010-2014" (13 May 2015): about
460,000 adults (18 and over) in private households, weighted by CBS, the
share who count themselves to a church denomination or philosophy-of-life
group and which. CBS prints a gemeente only when at least 150 respondents
stand behind it, and not the number. Its later religion surveys (Sociale
samenhang en welzijn, about 7,500 a year) are published by province and COROP
region only (``netherlands_religion.py``), so this is the latest figure by
gemeente there is.

**Vintage.** The table counts the gemeenten of 1 January 2014 (403); the map
draws those of 2022 after Weesp joined Amsterdam (344). What happened in
between is CBS's own record, StatLine 70739ned ("Gebieden; overzicht vanaf
1830"), whose explanation of every gemeente lists each merger, dissolution and
boundary change with the inhabitants it moved. Those transfers are followed
from 2014 to 2022, so each drawn gemeente is known as shares of 2014
gemeenten, and

* a gemeente that is one 2014 gemeente takes that gemeente's figure;
* a gemeente that is a union of whole 2014 gemeenten takes their mean,
  weighted by their population aged 18 and over on 1 January 2014 (StatLine
  03759ned), every part resting on CBS's 150 respondents or more;
* a gemeente holding part of a 2014 gemeente that was divided (Maasdonk in
  2015, Littenseradiel in 2018, Winsum in 2019 and Haaren in 2021 were shared
  out between several), or that gave or took more than a boundary correction,
  takes nothing, because a gemeente's figure is never split. Its record says
  so, with the transfers, in place of a bare gap.

A boundary change moving at most ``TOLERANCE`` (2%) of a gemeente's people is
a correction, not a different unit; every one is named in the log and the
note. ``--tolerance`` sets another share.

**Checks.** The categories make CBS's total within rounding for every
gemeente; the 2014 gemeenten are 70739ned's on that date, by code and name,
and their 2014 populations make the country's; every 2014 gemeente's
inhabitants end up in the 2022 gemeenten exactly once; every transfer a
recipient records is the one its donor records; and the gemeenten's
estimates, weighted by their adults, land within ``PARENT_TOLERANCE`` points
of CBS's own province and national figures from the same survey (StatLine
83288NED, 2010-2014). A miss stops the run.

Usage:
    python -m scripts.fetch_census.netherlands_religion_gemeente
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, http_json, log, record, write_json
from .central_ages import SITE, fold, units
from .netherlands_gemeente import read_ages

WORKBOOK = ("https://www.cbs.nl/-/media/imported/documents/2015/20/"
            "religie-en-kerkbezoek-naar-gemeente-2010-2014.xls")
PAGE = "https://www.cbs.nl/nl-nl/maatwerk/2015/20/religie-en-kerkbezoek-naar-gemeente-2010-2014"
SOURCE = ("CBS, Religie en kerkbezoek naar gemeente 2010-2014 (maatwerk, 13 May 2015), from the "
          "Enquête Beroepsbevolking")
LICENCE = "CC BY 4.0 (CBS)"
OUT = PROCESSED / "netherlands_religion_gemeente_survey.json"
YEAR = 2014
BASIS = "survey estimate: self-identification, adults 18+ in private households"

HISTORY = "https://opendata.cbs.nl/ODataApi/odata/70739ned/{path}?$format=json"
PROVINCE_TABLE = "https://opendata.cbs.nl/ODataApi/odata/83288NED/{path}?$format=json"
START, STOP = "20140101", "20221231"      # the table's division; the drawn one (after 24 March 2022)
PLACEHOLDERS = {"GM0996", "GM0998", "GM0999"}   # IJsselmeerpolders, abroad, not assigned
AGE_PERIOD = "2014JJ00"
SURVEY_YEARS = ("2010JJ00", "2011JJ00", "2012JJ00", "2013JJ00", "2014JJ00")

RESPONDENTS = 460_000        # the table's "circa 460 duizend volwassen personen"
MINIMUM = 150                # its footnote: "minimaal 150 waarnemingen per gemeente"
LOW_PRECISION = 300          # BRIEF_EU_SURVEYS: say so below 300 respondents
EXPECTED = 403               # gemeenten on 1 January 2014
DRAWN = 344
TOLERANCE = 0.02             # a boundary change this small (of either side) is a correction
SUM_TOLERANCE = 0.5          # nine categories rounded to 0.1, against a total rounded to 0.1
PARENT_TOLERANCE = 1.5       # points: 18+ pooled against 15+ by year, rounded to whole points

NO_RELIGION = "No religion"
OTHER = "Other or unspecified religion"
# The table's columns -> the map's labels (netherlands_religion.py's where it has one).
COLUMNS = {"Katholiek": "Roman Catholic", "Hervormd": "Dutch Reformed",
           "Gereformeerd": "Reformed (Gereformeerd)", "PKN": "Protestant Church in the Netherlands",
           "Islam": "Islam", "Joods": "Judaism", "Hindoe": "Hinduism", "Boeddhist": "Buddhism",
           "Anders": OTHER}
TOTAL_HEAD = "Kerkelijke gezindte of"   # "... of levensbeschouwelijke groepering", not the title
# 83288NED's measures, as sums of the table's columns, for the parent check.
PROVINCE_MEASURES = {
    "TotaalKerkelijkeGezindte_2": ("total",), "RoomsKatholiek_3": ("Katholiek",),
    "ProtestantseKerkInNederland_4": ("PKN",), "NederlandsHervormd_5": ("Hervormd",),
    "Gereformeerd_6": ("Gereformeerd",), "Islam_7": ("Islam",),
    "OverigeGezindte_8": ("Joods", "Hindoe", "Boeddhist", "Anders"),
}


# ---------------------------------------------------------------------------
# The table
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


def parse_table(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """{GM code: {name, province, total, parts{column: share}}} from the sheet's rows;
    a gemeente CBS suppressed has total None and no parts.

    The header is found, not assumed: the row naming every category, the row
    above it naming the total, and the row naming the gemeente columns.
    """
    texts = [[cell_text(c) for c in row] for row in rows]
    labels_at = next((i for i, row in enumerate(texts) if all(k in row for k in COLUMNS)), None)
    if labels_at is None:
        raise SystemExit("netherlands_religion_gemeente: no row names the nine categories")
    column = {k: texts[labels_at].index(k) for k in COLUMNS}
    total_at = next((j for i in range(labels_at) for j, c in enumerate(texts[i])
                     if c.startswith(TOTAL_HEAD)), None)
    head_at = next((i for i, row in enumerate(texts) if "Gemeente" in row and "Gemcode" in row), None)
    if total_at is None or head_at is None:
        raise SystemExit("netherlands_religion_gemeente: the total or the gemeente columns are missing")
    head = texts[head_at]
    at_province, at_name, at_code = head.index("Provincie"), head.index("Gemeente"), head.index("Gemcode")
    out: dict[str, dict[str, Any]] = {}
    for row, text in zip(rows[head_at + 1:], texts[head_at + 1:]):
        if len(text) <= max(column.values()) or not text[at_name] or not text[at_code]:
            continue
        code = gemeente_code(row[at_code])
        total = number(row[total_at])
        parts = {k: number(row[i]) for k, i in column.items()}
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


def check_table(table: dict[str, dict[str, Any]]) -> None:
    """Every share a share, and the categories make the total."""
    worst = (0.0, "")
    for code, g in table.items():
        if g["total"] is None:
            continue
        values = [g["total"], *g["parts"].values()]
        if any(v < 0 or v > 100 for v in values):
            raise SystemExit(f"netherlands_religion_gemeente: {g['name']}: a share outside 0-100")
        gap_ = abs(sum(g["parts"].values()) - g["total"])
        if gap_ > SUM_TOLERANCE:
            raise SystemExit(f"netherlands_religion_gemeente: {g['name']} ({code}): the categories "
                             f"make {sum(g['parts'].values()):.1f}, the total is {g['total']}")
        if gap_ > worst[0]:
            worst = (gap_, g["name"])
    log(f"  categories against the total: largest difference {worst[0]:.1f} ({worst[1]})")


def read_table() -> dict[str, dict[str, Any]]:
    import xlrd
    book = xlrd.open_workbook(file_contents=http_get(WORKBOOK, binary=True, timeout=300))
    sheet = book.sheet_by_name("Tabel")
    rows = [sheet.row_values(r) for r in range(sheet.nrows)]
    notes = " ".join(cell_text(c) for row in rows for c in row if isinstance(c, str))
    notes += " " + " ".join(cell_text(c) for r in range(book.sheet_by_name("Toelichting").nrows)
                            for c in book.sheet_by_name("Toelichting").row_values(r))
    # What the record will say about the table, read from the table.
    for claim in (r"Gemeentelijke indeling 2014", rf"minimaal {MINIMUM} waarnemingen",
                  r"460 duizend volwassen personen \(18 jaar of ouder\)", r"Enqu.te Beroepsbevolking"):
        if not re.search(claim, notes):
            raise SystemExit(f"netherlands_religion_gemeente: the workbook no longer says {claim!r}")
    return parse_table(rows)


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
    """{GM code: {title, begin, end, events}} for every gemeente since 1830."""
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
    rows = {COLUMNS[k]: v for k, v in parts.items()}
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
    parts = {k: sum(table[i]["parts"][k] * w for i, w in weights.items()) / whole for k in COLUMNS}
    return total, parts


@dataclass
class Unit:
    code: str                          # the drawn gemeente's CBS code
    whole: dict[str, float]            # 2014 gemeenten (nearly) wholly in it -> the share it holds
    foreign: dict[str, float]          # parts of other 2014 gemeenten -> the share it holds
    moved: float                       # share of its people (2014 terms) not from its whole parts,
                                       # or lost by them -- the larger
    events: list[str]                  # the transfers that touched it, in words
    reason: str | None                 # why it takes no figure, or None
    kind: str = ""                     # "changed" or "suppressed" when it takes none


def say_day(day: str) -> str:
    months = ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]
    return f"{int(day[6:])} {months[int(day[4:6]) - 1]} {day[:4]}"


def classify(code: str, walk: Crosswalk, population: dict[str, float],
             table: dict[str, dict[str, Any]], titles: dict[str, str],
             tolerance: float = TOLERANCE) -> Unit:
    """Whether the drawn gemeente ``code`` is a 2014 gemeente, or a union of
    whole ones, to within ``tolerance`` of its people either way."""
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
    donors: list[str] = []
    for t in walk.transfers:
        a, b, day = titles.get(t.donor, t.donor), titles.get(t.to, t.to), say_day(t.day)
        if t.to in line and t.donor not in line:
            events.append(f"it received {t.people:,} of the inhabitants of {a} when {a} was dissolved "
                          f"on {day}" if t.kind == "Opgeheven" else
                          f"it received {t.people:,} inhabitants from {a} on {day}")
            donors.append(t.donor)
        elif t.donor in line and t.to not in line:
            who = "it" if t.donor == code else f"{a}, now part of it,"
            events.append(f"{who} gave {t.people:,} inhabitants to {b} on {day}")
    # Where else the people of a gemeente it took part of went.
    for t in walk.transfers:
        if t.donor in donors and t.to not in line:
            events.append(f"{titles.get(t.donor, t.donor)} gave {t.people:,} inhabitants to "
                          f"{titles.get(t.to, t.to)} on {say_day(t.day)}")
    events = list(dict.fromkeys(events))
    moved = max(gained, lost)
    if gained > tolerance or not whole:
        return Unit(code, whole, foreign, moved, events, (
            f"is not a 2014 gemeente or a union of whole ones: since 2014, "
            f"{'; '.join(events) or 'it holds only parts of 2014 gemeenten'} (CBS StatLine "
            f"70739ned) -- {100 * moved:.1f}% of its people, more than the {100 * tolerance:.0f}% a "
            f"boundary correction may move -- and a gemeente's figure is never split"), "changed")
    dark = sorted(table[i]["name"] for i in whole if table[i]["total"] is None)
    if dark:
        return Unit(code, whole, foreign, moved, events, (
            f"CBS printed no figure for {' and '.join(dark)}: fewer than {MINIMUM} of its people "
            f"answered in 2010-2014"), "suppressed")
    return Unit(code, whole, foreign, moved, events, None)


# ---------------------------------------------------------------------------
# The parent check (83288NED)
# ---------------------------------------------------------------------------

def province_means() -> dict[str, dict[str, float]]:
    """{region title without "(PV)": {measure: mean 2010-2014}} from 83288NED."""
    titles = {r["Key"].strip(): re.sub(r"\s*\(PV\)\s*$", "", cell_text(r["Title"]))
              for r in odata_rows(PROVINCE_TABLE.format(path="RegioS"))}
    sums: dict[str, Counter] = {}
    counts: dict[str, Counter] = {}
    for r in odata_rows(PROVINCE_TABLE.format(path="TypedDataSet")):
        key, period = r["RegioS"].strip(), r["Perioden"].strip()
        if period not in SURVEY_YEARS or not (key.startswith("PV") or key == "NL01"):
            continue
        for measure in PROVINCE_MEASURES:
            if r.get(measure) is not None:
                sums.setdefault(titles[key], Counter())[measure] += float(r[measure])
                counts.setdefault(titles[key], Counter())[measure] += 1
    return {region: {m: sums[region][m] / counts[region][m] for m in sums[region]
                     if counts[region][m] == len(SURVEY_YEARS)} for region in sums}


def check_parents(table: dict[str, dict[str, Any]], adults: dict[str, float],
                  published: dict[str, dict[str, float]]) -> None:
    """The gemeenten's estimates, weighted by their adults, against CBS's own
    province and national figures from the same survey and years."""
    groups: dict[str, list[str]] = {}
    for code, g in table.items():
        if g["total"] is not None:
            groups.setdefault(g["province"], []).append(code)
            groups.setdefault("Nederland", []).append(code)
    if set(groups) - set(published):
        raise SystemExit(f"netherlands_religion_gemeente: no CBS figure for "
                         f"{sorted(set(groups) - set(published))}")
    worst = (0.0, "")
    for region, codes in sorted(groups.items()):
        whole = sum(adults[c] for c in codes)
        for measure, columns in PROVINCE_MEASURES.items():
            mine = sum(adults[c] * sum(table[c]["total"] if k == "total" else table[c]["parts"][k]
                                       for k in columns) for c in codes) / whole
            theirs = published[region].get(measure)
            if theirs is None:
                raise SystemExit(f"netherlands_religion_gemeente: 83288NED lacks {measure} for {region}")
            if abs(mine - theirs) > PARENT_TOLERANCE:
                raise SystemExit(f"netherlands_religion_gemeente: {region} {measure}: the gemeenten "
                                 f"make {mine:.1f}, CBS publishes {theirs:.1f} (2010-2014 mean)")
            if abs(mine - theirs) > worst[0]:
                worst = (abs(mine - theirs), f"{region} {measure} {mine:.1f} / {theirs:.1f}")
        religious = sum(adults[c] * table[c]["total"] for c in codes) / whole
        log(f"  {region}: {len(codes)} gemeenten, religious {religious:.1f}% against CBS's "
            f"{published[region]['TotaalKerkelijkeGezindte_2']:.1f}%")
    log(f"  gemeenten against CBS's provinces and country: largest difference {worst[0]:.2f} "
        f"points ({worst[1]})")


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
    "CBS survey estimate, pooled over 2010-2014 (Religie en kerkbezoek naar gemeente 2010-2014, "
    "from the Enquête Beroepsbevolking, the Labour Force Survey, which asked about religion from "
    "2010): the share of adults aged 18 and over in private households who count themselves to a "
    "church denomination or philosophy-of-life group, and which, weighted by CBS. About "
    f"{RESPONDENTS:,} adults answered over the five years; CBS prints a gemeente only when at least "
    f"{MINIMUM} respondents stand behind it and does not print the number. The question offered "
    "Roman Catholic, Dutch Reformed (Nederlands Hervormd), Reformed (Gereformeerd), the Protestant "
    "Church in the Netherlands (PKN, formed from both in 2004; many of its members still name the "
    "church they came from), Islam, Judaism, Hinduism, Buddhism and another group; "
    f"'{OTHER}' is that last answer, any other church, religion or philosophy of life, which CBS "
    f"does not divide. '{NO_RELIGION}' is everyone who counts themselves to none. The Netherlands "
    "has had no questionnaire census since 1971 and no register records religion; CBS's later "
    "religion surveys are published by province and COROP region only, so this is the latest "
    "figure by gemeente.")


def unit_note(unit: Unit, name: str, table: dict[str, dict[str, Any]], respondents: float,
              tolerance: float = TOLERANCE) -> str:
    parts = sorted(unit.whole, key=lambda i: table[i]["name"])
    if parts == [unit.code]:
        what = f" {name} is the gemeente of 2014 itself."
    else:
        names = [table[i]["name"] for i in parts]
        listed = ", ".join(names[:-1]) + f" and {names[-1]}"
        what = (f" {name} covers what in 2014 were the gemeenten {listed} (CBS's record of "
                "gemeente changes, StatLine 70739ned); their estimates are averaged, weighted by their "
                "population aged 18 and over on 1 January 2014 (StatLine 03759ned), and each rests "
                f"on at least {MINIMUM} respondents.")
    if unit.events:
        what += (f" Since 2014, {'; '.join(unit.events)} (70739ned): {100 * unit.moved:.1f}% of its "
                 f"people, within the {100 * tolerance:.0f}% a boundary correction may move.")
    if respondents < LOW_PRECISION:
        what += (" Low precision: CBS does not print the number of respondents, and at the survey's "
                 f"national rate this gemeente's adults would give about {respondents:,.0f}.")
    return NOTE + what


def build(tolerance: float = TOLERANCE) -> list[dict[str, Any]]:
    log("netherlands_religion_gemeente: CBS, Religie en kerkbezoek naar gemeente 2010-2014")
    table = read_table()
    printed = {c for c, g in table.items() if g["total"] is not None}
    log(f"  {len(table)} gemeenten of 2014, {len(printed)} printed; suppressed: "
        + ", ".join(sorted(g["name"] for g in table.values() if g["total"] is None)))
    if len(table) != EXPECTED:
        raise SystemExit(f"netherlands_religion_gemeente: {len(table)} gemeenten, not {EXPECTED}")
    check_table(table)

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
        raise SystemExit(f"netherlands_religion_gemeente: 03759ned has no 2014 ages for {missing}")
    population = {c: float(ages[c]["total"]) for c in table}
    adults = {c: float(sum(n for a, n in ages[c]["m"].items() if a >= 18)
                       + sum(n for a, n in ages[c]["f"].items() if a >= 18)) for c in table}
    national = float(ages["NL01"]["total"])
    if abs(sum(population.values()) - national) > 0.5:
        raise SystemExit(f"netherlands_religion_gemeente: the 2014 gemeenten make "
                         f"{sum(population.values()):,.0f}, the country {national:,.0f}")
    log(f"  2014 gemeenten against the country (03759ned, 1 January 2014): "
        f"{sum(population.values()):,.0f} = {national:,.0f}; adults {sum(adults.values()):,.0f}")
    check_parents(table, adults, province_means())

    walk = follow(history, population)
    last = set(walk.content)
    log(f"  70739ned: {len(walk.transfers)} transfers of people between {START} and {STOP}; "
        f"{len(last)} gemeenten on {STOP}")
    if len(last) != DRAWN:
        raise SystemExit(f"netherlands_religion_gemeente: {len(last)} gemeenten on {STOP}, not {DRAWN}")
    titles = {c: plain(g["title"]) for c, g in history.items()}
    rate = RESPONDENTS / sum(adults.values())

    raw = {u["id"]: u for u in json.loads((SITE / "admin2" / "NLD.units.json").read_text())}
    shapes = units("NLD", "admin2")
    bound, problems = bind(last, titles, shapes)
    left = sorted(s["name"] for s in shapes if s["id"] not in {b["id"] for b in bound.values()})
    if problems or left:
        raise SystemExit(f"netherlands_religion_gemeente: binding: {problems}; polygons left {left}")

    records, filled, unions, corrected, why = [], 0, 0, 0, Counter()
    for code in sorted(last):
        shape = bound[code]
        unit = classify(code, walk, population, table, titles, tolerance)
        name = raw[shape["id"]]["name"]
        base = dict(level="admin2", parent=shape["parent"], country="NLD", match_by="shape_id",
                    shape_id=shape["id"], aliases=[shape["name"]] if shape["name"] != name else [])
        if unit.reason:
            why[unit.kind] += 1
            said = f"{name} {unit.reason}" if unit.kind == "changed" else unit.reason
            log(f"  {name} ({code}): no figure -- {said}")
            records.append(record(
                f"NLD-CBS-EBB-REL-{code}", name, codes={"cbs_gemeente": code}, **base,
                religion=gap(NOT_AVAILABLE, (
                    "CBS's only table of religion by gemeente (Religie en kerkbezoek naar gemeente "
                    "2010-2014, from the Enquête Beroepsbevolking) counts the gemeenten of 2014, "
                    f"and {said}. CBS's later religion surveys are published by province and COROP "
                    "region only; the Netherlands has had no questionnaire census since 1971 and no "
                    "register records religion."))))
            continue
        weights = {i: adults[i] * f for i, f in unit.whole.items()}
        total, parts = blend(table, weights)
        respondents = rate * sum(weights.values())
        unions += len(unit.whole) > 1
        corrected += bool(unit.events)
        if unit.events:
            log(f"  {name} ({code}): {'; '.join(unit.events)} -- {100 * unit.moved:.2f}%, a correction")
        records.append(record(
            f"NLD-CBS-EBB-REL-{code}", name,
            codes={"cbs_gemeente": code, "cbs_gemeenten_2014": ",".join(sorted(unit.whole))}, **base,
            religion=composition(parts, total), religion_year=YEAR, religion_basis=BASIS,
            religion_note=unit_note(unit, name, table, respondents, tolerance),
            sources=[{"field": "religion", "name": SOURCE, "url": PAGE, "license": LICENCE,
                      "year": YEAR}]))
        filled += 1
    log(f"  {filled} of {len(last)} gemeenten take a figure ({unions} as unions of 2014 gemeenten, "
        f"{corrected} after boundary corrections); none for {why['changed']} changed since 2014 "
        f"and {why['suppressed']} that CBS suppressed")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tolerance", type=float, default=TOLERANCE,
                    help="largest share of a gemeente's people a boundary change may move and "
                         "leave it the same unit (default %(default)s)")
    args = ap.parse_args()
    records = build(args.tolerance)
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
