#!/usr/bin/env python3
"""Join boundaries and demographics into the per-entity records the app loads.

Inputs
------
* ``data/raw/boundaries/geoBoundariesCGAZ_ADM{0,1,2}.gpkg``  geometry + shapeIDs
* ``data/processed/admin0.json``                             Factbook country records
* ``data/processed/cities.json``                             Natural Earth largest cities
* ``data/curated/admin1_seed.json``                          hand-checked census rows
* ``data/processed/{us_*,uk_*,canada_*,brazil_*,eurostat_*,australia_*,india_*}.json``
  and ``wikidata_admin{1,2}.json`` -- whichever adapters have been run

Outputs
-------
* ``site/data/admin0.json``           every country, loaded up front (small)
* ``site/data/admin1/{ISO3}.json``    lazy-loaded on country selection
* ``site/data/admin2/{ISO3}.json``    lazy-loaded on admin-1 selection
* ``site/data/search-index.json``     flat id/name/level/parent rows for MiniSearch
* ``site/data/coverage.json``         per-country, per-field availability matrix

The join key is geoBoundaries' ``shapeID``; statistical sources are matched to it
by normalised name within a country, because no agency publishes shapeIDs.  Every
match records *how* it matched so a bad join is auditable rather than invisible.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from collections.abc import Sequence
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import canonical_groups
import group_tree
from common import (  # noqa: E402
    DERIVED, MODELLED, NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, RAW, ROOT,
    apply_collection_policy, collection_gap, estimate, gap, is_estimate, is_gap,
    known_as, log, measure, read_json, repair, respell, write_json,
)

SITE_DATA = ROOT / "site" / "data"
BOUNDARIES = RAW / "boundaries"

# Adapter outputs, in increasing order of authority: later files win.
ADAPTER_FILES = [
    # First of all, because it is a secondary tabulation of other people's
    # studies rather than a study: CLEAR Global's language files. Each one
    # names the source it was built from -- an IPUMS extract of a census, a
    # DHS or MICS round, an Afrobarometer round, a humanitarian needs
    # assessment -- and several of those sources are on this map already in
    # their own right. Where they are, the original must win, which is what
    # this position buys: 660 first-level units in 46 countries, filling a
    # language field no one else here fills and overwriting none.
    "clear_global_language.json",
    # Then Afrobarometer, a survey where every other file below is a count.
    # Ethiopia, Mali and South Africa already carry
    # census figures and must keep them, and because merge_adapter works field
    # by field this still fills a field a census left empty without touching
    # one it filled.
    # The three survey files run oldest first, which is lowest first: a
    # later file wins, so each round is there to fill what the newer ones
    # are short of and never to overwrite them.
    # Rounds 5 and 6 first, and only for Burundi and Egypt -- the two
    # countries Round 9 does not survey at all. Nothing else on the map
    # writes to either today, so the order costs nothing; it is here because
    # a survey ranks below a count whatever happens to be present.
    "afrobarometer_r56.json",
    # Then Round 8, for language alone. Round 9 is two years newer and
    # reaches 442 regions in 39 countries against Round 8's 356 in 34, so
    # Round 8 fills a region Round 9 is short of and overwrites none.
    "afrobarometer_r8_language.json",
    "afrobarometer_region.json",
    # Korea's pooled web-panel survey is the same kind of thing: a survey
    # that fills provinces no census file reaches, and that a census file
    # later in this list replaces field by field.
    "korea_survey_province.json",
    # Korea's nationality, by the owner's decision of 19 September 2026: the
    # immigration register's foreign residents by country of nationality
    # against the resident register's Koreans, written on the ethnicity
    # field under ethnicity_basis "nationality". A count, so it would sit
    # with the census files; it is here because it fills a field the
    # survey above does not touch, and nothing below it writes Korea.
    "korea_nationality.json",
    # Thailand's ethnicity, by the same decision as Japan's below: a model
    # built from the 2000 census's home-language minorities and a regional
    # assignment, every province a modelled estimate. Its religion file
    # (thailand_province.json) is a census transcription and sits lower.
    "thailand_ethnicity.json",
    # Taiwan, by the owner's decision of 19 September 2026: the 2020 census's
    # main home language as a composition, ethnicity and religion as modelled
    # estimates from register counts, a survey and a building registry. Part
    # census and part model, so it sits with the surveys, below every census
    # file read from an office.
    "taiwan_county.json",
    # Japan, by the owner's decision of 19 September 2026: nationality read
    # from the 2020 census as a composition, religion and language as
    # modelled estimates. Part survey and part model, so it sits with the
    # surveys, below every census file.
    "japan_prefecture.json",
    # Iran's languages, from the Atlas of the Languages of Iran: a linguist's
    # field estimate of what is spoken in each settlement, rolled up to the
    # province and the shahrestan by population. It sits here, among the
    # models and the surveys and below every file read from a statistical
    # office, because that is what it is -- a research atlas, not a count.
    # Iran's census does not ask language at all, so no count of this field
    # exists anywhere to rank it against, and these figures displace nothing:
    # the not_collected declaration in common.py stays true and every record
    # here is an estimate that says so on its face.
    #
    # Nothing else in this list writes an Iranian unit, so the position buys
    # no precedence over anybody. It is a statement of kind, and the place to
    # keep it if a count ever arrives.
    "iran_ali_language.json",
    # And CFPS 2012 for five Chinese provinces: a survey where the census
    # asks nothing, transcribed from the paper that reports it.
    "cfps_survey_province.json",
    # The same survey's newer wave, tabulated from its public-release file
    # and checked against that paper: it replaces the 2012 figure where read.
    "cfps_microdata_province.json",
    # Macau's own census, one shape under China: nationality (as ethnicity,
    # labelled nationality) and usual language from DSEC's 2021 results.
    "macau_census.json",
    # Viet Nam's 2019 census, ethnicity by province from Table 2 of the
    # office's own Vietnamese results volume: a census count.
    "vietnam_province.json",
    # Hong Kong's own census, one shape under China: ethnicity and usual
    # spoken language from the 2021 Main Results workbook.
    "hongkong_census.json",
    # Laos's 18 provinces and 148 districts: ethno-linguistic category and
    # religion summed from the 2015 census's own 8,500-village indicator
    # table, which the Lao Statistics Bureau releases through Open
    # Development Laos. A census count, read below the level it is published
    # at and added up. Language is not here: the census does not ask it, and
    # NOT_COLLECTED_POLICY says so.
    "laos_province.json", "laos_district.json",
    # China's census ethnicity by province, the tables the provinces'
    # Wikipedia articles transcribe: a census transcription, so above the
    # surveys, and it touches a field the surveys do not carry.
    "china_wiki_province.json",
    # The Netherlands' twelve provinces, religion from each province's own
    # nl.wikipedia infobox, which transcribes CBS. A statistical office's
    # figures read through a transcription, so it sits with the other
    # Wikipedia-transcribed census tables rather than with the surveys. It
    # touches religion only: language and ethnicity are NOT_COLLECTED_POLICY
    # for the Netherlands and this must not overwrite that.
    "netherlands_province.json",
    "wikidata_admin1.json", "wikidata_admin2.json",
    # The head count a first-level unit's own Wikipedia article prints,
    # where nothing on this map has one. Directly under the Wikidata sweep
    # because it answers the same question from the same kind of source and
    # exists only for the units that sweep missed: 610 of 3,224 first-level
    # shapes had no population at all on the build of 22 September 2026 --
    # every Maltese locality, every Jamaican parish, every Zambian province,
    # every Saudi region -- because admin-1 population had only ever been
    # fetched from Wikidata's P1082 and a unit with no P1082 statement came
    # out blank. Every census file below overwrites it, which is the point
    # of the position: it is a floor under the field and never a ceiling.
    "wiki_population_admin1.json",
    # OCHA's Common Operational Dataset -- population statistics, the district
    # populations of 52 countries by P-code. It carries no composition at all,
    # only a head count, and it sits here because a head count from a national
    # statistical office beats Wikidata's and loses to the office's own census
    # file further down.
    #
    # 30,170 of this map's 49,349 second-level shapes had no population, and
    # that is not cosmetic: a parent's composition cannot be subtracted down
    # to its one unread district without a weight, so 59 of the 103 residuals
    # refused on the build of 21 September 2026 said exactly that. Bolivia had
    # a population for 9 of 9 departments and 0 of 110 provinces.
    #
    # Which level a file describes is measured, not assumed. "adm2" is OCHA's
    # word and the two do not always mean the same divisions: Romania's adm2
    # table is its 42 judete, which are this map's *first* level, against
    # 3,235 communes at the second.
    # Afghan district ethnicity, from the ministry's district development
    # plans as the provinces' articles transcribe them. Above Wikidata because
    # it is a field Wikidata does not carry at all, and below every census
    # file because a planning survey loses to a count -- though for
    # Afghanistan there is no count to lose to, which is the whole reason this
    # file exists.
    "afghanistan_district.json",
    "cod_ps_admin2.json",
    # Indonesia, by the owner's decision of 19 September 2026: the 2010
    # census's ethnicity by province as its provinces' Wikipedia articles
    # transcribe it, and religion by province and regency from the registry
    # or BPS figure each place's article cites. Part census transcription
    # and part registry, so it sits with the surveys, below every census
    # file read from its office.
    #
    # After Wikidata, for the head count that comes with those faiths.
    # Wikidata's regency populations are the wrong number often enough to
    # matter: it puts Kota Blitar's 132,018 on Kabupaten Blitar, which holds
    # 1,257,701, and Kota Sorong's 295,809 on Kabupaten Sorong, which holds
    # 128,157 -- the city's count on the regency that surrounds it, four
    # times in East Java alone. The articles' own figures, cited to the
    # registry or to a BPS yearbook, agree with their provinces instead:
    # nine provinces have every regency counted, and eight of the nine sum
    # to within 2.5% of the province's own published population.
    "indonesia.json",
    # Europe, by the owner's decision of 20 September 2026: religion,
    # language and ethnicity read from each unit's own Wikipedia article at
    # the first and second level, the way Indonesia's regencies were. A
    # Wikipedia transcription ranks below any statistical office, so these
    # sit here, above the surveys and below every census file read from the
    # office that published it -- including Poland, Czechia, Croatia,
    # Romania, Bosnia, Ireland, Germany, the UK, Russia and Ukraine, none of
    # which these touch. Each country is its own file so that re-running one
    # cannot drop another.
    "europe_wiki_slovakia.json",
    "europe_wiki_north_macedonia.json",
    "europe_wiki_moldova.json",
    "europe_wiki_montenegro.json",
    "europe_wiki_serbia.json",
    "europe_wiki_bulgaria.json",
    # Moldova's seven units the Europe reader refused, read by the owner's
    # decision of 22 September 2026 from the Romanian articles and the
    # Transnistria article's table. After europe_wiki_moldova.json, whose gap
    # rows for the same units carry the refusal as a note that this file's
    # reading must replace.
    "moldova_ethnicity_gaps.json",
    # After Wikidata, which carries a population for North Korea's provinces
    # and for Pyongyang a 2015 estimate: this is the 2008 census's own Table 2,
    # for all 11 first-level units and all 179 counties, with the sex ratio
    # beside it. It writes no composition -- the country asks none of the
    # three, which this file's own reading of the report is what established.
    "northkorea_county.json",
    "eurostat_nuts2.json", "eurostat_nuts3.json",
    # After Eurostat, which carries no ethnicity or religion for Romania and
    # says so in a generic sentence; this is the census itself.
    "romania_county.json",
    "india_state.json", "india_district.json",
    # After the C-01 files: mother tongue is the one field these add, and a
    # later file never overwrites an earlier real value with a gap marker.
    "india_language_state.json", "india_language_district.json",
    "mexico_state.json", "mexico_municipality.json",
    "nepal_province.json", "nepal_district.json",
    "nz_region.json", "nz_territorial.json",
    "switzerland_canton.json",
    # After Eurostat, which covers both countries at NUTS 3 with population and
    # nothing else: these are the national registers, and ethnicity is a
    # question Eurostat does not ask.
    "estonia_county.json", "latvia_municipality.json", "finland_region.json",
    "singapore_region.json", "singapore_planning_area.json",
    "srilanka_province.json", "srilanka_district.json",
    # Timor-Leste's 13 municipalities and 65 administrative posts: mother
    # tongue and religion from the 2015 census's own Volume 2 priority
    # tables, population from the 2022 main report's basic table 4.01.
    # Ethnicity is a declaration rather than a gap -- the 2022 questionnaire
    # does not ask it -- and comes from NOT_COLLECTED_POLICY.
    "timor.json",
    # Mongolia's 22 aimags and all 339 soums: ethnicity for every aimag from
    # Appendix Table 3.6 of the 2020 census's English national report, religion
    # for 18 of them from those aimags' own results books, and ethnicity for
    # 204 soums from the tables of ethnic group by soum those books print. The
    # soums with no figure carry the reason instead. Language is a declaration
    # -- the 2020 questionnaire does not ask it -- and comes from
    # NOT_COLLECTED_POLICY.
    "mongolia.json",
    # Religion, population and mother tongue together: this one file reads
    # Table 9 and Table 11 of the same census. It used to be a pair, the
    # language half coming from the U.S. Census Bureau's tables of the 2017
    # round, which named nine tongues and left Chitral 93.1% "Other".
    "pakistan_district.json",
    # Population only: Bhutan's census does not ask religion, language or
    # ethnicity, and those three are declared not_collected in common.py.
    # This fills 205 gewogs that carried nothing at all, and Thimphu, which
    # carried nothing because geoBoundaries spells it "Thimpu".
    "bhutan_gewog.json",
    "bangladesh_district.json",
    "south_africa_province.json",
    "philippines_province.json", "ethiopia_region.json",
    # After Afrobarometer, which is first: Kenya's counties carried the survey
    # and now carry the 2019 census, and merge_adapter lets the count win the
    # religion field while the survey keeps any field the census did not ask.
    "kenya_county.json",
    # Likewise after Afrobarometer: Angola's 18 provinces carried the survey
    # and now carry the 2024 census for all three fields.
    "angola_province.json",
    # Likewise: Zimbabwe's provinces and Burkina Faso's regions carried the
    # survey and now carry their census for the fields it publishes by region.
    "zimbabwe_province.json", "burkina_region.json",
    "thailand_province.json",
    # Papua New Guinea's own office, two of its publications: the 2024
    # census's head count for the 22 provinces and 71 of the 87 district
    # shapes, and the 2011 census's one provincial religion figure. Nothing
    # else writes PNG, so its place here is only by kind -- a census count.
    "png.json",
    "kazakhstan_region.json", "cambodia_province.json",
    "kazakhstan_oblast.json", "kazakhstan_district.json",
    "malaysia_state.json", "malaysia_district.json",
    # After both: the same 16 states and the districts, religion only, from
    # the 2020 census; its gaps never displace the ethnicity above.
    "malaysia_religion.json",
    # Brunei's own census, one file for both levels: race and religion for the
    # four districts, a head count and a stated gap for the 38 mukims. It
    # overlaps nothing above -- no other adapter writes a Bruneian row -- so
    # its place here is alphabetical company rather than precedence.
    "brunei.json",
    "poland_voivodeship.json", "poland_powiat.json",
    "czechia_kraj.json", "czechia_okres.json",
    "croatia_county.json", "croatia_unit.json",
    "bosnia_entity.json", "bosnia_canton.json",
    "myanmar_state.json", "ukraine_oblast.json", "car_prefecture.json",
    "peru_department.json",
    "mali_region.json",
    # After both Afrobarometer and the 2009 census file: Mali's nine regions
    # now carry RGPH5 2022 for all three fields.
    "mali_rgph5_region.json",
    "drc_province.json", "russia_subject.json",
    "colombia_department.json", "jamaica_parish.json",
    "bahamas_island.json",
    "brazil_state.json", "brazil_municipality.json",
    "germany_land.json", "germany_regierungsbezirk.json",
    "canada_province.json", "canada_economic_region.json",
    "australia_state.json", "australia_lga.json",
    "uk_lad.json", "uk_county.json",
    # Scotland's councils and Northern Ireland's districts are shapes the ONS
    # census cannot reach: it covers England and Wales. Neither overlaps the
    # two files above or each other, so the order between them never arises.
    "scotland_council.json", "northern_ireland_district.json",
    # The other island. No overlap with anything above: the CSO's areas are in
    # the Republic and every UK file stops at the border.
    "ireland_lea.json",
    "us_state.json", "us_county.json",
    # After us_county, and replacing its religion rather than filling a gap.
    # The 2020 U.S. Religion Census that us_acs carries counts adherents as
    # religious bodies report them, which reaches about half the population
    # and pools everyone else as "unaffiliated or not reported" -- so it
    # cannot tell somebody with no religion from somebody nobody counted.
    # PRRI asks people, covers all of them, and separates the two. The owner
    # weighed that and chose it.
    "us_prri_county.json",
]

# Where a real adapter exists for a country's subnational demographics. Shown in
# the UI on units that have no values yet, so an empty panel says *which* command
# would fill it rather than just "no data".
ADAPTER_HINTS: dict[str, str] = {
    "USA": "US Census ACS (race, language, age) plus the 2020 U.S. Religion Census: "
           "python -m scripts.fetch_census.us_acs --level county",
    "GBR": "ONS Census 2021 via Nomis for England and Wales (TS021 ethnic "
           "group, TS030 religion): python -m scripts.fetch_census.uk_nomis; "
           "Scotland and Northern Ireland have adapters of their own, "
           "scotland_census and northern_ireland",
    "POL": "GUS NSP 2021 final tables (religion, national-ethnic identification, "
           "home language) by voivodeship and powiat: "
           "python -m scripts.fetch_census.poland",
    "MYS": "DOSM population estimates by ethnicity, OpenDOSM CSV by state and "
           "district: python -m scripts.fetch_census.malaysia --level both; "
           "religion from the 2020 census as DOSM's Kawasanku dashboard publishes "
           "it by state and district: python -m scripts.fetch_census.malaysia_religion",
    "BRN": "DEPS's annex workbook for the BPP 2021 census: race and religion by "
           "district (Tables A3 and A4), population by mukim (Table C1). Race and "
           "religion are published for the four districts and nowhere below them, "
           "and language is asked and never tabulated: "
           "python -m scripts.fetch_census.brunei",
    "CZE": "ČSÚ SLDB 2021 open data (nationality, religious belief, mother tongue) "
           "by kraj and okres: python -m scripts.fetch_census.czechia",
    "HRV": "DZS Popis 2021 workbook (ethnicity, religion, mother tongue) by "
           "županija and grad/općina: python -m scripts.fetch_census.croatia",
    "KAZ": "2021 census religion by region, transcribed on Wikipedia "
           "(python -m scripts.fetch_census.wiki_census --country KAZ); ethnicity by "
           "region and district from the Bureau's start-of-2025 workbook "
           "(python -m scripts.fetch_census.kazakhstan)",
    "KHM": "2019 census religion by province, transcribed on Wikipedia: "
           "python -m scripts.fetch_census.wiki_census --country KHM",
    "VNM": "2019 census Table 2 (population by ethnic group and province) from the "
           "office's own results volume: python -m scripts.fetch_census.vietnam",
    "LAO": "2015 census ethno-linguistic category and religion, summed from the Lao "
           "Statistics Bureau's own village indicator table on Open Development Laos "
           "(8,500 villages) to the 18 provinces and 148 districts: "
           "python -m scripts.fetch_census.laos --level both",
    "TLS": "INETL's 2015 census Volume 2 priority tables 11 and 12 (religion, mother "
           "tongue) by municipality, with the 2022 main report's basic table 4.01 for "
           "population down to the administrative post: "
           "python -m scripts.fetch_census.timor",
    "PNG": "NSO 2024 census Final Figures (population, sex ratio by province and "
           "district) and the 2011 National Report's Summary Indicators (each "
           "province's largest denomination): python -m scripts.fetch_census.png",
    "PRK": "The 2008 census's Table 2 (population by sex and urban/rural, by "
           "city/district/county and province) from the UN Statistics Division's "
           "copy of the CBS National Report: population and sex ratio only, "
           "because the census asks none of the three -- its form's one question "
           "about who a person is asks nationality: "
           "python -m scripts.fetch_census.northkorea",
    "PER": "INEI 2017 census profile book (religion, mother tongue) by department, "
           "read from the PDF's word positions: python -m scripts.fetch_census.peru",
    "MLI": "INSTAT RGPH5 2022 thematic report on cultural characteristics (religion, "
           "ethnie, langue maternelle) by region, its 20 regions summed into the 9 "
           "shapes: python -m scripts.fetch_census.mali",
    "ZWE": "ZIMSTAT 2022 census report (religion, mother tongue) by province: "
           "python -m scripts.fetch_census.zimbabwe",
    "BDI": "Afrobarometer, the only subnational source there is: religion and "
           "language from Round 6 (2014) and ethnicity from Round 5 (2012), "
           "which is the last round that asked it there. 17 of the 18 "
           "provinces; Rumonge postdates both fieldworks: "
           "python -m scripts.fetch_census.afrobarometer_r56",
    "BFA": "INSD RGPH 2019 table volume (religion) by region: "
           "python -m scripts.fetch_census.burkina",
    "CHN": "CFPS 2012 (religion) for the five provinces the survey sampled on their "
           "own, transcribed from Lu Yunfeng's report: "
           "python -m scripts.fetch_census.cfps_survey; census ethnicity by "
           "province, transcribed in each province's Wikipedia article: "
           "python -m scripts.fetch_census.china_wiki. Hong Kong SAR carries "
           "ethnicity and usual spoken language from its own 2021 Population "
           "Census (C&SD Main Results, Tables 3.9 and 3.13): "
           "python -m scripts.fetch_census.hongkong_census. Macau SAR carries "
           "nationality (as ethnicity, labelled nationality) and usual language "
           "from its own 2021 Population Census (DSEC Detailed Results, Tables 6 "
           "and 10): python -m scripts.fetch_census.macau_census",
    "KOR": "Hankook Research 2025 pooled survey (religion) by residence region, each "
           "of the seven regions' figure carried by its provinces: "
           "python -m scripts.fetch_census.korea_survey. Nationality as ethnicity "
           "(labelled nationality) for the 17 provinces and the districts, the "
           "Ministry of Justice's registered foreigners by country against the "
           "resident register's Koreans at the end of 2023: "
           "python -m scripts.fetch_census.korea_nationality",
    "TWN": "2020 census main language by county (DGBAS Table 2-5), ethnicity modelled from "
           "the household register's indigenous count, the Hakka Affairs Council's 2021 "
           "survey and a uniform Hoklo-mainlander split, religion modelled from Pew's 2023 "
           "survey tilted by the Ministry of the Interior's temple and church registry: "
           "python -m scripts.fetch_census.taiwan",
    "JPN": "2020 census nationality by prefecture (as ethnicity, labelled nationality), "
           "religion modelled from NHK's 2018 ISSP survey tilted by the Agency for "
           "Cultural Affairs' adherent counts, language modelled from nationality; "
           "needs ESTAT_API: python -m scripts.fetch_census.japan",
    "AGO": "INE Censo 2024 final report (ethnic group, mother tongue, religion) by "
           "province, read from the PDF's word coordinates: "
           "python -m scripts.fetch_census.angola",
    "BIH": "BHAS Popis 2013 Book 2 tables (ethnicity, religion, mother tongue) by "
           "entity and canton: python -m scripts.fetch_census.bosnia",
    "IRL": "CSO Census 2022 via PxStat (SAPMAP religion and ethnicity by local "
           "electoral area): python -m scripts.fetch_census.ireland",
    "DEU": "Zensus 2022 religion by Land, three categories from the church-tax "
           "register (needs a free ergebnisse.zensus2022.de account): "
           "python -m scripts.fetch_census.germany",
    "CAN": "Statistics Canada 2021 Census Profile (religion, visible minority, language): "
           "python -m scripts.fetch_census.statcan",
    "IDN": "2010 census ethnicity by province and the registry or BPS religion "
           "figure by province and regency, as the Indonesian Wikipedia transcribes "
           "them (BPS itself refuses automated readers and its API needs a key): "
           "python -m scripts.fetch_census.indonesia",
    "BRA": "IBGE SIDRA 2022 census (population, cor ou raça, religion): "
           "python -m scripts.fetch_census.ibge_sidra --level municipality",
    "AUS": "ABS 2021 Census (religion, ancestry): "
           "python -m scripts.fetch_census.abs --level lga",
    "MEX": "INEGI Censo 2020 ITER (religion, indigenous language, Afro-descendant): "
           "python -m scripts.fetch_census.mexico --level both",
    "NZL": "Stats NZ 2023 Census via Aotearoa Data Explorer (ethnicity, "
           "languages spoken, religious affiliation; needs an API key): "
           "python -m scripts.fetch_census.new_zealand",
    "NPL": "NPHC 2021 report (caste/ethnicity, mother tongue, religion): "
           "python -m scripts.fetch_census.nepal --url <report PDF>",
    "CHE": "FSO structural survey, main languages by canton: "
           "python -m scripts.fetch_census.switzerland",
    "SGP": "SingStat table M810771 (residents by planning region, age, sex): "
           "python -m scripts.fetch_census.singstat",
    "LKA": "Sri Lanka Census 2024 tables A1-A3 (population, ethnicity, religion): "
           "python -m scripts.fetch_census.sri_lanka --level district",
    "IND": "Census of India 2011 tables C-01 (religion) and C-16 (mother tongue): "
           "python -m scripts.fetch_census.india_census --level district && "
           "python -m scripts.fetch_census.india_language --level district",
    # Europe, read from each unit's own Wikipedia article the way Indonesia's
    # regencies were: the composition only where the article prints one with
    # a citation that can be dated, and a stated reason everywhere else.
    "SVK": "2011 census nationality and religion by kraj and okres, from the "
           "tables the Slovak Wikipedia article of each unit transcribes: "
           "python -m scripts.fetch_census.europe_wiki --country SVK",
    "SRB": "Census ethnicity by district and municipality, from the table the "
           "English Wikipedia article of each unit transcribes: "
           "python -m scripts.fetch_census.europe_wiki --country SRB",
    "MKD": "2021 census ethnicity by municipality, from the two-census table "
           "the English Wikipedia article of each municipality transcribes: "
           "python -m scripts.fetch_census.europe_wiki --country MKD",
    "MDA": "Census ethnicity by district, from the table the English Wikipedia "
           "article of each district transcribes: "
           "python -m scripts.fetch_census.europe_wiki --country MDA",
    "MNE": "Census ethnicity and religion by municipality, from the tables the "
           "English Wikipedia article of each municipality transcribes: "
           "python -m scripts.fetch_census.europe_wiki --country MNE",
    "BGR": "Census mother tongue, religion and ethnicity by oblast and "
           "obshtina, from the tables the Bulgarian Wikipedia article of each "
           "unit transcribes (the English ones carry a 2001 religion table "
           "and nothing else): "
           "python -m scripts.fetch_census.europe_wiki --country BGR",
}
# Countries where no command would help, because the figures are not published
# at this level -- or not published to an automated reader at all. A hint naming
# a script is a promise that running it would fill the panel; for these it would
# not, and saying so is the point of the map rather than an admission against
# it. Kept short here; docs/SOURCES.md carries what was actually tried.
ADAPTER_GAPS: dict[str, str] = {
    "THA": "The statistical office refuses automated readers on every host "
           "tried. Religion by province is the 2000 census, read from its "
           "provincial final reports as transcribed on Wikipedia; language was "
           "made public once, for 2000, in a file that is not a composition. "
           "Ethnicity is not asked, and by the owner's decision of 19 September "
           "2026 every province carries a modelled estimate instead: the 2000 "
           "census's home-language minorities as printed, the rest assigned to "
           "the region's Tai group as the Ethnolinguistic Maps of Thailand name "
           "it, labelled as a model on every record.",
    "IRN": "The 2016 census asked religion and the Statistical Centre publishes "
           "it by province, but amar.org.ir ends the TLS handshake before a "
           "standard client can read a page (an EOF in the protocol, measured "
           "on the runner), and this project does not turn verification off. "
           "The data exists and is not reachable from here. Language is a "
           "different kind of gap: no Iranian census has ever asked it, so "
           "there is nothing withheld and nothing to fetch. Eleven provinces "
           "and 96 counties carry a figure all the same -- a population-"
           "weighted roll-up of the settlement estimates in the Atlas of the "
           "Languages of Iran, marked as the atlas's field estimates and not "
           "as anybody's count. The atlas is published province by province "
           "and has reached twelve of the thirty-one; the rest of the country "
           "is empty because those modules do not exist yet, and Kermanshah "
           "is empty because its module reaches five of its fourteen counties "
           "and under a fifth of its people.",
    "EGY": "CAPMAS collected religion in the 2017 census and has not published "
           "it, nationally or by governorate; the last published figures are "
           "the 2006 census, national only. The data exists and is withheld. "
           "17 of the 27 governorates carry a survey estimate instead, from "
           "Afrobarometer Round 5 (2013), the last round that asked religion "
           "in Egypt; this one was not among them.",
}

# Shapes an adapter deliberately will not fill, and why -- a fact about the
# boundary file rather than about what a country publishes, which is why it
# sits here beside ADAPTER_GAPS rather than in an adapter.
#
# ADAPTER_GAPS answers "this country has no adapter". This answers the harder
# case: the country has an adapter, the adapter has the figures, and a
# particular polygon still cannot be given them because the polygon is not the
# place its label says it is. Joining by name anyway would put one district's
# population on another's ground -- the mis-match that looks exactly like a
# right answer, which is the one failure this project is built to avoid.
#
# Keyed by the name the boundary file writes, not by the district's own name,
# because the shape is what a reader clicks on. A name the file uses twice is
# keyed once: the reason is a fact about the label, so it is true of both
# polygons bearing it, and keying by name reaches both -- which nothing that
# joins data by name can do, since an ambiguous name is exactly what makes the
# join unsafe.
#
# Every entry here is required to be a shape that really does end up empty; a
# stale one fails the build. See check_shape_gaps below.
# Per-shape gap reasons, keyed by the boundary file's own spelling of the
# shape's name -- which is what reaches both polygons when a country's
# boundary file uses one name twice.
#
# Nepal's seven entries used to live here, covering nine shapes, and they are
# gone because the shapes are no longer empty: geoBoundaries draws Nepal's
# pre-2015 districts correctly and only *labels* them wrongly, so the nine are
# bound by shape id in scripts/fetch_census/nepal.py instead. Five of those
# seven reasons also said things that were not true -- that nothing
# distinguished the two polygons called "Bara", that Rukum East lay inside the
# shape named Rolpa, that Parsi's ground was inside no polygon at all. The
# last two were artefacts of bad Wikidata reference points (Parasi's P625 is
# in India), read as facts about the boundary file. A gap that says why it is
# a gap is worth having; a gap that says why, wrongly, is worse than a silent
# one, because it stops anyone looking again.
SHAPE_GAPS: dict[str, dict[str, str]] = {}


# ---------------------------------------------------------------------------
# Levels that are an overlay on a country rather than a partition of it.
#
# The three tables above are all about *data*: who publishes what, and which
# polygon an adapter must not fill. This one is about *ground*. A level is
# normally a tiling -- every square metre of the country is inside exactly one
# unit -- and the map is drawn on that assumption: above roughly z7.75 the
# first-order layer has faded out and only the second-order layer paints, so
# ground that is inside no second-order unit is painted with the background,
# which is the sea colour. A country whose second level does not tile it
# therefore does not look like a country with a gap in its data. It looks like
# a country that is not there.
#
# Uruguay is the one country in CGAZ where that happens at scale, and it is not
# a defect in the boundary file. Uruguay's second-order units are municipios,
# the third tier of government created by the 2009 decentralisation law (Ley
# 18.567), and a municipio is constituted around a population centre rather
# than carved out of the map: the territory of a department that lies in no
# municipio is administered by the departmental government directly. So the
# municipios are real, correctly drawn, and cover 36.8% of the country.
# 112,404 km2 of Uruguay -- 63.2%, more than the area of Bulgaria -- is inside
# no municipio, and at second-order zoom it renders as sea. Flores department
# is 0.0% covered, Florida 5.7%, Durazno 9.4%, Tacuarembo 11.8%.
#
# Measured across all 218 countries CGAZ draws second-order units for, Uruguay
# is alone by a factor of three. Ranking by how much coverage is lost between
# the first and second level: Uruguay 63.2 points, Tonga 19.5 (a 683 km2
# archipelago), Uganda 13.1 (Lake Victoria, which is water and *should* be
# drawn as water), Bahamas 6.4 (sea between islands), Kuwait 5.6. Nothing else
# exceeds 3. See check_level_coverage below, which re-measures this on every
# build so the claim cannot go stale, and which reports any country that
# develops the same shape without a declaration here.
#
# This is recorded rather than repaired. Inventing polygons for "resto del
# departamento" would put a unit on the map that Uruguay does not have, and a
# unit that does not exist cannot be given data that does not exist for it.
# A stated absence is the smaller lie: none.
PARTIAL_LEVELS: dict[tuple[str, str], dict[str, Any]] = {
    # Found by the detector below, then measured the way Uruguay was. The
    # 142 km2 of first-level ground that is in no district lies entirely
    # inside the country polygon -- which is itself 683 km2 against a real
    # land area near 750, so it is a land outline and not an envelope drawn
    # round the sea. That is land rendering as sea, at a fifth of the country.
    # The declaration says what was measured and not why: which islets the
    # districts leave out, and whether anyone lives on them, is not something
    # the boundary file can answer.
    ("TON", "admin2"): {
        "units": 21,
        "coverage_pct": 67.2,
        "note": "Tonga's second-order units are the 21 districts, and they do "
                "not cover the country: geoBoundaries draws them over 67.2% "
                "of it, and the remaining 142 km2 -- about a fifth of Tonga, "
                "inside the five island groups -- is in no district. That "
                "ground is land, not sea between islands; it lies inside the "
                "country polygon. It is blank at this level because there is "
                "nothing there to draw. The five island groups are the level "
                "that does cover it.",
    },
    ("URY", "admin2"): {
        "units": 124,
        "coverage_pct": 36.8,
        "note": "Uruguay's second-order units are municipios, and they do not "
                "cover the country. A municipio is constituted around a "
                "population centre rather than carved out of the map (Ley "
                "18.567 of 2009), so the ground of a department that lies in "
                "no municipio is administered by the departmental government "
                "directly and is not part of any second-order unit. "
                "geoBoundaries CGAZ draws 124 municipios covering 36.8% of "
                "Uruguay; the remaining 112,404 km2 -- 63.2% of the country, "
                "including almost all of Flores, Florida, Durazno and "
                "Tacuarembo -- is inside no second-order unit and is blank at "
                "this level because there is nothing there to draw. Uruguay's "
                "19 departments are the level that does cover it.",
    },
}

# How far a declared coverage figure may drift from the measured one before the
# build stops. The declaration is a sentence a reader is asked to believe, and
# boundary files change under it; a point of slack absorbs a redrawn coastline
# without absorbing a level that has quietly become a tiling (or stopped being
# one).
COVERAGE_TOLERANCE = 1.0

# The shape that makes a level worth declaring: the level above tiles the
# country and this one does not, by a margin no redrawn border explains. Set
# below Tonga's 19.5-point drop -- the largest undeclared case measured -- so a
# new one is reported, and well above the 3-point band every other country sits
# in, so ordinary coastline noise is not.
COVERAGE_DROP_REPORTABLE = 15.0


def _coverage(shapes: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, float]]:
    """Per-country share of the ADM0 polygon that each level's units cover.

    Areas are the planar degree-squared areas read_shapes already computed, not
    projected ones. The answer wanted is a ratio between two levels of the same
    country, so the projection's distortion is common to numerator and
    denominator and divides out: measured against an equal-area projection,
    Uruguay comes to 36.8% either way.
    """
    totals: dict[str, dict[str, float]] = {}
    for level in ("ADM0", "ADM1", "ADM2"):
        sums: dict[str, float] = defaultdict(float)
        for row in shapes.get(level, []):
            sums[row["group"]] += row.get("area") or 0.0
        totals[level] = sums
    out: dict[str, dict[str, float]] = {}
    for iso3, whole_area in totals["ADM0"].items():
        if whole_area <= 0:
            continue
        out[iso3] = {
            "adm1": totals["ADM1"].get(iso3, 0.0) / whole_area * 100,
            "adm2": totals["ADM2"].get(iso3, 0.0) / whole_area * 100,
        }
    return out


def check_level_coverage(shapes: dict[str, list[dict[str, Any]]]) -> None:
    """Re-measure every declared partial level, and report undeclared ones.

    Two directions, for the same reason check_shape_gaps has two. A declaration
    that has drifted is worse than no declaration: it is a specific number in
    front of a reader, and a reader who checks it is the person this map is
    for. And a country that has newly become partial is the bug this table was
    written to make visible -- Uruguay went unnoticed because a level with no
    polygons looks exactly like a level with no data, and the only difference
    is a measurement nobody was taking.

    A drifted declaration stops the build. A newly partial country is logged:
    it is a fact about an upstream boundary file that this build cannot fix,
    and refusing to write 218 countries because geoBoundaries redrew a
    nineteenth would be the wrong trade.
    """
    if not (shapes.get("ADM0") and shapes.get("ADM2")):
        return
    coverage = _coverage(shapes)
    counts: dict[str, int] = defaultdict(int)
    for row in shapes.get("ADM2", []):
        counts[row["group"]] += 1

    problems: list[str] = []
    for (iso3, level), declared in PARTIAL_LEVELS.items():
        if level != "admin2":
            continue
        if iso3 not in coverage:
            # A run that carries neither the country's outline nor any of its
            # second-order units is not a run this declaration is about --
            # that is what a caller passing a subset of shapes looks like, and
            # it is not evidence of anything. A country that has kept its
            # outline and lost its units is a different matter, and the unit
            # count below is what catches it.
            if not counts.get(iso3):
                continue
            problems.append(f"{iso3}: declared a partial {level}, and the "
                            f"boundary file draws {counts[iso3]} second-order "
                            f"units for it but no country polygon, so there is "
                            f"nothing to measure the coverage against")
            continue
        measured = coverage[iso3]["adm2"]
        if abs(measured - declared["coverage_pct"]) > COVERAGE_TOLERANCE:
            problems.append(
                f"{iso3} {level}: declared {declared['coverage_pct']}% of the "
                f"country covered, boundary file now gives {measured:.1f}% -- "
                f"the note a reader sees states the old figure")
        if counts.get(iso3, 0) != declared["units"]:
            problems.append(
                f"{iso3} {level}: declared {declared['units']} units, boundary "
                f"file draws {counts.get(iso3, 0)}")
    if problems:
        raise SystemExit(
            "build_entities: a partial-level declaration no longer matches the "
            "boundaries it describes, so nothing is being written:\n  - "
            + "\n  - ".join(problems))

    for iso3, pct in sorted(coverage.items()):
        if (iso3, "admin2") in PARTIAL_LEVELS:
            continue
        if not counts.get(iso3):
            continue
        if pct["adm1"] - pct["adm2"] >= COVERAGE_DROP_REPORTABLE and pct["adm2"] < 90:
            log(f"  note: {iso3} second-order units cover {pct['adm2']:.1f}% of "
                f"the country where its first-order units cover "
                f"{pct['adm1']:.1f}% -- ground in no second-order unit is drawn "
                f"as sea at that zoom. If that is how the country is governed, "
                f"declare it in PARTIAL_LEVELS so the map says so.")

EUROSTAT_HINT = ("Eurostat NUTS population and median age: "
                 "python -m scripts.fetch_census.eurostat --level nuts3")
EUROSTAT_COUNTRIES = {
    "AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU",
    "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT",
    "ROU", "SVK", "SVN", "ESP", "SWE", "NOR", "CHE", "ISL", "SRB", "MKD", "TUR",
}
WIKIDATA_HINT = ("Wikidata population, capital and coordinates for every country: "
                 "python scripts/fetch_wikidata.py --level admin2 --countries {iso3}")


def adapter_hint(iso3: str) -> str:
    if iso3 in ADAPTER_HINTS:
        return ADAPTER_HINTS[iso3]
    if iso3 in EUROSTAT_COUNTRIES:
        return EUROSTAT_HINT
    return WIKIDATA_HINT.format(iso3=iso3)


# Fields the coverage matrix reports on.
TRACKED = ("population", "capital", "largest_settlement", "median_age",
           "sex_ratio", "religion", "language", "ethnicity")


def is_disputed(group: str | None) -> bool:
    """geoBoundaries files disputed and special-status areas under numeric groups.

    They appear at all three levels (Abyei is both an ADM0 and an ADM1 shape), so
    the test lives here rather than being repeated per level.
    """
    return bool(group) and group.isdigit()


# Letters NFKD cannot take apart, because they are not an ASCII letter plus a
# mark -- they are their own letter. Stripping combining characters leaves them
# untouched, and the old "keep only a-z0-9" rule then deleted them outright:
# "Ostfold" became "stfold", which is a substring of "vestfoldogtelemark", so
# Norway's Ostfold was joined to Vestfold og Telemark. Folding them is the
# difference between a name and a fragment of one.
FOLD = str.maketrans({
    "ø": "o", "đ": "d", "ð": "d", "ł": "l", "ħ": "h", "ŧ": "t", "ŋ": "n",
    "ı": "i", "ə": "e",
    # Modifier letters standing in for a glottal stop or 'ayn. A source writes
    # "Sanaa" where the boundary file writes "Sanʿaʾ"; they are the same name.
    # ...and the plain apostrophes that stand in for them. Removed rather than
    # left to split a word: "Dar'a" is one name, and splitting it gave "dar"
    # and "a", which lines up with nothing.
    "ʻ": "", "ʼ": "", "ʹ": "", "ʾ": "", "ʿ": "", "ʽ": "",
    "`": "", "´": "", "'": "", "’": "", "ʼ": "",
    "ß": "ss", "æ": "ae", "œ": "oe", "þ": "th",
})


# Words that name a kind of administrative unit rather than a place, dropped
# from both sides of a comparison. English only, deliberately. Adding Latvian's
# "novads" here to reach "Aizkraukles novads" from "Aizkraukle municipality"
# also collapses "Ventspils" and "Ventspils novads" -- a state city and the
# municipality around it, two different places -- onto one key, and one of them
# then wears the other's figures. A local generic word is not a word to strip;
# it is a sign the two sources are speaking different languages, which is what
# the adapter now fixes by asking the office for its own local name.
GENERIC = (r"\b(province|state|region|district|county|prefecture|governorate|"
           r"oblast|department|municipality|city|autonomous|"
           r"territory|of|the|and)\b"
           # A seat count is not a name. geoBoundaries writes Ireland's local
           # electoral areas as "ADARE-RATHKEALE LEA-6", where the 6 is how
           # many councillors the area returns -- it is not part of what the
           # place is called, and the CSO does not write it. Left in, every one
           # of the 166 rows Ireland's census publishes misses its shape.
           #
           # Scoped to LEA followed by digits, and measured before it was
           # added: across both CGAZ levels that pattern appears on 166 shapes,
           # all Irish, and on nothing else in the world. The one real place
           # named Lea -- a township in the United States -- has no number
           # after it and is untouched.
           r"|\blea[-\s]*\d+\b")


def norm(text: str | None) -> str:
    """A name reduced to what two sources are likely to agree on.

    Alphanumerics of *any* script survive. Restricting the result to a-z0-9
    deleted every letter that is not Latin, so 693 boundary names -- 352
    Russian and 256 Tunisian second-level units among them -- normalised to the
    empty string: unmatchable by name, and all colliding on one key. Cyrillic
    stays Cyrillic here rather than being romanised, because a transliteration
    this code invents is a guess about a name, while the name itself is not.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text.lower()).translate(FOLD)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(GENERIC, " ", text)
    return "".join(c for c in text if c.isalnum())


# ---------------------------------------------------------------------------
# Geometry side
# ---------------------------------------------------------------------------

def read_shapes(level: str) -> list[dict[str, Any]]:
    """Feature properties + centroid for one CGAZ level (geometry stays on disk)."""
    import fiona
    from shapely.geometry import shape

    path = BOUNDARIES / f"geoBoundariesCGAZ_{level}.gpkg"
    if not path.exists():
        # Fatal, not a warning. The boundary files are the only source of
        # shapes, and they are too large to commit, so a checkout that has not
        # run fetch_boundaries.py has none. Carrying on regardless once wrote a
        # 9 kB search index over 218 countries and no divisions, a groups index
        # missing every subnational group, and a coverage matrix that reported
        # nothing below the national level -- all of it committed and deployed,
        # because every per-country shard was left untouched and only the
        # aggregates looked "rebuilt".
        raise SystemExit(
            f"missing {path}\n"
            "The CGAZ boundary files are not in git (they are ~550 MB).\n"
            "Run: python3 scripts/fetch_boundaries.py --cgaz")
    out: list[dict[str, Any]] = []
    with fiona.open(path) as src:
        for feat in src:
            props = dict(feat["properties"])
            geom = shape(feat["geometry"]) if feat["geometry"] else None
            if geom is None or geom.is_empty:
                continue
            point = geom.representative_point()
            bounds = geom.bounds
            out.append({
                "shape_id": props.get("shapeID") or props.get("shapeGroup"),
                "name": respell(repair((props.get("shapeName") or "").strip()),
                                props.get("shapeGroup")),
                "group": props.get("shapeGroup"),
                "point": [round(point.x, 5), round(point.y, 5)],
                "bbox": [round(b, 4) for b in bounds],
                "_geom": geom if level != "ADM2" else None,
                "area": geom.area,
            })
    log(f"  {level}: {len(out)} shapes")
    return out


def whole(geom):
    """The same shape, in a form GEOS will overlay.

    346 of CGAZ's 3,224 first-order polygons and 843 of its second-order ones
    do not satisfy GEOS -- a ring that touches itself, a hole that leaves its
    shell. An overlay against one of those either raises or, worse, quietly
    returns an empty geometry, and an empty geometry is indistinguishable from
    "these two do not meet". Repairing first is the only way the area of
    overlap means what it says: with lazy repair-on-exception, Belize City's
    six divisions came out overlapping no district in their own country.

    ``make_valid`` can hand back stray lines and points alongside the polygon.
    Area and containment are questions about the polygon, so that is the part
    kept.
    """
    from shapely import make_valid
    from shapely.ops import unary_union

    if geom is None or geom.is_valid:
        return geom
    fixed = make_valid(geom)
    if fixed.geom_type in ("Polygon", "MultiPolygon"):
        return fixed
    parts = [g for g in getattr(fixed, "geoms", [])
             if g.geom_type in ("Polygon", "MultiPolygon")]
    return unary_union(parts) if parts else fixed


def link_adm2_parents(adm1: list[dict[str, Any]], adm2: list[dict[str, Any]]) -> None:
    """CGAZ ADM2 carries no parent link, so work it out from the geometry.

    The unit belongs to the first-order shape it has the most area inside.
    That is the whole rule; everything below is about arriving at it without
    holding fifty thousand polygons in memory or intersecting all of them.

    It used to be a different rule: containment of the unit's representative
    point, and where that failed, whichever bounding box the spatial index
    happened to return first. Both halves were wrong in the same direction.
    The point is a one-pixel sample of a polygon, so where the two levels are
    not the same partition of the country it can land in a neighbour -- and
    the fallback is not a geographic answer at all, since index order is an
    artefact of how the tree was packed. Measured over all 49,349 second-order
    units, 228 were filed under the wrong first-order shape: Apostoles
    Department under Corrientes when it is in Misiones, Rukum East under
    Lumbini when it is in Karnali, eleven Bhutanese gewogs under the wrong
    dzongkhag, forty Chinese counties, forty-four Brazilian municipalities.
    A district filed under a neighbouring province is the kind of wrong this
    project ranks below a gap: nothing on screen says so, and the parent is
    what scopes an adapter's row to a shape, so it decides matches too.

    Three things make the exact rule affordable:

    * The point pass still runs first and is still right for nearly every
      unit; it costs no second-order geometry at all.
    * ``read_shapes`` already keeps every unit's bounding box. A unit whose
      whole box lies inside the parent the point chose cannot be mostly inside
      anything else, so it is settled there and never needs its polygon. That
      is 17,861 of them.
    * For the rest the file is streamed a second time, one polygon at a time.
      If the sitting parent holds a majority of the unit's area, no other
      candidate can beat it and the search stops at one overlay; only 256
      units in the world need the full comparison.

    Invalid polygons are repaired rather than skipped, and this is not a
    detail: 346 of the 3,224 first-order shapes and 843 of the second-order
    ones do not satisfy GEOS, and an overlay against one of them raises. An
    earlier version of this caught that exception and moved on, which silently
    dropped the true parent and handed the unit to whichever lesser neighbour
    happened not to raise -- Bouches-du-Rhone to Occitanie, Abu Dhabi to
    Sharjah. Swallowing an error from the most important candidate is worse
    than the arbitrary fallback it replaced.

    A unit whose polygon meets no first-order shape in its own country is left
    without a parent and counted in the log. Geometry has no evidence there,
    and nearness is a proxy for evidence rather than evidence; the entity
    falls back to the country, which is true, instead of to a province picked
    for being close, which may not be. Note also that no rule here can fix a
    boundary file whose two levels are not the same partition of the country.
    Bhutan's are not, and where the answer is still wrong the consequence is a
    row that fails to match and says so, not one that matches silently --
    ``resolve_admin2`` accepts an exact, country-unique name over a parent
    disagreement for exactly that reason.
    """
    import shapely
    from shapely.geometry import Point, box
    from shapely.strtree import STRtree

    by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in adm1:
        by_country[row["group"]].append(row)

    trees: dict[str, tuple[STRtree, list[dict[str, Any]]]] = {}
    for iso3, rows in by_country.items():
        kept = [r for r in rows if r["_geom"] is not None]
        if not kept:
            continue
        for parent in kept:
            # Repaired before anything is asked of it, and prepared once, then
            # asked about tens of thousands of points and boxes. Without the
            # preparation the point pass alone is minutes of work; without the
            # repair its answers are not reliably true.
            parent["_geom"] = whole(parent["_geom"])
            shapely.prepare(parent["_geom"])
        trees[iso3] = (STRtree([r["_geom"] for r in kept]), kept)

    matched = 0
    pending: dict[str, dict[str, Any]] = {}
    for row in adm2:
        entry = trees.get(row["group"])
        row["parent_shape"] = None
        if not entry:
            continue
        tree, rows = entry
        point = Point(row["point"])
        sitting = None
        for idx in tree.query(point):
            candidate = rows[int(idx)]
            if shapely.contains(candidate["_geom"], point):
                sitting = candidate
                break
        if sitting is None and len(rows) == 1:
            # One first-order shape in the country: there is nothing to choose
            # between, and reading the unit's polygon to prove it would be
            # waste.
            sitting = rows[0]
        if sitting is not None:
            row["parent_shape"] = sitting["shape_id"]
            matched += 1
            if shapely.contains(sitting["_geom"], box(*row["bbox"])):
                continue
        if row["shape_id"]:
            pending[row["shape_id"]] = row

    moved, unplaced = (weigh_adm2_parents(pending, trees, adm2_geometry(pending))
                       if pending else (0, []))
    # Recounted rather than adjusted: the second pass both gives parents to
    # units the point pass left without one and takes them away from units
    # whose polygon turns out to meet no first-order shape at all.
    matched = sum(1 for row in adm2 if row["parent_shape"])
    log(f"  ADM2 -> ADM1 parent assigned for {matched}/{len(adm2)} units "
        f"({len(pending)} weighed by area, {moved} moved to the shape they are "
        f"mostly inside)")
    if unplaced:
        shown = ", ".join(unplaced[:8])
        more = f" and {len(unplaced) - 8} more" if len(unplaced) > 8 else ""
        log(f"  {len(unplaced)} units meet no first-order shape of their own "
            f"country and stay under it: {shown}{more}")


def adm2_geometry(pending: dict[str, dict[str, Any]]):
    """Stream the second-order polygons the weighing pass asked for, and only those.

    A second read of the file rather than keeping every polygon from the
    first: the build wants ADM2 geometry for the parent pass and for nothing
    else, and 49,349 of them do not need to sit in memory through the whole
    join to serve one function. Skipping the ones not asked for means the
    two-thirds of units the bounding box already settled are never even
    turned into geometry.
    """
    import fiona
    from shapely.geometry import shape as to_shape

    with fiona.open(BOUNDARIES / "geoBoundariesCGAZ_ADM2.gpkg") as src:
        for feat in src:
            shape_id = feat["properties"].get("shapeID")
            if shape_id not in pending or not feat["geometry"]:
                continue
            geom = to_shape(feat["geometry"])
            if not geom.is_empty:
                yield shape_id, geom


def weigh_adm2_parents(
    pending: dict[str, dict[str, Any]],
    trees: dict[str, tuple[Any, list[dict[str, Any]]]],
    units,
) -> tuple[int, list[str]]:
    """Give each pending unit the first-order shape it is most inside.

    ``units`` yields ``(shape_id, polygon)``; where they come from is the
    caller's business, which is what lets this be tested on four squares
    instead of on 550 MB of boundary file.

    Returns ``(moved, unplaced_names)`` -- how many units changed parent, and
    the names of the ones left without one.
    """
    import shapely

    moved = 0
    unplaced: list[str] = []
    for shape_id, geom in units:
        row = pending.get(shape_id)
        if row is None:
            continue
        unit = whole(geom)
        tree, rows = trees[row["group"]]
        was = row["parent_shape"]
        sitting = next((r for r in rows if r["shape_id"] == was), None)
        best, held = None, 0.0
        if sitting is not None and unit.area == 0:
            # A sliver that make_valid collapsed to nothing polygonal cannot be
            # weighed -- every intersection is zero -- but the point pass had
            # already placed it, and that placement was sound. Re-weighing it
            # here would unparent a unit for having no area, which is not a
            # reason to doubt where its representative point fell.
            continue
        if sitting is not None:
            held = shapely.intersection(unit, sitting["_geom"]).area
            if held * 2 > unit.area:
                # A majority is unbeatable: the rest of the country has less
                # than half the unit between all of it.
                continue
            best = sitting if held > 0 else None
        for idx in tree.query(unit):
            candidate = rows[int(idx)]
            if candidate is sitting:
                continue
            area = shapely.intersection(unit, candidate["_geom"]).area
            if area > held:
                best, held = candidate, area
        if best is None:
            row["parent_shape"] = None
            unplaced.append(f"{row['name']} ({row['group']})")
            continue
        row["parent_shape"] = best["shape_id"]
        if best["shape_id"] != was:
            moved += 1
            if row["group"] in TRACE:
                # The name, not the shape id: this line is read by a person
                # deciding whether the move is right, and "not
                # 66845921B82067974050695" tells them nothing.
                log(f"    {row['group']} {row['name']}: parent by area is "
                    f"{best['name']}, not {sitting['name'] if sitting else '(none)'} "
                    f"({held / unit.area * 100:.1f}% inside)")
    return moved, unplaced


# ---------------------------------------------------------------------------
# Attribute side
# ---------------------------------------------------------------------------

def load_adapters() -> dict[str, list[dict[str, Any]]]:
    """Every adapter record, bucketed by country, in authority order."""
    by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for filename in ADAPTER_FILES:
        path = PROCESSED / filename
        rows = read_json(path, None)
        if not rows:
            continue
        log(f"  adapter {filename}: {len(rows)} records")
        for row in rows:
            iso3 = (row.get("country") or (row.get("id") or "")[:3]).upper()
            # Which file a row came from decides whether two rows landing on one
            # shape are a conflict. Across files it is normal -- India's C-01 and
            # C-16 both describe Kargil -- and within one file it means one of
            # them is wrong.
            row["_source"] = filename
            by_country[iso3].append(row)
    return by_country


def load_curated() -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    payload = read_json(ROOT / "data" / "curated" / "admin1_seed.json", {})
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("rows", []):
        rows[row["country"]].append(row)
    return rows, payload.get("_provenance", {})


# ---------------------------------------------------------------------------
# What a country's "other" holds
# ---------------------------------------------------------------------------
#
# The country panel's figures come from the Factbook, which prints one line per
# field and no note at all. Where a country's residual is large -- Vanuatu's
# "indigenous languages" is 82.6% of everybody, Bahrain's "other" religion a
# quarter of the country -- the question the reader has is what is inside it,
# and the Factbook's line cannot answer it.
#
# Two kinds of answer go in data/curated/admin0_detail.json. A row with
# ``groups`` replaces the field with a census's own division of it, which is
# always the better answer and is used wherever such a table exists. A row with
# only a ``note`` says what the bucket holds and why it is not divided, which
# is what is left when the census published one number and no break-up of it.
# Neither invents a split.
#
# This is the admin-0 counterpart of data/curated/admin1_seed.json, and it is a
# curated file for the same reason that one is: an adapter cannot reach admin0.
# Adapter output lands on admin1 and admin2 shapes; the country record is the
# Factbook profile plus whatever its children roll up into it, and there is no
# third door.


def load_country_detail() -> dict[str, list[dict[str, Any]]]:
    """ISO3 -> the curated admin-0 rows for it."""
    payload = read_json(ROOT / "data" / "curated" / "admin0_detail.json", {})
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("rows", []):
        rows[row["country"]].append(row)
    return rows


def apply_country_detail(admin0: list[dict[str, Any]],
                         rows: dict[str, list[dict[str, Any]]]) -> None:
    """Attach the curated notes and compositions to the country records.

    Runs after the roll-ups, so a curated row is the last word on the field it
    names. That order is the point: a note about a Factbook residual would be
    left standing beside a figure summed from the country's own divisions if
    the roll-up ran afterwards, describing a column that is no longer there.

    Every row must find its country and must name a field that exists, and a
    row that does not stops the build. A curated file whose keys have drifted
    fails silently otherwise -- the note simply never appears, which looks
    exactly like a country that was never given one.
    """
    by_id = {entity["id"]: entity for entity in admin0}
    applied = 0
    for iso3, country_rows in sorted(rows.items()):
        entity = by_id.get(iso3)
        if entity is None:
            raise SystemExit(
                f"admin0_detail: no country record with id {iso3!r}. The "
                f"curated rows for it would go nowhere and nothing would say "
                f"so.")
        for row in country_rows:
            field = row["field"]
            if field not in ("religion", "language", "ethnicity"):
                raise SystemExit(
                    f"admin0_detail: {iso3} names field {field!r}, which is "
                    f"not one of the three compositions.")
            if row.get("groups"):
                entity[field] = row["groups"]
                if row.get("year"):
                    entity[f"{field}_year"] = row["year"]
                if row.get("basis"):
                    entity[f"{field}_basis"] = row["basis"]
            entity[f"{field}_note"] = row["note"]
            if row.get("source"):
                entity.setdefault("sources", []).append(
                    {"field": field, "name": row["source"],
                     "url": row.get("url"), "year": row.get("year"),
                     "license": row.get("license", "See docs/SOURCES.md")})
            applied += 1
    log(f"  admin0 detail: {applied} curated rows on "
        f"{len(rows)} countries")


def primary_country_profiles(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Choose the one profile that can supply each ISO3 boundary."""
    countries: dict[str, dict[str, Any]] = {}
    for row in rows:
        iso3 = (row.get("codes") or {}).get("iso3")
        if not iso3:
            continue
        if row["id"] == iso3 or iso3 not in countries:
            countries[iso3] = row
    return countries


def geometryless_profiles(rows: list[dict[str, Any]],
                          countries: dict[str, dict[str, Any]],
                          matched_iso3: set[str]) -> list[dict[str, Any]]:
    """Retain unmatched primaries and every distinct secondary profile."""
    primary_ids = {source["id"] for source in countries.values()}
    return [source for source in rows
            if (source.get("codes") or {}).get("iso3")
            and not (source["id"] in primary_ids
                     and (source.get("codes") or {}).get("iso3") in matched_iso3)]


def subdivision_owner(entity: dict[str, Any]) -> str | None:
    """The ISO3 whose admin1 and admin2 rows belong to this record, if any.

    Subdivisions are keyed by ISO3, and for almost every admin0 record the code
    is the key: it is the sole profile for that code, so its id and its country
    are the same string. The exception is a *secondary* Factbook profile -- the
    West Bank inside PSE, Svalbard inside SJM, Clipperton Island inside FRA,
    Ashmore and Cartier inside AUS. Those are distinct places that share their
    administering state's code, and they own no subdivisions here.

    Reading the code's rows for them would report Australia's 9 states and 547
    districts as the *uninhabited* Coral Sea Islands' own, and France's 13
    regions as Clipperton Island's -- an unmatched row is a visible gap, but a
    mis-matched one is invisible, which is exactly what the coverage matrix
    exists to prevent.
    """
    iso3 = entity.get("country") or entity.get("id")
    return iso3 if entity.get("id") == iso3 else None


def apply_curated(entity: dict[str, Any], row: dict[str, Any], prov: dict[str, Any]) -> None:
    source = prov.get("source")
    year = prov.get("year")
    if row.get("population"):
        entity["population"] = measure(row["population"], year=year, source=source)
    if row.get("capital"):
        entity["capital"] = row["capital"]
    if row.get("largest_settlement"):
        entity["largest_settlement"] = row["largest_settlement"]
    if row.get("sex_ratio_f_per_1000_m"):
        entity["sex_ratio"] = measure(row["sex_ratio_f_per_1000_m"],
                                      unit="females_per_1000_males", year=year, source=source)
    for field in ("religion", "ethnicity", "language"):
        if row.get(field):
            entity[field] = row[field]
            # The same rule the adapters keep: the year describes the figure,
            # so it is written with it. The provenance block already states one
            # per country -- India's 2011, China's 2020 -- and it was reaching
            # the population and the sex ratio while the compositions beside
            # them went out undated.
            if prov.get("year"):
                entity[f"{field}_year"] = prov["year"]
            if prov.get("note"):
                entity[f"{field}_note"] = prov["note"]
    for field in ("religion", "ethnicity"):
        policy = prov.get(f"{field}_policy")
        if policy and is_gap(entity.get(field)):
            entity[field] = gap(NOT_COLLECTED, policy)
    entity.setdefault("sources", []).append(
        {"field": "curated", "name": source, "year": year,
         "note": prov.get("note"), "license": "See docs/SOURCES.md"})


# What makes a row an answer rather than a label. Wikidata supplies a shape's
# capital, coordinates, inception and ISO code and none of these; a census
# adapter supplies these. The distinction is what lets a code-matched row merge
# into a shape a Wikidata row already matched by name, without ever letting two
# sets of figures land on one shape.
VALUE_FIELDS = frozenset({"religion", "language", "ethnicity", "population",
                          "median_age", "sex_ratio", "largest_settlement"})


def value_fields(row: dict[str, Any]) -> set[str]:
    """The questions this row actually answers, gaps not counted."""
    return {k for k in VALUE_FIELDS if k in row and not is_gap(row[k])}


# What a composition carries beside itself: when it was counted, what it counts,
# and how the source qualifies it. All three describe the figure, so all three
# go with it when it is replaced -- see merge_adapter.
SATELLITES = ("_year", "_basis", "_note")
# The fields those describe. Wider than ROLLUP_FIELDS, which is about what can
# be summed: ancestry and India's scheduled groups are never summed and are
# still figures somebody measured in some year.
DESCRIBED_FIELDS = ("religion", "language", "ethnicity", "ancestry",
                    "scheduled_groups")


# Sources whose head count fills an empty population and never replaces one.
#
# ADAPTER_FILES ranks files by what they are for, and the rank is about the
# compositions: Japan's prefecture file sits among the models because its
# religion is modelled, Viet Nam's and Laos's census files sit high because
# nothing else writes their ethnicity. Each of those files also carries its
# census head count, and the Wikidata sweep lower down replaced it -- all 47
# of Japan's prefectures, 8 of Laos's provinces, 17 of Korea's, and 33 of Viet
# Nam's, where it did real damage. Viet Nam merged its 63 provinces into 34 in
# 2025 and Wikidata's P1082 moved with the merger, so the boundary file's
# pre-merger polygons wore the merged provinces' populations: Ho Chi Minh City
# 14.0 million, which is the old city with Binh Duong and Ba Ria-Vung Tau, and
# the country's first level summed to 126% of the country.
#
# A statistical office's count is not replaced by an encyclopaedia's, whatever
# order the files are read in. These two only ever fill a population nobody
# else has written.
FILL_ONLY = frozenset({"wikidata_admin1.json", "wikidata_admin2.json",
                       "wiki_population_admin1.json"})
FILL_ONLY_FIELDS = frozenset({"population"})


def merge_adapter(entity: dict[str, Any], row: dict[str, Any]) -> None:
    """Adapter values override seeds; gap markers never overwrite real values.

    A source that is superseded goes with the figures it produced. PRRI
    replaces the 2020 Religion Census on every county it covers, and keeping
    both citations left the panel crediting a study whose numbers were no
    longer on the record -- the first religion source listed was the one that
    had just been overwritten. A citation describes the value held now.

    Only a source whose every field is being replaced is dropped. The ACS is
    cited for "ethnicity/language/population" at once, and a row that replaces
    religion has nothing to say about those.

    The year, the basis and the note go the same way, and for the same reason.
    California's curated seed carried the 2011-2022 ACS as a placeholder and
    stamped 2022 on it; the live ACS row then replaced the figure, said nothing
    about a year, and the 2022 stayed -- describing numbers it had never seen,
    on three states out of fifty-two, which was enough for the country's sum to
    inherit it and read as dated. It happened to be the right year, which is
    exactly what made it worth removing: nothing on the record distinguished it
    from a wrong one. A row that replaces a figure owns what describes it, and
    what the row does not say is not carried over from what it displaced.
    """
    held = {key for key in FILL_ONLY_FIELDS
            if row.get("_source") in FILL_ONLY and not is_gap(entity.get(key))}
    replaced = {key for key, value in row.items()
                if key in VALUE_FIELDS and not is_gap(value) and key not in held}
    if replaced:
        entity["sources"] = [
            src for src in entity.get("sources", [])
            if not (str(src.get("field") or "").split("/")
                    and all(part in replaced
                            for part in str(src.get("field") or "").split("/")))]
    for key, value in row.items():
        if key in {"id", "level", "name", "parent", "parent_name", "parent_aliases",
                   "match_by", "_source"}:
            continue
        if key == "sources":
            # A citation for a figure that was held back describes nothing
            # on the record, so it is not added either.
            kept = [src for src in (value or [])
                    if not (held and set(str(src.get("field") or "").split("/")) <= held)]
            entity.setdefault("sources", []).extend(kept)
            continue
        if key in held:
            continue
        if is_gap(value) and not is_gap(entity.get(key)):
            continue
        # Among gaps, an estimate is the more informative one, so a bare
        # marker from a later file does not displace it. A policy statement
        # does: "the country does not count this" is the stronger claim, and
        # the one an estimate must never stand in front of.
        if (is_gap(value) and is_estimate(entity.get(key))
                and not (isinstance(value, dict)
                         and value.get("status") == NOT_COLLECTED)):
            continue
        entity[key] = value
    # After the copy, not before it: a satellite the row does supply has just
    # overwritten the old one in place, and popping first would have moved it
    # to the end of the record. build.json is a digest of the written files, so
    # a key order that churns invalidates every reader's cache for no change in
    # the figures.
    for field in DESCRIBED_FIELDS:
        if is_gap(row.get(field)) or field not in row:
            continue
        for suffix in SATELLITES:
            if f"{field}{suffix}" not in row:
                entity.pop(f"{field}{suffix}", None)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

# How much longer a boundary file's last word may be than the source's and still
# be the same word. An inflected or adjectival ending is what this is for --
# "Stockholm" against "Stockholms", "Plzen" against "Plzensky", "Northeast"
# against "Northeastern" -- and three characters covers those without reaching
# a different word: "Tala" against "Talampaya" is five.
INFLECTION_SLACK = 3

# The shortest word a match may rest on when it starts partway through a name.
# "Fes" is three letters and sits at the end of "Oued Fes", a different commune;
# a name has to give more than that before a match starting mid-way is worth
# believing. A match anchored at the first word is stronger evidence, so there
# a short word may still match, but only outright -- which is what carries
# "Lae Atoll" to "Lae" while "San" stays out of "Santa Cruz".
PREFIX_MIN = 4


@lru_cache(maxsize=200_000)
def tokens(text: str | None, joined: bool = False) -> tuple[str, ...]:
    """A name's words, folded the way norm() folds the whole string.

    norm() exists to compare two names as one key; this exists to compare them
    a word at a time, which is the only way to tell a name from a fragment of
    one that happens to straddle two words.
    """
    if not text:
        return ()
    folded = unicodedata.normalize("NFKD", text.lower()).translate(FOLD)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = re.sub(GENERIC, " ", folded)
    if joined:
        folded = re.sub(r"[-\u2010\u2013]", "", folded)
    out = []
    for word in re.split(r"[^\w]+", folded, flags=re.UNICODE):
        word = "".join(c for c in word if c.isalnum())
        if word:
            out.append(word)
    return tuple(out)


def name_forms(text: str | None) -> tuple[tuple[str, ...], ...]:
    """A name's words, read both ways a hyphen can be read.

    Neither reading is right on its own. Joining fixes CGAZ's "Bio-Bio" against
    a source's "Biobio", and Timor-Leste's "Oe-Cusse" against "Oecusse".
    Splitting fixes an Arabic article the other side leaves off -- "Al-Basrah"
    against "Basra", "An-Najaf" against "Najaf" -- where the article is its own
    word and the match is a run that starts after it. Trying both costs one
    extra comparison in a pass that only runs when the exact one has failed.
    """
    split, join = tokens(text), tokens(text, joined=True)
    return (split,) if split == join else (split, join)


def run_of(short: tuple[str, ...], long: tuple[str, ...], *,
           at_start: bool = False) -> bool:
    """Whether `short` appears in `long` as a run of whole words.

    The last word may run two characters short of its counterpart, which is what
    carries "Stockholm" into "Stockholms lan" -- a source and a boundary file
    disagreeing about an inflected ending, not about which place they mean. Any
    more slack than that and a word matches a different word: "Tala" is a prefix
    of "Talampaya", and Argentina's Talampaya National Park was joined to Tala,
    835 km away. Every earlier word has to match outright, so "anta" cannot
    creep into "santa".
    """
    if not short or len(short) > len(long):
        return False
    starts = [0] if at_start else range(len(long) - len(short) + 1)
    for start in starts:
        window = long[start:start + len(short)]
        tail, target = short[-1], window[-1]
        if not all(a == b for a, b in zip(short[:-1], window[:-1])):
            continue
        if len(tail) < PREFIX_MIN and not (at_start and start == 0):
            continue
        if tail == target:
            return True
        if len(tail) >= PREFIX_MIN and target.startswith(tail) \
                and len(target) - len(tail) <= INFLECTION_SLACK:
            return True
    return False


def related(mine: tuple[tuple[str, ...], ...], theirs: tuple[tuple[str, ...], ...],
            *, at_start: bool = False) -> bool:
    """Whether either name contains the other, under any reading of a hyphen."""
    return any(run_of(a, b, at_start=at_start) or run_of(b, a, at_start=at_start)
               for a in mine for b in theirs)


def match_name(row: dict[str, Any], lookup: dict[str, dict[str, Any]]
               ) -> tuple[dict[str, Any] | None, str]:
    """Exact normalised name, then declared aliases, then a *unique* prefix match.

    The prefix pass is what bridges "Tibet" to CGAZ's "Tibet Autonomous Region";
    it refuses to guess when more than one shape would match.
    """
    for candidate in [row["name"], *row.get("aliases", [])]:
        key = norm(candidate)
        if key in lookup:
            return lookup[key], "name" if candidate == row["name"] else "alias"
    # Whole words again, anchored at the first one: this is what bridges
    # "Mymensingh Division" to CGAZ's "Mymensingh" and "Alif Alif Atoll" to
    # "Alif Alif". On the squashed string it did what the containment pass did,
    # and read straight across word boundaries -- "Tala" starts
    # "talampayanationalpark", so Argentina's Talampaya National Park was joined
    # to Tala, 835 km away.
    for candidate in [row["name"], *row.get("aliases", [])]:
        mine = name_forms(candidate)
        if not any(mine):
            continue
        hits = [v for k, v in lookup.items()
                if related(mine, name_forms(v["name"]), at_start=True)]
        if len(hits) == 1:
            return hits[0], "prefix"
    # Last pass: unique containment, word by word. This is what bridges a
    # source's long official form to the boundary file's short one -- Wikidata's
    # "Canton of Zurich" to CGAZ's "Zurich", "Stockholms lan" to "Stockholm",
    # "Emirate of Sharjah" to "Sharjah". Exactly one shape may qualify.
    #
    # Word by word, and not by substring, because norm() squashes a name into
    # one run of letters and a substring test then reads straight across the
    # gaps between words. "Anta" is four letters and sits inside "santacruz",
    # so Argentina's Santa Cruz was joined to Anta, 406 km away; Santa Anita
    # went to the same shape, 817 km away. Comparing tokens instead means a
    # match has to start where a word starts.
    for candidate in [row["name"], *row.get("aliases", [])]:
        mine = name_forms(candidate)
        if not any(mine):
            continue
        hits = [v for k, v in lookup.items() if related(mine, name_forms(v["name"]))]
        if len(hits) == 1:
            return hits[0], "contains"
    return None, "unmatched"


def settle(by_name: dict[str, list[dict[str, Any]]],
           names: Sequence[str] = (),
           parent_id: str | None = None) -> dict[str, dict[str, Any]]:
    """The shapes inside one admin-1, keyed by name, dropping any still ambiguous.

    Ambiguous is not always undecidable. norm() drops the word "city", so
    geoBoundaries' "Cotabato" and "Cotabato City" -- a province and the city
    that is an enclave inside its neighbour, both drawn in Soccsksargen --
    arrive here under one key and both used to be thrown away. The province was
    then left to the containment pass, which handed it South Cotabato, a
    different province of 900,000 people; the refusal that caught that came
    from the collision pass, so what the map showed was a gap where a census of
    1.4 million people had been.

    Where exactly one of the rivals is written the way the row writes it, that
    is stronger evidence than the normalised key which made them look alike,
    and the tie is settled instead of refused. Nothing is settled on anything
    weaker: an identical name is the only tiebreak here, so this pass can add a
    match but never move one.
    """
    exact = {n.strip().casefold() for n in names if n}
    out = {}
    for key, entities in by_name.items():
        inside = entities if parent_id is None else \
            [e for e in entities if e.get("parent") == parent_id]
        if len(inside) == 1:
            out[key] = inside[0]
        elif len(inside) > 1 and exact:
            named = [e for e in inside
                     if (e.get("name") or "").strip().casefold() in exact]
            if len(named) == 1:
                out[key] = named[0]
    return out


def row_point(row: dict[str, Any]) -> list[float] | None:
    """The adapter row's own coordinates, if it published any.

    Wikidata writes them to `coordinates` and uses the same field to carry a gap
    marker when P625 is absent, so the shape of the value is the test.
    """
    for field in ("coordinates", "point"):
        value = row.get(field)
        if isinstance(value, (list, tuple)) and len(value) == 2 \
                and all(isinstance(n, (int, float)) for n in value):
            return [float(value[0]), float(value[1])]
    return None


def within_bbox(point: list[float] | None, bbox: list[float] | None) -> bool:
    """Whether a coordinate falls in a shape's bounding box.

    Deliberately weak as confirmation and strong as refutation: ADM2 geometry is
    dropped after the parent pass (49,349 polygons will not stay in memory), so a
    box is all there is to compare against. A point inside the box is not proof
    it is inside the shape; a point outside the box is proof it is not.
    """
    if not point or not bbox or len(bbox) != 4:
        return False
    return bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]


def match_admin2(row: dict[str, Any], by_name: dict[str, list[dict[str, Any]]],
                 admin1: dict[str, dict[str, Any]],
                 exact: dict[str, dict[str, Any]] | None = None,
                 ) -> tuple[dict[str, Any] | None, str]:
    """Resolve an adapter row to one admin-2 shape, using its state when it has one.

    District names repeat across states. India has a Hamirpur in Himachal Pradesh
    and another in Uttar Pradesh, a Pratapgarh in Rajasthan and another in Uttar
    Pradesh, an Aurangabad in Maharashtra and another in Bihar. A lookup keyed on
    name alone keeps whichever shape it saw last, which makes one district
    unreachable and lets the other quietly wear its twin's figures -- a wrong
    answer that looks exactly like a right one.

    So a row that names its parent state is matched only inside that state. A row
    that does not is matched only against names that are unique country-wide;
    where the name is ambiguous the row is refused, on the same principle the
    prefix and containment passes already follow -- an unmatched row is a visible
    gap, a mis-matched one is invisible.

    The one case that used to slip through was a row that named a state, resolved
    it, found nothing of that name inside -- and was then handed to the
    country-wide pass anyway, which happily matched a shape in a different state.
    That is the mis-match this function exists to prevent, arrived at by the
    function's own fallback: 443 rows across nine countries, among them Vietnam's
    An Duong (Haiphong, per Wikidata) wearing the figures of An Duong in Hai
    Duong, and Argentina's Apostoles Department (Misiones) wearing Corrientes'.
    A row that contradicts itself is refused when its own published coordinates
    land outside the shape, and kept when they land inside -- which is what
    rescues the city-provinces whose parent is named historically rather than
    currently, Bogota under Cundinamarca and Lima under Lima Department.

    The disagreement on its own is deliberately *not* enough to refuse on, and
    India is the reason. Its district figures are from the 2011 census, so they
    name the states of 2011: Adilabad and Nizamabad say Andhra Pradesh where the
    boundary file says Telangana, Leh and Kargil say Jammu and Kashmir where it
    says Ladakh. Those matches are correct -- the same district, named before the
    state it sits in was split -- and refusing every parent disagreement would
    have deleted 26 of them, along with correct rows in Mexico and the US. The
    census adapters publish no coordinates, so there is no evidence either way,
    and a rule with no evidence behind it should not be deciding.
    """
    parent_name = row.get("parent_name")
    if parent_name:
        # The parent name is matched with aliases too, because boundary files
        # and statistical agencies disagree about renamings: CGAZ still calls
        # Mexico City "Distrito Federal", a name it lost in 2016, so without an
        # alias none of its sixteen alcaldias can be scoped to it and the ones
        # sharing a name with a municipio elsewhere -- Benito Juarez, also in
        # Quintana Roo; Cuauhtemoc, also in Chihuahua and Colima -- are refused
        # as ambiguous.
        # An exact name first: norm() drops the generic word, so "Almaty Region"
        # and the city "Almaty" share one key and whichever was keyed last
        # answered for both -- which scoped Almaty Region's districts to the
        # city, where none of them are, and refused the two whose names repeat
        # elsewhere (Aksuskiy, Zhambylskiy) as ambiguous.
        # `exact` holds every first-level shape by its written name, the
        # ambiguous ones included, since a written name is not ambiguous.
        wanted = " ".join(parent_name.split()).casefold()
        parent = (exact or {}).get(wanted) or next(
            (e for e in admin1.values()
             if " ".join((e.get("name") or "").split()).casefold() == wanted), None)
        if parent is None:
            parent, _ = match_name({"name": parent_name,
                                    "aliases": row.get("parent_aliases") or []}, admin1)
        if parent is not None:
            scoped = settle(by_name, [row["name"], *row.get("aliases", [])],
                            parent["id"])
            entity, how = match_name(row, scoped)
            if entity is not None:
                return entity, f"{how}+state"
            # The row said which admin-1 it is in and no shape of its name is
            # there, so a country-wide match now would contradict the row's own
            # claim. Whether that contradiction is an error is decided by the
            # row's coordinates and by nothing else -- see the note below on why
            # the disagreement alone is not enough to refuse on.
            unique = {key: entities[0] for key, entities in by_name.items()
                      if len(entities) == 1}
            entity, how = match_name(row, unique)
            point = row_point(row)
            if entity is not None and point:
                if within_bbox(point, entity.get("bbox")):
                    return entity, f"{how}+point"
                return None, "outside_parent"
            # No coordinates to settle it, so the kind of name match decides.
            #
            # An exact name is evidence in its own right: India's Adilabad says
            # Andhra Pradesh and the boundary file says Telangana, and it is the
            # same district named before its state was split. Twenty-six such
            # matches are correct and refusing them would delete real figures.
            #
            # A prefix or containment match is not. It is already a guess about
            # which shape a longer name means, and made *across* a contradiction
            # the row itself states it is two weak signals stacked. That is how
            # "Western Connecticut Planning Region, Connecticut" came to wear
            # the Western District of American Samoa, 12,000 km away, carrying
            # Connecticut's population and a note about Connecticut's counties.
            if entity is not None and how not in ("name", "alias"):
                return None, "outside_parent"

    unique = {key: entities[0] for key, entities in by_name.items() if len(entities) == 1}
    entity, how = match_name(row, unique)
    if entity is not None:
        return entity, how
    if norm(row.get("name") or "") in by_name:
        return None, "ambiguous"
    return None, "unmatched"


# ---------------------------------------------------------------------------
# Summing a parent from its children
# ---------------------------------------------------------------------------

ROLLUP_FIELDS = ("religion", "language", "ethnicity")

# How far the children's population may sit from the parent's own before the
# sum is refused. Rounding and small-cell suppression move it a little -- New
# Zealand randomly rounds every count to a multiple of three -- and anything
# beyond this is the two figures describing different things.
ROLLUP_TOLERANCE = 0.02

# How much the population gate widens per year between the two figures' dates,
# and the most it will ever widen by. A census and an estimate of the same
# territory taken years apart are the same people counted at different times,
# and the difference between them is growth rather than a fault: Bangladesh's
# divisions carry 2011 figures and its districts the 2022 census, so the
# children exceed their parents by about a tenth. The cap keeps this from ever
# becoming a licence -- Wales' children exceed their parent by 166%, which is
# two different things being counted and stays refused at any drift.
ROLLUP_DRIFT_PER_YEAR = 0.015
ROLLUP_DRIFT_CAP = 0.20

# How much of a country's population its first-level divisions must carry
# before the country is summed from the ones that publish. It is the same 2%
# the population gate above allows, spent on the same kind of thing: there it
# is the gap between two counts of the same people, here it is the part of the
# country the sum does not reach. Both bound the error rather than denying it,
# and this one is stated on the record the reader sees.
#
# The level below is deliberately not given this. There a refused parent leaves
# a gap, which is honest; here it leaves the Factbook's older estimate standing
# in place of the divisions' own recent count, and pretending that is the
# safer of the two is what this constant refuses to do. 2% is also what keeps
# it to near-complete sets: India at 97.2% -- Telangana never published a 2011
# religion row -- stays refused, and says so with the figure.
COUNTRY_MIN_COVERAGE = 0.98

# How much of a summed figure's population must share one year before that
# year is stamped on it. The same 98%, for the same reason: a date is a claim
# about the whole record, so it is allowed only when nearly the whole record
# supports it. Pakistan is the case -- four provinces and Islamabad from the
# 2023 census and Azad Kashmir from 2017, which is 1.65% of the people -- and
# leaving that undated served nobody: the figure is a 2023 one with a stated
# exception, and a blank where the year goes reads as an omission. A country
# genuinely split between two censuses stays undated, and the note lists them.
YEAR_MAJORITY = 0.98


def published(value: Any) -> float | None:
    """A measured number, or None for a gap marker or anything else."""
    if isinstance(value, dict) and isinstance(value.get("value"), (int, float)):
        return float(value["value"])
    return None


def vintage(value: Any) -> int | None:
    """The year a measured number is for, when it says."""
    if isinstance(value, dict) and isinstance(value.get("year"), int):
        return value["year"]
    return None


def common_year(children: list[dict[str, Any]]) -> int | None:
    """The year most of the children's populations are for.

    The commonest rather than the newest: one child out of seventeen carrying a
    later date should not decide what the set is. New Zealand's territorial
    authorities are 2023 except for the Chatham Islands, whose figure this
    function's own caller had just rebuilt from its children and stamped 2025 --
    and reading the set as 2025 inverted the direction test and refused the
    whole country.
    """
    years = [y for y in ((vintage(c.get("population")) or None) for c in children)
             if y]
    if not years:
        return None
    counted: dict[int, int] = {}
    for year in years:
        counted[year] = counted.get(year, 0) + 1
    return sorted(counted, key=lambda y: (-counted[y], -y))[0]


def allowance(own_year: int | None, child_year: int | None,
              own: float, total: float) -> float:
    """How far the children may sit from the parent before it is a fault.

    Two figures of the same year should agree to the base tolerance. Two of
    different years should differ, in the direction time moves: children newer
    than their parent should be larger, children older should be smaller. The
    gate widens with the gap between the dates, but only for a difference
    pointing that way -- children *below* an older parent is shrinkage, which
    is what a missing child looks like, and gets no allowance at all.
    """
    if own_year is None or child_year is None or own_year == child_year:
        return ROLLUP_TOLERANCE
    newer = child_year > own_year
    if newer != (total > own):
        return ROLLUP_TOLERANCE
    drift = min(abs(child_year - own_year) * ROLLUP_DRIFT_PER_YEAR,
                ROLLUP_DRIFT_CAP)
    return ROLLUP_TOLERANCE + drift


def implied_total(groups: list[dict[str, Any]]) -> float | None:
    """The denominator a composition's own percentages were taken against.

    Not the unit's population, which is a different number more often than not:
    Mexico publishes indigenous-language shares of the population aged three and
    over, and New Zealand's ethnicity responses outnumber its people because one
    person may give several. Backing the denominator out of the rows keeps
    whatever basis the source used, so a parent summed from its children states
    the same kind of thing its children state.

    Taken from the largest group, whose percentage carries the least rounding
    error: a category at 0.0% would imply any denominator at all.
    """
    best: tuple[float, float] | None = None
    for row in groups:
        pct, count = row.get("pct"), row.get("count")
        if not isinstance(pct, (int, float)) or not isinstance(count, (int, float)):
            continue
        if pct <= 0:
            continue
        if best is None or count > best[0]:
            best = (count, count / (pct / 100.0))
    return best[1] if best else None


def year_weights(children: list[dict[str, Any]], field: str
                 ) -> tuple[dict[int, float], float]:
    """Population behind each year the children stamp, and the total behind all.

    Weighted by people rather than by counting divisions, because a date
    describes the figure and the figure is a sum of people: one small division
    on an older census should not take the date off a national count, and one
    large one should not keep it.
    """
    weight: dict[int, float] = {}
    total = 0.0
    for child in children:
        if not isinstance(child.get(field), list):
            continue
        pop = published(child.get("population")) or 0.0
        total += pop
        year = child.get(f"{field}_year")
        if isinstance(year, int):
            weight[year] = weight.get(year, 0.0) + pop
    return weight, total


def covered_share(children: list[dict[str, Any]], field: str) -> float | None:
    """How much of the children's population is carried by those with `field`.

    The bound on a partial sum, and the only number that makes one publishable:
    a group's share taken from 98.9% of a country can be wrong by at most the
    1.1% that was left out, so a reader told the figure can judge it. Without
    it there is no difference between a sum missing Wyoming and a sum missing
    California.

    Returns None when it cannot be measured, and the case that matters is a
    child with no `field` *and* no published population. Such a child is
    invisible to both sums, so leaving it out would inflate the answer in the
    one direction that must never be inflated -- the shares of the units that
    published nothing are exactly what an unmeasured tail is. A child that has
    the field and no population is the opposite and is simply dropped: it
    leaves both sums, which can only understate the coverage.
    """
    covered = total = 0.0
    for child in children:
        pop = published(child.get("population"))
        has = isinstance(child.get(field), list)
        if pop is None:
            if not has:
                return None
            continue
        total += pop
        if has:
            covered += pop
    return covered / total if total > 0 else None


def roll_up_field(parent: dict[str, Any], children: list[dict[str, Any]],
                  field: str, *, level: str = "second-level",
                  over_published: bool = False,
                  whole_country: bool = False,
                  complete: bool | None = None,
                  min_coverage: float | None = None) -> str | None:
    """Fill a parent's composition by summing a complete set of its children.

    Ladakh is the case this exists for. It became a union territory in 2019, so
    the 2011 census that supplies India's district figures never published a row
    for it -- but it published both of its districts, Leh and Kargil, and their
    counts sum to exactly the population Wikidata gives Ladakh: 274,289. A
    territory whose every constituent part is measured should not read as
    unmeasured.

    Returns a reason string when it refuses, so the build can say what it did
    not do and why. The refusals are the point of the function as much as the
    sums are:

      * Australia's LGAs carry religion but no population, so their populations
        sum to zero. Weighting by nothing would produce a state figure with no
        basis at all -- nine states' worth.
      * Wales' 22 children sum to 3,107,513 against a parent figure of
        1,168,000. Whatever those two numbers are counting, it is not the same
        people, and a sum across that gap would be invented.

    Only a parent with an independently published population can be checked at
    all, so only such a parent is filled. A control that came from the same
    source as the children would prove the arithmetic and nothing else.

    ``whole_country`` is the one thing that replaces that control, and it is a
    stronger one. The population comparison is a proxy for "are these all the
    children"; when *every* shape at this level in the country carries the
    field, the shapes partition the country and the answer is yes by
    construction, for every parent. Bangladesh is the case: 64 of 64 districts
    join, so each of its eight divisions has all of its districts, including
    the two divisions that have no published population of their own to be
    checked against. Pakistan is why it is not assumed -- 114 of its 126
    districts join, so its provinces are genuinely short and stay refused.
    """
    current = parent.get(field)
    if isinstance(current, list) and not over_published:
        return None                                   # already has a real value
    if isinstance(current, dict) and current.get("status") == NOT_COLLECTED:
        return None            # a policy statement, not a gap: leave it standing
    if not children:
        return None

    # A sum is of figures that count the same thing, and `{field}_basis` is
    # where a source says when it does not. Gilgit-Baltistan is the only place
    # in the world where this bites: it is the one division of Pakistan with a
    # sectarian breakdown, so the national sum came out listing Twelver Shi'a
    # at 0.2% -- arithmetically right, since its people appear once, and a flat
    # misstatement about a country that is perhaps a sixth Shia. The 0.2% is an
    # artefact of one division in fifty answering a different question.
    #
    # So a division counting something its siblings do not is left out and
    # named, exactly as one that publishes nothing is. Its own record keeps the
    # detail, which is where that detail is true.
    # Which basis is the usual one is decided by people, not by counting
    # divisions -- the same weighting the year rule uses, and for the same
    # reason: one small division answering differently should not make the
    # rest the exception. Ties are broken on the name so the answer does not
    # depend on the hash seed; this was found by CI disagreeing with a local
    # run about which of two equally-sized divisions was the odd one out.
    weight: dict[Any, float] = {}
    for child in children:
        if isinstance(child.get(field), list):
            basis = child.get(f"{field}_basis")
            weight[basis] = weight.get(basis, 0.0) + (
                published(child.get("population")) or 0.0)
    usual = (max(sorted(weight, key=lambda b: (b is not None, str(b))),
                 key=lambda b: weight[b])
             if weight else None)
    apart = [c for c in children if isinstance(c.get(field), list)
             and c.get(f"{field}_basis") != usual]
    if apart:
        children = [c for c in children if c not in apart]

    missing = [c for c in children if not isinstance(c.get(field), list)]
    left_out = ""
    if missing:
        # Partial coverage is the dangerous case: the sum would look whole and
        # describe only part of the territory. It is refused by default and
        # always was.
        #
        # `min_coverage` is the one place that is relaxed, and only for a
        # country summed from its first-level divisions, because there the
        # alternative is not a gap. It is a coarse published estimate that
        # stays on the map unchallenged: the United States kept a 2014
        # Factbook figure while 51 of its 56 divisions carried a 2024 one,
        # and Thailand, Senegal, Namibia, Niger and Latvia sat the same way.
        # Preferring an old estimate of the whole to a recent measurement of
        # 99% of it is not caution, it is just a different error, and a
        # silent one.
        #
        # What makes it safe enough to allow is that the bias is bounded and
        # stated: a group's share can be wrong by at most the share of the
        # population left out, and the note names the units and that figure,
        # so a reader can see exactly how much of the country the answer
        # describes.
        share = covered_share(children, field)
        if (min_coverage is None or share is None
                or share < min_coverage or len(missing) == len(children)):
            detail = ("" if share is None else
                      f" (the rest are {share:.1%} of the population)")
            return (f"{len(missing)} of {len(children)} children have no "
                    f"{field}{detail}"
                    if len(missing) < len(children) else None)
        listed = sorted(c.get("name", c.get("id", "?")) for c in missing)
        names = ", ".join(listed[:6]) + (" and others" if len(listed) > 6 else "")
        one = len(missing) == 1
        left_out = (f" {len(missing)} of the {len(children)} divisions "
                    f"publish{'es' if one else ''} no {field} and "
                    f"{'is' if one else 'are'} not included ({names}); this "
                    f"figure describes the {share:.1%} of the population that "
                    f"does.")
        children = [c for c in children if isinstance(c.get(field), list)]

    # The population comparison below is a control on one thing: whether these
    # are all the children. ``whole_country`` establishes that directly and
    # more strongly, so where it holds, children without a published
    # population no longer stop the sum -- they only cost it its control.
    # Burkina Faso is the case the change was made for: all thirteen regions
    # carry the census religion and not one carries a population, so a country
    # whose composition was fully determined was published as a gap.
    # Two different permissions, kept apart because they cost different
    # things. ``complete`` says these are certainly all the children, which is
    # what lets the sum happen without a population to check it against.
    # ``whole_country`` additionally lets the sum stand when the parent's own
    # published population disagrees with it -- a stronger step, since it
    # overrules a figure somebody published, and one the country-level pass
    # deliberately does not take.
    if complete is None:
        complete = whole_country
    kid_pop = [published(c.get("population")) for c in children]
    unpriced = sum(v is None for v in kid_pop)
    if unpriced and not complete:
        return f"{field}: {unpriced} children have no population"
    total_pop = sum(v for v in kid_pop if v is not None)
    if not total_pop and not complete:
        return f"{field}: the children have no population between them"

    disagrees = ""
    own = published(parent.get("population"))
    if unpriced or not total_pop:
        # No usable control, and none needed: every shape at this level in the
        # country carries the field, so the children partition it.
        own = None
    if own is None:
        if not complete:
            return f"{field}: no published population to check the sum against"
    else:
        limit = allowance(vintage(parent.get("population")),
                          common_year(children), own, total_pop)
        if abs(total_pop - own) > limit * own:
            drift = "" if limit == ROLLUP_TOLERANCE else \
                f", outside even the {limit:.0%} allowed for their dates"
            if not whole_country:
                return (f"{field}: children sum to {total_pop:,.0f} against a "
                        f"published {own:,.0f}{drift}")
            # Complete children and a parent figure that disagrees with them
            # means the parent's figure is the doubtful one, not the set: Dhaka
            # division carries a 2011 population of 49,729,000 and lost
            # Mymensingh out of it in 2015, so its 44,215,759 people in 2022 are
            # not a shortfall. The sum is taken and the disagreement is written
            # into the note rather than hidden by it.
            disagrees = (f" The unit's own published population of {own:,.0f} "
                         f"disagrees with that by {100 * (total_pop - own) / own:+.0f}%; "
                         "the sum was taken anyway because every division at "
                         "this level in the country carries these figures, so "
                         "these are certainly all of its children.")

    # Computed before the note, because a sum that carries no date owes the
    # reader the reason. Pakistan is the case: four provinces and Islamabad
    # from the 2023 census, Azad Kashmir from 2017, so the sum is genuinely
    # undated -- but a blank where a year belongs reads as an omission rather
    # than as the mixture it is.
    years = {c.get(f"{field}_year") for c in children} - {None}
    weight, weighed = year_weights(children, field)
    # The year nearly everyone in this sum was counted in, where there is one.
    dated = None
    if len(years) > 1 and weighed > 0:
        best = max(weight, key=lambda y: weight[y])
        if weight[best] / weighed >= YEAR_MAJORITY:
            dated = best
    aside = sorted((y, n) for y, n in (
        (c.get(f"{field}_year"), c.get("name", c.get("id", "?")))
        for c in children if isinstance(c.get(field), list))
        if y is not None and y != dated)

    counts: dict[str, float] = {}
    denominator = 0.0
    # Children whose shares had to be priced against their own population
    # because the source published no counts. Named in the note: a sum of
    # derived numbers is a weaker claim than a sum of published ones.
    derived: list[str] = []
    for child in children:
        share = implied_total(child[field])
        rows = child[field]
        priced = all(isinstance(r.get("count"), (int, float)) for r in rows)
        if not priced:
            # A composition of percentages and a published population is
            # enough: the count each share stands for is the share of that
            # population, which is the same arithmetic the source would have
            # done. It is only refused where the population is missing too,
            # because then there is no number to take a percentage of.
            #
            # The base is taken to be the whole population, which is why this
            # runs only when no counts exist: where a source counts a subset
            # -- Mexico's indigenous-language question asks people aged three
            # and over -- it publishes counts, and implied_total backs the
            # real base out of them instead.
            pop = published(child.get("population"))
            if pop is None:
                return f"{field}: a child publishes shares with no counts"
            rows = [dict(r, count=(r["pct"] / 100.0) * pop)
                    for r in rows if isinstance(r.get("pct"), (int, float))]
            share = implied_total(rows)
            derived.append(child.get("name", child.get("id", "")))
        if share is None:
            return f"{field}: a child publishes shares with no counts"
        denominator += share
        for row in rows:
            count = row.get("count")
            if not isinstance(count, (int, float)):
                return f"{field}: a child publishes shares with no counts"
            counts[row.get("group", "")] = counts.get(row.get("group", ""), 0) + count
    if denominator <= 0:
        return f"{field}: the children's percentages imply no denominator"

    parent[field] = [{"group": name,
                      "pct": round(100.0 * total / denominator, 1),
                      "count": int(round(total))}
                     # Name breaks a tie, so two groups of equal size do not
                     # swap places between runs: build.json is a digest of the
                     # written files, and a churning order would invalidate
                     # every reader's cache for no change in the figures.
                     for name, total in sorted(counts.items(),
                                               key=lambda kv: (-kv[1], kv[0]))]
    # Said on the record itself, not only in the source list: a figure nobody
    # published is a different kind of claim from one somebody did, and the
    # panel that shows the bars is where a reader would want to be told.
    many = len(children) != 1
    # A figure that replaced a published one has to say so, and has to say what
    # it replaced. Overwriting the only independent statement about a unit and
    # leaving no trace would turn the control into a casualty of the sum it was
    # there to check.
    displaced = ""
    if isinstance(current, list):
        top = ", ".join(f"{g.get('group')} {g.get('pct')}%" for g in current[:3])
        displaced = (f" Replaces a separately published figure for the unit "
                     f"({top}), which is kept here as the only independent "
                     f"check on this sum.")
    parent[f"{field}_note"] = (
        f"Summed from {'all ' if not left_out else ''}{len(children)} {level} "
        # The semicolon introduces the clause that follows it, so a sum that
        # displaced a published figure -- which has no such clause, it names
        # what it replaced at the end instead -- ends the sentence here.
        # Indonesia read "...34 first-level divisions; Their populations
        # total 281,547,223", a capital letter after a semicolon.
        f"division{'s' if many else ''}{';' if not displaced else '.'}"
        + (" no source publishes this figure for the unit itself."
           if not displaced else "")
        # A unit with no published population of its own was filled because
        # every shape at this level in the country carries the field, so the
        # note says that rather than comparing against a figure there isn't --
        # and where the children themselves carry no population, it says that
        # instead of printing a total nobody published.
        + (f" {'Their' if many else 'Its'} population"
           f"{'s total' if many else ' is'} {total_pop:,.0f}"
           f" against a published {own:,.0f} for the unit."
           if own is not None else
           (f" {'they publish' if many else 'it publishes'} no population of "
            f"{'their' if many else 'its'} own, and"
            if unpriced else
            f" {'Their' if many else 'Its'} population"
            f"{'s total' if many else ' is'} {total_pop:,.0f}, and")
           + " no source publishes a population for the unit to check that "
             "against; it was summed because every division at this level in "
             "the country has these figures, so these are all of its children.")
        + (f" {len(derived)} of them publish shares and no counts"
           f"{' (' + ', '.join(sorted(derived)[:3]) + ')' if len(derived) <= 3 else ''}"
           ", so their counts are those shares taken of their own published "
           "populations." if derived else "")
        + disagrees + displaced + left_out
        + (" " + ", ".join(sorted(c.get("name", c.get("id", "?"))
                                  for c in apart))
           + (f" counts {apart[0].get(f'{field}_basis')} rather than what the "
              f"others count, so it is not added in; its own record carries "
              f"that figure." if len(apart) == 1 else
              " count something the others do not, so they are not added in.")
           if apart else "")
        + (f" Dated {dated} because that is when all but"
           f" {', '.join(f'{n} ({y})' for y, n in aside)} were counted."
           if dated is not None else
           f" The divisions do not all report the same year"
           f" ({', '.join(str(y) for y in sorted(years))}),"
           f" so this figure carries no single date."
           if len(years) > 1 else
           " The divisions do not date their figures, so neither does this."
           if not years else ""))
    # The year belongs to the figure, not to the record, so it is rewritten
    # with it. Thailand is what made this matter: its 76 provinces carry the
    # 2000 census and stamp no year at all, so the sum inherited the 2021 the
    # Factbook estimate had been wearing, and the country's panel dated a
    # quarter-century-old count to five years ago. Britain and Poland were the
    # same fault pointing the other way -- 2021 census children under an
    # inherited 2011.
    #
    # Where the children do not agree on a year the stamp is dropped rather
    # than guessed. That costs the roughly two dozen countries whose displaced
    # figure happened to cite the same census their divisions did; it costs
    # them a label that was right by luck, and the note still says what the
    # figure was summed from. The alternative is a date that looks checked.
    if len(years) == 1:
        parent[f"{field}_year"] = years.pop()
    elif len(years) > 1 and dated is not None:
        parent[f"{field}_year"] = dated
    else:
        parent.pop(f"{field}_year", None)

    # A unit whose composition was just summed from a complete set of children
    # should carry their population too, when it has none, an older one, or one
    # of the same year from somewhere else.
    #
    # Bangladesh is the older case: two of its divisions publish no population
    # at all and six publish 2011 figures, so the level above was summing a
    # mixture of vintages -- six 2011 divisions and two 2022 ones -- and
    # comparing that mongrel against a 2025 estimate.
    #
    # Finland is the same-year case, and the reason the test is not a strict
    # one. Its nineteen regions total 5,652,881 for 2025 from Statistics
    # Finland's own register, and the country carried 5,550,449 for 2025 from
    # the Factbook: a hundred thousand people apart, an itemised count against
    # a general estimate, with the language shares already taken from the
    # register. Leaving the two side by side published a national population
    # that disagreed with the regions drawn inside it.
    #
    # A newer figure still wins, because a later estimate of a place is not
    # something an older count should overwrite. The figure replaced goes into
    # a note either way.
    # Nothing is rewritten when the two agree. Ladakh's Leh and Kargil sum to
    # exactly the 274,289 Wikidata gives it, and restamping that number as
    # "summed from 2 second-level divisions" would trade a named source for a
    # derivation and tell a reader less about the same figure.
    child_year = common_year(children)
    own_year = vintage(parent.get("population"))
    if unpriced or not total_pop:
        # Nothing to fill a population from: some child never published one,
        # so their total is a partial sum and stamping it on the parent would
        # publish a count of part of a place as the whole of it.
        return None
    own = published(parent.get("population"))
    if child_year and (own is None or (round(total_pop) != round(own)
                                       and (own_year is None
                                            or own_year <= child_year))):
        if own is not None:
            parent["population_note"] = (
                f"Summed from all {len(children)} {level} divisions. Replaces "
                f"a separately published {own:,.0f}"
                + (f" for {own_year}" if own_year else "")
                + ", which is kept here as the only independent check on this "
                  "sum.")
        parent["population"] = {"value": int(round(total_pop)),
                                "year": child_year,
                                "source": f"summed from {len(children)} "
                                          f"{level} divisions"}
    # Keyed on name *and* field, not name alone: one census appears in a record
    # several times under different fields, and Ladakh already carried this one
    # as the source of its "became a union territory in 2019" note. Deduplicating
    # by name dropped the entry that says where the religion figures came from,
    # which is the entry a reader would go looking for.
    seen = {(src.get("name"), src.get("field")) for src in parent.get("sources", [])}
    for child in children:
        for src in child.get("sources", []):
            mark = (src.get("name"), src.get("field"))
            if field in (src.get("field") or "") and mark not in seen:
                seen.add(mark)
                parent.setdefault("sources", []).append(dict(src))
    return None


def roll_up_countries(admin0: list[dict[str, Any]],
                      admin1_by_country: dict[str, list[dict[str, Any]]]) -> None:
    """Sum a country from its first-level divisions, where they are all there.

    Unlike the level below, this never fills a gap: every country record
    already carries a Factbook composition, so every sum here *replaces* a
    published figure. That is worth doing only because the two are not equally
    good. The children are usually a national statistical office's own count,
    itemised; the Factbook figure is an older estimate that lumps the tail into
    "other". Leaving them apart makes the map contradict itself between zoom
    levels -- Finland reads 85.9% Finnish nationally and 83.5% when you add up
    the nineteen regions drawn inside it.

    The displaced figure is written into the note rather than dropped, because
    it is the only independent statement about the country and the sum has
    nothing else to be checked against.

    ``COUNTRY_MIN_COVERAGE`` is the other thing particular to this level. One
    division short refuses the sum everywhere else, and rightly: a partial sum
    would look whole. Here the alternative to a partial sum is not a gap but
    the Factbook estimate staying put, so refusing is a choice between two
    imperfect figures rather than between a figure and silence. The United
    States is the case -- 51 divisions carrying PRRI's 2024 count and five
    territories carrying nothing, against a 2014 estimate of the whole -- and
    the reason it is safe to take is that the error is bounded by what was left
    out and the note says what that was.

    The population gate is the same 2% used below, and at this level it is
    doing something different: the parent's population comes from a current
    estimate and the children's from a census, so it refuses any country whose
    census is more than a couple of years stale -- Mexico by 3.6%, New Zealand
    by 3.2%, Nepal by 6.9%, Australia by 7.5%. Those are vintage gaps rather
    than faults, and widening the bound for them is a separate decision from
    this one; it is left tight here so that nothing is rewritten on a looser
    rule than the one that has been tested.
    """
    filled: list[str] = []
    refused: list[str] = []
    for country in admin0:
        iso3 = (country.get("codes") or {}).get("iso3") or country.get("id", "")[:3]
        if country.get("id") != iso3:
            continue
        children = admin1_by_country.get(iso3, [])
        if not children:
            continue
        for field in ROLLUP_FIELDS:
            before = country.get(field)
            # Every first-level division of the country is in `children`, and
            # the check above has already refused the field unless all of them
            # carry it, so these are certainly all of them. That is enough to
            # sum without child populations; it is not enough to overrule the
            # country's own published population, which stays gated at 2%.
            why = roll_up_field(country, children, field,
                                level="first-level", over_published=True,
                                complete=True,
                                min_coverage=COUNTRY_MIN_COVERAGE)
            if why:
                refused.append(f"{iso3}: {why}")
            elif country.get(field) is not before:
                filled.append(f"{iso3} {field}")
    if filled:
        log(f"  summed {len(filled)} country fields from their first-level "
            f"divisions: " + ", ".join(filled))
    for line in refused:
        log(f"  country not summed -- {line}")


def roll_up_parents(admin1_by_country: dict[str, list[dict[str, Any]]],
                    admin2_by_country: dict[str, list[dict[str, Any]]]) -> None:
    """Fill what can be summed, and say what could not be."""
    filled: list[str] = []
    refused: list[str] = []
    for iso3, parents in sorted(admin1_by_country.items()):
        kids: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for entity in admin2_by_country.get(iso3, []):
            kids[entity.get("parent")].append(entity)
        everywhere = {
            field: bool(admin2_by_country.get(iso3))
            and all(isinstance(e.get(field), list)
                    for e in admin2_by_country[iso3])
            for field in ROLLUP_FIELDS}
        for parent in parents:
            children = kids.get(parent["id"], [])
            for field in ROLLUP_FIELDS:
                before = parent.get(field)
                why = roll_up_field(parent, children, field,
                                    whole_country=everywhere[field])
                if why:
                    refused.append(f"{iso3} {parent['name']}: {why}")
                elif parent.get(field) is not before:
                    filled.append(f"{iso3} {parent['name']} {field}")
    if filled:
        log(f"  summed {len(filled)} admin1 fields from their children: "
            + ", ".join(filled[:8]) + (" ..." if len(filled) > 8 else ""))
    for line in refused:
        log(f"  not summed -- {line}")


# What identifies or locates a row rather than describing its people. Two rows
# differing only here may still be one place written twice; two rows differing
# anywhere else are carrying different claims about the population, whatever
# their names say. Wikidata gives every item its own Q-id, so counting that as
# a difference would make every rivalry look like a conflict.
#
# iso_3166_2 was added here and does not belong. A Q-id is unique per item,
# which is why it is excluded; an ISO 3166-2 code is the opposite -- it is
# shared and standard, so two rows holding *different* codes are two different
# official units by definition, and that is the strongest evidence this
# function can be given. Excluding it deleted exactly that evidence, and the
# duplicate-listing exemption below then handed one shape to whichever rival
# came last. Lithuania's Alytus County took the 25,356 people of "Alytus
# District Municipality" (LT-03 on Wikidata, though LT-03 is the county) in
# place of its own hundred and forty thousand, and Laos' Vientiane took
# Vientiane Province's 388,833 over the prefecture's. Both had been honest
# gaps: the collision pass had refused both rivals because nothing separated
# them, which is the trade this file exists to make.
METADATA = {"id", "wikidata", "level", "name", "parent", "parent_name",
            "parent_aliases", "aliases", "no_shape", "_source", "sources",
            "country", "point", "coordinates", "bbox", "match"}


def conflicting(rows: list[dict[str, Any]]) -> list[str]:
    """Fields on which these rows publish different real values.

    A gap is not a difference: one row saying "not available" where another
    gives a figure is what merge_adapter exists for, and the figure survives
    either order.
    """
    out = []
    for field in sorted({k for row in rows for k in row} - METADATA):
        real = [v for v in (row.get(field) for row in rows)
                if v is not None and not is_gap(v)]
        if len(real) > 1 and any(v != real[0] for v in real[1:]):
            out.append(field)
    return out


EXACT = 3


def evidence(how: str) -> int:
    """How much a match is worth when two rows want the same shape.

    A name that matched outright beats one that matched by a fragment of
    itself, and a match confined to the state the row named beats one that
    searched the whole country. Rotherham's own row says "Rotherham"; Rother's
    says "Rother" and reaches the same shape through the prefix pass, so the
    exact one is the one to keep.
    """
    base = how.split("+")[0]
    if base in ("name", "alias"):
        return EXACT
    return 2 if "+" in how else 1


def resolve_collisions(matched: list[tuple[dict[str, Any], dict[str, Any], str]]
                       ) -> tuple[set[int], list[str]]:
    """Refuse rows of one file that all landed on the same shape.

    Nothing stopped several rows of one adapter from matching one boundary, and
    whichever came last silently overwrote the rest: England's East, Mid, North
    and West Devon all reached a shape called Devon, so Devon wore West Devon's
    figures and the other three vanished. Texas's Jackson County reached a shape
    called Jack. 1,324 rows were being lost this way.

    What does *not* decide it is which rival is named exactly as the shape is.
    That test settles a tie between two shapes -- see settle(), where
    "Cotabato" picks the province over "Cotabato City" -- and inverts when the
    tie is between two rows. Boundary files drop the generic word by
    convention: CGAZ's Argentine ADM2 *is* the departments and calls them
    "Andalgalá", so the exactly-named rival is the town of 3,300 and the one
    that says "Andalgalá Department" is the unit the shape draws. Applying it
    here would have installed 104 confident mis-matches in place of 108 honest
    gaps, which is a worse trade in exactly the direction this file exists to
    avoid.

    Where one row's evidence beats every other's the shape is its own and the
    rest are refused -- "Rotherham" over "Rother", "Ostrobothnia" over "Central
    Ostrobothnia". Where nothing separates them, none of them may claim it:
    four Devons and no way to tell which is the shape's is exactly the case for
    a visible gap rather than an invisible guess.

    Rows that all matched *outright* are left alone, because there the rivalry
    is usually a source listing one place twice. Wikidata carries both "Ancasti"
    and "Ancasti Department", and "Department" is a word this code drops, so
    both are the same name reaching the same shape; refusing them would lose
    Ancasti to a duplicate rather than to a mistake. Last one still wins there.

    That held only as long as nobody asked whether the duplicates agreed. 113
    shapes had rivals publishing *different* figures under the exemption --
    Kyiv against Kyiv Oblast, Morogoro city against the region 150 km around
    it, Tashkent against Tashkent Region -- because the words this code drops
    include "Region", "Oblast" and "City", so a capital and its region reach
    one key exactly as a duplicate listing does. The names cannot separate
    those two cases. The figures can: one place written twice says the same
    thing twice, and rows that contradict each other are not one place. So the
    exemption now requires agreement, and a disagreement is ranked on evidence
    or refused like any other rivalry.
    """
    # Keyed by level as well as id: 334 polygons are drawn at both levels
    # under one id, and a source that binds both -- Moldova's Bender, once at
    # each level -- is two rows on two shapes, not two rows fighting over one.
    # Keyed by id alone they tied on evidence and both were refused.
    claims: dict[tuple[Any, Any, str], list[int]] = defaultdict(list)
    for i, (row, entity, _) in enumerate(matched):
        claims[(row.get("_source"), entity.get("level"), entity["id"])].append(i)

    dropped: set[int] = set()
    notes: list[str] = []
    for (_, _level, _eid), idxs in claims.items():
        if len(idxs) < 2:
            continue
        ranked = sorted(idxs, key=lambda i: -evidence(matched[i][2]))
        best, runner = evidence(matched[ranked[0]][2]), evidence(matched[ranked[1]][2])
        # Two outright matches are one place listed twice only if they agree.
        # Where they publish different figures they are two places, and the
        # exemption below would hand the shape to whichever came last: Kyiv's
        # 2.95 million on Kyiv Oblast, or Morogoro city's on the region 150 km
        # around it. norm() drops "Region", "Oblast", "City" and "Department"
        # alike, so the names cannot tell a duplicate listing from a capital
        # and its region -- but the figures can, and a row that contradicts its
        # rival is evidence enough to stop treating them as one.
        if best == EXACT and not conflicting([matched[i][0] for i in idxs]):
            # A name that matched outright owns the shape; anything that got
            # there through a fragment of itself does not. Several outright
            # matches are a duplicated source row, not a rivalry.
            losers = [i for i in idxs if evidence(matched[i][2]) < EXACT]
            kept = matched[ranked[0]][0].get("name")
        else:
            losers = ranked[1:] if best > runner else ranked
            kept = matched[ranked[0]][0].get("name") if best > runner else None
        if not losers:
            continue
        dropped.update(losers)
        shape = matched[idxs[0]][1]["name"]
        names = ", ".join(str(matched[i][0].get("name"))[:24] for i in losers[:4])
        notes.append(f"{shape!r}: refused {names}" +
                     (f" (kept {kept!r})" if kept else " (nothing to separate them)"))
    return dropped, notes


DISPUTED_NOTE = ("Disputed or special-status territory as delimited by geoBoundaries "
                 "CGAZ, which follows US Department of State definitions. Shown for "
                 "completeness; no sovereignty claim is implied and no demographic "
                 "source is joined to it.")


def mark_disputed_or_hint(entity: dict[str, Any], group: str) -> None:
    """Either flag the unit as disputed, or tell the UI which adapter would fill it.

    A disputed polygon gets no adapter hint: no statistical agency publishes
    demographics for it, so pointing at one would be a false promise.
    """
    partial = PARTIAL_LEVELS.get((group, entity.get("level")))
    if partial and not is_disputed(group):
        # Before the branch below and outside it: this says why the *level*
        # looks the way it does, which is a different question from why this
        # unit is empty, and the unit still wants its adapter hint. A reader
        # who has just watched two thirds of Uruguay render as sea is owed the
        # first answer whether or not there is data in the panel.
        entity["note"] = partial["note"]

    if is_disputed(group):
        entity["disputed"] = True
        entity["note"] = DISPUTED_NOTE
    elif entity.get("name") in SHAPE_GAPS.get(group, {}):
        # Before the country-level cases, because this is the more specific
        # fact: the adapter ran, and this one polygon still cannot be given
        # what it found. An adapter hint here would tell the reader to run a
        # script that has already run and deliberately skipped this shape.
        entity["gap_reason"] = SHAPE_GAPS[group][entity["name"]]
    elif group in ADAPTER_GAPS:
        # Not a hint: naming a script here would say the gap is this build's
        # doing, when it belongs to what the country publishes.
        entity["gap_reason"] = ADAPTER_GAPS[group]
    else:
        entity["adapter_hint"] = adapter_hint(group)


COMPOSITION_FIELDS = ("religion", "language", "ethnicity")

# The three ways a composition field can still be bare at the end of the
# pipeline, in the words the panel prints. Each says what is true and stops
# there: none of them claims the census does not ask, because none of them
# knows. The first is the one this pass exists for.
NO_SOURCE_READ = (
    "No unit-level source has been read for {country} at this level, so "
    "nothing has been fetched for this field. That is a gap in this map's "
    "reading, not a claim about what the census asks or publishes.")
SOURCE_LACKS_FIELD = (
    "The source read for this unit -- {sources} -- carries {present} and "
    "not {field}. Nothing has been fetched for it here, which is a limit of "
    "what was read and not a statement that the census does not ask.")
SOURCE_LACKS_ALL = (
    "The source read for this unit -- {sources} -- carries no composition "
    "for any of religion, language or ethnicity. Nothing has been fetched "
    "for this field, which is a limit of what was read and not a statement "
    "that the census does not ask.")
UNMATCHED_UNIT = (
    "A unit-level source was read for {country} at this level -- {sources} -- "
    "and {matched} of its {units} units were joined to it. This unit matched "
    "no row in that source, so whatever it publishes here has not been "
    "reached. That is a gap in this map's joining, not a claim about what the "
    "census asks or publishes.")


def joined_here(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """What a source reached at this level, for the units it did not reach.

    An unmatched unit sits beside units that matched, and the two need
    different sentences. Counting the siblings once per country is what lets
    say_why_empty tell them apart, and the counts go into the note so a reader
    can see the shape of the failure rather than take the word "gap" on trust.
    """
    live = [r for r in rows if not r.get("disputed")]
    matched = [r for r in live if r.get("match")]
    names = sorted({s.get("name") for r in matched
                    for s in r.get("sources", []) if s.get("name")})
    return {"sources": ", ".join(names) or "an unnamed source",
            "matched": len(matched), "units": len(live)}


def say_why_empty(entity: dict[str, Any], country: str,
                  joined: dict[str, Any] | None = None) -> str | None:
    """Give every bare composition field the true reason it is bare.

    A field left as ``{"status": "not_available"}`` with no note reads, on the
    map, as a blank panel -- and a blank panel says "nobody ran the adapter",
    which is a different claim from any of the true ones. This is the last
    pass before the files are written, so it sees only what every earlier
    stage left untouched: the adapters, the collection policy, the parent
    sums. It never overwrites a note, a composition, or a status it did not
    find bare.

    Returns which case applied, for the build log to count, or None.
    """
    case = None
    for field in COMPOSITION_FIELDS:
        value = entity.get(field)
        if not (isinstance(value, dict) and value.get("status")
                and not value.get("note")):
            continue
        if entity.get("disputed"):
            note, case = DISPUTED_NOTE, "disputed"
        elif entity.get("gap_reason"):
            # The country-level fact already on the record: what the country
            # publishes. True of the field, so it is the field's reason too.
            note, case = entity["gap_reason"], "country publishes nothing"
        elif entity.get("match"):
            sources = sorted({s.get("name") for s in entity.get("sources", [])
                              if s.get("name")}) or ["an unnamed source"]
            present = [f for f in COMPOSITION_FIELDS
                       if isinstance(entity.get(f), list)]
            if present:
                note = SOURCE_LACKS_FIELD.format(
                    sources=", ".join(sources), field=field,
                    present=" and ".join(present))
                case = "source lacks the field"
            else:
                note = SOURCE_LACKS_ALL.format(sources=", ".join(sources))
                case = "source carries no composition"
        elif joined and joined["matched"]:
            # The unit is bare because the join missed it, not because nobody
            # read anything: 27 of Bulgaria's 28 oblasts carry Wikidata and
            # Sofia does not, because "Sofia Oblast" could reach neither
            # "Sofia" nor "Sofia City" without reaching both. Saying "no
            # source has been read for Bulgaria" there is false, and false in
            # the direction that hides the bug -- it blames the absence of a
            # source for what is an unmatched row.
            note = UNMATCHED_UNIT.format(country=country, **joined)
            case = "unit matched no row"
        else:
            note, case = NO_SOURCE_READ.format(country=country), "no source read"
        entity[field] = gap(value["status"], note)
    return case


def check_shape_gaps(admin1: dict[str, list[dict[str, Any]]],
                     admin2: dict[str, list[dict[str, Any]]]) -> None:
    """Every declared shape gap names a shape that really is empty.

    The table is a promise about the boundary file, and boundary files change.
    A shape that gets renamed leaves an entry matching nothing, and a shape
    whose label gets corrected upstream would keep a sentence saying its
    figures cannot be trusted while quietly wearing them -- which is worse
    than the gap it was written to explain.

    So both directions are checked: an entry that matches no shape is stale,
    and an entry whose shape ended up with a composition is wrong. Either
    stops the build, because a declaration nobody checks is a comment.
    """
    problems: list[str] = []
    for iso3, declared in SHAPE_GAPS.items():
        seen = {name: [] for name in declared}
        for table in (admin1, admin2):
            for entity in table.get(iso3, []):
                if entity.get("name") in seen:
                    seen[entity["name"]].append(entity)
        for name, found in seen.items():
            if not found:
                problems.append(
                    f"{iso3} / {name}: declared a shape gap, but no shape of "
                    f"that name is drawn -- the boundary file has changed and "
                    f"the reason now explains nothing")
                continue
            filled = [e for e in found
                      if any(isinstance(e.get(f), list) and e[f]
                             for f in ("religion", "language", "ethnicity"))]
            if filled:
                problems.append(
                    f"{iso3} / {name}: declared a shape gap, but {len(filled)} "
                    f"of {len(found)} shape(s) of that name carry a "
                    f"composition -- either the join was fixed and this entry "
                    f"should go, or figures are landing on a shape this table "
                    f"says they must not")
    if problems:
        raise SystemExit(
            "build_entities: the shape-gap table does not match the shapes "
            "actually drawn, so nothing is being written:\n  - "
            + "\n  - ".join(problems))



# ---------------------------------------------------------------------------
# Derived values: what follows from published figures without reading more
# ---------------------------------------------------------------------------
#
# docs/MODELLING.md measures what modelling the blank regions could and could
# not do, and this is the part it recommends building: the cases that are
# arithmetic or geometry, where the assumption is about shapes and not about
# people. Everything written here is an estimate in common.py's sense -- a gap
# that carries a guess -- and so is invisible to every pass that wants a real
# value: the choropleth, the parent sums, the group index, the filter counts.
# The one exception is a pooled union, which is a sum of published rows and is
# written the way roll_up_field writes a sum.

# A shape the boundary file draws once where a source publishes it in parts.
# Namibia split Kavango into East and West in 2013 and CGAZ still draws one
# Kavango; Afrobarometer surveys each half and Wikidata counts each. Pooled,
# the parts describe the shape exactly. Pooling is done within one source file
# at a time, so a survey's respondents are never added to a census's people.
SHAPE_IS_UNION_OF: dict[tuple[str, str], tuple[str, ...]] = {
    ("NAM", "Kavango"): ("Kavango East", "Kavango West"),
    ("GRD", "Southern Grenadine Islands"): ("Carriacou Island", "Petite Martinique"),
}

# A source row that covers ground the boundary file has since divided. Bueng
# Kan was carved from Nong Khai in 2011; the 2000 census row for Nong Khai
# counted both. Giving the new unit the old row's shares assumes the parent
# was uniform inside, which docs/MODELLING.md measures to be false in about
# 45% of countries -- so the copy is an estimate, says so on its face, and the
# row's own shape keeps the published row untouched.
ROW_COVERS_SHAPES: dict[tuple[str, str], tuple[str, ...]] = {
    ("THA", "Nong Khai Province"): ("Bueng Kan Province",),
}

# How far a residual's people may differ from the unit's published population
# before the subtraction is refused as describing something else.
RESIDUAL_TOLERANCE = 0.03


def whole_hundred(shares: Sequence[tuple[str, float]]) -> list[dict[str, Any]]:
    """Shares to one decimal that sum to exactly 100.0, by largest remainder."""
    total = sum(max(v, 0.0) for _, v in shares)
    if total <= 0:
        return []
    tenths = [(g, max(v, 0.0) / total * 1000) for g, v in shares]
    floors = [int(v) for _, v in tenths]
    order = sorted(range(len(tenths)), key=lambda i: -(tenths[i][1] - floors[i]))
    for i in order[:1000 - sum(floors)]:
        floors[i] += 1
    return [{"group": g, "pct": floors[i] / 10} for i, (g, _) in enumerate(tenths)]


def shares_of(rows: Any) -> list[tuple[str, float]]:
    """(group, pct) for every entry that carries both."""
    return [(e["group"], float(e["pct"])) for e in (rows or [])
            if isinstance(e, dict) and e.get("group")
            and isinstance(e.get("pct"), (int, float))]


def pool_rows(name: str, parts: Sequence[dict[str, Any]], iso3: str,
              filename: str) -> dict[str, Any]:
    """One row for a shape, from the rows a source publishes for its parts.

    Counts are summed where every part carries them; otherwise the shares are
    weighted by the parts' populations; otherwise the field is left out and
    the log says so. A survey's counts are respondents and a census's are
    people, and both pool correctly because the parts come from one file.
    """
    pooled: dict[str, Any] = {
        "id": f"{iso3}-POOL-{norm(name)}-{norm(filename)}",
        "level": parts[0].get("level") or "admin1", "name": name,
        "parent": parts[0].get("parent") or iso3, "country": iso3,
        "_source": filename, "sources": []}
    seen: set[tuple[Any, ...]] = set()
    for part in parts:
        for src in part.get("sources", []) or []:
            key = (src.get("name"), src.get("url"), src.get("field"))
            if key not in seen:
                seen.add(key)
                pooled["sources"].append(src)
    pops = [published(p.get("population")) for p in parts]
    if all(v is not None for v in pops):
        first = dict(parts[0]["population"])
        first["value"] = int(round(sum(v for v in pops if v is not None)))
        years = {vintage(p.get("population")) for p in parts}
        if len(years) != 1:
            first.pop("year", None)
        pooled["population"] = first
    names = " and ".join(p["name"] for p in parts)
    for field in ROLLUP_FIELDS:
        lists = [p.get(field) for p in parts]
        if not all(isinstance(v, list) and shares_of(v) for v in lists):
            continue
        totals: dict[str, float] = defaultdict(float)
        counted = all(all(isinstance(e.get("count"), (int, float)) for e in v)
                      for v in lists)
        if counted:
            for v in lists:
                for e in v:
                    totals[e["group"]] += float(e["count"])
            whole = sum(totals.values())
            if whole <= 0:
                continue
            rows = whole_hundred([(g, c / whole * 100) for g, c in totals.items()])
            for row in rows:
                row["count"] = int(round(totals[row["group"]]))
            basis = "their published counts"
        elif all(v is not None for v in pops):
            for v, w in zip(lists, pops):
                for g, pct in shares_of(v):
                    totals[g] += pct * (w or 0.0)
            whole = sum(v for v in pops if v is not None)
            if whole <= 0:
                continue
            rows = whole_hundred([(g, c / whole) for g, c in totals.items()])
            basis = "their populations"
        else:
            log(f"  union {iso3} {name}: {field} not pooled from {filename} -- "
                f"the parts carry neither counts nor populations to weigh by")
            continue
        pooled[field] = rows
        pooled[f"{field}_note"] = (
            f"Pooled from the rows published for {names}, weighted by {basis}; "
            f"the boundary file draws them as one unit.")
        for satellite in ("year", "basis"):
            values = {p.get(f"{field}_{satellite}") for p in parts}
            if len(values) == 1 and None not in values:
                pooled[f"{field}_{satellite}"] = values.pop()
    return pooled


def pool_declared_unions(adapters: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Replace each declared union's parts with one row named for the shape."""
    done: list[str] = []
    for (iso3, shape_name), part_names in SHAPE_IS_UNION_OF.items():
        rows = adapters.get(iso3, [])
        # Matched the way the shapes are: Afrobarometer writes "Kavango East"
        # and Wikidata "Kavango East Region", and norm() reads those alike.
        wanted = {norm(p): p for p in part_names}
        by_file: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for row in rows:
            part = wanted.get(norm(row.get("name")))
            if part and part not in by_file[row["_source"]]:
                by_file[row["_source"]][part] = row
        if not by_file:
            log(f"  union {iso3} {shape_name}: no source publishes any of "
                + ", ".join(part_names))
        for filename, found in sorted(by_file.items()):
            missing = [p for p in part_names if p not in found]
            if missing:
                log(f"  union {iso3} {shape_name}: {filename} lacks "
                    f"{', '.join(missing)}, not pooled")
                continue
            pooled = pool_rows(shape_name, [found[p] for p in part_names], iso3, filename)
            for p in part_names:
                rows.remove(found[p])
            rows.append(pooled)
            done.append(f"{iso3} {shape_name} from {' + '.join(part_names)} ({filename})")
    return done


def estimate_from(src: dict[str, Any], target: str, iso3: str) -> dict[str, Any] | None:
    """A row for ``target`` carrying ``src``'s compositions as estimates."""
    copy: dict[str, Any] = {
        "id": f"{src.get('id') or norm(src['name'])}-SPLIT-{norm(target)}",
        "level": src.get("level") or "admin1", "name": target,
        "parent": src.get("parent") or iso3, "country": iso3,
        "_source": src["_source"], "sources": list(src.get("sources", []) or [])}
    written = False
    for field in ROLLUP_FIELDS:
        shares = src.get(field)
        if not (isinstance(shares, list) and shares_of(shares)):
            continue
        if collection_gap(iso3, field) is not None:
            log(f"  split {iso3} {src['name']} -> {target}: {field} is declared "
                f"not collected, no estimate written")
            continue
        year = src.get(f"{field}_year")
        when = f" in {year}" if year else ""
        copy[field] = estimate(
            MODELLED, shares, method="tier1-split",
            inputs=[src.get("id") or src["name"]],
            note=(f"No source has been read for {target}. This is the {field} "
                  f"composition published for {src['name']}{when}, which then "
                  f"included this ground, applied here on the assumption that the "
                  f"old unit was uniform inside. It is an estimate, not a published "
                  f"figure, and not evidence of what the census says about {target}."))
        written = True
    return copy if written else None


def split_declared_rows(adapters: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Add a row, as estimates, for each shape a declared source row covers."""
    done: list[str] = []
    for (iso3, row_name), targets in ROW_COVERS_SHAPES.items():
        rows = adapters.get(iso3, [])
        sources = [r for r in rows if r.get("name") == row_name]
        if not sources:
            log(f"  split {iso3} {row_name}: no source publishes it")
            continue
        for src in sources:
            have = {r.get("name") for r in rows if r["_source"] == src["_source"]}
            for target in targets:
                if target in have:
                    log(f"  split {iso3} {row_name} -> {target}: {src['_source']} "
                        f"publishes {target} itself, not copied")
                    continue
                copy = estimate_from(src, target, iso3)
                if copy is None:
                    log(f"  split {iso3} {row_name} -> {target}: {src['_source']} "
                        f"carries nothing to copy")
                    continue
                rows.append(copy)
                done.append(f"{iso3} {target} from {row_name} ({src['_source']}): "
                            + ", ".join(f for f in ROLLUP_FIELDS if f in copy))
    return done


def inherit_single_unit(admin0: list[dict[str, Any]],
                        admin1_by_country: dict[str, list[dict[str, Any]]]) -> list[str]:
    """A country drawn as one first-level unit gives that unit its own row.

    The unit's ground is the country's, so the national figure describes it
    exactly. Written as derived rather than as a reading, because nothing was
    read for the unit and a derived value never rolls back up into the
    country it came from.
    """
    done: list[str] = []
    nations = {c["id"]: c for c in admin0}
    for iso3, rows in sorted(admin1_by_country.items()):
        if len(rows) != 1 or rows[0].get("disputed"):
            continue
        unit, nation = rows[0], nations.get(iso3)
        if nation is None:
            continue
        for field in ROLLUP_FIELDS:
            shares, current = nation.get(field), unit.get(field)
            if not (isinstance(shares, list) and shares_of(shares)):
                continue
            if not (isinstance(current, dict) and current.get("status") == NOT_AVAILABLE):
                continue
            unit[field] = estimate(
                DERIVED, shares, method="tier0-single-unit", inputs=[iso3],
                note=(f"{nation.get('name', iso3)} is drawn as a single first-level "
                      f"unit, so this is the country's own {field} figure: it "
                      f"describes exactly this ground and no more. Derived from the "
                      f"national row, not separately published for the unit."))
            done.append(f"{iso3} {unit['name']} {field}")
    return done


# A source name ends with how this map reached it, which is provenance rather
# than identity. The Wikipedia readers append ", as the bg.wikipedia article
# 'X (област)' transcribes it", and a province and its municipalities each name
# their own article -- so two rows off one census read as two sources and every
# subtraction between them was refused. 53 of the 103 refusals on the build of
# 21 September 2026 were this and nothing else, Bulgaria's whole second level
# among them. The clause is cut before the comparison: what is left is the
# office and the publication, which is what "the same source" means.
TRANSCRIPTION = ", as the "


def source_identity(name: str) -> str:
    return name.split(TRANSCRIPTION, 1)[0].strip()


def source_names(entity: dict[str, Any], field: str) -> set[str]:
    return {source_identity(str(s.get("name"))) for s in entity.get("sources", []) or []
            if s.get("name") and field in str(s.get("field") or "").split("/")}


def residual(nation: dict[str, Any], known: list[dict[str, Any]],
             target: dict[str, Any], field: str
             ) -> tuple[str | None, list[dict[str, Any]] | None]:
    """The one missing unit's composition by subtraction, or why not.

    Each refusal is a way the subtraction would describe something other than
    the unit. Different sources: the national figure and the units' were
    counted by different people, so their difference is mostly the
    disagreement between them. Populations that do not add up: the same, with
    the arithmetic visible. Labels the national figure lacks: the units are
    answering a finer question, and a group the parent never named cannot be
    subtracted from it. A negative share: the inputs contradict each other. A
    residual whose people do not match the unit's own: whatever is left over,
    it is not this unit.
    """
    own = source_names(nation, field)
    theirs: set[str] = set().union(*(source_names(r, field) for r in known))
    if not own or not theirs or not (own & theirs):
        return (f"the national figure ({', '.join(sorted(own)) or 'no named source'}) "
                f"and the units' ({', '.join(sorted(theirs)) or 'no named source'}) "
                f"come from different sources; a difference between them is not a unit",
                None)
    nat_pop = published(nation.get("population"))
    pops = {r["id"]: published(r.get("population")) for r in [*known, target]}
    if nat_pop is None or any(v is None for v in pops.values()):
        return "not every unit and the country has a published population to weigh by", None
    total = sum(v for v in pops.values() if v is not None)
    if abs(total - nat_pop) > RESIDUAL_TOLERANCE * nat_pop:
        return (f"the units' populations sum to {total:,.0f} against a national "
                f"{nat_pop:,.0f}", None)
    labels = {g for g, _ in shares_of(nation.get(field))}
    foreign = {g for r in known for g, _ in shares_of(r[field])} - labels
    if foreign:
        return (f"the units name groups the national figure does not "
                f"({', '.join(sorted(foreign)[:4])})", None)
    counts = {g: pct / 100 * nat_pop for g, pct in shares_of(nation.get(field))}
    for r in known:
        for g, pct in shares_of(r[field]):
            counts[g] -= pct / 100 * (pops[r["id"]] or 0.0)
    own_pop = pops[target["id"]] or 0.0
    negative = [g for g, c in counts.items() if c < -RESIDUAL_TOLERANCE * own_pop]
    if negative:
        return f"the subtraction goes negative for {', '.join(sorted(negative)[:4])}", None
    left = sum(max(c, 0.0) for c in counts.values())
    if own_pop <= 0 or abs(left - own_pop) > RESIDUAL_TOLERANCE * own_pop:
        return (f"the residual is {left:,.0f} people against the unit's published "
                f"{own_pop:,.0f}", None)
    return None, whole_hundred([(g, c / left * 100) for g, c in counts.items()])


def residual_child(admin0: list[dict[str, Any]],
                   admin1_by_country: dict[str, list[dict[str, Any]]]
                   ) -> tuple[list[str], list[str]]:
    """Fill the one unit a country's own arithmetic determines, or say why not."""
    filled: list[str] = []
    refused: list[str] = []
    nations = {c["id"]: c for c in admin0}
    for iso3, rows in sorted(admin1_by_country.items()):
        nation = nations.get(iso3)
        if nation is None or len(rows) < 2 or any(r.get("disputed") for r in rows):
            continue
        for field in ROLLUP_FIELDS:
            if not (isinstance(nation.get(field), list) and shares_of(nation[field])):
                continue
            blank = [r for r in rows if isinstance(r.get(field), dict)
                     and r[field].get("status") == NOT_AVAILABLE]
            known = [r for r in rows if isinstance(r.get(field), list)]
            if len(blank) != 1 or len(known) != len(rows) - 1:
                continue
            target = blank[0]
            where = f"{iso3} {target['name']} {field}"
            why, shares = residual(nation, known, target, field)
            if why or not shares:
                refused.append(f"{where}: {why or 'nothing left over'}")
                continue
            target[field] = estimate(
                DERIVED, shares, method="tier0-residual",
                inputs=[iso3, *(r["id"] for r in known)],
                note=(f"No source has been read for {target['name']}. The national "
                      f"{field} figure and every other first-level unit's come from "
                      f"the same source and their populations agree, so this is the "
                      f"difference: the national count less the other units', share "
                      f"by share. Derived by subtraction, not separately published."))
            filled.append(where)
    return filled, refused


def residual_grandchild(admin1_by_country: dict[str, list[dict[str, Any]]],
                        admin2_by_country: dict[str, list[dict[str, Any]]]
                        ) -> tuple[list[str], list[str]]:
    """The same subtraction one level down: a parent unit and its districts.

    residual_child fills the one first-level unit a country's own arithmetic
    determines. This fills the one *district* a first-level unit determines,
    and it is the answer to a question the second level kept raising: a
    province carries a language composition, all but one of its districts
    carry one too, and that last district reads as unmeasured when in fact the
    province's own figure and its siblings' fix it exactly.

    It reuses residual() unchanged, which is worth saying because that
    function's refusals are the reason this is safe to run at all. It will not
    subtract across two sources, or where the children's populations do not
    add to the parent's, or where a child names a group the parent never did,
    or where the answer comes out negative, or where the people left over do
    not match the district's own published population. Every one of those is a
    way the difference would describe something other than the district.

    What this deliberately does NOT do is the many-unknowns case. Where two or
    more districts are empty their shares are not determined -- the province
    fixes only their sum -- and the obvious move, giving each of them the
    province's own composition, would assert that every district speaks like
    its province. For language that is close to the opposite of true, and it
    is the reason a province-level figure is worth less than a district-level
    one in the first place. Those districts keep their stated gap.
    """
    filled: list[str] = []
    refused: list[str] = []
    for iso3, parents in sorted(admin1_by_country.items()):
        kids: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        for entity in admin2_by_country.get(iso3, []):
            kids[entity.get("parent")].append(entity)
        for parent in parents:
            rows = kids.get(parent["id"], [])
            if len(rows) < 2 or parent.get("disputed") \
                    or any(r.get("disputed") for r in rows):
                continue
            for field in ROLLUP_FIELDS:
                if not (isinstance(parent.get(field), list)
                        and shares_of(parent[field])):
                    continue
                blank = [r for r in rows if isinstance(r.get(field), dict)
                         and r[field].get("status") == NOT_AVAILABLE]
                known = [r for r in rows if isinstance(r.get(field), list)]
                if len(blank) != 1 or len(known) != len(rows) - 1:
                    continue
                target = blank[0]
                where = f"{iso3} {target['name']} {field}"
                why, shares = residual(parent, known, target, field)
                if why or not shares:
                    refused.append(f"{where}: {why or 'nothing left over'}")
                    continue
                target[field] = estimate(
                    DERIVED, shares, method="tier0-residual",
                    inputs=[parent["id"], *(r["id"] for r in known)],
                    note=(f"No source has been read for {target['name']}. "
                          f"{parent.get('name') or 'Its parent'}'s {field} figure "
                          f"and every other district's come from the same source "
                          f"and their populations agree, so this is the "
                          f"difference: the parent's count less the other "
                          f"districts', share by share. Derived by subtraction, "
                          f"not separately published."))
                filled.append(where)
    return filled, refused


def check_no_estimate_on_policy_field(*tables: dict[str, list[dict[str, Any]]]) -> None:
    """An estimate on a field the country does not count is fatal.

    It would not fill a gap in what this map has read; it would manufacture a
    statistic about a category the state declined to enumerate. Every pass
    that writes an estimate checks the policy first, and this checks them.
    """
    bad = [f"{iso3} {entity.get('name')} {field}"
           for table in tables for iso3, rows in table.items() for entity in rows
           for field in ROLLUP_FIELDS
           if is_estimate(entity.get(field)) and collection_gap(iso3, field) is not None]
    if bad:
        raise SystemExit("estimates were written on fields the country does not "
                         "collect: " + ", ".join(bad[:10]))


def check_no_stale_country_declaration(
        admin0: list[dict[str, Any]],
        admin1_by_country: dict[str, list[dict[str, Any]]]) -> None:
    """A country saying "never collected" while its divisions carry figures.

    ``data/processed/admin0.json`` is a stored file, written by
    ``fetch_factbook.py`` from ``NOT_COLLECTED_POLICY`` at the time it ran. The
    policy table is code and changes with a commit; the file only changes when
    the adapter is re-run. When a country leaves the table -- as Japan and
    South Korea did on 19 September 2026, so that their divisions could carry
    nationality as a census composition -- the file keeps the old declaration,
    and nothing downstream notices: ``roll_up_field`` honours a
    ``not_collected`` by design, and returns ``None`` without logging, because
    a state's own statement is not a gap to be summed over.

    The effect is a map that contradicts itself between zoom levels and says
    the false half loudest: every Japanese prefecture carrying a composition,
    and Japan painted "not collected" at the zoom a reader opens on. That is
    what this refuses. The rule is narrow on purpose -- only a country whose
    own first-level divisions carry a real composition for the field, which is
    the contradiction itself and nothing else. A country that declines to ask
    and has no division carrying an answer is untouched, and so is an
    uninhabited dependency whose divisions carry nothing.

    The fix is always to re-run the adapter that wrote the file:
    ``python -m scripts.fetch_factbook``.
    """
    bad: list[str] = []
    for country in admin0:
        iso3 = (country.get("codes") or {}).get("iso3") or country.get("id", "")
        if country.get("id") != iso3:
            continue
        for field in ROLLUP_FIELDS:
            value = country.get(field)
            if not (isinstance(value, dict)
                    and value.get("status") == NOT_COLLECTED):
                continue
            if collection_gap(iso3, field) is not None:
                continue                      # the policy still says so
            carried = sum(1 for child in admin1_by_country.get(iso3, [])
                          if isinstance(child.get(field), list))
            if carried:
                bad.append(f"{iso3} {field} ({carried} divisions carry one)")
    if bad:
        raise SystemExit(
            "data/processed/admin0.json declares a field not collected that "
            "the policy table no longer declares, while the country's own "
            "divisions carry a composition for it: " + ", ".join(bad[:10])
            + ". The stored country file is stale -- re-run "
              "python -m scripts.fetch_factbook.")


def add_known_as(index: dict[str, list[dict[str, Any]]],
                 entities: Sequence[dict[str, Any]]) -> int:
    """Index each shape's declared alternative names, under two rules.

    A real name always wins. An alias is only ever added to a key no shape's
    own name has claimed, so declaring one can never make a working join
    ambiguous and take a filled unit away -- the table can add a match, never
    remove one.

    And an alias claimed by two shapes stays ambiguous, because the index
    keeps every claimant and the matcher refuses a key with more than one.
    Guessing between them is the failure this whole table exists to avoid.
    """
    own = {norm(e["name"]) for e in entities}
    added = 0
    for entity in entities:
        for alias in known_as(entity["name"], entity.get("country")):
            key = norm(alias)
            if key and key not in own and entity not in index[key]:
                index[key].append(entity)
                added += 1
    return added


# Wikidata rows placed on a polygon by declaration, because the boundary file
# labels the polygon in a way no name can undo.
#
# Belarus draws Minsk Region and Minsk the city as two shapes and calls the
# region plain "Minsk". norm() drops "Region" and "City", so all three names
# -- "Minsk", "Minsk City", "Minsk region" -- are one key, and the tiebreak on
# an identical name gave Wikidata's row for the *city* (Q2280) to the shape
# labelled "Minsk", which is the region: 66,000 km^2 of oblast wearing the
# capital's 1,995,091 people, with nothing on the map to say so. The region's
# own row found no shape at all.
#
# The general rule that would have fixed it was measured and rejected. Of the
# fifteen Wikidata admin-1 rows whose names collide across shapes, sending
# each to the smallest shape whose box holds its coordinates fixes Minsk and
# breaks Moscow Oblast and Kyiv Oblast, whose Wikidata coordinates sit on the
# capital. Every other collision the identical-name tiebreak already gets
# right, because those boundary files write "Kyiv Oblast" and "Moscow Oblast"
# where Belarus's writes "Minsk". So this is a declaration about one boundary
# file's labels, not a rule.
#
# Keyed by the Wikidata item, so it can only ever move the row it names; the
# value is the polygon's label as the boundary file writes it. A label that is
# not drawn stops the build rather than letting the row fall back to a name.
PLACED: dict[tuple[str, str], str] = {
    ("BLR", "Q2280"): "Minsk City",
    ("BLR", "Q192959"): "Minsk",
}


def placed(iso3: str, row: dict[str, Any],
           shapes: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The row bound to the polygon PLACED names for its item, if it names one.

    The row takes the polygon's own label as its name, with its own name kept
    as an alias, so the binding moves figures and never relabels a shape.
    """
    label = PLACED.get((iso3, row.get("wikidata") or ""))
    if not label:
        return row
    target = [e for e in shapes if e.get("name") == label]
    if len(target) != 1:
        raise SystemExit(f"{iso3}: PLACED sends {row.get('wikidata')} to "
                         f"{label!r}, which this country draws "
                         f"{len(target)} times rather than once")
    aliases = [*(row.get("aliases") or [])]
    if row.get("name") and row["name"] != label:
        aliases.append(row["name"])
    return {**row, "name": label, "aliases": aliases,
            "match_by": "shape_id", "shape_id": target[0]["id"]}


def bound(by_shape: dict[str, dict[str, Any]],
          by_level: dict[tuple[str, str], dict[str, Any]],
          wanted: str | None, level: str | None) -> dict[str, Any] | None:
    """The polygon a shape_id binding names, at the level the row says it is.

    An id is not always one polygon. The boundary file draws a small country's
    units at both levels under the same shapeID -- all 68 of Malta's, all of
    Moldova's, Libya's, Trinidad's, 334 in all -- and an index keyed by id alone
    kept whichever level was indexed last. Every first-level population the
    Wikipedia reader bound that way went onto the second-level twin, and the
    first level it was read for came out empty. Where the id is drawn at the
    row's own level, that is the polygon; otherwise any level will do, which is
    what a binding meant before and still means for Nepal's and Bhutan's.
    """
    if wanted is None:
        return None
    return by_level.get((level or "", wanted)) or by_shape.get(wanted)


def blank(shape: dict[str, Any], level: str, parent: str | None) -> dict[str, Any]:
    return {
        "id": shape["shape_id"],
        "level": level,
        "name": shape["name"] or shape["shape_id"],
        "parent": parent,
        "country": shape["group"],
        "point": shape["point"],
        "bbox": shape["bbox"],
        "capital": gap(NOT_AVAILABLE),
        "largest_settlement": gap(NOT_AVAILABLE),
        "population": gap(NOT_AVAILABLE),
        "median_age": gap(NOT_AVAILABLE),
        "sex_ratio": gap(NOT_AVAILABLE),
        "religion": gap(NOT_AVAILABLE),
        "language": gap(NOT_AVAILABLE),
        "ethnicity": gap(NOT_AVAILABLE),
        "sources": [],
    }


def field_state(value: Any) -> str:
    if value is None:
        return NOT_AVAILABLE
    if isinstance(value, dict) and value.get("status"):
        return value["status"]
    if isinstance(value, list) and not value:
        return NOT_AVAILABLE
    return "present"


def group_index(admin0: list[dict[str, Any]],
                admin1: dict[str, list[dict[str, Any]]],
                admin2: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """What can be filtered on worldwide, and what each choice actually covers.

    The app cannot build this from the records it happens to have loaded: at
    world zoom it holds countries only, so a group picker fed from those would
    offer nothing below the national level, and one fed from a single country's
    shard would offer only that country's spellings. The whole point of a global
    filter is to know that "Muslim" and "Islam" are one answer before the map is
    drawn, so the list is assembled here, over every record, once.

    Each entry carries what it is fair to conclude from it: how many units hold
    a figure, which countries those are, the source labels folded into it, and
    any country measuring it a different way -- the US religion figures count
    adherents reported by religious bodies rather than answers people gave, so a
    map of Christianity shades those counties on a basis the others do not share.
    """
    index: dict[str, Any] = {}
    levels = [("admin0", [("", admin0)]),
              ("admin1", sorted(admin1.items())),
              ("admin2", sorted(admin2.items()))]
    for field in ("religion", "language", "ethnicity"):
        units: dict[str, int] = {}
        countries: dict[str, set[str]] = {}
        # The same two tallies taken over each group's whole subtree, which is
        # what a reader gets when they pick it.
        rolled_up: dict[str, dict[str, Any]] = {}
        labels: dict[str, set[str]] = {}
        bases: dict[str, str] = {}
        conflicts: set[str] = set()
        # Counted per level as well as overall. A group reported by 122
        # countries nationally may exist for only two of them at district
        # level, and a map pinned to districts that claims 122 is telling the
        # reader the opposite of what it is showing.
        per_level: dict[str, dict[str, dict[str, Any]]] = {
            name: {} for name, _ in levels}

        # An estimate's groups are indexed too -- placed in the tree, given a
        # hue and a tier -- but tallied apart, under ``estimated_units``, so
        # that "76 units hold a figure" never counts a model as a figure. Left
        # out, Thailand's 76 modelled provinces painted "not yet classified":
        # the map could read the estimate but had no entry to classify it by.
        estimated: dict[str, int] = {}

        for level_name, sources in levels:
          for iso3, rows in sources:
            for record in rows:
                value = record.get(field)
                if is_estimate(value):
                    table = canonical_groups.lookup(field)
                    guessed: set[str] = set()
                    for row in value.get("estimate") or ():
                        if not isinstance(row, dict) or \
                           not isinstance(row.get("pct"), (int, float)):
                            continue
                        raw = row.get("group", "")
                        name = table.get(canonical_groups.key(raw), raw)
                        labels.setdefault(name, set()).add(raw)
                        guessed.add(name)
                    rolled_est: set[str] = set()
                    for name in guessed:
                        rolled_est.update(canonical_groups.ancestry(field, name))
                    for name in rolled_est:
                        estimated[name] = estimated.get(name, 0) + 1
                    continue
                if not isinstance(value, list):
                    continue
                code = iso3 or record.get("country") or record.get("id", "")
                for bad in canonical_groups.check_no_double_counting(value, field):
                    conflicts.add(f"{code}:{bad}")
                basis = record.get(f"{field}_basis")
                if basis:
                    bases[code] = basis
                table = canonical_groups.lookup(field)
                # Collected first, counted once. Several rows of one record can
                # fold into one group -- the US publishes Protestant, Catholic,
                # Orthodox, Latter-day Saints and Jehovah's Witnesses where
                # Australia publishes one "Christianity" -- and counting rows
                # made "units" a row tally wearing the word "areas": the app
                # read Christianity's 450 out to a reader as 450 countries,
                # when only 215 country records carry a religion at all.
                here: set[str] = set()
                for row in value:
                    if not isinstance(row.get("pct"), (int, float)):
                        continue
                    raw = row.get("group", "")
                    name = table.get(canonical_groups.key(raw), raw)
                    labels.setdefault(name, set()).add(raw)
                    here.add(name)
                # A record counts once for every group it names and once for
                # each of their ancestors, never twice for either. Poland's
                # powiaty say "Roman Catholic" and no more, so Christianity's
                # own tally there is nil and its rolled-up tally is 380: the
                # picker has to offer the second number, because a reader who
                # asks for Christianity will get those 380 shaded.
                rolled: set[str] = set()
                for name in here:
                    rolled.update(canonical_groups.ancestry(field, name))
                for name in here:
                    units[name] = units.get(name, 0) + 1
                    countries.setdefault(name, set()).add(code)
                for name in rolled:
                    at = per_level[level_name].setdefault(
                        name, {"units": 0, "countries": set(),
                               "own_units": 0, "own_countries": set()})
                    at["units"] += 1
                    at["countries"].add(code)
                    if name in here:
                        at["own_units"] += 1
                        at["own_countries"].add(code)
                    total = rolled_up.setdefault(
                        name, {"units": 0, "countries": set()})
                    total["units"] += 1
                    total["countries"].add(code)

        if conflicts:
            # Rolling children into a parent is only sound while no source
            # publishes both levels at once. If one starts to, the totals would
            # silently double, so the build stops rather than shipping them.
            raise SystemExit(f"{field}: parent and child reported together in "
                             f"{sorted(conflicts)[:5]}")

        # Every name the tree reaches, not only the ones a source wrote. A
        # parent nobody spells -- Christianity across Poland, Sino-Tibetan
        # languages anywhere -- is still a group a reader can pick, and it has
        # to be in the list to be picked.
        names = set(units) | set(rolled_up) | set(estimated)
        kids = canonical_groups.children(field)
        index[field] = {
            "groups": [
                {"name": name,
                 # What picking this shades: the group and everything under it.
                 "units": rolled_up.get(name, {}).get("units", 0),
                 "countries": sorted(
                     c for c in rolled_up.get(name, {}).get("countries", ())
                     if len(c) == 3),
                 # What sources actually wrote under this exact name, which is
                 # a different and smaller thing for any parent.
                 "own_units": units.get(name, 0),
                 # Units whose figure for this group is a model or a
                 # derivation, not a reading: counted here and nowhere above.
                 "estimated_units": estimated.get(name, 0),
                 "parent": canonical_groups.parent_of(field, name),
                 "children": [k for k in kids.get(name, []) if k in names],
                 "depth": len(canonical_groups.ancestry(field, name)) - 1,
                 # How broad a claim this group is: 1 is the widest grouping
                 # the project is willing to make, 3 is what a census wrote.
                 # The map's category control reads it.
                 "tier": group_tree.tier(field, name),
                 "census_category": name in group_tree.census_categories(),
                 "hue": canonical_groups.hue(field, name),
                 "labels": sorted(labels.get(name, ())),
                 # A residual is an answer's absence, not an answer. The
                 # picker still lists it -- dropping it would hide a fifth of
                 # some populations -- but sorts it last and says so.
                 "residual": canonical_groups.is_residual(name),
                 "canonical": len(labels.get(name, ())) > 1
                              or name in canonical_groups.TABLES[field]
                              or name in kids,
                 "levels": {
                     level_name: {
                         "units": per_level[level_name][name]["units"],
                         "countries": sorted(
                             c for c in per_level[level_name][name]["countries"]
                             if len(c) == 3),
                     }
                     for level_name, _ in levels if name in per_level[level_name]
                 }}
                for name in sorted(
                    names,
                    key=lambda n: (-rolled_up.get(n, {}).get("units", 0), n))
            ],
            "bases": bases,
        }
    return index


TRACE: set[str] = set()


def claim(claimed: dict[int, str], entity: dict[str, Any], row: dict[str, Any],
          iso3: str, wanted: str) -> None:
    """Record a row's binding to a polygon, refusing a second place on it.

    Two rows on one shape is how one district quietly wears another's
    figures, and that is what this stops. Two rows *about the same place* are
    not that: Transnistria's population comes from the Wikipedia reader and
    its ethnic composition from the Moldova reader, each bound to the same
    polygon by id, and refusing the pair stopped the build over two sources
    agreeing on where Transnistria is. So the second claim is refused only
    where it names a different place from the first.
    """
    name = row.get("name") or ""
    held = claimed.get(id(entity))
    if held is not None and norm(held) != norm(name):
        raise SystemExit(
            f"{iso3}: shape {wanted!r} is claimed by {name!r} and by "
            f"{held!r}. Two rows on one shape is how one district quietly "
            f"wears another's figures")
    claimed[id(entity)] = name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--levels", nargs="*", default=["ADM0", "ADM1", "ADM2"])
    # A count says a join went wrong; it never says which row went where, and
    # the difference between 26 matched before a change and 26 after can be a
    # dozen rows swapping places. This prints the verdict on every row of one
    # country, which is what makes a matcher change measurable rather than
    # merely plausible.
    ap.add_argument("--trace", nargs="*", default=[], metavar="ISO3",
                    help="log every adapter row's match for these countries")
    ap.add_argument("--out", type=Path, default=SITE_DATA)
    args = ap.parse_args()
    TRACE.update(iso.upper() for iso in args.trace)
    # And from the environment, because the one place this join actually runs
    # is the refresh workflow -- the boundary files are ~550 MB and live
    # nowhere else -- and nothing there could reach a command-line flag. A
    # trace that cannot be switched on where the join runs is a trace that
    # answers questions only about the countries somebody once ran locally.
    TRACE.update(iso.strip().upper()
                 for iso in os.environ.get("BUILD_TRACE", "").split(",")
                 if iso.strip())
    if TRACE:
        log(f"build_entities: tracing {', '.join(sorted(TRACE))}")

    log("build_entities: reading boundaries")
    shapes = {level: read_shapes(level) for level in args.levels}
    if "ADM1" in shapes and "ADM2" in shapes:
        link_adm2_parents(shapes["ADM1"], shapes["ADM2"])
    # Before anything is joined: this is a claim about the boundary files alone,
    # and it is the claim that explains a level looking empty for a reason no
    # amount of data would fix.
    check_level_coverage(shapes)

    log("build_entities: reading attributes")
    # Several Factbook entities can share one ISO3 (Australia and the Coral Sea
    # Islands are both AUS; France and Clipperton are both FRA). fetch_factbook
    # gives the primary entity the bare code and suffixes the rest, so prefer the
    # record whose id *is* the code -- otherwise a dependency overwrites its
    # parent and the country panel shows the wrong place.
    country_profiles = read_json(PROCESSED / "admin0.json", [])
    countries = primary_country_profiles(country_profiles)
    cities = read_json(PROCESSED / "cities.json", {"by_country": {}, "by_admin1": {}})
    adapters = load_adapters()
    for line in pool_declared_unions(adapters):
        log(f"  union pooled: {line}")
    for line in split_declared_rows(adapters):
        log(f"  split written as estimates: {line}")
    curated_rows, provenance = load_curated()
    country_detail = load_country_detail()

    # -- admin 0 -------------------------------------------------------------
    admin0: list[dict[str, Any]] = []
    matched_iso3: set[str] = set()
    for shape in shapes.get("ADM0", []):
        iso3 = shape["group"]
        entity = blank(shape, "admin0", None)
        entity["id"] = iso3
        if is_disputed(iso3):
            # geoBoundaries carries disputed and special-status areas under
            # numeric group codes (Abyei, Aksai Chin, the Senkakus, Gaza, the
            # West Bank). They are real polygons but not countries, so they get
            # their own id space and are labelled rather than silently counted
            # as states.
            # The id stays the raw shapeGroup so it still matches the tile's
            # promoted feature id; the flag is what the UI keys off.
            entity["disputed"] = True
            entity["note"] = DISPUTED_NOTE
            admin0.append(entity)
            continue
        matched_iso3.add(iso3)
        source = countries.get(iso3)
        if source:
            for key, value in source.items():
                if key in {"id", "level", "parent"}:
                    continue
                if key == "sources":
                    entity["sources"].extend(value)
                elif key == "name":
                    entity["name"] = value
                else:
                    entity[key] = value
        else:
            entity["data_status"] = "no Factbook profile matched this ISO3 code"
        city = cities["by_country"].get(iso3)
        if city and is_gap(entity.get("largest_settlement")):
            entity["largest_settlement"] = city["name"]
            entity["largest_settlement_population"] = measure(
                city["population"], source=city["source"])
        admin0.append(entity)

    # Factbook entities with no CGAZ polygon -- dependencies and territories that
    # geoBoundaries folds into their administering state (Hong Kong, Macau,
    # Puerto Rico, Palestine, the Channel Islands...). Keeping them as
    # geometry-less records means they are still searchable and still show their
    # demographics, with the missing outline stated rather than implied.
    for source in sorted(geometryless_profiles(country_profiles, countries, matched_iso3),
                         key=lambda row: row["name"]):
        iso3 = (source.get("codes") or {}).get("iso3")
        entity = dict(source)
        entity["id"] = source["id"]
        entity["level"] = "admin0"
        entity["parent"] = None
        entity["country"] = iso3
        entity["geometry_available"] = False
        entity["point"] = source.get("capital_coordinates")
        entity["bbox"] = None
        entity["note"] = ("geoBoundaries' global composite has no separate outline for "
                          "this entity -- it is drawn as part of the state that "
                          "administers it. The figures below are still its own.")
        entity.setdefault("sources", [])
        admin0.append(entity)

    admin0.sort(key=lambda e: e["name"])

    # -- admin 1 -------------------------------------------------------------
    admin1_by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    adm1_index: dict[str, dict[str, str]] = defaultdict(dict)
    for shape in shapes.get("ADM1", []):
        iso3 = shape["group"]
        entity = blank(shape, "admin1", iso3)
        city = cities["by_admin1"].get(f"{iso3}||{norm_city(shape['name'])}")
        if city:
            entity["largest_settlement"] = city["name"]
            entity["largest_settlement_population"] = measure(city["population"], source=city["source"])
        mark_disputed_or_hint(entity, iso3)
        admin1_by_country[iso3].append(entity)
        adm1_index[iso3][norm(shape["name"])] = entity["id"]

    for iso3, rows in curated_rows.items():
        prov = provenance.get(iso3, {})
        indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in admin1_by_country.get(iso3, []):
            indexed[norm(e["name"])].append(e)
        add_known_as(indexed, admin1_by_country.get(iso3, []))
        lookup = {k: v[0] for k, v in indexed.items() if len(v) == 1}
        for row in rows:
            entity, how = match_name(row, lookup)
            if entity is None:
                log(f"  curated row unmatched: {iso3} / {row['name']}")
                continue
            apply_curated(entity, row, prov)
            entity["match"] = f"curated:{how}"

    # -- admin 2 -------------------------------------------------------------
    admin2_by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shape in shapes.get("ADM2", []):
        iso3 = shape["group"]
        entity = blank(shape, "admin2", shape.get("parent_shape") or iso3)
        mark_disputed_or_hint(entity, iso3)
        admin2_by_country[iso3].append(entity)

    # -- adapters override both levels --------------------------------------
    for iso3, rows in adapters.items():
        # Grouped, not a dict comprehension. CGAZ draws both "Kyiv" and "Kyiv
        # Oblast" as first-order units and norm() drops the word "Oblast", so
        # keying by name alone let one silently overwrite the other and made a
        # capital of 2.95 million or the region around it unreachable --
        # whichever the file listed first. Ukraine's census names both.
        a1_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entity in admin1_by_country.get(iso3, []):
            a1_by_key[norm(entity["name"])].append(entity)
        # After every real name, so an alias can only fill an empty key.
        aka = add_known_as(a1_by_key, admin1_by_country.get(iso3, []))
        # A flat view for resolving a *parent*, where an ambiguous key is
        # simply dropped: a parent nobody can identify cannot scope anything,
        # and there is no row name to settle it with.
        a1 = {key: found[0] for key, found in a1_by_key.items()
              if len(found) == 1}
        # ...and the written names, for a district row that names its parent:
        # "Almaty Region" is not ambiguous even though its key is.
        a1_exact = {" ".join(e["name"].split()).casefold(): e
                    for e in admin1_by_country.get(iso3, [])}
        # An ISO 3166-2 code is the one key on both sides that needs no
        # romanisation. Russia's sheets are Cyrillic and its shapes English,
        # and norm() keeps Cyrillic as Cyrillic on purpose -- a transliteration
        # invented here would be a guess about a name. A code matches or it
        # does not.
        #
        # The code is not on the shape. geoBoundaries publishes no ISO 3166-2
        # column at all -- shapeName, shapeID, shapeGroup, shapeType, and
        # nothing else -- so the codes reach an entity from the Wikidata
        # adapter, whose rows are merged only after this loop has finished
        # matching. An index read off the entities is therefore empty at
        # exactly the moment it is needed: built that way, all 83 Russian
        # subjects fell through to the name pass, Cyrillic against English,
        # and 82 of them landed nowhere. The one that matched did so on an
        # alias, which is what made the failure look like a near miss instead
        # of a total one.
        #
        # So it is built from the rows that carry the code, keyed by the name
        # those rows will themselves be matched on. A normalised name claimed
        # by two different codes is an ambiguity, not a first-wins race, and
        # is dropped from the index rather than guessed at.
        a2: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entity in admin2_by_country.get(iso3, []):
            a2[norm(entity["name"])].append(entity)
        aka += add_known_as(a2, admin2_by_country.get(iso3, []))
        # Both levels, because a binding names a polygon and does not care
        # which order the boundary file draws it at -- and each level on its
        # own as well, because some ids are drawn at both (see bound()).
        by_shape: dict[str, dict[str, Any]] = {
            entity["id"]: entity
            for entity in (*admin1_by_country.get(iso3, []),
                           *admin2_by_country.get(iso3, []))
            if entity.get("id")}
        by_level: dict[tuple[str, str], dict[str, Any]] = {
            (entity["level"], entity["id"]): entity
            for entity in (*admin1_by_country.get(iso3, []),
                           *admin2_by_country.get(iso3, []))
            if entity.get("id")}
        claimed: dict[int, str] = {}
        hit = miss = ambiguous = outside = collided = declared = 0
        matched: list[tuple[dict[str, Any], dict[str, Any], str]] = []
        deferred: list[tuple[dict[str, Any], dict[str, Any]]] = []
        # Which value fields each shape has already been given, and by a row
        # matched how. The code pass needs this per field rather than per
        # shape: Wikidata's rows carry a population for almost every shape in
        # the world, so "has any value already" would refuse every code match
        # there is, Russia's 83 included.
        bearing: dict[int, set[str]] = defaultdict(set)
        for row in rows:
            # A row may declare that no boundary of its own exists. The
            # Philippines' highly urbanized cities are drawn inside the
            # provinces around them and Addis Ababa's sub-cities as one shape,
            # so those rows cannot be shown -- but left to the matcher they are
            # not merely unshown, they are dangerous: "Cebu City" and "Province
            # Of Cebu" normalise alike, both match outright, and the collision
            # pass below reads two outright matches as one place listed twice
            # and lets the last one win. An adapter that knows the boundary
            # file folds an area away can say so, and a stated gap is the one
            # kind that cannot become a wrong answer.
            if row.get("no_shape"):
                declared += 1
                miss += 1
                continue
            row = placed(iso3, row, admin1_by_country.get(iso3, []))
            # Aliases travel with the key. They were being dropped here, which
            # made every alias an adapter declared for an admin-2 row or its
            # parent dead weight -- the matcher never saw them.
            key = {"name": row.get("name") or "",
                   "aliases": row.get("aliases") or [],
                   "parent_name": row.get("parent_name"),
                   "parent_aliases": row.get("parent_aliases") or [],
                   # The coordinates travel with the key for the same reason the
                   # aliases do: the matcher cannot use what this dict leaves
                   # behind, and dropping them here would silently disable the
                   # one rescue that lets a correct match survive a parent named
                   # historically rather than currently.
                   "point": row_point(row)}
            # A row that names the shape it belongs on is put there, and no
            # name is consulted. This is the escape hatch for a boundary file
            # whose geometry is right and whose *labels* are wrong: Nepal's
            # CGAZ ADM2 draws the 75 pre-2015 districts correctly and uses two
            # of their names twice, omits four, and puts two post-split names
            # on pre-split polygons. No alias can fix that -- the keys collide
            # with real district names elsewhere in the same country -- and no
            # name-keyed pass can tell two polygons called "Bara" apart.
            #
            # Deliberately narrow. The id must exist in the country being
            # joined and must not already be spoken for, and a row asking for
            # an id that is not drawn stops the run rather than falling back
            # to a name: a stale id is a real mistake and the fallback would
            # hide it behind a match that looks ordinary. This is the strongest
            # claim an adapter can make about a shape, so it is the one that
            # has to be checked hardest.
            if row.get("match_by") == "shape_id":
                wanted = row.get("shape_id")
                entity = bound(by_shape, by_level, wanted, row.get("level"))
                if entity is None:
                    raise SystemExit(
                        f"{iso3}: {row.get('name')!r} asks for shape "
                        f"{wanted!r}, which this country does not draw. A "
                        f"binding is a claim about a specific polygon, so a "
                        f"stale one is a mistake rather than a near miss")
                claim(claimed, entity, row, iso3, wanted)
                # The binding carries the name as well as the figures, and it
                # has to. A shape labelled "Nawalapur" wearing Rupandehi's
                # 1,121,957 people is exactly the mis-match this project ranks
                # below a gap: the label says one district, the figures are
                # another's, and nothing on screen would say so. The boundary
                # file's own label is kept as an alias, so a reader who
                # searches the name printed on the shape still finds it.
                # The label goes onto the ROW, not onto the entity:
                # merge_adapter copies the row's aliases over the shape's, so
                # an alias added here would be overwritten a moment later and
                # the boundary file's own spelling would become unsearchable.
                label = entity.get("name")
                wanted_name = row.get("name")
                if wanted_name and label and label != wanted_name:
                    entity["name"] = wanted_name
                    row["aliases"] = [*(row.get("aliases") or []), label]
                matched.append((row, entity, "shape_id"))
                continue
            if row.get("level") == "admin1":
                entity, how = match_name(
                    key, settle(a1_by_key, [key["name"], *key["aliases"]]))
                # A row that *asks* to be matched on its ISO 3166-2 code and
                # did not match by name is held back for the code pass below
                # rather than counted as a miss. It cannot be resolved here:
                # the codes are
                # not on the shapes -- geoBoundaries publishes shapeName,
                # shapeID, shapeGroup and shapeType and nothing else -- they
                # arrive from the Wikidata adapter, whose own rows are in this
                # same list and are merged only after this loop finishes.
                #
                # Matching the code against the entities *here* was tried and
                # is wrong twice over. The index is empty at this point, so all
                # 83 Russian subjects fell through to the name pass, Cyrillic
                # against English, and 82 landed nowhere. Rebuilding it from
                # the code-bearing rows instead does not work either, because
                # that is an exact-key index standing in for a fuzzy matcher:
                # norm() takes "Moscow" and "Moscow Oblast" to the same key and
                # "Karelia" and "Republic of Karelia" to different ones, so the
                # same eight subjects were lost to an ambiguity and a miss.
                # Asked for, never assumed. Carrying a code is not a request
                # to be matched on one, and treating it as one does damage:
                # Wikidata puts the county code LT-03 on "Alytus District
                # Municipality", so Lithuania's Alytus County -- which the
                # name pass had rightly refused that row -- took the
                # municipality's 25,356 people in place of its own hundred and
                # forty thousand. Laos' Vientiane took Vientiane Province's
                # population over the prefecture's the same way. Both are the
                # mis-match this project ranks below a gap: nothing on the map
                # would say the number was wrong.
                #
                # So only an adapter that cannot be matched by name at all
                # declares it, and only Rosstat's does.
                code = row.get("iso_3166_2")
                if (entity is None and row.get("match_by") == "iso_3166_2"
                        and isinstance(code, str) and code):
                    deferred.append((row, key))
                    continue
            else:
                entity, how = match_admin2(key, a2, a1, a1_exact)
            if entity is None:
                miss += 1
                ambiguous += how == "ambiguous"
                outside += how == "outside_parent"
                if iso3 in TRACE:
                    log(f"    trace {iso3} {row.get('name')!r}: {how}")
                continue
            matched.append((row, entity, how))

        # Second pass, because a collision cannot be seen one row at a time.
        dropped, notes = resolve_collisions(matched)
        collided = len(dropped)
        miss += collided
        for i, (row, entity, how) in enumerate(matched):
            if iso3 in TRACE:
                verdict = "beaten to it by another row" if i in dropped else how
                log(f"    trace {iso3} {row.get('name')!r} -> "
                    f"{entity.get('name')!r} ({verdict})")
            if i in dropped:
                continue
            merge_adapter(entity, row)
            entity["match"] = f"adapter:{how}"
            hit += 1
            bearing[id(entity)] |= value_fields(row)

        # -- the code pass ---------------------------------------------------
        # Now, and not before, the entities carry whatever ISO 3166-2 codes the
        # Wikidata rows brought with them. A code is the one key on both sides
        # that needs no romanisation: Russia's sheets are Cyrillic and its
        # shapes English, and norm() keeps Cyrillic as Cyrillic on purpose,
        # because a transliteration invented here would be a guess about a
        # name and the guesses that look right are the dangerous ones.
        #
        # There is no name fallback after a code miss. The code is the stronger
        # evidence, and a name match that contradicted it would be the
        # invisible kind of wrong. A row whose code no shape carries is a plain
        # miss -- which is what leaves Sakha, the one Russian subject with no
        # code, to the alias it declares instead.
        if deferred:
            a1_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for entity in admin1_by_country.get(iso3, []):
                code = entity.get("iso_3166_2")
                if isinstance(code, str) and code:
                    a1_by_code[code].append(entity)
            for row, key in deferred:
                found = a1_by_code.get(row["iso_3166_2"]) or []
                # One shape per code, or the code is not identifying here.
                if len(found) != 1:
                    miss += 1
                    ambiguous += len(found) > 1
                    if iso3 in TRACE:
                        log(f"    trace {iso3} {row.get('name')!r}: "
                            f"{'ambiguous code' if found else 'code on no shape'}")
                    continue
                entity = found[0]
                # Two answers to the same question about one shape is the case
                # to refuse: a row matched by name and a row matched by code
                # both stating its religion would let the later one win in
                # silence. Answers to *different* questions are the ordinary
                # case and are merged, which is how a Russian subject keeps the
                # population Wikidata gave it and gains the ethnicity Rosstat
                # did.
                clash = value_fields(row) & bearing[id(entity)]
                if clash:
                    collided += 1
                    miss += 1
                    if iso3 in TRACE:
                        log(f"    trace {iso3} {row.get('name')!r} -> "
                            f"{entity.get('name')!r} (beaten to "
                            f"{sorted(clash)} by another row)")
                    continue
                merge_adapter(entity, row)
                entity["match"] = "adapter:iso_3166_2"
                bearing[id(entity)] |= value_fields(row)
                hit += 1
                if iso3 in TRACE:
                    log(f"    trace {iso3} {row.get('name')!r} -> "
                        f"{entity.get('name')!r} (iso_3166_2)")

        for note in notes[:4]:
            log(f"    {iso3} {note}")
        if len(notes) > 4:
            log(f"    {iso3} ...and {len(notes) - 4} more shapes with rival rows")
        if rows:
            # Named separately because they mean different things. "Ambiguous"
            # is a row we cannot place; "outside" is a row we could have placed
            # wrongly and refused to -- the count is the mis-match that is no
            # longer happening, and it should not quietly grow.
            why = [f"{ambiguous} ambiguous" if ambiguous else "",
                   f"{outside} outside their stated parent" if outside else "",
                   f"{collided} beaten to their shape by another row" if collided else "",
                   f"{declared} with no boundary, as declared" if declared else "",
                   f"{aka} shapes reachable under a declared second name"
                   if aka else ""]
            extra = " (" + ", ".join(w for w in why if w) + ")" if any(why) else ""
            log(f"  {iso3}: adapter rows matched {hit}, unmatched {miss}{extra}")

    # -- the shape-gap table is a promise, so check it -----------------------
    # Here rather than at declaration time: it is a claim about what the join
    # did, and the join has only just finished.
    check_shape_gaps(admin1_by_country, admin2_by_country)

    # -- collection policy ---------------------------------------------------
    # Last, so an adapter's real value always wins over the national marker.
    policy_hits: dict[str, int] = defaultdict(int)
    for table in (admin1_by_country, admin2_by_country):
        for iso3, rows in table.items():
            for entity in rows:
                for field in apply_collection_policy(entity, iso3):
                    policy_hits[f"{iso3}/{field}"] += 1
    if policy_hits:
        total = sum(policy_hits.values())
        top = sorted(policy_hits.items(), key=lambda kv: -kv[1])[:8]
        log(f"  collection policy marked {total} subnational fields with a "
            f"declared gap and its reason: "
            + ", ".join(f"{k} {v}" for k, v in top))

    # -- sum parents from children -------------------------------------------
    # After the policy, so "not collected" still wins: a country that does not
    # ask the question has no children to sum, and must not be given a figure by
    # a later pass that only looks at arithmetic.
    roll_up_parents(admin1_by_country, admin2_by_country)
    # After the level below, so a first-level unit that was itself summed can
    # carry into its country -- and so the country's note counts the divisions
    # as they finally stand rather than as they arrived.
    check_no_stale_country_declaration(admin0, admin1_by_country)
    roll_up_countries(admin0, admin1_by_country)

    # Last, so a curated country row is the last word on the field it names.
    apply_country_detail(admin0, country_detail)

    # -- derived values ------------------------------------------------------
    # After the country row is final and before the bare fields are explained:
    # these are gaps that carry a guess, and say_why_empty leaves a gap with a
    # note alone. Nothing here rolls up, because an estimate is not a list.
    inherited = inherit_single_unit(admin0, admin1_by_country)
    if inherited:
        log(f"  {len(inherited)} single-unit countries handed their row down: "
            + ", ".join(inherited[:6]))
    derived, refused = residual_child(admin0, admin1_by_country)
    if derived:
        log(f"  {len(derived)} units derived by subtraction: " + ", ".join(derived))
    for line in refused:
        log(f"  not derived -- {line}")
    # And the same one level down. It runs after, but it does not build on
    # what ran before: a first-level unit the pass above filled is an estimate
    # rather than a list, and this pass subtracts only from a published
    # figure. Subtracting from a guess would compound it and the note would
    # still say "derived".
    derived2, refused2 = residual_grandchild(admin1_by_country, admin2_by_country)
    if derived2:
        log(f"  {len(derived2)} districts derived by subtraction from their "
            f"parent: " + ", ".join(derived2[:8])
            + (" ..." if len(derived2) > 8 else ""))
    for line in refused2:
        log(f"  not derived -- {line}")
    check_no_estimate_on_policy_field(admin1_by_country, admin2_by_country)

    # -- every bare field says why -------------------------------------------
    # Last of all, after the policy and the parent sums have had their turn:
    # this pass only names what is still empty, and must not get in front of
    # anything that could have filled it. 79,588 fields were bare here before
    # it existed, 83% of them on units no adapter had ever touched.
    country_name = {r["id"]: r.get("name") or r["id"] for r in admin0}
    why: dict[str, int] = defaultdict(int)
    for table in (admin1_by_country, admin2_by_country):
        for iso3, rows in table.items():
            joined = joined_here(rows)
            for entity in rows:
                case = say_why_empty(entity, country_name.get(iso3, iso3), joined)
                if case:
                    why[case] += 1
    if why:
        log("  every bare composition field now says why: "
            + ", ".join(f"{n} units where {k}" for k, n in
                        sorted(why.items(), key=lambda kv: -kv[1])))

    # -- write ---------------------------------------------------------------
    out = args.out
    write_json(out / "admin0.json", admin0, compact=True)
    for iso3, rows in sorted(admin1_by_country.items()):
        rows.sort(key=lambda e: e["name"])
        write_json(out / "admin1" / f"{iso3}.json", rows, compact=True)
    for iso3, rows in sorted(admin2_by_country.items()):
        rows.sort(key=lambda e: e["name"])
        write_json(out / "admin2" / f"{iso3}.json", rows, compact=True)

    # Search index, sharded so the first paint does not wait on 49k admin-2 rows:
    # shard 0 (countries + admin-1) loads with the page, shard 2 (admin-2) is
    # fetched in the background and merged when it lands.  Rows are positional
    # arrays -- [id, name, level, country, bbox] -- which is ~40% smaller than
    # the equivalent objects over 52k entities.
    admin1_names = {e["id"]: e["name"]
                    for rows in admin1_by_country.values() for e in rows}

    def row(entity: dict[str, Any], level: int, country: str) -> list[Any]:
        bbox = entity.get("bbox")
        # The parent's name is what separates Harris County, Texas from Harris
        # County, Georgia in the result list.
        parent = admin1_names.get(entity.get("parent") or "") or ""
        return [entity["id"], entity["name"], level, country,
                [round(v, 3) for v in bbox] if bbox else None, parent]

    shard0: list[list[Any]] = [row(e, 0, e.get("country") or e["id"]) for e in admin0]
    for iso3, rows in admin1_by_country.items():
        shard0.extend(row(e, 1, iso3) for e in rows)
    shard2: list[list[Any]] = []
    for iso3, rows in admin2_by_country.items():
        shard2.extend(row(e, 2, iso3) for e in rows)

    fields = ["id", "name", "level", "country", "bbox", "parentName"]
    write_json(out / "search-index-0.json", {"fields": fields, "rows": shard0}, compact=True)
    write_json(out / "search-index-2.json", {"fields": fields, "rows": shard2}, compact=True)
    index = shard0 + shard2

    # Coverage matrix: what exists, what is missing, what is never collected.
    coverage: dict[str, Any] = {}
    for entity in admin0:
        if entity.get("disputed"):
            continue
        owner = subdivision_owner(entity)
        entry: dict[str, Any] = {"name": entity["name"], "admin0": {}, "admin1": {}, "admin2": {}}
        for field in TRACKED:
            entry["admin0"][field] = field_state(entity.get(field))
        for level, table in (("admin1", admin1_by_country), ("admin2", admin2_by_country)):
            rows = table.get(owner, []) if owner else []
            entry[level]["count"] = len(rows)
            for field in TRACKED:
                states = [field_state(r.get(field)) for r in rows]
                entry[level][field] = {
                    "present": sum(1 for s in states if s == "present"),
                    "not_collected": sum(1 for s in states if s == NOT_COLLECTED),
                    "not_available": sum(1 for s in states if s == NOT_AVAILABLE),
                }
        coverage[entity["id"]] = entry
    write_json(out / "coverage.json", coverage, compact=True)

    write_json(out / "groups.json", group_index(admin0, admin1_by_country,
                                                admin2_by_country), compact=True)

    # A stamp derived from what was actually written, so the app can bust a
    # viewer's cached shards the moment the figures change -- and only then.
    # Content, not a timestamp: an unchanged rebuild must not invalidate
    # everyone's cache, and a changed one must.
    digest = hashlib.sha256()
    for path in sorted(out.rglob("*.json")):
        if path.name != "build.json":
            digest.update(path.read_bytes())
    write_json(out / "build.json",
               {"version": digest.hexdigest()[:12],
                "adapters": adapter_digests(),
                # The countries whose second level is an overlay rather than a
                # partition, so the map can put land under the ground that is
                # in no unit instead of letting it fall through to the water
                # colour. Emitted from PARTIAL_LEVELS rather than repeated in
                # JavaScript: the declaration and what the map draws from it
                # must not be able to disagree.
                "partial_levels": [
                    {"iso3": iso3, "level": level,
                     "units": entry["units"],
                     "coverage_pct": entry["coverage_pct"]}
                    for (iso3, level), entry in sorted(PARTIAL_LEVELS.items())
                ]}, compact=True)

    log(f"  admin0 {len(admin0)} | admin1 {sum(len(v) for v in admin1_by_country.values())} "
        f"| admin2 {sum(len(v) for v in admin2_by_country.values())} | index {len(index)}")
    return 0


def adapter_digests(processed: Path | None = None) -> dict[str, str]:
    """What each adapter file held when the site was last built.

    An adapter run and a site build are separate acts: the adapter writes to
    data/processed and only the full pipeline joins that into site/data. So a
    merged adapter and a country visible on the map are different states, and
    nothing connected them -- South Africa sat correct in data/processed and
    absent from the map for a week, and it took a reader asking "I don't see
    anything for South Africa?" to find it.

    Recording the inputs beside the output closes that: scripts/check_site_fresh.py
    compares this against the files on disk, so the divergence is reported by
    the build rather than noticed by a person.
    """
    processed = processed or PROCESSED
    out: dict[str, str] = {}
    for filename in ADAPTER_FILES:
        path = processed / filename
        if path.exists():
            out[filename] = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return out


def norm_city(text: str | None) -> str:
    """Match Natural Earth's ADM1NAME spelling, which keeps the generic word."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.strip().lower()


if __name__ == "__main__":
    raise SystemExit(main())
