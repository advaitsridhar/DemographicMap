#!/usr/bin/env bash
# End-to-end build: sources -> attributes -> tiles -> site/.
#
# Steps that need network access to a blocked host fail loudly and are skipped,
# so a partial environment still produces a working site with the gaps marked.
#
# Usage:
#   scripts/build_all.sh                 # boundaries + Factbook + Natural Earth + tiles
#   SKIP_TILES=1 scripts/build_all.sh    # attributes only (tiles are slow)
#   WITH_CENSUS=1 scripts/build_all.sh   # also run the national statistics adapters
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
soft() {
  # Run a step that depends on an external API. A failure is reported and the
  # build continues -- the affected fields simply stay marked "not available".
  if ! "$@"; then
    printf '\033[33m    skipped (source unreachable): %s\033[0m\n' "$*" >&2
  fi
}

step "Natural Earth (code concordance + largest settlements)"
python3 scripts/fetch_natural_earth.py

step "geoBoundaries CGAZ (ADM0/ADM1/ADM2)"
python3 scripts/fetch_boundaries.py --cgaz --levels ADM0 ADM1 ADM2

step "CIA World Factbook country profiles"
python3 scripts/fetch_factbook.py

step "Wikidata subnational attributes"
soft python3 scripts/fetch_wikidata.py --level admin1

# Admin-2 from Wikidata, for countries whose second-level demographics no
# statistical adapter reaches. India is the motivating case: its 735 districts
# have no API at all (the 2011 census ships as per-state workbooks), so
# Wikidata's population and headquarters statements are the only structured
# district-level data available. One SPARQL query per country, so the list is
# deliberately short rather than global.
WIKIDATA_ADMIN2="${WIKIDATA_ADMIN2:-IND IDN PHL VNM THA PAK BGD NGA ETH KEN MEX COL PER ARG}"
soft python3 scripts/fetch_wikidata.py --level admin2 --countries $WIKIDATA_ADMIN2

if [ "${WITH_CENSUS:-0}" = "1" ]; then
  step "National statistical offices"
  soft python3 -m scripts.fetch_census.us_acs --level state
  soft python3 -m scripts.fetch_census.us_acs --level county
  soft python3 -m scripts.fetch_census.uk_nomis
  soft python3 -m scripts.fetch_census.statcan --level province
  soft python3 -m scripts.fetch_census.ibge_sidra --level state
  soft python3 -m scripts.fetch_census.eurostat --level nuts2
  # The ABS publishes 2021-census religion/ancestry by LGA, SA2, postal area
  # and similar -- there is no state-level dataflow (see the G14 catalogue
  # listing in run 32566750604). LGAs join the admin-2 layer.
  soft python3 -m scripts.fetch_census.abs --level lga
  # India has no statistics API; this reads a validated district-level extract
  # of the 2011 census and aggregates it to states.
  soft python3 -m scripts.fetch_census.india_census --level state
  soft python3 -m scripts.fetch_census.india_census --level district
  # Mother tongue (C-16) ships as its own per-state workbooks, checked into
  # data/raw/india/c16/. No network: these read from disk, so they run
  # unconditionally rather than through soft().
  # Sri Lanka's 2012 census tables are workbooks too, read from disk.
  soft python3 -m scripts.fetch_census.sri_lanka --level province
  soft python3 -m scripts.fetch_census.sri_lanka --level district
  soft python3 -m scripts.fetch_census.india_language --level state
  soft python3 -m scripts.fetch_census.india_language --level district
fi

if [ "${SKIP_TILES:-0}" != "1" ]; then
  step "Vector tiles"
  scripts/build_tiles.sh
fi

step "Join boundaries and attributes into site/data"
python3 scripts/build_entities.py

step "Done"
du -sh site/data site/tiles 2>/dev/null || true
echo "Serve locally with: python3 scripts/serve.py"
