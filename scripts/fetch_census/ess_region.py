#!/usr/bin/env python3
"""European Social Survey: religion and home language by region (discovery stage).

Reads the ESS Data Portal's own open tabulation service -- the GraphQL
endpoint behind the portal's variable viewer -- and never the microdata.

Usage:
    python -m scripts.fetch_census.ess_region --discover FR,ES,SE
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from ._shared import log
from common import USER_AGENT  # noqa: E402  (on the path through _shared)

API = "https://api.nsd.no/graphql"
SERIES = "321b06ad-1b98-4b7d-93ad-ca8a24e8788a"
AGENCY = "INT_ESSERIC"

TABULATE = """query($input: FrequencyTabulationInput!) { analysis {
  frequencyTabulation(input: $input) {
    variableValues { name values codeList { value label isMissing } }
    table { path count } } } }"""

STUDIES = """query($id: ID!) { search {
  seriesMetadata(id: $id, instance: PUBLISHED, agencyId: INT_ESSERIC) {
    title { en }
    studies { id version title { en }
      mainDataFiles { id version label { en } defaultWeight { name { en } } } } } } }"""


def gql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST one query; a GraphQL error stops the run with the server's message."""
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "User-Agent": USER_AGENT, "Content-Type": "application/json",
        "Accept": "application/json"})
    for wait in (5, 20, 60, None):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if wait is None:
                raise SystemExit(f"ess_region: {API} unreachable: {exc}")
            log(f"  retrying after {exc} in {wait}s")
            time.sleep(wait)
    if payload.get("errors"):
        raise SystemExit(f"ess_region: the portal refused a query: "
                         f"{json.dumps(payload['errors'])[:600]}")
    return payload["data"]


def tabulate(datafile: dict[str, Any], variables: list[str],
             weight: str | None) -> tuple[list[dict[str, Any]], dict[tuple[str, ...], float]]:
    """The portal's crosstab of ``variables``: their code lists and the cells by code."""
    data = gql(TABULATE, {"input": {
        "datafile": {"id": datafile["id"], "version": datafile["version"]},
        "instance": "PUBLISHED", "agencyId": AGENCY, "breakVariables": variables,
        "weightVariable": weight, "includeMissing": True, "includeEmpty": False,
        "metadataLanguage": "en"}})
    tab = data["analysis"]["frequencyTabulation"]
    values = [v["values"] for v in tab["variableValues"]]
    cells: dict[tuple[str, ...], float] = {}
    for cell in tab["table"]:
        if cell["count"]:
            key = tuple(values[i][j] for i, j in enumerate(cell["path"]))
            cells[key] = cells.get(key, 0) + cell["count"]
    return tab["variableValues"], cells


def studies() -> list[dict[str, Any]]:
    data = gql(STUDIES, {"id": SERIES})
    return data["search"]["seriesMetadata"]["studies"]


def discover(countries: list[str]) -> None:
    for study in studies():
        title = study["title"]["en"]
        for df in study.get("mainDataFiles") or []:
            weight = (df.get("defaultWeight") or {}).get("name", {}).get("en")
            log(f"== {title} :: {df['label']['en']} id={df['id']} v={df['version']} weight={weight}")
            for probe in (["cntry", "region"], ["cntry", "lnghom1"], ["cntry", "rlgdnm"]):
                try:
                    codes, cells = tabulate(df, probe, None)
                except SystemExit as exc:
                    log(f"   {probe[1]}: {str(exc)[:160]}")
                    continue
                labels = {c["value"]: c["label"] or "" for c in codes[1]["codeList"] or []}
                for cc in countries:
                    row = sorted(((k[1], v) for k, v in cells.items() if k[0] == cc),
                                 key=lambda kv: -kv[1])
                    if not row:
                        continue
                    shown = " ".join(f"{k}={labels.get(k, '?')[:22]}:{int(v)}"
                                     for k, v in row[:40])
                    log(f"   {probe[1]} {cc} n={int(sum(v for _, v in row))}: {shown}")
            # A weighted count: is it rounded, and on what scale?
            try:
                _, cells = tabulate(df, ["cntry"], weight)
                log(f"   weighted by {weight}: " + " ".join(
                    f"{k[0]}={v}" for k, v in sorted(cells.items())[:6]))
            except SystemExit as exc:
                log(f"   weighted: {str(exc)[:160]}")


VARIABLES = """query($id: ID!, $version: Int) { search {
  dataFileMetadata(id: $id, version: $version, agencyId: INT_ESSERIC, instance: PUBLISHED) {
    label { en } disseminationLimitation defaultWeight { name { en } }
    variables { name { en } label { en } hasCodes } } } }"""


def main_files() -> dict[str, dict[str, Any]]:
    """{label: datafile} for every round's main files, e.g. 'ESS11e04_2'."""
    return {df["label"]["en"]: df for study in studies()
            for df in study.get("mainDataFiles") or []}


def pick(files: dict[str, dict[str, Any]], prefix: str) -> dict[str, Any]:
    hits = [df for label, df in files.items() if label.startswith(prefix + "e")]
    if len(hits) != 1:
        raise SystemExit(f"ess_region: {prefix!r} names {len(hits)} datafiles: {sorted(files)}")
    return hits[0]


def show_variables(prefix: str, pattern: str) -> None:
    import re
    df = pick(main_files(), prefix)
    meta = gql(VARIABLES, {"id": df["id"], "version": df["version"]})["search"]["dataFileMetadata"]
    log(f"== {meta['label']['en']} limitation={meta.get('disseminationLimitation')} "
        f"weight={meta.get('defaultWeight')} variables={len(meta['variables'])}")
    rx = re.compile(pattern, re.I)
    for var in meta["variables"]:
        name, label = var["name"]["en"], (var.get("label") or {}).get("en") or ""
        if rx.search(name) or rx.search(label):
            log(f"   {name}: {label[:100]} codes={var.get('hasCodes')}")


def show_tab(prefix: str, variables: str, weight: str | None, limit: int) -> None:
    df = pick(main_files(), prefix)
    codes, cells = tabulate(df, variables.split(","), weight)
    for var in codes:
        log(f"   {var['name']}: {len(var['values'])} values; first "
            + " ".join(f"{c['value']}={c['label']}" for c in (var['codeList'] or [])[:12]))
    for key, count in sorted(cells.items())[:limit]:
        log(f"   {' '.join(key)} {count}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--discover", default=None,
                    help="comma-separated ESS country codes: list rounds and their codes")
    ap.add_argument("--variables", nargs=2, metavar=("ROUND", "REGEX"),
                    help="list a round's variables whose name or label matches, e.g. ESS11 region")
    ap.add_argument("--tab", nargs="+", metavar="ARG",
                    help="ROUND VAR1,VAR2 [WEIGHT [LIMIT]]: print a tabulation's cells")
    args = ap.parse_args()
    if args.variables:
        show_variables(*args.variables)
        return 0
    if args.tab:
        weight = args.tab[2] if len(args.tab) > 2 and args.tab[2] != "-" else None
        limit = int(args.tab[3]) if len(args.tab) > 3 else 60
        show_tab(args.tab[0], args.tab[1], weight, limit)
        return 0
    if args.discover:
        discover(args.discover.split(","))
        return 0
    raise SystemExit("ess_region: nothing to do yet")


if __name__ == "__main__":
    sys.exit(main())
