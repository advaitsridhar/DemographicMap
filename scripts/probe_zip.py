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
    for name in names:
        if not name.lower().endswith(".csv"):
            continue
        print(f"\n=== {name}")
        with archive.open(name) as fh:
            text = io.TextIOWrapper(fh, encoding="latin-1", newline="")
            reader = csv.reader(text)
            header = next(reader)
            print(f"  {len(header)} columns")
            if wanted:
                hits = [(i, c) for i, c in enumerate(header)
                        if any(w in c.lower() for w in wanted)]
                print(f"  {len(hits)} matching: {[c for _, c in hits][:40]}")
            else:
                print(f"  {header[:40]}")
            for n, row in enumerate(reader):
                if n >= args.rows:
                    break
                pairs = {header[i]: row[i] for i in range(min(len(header), len(row)))}
                keys = [c for _, c in (hits if wanted else [(0, k) for k in header][:14])]
                print("  row:", {k: pairs.get(k) for k in list(pairs)[:8]})
                if wanted:
                    print("   matched values:", {k: pairs.get(k) for k in keys[:12]})
        break
    return 0


if __name__ == "__main__":
    sys.exit(main())
