#!/usr/bin/env python3
"""Singapore -- resident population and age structure by planning region.

The Department of Statistics publishes through the SingStat Table Builder API,
and table M810771 gives, for each of the five planning regions, the resident
count with a male/female split and nineteen five-year age bands.

Two things about it decide what this adapter is willing to say.

**It counts residents, not everybody.** "Resident" means citizens and permanent
residents; Singapore's roughly six million people include around 1.8 million on
work passes and other long-term permits who are enumerated nationally but not in
this series. So the five regions sum to about 4.2 million against a country
total that is far larger, and every figure here carries a note saying so. A map
that showed the two side by side without explaining the gap would look simply
wrong.

**Median age is derived, not published.** The table gives grouped bands, so the
median is interpolated within whichever band contains the midpoint. That is
standard demography and it is not a measurement -- ``median_age_note`` says so,
because everywhere else in this map the median age is a figure a statistical
office published directly.

Religion, ethnicity and language are all collected by Singapore's census, but
none is published by planning region in this series, so each is an explicit
``not_available`` naming what is missing rather than a bare blank.

Usage:
    python -m scripts.fetch_census.singstat
    python -m scripts.fetch_census.singstat --input data/raw/singapore/M810771.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, gap, http_json, log, measure, record, write_json,
)

TABLE = "M810771"
API = f"https://tablebuilder.singstat.gov.sg/api/table/tabledata/{TABLE}"
CACHE = RAW / "singapore" / f"{TABLE}.json"
SOURCE = "Singapore Department of Statistics, SingStat Table Builder"
PORTAL = "https://tablebuilder.singstat.gov.sg/table/TS/" + TABLE

# "Central Region (Male)" -> ("Central Region", "Male"); "Central Region" -> (name, "")
SERIES = re.compile(r"^(?P<name>.+?)(?: \((?P<sex>Male|Female)\))?$")
BAND = re.compile(r"^(?P<low>\d+)\s*-\s*(?P<high>\d+) Years$")
OPEN_BAND = re.compile(r"^(?P<low>\d+) Years & Over$")

RESIDENT_NOTE = (
    "SingStat counts residents -- citizens and permanent residents. Singapore's "
    "total population is considerably larger: roughly 1.8 million people on work "
    "passes and other long-term permits are enumerated nationally but not in this "
    "series, so the five regions do not sum to the country figure shown above.")

NOT_BY_REGION = (
    "Singapore's census collects this, but SingStat does not publish it by "
    "planning region in the annual series used here -- only nationally, and by "
    "census planning area in the decennial release.")


def load(path: Path | None) -> dict[str, Any]:
    """The API when it can be reached, the committed payload when it cannot.

    The build sandbox has no route to tablebuilder.singstat.gov.sg, so this
    tries the live table first and falls back to the cached copy. On a runner
    the fetch succeeds and the cache is ignored, which is what keeps the figures
    refreshable rather than frozen at whatever was committed. Asking the network
    is the only reliable test: a socket connect succeeds against a proxy that
    then refuses the request.
    """
    if path:
        log(f"  reading {path}")
        return json.loads(path.read_text())
    try:
        log(f"  fetching {API}")
        return http_json(API, timeout=120)
    except Exception as exc:
        if not CACHE.exists():
            raise SystemExit(f"{API} unreachable and no cached payload at {CACHE}: {exc}")
        log(f"  unreachable ({type(exc).__name__}); using the cached payload {CACHE}")
        return json.loads(CACHE.read_text())


def series_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("Data") or payload.get("data") or {}
    rows = data.get("row") or []
    if not rows:
        raise SystemExit(f"{TABLE}: no rows in the response; keys were {sorted(data)}")
    return rows


def latest_year(rows: list[dict[str, Any]]) -> str:
    years = {c["key"] for row in rows for c in row.get("columns", []) if c.get("key")}
    if not years:
        raise SystemExit(f"{TABLE}: no periods in the response")
    return max(years)


def value(row: dict[str, Any], year: str) -> float | None:
    for column in row.get("columns", []):
        if column.get("key") == year:
            try:
                return float(column.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def parse(payload: dict[str, Any]) -> tuple[str, dict[str, dict[str, Any]]]:
    """Region -> totals, sexes and age bands, for the most recent period."""
    rows = series_rows(payload)
    year = latest_year(rows)
    regions: dict[str, dict[str, Any]] = {}
    current: str | None = None

    for row in rows:
        text = (row.get("rowText") or "").strip()
        number = str(row.get("seriesNo") or "")
        amount = value(row, year)
        if amount is None:
            continue

        if "." not in number:            # a top-level series: a region, or one sex of it
            match = SERIES.match(text)
            name, sex = match.group("name"), match.group("sex")
            unit = regions.setdefault(name, {"population": None, "male": None,
                                             "female": None, "bands": {}})
            if sex == "Male":
                unit["male"] = amount
            elif sex == "Female":
                unit["female"] = amount
            else:
                unit["population"] = amount
            # Age bands hang off the region's own series, not the sex splits.
            current = name if sex is None else None
        elif current:                    # an age band beneath the region total
            regions[current]["bands"][text] = amount

    log(f"  {len(regions)} planning regions, reference period {year}")
    return year, regions


def median_from_bands(bands: dict[str, float]) -> float | None:
    """Median age interpolated within the band holding the midpoint.

    Derived, not published: the table reports five-year groups, so this is the
    standard grouped-median interpolation rather than a figure the Department
    calculated. Everywhere else in this map median age comes straight from a
    statistical office, which is why the record says which one this is.
    """
    ordered = []
    for label, count in bands.items():
        closed, open_ended = BAND.match(label), OPEN_BAND.match(label)
        if closed:
            low, high = int(closed.group("low")), int(closed.group("high"))
            ordered.append((low, high + 1, count))
        elif open_ended:
            low = int(open_ended.group("low"))
            ordered.append((low, low + 5, count))     # nominal width for the tail
    if not ordered:
        return None
    ordered.sort()
    total = sum(count for _, _, count in ordered)
    if not total:
        return None

    midpoint, cumulative = total / 2.0, 0.0
    for low, high, count in ordered:
        if cumulative + count >= midpoint and count:
            return round(low + (midpoint - cumulative) / count * (high - low), 1)
        cumulative += count
    return None


def build(year: str, regions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for name, unit in sorted(regions.items()):
        population, male, female = unit["population"], unit["male"], unit["female"]
        if not population:
            continue
        ratio = round(1000.0 * female / male) if male and female else None
        median = median_from_bands(unit["bands"])
        out.append(record(
            f"SGP-R-{name.replace(' ', '-')}", name, level="admin1", parent="SGP",
            codes={"singstat_table": TABLE, "planning_region": name},
            population=measure(int(population), year=int(year), source=SOURCE,
                               unit="residents"),
            population_note=RESIDENT_NOTE,
            sex_ratio=(measure(ratio, unit="females_per_1000_males",
                               year=int(year), source=SOURCE)
                       if ratio else gap(NOT_AVAILABLE)),
            median_age=(measure(median, unit="years", year=int(year), source=SOURCE)
                        if median else gap(NOT_AVAILABLE)),
            median_age_note=(
                "Interpolated from the five-year age bands SingStat publishes, not a "
                "median the Department reported. It is also the median age of "
                "residents only. Elsewhere on this map median age is a published "
                "figure, so the two are not exactly like for like."),
            religion=gap(NOT_AVAILABLE, NOT_BY_REGION),
            ethnicity=gap(NOT_AVAILABLE, NOT_BY_REGION),
            language=gap(NOT_AVAILABLE, NOT_BY_REGION),
            sources=[{"field": "population/sex ratio/median age", "name": SOURCE,
                      "url": PORTAL, "year": int(year),
                      "note": f"Table {TABLE}, Singapore residents by planning "
                              f"region, age group and sex."}],
        ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=None,
                    help=f"a saved {TABLE} payload; omit to call the API")
    args = ap.parse_args()

    year, regions = parse(load(args.input))
    rows = build(year, regions)
    total = sum(r["population"]["value"] for r in rows)
    log(f"  {len(rows)} regions, {total:,} residents in {year}")
    write_json(PROCESSED / "singapore_region.json", rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
