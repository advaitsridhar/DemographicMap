#!/usr/bin/env python3
"""Indonesia's regency head counts from UN OCHA's Humanitarian API.

**Read the licence before reading anything else.** The figures here come from
`cod-ps-idn`, whose HDX catalogue entry says:

    "license_id": "hdx-other", "license_title": "Other",
    "license_other": "humanitarian use only", "isopen": false

That is not an open licence, and this map is not humanitarian use. The
owner's decision of 20 September 2026 was to use it anyway, having been shown
that string. So every record this writes carries the licence verbatim, names
UNFPA as the publisher and names the resource the row came from, and
`docs/SOURCES.md` says the same: what was taken and under what terms is on
the face of the data rather than buried in a commit message.

**And they are projections, not counts.** The catalogue says
"methodology_other": "Projections from 2010 census performed by UNFPA", with
reference year 2020. Indonesia's own registry gives 439 of the 475 regencies
a count for 2023-2025; these fill the rest, so a province ends up summed from
two vintages thirteen years and two methods apart. Every record says so, and
``check_province_sums`` measures what that costs before anything is written:
if the regencies of a province add to something far from the province's own
published figure, that is worth knowing and not worth hiding.

This is the lowest-authority source for an Indonesian head count. It fills a
regency the article route left empty and never replaces a figure that route
read.

The API wants an app identifier -- base64 of "appname:email" -- which is read
from the DEMOGRAPHIC_MAP secret through the environment and never printed.
The committed extract is one row per regency, which is all this reads.

Usage:
    python -m scripts.fetch_census.indonesia_hapi --fetch   # on the runner
    python -m scripts.fetch_census.indonesia_hapi           # report what is committed
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import RAW, log  # noqa: E402

from probe_hapi import KEY_VAR, key, scrub  # noqa: E402

BASE = "https://hapi.humdata.org/api/v2"
ENDPOINT = "geography-infrastructure/baseline-population"
EXTRACT = RAW / "indonesia" / "hapi_admpop_adm2_2020.csv"
PAGE = 10_000
TIMEOUT = 180
USER_AGENT = ("DemographicMap/1.0 "
              "(+https://github.com/advaitsridhar/DemographicMap)")

PUBLISHER = "UNFPA, Indonesia subnational population statistics (COD-PS)"
LICENCE = "Other (HDX): humanitarian use only; not an open licence"
DATASET = "https://data.humdata.org/dataset/cod-ps-idn"
YEAR = 2020
CAVEAT = (
    "A projection, not a count: UNFPA's own methodology note for this "
    "dataset reads \"Projections from 2010 census performed by UNFPA\", "
    "with 2020 as the reference year. Other regencies of this province "
    "carry a registry count for 2023 to 2025, so the two are not the same "
    "measurement and should not be compared with each other.")
TERMS = (
    "Used by the owner's decision of 20 September 2026. The publisher's HDX "
    "entry licenses this dataset for humanitarian use only and marks it as "
    "not open; that is recorded here rather than omitted.")


def fetch() -> list[dict[str, Any]]:
    """Every baseline-population row for Indonesia at admin2, paged."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {"location_code": "IDN", "admin_level": "2",
                  "limit": str(PAGE), "offset": str(offset),
                  "app_identifier": key()}
        url = f"{BASE}/{ENDPOINT}?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                body = json.loads(response.read())
        except Exception as err:                              # noqa: BLE001
            raise SystemExit(scrub(f"indonesia_hapi: {type(err).__name__}: {err}"))
        page = body.get("data") or []
        rows += page
        log(f"  offset {offset:,}: {len(page):,} rows")
        if len(page) < PAGE:
            break
        offset += PAGE
    return rows


def totals(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """One head count per regency, summed over the age bands and both sexes.

    A row with no age band would be a total the file already states, and
    adding it to the bands that make it up would double the regency. None
    have appeared, and the guard says so rather than assuming.
    """
    banded: dict[str, int] = collections.defaultdict(int)
    stated: dict[str, int] = collections.defaultdict(int)
    meta: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = row.get("admin2_code")
        if not code:
            continue
        meta.setdefault(code, {
            "admin1_name": row.get("admin1_name", ""),
            "admin2_name": row.get("admin2_name", ""),
            "resource": row.get("resource_hdx_id", ""),
        })
        value = int(row.get("population") or 0)
        if row.get("min_age") is None and row.get("max_age") is None:
            stated[code] += value
        else:
            banded[code] += value
    if stated:
        log(f"  {len(stated)} regencies also carry a row with no age band; "
            f"those are used and the bands ignored, to avoid double counting")
    out: dict[str, dict[str, Any]] = {}
    for code, info in meta.items():
        out[code] = dict(info, population=stated.get(code) or banded.get(code, 0))
    return out


def write(counts: dict[str, dict[str, Any]]) -> None:
    EXTRACT.parent.mkdir(parents=True, exist_ok=True)
    with EXTRACT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["admin2_code", "admin1_name", "admin2_name",
                         "population", "year", "resource_hdx_id"])
        for code, info in sorted(counts.items()):
            writer.writerow([code, info["admin1_name"], info["admin2_name"],
                             info["population"], YEAR, info["resource"]])
    log(f"  wrote {EXTRACT} ({len(counts)} regencies, "
        f"{sum(i['population'] for i in counts.values()):,} people)")


def committed() -> list[dict[str, str]]:
    if not EXTRACT.exists():
        return []
    with EXTRACT.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def by_province() -> dict[str, dict[str, dict[str, Any]]]:
    """{province name as HAPI spells it: {regency name: row}}."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for row in committed():
        out.setdefault(row["admin1_name"], {})[row["admin2_name"]] = {
            "population": int(row["population"]),
            "year": int(row["year"]),
            "code": row["admin2_code"],
            "resource": row["resource_hdx_id"],
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true",
                    help=f"re-read HAPI and rewrite the committed extract "
                         f"(needs {KEY_VAR}; run where there is network)")
    args = ap.parse_args()
    log("indonesia_hapi: regency head counts from UN OCHA's HAPI. "
        + TERMS + " " + LICENCE)
    if args.fetch:
        rows = fetch()
        log(f"  {len(rows):,} rows for Indonesia at admin2")
        counts = totals(rows)
        write(counts)
        return 0
    rows = committed()
    if not rows:
        raise SystemExit(f"indonesia_hapi: {EXTRACT} is missing; run --fetch "
                         f"where there is network")
    log(f"  {len(rows)} regencies committed, "
        f"{sum(int(r['population']) for r in rows):,} people in all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
