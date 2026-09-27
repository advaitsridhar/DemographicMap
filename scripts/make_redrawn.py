#!/usr/bin/env python3
"""Redraw second-order polygons the boundary file draws as the wrong number of units.

Two ways a boundary file can miscount a place, both found in Bolivia:

* **One feature for several units.** geoBoundaries draws the Cercado provinces
  of Beni, Cochabamba, Oruro and Tarija -- four provinces in four departments,
  the cities of Trinidad, Cochabamba, Oruro and Tarija -- as one multipolygon
  named "Cercado" and files it under Beni. No province's figures can go on it:
  every one of them would be a quarter of the truth drawn over four places.
  It is split here into its parts, each filed under the department its whole
  area lies in, and named as the province it is.
* **Several features for one unit.** Gualberto Villarroel (La Paz) is drawn as
  a polygon named for it and a second, two-part feature named "Gualberto
  Villarroe" that overlaps nothing else: the rest of the same province. The
  province's figures sit on the first and the second reads as an empty
  province of its own. They are merged here, under the first one's id, so the
  province is one unit with its whole ground.

Each redraw is measured before it is written: a split's every part must lie
at least 99% inside one first-order polygon, and no two parts in the same
one; a merge's features must not overlap any other second-order polygon of
the country. The output, data/processed/admin2_redrawn.geojson, is drawn by
the tiler into the second-order layer in place of the features it replaces
(``replaces`` on each feature), and read by the build the same way.

Usage:
    python3 scripts/make_redrawn.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_entities import BOUNDARIES, PROCESSED, whole  # noqa: E402

OUT = PROCESSED / "admin2_redrawn.geojson"
SIMPLIFY = 0.0005
INSIDE = 0.99

# iso3 -> redraws. A split names the feature and, per first-order polygon its
# parts fall in, the name the part is given; a merge names the features and
# the one whose id and name the whole keeps.
REDRAWS: dict[str, list[dict]] = {
    "BOL": [
        {"split": "80513517B48061932483413",
         "names": {"Beni": "Cercado", "Cochabamba": "Cercado", "Oruro": "Cercado",
                   "Tarija": "Cercado"}},
        {"merge": ["80513517B50126659359990", "80513517B19707809734230"],
         "keep": "80513517B50126659359990"},
    ],
}


def features(level: str, iso3: str) -> dict[str, tuple[dict, object]]:
    import fiona
    from shapely.geometry import shape

    out = {}
    with fiona.open(BOUNDARIES / f"geoBoundariesCGAZ_{level}.gpkg") as src:
        for feat in src:
            props = dict(feat["properties"])
            if props.get("shapeGroup") == iso3 and feat["geometry"]:
                out[props["shapeID"]] = (props, whole(shape(feat["geometry"])))
    return out


def parts_of(geom) -> list:
    return list(getattr(geom, "geoms", [geom]))


def main() -> int:
    from shapely.geometry import mapping
    from shapely.ops import unary_union

    out = []
    for iso3, redraws in REDRAWS.items():
        first = features("ADM1", iso3)
        second = features("ADM2", iso3)
        for redraw in redraws:
            if "split" in redraw:
                sid = redraw["split"]
                props, geom = second[sid]
                seen: dict[str, object] = {}
                for part in parts_of(geom):
                    inside = {fid: g.intersection(part).area / part.area
                              for fid, (_, g) in first.items() if g.intersects(part)}
                    fid, share = max(inside.items(), key=lambda kv: kv[1])
                    if share < INSIDE:
                        raise SystemExit(f"make_redrawn: a part of {props['shapeName']} "
                                         f"({sid}) is only {share:.1%} inside one first-order "
                                         "polygon; it cannot be filed under one")
                    if fid in seen:
                        raise SystemExit(f"make_redrawn: two parts of {sid} lie in "
                                         f"{first[fid][0]['shapeName']}")
                    seen[fid] = part
                for fid, part in seen.items():
                    parent = first[fid][0]["shapeName"]
                    name = redraw["names"].get(parent)
                    if name is None:
                        raise SystemExit(f"make_redrawn: {sid} has a part in {parent}, "
                                         "which the declaration does not name")
                    out.append({"type": "Feature", "properties": {
                        "shapeID": f"{sid}-{fid}", "shapeName": name, "shapeGroup": iso3,
                        "shapeType": "ADM2", "parentID": fid, "replaces": [sid],
                        "redrawn": (
                            f"geoBoundaries draws the {props['shapeName']} provinces of "
                            + ", ".join(sorted(first[f][0]["shapeName"] for f in seen))
                            + f" as one feature; this is the part in {parent}, drawn as a "
                            "unit of its own so its figures stand on its own ground.")},
                        "geometry": mapping(part.simplify(SIMPLIFY, preserve_topology=True))})
                print(f"  {iso3} {props['shapeName']}: split into {len(seen)} parts, in "
                      + ", ".join(first[f][0]["shapeName"] for f in seen))
            else:
                ids, keep = redraw["merge"], redraw["keep"]
                geoms = [second[i][1] for i in ids]
                for i in ids:
                    for other, (oprops, og) in second.items():
                        if other in ids or not og.intersects(second[i][1]):
                            continue
                        share = og.intersection(second[i][1]).area / second[i][1].area
                        if share > 0.01:
                            raise SystemExit(f"make_redrawn: {i} overlaps "
                                             f"{oprops['shapeName']} by {share:.1%}; it is "
                                             "not simply the rest of one unit")
                merged = whole(unary_union(geoms))
                inside = {fid: g.intersection(merged).area / merged.area
                          for fid, (_, g) in first.items() if g.intersects(merged)}
                fid = max(inside, key=inside.get)
                name = second[keep][0]["shapeName"]
                out.append({"type": "Feature", "properties": {
                    "shapeID": keep, "shapeName": name, "shapeGroup": iso3,
                    "shapeType": "ADM2", "parentID": fid, "replaces": ids,
                    "redrawn": (
                        f"geoBoundaries draws {name} as {len(ids)} features, one of them "
                        "labelled " + " and ".join(repr(second[i][0]["shapeName"]) for i in ids
                                                   if i != keep)
                        + "; they are drawn here as the one unit they are.")},
                    "geometry": mapping(merged.simplify(SIMPLIFY, preserve_topology=True))})
                print(f"  {iso3} {name}: {len(ids)} features merged under {keep}")
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": out},
                              ensure_ascii=False, separators=(",", ":")))
    print(f"make_redrawn: wrote {OUT.relative_to(ROOT)} ({len(out)} features)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
