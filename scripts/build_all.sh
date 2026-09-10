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
  # Race, language and age come from the ACS API; religion cannot, because the
  # census is barred from asking. It is read from the 2020 U.S. Religion Census
  # workbook in data/raw/us/, picked up automatically when present.
  # Reads a committed extract rather than the network, so it needs no key
  # and cannot fail on an unreachable host -- but it is still an adapter
  # and its output belongs in data/processed with the rest.
  soft python3 -m scripts.fetch_census.afrobarometer
  soft python3 -m scripts.fetch_census.us_acs --level state
  soft python3 -m scripts.fetch_census.us_acs --level county
  soft python3 -m scripts.fetch_census.uk_nomis --level district
  # Shire England: geoBoundaries draws the county, ONS publishes the
  # districts below it, and Nomis publishes both. Without this, 150 rows
  # have no shape and the counties that do have one carry nothing.
  soft python3 -m scripts.fetch_census.uk_nomis --level county
  # Reads three committed CSVs; no network, no key.
  soft python3 -m scripts.fetch_census.scotland_census
  # Likewise, three committed NISRA workbooks: the last of the UK shapes the
  # ONS census cannot reach.
  soft python3 -m scripts.fetch_census.northern_ireland
  # The Republic, from the CSO's PxStat. Needs the network; no key.
  soft python3 -m scripts.fetch_census.ireland
  # KNBS 2019 religion by county, from the openAFRICA mirror: knbs.or.ke
  # itself fails TLS verification on a clean client.
  soft python3 -m scripts.fetch_census.kenya
  soft python3 -m scripts.fetch_census.malaysia --level both
  soft python3 -m scripts.fetch_census.poland
  soft python3 -m scripts.fetch_census.statcan
  soft python3 -m scripts.fetch_census.ibge_sidra --level state
  # 5,570 municipalities, and the reason the level is spelled out twice:
  # brazil_municipality.json was registered as an adapter file long before
  # anything here wrote it, so the join would have read whatever the last
  # manual run left behind and aged it silently. A file the build consumes
  # and never refreshes is worse than one it does not have.
  soft python3 -m scripts.fetch_census.ibge_sidra --level municipality
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
  # Singapore, via the SingStat Table Builder API.
  # Mexico's ITER is a 36 MB download read straight from INEGI; too large to
  # check in, and the only file that carries religion, indigenous language and
  # Afro-descendant identity for all 2,470 municipios at once.
  soft python3 -m scripts.fetch_census.mexico --level state
  soft python3 -m scripts.fetch_census.mexico --level municipality
  soft python3 -m scripts.fetch_census.switzerland
  soft python3 -m scripts.fetch_census.singstat
  soft python3 -m scripts.fetch_census.singapore_areas
  # Sri Lanka's 2024 census tables are workbooks too, read from disk.
  soft python3 -m scripts.fetch_census.sri_lanka --level province
  soft python3 -m scripts.fetch_census.sri_lanka --level district
  soft python3 -m scripts.fetch_census.india_language --level state
  soft python3 -m scripts.fetch_census.india_language --level district
  # Five adapters were missing from this list for as long as they have
  # existed. Their output is committed under data/processed, so the join
  # still picked it up and the countries appeared on the map -- which is
  # exactly why nobody noticed. What a refresh could not do was re-run them,
  # so a census revision or a fix to one of these readers would never have
  # reached the site until someone dispatched the adapter by hand.
  #
  # Nepal reads a 13 MB report checked into data/raw/nepal/, so it needs no
  # network and runs unconditionally. New Zealand needs a Stats NZ key from
  # the environment and soft-fails without one.
  soft python3 -m scripts.fetch_census.pakistan
  soft python3 -m scripts.fetch_census.bangladesh
  soft python3 -m scripts.fetch_census.south_africa
  soft python3 -m scripts.fetch_census.nepal
  soft python3 -m scripts.fetch_census.new_zealand
  # One reader, every country in the U.S. Census Bureau's subnational series:
  # the Philippines (2020 census) and Ethiopia (2007, the last it completed).
  soft python3 -m scripts.fetch_census.uscb
  # Rosstat's own host serves a certificate signed by a state CA no
  # ordinary trust store carries, so this reads the same files from a
  # public archive and the citation says which capture.
  soft python3 -m scripts.fetch_census.russia
  # Needs ZENSUS_USER and ZENSUS_PASSWORD. Without them the adapter
  # refuses outright rather than fetching a 401 and reporting it as a
  # table that went away -- soft, so a refresh without the account
  # skips Germany instead of failing the run.
  soft python3 -m scripts.fetch_census.germany --level land
  soft python3 -m scripts.fetch_census.germany --level regierungsbezirk
fi

if [ "${SKIP_TILES:-0}" != "1" ]; then
  step "Vector tiles"
  scripts/build_tiles.sh || exit 1
fi

step "Join boundaries and attributes into site/data"
# Explicitly fatal. This script deliberately runs without "set -e" so that an
# adapter behind a blocked host can be skipped and still leave a working site
# -- but that also meant a crash *here* was survivable, and this is the step
# whose whole job is to produce site/data. One did crash: the quarterly
# refresh ran every adapter, died joining them, left the previous build's
# site/data untouched, exited 0 from the echo at the bottom, and opened a data
# PR reporting success. Russia's 83 subjects were in data/processed and absent
# from the map, which is the failure this project cares about most -- not a
# wrong answer, a missing one that nothing announced.
python3 scripts/build_entities.py || exit 1

# Runs here rather than in checks.yml because it needs the CGAZ boundary files
# (~550 MB, not in git), which only the full pipeline has fetched. It reports
# and never fails the build: a new adapter is allowed to introduce a rivalry,
# and the point is that somebody sees it.
step "Audit rival claims on the same shape"
python3 scripts/audit_claims.py

step "Done"
du -sh site/data site/tiles 2>/dev/null || true
echo "Serve locally with: python3 scripts/serve.py"
