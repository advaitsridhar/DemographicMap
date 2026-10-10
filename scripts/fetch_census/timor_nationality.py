#!/usr/bin/env python3
"""Timor-Leste: Timorese and foreign nationals by municipality, 2015 census.

Timor-Leste's census does not ask ethnicity (``NOT_COLLECTED_POLICY["TLS"]``
says so, from the 2022 questionnaire); it asks citizenship. Under the owner's
rule of 19 September 2026 a census's nationality count stands where ethnicity
is not counted, published under ``ethnicity_basis: "nationality"`` -- Japan's
and Korea's nationality files are the model -- and this file does that for
the thirteen municipalities the map draws.

The source is the 2015 Population and Housing Census's Volume 2 priority
table 9, "Timorese and foreign population by age and sex", in the workbook
``timor.py`` already reads religion from:

    https://inetl-ip.gov.tl/wp-content/uploads/2023/03/3_2015-V2-Nationality-Citizenship-Religion.xls

Sheet ``2.9`` is the country and sheets ``2.9.a`` to ``2.9.m`` the thirteen
municipalities of 2015 -- the thirteen polygons, Atauro then a post of Dili --
each with a Total row of Timorese and "other nationality/citizenship" for both
sexes, males and females. The 2022 census asked citizenship too and published
no table of it by municipality, so 2015 is the newest: the 24 basic tables of
its main report (chapter 4, ``Chapter-4-TLPHC-Census-report-Basic-tables.xlsx``
on inetl-ip.gov.tl, whose index sheet lists them) carry citizenship once, in
Table 4.10, "Population in private households, by five-year age group, and by
sex, Timor-Leste or foreign country of citizenship" -- for the whole country.

Two labels, both already in the group tree: "East Timorese" (the nationality,
which names no one people -- Tetum, Mambai, Makasae and thirty others are all
of it) and "Foreign nationals".

**Checks**, each a refusal: in every sheet's Total row Timorese and others
make the total for both sexes and each, and males and females make both
sexes; each municipal sheet's title names exactly one municipality and every
municipality comes once; the thirteen make the country's row in every column.

Usage:
    python -m scripts.fetch_census.timor_nationality
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from . import timor
from ._shared import PROCESSED, RAW, download, log, record, shares, write_json
from .sea_common import drawn

OUT = "timor_nationality.json"
YEAR = 2015
SOURCE = (f"{timor.CENSUS_2015}, Volume 2 priority table 9: Timorese and foreign population "
          "by age and sex, by municipality")
SHEET = re.compile(r"^2\.9\s*(?:\.\s*(?P<letter>[a-m]))?\s*$")
LABELS = ("East Timorese", "Foreign nationals")
# The workbook's own spellings in its sheet titles: table 9.i is "Liquicia".
TITLE_SPELLINGS = {"Liquicia": "Liquiçá"}
NOTE = ("Timor-Leste's census asks citizenship, not ethnicity; this is the 2015 census's "
        "count of the municipality's people by nationality -- Timorese against every other -- "
        "shown on this field because the census counts nationality and asks no ethnicity. "
        "\"East Timorese\" is a nationality, not one people. The 2022 census's basic tables "
        "count citizenship for the whole country only (Table 4.10).")


def total_row(grid: list[list[Any]], where: str) -> list[float]:
    """The sheet's Total row: both sexes, males, females x (total, Timorese, other)."""
    for row in grid:
        if timor.tidy(timor.at(row, 0)).lower() == "total":
            cells = [timor.number(timor.at(row, i)) for i in range(1, 10)]
            if any(c is None for c in cells):
                raise SystemExit(f"timor_nationality: {where}: a Total row with blanks {cells}")
            for i in (0, 3, 6):
                if cells[i + 1] + cells[i + 2] != cells[i]:
                    raise SystemExit(f"timor_nationality: {where}: Timorese and others do not "
                                     f"make the total in {cells}")
            if cells[3] + cells[6] != cells[0]:
                raise SystemExit(f"timor_nationality: {where}: the sexes do not make the total")
            return cells
    raise SystemExit(f"timor_nationality: {where}: no Total row")


def municipality_of(grid: list[list[Any]], where: str) -> str:
    """The one municipality a sheet's title names."""
    head = " ".join(timor.tidy(c) for row in grid[:3] for c in row if c)
    words = timor.fold(head)
    keys = {**timor.MUNICIPALITY_KEYS, **{timor.fold(k): timor.MUNICIPALITY_KEYS[timor.fold(v)]
                                         for k, v in TITLE_SPELLINGS.items()}}
    found = {name for key, name in keys.items() if len(key) > 3 and key in words}
    if len(found) != 1:
        raise SystemExit(f"timor_nationality: {where}'s title names {sorted(found) or 'none'}: "
                         f"{head[:160]!r}")
    return found.pop()


def read(sheets: dict[str, list[list[Any]]]) -> tuple[dict[str, list[float]], list[float]]:
    country = None
    municipalities: dict[str, list[float]] = {}
    for name, grid in sheets.items():
        m = SHEET.match(name)
        if not m:
            continue
        row = total_row(grid, name)
        if not m.group("letter"):
            country = row
            continue
        mun = municipality_of(grid, name)
        if mun in municipalities:
            raise SystemExit(f"timor_nationality: {mun} has two sheets")
        municipalities[mun] = row
    if country is None or len(municipalities) != 13:
        raise SystemExit(f"timor_nationality: the country {'found' if country else 'missing'}, "
                         f"{len(municipalities)} municipalities")
    made = [sum(r[i] for r in municipalities.values()) for i in range(9)]
    if made != country:
        raise SystemExit(f"timor_nationality: the municipalities make {made}, against the "
                         f"country's {country}")
    log(f"  table 9: 13 municipalities making the country's {country[0]:,.0f} -- "
        f"{country[1]:,.0f} Timorese, {country[2]:,.0f} of other nationality")
    return municipalities, country


def build(municipalities: dict[str, list[float]], admin1: list[dict[str, Any]]
          ) -> list[dict[str, Any]]:
    src = [{"field": "ethnicity", "name": SOURCE, "url": timor.RELIGION_PAGE, "year": YEAR,
            "license": timor.LICENCE}]
    out = []
    for shape in admin1:
        name = timor.MUNICIPALITY_KEYS.get(timor.fold(shape["name"]))
        if name is None or name not in municipalities:
            raise SystemExit(f"timor_nationality: no table 9 sheet for {shape['name']!r}")
        row = municipalities[name]
        out.append(record(
            f"TLS-NAT-{timor.fold(name)}", shape["name"], level="admin1", parent="TLS",
            country="TLS", match_by="shape_id", shape_id=shape["id"], sources=src,
            ethnicity=shares(dict(zip(LABELS, row[1:3])), total=row[0]),
            ethnicity_year=YEAR, ethnicity_basis="nationality", ethnicity_note=NOTE))
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import xlrd
    log(f"timor_nationality: {SOURCE}")
    path = download(timor.RELIGION_XLS, RAW / "timor" / timor.RELIGION_XLS.rsplit("/", 1)[-1])
    book = xlrd.open_workbook(str(path))
    sheets = {}
    for name in book.sheet_names():
        if SHEET.match(name):
            sheet = book.sheet_by_name(name)
            sheets[name] = [[sheet.cell_value(r, c) for c in range(sheet.ncols)]
                            for r in range(sheet.nrows)]
    municipalities, _ = read(sheets)
    records = build(municipalities, drawn("TLS", "admin1"))
    for r in records:
        log(f"    {r['name']:12} " + ", ".join(f"{g['group']} {g['pct']}"
                                                for g in r["ethnicity"]))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
