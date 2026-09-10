"""Helpers shared by the national statistical-office adapters."""

from __future__ import annotations

import sys
from pathlib import Path
from collections.abc import Iterable
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import (  # noqa: F401,E402
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, RAW, download, gap, http_get,
    http_json, log, measure, read_json, write_json,
)


def shares(counts: dict[str, float], *, total: float | None = None,
           min_pct: float = 0.0) -> list[dict[str, Any]]:
    """Counts -> percentage shares, largest first, rounded to 1 decimal."""
    total = total if total else sum(v for v in counts.values() if v)
    if not total:
        return []
    out = [{"group": k, "pct": round(100.0 * v / total, 1), "count": int(v)}
           for k, v in counts.items() if v is not None]
    out = [row for row in out if row["pct"] >= min_pct]
    out.sort(key=lambda r: r["pct"], reverse=True)
    return out


def leaves(labels: Iterable[str]) -> list[str]:
    """The labels that partition a population exactly once.

    Several offices publish a composition at two levels in one table -- a
    handful of broad groups, and beneath each the detail it is made of, both
    summing to the same population. Read whole, that counts everyone twice:
    Bradford's ethnicity came out at 199.9%, "White" 61.1% sitting beside
    "White: English, Welsh, Scottish, Northern Irish or British" 56.7%, which
    are the same people.

    The detail is the better answer -- "White" alone says nothing about the
    split between English, Irish, Roma and Gypsy or Irish Traveller -- so this
    keeps a group's detail where it has any and the group itself where it has
    none. A parent is recognised by being the part of some other label before
    its colon, which is how ONS, NRS and NISRA all write the nesting.
    """
    labels = list(labels)
    parents = {label.split(":")[0].strip() for label in labels if ":" in label}
    return [label for label in labels if label.strip() not in parents]


def record(entity_id: str, name: str, *, level: str, parent: str,
           **fields: Any) -> dict[str, Any]:
    base = {
        "id": entity_id, "level": level, "name": name, "parent": parent,
        "capital": gap(NOT_AVAILABLE),
        "largest_settlement": gap(NOT_AVAILABLE),
        "population": gap(NOT_AVAILABLE),
        "median_age": gap(NOT_AVAILABLE),
        "sex_ratio": gap(NOT_AVAILABLE),
        "religion": gap(NOT_AVAILABLE),
        "language": gap(NOT_AVAILABLE),
        "ethnicity": gap(NOT_AVAILABLE),
        "sources": [],
    }
    base.update({k: v for k, v in fields.items() if v is not None})
    return base
