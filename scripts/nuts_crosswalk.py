#!/usr/bin/env python3
"""Which of the map's polygons each Eurostat region is, by outline.

Eurostat's regions carry their own names -- "Bratislavsky kraj", "Grad
Zagreb", "Keski-Suomi" -- and the map's carry geoBoundaries' -- "Region of
Bratislava", "City of Zagreb", "Central Finland". Matched by name, Croatia,
Slovakia, Lithuania, Finland and a dozen more countries found nothing, and
Germany's Regierungsbezirke and Italy's regions, which are NUTS-2 regions
drawn at the map's second level, were looked for at the first.

An outline has no spelling. A region whose polygon and a map polygon cover
the same ground -- intersection over union of at least ``SAME`` -- is that
unit, whatever either calls it; anything less is left to the name matcher,
which refuses what it cannot place. Where a NUTS-2 region and a NUTS-3 region
are the same polygon (Istanbul is TR10 and TR100), the finer one keeps it.

Reads GISCO's outlines from data/raw/eurostat (``eurostat --fetch-geometry``
on a runner) and the CGAZ files; writes data/processed/nuts_crosswalk.json.

Usage:
    python -m scripts.nuts_crosswalk
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import PROCESSED, RAW, log, repair, write_json  # noqa: E402

GEOMETRY = RAW / "eurostat"
BOUNDARIES = RAW / "boundaries"
OUT = PROCESSED / "nuts_crosswalk.json"
SAME = 0.8
# Share of a polygon's area that makes it "inside" another.
HELD = 0.5
ALPHA2 = {"EL": "GRC", "UK": "GBR"}


def iso3_by_alpha2() -> dict[str, str]:
    out = dict(ALPHA2)
    site = PROCESSED.parent.parent / "site" / "data" / "admin0.json"
    for row in json.loads(site.read_text(encoding="utf-8")):
        iso2 = (row.get("codes") or {}).get("iso2")
        if iso2 and row.get("country"):
            out.setdefault(iso2, row["country"])
    return out


def load_nuts(level: int) -> list[dict]:
    from shapely.geometry import shape
    path = GEOMETRY / f"NUTS_RG_10M_2024_4326_LEVL_{level}.geojson"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [{"id": f["properties"]["NUTS_ID"], "cntr": f["properties"]["CNTR_CODE"],
             "geom": shape(f["geometry"]).buffer(0)} for f in data["features"]]


def load_shapes(countries: set[str]) -> list[dict]:
    import fiona
    from shapely.geometry import shape
    out = []
    for level, name in (("admin1", "ADM1"), ("admin2", "ADM2")):
        with fiona.open(BOUNDARIES / f"geoBoundariesCGAZ_{name}.gpkg") as src:
            for feat in src:
                props = feat["properties"]
                if props["shapeGroup"] in countries and feat["geometry"]:
                    out.append({"level": level, "id": props["shapeID"],
                                "group": props["shapeGroup"],
                                # As the build reads it: the file double-encodes
                                # some names ("BRAGANÃ\x87A").
                                "name": repair(props.get("shapeName") or ""),
                                "geom": shape(feat["geometry"]).buffer(0)})
    return out


def main() -> int:
    from shapely import STRtree
    iso3 = iso3_by_alpha2()
    regions = [(lvl, r) for lvl in (2, 3) for r in load_nuts(lvl)]
    countries = {iso3[r["cntr"]] for _, r in regions if r["cntr"] in iso3}
    shapes = load_shapes(countries)
    tree = STRtree([s["geom"] for s in shapes])
    log(f"{len(regions)} regions against {len(shapes)} polygons in {len(countries)} countries")

    best: dict[str, dict] = {}
    refused: dict[str, dict] = {}
    for lvl, region in regions:
        country = iso3.get(region["cntr"])
        geom = region["geom"]
        top = None
        for i in tree.query(geom, predicate="intersects"):
            s = shapes[i]
            if s["group"] != country:
                continue
            inter = geom.intersection(s["geom"]).area
            if not inter:
                continue
            iou = inter / geom.union(s["geom"]).area
            if top is None or iou > top[0]:
                top = (iou, s)
        if top and top[0] >= SAME:
            unit = top[1]
            # Area hides a small, dense place: "Oslo og Viken" covers the
            # map's Viken at 0.94 and holds Oslo besides. So no other unit of
            # the level may lie mostly inside the region, and no other
            # region of the level mostly inside the unit.
            extra = [s["id"] for i in tree.query(geom, predicate="intersects")
                     for s in [shapes[i]]
                     if s is not unit and s["group"] == country and s["level"] == unit["level"]
                     and geom.intersection(s["geom"]).area > HELD * s["geom"].area]
            also = [r["id"] for l2, r in regions
                    if l2 == lvl and r is not region and r["cntr"] == region["cntr"]
                    and r["geom"].intersects(unit["geom"])
                    and r["geom"].intersection(unit["geom"]).area > HELD * r["geom"].area]
            if extra or also:
                why = (f"covers {unit['id']} at {top[0]:.2f} but also holds "
                       f"{extra or also}")
                log(f"  {region['id']}: {why}; refused")
                refused[region["id"]] = {"refused": why}
                continue
            best[region["id"]] = {"nuts_level": lvl, "level": unit["level"],
                                  "shape_id": unit["id"], "name": unit["name"],
                                  "iou": round(top[0], 3)}

    # One region per polygon: the finer where NUTS-2 and NUTS-3 are the same
    # outline; and never two regions of one level on one polygon.
    by_shape: dict[str, list[str]] = defaultdict(list)
    for nuts_id, entry in best.items():
        by_shape[entry["shape_id"]].append(nuts_id)
    # A region whose outline shows it is a unit and more is refused, not left
    # to its name: Eurostat's Pest is the map's Pest without Budapest, and by
    # name it had been written onto a Pest that includes the capital.
    out: dict[str, dict] = dict(refused)
    for shape_id, ids in by_shape.items():
        ids.sort(key=lambda n: (-best[n]["nuts_level"], -best[n]["iou"]))
        keep = ids[0]
        if len([n for n in ids if best[n]["nuts_level"] == best[keep]["nuts_level"]]) > 1:
            log(f"  {shape_id}: {ids} all fit it; left to the name matcher")
            continue
        out[keep] = best[keep]
        for other in ids[1:]:
            out[other] = {"superseded_by": keep}
    placed = defaultdict(int)
    for entry in out.values():
        if "level" in entry:
            placed[(entry["nuts_level"], entry["level"])] += 1
    log(f"placed: {dict(placed)}; superseded {sum('superseded_by' in e for e in out.values())}; "
        f"refused {len(refused)}")
    write_json(OUT, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
