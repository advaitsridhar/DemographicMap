#!/usr/bin/env python3
"""What is actually inside a zipped CSV release.

A statistical office's bulk file is worth an adapter only if it carries the
columns the map needs, and column inventories are rarely documented in a form
you can trust -- INEGI's ITER has some 230 of them and the published dictionary
is a separate PDF. Downloading it once on a runner and printing the real header
settles what can be built before any of it is written.

It also distinguishes a file from a soft 404. INEGI answers a wrong path with
HTTP 200 and a 2 KB HTML page, so status alone proves nothing; only opening the
archive does.

Usage:
    python scripts/probe_zip.py <url> --match lengua,religion --rows 2
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
import zipfile

TIMEOUT = 180
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DemographicMap/1.0)"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--match", default="", help="comma-separated column-name substrings")
    ap.add_argument("--rows", type=int, default=1)
    ap.add_argument("--max-members", type=int, default=6)
    args = ap.parse_args()

    print(f"downloading {args.url}")
    req = urllib.request.Request(args.url, headers=dict(HEADERS))
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        blob = resp.read()
    print(f"  {len(blob):,} bytes, content-type {resp.headers.get('Content-Type')}")
    if not blob.startswith(b"PK"):
        print(f"  not a zip — first bytes: {blob[:120]!r}")
        return 0

    archive = zipfile.ZipFile(io.BytesIO(blob))
    names = archive.namelist()
    print(f"  {len(names)} member(s)")
    for name in names[:args.max_members]:
        info = archive.getinfo(name)
        print(f"  - {name}  ({info.file_size:,} bytes)")

    wanted = [w.strip().lower() for w in args.match.split(",") if w.strip()]
    csvs = [n for n in names if n.lower().endswith(".csv")]

    # A release usually ships its column inventory beside the data. Reading the
    # dictionary is how the columns get named without downloading a separate
    # PDF, and taking the first CSV in the archive instead finds a lookup table
    # of locality size bands.
    for name in csvs:
        if "diccionario" not in name.lower():
            continue
        print(f"\n=== dictionary: {name}")
        with archive.open(name) as fh:
            rows = list(csv.reader(io.TextIOWrapper(fh, encoding="latin-1", newline="")))
        print(f"  {len(rows)} entries")
        for row in rows:
            line = " | ".join(c for c in row if c)
            if wanted and any(w in line.lower() for w in wanted):
                print(f"  {line[:160]}")

    data = max((n for n in csvs if "diccionario" not in n.lower()
                and "catalogo" not in n.lower()),
               key=lambda n: archive.getinfo(n).file_size, default=None)
    if not data:
        print("\n  no data member found")
        return 0
    print(f"\n=== data: {data}")
    with archive.open(data) as fh:
        reader = csv.reader(io.TextIOWrapper(fh, encoding="latin-1", newline=""))
        header = [h.lstrip("\ufeff") for h in next(reader)]
        print(f"  {len(header)} columns")
        hits = [(i, c) for i, c in enumerate(header)
                if any(w in c.lower() for w in wanted)] if wanted else []
        print(f"  matching: {[c for _, c in hits][:60]}")
        # The municipal total is the row where the locality code is zero; the
        # rest of the file is individual localities, of which there are 190,000.
        shown = 0
        for row in reader:
            cells = dict(zip(header, row))
            if cells.get("LOC") not in ("0000", "0"):
                continue
            print(f"  municipio row: NOM_ENT={cells.get('NOM_ENT')} "
                  f"NOM_MUN={cells.get('NOM_MUN')} POBTOT={cells.get('POBTOT')}")
            print("   ", {c: cells.get(c) for _, c in hits[:14]})
            shown += 1
            if shown >= args.rows:
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
