#!/usr/bin/env python3
"""Which shapes does one adapter file claim twice, and does it matter?

``resolve_collisions`` refuses rivals for a shape, except where they all
matched outright -- there it treats them as one place a source listed twice
and lets the last one win. That exemption is right for Wikidata, which carries
both "Ancasti" and "Ancasti Department", and ``norm()`` drops "Department".

It was wrong for the Philippines. "Cebu City" and "Province Of Cebu" also
differ only by words ``norm()`` drops, and are two places 20 km and 3.9 million
people apart. Last one won, so one wore the other's figures with nothing on the
map to show it. Names alone cannot tell those two cases apart -- which is why
this asks a different question.

The question is whether the rivals *disagree*. Two listings of one place carry
the same figures, so whichever wins, the map is right. Two different places
carry different figures, so the loser's are being silently discarded. That
test needs no knowledge of any particular country, and it is the one that
separates a harmless duplicate from a wrong answer.

Usage:
    python3 scripts/audit_claims.py             # report, exit 0
    python3 scripts/audit_claims.py --strict    # exit 1 if any rivals disagree
    python3 scripts/audit_claims.py --country PHL ETH
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_entities as be  # noqa: E402

# The same test resolve_collisions now applies, imported rather than restated
# so the report and the rule can never drift apart.
disagreement = be.conflicting

# Two points this far apart are not one place written twice, whatever the
# names say. Generous on purpose: a province's centroid and a city's within it
# can be tens of kilometres apart and still be the honest same-place case, and
# this is evidence offered to a reader rather than a rule that decides.
FAR_KM = 50.0


def apart(rows: list[dict[str, Any]]) -> float | None:
    """Greatest distance in km between any two rivals that published a point."""
    points = [p for p in (be.row_point(r) for r in rows) if p]
    if len(points) < 2:
        return None
    from math import asin, cos, radians, sin, sqrt
    worst = 0.0
    for i, (lon1, lat1) in enumerate(points):
        for lon2, lat2 in points[i + 1:]:
            dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
            h = (sin(dlat / 2) ** 2
                 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2)
            worst = max(worst, 2 * 6371.0 * asin(sqrt(h)))
    return round(worst, 1)


def audit(countries: list[str] | None = None) -> list[dict[str, Any]]:
    by_country = be.load_adapters()
    shapes = {lvl: be.read_shapes(lvl) for lvl in ("ADM1", "ADM2")}
    be.link_adm2_parents(shapes["ADM1"], shapes["ADM2"])

    a1_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    a2_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shape in shapes["ADM1"]:
        a1_by[shape["group"]].append(be.blank(shape, "admin1", shape["group"]))
    for shape in shapes["ADM2"]:
        a2_by[shape["group"]].append(
            be.blank(shape, "admin2", shape.get("parent_shape") or shape["group"]))

    found = []
    for iso3, rows in sorted(by_country.items()):
        if countries and iso3 not in countries:
            continue
        a1 = {be.norm(e["name"]): e for e in a1_by.get(iso3, [])}
        a2: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entity in a2_by.get(iso3, []):
            a2[be.norm(entity["name"])].append(entity)

        matched = []
        for row in rows:
            if row.get("no_shape"):
                continue
            key = {"name": row.get("name") or "",
                   "aliases": row.get("aliases") or [],
                   "parent_name": row.get("parent_name"),
                   "parent_aliases": row.get("parent_aliases") or [],
                   "point": be.row_point(row)}
            if row.get("level") == "admin1":
                entity, how = be.match_name(key, a1)
            else:
                entity, how = be.match_admin2(key, a2, a1)
            if entity is not None:
                matched.append((row, entity, how))

        dropped, _ = be.resolve_collisions(matched)
        claims: dict[tuple[Any, str], list[int]] = defaultdict(list)
        for i, (row, entity, _how) in enumerate(matched):
            if i not in dropped:
                claims[(row.get("_source"), entity["id"])].append(i)
        for (source, _eid), idxs in claims.items():
            if len(idxs) < 2:
                continue
            rivals = [matched[i][0] for i in idxs]
            found.append({
                "country": iso3,
                "source": source,
                "shape": matched[idxs[0]][1]["name"],
                "level": matched[idxs[0]][1]["level"],
                "names": [r.get("name") for r in rivals],
                "fields": disagreement(rivals),
                "apart_km": apart(rivals),
            })
    return found


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when rival rows disagree on a value")
    ap.add_argument("--country", nargs="*", help="limit to these ISO3 codes")
    args = ap.parse_args()

    found = audit([c.upper() for c in args.country] if args.country else None)
    # A value disagreement is the harm: one row's figure is on the map and the
    # other's was discarded without trace. Distance is corroboration, not harm
    # -- rivals far apart with nothing to disagree about cost the map only a
    # centroid and a citation.
    conflicts = [f for f in found if f["fields"]]
    far = [f for f in found
           if not f["fields"] and (f["apart_km"] or 0) > FAR_KM]
    quiet = [f for f in found if f not in conflicts and f not in far]

    for f in conflicts:
        where = f" ({f['apart_km']} km apart)" if f["apart_km"] else ""
        be.log(f"  CONFLICT {f['country']} {f['source']} {f['level']} "
               f"{f['shape']!r} <- {', '.join(repr(n) for n in f['names'])}: "
               f"disagree on {', '.join(f['fields'])}{where}")
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for bucket, f in [(0, f) for f in far] + [(1, f) for f in quiet]:
        counts[f"{f['country']} {f['source']}"][bucket] += 1
    for where, (n_far, n_quiet) in sorted(counts.items(),
                                          key=lambda kv: -sum(kv[1])):
        parts = []
        if n_far:
            parts.append(f"{n_far} rivals over {FAR_KM:.0f} km apart with no "
                         f"differing value")
        if n_quiet:
            parts.append(f"{n_quiet} carrying nothing to disagree about")
        be.log(f"  {where}: " + ", ".join(parts))

    be.log(f"{len(conflicts)} shapes where a value is silently discarded; "
           f"{len(far)} where distant rivals differ only in identity; "
           f"{len(quiet)} with nothing to choose between")
    return 1 if (args.strict and conflicts) else 0


if __name__ == "__main__":
    sys.exit(main())
