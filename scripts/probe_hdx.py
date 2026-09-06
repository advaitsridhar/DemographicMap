#!/usr/bin/env python3
"""Which countries the US Census Bureau's subnational series covers on HDX.

The USCB adapter is generic: eight countries already run through it, and each
one is a config entry rather than a new reader. What has never been measured is
how many more the Bureau publishes, so the next country has been chosen by
guessing at names rather than by reading the list.

This reads it. It starts from a dataset the adapter already uses, takes the
organization from that rather than assuming one, and then lists every dataset
that organization publishes -- with the ISO3 the adapter would need, whether a
workbook is actually attached, and whether this map already has the country.

Read-only, and the output is the log. HDX blocks its HTML pages behind a
challenge but serves the API, which is why this asks the API.

Usage:
    python -m scripts.probe_hdx
    python -m scripts.probe_hdx --seed 809dfb22-77f4-482c-8560-79b07d20fc15
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://data.humdata.org/api/3/action"
TIMEOUT = 60
# The Philippines dataset, which the adapter has fetched successfully, so the
# organization it belongs to is a fact rather than a guess about HDX's naming.
SEED = "809dfb22-77f4-482c-8560-79b07d20fc15"


def get(path: str, **params: object) -> dict:
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
        return json.load(fh)["result"]


def workbooks(package: dict) -> list[str]:
    """The .xlsx resources on a dataset, which is what the adapter reads."""
    return [r.get("name", "") for r in package.get("resources", ())
            if str(r.get("format", "")).lower() in ("xlsx", "xls")
            or str(r.get("name", "")).lower().endswith((".xlsx", ".xls"))]


def already_here() -> set[str]:
    """ISO3s this map already carries subnational figures for."""
    site = Path(__file__).resolve().parent.parent / "site" / "data"
    out = set()
    for level in ("admin1", "admin2"):
        for path in sorted((site / level).glob("*.json")):
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if any(isinstance(row.get(f), list) and row[f]
                       for f in ("religion", "language", "ethnicity")):
                    out.add(path.stem)
                    break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", default=SEED,
                    help="a dataset id the adapter already uses")
    ap.add_argument("--rows", type=int, default=300)
    args = ap.parse_args()

    try:
        seed = get("package_show", id=args.seed)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as err:
        print(f"probe_hdx: cannot reach HDX: {err}")
        return 1
    org = (seed.get("organization") or {}).get("name", "")
    print(f"seed dataset : {seed.get('title')}")
    print(f"organization : {org!r}")
    if not org:
        print("no organization on the seed, so nothing to enumerate")
        return 1

    found = get("package_search", fq=f"organization:{org}", rows=args.rows)
    total = found.get("count", 0)
    results = found.get("results", [])
    print(f"datasets     : {len(results)} listed of {total}")
    have = already_here()
    print(f"already live : {len(have)} countries with subnational figures")
    print()

    rows = []
    for pkg in results:
        iso = ""
        for group in pkg.get("groups", ()):
            name = str(group.get("name", ""))
            if len(name) == 3 and name.isalpha():
                iso = name.upper()
                break
        books = workbooks(pkg)
        rows.append((bool(books), iso in have, iso, pkg.get("name", ""),
                     pkg.get("title", "")[:52], len(books)))

    rows.sort(key=lambda r: (not r[0], r[1], r[2]))
    print(f"{'ISO3':5} {'live':5} {'xlsx':5} {'dataset name':52} title")
    for has_book, live, iso, name, title, n in rows:
        print(f"{iso or '?':5} {'yes' if live else '-':5} "
              f"{(str(n) if has_book else '-'):5} {name[:52]:52} {title}")

    missing = sorted({r[2] for r in rows if r[0] and r[2] and not r[1]})
    print()
    print(f"candidates (a workbook, and not yet on the map): {len(missing)}")
    print("  " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
