# Sources, licences and collection policy

## Boundaries

### geoBoundaries (primary)

- **Licence:** gbOpen is CC BY 4.0. Some countries inherit ODbL or CC-BY-SA where the
  boundary was sourced from OpenStreetMap (Pakistan ADM1 is the usual example), so
  `scripts/fetch_boundaries.py` records `boundaryLicense` per file in
  `data/raw/boundaries/manifest.json`. Check it before redistributing a subset.
- **Attribution:** required, and shown on the map.
- **Coverage:** 199 entities including all 195 UN member states, plus Greenland,
  Taiwan, Niue and Kosovo.
- **Products used:** `CGAZ` global composites for the three shipped layers; `gbOpen`
  per-country files (`--countries`) for adding admin-2 country by country.
- **Access:** the API at `https://www.geoboundaries.org/api/current/gbOpen/{ISO3}/{ADM}/`
  returns a JSON record with `gjDownloadURL`. Release data lives in Git LFS, so
  `raw.githubusercontent.com` returns a 130-byte pointer file rather than the object;
  `media.githubusercontent.com/media/...` serves the real bytes. `fetch_boundaries.py`
  tries the API, then the media host, then the raw host, and detects pointer files so
  a silent 130-byte "success" cannot slip through.
- **Known imprecision:** CGAZ simplifies polygons, fills gaps along shared edges, and
  replaces disputed areas with polygons following US Department of State definitions.
  For single-country precision use gbOpen HPSCU (`--full-precision`).

### GADM — deliberately not used

GADM's licence states the data "is freely available for academic and other
non-commercial use. Redistribution, or commercial use, is not allowed without prior
permission." Hosting GADM geometry in a public repository would violate it. It is
fine for local analysis; it is not in this pipeline.

### Natural Earth

Public domain (CC0). Used for the GEC↔ISO code concordance (`FIPS_10` ↔ `ISO_A3` on
`ne_10m_admin_0_countries`), for largest-settlement points
(`ne_10m_populated_places`, which carries `ADM0_A3`, `ADM1NAME` and `POP_MAX`), and
as admin-0/1 fallback geometry when geoBoundaries is unreachable.

## Country demographics

### CIA World Factbook

Public domain. Read through the community `factbook/factbook.json` mirror (CC0),
which tracked the site weekly until its retirement in **February 2026**. Treat it as
a frozen snapshot; every field carries its own reference year.

Two parsing hazards, both handled in `scripts/common.py`:

1. The mirror keys profiles by two-letter **GEC** (ex-FIPS 10-4) stems, but has
   migrated some entities to ISO-style stems — `in` is India, `id` is Indonesia.
   Resolving by stem alone silently swaps countries, so `fetch_factbook.py` resolves
   by *name* against the Natural Earth index and uses the code only as a tie-break.
2. Compositions nest commas and semicolons inside parenthetical asides — *"Muslim
   (official; predominantly Sunni) 99%, other (includes Christian, Jewish...) <1%"*.
   A naive `split(",")` invents groups called "Jewish" and "and Anglican)", so the
   parser tracks parenthesis depth.

### Wikidata

CC0. Walks the administrative tree structurally — P150 (*contains administrative
territorial entity*) then P131 (*located in*) — rather than through per-country
entity classes, so no class table needs maintaining. Population statements are
filtered to the most recent P585 (*point in time*) qualifier, and every optional
field is wrapped in `OPTIONAL` so an entity missing a population is still returned.

## Subnational demographics

| Country | Source | Level | Notes |
|---|---|---|---|
| USA | Census ACS 5-year, tables B03002 / C16001 / DP05 | state, county | B03002 rather than B02001, because only B03002 makes Hispanic origin orthogonal to race the way published "White, non-Hispanic" figures do. |
| USA | 2020 U.S. Religion Census (ASARB/ARDA `RCMSCY20`) | county | **Adherents**, not self-identification: 372 bodies, 161,224,088 adherents, ~48.6% of the population. Never comparable with self-ID percentages. |
| UK | ONS Census 2021 via Nomis (TS021, TS030) | local authority | England and Wales only; Scotland ran its census in 2022 and Northern Ireland through NISRA. Religion is voluntary — "Not answered" is kept as its own category. |
| Canada | StatCan 2021 Census Profile (SDMX, keyed by DGUID) | province, census division | Religion is asked once a decade (2021 yes, 2016 no). "Visible minority" is an Employment Equity Act category, not an ethnicity question. |
| Brazil | IBGE SIDRA tables 9514 / 9605 / 10086 | state, municipality | *Cor ou raça* is self-declared skin colour (branca, preta, parda, amarela, indígena) — not equivalent to ethnicity elsewhere. |
| EU | Eurostat `demo_r_pjangrp3`, `demo_r_pjanind3` | NUTS-2, NUTS-3 | Population and age everywhere; **no** ethnicity or religion — those are national census questions and only some states ask them. |
| Australia | ABS 2021 Census `C21_G14`, `C21_G08` | state, LGA, SA3 | Ancestry is multi-response (up to two per person), so shares are of responses and exceed 100%. No ethnicity question exists. |
| India | Census 2011 tables C-01, C-16 | state, district | No public API — per-state workbooks from the censusindia.gov.in NADA catalogue. 2011 is the latest round; the next census was postponed. |

### India, and trusting a community mirror

India is the only major country here with no statistics API at all. The Registrar
General publishes table C-01 as per-state XLSX workbooks through the
censusindia.gov.in NADA catalogue, which cannot be automated.

The adapter therefore reads a **district-level CSV extract of the 2011 primary
census abstract** redistributed on GitHub, and aggregates it upward to states.
That is a weaker provenance chain than an official endpoint, so the extract is
not trusted -- it is *verified*, on every run, before any of it is used:

* 640 districts, matching the 2011 count exactly.
* Total population 1,210,854,977 -- the published figure, to the person.
* Hindu 79.80%, Muslim 14.23%, Christian 2.30%, Sikh 1.72%, Buddhist 0.70%,
  Jain 0.37% -- each within 0.05pp of what the Registrar General published.
* Scheduled Caste 16.63% and Scheduled Tribe 8.63%, against published 16.6/8.6.

`NATIONAL_CONTROLS` in `scripts/fetch_census/india_census.py` encodes those
figures and `validate()` raises rather than emit a single record if the extract
drifts from them. Separately, the state aggregates reproduce the independently
hand-compiled rows in `data/curated/admin1_seed.json` (Uttar Pradesh, Kerala,
Punjab, Jammu & Kashmir, Nagaland) to within rounding -- two sources compiled
by different routes agreeing is the strongest check available without the
workbooks themselves.

The source of record remains the Census of India (GODL-India); the GitHub file
is a retrieval path, exactly as the factbook.json mirror is for the Factbook.
To use the official workbooks instead, download them into `data/raw/india/` and
run with `--input`.

### Mother tongue: the official C-16 workbooks

Table C-16 (population by mother tongue) is a separate publication from C-01 and
is not in the CSV extract. It is now read from the Registrar General's own
workbooks, checked into `data/raw/india/c16/` because there is no API to fetch
them from — `scripts/fetch_census/india_language.py` reads whatever is present.

The all-India workbook (`DDWC16STMTMDDS0000.XLSX`) carries every state, so all 34
states enumerated in 2011 have a mother-tongue composition. The numbered
workbooks carry that state's districts; 17 are present, giving 298 districts.
Districts elsewhere keep an explicit gap. Adding a state is a matter of dropping
its workbook into that directory.

**Two kinds of "other".** C-16 has a residual group of its own (code 124),
distinct from the tail this adapter folds for payload size. They are labelled
apart — `Other languages (unspecified)` against `Other small languages` —
because conflating them would misdescribe both. In Zunheboto the census residual
is 95.6% of the district: the Sümi spoken there is reported under it rather than
under group 107, and no breakdown is published beneath it at district level.
Calling that a tail of minor tongues would be the opposite of the truth. Four
units are affected at 20% or more (Zunheboto, West Khasi Hills, Dimapur, Lohit),
and where the residual appears the note says what it is.

Two shapes in the table decide how it is read, and both are checked rather than
assumed:

* **It is hierarchical.** Mother-tongue codes ending in `000` are the 122
  language groups; the codes beneath each are the individual tongues returned
  under it. Both sit in one column, so summing the column counts everyone twice.
  Only group rows are read, and `check_levels` requires them to sum to the unit's
  enumerated population — an independent total, so unlike a shares-add-to-100%
  test it cannot be satisfied by double counting. It earned its keep immediately:
  every state's row appears in both the all-India workbook and its own, and
  accumulating rather than assigning doubled all fifteen.
* **It is nested geographically.** State, district and sub-district rows share
  one sheet. Only zero sub-district codes are read.

`NATIONAL_CONTROLS` encodes the published all-India figures — 1,210,854,977
people, Hindi 528,347,193, Bengali 97,237,669, Marathi 83,026,680 and nine more —
and nothing is emitted unless the workbooks reproduce them exactly.

The Esri "Languages in India at District level" layer on ArcGIS Online (item
`16a1324c517048db890b86a87858a8ef`) covers the same ground and was probed with
`scripts/probe_arcgis.py`, but it is licensed **CC BY-NC-SA 4.0**. Non-commercial
and share-alike are both incompatible with redistributing it under the permissive
terms everything else here carries — the same objection that rules out GADM
above. The official workbooks are a better source anyway: GODL-India, and the
primary record rather than a derivative.

**Boundary vintage.** The boundary files are newer than the census, so:

* ~109 of 735 present-day districts did not exist in 2011 and carry no census
  figure.
* Four 2011 districts have since been subdivided (Jaintia Hills, Karbi Anglong,
  Warangal, and Hyderabad's reorganisation). Their figures are **not** spread
  across the successor districts -- the census never measured those areas
  separately, and apportioning them would be an estimate presented as a
  measurement. The successors carry an explicit gap saying so.
* Telangana (2014) and Ladakh (2019) postdate the census entirely, so they have
  no state-level figure even though their districts do.

## Collection policy

The `not_collected` marker is asserted from these tables and nowhere else:

- `NOT_COLLECTED_POLICY` in `scripts/common.py` — asserted for the country and
  then propagated to every subnational unit inside it by `apply_collection_policy`,
  because a district of a state that never asks the religion question has not
  merely failed to publish an answer.
- `COLLECTION_POLICY` and `COLLECTS_BOTH` in `scripts/fetch_census/eurostat.py` — EU
  member states.
- `_provenance.*.{religion,ethnicity}_policy` in `data/curated/admin1_seed.json` —
  subnational.

Adding a country means adding a row with a citable reason. An empty API response is
never sufficient grounds: it produces `not_available`.

### Collecting vs. not, in the EU

Romania, Bulgaria, Slovakia, Ireland, Hungary, Croatia, Slovenia, the Baltics and
Czechia collect ethnicity and religion in their censuses. France collects neither.
Germany does not collect ethnicity. Spain records nationality and birthplace, and
co-official language by autonomous community, but neither ethnicity nor religion.
Eurostat redistributes none of the ethnicity or religion tables sub-nationally, so
for the collecting states the adapter emits `not_available` with a note pointing at
the national statistical office rather than pretending the question was never asked.
