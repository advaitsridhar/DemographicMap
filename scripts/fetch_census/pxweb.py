#!/usr/bin/env python3
"""PxWeb -- one adapter for the many statistical offices that run it.

Most of Europe's national statistical offices publish through PxWeb, and they
all speak the same two-call protocol: GET a table path for its metadata, POST a
query back to the same path for the figures. That makes a new office a few
lines of configuration rather than a new scraper, which is the same bargain the
Eurostat adapter makes and the reason this exists rather than eight files.

What it is *for* is the fields Eurostat does not carry. The Census Hub serves
population, age and sex for every member state on one reference date, but not
ethnicity, religion or language -- those are asked only by the states that ask
them, and published only through their own offices. Central and Eastern Europe
is where that matters: those censuses ask ethnicity and religion together, and
almost nothing else in this dataset does.

Two properties of PxWeb decide the shape of the code below.

A table's variables are named by the office, in its own language and its own
words, so the geography dimension is "Maakond" in Estonia and "region" in
Norway. Rather than hardcode those, each table's config names the variables it
needs and the adapter verifies they exist before asking for anything -- a query
against a variable that is not there returns an error page, not a smaller
answer.

And the query is a POST whose selection must be spelled out. Asking for
everything is what times out or gets refused; asking for one year, every region
and every category of one classification is what works.

Usage:
    python -m scripts.fetch_census.pxweb --country EST
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json,
)

TIMEOUT = 90


class Table:
    """One PxWeb table, and which of its variables mean what.

    ``geo`` and ``group`` are variable *codes* as the office publishes them.
    ``keep`` pins any remaining variable to a single value -- a year, a sex, a
    citizenship -- because a dimension left unpinned multiplies the response and
    usually means summing across something that should not be summed.
    """

    def __init__(self, path: str, field: str, geo: str, group: str,
                 keep: dict[str, str] | None = None, year: int | None = None,
                 note: str = "", drop: tuple[str, ...] = (),
                 geo_len: int | None = None, geo_suffix: str | None = None,
                 national: str | None = None):
        self.path = path
        self.field = field
        self.geo = geo
        self.group = group
        self.keep = keep or {}
        self.year = year
        self.note = note
        self.drop = drop
        # Length of a geography code at the level being asked for. A PxWeb
        # geography variable holds several levels at once, and the office
        # encodes depth in the code: Latvia's country is "LV", its statistical
        # regions "LV00A", its municipalities "LV0001000".
        self.geo_len = geo_len
        # ...and length alone is not always enough. Latvia's towns are the same
        # width as the municipalities that contain them and differ only in the
        # tail: Jekabpils municipality is "LV0031000" and the town of Jekabpils
        # inside it is "LV0031010".
        self.geo_suffix = geo_suffix
        # The geography code that means the whole country. Not guessable from
        # the label: Estonia calls that row "Whole country" and Latvia calls it
        # "Latvia", so looking for the word "total" found Estonia's and missed
        # Latvia's -- in the one table the check was written for.
        self.national = national


# Filled in from what scripts/probe_pxweb.py actually found. An office is only
# listed here once its tables have been seen to exist, be public, and break
# down by a geography the boundary files can join.
#
# Ten instances were walked. Lithuania, Slovakia, Croatia and Serbia answered
# 404 or something that was not JSON at the base URLs tried. Finland rate-limits
# metadata requests and asks language rather than ethnicity. Iceland, Norway,
# Sweden and Denmark ask citizenship, which is a different question. North
# Macedonia's tree returned only broadcast-language tables at the depth walked.
# Slovenia has ethnicity by all 193 municipalities but only from the 1991
# census, against boundaries that have been redrawn twice since, so it is left
# out rather than joined across thirty-five years of redistricting.
#
# What is left is the two Baltic offices, and they are the point: neither
# country has had any ethnicity figure in this dataset, and both publish one
# annually at a level the boundary files carry.
INSTANCES: dict[str, dict[str, Any]] = {
    "EST": {
        "name": "Statistics Estonia",
        "base": "https://andmed.stat.ee/api/v1/en/stat",
        "source": "Statistics Estonia, table RV0222U",
        "url": "https://andmed.stat.ee/en/stat/rahvastik__rahvastikunaitajad-ja"
               "-koosseis__rahvaarv-ja-rahvastiku-koosseis/RV0222U",
        "licence": "CC BY 4.0",
        "level": "admin1",
        "file": "estonia_county",
        "tables": [Table(
            path="rahvastik/rahvastikunaitajad-ja-koosseis/"
                 "rahvaarv-ja-rahvastiku-koosseis/RV0222U.PX",
            field="ethnicity", geo="Maakond", group="Rahvus",
            # Sex must be pinned or males and females are added to a total that
            # already contains both. Year likewise: this is a register count on
            # 1 January, not a census, and every year is in the same table.
            keep={"Aasta": "2026", "Sugu": "1"}, year=2026,
            # "00" is the whole country and "unk" is a county nobody recorded;
            # "784" Tallinn and "793" Tartu city sit *inside* Harju and Tartu
            # counties, so counting them beside their parents would double
            # those two counties' people.
            drop=("unk", "784", "793"), national="00",
            note="Ethnic nationality as recorded in the population register on "
                 "1 January 2026, not a census answer. Estonia asks it of "
                 "residents rather than inferring it from citizenship."),
        ],
    },
    "LVA": {
        "name": "Statistics Latvia",
        "base": "https://data.stat.gov.lv/api/v1/en/OSP_PUB",
        "source": "Central Statistical Bureau of Latvia, table IRE031",
        "url": "https://data.stat.gov.lv/pxweb/en/OSP_PUB/START__POP__IR__IRE/IRE031",
        "licence": "CC BY 4.0",
        "level": "admin1",
        "file": "latvia_municipality",
        "tables": [Table(
            path="POP/IR/IRE/IRE031",
            field="ethnicity", geo="AREA", group="ETHNICITY",
            # IRE031 is the count and IRE0311 the same figures as percentages;
            # taking both would read every number twice.
            keep={"ContentsCode": "IRE031", "TIME": "2026"}, year=2026,
            # Nine characters is the municipality and state-city level. The
            # same variable also carries the country and two vintages of the
            # statistical regions, defined before and after 1 January 2024,
            # which overlap each other.
            geo_len=9, geo_suffix="000", national="LV",
            note="Ethnicity as recorded in the population register at the "
                 "beginning of 2026. 'Other ethnicities' also holds people who "
                 "selected none and people who did not indicate one, so it is "
                 "not a count of anyone in particular."),
        ],
    },
}


def http_json(url: str, payload: dict | None = None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)",
        "Accept": "application/json",
        **({"Content-Type": "application/json"} if data else {}),
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def variables(base: str, table: Table) -> dict[str, dict[str, Any]]:
    """The table's variables by code, so a query can be checked before it is sent."""
    meta = http_json(f"{base}/{table.path}")
    return {v["code"]: v for v in meta.get("variables", [])}


def build_query(table: Table, meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Every region, every category, one value for everything else."""
    missing = [code for code in (table.geo, table.group) if code not in meta]
    if missing:
        raise SystemExit(
            f"{table.path}: no variable {missing} — the office renamed or "
            f"withdrew it. Present: {sorted(meta)}")

    query = []
    for code in (table.geo, table.group):
        query.append({"code": code,
                      "selection": {"filter": "all", "values": ["*"]}})
    for code, value in table.keep.items():
        if code not in meta:
            raise SystemExit(f"{table.path}: cannot pin absent variable {code!r}")
        query.append({"code": code,
                      "selection": {"filter": "item", "values": [value]}})
    # Anything still unpinned would multiply the table and force a sum across a
    # dimension nobody chose. Refuse rather than guess which way to collapse it.
    loose = [c for c in meta
             if c not in {table.geo, table.group} | set(table.keep)
             and len(meta[c].get("values", [])) > 1]
    if loose:
        raise SystemExit(
            f"{table.path}: {loose} left unpinned; each would be summed over. "
            "Add them to keep= with the value the figures should be read at.")
    return {"query": query, "response": {"format": "json-stat2"}}


# ---------------------------------------------------------------------------
# Reading a table back
# ---------------------------------------------------------------------------

# A value whose label starts with this is a sub-category of the one above it.
# Statistics Estonia writes "Other ethnic nationalities" and then "..Ukrainians",
# "..Belorussians" beneath it; keeping both counts those people twice, which is
# the same trap the ABS classification sets with its "... Total" rows.
CHILD_MARKER = ".."

# The label a PxWeb table gives the row that is everyone. It is the denominator
# rather than a category, and it is also the only population figure these tables
# carry, so it is taken out of the shares and kept as the unit's population.
TOTAL_LABELS = ("total", "whole country", "all")


def unstack(payload: dict[str, Any]) -> list[tuple[dict[str, tuple[str, str]], float]]:
    """json-stat2 -> one entry per cell, each carrying its dimensions' codes and labels.

    The values arrive as a single flat array in row-major order over the
    dimensions named in ``id``, so the position in that array *is* the
    combination of categories -- there is no other record of which cell is
    which.
    """
    ids: list[str] = payload["id"]
    sizes: list[int] = payload["size"]
    dims = payload["dimension"]

    order: list[list[str]] = []
    labels: list[dict[str, str]] = []
    for name in ids:
        category = dims[name]["category"]
        index = category["index"]
        # PxWeb sends the index either as code -> position or as a bare list.
        order.append(sorted(index, key=index.get) if isinstance(index, dict)
                     else list(index))
        labels.append(category.get("label") or {})

    strides = [1] * len(sizes)
    for i in range(len(sizes) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]

    values = payload["value"]
    if isinstance(values, dict):        # sparse form: position -> value
        values = [values.get(str(i)) for i in range(strides[0] * sizes[0])]

    out = []
    for flat, value in enumerate(values):
        if value is None:
            continue
        key = {}
        for i, name in enumerate(ids):
            code = order[i][(flat // strides[i]) % sizes[i]]
            key[name] = (code, labels[i].get(code, code))
        out.append((key, float(value)))
    return out


def is_total(label: str) -> bool:
    return label.strip().lower() in TOTAL_LABELS


def wanted_area(code: str, label: str, table: Table) -> bool:
    """Whether a geography value is one of the units being asked for.

    A PxWeb geography variable usually holds several levels at once, and often
    two vintages of one level: Latvia's lists the country, five statistical
    regions as defined before 2024, five as defined after, and then the
    municipalities. Summing or joining across that would double-count half the
    country, so the level is pinned by code length -- the office's own encoding
    of depth -- and everything else is refused.
    """
    if code in table.drop or is_total(label) or label.startswith(CHILD_MARKER):
        return False
    if table.geo_len is not None and len(code) != table.geo_len:
        return False
    return table.geo_suffix is None or code.endswith(table.geo_suffix)


def reject_reason(code: str, label: str, table: Table) -> str:
    if code == table.national:
        return "the country itself"
    if code in table.drop:
        return "named in drop="
    if is_total(label):
        return "a total, not a unit"
    if label.startswith(CHILD_MARKER):
        return f"labelled {CHILD_MARKER!r}, so inside another unit"
    if table.geo_len is not None and len(code) != table.geo_len:
        return f"code is not {table.geo_len} characters"
    return f"code does not end {table.geo_suffix!r}"


def fetch(base: str, table: Table) -> tuple[dict[str, dict[str, Any]], float | None]:
    """One table -> {area code: {"name", "counts", "total"}}, and the country total.

    The country row is dropped from the units and kept as the control. It is
    the office's own statement of how many people the table describes, and the
    units have to add up to it.
    """
    meta = variables(base, table)
    payload = http_json(f"{base}/{table.path}", build_query(table, meta))
    areas: dict[str, dict[str, Any]] = {}
    national: float | None = None
    # Which geography values were left out, and on which rule. A level pinned
    # by the shape of a code is a guess about an office's numbering, and a
    # silent one takes a real unit out with the duplicates: Latvia's first run
    # dropped three towns that sit inside their municipalities and one
    # municipality that does not.
    refused: dict[str, list[str]] = {}
    for key, value in unstack(payload):
        area_code, area_label = key[table.geo]
        group_code, group_label = key[table.group]
        if area_code == table.national and is_total(group_label):
            national = value
        if not wanted_area(area_code, area_label, table):
            refused.setdefault(reject_reason(area_code, area_label, table),
                               []).append(f"{area_code} {area_label}")
            continue
        entry = areas.setdefault(area_code, {"name": area_label, "counts": {},
                                             "total": None})
        if is_total(group_label):
            entry["total"] = value
        elif group_label.startswith(CHILD_MARKER):
            continue                    # counted already inside its parent
        elif group_code not in table.drop:
            entry["counts"][group_label] = entry["counts"].get(group_label, 0.0) + value
    for reason, names in sorted(refused.items()):
        unique = sorted(set(names))
        log(f"    left out ({reason}): {len(unique)} — " + ", ".join(unique[:6])
            + (" ..." if len(unique) > 6 else ""))
    return areas, national


def check(iso3: str, table: Table, areas: dict[str, dict[str, Any]],
          national: float | None = None) -> None:
    """Every unit's categories must add up to the total the table itself gives.

    This is the one control a single table can offer, and it is worth having:
    it is exactly what catches a level of the classification being kept twice
    or dropped once, which is the way these joins go wrong silently.
    """
    bad = []
    for code, entry in areas.items():
        total, counted = entry["total"], sum(entry["counts"].values())
        if not total:
            continue
        if abs(counted - total) > max(0.005 * total, 5):
            bad.append(f"{entry['name']} ({code}): categories {counted:,.0f} "
                       f"against a published {total:,.0f}")
    if bad:
        raise SystemExit(f"{iso3} {table.path}: the categories do not partition the "
                         f"population in {len(bad)} units — " + "; ".join(bad[:3]))
    log(f"    {len(areas)} units, categories sum to the published total in each")

    # ...and the units have to add up to the country, which is the check that
    # catches a unit counted inside another one. Every Latvian municipality's
    # own categories added up perfectly while three towns were being counted
    # twice, once on their own and once inside the municipality holding them:
    # 45 units summing to 1,911,026 against a country of 1,845,096.
    if national is None:
        log("    (no country row in this table: the units cannot be checked "
            "against a whole)")
        return
    summed = sum(e["total"] for e in areas.values() if e["total"])
    if abs(summed - national) > max(0.005 * national, 50):
        raise SystemExit(
            f"{iso3} {table.path}: {len(areas)} units sum to {summed:,.0f} against "
            f"a published national {national:,.0f}, a difference of "
            f"{summed - national:+,.0f}. One of them is inside another, or one "
            f"is missing.")
    log(f"    ...and to {summed:,.0f} against a published national {national:,.0f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    iso3 = args.country.strip().upper()
    spec = INSTANCES.get(iso3)
    if not spec:
        raise SystemExit(f"no PxWeb instance configured for {iso3}. "
                         f"Configured: {sorted(INSTANCES)}")

    log(f"pxweb: {spec['name']} ({iso3})")
    merged: dict[str, dict[str, Any]] = {}
    for table in spec["tables"]:
        log(f"  {table.path}")
        areas, national = fetch(spec["base"], table)
        check(iso3, table, areas, national)
        for code, entry in areas.items():
            slot = merged.setdefault(code, {"name": entry["name"], "fields": {},
                                            "population": None, "notes": {}})
            slot["population"] = slot["population"] or entry["total"]
            slot["fields"][table.field] = shares(entry["counts"], total=entry["total"])
            slot["notes"][table.field] = table.note
            slot["year"] = table.year

    source = {"field": "/".join(sorted({t.field for t in spec["tables"]})),
              "name": spec["source"], "url": spec["url"],
              "license": spec["licence"]}
    records = []
    for code, slot in sorted(merged.items()):
        fields: dict[str, Any] = {}
        for field, rows in slot["fields"].items():
            fields[field] = rows or gap(NOT_AVAILABLE)
            if slot["notes"].get(field):
                fields[f"{field}_note"] = slot["notes"][field]
            fields[f"{field}_year"] = slot.get("year")
        records.append(record(
            f"{iso3}-{code}", slot["name"].strip(),
            level=spec["level"], parent=iso3, codes={"pxweb": code},
            population=(measure(int(round(slot["population"])), year=slot.get("year"),
                                source=spec["source"])
                        if slot["population"] else gap(NOT_AVAILABLE)),
            sources=[source], **fields))

    out = args.out or PROCESSED / f"{spec['file']}.json"
    write_json(out, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
