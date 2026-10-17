#!/usr/bin/env python3
"""Read-only probes for West Africa and the Sahel: where a published polygon lies.

Mali's regions and cercles were redrawn in 2023 and Mauritania's moughataas
since 2013; the censuses count the new units, the map draws the old ones. Which
old unit a new one lies in is a question about ground, and the answer is in
OCHA's boundary files, which this sandbox cannot fetch. This prints, for every
polygon of a boundary file, its names and codes and a grid of points inside
it, so the new units can be placed against the map's polygons where the map's
boundary file is. Nothing is written and nothing is committed; the output is
the log.

Each argument is one probe, ``mode:url`` with ``~~`` parts after it:

    geo:URL[~~N]     every polygon of every GeoJSON file in the zip (or the
                     GeoJSON) at URL: its name and code properties and about N
                     points on a regular grid inside it (default 30)

Usage:
    python -m scripts.fetch_census.sahel_probe geo:https://example.org/boundaries.geojson.zip~~30
"""

from __future__ import annotations

import io
import json
import math
import re
import sys
import zipfile
from typing import Any

from ._shared import http_get

KEEP = re.compile(r"(?i)^(adm\d_(name|name1|pcode|ref)|name|pcode|shapename|shapeid)$")


def say(line: str) -> None:
    print(line, flush=True)


def grid(geom, n: int) -> list[tuple[float, float]]:
    """About ``n`` points on a regular grid inside ``geom``; its representative
    point when the polygon is too thin for the grid to land in it."""
    from shapely.geometry import Point
    from shapely.prepared import prep

    minx, miny, maxx, maxy = geom.bounds
    if geom.area <= 0:
        return []
    step = math.sqrt(geom.area / max(n, 1))
    inside = prep(geom)
    points: list[tuple[float, float]] = []
    for _ in range(4):
        points = []
        x = minx + step / 2
        while x < maxx:
            y = miny + step / 2
            while y < maxy:
                if inside.contains(Point(x, y)):
                    points.append((x, y))
                y += step
            x += step
        if len(points) >= max(3, n // 2):
            break
        step /= 1.6
    if not points:
        p = geom.representative_point()
        points = [(p.x, p.y)]
    return points


def features(blob: bytes) -> list[tuple[str, dict[str, Any]]]:
    """(file name, FeatureCollection) for each GeoJSON in the zip or the blob."""
    if blob[:2] == b"PK":
        out = []
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for name in zf.namelist():
                if name.lower().endswith((".geojson", ".json")):
                    out.append((name, json.loads(zf.read(name))))
        return out
    return [("(body)", json.loads(blob))]


def probe_geo(url: str, n: int) -> None:
    from shapely.geometry import shape

    blob = http_get(url, binary=True, cache=False, timeout=300)
    assert isinstance(blob, bytes)
    say(f"== {url}: {len(blob):,} bytes")
    for name, collection in features(blob):
        feats = collection.get("features") or []
        say(f"-- {name}: {len(feats)} features")
        for f in feats:
            geom = f.get("geometry")
            if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
                continue
            props = {k: v for k, v in (f.get("properties") or {}).items()
                     if KEEP.match(k) and v not in (None, "")}
            g = shape(geom)
            pts = grid(g, n)
            say("F " + json.dumps(props, ensure_ascii=False, sort_keys=True))
            say("P " + ";".join(f"{x:.4f},{y:.4f}" for x, y in pts))


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for arg in argv:
        mode, _, rest = arg.partition(":")
        parts = rest.split("~~")
        if mode == "geo":
            probe_geo(parts[0], int(parts[1]) if len(parts) > 1 and parts[1] else 30)
        else:
            raise SystemExit(f"sahel_probe: unknown mode {mode!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
