"""First-level populations that no one article's infobox holds, by declared arithmetic.

wiki_population reads a unit's own infobox, and sums several where the map
draws two units as one. What it cannot read is a figure that lives in a list
article's table, or a unit that is what is left of its country once another
unit is taken away. This reads exactly those, one declaration at a time.

Every term is held to the year it declares. A table's figure is taken only
from a column whose header prints that year, and an infobox's only where the
infobox dates it to that year; a term that fails says so and nothing is
written for the unit. That is the whole guard against the obvious mistake,
which is to subtract a unit's census count from a national estimate: Italy's
Factbook total less its other four macro-regions would give the south 15.3
million people where its six regions hold 13.3.

The output is a floor, like wiki_population's: it fills a population the
build has nothing for and never replaces one a source published.

Usage:
    python -m scripts.fetch_census.wiki_table_population
"""

from __future__ import annotations

import re
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, measure, read_json, record, write_json
from .europe_wiki import cell_text, fetch, number
from .wiki_population import read as infobox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import slugify  # noqa: E402
from probe_wikitable import tables  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = "wiki_table_population.json"
LICENCE = "CC BY-SA 4.0"


@dataclass(frozen=True)
class Term:
    """One figure: a table cell (row and column given) or an infobox (neither)."""
    title: str
    row: str | None = None
    column: str | None = None
    sign: int = 1


@dataclass(frozen=True)
class Figure:
    year: int
    terms: tuple[Term, ...]
    # What the panel prints under the figure: how it was reached, and what
    # it does not count.
    note: str
    source: str


FIGURES: dict[tuple[str, str], Figure] = {
    # The map draws Azerbaijan as Nakhchivan and the rest. The 2019 census
    # published the country's total and Nakhchivan's, so the rest is their
    # difference -- one census, one date, no estimate in it.
    ("AZE", "Contiguous Azerbaijan"): Figure(
        year=2019,
        terms=(Term("Demographics of Azerbaijan", row="Total", column=r"Census 2019"),
               Term("Nakhchivan Autonomous Republic", sign=-1)),
        source="2019 census of Azerbaijan, as the national total less Nakhchivan's",
        note=("Derived by subtraction within the 2019 census: {terms}. The census "
              "did not enumerate the area then held by the self-declared Republic "
              "of Artsakh -- it counted 178 Armenians in the whole country -- so "
              "that area's Armenian population is not in this figure.")),
    # Basse local government area is the Upper River Region. Its own
    # article's infobox leaves population_total empty; the list of the
    # country's regions carries the 2024 census figure.
    ("GMB", "Basse"): Figure(
        year=2024,
        terms=(Term("Subdivisions of the Gambia", row="Upper River",
                    column=r"Population \(2024\)"),),
        source="2024 census of the Gambia, as the list of its regions gives it",
        note=("Basse local government area is the Upper River Region, whose 2024 "
              "census figure is {terms}.")),
}


def cell(wikitext: str, row: str, column: str, year: int) -> tuple[int | None, str]:
    """The one table cell under a header naming ``year``, in the row labelled ``row``."""
    header = re.compile(column, re.I)
    found: list[int] = []
    for table in tables(wikitext):
        if not table:
            continue
        heads = [cell_text(c) for c in table[0]]
        at = [i for i, h in enumerate(heads) if header.search(h)]
        if len(at) != 1:
            continue
        if str(year) not in heads[at[0]]:
            return None, f"the column {heads[at[0]]!r} does not name {year}"
        for cells in table[1:]:
            if not cells or cell_text(cells[0]).casefold() != row.casefold():
                continue
            # Merged cells are not expanded, so a row that is shorter or
            # longer than its header cannot be lined up with it.
            if len(cells) != len(heads):
                return None, (f"the {row!r} row has {len(cells)} cells against "
                              f"{len(heads)} headers, so its columns cannot be lined up")
            value = number(cell_text(cells[at[0]]), ".")
            if value is None or value != int(value):
                return None, f"the {row!r} row's cell is {cells[at[0]]!r}, not a count"
            found.append(int(value))
    if len(found) != 1:
        return None, (f"{len(found)} tables have a {row!r} row under a column "
                      f"matching {column!r}; exactly one is read")
    return found[0], ""


def term_value(term: Term, year: int, fetcher=fetch) -> tuple[int | None, str, str]:
    """(value, the title it landed on, why not)."""
    wikitext, landed = fetcher(term.title, "en")
    if not wikitext:
        return None, landed, "the article has no wikitext"
    if term.row is None:
        value, found, remark = infobox(wikitext)
        if value is None:
            return None, landed, remark
        if found != year:
            return None, landed, f"its infobox dates the figure to {found}, not {year}"
        return value, landed, ""
    value, why = cell(wikitext, term.row, term.column or "", year)
    return value, landed, why


def url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def figure_row(iso3: str, name: str, figure: Figure, shape_id: str,
               fetcher=fetch) -> dict[str, Any] | None:
    total, said, sources = 0, [], []
    for term in figure.terms:
        value, landed, why = term_value(term, figure.year, fetcher)
        if value is None:
            log(f"  {iso3} {name}: {landed}: {why}; not written")
            return None
        total += term.sign * value
        where = f"the {term.row} row of {landed}" if term.row else f"{landed}'s infobox"
        joined = "" if not said else (" less " if term.sign < 0 else " plus ")
        said.append(f"{joined}{value:,} ({where})")
        sources.append({"field": "population", "name": "Wikipedia", "url": url(landed),
                        "year": figure.year, "license": LICENCE})
    if total <= 0:
        log(f"  {iso3} {name}: the terms come to {total:,}; not written")
        return None
    terms = "".join(said)
    log(f"  {iso3} {name}: {total:,} from {terms}")
    return record(
        f"{iso3}-WT-{slugify(name)}", name, level="admin1", parent=iso3, country=iso3,
        shape_id=shape_id, match_by="shape_id",
        population=measure(total, unit="people", year=figure.year, source=figure.source,
                           note=figure.note.format(terms=terms)),
        sources=sources)


def main() -> None:
    rows: list[dict[str, Any]] = []
    for (iso3, name), figure in FIGURES.items():
        drawn = [u for u in read_json(ROOT / "site" / "data" / "admin1" / f"{iso3}.json", [])
                 if u.get("name") == name]
        if len(drawn) != 1:
            log(f"  {iso3} {name}: drawn {len(drawn)} times; not written")
            continue
        row = figure_row(iso3, name, figure, drawn[0]["id"])
        if row:
            rows.append(row)
    write_json(PROCESSED / OUT, rows)
    log(f"wrote {len(rows)} records to {OUT}")


if __name__ == "__main__":
    main()
