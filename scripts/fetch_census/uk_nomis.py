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
    python -m scripts.fetch_census.uk_nomis --geography TYPE154
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geography", default=DEFAULT_GEOGRAPHY,
                    help="Nomis geography type (TYPE154 = 2021 local authorities)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    tables: dict[str, dict[str, dict[str, Any]]] = {}
    for field, (dataset, label, cell) in DATASETS.items():
        log(f"uk_nomis: {label} ({dataset})")
        tables[field] = fetch_table(dataset, cell, args.geography)

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
    write_json(args.out or PROCESSED / "uk_lad.json", records)
    log(f"  {len(records)} local authority records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
