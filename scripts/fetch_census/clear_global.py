#!/usr/bin/env python3
"""CLEAR Global's subnational language files, read from the HDX catalogue.

CLEAR Global (formerly Translators without Borders) publishes one HDX dataset
per country, named ``<country>-languages``, and each carries a CSV per
administrative level. This reads the admin1 and admin2 files.

Nothing here is hardcoded to a resource uuid: HDX rotates them, so the dataset
is asked for by stub and the resource by **name**, the way
``scripts/fetch_census/png.py`` does. The licence is read from the catalogue on
every run and written onto every record, rather than being written down once
and assumed to still hold.

Usage:
    python -m scripts.fetch_census.clear_global --probe SOM,IRQ,KGZ
    python -m scripts.fetch_census.clear_global --org
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.parse
import urllib.request
from typing import Any

from ._shared import log  # noqa: E402

API = "https://data.humdata.org/api/3/action"
ORG = "clear"
TIMEOUT = 120
HEADERS = {"Accept": "application/json",
           "User-Agent": "DemographicMap/1.0 "
                         "(+https://github.com/advaitsridhar/DemographicMap)"}


def get(path: str, **params: object) -> Any:
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
        return json.load(fh)["result"]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
        return fh.read().decode("utf-8-sig", "replace")


def catalogue() -> list[dict[str, Any]]:
    """Every dataset the publisher has, newest metadata first."""
    found = get("package_search", fq=f"organization:{ORG}", rows=300)
    return found.get("results", []) or []


def probe(isos: list[str]) -> None:
    """What one country's files actually contain, before anything is written."""
    packages = catalogue()
    by_iso: dict[str, list[dict[str, Any]]] = {}
    for pkg in packages:
        for group in pkg.get("groups", ()):
            name = str(group.get("name", "")).upper()
            if len(name) == 3:
                by_iso.setdefault(name, []).append(pkg)
    for iso in isos:
        for pkg in by_iso.get(iso.upper(), []):
            log(f"\n=== {iso.upper()}  {pkg.get('name')}  {pkg.get('title')} ===")
            log(f"  licence: license_id={pkg.get('license_id')!r} "
                f"license_title={pkg.get('license_title')!r} "
                f"license_other={(pkg.get('license_other') or '')!r} "
                f"isopen={pkg.get('isopen')}")
            notes = (pkg.get("notes") or "").strip().replace("\n", " ")
            log(f"  notes: {notes[:700]}")
            log(f"  methodology: {pkg.get('methodology')!r} "
                f"{(pkg.get('methodology_other') or '')[:300]!r}")
            log(f"  dataset_source: {pkg.get('dataset_source')!r}  "
                f"reference period: {pkg.get('dataset_date')!r}")
            for res in pkg.get("resources", []) or []:
                name = str(res.get("name", ""))
                if not name.lower().endswith(".csv"):
                    continue
                log(f"  --- {name}  {res.get('url')}")
                try:
                    body = fetch(str(res.get("url")))
                except Exception as err:               # noqa: BLE001 -- reported
                    log(f"      {type(err).__name__}: {err}")
                    continue
                rows = list(csv.reader(io.StringIO(body)))
                log(f"      {len(rows)} line(s)")
                for line in rows[:6]:
                    log("      | " + " | ".join(c[:28] for c in line)[:600])


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", default="",
                    help="comma-separated ISO3s whose files to describe")
    ap.add_argument("--org", action="store_true",
                    help="list the publisher's datasets and their licences")
    args = ap.parse_args()
    if args.org:
        for pkg in sorted(catalogue(), key=lambda p: str(p.get("name"))):
            log(f"{pkg.get('name')}  {pkg.get('license_id')}  "
                f"{pkg.get('dataset_date')}")
        return 0
    if args.probe:
        probe([x for x in args.probe.split(",") if x])
        return 0
    raise SystemExit("clear_global: give --probe ISO3,ISO3 or --org")


if __name__ == "__main__":
    raise SystemExit(main())
