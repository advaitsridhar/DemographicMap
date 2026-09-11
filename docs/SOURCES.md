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
| UK | ONS Census 2021 via Nomis (TS021, TS030) | local authority, county | **England and Wales only** — Scotland and Northern Ireland are the two rows below. Religion is voluntary, so "Not answered" is kept as its own category. TS021 is returned at two nesting levels at once and only the leaves are read; summing both counted every person twice. |
| Scotland | Census 2011 Key Statistics `KS201SC` / `KS206SC` / `KS209SCb` (NRS) | council area | Fourteen years older than England and Wales, and stamped 2011 on every figure rather than smoothed. The 2022 results are still only in a flexible table builder. Ethnicity reads the leaves; language reads the one block of `KS206SC` that is a composition. |
| Northern Ireland | NISRA Census 2021 `MS-B01` / `MS-B12` / `MS-B20` | local government district | Religion is the one **held** (`MS-B20`, 32 denominations), not the "religion or religion brought up in" of `MS-B23`/`B24` that is the province's more familiar figure — a different question, and this map has no field for it. Language is main language of residents aged 3+, not knowledge of Irish or Ulster-Scots. |
| Ireland | CSO Census 2022 via PxStat, `SAP2022T2T4LEA22` / `SAP2022T2T2LEA22` | local electoral area | Religion at this geography is **four categories** — Catholic, Other religion, No religion, Not stated — so "Other religion" holds the Church of Ireland, Presbyterians, Orthodox and Muslims together and a filter for Christianity reads an Irish area at its Catholic share. Language is declared, not filled: the census asks which foreign languages a person speaks (English absent) and whether they can speak Irish (an ability). |
| Canada | StatCan 2021 Census Profile, catalogue 98-401-X2021008 (zipped CSV) | province, economic region | Religion is asked once a decade (2021 yes, 2016 no). "Visible minority" is an Employment Equity Act category, not an ethnicity question; mother tongue is 100% data, the other two 25% sample data. The 76 economic regions are what geoBoundaries draws as the second level. Read from the downloadable profile, because www12's REST service answers non-browser clients with an HTML shell. |
| Brazil | IBGE SIDRA tables 9514 / 9605 / 9537 | state, municipality | *Cor ou raça* is self-declared skin colour (branca, preta, parda, amarela, indígena) — not equivalent to ethnicity elsewhere. Religion is a count of persons aged 10 and over, the universe the 2022 census asked. |
| EU | Eurostat `demo_r_pjangrp3`, `demo_r_pjanind3` | NUTS-2, NUTS-3 | Population and age everywhere; **no** ethnicity or religion — those are national census questions and only some states ask them. |
| Australia | ABS 2021 Census `C21_G14`, `C21_G08`, `C21_G13` | state, LGA | Ancestry is multi-response (up to two per person), so shares are of responses and exceed 100%. No ethnicity question exists. There is no state-level table: the states are read off the LGA table's own `STATE` dimension. Population is the religion table's total, which is the region's counted persons. Language used at home (G13) is held at the Total of its proficiency and sex dimensions; its "Other Languages Total" row sits beside every language under it and is found by arithmetic, and only categories marked "... Total" can be parents in the code tree, because "Speaks English only" is coded `1` and is no parent of `1403` Afrikaans. |
| Poland | GUS NSP 2021 final tables (three workbooks: przynależność wyznaniowa, narodowo-etniczna, język używany w domu) | voivodeship, powiat | Religion is a seven-level classification tree, cut once: Christian branches at level 5, other religions at level 4, no religion at level 3, and the fifth of Poland that declined to answer at level 2, kept as "Not stated". National-ethnic identification and home language allow two answers and are carried as multi-response; identifications and languages without an English name are summed as Other. Column A of every sheet is empty. |
| Malaysia | DOSM OpenDOSM `population_state` / `population_district` CSV | state, district | Annual population estimates by ethnicity carried forward from Census 2020, in thousands; the latest year is read and the records say "estimate". The non-citizen row is DOSM's own category of the resident population and is kept. |
| Kenya | KNBS 2019 Census Volume IV, Table 2.30 (openAFRICA mirror) | county | Religion for all 47 counties, replacing the Afrobarometer survey rows; ethnicity stays Afrobarometer's. KNBS's own site fails TLS verification (incomplete chain) and this project does not turn verification off. |
| Thailand | NSO 2000 Population and Housing Census, provincial final reports (`web.nso.go.th/pop2000/finalrep/`), transcribed in the Wikipedia article *Nationality, religion, and language data for the provinces of Thailand* | province | Buddhist, Muslim and Christian shares for 2000 as printed, read through the MediaWiki API because the NSO's own hosts refuse this client; the rest of 100% is one 'Other or not stated' group; an N/A is absent, not zero. 76 of 77 provinces: Bueng Kan was carved out of Nong Khai in 2011 and has no 2000 row. Nationality is citizenship and is not read as ethnicity; the 'linguistic minorities' cells name a few languages and not the rest, so language stays a gap. `scripts/fetch_census/thailand.py`. |
| Kazakhstan | Bureau of National Statistics, 2021 National Population Census, religious affiliation by region, transcribed in the Wikipedia article *Religion in Kazakhstan* | region | The percent columns are read (one count in the article is mistyped; its percent is not). The article lists 16 regions and omits Shymkent (a city of republican significance since 2018); the boundary file draws the 2017 layout in which Shymkent sits inside South Kazakhstan Region, so the article's Turkistan Region is deliberately not matched to that shape and South Kazakhstan stays a visible gap: 15/16. `scripts/fetch_census/wiki_census.py`. |
| Kazakhstan (ethnicity) | Bureau of National Statistics, *Population by ethnic groups of the Republic of Kazakhstan at the start of 2025* (series 18, 27 March 2025), workbook committed under `data/raw/kazakhstan/` because the Bureau's site offers no file link | region, district | Register-based population at 1 January 2025 carried forward from the 2021 census, 73 ethnic rows, and the record says it is not a census count. The workbook's 20 regions are summed into the 16 shapes of the 2017 layout (Abai into East Kazakhstan, Jetisu into Almaty Region, Ulytau into Karaganda, Shymkent into South Kazakhstan), exact because these are counts, and every column is checked against its own total. Districts keep the Bureau's Cyrillic name with a transliteration as alias; `RENAMED` declares the shapes the boundary file still draws under a superseded name (Zelenovskiy for Bäiterek, Tselinniy for Gabit Musrepov, and so on). Almaty and Shymkent get their city totals as their one second-level shape; Astana has none. 173 of 174 district shapes filled; the boundary file draws Jambyl's Zhualy district twice and the second copy stays empty. `scripts/fetch_census/kazakhstan.py`. |
| Cambodia | NIS General Population Census of Cambodia 2019, religion by province, transcribed in the Wikipedia article *Religion in Cambodia* (2008 and 2019 columns; 2019 read) | province | Buddhism, Islam, Christianity, Others as printed; 25/25 with four spellings declared as aliases (Bantey Meanchey, Kratie, Takeo, Tbong Khmum). `scripts/fetch_census/wiki_census.py`. |
| Angola | INE Angola, Recenseamento Geral da População e Habitação 2024, *Relatório dos Resultados Definitivos*, Quadro 6.1 (grupos étnicos ou tribos), Quadro 6.2 (língua materna) and Quadro 7.1 (religião ou espiritualidade) | province | Counts of the population aged 2 and over for all three fields, replacing the Afrobarometer survey rows on 13 provinces and filling the five the survey did not reach: 18/18. The report is a PDF whose tables wrap over two pages and print thousands with spaces, so the reader takes each word with its x-coordinates from pdfplumber, joins digit groups closer than 4.5 pt into one figure, refuses a row that does not carry exactly the expected number of figures, and checks every province's groups against its own total. The column order was fixed from the header words' positions, not their reading order (on 7.1 *Bom Deus* is the second column, *Universal do reino de Deus* the seventh; on 7.1's second page *Testemunha de Jeová* precedes *Metodista*). The report's 21 provinces are summed into the 18 shapes of the 2011 layout: Cuando and Cubango into Cuando Cubango, Icolo e Bengo into Luanda, Moxico Leste into Moxico. Religion keeps the report's fourteen denominations apart as printed. `scripts/fetch_census/angola.py`. |
| Mali (RGPH5) | INSTAT, 5ème Recensement Général de la Population et de l'Habitat 2022, rapport thématique *Caractéristiques culturelles de la population*: Tableau 2.03 (religion by region), annex Tableau 5 (ethnie by region), annex Tableau 6 (langue maternelle by region) | region | Replaces the Afrobarometer survey rows for religion and ethnicity and the 2009 census for mother tongue: 9/9. The report tabulates the 2023 layout of 19 regions and Bamako; the boundary file draws the 2012 layout of 8 and Bamako, and each new region was carved whole from one old one, so the shapes are sums, taken on counts rebuilt as a percent of each region's printed population. The annex pages are stored upside down and pdfplumber reads every cell mirrored with wrapped cells in fragments, so cells are read from the ruling lines, each token turned back round, and labels recognised by the letters they are made of. Checks: each region's shares sum to 100, the regions' populations sum to the printed total, and the national row rebuilt from the regions agrees with the printed one (to 0.02 on Tableau 5; Tableau 6's printed Bambara and Tamasheq differ from its own regions by 0.12 and 0.14, the report's arithmetic). Ethnicity is of the Malian population (21.20 million of 21.35 million residents); mother tongue of the 19.14 million the table covers, whose age floor the report does not state on the page. `scripts/fetch_census/mali.py`. |
| Peru | INEI, Censos Nacionales 2017, *Perú: Perfil Sociodemográfico* (Lib1539): Cuadro 2.64 (lengua materna aprendida en la niñez by department), Cuadros 2.78 to 2.81 (population professing the Catholic faith, the Evangelical faith, another religion, none, by department) | department | Fills a country that had nothing: 26/26 (24 departments, Callao, and Lima as its two shapes, Provincia de Lima and Región Lima, with the book's whole-Lima row used as a check). Mother tongue is of the population aged 5 and over, religion of 12 and over. Figures are printed with spaces for thousands and two of the religion tables in a font pdfplumber reads letter by letter, so each row is read from word positions: tokens closer than 4.5 pt are one cell, and a department is recognised by the letters of its name. Checks: every printed share against its count and total, the four religion tables agreeing on each department's total and summing to it, the two halves of the language table summing to the total. Ethnic self-perception is printed by department only as four graphics and is not read. `scripts/fetch_census/peru.py`. |
| Zimbabwe | ZIMSTAT, 2022 Population and Housing Census Report: Table 2.14(c) (religion by province, both sexes) and Table 2.17 (mother tongue by province) | province | Replaces the Afrobarometer survey rows for religion on all 10 provinces and adds mother tongue; ethnicity stays the survey's, since the report prints it for the country only (Table 2.15). Comma-thousand counts read as text; each religion row sums to its printed total, each language row sums across provinces to its printed total, and each province's languages sum to the printed province total. The mother-tongue table covers 13,913,253 of 15,178,957 residents and the page does not state its age floor. `scripts/fetch_census/zimbabwe.py`. |
| Burkina Faso | INSD, 5e RGPH 2019, *Volume des tableaux statistiques*, Tableau I.22 (population résidente par région selon la religion, en %, with each region's population) | region | Replaces the Afrobarometer survey rows for religion on all 13 regions. Shares to one decimal applied to the region's printed population; the thirteen populations must equal the printed national 18,171,751 and the national shares rebuilt from the regions must agree with the printed ones. The volume prints the principal language spoken by milieu only and no ethnicity, so those fields are untouched. `scripts/fetch_census/burkina.py`. |
| South Korea | Hankook Research, *2025 Religion Perception Survey* (Weekly Report No. 358-3, 3 December 2025), page 8: religion by residence region, the religion question pooled from the 22 waves of the biweekly "Yeoron sok-ui Yeoron" web panel, January to November 2025 (23,000 adults aged 18 and over, weighted by region, sex and age) | province | A survey, not a census, and the map's one stated exception to the rule that a figure coarser than the shape is not spread: the report's seven residence regions cover the seventeen provinces, and each province carries its region's figure by the map owner's decision, with the note naming the region and how many provinces share it. Whole percentages, 2025 column; "other religions" is the printed "has a religion" less Protestant, Catholic and Buddhist. Lowest authority for Korea: the 2015 census (KOSIS, keyed API) replaces it when read. `scripts/fetch_census/korea_survey.py`. |
| Czechia | ČSÚ SLDB 2021 open data (`sldb2021_narodnost.csv`, `sldb2021_vira.csv`, `sldb2021_jazyk1.csv`) | kraj, okres | Nationality is voluntary and allows two answers; the file counts every declaration and has no not-stated row, so it is carried as multi-response. Religious belief partitions the population across 78 rows, registered churches and write-in beliefs alike; a written "catholic" is kept apart from the Roman Catholic Church's count and a written "atheism" counts with no religious belief. Mother tongue is read from the single-mother-tongue file, and people with two mother tongues or a language outside its thirteen are the total less its rows, kept as one labelled bar. Okresy are named in Czech where geoBoundaries has English (Praha-východ / Prague-East), carried as aliases; the okres-to-kraj table is in the adapter because the rows do not carry it. |
| Croatia | DZS Popis 2021 final results, workbook `popis_2021-stanovnistvo_po_gradovima_opcinama.xlsx` (sheets 1, 2, 4) | županija, grad/općina | One layout for all three tables: a bilingual header (Croatian over English) with a count and a percent column per category, read from the header rather than declared; county rows interleaved with their towns and municipalities; a dash is zero. Each table partitions the population, Other, Not declared and Unknown included, and a row that does not sum to its total stops the build. Counties are named as geoBoundaries names them in English, with the Croatian as an alias; units are composed as the bureau writes them, type first ("Grad Samobor", "Općina Bibinje"). The workbook lists the City of Zagreb by its 17 city districts, which are skipped, the city coming from its own county row. The boundary file's spellings (a dozen typos, Istria's bilingual names, two islands each drawn as one town) are declared as aliases; 545 shapes for 556 units, 543 matched. |
| Bosnia and Herzegovina | BHAS Popis 2013, Book 2 workbooks `K2_T2_B` (ethnicity), `K2_T5_B` (religion), `K2_T6_B` (mother tongue) under `popis.gov.ba/popis2013/doc/Knjiga2/BOS/` | entity, canton | One layout for all three: Level, Area (Bosnian over English), Sex, Total, then the categories; the Total row of each territory is read and matched by its Bosnian name. The two entities and Brčko District are published at both levels, since geoBoundaries draws Republika Srpska and Brčko as their own second-level shapes beside the ten cantons: 3/3 and 12/12. The bureau's 'Islamska' and 'Muslimanska' religion columns are summed into Islam (both are Islam; the build refuses a group beside its parent) and the note says so; ethnonyms given as a religion, and 'Orthodox' given as an ethnicity, are kept and marked. A row that does not sum to its Total refuses. Republika Srpska's institute published a different reading of the same count; these are the Agency's figures. `scripts/fetch_census/bosnia.py`. |
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
| India | Census 2011 tables C-01, C-01 Appendix, C-16 | state, district | No public API — per-state workbooks from the censusindia.gov.in NADA catalogue. 2011 is the latest round; the next census was postponed. The Appendix names the religions inside "Other religions and persuasions" (Donyi-Polo, Sarna, Sanamahi …) for states only. 562 of 735 district shapes carry figures. The other 173 each say why: 98 are districts the census never enumerated, and 75 are districts that have since lost territory, so the 2011 row counts people who no longer live in the shape. Telangana and Ladakh have state figures summed from the ten and two districts the census did enumerate, and Andhra Pradesh and Jammu and Kashmir carry the residual rather than the undivided state. |

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

### What is inside "Other religions and persuasions"

C-01 publishes eight categories, one of which is a residual, and in four states
that residual is the third or fourth largest answer there is: Arunachal Pradesh
26.2% (362,553 people), Jharkhand 12.8% (4,235,786), Meghalaya 8.7% (258,271),
Manipur 8.2% (233,767). Nationally it is 7,937,734 people, 0.66%.

The Registrar General breaks it up in table **C-01 Appendix**, *Details of
religious community shown under 'Other religions and persuasions' in main table
C-01* (NADA 11398), which names the religions inside it — Donyi-Polo, Sarna,
Sanamahi, Khasi, Niamtre and scores more, nearly all Adivasi, and no other
census on earth names them. `india_census.py --level state` reads it and
substitutes those religions for C-01's single residual row; named plus a
labelled remainder is C-01's figure exactly, so the composition still sums to
the state's enumerated population, which the adapter checks.

**It is published for India and the states and nothing finer.** The sheet has a
district column and it reads `000` on every row — the reader refuses if it ever
does not, because the note it publishes on every state record says no
district-level figure exists. So a district's religion panel keeps the undivided
residual, and says why.

Its TLS is worth knowing about: censusindia.gov.in serves its leaf certificate
without the intermediate above it, which urllib reports as *unable to get local
issuer certificate*. That is not a reason to stop verifying. `probe_tls.py
--chain` fetches the missing intermediate from the certificate's own Authority
Information Access extension and verifies against it plus the public roots, and
`http_get(..., aia=True)` is the same repair for adapters. Certificate
verification is never disabled.

### Mother tongue: the official C-16 workbooks

Table C-16 (population by mother tongue) is a separate publication from C-01 and
is not in the CSV extract. It is now read from the Registrar General's own
workbooks, checked into `data/raw/india/c16/` because there is no API to fetch
them from — `scripts/fetch_census/india_language.py` reads whatever is present.

The all-India workbook (`DDWC16STMTMDDS0000.XLSX`) carries every state, so all 34
states enumerated in 2011 have a mother-tongue composition, and Telangana and
Ladakh have one summed from their districts' rows. All 35 per-state workbooks
are present, giving 562 of 735 districts. The 173 without a figure are
census-vintage gaps, not missing files: **91** are districts created after 2011,
**75** are districts that have lost territory to one of those 91, **6** are the
successors of the three districts that have been subdivided since, and **1** is
not a district at all — geoBoundaries draws a feature in Jammu and
Kashmir named, literally, "DATA NOT AVAILABLE", which is 268 disjoint fragments
totalling about 390 km², the slivers between the district polygons. All 173 carry
an explicit reason on population, religion and language; the 91 name the year
they were created and the 2011 district they were carved from
(`CREATED_AFTER_2011`, checked against the census's own district list on every
run), and the 75 name what was taken out of them and how much ground they have
left (`LOST_TERRITORY_SINCE_2011`, checked against `CREATED_AFTER_2011`).
Nothing is carried down into any of them — a new district is a *part* of an old
one, the district that kept the name is another part, and the rule that a figure
coarser than the shape is not spread across the shape's members applies to both.

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
* Three 2011 districts have since been subdivided so thoroughly that their
  names survive on no shape at all (Jaintia Hills, Karbi Anglong, Warangal).
  Their figures are **not** spread across the successor districts -- the census
  never measured those areas separately, and apportioning them would be an
  estimate presented as a measurement. The successors carry an explicit gap
  saying so.
* 75 more lost territory without losing their names, and are the subject of the
  next section.
* Telangana (2014) and Ladakh (2019) postdate the census entirely. They now
  carry a figure summed from the districts the census did enumerate, and the
  states they were separated from carry the residual; see below.

### The district that keeps the name is a fragment too

This is the error that took longest to see, because it looked exactly like data.

When Jagtial, Peddapalli and Rajanna Sircilla were carved out of Karimnagar in
2016, three new shapes appeared on the map with no figures and an explicit
reason. The fourth shape kept the name Karimnagar, kept the 2011 census row,
and lost three quarters of its ground: 2,132 km² of the 9,103 km² the census
measured. It went on showing 3,776,269 people, 85.6% Hindu, sourced and dated,
on a district that holds about a quarter of them. The blanks beside it were
honest about what was not known. The number was not, and nothing on the panel
said so.

`SUBDIVIDED_SINCE_2011` had the principle right and applied it to three
districts only. Warangal's six successors carry no figure because the census
measured the undivided district and the map cannot split it. **Karimnagar is
the same case**; the only difference is that one of its fragments kept the
name. `LOST_TERRITORY_SINCE_2011` now says so for every one of them.

**How many, and where.** Measured against the CGAZ shapes this map draws with
-- each district's area against its own area plus the area of every shape
`CREATED_AFTER_2011` declares was carved out of it -- 75 districts in 16 states
were in that position, carrying 172 million people's worth of 2011 figures:

| state | districts | state | districts |
|---|---|---|---|
| Gujarat | 10 | Tripura, Mizoram, Delhi, Meghalaya | 3 each |
| Telangana, Arunachal Pradesh | 8 each | Punjab, Madhya Pradesh | 2 each |
| Manipur | 7 | Maharashtra | 1 |
| Chhattisgarh | 6 | | |
| Tamil Nadu, Uttar Pradesh, Assam | 5 each | | |
| West Bengal | 4 | | |

The worst were Mahbubnagar (18% of its 2011 ground, 4,053,028 people),
Karimnagar (23%), Raipur (25%), Adilabad (25%), Medak (26%) and Durg (27%).
The largest single figure in the wrong place was Thane's 11,060,148, on 44% of
the district Palghar was taken out of in 2014.

**Why there is no "close enough" threshold.** The obvious softening -- keep the
figure where the district lost only a little -- cannot be done honestly with
what is measurable here. The measurement is of *territory* and the error is in
*people*, and the two do not track each other in the same direction twice:
Rangareddy kept 52% of its ground and lost Medchal-Malkajgiri, a small dense
suburb of Hyderabad holding close to half its population; Upper Subansiri kept
90% of its ground and the part it lost is high Himalaya with almost nobody in
it. A threshold set anywhere between them would be a guess wearing a
tolerance's clothes.

What area *can* settle is the binary question, and the measurement turns out to
be unambiguous about it: every district in the table retained between 18% and
90% of its 2011 extent, and every other Indian district retained 100%. There is
nothing in the gap to draw a line through, so the line is not drawn on area at
all -- it is "did a district get carved out of this one", which
`CREATED_AFTER_2011` already declares. `check_lost_territory` requires the two
tables to be exact mirrors of each other on every run: a predecessor named
there without a measurement here would leave a shape wearing the undivided
figure, and a measurement here with no predecessor there would delete a good
one.

**What is kept.** Hyderabad, and it is the check that the rule is not simply
deleting everything. The 2016 reorganisation created Medchal-Malkajgiri out of
Ranga Reddy, not out of Hyderabad, and left Hyderabad district alone; no entry
in `CREATED_AFTER_2011` names it, so nothing was carved out of it and its
figure stands. The Registrar General's own C-01 workbook lists 16 tehsils under
Hyderabad in 2011, and the present-day district has the same 16 mandals. Of
Telangana's nine districts that had figures, that is the one that survives.

The area measurement is *not* what settles Hyderabad, and it is worth saying
why. CGAZ draws the district at about 281 km² where the census gives 217 —
Hyderabad's published density of 18,172 people per km² over 3,943,323 people —
a 30% overshoot that is simplification on the smallest shape in the state
rather than a boundary change. Area is used for the districts that lost ground
because there it is answering a large question with a large margin; for a
district that lost none, the evidence is that none was taken.

**The extract was checked against the Registrar General's own workbook.** The
same exercise made it possible to test the community CSV mirror this adapter
reads against the official C-01 file for Andhra Pradesh, which is not where the
mirror came from. All 23 districts agree in all nine columns — population and
the eight religions — with no disagreement anywhere, and the workbook's 1,128
tehsil rows sum to its district rows to the person. `NATIONAL_CONTROLS` already
checked the mirror against the published national totals on every run; this
checks a whole state of it against the primary document.

**The route that would fill them, and why it is not taken.** C-01 *is*
published below district level: the Registrar General's own workbook for
Andhra Pradesh (`DDW28C01_MDDS.XLS`) carries 1,128 tehsil rows beside its 23
district rows, and they sum to the district totals to the person. C-16 is
published the same way. A modern district made of whole 2011 mandals could
therefore be summed rather than estimated. What does not exist is the other
half of that join: the census publishes no concordance from 2011 sub-districts
to present-day districts, and the 2016 reorganisation did not only reallocate
mandals but split some of them, so a hand-written mapping would not be a
partition even if every line of it were right. Writing one out would invent
precisely the thing the sub-district tables were meant to supply.

### Telangana, Ladakh, and summing a state from its districts

The mirror of the same problem, one level up, and here the fix adds figures
rather than removing them.

Telangana's state row read *not available*: "the 2011 census enumerated that
territory as part of Andhra Pradesh, so no census figure exists for Telangana
as such". That is true of the published tables and false of the census. Every
person in Telangana was counted in 2011, in one of ten district rows — 532
Adilabad through 541 Khammam — which partition the territory exactly. Ten
disjoint measurements that exhaust a territory sum to a measurement of it.
Nothing is apportioned and nothing is estimated.

Andhra Pradesh had the matching error and it was the invisible kind. Its state
row carried 84,580,777 people and 88.5% Hindu — undivided Andhra Pradesh,
Telangana included — on the shape of the residual state. The thirteen districts
that stayed hold 49,386,799 people and are 90.9% Hindu and 7.3% Muslim, against
Telangana's 85.1% and 12.7%. The undivided figure described neither. Jammu and
Kashmir and Ladakh were the same pair, smaller: Ladakh's two districts are 2.2%
of the old state's people and a quarter of its area.

| | summed | published | check |
|---|---|---|---|
| Telangana | 35,193,978 | 35,193,978 | Wikidata gives the same, independently |
| Andhra Pradesh (residual) | 49,386,799 | 49,386,799 | |
| Ladakh | 274,289 | 274,289 | |
| Jammu and Kashmir (residual) | 12,267,013 | 12,541,302 − 274,289 | |

Both halves must add back to the undivided state in **every** column, and each
half's population must equal the published figure to the person, or nothing is
emitted. The same split runs over C-16 for mother tongue, and the two tables
are kept apart deliberately: they have different district columns, and a split
right in one and wrong in the other is the failure neither file can see alone.
`SPLIT_STATES` carries both the district names and the census's district codes
because the religion extract keys on the name and the language workbooks key on
the code.

**The 190,304 people the sum cannot lose.** Seven mandals of Khammam —
Burgampahad, Chintur, Kukunoor, Kunavaram, Vararamachandrapuram, Velairpadu and
part of Bhadrachalam — were moved to Andhra Pradesh by ordinance on 29 May
2014, four days before Telangana existed, to put the Polavaram project on one
side of the border. They are inside the ten districts and outside the
present-day state, which is why the Registrar General's figure for Telangana as
it now stands is **35,003,674** and the ten districts hold 190,304 more. That
0.5% is stated on the record rather than removed, because removing it would
mean subtracting six whole mandals (208,421 people in the official
sub-district table) to land on 34,985,557 — a number nobody published, 18,117
people from the one they did, and wrong by an amount the note could not state.
A visible 0.5% beats an invisible one.

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

### Pakistan again: mother tongue, and a level that is not the one above

The religion above comes from the Bureau of Statistics' own PDF. The Census
Bureau's workbook for Pakistan carries **both** religion and mother tongue from
the same 2017 census, and only the second is read here.

**Religion is left where it is, deliberately.** Both files would be publishing
the same census table onto the same 126 district shapes, and under the
agreement rule two rows that differ by a single person send *both* to a gap.
Adding language costs nothing that works; adding religion risks 114 districts
that already do. A second source is only worth having where it fills something.

**The districts are at level 3, not level 2.** The file counts 8 first-order
areas, then **36 divisions** at level 2, then **155 districts** at level 3 --
and it is the districts geoBoundaries draws as Pakistan's second order, hanging
directly off the provinces. Reading level 2 would have put a division's figures
on a district's shape: 36 wrong answers that each look exactly like a right one.

That level also broke a rule the reader had been keeping by accident. `area()`
took a row's parent from the level immediately above, which is the same thing as
the first order in every country here until now. For Pakistan it is not, and a
district scoped inside "Karachi Division" would be scoped inside a parent no
boundary file has -- one that can never match, rather than one that sometimes
does. The parent is now taken from whichever level the country calls `admin1`,
so Karachi East is scoped inside Sindh.

**What does not join, and why.**

* The **Federally Administered Tribal Areas** are a first-order area in the 2017
  census and were merged into Khyber Pakhtunkhwa in 2018, so no shape is drawn
  for them. Declared rather than left to the matcher. Their 13 agencies keep
  their own rows: naming a parent that cannot be resolved falls through to the
  country-wide pass, and Bajaur, Kurram and the Waziristans are distinctive
  enough to land there.
* **Azad Kashmir and Gilgit-Baltistan are listed and left blank** -- 2 first-order
  areas and 20 districts with no figures at all. The census tabulates mother
  tongue for Pakistan proper. Those areas keep a visible gap, which is what they
  are.

Both levels reconcile exactly: 207,684,626 against the census's own
207,684,626, and every one of the 141 areas published reaches its own total.
Sindh reads Sindhi 61.6% and Urdu 18.2%; Punjab, Punjabi 69.7% and Saraiki
20.7%; Balochistan splits Balochi 35.5% against Pushto 35.3%.

### Karachi: the largest second-level language gap on the map, and why it was there

Pakistan's district language coverage was measured at **114 of 126 shapes**,
which reads like a country nearly finished. Ranked by people rather than by
shapes it read differently: one of the twelve blanks was **Karachi, 20.4
million people** -- more than every other blank district in the world outside
China, Indonesia, Bangladesh, Nigeria, Russia and the Congo put together.

The cause was not a bad join. It was a join with nothing to make:

* geoBoundaries draws **one** district called Karachi.
* The 2017 census counts **six** inside it -- Karachi Central, East, South and
  West, Korangi and Malir -- and the Bureau's workbook lists all six at level
  3, the level this map reads.
* Six rows, one shape. Each of the six reached nothing, because none of them
  *is* Karachi, and the shape stayed empty.

`scripts/fetch_census/pakistan.py` had already met this on the religion side
and declared it: `MERGED` sums the seven districts of 2023 into the one shape,
which is why Karachi carries a religion and a population and no language. The
Census Bureau reader had no such facility, so `Country.merged` is now the same
declaration in the same shape, and `combine()` performs it.

**Seven districts in 2023 and six in 2017 is not a contradiction.** Keamari was
split out of Karachi West in 2020. The ground is the same ground; only the
lines inside it moved, which is exactly the case one boundary shape covers.

**Every check refuses rather than repairs**, because each of them is a way for
a wrong merge to look like a right one. The dangerous one is a missing part:
five districts summed onto a shape that is six would put four fifths of
Karachi's people on all of Karachi and report nothing wrong -- the shares would
still add to 100%, every district would still reconcile against its own
published total, and the only trace would be a population no other check looks
at. So a merge is all of its declared parts or it is refused. The others are
the assembled area also being printed in the sheet (its people counted twice),
parts at two levels (a division and the districts inside it are the same
people), a denominator published for some parts and not others, and an area
declared both `no_shape` and part of a merge, which is a config asserting two
things that cannot both be true.

And one control the file supplies itself: an assembly may not hold more people
than the parent it is declared under, where that parent prints its own row.

**The refusal that was missing, and the run that proved it was.** The first
version of this had one more branch than it should have: a declaration that
reached none of the sheet's areas was passed over, on the theory that a sheet
might simply not carry them. Dispatched to the runner, it merged nothing in
either country and said nothing about it -- the log read `141 areas: 6 admin1,
135 admin2`, `every one of 141 areas reaches its published total`, `wrote
data/processed/pakistan_language.json (329 kB)`, and the file came back
byte-identical. The only way anyone knew was by diffing the output.

The cause was one line wide. Every declaration in a `Country` -- `aliases`,
`no_shape`, `merged` -- is written in the spelling the records carry, which is
the sheet's cell put through `str.title()`; Pakistan's Table 11 prints
`KARACHI CENTRAL DISTRICT`. `aliases` and `no_shape` had always folded the
cell before comparing. `combine()` compared it raw, so it was testing the one
spelling no declaration in this module is written in. The fold now lives in
`spelling()`, named and in one place, and a merge that matches nothing is
refused with what the sheet does have printed beside it -- `KARACHI CENTRAL
DISTRICT` next to `Karachi Central District` is a diagnosis at a glance.

Two things about how that got through are worth keeping. The tests passed,
because they handed `combine()` a mapping the test file had built, in a
spelling the test file had chosen: a test that writes both sides of a
comparison cannot see the two sides disagreeing. They now build a *sheet* and
read it through `read()`, in both spellings. And Ethiopia was briefly reported
as working because its output file had changed -- it had, by exactly the alias
line and the `no_shape` removal, and not by a single assembled record. A
changed file is not a done job.

Karachi now reads Urdu 42.3%, Pushto 15.0%, Punjabi 10.7%, Sindhi 10.7%, of
16,024,894 people the mother-tongue table counts -- 2017 figures on a shape
whose 2023 population is 20.4 million, and the record says so.

**The eleven other blanks are not this, and are not fixable here.** Ten are
Gilgit-Baltistan's districts and the eleventh is Azad Kashmir, both of which
this map has carried as a visible gap since the language adapter was written:
the 2017 census tabulates mother tongue for Pakistan proper, and those two
territories are enumerated apart from it. The 2023 round says the same thing
from a different direction -- `pakistan.py` lists Islamabad, Azad Jammu and
Kashmir and Gilgit-Baltistan as optional provinces and its last run found a
Table 9 for none of the three, at either of the two paths the Bureau uses. Not
a fetch that went wrong: a fact about what the Bureau publishes under the
census proper.

**Is 2017 the most current this can be?** No, and that is worth stating
plainly rather than leaving implied. PBS completed the 7th census in 2023 and
publishes its tables as per-province PDFs; `pakistan.py` already reads Table 9
(religion) from them. What is not established is whether the 2023 round
publishes a mother-tongue table in the same series, and under which number --
2017's was Table 11, and a table number is not a thing to guess at, because a
guessed URL that 404s and a table that was never published are the same
observation. The route to settle it is reconnaissance, not assumption:

```
scripts.probe_links https://www.pbs.gov.pk/census-2023-tables --match pdf --limit 80
scripts.fetch_census.uscb --inspect pakistan-subnational-population-and-housing-data-tables
```

The first says what the 2023 index actually links to. The second says whether
the Census Bureau's extraction is still the 2017 census or has been reissued --
its metadata sheet carries the census year, and the file's own date is an
extraction date that has been mistaken for it before. Until one of those
answers, 2017 is the most recent mother tongue this project can show, and the
records say 2017.

### Central African Republic: three fields, and a table that counts two things

The 2003 census (RGPH03) publishes ethnicity, religion and language, all three
at both levels this map draws, and it is the cleanest file the Bureau's
collection has offered. Its 17 first-order and 72 second-order areas are
exactly what geoBoundaries draws -- no level to work out, after Pakistan's
turned out to be 1 and 3 -- and every sheet reconciles to within a single
person of its own published total:

| sheet | groups | published | summed |
|---|---|---|---|
| Ethnicity | 26 | 3,895,139 | 3,895,138 |
| Religion | 5 | 3,836,736 | 3,836,735 |
| Language | 78 | 3,726,684 | 3,726,679 |

**No column prefix, deliberately.** Each sheet holds one question, and naming a
prefix could only silently drop a column that failed to match it. The evidence
that nothing is wrongly in or out is the reconciliation itself: a column
included by mistake or dropped by mistake would move the sum, and the worst
area in the whole file is off by one person.

**The ethnicity table counts two different things, and this is the reason it
is published anyway.** Its source is the census's own *Ethnie-Nationalité*,
which codes residents who are not Central African by nationality rather than
by ethnic group -- Cameroonian, Chadian, Sudanese, French and Lebanese sit in
the same column set as Gbaya and Banda.

That is precisely what Syria's sheet was refused for, so the difference has to
be stated rather than assumed. Syria's was nationality *entire*: nine columns,
Syrian first, which published as ethnicity would have told a reader the
country is ethnically uniform. Here the nine local groups carry **96.1%** of
the population and every foreign category together carries **1.8%**. It is an
ethnicity table with a foreign tail, not a nationality table wearing an
ethnicity label -- and dropping the tail would stop the composition summing to
the population it is a composition of, which is a worse fault than the mixing.

One local category is written `Haoussa/Musulman` in the original, defining an
ethnic group partly by religion. It is published as the census wrote it, on
the same principle as the Philippines' denominations: which categories are one
thing is the census's judgement to make, not this map's.

Four sub-prefectures needed an alias -- Aba/Abba, Bossemptele/Bossemtélé,
Nanga-Boguila/Nagha Boguila, and Ndjoukou, which loses its initial N in the
boundary file. Each was read off the two lists of leftovers, four rows with no
shape against four shapes with no row, pairing one to one.

### Mali: a quarter of the country, accounted for

Its 21 language columns sum to **11,109,312** against a census that counted
about 14.5 million. A quarter of a country unaccounted for is either a stated
universe or a misread sheet, and the two look identical from the numbers, so
the file was held back a release rather than guessed at.

The answer was in the source citation the whole time, and could not be read
because this reader printed only the first 150 characters of a data-dictionary
cell -- which is past the field description and stops inside the citation.
Mali's ended at `Tableau S-3: Population R...`. Printing 400 finishes the
sentence:

> `Tableau S-3: Population Residente de 6 Ans et Plus Selon la Langue`

The resident population **aged 6 and over**. The missing quarter is children
under six, who were not asked. So every Mali share on this map is of people
aged six and over, which the note says because the shares cannot.

**Regions only.** The file lists all 50 cercles and leaves every one blank, so
the second order would be a claim to a level that carries nothing. This is
Ukraine in reverse -- there the figures were at the second order and the first
was empty -- and it is settled the same way: publish the level that has the
data, and let the other be a visible gap.

One column, `LNG_MLS` "Main language spoken", comes from a different source
again (a 2022 percentages table, not the 2009 census) and holds a language
name rather than a count. It needed no special handling: it is text, `number()`
returns None, and the reader already skips it.

### Mali again: half the country missing from its own language chart

Mali was live and passing, nine regions of nine, and its country card showed a
language composition with no Bambara in it.

The Factbook's entry opens `Bambara (official), French 17.2%, Peuhl/Foulfoulbe/
Fulani 9.4%, ...`. Bambara carries the word "official" and no figure, so the
parser -- which reads a group only when it finds a share -- dropped the part
and returned the other eleven. Those eleven sum to **70.9%**, and were rendered
as Mali's whole language composition. The language about half the country
speaks did not appear at all.

Our own regional data settles what the right answer is, because it is the same
2009 census read at the level below. Summing the nine regions:

| | national roll-up | the Factbook's list |
|---|---|---|
| Bambara | 51.8% | *(no figure)* |
| Fula | 8.3% | 9.4% |
| Dogon | 6.5% | 7.2% |
| Maraka/Soninke | 5.7% | 6.4% |
| Sonrhai/Djerma | 5.3% | 5.6% |
| Malinke | 5.1% | 5.6% |
| Minianka | 3.8% | 4.3% |
| Tamasheq | 3.2% | 3.5% |
| Senufo | 2.0% | 2.6% |
| Bobo | 1.9% | 2.1% |
| not stated | 0.8% | 0.7% |

Every member reproduces to about a point. Bambara is the one that does not
appear, and `French 17.2%` is the one with no counterpart -- the 2009 mother
tongue table has no French in it anywhere. Neither figure is repaired here.
The Factbook's text is what the Factbook says, and inventing 46.3% for Bambara
from the arithmetic would be exactly the kind of plausible guess this project
refuses.

What changed is that a group the source **names** is no longer thrown away for
having no figure attached. Bambara is now a member of the composition with its
share recorded as a gap. Three outcomes were possible and this is the least bad
one: a wrong share would at least be visible, a named member with a stated gap
is honest, and silently dropping it is the failure that reads as though the
question was never asked.

It was never only Mali. The same rule was discarding **73** named groups, among
them eighteen of South Sudan's peoples -- Shilluk, Azande, Bari, Kakwa, Murle
and the rest, leaving an ethnicity chart of two groups summing to 52.5% -- and
eleven of Sudan's. Sierra Leone gained a real language list in place of four
fragments the old name-only path had cut inside parentheses (`English (official`,
`regular use limited to literate minority)`). No group that already had a share
changed by so much as a decimal: that was checked across all 260 profiles and
711 compositions before and after.

Three shapes are *not* members, and each is recognised by where it sits rather
than by what it means. Commentary that opens with a joining word (`including
Liberian English variants`). A count of languages rather than a language (`120
indigenous languages`). And one item of a name the comma-split tore apart --
South Africa's `ancestral, tribal, animist, or other traditional African
religions 5.4%` is a single group whose share sits on the last fragment, marked
not by the fragments but by what closes the run they are in.

#### And the same language under two spellings

The other half of the same bug. Mali is described by two sources at once, the
Factbook nationally and the 2009 census regionally, and they spell five
languages differently. Unmapped, each label keys on itself, so the world filter
offered `Tamasheq` over nine Malian regions beside `Tamacheq` over Mali entire,
as though they were different languages spoken by different people.

`Fula/fulfulbe` and `Peuhl/Foulfoulbe/Fulani`; `Maraka/soninke` and
`Maraka/Soninke`; `Sonrai/djerma` and `Sonrhai/Djerma`; `Tamasheq` and
`Tamacheq`; `Senufo` and `Senoufo`. Mali's 28 language groups are now 23, and
`Fula` reaches Burkina Faso and Finland as well.

Two of them keep the weld their source made. `Maraka/Soninke` and
`Sonrhai/Djerma` each name two peoples the Malian census counts together, and
the canonical form is the source's own spelling rather than a tidier invented
one: folding them into a bare "Soninke" or "Songhai" would merge a pair with
one of its own members the moment another country reports that member alone.

**The Central African Republic is deliberately left out of this.** Its `Fulah`
and `Peulh` look obviously foldable into Fula, and are not: CAR's census lists
`Fulah`, `Fulata` and `Peulh` as three separate rows *of the same prefecture*
(Bamingui-Bangoran has Fulah 11.4%, Fulata 0.0%, Peulh 0.0%), so its
classification distinguishes them and folding would sum categories the source
chose to keep apart. Mali's forms are safe because no Malian record carries two
of them at once, which is asserted by a test rather than assumed.

### The Democratic Republic of the Congo: the first source here that is not a census

Everything else on this map is a census. This is the *Enquête 1-2-3*, and it is
reported differently for that reason -- because the difference is invisible
once a figure is drawn on a shape.

**The figures are not people.** They are the **31,755 heads of household** the
survey reached, for a country of 119 million. The reader gained
`Country.counts_are_people` for it: where that is false only the share is
published and no count is, because the share is what the survey measures and
the count is how many doors it knocked on. A count of 11,114 Catholics sitting
in the same field as Pakistan's 200 million Muslims, with nothing to say one
is a sample, is exactly the invisible mis-match this map exists to refuse.
Shares without counts are not a new shape here: the whole-country rows from
the Factbook have always been that.

**The universe column is called "Sample size".** `denominator()` finds that
column by looking for the word "population" in its alias, which is right for
every census here and wrong for a survey. Unnamed, `TRB_SSIZE` is read as a
group -- and since it is the sum of every other group, as the largest tribe in
the country. `Topic.denominator` names it outright, and both topics take the
same column, which belongs to neither.

**Provinces only, and this is a decision about sample size rather than about
names.** The file also carries 164 districts and they would all have joined.
31,755 households over 26 provinces is about 1,200 each, which supports a
provincial estimate; over the districts it is about 194, which supports
nothing. Reading a level and not publishing it is the machinery Ukraine
already needed; here it is used to refuse detail the source cannot carry
rather than to build a level it left empty.

Two other things the note has to say, because no figure can. The source pools
the **2005 and 2012** rounds into one column set, so a share dates to neither
year exactly. And the unit is the household *head*, so a provincial share
describes heads of household rather than residents.

### Russia: matched on a code, and five wrong readings of one file

The 2020 census, Volume 5, publishes ethnic composition (table 1) and native
language (table 6) for every federal subject, each sheet naming its own
universe: *Указавшие национальную принадлежность* and *Указавшие родной язык*.
Both reconcile at **1.0000** -- the worst sheet in either file is exact to four
decimal places.

**Not table 5.** It is called ВЛАДЕНИЕ ЯЗЫКАМИ, *proficiency*, and asks which
languages a person knows, admitting several answers. Published as a
composition it reads past 100%, which is what Thailand's language file was
refused for. Table 6 partitions; table 5 does not.

**Matched on ISO 3166-2 rather than on names.** The sheets are Cyrillic, the
boundary file English, and `norm()` keeps Cyrillic as Cyrillic on purpose: a
romanisation invented in this code is a guess about a name, and the guesses
that look right are the dangerous ones. 82 of Russia's 83 shapes carry a code;
Sakha carries none and is aliased by name, and a test asserts it is the only
one. This is the first source where the two sides share no alphabet.

**88 sheets, 83 subjects.** Two skips are combined forms of subjects the
boundary file draws split -- Arkhangelsk with Nenets, Tyumen with the two
okrugs -- and reading them beside their parts would count about four million
people twice with nothing in the figures to show it. Two are Crimea and
Sevastopol, which Ukraine's 2001 census already publishes on these shapes and
which geoBoundaries does not draw inside Russia. One is the country's own row,
kept as the control.

**Fetched from the Internet Archive and checked in.** rosstat.gov.ru serves a
valid certificate signed by the Russian Trusted Sub CA, an authority no
ordinary trust store carries; the site is not refusing this client and this
project will not disable verification to reach it. The workbooks live in
`data/raw/russia/` for Nepal's reason -- no verified route to the original --
and the citation names the capture date.

#### What five wrong readings of this file cost, and what caught each

Nothing reached the map. Every one was stopped by the same reconciliation
against the universe the sheet publishes, which is the whole argument for
having it.

| the reading | what it did | how it showed |
|---|---|---|
| the plain archive URL | returned the Wayback player page, 10 kB of `<!DOCTYPE html>` | a workbook that was not a ZIP |
| leading whitespace means nested | dropped Русские in Воронежская область | that sheet at **13.55%** of its total |
| any indent means nested | Rosstat indents the whole list; 94 of 95 rows dropped | Чукотка at **0.95%** |
| shallower rows are members too | counted the *not stated* residual, which the universe excludes | ХМАО at **135%** |
| labels are in column 0 | two sheets keep the pivot table's member keys there | Ингушетия and Красноярский край silently **empty** |

The fourth is the one worth keeping. "Указавшие" means *those who stated*, so
the people who stated nothing sit outside the denominator by construction and
cannot be one of its parts -- and the commit before it had argued the exact
opposite in writing.

The fifth is the one that nearly got through, because an empty subject is
quiet: on the map it reads as a census that did not ask, when it was the
reader that did not look. Both completeness checks now test what was read
rather than whether a key exists, and the refusal prints the largest groups it
summed. `0.1355` says something is wrong; `largest: не указана 446` says what,
and that change turned four runs of guessing into one.

### Russia: the join that matched one subject of 83

The adapter was correct and the map was empty. Reconciliation had passed at
1.0000 on both tables, all 83 subjects were in `data/processed`, and the site
showed 83 shapes with no ethnicity and no language -- which reads exactly like
a census that did not ask.

Three things were wrong, in a row, and each hid the next.

**The code index was built before anything could fill it.** Matching on ISO
3166-2 rather than on a romanisation is the right design and was the whole
point of this adapter. But the codes are not on the shapes: geoBoundaries
publishes `shapeName`, `shapeID`, `shapeGroup`, `shapeType` and nothing else.
They arrive from the Wikidata adapter -- whose rows sit in the same list being
matched, and are merged only after that loop finishes. So the index was read at
the one moment it was guaranteed to be empty, all 83 Cyrillic sheet names fell
through to a name pass against English shape names, and 82 landed nowhere. The
one that matched did so on its declared alias, which is what made a total
failure look like a near miss.

Rebuilding the index from the code-bearing rows instead does not work either,
and that was worth learning: it puts an exact-key index where a fuzzy matcher
belongs. `norm()` takes "Moscow" and "Moscow Oblast" to the same key, and
"Karelia" and "Republic of Karelia" to different ones, so the same eight
subjects were lost -- two to a false ambiguity and six to a false miss. The
matcher bridges those with `contains` and `prefix`; an index cannot.

The fix is ordering, not keying. A row that names a code and misses on its name
is held back, and matched against the entities **after** the merge, when they
finally carry the codes Wikidata gave them. 83 of 83.

**A dict is not a code.** Every field in `METADATA` is normalised to
`{"status": ...}` when a row does not carry it, and 188 Wikidata admin-1 rows
hold that dict in `iso_3166_2`. A dict is unhashable, so `code in a1_by_code`
raised `TypeError` rather than missing -- killing the entire join, for every
country, on the first row that reached it.

**And the refresh reported success anyway.** `build_all.sh` runs without
`set -e` deliberately, so an adapter behind a blocked host can be skipped and
still leave a working site. That also made a crash in the *join* survivable:
the step died, `site/data` kept the previous build's contents, the script
exited 0 from the `echo` at the bottom, and the workflow opened a data PR
described as a successful refresh. The join step is now explicitly fatal.

That is the same shape as the three bugs inside this adapter, one level up: a
check that confirms the pipeline ran rather than that it produced anything.
Empty is the dangerous outcome precisely because it is quiet.

**And a fourth thing, in the other direction.** Adding `iso_3166_2` to
`METADATA` had one effect and it was not the intended one. `METADATA` is used
in exactly one place: it is the exclusion list `conflicting()` consults when
two rows land on the same shape, to decide whether they are one place written
twice or two different places. A Wikidata Q-id is excluded because it is unique
per item, so counting it would make every rivalry look like a conflict. An ISO
3166-2 code is the opposite of that -- shared and standard, so two rows holding
*different* codes are two different official units by definition.

Excluding it deleted the strongest evidence that function had. Lithuania's
Alytus County has two rivals, `Alytus City Municipality` (LT-02) and `Alytus
District Municipality` (LT-03), and the collision pass had been refusing both
because nothing separated them. With the codes invisible they read as one place
listed twice, the duplicate exemption applied, and the shape took the district
municipality's **25,356** people in place of the county's hundred and forty
thousand. Laos' Vientiane took Vientiane Province's 388,833 over the
prefecture's the same way.

Two honest gaps became two confident wrong numbers, which is the trade this
file exists to refuse. The code is comparable again.

**A correction to what is written above.** This adapter's notes said Wikidata
carried a code for 82 of Russia's 83 subjects and that Sakha was the exception
needing a name. Counting them gives 83, `RU-SA` among them; the belief was
never measured. The alias is kept as a spare if that row ever loses its code,
but it is not the load-bearing part it was described as -- and the test that
was supposed to guard this asserted it against the *built* file, where the
adapter writes its own code onto every shape it matches. It therefore returned
83 no matter what Wikidata held, and passed throughout the period the join was
producing one subject.

### Russia: 147 nationalities and 176 languages, in Russian

The join worked and the map was in the wrong language. Tatarstan read
`Русские 40.3%`, and the world filter offered `Русские` as a different answer
from the `Russian` it already had from Estonia, Latvia and Lithuania — the same
people, counted by four censuses, split across two alphabets.

Every other adapter here already emits English: Ukraine's oblasts publish
`Romanian`, not `румунська`. Russia was the exception.

**Why this is allowed where romanising a shape is not.** This adapter matches
subjects on their ISO 3166-2 code precisely so that no English spelling of a
place name is ever invented — a wrong guess there attaches real figures to the
wrong region and nothing on the map shows it. A group name is not a key into
anything; it is the label a bar carries. These are declared one at a time in
`canonical_groups.py`, not transliterated by rule.

The one thing a wrong entry here can still do is **merge two peoples**, because
rows reaching the same name are summed. So: every label the sheets publish
appears exactly once in the table, no two labels resolve to one name, and an
unknown label stops the run rather than reaching the map in Cyrillic — one
untranslated row among translated ones reads as a different kind of thing
rather than as the gap in a table that it is.

**Translated in the adapter, not in the group tables.** Folding the Cyrillic
into `ETHNICITY`/`LANGUAGE` was tried first and is half a fix: those tables
reach the group *picker*, while the name a bar carries comes from the record
itself. The picker said `Russian` while Tatarstan still said `Русские`.

**Moldovan is not folded into Romanian here.** The language table had
`"Romanian": ("Romanian", "Moldovan", "Moldovian")`, and Rosstat lists
`Молдавский` and `Румынский` as separate rows of the same subject in **80 of
83**. Folding would have summed two categories the census keeps apart, silently,
in eighty places — the same evidence that keeps the Central African Republic's
`Fulah`, `Fulata` and `Peulh` separate. Dropping the fold cost nothing: no
source in this dataset has ever emitted `Moldovan` as a *language* label, which
was checked across every built file. The ethnicity table never folded it and
still does not — there it is a nationality both Moldova and Ukraine report.

The result is 50 of Russia's ethnicity groups and 72 of its language groups now
sharing a filter with other countries, where before every one of them was an
island. Not one country's row-to-shape matching changed, which was checked by
diffing the per-country match counts before and after.

### Which countries the Census Bureau's series actually covers

The USCB adapter is generic, so a new country is a config entry rather than a
new reader — and how many countries were available had never been measured.
They were being chosen by guessing at names. `scripts/probe_hdx.py` reads the
list: it starts from a dataset the adapter already fetches, takes the
organization from that rather than assuming HDX's naming, and enumerates what
that organization publishes.

**34 datasets, 25 with workbooks, 9 already read here.** The probe immediately
killed three candidates picked by intuition — Kenya, Tanzania and Uganda are
not in the series at all.

Having a workbook is not having the fields. Of the largest remaining:

* **Nigeria** — its only relevant sheet is `Nationality`: Nigerian by birth,
  by naturalization, other ECOWAS, African other than ECOWAS, non-African.
  That is citizenship. Published as ethnicity it would tell a reader that a
  country of some 250 named peoples is ethnically uniform, which is exactly
  what Syria's sheet was refused for.
* **Sudan** — `Nationality_CensusGeog` holds two columns, "Born outside Sudan
  and South Sudan" and "Unknown", together 1.8% of the population. Not a
  composition.
* **Indonesia** — already recorded above, and worth repeating because it was
  briefly mistaken for an opening: its workbook carries a four-bucket first
  language split and no religion or ethnicity. The BPS key is still what
  Indonesia needs.

### Colombia: an answer people gave, and a sheet that adds up and is not read

The 2018 census's *autoreconocimiento étnico*, from the `Individuals` sheet:
seven categories summing to **44,164,417**, which is the sheet's own published
universe of those who answered, against a counted population of about 48
million. 33 departments and 1,122 municipalities, every one reaching its own
published total, both levels reconciling exactly.

| | |
|---|---|
| No ethnic group | 87.6% |
| Black | 6.7% |
| Indigenous | 4.3% |
| Unknown ethnicity | 1.4% |
| Raizal, palenquero, Rrom | 0.1% |

"No ethnic group" is an answer, not a residual invented here. Colombia asks
which of five recognised groups a person recognises themselves in, and most
Colombians answer none of them. The departments read the way Colombia reads:
Chocó is 73.8% Black, Vaupés 81.7% indigenous, La Guajira 47.8%.

**`ETH_` and nothing else.** That sheet holds two questions. Beside the seven
ethnicity columns sit eight `LNG_` ones asking whether indigenous people speak
or understand a native language — yes, no, unknown, about one group. It is not
a language composition, and "everything that is not geography" collects both
and reports 113% of the population.

**Departments and municipalities, not the third level.** `ADM_LEVEL 3` is
`CABECERA`, `CENTRO POBLADO` and `RURAL DISPERSO`: the urban and rural strata
each municipality divides into, repeated 1,122 times over. Every area the
inspection flagged as furthest from its own total sits there, because a
stratum's rows are being compared against a total belonging to the whole
municipality.

**The 124 indigenous peoples are not read.** The same workbook names them
individually — Achagua, Wiwa, Pijao, Misak — and the sheet reconciles at
exactly 1.000. Its universe is the 1,905,617 people who said they were
indigenous, not the country, so published as Colombia's ethnicity it would
look perfect and say the country is entirely indigenous. A file that adds up
is not the same as a file that means what its name suggests.

#### The file was written and never opened

The first build joined **0 of 1,155** Colombian areas and reported success. The
adapter was right in every respect; `build_entities` reads a named list and
`colombia_department.json` was not on it.

The log even said `COL: adapter rows matched 1085`, which was true and was the
Wikidata rows — the same shape as Russia's join reading one subject of 83, a
real number sitting in the log beside no data on the map. Both directions are
now asserted by a test: every country's declared output is on the list, and
every name on the list is one something actually writes.

Three shapes were waiting on a name, and the archipelago's mattered beyond
itself. geoBoundaries gives it its full constitutional name, and while the
department went unmatched its municipalities had no parent to scope them — so
San Andrés and Providencia, which each share a name with a mainland
municipality, could not be told apart from them and were refused. Naming the
department recovered all three. geoBoundaries also truncates Barranquilla's
official long name with a literal asterisk, and spells Tiquisio without its
second i.

One municipality carries nothing: `Papunaua`, a *corregimiento departamental*
in Vaupés that the census does not tabulate separately. That is a gap in the
source, and it stays visible.

### The rest of the Bureau's series: eight refusals and three small finds

Inspecting the eleven remaining candidates settled 144 million people in one
run. **137 million of it is closed.** Iraq, Yemen, Somalia, South Sudan, Haiti,
the Dominican Republic and Dominica publish no religion, ethnicity or language
sheet at all — their workbooks are humanitarian profiles: population, health,
poverty, displacement. Libya carries a `Nationality` sheet and nothing else,
which is citizenship, the same refusal as Nigeria's and Sudan's.

Six configs would have been written to discover that.

### Jamaica: two questions on one sheet, and two universes

The 2011 census by parish, and the first country here whose ethnicity and
religion arrive in the same sheet. Read whole it comes to 2.998 times the
population, because it holds both sets of columns *and* religion's own total —
Burma's case, and what `Topic.prefix` is for.

Ethnicity sums to **2,683,707** and religion to **2,678,981**, each exactly its
own published universe, across all 14 parishes. They are different questions
and the source says so; the map does not average them into one.

Religion names its denominator outright as `RLG_RTOTL`. Left unnamed it would
have been collected as the largest denomination in Jamaica, being the sum of
all the others. Naming it by its *label* rather than its column code was the
first attempt and the adapter refused the run — correctly, and after Jamaica's
ethnicity had already reconciled exactly, so the failure was precise about
where it was.

### The Bahamas: the race question, not the citizenship question beside it

`RCE_` and nothing else. The Individuals sheet also carries eight `CIT_`
columns — Bahamian, Haitian, Jamaican, Guyanese, Canadian, American, British,
other — and read together they come to three times the population. That block
is exactly what Nigeria's, Sudan's and Libya's whole workbooks were refused
for; here it sits beside a usable question rather than instead of one.

**14 of 32 districts.** The census publishes 18 island groupings and
geoBoundaries draws 32 districts that subdivide them: Abaco is Central Abaco,
Hope Town, Grand Cay and more; Grand Bahama is City of Freeport and East Grand
Bahama. Where an island is a district the join is exact; where the census is
coarser than the map, eight of its rows have no single shape to land on and
those districts stay visibly empty rather than being given a figure that
belongs to their neighbours.

### Saint Vincent and the Grenadines: published, and not placeable

Its workbook has what this map wants — ethnicity and religion from the 2012
census, reconciling to 109,188 exactly — for thirteen areas that are census
districts: Kingstown, Suburbs of Kingstown, Calliaqua, Marriaqua, Bridgetown,
Colonarie, Georgetown, Sandy Bay, Layou, Barrouallie, Chateaubelair, Northern
and Southern Grenadines.

geoBoundaries draws the six parishes: Charlotte, Grenadines, Saint Andrew,
Saint David, Saint George, Saint Patrick. **The two lists share no name at
all**, and configured as `admin1` the join was 0 of 6 — a country of shapes
with nothing in them.

The bridge exists and is not built. The sheet carries a `PARISH` column naming
each district's parish, so the thirteen could be summed into the six the way
Ukraine's rayons are summed into oblasts. Ukraine's parent comes from the
file's own geography columns; this one is an ordinary data column, which no
country here reads that way. Worth doing, and not worth pretending is done.

### Brazil, in English — and two states that never had figures

Brazil's 25 states read `Católica Apostólica Romana 56.7%` and `Parda` while
its own country record, from the Factbook, said Roman Catholic and mixed. The
canonical tables had been folding the Portuguese to the right groups for as
long as Brazil has been on this map — and those tables reach the group
*picker*, not the record. Exactly Russia's half-fix, found the same way and
fixed the same way: the adapter translates, and an unknown label stops the run.

Two of the five colour-or-race categories are deliberately not translated into
a category some other country also has, and they go opposite ways.

**`Parda` becomes `Pardo` and stays Brazil's own.** The table it sits in
already says why: Brazil's *parda*, the UK's *Mixed* and the US "two or more
races" are three different questions with three different answer sets, and a
person counted in one would not necessarily be counted in the others.
Translating it to "Mixed" would merge 92 million people into a category their
census did not ask about.

**`Amarela` becomes `Asian`,** which is the opposite call and needs its own
reason: Brazil's own country record already calls these people Asian, so
leaving the states in Portuguese kept a country apart from its own states —
the split this whole exercise exists to close.

And two states had a shape and no figures for as long as Brazil has been here.
IBGE publishes both; nothing reached them because geoBoundaries drops the "e"
from Grande and writes Janeiro as `Jeneiro`. Neither is detectable — they are
well-formed words — so both are declared beside South Africa's "Nothern Cape"
and Myanmar's "Saigang". **Brazil goes from 25 states to 27, and 21 million
people stop being a blank.**

### Colombia's residual, described rather than renamed

`No ethnic group` keeps the name the census gave it, and the field carries a
note saying what that 87.6% is.

Colombia's census asks which of five recognised groups a person recognises
themselves in — indigenous, Rrom/gypsy, raizal, palenquero, black or
Afro-Colombian — and 87.6% answer *ninguno de los anteriores*. Those people are
predominantly mestizo and white Colombians: the majority of the country, and
not among the groups the question offers. **DANE does not count them
separately, so this map does not either.**

Renaming the category to "Mestizo" was tried and reverted. It reads better and
asserts more than the census did: it would put white Colombians — a distinct
measured group in every other source here — inside a mestizo bar, and it would
join the filter holding Mexico's mestizo, where the category *is* measured, so
the two would look comparable and would not be. A note can say "predominantly
mestizo and white" and stay true; a label cannot say it at all.

The mechanism that did the renaming went with it. It worked, and it had one
user; an unexercised path that rewrites published labels is not worth keeping
against the chance that some future country wants one.

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

### The United Kingdom: two geographies, because the boundary file draws two

The UK looked like a bug and was two things, neither of them one. Its four
first-order units -- England, Scotland, Wales, Northern Ireland -- carried a
population and no composition while 152 of its second-order units carried
both. That reads like a roll-up that failed. It is not.

**The roll-up is refusing correctly.** It fills a parent only from a *complete*
set of children, and England had 130 of 150, Wales 21 of 22. Summing an
incomplete set would publish a figure smaller than the country, with nothing on
the map to say so, which is the trade this project exists to refuse.

**Why the children were incomplete is the real finding, and it is a geography
mismatch.** ONS publishes TS021 and TS030 for 331 local authority districts.
geoBoundaries' UK ADM2 is a *mixed* geography of 216 units: unitary
authorities, metropolitan boroughs, London boroughs, Scottish council areas and
Northern Irish districts -- but for shire England the **county**, not the
districts inside it. So 150 of the 331 rows had no shape of their own, every
one of them an ONS `E07` code, while the county above each of them had a shape
and no row. Read at districts alone the join was 152 of 331 rows, and 64 shapes
stayed empty.

Nomis publishes the same tables at the county tier, `TYPE155`. Read there the
join is **171 of 174 rows**, and because that tier contains the unitary
authorities and boroughs as well, it covers every shape the district read
covered and 19 more: **171 of 216**. The two files agree exactly on all 150
names they share -- same populations, same shares -- and the 24 names only the
county file has are exactly the shire counties: Cambridgeshire, Cumbria,
Derbyshire, Devon, East Sussex, Essex, Gloucestershire, Hampshire,
Hertfordshire, Kent and the rest.

**Asked for, not summed.** Ukraine's oblasts are built by adding up rayons
because nothing else was published. Here the county figures are published, by
the same office, from the same census, and a total that was counted beats one
reconstructed from parts. The type code was not guessed either: `--geographies`
asked Nomis, which answered `TYPE155 2022 local authorities: counties`
alongside output areas, wards, national parks and two 2023 vintages, none of
which the adapter had mentioned.

**The 43 shapes still empty are Scotland and Northern Ireland**, and that is a
source gap rather than a join one. The 2021 census this adapter reads covers
**England and Wales only**. Scotland ran its census in 2022 through National
Records of Scotland and Northern Ireland in 2021 through NISRA -- two more
offices, two more adapters, and two reference dates that do not match the third.
The adapter has always said so in its header; what is new is knowing that those
43 council areas and districts are the whole of what remains.

### England and Wales: two rows, and why a whole country stayed empty

The roll-up fills a parent only from a **complete** set of children, and after
the county fix England stood at 149 of 150 and Wales at 21 of 22. One
unreachable district each -- and so both countries' admin1 records carried no
composition at all while their districts were 99% filled. That is the rule
working, not failing: a country summed from 149 of 150 districts publishes a
figure smaller than the country with nothing on the map to say so.

The two shapes, and two quite different reasons:

**Rhondda Cynon Taf** is a single letter. The council spells itself with one
`f`, and so does geoBoundaries; Nomis writes `Taff`. Note which side is wrong,
because it decides where the fix goes: this is the **mirror** of the
`MISSPELLED` table in `scripts/common.py`, which exists because geoBoundaries
carries a bad name and correctly-spelled sources cannot reach the shape.
Here the *shape* is right. Declaring it in `MISSPELLED` would rewrite a correct
Welsh name into ONS's spelling and the map would begin labelling it "Taff", so
the correction belongs on the source side, in the adapter.

**Northamptonshire** is a geography change. The county was abolished in April
2021 and replaced by two unitary authorities; ONS publishes the 2021 census on
the successor geography while geoBoundaries still draws the county. One shape,
two rows.

That one is summed, and legitimately. The two unitaries partition the old
county exactly -- no remainder, no overlap -- and 359,523 + 425,723 = **785,246**
is the census figure for that area, so it is a complete set rather than a
sample of one. Every category is added as a **count** and the percentages are
recomputed from the sum, which is not the same as averaging two percentages and
gives a different answer for two areas of unequal size. Ukraine's oblasts are
built this way for the same reason. A partial set is refused rather than
published: half a county under the county's name is worse than an empty shape.

A merged row does not claim a single ONS code -- there is no published unit
behind it -- so it carries the codes it was added up from instead.

### Scotland: filled from 2011, because 2022 is still behind the builder

The section below records Scotland as blocked, and that finding was right about
the thing it measured and wrong about the country. **The block is on the 2022
census**, whose results National Records of Scotland publishes through a
flexible table builder; the only file that release links is a bulletin's chart
data. None of that applies to **2011**, whose Key Statistics were published as
ordinary CSVs, one row per council area, and which nobody here had looked for.

So Scotland's 32 council areas are filled: `KS209SCb` religion, `KS201SC`
ethnic group, `KS206SC` language. All three reconcile exactly against their own
published totals -- 5,295,403 people, which is what dates them, Scotland having
counted 5.44 million in 2022.

**The cost is the year, and it is stamped rather than smoothed.** England and
Wales are read from the 2021 census; Scotland is now 2011. A reader comparing
Glasgow with Manchester is comparing a decade apart, and every Scottish figure
says so in its note.

Two ways to read these tables wrong, both silent, both guarded by a test:

* **Ethnicity nests.** `KS201SC` carries six top-level groups summing exactly
  to the population, and eighteen detail columns beneath them summing to the
  same total again. Adding both counts 4.4 million White Scottish people as
  White as well. This reads the **leaves** -- detail where a group has it, the
  group itself where it has none -- because "White" alone says nothing about a
  country where the split between Scottish, Other British, Polish and Irish is
  the whole interest. Glasgow reads Scottish 78.6%, not White 86.6%.
* **Language asks three questions.** Proficiency in spoken English splits the
  population three ways; "Can speak Gaelic" and "Can speak Scots" are counts of
  an ability rather than shares of anything. Only *language used at home*
  partitions its universe, and that universe is people aged 3 and over, smaller
  than the population the other two tables use. Na h-Eileanan Siar reads Gaelic
  **40.4%** at home, which is the check that the right block was read: pick the
  wrong one and the Gaelic heartland reads as a rounding error.

Two councils needed a name declaration, and neither side is wrong: NRS writes
`Edinburgh, City of` where the boundary file writes `City of Edinburgh`, and
`Eilean Siar` where it writes the Gaelic `Na h-Eileanan Siar`. Source-side
aliases, the same shape as Rhondda Cynon Taf.

**Northern Ireland's 11 districts remain blocked**, and 43 empty UK shapes
become 11. The section below closes that too, and all 216 of the UK's
second-order shapes then carry a religion and an ethnicity.

(An earlier draft of this section counted 45 and 13. The measured figures are
43 and 11: 32 Scottish council areas plus 11 Northern Irish districts.)

### Northern Ireland: which of ten tables is a composition

NISRA publishes the Census 2021 "Ethnicity, Identity, Language and Religion"
release as ten `MS-B` workbooks by local government district. Three of them are
read and seven are not, and the exclusions are the judgement here.

**Read.** `MS-B01` ethnic group, thirteen categories. `MS-B12` main language,
eighteen named languages and Other languages, of residents aged 3 and over.
`MS-B20` religion in intermediate detail, thirty-two categories -- every
denomination Northern Ireland counted at a thousand people or more, from
Catholic and Presbyterian down to the Christian Fellowship Church. All three
reconcile exactly against their own published totals, and the adapter refuses
the run rather than publishing a composition that misses by more than half a
percent. None of the eleven district names needs an alias: NISRA and
geoBoundaries spell all eleven the same way.

**Not read, first kind: not a composition.** `MS-B05` knowledge of Irish,
`MS-B08` knowledge of Ulster-Scots and `MS-B14` proficiency in English count an
*ability*. A person can appear in the Irish table and the Ulster-Scots table
both, or in neither, so their columns do not add to anyone — `MS-B05` even
carries a "Some ability in Irish" summary column beside the four skill columns
it is the sum of, and adding every column of that sheet reaches 112% of the
people in it. This is Scotland's `KS206SC` again, which asked three questions
in one sheet. **12.4%** of Northern Ireland aged 3 and over reports some
ability in Irish and **0.3%** give it as their main language; a language field
built from `MS-B05` would state the first number where a reader expects the
second.

**Not read, second kind: a different question.** `MS-B23` and `MS-B24` report
**religion or religion brought up in** -- Northern Ireland's community
background, and the figure most often quoted about the place. They cover the
districts and they were not used. A person raised Catholic who now has no
religion is Catholic in `B23` and No religion in `B20`, and the two answers are
far apart: Belfast is **43.5% Catholic and 21.7% of no religion** by `B20`, and
**48.7% Catholic and 11.6% of none** by `B23`. Folding `B23` into a field
labelled "religion" would move five points of the city into a church and halve
the share that told the census it has no religion — a number against Belfast
answering a question Birmingham was never asked, with nothing on the map to say
so. The honest
statement is that this map has no community-background field, which is a gap
worth naming rather than papering over with the nearest number.

`MS-B19` is `B20`'s question at eight categories instead of thirty-two, with no
extra coverage, and `MS-B22` is religion back to 1861 for Northern Ireland as a
whole, with no district breakdown at all.

**Where the denominations go.** Presbyterian Church in Ireland, Church of
Ireland, Methodist Church in Ireland and the rest are named in no other source
this map reads. Unfolded, each would be a one-country group and a filter for
Christianity would show the province at roughly its Catholic share, so all
seventeen are declared in the canonical index. Belfast then reads Christianity
73.5%, No religion 21.7%.

**One guard needed loosening, and it was right to.** The build stops when a
record carries a parent total beside its own children. NISRA writes "Other
Religions" where the ONS writes "Other religion", both meaning everything the
question did not name, and the United Kingdom's rolled-up record now carries
one row from each office -- which tripped the guard, because the NISRA spelling
lowercases to the canonical group's own name. A residual is never a parent:
there is no third figure two catch-alls are both part of. The guard now exempts
them, and a real parent beside a real child still stops the build.

### Ireland: a seat count is not a name

Ireland had nothing subnational: four provinces and 166 local electoral areas
with no religion, no ethnicity and no language, and the Factbook's national
figures as the only Irish numbers on the map.

**The CSO does not run PxWeb.** It runs PxStat, its own platform, whose API
answers RPC-style method names rather than the navigable folder tree
`probe_pxweb` walks -- so Ireland was never going to appear in that probe
however often it ran, and the endpoint shape had to be established rather than
assumed. Two measurements worth keeping: the *collection* answers on the bare
`ReadCollection` method and returns **500** on the JSON-stat-suffixed path,
while `ReadDataset` is the other way round. Neither is guessable, and the
plausible-looking one is the broken one.

**The table is called "Population".** `SAP2022T2T4LEA22` is Ireland's religion
by local electoral area and its title says nothing about religion; the subject
is a *dimension*. Searching table titles returned zero matches and that zero
was nearly written up as a finding about Ireland when it was a fact about the
search. The probe now searches dimension labels too.

**Totals are named by the source.** Every PxStat dataset carries
`extension.elimination`, stating which category of each dimension is its total
-- `T` for Ethnicity, `IE0` for the geography. Hunting for the word "Total"
would be a guess that breaks on the first table spelling it differently, and
including one doubles the composition.

**The seat count is not a name, and this was the whole join.** geoBoundaries
writes `ADARE-RATHKEALE LEA-6` where the CSO writes `Adare-Rathkeale,
Limerick`: the 6 is how many councillors the area returns. Left in the
comparison, all 166 rows miss their shape. `norm()` now drops LEA followed by
digits, and that was measured before it was added -- across both CGAZ levels
the pattern appears on 166 shapes, every one Irish, and on nothing else in the
world. The single real place called Lea, a township in the United States, has
no number after it and is untouched.

**Stripping a suffix can merge two names, and here it merges exactly one
pair.** Athlone straddles the Shannon, so the town has two local electoral
areas either side of a county boundary, and the CSO distinguishes them only by
the county it appends. Resolved geometrically rather than guessed from seat
counts: `ATHLONE LEA-5` lies 100% inside Leinster and `ATHLONE LEA-6` 99.9%
inside Connacht, so the Westmeath row is the first and the Roscommon row the
second. Each states its province, which is the mechanism the matcher already
has. A test asserts `athlone` is the *only* shared key, because a second
undetected pair would hand one area another's figures in silence. The result
reads as it should: rural Roscommon 82.7% Catholic against urban Westmeath
66.0%, which is also the check that the two were not assigned the wrong way
round.

**What it cost.** 166 of 166 shapes matched, the 166 populations sum to
5,149,139 -- Ireland's Census 2022 count to the person -- and the four
provinces roll up to the same figure. Religion arrives in four categories,
which is what exists at this geography; the fuller classification is published
for counties and provinces, and geoBoundaries draws no Irish county layer, so
the real choice was four categories across 166 areas or nothing.

### England and Wales: ethnicity was counted twice for as long as it was published

Found while reading NISRA's tables for the nesting Scotland's `KS201SC` has.
Nomis returns TS021 at **both** classification levels in one response -- five
broad groups and the nineteen columns of detail beneath them, each level
summing to the population -- and the adapter kept them all. Every one of the
503 England and Wales records shipped with its ethnicity summing to about 200%:
Bradford carried `White` 61.1% beside `White: English, Welsh, Scottish,
Northern Irish or British` 56.7%, which are the same people.

Nothing downstream noticed, and the reason is worth recording. Neither label is
in the canonical index, so the double-counting guard saw two unrelated groups
rather than a parent and its child, and the group filter did too. A composition
that sums to 200% is not subtle; it survived because no check looked at the sum.

The fix is the rule `scotland_census` already applied, lifted into
`_shared.leaves()` and used by all three UK adapters: keep a group's detail
where it has any, the group itself where it has none. Scotland's output is
byte-for-byte unchanged by the refactor, TS030 religion is unaffected because
it nests at one level, and the England and Wales records lose 2,515 rows and
now sum to 100%.

### Scotland and Northern Ireland: published, and behind a table builder

Reading the UK census at Nomis' county tier took its second-order coverage from
152 shapes to 171. The 45 that remain are all Scottish council areas and
Northern Irish districts, and they are a **source** gap: the ONS census covers
England and Wales. Scotland ran its own in 2022 through National Records of
Scotland, Northern Ireland in 2021 through NISRA.

Both offices publish exactly what this map wants -- NISRA's MS-B01 religion and
MS-B02 ethnic group by 11 local government districts, Scotland's ethnic group
and religion by 32 council areas. Neither is reachable by a program without
guessing at an undocumented interface, and that was measured rather than
assumed:

* **Nomis does not carry them.** It is the UK's shared census warehouse and this
  project already talks to it, so it was asked first. Every one of the 39
  datasets whose name contains "religion" is suffixed **EW** -- QS208EW,
  DC2201EW, LC2107EW and the rest. England and Wales, and nothing else.
* **NISRA's API endpoints are not there.** `ws.nisra.gov.uk`, the host PxStat
  deployments usually use, does not resolve at all. Under the portal that does
  exist, `data.nisra.gov.uk`, both the PxStat RESTful read and a PxWeb-shaped
  root answer 404. The portal front page and the Census 2021 results page are
  HTML carrying 26 and 52 links, none of them a file or an API.
* **Scotland's SPARQL endpoint closes the connection.** `statistics.gov.scot`
  is a linked-data platform, and `/sparql` disconnects without a response to
  both a `.json` path and an Accept-negotiated request.
* **The one workbook that is published is a bulletin's chart data.** Scotland's
  ethnic-group-and-religion release links a single spreadsheet, and it holds a
  cover sheet, a contents page, notes and ten "Figure" sheets of the
  percentages behind that bulletin's charts -- not a council-area table.

What both offices have instead is a **flexible table builder**:
`build.nisra.gov.uk` and Scotland's *search the census*. Those are JavaScript
applications with APIs behind them, and the APIs are undocumented. Guessing at
one is how five separate readings went wrong on Germany before the catalogue
was asked directly, and there is no catalogue to ask here.

So this is a third kind of block, and worth distinguishing from the other two.
Indonesia needs a key the repository owner can register for. China's statistics
bureau refuses an automated client outright. Here the data is public, free and
unrestricted -- and published only through an interface built for a person
clicking, with no static file and no documented endpoint behind it.

What would open it: a documented endpoint from either builder, a bulk download
either office publishes that these probes did not reach, or the same tables
appearing on a warehouse that does answer programs. Until then, 43 shapes stay
visibly empty rather than being given England and Wales' figures, and the three
reference dates -- 2021 for England, Wales and Northern Ireland, 2022 for
Scotland -- would in any case need saying on any map that combined them.

### China: 1.4 billion people, and three closed routes

China carries a population on all 33 of its provinces and a composition on
four. Those four -- Xinjiang, Tibet, Guangxi and Ningxia -- are **hand-compiled
rows in `data/curated/admin1_seed.json`**, which is what that file exists for.
There has never been a China adapter, and it is worth saying plainly that this
is not a broken join: the join works, 27 provinces matching by name and 5 by
prefix, and the only one that reached nothing was Guangdong, drawn under its
capital city's name and now declared in `MISSPELLED`.

So the gap is real and the question is whether it can be filled. Three routes
were measured, and all three are closed:

* **The USCB subnational series does not carry China.** `scripts/probe_hdx.py`
  enumerates all 34 datasets that organization publishes -- the route that
  served Bangladesh, Myanmar, Colombia, Pakistan, Ethiopia and eight others --
  and no Chinese one is among them.
* **The National Bureau of Statistics answers 403.** Its portal is a JavaScript
  front end over `easyquery.htm`, which serves JSON; asked by a client that
  names itself, both the provincial and the national database refuse, from an
  unblocked runner and not only from the build sandbox. That is the Bureau
  declining to serve an automated reader. Getting past it means claiming to be
  a browser, which is circumventing a refusal rather than reading a
  publication, and this project does not do that -- the same line drawn at
  Indonesia's `bps.go.id`.
* **HDX carries 577 China datasets and not one census tabulation.** Searched
  across every publisher, not only the Census Bureau, because Bangladesh
  reached this map through HDX from a different publisher entirely. What is
  there is boundaries, World Bank indicator series, conflict data, health
  sites, airports and population rasters. No minzu, no census volume.

The data exists: the Seventh National Population Census of 2020 tabulated the
56 official nationalities by province, and the four curated rows come from its
provincial communiques. What is absent is a machine-readable route to it that
does not involve pretending to be something this project is not. China stays
1.4 billion people with a population and no composition, with the reason
written down -- and with four provinces filled from the census's own published
figures rather than none.

### Germany: sixteen Laender, three categories, and a church-tax register

Germany was the largest European country with nothing below the national line:
sixteen Laender, eleven carrying a population figure and none a composition.
The Eurostat adapter had recorded why ethnicity is absent -- Germany counts
citizenship and migration background -- but made no claim about religion, and
its own header said Germany collects it. It does, and it is now on the map:
82.7 million people across all sixteen Laender, from Zensus 2022 table
**1000A-1018**.

`scripts/probe_genesis.py` is how it was found, and what it found about the
other two databases is worth keeping:

* **GENESIS-Online**, the federal database, is open to the anonymous user
  `GAST` and searchable, and holds **no religion demography at all**. The word
  matches fifteen tables -- television airtime by broadcaster, book titles by
  subject group, gross earnings by occupation, national-accounts spending by
  government function -- every one of them "Deutschland, Jahre". The word sits
  in their subject classifications, not their variables. A real absence, read
  off the catalogue rather than inferred from a failed guess.
* **The Regionaldatenbank** admits `GAST` at the login check and then answers
  401 to every catalogue search. It needs an account and nothing about what it
  holds is known.
* **The Zensus 2022 results database** has the data, behind a free account.

**Which table, and why guessing would have failed.** Four tables share the
title *Personen: Religion* and differ by a letter. Only one is cut by a civil
geography:

| table | religion | geography |
| --- | --- | --- |
| **1000A-1018** | RELZG2, 3 values | **GEOBL1 -- 16 Bundeslaender** |
| 1000A-1E18 | RELZG2, 3 values | GEOEV1 -- 19 Landeskirchen |
| 1000A-1K18 | RELZG2, 3 values | GEORK1 -- 27 Bistuemer |
| 1000A-1W18 | RELZG2, 3 values | GEOWK1 -- 299 Bundestagswahlkreise |
| 2000X-1022 | RELZG1, 7 values | GEODL3 -- Germany as a whole |

Two of those geographies are church administrations and one is electoral. A
guess would have been wrong three times in four, and the wrong answer would
have joined nothing while looking like a table that simply did not match.

**What the three categories mean.** RELZG2 counts membership of a religious
body **incorporated under public law** -- the church-tax register -- not
religious belief. Only the Roman Catholic and Protestant churches are counted
separately. Germany's Muslims, Jews, Orthodox Christians and free-church
Protestants fall inside *Sonstige, keine, ohne Angabe* together with the
irreligious and those who did not answer, because their communities are mostly
not public-law corporations. That category is the **largest bar in every Land**
and the least informative one, running from 39.1% in Rheinland-Pfalz to 86.2%
in Sachsen-Anhalt. Every record carries a `religion_note` saying so.

The finer classification exists -- RELZG1, seven categories, table 2000X-1022
-- and is published for Germany as a whole and no further. **Germany publishes
something coarser about its Laender than about itself**, and this map shows the
coarser thing because it is the only one cut by a geography.

The figures are what German demography looks like, which is the check that
matters: Saarland 51.0% Catholic and Bayern 44.2%, Schleswig-Holstein 39.9%
Protestant, and the five eastern Laender between 73.9% and 86.2% *other, none
or not stated* -- the GDR's secularisation, still the sharpest religious line
in the country. The sixteen sum to 82.7 million, which is Zensus 2022's own
count and about 1.4 million below the register-based estimate the Factbook
carries; that gap is the census's headline finding, not a fault here.

**Four things were wrong before they were right**, and all four were one error:
reading our own request's failure as a fact about the server. They are recorded
because each nearly closed Germany as an absence.

* Every endpoint on all three instances answered **405** to a GET. That is the
  path existing and the verb being wrong.
* `data/tablefile` answered **406 Not Acceptable** -- content negotiation
  refusing an `Accept: application/json` the probe had chosen itself. Asked
  with `*/*` it answers 401, which is the real finding.
* GENESIS-Online answered **307**, and urllib follows neither 307 nor 308 for a
  POST. That instance had not been asked anything at the point it was nearly
  filed as not answering. Its redirect named `genesis.destatis.de`, not the
  `www-genesis.destatis.de` every Destatis document gives.
* With a valid account the server still answered `Username: GAST`, which reads
  exactly like a rejected credential. It was an **ignored** one: this API reads
  the account from **request headers**, and ignores it as a query parameter, as
  HTTP Basic and as a bearer token. `helloworld/logincheck` settles it, because
  it names the user the server thinks it is talking to.

Two smaller traps in the payload: `data/tablefile` returns a **ZIP** holding one
CSV whatever `compress=false` says, and that CSV is **UTF-8 with a byte-order
mark** rather than the Windows-1252 older GENESIS exports use. And in ffcsv
every figure appears twice, once as a percentage and once as a count -- only
the counts are read, because a count rebuilt from a rounded percentage is out
by thousands of people and carries no sign that it was never counted.

**A second level, from the same table.** `1000A-1018` is not a sixteen-row
table. It is published cut by Bundeslaender, by 36 Regierungsbezirke, by 400
Landkreise and by 10,787 Gemeinden, and asking for it without naming a
geography returns whichever it calls its default -- so four separate runs read
the same code and saw sixteen rows while the finer cuts sat behind it, never
absent and never asked for. `regionalvariable` is the parameter that asks.

That was found by asking the catalogue rather than reading titles. All four
single-variable religion tables are titled *Personen: Religion* and none of
them says what it is cut by, so an absence read off a list of titles would have
been a fact about titles. `catalogue/variables` and `catalogue/tables2variable`
make it a fact about the database.

**GEORB1 is the cut this map can use, and GEOLK4 is not.** geoBoundaries draws
Germany at ADM2 as 38 Regierungsbezirke and statistische Regionen, not as
Kreise, so the 400-row cut would join nothing at all while looking like four
hundred rows of progress.

GEORB1 returns 26 areas and all 26 reach a shape. Nine more come from the Land
cut of the same table -- see below -- for 35 of the 38 shapes and 78.6 million
people.
Getting there needed three prefixes, because the slash in
*Regierungsbezirke/Statistische Regionen* is doing real work: North
Rhine-Westphalia, Bavaria, Baden-Wuerttemberg and Hesse still have
Regierungsbezirke (`Reg.-Bez. Arnsberg`), Saxony renamed its own
*Direktionsbezirke*, and Lower Saxony abolished its own in 2004 and reports
*statistische Regionen* in their place. The boundary file carries the bare name
in all three cases, so the prefixes are stripped in the reader rather than
declared as misspellings -- they are what a source puts on every row of a
geography, not names anybody got wrong.

**Nine Laender have no Regierungsbezirke at all** -- Berlin, Hamburg, Bremen,
Saarland, Schleswig-Holstein and four eastern ones -- so GEORB1 has no row for
them, and geoBoundaries draws each as a single ADM2 shape carrying the Land's
own name. The shape *is* the Land, so the Land's figures are that shape's
figures and they are filled from the Land cut. Leaving them blank marked as
unmeasured nine places measured exactly once at exactly that extent.

That is a declaration, not the rule "a Land with no GEORB1 row", because the
rule catches ten and the tenth must not be filled. **Rhineland-Palatinate
abolished its Regierungsbezirke in 2000** and geoBoundaries still draws
Koblenz, Trier and Rheinhessen-Pfalz, so its single Land figure would have to
be split three ways and cannot be. Those three stay visibly empty rather than
taking a figure from a level they were not measured at, and the adapter refuses
outright if the two lists ever disagree -- a declared Land missing from the
Land cut, a name that does not match, or a Land that has since acquired its own
GEORB1 row and would be counted twice.

Credentials reach the adapter through `ZENSUS_USER` and `ZENSUS_PASSWORD` in
the environment, never a command line, and both workflows pass them. Without
them the adapter **refuses** rather than falling back to anonymous: `GAST` can
search the catalogue and read nothing, so an anonymous run would fetch a 401
that would have to be told apart from a table that had gone away.

### Nigeria: asked, and never tabulated

244 million people and no subnational composition, which makes Nigeria the
largest gap on this map after Indonesia. Four routes measured, and the answer
is unusual enough to be worth stating precisely: **the questions are asked, and
no published subnational tabulation of the answers is reachable.**

* **The Census Bureau's series** carries a `Nationality` sheet and nothing else
  -- Nigerian by birth, by naturalization, other ECOWAS, African other,
  non-African. That is citizenship, refused earlier and refused still.
* **DHS's subnational series on HDX** is 45 CSVs and none of them is a
  composition: anemia, anthropometry, literacy, immunization, water, tobacco,
  fertility. The mismatch is structural rather than incidental -- DHS publishes
  indicators broken down *by* region, never the distribution of the
  characteristic doing the breaking down. No amount of looking further into
  that series changes it.
* **NBS Nigeria's own site** publishes no census tabulation of either field.
  Nigeria's census has not carried religion or ethnicity for decades; the
  balance between them decides revenue allocation and representation, and the
  questions have been left off.
* **NBS's NADA microdata archive** is where they are, and it took a corrected
  probe to see it. `microdata.nigerianstat.gov.ng` holds 27 studies, and NADA's
  search matches *variable labels*, so it answers "was this asked" directly:
  MICS/NICS 2016-17 carries 11 ethnicity variables and MICS5 2016 carries 8,
  both public; DHS 2008 carries 4 of each; `tribe` matches nothing anywhere.

So the block is not availability and not permission. It is **shape**: what
exists is microdata -- individual survey records -- and every figure on this
map comes from a tabulation someone published. Turning MICS5 into a state-level
religious composition means downloading records behind an account, applying
sampling weights, and producing estimates with their own error, which is a
different kind of claim from "the census counted this many". This project has
never done that, and doing it silently would put survey estimates beside census
counts with nothing to tell them apart.

Two smaller cautions recorded so the next reader does not have to rediscover
them. The `language` search returns large hit counts -- 37 in one COVID-19
*phone* survey -- which is language of interview, not mother tongue; the count
is not evidence of a composition. And the Living Standards Survey 2018-19, the
one study designed to be representative at state level and the reason the probe
was written, appears in neither the religion nor the ethnicity search. The best
lead was the wrong one, which is the argument for asking rather than assuming.

What would open Nigeria: a published MICS or DHS tabulation by state, from
either office; or an explicit decision that this map may carry weighted survey
estimates, labelled as such, and the machinery to compute them.

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

Re-confirmed on 11 September 2026 against a *regency* site rather than a
provincial one: `metrokota.bps.go.id` answers **HTTP 403** to the runner
exactly as the provincial hosts do, so the block is the estate's and not one
tier of it. Two further probes that day were wasted and are recorded so the
next reader does not repeat them: `data.humdata.org`'s search page is rendered
in the browser, and its CKAN API returns JSON, so `probe_links` -- which
extracts links from HTML -- reports "0 matching links" for both and that is a
fact about the tool, not about HDX. The HDX bullet above already stood on a
real check.

**What the owner's manual downloads showed.** Five BPS CSVs were supplied on
the same day, and they resolve two questions.

* *Jumlah Penduduk Menurut Kecamatan dan Agama yang dianut, 2025* is the right
  table in the right shape -- counts, six religions, at **sub-district** level,
  finer than the kabupaten this section is waiting for. The copy supplied
  covers one kota: Metro, in Lampung, five kecamatan and 173,746 people against
  ~7,200 kecamatan and 284 million. It confirms the table is published per
  regency and is reachable by a person in a browser; it does not make the
  estate reachable by a reader.
* The four language tables are **not** usable, and the reason is about the
  question rather than the coverage. *Bahasa yang Pertama Kali Dikuasai* is a
  clean three-way partition of all 38 provinces summing to 100.00, but its
  categories are Bahasa Indonesia / Bahasa Daerah / Bahasa Asing -- a *kind* of
  language, not a language. Knowing that Central Java is 92.84% "a regional
  language" is not knowing it is Javanese, and this map's language field holds
  named groups. *Kemampuan Berbahasa Indonesia* measures a skill rather than a
  composition; *Penggunaan Bahasa Daerah* by age has no geography; the same by
  province is a binary use/do-not-use, a different question again. The owner
  decided on 11 September 2026 to leave Indonesia's language field an explicit
  gap rather than fill it with a composition of language types.

**The route that would work.** BPS publishes the religion table per province,
one table covering that province's kabupaten, and a person in a browser can
download it -- which is how the Metro file arrived. Thirty-four downloads would
close a 284-million-person gap at kabupaten level without a key and without
pretending to be a browser. That is a smaller ask than it looks and it is the
first thing to try if the WebAPI key does not materialise.

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
| Ukraine | **2001** (State Statistics Service) | language, ethnicity | 27 oblasts, summed from 661 rayons; nationality from the `NL_ETH_*` block of the Nationality-Language sheet, which is the whole population of each nationality |

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

The table below is the measurement as it stood when Addis Ababa's ten
sub-cities were declared shapeless. They are now summed into the shape instead
-- see *Addis Ababa: the fold that was pointing the wrong way*, below -- so on
the next run Ethiopia's zones read 84 areas rather than 93 and one fewer shape
is empty. The figures here are left as they were measured rather than replaced
with what they are expected to become.

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

#### Addis Ababa: the fold that was pointing the wrong way

"Declared shapeless" was the right answer for a Philippine city drawn inside
its province, and the wrong one for Addis Ababa's ten sub-cities -- and the
difference is a fact about the shape, not a matter of taste.

A highly urbanized city is drawn *inside* something larger that has a row of
its own: the province's figures already cover the city, so the city's row has
nowhere to go and `no_shape` says so. Addis Ababa's sub-cities are not inside
anything else at the second order. The ten **are** the second order there:
geoBoundaries draws exactly one zone-level shape in Addis Ababa, labelled
"Region 14", and it is the region entire. Declaring the ten absent left that
shape with no religion, no ethnicity and no language -- 2.7 million people, the
capital city, blank -- while ten rows of real figures sat beside it with
nowhere to be shown.

So they are summed into it, through the same `Country.merged` facility Karachi
uses, and the source itself says the sum is right. The ten sub-cities come to
**2,739,551** against a region row of **2,739,551** -- exact, group by group,
for all six religions. That is the census's own arithmetic stating that these
ten are all of Addis Ababa and nothing else is, which is the one thing a merge
declaration cannot establish about itself.

The shape is reached by an alias rather than by its name. The census calls the
place Ādīs Ābeba; "Region 14" is a label on a polygon, and it is declared as
what geoBoundaries calls this place rather than adopted as what the place is
called. At the first order it matches nothing, because no region is drawn under
that name.

"Special Woreda" is deliberately left alone. It looks like the same case and is
not: its bounding box is a single small area in Amhara, one special wereda
rather than a shape standing for all of them, and summing Ethiopia's scattered
special weredas into it would put people from five regions inside one polygon.
Identifying which wereda it is from a bounding box is a guess, and a guess is
how a mis-match gets made.

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
  gains religion as well as ethnicity: Buddhist 88.4%, Christian 7.2%, Islamic
  3.1%, Hindu 0.8%, Other 0.5%, Nat 0.1%, from the 2014 census, which published
  religion even while withholding ethnicity. That first figure read 90.9% here
  until the states that carry it were summed: with the other five it came to
  102.6%, so it was a transcription and not a misread table -- a misread would
  have moved every share, and these agree with the summed states to within
  0.02 points. 88.4% is also what the census itself published, 87.9%, plus the
  areas the sheet leaves out.

* **Myanmar's two questions do not count the same people.** Religion is asked
  of everyone; Table 14 is *Ethnic Nationalities Living*, and counts only the
  135 recognised national races. Across the fourteen first-order areas the
  religion columns total 47,915,382 and the ethnicity columns 46,701,817, and
  the 1.2 million difference is not spread evenly: Rakhine alone accounts for
  584,142 of it and Yangon for 274,710. So Rakhine's 93.7% Rakhine is a share
  of ethnic nationalities, not of residents, and the people missing from that
  denominator are the same ones the 2014 census declined to enumerate. Both
  numbers are published as they stand, with the table's own title carried in
  the citation for the ethnicity field, because a share cannot state its own
  universe.

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

**Religion, later.** The 2000 census did publish religion by province, in a
final report per province under `web.nso.go.th/pop2000/finalrep/`, and the
Wikipedia article *Nationality, religion, and language data for the provinces
of Thailand* transcribes the Buddhist, Muslim and Christian shares from all 76
of them, each row citing its report. That article is read through the MediaWiki
API (`scripts/fetch_census/thailand.py`), which the NSO's hosts never were, and
the record's source is the report the row cites. It is a 2000 figure and says
so; a 2010 or 2020 provincial religion table exists behind the same 418 and
would replace it the day the office serves one. The article's nationality
columns are citizenship and are not read as ethnicity, and its "linguistic
minorities" cells are the partial list the paragraphs above describe, so
language keeps its gap.

### Wikipedia transcriptions: what was measured and left

`scripts/probe_wikitable.py` prints an article's tables compactly, and one
runner pass read the list articles for the largest countries still empty at
the first level. Three carried a census table by region and became specs in
`scripts/fetch_census/wiki_census.py` or `thailand.py` (Thailand, Kazakhstan,
Cambodia). The rest did not:

* **Taiwan** -- *Demographics of Taiwan* has languages used at home by
  division, but Mandarin 83.5% beside Hokkien 81.9% is a multi-response
  question, not a composition, and is not read.
* **Kazakhstan, ethnicity** -- *Ethnic demography of Kazakhstan* carries the
  national series only; the 2021 census's ethnicity by region is on no list
  article measured.
* **Romania, Peru, Uzbekistan, Ecuador, Guatemala, Rwanda** -- the demographics
  and religion articles carry national series, age pyramids and vital
  statistics by region, and no ethnicity, religion or language table by
  county, department or province.

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

### Japan and Turkey: 208 million, and two different kinds of empty

Both are large, both are blank below the country line, and the reasons are not
the same -- which is the point of measuring rather than assuming.

**Japan does not ask, and that is now a fact about the catalogue.** The
Kokusei Chosa records name, sex, date of birth, marital status, nationality,
household relationship, dwelling, employment, industry, occupation and
commuting. Religion, ethnicity and language are all three declared here, and
all three used to rest on reading that questionnaire -- which settles the
census and not the country. e-Stat is the portal for *every* Japanese
government statistic, so a question a census declines can still be asked by an
agency survey, and nobody here had looked. The catalogue has now been asked,
with a free application id in `ESTAT_API` and `scripts/probe_estat.py` against
e-Stat's REST API 3.0: `getStatsList` for what exists, `getMetaInfo` for what
each table is cut by, `getStatsData` for the figures.

**Counted, not recalled.** e-Stat says how many tables carry a word before it
says which ones, and both numbers are worth having: the surveys say who asks,
the tables say how much of the catalogue is involved.

| word | tables | surveys | what they are |
| --- | --- | --- | --- |
| 宗教 religion | 5,603 | 39 | almost all of it economic: 宗教 is an industry class in the Economic Census, the establishment statistics and the national accounts. Exactly one survey is demography -- **宗教統計調査**, 00401101, the Agency for Cultural Affairs |
| 信者 believers | 30 | 3 | that survey, plus two that use the word for something else |
| 信徒 believers, the other word | 0 | 0 | nothing at all |
| 民族 ethnicity | 8 | 2 | six 社会教育調査 tables of *museum holdings*, where 民族資料 is a shelf of ethnographic objects, and two 矯正統計調査 tables counting foreign prisoners by nationality |
| 言語 language | 636 | 14 | 学校基本調査 counts of graduate schools (言語文化研究科 and its kin) and ICD-10 tables in 人口動態調査 and 患者調査, where 言語 is a speech disorder |
| 母語 mother tongue | 2 | 1 | one MEXT survey of schoolchildren -- below |
| アイヌ Ainu | 13 | 3 | prosecution statistics, human-rights infringement cases, and the national forest yearbook. None of the three counts a population |
| 国籍 nationality | 2,280 | 26 | the census, the migration report, immigration and residence statistics |
| 外国人 foreign residents | 2,017 | 30 | likewise |

Asked in English the same catalogue answers differently and worse. `ethnic`
matches **no survey at all**; `religion` matches eleven, none of them
宗教統計調査, because the Agency for Cultural Affairs publishes no English
title for it. An English-only sweep would have reported Japan as having no
religion statistic -- the right conclusion reached by missing the evidence,
which is the failure this file exists to prevent.

**Religion: the table exists, the API serves it, and it is not a composition.**
宗教統計調査 is published as 19 tables, two of them by prefecture: `0003282740`
(団体数, organisations) and **`0003282963`** -- 全国社寺教会等宗教団体・教師・
信者数（２）都道府県別　教師・信者数, 18,977 cells, cut by 都道府県 (48 codes),
by 教師 / 信者, and by 宗教系統: 神道系, 仏教系, キリスト教系, 諸教. It carries
every year from 2008年度 to 2025年度. The figures are there, by prefecture, in a
machine-readable series eighteen years long, and they still cannot go on this
map. The reason is arithmetic, and every number below is from `0003282963` at
2025年度 (as of 31 December 2024), with population from e-Stat's own
社会・人口統計体系, table `0000010101`, item `A1101_総人口` at 2024年度:

* **175,054,047 believers against 123,802,000 people: 1.41 per person.** The
  table does not partition a population. It counts memberships, and the same
  person is counted by a shrine and by a temple.
* It does not partition itself either. Its own 全国 row is 175,054,047 and its
  47 prefecture rows sum to **175,044,047** -- ten thousand apart, all of the
  difference in 仏教系 (80,463,918 nationally against 80,453,918 summed).
* The excess is not uniform, which is what would have made it survivable. The
  ratio runs from **0.54 in Kanagawa to 3.19 in Kyoto**, a 5.9-fold spread:
  Kyoto 3.19, Tokyo 3.09, Nagano 2.99, Shimane 2.84 at one end; Kanagawa 0.54,
  Chiba 0.56, Okinawa 0.61 at the other.
* The mechanism is visible in one pair. **Tokyo reports 35,352,899 Buddhist
  believers -- 43.9% of every Buddhist in Japan, in a prefecture holding 11.5%
  of the people** -- against Kanagawa's 1,762,105, which is 2.2% of the
  Buddhists in 7.5% of the people. A religious corporation reports its whole
  membership against the prefecture where it is *registered*, and the head
  temples are in Tokyo. Kyoto is the same artefact from the other side: its
  3.19 is Shinto (6,211,472) while its Buddhist count is 1,521,269, which is
  1.9% of the national figure in 2.0% of the population.

Read as shares -- which is what this map would do with them -- those rows put
**80.8% Buddhist and 16.5% Shinto on Tokyo**, 18.9% and 77.2% on Kyoto, 35.5%
and 48.2% on Kanagawa, and 90.4% Shinto on Okinawa. That is not a map of what
people believe. It is a map of where religious head offices are registered, and
it would be drawn in the same colours as Germany's church-tax register and
India's census, with nothing on the panel to say it means something else.

`religion_basis: "adherents"` does not rescue it. That field exists for a
figure that counts adherents rather than answers and *still partitions a
population* -- the 2020 U.S. Religion Census, which `us_acs.py` labels that way,
reaches about half the population and never exceeds it. A figure that sums to
141% of the people partitions nothing, and no basis label makes it do so. So
religion stays `not_collected`, and the declaration now rests on a table id
rather than on a yearbook's narrative.

**Ethnicity: eight tables, and not one of them is about anyone's ethnicity.**
Six belong to 社会教育調査 and count what museums hold -- 民族資料, ethnographic
objects on a shelf. Two belong to 矯正統計調査 and count foreign prisoners by
nationality. This is the trap Turkey set below, in Japanese: a keyword pass
that reported "8 matches for ethnicity" would have been counting museum
inventories. Nothing in e-Stat asks a person what they are, and the English
`ethnic` matches nothing at all.

What Japan does publish by prefecture is **nationality** -- the census's 国籍別
tables, 在留外国人統計 (00250012) and 出入国管理統計 (00250011) -- and that is
refused here for the reason Nigeria's, Sudan's, Libya's and Syria's
`Nationality` sheets were refused: citizenship is not ethnicity, and published
as one it would describe a country of 123 million as ethnically uniform. The
catalogue confirms the refusal rather than changing it: 2,280 tables carry
国籍 and every one of them is a passport.

**Language: two tables, and the denominator is a support need.** 母語 matches
exactly two tables in the whole of e-Stat -- `0003328485` for the country and
`0003328491` by prefecture -- and both belong to MEXT's 日本語指導が必要な
児童生徒の受入状況等に関する調査. The prefecture table is cut by 都道府県 (48
codes) and by nine categories (合計, 英語, 韓国・朝鮮語, スペイン語, 中国語,
フィリピノ語, ベトナム語, ポルトガル語, その他) for 2012, 2014 and 2016年度 and
no later. Its universe, at 2016年度, is **34,335 children**: foreign-national
pupils in public schools who need help with Japanese, 0.03% of the population,
2,932 of them in Tokyo. Two further tables (`0003328486`, `0003328492`) do the
same for Japanese-national pupils. These are a real count of a real thing and
they are not a language composition: the denominator is a support need, and
every child who speaks Japanese at home is outside it. Language stays
`not_collected`, and the 636 tables matching 言語 are graduate schools and
speech disorders.

**Access was never the problem.** e-Stat answered every request made of it:
`getStatsList`, `getMetaInfo` and `getStatsData` all return JSON to a plain
client over TLS, the application id is free, and the eighteen-year religion
series came back in one call. The key reaches the runner as a repository
secret, never a command line, and `probe_estat.scrub()` takes it out of every
line the probe prints -- URLs, echoed parameters, error bodies -- because a
probe whose product is a committed log cannot rely on remembering. What is
missing from Japan is not access and not effort. It is the question.

**Turkey may ask, and cannot be read.** Four routes measured:

* **HDX** carries about thirty Turkiye datasets and not one is a composition:
  World Bank indicator series, FAO food prices, earthquake response, conflict
  forecasts, geoBoundaries.
* **`data.tuik.gov.tr`** times out; its `Kategori/GetKategori` path answers
  3,685 bytes with no links, which is a fact about that path rather than about
  TUIK -- it is a fragment endpoint, and a first probe that treated it as a
  measurement would have been fiction.
* **`www.tuik.gov.tr`** answers properly, 431 kB, and names the two places the
  data would live: `biruni.tuik.gov.tr/medas` and its regional statistics
  portal.
* **MEDAS returns 66 kB and zero topic links**, because the catalogue tree is
  built client-side. The regional portal answers 6.5 kB, a frame.

That looked like the Scotland and Northern Ireland case -- a JavaScript
application with an undocumented API -- and it was not. **MEDAS renders its
subject list server-side**, as ninety-two `<option>` elements; only the
*contents* of a subject load over JavaScript. A saved copy of the page carries
the whole catalogue, and a link crawler saw none of it because there are no
links to see.

**Ninety-two subjects, and not one is religion, ethnicity or mother tongue.**
The list runs Address Based Population Registration System Results, births,
deaths, marriages, divorces, life tables, family structure, labour force,
education, health, poverty, income distribution, agriculture, industry,
prices, foreign trade, tourism, road traffic, prisons, suicide, cinema,
theatre, libraries. Turkey publishes a great deal by province. None of it is
what this map needs.

So Turkey is declared, and the declaration rests on that catalogue rather than
on history. The history is the explanation rather than the evidence: the census
last asked mother tongue and ethnicity in **1965**, and what replaced it is an
address-based register, which records where a citizen lives rather than what
they are.

One trap worth recording, because it nearly produced three findings out of
nothing. A first keyword pass matched `din` -- Turkish for religion -- and
returned "Building Construction Cost Index", "Building Permit Statistics" and
"Survey on Building and Dwelling Characteristics". All three are *Buil-din-g*.
Matching on word boundaries returns nothing, which is the true answer.

And the route that worked is worth keeping: **a saved page beat six probes.**
`data.tuik.gov.tr` timed out, its `GetKategori` path answered 3,685 bytes of
fragment, MEDAS answered 66 kB with zero links, and none of that settled
anything. One right-click on a rendered page settled all of it.

### Brazil: the table that answered was the wrong table

Brazil's 27 states carried a religion composition summing to a quarter of
each state's population, read as a quirk of a sample table. It was not.
Table 10086, which the adapter had been calling "population by religion",
is a fertility table: its one variable is women aged 12 and over who have
had live births, cross-tabulated by religion. Every figure on the map for
Brazil's religion was the religion of mothers. The id had been guessed, the
guess answered numbers, and numbers that answer look like the right ones.

`scripts/probe_sidra.py` now asks IBGE's aggregates catalogue what a table
*is* -- its name, variables, classifications and levels -- before any number
is read. The 2022 census religion table is 9537, persons aged 10 and over by
religion, sex and age group, published to municipality level; SIDRA returns
the Total of any classification a URL leaves out, so naming c133 alone gives
both sexes and all ages. Every Brazilian record now says the universe is
persons aged 10 and over, and Tradições indígenas, a category the build had
never seen, is Indigenous traditions.

### The survey: 90 countries, two waves, and what a runner can measure

`survey/BRIEF.md` is the brief the research agents worked under, one JSON
finding per country under `survey/findings/`. The first wave of 40 could
search the web; the shared search budget ran out mid-wave, so the second
wave of 50 (`survey/BRIEF_WAVE2.md`) wrote from what the agents already
knew, marked `"confidence": "recalled"`, and gave the statistical office's
homepage for a runner to crawl. `scripts/survey_sources.py`, run by
`survey-sources.yml`, then requested every proposed URL, crawled the office
homepage one level for files, searched HDX, and read each country's
Wikipedia list articles and five second-level articles through the
MediaWiki API; the measurements are under `data/survey/`.

What the Wikipedia pass found: across 90 countries, the second-level
articles carried a composition block in a handful of places (Bangladesh's
upazilas, Nepal's districts, Sri Lanka, two of Canada's regions) and nowhere
that a census table did not already cover better. The list articles by
place were rarer still. Wikipedia is not where a second-level composition
lives; the statistical office's file is, and the survey's value was in
naming those files. The nineteen `not_collected` declarations added to
`NOT_COLLECTED_POLICY` in `scripts/common.py` came from the tier-C findings,
each resting on a named fact about the questionnaire.

## Afrobarometer: the first sampled source, and the rules that keep it honest

Every other figure on this map is a count. Afrobarometer Round 9 is a survey of
**53,444 people across 39 African countries**, and it carries exactly the three
things this map wants: the region a respondent was interviewed in, Q95 "What is
your religion, if any?", and Q84a "What is your ethnic community, cultural group
or tribe?". For **36 of those countries there is nothing else at all**, which is
why it is here.

It is also, on its own terms, a national instrument. A region is a sampling
stratum rather than an estimation domain, and the arithmetic is not close: the
median region holds 72 respondents and the thinnest holds 8. Measured, not
estimated, from the release itself:

| country | n | regions | median/region | thinnest |
|---|---|---|---|---|
| Ethiopia | 2,400 | 13 | 112 | 104 |
| Kenya | 2,400 | 47 | 40 | **8** |
| Nigeria | 1,600 | 37 | 40 | 24 |
| Cote d'Ivoire | 1,200 | 33 | 24 | **8** |

A share from 40 respondents carries roughly ±15 points before any design
effect and ±22 after one; from 8, ±49. Afrobarometer clusters by enumeration
area, which is worst for exactly these two questions, because religion and
ethnicity are the most spatially clustered things a survey can ask.

So three rules, none of them invented here:

* **Under 25 respondents a region is dropped, not estimated.** That is the
  Demographic and Health Surveys' own suppression threshold, and using the
  field's convention keeps this comparable to how the source is normally read.
  442 of 519 regions survive it.
* **Between 25 and 49 the region says it is imprecise**, which is what DHS's
  parentheses mean. 117 regions carry that.
* **A question never asked is `not_collected`, never a composition.** The code
  is `9994`, and it is the whole of a country when it appears: Mauritania was
  not asked about religion, and Sudan, Tunisia and the Seychelles were not
  asked about ethnicity. Mauritania still gets its ethnicity, because
  `merge_adapter` works field by field.

And one rule about precedence. `afrobarometer_region.json` is **first** in
`ADAPTER_FILES`, which is the lowest authority, because three of the 39
countries already have counts: Ethiopia's 11 regions and 72 zones, Mali's 9
regions, South Africa's 9 provinces. A survey estimate silently replacing a
census figure is the invisible kind of wrong this project exists to avoid, and
ordering is what prevents it.

**What the codebook cost.** The value labels are parsed from the published
codebook rather than typed, and three parsing faults were caught by checking
the parse against the data rather than by reading the output. Label 821 arrived
as `New` instead of `New Apostolic Church`, because the codebook wraps a label
across lines. Label 9994 arrived as `Not asked in the` -- the code the
not-collected rule matches on, so the rule would have failed open and given
Mauritania a religion. And country 40 arrived as `Zimbabwe Note: Assigned by
data managers`, because that block ends with `Note:` rather than `Source:`.
None would have raised an error.

**Aliases, not new groups.** Afrobarometer offers a respondent a brotherhood
rather than a faith, and in Senegal most take it, so `canonical_groups.py` now
folds Mouridiya, Tijaniya, Qadiriya, Ismaeli and Ançardine into Islam -- a
filter for Islam that omitted the orders would show Senegal as barely Muslim.
Its named churches fold into Christianity the same way, the Zionist Christian
Church among them, which is South Africa's largest single denomination. One
label is deliberately left alone: **Faith of Unity** is a Ugandan new religious
movement rather than a Christian denomination, and it keeps its own name rather
than being folded on a guess.

## One ISO code, several places

Six ISO3 codes carry more than one Factbook profile, because the Factbook
describes places and ISO 3166 assigns codes to administering states. `PSE` is
Gaza *and* the West Bank; `SJM` is Jan Mayen *and* Svalbard; `AUS` also carries
Ashmore and Cartier and the Coral Sea Islands; `FRA` also carries Clipperton
Island; `UMI` carries Wake and Navassa.

One profile per code owns the boundary, and the others are kept as
geometry-less records so their figures stay visible and searchable -- the West
Bank's 3,310,554 people are published and would otherwise vanish.

**What a secondary profile does not own is subdivisions.** Those are filed by
ISO3, so reading them by code would hand the uninhabited Coral Sea Islands
Australia's 9 states and 547 districts, and give Clipperton Island France's 13
regions. The coverage matrix exists to say where data is missing, so a record
overstating what it contains is worse there than anywhere else: an unmatched
row is a visible gap, a mis-matched one is invisible. `subdivision_owner()`
draws the line -- a record owns the code's children only when its id *is* the
code -- and having no polygon is explicitly not the same test, so Hong Kong
keeps its own districts.

A related correction: Factbook stem `ck` is **Cocos (Keeling) Islands**, not
the Cook Islands. It had been declared `COK`, which took the Cook Islands'
code, suffixed the real Cook Islands to `COK-CW`, and then dropped them at the
join -- 7,592 people absent from the map because 593 wore their code. Cocos is
`CCK`.

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

**Yanam is under Andhra Pradesh, and it is the boundary file saying so.** The
map lists Yanam as a district of Andhra Pradesh. It is not one: it is a 30 km²
enclave of Puducherry, 600 km from the rest of that union territory, entirely
surrounded by East Godavari district. The census adapter has it right — its row
says Puducherry, and Puducherry's state total of 1,247,953 includes Yanam's
55,626 people. The parent on the map comes from the shapes, and CGAZ's shapes
disagree with each other about this one. Its ADM1 polygon for Andhra Pradesh is
not cut to exclude the enclave: it covers 66% of the ADM2 Yanam feature and
contains its representative point. CGAZ's Puducherry ADM1 *does* carry a Yanam
part, and that part overlaps only 34% of the ADM2 feature. Two CGAZ levels drawn
from different sources, neither one hole matching the other, so a
point-in-polygon test lands in the state that surrounds it rather than the one
that administers it. Nothing here can fix that without asserting a boundary the
file does not draw, so it is reported rather than overridden.

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

Ladakh is now summed in the adapter instead, from the census's own rows rather
than from whichever of its districts happen to reach a shape — see *Telangana,
Ladakh, and summing a state from its districts* above. It is kept here as the
case that shaped this function, and because the control it was built on is the
same one: the sum has to meet a population nobody involved in the sum
published.

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
  had none. This is the dangerous case, because the sum would look whole and
  describe only part of the territory. Telangana's refusal was right for the
  wrong reason: the nine that *did* carry figures were eight mis-matches and
  Hyderabad, so a sum over them would have counted 31.7 million people across a
  third of the state. It now has 32 gaps out of 33 and a state figure summed
  from the census's own ten district rows, which is the honest form of the same
  arithmetic.

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

### Measured on the runner, and declared: Iran, Korea, Egypt, Afghanistan, Venezuela

A second pass over the largest countries still empty at the first level, after
the Wikipedia transcriptions above, ended in declarations rather than files:

* **Iran** -- the 2016 census asked religion and the Statistical Centre
  publishes it by province, but `amar.org.ir` ends the TLS handshake before a
  standard client reads a page (`SSL: UNEXPECTED_EOF_WHILE_READING`, measured
  on the runner). Verification is not turned off for it. The country carries a
  `gap_reason` saying the data exists and is unreachable; ethnicity and
  language were already declared not collected.
* **South Korea** -- the 2015 census asked religion and KOSIS publishes it by
  province, behind an API that needs a registered key; *Religion in South
  Korea* carries the national series only. Declared a gap at first; the
  survey below has since filled the provinces, and the census replaces it
  when the key exists.
* **Egypt** -- CAPMAS collected religion in 2017 and has published nothing
  by governorate since 2006. Collected and withheld is a `gap_reason`, not
  `not_collected`.
* **Afghanistan** -- no population census has ever been completed (the 1979
  count was abandoned partway), so no census question exists for any of the
  three fields: `not_collected` on all three, with the NSIA's estimates named
  as what does exist.
* **Venezuela** -- the 2011 census asked indigenous and Afro-descendant
  self-recognition and not religion; `not_collected` for religion only.

### South Korea: a survey, spread by decision

Hankook Research's weekly report No. 358-3 (3 December 2025) pools the
religion question from the 22 waves of its biweekly web panel run January
to November 2025 -- 23,000 adults aged 18 and over, weighted by region, sex
and age to the resident register -- and prints it on page 8 by seven
residence regions: Seoul; Incheon/Gyeonggi; Daejeon/Sejong/Chungcheong;
Gwangju/Jeolla; Daegu/Gyeongbuk; Busan/Ulsan/Gyeongnam; Gangwon/Jeju. The
reader takes the 2025 column (Protestant, Catholic, Buddhist, has a
religion, no religion, whole percentages), derives "other religions" as the
printed "has a religion" less the three named faiths (it must land between 0
and 3), requires "has" and "none" to make 100 in every row, and rebuilds the
printed national row from the seven regions weighted by their share of the
adult population as the report prints it on page 10, within one point.

**The exception, stated.** The seven regions are coarser than the seventeen
provinces, and the map's rule elsewhere (the Bahamas, India's split
districts) is that a coarser figure is not spread across the shapes it
covers. The owner decided on 11 September 2026 that Korea carries the survey
anyway, because nothing finer is reachable: each province holds its region's
figure and its note says which region and how many provinces share it, so a
reader of Sejong sees that its figure is the Daejeon/Sejong/Chungcheong one.
The file sits beside Afrobarometer at the bottom of the authority order, and
the 2015 census (KOSIS, once a key exists) replaces it field by field.

Two limits worth keeping in view: it is a survey of adults, so it is not a
population composition, and a web panel: the report itself prints the 2015
census beside its series, which reads Catholics at 11% against the census's
8%. The report is Hankook Research's copyright, which permits research
citation of a small part with attribution and forbids redistribution; seven
rows of one table are read from the PDF at the pollster's own URL, and the
PDF is not stored.

### The African census sweep: reached, and not

One runner pass over ten statistical offices, for the countries whose
first-level religion still came from the Afrobarometer survey. Zimbabwe and
Burkina Faso became adapters. The rest:

* **Mozambique (INE), Senegal (ANSD), Côte d'Ivoire (INS), Uganda (UBOS)** --
  each fails certificate verification (an incomplete chain, or a certificate
  not valid for the host), and this project does not turn verification off.
* **Malawi (NSO)** -- the census page is a 3.7 MB script shell whose report
  files sit behind a content-management download API no anchor names; the
  guessed report URL answers 404.
* **Benin (INStaD)** -- the RGPH4 volumes are scanned images (Tome 3: 18 MB,
  20 pages, no text).
* **Guinea (INS)** -- RGPH 2014 is an indicators portal with no files; the
  RGPH-4 2025 preliminary results are counts only.
* **Liberia (LISGIS), Sierra Leone (Stats SL)** -- the sites carry no report
  links a reader can follow (a redirect stub of 168 bytes for Stats SL).

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
