#!/usr/bin/env python3
"""Bender and Transnistria: ethnicity from Transnistria's 2015 census, religion and
mother tongue modelled.

Moldova's 2024 census did not reach the left bank of the Dniester or Bender, so
the National Bureau's tables that give every other Moldovan unit its religion
and mother tongue stop at the river. Transnistria's own censuses -- 2004 and
2015 -- are the only counts of these two units, and what has been published
from them, and can be reached, is ethnicity alone: the 2015 table by district
that pop-stat.mashke.org compiles, which Wikipedia cites for the same figures.
Transnistria's own summary of the 2015 census gives no language or religion,
and its statistics service does not answer from outside.

So this writes two kinds of figure, and says which is which:

* **Ethnicity, read.** Bender is the census's own row for the Bender city
  council, dated 2015. Transnistria -- the map's shape is the left bank
  without Bender -- is the sum of the census's seven left-bank rows (Tiraspol,
  Dnestrovsc and five districts), which is exactly the republic's total less
  Bender. It is written as *derived*, not read, because Transnistria's
  Slobozia district also holds three communes on the right bank (Chițcani,
  Cremenciug, Gîsca) that the map draws inside Căușeni: the sum is of a
  slightly larger area than the shape.
* **Religion and mother tongue, modelled.** Each unit's 2015 ethnic mix,
  weighted by how each ethnicity answered the two questions in Moldova's
  2024 census (annex tables 5.35 and 5.33, ethnicity by religion and by
  mother tongue). This assumes that a Russian, a Ukrainian or a Moldovan on
  the left bank answers as one on the right bank does, which is the weak
  point: the left bank is more Russian-speaking than that, so the estimate
  understates Russian as a mother tongue. People whose ethnicity the 2015
  census did not record -- a fifth of Bender's -- are given the unit's
  declared mix. Ethnicities with no row of their own in Moldova's table
  ("Transnistrians", "other") are given the pooled rows of the smaller
  ethnicities that table lists. It is marked and hatched as modelled, and
  is never a reading.

Usage:
    python -m scripts.fetch_census.transnistria
"""

from __future__ import annotations

import argparse
import io
from html.parser import HTMLParser
from typing import Any

from ._shared import PROCESSED, http_get, log, shares, write_json
from .moldova_census import LABELS as CENSUS_LABELS
from .moldova_census import URL as ANNEX
from .moldova_census import count, fold, shapes

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import DERIVED, MODELLED, estimate  # noqa: E402

OUT = "transnistria_2015.json"
POPSTAT = "http://pop-stat.mashke.org/pmr-ethnic2015.htm"
YEAR = 2015

# The census's English header, to the map's names for the groups.
ETHNIC = {
    "total": None, "russians": "Russian", "moldovans": "Moldovan",
    "ukrainians": "Ukrainian", "bulgarians": "Bulgarian", "gagauzians": "Gagauz",
    "belorussians": "Belarusian", "germans": "German", "transnistrians": "Transnistrian",
    "poles": "Polish", "other": "Other", "undeclared": "Not declared",
    # Inside "undeclared", not beside it: the other columns add to the total
    # without it, in every row.
    "refused to answer": None,
}
BENDER = "mun bender"
LEFT_BANK = ("mun tiraspol", "or dnestrovsc", "grigoriopol", "dubasari", "camenca",
             "ribnita", "slobozia")
REPUBLIC = "republica moldoveneasca nistreana"

# The rows of Moldova's cross-tables each 2015 group takes its answers from.
# "Transnistrian" and "Other" have no row of their own and take the pooled
# rows of every ethnicity the table lists beyond the named ones.
ROWS = {"Russian": "rus", "Moldovan": "moldovean", "Ukrainian": "ucrainean",
        "Bulgarian": "bulgar", "Gagauz": "gagauz", "Belarusian": "belorus",
        "German": "german neamt", "Polish": "polonez"}
POOLED = ("Transnistrian", "Other")
NOT_POOLED = {"total", "nu au declarat", "roman", *ROWS.values()}

# The cross-tables' categories. Religion's are 5.29's with two spellings of
# its own; mother tongue's name every language the census recorded, and the
# ones not named here are one bar in a model whose precision does not run to
# a Czech or an Arabic share.
LABELS = {
    "religion": {**CENSUS_LABELS["religion"], "romano catolic": "Catholic",
                 "alta religie": "Other religion"},
    "language": {**CENSUS_LABELS["language"], "belorusa": "Belarusian",
                 "germana": "German", "poloneza": "Polish"},
}
REST = {"religion": "Other religion", "language": "Other"}
SHEETS = {"religion": "5.35", "language": "5.33"}
FLOOR = 0.1   # below this share a modelled group joins the remainder


class Rows(HTMLParser):
    """Table rows as cell texts, from markup that may never close a cell or a row.

    pop-stat's pages are written the old way -- "<tr><td>a<td>b" -- so a row
    ends where the next begins and a cell where the next cell does.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "tr":
            self.rows.append([])
            self.cell = None
        elif tag in ("td", "th") and self.rows:
            self.rows[-1].append("")
            self.cell = self.rows[-1]
        elif tag == "br" and self.cell is not None:
            self.cell[-1] += " "

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th", "tr", "table"):
            self.cell = None

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell[-1] += data


def table_rows(page: str) -> list[list[str]]:
    """Every row of the page's tables as cell texts."""
    parser = Rows()
    parser.feed(page)
    return [[" ".join(c.split()) for c in row] for row in parser.rows]


def ethnic_2015(page: str) -> dict[str, dict[str, int]]:
    """{folded Romanian unit name: {group: persons}} from the 2015 table."""
    rows = table_rows(page)
    header = next((r for r in rows if "total" in [fold(c) for c in r]
                   and "russians" in [fold(c) for c in r]), None)
    if header is None:
        raise SystemExit("transnistria: no English header row (Total, Russians, ...)")
    folded = [fold(c) for c in header]
    labels = folded[folded.index("total"):]
    unknown = [c for c in labels if c not in ETHNIC]
    if unknown:
        raise SystemExit(f"transnistria: header groups with no entry in ETHNIC: {unknown}")
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        if len(row) < len(labels) + 1:
            continue
        figures = row[-len(labels):]
        names = [fold(c) for c in row[:-len(labels)]]
        name = next((n for n in names if n in (BENDER, REPUBLIC, *LEFT_BANK)), None)
        if name is None:
            continue
        try:
            counts = dict(zip(labels, (count(c) for c in figures)))
        except ValueError:
            continue
        groups: dict[str, int] = {}
        for label, n in counts.items():
            if ETHNIC[label]:
                groups[ETHNIC[label]] = groups.get(ETHNIC[label], 0) + n
        if sum(groups.values()) != counts["total"]:
            raise SystemExit(f"transnistria: {name} adds to {sum(groups.values()):,} "
                             f"against its total {counts['total']:,}")
        out[name] = groups
    missing = [n for n in (BENDER, REPUBLIC, *LEFT_BANK) if n not in out]
    if missing:
        raise SystemExit(f"transnistria: rows not found in the 2015 table: {missing}")
    left = sum(sum(out[n].values()) for n in LEFT_BANK)
    whole = sum(out[REPUBLIC].values())
    if left + sum(out[BENDER].values()) != whole:
        raise SystemExit(f"transnistria: the left bank ({left:,}) and Bender do not "
                         f"make the republic ({whole:,})")
    return out


def by_ethnicity(field: str, rows: list[tuple[Any, ...]]) -> dict[str, dict[str, int]]:
    """{folded ethnicity: {group: persons}} from a cross-table's counts."""
    top = next((i for i, r in enumerate(rows)
                if r and any(fold(c).startswith("etnia declarat") for c in r)), None)
    if top is None:
        raise SystemExit(f"transnistria: {field}: no header row 'Etnia declarată'")
    at = next(j for j, c in enumerate(rows[top]) if fold(c).startswith("etnia declarat"))

    def cell(r: tuple[Any, ...], j: int) -> str:
        return str(r[j]).strip() if j < len(r) and r[j] is not None else ""
    letters = next((i for i in range(top + 1, len(rows))
                    if cell(rows[i], at) == "A" and cell(rows[i], at + 1) == "1"), None)
    if letters is None:
        raise SystemExit(f"transnistria: {field}: no row of column letters")
    width = max(len(r) for r in rows[top:letters])
    labels: dict[int, str] = {}
    for j in range(at + 1, width):
        cells = [rows[i][j] for i in range(top, letters)
                 if j < len(rows[i]) and rows[i][j] not in (None, "")]
        if cells and fold(cells[-1]) != "total":
            labels[j] = str(cells[-1]).strip()
    out: dict[str, dict[str, int]] = {}
    for row in rows[letters + 1:]:
        name = fold(cell(row, at))
        if not name:
            continue
        if name.startswith("in "):     # "în % față de total": the counts are over
            break
        total = count(row[at + 1])
        groups: dict[str, int] = {}
        for j, label in labels.items():
            key = next((v for k, v in LABELS[field].items() if fold(label).startswith(k)),
                       REST[field] if field == "language" else None)
            if key is None:
                raise SystemExit(f"transnistria: {field} category {label!r} has no entry")
            groups[key] = groups.get(key, 0) + count(row[j] if j < len(row) else None)
        if sum(groups.values()) != total:
            raise SystemExit(f"transnistria: {field}, {name}: adds to "
                             f"{sum(groups.values()):,} against {total:,}")
        out[name] = groups
    for name in ROWS.values():
        if name not in out:
            raise SystemExit(f"transnistria: {field}: no row for {name!r}")
    return out


def rates(table: dict[str, dict[str, int]]) -> dict[str, dict[str, float]]:
    """Each 2015 group's answers as shares, the pooled row for the ones without one."""
    def share(groups: dict[str, int]) -> dict[str, float]:
        total = sum(groups.values())
        return {g: n / total for g, n in groups.items()}
    out = {group: share(table[row]) for group, row in ROWS.items()}
    pooled: dict[str, int] = {}
    for name, groups in table.items():
        if name not in NOT_POOLED:
            for g, n in groups.items():
                pooled[g] = pooled.get(g, 0) + n
    for group in POOLED:
        out[group] = share(pooled)
    return out


def modelled(field: str, ethnic: dict[str, int], rate: dict[str, dict[str, float]]
             ) -> list[dict[str, Any]]:
    declared = {g: n for g, n in ethnic.items() if g != "Not declared" and n}
    total = sum(declared.values())
    mix: dict[str, float] = {}
    for group, n in declared.items():
        for answer, p in rate[group].items():
            mix[answer] = mix.get(answer, 0.0) + 100.0 * p * n / total
    rest = REST[field]
    kept = {g: v for g, v in mix.items() if v >= FLOOR or g == rest}
    kept[rest] = kept.get(rest, 0.0) + sum(v for g, v in mix.items() if g not in kept)
    rows = [{"group": g, "pct": round(v, 1)} for g, v in kept.items() if round(v, 1) > 0]
    rows.sort(key=lambda r: (-r["pct"], r["group"]))
    return rows


def records(ethnic: dict[str, dict[str, int]], rate: dict[str, dict[str, dict[str, float]]],
            drawn: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    left: dict[str, int] = {}
    for name in LEFT_BANK:
        for g, n in ethnic[name].items():
            left[g] = left.get(g, 0) + n
    units = {"Bender": ethnic[BENDER], "Transnistria": left}
    source_2015 = ("Transnistria's 2015 census, ethnic composition by district, as "
                   "pop-stat.mashke.org compiles it")
    source_2024 = ("Biroul Național de Statistică, Recensământul Populației și "
                   "Locuințelor 2024, annex tables 5.33 and 5.35 (by ethnicity)")
    out = []
    for name, counts in units.items():
        read = shares({g: n for g, n in counts.items() if n})
        if name == "Bender":
            ethnicity: Any = read
            ethnicity_note = ("Ethnic composition from Transnistria's own 2015 census, the "
                              "Bender city council's row, as pop-stat.mashke.org compiles "
                              "it. Moldova's 2024 census did not count Bender; this is the "
                              "breakaway authority's count, not Moldova's.")
        else:
            ethnicity = estimate(
                DERIVED, read, method="district-sum",
                inputs=[f"{source_2015}: {n}" for n in LEFT_BANK],
                note=("Not read as one figure: the sum of Transnistria's seven left-bank "
                      "rows of its own 2015 census, which is the republic's total less "
                      "Bender. Its Slobozia district also counts three communes on the "
                      "right bank (Chițcani, Cremenciug, Gîsca) that the map draws in "
                      "Căușeni, so the sum is of a slightly larger area than this shape. "
                      "Breakaway authority's census; Moldova's 2024 census did not count "
                      "this territory."))
            ethnicity_note = ethnicity["note"]
        fields: dict[str, Any] = {"ethnicity": ethnicity, "ethnicity_note": ethnicity_note}
        if name == "Bender":
            fields["ethnicity_year"] = YEAR
        for field, word in (("religion", "religious affiliation"), ("language", "mother tongue")):
            value = estimate(
                MODELLED, modelled(field, counts, rate[field]),
                method="ethnicity-weighted",
                inputs=[f"{source_2015}: {name}", source_2024],
                note=(f"Not read: no census that counted {name} has published its "
                      f"{word}. Modelled from its ethnic composition in Transnistria's "
                      f"2015 census, each group given the {word} its members declared in "
                      f"Moldova's 2024 census. Assumes the left bank's Russians, "
                      f"Ukrainians and Moldovans answer as the right bank's do; the left "
                      f"bank is more Russian-speaking, so this understates Russian"
                      + (" as a mother tongue" if field == "language" else "") +
                      f". People whose ethnicity was not recorded are given the declared "
                      f"mix."))
            fields[field] = value
            fields[f"{field}_note"] = value["note"]
        for level in ("admin1", "admin2"):
            shape = drawn.get(level, {}).get(fold(name).replace(" ", ""))
            if not shape:
                raise SystemExit(f"transnistria: {name!r} is not a {level} shape")
            out.append({
                "id": f"MDA-pmr-{level}-{name.lower()}", "level": level, "name": name,
                "parent": "MDA", "country": "MDA", "shape_id": shape, "match_by": "shape_id",
                **fields,
                "sources": [{"field": "ethnicity", "name": source_2015, "url": POPSTAT,
                             "license": "Compilation of census results"},
                            {"field": "religion/language", "name": source_2024,
                             "url": ANNEX, "license": "Official statistics of the "
                             "Republic of Moldova (reuse with attribution)"}],
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    import openpyxl
    log("transnistria: 2015 ethnic composition")
    page = http_get(POPSTAT, binary=True)
    page = page.decode("utf-8-sig", "replace") if isinstance(page, bytes) else page
    ethnic = ethnic_2015(page)
    for name in (BENDER, *LEFT_BANK):
        log(f"  {name}: {sum(ethnic[name].values()):,}")
    log("transnistria: Moldova 2024, ethnicity by religion and by mother tongue")
    blob = http_get(ANNEX, binary=True, timeout=600)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rate = {field: rates(by_ethnicity(field, [tuple(r) for r in book[sheet].iter_rows(values_only=True)]))
            for field, sheet in SHEETS.items()}
    rows = records(ethnic, rate, shapes())
    for r in rows:
        if r["level"] == "admin1":
            for field in ("religion", "language"):
                top = ", ".join(f"{g['group']} {g['pct']}" for g in r[field]["estimate"][:4])
                log(f"  {r['name']} {field} (modelled): {top}")
    write_json(PROCESSED / OUT, rows)
    log(f"wrote {len(rows)} records to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
