#!/usr/bin/env python3
"""India -- Census 2011 tables C-01 (religion) and C-16 (mother tongue).

There is no public API: censusindia.gov.in publishes per-state XLSX through its
NADA catalogue, so this reads a local directory of downloaded workbooks and
normalises them.  ``--list-sources`` prints the catalogue URLs to fetch.

Two standing caveats the app displays with every Indian figure:

* The reference year is **2011**. The 2021 census was postponed repeatedly and
  had not been conducted at the time of writing, so India's subnational
  demographics are more than a decade old.
* India does not collect ethnicity. Scheduled Caste and Scheduled Tribe shares
  (a constitutional-schedule classification, not an ethnic one) and mother
  tongue are collected instead.

Usage:
    python -m scripts.fetch_census.india_census --input data/raw/india --level state
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, RAW, gap, log, measure, record,
    shares, write_json,
)

CATALOG = "https://censusindia.gov.in/nada/index.php/catalog"
TABLES = {
    "C-01": "Population by religious community",
    "C-16": "Population by mother tongue",
    "A-01": "Number of villages, towns, households, population and area",
}

RELIGION_COLUMNS = {
    "hindu": "Hindu", "muslim": "Muslim", "christian": "Christian", "sikh": "Sikh",
    "buddhist": "Buddhist", "jain": "Jain", "other religions": "Other religions",
    "religion not stated": "Not stated",
}


def read_table(path: Path) -> list[dict[str, Any]]:
    """Read one C-01 workbook.  Requires ``openpyxl`` for .xlsx inputs."""
    if path.suffix.lower() in {".xlsx", ".xls"}:
        try:
            import openpyxl
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("pip install openpyxl to read censusindia workbooks") from exc
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheet = book[book.sheetnames[0]]
        rows = [[c for c in row] for row in sheet.iter_rows(values_only=True)]
    else:
        import csv
        with path.open(newline="", encoding="utf-8-sig") as fh:
            rows = [row for row in csv.reader(fh)]

    header_idx = next((i for i, row in enumerate(rows)
                       if any(isinstance(c, str) and "hindu" in c.lower() for c in row)), None)
    if header_idx is None:
        return []
    header = [str(c or "").strip().lower() for c in rows[header_idx]]
    out = []
    for row in rows[header_idx + 1:]:
        entry = dict(zip(header, row))
        if any(entry.values()):
            out.append(entry)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=RAW / "india",
                    help="directory of downloaded C-01 / C-16 workbooks")
    ap.add_argument("--level", default="state", choices=["state", "district"])
    ap.add_argument("--list-sources", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.list_sources:
        print(f"Census of India 2011 NADA catalogue: {CATALOG}")
        for code, title in TABLES.items():
            print(f"  {code}  {title}")
        print("Download the per-state workbooks into --input, then re-run without --list-sources.")
        return 0

    if not args.input.exists():
        log(f"  no input directory at {args.input}; run with --list-sources for the download URLs")
        return 1

    src = "Census of India 2011, table C-01 (Registrar General of India)"
    records: list[dict[str, Any]] = []
    for path in sorted(args.input.glob("*")):
        if path.suffix.lower() not in {".xlsx", ".xls", ".csv"}:
            continue
        for row in read_table(path):
            name = str(row.get("area name") or row.get("name") or "").strip()
            if not name:
                continue
            counts = {}
            for column, label in RELIGION_COLUMNS.items():
                value = row.get(column)
                if isinstance(value, (int, float)):
                    counts[label] = float(value)
            total = row.get("total population") or sum(counts.values())
            code = str(row.get("state code") or row.get("district code") or name).strip()
            records.append(record(
                f"IND-{code}", name.title(),
                level="admin1" if args.level == "state" else "admin2",
                parent="IND", codes={"census2011": code},
                population=measure(int(total), year=2011, source=src) if total else gap(NOT_AVAILABLE),
                religion=shares(counts, total=float(total) if total else None) or gap(NOT_AVAILABLE),
                religion_note="Census of India 2011 table C-01. India's next census was postponed; "
                              "these are the most recent official figures.",
                ethnicity=gap(NOT_COLLECTED,
                              "India does not collect ethnicity. Scheduled Caste / Scheduled Tribe "
                              "shares and mother tongue are collected instead."),
                sources=[{"field": "religion/population", "name": src, "url": CATALOG,
                          "license": "Government of India open data (GODL)"}],
            ))
    write_json(args.out or PROCESSED / f"india_{args.level}.json", records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
