#!/usr/bin/env python3
"""Draw the ground a country's second level leaves out, as units of its own.

Uruguay's second-order units are municipios, constituted around population
centres (Ley 18.567 of 2009), and the ground of a department that lies in no
municipio is governed by the department directly. geoBoundaries draws the 124
municipios and nothing else, so at second-order zoom 63% of the country -- most
of every department capital among it -- was in no unit at all and could only
be painted as blank land.

That ground is real and it is counted: a department's census count less its
municipios' is the people who live on it. So each department's remainder is
drawn as a unit of its own, named for what it is ("Salto, outside any
municipio"), and the build gives it that difference where the arithmetic is
sound and a gap that says why where it is not.

The geometry is the first-order polygon less every second-order polygon inside
it, with the slivers a pair of independently drawn boundary files leave along
their shared edges taken off, and simplified to about 100 m. It is written to
data/processed/admin2_remainders.geojson, which the tiler draws into the
second-order layer and the build reads as second-order shapes.

Usage:
    python3 scripts/make_remainders.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_entities import BOUNDARIES, PROCESSED, REMAINDERS, whole  # noqa: E402

OUT = PROCESSED / "admin2_remainders.geojson"
# Slivers: anything thinner than about 200 m along a shared edge.
SLIVER = 0.002
# A remainder smaller than this share of its first-order unit is edge noise.
MIN_SHARE = 0.01
SIMPLIFY = 0.001


def features(level: str, iso3: str) -> list[tuple[dict, object]]:
    import fiona
    from shapely.geometry import shape

    out = []
    with fiona.open(BOUNDARIES / f"geoBoundariesCGAZ_{level}.gpkg") as src:
        for feat in src:
            props = dict(feat["properties"])
            if props.get("shapeGroup") == iso3 and feat["geometry"]:
                out.append((props, whole(shape(feat["geometry"]))))
    return out


def remainders(iso3: str, label: str) -> list[dict]:
    from shapely.geometry import mapping
    from shapely.ops import unary_union

    firsts = features("ADM1", iso3)
    seconds = features("ADM2", iso3)
    out = []
    for props, polygon in firsts:
        inside = [g for _, g in seconds if polygon.contains(g.representative_point())]
        rest = polygon.difference(unary_union(inside)) if inside else polygon
        rest = rest.buffer(-SLIVER).buffer(SLIVER).intersection(polygon)
        if rest.is_empty or rest.area < MIN_SHARE * polygon.area:
            continue
        name = props["shapeName"]
        out.append({
            "type": "Feature",
            "properties": {"shapeID": f"{iso3}-REST-{props['shapeID']}",
                           "shapeName": f"{name}, {label}",
                           "shapeGroup": iso3, "shapeType": "ADM2",
                           "parentID": props["shapeID"]},
            "geometry": mapping(rest.simplify(SIMPLIFY, preserve_topology=True)),
        })
        print(f"  {iso3} {name}: {rest.area / polygon.area:.0%} of it in no second-order unit")
    return out


def main() -> int:
    collection = {"type": "FeatureCollection", "features": []}
    for iso3, (label, _note) in REMAINDERS.items():
        collection["features"].extend(remainders(iso3, label))
    OUT.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(collection['features'])} units")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
