#!/usr/bin/env python3
"""Build PMTiles vector-tile archives without tippecanoe.

``scripts/build_tiles.sh`` prefers tippecanoe + the ``pmtiles`` CLI when they
are installed -- that is the fast, battle-tested path.  This module is the
fallback so the pipeline still runs on a machine (or a CI runner) that has only
Python: it does the same job with shapely for clipping and
``mapbox_vector_tile`` for encoding, writing a spec-compliant PMTiles v3
archive.

Why tiles at all: the global CGAZ ADM2 layer is roughly 360 MB as GeoJSON with
~9 million coordinates.  No browser will take that as one download, so geometry
lives in tiles and attributes live in separate per-country JSON keyed by
shapeID.

Per-zoom simplification uses a tolerance of about one screen pixel at that
zoom, so a tile never carries detail the viewer cannot resolve, and features
whose on-screen area falls below a threshold are dropped rather than rendered
as a smudge -- the same trade-off tippecanoe's ``--drop-densest-as-needed``
makes.

Usage:
    python scripts/make_pmtiles.py data/raw/boundaries/geoBoundariesCGAZ_ADM1.gpkg \
        --layer admin1 --minzoom 0 --maxzoom 6 -o site/tiles/admin1.pmtiles
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import log  # noqa: E402

EXTENT = 4096          # MVT coordinate space per tile
BUFFER = 64            # tile-space buffer so strokes join across tile seams
WORLD = 20037508.342789244


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Web Mercator tile coordinates (fractional)."""
    lat = max(min(lat, 85.05112878), -85.05112878)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * n
    return x, y


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Tile bounds in degrees (west, south, east, north)."""
    n = 2.0 ** z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return west, south, east, north


def read_features(path: Path, layer: str | None, props: list[str]) -> list[dict[str, Any]]:
    import fiona
    from shapely.geometry import shape

    out: list[dict[str, Any]] = []
    with fiona.open(path, layer=layer) if layer else fiona.open(path) as src:
        for feat in src:
            geom = feat["geometry"]
            if geom is None:
                continue
            geometry = shape(geom)
            if geometry.is_empty:
                continue
            if not geometry.is_valid:
                geometry = geometry.buffer(0)
                if geometry.is_empty:
                    continue
            attrs = {k: v for k, v in dict(feat["properties"]).items()
                     if (not props or k in props) and v is not None}
            out.append({"geometry": geometry, "properties": attrs})
    return out


def simplify_for_zoom(geometry: Any, zoom: int) -> Any:
    """Douglas-Peucker at roughly one screen pixel for this zoom."""
    degrees_per_tile = 360.0 / (2 ** zoom)
    tolerance = degrees_per_tile / EXTENT * 2.0
    simple = geometry.simplify(tolerance, preserve_topology=True)
    if simple.is_empty:
        return geometry
    if not simple.is_valid:
        simple = simple.buffer(0)
    return simple if not simple.is_empty else geometry


def to_tile_space(geometry: Any, z: int, x: int, y: int) -> Any:
    """Map lon/lat to the tile's 0..EXTENT integer grid (y down)."""
    from shapely.ops import transform

    n = 2.0 ** z

    def project(lon: Any, lat: Any, _z: Any = None) -> tuple[Any, Any]:
        lat = max(min(lat, 85.05112878), -85.05112878)
        tx = (lon + 180.0) / 360.0 * n
        sin_lat = math.sin(math.radians(lat))
        ty = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * n
        return ((tx - x) * EXTENT, (ty - y) * EXTENT)

    return transform(project, geometry)


def _tiles_for_zoom(features: list[dict[str, Any]], layer_name: str, zoom: int,
                    maxzoom: int, min_area_px: float) -> dict[tuple[int, int, int], bytes]:
    """Encode every non-empty tile at one zoom level."""
    import mapbox_vector_tile
    from shapely.geometry import box

    started = time.time()
    n = 2 ** zoom
    # Dropping sub-pixel features keeps low zooms small without changing what
    # the viewer can actually see.
    min_area_deg = (360.0 / n / EXTENT) ** 2 * min_area_px * (EXTENT / 256.0) ** 2

    buckets: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for feature in features:
        geometry = simplify_for_zoom(feature["geometry"], zoom)
        if zoom < maxzoom and geometry.area < min_area_deg:
            continue
        west, south, east, north = geometry.bounds
        x0, y0 = lonlat_to_tile(west, north, zoom)
        x1, y1 = lonlat_to_tile(east, south, zoom)
        member = {"geometry": geometry, "bounds": (west, south, east, north),
                  "properties": feature["properties"]}
        for tx in range(max(0, int(x0)), min(n - 1, int(x1)) + 1):
            for ty in range(max(0, int(y0)), min(n - 1, int(y1)) + 1):
                buckets[(tx, ty)].append(member)

    out: dict[tuple[int, int, int], bytes] = {}
    for (tx, ty), members in buckets.items():
        west, south, east, north = tile_bounds(zoom, tx, ty)
        pad_x = (east - west) * BUFFER / EXTENT
        pad_y = (north - south) * BUFFER / EXTENT
        cw, cs, ce, cn = west - pad_x, south - pad_y, east + pad_x, north + pad_y
        clip = None
        encoded: list[dict[str, Any]] = []
        for member in members:
            mw, ms, me, mn = member["bounds"]
            if mw >= cw and ms >= cs and me <= ce and mn <= cn:
                # Wholly inside the tile: skip the intersection entirely. At
                # admin-2 zooms this is the common case and the main speed-up.
                piece = member["geometry"]
            else:
                if clip is None:
                    clip = box(cw, cs, ce, cn)
                try:
                    piece = member["geometry"].intersection(clip)
                except Exception:
                    piece = member["geometry"].buffer(0).intersection(clip)
            if piece.is_empty:
                continue
            local = to_tile_space(piece, zoom, tx, ty)
            if not local.is_valid:
                local = local.buffer(0)
            if local.is_empty:
                continue
            encoded.append({"geometry": local, "properties": member["properties"]})
        if not encoded:
            continue
        blob = mapbox_vector_tile.encode(
            {"name": layer_name, "features": encoded},
            default_options={
                "extents": EXTENT,
                # to_tile_space already emits MVT's y-down tile grid, so the
                # encoder must not flip it a second time.
                "y_coord_down": True,
                "check_winding_order": True,
                # Deliberately no on_invalid_geometry hook: the library's
                # make_it_valid collapses multi-part polygons to nothing, which
                # silently deleted Brazil, France and the USA. Geometry is
                # repaired with buffer(0) above instead.
            },
        )
        if blob:
            out[(zoom, tx, ty)] = gzip.compress(blob, 6)
    log(f"    z{zoom}: {len(out)} tiles ({time.time() - started:.1f}s)")
    return out


_WORKER_STATE: dict[str, Any] = {}


def _worker_init(features: list[dict[str, Any]], layer_name: str, maxzoom: int,
                 min_area_px: float) -> None:  # pragma: no cover - subprocess
    _WORKER_STATE.update(features=features, layer_name=layer_name,
                         maxzoom=maxzoom, min_area_px=min_area_px)


def _worker(zoom: int) -> dict[tuple[int, int, int], bytes]:  # pragma: no cover
    return _tiles_for_zoom(_WORKER_STATE["features"], _WORKER_STATE["layer_name"],
                           zoom, _WORKER_STATE["maxzoom"], _WORKER_STATE["min_area_px"])


def build_tiles(features: list[dict[str, Any]], layer_name: str, minzoom: int,
                maxzoom: int, min_area_px: float, jobs: int = 1
                ) -> dict[tuple[int, int, int], bytes]:
    """Tile every zoom in ``[minzoom, maxzoom]``.

    Zoom levels are independent, so with ``--jobs`` they run in forked workers
    that inherit the parsed geometry rather than re-reading or pickling it.
    """
    zooms = list(range(minzoom, maxzoom + 1))
    tiles: dict[tuple[int, int, int], bytes] = {}
    if jobs > 1 and len(zooms) > 1:
        import multiprocessing as mp

        ctx = mp.get_context("fork")
        with ctx.Pool(min(jobs, len(zooms)), initializer=_worker_init,
                      initargs=(features, layer_name, maxzoom, min_area_px)) as pool:
            for part in pool.imap_unordered(_worker, zooms):
                tiles.update(part)
        return tiles
    for zoom in zooms:
        tiles.update(_tiles_for_zoom(features, layer_name, zoom, maxzoom, min_area_px))
    return tiles


def write_archive(tiles: dict[tuple[int, int, int], bytes], dest: Path, *,
                  layer_name: str, minzoom: int, maxzoom: int,
                  fields: dict[str, str], attribution: str) -> None:
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer

    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as fh:
        writer = Writer(fh)
        # PMTiles requires tiles in tile-id (Hilbert) order.
        for (z, x, y) in sorted(tiles, key=lambda k: zxy_to_tileid(*k)):
            writer.write_tile(zxy_to_tileid(z, x, y), tiles[(z, x, y)])
        header = {
            "tile_type": TileType.MVT,
            "tile_compression": Compression.GZIP,
            "min_zoom": minzoom,
            "max_zoom": maxzoom,
            "min_lon_e7": int(-180 * 1e7), "min_lat_e7": int(-85.0 * 1e7),
            "max_lon_e7": int(180 * 1e7), "max_lat_e7": int(85.0 * 1e7),
            "center_zoom": minzoom,
            "center_lon_e7": 0, "center_lat_e7": int(20 * 1e7),
        }
        metadata = {
            "name": layer_name,
            "type": "overlay",
            "attribution": attribution,
            "vector_layers": [{
                "id": layer_name,
                "description": f"geoBoundaries {layer_name} boundaries",
                "minzoom": minzoom, "maxzoom": maxzoom,
                "fields": fields,
            }],
        }
        writer.finalize(header, metadata)
    log(f"  wrote {dest} ({dest.stat().st_size / 1e6:.1f} MB, {len(tiles)} tiles)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="GeoPackage or GeoJSON of polygons")
    ap.add_argument("--layer", required=True, help="vector-tile layer name (admin0/admin1/admin2)")
    ap.add_argument("--source-layer", default=None, help="layer name inside a GeoPackage")
    ap.add_argument("--minzoom", type=int, default=0)
    ap.add_argument("--maxzoom", type=int, default=6)
    ap.add_argument("--min-area-px", type=float, default=0.35,
                    help="drop features smaller than this many screen pixels squared")
    ap.add_argument("--properties", nargs="*", default=["shapeID", "shapeName", "shapeGroup"])
    ap.add_argument("--attribution",
                    default='<a href="https://www.geoboundaries.org/">geoBoundaries</a> CC BY 4.0')
    ap.add_argument("--jobs", type=int, default=1,
                    help="tile this many zoom levels in parallel (forked workers)")
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()

    log(f"make_pmtiles: {args.source.name} -> {args.out.name} (z{args.minzoom}-{args.maxzoom})")
    features = read_features(args.source, args.source_layer, args.properties)
    log(f"  {len(features)} features")
    tiles = build_tiles(features, args.layer, args.minzoom, args.maxzoom,
                        args.min_area_px, jobs=args.jobs)
    fields = {name: "String" for name in args.properties}
    write_archive(tiles, args.out, layer_name=args.layer, minzoom=args.minzoom,
                  maxzoom=args.maxzoom, fields=fields, attribution=args.attribution)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
