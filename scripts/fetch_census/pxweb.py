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
                 note: str = "", drop: tuple[str, ...] = ()):
        self.path = path
        self.field = field
        self.geo = geo
        self.group = group
        self.keep = keep or {}
        self.year = year
        self.note = note
        self.drop = drop


# Filled in from what scripts/probe_pxweb.py actually found. An office is only
# listed here once its tables have been seen to exist, be public, and break
# down by a geography the boundary files can join -- which is why this is empty:
# the discovery runs have not yet come back with a table to point it at. Until
# one does, nothing here is wired into build_all.sh, because an adapter that
# guesses a table code fails at fetch time rather than at review time.
INSTANCES: dict[str, dict[str, Any]] = {}


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
