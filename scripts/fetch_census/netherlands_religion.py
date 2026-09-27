#!/usr/bin/env python3
"""The Netherlands: religion by province, from CBS's own survey tables.

The Netherlands has had no questionnaire census since 1971, and no register
records religion. CBS measures it by survey and publishes it by region in
"Religie naar regio, 2021/2025" (maatwerk, March 2026), a workbook on
www.cbs.nl: the share of the non-institutional population aged 15 and over
who count themselves to a religion -- Roman Catholic, Protestant, Islam,
another religion -- by province and COROP region, pooled over 2021 to 2025.
CBS leaves out any region with fewer than 300 respondents, so every province
printed rests on at least 300.

These are **survey estimates**, and the record says so in ``religion_basis``
so that no roll-up sums them with a count; they go to their own file,
``netherlands_religion_survey.json``. They replace nothing: the province
religion on the map until now was read from Wikipedia infoboxes
(``netherlands.py``), which transcribe older releases of this same series,
and an encyclopaedia is not a source. The shares partition the population:
the four religious groups make "Totaal gelovig", and the rest is written as
"No religion", which is what the survey's other answer is. The municipal
level has no figure: CBS publishes this table by province and COROP region
only, and COROP regions are not drawn.

Usage:
    python -m scripts.fetch_census.netherlands_religion
"""

from __future__ import annotations

import argparse
import io
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json
from .central_ages import fold, units

WORKBOOK = "https://www.cbs.nl/-/media/_excel/2026/11/religie_2025_tabellen.xlsx"
PAGE = "https://www.cbs.nl/nl-nl/maatwerk/2026/11/religie-naar-regio-2021-2025"
SOURCE = "CBS, Religie naar regio, 2021/2025 (maatwerk, maart 2026), tabel 2"
LICENCE = "CC BY 4.0 (CBS)"
OUT = PROCESSED / "netherlands_religion_survey.json"
YEAR = 2025
COLUMNS = {"Rooms-katholiek": "Roman Catholic", "Rooms-kaholiek": "Roman Catholic",
           "Protestants": "Protestant", "Islam": "Islam", "Ander geloof": "Other religion"}
TOTAL = "Totaal gelovig"
PROVINCES = ("Groningen", "Fryslân", "Drenthe", "Overijssel", "Flevoland", "Gelderland",
             "Utrecht", "Noord-Holland", "Zuid-Holland", "Zeeland", "Noord-Brabant", "Limburg")


def read() -> dict[str, dict[str, float]]:
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(http_get(WORKBOOK, binary=True)), read_only=True,
                                  data_only=True)
    rows = [[c for c in row] for row in book["Tabel 2"].iter_rows(values_only=True)]
    header = next(r for r in rows if TOTAL in [str(c).strip() for c in r if c is not None])
    cells = [str(c).strip() if c is not None else "" for c in header]
    at = {name: cells.index(name) for name in [TOTAL, *[c for c in cells if c in COLUMNS]]}
    if len(at) != 5:
        raise SystemExit(f"netherlands_religion: Tabel 2's columns are {cells}")
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        name = str(row[0]).strip() if row and row[0] is not None else ""
        second = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        if name in (*PROVINCES, "Nederland") and second == "Totaal":
            values = {label: row[i] for label, i in at.items()}
            out[name] = {k: float(v) for k, v in values.items()}
    for note in (" ".join(str(c) for c in r if c) for r in rows):
        if "te weinig" in note:
            log(f"  CBS's note: {note}")
    return out


def build() -> list[dict[str, Any]]:
    table = read()
    missing = [p for p in PROVINCES if p not in table]
    if missing or "Nederland" not in table:
        raise SystemExit(f"netherlands_religion: provinces missing from Tabel 2: {missing}")
    shapes = {fold(u["name"]): u for u in units("NLD", "admin1")}
    records = []
    for name in PROVINCES:
        row = table[name]
        parts = {COLUMNS[k]: v for k, v in row.items() if k != TOTAL}
        if abs(sum(parts.values()) - row[TOTAL]) > 0.3:
            raise SystemExit(f"netherlands_religion: {name}: the four groups make "
                             f"{sum(parts.values()):.1f}, 'Totaal gelovig' is {row[TOTAL]}")
        parts["No religion"] = round(100 - row[TOTAL], 1)
        shape = shapes.get(fold(name))
        if shape is None:
            raise SystemExit(f"netherlands_religion: no province polygon named {name}")
        rows = sorted(({"group": g, "pct": round(p, 1)} for g, p in parts.items()),
                      key=lambda r: (-r["pct"], r["group"]))
        records.append(record(
            f"NLD-CBS-REL-{fold(name)}", shape["name"], level="admin1", parent="NLD",
            country="NLD", match_by="shape_id", shape_id=shape["id"],
            religion=rows, religion_year=YEAR,
            religion_basis="survey estimate: self-identification, non-institutional population 15+",
            religion_note=(
                "CBS survey estimate, pooled over 2021-2025 (Religie naar regio, 2021/2025): the "
                "share of the non-institutional population aged 15 and over who count themselves "
                "to a religion, weighted by CBS; CBS prints a region only when at least 300 "
                "respondents stand behind it. 'No religion' is everyone who does not count "
                "themselves to one (100 less 'Totaal gelovig'). The Netherlands has had no "
                "questionnaire census since 1971 and no register records religion."),
            sources=[{"field": "religion", "name": SOURCE, "url": PAGE, "license": LICENCE,
                      "year": YEAR}]))
    national = table["Nederland"]
    log(f"  Nederland: {national}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    records = build()
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
