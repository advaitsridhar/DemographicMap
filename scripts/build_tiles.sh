#!/usr/bin/env bash
# Build the three PMTiles archives the map reads.
#
# Prefers tippecanoe + the pmtiles CLI when they are installed; falls back to
# scripts/make_pmtiles.py (pure Python) otherwise, so the pipeline runs on a
# bare CI runner. Both paths produce the same layer names and property set:
#   layer admin0 / admin1 / admin2, properties shapeID, shapeName, shapeGroup.
#
# Usage:
#   scripts/build_tiles.sh                # all three levels
#   scripts/build_tiles.sh admin1 admin2  # a subset
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW="$ROOT/data/raw/boundaries"
OUT="$ROOT/site/tiles"
JOBS="${JOBS:-$( (command -v nproc >/dev/null && nproc) || echo 4)}"
ATTRIBUTION='<a href="https://www.geoboundaries.org/">geoBoundaries</a> CC BY 4.0'

mkdir -p "$OUT"

# level -> minzoom maxzoom.  Each layer is only tiled over the range at which it
# is actually drawn, which is what keeps the archives small:
#   admin0 z0-5, admin1 z0-7, admin2 z2-8.
zooms() {
  case "$1" in
    admin0) echo "0 5" ;;
    admin1) echo "0 7" ;;
    # z8 keeps the archive around 25 MB with ~76 m of simplification tolerance,
    # which MapLibre overzooms cleanly past z8. Raise to 9 for ~38 m and ~80 MB.
    # From z2, not z4: the app lets a viewer pin the map to second-level
    # divisions at world view, and a level with no tiles there shows ocean.
    admin2) echo "2 8" ;;
    *) echo "0 6" ;;
  esac
}

have_tippecanoe() { command -v tippecanoe >/dev/null && command -v pmtiles >/dev/null; }

build_with_tippecanoe() {
  local level="$1" src="$2" minz="$3" maxz="$4" dest="$5"
  local geojson="$RAW/${level}.geojson"
  if [ ! -f "$geojson" ]; then
    command -v ogr2ogr >/dev/null || { echo "need ogr2ogr to convert $src"; return 1; }
    echo "  ogr2ogr -> $(basename "$geojson")"
    ogr2ogr -f GeoJSONSeq "$geojson" "$src"
  fi
  # --drop-densest-as-needed is what keeps dense admin-2 areas under the tile
  # size limit instead of failing the build.
  tippecanoe \
    --layer="$level" \
    --minimum-zoom="$minz" --maximum-zoom="$maxz" \
    --drop-densest-as-needed --coalesce-densest-as-needed \
    --simplification=4 --detect-shared-borders \
    --no-tile-compression=false \
    --attribution="$ATTRIBUTION" \
    --force --output="${dest%.pmtiles}.mbtiles" \
    "$geojson"
  pmtiles convert "${dest%.pmtiles}.mbtiles" "$dest"
  rm -f "${dest%.pmtiles}.mbtiles"
}

build_with_python() {
  local level="$1" src="$2" minz="$3" maxz="$4" dest="$5"
  python3 "$ROOT/scripts/make_pmtiles.py" "$src" \
    --layer "$level" --minzoom "$minz" --maxzoom "$maxz" \
    --jobs "$JOBS" --attribution "$ATTRIBUTION" -o "$dest"
}

levels=("$@")
[ ${#levels[@]} -eq 0 ] && levels=(admin0 admin1 admin2)

for level in "${levels[@]}"; do
  case "$level" in
    admin0) src="$RAW/geoBoundariesCGAZ_ADM0.gpkg" ;;
    admin1) src="$RAW/geoBoundariesCGAZ_ADM1.gpkg" ;;
    admin2) src="$RAW/geoBoundariesCGAZ_ADM2.gpkg" ;;
    *) echo "unknown level: $level" >&2; exit 2 ;;
  esac
  [ -f "$src" ] || { echo "missing $src -- run scripts/fetch_boundaries.py --cgaz" >&2; exit 1; }

  read -r minz maxz <<<"$(zooms "$level")"
  dest="$OUT/$level.pmtiles"
  echo "==> $level (z$minz-$maxz) -> $(basename "$dest")"
  if have_tippecanoe; then
    build_with_tippecanoe "$level" "$src" "$minz" "$maxz" "$dest"
  else
    echo "  tippecanoe/pmtiles not found; using the Python tiler"
    build_with_python "$level" "$src" "$minz" "$maxz" "$dest"
  fi
  ls -lh "$dest" | awk '{print "  " $9 "  " $5}'
done

# GitHub blocks pushes of files over 100 MB, and the map streams these over HTTP
# range requests, so an oversized archive is a build error rather than a warning.
for f in "$OUT"/*.pmtiles; do
  size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f")
  if [ "$size" -gt 94371840 ]; then
    echo "ERROR: $(basename "$f") is $((size / 1048576)) MB (>90 MB)." >&2
    echo "       Lower the max zoom or raise --min-area-px in scripts/make_pmtiles.py." >&2
    exit 1
  fi
done
echo "tiles OK"
