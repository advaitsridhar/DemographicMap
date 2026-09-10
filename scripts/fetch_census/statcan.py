#!/usr/bin/env python3
"""Canada -- 2021 Census Profile for provinces, territories and economic regions.

The Census Profile web service on www12.statcan.gc.ca answers non-browser
clients with an HTML shell for every REST path, valid DGUIDs included -- a
deliberate wall this project does not spoof its way past. The same profile
is published as one downloadable file per geography set, and the set for
"Canada, provinces, territories and economic regions" (catalogue
98-401-X2021008) answers a plain GET on a runner: a 4 MB zip holding a 37 MB
CSV, one row per geography and characteristic. That file was requested and
its column and characteristic lists read before this was written.

The 76 economic regions are what geoBoundaries draws as Canada's second
level, so this adapter fills both levels from the one file.

**The characteristics are a tree.** Each row's CHARACTERISTIC_NAME carries
its depth as leading spaces, two per level, and a block starts at an
unindented "Total - ..." row. A composition is the block's leaves -- the rows
no deeper row follows -- which partition the block's total exactly (to
StatCan's random rounding to a multiple of 5). Religion's leaves are the
denominations under Christian and the other religions beside it; mother
tongue's are the individual languages and the multiple-response
combinations; visible minority's are the twelve groups under "Total visible
minority population" and "Not a visible minority" beside it.

**What the fields are.** Religion is asked once a decade and 2021 asked it.
Canada has no ethnicity question: "visible minority" is a category of the
Employment Equity Act, published beside a separate multi-response ethnic or
cultural origin question, and the record's note says so. Language is mother
tongue for the total population excluding institutional residents (100%
data); religion and visible minority are 25% sample data of the population
in private households, and their block totals are that universe.

Usage:
    python -m scripts.fetch_census.statcan
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import zipfile
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, write_json,
)

URL = ("https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/"
       "download-telecharger/comp/GetFile.cfm?Lang=E&FILETYPE=CSV&GEONO=008")
PAGE = "https://www150.statcan.gc.ca/n1/en/catalogue/98-401-X2021008"
SOURCE = "Statistics Canada, 2021 Census of Population, Census Profile (98-401-X2021008)"
LICENCE = "Statistics Canada Open Licence"
YEAR = 2021

# Block headers, matched as prefixes of the unindented row that opens each.
BLOCKS = {
    "population": "Population, 2021",
    "religion": "Total - Religion for the population in private households",
    "ethnicity": "Total - Visible minority for the population in private households",
    "language": "Total - Mother tongue for the total population excluding institutional residents",
}
NOTES = {
    "religion": ("Statistics Canada 2021 religion question (asked once a decade), 25% "
                 "sample data for the population in private households; shown at the "
                 "denominations StatCan publishes, with 'No religion and secular "
                 "perspectives' as its own category."),
    "ethnicity": ("Statistics Canada publishes 'visible minority', a category of the "
                  "Employment Equity Act, beside a separate multi-response ethnic or "
                  "cultural origin question; neither is an ethnicity question as other "
                  "countries ask one. This is the visible-minority classification, with "
                  "'Not a visible minority' kept as its own category."),
    "language": ("Mother tongue, 2021 Census, total population excluding institutional "
                 "residents (100% data), at the individual languages StatCan publishes; "
                 "people who reported more than one are in the multiple-response "
                 "categories rather than counted twice."),
}
PROVINCES = {
    "10": "Newfoundland and Labrador", "11": "Prince Edward Island",
    "12": "Nova Scotia", "13": "New Brunswick", "24": "Quebec",
    "35": "Ontario", "46": "Manitoba", "47": "Saskatchewan", "48": "Alberta",
    "59": "British Columbia", "60": "Yukon", "61": "Northwest Territories",
    "62": "Nunavut",
}
LEVELS = {"Province": "admin1", "Territory": "admin1", "Economic region": "admin2"}


def depth(name: str) -> int:
    return (len(name) - len(name.lstrip(" "))) // 2


def count(value: str) -> float | None:
    value = (value or "").strip().replace(",", "")
    if not value or value in ("..", "...", "x", "F"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def leaves(rows: list[tuple[str, float | None]]) -> dict[str, float]:
    """The rows of a block that nothing deeper follows, keyed by label.

    ``rows`` is the block's rows in file order after its header, as (name
    with indentation, count). A row is a leaf when the next row is not deeper
    than it. Missing counts (suppressed cells) are skipped, which the total
    check below then reports.
    """
    out: dict[str, float] = {}
    for i, (name, value) in enumerate(rows):
        here = depth(name)
        nxt = depth(rows[i + 1][0]) if i + 1 < len(rows) else 0
        if nxt > here:
            continue                      # a parent
        if value is None:
            continue
        label = name.strip()
        out[label] = out.get(label, 0.0) + value
    return out


def read_profile() -> dict[str, dict[str, Any]]:
    """{geography DGUID: {"name", "level", "code", field: {label: count}}}."""
    blob = http_get(URL, binary=True, timeout=600)
    archive = zipfile.ZipFile(io.BytesIO(blob))
    member = max((n for n in archive.namelist() if n.lower().endswith(".csv")),
                 key=lambda n: archive.getinfo(n).file_size)
    log(f"  {member}: {archive.getinfo(member).file_size:,} bytes")
    geos: dict[str, dict[str, Any]] = {}
    # One block at a time per geography: the header opens it, and the next
    # unindented row closes it.
    current: dict[str, Any] | None = None
    field: str | None = None
    block_rows: list[tuple[str, float | None]] = []
    block_total: float | None = None

    def close() -> None:
        nonlocal field, block_rows, block_total
        if current is not None and field and field != "population":
            current[field] = leaves(block_rows)
            current[f"{field}_total"] = block_total
        field, block_rows, block_total = None, [], None

    with archive.open(member) as fh:
        reader = csv.DictReader(io.TextIOWrapper(fh, encoding="cp1252", newline=""))
        for row in reader:
            level = LEVELS.get(row["GEO_LEVEL"])
            if level is None:
                continue
            dguid = row["DGUID"]
            if current is None or current["dguid"] != dguid:
                close()
                current = geos.setdefault(dguid, {
                    "dguid": dguid, "name": row["GEO_NAME"].strip(), "level": level,
                    "code": row["ALT_GEO_CODE"].strip()})
            name = row["CHARACTERISTIC_NAME"]
            value = count(row["C1_COUNT_TOTAL"])
            if depth(name) == 0:
                close()
                for key, header in BLOCKS.items():
                    if name.strip().startswith(header):
                        field = key
                        block_total = value
                        if key == "population":
                            current["population"] = value
                            field = None
                        break
                continue
            if field:
                block_rows.append((name, value))
    close()
    return geos


def build() -> list[dict[str, Any]]:
    log("statcan: 2021 Census Profile, provinces and economic regions")
    geos = read_profile()
    records = []
    for dguid, geo in geos.items():
        fields: dict[str, Any] = {}
        for key in ("religion", "ethnicity", "language"):
            groups = geo.get(key) or {}
            total = geo.get(f"{key}_total")
            summed = sum(groups.values())
            if not groups or not total:
                fields[key] = gap(NOT_AVAILABLE, f"{key} block not in the profile for this geography")
                continue
            # Leaves partition the block; random rounding to 5 on a few
            # hundred cells can miss by a few hundred people, never by a
            # category. Two percent is far beyond rounding and well short of
            # any real category.
            if abs(summed - total) > max(0.02 * total, 50):
                raise SystemExit(f"statcan: {geo['name']} {key} leaves sum to {summed:,.0f} "
                                 f"against the block total {total:,.0f}")
            fields[key] = shares(groups, total=total) or gap(NOT_AVAILABLE)
            fields[f"{key}_note"] = NOTES[key]
        if geo["level"] == "admin1":
            parent, parent_name = "CAN", None
        else:
            province = geo["code"][:2]
            parent, parent_name = f"CAN-{province}", PROVINCES.get(province)
        records.append(record(
            f"CAN-{geo['code']}", geo["name"], level=geo["level"], parent=parent,
            parent_name=parent_name, country="CAN", codes={"dguid": dguid},
            population=(measure(int(geo["population"]), year=YEAR, source=SOURCE)
                        if geo.get("population") else gap(NOT_AVAILABLE)),
            sources=[{"field": "population/religion/ethnicity/language", "name": SOURCE,
                      "url": PAGE, "license": LICENCE}],
            **fields,
        ))
    by_level = {"admin1": 0, "admin2": 0}
    for r in records:
        by_level[r["level"]] += 1
    log(f"  {by_level}")
    if by_level["admin1"] != 13 or not 70 <= by_level["admin2"] <= 80:
        raise SystemExit(f"statcan: expected 13 provinces and 76 economic regions, read {by_level}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    records = build()
    write_json(PROCESSED / "canada_province.json",
               [r for r in records if r["level"] == "admin1"])
    write_json(PROCESSED / "canada_economic_region.json",
               [r for r in records if r["level"] == "admin2"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
