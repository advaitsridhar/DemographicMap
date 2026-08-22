#!/usr/bin/env bash
# Clean and simplify boundary GeoJSON with mapshaper.
#
# Only needed for the GeoJSON/TopoJSON delivery path (the admin-0/admin-1
# fallback the app uses when PMTiles are unavailable). The PMTiles path
# simplifies per zoom level inside the tiler instead, which is strictly better
# because each zoom gets a tolerance matched to its own pixel size.
#
# Usage:
#   scripts/simplify.sh data/raw/boundaries/adm1.geojson site/data/geo/adm1.json 5%
set -euo pipefail

SRC="${1:?usage: simplify.sh <input> <output> [percentage]}"
DEST="${2:?usage: simplify.sh <input> <output> [percentage]}"
PCT="${3:-5%}"

command -v mapshaper >/dev/null || {
  echo "mapshaper not found. Install with: npm install -g mapshaper" >&2
  exit 1
}

mkdir -p "$(dirname "$DEST")"

# -simplify uses weighted Visvalingam by default; keep-shapes stops small
# polygons (island states, city districts) from vanishing entirely.
# precision=0.00001 is about 1 m at the equator, well below what the map draws.
case "$DEST" in
  *.topojson|*.topo.json)
    # TopoJSON stores each shared border once, so it lands 60-80% smaller than
    # the equivalent GeoJSON. quantization trades sub-metre precision for size.
    mapshaper "$SRC" \
      -simplify "$PCT" keep-shapes \
      -clean \
      -o "$DEST" format=topojson quantization=1e5 precision=0.00001
    ;;
  *)
    mapshaper "$SRC" \
      -simplify "$PCT" keep-shapes \
      -clean \
      -o "$DEST" format=geojson precision=0.00001
    ;;
esac

ls -lh "$DEST" | awk '{print $9 "  " $5}'
