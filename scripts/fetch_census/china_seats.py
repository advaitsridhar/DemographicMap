#!/usr/bin/env python3
"""Which of today's county-level seats stand in each of China's drawn county polygons.

China's 2,370 second-level polygons are a county division of the mid-1990s
(Tongxian, not Tongzhou District; Panyu as the county-level city it was until
2000), so a county's 2020 figure belongs on a polygon only where the polygon
is still that one county. ``data/processed/code_shapes.json`` says which
polygon a GB/T 2260 code's Wikidata item stands in when the item's name and
the polygon's agree; this says, for every polygon, which current county-level
codes stand in it at all. A polygon holding one seat and bound to that seat's
code by name is the county today; a polygon holding two or more is a city
core or a county a later district was cut from, and one holding none is a
county later merged into a neighbour -- whose own polygon then holds a
county that is bigger than it is drawn.

It needs the CGAZ boundary file the map is built from (data/raw/boundaries,
about 240 MB, not in git and not on the adapter runner), so it is run where
the boundaries are, and its small output is kept in the repository:
``data/raw/wikidata_points/CHN_P442_seats.json``, {shape id: [codes of the seats inside]}.

The seats are Wikidata's current items carrying a six-figure GB/T 2260 code
(data/raw/wikidata_points/CHN_P442.json), less prefecture codes (ending 00)
and the "districts" aggregates (ending 01 and labelled as such). Wikidata
names no figure here; it only says where a code's seat stands.

Usage:
    python -m scripts.fetch_census.china_seats
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POINTS = ROOT / "data" / "raw" / "wikidata_points" / "CHN_P442.json"
UNITS = ROOT / "site" / "data" / "admin2" / "CHN.units.json"
OUT = ROOT / "data" / "raw" / "wikidata_points" / "CHN_P442_seats.json"
CGAZ = "geoBoundariesCGAZ_ADM2.gpkg"


def county_codes(points: list[dict]) -> list[tuple[str, float, float]]:
    """(code, lon, lat) for every current county-level item."""
    out = []
    for p in points:
        code = re.sub(r"\s", "", p.get("code") or "")
        if not re.fullmatch(r"\d{6}", code) or code.endswith("00"):
            continue
        if code[4:] == "01" and re.search(r"(?i)districts\b|市辖区", p.get("label") or ""):
            continue
        out.append((code, float(p["lon"]), float(p["lat"])))
    return out


def boundaries() -> Path:
    for base in (ROOT / "data" / "raw" / "boundaries",
                 ROOT.parent.parent.parent / "data" / "raw" / "boundaries"):
        if (base / CGAZ).exists():
            return base / CGAZ
    raise SystemExit(f"china_seats: {CGAZ} is not here; run this where the boundaries are")


def main() -> int:
    import fiona
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree

    drawn = {u["id"] for u in json.loads(UNITS.read_text(encoding="utf-8"))}
    ids, geoms = [], []
    with fiona.open(boundaries()) as src:
        for feature in src.filter(bbox=(73, 17, 136, 54)):
            if feature["properties"]["shapeID"] in drawn:
                ids.append(feature["properties"]["shapeID"])
                geoms.append(shape(feature["geometry"]))
    if len(ids) != len(drawn):
        raise SystemExit(f"china_seats: {len(ids)} of the {len(drawn)} drawn polygons found")
    tree = STRtree(geoms)
    seats: dict[str, list[str]] = {sid: [] for sid in ids}
    outside = 0
    for code, lon, lat in county_codes(json.loads(POINTS.read_text(encoding="utf-8"))):
        point = Point(lon, lat)
        hits = [ids[i] for i in tree.query(point) if geoms[i].contains(point)]
        if hits:
            seats[hits[0]].append(code)
        else:
            outside += 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({k: sorted(v) for k, v in sorted(seats.items())},
                              ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    counts = [len(v) for v in seats.values()]
    print(f"china_seats: {len(ids)} polygons; {counts.count(1)} hold one seat, "
          f"{sum(1 for c in counts if c > 1)} several, {counts.count(0)} none; "
          f"{outside} seats in no polygon -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
