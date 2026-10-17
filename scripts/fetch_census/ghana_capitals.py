#!/usr/bin/env python3
"""Ghana -- each district's capital, from English Wikipedia's *Districts of Ghana*.

The Ghana Statistical Service's 2021 census tables (ghana_census) name the
261 districts but not their capitals, and its report on the population of
regions and districts (General Report Volume 3A) has no list of them either.
English Wikipedia's *Districts of Ghana* lists the districts region by region,
each with its capital, in one table per region; each capital is written for
the polygon of the district it names.

Matching is by name within the region, on ghana_census's reduction (without
"Municipal", "Metropolitan", "District" and brackets) and its aliases for the
boundary file's spellings, with ``ALIASES`` below for the article's own. The
boundary file draws 260 districts: Guan, made in 2019 out of part of Hohoe
Municipal, is drawn inside Hohoe's polygon, which gets Hohoe's capital. Every
other polygon must get exactly one of the article's districts and every one of
them but Guan a polygon, or nothing is written.

Usage:
    python -m scripts.fetch_census.ghana_capitals
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_json, log, record, write_json
from .ghana_census import ALIASES as CENSUS_ALIASES
from .ghana_census import REGIONS, key

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import tables  # noqa: E402

TITLE = "Districts of Ghana"
URL = "https://en.wikipedia.org/wiki/Districts_of_Ghana"
API = "https://en.wikipedia.org/w/api.php"
SOURCE = f"English Wikipedia, {TITLE}"
LICENCE = "CC BY-SA 4.0"
OUT = "ghana_capitals.json"
SITE = PROCESSED.parent.parent / "site" / "data"
# (region, the article's reduced name) -> the boundary file's or the census's.
ALIASES = {
    ("Ashanti", "atwimanwabiagya"): "atwimanwabiagyasouth",
    ("Central", "assincentral"): "assinfosu",
    ("Central", "awutusenyawest"): "awutusenya",
    ("Eastern", "akuapimnorth"): "akwapemnorth", ("Eastern", "akuapimsouth"): "akwapemsouth",
    ("Eastern", "nsawamadoagyire"): "nsawamadoagyiri",
    ("North East", "bunkpurugunyankpanduri"): "bunkpurugunakpanduri",
    ("Upper East", "kassenanankana"): "kasenanankana",
    ("Upper East", "kassenanankanawest"): "kasenanankanawest",
    ("Western", "amenficentral"): "wassaamenficentral",
    ("Western", "amenfiwest"): "wassaamenfiwest",
}
# Districts the boundary file draws inside another's polygon.
NOT_DRAWN = {("Oti", "guan")}
DISTRICTS = 261


def heading_region(heading: str) -> str | None:
    """The region a section heading names, the longest match ("Western North",
    not "Western")."""
    found = [r for r in REGIONS if re.search(rf"\b{re.escape(r)}\b", heading)]
    return max(found, key=len) if found else None


def capitals(wikitext: str) -> dict[str, list[tuple[str, str]]]:
    """{region: [(district, capital), ...]} from each region's section's table
    with a District and a Capital column."""
    parts = re.split(r"^(==+)\s*(.*?)\s*\1\s*$", wikitext, flags=re.M)
    out: dict[str, list[tuple[str, str]]] = {}
    region, depth = None, 0
    for j in range(1, len(parts) - 2, 3):
        marks, heading, body = parts[j], parts[j + 1], parts[j + 2]
        named = heading_region(heading)
        if named:
            region, depth = named, len(marks)
        elif len(marks) <= depth:
            region, depth = None, 0
        if region is None:
            continue
        for table in tables(body):
            head = [c.strip().lower() for c in table[0]] if table else []
            if "district" not in head or "capital" not in head:
                continue
            d, c = head.index("district"), head.index("capital")
            for row in table[1:]:
                if len(row) > max(d, c) and row[d].strip() and row[c].strip():
                    seat = re.sub(r",\s*Ghana$", "", row[c].strip())
                    out.setdefault(region, []).append((row[d].strip(), seat))
    return out


def bind(rows: dict[str, list[tuple[str, str]]], admin1: list[dict[str, Any]],
         admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    region_of = {s["id"]: re.sub(r"\s+Region$", "", s["name"]) for s in admin1}
    if sorted(region_of.values()) != sorted(REGIONS):
        raise SystemExit(f"ghana_capitals: region polygons {sorted(region_of.values())}")
    listed: dict[tuple[str, str], tuple[str, str]] = {}
    for region, items in rows.items():
        for name, seat in items:
            k = key(name)
            k = ALIASES.get((region, k), k)
            if (region, k) in listed:
                raise SystemExit(f"ghana_capitals: {region} lists {name!r} twice")
            listed[(region, k)] = (name, seat)
    if len(listed) != DISTRICTS:
        raise SystemExit(f"ghana_capitals: the article lists {len(listed)} districts, not "
                         f"{DISTRICTS}")
    records, used, left = [], set(), []
    for shape in admin2:
        region = region_of.get(shape["parent"])
        raw = key(shape["name"])
        hit = next(((region, k) for k in (CENSUS_ALIASES.get(raw, raw), raw)
                    if (region, k) in listed), None)
        if hit is None or hit in used:
            left.append(f"{shape['name']!r} ({region}, {raw})")
            continue
        used.add(hit)
        name, seat = listed[hit]
        records.append(record(
            f"GHA-SEAT-{shape['id']}", shape["name"], level="admin2", parent="GHA",
            country="GHA", match_by="shape_id", shape_id=shape["id"], capital=seat,
            sources=[{"field": "capital", "name": SOURCE, "url": URL, "license": LICENCE}]))
    unused = sorted(f"{r}: {listed[(r, k)][0]}" for r, k in listed
                    if (r, k) not in used and (r, k) not in NOT_DRAWN)
    if left or unused:
        raise SystemExit(f"ghana_capitals: polygons with no district {left}; districts on no "
                         f"polygon {unused}")
    return records


def fetch() -> tuple[str, int | None]:
    q = urllib.parse.urlencode({"action": "parse", "page": TITLE, "prop": "wikitext|revid",
                                "format": "json", "formatversion": "2", "redirects": "1"})
    data = http_json(f"{API}?{q}", timeout=90)
    parsed = data.get("parse") or {}
    if not parsed.get("wikitext"):
        raise SystemExit(f"ghana_capitals: {TITLE!r} returned no wikitext")
    return parsed["wikitext"], parsed.get("revid")


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    wikitext, revid = fetch()
    rows = capitals(wikitext)
    log(f"ghana_capitals: {TITLE!r}, revision {revid}: "
        + ", ".join(f"{r} {len(v)}" for r, v in rows.items()))
    admin1 = json.loads((SITE / "admin1" / "GHA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "GHA.units.json").read_text())
    records = bind(rows, admin1, admin2)
    log(f"  {len(records)} district capitals")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
