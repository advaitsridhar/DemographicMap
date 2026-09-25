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

from ._shared import PROCESSED, http_json, log, measure, read_json, record, write_json
from .cited_sources import Tables
from .europe_wiki import cell_text, fetch, number, sections
from .wiki_population import read as infobox

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import slugify  # noqa: E402
from probe_wikitable import tables  # noqa: E402
from common import shard_path  # noqa: E402

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
    # Read the table as the page renders it rather than from its wikitext:
    # for a table written in a way the wikitext reader cannot split into
    # cells, or with merged cells, which the rendered page expands.
    rendered: bool = False


@dataclass(frozen=True)
class Figure:
    # None where the source gives the figure no year: it is published as
    # undated, as the owner's rule has it, and says so.
    year: int | None
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
}

# Peru's 2025 census, for the two shapes the boundary file makes of Lima:
# the metropolitan province, and the department's other provinces around it.
# Wikidata's "Lima Department" (11.6 million) counts both, and the build no
# longer joins it to either (NOT_THIS_SHAPE).
FIGURES[("PER", "Lima")] = Figure(
    year=2025,
    terms=(Term("Department of Lima"),),
    source="2025 census of Peru, as English Wikipedia's Department of Lima gives it",
    note=("The Department of Lima without Metropolitan Lima, which the map draws as "
          "a shape of its own: {terms}."))
FIGURES[("PER", "Municipalidad Metropolitana de Lima")] = Figure(
    year=2025,
    terms=(Term("Lima"),),
    source="2025 census of Peru, as English Wikipedia's Lima gives it",
    note=("Metropolitan Lima, the province: {terms}. INEI's release of the 2025 "
          "census gives it as 9.6 million, rounded to a tenth of a million, and "
          "the article prints the same."))
# Dar es Salaam Region's own district table ends in the region's total.
FIGURES[("TZA", "Dar es Salaam")] = Figure(
    year=2022,
    terms=(Term("Dar es Salaam Region", row="Dar es Salaam Region",
                column=r"Population \(2022\)"),),
    source="2022 census of Tanzania, as the region's own district table gives it",
    note="The region's row in its district table: {terms}.")
# Cape Verde's municipalities by the 2021 census. The list writes each row
# on one line with single bars, which the wikitext reader cannot split, so
# the table is read as the page renders it.
for _name in ("Ribeira Grande de Santiago", "Santa Catarina", "Santa Catarina do Fogo",
              "Santa Cruz", "São Domingos", "São Lourenço dos Órgãos", "São Miguel",
              "São Salvador do Mundo"):
    FIGURES[("CPV", _name)] = Figure(
        year=2021,
        terms=(Term("Administrative divisions of Cape Verde", row=f"Municipality of {_name}",
                    key=r"^Municipality$", column=r"Population \(2021 Census\)",
                    rendered=True),),
        source="2021 census of Cape Verde, as the list of its municipalities gives it",
        note="The municipality's row in the list, under its 2021 census column: {terms}.")
# Yamoussoukro Autonomous District. Its article redirects to the city's,
# whose 422,072 (2021) covers 2,075 km^2 of the district's 3,500 and so is
# not the district's. The list of districts gives the district a figure and
# no year, and is read as that: undated.
FIGURES[("CIV", "District Autonome De Yamoussoukro")] = Figure(
    year=None,
    terms=(Term("Districts of Ivory Coast", row="Yamoussoukro",
                key=r"^District$", column=r"^Population \(District\)", rendered=True),),
    source=("English Wikipedia, Districts of Ivory Coast; the list gives no year "
            "for the figure"),
    note=("The district's row in the list of districts, which dates none of its "
          "figures: {terms}. The city's article gives 422,072 for 2021, over 2,075 "
          "km² of the district's 3,500, so that figure is not the district's."))

# Five of Libya's shapes are districts of the 2001 scheme, which the 2007
# scheme merged away. The list of districts keeps the 2001 table, whose
# population column gives no year: undated.
for _shape, _row in (("Ajdabiya", "Ajdabiya"), ("Al Qubbah", "Quba"),
                     ("Ghadamis", "Ghadames"), ("Mizdah", "Mizda"),
                     ("Tajura' wa an Nawahi al Arba", "Tajura wa Arba‘")):
    FIGURES[("LBY", _shape)] = Figure(
        year=None,
        terms=(Term("Districts of Libya", row=_row, key=r"^Sha.biyah$",
                    column=r"^Population$"),),
        source=("English Wikipedia, Districts of Libya (the 32 districts of 2001); the "
                "table gives no year for the figure"),
        note="The district's row in the table of the 2001 districts, which gives no year: {terms}.")

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


def cell(wikitext: str, row: str, column: str, year: int | None,
         key: str | None = None, cite: str | None = None,
         pairs: list[tuple[str, list[list[str]]]] | None = None) -> tuple[int | None, str]:
    """The one table cell under a header naming ``year``, in the row labelled ``row``.

    A table without the row says nothing about it, dated or not; a table with
    it that cannot be dated or lined up refuses the whole reading, because
    the row it holds might be the one meant. The header is the first row
    that has the column in it, since a table may open with a caption row.
    ``year`` None reads a figure the table does not date, which the caller
    then publishes as undated.
    """
    header = re.compile(column, re.I)
    found: list[int] = []
    if pairs is None:
        pairs = [(body, table) for _, body in sections(wikitext) for table in tables(body)]
    for body, table in pairs:
        start = next((n for n, r in enumerate(table[:4])
                      if sum(1 for c in r if header.search(cell_text(c))) == 1), None)
        if start is None:
            continue
        heads = [cell_text(c) for c in table[start]]
        at = [i for i, h in enumerate(heads) if header.search(h)]
        labels = [i for i, h in enumerate(heads) if key and re.search(key, h, re.I)]
        if key and len(labels) != 1:
            continue
        by = labels[0] if key else 0
        hits = [c for c in table[start + 1:] if len(c) > by and labelled(c[by], row)]
        if not hits:
            continue
        cited = year and cite and str(year) in cite and re.search(cite, body, re.I)
        if year and str(year) not in heads[at[0]] and not cited:
            return None, (f"the column {heads[at[0]]!r} does not name {year}"
                          + (f", and its section cites nothing matching {cite!r}"
                             if cite else ""))
        if year is None and re.search(r"\b(19|20)\d\d\b", heads[at[0]]):
            return None, (f"the column {heads[at[0]]!r} names a year the "
                          f"declaration does not")
        for cells in hits:
            # A row that is shorter or longer than its header cannot be lined
            # up with it. Merged cells in a rendered table are expanded before
            # this, so what is left is a row the table itself leaves ragged.
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


def labelled(cell_value: str, row: str) -> bool:
    """Whether a row's label is ``row``: exactly, or before a bracketed gloss.

    Ivory Coast's list writes "Lagunes (District des Lagunes)"; the name is the
    part before the bracket, and "Maputo City" is still not "Maputo".
    """
    text = cell_text(cell_value).casefold()
    return text == row.casefold() or re.split(r"\s*[\[(]", text, maxsplit=1)[0] == row.casefold()


def rendered(title: str) -> tuple[str, str]:
    """The article as the page shows it: templates expanded, tables as HTML."""
    q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "text",
                                "format": "json", "formatversion": "2", "redirects": "1"})
    data = http_json(f"https://en.wikipedia.org/w/api.php?{q}", timeout=90)
    parsed = data.get("parse") or {}
    return str(parsed.get("text") or ""), str(parsed.get("title") or title)


def term_value(term: Term, year: int | None, fetcher=fetch,
               renderer=rendered) -> tuple[int | None, str, str]:
    """(value, the title it landed on, why not)."""
    if term.rendered:
        html, landed = renderer(term.title)
        if not html:
            return None, landed, "the article did not render"
        parser = Tables()
        parser.feed(html)
        value, why = cell("", term.row or "", term.column or "", year, term.key, term.cite,
                          pairs=[(html, t) for t in parser.tables])
        return value, landed, why
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
               fetcher=fetch, renderer=rendered) -> dict[str, Any] | None:
    total, said, sources = 0, [], []
    for term in figure.terms:
        value, landed, why = term_value(term, figure.year, fetcher, renderer)
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
        drawn = [u for u in read_json(shard_path("admin1", iso3), [])
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
