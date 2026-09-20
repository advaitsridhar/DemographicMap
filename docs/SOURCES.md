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

### A second level that is not a partition — Uruguay

Reported as "nothing is visible at admin2 for Uruguay". It is not a build
failure and not a join failure. Everything in the pipeline checks out:
`site/data/admin2/URY.json` holds 124 records, all 124 ids match a CGAZ ADM2
`shapeID`, all 124 parents resolve to a real Uruguayan department, and URY
features decode out of `site/tiles/admin2.pmtiles` at z6, z7 and z8.

What is true is geometric, and measured against the boundary files with an
equal-area projection:

| level | shapes | area | share of the country |
| --- | --- | --- | --- |
| ADM0 | 1 | 177,859 km² | — |
| ADM1 departments | 19 | 177,753 km² | **99.9%** |
| ADM2 municipios | 124 | 65,417 km² | **36.8%** |

**Uruguay's second-order units are municipios, and municipios do not tile the
country.** A municipio is constituted around a population centre rather than
carved out of the map (Ley 18.567 of 2009), so the territory of a department
lying in no municipio is administered by the departmental government directly.
Flores is 0.0% covered, Florida 5.7%, Durazno 9.4%, Tacuarembó 11.8%.

**Why that reads as invisibility rather than as a gap.** Above roughly z7.75
the first-order layer has faded out and only the second-order layer paints.
Every fill in the style paints a *unit*, so ground inside no unit fell through
to the background — which is the water colour. Zoom into the interior and you
did not see a country with missing data; you saw sea. A missing figure is a
gap and the panel says so; ground drawn as ocean is a false statement about
the world, and the worse of the two.

Two changes, and they answer different questions:

* `PARTIAL_LEVELS` in `scripts/build_entities.py` declares the level and why,
  and the note reaches all 124 municipios and nothing else — not Uruguay's
  departments, which do tile the country and do carry figures.
  `check_level_coverage()` re-measures the declaration on every build and
  stops it if the figure a reader is shown has drifted **in either direction**,
  since a level that quietly became a tiling would leave a false sentence
  standing. The same pass logs any country that develops this shape without a
  declaration.
* The map paints a flat land colour under the declared countries, above the
  water background and below every data fill. It carries no feature-state: an
  unmapped stretch of Durazno must not borrow its department's number, because
  a unit that does not exist cannot be given a measurement. The country list
  comes from `build.json`, emitted from `PARTIAL_LEVELS`, so the declaration
  and what the map draws from it cannot disagree.

**Uruguay is a category of one.** Ranking all 218 countries CGAZ draws
second-order units for, by coverage lost between the first level and the
second: Uruguay 63.2 points, Tonga 19.5 (a 683 km² archipelago whose first
level is equally partial), Uganda 13.1 (Lake Victoria, which is water and
*should* be drawn as water), Bahamas 6.4 (open sea between islands), Kuwait
5.6. Nothing else exceeds three — which is why the land underlay is filtered
to declared countries rather than applied globally.

**It is recorded rather than repaired.** Inventing "resto del departamento"
polygons would put units on the map that Uruguay does not have.

Uruguay went unnoticed for as long as it did because a level with no polygons
looks exactly like a level with no data, and the only thing separating them is
a measurement nobody was taking.

### Romania — the census read through the Internet Archive

Romania had the largest single count of composition fields with no source
read: 9,829. Not for want of data — the census asks ethnicity and religion
and publishes both by județ — but for want of a route.

**Every Romanian host is unreachable from the runner**, measured five ways
across two days:

| host | result |
| --- | --- |
| `insse.ro` (INS), http and https | `[Errno 101] Network is unreachable` |
| `statistici.insse.ro` (TEMPO) | TLS handshake failure |
| `recensamantromania.ro` | timed out, including at 90s |
| `data.gov.ro` | timed out |
| HDX, searched for Romanian census | no dataset |

Errno 101 is a routing failure: no route to the host at all, not a slow
server and not a block page.

**So the office's own workbooks are read from the Internet Archive** — the
same trade already made for Bangladesh's Bureau, and for the same reason: the
alternative is not a better source, it is no source. A capture is fetched raw
with the `id_` modifier, and the adapter refuses outright if one plays back as
HTML, because xlrd failing to open a toolbar would otherwise read as the
office publishing a broken file.

Two tables from Volume 2, *Populația stabilă — structura etnică și
confesională*:

* **`vol2_t1.xls`** — population by ethnicity per county, nineteen named
  peoples, one row per census year 1930–2011.
* **`vol2_t12.xls`** — population by religion per county, twenty named
  confessions.

Both publish people, so shares are computed and the counts kept beside them.
**2011 and not 2021 deliberately:** RPL 2021 asks the same questions but its
county tables exist only behind those unreachable hosts. Every record carries
the year.

#### Three faults the tables set, and how each was caught

**The repeated table, which is the one that nearly shipped.** `vol2_t12`
prints the whole county list three times — total, then urban, then rural —
with identical headings and nothing in column zero to say which pass you are
in. Reading the last occurrence published each county's **rural** population
as the county. Nothing about the output looked wrong: every composition summed
to 100%, named the right confessions, and sat in a believable range. Only the
head count disagreed — Harghita's religion came to 178,447 people against a
census county of 310,867, Cluj to 232,738 against 691,106.

The first block is the total one, and `check_totals()` now makes the mistake
unshippable: **every composition must add up to the unit's own printed
population**, which is the one thing a wrong block cannot fake.

**The footnote marker.** The ethnicity table writes `ILFOV ⁴` and
`MUNICIPIUL BUCUREȘTI ⁴` — Ilfov was carved back out of Bucharest in 1997 and
that table spans rounds on both sides of it — while the religion table, which
covers one round, has no footnote to hang. One read 42 counties and the other
40 until the marker came off.

**Bucharest's dashes.** The religion table lists Bucharest among the counties
and fills its trailing block with dashes end to end. A dash elsewhere in this
volume is a stated zero, so they were read as zeros and produced a composition
of nobody. Bucharest turned out to be the *only* county unaffected by the
repeated-table fault, for the same reason it looked broken: a city has no
rural block, so the placeholder was skipped and its total survived.

#### What validates it

Two independent checks, neither from the source being read. The English
Wikipedia's "Hungarians in Romania" transcribes county figures from a separate
route, and it agrees **to the person**: Harghita 257,707 Hungarians, Covasna
150,468. And every county's groups now add to its published 2011 population —
Cluj 691,106, Timiș 683,540, Bucharest 1,883,425 — with the only differences
being the handful of people in cells the office suppressed for disclosure
control, which are dropped rather than read as zero.

`Unitarian` joins the religion tree for Transylvania's Hungarian Unitarian
Church, which the census counts apart from the Reformed. Chasing a failing
test also found a pre-existing fault: the Protestant patterns match the bare
word "Church", so **Armenian Apostolic Church** was being filed under the
Reformation. It is Oriental Orthodox, and now matches under Orthodoxy.

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
| Malaysia (religion) | DOSM Kawasanku dashboard, `kawasanku_admin_barmeter.parquet` (storage.dosm.gov.my), built on MyCensus 2020 | state, district | Religion is a census question but OpenDOSM's catalogue has no religion table; the dashboard DOSM built on the 2020 census carries the six-category shares (Islam, Buddhism, Christianity, Hinduism, other religions, no religion) for the country, 16 states and 160 districts as unrounded percentages, and the state rows equal the census's published state table to the decimal. Counts are those shares applied to each area's 2020 population from the OpenDOSM series and rounded, and the note says so; the census's "unknown" answers are not separated from the last two categories. The country row is checked against DOSM's Key Findings figures (63.5 / 18.7 / 9.1 / 6.1 / 2.7) and states and districts, weighted, against their parent. Language: the census has never asked it (policy entry `MYS`). `scripts/fetch_census/malaysia_religion.py`. |
| Brunei | DEPS, Population and Housing Census (BPP) 2021, annex tables A3 (race by district), A4 (religion by district) and C1 (population by mukim), read from the department's own annex workbook `wp-content/uploads/2025/11/EXCEL-TABLE-A-C.xlsx` | district, mukim | Race and religion for all 4 districts, 440,715 people, checked against the figures the census report prints in prose and reconciling to the person at every level. "Malay" is the state's administrative group, defined by the report as covering Brunei, Tutong, Belait, Kedayan, Dusun, Bisaya and Murut, whose shares are published for the country only; the religion residual pools other faiths, unstated answers and no religious belief, so it is carried as "Other, none, or not stated". All 38 mukims carry the census head count and a gap naming the three annexes that put no composition below the district; Gadong is the sum of the census's Gadong A and Gadong B, which the boundary file draws as one, and Bokok carries the file's spelling Bunkok as an alias. Language is asked (question E27, the language mainly spoken at home) and never tabulated, so it is `not_available` with that reason rather than `not_collected`. `scripts/fetch_census/brunei.py`. |
| Kenya | KNBS 2019 Census Volume IV, Table 2.30 (openAFRICA mirror) | county | Religion for all 47 counties, replacing the Afrobarometer survey rows; ethnicity stays Afrobarometer's. KNBS's own site fails TLS verification (incomplete chain) and this project does not turn verification off. |
| Thailand | NSO 2000 Population and Housing Census, provincial final reports (`web.nso.go.th/pop2000/finalrep/`), transcribed in the Wikipedia article *Nationality, religion, and language data for the provinces of Thailand* | province | Buddhist, Muslim and Christian shares for 2000 as printed, read through the MediaWiki API because the NSO's own hosts refuse this client; the rest of 100% is one 'Other or not stated' group; an N/A is absent, not zero. 76 of 77 provinces: Bueng Kan was carved out of Nong Khai in 2011 and has no 2000 row. Nationality is citizenship and is not read as ethnicity; the 'linguistic minorities' cells name a few languages and not the rest, so language stays a gap. `scripts/fetch_census/thailand.py`. |
| Thailand (ethnicity) | NSO 2000 Population and Housing Census, language spoken at home, the 'linguistic minorities' cell of the same provincial reports and the same Wikipedia transcription; Suwilai Premsrirat et al., *Ethnolinguistic Maps of Thailand* (Mahidol University Institute of Language and Culture, 2004) for the regional Tai groups and the national figures, as transcribed in *Demographics of Thailand* | province | By the map owner's decision of 19 September 2026, and every province a `modelled` estimate, never a list: the census's minorities as printed under its own category names, everyone else assigned to the region's Tai group (Central Thai, Isan (Lao), Northern Thai, Southern Thai). The run prints the national composition the provinces imply beside the maps' figures; no backtest is possible. 76 of 77 provinces, Bueng Kan having no 2000 row. See "Thailand: ethnicity from secondary sources, by the owner's decision". `scripts/fetch_census/thailand_ethnicity.py`. |
| Kazakhstan | Bureau of National Statistics, 2021 National Population Census, religious affiliation by region, transcribed in the Wikipedia article *Religion in Kazakhstan* | region | The percent columns are read (one count in the article is mistyped; its percent is not). The article lists 16 regions and omits Shymkent (a city of republican significance since 2018); the boundary file draws the 2017 layout in which Shymkent sits inside South Kazakhstan Region, so the article's Turkistan Region is deliberately not matched to that shape and South Kazakhstan stays a visible gap: 15/16. `scripts/fetch_census/wiki_census.py`. |
| Kazakhstan (ethnicity) | Bureau of National Statistics, *Population by ethnic groups of the Republic of Kazakhstan at the start of 2025* (series 18, 27 March 2025), workbook committed under `data/raw/kazakhstan/` because the Bureau's site offers no file link | region, district | Register-based population at 1 January 2025 carried forward from the 2021 census, 73 ethnic rows, and the record says it is not a census count. The workbook's 20 regions are summed into the 16 shapes of the 2017 layout (Abai into East Kazakhstan, Jetisu into Almaty Region, Ulytau into Karaganda, Shymkent into South Kazakhstan), exact because these are counts, and every column is checked against its own total. Districts keep the Bureau's Cyrillic name with a transliteration as alias; `RENAMED` declares the shapes the boundary file still draws under a superseded name (Zelenovskiy for Bäiterek, Tselinniy for Gabit Musrepov, and so on). Almaty and Shymkent get their city totals as their one second-level shape; Astana has none. 173 of 174 district shapes filled; the boundary file draws Jambyl's Zhualy district twice and the second copy stays empty. `scripts/fetch_census/kazakhstan.py`. |
| Cambodia | NIS General Population Census of Cambodia 2019, religion by province, transcribed in the Wikipedia article *Religion in Cambodia* (2008 and 2019 columns; 2019 read) | province | Buddhism, Islam, Christianity, Others as printed; 25/25 with four spellings declared as aliases (Bantey Meanchey, Kratie, Takeo, Tbong Khmum). `scripts/fetch_census/wiki_census.py`. |
| Angola | INE Angola, Recenseamento Geral da População e Habitação 2024, *Relatório dos Resultados Definitivos*, Quadro 6.1 (grupos étnicos ou tribos), Quadro 6.2 (língua materna) and Quadro 7.1 (religião ou espiritualidade) | province | Counts of the population aged 2 and over for all three fields, replacing the Afrobarometer survey rows on 13 provinces and filling the five the survey did not reach: 18/18. The report is a PDF whose tables wrap over two pages and print thousands with spaces, so the reader takes each word with its x-coordinates from pdfplumber, joins digit groups closer than 4.5 pt into one figure, refuses a row that does not carry exactly the expected number of figures, and checks every province's groups against its own total. The column order was fixed from the header words' positions, not their reading order (on 7.1 *Bom Deus* is the second column, *Universal do reino de Deus* the seventh; on 7.1's second page *Testemunha de Jeová* precedes *Metodista*). The report's 21 provinces are summed into the 18 shapes of the 2011 layout: Cuando and Cubango into Cuando Cubango, Icolo e Bengo into Luanda, Moxico Leste into Moxico. Religion keeps the report's fourteen denominations apart as printed. `scripts/fetch_census/angola.py`. |
| Mali (RGPH5) | INSTAT, 5ème Recensement Général de la Population et de l'Habitat 2022, rapport thématique *Caractéristiques culturelles de la population*: Tableau 2.03 (religion by region), annex Tableau 5 (ethnie by region), annex Tableau 6 (langue maternelle by region) | region | Replaces the Afrobarometer survey rows for religion and ethnicity and the 2009 census for mother tongue: 9/9. The report tabulates the 2023 layout of 19 regions and Bamako; the boundary file draws the 2012 layout of 8 and Bamako, and each new region was carved whole from one old one, so the shapes are sums, taken on counts rebuilt as a percent of each region's printed population. The annex pages are stored upside down and pdfplumber reads every cell mirrored with wrapped cells in fragments, so cells are read from the ruling lines, each token turned back round, and labels recognised by the letters they are made of. Checks: each region's shares sum to 100, the regions' populations sum to the printed total, and the national row rebuilt from the regions agrees with the printed one (to 0.02 on Tableau 5; Tableau 6's printed Bambara and Tamasheq differ from its own regions by 0.12 and 0.14, the report's arithmetic). Ethnicity is of the Malian population (21.20 million of 21.35 million residents); mother tongue of the 19.14 million the table covers, whose age floor the report does not state on the page. `scripts/fetch_census/mali.py`. |
| Peru | INEI, Censos Nacionales 2017, *Perú: Perfil Sociodemográfico* (Lib1539): Cuadro 2.64 (lengua materna aprendida en la niñez by department), Cuadros 2.78 to 2.81 (population professing the Catholic faith, the Evangelical faith, another religion, none, by department) | department | Fills a country that had nothing: 26/26 (24 departments, Callao, and Lima as its two shapes, Provincia de Lima and Región Lima, with the book's whole-Lima row used as a check). Mother tongue is of the population aged 5 and over, religion of 12 and over. Figures are printed with spaces for thousands and two of the religion tables in a font pdfplumber reads letter by letter, so each row is read from word positions: tokens closer than 4.5 pt are one cell, and a department is recognised by the letters of its name. Checks: every printed share against its count and total, the four religion tables agreeing on each department's total and summing to it, the two halves of the language table summing to the total. Ethnic self-perception is printed by department only as four graphics and is not read. `scripts/fetch_census/peru.py`. |
| Zimbabwe | ZIMSTAT, 2022 Population and Housing Census Report: Table 2.14(c) (religion by province, both sexes) and Table 2.17 (mother tongue by province) | province | Replaces the Afrobarometer survey rows for religion on all 10 provinces and adds mother tongue; ethnicity stays the survey's, since the report prints it for the country only (Table 2.15). Comma-thousand counts read as text; each religion row sums to its printed total, each language row sums across provinces to its printed total, and each province's languages sum to the printed province total. The mother-tongue table covers 13,913,253 of 15,178,957 residents and the page does not state its age floor. `scripts/fetch_census/zimbabwe.py`. |
| Burkina Faso | INSD, 5e RGPH 2019, *Volume des tableaux statistiques*, Tableau I.22 (population résidente par région selon la religion, en %, with each region's population) | region | Replaces the Afrobarometer survey rows for religion on all 13 regions. Shares to one decimal applied to the region's printed population; the thirteen populations must equal the printed national 18,171,751 and the national shares rebuilt from the regions must agree with the printed ones. The volume prints the principal language spoken by milieu only and no ethnicity, so those fields are untouched. `scripts/fetch_census/burkina.py`. |
| South Korea | Hankook Research, *2025 Religion Perception Survey* (Weekly Report No. 358-3, 3 December 2025), page 8: religion by residence region, the religion question pooled from the 22 waves of the biweekly "Yeoron sok-ui Yeoron" web panel, January to November 2025 (23,000 adults aged 18 and over, weighted by region, sex and age) | province | A survey, not a census, and the map's one stated exception to the rule that a figure coarser than the shape is not spread: the report's seven residence regions cover the seventeen provinces, and each province carries its region's figure by the map owner's decision, with the note naming the region and how many provinces share it. Whole percentages, 2025 column; "other religions" is the printed "has a religion" less Protestant, Catholic and Buddhist. Lowest authority for Korea: the 2015 census (KOSIS, keyed API) replaces it when read. `scripts/fetch_census/korea_survey.py`. |
| Japan | 2020 Population Census, 人口等基本集計, population by nationality (e-Stat `0003445244`); NHK/ISSP 2018 "Religion" survey (放送研究と調査, April 2019) as a national prior; Agency for Cultural Affairs 宗教統計調査 believers by prefecture (e-Stat `0003282963`, 2025年度) as a relative signal | prefecture | By the map owner's decision of 19 September 2026, and labelled throughout. Ethnicity is **nationality** (`ethnicity_basis: "nationality"`): a census count of passports, with Japanese nationals of every ancestry in one row. Religion and language are `modelled` estimates, never lists: religion is the survey's national shares tilted by each prefecture's adherent pattern, capped and with no backtest; language is each nationality assigned its majority home language. See "Japan, resolved by the owner's decision". `scripts/fetch_census/japan.py`. |
| Czechia | ČSÚ SLDB 2021 open data (`sldb2021_narodnost.csv`, `sldb2021_vira.csv`, `sldb2021_jazyk1.csv`) | kraj, okres | Nationality is voluntary and allows two answers; the file counts every declaration and has no not-stated row, so it is carried as multi-response. Religious belief partitions the population across 78 rows, registered churches and write-in beliefs alike; a written "catholic" is kept apart from the Roman Catholic Church's count and a written "atheism" counts with no religious belief. Mother tongue is read from the single-mother-tongue file, and people with two mother tongues or a language outside its thirteen are the total less its rows, kept as one labelled bar. Okresy are named in Czech where geoBoundaries has English (Praha-východ / Prague-East), carried as aliases; the okres-to-kraj table is in the adapter because the rows do not carry it. |
| Croatia | DZS Popis 2021 final results, workbook `popis_2021-stanovnistvo_po_gradovima_opcinama.xlsx` (sheets 1, 2, 4) | županija, grad/općina | One layout for all three tables: a bilingual header (Croatian over English) with a count and a percent column per category, read from the header rather than declared; county rows interleaved with their towns and municipalities; a dash is zero. Each table partitions the population, Other, Not declared and Unknown included, and a row that does not sum to its total stops the build. Counties are named as geoBoundaries names them in English, with the Croatian as an alias; units are composed as the bureau writes them, type first ("Grad Samobor", "Općina Bibinje"). The workbook lists the City of Zagreb by its 17 city districts, which are skipped, the city coming from its own county row. The boundary file's spellings (a dozen typos, Istria's bilingual names, two islands each drawn as one town) are declared as aliases; 545 shapes for 556 units, 543 matched. |
| Bosnia and Herzegovina | BHAS Popis 2013, Book 2 workbooks `K2_T2_B` (ethnicity), `K2_T5_B` (religion), `K2_T6_B` (mother tongue) under `popis.gov.ba/popis2013/doc/Knjiga2/BOS/` | entity, canton | One layout for all three: Level, Area (Bosnian over English), Sex, Total, then the categories; the Total row of each territory is read and matched by its Bosnian name. The two entities and Brčko District are published at both levels, since geoBoundaries draws Republika Srpska and Brčko as their own second-level shapes beside the ten cantons: 3/3 and 12/12. The bureau's 'Islamska' and 'Muslimanska' religion columns are summed into Islam (both are Islam; the build refuses a group beside its parent) and the note says so; ethnonyms given as a religion, and 'Orthodox' given as an ethnicity, are kept and marked. A row that does not sum to its Total refuses. Republika Srpska's institute published a different reading of the same count; these are the Agency's figures. `scripts/fetch_census/bosnia.py`. |
| Switzerland | FSO structural survey 2024, main languages | canton | Main languages for all 26 cantons. A person may name up to three, so shares exceed 100%. |
| Singapore | Census 2020 + GHS 2015 planning-area tables | planning area, planning region | Ethnicity, religion and language for the planning areas, on three different bases; the five regions summed from their areas' published rows, each note naming what the release left out. All 55 shapes carry a record: the 14 with no breakdown say how few people the survey counted there, or that it counted none. |
| Singapore | SingStat Table Builder M810771 | planning region | Resident population, sex ratio and a derived median age for the 5 regions. Religion, ethnicity and language are not published in this series; the planning-area adapter supplies them. |
| Finland | Statistics Finland table `11rl` (PxWeb) | region | Mother tongue for all 19 regions, from the population register at 31 December. One language is recorded per resident, so shares are of everyone rather than of the people who answered a question. |
| Estonia | Statistics Estonia table `RV0222U` (PxWeb) | county | Ethnic nationality for all 15 counties, from the population register on 1 January — a register count, not a census answer. |
| Latvia | Central Statistical Bureau table `IRE031` (PxWeb) | municipality, state city | Ethnicity for all 42 municipalities and state cities, from the population register. "Other ethnicities" also holds people who selected none and people who did not indicate one, so it is not a count of anyone in particular. |
| Sri Lanka | Census of Population and Housing 2024, tables A1–A3 | province, district | Population, sex ratio, religion and ethnicity for all 25 districts and 9 provinces. |
| Mongolia | NSO, 2020 Population and Housing Census: the English national report's Appendix Table 3.6 (percentage distribution of population by ethnicity, and aimags and the capital) and the 22 aimag results books (“Хүн ам, орон сууцны 2020 оны улсын тооллогын НЭГДСЭН ДҮН”), chapter three, all read from the Internet Archive | aimag, soum | Ethnic group for all 22 aimags and religion for 18 of them; ethnic group for 204 of the 339 soums, the other 135 carrying the reason instead. The office's own database is gone -- opendata.1212.mn no longer resolves, web.nso.mn refuses the connection, www2.1212.mn's certificate has expired and answers plain HTTP with an empty body, and nso.mn and www.1212.mn are one Next.js application that names no API. Religion is a ten per cent sample of the population aged 15 and over and is labelled as such; “No religion” is an answer people gave, the census asking whether before asking which. The soum tables come in three shapes across the 22 books and each is told by its own arithmetic; every one is checked group by group against Appendix Table 3.6, and Khovd's is refused because it makes the aimag 39.5% Khalkh where the report has 29.8%. Language is `not_collected` (policy entry `MNG`): the 2020 individual questionnaire runs to question 29, “Do you have a religion?”, and asks about no language. `scripts/fetch_census/mongolia.py`. |
| Timor-Leste | INETL, Census 2015 Volume 2 priority tables 12 (mother tongue by municipality) and 11 (religion by municipality); Census 2022 Main Report basic table 4.01 (population by municipality, administrative post and suco) | municipality, administrative post | Mother tongue and religion for all 13 municipalities, stamped 2015 because the 2022 round asked both questions (E57 and E58 of its questionnaire) and has published neither below the country. The 2015 tables are a partition — 38 tongues, one per person, adding to each municipality's own total to the person — and their national column is exactly the fifteen-entry language list the map's country row already carried. Both tables count 1,179,654 people, 3,989 below the volume's own total population and 1,314 above its private-household population, unexplained by any footnote. Population is 2022, with Atauro (a municipality of its own since 2022, an administrative post of Dili before) summed back into Dili, which is the division the boundary file draws. The 67 administrative posts carry population and a stated gap for each composition; no table in either round goes below the municipality and INETL's REDATAM dashboard, served from a bare address, timed out. Ethnicity is `not_collected` (policy entry `TLS`): the 2022 questionnaire runs E1 to E77 without asking it. `scripts/fetch_census/timor.py`. |
| Lao PDR | Lao Statistics Bureau, 4th Population and Housing Census 2015, village indicator table (`lao-population-census-2015.xlsx`, 8,499 villages x 75 columns) released through Open Development Laos; category definitions from Table 1 of the *Socio-Economic Atlas of the Lao PDR 2015* (LSB with CDE Bern); national controls from the census's own English results volume on UNFPA Laos | province, district | Ethnicity and religion for all 18 provinces and all 148 districts, where the results volume publishes both for the country only — its Tables 3.4, 3.5, P2.7 and P2.9 are national and none of its thirty province tables crosses either field. Each village's published percentage is turned back into people by its own published population and summed; shares are recomputed against the unit and re-rounded to add to 100. Ethnicity is the census's ten **ethno-linguistic categories**, not its 49 groups, and the Atlas's "Lao" is not the census's Lao: it puts the Lao of Huaphanh, Xiengkhuang, Borikhamxay, Vientiane province and Hinboun in "Tai-Thay", so the villages give Lao 43.7% and Tai-Thay 18.3% where Table 3.4 prints Lao 53.2% — together the volume's Lao-Tai family, 62.4%, which is where the check is made. Religion has five categories and a residual of 33.3%: the census counts a religion only where it has written doctrines, so the animist beliefs of most non-Lao-Tai people sit in "No religion or not stated" beside the 1.8% who stated nothing, and both residuals are marked so neither can lead a unit. The 8,499 villages weigh 6,481,625 people, 0.16% under the published 6,492,228; sex ratio 995.7 females per 1,000 males against 994.7. The two Vientianes are settled by an explicit table and carry no aliases; seven district names romanise differently in the two files and are declared. Language is `not_collected` (policy entry `LAO`): 282 pages with no language table and no occurrence of "mother tongue". `scripts/fetch_census/laos.py`. |
| North Korea | Central Bureau of Statistics, DPR Korea, *2008 Population Census — National Report* (Pyongyang, 2009), Table 2 (population by sex and urban/rural, by city/district/county and province), read from the UN Statistics Division's copy | province, county | **Population and sex ratio only, and a documented declaration for the other three.** All 11 first-level units and all 179 counties carried nothing at all before this; Table 2 counts every one of them. The report's geography is October 2008 and the boundary file's is after the 2010 changes, so four differences are settled by summing the report's own rows over the units the file draws, never by splitting one: Nampo is the six South Phyongan rows the file puts inside it (983,660) and South Pyongan its printed total less them; Kangnam, Junghwa and Sangwon move from Pyongyang to North Hwanghae; Chongjin City is the seven districts the report itself marks as its parts and Hamhung City the six it marks plus Hungnam; the Pyongyang shape is the city's remaining eighteen districts, Unjong and Kangdong being drawn separately. Each of the ten first-level areas equals its own county rows, the eleven shapes equal 23,349,859, and that is Table 2's own DPR Korea row — 702,372 below Table 1's 24,052,231, the difference being 662,349 men and 40,023 women living in military camps, whom no table of the report places in a province, so every sex ratio here runs above the census's own. Eight county names and both Phyongans are written differently in the two files and are declared, among them a Cholwon in North Phyongan where the county is Cholsan and a second Ryongchon in South Hwanghae where it is Ryongyon — the report's own slips, settled by the two lists closing with every other name in the province matching outright, and corrected nowhere. Religion, ethnicity and language are `not_collected` (policy entry `PRK`): the questionnaire's 53 questions ask none of them, and its one question about who a person is asks nationality. The adapter does not copy that declaration into its 190 rows — it marks the three `not_available` with a line saying the census asks none of them, which is the one form `apply_collection_policy` replaces, so sharpening the policy sharpens every unit at once. `scripts/fetch_census/northkorea.py`. |
| Mexico | INEGI Censo de Población y Vivienda 2020, ITER | state, municipality | Religion, indigenous-language speaking and Afro-descendant identification for 2,453 of 2,457 municipios. All from the *cuestionario básico*, so these are counts, not sample estimates. |
| New Zealand | Stats NZ 2023 Census via Aotearoa Data Explorer (SDMX) | region, territorial authority | Ethnicity, languages spoken and religious affiliation for all 88 territorial authorities and Auckland local boards. All three are multi-response, so shares are of people who named a group, not slices of a whole. Needs an API key. |
| Nepal | NPHC 2021, National Report on caste/ethnicity, Language and Religion | province, district | All three fields from one census: 142 castes/ethnicities, 124 mother tongues, 10 religions. All 7 provinces and 66 of 77 districts. The census measured all 77; the boundary file is what fails, drawing 75 shapes whose names do not all sit on the right ground, and the 9 shapes that therefore carry nothing each say so and name the province total that holds their people. |
| India | Census 2011 tables C-01, C-01 Appendix, C-16 | state, district | No public API — per-state workbooks from the censusindia.gov.in NADA catalogue. 2011 is the latest round; the next census was postponed. The Appendix names the religions inside "Other religions and persuasions" (Donyi-Polo, Sarna, Sanamahi …) for states only. 734 of 735 district shapes carry figures. 637 are the census's own rows; 97 are shapes the census never enumerated and which carry their predecessor's shares as a stated estimate, with no head count, so nobody is counted twice. 75 more are districts that have since lost territory, and keep their 2011 figure under a caveat saying how much ground they have left. The one shape without figures is not a district at all. Telangana and Ladakh have state figures summed from the ten and two districts the census did enumerate, and Andhra Pradesh and Jammu and Kashmir carry the residual rather than the undivided state. |
| Papua New Guinea | NSO, *2024 National Population Census -- Final Figures* (Table 1 and the 22 Provincial Snapshots) for population and sex ratio; *Papua New Guinea 2011 National Report* (2011 census), Summary Indicators row "Main religion (% of population)" | province, district | Fills a country that carried nothing at all: 22 provinces and 71 of 87 district shapes. Religion is **one group per province** -- the largest denomination and its share of the citizen population (19.7% to 68.4%, sixteen provinces under half), which is the only provincial religion figure published anywhere: Appendix 4 of the report prices the provincial tables at K40 a set and K2,000 a CD-ROM and the office publishes none of them, and a second search of the DHS API and report, the 2022 SDES, the 2000 census, the Archive's copy of the old PRISM site and Wikipedia found religion for the country and never for a province. Every panel says "describes N% of the population", and the run refuses if any province's single denomination ever reached the 95% at which it would stop saying so. Ethnicity and language are `not_collected` (policy entry `PNG`): the 2011 report's Appendix 1 lists the 33 questions of the one-page form and neither is among them, and the one language item is a literacy rate in English, Pidgin, Motu and Tokples. Both PDFs print their figures in kerned groups ("41 2 ,15 8" for 412,158), so a row is cut where males plus females make the total and the printed sex ratio holds. The 2024 layout has one district more than the boundary file draws in Western, Northern, Morobe and West New Britain and the booklet does not say which district it came out of, so those four provinces' 16 shapes carry the reason rather than a count. `scripts/fetch_census/png.py`. |
| Bhutan | National Statistics Bureau, 2017 Population & Housing Census of Bhutan (PHCB), Table 2.1 — population distribution by gewog and town — in each of the twenty *Dzongkhag Series* volumes, with the *National Report* (288 pp, ISBN 978-99936-28-50-7) as the control. Indexed at `www.nsb.gov.bt/phcb`, which links the national report and the twenty volumes; the volumes are fetched as `nsb.gov.bt/wp-content/uploads/2026/08/PHCB2017_{Dzongkhag}.pdf`. Licence: none stated — NSB official publications, cited as such. | dzongkhag, gewog | **Population and sex ratio only**, for all 20 dzongkhags and 205 gewogs, each volume's own Table 2.1. Religion, language and ethnicity are `not_collected`, measured over the round's whole 1,798 pages rather than assumed — see below. The census's one identity-adjacent split is **citizenship** (Bhutanese against non-Bhutanese, published to gewog) and it is deliberately not read as ethnicity. Sex ratio is derived as females per 1,000 males from the Male and Female columns of the same row, and only where those two reach the Total printed beside them; a row that does not add up keeps its head count and publishes a gap naming the three figures. The publications disagree on the head count and the disagreement is reported rather than resolved: the twenty volumes come to **720,837**, the national report analyses **727,145**, and it says **735,553** were found in the country, the difference being 8,408 non-Bhutanese and tourists in hotels on census night about whom nothing else was collected. Each volume reconciles to its own printed total, gewog by gewog, so the dzongkhag's own figure is the one carried. Towns and thromdes are enumerated *beside* the gewogs, not inside them, and geoBoundaries draws none of them, so the gewog layer is short of its parent by the urban population — 37.8% of Bhutan — and every gewog record says so. **Thirty gewogs are drawn under a different name, not a different spelling** — Samtse's Tashicholing as "Sipsu", its Norgaygang as "Bara", Sarpang's Samtenling as "Bhur": the Nepali-origin names southern Bhutan carried before the renamings. They are paired by Wikidata's reference point for the gewog the census names falling inside the polygon the boundary file draws, with Wikidata's dzongkhag agreeing with the census's — a method measured first (98 of the 102 gewogs already matched by name have their own point inside their own polygon) and corroborated against the published list of all 205 gewogs with their Dzongkha. Six with no point are taken by elimination inside a dzongkhag where nothing else is left; four whose names repeat across dzongkhags (two Gakilings, two Norboogangs) are bound to a polygon by its id. Two earlier name pairings were wrong and are removed: Punakha's Barp was wearing a polygon 96% inside Samtse, Chhukha's Maedtabkha one 60% inside Tsirang, and those two polygons are Samtse's Norgaygang and Tsirang's Sergithang, which had no figures at all. 205 of 205 gewog shapes now carry the census's. `scripts/fetch_census/bhutan.py`. |

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

**And the reader is told.** For a long time this table existed only here and in
an `UNJOINABLE` dict in the adapter, so the nine affected shapes rendered blank
with nothing on them — which reads as an adapter nobody ran, a different claim
from "the census measured this and the boundary file cannot take it".
`SHAPE_GAPS` in `build_entities.py` now carries a sentence onto each of those
shapes naming whose ground the polygon actually is and which province total
holds those people. It sits beside `ADAPTER_GAPS` and answers a different
question: `ADAPTER_GAPS` says a country has no adapter, `SHAPE_GAPS` says the
adapter ran and this one polygon still cannot be given what it found.

It is keyed by the boundary file's own spelling rather than the district's
name, which is what reaches *both* polygons called `Bara`. That is the point:
an ambiguous name is exactly what makes a data join unsafe, and exactly what
makes keying the reason that way safe, because the reason is true of both.

`check_shape_gaps` holds the table to its promise in both directions on every
build: an entry naming a shape nobody draws is stale and the boundary file has
moved on, and an entry whose shape ended up carrying a composition means
figures are landing somewhere this table says they must not. Either stops the
build rather than being written out.

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

### Singapore's planning areas: the census, read from data.gov.sg

The Department of Statistics publishes the census's planning-area tables on
**data.gov.sg**, whose datastore serves them as rows to anyone. Its own site,
`singstat.gov.sg`, answers the runner 403, and the Table Builder API that
`singstat.py` uses carries nothing below the five planning regions (its
catalogue was searched from here three ways: only the annual M810771 series
answers to "planning region"). `--fetch` reads each table into a CSV in
`data/raw/singapore/` and the adapter reads the CSVs, so a build without
network still runs and what was served is committed beside the code that read
it.

| Field | Source | Base | Total | Areas |
|---|---|---|---:|---:|
| Ethnicity | Census 2020, by planning area and subzone | all residents | 4,044,210 | 55 |
| Religion | Census 2020 | residents aged 15 and over | 3,459,093 | 30 |
| Language | Census 2020 | residents aged 5 and over | 3,596,284 | 30 |
| Religion | Census 2010 | residents aged 15 and over | 3,105,748 | 35 |
| Language | Census 2010 | residents aged 5 and over | 3,399,054 | 35 |

The three fields do **not** describe the same population, so each carries its
own note naming whose shares these are. Presenting them as one profile would
be wrong in three directions at once, and the totals make the difference
visible.

An earlier version of this adapter read ethnicity from the General Household
Survey 2015 (3,902,690 residents, 41 areas) because that was the extract to
hand. The census table replaces it: same geography, one census year across all
three fields, and a count for every area including the ones the survey
suppressed.

**`-` is not zero.** The census prints `-` for nil or negligible, and several
planning areas are industrial or military with under a hundred residents. An
area whose every group is `-` while its own total survives -- Boon Lay's 40
residents, Tengah's 10 -- has a count and a withheld breakdown, not forty
people of no race; it keeps its published population and its composition
becomes an explicit gap saying so. An area whose total is itself `-` carries no
figure at all and says that too.

**Five areas fall back to the 2010 census.** The 2020 religion and language
releases list 30 planning areas and bucket the rest into an "Others" row that
matches no shape on the map (25,756 residents aged 15 and over; 25,353 aged 5
and over). The 2010 census listed 35, so Changi, Mandai, Newton, Rochor and
Singapore River have a religion and a language row of their own a decade
earlier. Those are used, stamped `2010`, with the note saying which census and
why -- a decade-old count of a place is a count, where the newer release gives
nothing at all. The regions are summed from the 2020 rows only, so a region is
one census and no area is counted twice.

**The five regions are summed from their areas.** The map's own roll-up
(`roll_up_parents`) refused every region, and was right to: a sum over part of
a territory is refused on principle. What the roll-up cannot know is that the
missing shapes are empty. The adapter can: the URA's Master Plan says which
areas make each region (declared in `REGIONS`, and the boundary file's geometry
places the 55 shapes identically), and the area totals reconcile with each
table's national row, so an area with no published count holds nobody the
census counted. Each note names the areas the release left out and what they
hold. A national shortfall beyond the rounding tolerance is written into the
note in a sentence; beyond 1% the regions are refused, because then the areas
do not partition the country.

**Every one of the 55 shapes carries a record.** 42 have a census ethnic
composition; 35 have religion and language (30 from 2020, five from 2010). The
rest say why they are blank: a count too small for the Department to publish a
breakdown of, or no count anywhere, which is how it writes an area with nobody
living in it. No join failed: all 55 area names in the tables match the
boundary file's, which writes them in capitals.

Other routes, measured and closed: Wikipedia's planning-area articles carry no
demographic tables at all (six of seven probed have none; Bedok's only table
lists housing estates), and Kaggle has no planning-area composition -- six
searches return resale-flat prices, a 2015 population-by-dwelling table and
national ethnic-group series.

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
explicit `not_available` naming what is missing — filled, in the build, by the
planning-area adapter's region rows summed from the census tables (above).

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
are present, giving 734 of 735 districts. 637 of those are the census's own
rows. The other 97 are shapes the census never enumerated — **91** districts
created after 2011 and **6** successors of the three districts subdivided since
— and they carry their predecessor's 2011 shares as an estimate the note
declares before it says anything else. Shares only: the head count stays with
the row the census measured, so the 637 populations still sum to less than the
national total rather than more.

The **1** shape with no figures is not a district at all — geoBoundaries draws a
feature in Jammu and Kashmir named, literally, "DATA NOT AVAILABLE", which is
268 disjoint fragments totalling about 390 km², the slivers between the district
polygons. It carries an explicit reason on every field.

Every inherited and every empty shape says where its figures come from or why
there are none: the 91 name the year they were created and the 2011 district
they were carved from (`CREATED_AFTER_2011`, checked against the census's own
district list on every run), the 6 name the undivided district they are a
fragment of (`SUBDIVIDED_SINCE_2011`), and the 75 that lost territory without
losing their names keep their figure and name what was taken out of them and how
much ground they have left (`LOST_TERRITORY_SINCE_2011`, checked against
`CREATED_AFTER_2011`).
**Shares are carried down; counts never are.** A new district is a *part* of an
old one and the district that kept the name is another part, so a head count
put on either would be the same people counted twice. The proportions are a
different kind of claim: they survive being applied to a part, on the stated
assumption that a district resembles the ground it was cut out of. That
assumption is real, and weakest exactly where a district was carved out
*because* it differs — which is why every inherited composition opens with
"Estimated, not measured" rather than carrying it quietly.

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
  figure of their own. They carry their predecessor's shares instead, labelled
  as an estimate.
* Three 2011 districts have since been subdivided so thoroughly that their
  names survive on no shape at all (Jaintia Hills, Karbi Anglong, Warangal).
  Their **counts** are still not spread across the successors -- the census
  never measured those areas separately, and splitting a head count between
  them would put the same people on six shapes at once. Their **shares** are
  carried to all six, which is the treatment every other post-2011 district
  gets and which these are: the only thing that ever set them apart is that two
  of them kept the old district's name.
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
measured. It went on showing 3,776,269 people, 92.4% Hindu, sourced and dated,
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
Rangareddy kept 52% of its ground, and of the two districts taken out of it the
one that took least land took most people -- Medchal-Malkajgiri is 1,067 km² of
built-up Hyderabad fringe against Vikarabad's 3,621 km² of farmland. Upper
Subansiri kept 90% of its ground and what it lost is high Himalaya with almost
nobody in it. A threshold set anywhere between the two would be a guess wearing
a tolerance's clothes.

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

### "Many Indian districts have no population": which, why, and where the reason went

Counted rather than estimated, over the 735 CGAZ ADM2 shapes for IND:

| | shapes |
|---|---:|
| carry a 2011 head count | 637 |
| carry none | 98 |

None of the 98 is a join that failed. Every one of the 735 shapes is claimed by
an adapter row — 735 rows from `india_district.json` and 734 from
`india_language_district.json`, no row unmatched, no shape unclaimed — so there
is no alias to add and no binding to make. The 98 break down as:

| class | shapes | |
|---|---:|---|
| the source has the figure and the row never matched the shape | **0** | nothing to fix |
| the source genuinely has no figure | **97** | 91 districts created 2010–2020 out of a district the census *did* count, plus the 6 successors of the three districts subdivided since (Warangal ×2, Karbi Anglong ×2, Jaintia Hills ×2) |
| the adapter never read the table | **0** | both C-01 and C-16 are read at district level |
| not a district at all | **1** | `DATA NOT AVAILABLE`, geoBoundaries' 268-fragment sliver in Jammu and Kashmir |

So it is the honest case throughout, and `CREATED_AFTER_2011`,
`SUBDIVIDED_SINCE_2011` and `BOUNDARY_ARTEFACTS` already wrote a sentence for
every one of them saying which census never counted that ground.

**The reason was written and then thrown away at the last step.** The sentence
lived in the record — `population: {status, note}`, which is what
`common.py`'s `gap()` builds — and `tests/test_india.py` asserted on the built
file that no Indian district carries a gap without one. What had no test was
the panel. `Dashboard.factCard` rendered a gap as the words "Not yet
available" and dropped `note` on the floor, and rendered a value without
reading the record's `<field>_note` beside it. Across the whole build that was
**1,311 written reasons that never reached a reader**: 887 notes inside gap
values and 424 `population_note` / `sex_ratio_note` / `median_age_note`
sidecars. 354 of them are India's — the 98 blanks, and the 75 shrunken
districts whose head count is for more ground than the shape covers and whose
caption saying so was also dropped, which is the worse half of the same bug.
The fact tiles now carry the note behind the same "i" the composition panels
use, and `tests/test_frontend.js` asserts it on both a gap and a value.

**Is there a newer official figure?** Asked rather than assumed, and the answer
is no at this geography:

* **Census.** 2011 remains the last complete count. The 2021 round was
  postponed; the Government notified the next in the Gazette on 16 June 2025,
  with reference dates of 1 October 2026 for the snow-bound areas of Ladakh,
  Jammu and Kashmir, Himachal Pradesh and Uttarakhand and **1 March 2027** for
  the rest of the country. Nothing from it is published.
* **Projections.** The one official series is *Population Projections for India
  and States 2011–2036* (Technical Group on Population Projections, National
  Commission on Population, July 2020), and its title is exact: India and the
  states. It contains no district table. The district-level projections that
  circulate — an IIPS report prepared for the health ministry, and academic
  products such as India Policy Insights — are derivations from that state
  series, not Registrar General output, and they are keyed to the NFHS survey
  frames (640 districts for NFHS-4, 707 for NFHS-5) rather than to the present
  set, so they would not reach the districts that are empty here.
* **Sample Registration System.** A sample survey, published for India and the
  major states; its own documentation states it cannot produce small-area
  statistics at district or sub-district level, and its sample supports
  breakdowns no finer than NSSO natural divisions, which are groups of
  districts.
* **Civil registration.** The CRS counts registered births and deaths. It is
  not a population count and cannot become one without a base to carry forward,
  which is the thing that is missing.

So the 97 stay gaps, and the fix owed them was the one made: to say so where a
reader is standing. The route that *would* fill them with a measurement rather
than a projection is the sub-district one described above — and note that the
raw material for half of it is already in this repository, since the C-16
workbooks under `data/raw/india/c16/` carry sub-district rows beside their
district rows (Punjab's, for instance, has 20 district rows and 77 sub-district
rows, with Pathankot and Dhar Kalan sitting under Gurdaspur as the tehsils that
became Pathankot district in 2011). It is still the other half — a published
concordance from 2011 sub-districts to present-day districts — that does not
exist, and hand-writing one is what this file declines to do.

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

> **This paragraph was one third wrong and stayed wrong for two rounds.**
> Islamabad's Table 9 is published, at `table_9_islamabad.pdf`, and was being
> asked for under a name the office does not use. It now reads, and so does
> the 2023 mother-tongue table this section's last paragraph leaves open. Azad
> Jammu and Kashmir's religion comes from its own government's yearbook.
> Gilgit-Baltistan is the only one of the three still empty. See *Pakistan's
> last three divisions* below, which measures all of it.
>
> **And none of the seven is empty now.** Both territories have a language as
> well, each from its own government and neither from the census -- Azad
> Kashmir from Table 15.33 of the same yearbook, Gilgit-Baltistan from Table
> SR.3.1 of its MICS 2024-25. See *The two territories' languages* below.

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

> **Superseded for Pakistan**, and kept because the level problem it found is
> general and still live for other countries. Pakistan's mother tongue now
> comes from the 2023 census direct -- see *The 2023 Table 11*, below -- and
> `PAKISTAN` is no longer one of `uscb.COUNTRIES`.

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

> Two of those three have since moved. Islamabad's Table 9 and Table 11 are
> both published and both now read; Azad Kashmir has religion from its own
> government. Mother tongue for Azad Kashmir and Gilgit-Baltistan is still
> exactly this: eleven blanks, and the section below says what was asked.

**Is 2017 the most current this can be?** No, and that is worth stating
plainly rather than leaving implied. PBS completed the 7th census in 2023 and
publishes its tables as per-province PDFs; `pakistan.py` already reads Table 9
(religion) from them. What is not established is whether the 2023 round
publishes a mother-tongue table in the same series, and under which number --
2017's was Table 11, and a table number is not a thing to guess at, because a
guessed URL that 404s and a table that was never published are the same
observation.

**It is Table 11, and it is published.** Asked on the runner, the office
answers 200 to `table_11_kp_districts.pdf` (3.4 MB),
`table_11_punjab_districts.pdf` (3.5 MB), `table_11_sindh_districts.pdf`
(3.2 MB), `table_11_balochistan_districts.pdf` (3.6 MB) and
`table_11_islamabad.pdf` (45,805 bytes) -- the same five areas and the same
naming scheme as Table 9, down to Islamabad dropping the word "districts". It
answers 404 to `table_11_ajk.pdf` and `table_11_gb.pdf`. So the 2023 round
does publish mother tongue by district, for 240 million of Pakistan's people,
and the figures on this map are 2017.

> **Since done.** See *The 2023 Table 11, and two districts whose largest
> group was a missing category*, below. The paragraphs that follow describe
> why it had not been, and the reasoning they set out is the reasoning that
> was followed: the 2023 table replaced the 2017 route, `PAKISTAN` left
> `uscb.py`, and Table 11 is read the way Table 9 is.

**Wiring it is not a matter of adding a file, which is why it has not been
done here.** `pakistan_district.json` and `pakistan_language.json` currently
share 114 district shapes without colliding, because neither publishes a field
the other does: one carries population and religion, the other language.
Putting 2023 mother tongue into the first would give both a real `language`
on one shape, and `conflicting()` in `build_entities.py` counts two real
values that differ as a conflict -- which would send Pakistan's language to a
gap on every district that currently has one. The 2023 table is a
*replacement* for the 2017 route, not an addition beside it: it means
retiring `PAKISTAN` from `uscb.py` and reading Table 11 the way Table 9 is
read, with the same reconciliations. That is a day's work with a real payoff
-- 2023 figures, and Islamabad's mother tongue from the census rather than
from a Census Bureau extraction -- and it is left measured rather than
half-done.

The other half of the old plan is answered too:
`scripts.fetch_census.uscb --inspect pakistan-subnational-population-and-housing-data-tables`
was the second route named here, to say whether the Census Bureau's workbook
had been reissued off the 2023 round. It does not need running to settle the
question the 2023 tables now answer directly.

### Pakistan: ethnicity, and the difference between two kinds of empty

All 145 Pakistani records — 7 provinces and 138 districts — carried a bare
`not_available` on ethnicity: a status with no reason, which on the map is an
empty panel that reads as "nobody ran the adapter". Worse, `not_available` is
a specific claim — *asked, and not published at this level* — and it was the
wrong one.

**Pakistan's census does not ask ethnicity.** Measured against the Bureau's
own publications rather than recalled:

* **The official table list.** *List of Statistical Tables of Population and
  Housing Census-2023 (Updated & Final)* runs Tables 1–26 and 31–34, under
  Basic / Literacy and Education / Economic Active Population / Disabled
  Population / Migration / Housing Census / Listing Information. All 26
  district files were fetched and their printed titles read. The only three
  tables about who a person is are **Table 9 religion, Table 10 nationality,
  Table 11 mother tongue.**
* **National Census Report 2023, §4.1.2** (p. 124) lists what the census
  collected: age, mother tongue, religion, disability, migration, literacy,
  employment and nationality. Eight characteristics; ethnicity is not one.
* **§4.4** (p. 138), repeated in the District Census Reports, is PBS ruling out
  its own nearest-looking variable in its own words: nationality *"can be
  called and understood as citizenship, or more generally as subject or
  belonging to a sovereign state, **and not as ethnicity**."*
* **"Scheduled Castes" is not the exception it looks like.** It is a category
  of the *religion* question in Table 9, counted apart from Hindu, not an
  enumeration of caste.

So the status is `not_collected`, and all 145 records now carry it with a
stated reason naming the report, the section and the table list.

**Mother tongue was not moved into the field.** A language is not an
ethnicity, and republishing Table 11 under the ethnicity heading would be the
mis-match this project ranks below a gap. The note instead points the reader
at the language field beside it and names that unit's leading tongue — Karachi
"Urdu leads at 50.7%", Khyber Pakhtunkhwa "Pushto leads at 81.0%" — with a
variant carrying no figure for units that have no language composition.

**One honest negative.** The three enumeration-form PDFs PBS publishes scored
zero for *every* term, religion and mother tongue included, which are
certainly on the form. They are scans with no text layer. Reading that silence
as "not asked" would have been the worst mistake available here; the claim
rests on the report and the table list instead.

#### The country row was contradicting the districts

`admin0.json` gave PAK a seven-group ethnicity composition — Punjabi 44.7,
Pashtun 15.4, Sindhi 14.1, Saraiki 8.4, Muhajirs 7.6, Baloch 3.6 — undated and
unsourced, while all 145 units beneath it said the question is never asked.

That vector is the Factbook's, and for Pakistan it is **the 1998 census's
mother-tongue shares with the labels swapped**: Pashto printed as Pashtun,
Urdu as Muhajir. The map already carries those figures correctly on the
language field, where the same country row gives Pashto 18.2% beside the
ethnicity row's Pashtun 15.4% — two numbers for one question asked once.

PAK is therefore declared in `NOT_COLLECTED_POLICY`, which `fetch_factbook`
consults *before* it parses anything, so the declaration is the answer for
that field and the measured figures keep the field they belong to.

#### Gilgit-Baltistan and Azad Jammu & Kashmir, checked while here

AJ&K carries a language composition on both its rows (Pahari-Pothwari 68.8,
Gojri 18.6, Kashmiri 4.6, Punjabi 3.6); GB's territory row carries one (Shina
48.1, Balti 29.2, Burushaski 12.3, Khowar 5.2). **GB's 10 districts remain a
stated gap**, and the search behind it is exhausted rather than untried: no
Table 11 under any filename, no language table in *GB At a Glance 2025*, and
GB-MICS 2024-25 publishes language of household head and district as two
uncrossed distributions. A district-level GB language figure is a separate
investigation, not a loose end.

### Pakistan's last three divisions: a filename, a yearbook, and one real absence

Seven first-level units, four of them full since the 2023 census landed and
three of them blank. The three were blank for three different reasons, and
the file said they were blank for one.

**Everything below was measured on the runner.** Each line is a URL asked for
and what the host answered; nothing here is inferred from a search result.

| asked | answered |
| --- | --- |
| `…/census_tables/tables/table_9_islamabad.pdf` | **200**, application/pdf, 36,012 bytes |
| `…/census_tables/tables/table_9_islamabad_districts.pdf` | 404 |
| `…/census_tables/tables/table_9_ict_districts.pdf` | 404 |
| `…/census_tables/tables/table_11_islamabad.pdf` | **200**, 45,805 bytes |
| `…/census_tables/tables/table_11_{kp,punjab,sindh,balochistan}_districts.pdf` | **200**, 3.2–3.6 MB each |
| `…/census_tables/tables/table_9_{ajk,gb}.pdf` | 404 |
| `…/census_tables/tables/table_9_{ajk,gb}_districts.pdf` | 404 |
| `…/census_tables/tables/table_9_{gilgit_baltistan,azad_jammu_kashmir}.pdf` | 404 |
| `…/census_tables/tables/table_11_{ajk,gb}.pdf` | 404 |
| `…/population/2023/tables/table_9_{islamabad,punjab,ajk,gb,kp}.xlsx` | 404, all five |
| `www.pbs.gov.pk/census-2023-tables` | **404**, three times |
| `www.pbs.gov.pk/census-2023`, `/census_tables`, `/digital-census/detailed-results` | 404 |
| `www.pbs.gov.pk/…/National-Census-Report-2023.pdf` | 200, 12.1 MB |
| `www.pbs.gov.pk/…/District-Census-Report-2023-Islamabad.pdf` | 200, 4.7 MB |
| `www.pbos.gov.pk/page/population-census` | **TLS: certificate has expired** |
| `census23.pbos.gov.pk/` | timed out at 40s |
| `pndajk.gov.pk/…/AJ&K Statistical Year Book 2023(1).pdf` | **200**, and carries the religion table below |
| `www.pndajk.gov.pk/…/Statistical Year Book 2020.pdf` | 200, no mother-tongue table |
| `www.pndajk.gov.pk/…/AJK At a Glance 2025.pdf` | 200, 4.9 MB, no religion and no mother tongue |
| `www.pnd.gog.pk/pages/downloads` | 200, eight PDFs, listed below |
| `en.wikipedia.org` "Gilgit-Baltistan" via the MediaWiki API | 200, two wikitables, neither a composition |
| `alfgb.gbit.gov.pk/storage/downloads/…` | TLS: `TLSV1_ALERT_INTERNAL_ERROR` |

**`www.pbs.gov.pk` did not block anything.** It answered a plain
`DemographicMap/1.0` client on every request above, 404 where the file is not
there and 200 where it is. The two hosts that are closed are closed by their
certificates -- `www.pbos.gov.pk` serves an expired one and `alfgb.gbit.gov.pk`
fails the handshake outright -- and neither is a thing to work around. An
expired certificate is not an incomplete chain: the AIA `caIssuers` trick that
`india_census.py` uses completes a chain the server forgot to send, and there
is nothing to complete here.

#### Islamabad was behind a filename

`table_9_islamabad.pdf`. The four provinces are `table_9_<slug>_districts.pdf`,
this module read "districts" as part of the scheme, and the office drops the
word for the capital, which has no districts under it, being one. Both names
this module tried came back 404 -- and a 404 from a name the office does not
use looks exactly like a 404 from a table that was never written. Islamabad
spent two census rounds filed under "enumerated apart, not published", which
was true of the other two and never of it.

The file is one page and prints one district, `ISLAMABAD DISTRICT`, followed
by `ISLAMABAD TEHSIL` repeating the same figures. So it has no territory row
above its districts, and the territory row is the Malakand check -- the one
control that catches a unit the reader never noticed, worth 825,377 people in
Khyber Pakhtunkhwa. `ONE_DISTRICT` in `pakistan.py` names the province where
that row is redundant rather than letting a missing row pass anywhere it turns
up, and the declaration pays for the check it removes: exactly one district
must be read, or the province is refused.

Islamabad now carries **2,283,244 people, Muslim 95.6%, Christian 4.3%,
Ahmadi 0.1%, Hindu 0.0%** -- the largest Christian share of any first-level
unit in Pakistan, against Punjab's 1.9% and Khyber Pakhtunkhwa's 0.3%, and
2.9% of the country's Christians in 0.9% of its people. Its row also breaks three figures across two words each (45, 60 and
10) and sets the tightest column gap either province offered, **12 points**
between `,283,244` and the `2` of `2,181,663`, against the 13 this file
records as the minimum. `GAP` is 4, so the margin is 4 against 12; a rule
tuned any closer to the gap it had seen would have joined two columns here.

#### Azad Jammu and Kashmir: religion from its own government

The Bureau publishes no Table 9 for it. Its own does. The **AJ&K Statistical
Year Book 2023**, from the Bureau of Statistics, P&DD, Azad Government of the
State of Jammu & Kashmir, reprints two religion tables from the **2017**
census: 15.23 for the territory rural and urban, and **15.24 by district**.
That is a Pakistan Bureau of Statistics table reprinted by the territory's
government, which is the same standard `wiki_census.py` holds a Wikipedia
transcription to, met by a government publication instead.

15.24 is the one read, because it is the one that can be checked. Its ten
districts sum to its own AJ&K row in **all seven columns, to the person**:

| | Muslim | Hindu | Christian | Ahmadi | Sch. Caste | Other | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ten districts summed | 4,025,737 | 14 | 2,934 | 3,402 | 60 | 270 | 4,032,363 |
| the printed AJ&K row | 4,025,737 | 14 | 2,934 | 3,402 | 60 | 270 | 4,032,363 |

A territory-level table alone would have had no such control, which is why
15.23 is not the one taken.

**One discrepancy, carried rather than hidden.** Poonch's religions sum to 54
more than the total printed beside them, and the AJ&K row's own parts exceed
its own total by the same 54 -- which is exactly the gap between 15.24's
Muslims (4,025,737) and 15.23's (4,025,683, being 3,325,839 rural plus 699,844
urban). The yearbook disagrees with itself about 54 Muslims in Poonch out of
four million people, and says so twice. It is 0.011% of Poonch, it moves no
share this map prints, and the run names it in the log.

**The districts are not published as records.** geoBoundaries draws Azad
Kashmir as a *single* second-level unit where the yearbook counts ten, so ten
rows would reach one shape: nine would lose and the tenth would put a
district's figures on the whole territory, looking entirely normal while being
wrong by four fifths. The territory's row goes on the territory's shape. This
also answers a question worth asking outright -- AJK is drawn as one admin2
unit because the boundary file draws one, not because a join is failing.

The territory's population becomes **4,032,363 (2017 census)**, replacing a
**2008** Wikidata figure of 4,567,982.

#### Gilgit-Baltistan is the one real absence

> **Partly superseded** by *The two territories' languages, from two
> governments and neither of them the census* below. The census routes named
> here are still shut and still 404. What has changed is the survey: the GB
> MICS bullet below says the territory's own report is "recorded here and not
> wired", and the **2024-25** round's Table SR.3.1 is now what
> Gilgit-Baltistan's language comes from. Azad Kashmir's languages have a
> source too, from a table in the yearbook this section had searched for the
> wrong word.

Nothing found for it, and the routes are worth naming so nobody walks them
again.

* **The Bureau's census tables.** Six filenames, six 404s, listed above.
* **Its own Planning & Development Department**, `www.pnd.gog.pk/pages/downloads`,
  publishes eight PDFs: *GB At a Glance 2025*, *GB MICS 2024-25* in two
  reports, an investment brochure, and four Annual Development Programmes. **GB
  At a Glance 2025 contains district tables drawn from the 2023 census and the
  words "religion", "tongue", "Muslim" and "Shia" on no page of it.**
* **GB-MICS** does carry language, and it is not the same question. Its
  background table reads Balti 28.4%, Burushaski 11.4%, Khowar 5.2%, Wakhi
  0.9%, Other 6.2%, against weighted and unweighted respondent counts in the
  hundreds and low thousands -- a survey's *respondents* by language, not a
  population by mother tongue, and territory-wide rather than by district.
  Publishing that beside four provinces of census mother tongue, in the same
  field, is the mismatch this project exists to refuse. It is a real official
  survey and a usable source for someone willing to mark the basis
  (`{field}_basis`, as `us_prri.py` does) and to establish the universe from
  the report rather than from its table of contents; it is recorded here and
  not wired.
* **`mics.unicef.org` was not asked**, and does not need to be: this
  repository has already recorded it as blocking non-browser clients, and the
  GB government serves the same reports itself.
* **The Pamir Times article** (`pamirtimes.net`, 23 December 2023,
  "Treading the Sacred Linguistic Landscape of Gilgit-Baltistan") that
  circulates household counts by language for GB cites GB-MICS 2017 for them.
  This was first refused here on the principle that a regional news outlet is
  not a source this project cites, only what it points at -- **and the owner
  overruled that, twice. It is now wired**, and is where Gilgit-Baltistan's
  mother tongue on this map comes from. What it gives is three household
  counts (Balti "over 74,000", Shina 70,000, Burushaski 33,512) and three
  percentages (Khowar 3%, Wakhi 2%, other languages 4%), with no total; the
  total of 195,068 households is recovered by division, since the three
  percentages account for 9% and therefore the three counts for 91%. Three
  caveats ride on the figure and all three are in its note: these are
  **households, not persons**, which is what `language_basis` records and what
  keeps them out of Pakistan's national mother tongue; the article is an
  estimate at two removes, scaling a survey on census population; and **Balti
  leads Shina by 4,000 households on figures rounded to the thousand**, which
  is inside the source's own precision even though it decides which colour
  Gilgit-Baltistan takes on the dominant-group map. Other accounts of the
  territory call Shina the larger.
* **Wikipedia carries no table to transcribe.** `wiki_census.py` exists for
  exactly this case -- a census table that reaches this project only as an
  encyclopaedia's copy of it -- and the article does not have one. "Gilgit-
  Baltistan" holds two wikitables: the ten districts with area, capital and a
  2023 population (1,709,049 in total), and a *ranked list* of languages,
  "Rank | Language | Detail", whose cells are prose -- "It is a Dardic
  language spoken in..." -- with no percentage and no count anywhere in it.
  There is nothing for a spec to read: `wiki_census` needs share columns and
  refuses a table it cannot add up, which is the property that makes the route
  safe. Recorded so the next person does not open the article hoping.
* **That district table is a population route, though, and it has now been
  taken -- from the territory's own government rather than from Wikipedia.**
  GB's population on this map was a 2011 Wikidata figure of 1,155,755 against
  a 2023 census 1,709,049, a third too low, and its ten districts had no
  population at all. *Gilgit-Baltistan at a Glance 2025*, on the P&DD host,
  prints the census's district counts, and that is what is read. See
  *Gilgit-Baltistan's population, and what the districts weigh to* below.
* **The census's own category scheme is the deeper problem.** Pakistan's
  mother-tongue question names nine tongues and an "Other", and Shina, Balti
  and Burushaski -- which is to say nearly all of Gilgit-Baltistan -- are in
  the Other. So even a Table 11 for the territory would not name a single one
  of its languages. A census figure with a category scheme that cannot see the
  population is a different problem from no census figure, and for GB the
  answer happens to be both.

The run reads the yearbook's table on PDF page 209 -- the caption is also on page 15, in the contents, and a page carrying the caption with no district rows under it is a mention of the table rather than the table.

Gilgit-Baltistan's two first-level fields and its ten districts therefore
carry an explicit `not_available` with a note naming what was asked, rather
than an empty field that reads as an adapter nobody has run. `not_available`
and not `not_collected`: Pakistan does ask religion and mother tongue, and
asked them there in 2023. It is the publication that is missing, not the
question.

#### What it moved

| | before | after |
| --- | --- | --- |
| Islamabad Capital Territory | no population, no religion | 2,283,244; religion 2023 |
| Azad Jammu and Kashmir | no religion; population 4,567,982, a **2008** Wikidata figure | religion 2017 (Muslim 99.8%, Ahmadi 3,402, Christian 2,934); population 4,032,363, the 2017 census |
| Gilgit-Baltistan | empty | declared, with the routes named; its population read since, below |
| Pakistan's religion roll-up | refused, and **unmeasurable** -- Islamabad had neither the field nor a population, so `covered_share` could not answer at all | measurable, at **99.5%**: only Gilgit-Baltistan's 1.2 million are outside it, against a `COUNTRY_MIN_COVERAGE` of 98% |
| Pakistan's language roll-up | refused at 97.65% | still refused: Azad Kashmir and Gilgit-Baltistan have no mother tongue, and 2.1% of the country is more than the bound allows |

The language roll-up is the one thing still blocked, and the two ways to
unblock it are both named above: read the 2023 Table 11 (which replaces the
2017 route rather than joining it), or find a mother tongue for the two
territories, where every route measured so far is closed.

### Gilgit-Baltistan's population, and what the districts weigh to

The paragraph above named the route and said it was not taken. This is what
happened when it was.

**The Bureau still publishes nothing, and that has not changed.** Table 9 and
Table 11 answer 404 for this territory under every name the four provinces and
Islamabad are filed under. What the territory's own Planning & Development
Department publishes is the census's figures: *Gilgit-Baltistan at a Glance
2025* -- the eighth edition of the Statistical & Research Cell's annual
compilation, 2.4 MB, eighteen pages -- carries "District Wise Population and
Area of GB" on page 3, over a source line reading *i. Pakistan Bureau of
Statistics ii. SRC P&DD GB*. The row is area, the 2017 and 2023 census counts,
the intercensal growth rate, a 2026 projection and a population density, for
the ten districts and for the territory. So the figures are the census's and
the booklet is where they are printed, which is exactly the standing the AJ&K
Statistical Year Book's religion table already has here.

| | |
| --- | --- |
| file | `www.pnd.gog.pk/storage/downloads/AiRIlDEcscWPC1s58oXIgpjlVAS7jd-metaR0IgQVQgR2xhbmNlIDIwMjUuMS5wZGY=-.pdf` |
| found from | `www.pnd.gog.pk/pages/downloads`, which links eight PDFs |
| table | page 3, *District Wise Population and Area of GB* |

**Wikipedia has the same table and is not what is read.** "Gilgit-Baltistan"
transcribes it figure for figure -- ten districts with area, capital and a 2023
population, totalling the same 1,709,049 -- and `wiki_census.py` exists for the
case where an encyclopaedia's copy is the only reachable one. That is not this
case: the office's own publication is reachable, so it is preferred, and the
article is worth recording only as an independent confirmation that the ten
figures are what they are. Its copy is also the harder of the two to read. The
article's division column is merged across rows, so Ghanche, Gilgit, Diamer and
Astore each arrive with a division's name sitting in the district's cell.

**Two columns in that row must never be confused, and no figure tells them
apart.** The 2023 census count and the 2026 projection sit side by side, and
publishing the projection as a census would be invisible -- the exact failure
this project calls worse than a gap. So the column is not taken by position.
The growth rate the table prints between them is recomputed from the two census
counts compounded over the six years between rounds, and a row whose printed
rate does not come back within a twentieth of a percentage point stops the run.
All eleven rows reproduce to within 0.006 of a point. Reading the projection as
the count, or 2017 as 2023, breaks the arithmetic in the first row it is tried
on.

**And the ten add up to the eleventh, to the person** -- 1,709,049, the same
control the AJ&K table is held to and for the same reason: a district this
reader never noticed would otherwise cost its people silently.

| district | 2023 census |
| --- | ---: |
| Astore | 111,573 |
| Diamer | 337,329 |
| Ghanche | 157,822 |
| Ghizer | 200,069 |
| Gilgit | 324,552 |
| Hunza | 65,497 |
| Kharmang | 61,304 |
| Nagar | 87,410 |
| Shigar | 84,608 |
| Skardu | 278,885 |
| **Gilgit-Baltistan** | **1,709,049** |

A figure arrives as several words here too, and more freely than in the
Bureau's tables: Ghanche's 156,697 comes back as `156,`, `6`, `9`, `7`, its
area 8,531 as `8,5` and `31`, and Shigar's density 22 as `2` and `2`. The gap
inside a figure is 0 points and the gap between two columns is never less than
12, which is the same measurement `printed()` already rests on, so the same
threshold rejoins them.

#### What the districts weigh to, which is not what the territory row says

The district populations are what made this askable, and the answer is worth
printing. PILDAT's "Faith Map of Gilgit-Baltistan" gives an area-wise
breakdown, already published here district by district. Weighted by the census
counts above, those ten come to:

| | weighted from the districts | PILDAT's own territory figure |
| --- | ---: | ---: |
| Twelver Shi'a | 42.8% | 39.85% |
| Sunni | 33.7% | 30.05% |
| Isma'ili Shi'a | **15.5%** | **24.0%** |
| Nurbakhshia | 7.9% | 6.1% |

One paper, two statements about one population, and they do not agree -- most
sharply about the Ismaili share, where the gap is eight and a half points. The
likeliest reading is that the area-wise map's flat 100 per cent for Hunza and
Ghizer understates how widely Ismailis live outside those two districts; the
same page's narrative names Ismaili minorities in Skardu that its own figures
leave no room for. Neither figure is adjusted to the other. Both are the
paper's, the territory row's note now says so in as many words, and the
sentence is built from the figures the run computes rather than from a number
typed beside them.

### The two territories' languages, from two governments and neither of them the census

*Gilgit-Baltistan is the one real absence* above ends by saying that the
territories' mother tongue has no route. Two of the three statements in it
have since been overtaken by measurement, and the third has been sharpened.
What follows is what each route actually answered.

**Azad Jammu and Kashmir had a district table nobody had opened.** The
paragraph above records that the AJ&K Statistical Year Book 2023 "contains the
word 'tongue' on no page of it", which is true and was the wrong search. The
table is called **15.33, *Languages Spoken in AJ&K***, it is on PDF page 213
beside the marriages table, and it prints a percentage for each of the ten
districts:

| district | Kashmiri | Gojri | Pahari | Shina | Others |
| --- | ---: | ---: | ---: | ---: | ---: |
| Muzaffarabad | 15 | 35 | 50 | – | – |
| Neelum | 20 | 10 | 63 | 5 | 2 *Kundal Shahi* |
| Jhelum Valley | 15 | 35 | 50 | – | – |
| Bagh | 2 | 3 | 95 *Dhundi-Khairali* | – | – |
| Haveli | 5 | 30 | 65 *Chibali* | – | – |
| Poonch | – | 6 | 94 *Punchi* | – | – |
| Sudhnoti | – | – | 95 *Punchi* | – | 5 |
| Kotli | – | 35 | 63 *Pahari Pothwari* | – | 2 |
| Mirpur | – | 10 | 85 *Mirpuri* | – | 2 |
| Bhimber | – | 5 | 30 *Mirpuri* | 30 *Dogri* | 35 *Punjabi* |

Four things about that table decide how it is read.

* **Its source is not a statistical office.** The line under it names the
  **Kashmir Liberation Cell, Muzaffarabad** — a department of the AJ&K
  government — and not the Bureau of Statistics whose religion table sits nine
  pages earlier. The record says so first, and `language_basis` is
  *languages spoken*, which keeps it out of Pakistan's national mother tongue
  exactly as Gilgit-Baltistan's is kept out.
* **It prints no year.** Table 15.32 above it is captioned "(2018 to 2022)";
  15.33 is captioned nothing. So the two AJ&K rows carry **no
  `language_year`**, and `tests/test_composition_year.py` was rewritten to
  hold an exemption to the *rows* it covers rather than to a whole field of a
  file, so this one table cannot cover for a second.
* **Five columns are made to hold eight languages.** Where a district speaks
  something the headings do not name, the office writes the name in the cell:
  Bhimber's **Dogri is printed under the column headed *Shina*** and its
  Punjabi under *Others*. Reading the heading would have filed Dogri speakers
  as Shina, and Bhimber would still have summed to 100. Every cell name is
  therefore declared in `AJK_TONGUE_NAMES`, and an unrecognised one stops the
  run. The five local names of the Pahari–Pothwari continuum stay in the
  Pahari column, where the table puts them; the map writes
  **Pahari-Pothwari** rather than "Pahari" because Nepal's unrelated
  Tibeto-Burman *Pahari* is already on this map, and one label for two
  languages would put four million people in the wrong family.
* **Mirpur's row sums to 97.** The other nine sum to exactly 100. Three points
  of one district is 0.34% of the territory — inside the half point the
  panel's own rounding repair would have swallowed without a word — so it is
  spread across *Mirpur's own* languages, where the people it describes live,
  and the note names the district and the shortfall.

geoBoundaries draws Azad Kashmir as a **single** second-level unit — measured
against the boundary file, which gives Pakistan 126 second-level shapes and
exactly one of them for the whole territory — so the ten rows have nowhere of
their own to land, exactly as the religion table's ten do. They are weighted
by the 2017 census populations the religion table already supplies and
published once on the territory and once on the shape:

> **Pahari-Pothwari 68.8%, Gojri 18.6%, Kashmiri 4.6%, Punjabi 3.6%, Dogri
> 3.1%, Other languages 1.0%, Shina 0.2%, Kundal Shahi 0.1%.**

Two of those eight exist only because the cell was read instead of the column:
Dogri's 3.1% is Bhimber's 30% of 432,719 people, and it would otherwise have
been added to Shina, which 0.2% of the territory actually speaks.

**The AJ&K MICS asks the question and does not publish the answer.** Worth
recording, because it is the obvious next place to look. `pndajk.gov.pk/micsajk/`
serves three files; the 734-page **AJ&K MICS 2020-21 Survey Findings Report**
prints the questionnaire in Appendix E, and **HC1B** reads *"What is the mother
tongue of (name of the head of the household)?"* with English, Urdu,
Hindko/Pahari/Potohari, Kashmiri, Gojri, Punjabi and an Other. The word
"Gojri" occurs on eight pages of that report and every one of them is a
questionnaire: there is no results table. The answers are in the microdata, on
`mics.unicef.org`, which this repository has already recorded as blocking
non-browser clients and which is not spoofed.

**Gilgit-Baltistan's own survey does publish it.** `www.pnd.gog.pk` links two
**GB MICS 2024-25** reports, and the Survey Findings Report's **Table SR.3.1,
*Household composition*** (PDF page 57, printed page 39) distributes 6,929
households by the language of the household head:

| | Shina | Balti | Brushaski | Khowar | Wakhi | Other |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| weighted per cent | 48.0 | 29.2 | 12.3 | 5.2 | 1.0 | 4.2 |
| weighted households | 3,325 | 2,025 | 855 | 360 | 71 | 293 |

That table had been looked for and missed, **because the report spells it
"Brushaski"**: a search of its 731 pages for *Burushaski* returned nothing, and
so did the 2016-17 round's 398-page Final Report, which genuinely has no
language table at all — neither *Burushaski* nor *Shina* appears on any page
of it. The spelling is declared in `GB_MICS_SPELLING` rather than matched
loosely. The shares are built from the weighted household counts rather than
the printed percentages, so they partition exactly; fieldwork ran **October
2024 – February 2025**, so the year is 2025, and the run reads it off the
table's own caption rather than the file name.

**This replaces the Pamir Times article as the figure and keeps it as the
fallback.** The owner overruled a refusal to cite that article twice, and the
reason was that nothing official was reachable; the office's own report now
is. The two disagree about the thing the article's own note flagged: it put
Balti 4,000 households ahead of Shina on figures rounded to the thousand, and
the survey's own table puts **Shina eighteen points ahead of Balti**. Where
the survey cannot be fetched the field falls back to the article, with its
date and its note, rather than to a blank.

**The ten districts still have no language, and now say why.** Every route was
asked and each is named on the district rather than only here: the Bureau
publishes no Table 11 for the territory under any name the four provinces are
filed under; the 2023 census question would not answer it either, naming Shina
and Balti but having **no column for Burushaski, Khowar, Wakhi or Domaaki**, so
Hunza, Nagar and much of Ghizer would be counted inside its "Other"; *GB at a
Glance 2025*, which is where these districts' population comes from, carries
no language table; and **both MICS rounds give district and language of the
household head as two separate distributions in the same table rather than one
crossed table**. The territory's figure is not spread over the ten because
they differ sharply from it and from each other — Balti is the language of
Skardu, Ghanche, Kharmang and Shigar, Shina of Astore, Diamer, Ghizer and
Gilgit, Burushaski of Hunza and Nagar — so a territory average put on all ten
would be wrong on every one of them.

### The 2023 Table 11, and two districts whose largest group was a missing category

The paragraph above named the route; this is what happened when it was taken.

**The observation that started it was a district, not a country.** Chitral came
out **93.1% "Other language"** and Kohistan **91.9%** -- 1.4 million people
between them whose largest language group was the absence of a category. That
is not a bad join, and it is not a gap either: a gap is visible and says the
field is empty, while this says, with a number and a colour on the map, that
the commonest thing about these people is that the form had no word for them.

The cause was the census round. Language came from the 2017 question, which
names nine tongues and an Other, and the languages of the north are all in the
Other. **The 2023 question names fifteen** -- Shina, Balti, Mewati, Kalasha and
Kohistani were added -- and the Bureau publishes it as Table 11, filed exactly
as the Table 9 this project already reads:
`table_11_<province>_districts.pdf`, with Islamabad again dropping the word
because it is one district. All four provinces and the capital answer 200.
Gilgit-Baltistan and Azad Kashmir answer 404, as they do for Table 9 -- one
fact about the Bureau's coverage, not two.

**The reader did not need to be written.** Table 11 has the same shape as Table
9 down to the details that were expensive to learn the first time: tehsils
interleaved with districts, ALL LOCALITIES / RURAL / URBAN each repeating the
same people, a dash printed where a language is absent, and a figure arriving
as several words. Nine cells to a row against sixteen is the only difference,
so `districts()`, `check()`, `province_row()` and `merge()` now take the column
list instead of assuming it.

**Table 11's districts are held to Table 9's.** The two come out of one census
and one office, so the sets are compared and any difference either way stops
the run. The failure this guards against is silent: a district whose language
row was never found simply has no language, which on this map is
indistinguishable from a district the census did not ask.

#### What it moved

| | before (2017, via the Census Bureau) | after (2023, from the Bureau direct) |
| --- | --- | --- |
| Kohistan | 91.9% Other language | **88.5% Kohistani**, 6.5% Shina |
| Chitral | 93.1% Other language | 92.4% Other -- and **Kalasha 5,065**, named |
| Upper Dir | 8.6% Other | 3.7% Other, 5.1% Kohistani |
| districts with a residual above 1% | 33 | 6 above 5% |
| districts published | 124 | **127** -- Chaman, Duki and Surab, created since 2017 |
| language year | 2017, six years off the religion beside it | 2023, the same census |

The three districts gained and the six "Frontier Region" units lost are the
same event: FATA was abolished in 2018, so those units do not exist in the 2023
census, and three new districts do.

**Pakistan therefore leaves `uscb.py`.** Two files publishing language onto one
shape, six years and six named tongues apart, is exactly what the agreement
rule answers by sending both to a gap. The Karachi declaration written there is
the case that made `combine()` exist -- six parts, one shape, no published row
of their own to check the sum against -- so `tests/test_uscb_merge.py` keeps it,
copied verbatim rather than rewritten to suit the test.

#### Kalasha, and what a census can and cannot see

The Kalash are about four thousand people in three valleys of Chitral, and the
only community in Pakistan practising the pre-Islamic religion of the Hindu
Kush. Before this they appeared **nowhere in this project's data**, under any
field, at any level.

They appear now, as a language: `Kalasha`, **5,065 people in Chitral**. The
column sums to **7,467 nationally** against the 7,466 that accounts of the 2023
census publish -- which is the strongest check available on this reader,
because it is not this project's arithmetic. The rest is ones and twos in the
cities, 614 in Karachi the largest.

They do **not** appear as a religion, and that is the census's doing rather
than this project's. Table 9's categories are Muslim, Christian, Hindu, Ahmadi,
Scheduled Castes, Sikh, Parsi and Other; the Kalash faith is in the Other, with
4,970 people in Chitral. That figure is left as printed. Naming all of it
Kalash would overstate a community put at 3,000 to 4,000 adherents, and naming
part of it would mean choosing between estimates -- the gap between 4,970,
5,065 Kalasha speakers and ~3,500 adherents being families who converted and
kept the language. The note says all of this; the number stays the census's.

#### Six districts that say what their Other holds

Reading the newer table did not empty the Other column, and in one district it
barely touched it: **Khowar has no column on the 2023 form either**, so Chitral
is still 92.4% Other, and Khowar is what that is.

Six districts now carry a note naming the contents of theirs:

| district | Other | what it is |
| --- | --- | --- |
| Chitral | 92.4% | **divided — see below** |
| Batagram | 11.9% | Gujari, and Kohistani across the northern boundary |
| Mansehra | 11.6% | Gujari of the Kaghan valley |
| Quetta | 8.2% | Hazaragi |
| Rawalpindi | 6.3% | Pothwari |
| Swat | 6.1% | Torwali in Bahrain, Gawri in Kalam, Gujari in the hills |

**They name the languages and do not divide the figure between them**, which is
a different decision from the one taken for India's "Other religions" and taken
for a different reason. There the census published its own breakdown of its own
residual (the C-01 Appendix) and the job was to read it. Here the Bureau prints
one number and no breakdown at all, so any split would be this project's
arithmetic wearing the census's clothes -- and the estimates that would drive it
disagree badly: Dameli is "perhaps seventy families" in one account and 5,000
speakers in another, an order of magnitude apart. SIL's *Sociolinguistic Survey
of Northern Pakistan* volume 5 would settle it and answers **403** to this
project, which is a deliberate block and is not worked around.

A reader told the split is not published can go and find it. A reader shown a
split this file invented cannot tell that it was.

#### Chitral, divided anyway — on the owner's instruction, and how it is marked

The paragraph above is the general rule and Chitral is the declared exception
to it. The owner asked for numbers. 474,149 people is too many to leave as a
word, and unlike the other five this district's Other is not a fringe — it is
almost everybody in it.

**Khowar is the remainder, not a count, and that is the whole design.** No
source publishes a Chitral-specific Khowar figure: Ethnologue's 580,000 is
every Khowar speaker anywhere, which is more people than live in Chitral,
because Khowar is also spoken in Ghizer, Gupis-Yasin and upper Swat. So the
six minority languages take their published estimates and Khowar takes what
is left of the census's column:

| group | figure | where it comes from |
| --- | --- | --- |
| Khowar | **441,999** | the census column less the six below — a *remainder* |
| Palula | 10,000 | Ashret and Biori valleys, Puri in Shishi, Kalkatak |
| Yidgha | 6,150 | the Lutkoh valley |
| Dameli | 5,000 | the Damel valley |
| Gawar-bati | 4,000 | Arandu, of some 12,000 across the Afghan border |
| Madaklashti | 4,000 | Badakhshani Persian, Shishi valley |
| Kativiri | 3,000 | "less than 3,000", on the Nuristan border |

Chitral therefore reads Khowar 86.1%, Pashto 5.8%, Palula 1.9%, Yidgha 1.2%,
Kalasha 1.0%, Dameli 1.0%, and the rest below that — and carries **no residual
at all**, the only district in Pakistan where one was removed rather than
shrunk.

**Why the remainder goes on the largest figure.** Every error in those six
estimates lands on Khowar, where it is proportionally smallest: being wrong by
2,000 on Palula moves Khowar by half a percent of itself. The estimates are of
mixed vintage and are published as-is, not scaled up for Chitral's growth
since they were made — scaling would be a second layer of this project's
arithmetic on someone else's, and the residual absorbs whatever they are short
by. This is the discipline Gilgit-Baltistan's language table already uses,
where Balti carries the residual for being the least precise figure its source
gives.

**Khowar is overstated, and the note says so.** The tongues with no published
Chitral figure — Wakhi in Broghil and upper Yarkhun, Kyrgyz beside them,
Gujari, Sarikoli — have nowhere else to go, so they are inside that 441,999.
They are families and hundreds against 442,000. Inventing a number for each to
avoid admitting it would have been the worse trade.

**What the note has to carry**, and what a test asserts it still does: that
the division is not the census's, that the Khowar figure is a remainder rather
than a count, and that Khowar is overstated. Only the district total and the
Pashto, Kalasha, Urdu and Kohistani beside it are counted by the census.

**Khyber Pakhtunkhwa's own row keeps its Other unbroken.** The estimate was
made for one district; spreading it across the province would be exactly the
arithmetic the note disclaims. A reader drilling from the province into the
district will see the Other vanish, and that is the honest asymmetry rather
than a bug.

**The substitution is inside the Other column and touches nothing else**, so
the row still sums to the district's printed 513,395 — asserted, and the run
refuses if it stops being true. It also refuses rather than clamping if the
estimates ever outgrow the column, because a negative remainder would mean
either the column or an estimate is wrong, and both are worth stopping for.

Nuristani joins the group tree as its own branch of Indo-Iranian, which is
what Kativiri is — neither Indo-Aryan nor Iranian, and the only such language
on this map.

**A note keyed to a district that no longer exists reaches nobody, silently** --
the district keeps the general note and looks exactly like one nothing was
written for. The Bureau renames and splits districts between rounds (Chitral
and Kohistan are each several districts now, summed here into the one shape
geoBoundaries draws), so the run refuses if any note names a district the
tables do not.

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
* **Indonesia** — its workbook carries a four-bucket first language split
  and no religion or ethnicity, and was briefly mistaken for an opening. What
  Indonesia carries now came from elsewhere: see *Indonesia: what BPS's
  refusal left reachable* below.

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

  > **This one is now openable, and the repair is the project's own.**
  > `probe_tls --chain` fetched the intermediate from the certificate's AIA
  > `caIssuers` extension, then the root above it, and reported **VERIFIED
  > handshake ok, TLSv1.3**; the census page then answered 200 and linked the
  > office's own PDFs, which serve 200 to a plain client. That is the same
  > `aia=True` repair `india_census.py` uses, and it is full verification
  > rather than a way round it — see `scripts/probe_tls.py`. It is what the
  > Bangladesh language evidence below is cited from. The workbook itself is
  > still read from HDX, which works and is the office's own file under a CC0
  > release; moving a working data path is a separate change from recording
  > that the host is no longer shut.
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

#### Bangladesh's language: the question was put, and the answer has two columns

All 64 zilas carried an empty `language`, with no note on it at all — which on
this map reads as an adapter nobody has run. It is not that. Measured, in this
order:

| asked | answered |
| --- | --- |
| the HDX workbook's 42 sheets, listed in full | dwelling, household type, sex, marital status, **religion**, growth and sex ratio, disability, literacy (three sheets, one of them by religion), students, working status, work type, sector, NEET, mobile phone, internet, financial account, mobile banking, **ethnic population**, nationality, returned migrant, and fourteen housing sheets. **No language sheet, and no language column in the 445-column merged sheet.** |
| `nsds.bbs.gov.bd` (two census pages) | timed out, both |
| `file.portal.gov.bd` (the National Report) | timed out |
| `web.archive.org` mirror of `bbs.portal.gov.bd/.../2024-01-31-15-51-b53c55dd692233ae401ba013060b9cbb.pdf` | **200**, 10,307,919 bytes, *Population and Housing Census 2022, National Report (Volume I)*, 520 pages |
| `bbs.gov.bd/site/page/47856ad0-…/Population-and-Housing-Census`, with the chain completed from AIA | **200**, and it links the office's own copy of that report |
| `objectstorage.ap-dcc-gazipur-1.oraclecloud15.com/…/9ce5bd160bb14a1ab1eabe886adddb9a.pdf` | **200**, **10,307,919 bytes**, 520 pages — the same file, first-hand |
| that file, searched for *tongue* and *Language* | **one page in 520**, and it is the literacy definition ("can read and write at least in one language") |
| `catalog.ihsn.org`, keyword *bangladesh* | 957 studies, none of them this census |

The National Report is what settles it, because it describes the form the
census was collected on. It was first read through the Internet Archive and
then from the office's own store, byte for byte the same file, which is the
copy cited here. Section 1.8, *Census Questionnaire*, page 15:

> The questionnaire consists of two modules the Household Module and the
> Individual Module. In the Household Module, there are 15 questions on various
> characteristics of households […] In the Individual Module, there are 20
> questions on different individual facts such as age, sex, marital status,
> religion, disability, education, working status, training, mobile phone and
> internet use, banking inclusion, ethnic population etc. Including all, there
> are 35 questions in the census questionnaire.

Language is not among them, and nothing downstream contradicts that. The word
appears on **one of the report's 520 pages**, and that page is the definition
of literacy rather than a table. Its contents list no language table, its 33
district tables (P1–P33) run from household and population through literacy,
disability and work to *Ethnic Population by Sex and District* and *Ethnic
Population by Category, Sex and Division* without one, and the office's own
district workbook has 42 topic sheets and none.

All of that is true, and the conclusion first drawn from it — that the
question was never put, `not_collected` — was **too strong**. The census is
not the whole of what the Bureau asked.

##### The survey that does ask it

The *Report on Socio-Economic and Demographic Survey 2023* (BBS, Statistics
and Informatics Division, Ministry of Planning, June 2024, ISBN
978-984-475-268-9, **553 pages**, Bangla and English on facing columns) is the
**long-questionnaire survey run after the census** — "formerly known as a
Sample Census" — and is published as one of the **five national reports of the
Population and Housing Census 2021 Project**. Fieldwork ran 21 May to 22 June
2023. Two-stage cluster sample: EAs drawn from the Census 2022 EA frame, then
25 households per EA, 86 EAs per stratum across **140 strata** — each of the
64 districts split rural/urban, plus 12 city corporations, `(64×2) + 12 = 140`.

Its **Module 4 collects mother tongue by name**, beside religion and ethnic
population. So Bangladesh does gather the answer, and a map saying otherwise
is wrong — most visibly on the eight divisions, the exact shapes for which a
mother-tongue table exists.

**What it publishes still cannot be drawn.** Table 3.6, *Population by Mother
Tongue and Second Language, Division and Location*, has exactly two
mother-tongue columns:

| division | Bangla | Others |
| --- | ---: | ---: |
| National | 99.17 | 0.83 |
| Barishal | 99.99 | 0.01 |
| Chattogram | 97.11 | **2.89** |
| Dhaka | 99.76 | 0.24 |
| Khulna | 100.00 | 0.00 |
| Mymensingh | 99.29 | 0.71 |
| Rajshahi | 99.36 | 0.64 |
| Rangpur | 99.86 | 0.14 |
| Sylhet | 98.96 | 1.04 |

"Others" is a residual and nothing else: **no mother tongue but Bangla is
named anywhere in the report**. All 553 pages were swept for Chakma, Marma,
Santal, Garo, Tripura, Mro, Rakhain, Manipuri, Urdu, Bishnupriya, Tanchangya,
Khasi, Hajong, Munda, Oraon, Rohingya, Bawm, Khumi, Chak, Pankho, Lushai,
Koch, Dalu and Rajbanshi — **zero pages match**. (The only other language the
report names at all is English, and it names it as a *second* language, an
ability rather than a composition.)

A named group against a residual is not a composition: drawn as two slices it
would read as a survey that found two languages. And there is nothing below
the division to draw in any case — the report's list of tables says
**Division 66 times and District not once**, although the survey is stratified
on the districts and its own precision table (Table 1.1) quotes a *District
Estimate* margin of error beside the divisional ones. The design supports
district figures; this report publishes none.

##### So the gap stands, and its reason changed

Bangladesh's language is a gap at every level, and it is **`not_available`,
not `not_collected`** — declared once in `NOT_COLLECTED_POLICY` so the country
row and its 64 zilas cannot drift apart. The status matters: `not_collected`
means the state never gathers the field, and Bangladesh does. The honest
reason names the census questionnaire that omits it, the survey that asks it,
and the two-column shape of what was published.

That is the same shape of fact as Bangladesh's ethnicity, and is now marked
the same way. The central declaration carries no percentages, by the rule that
**a declaration explains an absence and never states a share** — the rule the
Maldives' tempting "100% Islam" was written down to prevent. The figures live
in this document instead.

**Religion is not declared with it**: the same census asks religion, and it is
on the map from the same workbook, at zila level. What Bangladesh asks about a
minority's identity is ethnic group, under the *Khudra Nri-goshthi Sangskritik
Pratisthan Ain, 2010*, and that stays `not_available` too: the census does
collect it, publishes a count of the ethnic population by district and a
breakdown by category only by division, and a count of "the ethnic population"
against everyone else is not a composition by ethnic group.

##### What the survey report does *not* settle

Measured, so the next reader does not re-open it hoping:

* **Religion** — Table 3.2, *Population by Religion, Division and Location*:
  Muslim, Hindu, Christian, Buddhist, Others, for the eight divisions. The map
  already carries the same five groups for all **64 zilas** from the 2022
  census itself, as exact counts rather than sample shares. The survey table
  is coarser and weaker, and is not read.
* **Ethnicity** — Table 3.4, *Ethnic Population by Sex, Division and
  Location*, is **not** each division's ethnic share. Its division column sums
  to exactly 100.00 (0.08 + 61.15 + 2.38 + 1.92 + 3.91 + 18.37 + 5.28 + 6.91):
  it is the distribution of the country's ethnic population *across*
  divisions, and carries no category breakdown at all. It is a different table
  from the National Report's *Ethnic Population by Category, Sex and
  Division*, which remains the open route to a real Bangladeshi ethnicity
  composition and is **not** in this report.

#### …and the count it does publish now reaches the reader

`not_available` was right; a *bare* `not_available` was not. All 64 zilas
carried the status with no note at all — on the map, the blank panel that says
a fetch nobody ran, when what is true is a question asked, answered and
published at a coarser grain than this map draws.

The adapter now reads the workbook's third relevant sheet, *Ethnic Population
by Sex* (Table P28), and puts the district's own figure in the reason:

> Census 2022 counts 372,875 of Rangamati's 647,586 people as ethnic
> population — 57.58% — but does not say which peoples they are. …

Nationally that is **1,650,478 people, 1.00%**, and it is concentrated almost
entirely in three districts: **Rangamati 57.6%, Khagrachhari 48.9%, Bandarban
41.2%** — the Chittagong Hill Tracts — against 0.01% in Nilphamari,
Lakshmipur and Lalmonirhat. None of that was visible before.

The shares are taken against *Population by Sex, Dist & Loca*, the same
district totals the religion check reconciles to the person. The workbook's
other population sheet, `Population_District`, differs by a few hundred people
in places; mixing the two would print a share beside a total it was not taken
from.

Held to the same standard as a religion: the ethnic total must equal its own
male plus female column in every district (it does, 64 of 64), and must never
exceed the district's population — which is how a column read one place left
announces itself before it reaches a panel as a percentage over 100.

**This paragraph used to end "it is still not drawn as a composition at zila
level, and must not be", and that was wrong.** The objection was that "a
single total and a residual is not a list of peoples". The premise is false:
the remainder is not a residual. Table P28 counts the scheduled population and
*Population by Sex, Dist & Loca* counts the whole district, and the difference
between two counted figures is itself counted. What the split does not do is
*name* the peoples — which is a limit on the labels, not a reason to withhold
the measurement. See "The split the census does support" below.

#### The named groups, at the eight divisions

The route the paragraph above left open has been taken. The National Report's
**Table P29, *Ethnic Population by Category, Sex and Division*** (PDF pages
413–420) breaks the same 1,650,478 people into **51 named categories** — the
groups scheduled under the 2010 Act — for each division. Nationally: Chakma
483,365, Marma 224,299, Tripura 156,620, Saontal 129,056, Oraon 85,858, Garo
76,854, Munda 60,201, Mro 52,463, Tonchonga 45,974, Barman 44,671, down to
Vil at 95 and Kol's two people in one division.

**Table P28 is read from the same report alongside it**, and the two make each
other trustworthy rather than merely parsed. Four checks, every one to the
person:

1. each block's rows sum to the header printed above them;
2. the eight divisions sum to the national header;
3. each category's national figure equals the sum of its eight divisional
   ones — the table read down as well as across;
4. the report's 64 district totals equal the workbook's, two separate
   publications of one census agreeing.

The Bureau spells two districts differently between its own publications —
*Netrokona* against *Netrakona*, *Chapainawabganj* against *Chapainababganj* —
and those two are declared rather than bridged by a rule, so a third spelling
fails loudly instead of quietly matching something near it.

**The shares are of each division's whole population.** Chattogram's Chakma
are 475,548 people: 48% of the division's ethnic population and **1.4% of the
division**. Published the first way, this map would call Chakma the largest
group in Chattogram, where they are one person in seventy. So the denominator
is the division's own population, summed from the districts the report itself
places in it; the list covers 2.90% of Chattogram, 1.10% of Rajshahi, 1.00% of
Sylhet and 0.05% of Barishal; the panel says so, and the map declines to name
a leader because the largest listed group cannot exceed what is unlisted.

Everyone else is **not shown**. The census publishes the ethnic categories and
no count and no label for anybody else, and a slice invented to fill the bar
would be fabrication.

**47 of the 51 categories have no place in this project's group tree yet** and
are published under the census's own spelling — Bom, Tonchonga, Monipuri,
Saontal, Lusai as BBS writes them. The tree having no opinion about them is a
fact about the tree; inventing one from a resemblance would be a fact about
nothing. Placing them is open work.

#### The split the census does support, at all 64 zilas

The naming stops at the division. The *counting* does not, and those are two
different limits that were being treated as one.

Table P28 gives every district the number of people in the scheduled ethnic
groups. *Population by Sex, Dist & Loca* gives every district its whole
population. Both are counted, both are published, and their difference is
counted too — so each zila now carries a two-part composition rather than a
sentence in a panel:

| Zila | Scheduled ethnic groups | Bengali |
| --- | --- | --- |
| Rangamati | 372,875 — **57.6%** | 274,711 — 42.4% |
| Khagrachhari | 349,390 — 48.9% | 364,729 — **51.1%** |
| Bandarban | 197,983 — 41.2% | 283,123 — **58.8%** |
| Dhaka | 27,137 — 0.2% | 14,707,564 — **99.8%** |

Rangamati is the one district in Bangladesh where the scheduled groups are the
majority, and until this change the map painted it nothing at all.

**The remainder is called Bengali because that is the census's own framing**,
not because it is a leftover bucket. The 2010 Act schedules a list of peoples
*set apart from* the Bangalee population; the Bureau's own tables are built on
that contrast. Naming it "other" would be less true, not more cautious.

**The category is deliberately not called "ethnic minorities".** That label
already exists in the group index as China's, marked residual — and
`dominant()` skips residual groups in favour of any non-residual one. Under
that name Rangamati would have been painted **Bengali at 42.4%** while the
scheduled groups held 57.6% of it: the map contradicting its own panel. This
is a counted category, so it is named and filed as one — a census category
under South Asian ancestry in `group_tree.py`, beside Indo-Aryan, Dravidian,
Munda and Tibeto-Burman rather than below them, because the fifty-one peoples
inside it belong to all four.

**Every zila note says where the naming stops**, so "Scheduled ethnic groups
57.6%" cannot be read as the census declining to look:

> …the district is as fine as the naming goes: the Bureau publishes the
> fifty-one categories behind that total only by division, so which peoples
> these are is on the division above this one, not here.

**Language does not follow**, and the reason is sharper than the geography.
See the sweep below.

#### Why there is no zila language, re-argued from five publications

"SDS 2023 stops at the division" was one source's habit, not a fact about
Bangladesh. It was treated as a hypothesis and attacked on five routes, all
fetched on the runner:

1. **The Census 2022 admin-2 workbook** (HDX, 1,213,869 bytes) — **all 42
   sheets** enumerated by name with their header rows, not just the three the
   adapter reads. Dwelling type, household type, sex and location, marital
   status, religion, growth and sex ratio, disability, literacy ×3, students,
   working status, type of work, sector, NEET, mobile phone, internet,
   financial account, mobile banking, ethnic population, `Population_District`,
   returned migrants and 14 housing sheets. **None is language.** The two
   sheets matching "Bangla" carry *Bangladeshi National* — citizenship.
2. **The Census 2022 National Report**, 520 pages. `mother tongue`: **0
   pages**. `language`: 1 page. `bilingual`, `spoken`, `speak`, `dialect`,
   `linguistic`: 0. Of its **239 distinct table headings, 109 name a Division
   and 46 a District — not one names a language.**
3. **2011 Zila Report, Rangamati** (470 pp), chosen as the most linguistically
   various district. `mother tongue`: 0 pages. 49 table headings, none a
   language.
4. **2011 Community Report, Rangpur** (694 pp) — 32 table headings, none a
   mother tongue.
5. **MICS 2019** (564 pp), and this is the sharpest finding. MICS **is**
   district-representative and it **does ask**: question **HC1B**, *"What is
   the mother tongue/native language of the head of the household?"*, with
   exactly two printed answers, **BANGLA** and **OTHER LANGUAGE**. The phrase
   occurs on 1 page in 564, and that page is the blank questionnaire. Nothing
   tabulates it. The MICS 2019 *District Summary Findings Report* does not
   contain the word "language" at all.

**So the limit is not geography first.** Both Bangladeshi instruments that ask
mother tongue — SDS 2023 and MICS 2019 — code it as **one named language
against an unnamed residual**. That shape is not a composition at *any* level;
the division ceiling is the second reason, not the first.

**Two limits stated rather than rounded up.** 63 of the 64 Zila Reports were
not read. And the 2011 *National Report Vol-04* (378 pp) scored zero for every
term and **proves nothing** — printing its pages returns empty text, because it
is a scan with no text layer. That is recorded as a non-result rather than
counted as evidence.

The three 2011 volumes were read through the Internet Archive's copy of the
Bureau's own files: `203.112.218.65:8008`, which `bbs.gov.bd` still links the
whole series to, times out from the runner.


#### The fifty-one categories, placed in the group tree

Publishing the names at division level put 42 labels in front of the map that
the tree had no family for — they would have led a unit with no colour. They
are now filed by the language each community speaks, which is the axis
`group_tree.py` states it uses elsewhere:

* **Tibeto-Burman** — Marma, Rakhain, Mro, Chak, Bom, Khiang, Khumi, Lusai and
  Pankhoa in the Hill Tracts; Tripura, Monipuri, Koch, Barman and Dalu along
  the northern border.
* **Indo-Aryan** — Chakma and Tonchonga, whose language is a close relative of
  Chittagonian rather than of Marma, which is why they sit here and not with
  their Hill Tracts neighbours; Hajong and Banai; the plains and tea-garden
  communities Bagdi, Bedia, Bhuimali, Gonju, Malo/Ghasimalo, Mushor, Rajoar
  and Vil; and Gurkha, from the Nepali garrison settlements.
* **Munda** — Saontal, Mahali, Kora, Turi, Kol and Shobor.
* **Dravidian** — Kondo, the Bureau's spelling of Khond, whose Kui is
  Dravidian.

**Five are left unplaced on purpose**: Boraik/Baraik, Gorait, Hudi,
Kharoar/Kheroar and Patro. Each is a small tea-garden or Sylhet community
whose affiliation the sources genuinely disagree about, and this project would
rather carry five labels with no family than five filed under a guess. They
lead no unit, so nothing on the map turns on them.

#### Why the hill districts stop at the division too — both 2011 series read

Table P29 stops at eight divisions, so the obvious next question is whether
the three Chittagong Hill Tracts districts — Rangamati 57.6% ethnic,
Khagrachhari 48.9%, Bandarban 41.2% — can be given a composition of their
own. **They cannot from anything BBS has published.** Both candidate series
were fetched and read rather than assumed:

* **Zila Report: Rangamati** (2011 census, BBS, October 2015, 470 pp,
  ISBN 978-984-33-8608-3). It has an *Ethnic Population* section and three
  upazila-level ethnic tables, and none of them is a breakdown by group:
  **H08** crosses ethnic households with drinking water, toilet and
  electricity; **H09** with literacy; **H10** with household size and sex.
  The zila's ethnic population is given as a single total — 356,153 people,
  59.76% of Rangamati — and the peoples appear only in a prose sentence with
  no numbers: *"Ethnic communities such as Chakma, Marma, Tanchangya,
  Tripura, Chak, Khumee, Luchei, Pankhoa, Riang, Khumi, Mro, Santal,
  Monipuri, Bome, Kheyang, Murang and other sub-groups belong to this zila."*

* **Zila Community Report: Bandarban** (2011 census, BBS, November 2014,
  617 pp, 22.7 MB). Its **Table C-01** is *"Area, household, population and
  density by residence and community"*, and its columns are area in acres,
  households, population total, population in households, floating
  population and density — verified on the zila line, 387,129 in households
  plus 1,206 floating against a printed 388,335. It is a **gazetteer**: every
  mauza and para of the district listed with its head count. There is no
  ethnic column and no group column anywhere in it. The hundreds of pages
  that match *Chakma*, *Marma* or *Mro* match them as **place names** —
  Banopur Chakma Para, Amtali Marma Para, Nutan Murung Para — *para* being a
  hamlet, not a category.

So BBS 2011 publishes ethnic population exactly as BBS 2022 does: **a total,
never split by named group**, one administrative level finer. Which means the
per-upazila group percentages that circulate (Wikipedia's *Ethnic groups in
the Chittagong Hill Tracts* gives Chakma 91.15% in Juraichhari, Marma 49.48%
in Rowangchhari, and so on for six peoples) **are not traceable to either
published series**, and this project does not carry a figure it cannot source.
They are also percentages with no denominators and truncated at `Others <1%`,
so they could not be aggregated to a district even if they were sourced.

**Fetching note, since the route is not obvious.** `bbs.gov.bd` hangs on this
page (a `probe_tls --chain --fetch` run sat in progress for 25 minutes), and
the reports themselves live on `203.112.218.65:8008`, a host that is dead.
The Internet Archive has them, but asking it for a *page's* timestamp gives a
playback that truncates: two attempts at `Com_Bandarban.pdf` both died at
7,257,916 of 22,753,064 bytes. The fix is the **CDX API** — query
`web.archive.org/cdx/search/cdx?url=…&matchType=prefix` for the file's own
captures, then request one by its exact timestamp with the `id_` modifier.
`20211123141051id_` returned all 22.7 MB cleanly. Four good captures of that
file exist (2019, and three in 2021).

#### The two Wikipedia tables, reconciled

* ***Ethnic minorities in Bangladesh*** carries Table P29's national column:
  the same 51 categories, none extra, none missing. But **21 of 51 rows agree
  exactly and 30 do not**, and every disagreement is in the same direction —
  the census higher. Chakma 483,365 against 483,299, Marma 224,299 against
  224,261, Tripura 156,620 against 156,578, Others 68,588 against 68,538;
  total **1,650,478 against 1,650,159**, 319 people short. A one-directional
  error across 30 rows is a transcription, not a second measurement.

* ***Languages of Bangladesh*** gives Bangla 163,507,029 and Others
  **1,651,587** against a total of 165,158,616 — and that total is the census
  figure exactly. But "Others" is **1.0000% of it to within one person**
  (a flat 1% would be 1,651,586), while BBS's own SDS 2023 Table 3.6 puts
  Others at **0.83%**, about 1,370,817 people. The ethnic population is
  1,650,478, or 0.9993%. The table therefore looks like the **ethnic count
  relabelled as a language split**, and it contradicts the Bureau's own
  language figure by roughly 281,000 people. It is not used.

Two faults were found and fixed in the reading of this table, both silent.
The reader locked onto the report's **list of tables**, where "Table P28" and
"Table P29" sit two lines apart, read a two-line slice and found nothing — and
the reconciliation **passed anyway**, because each of its checks loops over
the blocks and there were none to disagree with. It wrote a file and logged
success beside the line "-1 divisions in Table P28, 0 districts". Every
occurrence of a heading is now tried and the first with rows under it is the
table; emptiness is checked first and by shape.

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

*Historical: written when China carried a composition on four provinces. The
census's ethnicity tables were later read for all 31 divisions through the
copies Wikipedia keeps of them (see "China: ethnicity for 31 divisions"
below) and religion for five provinces from the CFPS survey. The three routes
measured here are still closed; what changed is that a fourth was found.*

China carried a population on all 33 of its provinces and a composition on
four. Those four -- Xinjiang, Tibet, Guangxi and Ningxia -- were **hand-compiled
rows in `data/curated/admin1_seed.json`**, which is what that file exists for.
There had never been a China adapter, and it is worth saying plainly that this
was not a broken join: the join works, 27 provinces matching by name and 5 by
prefix, and the only one that reached nothing was Guangdong, drawn under its
capital city's name and now declared in `MISSPELLED`.

So the gap was real and the question was whether it could be filled. Three
routes were measured, and all three are closed:

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

### Indonesia: what BPS's refusal left reachable, read from the provinces' own pages

Indonesia is 284 million people, 34 provinces and 518 second-level shapes on
this map, and until 19 September 2026 every one of them carried nothing. The
reason is kept below, because "unreachable" has meant four different things in
this file and only one of them was about Indonesia. On that day the owner
decided the country was to be resolved from every reachable official and
secondary source, each figure cited for what it is, and this section says what
that produced: `scripts/fetch_census/indonesia.py`, writing
`data/processed/indonesia.json`, 491 records.

**What was measured about BPS, and still holds.**

* `bps.go.id`, `www.bps.go.id` and every provincial and regency `*.bps.go.id`
  host answer **HTTP 403** to a clean client -- a deliberate block, not a
  certificate problem, and getting past it would mean claiming to be a
  browser. This project does not do that.
* `webapi.bps.go.id` works and answers `Parameter Key is Missing`: BPS's own
  sanctioned interface, wanting a free registered key that has not been
  supplied. That stays the right route the day a key exists.
* `sp2010.bps.go.id`, the 2010 census service, serves one identical 52,849-byte
  page at every URL. There is nothing behind it to read.
* `satudata.kemenag.go.id` and `data.go.id` time out. HDX carries Indonesia's
  subnational population and no religion. Kaggle's catalogue, searched on the
  runner for "indonesia ethnic", "sensus penduduk 2010 suku", "indonesia
  census", "indonesia religion", "penduduk agama kabupaten" and "indonesia
  province demographics", holds a five-accent speech corpus, a 2.8 KB
  "Indonesian Demography" file and a 1.6 KB "Religion in Indonesia" file, and
  no census table. GitHub's code search finds no mirror of the BPS tables.

**What is reachable: the Indonesian Wikipedia, through the MediaWiki API.**
Both language editions were inspected article by article (`wiki_census
--inspect`, a dozen dispatches in the branch's run-log history), and the
Indonesian one carries two things the office does not let a reader fetch.

*Ethnicity by province -- the 2010 census, transcribed.* BPS published
*Kewarganegaraan, Suku Bangsa, Agama, dan Bahasa Sehari-hari Penduduk
Indonesia: Hasil Sensus Penduduk 2010* (2011), and each province's Indonesian
article (`Sumatera Utara`, `Jawa Tengah`, `Nusa Tenggara Timur`, ...)
transcribes that province's column as a table headed "No | Suku | Jumlah 2010
| %" -- with the header written six different ways across the articles: a
count and a percentage; two censuses side by side (Jambi, Jawa Barat); the
percentages of four censuses before the 2010 count (Jakarta); a citation
falling out of the caption into a row of its own (Kalimantan Timur, Utara).
The reader finds the table by its content, reads the counts, recomputes the
shares against the table's own total, and treats the printed percentages as a
check. **32 of the 34 provinces** carry such a table, `ethnicity_year` 2010;
`Kepulauan Bangka Belitung` and `Sulawesi Barat` do not, in either edition,
and stay empty for the field with a note saying so.

The labels are BPS's and not all of them are peoples. Beside Jawa, Sunda and
Batak the census tabulates regional bundles -- "asal Sulawesi lainnya", "asal
NTT", "asal Sumatera Selatan", "Asli Papua" -- and those are carried under a
regional label (`Other Sulawesi peoples`, `East Nusa Tenggara peoples`,
`Papuan`) rather than invented into a people. The group tree places each under
the Austronesian peoples they are, and `Chinese Indonesian` under the Han and
Sinitic peoples; `Moluccan`, whose northern peoples are Papuan, is left
unplaced. One row is carried against its label: Nusa Tenggara Timur's article
prints 14.5% "asal Kalimantan", a share of Kalimantan migrants that no census
of the province supports and that is the size of the Sikka, Ende, Nagekeo and
Kedang peoples the table otherwise omits; it is kept in `Other ethnic groups`
with the article's wording in the note. Banten's article folds the census's
Bantenese into its Sunda row -- 4.66 million people nationally, nearly all of
them in Banten -- and its note says so; the national check below is how that
was found.

Tables that needed a decision have it written into the province's note in one
sentence. Riau's prints a total of 6,407,842 under rows adding to 5,499,561,
which is what the 2010 census counted (5,538,367); the rows are the
denominator. Kalimantan Tengah's, Sumatera Selatan's, Jawa Barat's,
Kalimantan Barat's and Kalimantan Timur's rows miss their printed totals by
0.3%, 0.7%, 0.1%, 0.3% and two people; the rows are the denominator there too.
Aceh's, Kepulauan Riau's and Yogyakarta's have no total row and the rows' sum
stands as one. Kalimantan Timur's table is for the province as it is since
Kalimantan Utara left it in 2012, and the two are checked against the 2010
population as a pair.

*The national check.* The English article *Ethnic groups in Indonesia*
transcribes BPS's national table (Javanese 95,217,022 of 236,728,379, 40.22%).
Summed over the 32 provinces read, the Javanese counts come to **95,107,968,
99.89% of the census figure**, the two provinces without a table accounting
for most of the rest; the run refuses below 97% and, between 97% and 99.5%,
publishes with the ratio on every province's note. Every province's shares
add to 100 within 0.3. The other large groups, logged beside their national
figures on every run: Batak 99.8%, Madurese 99.0%, Betawi 99.0%, Minangkabau
100.2%, Banjar 98.7%, Balinese 98.3%, Dayak 100.1%, Sasak 99.4%, Makassarese
97.1% -- and Sundanese 112.2% against Bantenese 1.6%, which is Banten's table
above.

*Religion by regency and province -- the infobox, and what it cites.* Each
kabupaten, kota and province article carries a religion composition in its
infobox, a percentage per faith with a citation, in one of two layouts (a
`{{ublist}}` of "98,62% [[Islam]]" items with the Christian split as a
`{{Tree list}}`, or a `<br>`-separated "[[Islam]] 70,84%" list with the split
dashed). The citation is nearly always one of four things, and the record says
which, with the year it carries: the Ministry of Home Affairs' civil-registry
visualisation (*Visualisasi Data Kependudukan*, Dukcapil, which records the
religion on every resident's identity card -- a registry count, not a census
answer), a provincial or regency BPS table of population by religion, the
Ministry of Religious Affairs' count of adherents, or the 2010 census itself
(`sp2010.bps.go.id` table 321, cited by URL although the host no longer serves
it). Where several are cited the most census-like names the source and the
latest year among them dates it; a citation with no year in its title, path
or date field dates nothing and is not read.

Read on 19 September 2026: **457 of the 513 regency shapes** (five of the 518
are water or forest polygons with no article), by kind of source: Dukcapil
registry 251, BPS table 120, 2010 census 67, other regional government 11,
Kemenag 7, the Jakarta statistics office 1; the years run from 2010 to 2026,
149 of them 2024. **32 of the 34 provinces**: Papua and Papua Barat were
divided in 2022 and their articles now describe the smaller provinces that
kept the names, so their province-level figure is not read and their
regencies' are. Not read, 56: 23 whose citation carries no year, 26 whose
figure carries no citation (eight of them a reference by a name the page
never defines), five whose faith list the reader could not parse ("Budha
danHindu", "Hindu/Buddha"), and two with no religion in the infobox
(`Flores Timur`, `Takalar`). A list that stops short of 100 carries the rest
as `Other or not stated`; one that overruns by up to three points -- ten
regencies, Bolaang Mongondow's Protestant share printed above its Christian
total -- is carried as printed with the overrun in the note, by the owner's
instruction that a small disagreement is published with a sentence rather
than refused. The 550 requests are spaced, because the runner is shared and
the API answered 429 to the first unspaced run.

*Language* is not written. The 2010 volume's "bahasa sehari-hari" by province
is transcribed nowhere this reader can reach; the Indonesian *Demografi
Indonesia* carries the national column only (Javanese 68.0 million, Indonesian
42.7, Sundanese 32.4), and the four-bucket language-type tables the owner
supplied on 11 September remain what they were, a kind of language and not a
language.

**What this is and is not.** The ethnicity is a census count, transcribed.
The religion is a real composition on every row it is written, but of mixed
kind and vintage -- the 2010 census on 67 regencies, a 2014-2026 registry or
statistical table on the rest -- and each row's `religion_year` and two- or
three-sentence note say which. Nothing here is a model. What would still
improve it: the WebAPI key, which would replace 457 transcriptions with BPS's
own *Jumlah Penduduk Menurut Kabupaten/Kota dan Agama* series in one vintage.

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
breakdown. Religion by regency and ethnicity by province came from the
provinces' own Wikipedia articles instead, on 19 September 2026 (see
*Indonesia: what BPS's refusal left reachable*); BPS's own series still needs
the key.

### Viet Nam: collected, published by province in the Vietnamese volume, and read from it

Viet Nam's 2019 Population and Housing Census asked religion. Its questionnaire,
reproduced on page 330 of the English results volume, puts it plainly:

> 7. Does [NAME] follow any faith/religion? IF YES: What is [NAME]'s
> faith/religion?

And it asked ethnicity, in the question above it. An earlier pass of this
project read the English volume and concluded that the office publishes both
counts for the country and not for its provinces. That was true of the English
volume and wrong about the census, and this entry keeps the record of both.

**The English volume, and what it showed.** The statistics office did not
answer this project from a GitHub runner in early September 2026 --
`www.gso.gov.vn` timed out, `www.nso.gov.vn` (the office was restructured into a
National Statistics Office in 2025) reset the connection -- and the English
`Results - 2019 Population and Housing Census_full.pdf` (380 pages, 6.8 MB) was
read from UNFPA, the census's technical partner and the body named on its title
page. In it, Table 2 (ethnic group) and Table 3 (religion) are national, and
Table 5, whose caption reads "BY AGE GROUP, SEX, ETHNIC, URBAN, RURAL,
SOCIO-ECONOMIC REGION AND PROVINCE, CITY", stacks an ethnic-group block and a
province block under the same age columns rather than crossing them. That
reading stands: the English volume prints no ethnic group by province.

**What changed on 19 September 2026.** The owner decided that Viet Nam's
provincial ethnicity was to be read from whichever route yields it -- the
office's own files, a Kaggle dataset, or the Vietnamese Wikipedia's
transcription, in that order, secondary sources included and named as such.
`scripts/fetch_census/vietnam.py --probe` asked all three in one runner
dispatch, and the log of each is committed on the branch:

* `www.gso.gov.vn` no longer resolves at all (*Name or service not known*).
  `www.nso.gov.vn` now answers a plain client with 200, where it reset the
  socket two weeks earlier, and its WordPress uploads keep the old paths.
  `tongdieutradanso.vn`, the census's own site, answers a 444-byte stub.
* Kaggle's catalogue, searched with the owner's token, lists nothing for Viet
  Nam under "vietnam census", "vietnam ethnic", "vietnam population province",
  "vietnam religion", "dân tộc" or "tổng điều tra dân số" -- every hit is the
  1994 US adult-income set, a real-estate scrape, or the CIA Factbook.
* The Vietnamese Wikipedia's province articles carry 2009 prose ("tính đến ngày
  1 tháng 4 năm 2009 ... dân tộc Kinh chiếm đông nhất với 1.161.533 người") and
  no 2019 table; "Các dân tộc Việt Nam" holds the national 2019 table with, per
  group, its three or four largest provinces, which is not a composition of any
  province. But the article for Điện Biên cites, for "dân tộc Mông ... 228.279
  người, chiếm 38,1%", the URL of the *Vietnamese* results volume on
  gso.gov.vn. That citation is what said the table existed.

**The Vietnamese volume.** "Kết quả toàn bộ Tổng điều tra dân số và nhà ở năm
2019" (Nhà xuất bản Thống kê, 2020; 842 pages, 9.5 MB) is at
`https://www.nso.gov.vn/wp-content/uploads/2019/12/Ket-qua-toan-bo-Tong-dieu-tra-dan-so-va-nha-o-2019.pdf`,
the same path the citation gave on the old host. Its contents page settles
what the English one left open:

| Biểu / Table | Breakdown | Pages |
| --- | --- | --- |
| 2 | Dân số theo dân tộc, thành thị/nông thôn, giới tính, vùng kinh tế - xã hội **và tỉnh/thành phố** -- population by ethnic group, urban/rural, sex, socio-economic region **and province/city** | 43-209 |
| 3 | Dân số theo tôn giáo, thành thị/nông thôn, giới tính -- population by religion, urban/rural, sex; **national** | 210 |

Table 2 is nested, not crossed: the country, then each of the six regions,
then each of the 63 provinces, and under every unit all 54 groups in the
office's order (Kinh, Tày, Thái, Hoa, Khmer, Mường, Nùng, Mông, Dao, Gia Rai,
Ngái, Ê Đê, Ba Na, Xơ Đăng, Sán Chay, Cơ Ho, Chăm, Sán Dìu, Hrê, Mnông, Raglay,
Xtiêng, Bru Vân Kiều, Thổ, Giáy, Cơ Tu, Gié Triêng, Mạ, Khơ Mú, Co, Tà Ôi,
Chơ Ro, Kháng, Xinh Mun, Hà Nhì, Chu Ru, Lào, La Chí, La Ha, Phù Lá, La Hủ,
Lự, Lô Lô, Chứt, Mảng, Pà Thẻn, Cơ Lao, Cống, Bố Y, Si La, Pu Péo, Brâu, Ơ Đu,
Rơ Măm), then "Người nước ngoài" (foreign nationals) and "Không xác định"
(undetermined). A first scan of the volume, which looked for a minority named
beside three provinces on one page, found nothing, because a page of a nested
table names one province and fifty rows; the second scan, which looked for
many ethnonyms beside any one province, found 79 such pages. The word
"religion" leads to Table 3 alone, so **religion stays unwritten** for the
provinces: it was collected, and it is published for the country only.

**Reading it.** The volume prints a space as the thousands separator, and the
narrative pages of the English edition extract as mojibake; these table pages
extract cleanly through pypdf, with the row label first and then its figures.
Every row carries nine: Total, Male and Female for the whole, the urban and the
rural population. The reader tries every split of a row's digit groups into
nine numbers and keeps the one where Male plus Female equals Total three times
over and urban plus rural equals the whole -- the constraint this entry banked
in September for exactly this table, taken from `south_africa.py`. A row with
no single such reading refuses the run. Units are told from groups by name:
the volume prints its country and regions bilingually ("TOÀN QUỐC - ENTIRE
COUNTRY", "Đồng bằng sông Hồng - Red River Delta"), which cost one refused run
before either half was accepted, and the first page's heading "Biểu - Table 2"
cost another, its trailing digit having been read as a one-figure row.

The checks it passes, each of which would have refused the run: the rows under
every one of the 70 units add to the unit's printed total; the 63 provinces add
to 96,208,984 people and 82,085,826 Kinh, the published national figures, to
the person, and the volume's own national row agrees; every province is read
once. Điện Biên comes out at Mông 228,279 (38.1%), the figure the Wikipedia
article cited from this volume.

**What is written.** `data/processed/vietnam_province.json`: for each of the 63
provinces the population and sex ratio from the unit row, and an ethnicity
composition with counts -- every group at 0.05% of the province or more, and
"Other ethnic groups" for the rest together with foreign nationals and the
undetermined, shares re-rounded to one decimal so each province adds to exactly
100. The map draws 64 shapes for Viet Nam; the sixty-fourth is Côn Đảo, the
island district of Bà Rịa–Vũng Tàu that the boundary file separates, and no
row of the volume is for it, so it stays a gap by design. Every one of the 54
groups is placed in the ethnicity tree under "Mainland Southeast Asian peoples"
except the Hoa and the Ngái, who are Viet Nam's Han and Hakka-speaking Chinese
and sit with the Sinitic peoples. Several had to be named there explicitly
because the tree's shape rules read them as something else: Thái as the Thai
nationality, Gia Rai as the Himalayan Rai, Sán Chay and Sán Dìu as the San of
the Kalahari, Cờ Lao as Lao, Rơ Măm as a Mesoamerican Mam.

The 53-minorities survey of 2019 ("Kết quả điều tra thu thập thông tin về thực
trạng kinh tế - xã hội của 53 dân tộc thiểu số năm 2019", GSO with the
Committee for Ethnic Minority Affairs) is on the same host and was also
reached; its first file is the 103-page narrative volume, its tables are by
group and region rather than by province, and nothing was read from it.

### Timor-Leste: two questions asked, a third that is not, and a census ten years apart from its own population

Timor-Leste carried nothing on any of its 13 municipalities or 65
administrative posts: every field on every unit a bare `not_available`, and the
country row itself had no ethnicity at all. It now carries mother tongue and
religion on all 13 municipalities, a population on those and on the
administrative posts, and an ethnicity that is a sourced declaration rather
than a blank -- at the country level and at every level below it.

**The office answers.** `inetl-ip.gov.tl` -- the Instituto Nacional de
Estatística de Timor-Leste, the Direção-Geral de Estatística until 2022 --
served a plain client 200 on every request this work made, and the files are
its own. `statistics.gov.tl`, the host the older literature cites, no longer
resolves (*Temporary failure in name resolution*). The one thing that did not
answer is INETL's own **REDATAM population dashboard**, linked from every page
of the site as `http://20.6.104.113/redatam/` -- a bare address over plain HTTP,
which timed out on the runner. That matters because REDATAM tabulates the
microdata to any geography, and it is the only route that would have put
religion or mother tongue on an administrative post.

**The 2022 census asked both questions and has published neither below the
country.** Its questionnaire is reproduced in full as Annex III of the main
report (`Final-Main-Report_TLPHC-Census_WEB.pdf`, 204 pages), and the two
questions sit next to each other:

> **E 57 Religion.** What is \<Name\>'s religion?
> 01 Christianity - Catholicism / 02 Christianity - Protestantism /
> Evangelicalism / 03 Islam / 04 Buddhism / 05 Hinduism / 06 Indigenous
> religion / 07 Other / 08 No religion / 09 No answer
>
> **E 58 Mother tongues.** What languages did \<Name\> learn as a child?
> *Select at least one and no more than two languages from the list.*

What the 2022 round published of them is one table: basic table 4.07, religion
by five-year age group and sex, **for the country**. Its 24 basic tables include
no mother-tongue table at any geography, and the census's thematic reports so
far are education, labour force, mortality, fertility, migration, population
projection, disability, gender, and children and youth. So the newest published
composition for any Timorese municipality is the 2015 one, and that is what the
map carries, stamped 2015.

**Ethnicity: measured, and declared.** The task was to settle whether the census
asks it at all. It does not. The individual module of the 2022 questionnaire
runs from E1 to E77 without a break -- member providing information, place on
census night, marital status, parents, birth registration, country and
municipality of birth, internal migration, first and second citizenship,
literacy, education, labour force, religion, mother tongues, the six Washington
Group disability questions, children ever born, birth attendance -- and not one
of the 77 asks ethnicity, race, tribe or ancestry. Timor-Leste is therefore in
`NOT_COLLECTED_POLICY`, which fixes the country row and propagates to every
unit below it.

The Factbook's Timor-Leste "Ethnic groups" line, which the country row used to
hold as a note beside an empty field, reads "Austronesian (Malayo-Polynesian)
(includes Tetun, Mambai, Tokodede, Galoli, Kemak, Baikeno), Melanesian-Papuan
(includes Bunak, Fataluku, Bakasai), small Chinese minority". That is the
census's mother-tongue list sorted into two language families, with no shares
attached to either. The map carries those tongues, counted, on the language
field, which is the question that was actually asked; publishing the same
division again under ethnicity is the relabelling this project refuses for
Pakistan and refuses here.

**The two 2015 tables.** Volume 2 of the 2015 census is published as a numbered
series of priority tables, one workbook each, from the office's Census
Population page:

| File | Sheet | Table |
| --- | --- | --- |
| `4_2015-V2-Language.xls` | `2.12` | Table 12, population by mother tongue, urban/rural location **and municipality** |
| `3_2015-V2-Nationality-Citizenship-Religion.xls` | `2.11` | Table 11, population by religion, urban/rural location, **municipality** and sex |
| `1_2015-V2-Population-Household-Distribution.xls` | `2.1.a` | Table 1.a, total population and private households by municipality |
| `7_2015-V2-Aldeia-populations.xls` | `2.20a`-`2.20m` | Table 20, every administrative post, suco and aldeia, one sheet per municipality |

Table 12 puts 38 mother tongues down the side and the country, urban, rural and
the 13 municipalities across the top: Tetun Prasa, Tetun Terik, Adabe, Atauran,
Baikenu, Bekais, Bunak, Dadu'a, Fataluku, Galoli, Habun, Idalaka, Idate, Isni,
Kairui, Kawaimina, Kemak, Lakalei, Lolein, Makalero, Sa'ani, Makasai, Makuva,
Mambai, Midiki, Nanaek, Naueti, Rahesuk, Raklungu, Resuk, Tokodede, Waima'a,
and then Portuguese, Indonesian, English, Malay, Chinese and Other. Every
municipality's 38 rows add to its own column total to the person, so in 2015
the question took one answer per person and the table is a partition -- which
the 2022 question, allowing two answers, would not be.

Table 11 stacks its units instead: the country, urban and rural, then each
municipality, each followed by a male and a female row, against Catholicism,
Protestantism/Evangelicalism, Islam, Buddhism, Hinduism, Traditional and Other.
There is no "no religion" and no "not stated" column, so those answers are
inside "Other", which is why "Other religion" is published here as a religion
and not as a residual.

**Reading them.** Both sheets are legacy `.xls` and both do two things a reader
has to survive. They print a column-numbering row -- `-1.0`, `-2.0`, `-3.0` --
whose every cell is a number under a label that is also a number, so nothing but
the absence of a letter tells it from a row of figures. And they stack headers:
table 11 writes "Municipality, urban/rural location, sex | Total | Religion"
over the seven religion names, so the Total column is headed a row above the
religions, and the first run refused on not finding it there. The religion
columns are matched by what their heading starts with once folded, because the
sheet breaks the second one across a line as "Protestantism/ Evangelicalism".
The exclave is "SAR1 of Oecusse" in one workbook and "SAR1 OF OECUSSE" in the
other, the 1 being a footnote marker, so the name fold drops digits as well as
case and accents; Lautém is "Lautem" in one and "LAUTÉM" in the other.

**What the self-checks found.** Every one of them passed, and each would have
refused the run:

* the 38 mother tongues of each of the 13 municipalities add to that
  municipality's own printed total, to the person;
* the seven religions of each municipality add to its own printed total, the 13
  municipalities add to the country row's 1,179,654, and every religion column
  adds to the country row's figure for it, all to the person;
* the two tables count the same people municipality by municipality, so the
  religion and the language shares on a unit are shares of one population;
* **against the office's own published figures**: Catholicism comes out at
  97.57% of the country where the 2022 main report says Catholicism "was
  reported for 97.6" percent of the population in 2015; and all fourteen of the
  named mother tongues in the map's own country row -- Tetun Prasa 30.6, Mambai
  16.6, Makasai 10.5, Tetun Terik 6.1, Baikenu 5.9, Kemak 5.8, Bunak 5.5,
  Tokodede 4.0, Fataluku 3.5, Waima'a 1.8, Galoli 1.4, Naueti 1.4, Idate 1.2,
  Midiki 1.2 -- are reproduced from this table to within a rounding step. The
  country row's language list *is* this table's national column, so the
  municipalities and the country now agree because they are the same census;
* the 2022 population table's 14 municipalities add to 1,341,737, the published
  national figure, and its 67 administrative posts each add to the municipality
  they sit in.

**The base is 1,179,654, and the volume does not say why.** Tables 11 and 12
both count 1,179,654 people. The same volume's table 1 counts 1,183,643 in
total and 1,178,340 in private households, so the base of the two composition
tables sits between the two -- 3,989 below the census's whole population and
1,314 above its private-household population -- and neither workbook prints a
footnote saying which people it leaves out. The difference is 0.34% of the
country and is spread across all 13 municipalities rather than sitting in one,
so it is stated rather than explained away. Each municipality's own base is in
its notes.

**Population comes from the 2022 census, and Atauro is why that needs saying.**
The main report's basic table 4.01 gives the population of every municipality,
administrative post and suco in 2022, with a label column per level, and it is
the only table in either round that reaches below the municipality. It counts
**14** municipalities: Atauro, an island that was an administrative post of
Dili, became a municipality of its own in 2022. The boundary file draws the 13
of 2015, so the figure written on Dili is Dili's 324,738 plus Atauro's 10,295 --
a sum of two published counts over a division the census itself states, not an
apportionment -- and Dili's population note says so. Atauro's administrative
post is written under Dili for the same reason. The 2015 compositions need no
such treatment: in 2015 Atauro was inside Dili and its people are in Dili's
column already.

**67 posts against 65.** `scripts/fetch_census/timor.py --probe` is the
reconnaissance that settled this, and its log is on the branch. It reads the
2015 volume's table 20 -- which puts administrative post, suco and aldeia in
one column and marks the level by indentation, the one mark a reader should not
trust -- and recovers the levels from the arithmetic instead, each unit's count
being the sum of the units beneath it. Comparing that with basic table 4.01
suco by suco: two municipalities were re-divided. Ermera's **Hatulia** is
**Hatulia A** and **Hatulia B**, whose eight and five sucos are the old post's
twelve with Hatulia Vila spelled Hatolia Vila. **Lautém** has six posts where it
had five, the new one being **Lore**. Ainaro's Hato-Builico is spelled
Hato-Buiico in 2022 and is otherwise the same three sucos.

The rows written are the 67 the 2022 census names, not a re-division of them.
A row that finds no shape is a gap the coordinator sees; a row silently joined
to a shape covering different ground is the mis-match this project treats as
worse, so every administrative post of Ermera and of Lautém carries a sentence
in its population note saying that the 2022 division is not the 2015 one.

**What each unit carries.** `data/processed/timor.json`:

* **13 municipalities** -- mother tongue and religion from 2015 with counts and
  shares, a 2022 population, and the ethnicity declaration. Oecusse is 98.1%
  Baikenu, Lautém 60.9% Fataluku, Baucau 60.3% Makasai, Liquiçá 64.0% Tokodede,
  Cova Lima 48.0% Bunak, Manatuto 29.9% Galoli, and Dili 82.5% Tetun Prasa;
  Mambai leads Aileu, Ainaro, Ermera and Manufahi, Kemak leads Bobonaro and
  Makasai leads Viqueque. That regional pattern is what the map had nothing of
  for this country. Catholicism runs from 92.1% in Aileu to 99.7% in Bobonaro.
* **67 administrative posts** -- the 2022 population, and religion and mother
  tongue as gaps that say what was asked of which source: no census publishes
  either below the municipality, and the dashboard that would have is
  unreachable.

A mother tongue spoken by under 0.05% of a municipality is counted in that
municipality's base and given no row of its own, so a municipality's shares add
to a shade under 100 rather than to a residual row that would mean something
different from the census's own "Other" column, which is published.

**The group tree.** The 2015 list is the whole language inventory of the
country, and Timor-Leste's split between Austronesian and Papuan is settled, so
`scripts/group_tree.py` gains Adabe under **Papuan languages** beside Bunak,
Fataluku, Makasai and Makalero, and Atauran, Bekais, Dadu'a, Habun, Idalaka,
Isni, Kairui, Kawaimina, Lakalei, Lolein, Makuva, Nanaek, Rahesuk, Raklungu and
Resuk under **Malayo-Polynesian languages** beside the twelve already there.
One label is deliberately left unplaced: **Sa'ani**, which the census names and
which the literature does not settle on one side of that split or the other. It
leads no unit anywhere, so nothing is drawn in the unclassified colour for it;
asserting a family for it would be a guess with nothing behind it, and this
entry would rather carry one unplaced label than one invented classification.

### Lao PDR: a census published only for the country, and its own village file

Laos carried nothing below the country: 18 provinces and 148 districts, every
one of them a bare `not_available` on all three fields, while the country row
had the Factbook's figures — which for Laos are the 2015 census's, Lao 53.2%
and Buddhist 64.7%.

**What the results volume publishes, and what it does not.** The 4th
Population and Housing Census was taken in March 2015 under Prime Ministerial
Decree 89/PM; its questionnaire ran to 63 questions in 10 parts, and two of
them were ethnicity (the 49 officially recognised groups) and religion. The
Lao Statistics Bureau's English results volume, *Results of Population and
Housing Census 2015* (282 pages), is not on `lsb.gov.la` — which serves a
WordPress home page in Lao with no file links and answers 404 to
`/wp-json/wp/v2/media` — but is on UNFPA Laos, the census's technical partner,
at `lao.unfpa.org/sites/default/files/pub-pdf/PHC-ENG-FNAL-WEB_0.pdf`, 5.3 MB.
Reading it settles the question the country row raises:

| Table | Breakdown | Page |
| --- | --- | --- |
| 3.4 | Population by ethnic group — Lao 3,427,665 (53.2%), Khmou, Hmong, … | 37 |
| 3.5 | Population by religion — Buddhist 4,201,993 (64.7%), Christian, … | 37 |
| P2.7 | Total Lao citizen population by sex and **ethnicity**, all 49 groups | 121-122 |
| P2.9 | Total population by sex and **religion**, six categories | 123 |

All four are national. The volume's other appendix tables do cross province —
with age, migration, literacy, schooling, economic activity, disability and
housing, thirty of them — and not once with ethnicity or religion. So the
first reading of Laos is the one Viet Nam's entry describes for its English
volume: collected, and published for the country only.

**The route that answers.** `scripts/fetch_census/laos.py --probe` asked the
other places such a table might be, and the log of each is committed on the
branch. `laosis.lsb.gov.la`, the Bureau's statistics portal, fails
verification with *unable to get local issuer certificate* and then, with the
intermediate its server omits supplied from the certificate's own AIA
extension, with *DH_KEY_TOO_SMALL* — a handshake no current client will
complete, and not something to be worked around. `decide.la` serves a
certificate that is not valid for its own hostname. HDX has WorldPop rasters,
the World Bank's indicator series and UNICEF's equity analysis, and no
composition. What answers is **Open Development Laos**, the CKAN portal that
carries LSB's own releases: the national open-data portal this project has
learned to try early, the way Singapore was solved after `singstat.gov.sg`
answered 403.

Its dataset `lao-population-and-housing-census-2015-general-demographic` is
the census's **village indicator table**: one row for each of 8,499 villages,
75 columns, 4.5 MB, with a `Meta` sheet that names every column in Lao and
English and gives the source as "Lao Population and Housing Census 2015" and
the data owner as the Lao Statistics Bureau. Beside the province, district and
village names in both scripts and the village's total population, it carries
ten ethno-linguistic categories and five religions, each as a percentage of
that village's people:

* `u_eth_cat_lao_pct` … `u_eth_cat_mien_pct` — Lao, Tai-Thay, Khmuic,
  Palaungic, Katuic, Bahnaric-Khmer, Vietic, Tibeto-Burman, Hmong, Mien;
* `u_pop_buddhist_pct`, `u_pop_christian_pct`, `u_pop_bahai_pct`,
  `u_pop_muslim_pct`, `u_pop_religion_other_pct`.

**How it is read.** A percentage of a village is turned back into people by
that village's own published population — the one figure in the table that is
a count — and those counts are summed over the villages of each district and
each province, the shares then recomputed against the unit's total and
re-rounded by largest remainder so every unit adds to exactly 100. The sex
ratio is handled the same way and for the same reason: a village's ratio is
men per hundred women, so its two halves follow from it and the population,
and the halves are summed rather than the ratios averaged.

**What the residual holds.** Neither set of columns reaches 100, and the two
gaps are different things, so each is one named row.

* `Other or not stated` — what the ten categories leave. Nationally 1.8%,
  against the volume's 1.2% "other and not stated" plus 0.7% foreign
  population.
* `No religion or not stated` — what the five religions leave, 33.3%
  nationally. This one is a third of the country and needs its sentence: the
  census counts a religion only where it has written doctrines, so the animist
  beliefs of most non-Lao-Tai people — the *Satsana Phi*, the "religion of
  spirits" — are not among the five and are recorded here, beside the 1.8% who
  stated nothing. The census publishes 31.4% "no religion" and 1.8% "not
  stated" for the country, which is this row's 33.3% to a tenth. The label is
  the Socio-Economic Atlas's own wording for it, and the group tree files it
  under "Not stated", beside the other labels that weld a real answer to a
  non-answer, because colouring a third of Laos "no religion" would answer a
  question nobody was asked.

Both residuals are named in `RESIDUAL` in `scripts/canonical_groups.py`, which
is what stops either leading a unit. That is not a formality here: the
religion residual is the largest row in nine of the 18 provinces and in half
the districts — 53.5% of Xiangkhouang against Buddhism's 44.6% — so without it
the map would have shaded a third of the country for the absence of an answer
and called it the province's religion.

**The one disagreement, and where it comes from.** Summed over the villages,
the Lao category is **43.7%** of the country where the volume's Table 3.4
prints the Lao ethnic group at **53.2%**. That is not an arithmetic error and
it was worth chasing: the ten categories are defined in Table 1 of the
*Socio-Economic Atlas of the Lao PDR 2015* (LSB with the Centre for
Development and Environment of the University of Bern, 123 pages, on the same
portal), which is the publication this village table underlies, and its
"Tai-Thay" category is *Phou Thay; Tai; Nyouan; Lue; Yang; Sek; Tai Neua; and
Lao in Huaphanh, Xiengkhuang, Borikhamxay, Vientiane province and Hinboun
district of Khammuane*. The Lao of those five areas are counted as Tai-Thay,
which is the missing 9.5 points exactly; Lao 43.7% plus Tai-Thay 18.3% is the
volume's Lao-Tai family, 62.4%. So the adapter checks at the family level, and
logs both figures on every run so the difference stays on the record. Every
row's note says it too, because a reader who knows the Factbook's "Lao 53.2%"
would otherwise read the map as contradicting it.

**The checks, each of which refuses the run rather than writing.** The 8,499
villages add to 6,481,625 people, 0.16% under the census's published
6,492,228 — the table is the household population and the census total
includes the institutional one. The sex ratio comes to 995.7 females per 1,000
males against the published 994.7 (3,237,458 women to 3,254,770 men); that
check is also what would catch the workbook's ratio being the other way up,
since a reversed reading gives 1,005.3 and fails. The four ethno-linguistic
families come to Lao-Tai 62.0, Mon-Khmer 23.6, Hmong-Mien 9.7 and
Chinese-Tibetan 2.9 against the volume's summary page 62.4 / 23.7 / 9.7 / 2.9;
religion to Buddhist 64.7, Christian 1.7 and the residual 33.3 against 64.7 /
1.7 / 33.2. Every province must be read, and the districts may not hold more
people than their provinces do.

**Names.** The record carries the boundary file's own spelling, because the
boundary file's 148 district names are the list a census name is placed
against — a match is an identity, not a nearest neighbour. Seventeen of the 18
province names agree after the diacritics are folded away; the workbook writes
Xaignabouli as "Xaignabouly". The two Vientianes are settled by a table of
their own and by nothing loose: the capital is recognised by its qualifier,
only a bare "Vientiane" is the province, and any other label beginning with
the word is refused. That is not caution for its own sake —
`scripts/build_entities.py` records the time Vientiane took Vientiane
Province's 388,833 people over the prefecture's, which is the mis-match this
project ranks below a gap. Seven district names romanise differently in the
two files: Houaphan's Hiem/Huim, Kuan/Kuane and Xon/Sone, Khammouane's
Nakay/Nakai, Phongsaly's Boontay/Boontai, Xiangkhouang's Mork/Morkmay and
Phookood/Phoukoud. Each is declared as an alias rather than matched loosely,
and each is an identity rather than a guess: in every one of those four
provinces the number of census names the fold could not place equals the
number of shapes left without a village, so the correspondence is forced.

**What is written.** `data/processed/laos_province.json` (18 provinces) and
`laos_district.json` (148 districts), each row with population, sex ratio, an
ethnicity composition and a religion composition, all `_year` 2015. Every one
of the 148 district shapes is filled. The leading category is Lao in seven
provinces — 90.1% of Vientiane Capital, 84.7% of Champasak — Tai-Thay in four,
Khmuic in three (59.1% of Oudomxay), Bahnaric-Khmer in Attapeu and Xekong,
Tibeto-Burman in Luang Namtha and Phongsaly, and Hmong in Xaisomboun. Nine of
the ten categories are placed in the ethnicity tree under "Mainland Southeast
Asian peoples" and the tenth, Tibeto-Burman, under "Himalayan and
Tibeto-Burman peoples" beside the Akha and Lahu it is made of; each is named
there rather than left to the word rules, which read "Tai-Thay" through "Tai"
and "Bahnaric-Khmer" through "Khmer" — right by luck — and reach Khmuic,
Palaungic, Katuic and Vietic not at all.

**Language is declared rather than left blank.** See *Laos: 282 pages, and no
language question* under Collection policy.

**What was measured and left.** The 5th Population and Housing Census was
taken in 2025 and UNFPA Laos has published six briefs about it; no results
volume and no table of either field has appeared, so 2015 remains the census
on the map. The Lao Social Indicator Survey II (2017) and III (2023) are the
MICS rounds and both tabulate by province; neither was read, because a census
count at village level is the better answer and was reached first. The Atlas's
2005 half was not read either: this project carries one vintage per unit, and
2015 is the later one.

### Mongolia: a statistical office that has moved, and 22 books on the Internet Archive

Mongolia's 2020 Population and Housing Census asked ethnic group of every
Mongolian citizen -- 33 groups where 2010 had 29 -- and asked religion, at
question 29 of the individual form, of the ten per cent of households that
got the long questionnaire. Before this it carried nothing on any of its 22
aimags and nothing on any of its 339 soums: every field on every unit was a
bare `not_available`, and the country row's Khalkh 83.8% and Buddhist 51.8%
came from the Factbook.

**The office's own database is gone.** `opendata.1212.mn`, the API the CRAN
package NSO1212 is written against and the thing this task was pointed at
first, no longer resolves at all. Nor does the rest of the old estate:

| Host | What it answers now |
| --- | --- |
| `opendata.1212.mn` | *Name or service not known* |
| `web.nso.mn` (the NADA microdata catalogue) | connection refused |
| `www2.1212.mn` | HTTPS with a certificate that expired |
| `www2.1212.mn` over plain HTTP | 200, and a body of zero bytes |
| `nso.mn`, `www.1212.mn`, `data.nso.mn`, `metadata.nso.mn` | 200, and one Next.js application between them |

The live hosts are reachable but carry nothing an automated reader can take:
`nso.mn` and `www.1212.mn` serve the same single-page application, whose
client bundle names no API at all because its pages are rendered on the
server; `data.nso.mn` is the Ministry of Digital Development's "Data Nation"
warehouse and answers `/api/...` with its own 404 page. Every `*.nso.mn` and
`*.1212.mn` host also sends its leaf certificate without the Sectigo
intermediate above it, so a plain urllib client fails them with *unable to
get local issuer certificate*; `common.http_get(..., aia=True)` completes
the chain from the certificate's own AIA extension and verifies, which is
what the probe uses. None of this is a refusal of automated readers -- it is
a site that has been replaced -- and it is written down rather than worked
around.

**What the office published, and where it survives.** Beside the national
report, the NSO published a results book for each of the 21 aimags and the
capital: *"<aimag> аймгийн хүн ам, орон сууцны 2020 оны улсын тооллогын
НЭГДСЭН ДҮН"*, written by that aimag's own statistics department, chapter
three of every one being "Улсын харьяалал, үндэс угсаа, шашин". They were
served by an ASP.NET handler, `1212.mn/BookLibraryDownload.ashx?url=<file>&ln=Mn`,
and the Internet Archive has all 22, the way it has Romania's 2011 census
(*Romania — the census read through the Internet Archive*). One CDX query
lists every capture of every book and `--fetch` takes the largest, because
the Archive stored several of them twice -- once whole and once truncated at
exactly 1,048,576 bytes, a download cut off at one mebibyte, which opens as
a PDF of no pages. Where the largest capture is itself half-written or the
Archive answers 503 for it, the next one down is tried.

Two books are not under the XAOCT stem the other twenty share and were found
by name: `dundgovi.pdf` and `Khentii.pdf`. `Khentii.pdf` turns out to be that
aimag's **2010** book, typeset in a legacy Mongolian codepage that extracts as
Latin-1 mojibake ("Õ¯Í ÀÌ, ÎÐÎÍ ÑÓÓÖÍÛ 2010 ÎÍÛ"); it is rejected by the
test that a book must name 2020 somewhere. The only other Khentii candidate
the Archive holds, `18._Khentii.pdf`, names neither ethnic group nor religion
on any of its pages, so Khentii's 2020 book is not there under any name this
project searched. `dundgovi.pdf` is 34 MB of scanned image
with only its running heads in the text layer.

`--fetch` keeps the pages of each book that name ethnic group, religion or
the sex ratio and writes them to `data/raw/mongolia/`, so a build without
network still runs and what was read is committed beside the code that read
it. Each word is written with the span it occupies on the page, the way
`probe_pdf --boxes` does, because these books write a thousands separator as
a space: "Хэрлэн сум 46 192 37 611 49 173" is eight numbers or twelve and
only the gaps say which -- the space inside a number is two or three points
wide where the gap between two columns is ten or more.

**The aimags' ethnicity is not from the books.** Appendix Table 3.6 of the
English national report, *"Percentage distribution of population, by
ethnicity, and aimags and the capital, region, 2020"*, gives all 22 units
over 26 ethnic groups in the office's own English spellings, printed in three
column blocks with the transposed Table 3.6a interleaved between them. It is
read from the same Archive. Blocks one and two carry a clean header line and
the reader checks the names against the ones it expects; the third's header
is broken across three baselines -- "Tsaatan", "Uzbek" and "groups /" sit
above "Eljigen Sartuul Tuva Khamnigan Khoshuud Other" -- so its column order
is declared, and the check that it is right is that every aimag's 26 shares
then add to exactly 100 and each group's largest aimag share exceeds its
national one.

**The aimags' religion is from the books.** Chapter three of each prints two
tables: the share of the population aged 15 and over who follow a religion at
all, and the breakdown of those who do. The composition written here is the
first split by the second. Eighteen of the 22 were read. The four that were
not are not a shrug:

* **Darkhan-Uul** -- the book is whole and its chapter-three tables are
  images. Its 558 kept lines contain no row of five figures at all.
* **Dundgovi** -- the only capture that opens is the scan.
* **Khentii** -- no 2020 book.
* **Khovd** -- the book prints the breakdown of the religious population
  (Buddhist 81.3%, Muslim 13.6%) and this reader could not find, on any page
  it kept, the published share who follow a religion; the narrative says
  60.6% and putting a sentence's number where a table's should go is not
  something this file does.

**Which soums the census published, and in three different shapes.** Most of
the 22 books print a table of ethnic group by soum and no two departments
agreed how. Some give each soum's own composition in percentages; some give
counts; and some give the *distribution of each ethnic group across the
soums*, a table whose columns add to 100 and not its rows. The third is still
a composition once each column is weighted by the aimag's own group shares
from Appendix Table 3.6, and the note on those soums says the figure is
derived rather than transcribed. Each shape is told by its own arithmetic --
rows opening at exactly 100.0, columns adding to the unit's own line, columns
adding to 100 -- and a block whose arithmetic fits none of them is not read.

Two things about these pages cost several readings before they were right,
and both are in the tests:

* **The headings are set in fragments.** Sükhbaatar prints "Дарь-" and
  "Уриан-" on the line above the header and "ганга" and "хай" on the line
  below, so the line that looks like the header names six groups where the
  table has eight columns; a reader that trusts it hands every group the
  column to its left, and Dariganga's 39% of the aimag is written as
  Zakhchin's. The header is therefore assembled from the words of the lines
  around it, grouped by the space each occupies across the page and joined in
  reading order, which recovers those two names and Khuvsgul's four-line
  "Хөвсгөл аймгийн харьяат-Бүгд".
* **Whether there is a total column in front of the groups** is a question
  about where the figures sit, not about the header: Dornod's second block
  reads fourteen rows at either width, and the wrong one silently shifts
  Barga and Uzemchin by one. It is settled by asking whether a row's first
  figure begins to the left of the first group's heading.

**Every soum table is then checked against a different document.** Where a
book prints its aimag's own line, that line must be the composition Appendix
Table 3.6 gives, group by group, to within a fifth of the group; where it
prints each group's distribution over the soums, weighting that by the
report's shares must reproduce the book's own column of each soum's share of
the aimag. Khovd's table fails it -- the reader makes the aimag 39.5% Khalkh
where the report has 29.8% -- and Khovd's seventeen soums are left unwritten
with that sentence as their reason, because a composition read one column out
of step is worse than none.

**Joining a soum to a shape.** The boundary file romanises Mongolian in a
scheme of its own, and not consistently: "Adaacag", "Aldarxaan",
"Altanco'gc", "Bor-Ondor" against "O'ndor-Ulaan", "Herlen" in Dornod against
"Xerlen" in Khentii, "Saintsagaan" against "Cagaandelger", "Xalx gol" and
"Zamyn U'ud" where the name is one word. Names are compared on a folded key
that both sides reduce to: apostrophes, hyphens and spaces dropped, kh and h
read as x, ts and ch as c, sh as s, y as i. Doubled vowels are kept, because
Khuvsgul has both Цагааннуур and Цагаан-Уур and collapsing them would make
one name of two soums. Three aimags have a soum called Altai and every match
is made inside one aimag, so none of the three is ambiguous. One row was left
unwritten by name: Zavkhan's book prints Их-Уул twice, once as "Ихуул", and
the second row for a shape already written is refused rather than merged.

**What the self-checks found.** Appendix Table 3.6 reads for all 22 aimags
and each one's 26 shares add to exactly 100. Khovd comes out Khalkh 28.1%,
Zakhchin 25.3%, Kazakh 11.2%, Uriankhai 8.3%, Torguud 7.4%, Durvud 6.5%,
which is the report's own sentence about Khovd to the tenth. Bayan-Ölgii --
the aimag that looks nothing like the country, and the reason to check --
comes out **Kazakh 91.0%, Uriankhai 5.6%, Durvud 0.9%, Khalkh 0.9%, Tuva
0.8%** on ethnicity and **Islam 82.0%, no religion 11.3%, Buddhism 5.4%,
shamanism 0.8%** on religion; no other aimag is above 3.5% Muslim, the next
being Uvs. Uvs is Durvud 42.3% and Bayad 34.2%, which is where the report
puts 41.8% of Mongolia's Durvuds and 44.3% of its Bayads. Across the 18
aimags whose religion was read the Buddhist share runs from 5.4% to 86.3%,
bracketing the national 51.7% (59.4% of the population aged 15 and over
follow a religion, of whom 87.1% are Buddhist).

**Mongolia's residual, and the two kinds of it.** The census asks whether a
person follows a religion before asking which, so "No religion" here is an
answer people gave and not a bucket welded to non-response -- unlike Laos's
"No religion or not stated", it leads a unit honestly, and it does in nine
aimags. The ethnicity question has two residuals and both are marked as
residuals in `canonical_groups.RESIDUAL` so that neither can lead a unit:
"Other ethnic groups", which is every group with fewer than a hundred people
in the country, and "Other nationals (Mongolian citizens)", which is a
citizenship and not an ancestry. Nineteen of the census's groups joined the
tree under *Mongolic and Siberian peoples*; Тува, Халимаг and Балба are the
Mongolian for Tuvan, Kalmyk and Nepali and are resolved as variants of names
the tree already carried.

**What is written.** `data/processed/mongolia.json`: 22 aimags, each with the
census's ethnic composition, and 18 of them with its religion; 339 soums, of
which 204 carry an ethnic composition and 135 carry a written reason instead.
Every soum's religion is a gap that says the census published the answer for
the aimag and that this aimag's book prints no religion table by soum. The
base of every ethnic figure is Mongolian citizens, so the 22,418 foreign
nationals the census counted are outside it, and a group under 0.05% of a
unit is inside "Other ethnic groups".

**Language is declared rather than left blank.** See *Mongolia: a
questionnaire that runs to question 29* under Collection policy.

**What was measured and left.** HDX carries Mongolia's boundaries and
humanitarian datasets, not census tables, and was not read. The 2010 census's
books are on the Archive too and were not read: this project carries one
vintage per unit and 2020 is the later one. Nothing was taken from the
narrative of any book -- several state the aimag's religious split in a
sentence where the table is an image, and a sentence's number is not a
table's.

### Brunei: two fields by district, a third asked and never printed

Brunei's Department of Economic Planning and Statistics ran the sixth
Population and Housing Census (Banci Penduduk dan Perumahan, **BPP 2021**)
through 2021 and reported it in *Report of the Population and Housing Census
(BPP) 2021: Demographic, Household and Housing Characteristics*, October 2022.
The report itself is 94 pages of narrative and charts. The figures are in its
three annexes, which DEPS publishes both as PDFs and as one workbook:

| | |
|---|---|
| Workbook | `wp-content/uploads/2025/11/EXCEL-TABLE-A-C.xlsx` |
| Report | `wp-content/uploads/2025/11/RPT-2.pdf` (40 MB) |
| Annexes | `ANNEX-A.pdf`, `ANNEX-B.pdf`, `ANNEX-C.pdf` |
| Questionnaire | `Q_BPP2021.pdf` |

all under `https://deps.mofe.gov.bn/`. `scripts/fetch_census/brunei.py` reads
the workbook; the host answers an ordinary verified client, no key and no
archive involved.

**Finding them took a detour worth recording.** Every link the department's own
pages print for the 2021 census points into
`deps.mofe.gov.bn/DEPD Documents Library/DOS/POP/2021/`, the SharePoint library
the old site served, and every one of those paths now redirects to a 404: the
census report, the annexes, the workbook and the questionnaire alike. The files
are all still there under `wp-content/uploads/`, and what found them was the
site's own WordPress media API — `wp-json/wp/v2/media?search=annex`,
`?search=table`, `?search=BPP` — which lists the real `source_url` of every
upload. `data.gov.bn` answers a TLS hostname mismatch (its certificate is not
valid for `data.gov.bn`), which is where this would otherwise have gone first;
`brucensus.gov.bn`, the census's own site, times out. HDX has 84 Brunei
datasets and not one composition: World Bank indicator mirrors, WorldPop
rasters, HOT OSM extracts, ADB key indicators.

**Race and religion, by district.** Table **A3** is Population by Race,
District and Sex and table **A4** is Population by Religion, District and Sex,
both for 2021, and between them they fill all four districts:

| | Brunei Muara | Belait | Tutong | Temburong | Brunei |
|---|---:|---:|---:|---:|---:|
| Population | 318,530 | 65,531 | 47,210 | 9,444 | 440,715 |
| Malay | 69.9% | 50.7% | 74.7% | 60.5% | 67.4% |
| Chinese | 9.0% | 16.9% | 4.9% | 2.4% | 9.6% |
| Others | 21.1% | 32.4% | 20.4% | 37.1% | 23.0% |
| Islam | 84.5% | 70.3% | 84.2% | 75.5% | 82.1% |
| Christianity | 6.3% | 10.7% | 2.4% | 12.8% | 6.7% |
| Buddhism | 6.1% | 11.0% | 2.3% | 1.1% | 6.3% |
| Other, none, or not stated | 3.2% | 7.9% | 11.0% | 10.7% | 4.9% |

**What the state's categories are.** Brunei's race question (E09) offers three
groups, and "Malay" is an administrative category rather than an ethnonym. The
report's own definition: a Brunei Malay is "the persons belonging to one of the
following ethnic groups of the Malay race, namely Brunei, Tutong, Belait,
Kedayan, Dusun, Bisaya or Murut", and the questionnaire numbers those seven
beneath it. Their shares are published for the country and nowhere else —
Melayu Brunei 82.1% of the Malay total, Melayu Tutong 5.9%, Melayu Kedayan
5.6%, the other four under 5% each — so the district rows carry the state's
three groups and nothing here splits Malay or renames it. This is the same kind
of category as Singapore's CMIO and Malaysia's bumiputera, described in those
sections: a classification the state makes and administers, not a summary of
how people describe themselves. "Others" is the report's residual, "the rest of
the population not included in the Malay and Chinese racial groups"; in a
country where 18.4% of those counted were temporary residents, it is largely
foreign workers, and also the Malays of Malaysia and Indonesia, the Ibans, and
everyone else.

Religion (E10) offered Islam, Christianity, Buddhism, Hinduism and Others and
the published table has four columns, because — the report says so plainly —
"the other religions, unstated faiths and no religious beliefs were grouped
into 'Others'". That welds a real answer to a non-answer, which this map's
group tree has a place for: the bucket is carried as **Other, none, or not
stated**, filed under "Not stated" beside the other labels that do the same,
rather than as "Other religions", which would count the irreligious as
adherents of something. Islam is the state religion, and at 82.1% nationally it
leads every district.

**The mukims carry a head count and a stated gap.** The map draws 38 mukims for
Brunei and all 38 now have the census's population, from table **C1**,
Population by Mukim, Residential Status and Sex. None has a composition, and
that is what the annexes publish rather than what this reader managed:

* **Annex A**, twelve tables, crosses race and religion with district, age and
  residential status. Nothing below the district.
* **Annex B**, sixteen tables, gives total population, households and occupied
  living quarters by district, by mukim and by kampung. No composition of any
  kind.
* **Annex C**, ten tables, gives mukim and kampung by residential status and by
  age group. Again no composition.

So each mukim's `ethnicity` and `religion` say what the census counted there
and which three annexes were read to establish that it counts no more.

**Language is asked and never tabulated**, which is the Nigeria case above
rather than the Bhutan one, and the difference is the whole point of the
distinction. The BPP 2021 questionnaire has two language questions: **E26**,
"Language(s) that you can read and write", marked *all that apply* — a set of
overlapping proficiencies, not a composition — and **E27**, "Language mainly
spoken at home", marked *only one that applies*, which is exactly a
composition. Neither is reported. No table in any of the 38 in Annexes A, B and
C has a language column, and the report's Concepts and Definitions defines
race, religion, marital status, country of birth and nationality and says
nothing about language. So Brunei is **not** in `NOT_COLLECTED_POLICY`: every
Bruneian record carries `not_available` with that reason, because the census
did ask and the answer was not printed.

**Self-checks, and what they found.** The workbook's national column is checked
against the figures the report prints in prose in its Executive Summary and
chapter 1 — 297,016 Malays, 42,132 Chinese, 101,567 Others; 362,035 Muslims,
29,462 Christians, 27,745 Buddhists, 21,473 Others; 440,715 people — which is a
cross-check rather than a restatement, the two being different documents by the
same office. Then each district's groups must sum to the district's own printed
total, the four districts must sum to each national figure, the two tables must
agree about how many people each district holds, and each district's mukims
must sum to the district. All of them passed exactly, to the person, on the
first run; nothing is rounded and nothing is derived. The percentages above are
computed from those counts and match the Factbook figures already on Brunei's
country row (Malay 67.4%, Muslim 82.1%), which is the same census reaching the
map twice by different routes.

**Two names, neither of them guessed.** geoBoundaries draws 38 mukims where the
census counts 39, and the two differences are forced rather than chosen:

* The census counts **Gadong A** and **Gadong B**; the boundary file draws one
  **Gadong**. Brunei Muara has 18 census mukims and 17 shapes and every other
  name matches outright, so the one shape is the two mukims. Their head counts
  are added — 35,424 and 38,067 — and the record's note says so. Nothing else
  in the file is summed.
* The census writes **Bokok**; the boundary file writes **Bunkok**. Temburong
  has five mukims in both and four of them are identical (Amo, Bangar, Batu
  Apoi, Labu), so the fifth is one mukim under two spellings. It is declared as
  an alias on the row, not left to a resemblance test, which would not have
  made the match anyway.

Brunei Muara is hyphenated in the boundary file and not in the census;
"Brunei-Muara" is declared as an alias for the same reason. No join failed:
4 districts and 38 mukims, every one reaching its shape.

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
for 2000. So Thailand is a gap about publication, as Viet Nam was until its Vietnamese volume was read, rather than a
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

### Thailand: ethnicity from secondary sources, by the owner's decision

Everything the section above measured still holds: the census does not ask
ethnicity, the office's hosts answer 418 and 403, and the one public
language file is not a composition. What changed is a decision. On **19
September 2026** the map's owner decided that Thailand's 77 provinces should
carry what secondary sources can say about ethnicity, with stated modelling
and honest labels: a real count as a composition, anything estimated as a
`modelled` estimate with its method on the record.
`scripts/fetch_census/thailand_ethnicity.py` is that decision, and the
sources were measured in the order the decision named them.

**(a) The Ethnolinguistic Maps of Thailand** (แผนที่ภาษาของกลุ่มชาติพันธุ์ต่าง ๆ
ในประเทศไทย, Suwilai Premsrirat et al., Mahidol University Institute of
Language and Culture, 2004) are the standard secondary source, and their
per-province tables are not where a clean client can read them. Measured
from the runner: the Sirindhorn Anthropology Centre's ethnic-groups database
(`ethnicity.sac.or.th`, the database the centre's front page links to)
answers **403**; `www.lc.mahidol.ac.th` serves a certificate that is **not
valid for its own hostname**, which this project does not step around;
`langrevival.mahidol.ac.th` answers **403**; `www.sac.or.th` itself serves
its news and nothing tabular. What Wikipedia carries of the maps is national:
*Demographics of Thailand* transcribes ten groups (Central Thai 20.0 million,
Lao 15.2, Kam Mueang 6.0, Pak Tai 4.5, Northern Khmer 1.4, Yawi 1.4, Nyaw
0.5, Phu Thai 0.5, Karen 0.4, Kuy 0.4), and *Ethnic groups in Thailand*
transcribes the 2011 CERD country report's table by language family, which
counts 16.1 million Tai and 1.9 million Austroasiatic and then writes
"cannot specify ethnicity/number 32,888,000". Neither has a province in it.
The Thai edition's *กลุ่มชาติพันธุ์ในประเทศไทย* does not exist, and its
*ภาษาในประเทศไทย* and *ประชากรศาสตร์ไทย* carry no ethnicity table.

**(b) Kaggle** was searched from the runner (`scripts/probe_kaggle.py
--search`, through the kagglesdk client with the owner's token in the
environment) for "thailand census", "thailand population province",
"thailand language" and "thailand ethnic": 41 datasets listed, none of them
Thailand's census or anything by province -- the US Adult income set, road
accidents, tourism, a Thai text corpus, the World Factbook.

**(c) Wikipedia's provincial articles** were surveyed through the API.
*Northern Khmer people* carries the Khmer share of nine provinces for 1990
and 2000, which is the same 2000 census figure the list article already
holds; *Isan people* and *Languages of Thailand* carry no table at all.

So there is no per-province ethnolinguistic table to transcribe, and the
province figure is a **model**, built from the one per-province thing the
census did count. The list article's "Linguistic minorities in 2000" column
-- the cell `thailand.py` leaves unread -- transcribes, from each provincial
final report, the share speaking each minority language at home: "Khmer
(47.2%)" for Surin, "Malay (66.1%), Chinese (3.0%)" for Yala, "Hill tribe
languages (63.0%)" for Mae Hong Son. The adapter reads those as printed,
under the census's own category names ("Hill tribe languages", "Burmese and
Peguan", "Laotian and Vietnamese" are kept as the rows they are), drops and
names in the note anything printed below 0.1%, and assigns everyone else --
whom the census counted as speaking Thai -- to the regional Tai group the
maps give for the province's region: Northern Thai in the eight
upper-northern provinces, Isan (Lao) in the twenty of the northeast,
Southern Thai in the fourteen of the south, Central Thai in the other 35.
Every province's shares sum to 100 by construction. The method is named
`tier1-census-home-language-plus-regional-assignment`, the two inputs are on
the record, and the note says what the model cannot do: separate the Tai
groups the maps count apart (Thai Khorat, Phu Thai, Nyaw, Kaleung, Phuan,
Lue, Shan), name the Austroasiatic peoples the census did not (Kuy, So, Bru,
Mon), or see the Thai Chinese, who are a tenth or more of the country by
descent and a few hundred thousand by home language.

**The national check**, printed by the run. The 76 provinces weighted by the
December 2024 populations in *Provinces of Thailand* (the 2000 totals sit
behind the same 418) imply Central Thai 43.6%, Isan 30.1, Southern Thai 11.7,
Northern Thai 7.9, Malay 2.7, Khmer 2.3, hill tribe languages 1.4; the maps'
figures against the 2000 census population of 60,916,441 are 32.8, 25.0, 7.4,
9.8, 2.3, 2.3. The census-counted rows agree; the regional remainders run
high, because the maps' ten largest groups are 82.6% of the population and
the remainders are all of it, and by most in the centre and south where the
Chinese-descended and the smaller Tai groups live. That gap is the assumption
showing, and it is why the figure is an estimate and is labelled one. **No
backtest is possible**: no provincial ethnicity figure exists to hide and
predict, and the record says so rather than carrying one.

The labels the model writes are placed in the tree where they are certain:
Central, Northern and Southern Thai beside Isan under Mainland Southeast
Asian peoples (spelled out, because the bare "Thai" is also the nationality
Japan's census counts, and that entry wins), Kuy and Mien with them, "Burmese
and Mon" where the tree keeps Mon, Thai Chinese under Han and Sinitic
peoples, and the census's "hill tribe languages" row as a census category of
its own under East and Southeast Asian ancestry, since its peoples are half
Tibeto-Burman and half not. Bueng Kan, carved out of Nong Khai in 2011, has
no 2000 row and stays empty here as it does for religion. Thailand stays in
`ADAPTER_GAPS`, and its reason now names the model.

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
| 信者 believers | 30 | 3 | seventeen of them are that survey's own tables and one is a 社会・人口統計体系 indicator table; the other eleven are 通信利用動向調査 tables about how often a household receives spam mail, where 信者 is the tail of 受信者 and 送信者 |
| 信徒 believers, the other word | 0 | 0 | nothing at all |
| 民族 ethnicity | 8 | 2 | six 社会教育調査 tables of *museum holdings*, where 民族資料 is a shelf of ethnographic objects, and two 矯正統計調査 tables counting foreign prisoners by nationality |
| 言語 language | 636 | 14 | 学校基本調査 counts of graduate schools (言語文化研究科 and its kin) and ICD-10 tables in 人口動態調査 and 患者調査, where 言語 is a speech disorder |
| 母語 mother tongue | 2 | 1 | one MEXT survey of schoolchildren -- below |
| アイヌ Ainu | 13 | 3 | prosecution statistics, human-rights infringement cases, and the national forest yearbook. None of the three counts a population |
| 国籍 nationality | 2,280 | 26 | the census, the migration report, immigration and residence statistics |
| 外国人 foreign residents | 2,017 | 30 | likewise |

The one apparent second source is not one. 社会・人口統計体系 (00200502) also
carries the word, in table `0000010107`, Ｇ　文化・スポーツ, published by
prefecture -- but that is a compilation: 248 indicators per prefecture going
back to 1975, assembled from other statistics rather than collected. The only
statistic in the catalogue that asks anybody about religion is 宗教統計調査, so
any believer count anywhere in e-Stat is that survey's figure wearing another
table's number.

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

### Japan, resolved by the owner's decision

Everything the section above measured still holds: the census asks
nationality and none of the three, and the Agency for Cultural Affairs'
adherent table counts memberships against the prefecture where a
corporation is registered. What changed is a decision. On **19 September
2026** the map's owner decided that Japan's 47 prefectures should carry what
secondary sources can say, the way Korea's provinces carry a pollster's
survey by the decision of 11 September, provided each figure is labelled for
what it is. `scripts/fetch_census/japan.py` is that decision, and the `JPN`
entry left `NOT_COLLECTED_POLICY` the same day, because the build's guard
(`check_no_estimate_on_policy_field`) refuses an estimate on a declared
field, and rightly. The substance of the three declarations now lives in the
adapter's notes, on every prefecture, instead of in one line in `common.py`.

**What was read.** Two e-Stat tables and one survey report, all through the
runner (`ESTAT_API` in its environment, scrubbed from every log line):

* **`0003445244`**, 令和２年国勢調査 人口等基本集計, 外国人 男女，国籍別人口 --
  全国，都道府県，市区町村. Its 国籍 dimension carries 総数, 外国人, thirteen
  nationalities (韓国，朝鮮; 中国; フィリピン; タイ; インドネシア; ベトナム;
  インド; ネパール; イギリス; アメリカ; ブラジル; ペルー; その他), 日本人, and
  日本人・外国人の別「不詳」. Read at `lvArea=1-2` (the country and the 47
  prefectures) for both sexes. **Ethnicity is this table, as a list, under
  `ethnicity_basis: "nationality"`**, because it is a census count and the
  map's rule is that a count is written as one. The note on every prefecture
  says the census counts nationality and not ethnicity, that "Japanese"
  holds naturalised citizens and people of any ancestry, and how many people
  the census recorded as neither Japanese nor foreign (left out of the
  denominator, and printed). The reader refuses to write unless the 47
  prefectures reproduce the table's own 全国 row exactly, the thirteen
  nationalities its foreign total, and the total the census's published
  126,146,099.
* **The Statistics Bureau's 結果の概要** for the same tabulation
  (`stat.go.jp/data/kokusei/2020/kekka/pdf/outline_01.pdf`, 30 November
  2021, 60 pages), read by the runner's `probe_pdf`. The first attempt at
  this adapter refused because the table's national row did not reproduce
  eight per-nationality "published" counts -- which no probe had read; they
  had been written from memory, and were wrong. What the 概要 actually prints
  in section IV (pages 33 and 35) is a **different universe from the
  table**: its headline counts are 不詳補完値, in which the 2,202,484 people
  the census recorded as neither Japanese nor foreign are allocated to one
  or the other, so it puts foreign nationals at 2,747,137 (2.2% of
  126,146,099) where the table records 2,402,460 (1.9% of those recorded);
  the imputation sends 344,677 of the unstated to "foreign", a far higher
  share than among the recorded. Section VII (page 48) prints the
  nationalities themselves, but the probe's page cap stopped at section IV
  and, by the owner's instruction that day ("why don't you just publish the
  estimates with a note?"), no second probe was spent. The reader now
  enforces what it read -- the published total exactly, the imputed
  Japanese and foreign summing to it, the imputed foreign share within half
  a point of the recorded one (it is 0.24 points over) -- and publishes the
  table with that difference stated in one sentence on every prefecture's
  `ethnicity_note`, instead of holding 47 prefectures back over a summary.
  The composition is of recorded nationalities, so its foreign share runs
  about a quarter of a point low nationally against the Bureau's headline.
* **`0003282963`**, the same 宗教統計調査 table the section above measured,
  at 2025年度 (31 December 2024): 信者 by 宗教系統 for the country and the 47
  prefectures. 175,054,047 believers, 1.39 per person. Used as a **relative
  signal only** -- the reader refuses it if it ever sums to fewer than the
  people, because then it would be a different table.
* **NHK's ISSP 2018 "Religion" round**, reported by Toshiyuki Kobayashi in
  放送研究と調査 (April 2019, pp. 52-72; fieldwork 27 October to 4 November
  2018, 2,400 adults aged 18 and over by drop-off/pick-up, 1,466 valid
  responses). The question is "ふだん信仰している宗教がありますか", with the
  instruction that a religion kept only for weddings and funerals does not
  count. Page 53: Buddhism 31%, Shinto 3%, Christianity 1%, any religion 36%
  (so other is 1%), no religion 62%, and the remaining 2% no answer. Unchanged
  from 2008. `nhk.or.jp` served the runner nothing -- the page came back
  empty and the PDF as zero bytes -- and the report was read through the
  Internet Archive's copy of the PDF at the same URL.

**What is modelled, and how.** Religion on every prefecture is `modelled`,
method `tier1-national-prior-tilted-by-adherents`: the survey's four
affiliated shares, each multiplied by the prefecture's tilt ratio (the
tradition's share of the prefecture's reported believers over its share of
the nation's, clipped to between 1/3 and 3), rescaled to the survey's
affiliated total, with no religion held at the survey's national figure
because nothing gives it by prefecture, and the 2% no-answer left out. Two
absolute bounds stop the signal's known artefacts passing through: Christianity
at most 5% (Nagasaki, Japan's most Christian prefecture, is a few percent by
the churches' own counts and comes out at 3.2, its tilt ratio at the 3.0
clip) and Shinto at most 9% (three times the national self-identification).
Three prefectures hit a bound -- Okinawa, whose corporations report 90% of
its believers as Shinto, Kyoto and Nagano -- and their notes say so. The
record carries the ratios under `tilt` and the bound groups under `capped`;
the log prints the five prefectures the tilt moves furthest from the prior,
which on the 19 September run were Okinawa (9.9 points), Kyoto (6.9), Nagano
(5.9), Miyagi (5.4) and Yamanashi (5.2), every one of them a Shinto-heavy
registration count pulling Shinto up and Buddhism down. **No backtest exists and none is
claimed**: there is no prefecture-level self-identification figure to score
against, so the estimate has no `backtest` key and its note says why.

Language is `modelled`, method `tier1-nationality-to-language`: the same
nationality composition with every person given the majority home language
of their nationality (Japanese, Korean, Mandarin, Filipino, Thai, Indonesian,
Vietnamese, Hindi for Indians -- a plurality, and the note says so -- Nepali,
English for British and Americans, Portuguese, Spanish, other). The note
states the assumption and which way it errs: a Korean national born in Osaka
and a Brazilian of Japanese descent speak Japanese at home more often than it
allows, and naturalised citizens' families are counted the other way. A
language under a twentieth of a point folds into "Other languages" rather
than printing as 0.0%.

**What remains unknowable.** Whether anyone in a given prefecture identifies
with a religion: the model puts the survey's 63% no-religion on Okinawa and
on Nara alike, and that is the survey's national figure repeated, not a
finding. Any ethnicity of a Japanese national -- Ainu, Ryukyuan, Japan-born
Korean who has naturalised, nikkei returnee -- all "Japanese". Any language
anyone actually speaks at home. The Statistics Bureau's own 不詳 row, 2.2
million people in 2020 whose nationality the census could not establish,
which is left out of every denominator and printed on every note.

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
map lists Yanam as a district of Andhra Pradesh. It is not one: it is an enclave of
Puducherry, 600 km from the rest of that union territory, entirely surrounded
by East Godavari district. The census adapter has it right — its row
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

### The units that sat blank beside their neighbours

A different failure, found by asking which first-level units were empty on all
three fields while most of their siblings were filled. That shape is the
signature of a join that missed, not of a source that does not exist: **59
units in 34 countries**, each one blank next to a country that had been read.

They were also saying the wrong thing. A unit no adapter row reached fell
through to the note "No unit-level source has been read for Bulgaria at this
level" — which was false, and false in the direction that hides the bug. A
source *had* been read for Bulgaria; 27 of its 28 oblasts carried it. So a
fourth case was added, and it counts what it claims:

> A unit-level source was read for Bulgaria at this level — Wikidata — and 27
> of its 28 units were joined to it. This unit matched no row in that source,
> so whatever it publishes here has not been reached. That is a gap in this
> map's joining, not a claim about what the census asks or publishes.

Across both levels that sentence replaced the wrong one on **665 units**.

**40 of the 59 then joined**, under two tables with opposite meanings. Where
the boundary file is *wrong*, `MISSPELLED` corrects it and fixes the label and
the join together: Eritrea's "Northen Red Sea Region", Guyana's "Barina-Waini"
for Barima-Waini, Nicaragua's "Carribean", Benin's "Atlanique", Turkmenistan's
"Ahai" for Ahal. Seychelles was not misspelled but *cut off* — every one of its
26 district names in CGAZ is at most ten characters ("Anse Boile", "Roche
Caïm", "La Digue a"), which is a field width and not a spelling.

Where the boundary file is *right* and a source simply says something else,
`ALSO_KNOWN_AS` joins the shape under a second name and leaves its label
alone: Srem for Syrmia, Al Asimah for the Capital Governorate, Zambezi for
Caprivi, Elías Piña for La Estrelleta. Renaming those shapes to the source's
word would be a worse error than the gap it closes.

Every entry was checked against the shape it claims — the source's own
coordinate has to fall inside that shape's bounding box, a stronger test than
any reading of two names. It earned its keep twice. Trinidad and Tobago's
leftover shape "Tobago" and leftover row "Arima" are 95 km apart on different
islands, which a distance threshold loose enough for a large country would
have waved through; and Seychelles' two Grand'Anses, one on Mahé and one on
Praslin, are assigned *opposite* to what the names suggest — the district CGAZ
writes without the apostrophe is the one on Praslin. Reading the names would
have swapped them.

**19 units did not join, for three reasons, and all three are stated rather
than papered over.**

*The source has no such row.* Burundi's Rumonge (created 2015), Botswana's
Chobe, Mauritius' Agaléga and St. Brandon, Seychelles' Outer Islands, Tobago,
St Lucia's Canaries, Samoa's Tuamasaga.

*The two sides divide the ground differently.* Namibia draws one Kavango where
the source has Kavango East and West; Chad draws Ennedi-Est and Ennedi-Ouest
where the source has one Ennedi; Grenada draws one Southern Grenadine Islands
for Carriacou and Petite Martinique; Madagascar's shapes are the 22 regions and
the source's rows are the 6 old provinces. Each is a sum or a split, not a
name, and inventing either would put a number on the map that nobody published.

*A city and the region around it collide on one key.* `norm()` drops the words
"City", "Oblast", "Province" and "Governorate", so Sofia and Sofia City reduce
alike, as do Maputo and Maputo Province and Sanʿaʾ and Sanʿaʾ Governorate. No
alias can separate them: every name anyone would declare lands on the key that
is already ambiguous. These are the one class where a declaration would have
*looked* like a fix, so the table says in writing that it cannot make it — a
declaration that does nothing is worse than the gap it claims to close,
because it reads as though the question has been settled.

## China: religion for five provinces, from a survey the census does not run

China's census does not ask religion, and every province said so. The China
Family Panel Studies (CFPS, Peking University's Institute of Social Science
Survey) asked a religion module in its 2012 wave, and Lu Yunfeng's report on
it -- *当代中国宗教状况报告——基于 CFPS (2012) 调查数据*, 世界宗教文化 2014 no. 1,
pp. 11-25, reached through the Internet Archive from the CASS Institute of
World Religions' site -- prints self-declared affiliation of adults by
province for the five provinces the survey drew as independent,
self-representative subsamples of 1,600 households each: **Shanghai,
Liaoning, Henan, Gansu, Guangdong**. The paper is explicit (p. 12) that only
those five support province-level inference; the other twenty provinces came
from one pooled frame and are not read. Six regions were not surveyed at all
-- Xinjiang, Tibet, Qinghai, Inner Mongolia, Ningxia, Hainan -- so the
national figure understates Islam and Tibetan Buddhism, and is not written.

The PDF is InDesign's vector outlines with no text layer; nothing parses it,
so Table 2 is transcribed in `scripts/fetch_census/cfps_survey.py` from the
rendered page and each column is checked to sum to 100. Shanghai: Buddhism
10.4%, Protestant 1.9%, Roman Catholic 0.7%, Taoism 0.1%, no religion 86.7%,
n = 2,362. Henan is the province where Protestantism reaches 5.6%, Gansu where
Islam reaches 3.4%. Affiliation, not practice: the same paper finds about 1%
of respondents in any religious organisation. Registered after the Korea
survey as the lowest-authority file for China; the twenty-eight other
provinces keep the policy statement, which now says the survey exists.

### The microdata, and what checking it against the paper taught

A Kaggle re-upload of the public-release files (2012 through 2020) exists.
`scripts/probe_kaggle.py` read what it holds on the runner -- the only place
that reaches Kaggle -- before anything was written: 2012 and 2016 carry the
seven-answer affiliation question (`qm601`), 2014 asked instead which deities
a person believes in, and 2018 and 2020 ask only about membership of a
religious organisation. So 2016 is the newest comparable wave, and
`scripts/fetch_census/cfps_microdata.py` tabulates it by province with the
wave's cross-sectional individual weight, `rswt_natcs16`.

**The adapter checks itself against the paper before writing, and the check
found something.** Tabulating the 2012 file and comparing it with Table 2, the
first run refused: Liaoning came out at 2,810 respondents against the paper's
2,939. A diagnose mode tried every reading, and the answer is that **the
paper's table is unweighted** -- an unweighted tabulation reproduces all five
provinces within 0.20 points and their sample sizes within 0.9% (the 201906
re-release adds or drops a few rows), while no weighting comes within half a
point. Shanghai's Buddhism is 10.4% unweighted and 8.3% with the weight. The
check is therefore the unweighted one, which is what proves the province
codes; what is written is weighted, which is what the weights are for and is
valid within a self-representative province; and the note says the paper's
figure is unweighted, so a reader comparing the two sees a method and not a
disagreement.

Written from 2016, weighted: Shanghai no religion 79.3%, Buddhism 16.6%,
Protestant 2.1%, Roman Catholic 1.0% (n = 1,839 with a weight); Henan
Protestant 7.0%; Gansu Islam 4.8%. Every province's shares are in the run log
with their sample sizes, and the twenty that are not written show why they
are not: Fujian is 55% Buddhist on 357 respondents, Tibet has five. The 2016
stem asks which religion a person *believes in* where 2012 asked which they
*belong to*, and takes more than one answer, of which the first is counted;
shares rose in every province between the waves, and the wording is part of
why. The 2012 file (`cfps_survey_province.json`) stays as the lower-authority
row, so removing the Kaggle-derived file leaves the five provinces on the
published table.

Provenance: CFPS is distributed by Peking University's ISSS under a data-use
agreement; the Kaggle bundle is a third party's re-upload whose standing is
not verified here. Only aggregate shares are kept. The clean chain of
custody is to register with ISSS, download the public-release files, and run
the adapter with ``--root`` pointing at them: it runs the same self-check,
writes the same output, and the source then cites ISSS rather than Kaggle.
The microdata never enters the repository either way.

## China: ethnicity for 31 divisions, from the census tables Wikipedia transcribes

China's census records the 56 official nationalities (民族) and the National
Bureau of Statistics tabulates every first-level division's composition. The
tabulations sit on `stats.gov.cn`, which answers an automated reader 403 (the
closed route above, not circumvented). What is reachable is the copy: a
division's Wikipedia article transcribes its census table under
"Demographics", "Ethnic groups" or 民族, and the English article *List of
Chinese administrative divisions by ethnic group* tabulates the 2020 census
for every division by region, a count and a share for the region's ten or so
largest nationalities and a 2020 Census row of totals. `china_wiki.py` reads
all three -- each division's English and Chinese article, its Chinese
"民族构成列表" page, and the list -- through the MediaWiki API, the way
`wiki_census.py` reads Kazakhstan and Cambodia, and each record names the
census as its source and the article as the copy it was read from.

What the reader does is written at the top of the adapter; the decisions that
matter are these. A table counts as a census composition when its first
column is nationalities, names Han and at least one other of the 56, and its
caption or heading says which census; a time series or a table with no
population column is passed over. Among the tables an article carries the
latest census wins, then the division's own article over the list, then the
one with more nationalities. Where every row prints a count the shares are
recomputed from the counts, because the transcribed shares are where the
slips are (Shandong's table gave its 310,738 "other" as 0.003%); otherwise
the printed shares are read and a shortfall of up to five points is written
as the remainder. Shares must add to 100 within 0.3 or the division is
refused with the sum in the log; they are then re-rounded to one decimal by
largest remainder. The census's residual row (其他民族, "Others") is written
as "Other ethnic groups" and the rows for people of no recognised
nationality (未识别民族) fold into it, which the note says. "Yao" is written
"Yao (China)" because the tree's bare Yao is the Bantu people of Malawi.

The run of 19 September 2026 wrote **31 of 31 divisions**, none refused: 30
from the 2020 census and Inner Mongolia from 2010 (its English article
carries the 2010 table and no 2020 one has been transcribed; the note says
so). Fourteen were read from the list of divisions (the municipalities, Hebei,
Jiangsu, Zhejiang, Anhui, Fujian, Jiangxi, Henan, Hubei, Yunnan, Tibet,
Shaanxi, Gansu), ten from their Chinese article (Shanxi, Liaoning, Jilin,
Hunan, Hainan, Chongqing, Sichuan, Guizhou, Qinghai, Ningxia), Guangdong from
its Chinese 民族构成列表 (57 groups), and Heilongjiang, Shandong, Guangxi and
Xinjiang from their English articles. Beijing is the cross-check: the city's
own 2010 census communique (bjstats, read earlier in this project) printed
Han 95.9% of 19,612,000 with Manchu 336,000, Hui 249,000, Mongol 77,000,
Korean 37,000 and Tujia 24,000; the 2020 table reads Han 95.2% of 21,893,095
with Manchu 469,995, Hui 274,112, Mongol 123,340, Korean 32,984 and Tujia
29,580 -- the same ordering and the same magnitudes a decade on. Hong Kong and
Macau come from their own censuses (below) and are not in this file.

Religion is not asked by the census and stays under the policy; language is
not published by division and stays a gap.

## Hong Kong: a census of its own, one shape under China

Hong Kong is one first-level shape on this map, drawn under China because
geoBoundaries folds the Special Administrative Region into the state that
administers it. Its census is not China's. The Census and Statistics
Department counts the territory every ten years and asks two of the three
questions the mainland census does not -- ethnicity and usual spoken
language -- and does not ask the third, religion, which stays declared not
collected under the China policy. Before this the shape carried Wikidata's
population and nothing else, with the China policy's religion sentence and
two `not_available` markers saying a source had not been read.

The source is the *2021 Population Census -- Main Results* (C&SD, December
2022), which the Department publishes on `census2021.gov.hk` twice over: as a
354-page bilingual PDF, and beside it as one workbook of the same tables,
161 sheets, one per table. The workbook is what
`scripts/fetch_census/hongkong_census.py` reads, and it is worth saying why.
The PDF sets each table without ruling lines, so pdfplumber finds no table on
its pages at all (the runner's probe of the two pages reported "0 table(s)"),
and a text reader prints the Chinese row labels, the figures and the English
labels as three separate runs, which is the Pakistan problem all over again.
The workbook has none of that: each row is its Chinese label with the figures
beside it and the English label alone on the row beneath, and the reader
pairs them.

Two sheets are read. **Table 3.9 (3)** is *Population by sex, ethnicity and
age group, 2021*, the both-sexes block: Chinese 6,793,502 (91.6%), then the
619,568 non-Chinese as the census prints them -- Filipino 201,291 (2.7%),
Indonesian 142,065 (1.9%), Indian 42,569, Nepalese 29,701, Pakistani 24,385,
Other South Asian 5,314 (Bangladeshi and Sri Lankan, by the table's note),
Thai 12,972, Japanese 10,291, Korean 8,700, Other Asian 10,574, White 61,582
(0.8%) and Others 70,124 (0.9%). "South Asian" is printed above its four
detail rows and is their sum, so it is not written; "Others", which the note
says includes people who reported more than one ethnicity, is written as
"Other ethnic groups". **Table 3.13** is *Population aged 5 and over by usual
spoken language and place of birth, 2021*, and its Total column is the whole
composition: Cantonese 6,328,947 (88.2%), English 330,782 (4.6%), Putonghua
165,451 (2.3%), Fukien 60,864, Hakka 41,514, Chiu Chau 37,621, Other Chinese
dialects 64,572, Filipino (Tagalog) 29,413, Indonesian (Bahasa Indonesia)
24,244, Japanese 8,704 and Others 87,015 (1.2%), of 7,179,127 people aged 5
and over who are not mute. That basis is written in `language_basis` and in
the note, because it is not the population: a person's usual spoken language
is the one language they usually speak at home, and the 233,943 people
between the two totals are the under-fives, who are not asked, and the
mute, whom the table's note excludes.

The language table a reader meets first is not this one. Table 3.12,
*Proportion of population aged 5 and over able to speak selected
languages/dialects*, is the table the report's text cites for Cantonese, and
its "as the usual spoken language" column carries the same 88.2 -- but its
rows are eleven selected languages, not everyone, and its point is the other
two columns, which say that 58.7% can speak English and 54.2% Putonghua. Those
are abilities, and they add to well over 100. Read as a composition it would
have left 2% of the population nowhere and called Filipino's 0.4% a share of
speakers rather than of homes.

Every figure is checked as it is read, and the checks are the report's own.
The ethnicity leaves must sum to the printed 7,413,070 and the South Asian
detail to the printed 101,969; the language rows must sum to the printed
7,179,127; every share computed from a count must agree with the share the
census prints beside it; and the two figures the report states in prose --
91.6% Chinese (paragraph 3.18) and 88.2% Cantonese (paragraph 3.24) -- must
come out of the arithmetic. Any of those failing is a refusal, since a
workbook that has moved a column is the same file with the wrong answer in
it. Fukien and Chiu Chau are the census's romanisations of Hokkien and
Teochew and are registered as such in `scripts/group_tree.py`; every other
label already had a place. The build sandbox cannot reach `census2021.gov.hk`
(the egress proxy refuses the connection), so the adapter runs on the
workflow runner like the rest; the owner's copy of the PDF on Google Drive
was read first, and confirmed the figures the workbook then supplied, but the
Department's URL is what is cited.

### Macau

Macau is the other Special Administrative Region drawn under China, and like
Hong Kong it runs a census of its own: the Statistics and Census Service
(DSEC) counts the territory every ten years with a by-census between, and
asks nationality, ethnicity and usual language, which the mainland census
does not. Before this the shape carried Wikidata's population and nothing
else, with the China policy's religion sentence and two `not_available`
markers.

**Religion is not asked, and that is measured rather than assumed.** The
runner's probe searched the whole of DSEC's *Detailed Results of 2021
Population Census* (revised version, October 2022, 147 pages,
`https://www.dsec.gov.mo/getAttachment/6cb29f2f-524a-488f-aed3-4d7207bb109e/E_CEN_PUB_2021_Y.aspx`)
and of the *2016 Population By-census Detailed Results* (133 pages,
`https://www.dsec.gov.mo/getAttachment/e20c6bab-ada4-4f83-9349-e72605674a42/E_ICEN_PUB_2016_Y.aspx`)
for religion, religious, Buddhis- and Catholic: zero pages in each. The
2021 report's own account of its questionnaire lists what the long form
collects -- ethnicity, nationality, place of previous residence, education,
employment and earnings -- and religion is not among them. So Macau's
religion stays `not_collected` under the China policy, and nothing is
written for it; the religious-affiliation figures that circulate for Macau
are surveys, not DSEC's.

`scripts/fetch_census/macau_census.py` reads two statistical tables of the
2021 report, both sexes, the Total row. **Table 6**, *Population by gender,
age group and nationality*: Chinese 608,379 (89.2%), Filipino 33,896
(5.0%), Other Asian countries 26,640 (3.9%), Portuguese 8,991 (1.3%) and
Others 4,164 (0.6%), of 682,070. It is carried as the ethnicity field under
`ethnicity_basis: "nationality"`, the way Japan's prefectures carry their
census, because a passport is not an ancestry. The census does have an
ethnicity table (Table 7) and it is the poorer answer: Chinese 609,863
(89.4%), Portuguese 5,162, Chinese and Portuguese 6,668, Chinese and
non-Portuguese 1,498, Portuguese and others 1,191, and then one "Others" of
57,688 (8.5%) holding every other people in the territory, where the
nationality table at least names the Filipinos. The Vietnamese, whom the
report's text puts at 1.8% of the population, are inside "Other Asian
countries" in both; the table does not print them apart. That column is
written as "Other Asian nationality" and registered in `scripts/group_tree.py`
under "Other national identities", because the prefix rule would otherwise
have filed it as East and Southeast Asian ancestry, which the Nepalese,
Indian and Burmese nationals in it are not; the census's "Others" is written
as "Other nationalities", already a residual. **Table 10**, *Population by
gender, age group and usual language*: Cantonese 537,981 (81.0%), Mandarin
31,405 (4.7%), Other Chinese dialects 36,032 (5.4%), Portuguese 3,949
(0.6%), English 23,635 (3.6%), Tagalog 19,154 (2.9%) and Others 11,626
(1.8%), of the 663,782 people aged 3 and over, which `language_basis`
states. Usual language is the one language a person mostly uses at home.

The PDF is what makes the reader what it is. pypdf runs a table row together
with a space for every thousands separator -- `MF 682 070 608 379 33 896 26
640 8 991 4 164` -- so a row is not a list of figures until it is cut into
as many as the table has columns, and the text does not say where. Every
cut is tried and the one kept is the one in which the Total column equals
the sum of the others; a row with no such cut, or two, is refused. The
checks are then the report's own: each table's Total must be the population
the census publishes (682,070, section 1.1; 663,782, Principal
Characteristics page 40); the language counts must agree, count for count,
with the same table as the report prints it a second time on page 40, and
its "Chinese" row there must be the three Chinese columns together; each
composition must sum to 100 within three tenths. Two softer checks follow
the owner's rule that a small disagreement with a secondary figure is a
sentence in the note and not a refusal: the shares printed beside the
counts on page 40, and the shares the report's prose states (Chinese
nationality 89.2%, Cantonese 81.0%), are held against the computed shares
within a tenth, and a difference is written into the note. On the 2021 file
there is none. The build sandbox cannot reach `dsec.gov.mo` (the egress
proxy refuses the connection), so the adapter runs on the workflow runner;
it reads only the report's pages 36 to 80, finding the three pages by title,
because extracting all 147 costs the runner most of an hour.

### Taiwan, resolved by the owner's decision

Taiwan's 22 counties and cities, 23.6 million people, carried nothing for
religion, ethnicity or language -- the largest wholly blank country on the
map. The census asks language and not the other two; the one Wikipedia table
measured earlier (languages used at home by division) is multi-response and
was rightly not read. On **19 September 2026** the map's owner decided that
Taiwan, like Japan the same day, should carry what official and secondary
sources can say, each figure labelled for what it is: a count as a
composition, everything else as a `modelled` estimate. `NOT_COLLECTED_POLICY`
never had a `TWN` entry, so nothing had to leave it. `scripts/fetch_census/taiwan.py`
is that decision, and this is what it read, what it modelled, and what it
could not reach.

**What the sandbox could not do.** Every Taiwanese host answered nothing at
all from the build sandbox (`curl` returns no status), so every read below
went through the runner. From the runner, `census.dgbas.gov.tw` answers 403,
`religion.moi.gov.tw` (the temple and church registry, and the XML the open
data portal links for datasets 8203 and 8204) times out on every request,
`state.gov` answers 403 and its archived copy is a script shell, and
`ws.dgbas.gov.tw` sends its certificate without the intermediate above it --
which the earlier attempt recorded as a refusal, and which `probe_pdf --aia`
repairs the way `scripts/probe_tls.py` documents, with full verification.
The historical yearbook workbooks on `ws.moi.gov.tw` (`y06-01.xls` and
neighbours) answer a 307 to an error page; the historical monthly workbooks
beside them read fine but stop at December 2016. The current tables are on
`statis.moi.gov.tw`, whose menu is built by a script from an array of report
ids and whose files are static under `micst/report/<type><id>.xlsx`.

**Language, read.** The DGBAS results release of the 2020 census
(109年人口及住宅普查總報告統計結果, 30 November 2022, the PDF linked from
`dgbas.gov.tw/News_Content.aspx?n=3602&s=230162`) prints on page 32 Table
2-5, 6歲以上本國籍常住人口使用語言情形: for the country, the regions and every
county, the *main* language currently used -- 國語, 閩南語, 客語, 原住民族語,
其他 -- as a single-answer composition of residents of ROC nationality aged 6
and over, and beside it the secondary language, which is not read. This is
the newer of the two censuses that asked (the 2010 census published only a
multiple-response table) and it is a composition, so it is written as a
list under `language_basis` "main language currently used, resident
population of ROC nationality aged 6 and over", 原住民族語 as "Taiwanese
indigenous languages" (placed under a new Formosan branch of the Austronesian
family; Yami is Batanic and is deliberately not listed under it). Nationally:
Mandarin 66.4, Hokkien 31.7, Hakka 1.5, indigenous 0.2, other 0.2, of
21,784,369 people. The reader refuses the table unless the 22 counties' base
populations sum to the printed total exactly and the national row rebuilt
from them, weighted by those bases, sits within half a point of the printed
one (it sits within 0.03). Hsinchu County is 11.5% Hakka-speaking and Miaoli
18.1; Hualien and Taitung 4.1 and 6.4 indigenous-language; Lienchiang 5.2
"other", which is Matsu's Eastern Min. The 2010 census's own table, by
contrast, has Hakka at 56% of Hsinchu County -- that was the share of
people who use Hakka at home at all.

**Ethnicity, modelled.** Three official figures, and one assumption:

* *Indigenous*: the household register's count of people holding indigenous
  status by county, from the Ministry of the Interior's current monthly
  bulletin (內政統計月報 table 1.4, 現住原住民人口數), over the same month's
  registered population from table 1.1 of the same bulletin. Both are the
  register, both are the same month, and the reader refuses them if their
  months differ or their counties do not sum to their own totals. The
  workbooks (`statis.moi.gov.tw/micst/report/321010.xlsx` and `321040.xlsx`)
  carry one sheet per year and one for the latest month, and the run read
  the end of August 2026: 639,340 people of indigenous status among
  23,224,721 registered residents (2.75%); Taitung 38.4%, Hualien 30.6%,
  Pingtung 8.2%, Nantou 6.5%, Taipei 0.8%. The
  Council of Indigenous Peoples publishes the same count by people and
  county (台閩縣市原住民族人口-按性別族別, July 2026: 638,466, Amis 238,027)
  from the same register; it was read and agrees, and the Ministry's table
  is cited because its population sits beside it.
* *Hakka*: the Hakka Affairs Council's 110年全國客家人口暨語言基礎資料調查研究
  (2021; `hakka.gov.tw/File/Attach/37585/File_96737.pdf`, 481 pages),
  Figure 8, page 12: for each county, the December 2020 registered
  population and the share meeting the Hakka Basic Act definition (Hakka
  descent or connection, and self-identification as Hakka), from 63,111
  telephone interviews weighted to the register. Nationally 19.82%, 4,669,192
  people; Hsinchu County 67.8, Miaoli 62.5, Taoyuan 39.9, Hualien 34.2,
  Hsinchu City 30.3. The reader checks that the counties' populations and
  Hakka counts sum to the report's totals and that each county's count over
  its population reproduces its printed share.
* *The rest*: Table 4-1 of the same report, page 116, the national *single*
  self-identification in 2021: Hoklo 71.3, Hakka 15.7, mainlander 5.0,
  indigenous 3.0, "Taiwanese" only 3.8, other 0.1, don't know 1.0. Every
  county's remainder after indigenous and Hakka is split Hoklo : mainlander
  in the ratio 71.3 : 5.0, the 4.9% who chose "Taiwanese", other or no answer
  spread over both. **This is uniform and therefore an assumption**: it says
  nothing about where the 1949 migrants and their descendants settled, and
  it is why every county is `modelled`
  (`tier1-register-counts-plus-survey-share-plus-uniform-split`) even
  though two of its four parts are official counts. The Hakka share is of
  registered residents and the indigenous count of the same, and a person
  can be both. Labels: "Taiwanese indigenous peoples" (a new node under East
  and Southeast Asian ancestry holding the sixteen recognised peoples),
  "Hakka", "Hoklo Taiwanese", "Mainland Chinese (waishengren)".

**Religion, modelled.** No census or register counts affiliation. The
national prior is Pew Research Center's *Religion and Spirituality in East
Asian Societies* (17 June 2024; adults surveyed in 2023), read from Pew's
own page on the runner: Buddhist 28%, Daoist 24%, Christian 7% (the three
groups Pew names with the unaffiliated sum to 62%), other 12%, no religion
27%, don't know 2% (left out and the rest scaled). A 2021 figure that
Wikipedia attributes to the State Department's religious-freedom report
(folk beliefs 27.9, none 23.9, Buddhism 19.8, Taoism 18.7, Protestant 5.5,
Yiguandao 2.2, Catholic 1.4) could not be read at its source and is not
used. The county signal is the Ministry of the Interior's yearbook table
宗教教務概況 (內政統計年報, section 6, table 01, `statis.moi.gov.tw`
report 331030): registered temples and churches by county, from the
workbook's latest county sheet (`2025(區域別)`, the end of 2025). The
workbook splits temples by tradition (道教 9,824 of 12,397, 佛教 2,277,
一貫道 243 ...) only in its national 宗教別 sheet, and the registry that
would do it by county (`religion.moi.gov.tw`, the source of the open-data
XML) answers nothing from the runner, so the signal is two-way: churches
tilt Christianity, temples tilt Buddhism, Taoism and the other traditions
together, and within a county those three keep the prior's proportions.
Used only *relatively*, as for Japan: the county's church (temple) share of
its registered buildings over the nation's (18.7% churches nationally),
clipped to between 1/3 and 3, scales the survey's share; the four
affiliated shares are rescaled to the survey's affiliated total; no
religion is held at the national 27.6% because nothing gives it by county;
Christianity and "other" are bounded at 25% absolutely. The bound is the
model's admission of what the signal cannot tell apart: a church share is
high where there are many Christians (Hualien, Taitung) and where there are
few temples for the size of the city (Taipei, two churches for every
temple), and the building count alone does not say which. The record
carries the ratios under `tilt` (keyed `Temples` and `Churches`) and any
bound group under `capped`; the run log prints the five counties the tilt
moves furthest from the prior. In the run of 19 September 2026 (buildings
at the end of 2025) they were Taipei (280 temples, 564 churches), Taitung
(222, 282) and Hualien (194, 260), each 17.9 points from the prior with
Christianity held at the bound, then Taoyuan (8.0 points, Christianity
15.2%) and Hsinchu County (7.1, 14.2%); the temple-heavy west moves two to
three points the other way (Yunlin: Christianity 2.2%, Taoism 26.4%).
Taitung and Hualien are the counties where a third of residents hold
indigenous status and most indigenous Taiwanese are Christian, so their
bound is likely near the truth; Taipei's is the artefact the bound exists
for, and its record says so. **No backtest exists and none is claimed**:
there is no county-level self-identification figure to score against, so
the estimate has no `backtest` key and its note says why.

**What remains unknowable.** Whether anyone in a given county has a
religion: the model repeats Pew's national 27.6% no-religion on Hualien and
on Taipei alike. Where mainlanders and their descendants live: the model
gives every county the same Hoklo-mainlander ratio, and the veterans'
villages of Taoyuan and the mountain counties' plains townships are not in
it. Any identity the register does not hold: new immigrants and their
children, who are in the Hoklo-mainlander remainder. Which of the sixteen
peoples an indigenous person belongs to, which the Council's table gives and
the composition does not carry.

## Derived values: what follows without reading more

`docs/MODELLING.md` measures what modelling the blank regions could and could
not do, and recommends building only the part that is arithmetic or geometry.
That part is built, and everything it writes is an *estimate* in
`common.py`'s sense: a gap that carries a guess, with status `derived` or
`modelled`, shares under `estimate` rather than under the field, and a note
saying nothing was read for the unit. Both statuses are registered as gaps in
Python and in the browser, so the choropleth, the group index, the filter
counts and the parent sums all treat an estimate as a gap; the panel shows it
under its own label, after the sentence that says what it is.

**Pooled unions.** Namibia split Kavango into East and West in 2013 and CGAZ
still draws one Kavango; Afrobarometer surveys each half and Wikidata counts
each. `SHAPE_IS_UNION_OF` declares the parts, and the build pools them within
each source file — respondents with respondents, people with people — into
one row named for the shape. Kavango now carries religion and ethnicity from
the survey and a population of 341,687 from Wikidata; the Southern Grenadine
Islands carry Carriacou's and Petite Martinique's 6,900 people. A pooled row
is a sum of published figures and is written as one, the way a parent summed
from its children is.

**Declared splits.** Bueng Kan was carved from Nong Khai in 2011; the 2000
census row for Nong Khai counted both. `ROW_COVERS_SHAPES` declares that, and
the build gives Bueng Kan a `modelled` copy of Nong Khai's religion — 99.1%
Buddhist — on the assumption that the old province was uniform inside, which
`MODELLING.md` measures to be false in about 45% of countries. The note says
so. Nong Khai keeps the published row untouched.

**Single-unit countries.** Monaco is drawn as one first-level unit, so its
religion and ethnicity are the country's own figures, written `derived`.

**Exact residuals: built, and empty.** Where a country's composition and
every unit's but one are known, the missing unit follows by subtraction — if
the national figure and the units' come from the same source, their
populations agree, the units name no group the national figure lacks, and no
share goes negative. Seven candidates, seven refusals, all on the first test:
a Factbook national over Afrobarometer units, whose difference is the
disagreement between two bodies and not a place. The one country that would
have passed, Kazakhstan, was a join failure instead — the 2021 census calls
the region Turkistan and the boundary file South Kazakhstan — and reads
directly now, 3.4 million people. When a parent and all-but-one of its
children are known, look for the unmatched name before the subtraction.

An estimate is never written on a field the country does not collect.
`check_no_estimate_on_policy_field` runs after every pass and fails the build
if one is.

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
  arithmetic. Singapore's regions are the same shape of answer: the shapes the
  roll-up saw as missing are uninhabited, which the adapter knows from the
  survey's own totals and the roll-up cannot, so the adapter sums them itself
  (see the Singapore section).

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

The country row honours the same declaration, for **all three** fields. It used
to honour two of them: `fetch_factbook.py` passed religion and ethnicity
through the policy gate and let language past it, so Japan, Turkey, Sweden,
Belgium, Austria, Algeria, Saudi Arabia, Iraq, Greece, North Korea, Afghanistan
and the rest each had every province saying that no census of theirs asks
language, while the country panel directly above them showed a Factbook list.
That is the map contradicting itself on one screen, and it is now one gate for
the three. Nothing else narrows: a country with no policy keeps exactly what
the Factbook says, and a declaration is never dated, because `dated()` stamps a
year onto a composition and onto nothing else.

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
  as what does exist. Re-checked since against the household survey that would
  otherwise stand in for a census -- see *Afghanistan: verifying a declaration,
  and the survey that does not exist* below.
* **Venezuela** -- the 2011 census asked indigenous and Afro-descendant
  self-recognition and not religion; `not_collected` for religion only.

### Mongolia: a questionnaire that runs to question 29

Mongolia's 2020 census asked ethnic group and religion, and the map carries
both for the aimags (see *Mongolia: a statistical office that has moved, and
22 books on the Internet Archive*). Language is declared `not_collected`
rather than left blank, and the declaration is read off the form rather than
inferred from a table that happened to lack a column.

* The individual questionnaire is reproduced in the appendix of the National
  Statistics Office's English national report. It runs from "What is your
  relationship with household head?" through gender, age, birthplace,
  migration, disability, education, literacy, employment and marital status
  to **question 29, "Do you have a religion?"** — whose answers are no
  religion, Buddhism, Christianity, Islam, shamanism and other — and asks
  about no language at any point.
* In the report's 298 pages the word "language" appears twice, and neither is
  a question: the definition of literacy, "a person who can read and write
  simple sentences in **any languages** was considered as literate", and sign
  language among the Washington Group's short set on functional difficulty.
* None of the report's tables, and none of the tables in the 22 aimag results
  books read for it, is a language table.

Ethnic group is the question Mongolia does ask about who a person is, 33
groups of it, and that is where this map carries the answer.

### Laos: 282 pages, and no language question

Laos's 2015 census asked ethnicity and religion, and the map carries both for
all 18 provinces and all 148 districts (see *Lao PDR: a census published only
for the country, and its own village file*). The third field is declared
`not_collected` rather than left blank, and the declaration is measured the
way Bhutan's was — against the census's own output rather than against an
empty response.

* The English results volume runs 282 pages. The words **"mother tongue"
  appear on none of them.** "Language" appears on six, and every occurrence is
  prose: the content and language of the questionnaire being tested, the
  enumerators recruited for their ethnic language skills so they could work in
  ethnic communities, the similarity of language and culture that sends Lao
  migrants to Thailand, and the compound "ethno-linguistic".
* None of the volume's tables is a language table. Its Appendix 1 lists them
  all, and they cross province with age, migration, literacy, schooling,
  economic activity, disability and housing.
* The village indicator table the provinces and districts are read from
  carries 68 indicators for each of 8,499 villages, ethno-linguistic category
  and religion among them, and no language variable.
* The *Socio-Economic Atlas of the Lao PDR 2015*, the census's own thematic
  atlas of 131 maps, has a section F "Ethnicity and Religion" — families,
  categories, religions — and no language map.

The obvious objection is the ethno-linguistic categorisation itself, and the
Atlas answers it in as many words: the term "indicates a categorization based
on a common ethnicity through self-identification mainly based on language".
It is an ethnicity answer sorted by linguists after the fact, not a language
anybody was asked to speak, and this map publishes it on the ethnicity field
for that reason. Publishing it a second time as language would be the
mis-match this project ranks below a gap — Pakistan's ethnicity row, in the
mirror.

### North Korea: 53 questions, one of which asks who you are

`NOT_COLLECTED_POLICY["PRK"]` declared religion, ethnicity **and** language,
and the declaration reached all 11 provinces and all 179 counties, so every
North Korean unit on the map said `not_collected` with a reason. What it did
not have was a measurement: the country had no section here, only its name in
a list, and the three notes said what the census does not ask without ever
saying what was read to find out. The declarations this project stands on are
backed by a page count and a term search — Laos's 282 pages, Bhutan's 1,798,
Timor-Leste's questionnaire running E1 to E77. This one now is too.

The check could have gone the other way and was run as though it would. North
Korea is not a country without a census. The **2008 Population Census** was
enumerated from 1 to 15 October 2008 by about 35,000 enumerators and nearly
8,000 team supervisors, under Cabinet Declaration No. 33 of October 2006, with
financial and technical support from UNFPA, and the **National Report**
(Central Bureau of Statistics, Pyongyang, 2009) was published — 278 pages,
53 tables, and all three questionnaires printed as annexes. The UN Statistics
Division serves it at
`unstats.un.org/unsd/demographic/sources/census/wphc/North_Korea/Final national census report.pdf`,
which is what was read; the directory above it answers 403 to an automated
reader, so the one other DPRK file it serves, the one-page preliminary
results, was reached by name rather than by listing.

**The form.** Annex 2, the CPF 2 questionnaire, is printed whole. It runs
**53 questions**: H1 to H14 on the household and the dwelling unit (members,
type of household, class of labour of the head, dwelling type, occupancy,
floor area, rooms, water tap, water source, toilet, heating installed,
heating used, cooking fuel), P1 to P29 on the person, and M1 to M10 on deaths
in the household in the twelve months before the census. **Exactly one of the
53 asks who a person is:**

> **P7  What is ____'s nationality?**  1 Korean  2 Others

The rest of Module 2 is household membership, where the person is registered,
relationship to the head, sex, date of birth, the four disability questions,
schooling and educational attainment, the post-secondary certificate and field
of study, usual activity, household economic activity and hours, industry,
occupation, class of labour, marital status, age at first marriage and births
in the past year. There is no religion question, no ethnicity question and
nothing about mother tongue or language. Annex 1 (CPF 1) is a listing form —
building, dwelling unit, household, name of head, address, counts — and Annex
3 (CPF 2-B) the shorter form for institutional living quarters. The Concepts
and Definitions section defines dwelling unit, household, head of household,
household member, institutional living quarters, institutional population,
nuclear and extended household, and class of labour, and defines none of the
three.

**The tables.** The List of Tables runs **Table 1 to Table 53**, and the one
table built on P7 is:

> **Table 5.  Population by Nationality, by 5-year age Group and by Sex** —
> 23,349,859 people, of whom **23,349,326 Koreans** and **533 of other
> nationalities**, and that is the whole of it. By age and by sex, and by
> nothing else.

Nationality is not written onto the ethnicity field. The Maldives entry above
settles the principle — a passport is not an ethnic group — and here the point
is moot twice over: Table 5 has no geography to put a composition on, and the
Scope and Coverage section says the enumeration covered "all Korean citizens
living in DPRK and people of other nationalities who have already acquired
Korean citizenship", so the 533 are the residue of a question about papers.

Searched over the text of all 278 pages for *religio*, *ethnic*, *mother
tongue*, *language*, *church*, *Buddhis*, *Christian*, *Chondo*, *Confucian*
and *faith*, **two pages match**, and neither is a table of anything:

* page 109, the note under **Table 22**: "Literacy refers to the ability of an
  individual to read and write a simple message in **any language**." That
  counts an ability and never records which language — the Maldives' ED1, in
  the mirror.
* page 200, one line of **Table 37**'s occupation list: "**Religious
  professionals** 103", 36 men and 67 women, between *Legal professionals* and
  *Archivists librarians and related professionals*. An occupation with a
  hundred people in it is not a religion composition, and publishing it as one
  would be the mis-match this project ranks below a gap.

*Ethnic* and *mother tongue* occur on no page of the report at all.

**And there is no survey standing in for it,** which is the question
Afghanistan's entry asks of any country in this position. The Central Bureau
of Statistics' own **Socio-Economic, Demographic and Health Survey 2014**
(December, Juche 104 (2015), 167 pages, served by `dprkorea.un.org`) matches
*religio*, *ethnic*, *mother tongue*, *language* and *nationality* on **zero
of its 167 pages**. The 2017 MICS, run by the same bureau with UNICEF, is the
one thing left unread: `unicef.org/eap` and the MICS repository on S3 both
answer **403** to a standard client and ReliefWeb's API answers **410 Gone**.
No User-Agent was spoofed to get past either, and its subject is the health
and nutrition of children and women.

So the declaration stands, and `scripts/common.py` now says what was read.

**What the 2008 census does publish by province** — recorded here so the next
reader does not search the report again. Of the 53 tables, **33 cross a
province** and one goes below it:

* population and households — Table 2 (by **city/district/county** and
  province, the only table below the first level), 3 (localities and their
  population by size-class), 4 (5-year age group by sex, urban/rural),
  6 (relationship to head and marital status), 8 (marital status 15+),
  12 (heads of households), 13 (households by type and size);
* fertility and mortality — 14 (live births in the past year and women by age),
  15 (the same by educational attainment), 16 (by class of labour), 17 (deaths
  by age and sex), 18 (maternal deaths by place of death);
* migration — 19 (residence five years ago), 20 (migrants by province of
  origin and province of destination);
* education — 23 (literacy status), 24 (currently attending school by level
  and single year of age), 28 (highest educational attainment), 29
  (post-secondary certificate type), 30 (field of study);
* work — 32 (usual activity status), 34 (usual activity by attainment), 36
  (major industry group), 38 (major occupation group), 40 (household economic
  activities), 41 (hours worked);
* housing — 46 (dwelling type by household size), 47 (occupancy status), 48
  (floor area), 49 (rooms), 50 (water supply), 51 (toilet facility), 52
  (heating system), 53 (cooking fuel).

The remaining 20 tables are national: 1, 5, 7, 9, 10, 11, 21, 22, 25, 26, 27,
31, 33, 35, 37, 39, 42, 43, 44 and 45. Nothing anywhere in the round is a
religion, ethnicity or language table, at any level.

**What was filled.** Table 2, so all 190 units carry a head count and a sex
ratio — see *North Korea* in the subnational sources table above and
`scripts/fetch_census/northkorea.py`. Two things about those figures are worth
keeping here rather than in 190 notes. The report writes its thousands
separator as a space, so a row's nine figures are told apart by the
publisher's own arithmetic — males and females adding to both sexes in each of
the three blocks, urban and rural adding to all areas in each of the three
columns, six equations that leave exactly one reading of the row and refuse it
if they leave none or two. And Table 2's universe is the civilian one: it
comes to **23,349,859** where **Table 1 counts 24,052,231**, and the 702,372
between them — 662,349 men and 40,023 women — are the people living in
military camps, whom the report allocates to no province. The census's own
preliminary results sheet is where that gets its name, printing a civilian
sub-total "living in regular households and in institutional living quarters"
against a total that "includes population living in military camps", 702,373
apart on the manual tallies the final figures replaced. So every sex ratio
here — 1,111 females per 1,000 males for the country against the 1,052 implied
by Table 1 — is a ratio among civilians, and every row says so.

### The Maldives: one question about who you are, and its answer is a passport

The Maldives was empty at all three levels -- one country row of Factbook prose,
13 atolls and 20 atolls below them with nothing. The obvious explanation is the
one to refuse: Article 9(d) of the constitution requires a citizen of the
Maldives to be a Muslim, so "100% Islam" is a sentence anyone could write, and
it is not a census result. Nobody was counted giving that answer. Putting it on
the map would be the mis-match this project ranks below a gap -- a figure with a
census's authority that no census produced -- so what was measured instead is
the census's own form and the census's own list of tables.

**The form.** The 2006 questionnaire is published through the IHSN microdata
catalogue as the entry for `MDV_2006_PHC_V01_M`
(`catalog.ihsn.org/catalog/4273/related-materials`, the 388 kB PDF): 16 pages,
the whole *Shaviyani Form -- Information on Households and Individuals*, issued
by the Ministry of Planning and National Development. Searched for *religion*,
*mother tongue*, *language*, *ethnic*, *nationality* and *Dhivehi*, exactly one
page of the sixteen matches, and the match is question **M4, "What is your
Nationality?", answered 1 Maldivian or 2 Foreigner**. The rest of the form is
household composition, the building, water, sanitation, lighting, fuel, waste,
tenure, education, activity and migration. There is no religion question, no
language question and no ethnicity question on it.

**The tables.** The Census 2022 results summary
(`statisticsmaldives.gov.mv/census-2022-results-summary/`) lists the round's
whole published output, and it is about sixty tables in five families:

| family | tables | what they cross |
| --- | --- | --- |
| Population | P1-P6 | place of enumeration, **nationality**, sex, locality, island, five-year age group |
| Employment | EC1-EC6 | labour force status, activity, industry, occupation, employment status |
| Housing | H1-H8 | type of living quarters, rooms, drinking water, assets |
| Migration | MG1-MG13 | place of registration, birth, usual residence, enumeration, **nationality** |
| Education | ED1-ED19 | literacy, attendance, grade, highest attainment |

Not one is a religion table. Nationality -- Maldivian or foreigner, the same
M4 -- is the only characteristic of that kind anywhere in the set, which is
the published half of the fact the questionnaire shows the collection half of.
The atoll profiles the Bureau has been issuing from the same round since 2024
say it a third time: Shaviyani's, 32 pages, is resident population, resident
Maldivians, resident foreigners, administrative and non-administrative islands,
and no more.

**Language is the Irish case, not an absence.** ED1, ED2 and ED16 cross
*literacy in mother tongue* with age, sex, atoll and island; ED3 and ED4 do the
same for English. Those count an **ability**. Which language the mother tongue
*is* never gets recorded, so there is no composition inside them, and deriving
"Dhivehi 100%" from the fact that Maldivians are literate in their mother
tongue would be inventing the very figure the table declines to collect. It is
the same distinction already written down for Ireland, whose census asks
whether a person can speak Irish and gets an answer that is a skill.

So all three fields are declared in `NOT_COLLECTED_POLICY["MDV"]`, and
`apply_collection_policy` carries the declaration down to all 13 first-level
and 20 second-level shapes. **No adapter and no atoll-level file were
written**, and that is the point rather than a shortcut: there is nothing to
join, and a per-atoll record would have to be bound through a boundary file
that does not nest. CGAZ draws the Maldives' first level as **13** units named
for administrative atolls (Haa Alif, Baa, Kaafu -- the country has 20 of those
plus Malé City) and its second level as **20** units named for the natural
atolls (North Thiladhunmathe, South Maalhosmadulu, Faadhippolhu), with `Male'`
used for two different second-level shapes and Gnaviyani/Fuvahmulah on
neither level. Measured against the geometry: **13 of the 20 second-level
representative points fall outside every first-level polygon**, and **9 of the
20 intersect no first-level polygon at all** -- several of the first-level
shapes are slivers of near-zero area, one of them a single point. Eleven pair
cleanly by overlap (South Nilandhoo to Dhaalu, Faadhippolhu to Lhaviyani, and
so on), which is the shape of the answer if anyone needs it: pair by
intersection area and bind by `shape_id`, the way `fetch_census/nepal.py`
binds the nine districts CGAZ labels wrongly. None of that has to be solved to
say truthfully that the census does not ask. It would have to be solved to
publish a number, and there is no number.

What this closes and what it does not: religion, ethnicity and language are
answered. **Population by atoll and island is published and is not here** --
`Atoll-Level-Indicator-Sheet-Population.xlsx` and
`Island-Level-Indicator-Sheet-Population.xlsx` under
`statisticsmaldives.gov.mv/mbs/wp-content/uploads/2023/09/`, plus tables P1-P6
as both XLSX and PDF. That is a real route, left open deliberately, and whoever
takes it will spend their time on the name-matching described above rather than
on the figures.

One thing the census site does not serve: `census.gov.mv/2022/` and every
directory under it answer 404 to a reader, though individual files beneath
`census.gov.mv/2022/wp-content/uploads/` still resolve. The Bureau's own
`statisticsmaldives.gov.mv` carries the same material and is what was read.

### Afghanistan: verifying a declaration, and the survey that does not exist

`NOT_COLLECTED_POLICY["AFG"]` already said that Afghanistan has never completed
a population census, so no census question on religion, ethnicity or language
exists. That stands, and nothing found here disturbs it. What it left open is
the question worth asking of any country in that position, because this map
answers it *yes* elsewhere: **is there a survey?** South Korea's provinces
carry a pollster's pooled web panel; 39 African countries carry Afrobarometer,
a sample of 53,444 people. A survey from a named institution, labelled as one
and carrying its own provenance, is a source this project accepts. Afghanistan
has the institution and the survey series -- the Central Statistics
Organization, now the NSIA, has run a nationwide household survey since 2003
that is **designed to be representative at provincial level** -- so the only
thing to establish was whether it asks the three questions.

It does not, and this was measured rather than inferred:

* **ALCS 2013-14 household questionnaire** (the ALCS 1392-93 form, printed as
  Annex III.1 and published at `catalog.ihsn.org/catalog/6557/download/80079`),
  45 pages. Searched for *religio*, *ethnic*, *tongue*, *language*, *Pashto*
  and *Dari*: **zero pages match**. The household roster asks name,
  relationship to head, age, sex, marital status, and the line numbers of
  spouse, father and mother. Nothing else about identity.
* **ALCS 2016-17 analysis report** (CSO, 2018, ISBN 978-9936-8050-7-1), 421
  pages, questionnaire annexed. Eleven pages match those six terms and not one
  is a table or a question: the SDG disaggregation boilerplate, an entrance
  exam interviewers sat on local culture, the languages the CAPI application
  was written in, the UN's definition of a refugee, and the Dari-or-Pashtu
  choice in the primary school curriculum.
* **NRVA 2011-12 report** (CSO, 2014), 238 pages. Two pages match, both in the
  metadata chapter, both saying that the report itself will be available in
  Dari, Pashtu and English.
* **Socio-Demographic and Economic Survey** (CSO with UNFPA, Bamiyan 2011 then
  Ghor and Daykundi 2012), the only sub-provincial enumeration since 1979 and
  the last open lead in `survey/findings/AFG.json`. Its own contents page lists
  population characteristics, literacy, educational attainment, migration,
  employment, functional difficulty, fertility, mortality and housing. None of
  the three is among them.

So the declaration is not merely "there is no census". It is that the survey
which would otherwise stand in for one has a published questionnaire and that
questionnaire carries none of the three fields -- which is a stronger claim and
a more useful one, because it tells the next reader that the ALCS is not worth
re-opening. The three reasons in `common.py` now say so. The claim sometimes
made that the 2011-13 NRVA/ALCS rounds carried language and ethnicity at
province level was tested here against the questionnaire and the report, and it
is not so.

**What the NSIA does publish, and where it can be reached.** Annual population
estimates by province and district, which is real and is not a composition.
Its own site cannot be read over a verified connection: `nsia.gov.af` and
`www.nsia.gov.af` serve, on both 443 and 8443, a Certum DV certificate issued
for `*.gsia.gov.af` and `gsia.gov.af` and for no other name, so every request
fails hostname verification. `gsia.gov.af` itself *does* verify once the
missing intermediate is fetched through the certificate's own AIA extension
(`scripts/probe_tls.py --chain` reports `VERIFIED handshake ok, TLSv1.3`), and
what it serves at the root is a 2.4 kB stub with no links. Verification is not
turned off for either, and no User-Agent is spoofed.

The estimates are reachable anyway, through HDX, the same route several other
countries here are covered by: dataset **`cod-ps-afg`, "Afghanistan -
Subnational Population Statistics"**, whose `dataset_source` is *National
Statistic and Information Authority (NSIA) Afghanistan*, maintained by OCHA
Afghanistan, CC BY-IGO, last modified December 2025. It carries admin-0,
admin-1 and admin-2 population as XLSX, with a gazetteer of **34 provinces and
402 districts**; the reference year is 2021 and the method is stated as
estimates built on a 2017 Flowminder/UNFPA micro-census and remote-sensing
study, not an enumeration. That is a population route and only a population
route, and it is left open here rather than taken: CGAZ draws 398 second-level
units against the gazetteer's 402, so it needs the same kind of careful,
per-district reconciliation that Nepal's shape bindings needed, and it would
fill no part of the religion, ethnicity or language gap this section is about.


### Bhutan: 1,798 pages, and a census that asks none of the three

`NOT_COLLECTED_POLICY["BTN"]` declares religion, language **and** ethnicity,
which is the strongest form of the claim this project makes about a country,
so it is worth recording exactly what was read to support it. Bhutan is not a
country without a census: the 2017 Population & Housing Census was enumerated
over three days from 30 May 2017 by 9,750 enumerators, it reached every
dzongkhag, and it published more than most. It simply does not ask.

Both halves of the round were swept, page by page, over the text of every page:

* **National Report** (NSB, 2018, ISBN 978-99936-28-50-7), **288 pages**.
  Searched for *religion*, *ethnic*, *tongue*, *Lhotshamkha* and *Nepali*:
  **two pages match, and both match on Lhotshamkha alone**. Page 24 is census
  publicity — radio talk shows advocating the census "were held in Dzongkha,
  Sharchopkha, and Lhotshamkha". Page 42 is the definition of literacy, "the
  ability to read and write a short text in Dzongkha, English, Lhotshamkha, or
  any other language". *Religion*, *ethnic*, *mother tongue* and *Nepali*
  occur on no page of the report at all. Its chapters are demographic
  characteristics, education, health, labour and employment, migration,
  housing and amenities, and household asset ownership, at national, dzongkhag
  and thromde level.
* **Dzongkhag Series**, the twenty volumes, **1,510 pages** read as one
  document. Searched for the same five terms and *Hindu*: **twenty pages
  match, one per volume, and every one is the same sentence** — that literacy
  definition again. Not one occurrence of *religion*, *ethnic*, *mother
  tongue*, *Nepali* or *Hindu* in fifteen hundred pages. Each volume runs
  introduction and administrative set-up, demographic characteristics,
  education, health, labour and employment, migration and housing.

A definition of literacy naming three languages is not a language composition;
it is the set of scripts a test card could be written in. The 2005 round is
the same, and its own list of what it collected stops at housing.

**What the census does ask that looks close, and why it is refused.**
Citizenship — Bhutanese against non-Bhutanese — is published down to gewog,
and it is not read here or anywhere else on this map as a proxy for ethnicity.
Citizenship is precisely the contested variable in Bhutan: the 1985
Citizenship Act is how much of the Lhotshampa population lost its legal
standing before leaving. A map that quietly relabelled that column "ethnicity"
would be making a claim about people the census took care not to make.

**So the national figures on Bhutan's country row are not Bhutanese.** The
Factbook's religion vector is not from either census — PHCB 2005 has no
religion table at all — and the State Department's religious freedom report
attributes the same split to Pew. There is no Bhutanese figure of any kind to
prefer to it, at any level.

**What was filled instead.** Table 2.1 of each volume prints Male, Female and
Total for every gewog, every town and the dzongkhag itself, so the twenty
volumes give a head count and a sex ratio for 20 dzongkhags and 205 gewogs.
Both are the dzongkhag's own figures; the sex ratio is taken only where the
publisher's two halves reach the total printed beside them, and a row that
does not add up keeps its head count and says in its gap why it has no ratio.
The national report's own row — 380,453 males and 346,692 females of 727,145 —
is the control the twenty volumes are reported against, and is not written
onto any record here.


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

### South Korea: nationality as ethnicity, by the owner's decision

Korea's census asks no ethnicity question, and the seventeen provinces and
228 districts said so (`NOT_COLLECTED_POLICY["KOR"]`, "South Korea's census
does not collect ethnicity") for as long as the map read only what a census
asks. What the state does count is **nationality**: every Korean national is
on the resident register, and every foreigner staying more than ninety days
registers with the immigration office under Article 31 of the Immigration
Act, by country of nationality. On **19 September 2026** the map's owner
decided that Korea's ethnicity field should carry that count as a real
composition under `ethnicity_basis: "nationality"`, the way Japan's
prefectures carry their census's nationality table. The `KOR` entry left
`NOT_COLLECTED_POLICY` that day; the substance of the declaration (no
ethnicity question is asked) is now the second sentence of every row's
note. `scripts/fetch_census/korea_nationality.py` is the decision, and it is
a count, not a model: nothing in it estimates anything.

**What was read**, all from the runner, no key. Neither host answers a
runner reliably -- data.go.kr's file endpoint times out about as often as
it answers, and the register's form drops a connection every few requests
-- so every file a run reaches is kept under `data/raw/korea`, which
.gitignore admits, and a later run reads the copy;
`--fetch-only` asks for whatever is still missing and stops, so a run that
reaches one host banks its file while another is down. With all three
banked the reader needs no network at all.

* **Foreign residents.** The Ministry of Justice's *registered foreign
  residents by city/county/district and nationality* (법무부_시군구별 국적별
  등록외국인 체류현황, data.go.kr dataset 15108413,
  `https://www.data.go.kr/data/15108413/fileData.do`), a zip of two cp949
  CSVs, 2022 and 2023, served without a key from the portal's file endpoint
  (`fileDownload.do?atchFileId=FILE_000000002903067`). The 2023 file, at 31
  December 2023, has 500 rows -- 250 units by sex, the districts of a city
  that has them (수원시 장안구 ...) listed separately -- and 201 columns: 시도,
  시군구, 성별, a total, and 196 nationalities from 한국계중국인 to 기타. The
  reader sums the sexes and a city's districts into the city, and refuses a
  row whose nationalities do not add up to its printed total; the 250 fold
  into 229 units, which are the 228 shapes and Yeonggwang-gun. Sejong has
  no 시군구 at all and the file writes a bare "0" for it.
* **Koreans.** The Ministry of the Interior and Safety's resident
  registration population (주민등록 인구통계) for December 2023, from the
  Ministry's own site (`https://jumin.mois.go.kr/statMonth.do`). The site
  serves the table only through a form: a dozen fields posted to
  `downloadCsv.do?searchYearMonth=month&xlsStats=1` (the runner's probe of
  the page printed them; `scripts/probe_post.py` exists to make that one
  request) come back as a cp949 CSV of "행정구역 (code)", 총인구수 and 세대수.
  One request with the province level "A" lists the seventeen provinces and
  the national row (51,325,329 at December 2023); one request per province
  lists its districts, with a city's own districts beside the city. What
  tells a city's district from a district of a province is that it names
  three levels -- "충청북도 청주시 상당구" against "충청북도 영동군"
  -- and not the code: 증평군, split off from 괴산군 in 2003, is
  4374500000, a county of its own with a non-zero fifth digit sitting
  beside 영동군 at 4374000000, and reading the code as a parent's dropped
  its 37,484 people out of North Chungcheong. Sejong is a province that is
  one city: the register repeats its name a level down, and the Ministry of
  Justice's file writes a bare "0" in the 시군구 column for it, so both
  are keyed by the province's name and meet. The listing reads 228 district
  rows, one per shape, and Sejong's. data.go.kr's copy of the same table
  (dataset 3033301) is offered on application only, and its file endpoint
  never answered the runner (`Connection timed out`, four times).
* **The national check.** The Ministry's *registered foreign residents by
  nationality by year* (연도별 등록외국인 국적(지역)별 현황, data.go.kr
  dataset 15100019), a 53 KB cp949 CSV of 년, 국적지역 and 등록외국인 수,
  2011 to 2025, 195 nationalities for 2023. The portal's file endpoint
  timed out on it fifteen times running while handing over the district
  zip on request, so the dataset page's own download servlet is tried
  beside it and whichever answers is kept.

**What the labels mean.** "Korean" is everyone on the resident register,
naturalised citizens and people of any ancestry included. "Korean-Chinese"
is the immigration statistics' own category 한국계 중국인 -- Chinese
nationals of Korean descent, the 조선족 -- which the Ministry lists apart
from other Chinese nationals and the map keeps apart, because folding it
into "Chinese" would hide the largest foreign community in the country;
"Chinese" is every other Chinese national. Nationalities with at least
10,000 registered residents nationally are named (adjectives, singular:
Vietnamese, Thai, Uzbek, Nepalese, Filipino, Cambodian, Indonesian,
American, Burmese, Sri Lankan, Mongolian, Japanese, Russian, Kazakh ...);
the rest are "Other nationalities". A nationality above the threshold that
the label table does not know is a refusal, not a silent fold. Cambodian,
Malaysian, East Timorese, Hong Konger and Ghanaian joined the group tree's
"Other national identities" node under "Stated as a nationality"; the rest
were already placed.

**What is not counted, said on every row.** Registered foreigners are those
who registered under the Immigration Act. Overseas Koreans of foreign
nationality living in Korea on a domestic residence report (국내거소신고,
the F-4 status, some half a million people, most of them Korean-Chinese)
are a separate register and are not in the file, nor are short-term
visitors or the undocumented; the resident register counts Koreans, not
foreigners. So the foreign share is of *registered* foreign residents and
runs below the share of all foreigners present, and the Korean-Chinese
figure in particular is the registered part of that community.

**The shapes.** All 228 districts are matched. geoBoundaries CGAZ draws
twenty of them under the wrong province or under the country itself --
Seoul's Eunpyeong-gu under Gyeonggi; Incheon's Seo-gu, Gyeyang-gu and
Ganghwa-gun under Gyeonggi and Ongjin-gun under the country; Gwangju's
Dong-gu, Seo-gu, Nam-gu and Gwangsan-gu under South Jeolla; Busan's
Gangseo-gu and Gijang-gun under South Gyeongsang and Yeongdo-gu under the
country; Daegu's Dalseong-gun and Gunwi-gun under North Gyeongsang;
Daejeon's Dong-gu under North Chungcheong; Gyeongbuk's Uljin-gun under
Gangwon; Jeonnam's Sinan-gun under the country. Each of those rows names the
province the shape is drawn under as its `parent_name`, because that is the
only way the join finds a Dong-gu among six, and its note says which
province it is actually part of; the province rows sum the districts by
their real province. Jeonnam's Yeonggwang-gun has no shape at all and counts
in South Jeolla only. Cities with districts (Suwon, Seongnam, Goyang, Yongin,
Ansan, Anyang, Cheongju, Cheonan, Jeonju, Pohang, Changwon) are one shape
each and are summed from the file's district rows.

**Checks.** The reader refuses to write anything if a row's nationalities
do not sum to its printed total, if the seventeen provinces are not the
seventeen the file is known to write, if the register's districts do not
sum to its province row or its provinces to its national row, if a unit's
shares do not make 100 within 0.3 points, if any of the 228 shapes has no
row, or if a nationality above the naming threshold has no label. The
national check is the last of them: the district file must sit within half
a point of the Ministry's own published national figure, and the run of 19
September 2026 found them identical -- **1,348,626** registered foreigners
either way, 2.56% against 51,325,329 resident-registered Koreans, and every
named nationality agreeing to the person (Vietnamese 227,930, Uzbek 55,239,
Thai 40,062, Sri Lankan 28,258, Taiwanese 17,704). The two files are the
same register counted at the same date, one by district and one by
nationality, so no caveat sentence was needed on the rows.

**What it comes to.** Seventeen provinces and all 228 districts, each a
count. Nationally 97.4% Korean; the most foreign districts are Yeongam-gun
in South Jeolla at 13.6% (the Samho shipyard), Eumseong-gun at 11.6% and
Jincheon-gun at 8.0% in North Chungcheong, Pocheon-si at 9.3%, Seoul's
Jung-gu at 7.9% and Ansan-si at 7.7%. Korean-Chinese are the largest
foreign group in Seoul's south-west -- 3.8% of Yeongdeungpo-gu and of
Guro-gu -- and 2.9% of Ansan.

**Also found, and not used.** The Ministry of the Interior and Safety's
annual *foreign residents by local government* (지방자치단체 외국인주민 현황,
1 November 2023: `https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000014&nttId=113261`,
a 4.2 MB xlsx), which counts foreign nationals of both registers -- the
F-4 residence-report population included -- by district and by some twenty
nationalities, beside the resident-registered Koreans. It would put the
Korean-Chinese at their full size. `mois.go.kr` answered the runner about
one request in two (`Connection timed out` on the rest), and the two
registers above answered every time, so the registers were read first; the
xlsx is the next pass.

### Timor-Leste: the questionnaire itself, all 77 questions of it

Timor-Leste's declaration is read off the instrument rather than off an absent
table. INETL reproduces the 2022 questionnaire in full as Annex III of the
census main report, and its individual module runs from E1 to E77 with no
ethnicity, race, tribe or ancestry question anywhere in it -- religion is E57
and mother tongues is E58, and those two are the country's identity variables.
Both of them are on the map, from the 2015 round, so this is a declaration
about one field and not a country written off. The evidence, and what was
looked at to be sure of it, is under "Timor-Leste: two questions asked, a third
that is not" above.

### Papua New Guinea: one office, two publications, and one figure per province

Papua New Guinea carried nothing at all below its own row before this: 22
provinces and 87 districts of bare `not_available` on every field, and no
`NOT_COLLECTED_POLICY` entry. The National Statistical Office
(`www.nso.gov.pg`) answers an automated reader without complaint, and two of
its publications are what the country now carries.

**What its site holds, all of it.** The site is WordPress, and its sitemap
names every file it publishes: `wp-sitemap-posts-wpfd_file-1.xml` (39 KB)
lists **289 file posts** and `wp-sitemap-taxonomies-wpfd-category-1.xml` the
**33 download categories** they sit in. Most of the 289 are job advertisements
and position descriptions. Everything demographic on the whole site is this:
the 2024 census Final Figures; the 2011 and 2000 National Reports (three
copies each, under `population-housing`, `nso-digital-library` and
`education`); the 2011 Final Figures booklet and brochure (two copies each);
four regional "Census Figures by Wards" tables; twenty-two *Population
Estimate Results*, one per province, from the 2021 estimates; the 2006 and
2016-18 DHS reports; the 2009-10 HIES summary tables; and the 2022
Socio-Demographic and Economic Survey. **There is no provincial census
report, and nothing below the province carries religion.** A Wayback CDX
listing of every PDF, XLS and CSV ever archived under `nso.gov.pg` (400 rows,
the whole domain from 2004 to 2026) adds nothing of the kind either. That
matters, because the 2011 National Report's own foreword says the release is
"The National Report and the 22 Provincial Reports" -- so the provincial
tables exist and are not published.

The 2011 Final Figures booklet answers **HTTP 415 Unsupported Media Type**
from `/download/51/`, but the second copy of it, at
`/download/77/nso-digital-library/2246/`, serves: 5.9 MB, 40 pages, and the
word *religion* on **none** of them -- it is population counts by ward, LLG,
district and province, and its own foreword says "Detailed reports covering
other demographic and social characteristics ... will be produced and
released progressively". The four ward tables are the same kind of thing
(Southern Region: 3.0 MB, 35 pages, religion on zero), and so are the 22
provincial *Population Estimate Results* (Western: 2 pages, "total population
count at the National, Provincial, District and LLG levels and also by age
and sex"). The 2000 National Report is a 22 MB scan with no text layer at all
-- 109 pages, **zero** extractable characters -- and all three of its copies
are the same 22,359,391 bytes, so nothing short of OCR would read it.

**The two files read.** `scripts/fetch_census/png.py` reads both with pypdf:

| File | What it gives |
| --- | --- |
| `.../4310/2024-national-population-census-final-figures_web.pdf` (35 pp, Oct 2025) | Table 1: population, males, females and sex ratio for the 22 provinces. Twenty-two Provincial Snapshots: the same three counts for each of the 96 districts it lists. |
| `.../2152/png-national-report-2011-census.pdf` (100 pp) | The Summary Indicators row "Main religion (% of population)" for each of the 22 provinces -- one denomination and one share. |

Both are fetched with `Accept: application/pdf`. The office's download plugin
negotiates on that header and hands a client that does not send it an HTML
page, which is what the first run got and what pypdf refused; asking a server
for the representation it publishes is not claiming to be a browser, and
nothing here does that.

**Religion, and why it is one row.** The 2011 census asked religion -- the
report's glossary defines it, chapter 2 reports it, and Table 2.4 gives the
country's Christian / non-Christian / no religion / not stated split with
Figure 2.1's eleven denominations under it (Roman Catholic 26.0, Evangelical
Lutheran 18.4, Seventh Day Adventist 12.9, Pentecostals 10.4, United Church
10.3 …). For a **province** it publishes exactly one figure: the largest
denomination and its share of the citizen population. A term sweep of all 100
pages for *religion*, *Catholic*, *Lutheran* and *Adventist* returns 14
pages, and none of them is a provincial religion table; the 2024 Final
Figures mention religion on none of their 35.

So each province carries a one-row composition -- Bougainville "Roman
Catholic 68.4%", Morobe "Evangelical Lutheran 67.0%", Eastern Highlands
"Seventh Day Adventist 39.6%" -- and the panel labels it for what it is
without being told to: a composition that falls short of 100 draws the chip
*describes 68.4% of the population*. **That is the whole difficulty with this
country's religion**, and it is worth stating plainly: the shares run from
**19.7%** (Southern Highlands and Hela) to **68.4%** (Bougainville), the
median province is described at about 38%, and Central Province -- the one
the owner asked about -- at 40.0%. Seventeen of the 22 are under half. The
adapter prints all 22 shares into the run's log and **refuses** a run in
which any of them reached 95%, the threshold the dashboard stops calling a
composition partial at: one denomination shown as a complete composition
would be a quiet untruth, and this is the kind the project ranks worse than
an empty cell. Each record's note now opens by saying the figure is the
largest denomination, and says what the rest is -- unpublished, not
uncounted. The denominational pattern is the real one the report describes:
ten provinces lead Roman Catholic, four Evangelical Lutheran, four United
Church, and Anglican, Seventh Day Adventist and Evangelical Alliance lead one
or two each.

**The rest of each province is sold, not published.** Appendix 4 of the 2011
National Report (page 95) is a price list, and it is the answer to where the
missing three fifths of each province went:

| Product | What it holds | Price |
| --- | --- | --- |
| PNG 2011 Census **Basic Tables** | "a set of 31 cross-classified tables covering the main census topics at national **and provincial** level for all sectors, urban sector and rural sector" | K40.00 per set |
| PNG 2011 Census **Provincial Report** | "an easy to read commentary with accompanying statistical tables and graphs ... at provincial level" | K40.00 per province |
| PNG 2011 Census **Table Retrieval System** | a CD-ROM of the basic tables at national, provincial, urban/rural, **district and statistical LLG** level, with retrieval software | K2,000.00 |
| PNG 2011 Census **Community Profile System** | a CD-ROM of counts and profiles from the census unit upwards | K2,000.00 |
| PNG 2011 Census **User Service** | "NSO will prepare specialized tables to a user's specifications" | on application |

The provincial religion table is inside the K40 set and the K2,000 CD-ROM.
Neither is a download; the office's contact block gives a post-office box and
two telephone numbers. This is not a country that failed to count religion,
nor one whose tables were lost: it is one that charges for them, and the
figure on the map is the free summary of the priced product.

**Reading a kerned figure.** Both PDFs are typeset so that pypdf reads a
figure in groups -- Milne Bay's 412,158 comes out as `41 2 ,15 8`,
Bougainville's 367,093 as `3 6 7,0 9 3` -- and a space inside a number is
indistinguishable from the space between two numbers. The reader therefore
does what `vietnam.py` does: take every digit on the row in order, try every
cut of that string into the numbers the row is supposed to carry, and keep
the one where the census's own arithmetic holds -- males plus females equal
the total, and the printed sex ratio is 100 males per females. Across the 22
province rows and the 96 district rows exactly one cut satisfies that every
time; a row with none, or with two, refuses the run. The same files also read
a capital away from its word ("T elefomin", "T awae/Siassi"), which is
repaired before a name is matched.

**Districts: 71 of 87, and why the other 16 are empty.** The boundary file
draws the 87 districts of the 2011 layout; the 2024 booklet tabulates 96 in a
later one, and says PNG now has 98. Where a province's 2024 districts still
partition its shapes the shapes are written: name for name, under a declared
alias where the spelling moved (Mendi for Mendi/Munihu, Hagen Central for Mt
Hagen, Kainantu for Kainanatu, Karimui for Karimui/Nomane, Huon Gulf for
Huon), or as a declared union where one shape's own name names the two
districts that now cover it -- **Kairuku - Hiri** = Kairuku + Hiri-Koiari,
**Lagaip/Pogera** = Lagaip + Pogera Paiela, **Komo/Magarima** = Komo Hulia +
Magarima -- and the National Capital District, one shape holding the city's
three Moresby seats. Each written province's districts must then add to the
province's own printed total, and land on exactly as many shapes as the
boundary file draws for it, or the run refuses.

Four provinces have one 2024 district that no shape corresponds to: Western's
**Delta Fly**, Northern's **Popondetta**, Morobe's **Wau/Waria** and West New
Britain's **Nakanai**. Each was carved out since 2011 and the booklet does not
say from which district, so any of that province's shapes may have lost
ground to it. None of those four provinces' district shapes is written --
16 in all, 3 + 2 + 9 + 2 -- and each of the 16 carries a record saying so and
naming the district that cannot be placed. A count on the wrong one of them
would be invisible, which is the failure this project ranks above an empty
cell.

**Ethnicity and language are declared, not left blank.** Appendix 1 of the
2011 National Report lists what the census collected: "Basic demographic,
social and economic information on age; sex, marital status, religion,
migration, economic activity, occupation, industry, fertility, mortality and
household income generating activities were collected. A total of 33
questions were asked using a one-page census questionnaire." Neither
ethnicity nor language is among them, and the report has no table of either.

Language needs the careful wording, because the census does ask about
languages -- and it asks the wrong question for this map. Table 4.6 is a
**literacy rate by language**: the share of people aged 10 and over who can
read and write English (48.9%), Pidgin (57.4%), Motu (4.7%) or Tokples
(55.8%). Those are four overlapping abilities, three of them in lingua
francas, and the fourth is the report's own catch-all: its glossary defines
Tokples as "Pidgin word meaning 'language of my place'. The local language of
a traditional area belonging to a tribe or clan" -- all 800-odd of them under
one heading. They sum past 100 and describe nobody's mother tongue, and
turning them into a composition would be inventing a statistic. Both fields
are `not_collected` in `NOT_COLLECTED_POLICY["PNG"]`, which also fixes the
country row, whose ethnicity was a bare `not_available` with the Factbook's
free text ("Melanesian, Papuan, Negrito, Micronesian, Polynesian") beside it.

The **2016-18 Demographic and Health Survey** does ask religion, in eleven
categories, and it is provincially representative -- its Table 3.1 gives the
weighted sample for all 22 provinces. It publishes religion for the country
only (Roman Catholic 24.9% of women, Seventh Day Adventist 13.7%, Evangelical
Lutheran 12.5%, United Church 10.4%), and no table in its 519 pages crosses
it with province, so it would not fill a provincial gap either.

**The regional routes, measured.** The Pacific Community is the obvious place
to look for a Pacific census tabulation, and it was asked three ways.
`pacificdata.org`, the Pacific Data Hub's CKAN, answers **403** at
`/data/dataset` and at `/data/api/3/action/package_search` alike -- the
"blocks browsers, serves the API" pattern does not hold here. `sdd.spc.int`
serves its country page but puts an interstitial challenge on its root and
**403** on its search. `microdata.pacificdata.org` answers **403**. What does
answer is PDH.stat's SDMX service,
`stats-nsi-stable.pacificdata.org/rest/dataflow/SPC`, which returns 357 KB
listing **127 dataflows** -- and not one of them is religion, ethnicity or
language: the population ones are `DF_POP_AGE`, `DF_POP_SEX`,
`DF_POP_URBAN`, `DF_POP_DENSITY`, `DF_POP_PROJ`, `DF_POP_COAST`,
`DF_POP_LECZ`, beside `DF_MARITAL_STATUS`, `DF_HHCOUNTS`, `DF_VITAL`, the
SDG series and the rest. SPC's own digital library carries the same three PNG
census documents the NSO hosts and no provincial report.

HDX has **`cod-ps-png`**, OCHA's common operational dataset: the 2011 census
population at admin levels 0 to 3, sourced from the NSO, on the same district
layout the boundary file draws. It is a clean join and it is not used, because
the 71 districts that are written carry the 2024 count and a 2011 figure
beside them on the other 16 would put two censuses on one level. It remains
the obvious way to fill those sixteen if the mixture is ever wanted. Nothing
else on HDX carries PNG religion: a 50-row search returns airports, roads,
conflict data, WorldPop rasters and the World Bank indicator mirrors.
`pngnri.org`, the National Research Institute that publishes the *District
and Provincial Profiles*, answers **403** to an automated reader; the
Internet Archive's 1,108 copies of its PDFs are education and development
indicator sheets, not census tables (see the table below).

**Round two: every other way in, and what it answered.** The one-row
composition was not accepted without a second search, this one for anything --
census, survey or transcription -- that publishes religion for a Papua New
Guinean province. Nothing does. Each route, and the measurement that closed
it:

| Route | Asked | Answered |
| --- | --- | --- |
| **DHS StatCompiler API**, indicators | `api.dhsprogram.com/rest/dhs/indicators?countryIds=PG` | 2.2 MB of indicator JSON. The only labels containing *religio* are `ML_NSRC_N_REL` "Net source: Religious institution" and `DV_STPS_W_RLG` "Sought help to stop violence from religious leader". Religion is a background characteristic in DHS, never an indicator, so **StatCompiler cannot serve it by region**. `surveycharacteristics` (1.8 KB) and `surveys` (0.9 KB) for PG do not mention it either. |
| **DHS 2016-18 final report** | `dhsprogram.com/pubs/pdf/FR364/FR364.pdf` | 5.8 MB, **519 pages**, religion on **6**: p. 69 (chapter intro), **p. 75 Table 3.1** (the country's distribution -- Roman Catholic 24.9% of women, Evangelical Lutheran 12.5%, Pentecostal 9.0%, Evangelical Alliance 3.8%, Anglican 2.7%), p. 264 (prose on circumcision), **p. 278** (one table with a *province* panel and a *religion* panel, side by side and never crossed), pp. 420 and 496 (the questionnaire's 11 categories). No table crosses religion with province. |
| **DHS microdata** | `api.dhsprogram.com/rest/dhs/datasets?countryIds=PG` | Names **30 files** (`PGHR71DT.ZIP`, `PGIR71FL.ZIP` …). They are served only to a registered account that has stated a research purpose. Not attempted: a gate is a measured result, not an obstacle to climb. |
| **2022 Socio-Demographic and Economic Survey** | the NSO's nine thematic workbooks | The survey **does** publish religion: `02_2022_png_sdes_demographic-characteristics.xlsx`, sheet **T2.4**, "Percent distribution by religion" -- Roman Catholic 25.8%, and so on -- but its columns are *Total, Urban, Rural* by sex and nothing else. The Key Indicators Report (7 pp) says why: the SDES is "a nationally representative household survey" of **321 sample census units** giving indicators "at the national level". It has no provincial estimates to give. |
| **2000 National Report** | `/download/51/…/2151/`, `/download/77/…/2247/`, `/download/101/…/2876/` | All three copies are the same file: 22,359,391 bytes, **109 pages, zero characters**. A scan with no text layer. Only OCR would read it, and nothing else publishes what is in it. |
| **The 2000 census on the NSO's old PRISM site**, via the Internet Archive | `web.archive.org` copies of `spc.int/prism/country/pg/stats/*` | The CDX listing (39 KB) names 78 candidate files: GDP, CPI, business census, labour force, education. The 2000 census page itself (capture of 2004-03-10, 15 KB) links **no tables**, only site navigation. `popdemog.htm` (46 KB) does carry a *Religion* block -- and it is three national rates, "rate of religious affiliation" christian / non-christian / none. `PNG-Tab1.xls` (16 KB) is a national population summary by age and sex. |
| **2011 National Report, read whole** | 100 pages, term sweep and pages 26-34 read out | Religion is on pp. 26-30 (Summary Indicators, the one provincial row), pp. 32-34 (Table 2.4, the country by affiliation for 2000 and 2011; Figure 2.1, the country's eleven denominations; Figure 2.2, non-citizens) and p. 85. **No appendix table of religion by province exists**; Appendix 4 is the price list above. |
| **2024 census Final Figures** | 35 pages | Religion on none of them; the preface says detailed demographic information "will be released progressively". |
| **Wikipedia** | *Religion in Papua New Guinea* and the province articles | The article has one wikitable, the **2000 census's national** denominations (Catholic 27.0, Evangelical Lutheran 19.5, United Church 11.5 …), and its 2011 figures are the national ones this project already has. The province articles (Central, Morobe, East New Britain, Enga) carry tables of districts, premiers, governors and electorates, and **no religion table**. A transcription would have been publishable; there is none to transcribe. |
| **PNG National Research Institute**, via the Internet Archive | `pngnri.org` answers 403 live; the Archive holds **1,108** of its PDFs | They are the NRI's atlas sheets -- three per province, `P01_themeInd01.pdf` and the like -- and the first of them is "Universal Basic Education -- Access Rate, Districts of Western Province 2019". Education indicators mapped from census data, not religion. |
| **The Internet Archive's text collection** | `archive.org/advancedsearch.php?q=papua+new+guinea+census+report` | `numFound: 6`, and not one of them is a PNG census document (a CIA reading-room memo on Western Sahara, two VOA broadcasts …). |
| **Candidate hosts that do not exist** | `nada.nso.gov.pg`, `microdata.nso.gov.pg`, `png.prism.spc.int` | All three fail to resolve (`Name or service not known`). The NSO runs no microdata catalogue of its own. |

Carried over from the first round, and still true: `pacificdata.org` and
`microdata.pacificdata.org` answer **403**, `sdd.spc.int` puts a challenge on
its root and 403s its search, PDH.stat's SDMX service lists **127 dataflows**
with no religion among them, and HDX has `cod-ps-png` (population only) and
nothing else for the country.

What would fill this gap is a purchase, a data request to the office
("specialized tables to a user's specifications"), or a library holding of
one of the 22 Provincial Reports. **The ARDA / World Religion Database and
Joshua Project are not that.** They model denominational shares from partial
inputs; putting their provincial numbers here would replace a true "we know
40% of this province" with a false "we know all of it", and the map's rule is
that a modelled figure may only ever appear as an `estimate(MODELLED, …)`
and only with the coordinator's agreement. None is used and none is
proposed.

**What the file comes to.** `data/processed/png.json`: 22 provinces with the
2024 census population and sex ratio and the 2011 census's main religion, and
87 districts of which 71 carry the 2024 count and 16 carry the reason they do
not. The provinces add to the printed 10,185,363; the 2024 booklet's own 2011
comparison (7,275,324) is the whole population where the 2011 National
Report's tables count 7,254,442 citizens in private dwellings, which is the
universe every religion share here is a share of.

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
