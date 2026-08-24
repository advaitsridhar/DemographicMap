#!/usr/bin/env python3
"""Check that a boundary file's admin-2 names sit on the right ground.

The join between a census and a boundary file is made on names, which assumes
the boundary file's names are on the right polygons. That assumption is usually
safe and occasionally very wrong: geoBoundaries CGAZ labels Nepal's districts
in a way that puts Rupandehi's territory inside a shape called "Nawalapur" and
Dailekh's inside one called "Jajarkot". A name join cannot notice, because the
result looks exactly like a correct one.

This checks it against an independent reference point per unit -- Wikidata's
P625, fetched by ``fetch_wikidata.py --level admin2`` -- and reports, for every
unit, whether the polygon containing its point is the polygon bearing its name.

Three outcomes, and they are not the same thing:

* **agrees** -- the point falls inside the polygon of that name. Joinable.
* **near** -- the point falls just outside it, and no other unit's point falls
  inside it either. Reference points are town halls and centroids, not
  authoritative geometry, so a point a kilometre or two over a boundary says
  more about the point than the polygon. Joinable, and the distance is printed
  so the call is reviewable.
* **elsewhere** -- the point falls inside a *differently named* polygon, or no
  polygon bears the name at all. Not joinable: attributing the census figures
  there would put one unit's population on another's ground.

Usage:
    python scripts/verify_shapes.py --country NPL \\
        --points data/processed/nepal_wikidata_points.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# ...and the repository root, so --alias-module can name an adapter by its
# dotted path when this is run as a script rather than as a module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import RAW, log  # noqa: E402

# Roughly 3 km at Nepal's latitude. A reference point further outside its own
# polygon than this is not a rounding difference between sources.
NEAR = 0.03


_canonical = None


def normalise(name: str) -> str:
    """One spelling of a name, resolved the same way the join resolves it.

    Without this the check reports an adapter's own aliases as errors: CGAZ
    writes Bajura as "Baijura" and Syangja as "Synagja", the adapter already
    knows both, and a raw-string comparison would call them mismatches while
    the join handles them correctly. --alias-module points at the adapter so
    there is one list of spellings rather than two that can drift.
    """
    plain = " ".join(name.replace(" District", "").split()).strip()
    if _canonical is not None:
        try:
            return _canonical(plain).lower()
        except KeyError:
            pass
    return plain.lower()


def use_aliases(dotted: str) -> None:
    global _canonical
    import importlib
    module = importlib.import_module(dotted)
    known, canonical = module.known_area, module.canonical_area
    _canonical = lambda name: canonical(name) if known(name) else name  # noqa: E731


def load_points(path: Path, keep: str = "") -> dict[str, tuple[float, float]]:
    """Reference points, keyed by normalised name.

    ``keep`` filters by a substring of the raw name, which is how a country
    whose Wikidata admin-2 query returns two tiers is narrowed to one: Nepal's
    returns its 77 districts and 112 municipalities together, and a
    municipality's point inside a district polygon would read as that polygon
    claiming a second unit.
    """
    out = {}
    for row in json.load(path.open()):
        point = row.get("coordinates")
        name = row.get("name") or ""
        if keep and keep.lower() not in name.lower():
            continue
        if not name or not isinstance(point, (list, tuple)) or len(point) != 2:
            continue
        if not all(isinstance(v, (int, float)) for v in point):
            continue
        out[normalise(name)] = (float(point[0]), float(point[1]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", required=True, help="ISO3, as shapeGroup")
    ap.add_argument("--points", type=Path, required=True)
    ap.add_argument("--level", default="ADM2", choices=["ADM1", "ADM2"])
    ap.add_argument("--near", type=float, default=NEAR)
    ap.add_argument("--alias-module", default="",
                    help="dotted module exposing known_area/canonical_area, so "
                         "the check resolves names the way the join does")
    ap.add_argument("--name-contains", default="",
                    help="keep only reference names containing this, for "
                         "countries whose admin-2 query returns two tiers")
    args = ap.parse_args()

    if args.alias_module:
        use_aliases(args.alias_module)

    import fiona
    from shapely.geometry import Point, shape

    points = load_points(args.points, args.name_contains)
    log(f"  {len(points)} reference points")

    shapes: dict[str, list] = {}
    path = RAW / "boundaries" / f"geoBoundariesCGAZ_{args.level}.gpkg"
    with fiona.open(path) as src:
        for feat in src:
            props = feat["properties"]
            if props.get("shapeGroup") != args.country:
                continue
            shapes.setdefault(normalise(props.get("shapeName") or ""),
                              []).append(shape(feat["geometry"]))
    log(f"  {sum(len(v) for v in shapes.values())} shapes under "
        f"{len(shapes)} distinct names")

    # Which reference points each polygon name claims, so an over-extended or
    # duplicated polygon is visible rather than inferred.
    claims: dict[str, list[str]] = {}
    for name, geoms in shapes.items():
        claims[name] = [unit for unit, (lon, lat) in points.items()
                        if any(g.contains(Point(lon, lat)) for g in geoms)]

    agrees, near, elsewhere = [], [], []
    for unit, (lon, lat) in sorted(points.items()):
        pt = Point(lon, lat)
        holding = [name for name, geoms in shapes.items()
                   if any(g.contains(pt) for g in geoms)]
        own = shapes.get(unit)
        if unit in holding and len(shapes[unit]) == 1:
            agrees.append(unit)
        elif own is not None and len(own) == 1 and not holding:
            elsewhere.append((unit, "point is outside every polygon"))
        elif own is not None and len(own) == 1 and not claims[unit]:
            distance = min(g.distance(pt) for g in own)
            if distance <= args.near:
                near.append((unit, distance, holding))
            else:
                elsewhere.append((unit, f"{distance:.3f} deg from its own "
                                        f"polygon; point is inside {holding}"))
        elif own is None:
            elsewhere.append((unit, f"no polygon bears this name; point is "
                                    f"inside {holding}"))
        else:
            elsewhere.append((unit, f"{len(shapes[unit])} polygons bear this "
                                    f"name; point is inside {holding}"))

    print(f"\nagrees   {len(agrees)}")
    print(f"near     {len(near)}")
    print(f"elsewhere {len(elsewhere)}\n")
    for unit, distance, holding in near:
        print(f"  near      {unit:<18} {distance:.4f} deg outside; point is "
              f"inside {holding}")
    for unit, why in elsewhere:
        print(f"  elsewhere {unit:<18} {why}")

    orphans = sorted(n for n, held in claims.items() if not held)
    if orphans:
        print(f"\n  polygons claiming no reference point: {orphans}")
    crowded = {n: held for n, held in claims.items() if len(held) > 1}
    if crowded:
        print("  polygons claiming more than one:")
        for name, held in sorted(crowded.items()):
            print(f"    {name:<18} {held}")

    missing = sorted(set(shapes) - set(points))
    if missing:
        print(f"\n  polygon names with no reference point: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
