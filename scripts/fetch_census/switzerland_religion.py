#!/usr/bin/env python3
"""Switzerland: religion by canton, from BFS's structural survey (a survey estimate).

Since 2010 the Swiss census asks religion only in the structural survey
(Strukturerhebung), an annual sample of the permanent resident population
aged 15 and over, weighted by BFS. Its table je-d-01.08.02.02, "Religions-
zugehörigkeit nach Grossregion und Kanton" (DAM asset 36347568), gives one
sheet per year with the weighted number of people in each religious group
and each estimate's confidence interval, as a percentage of the estimate.

A single year's estimate for a small group in a small canton carries an
interval past ±50%, and dropping such estimates (as the language reader,
``switzerland.py``, does) would drop the Reformed of Uri. So the three latest
years are averaged instead, which narrows the error, and a group BFS
suppressed ("X") in any of them is left out, so a canton's shares can fall
short of 100. They are survey estimates and say so in ``religion_basis``; the output
is a ``*_survey.json`` file, which the build uses only where no count exists.

Usage:
    python -m scripts.fetch_census.switzerland_religion [--year 2024]
"""

from __future__ import annotations

import argparse
import io
from typing import Any

from ._shared import PROCESSED, dated, http_get, log, record, shares, write_json
from .central_ages import fold, units

DATA = "https://dam-api.bfs.admin.ch/hub/api/dam/assets/36347568/master"
PORTAL = "https://www.bfs.admin.ch/asset/de/36347568"
SOURCE = ("Federal Statistical Office (BFS/OFS), Strukturerhebung, je-d-01.08.02.02 "
          "(Religionszugehörigkeit nach Grossregion und Kanton)")
LICENCE = "BFS open data (free reuse with attribution)"
OUT = PROCESSED / "switzerland_religion_survey.json"
RELIGION = {
    "Evangelisch-reformiert": "Reformed", "Römisch-katholisch": "Roman Catholic",
    "Andere christliche Glaubensgemeinschaften": "Other Christian",
    "Jüdische Glaubensgemeinschaften": "Judaism", "Jüdische Glaubensgemeinschaft": "Judaism",
    "Islamische Glaubensgemeinschaften": "Islam", "Islamische Glaubensgemeinschaft": "Islam",
    "Andere Religionsgemeinschaften": "Other religion",
    "Ohne Religionszugehörigkeit": "No religion", "Religionszugehörigkeit unbekannt": "Not stated",
    "Unbekannt": "Not stated", "Ohne Angabe": "Not stated",
}
ALIASES = {"Appenzell A. Rh.": "Appenzell Ausserrhoden", "Appenzell I. Rh.": "Appenzell Innerrhoden"}


def clean(cell: Any) -> str:
    return " ".join(str(cell if cell is not None else "").split())


def read(year: int) -> dict[str, dict[str, tuple[float | None, float | None]]]:
    """{row label: {category: (estimate, interval %)}}; None where BFS printed X."""
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(http_get(DATA, binary=True, timeout=300)),
                                  read_only=True, data_only=True)
    if str(year) not in book.sheetnames:
        raise SystemExit(f"switzerland_religion: no sheet {year}; sheets {book.sheetnames}")
    rows = [list(r) for r in book[str(year)].iter_rows(values_only=True)]
    sub_at = next(i for i, r in enumerate(rows) if any(clean(c).startswith("Anzahl") for c in r))
    head, sub = [clean(c) for c in rows[sub_at - 1]], [clean(c) for c in rows[sub_at]]
    columns: dict[int, str] = {}
    label = ""
    for j, cell in enumerate(head):
        # A trailing asterisk is a footnote mark, not part of the category.
        label = cell.rstrip("*").strip() or label
        if sub[j].startswith("Anzahl") or (label == "Total" and head[j] == "Total"):
            columns[j] = label
    log(f"  {year}: columns {columns}")
    unknown = [c for c in columns.values() if c != "Total" and c not in RELIGION]
    if unknown:
        raise SystemExit(f"switzerland_religion: categories this reader does not know: {unknown}")

    def value(cell: Any) -> float | None:
        text = clean(cell)
        return None if text in ("X", "x", "") else float(cell)

    out: dict[str, dict[str, tuple[float | None, float | None]]] = {}
    for r in rows[sub_at + 1:]:
        name = clean(r[0])
        if not name or all(c is None for c in r[1:]):
            continue
        entry = {}
        for j, category in columns.items():
            ci = value(r[j + 1]) if category != "Total" and j + 1 < len(r) else None
            entry[category] = (value(r[j]), ci)
        if name in out and out[name] != entry:
            raise SystemExit(f"switzerland_religion: {name} is printed twice with different figures")
        out[name] = entry
    return out


def build(year: int, span: int = 3) -> list[dict[str, Any]]:
    years = list(range(year - span + 1, year + 1))
    log(f"switzerland_religion: BFS structural survey, religion by canton, {years}")
    tables = {y: read(y) for y in years}
    shapes = units("CHE", "admin1")
    by_name = {fold(s["name"]): s for s in shapes}
    records, used = [], set()
    note = (f"BFS structural survey (Strukturerhebung) {years[0]}-{years[-1]}: religious "
            f"affiliation of the permanent resident population aged 15 and over, weighted by BFS; "
            f"the shares are of the average of the {span} annual weighted estimates, which "
            f"narrows the sampling error of a single year (whose confidence intervals, for the "
            f"small groups of the small cantons, run past ±50%). A group BFS suppresses in any "
            f"of the years for too few respondents is left out, so the shares can fall short of "
            f"100. BFS does not print the number of respondents per canton. The census has not "
            f"asked every resident since 2000.")
    for name, cells in tables[year].items():
        parts = [p.strip() for p in ALIASES.get(name, name).split("/")]
        shape = next((by_name[fold(p)] for p in parts if fold(p) in by_name), None)
        if shape is None:
            continue                      # the country and its Grossregionen
        per_year = []
        for y in years:
            row = tables[y].get(name)
            if row is None:
                raise SystemExit(f"switzerland_religion: {name} has no row in {y}")
            total = row["Total"][0]
            published = sum(v for k, (v, _) in row.items() if k != "Total" and v is not None)
            suppressed = [k for k, (v, _) in row.items() if v is None]
            if not total or published > total * 1.001 or (not suppressed and published < total * 0.999):
                raise SystemExit(f"switzerland_religion: {name} {y}: groups make {published:,.0f} "
                                 f"of {total} (suppressed {suppressed})")
            per_year.append(row)
        total = sum(r["Total"][0] for r in per_year) / span
        counts: dict[str, float] = {}
        withheld, widest = [], {}
        for german in RELIGION:
            values = [r.get(german, (None, None))[0] for r in per_year]
            if all(r.get(german) is None for r in per_year):
                continue
            if any(v is None for v in values):
                withheld.append(RELIGION[german])
                continue
            counts[RELIGION[german]] = counts.get(RELIGION[german], 0.0) + sum(values) / span
            widest[RELIGION[german]] = max((r[german][1] or 0.0) for r in per_year)
        rows = shares(counts, total=total)
        used.add(shape["id"])
        log(f"  {shape['name']}: {total:,.0f} aged 15+ (mean of {span} years); withheld "
            f"{withheld}; widest single-year interval "
            f"{max(widest.items(), key=lambda kv: kv[1]) if widest else None}")
        records.append(record(
            f"CHE-SE{year}-{fold(shape['name'])}", shape["name"], level="admin1", parent="CHE",
            country="CHE", match_by="shape_id", shape_id=shape["id"],
            sources=[{"field": "religion", "name": SOURCE, "url": PORTAL, "license": LICENCE,
                      "year": year}],
            religion=rows, religion_year=dated(rows, year),
            religion_basis="survey estimate: structural survey, permanent resident population 15+",
            religion_note=note))
    left = sorted(s["name"] for s in shapes if s["id"] not in used)
    if left:
        raise SystemExit(f"switzerland_religion: cantons with no row: {left}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, default=2024)
    args = ap.parse_args()
    records = build(args.year)
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
