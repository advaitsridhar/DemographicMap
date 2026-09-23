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
from .europe_wiki import cell_text, fetch, number, sections
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
    # The header of the column the row is labelled in, where it is not the first.
    key: str | None = None
    # Where the column's header names no year: a citation in the table's own
    # section that does, such as the census the table transcribes.
    cite: str | None = None


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
    # The boundary file's Maputo holds the capital as well as the province
    # around it. Not the sum of the two articles' infoboxes: those print
    # 1,968,906 and 1,088,449, each "2017 census", from two different
    # releases of it, where the list of provinces prints one release for all
    # eleven -- the one the map's other provinces already carry, eight of the
    # nine to the person.
    ("MOZ", "Maputo"): Figure(
        year=2017,
        terms=(Term("Provinces of Mozambique", row="Maputo City", key=r"^Province$",
                    column=r"Population \(2017 census\)"),
               Term("Provinces of Mozambique", row="Maputo", key=r"^Province$",
                    column=r"Population \(2017 census\)")),
        source="2017 census of Mozambique, as the list of its provinces gives it",
        note=("The boundary file draws Maputo City and Maputo Province as one "
              "shape; this is the sum of their rows: {terms}.")),
    # Somalia's regions, in one list with one date.
    ("SOM", "Bakool"): Figure(
        year=2025,
        terms=(Term("Administrative divisions of Somalia", row="Bakool Region",
                    column=r"Population \(2025 estimate\)"),),
        source="2025 estimate, as the list of Somalia's regions gives it",
        note=("Bakool's own article prints its population as '1,15,6400', which is "
              "no number; this is its row in the list of regions: {terms}.")),
}

# The Bahamas' 2022 census by district, as "Local government in the Bahamas"
# transcribes it. The table groups some districts the map draws apart --
# "South Abaco + Central Abaco + Moore's Island" -- and those stay empty: a
# group's figure is not any one of its members'. These three it prints alone.
for _district in ("North Eleuthera", "East Grand Bahama", "West Grand Bahama"):
    FIGURES[("BHS", _district)] = Figure(
        year=2022,
        terms=(Term("Local government in the Bahamas", row=_district,
                    column=r"^Population$", cite=r"Census of The Bahamas 2022"),),
        source="2022 census of the Bahamas, as Wikipedia's list of its districts gives it",
        note="The district's row in the 2022 census table: {terms}.")


def cell(wikitext: str, row: str, column: str, year: int,
         key: str | None = None, cite: str | None = None) -> tuple[int | None, str]:
    """The one table cell under a header naming ``year``, in the row labelled ``row``.

    A table without the row says nothing about it, dated or not; a table with
    it that cannot be dated or lined up refuses the whole reading, because
    the row it holds might be the one meant.
    """
    header = re.compile(column, re.I)
    found: list[int] = []
    for _, body in sections(wikitext):
        for table in tables(body):
            if not table:
                continue
            heads = [cell_text(c) for c in table[0]]
            at = [i for i, h in enumerate(heads) if header.search(h)]
            labels = [i for i, h in enumerate(heads) if key and re.search(key, h, re.I)]
            if len(at) != 1 or (key and len(labels) != 1):
                continue
            by = labels[0] if key else 0
            hits = [c for c in table[1:]
                    if len(c) > by and cell_text(c[by]).casefold() == row.casefold()]
            if not hits:
                continue
            cited = cite and str(year) in cite and re.search(cite, body, re.I)
            if str(year) not in heads[at[0]] and not cited:
                return None, (f"the column {heads[at[0]]!r} does not name {year}"
                              + (f", and its section cites nothing matching {cite!r}"
                                 if cite else ""))
            for cells in hits:
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
    value, why = cell(wikitext, term.row, term.column or "", year, term.key, term.cite)
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
        if url(landed) not in {src["url"] for src in sources}:
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
