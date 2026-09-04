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
| Australia | ABS 2021 Census `C21_G14`, `C21_G08` | state, LGA | Ancestry is multi-response (up to two per person), so shares are of responses and exceed 100%. No ethnicity question exists. There is no state-level table: the states are read off the LGA table's own `STATE` dimension. Population is the religion table's total, which is the region's counted persons. |
| Switzerland | FSO structural survey 2024, main languages | canton | Main languages for all 26 cantons. A person may name up to three, so shares exceed 100%. |
| Singapore | Census 2020 + GHS 2015 planning-area tables | planning area |Ethnicity, religion and language for the planning areas, on three different bases. |
| Singapore | SingStat Table Builder M810771 | planning region | Resident population, sex ratio and a derived median age for the 5 regions. Religion, ethnicity and language are collected but not published at this geography. |
| Finland | Statistics Finland table `11rl` (PxWeb) | region | Mother tongue for all 19 regions, from the population register at 31 December. One language is recorded per resident, so shares are of everyone rather than of the people who answered a question. |
| Estonia | Statistics Estonia table `RV0222U` (PxWeb) | county | Ethnic nationality for all 15 counties, from the population register on 1 January — a register count, not a census answer. |
| Latvia | Central Statistical Bureau table `IRE031` (PxWeb) | municipality, state city | Ethnicity for all 42 municipalities and state cities, from the population register. "Other ethnicities" also holds people who selected none and people who did not indicate one, so it is not a count of anyone in particular. |
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

### Australia: a table that was there, and four religions that were not

Two faults, both in the reading rather than the source.

**Every LGA shipped without a population.** The module docstring promised table
`C21_G01` "selected person characteristics" and the code never fetched it,
while the religion table it does fetch carries each region's own total. That
total is the region's counted persons — religion is voluntary, but a blank
answer is coded "Not stated" rather than dropped — and it was being discarded
as a denominator. The 565 LGA totals sum to **25,422,828** against Australia's
published 2021 census count of 25,422,788: forty people apart, which is the
ABS's perturbation of small cells.

**Islam, Hinduism, Buddhism and Judaism were missing from all 565 of them.**
The adapter keeps the rows marked `... Total`, because a category with
sub-levels is published beside its own children and summing both counts
everyone twice. A category with *no* sub-levels carries no marker, so those four
looked like denominations and were dropped. The arithmetic named them exactly:
the LGA populations summed to 25,422,828 and their religion counts to
23,209,496, a shortfall of 2,213,332 against those four religions' published
national totals of 2,213,173 — a difference of 159 people.

The classification's own code tree says what the marker cannot. A live region
looks like this:

```
   '_T'   8,665  Total
    '2'   4,644  Christianity Total
  '7_T'   2,961  Secular ... Total
 '7101'   2,947  No Religion, so described
  '207'   2,040  Catholic
   '_N'     948  Religious affiliation not stated
  '6_T'      39  Other Religions Total
    '3'      25  Hinduism
    '1'      22  Buddhism
    '4'      17  Islam
```

Widths vary at the same level, so keeping the shortest codes would throw away
every branch carrying the marker. The marker has to come off before the prefix
test, because the children of `7_T` are numbered from `7`. And the grand total
is nobody's parent: `_T` loses its marker and becomes the empty string, a prefix
of every code there is. **A category is outermost when no other category's
branch code is a proper prefix of its own** — which is the only rule that sees a
childless one.

Two rules disagree about the outermost level and the published total settles
it, because a partition of a population sums to that population. The bound is
the larger of half a percent and sixty people: the ABS perturbs counts by an
absolute number, so a proportional bound alone rejected 48 correct partitions in
LGAs of 11 to 2,520 people, none out by more than 53. Sixty cannot hide a
missing category — Australia's was out by 2.2 million.

**There is no state-level census table.** The catalogue offers `C21_G14` for
CED, LGA, POA, RA, SA2, SAL, SED, SUA and UCL and nothing for STE, so asking for
`--level state` fell through to Remoteness Areas and returned "Major Cities of
Australia (NSW)" as a state — 53 records, written to the file the build reads as
admin-1. The LGA table carries a `STATE` dimension, so the states are read off
that instead: the ABS's own assignment of each LGA to its state rather than a
guess from geometry. A state run that returns anything but eight or so records
now refuses to write.

The state populations are 2021 census counts, which replaced Wikidata's more
recent estimated resident population. They are the denominator their own
religion shares are taken against, and the same measure as the LGAs beneath
them; the ERP is more current but is a different measure, and mixing the two
across one hierarchy is what the roll-up check would have caught anyway.

### The Baltic offices: a shared adapter, and three ways a level hides

Most of Europe's statistical offices publish through PxWeb, so one adapter
serves many countries. Ten instances were walked before two were worth
pointing it at, and what the walk ruled out is worth writing down so nobody
walks it again: Lithuania, Slovakia, Croatia and Serbia answered 404 or
something that was not JSON at the base URLs tried; North Macedonia's tree
returned only broadcast-language tables at the depth walked; Slovenia has
ethnicity for all 193 municipalities but only from the 1991 census, against
boundaries redrawn twice since, so it is left out rather than joined across
thirty-five years of redistricting.

Estonia and Latvia are the point. Neither country had any ethnicity figure in
this dataset, both publish one annually, and both do it at a level the
boundary files carry.

**The Nordic offices were ruled out wrongly, and the note that ruled them
out is worth keeping as a warning.** It read: they "ask citizenship, which is a
different question", and Finland "rate-limits metadata and asks language rather
than ethnicity". Two mistakes in one sentence.

The first is a category error about this project. Ethnicity is not the only
field on this map; language is one of the four, and Finland records mother
tongue in the population register for every resident — a count, not a sample,
and better coverage than most censuses manage. Writing that off as "language
rather than ethnicity" treated a field the map has a column for as a
consolation prize.

The second is worse, because it dressed a bug up as a finding. StatFin answers
429 under a brisk walk. The probe treated that error like an unreachable node,
found nothing, and the nothing was written down as a fact about Finland's
statistics. Re-walked with backoff, the same instance returns 44 candidate
tables. A probe that cannot tell "throttled" from "empty" will keep producing
confident absences, so it now backs off on 429, carries a per-instance pace
and budget, and says explicitly when a budget ran out — because only a
completed walk can report an absence.

**A PxWeb geography variable holds several levels at once**, and often two
vintages of one level. Latvia's carries the country, five statistical regions
as defined before 1 January 2024, five as defined after, and then the
municipalities. Summing across that double-counts half the country. Three
separate rules were needed, and each was found by a check rather than by
reading:

* *Code length* pins the municipalities apart from the country and the
  regions. That is the office's own encoding of depth.
* *Codes grouped by their stem* separate a municipality from a town inside it.
  `LV0031000` is Jēkabpils municipality and `LV0031010` is the town of
  Jēkabpils within it — same width, and the parent's tail sorts first. This
  cannot be decided one row at a time: a town looks exactly like a
  municipality until the municipality turns up beside it. A rule that simply
  refused every tail but `000` read the three towns correctly and then also
  threw away Madona, which since the July 2025 merge with Varakļāni is
  `LV0038001` and is nobody's child.
* *A label beginning `..`* is a sub-category of the one above it. Estonia
  writes "Other ethnic nationalities" and then "..Ukrainians" beneath it, and
  Tallinn as "..Tallinn" because it sits inside Harju county.

**Two controls, and only the second one catches containment.** Every unit's
categories are checked against the total the table itself publishes; that
catches a level of the classification kept twice or dropped once. It cannot
catch a unit counted inside another, because each such unit is internally
consistent. Latvia's first run returned 45 municipalities, every one summing
exactly to its own published total, and 1,911,026 people against a country of
1,845,096. Only the country row shows that. It now stands as the second
control, and Latvia's 42 units sum to 1,845,096 exactly.

**The names had to come from the office, not from a rule.** geoBoundaries
carries local-language names for both countries — `Harju maakond`,
`Aizkraukles novads` — and the tables' English labels are "Harju county" and
"Aizkraukle municipality". That is two disagreements at once, a translated
generic word and a genitive ending, and no rule about English suffixes bridges
either.

Adding `novads` to the words the matcher strips looked like the fix and is a
worse bug: it collapses `Ventspils` and `Ventspils novads` — a state city and
the municipality around it, two different places — onto one key, and one of
them then quietly wears the other's figures. A local generic word is not a
word to strip; it is a sign the two sources are speaking different languages.

PxWeb serves the same table under a language path, with the same codes and the
same figures and local labels, so the adapter asks for those and joins on
them. The English label stays as an alias. The one qualifier that has to come
off is the vintage tag an office attaches to a redrawn unit — and what marks
that is the date inside the parenthesis, not the word in front of it: matching
on "from" and "until" read the English labels and missed the Latvian
`(no 01.07.2025.)`.

**Finland, and what a level looks like when the office spells it out.** Table
11rl gives mother tongue by region: not a census question but a register
field, one language per resident, which is why the 19 regions sum to
5,652,881 against a published 5,652,881 exactly.

The level is named in the code rather than implied by its width. `MK` is
*maakunta*, and the same variable carries `SSS` whole country, `MA1` mainland
and `MA2` Åland beside the regions. A width rule separates them here by luck —
every MK code happens to be one character longer — and would stop being true
the day an aggregate got a fourth character, so the rule is the prefix the
office itself uses. `MA2` is the one that would have cost something: it is
`MK21` under another name, and keeping both adds the whole province twice.

The language list is two levels deep and its parents are not marked the way
Estonia's are. `01 NATIONAL LANGUAGES, TOTAL` holds Finnish, Swedish and Sami;
`02 FOREIGN LANGUAGES, TOTAL` holds the other 163. Neither label is a word the
total-detection knows, so both would have been read as ordinary categories and
most of the country counted twice — with every check still passing, because a
partition that double-counts consistently still sums to its own total.

Six regions needed declared aliases, because geoBoundaries names them with
older English exonyms: *Finland Proper* for Varsinais-Suomi, *Tavastia Proper*
for Kanta-Häme, *Southern* and *Northern Savonia* for Etelä- and Pohjois-Savo,
*Northern Ostrobothnia* for Pohjois-Pohjanmaa, *Åland Islands* for Ahvenanmaa.
Nothing infers "Finland Proper" from "Varsinais-Suomi"; they share no word.

Northern Ostrobothnia is why that matters rather than being tidy-up. "North
Ostrobothnia" is close enough to bare "Ostrobothnia" — a different region, and
one where Swedish is the plurality language against Finnish at 95% in the
other — that the loose pass reached it. The only thing that stopped it was the
rule refusing two rows that land on one shape, and that rule stopped it by
dropping the row rather than by placing it. A wrong join that a tiebreak
happens to catch is still a wrong join, waiting for the tiebreak to be absent.

**The rest of the Nordics, walked properly this time.** Finland was the one
that paid. The others were each ruled out for a reason worth writing down,
because "we looked and there is nothing" is only worth as much as the looking.

*Sweden* has neither. Six candidate tables, every one citizenship or
naturalisation, and the tree finished inside its budget — so this is a real
absence rather than an interrupted search. Sweden has kept no register of
religion since the church separation in 2000 and does not collect ethnicity.
The original note was right about Sweden.

*Norway* publishes membership of religious and life-stance communities by
region — table 08531, 42 regions — and it cannot be used here. Every one of
those tables counts communities **outside the Church of Norway**. The Church
itself is roughly two-thirds of the country and appears only in table 06929,
**by diocese**, and Norway's twelve dioceses do not nest into its eleven
counties. KOSTRA reports the Church by municipality for services, employees,
users and finances, but not for membership. People who belong to nothing are
not counted at all.

So a share built from 08531 would have "members of minority religious
communities" as its denominator. Islam reading 25% in a county would mean a
quarter of a small slice, not a quarter of the county, on a map where every
other religion figure is a share of population. That is the mis-match this
project exists to refuse, and refusing it leaves Norway an honest blank rather
than a number that looks right.

*Iceland* keeps a register of religious and life-stance organisations —
MAN10001, 64 organisations, annual since 1998 — and it carries **no geography
dimension at all**: year, organisation, and a split by sex, age and parish-fee
payment. National only, exactly like Finland's 11rx.

Finding it took four `--tree` calls, and the reason is worth recording: it is
not in the database the instance is configured against. Statistics Iceland
serves several, the configured one is *Ibuar* (inhabitants), and religion sits
under *Samfelag* → culture → religious organisations. Every walk of Ibuar
correctly reported no religion tables, and that report was about which database
had been walked.

*Denmark* is not PxWeb. StatBank has its own REST shape, so the walk cannot
read it and it is skipped by name rather than reported as empty.

**Not taken from Finland.** Table 11rx, *belonging to a religious community*,
has no geography dimension at all — religious community, sex, age, year, and
nothing else. It is a national figure and this map already has one. Table 11rm
gives language by all 309 municipalities, but geoBoundaries' admin-2 for
Finland is 70 sub-regions rather than the municipalities, so it would have to
be rolled up before it could join.

**Where the gaps are.** All 15 Estonian counties join, and 40 of Latvia's 42
units — 39 of them on an exact name. Madona joins through the prefix pass
because geoBoundaries has not yet absorbed Varakļāni into it, so the figures
are for the merged municipality on the pre-merger shape and Varakļānu novads
sits blank beside it.

Two do not join: `Jelgava` and `Rēzekne`. geoBoundaries writes the state
cities in the genitive — `Jelgavas`, `Rēzeknes` — so only the loose pass can
reach them, and it reaches `Jelgavas novads` at the same time. This project
refuses a loose match that two shapes answer to, and that refusal is
deliberate and tested; these two stay visible gaps rather than a coin flip
between a city and the municipality surrounding it. `Jūrmala` and `Liepāja`
are inflected the same way and do join, because neither has a municipality
named after it to compete.

What this pass did fix is the opposite failure. `Ventspils municipality` used
to normalise to `ventspils` and match the *city* outright, beside the city's
own row doing the same — two different places on one shape, one of them
silently wearing the other's figures. On the office's own names they are
`Ventspils` and `Ventspils novads`, and they land where they belong.

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

### Pakistan: a table that exists only as a document

The Bureau of Statistics publishes Table 9 -- *population by sex, religion and
rural/urban* -- as one PDF per province, from the 7th Population and Housing
Census 2023. There is no API and no spreadsheet. Reading the document is the
whole job, and it took nine refusals to do it, every one of them the adapter
stopping itself rather than shipping something wrong.

**The row labels are stored apart from the figures.** pypdf returns a page's
strings in the order the file happens to hold them, which here is every number
first and every label afterwards, in a block that is not itself in document
order. Pairing by position is a guess, and the table interleaves districts with
the tehsils inside them, so a wrong guess does not look wrong: it puts a
tehsil's people on a district and every total still adds up. pdfplumber reports
each word with its box, so the rows are rebuilt from where the words sit.

**A figure can arrive as several words.** Khyber Pakhtunkhwa's 36 Parsis come
back as `3` and `6`; Punjab writes 124,462,897 as `1` and `24,462,897`, and
1,071,693 as `1` and `,071,693`. Splitting a row on whitespace yields more
values than there are columns and shifts every column after the split one place
to the left. The gaps settle it: measured in both files, a gap inside a value
is exactly 0 points and a gap between columns never less than 13.

**Where the columns are is not a fact this document has.** Three rules were
tried on position and each fitted whichever file it had been read off:

* The header's numbered row, `1 2 3 … 10`, is set flush right with the columns
  in Punjab -- the `2` heading TOTAL POPULATION ends at x=173 and so does
  127,333,305 beneath it -- and twenty points to their left in Khyber
  Pakhtunkhwa.
* The figures themselves are flush right, but the table sits at its own
  horizontal offset on every page, so edges learned across the document match
  no page in particular.
* And within one page: page 2 of Khyber Pakhtunkhwa carries two offsets at
  once, 37 rows at one and 12 at the other.

What the table does print, every time, is nine cells to a row with nothing left
out, because the office writes a dash where a religion is absent rather than
leaving the cell empty. So the cells are counted, dash included, and a row
without nine of them is refused rather than trimmed to fit. A row shifted
bodily sideways reads the same, which is a test.

Counting is what failed at the very start. It failed because the words were
miscounted, not because counting was the wrong idea.

**Two controls, both supplied by the file.** Each district's religions must sum
to the total printed beside them -- a column read one place to the left still
sums to something, but not to that. And the districts must sum to the province
printed above them.

The second one is the one that mattered. Thirty-four districts were read from
Khyber Pakhtunkhwa, every one reconciling perfectly against its own printed
total, and together they were 825,377 people short of their province. The
missing unit was `MALAKAND PROTECTED AREA`, which is not called a district and
so was never noticed: a heading this reader does not recognise produces no
wrong figure anywhere. Nothing but the file's own province row knew.

**What is not here.** Islamabad, Azad Jammu and Kashmir and Gilgit-Baltistan
are enumerated apart from the census proper and their Table 9 is not published
at either path the office uses. They are named in the run's log as absent
territories rather than as failed fetches, and the four provinces -- 238 of
Pakistan's 241 million people -- are required before anything is written.

**Joining, and three different kinds of miss.** Of 126 units, 114 join and
carry 96.7% of the people.

* *Spelling and renaming*, declared rather than derived: Battagram for
  Batagram, Qilla Abdullah for Killa Abdullah, and Nawabshah for Shaheed
  Benazirabad -- a rename that shares no word with the current name, so nothing
  could infer it. A rule loose enough to bridge these is loose enough to bridge
  places that are not the same.
* *Several districts to one shape.* geoBoundaries draws one Chitral where the
  census counts Lower and Upper, one Kohistan where it counts three, and one
  Karachi where it counts seven city districts. Each is a division of an older
  district the file still draws whole, so the parts are exactly the shape. They
  are summed and the note on each says which districts were summed. A partial
  sum is refused: putting a fraction of the people on the whole shape would
  look entirely normal.
* *Districts the boundary file does not have*: Larkana, Chiniot, Nankana Sahib,
  Sujawal, Torghar, and six of Balochistan's newer ones -- 7.8 million people,
  3.3% of the country. These stay unmatched, which is what an unmatched row is
  for.

**The population figure** is Table 9's own TOTAL POPULATION column, because
that is the denominator these shares are of. It is not the only population the
office publishes.

### Bangladesh: a mirror, and a merged sheet that is wrong

The Bureau of Statistics publishes a workbook of Census 2022 indicators at
admin-2, one row per zila, and among its forty-two sheets is *Population by
Religion, Sex*: Muslim, Hindu, Christian, Buddhist and Others, for all
sixty-four districts. All 64 join, carrying every one of Bangladesh's
165,158,616 people.

**It is read from a mirror, deliberately.** None of the office's own hosts can
be fetched over a connection that verifies:

* `bbs.gov.bd` has a valid Sectigo certificate that does cover the host, but
  the server never sends its intermediate, so no chain can be built. A browser
  papers over this by fetching the issuer the certificate names; urllib does
  not.
* `bbs.portal.gov.bd` answers with a "Kubernetes Ingress Controller Fake
  Certificate" for `ingress.local`.
* `file.portal.gov.bd`, `sid.portal.gov.bd` and `portal.gov.bd` time out.

The alternatives were disabling certificate verification, which this project
does not do, or recording Bangladesh as uncollectable, which would be false:
the census exists, is published, and is CC0. HDX carries the office's own
workbook under the UN in Bangladesh.

An earlier note in this repository said `bbs.gov.bd` "failed TLS". It does not
— its certificate is valid and names the host. What failed was a fetch from a
sandbox whose egress proxy blocks the domain, and the two were written down as
the same thing. That is the same error as reading a 429 as an empty database,
and it is kept here rather than quietly corrected because a probe that cannot
tell "we could not reach it" from "it is broken" produces confident absences.

**The workbook's merged sheet is wrong, and is not used.** `Merged_All_Table`
flattens the forty-two sheets into 445 columns. In it, Cumilla and Cox's Bazar
hold each other's household and population figures — Cumilla 2,823,268 against
a real 6.2 million — while their district geocodes, 19 and 22, stay correct.
Joypurhat and Naogaon are wrong too, and Naogaon's figure matches neither
district, so it is not a clean transposition throughout. The per-topic sheets
it was built from are consistent, and those are read instead. Nothing here
takes even the division names from the merged sheet: they may well be sound,
but a sheet with three known transpositions is not somewhere to take an
unverifiable field from.

**Two checks, and the second is what found that.** Each religion's total must
equal its own male plus female column — the sheet stating the same figure
twice, which is what makes the column headings trustworthy rather than
assumed. And the religions plus the third gender must equal the district's
published population **exactly**, which is two separate sheets agreeing to the
person about every district.

Had only the first check existed, all 64 districts would have passed and three
would have shipped carrying another district's population: every religion in
them adds up by sex perfectly well. A tolerance wide enough to admit a hijra
count would have been wide enough to hide the transposition.

**The religion table does not count everybody.** Each religion's total is
exactly male plus female, and Bangladesh enumerates a third gender: Barguna's
religions sum to 1,010,461 against a published 1,010,531, and the 70 missing
are its hijra — the number the population sheet prints in its own Hijra
column. Nationally that is 8,124 people the religion table does not classify.
So the shares are of the population it does classify, and both figures are
kept: the district's population, and the denominator the shares are of.
Silently using one for the other is how a footnote becomes a wrong number.

**Joining.** Eight districts were respelled in English in 2018 — Chittagong to
Chattogram, Comilla to Cumilla, Barisal to Barishal, Jessore to Jashore, Bogra
to Bogura — and geoBoundaries still carries the older forms, with plain
transliteration variants for three more. Declared rather than derived:
"Nawabganj" and "Chapainababganj" share no word.

### Indonesia: published, and not fetchable

Indonesia is 284 million people and the largest population this map still has
no subnational religion for. The data exists: BPS publishes *Population by
Regency/Municipality and Religion* on each provincial site, one table covering
that province's kabupaten. It could not be fetched, and the reason is worth
recording precisely, because "unreachable" has meant four different things
here and only one of them was about Indonesia.

* `bps.go.id`, `www.bps.go.id` and the provincial `*.bps.go.id` sites answer
  **HTTP 403** to a request carrying this project's User-Agent. Not a
  certificate problem -- their DigiCert and Google chains are valid and cover
  the hosts. The block is deliberate, and getting past it means claiming to be
  a browser, which is circumventing a refusal rather than reading a
  publication. This project does not do that.
* `webapi.bps.go.id` **works**. It answered
  `{"status":"Error","message":"Parameter Key is Missing."}` -- reachable,
  functioning, and wanting a free registered key. This is BPS's own sanctioned
  programmatic interface and is the route to take when a key exists.
* `sp2010.bps.go.id`, the 2010 census service, is reachable and serves **one
  identical 52,849-byte HTML document at every URL**. Its root, a table path, a
  topic path, `/static/js/app.js`, `/static/css/app.css` and a deliberately
  nonsense path all return the same bytes. Its apparent navigation and script
  list are that document's own template, so searching it for an API endpoint
  searches the same page again. There is nothing behind it to read.
* `satudata.kemenag.go.id` (Ministry of Religion) and `data.go.id` time out.
* HDX carries Indonesia's subnational **population** but not religion, so the
  mirror that made Bangladesh possible does not help here.

The honest state is therefore: the census exists, is public, and is not
available to an automated reader without a key. Indonesia stays an explicit
gap until one exists -- 284 million people uncoloured, with the reason written
down, rather than a figure assembled from somewhere it should not have come
from.

Two of those bullets were mistakes before they were findings, and both are the
same mistake. `sp2010.bps.go.id` was described in this repository as serving
the 2010 tables in plain HTML before anyone had checked that it served
anything; and `bps.go.id` was first recorded as unreachable on the strength of
a 403 from a sandbox whose egress proxy blocks it, exactly as `bbs.gov.bd` was.
A source is only as absent as the search behind it, and a search is only as
good as the thing it actually fetched.

### The U.S. Census Bureau's subnational series: one reader, many countries

Some countries publish a census and never publish it as data. The U.S. Census
Bureau extracts those, for USAID's humanitarian bureau, into one workbook per
country under a schema that does not vary: every sheet opens with the same
geography columns -- `AREA_NAME`, `ADM1_NAME`, `ADM2_NAME`, `ADM_LEVEL` -- and
then a block of value columns for one topic. So `scripts/fetch_census/uscb.py`
is one reader with a configuration per country rather than an adapter each, the
same call `pxweb.py` makes for the Nordic offices.

| | Census | Fields | Areas |
| --- | --- | --- | --- |
| Philippines | 2020 (Philippine Statistics Authority) | religion, ethnicity | 17 regions, 116 provinces and cities |
| Ethiopia | **2007** (Central Statistical Agency) | religion, ethnicity, language | 13 first-order areas, 93 zones |
| Myanmar | 2014 census (religion), **2017** Township Profiles (ethnicity) | religion, ethnicity | 15 states and regions, 80 districts |
| Ukraine | **2001** (State Statistics Service) | language | 27 oblasts, summed from 661 rayons |

Ethiopia is 2007 because that is the last census Ethiopia has completed -- the
2017 round was postponed and never held. It is the most recent measurement in
existence, not the most recent this project could reach, and every record says
so. The workbook's own filename dates (`_202308`) are extraction dates and were
never allowed to stand in for the census year; the table identifiers inside
(`ET_RELIGION_2007census`) are where the year actually comes from.

**Five things this reader learned the hard way**, each from a run that failed
against a real file rather than from reading the schema:

* **-999 is a missing marker, and nothing documents it.** Four Ethiopian areas
  carry it across all six religions, and openpyxl hands it over as an ordinary
  number. The sex check caught it -- "females plus males" came to -1,998
  against a both-sexes -999 -- and without that it would have put a negative
  population on the map. Rejected as *not a count* rather than as -999
  specifically: no census reports a negative number of people, so any negative
  is a marker whatever its value, and a sentinel changed to -998 tomorrow is
  still caught.
* **Which columns hold groups is a fact the sheet states.** The first version
  carried a column prefix per topic and was wrong on its second file, because
  Ethiopia's ethnic-group columns are not named `ETH_`. They are now whatever
  is not geography, which is simpler and cannot be wrong on the next country.
* **Sex is a check, not a dimension.** Ethiopia reports every religion three
  times. Only the both-sexes column is a value here; the other two are an
  independent statement about the same population, and a file whose sexes do
  not add up is a file the reader has misunderstood. It holds across 5,070
  cells.
* **The country's own row is the control.** Every workbook carries one, and
  not using it is how three million people go missing quietly. Ethiopia's
  first-order areas come to 73,750,932 against a national 73,750,932, and the
  Philippines' regions to 108,667,043 against 108,667,043; both levels
  reconcile to the person.

  They did not at first, and the story of why is worth keeping. The reader
  keyed areas by name alone, so Ethiopia's two North Shewas -- one in Amhara,
  one in Oromia -- overwrote each other, and the national total came out
  3,050,890 short. That number is very close to Sidama's 2,954,136 plus a
  small area's 96,754, and so a tidy explanation was available and was
  believed: that the two are regions created in 2020-21 and were being
  reported at the level the 2007 census counted them at. It was wrong. The
  shortfall was the bug, the arithmetic was a coincidence, and the account
  survived as long as it did because it explained the number without ever
  being checked against the file. Once the key became (parent, name) the sums
  closed exactly and there was nothing left to explain.

* **A first-order area the file does not name.** Ethiopia's thirteenth
  first-order row is labelled only "Region 17": 96,754 people, 92.5% Muslim,
  4.8% Orthodox. The Bureau gives it no name, geoBoundaries has nothing
  corresponding to it, and this project does not guess -- it is carried with
  the label the file gives it and joined to no shape.

**A shortfall is judged by its shape, not only its size.** Three Philippine
areas -- MIMAROPA and its two Mindoro provinces -- fall 0.6% to 1.3% short of
the census's own household population, and the region's shortfall is the sum of
its provinces'. That is a hole in the source, so they are named, kept, and the
map draws the remainder as an explicit unaccounted share. A single tolerance
cannot tell that from a reader that has read the wrong column, so the test is
the pattern instead: any area more than 5% short is refused as too large to be
a suppressed group, and more than a tenth of areas falling short is refused as
a misreading rather than a source with holes in it.

**The Philippine religion groups are published as the census names them** --
129 of them, from Roman Catholic to the Bible Baptist Church -- rather than
collapsed into traditions. Collapsing would decide, on this map's authority
rather than the census's, which churches count as one religion, and the
Philippines is exactly where that is contentious: Iglesia ni Cristo and the
Aglipayan church are distinct national institutions, not footnotes under
"Christian". The panel folds a long tail into "Other groups" for display, so
faithfulness costs nothing a reader sees. The national figures reproduce the
PSA's published ones: Roman Catholic 78.81%, Islam 6.42%, Iglesia ni Cristo
2.58%.

**What of this reaches the map, measured rather than assumed.** A correct
adapter and a visible country are different things, and the only way to know
which one you have is to run the join and count.

| | Rows | On a shape | Declared shapeless | Unmatched |
| --- | --- | --- | --- | --- |
| Philippines regions | 17 | 17 | -- | -- |
| Philippines provinces and cities | 116 | 82 | 33 | 1 |
| Ethiopia first-order | 13 | 11 | -- | 2 |
| Ethiopia zones | 93 | 72 | 20 | 1 |

Every CGAZ shape for both countries is filled except six: Ethiopia's "Region
14" (Addis Ababa, whose ten sub-cities are separate census areas) and "Special
Woreda" (likewise), the three numbered NCR district shapes that stand for
fifteen Metro Manila cities, and Cotabato City, which the workbook does not
carry as an area of its own.

Three kinds of miss, and they are not the same kind of thing:

* **Declared shapeless** -- 53 rows the boundary file folds away by design. A
  highly urbanized Philippine city is drawn inside the province around it;
  Addis Ababa's sub-cities are drawn as one shape. These rows carry real
  figures that no shape can show, and the adapter now says so in the data
  rather than leaving them to the matcher. That is not tidiness. "Cebu City"
  and "Province Of Cebu" both normalise to `cebu`, both matched outright, and
  the collision pass reads two outright matches as one place listed twice and
  lets the last one win -- so a city of 964,000 was wearing a province's
  figures, invisibly, and so were Iloilo and Quezon City. Declaring the fold
  is what turned three wrong answers into three stated gaps.
* **Absent upstream** -- Sultan Kudarat, a Philippine province with no CGAZ
  shape at all; Sidama, an Ethiopian region created after CGAZ's Ethiopian
  vintage; and "Region 17". These are deliberately *not* declared. They are
  omissions a later boundary release could fix, and a declaration would then
  be a lie that suppresses a real match. A declaration should only ever be
  doing work.
* **Two shapes under one name** -- geoBoundaries carries both "Cotabato" and
  "Cotabato City" inside Soccsksargen, and `norm()` drops the word "city", so
  both arrived under one key and both were thrown away as ambiguous. Cotabato
  province, 1.4 million people, was then handed South Cotabato by the
  containment pass and saved only by the collision pass refusing it. Where
  exactly one of two tied shapes is written the way the row writes it, that is
  stronger evidence than the key that tied them, and the tie is now settled on
  the exact name and on nothing weaker.

**A sheet's name is not its contents, and three countries prove it.**

* **Myanmar's "Ethnicity" sheet is not from the census.** The 2014 Population
  and Housing Census asked about ethnicity and its results were never
  published; the tables were withheld. So the Bureau uses the Department of
  Population's *2018 Township Profiles*, Table 14, with a reference date of
  April 2017 -- and says so in the data dictionary while the sheet keeps the
  same name and sits in the same file as the 2014 Age-Sex tables. Dating those
  figures to 2014 would attribute them to a census that refused to release
  them, which is the single most notable fact about ethnicity data in Myanmar.
  `Topic` therefore carries its own year, source and note, overriding the
  country's, and each record gets one citation per topic rather than one for
  the file. Myanmar recognises 135 official ethnic groups and this table names
  40; the Rohingya appear in neither, having been excluded from enumeration as
  an ethnicity in 2014.

* **Syria's "Ethnicity" sheet is nationality, and is not read.** Its nine
  columns are Syrian, Palestinian, Arab-other, European, African non-Arab,
  Asian, Australian, American, Other, and its dictionary names the source
  table: *Distribution of Individuals by Nationality*. Published as ethnicity
  that would tell a reader Syria is ethnically uniform, which is neither what
  the 2004 census measured nor what it claimed. There is no field on this map
  for citizenship, so Syria stays empty and this is the reason.

* **Myanmar's sheet holds two questions.** It is called "Ethnicity" and
  carries the religion columns beside the ethnic ones. Reading "everything
  that is not geography" collected both, and the shares came to 3.05 times the
  population -- 47.8 million of ethnicity, plus 49.0 million of religion, plus
  the religion denominator, summed as one question. `check_total` refused it.
  `Topic` therefore takes an optional column prefix, used *only* where a sheet
  is shared; where it is empty the columns are still whatever is left after
  the geography, which is what keeps Ethiopia working, since its ethnic-group
  columns are not named `ETH_`. That is the same trap the first version of
  this reader fell into, in the opposite direction. The upshot is that Myanmar
  gains religion as well as ethnicity: Buddhist 90.9%, Christian 7.2%, Islamic
  3.1%, Hindu 0.8%, from the 2014 census, which published religion even while
  withholding ethnicity.

* **Ukraine publishes its language table by rayon, and this map by oblast.**
  The 2001 census asked native language and the Bureau's sheet gives ten of
  them against a total -- but only at rayon level. All 25 oblast rows above
  them are blank, so Ukraine's first order carried nothing, and only 58 of 663
  areas reached a shape: the census romanises Ukrainian adjectivally where
  geoBoundaries uses the short exonym, so `BAKHCHYSARAYS'KYY RAYON` has to
  become `Bakhchysarai`, 661 times over. A suffix-stripping rule would bridge
  most of them and is precisely what `norm()`'s generic-word list refuses to do
  for a local generic word; it would also collapse `Luts'ka Mis'krada`, the
  city council, onto `Luts'kyy Rayon`, the district around it -- two places
  geoBoundaries draws as one shape.

  So `Country.sum_into` names a level the source lists and leaves empty, to be
  built from the level below. The file's own `ADM1_NAME` column says which
  oblast each rayon belongs to, which makes the addition the source's
  arithmetic rather than this map's invention; only areas with no figures of
  their own are built, so an area publishing directly keeps what it published.
  **27 of 27 oblasts now carry language, and the first order reconciles to
  48,121,632 against the census's own 48,121,632 exactly** -- Lviv 95.3%
  Ukrainian, Donetsk 74.9% Russian, Kyiv city 72.1% against 25.3%.

  **The rayons are summed and not published.** Emitting all 661 put 605 rows
  nowhere and 56 onto shapes by prefix and containment against an adjectival
  form. Most of those 56 are probably right, and that is what makes them the
  kind this map refuses: nobody can check them one at a time, an unmatched row
  is a visible gap, and a mis-matched one is invisible. Children are therefore
  added up *before* the level filter, so a level can feed its parent without
  appearing on the map itself.

  **A built denominator counts children that have no figures.** A rayon the
  source lists and leaves empty is still part of the oblast's population, so
  including its published total draws the remainder as an unaccounted share.
  Leaving it out would have let the sum reconcile perfectly against a
  denominator that had quietly shrunk to match it, and an incomplete oblast
  would have looked complete. Each such oblast is named in the log with how
  many of its children it was built from.

* **A widened bound is a claim, and it is narrowed when its evidence goes.**
  The refusal bounds moved onto `Country`, defaulting to the module's, because
  Ukraine's rayons fell short of their own totals in 105 of 663 cases by up to
  6.9% -- a hole in the source rather than a misreading, since the national row
  reconciled to 99.8% and 558 rayons agreed exactly. Both bounds were widened
  on that evidence.

  Publishing oblasts instead retired half of it. Only 3 of 27 oblasts fall
  short and the worst is 0.7%, so the *size* bound went back to the module's
  5%. Only the *share* bound stays widened, and for a different reason: 27
  areas is a coarse denominator, one oblast being 3.7% of the count, so three
  of them tripping a 10% test says almost nothing about whether the sheet was
  understood. Ukraine is still the only country that widens anything, and a
  test asserts both which bound and which country.

**Two boundary names are misspelled rather than differently spelled.**
geoBoundaries transposes Sagaing into "Saigang" and drops a letter from
Tanintharyi. Both are well-formed words, so nothing can detect them the way
mojibake announces itself; they are corrected in `common.MISSPELLED`, which
fixes the label a reader sees along with the join. Everything else in Myanmar
needs no alias at all: the census writes "KACHIN STATE" where the boundary file
writes "Kachin", and `norm()` drops the word "state" on both sides. Ukraine is
the opposite -- all 27 oblasts need declaring, because the Bureau romanises
from Ukrainian and geoBoundaries uses the English exonyms, and
"CHERKAS'KA OBLAST'" shares no surviving word with "Cherkasy Oblast".

**And Ukraine found a live defect in the join.** CGAZ draws both `Kyiv` and
`Kyiv Oblast` as first-order units; `norm()` drops "Oblast"; and the admin-1
lookup was a dict comprehension keyed on the normalised name. One silently
overwrote the other, so a capital of 2.95 million or the region around it was
unreachable, whichever the boundary file listed first. The lookup is now
grouped and the tie settled on an exact name -- the same test that picks
Cotabato province over Cotabato City.

**Indonesia is in this series and is not read from it.** Its workbook carries
no religion and no ethnicity, only a language sheet whose composition is
"first language: Indonesian / regional / foreign / sign" -- four buckets that
reconcile exactly to the total but name no actual language, since "regional"
holds all seven hundred of them. That is a true statement and not a language
breakdown, so Indonesia stays the gap it was: what is missing there is religion
by regency, and that still needs the BPS key.

### Viet Nam: collected, and published only for the whole country

Viet Nam's 2019 Population and Housing Census asked religion. Its questionnaire,
reproduced on page 330 of the results volume, puts it plainly:

> 7. Does [NAME] follow any faith/religion? IF YES: What is [NAME]'s
> faith/religion?

And it asked ethnicity, in the question above it. So this is not a country that
declines to count these things. It is a country that publishes the count for
itself and not for its provinces, which is a different gap and wants a
different word.

**Getting to the report at all.** The statistics office does not answer this
project from a GitHub runner, and the three refusals are not the same refusal:

* `www.gso.gov.vn` **times out** -- no response, on two different paths, in two
  separate runs, while every other host in the same run answered.
* `www.nso.gov.vn` and `nso.gov.vn` **reset the connection**. The General
  Statistics Office was restructured into a National Statistics Office in 2025,
  so this is the current host: it resolves, it is up, and it closes the socket
  on this client.
* `www2.gso.gov.vn` **does not resolve** -- but that one is a fact about a
  hostname this project guessed at, not about Viet Nam. It is recorded here
  because a guess that fails looks exactly like a source that is missing.

The report is reachable anyway, from the body named on its own title page:
UNFPA provided the technical assistance for the census and hosts
`Results - 2019 Population and Housing Census_full.pdf`, 6.8 MB and 380 pages.
That is a co-publisher rather than a mirror, which is why it is usable where
`citypopulation.de` would not be.

**What the report contains.** Its narrative body extracts as mojibake --
`dŚĞ ϮϬϭϵ WŽƉƵůĂƚŝŽŶ` for "The 2019 Population", a font carrying no usable
character map -- but Part III's data tables are set in a different font and
decode cleanly. In those tables:

| Table | Breakdown |
| --- | --- |
| 2 | Population by ethnic group, urban/rural and sex — **national** |
| 3 | Population by religion, urban/rural and sex — **national** |
| 5 | Population by age group and sex, for ethnic groups **and then** for provinces |
| 13, 18 | Two indicators, same stacked shape |

The word "religion" appears on five of the 380 pages: Table 3, and four pages
of questionnaire. There is no religion-by-province table to miss.

Table 5 looks at first like the cross-tabulation this map needs, because its
caption reads "BY AGE GROUP, SEX, ETHNIC, URBAN, RURAL, SOCIO-ECONOMIC REGION
AND PROVINCE, CITY". It is not. Page 198 prints a section header --

```
P r o v i n c e ,  c i t y
Ha Noi        2 133 354  1 133 036  1 000 318
Ha Giang        296 271    151 900    144 371
```

-- and repeats the same age-group columns for provinces after finishing the
ethnic groups. Two breakdowns stacked under one title, not crossed. The caption
could not settle that and reading the rows could, which is the only reason this
entry can say so.

One thing is banked for whenever a provincial table does surface: Viet Nam
prints its figures with **a space as the thousands separator**, and every row
carries Total, Male and Female. That is the South African problem exactly, and
the arithmetic reader in `scripts/fetch_census/south_africa.py` transfers to it
with `Total == Male + Female` as the constraint that picks the right reading.

### Thailand: a language table that cannot be a composition

Thailand's National Statistical Office refuses this project from every host
tried, and its open-data portal refuses the machine interface too:

* `www.nso.go.th` and `catalog.nso.go.th` answer **HTTP 418**, the teapot code
  some web application firewalls return to a client they have decided is not a
  browser.
* `portal.nso.go.th` answers **HTTP 403**.
* `statbbi.nso.go.th`, the statistical database, **does not resolve**.
* `data.go.th` answers **403 at `/` and at `/api/3/action/` alike**. That second
  one is worth recording: HDX is also CKAN and blocks its HTML pages while
  serving its API perfectly, so "the site blocks browsers, try the API" is a
  real pattern -- it simply does not hold here.

Getting past a 418 or a 403 means claiming to be a browser. This project does
not do that, for the same reason it does not do it to BPS.

That leaves one candidate, and it fails on its own contents rather than on
access. HDX carries **Thailand: Languages** from CLEAR Global, with a file per
administrative level -- `th_lang_admin1_v01.csv` is by province, exactly the
shape wanted. It cannot be used, for four reasons in ascending order of
seriousness:

1. **The shares are not a composition.** Bangkok is Thai `0.997` and Other
   `0.036`, which is 103.3%. Buri Ram is `0.972` and `0.239`, which is 121.1%.
   These are independent indicators that cannot be parts of one whole.
2. **The provincial detail is two columns.** The national file names five
   languages; the province file has Thai and Other. Most provinces read Thai
   `1.000`, Other `0.000` -- a map drawn from it would assert that Isan,
   Northern Thai and Malay-Yawi do not exist.
3. **There are visible errors.** Ang Thong's female literacy is `0.093` against
   a male `0.945`; the file rates its own `data_confidence` as Medium.
4. **It is the 2000 census**, and the file says so itself, in its own notes
   column: *"Province was established after the 2000 Population Census, the
   only Census for which language and literacy data were made publicly
   available."* Its population column (65,981,659) is a later figure again, so
   the language shares and the denominator are twenty years apart.

The fourth point is the one that answers the original question. It is not only
that `nso.go.th` will not serve this client: by the account of the people who
compiled this dataset, Thailand has made census language data public **once**,
for 2000. So Thailand is a gap about publication, like Viet Nam, rather than a
gap about access -- and the access problem is real too.

### South Africa: a table whose separator is a space

Statistics South Africa publishes Census 2022 through a portal at
`census.statssa.gov.za` that is a JavaScript shell: fetched, it returns 57,280
bytes of markup containing **no anchors at all**. Following links from it finds
nothing, the same way Indonesia's `sp2010` service finds nothing, and for the
same reason. What it does have is an `/assets/` path the shell does not affect,
and under it the *Census 2022 Statistical Release* (P0301.4) -- 113 pages, 3.6
MB, and the only public place four of these tables exist.

Five of its tables carry a province in every row, and they are not equally
good:

| Table | What it gives | As |
| --- | --- | --- |
| 2.2 | Population by province, four censuses | Counts |
| 2.4 | Population group by province | **Counts**, five groups and a total |
| 2.7 | Sex ratio by province | Males per 100 females, one decimal |
| 2.9 | Language spoken most often at home | Percentages, one decimal |
| 2.10 | Religious affiliation/belief | Percentages, one decimal |

That difference decides what the adapter claims. Population group is a count,
so it reconciles and it sums into a country. Language and religion are
percentages and nothing else, so they are stored as shares **with no count
attached**, and the build's rule that a parent is never summed from children
publishing shares without counts leaves South Africa's own religion and
language at the province level. The alternative was available and is worse: a
count reconstructed as 24,4% of 12,4 million people is out by up to six
thousand and carries no mark saying it was never counted.

**The thousands separator is a space.** So `2 884 511 3 124 757 84 363` is nine
words for three numbers, and nothing in the row says where one ends. Pakistan's
Table 9 posed the same problem and was solved by measuring the gaps between
words. Here the arithmetic solves it outright: the row prints five groups and
their total, so of the 3,003 ways to cut sixteen fragments into six numbers,
the published one is the one where the first five add up to the sixth. Every
province row has exactly one such reading, and two readings would be refused as
firmly as none.

That method needs no coordinates, which is the point. Gauteng's coloured column
is printed `44 3857` -- the space in the wrong place, four digits after it
where a thousands group has three. No rule about gaps or digit counts reads
that as 443,857. The arithmetic does, and the nine provinces then sum to the
published national figure for that column exactly.

**The national row does not add up.** Read the same way it yields nothing: its
five groups come to 61,988,316 against its own printed total of 61,988,314. Set
against the nine provinces, its Black African and Indian/Asian cells are each
one person high and its other four columns agree to the person. So the
provinces are internally consistent and StatsSA's national row is off by two.
The run reports both differences by name rather than widening a tolerance until
they disappear, and reads that row only under an allowance whose size was taken
from the discrepancy rather than chosen to make a check pass.

**Population comes from Table 2.2, not from Table 2.4's own total.** Table 2.4
excludes people whose population group was not specified, which makes its
Western Cape total 7,426,673 where the province holds 7,433,019. Shares should
be of the group question's own denominator; the population field should not be.

Two smaller things worth writing down:

* **The caption is not enough to find a table.** Every caption appears twice,
  over the table and in the LIST OF TABLES, and the contents entry comes first.
  The leader of dots that marks a contents entry wraps onto the following line
  for the longer captions, so `Table 2.9:` reads identically in both places.
  Every occurrence is therefore tried and the readers decide which one is a
  table, which works because each reader is strict about the shape it expects.
* **Median age by province is deliberately not read.** It exists, as Figure
  2.11, but only as a chart: the province names survive extraction as
  `Norther Cape` and `KwaZul u Natal`, and `North` is a prefix of two different
  provinces. Recovering the column order would be a guess, and a wrong guess
  gives Limpopo the Western Cape's median age while every number on the page
  stays plausible. An unmatched row is a visible gap; a mis-matched one is
  invisible and worse.

One join needed declaring. geoBoundaries' global composite spells the Northern
Cape **`Nothern Cape`**, a letter short, so the census's own spelling matched no
shape and that province carried nothing. It was fixed as an alias rather than a
looser matching rule, because "Nothern Cape" and "Northern Cape" differ by less
than "Eastern Cape" and "Western Cape" do -- anything lenient enough to bridge
the first would bridge the second, and put one province's people on another.

The alias made the data land but left the *label* wrong: entity names come from
the boundary file, and adapters never override them, so the map read "Nothern
Cape" over correct figures. The misspelling is now corrected where the shapes
are read (`common.respell`, beside the `repair()` that undoes geoBoundaries'
mojibake), which fixes the name a viewer sees and the name every source is
matched against at once. Nothing is inferred there either: each correction is
declared with the country it belongs to, because "Nothern Cape" is a
well-formed string that only a reader who knows the place can tell is wrong.

Two label decisions follow from having both this release and the Factbook
describing one country. The Factbook writes South Africa's languages as
compounds -- `isiZulu or Zulu`, `Sepedi or Pedi` -- so those are declared
aliases of the census's own spelling, and the province panels and the country
panel now name the same language the same way. But the bare names `Ndebele` and
`Sotho` are **not** folded: Ndebele is Northern Ndebele in Zimbabwe and
Southern Ndebele in South Africa, two different languages, and Sotho is used
for both Sesotho and Sepedi. The Factbook's compounds are safe precisely
because they only ever appear in the South African entry.

## Joining a row to a shape

Every adapter row has to find one boundary polygon. Names alone cannot do it:
district names repeat, and a lookup keyed on name keeps whichever shape it saw
last, which makes one district unreachable and lets the other quietly wear its
twin's figures. So a row that names its parent state is matched only inside
that state, and a row that does not is matched only against names that are
unique country-wide.

**Names are compared word by word.** `norm()` squashes a name into one run of
letters so two spellings can be compared as one key, and a substring test on
that run reads straight across the gaps between words. "Anta" is four letters
and sits inside "santacruz", so Argentina's Santa Cruz was joined to a
department called Anta 406 km away, and Santa Anita to the same shape 817 km
away. "Tala" starts "talampayanationalpark", so Talampaya National Park went to
Tala, 835 km away. Both loose passes now line up whole words instead:

* The **prefix** pass anchors at the first word — "Mymensingh Division" to
  CGAZ's "Mymensingh", "Alif Alif Atoll" to "Alif Alif".
* The **containment** pass allows a run starting anywhere — "Canton of Zurich"
  to "Zurich", "Provincia de Bocas del Toro" to "Bocas del Toro".
* The last word may run up to three characters short of its counterpart, which
  is an inflected or adjectival ending and not a different word: "Stockholm"
  against "Stockholms", "Plzeň" against "Plzeňský", "Northeast" against
  "Northeastern". At five it would reach "Talampaya" from "Tala".
* A hyphen is read **both ways**, because neither reading is right on its own.
  Joined, CGAZ's "Bío-Bío" meets a source's "Biobío" and Timor-Leste's
  "Oe-Cusse" meets "Oecusse". Split, an Arabic article the other side leaves
  off becomes its own word and the run simply starts after it: "Al-Basrah" to
  "Basra", "An-Najaf" to "Najaf", "Ar-Raqqa" to "Raqqa".
* A word under four letters counts only where the match is anchored at the
  first word. "Lae Atoll" to "Lae" is evidence; "Fes" three letters into "Oued
  Fes" is a different commune.

Across every adapter this moved 67 joins from a loose pass to an exact one and
removed 36 loose ones, a net gain of 31. Among the joins it removed: Budapest
from Pest, Oberbayern and Niederbayern from Bayern, Rheinhessen-Pfalz from
Hessen, and North and South Aegean from a single shape called Egean.

**`norm()` keeps letters of every script.** It reduced a name to `a-z0-9`,
which does not delete an accent — NFKD already did that — but does delete any
letter that is not Latin at all. 693 boundary names normalised to the empty
string, 352 Russian and 256 Tunisian second-level units among them: unmatchable
by name, and all colliding on one key. The same rule deleted the letters NFKD
cannot take apart because they are not a letter plus a mark — "Østfold" became
"stfold", which is a substring of "vestfoldogtelemark", and Norway's Østfold
was joined to Vestfold og Telemark. Those letters are now folded (ø→o, đ→d,
ß→ss, æ→ae) and everything else alphanumeric is kept as itself. Cyrillic stays
Cyrillic rather than being romanised, because a transliteration this code
invents is a guess about a name and the name itself is not.

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

**Rival rows for one shape.** The uniqueness rule works one row at a time, so
it cannot see several rows of the same adapter all reaching the same boundary —
and whichever came last silently overwrote the rest. England's East, Mid, North
and West Devon all reached a shape called Devon, and the source has no plain
"Devon" row at all, so Devon wore West Devon's figures and the other three
vanished. Texas's Jackson County reached a shape called Jack. 1,324 rows were
being lost this way.

A second pass now settles each shape's rivals by how much evidence each row
brings: a name that matched outright beats one that arrived through a fragment
of itself, and a match confined to the state the row named beats one that
searched the whole country. So "Rotherham" keeps its shape and "Rother" is
refused; "Ostrobothnia" keeps its own and Central and North Ostrobothnia are
refused; "Bariloche" keeps its own and "Bariloche Army Garrison" is refused.
Where nothing separates the rivals, none of them may claim it — four Devons and
no way to tell which is the shape's is exactly the case for a visible gap.

Rows that all matched *outright* are left alone, because there the rivalry is
usually a source listing one place twice: Wikidata carries both "Ancasti" and
"Ancasti Department", and "Department" is a word `norm()` drops.

That exemption has a cost, and the Philippines is where it came due. "Cebu
City" and "Province Of Cebu" are two places, not one place listed twice, and
they reach this pass looking exactly like Ancasti: both outright, differing
only by a word `norm()` drops. Last one wins, and a city's figures land on a
province with nothing visible to show for it. Nothing here can tell those two
cases apart from the names alone -- so the Philippine fix was upstream, where
the adapter knows the boundary file folds those cities away and can say so
before the matcher ever sees the row.

**Then the same question was asked of every adapter, and the answer was 113
more.** `scripts/audit_claims.py` runs the real matcher over the real
boundaries and reports every shape that one file's rows claim twice. The names
could not sort them, but a different question could: *do the rivals agree?* One
place written twice publishes the same figures both times, so whichever wins,
the map is right. Two places publish different figures, and the loser's are
being discarded without trace. That test needs no knowledge of any country.

It found 113. `norm()` drops "Region", "Oblast" and "City" exactly as it drops
"Department", so a capital and the region named after it arrive under one key
looking precisely like a duplicate listing:

| shape | rival rows | published |
| --- | --- | --- |
| Moscow Oblast | Moscow / Moscow Oblast | 13,274,285 vs 8,594,454 |
| Kyiv | Kyiv / Kyiv Oblast | 2,952,301 vs 1,795,079 |
| Morogoro | Morogoro / Morogoro Region | 150 km apart |
| Xoxocotla | Morelos's / Veracruz's | 74.6% vs 88.4% Catholic |

The exemption now requires agreement. Ancasti keeps it -- Wikidata's two items
both say 3,302 people, so nothing is at stake -- and a rivalry that
contradicts itself is ranked on evidence or refused like any other. 108 shapes
lose a figure and none gains one; 104 of the 108 are Wikidata population
estimates, and two are Mexican municipios where a religion breakdown was
landing on the wrong state.

**What decides it is not which rival is named exactly as the shape is**, and
that is worth recording because it is the plausible fix and it is backwards.
An exact name settles a tie between two *shapes* -- "Cotabato" picks the
province over "Cotabato City". Between two *rows* it inverts, because boundary
files drop the generic word by convention: CGAZ's Argentine second level *is*
the departments and names them "Andalgalá", so the exactly-named rival is the
town of 3,300 and the one saying "Andalgalá Department" is what the shape
draws. Measured before it was written, that rule would have replaced 108
honest gaps with 104 confident mis-matches.

111 rows across 32 countries are refused this way, and each one is named in the
build log. Much of what it removes is Wikidata entities that are not
administrative units at all — army garrisons, national parks, Roman Catholic
dioceses, parliamentary constituencies — which had been taking the shape of the
place they are named after.

**What is still wrong here.** Six Ethiopian zones each contain the words
"special woreda" and CGAZ has one shape named exactly that; five are now
refused, but Argobba's still lands on it, because its parent resolved and the
others' did not. That is the rule preferring more evidence, and the evidence is
still not about the right thing.

**38 rows are still refused as ambiguous**, in Argentina (20), Vietnam (13),
Colombia and Thailand (2 each) and Mexico (1). Each names a state that resolves,
holds no shape of that name, and shares its name with two to eleven shapes
elsewhere — eleven Argentine provinces have a "Capital Department". A
coordinate settles fifteen of them, but the shape it picks usually contradicts
the state the row itself names, so the two signals disagree and neither is
strong enough to overrule the other. They stay visible gaps.

## Summing a parent from its children

Ladakh became a union territory in 2019, so the 2011 census that supplies
India's district figures never published a row for it — while publishing both
of its districts. A territory whose every constituent part is measured should
not read as unmeasured, so `build_entities.py` sums one when it can.

**The control is the parent's own published population.** Leh (133,487) and
Kargil (140,802) sum to 274,289, which is exactly the population Wikidata gives
Ladakh — and Wikidata is not where the district figures came from, so the two
numbers are genuinely independent. A parent with no published population of its
own is not filled at all: there would be nothing to check the sum against.

The refusals are as much the point as the sums. Of sixteen candidates, five
were filled and eleven were not:

* **Australia, nine states.** The LGA records carried religion and no
  population, so their populations summed to zero and weighting by nothing
  would have produced a state figure with no basis at all. Fixed at the source
  since — see below — and the states now carry their own figures, so there is
  nothing left to sum.
* **Wales.** Its 22 children sum to 3,107,513 against a published 1,168,000.
  Whatever those two numbers count, it is not the same people.
* **England, Telangana, Singapore's five regions, American Samoa.** Partial
  coverage — 9 of England's 150 children have no religion, 24 of Telangana's 33
  have none. This is the dangerous case, because the sum would look whole and
  describe only part of the territory.

**Percentages are recomputed against the denominator the children used, not
against population.** Mexico publishes indigenous-language shares of the
population aged three and over, and New Zealand's ethnicity responses outnumber
its people because one person may give several. The denominator is backed out
of each child's own rows — from its largest group, whose percentage carries the
least rounding error — and summed. Chatham Islands' rolled-up ethnicity totals
149.5%, which is what its child says and what the panel is built to show.

Every summed figure carries a note on the record saying so, how many children
it came from, and the two population numbers side by side, because a figure
nobody published is a different kind of claim from one somebody did. A value
marked `not_collected` is never filled: that is a statement about the country,
not a gap.

### And up again, to the country

The same sum runs a level higher, from first-level divisions to the country.
It behaves differently there, and the difference is worth stating: **it never
fills a gap.** Every country record already carries a Factbook composition, so
every sum at this level *replaces* a published figure.

That is worth doing only because the two are not equally good. The children are
a national statistical office's own count, itemised; the Factbook figure is an
older estimate that lumps the tail into "other". Left apart, the map
contradicts itself between zoom levels — Finland read 85.9% Finnish nationally
and 83.5% when you added up the nineteen regions drawn inside it.

Five figures are summed this way: Finland's and Switzerland's language,
Estonia's ethnicity, and Sri Lanka's religion and ethnicity.

| | published | summed from divisions |
|---|---|---|
| Finland, language | Finnish 85.9%, Swedish 5.2%, *other 7.2%* | Finnish 83.5%, Swedish 5.0%, then Russian, Estonian, Ukrainian, Arabic… |
| Switzerland, language | German 62.1%, French 22.8%, Italian 8.0% | German 61.1%, French 22.5%, Italian 7.8%, and a 20.5% *Other languages* the estimate does not carry |
| Estonia, ethnicity | Estonian 69.1%, Russian 23.7% | Estonians 68.5%, Russians 20.3% |
| Sri Lanka, religion | Buddhist 70.2%, Muslim 9.7% (2012) | Buddhist 69.8%, Islam 10.7% (2024) |

**The displaced figure goes into the note, not the bin.** It is the only
independent statement about the country, and the sum has nothing else to be
checked against; overwriting it silently would make the control a casualty of
the thing it was there to check.

**What the gate refuses here, and why it is a different question.** The 2%
population bound is the same one used a level down, but it is doing something
else: the parent's population is a current estimate and the children's is a
census, so it refuses any country whose census has drifted — Mexico by 3.6%,
New Zealand by 3.2%, Nepal by 6.9%, Australia by 7.5%. Those are vintage gaps
rather than faults. Widening the bound to admit them is a separate decision
from this one, and the bound is left tight so nothing is rewritten on a looser
rule than the one that has been tested.

Everything else is refused for incompleteness, which is the dangerous case: 12
of Canada's 13 provinces have no religion, 29 of China's 33 units no ethnicity,
14 of the Philippines' 17 regions no religion. A sum across those would look
whole and describe a fraction of the country.

Percentages are not expected to land on 100. Finland's summed language totals
98.8% against children ranging 99.1–99.9%, because the country has some 166
language groups and the long tail rounds to 0.0% one group at a time; the
counts reconcile to the person, 5,652,881 either way. Switzerland's totals
118.7%, because a Swiss resident may name up to three main languages, which is
what its cantons say too.

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
