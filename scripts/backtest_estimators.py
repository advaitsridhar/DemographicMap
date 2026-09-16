#!/usr/bin/env python3
"""Measure how wrong a modelled composition would be, on data we already have.

Nothing here writes to the map. This is the evidence a modelling methodology
stands on: every estimator is scored by hiding a unit's real composition,
predicting it from what is left, and comparing the prediction with what was
taken away. An estimator nobody has scored this way is a guess with a
confident tone.

Two things make the scores mean what they say.

*Canonical space.* The national row and the unit rows usually come from
different adapters with different vocabularies -- one says "Muslim", the other
"Islam"; one "Christian", the other "Christianity". Scored on raw labels those
read as total disagreement, and the median error for ethnicity comes out at
41% when the real figure is 10%. Every composition is therefore folded to its
tier-2 canonical group before anything is compared.

*Total variation distance.* Half the L1 distance between two compositions,
which is the share of the population the prediction puts in the wrong group.
It is reported alongside whether the prediction gets the *leading* group
right, because that is what the choropleth paints: an estimate can be 8% off
and still colour the unit correctly, or 20% off and colour it wrong, and only
the second is visible to a reader.

    python3 -m scripts.backtest_estimators            # all estimators
    python3 -m scripts.backtest_estimators --calibrate  # is error predictable?
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import sys
from typing import Any, Iterable

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import canonical_groups as cg  # noqa: E402
from common import NOT_COLLECTED  # noqa: E402

FIELDS = ("religion", "ethnicity", "language")
SITE = os.path.join(os.path.dirname(__file__), "..", "site", "data")

_TIER2: dict[tuple[str, str], str] = {}


def tier2(field: str, name: str) -> str:
    """The group's ancestor just below the root of its tree.

    Tier 1 is too coarse to score against -- it puts Islam and Christianity
    both under "Abrahamic religions", so every prediction would look right.
    Tier 2 is the level at which "Muslim" and "Islam" are the same answer and
    Islam and Christianity are different ones.
    """
    key = (field, name)
    if key not in _TIER2:
        trail = cg.ancestry(field, name)
        _TIER2[key] = trail[-2] if len(trail) >= 2 else trail[-1]
    return _TIER2[key]


def composition(rows: Iterable[Any], field: str, canonical: bool = True
                ) -> dict[str, float]:
    """A composition as group -> share, summing to 1. Empty if it cannot."""
    out: dict[str, float] = collections.defaultdict(float)
    for entry in rows:
        if isinstance(entry, dict) and entry.get("group") and entry.get("pct") is not None:
            group = tier2(field, entry["group"]) if canonical else entry["group"]
            out[group] += float(entry["pct"])
    total = sum(out.values())
    return {k: v / total for k, v in out.items()} if total > 0 else {}


def tvd(p: dict[str, float], q: dict[str, float]) -> float:
    """Total variation distance: the share of people put in the wrong group."""
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in set(p) | set(q))


def leader(shares: dict[str, float]) -> str | None:
    return max(shares, key=shares.get) if shares else None


def population(row: dict[str, Any]) -> float:
    value = row.get("population")
    value = value.get("value") if isinstance(value, dict) else value
    return float(value or 0)


def great_circle_km(a: Any, b: Any) -> float:
    if not (isinstance(a, list) and isinstance(b, list)):
        return math.inf
    dy = (a[1] - b[1]) * 111.0
    dx = (a[0] - b[0]) * 111.0 * math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot(dx, dy)


def mix(parts: list[tuple[dict[str, float], float]]) -> dict[str, float]:
    """A weighted blend of compositions, renormalised to sum to 1."""
    out: dict[str, float] = collections.defaultdict(float)
    total = sum(w for _, w in parts)
    for shares, weight in parts:
        weight = weight / total if total else 1 / max(len(parts), 1)
        for group, share in shares.items():
            out[group] += share * weight
    scale = sum(out.values())
    return {k: v / scale for k, v in out.items()} if scale > 0 else {}


def load() -> tuple[dict[str, dict], dict[str, list[dict]]]:
    countries = {c["id"]: c for c in json.load(open(f"{SITE}/admin0.json"))}
    units: dict[str, list[dict]] = collections.defaultdict(list)
    for name in sorted(os.listdir(f"{SITE}/admin1")):
        if name.endswith(".json"):
            for row in json.load(open(f"{SITE}/admin1/{name}")):
                if not row.get("disputed"):
                    units[row.get("country")].append(row)
    return countries, units


def predictions(row, truth_index, others, foreign, national):
    """Every estimator's answer for one held-out unit, by name."""
    out: dict[str, dict[str, float]] = {}
    if national:
        out["national prior"] = national
    if others:
        out["country mean (LOO)"] = mix([(v, population(o) or 1) for o, v in others])
        near = sorted(others, key=lambda ov: great_circle_km(row.get("point"),
                                                            ov[0].get("point")))
        if math.isfinite(great_circle_km(row.get("point"), near[0][0].get("point"))):
            out["nearest neighbour"] = near[0][1]
            out["3 nearest, IDW"] = mix(
                [(v, 1.0 / max(great_circle_km(row.get("point"), o.get("point")), 10.0))
                 for o, v in near[:3]])
    if foreign:
        near = sorted(foreign, key=lambda ov: great_circle_km(row.get("point"),
                                                             ov[0].get("point")))[:3]
        if math.isfinite(great_circle_km(row.get("point"), near[0][0].get("point"))):
            out["cross-border 3 IDW"] = mix(
                [(v, 1.0 / max(great_circle_km(row.get("point"), o.get("point")), 10.0))
                 for o, v in near])
    return {k: v for k, v in out.items() if v}


def score(canonical: bool = True, cross_border: bool = False):
    countries, units = load()
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for field in FIELDS:
        observed_all = [(r, composition(r[field], field, canonical))
                        for rows in units.values() for r in rows
                        if isinstance(r.get(field), list)]
        observed_all = [(r, v) for r, v in observed_all if v]
        for country, rows in units.items():
            seen = [(r, composition(r[field], field, canonical)) for r in rows
                    if isinstance(r.get(field), list)]
            seen = [(r, v) for r, v in seen if v]
            if len(seen) < 2:
                continue
            national_rows = countries.get(country, {}).get(field)
            national = (composition(national_rows, field, canonical)
                        if isinstance(national_rows, list) else None)
            foreign = ([(o, v) for o, v in observed_all if o.get("country") != country]
                       if cross_border else [])
            for i, (row, truth) in enumerate(seen):
                others = [pair for j, pair in enumerate(seen) if j != i]
                for name, guess in predictions(row, i, others, foreign, national).items():
                    out[field][name].append((tvd(truth, guess),
                                             leader(truth) == leader(guess)))
    return out


def report(results, title):
    print(f"\n=== {title}")
    print(f"{'field':<10} {'estimator':<22} {'n':>5} {'median':>8} {'p75':>7} "
          f"{'p90':>7} {'leading group right':>20}")
    for field in FIELDS:
        for name, rows in sorted(results[field].items(),
                                 key=lambda kv: -sum(x[1] for x in kv[1]) / len(kv[1])):
            errors = sorted(x[0] for x in rows)
            accuracy = sum(x[1] for x in rows) / len(rows)
            at = lambda f: errors[min(int(len(errors) * f), len(errors) - 1)]
            print(f"{field:<10} {name:<22} {len(errors):>5} {at(.5) * 100:>7.1f}% "
                  f"{at(.75) * 100:>6.1f}% {at(.9) * 100:>6.1f}% "
                  f"{accuracy * 100:>19.1f}%")


def reachability():
    """How many blank units the neighbour estimators can even see.

    The backtest only scores units that have a composition, and those sit in
    better-covered neighbourhoods than the blank ones by construction. This is
    the correction: for each field, the share of blank units with any observed
    unit in their own country.
    """
    _, units = load()
    print("\n=== Can the neighbour estimators reach the units we want to fill?")
    print(f"{'field':<10} {'set':<28} {'n':>6} {'has an in-country neighbour':>28}")
    for field in FIELDS:
        def state(r):
            v = r.get(field)
            return v.get("status") if isinstance(v, dict) else "observed"
        for label, keep in (("observed (the backtest set)",
                             lambda r: state(r) == "observed"),
                            ("blank and not refused",
                             lambda r: state(r) not in ("observed", NOT_COLLECTED))):
            total = reachable = 0
            for rows in units.values():
                seen = [r for r in rows if state(r) == "observed"]
                for row in rows:
                    if not keep(row):
                        continue
                    total += 1
                    if any(o is not row and math.isfinite(
                            great_circle_km(row.get("point"), o.get("point")))
                           for o in seen):
                        reachable += 1
            share = reachable / total * 100 if total else 0.0
            print(f"{field:<10} {label:<28} {total:>6} {share:>27.0f}%")


def calibrate():
    """Is the error predictable before the answer is known?

    Two signals available at prediction time: how far the nearest observed
    unit is, and whether independent estimators agree with each other.
    """
    countries, units = load()
    rows_out = []
    for field in FIELDS:
        for country, rows in units.items():
            seen = [(r, composition(r[field], field)) for r in rows
                    if isinstance(r.get(field), list)]
            seen = [(r, v) for r, v in seen if v]
            if len(seen) < 4:
                continue
            national_rows = countries.get(country, {}).get(field)
            national = (composition(national_rows, field)
                        if isinstance(national_rows, list) else None)
            for i, (row, truth) in enumerate(seen):
                others = [pair for j, pair in enumerate(seen) if j != i]
                near = sorted(others, key=lambda ov: great_circle_km(
                    row.get("point"), ov[0].get("point")))
                distance = great_circle_km(row.get("point"), near[0][0].get("point"))
                if not math.isfinite(distance):
                    continue
                idw = mix([(v, 1.0 / max(great_circle_km(row.get("point"),
                                                         o.get("point")), 10.0))
                           for o, v in near[:3]])
                mean = mix([(v, population(o) or 1) for o, v in others])
                rivals = [idw, mean] + ([national] if national else [])
                spread = max((tvd(a, b) for n, a in enumerate(rivals)
                              for b in rivals[n + 1:]), default=0.0)
                rows_out.append((field, tvd(truth, idw),
                                 leader(truth) == leader(idw), distance, spread))

    def bands(rows, label, key, edges):
        print(f"\n  by {label}:")
        print(f"    {'band':<16} {'n':>5} {'median':>9} {'p90':>7} "
              f"{'leading group right':>20}")
        for low, high in zip([0] + edges, edges + [math.inf]):
            sel = [r for r in rows if low <= key(r) < high]
            if len(sel) < 25:
                continue
            errors = sorted(r[1] for r in sel)
            accuracy = sum(r[2] for r in sel) / len(sel)
            at = lambda f: errors[min(int(len(errors) * f), len(errors) - 1)]
            name = f"{low:g}-{high:g}" if math.isfinite(high) else f"{low:g}+"
            print(f"    {name:<16} {len(sel):>5} {at(.5) * 100:>8.1f}% "
                  f"{at(.9) * 100:>6.1f}% {accuracy * 100:>19.1f}%")

    for field in FIELDS:
        rows = [r for r in rows_out if r[0] == field]
        print(f"\n=== {field} (n={len(rows)}, estimator: 3 nearest IDW)")
        bands(rows, "km to the nearest observed unit", lambda r: r[3], [50, 150, 400])
        bands(rows, "disagreement between estimators", lambda r: r[4],
              [0.05, 0.15, 0.30])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--calibrate", action="store_true",
                    help="is the error predictable before the answer is known?")
    ap.add_argument("--raw", action="store_true",
                    help="also score on raw labels, to show what canonicalising buys")
    args = ap.parse_args()
    if args.calibrate:
        calibrate()
        return 0
    if args.raw:
        report(score(canonical=False), "RAW LABELS (vocabulary differences count as error)")
    report(score(canonical=True, cross_border=True), "CANONICAL (tier-2 groups)")
    reachability()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
