#!/usr/bin/env python3
"""Small helpers the East Asian readers share: the drawn units, ages, shares.

Nothing here fetches anything. Each reader of China, Taiwan, Japan, the two
Koreas and Mongolia binds its office's rows to the boundary file's polygons by
shape id, computes a median age from the office's own age table and a sex
ratio from its own counts, and writes a composition as shares that add to
exactly 100; the arithmetic is the same for all of them and lives here once.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ._shared import measure

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site" / "data"


def drawn(iso3: str, level: str) -> list[dict[str, Any]]:
    """The units the map draws for ``iso3`` at ``level``, under the boundary
    file's own labels (``common.as_drawn``): the build renames a polygon to
    the name of the row bound to it, and a reader that matched the renamed
    label would move the ground under itself on every rebuild."""
    path = SITE / level / f"{iso3}.units.json"
    units = json.loads(path.read_text(encoding="utf-8"))
    return [{**u, "name": u["shape_name"]} if u.get("shape_name") else u for u in units]


def single_year_median(ages: dict[int, float]) -> float | None:
    """The age half the people are younger than, interpolated within its single
    year of age. ``ages`` maps each year (the last one may be an open top class,
    which must not hold the median) to people."""
    total = sum(ages.values())
    if total <= 0:
        return None
    half, before = total / 2, 0.0
    keys = sorted(ages)
    for i, age in enumerate(keys):
        n = ages[age]
        if n > 0 and before + n >= half:
            if i == len(keys) - 1 and len(keys) > 1:
                raise SystemExit("the median falls in the open top age class")
            return round(age + (half - before) / n, 1)
        before += n
    return None


def grouped_median(groups: Iterable[tuple[float, float | None, float]]) -> float | None:
    """The median age interpolated within the age group that holds it.

    ``groups`` is (lower bound, width in years, people); the open top group has
    width None and must not hold the median. Used only where the office
    publishes nothing finer than groups, and the note says so.
    """
    rows = sorted(groups)
    total = sum(n for _, _, n in rows)
    if total <= 0:
        return None
    half, before = total / 2, 0.0
    for lower, width, n in rows:
        if n > 0 and before + n >= half:
            if width is None:
                raise SystemExit("the median falls in the open top age group")
            return round(lower + width * (half - before) / n, 1)
        before += n
    return None


def sex_ratio(men: float, women: float, *, year: int, source: str,
              **extra: Any) -> dict[str, Any] | None:
    """Males per 100 females, to one decimal."""
    if not women or not men:
        return None
    return measure(round(100 * men / women, 1), unit="males_per_100_females",
                   year=year, source=source, **extra)


def pool_small(counts: dict[str, float], residual: str) -> tuple[dict[str, float], list[str], int]:
    """The groups as ``hundred`` shows them, every one too small to show at one
    decimal added to ``residual`` rather than dropped: (counts, the groups
    pooled, how many people they are). Only a group under 0.1% can fail to
    show, and pooling one can move the rounding of another, so it repeats
    until every group left but the residual shows. The residual itself can
    still be too small to show; ``unshown`` says how many people that leaves
    out, for the note."""
    counts = {g: v for g, v in counts.items() if v}
    moved: list[str] = []
    people = 0.0
    while True:
        shown = {row["group"] for row in hundred(counts)}
        small = [g for g in counts if g != residual and g not in shown]
        if not small:
            return counts, moved, int(round(people))
        for group in small:
            value = counts.pop(group)
            counts[residual] = counts.get(residual, 0) + value
            people += value
            moved.append(group)


def unshown(counts: dict[str, float]) -> int:
    """People in ``counts`` whom ``hundred`` does not show (groups rounding to
    0.0)."""
    return int(round(sum(v for v in counts.values() if v and v > 0)
                     - sum(r["count"] for r in hundred(counts))))


def hundred(counts: dict[str, float], *, keep_counts: bool = True) -> list[dict[str, Any]]:
    """Counts to shares of one decimal that add to exactly 100.0, by largest
    remainder; largest first, the name breaking a tie. A group that rounds to
    0.0 is dropped: a bar of nothing asserts a precision no one asked for, and
    the shares left still add to 100.0."""
    total = sum(v for v in counts.values() if v and v > 0)
    if total <= 0:
        return []
    items = [(g, v, v / total * 1000) for g, v in counts.items() if v and v > 0]
    floors = [int(t) for _, _, t in items]
    order = sorted(range(len(items)), key=lambda i: (-(items[i][2] - floors[i]), items[i][0]))
    for i in order[:1000 - sum(floors)]:
        floors[i] += 1
    out = []
    for i, (group, value, _) in enumerate(items):
        row: dict[str, Any] = {"group": group, "pct": floors[i] / 10}
        if keep_counts:
            row["count"] = int(round(value))
        out.append(row)
    out = [r for r in out if r["pct"] > 0]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out
