#!/usr/bin/env python3
"""What a CSV release, zipped or bare, says before an adapter is written against it.

Statistics Canada's Census Profile ships as a 37 MB CSV in a zip, one row per
geography and characteristic, with the characteristics nested by indentation
in their names. Which rows are the religion block, what its children are
called, and which GEO_LEVEL values the file carries are facts only the file
can settle. This streams one member and reports the distinct values of one
column, optionally only where another column matches a pattern.

A bare CSV (the Czech Statistical Office publishes its census open data as
one plain file per table) is read the same way; without ``--column`` the
first rows are printed whole, which is how its column names are learnt.

Usage:
    python scripts/probe_csvzip.py <url>            # bare CSV, first rows whole
    python scripts/probe_csvzip.py <url> --member data.csv --column GEO_LEVEL
    python scripts/probe_csvzip.py <url> --column CHARACTERISTIC_NAME \\
        --where "GEO_NAME=Canada" --match "religion|ethnic|mother tongue" --context 40
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import urllib.request
import zipfile

HEADERS = {"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--member", default="", help="substring of the member to read; else the largest CSV")
    ap.add_argument("--column", default="", help="column whose distinct values to report; "
                    "omitted, the first --limit rows are printed whole")
    ap.add_argument("--where", default="", help="COLUMN=VALUE, rows to keep")
    ap.add_argument("--match", default="", help="regex on the column's value (case-insensitive)")
    ap.add_argument("--context", type=int, default=0,
                    help="also print this many rows following each match, in file order")
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--encoding", default="utf-8-sig")
    args = ap.parse_args()

    req = urllib.request.Request(args.url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=300) as resp:
        blob = resp.read()
    print(f"{len(blob):,} bytes")
    if zipfile.is_zipfile(io.BytesIO(blob)):
        archive = zipfile.ZipFile(io.BytesIO(blob))
        members = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        name = next((n for n in members if args.member and args.member.lower() in n.lower()), None) \
            or max(members, key=lambda n: archive.getinfo(n).file_size)
        print(f"member: {name} ({archive.getinfo(name).file_size:,} bytes)")
        opened = archive.open(name)
    else:
        print("bare CSV (not a zip)")
        opened = io.BytesIO(blob)

    where = None
    if args.where:
        k, _, v = args.where.partition("=")
        where = (k.strip(), v.strip())
    pattern = re.compile(args.match, re.I) if args.match else None
    seen: dict[str, int] = {}
    printed = 0
    trailing = 0
    with opened as fh:
        text = io.TextIOWrapper(fh, encoding=args.encoding, newline="")
        sample = text.read(4096)
        text.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample else csv.excel
        reader = csv.DictReader(text, dialect=dialect)
        print(f"columns: {reader.fieldnames}")
        for row in reader:
            if where and row.get(where[0]) != where[1]:
                continue
            if not args.column:
                if printed < args.limit:
                    print("  " + " | ".join(f"{k}={v!r}" for k, v in row.items()))
                    printed += 1
                    continue
                break
            value = row.get(args.column, "")
            hit = pattern.search(value) if pattern else True
            if hit or trailing:
                if value not in seen and printed < args.limit:
                    ident = row.get("CHARACTERISTIC_ID", "")
                    count = row.get("C1_COUNT_TOTAL", "")
                    print(f"  {ident:>6} | {value[:110]!r} | {count}")
                    printed += 1
                trailing = args.context if hit else trailing - 1
            seen[value] = seen.get(value, 0) + 1
    if args.column:
        print(f"{len(seen)} distinct values of {args.column}; {printed} printed")
    else:
        print(f"{printed} rows printed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
