#!/usr/bin/env python3
"""United Kingdom -- ONS Census 2021 via the Nomis API (local authorities).

Nomis serves the 2021 census topic summaries as machine-readable datasets:

* ``NM_2041_1`` = TS021 Ethnic group
* ``NM_2049_1`` = TS030 Religion
* ``NM_2020_1`` = TS007A Age by five-year band (used for median age)

Coverage caveat that the app displays: the 2021 census covers England and
Wales.  Scotland ran its census in **2022** (National Records of Scotland) and
Northern Ireland in 2021 through NISRA, so UK-wide comparisons mix reference
dates.  Religion is a *voluntary* question in England and Wales -- about 6% of
people left it blank -- so shares are of all usual residents including
non-responders, matching the ONS's own published percentages.

Usage:
    python -m scripts.fetch_census.uk_nomis --level district
    python -m scripts.fetch_census.uk_nomis --level county
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, http_json, log, measure, record, shares, write_json,
)

BASE = "https://www.nomisweb.co.uk/api/v01/dataset"
DATASETS = {
    "ethnicity": ("NM_2041_1", "TS021 Ethnic group", "c2021_eth_20"),
    "religion": ("NM_2049_1", "TS030 Religion", "c2021_religion_10"),
}
# TYPE154 = 2021 local authority districts; TYPE499 = regions; TYPE480 = countries.
DEFAULT_GEOGRAPHY = "TYPE154"

# Two geographies, because one is not enough to cover the shapes that exist.
#
# Nomis publishes the census for districts (TYPE154) and for counties
# (TYPE155), and geoBoundaries' UK ADM2 needs both: it draws unitary
# authorities, metropolitan and London boroughs, Scottish councils and Northern
# Irish districts -- but for shire England it draws the *county*. Read at
# districts alone, 150 of 331 rows are ONS "E07" codes with no shape of their
# own, while the counties above them have a shape and no row.
#
# Asked for rather than summed. Ukraine's oblasts are built by adding up
# rayons because nothing else was published; here the county figures are
# published, by the same office, from the same census, and a total that was
# counted beats one that was reconstructed.
LEVELS: dict[str, tuple[str, str]] = {
    "district": ("TYPE154", "uk_lad.json"),
    "county": ("TYPE155", "uk_county.json"),
}


def fetch_table(dataset: str, cell: str, geography: str) -> dict[str, dict[str, Any]]:
    # No `select=`: that parameter switches Nomis to a flat column format and
    # empties the nested "obs" list this parser reads.  Leaving the category
    # dimension unspecified returns every category, totals included, which is
    # exactly what shares() needs.
    url = f"{BASE}/{dataset}.data.json?geography={geography}&measures=20100"
    payload = http_json(url, timeout=300)
    out: dict[str, dict[str, Any]] = {}
    for obs in payload.get("obs", []):
        code = obs["geography"]["geogcode"]
        name = obs["geography"]["description"]
        label = obs[cell]["description"]
        value = obs.get("obs_value", {}).get("value")
        if value is None:
            continue
        entry = out.setdefault(code, {"name": name, "counts": {}, "total": None})
        if label.lower().startswith("total"):
            entry["total"] = float(value)
        else:
            entry["counts"][label] = float(value)
    return out


def list_datasets(match: str) -> int:
    """Every dataset Nomis serves, filtered by name.

    Nomis is run for the ONS but is not only the ONS: it is the UK's shared
    labour-market and census warehouse, and which offices' tables reach it is
    not something the ONS pages say. That matters because the 45 UK shapes this
    map cannot fill are Scottish council areas and Northern Irish districts,
    whose censuses were run by NRS and NISRA -- and their own portals answer a
    JavaScript shell to a program, with the PxStat and SPARQL endpoints their
    platforms usually expose returning 404 or closing the connection.

    So before crawling two more sites, ask the warehouse this project already
    talks to whether it has them. One call lists everything it serves.
    """
    url = f"{BASE}/def.sdmx.json"
    log(f"uk_nomis: datasets matching {match!r}")
    try:
        payload = http_json(url, timeout=180)
    except Exception as err:                        # noqa: BLE001 -- reported
        log(f"  {type(err).__name__}: {err}")
        return 1
    lists = (payload.get("structure", {}).get("keyfamilies", {})
             .get("keyfamily", []))
    needle = match.lower()
    shown = 0
    for family in lists:
        name = ((family.get("name") or [{}])[0] or {}).get("value", "") \
            if isinstance(family.get("name"), list) else \
            (family.get("name") or {}).get("value", "")
        if needle and needle not in name.lower():
            continue
        log(f"  {str(family.get('id','?')):<14} {name[:120]}")
        shown += 1
    log(f"  {shown} of {len(lists)} datasets matched")
    return 0


def list_geographies() -> int:
    """Which geographies Nomis publishes TS030 for.

    150 of the 331 rows this adapter writes reach no shape, and every one of
    them is an ONS "E07" -- a non-metropolitan district sitting inside a
    county. geoBoundaries' UK ADM2 is a mixed geography: unitary authorities,
    metropolitan and London boroughs, Scottish councils and Northern Irish
    districts, but for shire England the *county*, not the districts below it.
    So those 150 rows have no shape of their own and their county has no row.

    Ukraine's oblasts were built by summing rayons and that is one way out.
    Asking Nomis for the county geography instead is a better one, if it has
    it: the same table, the geography the boundary file actually draws, and no
    figure reconstructed from parts. Whether it has it is not guessable -- the
    file names TYPE154, TYPE499 and TYPE480 and says nothing about counties --
    so this asks.
    """
    url = (f"{BASE}/{DATASETS['religion'][0]}/geography/"
           f"TYPE.def.sdmx.json")
    log(f"uk_nomis: geography types for {DATASETS['religion'][0]}")
    try:
        payload = http_json(url, timeout=120)
    except Exception as err:                        # noqa: BLE001 -- reported
        log(f"  {type(err).__name__}: {err}")
        return 1
    codes = (payload.get("structure", {}).get("codelists", {})
             .get("codelist", []))
    shown = 0
    for codelist in codes:
        for code in codelist.get("code", []):
            name = (code.get("description", {}) or {}).get("value", "")
            log(f"  {str(code.get('value','?')):<12} {name}")
            shown += 1
    if not shown:
        log(f"  nothing listed; raw: {str(payload)[:400]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="district", choices=list(LEVELS),
                    help="district (TYPE154) or county (TYPE155)")
    ap.add_argument("--geography", default=None,
                    help="a Nomis geography type, overriding --level")
    ap.add_argument("--datasets", default=None, metavar="TEXT",
                    help="list Nomis datasets whose name contains TEXT, and stop")
    ap.add_argument("--geographies", action="store_true",
                    help="list the geography types this dataset is published "
                         "for, and stop")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    tables: dict[str, dict[str, dict[str, Any]]] = {}
    if args.datasets is not None:
        return list_datasets(args.datasets)
    if args.geographies:
        return list_geographies()

    geography, filename = LEVELS[args.level]
    geography = args.geography or geography
    log(f"uk_nomis: {args.level} ({geography})")
    for field, (dataset, label, cell) in DATASETS.items():
        log(f"uk_nomis: {label} ({dataset})")
        tables[field] = fetch_table(dataset, cell, geography)

    codes = sorted(set().union(*(set(t) for t in tables.values())) if tables else set())
    src = "ONS Census 2021 (England and Wales) via Nomis"
    records: list[dict[str, Any]] = []
    for code in codes:
        eth = tables["ethnicity"].get(code, {})
        rel = tables["religion"].get(code, {})
        name = eth.get("name") or rel.get("name") or code
        total = eth.get("total") or rel.get("total")
        records.append(record(
            f"GBR-{code}", name, level="admin2", parent="GBR",
            codes={"ons_code": code},
            population=measure(int(total), year=2021, source=src) if total else gap(NOT_AVAILABLE),
            ethnicity=shares(eth.get("counts", {}), total=eth.get("total")) or gap(NOT_AVAILABLE),
            ethnicity_note="ONS 2021 ethnic group classification (TS021), England and Wales.",
            religion=shares(rel.get("counts", {}), total=rel.get("total")) or gap(NOT_AVAILABLE),
            religion_note=("ONS 2021 religion question (TS030) is voluntary; 'Not answered' is "
                           "reported as its own category rather than excluded."),
            sources=[{"field": "ethnicity/religion", "name": src,
                      "url": f"{BASE}/{DATASETS['ethnicity'][0]}.data.json",
                      "license": "Open Government Licence v3.0"}],
        ))
    write_json(args.out or PROCESSED / filename, records)
    log(f"  {len(records)} records")
    log(f"  {len(records)} local authority records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
