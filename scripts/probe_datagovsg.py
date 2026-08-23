#!/usr/bin/env python3
"""Find out what data.gov.sg will answer, and whether a key is needed.

data.gov.sg has had several API generations -- the CKAN-style ``/api/action``
endpoints, the v2 production API, and the newer api-open host -- and which of
them are live, which need a key, and which carry the datasets worth having is
not something to guess at. This tries each in turn and reports the status, the
shape of the response, and a sample, so an adapter can be written against
whichever actually works.

The key, if any, is read from the environment and never printed. Only its
presence and length are reported, which is enough to tell a missing secret from
a rejected one.

Usage:
    DATA_GOV_SG_KEY=... python scripts/probe_datagovsg.py --search population
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import log  # noqa: E402

# Environment variables that might carry the key, in the order they are tried.
KEY_VARS = ("DEMOGRAPHICMAP", "DATA_GOV_SG_KEY", "DATAGOVSG_API_KEY",
            "DATA_GOV_SG_API_KEY", "DATAGOVSG_KEY", "DATA_GOV_SG_TOKEN")

# Header names the service has used for keys at different times; each candidate
# endpoint is tried with every plausible header until one answers.
HEADERS = ("x-api-key", "api-key", "AccountKey", "Authorization")

V2 = "https://api-production.data.gov.sg/v2/public/api"
OPEN = "https://api-open.data.gov.sg/v1/public/api"

ENDPOINTS = [
    ("v2 dataset list", V2 + "/datasets?page=1"),
    ("v2 dataset search param", V2 + "/datasets?page=1&query={query}"),
    ("api-open collections", OPEN + "/collections?page=1"),
    ("CKAN package_list", "https://data.gov.sg/api/action/package_list"),
]

# How many list pages to walk when the server offers no search of its own.
MAX_PAGES = 60


def find_key() -> tuple[str | None, str | None]:
    for name in KEY_VARS:
        value = os.environ.get(name)
        if value:
            return name, value
    return None, None


def fetch(url: str, key: str | None, header: str | None) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "DemographicMap/probe"})
    if key and header:
        request.add_header(header,
                           f"Bearer {key}" if header == "Authorization" else key)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read(6000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(1500).decode("utf-8", "replace")
    except Exception as exc:                       # noqa: BLE001 - report anything
        return 0, f"{type(exc).__name__}: {exc}"


def describe(body: str) -> str:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return "  (not JSON) " + " ".join(body[:300].split())
    if isinstance(parsed, dict):
        lines = [f"  JSON object, keys: {sorted(parsed)[:12]}"]
        for key in ("data", "result", "results"):
            inner: Any = parsed.get(key)
            if isinstance(inner, dict):
                lines.append(f"  {key} keys: {sorted(inner)[:12]}")
                for deeper in ("datasets", "collections", "records", "results"):
                    items = inner.get(deeper)
                    if isinstance(items, list) and items:
                        lines.append(f"  {key}.{deeper}: {len(items)} items; first:")
                        lines.append("    " + json.dumps(items[0], default=str)[:600])
            elif isinstance(inner, list) and inner:
                lines.append(f"  {key}: {len(inner)} items; first:")
                lines.append("    " + json.dumps(inner[0], default=str)[:600])
        return "\n".join(lines)
    if isinstance(parsed, list):
        return f"  JSON array of {len(parsed)}; first: {json.dumps(parsed[:3])[:400]}"
    return f"  JSON scalar: {parsed!r}"


def catalogue(terms: list[str], key: str | None) -> list[dict[str, Any]]:
    """Datasets whose name or description mentions every term.

    The v2 list endpoint pages ten at a time and the probe above establishes
    whether it honours a query parameter; where it does not, the filtering has
    to happen here, which is why this walks pages rather than asking.
    """
    found, page, seen = [], 1, 0
    while page <= MAX_PAGES:
        status, body = fetch(f"{V2}/datasets?page={page}", key, "x-api-key")
        if status != 200:
            log(f"  page {page}: HTTP {status}; stopping")
            break
        try:
            data = json.loads(body).get("data") or {}
        except json.JSONDecodeError:
            break
        datasets = data.get("datasets") or []
        if not datasets:
            break
        seen += len(datasets)
        for entry in datasets:
            haystack = " ".join(str(entry.get(field) or "")
                                for field in ("name", "description")).lower()
            if all(term in haystack for term in terms):
                found.append(entry)
        total = data.get("pages")
        if total and page >= total:
            break
        page += 1
    log(f"  walked {page} page(s), {seen} datasets, {len(found)} matching {terms}")
    return found


def sample(dataset_id: str, key: str | None) -> None:
    """Metadata and a few rows, so an adapter can be written against real fields."""
    for label, url in (
            ("metadata", f"{V2}/datasets/{dataset_id}/metadata"),
            ("datastore rows",
             f"https://data.gov.sg/api/action/datastore_search"
             f"?resource_id={dataset_id}&limit=3"),
            ("api-open rows", f"{OPEN}/datasets/{dataset_id}/poll-download")):
        status, body = fetch(url, key, "x-api-key")
        log(f"\n  --- {label}: HTTP {status}\n      {url}")
        if status == 200:
            log(describe(body))
        else:
            log("      " + " ".join(body[:220].split()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--search", default="population planning area")
    ap.add_argument("--catalogue", action="store_true",
                    help="walk the dataset list and sample the best match")
    args = ap.parse_args()

    name, key = find_key()
    if key:
        log(f"key found in ${name} ({len(key)} characters). Its value is never printed.")
    else:
        log(f"no key in any of {KEY_VARS}. Trying the endpoints unauthenticated -- "
            f"if one answers, no key is needed; if all reject, the secret is under "
            f"a name not in that list and the workflow needs updating.")

    for label, template in ENDPOINTS:
        url = template.format(query=urllib.parse.quote(args.search))
        log(f"\n=== {label}\n    {url}")
        status, body = fetch(url, None, None)
        log(f"  unauthenticated: HTTP {status}")
        if status == 200:
            log(describe(body))
            continue
        if not key:
            log("  " + " ".join(body[:200].split()))
            continue
        for header in HEADERS:
            status, body = fetch(url, key, header)
            log(f"  with {header}: HTTP {status}")
            if status == 200:
                log(describe(body))
                break
        else:
            log("  " + " ".join(body[:200].split()))

    if args.catalogue:
        terms = [t for t in args.search.lower().split() if len(t) > 2]
        log(f"\n=== searching the catalogue for {terms}")
        matches = catalogue(terms, key)
        for entry in matches[:15]:
            log(f"  {entry.get('datasetId')}  {entry.get('name')}")
        if matches:
            first = matches[0]
            log(f"\n=== sampling {first.get('name')!r} ({first.get('datasetId')})")
            sample(str(first.get("datasetId")), key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
