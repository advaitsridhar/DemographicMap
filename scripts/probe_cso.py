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
# Measured, not guessed: the JSON-stat-suffixed path answers 500 and the bare
# one answers 45 MB of JSON-stat collection, which is the reverse of what
# the ReadDataset shape below would suggest. Both are kept and both are
# reported, so the day the CSO fixes the first one this still works.
COLLECTION_URLS = [
    f"{BASE}/api.restful/PxStat.Data.Cube_API.ReadCollection",
    f"{BASE}/api.restful/PxStat.Data.Cube_API.ReadCollection/JSON-stat/2.0/en",
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


def datasets(payload: Any) -> list[dict[str, Any]]:
    """Every dataset in the collection, with its dimensions and their sizes.

    The collection is 45 MB and 65,266 labelled nodes because it embeds each
    dataset's own dimension block, which is the useful accident here: one fetch
    answers both "which tables are about religion" and "how many areas does
    each one break down by", and the second question is the one that decides
    whether a table is usable.

    A node is a dataset when it carries a matrix code. Dimension labels --
    "Religion", "Ethnic or Cultural Background" -- are labelled nodes too, and
    counting those as tables is how a first pass reported 281 matches that were
    mostly the same handful of datasets seen from the inside.
    """
    out: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            extension = node.get("extension")
            matrix = (extension or {}).get("matrix") if isinstance(extension, dict) else None
            if matrix:
                dims = []
                dimension = node.get("dimension") or {}
                for name in (node.get("id") or list(dimension)):
                    entry = dimension.get(name) or {}
                    category = entry.get("category") or {}
                    labels = category.get("label") or category.get("index") or {}
                    dims.append({"name": name,
                                 "label": entry.get("label") or name,
                                 "size": len(labels),
                                 "sample": list(labels.values())[:4]
                                 if isinstance(labels, dict) else []})
                out.append({"matrix": str(matrix),
                            "label": str(node.get("label") or ""),
                            "updated": str(node.get("updated") or ""),
                            "dims": dims})
                return                      # a dataset's insides are not datasets
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return out


def geography_of(row: dict[str, Any]) -> dict[str, Any] | None:
    """The dimension that is a place, if the dataset has one.

    Recognised by name rather than by position: PxStat puts STATISTIC and TLIST
    (the time dimension) in every dataset, and whatever remains is the subject
    and the geography in an order that is not guaranteed.
    """
    for dim in row["dims"]:
        name = dim["name"].upper()
        label = dim["label"].lower()
        if name in ("STATISTIC",) or name.startswith("TLIST"):
            continue
        if any(word in label for word in
               ("area", "region", "county", "province", "electoral",
                "administrative", "town", "settlement", "aggregate")):
            return dim
    return None


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
    ap.add_argument("--search", default="religion,ethnic,irish travel",
                    help="comma-separated terms matched against table titles")
    ap.add_argument("--census", default=None,
                    help="only tables whose title names this census year, e.g. 2022")
    ap.add_argument("--matrix", default=None,
                    help="describe one table's dimensions and stop")
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args()

    if args.matrix:
        return describe(args.matrix)

    url, payload = try_urls(COLLECTION_URLS, "collection")
    if not payload:
        print("\nNo collection URL answered JSON. That is a fact about the URLs "
              "above and not about what the CSO publishes.")
        return 1
    print(f"\n  collection came from {url}")

    rows = datasets(payload)
    print(f"  {len(rows)} datasets in the collection")

    needles = [term.strip().lower() for term in args.search.split(",") if term.strip()]
    matches = [r for r in rows
               if any(n in r["label"].lower() for n in needles)
               and (not args.census or args.census in r["label"])]
    matches.sort(key=lambda r: (-len(r["label"]), r["matrix"]))
    label = f"{len(matches)} datasets matching {needles}"
    if args.census:
        label += f" from the {args.census} census"
    print(f"\n== {label}")
    for row in matches[:args.limit]:
        place = geography_of(row)
        where = (f"{place['size']:>5} x {place['label'][:34]}" if place
                 else "    ? no geography dimension recognised")
        print(f"\n  {row['matrix']:<9} {row['updated'][:10]}  {row['label'][:120]}")
        print(f"      geography: {where}")
        if place and place["sample"]:
            print(f"      first areas: {'; '.join(str(s) for s in place['sample'])}")
        for dim in row["dims"]:
            print(f"      dim {dim['name']:<22} {dim['size']:>6}  {dim['label'][:60]}")
    if len(matches) > args.limit:
        print(f"\n  ... and {len(matches) - args.limit} more")

    # What geographies exist at all, across every matching table. This is the
    # number the adapter lives or dies by: geoBoundaries draws 4 provinces and
    # 166 local electoral areas for Ireland, and a table published only for 26
    # counties fills none of those shapes.
    sizes: dict[str, int] = {}
    for row in matches:
        place = geography_of(row)
        if place:
            key = f"{place['label']} ({place['size']})"
            sizes[key] = sizes.get(key, 0) + 1
    print("\n== geographies offered by the matching tables")
    for key, count in sorted(sizes.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>4} tables  {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
