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
* ``site/data/admin1/{ISO3}.units.json`` lazy-loaded on country selection
* ``site/data/admin2/{ISO3}.units.json`` lazy-loaded on admin-1 selection
* ``site/data/search-index.json``     flat id/name/level/parent rows for MiniSearch
* ``site/data/coverage.json``         per-country, per-field availability matrix

The join key is geoBoundaries' ``shapeID``; statistical sources are matched to it
by normalised name within a country, because no agency publishes shapeIDs.  Every
match records *how* it matched so a bad join is auditable rather than invisible.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from collections.abc import Sequence
from typing import Any, Callable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))

import canonical_groups
import check_rollups
import group_tree
from fetch_geonames import SPANS as GEONAMES_SPANS  # noqa: E402
from common import (  # noqa: E402
    DERIVED, MODELLED, NOT_APPLICABLE, NOT_AVAILABLE, NOT_COLLECTED, PROCESSED,
    RAW, ROOT,
    apply_collection_policy, collection_gap, estimate, gap, is_estimate, is_gap,
    known_as, log, measure, read_json, repair, respell, shard_path, write_json,
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
    # The European Social Survey, rounds 7-11 (2014-2024; from 2010 where a
    # region needs it to reach 100 respondents): religion and home language by
    # NUTS region, from the ESS portal's open tabulation service, bound by the
    # outline crosswalk. A survey, so it only fills (its name says so), and a
    # cross-national one, so a national survey stands in front of it too.
    "ess_region_survey.json",
    # National offices' surveys for the fields their censuses do not ask, each
    # a *_survey.json, so behind any count and in front of the ESS above.
    # Austria's religion by Land in 2021 (austria_religion): Statistik Austria's
    # estimate from questions added to the 2021 Mikrozensus (27,656
    # respondents), cells under its own 3,000 threshold withheld.
    "austria_religion_survey.json",
    # Religion by canton from BFS's structural survey, the mean of the
    # 2022-2024 annual estimates (switzerland_religion), each note with BFS's
    # drawn sample for the canton.
    "switzerland_religion_survey.json",
    # Main languages by canton from BFS's structural survey 2024 (switzerland):
    # a survey estimate with its drawn sample per canton, in its own file so
    # counts outrank it; it replaces switzerland_canton.json and writes no
    # population.
    "switzerland_language_survey.json",
    # Religion by province from CBS's own survey workbook, 2021/2025
    # (netherlands_religion); CBS's 'ander geloof' kept as the residual it is.
    "netherlands_religion_survey.json",
    # Religion by gemeente from CBS's Labour Force Survey, 2010-2015 pooled, on
    # the gemeenten of 2016 (netherlands_religion_gemeente): carried to the 344
    # drawn ones through CBS's record of mergers (70739ned), unions weighted by
    # their adults; a gemeente holding part of a divided one gets a gap saying so.
    "netherlands_religion_gemeente_survey.json",
    # ISTAT's 2015 survey 'I cittadini e il tempo libero' (24,000 households,
    # every region a domain): language used mostly in the family, persons aged
    # 6+, for the 20 regions and, added up, the 5 ripartizioni. Each note
    # gives ISTAT's own sampling error (Prospetto C) and the effective sample
    # it implies (980 to 8,250).
    "italy_language_survey.json",
    # Spain's regional offices' language surveys: the IGE's (table 2953, 2023)
    # language usually spoken for Galicia and its four provinces, 5+ (design:
    # 1,620 to 3,240 dwellings a province), and Idescat's EULP 2023 habitual
    # language for Catalonia, 15+ (effective sample 8,682; not by province).
    "spain_language_survey.json",
    # Spain's religion from the CIS's pre-electoral surveys (spain_cis): 27
    # provinces and 8 comunidades, 2019-2026, each from the newest study that
    # publishes it -- workbooks, HTML and PDF marginals, and La Rioja's 2019
    # PDF as the Internet Archive kept it. Spanish citizens 18+.
    "spain_cis_survey.json",
    # Catalonia's religion (four provinces and Catalonia) and first language
    # (provinces only; Catalonia keeps Idescat's EULP) from the CEO's political
    # barometer, waves 62-64 (2025-2026), open microdata tallied on the runner.
    "catalonia_ceo_survey.json",
    # Russia's religion by federal subject from Sreda's Arena survey (FOM,
    # 2012: 56,900 adults, 500 to 800 in each of 79 subjects). No census has
    # asked religion since 1937 (russia_religion).
    "russia_religion_survey.json",
    # Korea's pooled web-panel survey is the same kind of thing: a survey
    # that fills provinces no census file reaches, and that a census file
    # later in this list replaces field by field.
    "korea_province_survey.json",
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
    # spoken language from the 2021 Main Results workbook, on the SAR and
    # again on 'Xianggang', the polygon the second level draws it as.
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
    # nl.wikipedia infobox, which transcribes CBS. CBS's figures are survey
    # estimates, so TRANSCRIBED_SURVEYS ranks this file with the surveys and
    # behind CBS's own workbook above; it fills only what that leaves. It
    # touches religion only: language and ethnicity are NOT_COLLECTED_POLICY
    # for the Netherlands and this must not overwrite that.
    "netherlands_province.json",
    "wikidata_admin1.json", "wikidata_admin2.json",
    # Wikidata items of one class in one country, for the countries the
    # structural walk under-reached (fetch_wikidata --class-sweep). Fill-only
    # like the file above it.
    "wikidata_admin2_classes.json",
    # Wikidata populations for units whose office code, coordinate and name
    # all place them on one polygon (scripts/wikidata_points.py): bound by
    # id, so a romanisation the name matcher cannot bridge still arrives.
    "wikidata_points_admin1.json", "wikidata_points_admin2.json",
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
    # The same floor for the few units no infobox holds: a figure in a list
    # article's table, or a unit that is its country less another unit of
    # the same census (wiki_table_population). Fill-only like the file above.
    "wiki_table_population.json",
    # Lebanon's cazas and governorates: residents by nationality (Lebanese or
    # not) from CAS's Labour Force and Household Living Conditions Survey
    # 2018-19, Table HL.6A (lebanon_survey). Lebanon has held no census since
    # 1932; a survey, so its compositions only fill, behind any count, as a
    # *_survey.json's do wherever it sits. It sits below the encyclopaedic
    # floor above for its population statements: each caza's says no count of
    # its residents exists and displaces Wikidata's undated figure for it
    # (Baabda's 511,200), and a statement read before that figure would have
    # been overwritten by it -- and, where Wikidata has none, by Wikidata's
    # own "no P1082 statement" marker (Jezzine).
    "lebanon_survey.json",
    # The source a Wikipedia article cites, read where the article's own
    # figure garbles or contradicts it (cited_sources): Somalia's eighteen
    # regions from citypopulation.de's 2019 column, which six region articles
    # misprint, and the Seychelles' Outer Islands from the NBS bulletin its
    # article cites. Not fill-only: replacing those misprints is its purpose.
    "cited_sources.json",
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
    # Afghan district ethnicity read from the development plans' own PDFs (the
    # Internet Archive's copies): where a plan states shares they replace the
    # articles' transcription above, whose year is a range and so decides nothing.
    "afghanistan_ddp.json",
    # The statistics office's 1396 (2017-18) estimates by district and province:
    # settled population and sex ratio, temporary districts summed into the
    # polygon drawn for them; a stated reason for median age and ethnicity on all.
    "afghanistan_estimates.json",
    # Median age by district from the office's Socio-Demographic and Economic
    # Survey of twelve provinces (2011-16): a survey estimate from every other
    # listed household (Bamyan's from its full listing), each record giving its
    # basis and size. After the estimates file so its particular reasons stand.
    "afghanistan_sdes_survey.json",
    "cod_ps_admin2.json",
    # Median age and sex ratio from the same datasets' sex and five-year age
    # breakdown, for the regions no census file gives them. Fill-only (see
    # FILL_ONLY): most are the offices' projections, and a census's own figure
    # stands whatever year either is for.
    "cod_ps_age.json",
    # Turkey's 972 districts from TUIK's address-based register for 31
    # December 2022, by sex and five-year age group, as OCHA's COD-PS relays
    # it: count, median age and men per hundred women. Fill-only, so TUIK's own
    # tables would win (turkey_districts).
    "turkey_districts.json",
    # Uzbekistan's permanent population on 1 January, every region and
    # district, from the Statistics Agency's open-data portal (uzbekistan_siat).
    # Where the agency counts a district the boundary file does not draw, the
    # older shape around it carries both, or a gap that says why.
    "uzbekistan_siat.json",
    # Uzbekistan's 2026 census, preliminary results by region: population,
    # five-year ages, sex, nationality and native language
    # (uzbekistan_census). A count, so after SIAT's estimate for the same year.
    "uzbekistan_census.json",
    # Iraq's 2024 census from COSIT's Annual Abstract (iraq_census): every
    # governorate, and the districts of the governorates whose census districts
    # can be placed wholly inside the boundary file's older ones.
    "iraq_census.json",
    # Iran's 2016 census by province and shahrestan -- single-year ages, sex,
    # citizenship as ethnicity (basis "citizenship") -- and the 1395 yearbook's
    # religion by province, from Archive captures (iran_census). The three
    # shahrestans drawn as two polygons take each half's own settlement count.
    "iran_census.json",
    # Kyrgyzstan's 2022 census Book III: age, sex, ethnic group and native
    # language by region, district and city.
    "kyrgyzstan_census.json",
    # Tajikistan's 2020 census volume 2 and the 2010 census's nationality by
    # region.
    "tajikistan_census.json",
    # Turkmenistan's 2022 census volumes 2 and 4 by velayat, Ashgabat inside
    # Ahal. Every etrap carries its own reason, which displaces older
    # Wikidata figures.
    "turkmenistan_census.json",
    # Ecuador's 2022 census by province and canton, from INEC's workbook as
    # the Internet Archive captured it (ecuador_census): INEC's host refuses
    # the runner.
    "ecuador_census.json",
    # Median age and sex ratio for the same provinces and cantons, from sheet 2.1
    # of the same INEC workbook.
    "ecuador_profile.json",
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
    # Syria's 2004 census by governorate and district, from the Census Bureau's
    # HDX workbook (syria_census): age, sex and nationality, the census's only
    # identity question. The citizens' row is "Syrian citizens", naming no people.
    "syria_census.json",
    # Yemen's 2004 census by governorate and district from the same kind of
    # workbook (yemen_census): people, sex, nationality; the units the boundary
    # file cuts or merges say why they are empty.
    "yemen_census.json",
    # Median age from the CSO's 2017 district projection (yemen_census).
    # Fill-only: a projection never replaces a count.
    "yemen_census_age.json",
    # Bahrain's 2020 census on data.gov.bh (bahrain_census): governorates by sex
    # and eight nationality groups, written at both levels, the map drawing the
    # same four polygons twice; age and religion are kingdom-only and say so.
    "bahrain_census.json",
    # Saudi Arabia's 2022 census by region, sex and age as OCHA's COD-PS relays
    # GASTAT (saudi_census); the 147 governorates say why they hold no figure.
    "saudi_census.json",
    # Qatar's 2020 census by municipality, sex and age from data.gov.qa
    # (qatar_census); the 79 zones say why the portal's zone table is not used.
    "qatar_census.json",
    # Kuwait's 2021 register-based census from the CSB (kuwait_census):
    # governorates by sex, age and nationality group; areas by sex and Kuwaiti or
    # not, bound by their OpenStreetMap ground, the rest saying what they may hold.
    "kuwait_census.json",
    # Israel's CBS Statistical Abstract 2024 tables 2.17, 2.19 and 2.15
    # (israel_cbs): population group, median age, sex, district religion;
    # Jerusalem's encyclopaedia figures are displaced by a stated gap.
    "israel_cbs.json",
    # Jordan's DoS end-2025 estimates (people, sex) and 2015 census (median age,
    # nationality) by governorate (jordan_dos); the second-level shapes are not
    # the DoS's liwas and say so.
    "jordan_dos.json",
    # Oman's NCSI Statistical Year Book 2024 (oman_ncsi): wilayats' registered
    # population by nationality at the end of 2023, regions summed from them,
    # median age where a region is whole governorates.
    "oman_ncsi.json",
    # Abu Dhabi emirate from SCAD's census site (uae_scad): 2024 population and
    # sex ratio, written at both levels, the map drawing the emirates twice.
    "uae_scad.json",
    # Moldova's seven units the Europe reader refused, read by the owner's
    # decision of 22 September 2026 from the Romanian articles and the
    # Transnistria article's table. After europe_wiki_moldova.json, whose gap
    # rows for the same units carry the refusal as a note that this file's
    # reading must replace.
    "moldova_ethnicity_gaps.json",
    # Moldova's 2024 census annex: religion and mother tongue for the 35 units
    # it counted. After both files above, because the districts' Wikipedia
    # lists transcribe this same table -- with their editors' slips -- and
    # the census's own counts are the better reading of it.
    "moldova_census.json",
    # Bender and Transnistria, which Moldova's census did not reach: their
    # ethnicity from Transnistria's own 2015 census (Transnistria's summed
    # from its left-bank rows, and marked derived), their religion and
    # mother tongue modelled from it. After moldova_census.json, which has
    # nothing for either.
    "transnistria_2015.json",
    # After Wikidata, which carries a population for North Korea's provinces
    # and for Pyongyang a 2015 estimate: this is the 2008 census's own Table 2,
    # for all 11 first-level units and all 179 counties, with the sex ratio
    # beside it (males per 100 females), and Table 4's median age for the 7
    # provinces drawn on their 2008 ground. It writes no composition -- the
    # country asks none of the three, which this file's own reading of the
    # report is what established.
    "northkorea_county.json",
    # NUTS-1 where it is a first-level unit -- France's regions, Germany's
    # Laender, Belgium's regions, Italy's macro-regions, Mazowieckie -- placed
    # only by outline; the finer files follow and hold their own ground.
    "eurostat_nuts1.json", "eurostat_nuts2.json", "eurostat_nuts3.json",
    # The three second-level shapes NUTS cannot reach (spain_italy_age): Las
    # Palmas and Santa Cruz de Tenerife from INE's Estadistica Continua (single
    # years, 1 January 2026; Eurostat splits the Canaries by island), and
    # Trentino-Alto Adige as ISTAT's Bolzano plus Trento, age by age.
    "spain_italy_age.json",
    # Portugal's Censos 2021 from INE's JSON API (portugal_census): 308
    # municipalities and the 20 districts and autonomous regions (summed from
    # them) -- single years of age (median, sex ratio, head count) and
    # religion aged 15+ with the unanswered as Not stated. The 21 km2 second
    # 'Oliveira de Frades' polygon is written as a stated gap.
    "portugal_census.json",
    # Malta's 2021 census for the 68 localities, which both levels draw
    # (malta_census): single years, religion 15+ (Table 5.3), racial origin
    # (Table 4.3) and the Maltese citizens' main language (Vol. 3 Table 3.6)
    # as shares of all residents 5+, read from the Internet Archive's copies
    # (nso.gov.mt answers 403).
    "malta_census.json",
    # The Basque Country's language spoken at home, Eustat's 2021 Population
    # and Housing Statistics (its own census, cepv3_lhc04): the community and
    # its three provinces, everyone aged 2+ (basque_language).
    "basque_language.json",
    # The microstates' own offices (microstates): San Marino's castelli by sex
    # at 31 December 2025, Monaco's 2025 register-based census (districts of
    # Sovereign Order 4,481 of 2013) and Andorra's parishes in 2025, summed
    # from the Departament d'Estadistica's settlements.
    "microstates.json",
    # Japan's 2020 census for all 1,731 municipalities, bound by JIS code
    # (japan_municipal): population and nationality as ethnicity (e-Stat
    # 0003445244, the owner's decision of 19 September 2026), median age
    # (0004019308) and sex ratio (0004019309), and the prefectures' median and
    # sex ratio; religion and language not_collected on every municipality.
    "japan_municipal.json",
    # Korea's resident register by single year of age, 31 December 2025
    # (korea_ages): median age and sex ratio for 17 provinces and 228
    # districts; no population (korea_nationality's), no composition.
    "korea_ages.json",
    # Korea's 2015 census religion (korea_religion, KOSIS DT_1PM1502: the
    # sample's answers weighted to every resident) for 17 provinces and 228
    # districts. A count: it replaces the 2025 survey above wherever both reach.
    "korea_religion.json",
    # Taiwan's 368 townships (taiwan_townships): the household register at the
    # end of August 2026 for population, median age, sex ratio and indigenous
    # status; the 2020 census's main language from the county reports' Table 6;
    # religion not_collected. The 22 counties get the register's population,
    # median and sex ratio and keep taiwan_county.json's modelled religion;
    # their ethnicity is the register's indigenous-status count.
    "taiwan_township.json",
    # China's census yearbook 2020, the bureau's own tables (china_census): 31
    # provinces' population, sex ratio, median age and 56 nationalities (after
    # china_wiki_province, which transcribes the same tables); Hong Kong's and
    # Macau's 2021 median age and sex ratio.
    "china_census_province.json",
    # China's 2,370 county polygons (china_census): a reason on each mainland
    # polygon; Hong Kong drawn again ('Xianggang') with the SAR's median and sex
    # ratio and a stated count gap; Macau's 1.4 km2 sliver a stated gap.
    "china_census_county.json",
    # The provinces' own 2020 census yearbooks by county (china_county_census):
    # Jilin, Jiangsu, Qinghai, Inner Mongolia, Hebei and Shandong. Population,
    # sex ratio, median age and nationalities on the 75 polygons still the
    # county counted (six tests), a specific reason on the other 260. After
    # china_census_county.json, whose general reason it replaces.
    "china_county_census.json",
    # After Eurostat, which carries no ethnicity or religion for Romania and
    # says so in a generic sentence; this is the census itself.
    "romania_county.json",
    # Every commune's, town's and city's 2021 ethnicity and religion, as
    # Romanian Wikipedia charts the INS tables, bound by Wikidata item.
    "romania_uat.json",
    "india_state.json", "india_district.json",
    # After the C-01 files: mother tongue is the one field these add, and a
    # later file never overwrites an earlier real value with a gap marker.
    "india_language_state.json", "india_language_district.json",
    # Median age for every state and every district drawn as the 2011 census
    # counted it, from table C-13's single years; shapes made or cut since say
    # why, and nothing of a parent is put on a child.
    "india_age.json",
    # Place of birth (Census 2011 D-01) on the ethnicity field under its basis,
    # by the owner's decision of 19 September 2026; same shapes as india_age.
    "india_birthplace.json",
    "mexico_state.json", "mexico_municipality.json", "mexico_municipality_age.json",
    # Indigenous and Afro-Mexican self-identification, crossed in the extended
    # questionnaire's sample; ITER's files above carry no ethnicity.
    "mexico_ethnicity.json",
    "colombia_municipality.json",
    # Chile's 2024 census by region and province: population, median age, sex
    # ratio, religion, indigenous languages, and indigenous and Afro-descendant
    # identity, each summed from INE's comuna tables.
    "chile_census.json",
    # Argentina's 2022 census by province and department: population, median
    # age and sex ratio from single years of age, and indigenous and
    # Afro-descendant self-recognition. Bound by shape id, since the boundary
    # file files some departments under a neighbouring province.
    "argentina_census.json",
    # Panama's 2023 census by province, comarca and district: population, sex
    # ratio, median age (provinces), and indigenous and Afro-descendant
    # identity; districts split since 2010 summed back into their parents.
    "panama_census.json",
    # The same census's single years of age by district, from INEC's REDATAM
    # base LP2023: the median age of the 75 districts, which INEC's workbooks
    # do not tabulate. Each district is panama_census's, on the same polygon.
    "panama_redatam.json",
    # Honduras's 2013 census on INE's REDATAM base (181.115.7.199): median
    # age, sex ratio and P05/P06 ethnicity for the 18 departments and 297
    # municipios. No population: the base is the enumeration before INE's
    # adjustment for omission, and the map's 2024 figures are newer.
    "honduras_census.json",
    # Nicaragua's 2005 census on INIDE's REDATAM base: median age, sex ratio,
    # religion (P13, aged 5+) and P06/P07 ethnicity for the 17 departments
    # and 153 municipios, and the 2005 count, which only fills a municipio
    # the newer OCHA figures miss.
    "nicaragua_census.json",
    # El Salvador's 2024 census from the BCR's workbooks: population, median
    # age, sex ratio and the indigenous and Afro-descendant questions for the
    # 14 departments and the 262 districts (the old municipios). Same year as
    # OCHA's projections, and a count, so it replaces them.
    "el_salvador_census.json",
    # Costa Rica's 2011 census on INEC's REDATAM base: median age, sex ratio
    # and P07/P08/P10 ethnicity for the 7 provinces and 83 cantons (Rio Cuarto
    # and Puerto Jimenez as the districts they were made from), and the 2011
    # count on the cantons, which only fills Palmares.
    "costa_rica_census.json",
    # Bolivia's 2024 census by department and province, counted from INE's
    # person database: population, median age, sex ratio, nación o pueblo
    # (indigenous and Afro-Bolivian identity) and mother tongue.
    "bolivia_census.json",
    # Venezuela's 2011 census by state: the indigenous population by people,
    # and everyone else as one line.
    "venezuela_census.json",
    # Venezuela's 2011 census on INE's REDATAM base: median age, sex ratio and
    # ethnicity (the peoples and question 7's identity) for the 25 states and
    # 334 municipios, and the 2011 count by municipio. After venezuela_census
    # so its state ethnicity replaces the peoples-only line.
    "venezuela_redatam.json",
    # Paraguay's 2022 census on INE's REDATAM base by department and district:
    # population, age, sex, language (several answers allowed), indigenous
    # identity with the peoples by department from the 2022 Indigenous
    # Census's Cuadro A2; and the 2002 census's religion, departments and the
    # 201 districts drawn as they were then.
    "paraguay_census.json",
    # Uruguay's 2023 census microdata: departments from INE's July 2026
    # weighted release (checked against Cuadros 1 and 14); municipios and the
    # ground outside them from the February 2026 release, which files people
    # by the 2020 series the map draws. Principal ethnic-racial ancestry.
    "uruguay_census.json",
    # Peru's 2017 census by province, tabulated on INEI's REDATAM base:
    # median age, sex ratio, ethnicity, religion and mother tongue for the
    # 196 provinces, and median age, sex ratio and ethnicity for the first
    # level. It writes no religion or language there: peru_department.json,
    # the Perfil's department tables of the same count, carries those.
    "peru_redatam.json",
    # The same run's count of each province's people. It stands against
    # Wikidata's newer figures, as a count does against an encyclopaedia.
    "peru_redatam_population.json",
    # The Dominican Republic's 155 municipalities: median age and sex ratio
    # from the 2010 census's age-sex table, as the US Census Bureau tabulates
    # it (uscb_age_sex). They had neither; nothing else is written.
    "dominican_republic_age_sex.json",
    # Cuba's 16 provinces and 168 municipios (cuba_census): population, median
    # age and sex ratio from ONEI's 2024 estimates, skin colour from the 2012
    # census; Banes and Antilla, redrawn in 2021, left as stated gaps.
    "cuba_census.json",
    # The Dominican Republic's 2022 census (dominican_census): age, sex and
    # question 64 by province; population, age and sex by municipio, made to
    # the boundary file's extents. Supersedes the 2010 file above.
    "dominican_census.json",
    # Haiti's departments and arrondissements (haiti_census): IHSI's 2015
    # estimates by sex, and why religion stops at the country.
    "haiti_census.json",
    # Median age from UNFPA's 2024 COD-PS for Haiti, communes summed into
    # IHSI's arrondissements; a projection, so fill-only.
    "haiti_cod_ps_age.json",
    "nepal_province.json", "nepal_district.json",
    "nz_region.json", "nz_territorial.json",
    # After Eurostat, which covers both countries at NUTS 3 with population and
    # nothing else: these are the national registers, and ethnicity is a
    # question Eurostat does not ask.
    "estonia_county.json", "latvia_municipality.json", "finland_region.json",
    # Estonia's pre-2017 municipalities and counties (estonia): RV0241's single
    # years on 1 January 2017 for all 214 drawn units; mother tongue, religion
    # and (91 units) ethnicity from the 2011 census. After estonia_county.json.
    "estonia_municipality.json",
    # Latvia's 43 municipalities and 589 parishes and towns (latvia): CSB's
    # 2026 register population, median age, sex ratio and ethnicity; home
    # language from the 2011 census for 41 municipalities. After
    # latvia_municipality.json, which it supersedes field for field.
    "latvia_territorial.json",
    # Finland's 70 sub-regions of 2020 (finland): 11rf's single years summed by
    # the classification's key -- 31 December 2025 for the 57 unchanged since,
    # 2020 for the rest -- and the register's mother tongue (11rm, 2025).
    "finland_subregion.json",
    # Finland's religious community from the population register (finland_religion):
    # StatFin 11ra's Lutheran / other community / none shares, 31 December 2025, for the
    # 70 sub-regions and 19 regions as drawn (2020 key; Iitti and Vaala where the map
    # draws them), with the same day's population for the drawn territory.
    "finland_religion.json",
    # Lithuania's 60 municipalities and 10 counties (lithuania): the OSP's
    # single years for 1 January 2026; mother tongue from the 2021 census;
    # ethnicity 2021 for Vilnius county and 15 municipalities, 2011 elsewhere;
    # religion from 2011.
    "lithuania_municipality.json",
    # Sweden's 290 kommuner and 21 lan (sweden): SCB's register population on
    # 31 December 2025 by single year of age and sex (BefolkningCKM), with
    # median age and sex ratio.
    "sweden_kommun.json",
    # Church of Sweden membership by kommun and län (nordic_church): each unit's parish
    # members against its parishes' people, 31 December 2021 (Bjuv 2019); all 21 län and
    # the 275 kommuner whose parishes are their territory. Membership, not belief.
    "sweden_church.json",
    # Norway's 2017 kommuner and 2020-2023 fylker (norway): SSB 07459 today
    # where no merger has touched a kommune, else its last whole year (2017,
    # 2019, 2025); Church and other-faith membership (12026; 08531 by religion
    # for fylker); Klepp and Time withheld, as SSB's own note advises.
    "norway_kommune.json",
    # Denmark's 98 kommuner and 5 regions (denmark): StatBank FOLK1A's single
    # years (third quarter 2026) and KM6's National Church membership for every
    # resident on 1 January 2026 -- membership, not belief, non-members one
    # group.
    "denmark_kommune.json",
    # Iceland's 74 municipalities of 2017 and 8 regions (iceland): Hagstofa
    # MAN02005's 2026 count for the 52 no merger has touched, MAN09000's last
    # own 1 December count for each merged one; the regions summed from
    # MAN02005's municipalities.
    "iceland_municipality.json",
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
    # Mongolia's resident population at the end of 2025 by sex and five-year
    # age for all 339 soums (mongolia_ages, NSO DT_NSO_0300_068V2/067V2);
    # aimags are sums of their drawn soums, the 2025 reform's moves noted.
    "mongolia_ages.json",
    # Religion, population and mother tongue together: this one file reads
    # Table 9 and Table 11 of the same census. It used to be a pair, the
    # language half coming from the U.S. Census Bureau's tables of the 2017
    # round, which named nine tongues and left Chitral 93.1% "Other".
    "pakistan_district.json",
    # Census 2023 Table 4 (single years by sex) by district: median age and sex
    # ratio; Gilgit-Baltistan, which PBS tabulates apart, says why it has none.
    "pakistan_age.json",
    # Table 10's nationality on the ethnicity field under its basis, in the
    # census's own categories ("Bangali" as printed).
    "pakistan_nationality.json",
    # Bhutan's 20 dzongkhags and 205 gewogs from the PHCB 2017 dzongkhag reports:
    # population and sex ratio from Table 2.1, median age from annex A2.6/A2.7
    # where its groups add up, and citizenship (Table 2.2 against 2.1) on the
    # ethnicity field under its basis. Religion and language are declarations.
    "bhutan_gewog.json",
    "bangladesh_district.json",
    # Every zila's 2022 median age, interpolated in the five-year groups of the
    # Bureau's Community Series (Table C-02), each division's zilas held to
    # National Report Table P03 group by group; dated 2022 on the record.
    "bangladesh_zila_age.json",
    # The Maldives' 2022 census by atoll: head count, sex ratio and the bureau's
    # own median age; nationality on the ethnicity field under its basis.
    # (One shared comment; maldives_census.json and maldives_nationality.json go on one line: "maldives_census.json", "maldives_nationality.json",)
    "maldives_census.json",
    # (same line and comment as maldives_census.json)
    "maldives_nationality.json",
    "south_africa_province.json",
    # Statistics offices' own counts for units OCHA's COD-PS projects, after
    # cod_ps_admin2.json and cod_ps_age.json so each office's count stands in
    # front of the projection for the same unit: Senegal's RGPH-5 2023 by
    # region and department (Pikine and Rufisque say why they carry none),
    # Morocco's RGPH 2024 by region and province (the polygons the Western
    # Sahara line cuts say why), Zambia's final 2022 count by district,
    # Guinea-Bissau's 2009 census by sector, Tanzania's 2022 census by council
    # pooled onto the councils drawn, Ghana's PHC 2021 by district (with
    # religion and ethnicity), South Africa's Census 2022 by district
    # municipality, and Cabo Verde's 2021 census by municipality with its
    # parishes (the 18 parishes of the eight municipalities with several on
    # the 2010 census).
    "senegal_rgph5.json", "morocco_rgph2024.json", "zambia_census.json",
    "guinea_bissau_census.json", "tanzania_census.json", "ghana_census.json",
    "south_africa_districts.json", "cabo_verde_parishes.json",
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
    # Papua New Guinea's own office, two of its publications: the 2024 census's
    # head count and sex ratio for the 22 provinces and all 87 district shapes, and
    # the 2011 census's provincial median age (20 of 22; NCD's and Milne Bay's
    # contradict their sexes') and one provincial religion figure. Nothing else
    # writes PNG.
    "png.json",
    # Fiji's 2017 census by five-year age and sex for the 15 provinces and 4
    # divisions (median age, sex ratio), and the 2007 census's Table P01-3
    # religion and ethnicity, the latest by province. The Eastern polygon is Kadavu alone.
    "fiji_census.json",
    # Solomon Islands' 2019 census Basic Tables by province and ward, the wards
    # summed into the constituencies by OCHA's ward table: count, median age,
    # sex ratio, religion; ethnicity by province only. OCHA's 2023 projections
    # for the same constituencies give way to it (SUPERSEDED_ROWS).
    "solomon_census.json",
    # Vanuatu's 2020 census, Volume 1, for the six provinces and 58 drawn area
    # councils: count, median age (Table 4's own for the rural provinces), sex
    # ratio, ethnic origin, religion, and first language of everyone aged 3+.
    "vanuatu_census.json",
    # Samoa's 2021 census villages filed into the 41 old Faipule districts by the
    # 2016 census's village lists, and the 11 itumalo made of them: count, median
    # age, sex ratio, religion, and citizenship on the ethnicity field.
    "samoa_census.json",
    # Tonga's 2021 census General Tables for the five divisions and 21 drawn
    # districts: count, median age, sex ratio, religion, multi-response ethnic
    # origin; language at home by division only.
    "tonga_census.json",
    # Kiribati's 2020 census by island: the Island Profile's counts, the General
    # Report's sex and ethnicity, median ages from SPC's five-year tabulation of
    # the same census (the Report's own column contradicts its age groups), and
    # the 2015 census's religion by island. Same year as cod_ps_admin2.json's
    # island counts, so it replaces them.
    "kiribati_census.json",
    # The Marshall Islands' 2021 census by atoll, the same record at both levels:
    # count, median age, sex ratio, religion, ethnicity; language for Majuro and
    # Kwajalein only (multi-response).
    "marshall_census.json",
    # Tuvalu's 2022 census by island (count, median age, sex ratio), the 2017
    # census's religion and ethnicity by island, and its count and sex ratio for
    # the six drawn villages.
    "tuvalu_census.json",
    # The FSM's 2023 census by state and municipality (count, median age, sex
    # ratio, religion), the 2010 census's ethnicity and language, and the 2000
    # census's first ethnicity for Chuuk's and Kosrae's municipalities.
    "micronesia_census.json",
    # Nauru's 2021 census by district: count, sex ratio, median age from the
    # five-year groups above 15, ethnicity, and the religion of its citizens.
    "nauru_census.json",
    # Palau's 2020 census by state and Koror hamlet, transcribed from Volume I's
    # scanned tables: count, median age, sex ratio, ethnicity, religion, and
    # whether people speak Palauan.
    "palau_census.json",
    "kazakhstan_region.json", "cambodia_province.json",
    "kazakhstan_oblast.json", "kazakhstan_district.json",
    # Kazakhstan's 2021 census median age and sex ratio by region and district.
    "kazakhstan_census.json",
    # Religion by region from the 2021 census's brief results (table 7.1),
    # replacing Wikipedia's transcription, and by district from the 2009 census.
    "kazakhstan_religion.json",
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
    # GUS's own population, median age and sex ratio for the 380 powiats and
    # all 16 voivodeships (poland_ages, BDL, 31 December 2025): one definition
    # at both levels, 2.3% above Eurostat's usual-resident figures, which the
    # note measures and says.
    "poland_powiat_age.json",
    "czechia_kraj.json", "czechia_okres.json",
    # CZSO single years of age by okres, 31 December 2024 (czechia_ages):
    # median age, sex ratio and population; Prague is the kraj and the okres
    # at once.
    "czechia_okres_age.json",
    "croatia_county.json", "croatia_unit.json",
    "bosnia_entity.json", "bosnia_canton.json",
    # Bosnia's 2013 census by age and sex: median age and sex ratio for the
    # entities and Brcko from single years (FR_T1), for the ten cantons from
    # five-year groups (FR_T2). After bosnia_canton.json, which writes neither.
    "bosnia_age.json",
    # South-east Europe from its statistics offices' own tables, after the
    # europe_wiki_* files (whose Wikipedia transcriptions these replace at
    # the same year) and after Wikidata's head counts. Romania's 2021 census by
    # county and UAT (romania_census), after romania_uat.json, the Wikipedia
    # charts of the same INS tables; Bulgaria's 2021 by district and
    # municipality (bulgaria_census); Serbia's 2022 by district and
    # municipality from RZS's open data (serbia_census); Montenegro's 2023
    # (montenegro_census), North Macedonia's 2021 (north_macedonia_census) and
    # Kosovo's 2024 (kosovo_census) by municipality and region; Albania's 2023
    # compositions by prefecture, and its 36 former districts' head count and
    # sex ratio summed from the 2011 census's communes, or the 2023 count
    # where a district is one municipality (albania_census); Cyprus's 2021 by
    # district and community, with every polygon it does not reach saying why
    # (cyprus_census); Moldova's 2024 age and sex by district
    # (moldova_age); Greece's decentralized administrations' ages from
    # Eurostat's single years and Mount Athos's 2021 count (greece_age); and
    # Bucharest's six sectors' median age from DRSMB's population by legal
    # domicile of July 2022, which the census's ages do not reach
    # (bucharest_sectors); and the 2002 census's religion and mother tongue
    # for the five municipalities merged into Kichevo in 2013, which the map
    # draws as they were and the 2021 census does not reach
    # (north_macedonia_2002).
    "romania_census.json", "bulgaria_census.json", "serbia_census.json",
    "montenegro_census.json", "north_macedonia_census.json", "kosovo_census.json",
    "albania_census.json", "cyprus_census.json", "moldova_age.json", "greece_age.json",
    # The census taken in 2011 by the Turkish Cypriot administration in the
    # north (not recognised internationally), by village, on the polygons its
    # quarters can be bound to; every other northern polygon, the villages in
    # the buffer zone and Kyrenia district say why they have no figure
    # (cyprus_north_census). After cyprus_census.json, whose 2021 counts stand
    # wherever both reach.
    "cyprus_north_census.json",
    "bucharest_sectors.json", "north_macedonia_2002.json",
    "myanmar_state.json", "ukraine_oblast.json", "car_prefecture.json",
    "peru_department.json",
    # Southeast Asia from its offices' own tables. After indonesia, timor,
    # singapore_planning_area, philippines_province, thailand_province,
    # cambodia_province and myanmar_state, whose same-year figures these replace.
    # Indonesia: population, median age and sex ratio for 34 provinces and 513
    # regencies, BPS 2020 census Long Form (2022, Table 3.1) via USCB on HDX;
    # stated reasons for regency ethnicity, religion and language.
    "indonesia_age.json",
    # Viet Nam: 2019 census district population and sex ratio (Table 1) and
    # province median age (Table 5); religion by province from the 2009 census
    # (Tables 7 and 1), which 2019 publishes for the country only.
    "vietnam_district.json",
    "vietnam_religion.json",
    # Timor-Leste: 2022 municipality median and sex ratio; post sex ratio and
    # count (2022) and post median (2015, tables 6 and 7); nationality by
    # municipality (2015, table 9) as ethnicity_basis "nationality".
    "timor_age.json",
    "timor_nationality.json",
    # Myanmar: median, sex ratio and count by district and state/region from the
    # 2014 census's five-year groups; nine split or zoned polygons summed.
    "myanmar_age.json",
    # Philippines: median, sex ratio and count by province and region from the
    # PSA 2020 census single years by barangay; two mismatched polygons say why.
    "philippines_age.json",
    # Religion and ethnicity summed onto Myanmar's composed districts and Metro
    # Manila's districts, under uscb's labels; CLEAR Global's 2010 household
    # language bound to Metro Manila's four districts, Isabela's row refused.
    "sea_composed.json",
    # Singapore: median age and sex ratio by planning area, Census 2020.
    "singapore_age.json",
    # Cambodia: district and province count and sex ratio, 2019 census final
    # report (Table 2.1.1, annex P-01 to P-25), communes crosswalked by name.
    "cambodia_census.json",
    # Thailand, Laos, Cambodia: COD-PS medians and sex ratios (projections,
    # FILL_ONLY), plus Thailand's district composition reasons, which replace
    # thailand_province's generic ones.
    "sea_cod_ps_age.json",
    # Thailand: Thai and foreign nationals by province, 2000 census (each final
    # report's key indicators, read off the page and checked against the
    # census's Table 1), ethnicity_basis "nationality". A count, so it replaces
    # thailand_ethnicity's modelled estimate on the 76 provinces.
    "thailand_nationality.json",
    # Guatemala's 2018 census, read from INE's person database: pueblo and
    # the language each person learned to speak in, for all 22 departments
    # and 340 municipios. Below CLEAR Global, whose 2002 sample it replaces
    # field by field; it writes no population, so the newer 2024 figures on
    # the municipios stand.
    "guatemala_census.json",
    "mali_region.json",
    # After both Afrobarometer and the 2009 census file: Mali's nine regions
    # now carry RGPH5 2022 for all three fields.
    "mali_rgph5_region.json",
    "drc_province.json", "russia_subject.json",
    # Russia's 2020 census count and men per hundred women for the municipal
    # districts and urban okrugs, bound one to one by name, kind and the towns
    # inside. Okrugs merged since the boundary file was drawn, and Chechnya's
    # 2019-2020 redrawing, are written as gaps that say why (russia_municipal).
    "russia_municipal.json",
    # Ukraine's 2001 census by raion and city council -- count, median age,
    # sex, native language and nationality -- placed on the pre-2020 raion
    # outlines by name and by the census's own outlines, each seat city by
    # area; the oblasts' median age and sex from the 2017 estimate. After
    # ukraine_oblast so a tie goes to the office (ukraine_raion).
    "ukraine_raion.json",
    # Belarus's 2019 census, volume 2: count and sex for every raion with the
    # oblast-subordinate cities it holds; nationality and home language by
    # oblast (belarus).
    "belarus.json",
    # Georgia from Geostat: the 1 January 2026 count; the 2014 census's age,
    # sex, nationality, religion and native language by region; sex and median
    # age by municipality; nationality by municipality from 2002 (georgia).
    "georgia.json",
    # Abkhazia, which Georgia's census and estimates do not reach, from its de
    # facto authorities' statistics committee: the 1 January 2026 count by
    # district and sex, and the 2011 census's ages and nationality. Two of the
    # six drawn municipalities are one of their districts; the other four are
    # gaps that say why. After georgia.json, whose stated gaps it replaces
    # (abkhazia_census).
    "abkhazia_census.json",
    # Armenia's marzes and Yerevan on 1 January 2026 from Armstat's age-sex
    # workbook; the map's pre-1995 raions are gaps that say why (armenia).
    "armenia.json",
    # Armenia's 2011 census by marz, with Yerevan at both levels: nationality,
    # mother tongue and religion, the latest published below the republic
    # (armenia_2011).
    "armenia_2011.json",
    # Azerbaijan's rayons and cities on 1 January 2026 by age and sex (Azstat
    # table 1.23), with the four cities the map draws apart from table 1.19
    # (azerbaijan).
    "azerbaijan_rayon.json",
    "colombia_department.json", "jamaica_parish.json",
    "bahamas_island.json",
    # The Caribbean from its statistics offices' own tables, after the Census
    # Bureau's tabulations above (jamaica_parish, bahamas_island) so a tie
    # goes to the office. Jamaica's 2022 count by parish and by community,
    # bound by name within the parish (jamaica_census). Trinidad and
    # Tobago's 2011 Demographic Report by municipality, Arima inside the
    # map's Tunapuna-Piarco (tto_census).
    "jamaica_census.json", "tto_census.json",
    # Guyana's 2012 compositions and median age by region and its 2022
    # preliminary count; the sub-regions as stated gaps (guyana_census).
    # Suriname's 2012 census by ressort -- ethnic group, age and sex -- with
    # 2004's ressort religion and household language (suriname_census).
    "guyana_census.json", "suriname_census.json",
    # Belize's 2022 tables by district (belize_census); The Bahamas' 2010
    # island reports for the islands the map draws whole (bahamas_census);
    # Barbados's 2021 tables by parish with the 2010 population
    # (barbados_census).
    "belize_census.json", "bahamas_census.json", "barbados_census.json",
    # Median age and sex ratio from the Census Bureau's age-sex sheets for
    # Dominica's parishes and the Bahamas' whole islands (caribbean_uscb).
    "dominica_census.json", "bahamas_age_sex.json",
    # Saint Lucia's 2022 districts and 2010 settlements (lucia_census),
    # Grenada's 2021 parishes (grenada_census), Saint Vincent's 2012 districts
    # summed into parishes with 2023's divisions where whole (vincent_census),
    # Antigua and Barbuda's 2011 parishes (antigua_census).
    "lucia_census.json", "grenada_census.json", "vincent_census.json",
    "antigua_census.json",
    # Last, and only gaps: what none of the above fills, with the reason. A
    # gap never replaces a value, so its place in the list costs nothing.
    "caribbean_gaps.json",
    "brazil_state.json", "brazil_municipality.json",
    "germany_land.json", "germany_regierungsbezirk.json",
    # Austria's 94 political districts (austria): population, median age and
    # sex ratio on 1 January 2026, summed from Statistik Austria's OGD
    # population by municipality, sex and single year of age; Vienna's 23
    # Gemeindebezirke as the one district the map draws.
    "austria_bezirk.json",
    # Religion and Umgangssprache for the same 94 districts from the 2001
    # census, the last to ask (austria_census): Statistik Austria's
    # per-municipality census sheets, a municipality merged since 2001 read as
    # its 2001 parts; municipalities checked to 8,032,926.
    "austria_census.json",
    # Liechtenstein's eleven Gemeinden at both levels (liechtenstein):
    # population, median age and sex ratio on 31 December 2025 from eTab
    # 211.004, religion and main language from the 2020 census.
    "liechtenstein_gemeinde.json",
    # Switzerland's districts as the map draws them (2009) (switzerland_ages):
    # population, median age and sex ratio on 31 December 2025 from BFS
    # STATPOP through AGVCH; the 27 a merged commune straddles take BFS's
    # population for the last year their communes nested.
    "switzerland_bezirk.json",
    # Religion and main language for the same 2009 districts from the 2000
    # census, the last to ask everyone (switzerland_census): BFS's commune
    # tables carried to 2009 through AGVCH, communes and units each checked to
    # 7,288,010.
    "switzerland_census.json",
    # Slovakia's 2021 census nationality, mother tongue and religion by kraj
    # and okres (slovakia_census), the office's own tables; after
    # europe_wiki_slovakia, whose Wikipedia-read compositions it replaces on
    # all 87 units.
    "slovakia_census.json",
    # The office's own median age by okres, with population and sex ratio from
    # DATAcube, 31 December 2025 (slovakia).
    "slovakia_okres.json",
    # Hungary's 2022 census by county and district (hungary): ages, sex,
    # religion, nationality and mother tongue from KSH's census database; the
    # 13 districts of 2013-14 whose settlements moved since (Polgardi among
    # them) summed from settlements via KSH's 2014 gazetteer.
    "hungary_census.json",
    # Slovenia's 212 municipalities, 1 January 2026 (slovenia): SiStat single
    # years of age and population by sex; an outlying sex ratio or median says
    # why, from SiStat's settlements.
    "slovenia_obcina.json",
    # Ethnicity, religion and mother tongue from the 2002 census, the last to
    # ask (slovenia_census): the 168 municipalities unchanged since 2002 and
    # both cohesion regions; the 45 others are stated gaps.
    "slovenia_census.json",
    # The 344 gemeenten (Weesp inside Amsterdam) with CBS's key figures of 1
    # January 2022, read from the wijk- en buurtkaart WFS on PDOK: population
    # and sex ratio (netherlands_gemeente).
    "netherlands_gemeente.json",
    # Luxembourg's communes and cantons from the 2021 census (luxembourg):
    # population, median age (five-year groups) and sex ratio; the six
    # communes merged in 2018 take STATEC's 2017 population and the 2011
    # census's age and sex.
    "luxembourg_commune.json",
    # Ethnicity where the state records nationality, country of birth or
    # origin rather than ethnicity, by the owner's decision of 19 September
    # 2026 (the Korean and Japanese model), each under an ethnicity_basis
    # naming exactly what was counted: Austria's citizenship by Bezirk and
    # Land (austria_nationality), Switzerland's by district and canton
    # (switzerland_nationality), Belgium's by province and region
    # (belgium_nationality), Luxembourg's by commune and canton
    # (luxembourg_nationality); Sweden's country of birth, Norway's immigrant
    # background, Denmark's ancestry and Iceland's citizenship by municipality
    # and region (nordic_origin).
    "austria_nationality.json", "switzerland_nationality.json",
    "belgium_nationality.json", "luxembourg_nationality.json",
    "sweden_origin.json", "norway_origin.json", "denmark_origin.json",
    "iceland_origin.json",
    "canada_province.json", "canada_economic_region.json",
    "australia_state.json", "australia_lga.json",
    # The ABS's 2021 General Community Profile for the 547 LGAs and nine states
    # (australia_profile): median age (G02), sex ratio (G01), ancestry on the
    # ethnicity field (G08); each state's own G01 count and G14/G13 religion and
    # language (Australian Indigenous languages named) from the SA2+ tables.
    "australia_profile.json",
    "uk_lad.json", "uk_county.json",
    # England and Wales themselves, the map's first level: the same ONS 2021
    # tables (TS021 ethnic group, TS030 religion, TS024 main language) asked
    # of Nomis for the two nations rather than rolled up -- the Isles of
    # Scilly are drawn outside England, so England's children are one short
    # of it (uk_nomis --level nation).
    "uk_nation.json",
    # Scotland's councils and Northern Ireland's districts are shapes the ONS
    # census cannot reach: it covers England and Wales. Neither overlaps the
    # two files above or each other, so the order between them never arises.
    "scotland_council.json", "northern_ireland_district.json",
    # Population, median age and sex ratio for all 216 UK second-level shapes
    # and the four nations (uk_mye): the ONS, NRS and NISRA mid-year estimates
    # by single year of age (Nomis NM_2002_1), mid-2025 (Northern Ireland
    # mid-2024). Newer than the census head counts above, which it replaces;
    # Cumbria and Northamptonshire are their successor unitaries added age by
    # age, and a figure far from its mid-2021 one carries the office's series
    # in its note (City of London).
    "uk_mye.json",
    # The other island. No overlap with anything above: the CSO's areas are in
    # the Republic and every UK file stops at the border.
    "ireland_lea.json",
    # Ireland's four provinces (ireland): religion, ethnicity and home
    # language, Census 2022, each the sum of its own local electoral areas by
    # the county the CSO names -- not of the areas drawn inside its outline,
    # which put Newport (Tipperary), a Munster area, inside Connacht.
    "ireland_province.json",
    # Ireland's median age and sex ratio, Census 2022 (ireland_age): the
    # provinces from single years by county (FY006B, State median 38.8, the
    # CSO's), the 166 local electoral areas interpolated within five-year
    # groups (SAP2022T1T1ALEA22).
    "ireland_age.json",
    "us_state.json", "us_county.json",
    # Guam, the Virgin Islands, American Samoa and the Northern Marianas, which
    # the ACS does not survey: their 2020 census, territory and district.
    "us_island_areas.json",
    # After us_county, and replacing its religion rather than filling a gap.
    # The 2020 U.S. Religion Census that us_acs carries counts adherents as
    # religious bodies report them, which reaches about half the population
    # and pools everyone else as "unaffiliated or not reported" -- so it
    # cannot tell somebody with no religion from somebody nobody counted.
    # PRRI asks people, covers all of them, and separates the two. The owner
    # weighed that and chose it.
    "us_prri_county.json",
    # Last of all: the stated reasons for polygons no figure describes (towns
    # drawn inside the territory that counts them, a lake, pieces of other
    # units, rows no tabulation has). It writes no figure, so it displaces
    # none, and being last its reason replaces an earlier, vaguer one.
    "stated_gaps.json",
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
    "KAZ": "2021 census religion by region from the Bureau's brief results, and by "
           "district from the 2009 census's regional volumes "
           "(python -m scripts.fetch_census.kazakhstan_religion); ethnicity by "
           "region and district from the Bureau's start-of-2025 workbook "
           "(python -m scripts.fetch_census.kazakhstan); median age and sex ratio "
           "from the 2021 census (python -m scripts.fetch_census.kazakhstan_census)",
    "UZB": "Population, median age and sex ratio by region and district from SIAT "
           "(python -m scripts.fetch_census.uzbekistan_siat); the 2026 census's "
           "preliminary results by region -- population, age, sex, nationality, "
           "native language (python -m scripts.fetch_census.uzbekistan_census)",
    "KGZ": "2022 census Book III, the nine regional books: population, age, sex, "
           "ethnic group and native language by region, district and city: "
           "python -m scripts.fetch_census.kyrgyzstan_census",
    "TJK": "2020 census volume 2 (age and sex by region; men and women by city and "
           "district) and the 2010 census's volume III (nationality by region): "
           "python -m scripts.fetch_census.tajikistan_census",
    "TKM": "2022 census volumes 2 and 4 by velayat (age, sex, nationality, mother "
           "tongue): python -m scripts.fetch_census.turkmenistan_census",
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
    "MEX": "INEGI Censo 2020 ITER (religion, indigenous language): "
           "python -m scripts.fetch_census.mexico --level both; extended "
           "questionnaire (indigenous and Afro-Mexican self-identification): "
           "python -m scripts.fetch_census.mexico_ethnicity",
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
IRAN_LANGUAGE = (
    "Language: no Iranian census has ever asked it. Some provinces and "
    "counties carry a figure all the same -- a population-weighted roll-up of "
    "the settlement estimates in the Atlas of the Languages of Iran, marked as "
    "the atlas's field estimates and not as anybody's count. The atlas is "
    "published province by province and has reached twelve of the thirty-one; "
    "the rest of the country is empty because those modules do not exist yet, "
    "and Kermanshah is empty because its module reaches five of its fourteen "
    "counties and under a fifth of its people.")
ADAPTER_GAPS: dict[str, str] = {
    "THA": "The statistical office's own tables have not been obtained from its "
           "websites. Religion by province is the 2000 census, taken from its "
           "provincial final reports as transcribed on Wikipedia; language was "
           "made public once, for 2000, in a table whose shares are not parts of "
           "one whole. "
           "Ethnicity is not asked: the provinces carry the 2000 census's count "
           "of Thai and foreign nationals.",
    # Only language is left for this to explain. The 2016 census's religion
    # by province now comes from iran_census.json, which reads the Statistical
    # Centre's 1395 yearbook as the Internet Archive captured it (amar.org.ir
    # itself still ends the TLS handshake), and every unit it cannot fill --
    # each county, Golestan, the polygon drawn for Bandar-e Gaz -- carries
    # its own stated reason.
    "IRN": IRAN_LANGUAGE + " Religion is a different gap: the 2016 census "
           "asked it and the Statistical Centre publishes it by province only, "
           "so no county carries it.",
}
# A country-level reason for one field, where ADAPTER_GAPS' one sentence for
# the whole unit would be wrong about the others. Egypt's said CAPMAS withheld
# religion, and say_why_empty put that under language and ethnicity too, and
# on 341 districts whose main empty field is a population nobody has counted
# for them. Iran's put its religion sentence under language. A reason given
# by level applies at that level only. Checked by say_why_empty before the
# unit's gap_reason, and never over a note already there.
FIELD_GAPS: dict[str, dict[str, str | dict[str, str]]] = {
    "EGY": {
        "religion": {
            "admin1": "CAPMAS collected religion in the 2017 census and has not "
                      "published it, nationally or by governorate; the last "
                      "published figures are the 2006 census's, national only. 17 of "
                      "the 27 governorates carry a survey estimate instead, from "
                      "Afrobarometer Round 5 (2013), the last round that asked "
                      "religion in Egypt; this governorate is not among them.",
            "admin2": "CAPMAS collected religion in the 2017 census and has not "
                      "published it, nationally, by governorate or by district; the "
                      "last published figures are the 2006 census's, national only. "
                      "The survey estimate some governorates carry (Afrobarometer "
                      "Round 5, 2013) is sampled by governorate and gives no figure "
                      "for a district.",
        },
        "language": "Afrobarometer asked about language in Egypt but coded every "
                    "one of its 2,388 Egyptian respondents, across both rounds, to a "
                    "single value, so no composition is built from it, and no census "
                    "table of language by governorate or district has been read.",
        "ethnicity": "Afrobarometer did not ask about ethnicity in Egypt in either "
                     "round that surveyed it, and no census table of ethnicity by "
                     "governorate or district has been read.",
    },
    "IRN": {"language": IRAN_LANGUAGE},
}


def field_gap(country: str | None, field: str, level: str | None) -> str | None:
    """FIELD_GAPS' reason for this field of a unit of this country and level."""
    reason = FIELD_GAPS.get(country or "", {}).get(field)
    if isinstance(reason, dict):
        return reason.get(level or "")
    return reason

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
SHAPE_GAPS: dict[str, dict[str, str]] = {
    # El Salvador's second level has ten polygons geoBoundaries leaves
    # unnamed: pieces of the Bay of Jiquilisco and the Gulf of Fonseca, ground
    # along the Honduran border, and one in Sonsonate. With no name, no
    # census row can be matched to them.
    "SLV": {
        "Null": (
            "The map draws this polygon with no name (\"Null\") and does not "
            "say which district's ground it is, so no census count can be put "
            "on it."),
    },
    # Ecuador's two zonas no delimitadas the boundary file draws: ground whose
    # province was unsettled when it was drawn. INEC's 2022 table is by canton
    # and has no row for either.
    "ECU": {
        "El Piedrero": (
            "Not a canton: one of Ecuador's zonas no delimitadas, ground whose "
            "province was not settled when the boundary file was drawn. INEC's "
            "2022 census table is by canton and has no row for it, so no count "
            "is published for it as a unit."),
        "Las Golondrinas": (
            "Not a canton: one of Ecuador's zonas no delimitadas, ground whose "
            "province was not settled when the boundary file was drawn. INEC's "
            "2022 census table is by canton and has no row for it, so no count "
            "is published for it as a unit."),
    },
}


# ---------------------------------------------------------------------------
# Shapes that are water.
#
# geoBoundaries draws Guatemala's second level as 342 polygons, and Guatemala
# has 340 municipios. The other two are Lake Atitlan and Lake Amatitlan, each
# drawn as a unit of its own between the municipios on its shore: measured
# on the CGAZ polygons they are 127 and 14 km2, lying where the lakes lie.
# Nobody lives on either, so no census row can ever reach them, and left as
# ordinary units they read as two municipios whose data this map has failed
# to find -- a gap that says the wrong thing about why it is a gap.
#
# Honduras and Mozambique have one each, found by the same measurement:
# Lake Yojoa, 81 km2 and ringed by Taulabe, Santa Cruz de Yojoa, San Pedro
# Zacapa and Las Vegas; and Mozambique's part of Lake Niassa, 6,628 km2,
# bounded on land only by Lago and Chimbonila districts. None of the four
# overlaps a neighbour.
#
# Indonesia has four, the ones UN OCHA lists among the uninhabited features
# of the same boundary set that are water (its fifth, Hutan, is a forest and
# stays land). "Danau Toba" is Lake Toba, 1,107 km2, ringed by seven
# regencies with Samosir, the island in the lake, one of them. "Danau" --
# lake -- is one shape in four pieces, each lying where a lake lies: Ranau
# (124 km2), Singkarak (108), Tondano (47) and Moat (6.5). Waduk Cirata
# (56.5 km2) and Wadung Kedungombo (28.5 km2) are reservoirs. indonesia.py
# already writes each as "not collected" with OCHA's caveat; the water
# declaration settles them after every adapter has run, see
# check_water_shapes.
#
# So each is declared here, keyed by the boundary file's spelling, and
# becomes water: every field not applicable, with the reason, and drawn in
# the water colour whatever the metric. A declaration is checked like the
# shape gaps above -- the shape must be drawn, and nothing may land on it.
WATER_SHAPES: dict[str, dict[str, str]] = {
    "GTM": {
        "Lago De Atitlan": (
            "This shape is Lake Atitlan, not a municipio. geoBoundaries "
            "draws the lake as a second-order unit of its own (127 km2), "
            "between the municipios on its shore, which is why Guatemala "
            "shows 342 units against its 340 municipios. Nobody lives on "
            "it: the people around the lake are counted in those "
            "municipios, and nothing here is missing."),
        "Lago De Amatitlan": (
            "This shape is Lake Amatitlan, not a municipio. geoBoundaries "
            "draws the lake as a second-order unit of its own (14 km2), "
            "between the municipios on its shore, which is why Guatemala "
            "shows 342 units against its 340 municipios. Nobody lives on "
            "it: the people around the lake are counted in those "
            "municipios, and nothing here is missing."),
    },
    "HND": {
        "Lago de Yojoa": (
            "This shape is Lake Yojoa, not a municipio. geoBoundaries draws "
            "the lake as a second-order unit of its own (81 km2), between "
            "Taulabe, Santa Cruz de Yojoa, San Pedro Zacapa and Las Vegas on "
            "its shore. Nobody lives on it: the people around the lake are "
            "counted in those municipios, and nothing here is missing."),
    },
    "IDN": {
        "Danau Toba": (
            "This shape is Lake Toba, not a regency. geoBoundaries draws the "
            "lake as a second-order unit of its own (1,107 km2), between the "
            "regencies on its shore and around Samosir, the island in it, "
            "which is a regency of its own. UN OCHA lists it among the "
            "uninhabited features of the same boundaries. Nobody lives on "
            "the water: the "
            "people around it are counted in those regencies, and nothing "
            "here is missing."),
        "Danau": (
            "This shape is four lakes, not a regency: geoBoundaries draws "
            "them as one second-order unit named \"Danau\", lake. Its "
            "pieces lie where Lake Ranau (124 km2) and Lake Singkarak (108 "
            "km2) on Sumatra and Lake Tondano (47 km2) and Lake Moat (6.5 "
            "km2) on Sulawesi lie. Nobody lives on them: the people around "
            "each are counted in the regencies on its shore, and nothing "
            "here is missing."),
        "Waduk Cirata": (
            "This shape is the Cirata reservoir, not a regency. geoBoundaries "
            "draws it as a second-order unit of its own (56.5 km2), between "
            "Bandung Barat, Cianjur and Purwakarta. Nobody lives on it: the "
            "people around it are counted in those regencies, and nothing "
            "here is missing."),
        "Wadung Kedungombo": (
            "This shape is the Kedungombo reservoir, not a regency. "
            "geoBoundaries draws it as a second-order unit of its own (28.5 "
            "km2), between Boyolali, Grobogan and Sragen. Nobody lives on "
            "it: the people around it are counted in those regencies, and "
            "nothing here is missing."),
    },
    "MOZ": {
        "Lago Niassa": (
            "This shape is Mozambique's part of Lake Niassa (Lake Malawi), "
            "not a district. geoBoundaries draws it as a second-order unit "
            "of its own (6,628 km2), beside Lago and Chimbonila districts on "
            "its shore. Nobody lives on it: the people along the shore are "
            "counted in those districts, and nothing here is missing."),
    },
}

# Every field a unit can carry a figure in, which is every field water has none in.
UNIT_FIELDS = ("capital", "largest_settlement", "population", "median_age",
               "sex_ratio", "religion", "language", "ethnicity")


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
# It was first recorded rather than repaired, on the ground that a unit
# Uruguay does not have should not be drawn. The owner's objection of 24
# September 2026 was that most of the country then read as blank, and the
# objection holds: the ground is real, the department governs it directly,
# and a department's census count less its municipios' is the people living
# on it. So it is drawn now, one unit per department named for what it is
# (see REMAINDERS and scripts/make_remainders.py), and Uruguay's declaration
# here is gone. Tonga's stays: its islets are not a unit anyone counts.
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
    # Not found by the detector: the ground left out is five islets, 12% of
    # Torba's first-level polygon and under a point of the country, which
    # renders as sea at second-level zoom all the same. The 2020 census counts
    # 66 area councils and the boundary file draws 58 (vanuatu_census): the
    # Torres Islands (166.6E 13.1-13.4S) lie inside Torba's first-level outline
    # and in no council's; Mota, Merelava and Shefa's five undrawn councils'
    # islands lie outside every polygon, the country's own outline included
    # (8 to 54 km from it). The declared share is of the country polygon, which
    # is larger than its provinces' outlines (89.6%), so the figure measures
    # the boundary file's coastlines more than the councils; the note says
    # what the councils leave out instead. Declaring the level puts land under
    # the Torres Islands (map.js's partial-land layer, from the first level).
    #   It does more than that, and the rest is not free. A declared level is
    # taken out of every comparison of a province with its councils: no
    # province is filled from its councils (fill_parent_populations) or
    # restated as their sum (restate_encyclopaedia_parents),
    # population_disagreements writes no "divisions add up to" sentence for
    # one, and check_rollups skips the country (it reads build.json's
    # partial_levels). And mark_disputed_or_hint writes the level's note as
    # the record note of all 58 councils. Measured when it was declared,
    # nothing was hidden: Malampa, Penama, Sanma (off by one person) and Tafea
    # make their councils' sums, and Torba's and Shefa's shortfalls are said
    # by UNDRAWN_PARTS, which does not read this table. A later gap between a
    # Vanuatu province and its councils is not caught by check_rollups, and
    # must be looked for by hand.
    ("VUT", "admin2"): {
        "units": 58,
        "coverage_pct": 88.9,
        "note": "Vanuatu's second-order units are its area councils. The 2020 census "
                "counts 66 of them and the boundary file draws 58. The Torres Islands, "
                "in Torba, lie inside the province's outline but in none of its "
                "councils', so at this level they show as land with no unit on it; "
                "Mota and Merelava in Torba, and North Tongoa, Tongariki, Makimae, "
                "Nguna and Emau in Shefa, are not drawn at all. Their people are in "
                "their provinces' counts.",
    },
}

# The ground a second level leaves out, drawn as one unit per first-order
# unit (scripts/make_remainders.py writes the polygons): the label it is named
# with, and what it says it is.
REMAINDERS: dict[str, tuple[str, str]] = {
    "URY": ("outside any municipio",
            "Uruguay's municipios are constituted around population centres "
            "(Ley 18.567 of 2009), and the ground of a department that lies in "
            "none of them -- most of the department's capital among it -- is "
            "governed by the department directly. This is that ground: not a "
            "municipio, and drawn so that the department's whole territory is "
            "on the map."),
}
REMAINDERS_FILE = PROCESSED / "admin2_remainders.geojson"
# Second-order polygons the boundary file draws as the wrong number of units --
# one feature for four Bolivian provinces, two features for one -- redrawn by
# scripts/make_redrawn.py, and drawn and joined in place of what they replace.
REDRAWN_FILE = PROCESSED / "admin2_redrawn.geojson"


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

# Second-level polygons whose labels are measured against another outline.
#
# geoBoundaries CGAZ draws Namibia's constituencies in the right places and
# labels them wrongly: the polygon at Windhoek is "Eenhana", a town on the
# Angolan border; "Katutura Central" lies in Hardap, 90 km south of the city;
# seven polygons are "Luderitz". Every name join put one constituency's
# figures on another's ground, with nothing to show it -- each region's
# divisions simply summed to the wrong total. No alias can fix a shuffle, so
# each polygon is named instead by the OCHA outline it is
# (scripts/fetch_census/namibia_shapes.py), measured on every build:
#   * the polygon and one outline cover SAME_UNIT or more of each other: it is
#     that constituency, and takes its name;
#   * two or more outlines lie WHOLE_PART or more inside it, and together make
#     up WHOLE_PART of it: it is their union, named for them all, and a
#     source's rows for the parts are pooled onto it;
#   * anything else is a mixture -- a constituency and part of another -- and
#     is named for what it holds and given no figures, since none describes it.
# Measured on 24 September 2026, 96 of the 103 polygons are one constituency
# (91 at 80% or more each way), four are unions of two, and three are
# mixtures.
OUTLINE_REFERENCE: dict[str, str] = {"NAM": "nam_adm2_reference.json"}
SAME_UNIT = 0.7
WHOLE_PART = 0.9
# A sliver this small of a polygon is a drawing difference, not a part of it.
OUTLINE_SLIVER = 0.05


def relabel_from_outlines(rows: list[dict[str, Any]], iso3: str,
                          units: list[dict[str, Any]]) -> dict[str, int]:
    """Name each of a country's polygons by the reference outline it is.

    ``rows`` are read_shapes rows still carrying ``_geom``; ``units`` are the
    reference outlines as the fetcher wrote them. Each row's name is replaced,
    and ``outline`` records what the polygon was measured to be.
    """
    from shapely.geometry import shape as to_shape

    outlines = [(u, whole(to_shape(u["geometry"]))) for u in units]
    counts: dict[str, int] = defaultdict(int)
    claimed: dict[str, str] = {}
    for row in rows:
        geom = whole(row["_geom"])
        label = row["name"]
        hits = []
        for unit, outline in outlines:
            if not geom.intersects(outline):
                continue
            shared = geom.intersection(outline).area
            if shared > 0:
                hits.append((shared / geom.area, shared / outline.area, unit))
        hits.sort(key=lambda h: -h[0])
        whole_units = [h for h in hits if h[1] >= WHOLE_PART]
        if len(whole_units) >= 2 and sum(h[0] for h in whole_units) >= WHOLE_PART:
            kind, parts = "union", [h[2]["name"] for h in whole_units]
            name = ", ".join(parts[:-1]) + " and " + parts[-1]
        elif hits and hits[0][0] >= SAME_UNIT and hits[0][1] >= SAME_UNIT \
                and hits[0][2]["pcode"] not in claimed:
            kind, parts = "same", [hits[0][2]["name"]]
            name = parts[0]
            claimed[hits[0][2]["pcode"]] = row["shape_id"]
        else:
            kind = "mixed"
            held = [h for h in hits if h[0] >= OUTLINE_SLIVER]
            parts = [h[2]["name"] for h in held]
            words = [(h[2]["name"] if h[1] >= WHOLE_PART else f"part of {h[2]['name']}")
                     for h in held]
            name = (", ".join(words[:-1]) + " and " + words[-1]) if len(words) > 1 \
                else (words[0] if words else label)
            name = name[:1].upper() + name[1:]
        row["name"] = name
        row["outline"] = {"kind": kind, "parts": parts, "label": label,
                          "shares": [[h[2]["name"], round(h[0], 3), round(h[1], 3)]
                                     for h in hits[:4]]}
        counts[kind] += 1
    return dict(counts)


def outline_note(outline: dict[str, Any], source: str) -> str:
    """What a relabelled polygon is, as the measurement found it."""
    shares = "; ".join(f"{n}: {a:.0%} of this polygon, {b:.0%} of {n}"
                       for n, a, b in outline["shares"])
    return (f"geoBoundaries labels this polygon \"{outline['label']}\", which is "
            f"not where it lies; it is named here from {source}. Measured "
            f"against those outlines -- {shares} -- it is not any one "
            f"constituency, so no published figure describes it and none is "
            f"shown.")


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
    seats = seat_points() if level in ("ADM1", "ADM2") else None
    with fiona.open(path) as src:
        for feat in src:
            props = dict(feat["properties"])
            geom = shape(feat["geometry"]) if feat["geometry"] else None
            if geom is None or geom.is_empty:
                continue
            point = geom.representative_point()
            bounds = geom.bounds
            name = respell(repair((props.get("shapeName") or "").strip()),
                           props.get("shapeGroup"))
            row = {
                "shape_id": props.get("shapeID") or props.get("shapeGroup"),
                "name": name,
                "group": props.get("shapeGroup"),
                "point": [round(point.x, 5), round(point.y, 5)],
                "bbox": [round(b, 4) for b in bounds],
                "_geom": (geom if level != "ADM2"
                          or props.get("shapeGroup") in OUTLINE_REFERENCE else None),
                "area": geom.area,
            }
            # While the polygon is in hand: the second level's is not kept.
            seat = seat_drawn_for(geom, row["group"], name, seats) if seats else None
            if seat:
                row["_seat"] = seat
            out.append(row)
    log(f"  {level}: {len(out)} shapes")
    if level == "ADM2":
        for iso3, filename in OUTLINE_REFERENCE.items():
            reference = read_json(PROCESSED / filename, None)
            if not reference or not reference.get("units"):
                raise SystemExit(
                    f"build_entities: {iso3}'s second-level labels are declared "
                    f"wrong and are named from {filename}, which is missing. "
                    f"Run: python -m scripts.fetch_census.namibia_shapes")
            rows = [r for r in out if r["group"] == iso3]
            counts = relabel_from_outlines(rows, iso3, reference["units"])
            for r in rows:
                r["outline"]["source"] = reference.get("source")
                r["_geom"] = None
            log(f"  {iso3}: {len(rows)} polygons named from {filename}: "
                + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())))
    return out


def read_remainders() -> list[dict[str, Any]]:
    """The second-order units drawn for the ground a country's second level leaves out.

    Each carries its first-order parent already, so the geometry pass that
    works out every other unit's parent is not asked about it.
    """
    from shapely.geometry import shape

    if not REMAINDERS:
        return []
    collection = read_json(REMAINDERS_FILE, None)
    if not collection:
        raise SystemExit(f"build_entities: {REMAINDERS_FILE.name} is missing; "
                         f"run: python3 scripts/make_remainders.py")
    out = []
    for feat in collection.get("features", []):
        props = feat["properties"]
        geom = shape(feat["geometry"])
        point = geom.representative_point()
        out.append({
            "shape_id": props["shapeID"], "name": props["shapeName"],
            "group": props["shapeGroup"], "parent_shape": props["parentID"],
            "point": [round(point.x, 5), round(point.y, 5)],
            "bbox": [round(b, 4) for b in geom.bounds], "_geom": None,
            "area": geom.area, "remainder": True,
        })
    return out


def read_redrawn() -> tuple[set[str], list[dict[str, Any]]]:
    """The redrawn second-order units, and the boundary file's ids they replace.

    Each carries its first-order parent already, measured when it was drawn,
    and says what was redrawn and why, which the unit shows as its note.
    """
    from shapely.geometry import shape

    collection = read_json(REDRAWN_FILE, None)
    if not collection:
        return set(), []
    replaced: set[str] = set()
    out = []
    for feat in collection.get("features", []):
        props = feat["properties"]
        geom = shape(feat["geometry"])
        point = geom.representative_point()
        replaced.update(props.get("replaces") or [])
        out.append({
            "shape_id": props["shapeID"], "name": props["shapeName"],
            "group": props["shapeGroup"], "parent_shape": props["parentID"],
            "point": [round(point.x, 5), round(point.y, 5)],
            "bbox": [round(b, 4) for b in geom.bounds], "_geom": None,
            "area": geom.area, "redrawn": props.get("redrawn"),
        })
    return replaced, out


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


# Countries whose boundary file draws a second level that is not inside its
# first, so that no first-level unit is the parent of any second-level one:
# {country: what the two levels are}. Each second-level unit falls back to the
# country, which is true, rather than to the one first-level unit it is most
# inside, which is not its parent.
#   SYC  The first level is the 26 districts; the second is the eight regions
#        OCHA's population table counts (Central 1 Mahe, Central 2 Mahe, East,
#        North and West Mahe, Praslin, La Digue and Other Islands), each made
#        of several districts. By area each region went to the one district it
#        is most inside: East Mahe's 22,414 people sat under Takamaka's 2,850,
#        and Takamaka's "divisions" came to 7.9 times its own count.
NOT_NESTED: dict[str, str] = {
    "SYC": "Seychelles' second level is its eight regions, each of several of the 26 "
           "districts that make its first level",
}

# Second-level polygons with no first-level parent on the map, though their
# country's levels nest: {shapeID: (ISO3, why)}. Belgium's "Brussels" is the
# whole Brussels-Capital Region (162 km2), and the first-level polygon labelled
# Brussels Hoofdstedelijk is 70.6 km2 of it, the rest drawn inside Flanders'
# outline; the region's figures stand on this polygon and none on the
# first-level one (NOT_THIS_GROUND). By area it sat under Flanders, whose drawn
# provinces then came to 8,155,980 against its 6,884,271; filed under the half
# polygon instead, the roll-ups would put the whole region's figures back on
# ground they were refused for. So it is filed under neither, and falls back to
# the country: Flanders' five provinces make Flanders.
UNPARENTED: dict[str, tuple[str, str]] = {
    "21686613B18913386279163": (
        "BEL", "the whole Brussels-Capital Region, whose first-level polygon is drawn as "
               "half of it"),
}


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
    unnested = 0
    for row in adm2:
        entry = trees.get(row["group"])
        row["parent_shape"] = None
        if row["group"] in NOT_NESTED or row.get("shape_id") in UNPARENTED:
            # A second level that is not inside the first has no parent in
            # it, nor does a unit drawn across a first-level polygon that is
            # part of it: the unit falls back to the country (NOT_NESTED,
            # UNPARENTED).
            unnested += 1
            continue
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
    if unnested:
        log(f"  {unnested} units left under their country, the first level drawn round "
            f"none of them (NOT_NESTED: {', '.join(sorted(NOT_NESTED))}; UNPARENTED: "
            f"{', '.join(sorted({iso3 for iso3, _ in UNPARENTED.values()}))})")
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


# Second-level polygons whose first-level unit the geometry cannot give,
# declared with the unit the census files them under:
# {shapeID: (ISO3, the first-level unit's name as the boundary file labels it)}.
# Geometry stays the rule (see link_adm2_parents); this is for a polygon that
# meets no first-level one, or that the boundary file's coarser first level
# puts mostly inside a neighbour, each entry with the count that shows it.
#
# The parent is not decoration. It is what a first-level unit's sum is taken
# over, so a child filed elsewhere is a child that sum leaves out: Kinmen's five
# drawn townships added up to 136,611 against the county's registered 137,208,
# and the sum replaced the count.
DECLARED_PARENTS: dict[str, tuple[str, str]] = {
    # Wuqiu township lies off the Fujian coast, about a degree from both Kinmen
    # and the Matsu Islands, and its polygon meets no first-level one. The
    # household register files it under Kinmen County: its register code
    # 09020060 is Kinmen's (09020), its register name 金門縣烏坵鄉, and
    # Kinmen's 137,208 registered people are its six townships' to the person,
    # Wuqiu's 597 included (taiwan_township, taiwan_county).
    "52511910B62500214534323": ("TWN", "Kinmen"),
    # Kiribati is deliberately absent. The polygon CGAZ labels the Phoenix
    # Islands also draws Tarawa and Banaba, which the census counts in the
    # Gilbert group; kiribati_census gives each island-group polygon the
    # islands it draws ('Tarawa, Banaba and the Phoenix Islands', 'Gilbert
    # Islands except Tarawa and Banaba') and stops if the map files those
    # islands anywhere but where they are drawn, which is where geometry puts
    # them.
    # Viet Nam's first level is drawn coarser than its districts, so by area
    # An Duong and An Lao (Hai Phong's) and Dong Trieu (Quang Ninh's) sat in
    # Hai Duong, whose 13 drawn children added up to 2,149,590 against its
    # census 1,892,254; Son Tay (Quang Ngai's) sat in Kon Tum and Ba Vi (Ha
    # Noi's) in Phu Tho, and five island districts met no province at all.
    # Each is filed under the province whose districts the General Statistics
    # Office's 2019 table counts it among (vietnam_district.json's ids); with
    # all 27 so filed, every one of the 19 provinces they touch adds up to its
    # census population exactly, where by area they ran from 66% (Bac Giang)
    # to 127% (Phu Tho).
    "81297802B90799057915407": ("VNM", "Bình Thuận"),  # Phu Quy; by area in no province
    "81297802B61782089337393": ("VNM", "Bắc Giang"),  # Hiep Hoa; by area in Hà Nội
    "81297802B30186135932553": ("VNM", "Bắc Giang"),  # Viet Yen; by area in Bắc Ninh
    "81297802B99638089462809": ("VNM", "Bắc Giang"),  # Yen Dung; by area in Bắc Ninh
    "81297802B85996690558528": ("VNM", "Bắc Ninh"),  # Tu Son; by area in Hà Nội
    "81297802B94958861355476": ("VNM", "Hà Nội"),  # Ba Vi; by area in Phú Thọ
    "81297802B91668671895601": ("VNM", "Hà Nội"),  # Me Linh; by area in Vĩnh Phúc
    "81297802B48632704069528": ("VNM", "Hà Nội"),  # My Duc; by area in Hòa Bình
    "81297802B83594447255": ("VNM", "Hưng Yên"),  # Hung Yen; by area in Hà Nam
    "81297802B59998896925567": ("VNM", "Hưng Yên"),  # Khoai Chau; by area in Hà Nội
    "81297802B33082020704537": ("VNM", "Hưng Yên"),  # Van Giang; by area in Hà Nội
    "81297802B56696175700764": ("VNM", "Hải Dương"),  # Binh Giang; by area in Hưng Yên
    "81297802B67689154766571": ("VNM", "Hải Dương"),  # Thanh Mien; by area in Hưng Yên
    "81297802B31270346353021": ("VNM", "Hải Phòng"),  # An Duong; by area in Hải Dương
    "81297802B65658789050233": ("VNM", "Hải Phòng"),  # An Lao; by area in Hải Dương
    "81297802B40834484476285": ("VNM", "Hải Phòng"),  # Bach Long Vi; by area in no province
    "81297802B83209776142835": ("VNM", "Hậu Giang"),  # Chau Thanh; by area in Cần Thơ
    "81297802B94036559538482": ("VNM", "Hậu Giang"),  # Chau Thanh A; by area in Cần Thơ
    "81297802B10550571931229": ("VNM", "Kiên Giang"),  # Kien Hai; by area in no province
    "81297802B63810165613250": ("VNM", "Quảng Ngãi"),  # Ly Son; by area in no province
    "81297802B56181672233009": ("VNM", "Quảng Ngãi"),  # Son Tay; by area in Kon Tum
    "81297802B76384767601248": ("VNM", "Quảng Ninh"),  # Co To; by area in no province
    "81297802B3249391660958": ("VNM", "Quảng Ninh"),  # Dong Trieu; by area in Hải Dương
    "81297802B38356347526872": ("VNM", "Quảng Ninh"),  # Quang Yen; by area in Hải Phòng
    "81297802B99897160628736": ("VNM", "Thái Bình"),  # Vu Thu; by area in Nam Định
    "81297802B72352297629850": ("VNM", "Vĩnh Phúc"),  # Song Lo; by area in Phú Thọ
    "81297802B74371944720443": ("VNM", "Vĩnh Phúc"),  # Vinh Tuong; by area in Hà Nội
    # Timor-Leste: the 2022 census counts Dom Aleixo (165,799) in Dili and
    # Zumalai in Cova Lima; by area they fell in Liquica, whose four drawn
    # children came to 249,457 against its 83,658, and in Ainaro. Filed as
    # counted, Dili, Liquica, Ainaro and Cova Lima each add up to their census
    # populations (timor_age).
    "22284137B34351426942246": ("TLS", "Dili"),  # Dom Aleixo; by area in Liquiçá
    "22284137B47375840688188": ("TLS", "Cova Lima"),  # Zumalai; by area in Ainaro
    # Samoa: the 2021 census counts Vaisigano East (Vaisigano No. 1: Auala,
    # Matavai (Asau), Utuloa and Vaisala) in Vaisigano. Its polygon reaches
    # inland, so by area it is 56% in Gaga'ifomauga, whose drawn children then
    # came to 6,896 against its census 4,797 and Vaisigano's to 4,658 against
    # 6,757. Filed as counted, both add up to their census populations
    # (samoa_census).
    "51752279B16736708134398": ("WSM", "Vaisigano"),  # Vaisigano East; by area in Gaga'ifomauga
    # Solomon Islands: the 2019 census counts West Honiara (wards Nggossi,
    # Mbumburu and Rove/Lengakiki) in Honiara. The boundary file draws the
    # Capital Territory narrow, so by area 76% of West Honiara lies in
    # Guadalcanal, whose drawn constituencies then came to 190,081 against its
    # census 154,022 and Honiara's to 93,510 against 129,569. Three island
    # constituencies meet no province at all. Filed as counted, Honiara,
    # Guadalcanal, Western, Malaita and Makira each add up to their census
    # populations (solomon_census); Temotu is short only Temotu Pele, which
    # has no polygon.
    "97153195B79685360325521": ("SLB", "Capital Territory (Honiara)"),  # West Honiara; by area in Guadalcanal
    "97153195B5229435776265": ("SLB", "Western"),  # Ranongga-Simbo; by area in no province
    "97153195B283418478941": ("SLB", "Malaita"),  # Malaita Outer Island; by area in no province
    "97153195B5813678005448": ("SLB", "Makira"),  # Ulawa-Ugi; by area in no province
    # South Korea: the boundary file draws the metropolitan cities small, and
    # seventeen districts fall inside a neighbouring province's polygon or
    # outside every province's. Gwangju's drawn children came to 426,867
    # against its 1,444,585 registered people, with four of its five districts
    # under South Jeolla (2,778,927 against 1,853,327); Incheon's to 0.67 of
    # it and Gyeonggi's to 1.10. The resident register files each of them
    # under its own province (korea_nationality's DRAWN_ELSEWHERE); filed so,
    # every province adds up to its registered population exactly, South
    # Jeolla short only Yeonggwang-gun, which has no polygon. Gunwi-gun is
    # Daegu's since July 2023, which is the register this follows.
    "91817680B53616587081026": ("KOR", "Seoul"),  # Eunpyeong-gu; in Gyeonggi's polygon
    "91817680B73279111808647": ("KOR", "Incheon"),  # Seo-gu [West District]; in Gyeonggi's polygon
    "91817680B94833670639499": ("KOR", "Incheon"),  # Gyeyang-gu; in Gyeonggi's polygon
    "91817680B24929628173287": ("KOR", "Incheon"),  # Ganghwa-gun; in Gyeonggi's polygon
    "91817680B43125449030549": ("KOR", "Incheon"),  # Ongjin-gun; in no province
    "91817680B91211823266814": ("KOR", "Busan"),  # Gangseo-gu; in South Gyeongsang's polygon
    "91817680B54012703126739": ("KOR", "Busan"),  # Gijang-gun; in South Gyeongsang's polygon
    "91817680B63526671374694": ("KOR", "Busan"),  # Yeongdo-gu; in no province
    "91817680B33489673734556": ("KOR", "Daegu"),  # Dalseong-gun; in North Gyeongsang's polygon
    "91817680B30315657457409": ("KOR", "Daegu"),  # Gunwi-gun; in North Gyeongsang's polygon
    "91817680B89733153975870": ("KOR", "Gwangju"),  # Dong-gu [East District]; in South Jeolla's polygon
    "91817680B87996420220515": ("KOR", "Gwangju"),  # Seo-gu [West District]; in South Jeolla's polygon
    "91817680B68494559899558": ("KOR", "Gwangju"),  # Nam-gu [South District]; in South Jeolla's polygon
    "91817680B16538338684661": ("KOR", "Gwangju"),  # Gwangsan-gu; in South Jeolla's polygon
    "91817680B53543824194985": ("KOR", "Daejeon"),  # Dong-gu; in North Chungcheong's polygon
    "91817680B88731995383072": ("KOR", "North Gyeongsang"),  # Uljin-gun; in Gangwon's polygon
    "91817680B46467557111645": ("KOR", "South Jeolla"),  # Sinan-gun; in no province
    # Bhutan: the boundary file's dzongkhags and gewogs are not one partition,
    # and by area 17 of the 205 gewogs fell in a neighbouring dzongkhag --
    # Punakha's Goenshari, Kabjisa, Talo and Toepisa in Thimpu, whose own
    # Mewang and Soe fell in Paro, so Thimpu's drawn gewogs came to 23,072
    # with four of them Punakha's. The 2017 census prints each gewog in its
    # dzongkhag's own report (bhutan_gewog's parent_name), and filed so, every
    # dzongkhag's gewogs add up to its Table 2.1 count less the towns it counts
    # beside them, to the person (Thimpu's eight 23,219, Punakha's eleven
    # 21,694, Pemagatshel's eleven 16,007), which is what each dzongkhag's
    # note says.
    "84629894B72045307811039": ("BTN", "Thimpu"),  # Mewang; by area in Paro
    "84629894B34921780137315": ("BTN", "Thimpu"),  # Soe; by area in Paro
    "84629894B19712913086843": ("BTN", "Punakha"),  # Goenshari; by area in Thimpu
    "84629894B81369433275324": ("BTN", "Punakha"),  # Kabjisa; by area in Thimpu
    "84629894B89675802182154": ("BTN", "Punakha"),  # Talo; by area in Thimpu
    "84629894B31491158844122": ("BTN", "Punakha"),  # Toepisa; by area in Thimpu
    "84629894B48304633314853": ("BTN", "Punakha"),  # Bapisa (Barp); by area in Wangdue Phodrang
    "84629894B81792888214428": ("BTN", "Pemagatshel"),  # Chhimung; by area in Mongar
    "84629894B57619855084660": ("BTN", "Pemagatshel"),  # Chokhorling; by area in Samdrup Jongkhar
    "84629894B76488101752434": ("BTN", "Pemagatshel"),  # Dechhenling; by area in Samdrup Jongkhar
    "84629894B84199937092772": ("BTN", "Pemagatshel"),  # Norboogang; by area in Samdrup Jongkhar
    "84629894B55544402274944": ("BTN", "Pemagatshel"),  # Nanong; by area in Trashigang
    "84629894B7815238118708": ("BTN", "Samdrup Jongkhar"),  # Gomdar; by area in Trashigang
    "84629894B93354039766562": ("BTN", "Trashigang"),  # Bartsham; by area in Trashiyangtse
    "84629894B1832791956678": ("BTN", "Samtse"),  # Denchhukha; by area in Haa
    "84629894B38821780913292": ("BTN", "Dagana"),  # Lhamoizingkha; by area in Sarpang
    "84629894B33123696098059": ("BTN", "Dagana"),  # Nichula; by area in Sarpang
    # Saudi Arabia: Sharurah governorate is Najran Region's; its polygon lies
    # 50.8% in the Eastern Region's and 49.2% in Najran's, so by area it sat
    # under the Eastern Region and Najran's drawn governorates came to 415,660.
    "3984122B36425593132698": ("SAU", "Najran Region"),  # Sharurah; by area in Eastern Region
    # Uzbekistan: the statistics agency counts Bektemir, Sergeli and Uchtepa
    # in Tashkent city (SIAT codes 1726264, 1726283 with Yangikhayot's
    # 1726292, and 1726262); the boundary file draws the city small, and by
    # area they lay 95.8%, 59.5% and 52.6% in Tashkent Region. Filed under the
    # city, its eleven districts come to 3,178,100 against the census's
    # 3,224,838, the agency's count of 1 January against the census's of 15
    # January.
    "79887680B40109116454398": ("UZB", "Tashkent"),  # Bektemir; by area in Tashkent Region
    "79887680B58716268454454": ("UZB", "Tashkent"),  # Sergeli; by area in Tashkent Region
    "79887680B78178339313098": ("UZB", "Tashkent"),  # Uchtepa; by area in Tashkent Region
    # Iraq: COSIT's 2024 census (Table 11/2) and OCHA's gazetteer count
    # Al-Hindiya in Kerbala and Al-Mahmoudiya, Al-Kadhmiyah and Al-Mada'in in
    # Baghdad, whose first-level polygon the boundary file draws small. By area
    # they lay in Babil (69.0% and 91.9%), Salah al-Din (32.9%, as much as in
    # Al-Anbar) and Diyala (80.6%), and Babil's drawn districts came to
    # 2,834,827 against its 2,482,324. Filed as counted, Babil, Kerbala, Diyala
    # and Salah al-Din each add up to their census counts (iraq_census).
    "34846034B69940766405797": ("IRQ", "Karbala"),  # Al-Hindiya; by area in Babil
    "34846034B92813694057989": ("IRQ", "Baghdad"),  # Al-Mahmoudiya; by area in Babil
    "34846034B5863384083959": ("IRQ", "Baghdad"),  # Al-Kadhmiyah; by area in Salah al-Din
    "34846034B77650308075556": ("IRQ", "Baghdad"),  # Al-Mada'in; by area in Diyala
    # Argentina: INDEC's 2022 census counts ten Greater Buenos Aires partidos
    # in Buenos Aires province, Juan Bautista Alberdi and Tafí del Valle in
    # Tucumán and Rivadavia in Santiago del Estero; by area they lay in the
    # capital, Catamarca and Córdoba, and Comuna 1 meets no first-level polygon
    # at all. The capital's drawn children came to 6,147,121 against its
    # 3,121,707; filed as counted, the capital, Tucumán, Catamarca, Córdoba and
    # Santiago del Estero each add up to their census counts
    # (argentina_census). Entre Ríos has no polygon at the first level, and its
    # departments stay under Buenos Aires, whose polygon draws both provinces.
    "61730980B497821979952": ("ARG", "Buenos Aires"),  # Avellaneda; by area in the capital
    "61730980B46018574851610": ("ARG", "Buenos Aires"),  # General San Martín; by area in the capital
    "61730980B67082136706980": ("ARG", "Buenos Aires"),  # Hurlingham; by area in the capital
    "61730980B5073290621442": ("ARG", "Buenos Aires"),  # Ituzaingó; by area in the capital
    "61730980B82567739160952": ("ARG", "Buenos Aires"),  # Lanús; by area in the capital
    "61730980B30318397352263": ("ARG", "Buenos Aires"),  # Morón; by area in the capital
    "61730980B51340579014160": ("ARG", "Buenos Aires"),  # San Isidro; by area in the capital
    "61730980B42310570317073": ("ARG", "Buenos Aires"),  # San Miguel; by area in the capital
    "61730980B88678124443771": ("ARG", "Buenos Aires"),  # Tres de Febrero; by area in the capital
    "61730980B14767108287685": ("ARG", "Buenos Aires"),  # Vicente López; by area in the capital
    "61730980B33319795319357": ("ARG", "Ciudad Autónoma de Buenos Aires"),  # Comuna 1; in no province
    "61730980B38664240857483": ("ARG", "Tucumán"),  # Juan Bautista Alberdi; by area in Catamarca
    "61730980B13889034691247": ("ARG", "Tucumán"),  # Tafí del Valle; by area in Catamarca
    "61730980B21057051979490": ("ARG", "Santiago del Estero"),  # Rivadavia; by area in Córdoba
    # Belgium's "Brussels", by area in Flanders, is UNPARENTED instead.
    # Malawi: Mangochi is a Southern Region district (OCHA's cod-ps-mwi); its
    # polygon takes in the south of Lake Malawi, and by area 76.7% of it lay
    # in the Northern Region's.
    "42251766B89682559169951": ("MWI", "Southern Region"),  # Mangochi; by area in Northern Region
    # Madagascar: Vohipeno is Vatovavy-Fitovinany's (OCHA's cod-ps-mdg);
    # by area 91.2% of it lay in Atsimo-Atsinanana.
    "10022922B81120329184352": ("MDG", "Vatovavy-Fitovinany"),  # Vohipeno; by area in Atsimo-Atsinanana
    # Namibia: the constituency measured as Mukwe (labelled "Arandis" in the
    # boundary file) is Kavango East's (OCHA's cod-ps-nam); the boundary file
    # draws Kavango whole, and by area 96.7% of Mukwe lay in Caprivi's polygon.
    "8085530B20929283489058": ("NAM", "Kavango"),  # Mukwe; by area in Caprivi
    # The Dominican Republic: the 2022 census counts the Distrito Nacional
    # municipio in the Distrito Nacional, Bajos de Haina in San Cristóbal, Las
    # Salinas in Barahona, Arenoso in Duarte and Sabana Iglesia in Santiago;
    # by area they lay in Santo Domingo (62.9% and 51.5%), Independencia,
    # Samaná and La Vega. Filed as counted, every province's municipios make
    # its census count (dominican_census).
    "3306468B63097535879723": ("DOM", "Distrito Nacional"),  # Distrito Nacional; by area in Santo Domingo
    "3306468B44390196227357": ("DOM", "San Cristóbal"),  # Bajos de Haina; by area in Santo Domingo
    "3306468B53490324555446": ("DOM", "Barahona"),  # Las Salinas; by area in Independencia
    "3306468B79017025460716": ("DOM", "Duarte"),  # Arenoso; by area in Samaná
    "3306468B1703224271200": ("DOM", "Santiago"),  # Sabana Iglesia; by area in La Vega
    # Suriname: the 2012 census counts Kwatta in Wanica and Pontbuiten and Weg
    # naar Zee in Paramaribo; by area they lay in Saramacca (94.8%) and
    # Wanica (100% and 46.3%). Filed as counted, Wanica and Saramacca add up to
    # their census counts; Paramaribo is short only the four ressorts the
    # boundary file does not draw (UNDRAWN_PARTS).
    "93971198B97783973915980": ("SUR", "Wanica"),  # Kwatta; by area in Saramacca
    "93971198B33771230340661": ("SUR", "Paramaribo"),  # Pontbuiten; by area in Wanica
    "93971198B55832706288336": ("SUR", "Paramaribo"),  # Weg naar Zee; by area in Wanica
    # The Bahamas: the second level draws each district again, and two of
    # them by area under a neighbour -- Spanish Wells under Harbour Island
    # (66.2%), the City of Freeport under West Grand Bahama (79.6%). Each is
    # its first-level namesake's ground; Spanish Wells' 1,551 people (2010
    # census) are that district's, not Harbour Island's.
    "86173395B84342245076332": ("BHS", "Spanish Wells"),  # Spanish Wells; by area in Harbour Island
    "86173395B95713051783720": ("BHS", "City of Freeport"),  # City of Freeport; by area in West Grand Bahama
    # Portugal: INE's districts are their municipalities (the first two digits
    # of the municipality code), and five are drawn mostly inside another
    # district's outline: Espinho (Aveiro's) and Mesão Frio (Vila Real's) in
    # Porto's, Tábua (Coimbra's) in Viseu's, Oliveira de Frades (Viseu's) in
    # Aveiro's and Sardoal (Santarém's) in Castelo Branco's. Filed as INE
    # counts them, every district's municipalities make its census count
    # (portugal_census).
    "2272694B58845957130361": ("PRT", "AVEIRO"),  # Espinho; by area in Porto
    "2272694B97180634547799": ("PRT", "COIMBRA"),  # Tábua; by area in Viseu
    "2272694B62092960833864": ("PRT", "SANTARÉM"),  # Sardoal; by area in Castelo Branco
    "2272694B2878786593857": ("PRT", "VILA REAL"),  # Mesão Frio; by area in Porto
    "2272694B21944289016738": ("PRT", "VISEU"),  # Oliveira de Frades; by area in Aveiro
    # Slovenia: the boundary file's two cohesion regions are drawn on another
    # line than NUTS's, so by area Primorsko-notranjska's six municipalities
    # and Sodražica (SI03, Vzhodna) sat in Zahodna Slovenija, seven of
    # Osrednjeslovenska's and Gorenjska's (SI04, Zahodna) in Vzhodna, and Brda
    # in neither; Zahodna's 63 drawn children added up to 998,322 against
    # Eurostat's 1,017,119. Each is filed in the region whose NUTS 3 unit holds
    # 86% or more of its polygon (Eurostat's NUTS 2024 boundaries).
    "79292919B39846175999715": ("SVN", "Zahodna Slovenija"),  # Brda; by area in neither
    "79292919B28618537144130": ("SVN", "Zahodna Slovenija"),  # Kamnik; by area in Vzhodna
    "79292919B10853611876799": ("SVN", "Zahodna Slovenija"),  # Dol pri Ljubljani; in Vzhodna
    "79292919B38910398749783": ("SVN", "Zahodna Slovenija"),  # Lukovica; by area in Vzhodna
    "79292919B87990706062865": ("SVN", "Zahodna Slovenija"),  # Moravče; by area in Vzhodna
    "79292919B41680562738857": ("SVN", "Zahodna Slovenija"),  # Šmartno pri Litiji; Vzhodna
    "79292919B27778695189905": ("SVN", "Zahodna Slovenija"),  # Ivančna Gorica; in Vzhodna
    "79292919B51302363560812": ("SVN", "Zahodna Slovenija"),  # Jezersko; by area in Vzhodna
    "79292919B88661184998894": ("SVN", "Vzhodna"),  # Sodražica; by area in Zahodna
    "79292919B86153234432481": ("SVN", "Vzhodna"),  # Loška dolina; by area in Zahodna
    "79292919B32570371692046": ("SVN", "Vzhodna"),  # Ilirska Bistrica; by area in Zahodna
    "79292919B70479288725933": ("SVN", "Vzhodna"),  # Pivka; by area in Zahodna
    "79292919B30079585867882": ("SVN", "Vzhodna"),  # Postojna; by area in Zahodna
    "79292919B19554174708410": ("SVN", "Vzhodna"),  # Bloke; by area in Zahodna
    "79292919B16697278472922": ("SVN", "Vzhodna"),  # Cerknica; by area in Zahodna
}


# First-level units whose own count takes in second-level units the boundary
# file draws no polygon for, so their drawn divisions cannot add up to it.
# (country, first-level label) -> the undrawn unit's name, or, where there are
# several, (what they are, their names). The note says so, with what the drawn
# divisions add up to and what that leaves -- a difference, which is the
# undrawn units' people only where the count and its divisions are of one year
# (note_undrawn_parts stops the build where they are not).
#   FSM  The boundary file draws ten of Yap's 20 municipalities and seven of
#        Pohnpei's 11; Elato and Sapwuahfik are inside the country's outline
#        but in no state or municipality, the rest in no polygon at all. The
#        2023 census's state basic tables count every one (micronesia_census);
#        their municipalities' rows differ from the state's by up to three
#        people, so the difference is the undrawn ones' to within that.
#        Chuuk is not here: its municipalities' latest counts are 2010's,
#        under a 2023 state count, and micronesia_census says so on the state.
#   VUT  The 2020 census's Table 1.1 counts 66 area councils and the boundary
#        file draws 58 (vanuatu_census's UNDRAWN): Torres, Mota and Merelava
#        are Torba's, the Torres Islands inside Torba's first-level outline
#        and the other two in no polygon; North Tongoa, Tongariki, Makimae,
#        Nguna and Emau are Shefa's islands, in no polygon.
#   SUR  The 2012 census counts Beekhuizen, Latour, Tammenga and Welgelegen
#        in Paramaribo (suriname_census); the boundary file draws none of them.
# Senegal's Dakar is not here although Keur Massar department, made in 2021,
# has no polygon: its ground is drawn, inside the outlines Pikine and Rufisque
# had before it was cut from them, so it is not missing ground, and the
# difference would not be its people either -- the RGPH-5 counts Keur Massar
# at 770,314 (ANSD's 2023-2050 projections workbook, base year), where Dakar's
# figure less its drawn departments' leaves 668,496.
UNDRAWN_PARTS: dict[tuple[str, str], str | tuple[str, tuple[str, ...]]] = {
    ("KOR", "South Jeolla"): "Yeonggwang-gun",
    ("SLB", "Temotu"): "Temotu Pele",
    ("FSM", "Yap"): ("municipalities", ("Rumung", "Ulithi", "Fais", "Ngulu", "Eauripik",
                                        "Ifalik", "Faraulep", "Elato", "Lamotrek",
                                        "Satawal")),
    ("FSM", "Pohnpei"): ("municipalities", ("Mwoakilloa", "Sapwuahfik", "Nukuoro",
                                            "Kapingamarangi")),
    ("VUT", "Torba"): ("area councils", ("Torres", "Mota", "Merelava")),
    ("VUT", "Shefa Province"): ("area councils", ("North Tongoa", "Tongariki", "Makimae",
                                                  "Nguna", "Emau")),
    ("SUR", "Paramaribo"): ("ressorts", ("Beekhuizen", "Latour", "Tammenga", "Welgelegen")),
}


def listed(names: Sequence[str]) -> str:
    """Names as a sentence lists them: "a", "a and b", "a, b and c"."""
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def undrawn_sentence(part: str | tuple[str, tuple[str, ...]], kids: int, drawn: float,
                     own: float) -> str:
    """The note's sentence for one UNDRAWN_PARTS entry."""
    rest = f"{own - drawn:,.0f}"
    if isinstance(part, str):
        return (f"This count takes in {part}, which the map does not draw as a unit of "
                f"its own: the {kids} divisions drawn here add up to {drawn:,.0f}, which "
                f"leaves {rest} for {part}.")
    kind, names = part
    return (f"This count takes in {len(names)} {kind} the map does not draw as units of "
            f"their own: {listed(names)}. The {kids} divisions drawn here add up to "
            f"{drawn:,.0f}, which leaves {rest} for those {len(names)}.")


def note_undrawn_parts(admin1: dict[str, list[dict[str, Any]]],
                       admin2: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Say where a first-level count takes in units the map does not draw.

    DECLARED_PARENTS files every Korean, Samoan and Solomon second-level
    polygon under the unit that counts it, and each first-level unit then adds
    up to its own count -- but two: South Jeolla is 52,871 more than its drawn
    counties, Yeonggwang-gun having no polygon, and Temotu 5,395 more than its
    drawn constituencies, Temotu Pele having none. That was said only in a
    comment. Run once the populations are final; a note already there is kept
    and this follows it, and nothing is said where a division has no
    population or the drawn ones do not fall short.

    The difference is the undrawn units' people only when the count and the
    divisions are of one year: Chuuk's 33,885 of 2023 less its drawn
    municipalities' 26,553 of 2010 would put 7,332 people on thirty
    municipalities that held 22,101 in 2010. So the build stops where an
    entry's unit and its divisions carry different years, or the divisions no
    one year between them: the sentence would state a difference of two
    counts as a number of people.
    """
    said = []
    for (iso3, name), part in sorted(UNDRAWN_PARTS.items()):
        if not admin1.get(iso3):
            # A run that draws nothing of the country (a caller passing some
            # countries' units) is not one this entry is about; a country that
            # is drawn and has lost the unit is, and stops below.
            continue
        units = [e for e in admin1.get(iso3, [])
                 if name in (e.get("name"), e.get("shape_name"))]
        if len(units) != 1:
            raise SystemExit(f"UNDRAWN_PARTS: {iso3} draws {len(units)} first-level "
                             f"units named {name!r}")
        unit = units[0]
        own = published(unit.get("population"))
        children = [e for e in admin2.get(iso3, [])
                    if e.get("parent") == unit["id"] and not e.get("water")]
        kids = [published(e.get("population")) for e in children]
        if own is None or not kids or None in kids:
            continue
        drawn = sum(kids)
        if drawn >= own:
            continue
        years = {vintage(e.get("population")) for e in children}
        year = vintage(unit.get("population"))
        if len(years) != 1 or years != {year}:
            shown = ", ".join(str(y) for y in sorted(years, key=str))
            raise SystemExit(
                f"UNDRAWN_PARTS: {iso3} {name}'s count is for {year}, and its divisions' "
                f"figures for {shown}; the difference between them is not the undrawn "
                f"units' people, so the note would be false. Say why the two differ in "
                f"the unit's own note instead, and take the entry out.")
        sentence = undrawn_sentence(part, len(kids), drawn, own)
        held = unit.get("population_note")
        unit["population_note"] = f"{held} {sentence}" if held else sentence
        what = part if isinstance(part, str) else listed(part[1])
        said.append(f"{iso3} {name}: {what} {own - drawn:,.0f}")
    return said


def declare_parents(adm1: list[dict[str, Any]], adm2: list[dict[str, Any]],
                    declared: dict[str, tuple[str, str]] | None = None) -> list[str]:
    """Give the declared second-level polygons the first-level unit they belong to.

    A declaration names its unit by the boundary file's label, so it reads as
    what it claims; the label must name exactly one first-level shape of that
    country, and the polygon must be drawn in it. Either failing stops the
    build: a stale declaration would file a district under nothing, or under
    a namesake, and say nothing.
    """
    declared = DECLARED_PARENTS if declared is None else declared
    by_name: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in adm1:
        by_name[(row["group"], row["name"])].append(row)
    seen: set[str] = set()
    done: list[str] = []
    for row in adm2:
        wanted = declared.get(row.get("shape_id") or "")
        if wanted is None:
            continue
        iso3, name = wanted
        if row["group"] != iso3:
            raise SystemExit(
                f"DECLARED_PARENTS: {row['shape_id']} ({row['name']}) is drawn in "
                f"{row['group']}, not {iso3}")
        if iso3 in NOT_NESTED or row["shape_id"] in UNPARENTED:
            raise SystemExit(
                f"DECLARED_PARENTS: {row['shape_id']} ({row['name']}) is declared under "
                f"{name!r}, and also as having no first-level parent (NOT_NESTED, "
                f"UNPARENTED)")
        found = by_name.get((iso3, name), [])
        if len(found) != 1:
            raise SystemExit(
                f"DECLARED_PARENTS: {iso3} draws {len(found)} first-level shapes "
                f"labelled {name!r}, where {row['name']} needs exactly one")
        was = row.get("parent_shape")
        row["parent_shape"] = found[0]["shape_id"]
        seen.add(row["shape_id"])
        if was != row["parent_shape"]:
            done.append(f"{row['name']} ({iso3}) under {name}")
    missing = sorted(set(declared) - seen)
    if missing:
        raise SystemExit(f"DECLARED_PARENTS: no second-level shape drawn with id "
                         f"{', '.join(missing)}")
    return done


# ---------------------------------------------------------------------------
# Attribute side
# ---------------------------------------------------------------------------

# A file's rows for a country, dropped where another registered file counts
# the same units outright: {file: {country: the file that counts them}}.
# OCHA's Afghan table (cod-ps-afg, reference year 2026) totals 48.6 million
# people and binds about 266 of the 398 drawn districts; the statistics
# office's own 1396 (2017-18) estimates total 28.2 million settled people,
# bind every district but two, and make their provinces to the person. The
# year rule put OCHA's figure in front of the office's wherever both reached
# a district, so a province's districts added up to neither year's total.
# One vintage per level: the office's.
# OCHA's Solomon Islands table is the National Statistics Office's projection
# for 2023, by constituency; solomon_census.json sums the 2019 census's own
# ward counts into the same 49 drawn constituencies (OCHA's fiftieth row,
# Temotu Pele, has no polygon). Temotu's province figure is the census's and
# says how much of it lies on islands the map does not draw (UNDRAWN_PARTS),
# which holds only while its constituencies carry the same census; the
# projection waits on that note being written another way.
# The Wikipedia floor gives way the same way where an office's file pins every
# first-level polygon of the country. It fills only what nothing else writes,
# but a row still claims its polygon, and two rows naming different places on
# one polygon stop the build. Afghanistan's one row is Ghazni's infobox
# figure under the boundary file's misspelling, 'Ghanzi', on the polygon the
# office's estimates now pin as Ghazni. Kiribati's three are the island
# groups' Wikipedia figures -- the Gilbert group's 83,382 of 2005 -- on
# polygons kiribati_census gives the census counts of the islands each draws,
# named for them: the Gilbert polygon draws neither Tarawa nor Banaba.
# Thailand's is a mismatch of concepts. Its provinces carry the Department of
# Provincial Administration's register (through Wikidata, 2018-2022), and
# OCHA's districts the US Census Bureau's 2023 projection of the de facto
# population, which puts Bangkok's 50 districts at 11,479,338 against the
# register's 5,676,648 and Mueang Samut Sakhon alone at 1,353,400 against its
# province's 586,199. Wikidata carries the register for the districts too (877
# of them at 2018): filed under the provinces Wikidata gives them, they add up
# to the provinces' figures within 3% in 71 of 74. The projection's ages and
# sexes stay, in sea_cod_ps_age.json.
# The rest are projections from an older census than the office counted,
# which are older word of the units however late the year they are for (a
# projection from the office's own census is held behind it instead, and
# stands where it is newer and the same ground: HELD_ROWS):
#   GTM  guatemala_census.json, everyone INE's 2018 census enumerated in each
#        of the 340 municipios and 22 departments (the person file's rows,
#        which make INE's published department counts); OCHA's 2024 figures
#        are a projection from the 2002 census and stood on all 340.
#   DOM  dominican_census.json, the 2022 census's count of the 32 provinces,
#        which their municipios make; OCHA's table for the Dominican Republic
#        is of the provinces for 2023, projected before that count, and runs
#        a median 4.8% below it.
#   PRY  paraguay_census.json, the 2022 census of 236 of the 247 districts
#        and a stated reason on the 11 drawn as they were before a district
#        was cut from them; OCHA's 2023 figures are projections made before
#        that count, a median 31% above it.
#   CRI  costa_rica_census.json, the 2011 census of the 83 cantons as drawn.
#        OCHA's 2021 figures are INEC's projection from that census, and the
#        2022 census, which the provinces show, counted fewer: Heredia's
#        cantons are projected at 532,954 and the census found 479,117 in the
#        province. The 2022 count of the cantons is not read yet; until it is,
#        a projection a newer count contradicts does not stand in front of the
#        count it was made from.
# And Georgia's is older than the office's: Geostat's figures for the 55
# municipalities it can place are for 2026, OCHA's for 2014, and these stood
# on four of the 13 it cannot place (Khobi, Lanchkhuti, Terjola, Tkibuli),
# whose polygons hold Poti's or Kutaisi's ground or none of it.
# Myanmar is not listed although its 2014 census file binds all 74
# districts: its states and the composed districts (sea_composed.json) carry
# the same OCHA table for 2023, so the projection is one vintage at both
# levels there, and dropping it from the districts alone would put 2014
# children under 2023 parents.
SUPERSEDED_ROWS: dict[str, dict[str, str]] = {
    "cod_ps_admin2.json": {"AFG": "afghanistan_estimates.json",
                           "CRI": "costa_rica_census.json",
                           "DOM": "dominican_census.json",
                           "GEO": "georgia.json",
                           "GTM": "guatemala_census.json",
                           "PRY": "paraguay_census.json",
                           "SLB": "solomon_census.json",
                           "THA": "wikidata_admin2.json"},
    "wiki_population_admin1.json": {"AFG": "afghanistan_estimates.json",
                                    "KIR": "kiribati_census.json"},
}


# Rows a file spells differently from the boundary file, keyed by file and row
# id. The alias joins the row's own names, so the matcher reaches the shape by
# an exact name inside the row's province rather than by a guess. Thailand's
# districts take the register through Wikidata (SUPERSEDED_ROWS), and three of
# its romanisations are not the boundary file's: Watthana is CGAZ's 'Vadhana'
# (Bangkok), Khwao Sinarin its 'Khwao Sin Rin' (Surin) and Thap Khlo its 'Tap
# Khlo' (Phichit).
#
# OCHA's district tables are the same case, and so is CLEAR Global's: each row
# below is the one unit the boundary file draws under that label, in the
# province the row itself names, from the same release as every sibling that
# did join. Each was checked against the shapes of its province before it was
# listed; none of the labels is used twice in its country.
#   * Spellings: Quiculungo/Quiculongo, Nyarusange/Nyanrusang,
#     Kourittenga/Kouritenga, Komandjari/Komonjdjari, Nangha/Nagha Boguila,
#     Baraouéli/Baroueli, Ngwa/Nwga, Damban/Dambam, Igueben/Iguegben,
#     Mbaitoli/Mbatoli, Bagudo/Bagudu, Wamako/Wamakko, Raja/Raga,
#     Me-Zochi/Mé-zóxi, Tarmua/Tarmuwa, Tivaouane/Tivaoune,
#     Garoowe/GAROWE, Mohammadia/Mohammédia, Taroudannt/Taroudant,
#     Rehamna/Rhamna, Fquih Ben Salah/Saleh, Tanger/Tangier.
#   * Morocco's elided names: OCHA writes "Province d Azilal" and CLEAR
#     "Azilal", the boundary file "Province d'Azilal" with the Arabic name
#     after it, so neither the exact key nor a whole-word run reaches it. An
#     explicit alias was preferred to teaching norm() to split "d'" and "l'":
#     the alias can only add the join it names.
#   * "Gambos (ex-Chiange)" is the boundary file's "Gambos(Chiange)"; "Ville
#     de Tahoua" its "Tahoua Ville", an enclave the department of Tahoua, a
#     separate OCHA row, surrounds; "ABUJA MUNICIPAL" its "Municipal Area
#     Council".
#   * Not aliased: OCHA's Harari (Ethiopia) and Região Autónoma do Príncipe
#     (Sao Tome) rows. Each region is drawn once more at the second level on
#     the same ground (Hareri; Pagué), which fill_sole_children gives the
#     region's own figure; an alias would put OCHA's older 2022 projection on
#     the second-level copy and so show the one ground with two populations.
#   * Tanzania's town and municipal councils, which OCHA writes "<X>
#     MUNICIPAL" or "<X> TOWN" and the boundary file "<X> Urban" or "<X>
#     Township Authority": in each region the councils OCHA lists are the
#     polygons drawn, one for one, and the rural council of the same name
#     already joins its own polygon. Aliasing them one by one is narrower than
#     treating Urban, Municipal and Town as one word.
#   * Belarus: Wikidata's English labels for three regions are romanisations
#     of their Belarusian names -- "Byerastsye Region", "Horadnia Region",
#     "Mahilyow Region" -- where the boundary file draws Brest, Grodno and
#     Mogilev; their ISO 3166-2 codes (BY-BR, BY-HR, BY-MA) say which. The
#     other four regions join by name, so the three showed English
#     Wikipedia's 2024 figures beside their siblings' 2026 ones.
ROW_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "wikidata_admin1.json": {
        "BLR-WD-Q173822": ("Brest",),
        "BLR-WD-Q191061": ("Grodno",),
        "BLR-WD-Q189822": ("Mogilev",),
    },
    "wikidata_admin2.json": {
        "THA-WD-Q1019417": ("Vadhana",),
        "THA-WD-Q475772": ("Khwao Sin Rin",),
        "THA-WD-Q476889": ("Tap Khlo",),
    },
    "cod_ps_admin2.json": {
        "AGO-CODPS-AO06048": ("Quiculongo",),
        "AGO-CODPS-AO09073": ("Gambos(Chiange)",),
        "BDI-CODPS-BDI006011": ("Nyanrusang",),
        "BDI-CODPS-BDI016006": ("Nyabitsind",),
        "BFA-CODPS-BF4803": ("Kouritenga",),
        "BFA-CODPS-BF5203": ("Komonjdjari",),
        "CAF-CODPS-CF324": ("Nagha Boguila",),
        "MAR-CODPS-MA001001": ("Province d'Azilal إقليم أزيلال",),
        "MAR-CODPS-MA006005": ("Province d'El Kelâat Es-Sraghna إقليم قلعة السراغنة",),
        "MLI-CODPS-ML0401": ("Baroueli",),
        "NER-CODPS-NE005013": ("Tahoua Ville",),
        "NGA-CODPS-NG001009": ("Obi Nwga",),
        "NGA-CODPS-NG005004": ("Dambam",),
        "NGA-CODPS-NG012010": ("Iguegben",),
        "NGA-CODPS-NG015002": ("Municipal Area Council",),
        "NGA-CODPS-NG017011": ("Mbatoli",),
        "NGA-CODPS-NG022005": ("Bagudu",),
        "NGA-CODPS-NG034021": ("Wamakko",),
        "SSD-CODPS-SS0902": ("Raga",),
        "STP-CODPS-ST0206": ("Mé-zóxi",),
        "TZA-CODPS-TZ0105": ("Dodoma Urban",),
        "TZA-CODPS-TZ0306": ("Moshi Urban",),
        "TZA-CODPS-TZ0409": ("Korogwe Township Authority",),
        "TZA-CODPS-TZ0410": ("Handeni Mji",),
        "TZA-CODPS-TZ0505": ("Morogoro Urban",),
        "TZA-CODPS-TZ0607": ("Kibaha Urban",),
        "TZA-CODPS-TZ0806": ("Lindi Urban",),
        "TZA-CODPS-TZ0905": ("Mtwara Urban",),
        "TZA-CODPS-TZ0907": ("Masasi  Township Authority",),
        "TZA-CODPS-TZ1004": ("Songea Urban",),
        "TZA-CODPS-TZ1103": ("Iringa Urban",),
        "TZA-CODPS-TZ1304": ("Singida Urban",),
        "TZA-CODPS-TZ1406": ("Tabora Urban",),
        "TZA-CODPS-TZ1504": ("Sumbawanga Urban",),
        "TZA-CODPS-TZ1604": ("Kigoma  Urban",),
        "TZA-CODPS-TZ1608": ("Kasulu Township Authority",),
        "TZA-CODPS-TZ1701": ("Shinyanga Urban",),
        "TZA-CODPS-TZ1705": ("Kahama Township Authority",),
        "TZA-CODPS-TZ1806": ("Bukoba Urban",),
        "TZA-CODPS-TZ2005": ("Musoma Urban",),
        "TZA-CODPS-TZ2106": ("Babati UrbanBabati Urban",),
        "TZA-CODPS-TZ2201": ("Njombe Urban",),
        "TZA-CODPS-TZ2206": ("Makambako Township Authority",),
        "TZA-CODPS-TZ2301": ("Mpanda Urban",),
    },
    "clear_global_language.json": {
        "MAR-CG-MA001001": ("Province d'Azilal إقليم أزيلال",),
        "MAR-CG-MA001003": ("Province de Fquih Ben Saleh إقليم الفقيه بن صالح",),
        "MAR-CG-MA002006": ("Prefecture of Mohammédia",),
        "MAR-CG-MA003002": ("Province d'Errachidia إقليم الرشيدية",),
        "MAR-CG-MA004001": ("Préfecture de Fès عمالة فاس",),
        "MAR-CG-MA004003": ("Province d'El Hajeb إقليم الحاجب",),
        "MAR-CG-MA004004": ("Province d'Ifrane ⵜⴰⵙⴳⴰ ⵏ ⵉⴼⵔⴰⵏ إقليم إفران",),
        "MAR-CG-MA006005": ("Province d'El Kelâat Es-Sraghna إقليم قلعة السراغنة",),
        "MAR-CG-MA006008": ("Rhamna Province",),
        "MAR-CG-MA007001": ("Préfecture d'Oujda-Angad عمالة وجدة - أنجاد",),
        "MAR-CG-MA009004": ("Taroudant Province",),
        "MAR-CG-MA010005": ("Préfecture de M'diq-Fnideq عمالة المضيق الفنيدق",),
        "MAR-CG-MA010006": ("Prefecture of Tangier - Assilah",),
        "MAR-CG-MA010007": ("Province d'Ouezzane إقليم وزان",),
        "MLI-CG-ML0401": ("Baroueli",),
        "NGA-CG-NG034021": ("Wamakko",),
        "NGA-CG-NG036015": ("Tarmuwa",),
        "SEN-CG-SN1303": ("Tivaoune",),
        "SOM-CG-SO1701": ("GAROWE",),
    },
}

# Rows whose name is drawn more than once in their country and which do not
# say which province they are in, keyed by file and row id, with the province
# the row's own code names. Cambodia draws two Samraongs, Takeo's district and
# Oddar Meanchey's city, and CLEAR's row KH2107 names neither; its code's
# first two digits are Takeo's (KH21, the province row CLEAR itself
# publishes), so it is matched inside Takeo and nowhere else.
ROW_PARENTS: dict[str, dict[str, str]] = {
    "clear_global_language.json": {
        "KHM-CG-KH2107": "Takeo",
    },
}

# Rows bound to a polygon by its id, keyed by file and row id, with the polygon
# and the label it carries. For a row whose own name reaches another polygon
# first: OCHA's "ARUSHA CITY" and "MBEYA CITY" lose the word "city" to norm()
# and so are keyed exactly like the district councils "ARUSHA" and "MBEYA"
# beside them; both pairs met on the district's polygon and neither was kept.
# The cities are the polygons the boundary file calls "Arusha Urban" (269 km2)
# and "Mbeya Urban" (254 km2), and the district councils then join their own.
# The row takes the polygon's label as its name and keeps its own as an alias.
#
# Laos draws two Phonthongs and two Viengkhams, and OCHA's rows name their
# provinces as "Louangphabang" and "Champasack", which reach none of the map's
# (Luang Prabang, Champasak), so the three below joined nothing and their
# districts kept the 2015 census beside siblings on OCHA's 2024 projection.
# Each P-code's province digits say which polygon is the row's: LA06 is Luang
# Prabang, LA16 Champasak. (Vientiane's Viengkham, LA1009, joins by name.)
ROW_SHAPES: dict[str, dict[str, tuple[str, str]]] = {
    "cod_ps_admin2.json": {
        "TZA-CODPS-TZ0203": ("72390352B90906351205470", "Arusha Urban"),
        "TZA-CODPS-TZ1208": ("72390352B25057310038558", "Mbeya Urban"),
        "LAO-CODPS-LA0610": ("54806243B97421577673591", "Viengkham"),
        "LAO-CODPS-LA0612": ("54806243B14812805317737", "Phonthong"),
        "LAO-CODPS-LA1606": ("54806243B67434402908614", "Phonthong"),
    },
}

# A sentence a row carries about the polygon it lands on, keyed by file, row
# id and field, and written beside the field as ``<field>_note`` -- or into a
# gap's own note -- since it is about the polygon and not the figure, which
# other passes may copy elsewhere. Angola's Huíla has fourteen municipalities in
# OCHA's table and thirteen polygons: the boundary file draws no Cacula, and
# Cacula's seat (GeoNames 14.4956S 14.1163E) lies inside the polygon called
# Lubango. That polygon is 3,680 km2, about 540 km2 more than Lubango
# municipality's own area, so it is not Lubango and Cacula together and
# pooling the two would put Cacula's people on ground the map draws in other
# municipalities; Lubango's figure stands, saying what it leaves out.
#
# Zugdidi's polygon runs past the Enguri into Abkhazia: the eight village
# administrations of Gal district on that side -- Chuburkhinji, the two
# Otobaias, Tagiloni, Pichori, Nabakevi, Dikhazurga and Ganakhleba, whose
# Wikidata points lie 0.4 to 4.7 km inside it -- counted 12,066 people in the
# de facto authorities' 2011 census (abkhazia_census.ENGURI). Geostat counts
# the municipality without them, which is the figure the polygon carries, and
# neither its 2014 census (ages, sex) nor the 2002 one (nationality) counted
# them either.
ENGURI_VILLAGES = (
    "The outline drawn here also takes in the villages along the Enguri that the de "
    "facto authorities in Abkhazia count in their Gal district (Chuburkhinji, Otobaia, "
    "Tagiloni, Pichori and others), 12,000 or more people at their 2011 census, ")
ROW_NOTES: dict[str, dict[str, dict[str, str]]] = {
    "cod_ps_admin2.json": {
        "AGO-CODPS-AO09077": {"population": (
            "The map draws no polygon for Cacula, the municipality to the "
            "north-east whose seat lies inside this polygon; OCHA's table counts "
            "197,616 people in Cacula in 2024, who are not in this figure.")},
    },
    "georgia.json": {
        "GEO-GEOSTAT-92138335B56355921545740": {
            "population": ENGURI_VILLAGES + "who are not in this figure.",
            "median_age": ENGURI_VILLAGES + "whom the 2014 census did not count.",
            "sex_ratio": ENGURI_VILLAGES + "whom the 2014 census did not count.",
            "ethnicity": ENGURI_VILLAGES + "whom the 2002 census did not count.",
        },
    },
}

# The sources ROW_NOTES' sentences quote, cited on the row for its notes: Gal
# district's 2011 village rows, which Zugdidi's four notes count.
GAL_VILLAGES_2011 = {
    "name": "Ethno-Caucasus (ethno-kavkaz.narod.ru), the de facto authorities' 2011 "
            "census of Gal district by village administration",
    "url": "http://ethno-kavkaz.narod.ru/gal11.html", "year": 2011,
    "license": "Transcription of the census; terms of reuse not stated"}
ROW_NOTE_SOURCES: dict[str, dict[str, list[dict[str, Any]]]] = {
    "georgia.json": {
        "GEO-GEOSTAT-92138335B56355921545740": [
            {"field": f"{field} note", **GAL_VILLAGES_2011}
            for field in ("population", "median_age", "sex_ratio", "ethnicity")],
    },
}

# Rows that are not a unit of today's map, keyed by file and row id, with the
# reason. Wikidata files Thonburi Province, merged into Bangkok in 1971, among
# Bangkok's districts with its 1970 population (920,033); its name reaches the
# Thon Buri district's polygon, so the district's own row (103,377 in 2020)
# met a rival and neither was placed. English Wikipedia's Vatovavy-Fitovinany
# article now opens as Fitovinany, the region made in 2021 from three of the
# six districts the polygon holds, and its infobox's 730,207 (2018) is
# Fitovinany's; the polygon's six districts carry OCHA's 2018 figures, which
# fill_parent_populations then sums.
DROPPED_ROWS: dict[str, dict[str, str]] = {
    "wikidata_admin2.json": {
        "THA-WD-Q6580711": "Thonburi Province, merged into Bangkok in 1971",
    },
    "wiki_population_admin1.json": {
        "MDG-WP-vatovavy-fitovinany": "Fitovinany's 2018 figure, three of the "
                                      "polygon's six districts",
    },
}


def superseded(filename: str) -> set[str]:
    """The countries whose rows in ``filename`` give way to a registered file with rows."""
    return {iso3 for iso3, by in SUPERSEDED_ROWS.get(filename, {}).items()
            if by in ADAPTER_FILES and read_json(PROCESSED / by, None)}


def offered(filename: str) -> set[str]:
    """The countries whose rows in ``filename`` are held behind a registered file
    with rows (HELD_ROWS): without that file they are read as any row is."""
    return {iso3 for iso3, by in HELD_ROWS.get(filename, {}).items()
            if by in ADAPTER_FILES and read_json(PROCESSED / by, None)}


def load_adapters() -> dict[str, list[dict[str, Any]]]:
    """Every adapter record, bucketed by country, in authority order."""
    by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for filename in ADAPTER_FILES:
        path = PROCESSED / filename
        rows = read_json(path, None)
        if not rows:
            continue
        log(f"  adapter {filename}: {len(rows)} records")
        dropped = superseded(filename)
        offers = offered(filename)
        aliases = ROW_ALIASES.get(filename, {})
        not_units = DROPPED_ROWS.get(filename, {})
        parents = ROW_PARENTS.get(filename, {})
        placed_by_id = ROW_SHAPES.get(filename, {})
        notes = ROW_NOTES.get(filename, {})
        # A row a declared union pools stays although its country's rows in
        # this file give way: the union names it by id, and the office's file
        # that supersedes the rest says the polygon is not one of its units.
        pooled = union_row_ids(filename)
        for row in rows:
            iso3 = (row.get("country") or (row.get("id") or "")[:3]).upper()
            if (iso3 in dropped and row.get("id") not in pooled) \
                    or row.get("id") in not_units:
                continue
            if row.get("sources"):
                row["sources"] = spell_fields(row["sources"])
            if row.get("id") in aliases:
                row["aliases"] = [*(row.get("aliases") or []), *aliases[row["id"]]]
            if row.get("id") in parents and not row.get("parent_name"):
                row["parent_name"] = parents[row["id"]]
            for field, extra in notes.get(row.get("id"), {}).items():
                value = row.get(field)
                if value is None:
                    raise SystemExit(f"ROW_NOTES: {filename} {row['id']} has no {field} "
                                     f"for its sentence to sit beside")
                if is_gap(value):
                    row[field] = {**value, "note": join_note(value.get("note"), extra)}
                else:
                    row[f"{field}_note"] = join_note(row.get(f"{field}_note"), extra)
            for cited in ROW_NOTE_SOURCES.get(filename, {}).get(row.get("id"), []):
                row["sources"] = [*(row.get("sources") or []), dict(cited)]
            if row.get("id") in placed_by_id:
                shape_id, label = placed_by_id[row["id"]]
                row["aliases"] = [*(row.get("aliases") or []), row.get("name")]
                row.update(name=label, match_by="shape_id", shape_id=shape_id)
            # Which file a row came from decides whether two rows landing on one
            # shape are a conflict. Across files it is normal -- India's C-01 and
            # C-16 both describe Kargil -- and within one file it means one of
            # them is wrong.
            row["_source"] = filename
            # A row held behind an office's count offers its population and
            # nothing else: its other fields are the markers of questions it
            # does not answer, which the office's file answers.
            if iso3 in offers:
                row = offer_only(row)
            by_country[iso3].append(row)
    return by_country


# What a held row keeps besides its population (load_adapters): what places it.
HELD_KEYS = frozenset({"id", "level", "name", "parent", "parent_name", "parent_aliases",
                       "country", "match_by", "shape_id", "shape_label", "no_shape",
                       "aliases", "wikidata", "sources", "_source"})


def offer_only(row: dict[str, Any]) -> dict[str, Any]:
    """A HELD_ROWS row as it is read: what places it, its population and that
    figure's citation, marked as an offer (``_offer``), which merge_adapter
    holds behind whatever the unit carries."""
    kept = {key: value for key, value in row.items()
            if key in HELD_KEYS or key == "population"}
    kept["sources"] = [src for src in row.get("sources") or []
                       if set(str(src.get("field") or "").split("/")) <= {"population"}]
    kept["_offer"] = True
    return kept


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
# Three kinds of answer go in data/curated/admin0_detail.json for a
# composition. A row with ``groups`` replaces the field with a census's own
# division of it, which is always the better answer and is used wherever such
# a table exists -- or, where the census does not ask, a survey's, marked as
# one by its ``basis`` (the European Social Survey's pooled national samples).
# A row with only a ``note`` says what the bucket holds and why it is not
# divided, which is what is left when the census published one number and no
# break-up of it. A row with a ``status`` replaces a line that is not a
# composition at all with a stated gap -- Kazakhstan's Factbook "languages" are
# the shares of people who know Kazakh, Russian and English, 199% in all. None
# of them invents a split.
#
# And a row for ``median_age`` or ``sex_ratio`` gives the country a census's
# own figure where the Factbook's estimate cannot be the same people as the
# census its divisions carry: Nauru's median of 28.2 against the census's 21.6.
# A ``population`` row with ``"use": "check"`` is not shown: every country
# shows the Factbook's estimate, and the row is the census or register count
# of the people its first level counts, which a sum of the first level is
# checked against instead (CHECKED_AGAINST) -- the Marshall Islands' 82,011
# against the 2021 census's 42,418 the atolls carry. Those are applied before
# the roll-ups, because the population is what a sum of the divisions is
# checked against.
#
# This is the admin-0 counterpart of data/curated/admin1_seed.json, and it is a
# curated file for the same reason that one is: an adapter cannot reach admin0.
# Adapter output lands on admin1 and admin2 shapes; the country record is the
# Factbook profile plus whatever its children roll up into it, and there is no
# third door.

COMPOSITION_ROWS = ("religion", "language", "ethnicity")
FIGURE_ROWS = {"population": None, "median_age": "years",
               "sex_ratio": "males_per_1000_females"}
CURATED_GAPS = (NOT_AVAILABLE, NOT_COLLECTED)
# The keys of a curated figure row that only says what the figure counts.
# ``note_sources`` cites the counts its note quotes besides the row's own.
NOTE_ONLY = frozenset({"country", "field", "note", "status", "note_sources"})


def load_country_detail() -> dict[str, list[dict[str, Any]]]:
    """ISO3 -> the curated admin-0 rows for it."""
    payload = read_json(ROOT / "data" / "curated" / "admin0_detail.json", {})
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("rows", []):
        rows[row["country"]].append(row)
    return rows


def _curated_country(by_id: dict[str, dict[str, Any]], iso3: str) -> dict[str, Any]:
    entity = by_id.get(iso3)
    if entity is None:
        raise SystemExit(
            f"admin0_detail: no country record with id {iso3!r}. The "
            f"curated rows for it would go nowhere and nothing would say "
            f"so.")
    return entity


def _cite(entity: dict[str, Any], field: str, row: dict[str, Any]) -> None:
    """The row's source on the record, in place of what the field held before.

    A source goes with the figure it produced, as in merge_adapter: Uganda kept
    Afrobarometer beside the census table that had replaced its figure, and
    Austria ten regional survey citations beside the national table, each read
    as a source of the number on screen. Entries that cite this field and
    nothing else go; one citing several fields stays, for the others.
    """
    sources = entity.setdefault("sources", [])
    sources[:] = [src for src in sources
                  if not set(str(src.get("field") or "").split("/")) <= {field}]
    if row.get("source"):
        sources.append({"field": field, "name": row["source"],
                        "url": row.get("url"), "year": row.get("year"),
                        "license": row.get("license", "")})


def _cite_quoted(entity: dict[str, Any], field: str, source: dict[str, Any]) -> None:
    """Cite a count the note beside a figure quotes, said to be that.

    Tuvalu's 2022 census was named in the note beside the Factbook's figure
    and never linked; Bhutan's 2017 census, Israel's districts and Laos's two
    totals were quoted with no source on the record at all.
    """
    quoted = {"field": f"{field} note", "name": source["name"],
              "url": source.get("url"), "year": source.get("year"),
              "license": source.get("license", ""),
              "note": "The count the note beside the population quotes, "
                      "not the source of the figure shown."}
    if quoted not in entity.setdefault("sources", []):
        entity["sources"].append(quoted)


def apply_country_figures(admin0: list[dict[str, Any]],
                          rows: dict[str, list[dict[str, Any]]]) -> None:
    """Put the curated population, median age and sex ratio on the countries.

    Run before the roll-ups, which check a sum of the divisions against the
    country's population: a Factbook estimate twice the census's count refused
    every sum the Marshall Islands' atolls could give.

    A row must give a value, a year and a source; one that does not stops the
    build, as an unmatched country does. The one exception is a row that
    gives a note and nothing else (NOTE_ONLY): it says what the figure
    already shown counts, and leaves the figure alone -- Israel's Factbook
    population counts East Jerusalem and the Golan, which the map draws
    outside its shape. On a field that is a gap, the note is the gap's own
    reason, with the row's status if it gives one (Antarctica has no
    permanent population to count).

    A population row with ``"use": "check"`` leaves the figure shown too: its
    count goes beside it, for the sums of the first level to be checked
    against (CHECKED_AGAINST), and its note says what the two figures are. One
    for a country that shows no population stops the build: its note would
    describe a figure that is not there.
    """
    by_id = {entity["id"]: entity for entity in admin0}
    applied = 0
    for iso3, country_rows in sorted(rows.items()):
        for row in country_rows:
            field = row["field"]
            if field not in FIGURE_ROWS:
                continue
            entity = _curated_country(by_id, iso3)
            if set(row) <= NOTE_ONLY and row.get("note"):
                if is_gap(entity.get(field)):
                    held = entity.get(field)
                    status = row.get("status") or (held.get("status") if isinstance(held, dict)
                                                   else None) or NOT_AVAILABLE
                    if status not in (NOT_AVAILABLE, NOT_COLLECTED, NOT_APPLICABLE):
                        raise SystemExit(f"admin0_detail: {iso3} {field} gives status "
                                         f"{status!r}, which is not a gap's")
                    entity[field] = gap(status, row["note"])
                else:
                    entity[f"{field}_note"] = row["note"]
                for source in row.get("note_sources") or []:
                    _cite_quoted(entity, field, source)
                applied += 1
                continue
            if not isinstance(row.get("value"), (int, float)) or not row.get("year") \
                    or not row.get("source"):
                raise SystemExit(f"admin0_detail: {iso3} {field} needs a value, a year "
                                 f"and a source")
            if "use" in row and (row["use"] != "check" or field != "population"):
                raise SystemExit(f"admin0_detail: {iso3} {field} says use "
                                 f"{row['use']!r}; only a population row is used "
                                 f"as a check")
            shown = entity.get(field)
            if row.get("use") == "check":
                # Its note says what the figure shown is, so a country with
                # none would be told about a figure it does not show.
                if published(shown) is None:
                    raise SystemExit(f"admin0_detail: {iso3}'s population row is a "
                                     f"check beside the figure shown, and the country "
                                     f"shows none; give the count its own note and "
                                     f"drop \"use\" to show it")
                entity[field] = {**shown, CHECKED_AGAINST: {
                    "value": row["value"], "year": row["year"], "source": row["source"]}}
                # The count the note quotes keeps its link and licence, cited
                # for the note and said to be that, not for the figure shown.
                _cite_quoted(entity, field, {"name": row["source"], "url": row.get("url"),
                                             "year": row.get("year"),
                                             "license": row.get("license", "")})
            else:
                entity[field] = measure(row["value"], unit=FIGURE_ROWS[field],
                                        year=row["year"], source=row["source"])
                _cite(entity, field, row)
            for source in row.get("note_sources") or []:
                _cite_quoted(entity, field, source)
            entity[f"{field}_note"] = row["note"]
            applied += 1
    if applied:
        log(f"  admin0 detail: {applied} curated figures on "
            f"{len({r['country'] for rs in rows.values() for r in rs if r['field'] in FIGURE_ROWS})} "
            f"countries")


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
        entity = _curated_country(by_id, iso3)
        for row in country_rows:
            field = row["field"]
            if field in FIGURE_ROWS:
                continue                     # apply_country_figures' rows
            if field not in COMPOSITION_ROWS:
                raise SystemExit(
                    f"admin0_detail: {iso3} names field {field!r}, which is "
                    f"not one of the three compositions.")
            if row.get("status"):
                if row["status"] not in CURATED_GAPS or row.get("groups"):
                    raise SystemExit(
                        f"admin0_detail: {iso3} {field} gives status "
                        f"{row['status']!r}; a row states a gap "
                        f"({' or '.join(CURATED_GAPS)}) or gives groups, not both")
                # The reason is the gap's own note, as everywhere else; a
                # separate field note would say it twice.
                entity[field] = gap(row["status"], row["note"])
                for suffix in SATELLITES:
                    entity.pop(f"{field}{suffix}", None)
                _cite(entity, field, row)
                applied += 1
                continue
            if row.get("groups"):
                entity[field] = row["groups"]
                for suffix in ("_year", "_basis"):
                    entity.pop(f"{field}{suffix}", None)
                if row.get("year"):
                    entity[f"{field}_year"] = row["year"]
                _cite(entity, field, row)
            elif row.get("source"):
                entity.setdefault("sources", []).append(
                    {"field": field, "name": row["source"],
                     "url": row.get("url"), "year": row.get("year"),
                     "license": row.get("license", "")})
            # A basis on a note-only row says what the line already there
            # counts: Thailand's Factbook "ethnic groups" are nationality, by
            # the Factbook's own note, and read as ethnicity without it.
            if row.get("basis"):
                entity[f"{field}_basis"] = row["basis"]
            entity[f"{field}_note"] = row["note"]
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


# Factbook entities without a country outline of their own that the boundary
# file does draw, as a disputed area: the West Bank (shapeGroup 129), Gaza
# (118) and the Falklands (117). Their records said the composite has no
# outline for them and draws them inside the administering state, which is
# false, and the Jerusalem District's notes rely on the West Bank outline.
# record id -> the disputed area's name in the boundary file, and as a
# sentence says it.
DRAWN_AS_DISPUTED: dict[str, tuple[str, str]] = {
    "PSE-WE": ("West Bank", "the West Bank"),
    "PSE": ("Gaza Strip", "the Gaza Strip"),
    "FLK": ("Falkland Islands (UK)", "the Falkland Islands"),
}


def disputed_outline_note(record_id: str, admin0: list[dict[str, Any]]) -> str | None:
    """What a geometry-less record drawn as a disputed area says about its outline.

    None for a record not declared, or where no boundary layer of disputed
    areas was read; a declaration whose area is no longer drawn stops the
    build rather than say something false.
    """
    declared = DRAWN_AS_DISPUTED.get(record_id)
    if not declared or not any(e.get("disputed") for e in admin0):
        return None
    name, said = declared
    if not any(e.get("disputed") and e.get("name") == name for e in admin0):
        raise SystemExit(f"build_entities: {record_id} is declared drawn as the disputed "
                         f"area {name!r}, which the boundary file no longer draws")
    return (f"The map draws {said} as a disputed area of its own, as geoBoundaries' "
            f"global composite delimits it, and shows no figures on that outline; the "
            f"territory's own figures are shown here instead.")


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
         "note": prov.get("note"), "license": ""})


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
# order the files are read in. These only ever fill a population nobody
# else has written.
#
# Nor is a census's median age or sex ratio replaced by a projection's. The
# medians cod_ps_age.json interpolates for 2024 run a year above INEGI's 2020
# census in Mexico and two above INE's 2018 census in Guatemala -- ageing, not
# error -- and dated comparison would let every one of them win.
FILL_ONLY = frozenset({"wikidata_admin1.json", "wikidata_admin2.json",
                       "wikidata_admin2_classes.json",
                       "wiki_population_admin1.json", "wiki_table_population.json",
                       "cod_ps_age.json",
                       # Haiti's median ages: a 2024 projection from the 2003
                       # census, which a count would always replace.
                       "haiti_cod_ps_age.json",
                       # Bucharest's sectors' median age by legal domicile,
                       # which is not the census's usual residence: it only
                       # fills a sector no census median reaches.
                       "bucharest_sectors.json",
                       # Turkey's districts as OCHA relays TUIK's 2022 register.
                       "turkey_districts.json",
                       # Thailand's, Laos's and Cambodia's medians and sex
                       # ratios from OCHA's COD-PS: projections (Thailand's
                       # by the US Census Bureau), read only where no office
                       # could be.
                       "sea_cod_ps_age.json",
                       # Yemen's median ages from the CSO's 2017 district
                       # projection: a projection never replaces a count.
                       "yemen_census_age.json"})
FILL_ONLY_FIELDS = frozenset({"population", "median_age", "sex_ratio"})

# A file's rows for a country, held behind the statistics office's own count
# rather than competing with it by date: {file: {country: the file that counts
# them}}. Their populations stand in front of the office's only where
# prefer_newer_figures finds them newer and the same ground; their other
# fields are not read. Each office's file gives every drawn unit of its
# country a count or a stated reason, so no polygon waits on these to be
# filled, and a stated reason is never filled over by them. (SUPERSEDED_ROWS
# drops a file's rows outright, where they are not the office's units or not
# the same people at all.)
#
# OCHA's tables here are the offices' own projections from the census the
# office's file counts, so they are newer word of the same units: Laos's
# districts for 2024 from the 2015 census, Mexico's municipios for 2024 from
# the 2020 census (CONAPO), Costa Rica's cantons for 2021 from the 2011
# census, Nicaragua's municipios for 2020 from the 2005 census, Nepal's
# districts for 2023 from the 2021 census, the Philippines' provinces for 2022
# from the 2020 census. Japan's are Wikidata's registered populations for
# 2021-2024, bound by id, against the 2020 census: Okuma, under an evacuation
# order, registered 10,004 and the census found 847 living there, and the
# test keeps that one off. Where OCHA's table projects an older census than
# the office counted -- Guatemala's 2024 figures from the 2002 census over the
# 2018 count, the Dominican Republic's 2023 provinces from the 2010 census
# over the 2022 count, Paraguay's 2023 districts over the 2022 count -- the
# count is the newer word, and those rows are still dropped (SUPERSEDED_ROWS).
HELD_ROWS: dict[str, dict[str, str]] = {
    "cod_ps_admin2.json": {"LAO": "laos_district.json",
                           "MEX": "mexico_municipality.json",
                           "NIC": "nicaragua_census.json",
                           "NPL": "nepal_district.json",
                           "PHL": "philippines_age.json"},
    "wikidata_points_admin2.json": {"JPN": "japan_municipal.json"},
}


def is_fill_only(source: str | None, iso3: str | None) -> bool:
    """Whether a file's figure for this country fills only, held behind a count."""
    return source in FILL_ONLY or (iso3 or "") in HELD_ROWS.get(source or "", {})

# How far a newer figure may sit from an older count and still be taken for
# the same ground (prefer_newer_figures): its change a year within
# RECENCY_SPREAD of the median change of the country's other units offered
# the same way, where there are RECENCY_PEERS of them, else within
# RECENCY_FEW; and an encyclopaedia's no more than RECENCY_SPAN years after
# the count.
RECENCY_SPREAD = 0.02
RECENCY_PEERS = 5
RECENCY_FEW = (-0.02, 0.03)
RECENCY_SPAN = 10

# Offices' files whose counts are of the units as the map draws them, older
# than the units of the same names today, so a newer figure under a unit's
# name is the new unit's: Estonia's municipalities before the 2017 reform,
# Norway's kommuner before 2020's, Iceland's of 2017, and Ukraine's raions
# with the cities of oblast significance drawn inside them (the 2001 census;
# Wikidata's 2022 Konotop is the city's 83,543, the raion with it held
# 135,932).
GROUND_PINNED = frozenset({"estonia_municipality.json", "norway_kommune.json",
                           "iceland_municipality.json", "ukraine_raion.json"})

# Files whose newer figures for a country count other people than the counts
# they would replace, so prefer_newer_figures leaves them behind. Korea's
# provinces carry the resident register's Koreans with the registered
# foreigners at the end of 2023, the basis their districts share; Wikidata's
# provincial figures are the register's Koreans alone. Incheon's 3,049,315 for
# 2025 stood in front of its 3,078,426, 81,016 of them foreigners, so a
# province that grew read as shrinking.
#
# Nepal's is a projection on another basis than the census it is said to come
# from: OCHA's 77 districts add up to 30,899,443 for 2023, 5.95% above the
# 2021 census's 29,164,578 two years on, where the census itself had grown
# from the 2011 census's 26,494,504 by under 1% a year. Every district moved
# by about as much, so the comparison with its peers let the whole table
# through, and Koshi took the districts' 2023 sum.
#
# Cambodia's are figures nobody can say whose people they are: English
# Wikipedia's infoboxes give Tboung Khmum 889,970, Banteay Meanchey 898,484
# and Preah Sihanouk 234,702 "as of 2024", and cite for them the 2019
# census's final results, which count 776,841, 861,883 and 310,072. Tboung
# Khmum's would be 2.8% a year, against 1.7% for the country.
OTHER_PEOPLE: dict[tuple[str, str], str] = {
    ("KOR", "wikidata_admin1.json"): "the resident register's Korean nationals alone, "
                                     "without the registered foreigners",
    ("NPL", "cod_ps_admin2.json"): "a projection 5.95% above the 2021 census two years "
                                   "on, which is another basis and not growth",
    ("KHM", "wiki_population_admin1.json"): "figures dated 2024 whose cited source, the "
                                            "2019 census's final results, does not give them",
}

# A count whose note says it was put together for the polygon -- summed over
# the units drawn inside it, two units the census counts apart, a unit as it
# stood before a reform or as the map draws it, a unit with or without a part
# the boundary file draws otherwise -- is the polygon's ground by
# construction, and a newer figure under the unit's name is the unit's.
# Belarus's Gomel polygon carried the raion with the city of Gomel, "counted
# apart", and Wikidata's 2026 Gomel is the city's 499,853 against the two's
# 581,020; Costa Rica's Grecia carried the canton "without Río Cuarto ...,
# which the boundary file draws apart", and OCHA's 2021 Grecia is the canton
# as it stood before Río Cuarto left it in 2017.
COMPOSED_COUNT = re.compile(
    r"\bsummed\b|\badded up\b|\bthe sum of\b|\btheir sum\b|\bthe two together\b"
    r"|\bcount(?:s|ed)? (?:it |them )?apart\b|\bdraws? (?:it |them )?apart\b"
    r"|\bdrawn apart\b|\b(?:boundary file|map) does not draw\b"
    r"|\bsince the boundary file was drawn\b|\bwhich this polygon takes in\b"
    r"|\bas the map draws\b|\bas drawn\b|\bas it stood\b|\bas it was before\b"
    r"|\bbefore the \d{4} reform\b|\bas one (?:shape|polygon)\b|\bless (?:its|the)\b",
    re.I)

# ... unless the clause says there is none: China's county notes say "its
# prefecture lists no development zone counted apart".
COMPOSED_DENIED = re.compile(r"\bno\b", re.I)


def composed(said: str) -> bool:
    """Whether a count's note says it was put together for the polygon."""
    for found in COMPOSED_COUNT.finditer(said):
        start = max(said.rfind(mark, 0, found.start()) for mark in ".;:,(") + 1
        if not COMPOSED_DENIED.search(said[start:found.start()]):
            return True
    return False

# The figures a statistics office's stated reason may displace
# (``displaces_before``): every fill-only file's, and Wikidata's as the points
# files bind it by id (scripts/wikidata_points.py). Those are not fill-only --
# a figure bound by id corrects one matched by name -- but they are still an
# encyclopaedia's, and the reason has to reach them: Cambodia's census refuses
# Preah Sihanouk's four districts as a 29% undercount, and Wikidata's 2019
# figures for them, the same undercount, arrive through wikidata_points_admin2
# after wikidata_admin2 and stood beside the reason.
DISPLACEABLE = FILL_ONLY | {"wikidata_points_admin1.json", "wikidata_points_admin2.json"}

# A survey's share is an estimate from a sample, and a census's or a
# register's is a count of everyone: where both describe a unit, the count
# stands, however much older it is. Survey readers written for the fields a
# census does not ask -- Europe's religion and home language -- name their
# output ``*_survey.json``, and their compositions only fill what no count
# has written. Between two surveys the newer stands, as between two counts.
SURVEY_FIELDS = frozenset({"religion", "language", "ethnicity"})

# And a national office's survey -- the Mikrozensus, a statistics office's
# language survey, a large national sample -- stands in front of a
# cross-national one, whose few hundred respondents a region are drawn to
# compare countries rather than to describe a region.
CROSS_NATIONAL_SURVEYS = frozenset({"ess_region_survey.json"})

# Survey estimates that reach the map through a transcription rather than in a
# file of their own: CBS's religion by province, as nl.wikipedia's infoboxes
# copy it. CBS measures religion by survey -- no Dutch census has asked it
# since 1971 -- so these rank with the surveys and, being transcriptions, stand
# behind CBS's own workbook whatever year an infobox gives. Drenthe's infobox
# carries the 2021/2025 workbook's figures under a citation of the December
# 2016 release, and Noord-Brabant's prints 47.4% with no religion where that
# workbook has 52.6%.
TRANSCRIBED_SURVEYS = frozenset({"netherlands_province.json"})


def is_survey(filename: str | None) -> bool:
    """A file of survey estimates, which fills compositions and replaces none."""
    return bool(filename) and filename.endswith("_survey.json")


def composition_rank(filename: str | None) -> int:
    """0 for a count, 1 for a national survey, 2 for a cross-national one."""
    if filename in CROSS_NATIONAL_SURVEYS:
        return 2
    return 1 if is_survey(filename) or filename in TRANSCRIBED_SURVEYS else 0


# A census composition as Wikipedia transcribes it (europe_wiki.py) is the
# office's figure at one remove, and dated by whatever the article cites --
# often the year the results were published. Serbia's district articles cite
# the 2022 census's 2023 release, so 22 districts' Wikipedia ethnicity read as
# 2023 and held RZS's own 2022 tables back as the older. The office's table
# stands in front of the transcription whatever the two years say, as the
# Europe brief has it; between two transcriptions, or two tables, the newer
# still stands.
def is_wiki_composition(filename: str | None) -> bool:
    return bool(filename) and (filename.startswith("europe_wiki_")
                               or filename in TRANSCRIBED_SURVEYS)


def year_of(container: dict[str, Any], key: str) -> int | None:
    """The year a field's value is for: inside a figure, beside a composition."""
    value = container.get(key)
    if isinstance(value, dict) and isinstance(value.get("year"), int):
        return value["year"]
    if isinstance(value, list) and isinstance(container.get(f"{key}_year"), int):
        return container[f"{key}_year"]
    return None


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
    # The newer of two dated figures stands, whichever file it came from and
    # whichever came first. File order is a ranking of sources, and it was
    # being applied to dates: a 2011 census file below a 2021 estimate in the
    # list replaced the estimate. An older figure is used only where nothing
    # newer is published; it is held aside rather than dropped, so a check
    # that later refuses the newer one can still fall back to it.
    #
    # Between two kinds of source it does not decide: an encyclopaedia's figure
    # never replaces a count, however recent (the owner's rule of 22 September
    # 2026). Viet Nam is why. It merged its provinces in 2025, and Wikidata's
    # 2024 figure for An Giang -- 3,679,300 -- is the merged province's, on the
    # old province's shape, against the 2019 census's 1,908,352. A newer figure
    # can be a different unit's.
    iso3 = entity.get("country")
    encyclopaedic = is_fill_only(row.get("_source"), iso3)
    rank = composition_rank(row.get("_source"))
    origin = entity.get("_from") or {}
    transcribed = is_wiki_composition(row.get("_source"))
    dated = {key: (year_of(row, key), year_of(entity, key)) for key in VALUE_FIELDS
             if not is_gap(row.get(key)) and not is_gap(entity.get(key))
             and is_fill_only(origin.get(key), iso3) == encyclopaedic
             and composition_rank(origin.get(key)) == rank
             and not (key in SURVEY_FIELDS and origin.get(key)
                      and is_wiki_composition(origin.get(key)) != transcribed)}
    newer = {key for key, (theirs, ours) in dated.items()
             if theirs is not None and ours is not None and theirs > ours}
    older = {key for key, (theirs, ours) in dated.items()
             if theirs is not None and ours is not None and theirs < ours}
    held = {key for key in FILL_ONLY_FIELDS
            if encyclopaedic and not is_gap(entity.get(key)) and key not in newer} | older
    # A file held behind an office's count (HELD_ROWS) offers its population
    # and writes nothing, whatever the unit holds and whichever came first.
    if row.get("_offer") and not is_gap(row.get("population")):
        held.add("population")
    # A survey's estimate stands behind any count already written, and a
    # cross-national survey's behind a national one's.
    held |= {key for key in SURVEY_FIELDS
             if not is_gap(row.get(key)) and not is_gap(entity.get(key))
             and composition_rank(origin.get(key)) < rank}
    # And a Wikipedia transcription stands behind an office's own table of the
    # same kind: a census's behind the census's, a survey's behind the survey's.
    held |= {key for key in SURVEY_FIELDS
             if transcribed and not is_gap(row.get(key)) and not is_gap(entity.get(key))
             and origin.get(key) and composition_rank(origin.get(key)) <= rank
             and not is_wiki_composition(origin.get(key))}
    # What was held back is kept aside, not thrown away: a check that later
    # refuses the figure in front of it can fall back to it (see fall_back).
    for key in held:
        if not is_gap(row.get(key)):
            entity.setdefault("_held", {}).setdefault(key, []).append({
                "value": row[key], "wikidata": row.get("wikidata"),
                "file": row.get("_source"), "match": row.get("_match"),
                "sources": [src for src in row.get("sources") or []
                            if key in str(src.get("field") or "").split("/")],
                "row": row.get("id"),
                # The note beside the figure goes with it, to wherever it is
                # later shown: a union's says what was added up.
                **({"unit_note": row[f"{key}_note"]} if row.get(f"{key}_note") else {})})
    replaced = {key for key, value in row.items()
                if key in VALUE_FIELDS and not is_gap(value) and key not in held}
    # And what a newer figure displaces is kept aside the same way. The town
    # of Bovec's 2024 figure displaces the municipality's 2020 one; when the
    # settlement check refuses the town's, the municipality's is still there.
    for key in replaced & FILL_ONLY_FIELDS:
        if not is_gap(entity.get(key)):
            entity.setdefault("_held", {}).setdefault(key, []).append({
                "value": entity[key], "wikidata": entity.get("wikidata"),
                "file": origin.get(key), "match": (entity.get("_how") or {}).get(key),
                "sources": [src for src in entity.get("sources") or []
                            if key in str(src.get("field") or "").split("/")]})
    if replaced:
        entity["sources"] = [
            src for src in entity.get("sources", [])
            if not (str(src.get("field") or "").split("/")
                    and all(part in replaced
                            for part in str(src.get("field") or "").split("/")))]
    for key, value in row.items():
        if key in {"id", "level", "name", "parent", "parent_name", "parent_aliases",
                   "match_by", "shape_label", "_source", "_match", "_offer",
                   # What a median was taken from, for pool_rows; not shown.
                   "age_groups"}:
            continue
        if key == "sources":
            # A citation for a figure that was held back describes nothing
            # on the record, so it is not added either.
            kept = [src for src in (value or [])
                    if not (held and set(str(src.get("field") or "").split("/")) <= held)]
            entity.setdefault("sources", []).extend(kept)
            continue
        if key in held or any(key == f"{f}{suffix}" for f in held for suffix in SATELLITES):
            continue
        # The item a unit is linked to is the one its figure came from. Bled's
        # municipality gives the shape 8,217 people and the town of Bled's row,
        # joined after it, is held back; had the town's item replaced the
        # link, the settlement check below would read the town's classes and
        # refuse the municipality's figure as a town's.
        if key == "wikidata" and ("population" in held and entity.get("wikidata")
                                  or row.get("_offer")):
            continue
        # A statistics office's statement that its census does not reach a
        # unit displaces an encyclopaedia's figure for it that is older than
        # the year the statement names (``displaces_before``). Cyprus's
        # censuses since 1974 are taken only where its Government governs,
        # and Wikidata's figures for the communities beyond are the 1973
        # census's: 1973 read as the population of Kyrenia. A count is never
        # displaced, nor an encyclopaedia's figure of that year or later, and
        # the figure is not kept aside to fall back to: the statement is
        # that there is none for now. A statement that says so
        # (``displaces_undated``) displaces an undated figure too: Wikidata's
        # undated 80,000 for Khavas, 88,900 for As-Salt and 511,200 for
        # Baabda stand on shapes no count reaches, and nothing dates them.
        if (key in FILL_ONLY_FIELDS and is_gap(value) and isinstance(value, dict)
                and isinstance(value.get("displaces_before"), int) and not encyclopaedic
                and not is_gap(entity.get(key))
                and (origin.get(key) in DISPLACEABLE or is_fill_only(origin.get(key), iso3))
                and ((year_of(entity, key) is None and value.get("displaces_undated") is True)
                     or (year_of(entity, key) or value["displaces_before"])
                     < value["displaces_before"])):
            entity[key] = value
            for suffix in SATELLITES:
                if f"{key}{suffix}" not in row:
                    entity.pop(f"{key}{suffix}", None)
            entity.get("_from", {}).pop(key, None)
            entity.get("_how", {}).pop(key, None)
            entity["sources"] = [src for src in entity.get("sources", [])
                                 if set(str(src.get("field") or "").split("/")) != {key}]
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
        # Nor does a bare marker displace a gap that says why it is one. Every
        # file marks the questions it doesn't answer; Mexico's ethnicity file,
        # read after the median-age file, erased the note saying why Oaxaca's
        # 570 municipios have no median age.
        if (is_gap(value) and is_gap(entity.get(key))
                and isinstance(entity.get(key), dict) and entity[key].get("note")
                and not (isinstance(value, dict)
                         and (value.get("note") or value.get("status") == NOT_COLLECTED))):
            continue
        entity[key] = value
        if key in VALUE_FIELDS and not is_gap(value):
            entity.setdefault("_from", {})[key] = row.get("_source")
            entity.setdefault("_how", {})[key] = row.get("_match")
    # After the copy, not before it: a satellite the row does supply has just
    # overwritten the old one in place, and popping first would have moved it
    # to the end of the record. build.json is a digest of the written files, so
    # a key order that churns invalidates every reader's cache for no change in
    # the figures.
    #
    # The figures as much as the compositions: Mexico's municipios took OCHA's
    # 2024 median age and sex ratio first, with notes saying so, and the 2020
    # census's figures in their place from a later file, which says nothing
    # beside them -- 1,901 median ages and 2,467 sex ratios, and the sex ratios
    # of eight more Latin American countries, went out under a note about a
    # projection they were not.
    for field in (*DESCRIBED_FIELDS, *FIGURE_FIELDS):
        if is_gap(row.get(field)) or field not in row or field in held:
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


# Words that make a longer name a different place from the shorter one inside
# it, not a longer way of writing the same one. "Provincia de Cocle" is Cocle;
# "Nouvelle-Aquitaine" is not Aquitaine but the region Aquitaine was merged
# into in 2016, and Eurostat's NUTS-2 row for old Aquitaine -- 3,635,159
# people -- was joined to it by containment and stood for its 6.2 million.
# "Peninsula de Setubal" is most of Setubal District and not all of it, and
# "Area Metropolitana de Lisboa" reaches across the Tagus into it.
#
# Only just before the shorter name. After it, the same words are a locator: the
# first cut read them on both sides and took the census figures off 446 US
# counties, because "Abbeville County, South Carolina" ends in "South", and
# off Tierra del Fuego, whose full name ends "Islas del Atlantico Sur".
# "Greater" is not one: OCHA still writes South Africa's Sekhukhune district
# under its old name, Greater Sekhukhune, and it is the same place.
QUALIFIERS = frozenset({
    "new", "nouvelle", "nouveau", "nueva", "nuevo", "nova", "novo",
    "north", "northern", "nord", "norte", "south", "southern", "sud", "sur", "sul",
    "east", "eastern", "est", "este", "leste", "west", "western", "ouest", "oeste",
    "central", "middle",
    "upper", "lower", "haute", "haut", "basse", "bas", "alto", "baixo", "bajo",
    "grande", "little", "peninsula",
    "metropolitan", "metropolitana", "metropolitaine",
    "utara", "selatan", "barat", "timur", "tengah",
})


# Words that join a qualifier to the name it qualifies: "Peninsula de Setubal",
# "Area Metropolitana de Lisboa".
CONNECTORS = frozenset({"de", "del", "della", "do", "da", "dos", "das", "di",
                        "du", "des", "la", "le", "el", "al", "y", "e", "et"})


def qualified(before: tuple[str, ...]) -> bool:
    """Whether the word just before a name, past any connector, qualifies it.

    Only the nearest word: "West Sepik (Sandaun) Province" is Sandaun Province
    under a second name, and reading every word before "Sandaun" found "West"
    and took Vanimo off the map as Sandaun's capital.
    """
    words = [w for w in before if w not in CONNECTORS]
    return bool(words) and words[-1] in QUALIFIERS


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
        if qualified(long[:start]):
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
# One group at this share or more is the whole composition, not its largest part.
SOLE_GROUP_WHOLE = 99.0

# How far the children's population may sit from the parent's own before the
# sum is refused. Rounding and small-cell suppression move it a little -- New
# Zealand randomly rounds every count to a multiple of three -- and anything
# beyond this is the two figures describing different things.
ROLLUP_TOLERANCE = 0.02

# Below this share of a division's population, a composition's counts are a
# sample's respondents rather than its people. An Afrobarometer region is a
# hundred or so interviews; a census row is the whole population, or the part
# of it a question covers. Measured across every unit with both on 24
# September 2026: 975 rows sit below 5%, all of them survey regions, the
# highest being Cape Verde's Santa Catarina do Fogo (78 interviews for 4,725
# people, 1.7%); the lowest row above it is a Mexican municipio's indigenous
# speakers, 8.5% of its people and a census count.
SAMPLE_SHARE = 0.05

# The tree's spelling variants, which a sum across divisions folds together.
VARIANTS = {"language": group_tree.LANGUAGE_VARIANTS,
            "ethnicity": group_tree.ETHNIC_VARIANTS}

# What a division's composition is when it is not a count at all, and so is
# never added up into its parent. Empty: a sum of every division's shares,
# priced at their own populations and labelled with the basis they share, is
# a figure a reader can judge from its note.
#
# Afghanistan's district development plans were here. Each district carries
# the ethnic line of its plan (afghanistan, afghanistan_ddp), from plans drawn
# up between 2007 and 2014, and Kunduz's sum once came to 95.5% with nothing
# said about the rest. Every district now carries an "Other or not stated"
# remainder that closes its line to 100%, so where every district of a
# province has a line the province is summed from them -- Faryab, Kunduz,
# Laghman, Nangarhar and Nuristan -- with the basis, "district development
# plan", carried onto the sum and its note saying it is one. The mechanism
# stays for a basis that is not a share of people at all.
UNSUMMED_BASES: frozenset[str] = frozenset()

# How a sum's note says what its divisions' basis is, where "Every division
# counts <basis>" would not be English: a plan is not a thing counted.
BASIS_SAID = {
    "district development plan": (
        "Every division's shares are the ones its district development plan "
        "states, an estimate rather than a count, and so are these."),
}


def basis_sentence(basis: str, field: str) -> str:
    """What a sum's divisions count, said as a sentence a reader can follow.

    A survey's basis names itself ("survey estimate: self-identification,
    residents aged 15 and over in private households"), and "every division
    counts survey estimate: ... rather than religion" was not English.
    """
    if basis in BASIS_SAID:
        return BASIS_SAID[basis]
    if basis.startswith("survey estimate"):
        return f"Every division's figure is a {basis}, and so is this one."
    return f"Every division counts {basis} rather than {field}, so this does too."

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
# The share of a sum's people counted in its year for it to stand for that year.
ONE_MOMENT = 0.9


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


# The flag restate_encyclopaedia_parents leaves on a first-level population it
# replaced with its divisions' sum: the figure the unit carried before, which
# the country's composition gate still weighs (control_population). Dropped
# before writing (BUILD_FLAGS).
RESTATED_FROM = "restated_from"


# Every country shows the Factbook's estimate of its population: one estimate,
# of one moment, for every country, which no census or sum of its divisions
# replaces (roll_up_countries). Some carry beside it the census or register
# count of the people their first level counts (data/curated/admin0_detail.json,
# rows with "use": "check"), and a sum of the first level's compositions is
# weighed against that count instead of the estimate shown: the Factbook's
# 18,255,216 Guatemalans for 2024 would refuse every sum of the 2018 census's
# departments, which count 14,901,286 and are the whole country. A build flag,
# taken off before the record is written.
CHECKED_AGAINST = "checked_against"


def gate_population(entity: dict[str, Any]) -> Any:
    """The population a sum of a unit's divisions is weighed against: the
    count curated beside a country's figure (CHECKED_AGAINST) where there is
    one, else the count a newer figure took the place of (RESTATED_FROM, see
    prefer_newer_figures), else the figure shown. The compositions summed are
    a census's, and the count is that census's people."""
    pop = entity.get("population")
    if isinstance(pop, dict) and isinstance(pop.get(CHECKED_AGAINST), dict):
        return pop[CHECKED_AGAINST]
    if isinstance(pop, dict) and isinstance(pop.get(RESTATED_FROM), dict):
        return pop[RESTATED_FROM]
    return pop


def named_figure(pop: Any) -> str:
    """A population as a sentence names it: "14,901,286 for 2018 (INE Guatemala)"."""
    value, year = published(pop), vintage(pop)
    source = str(pop.get("source") or "") if isinstance(pop, dict) else ""
    return (f"{value:,.0f}" + (f" for {year}" if year else "")
            + (f" ({check_rollups.short_source(source)})" if source else ""))


# A source named for what it is takes "the" after "from": Maputo's note read
# "an older figure from 2017 census of Mozambique", and Laos's provinces
# "from Lao Statistics Bureau". A name of its own -- Eurostat, INEGI,
# Statistik Austria, Wikidata, OCHA's common operational dataset -- takes none.
SOURCE_TAKES_THE = re.compile(
    r"^\d{4}(?!\d)|^[A-Z][\w.&'-]*(?: [A-Z][\w.&'-]*)* of "
    r"|(?i:(?<![\w-])(?:agency|authority|board|bureau|census|cent(?:re|er)|commission|"
    r"committee|community|council|department|directorate|division|factbook|institute|"
    r"ministry|office|organi[sz]ation|questionnaire|report|service|survey)(?![\w-]))")


def named_source(source: str) -> str:
    """A source as a sentence names it after "from": check_rollups.short_source,
    with "the" where the name needs one ("the Lao Statistics Bureau")."""
    name = check_rollups.short_source(source)
    if (not re.match(r"[A-Z0-9]", name) or name.startswith("The ")
            or re.search(r"['’]s ", name)):
        return name
    return f"the {name}" if SOURCE_TAKES_THE.search(name) else name


def control_population(entity: dict[str, Any]) -> Any:
    """The population a country's sum of its first level is gated on.

    The unit's own, except where restate_encyclopaedia_parents put its
    divisions' sum in its place: then the figure it carried before. The gate
    asks whether the first level's compositions describe the country's people,
    and it was set on the figures the units carry for themselves, mostly the
    censuses their compositions come from. A sum put there so the unit agrees
    with what is drawn inside it, OCHA's projections mostly, moved it for no
    reason of the compositions': Honduras' and Colombia's census ethnicity,
    summed until then, were refused because OCHA's 2024 and 2025 projections
    ran 4% and 7% above the Factbook's estimates; and because the projections
    ran close to the Factbook's, Burkina Faso's, Mozambique's and São Tomé's
    census and Factbook lines gave way to sums of a survey's interviews, and
    the Central African Republic's 2020 religion estimate to its regions'
    2003 census.
    """
    pop = entity.get("population")
    if isinstance(pop, dict) and isinstance(pop.get(RESTATED_FROM), dict):
        return pop[RESTATED_FROM]
    return pop


def own_population_figures(admin1_by_country: dict[str, list[dict[str, Any]]]
                           ) -> dict[tuple[str, Any], dict[str, Any]]:
    """Each first-level unit's published population before any pass restates it
    from its divisions, for mark_restated_since: (country, unit id) -> figure."""
    return {(iso3, unit.get("id")): dict(unit["population"])
            for iso3, units in admin1_by_country.items() for unit in units
            if published(unit.get("population")) is not None}


def mark_restated_since(admin1_by_country: dict[str, list[dict[str, Any]]],
                        before: dict[tuple[str, Any], dict[str, Any]]) -> list[str]:
    """Flag each first-level population put in place of the unit's own figure
    since ``before`` was taken (RESTATED_FROM), as restate_encyclopaedia_parents
    flags its own, so the country's gate weighs the unit's own figure
    (control_population) whichever pass restated it.

    The sole-division pass gives Burkina Faso's Centre, Guinea's Conakry and
    Benin's Littoral their one division's OCHA figure. Unflagged, Centre's
    3,510,028 for 2023 in place of Wikipedia's 3,030,384 for 2019 brought
    Burkina Faso's regions within the gate of the Factbook's figure, and their
    survey shares replaced its census and Factbook lines.
    """
    marked: list[str] = []
    for iso3, units in sorted(admin1_by_country.items()):
        for unit in units:
            pop = unit.get("population")
            was = before.get((iso3, unit.get("id")))
            if not isinstance(pop, dict) or was is None or RESTATED_FROM in pop:
                continue
            if (published(pop), vintage(pop)) != (published(was), vintage(was)):
                pop[RESTATED_FROM] = {k: was[k] for k in ("value", "year", "source")
                                      if k in was}
                marked.append(f"{iso3} {unit.get('name')}")
    return marked


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


def counted_total(groups: list[dict[str, Any]]) -> float | None:
    """The people a composition's counts are of, where they are all of them.

    implied_total backs the base out of one group's rounded percentage, which
    is right where the rows count part of it -- Mexico's speakers of an
    indigenous language, three and over -- and a little off where they count
    everyone: Kuwait's governorates count 4,381,139 people by nationality, and
    their sum's note said 4,381,064, under a population note giving 4,381,139.
    Where the counts add up to the backed-out base within what the rounding of
    that percentage allows, they are the whole of it, and their sum is the
    base exactly.
    """
    implied = implied_total(groups)
    if implied is None:
        return None
    counts = [row.get("count") for row in groups]
    if not all(isinstance(c, (int, float)) for c in counts):
        return implied
    best = max((row for row in groups if isinstance(row.get("pct"), (int, float))
                and row["pct"] > 0), key=lambda row: row["count"], default=None)
    if best is None:
        return implied
    slack = implied * (0.05 / best["pct"] + 1e-6)
    whole = float(sum(counts))
    return whole if abs(whole - implied) <= slack else implied


def repriced_sentence(repriced: list[tuple[str, Any]]) -> str:
    """What a sum says of the divisions whose shares were taken of the figure
    they carried before the newer one shown: "For Tbong Khmum the population
    taken is 776,841 for 2019, the figure it carried before the newer one
    shown." Empty where there are none."""
    if not repriced:
        return ""
    if len(repriced) == 1:
        name, was = repriced[0]
        value, year = published(was), vintage(was)
        return (f" For {name} the population taken is {value:,.0f}"
                + (f" for {year}" if year else "")
                + ", the figure it carried before the newer one shown.")
    names = sorted(name for name, _ in repriced)
    listed = (", ".join(names[:-1]) + f" and {names[-1]}" if len(names) <= 4
              else ", ".join(names[:3]) + f" and {len(names) - 3} others")
    return (f" For {listed} the populations taken are the figures they "
            f"carried before the newer ones shown.")


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
        if pop is None and not has:
            # A count refused only because the polygon is not its ground
            # (NOT_THIS_GROUND) still says how many people the unit has:
            # Laayoune-Sakia El Hamra's 451,028, most of whom live across the
            # Western Sahara line from the strip drawn under its name. Weighed
            # in, it can only understate the share the others cover.
            held = child.get("population")
            pop = held.get("refused_value") if isinstance(held, dict) else None
        if pop is None:
            if not has:
                return None
            continue
        total += pop
        if has:
            covered += pop
    return covered / total if total > 0 else None


def year_sort_key(year: Any) -> tuple[int, str]:
    """A year or year span ("2008-2014") as a sortable key: its first four-digit year."""
    m = re.search(r"\d{4}", str(year))
    return (int(m.group()) if m else 0, str(year))


def counted_noun(basis: Any) -> str:
    """What the divisions' own counts are counts of, for the roll-up's note.

    People, unless the basis every division counts on says otherwise.
    Suriname's districts count households by the language most spoken in
    them, and the country's note read "the divisions' own counts, of 123,416
    people in 2004" above a sentence saying they are households. Gilgit-
    Baltistan's survey, which counts the language of each household's head,
    counts households too.
    """
    said = basis.casefold() if isinstance(basis, str) else ""
    return ("households" if said.startswith("households") or "household head" in said
            else "people")


def roll_up_field(parent: dict[str, Any], children: list[dict[str, Any]],
                  field: str, *, level: str = "second-level",
                  over_published: bool = False,
                  whole_country: bool = False,
                  complete: bool | None = None,
                  min_coverage: float | None = None,
                  fill_population_only: bool = False) -> str | None:
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

    ``fill_population_only`` keeps a published population whatever the
    children add up to, and lets their total fill only a unit that has none:
    a country shows the Factbook's estimate, and its first level's sum, of
    whatever year, does not replace it (roll_up_countries). Elsewhere an older
    figure gives way to the children's newer total; one of their own year does
    not, because children of the same year that add up to something else are
    short of a child or counted apart, not better: Kinmen's five drawn
    townships made 136,611 against the county's registered 137,208 -- the
    register's sixth township, Wuqiu, is drawn apart from it.
    """
    current = parent.get(field)
    if isinstance(current, list) and not over_published:
        return None                                   # already has a real value
    # A policy statement, not a gap: it stands -- unless every division drawn
    # inside the unit carries a measured composition, which is then summed
    # like any other and the statement opens its note. Greece's census has not
    # asked religion or language since 1951, so its first level says so, but
    # the thirteen regions drawn below it carry the European Social Survey's
    # figures the country itself shows: five first-level units whose every
    # region had them were left saying "not collected" over their children.
    # A country's statement stands whatever its regions carry: the country
    # takes its survey figures from its own curated row, not from a sum.
    policy_note = None
    if isinstance(current, dict) and current.get("status") == NOT_COLLECTED:
        if (over_published or not children
                or not all(isinstance(c.get(field), list) for c in children)):
            return None
        policy_note = current.get("note")
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
    if usual in UNSUMMED_BASES:
        return (f"{field}: its divisions carry {usual} estimates, which are not "
                f"added up into a figure for the unit")

    # A division that names only its largest group has not published a
    # composition, and largest groups do not add up to one. Papua New Guinea's
    # provinces each carry the "Main religion" row of the 2011 census --
    # Bougainville Roman Catholic 68.4%, Central Province United Church 40.0%
    # -- and their sum made the country 15.4% Catholic and left out every
    # denomination that is nowhere the largest, over the census's own national
    # figure of 26%. One such division among many costs the sum little
    # (Appenzell Innerrhoden among Switzerland's 26 cantons); when they are
    # half of it, the sum is of winners, not of people.
    listed = [c for c in children if isinstance(c.get(field), list)]
    lone = [c for c in listed if len(c[field]) == 1
            and (c[field][0].get("pct") or 0) < SOLE_GROUP_WHOLE]
    if lone and 2 * len(lone) >= len(listed):
        return (f"{field}: {len(lone)} of {len(listed)} children publish only "
                f"their largest group, and largest groups do not add up to a "
                f"composition")

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

    # A survey's counts are its respondents, not the division's people. Added
    # to one another they weigh each division by its interviews, which a
    # national sample drawn in proportion to population roughly makes right.
    # Added to counts of people they are simply wrong: a division priced at
    # its population, or counted by a census, weighs as millions against the
    # others' hundreds. That is how Tanzania's languages came out as Swahili
    # 54.8% and Sukuma 45.1% -- Katavi, priced at its population, against
    # 2,268 interviews everywhere else. So where one sum would mix the two,
    # each division's shares are taken of its own population instead, which
    # is how regional shares combine into a whole; and where a division has
    # no population to take them of, the mixture is refused.
    bases = [implied_total(c[field]) for c in children]
    sampled = [c.get("name", c.get("id", "?"))
               for c, pop, base in zip(children, kid_pop, bases)
               if pop and base is not None and base < SAMPLE_SHARE * pop]
    weighted = 0 < len(sampled) < len(children)
    if weighted and unpriced:
        return (f"{field}: {len(sampled)} children count a survey's respondents "
                f"and the rest count people, and {unpriced} have no population "
                f"to weigh them by")

    disagrees = ""
    # Whether the sum stands although the gate below found the populations
    # apart: a waived control, which no population is then taken from.
    overruled = False
    # Weighed against the count curated beside a country's Factbook estimate
    # where there is one (gate_population); every sentence below that quotes
    # the figure says which it is.
    gate = gate_population(parent)
    shown = published(parent.get("population"))
    own = published(gate)
    stated = shown
    beside = (gate is not parent.get("population") and own is not None
              and shown is not None and own != shown)
    unit_figure = (f"{named_figure(gate)}, the figure this sum is checked against; the "
                   f"population shown is {named_figure(parent.get('population'))}"
                   if beside else f"a published {own:,.0f} for the unit"
                   if own is not None else "")
    if (unpriced or not total_pop) and own is not None and over_published \
            and shares_of(current):
        # A sum that would replace a published composition is checked against
        # the unit's own population, and with a division unpriced there is no
        # total to check. Skipping the check here let one missing figure
        # decide the matter: Angola's national composition was replaced the
        # day Moxico's population was taken off as its capital's, although
        # with Moxico priced the same sum is refused, 11% short of the
        # country's published population.
        return (f"{field}: {unpriced} of {len(children)} children have no "
                f"population, so the sum cannot be checked against the "
                f"published {own:,.0f}")
    if unpriced or not total_pop:
        # No usable control, and none needed: every shape at this level in the
        # country carries the field, so the children partition it.
        own = None
    if own is None:
        if not complete:
            return f"{field}: no published population to check the sum against"
    else:
        # Weighed on the figures the divisions carry for themselves, before any
        # was restated to its own divisions' sum (control_population); the
        # note below still quotes the populations the map shows.
        controls = [{"population": control_population(c)} for c in children]
        gated = sum(published(c["population"]) or 0.0 for c in controls)
        limit = allowance(vintage(gate), common_year(controls), own, gated)
        if abs(gated - own) > limit * own:
            overruled = True
            drift = "" if limit == ROLLUP_TOLERANCE else \
                f", outside even the {limit:.0%} allowed for their dates"
            # Complete children and a parent figure that disagrees with them
            # means the parent's figure is the doubtful one, not the set: Dhaka
            # division carries a 2011 population of 49,729,000 and lost
            # Mymensingh out of it in 2015, so its 44,215,759 people in 2022 are
            # not a shortfall. The sum is taken and the disagreement is written
            # into the note rather than hidden by it.
            #
            # A country with no shares of its own is the other case. The gate
            # is there so a sum does not overrule a published figure on the
            # strength of children that may not be all of it -- and where the
            # children are the country's divisions and the country publishes
            # only a list of names, there is nothing to overrule, and the gap
            # is a census against a later estimate. Tanzania's regions carry
            # 2012 and 2022 counts that total 60.4 million against the
            # Factbook's 69.1 million for 2025; refusing them left Tanzania
            # with no language shares at all.
            if not whole_country and (not complete or shares_of(current)):
                return (f"{field}: children sum to {gated:,.0f} against a "
                        f"published {own:,.0f}{drift}"
                        + (f" (their figures before their divisions' sums were put "
                           f"on them; they now total {total_pop:,.0f})"
                           if round(gated) != round(total_pop) else ""))
            # The sentence names the total it is measured against rather than
            # pointing back at "that": other sentences can stand between the
            # two -- the divisions' own counts, a weighting -- and Italy's
            # note then read "...own counts, of 57,251,233 people in 2015. The
            # unit's own published population of 60,924,851 disagrees with
            # that by -3%", a gap that is -6% against the figure just named.
            # It is the total the map shows, and it is said only where that
            # one disagrees too: a first level restated to its divisions'
            # sums can agree with the unit where its own figures did not.
            if abs(total_pop - own) > ROLLUP_TOLERANCE * own:
                disagrees = ((f" The figure this sum is checked against, "
                              f"{named_figure(gate)}," if beside else
                              f" The unit's own published population of {own:,.0f}")
                             + f" disagrees with the divisions' total of "
                             f"{total_pop:,.0f} by "
                             f"{100 * (total_pop - own) / own:+.0f}%; "
                             + ("the sum was taken anyway because every division "
                                "at this level in the country carries these "
                                "figures, so these are certainly all of its "
                                "children." if whole_country else
                                "the sum was taken anyway because these are the "
                                "country's own divisions and it publishes no "
                                "shares of its own for the sum to overrule."))

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
    # Years are sorted by their first four-digit year, so a span a source
    # writes as text ("2008-2014", Afghanistan's district profiles) sorts
    # beside the integer years of a sibling file instead of breaking the sort.
    aside = sorted(((y, n) for y, n in (
        (c.get(f"{field}_year"), c.get("name", c.get("id", "?")))
        for c in children if isinstance(c.get(field), list))
        if y is not None and y != dated), key=lambda t: (year_sort_key(t[0]), t[1]))

    counts: dict[str, float] = {}
    denominator = 0.0
    # Children whose shares had to be priced against their own population
    # because the source published no counts. Named in the note: a sum of
    # derived numbers is a weaker claim than a sum of published ones.
    derived: list[str] = []
    # Those of them priced at the figure they carried before a newer one was
    # shown (control_population), named with it in the note.
    repriced: list[tuple[str, Any]] = []
    for child in children:
        share = counted_total(child[field])
        rows = child[field]
        priced = all(isinstance(r.get("count"), (int, float)) for r in rows)
        if not priced or weighted:
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
            #
            # The population is the one the unit carried before a newer figure
            # took its place, where one did (control_population), as the gate
            # above weighs it: a census's shares are of that census's people.
            # Cambodia's 25 provinces publish the 2019 census's shares, and two
            # of them showing 2024 figures moved the country's Muslims from the
            # census's 2.0% to 2.1% under the census's date.
            control = control_population(child)
            pop = published(control)
            if pop is None:
                return f"{field}: a child publishes shares with no counts"
            rows = [dict(r, count=(r["pct"] / 100.0) * pop)
                    for r in rows if isinstance(r.get("pct"), (int, float))]
            share = implied_total(rows)
            derived.append(child.get("name", child.get("id", "")))
            if control is not child.get("population"):
                repriced.append((child.get("name", child.get("id", "")), control))
        if share is None:
            return f"{field}: a child publishes shares with no counts"
        denominator += share
        for row in rows:
            count = row.get("count")
            if not isinstance(count, (int, float)):
                return f"{field}: a child publishes shares with no counts"
            counts[row.get("group", "")] = counts.get(row.get("group", ""), 0) + count
    # One group spelled two ways by two divisions is still one group: Kenya's
    # counties write both "MijiKenda" and "Mijikenda", and their sum printed
    # the two as separate rows. Folded only where both spellings are in this
    # sum, so a sum that uses one spelling keeps the source's.
    variants = VARIANTS.get(field, {})
    for name in [n for n in counts if variants.get(n, n) != n
                 and variants[n] in counts]:
        counts[variants[name]] += counts.pop(name)
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
    if shares_of(current):
        # A group the source names without a share is named alone: Ireland's
        # English, beside Irish 37.7%, read "English None%".
        top = ", ".join(f"{g.get('group')} {g.get('pct')}%"
                        if isinstance(g.get("pct"), (int, float)) else str(g.get("group"))
                        for g in current[:3])
        displaced = (f" Replaces a separately published figure for the unit "
                     f"({top}), which is kept here as the only independent "
                     f"check on this sum.")
    elif isinstance(current, list) and current:
        # A list of names is not a figure, and printing it as one read
        # "Kiswahili or Swahili None%".
        named = ", ".join(str(g.get("group")) for g in current[:3])
        displaced = (f" Replaces a list that names groups without shares "
                     f"({named}{', ...' if len(current) > 3 else ''}), which "
                     f"gives this sum nothing to be checked against.")
    # The people the added counts are of, where that is not the populations the
    # note quotes. Kazakhstan's regions carry the register's 2025 populations
    # and the 2021 census's religion, which counts 19.2 million people, not
    # their 20.3 million; Tajikistan's carry 2020 populations and the 2010
    # census's nationalities. Quoting only the populations put a total and a
    # year on the figure that are not its own.
    # Not where every division's figures are its shares taken of a population:
    # those are no division's counts, and the sentences below say which
    # populations they were taken of.
    # Nor where some are: Indonesia's 34 provinces, 32 of them shares taken
    # of a population, read "The figures added are the divisions' own
    # counts", followed by the sentence saying 32 have none. The sentence on
    # the derived ones says what was added.
    counted = ""
    if (not weighted and denominator > 0 and total_pop and not derived
            and abs(denominator - total_pop) > ROLLUP_TOLERANCE * total_pop):
        when = (f" in {next(iter(years))}" if len(years) == 1 else
                f", nearly all of them in {dated}" if dated is not None else "")
        counted = (f" The figures added are the divisions' own counts, of "
                   f"{denominator:,.0f} {counted_noun(usual)}{when}.")
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
           f" against {unit_figure}."
           if own is not None else
           (f" {'they publish' if many else 'it publishes'} no population of "
            f"{'their' if many else 'its'} own, and"
            if unpriced == len(children) else
            f" {unpriced} of them publish no population, so their total is not "
            f"known, and" if unpriced else
            f" {'Their' if many else 'Its'} population"
            f"{'s total' if many else ' is'} {total_pop:,.0f}, and")
           + (" no source publishes a population for the unit to check that "
              "against" if stated is None else
              f" the unit's own published {stated:,.0f} cannot be checked "
              f"against it")
           + "; it was summed because every division at this level in "
             "the country has these figures, so these are all of its children.")
        + counted
        + (f" Weighted by population: {len(sampled)} of them count a survey's "
           "respondents and the rest count people, so every division's shares "
           "are taken of its own published population." if weighted else
           f" {len(derived)} of them publish shares and no counts"
           f"{' (' + ', '.join(sorted(derived)[:3]) + ')' if len(derived) <= 3 else ''}"
           ", so their counts are those shares taken of their own published "
           "populations." if derived else "")
        + repriced_sentence(repriced)
        + disagrees + displaced + left_out
        + (" " + ", ".join(sorted(c.get("name", c.get("id", "?"))
                                  for c in apart))
           + (f" counts {apart[0].get(f'{field}_basis')} rather than what the "
              f"others count, so it is not added in; its own figure is shown "
              f"on it." if len(apart) == 1 else
              " count something the others do not, so they are not added in.")
           if apart else "")
        + (f" Dated {dated} because that is when all but"
           f" {', '.join(f'{n} ({y})' for y, n in aside)} were counted."
           if dated is not None else
           f" The divisions do not all report the same year"
           f" ({', '.join(str(y) for y in sorted(years, key=year_sort_key))}),"
           f" so this figure carries no single date."
           if len(years) > 1 else
           " The divisions do not date their figures, so neither does this."
           if not years else "")
        # Korea's provinces count nationality on the ethnicity field, and
        # the country's sum of them does too: without the basis it read as
        # a count of ethnicity.
        + (f" {basis_sentence(usual, field)}" if usual else ""))
    if policy_note:
        parent[f"{field}_note"] = f"{policy_note} {parent[f'{field}_note']}"
    if usual:
        parent[f"{field}_basis"] = usual
    else:
        parent.pop(f"{field}_basis", None)
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
    # should carry their population too, when it has none or an older one.
    #
    # Bangladesh is the older case: two of its divisions publish no population
    # at all and six publish 2011 figures, so the level above was summing a
    # mixture of vintages -- six 2011 divisions and two 2022 ones -- and
    # comparing that mongrel against a 2025 estimate.
    #
    # A newer figure still wins, because a later estimate of a place is not
    # something an older count should overwrite. The figure replaced goes into
    # a note.
    #
    # A country is the exception (``fill_population_only``): it shows the
    # Factbook's estimate, one moment for every country, and its first level
    # fills it only where it has none. Finland's nineteen regions total
    # 5,652,881 for 2025 from Statistics Finland's register, and the country
    # shows the Factbook's 5,550,449 for 2025 beside them.
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
    # Not where the sum stood only because the population check was waived,
    # nor where a division was left out. In the first the two populations
    # were just found to disagree, and in the second the total is of part of
    # the country; either way it is not the country's population. Taken
    # anyway, it became the control for the next field: Guinea's languages,
    # summed past an 18% gap, set its population to their 11.8 million, and
    # its ethnicity then "agreed" with that and overwrote the Factbook's
    # shares. Morocco lost Laayoune-Sakia El Hamra from its population the
    # same way.
    waived = overruled and not whole_country
    # And only a sum of about one year replaces a figure that exists: years at
    # most one apart, or nine in ten of the people counted in the same one.
    # Germany's states carry Eurostat's 2025 figures where a state is its own
    # NUTS region and the 2022 census elsewhere -- 78% of Germans on 2022 --
    # and their total of 82.9 million is no one year's count; it once replaced
    # the country's 2025 estimate of 84.0 million as though it were. The
    # Netherlands (96% on 2025) and Peru (2025 and 2026) are sums of one
    # moment; Germany's is not. A mixed sum still fills a unit that has
    # nothing.
    stamped = [(vintage(c.get("population")), published(c.get("population")) or 0.0)
               for c in children]
    years_seen = [y for y, _ in stamped if y is not None]
    on_child_year = sum(v for y, v in stamped if y == child_year)
    one_year = bool(years_seen) and (
        max(years_seen) - min(years_seen) <= 1
        or on_child_year >= ONE_MOMENT * sum(v for _, v in stamped))
    # A published figure is replaced only where it is older than the children's
    # and the caller lets a sum replace one at all (``fill_population_only``).
    if child_year and not waived and not left_out and (
            own is None or (not fill_population_only and one_year
                            and round(total_pop) != round(own)
                            and (own_year is None or own_year < child_year))):
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


def fill_parent_populations(admin1_by_country: dict[str, list[dict[str, Any]]],
                            admin2_by_country: dict[str, list[dict[str, Any]]]) -> list[str]:
    """A first-level unit with no population, filled from all of its divisions.

    Angola's Moxico is the case: its Wikidata figure was the province cut down
    in 2024, on the old province's ground, and was left out; OCHA counts every
    one of the nine municipalities the old province is drawn with. Only a
    unit with nothing is filled, only when every division it holds carries a
    population, and the record says it is a sum. Run after the compositions
    are summed, so a sum is never the control it is checked against.
    """
    filled: list[str] = []
    for iso3, parents in admin1_by_country.items():
        if (iso3, "admin2") in PARTIAL_LEVELS:
            continue
        kids: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for entity in admin2_by_country.get(iso3, []):
            if not entity.get("water"):
                kids[entity.get("parent")].append(entity)
        for parent in parents:
            pop = parent.get("population")
            if not (isinstance(pop, dict) and pop.get("status") == NOT_AVAILABLE):
                continue
            # A gap whose adapter says the divisions linked to it do not make
            # its polygon either: Afghanistan's provinces where a district's
            # point falls across the province's edge, whose linked districts
            # are not the ground drawn (afghanistan_estimates' POINT_ELSEWHERE).
            if pop.get("no_child_sum"):
                continue
            children = kids.get(parent["id"], [])
            values = [published(c.get("population")) for c in children]
            if not children or any(v is None for v in values):
                continue
            years = {vintage(c.get("population")) for c in children}
            year = years.pop() if len(years) == 1 and None not in years else None
            # Named as a sentence can name them: cut at sixty characters, OCHA's
            # dataset ended "population statistics (c)." under Moxico and
            # Vatovavy-Fitovinany.
            names = ", ".join(sorted({check_rollups.short_source(
                str(c["population"].get("source") or "")) for c in children}))
            parent["population"] = {
                "value": int(round(sum(values))),
                **({"year": year} if year else {}),
                "source": f"summed from {len(children)} second-level divisions",
                "note": (f"No figure is published for this unit that describes its "
                         f"ground; this is the sum of all {len(children)} divisions "
                         f"drawn inside it ({names})."
                         + ("" if year else " They are not all counted in one year, "
                            "so the sum carries no year.")
                         + (" " + pop["note"] if pop.get("note") else ""))}
            # The sum cites what it adds up, and the figure left out is no
            # longer cited for the population: Moxico listed Wikidata for
            # "population/capital/coordinates" and nothing for OCHA's
            # municipalities, whose figures the sum is.
            kept = []
            for src in parent.get("sources", []):
                cites = cited_fields(src)
                if "population" not in cites:
                    kept.append(src)
                elif set(cites) - {"population"}:
                    kept.append(dict(src, field="/".join(f for f in cites
                                                         if f != "population")))
            for child in children:
                # The entry that is the source of the figure shown, where one
                # says so: a division's Wikidata item can still be cited for
                # "population/capital/coordinates" beside OCHA's figure.
                cited = [src for src in child.get("sources", [])
                         if "population" in cited_fields(src)]
                naming = [src for src in cited if names_source(src, child.get("population"))]
                for src in naming or cited:
                    entry = dict(src, field="population")
                    if entry not in kept:
                        kept.append(entry)
            parent["sources"] = kept
            filled.append(f"{iso3} {parent['name']}")
    return filled


# Countries whose first level keeps an encyclopaedia's figure over divisions of
# a later year, because the divisions' source is the older account. Zimbabwe's
# provinces carry ZIMSTAT's 2022 census as Wikipedia and Wikidata print it
# (Mashonaland Central an older figure), and its districts OCHA's table for
# 2023, a projection: the districts add up to 17,408,564 against the
# provinces' 14,961,031, and to more than the census counted in every province
# that carries its count (by 4% to 27%). A later reference year, an older
# account. The province's note says what its districts add up to instead, and
# why the two differ.
RESTATE_KEEPS: dict[str, str] = {
    "ZWE": "the districts carry OCHA's projection for 2023, which runs above the 2022 "
           "census's count in every province that carries one",
}

# Divisions drawn by area under a first-level unit other than the one their
# census counts them in, and not yet filed where they belong: (country, shape
# id) -> (division, the unit that counts it). While one is filed away from its
# unit, neither the unit holding it nor the unit missing it is restated to its
# divisions' sum, which would count one unit's people as another's. Empty:
# Mangochi (OCHA's 1,346,740, by area under Malawi's Northern Region, across
# the lake from the Southern Region that counts it) and Mukwe (29,965, by area
# under Namibia's Caprivi, though it is Kavango East's) were here, and
# DECLARED_PARENTS now files both where their census counts them, so their
# units take their divisions' sums. An entry belongs here only until its
# division is so filed.
MISFILED_DIVISIONS: dict[tuple[str, str], tuple[str, str]] = {}

# What a restated unit's earlier note said about how the map draws it, which
# the restatement's own note replaces: the divisions' sum is still of that
# ground, and the reader still needs to be told what the ground is. A unit
# whose earlier note said its count was put together for the polygon and that
# has no sentence here is named in the build log.
RESTATED_GROUND: dict[tuple[str, str], str] = {
    ("MOZ", "Maputo"): "The map draws Maputo City and Maputo Province as one shape.",
    ("LVA", "Madonas novads"): "Madona and Varakļāni merged on 1 July 2025 and are drawn "
                               "apart; these are the parishes and towns of Madona as it "
                               "was before.",
    ("LVA", "Varakļānu novads"): "Varakļāni merged into Madona on 1 July 2025 and the two "
                                 "are drawn apart; these are the parishes and town of "
                                 "Varakļāni as it was before.",
}

# A projection dated a year after the parent's figure is not a later account
# of the same people but another account of the same moment: where the two
# differ, the projection rests on an older base. Rwanda's provinces carry the
# 2022 census (Eastern Province 3,563,145) and OCHA's districts a projection
# for 2023 that puts 3,948,191 there and 10% fewer in the Northern Province
# than the census counted. A projection replaces only a figure at least this
# many years older; the parent keeps its figure otherwise, and a gap over 15%
# is said like any other.
RESTATE_PROJECTION_YEARS = 2

# First-level units drawn as one division on the same ground, whose
# encyclopaedia figure the count of that ground contradicts by more than any
# growth: the unit shows its division's count, and the note says why the other
# figure goes. Venezuela's Capital District is the municipality of Libertador
# and nothing else; the infobox of its Wikipedia article gives 3,523,959 for
# 2020 -- 81% above the 2011 census's 1,943,901 for the same ground -- while the
# same article's text gives 2,073,768 for 2004. The year rule cannot settle it
# (the encyclopaedia's figure is the newer), and two figures for one ground
# 81% apart cannot both be right.
RESTATE_SOLE_DIVISION: dict[tuple[str, str], tuple[str, str]] = {
    ("VEN", "Distrito Capital"): (
        "The Capital District is the municipality of Libertador, the one division "
        "drawn inside it, so this is Libertador's count.",
        "the same article gives the district 2,073,768 people in 2004"),
}


def restate_encyclopaedia_parents(admin1_by_country: dict[str, list[dict[str, Any]]],
                                  admin2_by_country: dict[str, list[dict[str, Any]]],
                                  *, counts: bool = False) -> list[str]:
    """A first-level unit whose population an encyclopaedia gives, over divisions
    that all carry one source's figures of one later year, takes their sum.

    Burundi's provinces carried Wikidata's 2008 census figures and its 119
    communes OCHA's 2022 table, so the provinces added up to 12.1 million and
    the country's provinces to 8.4; Namibia's regions, Benin's departments,
    Sudan's states and some 120 more sat the same way, the parent a different
    source a decade older than the divisions drawn inside it. An encyclopaedia
    never replaces a count, and here it is the other way round: the divisions'
    own figures, one source and one year, are the better account of the
    parent, and the figure replaced goes into the note.

    Only where every non-water division carries a figure (a partial sum is not
    the unit), where all of them share one source that is not itself an
    encyclopaedia and one year later than the parent's (or the parent gives
    none), and where there are at least two of them -- a unit drawn as a single
    division is its own ground or a misfiled one, and is left to the passes
    that weigh that, except where ``RESTATE_SOLE_DIVISION`` declares the
    division the unit's whole ground and the encyclopaedia's figure not that
    ground's. A unit whose count takes in ground the map does not draw
    (``UNDRAWN_PARTS``) keeps its count, since its divisions are not all of it,
    and so do two units between which a division is drawn on the wrong side
    (``MISFILED_DIVISIONS``), and a dated figure that a projection only a year
    later would replace (``RESTATE_PROJECTION_YEARS``).

    ``counts`` takes the same sum over an office's dated count of an earlier
    year too: a subdivision shows the most recent figure available (the
    owner's rule since round 7). Laos's provinces carry the 2015 census and
    their districts OCHA's projection of it for 2024. A count gives way only
    where the years between it and the sum could make the one the other
    (check_rollups.growth_explains); a sum further off is of other ground
    than the count, and the parent's note says what its divisions add up to
    instead.
    """
    done: list[str] = []
    for iso3, parents in sorted(admin1_by_country.items()):
        if (iso3, "admin2") in PARTIAL_LEVELS or iso3 in RESTATE_KEEPS:
            continue
        kids: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for entity in admin2_by_country.get(iso3, []):
            if not entity.get("water"):
                kids[entity.get("parent")].append(entity)
        for parent in parents:
            pop = parent.get("population")
            own = published(pop)
            counted = not check_rollups.is_encyclopaedic(pop)
            if (own is None or parent.get("water") or (counted and not counts)
                    or (iso3, parent.get("name")) in UNDRAWN_PARTS):
                continue
            children = kids.get(parent["id"], [])
            name = parent.get("name")
            held = {c.get("id") for c in children}
            if any(MISFILED_DIVISIONS.get((iso3, c.get("id")), (None, name))[1] != name
                   for c in children) or any(
                    home == name and shape not in held
                    for (iso, shape), (_, home) in MISFILED_DIVISIONS.items() if iso == iso3):
                continue
            summed = check_rollups.complete_sum(children)
            declared = None if counted else RESTATE_SOLE_DIVISION.get((iso3, parent.get("name")))
            if summed is None or summed["n"] < (1 if declared else 2):
                continue
            if declared and summed["n"] != 1:
                raise SystemExit(f"RESTATE_SOLE_DIVISION: {iso3} {parent.get('name')} is "
                                 f"drawn with {summed['n']} divisions, not one")
            if len(summed["sources"]) != 1 or len(summed["years"]) != 1:
                continue
            source, year = next(iter(summed["sources"])), next(iter(summed["years"]))
            if not source or year is None or check_rollups.is_encyclopaedic({"source": source}):
                continue
            own_year = vintage(pop)
            # A sum of the same year as the figure shown is no newer, and does
            # not replace it, even where that figure is an encyclopaedia's that
            # prefer_newer_figures put in front of a count. Jambi's eleven
            # regencies carry the civil register's figures for 2024, which add
            # up to 3,819,233; Wikidata's 3,724,300 for 2024 is BPS's own
            # projection in thousands, as it is for the other thirty provinces
            # that show 2024, and the register counts on a different basis.
            if not declared and own_year is not None and year <= own_year:
                continue
            if (not declared and own_year is not None and projection({"source": source})
                    and year - own_year < RESTATE_PROJECTION_YEARS):
                continue
            total = int(round(summed["total"]))
            if total == round(own):
                continue
            if counted and (own_year is None
                            or not check_rollups.growth_explains(own, own_year, total, year)):
                continue
            # The note names the count the unit showed, not a newer figure
            # prefer_newer_figures put in front of it in this same build and
            # no published map showed: Xiangkhouang's 2015 census, not the
            # Wikidata 2020 figure it held.
            counted_as = (pop[RESTATED_FROM] if isinstance(pop.get(RESTATED_FROM), dict)
                          else pop)
            was_value = published(counted_as) if published(counted_as) is not None else own
            was_year = vintage(counted_as) if counted_as is not pop else own_year
            was = named_source(str(counted_as.get("source") or ""))
            said_before = " ".join(str(text or "") for text in (
                parent.get("population_note"), pop.get("note")))
            ground = RESTATED_GROUND.get((iso3, name))
            if ground is None and composed(said_before):
                log(f"  restate: {iso3} {name}'s earlier note said its count was put "
                    f"together for the polygon, and RESTATED_GROUND says nothing")
            if declared:
                # The division's own figure, as it stands, on its parent.
                parent["population"] = {k: v for k, v in children[0]["population"].items()
                                        if k in ("value", "unit", "year", "source")}
                lead, why_not = declared
                side = "above" if was_value > total else "below"
                parent["population_note"] = (
                    f"{lead} It replaces {was_value:,.0f}"
                    + (f" for {was_year}" if was_year else "")
                    + f" from {was}, {abs(was_value / total - 1):.0%} {side} this count of "
                      f"the same ground; {why_not}.")
            else:
                parent["population"] = {"value": total, "year": year,
                                        "source": f"summed from {summed['n']} second-level "
                                                  f"divisions"}
                every = "both" if summed["n"] == 2 else f"all {summed['n']}"
                parent["population_note"] = (
                    f"The sum of {every} divisions drawn inside it, which all carry "
                    f"figures for {year} from {named_source(source)}. It "
                    f"replaces {was_value:,.0f}"
                    + (f" for {was_year}, an older figure from {was}." if was_year else
                       f" from {was}, which gives no year for it."))
            if ground:
                parent["population_note"] = f"{ground} {parent['population_note']}"
            # What the unit carried before, for the country's composition gate
            # (control_population); a build flag, not written. A count a newer
            # figure already stood in front of stays the one carried.
            parent["population"][RESTATED_FROM] = (
                dict(pop[RESTATED_FROM]) if isinstance(pop.get(RESTATED_FROM), dict)
                else {k: pop[k] for k in ("value", "year", "source") if k in pop})
            # The source goes with the figure: an entry citing the population
            # alone goes, and one citing other fields too stays for those
            # alone. Sierra Leone's Northern Province listed Wikidata for
            # "population/capital/coordinates" beside OCHA's population.
            kept = []
            for src in parent.get("sources", []):
                cites = str(src.get("field") or "").split("/")
                if "population" not in cites:
                    kept.append(src)
                elif set(cites) - {"population"}:
                    kept.append(dict(src, field="/".join(f for f in cites
                                                         if f != "population")))
            parent["sources"] = kept
            # Every division's own entry, as fill_parent_populations has it:
            # North Kalimantan's five regencies each cite their own article,
            # and the province cited Bulungan's alone.
            for child in children:
                for src in child.get("sources", []):
                    entry = dict(src, field="population")
                    if ("population" in cited_fields(src) and src.get("name") == source
                            and entry not in parent["sources"]):
                        parent["sources"].append(entry)
            done.append(f"{iso3} {parent['name']} {own:,.0f} -> {total:,}")
    return done


# Units whose population is a bare gap and whose reason is known: the area
# Sudan and South Sudan both claim, drawn inside Sudan's first level and again
# at its second, which no count may cross into. The reason is the disputed
# areas' own.
STATED_POPULATION_GAPS: dict[tuple[str, str], str] = {
    ("SDN", "Abyei PCA"): "disputed",
    ("SDN", "Abyei PCA area"): "disputed",
}


def state_population_gaps(admin0: list[dict[str, Any]],
                          *tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Say why a population is empty where the reason is known and nothing said it.

    Antarctica has no permanent population, which its country record says;
    its one drawn unit at each level said only that Wikidata gives it no
    figure. A country whose population is not applicable passes that down to
    every unit drawn inside it, with the median age and sex ratio, which have
    no one to describe either. ``STATED_POPULATION_GAPS`` names the rest.
    """
    not_applicable = {c["id"]: c["population"] for c in admin0
                      if isinstance(c.get("population"), dict)
                      and c["population"].get("status") == NOT_APPLICABLE}
    said: list[str] = []

    def bare(value: Any) -> bool:
        return is_gap(value) and not (isinstance(value, dict) and value.get("note"))

    for table in tables:
        for iso3, rows in table.items():
            for entity in rows:
                reason = None
                if iso3 in not_applicable:
                    reason = dict(not_applicable[iso3])
                elif STATED_POPULATION_GAPS.get((iso3, entity.get("name"))) == "disputed":
                    # A population that already says why goes with its ages:
                    # Sudan's "Abyei PCA" is a 41 km2 edge of the Abyei Area,
                    # not the disputed ground itself, and says so.
                    own = entity.get("population")
                    reason = (dict(own) if is_gap(own) and isinstance(own, dict)
                              and own.get("note") else gap(NOT_AVAILABLE, DISPUTED_GAP))
                if reason is None:
                    continue
                changed = False
                for field in ("population", "median_age", "sex_ratio"):
                    if bare(entity.get(field)):
                        entity[field] = dict(reason)
                        changed = True
                if changed:
                    said.append(f"{iso3} {entity.get('name')}")
    return said


def country_from_sole_unit(admin0: list[dict[str, Any]],
                           admin1_by_country: dict[str, list[dict[str, Any]]]
                           ) -> list[str]:
    """A country with no population takes its one first-level unit's figure.

    A unit that covers all of the country and nothing else, measured on the
    boundary file, is the country's ground, so its figure is the country's.
    Western Sahara was the case until the Factbook reader took the figure its
    profile gives in an older layout ("652,271 (July 2020 est.)", with no
    total under it; fetch_factbook.build_record): its one unit carries the
    UN's 2021 estimate, and the country now shows the Factbook's.
    The disputed areas, each drawn as a country of one unit, are left alone:
    their record already says why nothing is joined to them, and that is what
    the panel shows. A country whose population is not applicable keeps that.
    """
    done: list[str] = []
    for country in admin0:
        if country.get("disputed"):
            continue
        pop = country.get("population")
        if published(pop) is not None or (isinstance(pop, dict)
                                           and pop.get("status") == NOT_APPLICABLE):
            continue
        units = [u for u in admin1_by_country.get(country["id"], []) if not u.get("water")]
        if len(units) != 1 or published(units[0].get("population")) is None:
            continue
        unit = units[0]
        country["population"] = {k: v for k, v in unit["population"].items()
                                 if k in ("value", "unit", "year", "source")}
        country["population_note"] = (
            "The figure of the one first-level unit the map draws for it, which "
            "covers the whole territory.")
        cited = [dict(src) for src in unit.get("sources", [])
                 if "population" in str(src.get("field") or "").split("/")]
        if cited:
            country["sources"] = [*country.get("sources", []), *cited]
        done.append(f"{country['id']} {published(unit['population']):,.0f}")
    return done


def note_population_gaps(admin0: list[dict[str, Any]],
                         admin1_by_country: dict[str, list[dict[str, Any]]],
                         admin2_by_country: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Say what a unit's divisions add up to where that is far from its own figure.

    A first-level unit and the second-level divisions drawn inside it, or a
    country and its first level, are two answers to one question, and where
    every division carries a figure the two can be compared. Where they differ
    by more than a sixth (``check_rollups.GAP``) and nothing on the record
    already names the divisions' total or the difference, the parent's note
    says what its divisions add up to, from what and for when, and the reason
    the figures themselves give -- the divisions counted years apart from the
    parent, by no more than growth over those years makes, or two sources'
    figures for one year, no further apart than two accounts of one ground
    (check_rollups.gap_sentence). 254 first-level units outside Asia and 39
    countries disagreed that way with nothing said; scripts/check_rollups.py
    finds any that a later change leaves unsaid.

    Run last of the passes that set a population, so the sentence describes
    the figures the reader is shown. Where a country's first level kept its
    figures over later divisions on purpose (``RESTATE_KEEPS``), the reason it
    did is the reason the two differ, and the sentence ends with it.
    """
    said: list[str] = []
    for iso3, parent, summed, own, level in population_disagreements(
            admin0, admin1_by_country, admin2_by_country):
        if check_rollups.explained(check_rollups.notes_of(parent), own, summed["total"]):
            continue
        pop = parent["population"]
        sentence = check_rollups.gap_sentence(summed, own, vintage(pop), level,
                                              own_source=str(pop.get("source") or ""))
        if level == "divisions" and iso3 in RESTATE_KEEPS:
            sentence = f"{sentence[:-1]}; {RESTATE_KEEPS[iso3]}."
        held = parent.get("population_note") or (pop.get("note") if isinstance(pop, dict)
                                                 else None)
        parent["population_note"] = f"{held} {sentence}" if held else sentence
        said.append(f"{iso3} {parent.get('name')}: {summed['total']:,.0f} against {own:,.0f}")
    return said


def population_disagreements(admin0: list[dict[str, Any]],
                             admin1_by_country: dict[str, list[dict[str, Any]]],
                             admin2_by_country: dict[str, list[dict[str, Any]]]
                             ) -> Iterator[tuple[str, dict[str, Any], dict[str, Any], float, str]]:
    """Each parent whose complete divisions differ from its population by more
    than ``check_rollups.GAP``: (country, parent, the divisions' sum, the
    parent's figure, what its divisions are called).

    A first-level unit against the non-water divisions drawn inside it, outside
    the countries whose second level does not cover their first
    (``PARTIAL_LEVELS``); a country against its first level. A parent with no
    figure, or a division without one, is not compared: a partial sum says
    nothing about the parent. scripts/check_rollups.py asks the same of the
    published files.
    """
    for iso3, parents in sorted(admin1_by_country.items()):
        if (iso3, "admin2") in PARTIAL_LEVELS:
            continue
        kids: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for entity in admin2_by_country.get(iso3, []):
            kids[entity.get("parent")].append(entity)
        for parent in parents:
            if parent.get("water"):
                continue
            own = published(parent.get("population"))
            summed = check_rollups.complete_sum(kids.get(parent["id"], []))
            if own is not None and summed is not None \
                    and check_rollups.disagrees(own, summed["total"]):
                yield iso3, parent, summed, own, "divisions"
    for country in admin0:
        iso3 = country.get("id")
        if iso3 not in admin1_by_country:
            continue
        own = published(country.get("population"))
        summed = check_rollups.complete_sum(admin1_by_country[iso3])
        if own is not None and summed is not None \
                and check_rollups.disagrees(own, summed["total"]):
            yield iso3, country, summed, own, "first-level divisions"


def check_population_gaps_said(admin0: list[dict[str, Any]],
                               admin1_by_country: dict[str, list[dict[str, Any]]],
                               admin2_by_country: dict[str, list[dict[str, Any]]]) -> None:
    """Stop the build if a parent far from its divisions' sum says nothing about it.

    note_population_gaps writes the sentence; this runs on the records as they
    are about to be written, so a pass added after it that moves a population
    or rewrites a note cannot publish a disagreement the reader is not told
    of. It asks what scripts/check_rollups.py asks of site/data, which the
    unit tests run on the published files.
    """
    unsaid = [f"{iso3} {parent.get('name')}: {summed['total']:,.0f} against {own:,.0f}"
              for iso3, parent, summed, own, _ in population_disagreements(
                  admin0, admin1_by_country, admin2_by_country)
              if not check_rollups.explained(check_rollups.notes_of(parent), own,
                                             summed["total"])]
    if unsaid:
        raise SystemExit(f"{len(unsaid)} populations differ from their divisions' sum by "
                         f"more than {check_rollups.GAP:.0%} with nothing said about it: "
                         + "; ".join(unsaid[:10]))


def note_country_not_summed(admin0: list[dict[str, Any]]) -> list[str]:
    """Write a declared refusal to sum a country into the country's own note.

    ``COUNTRY_NOT_SUMMED`` said why only in the build log, so the country kept
    its figure and its note never said why the divisions drawn inside it show
    something else: Suriname's religion, Estonia's three compositions,
    Norway's membership. Run after the curated notes, which would otherwise
    replace it.
    """
    by_id = {c.get("id"): c for c in admin0}
    said: list[str] = []
    for (iso3, field), reason in sorted(COUNTRY_NOT_SUMMED.items()):
        country = by_id.get(iso3)
        if country is None or field not in country:
            continue
        sentence = (f"Its first-level divisions are not added up into this figure: "
                    f"{reason}.")
        value = country.get(field)
        if is_gap(value) and isinstance(value, dict):
            note = value.get("note") or ""
            if sentence not in note:
                country[field] = {**value, "note": f"{note} {sentence}".strip()}
        else:
            note = country.get(f"{field}_note") or ""
            if sentence in note:
                continue
            country[f"{field}_note"] = f"{note} {sentence}".strip()
        said.append(f"{iso3} {field}")
    return said


# Sex ratios reach the build in three units -- males per 100 females (most
# censuses), males per 1,000 females (the Factbook, Eurostat, the US Census
# Bureau, OCHA) and females per 1,000 males (India, Viet Nam, Laos, Bhutan) --
# and a country could show one at its own level, another for its regions and a
# third for their districts: Switzerland's cantons read 1,017 and their
# districts 98.5. Each was right in its own unit, which the panel prints, but a
# reader moving down a level saw the number jump tenfold or turn over. One
# unit for all of them, the United Nations' males per 100 females.
SEX_RATIO_UNIT = "males_per_100_females"
SEX_RATIO_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Canada's census counts gender: "Men+ per 1,000 women+".
    (re.compile(r"\b([Mm]en)\+ per (?:1,000|1000) (women)\+"), r"\1+ per 100 \2+"),
    (re.compile(r"\b([Mm]ales|[Mm]en) per (?:1,000|1000) (females|women)\b"), r"\1 per 100 \2"),
    (re.compile(r"\b([Mm]ales|[Mm]en) per thousand (females|women)\b"), r"\1 per hundred \2"),
    (re.compile(r"\bFemales per (?:1,000|1000) males\b"), "Males per 100 females"),
    (re.compile(r"\bfemales per (?:1,000|1000) males\b"), "males per 100 females"),
)
# A note that prints a ratio in its own unit ("706 females per 1,000 males
# against 943 for India") keeps it: it says which unit it means.
PRINTED_RATIO = re.compile(r"(?i)\d[\d,.]*\s+(?:males|men|females|women)\s+per\s")


def one_sex_ratio_unit(*tables: Any) -> int:
    """Put every sex ratio in males per 100 females, and its note's unit with it.

    A note beside a gap names its unit too: Saint Lucia's settlements with no
    ratio read "Men per thousand women among the 1 people the 2010 base holds"
    where every published ratio of theirs is per hundred. It is put in the
    same unit; a note that prints a ratio in its own unit keeps it.
    """
    done = 0
    for table in tables:
        rows = (table if isinstance(table, list)
                else [e for rows in table.values() for e in rows])
        for entity in rows:
            value = entity.get("sex_ratio")
            ratio = published(value)
            if ratio is None:
                note = entity.get("sex_ratio_note")
                if is_gap(value) and isinstance(note, str) and note \
                        and not PRINTED_RATIO.search(note):
                    for pattern, said in SEX_RATIO_PHRASES:
                        note = pattern.sub(said, note)
                    entity["sex_ratio_note"] = note
                continue
            if value.get("unit") == SEX_RATIO_UNIT:
                continue
            unit = value.get("unit")
            if unit == "males_per_1000_females":
                converted = round(ratio / 10, 1)
            elif unit == "females_per_1000_males" and ratio > 0:
                converted = round(100_000 / ratio, 1)
            else:
                raise SystemExit(f"sex ratio of {entity.get('id')} ({entity.get('name')}) "
                                 f"is in {unit!r}, which this build cannot convert")
            entity["sex_ratio"] = {**value, "value": converted, "unit": SEX_RATIO_UNIT}
            note = entity.get("sex_ratio_note")
            if isinstance(note, str) and note and not PRINTED_RATIO.search(note):
                for pattern, said in SEX_RATIO_PHRASES:
                    note = pattern.sub(said, note)
                entity["sex_ratio_note"] = note
            done += 1
    return done


def fill_remainders(admin1_by_country: dict[str, list[dict[str, Any]]],
                    admin2_by_country: dict[str, list[dict[str, Any]]]) -> list[str]:
    """The ground outside every second-order unit: its parent's count less theirs.

    Only where the arithmetic says something true. The parent's figure and
    every one of its divisions' must be published and of one year -- a count
    less a count -- and what is left must be more than nothing. Otherwise the
    unit keeps a gap that says which of those failed: a difference taken
    against a missing division would give the remainder that division's people.
    """
    done: list[str] = []
    for iso3, rows in admin2_by_country.items():
        parents = {e["id"]: e for e in admin1_by_country.get(iso3, [])}
        kids: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for entity in rows:
            if not entity.get("water"):
                kids[entity.get("parent")].append(entity)
        for rest in (e for e in rows if e.get("remainder")):
            # A remainder a source counts directly keeps that count: Uruguay's
            # census files its people under "Sin Municipio" by department, and
            # the difference would also take in the people INE records with no
            # municipio at all, and a municipio's strip across a department line.
            if published(rest.get("population")) is not None:
                continue
            parent = parents.get(rest.get("parent"))
            if parent is None:
                continue
            siblings = [k for k in kids[rest.get("parent")] if k is not rest]
            whole_pop = parent.get("population")
            total = published(whole_pop)
            values = [published(k.get("population")) for k in siblings]
            missing = [k["name"] for k, v in zip(siblings, values) if v is None]
            years = {vintage(whole_pop), *(vintage(k.get("population")) for k in siblings)}
            why = None
            if total is None:
                why = f"{parent['name']} has no published population to take its divisions from."
            elif missing:
                why = (f"{len(missing)} of the {len(siblings)} divisions of "
                       f"{parent['name']} have no count ({', '.join(missing[:6])}"
                       + (" and others" if len(missing) > 6 else "")
                       + "), so what is left of it cannot be worked out.")
            elif len(years) != 1 or None in years:
                why = (f"{parent['name']}'s count and its divisions' are not all of "
                       f"one year, so one cannot be taken from the other.")
            elif total - sum(values) <= 0:
                why = (f"{parent['name']}'s divisions add up to its own count or more, "
                       f"so no figure is left for the ground outside them.")
            if why:
                rest["population"] = gap(NOT_AVAILABLE, why)
                continue
            year = years.pop()
            rest["population"] = {
                "value": int(round(total - sum(values))), "year": year,
                "source": (f"{parent['name']}'s {year} count less its "
                           f"{len(siblings)} divisions' {year} counts"),
                "note": (f"{parent['name']} counted {total:,.0f} people in {year} and "
                         f"its {len(siblings)} divisions {sum(values):,.0f}; this is "
                         f"the difference, the people living outside all of them. "
                         f"Figures from {whole_pop.get('source')}.")}
            done.append(f"{iso3} {rest['name']}")
    return done


def fill_same_polygons(admin1_by_country: dict[str, list[dict[str, Any]]],
                       admin2_by_country: dict[str, list[dict[str, Any]]]) -> int:
    """A polygon drawn at both levels shows one unit's figures at both.

    The boundary file draws some units at both levels under one id (see
    bound()), and a source is joined to whichever copy it names. Montenegro's
    municipalities carried their census counts on the first-level copy and,
    on the second, a town's figure the settlement check had rightly refused;
    Moldova's 37 districts, the Marshall Islands' atolls and Trinidad's
    corporations were blank a level down while filled a level up. It is the
    same polygon and the same unit, so the second-level copy takes what the
    first holds wherever it holds nothing itself. Run after the sums, so what
    is copied is what the first level finally shows.
    """
    filled = 0
    for iso3, rows in admin2_by_country.items():
        twins = {e["id"]: e for e in admin1_by_country.get(iso3, []) if e.get("id")}
        for entity in rows:
            twin = twins.get(entity.get("id"))
            if twin is None or entity.get("water"):
                continue
            # One polygon, two populations: show one. The second copy's
            # figure was joined by name, often to the town the unit is named
            # for -- Libya's Az Zawiyah read the city's 198,567 under the
            # district's 290,993, Mauritius's Port Louis the city item's
            # 149,194 under the district's 118,123.
            chosen = twin_population(twin, entity)
            if chosen is not None:
                source, target = chosen
                if target is twin or put_in_front_of(source.get("population"),
                                                     target.get("population")):
                    # The first level's own figure gives way, or a count a
                    # newer figure stands in front of on the other copy:
                    # flagged, so the gates still weigh the count
                    # (restate_population).
                    restate_population(source, target)
                else:
                    copy_field(source, target, "population")
                filled += 1
            for field in sorted(VALUE_FIELDS):
                mine, theirs = entity.get(field), twin.get(field)
                if (is_gap(mine) and is_gap(theirs) and isinstance(theirs, dict)
                        and theirs.get("note")
                        and not (isinstance(mine, dict) and mine.get("note"))):
                    # The same polygon's reason for the gap, where the first
                    # level has one and this level none: Saint Kitts' parishes
                    # say why no median age is published below the country,
                    # and the same parishes drawn again said nothing.
                    entity[field] = copy.deepcopy(theirs)
                    continue
                if not is_gap(mine) or is_gap(theirs) or field not in twin:
                    continue
                entity[field] = copy.deepcopy(twin[field])
                for suffix in SATELLITES:
                    if f"{field}{suffix}" in twin:
                        entity[f"{field}{suffix}"] = copy.deepcopy(twin[f"{field}{suffix}"])
                    else:
                        entity.pop(f"{field}{suffix}", None)
                sources = entity.setdefault("sources", [])
                sources[:] = [src for src in sources
                              if not set(str(src.get("field") or "").split("/")) <= {field}]
                sources.extend(src for src in twin.get("sources") or []
                               if field in str(src.get("field") or "").split("/")
                               and src not in sources)
                filled += 1
    return filled


def put_in_front_of(value: Any, count: Any) -> bool:
    """Whether ``value`` is a figure put in front of ``count`` in this build:
    it carries that count, value and year, as the figure it replaced."""
    was = value.get(RESTATED_FROM) if isinstance(value, dict) else None
    return (isinstance(was, dict) and published(was) is not None
            and published(was) == published(count) and vintage(was) == vintage(count))


def twin_population(first: dict[str, Any], second: dict[str, Any]
                    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(the copy whose population both should show, the other), or None.

    A statistics office's figure stands over an encyclopaedia's, as FILL_ONLY
    has it -- on the first level's side only where it is at least as new,
    since the second level was filled by other passes and an older count
    should not take a newer figure off the unit's first copy. Two
    encyclopaedia figures: the first level's, which was joined to the unit
    at its own level. Two offices' figures, or a projection beside either,
    stand where they are.
    """
    a, b = first.get("population"), second.get("population")
    va, vb = published(a), published(b)
    if va is None or vb is None or va == vb:
        return None
    # A newer figure prefer_newer_figures put in front of the count the other
    # copy shows is that count's successor on both: Malta's Birkirkara read
    # Wikipedia's 30,166 for 2026 a level up and the 2021 census's 25,807 a
    # level down, on one polygon.
    if put_in_front_of(a, b):
        return first, second
    if put_in_front_of(b, a):
        return second, first
    ya, yb = vintage(a), vintage(b)
    if encyclopaedic(a) and encyclopaedic(b):
        # One item at both levels is one figure's history: the newer.
        if first.get("wikidata") and first.get("wikidata") == second.get("wikidata") \
                and ya is not None and yb is not None and ya != yb:
            return (first, second) if ya > yb else (second, first)
        return first, second
    if projection(a) or projection(b):
        # A projection beside an encyclopaedia's figure, which may be a
        # census's at one remove: neither is put over the other.
        return None
    if encyclopaedic(b):
        return first, second
    if encyclopaedic(a):
        if yb is not None and (ya is None or yb >= ya):
            return second, first
        return None
    # Two offices' figures stand where they are.
    return None


# Country fields whose first-level divisions carry figures a sum cannot be
# taken across, declared with the reason; the country keeps its own figure.
COUNTRY_NOT_SUMMED: dict[tuple[str, str], str] = {
    # suriname_census gives seven districts the 2004 census's religion and the
    # three interior districts the 2012 census's denominations (the ABS's
    # District Results Volume III), each the newest their district has. Summed,
    # they are a figure of neither year, listing Christianity beside its own
    # churches. The country keeps the 2012 census's national table as the
    # Factbook prints it (Protestant 23.6%, Hindu 22.3%, Roman Catholic 21.6%).
    ("SUR", "religion"): "its districts' religion comes from two censuses, 2004 "
                         "and 2012, and no sum across them is either",
    # paraguay_census gives the 18 departments the 2002 census's religion
    # (INE's REDATAM base CPV2002), the latest it publishes by department;
    # the country carries the Factbook's line of 2023. The 2022 census's
    # department populations brought the sum within the population gate,
    # which is why this has to be said rather than left to the gate: a sum
    # would put Catholics at 90.5% of 2002 over the 80.4% of 2023.
    ("PRY", "religion"): "its departments' religion is the 2002 census's, and the "
                         "country's figure is of 2023",
    # malta_census gives each locality the main language of its Maltese
    # citizens (Volume 3, Table 3.6) as shares of all its residents aged 5 and
    # over; the NSO tabulates the other fifth of residents by district only.
    # Summed, the localities would describe Malta's citizens as if they were
    # its population.
    ("MLT", "language"): "its localities' language counts Maltese citizens only; "
                         "the other residents are tabulated by district, not by locality",
    # lithuania_municipality gives the ten counties the 2011 census's religion
    # (the 2021 census published religion for the country only), and nine of
    # them the 2011 census's ethnicity beside Vilnius county's 2021 figure. The
    # country carries the 2021 census; a sum would put 2011 over it.
    ("LTU", "religion"): "its counties' religion is the 2011 census's, and the "
                         "country's is the 2021 census's",
    ("LTU", "ethnicity"): "its counties' ethnicity is the 2011 census's for nine of "
                          "them and the 2021 census's for Vilnius county",
    # estonia_municipality draws the fifteen counties of before the 2017
    # reform: eleven carry the 2011 census's language and religion and the
    # register's ethnicity of 2017, and the four the reform left alone the
    # 2021 census and the register of 2026 (estonia_county). A sum is of no
    # one year, and older than the country's own 2021 figures.
    ("EST", "religion"): "its pre-2017 counties mix the 2011 and 2021 censuses",
    ("EST", "language"): "its pre-2017 counties mix the 2011 and 2021 censuses",
    ("EST", "ethnicity"): "its pre-2017 counties mix the register of 2017 and of 2026",
    # norway_kommune's fylker carry registered membership for 2020, the last
    # year SSB counts the communities outside the Church by fylke (08531 is a
    # closed series); the country's figure is 2021's.
    ("NOR", "religion"): "its fylker's membership is 2020's, older than the country's "
                         "2021 figure",
    # armenia_2011 gives the marzes the 2011 census's nationality and religion,
    # the latest Armstat has published below the republic; the country keeps
    # the 2022 census's national shares (the Factbook's, 2022). A sum would put
    # 2011 over 2022.
    ("ARM", "ethnicity"): "its marzes' nationality is the 2011 census's, and the "
                          "country's is the 2022 census's",
    ("ARM", "religion"): "its marzes' religion is the 2011 census's, and the "
                         "country's is the 2022 census's",
    # fiji_census gives the four divisions Table P01-3's 2007 religion and
    # ethnicity, but the polygon the boundary file labels Eastern is Kadavu
    # alone and carries Kadavu's: Lau, Lomaiviti and Rotuma (26,779 people in
    # 2017) are drawn only at the second level. A sum would leave them out and
    # look whole. The country keeps the 2007 census's national table, the
    # same census, as the Factbook prints it.
    ("FJI", "religion"): "its Eastern polygon is Kadavu alone; Lau, Lomaiviti and "
                         "Rotuma are drawn only at the second level",
    ("FJI", "ethnicity"): "its Eastern polygon is Kadavu alone; Lau, Lomaiviti and "
                          "Rotuma are drawn only at the second level",
    # kiribati_census gives the three island groups the 2015 census's religion
    # (Volume 1, Table 6), the latest by island: the 2020 census published
    # religion for the country only (General Report, Table G-3), and the
    # country carries that.
    ("KIR", "religion"): "its island groups' religion is the 2015 census's, and the "
                         "country's is the 2020 census's",
    # vietnam_religion gives the 63 provinces the 2009 census's Table 7, the
    # newest religion by province: the 2019 census published religion for the
    # country only (Completed Results, Table 3), and the country carries that
    # table (data/curated/admin0_detail.json).
    ("VNM", "religion"): "its provinces' religion is the 2009 census's, and the "
                         "country's is the 2019 census's",
    # timor gives the 13 municipalities the 2015 census's priority table 11,
    # the newest religion by municipality: the 2022 census published religion
    # for the country only (Main Report basic table 4.07), and the country
    # carries that table (data/curated/admin0_detail.json).
    ("TLS", "religion"): "its municipalities' religion is the 2015 census's, and the "
                         "country's is the 2022 census's",
    # thailand_nationality and thailand give the 76 provinces the 2000
    # census's provincial reports, the last to print nationality and religion
    # by province. The country's figures are later: the Factbook's 2015
    # nationality line (Thai 97.5%, Burmese 1.3%) and its 2021 religion line.
    # A sum would put a count from 2000 over both.
    ("THA", "ethnicity"): "its provinces' nationality is the 2000 census's, and the "
                          "country's figure is of 2015",
    ("THA", "religion"): "its provinces' religion is the 2000 census's, and the "
                         "country's figure is of 2021",
    # vanuatu_census gives each province Table 6.16 of the 2020 census, first
    # language learned, which the census asked only of the people who speak
    # one of the islands' own languages: 84-97% of each province, every share
    # taken of everyone. A sum would leave out the rest and look whole. The
    # country keeps the Analytical Report's four-way split of everyone
    # (indigenous languages, Bislama, English, French), which its note
    # describes.
    ("VUT", "language"): "its provinces' first language was asked only of the people "
                         "who speak one of the islands' own languages, 84-97% of each "
                         "province",
    # clear_global_language gives the 25 provinces CLEAR Global's tabulation of the
    # 2019 census's IPUMS sample: the main language spoken in each household.
    # Summed they come to Khmer 96.3% and Chinese 0.1%; the census's own count
    # by mother tongue, which the Factbook prints and the country's ethnicity
    # note describes, is Khmer 95.8% and Chinese 0.6%.
    ("KHM", "language"): "its provinces carry the main language spoken in each "
                         "household, tabulated from a sample of the 2019 census, and "
                         "the country's figure is the census's own count by mother "
                         "tongue",
    # lebanon_survey gives the governorates the LFHLCS 2018-19's residents by
    # nationality, a survey of residential dwellings: the refugee camps and
    # their gatherings, informal settlements, barracks and work sites are
    # outside it, which is where many of the country's foreign nationals live.
    # Each governorate's own record says so; a country total would read as
    # Lebanon's share of foreign nationals and understate it.
    ("LBN", "ethnicity"): "its governorates' nationality is a survey of residential "
                          "dwellings, which leaves out the refugee camps and informal "
                          "settlements",
    # Myanmar's 14 drawn states and regions carry the Department of
    # Population's 2018 Township Profiles, Table 14 (reference date 1 April
    # 2017), for ethnicity (uscb): 40 of the 135 national races, counting
    # 47.8 million of the states' 56.2 million people. The Rohingya are not in
    # it (Rakhine's rows total 2,086,677 of 3,397,770 people), and Chinese and
    # Indian people hardly are (5,638 and 1,921 in all), so a sum reads Chinese
    # 0.0% and looks whole. Their religion is the 2014 census's township
    # columns, 49.0 million people; the census's own Union table, which the
    # country carries (Buddhist 87.9%, Christian 6.2%, Muslim 4.3%), counts
    # 51,486,253, with the 1.2 million it did not enumerate, most of them in
    # Rakhine and counted as Muslim. A sum gives Muslim 3.0%, matching neither
    # that table nor the enumerated people's 2.3%. The country keeps the
    # Factbook's ethnicity line and the census's national religion; the
    # states keep their own figures and caveats. COD-PS 2023 populations
    # brought the states within the population gate (2.9% under, against 5%),
    # which is why this has to be said rather than left to the gate.
    ("MMR", "ethnicity"): "its states' ethnicity is the 2018 Township Profiles' table of "
                          "40 national races, counting 47.8 million of their 56.2 million "
                          "people; the Rohingya are not in it and Chinese and Indian "
                          "people hardly are",
    ("MMR", "religion"): "its states' religion counts 49.0 million people; the census's "
                         "national table, which the country carries, counts 51.5 million, "
                         "with the 1.2 million it did not enumerate",
}


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

    The population itself is never summed over: every country shows the
    Factbook's estimate, one moment for every country, and its first level's
    total fills it only where it has none. Where the Factbook's estimate cannot
    be the people the first level counts, a census count curated beside it is
    what the sums are checked against (CHECKED_AGAINST): the Marshall Islands'
    drawn atolls add up to 42,262, Lib's 156 people having no polygon, against
    the census's 42,418 for the same day, and the Factbook's 82,011 is shown.
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
            if (iso3, field) in COUNTRY_NOT_SUMMED:
                refused.append(f"{iso3}: {field}: {COUNTRY_NOT_SUMMED[(iso3, field)]}")
                continue
            before = country.get(field)
            # Every first-level division of the country is in `children`, and
            # the check above has already refused the field unless all of them
            # carry it, so these are certainly all of them. That is enough to
            # sum without child populations; it is not enough to overrule the
            # country's own published population, which stays gated at 2%.
            why = roll_up_field(country, children, field,
                                level="first-level", over_published=True,
                                complete=True,
                                min_coverage=COUNTRY_MIN_COVERAGE,
                                fill_population_only=True)
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
        # A name borrowed is not a claim. Wikidata's local-language labels gave
        # the town of Perito Moreno the alias "Lago Buenos Aires" and Villa de
        # Pomán the alias "Pomán" -- the names of the departments they lie in
        # -- and each tied with its department for the department's shape, so
        # neither was kept and three Argentine departments went blank. Where
        # one rival reached the shape only through an alias and another
        # carries the shape's name as its own, the alias yields. Two rivals
        # both named like the shape (the town of Andalgalá and Andalgalá
        # Department) are untouched: that is the tie the ranking below exists
        # for.
        shape_name = str(matched[idxs[0]][1].get("name") or "")
        # Own means the shape's whole name, at the start of the row's:
        # "Pomán Department" is Pomán's, and "Maneh County" -- one of the two
        # counties Maneh and Samalqan was split into -- is not the undivided
        # county's, which the row whose alias is "Maneh and Samalqan County"
        # describes.
        own = [i for i in idxs if norm(matched[i][0].get("name")) == norm(shape_name)
               or any(run_of(whole, theirs, at_start=True)
                      for whole in name_forms(shape_name)
                      for theirs in name_forms(matched[i][0].get("name")))]
        borrowed = [i for i in idxs if i not in own and any(
            norm(a) == norm(shape_name)
            or related(name_forms(a), name_forms(shape_name))
            for a in matched[i][0].get("aliases") or [])]
        if own and borrowed:
            dropped.update(borrowed)
            notes.append(f"{shape_name!r}: refused "
                         + ", ".join(str(matched[i][0].get("name"))[:24] for i in borrowed[:4])
                         + " (reached it only by a name another row carries)")
            idxs = [i for i in idxs if i not in borrowed]
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
                 "completeness; no sovereignty claim is implied.")
# The same, for a figure the territory has none of. It said "no demographic
# source is joined to it", which spoke of the map's making, and was false
# beside the Gaza Strip's, the West Bank's and the Falklands' populations.
DISPUTED_GAP = DISPUTED_NOTE + " No source used here gives this figure for it."

# Disputed outlines the Factbook profiles as a territory of its own, under no
# country's code: the outline is the profile's ground, so it shows the
# profile's population. The boundary file's name -> the profile's record in
# admin0.json, and what the figure's note says.
DISPUTED_PROFILES: dict[str, tuple[str, str]] = {
    "Paracel Is": ("GEC-PF", "The Factbook's estimate for the Paracel Islands, which it "
                             "profiles apart from the states that claim them; it puts over "
                             "1,000 Chinese on Woody Island, the largest of them, and "
                             "scattered Chinese garrisons on some of the others."),
}


def disputed_record(entity: dict[str, Any], profiles: dict[str, dict[str, Any]]) -> None:
    """A disputed outline's record: the Factbook's own figure for it where it
    profiles the territory (DISPUTED_PROFILES), and the reason on every field
    that has none -- Abyei's six fields were bare beside the outline's note."""
    entity["disputed"] = True
    entity["note"] = DISPUTED_NOTE
    declared = DISPUTED_PROFILES.get(entity.get("name"))
    profile = profiles.get(declared[0]) if declared else None
    if declared and profile is None:
        raise SystemExit(f"build_entities: {entity.get('name')!r} is declared the "
                         f"Factbook's {declared[0]}, which admin0.json no longer has")
    if profile and published(profile.get("population")) is not None:
        entity["population"] = {k: v for k, v in profile["population"].items()
                                if k in ("value", "year", "source")}
        entity["population_note"] = declared[1]
        entity["sources"] = [*entity.get("sources", []),
                             *(dict(src, field="population")
                               for src in profile.get("sources") or []
                               if "*" in cited_fields(src)
                               or "population" in cited_fields(src))]
    for field in (*FIGURE_FIELDS, *COMPOSITION_FIELDS):
        value = entity.get(field)
        if isinstance(value, dict) and value.get("status") and not value.get("note"):
            entity[field] = gap(value["status"], DISPUTED_GAP)


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


def mark_water(entity: dict[str, Any], group: str) -> None:
    """Make a declared lake water: every field not applicable, and why.

    Instead of an adapter hint, which would send a reader to fetch figures
    for a lake. Each field carries the reason as its note, so the passes that
    explain bare fields find nothing to explain, and the collection policy,
    which only ever replaces "not available", leaves it alone.
    """
    note = WATER_SHAPES.get(group, {}).get(entity.get("name"))
    if note is None:
        return
    entity["water"] = True
    entity["note"] = note
    entity.pop("adapter_hint", None)
    entity.pop("gap_reason", None)
    for field in UNIT_FIELDS:
        entity[field] = gap(NOT_APPLICABLE, note)


COMPOSITION_FIELDS = ("religion", "language", "ethnicity")

# The ways a composition field can still be bare at the end of the pipeline,
# in the words the panel prints. Each says what is true and stops there: none
# of them claims the census does not ask, because none of them knows. They say
# what the sources give, not how the map was put together: the first wording
# told the visitor what had been "read", "fetched" and "joined", and which
# unit "matched no row" -- on Libya's districts, whose populations the same
# sources give.
NO_SOURCE_READ = (
    "No {field} figure is shown: none of the sources used here gives figures "
    "for the units of {country} at this level.")
SOURCE_LACKS_FIELD = (
    "The sources used for this unit ({sources}) give its {present} but not its "
    "{field}, and no {field} figure has been found for it. That says nothing "
    "about whether the census asks.")
SOURCE_LACKS_ALL = (
    "None of the sources used for this unit ({sources}) gives its religion, "
    "language or ethnicity, and no figure has been found for it. That says "
    "nothing about whether the census asks.")
# A unit beside others at its level that carry the field, and one beside none.
FIELD_ELSEWHERE = (
    "No {field} figure has been found for this unit. {carriers} {give} it for "
    "{n} of the {units} units of {country} at this level, not for this one.")
FIELD_NOWHERE = (
    "None of the sources used for the units of {country} at this level "
    "({sources}) gives {field}, and no figure has been found for this unit. "
    "That says nothing about whether the census asks.")


def cited_names(sources: Sequence[dict[str, Any]]) -> list[str]:
    """The sources cited, as a sentence names them, once each."""
    return sorted({check_rollups.short_source(str(s.get("name")))
                   for s in sources if s.get("name")}) or ["an unnamed source"]


def joined_here(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """What the sources give at this level, for the units they give nothing.

    A bare unit beside units that carry the field and one beside none need
    different sentences. Counted once per country and level, and the counts go
    into the note, so a reader can see how far the sources reach rather than
    take the word "gap" on trust.
    """
    live = [r for r in rows if not r.get("disputed")]
    matched = [r for r in live if r.get("match")]
    fields = {}
    for field in COMPOSITION_FIELDS:
        carrying = [r for r in live if isinstance(r.get(field), list) and r[field]]
        fields[field] = {"n": len(carrying), "sources": cited_names(
            [src for r in carrying for src in r.get("sources", [])
             if field in cited_fields(src)])}
    return {"sources": listed(cited_names([src for r in matched
                                           for src in r.get("sources", [])])),
            "matched": len(matched), "units": len(live), "fields": fields}


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
    # "The Gambia" and "The Bahamas" mid-sentence, and "the" before a name
    # that takes one: "the units of the DRC", "of the United States".
    country = re.sub(r"^The ", "the ", country)
    if re.search(r"^(?:United |Central African |Federated |Holy See\b|Isle of )"
                 r"|^(?:Comoros|DRC|Maldives|Netherlands|Philippines)$|\bIslands(?: \(|$)",
                 country):
        country = f"the {country}"
    for field in COMPOSITION_FIELDS:
        value = entity.get(field)
        if not (isinstance(value, dict) and value.get("status")
                and not value.get("note")):
            continue
        reach = ((joined or {}).get("fields") or {}).get(field) or {"n": 0, "sources": []}
        if entity.get("disputed"):
            note, case = DISPUTED_GAP, "disputed"
        elif field_gap(entity.get("country"), field, entity.get("level")):
            note = field_gap(entity.get("country"), field, entity.get("level"))
            case = "country publishes nothing"
        elif entity.get("gap_reason"):
            # The country-level fact already on the record: what the country
            # publishes. True of the field, so it is the field's reason too.
            note, case = entity["gap_reason"], "country publishes nothing"
        elif joined and reach["n"]:
            # Other units at this level carry the field and this one does
            # not: 27 of Bulgaria's 28 oblasts carry Wikidata and Sofia does
            # not, because "Sofia Oblast" could reach neither "Sofia" nor
            # "Sofia City" without reaching both. Saying no source gives the
            # field there is false, and false in the direction that hides the
            # miss.
            carriers = reach["sources"]
            # Named as a sentence names them, at its start: "The U.S. Census
            # Bureau gives it", "The European Social Survey gives it".
            named = [named_source(name) for name in carriers]
            named[0] = named[0][:1].upper() + named[0][1:]
            note = FIELD_ELSEWHERE.format(
                field=field, carriers=listed(named),
                give="give" if len(carriers) > 1 else "gives",
                n=f"{reach['n']:,}", country=country, units=f"{joined['units']:,}")
            case = "others at this level carry it"
        elif entity.get("match"):
            sources = listed(cited_names(entity.get("sources", [])))
            present = [f for f in COMPOSITION_FIELDS
                       if isinstance(entity.get(f), list)]
            if present:
                note = SOURCE_LACKS_FIELD.format(
                    sources=sources, field=field, present=" and ".join(present))
                case = "source lacks the field"
            else:
                note = SOURCE_LACKS_ALL.format(sources=sources)
                case = "source carries no composition"
        elif joined and joined["matched"]:
            note = FIELD_NOWHERE.format(country=country, sources=joined["sources"],
                                        field=field)
            case = "no unit at this level carries it"
        else:
            note = NO_SOURCE_READ.format(country=country, field=field)
            case = "no source read"
        entity[field] = gap(value["status"], note)
    return case


# The fields the panel reads to decide that a unit is empty, in its order
# (hintPanel in site/js/dashboard.js).
PANEL_FIELDS = ("population", "religion", "language", "ethnicity", "median_age")


def drop_answered_hint(entity: dict[str, Any]) -> bool:
    """Take the adapter hint off a unit whose every empty field says why.

    A hint is printed on a unit with nothing in it, as "this build has not
    fetched demographics for this unit" and a command to fetch them. That is
    true of a unit nobody has read. It is false of one an adapter read and
    left empty on purpose, field by field, with the reason on each: Jerusalem
    District's figures count East Jerusalem, which the map draws in the West
    Bank, and its panel went on to recommend the Wikidata fetch whose count
    had just been refused for exactly that; Turkmenistan's etraps are divided
    differently by the census and the boundary file, and the panel offered to
    run the census adapter that said so. Each card already gives its own
    reason, so the hint is taken off rather than turned into one more.

    A unit with any field that is a gap with no reason keeps its hint: there
    something really has not been fetched. Runs after say_why_empty, which is
    what gives the bare compositions their reasons.
    """
    if "adapter_hint" not in entity:
        return False
    for field in PANEL_FIELDS:
        value = entity.get(field)
        if not (isinstance(value, dict) and is_gap(value) and value.get("note")):
            return False
    entity.pop("adapter_hint")
    return True


# Instructions an adapter gives the build on a field's value, read while the
# rows are merged and summed, and nothing a reader of the map is told:
# ``displaces_before`` and ``displaces_undated`` (see merge_adapter) and
# ``no_child_sum`` (see fill_parent_populations); and two the build leaves for
# itself, ``restated_from`` (RESTATED_FROM, see control_population) and
# ``checked_against`` (CHECKED_AGAINST, see gate_population).
BUILD_FLAGS = ("displaces_before", "displaces_undated", "no_child_sum", "not_this_ground",
               "restated_from", "refused_value", "checked_against")


def drop_build_flags(entity: dict[str, Any]) -> int:
    """Take the build's own flags off a record's values before it is written.

    Afghanistan's seven provinces drawn across the census's lines went out
    with ``"no_child_sum": true`` on their population, and 430 stated gaps
    with the year before which they displace an encyclopaedia's figure:
    instructions to the build, written into the published files beside the
    figures. Returns how many were taken.
    """
    taken = 0
    for value in entity.values():
        if isinstance(value, dict):
            for flag in BUILD_FLAGS:
                if value.pop(flag, None) is not None:
                    taken += 1
    return taken


# A reason written in a source's own vocabulary, said in plain words. The
# Wikidata sweep marks a unit whose item has no population statement with the
# property's number (scripts/fetch_wikidata.py), and 982 population tiles read
# "No P1082 statement on Wikidata (asked by id)."
PLAIN_NOTES = {
    "No P1082 statement on Wikidata.": "Wikidata gives no population for this unit.",
    "No P1082 statement on Wikidata (asked by id).":
        "Wikidata gives no population for this unit.",
}


def plain_notes(entity: dict[str, Any]) -> int:
    """Say a source's coded reasons in plain words; returns how many."""
    said = 0
    for value in entity.values():
        if isinstance(value, dict) and value.get("note") in PLAIN_NOTES:
            value["note"] = PLAIN_NOTES[value["note"]]
            said += 1
    return said


# Pipeline wording in the visitor's text, said as what is or is not published.
# Adapters wrote these into notes, licences and reasons: the server's answer
# to this project's reader ("BPS answers automated requests with HTTP 403"),
# the CKAN registry's own fields beside a licence's name ("license_id='cc-by',
# isopen=True"), a publisher's coded grade ("representivity very_high"), how a
# row was joined to its polygon, and a file of this repository. Each is put
# in plain words, or dropped where the sentence says nothing else.
PLAIN_PHRASES: tuple[tuple[str, str], ...] = (
    ("BPS answers automated requests with HTTP 403 on every bps.go.id host",
     "BPS's own websites could not be read"),
    ("Statistics Indonesia (BPS) answers this project's reader HTTP 403 on every "
     "bps.go.id host", "Statistics Indonesia's (BPS's) own websites could not be read"),
    ("and the government's open-data portal and the National Statistical Office's "
     "census hosts answer HTTP 403 or 418 to automated requests",
     "and the government's open-data portal and the National Statistical Office's "
     "census websites could not be read"),
    ("and the National Statistical Office's hosts and the government's open-data "
     "portal answer HTTP 418 or 403 to automated requests",
     "and the National Statistical Office's and the government's open-data "
     "websites could not be read"),
    ("the National Statistical Office's later census hosts refuse automated requests",
     "the National Statistical Office's later census tables could not be read from "
     "its websites"),
    ("The National Statistical Office's later census hosts refuse automated requests",
     "The National Statistical Office's later census tables could not be read from "
     "its websites"),
    (" (docs/SOURCES.md, \"Indonesia: what BPS's refusal left reachable\", lists the "
     "110 portals tried)", " (110 portals were tried)"),
    ("Bound to this boundary shape by the shape's own id rather than by its name. ", ""),
    (" Bound to this boundary shape by the shape's own id rather than by its name.", ""),
    (" (prod.redatam.org/binkna/RpWebEngine.exe/Portal answers 404)", ""),
)
PLAIN_PATTERNS: tuple[tuple[re.Pattern[str], Any], ...] = (
    (re.compile(r" -- license_id='[^']*', isopen=(?:True|False)"), ""),
    (re.compile(r" \(HTTP \d{3}\)"), ""),
    (re.compile(r"\brepresentivity (very_high|high|moderate|low|very_low)\b"),
     lambda m: f"representativeness rated {m.group(1).replace('_', ' ')}"),
    # "Not written:" opens an adapter's reason for a figure it left out, and
    # says how the map was made rather than what is or is not published. What
    # follows it is the reason itself, which stands as the sentence: Slovenia's
    # "SiStat blanks 68 of the municipality's 332 people ...".
    (re.compile(r"\bNot written: (\w)"), lambda m: m.group(1).upper()),
    # "The boundary file" names the file the map is drawn from, in some 10,800
    # notes from many adapters; what the visitor looks at is the map. "Its
    # districts as drawn add up to 2,853,295 ...: the boundary file draws
    # Parasi as one district with Nawalpur" reads "the map draws".
    (re.compile(r"\b([Tt])he boundary file('s)?\b"),
     lambda m: f"{m.group(1)}he map{m.group(2) or ''}"),
    # A quotation of the Factbook that had to be cut ends at its last whole
    # item (see whole_items), as fetch_factbook now cuts one.
    (re.compile(r'(?<=which reads: ")([^"]*?)\.\.\.(?=")'),
     lambda m: whole_items(m.group(1))),
    # Round 7's review: notes that said how the map was put together --
    # what was read, fetched, joined or bound, a file's name, a database's words --
    # said as what is or is not published, and sentences a rewrite left
    # broken. Each changes only the texts it names (tested on every note).
    # binding-fetch: KWT binding wording: '(N% of these, more than the 10% a binding allows)' in population/sex_ratio/ethnicity .note
    (re.compile(r"more than the (\d+%) a binding allows\)"), r"more than the \1 a polygon's count may leave out)"),
    # binding-fetch: LCA binding wording and REDATAM base name: 'The 2010 census's REDATAM base (PHC2010C) holds no settlement of this name in the district, or holds it tw
    (re.compile(r"The 2010 census's REDATAM base \(PHC2010C\) holds no settlement of this name in the district, or holds it twice, so nothing is bound to this outline\."), r"The 2010 census lists no settlement of this name in this district, or lists two, so no census figure is shown for this outline."),
    # binding-fetch: KAZ Zhualy (9891525B50399930684689): 'No unit the Bureau publishes is this polygon, so nothing is bound to it.'
    (re.compile(r"(No unit the Bureau publishes is this polygon), so nothing is bound to it\."), r"\1, so no figure is shown for it."),
    # binding-fetch: CYP Kyrenia (96831152B33829437974548): 'its quarters are bound to 31 of this district's 46 community polygons'
    (re.compile(r"\bits quarters are bound to (\d+ of this district's)\b"), r"its quarters' counts are put on \1"),
    # binding-fetch: PHL NCR districts language_note (4): '; it is bound to the polygon by that code.'
    (re.compile(r"(, which is its PSGC code); it is bound to the polygon by that code\."), r"\1."),
    # binding-fetch: SAU fetch-failure wording: 'No table ... could be read: the census portal (portal.saudicensus.sa) could not be reached, ... drawn by script, ... did n
    (re.compile(r"\b([Nn]o table of (?:it|the 2022 census) by (?:governorate|region)) could be read(?:: the census portal \(portal\.saudicensus\.sa\) could not be reached, GASTAT's census page on stats\.gov\.sa \(statistics\?index=119025\) links no table file, its content being drawn by script, the Saudi open-data portal \(open\.data\.gov\.sa\) did not answer, and|;)(?= OCHA's| the governorates)"), r"\1 has been obtained;"),
    # binding-fetch: ISR language notes (21): '...could not be read (their content is drawn by script, and the Internet Archive's index of the 2008 census site did not ans
    (re.compile(r"; and the CBS's census and social-survey pages could not be read \(their content is drawn by script, and the Internet Archive's index of the 2008 census site did not answer\)\."), r"; and no table has been obtained from the CBS's census and social-survey pages."),
    # binding-fetch: RUS median_age/language/ethnicity notes (2,303 records): 'has not been read for this map ... on their own sites, which could not be reached, and the I
    (re.compile(r"\b(The 2020 census's (?:age|native language|nationality) by municipal unit) has not been read for this map\.( Rosstat's federal volumes publish it by subject only \(shown one level up\); below that the regional statistics offices publish it on their own sites), which could not be reached, and the Internet Archive holds copies of only about \d+ of their \d+ sites\."), r"\1 has not been obtained for this map.\2."),
    # binding-fetch: THA religion/language notes: 'the National Statistical Office's later census tables could not be read from its websites' (same family as the finding's
    (re.compile(r"\b([Tt]he National Statistical Office's later census tables) could not be read from its websites\."), r"\1 have not been obtained."),
    # binding-fetch: THA median_age_note (1,003): '-- could not be retrieved: its statistics host does not resolve, and the government's open-data portal and the National 
    (re.compile(r"\b(population register --) could not be retrieved: its statistics host does not resolve, and the government's open-data portal and the National Statistical Office's census websites could not be read\."), r"\1 has not been obtained."),
    # binding-fetch: THA Ban Kha (78962969B84740319728586) and Suan Phueng (78962969B47422412766823) median_age.note/sex_ratio.note: 'the only age-and-sex table this map c
    (re.compile(r"\bis the only age-and-sex table this map could read here(, .+?\. )Thailand's own figures could not be retrieved: the Department of Provincial Administration's register statistics \(stat\.bora\.dopa\.go\.th\) do not resolve, and the National Statistical Office's and the government's open-data websites could not be read\."), r"is the only age-and-sex table obtained for this district\1Thailand's own figures have not been obtained."),
    # binding-fetch: IDN ethnicity.note (513): 'no table of it by regency could be retrieved: BPS's own websites could not be read, and its 2010 census site (sp2010.bps.go
    (re.compile(r"\b(no table of it by regency) could be retrieved: BPS's own websites could not be read, and its 2010 census site \(sp2010\.bps\.go\.id\) serves one identical page at every address\."), r"\1 has been obtained."),
    # binding-fetch: IDN language.note (344): 'No count of this regency's languages could be retrieved. ... for some units only; BPS's own websites could not be read; and 
    (re.compile(r"\b(No count of this (?:regency|province)'s languages) could be retrieved\.( The 2010 census's household language reaches the map through CLEAR Global's tabulation of its IPUMS sample, for some units only); BPS's own websites could not be read;"), r"\1 has been obtained.\2;"),
    # binding-fetch: IDN religion.note (40): 'No table of this regency's religion could be retrieved. BPS's own websites could not be read, and neither...'
    (re.compile(r"\b(No table of this regency's religion) could be retrieved\. BPS's own websites could not be read, and neither"), r"\1 has been obtained from BPS, and neither"),
    # binding-fetch: EXTRA, same family as [None.8]: CHN 'X's own census yearbook has not been read.' (COUNTY_UNREAD)
    (re.compile(r"\b(own census yearbook) has not been read\."), r"\1 has not been obtained."),
    # binding-fetch: EXTRA, same family: CHN 'X's own census yearbook has been read, but none of the counties it counts could be shown to be this polygon.' (COUNTY_UNMATCH
    (re.compile(r"\b(own census yearbook) has been read, but none of the counties it counts could be shown to be this polygon\."), r"\1 counts its counties, but none of them could be shown to be this polygon."),
    # binding-fetch: EXTRA, same family: CHN Inner Mongolia median_age.note (27): 'but that workbook could not be read: the bureau's server refused it and the Internet Arc
    (re.compile(r"(, but that) workbook could not be read: (?:the bureau's server (?:refused it|did not answer)|the Internet Archive (?:holds no capture of it|did not serve its capture)|it could not be reached)(?: and the Internet Archive (?:holds no capture of it|did not serve its capture))?\."), r"\1 table has not been obtained."),
    # binding-fetch: EXTRA, same family: TLS religion/language .note (130): 'INETL's REDATAM dashboard, which tabulates the microdata to any geography, is served from a ba
    (re.compile(r"\b(INETL's REDATAM dashboard), which (tabulates the microdata to any geography), is served from a bare address that did not answer\."), r"\1 \2, but no table has been obtained from it."),
    # binding-fetch: EXTRA, same family: ARE Ajman/Fujairah/Ras al-Khaimah/Umm al-Quwain median_age/sex_ratio .note: 'could be read for this map: the federal statistics ce
    (re.compile(r"\b(No table of [^.:;]+?'s population by age and sex) could be read for this map: the federal statistics centre's site \((fcsc\.gov\.ae)\) refused the requests made for it, and the UAE's open-data portal \((bayanat\.ae)\) returned no dataset for a search for population\."), r"\1 has been obtained from the federal statistics centre (\2) or the UAE's open-data portal (\3)."),
    # binding-fetch: EXTRA, same family: ARE Dubai median_age/sex_ratio .note: '...but its site (dsc.gov.ae) refused the requests made for it, and no such table was found 
    (re.compile(r"\b(No table of Dubai's population by age and sex) could be read for this map\. The (Dubai Statistics Center publishes the emirate's population by sex and age group), but its site \((dsc\.gov\.ae)\) refused the requests made for it, and no such table was found among the Internet Archive's copies of the Center's reports\."), r"\1 has been obtained, although the \2 on its site (\3)."),
    # binding-fetch: EXTRA, same family: ARE Sharjah median_age/sex_ratio .note: '...could not be reached (dscd.sharjah.ae), and the federal statistics centre's site (fcsc
    (re.compile(r"\b(No table of Sharjah's population by age and sex) could be read for this map: (the emirate's Department of Statistics and Community Development), (which took its \d{4} census), could not be reached \((dscd\.sharjah\.ae)\), and the federal statistics centre's site \((fcsc\.gov\.ae)\) refused the requests made for it\."), r"\1 has been obtained from \2 (\4), \3, or from the federal statistics centre (\5)."),
    # binding-fetch: EXTRA, same family: MNG 'No capture of that book could be read from the Internet Archive, and 1212.mn, which served it, no longer answers.'
    (re.compile(r"\b(The 2020 census published religion for this aimag) (in the aimag's own results book)\. No capture of that book could be read from the Internet Archive, and 1212\.mn, which served it, no longer answers\."), r"\1, and anything it published by soum, \2. That book has not been obtained."),
    # binding-fetch: EXTRA, same family: MNG soum ethnicity.note (95): '...prints no table of ethnic group by soum that could be read.'
    (re.compile(r"; (this aimag's own results book, which is where the census published anything by soum), prints no table of ethnic group by soum that could be read\."), r"; no table of ethnic group by soum has been found in \1."),
    # binding-fetch: EXTRA, same family: MNG religion.note (3): 'This aimag's 2020 census results book was read, and no table ...'
    (re.compile(r"\b(This aimag's 2020 census results book) was read, and (no table of religious adherence in it could be resolved into a composition\.)"), r"\1 has been obtained, but \2"),
    # binding-fetch: EXTRA, same family: KNA (140): 'Saint Kitts and Nevis publishes nothing below the country from its 2011 census that could be read:'
    (re.compile(r"\bSaint Kitts and Nevis publishes nothing below the country from its (\d{4}) census that could be read:"), r"No figure below the country from Saint Kitts and Nevis's \1 census has been found:"),
    # binding-fetch: NEW (missed variant of [None.8], fetch failure): UZB religion/language/ethnicity .note on 198 admin2 records: '...; the government open-data portal da
    (re.compile(r"; the government open-data portal data\.egov\.uz refused the connection\."), r"; no table has been obtained from the government open-data portal (data.egov.uz)."),
    # binding-fetch: NEW (missed variant of [None.8], fetch failure plus agent wording): PAK Gilgit-Baltistan districts' language.note (10): '... because both sit behind h
    (re.compile(r"\bTwo routes are known and not taken( -- the MICS household microdata, which would cross language against district directly, and the Sociolinguistic Survey of Northern Pakistan, which mapped these valleys village by village --) because both sit behind hosts that deliberately refuse this kind of client, and this project does not disguise itself as a browser to get round that\."), r"Two further routes are known\1 but neither has been obtained."),
    # binding-fetch: NEW (missed variant of [None.8], fetch failure): ESP La Rioja religion_note (admin1 and admin2): 'Read from the CIS's PDF marginals ...: the study's p
    (re.compile(r"\bRead from (the CIS's PDF marginals for [^.:]+? as its former website published them, captured by the Internet Archive on [^.:]+): the study's page on the CIS's current site links them to pages that no longer answer\."), r"Taken from \1: the links to them on the study's page on the CIS's current site no longer work."),
    # binding-fetch: NEW (missed variant of [None.8], 'not been read for this map'): CHN language.note (2,399): '... published nowhere as data; this map has not read them,
    (re.compile(r"\bthis map has not read them\b"), r"they have not been obtained for this map"),
    # binding-fetch: NEW (missed variant of [None.8], 'has been read'): EGY language.note and ethnicity.note (748): '... and no census table of language/ethnicity by gover
    (re.compile(r"\b(no census table of (?:language|ethnicity) by governorate or district) has been read\."), r"\1 has been found."),
    # binding-fetch: NEW (missed variant, 'has been read'): MAR Tarfaya Province population and field notes: '... and no figure for the part north of it alone has been rea
    (re.compile(r"\b(no figure for the part north of it alone) has been read\b"), r"\1 has been found"),
    # binding-fetch: NEW (missed variant, 'has been read'): BHS North Abaco population.note: 'This polygon is the smaller local-government district, for which no count has
    (re.compile(r"\bfor which no count has been read\b"), r"for which no count has been found"),
    # binding-fetch: NEW (missed variant, 'has been read'): THA Bueng Kan Province religion.note: 'No religion figure for Bueng Kan Province on its own has been read. The 
    (re.compile(r"\b(No \w+ figure for [^.]+? on its own) has been read\. The one read for\b"), r"\1 has been found. The one given for"),
    # binding-fetch: NEW (missed variant, 'has been read'): DJI Djibouti population.note: '... so the city's figure is not this polygon's, and no figure has been read for 
    (re.compile(r"\bno figure has been read for that ground\b"), r"no figure has been found for that ground"),
    # binding-fetch: NEW (missed variant, 'has been read'): KHM Baray language.note: 'No source has been read for Baray. Kampong Thom's language figure and every other dis
    (re.compile(r"\bNo source has been read for ([^.]+?)\."), r"No source has been found for \1."),
    # binding-fetch: NEW (missed variant, 'was read'): IRN language.note (113): 'Nothing was read for <unit> itself. This is the population-weighted sum of the language es
    (re.compile(r"\bNothing was read for ([^.]+?) itself\. (?=This is the population-weighted sum of the language estimates)"), r"No language figure for \1 itself has been found. "),
    # binding-fetch: NEW (missed variant, 'read' as 'obtained'): BWA Gaborone population.note: '... so the city's count is not this polygon's, and no count read describes 
    (re.compile(r"\bno count read describes this ground\b"), r"no count for this ground has been found"),
    # binding-fetch: NEW (missed variant, 'read' as 'obtained'): GNQ Riaba population.note: 'This polygon is the district of Riaba, 379 km² of southern Bioko, and no figur
    (re.compile(r"\bno figure read describes it\b"), r"no figure for it has been found"),
    # binding-fetch: NEW (missed variant, 'read' as 'obtained'): SDN Abyei PCA population and language notes (admin1 and admin2): 'No statistics read for either country co
    (re.compile(r"\bNo statistics read for either country count it\b"), r"None of the statistics found for either country counts it"),
    # geometry: CHN Macau fragment (admin2 17275852B34966799109471): 'in the map' and dangling 'the file draws'
    (re.compile(r"\b(fragment of southern Coloane) in the map(, about [^;]*?, and the only second-level polygon) the file draws\b"), r"\1\2 the map draws"),
    # geometry: SLV 'Null' polygons field notes: 'so no census row is matched to it'
    (re.compile(r"\b(The map draws this polygon with no name), so no census row is matched to it\."), r"\1."),
    # geometry: JPN sliver (admin2 22064153B20100015994007) 'a sliver of the map', plus the same wording on SVN Maribor sliver (79292919B38849654156102)
    (re.compile(r"\b([Aa]) sliver of the map\b(?!')"), r"\1 sliver on the map"),
    # geometry: IRQ 'redrawn since the map's' (no noun after the possessive)
    (re.compile(r"\bsince the map's(?=[.,:;])"), r"since the map was drawn"),
    # geometry: UKR 100% type (Zmiiv 74538382B19382473130603, Staryi Sambir 74538382B78037249212092): 'cannot be split between the two' gives no reason, and 'people a
    (re.compile(r"\b100% of the area the 2001 census counts as ([^;]+?) lies in this polygon, and that area's people are drawn by the map outside the polygon of the raion it is the seat of \([^()]*\); the census's figures cannot be split between the two\."), r"100% of the area the 2001 census counts as \1 lies in this polygon, though that city is the seat of another raion; the census counts the city apart, so this raion's figures would not describe the polygon."),
    # geometry: UKR Khrystynivka type (Khrystynivka 74538382B17175920641899, Uman 74538382B32197013600938, Vitovka 74538382B2161330582129, Mykolaiv 74538382B842481208
    (re.compile(r"\b(?!100%)(\d+% of the area the 2001 census counts as [^;]+? lies in this polygon, )and that area's people are drawn by the map outside the polygon of the raion it is the seat of \("), r"\1and the map draws most of that city outside the polygon of the raion it is the seat of ("),
    # geometry: UKR variant beyond the finding's list: Makiivka 'that area's people are drawn in no polygon by a majority of its area' (Amvrosiivka 74538382B609642378
    (re.compile(r"\band that area's people are drawn in no polygon by a majority of its area; the census's figures cannot be split between the two\."), r"and no polygon holds a majority of that area; the census's figures for it cannot be split between the polygons it lies in."),
    # geometry: UKR 'only 0%' (Brovary 74538382B7147656565480, Chuhuiv 74538382B29130308321511, Voznesensk 74538382B59692398614753, Kropyvnytskyi 74538382B50656102387
    (re.compile(r"\bonly 0% of\b"), r"less than 1% of"),
    # geometry: PRK Nampo (admin1 3916807B42842403076429) population_note: 'the six South Phyongan rows the map draws inside it'
    (re.compile(r"\bSouth Phyongan rows the map draws\b"), r"South Phyongan counties the map draws"),
    # geometry: OMN WILAYAT AL MUDAYBI (60546857B87143917250519) and WILAYAT NIZWA (60546857B8832404475688): 'made since the map was drawn from this wilayat's ground'
    (re.compile(r"\b(made) since the map was drawn (from this wilayat's ground)"), r"\1 \2 since the map was drawn"),
    # geometry: UKR 'The polygon is X. The polygon is X by its name; ...' repeated sentence (207 records / 1,035 texts)
    (re.compile(r"\bThe polygon is ([^.;]+?)\. (The polygon is \1 by its name;)"), r"\2"),
    # geometry: NEW: JPN sliver (admin2 22064153B20100015994007): 'with no name in the map' in the same sentence item 3 rewrites (a variant of None.6's 'in the map')
    (re.compile(r"\bThis ([\d.]+ km2) polygon, with no name in the map, "), r"This unnamed \1 polygon "),
    # geometry: NEW (optional): UKR 16 records / 79 texts: '... and that area's people are placed in no polygon: the map's name for it and its outline disagree; the c
    (re.compile(r"\band that area's people are placed in no polygon: the map's name for it and its outline disagree; the census's figures cannot be split between the two\."), r"and that raion's figures are shown on no polygon, as the map's name for it and its outline disagree; the census's figures for it cannot be split between the polygons it lies in."),
    # database-words: [None.2] BTN gewogs: 'The figure here is the dzongkhag's own' contradicts 'This is the gewog's own count'
    (re.compile(r"The figure here is the dzongkhag's own, which its gewogs and towns add up to exactly\. (?=This is the gewog's own count\.)"), r""),
    # database-words: [None.2] BTN: 'the ethnicity field carries citizenship'
    (re.compile(r"\bthe ethnicity field carries citizenship, the one count of identity the census publishes\b"), r"citizenship, the one count of identity the census publishes, is shown under ethnicity"),
    # database-words: [None.2] BTN gewogs: 'and named on the dzongkhag's record'
    (re.compile(r"\band named on the dzongkhag's record\."), r"and named in the dzongkhag's population note."),
    # database-words: [None.2] BTN dzongkhags: 'less than this row'
    (re.compile(r"\b(the gewogs below come to that much less than) this row\."), r"\1 this figure."),
    # database-words: [None.2]/[None.11] BTN gewogs: 'The polygon was identified by this gewog's own reference point ...'
    (re.compile(r"The polygon was identified by this gewog's own reference point falling inside it and by Wikidata placing that gewog in this dzongkhag, not by either spelling\."), r"The polygon is shown as this gewog because the gewog's own reference point falls inside it and Wikidata places the gewog in this dzongkhag, not because of either spelling."),
    # database-words: [None.2]/[None.11] BTN gewogs: 'the polygon was identified by elimination ... is matched'
    (re.compile(r"\bso the polygon was identified by elimination: every other gewog of ([^.:]+?) is matched,"), r"so the polygon is shown as this gewog by elimination: every other gewog of \1 has its own polygon,"),
    # database-words: [None.11] NPL: 'the district was identified instead by which of the census's reference points fall inside the polygon'
    (re.compile(r"\bso the district was identified instead by which of the census's reference points fall inside the polygon\b"), r"so the district shown on it is the one indicated instead by which of the census's reference points fall inside the polygon"),
    # database-words: [None.11] SAU 'citizenship may stand on this field'
    (re.compile(r"\bcitizenship may stand on this field\b"), r"citizenship could be shown in its place"),
    # database-words: [None.11] PAK 'which the map carries on this field' (+ LAO 'which the map carries on the ethnicity field')
    (re.compile(r"\bwhich the map carries on (?:this|the ethnicity) field\b"), r"which the map shows under ethnicity"),
    # database-words: [None.11] PAK 'it is not republished under this field, and the language field beside this one'
    (re.compile(r"\bit is not republished under this field, and the language field beside this one says\b"), r"it is not shown under ethnicity, and the note under language says"),
    # database-words: [None.11]/[None.2] variant: 'It is shown on this field because ...' (BTN, IND, THA, TLS ethnicity notes)
    (re.compile(r"\bshown on this field because\b"), r"shown under ethnicity because"),
    # database-words: [None.2]/[None.11] variant: 'is on the ethnicity field' (BTN sex_ratio_note, HND and PAN language notes)
    (re.compile(r"\bis on the ethnicity field\b"), r"is shown under ethnicity"),
    # database-words: [None.11] variant: 'are on the language field' (TLS posts and admin0 TLS, PAK)
    (re.compile(r"\bare on the language field\b"), r"belong under language"),
    # database-words: [None.2]/[None.11] variant: admin0 'shows (it) on the ethnicity field under its basis' (BTN, MDV)
    (re.compile(r"\bshows (it )?on the ethnicity field under its basis\b"), r"shows \1under ethnicity, by its own name"),
    # database-words: [None.11] variant: PAK admin0 'is shown on the ethnicity field of the provinces and districts under its basis'
    (re.compile(r"\bis shown on the ethnicity field of the provinces and districts under its basis\b"), r"is shown under ethnicity for the provinces and districts, by its own name"),
    # database-words: [None.11] variant: XKX 'publishes this field for'
    (re.compile(r"\bpublishes this field for\b"), r"publishes these figures for"),
    # database-words: [None.11] variant: MMR 'unless a field says otherwise'
    (re.compile(r"\bunless a field says otherwise\b"), r"unless stated otherwise"),
    # database-words: [None.11] USA 'answers null for every county'
    (re.compile(r" and answers null for every county\b"), r", with no figure for any county"),
    # database-words: [None.11] variant 'record': IND 'and this record covers only what was left of it'
    (re.compile(r"\band this record covers only what was left of it\b"), r"and this unit covers only what was left of it"),
    # database-words: [None.11] variant 'record': KIR 'for the reason each island's record gives'
    (re.compile(r"\bfor the reason each island's record gives\b"), r"for the reason each island's note gives"),
    # database-words: [None.11] variant 'record': LVA 'as for the city's own municipal record'
    (re.compile(r"\bas for the city's own municipal record\b"), r"as for the city at the municipality level"),
    # database-words: [None.11] variant: PAK Gilgit-Baltistan 'which is what language_basis records and'
    (re.compile(r"\bwhich is what language_basis records and what keeps\b"), r"which is what keeps"),
    # database-words: [None.11] variant 'row': PAK Gilgit-Baltistan 'This row is the ten districts' own figures'
    (re.compile(r"\bThis row is the ten districts' own figures weighted\b"), r"The composition shown here is the ten districts' own figures weighted"),
    # database-words: [None.2] variant 'row': ARM Yerevan 'this is the city's own row'
    (re.compile(r"\bthis is the city's own row\b"), r"these are the city's own figures"),
    # database-words: NEW variant 'field': KHM ethnicity note 'which the map carries on the language field'
    (re.compile(r", which the map carries on the language field\."), r"."),
    # database-words: NEW variant 'field': CHN language.note 'so the field is not available rather than never collected'
    (re.compile(r", so the field is not available rather than never collected\."), r", so language is shown as not yet available rather than as never collected."),
    # database-words: NEW variant 'row': PAK Chitral language_note 'Khyber Pakhtunkhwa's own row above keeps the Other unbroken'
    (re.compile(r"\bKhyber Pakhtunkhwa's own row above keeps\b"), r"Khyber Pakhtunkhwa's own figures keep"),
    # database-words: NEW variant 'field': IDN Long Form notes 'the Bureau's dictionary dates the field to the census day'
    (re.compile(r"\bthe Bureau's dictionary dates the field to\b"), r"the Bureau's data dictionary dates these figures to"),
    # database-words: NEW data-model wording in the [None.2] BTN population_note: 'religion and language are declared rather than left empty'
    (re.compile(r"\breligion and language are declared rather than left empty\b"), r"religion and language are shown as not collected rather than left empty"),
    # Round 7's review, continued (files-joins).
    # files-joins: GUY questionnaire PDF name and byte count; KNA infographic PNG name (download-file names in parentheses)
    (re.compile(r" \([\w\-]+\.(?:pdf|png)(?:, [\d,]+ bytes)?\)"), r""),
    # files-joins: GUY 'Nothing read says whether' (same sentence as the questionnaire file name)
    (re.compile(r"\bNothing read says whether\b"), r"It is not clear whether"),
    # files-joins: USA 3,118 county religion_note: 'so this file cannot be used to ask about religion by race'
    (re.compile(r"\bthis file (cannot be used to ask about religion by race)\b"), r"these figures \1"),
    # files-joins: BHS 13 island ethnicity_note: 'The file's own dates are a 2021 extraction'
    (re.compile(r"\bThe file's own dates are an? (\d{4}) extraction;"), r"The table is dated \1, when it was extracted;"),
    # files-joins: TLS 4 Ermera posts population.note (Atsabe, Ermera, Letefoho, Railaco): 'where this file has two'
    (re.compile(r" A boundary drawn on the older division has one shape where this file has two\."), r" The map follows the older division and draws Hatulia as one shape, where the 2022 census has two posts."),
    # files-joins: TLS 4 Lautém posts population.note (Iliomar, Tutuala, Luro, Lautém): untrue 'joined' sentence
    (re.compile(r" A boundary drawn on the older division covers more ground than whichever of these rows it is joined to\."), r""),
    # files-joins: CHN 5 CFPS licence strings (sources[0].license): 'the file was read from a third-party re-upload on Kaggle'
    (re.compile(r"; the file was read from a third-party re-upload on Kaggle and only aggregate shares are kept\b"), r"; the copy used here is a third-party re-upload on Kaggle, and only aggregate shares are kept"),
    # files-joins: Factbook gap notes on admin0: 'No composition published by the Factbook for this entity.' (39) and 'Factbook lists no major urban areas for this entit
    (re.compile(r"\b(Factbook|major urban areas) for this entity\b"), r"\1"),
    # files-joins: NEW: FSM Chuuk municipalities religion.note and language.note (20 texts / 10 records, e.g. admin2/FSM 79324940B39467357025683 Weno): '... are not amon
    (re.compile(r"\bare not among the files the office's site or the Internet Archive's copies of its former one serve\."), r"are not among the documents on the office's site or in the Internet Archive's copies of its former one."),
    # files-joins: NEW: ESP ESS religion_note (13 texts / 13 records: 8 admin1, 5 admin2, e.g. admin1/ESP 25490228B84620027724461): 'Round 10 here is the self-completion
    (re.compile(r"\bRound (\d+) here is the self-completion file\b"), r"Round \1 here is the self-completion questionnaire"),
    # files-joins: NEW: PAK Gilgit-Baltistan districts language.note (10 texts / 10 records, e.g. admin2/PAK 60131773B26577032556552 Astore): 'its own upload index names
    (re.compile(r"\bits own upload index names no file at all for\b"), r"a search of the documents uploaded to its website finds none at all for"),
    # files-joins: NEW: PAK Azad Kashmir religion_note (2 texts / 2 records: admin1 70912109B7720427584286, admin2 60131773B7720427584286): '... rather than from the sam
    (re.compile(r"\brather than from the same file as the four provinces\b"), r"rather than from the same table as the four provinces"),
    # files-joins: NEW: CHN CFPS religion_note (5 texts / 5 records, e.g. admin1/CHN 43563684B11053367304830 Gansu): '... (rswt_natcs16) from the public-release file.'
    (re.compile(r"\bfrom the public-release file\b"), r"from the public-release data"),
    # files-joins: NEW: CHN CFPS religion_note (5 texts / 5 records): 'The same reading of the 2012 file, unweighted, reproduces Table 2 of Lu Yunfeng's report'
    (re.compile(r"\bThe same reading of the (\d{4}) file\b"), r"The same tabulation of the \1 wave"),
    # Round 7's review, continued (quotes-small).
    # quotes-small: NLD religion_note: raw Wikipedia link markup and cut-off archive link (CBS 2016 release; 10 provinces incl. Flevoland, Fryslân, Gelderland)
    (re.compile(r"Cited to: \[https?://\S+ ([^\]]+)\], CBS, (\d{1,2}) december (\d{4})\.(?: \[https?://[^\s\]]*\.(?= ))?"), r'Cited to: CBS, "\1", \2 December \3.'),
    # quotes-small: NLD religion_note: raw, garbled Wikipedia citation with a cut-off date (Limburg, Noord-Brabant)
    (re.compile(r"Cited to: \[https?://www\.cbs\.nl/-/media/_excel/2026/11/religie_2025_tabellen\.xlsx [^\]]*\] CBS, \d{1,2}\. \w+(?: \d+)?\."), r'Cited to: CBS, "Religie naar regio, 2021/2025", table 2 (the share of each religious group among people aged 15 and over, by province and region).'),
    # quotes-small: BLR population_note/sex_ratio_note with untransliterated Cyrillic: single raion or city (same sentence as the 11 records, other variant)
    (re.compile(r"(?<=\.) The (?:г\.)?[А-яЁё][А-яЁё-]*(?: район)? as the 2019 census counted it\."), r""),
    # quotes-small: BLR raion population_note/sex_ratio_note with untransliterated Cyrillic: raion plus its seat city (Babruysk, Baranovichy, Brest, Gomel, Grodno, Mogile
    (re.compile(r"The г\.[А-яЁё][А-яЁё-]*, [А-яЁё][А-яЁё-]* район as the 2019 census counted it; with it the city of ([A-Z][\w'-]*(?: [A-Z][\w'-]*)*), the raion's seat, counted apart\."), r"The 2019 census counted \1 raion and the city of \1, its seat, separately; the figures here add the two together."),
    # quotes-small: BLR raion population_note/sex_ratio_note with untransliterated Cyrillic: raion plus a city that is no raion's seat (Barysaw with Zhodzina, Polotsk wit
    (re.compile(r"The г\.[А-яЁё][А-яЁё-]*, [А-яЁё][А-яЁё-]* район as the 2019 census counted it; with it the city of ([A-Z][\w'-]*(?: [A-Z][\w'-]*)*), counted apart and drawn inside this polygon \(its centre lies in it\)\."), r"The 2019 census counted this raion and the city of \1 separately; the city's centre lies inside this outline, so the figures here add the two together."),
    # quotes-small: BLR Horki population_note/sex_ratio_note: two Cyrillic raion names (Горецкий, Дрибинский)
    (re.compile(r"The Горецкий район, Дрибинский район as the 2019 census counted it; with it Дрибинский район, formed from Horki raion in (\d{4}), which the map draws as part of this polygon\."), r"The 2019 census counted Horki raion and Drybin raion separately; Drybin raion was formed from Horki raion in \1, the map draws it as part of this outline, and the figures here add the two together."),
    # quotes-small: OMN region population.note '(of the governorates Dhofar)': one governorate
    (re.compile(r"(?<=in this region )\(of the governorates (?!of )([^,()]+)\)"), r"(of the governorate of \1)"),
    # quotes-small: OMN region population.note '(of the governorates A, B)': several governorates
    (re.compile(r"(?<=in this region )\(of the governorates (?!of )([^()]+), ([^,()]+)\)"), r"(of the governorates of \1 and \2)"),
    # quotes-small: KOR North Gyeongsang median_age_note 'those districts included' after one district (Uljin-gun)
    (re.compile(r"(The map draws [A-Z][\w-]*(?: [A-Z][\w-]*)* (?:inside [A-Z][\w-]*(?: [A-Z][\w-]*)*'s polygon|outside every province's polygon): the figures here are the register's for the whole province), those districts included,"), r"\1, that district included,"),
    # quotes-small: KOR companion sentence, same singular/plural slip: one district drawn here 'they are counted ... files them under' (Gangwon, North Chungcheong)
    (re.compile(r"((?:The map|It also) draws [A-Z][\w-]*(?: [A-Z][\w-]*)*'s [A-Z][\w-]*) inside this province's polygon; they are counted with the province the register files them under,"), r"\1 inside this province's polygon; it is counted with the province the register files it under,"),
    # quotes-small: NEW, missed variant of the KOR singular/plural slip: IND district notes say 'the rest is now in those districts' after a single carved-out district (5
    (re.compile(r"(\bwas carved out of it\. The shape drawn here keeps about \d+% of [^.]*?), and the rest is now in those districts\."), r"\1, and the rest is now in that district."),
    # quotes-small: NEW, missed variant of the MOZ missing article: LVA median_age_note 'from Central Statistical Bureau of Latvia, IRD041's count of residents by single 
    (re.compile(r"\bfrom Central Statistical Bureau of Latvia, (IRD\d+)'s count of residents by single year of age (?:on|at) the beginning of (\d{4});"), r"from the Central Statistical Bureau of Latvia's count (table \1) of residents by single year of age at the beginning of \2;"),
    # Round 7's review, continued (build-words, grammar).
    # build-words: COL ethnicity_note: 'The same workbook carries a second sheet naming 124 individual indigenous peoples, and it is not read.' (workbook, sheet, read)
    (re.compile(r"\bThe same workbook carries a second sheet naming (\d+) individual indigenous peoples, and it is not read\."), r"A second table in the same release names \1 individual indigenous peoples; it is not shown here."),
    # build-words: COL ethnicity_note: 'which is the sheet's own published universe of people who answered the question' (sheet)
    (re.compile(r"\bwhich is the sheet's own published universe\b"), r"which is the table's own published universe"),
    # build-words: TWN language_note: 'The census also recorded a secondary language, which is not read' (and the admin1 variant ending ': Hokkien is the second language
    (re.compile(r"\b(The census also recorded a secondary language), which is not read\b"), r"\1, which is not shown here"),
    # build-words: AFG ethnicity_note: '...as the English Wikipedia article ... transcribes them; the plan itself is not read here' (e.g. 17698898B14779938213850 Acheen)
    (re.compile(r"\bthe plan itself is not read here\b"), r"the plan itself has not been consulted here"),
    # build-words: IND Palghar scheduled_groups.note: 'published by sub-district in the primary census abstract, which is not read here'
    (re.compile(r"\b(published by sub-district in the primary census abstract), which is not read here\b"), r"\1, which is not used here"),
    # build-words: ESS religion/language notes: 'a census or register count replaces this estimate wherever one is read' (AUT/BEL/DEU/DNK/ESP/FRA/GRC/ITA/SWE...)
    (re.compile(r"\b(a census or register count replaces this estimate wherever one) is read\b"), r"\1 has been found"),
    # build-words: MYS population/ethnicity notes: 'so Sarawak's/Sabah's districts are read at 2024-01-01, the latest date whose districts are the map's'
    (re.compile(r"\b(districts are) read at (\d{4}-\d{2}-\d{2})\b"), r"\1 shown as at \2"),
    # build-words: MDA Bender/Transnistria religion.note and language.note: 'Not read: no census that counted Bender has published its religious affiliation.'
    (re.compile(r"\bNot read: no census\b"), r"No census"),
    # build-words: MDA Transnistria ethnicity.note: 'Not read as one figure: the sum of Transnistria's seven left-bank rows of its own 2015 census'
    (re.compile(r"\bNot read as one figure: the sum of\b"), r"This is not one published figure but the sum of"),
    # build-words: IRN language.note: 'N settlement estimate(s) could not be read as shares ...' and 'whose estimate could not be read as shares: its shares add to 80%, 
    (re.compile(r"\bcould not be read as shares\b"), r"could not be used as shares"),
    # build-words: IRN language.note: '... and was/were refused rather than guessed at' (refused as a build action)
    (re.compile(r"\b(was|were) refused rather than guessed at\b"), r"\1 left out rather than guessed at"),
    # build-words: BTN gewog median_age.note: 'no All Chiwogs block under the gewog's name could be read in the report's Table A2.7'
    (re.compile(r"\b(no All Chiwogs block under the gewog's name) could be read in\b"), r"\1 could be found in"),
    # build-words: Provenance ', read from ...' (THA gap_reason 'read from its provincial final reports', IRN 'read from the Internet Archive's capture of amar.org.ir', 
    (re.compile(r"(?:^|(?<=, ))read from\b"), r"taken from"),
    # build-words: Provenance 'Read from ...' opening a sentence: KAZ 'Read from the Bureau's workbook.', ESP 'Read from the CEO's anonymised microdata ...', ESP Caceres
    (re.compile(r"\bRead from\b"), r"Taken from"),
    # build-words: GBR (Scotland) religion/language notes: 'England and Wales are read from the 2021 census, so a comparison across the border spans ten years.'
    (re.compile(r"\bEngland and Wales are read from the (\d{4}) census\b"), r"The figures for England and Wales are from the \1 census"),
    # build-words: CHN county population_note: '..., Table 1-1, read for the polygon because the polygon is still this one county'
    (re.compile(r"\bread for the polygon because\b"), r"shown on the polygon because"),
    # build-words: SOM population.note: 'Read for every region from the one table, because several articles print figures that table does not give.'
    (re.compile(r"\bRead for every region from the one table\b"), r"Taken for every region from the one table"),
    # build-words: COD/MOZ population.note: 'The population statistics and language data read for the DRC count its people within ...' and 'The population statistics rea
    (re.compile(r"\b(The population statistics(?: and language data)?) read\b(?= (?:for the DRC|count))"), r"\1 used"),
    # build-words: SYC La Digue religion.note: 'The survey figures read for La Digue and Inner Islands, Afrobarometer's region, describe the whole district'
    (re.compile(r"\bThe survey figures read for\b"), r"The survey figures for"),
    # build-words: MNG soum sex_ratio_note: 'it is the office's count, read as published, and the table says nothing of why'
    (re.compile(r"\b(it is the office's count), read as published,"), r"\1 as published,"),
    # build-words: BTN dzongkhag median_age_note: '...; the median reads the totals.'
    (re.compile(r"\bthe median reads the totals\b"), r"the median uses the totals"),
    # build-words: LVA Madona/Varaklani median_age_note: 'Madona and Varaklani merged on 1 July 2025 and are drawn apart, so both are read before the merger.'
    (re.compile(r"\bso both are read before the merger\b"), r"so both are shown as they were before the merger"),
    # build-words: KHM province religion_note: '...transcribes the 2008 and 2019 census tables by province; the 2019 columns are read.'
    (re.compile(r"; the (\d{4}) columns are read\."), r"; the \1 columns are used."),
    # build-words: IRN language.note: 'The atlas's module for Khuzestan is read and the province carries its figure, but ...' and admin1 Kermanshah 'The atlas's module f
    (re.compile(r"\b(The atlas's module for [^.,;:]+?) is read\b"), r"\1 is published"),
    # build-words: IRN Rasht / Aran and Bidgol language.note: 'The atlas's settlements in Rasht that carry a population and a reading hold 272,266 people'
    (re.compile(r"\bthat carry a population and a reading hold\b"), r"that carry a population and a language estimate hold"),
    # build-words: IND district median_age.note (one parent district): 'The 2011 row that counted these people covers the undivided X. That row is on this map, on the sh
    (re.compile(r"\bThe (\d{4}) row that counted these people covers the undivided ([^.]+?)\. That row is on this map, on the shape that still bears that name -- now only the part left after this district was carved out, which the note on it says -- so the count exists and is for more ground than that shape covers\."), r"The \1 census counted these people in the undivided \2, so the count exists, but it is for more ground than the shape on this map that still bears that name -- now only the part left after this district was carved out, which the note on it says."),
    # build-words: IND district median_age.note (two or three parent districts, 8 texts: Amethi, Batod, Kamle, Lower Siang, Mahisagar, Morbi, Shahdara, Siang): the same 
    (re.compile(r"\bThe (\d{4}) row that counted these people covers the undivided ([^.]+?)\. That row is on this map, on the shape that still bears those names -- now only the part left after this district was carved out, which the note on it says -- so the count exists and is for more ground than that shape covers\. It is not repeated here:"), r"The \1 census counted these people in the undivided \2, so the counts exist, but they are for more ground than the shapes on this map that still bear those names -- now only the parts left after this district was carved out, which the notes on them say. They are not repeated here:"),
    # build-words: IND Jangaon/Jayashankar/Mahabubabad/... median_age.note: 'so the 2011 row covering this ground is on no district on this map either; the state total c
    (re.compile(r"\bthe (\d{4}) row covering this ground is on no district on this map either\b"), r"the \1 count covering this ground is shown on no district on this map either"),
    # build-words: IND shrunken-district notes: 'This figure is for X as the 2011 census measured it ... The shape drawn here keeps about 25% of the ground that row coun
    (re.compile(r"\bof the ground that row counted\b"), r"of the ground that figure covers"),
    # build-words: BHS island ethnicity_note: 'The race question, not the citizenship question that shares its sheet.'
    (re.compile(r"\bthe citizenship question that shares its sheet\b"), r"the citizenship question that shares its table"),
    # build-words: UKR raion language_note/ethnicity.note: 'The Bureau's Language sheet names eight languages ...', 'The Bureau's Nationality-Language sheet has no figur
    (re.compile(r"\b(The Bureau's (?:Nationality-)?Language) sheet\b"), r"\1 table"),
    # build-words: UKR raion language_note: 'N of the M people (0.2%) fall in none of the sheet's columns and are shown as 'Other and unspecified''
    (re.compile(r"\bnone of the sheet's columns\b"), r"none of the table's columns"),
    # build-words: CAF ethnicity_note: 'so this is an ethnicity table with a foreign tail rather than the nationality table Syria's sheet turned out to be'
    (re.compile(r"\brather than the nationality table Syria's sheet turned out to be\b"), r"rather than a nationality table like Syria's"),
    # build-words: MDV atoll ethnicity_note: 'publishes no breakdown of foreigners by country in its atoll sheet'; admin0 MDV ethnicity.note: 'for every atoll and island
    (re.compile(r"\b((?:\d{4} )?atoll) sheet\b"), r"\1 table"),
    # build-words: SYR admin0 ethnicity.note: 'the 2004 sheet labelled Ethnicity is a distribution by nationality, which is citizenship'
    (re.compile(r"\bthe (\d{4}) sheet labelled Ethnicity\b"), r"the \1 table labelled Ethnicity"),
    # build-words: 'written' as the build writing a figure onto a unit: 'so no share is written below the province' (IRN), 'so no etrap's figure is written' (TKM), 'noth
    (re.compile(r"\b((?:[Nn]o|[Nn]either)\b[\w' ]{0,40}?|[Nn]one|[Nn]othing|those counts) (is|are) written\b(?! as\b| together\b)"), r"\1 \2 shown"),
    # build-words: KHM Preah Sihanouk / Kampong Seila population and sex_ratio notes: '...so a district's figure from those tables would understate it by as much, and is
    (re.compile(r"\bwould understate it by as much, and is not written\."), r"would understate it by as much, and is not shown."),
    # build-words: YEM Hadhramaut/Socotra population.note: 'Its nationality, published only for the census's row, is not written.'
    (re.compile(r"\b(Its nationality, published only for the census's row,) is not written\."), r"\1 is not shown."),
    # build-words: VNM province ethnicity_note: 'Religion is not written: the volume's Table 3 gives it for the country only.' (the provinces do show religion, from the 
    (re.compile(r"\bReligion is not written: the volume's Table (\d+) gives it for the country only\."), r"Religion is not taken from this volume: its Table \1 gives it for the country only."),
    # build-words: CHN CFPS religion_note: '...for which the survey supports province-level inference; the other provinces are not written.'
    (re.compile(r"; the other provinces are not written\."), r"; its figures for the other provinces are not shown."),
    # build-words: PAK province religion_note: 'The two are the same figure -- the run checks that every district adds up to this exactly -- but ..., which a sum of what
    (re.compile(r"\b(The two are the same figure) -- the run checks that every district adds up to this exactly -- (but the printed row also covers the districts geoBoundaries has no shape for), which a sum of what landed on the map would silently leave out\."), r"\1 -- the districts add up to it exactly -- \2, which a sum of the districts drawn on the map would silently leave out."),
    # build-words: AFG district ethnicity.note: '...or is archived or transcribed under a name or a province the map does not match to this polygon.'
    (re.compile(r"\bunder a name or a province the map does not match to this polygon\b"), r"under a name or a province that could not be tied to this polygon"),
    # build-words: ETH notes: 'so this is the most recent measurement in existence, not the most recent available to this project' (owner wording)
    (re.compile(r"\bnot the most recent available to this project\b"), r"not merely the most recent one found for this map"),
    # build-words: PNG province religion_note: '...and no denominational breakdown for any province is online anywhere this project could reach' (owner wording)
    (re.compile(r"\bis online anywhere this project could reach\b"), r"has been found online"),
    # build-words: NEW: PAK Gilgit-Baltistan population_note (GB and its ten districts) and GB language_note: 'the Bureau publishes no census table for it at any path' /
    (re.compile(r"\b(publishes no (?:census|mother-tongue) table for (?:it|Gilgit-Baltistan)) at any path\b"), r"\1 on its website"),
    # build-words: NEW: PAK Azad Kashmir and Gilgit-Baltistan median_age.note and sex_ratio.note: '-- the four provinces and Islamabad have it, at every path the office 
    (re.compile(r", at every path the office files it under, and these two do not\."), r", wherever the office publishes it, and these two do not."),
    # grammar: Nordic/Baltic age template, offices with an abbreviation (NOR, SWE): '{source}, {table}'s count' -- 'from Statistics Norway (SSB), table 07459's count
    (re.compile(r"\bfrom (Statistics [A-Z][a-z]+) \(([A-Z]{2,4})\), (?:table )?([A-Za-z0-9]+)'s count of residents by single year of age on (\d{1,2} [A-Z][a-z]+ \d{4});"), r"from \1's count (\2, table \3) of residents by single year of age on \4;"),
    # grammar: Nordic age template, offices without an abbreviation (DNK, EST, FIN, ISL): '{source}, {table}'s count' -- 'from Statistics Denmark, FOLK1A's count of 
    (re.compile(r"\bfrom (Statistics [A-Z][a-z]+), (?:table )?([A-Za-z0-9]+)'s count of residents by single year of age on (\d{1,2} [A-Z][a-z]+ \d{4});"), r"from \1's count (table \2) of residents by single year of age on \3;"),
    # grammar: LVA admin1, same template: 'Registered residents on the beginning of 2026.' and 'Males per 100 females among residents on the beginning of 2026 (...)'
    (re.compile(r"\b(Registered residents|Males per 100 females among residents) on (the beginning of \d{4})\b"), r"\1 at \2"),
    # grammar: ARG department ethnicity notes: a sentence starts in lower case after a full stop -- '... so the department's indigenous population is one line. the c
    (re.compile(r"(?<=\. )the census asks nothing about European or mestizo ancestry\."), r"The census asks nothing about European or mestizo ancestry."),
    # grammar: VNM district population notes repeat the source: 'The 2019 census: the 2019 census's count of An Biên (district), Kiên Giang (Table 1).'
    (re.compile(r"\bThe (\d{4}) census: the \1 census's count of\b"), r"The \1 census's count of"),
    # grammar: IRQ district population notes: a census unit's bracketed second name is left unclosed -- 'Akd (Al-Daggara (89,503)', 'Al-Multaqa (Mullah Abdullah (Kir
    (re.compile(r"(?<=[\w'-]) \(([A-Z][\w'-]*(?:[ -][A-Za-z][\w'-]*)*) \((?=[\d,]+\)[,.]|[A-Z][\w'-]*\) \([\d,]+\)[,.])"), r" (\1) ("),
    # grammar: Redrawn second-level units drawn as 2 features with the same label: 'geoBoundaries draws ARAD as 2 features, one of them labelled 'ARAD'' says nothing
    (re.compile(r"\bgeoBoundaries draws ([^.;']+?) as 2 features, one of them labelled '\1';"), r"geoBoundaries draws \1 as 2 features, both labelled '\1';"),
    # grammar: Redrawn units drawn as 3+ features: one feature given several labels -- 'geoBoundaries draws VLAHITA as 6 features, one of them labelled 'VLAHITA' and
    (re.compile(r"\bgeoBoundaries draws ([^.;']+?) as (\d+) features, one of them labelled '\1'(?: and '\1')+;"), r"geoBoundaries draws \1 as \2 features, all labelled '\1';"),
    # grammar: The same slip with two different labels: 'geoBoundaries draws Opicina Pirovac as 3 features, one of them labelled 'Opicina Muter-Kornati' and 'Otok Ko
    (re.compile(r"\bgeoBoundaries draws ([^.;']+?) as 3 features, one of them labelled (?!'\1' and '\1';)('[^']*' and '[^']*');"), r"geoBoundaries draws \1 as 3 features, two of them labelled \2;"),
    # grammar: BOL Cercado parts: a list with no 'and' -- 'geoBoundaries draws the Cercado provinces of Beni, Cochabamba, Oruro, Tarija as one feature'
    (re.compile(r"(\bgeoBoundaries draws the [^.;]*? provinces of [^.;]*?), ((?:(?! and )[^,.;])+?) as one feature;"), r"\1 and \2 as one feature;"),
    # grammar: ALB former districts: 'the 8 municipalities and communes of 2011 that made up the one made up the other' (a sentence that reads as a stutter)
    (re.compile(r"\bthe (\d+) municipalities and communes of 2011 that made up the one made up the other\."), r"the two are made up of the same \1 municipalities and communes of 2011."),
    # grammar: GHA: doubled word 'Cape Cape Metropolitan Area' in 'The 2021 census's count for Cape Cape Metropolitan Area (CCMA).'
    (re.compile(r"\bCape Cape Metropolitan Area\b"), r"Cape Coast Metropolitan Area"),
    # grammar: AFG Sari Pul ethnicity note: doubled word 'for Saripul Saripul Center district, Sar-E-Pul province'
    (re.compile(r"\bfor Saripul Saripul Center district\b"), r"for Saripul Center district"),
    # grammar: ROU Bucharest sectors: a source note that is a lower-case fragment with no full stop -- 'the city's median, the check'
    (re.compile(r"^the city's median, the check$"), r"Gives the census's ages for the city as a whole, the check on the domicile figures."),
    # grammar: Admin0 Factbook gap notes: no article, no full stop -- 'Factbook reports free text only: Hutu, Tutsi, Twa, South Asian'
    (re.compile(r"^Factbook reports free text only: (.*(?:\.\.\.|[^.\s]))\s*$"), r"The CIA World Factbook gives only the words “\1”."),
    # grammar: Admin0 largest-settlement gap notes: no article before the source -- 'Factbook lists no major urban areas for this entity.'
    (re.compile(r"^Factbook lists no major urban areas\b"), r"The CIA World Factbook lists no major urban areas"),
    # grammar: '1 people whose age was not stated/known/declared are left out' (UKR raions, WSM districts, PAN)
    (re.compile(r"(?<![\d,.])\b1 people whose age was not (stated|known|declared) are left out\b"), r"1 person whose age was not \1 is left out"),
    # grammar: LCA settlements with one person: 'the 1 people the 2010 base holds in the settlement' (median age, ethnicity, religion and sex-ratio notes)
    (re.compile(r"(?<![\d,.])\bthe 1 people the\b"), r"the 1 person the"),
    # grammar: LCA one-person settlements: 'The 2010 count here has 1 men and 0 women'
    (re.compile(r"\bhas 1 men and 0 women\b"), r"has 1 man and 0 women"),
    # grammar: LCA one-person settlements: 'The 2010 count here has 0 men and 1 women'
    (re.compile(r"\bhas 0 men and 1 women\b"), r"has 0 men and 1 woman"),
    # grammar: GEO regions: '1 categories are suppressed in this region'
    (re.compile(r"(?<![\d,.])\b1 categories are suppressed\b"), r"1 category is suppressed"),
    # grammar: GEO: '(1 people)' after the suppressed-categories sentence
    (re.compile(r"\(1 people\)"), r"(1 person)"),
    # grammar: CHN counties: ''Other ethnic groups' is the 1 people whose nationality is not identified (未定族称) ...'
    (re.compile(r"(?<![\d,.])\bthe 1 people whose nationality is not identified\b"), r"the 1 person whose nationality is not identified"),
    # grammar: FSM Kolonia religion note: 'the 1 people in those cells (0.0%) are left out'
    (re.compile(r"(?<![\d,.])\bthe 1 people in those cells (\([^()]*\)) are left out\b"), r"the 1 person in those cells \1 is left out"),
    # grammar: LTU Rokiškis language note: '1 people are in cells the office withholds as confidential, and are counted in 'Other language''
    (re.compile(r"(?<![\d,.])\b1 people are in cells the office withholds as confidential, and are counted in\b"), r"1 person is in a cell the office withholds as confidential, and is counted in"),
    # grammar: CHE districts with a single commune: 'summed over the 1 communes of today that lie wholly within this unit'
    (re.compile(r"(?<![\d,.])\bthe 1 communes of today that lie wholly within\b"), r"the 1 commune of today that lies wholly within"),
    # grammar: FIN sub-regions: 'So are the 1 languages each spoken by under 0.05% of the sub-region (12 people in all).'
    (re.compile(r"\bSo are the 1 languages each spoken by\b"), r"So is the 1 language spoken by"),
    # grammar: IRN Gilan shahrestans: '1 places the atlas records as uninhabited carry no language and are excluded.'
    (re.compile(r"(?<![\d,.])\b1 places the atlas records as uninhabited carry no language and are excluded\b"), r"1 place the atlas records as uninhabited carries no language and is excluded"),
    # grammar: SLB South Vella la Vella: 'Its 1 wards: Vonunu.'
    (re.compile(r"\bIts 1 wards:"), r"Its 1 ward:"),
    # grammar: WSM districts with one listed village: 'The 2021 Census counts of the 1 villages the 2016 Census lists in Gagaemauga I on Upolu: Leauvaa.'
    (re.compile(r"\bCensus counts of the 1 villages the\b"), r"Census count of the 1 village the"),
    # grammar: USA District of Columbia religion note: 'Summed from the 1 counties PRRI publishes, ... so this is those counties' weighted mean'
    (re.compile(r"\bSummed from the 1 counties PRRI publishes, weighted by PRRI's own adult population -- the denominator its county shares are already expressed over, so this is those counties' weighted mean rather than a separate estimate\."), r"Taken from the 1 county PRRI publishes, so this is that county's own figure rather than a separate estimate."),
    # grammar: BTN gewogs with one non-citizen: '1,561 are Bhutanese (its Table 2.2) and 1 are not'
    (re.compile(r"(\(its Table 2\.2\) and 1) are not\b"), r"\1 is not"),
    # grammar: WSM districts with one foreign national: ''Foreign nationals' the 1 who are not.'
    (re.compile(r"(?<![\d,.])\bthe 1 who are not\."), r"the 1 who is not."),
    # grammar: BTN gewog with one non-citizen in the sex-ratio note: '1 of the 250 is not Bhutanese citizens (Table 2.2)'
    (re.compile(r"\b(1 of the [\d,]+ is not) Bhutanese citizens\b"), r"\1 a Bhutanese citizen"),
    # grammar: BTN Naro sex-ratio note: '1 of the 250 is not Bhutanese citizens (Table 2.2), 1 of them male and 0 female.'
    (re.compile(r"\b(1 of the [\d,]+ is not) (?:a Bhutanese citizen|Bhutanese citizens) \(Table 2\.2\), 1 of them male and 0 female\."), r"\1 a Bhutanese citizen (Table 2.2), and is male."),
    # grammar: VEN ethnicity notes with one indigenous person: '1 of the 2,155 people here do, and each people is its own line'
    (re.compile(r"(?<![\d,.])\b1 of the ([\d,]+) people here do\b"), r"1 of the \1 people here does"),
    # grammar: ESS (European Social Survey) notes with one non-respondent: '(1 refused, did not know or did not answer and are left out)'
    (re.compile(r"\(1 refused, did not know or did not answer and are left out\)"), r"(1 refused, did not know or did not answer and is left out)"),
    # grammar: PRY religion note: '4,156 people of that age answered here; 1 gave no answer and are left out.' (the same template in latvia.py: 'the other N gave no 
    (re.compile(r"(?<![\d,.])\b1 gave no answer and are left out\b"), r"1 gave no answer and is left out"),
    # grammar: PAK district sex-ratio notes: 'The 1 transgender persons the census counted are in the population and in neither figure.'
    (re.compile(r"\b([Tt]he) 1 transgender persons the census counted are in\b"), r"\1 1 transgender person the census counted is in"),
    # grammar: MHL atoll religion and ethnicity notes: 'the 1 counted in its institutions -- boarding schools, hospitals, hostels -- are in neither table.'
    (re.compile(r"(?<![\d,.])\bthe 1 counted in its institutions -- boarding schools, hospitals, hostels -- are in neither table\b"), r"the 1 counted in its institutions -- boarding schools, hospitals, hostels -- is in neither table"),
    # grammar: SLV ethnicity note: '1 did not know or did not say whether they are indigenous and are left out of the shares.'
    (re.compile(r"(?<![\d,.])\b1 did not know or did not say whether they are indigenous and are left out\b"), r"1 did not know or did not say whether they are indigenous and is left out"),
    # grammar: CHN county notes: '(1 of 内蒙古阿拉善经济开发区's 1 townships has no point to place it by (乌斯太镇))' -- a zone with a single township
    (re.compile(r"\b1 of ([^;()]+?)'s 1 townships has no point to place it by\b"), r"\1's only township has no point to place it by"),
    # grammar: AFG Parwan population note: a space inside a bracket -- 'Sia Gird ( Ghorbund)'
    (re.compile(r"\bSia Gird \( Ghorbund\)"), r"Sia Gird (Ghorbund)"),
    # grammar: GMB (2) and SYC (1) source notes begin in lower case with build wording: 'read from the Internet Archive's copy, https://web.archive.org/...'
    (re.compile(r"^(?:read|taken) from the Internet Archive's copy, "), r"Taken from the Internet Archive's copy, "),
    # grammar: DNK religion notes print the year twice: '(FOLK1A 2026K1; the population shown here is of 1 July 2026 2026)'
    (re.compile(r"\b(the population shown here is of \d{1,2} [A-Z][a-z]+ (\d{4})) \2\)"), r"\1)"),
    # grammar: VNM Côn Đảo (admin1) median-age and ethnicity gap notes: a capital after a semicolon -- '..., drawn at the first level; The 2019 census publishes ages
    (re.compile(r"\b(drawn at the first level); The (\d{4}) census\b"), r"\1; the \2 census"),
    # grammar: TON Niuas (admin1) population note: a capital after a semicolon -- '(General Table G 1); The map draws Niuafo'ou alone for the Niuas'
    (re.compile(r"(\(General Table G 1\);) The (map|boundary file) draws\b"), r"\1 the \2 draws"),
    # grammar: KAZ district notes: a list of two or three units with no 'and' -- 'holds Улытауский район and also Жезказган г.а., Сатпаев г.а., which the map does no
    (re.compile(r"(\band also (?:[^,;]+, )*?[^,;]+), ((?:(?! and )[^,;])+), (which the (?:map|boundary file) does not draw apart)"), r"\1 and \2, \3"),
)
# The keys whose text a visitor reads: notes, reasons and licences.
WORDED = re.compile(r"(?:^|_)note$|^gap_reason$|^license$")


def whole_items(head: str) -> str:
    """A quotation cut short, ended at its last whole item and marked "...".

    The Factbook's lists were cut at a word: Uruguay's religions ended
    "atheist 1.3%," and Bolivia's "agnostic 0.6%, none", a share without its
    number. A trailing comma goes, and in a list of shares the last item, if
    it has no share, is the one the cut broke and goes too. What is left ends
    on a whole item, so a second pass changes nothing.
    """
    head = head.rstrip()
    if head.endswith((",", ";")):
        return head.rstrip(",; ") + "..."
    depth, cut = 0, -1
    for i, ch in enumerate(head):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch in ",;" and depth == 0:
            cut = i
    if cut > 0 and "%" in head[:cut] and "%" not in head[cut:]:
        return head[:cut] + "..."
    return head + "..."


def plain_wording(text: str) -> str:
    """A visitor's text with PLAIN_PHRASES and PLAIN_PATTERNS applied."""
    for old, new in PLAIN_PHRASES:
        if old in text:
            text = text.replace(old, new)
    for pattern, new in PLAIN_PATTERNS:
        text = pattern.sub(new, text)
    return text


def notes_said(entity: dict[str, Any]) -> str:
    """Every note a visitor reads on a record, as one text: its own notes and
    the notes inside its figures and gaps."""
    parts = []
    for key, value in entity.items():
        if (key == "note" or key.endswith("_note") or key == "gap_reason") \
                and isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict) and isinstance(value.get("note"), str):
            parts.append(value["note"])
    return " ".join(parts)


def named_in(src: dict[str, Any], said: str) -> bool:
    """Whether a note names a source entry, as a sentence names a source
    (check_rollups.short_source: "Wikidata", "OCHA's common operational
    dataset", "Eurostat")."""
    short = check_rollups.short_source(str(src.get("name") or ""))
    return (bool(said) and len(short) >= 4 and short != "an unnamed source"
            and re.search(rf"(?<!\w){re.escape(short)}(?!\w)", said) is not None)


def tidy_citations(entity: dict[str, Any]) -> int:
    """Cite each figure shown to the source it is from, and each source once.

    Three ways a record's list came to cite what it does not show:
      * an entry kept a field whose figure another entry is the source of --
        Kuwait's census cited for the population beside the Factbook's, which
        is the figure shown; Ensenada's INEGI table of median ages beside
        OCHA's pooled median, which is -- unless a note names it, quoting its
        figure;
      * one source cited twice, for overlapping fields -- every Belarusian
        region's Wikidata item, "capital/coordinates" and "population/capital/
        coordinates";
      * a Wikidata item other than the record's own, cited for fields the
        record's own item is cited for -- Sokhumi's city item beside the
        district's.
    The panel lists each source once by name and link, so the visitor saw
    two of the last. Returns how many entries changed or went.
    """
    sources = entity.get("sources")
    if not isinstance(sources, list) or not sources:
        return 0
    changed = 0
    said = notes_said(entity)
    for field in FIGURE_FIELDS:
        value = entity.get(field)
        if not isinstance(value, dict) or is_gap(value):
            continue
        # The Factbook's entry cites every field ("*").
        if not any({field, "*"} & set(cited_fields(src)) and names_source(src, value)
                   for src in sources if src is not None):
            continue
        for i, src in enumerate(sources):
            if src is None:
                continue
            cites = cited_fields(src)
            # An entry a note names stays: the note quotes its figure --
            # "It replaces 139,628 for 2015, an older figure from the Lao
            # Statistics Bureau", "A newer figure is not shown: ... from
            # Wikidata".
            if field not in cites or names_source(src, value) or named_in(src, said):
                continue
            rest = [f for f in cites if f != field]
            sources[i] = dict(src, field="/".join(rest)) if rest else None
            changed += 1
    sources = [src for src in sources if src is not None]
    merged: list[dict[str, Any]] = []
    for src in sources:
        rest = {k: v for k, v in src.items() if k != "field"}
        twin = next((m for m in merged
                     if {k: v for k, v in m.items() if k != "field"} == rest), None)
        if twin is None:
            merged.append(dict(src))
            continue
        fields = cited_fields(twin)
        twin["field"] = "/".join(fields + [f for f in cited_fields(src) if f not in fields])
        changed += 1
    own = entity.get("wikidata")
    if own:
        mine = [m for m in merged if m.get("name") == "Wikidata"
                and str(m.get("url") or "").endswith(f"/{own}")]
        covered = {f for m in mine for f in cited_fields(m)}
        kept = [m for m in merged
                if not (m.get("name") == "Wikidata" and mine and m not in mine
                        and set(cited_fields(m)) <= covered)]
        changed += len(merged) - len(kept)
        merged = kept
    entity["sources"] = merged
    return changed


def plain_record(value: Any, key: str = "") -> int:
    """Put every note, reason and licence under a record in plain words; how many changed."""
    changed = 0
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, str) and WORDED.search(k):
                said = plain_wording(v)
                if said != v:
                    value[k] = said
                    changed += 1
            else:
                changed += plain_record(v, k)
    elif isinstance(value, list):
        for v in value:
            changed += plain_record(v, key)
    return changed


# A Wikidata item joined to a district by name is sometimes the town of that
# name, not the district. Before its population was fetched the mistake was
# invisible; afterwards Trinidad's Siparia region -- 86,949 people, drawn as
# one second-level shape -- read 2,374, the town's, and six Montenegrin
# municipalities and Algeria's Adrar took their towns' figures the same way.
# Two checks against the unit above, which is published independently:
#   * a division may not hold more than half again its parent's people;
#   * a parent's only division is the parent's ground, so its figure must
#     be within 0.6 and 1.6 of the parent's (years apart, not towns apart).
# Measured on 24 September 2026 over every Wikidata figure at this level,
# after the settlement check below has taken what it can tell from Wikidata's
# own classes: 28 fail with the namesake rule that follows, every one a town,
# a city proper, a parent's figure or a wrong item.
TOWN_RATIO_MAX = 1.5
SOLE_CHILD_BAND = (0.6, 1.6)
# And the other way round: a division named like its parent that carries the
# parent's figure. Utrecht's municipality item prefers 1,253,672 (2013), the
# province's; so do Groningen's and Midden-Drenthe's, and four Dominican
# municipalities named for their provinces -- San Felipe de Puerto Plata read
# 338,339 against a province of 335,424. Such a figure is within a quarter
# (or a third above) of the parent's, and with the other divisions beside it
# the parent is overfilled by more than a quarter. Those others must hold less
# than the parent does; when they hold more, the parent is the one that is
# wrong, and refuse_capital_figures below has already taken it off.
PARENT_BAND = (0.75, 1.33)
NO_ROOM = 1.25
# What the polygon is, where the drawing says more than the ratio does:
# (country, polygon) -> what follows "gives N (year), ". Djibouti's
# second-level polygon is filed under Arta, 63% of it lying there, and holds
# 99.8% of Djibouti region's polygon besides, with the GeoNames points of
# Djibouti, Balbala and Arta inside it; the item is the city's (Q3604).
TOWN_FIGURE_GROUND: dict[tuple[str, str], str] = {
    ("DJI", "Djibouti"): (
        "the figure of the city of Djibouti. This polygon, filed under Arta, holds the "
        "city and Balbala as well as the town of Arta and the land between them, so the "
        "city's figure is not this polygon's, and no figure has been read for that "
        "ground. It is left out."),
}


def fall_back(entity: dict[str, Any], refused: dict[str, Any],
              field: str = "population",
              usable: Callable[[dict[str, Any]], bool] | None = None) -> bool:
    """Put back a figure a fill-only file offered and Wikidata's figure held off.

    Wikidata and Wikipedia both fill only gaps, and Wikidata comes first, so
    Portugal's districts took their capitals' figures from Wikidata and the
    district figures their own Wikipedia articles print were held back. When
    a check refuses the figure in front, the first held one not from
    Wikidata takes its place, saying what it replaced.
    """
    for held in (entity.get("_held") or {}).get(field, []):
        value = held["value"]
        if not published(value):
            continue
        # A figure whose row reached the shape by a fragment of its name was
        # never evidence about this shape: "Severny District, Novosibirsk
        # Oblast" reaches Novosibirsk by containing it, and its 7,319 people
        # stood in for the city's 1.6 million.
        if str(held.get("match") or "").split("+")[0] in ("prefix", "contains"):
            continue
        if usable is not None:
            if not usable(held):
                continue
        elif str(value.get("source") or "").startswith("Wikidata"):
            continue
        # Every refusal ends "... is left out." and the one shown must say it
        # is not the one refused: a note reading "left out" over a figure
        # reads as that figure being the refused one.
        entity[field] = {**value, "note": (
            (value.get("note") + " " if value.get("note") else "")
            + re.sub(r"\bleft out(?=\.?$)", "left out and this figure is shown instead",
                     refused.get("note", "")))}
        entity.setdefault("sources", []).extend(held["sources"])
        # A count prefer_newer_figures held aside comes back as it was shown:
        # with its own note, and linked to the item it was linked to.
        if held.get("unit_note"):
            entity[f"{field}_note"] = held["unit_note"]
        if "link" in held:
            if held["link"]:
                entity["wikidata"] = held["link"]
            else:
                entity.pop("wikidata", None)
        return True
    return False


def prefer_newer_figures(admin1: dict[str, list[dict[str, Any]]],
                         admin2: dict[str, list[dict[str, Any]]]
                         ) -> tuple[list[str], list[str]]:
    """Put the newest population a unit was offered in front of an older count.

    A subdivision shows the most recent figure available (the owner's rule
    since round 7). merge_adapter lets the newer of two counts stand already,
    but holds an encyclopaedia's figure behind any count however recent, and
    a file held behind an office's census (HELD_ROWS) behind that census:
    a newer figure can be a different unit's. Wikidata's 2024 An Giang is the
    province Viet Nam made in 2025 out of three, on the old province's shape.
    So the held figure takes the count's place only where nothing says it is
    other ground:

      * it reached the unit by its whole name, an alias, a code or an id, not
        a fragment of its name -- Norway's 2026 Kristiansand, three of 2019's
        municipalities since 2020, reached the old one as "prefix+state" --
        and no declaration says its file's figure is other ground here
        (NOT_THIS_GROUND);
      * the count is not one put together for the polygon (GROUND_PINNED,
        COMPOSED_COUNT), and an encyclopaedia's figure is at most RECENCY_SPAN
        years newer: over longer, the change people make covers the
        difference between a city and the district around it, and an
        encyclopaedia names both alike (a projection held behind a census is
        of the census's own units, HELD_ROWS);
      * the change a year it makes from the count is one people make, at
        most GROWTH up or DECLINE down (check_rollups), and within
        RECENCY_SPREAD of the median change of the country's other units at
        its level offered a figure within those bounds, where there are
        RECENCY_PEERS of them, the unit's own left out; where there are
        fewer, within RECENCY_FEW, and where most of the level's offers are
        outside the bounds, only beside another offer that changes as it
        does. Viet Nam is why the median and the bound together: the merged
        provinces' figures run 8.7% a year and more above the 2019 census,
        and the provinces that were not merged change by about 1%. Nigeria
        is why the last: four of its five offers are no change a population
        makes, and the fifth, which is, is the 2006 census's count dated
        2026.

    A unit kept from its newer figure says so, and where it is far from its
    peers, gives the median change of the units at its level that do show
    newer figures.

    The count is held in the newer figure's place, with its note and its
    link, so a check that later refuses the newer figure -- a town's, a
    settlement's -- shows the count again (fall_back); and it rides on the
    newer figure as RESTATED_FROM, so the sums of compositions are still
    weighed on the counts the compositions come from. Returns one line for
    each unit given a newer figure and one for each kept from one.
    """
    refused_files = {(iso3, shape_id): declared["population"][0]
                     for (iso3, shape_id), declared in NOT_THIS_GROUND.items()
                     if "population" in declared}
    offers: list[tuple[str, dict[str, Any], dict[str, Any], float]] = []
    for table in (admin1, admin2):
        for iso3, rows in table.items():
            for entity in rows:
                shown = entity.get("population")
                value, year = published(shown), vintage(shown)
                if entity.get("water") or not value or not year or value <= 0:
                    continue
                origin = (entity.get("_from") or {}).get("population")
                if is_fill_only(origin, iso3):
                    continue                 # the newer of those already stands
                if origin in GROUND_PINNED:
                    continue
                said = " ".join(str(text or "") for text in (
                    entity.get("population_note"),
                    shown.get("note") if isinstance(shown, dict) else None))
                # A count put together for the polygon gives way only to a
                # newer figure put together the same way: a union of the same
                # places pooled from another file (pool_rows), as Mexico's
                # municipios drawn with those made out of them are pooled from
                # the 2020 census and from OCHA's table for 2024.
                together = composed(said)
                best = None
                for held in (entity.get("_held") or {}).get("population", []):
                    if together and "-POOL-" not in str(held.get("row") or ""):
                        continue
                    offered, when = published(held.get("value")), vintage(held.get("value"))
                    if (not is_fill_only(held.get("file"), iso3) or not offered
                            or not when or when <= year
                            or (iso3, held.get("file")) in OTHER_PEOPLE
                            or (held.get("file") in FILL_ONLY and when - year > RECENCY_SPAN)
                            or round(offered) == round(value)
                            or str(held.get("match") or "").split("+")[0]
                            in ("prefix", "contains")
                            or held.get("file") == refused_files.get((iso3, entity.get("id")))):
                        continue
                    if best is None or when > vintage(best["value"]):
                        best = held
                if best is not None:
                    rate = (published(best["value"]) / value) ** (
                        1 / (vintage(best["value"]) - year)) - 1
                    offers.append((iso3, entity, best, rate))
    # Peers are the country's other units at the same level, and only their
    # offers a population can make, within -DECLINE..GROWTH. Viet Nam's
    # provinces offered the 2025 merger's figures, 8.7% a year and more above
    # the 2019 census: in the median, they set it at +9.3% a year, and the
    # eleven provinces the merger left alone, changing by about 1% a year,
    # were kept off as far from their peers; and they set the median Viet
    # Nam's districts were weighed against until the levels were told apart.
    def possible(rate: float) -> bool:
        return -check_rollups.DECLINE <= rate <= check_rollups.GROWTH

    def median(rates: list[float]) -> float:
        ordered = sorted(rates)
        mid = len(ordered) // 2
        return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2

    offered: Counter[tuple[str, Any]] = Counter()
    plausible: dict[tuple[str, Any], list[tuple[int, float]]] = defaultdict(list)
    for iso3, entity, _, rate in offers:
        level = (iso3, entity.get("level"))
        offered[level] += 1
        if possible(rate):
            plausible[level].append((id(entity), rate))

    # Every offer is decided before any note is written, so a note can give
    # the change of the units that do show newer figures.
    decided: list[tuple[str, dict[str, Any], dict[str, Any], float, str]] = []
    for iso3, entity, best, rate in offers:
        level = (iso3, entity.get("level"))
        others = [r for who, r in plausible[level] if who != id(entity)]
        if len(others) >= RECENCY_PEERS:
            far = abs(rate - median(others)) > RECENCY_SPREAD
            verdict = "far" if far else ("taken" if possible(rate) else "large")
        elif not RECENCY_FEW[0] <= rate <= RECENCY_FEW[1]:
            verdict = "large"
        elif (2 * len(plausible[level]) < offered[level]
              and not any(abs(r - rate) <= RECENCY_SPREAD for r in others)):
            # Most of the level's newer figures are no change a population
            # makes, and one from among them that happens to sit close to its
            # count, with no other changing as it does, is not good for that:
            # two of Nigeria's five offers are dated 2026 and are the 2006
            # census's counts, and Ibadan South East's, -0.5% a year from
            # 2020, is one of the two.
            verdict = "most"
        else:
            verdict = "taken"
        decided.append((iso3, entity, best, rate, verdict))
    given: dict[tuple[str, Any], list[float]] = defaultdict(list)
    for iso3, entity, _, rate, verdict in decided:
        if verdict == "taken":
            given[(iso3, entity.get("level"))].append(rate)

    taken: list[str] = []
    kept: list[str] = []
    for iso3, entity, best, rate, verdict in decided:
        shown = entity["population"]
        line = (f"{iso3} {entity.get('name')}: {published(shown):,.0f} ({vintage(shown)}) "
                f"-> {published(best['value']):,.0f} ({vintage(best['value'])}), "
                f"{rate:+.1%} a year")
        if verdict != "taken":
            kept.append(line)
            shown_newer = given[(iso3, entity.get("level"))]
            if verdict == "far" and shown_newer:
                why = (f", where the newer figures shown for the country's other units at "
                       f"this level change by {median(shown_newer):+.1%} a year in the "
                       f"median. A figure so far from theirs may be of other ground or "
                       f"counted another way.")
            elif verdict == "far":
                why = (", far from the change the country's other newer figures at this "
                       "level make. A figure so far from theirs may be of other ground or "
                       "counted another way.")
            elif verdict == "most":
                why = (". Most of the newer figures for the country's other units at this "
                       "level change by more than a population does, and none of the rest "
                       "changes as this one does, so this one is not shown either.")
            else:
                why = (". A change that large may mean other ground or another way of "
                       "counting.")
            # Said on the unit, once every pass that may change its figure has
            # run (say_newer_not_taken): Kuwait's note had the governorates
            # show the census "where no newer figure is published", and
            # Farwaniya's and Jahra's are published and were not taken.
            entity["_not_taken"] = {"shown": published(shown), "offer": best["value"],
                                    "sentence": (
                f"A newer figure is not shown: {published(best['value']):,.0f} for "
                f"{vintage(best['value'])} from "
                f"{named_source(str(best['value'].get('source') or ''))}, "
                f"a {'rise' if rate > 0 else 'fall'} of {abs(rate):.1%} a year from the "
                f"figure shown" + why)}
            continue
        origin = entity.setdefault("_from", {})
        how = entity.setdefault("_how", {})
        # The count's citations go with it, as the restatement pass has it: one
        # citing the population alone is held with the count, and one citing
        # other fields too stays for those alone, its population held. Mexico's
        # 2,234 municipios cited INEGI's 2020 census for "population/sex
        # ratio/religion/language" beside OCHA's 2024 figure.
        cited: list[dict[str, Any]] = []
        kept_sources: list[dict[str, Any]] = []
        for src in entity.get("sources") or []:
            cites = str(src.get("field") or "").split("/")
            if "population" not in cites:
                kept_sources.append(src)
                continue
            cited.append(dict(src, field="population") if len(cites) > 1 else src)
            if len(cites) > 1:
                kept_sources.append(dict(src, field="/".join(f for f in cites
                                                             if f != "population")))
        held_list = entity["_held"]["population"]
        held_list.remove(best)
        # Held as the count it is, not as a figure of the item the unit is
        # linked to: a_unit refuses the refused item's own figures.
        held_list.insert(0, {"value": shown, "wikidata": None,
                             "file": origin.get("population"),
                             "match": how.get("population"), "sources": cited,
                             "unit_note": entity.get("population_note"),
                             "link": entity.get("wikidata")})
        # The count stays the figure a sum of compositions is weighed on
        # (control_population, gate_population): the compositions are the
        # census's, of the people it counted, not of the newer figure's.
        entity["population"] = {**best["value"], RESTATED_FROM: {
            k: shown[k] for k in ("value", "year", "source") if k in shown}}
        entity.pop("population_note", None)
        if best.get("unit_note"):
            entity["population_note"] = best["unit_note"]
        entity["sources"] = kept_sources + [src for src in best.get("sources") or []
                                            if src not in kept_sources]
        origin["population"] = best.get("file")
        how["population"] = best.get("match")
        if best.get("wikidata"):
            entity["wikidata"] = best["wikidata"]
        taken.append(line)
    return taken, kept


def say_newer_not_taken(*tables: dict[str, list[dict[str, Any]]]) -> int:
    """Say on a unit why a newer figure it was offered is not the one shown.

    Only where the figure shown is still the one the newer figure was weighed
    against: a pass after prefer_newer_figures that replaced it took the
    reason's subject with it. Returns how many units say so.
    """
    said = 0
    for table in tables:
        for rows in table.values():
            for entity in rows:
                why = entity.pop("_not_taken", None)
                if not why or published(entity.get("population")) != why["shown"]:
                    continue
                note = entity.get("population_note")
                entity["population_note"] = (f"{note} {why['sentence']}" if note
                                             else why["sentence"])
                said += 1
                # A median or ratio from the same table as the figure not
                # shown says so: 52 of Mexico's municipios show OCHA's 2024
                # median age, worked out from the age groups whose total is
                # the 2024 population their notes give as perhaps of other
                # ground.
                offer = why.get("offer") or {}
                for field in ("median_age", "sex_ratio"):
                    value = entity.get(field)
                    if (isinstance(value, dict) and not is_gap(value)
                            and value.get("source") and value.get("source") == offer.get("source")
                            and vintage(value) == vintage(offer)):
                        entity[f"{field}_note"] = join_note(
                            entity.get(f"{field}_note"),
                            f"It is from the same table as the {published(offer):,.0f} for "
                            f"{vintage(offer)} that the population's note says is not shown.")
    return said


def refuse_town_figures(admin1: dict[str, list[dict[str, Any]]],
                        admin2: dict[str, list[dict[str, Any]]]) -> int:
    """Take a Wikidata population off a district it cannot belong to."""
    refused = 0
    for iso3, rows in admin2.items():
        parents = {e["id"]: e for e in admin1.get(iso3, [])}
        siblings: dict[Any, int] = defaultdict(int)
        held: dict[Any, float] = defaultdict(float)
        for entity in rows:
            siblings[entity.get("parent")] += 1
            held[entity.get("parent")] += published(entity.get("population")) or 0
        for entity in rows:
            pop = entity.get("population")
            if not (isinstance(pop, dict) and pop.get("value")
                    and str(pop.get("source") or "").startswith("Wikidata")):
                continue
            parent = parents.get(entity.get("parent"))
            above = published(parent.get("population")) if parent else None
            if not above:
                continue
            ratio = pop["value"] / above
            sole = siblings[entity.get("parent")] == 1
            rest = held[entity.get("parent")] - pop["value"]
            what = "the town of this name"
            verdict = None
            if ratio > TOWN_RATIO_MAX:
                why = (f"more than {parent['name']}'s own {above:,.0f}, "
                       f"the unit it lies in")
            elif sole and not SOLE_CHILD_BAND[0] <= ratio <= SOLE_CHILD_BAND[1]:
                # Only the division drawn under it is said, not that it covers
                # the parent's ground: that is a measurement, and Algeria's
                # second level, the wilayas drawn again out of register, and
                # Naro-Fominsky under Moscow are not the parent's ground. Nor
                # is the figure said to be a town's: Naro-Fominsky's item is
                # the urban okrug, a unit, counted on other ground than the
                # polygon drawn under Moscow. What is known is that the two
                # do not match.
                why = (f"{ratio:.0%} of {parent['name']}'s {above:,.0f}, though "
                       f"this polygon is the only division drawn under "
                       f"{parent['name']}")
                verdict = "The figure does not describe the polygon as drawn, so it is left out."
            elif (not sole and rest < above
                  and PARENT_BAND[0] <= ratio <= PARENT_BAND[1]
                  and pop["value"] + rest > NO_ROOM * above
                  and related(name_forms(entity.get("name")),
                              name_forms(parent.get("name")))):
                why = (f"close to {parent['name']}'s own {above:,.0f}, though its "
                       f"other divisions hold {rest:,.0f} besides")
                what = f"{parent['name']} as a whole"
            else:
                continue
            ground = TOWN_FIGURE_GROUND.get((iso3, entity.get("name")))
            entity["population"] = gap(NOT_AVAILABLE, (
                f"Wikidata gives {pop['value']:,}"
                + (f" ({pop['year']})" if pop.get("year") else "")
                + " for a place of this name"
                + (f", {ground}" if ground else
                   f", which is {why}. "
                   + (verdict or f"It is probably {what} rather than this unit, so its "
                                 f"figure is left out."))))
            fall_back(entity, entity["population"])
            refused += 1
    return refused


# What the item joined to a district is, when Wikidata says. The name join
# cannot tell the town of Luba from Luba District, and before populations were
# fetched by id the mistake cost nothing; afterwards Bioko Sur's two districts
# read 7,739 and 1,071, the towns', and Armenia's raion of Tavush read the
# 1,454 people of the village of Tavush. scripts/fetch_wikidata.py
# --item-classes records every such item's classes, and an item whose every
# class is a kind of settlement -- no municipality, commune or district among
# them -- is a place people live in, not a unit they are counted by, and its
# figure is left out. An item that is both, as the cities of Japan and the
# municipalities of the Netherlands are, keeps its figure: it is the unit.
#
# Listed by hand from the classes the 19,451 items giving this level a figure
# carry, measured on 24 September 2026: settlements only. "Town in Romania",
# "city of Japan", "city in Finland", "prefecture-level city of China", "city
# of Indonesia" and the like are units of government and are not here; nor are
# the three bare "city" classes Estonia's town municipalities carry, nor "city
# in Cyprus" or "settlement of Andorra", whose towns are their units' ground.
#
# 188 figures were only settlements: Bled's 4,969 on a municipality of 8,000,
# Alytus city's 51,856 on Alytus District Municipality, Amman's four million
# on one of its districts. Two kinds keep theirs, because there the settlement
# is the unit:
#   * a shape named as a city -- Uzbekistan draws "Andijan" and "Andijan city"
#     side by side, and the city's item belongs on the second, which says so;
#   * a parent's only division within SOLE_CHILD_BAND of the parent -- Malta's
#     local councils, whose towns' figures are the councils' to a few percent.
SETTLEMENT_CLASSES: dict[str, str] = {
    "Q486972": "human settlement", "Q532": "village", "Q3957": "town",
    "Q515": "city", "Q1549591": "big city", "Q7930989": "city or town",
    "Q5084": "hamlet", "Q123705": "neighborhood", "Q188509": "suburb",
    "Q1637706": "city with millions", "Q200250": "metropolis",
    "Q174844": "megacity", "Q208511": "global city", "Q5119": "capital city",
    "Q108178728": "national capital", "Q11271835": "state capital",
    "Q27554677": "former capital", "Q129268952": "former national capital",
    "Q129319205": "de facto national capital", "Q3147563": "capital of regency",
    "Q51929311": "largest city", "Q902814": "border city", "Q2264924": "port city",
    "Q11422368": "city for international conferences and tourism",
    "Q707813": "Hanseatic city", "Q1187811": "college town",
    "Q691960": "satellite city", "Q1200957": "tourist destination",
    "Q11499984": "educational town", "Q9391358": "city with public health center",
    "Q692581": "holy city of Abrahamic religion", "Q11394721": "inland city",
    "Q828359": "commuter town", "Q677678": "fortified town",
    "Q317548": "resort town", "Q67123843": "town divided by border",
    "Q15661340": "ancient city", "Q620509": "military town",
    "Q40364446": "historic city", "Q4946461": "spa town",
    "Q1782540": "railway town", "Q28328984": "village in Armenia",
    "Q20724701": "city or town in Armenia", "Q21672098": "village of Ukraine",
    "Q12131624": "city in Ukraine", "Q12131640": "city of district significance",
    "Q2989457": "urban-type settlement",
    "Q4100864": "urban-type settlement in Ukraine",
    "Q15078955": "urban-type settlement in Russia",
    "Q20019082": "work settlement of Russia", "Q106389302": "city/town in Russia",
    "Q41501164": "village of Crimea", "Q28371991": "village of Yemen",
    "Q16127605": "populated place in Syria", "Q20202352": "locality of Mexico",
    "Q3257686": "locality", "Q16362394": "large village in Latvia",
    "Q89487741": "city in Bulgaria", "Q5770918": "city of Argentina",
    "Q63209072": "city of Colombia",
    "Q1852859": "cadastral populated place in the Netherlands",
    "Q14770218": "cantonal capital of Switzerland", "Q134626": "district capital",
    "Q137640468": "provincial capital", "Q1422929": "primate city",
    "Q8501237": "large city", "Q129676344": "large city", "Q18466176": "small city",
    "Q505681": "linear settlement", "Q378636": "village with a church",
    "Q22674925": "former settlement", "Q627236": "company town",
    "Q6882870": "designated spa town", "Q2202509": "Roman city",
    "Q1392581": "cycling city", "Q137547946": "Forest City",
}
ITEM_CLASSES = PROCESSED / "wikidata_admin2_item_classes.json"
# Cities that are the unit drawn, where the shape's name does not say so. CGAZ
# draws Novosibirsk's urban okrug, 26 by 44 km, the city's extent, as plain
# "Novosibirsk", and Wikidata calls the city nothing but a city.
SETTLEMENT_IS_THE_UNIT = frozenset({"Q883"})
CITY_SHAPE = re.compile(r"\b(city|kota|ciudad|ville|shahar)\b", re.I)


GEONAMES_SETTLEMENTS = PROCESSED / "geonames_settlements.json"
GEONAMES_SOURCE = {"field": "largest settlement", "name": "GeoNames",
                   "url": "https://www.geonames.org/", "license": "CC BY 4.0"}


GEONAMES_SEATS = PROCESSED / "geonames_seats.json"


def fill_capitals_from_geonames(admin1: dict[str, list[dict[str, Any]]],
                                admin2: dict[str, list[dict[str, Any]]]) -> int:
    """Each unit's seat from GeoNames, where no source named its capital.

    scripts/fetch_geonames.py keeps a seat only in countries whose GeoNames
    units are the map's -- most polygons hold exactly one seat of the level
    and next to none hold two -- and whose seats agree with the capitals
    other sources give. A capital that is a bare Wikidata id ("Q139491508",
    an item with no English label) is a blank shown as a code, and is
    replaced too.
    """
    seats = read_json(GEONAMES_SEATS, {}) or {}
    filled = 0
    for table in (admin1, admin2):
        for rows in table.values():
            for entity in rows:
                seat = seats.get(entity["id"])
                held = entity.get("capital")
                if not seat or entity.get("water"):
                    continue
                # A capital the unit's own seat contradicts, and that names a
                # town elsewhere in the country (Central Kalimantan's
                # "Banjarmasin"): a former capital read as the current one.
                if seat.get("refutes") and held == seat["refutes"]:
                    entity["capital"] = seat["seat"]
                    # Kept so the next placement still sees what the sources
                    # say; judged against the corrected capital, it would find
                    # nothing to refute and the next build would restore it.
                    entity["capital_refuted"] = held
                    entity["capital_note"] = (
                        f"{held}, which another source gives, stands elsewhere in "
                        f"the country; {seat['seat']} is this unit's own seat.")
                    entity.setdefault("sources", []).append({**GEONAMES_SOURCE, "field": "capital"})
                    filled += 1
                    continue
                bare_id = isinstance(held, str) and re.fullmatch(r"Q\d+", held)
                if "name" not in seat or not (is_gap(held) or bare_id):
                    continue
                entity["capital"] = seat["name"]
                entity.setdefault("sources", []).append(
                    {**GEONAMES_SOURCE, "field": "capital"})
                filled += 1
    return filled


# GeoNames places put inside a unit's polygon that belong to the unit beside
# it, where the polygons are simplified at the line: Chosica's point is 300 m
# outside Metropolitan Lima's outline, and GeoNames' own second-order code for
# it is Lima Province's (1501). Left unnamed rather than named for the region
# around Lima. (country, unit, place) -> the unit the place is part of. Where
# that unit is drawn at the same level under that very name and GeoNames puts
# no place of its own in it, the place is named there instead.
GEONAMES_ELSEWHERE: dict[tuple[str, str, str], str] = {
    ("PER", "Lima", "Chosica"): "Lima Province (Metropolitan Lima)",
    # Hwawŏn-eup is a town of Dalseong-gun, Daegu's one county, and GeoNames
    # files it there (second-order code 22310, KOSTAT's for Dalseong-gun);
    # its point is 0.002 degrees inside Dalseo-gu's simplified outline, and
    # Dalseong-gun's own polygon holds no GeoNames place at all.
    ("KOR", "Dalseo-gu", "Hwawŏn"): "Dalseong-gun",
}


@lru_cache(maxsize=1)
def seat_points() -> tuple[Any, list[dict[str, Any]]] | None:
    """GeoNames' seats down to the second order that have a population, as
    (STRtree of their points, the places), or None without the places file."""
    from fetch_geonames import PLACES, SEATS, read_places
    from shapely import STRtree
    from shapely.geometry import Point

    if not PLACES.exists():
        return None
    rows = [p for p in read_places() if p["code"] in SEATS and p["population"] > 0]
    return STRtree([Point(p["lon"], p["lat"]) for p in rows]), rows


def seat_drawn_for(geom: Any, iso3: str, name: str,
                   seats: tuple[Any, list[dict[str, Any]]]) -> dict[str, Any] | None:
    """The GeoNames seat whose point this polygon holds and that the polygon is
    drawn for, or None.

    scripts/fetch_geonames.py passes over a place whose first- or
    second-order code is not the one most places inside its polygon carry:
    it has most likely crossed a simplified line. A seat inside a polygon
    drawn for it has not, whatever the codes say. Minsk stands inside the
    Minsk City polygon, coded '04' among places coded '05' (Minsk Region's);
    Lima inside Metropolitan Lima, coded 'LMA' among places coded '15'; and
    Yamoussoukro inside its autonomous district. Each unit was given a
    village or a suburb as its largest settlement instead: Syenitsa,
    Santa Anita, Zata. The name test is the one that decides whether
    Natural Earth's place for a region stands in a polygon drawn for it
    (drawn_for), or the unit's own name in its own spelling (own_key).
    """
    tree, rows = seats
    mine = [rows[int(i)] for i in tree.query(geom, predicate="contains")]
    mine = [p for p in mine if p["iso3"] == iso3
            and (drawn_for(p["name"], name)
                 or (own_key(p["name"]) and own_key(p["name"]) == own_key(name)))]
    if not mine:
        return None
    best = max(mine, key=lambda p: p["population"])
    return {"name": best["name"], "population": best["population"],
            "geonameid": best["geonameid"], "feature_code": best["code"],
            "coordinates": [round(best["lon"], 5), round(best["lat"], 5)],
            "source": "GeoNames (CC BY 4.0)"}


# The reasons fetch_geonames gives for naming nothing where no place, or no
# place with a population, can be shown to stand in the unit.
NO_PLACE = ("no place with a population",
            "GeoNames lists no populated place that can be shown to stand in this unit")


def with_own_seat(town: dict[str, Any] | None, seat: dict[str, Any] | None,
                  taken: set[str]) -> dict[str, Any] | None:
    """A unit's GeoNames place once its own seat is counted among its places.

    The seat replaces the place fetch_geonames chose only where it is more
    populous than that place, which is what fetch_geonames would have done
    had it credited the seat: where the place chosen carries no figure (it
    was more than the unit), or was refused for being more than the unit and
    is larger than the seat, it stands. A seat GeoNames already gives to
    another unit of the same level is that unit's.
    """
    if not seat or seat["geonameid"] in taken:
        return town
    if not town or town.get("none") in NO_PLACE:
        return seat
    if "none" in town:
        spans = SPANS_REASON.match(town["none"])
        if spans and seat["population"] > int(spans["people"].replace(",", "")):
            return seat
        return town
    if town.get("geonameid") == seat["geonameid"] or not town.get("population"):
        return town
    return seat if seat["population"] > town["population"] else town


def fill_settlements_from_geonames(admin1: dict[str, list[dict[str, Any]]],
                                   admin2: dict[str, list[dict[str, Any]]],
                                   own_seats: dict[str, dict[str, Any]] | None = None) -> int:
    """The largest GeoNames place inside each unit, where no source named one.

    scripts/fetch_geonames.py places GeoNames' populated places in the map's
    own polygons and keeps the most populous that belongs; this reads the
    result, with a seat in the polygon drawn for it counted among the unit's
    places (``own_seats``, see seat_drawn_for). It never replaces a
    settlement a national source or Natural Earth named, and a town GeoNames
    counts larger than the unit it is in carries its name without that
    figure.
    """
    towns = read_json(GEONAMES_SETTLEMENTS, {}) or {}
    own_seats = own_seats or {}
    filled = 0
    for table in (admin1, admin2):
        level_ids = {e["id"] for rows in table.values() for e in rows}
        # A seat is not counted for a unit where GeoNames gives it to another
        # unit of the same level.
        held_by: dict[str, set[str]] = defaultdict(set)
        for sid in level_ids:
            town = towns.get(sid) or {}
            if town.get("geonameid"):
                held_by[town["geonameid"]].add(sid)
        placed = {}
        for sid in level_ids:
            seat = own_seats.get(sid)
            taken = ({seat["geonameid"]} if seat and held_by.get(seat["geonameid"], set()) - {sid}
                     else set())
            placed[sid] = with_own_seat(towns.get(sid), seat, taken)
        moved: dict[tuple[str, str], dict[str, Any]] = {}
        for iso3, rows in table.items():
            for entity in rows:
                town = placed.get(entity["id"])
                # A lake is water whatever town stands on its islands or shore.
                if not town or entity.get("water") or not is_gap(entity.get("largest_settlement")):
                    continue
                where = GEONAMES_ELSEWHERE.get((iso3, entity.get("name"), town.get("name")))
                if where:
                    entity["largest_settlement"] = gap(NOT_AVAILABLE, (
                        f"No GeoNames place is named: the most populous place GeoNames "
                        f"puts inside this outline, {town['name']}"
                        + (f" ({town['population']:,})" if town.get("population") else "")
                        + f", is part of {where}, drawn as a unit of its own; its "
                          f"point lies just outside that unit's simplified outline."))
                    moved[(iso3, where)] = town
                    continue
                filled += name_geonames_place(entity, town)
        for iso3, rows in table.items():
            for entity in rows:
                town = moved.get((iso3, entity.get("name")))
                if not town:
                    continue
                held = placed.get(entity["id"]) or {}
                shown = entity.get("largest_settlement")
                said = (shown.get("note") if isinstance(shown, dict) else None) or ""
                if (held.get("none") in NO_PLACE and not entity.get("water")
                        and is_gap(shown)
                        and (not said or said.startswith("No GeoNames place is named"))):
                    entity["largest_settlement"] = gap(NOT_AVAILABLE)
                    filled += name_geonames_place(entity, town)
    return filled


def name_geonames_place(entity: dict[str, Any], town: dict[str, Any]) -> int:
    """Name a GeoNames place as the unit's largest settlement, or say why none is."""
    if "none" in town:
        held = entity.get("largest_settlement") or {}
        if not held.get("note"):
            entity["largest_settlement"] = gap(
                held.get("status") or NOT_AVAILABLE,
                f"No GeoNames place is named: {town['none']}.")
            # The one refusal that turns on the unit's population, which is
            # weighed again once the populations are final
            # (settle_geonames_spans).
            spans = SPANS_REASON.match(town["none"])
            if spans:
                entity["largest_settlement"]["_spans"] = {
                    "town": spans["town"],
                    "people": int(spans["people"].replace(",", ""))}
        return 0
    entity["largest_settlement"] = town["name"]
    if town.get("population"):
        entity["largest_settlement_population"] = measure(
            town["population"], source="GeoNames (CC BY 4.0)")
    entity.setdefault("sources", []).append(dict(GEONAMES_SOURCE))
    return 1


# scripts/fetch_geonames.py names no settlement where the most populous place
# inside a unit outnumbers the unit SPANS times over -- a city the unit is only
# part of, or a place across a boundary -- and says so in these words, with
# the unit's population as the map showed it when the places were placed.
SPANS_REASON = re.compile(r"^(?P<town>.+) \((?P<people>\d{1,3}(?:,\d{3})*)\) is more than "
                          r"the unit \((?P<unit>\d{1,3}(?:,\d{3})*)\)")


def beyond_unit_note(town: str, people: float, unit: float) -> str:
    """Why a GeoNames place more than SPANS times its unit is not named.

    Only what was measured: the place is not the unit's own name, and its
    figure is too large to be the unit's town. Which of the reasons a figure
    can be that large -- a city the unit is part of, a place across a line,
    an older or wider count -- is not something the build has checked, so it
    is not asserted: Kep's 35,990 in Kaeb is the province's 2008 count."""
    return (f"No GeoNames place is named: GeoNames gives {town} {people:,.0f} people, "
            f"more than one and a half times the unit's {unit:,.0f}, so it is not taken "
            f"to be the unit's own town. Its figure may be of a city the unit is only "
            f"part of, of a place across a boundary, or a wider or older count than "
            f"the unit's.")


def drawn_elsewhere_note(town: str, people: float, unit: float) -> str:
    """Why a GeoNames place a little more than its unit, named like another unit, is not named."""
    return (f"No GeoNames place is named: {town} ({people:,.0f}) is more than the unit "
            f"({unit:,.0f}), and the map draws a unit named like it elsewhere, so it "
            f"cannot be shown to be this unit's town.")


def settle_geonames_spans(admin1: dict[str, list[dict[str, Any]]],
                          admin2: dict[str, list[dict[str, Any]]]) -> tuple[int, int]:
    """Weigh GeoNames' 'more than the unit' refusals against the final populations.

    The refusal is a comparison with the unit's population, and fetch_geonames
    made it against whatever population the map carried on the day it ran.
    Populations change after that, and the reason then quotes a figure the map
    no longer shows: Bukhar-Zhyrauskiy's said Temirtau (170,600) outnumbered
    the unit's 52,263 while the map gave the district 798,840, and Kulob
    District's that Kulob (214,700) outnumbered 96,000 against the census's
    216,830. So the comparison is made again here, against the population the
    record is written with. Where the place no longer outnumbers the unit
    SPANS times over it is named, as fetch_geonames would have named it, with
    its population only where that is not more than the unit's; where it still
    does, the reason quotes the population shown; and where the unit has none,
    the reason says that instead of quoting one.

    A place that is still more than the unit, if less than SPANS times, is
    named only when no other unit of the country is drawn under its name, or
    when it bears the unit's own name (see town_stands). The margin is for a
    town whose GeoNames figure is older or wider than the unit's count; it is
    not for Dushanbe, whose point GeoNames puts inside Rudaki District's
    polygon while the map draws the city as a first-level unit of its own, of
    948,251 people beside Rudaki's 603,337. The unit itself, the units above
    it and the units drawn inside it do not count: Pristina is drawn inside
    the District of Prishtina.

    Returns (named, restated).
    """
    named = restated = 0
    for iso3 in sorted(set(admin1) | set(admin2)):
        units = admin1.get(iso3, []) + admin2.get(iso3, [])
        apart_from = drawn_apart(units)
        for entity in units:
            held = entity.get("largest_settlement")
            if not isinstance(held, dict) or "_spans" not in held:
                continue
            spans = held.pop("_spans")
            town, people = spans["town"], spans["people"]
            unit = published(entity.get("population"))
            if unit is not None and (people <= unit
                                     or town_stands(town, people, unit, entity, apart_from)):
                entity["largest_settlement"] = town
                if people <= unit:
                    entity["largest_settlement_population"] = measure(
                        people, source="GeoNames (CC BY 4.0)")
                entity.setdefault("sources", []).append(dict(GEONAMES_SOURCE))
                named += 1
                continue
            was = held.get("note")
            if unit is not None and people <= GEONAMES_SPANS * unit:
                held["note"] = drawn_elsewhere_note(town, people, unit)
            elif unit is not None:
                held["note"] = beyond_unit_note(town, people, unit)
            else:
                held["note"] = (f"No GeoNames place is named: the most populous place "
                                f"GeoNames puts inside it, {town} ({people:,}), cannot "
                                f"be weighed against a population for the unit, which "
                                f"has none here, so it may be a city the unit is only "
                                f"part of, or a place across a boundary.")
            restated += held["note"] != was
    return named, restated


# Words that make a unit's name the town itself: Russia's urban okrugs and
# closed towns ("городской округ Радужный", "ЗАТО Заозёрск"), Vietnam's
# provincial cities and towns ("Thành phố Bà Rịa"), Azerbaijan's cities
# ("Lənkəran şəhəri") and a name ending "City" ("Al Mukalla City"). Read only
# to compare a GeoNames place the unit's polygon holds with the unit's own
# name (see own_key), never in a join.
TOWN_UNIT = re.compile(
    r"^(?:городской округ|зато|город|г\.|thành phố|thanh pho|thị xã|thi xa)\s+"
    r"|\s+(?:şəhəri|seheri|city)$")
# A leading Arabic article: "Al Mukalla City" against GeoNames' "Mukalla".
ARTICLE = re.compile(r"^(?:al|el)[\s-]+")
# Russian Cyrillic in the romanisation GeoNames uses for its own names
# (Raduzhny, Slobodskoy, Zaozërsk); the doubled letters that leaves are
# folded away by own_key. And the Azerbaijani schwa, which GeoNames writes
# "a" (Lankaran) where FOLD makes it "e".
CYRILLIC = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ə": "a",
})
# Ho Chi Minh City's numbered districts, which GeoNames writes in words
# ("Quận Mười Một") and the boundary file in figures ("Quan 11"). Only after
# "Quận" with its marks, so Hà Giang's Quản Bạ, written "Quan Ba", is not
# district 3.
VIET_NUMBER = {"một": "1", "hai": "2", "ba": "3", "bốn": "4", "tư": "4", "năm": "5",
               "sáu": "6", "bảy": "7", "tám": "8", "chín": "9", "mười": "10",
               "mười một": "11", "mười hai": "12"}
VIET_DISTRICT = re.compile(r"\bquận (mười một|mười hai|mười|một|hai|ba|bốn|tư|năm|"
                           r"sáu|bảy|tám|chín)\b")


@lru_cache(maxsize=200_000)
def own_key(text: str | None) -> str:
    """A unit's or a place's name as two spellings of one town agree on it.

    norm() keeps a name in its own script and spelling, which is right for a
    join: a romanisation this code invents is a guess about which place a
    row means. This is asked something narrower -- whether a GeoNames place
    whose point the unit's own polygon holds bears the unit's name -- and the
    place is already located. So here the town words come off ("городской
    округ", "Thành phố", "şəhəri", "City", a leading "Al"), Cyrillic is
    romanised as GeoNames romanises it, Ho Chi Minh City's district numbers
    are read as figures, and the letters spellings of one name trade are
    folded together: ə and a (Lənkəran, Lankaran), y and i (Quy Nhon, Qui
    Nhon), x and kh (Yevlax, Yevlakh), a doubled letter and a single one
    (Khoramshahr, Khorramshahr).
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).lower().strip()
    text = VIET_DISTRICT.sub(lambda m: "quận " + VIET_NUMBER[m.group(1)], text)
    text = TOWN_UNIT.sub("", text).strip()
    text = ARTICLE.sub("", text)
    key = norm(text.translate(CYRILLIC))
    key = key.replace("x", "kh").replace("y", "i")
    # Letters only: Quan 11 is not Quan 1.
    return re.sub(r"([^\W\d_])\1+", r"\1", key)


def town_unit(name: str | None) -> bool:
    """Whether a unit's name says the unit is a town or city itself."""
    return bool(name) and bool(TOWN_UNIT.search(
        unicodedata.normalize("NFC", name).lower().strip()))


def drawn_apart(units: list[dict[str, Any]]):
    """A test of whether the map draws a unit named like a town somewhere
    other than the unit itself, the units above it and the units drawn inside
    it, over one country's units (see settle_geonames_spans).

    With ``loose`` it reads names by own_key as well as norm(), for a town
    that bears the unit's own name in another spelling: Mukalla, in Al
    Mukalla City, has Al Mukalla drawn beside it under the same name."""
    drawn: dict[str, set[str]] = defaultdict(set)
    loosely: dict[str, set[str]] = defaultdict(set)
    inside: dict[Any, set[str]] = defaultdict(set)
    for entity in units:
        if norm(entity.get("name")):
            drawn[norm(entity.get("name"))].add(entity["id"])
        if own_key(entity.get("name")):
            loosely[own_key(entity.get("name"))].add(entity["id"])
        inside[entity.get("parent")].add(entity["id"])

    def apart(town: str, entity: dict[str, Any], loose: bool = False) -> bool:
        near = {entity["id"], entity.get("parent")} | inside[entity["id"]]
        found = set(drawn.get(norm(town), set()))
        if loose:
            found |= loosely.get(own_key(town), set())
        return bool(found - near)
    return apart


def town_stands(town: str, people: float, unit: float, entity: dict[str, Any],
                apart_from) -> bool:
    """Whether a GeoNames place more than its unit is still named, without its figure.

    GeoNames placed the place by its point, inside this unit's polygon; what
    is weighed here is whether its figure says it is a different place.

    Within SPANS times the unit it is named unless another unit of the country
    is drawn under its name -- and even then where the place bears this unit's
    own name. The test of a name drawn apart reads names the way the joins
    do, so "Kyiv Oblast" is drawn under "Kyiv", and the boundary file names
    Baltimore County "Baltimore" and the regency of Bekasi "Bekasi"; on its
    own it took Kyiv off the city of Kyiv, Baltimore off Baltimore city and
    Bekasi off Kota Bekasi, each with a figure a little above a census that
    is older or narrower than GeoNames'. Japan's two Oyamas and Portugal's
    two Calhetas are a city and a town far apart, and the point says which
    one this is. Dushanbe is not Rudaki District's name, and stays unnamed
    there.

    Beyond SPANS times the unit the place may be a city the unit is only part
    of, or a place across a boundary -- Aden in Kritar - Sirah, Ibadan in
    Ibadan North East, Bratislava in Bratislava I -- and it is named only
    where it bears the unit's own name and no other unit is drawn under that
    name: Drammen (106,013) in the municipality of Drammen (68,933), Periam
    (6,563) in the commune of Periam (4,196), where GeoNames' figure is older
    than the census or reaches past the town.

    The unit's own name is read in its own spelling or script too (own_key):
    Qui Nhon in Quy Nhon, Lankaran in Lənkəran şəhəri, Raduzhny in городской
    округ Радужный, Quận Mười in Quan 10. And a unit whose name says it is the
    town (TOWN_UNIT) keeps its own town beside another unit named for it:
    Slobodskoy is the urban okrug's town, whatever Slobodskoy District around
    it is called, and Raduzhny the okrug's in Khanty-Mansi, whatever Vladimir's
    closed town of the name is. Tirmiz, in Termez District beside Termez city,
    is not the district's name and is still refused, as is Bukhara in Bukhara
    District beside Bukhara city.
    """
    mine = entity.get("name")
    same = bool(norm(town)) and norm(town) == norm(mine)
    loose = bool(own_key(town)) and own_key(town) == own_key(mine)
    if people <= GEONAMES_SPANS * unit:
        # The very name as well as a related one: related() reads no name
        # whose last word is shorter than PREFIX_MIN, so it found neither
        # Ono in Ono nor Orange Bay in Orange Bay.
        return (not apart_from(town, entity) or same or loose
                or related(name_forms(town), name_forms(mine)))
    return (same or loose) and (town_unit(mine)
                                or not apart_from(town, entity, loose=True))


GEONAMES_FIGURE = "GeoNames (CC BY 4.0)"


def settle_settlement_figures(admin1: dict[str, list[dict[str, Any]]],
                              admin2: dict[str, list[dict[str, Any]]]) -> tuple[int, int]:
    """Weigh every largest settlement's figure against the unit's final population.

    scripts/fetch_geonames.py gives a place its figure only where that is not
    more than the unit's population, and names no place at all where it is
    more than SPANS times the unit, or more than the unit while the map draws
    a unit of its name elsewhere. It weighs against the population the map
    carried on the day it ran, and a unit that had none then kept its town's
    figure whatever it was. Populations filled or lowered since then turned
    the rule over: Kritar - Sirah, a district of Aden, came out at 76,723
    people beside Aden's 1,079,670, and Hirat district at 506,896 beside
    Herat's 574,300. settle_geonames_spans weighs again only the places
    fetch_geonames refused; this weighs the ones it named, against the
    population each record is written with.

    A GeoNames place more than SPANS times the unit, or more than the unit
    and drawn as a unit of its own elsewhere, is not named, with
    fetch_geonames' reason, unless town_stands finds it is the unit's own
    town; one that is only more than the unit keeps its name and loses its
    figure. Natural Earth's figures are of a metropolitan area
    the place stands for -- Tokyo's 35,676,000 beside the prefecture's
    14,047,594 -- so its name, found by the unit's own name rather than a
    point, stands and only the larger figure goes.

    Returns (unnamed, unfigured).
    """
    unnamed = unfigured = 0
    for iso3 in sorted(set(admin1) | set(admin2)):
        units = admin1.get(iso3, []) + admin2.get(iso3, [])
        apart_from = drawn_apart(units)
        for entity in units:
            figure = entity.get("largest_settlement_population")
            town = entity.get("largest_settlement")
            people = published(figure)
            unit = published(entity.get("population"))
            if people is None or unit is None or people <= unit:
                continue
            if (figure.get("source") == GEONAMES_FIGURE and isinstance(town, str)
                    and not town_stands(town, people, unit, entity, apart_from)):
                entity["largest_settlement"] = gap(
                    NOT_AVAILABLE,
                    drawn_elsewhere_note(town, people, unit)
                    if people <= GEONAMES_SPANS * unit else
                    beyond_unit_note(town, people, unit))
                entity["sources"] = [
                    src for src in entity.get("sources", [])
                    if not (src.get("name") == GEONAMES_SOURCE["name"]
                            and src.get("field") == GEONAMES_SOURCE["field"])]
                unnamed += 1
            else:
                unfigured += 1
            del entity["largest_settlement_population"]
    return unnamed, unfigured


# A Natural Earth figure this much larger than GeoNames' for the same place is
# said to be the urban area's.
URBAN_AREA_MARGIN = 1.1


def note_urban_area_figures(admin1: dict[str, list[dict[str, Any]]]) -> int:
    """Say where a first-level unit's settlement figure is Natural Earth's urban area.

    Natural Earth's figure for a populated place is the largest it has, which
    for a city is its urban area: Haifa District showed Haifa with 1,011,000
    people, the city's urban area, while the Haifa sub-district beside it
    showed GeoNames' 285,316 for the same city. The figure stays -- it is
    Natural Earth's for every first-level unit, and an urban area is a fair
    reading of a settlement -- and where GeoNames gives the same place a
    figure smaller by more than URBAN_AREA_MARGIN, the note says which is
    which. Run after settle_settlement_figures, so only a figure that is
    still shown is described.
    """
    towns = read_json(GEONAMES_SETTLEMENTS, {}) or {}
    noted = 0
    for rows in admin1.values():
        for entity in rows:
            figure = entity.get("largest_settlement_population")
            town = entity.get("largest_settlement")
            if (not isinstance(figure, dict) or not isinstance(town, str)
                    or not str(figure.get("source") or "").startswith("Natural Earth")
                    or entity.get("largest_settlement_note")):
                continue
            place = towns.get(entity["id"]) or {}
            people = place.get("population")
            if (not people or norm(place.get("name")) != norm(town)
                    or figure["value"] <= URBAN_AREA_MARGIN * people):
                continue
            entity["largest_settlement_note"] = (
                f"Natural Earth's figure, for the urban area {town} stands for, which "
                f"can reach past the city's own limits; GeoNames gives {town} "
                f"{people:,} people.")
            noted += 1
    return noted


# How far outside a first-level polygon, in degrees, Natural Earth's point for
# the place it files under that unit may lie inside another unit's polygon
# before the place is taken to be the other unit's. CGAZ's outlines are
# simplified, and a city on a border river can land across it: Neuquén's
# point is 0.11 degrees from the province's polygon, inside Río Negro's.
NATURAL_EARTH_APART = 0.2

# Natural Earth places filed under a first-level unit they are not in, where
# the point cannot say so: each lands inside the unit it belongs to, but
# within NATURAL_EARTH_APART of the unit it is filed under, as Neuquén and
# Mobaye (on the Ubangi, its point across the river in Congo) land just
# outside their own. (country, unit, place) -> the unit the place is in.
NATURAL_EARTH_MISFILED: dict[tuple[str, str, str], str] = {
    ("ALB", "Durrës", "Tirana"): "Tiranë",
    ("BDI", "Muramvya", "Gitega"): "Gitega",
    ("BEN", "Oueme", "Cotonou"): "Littoral",
    ("MDA", "Bender", "Tiraspol"): "Transnistria",
    ("SEN", "Matam", "Kaédi"): "Gorgol, Mauritania",
    ("TCD", "Mandoul", "Sarh"): "Moyen-Chari",
    ("TWN", "Chiayi", "Puzi"): "Chiayi County",
    ("TWN", "Hsinchu", "Zhubei"): "Hsinchu County",
}

# The words that make a unit's name the metropolitan government of a place,
# and the French elided article: "Municipalidad Metropolitana de Lima" is
# Lima's own unit, and "District Autonome D'Abidjan" Abidjan's. Read only to
# ask whether a polygon a place's point stands in is drawn for the place; a
# join still takes "Area Metropolitana de Lisboa" for a different place from
# Lisbon (see QUALIFIERS).
METROPOLITAN = frozenset({"metropolitan", "metropolitana", "metropolitaine"})
ELIDED = re.compile(r"\b([DdLl])['’]")


def drawn_for(place: str, unit: str) -> bool:
    """Whether a unit's name is a place's own, as a unit drawn for it."""
    if related(name_forms(place), name_forms(unit)):
        return True
    words = tuple(w for w in tokens(ELIDED.sub(r"\1 ", unit)) if w not in METROPOLITAN)
    return related(name_forms(place), (words,))


def natural_earth_elsewhere(city: dict[str, Any], shape: dict[str, Any],
                            others) -> str | None:
    """Why Natural Earth's place for a first-level unit is another unit's, or None.

    Natural Earth files its populated places under a first-level unit by that
    unit's name (ADM1NAME), not by where the place stands, and the build
    joined them by that name alone. Daegu came out with Pohang, a city of
    North Gyeongsang 60 km away, and Gwangju with Yeosu in South Jeolla;
    Thái Nguyên with Hanoi; the piece of Golestan the boundary file labels
    Mazandaran with Sari, inside the other Mazandaran polygon. A place is
    another unit's when its point is inside another first-level polygon and
    either that polygon is drawn for the place itself (Minsk's region and
    Minsk City, Selangor and Kuala Lumpur, Hadjer-Lamis and N'Djamena) or it
    lies more than NATURAL_EARTH_APART from this unit's. A point in no
    polygon -- Fortaleza, São Luís, Suva, a few hundred metres off a
    simplified coast -- is left to the name. So is one just across a border
    from the unit it is filed under, unless NATURAL_EARTH_MISFILED says
    which unit it is in: Tirana, filed under Durrës, is 0.11 degrees inside
    Tiranë, as close as Neuquén is to its own province.

    ``others`` answers which first-level shapes hold a point (an STRtree query
    over every first-level shape, with the shapes in the same order).
    """
    import shapely
    from shapely.geometry import Point

    misfiled = NATURAL_EARTH_MISFILED.get((shape.get("group"), shape.get("name"),
                                           city.get("name")))
    if misfiled:
        return f"a place of {misfiled}"
    geom = shape.get("_geom")
    point = city.get("coordinates")
    if geom is None or not point:
        return None
    point = Point(point)
    if shapely.contains(geom, point):
        return None
    tree, rows = others
    for idx in tree.query(point):
        other = rows[int(idx)]
        if other is shape or not shapely.contains(other["_geom"], point):
            continue
        if drawn_for(city["name"], other["name"]):
            return f"drawn as a unit of its own, {other['name']}"
        if shapely.distance(geom, point) > NATURAL_EARTH_APART:
            return f"inside {other['name']}"
        return None
    return None


def refuse_settlement_figures(admin1: dict[str, list[dict[str, Any]]],
                              admin2: dict[str, list[dict[str, Any]]],
                              classes: dict[str, list[list[str]]]) -> int:
    """Take a Wikidata population off a unit whose item is only a settlement."""
    refused = 0
    for iso3, rows in admin2.items():
        parents = {e["id"]: e for e in admin1.get(iso3, [])}
        siblings: dict[Any, int] = defaultdict(int)
        for entity in rows:
            siblings[entity.get("parent")] += 1
        for entity in rows:
            pop = entity.get("population")
            if not (isinstance(pop, dict) and pop.get("value")
                    and str(pop.get("source") or "").startswith("Wikidata")):
                continue
            kinds = classes.get(entity.get("wikidata") or "")
            if not kinds or not all(k in SETTLEMENT_CLASSES for k, _ in kinds):
                continue
            if CITY_SHAPE.search(entity.get("name") or "") \
                    or entity.get("wikidata") in SETTLEMENT_IS_THE_UNIT:
                continue
            parent = parents.get(entity.get("parent"))
            above = published(parent.get("population")) if parent else None
            if (above and siblings[entity.get("parent")] == 1
                    and SOLE_CHILD_BAND[0] <= pop["value"] / above <= SOLE_CHILD_BAND[1]):
                continue
            # Each class once, the closest: Damietta's item is a "big city"
            # and a "city", Belmopan's a "city" and a "human settlement", and
            # the note named both.
            named = {SETTLEMENT_CLASSES[k] for k, _ in kinds}
            narrow = {n for n in named
                      if n not in ("human settlement", "city or town", "locality")} or named
            labels = sorted(n for n in narrow
                            if not any(o != n and (o.endswith(" " + n) or o.startswith(n + " "))
                                       for o in narrow))
            what = (labels[0] if len(labels) == 1
                    else ", ".join(labels[:-1]) + " and " + labels[-1])
            article = "an" if what[0] in "aeiou" else "a"
            entity["population"] = gap(NOT_AVAILABLE, (
                f"Wikidata's item of this name, {entity['wikidata']}, is "
                f"{article} {what}, and Wikidata calls it nothing else -- no "
                f"municipality or district; its "
                f"{pop['value']:,}"
                + (f" ({pop['year']})" if pop.get("year") else "")
                + " are the settlement's people rather than this unit's, so the "
                  "figure is left out."))
            fall_back(entity, entity["population"],
                      usable=lambda held, item=entity.get("wikidata"):
                      a_unit(held, item, classes))
            refused += 1
    return refused


def a_unit(held: dict[str, Any], refused: str | None,
           classes: dict[str, list[list[str]]]) -> bool:
    """Whether a held figure is a unit's rather than another settlement's.

    An item a country lists as its first-level division is a unit by
    construction: that is what the first-level sweep asks Wikidata for. It
    reaches a district only where the map draws the first level second --
    Slovenia's municipality of Bovec behind the town of Bovec.
    """
    if held.get("wikidata") == refused:
        return False
    if held.get("file") == "wikidata_admin1.json":
        return True
    kinds = classes.get(held.get("wikidata") or "")
    if kinds:
        return not all(k in SETTLEMENT_CLASSES for k, _ in kinds)
    return not str(held["value"].get("source") or "").startswith("Wikidata")


def settle_outline_mixtures(admin2: dict[str, list[dict[str, Any]]]) -> int:
    """No figures on a polygon measured to be part of one unit and part of another.

    Named for what it holds, it can still take a row by name -- "Endola and
    part of Omulonga" starts with Endola -- and that row describes other
    ground. The polygon keeps the gap and says why, the way a lake does.
    """
    settled = 0
    for rows in admin2.values():
        for entity in rows:
            # The measurement has done its work once the joins are made; the
            # record keeps only what it says to a reader.
            outline = entity.pop("outline", None) or {}
            if outline.get("kind") != "mixed":
                continue
            # Named by the dataset, not by the reference's own title, which ends
            # with the archive it is downloaded as ("nam_admin_boundaries.shp.zip").
            named = {"NAM": "OCHA's administrative boundaries for Namibia (cod-ab-nam)"}
            note = outline_note(outline, named.get(entity.get("country"), "OCHA's outlines"))
            entity["note"] = note
            entity.pop("adapter_hint", None)
            for field in UNIT_FIELDS:
                entity[field] = gap(NOT_AVAILABLE, note)
            settled += 1
    return settled


# A figure from before any census could have counted the unit on the map is
# history, not population. Iraq's district of Al-Mada'in was joined by name to
# the item for the ancient city, and read 500,000 people in the year 622.
# Measured on 24 September 2026, it is the only Wikidata figure at either
# level dated before 1900.
OLDEST_FIGURE = 1900


def refuse_historic_figures(admin2: dict[str, list[dict[str, Any]]]) -> int:
    """Take off a Wikidata population dated before any modern count."""
    refused = 0
    for rows in admin2.values():
        for entity in rows:
            pop = entity.get("population")
            year = vintage(pop)
            if not (year and year < OLDEST_FIGURE and pop.get("value")
                    and str(pop.get("source") or "").startswith("Wikidata")):
                continue
            entity["population"] = gap(NOT_AVAILABLE, (
                f"Wikidata gives {pop['value']:,} for the year {year} for a place of "
                f"this name: a historical place, not the unit on the map, so its figure "
                f"is left out."))
            fall_back(entity, entity["population"])
            refused += 1
    return refused


# The same mistake one level up, where it also blinds the check above. Wikidata's
# items for Portugal's districts carry their capitals' 2018 figures -- Portalegre
# District 22,359, the municipality of Portalegre's -- so every district read as
# a town, and against Aveiro's 77,916 the check above refused Santa Maria da
# Feira's 136,674 as a town's. A parent's figure is taken for its capital's when
# both hold:
#   * it is within a quarter of the figure of its division named for it or for
#     its capital (years apart, not units apart);
#   * its other divisions alone hold more people than it does.
# Only a Wikidata figure is judged: a census or an official table is not
# overruled by a sum that is mostly Wikidata's. Measured on 24 September 2026
# over every parent with a namesake division: 14 fail -- twelve Portuguese
# districts, Cuba's Sancti Spiritus (150,000, the city's) and Angola's Moxico
# (574,253, the province cut down in 2024, on the old province's ground).
# Run first, so the check above measures against a parent's own figure.
CAPITAL_BAND = (0.75, 1.33)
# When the capital's own division has no figure to compare -- Setubal's is
# spelt "Setubul" and joins an item with none, Faro's item has none -- the
# divisions' sum must do it alone, and so must clear a wider margin. Over every
# first-level Wikidata figure with five divisions or more, only Faro (6.4) and
# Setubal (4.5) exceed three times; below that sit parents that are right and
# divisions that are not (Namibia's Hardap, 2.8, whose constituencies are
# attached to the wrong regions) and Thai provinces counted two ways.
CAPITAL_FALLBACK_RATIO = 3.0
CAPITAL_FALLBACK_DIVISIONS = 5


def refuse_capital_figures(admin1: dict[str, list[dict[str, Any]]],
                           admin2: dict[str, list[dict[str, Any]]]) -> int:
    """Take a Wikidata population off a parent when it is its capital's."""
    refused = 0
    for iso3, parents in admin1.items():
        kids: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for entity in admin2.get(iso3, []):
            kids[entity.get("parent")].append(entity)
        for parent in parents:
            pop = parent.get("population")
            if not (isinstance(pop, dict) and pop.get("value")
                    and str(pop.get("source") or "").startswith("Wikidata")):
                continue
            children = kids.get(parent["id"], [])
            names = {norm(parent.get("name"))}
            if isinstance(parent.get("capital"), str):
                names.add(norm(parent["capital"]))
            names.discard("")
            town = next((c for c in children if norm(c.get("name")) in names
                         and published(c.get("population"))), None)
            figures = [published(c.get("population")) for c in children
                       if published(c.get("population"))]
            if town is not None:
                held = published(town["population"])
                rest = sum(figures) - held
                if not (CAPITAL_BAND[0] <= pop["value"] / held <= CAPITAL_BAND[1]
                        and rest > pop["value"]):
                    continue
                why = (f"close to the {held:,.0f} of {town['name']}, one of its "
                       f"divisions, while its other divisions hold {rest:,.0f} "
                       f"between them")
            elif (len(figures) >= CAPITAL_FALLBACK_DIVISIONS
                  and sum(figures) > CAPITAL_FALLBACK_RATIO * pop["value"]):
                why = (f"while {len(figures)} of its divisions hold "
                       f"{sum(figures):,.0f} between them")
            else:
                continue
            # Worded as the other refusals of a figure joined by name are: the
            # item is the place Wikidata calls by this name, and saying the
            # figure is "for this unit" and then probably not this unit's
            # contradicted itself (Angola's Moxico).
            parent["population"] = gap(NOT_AVAILABLE, (
                f"Wikidata gives {pop['value']:,}"
                + (f" ({pop['year']})" if pop.get("year") else "")
                + f" for a place of this name, {why}. It is probably the figure of the "
                  f"town or of a smaller unit, so it is left out."))
            fall_back(parent, parent["population"])
            refused += 1
    return refused


def check_water_shapes(admin1: dict[str, list[dict[str, Any]]],
                       admin2: dict[str, list[dict[str, Any]]]) -> None:
    """Every declared lake is drawn, nothing has landed on it, and it is water.

    A declaration that names no shape is stale, and a lake that ends up with
    a population or a composition means a row was joined to water -- a
    mis-match, which is worse than the gap it replaced. Either stops the build.

    A gap that landed is a different thing: an adapter agreeing that nothing
    is here. Indonesia's writes "not collected" on its lakes and reservoirs,
    with UN OCHA's list of uninhabited features as the reason, and the
    declaration settles those back to water. Its citation stays on the
    record, since it says the same thing.
    """
    problems: list[str] = []
    for iso3, declared in WATER_SHAPES.items():
        found = {name: [] for name in declared}
        for table in (admin1, admin2):
            for entity in table.get(iso3, []):
                if entity.get("name") in found:
                    found[entity["name"]].append(entity)
        for name, shapes in found.items():
            if len(shapes) != 1:
                problems.append(
                    f"{iso3} / {name}: declared as water, and {len(shapes)} "
                    f"shapes carry that name -- it should be exactly one")
                continue
            landed = [f for f in UNIT_FIELDS
                      if field_state(shapes[0].get(f))
                      not in (NOT_APPLICABLE, NOT_AVAILABLE, NOT_COLLECTED)]
            if landed:
                problems.append(
                    f"{iso3} / {name}: declared as water, but {', '.join(landed)} "
                    f"ended up with a figure -- a row was joined to a lake")
                continue
            mark_water(shapes[0], iso3)
    if problems:
        raise SystemExit("water shapes:\n  " + "\n  ".join(problems))


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
#
# A part may be a tuple of spellings, one per source that names it differently.
# Greece is the case that needs it. The map draws the seven decentralized
# administrations of 2011, and every source publishes the thirteen regions
# inside them: Wikidata in English ("Thessaly Region") and Eurostat in
# transliterated Greek ("Thessalia"). Left unpooled, a region's row is not a
# gap -- it is a wrong answer. "Thessalia" prefix-matched "Thessalia-Central
# Greece" and put Thessaly's 676,040 people and median age on a shape that
# also holds Central Greece; Wikidata's "Eastern Macedonia and Thrace" matched
# "Macedonia-Thrace" and gave it 562,201 people and Komotini for a capital,
# where the administration also holds Central Macedonia's 1.8 million.
SHAPE_IS_UNION_OF: dict[tuple[str, str], tuple[str | tuple[str, ...], ...]] = {
    ("NAM", "Kavango"): ("Kavango East", "Kavango West"),
    # Eurostat counts Trentino-Alto Adige as its two autonomous provinces.
    ("ITA", "Trentino-Alto Adige"): ("Provincia Autonoma di Bolzano/Bozen",
                                     "Provincia Autonoma di Trento"),
    ("GRD", "Southern Grenadine Islands"): ("Carriacou Island", "Petite Martinique"),
    ("GRC", "Macedonia-Thrace"): (("Central Macedonia", "Kentriki Makedonia"),
                                  ("Eastern Macedonia and Thrace",
                                   "Anatoliki Makedonia, Thraki")),
    ("GRC", "Thessalia-Central Greece"): (("Thessaly", "Thessalia"),
                                          ("Central Greece", "Sterea Elláda")),
    ("GRC", "Egean"): (("North Aegean", "Voreio Aigaio"),
                       ("South Aegean", "Notio Aigaio")),
    ("GRC", "Epirus-Western Macedonia"): (("Epirus", "Ipeiros"),
                                          ("Western Macedonia", "Dytiki Makedonia")),
    ("GRC", "Peloponisos-W. Greece & Ionian"): (("Peloponnese", "Peloponnisos"),
                                                ("West Greece", "Dytiki Elláda"),
                                                ("Ionian Islands", "Ionia Nisia")),
}


def spellings(part: str | tuple[str, ...]) -> tuple[str, ...]:
    return (part,) if isinstance(part, str) else part

# A source row that covers ground the boundary file has since divided. Bueng
# Kan was carved from Nong Khai in 2011; the 2000 census row for Nong Khai
# counted both. The new unit is given a gap saying so for each field the row
# carries, and the row's own shape keeps the published row untouched. It was
# once given the old row's shares as an estimate, which is a region's figure
# copied onto a part of it: it assumes the old unit was uniform inside, which
# docs/MODELLING.md measures to be false in about 45% of countries.
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


def shared_sentences(notes: Sequence[Any]) -> str:
    """The whole sentences every part's note opens with, to keep on the pool.

    A survey's caveat -- "Regional shares are survey estimates, not census
    counts ..." -- is true of the pool too, and was being dropped with the
    parts' notes; the sentence that differs ("This region: 112 respondents")
    describes one part and is left out.
    """
    if not notes or not all(isinstance(n, str) and n for n in notes):
        return ""
    prefix = os.path.commonprefix(list(notes))
    cut = prefix.rfind(". ")
    if len(set(notes)) == 1:
        return notes[0].rstrip() + " "
    return prefix[:cut + 2] if cut > 0 else ""


RATIO_UNIT_WORDS = re.compile(r"^(males|females)_per_(\d+)_(males|females)$")


def pool_sex_ratio(pooled: dict[str, Any], parts: Sequence[dict[str, Any]],
                   pops: Sequence[float | None], names: str) -> None:
    """The parts' sex ratio pooled, from each part's population and ratio.

    A ratio of males to females and the population give each part's men and
    women, and the pooled ratio is theirs summed -- exact, as a weighted mean
    of the ratios is not. Where the parts carry ratios but the file gives no
    populations to weigh them by, the field says so rather than staying
    silent: a part's own ratio would describe less than the polygon.
    """
    ratios = [p.get("sex_ratio") for p in parts]
    if not all(published(r) is not None for r in ratios):
        return
    units = {r.get("unit") for r in ratios}
    found = RATIO_UNIT_WORDS.match(str(next(iter(units)))) if len(units) == 1 else None
    if found is None or any(v is None for v in pops):
        pooled["sex_ratio"] = gap(NOT_AVAILABLE, (
            f"Published for {names} separately, with no populations from the same "
            f"source to weigh them by, so they are not combined for this polygon, "
            f"which draws them as one unit."))
        return
    per = float(found.group(2))
    over = under = 0.0
    for people, ratio in zip(pops, (float(published(r)) for r in ratios)):
        over += people * ratio / (per + ratio)
        under += people * per / (per + ratio)
    value = dict(ratios[0])
    value.pop("note", None)
    value["value"] = round(over / under * per, 1 if per <= 100 else 0)
    if per > 100:
        value["value"] = int(value["value"])
    if len({vintage(r) for r in ratios}) != 1:
        value.pop("year", None)
    pooled["sex_ratio"] = value
    pooled["sex_ratio_note"] = (
        shared_sentences([p.get("sex_ratio_note") for p in parts])
        + f"Pooled from the populations and ratios published for {names}; the map "
        f"draws them as one unit.")


def pooled_age_groups(parts: Sequence[dict[str, Any]]
                      ) -> list[tuple[int, int | None, float]] | None:
    """The parts' age groups added together, where every part gives the same
    groups (``age_groups``: [low, high, people], the last open); else None."""
    tables = [p.get("age_groups") for p in parts]
    if not all(isinstance(t, list) and t for t in tables):
        return None
    bands = [(low, high) for low, high, _ in tables[0]]
    if any([(low, high) for low, high, _ in t] != bands for t in tables[1:]):
        return None
    return [(low, high, sum(t[i][2] for t in tables)) for i, (low, high) in enumerate(bands)]


def grouped_median(groups: Sequence[tuple[int, int | None, float]]) -> float | None:
    """The median of ``(low, high, people)`` groups, interpolated within the
    group that holds the middle person; None where that group is the open one.
    As scripts/fetch_census/cod_ps_age.py takes each unit's."""
    base = sum(n for _, _, n in groups)
    if base <= 0:
        return None
    half, before = base / 2, 0.0
    for low, high, people in groups:
        if before + people >= half:
            if high is None or people <= 0:
                return None
            return round(low + (half - before) / people * (high - low + 1), 1)
        before += people
    return None


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
    listed = [p["name"] for p in parts]
    # Two parts of one name are told apart by the province each is in:
    # Paraguay's Bella Vista in Amambay and Bella Vista in Itapúa.
    if len(set(listed)) < len(listed):
        listed = [f"{p['name']} ({p['parent_name']})" if p.get("parent_name") else p["name"]
                  for p in parts]
    names = ", ".join(listed[:-1]) + " and " + listed[-1] if len(listed) > 1 else listed[0]
    pops = [published(p.get("population")) for p in parts]
    if all(v is not None for v in pops):
        first = dict(parts[0]["population"])
        first["value"] = int(round(sum(v for v in pops if v is not None)))
        first.pop("note", None)
        years = {vintage(p.get("population")) for p in parts}
        if len(years) != 1:
            first.pop("year", None)
        # A sum says it is one: no row this source published has this figure.
        # Said in population_note, beside the figure; the note inside the
        # first part's figure is about that part alone, so it is dropped.
        pooled["population"] = first
        pooled["population_note"] = (
            shared_sentences([p.get("population_note") for p in parts])
            + f"The sum of the figures published for {names}; the map draws them "
            f"as one unit.")
    pool_sex_ratio(pooled, parts, pops, names)
    if all(published(p.get("median_age")) is not None for p in parts):
        # A median of two places together is not a mix of their medians, but
        # it is the median of their age groups added together, where the
        # source gives them: OCHA's five-year groups for Mexico's municipios.
        groups = pooled_age_groups(parts)
        together = {2: "the two", 3: "the three", 4: "the four"}.get(len(parts), "them all")
        median = grouped_median(groups) if groups else None
        if median is not None:
            first = parts[0]["median_age"]
            years = {vintage(p.get("median_age")) for p in parts}
            pooled["median_age"] = {**{k: first[k] for k in ("unit", "source") if k in first},
                                    "value": median,
                                    **({"year": years.pop()} if len(years) == 1 else {})}
            pooled["median_age_note"] = (
                shared_sentences([p.get("median_age_note") for p in parts])
                + f"Taken from the age groups published for {names}, added together; "
                f"the map draws them as one unit.")
        else:
            # Siltepec's polygon holds three municipios.
            pooled["median_age"] = gap(NOT_AVAILABLE, (
                f"Published for {names} separately: the median of {together} together "
                f"cannot be taken from their medians, and the map draws them as one "
                f"unit."))
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
            # Said on the record too: a gap that only says no source carries
            # the field is false here, since one carries it for every part.
            # Weighing the parts by another file's populations would put one
            # source's shares on another source's people, often of another
            # year, so they are not combined.
            pooled[field] = gap(NOT_AVAILABLE, (
                f"Shares are published for {names} separately, with no counts "
                f"or populations from the same source to weigh them by, so they "
                f"are not combined for this polygon, which draws them as one "
                f"unit."))
            continue
        pooled[field] = rows
        pooled[f"{field}_note"] = (
            shared_sentences([p.get(f"{field}_note") for p in parts])
            + f"Pooled from the figures published for {names}, weighted by {basis}; "
            f"the map draws them as one unit.")
        for satellite in ("year", "basis"):
            values = {p.get(f"{field}_{satellite}") for p in parts}
            if len(values) == 1 and None not in values:
                pooled[f"{field}_{satellite}"] = values.pop()
    return pooled


def outline_unions(adm2: list[dict[str, Any]]
                   ) -> dict[tuple[str, str], tuple[str, ...]]:
    """The unions relabel_from_outlines measured, in SHAPE_IS_UNION_OF's form."""
    return {(r["group"], r["name"]): tuple(r["outline"]["parts"])
            for r in adm2 if (r.get("outline") or {}).get("kind") == "union"}


def pool_declared_unions(adapters: dict[str, list[dict[str, Any]]],
                         unions: dict[tuple[str, str], tuple[Any, ...]] | None = None
                         ) -> list[str]:
    """Replace each declared union's parts with one row named for the shape."""
    done: list[str] = []
    for (iso3, shape_name), parts in (SHAPE_IS_UNION_OF if unions is None
                                      else unions).items():
        rows = adapters.get(iso3, [])
        # Each part is known by its first spelling.
        part_names = tuple(spellings(p)[0] for p in parts)
        # Matched the way the shapes are: Afrobarometer writes "Kavango East"
        # and Wikidata "Kavango East Region", and norm() reads those alike.
        wanted = {norm(s): spellings(p)[0] for p in parts for s in spellings(p)}
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


# Unions of named rows of one file, pooled onto the polygon given by its id.
# SHAPE_IS_UNION_OF names its parts, and that cannot reach these: norm() reads
# "Zomba City" and "Zomba District", "Maputo City" and "Maputo Province", as
# one name, and Paraguay's two districts are both "Bella Vista". So each part
# is the row's id, and the pooled row is bound to the polygon by its id and
# carries the polygon's label. Each entry was measured before it was listed:
#   MWI  OCHA's 2023 table counts each of Malawi's four cities apart from the
#        district around it. The boundary file draws no city: Zomba, Lilongwe,
#        Mzuzu and Blantyre each lie inside the district polygon of their
#        name (Mzuzu inside Mzimba's), and every other district of the table
#        is a polygon of its own, so district and city together are each
#        polygon's ground. Unpooled, Zomba's two rows met on one key and
#        neither was kept, and Lilongwe, Mzimba and Blantyre carried their
#        city's or their district's figure alone.
#   ETH  Dire Dawa's urban and rural rows (OCHA 2022) are the city
#        administration, which the boundary file draws once at each level.
#   MOZ  The boundary file draws Maputo City and Maputo Province as one
#        polygon; Afrobarometer's ninth round surveys each, and its counts of
#        respondents are summed.
#   STP  Afrobarometer's ninth round divides São Tomé island into three
#        strata, Norte Oeste, Centro Este and Sul Este, which together are the
#        island and so the province; Príncipe is its fourth.
#   PRY  The polygon is Bella Vista (Amambay) and Bella Vista (Itapúa) drawn
#        as one, as both were before Cerro Corá was cut from the first in
#        2020; OCHA's 2023 table has both districts and no Cerro Corá. The
#        2022 census counts the districts as they are now, so it has no figure
#        for this ground (paraguay_census says so on the polygon), and OCHA's
#        rows are kept for this union although the census supersedes the rest.
#   MEX  Twelve polygons are drawn as the municipio was before a newer one was
#        made out of it: the census of 2020 and OCHA's table for 2024 count
#        the two apart, and the newer has no polygon. Each part's seat lies
#        inside the old polygon (GeoNames' seats, and for Mezcalapa, Hueyapan,
#        Puerto Morelos and San Felipe their towns; Seybaplaya's and Puerto
#        Morelos' lie on the coast just outside the generalised line, nearest
#        it); Emiliano Zapata, made a municipio in 2011 (Spanish Wikipedia),
#        has its seat at 16.538N 92.897W in Acala's polygon. The census's
#        populations, sex ratios and compositions are pooled from its counts;
#        a median age is not, and the field says why. San Felipe was made out
#        of Mexicali after the 2020 census, which counted it in Mexicali, so
#        only OCHA's rows are pooled there. Tecpatán alone drew 22,580 people
#        of 47,348.
#        An entry with "parts" pools each file's rows for the same places.
ROW_UNIONS: dict[tuple[str, str], dict[str, Any]] = {
    ("MWI", "Zomba"): {
        "file": "cod_ps_admin2.json",
        "rows": ("MWI-CODPS-MW314", "MWI-CODPS-MW303"),
        "shapes": (("admin2", "42251766B13881881574545"),),
        "note": "The city has no polygon of its own and lies inside this one."},
    ("MWI", "Lilongwe"): {
        "file": "cod_ps_admin2.json",
        "rows": ("MWI-CODPS-MW210", "MWI-CODPS-MW206"),
        "shapes": (("admin2", "42251766B26147222520266"),),
        "note": "The city has no polygon of its own and lies inside this one."},
    ("MWI", "Mzimba"): {
        "file": "cod_ps_admin2.json",
        "rows": ("MWI-CODPS-MW105", "MWI-CODPS-MW107"),
        "shapes": (("admin2", "42251766B77624810989827"),),
        "note": "Mzuzu has no polygon of its own and lies inside this one."},
    ("MWI", "Blantyre"): {
        "file": "cod_ps_admin2.json",
        "rows": ("MWI-CODPS-MW315", "MWI-CODPS-MW305"),
        "shapes": (("admin2", "42251766B636776762176"),),
        "note": "The city has no polygon of its own and lies inside this one."},
    ("ETH", "Dire Dawa"): {
        "file": "cod_ps_admin2.json",
        "rows": ("ETH-CODPS-ET1501", "ETH-CODPS-ET1502"),
        "shapes": (("admin1", "75662566B22109266514860"),
                   ("admin2", "57463737B22109266514860")),
        "note": "Together they are the Dire Dawa city administration."},
    ("MOZ", "Maputo"): {
        "file": "afrobarometer_region.json",
        "rows": ("MOZ-AB9-540", "MOZ-AB9-541"),
        "shapes": (("admin1", "27363107B47421408423272"),)},
    ("STP", "São Tomé Province"): {
        "file": "afrobarometer_region.json",
        "rows": ("STP-AB9-1660", "STP-AB9-1661", "STP-AB9-1662"),
        "shapes": (("admin1", "19237168B40253326356618"),),
        "note": "The three are the survey's divisions of São Tomé island."},
    ("PRY", "Bella Vista"): {
        "file": "cod_ps_admin2.json",
        "rows": ("PRY-CODPS-PY1302", "PRY-CODPS-PY0702"),
        "shapes": (("admin2", "47425931B90614418626785"),),
        "note": ("Both are the districts as they were before Cerro Corá was "
                 "created in 2020, which is how the boundary file draws them; "
                 "the figures are projections for 2023.")},
    ("MEX", "Ensenada"): {
        "parts": {
            "mexico_municipality.json": ("MEX-02001", "MEX-02006"),
            "mexico_municipality_age.json": ("MEX-02001", "MEX-02006"),
            "mexico_ethnicity.json": ("MEX-02001", "MEX-02006"),
            "cod_ps_admin2.json": ("MEX-CODPS-MX02001", "MEX-CODPS-MX02006"),
            "cod_ps_age.json": ("MEX-CODPSAGE-MX02001", "MEX-CODPSAGE-MX02006"),
        },
        "shapes": (("admin2", "50627088B13797450449328"),),
        "note": "San Quintín has no outline of its own and lies inside this one."},
    ("MEX", "Mexicali"): {
        "parts": {
            "cod_ps_admin2.json": ("MEX-CODPS-MX02002", "MEX-CODPS-MX02007"),
            "cod_ps_age.json": ("MEX-CODPSAGE-MX02002", "MEX-CODPSAGE-MX02007"),
        },
        "shapes": (("admin2", "50627088B84599572497035"),),
        "note": ("San Felipe has no outline of its own and lies inside this one; the 2020 "
                 "census, taken before it was made a municipio, counted it in Mexicali.")},
    ("MEX", "Champotón"): {
        "parts": {
            "mexico_municipality.json": ("MEX-04004", "MEX-04012"),
            "mexico_municipality_age.json": ("MEX-04004", "MEX-04012"),
            "mexico_ethnicity.json": ("MEX-04004", "MEX-04012"),
            "cod_ps_admin2.json": ("MEX-CODPS-MX04004", "MEX-CODPS-MX04012"),
            "cod_ps_age.json": ("MEX-CODPSAGE-MX04004", "MEX-CODPSAGE-MX04012"),
        },
        "shapes": (("admin2", "50627088B90852523965903"),),
        "note": "Seybaplaya has no outline of its own and lies inside this one."},
    ("MEX", "Acala"): {
        "parts": {
            "mexico_municipality.json": ("MEX-07002", "MEX-07123"),
            "mexico_municipality_age.json": ("MEX-07002", "MEX-07123"),
            "mexico_ethnicity.json": ("MEX-07002", "MEX-07123"),
            "cod_ps_admin2.json": ("MEX-CODPS-MX07002", "MEX-CODPS-MX07123"),
            "cod_ps_age.json": ("MEX-CODPSAGE-MX07002", "MEX-CODPSAGE-MX07123"),
        },
        "shapes": (("admin2", "50627088B13121801882345"),),
        "note": "Emiliano Zapata has no outline of its own and lies inside this one."},
    ("MEX", "Pueblo Nuevo Solistahuacán"): {
        "parts": {
            "mexico_municipality.json": ("MEX-07072", "MEX-07121"),
            "mexico_municipality_age.json": ("MEX-07072", "MEX-07121"),
            "mexico_ethnicity.json": ("MEX-07072", "MEX-07121"),
            "cod_ps_admin2.json": ("MEX-CODPS-MX07072", "MEX-CODPS-MX07121"),
            "cod_ps_age.json": ("MEX-CODPSAGE-MX07072", "MEX-CODPSAGE-MX07121"),
        },
        "shapes": (("admin2", "50627088B52747419907097"),),
        "note": ("Rincón Chamula San Pedro has no outline of its own and lies inside this "
                 "one.")},
    ("MEX", "Siltepec"): {
        "parts": {
            "mexico_municipality.json": ("MEX-07080", "MEX-07120", "MEX-07125"),
            "mexico_municipality_age.json": ("MEX-07080", "MEX-07120", "MEX-07125"),
            "mexico_ethnicity.json": ("MEX-07080", "MEX-07120", "MEX-07125"),
            "cod_ps_admin2.json": ("MEX-CODPS-MX07080", "MEX-CODPS-MX07120", "MEX-CODPS-MX07125"),
            "cod_ps_age.json": ("MEX-CODPSAGE-MX07080", "MEX-CODPSAGE-MX07120", "MEX-CODPSAGE-MX07125"),
        },
        "shapes": (("admin2", "50627088B9123326628132"),),
        "note": ("Capitán Luis Ángel Vidal and Honduras de la Sierra have no outlines of "
                 "their own and lie inside this one.")},
    ("MEX", "Tecpatán"): {
        "parts": {
            "mexico_municipality.json": ("MEX-07092", "MEX-07124"),
            "mexico_municipality_age.json": ("MEX-07092", "MEX-07124"),
            "mexico_ethnicity.json": ("MEX-07092", "MEX-07124"),
            "cod_ps_admin2.json": ("MEX-CODPS-MX07092", "MEX-CODPS-MX07124"),
            "cod_ps_age.json": ("MEX-CODPSAGE-MX07092", "MEX-CODPSAGE-MX07124"),
        },
        "shapes": (("admin2", "50627088B96420175301119"),),
        "note": "Mezcalapa has no outline of its own and lies inside this one."},
    ("MEX", "Villa Corzo"): {
        "parts": {
            "mexico_municipality.json": ("MEX-07107", "MEX-07122"),
            "mexico_municipality_age.json": ("MEX-07107", "MEX-07122"),
            "mexico_ethnicity.json": ("MEX-07107", "MEX-07122"),
            "cod_ps_admin2.json": ("MEX-CODPS-MX07107", "MEX-CODPS-MX07122"),
            "cod_ps_age.json": ("MEX-CODPSAGE-MX07107", "MEX-CODPSAGE-MX07122"),
        },
        "shapes": (("admin2", "50627088B92605446489911"),),
        "note": "El Parral has no outline of its own and lies inside this one."},
    ("MEX", "Miacatlán"): {
        "parts": {
            "mexico_municipality.json": ("MEX-17015", "MEX-17034"),
            "mexico_municipality_age.json": ("MEX-17015", "MEX-17034"),
            "mexico_ethnicity.json": ("MEX-17015", "MEX-17034"),
            "cod_ps_admin2.json": ("MEX-CODPS-MX17015", "MEX-CODPS-MX17034"),
            "cod_ps_age.json": ("MEX-CODPSAGE-MX17015", "MEX-CODPSAGE-MX17034"),
        },
        "shapes": (("admin2", "50627088B93952904425300"),),
        "note": "Coatetelco has no outline of its own and lies inside this one."},
    ("MEX", "Puente de Ixtla"): {
        "parts": {
            "mexico_municipality.json": ("MEX-17017", "MEX-17035"),
            "mexico_municipality_age.json": ("MEX-17017", "MEX-17035"),
            "mexico_ethnicity.json": ("MEX-17017", "MEX-17035"),
            "cod_ps_admin2.json": ("MEX-CODPS-MX17017", "MEX-CODPS-MX17035"),
            "cod_ps_age.json": ("MEX-CODPSAGE-MX17017", "MEX-CODPSAGE-MX17035"),
        },
        "shapes": (("admin2", "50627088B15428140679131"),),
        "note": "Xoxocotla has no outline of its own and lies inside this one."},
    ("MEX", "Tetela del Volcán"): {
        "parts": {
            "mexico_municipality.json": ("MEX-17022", "MEX-17036"),
            "mexico_municipality_age.json": ("MEX-17022", "MEX-17036"),
            "mexico_ethnicity.json": ("MEX-17022", "MEX-17036"),
            "cod_ps_admin2.json": ("MEX-CODPS-MX17022", "MEX-CODPS-MX17036"),
            "cod_ps_age.json": ("MEX-CODPSAGE-MX17022", "MEX-CODPSAGE-MX17036"),
        },
        "shapes": (("admin2", "50627088B54865100778576"),),
        "note": "Hueyapan has no outline of its own and lies inside this one."},
    ("MEX", "Benito Juárez"): {
        "parts": {
            "mexico_municipality.json": ("MEX-23005", "MEX-23011"),
            "mexico_municipality_age.json": ("MEX-23005", "MEX-23011"),
            "mexico_ethnicity.json": ("MEX-23005", "MEX-23011"),
            "cod_ps_admin2.json": ("MEX-CODPS-MX23005", "MEX-CODPS-MX23011"),
            "cod_ps_age.json": ("MEX-CODPSAGE-MX23005", "MEX-CODPSAGE-MX23011"),
        },
        "shapes": (("admin2", "50627088B55174657645518"),),
        "note": "Puerto Morelos has no outline of its own and lies inside this one."},
}


def union_groups(spec: dict[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
    """A ROW_UNIONS entry's (file, row ids) groups: one file's rows, or each of
    several files' rows for the same parts (``parts``)."""
    if "parts" in spec:
        return [(filename, tuple(rows)) for filename, rows in spec["parts"].items()]
    return [(spec["file"], tuple(spec["rows"]))]


def union_row_ids(filename: str) -> set[str]:
    """Every row id a ROW_UNIONS entry pools from ``filename``."""
    return {rid for spec in ROW_UNIONS.values()
            for file, rows in union_groups(spec) if file == filename for rid in rows}


def pool_row_unions(adapters: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Replace each ROW_UNIONS entry's rows with one pooled row per polygon.

    Every named row must be there: a union missing a part would be one part's
    figure under the whole's label, so it is left unpooled and the log says
    which part is missing.
    """
    done: list[str] = []
    for (iso3, shape_name), spec in ROW_UNIONS.items():
        rows = adapters.get(iso3, [])
        for filename, wanted in union_groups(spec):
            found = {r.get("id"): r for r in rows
                     if r.get("_source") == filename and r.get("id") in wanted}
            missing = [rid for rid in wanted if rid not in found]
            if missing:
                log(f"  union {iso3} {shape_name}: {filename} lacks "
                    f"{', '.join(missing)}, not pooled")
                continue
            parts = [found[rid] for rid in wanted]
            pooled = pool_rows(shape_name, parts, iso3, filename)
            extra = spec.get("note")
            if extra:
                for key in ("population", "sex_ratio", *ROLLUP_FIELDS):
                    value = pooled.get(key)
                    if isinstance(value, dict) and value.get("note") and "value" in value:
                        value["note"] = f"{value['note']} {extra}"
                    elif pooled.get(f"{key}_note"):
                        pooled[f"{key}_note"] = f"{pooled[f'{key}_note']} {extra}"
            for part in parts:
                rows.remove(part)
            for level, shape_id in spec["shapes"]:
                rows.append({**copy.deepcopy(pooled), "level": level,
                             "id": f"{pooled['id']}-{level}", "match_by": "shape_id",
                             "shape_id": shape_id,
                             "aliases": [p["name"] for p in parts]})
            done.append(f"{iso3} {shape_name} from {' + '.join(wanted)} ({filename})")
    return done


def gaps_from(src: dict[str, Any], target: str, iso3: str) -> dict[str, Any] | None:
    """A row for ``target`` saying, for each composition ``src`` carries, that
    the figure is the old unit's and not this one's."""
    row: dict[str, Any] = {
        "id": f"{src.get('id') or norm(src['name'])}-SPLIT-{norm(target)}",
        "level": src.get("level") or "admin1", "name": target,
        "parent": src.get("parent") or iso3, "country": iso3,
        "_source": src["_source"], "sources": []}
    written = False
    for field in ROLLUP_FIELDS:
        shares = src.get(field)
        if not (isinstance(shares, list) and shares_of(shares)):
            continue
        if collection_gap(iso3, field) is not None:
            continue
        year = src.get(f"{field}_year")
        when = f" in {year}" if year else ""
        # Not "no source publishes it": Thailand's 2010 census did, for the
        # new province. What is true is that none read here does.
        row[field] = gap(NOT_AVAILABLE, (
            f"No {field} figure for {target} on its own has been read. The one "
            f"read for {src['name']}{when} counted this ground as part of it, and a "
            f"region's figure is not any one of its parts', so it is not repeated "
            f"here."))
        written = True
    return row if written else None


def split_declared_rows(adapters: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Add a row of stated gaps for each shape a declared source row covers."""
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
                made = gaps_from(src, target, iso3)
                if made is None:
                    log(f"  split {iso3} {row_name} -> {target}: {src['_source']} "
                        f"carries nothing to say")
                    continue
                rows.append(made)
                done.append(f"{iso3} {target} from {row_name} ({src['_source']}): "
                            + ", ".join(f for f in ROLLUP_FIELDS if f in made))
    return done


def inherit_single_unit(admin0: list[dict[str, Any]],
                        admin1_by_country: dict[str, list[dict[str, Any]]],
                        admin2_by_country: dict[str, list[dict[str, Any]]] | None = None
                        ) -> list[str]:
    """A country drawn as one first-level unit gives that unit its own row.

    The unit's ground is the country's, so the national figure describes it
    exactly. A share list is written as derived rather than as a reading,
    because nothing was read for the unit and a derived value never rolls
    back up into the country it came from. A median age, a sex ratio or a
    population is the same people's and is copied as it stands, with a
    sentence saying whose it is; so is a list of languages the Factbook names
    without shares, which no estimate can carry. Western Sahara and Vatican
    City were the two the share rule left blank: their country rows hold a
    median age, a sex ratio and a list of languages, and nothing else.

    The boundary file draws both again at the second level under the same
    id. fill_same_polygons ran before this and found the first level empty,
    so the twin takes the same figures here.
    """
    done: list[str] = []
    nations = {c["id"]: c for c in admin0}
    for iso3, rows in sorted(admin1_by_country.items()):
        if len(rows) != 1 or rows[0].get("disputed"):
            continue
        unit, nation = rows[0], nations.get(iso3)
        if nation is None:
            continue
        said = (f"{nation.get('name', iso3)} is drawn as a single first-level unit, "
                f"so this is the country's own figure: it describes exactly this "
                f"ground and no more.")
        written: list[str] = []
        for field in SOLE_FIELDS:
            current = unit.get(field)
            if not (isinstance(current, dict) and current.get("status") == NOT_AVAILABLE
                    and not current.get("not_this_ground")):
                continue
            value = nation.get(field)
            if isinstance(value, list) and shares_of(value):
                unit[field] = estimate(
                    DERIVED, value, method="tier0-single-unit", inputs=[iso3],
                    note=(f"{nation.get('name', iso3)} is drawn as a single first-level "
                          f"unit, so this is the country's own {field} figure: it "
                          f"describes exactly this ground and no more. Derived from the "
                          f"national row, not separately published for the unit."))
            elif (isinstance(value, list) and value and field in ROLLUP_FIELDS) \
                    or (field in FIGURE_FIELDS and published(value) is not None):
                # A list of names with no shares, or a median, a ratio or a
                # count: the same value, said to be the country's in the note
                # beside it, which is the one the panel shows.
                unit[field] = copy.deepcopy(value)
                for suffix in ("_year", "_basis"):
                    if nation.get(f"{field}{suffix}") is not None:
                        unit[f"{field}{suffix}"] = nation[f"{field}{suffix}"]
                # A list of names is no figure: it says which languages, not
                # how many speak them.
                unit[f"{field}_note"] = join_note(
                    nation.get(f"{field}_note"),
                    said.replace("own figure", "own list") if isinstance(value, list) else said)
            else:
                continue
            cite_country(unit, nation, field)
            written.append(field)
            done.append(f"{iso3} {unit['name']} {field}")
        # Where the country has no figure to hand down either, the unit says
        # why in the country's words. Once the unit cites the country's source
        # for what it did take, the generic sentence for an empty field would
        # name that source as lacking the field: Western Sahara's religion
        # read "the CIA World Factbook ... carries language and not
        # religion", where the Factbook gives "Muslim" with no shares.
        reasons: dict[str, str] = {}
        if written:
            for field in ROLLUP_FIELDS:
                why = country_gap_reason(nation, field)
                if why and field not in written and say_in_gap(unit, field, why):
                    reasons[field] = why
                    done.append(f"{iso3} {unit['name']} {field} (the country's reason)")
        # The same unit drawn again a level down takes what was just written.
        for twin in (admin2_by_country or {}).get(iso3, []):
            if twin.get("id") != unit.get("id") or twin.get("water"):
                continue
            for field in written:
                mine = twin.get(field)
                if isinstance(mine, dict) and mine.get("status") == NOT_AVAILABLE \
                        and not mine.get("not_this_ground"):
                    copy_field(unit, twin, field)
                    done.append(f"{iso3} {twin['name']} {field} (drawn again)")
            for field, why in reasons.items():
                if say_in_gap(twin, field, why):
                    done.append(f"{iso3} {twin['name']} {field} (the country's reason, "
                                f"drawn again)")
    return done


# How the Factbook reader says a field is given in words alone
# (scripts/fetch_factbook.py).
FACTBOOK_FREE_TEXT = "Factbook reports free text only: "


def country_gap_reason(nation: dict[str, Any], field: str) -> str | None:
    """For a country drawn as one first-level unit, why that unit has no
    ``field`` either: the country's own reason for its gap, or None where it
    gives none."""
    value = nation.get(field)
    if not (isinstance(value, dict) and is_gap(value) and value.get("note")):
        return None
    note = str(value["note"]).strip()
    if note.startswith(FACTBOOK_FREE_TEXT):
        words = note[len(FACTBOOK_FREE_TEXT):].strip()
        why = f"the CIA World Factbook gives only the words “{words}”."
    else:
        why = note if note.endswith(".") else note + "."
        if why[:1].isupper() and why[1:2].islower():
            why = why[:1].lower() + why[1:]
    return (f"{nation.get('name') or nation.get('id')} is drawn as a single first-level "
            f"unit, so the country's own figures are this unit's. The country has no "
            f"{field} shares to give it: {why}")


def join_note(before: Any, sentence: str) -> str:
    """A note with one more sentence, unless it already says it."""
    before = str(before or "").strip()
    if sentence in before:
        return before
    return f"{before} {sentence}".strip()


def cite_country(unit: dict[str, Any], nation: dict[str, Any], field: str) -> None:
    """The country's citation for ``field``, on the unit that now shows its figure."""
    cited = unit.setdefault("sources", [])
    for src in nation.get("sources") or []:
        fields = str(src.get("field") or "").split("/")
        if field in fields or "*" in fields:
            entry = {**src, "field": field}
            if entry not in cited:
                cited.append(entry)


def copy_field(source: dict[str, Any], target: dict[str, Any], field: str,
               sentence: str | None = None) -> None:
    """``source``'s value for ``field`` onto ``target``, with its satellites and sources.

    What fill_same_polygons does for a polygon drawn twice, for any two
    records that are the same ground. ``sentence`` is added to the note
    beside the value, ``<field>_note``, after the source's own: that is the
    note the panel shows for a figure as for a list. A note inside a figure
    travels with the figure, so a sentence about this record goes beside it.
    """
    value = copy.deepcopy(source[field])
    if isinstance(value, dict):
        # What the source record carried before a pass restated it describes
        # that record, not this one.
        value.pop(RESTATED_FROM, None)
    for suffix in SATELLITES:
        if f"{field}{suffix}" in source:
            target[f"{field}{suffix}"] = copy.deepcopy(source[f"{field}{suffix}"])
        else:
            target.pop(f"{field}{suffix}", None)
    if sentence and not is_gap(value):
        target[f"{field}_note"] = join_note(target.get(f"{field}_note"), sentence)
    target[field] = value
    carry_citation(source, target, field)


def restate_population(source: dict[str, Any], unit: dict[str, Any],
                       sentence: str | None = None) -> None:
    """copy_field for a first-level unit whose own population gives way to
    the same ground's figure on another record, flagged as the roll-ups'
    restate flags its own (RESTATED_FROM): the country's sum of its first
    level is gated on the figure the unit carried for itself
    (control_population), not on the one put in its place.

    Burkina Faso's Centre shows its one division Kadiogo's OCHA figure,
    3,510,028 for 2023, in place of Wikipedia's 3,030,384 for 2019.
    Unflagged, that brought the regions within the gate of the Factbook's
    figure for the country, and Burkina Faso's census and Factbook lines
    gave way to sums of a survey's 1,191 interviews.
    """
    was = unit.get("population")
    copy_field(source, unit, "population", sentence)
    if published(was) is None:
        return
    own = was.get(RESTATED_FROM)
    unit["population"][RESTATED_FROM] = (
        dict(own) if isinstance(own, dict)
        else {k: was[k] for k in ("value", "year", "source") if k in was})


# The fields' names as a source entry may spell them, and as the build does.
# INEGI's, the Dominican Republic's, Ireland's and a dozen other adapters'
# entries cite "median age/sex ratio", and every comparison with "median_age"
# missed them: Ensenada cited INEGI's median age beside OCHA's pooled one.
FIELD_SPELLINGS = {"median age": "median_age", "sex ratio": "sex_ratio"}


def field_name(part: str) -> str:
    """One field of a source entry's "a/b/c", as the build spells it."""
    part = part.strip()
    return FIELD_SPELLINGS.get(part, part)


def cited_fields(src: dict[str, Any]) -> list[str]:
    """The fields a source entry is cited for."""
    return [field_name(part) for part in str(src.get("field") or "").split("/")]


def spell_fields(sources: Any) -> Any:
    """A record's source entries with their fields spelled as the build does."""
    if not isinstance(sources, list):
        return sources
    out = []
    for src in sources:
        if isinstance(src, dict) and isinstance(src.get("field"), str):
            spelled = "/".join(cited_fields(src))
            if spelled != src["field"]:
                src = dict(src, field=spelled)
        out.append(src)
    return out


def names_source(src: dict[str, Any], value: Any) -> bool:
    """Whether a source entry names the source a figure says it is from: the
    same words, or the entry's name standing whole in the figure's (an entry
    "Wikidata" for "Wikidata (CC0)", "OCHA" for OCHA's dataset)."""
    said = str(value.get("source") or "") if isinstance(value, dict) else ""
    name = str(src.get("name") or "")
    if not said or not name:
        return False
    if (source_identity(said) == source_identity(name)
            or re.search(rf"(?<!\w){re.escape(name)}(?!\w)", said) is not None):
        return True
    # A figure two offices' tables add up to names both, ", and " between
    # them, and each office's entry is named office first: Korea's "Ministry
    # of the Interior and Safety, resident register, and Ministry of Justice,
    # registered foreign residents".
    parts = re.split(r", and (?=[A-Z])", said)
    return len(parts) > 1 and check_rollups.short_source(name) in {
        check_rollups.short_source(part) for part in parts}


def carry_citation(source: dict[str, Any], target: dict[str, Any], field: str) -> None:
    """The citation for ``field`` goes with its value from ``source`` to ``target``.

    On ``target``, an entry citing ``field`` alone goes, and one citing other
    fields too stays for those alone. From ``source`` each entry citing
    ``field`` comes, for that field alone; and where some of them name the
    source the figure says it is from, only those. Kadiogo cites its
    Wikidata item for "population/capital/coordinates" beside OCHA's
    population table, and when Centre shows Kadiogo's OCHA figure the item
    is not Centre's source for anything; Centre's own Wikipedia citation for
    the figure it no longer shows goes. An entry carried for several fields,
    one call each, is cited once for all of them, in its own order.
    """
    kept: list[dict[str, Any]] = []
    for src in target.get("sources") or []:
        fields = cited_fields(src)
        if field not in fields:
            kept.append(src)
        elif set(fields) - {field}:
            kept.append(dict(src, field="/".join(f for f in fields if f != field)))
    citing = [src for src in source.get("sources") or [] if field in cited_fields(src)]
    named = [src for src in citing if names_source(src, source.get(field))]
    # Of several Wikidata items, the one the source record is linked to: the
    # figure is that item's. Gotland's only division cited the island's item,
    # which has no population, beside Region Gotland's, which is the 60,724
    # shown, and Gotland County took both.
    own = source.get("wikidata")
    mine = [src for src in named if own and src.get("name") == "Wikidata"
            and str(src.get("url") or "").endswith(f"/{own}")]
    if mine:
        named = [src for src in named if src.get("name") != "Wikidata" or src in mine]
    for src in named or citing:
        entry = dict(src, field=field)
        if entry in kept:
            continue
        order = cited_fields(src)
        # An earlier field's narrowed copy of this same entry.
        same = next((i for i, have in enumerate(kept)
                     if dict(have, field=field) == entry
                     and set(cited_fields(have)) <= set(order)), None)
        if same is None:
            kept.append(entry)
            continue
        have = set(cited_fields(kept[same])) | {field}
        kept[same] = dict(kept[same], field="/".join(f for f in order if f in have))
    target["sources"] = kept


def fields_published(rows: list[dict[str, Any]]) -> set[str]:
    """The composition fields some unit of this level and country carries."""
    return {f for f in COMPOSITION_FIELDS for e in rows
            if isinstance(e.get(f), list) and e.get(f)}


def own_reasons(entity: dict[str, Any], published_here: set[str]) -> set[str]:
    """The fields whose gap carries a source's own reason the policy must not
    overwrite.

    The collection policy's sentence is about the country: its census does
    not ask the question, or asks another one. Where the unit's neighbours at
    this level do carry the field -- Switzerland's districts their nationality,
    Norway's kommuner their immigrant background, Slovenia's municipalities
    the 2002 census's religion -- that sentence is not why this one unit is
    empty, and the source that left it empty usually says why: Lac's 2009
    outline is straddled by a merged commune, a polygon is a detached piece
    of Frogn, Ankaran was carved out after 2002. Those reasons stand. Where
    no neighbour carries the field, the policy's reason is the true one and
    replaces whatever an adapter wrote, a stale copy of it or a generic hint
    (see apply_collection_policy).
    """
    return {f for f in published_here
            if isinstance(entity.get(f), dict)
            and entity[f].get("status") == NOT_AVAILABLE and entity[f].get("note")}


# ---------------------------------------------------------------------------
# A first-level unit's only division
# ---------------------------------------------------------------------------
#
# 172 first-level units on the build of main 1a72bd7 have exactly one
# division drawn beneath them under another id: Cotonou under Littoral,
# Kadiogo under Centre, Bulawayo under its province, Cape Verde's one-parish
# municipalities. Where the division is the parent's whole ground it is the
# same people, and the parent's figures -- counts, medians and ratios as well
# as shares -- describe it exactly. Where it is not, copying puts a region's
# figure on a part of it, which is the one thing this map must never do.
#
# The drawing alone cannot tell them apart, measured over all 172. Genuine
# pairs can look poor (Cape Verde's parishes sit only 83% inside their
# municipality, the rest coast; Littoral is drawn too large, over a quarter
# of Seme-Kpodji). Non-pairs can look good: Algeria's second level is its
# 48 wilayas drawn a second time from another source and out of register --
# Naama overlaps its own at IoU 0.905 while Algiers, Oran and Annaba lie
# outside "their" polygons. So five gates, each of which must pass:
#
#  1. the level divides its parent: a country whose second level is its
#     first drawn again, one division to every unit, has nothing to hand
#     down (Algeria);
#  2. evidence the division is the parent's only one: a code list the build
#     reads (OCHA COD-PS, CLEAR Global's pcodes) with one division under
#     the parent and none of that name under another; the same count, of
#     the same year, on both; the parent's own name on the division; or a
#     declared fact (SOLE_CHILD_DECLARED);
#  3. the drawing: SOLE_INSIDE of the division inside the parent, SOLE_SHARE
#     of the parent under it, no more than SOLE_SPILL of any other
#     first-level polygon taken, and no other division covering more than
#     SOLE_COVER of the parent -- whole islands with no populated place left
#     out of every measure, and the share and cover waived only where a code
#     list holds the pair and the land the parent has besides holds nobody;
#  4. the same people: two counts of the same year within SOLE_CHILD_BAND;
#  5. the parent's figure is its own ground: never a source's row that
#     covers more or less than the drawn unit (SOLE_CHILD_NOT_ITS_GROUND,
#     SOLE_CHILD_SOURCES_REFUSED, or a figure flagged not_this_ground).
#
# What passes is copied only into a field that is an empty not_available,
# never over a stated not_collected or a policy's reason, and never displaces
# a figure; except that where both copies carry a population and one is a
# statistics office's at least as new as an encyclopaedia's on the other,
# the office's is shown on both (an office's count is never replaced by an
# encyclopaedia's -- see FILL_ONLY -- and here the two are one unit).
SOLE_INSIDE = 0.80
SOLE_SHARE = 0.80
SOLE_SPILL = 0.15
SOLE_COVER = 0.15
SOLE_FIELDS = ("population", "median_age", "sex_ratio", "religion", "language", "ethnicity")
FIGURE_FIELDS = ("population", "median_age", "sex_ratio")
# A component of a polygon this much or less inside the other shape is not
# part of their common ground; and such components are left out only while
# together they are a minority of the polygon. Tarrafal de Sao Nicolau's
# three islets are 24% of it; the inner islands of La Digue's district are
# 67% of its polygon and hold people GeoNames does not list, and are not
# left out.
ISLET_TOUCH = 0.01
ISLET_AREA_MAX = 0.30

# Evidence for gate 2 that no code list the build reads gives:
# (country, parent) -> (the division's name as drawn, the fact, figures
# describe the division's ground although the parent is drawn larger).
SOLE_CHILD_DECLARED: dict[tuple[str, str], tuple[str, str, bool]] = {
    # Cape Verde's 22 municipalities hold 32 parishes (freguesias), and these
    # fourteen one each; the boundary file draws the parish under each.
    **{("CPV", municipality): (parish, f"{municipality} has one parish", False)
       for municipality, parish in (
           ("Maio", "Nossa Senhora da Luz"),
           ("Mosteiros", "Nossa Senhora da Ajuda"),
           ("Paul", "Santo Antonio das Pombas"),
           ("Praia", "Nossa Senhora da Graca"),
           ("Sal", "Nossa Senhora das Dores"),
           ("Santa Catarina", "Santa Catarina"),
           ("Santa Catarina do Fogo", "Santa Catarina do Fogo"),
           ("Santa Cruz", "Santiago Maior"),
           ("São Lourenço dos Órgãos", "Sao Lourenco dos Orgaos"),
           ("São Miguel", "Sao Miguel Arcanjo"),
           ("São Salvador do Mundo", "Sao Salvador do Mundo"),
           ("São Vicente", "Nossa Senhora da Luz"),
           ("Tarrafal", "Santo Amaro Abade"),
           ("Tarrafal de São Nicolau", "Sao Francisco de Assis"))},
    # The boundary file spells Ali Sabieh region "Ali Sabeh" at the second level.
    ("DJI", "Ali Sabieh"): ("Ali Sabeh", "Ali Sabeh is Ali Sabieh as the boundary file "
                                         "spells it", False),
    # Qatar's zones are numbered, and zone 71 is all of Umm Salal municipality.
    ("QAT", "Umm Slal"): ("71", "zone 71 is the whole of Umm Salal municipality", False),
    # Bangui is one commune with no sub-prefecture (car_prefecture lists it
    # once at each level). The first-level polygon is drawn over part of
    # Ombella-M'Poko as well, so it fails the share; its figures are the
    # commune's.
    ("CAF", "Bangui"): ("Bangui", "Bangui is one commune, with nothing below it", True),
}

# Gate 5, row by row: a parent figure a source publishes for other ground
# than the polygon it sits on. (country, parent) -> {field or "*": why}.
_SURVEY_FIELDS = ("religion", "language", "ethnicity")
SOLE_CHILD_NOT_ITS_GROUND: dict[tuple[str, str], dict[str, Any]] = {
    # Afrobarometer's region "Fogo" is the whole island -- Sao Filipe,
    # Mosteiros and Santa Catarina do Fogo -- joined to one municipality.
    ("CPV", "Santa Catarina do Fogo"): {
        f: "its survey region is the whole island of Fogo, not this municipality"
        for f in _SURVEY_FIELDS},
    # Wikidata's undated, round 30,000; the 2010 census counted 18,565. Only
    # that figure is refused: the 2021 census's own row is the municipality's.
    ("CPV", "Tarrafal"): {"population": (30000, "its 30,000 is not the census's count "
                                                "(18,565 in 2010)")},
    # Afrobarometer's North East region leaves out Francistown, its own
    # region in the survey, which lies inside this polygon.
    ("BWA", "North-East District"): {
        f: "its survey region leaves out Francistown, which this polygon holds"
        for f in _SURVEY_FIELDS},
    # The census's settlement table puts North Abaco at 3,772 in 2010; only
    # the 9,578 is refused.
    ("BHS", "North Abaco"): {"population": (9578, "its 9,578 is not the census's count of "
                                                  "the district (3,772 in 2010)")},
    # The census's island report "Exuma and Cays" takes in Black Point,
    # which the map draws as its own district.
    ("BHS", "Exuma"): {"*": "the census's Exuma and Cays takes in Black Point"},
    # The 2010 report gives San Salvador's religion and racial group only with
    # Rum Cay's (Tables 7.0 and 8.0).
    ("BHS", "San Salvador"): {f: "the census gives it only with Rum Cay's"
                              for f in _SURVEY_FIELDS},
    # Wikidata's 277,000 (2015) is Dire Dawa city's; the chartered
    # administration drawn here also holds its rural kebeles (OCHA's COD-PS
    # counts the two apart: ET1501 and ET1502).
    ("ETH", "Dire Dawa"): {"population": "its figure is the city's alone, without the "
                                          "administration's rural part"},
    # The census's own Central Andros district files Fresh Creek, the
    # local-government district's seat, under North Andros.
    ("BHS", "Central Andros"): {"population": "the census's Central Andros is not the "
                                               "district drawn: it leaves out Fresh Creek"},
}

# Gate 5, source by source: every figure of a kind a country's sources give
# for other ground than the drawn units. country -> ((field, year or None for
# every year, why), ...).
SOLE_CHILD_SOURCES_REFUSED: dict[str, tuple[tuple[str, int | None, str], ...]] = {
    # The 2022 census's district rows, as Wikipedia and Wikidata carry them,
    # are its supervisory districts, drawn like the constituencies: East Grand
    # Bahama's 11,011 is a constituency's, on a district drawn round High Rock;
    # South Andros's 3,711 is South and Central Andros and Mangrove Cay.
    "BHS": (("population", 2022, "the 2022 census's district rows are its supervisory "
                                 "districts, not the districts the map draws"),),
    # Lebanon has taken no census since 1932, and its governorates' and
    # cazas' figures are estimates the map takes for nothing but compositions.
    "LBN": (("population", None, "Lebanon has no count of its governorates' residents"),),
}

# Gate 1's reason, where the country is known. Algeria's 48 second-level
# polygons are its 48 wilayas drawn again, from another source.
LEVEL_REDRAWS_FIRST: dict[str, str] = {
    "DZA": ("The boundary file's second level for Algeria is not its districts or "
            "communes: it draws the 48 wilayas a second time, from another source and "
            "out of register with the first level, so its outlines do not follow the "
            "wilayas' and some lie over other wilayas. The wilaya's own figures, where "
            "it has any, are on the first level, and none is repeated here."),
}

# What a refused division says in place of its parent's figures, where the
# reason is a fact about the drawing a reader should have rather than one
# measure falling short: (country, parent, division) -> note, written where
# the division's field is a gap with no reason and the parent carries a
# figure. Each was checked on the boundary file and GeoNames' points.
SOLE_CHILD_REFUSED_NOTES: dict[tuple[str, str, str], str] = {
    # The second level's names are shuffled: Brazzaville's point lies in the
    # polygon labelled Zanaga, Zanaga's (226 km away) in "Komono", Sibiti's in
    # "Divenie", Impfondo's in "Owando", Dongou's in "Ngabe", Mvouti's in
    # "Djambala". The polygon is Brazzaville's ground under another name.
    ("COG", "Brazzaville", "Zanaga"): (
        "This polygon is labelled Zanaga, but it is the ground around Brazzaville, the "
        "city's centre included. The town of Zanaga lies about 230 km to the north-west, "
        "in Lékoumou, inside a polygon labelled Komono, and other second-level polygons "
        "of the country carry names out of place in the same way. Brazzaville's figures "
        "are shown one level up and are not repeated under this name."),
    # 79% of the drawn Nouadhibou lies inside the region and some 3,000 km2 in
    # Inchiri; the region's department of Chami (Wikidata Q131008371) is drawn
    # as a polygon filed under Inchiri, over 26% of the region's polygon.
    ("MRT", "Dakhlet Nouadhibou", "Nouadhibou"): (
        "This polygon is not the region's ground as the map draws it: about a fifth of "
        "it lies in Inchiri, and the region's other department, Chami, is drawn as a "
        "polygon filed under Inchiri. Dakhlet Nouadhibou's figures are shown one level "
        "up and are not repeated here."),
    # Seychelles is not here: its second level is the census's eight regions,
    # each of several districts, and is filed under the country (NOT_NESTED),
    # so no district has an only division and none is refused.
}

# How a refused figure is named in the sentence that says so.
FIELD_WORDS = {"population": "population", "median_age": "median age",
               "sex_ratio": "sex ratio", "religion": "religion", "language": "language",
               "ethnicity": "ethnicity"}
# Gate 5's reason for a figure its own source flags; the source's note says it.
FLAGGED_GROUND = "its figure is flagged as another ground's"


def say_in_gap(entity: dict[str, Any], field: str, note: str) -> bool:
    """``note`` as the reason ``field`` is empty, where it is a gap with no
    reason yet or only a source's coded marker, which is kept in plain words
    before it. Never over a figure, a stated reason or another status."""
    value = entity.get(field)
    if not (isinstance(value, dict) and value.get("status") == NOT_AVAILABLE
            and "value" not in value):
        return False
    before = value.get("note")
    if before and before not in PLAIN_NOTES:
        return False
    entity[field] = {**value, "note": join_note(PLAIN_NOTES.get(before), note)}
    return True


def say_refused(iso3: str, parent: dict[str, Any], child: dict[str, Any]) -> None:
    """A refused division's declared reason, in each field its parent fills."""
    note = SOLE_CHILD_REFUSED_NOTES.get((iso3, parent.get("name"), child.get("name")))
    if not note:
        return
    for field in SOLE_FIELDS:
        value = parent.get(field)
        if published(value) is not None or (isinstance(value, list) and value):
            say_in_gap(child, field, note)


def sole_children(admin1_by_country: dict[str, list[dict[str, Any]]],
                  admin2_by_country: dict[str, list[dict[str, Any]]]
                  ) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """(country, parent, its only division) for every first-level unit with one
    land division drawn under another id."""
    out = []
    for iso3, parents in sorted(admin1_by_country.items()):
        kids: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for entity in admin2_by_country.get(iso3, []):
            if not entity.get("water"):
                kids[entity.get("parent")].append(entity)
        for parent in parents:
            rows = kids.get(parent["id"], [])
            if (len(rows) == 1 and rows[0]["id"] != parent["id"]
                    and not parent.get("water")):
                out.append((iso3, parent, rows[0]))
    return out


def level_redraws(parents: list[dict[str, Any]], children: list[dict[str, Any]]) -> bool:
    """Gate 1: the second level is the first drawn again, one for one."""
    land1 = [p for p in parents if not p.get("water")]
    land2 = [c for c in children if not c.get("water")]
    if len(land1) < 2 or len(land1) != len(land2):
        return False
    under: dict[Any, int] = defaultdict(int)
    for c in land2:
        under[c.get("parent")] += 1
    ids = {p["id"] for p in land1}
    return (all(under.get(p["id"]) == 1 for p in land1)
            and not any(c["id"] in ids for c in land2))


def code_hierarchy(processed: Path | None = None) -> dict[str, dict[str, list[str]]]:
    """{country: {norm(first-level name): [its second-level names]}} from the
    code lists the build reads: OCHA COD-PS's parent names, and CLEAR
    Global's pcodes, where a second-level code begins with its parent's."""
    base = processed or PROCESSED
    out: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in read_json(base / "cod_ps_admin2.json", []) or []:
        if row.get("parent_name") and row.get("country") and row.get("name"):
            out[row["country"]][norm(row["parent_name"])].append(row["name"])
    clear = read_json(base / "clear_global_language.json", []) or []
    codes1: dict[str, dict[str, str]] = defaultdict(dict)
    for row in clear:
        code = str(row.get("id") or "").split("-")[-1]
        if row.get("level") == "admin1" and row.get("country"):
            codes1[row["country"]][code] = row.get("name") or ""
    for row in clear:
        code = str(row.get("id") or "").split("-")[-1]
        if row.get("level") != "admin2" or not row.get("country"):
            continue
        parent = max((c for c in codes1[row["country"]] if code.startswith(c) and c != code),
                     key=len, default=None)
        if parent is not None:
            names = out[row["country"]][norm(codes1[row["country"]][parent])]
            if row.get("name") not in names:
                names.append(row.get("name"))
    return out


def same_name(a: str | None, b: str | None) -> bool:
    return bool(a and b) and (norm(a) == norm(b) or related(name_forms(a), name_forms(b)))


def sole_child_evidence(iso3: str, parent: dict[str, Any], child: dict[str, Any],
                        codes: dict[str, dict[str, list[str]]]) -> tuple[str | None, bool, bool]:
    """Gate 2: (the evidence in words or None, whether it is a code list's,
    whether the parent's figures are declared the child's ground)."""
    declared = SOLE_CHILD_DECLARED.get((iso3, parent.get("name")))
    if declared and same_name(declared[0], child.get("name")):
        return declared[1], False, declared[2]
    country = codes.get(iso3) or {}
    under = country.get(norm(parent.get("name")))
    if under is None:
        under = next((v for k, v in country.items()
                      if k and related(name_forms(k), name_forms(parent.get("name")))), None)
    if under is not None and len(under) == 1:
        elsewhere = [k for k, v in country.items() if v is not under
                     and any(norm(n) == norm(child.get("name")) for n in v)]
        if not elsewhere:
            return (f"the code list has one division under {parent.get('name')}",
                    True, False)
    mine, theirs = child.get("population"), parent.get("population")
    if (published(mine) is not None and published(mine) == published(theirs)
            and vintage(mine) is not None and vintage(mine) == vintage(theirs)):
        return "both carry the same count", False, False
    if same_name(child.get("name"), parent.get("name")):
        return "it carries the parent's own name", False, False
    return None, False, False


def islets_dropped(shape, other, points):
    """``shape`` without its whole islands that meet ``other`` hardly at all
    and hold no populated place."""
    from shapely.geometry import MultiPolygon

    parts = list(getattr(shape, "geoms", [shape]))
    if len(parts) < 2:
        return shape
    kept = []
    for part in parts:
        if part.area <= 0:
            continue
        touched = part.intersection(other).area / part.area if other is not None else 0.0
        if touched > ISLET_TOUCH or any(part.contains(p) for p in points):
            kept.append(part)
    if not kept or sum(p.area for p in kept) < (1 - ISLET_AREA_MAX) * shape.area:
        return shape
    polys = [g for part in kept for g in getattr(part, "geoms", [part])
             if g.geom_type == "Polygon"]
    return MultiPolygon(polys) if len(polys) > 1 else polys[0]


def geonames_points(countries: set[str], path: Path | None = None) -> dict[str, list[Any]]:
    """GeoNames' populated places, as points, for the countries asked."""
    import gzip
    from shapely.geometry import Point

    path = path or RAW / "geonames" / "places.tsv.gz"
    out: dict[str, list[Any]] = defaultdict(list)
    if not path.exists() or not countries:
        return out
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        header = next(handle).rstrip("\n").split("\t")
        at = {k: i for i, k in enumerate(header)}
        for line in handle:
            row = line.rstrip("\n").split("\t")
            if row[at["iso3"]] in countries:
                try:
                    out[row[at["iso3"]]].append(Point(float(row[at["lon"]]),
                                                      float(row[at["lat"]])))
                except ValueError:
                    continue
    return out


def measure_sole_children(pairs: list[tuple[str, dict[str, Any], dict[str, Any]]],
                          shapes: dict[str, list[dict[str, Any]]],
                          geometry: Callable[[dict[str, dict[str, Any]]], Any] | None = None,
                          points: dict[str, list[Any]] | None = None
                          ) -> dict[str, dict[str, Any]]:
    """Gate 3's measures for each pair, keyed by the division's id.

    inside: of the division, the share inside its parent; share: of the
    parent, the share under the division; spill: the most of any other
    first-level polygon the division takes, and whose; cover: each other
    division's share of the parent, with its parent; peopled: whether the
    parent's land outside the division holds a populated place. Whole
    islands with no populated place that the other polygon hardly meets are
    left out of every measure: Santa Luzia, Raso and Branco are Sao
    Vicente's, filed by the first level under Tarrafal de Sao Nicolau.
    """
    from shapely.geometry import box

    adm1 = {s["shape_id"]: s for s in shapes.get("ADM1", []) if s.get("_geom") is not None}
    adm2 = {s["shape_id"]: s for s in shapes.get("ADM2", []) if s.get("shape_id")}
    by_country1: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in adm1.values():
        by_country1[s["group"]].append(s)
    by_country2: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in adm2.values():
        by_country2[s["group"]].append(s)
    wanted: dict[str, dict[str, Any]] = {}
    for iso3, parent, child in pairs:
        p = adm1.get(parent["id"])
        if p is None or child["id"] not in adm2:
            continue
        wanted[child["id"]] = adm2[child["id"]]
        frame = box(*p["bbox"])
        for s in by_country2[iso3]:
            if s["shape_id"] != child["id"] and box(*s["bbox"]).intersects(frame):
                wanted[s["shape_id"]] = s
    if not wanted:
        return {}
    geoms = {sid: whole(g) for sid, g in (geometry or adm2_geometry)(wanted)}
    if points is None:
        points = geonames_points({iso3 for iso3, _, _ in pairs})
    out: dict[str, dict[str, Any]] = {}
    for iso3, parent, child in pairs:
        p = adm1.get(parent["id"])
        c_geom = geoms.get(child["id"])
        if p is None or c_geom is None or c_geom.is_empty:
            continue
        here = points.get(iso3, [])
        p_geom = whole(p["_geom"])
        p_land = islets_dropped(p_geom, c_geom, here)
        c_land = islets_dropped(c_geom, p_geom, here)
        both = p_land.intersection(c_land).area
        spill, spill_by = 0.0, None
        for q in by_country1[iso3]:
            if q["shape_id"] == parent["id"] or not box(*q["bbox"]).intersects(box(*c_land.bounds)):
                continue
            q_geom = whole(q["_geom"])
            taken = c_land.intersection(q_geom).area / q_geom.area if q_geom.area else 0.0
            if taken > spill:
                spill, spill_by = taken, q["name"]
        cover = []
        for sid, d_geom in geoms.items():
            if sid == child["id"] or adm2[sid]["group"] != iso3:
                continue
            under = p_land.intersection(d_geom).area / p_land.area if p_land.area else 0.0
            if under > 0.0:
                cover.append((round(under, 4), adm2[sid]["name"], adm2[sid].get("parent_shape")))
        cover.sort(reverse=True)
        rest = p_land.difference(c_land)
        out[child["id"]] = {
            "inside": round(both / c_land.area, 4) if c_land.area else 0.0,
            "share": round(both / p_land.area, 4) if p_land.area else 0.0,
            "spill": round(spill, 4), "spill_by": spill_by,
            "cover": cover[:5],
            "peopled": any(rest.contains(pt) for pt in here) if not rest.is_empty else False,
        }
    return out


def sole_child_drawing(parent: dict[str, Any], m: dict[str, Any] | None,
                       from_codes: bool, own_ground: bool) -> str | None:
    """Gate 3: why the drawing refuses the pair, or None."""
    if not m:
        return "its polygon could not be measured"
    if m["inside"] < SOLE_INSIDE:
        return f"only {m['inside']:.0%} of it lies inside {parent.get('name')}"
    if m["spill"] > SOLE_SPILL:
        return f"it takes {m['spill']:.0%} of {m['spill_by']}"
    others = [(share, name, owner) for share, name, owner in m["cover"] if share > SOLE_COVER]
    short = m["share"] < SOLE_SHARE
    if not short and not others:
        return None
    # Waived only where a code list holds the pair, the covering divisions
    # are other parents', and the parent's figures are the division's own
    # ground: declared so, or the land the parent has besides holds nobody.
    if (from_codes or own_ground) and all(owner != parent["id"] for _, _, owner in others) \
            and (own_ground or not m["peopled"]):
        return None
    if others:
        share, name, _ = others[0]
        return f"{name} covers {share:.0%} of {parent.get('name')}"
    return f"it covers only {m['share']:.0%} of {parent.get('name')}"


def parent_not_its_ground(iso3: str, parent: dict[str, Any], field: str) -> str | None:
    """Gate 5: why the parent's figure for ``field`` is not its own drawn ground."""
    value = parent.get(field)
    if isinstance(value, dict) and value.get("not_this_ground"):
        return FLAGGED_GROUND
    declared = SOLE_CHILD_NOT_ITS_GROUND.get((iso3, parent.get("name"))) or {}
    why = declared.get(field) or declared.get("*")
    if isinstance(why, tuple):
        # One figure refused, by its value; another figure for the field is
        # the parent's own and may pass.
        refused, why = why
        if published(value) != refused:
            why = None
    if why:
        return why
    for name, year, reason in SOLE_CHILD_SOURCES_REFUSED.get(iso3, ()):
        if name == field and (year is None or vintage(value) == year):
            return reason
    return None


def encyclopaedic(value: Any) -> bool:
    """A figure an encyclopaedia carries: Wikidata's or Wikipedia's."""
    source = str(value.get("source") or "") if isinstance(value, dict) else ""
    return source.startswith("Wikidata") or "Wikipedia" in source


def projection(value: Any) -> bool:
    """A figure projected forward from an older count, not a count: OCHA's
    COD-PS tables and anything that says it is a projection."""
    source = str(value.get("source") or "") if isinstance(value, dict) else ""
    return bool(re.search(r"Common Operational Dataset|COD-PS|projection", source, re.I))


def office_over_encyclopaedia(a: dict[str, Any], b: dict[str, Any]
                              ) -> dict[str, Any] | None:
    """Of two records that are one unit, the one whose population should show
    on both: a statistics office's at least as new as the encyclopaedia's
    figure on the other. None when that is not the case."""
    pa, pb = a.get("population"), b.get("population")
    va, vb = published(pa), published(pb)
    if va is None or vb is None or va == vb:
        return None
    if encyclopaedic(pa) == encyclopaedic(pb):
        return None
    office, other = (a, b) if encyclopaedic(pb) else (b, a)
    # A projection is not a count, and an encyclopaedia's figure is often a
    # census's at one remove: between the two neither is put over the other.
    if projection(office.get("population")):
        return None
    newer = vintage(office.get("population"))
    older = vintage(other.get("population"))
    if newer is None or (older is not None and newer < older):
        return None
    ratio = published(other.get("population")) / published(office.get("population"))
    if not SOLE_CHILD_BAND[0] <= ratio <= SOLE_CHILD_BAND[1]:
        return None
    return office


def newer_office(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
    """Of two records that are one unit, both with an office's count and no
    encyclopaedia's or projection's, the one whose figure is newer, to show
    on both (a subdivision shows the most recent figure available). None
    where the two are of one year, either is missing, or they are too far
    apart to be one ground's."""
    pa, pb = a.get("population"), b.get("population")
    va, vb = published(pa), published(pb)
    if va is None or vb is None or va == vb:
        return None
    if encyclopaedic(pa) or encyclopaedic(pb) or projection(pa) or projection(pb):
        return None
    ya, yb = vintage(pa), vintage(pb)
    if ya is None or yb is None or ya == yb:
        return None
    newer, other = (a, b) if ya > yb else (b, a)
    ratio = published(other.get("population")) / published(newer.get("population"))
    if not SOLE_CHILD_BAND[0] <= ratio <= SOLE_CHILD_BAND[1]:
        return None
    return newer


def fill_sole_children(admin1_by_country: dict[str, list[dict[str, Any]]],
                       admin2_by_country: dict[str, list[dict[str, Any]]],
                       measures: dict[str, dict[str, Any]],
                       codes: dict[str, dict[str, list[str]]]
                       ) -> tuple[list[str], list[str]]:
    """Give a first-level unit's only division, on the same ground, its figures.

    See the gates above. Returns the cells written and the pairs refused,
    each with its reason, for the log.
    """
    filled: list[str] = []
    refused: list[str] = []
    redrawn = {iso3 for iso3, parents in admin1_by_country.items()
               if level_redraws(parents, admin2_by_country.get(iso3, []))}
    for iso3, parent, child in sole_children(admin1_by_country, admin2_by_country):
        where = f"{iso3} {parent.get('name')} > {child.get('name')}"
        if parent.get("disputed") or child.get("disputed"):
            continue
        if iso3 in redrawn:
            refused.append(f"{where}: the second level draws the first again")
            note = LEVEL_REDRAWS_FIRST.get(iso3)
            if note:
                for field in FIGURE_FIELDS:
                    value = child.get(field)
                    if isinstance(value, dict) and value.get("status") == NOT_AVAILABLE:
                        before = str(value.get("note") or "")
                        kept = before if "left out" in before else ""
                        child[field] = gap(NOT_AVAILABLE, join_note(kept, note))
            continue
        evidence, from_codes, own_ground = sole_child_evidence(iso3, parent, child, codes)
        if evidence is None:
            refused.append(f"{where}: nothing shows it is the parent's only division")
            say_refused(iso3, parent, child)
            continue
        why = sole_child_drawing(parent, measures.get(child["id"]), from_codes, own_ground)
        if why:
            refused.append(f"{where}: {why}")
            say_refused(iso3, parent, child)
            continue
        mine, theirs = child.get("population"), parent.get("population")
        if published(mine) and published(theirs) and vintage(mine) is not None \
                and vintage(mine) == vintage(theirs):
            ratio = published(mine) / published(theirs)
            if not SOLE_CHILD_BAND[0] <= ratio <= SOLE_CHILD_BAND[1]:
                refused.append(f"{where}: it counts {ratio:.0%} of its parent's people "
                               f"in the same year")
                say_refused(iso3, parent, child)
                continue
        # Said of the division, on the division's record: its own name would
        # read "Conakry is Conakry's only division".
        sentence = (f"This is {parent.get('name')}'s only division and covers the same "
                    f"ground, so the figure is {parent.get('name')}'s.")
        for field in SOLE_FIELDS:
            current, value = child.get(field), parent.get(field)
            if not (isinstance(current, dict) and current.get("status") == NOT_AVAILABLE
                    and not current.get("not_this_ground")):
                continue
            if field in ROLLUP_FIELDS and collection_gap(iso3, field) is not None:
                continue
            if field in FIGURE_FIELDS:
                if published(value) is None:
                    continue
            elif not (isinstance(value, list) and value):
                continue
            ground = parent_not_its_ground(iso3, parent, field)
            if ground:
                refused.append(f"{where} {field}: {ground}")
                # Said where the division would otherwise be bare; a figure
                # its own source flags is explained by that source's note.
                if ground != FLAGGED_GROUND:
                    say_in_gap(child, field, f"{parent.get('name')}'s {FIELD_WORDS[field]} "
                                             f"figure is not repeated here: {ground}.")
                continue
            copy_field(parent, child, field, sentence)
            filled.append(f"{where} {field}")
        # A newer figure prefer_newer_figures put in front of the count the
        # other record shows is that count's successor on both, as for a
        # polygon drawn twice (twin_population): Minsk City showed Wikidata's
        # 1,995,091 for 2026 in front of the 2019 census, and its only
        # division the census's 2,018,281 beside the same ground.
        for newer, older in ((parent, child), (child, parent)):
            if not put_in_front_of(newer.get("population"), older.get("population")):
                continue
            if newer is parent and parent_not_its_ground(iso3, parent, "population"):
                continue
            said = (f"This is {parent.get('name')}'s only division and covers the same "
                    f"ground, so both show this figure." if older is child else
                    f"{only_division(parent, child)} covers the same ground, so both show "
                    f"this figure.")
            was = published(older["population"])
            restate_population(newer, older, said)
            filled.append(f"{where} population: {was:,.0f} on the "
                          f"{'division' if older is child else 'parent'} gives way to "
                          f"{published(newer['population']):,.0f}")
            break
        else:
            newer = None
        if newer is not None:
            continue
        # One unit, two populations: the office's on both, where it is at
        # least as new as the encyclopaedia's. A parent figure of other ground
        # is never handed down; it may still give way to its division's.
        # Or two offices' counts of it, the newer on both: Vienna showed
        # Eurostat's 2,028,289 for 2025 and its only division, Wien(Stadt),
        # Statistik Austria's 2,040,914 for 2026.
        office = (office_over_encyclopaedia(parent, child)
                  or newer_office(parent, child))
        if office is parent and parent_not_its_ground(iso3, parent, "population"):
            office = None
        if office is not None:
            other = child if office is parent else parent
            said = (f"This is {parent.get('name')}'s only division and covers the same "
                    f"ground, so both show this figure." if other is child else
                    f"{only_division(parent, child)} covers the same ground, so both show "
                    f"this figure.")
            was = published(other["population"])
            if other is parent:
                restate_population(office, parent, said)
            else:
                copy_field(office, other, "population", said)
            filled.append(f"{where} population: {was:,.0f} on the "
                          f"{'division' if other is child else 'parent'} gives way to "
                          f"{published(office['population']):,.0f}")
            continue
        said = division_restates_parent(iso3, parent, child)
        if said:
            was = published(parent["population"])
            restate_population(child, parent, said)
            filled.append(f"{where} population: {was:,.0f} on the parent gives way to "
                          f"its division's {published(child['population']):,.0f}")
    return filled, refused


def division_restates_parent(iso3: str, parent: dict[str, Any], child: dict[str, Any]
                             ) -> str | None:
    """The sentence for a parent whose encyclopaedia figure gives way to its only
    division's, or None.

    restate_encyclopaedia_parents puts the one-source sum of a unit's
    divisions in place of an encyclopaedia's older figure for the unit, and
    leaves a unit drawn as a single division to this pass, which is the one
    that weighs whether the division is the unit's whole ground. Where it is,
    the same rule holds for its one figure. Burkina Faso's Centre carried
    Wikipedia's 3,030,384 for 2019 over Kadiogo, its whole ground, at OCHA's
    3,510,028 for 2023, while the country's other regions took their
    provinces' 2023 sums; Conakry and Benin's Littoral sat the same way. As
    there, only a division's figure of a later year than the parent's, from a
    source that is not itself an encyclopaedia, a projection only where the
    parent's figure is RESTATE_PROJECTION_YEARS older or more, and never in a
    country RESTATE_KEEPS names, for a unit whose count takes in ground the map
    draws elsewhere (UNDRAWN_PARTS), or where a division is drawn on the wrong
    side of the unit's edge (MISFILED_DIVISIONS).
    """
    pop, theirs = parent.get("population"), child.get("population")
    own, value = published(pop), published(theirs)
    if own is None or value is None or round(own) == round(value):
        return None
    if not check_rollups.is_encyclopaedic(pop) or check_rollups.is_encyclopaedic(theirs):
        return None
    if iso3 in RESTATE_KEEPS or (iso3, parent.get("name")) in UNDRAWN_PARTS:
        return None
    if theirs.get("not_this_ground"):
        return None
    if (iso3, child.get("id")) in MISFILED_DIVISIONS or any(
            iso == iso3 and home == parent.get("name")
            for (iso, _), (_, home) in MISFILED_DIVISIONS.items()):
        return None
    year, own_year = vintage(theirs), vintage(pop)
    if year is None or (own_year is not None and year <= own_year):
        return None
    if own_year is not None and projection(theirs) \
            and year - own_year < RESTATE_PROJECTION_YEARS:
        return None
    was = named_source(str(pop.get("source") or ""))
    return (f"{only_division(parent, child)} covers the same ground, and its figure is "
            f"shown here too, for {year} from "
            f"{named_source(str(theirs.get('source') or ''))}. It replaces "
            f"{own:,.0f}"
            + (f" for {own_year}, an older figure from {was}." if own_year
               else f" from {was}, which gives no year for it."))


def only_division(parent: dict[str, Any], child: dict[str, Any]) -> str:
    """The parent's one division, named as the parent's record says it.

    "Of the same name" only where the two names are one: same_name also
    relates Crooked Island to its division Crooked Island and Long Cay, which
    is evidence enough for gate 2 but not a thing to tell a reader.
    """
    if child.get("name") and norm(child.get("name")) == norm(parent.get("name")):
        return "Its only division, of the same name,"
    return f"Its only division, {child.get('name')},"


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


# A label a parent's table leaves out, where the children name it, is one
# the table printed as nothing: below its print cut. CLEAR Global prints
# shares to a tenth of a point and leaves out what rounds to nothing, so a
# label below half a tenth of a point of the parent's people is taken to be
# that, and anything above it is a finer question than the parent's.
PRINT_CUT = 0.0005

# Countries whose divisions' populations are of another base than their
# parents' own figure, in the same census, so the parent is weighed by the
# sum of its divisions. Cambodia's 2019 census gives each district its people
# in normal or regular households (the final report's Tables P-01 to P-25)
# and each province its total population (Table 2.1.1); Kampong Thom's
# districts make 675,400 of its 681,549. Weighed by its own total, the
# province's shares carry the 6,149 others into the district left over.
RESIDUAL_PARENT_BY_DIVISIONS: dict[str, str] = {
    "KHM": "the districts' populations are the census's household population and "
           "the province's its total",
}


# A unit whose subtraction was once on the map and is refused now, with the
# reason in words. Morocco's Assa-Zag carried CLEAR Global's 2014 census
# shares for its region less its other three provinces, weighed by 2024
# populations; on the census's own 2014 weights the difference still put more
# people on Tachelhit than the High Commission for Planning's 2014 report on
# the province counts using it at all, so the region's row does not
# decompose and nothing is written.
RESIDUAL_REFUSED_NOTES: dict[tuple[str, str, str], str] = {
    ("MAR", "Assa-Zag Province", "language"): (
        "CLEAR Global's tabulation of Morocco's 2014 census gives Guelmim-Oued Noun and "
        "its other provinces, but no row for Assa-Zag. The region's figure less the other "
        "provinces' is not given in its place: the populations to weigh their shares by "
        "are of other years, and a difference taken that way is not a count of anyone "
        "here. Weighed by the census's own 2014 populations instead, it would put more "
        "people on Tachelhit than the High Commission for Planning's 2014 report on the "
        "province counts using the language at all."),
}


def residual(nation: dict[str, Any], known: list[dict[str, Any]],
             target: dict[str, Any], field: str, iso3: str | None = None
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

    Where the parent and every other unit print counts, the counts are
    subtracted: that is the source's own arithmetic, whatever year anyone's
    population is. Latvia's Ropazu novads is its three 2009-2021 units'
    2011 census counts summed, and less those three units it leaves nobody
    for Vangazi -- which was, in 2011, part of another novads.

    Otherwise the shares are weighed by populations, and only by populations
    of the composition's own year: shares of one year priced by people of
    another describe neither. As built before, Latvia's 2011 shares were
    weighed by 2026 populations and wrote a Vangazi that does not exist, and
    Morocco's 2014 census shares by 2024 figures put Tachelhit on Assa-Zag
    eight points too high.
    """
    own = source_names(nation, field)
    theirs: set[str] = set().union(*(source_names(r, field) for r in known))
    if not own or not theirs or not (own & theirs):
        return (f"the national figure ({', '.join(sorted(own)) or 'no named source'}) "
                f"and the units' ({', '.join(sorted(theirs)) or 'no named source'}) "
                f"come from different sources; a difference between them is not a unit",
                None)
    rows = [nation.get(field), *(r[field] for r in known)]
    if all(isinstance(v, list) and v and all(isinstance(e.get("count"), (int, float))
                                             for e in v if isinstance(e, dict))
           for v in rows):
        return residual_by_counts(nation, known, target, field)
    years = ({nation.get(f"{field}_year")}
             | {r.get(f"{field}_year") for r in known}
             | {vintage(r.get("population")) for r in [nation, *known, target]})
    if len(years) > 1:
        shown = ", ".join(str(y) for y in sorted(y for y in years if y)) or "none"
        return (f"the shares and the populations to weigh them by are not of one "
                f"year ({shown}{', and undated' if None in years else ''})", None)
    pops = {r["id"]: published(r.get("population")) for r in [*known, target]}
    if any(v is None for v in pops.values()):
        return "not every unit and the country has a published population to weigh by", None
    total = sum(v for v in pops.values() if v is not None)
    if iso3 in RESIDUAL_PARENT_BY_DIVISIONS:
        nat_pop = total
    else:
        nat_pop = published(nation.get("population"))
        if nat_pop is None:
            return ("not every unit and the country has a published population to "
                    "weigh by", None)
        if abs(total - nat_pop) > RESIDUAL_TOLERANCE * nat_pop:
            return (f"the units' populations sum to {total:,.0f} against a national "
                    f"{nat_pop:,.0f}", None)
    labels = {g for g, _ in shares_of(nation.get(field))}
    implied: dict[str, float] = defaultdict(float)
    for r in known:
        for g, pct in shares_of(r[field]):
            if g not in labels:
                implied[g] += pct / 100 * (pops[r["id"]] or 0.0)
    foreign = {g for g, people in implied.items() if people >= PRINT_CUT * nat_pop}
    if foreign:
        return (f"the units name groups the national figure does not "
                f"({', '.join(sorted(foreign)[:4])})", None)
    counts = {g: pct / 100 * nat_pop for g, pct in shares_of(nation.get(field))}
    for r in known:
        for g, pct in shares_of(r[field]):
            counts[g] = counts.get(g, 0.0) - pct / 100 * (pops[r["id"]] or 0.0)
    own_pop = pops[target["id"]] or 0.0
    negative = [g for g, c in counts.items() if c < -RESIDUAL_TOLERANCE * own_pop]
    if negative:
        return f"the subtraction goes negative for {', '.join(sorted(negative)[:4])}", None
    left = sum(max(c, 0.0) for c in counts.values())
    if own_pop <= 0 or abs(left - own_pop) > RESIDUAL_TOLERANCE * own_pop:
        return (f"the residual is {left:,.0f} people against the unit's published "
                f"{own_pop:,.0f}", None)
    return None, whole_hundred([(g, c / left * 100) for g, c in counts.items() if c > 0])


def residual_by_counts(nation: dict[str, Any], known: list[dict[str, Any]],
                       target: dict[str, Any], field: str
                       ) -> tuple[str | None, list[dict[str, Any]] | None]:
    """The subtraction on the counts the parent and its other units print."""
    counts: dict[str, float] = defaultdict(float)
    for e in nation.get(field) or []:
        counts[e["group"]] += float(e["count"])
    whole = sum(counts.values())
    for r in known:
        for e in r[field]:
            counts[e["group"]] -= float(e["count"])
    left = sum(max(c, 0.0) for c in counts.values())
    if whole <= 0 or left < max(1.0, 0.001 * whole):
        return ("the parent's counts are its other units' own: nothing is left over "
                "for this one", None)
    negative = [g for g, c in counts.items() if c < -RESIDUAL_TOLERANCE * left]
    if negative:
        return f"the subtraction goes negative for {', '.join(sorted(negative)[:4])}", None
    # What is left over has to be this unit's people, give or take the years
    # between its count and the table's: otherwise it is ground the other
    # units do not cover, or a unit the table does not have.
    own_pop = published(target.get("population"))
    if not own_pop:
        return ("the unit has no published population to check what is left over "
                "against", None)
    when, then = vintage(target.get("population")), nation.get(f"{field}_year")
    apart = abs(when - then) if isinstance(when, int) and isinstance(then, int) else 0
    slack = min(ROLLUP_DRIFT_CAP, RESIDUAL_TOLERANCE + ROLLUP_DRIFT_PER_YEAR * apart)
    if abs(left - own_pop) > slack * own_pop:
        return (f"the residual is {left:,.0f} people against the unit's published "
                f"{own_pop:,.0f}", None)
    rows = whole_hundred([(g, c / left * 100) for g, c in counts.items() if c > 0])
    return None, rows


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
            if collection_gap(iso3, field) is not None:
                continue
            blank = [r for r in rows if isinstance(r.get(field), dict)
                     and r[field].get("status") == NOT_AVAILABLE]
            known = [r for r in rows if isinstance(r.get(field), list)]
            if len(blank) != 1 or len(known) != len(rows) - 1:
                continue
            target = blank[0]
            where = f"{iso3} {target['name']} {field}"
            if target[field].get("not_this_ground"):
                refused.append(f"{where}: its own gap says no figure fits this polygon")
                continue
            why, shares = residual(nation, known, target, field, iso3)
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
                # A field with a stated policy is one whose gaps are reasons,
                # not unread figures: Sweden's two kommuner whose church rows
                # are another territory would get those rows back by
                # subtraction from the län that sums them.
                if collection_gap(iso3, field) is not None:
                    continue
                blank = [r for r in rows if isinstance(r.get(field), dict)
                         and r[field].get("status") == NOT_AVAILABLE]
                known = [r for r in rows if isinstance(r.get(field), list)]
                if len(blank) != 1 or len(known) != len(rows) - 1:
                    continue
                target = blank[0]
                where = f"{iso3} {target['name']} {field}"
                # An adapter's gap can say that no figure, its own or a
                # difference, fits the polygon: Maguindanao's religion once the
                # ARMM it sits in carried a count of the region's own ground.
                if target[field].get("not_this_ground"):
                    refused.append(f"{where}: its own gap says no figure fits this polygon")
                    continue
                why, shares = residual(parent, known, target, field, iso3)
                if why or not shares:
                    refused.append(f"{where}: {why or 'nothing left over'}")
                    said = RESIDUAL_REFUSED_NOTES.get((iso3, target.get("name"), field))
                    if said and not target[field].get("note"):
                        target[field] = gap(target[field]["status"], said)
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
# A source row the name matcher would put on a shape it does not describe,
# keyed by the row's Wikidata item, with what the row is instead. Wikidata's
# first level for Ivory Coast is still the nineteen regions of 1997, and the
# map draws the fourteen districts of 2011. Three old regions share a name
# with a district and not its ground, and each was joined by name alone.
NOT_THIS_SHAPE: dict[tuple[str, str], str] = {
    ("CIV", "Q639491"): ("the Lagunes region of 1997-2011, which held Abidjan: its "
                         "5,336,658 people and its capital are mostly Abidjan's, and "
                         "the Lagunes District of 2011 leaves Abidjan out"),
    ("CIV", "Q839083"): ("Marahoué Region, one of the two regions Sassandra-Marahoué "
                         "District holds; its 981,179 people and Bouaflé leave out "
                         "Haut-Sassandra and the district's capital, Daloa"),
    ("CIV", "Q845706"): ("the Lacs region of 1997-2011, whose capital Yamoussoukro is "
                         "now an autonomous district of its own; the Lacs District's "
                         "capital is Dimbokro"),
    # Peru's boundary file draws Metropolitan Lima as a shape of its own, and
    # "Lima" as the rest of the department around it.
    ("PER", "Q211795"): ("the Department of Lima with Metropolitan Lima inside it: "
                         "11,595,510 people, most of them in the metropolitan "
                         "province the map draws separately"),
    # "Danau Sentarum National Park" reached the shape called "Danau" on its
    # first word. The park is in West Kalimantan; the shape is four lakes on
    # Sumatra and Sulawesi, and took the park's point on Borneo.
    ("IDN", "Q239494"): ("Danau Sentarum National Park in West Kalimantan, a park "
                         "and not any of the four lakes on Sumatra and Sulawesi "
                         "the shape called Danau draws"),
    # Portugal's boundary file draws two polygons named Oliveira de Frades: a
    # 144 km2 one under Aveiro, the municipality (145 km2), which
    # portugal_census binds by id, and a 21 km2 one under Viseu, wedged
    # between Tondela, Vouzela and Agueda, which is not the municipality and
    # whose identity could not be established. By name and parent the
    # Wikidata item took the second, and the municipality was shown twice.
    ("PRT", "Q861584"): ("the municipality of Oliveira de Frades, whose census count "
                         "is on the 144 km2 polygon of that name; this 21 km2 polygon "
                         "is not the municipality"),
    # Russia's okrugs of today on the polygons of the units they were made
    # from. Each item's own series shows the merger's jump, and the boundary
    # file draws only part of the okrug -- the rest is a polygon of its own.
    # russia_municipal refuses the census's count on these polygons for the
    # same reason.
    ("RUS", "Q4145666"): ("the Kolomna urban okrug of today, the city with the "
                          "Kolomensky District (2017) and Ozyory (2020): 144,125 people "
                          "in 2017, 217,703 in 2021 and 215,146 in 2025; the polygon "
                          "draws the city, and the district and Ozyory are polygons of "
                          "their own"),
    ("RUS", "Q1773432"): ("the Pushkinsky urban okrug of 2019, the district with "
                          "Ivanteyevka and Krasnoarmeysk: 178,536 people in 2020 and "
                          "299,385 in 2021; the map draws both towns as polygons of "
                          "their own"),
    ("RUS", "Q1254433"): ("the Georgiyevsky urban okrug of 2017, the district with the "
                          "town of Georgiyevsk: 100,518 people in 2017 and 167,262 in "
                          "2018; the map draws the town as a polygon of its own"),
    ("RUS", "Q27477659"): ("the Serpukhov urban okrug of today, the city with the "
                           "Serpukhovsky District and more: 124,897 people in 2019, "
                           "181,030 in 2021 and 239,430 in 2025; the polygon draws the "
                           "city, and the district is a polygon of its own"),
    ("RUS", "Q27532886"): ("the Novozybkov urban okrug of 2019, the town with the "
                           "Novozybkovsky District (49,379 people in 2021, 38,680 of "
                           "them in the town); the district is a polygon of its own"),
    ("RUS", "Q27572811"): ("the Manturovo urban okrug of 2019, the town with the rural "
                           "part of the Manturovsky District (15,452 people in 2018, "
                           "18,863 in 2019); the district is a polygon of its own"),
    ("RUS", "Q1653098"): ("the Manturovsky District of Kostroma Oblast, merged into the "
                          "Manturovo okrug in 2019: 3,852 people in 2018, and 14,900 in "
                          "2025 for the okrug, town and all, which the map draws as a "
                          "polygon of its own"),
    # Chechnya's districts after their 2019-2020 redrawing, on the older
    # outlines the boundary file draws. Each item's own series shows the change
    # (Groznensky fell from 132,719 to 76,808 between 2019 and 2020); the census
    # files Starye Atagi, Kulary, Chechen-Aul and Bamut in districts other than
    # the polygons that hold them. russia_municipal refuses the census's counts
    # on these polygons for the same reason.
    ("RUS", "Q1027864"): ("the Groznensky District after 2019-2020, without Starye "
                          "Atagi, Kulary, Chechen-Aul and other villages (132,719 "
                          "people in 2019, 76,808 in 2020, 86,700 in 2024); the polygon "
                          "is the district of before"),
    ("RUS", "Q1026606"): ("the Urus-Martanovsky District after it took in Starye Atagi "
                          "in 2019-2020 (144,708 people in 2019, 159,518 in 2020, "
                          "171,261 in 2024); the polygon is the district of before, and "
                          "Starye Atagi lies in the map's Groznensky District"),
    ("RUS", "Q482011"): ("the Achkhoy-Martanovsky District after 2019-2020, with Kulary "
                         "and without Bamut (99,296 people in 2024); the polygon is the "
                         "district of before"),
    ("RUS", "Q856394"): ("the Sernovodsky District of 2020, the Sunzhensky District "
                         "renamed with Bamut added (23,040 people in 2019, 28,772 in "
                         "2020, 27,505 in 2025); the polygon is the Sunzhensky District "
                         "of before, and Bamut lies in the map's Achkhoy-Martanovsky "
                         "District"),
    # Ukraine's pre-2020 raion polygons that ukraine_raion refuses, joined by
    # name to items whose figure describes another area: the Zviahel raion of
    # 2020, four cities, and raions whose polygon the 2001 census's own
    # outlines (the Census Bureau's) show to be largely something else -- the
    # reason is the one ukraine_raion writes on the polygon. Sevastopol's
    # districts stay: their polygons are refused for the census's grain only.
    ("UKR", "Q2994010"): ("the Amvrosiivka raion of before 2020 (44,379 people in "
                          "2017), whose figure does not describe this polygon: 42% of "
                          "the area the 2001 census counts as Makiivka (Miskrada) lies "
                          "in this polygon, and that area's people are drawn in no "
                          "polygon by a majority of its area"),
    ("UKR", "Q2216511"): ("the Antratsyt raion of before 2020 (30,070 people), whose "
                          "figure does not describe this polygon: 45% of the area the "
                          "2001 census counts as Snizhne (Miskrada) lies in this "
                          "polygon, and that area's people are counted with "
                          "'Shakhtarsk'"),
    ("UKR", "Q2883763"): ("the Borodianka raion of before 2020 (57,301 people in 2019), "
                          "whose figure does not describe this polygon: only 57% of the "
                          "area the 2001 census counts as Irpin (Miskrada) lies in this "
                          "polygon"),
    ("UKR", "Q161984"): ("the city of Fastiv (45,907 people in 2019), not the Fastiv "
                         "raion of before 2020 that the polygon is named for"),
    ("UKR", "Q2599695"): ("the Horodok raion of before 2020 (68,544 people in 2019), "
                          "whose figure does not describe this polygon: the boundary "
                          "file names this polygon for Horodotskyi Raion (Lvivska "
                          "Oblast), but only 35% of the area the 2001 census counts as "
                          "that raion lies in it and 40% in 'Sambir'"),
    ("UKR", "Q2996142"): ("the Illintsi raion of before 2020 (37,059 people in 2017), "
                          "whose figure does not describe this polygon: 49% of the area "
                          "the 2001 census counts as Haisynskyi Raion lies in this "
                          "polygon, and that area's people are placed in no polygon: "
                          "the map's name for it and its outline disagree"),
    ("UKR", "Q2996222"): ("the Kaharlyk raion of before 2020 (32,814 people in 2019), "
                          "whose figure does not describe this polygon: only 65% of the "
                          "area the 2001 census counts as M. Rzhyshchiv lies in this "
                          "polygon"),
    ("UKR", "Q1995820"): ("the Kamianka raion of before 2020 (25,933 people in 2019), "
                          "whose figure does not describe this polygon: the boundary "
                          "file names this polygon for Kamianskyi Raion, but only 41% "
                          "of the area the 2001 census counts as that raion lies in it "
                          "and 44% in 'Smila'"),
    ("UKR", "Q2494465"): ("the Khoroshiv raion of before 2020 (34,553 people in 2018), "
                          "whose figure does not describe this polygon: the boundary "
                          "file names this polygon for Volodarsko-Volynskyi Raion, but "
                          "only 46% of the area the 2001 census counts as that raion "
                          "lies in it and 51% in 'Pulyny'"),
    ("UKR", "Q2996158"): ("the Kryzhopil raion of before 2020 (32,976 people in 2018), "
                          "whose figure does not describe this polygon: 52% of the area "
                          "the 2001 census counts as Pishchanskyi Raion lies in this "
                          "polygon, and that area's people are placed in no polygon: "
                          "the map's name for it and its outline disagree"),
    ("UKR", "Q2996231"): ("the Kyiv-Sviatoshyn raion of before 2020 (198,674 people in "
                          "2019), whose figure does not describe this polygon: 43% of "
                          "the area the 2001 census counts as Irpin (Miskrada) lies in "
                          "this polygon, and that area's people are counted with "
                          "'Borodianka'"),
    ("UKR", "Q2620746"): ("the Luhyny raion of before 2020 (16,321 people in 2018), "
                          "whose figure does not describe this polygon: the boundary "
                          "file names this polygon for Luhynskyi Raion, but only 40% of "
                          "the area the 2001 census counts as that raion lies in it and "
                          "52% in 'Yemilchyne'"),
    ("UKR", "Q2628102"): ("the Manhush raion of before 2020 (26,510 people in 2017), "
                          "whose figure does not describe this polygon: only 68% of the "
                          "area the 2001 census counts as Mariupol (Miskrada) lies in "
                          "this polygon"),
    ("UKR", "Q2994031"): ("the Marinka raion of before 2020 (90,434 people in 2001), "
                          "whose figure does not describe this polygon: only 50% of the "
                          "area the 2001 census counts as Selidove (Miskrada) lies in "
                          "this polygon"),
    ("UKR", "Q2992440"): ("the Mlyniv raion of before 2020 (37,579 people), whose "
                          "figure does not describe this polygon: 40% of the area the "
                          "2001 census counts as M. Dubno lies in this polygon, and "
                          "that area's people are counted with 'Dubno'"),
    ("UKR", "Q2996182"): ("the Murovani Kurylivtsi raion of before 2020 (24,919 people "
                          "in 2018), whose figure does not describe this polygon: 48% "
                          "of the area the 2001 census counts as M. Novodnistrovsk lies "
                          "in this polygon, and that area's people are counted with "
                          "'Mohyliv-Podilskyi'"),
    ("UKR", "Q582804"): ("the Nosivka raion of before 2020 (28,814 people in 2017), "
                         "whose figure does not describe this polygon: the boundary "
                         "file names this polygon for Nosivskyi Raion, but only 33% of "
                         "the area the 2001 census counts as that raion lies in it and "
                         "34% in 'Kozelets'"),
    ("UKR", "Q1011303"): ("the city of Obukhiv (33,204 people in 2019), not the Obukhiv "
                          "raion of before 2020 that the polygon is named for"),
    ("UKR", "Q2639686"): ("the Oleshky raion of before 2020 (70,367 people in 2019), "
                          "whose figure does not describe this polygon: only 52% of the "
                          "area the 2001 census counts as Nova Kakhovka (Miskrada) lies "
                          "in this polygon"),
    ("UKR", "Q2216338"): ("the Perevalsk raion of before 2020 (69,738 people), whose "
                          "figure does not describe this polygon: only 63% of the area "
                          "the 2001 census counts as Krasnyi Luch (Miskrada) lies in "
                          "this polygon"),
    ("UKR", "Q1728636"): ("the Piatykhatky raion of before 2020 (44,575 people in "
                          "2018), whose figure does not describe this polygon: 36% of "
                          "the area the 2001 census counts as M. Vilnohirsk lies in "
                          "this polygon, and that area's people are counted with "
                          "'Verkhnodniprovsk'"),
    ("UKR", "Q2619410"): ("the Pishchanka raion of before 2020 (20,678 people in 2018), "
                          "whose figure does not describe this polygon: the boundary "
                          "file names this polygon for Pishchanskyi Raion, but only 42% "
                          "of the area the 2001 census counts as that raion lies in it "
                          "and 52% in 'Kryzhopil'"),
    ("UKR", "Q2620082"): ("the Pulyny raion of before 2020 (22,784 people in 2018), "
                          "whose figure does not describe this polygon: 51% of the area "
                          "the 2001 census counts as Volodarsko-Volynskyi Raion lies in "
                          "this polygon, and that area's people are placed in no "
                          "polygon: the map's name for it and its outline disagree"),
    ("UKR", "Q2997697"): ("the Rokytne raion of before 2020 (26,153 people in 2019), "
                          "whose figure does not describe this polygon: the boundary "
                          "file names this polygon for Rokytnianskyi Raion, but only "
                          "41% of the area the 2001 census counts as that raion lies in "
                          "it and 58% in 'Bila Tserkva'"),
    ("UKR", "Q156593"): ("the city of Sambir (34,444 people in 2021), not the Sambir "
                         "raion of before 2020 that the polygon is named for"),
    ("UKR", "Q2627813"): ("the Shakhtarsk raion of before 2020 (18,952 people in 2019), "
                          "whose figure does not describe this polygon: only 62% of the "
                          "area the 2001 census counts as Horlivka (Miskrada) lies in "
                          "this polygon"),
    ("UKR", "Q2996242"): ("the Skvyra raion of before 2020 (36,328 people in 2019), "
                          "whose figure does not describe this polygon: 44% of the area "
                          "the 2001 census counts as M. Bila Tserkva lies in this "
                          "polygon, and that area's people are counted with 'Bila "
                          "Tserkva'"),
    ("UKR", "Q2216840"): ("the Slovianoserbsk raion of before 2020 (53,784 people), "
                          "whose figure does not describe this polygon: only 59% of the "
                          "area the 2001 census counts as Luhansk (Miskrada) lies in "
                          "this polygon"),
    ("UKR", "Q2216649"): ("the Stanytsia-Luhanska raion of before 2020 (49,759 people), "
                          "whose figure does not describe this polygon: 31% of the area "
                          "the 2001 census counts as Luhansk (Miskrada) lies in this "
                          "polygon, and that area's people are counted with "
                          "'Slovianoserbsk'"),
    ("UKR", "Q2997764"): ("the Teplyk raion of before 2020 (27,818 people in 2018), "
                          "whose figure does not describe this polygon: the boundary "
                          "file names this polygon for Teplytskyi Raion, but only 19% "
                          "of the area the 2001 census counts as that raion lies in it "
                          "and 73% in 'Haisyn'"),
    ("UKR", "Q2639671"): ("the Tomakivka raion of before 2020 (24,658 people in 2018), "
                          "whose figure does not describe this polygon: only 60% of the "
                          "area the 2001 census counts as Marhanets (Miskrada) lies in "
                          "this polygon"),
    ("UKR", "Q997421"): ("the city of Vasylkiv (37,696 people in 2019), not the "
                         "Vasylkiv raion of before 2020 that the polygon is named for"),
    ("UKR", "Q2637060"): ("the Verkhnodniprovsk raion of before 2020 (52,858 people in "
                          "2018), whose figure does not describe this polygon: only 61% "
                          "of the area the 2001 census counts as M. Vilnohirsk lies in "
                          "this polygon"),
    ("UKR", "Q2216204"): ("the Zmiiv raion of before 2020 (72,587 people), whose figure "
                          "does not describe this polygon: 100% of the area the 2001 "
                          "census counts as Chuhuiv (Miskrada) lies in this polygon, "
                          "and that area's people are drawn by the boundary file "
                          "outside the polygon of the raion it is the seat of (Zmiiv "
                          "100%)"),
    ("UKR", "Q102451616"): ("the Zviahel Raion established in 2020 by merging the "
                            "Novohrad-Volynskyi raion with its neighbours (164,972 "
                            "people in 2022); the polygon is the Novohrad-Volynskyi "
                            "raion of before"),
    # Armenia's second level is the raions of before the 1995 reform into
    # marzes. The items joined to them by name are the municipalities formed
    # by consolidating communities from 2016 on, which Wikidata describes as
    # such: another unit, whose figure does not describe the raion's polygon.
    # armenia.py writes each raion as a gap that says why.
    ("ARM", "Q138827280"): ("Akhuryan Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (41,546 people in "
                            "2011); the polygon is the Akhuryan raion of before the "
                            "1995 reform, another unit"),
    ("ARM", "Q138827356"): ("Amasia Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (6,306 people in "
                            "2011); the polygon is the Amasia raion of before the 1995 "
                            "reform, another unit"),
    ("ARM", "Q65225951"): ("Ani Municipality, one of the municipalities formed by "
                           "consolidating communities from 2016 on (18,958 people in "
                           "2011); the polygon is the Ani raion of before the 1995 "
                           "reform, another unit"),
    ("ARM", "Q138679185"): ("Ararat Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (41,725 people in "
                            "2011); the polygon is the Ararat raion of before the 1995 "
                            "reform, another unit"),
    ("ARM", "Q138682414"): ("Armavir Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (51,974 people in "
                            "2011); the polygon is the Armavir raion of before the 1995 "
                            "reform, another unit"),
    ("ARM", "Q138679138"): ("Artashat Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (91,182 people in "
                            "2011); the polygon is the Artashat raion of before the "
                            "1995 reform, another unit"),
    ("ARM", "Q138828005"): ("Artik Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (54,065 people in "
                            "2011); the polygon is the Artik raion of before the 1995 "
                            "reform, another unit"),
    ("ARM", "Q138666250"): ("Ashtarak Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (63,926 people in "
                            "2011); the polygon is the Ashtarak raion of before the "
                            "1995 reform, another unit"),
    ("ARM", "Q138684251"): ("Baghramyan Municipality, one of the municipalities formed "
                            "by consolidating communities from 2016 on (16,255 people "
                            "in 2011); the polygon is the Baghramyan raion of before "
                            "the 1995 reform, another unit"),
    ("ARM", "Q138701168"): ("Gavar Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (52,687 people in "
                            "2011); the polygon is the Gavar raion of before the 1995 "
                            "reform, another unit"),
    ("ARM", "Q48862719"): ("Goris Municipality, one of the municipalities formed by "
                           "consolidating communities from 2016 on (29,319 people in "
                           "2011); the polygon is the Goris raion of before the 1995 "
                           "reform, another unit"),
    ("ARM", "Q138710451"): ("Hrazdan Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (52,283 people in "
                            "2022); the polygon is the Hrazdan raion of before the 1995 "
                            "reform, another unit"),
    ("ARM", "Q55075050"): ("Kapan Municipality, one of the municipalities formed by "
                           "consolidating communities from 2016 on (49,788 people in "
                           "2011); the polygon is the Kapan raion of before the 1995 "
                           "reform, another unit"),
    ("ARM", "Q138701606"): ("Martuni Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (90,224 people in "
                            "2011); the polygon is the Martuni raion of before the 1995 "
                            "reform, another unit"),
    ("ARM", "Q138679271"): ("Masis Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (78,442 people in "
                            "2011); the polygon is the Masis raion of before the 1995 "
                            "reform, another unit"),
    ("ARM", "Q55394256"): ("Meghri Municipality, one of the municipalities formed by "
                           "consolidating communities from 2016 on (11,377 people in "
                           "2011); the polygon is the Meghri raion of before the 1995 "
                           "reform, another unit"),
    ("ARM", "Q138748713"): ("Nairi Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (31,590 people in "
                            "2011); the polygon is the Nairi raion of before the 1995 "
                            "reform, another unit"),
    ("ARM", "Q138666528"): ("Noyemberyan Municipality, one of the municipalities formed "
                            "by consolidating communities from 2016 on (29,346 people "
                            "in 2011); the polygon is the Noyemberyan raion of before "
                            "the 1995 reform, another unit"),
    ("ARM", "Q138702189"): ("Sevan Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (39,776 people in "
                            "2011); the polygon is the Sevan raion of before the 1995 "
                            "reform, another unit"),
    ("ARM", "Q50495586"): ("Sisian Municipality, one of the municipalities formed by "
                           "consolidating communities from 2016 on (30,265 people in "
                           "2011); the polygon is the Sisian raion of before the 1995 "
                           "reform, another unit"),
    ("ARM", "Q138794219"): ("Spitak Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (38,037 people in "
                            "2022); the polygon is the Spitak raion of before the 1995 "
                            "reform, another unit"),
    ("ARM", "Q65226139"): ("Stepanavan Municipality, one of the municipalities formed "
                           "by consolidating communities from 2016 on (14,557 people in "
                           "2011); the polygon is the Stepanavan raion of before the "
                           "1995 reform, another unit"),
    ("ARM", "Q138666308"): ("Talin Municipality, one of the municipalities formed by "
                            "consolidating communities from 2016 on (32,472 people in "
                            "2011); the polygon is the Talin raion of before the 1995 "
                            "reform, another unit"),
    ("ARM", "Q65226147"): ("Tashir Municipality, one of the municipalities formed by "
                           "consolidating communities from 2016 on (22,185 people in "
                           "2011); the polygon is the Tashir raion of before the 1995 "
                           "reform, another unit"),
    ("ARM", "Q138690894"): ("Vagharshapat Municipality, one of the municipalities "
                            "formed by consolidating communities from 2016 on (50,031 "
                            "people in 2011); the polygon is the Vagharshapat raion of "
                            "before the 1995 reform, another unit"),
    ("ARM", "Q65226141"): ("Vardenis Municipality, one of the municipalities formed by "
                           "consolidating communities from 2016 on (38,240 people in "
                           "2011); the polygon is the Vardenis raion of before the 1995 "
                           "reform, another unit"),
    ("ARM", "Q48862592"): ("Vayk Municipality, one of the municipalities formed by "
                           "consolidating communities from 2016 on (11,928 people in "
                           "2011); the polygon is the Vayk raion of before the 1995 "
                           "reform, another unit"),
    ("ARM", "Q138666686"): ("Yeghegnadzor Municipality, one of the municipalities "
                            "formed by consolidating communities from 2016 on (16,304 "
                            "people in 2022); the polygon is the Yeghegnadzor raion of "
                            "before the 1995 reform, another unit"),
}

# Figures that reach the right polygon by name and describe other ground,
# keyed by country and polygon id: for each field, the file whose figure is
# refused (None for any file's, where no figure could describe the polygon)
# and the reason the record states instead. Applied after the join, so it
# reaches a figure however it arrived, and nothing falls back in its place:
# the reason is that no figure for this ground has been read. Measured on the
# CGAZ polygons on 10 October 2026:
#   MAR  Laâyoune-Sakia El Hamra is drawn as the 7,789 km2 of the region north
#        of 27°40'N (Tarfaya Province and slivers); Laâyoune, where most of
#        the region's people live, lies south of that line in Western Sahara,
#        which the boundary file draws as a disputed area of its own. "Oued
#        Ed-Dahab Province" is 0.7 km2 of slivers along the same line, and
#        the province's figure is Dakhla's, 1,700 km to the south.
#   UKR  "Leninskyi" is a 2.2 km2 polygon in Sevastopol; Wikidata's 2025
#        figure is the authorities' count for a whole district of the city,
#        which Ukraine's statistics office has not counted since 2001.
#   BWA  "Gaborone" at the second level is 1,296 km2 and holds Tlokweng,
#        Mogoditshane, Ramotswa and Otse besides the city (GeoNames' points);
#        235,884 is the city's.
#   GNQ  Wikidata's item for Riaba is a municipality whose one undated figure,
#        1,071, is the size of the town (GeoNames: 971); the polygon is the
#        district, 379 km2.
#   GHA  OCHA's 2021 row is Savelugu-Nanton, the district before Nanton was
#        made a district of its own in 2018; the map draws Nanton apart, and
#        Wikidata's 2021 figure for Nanton (50,767) stands on it, so the
#        old district's 180,507 counted Nanton's people twice.
#   CHN  "Xianggang", Hong Kong at the second level, is 441 km2 without Hong
#        Kong Island and Lantau (china_census measures it); the SAR's census
#        figures describe all of the SAR's people.
#   BEL  "Brussels Hoofdstedelijk" at the first level is 79.7 km2, of which
#        70.6 km2 lies in the Brussels-Capital Region; the other 91.6 km2 of
#        the region (162.2 km2, drawn whole at the second level as
#        "Brussels") lies inside the polygon drawn for Flanders, and with it
#        the seats of Anderlecht, Schaerbeek, Molenbeek-Saint-Jean, Uccle,
#        Jette, Berchem-Sainte-Agathe, Ganshoren and Koekelberg (GeoNames'
#        points), about half the region's people. Every figure the region
#        publishes -- Eurostat's population, median age and sex ratio, the
#        census's nationalities, the survey's religion and language -- stands
#        on the second-level polygon, and none of them on this one. Belgium's
#        own sums over its three regions then lack this one; the country's
#        published figures stand instead.
#   CPV  Wikidata's undated 30,000 for Tarrafal (Santiago, 115 km2 as drawn)
#        is nearly twice what the municipality's censuses count; the 2021
#        census row (wiki_table_population) it stood in front of shows.
#   BHS  North Abaco's 9,578 (2010) is the census's supervisory district
#        (North Abaco 9,578 + South Abaco 7,646 = Abaco 17,224, census table
#        by island and supervisory district); the polygon is the 189 km2
#        local-government district, and Grand Cay is drawn apart.
NOT_THIS_GROUND: dict[tuple[str, str], dict[str, tuple[str | None, str]]] = {
    ("MAR", "70788906B89532291078161"): {
        "population": (None, (
            "The figure published for the Laâyoune-Sakia El Hamra region, 451,028 "
            "people in 2024, counts mostly the city of Laâyoune, which lies south of "
            "27°40'N in Western Sahara. The boundary file draws Western Sahara as a "
            "separate disputed area, and this polygon is only the 7,789 km² of the "
            "region north of that line, mostly Tarfaya Province, so the region's "
            "count is not this polygon's and no count is published for this part "
            "alone.")),
    },
    ("MAR", "96644757B78111329468616"): {
        "population": (None, (
            "This polygon is 0.7 km² of slivers along 27°40'N. The figure "
            "published for the province of Oued Ed-Dahab, 195,467 people in 2024, "
            "most of them in Dakhla, describes ground south of that line in Western "
            "Sahara, which the boundary file draws as a separate disputed area, so "
            "it is not this polygon's, and no count describes these slivers.")),
    },
    ("UKR", "74538382B30799636343123"): {
        "population": ("wikidata_admin2.json", (
            "This polygon is 2.2 km² of Sevastopol. The 137,952 people given for "
            "the Leninskyi district in 2025 live in a district far larger than "
            "the polygon, and are counted by the authorities that have controlled "
            "the city since 2014, not by Ukraine's statistics office, so the "
            "figure is not this polygon's. The 2001 census counts Sevastopol "
            "whole; the map cuts it into polygons, and the whole city's figures "
            "describe none of them.")),
    },
    ("BWA", "55941954B98371115502172"): {
        "population": ("wikidata_admin2.json", (
            "235,884 (2013) is the city of Gaborone's figure. This polygon is "
            "1,296 km² around the city and also holds Tlokweng, Mogoditshane, "
            "Ramotswa and Otse, so the city's count is not this polygon's, and no "
            "count read describes this ground.")),
    },
    ("GNQ", "11065452B69866248222639"): {
        "population": ("wikidata_admin2.json", (
            "Wikidata's 1,071 for Riaba carries no date and is the size of the "
            "town of Riaba (971 people, by GeoNames). This polygon is the district "
            "of Riaba, 379 km² of southern Bioko, and no figure read describes "
            "it.")),
    },
    ("GHA", "2480657B27215926841583"): {
        "population": ("cod_ps_admin2.json", (
            "The 2021 figure of 180,507 is for Savelugu-Nanton, the district as it "
            "was before Nanton was made a district of its own in 2018. The map "
            "draws Nanton apart, with its own figure, so the old district's count "
            "is not this polygon's, and no figure for Savelugu alone has been "
            "read.")),
    },
    # Barrancominas has been a municipality since 2019, when the former area
    # of Mapiripana was joined to it; OCHA's figure counts both, and the map
    # draws Mapiripana apart with DANE's own 2018 count. The note ends "left
    # out" so DANE's 2018 count for Barrancominas, held behind OCHA's, is
    # shown instead (refuse_not_this_ground -> fall_back).
    ("COL", "7082276B12505915261295"): {
        "population": ("cod_ps_admin2.json", (
            "OCHA's 2025 figure of 9,225 is for Barrancominas as it has stood since "
            "2019, when the former area of Mapiripana was joined to it. The map "
            "draws Mapiripana apart with its own count, so the 2025 figure, which "
            "counts Mapiripana's people as well, is left out.")),
    },
    # The polygon named Sonsonate lies north of the city, where Sonzacate is;
    # the 2024 census counts the two districts on it and the unnamed polygon
    # beside it, and which is which cannot be told. (OCHA's figure comes first
    # in the sentence: RefusedFiguresAreTheFilesFigures checks it is the file's.)
    ("SLV", "79315794B61024232293340"): {
        field: (source, (
            "OCHA's 2024 figure of 81,236 for the municipio of Sonsonate is not "
            "this polygon's. The 2024 census's districts of Sonsonate (72,233) and "
            "Sonzacate (28,226) together count 100,459 people on this polygon and "
            "the unnamed one beside it, but which polygon is which district cannot "
            "be told: this polygon lies north of the city, where Sonzacate is."))
        for field, source in (("population", "cod_ps_admin2.json"),
                              ("median_age", "cod_ps_age.json"),
                              ("sex_ratio", "cod_ps_age.json"))
    },
    # The Bahamas' 2022 census tabulates by its supervisory districts, drawn
    # like the parliamentary constituencies (see wiki_table_population's
    # SUPERVISORY). English Wikipedia's district infoboxes repeat those rows:
    # South Andros' 3,711 is the row that takes in South Andros, Central Andros
    # and Mangrove Cay together (the table prints it so), and North Andros'
    # 4,069 is the supervisory district that also takes in Fresh Creek and
    # Coakley Town, which lie in the local-government district of Central
    # Andros. Neither is the district drawn.
    ("BHS", "57655419B29435673895959"): {
        "population": ("wiki_population_admin1.json", (
            "English Wikipedia's 3,711 for 2022 is the census's figure for South "
            "Andros, Central Andros and Mangrove Cay together, which the census "
            "counts as one supervisory district, so it is not this district's.")),
    },
    ("BHS", "57655419B63159467904865"): {
        "population": ("wiki_population_admin1.json", (
            "English Wikipedia's 4,069 for 2022 is the census's supervisory district "
            "of North Andros, which also takes in Fresh Creek and Coakley Town in the "
            "local-government district of Central Andros, so it is not this "
            "district's.")),
    },
    # The 2010 census's island report prints San Salvador's racial groups only
    # together with Rum Cay's (Table 8.0, "San Salvador & Rum Cay": 1,039
    # people, San Salvador's 940 and Rum Cay's 99), as the religion gaps of
    # both islands already say.
    ("BHS", "57655419B6447054147513"): {
        # Any file's: a composition's file is no longer known when compositions
        # are refused, so a refusal scoped to one never applied.
        "ethnicity": (None, (
            "The 2010 census's report prints San Salvador's racial groups only "
            "together with Rum Cay's (Table 8.0, San Salvador & Rum Cay, 1,039 "
            "people), so the table is not this island's alone.")),
    },
    # The second-level polygon labelled Kyiv is drawn off the city: 983 km2,
    # of which 53% lies inside the city (the first-level polygon, 827 km2)
    # and the rest in Kyiv Oblast around Brovary, whose centre it holds, while
    # 37% of the city lies outside it. The city's 2001 census figures are its
    # ten raions', which are the first-level polygon's ground, not this one.
    ("UKR", "74538382B60890943260132"): {
        field: (None, (
            "This polygon is drawn off the city: about half of it lies outside Kyiv, "
            "in Kyiv Oblast around Brovary, and over a third of the city lies outside "
            "it. The city's own figures are shown on Kyiv one level up."))
        for field in ("population", "median_age", "sex_ratio", "language")
    },
    ("CHN", "17275852B66204891178522"): {
        field: (None, (
            "This polygon is part of Hong Kong as the boundary file's second level "
            "draws it ('Xianggang'): about 441 km² of the SAR's 1,110 or so km² of "
            "land, without Hong Kong Island and Lantau. The 2021 census figures "
            "describe the whole SAR, many of whose people live outside this "
            "polygon, so they are not repeated here; they are shown one level up, "
            "for the SAR as a unit, though the boundary file draws that polygon "
            "too as only part of the SAR's land. No census area follows this "
            "polygon's edge."))
        for field in ("population", "median_age", "sex_ratio", "language", "ethnicity")
    },
    ("BEL", "27649430B17719898407236"): {
        field: (None, (
            "This polygon is about half of the Brussels-Capital Region: 70.6 km² "
            "of the region's 162 km² lie in it, and the rest, with Anderlecht, "
            "Schaerbeek, Molenbeek-Saint-Jean, Uccle and Jette, is drawn inside the "
            "polygon for Flanders. The region's figures are shown on the "
            "second-level polygon \"Brussels\", which is the whole region, and "
            "describe more ground and more people than this polygon holds."))
        for field in ("population", "median_age", "sex_ratio",
                      "religion", "language", "ethnicity")
    },
    ("CPV", "35879248B2594883865860"): {
        "population": ("wikidata_admin1.json", (
            "Wikidata's undated 30,000 for Tarrafal is nearly twice what the "
            "municipality's censuses count (18,565 in 2010, 16,620 in 2021), so it "
            "is left out.")),
    },
    ("BHS", "57655419B79428110843392"): {
        "population": ("wiki_population_admin1.json", (
            "The 9,578 given for North Abaco is the 2010 census's count of its "
            "supervisory district of that name, which with South Abaco's 7,646 makes "
            "up all 17,224 people of Abaco and takes in Grand Cay, drawn apart with "
            "its own figure. This polygon is the smaller local-government district, "
            "for which no count has been read, so the figure is left out.")),
    },
}


def refuse_not_this_ground(admin1: dict[str, list[dict[str, Any]]],
                           admin2: dict[str, list[dict[str, Any]]],
                           fields: Sequence[str]) -> list[str]:
    """Put NOT_THIS_GROUND's reasons in place of the figures it refuses.

    Run once for the population after the join, while each figure still says
    which file it came from, and once for the compositions after the
    collection policy, which would otherwise replace the reason with the
    country's. A refusal scoped to one file leaves another file's figure
    standing and lets a figure that file's was held in front of come back
    (fall_back); a refusal of any file's figure writes the reason whatever
    was there. A declared polygon that is not drawn stops the build.
    """
    done: list[str] = []
    for (iso3, shape_id), declared in NOT_THIS_GROUND.items():
        found = [e for table in (admin1, admin2) for e in table.get(iso3, [])
                 if e.get("id") == shape_id]
        if not found:
            raise SystemExit(f"build_entities: NOT_THIS_GROUND names {iso3} shape "
                             f"{shape_id!r}, which the boundary file does not draw")
        for entity in found:
            for field, (source, note) in declared.items():
                if field not in fields:
                    continue
                current = entity.get(field)
                origin = (entity.get("_from") or {}).get(field)
                refused = dict(gap(NOT_AVAILABLE, note), not_this_ground=True)
                if field == "population":
                    # The unit's own count, refused only for this polygon: kept
                    # (as a build flag, never written out) so that a country's
                    # sum can still weigh how much of it this unit is. A reader
                    # that wrote the gap itself hands the count on the same way:
                    # morocco_rgph2024's Laayoune-Sakia El Hamra had displaced
                    # the figure this refusal would have kept, and Morocco's
                    # language went unsummed for want of its 451,028.
                    kept = published(current)
                    if kept is None and isinstance(current, dict):
                        kept = current.get("refused_value")
                    if kept is not None:
                        refused["refused_value"] = kept
                if field == "population" and entity.get("level") == "admin1":
                    # Its divisions do not make the ground the figure was for
                    # either: no sum of them stands in for it.
                    refused["no_child_sum"] = True
                if not is_gap(current) and source is not None and origin != source:
                    log(f"  not this ground: {iso3} {entity.get('name')} {field} "
                        f"kept, from {origin}, not {source}")
                    continue
                entity[field] = refused
                for suffix in SATELLITES:
                    entity.pop(f"{field}{suffix}", None)
                (entity.get("_from") or {}).pop(field, None)
                entity["sources"] = [
                    src for src in entity.get("sources", []) or []
                    if set(str(src.get("field") or "").split("/")) != {field}]
                if is_gap(current):
                    continue
                # Only where the reason says so: it ends "is left out", and the
                # figure the refused one stood in front of is shown instead.
                if source is not None and note.rstrip(".").endswith("left out"):
                    fall_back(entity, refused, field,
                              usable=lambda held, source=source: held.get("file") != source)
                done.append(f"{iso3} {entity.get('name')} {field}")
            # A citation goes with the figures it produced: one naming several
            # fields, every one of them now refused here, cites nothing on the
            # map (Brussels' half polygon kept Eurostat for 'population/median
            # age/sex ratio' after all three were refused).
            gone = {f for f, v in entity.items()
                    if isinstance(v, dict) and v.get("not_this_ground")}
            if gone:
                def cites(src: dict[str, Any]) -> set[str]:
                    return {f.strip().replace(" ", "_")
                            for f in str(src.get("field") or "").split("/") if f.strip()}
                entity["sources"] = [src for src in entity.get("sources", []) or []
                                     if not cites(src) or not cites(src) <= gone]
    return done

# Countries whose boundary file draws their first level one level down: under
# two cohesion regions, Slovenia's second level is its 212 municipalities;
# under five macro-regions, Italy's is its 20 regions; Kosovo's, North
# Macedonia's, Azerbaijan's and Lithuania's are their municipalities and
# districts. Wikidata's first level for each is those same units, and with
# nowhere to land they were lost while the towns named like them were joined
# instead -- 142 of Slovenia's municipalities and 12 of Italy's regions had no
# population. A first-level row that finds no first-level shape here is
# joined one level down, by its own name or alias only: a prefix or
# containment match one level off is two guesses stacked.
#
# Declared, not inferred. Measured on 24 September 2026 across every country,
# the same join elsewhere puts Costa Rica's province of San José on the canton
# of San José, Stockholm County on Stockholm Municipality and Mali's regions of
# 2016 on the cercles they are named after: a unit on its capital's ground.
FIRST_LEVEL_DRAWN_SECOND = frozenset({"SVN", "ITA", "XKX", "MKD", "AZE", "LTU"})

PLACED: dict[tuple[str, str], str] = {
    ("BLR", "Q2280"): "Minsk City",
    ("BLR", "Q192959"): "Minsk",
    # "monastic community of Mount Athos" shares no word with "Agion Oros".
    ("GRC", "Q780149"): "Agion Oros",
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


def claim(claimed: dict[int, set[str]], entity: dict[str, Any], row: dict[str, Any],
          iso3: str, wanted: str) -> None:
    """Record a row's binding to a polygon, refusing a second place on it.

    Two rows on one shape is how one district quietly wears another's
    figures, and that is what this stops. Two rows *about the same place* are
    not that: Transnistria's population comes from the Wikipedia reader and
    its ethnic composition from the Moldova reader, each bound to the same
    polygon by id, and refusing the pair stopped the build over two sources
    agreeing on where Transnistria is. So the second claim is refused only
    where it names a different place from the first -- by its name or any
    alias it declares: INDEC's "La Rioja" declares the boundary file's
    misspelt "La Roja", which another reader's row is named by.
    """
    name = row.get("name") or ""
    names = {name} | {a for a in row.get("aliases") or [] if a}
    # A pin (scripts/fetch_census/pins.py) says which label it expects the
    # polygon to carry. The first claim checks the polygon still carries it --
    # a pin to a relabelled or renumbered polygon is stale -- and the label
    # joins the names a later claim is compared with, so two readers' rows
    # pinned there by the same office code are one place however each spells
    # it: DANE's "San Andrés Sotavento" and OCHA's "San Andrés de Sotavento".
    label = row.get("shape_label")
    if label:
        if id(entity) not in claimed and norm(label) != norm(entity.get("name") or ""):
            raise SystemExit(
                f"{iso3}: {name!r} is pinned to shape {wanted!r} as {label!r}, "
                f"but the boundary file labels it {entity.get('name')!r}; the pin is stale")
        names.add(label)
    held = claimed.get(id(entity))
    if held is not None and not ({norm(n) for n in held} & {norm(n) for n in names}):
        raise SystemExit(
            f"{iso3}: shape {wanted!r} is claimed by {name!r} and by "
            f"{' / '.join(sorted(held))!r}. Two rows on one shape is how one district "
            f"quietly wears another's figures")
    claimed[id(entity)] = (held or set()) | names


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
    own_seats = {row["shape_id"]: row.pop("_seat")
                 for rows in shapes.values() for row in rows if row.get("_seat")}
    log(f"  {len(own_seats)} polygons hold a GeoNames seat drawn for them")
    if "ADM1" in shapes and "ADM2" in shapes:
        link_adm2_parents(shapes["ADM1"], shapes["ADM2"])
        for line in declare_parents(shapes["ADM1"], shapes["ADM2"]):
            log(f"  declared parent: {line}")
        shapes["ADM2"].extend(read_remainders())
        replaced, redrawn = read_redrawn()
        if redrawn:
            shapes["ADM2"] = [shape for shape in shapes["ADM2"]
                              if shape["shape_id"] not in replaced] + redrawn
            log(f"  ADM2: {len(replaced)} polygons redrawn as {len(redrawn)}")
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
    # The Factbook's words for a census's own categories (Brazil's "mixed" is
    # its pardo), applied as the adapter applies them, so a file fetched
    # before the rule was written reads the same as one fetched after.
    from fetch_factbook import census_names
    for profile in country_profiles:
        profile["ethnicity"] = census_names((profile.get("codes") or {}).get("iso3"),
                                            profile.get("ethnicity"))
    countries = primary_country_profiles(country_profiles)
    cities = read_json(PROCESSED / "cities.json", {"by_country": {}, "by_admin1": {}})
    adapters = load_adapters()
    for line in pool_declared_unions(
            adapters, {**SHAPE_IS_UNION_OF, **outline_unions(shapes.get("ADM2", []))}):
        log(f"  union pooled: {line}")
    for line in pool_row_unions(adapters):
        log(f"  union pooled by row: {line}")
    for line in split_declared_rows(adapters):
        log(f"  part of an older unit, given its reason: {line}")
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
            disputed_record(entity, {row["id"]: row for row in country_profiles})
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
                          "this territory -- it is drawn as part of the state that "
                          "administers it. The figures below are still its own.")
        entity["note"] = disputed_outline_note(entity["id"], admin0) or entity["note"]
        entity.setdefault("sources", [])
        admin0.append(entity)

    admin0.sort(key=lambda e: e["name"])
    # Before anything is summed: a country's population is what the sums of
    # its divisions are checked against.
    apply_country_figures(admin0, country_detail)

    # -- admin 1 -------------------------------------------------------------
    admin1_by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    adm1_index: dict[str, dict[str, str]] = defaultdict(dict)
    # Natural Earth's place for a unit is joined by the unit's name; its point
    # is checked against the polygons, and a place that is another unit's is
    # left for GeoNames' placement by point (see natural_earth_elsewhere).
    from shapely.strtree import STRtree
    drawn1 = [s for s in shapes.get("ADM1", []) if s.get("_geom") is not None]
    held_by = (STRtree([s["_geom"] for s in drawn1]), drawn1) if drawn1 else None
    elsewhere: list[str] = []
    for shape in shapes.get("ADM1", []):
        iso3 = shape["group"]
        entity = blank(shape, "admin1", iso3)
        city = cities["by_admin1"].get(f"{iso3}||{norm_city(shape['name'])}")
        why = natural_earth_elsewhere(city, shape, held_by) if city and held_by else None
        if why:
            elsewhere.append(f"{iso3} {shape['name']}: {city['name']}, {why}")
            city = None
        if city:
            entity["largest_settlement"] = city["name"]
            entity["largest_settlement_population"] = measure(city["population"], source=city["source"])
        mark_disputed_or_hint(entity, iso3)
        mark_water(entity, iso3)
        admin1_by_country[iso3].append(entity)
        adm1_index[iso3][norm(shape["name"])] = entity["id"]
    if elsewhere:
        log(f"  {len(elsewhere)} Natural Earth places filed under a first-level unit "
            f"stand in another and are left to GeoNames: " + "; ".join(elsewhere))

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
        if shape.get("remainder"):
            entity["remainder"] = True
            entity["note"] = REMAINDERS[iso3][1]
        if shape.get("redrawn"):
            entity["note"] = shape["redrawn"]
        mark_disputed_or_hint(entity, iso3)
        mark_water(entity, iso3)
        if shape.get("outline"):
            entity["outline"] = shape["outline"]
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
            # Ground no source names: "Salto, outside any municipio" must not
            # take the city of Salto's row by starting with its name.
            if entity.get("remainder"):
                continue
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
        claimed: dict[int, set[str]] = {}
        hit = miss = ambiguous = outside = collided = declared = turned = 0
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
            elsewhere = NOT_THIS_SHAPE.get((iso3, row.get("wikidata") or ""))
            if elsewhere:
                log(f"  {iso3} {row.get('name')}: not joined -- it is {elsewhere}")
                turned += 1
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
                    # An unnamed polygon's label is its id, not a spelling.
                    if label != entity["id"]:
                        row["aliases"] = [*(row.get("aliases") or []), label]
                        # And the label itself is kept where nothing renames it
                        # (``shape_name``): readers find their polygons by the
                        # boundary file's labels, and a reader re-run after a
                        # build that renamed one -- "District of Bardejov" to
                        # "Bardejov" -- no longer found it under either name.
                        entity.setdefault("shape_name", label)
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
                if entity is None and iso3 in FIRST_LEVEL_DRAWN_SECOND:
                    below, kind = match_admin2({**key, "parent_name": None},
                                               a2, a1, a1_exact)
                    if below is not None and kind in ("name", "alias"):
                        entity, how = below, f"{kind}+one level down"
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
            row["_match"] = how
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
                   f"{turned} declared to be other ground" if turned else "",
                   f"{aka} shapes reachable under a declared second name"
                   if aka else ""]
            extra = " (" + ", ".join(w for w in why if w) + ")" if any(why) else ""
            log(f"  {iso3}: adapter rows matched {hit}, unmatched {miss}{extra}")

    # -- figures that reached a polygon whose ground they do not describe ----
    # First, while each figure still says which file it came from.
    for line in refuse_not_this_ground(admin1_by_country, admin2_by_country,
                                       ("population", "median_age", "sex_ratio")):
        log(f"  not this ground: {line}")

    # -- a town's figure on a district --------------------------------------
    # After every adapter, so the parent's population is the one it will
    # keep; before anything sums or weighs by these figures.
    mixtures = settle_outline_mixtures(admin2_by_country)
    if mixtures:
        log(f"  {mixtures} polygons measured as mixtures of constituencies left "
            f"without figures")
    # The most recent figure each unit was offered, where it is the same
    # ground: before the settlement checks, which may refuse it and show the
    # count it displaced again.
    newer, refused_newer = prefer_newer_figures(admin1_by_country, admin2_by_country)
    if newer:
        log(f"  {len(newer)} populations shown from a newer figure than the count "
            f"behind them: " + "; ".join(newer[:6]) + (" ..." if len(newer) > 6 else ""))
    for line in refused_newer:
        log(f"  newer figure not taken for the same ground -- {line}")
    settlements = refuse_settlement_figures(admin1_by_country, admin2_by_country,
                                            read_json(ITEM_CLASSES, {}) or {})
    if settlements:
        log(f"  {settlements} Wikidata district figures left out as a "
            f"settlement's, not the district's")
    historic = refuse_historic_figures(admin2_by_country)
    if historic:
        log(f"  {historic} Wikidata district figures left out as history")
    capitals = refuse_capital_figures(admin1_by_country, admin2_by_country)
    if capitals:
        log(f"  {capitals} Wikidata first-level figures left out as a capital's, "
            f"not the unit's")
    towns = refuse_town_figures(admin1_by_country, admin2_by_country)
    if towns:
        log(f"  {towns} Wikidata district figures left out as a town's, not "
            f"the district's")
    placed_towns = fill_settlements_from_geonames(admin1_by_country, admin2_by_country,
                                                  own_seats)
    if placed_towns:
        log(f"  {placed_towns} largest settlements placed from GeoNames")
    placed_seats = fill_capitals_from_geonames(admin1_by_country, admin2_by_country)
    if placed_seats:
        log(f"  {placed_seats} capitals placed from GeoNames seats")
    fell_back = 0
    for table in (admin1_by_country, admin2_by_country):
        for rows in table.values():
            for entity in rows:
                entity.pop("_from", None)
                entity.pop("_how", None)
                held = entity.pop("_held", None)
                if held and isinstance(entity.get("population"), dict) \
                        and "shown instead" in str(entity["population"].get("note") or ""):
                    fell_back += 1
    if fell_back:
        log(f"  {fell_back} refused figures replaced by the next source's")

    # -- the shape-gap table is a promise, so check it -----------------------
    # Here rather than at declaration time: it is a claim about what the join
    # did, and the join has only just finished.
    check_shape_gaps(admin1_by_country, admin2_by_country)

    # -- collection policy ---------------------------------------------------
    # Last, so an adapter's real value always wins over the national marker.
    policy_hits: dict[str, int] = defaultdict(int)
    kept_reasons = 0
    for table in (admin1_by_country, admin2_by_country):
        for iso3, rows in table.items():
            published_here = fields_published(rows)
            for entity in rows:
                own = own_reasons(entity, published_here)
                kept_reasons += len(own)
                for field in apply_collection_policy(
                        entity, iso3, [f for f in COMPOSITION_FIELDS if f not in own]):
                    policy_hits[f"{iso3}/{field}"] += 1
    if kept_reasons:
        log(f"  {kept_reasons} fields keep their own source's reason over the "
            f"country's policy, the field being published for the unit's neighbours")
    if policy_hits:
        total = sum(policy_hits.values())
        top = sorted(policy_hits.items(), key=lambda kv: -kv[1])[:8]
        log(f"  collection policy marked {total} subnational fields with a "
            f"declared gap and its reason: "
            + ", ".join(f"{k} {v}" for k, v in top))
    # The compositions a polygon must not carry, after the policy so the
    # polygon's own reason is the one it gives.
    for line in refuse_not_this_ground(admin1_by_country, admin2_by_country,
                                       ROLLUP_FIELDS):
        log(f"  not this ground: {line}")

    # -- sum parents from children -------------------------------------------
    # After the policy, so "not collected" still wins: a country that does not
    # ask the question has no children to sum, and must not be given a figure by
    # a later pass that only looks at arithmetic.
    roll_up_parents(admin1_by_country, admin2_by_country)
    # After the compositions are summed, so a sum is never their control.
    summed_up = fill_parent_populations(admin1_by_country, admin2_by_country)
    if summed_up:
        log(f"  {len(summed_up)} first-level populations filled from all their "
            f"divisions: " + ", ".join(summed_up[:12])
            + (" ..." if len(summed_up) > 12 else ""))
    # Before the country sums, which read the first level's populations; the
    # figures the units carry for themselves are kept for the country's gate
    # (mark_restated_since, below).
    own_figures = own_population_figures(admin1_by_country)
    restated = restate_encyclopaedia_parents(admin1_by_country, admin2_by_country,
                                             counts=True)
    if restated:
        log(f"  {len(restated)} first-level populations replaced by their divisions' "
            f"newer one-source sum: " + ", ".join(restated[:10])
            + (" ..." if len(restated) > 10 else ""))
    remaining = fill_remainders(admin1_by_country, admin2_by_country)
    if remaining:
        log(f"  {len(remaining)} remainders given their parent's count less its "
            f"divisions': " + ", ".join(remaining))
    twinned = fill_same_polygons(admin1_by_country, admin2_by_country)
    if twinned:
        log(f"  {twinned} second-level fields filled from the same polygon "
            f"drawn a level up")
    # Straight after, and before anything weighs GeoNames' places against a
    # unit's population: a parent's only division on the same ground is the
    # same people, and takes the parent's figures.
    pairs = sole_children(admin1_by_country, admin2_by_country)
    sole, not_sole = fill_sole_children(
        admin1_by_country, admin2_by_country,
        measure_sole_children(pairs, shapes) if "ADM2" in shapes else {},
        code_hierarchy())
    if sole:
        log(f"  {len(sole)} fields of a parent's only division filled from the "
            f"parent: " + ", ".join(sole))
    for line in not_sole:
        log(f"  not filled from its parent -- {line}")
    for line in note_undrawn_parts(admin1_by_country, admin2_by_country):
        log(f"  undrawn part of a first-level count: {line}")
    # After every pass that sets a unit's population, so GeoNames' refusals
    # are weighed against the figure each record is written with.
    named, restated = settle_geonames_spans(admin1_by_country, admin2_by_country)
    if named or restated:
        log(f"  GeoNames places weighed again against final populations: {named} "
            f"named, {restated} reasons restated")
    # And the places that were named, for the same reason.
    unnamed, unfigured = settle_settlement_figures(admin1_by_country, admin2_by_country)
    if unnamed or unfigured:
        log(f"  largest settlements larger than their unit: {unnamed} no longer "
            f"named, {unfigured} named without their figure")
    urban = note_urban_area_figures(admin1_by_country)
    if urban:
        log(f"  {urban} first-level settlement figures said to be Natural Earth's "
            f"urban area")
    # After the level below, so a first-level unit that was itself summed can
    # carry into its country -- and so the country's note counts the divisions
    # as they finally stand rather than as they arrived.
    check_no_stale_country_declaration(admin0, admin1_by_country)
    # A first-level figure restated from its divisions since then is shown,
    # but the country's gate weighs the unit's own (control_population).
    flagged = mark_restated_since(admin1_by_country, own_figures)
    if flagged:
        log(f"  {len(flagged)} first-level populations restated from their divisions; "
            f"the country sums are gated on the units' own figures")
    roll_up_countries(admin0, admin1_by_country)

    # Last, so a curated country row is the last word on the field it names.
    apply_country_detail(admin0, country_detail)
    # And then the reasons a country was not summed, after the curated notes
    # that would otherwise replace them.
    unsummed = note_country_not_summed(admin0)
    if unsummed:
        log(f"  {len(unsummed)} country notes say why the first level is not added "
            f"up: " + ", ".join(unsummed))
    # A country with no figure whose one unit is the whole country.
    for line in country_from_sole_unit(admin0, admin1_by_country):
        log(f"  country population from its one first-level unit: {line}")

    # -- derived values ------------------------------------------------------
    # After the country row is final and before the bare fields are explained:
    # these are gaps that carry a guess, and say_why_empty leaves a gap with a
    # note alone. Nothing here rolls up, because an estimate is not a list.
    inherited = inherit_single_unit(admin0, admin1_by_country, admin2_by_country)
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

    # -- populations: what an empty one and a disagreeing one mean -----------
    # After every pass that sets a population, so each sentence describes the
    # figures the reader is shown.
    not_taken = say_newer_not_taken(admin1_by_country, admin2_by_country)
    if not_taken:
        log(f"  {not_taken} units say why a newer figure they were offered is not shown")
    stated = state_population_gaps(admin0, admin1_by_country, admin2_by_country)
    if stated:
        log(f"  {len(stated)} empty populations given their reason: " + ", ".join(stated))
    gaps_said = note_population_gaps(admin0, admin1_by_country, admin2_by_country)
    if gaps_said:
        log(f"  {len(gaps_said)} populations far from their divisions' sum say what "
            f"the divisions add up to: " + "; ".join(gaps_said[:8])
            + (" ..." if len(gaps_said) > 8 else ""))

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
    # After the reasons are written, since it reads them.
    answered = sum(drop_answered_hint(entity)
                   for table in (admin1_by_country, admin2_by_country)
                   for rows in table.values() for entity in rows)
    if answered:
        log(f"  {answered} adapter hints taken off units whose every empty "
            f"field already says why")

    # Last check before writing: every pass that could have filled a field
    # has run, so a lake that is still water here stays water on the map.
    check_water_shapes(admin1_by_country, admin2_by_country)
    # Nothing reads the adapters' instructions to the build after this.
    flags = sum(drop_build_flags(entity) for entity in admin0) + sum(
        drop_build_flags(entity) for table in (admin1_by_country, admin2_by_country)
        for rows in table.values() for entity in rows)
    if flags:
        log(f"  {flags} build flags taken off the values before writing")
    reworded = sum(plain_notes(entity) for table in (admin1_by_country, admin2_by_country)
                   for rows in table.values() for entity in rows)
    if reworded:
        log(f"  {reworded} coded reasons said in plain words")
    plain = sum(plain_record(entity) for entity in admin0) + sum(
        plain_record(entity) for table in (admin1_by_country, admin2_by_country)
        for rows in table.values() for entity in rows)
    if plain:
        log(f"  {plain} notes, reasons and licences put in plain words")
    tidied = sum(tidy_citations(entity) for entity in admin0) + sum(
        tidy_citations(entity) for table in (admin1_by_country, admin2_by_country)
        for rows in table.values() for entity in rows)
    if tidied:
        log(f"  {tidied} citations narrowed to what they cite, merged or dropped")
    converted = one_sex_ratio_unit(admin0, admin1_by_country, admin2_by_country)
    if converted:
        log(f"  {converted} sex ratios put in males per 100 females")
    # On the records as they are written: no parent far from its divisions'
    # sum without a sentence saying what they add up to.
    check_population_gaps_said(admin0, admin1_by_country, admin2_by_country)

    # -- write ---------------------------------------------------------------
    out = args.out
    write_json(out / "admin0.json", admin0, compact=True)
    written: set[Path] = set()
    for level, by_country in (("admin1", admin1_by_country), ("admin2", admin2_by_country)):
        for iso3, rows in sorted(by_country.items()):
            rows.sort(key=lambda e: e["name"])
            path = shard_path(level, iso3, out)
            write_json(path, rows, compact=True)
            written.add(path)
    # A shard this run did not write is stale -- a country no longer drawn at
    # that level, or a file under an old name ("GTM.json", which a content
    # blocker refused; see common.SHARD_SUFFIX) -- and would still be served.
    for level in ("admin1", "admin2"):
        for path in sorted((out / level).glob("*.json")):
            if path not in written:
                path.unlink()

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
                ],
                # The disagreement between a parent and its divisions' sum past
                # which the build wrote a sentence (note_population_gaps), so a
                # check of site/data knows the data was built to that rule.
                "rollup_gap": check_rollups.GAP}, compact=True)

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
