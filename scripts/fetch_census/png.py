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
of what the office publishes for a province. The shares run from 19.7%
(Southern Highlands, Hela) to 68.4% (Bougainville), so for most provinces the
record describes under half the people, and the panel says so by itself:
shares that fall short of 100 draw the chip "describes 68.4% of the
population". ``report_coverage`` prints every province's share into the run's
log and refuses a run where any of them reached the threshold that chip stops
at, because a lone denomination shown as a whole composition would be a quiet
untruth.

**The rest of each province is sold, not published.** Appendix 4 of the 2011
National Report lists the census products and their prices: the *Provincial
Report* at K40 a province, the *Basic Tables* -- "a set of 31 cross-classified
tables covering the main census topics at national and provincial level" -- at
K40 a set, the *Table Retrieval System* CD-ROM, which holds those tables down
to district and LLG, at K2,000, and a *User Service* that will prepare a table
"on application". None of them is a file. A second round of work looked for
any of it elsewhere -- the office's own complete file list, the DHS
StatCompiler API and its 519-page report, the 2022 SDES, the 2000 census, the
Internet Archive's copy of the NSO's old PRISM site, Wikipedia -- and found
religion published for Papua New Guinea as a country and never for a province.
Every route and what it answered is in docs/SOURCES.md.

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
district each was carved from. Which one is established from the two censuses
instead -- see ``CARVED`` and ``check_carved_unions`` -- and the new district
is summed into the shape it came out of, the same union the four above are.
The 2011 census, tabulated on the layout the boundary file draws, is what
makes that test possible: it comes from UN OCHA's Common Operational Dataset
and is committed under ``data/raw/png/``. All 87 shapes carry the 2024 count.

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
    python -m scripts.fetch_census.png --get https://example.org/x --terms religion
"""

from __future__ import annotations

import argparse
import csv
import json
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
    # The four established below, where the shape keeps the name of the
    # district it was and gains the one carved out of it.
    "Middle Fly District": ("Middle Fly", "Delta Fly"),
    "Ijivitari District": ("Ijivitari", "Popondetta"),
    "Bulolo District": ("Bulolo", "Wau/Waria"),
    "Talasea District": ("Talasea", "Nakanai"),
}

# Four districts of the 2024 layout correspond to no 2011 shape at all: each
# was carved out of one of its province's 2011 districts after the boundary
# file was drawn, and the booklet does not say which. Which one is *established*
# here rather than assumed, and `check_carved_unions` re-runs the establishing
# test on every run -- so a later edition whose figures stopped supporting one
# of these would refuse rather than quietly summing into the wrong shape.
#
# shape -> (province, the district carved out of it, what establishes it)
CARVED: dict[str, tuple[str, str, str]] = {
    "Middle Fly District": (
        "Western", "Delta Fly",
        "no other assignment is arithmetically possible: putting Delta Fly's "
        "76,097 on North Fly or South Fly needs that district to have grown "
        "184% or 167% since 2011 and Middle Fly to have lost half its people"),
    "Ijivitari District": (
        "Northern", "Popondetta",
        "Popondetta Urban LLG is one of Ijivitari's five in the office's own "
        "2011 ward tables, and the alternative has Ijivitari losing 45% of its "
        "people while its province gained 47%"),
    "Bulolo District": (
        "Morobe", "Wau/Waria",
        "Wau Rural and Waria Rural are both Bulolo LLGs in the office's own "
        "2011 ward tables, and every other district of Morobe would have to "
        "have grown by between 104% and 259%"),
    "Talasea District": (
        "West New Britain", "Nakanai",
        "the alternative puts Kandrian/Gloucester at +262% and Talasea at -47% "
        "against a province that grew 39%"),
}

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
UNION_NOTE = ("Counted by the 2024 National Population Census and summed from "
              "the {n} districts the census now draws inside this one -- {parts}"
              "{rest}")
UNION_REST = (" -- which together cover it and nothing else, every other district "
              "of {province} having a shape of its own.")
CARVED_WHY = (" {new} was carved out of this district after the boundary file "
              "was drawn and the census booklet does not say from which, so "
              "where it came from is established rather than published: {why}.")
RELIGION_NOTE = (
    "{group} was the largest denomination in this province at the 2011 "
    "census, with {pct}% of its citizen population -- and it is the only "
    "religion figure published for a province, the \"Main religion\" row of "
    "the Summary Indicators in the National Statistical Office's 2011 National "
    "Report. The remaining {rest}% is not a gap in the census but in what was "
    "published: the office sells the provincial tables rather than publishing "
    "them -- its Provincial Report at K40 a province and its 31 cross-"
    "classified Basic Tables at K40 a set, on paper and CD-ROM -- and no "
    "denominational breakdown for any province is online anywhere this project "
    "could reach.")
DISTRICT_RELIGION_GAP = (
    "The 2011 census asked religion, and the National Statistical Office "
    "publishes no answer below the province: its 2011 National Report gives "
    "each province one figure (its largest denomination) and the country the "
    "full table, and the 2024 census's Final Figures, the only district-level "
    "release, carries no religion on any of its 35 pages. The district tables "
    "exist in the office's priced Table Retrieval System CD-ROM, which is not "
    "published online.")
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

    def __init__(self, name: str, total: int, male: int, female: int,
                 parts: tuple[str, ...] = ()) -> None:
        self.name, self.total, self.male, self.female = name, total, male, female
        # The districts summed into this one, where the shape is a union.
        self.parts = parts

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


def place_districts(province: str, districts: list[Unit]) -> dict[str, Unit]:
    """The province's districts on the boundary file's shapes, or nothing.

    Returns ``{shape name: unit}``. A district that belongs to no declared
    union takes the shape of its own name, so a *new* district the census
    starts tabulating lands on a shape name the boundary file does not draw
    and the caller's count check refuses the province -- which is what should
    happen, since its ground came out of one of the shapes and the booklet
    does not say which.
    """
    by_name = {d.name: d for d in districts}
    placed: dict[str, Unit] = {}
    used: set[str] = set()
    for shape, parts in UNIONS.items():
        if all(p in by_name for p in parts):
            total = sum(by_name[p].total for p in parts)
            male = sum(by_name[p].male for p in parts)
            female = sum(by_name[p].female for p in parts)
            placed[shape] = Unit(shape, total, male, female, parts)
            used.update(parts)
    for name, unit in by_name.items():
        if name in used:
            continue
        shape = DISTRICT_ALIASES.get(name, f"{name} District")
        placed[shape] = unit
        used.add(name)
    return placed


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
        note = (UNION_NOTE.format(
                    n=len(unit.parts), parts=", ".join(unit.parts),
                    rest=(UNION_REST.format(province=province)
                          if SHAPES[province] > 1 else
                          ", which are the whole of it: the boundary file draws "
                          "this province as one shape."))
                if unit.parts else DISTRICT_NOTE)
        if shape in CARVED:
            _, carved, why = CARVED[shape]
            note += CARVED_WHY.format(new=carved, why=why)
        fields["population_note"] = note
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
                  "url": FINAL_FIGURES_URL, "year": CENSUS_2024,
                  "license": LICENCE}]
                + ([{"field": "population", "name": COD_PS, "url": COD_PS_URL,
                     "year": CENSUS_2011, "license": COD_PS_LICENCE}]
                   if shape in CARVED else []),
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

# ---------------------------------------------------------------------------
# The 2011 count, for the shapes the 2024 booklet cannot be placed on
# ---------------------------------------------------------------------------

# UN OCHA's Common Operational Dataset for population statistics, which
# publishes the 2011 census by province, district and local-level government.
# It is here for one reason: it is tabulated on the *2011* district layout,
# which is the layout the boundary file draws. The 2024 booklet is not -- it
# counts four districts that did not exist in 2011 and does not say what they
# were carved from, which is why sixteen shapes in four provinces carried no
# count at all. A thirteen-year-old figure for the right district is a true
# statement about that district; a recent figure for a district whose edges
# have moved is not, and there is no way to tell which of the two it would be.
COD_PS = ("UN OCHA Common Operational Dataset, Papua New Guinea subnational "
          "population statistics (COD-PS), from the National Statistical "
          "Office's 2011 National Population and Housing Census")
COD_PS_URL = "https://data.humdata.org/dataset/cod-ps-png"
COD_PS_API = ("https://data.humdata.org/api/3/action/"
              "package_show?id=cod-ps-png")
COD_PS_LICENCE = ("Creative Commons Attribution for Intergovernmental "
                  "Organisations (CC BY-IGO 3.0)")
COD_PS_DIR = RAW / "png"
COD_PS_FILES = {1: "png_admpop_adm1_2011_v2.csv", 2: "png_admpop_adm2_2011_v2.csv"}
# The census's own published headline, which the file has to reproduce.
NATIONAL_2011 = 7_275_324



def read_cod_ps(level: int) -> dict[str, Unit]:
    """The COD's rows for one level, keyed by the name it gives the unit.

    The file is UTF-8 with a byte-order mark, which ``csv`` reads as part of
    the first column's name unless the encoding says otherwise; that cost a
    KeyError on ``ADM1_EN`` before it was spelled out here.
    """
    path = COD_PS_DIR / COD_PS_FILES[level]
    if not path.exists():
        raise SystemExit(f"png: {path} is missing; run --fetch where there is "
                         f"network, or see docs/SOURCES.md")
    key = f"ADM{level}_EN"
    out: dict[str, Unit] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            name = (row.get(key) or "").strip()
            if not name:
                continue                      # the file ends with a blank line
            total, male, female = (int(row[c]) for c in ("T_TL", "M_TL", "F_TL"))
            if male + female != total:
                raise SystemExit(f"png: COD adm{level} row {name!r} has "
                                 f"{male:,} + {female:,} against {total:,}")
            out[name] = Unit(name, total, male, female)
    return out


def cod_districts() -> dict[str, Unit]:
    """The 2011 districts, checked against the census's own totals.

    Two controls, both the source's own: the 87 districts must add to the
    7,275,324 the census published, and each province's districts must add to
    that province's own row in the COD's first-level file. Nothing here is
    read unless both hold -- a transcription that reproduces neither of its
    publisher's totals is not the table it claims to be.
    """
    provinces, districts = read_cod_ps(1), read_cod_ps(2)
    total = sum(u.total for u in districts.values())
    if total != NATIONAL_2011:
        raise SystemExit(f"png: the COD's {len(districts)} districts add to "
                         f"{total:,}, not the census's {NATIONAL_2011:,}")
    by_province: dict[str, int] = {}
    with (COD_PS_DIR / COD_PS_FILES[2]).open(encoding="utf-8-sig", newline="") as h:
        for row in csv.DictReader(h):
            if row.get("ADM2_EN"):
                by_province[row["ADM1_EN"]] = (
                    by_province.get(row["ADM1_EN"], 0) + int(row["T_TL"]))
    for name, summed in sorted(by_province.items()):
        own = provinces[name].total
        if summed != own:
            raise SystemExit(f"png: the COD's districts of {name} add to "
                             f"{summed:,}, not its own {own:,}")
    # The dataset's caveat says the first level "does not refer to the National
    # Capital District or to the Autonomous Region of Bougainville", the one
    # being folded into Central and the other into North Solomons. That is
    # true of an earlier edition and not of the v2 tables: both have a row of
    # their own, Central's four districts add to its own 269,756 without
    # Moresby's 364,125 in them, and every level reconciles to the person
    # rather than to the "small differences ... due to rounding" the caveat
    # also warns of. It is checked rather than believed, because a republished
    # edition that did fold them would put 364,125 people in the wrong
    # province silently.
    for apart in ("National Capital District", "Autonomous Region of Bougainville"):
        if apart not in provinces:
            raise SystemExit(
                f"png: the COD's first level no longer has a row for {apart}; "
                f"its caveat about that province being combined with another "
                f"has come true and the districts cannot be trusted to their "
                f"parents")
    log(f"  COD 2011: {len(districts)} districts add to {total:,}, the census's "
        f"own figure; each province's add to its own row; and the caveat's two "
        f"combined provinces are separate in these tables")
    return districts


def growth(province: str, snapshots: list[Unit], cod: dict[str, Unit],
           carved_onto: dict[str, str]) -> dict[str, float]:
    """Each 2011 shape's growth to 2024, given an assignment of the carved
    districts. Returns percentages, and raises where a shape has no 2011 row."""
    now: dict[str, float] = {}
    for unit in snapshots:
        shape = DISTRICT_ALIASES.get(unit.name, f"{unit.name} District")
        shape = carved_onto.get(unit.name, shape)
        now[shape] = now.get(shape, 0.0) + unit.total
    out: dict[str, float] = {}
    for shape, total in now.items():
        was = cod.get(shape)
        if was is None or not was.total:
            raise SystemExit(f"png: {province}'s {shape} has no 2011 row to "
                             f"check the carved union against")
        out[shape] = 100.0 * (total - was.total) / was.total
    return out


def check_carved_unions(provinces: dict[str, Unit], snapshots: dict[str, list[Unit]],
                        cod: dict[str, Unit]) -> None:
    """Re-establish, from the two censuses, that each carved district came out
    of the shape ``CARVED`` says it did.

    The test is the one that established them. A district the 2024 booklet
    tabulates and the 2011 shapes do not contain came out of exactly one of
    its province's shapes, so there are as many candidate assignments as the
    province has shapes; the right one is the assignment under which no shape
    grew wildly out of step with its province. It is not a close call: for
    Delta Fly the two rejected assignments need North Fly or South Fly to have
    grown 184% or 167% while Middle Fly lost half its people, and for Nakanai
    the rejected one needs Kandrian/Gloucester at +262% and Talasea at -47%.

    Declared assignment must be the unique best -- strictly better than every
    alternative on the worst deviation from the province's own growth -- and
    must leave no shape shrinking while its province grows. Either failing
    refuses the run, because a sum onto the wrong shape is exactly the
    mis-match this project ranks above an empty cell.
    """
    for shape, (province, carved, _why) in sorted(CARVED.items()):
        units = snapshots[province]
        own = provinces[province]
        was = sum(cod[DISTRICT_ALIASES.get(u.name, f"{u.name} District")].total
                  for u in units if u.name != carved
                  and DISTRICT_ALIASES.get(u.name, f"{u.name} District") in cod)
        rate = 100.0 * (own.total - was) / was if was else 0.0
        scores: dict[str, float] = {}
        for candidate in sorted(
                {DISTRICT_ALIASES.get(u.name, f"{u.name} District")
                 for u in units if u.name != carved}):
            rates = growth(province, units, cod, {carved: candidate})
            scores[candidate] = max(abs(r - rate) for r in rates.values())
        best = min(scores, key=lambda k: (scores[k], k))
        runner = min((k for k in scores if k != best),
                     key=lambda k: (scores[k], k), default=None)
        if best != shape:
            raise SystemExit(
                f"png: {carved} is declared as carved out of {shape}, but the "
                f"two censuses fit {best} better ({scores[best]:.0f} against "
                f"{scores[shape]:.0f} points of deviation from {province}'s own "
                f"{rate:+.0f}%). The declaration in CARVED is wrong, or the "
                f"figures have changed.")
        shrinking = sorted(k for k, v in growth(province, units, cod,
                                                {carved: shape}).items() if v < 0)
        if shrinking:
            raise SystemExit(
                f"png: summing {carved} into {shape} leaves {', '.join(shrinking)} "
                f"smaller in 2024 than in 2011 while {province} grew {rate:+.0f}%")
        log(f"    {carved} -> {shape}: {scores[shape]:.0f} points of deviation "
            f"from {province}'s {rate:+.0f}%, against "
            + (f"{scores[runner]:.0f} for the next best ({runner})"
               if runner else "no alternative"))


def fetch_cod_ps() -> int:
    """Refresh the committed CSVs from HDX. Run where there is network.

    The download URL carries the resource's uuid, not its name, and a
    republished resource gets a new uuid -- so the catalogue entry is asked
    for the file by name rather than a link being written down here and
    rotting. The licence is logged rather than assumed, for the same reason.
    """
    catalogue = json.loads(http_get(COD_PS_API).decode("utf-8"))["result"]
    log(f"  {COD_PS_API}: {catalogue.get('license_title')!r} "
        f"({catalogue.get('license_id')}), {len(catalogue['resources'])} resources")
    by_name = {r["name"]: r for r in catalogue["resources"]}
    COD_PS_DIR.mkdir(parents=True, exist_ok=True)
    for level, name in sorted(COD_PS_FILES.items()):
        resource = by_name.get(name)
        if resource is None:
            raise SystemExit(f"png: HDX no longer publishes {name}; it holds "
                             f"{sorted(by_name)}")
        path = COD_PS_DIR / name
        path.write_bytes(http_get(resource["url"]))
        log(f"  adm{level}: {name} <- {resource['url']} "
            f"({path.stat().st_size:,} bytes)")
    return 0


REDRAWN_SHAPES: dict[str, tuple[str, ...]] = {
    "Western": ("Middle Fly District", "North Fly District", "South Fly District"),
    "Northern": ("Ijivitari District", "Sohe District"),
    "Morobe": ("Bulolo District", "Finschafen District", "Huon District",
               "Kabwum District", "Lae District", "Markham District",
               "Menyamya District", "Nawae District", "Tawae/Siassi District"),
    "West New Britain": ("Kandrian/Gloucester District", "Talasea District"),
}


# Where the rest of each province was looked for, and what came back. This is
# printed by every run: a gap that says why it is a gap has to say it where
# the run's reader is, and not only in docs/SOURCES.md.
ROUTES: tuple[tuple[str, str], ...] = (
    ("2011 National Report, all 100 pp",
     "religion on pp. 26-30 (the one provincial row), 32-34 (Table 2.4 and "
     "Figures 2.1-2.2, country only) and 85; no provincial table"),
    ("2011 National Report, Appendix 4 (p. 95)",
     "the provincial tables are priced products -- Provincial Report K40 a "
     "province, 31 Basic Tables K40 a set, Table Retrieval System CD-ROM "
     "K2,000 -- and none of them is a download"),
    ("nso.gov.pg sitemap, all 289 published files",
     "no provincial census report; nothing below the province carries religion"),
    ("2024 Final Figures (35 pp), 2011 Final Figures booklet (40 pp), "
     "ward tables (35 pp), 2021 provincial estimates (2 pp)",
     "religion on zero pages of any of them"),
    ("2000 National Report, three copies",
     "one 22,359,391-byte scan, 109 pp, zero extractable characters"),
    ("DHS StatCompiler API (api.dhsprogram.com)",
     "2.2 MB of indicators and no religion composition among them; religion "
     "is a DHS background characteristic, never an indicator"),
    ("DHS 2016-18 final report FR364 (519 pp)",
     "religion on 6 pages, crossed with province on none"),
    ("DHS microdata", "30 files named by the API, served only to a registered "
     "account; not attempted"),
    ("2022 SDES thematic workbooks",
     "sheet T2.4 is religion by Total/Urban/Rural and sex -- a 321-cluster "
     "national survey with no provincial estimates"),
    ("spc.int PRISM, via the Internet Archive",
     "the 2000 census page links no tables; popdemog.htm has three national "
     "rates (christian / non-christian / none)"),
    ("Wikipedia (Religion in PNG, province articles)",
     "national denominations only; no province article has a religion table"),
    ("pngnri.org via the Internet Archive (1,108 PDFs)",
     "atlas sheets of education and development indicators, not census tables"),
)

# The share above which the dashboard stops calling a composition partial
# (site/js/dashboard.js: a total under 95 draws "describes N% of the
# population"). Every PNG province must sit below it, because every one of
# them carries a single denomination and a reader has to be told so.
PARTIAL_BELOW = 95.0


def report_coverage(religion: dict[str, tuple[str, float]]) -> None:
    """What share of each province the one published denomination describes.

    The figure on a province is one denomination, so the record describes
    between a fifth and two thirds of the people on it and the panel says so
    by itself -- but only while every share stays under the threshold the
    dashboard draws that chip at. A province that crept over it would show as
    a complete composition of one group, which is the kind of quiet
    mis-statement this project ranks worse than an empty cell, so the run
    refuses rather than writing it.
    """
    covered = sorted(((pct, name) for name, (_, pct) in religion.items()))
    over = [name for pct, name in covered if pct >= PARTIAL_BELOW]
    if over:
        raise SystemExit(f"png: {over} carry a single denomination at "
                         f"{PARTIAL_BELOW}% or more, which the panel would show "
                         f"as a whole composition; refusing to publish that")
    log(f"  religion coverage: one denomination per province, describing "
        f"{covered[0][0]}% of {covered[0][1]} at the least and "
        f"{covered[-1][0]}% of {covered[-1][1]} at the most; all 22 below "
        f"{PARTIAL_BELOW}%, so every panel says what share it describes")
    for pct, name in covered:
        log(f"    {name:34s} {religion[name][0]:22s} {pct:5.1f}%")


def build() -> list[dict[str, Any]]:
    booklet = page_texts(FINAL_FIGURES_URL, "2024-final-figures.pdf")
    report = page_texts(NATIONAL_REPORT_URL, "2011-national-report.pdf")
    provinces = read_province_table(booklet)
    snapshots = read_snapshots(booklet)
    religion = read_main_religion(report)

    records = [province_record(name, provinces[name], religion.get(name))
               for name in PROVINCES]
    report_coverage(religion)

    check_carved_unions(provinces, snapshots, cod_districts())
    written = 0
    for province in PROVINCES:
        placed = place_districts(province, snapshots[province])
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

    log(f"  districts: all {written} shapes carry the 2024 count, {len(CARVED)} "
        f"of them summed with the district carved out of them since 2011 "
        f"({', '.join(new for _, new, _ in CARVED.values())})")
    log("  the rest of each province was looked for here, and is not published:")
    for route, answer in ROUTES:
        log(f"    {route}\n      -> {answer}")
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


def get(url: str, *, limit: int = 3000, find: str | None = None,
        terms: list[str] | None = None, context: int = 200) -> str | None:
    """Fetch one URL and print what was asked of it -- reconnaissance, no writes.

    The same shape as ``mongolia.py``'s ``--get``: a URL, and either a regex
    whose distinct matches are printed (a CDX listing, a sitemap), or a list of
    words whose surroundings are printed (an API's JSON), or neither, in which
    case the first ``limit`` characters are. An unreachable host prints its
    exception and the next URL is still tried, because the reason a route is
    closed is the product of the run.
    """
    try:
        body = http_get(url, cache=False, retries=1, timeout=120,
                        headers={"Accept": "application/json, text/xml, */*"})
    except Exception as exc:            # noqa: BLE001 - the probe's product is the reason
        log(f"  {url}\n    unreachable: {type(exc).__name__}: {exc}")
        return None
    text = body if isinstance(body, str) else body.decode("utf-8", "replace")
    log(f"  {url}\n    {len(text):,} chars")
    if find:
        hits = sorted({m.group(0) for m in re.finditer(find, text)})
        log(f"    {len(hits)} distinct match(es) for {find!r}")
        for hit in hits[:300]:
            log(f"      {hit}")
    elif terms:
        for term in terms:
            seen = 0
            at = text.find(term)
            while at >= 0 and seen < 12:
                lo, hi = max(0, at - context), min(len(text), at + len(term) + context)
                log(f"    [{term} @{at}] ...{text[lo:hi]}...")
                seen += 1
                at = text.find(term, at + 1)
            if not seen:
                log(f"    [{term}] not present")
    else:
        log("    " + text[:limit].replace("\n", "\n    "))
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="report what the two publications hold, and write nothing")
    ap.add_argument("--get", action="append",
                    help="fetch this URL and print what --find or --terms asks "
                         "of it, writing nothing")
    ap.add_argument("--find",
                    help="with --get, print the distinct matches of this regex")
    ap.add_argument("--terms",
                    help="with --get, comma-separated words whose surroundings "
                         "to print")
    ap.add_argument("--context", type=int, default=200,
                    help="with --get --terms, characters either side")
    ap.add_argument("--bytes", type=int, default=3000,
                    help="with --get and neither --find nor --terms, how much "
                         "of the body to print")
    ap.add_argument("--fetch", action="store_true",
                    help="refresh the committed COD-PS CSVs from HDX and write "
                         "nothing else; run where there is network")
    ap.add_argument("--out", default=None, help="write somewhere other than the default")
    args = ap.parse_args()
    if args.fetch:
        return fetch_cod_ps()
    if args.get:
        for url in args.get:
            get(url, limit=args.bytes, find=args.find,
                terms=args.terms.split(",") if args.terms else None,
                context=args.context)
        return 0
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
