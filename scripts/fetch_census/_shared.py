"""Helpers shared by the national statistical-office adapters."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import (  # noqa: F401,E402
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, RAW, gap, http_get, http_json,
    log, measure, read_json, write_json,
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
