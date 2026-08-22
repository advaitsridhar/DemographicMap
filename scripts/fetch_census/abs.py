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

API = "https://data.api.abs.gov.au/rest/data/{agency},{dataflow},{version}/{key}"
CATALOGUE = "https://data.api.abs.gov.au/rest/dataflow/ABS?detail=allstubs"
REGION_TYPE = {"state": "STE", "lga": "LGA", "sa3": "SA3"}
# Census 2021 table numbers: G14 religious affiliation, G08 ancestry.
DATAFLOW_HINTS = {"religion": "C21_G14_{r}", "ancestry": "C21_G08_{r}"}


def discover_dataflows(region: str) -> dict[str, tuple[str, str, str]]:
    """Resolve field -> (agency, dataflow id, version) from the live catalogue.

    The exact 2021-census dataflow ids were guessed once and 404ed, so instead
    of hardcoding them, list every dataflow the ABS publishes and pick the ones
    whose id matches the census table number and region suffix.
    """
    import re as _re
    xml = http_get(CATALOGUE, timeout=300,
                   headers={"Accept": "application/vnd.sdmx.structure+xml;version=2.1"})
    assert isinstance(xml, str)
    flows = _re.findall(
        r'<(?:str|structure):Dataflow[^>]*\bid="([^"]+)"[^>]*\bagencyID="([^"]+)"'
        r'[^>]*\bversion="([^"]+)"', xml)
    if not flows:  # attribute order is not guaranteed in XML
        flows = [(m.group("id"), m.group("agency"), m.group("version"))
                 for m in _re.finditer(
                     r'<[^>]*Dataflow(?=[^>]*\bid="(?P<id>[^"]+)")'
                     r'(?=[^>]*\bagencyID="(?P<agency>[^"]+)")'
                     r'(?=[^>]*\bversion="(?P<version>[^"]+)")[^>]*>', xml)]
    log(f"  {len(flows)} dataflows in the ABS catalogue")
    # When nothing matches, the census-looking ids are the diagnosis: print
    # them so a failed CI run documents the real naming scheme.
    # The G14/G08 sets are small; print them completely -- run 3's broad sample
    # was drowned in sixty CENSUS2011_B* ids before reaching the C21 block.
    for table in ("G14", "G08"):
        ids = sorted(f[0] for f in flows if table in f[0].upper())
        if ids:
            log(f"  dataflows containing {table}: " + ", ".join(ids[:40]))

    out: dict[str, tuple[str, str, str]] = {}
    table_of = {"religion": "G14", "ancestry": "G08"}
    for field, pattern in DATAFLOW_HINTS.items():
        wanted = pattern.format(r=region).upper()
        table = table_of[field]
        exact = [f for f in flows if f[0].upper() == wanted]
        # Same census table, right region.
        regional = [f for f in flows
                    if table in f[0].upper() and region in f[0].upper()]
        # Same census table at all: better one dataflow filtered by region
        # dimension at query time than nothing.
        any_region = [f for f in flows if table in f[0].upper()]
        chosen = (exact or regional or sorted(any_region, key=lambda f: len(f[0])) or [None])[0]
        if chosen:
            out[field] = (chosen[1], chosen[0], chosen[2])
            log(f"  {field}: dataflow {chosen[1]},{chosen[0]},{chosen[2]}")
        else:
            log(f"  {field}: nothing in the catalogue mentions table {table}")
    return out


def sdmx(flow: tuple[str, str, str], key: str = "all") -> dict[str, Any]:
    agency, dataflow, version = flow
    url = (API.format(agency=agency, dataflow=dataflow, version=version, key=key)
           + "?format=jsondata&detail=full")
    import json as _json
    return _json.loads(http_get(url, timeout=300,
                                headers={"Accept": "application/vnd.sdmx.data+json"}))


def unpack(payload: dict[str, Any]) -> list[tuple[dict[str, str], float]]:
    """SDMX-JSON series -> [(dimension label map, observation value)].

    Handles both wire formats the ABS serves: SDMX-JSON 1.0 puts a singular
    ``structure`` beside ``dataSets``; 2.0 puts a ``structures`` list there
    (the live API answered with the latter -- KeyError 'structure' in run 3).
    """
    body = payload["data"]
    data = body["dataSets"][0]
    struct_node = body.get("structure")
    if struct_node is None:
        candidates = body.get("structures") or payload.get("structures") or []
        struct_node = candidates[0] if candidates else {}
    struct = struct_node["dimensions"]
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
    flows = discover_dataflows(suffix)
    if not flows:
        log("  no matching dataflows; nothing to fetch")
        return 1
    religion_rows = unpack(sdmx(flows["religion"])) if "religion" in flows else []
    ancestry_rows = unpack(sdmx(flows["ancestry"])) if "ancestry" in flows else []

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
                      "url": "https://data.api.abs.gov.au/",
                      "license": "CC BY 4.0"}],
        ))
    write_json(args.out or PROCESSED / f"australia_{args.level}.json", records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
