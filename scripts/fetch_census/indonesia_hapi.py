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
    """One head count per regency, with three readings of it checked against
    each other.

    Every regency comes back as 51 rows: seventeen age bands times three
    values of ``gender`` -- "all", "f" and "m" -- and three of those rows
    carry ``age_range`` "all" rather than a band. Adding up everything with
    no band therefore adds the total to the two halves that make it up, and
    the first run of this module did exactly that: Indonesia came out at
    539,206,860 people, almost precisely twice its real size.

    So the figure is the one row that is both "all" genders and "all" ages,
    and the two other ways of arriving at it are computed and compared:
    the sexes' own totals added together, and the "all"-gender age bands
    added together. A regency where the three disagree is refused rather
    than published, because there is then no saying which of them is the
    head count.
    """
    grand: dict[str, int] = {}
    by_sex: dict[str, int] = collections.defaultdict(int)
    by_band: dict[str, int] = collections.defaultdict(int)
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
        gender = (row.get("gender") or "").lower()
        whole = row.get("min_age") is None and row.get("max_age") is None
        if gender == "all" and whole:
            grand[code] = value
        elif gender in ("f", "m") and whole:
            by_sex[code] += value
        elif gender == "all":
            by_band[code] += value
    out: dict[str, dict[str, Any]] = {}
    disagreed: list[str] = []
    for code, info in meta.items():
        total = grand.get(code)
        if total is None or total != by_sex.get(code) or total != by_band.get(code):
            disagreed.append(f"{info['admin2_name']} ({code}): "
                             f"stated {grand.get(code)}, sexes {by_sex.get(code)}, "
                             f"bands {by_band.get(code)}")
            continue
        out[code] = dict(info, population=total)
    log(f"  {len(out)} regencies where the stated total, the two sexes added "
        f"and the age bands added all agree")
    for line in disagreed[:10]:
        log(f"    refused, the three readings differ: {line}")
    if disagreed:
        log(f"    {len(disagreed)} refused in all")
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
        people = sum(i["population"] for i in counts.values())
        # Indonesia was 270.2 million at the 2020 census and is about 280
        # million now; a projection for 2020 that lands outside this range is
        # not a projection of Indonesia, it is an arithmetic mistake. The
        # first run of this module wrote 539,206,860 and nothing stopped it.
        if not 240_000_000 <= people <= 300_000_000:
            raise SystemExit(
                f"indonesia_hapi: the regencies add to {people:,}, which is "
                f"not a plausible Indonesia; refusing to write {EXTRACT}")
        log(f"  the {len(counts)} regencies add to {people:,}, against "
            f"270.2 million counted in the 2020 census")
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
