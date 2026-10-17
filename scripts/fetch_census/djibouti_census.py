#!/usr/bin/env python3
"""Djibouti: the 2024 census's head count by region, and why nothing else is written.

Djibouti's third general census of population and housing (RGPH-3) counted
1,066,809 people on 20 May 2024. The national institute's results by region and
sub-prefecture are tabulated by City Population (citypopulation.de, Thomas
Brinkhoff), which is read here: the five regions, the city of Djibouti (a
region of its own), the sub-prefectures and towns within each region, and the
national row, with men and women for the country only.

**Regions.** Each region's 2024 count. The map carried English Wikipedia's
figures, among them 776,966 for the city of Djibouti, which with the other five
regions' counts makes 9,716 more than the national total, and Obock's 37,856 of
2009.

**The second level.** The map's eleven units in Djibouti are an older division
than the 2024 sub-prefectures (Arta Region has none of its own, and the unit
named Djibouti holds the city and Balbala with the town of Arta and the land
between), and the census publishes no outlines, so whether a unit is a
sub-prefecture of 2024, or which of them make it up, is not established: each
says why it carries no count. Ali Sabeh keeps the figure it has.

**Ages and sexes** are published for the country only: every unit says so.

**Checks.** The regions make the national total, and each region's
sub-prefectures and towns make the region.

Usage:
    python -m scripts.fetch_census.djibouti_census
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import fold
from .cited_sources import Tables, count, main_name

OUT = "djibouti_census.json"
YEAR = 2024
NATIONAL = 1_066_809
SITE = PROCESSED.parent.parent / "site" / "data"
URL = "https://www.citypopulation.de/en/djibouti/admin/"
SOURCE = ("Institut National de la Statistique de Djibouti, Third General Census of Population "
          "and Housing (RGPH-3), 20 May 2024, as City Population (citypopulation.de) tabulates "
          "it")
LICENCE = "citation of citypopulation.de required"
AGES = ("No published count of this unit's ages or sexes has been found: the 2024 census's "
        "results so far give head counts by region and sub-prefecture, and men and women for "
        "the country as a whole.")
UNITS = ("The 2024 census was published for Djibouti's regions and its sub-prefectures of "
         "2024, without their outlines, and whether this unit as drawn is one of them, or "
         "which of them make it up, is not established, so no count is given for it.")


def read_table(html: str) -> dict[str, Any]:
    """{"regions": {key: {name, total, parts}}, "men", "women"} from the page, checked."""
    parser = Tables()
    parser.feed(html)
    table = next((t for t in parser.tables
                  if any("Census 2024" in c for r in t[:2] for c in r)), None)
    if table is None:
        raise SystemExit("djibouti_census: no table on the page has a 2024 census column")
    head = next(r for r in table if any("Census 2024" in c for c in r))
    col = next(i for i, c in enumerate(head) if "Census 2024" in c)
    name_col = next(i for i, c in enumerate(head) if c.strip().lower() == "name")
    status_col = next(i for i, c in enumerate(head) if c.strip().lower() == "status")
    regions: dict[str, dict[str, Any]] = {}
    current = None
    national = None
    for row in table:
        if len(row) <= col or row is head:
            continue
        name, status, figure = main_name(row[name_col]), row[status_col].strip(), count(row[col])
        if figure is None:
            continue
        if status == "Republic":
            national = figure
        elif status == "Region":
            current = regions.setdefault(fold(name), {"name": name, "total": figure, "parts": 0})
        elif status == "City" and fold(name) == "djibouti":
            # The city is a region of its own; its communes follow it.
            current = regions.setdefault("djibouti", {"name": name, "total": figure, "parts": 0})
        elif current is not None:
            current["parts"] += figure
    if national != NATIONAL:
        raise SystemExit(f"djibouti_census: the national row is {national}, not {NATIONAL:,}")
    made = sum(r["total"] for r in regions.values())
    if len(regions) != 6 or made != NATIONAL:
        raise SystemExit(f"djibouti_census: {len(regions)} regions making {made:,}")
    for r in regions.values():
        if r["parts"] != r["total"]:
            raise SystemExit(f"djibouti_census: {r['name']}'s parts make {r['parts']:,}, not "
                             f"{r['total']:,}")
    return {"regions": regions}


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cite = [{"field": "population", "name": SOURCE, "url": URL, "year": YEAR,
             "license": LICENCE}]
    stated = gap(NOT_AVAILABLE, AGES)
    records = []
    for shape in admin1:
        row = table["regions"].get(fold(shape["name"]))
        if row is None:
            raise SystemExit(f"djibouti_census: no 2024 count for {shape['name']}")
        records.append(record(
            f"DJI-2024-{shape['id']}", shape["name"].strip(), level="admin1", parent="DJI",
            country="DJI", match_by="shape_id", shape_id=shape["id"],
            population=measure(row["total"], year=YEAR, source=SOURCE),
            population_note=("The 2024 census's count of everyone in the region." if
                             fold(shape["name"]) != "djibouti" else
                             "The 2024 census's count of everyone in the city of Djibouti, "
                             "a region of its own."),
            median_age=stated, sex_ratio=stated, sources=cite))
    for shape in admin2:
        fields: dict[str, Any] = {"median_age": stated, "sex_ratio": stated}
        if fold(shape["name"]) != "alisabeh":
            fields["population"] = gap(NOT_AVAILABLE, UNITS)
        records.append(record(
            f"DJI-2024-{shape['id']}", shape["name"].strip(), level="admin2", parent="DJI",
            country="DJI", match_by="shape_id", shape_id=shape["id"], sources=cite, **fields))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    ap.parse_args()
    html = http_get(URL, cache=False, timeout=120)
    if not isinstance(html, str):
        html = html.decode("utf-8", "replace")
    table = read_table(html)
    for r in table["regions"].values():
        log(f"  {r['name']}: {r['total']:,}, its parts making it")
    admin1 = json.loads((SITE / "admin1" / "DJI.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "DJI.units.json").read_text())
    records = build(table, admin1, admin2)
    write_json(PROCESSED / OUT, records)
    log(f"  {len(admin1)} regions and {len(admin2)} second-level units written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
