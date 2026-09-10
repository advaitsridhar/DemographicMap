#!/usr/bin/env python3
"""Read what the CSO's PxStat actually serves for Ireland's Census 2022.

Ireland is 5.2 million people with nothing subnational on this map: its four
provinces and 166 local electoral areas carry no religion, ethnicity or
language at all, and the country's only figures are the Factbook's national
ones. Census 2022 Profile 5 -- "Diversity, Migration, Ethnicity, Irish
Travellers and Religion" -- is exactly the missing release.

The CSO does not run PxWeb. It runs **PxStat**, its own open-source platform,
whose API is a set of RPC-style methods rather than the navigable folder tree
``probe_pxweb`` walks, so that probe cannot see it and the endpoint shape has
to be established rather than assumed.

Which is the point of this script. Several URL shapes are plausible and only
the server knows which is real, so this tries each and reports what came back
-- status, bytes, first line -- before parsing anything. A 404 here is a fact
about the URL this script guessed, not about what Ireland publishes: four
guessed paths answering 400 was read as "NADA has no data" earlier in this
project and it was wrong both times.

Nothing is written and nothing is committed. The output is the log.

Usage:
    python scripts/probe_cso.py --search religion,ethnic,irish travel
    python scripts/probe_cso.py --matrix F5013
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://ws.cso.ie/public"
AGENT = "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)"

# Every shape worth trying, in the order most likely to be right. Reported
# individually so a failure names which one failed.
_RPC = urllib.parse.quote(json.dumps({
    "jsonrpc": "2.0", "method": "PxStat.Data.Cube_API.ReadCollection",
    "params": {"language": "en"}, "id": 1,
}))
COLLECTION_URLS = [
    f"{BASE}/api.restful/PxStat.Data.Cube_API.ReadCollection/JSON-stat/2.0/en",
    f"{BASE}/api.restful/PxStat.Data.Cube_API.ReadCollection",
    f"{BASE}/api.jsonrpc?data={_RPC}",
]


def get(url: str, timeout: int = 120) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT,
                                                   "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()[:2000]
    except Exception as err:                          # noqa: BLE001 -- reported
        print(f"    {type(err).__name__}: {err}")
        return 0, b""


def try_urls(urls: list[str], label: str) -> tuple[str, Any] | tuple[None, None]:
    """The first URL that answers JSON, with every attempt reported."""
    print(f"\n== {label}")
    for url in urls:
        if not url:
            continue
        status, body = get(url)
        head = body[:120].decode("utf-8", "replace").replace("\n", " ")
        print(f"  {status} {len(body):>9,} B  {url[:110]}")
        print(f"      {head}")
        if status == 200 and body:
            try:
                return url, json.loads(body)
            except ValueError:
                print("      (200 but not JSON)")
    return None, None


def walk_collection(payload: Any, needles: list[str]) -> list[dict[str, str]]:
    """Every table in the collection whose title matches, however it is nested.

    PxStat's collection is JSON-stat 2.0, whose "link.item" holds one entry per
    dataset -- but the exact nesting has changed between releases, so this
    searches for the shape rather than indexing into a path that may not exist.
    """
    found: list[dict[str, str]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            label = node.get("label") or node.get("title") or ""
            href = node.get("href") or ""
            extension = node.get("extension") or {}
            matrix = (extension.get("matrix") if isinstance(extension, dict) else None) or ""
            if isinstance(label, str) and label:
                if not needles or any(n in label.lower() for n in needles):
                    found.append({"label": label, "matrix": str(matrix),
                                  "href": str(href),
                                  "updated": str(node.get("updated") or "")})
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return found


def describe(matrix: str) -> int:
    """One table's dimensions, and how many categories each holds.

    The geography dimension is the one that decides whether a table is usable
    at all: 166 local electoral areas would fill the shapes this map draws, 26
    counties would fill none of them, and the State alone would fill nothing
    the Factbook has not already.
    """
    urls = [
        f"{BASE}/api.restful/PxStat.Data.Cube_API.ReadMetadata/{matrix}/JSON-stat/2.0/en",
        f"{BASE}/api.restful/PxStat.Data.Cube_API.ReadDataset/{matrix}/JSON-stat/2.0/en",
    ]
    url, payload = try_urls(urls, f"metadata for {matrix}")
    if not payload:
        print(f"  no shape answered for {matrix}; that is this script's URLs, "
              f"not a statement about the table")
        return 1

    print(f"  label: {payload.get('label')}")
    print(f"  updated: {payload.get('updated')}")
    for key in ("note", "extension"):
        value = payload.get(key)
        if value:
            print(f"  {key}: {json.dumps(value)[:400]}")
    dimension = payload.get("dimension") or {}
    order = payload.get("id") or list(dimension)
    for name in order:
        entry = dimension.get(name) or {}
        category = entry.get("category") or {}
        labels = category.get("label") or category.get("index") or {}
        items = list(labels.items()) if isinstance(labels, dict) else list(enumerate(labels))
        print(f"\n  dimension {name!r}: {entry.get('label')} -- {len(items)} categories")
        for code, label in items[:14]:
            print(f"      {code:<12} {label}")
        if len(items) > 14:
            print(f"      ... and {len(items) - 14} more")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--search", default="religion,ethnic,irish travel,nationality",
                    help="comma-separated terms matched against table titles")
    ap.add_argument("--matrix", default=None,
                    help="describe one table's dimensions and stop")
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args()

    if args.matrix:
        return describe(args.matrix)

    url, payload = try_urls(COLLECTION_URLS, "collection")
    if not payload:
        print("\nNo collection URL answered JSON. That is a fact about the four "
              "URLs above and not about what the CSO publishes.")
        return 1
    print(f"\n  collection came from {url}")

    needles = [t.strip().lower() for t in args.search.split(",") if t.strip()]
    matches = walk_collection(payload, needles)
    seen: set[str] = set()
    unique = []
    for row in matches:
        key = row["matrix"] or row["label"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    print(f"\n== {len(unique)} tables matching {needles}")
    for row in unique[:args.limit]:
        print(f"  {row['matrix']:<10} {row['updated'][:10]:<12} {row['label'][:130]}")
    if len(unique) > args.limit:
        print(f"  ... and {len(unique) - args.limit} more")

    everything = walk_collection(payload, [])
    print(f"\n  ({len(everything)} labelled nodes in the collection in total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
