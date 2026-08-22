#!/usr/bin/env python3
"""Australia -- ABS Data API (SDMX-JSON), 2021 Census, states and SA3/LGA.

The ABS Data API serves census tables as SDMX-JSON dataflows.  This pulls:

* ``C21_G14_LGA`` religious affiliation
* ``C21_G08_LGA`` ancestry (multi-response: people may report two ancestries,
  so shares sum above 100% and are labelled as responses, not persons)
* ``C21_G01_LGA`` selected person characteristics (population, median age)

Australia has no ethnicity question. It asks *ancestry* plus country of birth,
and separately Aboriginal and Torres Strait Islander status; the app keeps those
as distinct fields rather than folding them into an "ethnicity" bucket.
Religion is a voluntary question ("not stated" is its own category).

Usage:
    python -m scripts.fetch_census.abs --level state
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import (
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, gap, http_get, log, measure,
    record, shares, write_json,
)

API = "https://data.api.abs.gov.au/rest/data/ABS,{dataflow},1.0.0/{key}"
REGION_TYPE = {"state": "STE", "lga": "LGA", "sa3": "SA3"}
DATAFLOWS = {"religion": "C21_G14_{r}", "ancestry": "C21_G08_{r}", "profile": "C21_G01_{r}"}


def sdmx(dataflow: str, key: str = "all") -> dict[str, Any]:
    url = API.format(dataflow=dataflow, key=key) + "?format=jsondata&detail=full"
    import json as _json
    return _json.loads(http_get(url, timeout=300,
                                headers={"Accept": "application/vnd.sdmx.data+json"}))


def unpack(payload: dict[str, Any]) -> list[tuple[dict[str, str], float]]:
    """SDMX-JSON series -> [(dimension label map, observation value)]."""
    data = payload["data"]["dataSets"][0]
    struct = payload["data"]["structure"]["dimensions"]
    series_dims = struct.get("series", [])
    obs_dims = struct.get("observation", [])
    out: list[tuple[dict[str, str], float]] = []
    for series_key, series in data.get("series", {}).items():
        idx = [int(i) for i in series_key.split(":")]
        labels = {dim["id"]: dim["values"][i]["name"]
                  for dim, i in zip(series_dims, idx)}
        codes = {dim["id"] + "_CODE": dim["values"][i]["id"]
                 for dim, i in zip(series_dims, idx)}
        labels.update(codes)
        for obs_key, obs in series.get("observations", {}).items():
            if obs and obs[0] is not None:
                entry = dict(labels)
                for dim, i in zip(obs_dims, [int(x) for x in obs_key.split(":")]):
                    entry[dim["id"]] = dim["values"][i]["name"]
                out.append((entry, float(obs[0])))
    return out


def group_by_region(rows: list[tuple[dict[str, str], float]], label_dim: str,
                    region_dim: str = "REGION") -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for labels, value in rows:
        region = labels.get(region_dim + "_CODE") or labels.get(region_dim)
        label = labels.get(label_dim)
        if not region or not label:
            continue
        out.setdefault(region, {})[label] = out.setdefault(region, {}).get(label, 0.0) + value
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="state", choices=list(REGION_TYPE))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    suffix = REGION_TYPE[args.level]
    log(f"abs: 2021 Census, {suffix}")
    religion_rows = unpack(sdmx(DATAFLOWS["religion"].format(r=suffix)))
    ancestry_rows = unpack(sdmx(DATAFLOWS["ancestry"].format(r=suffix)))

    religion = group_by_region(religion_rows, "RELIGION")
    ancestry = group_by_region(ancestry_rows, "ANCP")
    names = {}
    for labels, _ in religion_rows + ancestry_rows:
        code = labels.get("REGION_CODE")
        if code:
            names.setdefault(code, labels.get("REGION", code))

    src = "Australian Bureau of Statistics, Census of Population and Housing 2021"
    records: list[dict[str, Any]] = []
    for code in sorted(set(religion) | set(ancestry)):
        rel = {k: v for k, v in religion.get(code, {}).items() if not k.lower().startswith("total")}
        anc = {k: v for k, v in ancestry.get(code, {}).items() if not k.lower().startswith("total")}
        records.append(record(
            f"AUS-{code}", names.get(code, code),
            level="admin1" if args.level == "state" else "admin2",
            parent="AUS", codes={"asgs": code, "asgs_level": suffix},
            religion=shares(rel) or gap(NOT_AVAILABLE),
            religion_note="ABS 2021 religious affiliation; the question is voluntary and "
                          "'not stated' is retained as its own category.",
            ancestry=shares(anc) or gap(NOT_AVAILABLE),
            ancestry_note="ABS ancestry is multi-response (up to two per person), so shares "
                          "are of responses and sum above 100%.",
            ethnicity=gap(NOT_COLLECTED,
                          "Australia's census does not ask ethnicity. It asks ancestry and "
                          "country of birth, plus a separate Aboriginal and Torres Strait "
                          "Islander status question."),
            sources=[{"field": "religion/ancestry", "name": src,
                      "url": API.format(dataflow=DATAFLOWS["religion"].format(r=suffix), key="all"),
                      "license": "CC BY 4.0"}],
        ))
    write_json(args.out or PROCESSED / f"australia_{args.level}.json", records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
