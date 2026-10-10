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
  soft python3 -m scripts.fetch_census.afrobarometer_r8
  # The European Social Survey's open tabulation service, by NUTS region; no
  # account, and no microdata: it answers with weighted frequency tables.
  soft python3 -m scripts.fetch_census.ess_region --fetch
  soft python3 -m scripts.fetch_census.us_acs --level state
  soft python3 -m scripts.fetch_census.us_acs --level county
  soft python3 -m scripts.fetch_census.uk_nomis --level district
  # Shire England: geoBoundaries draws the county, ONS publishes the
  # districts below it, and Nomis publishes both. Without this, 150 rows
  # have no shape and the counties that do have one carry nothing.
  soft python3 -m scripts.fetch_census.uk_nomis --level county
  soft python3 -m scripts.fetch_census.uk_nomis --level nation
  soft python3 -m scripts.fetch_census.uk_mye
  # Reads three committed CSVs; no network, no key.
  soft python3 -m scripts.fetch_census.scotland_census
  # Likewise, three committed NISRA workbooks: the last of the UK shapes the
  # ONS census cannot reach.
  soft python3 -m scripts.fetch_census.northern_ireland
  # The Republic, from the CSO's PxStat. Needs the network; no key.
  soft python3 -m scripts.fetch_census.ireland
  soft python3 -m scripts.fetch_census.ireland_age
  # KNBS 2019 religion by county, from the openAFRICA mirror: knbs.or.ke
  # itself fails TLS verification on a clean client.
  soft python3 -m scripts.fetch_census.kenya
  # INE Angola's 12 MB final report; the tables are read from word coordinates.
  soft python3 -m scripts.fetch_census.angola
  # INSTAT Mali's RGPH5 thematic report (18 MB); annex tables read cell by cell.
  soft python3 -m scripts.fetch_census.mali
  # INEI's 2017 profile book (600 pages); read from word positions.
  soft python3 -m scripts.fetch_census.peru
  soft python3 -m scripts.fetch_census.zimbabwe
  soft python3 -m scripts.fetch_census.burkina
  # A survey, read from one page of the pollster's own report.
  soft python3 -m scripts.fetch_census.korea_survey
  # Korea's nationality as ethnicity, by the owner's decision: two register
  # files from data.go.kr, no key.
  soft python3 -m scripts.fetch_census.korea_nationality
  soft python3 -m scripts.fetch_census.korea_ages
  soft python3 -m scripts.fetch_census.korea_religion
  # Taiwan by the owner's decision: census main language read, ethnicity and
  # religion modelled; two DGBAS/Hakka PDFs and three MOI tables, no key.
  soft python3 -m scripts.fetch_census.taiwan
  soft python3 -m scripts.fetch_census.taiwan_townships
  # Japan by the owner's decision: census nationality read, religion and
  # language modelled; two e-Stat calls, needs ESTAT_API.
  soft python3 -m scripts.fetch_census.japan
  soft python3 -m scripts.fetch_census.japan_municipal
  # Five Chinese provinces from a survey, transcribed; no network.
  soft python3 -m scripts.fetch_census.cfps_survey
  # Its newer wave from the public-release file on Kaggle; needs egress.
  soft python3 -m scripts.fetch_census.cfps_microdata
  # Macau's 2021 census: nationality and usual language from DSEC's
  # Detailed Results PDF; needs egress.
  soft python3 -m scripts.fetch_census.macau_census
  # Viet Nam's 2019 census, Table 2 of the office's 842-page results
  # volume on nso.gov.vn; needs egress.
  soft python3 -m scripts.fetch_census.vietnam
  # Hong Kong's 2021 census: ethnicity and usual spoken language from the
  # C&SD Main Results workbook; needs egress.
  soft python3 -m scripts.fetch_census.hongkong_census
  # Timor-Leste: mother tongue and religion by municipality from the 2015
  # census's Volume 2 priority tables, population by municipality and
  # administrative post from the 2022 main report; three files from
  # inetl-ip.gov.tl, needs egress.
  soft python3 -m scripts.fetch_census.timor
  # Laos: the 2015 census's 8,500-village indicator table from Open
  # Development Laos, summed to 18 provinces and 148 districts; one 4.5 MB
  # workbook, needs egress.
  soft python3 -m scripts.fetch_census.laos --level both
  # Mongolia: ethnic group and religion for the 22 aimags and ethnic group for
  # the soums, from the 2020 census's national report and the 22 aimag results
  # books. The books are read from the Internet Archive by --fetch, which needs
  # egress and 300 MB of PDF; the adapter itself reads the text files --fetch
  # left in data/raw/mongolia and needs nothing.
  soft python3 -m scripts.fetch_census.mongolia
  soft python3 -m scripts.fetch_census.mongolia_ages
  # North Korea: the 2008 census's Table 2, population and sex ratio for the
  # 11 first-level units and all 179 counties, read from the UN Statistics
  # Division's copy of the CBS National Report; one 1.4 MB PDF, needs egress.
  soft python3 -m scripts.fetch_census.northkorea
  # Census ethnicity for the 31 divisions, one MediaWiki API call each.
  soft python3 -m scripts.fetch_census.china_wiki
  soft python3 -m scripts.fetch_census.china_census
  soft python3 -m scripts.fetch_census.china_county_census
  # One MediaWiki API call; the NSO's own hosts refuse automated readers.
  soft python3 -m scripts.fetch_census.thailand
  # Thailand's ethnicity by the owner's decision: modelled from the same
  # article's home-language cells and a regional assignment; two API calls.
  soft python3 -m scripts.fetch_census.thailand_ethnicity
  soft python3 -m scripts.fetch_census.thailand_nationality
  # Papua New Guinea: two NSO PDFs, the 2024 census Final Figures (8 MB) and
  # the 2011 National Report (12 MB), read with pypdf.
  soft python3 -m scripts.fetch_census.png
  # The Pacific offices' own census tables, a few PDFs or workbooks each (some
  # through the Internet Archive); nothing is read from data/raw.
  soft python3 -m scripts.fetch_census.fiji_census
  soft python3 -m scripts.fetch_census.solomon_census
  soft python3 -m scripts.fetch_census.vanuatu_census
  soft python3 -m scripts.fetch_census.samoa_census
  soft python3 -m scripts.fetch_census.tonga_census
  soft python3 -m scripts.fetch_census.kiribati_census
  soft python3 -m scripts.fetch_census.marshall_census
  soft python3 -m scripts.fetch_census.tuvalu_census
  soft python3 -m scripts.fetch_census.micronesia_census
  soft python3 -m scripts.fetch_census.nauru_census
  soft python3 -m scripts.fetch_census.palau_census
  # Census tables that reach us only as Wikipedia transcriptions (KAZ, KHM).
  soft python3 -m scripts.fetch_census.wiki_census
  # Reads the committed BNS workbook under data/raw/kazakhstan; no network.
  soft python3 -m scripts.fetch_census.kazakhstan
  soft python3 -m scripts.fetch_census.kazakhstan_census
  soft python3 -m scripts.fetch_census.kazakhstan_religion
  soft python3 -m scripts.fetch_census.iran_census
  soft python3 -m scripts.fetch_census.iran_ali
  soft python3 -m scripts.fetch_census.uzbekistan_siat
  soft python3 -m scripts.fetch_census.uzbekistan_census
  soft python3 -m scripts.fetch_census.kyrgyzstan_census
  soft python3 -m scripts.fetch_census.tajikistan_census
  soft python3 -m scripts.fetch_census.turkmenistan_census
  soft python3 -m scripts.fetch_census.malaysia --level both
  # One DOSM dashboard parquet (religion, 2020 census) plus the two population
  # CSVs above for the count base; needs pyarrow.
  soft python3 -m scripts.fetch_census.malaysia_religion
  # Brunei: one DEPS workbook, the BPP 2021 census annexes. Race and religion
  # for the four districts, a head count for the 38 mukims; needs openpyxl.
  soft python3 -m scripts.fetch_census.brunei
  soft python3 -m scripts.fetch_census.indonesia_age
  # Indonesia: 2010 census ethnicity by province and registry/BPS religion by
  # province and regency, read from the Indonesian Wikipedia (~550 API calls).
  soft python3 -m scripts.fetch_census.indonesia
  soft python3 -m scripts.fetch_census.vietnam_district
  soft python3 -m scripts.fetch_census.vietnam_religion
  soft python3 -m scripts.fetch_census.timor_age
  soft python3 -m scripts.fetch_census.timor_nationality
  soft python3 -m scripts.fetch_census.myanmar_age
  soft python3 -m scripts.fetch_census.philippines_age
  soft python3 -m scripts.fetch_census.sea_composed
  soft python3 -m scripts.fetch_census.singapore_age
  soft python3 -m scripts.fetch_census.cambodia_census
  soft python3 -m scripts.fetch_census.sea_cod_ps_age
  # held: soft python3 -m scripts.fetch_census.indonesia_language
  soft python3 -m scripts.fetch_census.poland
  # Three ČSÚ open-data CSVs, 170 MB between them; no key.
  soft python3 -m scripts.fetch_census.czechia
  # One 18 MB DZS workbook; no key.
  soft python3 -m scripts.fetch_census.croatia
  soft python3 -m scripts.fetch_census.romania
  # Three small BHAS workbooks; no key.
  soft python3 -m scripts.fetch_census.bosnia
  soft python3 -m scripts.fetch_census.statcan
  soft python3 -m scripts.fetch_census.ibge_sidra --level state
  # 5,570 municipalities, and the reason the level is spelled out twice:
  # brazil_municipality.json was registered as an adapter file long before
  # anything here wrote it, so the join would have read whatever the last
  # manual run left behind and aged it silently. A file the build consumes
  # and never refreshes is worse than one it does not have.
  soft python3 -m scripts.fetch_census.ibge_sidra --level municipality
  soft python3 -m scripts.fetch_census.eurostat --level nuts1
  soft python3 -m scripts.fetch_census.eurostat --level nuts2
  soft python3 -m scripts.fetch_census.eurostat --level nuts3
  # Europe from its own statistics offices, below the level Eurostat reaches:
  # the PxWeb registers, then each office's reader. Several read the drawn
  # units' vintage rather than today's (Estonia 2017, Norway 2017-2019,
  # Iceland 2017, Switzerland's 2009 districts) and pin a year so a re-run
  # reproduces what was checked.
  soft python3 -m scripts.fetch_census.pxweb --country EST
  soft python3 -m scripts.fetch_census.pxweb --country LVA
  soft python3 -m scripts.fetch_census.pxweb --country FIN
  soft python3 -m scripts.fetch_census.estonia
  soft python3 -m scripts.fetch_census.latvia
  soft python3 -m scripts.fetch_census.finland
  soft python3 -m scripts.fetch_census.finland_religion
  soft python3 -m scripts.fetch_census.lithuania
  soft python3 -m scripts.fetch_census.sweden
  soft python3 -m scripts.fetch_census.nordic_church --country SWE
  soft python3 -m scripts.fetch_census.norway
  soft python3 -m scripts.fetch_census.denmark
  soft python3 -m scripts.fetch_census.iceland
  soft python3 -m scripts.fetch_census.austria --year 2026
  soft python3 -m scripts.fetch_census.austria_census
  soft python3 -m scripts.fetch_census.austria_religion
  soft python3 -m scripts.fetch_census.liechtenstein --year 2025
  soft python3 -m scripts.fetch_census.switzerland_ages --year 2025
  soft python3 -m scripts.fetch_census.switzerland_census
  soft python3 -m scripts.fetch_census.switzerland_religion
  soft python3 -m scripts.fetch_census.poland_ages
  soft python3 -m scripts.fetch_census.czechia_ages --year 2024
  soft python3 -m scripts.fetch_census.slovakia_census
  soft python3 -m scripts.fetch_census.slovakia --year 2025
  soft python3 -m scripts.fetch_census.hungary
  soft python3 -m scripts.fetch_census.slovenia --half 2026H1
  soft python3 -m scripts.fetch_census.slovenia_census
  soft python3 -m scripts.fetch_census.netherlands_gemeente
  soft python3 -m scripts.fetch_census.netherlands_religion
  soft python3 -m scripts.fetch_census.netherlands_religion_gemeente
  soft python3 -m scripts.fetch_census.luxembourg
  soft python3 -m scripts.fetch_census.austria_nationality
  soft python3 -m scripts.fetch_census.switzerland_nationality
  soft python3 -m scripts.fetch_census.belgium_nationality
  soft python3 -m scripts.fetch_census.luxembourg_nationality
  soft python3 -m scripts.fetch_census.nordic_origin --country SWE
  soft python3 -m scripts.fetch_census.nordic_origin --country NOR
  soft python3 -m scripts.fetch_census.nordic_origin --country DNK
  soft python3 -m scripts.fetch_census.nordic_origin --country ISL
  soft python3 -m scripts.fetch_census.romania_census
  soft python3 -m scripts.fetch_census.bulgaria_census
  soft python3 -m scripts.fetch_census.serbia_census
  soft python3 -m scripts.fetch_census.montenegro
  soft python3 -m scripts.fetch_census.north_macedonia
  soft python3 -m scripts.fetch_census.north_macedonia_2002
  soft python3 -m scripts.fetch_census.kosovo
  soft python3 -m scripts.fetch_census.albania_census
  soft python3 -m scripts.fetch_census.cyprus_census
  soft python3 -m scripts.fetch_census.cyprus_north_census
  soft python3 -m scripts.fetch_census.moldova_age
  soft python3 -m scripts.fetch_census.greece_age
  soft python3 -m scripts.fetch_census.bucharest_sectors
  soft python3 -m scripts.fetch_census.bosnia_age
  soft python3 -m scripts.fetch_census.spain_italy_age
  soft python3 -m scripts.fetch_census.portugal_census
  soft python3 -m scripts.fetch_census.malta_census
  soft python3 -m scripts.fetch_census.basque_language
  soft python3 -m scripts.fetch_census.microstates
  soft python3 -m scripts.fetch_census.italy_language_survey
  soft python3 -m scripts.fetch_census.spain_language_survey
  soft python3 -m scripts.fetch_census.spain_cis
  soft python3 -m scripts.fetch_census.catalonia_ceo
  # The ABS publishes 2021-census religion/ancestry by LGA, SA2, postal area
  # and similar -- there is no state-level dataflow (see the G14 catalogue
  # listing in run 32566750604). LGAs join the admin-2 layer.
  soft python3 -m scripts.fetch_census.abs --level lga
  # The ABS Data API's 2021 G01/G02/G08 by LGA and SA2+, G13/G14 by state:
  # medians, sex ratios, ancestry, and the states' own counts and compositions.
  soft python3 -m scripts.fetch_census.australia_profile
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
  # South Asia's later readers, each after the file it reads: the India
  # readers check against the C-01 shapes india_census writes,
  # pakistan_census_tables against pakistan_district.json (pakistan),
  # bangladesh_zila_ages against bangladesh_district.json (bangladesh), and
  # afghanistan_sdes takes each figure's size from afghanistan_estimates.
  # afghanistan reads the district development plans' ethnic shares as the
  # provinces' articles transcribe them, afghanistan_ddp the plans' own PDFs
  # in the Internet Archive (and compares the two, so it runs after).
  soft python3 -m scripts.fetch_census.india_ages
  soft python3 -m scripts.fetch_census.india_birthplace
  soft python3 -m scripts.fetch_census.pakistan_census_tables
  soft python3 -m scripts.fetch_census.bangladesh_zila_ages
  soft python3 -m scripts.fetch_census.bhutan
  soft python3 -m scripts.fetch_census.maldives_census
  soft python3 -m scripts.fetch_census.afghanistan
  soft python3 -m scripts.fetch_census.afghanistan_ddp
  soft python3 -m scripts.fetch_census.afghanistan_estimates
  soft python3 -m scripts.fetch_census.afghanistan_sdes
  soft python3 -m scripts.fetch_census.new_zealand
  # One reader, every country in the U.S. Census Bureau's subnational series:
  # the Philippines (2020 census) and Ethiopia (2007, the last it completed).
  soft python3 -m scripts.fetch_census.uscb
  # Rosstat's own host serves a certificate signed by a state CA no
  # ordinary trust store carries, so this reads the same files from a
  # public archive and the citation says which capture.
  soft python3 -m scripts.fetch_census.russia
  soft python3 -m scripts.fetch_census.russia_municipal
  soft python3 -m scripts.fetch_census.russia_religion
  soft python3 -m scripts.fetch_census.ukraine_raion
  soft python3 -m scripts.fetch_census.belarus
  soft python3 -m scripts.fetch_census.georgia
  soft python3 -m scripts.fetch_census.armenia
  soft python3 -m scripts.fetch_census.armenia_2011
  soft python3 -m scripts.fetch_census.azerbaijan
  soft python3 -m scripts.fetch_census.turkey_districts
  # Needs ZENSUS_USER and ZENSUS_PASSWORD. Without them the adapter
  # refuses outright rather than fetching a 401 and reporting it as a
  # table that went away -- soft, so a refresh without the account
  # skips Germany instead of failing the run.
  soft python3 -m scripts.fetch_census.germany --level land
  soft python3 -m scripts.fetch_census.germany --level regierungsbezirk
  soft python3 -m scripts.fetch_census.iraq_census --offline
  soft python3 -m scripts.fetch_census.syria_census
  soft python3 -m scripts.fetch_census.yemen_census
  soft python3 -m scripts.fetch_census.bahrain_census
  soft python3 -m scripts.fetch_census.saudi_census
  soft python3 -m scripts.fetch_census.qatar_census
  soft python3 -m scripts.fetch_census.kuwait_census
  soft python3 -m scripts.fetch_census.israel_cbs
  soft python3 -m scripts.fetch_census.jordan_dos
  soft python3 -m scripts.fetch_census.oman_ncsi
  soft python3 -m scripts.fetch_census.lebanon_survey
  soft python3 -m scripts.fetch_census.uae_scad
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
