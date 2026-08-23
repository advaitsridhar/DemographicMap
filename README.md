# World Demographics Map

**Live map: https://advaitsridhar.github.io/DemographicMap/**

An interactive map of the world's administrative divisions — countries, first-level
divisions, second-level divisions — joined to population, religion, language and
ethnicity data, **and to an explicit record of where that data does not exist**.

Boundaries come from geoBoundaries, country demographics from the CIA World
Factbook, and subnational demographics from national statistical offices. The
whole thing is static: three PMTiles archives and a pile of small JSON files,
served by GitHub Pages with no tile server and no API keys.

```
git clone https://github.com/advaitsridhar/DemographicMap
cd DemographicMap
python3 scripts/serve.py          # http://127.0.0.1:8899
```

Use `scripts/serve.py` rather than `python3 -m http.server`: the stock server
ignores `Range` headers, and PMTiles reads tiles by byte range, so the map comes
up blank. Opening `site/index.html` over `file://` does not work either — the
browser blocks the data fetches.

## Deploying

Pushing to `main` runs `.github/workflows/pages.yml`, which validates the build
and publishes `site/` to GitHub Pages at `https://<owner>.github.io/DemographicMap/`
— for this repository, https://advaitsridhar.github.io/DemographicMap/.

**One-time setup.** Pages has to be switched on for the repository first, under
**Settings → Pages → Build and deployment → Source → GitHub Actions**. The
workflow does pass `enablement: true` to `actions/configure-pages`, which asks
the API to create the Pages site, but the default `GITHUB_TOKEN` is not
permitted to do so — it fails with `Create Pages site failed. Error: Resource
not accessible by integration`. Enabling it by hand once (or giving that step a
PAT with `repo` scope) is what unblocks it; every push after that deploys
unattended.

Any static host works, provided it sends `Access-Control-Allow-Origin`, honours
`Range` requests, and sets a long `Cache-Control` — those three are what the
PMTiles archives need.

---

## Why the gaps are the point

Demographic coverage is wildly asymmetric, and most demographic maps hide that by
painting an absence the same colour as a zero. This one refuses to. Every field is
one of three things:

| State | Meaning | Example |
|---|---|---|
| **Recorded** | A value, with a named source and a reference year. | Germany's religion shares, 2022. |
| **Not yet available** | The figure exists somewhere; this build has not fetched it. | Religion for US counties before you run the ACS/ARDA adapter. |
| **Not collected** | The country does not gather it at all. | France records neither ethnicity nor religion — *statistiques ethniques* are barred by law. |

The third category is an editorial commitment, not a shrug. It is asserted from a
hand-maintained policy table (`NOT_COLLECTED_POLICY` in `scripts/common.py`,
`COLLECTION_POLICY` in `scripts/fetch_census/eurostat.py`), never inferred from
an empty field, because "the source said nothing" and "the state asks nobody"
are different facts.

The marker propagates down every level: a question a national census does not
ask has no answer in that country's provinces or districts either, so
`apply_collection_policy` re-marks their `not_available` fields after the
adapters run — and only those, so a region that publishes what its national
census declines to ask keeps its real value. Countries covered:

- **France** collects neither ethnicity nor religion in its census.
- **Germany** records citizenship and migration background, not ethnicity; religion
  comes from church-tax registration rather than fine-grained census self-ID.
- **Japan** asks nationality, not ethnicity, and does not ask religion at all.
- **India** collects religion and mother tongue, plus Scheduled Caste / Scheduled
  Tribe status — but not ethnicity.
- **China** records the 56 official nationalities (*minzu*); the census does not ask
  religion.
- **The United States** census may not ask a mandatory religion question
  (13 U.S.C. 221(c)); the county-level substitute counts *adherents*, not self-ID.

### Percentages do not cross borders

US race, Brazilian *cor ou raça*, UK ethnic group, Australian ancestry, Chinese
*minzu* and Indonesian *suku* are different questions with different answer sets.
The app labels every composition with the classification it came from and never
compares them across a border. Neither should you.

---

## What is in this build

| Layer | Units | Geometry | Demographics |
|---|---|---|---|
| Countries (ADM0) | 218 mapped + 43 geometry-less dependencies | geoBoundaries CGAZ | CIA World Factbook: religion, language, ethnicity, population, median age, sex ratio, life expectancy, urbanisation; Natural Earth for largest settlement |
| First-level (ADM1) | 3,224 | geoBoundaries CGAZ | Largest settlement everywhere; census figures for the countries in `data/curated/admin1_seed.json`; everything else marked explicitly |
| Second-level (ADM2) | 49,349 | geoBoundaries CGAZ | Geometry and names only in this build — every adapter that would fill them is written and ready to run |

Country-level coverage as built: **218 of 260** Factbook entities have parsed
religion shares, **192** have ethnicity shares, and **13** are marked *not
collected* rather than blank.

Subnational demographics are sparse here on purpose. The adapters in
`scripts/fetch_census/` talk to `api.census.gov`, `nomisweb.co.uk`,
`www12.statcan.gc.ca`, `apisidra.ibge.gov.br`, `ec.europa.eu`, `data.api.abs.gov.au`
and `query.wikidata.org`; none of those hosts was reachable from the sandbox this
build ran in, so those fields ship as `not_available` with the exact command that
fills them shown in the app's "Filling this gap" panel. Run
`WITH_CENSUS=1 scripts/build_all.sh` on a machine with open egress and the map
fills in.

---

## Architecture

```
data/
├── raw/            # downloaded sources (gitignored — reproducible)
├── curated/        # hand-checked census rows, each with its own citation
└── processed/      # normalised per-source JSON
scripts/
├── common.py               # gap semantics, HTTP cache, Factbook text parsing
├── fetch_boundaries.py     # geoBoundaries CGAZ + per-country gbOpen
├── fetch_natural_earth.py  # code concordance + largest settlements
├── fetch_factbook.py       # country demographics
├── fetch_wikidata.py       # subnational population/capital via SPARQL
├── fetch_census/           # us_acs, uk_nomis, statcan, ibge_sidra, eurostat, abs, india_census
├── make_pmtiles.py         # pure-Python vector tiler (tippecanoe fallback)
├── build_tiles.sh          # tippecanoe + pmtiles, or make_pmtiles.py
├── simplify.sh             # mapshaper simplification for the GeoJSON path
├── build_entities.py       # the join: boundaries x attributes -> site/data
├── build_all.sh            # end-to-end
└── serve.py                # dev server with HTTP Range support
site/                       # the deployed static app
├── index.html
├── js/{palette,data,metrics,dashboard,search,map,app}.js
├── tiles/{admin0,admin1,admin2}.pmtiles
└── data/{admin0.json,admin1/*.json,admin2/*.json,search-index-*.json,coverage.json}
```

### Boundaries: geoBoundaries, not GADM

GADM covers ADM0–ADM5 globally and is **disqualified** for this project: its licence
permits academic and non-commercial use but forbids redistribution, which a public
repo cannot satisfy. geoBoundaries' gbOpen release is CC BY 4.0 and redistributable;
a few countries inherit ODbL or CC-BY-SA from OpenStreetMap, and
`fetch_boundaries.py` records each file's licence in its manifest. Natural Earth
(CC0) is used for admin-0/1 fallback geometry and for the code concordance.

The global CGAZ composite ships as GeoPackage (162 / 144 / 241 MB for ADM0 / ADM1 /
ADM2) rather than GeoJSON (401 / 361 / 550 MB) — same data, streamable, 2.5× smaller.
geoBoundaries' own caveat applies and is surfaced in the app: CGAZ simplifies
polygons, fills gaps along shared edges, and substitutes disputed areas using US
Department of State definitions. Fine for a demographics choropleth; not
authoritative for boundary disputes. The 19 disputed and special-status polygons it
carries (Abyei, Aksai Chin, the Senkakus, Gaza, the West Bank, …) are labelled as
such rather than counted as countries.

### Tiles: PMTiles, no tile server

The global ADM2 layer is ~360 MB of GeoJSON with roughly 9 million coordinates. No
browser takes that as one download, so geometry lives in vector tiles and attributes
live in separate per-country JSON keyed by `shapeID`.

`scripts/build_tiles.sh` prefers `tippecanoe` + the `pmtiles` CLI when they are
installed. When they are not — a bare CI runner, this build — it falls back to
`scripts/make_pmtiles.py`, a pure-Python tiler using shapely for clipping and
`mapbox_vector_tile` for encoding, which writes a spec-compliant PMTiles v3 archive.
Both paths emit the same layer names and property set.

| Archive | Zooms | Size | Tiles |
|---|---|---|---|
| `admin0.pmtiles` | z0–5 | ~2 MB | 988 |
| `admin1.pmtiles` | z0–7 | ~12 MB | 10,707 |
| `admin2.pmtiles` | z4–8 | ~48 MB | 38,797 |

MapLibre reads them over HTTP range requests, so GitHub Pages serving three static
files is the entire backend. Any host works provided it sends
`Access-Control-Allow-Origin`, honours `Range`, and sets a long `Cache-Control` —
which is why `scripts/serve.py` exists: Python's stock `http.server` ignores `Range`
and would hand the browser all 48 MB on every tile request.

### Lazy loading

`site/data/admin0.json` (~470 kB) loads with the page. Admin-1 attributes load per
country when that country enters the viewport or is selected; admin-2 attributes load
when an admin-1 unit is opened. The search index is sharded the same way: countries
and first-level divisions (~283 kB) load immediately, the 49k second-level divisions
(~4.6 MB) stream in behind them and merge when they land.

### No build step, no framework

`site/` is plain HTML, CSS and seven ES5-compatible scripts. The only dependencies
are vendored in `site/vendor/` (MapLibre GL JS, PMTiles, MiniSearch — 1.3 MB total,
all BSD/MIT) so the app runs behind a firewall and from `file://`. There is no
charting library: composition charts are a flex-box stacked bar plus a labelled
list, which keeps every value in the DOM for screen readers, find-in-page and
copy-paste.

### Colour

Three palettes, one job each, following the project's data-viz tokens in
`site/js/palette.js`:

- **Sequential** (one blue hue, light→dark) for every numeric choropleth.
- **Status** (reserved colours + icon + label) for present / not-yet-available /
  not-collected — so a gap never rests on hue alone.
- **Categorical** (eight fixed slots, never cycled) only in the sidebar composition
  charts, where every segment also carries a text label and a percentage.

There is deliberately **no "dominant religion" categorical choropleth**.
Colour-vision-safe separation across all pairs of an eight-hue set is not
achievable, and a map has no room for the direct labels that make the sidebar
charts safe. The same question is answered by faceting: pick one group and read
its share on a single sequential ramp ("Share of one group" in the Colour by
menu).

---

## Rebuilding

```bash
pip install -r requirements.txt

scripts/build_all.sh                  # boundaries + Factbook + Natural Earth + tiles + join
SKIP_TILES=1 scripts/build_all.sh     # attributes only (tiles take ~10 min)
WITH_CENSUS=1 scripts/build_all.sh    # also run the national statistics adapters
```

Individual steps:

```bash
python3 scripts/fetch_natural_earth.py                       # writes the code concordance first
python3 scripts/fetch_boundaries.py --cgaz --levels ADM0 ADM1 ADM2
python3 scripts/fetch_boundaries.py --countries priority --level ADM2   # per-country gbOpen
python3 scripts/fetch_factbook.py
python3 scripts/fetch_wikidata.py --level admin1
python3 -m scripts.fetch_census.us_acs --level county --religion-file data/raw/RCMSCY20.csv
scripts/build_tiles.sh admin1
python3 scripts/build_entities.py
```

`CENSUS_API_KEY` is optional for the US adapter (it lifts the 500 calls/day
anonymous cap). Nothing else needs credentials.

---

## Data sources

| Source | Licence | Used for |
|---|---|---|
| [geoBoundaries](https://www.geoboundaries.org/) gbOpen / CGAZ | CC BY 4.0 (some ODbL / CC-BY-SA per country) | All boundary geometry |
| [CIA World Factbook](https://www.cia.gov/the-world-factbook/) via [factbook.json](https://github.com/factbook/factbook.json) | Public domain / CC0 | Country religion, language, ethnicity, population, median age, sex ratio |
| [Natural Earth](https://www.naturalearthdata.com/) | Public domain (CC0) | GEC↔ISO concordance, largest settlements, fallback geometry |
| [Wikidata](https://www.wikidata.org/) | CC0 | Subnational population, capital, coordinates |
| [US Census ACS](https://www.census.gov/data/developers/data-sets/acs-5year.html) | Public domain | State/county race, ethnicity, language, median age |
| [2020 U.S. Religion Census](https://www.usreligioncensus.org/) (ASARB/ARDA) | See ARDA terms | County religion **adherence** |
| [ONS / Nomis](https://www.nomisweb.co.uk/) | Open Government Licence v3.0 | UK local-authority ethnicity and religion |
| [Statistics Canada](https://www12.statcan.gc.ca/) | StatCan Open Licence | Province / census-division religion, visible minority, language |
| [IBGE SIDRA](https://apisidra.ibge.gov.br/) | IBGE open data | Brazil state / municipality population, *cor ou raça*, religion |
| [Eurostat](https://ec.europa.eu/eurostat/) | Eurostat re-use policy | NUTS-2 / NUTS-3 population and median age |
| [ABS](https://data.api.abs.gov.au/) | CC BY 4.0 | Australian religion and ancestry |
| [Census of India 2011](https://censusindia.gov.in/) | GODL India | State / district religion, sex ratio, Scheduled Caste / Tribe |

Attribution for geoBoundaries, the Factbook and Natural Earth is shown on the map
itself, as CC BY requires.

---

## Known caveats

- **The Factbook is frozen.** It was retired in February 2026, so country figures are
  a snapshot. Every field carries its own reference year so the staleness is visible.
- **India's subnational data is from 2011.** The next census was postponed repeatedly.
- **Indonesia's ethnicity and religion data is from 2010** — the 2020 census dropped
  both questions.
- **The 2020 U.S. Religion Census counts adherents**, reported by 372 religious
  bodies covering about 48.6% of the population. It is not self-identification and
  does not sum to 100%.
- **Multi-response questions sum above 100%** (Australian ancestry, Canadian ethnic
  origin). The app says so on the panel rather than silently normalising.
- **`<1%` is an upper bound**, and is stored and rendered as one rather than being
  promoted to an exact share.
- **Some Factbook entities have no CGAZ outline** — Hong Kong, Macau, Puerto Rico,
  Palestine, the Channel Islands and 38 others are drawn as part of the state that
  administers them. They are kept as geometry-less records so their demographics are
  still searchable, with the missing outline stated.

## Licence

Code is MIT (`LICENSE`). Data keeps the licence of its source — see the table above
and `docs/SOURCES.md`. If you redistribute the boundary files, keep the geoBoundaries
attribution.
