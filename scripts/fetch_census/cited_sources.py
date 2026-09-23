"""First-level populations read from the source a Wikipedia article cites, where
the article's own figure garbles or contradicts it.

The readers in wiki_population take an infobox at its word. That is the rule
the owner set -- use the figure Wikipedia has -- and it assumes the figure is
the one its citation gives. For two countries it is not, and this reads the
cited source instead:

* Somalia. Every region's article cites citypopulation.de, whose table gives
  each of the eighteen pre-war regions OCHA's calculation for 2019. Six of the
  articles print something else, and always more: Hiiraan's "2,566,400" is the
  table's 566,400 with a "2," in front, and Bakool's "1,15,6400" is not a
  number at all. Summed, the map's regions came to 21.0 million against the
  table's 15.6 million for the same year. The whole country is read from the
  table, so its eighteen regions share one source and one date.

* Seychelles. The Outer Islands' article prints "1.032" and cites the National
  Bureau of Statistics' mid-2019 bulletin, whose Table 10 gives the district
  ("Other Islands") 574 for mid-2019 and 1,042 at the 2010 census; 1,032 is
  in neither. The bureau's server refuses this runner, so the bulletin is read
  from the Internet Archive's copy of the same address.

Each table is held to its own total before anything is written: Somalia's
regions must add to the table's national row in two columns, which is also
what proves the columns were lined up, and the Seychelles districts to the
bulletin's Total row.

Usage:
    python -m scripts.fetch_census.cited_sources
"""

from __future__ import annotations

import io
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, read_json, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = "cited_sources.json"

# ---------------------------------------------------------------------------
# Somalia
# ---------------------------------------------------------------------------

SOMALIA_URL = "https://www.citypopulation.de/en/somalia/"
SOMALIA_YEAR = 2019
# The table's name for each region (before any bracketed alternative), and the
# boundary file's. Declared rather than matched: "Banaadir" and "Banadir" are
# one place, and the Juba and Shabeellaha regions are named in Somali there
# and in English here.
SOMALIA = {
    "Awdal": "Awdal", "Bakool": "Bakool", "Banaadir": "Banadir", "Bari": "Bari",
    "Bay": "Bay", "Galgaduud": "Galgaduud", "Gedo": "Gedo", "Hiiraan": "Hiiraan",
    "Jubbada Dhexe": "Middle Juba", "Jubbada Hoose": "Lower Juba", "Mudug": "Mudug",
    "Nugaal": "Nugaal", "Sanaag": "Sanaag", "Shabeellaha Dhexe": "Middle Shebelle",
    "Shabeellaha Hoose": "Lower Shebelle", "Sool": "Sool", "Togdheer": "Togdheer",
    "Woqooyi Galbeed": "Woqooyi Galbeed",
}
# How far the regions may sum from the national row: the table rounds each
# 2019 figure to the hundred, so eighteen of them drift by at most 900.
SUM_SLACK = 0.001


class Tables(HTMLParser):
    """Every table's rows, as lists of cell texts, nested tables included.

    A cell belongs to the innermost table it sits in, so a table used for page
    layout does not swallow the data table inside it.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.open: list[list[list[str]]] = []
        self.cells: list[list[str] | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.open.append([])
            self.tables.append(self.open[-1])
            self.cells.append(None)
        elif not self.open:
            return
        elif tag == "tr":
            self.open[-1].append([])
        elif tag in ("td", "th") and self.open[-1]:
            self.cells[-1] = []
        elif tag == "br" and self.cells[-1] is not None:
            self.cells[-1].append(" ")

    def handle_endtag(self, tag: str) -> None:
        if not self.open:
            return
        if tag == "table":
            self.open.pop()
            self.cells.pop()
        elif tag in ("td", "th") and self.cells[-1] is not None:
            self.open[-1][-1].append(" ".join("".join(self.cells[-1]).split()))
            self.cells[-1] = None

    def handle_data(self, data: str) -> None:
        if self.cells and self.cells[-1] is not None:
            self.cells[-1].append(data)


def count(text: str) -> int | None:
    digits = text.replace(",", "").strip()
    return int(digits) if re.fullmatch(r"\d+", digits) else None


def main_name(text: str) -> str:
    """ "Jubbada Hoose [ Lower Juba ]" -> "Jubbada Hoose"; "( Galguduud )" likewise."""
    return re.split(r"\s*[\[(]", text, maxsplit=1)[0].strip()


def somalia_rows(html: str) -> tuple[dict[str, int], str]:
    """{table name: 2019 figure} for the eighteen regions, or why not."""
    parser = Tables()
    parser.feed(html)
    why = "no table on the page has a 2019 column"
    for table in parser.tables:
        figures, refused = somalia_table(table)
        if figures:
            return figures, ""
        if refused:
            why = refused
            log(f"  SOM: a table was refused ({refused}); its first rows: "
                + " / ".join(" | ".join(r) for r in table[:3])[:600])
    return {}, why


def somalia_table(table: list[list[str]]) -> tuple[dict[str, int], str]:
    """The regions' figures from one table; ({}, "") where it is not the table."""
    heads = next((r for r in table if any("2019" in c for c in r)), None)
    if not heads:
        return {}, ""
    rows = {main_name(r[0]): r for r in table if r}
    if not any(name in rows for name in SOMALIA):
        return {}, ""
    at = {year: [i for i, h in enumerate(heads) if str(year) in h] for year in (2014, 2019)}
    if any(len(v) != 1 for v in at.values()):
        return {}, f"the header {heads} does not name 2014 and 2019 once each"
    rows = {name: r for name, r in rows.items() if len(r) > max(at[2019][0], at[2014][0])}
    nation = rows.get("Somalia")
    if not nation:
        return {}, "the table has no national row to check the regions against"
    found = {name: rows[name] for name in SOMALIA if name in rows}
    missing = sorted(set(SOMALIA) - set(found))
    if missing:
        return {}, f"the table lacks {', '.join(missing)}"
    for year, (i,) in at.items():
        whole = count(nation[i])
        parts = [count(r[i]) for r in found.values()]
        if whole is None or any(p is None for p in parts):
            return {}, f"a {year} cell is not a count"
        total = sum(p for p in parts if p is not None)
        if abs(total - whole) > SUM_SLACK * whole:
            return {}, (f"the regions' {year} figures sum to {total:,} against "
                        f"the national row's {whole:,}; the columns are not "
                        f"where the header says")
    # The sums prove each column is whole; they cannot prove which year a
    # column is, since every column adds up to its own national figure. The
    # figures can: OCHA's 2019 calculation is rounded to the hundred and
    # the 2014 survey's are exact, so a header shifted by a cell shows.
    i, j = at[2019][0], at[2014][0]
    if any((count(r[i]) or 0) % 100 for r in found.values()) or \
            all((count(r[j]) or 0) % 100 == 0 for r in found.values()):
        return {}, ("the column headed 2019 is not rounded to the hundred, or the "
                    "one headed 2014 is: the header does not sit over its figures")
    return {name: count(r[i]) or 0 for name, r in found.items()}, ""


def somalia(drawn: dict[str, str]) -> list[dict[str, Any]]:
    html = http_get(SOMALIA_URL)
    assert isinstance(html, str)
    figures, why = somalia_rows(html)
    if why:
        log(f"  SOM: {why}; nothing written")
        return []
    out = []
    for name, value in figures.items():
        shape = SOMALIA[name]
        if shape not in drawn:
            log(f"  SOM: the map draws no {shape!r}; nothing written")
            return []
        log(f"  SOM {shape}: {value:,}")
        out.append(record(
            f"SOM-CP-{shape.replace(' ', '-')}", shape, level="admin1", parent="SOM",
            country="SOM", shape_id=drawn[shape], match_by="shape_id",
            population=measure(
                value, unit="people", year=SOMALIA_YEAR,
                source="OCHA Somalia, 2019 calculation, as citypopulation.de tabulates it",
                note=("An estimate, not a count: the calculation for 1 January 2019 by "
                      "OCHA Somalia's Information Management Working Group, for the "
                      "eighteen pre-war regions, from the citypopulation.de table the "
                      "region's Wikipedia article cites. Read for every region from "
                      "the one table, because several articles print figures that "
                      "table does not give.")),
            sources=[{"field": "population",
                      "name": "citypopulation.de (Thomas Brinkhoff), after OCHA Somalia",
                      "url": SOMALIA_URL, "year": SOMALIA_YEAR,
                      "license": "citation of citypopulation.de required"}]))
    return out


# ---------------------------------------------------------------------------
# Seychelles
# ---------------------------------------------------------------------------

NBS_URL = "https://www.nbs.gov.sc/downloads/mid-2019-population-bulletin/viewdocument"
NBS_ARCHIVED = "https://web.archive.org/web/2021id_/" + NBS_URL
SEYCHELLES_YEAR = 2019
# The bulletin's row and the map's shape. The bulletin calls the Outer Islands
# district "Other Islands"; La Digue and the Inner Islands have a row of their
# own, so nothing else is in it.
SEYCHELLES = {"Other Islands": "Outer Islands"}


def seychelles_rows(text: str) -> tuple[dict[str, int], str]:
    """{row label: mid-2019 figure} from Table 10, checked against its Total row."""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    try:
        start = next(i for i, line in enumerate(lines)
                     if line.startswith("District Census 2010"))
    except StopIteration:
        return {}, "no Table 10 header ('District Census 2010 ...') in the bulletin"
    years = [int(y) for y in re.findall(r"\b(20\d\d)\b", lines[start])]
    if SEYCHELLES_YEAR not in years:
        return {}, f"Table 10's header {lines[start]!r} has no {SEYCHELLES_YEAR}"
    at = years.index(SEYCHELLES_YEAR)
    rows: dict[str, list[int]] = {}
    for line in lines[start + 1:]:
        m = re.match(r"^([A-Za-z][A-Za-z' ]*?)\s+((?:\d{1,3}(?:,\d{3})*\s*)+)$", line)
        if not m:
            if rows:
                break
            continue
        rows[m.group(1)] = [int(v.replace(",", "")) for v in m.group(2).split()]
    total = rows.pop("Total", None)
    if not total or len(total) != len(years):
        return {}, "Table 10 has no Total row of one figure per year"
    # Rows with a figure for every year; Perseverance, new in 2017, has fewer
    # and is added from the right.
    column = [r[at - len(years)] for r in rows.values() if len(r) >= len(years) - at]
    # Each estimate is rounded to a person, so the column may miss its total
    # by up to half a person a row: 97,624 against 97,625 for mid-2019.
    if abs(sum(column) - total[at]) > len(column) / 2:
        return {}, (f"the districts' {SEYCHELLES_YEAR} figures sum to {sum(column):,} "
                    f"against the Total row's {total[at]:,}")
    out = {}
    for label in SEYCHELLES:
        row = rows.get(label)
        if not row or len(row) != len(years):
            return {}, f"Table 10 has no full {label!r} row"
        out[label] = row[at]
    return out, ""


def seychelles(drawn: dict[str, str]) -> list[dict[str, Any]]:
    from pypdf import PdfReader

    # The PDF probe's fetch, which read this address on 23 September 2026:
    # the archive redirected http_get's request back to the bureau, which
    # refuses this runner.
    from probe_pdf import fetch_blob

    for wait in (30, 90, None):
        try:
            blob = fetch_blob(NBS_ARCHIVED)
            break
        except OSError as exc:  # the archive refuses or times out now and then
            if wait is None:
                log(f"  SYC: the archive did not answer ({exc}); nothing written")
                return []
            log(f"  SYC: the archive did not answer ({exc}); waiting {wait}s")
            time.sleep(wait)
    text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(blob)).pages)
    figures, why = seychelles_rows(text)
    if why:
        log(f"  SYC: {why}; nothing written")
        return []
    out = []
    for label, value in figures.items():
        shape = SEYCHELLES[label]
        if shape not in drawn:
            log(f"  SYC: the map draws no {shape!r}; nothing written")
            continue
        log(f"  SYC {shape}: {value:,} (Table 10, {label!r}, mid-{SEYCHELLES_YEAR})")
        out.append(record(
            f"SYC-NBS-{shape.replace(' ', '-')}", shape, level="admin1", parent="SYC",
            country="SYC", shape_id=drawn[shape], match_by="shape_id",
            population=measure(
                value, unit="people", year=SEYCHELLES_YEAR,
                source="National Bureau of Statistics, Seychelles, mid-2019 bulletin, Table 10",
                note=(f"The bulletin's mid-2019 estimate for its '{label}' row, which is "
                      f"this district. The Wikipedia article cites this bulletin and "
                      f"prints '1.032', a figure the bulletin does not give: its row "
                      f"reads 1,042 at the 2010 census and {value:,} for mid-2019.")),
            sources=[{"field": "population", "name": "National Bureau of Statistics, Seychelles",
                      "url": NBS_URL, "year": SEYCHELLES_YEAR,
                      "note": f"read from the Internet Archive's copy, {NBS_ARCHIVED}"}]))
    return out


def drawn(iso3: str) -> dict[str, str]:
    return {u["name"]: u["id"]
            for u in read_json(ROOT / "site" / "data" / "admin1" / f"{iso3}.json", [])}


def dump() -> None:
    """Print every table citypopulation.de's page parses into, for a reader to see."""
    html = http_get(SOMALIA_URL)
    assert isinstance(html, str)
    parser = Tables()
    parser.feed(html)
    log(f"{len(html):,} characters, {html.count('<table')} '<table' tags, "
        f"{len(parser.tables)} tables parsed")
    for n, table in enumerate(parser.tables):
        log(f"-- table {n}: {len(table)} rows")
        for row in table[:6]:
            log("   " + " | ".join(row)[:300])
    at = html.find("Bakool")
    log("around 'Bakool': " + " ".join(html[max(0, at - 1500):at + 400].split()))


def main() -> None:
    if "--dump" in sys.argv:
        dump()
        return
    rows = somalia(drawn("SOM")) + seychelles(drawn("SYC"))
    write_json(PROCESSED / OUT, rows)
    log(f"wrote {len(rows)} records to {OUT}")


if __name__ == "__main__":
    main()
