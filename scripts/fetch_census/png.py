#!/usr/bin/env python3
"""Papua New Guinea: the 2024 census head count, and the 2011 census's religion.

Two publications of one office, the National Statistical Office
(``www.nso.gov.pg``), which answers an automated reader without complaint:

* **2024 National Population Census -- Final Figures** (October 2025, 35 pp).
  Table 1 is population, males, females and sex ratio for the 22 provinces;
  the 22 Provincial Snapshots that follow give the same three counts for each
  of the 96 districts it lists. It carries **no religion**: the word does not
  appear on any of its 35 pages, and its own preface says "Detailed
  demographic information from the 2024 Census will be released
  progressively."
* **Papua New Guinea 2011 National Report** (100 pp), the fourth census's
  main release. Its religion chapter prints the denominational table for the
  country and, for each province, **one figure**: the Summary Indicators row
  "Main religion (% of population)" -- the largest denomination and its share
  of the citizen population. That row is what the 22 provinces carry here.

**What the census asks.** Appendix 1 of the 2011 report lists the
questionnaire's subjects: "age; sex, marital status, religion, migration,
economic activity, occupation, industry, fertility, mortality and household
income generating activities ... A total of 33 questions were asked using a
one-page census questionnaire." There is no ethnicity question and no
mother-tongue question; the only language item is literacy -- Table 4.6,
"Literacy rate ... by language", which counts who can read and write English,
Pidgin, Motu or Tokples, an ability and not a composition. Both are declared
in ``NOT_COLLECTED_POLICY`` (``PNG``), with that evidence, rather than left
as gaps.

**Religion as a one-row composition.** A province's record carries a single
group -- "Roman Catholic 68.4%" for Bougainville -- because that is the whole
of what the office publishes for a province. The panel says so by itself:
shares that fall short of 100 draw the chip "describes 68.4% of the
population". The rest of each province is not broken down anywhere this
project could reach. The National Report's foreword says the full tables are
in "the 22 Provincial Reports"; the office's Population & Housing download
category holds ten files and none of them is a provincial report, and no
mirror carries one (see docs/SOURCES.md).

**Reading the figures.** Both PDFs extract through pypdf with their thousands
separators intact but their digits broken up by kerning -- Milne Bay's
412,158 comes out as "41 2 ,15 8". So a row is read the way ``vietnam.py``
reads its volume: every digit on the row in order, then every way of cutting
that string into the numbers the row is supposed to carry, keeping the one
where the census's own arithmetic holds -- males plus females equal the
total, and the printed sex ratio equals 100 males per females. A row with no
single such reading refuses the run.

**Districts.** The boundary file draws the 87 districts of the 2011 layout;
the 2024 booklet tabulates a later one. Where a province's districts still
partition its shapes -- name for name, or two districts making up one shape
whose name is the union of theirs (Kairuku - Hiri, Lagaip/Pogera,
Komo/Magarima, and the National Capital District's three Moresby seats) --
the shapes are written and their totals must add to the province's printed
total. In four provinces the 2024 layout has one district more than the
boundary file draws -- Western's Delta Fly, Northern's Popondetta, Morobe's
Wau/Waria, West New Britain's Nakanai -- and the booklet does not say which
district each was carved from, so **none** of those four provinces' district
shapes is written: a figure on the wrong one of them would be invisible.
That is 71 of 87 shapes filled and 16 left with a reason.

**Self-checks**, each of which refuses the run rather than writing:

* the 22 provinces' persons add to the printed national 10,185,363;
* every row's males and females add to its own total, and the sex ratio this
  computes from them equals the printed one;
* every written province's districts add to the province's printed total;
* the three provinces the 2011 report names in prose -- "AROB (Roman
  Catholic, 68%), Morobe province (Evangelical Lutheran, 67%) and Northern
  Province (Anglican, 61%)" -- must come out of the Summary Indicators table
  at those denominations and those shares;
* all 22 provinces must be read from each publication, and a denomination
  abbreviation this reader does not know refuses rather than being dropped.

Usage:
    python -m scripts.fetch_census.png
    python -m scripts.fetch_census.png --probe
"""

from __future__ import annotations

import argparse
import re
from typing import Any, Iterable

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, collection_gap, dated, gap, http_get, log,
    measure, record, write_json,
)

OFFICE = "National Statistical Office of Papua New Guinea"
FINAL_FIGURES_URL = ("https://www.nso.gov.pg/download/51/population-housing/4310/"
                     "2024-national-population-census-final-figures_web.pdf")
NATIONAL_REPORT_URL = ("https://www.nso.gov.pg/download/51/population-housing/2152/"
                       "png-national-report-2011-census.pdf")
FINAL_FIGURES = f"2024 National Population Census: Final Figures, {OFFICE}"
NATIONAL_REPORT = f"Papua New Guinea 2011 National Report (2011 census), {OFFICE}"
POPULATION_PAGE = "https://www.nso.gov.pg/statistics/population/"
LICENCE = "None stated -- National Statistical Office publication, cited as such"

CENSUS_2024 = 2024
CENSUS_2011 = 2011

# The national row of the 2024 booklet, as it prints it. A file that does not
# reproduce its own headline total is not the table it claims to be.
NATIONAL_2024 = (10_185_363, 5_336_546, 4_848_817, 110)

# The 22 provinces, spelled as the booklet spells them, with the boundary
# file's own spelling as an alias. Three of the shapes carry a second name in
# brackets that norm() does not reduce away, so every one is declared rather
# than leaving the matcher to bridge them.
PROVINCES: dict[str, str] = {
    "Western": "Western Province",
    "Gulf": "Gulf Province",
    "Central": "Central Province",
    "National Capital District": "National Capital District",
    "Milne Bay": "Milne Bay Province",
    "Northern": "Northern (Oro) Province",
    "Southern Highlands": "Southern Highlands Province",
    "Enga": "Enga Province",
    "Western Highlands": "Western Highlands Province",
    "Chimbu": "Chimbu (Simbu) Province",
    "Eastern Highlands": "Eastern Highlands Province",
    "Hela": "Hela Province",
    "Jiwaka": "Jiwaka Province",
    "Morobe": "Morobe Province",
    "Madang": "Madang Province",
    "East Sepik": "East Sepik Province",
    "West Sepik": "West Sepik (Sandaun) Province",
    "Manus": "Manus Province",
    "New Ireland": "New Ireland Province",
    "East New Britain": "East New Britain Province",
    "West New Britain": "West New Britain Province",
    "Autonomous Region of Bougainville": "Autonomous Region of Bougainville",
}

# A 2024 district whose boundary shape is written under another name. Only
# spellings and renamings of one and the same district are here; a district
# that was carved out of another is not, and is handled by NEW_DISTRICTS.
DISTRICT_ALIASES: dict[str, str] = {
    "Mendi": "Mendi/Munihu District",
    "Hagen Central": "Mt Hagen District",
    "Kainantu": "Kainanatu District",
    "Sina Sina Yongomugl": "Sina Sina Yonggomugl District",
    "Karimui": "Karimui/Nomane District",
    "Kompiam/Ambum": "Kompiam District",
    "Huon Gulf": "Huon District",
    "Aitape Lumi": "Aitape/Lumi District",
    "Vanimo Green River": "Vanimo/Green River District",
    "Koroba Kopiago": "Koroba/Kopiago District",
    "Unggai-Benna": "Unggai/Benna District",
}

# One boundary shape, several districts of the 2024 layout. Declared, never
# inferred: in each case the shape's own name names the parts (Kairuku - Hiri
# is Kairuku and Hiri-Koiari; Lagaip/Pogera is Lagaip and Pogera Paiela;
# Komo/Magarima is Komo Hulia and Magarima), and the National Capital
# District is one shape holding the city's three seats. The sum is exact
# because these are counts of the same census.
UNIONS: dict[str, tuple[str, ...]] = {
    "Kairuku - Hiri District": ("Kairuku", "Hiri-Koiari"),
    "Lagaip/Pogera District": ("Lagaip", "Pogera Paiela"),
    "Komo/Magarima District": ("Komo Hulia", "Magarima"),
    "National Capital District": ("Moresby North West", "Moresby North East",
                                  "Moresby South"),
}

# Districts of the 2024 layout that no shape of the boundary file's 2011
# layout corresponds to, with the province each appears in. The booklet does
# not say which district each was carved from, so the whole of that province's
# district level is left unwritten -- see the module docstring.
NEW_DISTRICTS: dict[str, str] = {
    "Delta Fly": "Western",
    "Popondetta": "Northern",
    "Wau/Waria": "Morobe",
    "Nakanai": "West New Britain",
}
REDRAWN = sorted(set(NEW_DISTRICTS.values()))

# How the 2011 Summary Indicators abbreviate a denomination, and the label
# this map carries it under. An abbreviation absent from here refuses the run
# rather than being dropped: the row is one figure wide and losing it is
# losing the province.
DENOMINATIONS: dict[str, str] = {
    "R/Cath.": "Roman Catholic",
    "R/Cath": "Roman Catholic",
    "Evan.Luth": "Evangelical Lutheran",
    "Evan.Luth.": "Evangelical Lutheran",
    "Evan.All.": "Evangelical Alliance",
    "Evan.All": "Evangelical Alliance",
    "U/Church": "United Church",
    "Anglican": "Anglican",
    "SDA": "Seventh Day Adventist",
    "Pentecostal": "Pentecostal",
    "Pentecostals": "Pentecostal",
    "Baptist": "Baptist",
    "Salv.Army": "Salvation Army",
    "Kwato": "Kwato Church",
}

# The four blocks of the 2011 report's provincial Summary Indicators, with
# the abbreviations it heads their columns with, in the order it prints them.
BLOCKS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("Southern Region", (
        ("Western", "Western"), ("Gulf", "Gulf"), ("Central", "Central"),
        ("NCD", "National Capital District"), ("MBP", "Milne Bay"),
        ("Northern", "Northern"))),
    ("Highlands Region", (
        ("SHP", "Southern Highlands"), ("Enga", "Enga"),
        ("WHP", "Western Highlands"), ("Chimbu", "Chimbu"),
        ("EHP", "Eastern Highlands"), ("Hela", "Hela"), ("Jiwaka", "Jiwaka"))),
    ("Momase Region", (
        ("Morobe", "Morobe"), ("Madang", "Madang"), ("ESP", "East Sepik"),
        ("WSP", "West Sepik"))),
    ("New Guinea Islands Region", (
        ("Manus", "Manus"), ("NIP", "New Ireland"),
        ("ENBP", "East New Britain"), ("WNBP", "West New Britain"),
        ("AROB", "Autonomous Region of Bougainville"))),
)

# What the 2011 report says in prose about three provinces, on the page after
# the table these figures are read from: "Such were found in AROB (Roman
# Catholic, 68%), Morobe province (Evangelical Lutheran, 67%) and Northern
# Province (Anglican, 61%)." The table must agree with it.
PROSE_CONTROLS: dict[str, tuple[str, int]] = {
    "Autonomous Region of Bougainville": ("Roman Catholic", 68),
    "Morobe": ("Evangelical Lutheran", 67),
    "Northern": ("Anglican", 61),
}

DISTRICT_NOTE = ("Counted by the 2024 National Population Census, which the "
                 "National Statistical Office published as district totals in "
                 "each province's snapshot.")
REDRAWN_NOTE = (
    "No 2024 figure is written for this district. The census tabulates {n} "
    "districts in {province} where the boundary file draws {m}: {new} has been "
    "carved out since 2011 and the office's booklet does not say from which "
    "district, so every one of this province's shapes may have lost ground to "
    "it. A count put on the wrong one would be invisible, so none is put.")
RELIGION_NOTE = (
    "{group} was the largest religious affiliation of this province's citizen "
    "population at the 2011 census, at {pct}% -- the one religion figure the "
    "National Statistical Office publishes for a province, in the Summary "
    "Indicators of its 2011 National Report. The other {rest}% is not broken "
    "down: the census asked religion and the office published the full "
    "denominational table for the country alone, the provincial tables being "
    "in the 22 Provincial Reports, which it does not host.")
DISTRICT_RELIGION_GAP = (
    "The 2011 census asked religion, and the National Statistical Office "
    "publishes no answer below the province: its 2011 National Report gives "
    "each province one figure (its largest denomination) and the country the "
    "full table, and the 2024 census's Final Figures, the only district-level "
    "release, carries no religion on any of its 35 pages.")
PROVINCE_RELIGION_GAP = (
    "The 2011 census asked religion, but the Summary Indicators of the "
    "National Statistical Office's 2011 National Report, the only provincial "
    "religion figure it publishes, could not be read for this province.")


# ---------------------------------------------------------------------------
# Reading a PDF
# ---------------------------------------------------------------------------

def fetch_pdf(url: str, name: str) -> Any:
    """The file itself, and not the page the download plugin would rather serve.

    ``www.nso.gov.pg`` puts its publications behind a WordPress download
    plugin that negotiates on the Accept header: a client that does not say it
    wants a PDF is handed an HTML page (or, for the 2011 Final Figures
    booklet, HTTP 415 Unsupported Media Type). Asking for ``application/pdf``
    is asking the server for the representation it publishes, which is not the
    same thing as claiming to be a browser, and nothing here does that.
    """
    path = RAW / "png" / name
    if path.exists() and path.stat().st_size > 1_000_000:
        log(f"  cached {path.name} ({path.stat().st_size / 1e6:.1f} MB)")
        return path
    blob = http_get(url, binary=True, timeout=300,
                    headers={"Accept": "application/pdf,*/*"})
    if not isinstance(blob, bytes) or not blob.startswith(b"%PDF"):
        head = bytes(blob[:40]) if isinstance(blob, bytes) else str(blob)[:40]
        raise SystemExit(f"png: {url} did not serve a PDF; it begins {head!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    log(f"  fetched {path.name} ({len(blob) / 1e6:.1f} MB)")
    return path


def page_texts(url: str, name: str) -> list[str]:
    from pypdf import PdfReader  # noqa: PLC0415
    reader = PdfReader(str(fetch_pdf(url, name)))
    return [(page.extract_text() or "") for page in reader.pages]


def unkern(text: str) -> str:
    """Undo the two things this office's PDFs do to a word.

    Both files are typeset so that pypdf reads a capital away from the rest of
    its word -- "T otal", "T elefomin", "T awae/Siassi" -- and reads the digits
    of a figure in groups, "41 2 ,15 8" for 412,158. The first is repaired
    here, because a district is matched by its name; the second is not, because
    a space inside a figure is indistinguishable from the space between two
    figures and only the row's own arithmetic can tell them apart (see
    ``split_figures``).
    """
    return re.sub(r"\b([A-Z]) (?=[a-z])", r"\1", text)


def rows_of(page: str) -> list[str]:
    return [" ".join(line.split()) for line in unkern(page).splitlines() if line.strip()]


def split_figures(text: str, count: int, *, ratio: bool = False) -> tuple[int, ...]:
    """The digits of one row, cut into the numbers the row is supposed to hold.

    The office's typesetting puts spaces inside a figure, so "39,676 20,516 1
    9,1 6 0" is three numbers and nothing in the text says where one ends. What
    does say is the census's own arithmetic: males plus females make the total,
    and where a sex ratio is printed it is 100 males per females. Every cut of
    the row's digits is tried and exactly one must satisfy that; none, or more
    than one, refuses the run.
    """
    digits = re.sub(r"\D", "", text)
    if not digits:
        raise SystemExit(f"png: no figures on row {text!r}")
    want = count
    found: list[tuple[int, ...]] = []

    def cuts(start: int, left: int) -> Iterable[tuple[int, ...]]:
        if left == 1:
            piece = digits[start:]
            if piece and (piece[0] != "0" or piece == "0"):
                yield (int(piece),)
            return
        for end in range(start + 1, len(digits) - left + 2):
            piece = digits[start:end]
            if piece[0] == "0" and len(piece) > 1:
                continue
            for rest in cuts(end, left - 1):
                yield (int(piece), *rest)

    for parts in cuts(0, want):
        total, male, female = parts[0], parts[1], parts[2]
        if male + female != total or not male or not female:
            continue
        if ratio:
            printed = parts[3]
            if not 80 <= printed <= 140:
                continue
            if abs(printed - round(100.0 * male / female)) > 1:
                continue
        found.append(parts)
        if len(found) > 1:
            break
    if len(found) != 1:
        raise SystemExit(f"png: row {text!r} has {len(found)} readings that add "
                         f"up; refusing to guess which is the census's")
    return found[0]


def sex_ratio(male: int, female: int) -> int:
    return int(round(100.0 * male / female))


# ---------------------------------------------------------------------------
# The 2024 Final Figures
# ---------------------------------------------------------------------------

class Unit:
    """One province or district as the booklet counts it."""

    def __init__(self, name: str, total: int, male: int, female: int) -> None:
        self.name, self.total, self.male, self.female = name, total, male, female

    @property
    def ratio(self) -> int:
        return sex_ratio(self.male, self.female)


def read_province_table(pages: list[str]) -> dict[str, Unit]:
    """Table 1: population by sex, sex ratio and province, 2024."""
    page = next((p for p in pages if "Population by sex, sex ratio and province"
                 in unkern(p)), None)
    if page is None:
        raise SystemExit("png: the 2024 booklet has no Table 1")
    lines = rows_of(page)
    national = next((ln for ln in lines if ln.startswith("Papua New Guinea ")), None)
    if national is None:
        raise SystemExit("png: Table 1 has no Papua New Guinea row")
    if split_figures(national[len("Papua New Guinea "):], 4, ratio=True) != NATIONAL_2024:
        raise SystemExit(f"png: the booklet's national row is not "
                         f"{NATIONAL_2024}; this is not the 2024 Final Figures")

    # Table 1 numbers its provinces 1 to 22 and the page's prose does not, so
    # the enumerator is what tells a row from a sentence. Without it the
    # paragraph above the table -- "... and Eastern Highlands Province with
    # 800,072. Table 1 below shows ..." -- reads as Eastern Highlands's row
    # and refuses the run.
    out: dict[str, Unit] = {}
    seen: list[int] = []
    for line in lines:
        head = re.match(r"^\s*(\d{1,2})\s*[.]\s*(.+)$", line)
        if not head:
            continue
        number, body = int(head.group(1)), head.group(2)
        # Longest name first: "Western Highlands" starts with "Western", and
        # taking the shorter one read row 9 as a second Western and lost the
        # province. The same rule picks a snapshot's heading.
        for name in sorted(PROVINCES, key=len, reverse=True):
            if body.startswith(name) and body[len(name):len(name) + 1] == " ":
                rest = body[len(name):]
                if not re.search(r"\d", rest):
                    continue
                total, male, female, _printed = split_figures(rest, 4, ratio=True)
                out.setdefault(name, Unit(name, total, male, female))
                seen.append(number)
                break
    missing = sorted(set(PROVINCES) - set(out))
    if missing:
        raise SystemExit(f"png: Table 1 is missing {missing}")
    if sorted(seen) != list(range(1, len(PROVINCES) + 1)):
        raise SystemExit(f"png: Table 1's rows are numbered {sorted(seen)}, not 1..22")
    summed = sum(u.total for u in out.values())
    if summed != NATIONAL_2024[0]:
        raise SystemExit(f"png: the 22 provinces add to {summed:,}, not the "
                         f"printed {NATIONAL_2024[0]:,}")
    log(f"  2024 Table 1: 22 provinces adding to {summed:,}, the printed national total")
    return out


def read_snapshot(page: str) -> tuple[str, list[Unit]] | None:
    """One Provincial Snapshot: its province, and the districts it tabulates."""
    lines = rows_of(page)
    heading = " ".join(lines[:4]).upper()
    province = next((p for p in sorted(PROVINCES, key=len, reverse=True)
                     if p.upper() in heading), None)
    if province is None:
        return None
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith("Districts"))
        stop = next(i for i, ln in enumerate(lines) if ln.startswith("Proportion of"))
    except StopIteration:
        return None
    if stop <= start:
        return None

    districts: list[Unit] = []
    for line in lines[start + 1:stop]:
        match = re.match(r"^([^\d]+?)\s+(\d.*)$", line)
        if not match:
            raise SystemExit(f"png: {province}: row {line!r} is not a district row")
        name = re.sub(r"\s+District$", "", match.group(1).strip())
        total, male, female = split_figures(match.group(2), 3)
        districts.append(Unit(name, total, male, female))
    if not districts:
        raise SystemExit(f"png: {province}'s snapshot lists no districts")
    return province, districts


def read_snapshots(pages: list[str]) -> dict[str, list[Unit]]:
    out: dict[str, list[Unit]] = {}
    for page in pages:
        if "Districts" not in unkern(page) or "Proportion of" not in unkern(page):
            continue
        read = read_snapshot(page)
        if read is None:
            continue
        province, districts = read
        if province in out:
            raise SystemExit(f"png: two snapshots for {province}")
        out[province] = districts
    missing = sorted(set(PROVINCES) - set(out))
    if missing:
        raise SystemExit(f"png: no Provincial Snapshot for {missing}")
    log(f"  2024 Provincial Snapshots: {sum(len(v) for v in out.values())} districts "
        f"across {len(out)} provinces")
    return out


# ---------------------------------------------------------------------------
# The 2011 National Report's provincial religion row
# ---------------------------------------------------------------------------

def read_religion_row(lines: list[str], row: int, width: int
                      ) -> tuple[list[str], list[str]] | None:
    """One "Main religion" row read as ``width`` denominations and shares.

    The abbreviations sit either on the row itself or on the line above it,
    and the figures either after the row's own "Total" or on the line below.
    Returns None where the row does not read as exactly ``width`` of each,
    which is how a row belonging to some other table is told from this one
    rather than by where it sits on the page.
    """
    labels: list[str] = []
    for line in (lines[row - 1] if row else "", lines[row]):
        labels += [DENOMINATIONS[t] for t in line.split() if t in DENOMINATIONS]
    if len(labels) != width:
        return None
    figures = re.findall(r"\d+\.\d", lines[row])
    if len(figures) != width and row + 1 < len(lines):
        figures = re.findall(r"\d+\.\d", lines[row + 1])
    if len(figures) != width:
        return None
    return labels, figures


def read_main_religion(pages: list[str]) -> dict[str, tuple[str, float]]:
    """The Summary Indicators row "Main religion (% of population)", per province.

    The report prints the provinces in four regional blocks, and prints those
    blocks again for every chapter: six Summary Indicators pages carry the
    Southern Region's column header, one per chapter, and only chapter 2's has
    a religion row under it. Chapter 2 also opens with the *national* Summary
    Indicators, whose religion row has the same label and three columns (the
    four census years, one of them "na"). So neither the header alone nor the
    label alone finds the row: a block is a column header, and under it before
    the next header a "Main religion" row that reads as exactly as many
    denominations and as many shares as the block has provinces. Exactly one
    such reading may exist, or the run refuses.

    Each block heads its columns with the provinces' abbreviations and, above
    or beside the religion row, the abbreviated denomination for each; the
    figures follow the word Total. Both orderings the report uses are
    accepted.
    """
    lines = [line for page in pages for line in rows_of(page)]
    out: dict[str, tuple[str, float]] = {}
    # Where any block's columns are headed, so one block's window stops where
    # the next one starts rather than reading into it.
    starts = sorted({i for _, columns in BLOCKS
                     for i, ln in enumerate(lines)
                     if ln.endswith(" ".join(a for a, _ in columns))})

    for block, columns in BLOCKS:
        wanted = " ".join(abbr for abbr, _ in columns)
        found: list[tuple[list[str], list[str]]] = []
        near: list[str] = []
        for header in (i for i in starts if lines[i].endswith(wanted)):
            stop = next((s for s in starts if s > header), len(lines))
            for row in range(header + 1, stop):
                if not lines[row].startswith("Main religion"):
                    continue
                read = read_religion_row(lines, row, len(columns))
                near.append(f"line {row}: {lines[row][:70]!r}")
                if read is not None:
                    found.append(read)
        if len(found) != 1:
            raise SystemExit(
                f"png: the 2011 report gives {len(found)} readings of the {block} "
                f"'Main religion' row at the block's own width of {len(columns)}; "
                f"expected one. Rows tried: {near}")
        labels, figures = found[0]

        for (abbr, province), label, share in zip(columns, labels, figures):
            pct = float(share)
            if not 10.0 <= pct <= 90.0:
                raise SystemExit(f"png: {province} ({abbr}) main religion {pct}% "
                                 f"is outside anything this table prints")
            out[province] = (label, pct)

    missing = sorted(set(PROVINCES) - set(out))
    if missing:
        raise SystemExit(f"png: the 2011 Summary Indicators gave nothing for {missing}")
    for province, (group, pct) in PROSE_CONTROLS.items():
        read_group, read_pct = out[province]
        if read_group != group or abs(read_pct - pct) > 0.5:
            raise SystemExit(
                f"png: the table reads {province} as {read_group} {read_pct}% where "
                f"the report's own prose says {group} {pct}%")
    log("  2011 Summary Indicators: 22 provinces, and the three the report names in "
        "prose (Bougainville, Morobe, Northern) agree with it")
    return out


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def place_districts(province: str, districts: list[Unit]
                    ) -> tuple[dict[str, Unit], list[str]]:
    """The province's districts on the boundary file's shapes, or nothing.

    Returns ``{shape name: unit}`` and the districts that reach no shape. A
    province where anything is left over is returned empty, because the
    leftover's ground came out of one of the shapes and the booklet does not
    say which.
    """
    by_name = {d.name: d for d in districts}
    placed: dict[str, Unit] = {}
    used: set[str] = set()
    for shape, parts in UNIONS.items():
        if all(p in by_name for p in parts):
            total = sum(by_name[p].total for p in parts)
            male = sum(by_name[p].male for p in parts)
            female = sum(by_name[p].female for p in parts)
            placed[shape] = Unit(shape, total, male, female)
            used.update(parts)
    for name, unit in by_name.items():
        if name in used:
            continue
        shape = DISTRICT_ALIASES.get(name, f"{name} District")
        placed[shape] = unit
        used.add(name)
    left = sorted(n for n in by_name if n in NEW_DISTRICTS)
    if left:
        return {}, left
    return placed, []


def province_record(name: str, unit: Unit, religion: tuple[str, float] | None,
                    ) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if religion is not None:
        group, pct = religion
        rows = [{"group": group, "pct": pct}]
        fields["religion"] = rows
        fields["religion_year"] = dated(rows, CENSUS_2011)
        fields["religion_note"] = RELIGION_NOTE.format(
            group=group, pct=f"{pct:.1f}", rest=f"{100.0 - pct:.1f}")
    else:
        fields["religion"] = gap(NOT_AVAILABLE, PROVINCE_RELIGION_GAP)
    return record(
        f"PNG-{slug(name)}", name, level="admin1", parent="PNG", country="PNG",
        aliases=[PROVINCES[name]],
        population=measure(unit.total, year=CENSUS_2024, source=FINAL_FIGURES,
                           unit="persons"),
        sex_ratio=measure(unit.ratio, year=CENSUS_2024, source=FINAL_FIGURES,
                          unit="males_per_100_females"),
        language=collection_gap("PNG", "language"),
        ethnicity=collection_gap("PNG", "ethnicity"),
        sources=[{"field": "population/sex_ratio", "name": FINAL_FIGURES,
                  "url": FINAL_FIGURES_URL, "year": CENSUS_2024, "license": LICENCE},
                 {"field": "religion", "name": NATIONAL_REPORT,
                  "url": NATIONAL_REPORT_URL, "year": CENSUS_2011, "license": LICENCE}],
        **fields)


def district_record(province: str, shape: str, unit: Unit | None,
                    reason: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if unit is not None:
        fields["population"] = measure(unit.total, year=CENSUS_2024,
                                       source=FINAL_FIGURES, unit="persons")
        fields["sex_ratio"] = measure(unit.ratio, year=CENSUS_2024,
                                      source=FINAL_FIGURES,
                                      unit="males_per_100_females")
        fields["population_note"] = DISTRICT_NOTE
    else:
        fields["population"] = gap(NOT_AVAILABLE, reason)
    return record(
        f"PNG-{slug(province)}-{slug(shape)}", shape, level="admin2",
        parent=f"PNG-{slug(province)}", country="PNG",
        parent_name=province, parent_aliases=[PROVINCES[province]],
        religion=gap(NOT_AVAILABLE, DISTRICT_RELIGION_GAP),
        language=collection_gap("PNG", "language"),
        ethnicity=collection_gap("PNG", "ethnicity"),
        sources=[{"field": "population/sex_ratio", "name": FINAL_FIGURES,
                  "url": FINAL_FIGURES_URL, "year": CENSUS_2024, "license": LICENCE}],
        **fields)


# The shapes the boundary file draws in the four provinces whose district
# layout has since been redrawn. Written out so that those sixteen shapes get
# a record saying why they are empty, rather than no record at all.
SHAPES: dict[str, int] = {
    "Western": 3, "Gulf": 2, "Central": 4, "National Capital District": 1,
    "Milne Bay": 4, "Northern": 2, "Southern Highlands": 5, "Enga": 5,
    "Western Highlands": 4, "Chimbu": 6, "Eastern Highlands": 8, "Hela": 3,
    "Jiwaka": 3, "Morobe": 9, "Madang": 6, "East Sepik": 6, "West Sepik": 4,
    "Manus": 1, "New Ireland": 2, "East New Britain": 4, "West New Britain": 2,
    "Autonomous Region of Bougainville": 3,
}

REDRAWN_SHAPES: dict[str, tuple[str, ...]] = {
    "Western": ("Middle Fly District", "North Fly District", "South Fly District"),
    "Northern": ("Ijivitari District", "Sohe District"),
    "Morobe": ("Bulolo District", "Finschafen District", "Huon District",
               "Kabwum District", "Lae District", "Markham District",
               "Menyamya District", "Nawae District", "Tawae/Siassi District"),
    "West New Britain": ("Kandrian/Gloucester District", "Talasea District"),
}


def build() -> list[dict[str, Any]]:
    booklet = page_texts(FINAL_FIGURES_URL, "2024-final-figures.pdf")
    report = page_texts(NATIONAL_REPORT_URL, "2011-national-report.pdf")
    provinces = read_province_table(booklet)
    snapshots = read_snapshots(booklet)
    religion = read_main_religion(report)

    records = [province_record(name, provinces[name], religion.get(name))
               for name in PROVINCES]

    written = skipped = 0
    for province in PROVINCES:
        placed, left = place_districts(province, snapshots[province])
        if left:
            shapes = REDRAWN_SHAPES.get(province)
            if shapes is None:
                raise SystemExit(
                    f"png: {province} has districts with no shape ({left}) and is "
                    f"not among the provinces declared redrawn ({REDRAWN})")
            reason = REDRAWN_NOTE.format(
                n=len(snapshots[province]), m=len(shapes), province=province,
                new=" and ".join(left))
            for shape in shapes:
                records.append(district_record(province, shape, None, reason))
                skipped += 1
            continue
        if len(placed) != SHAPES[province]:
            raise SystemExit(
                f"png: {province}'s districts land on {len(placed)} shapes where "
                f"the boundary file draws {SHAPES[province]}: {sorted(placed)}")
        summed = sum(u.total for u in placed.values())
        if summed != provinces[province].total:
            raise SystemExit(
                f"png: {province}'s districts add to {summed:,}, not the printed "
                f"{provinces[province].total:,}")
        for shape, unit in sorted(placed.items()):
            records.append(district_record(province, shape, unit, ""))
            written += 1

    log(f"  districts: {written} shapes carry the 2024 count; {skipped} in "
        f"{len(REDRAWN)} provinces ({', '.join(REDRAWN)}) are left with a reason")
    return records


def probe() -> int:
    """What the two publications hold, and nothing written."""
    for label, url, name in (("2024 Final Figures", FINAL_FIGURES_URL,
                              "2024-final-figures.pdf"),
                             ("2011 National Report", NATIONAL_REPORT_URL,
                              "2011-national-report.pdf")):
        pages = page_texts(url, name)
        joined = "\n".join(pages).lower()
        log(f"== {label}: {len(pages)} pages")
        for word in ("religion", "ethnic", "mother tongue", "language", "literac",
                     "tokples", "catholic", "lutheran"):
            hits = sum(1 for page in pages if word in page.lower())
            log(f"   {word!r}: on {hits} page(s); {joined.count(word)} mention(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="report what the two publications hold, and write nothing")
    ap.add_argument("--out", default=None, help="write somewhere other than the default")
    args = ap.parse_args()
    if args.probe:
        return probe()
    log("png: the 2024 census head count and the 2011 census's provincial religion")
    records = build()
    from pathlib import Path  # noqa: PLC0415
    write_json(Path(args.out) if args.out else PROCESSED / "png.json", records)
    log(f"  wrote {len(records)} records "
        f"({sum(1 for r in records if r['level'] == 'admin1')} provinces, "
        f"{sum(1 for r in records if r['level'] == 'admin2')} districts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
