"""Shared helpers for the DemographicMap ETL pipeline.

Every fetch_* script writes *one JSON record per entity* with explicit gap
markers, so a missing value is always distinguishable from a value of zero.
See ``docs/SCHEMA.md`` for the full record contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
CURATED = DATA / "curated"
TILES = DATA / "tiles"

USER_AGENT = (
    "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap) "
    "python-urllib"
)

# ---------------------------------------------------------------------------
# Gap semantics.  The editorial rule from the plan: never let "we did not fetch
# it" look like "the country does not collect it".
# ---------------------------------------------------------------------------
NOT_COLLECTED = "not_collected"   # country legally/administratively never gathers it
NOT_AVAILABLE = "not_available"   # exists somewhere, but not in this build
NOT_APPLICABLE = "not_applicable"  # meaningless for this entity (e.g. capital of a county)
# An estimate is a gap that carries a guess. Nothing has been read for the
# unit; what is here follows from figures read elsewhere, and the status says
# by what step. It sits among the gap statuses on purpose: every consumer
# that asks "is there a real value" -- the choropleth, the parent sums, the
# group index, the filter counts -- must answer no, and does, because is_gap
# says so. Only code that asks for the estimate by name gets it.
DERIVED = "derived"     # follows from published figures by arithmetic or geometry alone
MODELLED = "modelled"   # follows from published figures under a stated assumption

GAP_STATUSES = {NOT_COLLECTED, NOT_AVAILABLE, NOT_APPLICABLE, DERIVED, MODELLED}
ESTIMATE_STATUSES = {DERIVED, MODELLED}


def gap(status: str, note: str | None = None) -> dict[str, Any]:
    """Build an explicit gap marker instead of a bare ``null``."""
    if status not in GAP_STATUSES:
        raise ValueError(f"unknown gap status {status!r}")
    out: dict[str, Any] = {"status": status}
    if note:
        out["note"] = note
    return out


def is_gap(value: Any) -> bool:
    return value is None or (isinstance(value, dict) and value.get("status") in GAP_STATUSES)


def is_estimate(value: Any) -> bool:
    """A gap that carries a guess: derived or modelled, never read."""
    return isinstance(value, dict) and value.get("status") in ESTIMATE_STATUSES


def estimate(status: str, shares: Iterable[dict[str, Any]], *, method: str,
             inputs: Iterable[str], note: str) -> dict[str, Any]:
    """An estimate, built the one way that makes it recognisable everywhere.

    The shares go under ``estimate`` and not under the field's own shape, so
    no reader that expects a list finds one. The method names the step that
    produced it, the inputs name the records it was produced from, and the
    note is what the panel prints: it must say that nothing was read for this
    unit and that the figure is not evidence of what any census says.
    """
    if status not in ESTIMATE_STATUSES:
        raise ValueError(f"not an estimate status: {status!r}")
    if not note:
        raise ValueError("an estimate must say what it is")
    rows = [{"group": row["group"], "pct": row["pct"]} for row in shares
            if isinstance(row, dict) and row.get("group") and row.get("pct") is not None]
    if not rows:
        raise ValueError("an estimate must carry shares")
    return {"status": status, "estimate": rows, "method": method,
            "inputs": list(inputs), "note": note}


def dated(value: Any, year: int | None) -> int | None:
    """``year``, where there is a figure for it to describe.

    An adapter reads one census or one survey round, so the year is a constant
    it already knows; what it must not do is print that constant beside a gap.
    Two things go wrong when it does. A panel reading "not available -- 2021"
    claims a measurement nobody took. And the stamp outlives the value:
    ``merge_adapter`` lets a gap fall through to whatever the record already
    held, so a year travelling beside that gap would land on another source's
    figures and date them wrongly -- Thailand's fault, one level down.

    Returning None rather than omitting the key is what makes this one
    expression at the call site: ``record()`` drops a None field, so
    ``fields[f"{field}_year"] = dated(fields[field], YEAR)`` says the whole
    rule in a line.
    """
    return year if isinstance(value, list) and value else None


def measure(value: Any, *, year: Any = None, source: str | None = None, unit: str | None = None,
            **extra: Any) -> dict[str, Any] | None:
    """A value carrying its provenance.  Returns ``None`` when value is None."""
    if value is None:
        return None
    out: dict[str, Any] = {"value": value}
    if unit:
        out["unit"] = unit
    if year is not None:
        out["year"] = year
    if source:
        out["source"] = source
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


# ---------------------------------------------------------------------------
# Collection policy: which states do not publish a composition for a field.
#
# This is the project's central editorial claim, so it lives in one place and is
# asserted only from a citable reason -- never inferred from an empty API
# response. It is keyed by ISO3 and applies to the whole country: if a national
# census does not ask a question, its provinces and districts have no answer to
# it either, so `apply_collection_policy` propagates the marker down every
# level. Before that propagation existed, 8,541 subnational fields in countries
# that demonstrably do not collect them still read "not yet available", which
# told the reader the exact opposite of the truth.
# ---------------------------------------------------------------------------

NOT_COLLECTED_POLICY: dict[str, dict[str, str | dict[str, str]]] = {
    # Bhutan's census does not ask any of the three, which is a different
    # fact from not publishing them. Measured rather than assumed: the 2017
    # national report runs 288 pages and the words religion, ethnic, Hindu,
    # Buddhist, Nepali and mother tongue appear on none of them except two
    # describing the census's own publicity. The 2005 round is the same, and
    # its own list of what it collected stops at housing.
    #
    # The Factbook's religion vector for Bhutan is not from either census --
    # PHCB 2005 has no religion table at all -- and the State Department's
    # religious freedom report attributes the same split to Pew. So there is
    # no Bhutanese figure of any kind to prefer to it.
    "BTN": {
        "religion": "Bhutan's census does not ask religion. The 2017 round published 288 pages of national tables and 20 dzongkhag volumes on education, fertility, mortality, disability, labour, migration and housing, and asked nothing about it; the 2005 round did not either.",
        "language": "Bhutan's census does not ask language or mother tongue.",
        "ethnicity": "Bhutan's census does not ask ethnicity. It does publish citizenship -- Bhutanese against non-Bhutanese, down to gewog -- which is not the same question and is not used as a proxy for it here: citizenship is the contested variable in Bhutan, the 1985 Citizenship Act being how much of the Lhotshampa population lost its legal standing before leaving.",
    },
    "FRA": {
        "ethnicity": "France does not collect ethnicity; statistiques ethniques are barred by law (Loi Informatique et Libertes 1978, Conseil constitutionnel 2007).",
        "religion": "France does not collect religion in its census for the same reason.",
    },
    "DEU": {
        "ethnicity": "Germany does not collect ethnicity. The census records citizenship and migration background; religion comes from church-tax registration, not fine-grained self-ID.",
    },
    # Pakistan is here because the country row was contradicting its own
    # districts. All 145 Pakistani units say the census asks no ethnicity
    # question -- read out of the Bureau's own National Census Report 2023 and
    # its final list of census tables -- while PAK's admin0 record carried a
    # seven-group "ethnicity" composition with no year and no note.
    #
    # That composition is the Factbook's Ethnic groups vector, and for Pakistan
    # it is the 1998 census's *mother tongue* shares with the labels swapped:
    # Pashto printed as Pashtun, Urdu as Muhajir. The map already carries those
    # figures, correctly, on the language field. Publishing them again under
    # ethnicity is the mis-match this project treats as worse than a gap --
    # invisible, because it looks like an answer.
    "PAK": {
        "ethnicity": "Pakistan's census does not ask ethnicity. The Bureau of Statistics' National Census Report 2023 lists what the 7th Population and Housing Census collected -- age, mother tongue, religion, disability, migration, literacy, employment and nationality -- and ethnicity is not among the eight; the report adds that nationality \"can be called and understood as citizenship, or more generally as subject or belonging to a sovereign state, and not as ethnicity\". The Factbook's ethnic-groups vector for Pakistan is the 1998 census's mother-tongue shares relabelled (Pashto as Pashtun, Urdu as Muhajir), so it is not used here: those figures are on the language field, which is the question that was actually asked.",
    },
    # Measured against e-Stat's catalogue rather than against the census
    # questionnaire alone -- see docs/SOURCES.md. The catalogue is the reason
    # each of these three is a declaration and not a gap: the API was asked, it
    # answered, and what it holds is not a composition.
    # Japan carried all three fields here until 19 September 2026, and the
    # facts have not changed: the Kokusei Chosa asks nationality and not
    # religion, ethnicity or language, and the one official religion
    # statistic counts memberships as religious bodies report them. What
    # changed is the owner's decision that day that the prefectures should
    # carry what secondary sources can say, labelled for what it is, the way
    # Korea's provinces carry a survey. scripts/fetch_census/japan.py writes
    # that -- nationality as a census composition under ethnicity_basis
    # "nationality", religion and language as modelled estimates whose notes
    # hold the substance of the declarations that used to sit here -- and an
    # entry here would make check_no_estimate_on_policy_field refuse it.
    "IND": {
        "ethnicity": "India does not collect ethnicity. Scheduled Caste / Scheduled Tribe shares and mother tongue are collected instead.",
    },
    # Laos asks ethnicity and religion and is here for the third field only.
    # Measured rather than assumed, the way Bhutan's declaration was: the 2015
    # results volume runs 282 pages, the words "mother tongue" appear on none
    # of them, and "language" appears on six -- the questionnaire's own
    # wording, the enumerators recruited for their ethnic language skills, and
    # why Lao migrants choose Thailand. None of its tables is a language
    # table. Nor is the census's ethno-linguistic categorisation one: the
    # Socio-Economic Atlas, which defines it, says the term "indicates a
    # categorization based on a common ethnicity through self-identification
    # mainly based on language" -- an ethnicity answer sorted by linguists,
    # not a language anybody was asked to speak, and it is published here on
    # the ethnicity field. The 8,500-village indicator table the provinces and
    # districts are read from carries 68 indicators and no language column.
    # Mongolia asks ethnic group of every citizen and religion of a ten per
    # cent sample, and both are on the map (mongolia.py). Language is the one
    # it does not ask, read off the questionnaire itself rather than inferred
    # from a table that happened to lack a column.
    "MNG": {
        "language": "Mongolia's census does not ask language or mother tongue. The individual questionnaire of the 2020 Population and Housing Census, reproduced in the appendix of the National Statistics Office's national report, runs from \"What is your relationship with household head?\" through gender, age, birthplace, migration, disability, education, literacy, employment and marital status to question 29, \"Do you have a religion?\", and asks nothing about a language at all. In the report's 298 pages the word appears twice: in the definition of literacy -- \"a person who can read and write simple sentences in any languages was considered as literate\" -- and in a note on sign language among the Washington Group's questions on functional difficulty. Ethnic group and religion are both asked, and the aimags carry them.",
    },
    "LAO": {
        "language": "Laos's census does not ask language or mother tongue. The 4th Population and Housing Census 2015 asked 63 questions in 10 parts, among them ethnicity and religion; its 282-page results volume prints no language or mother-tongue table and never uses the words \"mother tongue\", and neither the Socio-Economic Atlas of the Lao PDR 2015 nor the village indicator table behind it carries a language variable. The ten ethno-linguistic categories the census does publish are a classification of the ethnic group a person named, which the map carries on the ethnicity field.",
    },
    # Papua New Guinea, read off its census's own account of its form rather
    # than inferred from a table that happened to lack a column. Appendix 1 of
    # the 2011 National Report lists what the fourth census collected --
    # "age; sex, marital status, religion, migration, economic activity,
    # occupation, industry, fertility, mortality and household income
    # generating activities ... A total of 33 questions were asked using a
    # one-page census questionnaire" -- and neither ethnicity nor language is
    # among them. Religion is, and the provinces carry it (png.py).
    #
    # Language is the one that needs the careful wording, because the census
    # does ask about languages: Table 4.6 is a literacy rate "by language",
    # counting who can read and write English, Pidgin (Tok Pisin), Motu or
    # Tokples -- the report's own glossary defines Tokples as "language of my
    # place ... the local language of a traditional area belonging to a tribe
    # or clan", which is to say every one of the 800-odd of them under one
    # heading. Four abilities, three of them in lingua francas, and they
    # overlap: they are not a composition of anybody's mother tongue, and
    # turning them into one would be inventing a statistic. The Factbook's
    # language vector for PNG ("Tok Pisin, English, Hiri Motu, some 839 living
    # indigenous languages") is a list of what is spoken and carries a share
    # for none of them.
    "PNG": {
        "ethnicity": "Papua New Guinea's census does not ask ethnicity. Appendix 1 of the National Statistical Office's 2011 National Report lists what the 33 questions of the one-page census form collected -- age, sex, marital status, religion, migration, economic activity, occupation, industry, fertility, mortality and household income-generating activities -- and ethnicity is not among them; the country has no national ethnic classification, its people being counted instead by province and by the language of their place. The 2024 census's Final Figures publish nothing of the kind either.",
        "language": "Papua New Guinea's census does not ask mother tongue or language spoken at home. The one language question is literacy: the 2011 National Report's Table 4.6 gives the share of people aged 10 and over who can read and write English, Pidgin (Tok Pisin), Motu or Tokples -- 'language of my place', the report's own name for all 800-odd local languages together. Those four are overlapping abilities in three lingua francas and one residual, not a composition of what anybody speaks, so no language share is published for the country or for any province.",
    },
    # Read off the census's own account of its questionnaire, not inferred
    # from a file that happened to lack the column. The Population and Housing
    # Census 2022 National Report (Volume I) describes the form it was
    # collected on -- two modules, 15 household questions and 20 individual
    # ones, 35 in all -- and names the individual module's subjects. Language
    # is not one of them; ethnic group is, and religion is. Nothing in the
    # report's 520 pages is a language table, its list of district tables
    # (P1-P33) has none, and the Bureau's own district-level indicator
    # workbook runs to 42 topic sheets without one.
    #
    # That was read as "the question was never put", and this entry said so
    # with status not_collected. **It is too strong, and the census project
    # itself is what disproves it.** The Bureau's *Report on Socio-Economic
    # and Demographic Survey 2023* -- June 2024, ISBN 978-984-475-268-9, 553
    # pages, one of the five national reports published under the Population
    # and Housing Census 2021 Project -- is the long-questionnaire survey run
    # after the census on a sample of 301,000 households, and its Module 4
    # collects mother tongue by name, beside religion and ethnic population.
    # So Bangladesh does gather the answer; what it does not do is publish a
    # composition of it.
    #
    # Table 3.6, *Population by Mother Tongue and Second Language, Division
    # and Location*, has exactly two mother-tongue columns -- Bangla and
    # Others -- for the eight divisions. (The shares themselves are in
    # docs/SOURCES.md, not here: a declaration explains an absence and never
    # states a share, which is the rule the Maldives' "100% Islam" was written
    # down to prevent.) Across all 553 pages no mother tongue but Bangla is
    # ever named: a sweep for Chakma,
    # Marma, Santal, Garo, Tripura, Mro, Rakhain, Manipuri, Urdu, Bishnupriya,
    # Tanchangya, Khasi, Hajong, Munda, Oraon, Rohingya, Bawm, Khumi, Chak,
    # Pankho, Lushai, Koch, Dalu and Rajbanshi returns zero pages.
    #
    # A named group against a residual is not a composition -- drawn as two
    # slices it would read as a survey that found two languages -- and the
    # report publishes nothing below the division anyway, so no zila has a
    # mother-tongue figure from either round. The gap therefore stands, but
    # it is `not_available` and not `not_collected`: the question is asked,
    # and the honest reason names what the answer was and why it cannot be a
    # chart. Religion, which the same census asks at zila level, is on the
    # map from the Bureau's own workbook.
    "BGD": {
        "language": {
            "status": NOT_AVAILABLE,
            "note": "Bangladesh's census does not ask language. The 2022 "
                    "questionnaire has 35 questions -- 15 in the household "
                    "module and 20 in the individual module, which the National "
                    "Report (Volume I) lists as age, sex, marital status, religion, "
                    "disability, education, working status, training, mobile phone "
                    "and internet use, banking inclusion and ethnic population -- "
                    "and none of them is language. The census project's own "
                    "long-questionnaire sample survey does ask it: the Report on "
                    "Socio-Economic and Demographic Survey 2023 (BBS, June 2024, "
                    "553 pages) collects mother tongue in Module 4 and publishes "
                    "Table 3.6, Population by Mother Tongue and Second Language, "
                    "Division and Location. That table has two mother-tongue "
                    "columns for the eight divisions, Bangla and Others, and no "
                    "mother tongue but Bangla is named anywhere in its 553 pages. "
                    "A named group against a residual is not a composition, and "
                    "the survey publishes nothing below the division, so no zila "
                    "has a mother-tongue figure from either round. The one "
                    "Bangladeshi instrument that is district-representative asks "
                    "the question and never tabulates it: MICS 2019 puts it to "
                    "every household as question HC1B, \"What is the mother "
                    "tongue/native language of the head of the household?\", and "
                    "prints exactly two answers beside it, BANGLA and OTHER "
                    "LANGUAGE. In 564 pages that phrase appears once, on the blank "
                    "questionnaire, and the survey's own District Summary Findings "
                    "Report does not contain the word language at all. So the limit "
                    "is not only that the figures stop at the division: every "
                    "Bangladeshi instrument that asks mother tongue codes it as one "
                    "language against an unnamed rest, which is not a composition at "
                    "any level. What the census asks "
                    "about a minority's identity is ethnic group, under the Khudra "
                    "Nri-goshthi Sangskritik Pratisthan Ain 2010.",
        },
    },
    "ESP": {
        "ethnicity": "Spain's census records nationality and birthplace, not ethnicity.",
        "religion": "Spain's census does not ask religion (CIS survey data exists instead).",
    },
    "CHN": {
        "religion": "China's census does not ask religion; it records the 56 official "
                    "nationalities (minzu) instead. The China Family Panel Studies asked "
                    "it in 2012 and supports province-level figures for five provinces "
                    "(Shanghai, Liaoning, Henan, Gansu, Guangdong), which carry them.",
    },
    # Ireland asks about language twice and neither answer is a composition.
    # Census 2022 publishes "Speakers of foreign languages" -- a count of only
    # those people, split by which language, with English absent from it
    # entirely -- and "Ability to Speak Irish", which is a skill, not a
    # language spoken. Religion and ethnicity are read from the same census.
    "IRL": {
        "language": "Ireland's census asks which foreign languages a person "
                    "speaks and whether they can speak Irish. Neither is a "
                    "breakdown of the population by language: the first "
                    "excludes English speakers, the second counts an ability.",
    },
    # Measured rather than recalled: MEDAS, TUIK's statistical database, lists
    # 92 subjects and not one of them is religion, ethnicity or mother tongue.
    # The catalogue runs from the address-based population register through
    # births, deaths, marriages, life tables, labour force and prices to
    # theatre and prisons. Turkey's census last asked mother tongue and
    # ethnicity in 1965; what replaced it is an address register, which records
    # where a citizen lives rather than what they are.
    "TUR": {
        "religion": "Turkey does not publish religion. Its statistical database lists 92 subjects and none is religion; population figures come from an address-based register.",
        "ethnicity": "Turkey has not collected ethnicity since the 1965 census; its address-based register records residence and citizenship instead.",
        "language": "Turkey has not collected mother tongue since the 1965 census.",
    },
    # The entries below were written from the survey under survey/findings:
    # each names the census and the fact about its questionnaire the
    # declaration rests on. A wrong "not asked" would hide real data, so a
    # country whose questionnaire the survey could not settle is left alone.
    "NGA": {
        "religion": "Nigeria's census does not ask religion. The National Population Commission stated in 2022 and 2023 that the question was excluded from the 2023 questionnaire for its sensitivity, as it was from 1991 and 2006; the only subnational figures are survey estimates.",
        "ethnicity": "Nigeria's census does not ask ethnicity, excluded from the 2023 questionnaire with religion for the same stated reason; the only subnational figures are survey estimates.",
    },
    "TZA": {
        "religion": "Tanzania's census has not asked religion since 1967; the 2022 census did not, and the only subnational figures are survey estimates.",
        "ethnicity": "Tanzania's census has not asked ethnic group since 1973; the 2022 census did not.",
    },
    "SDN": {
        "religion": "Sudan's 2008 census, the last, dropped religion from the questionnaire by decision of the Presidency (UNSD country paper; IHSN catalogue); the only subnational figures are survey estimates.",
        "ethnicity": "Sudan's 2008 census dropped ethnicity with religion; the last count of ethnic group was 1956, on nine provinces that match no current boundary.",
    },
    "SSD": {
        "religion": "South Sudan has held no census since independence; the 2008 Sudan census that covered it dropped religion from the questionnaire by decision of the Presidency.",
        "ethnicity": "South Sudan has held no census since independence; the 2008 Sudan census that covered it dropped ethnicity with religion.",
    },
    "COL": {
        "religion": "Colombia's census does not ask religion; DANE publishes no religious statistics. The 2018 census asked ethnic self-recognition, which is on the map.",
        "language": "Colombia's 2018 census has no language question for the population; it asks only whether a person who is indigenous speaks their native language, which is not a composition.",
    },
    "DZA": {
        "religion": "Algeria's census does not ask religion; censuses on a religious, linguistic or ethnic basis are barred to preserve national unity. The 2022 RGPH form has no such question.",
        "ethnicity": "Algeria's census does not ask ethnicity, barred with religion and language; the 2022 RGPH form has no such question.",
        "language": "Algeria's census has not asked language since 1966, on a division set that matches no current boundary; the 2022 RGPH form has no such question.",
    },
    "SAU": {
        "religion": "Saudi Arabia's 2022 census asks citizenship (Saudi or non-Saudi, and country of citizenship) and not religion; there are no official religious statistics at any level.",
        "ethnicity": "Saudi Arabia's 2022 census records citizenship, not ethnicity.",
        "language": "Saudi Arabia's 2022 census does not ask language.",
    },
    "IRQ": {
        "ethnicity": "Iraq's 2024 census, the first nationwide count since 1987, deliberately excluded ethnicity from the questionnaire; religion was asked, sect was not.",
        "language": "Iraq's 2024 census deliberately excluded language from the questionnaire with ethnicity.",
    },
    "RUS": {
        "religion": "Russia's census has never asked religion; the 2020 census asked nationality and native language, which are on the map.",
    },
    "ARG": {
        "religion": "Argentina's census has not asked religion since 1960; only the 1947 and 1960 censuses carried the question. The 2022 census asks indigenous and Afro-descendant self-recognition instead.",
    },
    "BRA": {
        "language": "Brazil's census does not ask language of the population; the 2022 census asks which indigenous languages an indigenous person speaks, which is not a composition.",
    },
    "IRN": {
        "ethnicity": "Iran's census does not ask ethnicity; the 2016 census asked religion in the state's recognised categories, not ethnic group.",
        # Language is deliberately absent, by the owner's decision of 20
        # September 2026. Iran's census does not ask it -- that remains true,
        # and every ALI record says so in its own note -- but this table means
        # something stronger than "the census does not ask": it means no value
        # may ever be written, and check_no_estimate_on_policy_field enforces
        # that as fatal. The Atlas of the Languages of Iran did measure
        # language, at 21,152 settlements, so a figure here is a reading of
        # somebody's fieldwork rather than a statistic manufactured about a
        # category the state declined to enumerate, which is what the guard
        # exists to stop. The nineteen provinces the atlas has not reached
        # take their stated reason from ADAPTER_GAPS["IRN"] instead.
    },
    "GRC": {
        "religion": "Greece's census has not asked religion since 1951; the 2021 census records citizenship and country of birth.",
        "language": "Greece's census has not asked mother tongue since 1951.",
    },
    # The census half of this was already established. What has now been
    # measured is the half it left open: whether the household surveys that
    # stand in for the census carry the three fields, the way Afrobarometer
    # and the Hankook pooled survey carry them elsewhere on this map. They do
    # not. The CSO/NSIA series -- NRVA 2003, 2005, 2007-08 and 2011-12, then
    # ALCS 2013-14 and 2016-17 -- prints its own household questionnaire in
    # the report, and the ALCS 1392-93 form (45 pages) mentions religion,
    # ethnicity, language, Pashto and Dari on no page at all. The ALCS 2016-17
    # report runs 421 pages and its eleven mentions of those words are the
    # language the interview software was written in, an exam interviewers sat
    # on local culture, and the UN's definition of a refugee. The NRVA 2011-12
    # report, 238 pages, mentions "language" twice, both times to say which
    # languages the report itself is printed in. The one sub-provincial
    # enumeration since 1979, the CSO/UNFPA Socio-Demographic and Economic
    # Survey, lists its own contents -- population, literacy, education,
    # migration, employment, disability, fertility, mortality, housing -- and
    # none of the three is among them.
    #
    # So there is no survey to label and carry here; the declaration stands on
    # its own, and it now says why no non-census route replaces it.
    "AFG": {
        "religion": "Afghanistan has never completed a population census: the 1979 count was abandoned partway and none has been held since, so no census question on religion exists. No survey stands in for it either -- the CSO/NSIA household series (NRVA 2011-12, ALCS 2013-14 and 2016-17) publishes its questionnaire and asks nothing about religion. The NSIA publishes population estimates only.",
        # Ethnicity is deliberately no longer here, by the owner's decision of
        # 22 September 2026: where a source exists, it is read, and the policy
        # table does not get to forbid it.
        #
        # What this table means is "no value may ever be written", which is a
        # stronger claim than the one the entry actually established. The
        # entry was right that no *census* asks -- none has ever been
        # completed -- but that is not the same as there being nothing to
        # read. The Ministry of Rural Rehabilitation and Development published
        # district development plans between about 2008 and 2014, and many
        # state an ethnic breakdown; scripts/fetch_census/afghanistan.py reads
        # them and labels them as what they are, a ministry planning survey
        # rather than a count.
        #
        # The sentence itself is kept, because it is true and a district the
        # plans do not cover still needs to say why it is empty -- it is now
        # the gap's note rather than a prohibition.
        "language": "Afghanistan has never completed a population census, so no census question on language exists. The CSO/NSIA household series does not ask mother tongue: the ALCS questionnaire carries no language question, and the NRVA 2011-12 report mentions language only to say which languages the report itself is printed in. The NSIA publishes population estimates only.",
    },
    # Measured against the census's own form and its own table list, not
    # against the constitution. Article 9(d) requires a citizen of the
    # Maldives to be a Muslim, and that is a fact about the law rather than an
    # answer anybody was counted giving: a 100% Islam figure attributed to the
    # census would be a figure the census never produced, which is the one
    # kind of error this project ranks below a gap.
    #
    # What the form asks: the 2006 questionnaire -- 16 pages, the whole
    # Shaviyani Form, published through the IHSN microdata catalogue -- puts
    # exactly one question about who a person is, M4, "What is your
    # Nationality?", answered Maldivian or Foreigner. Nothing on religion,
    # ethnicity, mother tongue or language.
    #
    # What the round publishes: the Census 2022 results summary lists the
    # whole output, and it is 60-odd tables -- population P1-P6, employment
    # EC1-EC6, housing H1-H8, migration MG1-MG13, education ED1-ED19. Not one
    # is a religion table; nationality is again the only characteristic of
    # that kind anywhere in the set. The atoll profiles the Bureau published
    # from it in 2024-25 are the same: resident population, Maldivians and
    # foreigners, island by island.
    #
    # Language is the Irish case rather than an absence. ED1, ED2 and ED16
    # cross "literacy in mother tongue" with age, sex, atoll and island, and
    # ED3-ED4 do the same for English. Those count an ability; which language
    # the mother tongue *is* goes unrecorded, so there is no composition in
    # them and reading one out would be inventing it. Dhivehi being
    # near-universal is a true sentence and not a published figure.
    "MDV": {
        "religion": "The Maldives census does not ask religion. The only question on its form about who a person is asks nationality -- Maldivian or foreigner -- and no output of the 2022 round, across some sixty published tables, is a religion table. The constitution requires a citizen to be Muslim; that is the law, not a count, and no census figure for it exists.",
        "ethnicity": "The Maldives census does not ask ethnicity. Nationality, Maldivian or foreigner, is the only question of that kind on the form and the only such breakdown in the published tables.",
        "language": "The Maldives census does not ask language. It asks literacy in mother tongue and literacy in English -- Census 2022 tables ED1, ED2, ED16 and ED3-ED4 -- which count an ability and never record which language the mother tongue is. Dhivehi being near-universal is not a figure the census published.",
    },
    "VEN": {
        "religion": "Venezuela's 2011 census asked indigenous and Afro-descendant self-recognition and not religion; no census since 1961 has carried a religion question.",
    },
    # Measured against the census's own form and its own 53 tables, after the
    # three notes here had stood for a while as an assertion with nothing
    # behind them. North Korea is not a country without a census: the 2008
    # round was enumerated over 1-15 October by about 35,000 enumerators with
    # UNFPA support, and the Central Bureau of Statistics' National Report was
    # published -- 278 pages, served by the UN Statistics Division, with all
    # three questionnaires printed as annexes.
    #
    # What the form asks: 53 questions, H1-H14 on the household and the
    # dwelling, P1-P29 on the person, M1-M10 on deaths in the household. One
    # of the 53 asks who a person is, P7, "What is ____'s nationality?",
    # answered 1 Korean or 2 Others.
    #
    # What the round publishes: Tables 1 to 53, and Table 5 is the only one
    # carrying P7 -- national, by age and sex, 23,349,326 Koreans against 533
    # people of other nationalities. Over the text of all 278 pages,
    # *religio*, *ethnic*, *mother tongue*, *language*, *church*, *Buddhis*,
    # *Christian*, *Chondo*, *Confucian* and *faith* match two pages: Table
    # 22's definition of literacy ("read and write a simple message in any
    # language") and one line of Table 37's occupation list ("Religious
    # professionals", 103 people). Neither is a composition.
    #
    # And there is no survey standing in for the census, which is the question
    # Afghanistan's entry below exists to answer: the CBS's Socio-Economic,
    # Demographic and Health Survey 2014, 167 pages, matches none of those
    # words on any page.
    #
    # Nationality is not carried onto the ethnicity field, for the Maldives'
    # reason: a passport is not an ethnic group, and Table 5 has no geography
    # to put one on in any case.
    "PRK": {
        "religion": "North Korea's census does not ask religion. Its 2008 questionnaire has 53 questions -- H1 to H14 on the household, P1 to P29 on the person, M1 to M10 on deaths -- and none of them is about religion; in the 278 pages of the National Report the word occurs once, as the occupation 'religious professionals', 103 people, in Table 37. No table of the 53 is a religion table and the state publishes no other figures.",
        "ethnicity": "North Korea's census does not ask ethnicity. The one question on its form about who a person is, P7, asks nationality -- 1 Korean or 2 Others -- and the only table built from it, Table 5, is national: 23,349,326 Koreans and 533 people of other nationalities, by age and by sex. Nationality is not ethnicity, and nothing in the round crosses either with a province.",
        "language": "North Korea's census does not ask language. In the 278 pages of the 2008 National Report 'mother tongue' appears nowhere and 'language' appears once, in Table 22's definition of literacy -- the ability to read and write a simple message in any language -- which counts an ability and records no language. No table of the 53 is a language table.",
    },
    "SYR": {
        "religion": "Syria's census has not asked religion since 1960; the 2004 census asked nationality (citizenship) only, as the US Census Bureau workbook's dictionary confirms.",
        "ethnicity": "Syria's census has never asked ethnicity; the 2004 sheet labelled Ethnicity is a distribution by nationality, which is citizenship.",
    },
    "TUN": {
        "religion": "Tunisia's census (2014, 2024) carries no religion question; the national figure is an estimate, not a count, and the only subnational figures are survey estimates.",
        "ethnicity": "Tunisia's census does not ask ethnicity.",
    },
    # South Korea carried "the census does not collect ethnicity" here until
    # 19 September 2026, when the map's owner decided that Korea's
    # ethnicity field carries nationality -- Korean nationals and
    # registered foreign residents by country of nationality, which the
    # state does count -- as a real composition under ethnicity_basis
    # "nationality", the way Japan's prefectures do. The substance of the
    # old declaration (no ethnicity question is asked) now lives in every
    # row's note, written by scripts/fetch_census/korea_nationality.py.
    # Read off the census's own questionnaire: MyCensus 2020's demographic
    # module asks sex, age, marital status, ethnic group, citizenship and
    # religion, and no census round has asked language or mother tongue.
    # Ethnicity and religion are real compositions on the 16 states and the
    # districts; language was reading as "not fetched yet" on all of them.
    "MYS": {"language": "Malaysia's census asks ethnic group, citizenship and religion but has never asked language or mother tongue, and DOSM publishes no language composition."},
    "NLD": {"ethnicity": "The Netherlands records migration background, not ethnicity.",
            "language": "The Netherlands has had no questionnaire census since 1971 and no register records language."},
    "SWE": {"ethnicity": "Sweden records country of birth and citizenship, not ethnicity.",
            "religion": "Sweden's census is compiled from registers, and no register records religion; the state kept none after the Church of Sweden separated in 2000.",
            "language": "Sweden's census is compiled from registers, and no register records mother tongue."},
    "NOR": {"ethnicity": "Norway records immigrant background, not ethnicity."},
    "DNK": {"ethnicity": "Denmark records ancestry/citizenship, not ethnicity."},
    "BEL": {"ethnicity": "Belgium does not collect ethnicity; language community is administrative, not a census question.",
            "religion": "Belgium's census is compiled from registers and has never carried religion.",
            "language": "Belgium's language census was abolished by the law of 24 July 1961 after the 1947 count; the register-based census records none."},
    "ITA": {"ethnicity": "Italy's census records citizenship, not ethnicity."},
    "AUT": {
        "ethnicity": "Austria's census has been register-based since 2011 (Registerzählung) and records citizenship and country of birth; no register holds ethnicity.",
        "religion": "Austria's register-based census carries no religion; the last religion question was in the 2001 census.",
        "language": "Austria's register-based census carries no language; the last Umgangssprache question was in 2001.",
    },
    "SVN": {
        "ethnicity": "Slovenia's census has been register-based since 2011; ethnic affiliation was last asked in 2002.",
        "religion": "Slovenia's register-based census carries no religion; last asked in 2002.",
        "language": "Slovenia's register-based census carries no mother tongue; last asked in 2002.",
    },
    "ISL": {
        "ethnicity": "Iceland's census is register-based and records citizenship and country of birth, not ethnicity.",
        "language": "Iceland's register-based census carries no language.",
    },
    "FIN": {
        "ethnicity": "Finland's census is register-based and records citizenship, country of birth and mother tongue, not ethnicity.",
    },
    "CHE": {
        "ethnicity": "Switzerland's census records nationality, not ethnicity; religion and language come from the structural survey.",
    },
    "LUX": {
        "ethnicity": "Luxembourg's census records nationality, not ethnicity.",
        "religion": "Luxembourg's census (RP 2021) does not ask religion.",
    },
    "PRT": {
        "ethnicity": "Portugal's census records nationality, not ethnicity; an ethno-racial question was considered for 2021 and not included.",
    },
    "LVA": {
        "religion": "Latvia's census does not ask religion; it asks ethnicity and language.",
    },
    "UKR": {
        "religion": "Ukraine's 2001 census asked nationality and language, not religion.",
    },
    "BLR": {
        "religion": "Belarus's 2019 census asked nationality and language, not religion.",
    },
    # Read off the 2022 questionnaire itself, which INETL reproduces in full as
    # Annex III of the census main report. Its individual module runs from E1 to
    # E77 without a break -- marital status, parents, birth registration, place
    # of birth, internal migration, citizenship, literacy, education, labour,
    # religion (E57), mother tongues (E58), disability, fertility, birth
    # attendance -- and none of those 77 questions asks ethnicity, race, tribe or
    # ancestry. Timor-Leste's two collected identity variables sit next to each
    # other at E57 and E58, and both are on this map.
    #
    # The Factbook's Timor-Leste "Ethnic groups" line is not a census figure and
    # carries no shares: it reads "Austronesian (Malayo-Polynesian) (includes
    # Tetun, Mambai, Tokodede, Galoli, Kemak, Baikeno), Melanesian-Papuan
    # (includes Bunak, Fataluku, Bakasai), small Chinese minority" -- which is
    # the census's mother-tongue list sorted into two language families. The map
    # carries those tongues, counted, on the language field, and putting the
    # same division under ethnicity would publish one question's answer as
    # another's.
    "TLS": {
        "ethnicity": "Timor-Leste's census does not ask ethnicity. The 2022 questionnaire, reproduced as Annex III of INETL's census main report, runs its individual module from E1 to E77 -- marital status, parents, birth registration, place of birth, migration, citizenship, literacy, education, labour, religion, mother tongues, disability, fertility, birth attendance -- and asks nothing about ethnicity, race, tribe or ancestry. What it does ask, at E58, is \"what languages did <Name> learn as a child?\", and Timorese identity largely tracks that answer; the Factbook's ethnic-groups line for Timor-Leste is the census's mother-tongue list sorted into Austronesian and Papuan, with no shares, so it is not used here. The mother tongues themselves are on the language field, which is the question that was actually asked.",
    },
}


def _policy_entry(iso3: str | None, field: str) -> dict[str, str] | None:
    """One policy declaration, in its long form.

    An entry is written as a plain string when the country does not gather the
    field at all, which is the ordinary case and stays the ordinary spelling.
    It may instead be a mapping carrying its own ``status``, for the case the
    string form cannot say: a country that *does* gather the answer and
    publishes it in a shape this map cannot draw. Bangladesh's mother tongue
    is the one of those -- asked in the census project's sample survey,
    published as Bangla against a residual at the division and nowhere below
    it -- and calling that ``not_collected`` would state the opposite of what
    the Bureau did.
    """
    if not iso3:
        return None
    declared = NOT_COLLECTED_POLICY.get(iso3.upper(), {}).get(field)
    if declared is None:
        return None
    if isinstance(declared, str):
        return {"status": NOT_COLLECTED, "note": declared}
    return {"status": declared["status"], "note": declared["note"]}


def collection_policy(iso3: str | None, field: str) -> str | None:
    """The documented reason a country does not publish ``field``, or None."""
    entry = _policy_entry(iso3, field)
    return entry["note"] if entry else None


def collection_status(iso3: str | None, field: str) -> str | None:
    """The gap status the policy declares for ``field``, or None."""
    entry = _policy_entry(iso3, field)
    return entry["status"] if entry else None


def collection_gap(iso3: str | None, field: str) -> dict[str, Any] | None:
    """The policy's declaration as a ready-made gap marker, or None.

    Adapters take the whole marker from here rather than pairing a status of
    their own with the central reason: the country row and its districts
    disagreeing about whether the question was asked is exactly the drift this
    table exists to prevent, and a status is half of that claim.
    """
    entry = _policy_entry(iso3, field)
    return gap(entry["status"], entry["note"]) if entry else None


def apply_collection_policy(record: dict[str, Any], iso3: str | None,
                            fields: Iterable[str] = ("religion", "ethnicity", "language"),
                            ) -> list[str]:
    """Mark fields the country does not publish a composition for, in place.

    Only replaces a ``not_available`` marker: a real value from a subnational
    source always wins (a country can decline to ask nationally while a region
    publishes its own figures), and a gap of any other status is left alone.

    A ``not_available`` is replaced whether or not it already carries a note,
    and that is deliberate. The policy is the one place a country-level reason
    is written, and the notes adapters attach to a ``not_available`` are
    either a copy of it or a generic hint from a multi-country source. Both
    should yield: a copy goes stale the moment the policy is improved (the 64
    Bangladeshi zilas lost the MICS evidence when a note-guard was tried), and
    a generic hint can be flatly wrong for the country it is printed on --
    Eurostat's "SI collects religion in its national census" for a Slovenia
    that has been register-based since 2011. A review proposed guarding on
    the note; a rebuild showed both of those regressions, and the guard was
    taken out. The Slovenia case is pinned in the tests.
    """
    applied: list[str] = []
    for field in fields:
        entry = _policy_entry(iso3, field)
        if not entry:
            continue
        current = record.get(field)
        if not isinstance(current, dict):
            continue
        status = current.get("status")
        # A not_available always yields (see the docstring). A not_collected
        # yields only when it carries no reason: that is an adapter agreeing
        # with the policy and saying nothing else, and the five Tunisian
        # fields Afrobarometer wrote that way sat bare because this branch
        # matched only the one status. A noted not_collected is an adapter's
        # own declaration and stands.
        if status == NOT_AVAILABLE or (status == entry["status"]
                                       and not current.get("note")):
            record[field] = gap(entry["status"], entry["note"])
            applied.append(field)
    return applied


# ---------------------------------------------------------------------------
# HTTP with on-disk cache + retry/backoff
# ---------------------------------------------------------------------------

def log(*args: Any) -> None:
    print(*args, file=sys.stderr, flush=True)


def cache_path(url: str, cache_dir: Path | None = None) -> Path:
    """Where http_get keeps this URL's body."""
    cache_dir = cache_dir or (RAW / "http_cache")
    return cache_dir / hashlib.sha256(url.encode()).hexdigest()[:24]


def forget(url: str, cache_dir: Path | None = None) -> None:
    """Drop a cached body, for a caller that finds it is not what it claims.

    http_get caches on a 200 and cannot tell a complete body from a truncated
    one -- the server said OK and the bytes arrived. Only the caller that
    parses it knows. Wikidata's endpoint is the case this exists for: it
    answers 200, streams results, hits its own 60-second limit part way
    through and abandons the stream, so the body is valid JSON up to some
    byte several hundred kB in and then simply stops. Cached, that truncation
    is what every retry in the run gets back.
    """
    cache_path(url, cache_dir).unlink(missing_ok=True)


def http_get(url: str, *, cache: bool = True, retries: int = 4, timeout: int = 120,
             headers: dict[str, str] | None = None, binary: bool = False,
             cache_dir: Path | None = None, aia: bool = False) -> bytes | str:
    """GET with a content-addressed disk cache and exponential backoff.

    Retries only network/5xx errors; a 404 raises immediately so callers can
    treat "this country has no ADM2" as data rather than as a failure.

    ``aia`` is for a server that sends its leaf certificate and omits the
    intermediate above it, which urllib reports as *unable to get local issuer
    certificate*. censusindia.gov.in is one: its certificate is properly issued
    and its chain is one link short, so a browser reaches it and Python does
    not. The repair is to fetch the missing intermediate from the certificate's
    own Authority Information Access extension and verify against it plus the
    public roots -- full verification, with the link the server failed to send
    supplied. It is never a way to skip the check: see scripts/probe_tls.py,
    which does the work and explains why an intermediate fetched over plain
    HTTP is safe to add (it is believed only if it chains to a trusted root,
    which the handshake then tests).
    """
    path = cache_path(url, cache_dir)
    cache_dir = path.parent
    if cache and path.exists():
        blob = path.read_bytes()
        return blob if binary else blob.decode("utf-8", "replace")

    req_headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    req_headers.update(headers or {})
    opener = urllib.request.urlopen
    if aia:
        # Imported here, and with the directory put on the path first: this
        # module is reached both as `common` (scripts/ on sys.path) and as
        # `scripts.common`, and probe_tls is a sibling file rather than a
        # package member. Nothing above pays for it -- an adapter that does not
        # ask for the repair never runs this.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from probe_tls import verified_opener                 # noqa: PLC0415
        opener = verified_opener(urllib.parse.urlsplit(url).hostname or "").open
    delay = 2.0
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with opener(req, timeout=timeout) as resp:
                blob = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    blob = gzip.decompress(blob)
            if cache:
                cache_dir.mkdir(parents=True, exist_ok=True)
                path.write_bytes(blob)
            return blob if binary else blob.decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:  # noqa: PERF203
            if exc.code in (400, 404, 403, 401):
                # Client errors will not get better on retry; fail fast so a
                # wrong table id costs one request, not 30 seconds of backoff.
                raise
            last = exc
        except Exception as exc:  # pragma: no cover - network shape varies
            last = exc
        if attempt < retries:
            log(f"  retry {attempt + 1}/{retries} after {delay:.0f}s :: {url} :: {last}")
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"GET failed after {retries} retries: {url}") from last


def http_json(url: str, **kwargs: Any) -> Any:
    """GET + parse, tolerating the quirks national statistics APIs actually have.

    Statistics Canada prepends a UTF-8 BOM and sometimes a ``//`` guard line to
    its JSON; both make a raw ``json.loads`` fail with "Expecting value: line 1
    column 1".  And when a body still is not JSON, the parse error alone is
    useless in CI -- log the start of what the server actually sent, so a failed
    run diagnoses itself.
    """
    text = http_get(url, **kwargs)
    assert isinstance(text, str)
    cleaned = text.lstrip("\ufeff \n\r\t")
    if cleaned.startswith("//"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        preview = " ".join(text[:300].split())
        log(f"  ! non-JSON response from {url}\n    body starts: {preview!r}")
        raise


def download(url: str, dest: Path, *, force: bool = False, timeout: int = 3000) -> Path:
    """Stream a large file to disk, skipping the fetch when it already exists."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        log(f"  cached {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    delay = 2.0
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open("wb") as fh:
                while chunk := resp.read(1 << 20):
                    fh.write(chunk)
            tmp.replace(dest)
            log(f"  fetched {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
            return dest
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 403, 401):
                raise
            log(f"  retry {attempt + 1}/4 in {delay:.0f}s :: {exc}")
        except Exception as exc:  # pragma: no cover
            log(f"  retry {attempt + 1}/4 in {delay:.0f}s :: {exc}")
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"download failed: {url}")


# ---------------------------------------------------------------------------
# Parsing helpers for the free-text sources (Factbook, census footnotes)
# ---------------------------------------------------------------------------

_NUM = r"[-+]?\d[\d,]*(?:\.\d+)?"
# "Greek Orthodox 81-90%" and "Muslim 98.0 - 99.0%": an optional second
# number makes the range explicit instead of leaving the row unmatched.
# Words that qualify a figure rather than name a group.
_QUALIFIER = re.compile(
    r"\b(?:approximately|approx\.?|about|roughly|around|est\.?|more than|over|"
    r"at least|greater than|less than|under|up to|nearly|almost|fewer than)\b",
    re.I)
_SHARE = re.compile(r"(?:^|\s)(<|>)?\s*(" + _NUM + r")"
                    r"(?:\s*[-\u2013\u2014]\s*(\d[\d,]*(?:\.\d+)?))?\s*%")


# The signature of UTF-8 bytes read as latin-1, written as the byte ranges it
# actually is: a two-or-more-byte lead (0xC2 and up) followed by a continuation
# byte (0x80-0xBF). Read as latin-1 those land on A-circumflex through sharp-s
# and then on a C1 control or Latin-1 punctuation -- a pair no real place name
# contains. Guessing at the visible lead characters instead missed Maori
# macrons, which encode from 0xC4 and 0xC5.
_MOJIBAKE = re.compile("[\u00c2-\u00df][\u0080-\u00bf]")


def repair(name: str) -> str:
    """Undo a name stored as UTF-8 that had been read as latin-1.

    geoBoundaries ships 33 such names across five countries -- Chile's regions
    read "Regi\u00c3\u00b3n Metropolitana de Santiago" -- and they are both
    shown to viewers and matched against by the census join, so every reader of
    the boundary file needs this, not just the one that builds the site.

    Re-encoding to latin-1 and decoding as UTF-8 is safe because it is
    self-checking: a name that really is latin-1 does not survive the round
    trip. "Ca\u00f1ete" encodes to bytes that are not valid UTF-8, so the
    decode raises and the name is left alone; only a string that *was* UTF-8
    all along comes back different and legible.
    """
    if not _MOJIBAKE.search(name):
        return name
    try:
        return name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


# Names geoBoundaries spells wrong, and what they should be. Keyed by the
# country's ISO3 so a correction can never reach a similar name elsewhere.
#
# Unlike repair() above, nothing detects these. Mojibake is self-announcing --
# a byte pair no place name contains -- and the fix verifies itself by round
# trip. "Nothern Cape" is a perfectly well-formed string; only a reader who
# knows the place can tell it is wrong. So each entry is declared, matched
# exactly, and nothing is inferred: a rule loose enough to find these by
# similarity would also "correct" real names that merely resemble another, and
# "Nothern Cape" differs from "Northern Cape" by less than "Eastern Cape"
# differs from "Western Cape".
MISSPELLED: dict[tuple[str, str], str] = {
    ("ZAF", "Nothern Cape"): "Northern Cape",
    # geoBoundaries transposes Sagaing and drops a letter from Tanintharyi.
    # Both are well-formed words, so nothing can detect them; a reader who
    # knows Myanmar is the only test there is. The census, the Department of
    # Population and Myanmar's own English-language usage all agree.
    ("MMR", "Saigang"): "Sagaing",
    ("MMR", "Tanitharyi"): "Tanintharyi",
    # Two Brazilian states, and between them 21 million people who have had a
    # shape and no figures for as long as Brazil has been on this map. IBGE
    # publishes both; nothing reached them because geoBoundaries drops the "e"
    # from Grande and writes Janeiro as Jeneiro. Neither is detectable -- they
    # are well-formed words -- and both are the state's name in every Brazilian
    # source including the census this map reads.
    ("BRA", "Rio Granda do Norte"): "Rio Grande do Norte",
    ("BRA", "Rio de Jeneiro"): "Rio de Janeiro",
    # Five municipalities the 2022 census reached and the boundary file spells
    # its own way, found by reading the 22 shapes the join left unmatched. Each
    # right-hand side is IBGE's spelling, taken from the census file rather than
    # from anyone's memory: Arez keeps a z, Assu doubles its s, Graccho doubles
    # its c, and two prepositions differ -- Leverger takes "de" and Monte Alto
    # takes "do", which is the sort of thing no rule finds and no reader
    # doubts once the two lists are set side by side.
    ("BRA", "Arês"): "Arez",
    ("BRA", "Açu"): "Assú",
    ("BRA", "Gracho Cardoso"): "Graccho Cardoso",
    ("BRA", "Santo Antônio do Leverger"): "Santo Antônio de Leverger",
    ("BRA", "Barão de Monte Alto"): "Barão do Monte Alto",
    # China's most populous province, 126 million people, drawn under the name
    # of its capital city. Guangzhou is the city; Guangdong is the province, and
    # nothing that says Guangdong -- Wikidata included -- could ever reach a
    # shape called Guangzhou, so the province had a polygon and no figures.
    ("CHN", "Guangzhou Province"): "Guangdong",
    # And a doubled word: the shape is "Ningxia Ningxia Hui Autonomous Region".
    # It matched anyway, on the prefix, so this changes no join -- it changes
    # what a reader is shown, which is reason enough.
    ("CHN", "Ningxia Ningxia Hui Autonomous Region"): "Ningxia Hui Autonomous Region",
    # Found by reading the units that sat blank beside covered neighbours.
    # Each is a well-formed string and none is detectable; the right-hand side
    # is the name the country itself uses.
    ("ERI", "Northen Red Sea Region"): "Northern Red Sea Region",
    ("GUY", "Barina-Waini"): "Barima-Waini",
    ("BEN", "Atlanique"): "Atlantique",
    ("NIC", "North Carribean Coast Autonomous Region"):
        "North Caribbean Coast Autonomous Region",
    ("TKM", "Ahai"): "Ahal",
    ("WSM", "Fa'asaleleage"): "Fa'asaleleaga",
    ("LCA", "Anse la Raya"): "Anse la Raye",
    # Seychelles is not misspelled -- it is cut off. Every one of its 26
    # district names in CGAZ is at most ten characters ("Anse Boile", "Baie
    # Saint", "Roche Caïm", "La Digue a"), which is a field width, not a
    # spelling. Most survived because ten characters still uniquely prefix one
    # district. These four did not: "Anse Aux P" stops mid-word, so no
    # whole-word pass can reach "Anse aux Pins", and the two Grand'Anses --
    # one on Mahé, one on Praslin, 45 km apart -- are cut down to a pair of
    # names that differ only by an apostrophe and prefix both districts
    # equally, so the matcher rightly refused to choose.
    #
    # Which is which was settled on the shapes and not on the names: the
    # district CGAZ calls "Grand Anse" is centred at 55.722E, 4.327S, four
    # hundred metres from Wikidata's Grand'Anse Praslin, and the one it calls
    # "Grand'Anse" sits on Mahé. The apostrophe is on the wrong one -- reading
    # the names would have swapped them.
    ("SYC", "Anse Aux P"): "Anse aux Pins",
    ("SYC", "Grand Anse"): "Grand'Anse Praslin",
    ("SYC", "Grand'Anse"): "Grand'Anse Mahé",
    ("SYC", "Outer Isla"): "Outer Islands",
}

# The other half of the same problem, and the opposite remedy. Above, the
# boundary file is wrong and correcting it fixes both the label and the join.
# Here the boundary file is *right* -- "Sofia" is the oblast's name, "Al
# Asimah" is the governorate's, "Caprivi" is what the strip was called until
# 2013 -- and a source simply calls the place something else. Renaming the
# shape to the source's word would be a worse error than the gap it closes, so
# these are joined under an extra name and labelled under their own.
#
# Every entry was checked against the shape it claims: the source's own
# coordinate has to fall inside that shape's bounding box, which is a stronger
# test than any reading of the two names. It rejected two pairs that looked
# plausible on paper -- Trinidad and Tobago's leftover shape "Tobago" against
# the leftover row "Arima", 95 km away on the other island, and Seychelles'
# "Outer Isla" against "La Digue and Inner Islands", 1,184 km away. Neither
# has a row in the source at all, and an unmatched unit is a visible gap where
# either of those would have been an invisible lie.
# What this table cannot do, because norm() folds the words that would carry
# the distinction. "Sofia" and "Sofia City" both reduce to "sofia", as do
# "Sofia Oblast" and "Sofia City"; so do Mozambique's "Maputo" and "Maputo
# Province", and Yemen's "Sanʿaʾ" and "Sanʿaʾ Governorate". These are not
# variant names -- they are a city and the region around it colliding on one
# key -- and an alias cannot separate them, because every name anyone would
# declare lands on the same key that is already ambiguous. They are left as
# stated gaps: a declaration that does nothing is worse than the gap it claims
# to close, because it reads like the question has been settled.
ALSO_KNOWN_AS: dict[tuple[str, str], tuple[str, ...]] = {
    # Albanian and Bulgarian counties written with, and without, the word.
    ("ALB", "Dibër"): ("Dibra County", "Dibra"),
    ("ALB", "Tiranë"): ("Tirana County", "Tirana"),
    # Chile's regions in Spanish on the map, in English in the source.
    ("CHL", "Región Metropolitana de Santiago"): ("Santiago Metropolitan Region",),
    ("CHL", "Región de Magallanes y Antártica Chilena"):
        ("Magellan and the Chilean Antarctic Region",),
    ("CUB", "Isle of Youth"): ("Isla de la Juventud",),
    ("DOM", "Bahoruco"): ("Baoruco Province", "Baoruco"),
    ("DOM", "El Seybo"): ("El Seibo Province", "El Seibo"),
    # Renamed for the general in 1942; the older name is still the shape's.
    ("DOM", "La Estrelleta"): ("Elías Piña Province", "Elías Piña"),
    # "Al Asimah" is Arabic for "the Capital", which is what the source calls it.
    # Renamed Turkistan in 2018; the 2021 census row carries the new name and
    # the boundary file the old. 3.4 million people, the country's most
    # populous region, blank beside fifteen filled ones -- and the one case
    # measured in docs/MODELLING.md that would have qualified for an exact
    # residual, since the census publishes the national total and every other
    # region. Read directly instead, which is always better than derived.
    ("KAZ", "South Kazakhstan Region"): ("Turkistan Region", "Turkistan"),
    ("KWT", "Al Asimah"): ("Capital Governorate",),
    ("MAR", "Fez-Meknes"): ("Fès-Meknès",),
    # Transnistria under the name Moldova gives it in law.
    ("MDA", "Transnistria"):
        ("Administrative-Territorial Units of the Left Bank of the Dniester",),
    ("MNG", "Hovsgel"): ("Khövsgöl Province", "Khövsgöl"),
    ("MNG", "Ömnögovi"): ("Province of Umnugobi", "Umnugobi"),
    ("MRT", "Guidimaka"): ("Guidimakha",),
    # Renamed from Caprivi to Zambezi in 2013.
    ("NAM", "Caprivi"): ("Zambezi Region", "Zambezi"),
    # Renamed from South Atlantic to South Caribbean Coast in 1987.
    ("NIC", "South Atlantic Autonomous Region"):
        ("South Caribbean Coast Autonomous Region",),
    # Panama writes the word first, the source writes it last.
    ("PAN", "Comarca Emberá-Wounaan"): ("Emberá-Wounaan Comarca",),
    ("PAN", "Comarca Ngäbe-Buglé"): ("Ngöbe-Buglé Comarca", "Ngäbe-Buglé Comarca"),
    ("PAN", "Provincia de Panamá"): ("Panamá Province", "Panamá"),
    ("PNG", "Northern (Oro) Province"): ("Oro Province", "Northern Province"),
    # CGAZ shouts this one and drops the accent, alone among the seventeen
    # departments. Left as it is rather than declared a misspelling: norm()
    # folds case and accents both, so correcting it would change no join, and
    # the table above is checked for exactly that.
    ("PRY", "ASUNCION"): ("Capital District", "Distrito Capital"),
    ("SLV", "Departamento de La Paz"): ("La Paz Department",),
    ("SLV", "Departamento de Santa Ana"): ("Santa Ana Department",),
    # Srem is the Serbian name for Syrmia.
    ("SRB", "Syrmia District"): ("Srem District",),
    ("TJK", "Districts of Republican Subordination"):
        ("Districts under Central Government Jurisdiction",),
    ("TTO", "Rio Claro-Mayaro"): ("Mayaro-Rio Claro",),
    # Yemen in two romanisations. The Sanaa pair is the one that could have
    # gone wrong quietly: CGAZ draws "Sanʿaʾ" and "Sanʿaʾ Governorate", and
    # the source draws "Amanat al-Asimah Governorate" -- the capital
    # municipality -- and "Sanaa Governorate" around it. The small shape is
    # 0.11 square degrees and the large one 2.08, which settles it on size and
    # on position both, where the names alone do not.
    ("YEM", "Sanʿaʾ"): ("Amanat al-Asimah Governorate", "Amanat al-Asimah"),
    ("YEM", "Ad Dali' Governorate"): ("Dhale Governorate",),
    ("YEM", "Sa'dah Governorate"): ("Saada Governorate",),
    ("YEM", "‘Adan Governorate"): ("Aden Governorate", "Aden"),
}


def known_as(name: str, group: str | None = None) -> tuple[str, ...]:
    """The declared alternative names for a boundary-file shape, if any.

    Read after respell(), so an entry is keyed by the name a viewer sees.
    """
    if not group:
        return ()
    return ALSO_KNOWN_AS.get((group, name), ())


def respell(name: str, group: str | None = None) -> str:
    """The boundary file's name, with a declared misspelling corrected.

    Applied where the shapes are read, so the correct spelling is what the
    census join matches against as well as what a viewer sees. Without it the
    map labels a South African province "Nothern Cape" -- the data on it right,
    the name on it wrong -- and every source that spells the province correctly
    has to carry an alias to reach the shape at all.
    """
    if not group:
        return name
    return MISSPELLED.get((group, name), name)


def parse_number(text: str | None) -> float | int | None:
    if not text:
        return None
    m = re.search(_NUM, text.replace(" ", " "))
    if not m:
        return None
    raw = m.group(0).replace(",", "")
    try:
        val = float(raw)
    except ValueError:
        return None
    return int(val) if val.is_integer() else val


def parse_year(text: str | None) -> int | None:
    """Pull the reference year out of strings like ``(2022 est.)``."""
    if not text:
        return None
    years = re.findall(r"(1[89]\d{2}|20\d{2})", text)
    return int(years[-1]) if years else None


def _split_top_level(text: str, separators: str = ",") -> list[str]:
    """Split on separators that are not inside parentheses or brackets.

    The Factbook nests commas and semicolons inside its asides -- "Muslim
    (official; predominantly Sunni) 99%, other (includes Christian, Jewish...)"
    -- so a naive ``split(",")`` invents groups called "Jewish" and "and
    Anglican)". Depth tracking is what keeps those inside their own aside.
    """
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for char in text:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        if char in separators and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(char)
    parts.append("".join(buf))
    return parts


_YEAR = re.compile(r"\(\s*\d{4}")


def _pick_composition_block(text: str) -> str:
    """One composition out of a field that may carry several.

    The Factbook separates independent compositions with ``<br><br>``, and by
    the time the tags are stripped they read as one long list. Uruguay carries a
    detailed older survey followed by a 2023 estimate, so the merged reading put
    Roman Catholic in twice and totalled 158.2%.

    The most recent estimate wins, which is the last block carrying a vintage
    marker. Prose notes are dropped first: the World entry ends with three of
    them, so "take the last block" would return a sentence about how many
    languages exist rather than any figures at all.
    """
    blocks = [b for b in re.split(r"(?:<br\s*/?>\s*)+|\n{2,}", text) if b.strip()]
    if len(blocks) < 2:
        return text
    usable = [b for b in blocks
              if not re.match(r"\s*(?:<[^>]+>\s*)*note\b", b, re.I)
              and re.search(r"\d\s*%", b)]
    if not usable:
        return text
    dated = [b for b in usable if _YEAR.search(b)]
    return dated[-1] if dated else usable[0]


# A part that carries no readable share is still usually a group: the Factbook
# writes Mali's plurality language as "Bambara (official)" with no figure, and
# names South Sudan's Shilluk, Azande, Bari and fifteen more without one. Those
# used to be dropped, which is the worst of the three possible outcomes -- the
# remaining slivers were then presented as a whole composition, so Mali read as
# a country where the language half of it speaks does not exist. Keeping the
# member with an explicit gap says what the source actually says: this group is
# here, its share is not published.
#
# Three shapes are not members, and each is recognised by where it sits rather
# than by what it means:
_NOT_A_MEMBER = re.compile(
    r"^(?:including|and|or|some|mostly|mainly|largely|chiefly|such\s+as|"
    r"with|plus|note)\b", re.I)


def _shareless_member(parts: list[str], i: int) -> dict[str, Any] | None:
    """The row for a part naming a group the source gives no figure for.

    Only ever called for a text that carries at least one real share. A list
    with no figures anywhere is not a composition missing one member, it is a
    list of names, and ``parse_languages`` already renders those as the whole
    field being unquantified. Reading them here instead would turn the EU's
    24 official languages into 24 gaps in a chart nobody asked for.
    """
    part = parts[i]
    # (1) Commentary rather than a group: "including Liberian English variants"
    #     after Liberia's English, "some 839 living indigenous languages".
    if _NOT_A_MEMBER.match(part):
        return None
    # (2) A count of languages rather than a language: PNG's and the Solomon
    #     Islands' "120 indigenous languages".
    if re.match(r"^\d", part):
        return None
    # (3) One item of a name the comma-split tore apart. South Africa's
    #     "ancestral, tribal, animist, or other traditional African religions
    #     5.4%" is a single group whose share sits on the last fragment, and
    #     Botswana's bare "other" belongs to "including Kgalagadi ... 7%".
    #     What marks it is not the fragment but what closes the run it is in:
    #     a following part opening with "or" or "including" means every
    #     shareless part back to here was part of that one name.
    for j in range(i + 1, len(parts)):
        if re.match(r"^(?:or|including)\b", parts[j], re.I):
            return None
        if _SHARE.search(re.sub(r"\([^()]*\)", " ", parts[j])):
            break
    label = re.sub(r"\([^()]*\)", " ", part)
    # A figure the parser could not read -- the Factbook's "Christian 93/1%"
    # for the DRC, Andorra's "Christian 89.5" with the sign missing -- leaves
    # digits behind. The name in front of it is still the group; the mangled
    # figure is not repaired here, because inferring 93.1 from "93/1" is a
    # guess, and a named group with a stated gap is the honest reading.
    label = re.split(r"[<>\d]", label)[0]
    # Qualifiers are deliberately *not* stripped: they belong to a measurement,
    # and there is none. Rwanda's census category is "more than one language",
    # which stripping would leave as the nonsense "one language".
    label = re.sub(r"\s+", " ", label).strip(" .,;-")
    if not label or len(label) > 80 or not re.search(r"[^\W\d_]", label):
        return None
    # Cutting at the digit can leave the qualifier that introduced it and
    # nothing else -- Chad's "more than 120 languages", Niger's "over", Taiwan's
    # "approximately". A group name that is only a qualifier is not a group.
    if not _QUALIFIER.sub(" ", label).strip(" .,;-"):
        return None
    return {"group": label, "pct": None, "pct_status": NOT_AVAILABLE}


def parse_composition(text: str | None, *, source: str | None = None) -> list[dict[str, Any]] | None:
    """Turn ``"Hindu 79.8%, Muslim 14.2%, other 0.9%"`` into structured shares.

    Handles the Factbook's parenthetical asides, ``<1%`` markers and trailing
    ``(2011 est.)`` year tags.  Returns ``None`` when nothing parseable is found,
    which the caller renders as an explicit gap rather than as an empty chart.
    """
    if not text:
        return None
    # Before the tags go: they are what marks the boundary between two separate
    # compositions, and stripping them first silently welds the two together.
    text = _pick_composition_block(text)
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = clean.replace("\u00a0", " ")
    clean = re.sub(r"\s*note\s*\d*\s*:.*$", "", clean, flags=re.I | re.S)
    # Drop only the trailing vintage marker -- "(2011 est.)" -- not every aside.
    clean = re.sub(r"\((?:[^()]*?\b(?:est\.|census)\b[^()]*?|\s*\d{4}\s*)\)\s*$", " ", clean)
    # A top-level semicolon introduces commentary, not another group.
    clean = _split_top_level(clean, ";")[0]
    # A block may open with a heading -- "most-spoken language:" -- which once
    # stripped of its tags reads as part of the first group's name. Only a short
    # colon-terminated run before any figure qualifies, so a real label
    # containing a colon cannot be eaten.
    clean = re.sub(r"^[^,%:]{0,40}:\s*", "", clean.lstrip())
    # "1%-2%" is one range, written with a sign on each end. Normalising it to
    # "1-2%" lets the range arm read it, and lets an aside be judged on how many
    # figures it really carries rather than how many per-cent signs it contains.
    clean = re.sub(r"(\d[\d.,]*)\s*%\s*([-\u2013\u2014])\s*(\d[\d.,]*)\s*%",
                   r"\1\2\3%", clean)

    out: list[dict[str, Any]] = []
    parts = [p for p in (q.strip(" .") for q in _split_top_level(clean, ",")) if p]
    # Whether this text is a composition at all, which is what makes a member
    # with no figure worth recording. Decided once, over the whole text.
    quantified = _SHARE.search(clean) is not None
    for i, part in enumerate(parts):
        # Parenthetical asides go before the figure is read, not after. They
        # carry percentages of their own -- Iraq's "Muslim (official) 95-98%
        # (Shia 61-64%, Sunni 29-34%)" -- and a search that can see inside them
        # picks up a sub-split and reports it as the group's own share. It also
        # means a country whose only figures are inside an aside, as Saudi
        # Arabia's are, yields nothing and stays an honest gap.
        bare = re.sub(r"\([^()]*\)", " ", part)
        match = _SHARE.search(bare)
        if match:
            part = bare
        else:
            # Nothing outside the aside. Some asides do carry the group's own
            # share -- Sudan's "Sudanese Arab (approximately 70%)", the Solomon
            # Islands' "English (... spoken by only 1%-2% ...)" -- and dropping
            # those loses the only figure the entry has.
            #
            # Others carry a breakdown of the group instead, or a statistic
            # about something else entirely. Saudi Arabia's "(official; citizens
            # are 85-90% Sunni and 10-12% Shia)" would otherwise be read as the
            # Muslim share, and Sierra Leone's aside about Krio being "a first
            # language for 10%" as the country's whole language composition.
            # Both of those list several things: a semicolon, or more than one
            # figure. One figure and no list is the case worth trusting.
            aside = " ".join(re.findall(r"\(([^()]*)\)", part))
            match = None if (";" in aside or aside.count("%") != 1) else _SHARE.search(part)
            if not match:
                row = _shareless_member(parts, i) if quantified else None
                if row:
                    out.append(row)
                continue
        bound = match.group(1)
        low = float(match.group(2).replace(",", ""))
        high = match.group(3)
        # A range is the Factbook's way of saying it does not know precisely.
        # Dropping these rows -- which is what a pattern without the range arm
        # did -- left Greece with no Orthodox, Serbia with neither of its two
        # largest groups, and Saudi Arabia and the West Bank with nothing at
        # all, while the remaining slivers still read as a whole composition.
        # The midpoint is used and the range kept, so the figure can be shown
        # as the estimate it is rather than as false precision.
        pct = low if high is None else (low + float(high.replace(",", ""))) / 2
        label = part[: match.start()].strip(" .-")
        label = re.sub(r"\s*\([^)]*\)?\s*", " ", label)
        label = re.sub(r"\s+", " ", label)
        # A qualifier sitting between the group and its figure -- "approximately
        # 35-40%", "more than 95%" -- is part of the measurement, not of the
        # group's name. Taiwan is "Han Chinese", not "Han Chinese more than".
        # Where the qualifier is directional it is kept as a bound, which the
        # record format already carries for "<1%".
        tail = label[-24:].lower()
        if not bound:
            if re.search(r"\b(?:more than|over|at least|greater than)\s*$", tail):
                bound = ">"
            elif re.search(r"\b(?:less than|under|up to|nearly|almost|fewer than)\s*$", tail):
                bound = "<"
        label = re.sub(_QUALIFIER, " ", label)
        label = re.sub(r"\s+", " ", label).strip(" .-")
        if not label or len(label) > 80:
            continue
        row: dict[str, Any] = {"group": label, "pct": pct}
        if high is not None:
            row["range"] = [low, float(high.replace(",", ""))]
        # "<1%" is an upper bound, not a measurement; keep the distinction so a
        # chart cannot quietly promote it to an exact share.
        if bound:
            row["bound"] = bound
        out.append(row)
    return out or None


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", (text or "").lower())
    return re.sub(r"[\s_-]+", "-", text).strip("-")


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------

def write_json(path: Path, payload: Any, *, compact: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    path.write_text(text + "\n", encoding="utf-8")
    # A --out given on the command line is relative to the working directory,
    # not to ROOT, and relative_to raises rather than falling back. The write
    # has already happened by this point, so a tidier log line was taking down
    # runs whose real work had succeeded.
    try:
        shown = path.resolve().relative_to(ROOT)
    except ValueError:
        shown = path
    log(f"  wrote {shown} ({path.stat().st_size / 1e3:.0f} kB)")
    return path


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def chunked(items: Iterable[Any], size: int) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
