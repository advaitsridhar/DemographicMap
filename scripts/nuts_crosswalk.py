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

NUTS-1 regions are the unions of their NUTS-2 regions. A region too coarsely
drawn to reach ``SAME`` -- an exclave, an island group -- is still placed when
it lies on nothing else (``alone``), and ``DECIDED`` settles the two regions
the rules get wrong, with what was measured.

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
# Two of the map's polygons at different levels this alike are one place.
TWIN = 0.9
# A region drawn too coarsely for SAME is still one polygon when this much of
# the ground it shares with its country's polygons of a level is on that one,
# at least UNDER of the polygon lies under it, and no other region of its
# level covers more than ELSE of the polygon (see ``alone``).
ALONE = 0.98
UNDER = 0.4
ELSE = 0.02

# Regions settled by hand where the outline rules decide wrongly, each with
# what was measured: the polygon a region is, or None for one it must not
# reach.
DECIDED: dict[str, tuple[str | None, str]] = {
    # The rule refused Flanders as holding Brussels (BE1), but GISCO's 1:10
    # million Brussels is drawn at 1.9 times its area and only half of it
    # (0.504) spills onto the map's Flanders. The map cuts Brussels out of
    # Flanders as a hole -- the two polygons share none of their ground -- and
    # BE2 covers the map's Flanders at 0.89.
    "BE2": ("27649430B69989386836371",
            "Vlaams Gewest; refused by outline only because GISCO's coarse Brussels "
            "spills onto it, while the map draws Brussels as a hole in it"),
    # Kozep-Magyarorszag is Budapest and Pest county. The map draws no
    # Budapest; its Pest polygon covers both (0.91) but the unit counts Pest
    # county's people alone, 1.33 million against the region's 3.0 million, so
    # the region's figures would contradict the population beside them.
    "HU1": (None, "Budapest and Pest county together, on a Pest polygon that counts "
                  "Pest county's people alone"),
    # Portugal's first level is its eighteen districts and two autonomous
    # regions, and NUTS-3 is a different grouping of the same municipalities.
    # Six regions are a district exactly (Alto Minho, Algarve, Alto Alentejo,
    # Alentejo Central, the Azores, Madeira); these three pass 0.8 and are
    # not. Measured by laying the municipalities (bound to INE codes by
    # portugal_census) on GISCO's 2024 outlines, and by the 2021 census
    # counts of each side:
    #   PT11E Terras de Tras-os-Montes: 9 of Braganca's 12 municipalities
    #     (not Carrazeda de Ansiaes, Freixo de Espada a Cinta, Torre de
    #     Moncorvo), 107,272 people in 2021 against the district's 122,804;
    #   PT192 Regiao de Coimbra: Coimbra's 17 and Mealhada (Aveiro) and
    #     Mortagua (Viseu), 436,862 against 408,551;
    #   PT1C2 Baixo Alentejo: 13 of Beja's 14 (not Odemira, 29,538 people,
    #     which is Alentejo Litoral), 114,863 against 144,401.
    # Written on the districts, each region's figures stood beside the census
    # district's religion as though they described the same people.
    # Nordjylland is one NUTS-2 region (DK05) and one NUTS-3 region (DK050),
    # and the map's Nordjylland is it: GISCO's 1:10 million outline covers the
    # polygon at 0.788, just under SAME, for a coast and islands (Læsø) drawn
    # coarsely, and lies on no other Danish unit. Neither rule placed it, and
    # nothing refused it either, so the region dropped out of the file
    # unremarked, and with it Denmark's fifth region's survey figures.
    "DK05": ("84455774B84842167963849", "Nordjylland, drawn too coarsely for the outline rule "
                                        "(0.788) and on no other Danish unit"),
    "DK050": ("84455774B84842167963849", "Nordjylland, drawn too coarsely for the outline "
                                         "rule (0.788) and on no other Danish unit"),
    "PT11E": (None, "Terras de Tras-os-Montes, 9 of the Braganca district's 12 municipalities"),
    "PT192": (None, "Regiao de Coimbra, the Coimbra district's 17 municipalities with "
                    "Mealhada and Mortagua"),
    "PT1C2": (None, "Baixo Alentejo, the Beja district without Odemira"),
}
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


def nuts1_from(level2: list[dict]) -> list[dict]:
    """NUTS-1 regions as the union of their NUTS-2 regions.

    A NUTS-1 code is the first three characters of each of its NUTS-2
    regions' (FRK is FRK1 and FRK2), and the classification nests exactly, so
    the union is the region's outline without a third download -- which the
    runner could not commit anyway, since data/raw is ignored but for the
    files already tracked.
    """
    from shapely.ops import unary_union
    groups: dict[str, list[dict]] = defaultdict(list)
    for region in level2:
        groups[region["id"][:3]].append(region)
    return [{"id": code, "cntr": parts[0]["cntr"],
             "geom": unary_union([p["geom"] for p in parts]).buffer(0)}
            for code, parts in sorted(groups.items())]


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


def alone(region: dict, regions: list, lvl: int, tree, shapes: list[dict],
          country: str | None) -> tuple[dict, str] | None:
    """The one polygon a region too coarsely drawn to reach ``SAME`` must be.

    GISCO's 1:10 million outlines generalise a small place or an island's
    coast past what intersection over union forgives: Ceuta's outline covers
    the map's Ceuta at 0.42, the Ionian Islands' at 0.73, though neither
    region touches any other unit of Spain or Greece. Such a region is still
    the one polygon if, at one level of the map, all the ground it shares with
    the country lies on that polygon (``ALONE``), and no other region of its
    NUTS level lies on the polygon at all -- which is what keeps a part of a
    unit from passing for the whole (Gran Canaria lies only on the map's Las
    Palmas, and so do Lanzarote and Fuerteventura). The polygon must also lie
    mostly under the region (``UNDER``), so an outline that merely falls
    inside a much larger unit is not taken for it.
    """
    geom = region["geom"]
    by_level: dict[str, list[tuple[float, dict]]] = defaultdict(list)
    for i in tree.query(geom, predicate="intersects"):
        s = shapes[i]
        if s["group"] != country:
            continue
        inter = geom.intersection(s["geom"]).area
        if inter:
            by_level[s["level"]].append((inter, s))
    found = []
    for level, hits in by_level.items():
        total = sum(a for a, _ in hits)
        area, unit = max(hits, key=lambda h: h[0])
        if area < ALONE * total or area < UNDER * unit["geom"].area:
            continue
        others = [r["id"] for l2, r in regions
                  if l2 == lvl and r is not region and r["cntr"] == region["cntr"]
                  and r["geom"].intersects(unit["geom"])
                  and r["geom"].intersection(unit["geom"]).area > ELSE * unit["geom"].area]
        if others:
            continue
        found.append((area / unit["geom"].area, unit, f"drawn too coarsely for {SAME} (it covers {unit['id']}, "
                            f"{unit['name']}, at {area / unit['geom'].area:.2f}) but lies on "
                            f"nothing else of its {level} and shares it with no other region; "
                            "placed there"))
    # A place the map draws at both levels (Ceuta) is found at both; the one
    # it covers more of is taken, and the other reached by the twin rule below.
    if not found:
        return None
    _, unit, why = max(found, key=lambda f: f[0])
    return unit, why


def main() -> int:
    from shapely import STRtree
    iso3 = iso3_by_alpha2()
    level2 = load_nuts(2)
    regions = ([(1, r) for r in nuts1_from(level2)] + [(2, r) for r in level2]
               + [(3, r) for r in load_nuts(3)])
    countries = {iso3[r["cntr"]] for _, r in regions if r["cntr"] in iso3}
    shapes = load_shapes(countries)
    tree = STRtree([s["geom"] for s in shapes])
    log(f"{len(regions)} regions against {len(shapes)} polygons in {len(countries)} countries")

    best: dict[str, dict] = {}
    refused: dict[str, dict] = {}
    for lvl, region in regions:
        country = iso3.get(region["cntr"])
        geom = region["geom"]
        if region["id"] in DECIDED:
            shape_id, why = DECIDED[region["id"]]
            log(f"  {region['id']}: decided -- {why}")
            if shape_id is None:
                refused[region["id"]] = {"refused": why}
                continue
            unit = next(s for s in shapes if s["id"] == shape_id)
            best[region["id"]] = {"nuts_level": lvl, "level": unit["level"],
                                  "shape_id": unit["id"], "name": unit["name"],
                                  "iou": round(geom.intersection(unit["geom"]).area
                                               / geom.union(unit["geom"]).area, 3),
                                  "decided": why}
            continue
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
        coarse = None
        if top and top[0] < SAME:
            coarse = alone(region, regions, lvl, tree, shapes, country)
            if coarse:
                log(f"  {region['id']}: {coarse[1]}")
                top = (top[0], coarse[0])
        if top and (top[0] >= SAME or coarse):
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
                                  "iou": round(geom.intersection(unit["geom"]).area
                                               / geom.union(unit["geom"]).area, 3)}
            if coarse:
                best[region["id"]]["coarse"] = True

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
    # The map draws some polygons at both levels -- Madrid, Navarra, Prague,
    # Brandenburg -- and a region reaches only one of them; its twin at the
    # other level gets the same figures.
    for entry in out.values():
        if "shape_id" not in entry:
            continue
        unit = next(s for s in shapes if s["id"] == entry["shape_id"] and s["level"] == entry["level"])
        twins = []
        for i in tree.query(unit["geom"], predicate="intersects"):
            s = shapes[i]
            if s["level"] == unit["level"] or s["group"] != unit["group"]:
                continue
            inter = unit["geom"].intersection(s["geom"]).area
            if inter and inter / unit["geom"].union(s["geom"]).area >= TWIN:
                twins.append({"level": s["level"], "shape_id": s["id"], "name": s["name"]})
        if len(twins) == 1:
            entry["also"] = twins
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
