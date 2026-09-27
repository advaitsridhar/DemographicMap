#!/usr/bin/env python3
"""Sweden: population, median age and sex ratio for the 290 kommuner and 21 län.

Statistics Sweden (SCB) publishes the register population on 31 December by
region, marital status, single year of age and sex. Two tables carry it:
``BefolkningNy`` (1968-2024) and ``BefolkningCKM`` (2025 onward), which differ
in how the age variable is coded -- the newer one lists single years beside
five- and ten-year bands and three different totals, one per banding. The
single years are "0".."99" and the open class "100+1"; "TOT1" is their total,
and it is the check that the single years were all read.

Marital status is pinned to its total ("SC"), and both sexes are read so that
the ratio and the total come from one query. The 290 kommuner are the office's
current units (unchanged since Knivsta in 2003), and the map draws those.

Sweden's census is compiled from registers, and no register holds religion,
mother tongue or ethnicity; those fields keep the existing policy, and nothing
here writes them.

Checks: each region's single years make its published total; the kommuner make
their län; the län make the country; every kommun and län is bound one to one;
the national median from the single years is within 0.3 years of Eurostat's
(demo_pjanind, computed from SCB's own count). From 2025 SCB perturbs every
cell by the cell-key method ("CKM" in the table's name), so the sums hold to
within a few people rather than exactly; the run prints the worst difference.

Usage:
    python -m scripts.fetch_census.sweden
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any, Iterable

from ._shared import PROCESSED, log, record, write_json
from .binding import fold
from .nordic_common import (AgeSex, bind_rows, check_national_median, check_parts,
                            load_units, request_json)
from .pxweb import unstack

BASE = "https://api.scb.se/OV0104/v1/doris/{lang}/ssd/BE/BE0101/BE0101A/{table}"
# The table, its population content code, its open age class and the total
# that belongs to the single-year banding.
TABLE, CONTENT, TOP, TOTAL = "BefolkningCKM", "000007ME", "100+1", "TOT1"
# The cell-key method moves each published cell by a few people. A region's
# 202 single-year cells then sum to within a few dozen of its own (separately
# perturbed) total -- Vaxholm's came to 11,614 against 11,635 -- while one
# total against another differs by a handful. Both allowances are about five
# standard deviations of that noise; a misread table misses by thousands.
CKM_CELLS_SLACK = 90     # people: 202 perturbed cells against one perturbed total
CKM_TOTALS_SLACK = 50    # people: a few dozen perturbed totals against another
CKM_NOTE = (" SCB perturbs every published cell slightly (the cell-key method), so a "
            "count can differ by a few people from the register itself.")
SOURCE = "Statistics Sweden (SCB)"
PAGE = ("https://www.statistikdatabasen.scb.se/pxweb/en/ssd/START__BE__BE0101__BE0101A/"
        "{table}/")
OUT = PROCESSED / "sweden_kommun.json"
ALIASES = {"Göteborg": "Gothenburg"}     # the boundary file's English exonym


def read_cells(cells: Iterable[tuple[dict[str, Any], float]], top: str = TOP,
               total: str = TOTAL) -> tuple[dict[str, AgeSex], dict[str, float]]:
    """json-stat cells -> each region's people by single year and sex, and its
    published total. ``top`` ("100+1") is the open class, read as 100; ``total``
    ("TOT1") is the total that belongs to the single-year banding. Any other age
    code -- a band, or another banding's total -- stops the run: the query asks
    for single years and one total only, so one would mean the layout moved."""
    people: dict[str, AgeSex] = defaultdict(AgeSex)
    published: dict[str, float] = defaultdict(float)
    for key, value in cells:
        region, age, sex = key["Region"][0], key["Alder"][0], key["Kon"][0]
        if age == total:
            published[region] += value
            continue
        if age != top and not age.isdigit():
            raise SystemExit(f"{TABLE}: age code {age!r} is neither a single year, {top} "
                             f"nor {total}")
        people[region].add(100 if age == top else int(age), "m" if sex == "1" else "f", value)
    return people, published


def check_cells(people: dict[str, AgeSex], published: dict[str, float]) -> float:
    """Each region's single years against its published total, within the
    cell-key noise; returns the worst difference as a share of the total.

    From 2025 SCB protects its tables with the cell-key method: every cell,
    totals included, carries a small random perturbation, so a region's single
    years need not add to its published total exactly. A difference of a few
    people is that noise; anything larger is a misread.
    """
    worst = 0.0
    for region, got in people.items():
        if region not in published:
            raise SystemExit(f"{TABLE} {region}: single years but no published total")
        off = abs(got.total - published[region])
        worst = max(worst, off / max(published[region], 1))
        if off > max(CKM_CELLS_SLACK, 0.001 * published[region]):
            raise SystemExit(f"{TABLE} {region}: single years make {got.total:,.0f} against "
                             f"a published {published[region]:,.0f}")
    return worst


def bind_kommuner(sv: dict[str, str], kommuner: list[str]) -> dict[str, str]:
    """SCB's kommun codes -> the map's shape ids, within each län. Every kommun
    must find its polygon and every polygon its kommun, or the run stops."""
    bound, missing, left, pieces = bind_rows(
        "SWE", "admin2", {c: (sv[c], sv[c[:2]]) for c in kommuner}, aliases=ALIASES)
    if missing or left:
        raise SystemExit(f"sweden: kommuner with no polygon {missing}; polygons with no "
                         f"kommun {[s['name'] for s in left]}")
    log(f"  all {len(bound)} kommuner bound one to one; pieces set aside: "
        f"{[s['name'] for s in pieces] or 'none'}")
    return bound


def bind_lan(sv: dict[str, str], counties: list[str]) -> dict[str, dict[str, Any]]:
    """SCB's län codes -> the map's admin1 units, by the Swedish name, one to one."""
    admin1 = {fold(u["name"]): u for u in load_units("SWE", "admin1")}
    out = {}
    for code in counties:
        shape = admin1.get(fold(sv[code]))
        if shape is None:
            raise SystemExit(f"sweden: län {sv[code]!r} has no polygon")
        out[code] = shape
    if len({s["id"] for s in out.values()}) != len(out) or len(out) != len(admin1):
        raise SystemExit(f"sweden: {len(out)} län bound to {len(admin1)} polygons")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    log("sweden: SCB population by region, age and sex")
    table, top, total = TABLE, TOP, TOTAL
    url = BASE.format(lang="en", table=table)
    meta = {v["code"]: v for v in request_json(url)["variables"]}
    year = meta["Tid"]["values"][-1]
    ages = [a for a in meta["Alder"]["values"] if a.isdigit()] + [top]
    if len(ages) != 101 or total not in meta["Alder"]["values"]:
        raise SystemExit(f"{table}: expected ages 0..99, {top} and {total}; the age list is "
                         f"{meta['Alder']['values']}")
    body = request_json(url, {"query": [
        {"code": "Region", "selection": {"filter": "item", "values": meta["Region"]["values"]}},
        {"code": "Civilstand", "selection": {"filter": "item", "values": ["SC"]}},
        {"code": "Alder", "selection": {"filter": "item", "values": ages + [total]}},
        {"code": "Kon", "selection": {"filter": "item", "values": ["1", "2"]}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": [CONTENT]}},
        {"code": "Tid", "selection": {"filter": "item", "values": [year]}},
    ], "response": {"format": "json-stat2"}})
    names = dict(zip(meta["Region"]["values"], meta["Region"]["valueTexts"]))
    local = {v["code"]: v for v in request_json(BASE.format(lang="sv", table=table))["variables"]}
    sv = dict(zip(local["Region"]["values"], local["Region"]["valueTexts"]))
    people, published = read_cells(unstack(body), top, total)
    worst = check_cells(people, published)
    log(f"  single years against each region's published total: worst {100 * worst:.3f}%")
    counties = sorted(c for c in names if len(c) == 2 and c != "00")
    kommuner = sorted(c for c in names if len(c) == 4)
    date = f"31 December {year}"
    page = PAGE.format(table=table)
    source = f"{SOURCE}, {table}"
    log(f"  {table} {year}: {len(kommuner)} kommuner, {len(counties)} län; "
        f"Sweden {people['00'].total:,.0f}")
    # SCB's 31 December is Eurostat's 1 January of the next year.
    check_national_median("SE", int(year) + 1, people["00"].median(), f"{table} {year}")
    # The sums are of published totals, each perturbed once, rather than of
    # single years, whose noise would add up over hundreds of cells.
    check_parts({c: published[c] for c in counties}, published["00"], "län -> Sweden",
                0.0001, CKM_TOTALS_SLACK)
    for county in counties:
        check_parts({c: published[c] for c in kommuner if c[:2] == county},
                    published[county], f"kommuner -> {sv[county]}", 0.0001, CKM_TOTALS_SLACK)

    def fields(code: str) -> dict:
        out = people[code].fields(year=int(year), source=source, url=page, date=date,
                                  extra_note=CKM_NOTE)
        # The population is the table's own total, not the single years' sum.
        out["population"]["value"] = int(round(published[code]))
        return out

    shapes = load_units("SWE", "admin2")
    labels = {s["id"]: s["name"] for s in shapes}
    bound = bind_kommuner(sv, kommuner)
    lan = bind_lan(sv, counties)
    records = []
    for code in kommuner:
        sid = bound[code]
        records.append(record(
            f"SWE-SCB-{code}", sv[code], level="admin2", parent="SWE", country="SWE",
            parent_name=sv[code[:2]], codes={"scb": code}, match_by="shape_id", shape_id=sid,
            aliases=[labels[sid]] if labels[sid] != sv[code] else [],
            **fields(code)))
    for code in counties:
        shape = lan[code]
        records.append(record(
            f"SWE-SCB-{code}", shape["name"], level="admin1", parent="SWE", country="SWE",
            codes={"scb": code}, match_by="shape_id", shape_id=shape["id"],
            aliases=[names[code]], **fields(code)))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
