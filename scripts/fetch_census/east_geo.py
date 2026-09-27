#!/usr/bin/env python3
"""Where a place lies on the map, for the eastern census adapters.

Several of this region's boundary files draw units that the offices count
differently: Ukraine's raions and Georgia's municipalities swallow the cities
counted apart from them, Belarus's raions their oblast towns, and Russia's
second level mixes districts abolished years ago with the okrugs that replaced
them. A name cannot say which polygon a city counted apart has been drawn
into; its coordinate, put in the polygons, can.

Two helpers, and nothing more: the map's own polygons for a country (the
geoBoundaries release the map is built from, simplified, fetched once and
cached under data/raw/boundaries), and GeoNames' populated places for it
(data/raw/geonames, in the repository). Neither is ever a source of a figure.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from ._shared import log

import fetch_boundaries  # noqa: E402  (scripts/ is on the path via _shared)
import fetch_geonames  # noqa: E402


def polygons(iso3: str, level: str = "ADM2") -> dict[str, Any]:
    """{shape id: shapely geometry} for the map's polygons of one country."""
    from shapely.geometry import shape
    from shapely.prepared import prep

    got = fetch_boundaries.fetch_country(iso3, level, simplified=True, force=False)
    if not got:
        raise SystemExit(f"east_geo: no {level} boundaries for {iso3}")
    data = json.loads(Path(got["path"]).read_text())
    out = {}
    for feature in data["features"]:
        geometry = shape(feature["geometry"])
        out[feature["properties"]["shapeID"]] = (geometry, prep(geometry))
    log(f"  {iso3} {level}: {len(out)} polygons from {Path(got['path']).name}")
    return out


def containing(shapes: dict[str, Any], lon: float, lat: float,
               near: float = 0.0) -> list[str]:
    """The shape ids a point falls in; with ``near``, within that many degrees."""
    from shapely.geometry import Point

    point = Point(lon, lat)
    inside = [sid for sid, (_, prepared) in shapes.items() if prepared.contains(point)]
    if inside or not near:
        return inside
    return [sid for sid, (geometry, _) in shapes.items()
            if geometry.distance(point) <= near]


def places(iso3: str) -> list[dict[str, Any]]:
    """GeoNames' populated places in one country, as the repository keeps them."""
    return [p for p in fetch_geonames.read_places() if p["iso3"] == iso3]


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text)
