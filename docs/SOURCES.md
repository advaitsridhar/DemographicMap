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
| Switzerland | FSO structural survey 2024, main languages | canton | Main languages for all 26 cantons. A person may name up to three, so shares exceed 100%. |
| Singapore | Census 2020 + GHS 2015 planning-area tables | planning area |Ethnicity, religion and language for the planning areas, on three different bases. |
| Singapore | SingStat Table Builder M810771 | planning region | Resident population, sex ratio and a derived median age for the 5 regions. Religion, ethnicity and language are collected but not published at this geography. |
| Sri Lanka | Census of Population and Housing 2024, tables A1–A3 | province, district | Population, sex ratio, religion and ethnicity for all 25 districts and 9 provinces. |
| Mexico | INEGI Censo de Población y Vivienda 2020, ITER | state, municipality | Religion, indigenous-language speaking and Afro-descendant identification for 2,453 of 2,457 municipios. All from the *cuestionario básico*, so these are counts, not sample estimates. |
| New Zealand | Stats NZ 2023 Census via Aotearoa Data Explorer (SDMX) | region, territorial authority | Ethnicity, languages spoken and religious affiliation for all 88 territorial authorities and Auckland local boards. All three are multi-response, so shares are of people who named a group, not slices of a whole. Needs an API key. |
| Nepal | NPHC 2021, National Report on caste/ethnicity, Language and Religion | province, district | All three fields from one census: 142 castes/ethnicities, 124 mother tongues, 10 religions. All 7 provinces and 66 of 77 districts — the boundary file's district names do not all sit on the right polygons. |
| India | Census 2011 tables C-01, C-16 | state, district | No public API — per-state workbooks from the censusindia.gov.in NADA catalogue. 2011 is the latest round; the next census was postponed. |

### New Zealand: the geography that already fitted

Stats NZ asks ethnicity, languages spoken and religious affiliation, and
publishes all three broken down by *territorial authority and Auckland local
board area* — 67 territorial authorities with Auckland replaced by its 21 local
boards. That is exactly the 88-shape admin-2 layer geoBoundaries ships for New
Zealand, and all 88 join. Nothing else in this project has lined up so
precisely; it is worth saying plainly that this was luck, not craft.

**The API needs a key.** Only the bare dataflow catalogue at
`api.data.stats.govt.nz` is open. Every `/data/`, `/datastructure/` and
`?references=` request is 401 without one, because the Explorer's public member
is captcha-gated — its own page config says so. The key lives in a repository
secret, reaches the runner through the workflow's `env` block, and is sent as
an Azure API Management header. It never touches a file, a log or a command
line, and the adapter refuses to run without one rather than failing on a parse.

**Tiers are read from the codelist, not from the code width.** One area
codelist holds every geography at once, and the widths overlap where it
matters: `076` is Auckland the territorial authority and `102` is Auckland the
Te Whatu Ora health district — both three digits, both named "Auckland".
Reading the tier off the width put twenty health districts on the map as
territorial authorities. Every code carries a `Parent`, and the three tier
totals are distinct, so the tier is read:

| Parent | Tier | Codes |
|---|---|---:|
| `9999` | regional council | 17 |
| `999999` | territorial authority and Auckland local board | 89 |
| `99999` | health region and health district | excluded |

**Ethnicity is hierarchical in that same list.** `1 European` is the parent of
`111 New Zealand European`, `122 Dutch` and the rest, and both levels sit in
one codelist. Only the six level-1 codes are read; summing the column would
count most of the country twice, which is the trap the ABS "Christianity Total"
row and India's mother-tongue groups set in exactly the same way.

**All three fields are multi-response, and that is not an error to correct.**

| Field | Parts sum to | Because |
|---|---:|---|
| Ethnicity | 114.6% | a person may report more than one |
| Languages spoken | 124.7% | a person may speak several |
| Religious affiliation | 100.3% | a person may report more than one |

So each share is the percentage of people who named that group, not a slice of
a whole — European 67.8% and Māori 17.8% are both correct and they do not
compete. The denominator is the census usually resident population Stats NZ
prints on every table, which is what makes those figures match its own
published percentages.

**Two categories that are not what they look like.** "Object to answering" is
kept as its own category rather than folded into a non-response bucket,
because Stats NZ counts it inside *total stated* — it is an answer people gave,
not a question they skipped. And a suppressed cell is not a zero: Stats NZ
randomly rounds every count to base 3 and withholds cells too small to publish,
so a withheld group is named in the field's note rather than read as an absence.

**Where the gaps are.** Three source rows have no shape and one shape has no
source row, all four for the same honest reason:

* `Auckland` (the whole territorial authority) — geoBoundaries carries its 21
  local boards instead, and those all join.
* `Area Outside Region` and `Area Outside Territorial Authority` — offshore
  residuals with no polygon.
* `Chatham Islands Territory` at region level — the Chathams sit outside every
  regional council, so Stats NZ's regional tier has no row for them. Their
  figures are on the map at territorial-authority level.

The region names needed one alias: the region took the "Whanganui" spelling in
2015 and geoBoundaries still carries "Wanganui", which normalisation cannot
bridge because the h is a letter rather than an accent.

**The positional check could not be run here, and that is worth saying.**
After Nepal, every name join is meant to be checked against independent
reference points rather than trusted. For New Zealand it could not be:
Wikidata's SPARQL endpoint timed out on the admin-2 query on two separate
attempts, so there are no reference points to check against. What stands
instead is weaker evidence, but not nothing:

* `verify_shapes.py` reports 88 shapes under **88 distinct names** — no
  duplicates. Nepal's failure began with `Bara` and `Saptari` each appearing
  twice, and that failure mode is absent here.
* All 88 join by name, against a source whose tier is defined identically —
  Stats NZ's "territorial authority and Auckland local board area" is the
  layer geoBoundaries used, including all 21 local boards individually.
* Every national control matches Stats NZ's published figures to the person.

A 100% match on a tier both files define the same way is a different situation
from Nepal's 75 shapes for 77 districts. It is still an unverified assumption,
and re-running `fetch_wikidata.py --level admin2 --countries NZL` when the
endpoint is healthy would settle it.

### Nepal: three fields, one census, and a boundary file that does not fit

Nepal's census asks caste/ethnicity, mother tongue and religion, and the
National Statistics Office publishes all three in a single document. Nothing
else on this map carries all three from one enumeration, and no statistical
office outside South Asia asks caste at all.

**It is a PDF because nothing else can be reached.** `censusnepal.cbs.gov.np`
serves the census portal with a certificate that is not valid for that
hostname; so does `cbs.gov.np`. `microdata.nsonepal.gov.np` presents a good
certificate and returns an empty body, and `censusnepal.nsonepal.gov.np` — the
name the `microdata` certificate suggested — does not resolve. Population
figures are not worth taking over a connection that cannot be authenticated,
so the report is fetched once from a URL given on the command line and checked
into `data/raw/nepal/`, the same treatment as the Census of India C-16
workbooks and the 2020 U.S. Religion Census.

**One parser reads all three annexes**, because they share a layout: an area
name alone on a line, the area's printed total, then one row per group with
three figures. Which areas are provinces and which are districts is nowhere in
the text — the annex simply runs Nepal, then a province, then that province's
districts, then the next province — so the 7 provinces and 77 districts are
named lists in the adapter and an area matching neither is refused. That is
what stops a page number or a stray header being emitted as a place.

**Two checks, one of them independent.** The summary chapter's tables 10, 11
and 14 publish national figures for all three fields and are typeset
separately from the annexes, so agreement is evidence the reading is right
rather than evidence the arithmetic is self-consistent; every figure has to
match before a record is emitted. Separately, each area's rows must sum to its
own printed total. That second check is the one that catches a dropped row: a
shares-add-to-100% test cannot, because the shares are computed from whatever
was read.

**Eleven districts are withheld, and the reason is the boundary file.**
geoBoundaries CGAZ carries 75 shapes for Nepal's 77 districts, two of the names
appear twice, and in Karnali the labels are shifted along by one. This is not a
spelling problem an alias fixes — the names are on the wrong ground, and a
name-keyed join cannot notice, because a wrong join looks exactly like a right
one.

So the join is checked rather than assumed. `scripts/verify_shapes.py` takes an
independent reference point for every district — Wikidata's P625, fetched by
`fetch_wikidata.py --level admin2` — and asks which polygon contains it:

```
python scripts/verify_shapes.py --country NPL \
    --points data/processed/nepal_wikidata_points.json \
    --name-contains District --alias-module scripts.fetch_census.nepal
```

| | Districts | |
|---|---:|---|
| agrees | 64 | the point is inside the polygon of that name |
| near | 2 | just outside it, and no other district's point is inside it either |
| elsewhere | 11 | inside a differently named polygon, or no polygon bears the name |

The two "near" cases are Lalitpur, 1.6 km outside its own polygon, and Myagdi,
2.6 km. A reference point is a town hall or a centroid, not authoritative
geometry, and a point that lands just over a boundary into a neighbour whose
own point is somewhere else says more about the point than the polygon. Both
join, and the distance is printed so the call is reviewable.

The eleven are not marginal:

| District | Where its ground actually is |
|---|---|
| Rupandehi | inside a polygon named `Nawalapur` |
| Nawalpur | inside one named `Nawalparasi` |
| Parasi | inside no polygon at all |
| Dailekh | inside one named `Jajarkot` |
| Jajarkot | inside one named `Rukum West` |
| Rukum West | inside one named `Rukum East` |
| Rukum East | inside one named `Rolpa` |
| Parsa | inside one named `Bara` |
| Siraha | inside one named `Saptari` |
| Bara, Saptari | two polygons bear each name |

Joining any of these would render one district's population on another's
territory, which is the one failure this project treats as worse than a gap.
The check is not Nepal-specific: any country whose boundary names might have
drifted can be run through it, and the aliases come from the adapter itself so
there is one list of spellings rather than two that can disagree.

**Provinces changed their names, and the boundary file did not.** CGAZ still
calls Koshi "Province 1" and Madhesh "Province 2", names dropped when the
provinces were formally named. Those are genuine spelling variants of the same
territory, so they are declared as aliases and the join succeeds.

### Mexico: one file, four levels of geography

INEGI publishes the 2020 census as ITER — *Principales resultados por
localidad* — a single CSV covering every locality, municipio, state and the
nation in one table, distinguished only by the code columns. It carries three
of the fields this map wants, and all three come from the *cuestionario
básico*, the short form asked of everyone. They are therefore counts rather
than sample estimates, which is the only reason Mexico can be shown at
municipio level at all: an extended-questionnaire field would have a sampling
error at that geography large enough to make the colours meaningless.

**The nation is all three codes zero, not just the first.** ENTIDAD `00` looks
like the country, and it is — but it also carries national sub-totals, one row
per aggregation. Treating every `00` row as the nation ran the validation check
against a row holding 250,354 people instead of 126 million. This is the same
trap as the ABS "Christianity Total" row and the US Religion Census grand
total, and it is invisible in the shares: sub-totals are internally consistent,
so only an independently published figure catches it. A nation now requires
ENTIDAD, MUN and LOC all zero; a state requires MUN and LOC zero; a municipio
requires LOC zero.

**The columns are read from the archive's own dictionary.** The release ships
its data dictionary beside the data, so the religion columns are found by
matching descriptions rather than hardcoding `PCATOLICA` and guessing at the
rest. Matching is accent-blind and tries UTF-8 before latin-1, because the
archive mixes encodings — read as latin-1 throughout, a UTF-8 member comes back
as `religiÃ³n` and every match fails silently, which is exactly what happened.

**Three fields, three denominators.**

| Field | Question | Base |
|---|---|---|
| Religion | Católica / Protestante o cristiana evangélica / Otras religiones / Sin religión | everyone |
| Language | Speaks an indigenous language, yes or no | population aged 3 and over |
| Ethnicity | Identifies as Afro-Mexican or Afro-descendant, yes or no | everyone |

Religion's four groups are asked of everyone, so the remainder is people who
did not state one; it is named rather than dropped, and the bar reaches 100%
without implying the remainder is irreligious. Language is not a composition of
languages: the census records *whether* a person speaks an indigenous language
in this table, not which one, so the map shows a yes/no split and says so.
Ethnicity is a single self-identification question, so "Not Afro-descendant"
means "did not identify as Afro-descendant" and not membership of anything
else — it is not comparable with other countries' ethnicity categories.

**Validated against three published national figures**, not against itself:
126,014,024 people, 7,364,645 speakers of an indigenous language aged 3 and
over, and 2,576,213 people identifying as Afro-descendant. A control derived
from the same file would only prove the arithmetic; these come from INEGI's own
published summary, so they test the reading.

**Where the four gaps are.** Oaxaca has two municipios called San Juan
Mixtepec and two called San Pedro Mixtepec. CGAZ distinguishes them by the
*distrito* — "San Juan Mixtepec -Dto. 08 -" — and INEGI distinguishes them by
code, `20208` and `20209`, while giving both the same name. Neither file
carries the other's discriminator, so the join is refused: an unmatched
municipio is a visible gap, a mis-matched one would be invisible and would put
one community's figures on the other's territory.

Mexico City needed the opposite fix. CGAZ still calls it "Distrito Federal", a
name it lost in 2016, so its sixteen alcaldías could not be scoped to their
parent; seven of them share a name with a municipio elsewhere — Benito Juárez
is also in Quintana Roo, Cuauhtémoc in Chihuahua and Colima — and were being
refused as ambiguous. The adapter declares the old name as an alias, which is
what the matcher needed to see them as one place.

### Switzerland: a survey, and up to three languages per person

The Federal Statistical Office publishes main languages by canton as a
spreadsheet, so it lives in `data/raw/switzerland/`. Two properties decide what
the records may claim.

**A person may name up to three main languages.** The columns sum to 118.9% of
the population nationally, so the shares are of *responses*, not of people —
the same shape as Australian ancestry, and stated on every record rather than
left for a reader to notice the bars overflow.

**It is a sample survey, not a census.** Every figure ships with a confidence
interval, some enormous: Uri's French estimate carries ±57%. Estimates whose
interval exceeds ±25% of the estimate are dropped rather than shown, and the
note names what was dropped and why. `X` marks cells the FSO suppressed for
disclosure control — fewer than five observations — and is not zero.

The check reconciles the 26 cantons against the sheet's own national row. An
early version read the canton rows only, missed that row, and fell back to
comparing the canton sum with itself, which cannot fail; the adapter now
refuses to run if the national row is absent.

### Singapore's planning areas: three tables, three populations

The planning-area tables come from the census and household-survey releases
rather than the Table Builder API, so they sit as CSV extracts in
`data/raw/singapore/`. They do **not** describe the same population:

| Field | Source | Base | Total |
|---|---|---|---:|
| Ethnicity | General Household Survey 2015 | all residents | 3,902,690 |
| Religion | Census 2020 | residents aged 15 and over | 3,459,093 |
| Language | Census 2020 | residents aged 5 and over | 3,596,284 |

Each field therefore carries its own year and its own note naming whose shares
these are. Presenting them as one profile of one population would be wrong in
three directions at once, and the totals make the difference visible.

**`na` is not zero.** The releases suppress cells too small to publish, and
several planning areas are industrial or military with under a hundred
residents. A suppressed cell reads as missing, an explicit `-` as nil, and an
area whose breakdown is entirely suppressed keeps its published population while
the composition becomes an explicit gap saying it was withheld. The
reconciliation check flagged exactly this for Lim Chu Kang, Pioneer and Tuas
before it was handled.

Coverage differs by table: ethnicity reaches 41 planning areas, religion and
language 30 each — those two releases bucket the remainder into an "Others" row
that matches no shape on the map, and it is dropped rather than joined to
anything.

### Singapore, and two things the figures are not

The Department of Statistics publishes through the SingStat Table Builder API.
Table M810771 gives, for each of the five URA planning regions, the resident
count with a male/female split and nineteen five-year age bands.

**It counts residents, not everybody.** "Resident" means citizens and permanent
residents. Singapore's total population is considerably larger — roughly 1.8
million people on work passes and other long-term permits are enumerated
nationally but not in this series — so the five regions sum to about 4.2 million
against a much larger country figure. Every record carries a note saying so,
because a map showing the two side by side without explaining the gap would
simply look wrong.

**Median age is derived, not published.** The table reports grouped bands, so
the median is interpolated within whichever band holds the midpoint. That is
standard demography, but everywhere else in this map median age is a figure a
statistical office calculated, so `median_age_note` says which kind this is.
The open-ended top band is given a nominal five-year width rather than dropped,
which would bias the result downwards.

Religion, ethnicity and language are all collected by Singapore's census, but
none is published by planning region in this annual series, so each is an
explicit `not_available` naming what is missing.

The adapter calls the API and falls back to a payload committed under
`data/raw/singapore/` when the host is unreachable, which is what lets the build
run in a sandbox with no route to it while still refreshing on a runner. Note
that Wikidata offers Singapore's five Community Development Councils, which are
a *different* geography from the planning regions in the boundary files; the
join refuses them rather than matching them by resemblance.

### Sri Lanka, and a check the source hands you

The Department of Census and Statistics publishes the 2024 district tables as
small trilingual workbooks — Sinhala, Tamil and English run together in one
cell — with no API. They live in `data/raw/srilanka/` and are read from disk:
A1 population by sex and age, A2 by ethnicity, A3 by religion. Each title row
carries the year in all three languages, which is the authority for the 2024
label here.

At 2024 this is the **most recent census in the whole dataset** — newer than
Australia's 2021, England and Wales' 2021, and India's 2011.

Each district occupies **two** rows: counts, then the Department's own published
percentages. Only the counts are used, but the percentages are not ignored.
`check_published_shares` recomputes every share from the counts and requires it
to agree with what was printed beside it, within 0.1pp. That is worth more than
it sounds: a column read one cell to the left still sums to 100%, so no
internal consistency test would notice, while the published figures disagree
immediately. It earned its keep on the first run by catching a rename applied to
the counts but not to the lookup.

`NATIONAL_CONTROLS` additionally pins the national row — 21,781,800 people,
Buddhist 15,199,093, Sinhalese 16,144,037 and seven more — and the 25 districts
must sum to that total exactly. Note what that is and is not: those figures were
read out of these same workbooks, so it is a regression guard against a file
being swapped, **not** independent validation the way the India controls are.
The genuinely independent check here is the published-percentage one above.

The nine provinces are not in these tables; they are summed from their
districts, which is arithmetic on official counts rather than estimation, and
the nine sums are required to reproduce the national population.

**Language is `not_collected`, not merely missing.** Sri Lanka's census does not
ask mother tongue. It asks *literacy* — the ability to speak, read and write
Sinhala, Tamil and English, for people aged 10 and over — and the 2024 report
states plainly that it "did not account for proficiency in other languages".
Those are overlapping proficiencies rather than shares of a population, so they
are not a composition and are not a substitute for one: a bilingual person
counts in two of them.

Nor is language inferred from ethnicity here. Most Sri Lankan Moors speak Tamil,
so that inference would put roughly a tenth of the country in the wrong column.

The literacy figures do exist by district (report table 7.10 — Batticaloa 92.7%
overall, English literacy from 74.2% in Colombo to 31.7% in Mullaitivu) and
would be a legitimate field of their own. They are simply not the `language`
field, and are not loaded.

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
states enumerated in 2011 have a mother-tongue composition. All 35 per-state
workbooks are present, giving 637 of 735 districts. The 98 without a figure are
census-vintage gaps, not missing files: 92 are districts created after 2011 and
6 were undivided when the census ran.

**Not the `DDWC16TOWN...` files.** The catalogue also publishes a town-level
C-16 whose filename differs only by that infix. It enumerates urban population
only — its rural columns are zero — so feeding it to this adapter would publish
town figures as whole-district ones, and the internal checks would not catch it
because an urban-only state row and its urban-only district rows agree with each
other perfectly. Only `DDWC16STMTMDDS*.XLSX` belongs in that directory.

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

## Joining a row to a shape

Every adapter row has to find one boundary polygon. Names alone cannot do it:
district names repeat, and a lookup keyed on name keeps whichever shape it saw
last, which makes one district unreachable and lets the other quietly wear its
twin's figures. So a row that names its parent state is matched only inside
that state, and a row that does not is matched only against names that are
unique country-wide.

**A row that contradicts itself.** The case that slipped through for a long
time was a row that named a state, resolved it, found no shape of its name
inside — and was handed to the country-wide pass anyway, which matched a shape
in a different state. 443 rows across nine countries were joined that way. The
clearest was Vietnam's An Biên: the Wikidata entity is a ward of Haiphong at
20.85°N, and it was carrying the figures of the An Biên district of Kiên Giang,
1,200 km south. Argentina's Apóstoles Department (Misiones) wore Corrientes',
Peru's Huamantanga (Lima) wore Cusco's, and Thailand's Ao Phang Nga National
Park — not an administrative unit at all — wore Chiang Rai's.

**Coordinates decide, and only coordinates.** Where a row publishes its own
P625 point, the disagreement is settled against the matched shape's bounding
box: outside, the match is refused; inside, it is kept. That box is deliberately
weak as confirmation and strong as refutation — ADM2 geometry is dropped after
the parent pass, because 49,349 polygons will not stay in memory, so a point
inside the box is not proof it is inside the shape while a point outside it is
proof it is not. 274 joins were refused this way and 131 kept.

The 131 matter as much as the 274. They are the rows whose parent is named
historically rather than currently — Bogotá under Cundinamarca, Lima under Lima
Department, Sulu under Zamboanga Peninsula — and the rows where CGAZ's own
parent link is the thing that is wrong: it assigns each ADM2 to whichever ADM1
polygon contains its centroid, so Hurlingham, Lanús and Morón, all in Buenos
Aires Province, come out inside the Autonomous City. A rule that refused every
parent disagreement would have deleted all of them.

**Where there is no coordinate, nothing is refused.** India's district figures
are from the 2011 census, so they name the states of 2011: Adilabad and
Nizamabad say Andhra Pradesh where the boundary file says Telangana, Leh and
Kargil say Jammu and Kashmir where it says Ladakh. Those matches are correct —
the same district, named before the state it sits in was split. The census
adapters publish no coordinates, so there is no evidence either way, and
refusing on the disagreement alone would have deleted 26 correct Indian
districts along with correct rows in Mexico and the United States. A rule with
no evidence behind it does not get to decide.

**38 rows are still refused as ambiguous**, in Argentina (20), Vietnam (13),
Colombia and Thailand (2 each) and Mexico (1). Each names a state that resolves,
holds no shape of that name, and shares its name with two to eleven shapes
elsewhere — eleven Argentine provinces have a "Capital Department". A
coordinate settles fifteen of them, but the shape it picks usually contradicts
the state the row itself names, so the two signals disagree and neither is
strong enough to overrule the other. They stay visible gaps.

## Filtering one group across countries

The map can colour every unit in the world by its share of a single religion,
language or ethnic group. That is only possible because `scripts/canonical_groups.py`
records which labels name the same thing, and `build_entities.py` emits the
result to `site/data/groups.json`. Across nine countries the religion field
alone carries 39 labels for about a dozen religions, so a filter on raw strings
would draw a map of Islam that omits every country whose census says "Muslim" —
865 units in one spelling against 737 in the other.

Three properties of that index matter when reading the map:

* **The list is worldwide, not local.** It is built over every record. The
  picker used to be filled from whatever was loaded, which quietly made the
  filter local: at world zoom it offered only groups appearing in country rows,
  and inside one country only that country's own spellings.
* **A group's share is summed, not looked up.** The US reports Protestant,
  Catholic, Orthodox, Latter-day Saints and Jehovah's Witnesses where Australia
  reports one "Christianity" row. Matching a single row would show the US at its
  largest denomination and call that its Christian share.
* **Capitalisation is a house style, not a distinction.** Labels are matched
  case-insensitively. Matched literally, the Factbook's `no religion` and a
  census's `No religion` sat in the picker as two entries, one reaching ten
  countries nationally and the other six countries' provinces, as though they
  were different answers. The same fold takes the Factbook's `none` into "No
  religion", and `unspecified`, `no response` and `no answer` into "Not
  stated" — one uncertainty into another, which is the only direction that is
  safe. None of them is folded into "No religion", and neither is the US
  "Unaffiliated or not reported", which mixes people who belong to nothing
  with members of bodies that did not report.
* **Blank is not zero.** Most groups are reported by a minority of countries.
  Sikhism is reported by eight countries in all and by four of them nationally,
  so a world-zoom map of it shades four shapes and leaves the rest blank; that
  means four countries publish a national figure, not that nobody else has any
  Sikhs. The note under the
  list says how many countries and areas stand behind the current filter, which
  labels were folded together, and where a country measured it another way.
* **`units` counts areas, not rows.** One record can carry several rows that
  fold into one group — the US publishes Protestant, Catholic, Orthodox,
  Latter-day Saints and Jehovah's Witnesses where Australia publishes one
  "Christianity". Counting rows made `units` a row tally wearing the word
  "areas", and the panel read Christianity's country-level 450 out to a reader
  as 450 countries when only 215 country records carry a religion at all. It is
  now 201, which is exactly the length of the group's country list.

Ethnicity has the smallest layer of the three, and deliberately. Its
categories are made by states rather than found in the world: Brazil's *parda*,
the UK's "Mixed" and the US "Two or more races" are three different questions
with three different answer sets, and a person counted in one would not
necessarily be counted in the others. So the table holds only two kinds of
entry — one people spelled two ways (Māori/Maori, Romani/Roma/Gypsy), and one
population two sources name differently (Mexico writes its census category as
both "Afro-descendant" and "Afro-Mexican or Afro-descendant").

Four pairs are named in the code as deliberately *not* merged, because each
looks foldable and is not: White/European, Black/African, Mestizo/Mixed, and
Indian/East Indian. Nothing is lost by leaving them apart — an unmapped label
keys on itself, so the "White" of 27 countries is already one filter.

**A residual is not a group.** "other" reaches 92 countries in the language
field and 142 in ethnicity, and topped the picker while meaning nothing in
particular. Those buckets are now named ("Other languages", "Ethnicity not
stated") and flagged `residual` in `groups.json`, so the picker sorts them
last, under a heading saying they are the absence of an answer rather than a
group anyone belongs to. They are still shown: a bar that quietly drops a fifth
of a population is the failure this project cares about most.

**Reach is the sort order, not size.** The index is written most-areas-first,
which is the wrong first answer for a worldwide filter: "Unaffiliated or not
reported" is 3,130 US counties in one country, and it outranked Islam's 124
countries. The panel sorts by how many countries report a group, because that
is what makes it comparable across a border at all.

The same groups are reachable from the search box at the top, alongside
places: typing `islam` offers the religion before the places whose names
merely look like it, and picking it shades the map instead of moving it.
Group matches are capped at three, because `tamil` is a language, two
ethnic categories *and* Tamil Nādu, and burying the state under its own
linguistic namesakes would be its own kind of wrong.

## The filter panel

Everything above is only reachable through one control, so the control gets the
left side of the page rather than a floating box over the map. It shows and
hides from the topbar (**Filters**), from its own ✕, and with Escape; the
choice is remembered, and on a screen narrower than 900px it starts hidden and
opens as a drawer below the topbar rather than over it.

Four things it does that the four `<select>`s it replaced could not:

* **Field and group are separate controls.** They used to be one list whose
  entries read `Religion: Christianity  (201 countries)`, so choosing a
  language meant scrolling past every religion, and the same control silently
  changed jobs — from "field" to "group" — depending on a setting three rows up.
* **Each choice carries the sentence that says what it does.** A `<select>`
  has room for a label and nothing else, so "Data coverage" and "Share of one
  group" sat side by side with no hint that one of them needed a group chosen
  first.
* **The group list shows its evidence.** Every entry carries how many countries
  and areas report it, and the source labels folded into it, so the reader can
  see that picking "Christianity" also answers for the census that said
  "Catholic" — before picking it, not after.
* **The legend follows the panel out.** Hiding the controls is a request for
  more map, not for a map whose colours mean nothing, so the ramp, the chips
  naming the current filter, and the sentence about what blank means move to
  the map's corner when the panel closes.

All four choice lists — metric, field, group, detail — follow the same keyboard
contract: one tab stop, arrows to move, moving selects. The group list is a
listbox rather than a radio group, but behaves identically, because a list that
worked differently from the controls directly above it would be the more
surprising choice. Typing in the group search and pressing ArrowDown lands in
the list. A group chosen from the search box that a later search excludes is
kept, at the foot of the list under "Still on the map" — dropping it would
colour the map by something the picker denied was selected, and putting it at
the top would make the search look broken.

## Choosing the level of detail

By default the level follows the zoom: countries, then first-level divisions
from z3.6, then second-level from z6.6. The **Detail** control overrides that
and pins one level at every zoom, which is what makes a filtered group readable
at district granularity across borders — 49,349 second-level divisions at once
rather than 261 countries.

Two consequences are handled rather than hidden:

* `admin2.pmtiles` is built from **z2**, not z4 as before, because a pinned
  level with no tiles at the current zoom shows ocean and reads as a broken map.
  The archive grew from 47 MB to 51.8 MB. PMTiles is range-requested, so a
  viewer who never pins the level never fetches those tiles.
* Pinning second-level divisions at world view asks for every country's
  attribute shard — 48 MB across 218 files. They are fetched in batches and the
  map colours in as they arrive, with a counter saying how far along it is,
  because a map that stays blank until the last byte reads as broken too. The
  default stays "Follow zoom", so nobody pays that cost without asking for it.

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

## United States — religion

The United States is the clearest case in the dataset of a gap created
deliberately by law. The Census Bureau may not ask a mandatory religion question
(13 U.S.C. 221(c), since 1976), so **no government figures exist at any level of
geography**. Every US record says so before saying anything else.

The figures the map shows come instead from the **2020 U.S. Religion Census:
Religious Congregations & Membership Study**, checked in at
`data/raw/us/2020_USRC_Group_Detail.xlsx`. Suggested citation, as the publisher
gives it:

> Clifford Grammich, Erica Dollhopf, Mary Gautier, Richard Houseal, Dale E.
> Jones, Alexei Krindatch, Richie Stanley, and Scott Thumma. 2023. *2020 U.S.
> Religion Census: Religious Congregations & Membership Study.* Association of
> Statisticians of American Religious Bodies.

It is carried on every record the study touches. (The workbook's own Copyright
sheet dates itself 2022 and the suggested citation on usreligioncensus.org says
2023; the publisher's own wording is what goes on the record.)

**It is a different kind of number.** The study counts *adherents reported by
372 religious bodies*, not people answering a question about themselves. It
reached 161,009,516 people across 3,141 counties — about **48.6%** of the
population. Shares are marked `religion_basis: adherents` to keep them from
being read as the self-identification percentages every other country here uses.

The rest of each area appears as one category, **"Unaffiliated or not
reported"**, so the composition sums to 100%. That label is deliberately two
things at once: it mixes people who belong to nothing with members of bodies
that declined to report, and the study cannot separate them. Naming it that way
is the only honest option, because the alternatives are both wrong — calling it
"no religion" invents a measurement nobody took, and leaving it out invites the
reader to assume the bar describes everyone.

**It must not be rescaled to 100%.** The obvious-looking fix — treat the study
as a sample and scale each area's shares up until they fill the bar — fails for
two reasons. It is not a sample: it enumerates religious *bodies*, with no
sampling frame over people and no weights, so there is nothing to extrapolate
from. And coverage is not a constant to be divided out. It ranges from **27.3%
of New Hampshire to 76.2% of Utah**:

| Lowest coverage | | Highest coverage | |
|---|---|---|---|
| New Hampshire | 27.3% | Utah | 76.2% |
| Maine | 30.7% | Alabama | 63.8% |
| Oregon | 33.0% | Louisiana | 63.3% |
| Montana | 34.9% | Oklahoma | 61.0% |

That spread is the most informative thing in the dataset. Rescaling would make
New Hampshire and Utah look equally religious and would assert that nobody in
the United States is unaffiliated.

Thirty counties report *more* adherents than residents — rural congregations
drawing members from outside the county, King County, Texas at 452% — so the
remainder is only added where it is positive.

### Traditions, not denominations

372 individual bodies is neither mappable nor comparable with a census question,
so they are collapsed into traditions: Catholic, Protestant, Orthodox Christian,
Latter-day Saints, Jehovah's Witnesses, Other Christian, Judaism, Islam,
Buddhism, Hinduism, Other religions.

The mapping is by **exact name**, and only for what is *not* Protestant;
anything unlisted falls through to Protestant. Keyword matching would be wrong
in both directions and quietly so — the *Orthodox Presbyterian Church* and the
*Orthodox Mennonite Church* are Protestant, and the *Polish National Catholic
Church* is not Roman Catholic. Because the default absorbs anything unknown, the
adapter prints the largest bodies that fell through on every run, so a body
added or renamed in a later release is visible rather than silently swallowed.

Judaism is reported by movement (Orthodox, Reform, Conservative,
Reconstructionist, Independent, Chabad) and shown as one religion. Several
smaller traditions — Sikh, Jain, Zoroastrian, Shinto, Tao, Vedanta — appear in
the study with congregations but **no adherent estimate at all**, so they
contribute nothing to any share. They are classified anyway, so that they land
correctly if a later release does estimate them.

### The whole-country row, hidden three different ways

Every sheet carries a row holding the entire United States, and each sheet hides
it differently:

| Sheet | How the row is keyed |
|---|---|
| Group by County | `FIPS = "Total"` |
| Group by State | `StateCode = "Totals"` |
| Group by Nation | `Group Code = "Totals"` |

None of them names a religious group. Summing a column without excluding it
gives **322,019,032 adherents — 97% of the United States religiously adherent**,
wrong by exactly a factor of two.

Nothing inside the table catches this. Every county's own shares stay correct
and still reproduce the percentages printed beside them; the error lives
entirely in the aggregate. It is the same shape as the ABS "Christianity Total"
rows and the India C-16 group codes ending `000`: a parent and its children in
one column, where only a total the child rows did not produce can tell them
apart. The singular/plural difference between sheets is why the marker is a set
and not a string — an exact match on `"total"` silently misses the state sheet,
and a doubled country then reads as a perfectly valid table.

So `check_national` uses those rows as the control and **refuses to run without
one**. A reader that requires a group name skips them silently, since they have
none. With the check in place both levels reconcile exactly:

```
county: 161,009,516 vs whole-country row 161,009,516 (0.0000% apart, 3141 areas)
state:  161,224,088 vs whole-country row 161,224,088 (0.0000% apart, 51 areas)
```

Shares are taken against the population the file itself implies for each area,
recovered by inverting its published percentage column, rather than against the
ACS estimate on the record — which is a different year and would quietly
disagree with the percentages the study published. That inversion assumes one
denominator per area, so the adapter verifies it on every row: across all 3,140
counties the rows disagree by 0.000000%.

### A note on the checked-in workbooks

`.gitignore` excluded `data/raw/` — the directory itself, not its contents. Git
does not descend into an excluded directory, so every `!data/raw/.../*.xlsx`
negation beneath it was inert. The files already committed were unaffected,
because a tracked file ignores `.gitignore` entirely, which is exactly why the
rule looked as though it worked.

It did not. Twenty of the thirty-six Census of India C-16 workbooks had never
been committed, and a refresh from a clean checkout would have rebuilt mother
tongue from sixteen states and quietly returned the other twenty to
`not_available`. The pattern is now `data/raw/*`, which excludes the contents
and leaves the directory traversable, and all thirty-six are in the repository.

### Where there is still no figure

90 counties and one state keep a gap, and each says which kind it is:

* **78 Puerto Rico municipios and Puerto Rico itself** — the study covers the 50
  states and DC. Puerto Rico is outside its frame.
* **9 Connecticut planning regions** — Connecticut replaced its eight counties
  with nine planning regions in 2022. The 2020 study reports the old counties,
  and its figures cannot be placed on the new geography without inventing a way
  to split them. Same class of problem as the post-2011 Indian districts.
* **Alpine County CA (pop 1,515), Arthur County NE (485) and Loving County TX
  (96)** — the least populous county in each of those states. No reporting body
  had a congregation there. That is an absence of reported adherents, not a
  count of zero believers.
