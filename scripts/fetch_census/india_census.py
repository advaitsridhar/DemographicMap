#!/usr/bin/env python3
"""India -- Census 2011 religion and population, by district and state.

India is the one major country in this pipeline with no statistics API. The
Registrar General publishes table C-01 (population by religious community) as
per-state XLSX workbooks through the censusindia.gov.in NADA catalogue, which
cannot be automated.

So the default path reads a **district-level CSV extract of the 2011 primary
census abstract** and aggregates it upward. Because that extract is a community
redistribution rather than an official endpoint, it is not taken on trust: every
run re-checks it against the figures the Registrar General published, and
refuses to emit anything if they drift (see ``NATIONAL_CONTROLS`` and
``validate``). The current file reproduces the official national totals exactly
-- 1,210,854,977 people, Hindu 79.80%, Muslim 14.23%, Christian 2.30%, Sikh
1.72%, Buddhist 0.70%, Jain 0.37% -- and its per-state aggregates reproduce the
independently hand-compiled rows in ``data/curated/admin1_seed.json`` to within
rounding.

Two standing caveats the app displays with every Indian figure:

* The reference year is **2011**. The next census was postponed repeatedly and
  had not been conducted at the time of writing, so India's subnational
  demographics are more than a decade old.
* India does not collect ethnicity. Scheduled Caste and Scheduled Tribe shares
  (a constitutional-schedule classification, not an ethnic one) are collected
  instead, and are emitted here as their own field rather than folded into
  "ethnicity".

**The districts moved and the census did not.** The census enumerated 640
districts; the boundary files draw 735, because India has created about a
hundred since -- Telangana replaced ten with thirty-three in 2016 alone. Those
95 extra shapes are not a join that failed. Every one of the 640 census rows
matches a shape; the surplus shapes are districts the census never counted,
and no later count exists to fill them. They are declared in
``CREATED_AFTER_2011`` with the year and the district they were carved from,
so the panel says which measurement covers their ground instead of showing an
unexplained blank. Nothing is carried down into them: a new district is a
*part* of an old one, and giving it the old one's composition would assert an
even spread inside a district that nobody measured.

**"Other religions" is the census's residual and it is not small everywhere.**
C-01 publishes six named religions, "Other religions and persuasions" and
"Religion not stated", and nothing beneath them. Nationally the residual is
7,937,734 people, 0.66%; in Arunachal Pradesh it is 362,553 people, 26.2% of
the state, and almost all of that is Donyi-Polo. The Registrar General does
publish the break-up -- table **C-01 Appendix**, *Details of religious
community shown under 'Other religions and persuasions'*, 83 named religions
including Donyi-Polo, Sarna, Sanamahi, Khasi and Niamtre -- but only for India
and the states, never by district, so a district-level figure for any of them
does not exist in any Indian census publication. Until that workbook is read,
the residual is emitted as the one group the census published, labelled the
way the census labels it.

Mother tongue (table C-16) is a separate publication and is not in this
extract; ``india_language.py`` reads it from the official workbooks.

Usage:
    python -m scripts.fetch_census.india_census --level district
    python -m scripts.fetch_census.india_census --level state
    python -m scripts.fetch_census.india_census --input data/raw/india   # XLSX
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, RAW, gap, http_get, log, measure,
    record, shares, write_json,
)

CATALOG = "https://censusindia.gov.in/nada/index.php/catalog"
CSV_URL = ("https://raw.githubusercontent.com/nishusharma1608/"
           "India-Census-2011-Analysis/master/india-districts-census-2011.csv")

SOURCE = "Census of India 2011, table C-01 (Registrar General & Census Commissioner)"
SOURCE_NOTE = ("District-level extract of the 2011 primary census abstract. Validated "
               "on every run against the Registrar General's published national totals.")

# CSV column -> display label, in the order the Registrar General reports them.
RELIGION_COLUMNS = {
    "Hindus": "Hindu",
    "Muslims": "Muslim",
    "Christians": "Christian",
    "Sikhs": "Sikh",
    "Buddhists": "Buddhist",
    "Jains": "Jain",
    "Others_Religions": "Other religions",
    "Religion_Not_Stated": "Not stated",
}
SCHEDULED_COLUMNS = {"SC": "Scheduled Caste", "ST": "Scheduled Tribe"}

# What the Registrar General published. A mirror that does not reproduce these
# is not the census, whatever it claims to be, so the run stops.
NATIONAL_CONTROLS = {
    "districts": (640, 0),           # (expected, tolerance)
    "population": (1_210_854_977, 0),
    "Hindus": (79.80, 0.05),         # percentages
    "Muslims": (14.23, 0.05),
    "Christians": (2.30, 0.05),
    "Sikhs": (1.72, 0.05),
    "Buddhists": (0.70, 0.05),
    "Jains": (0.37, 0.05),
}

# Districts the 2011 census reported under a name the current boundary files
# spell differently. Renames only -- never a merge or a split.
DISTRICT_ALIASES = {
    "y.s.r.": "Kadapa(YSR)",
    "pondicherry": "Puducherry",
    # Spellings the boundary files get wrong, or spell differently. Both of
    # these cost the district its religion figures as well as its languages,
    # and Hyderabad is not a place to leave blank over a missing vowel.
    "hyderabad": "Hydrabad",
    "mahbubnagar": "Mahabubnagar",
}

# States the 2011 census reported under a different name.
STATE_ALIASES = {
    "orissa": "Odisha",              # renamed 2011
    "pondicherry": "Puducherry",     # renamed 2006
    "nct of delhi": "NCT of Delhi",
}

# States that did not exist at the 2011 census, so no census row covers them.
# Their territory was enumerated under the predecessor state; splitting that
# retrospectively would be an estimate, not a measurement, so they get an
# explicit gap carrying the reason.
FORMED_AFTER_2011 = {
    "Telangana": ("Telangana was formed in 2014 from ten districts of Andhra "
                  "Pradesh. The 2011 census enumerated that territory as part of "
                  "Andhra Pradesh, so no census figure exists for Telangana as "
                  "such. Its districts do carry 2011 figures."),
    "Ladakh": ("Ladakh became a union territory in 2019, split from Jammu and "
               "Kashmir. The 2011 census enumerated it as part of Jammu and "
               "Kashmir, so no census figure exists for Ladakh as such. Its "
               "districts (Leh, Kargil) do carry 2011 figures."),
}

# 2011 districts that have since been subdivided, so one census row covers
# several present-day boundary units. Their figures are deliberately NOT
# spread across the successors: the census never measured those areas
# separately, and inventing a split would be fabrication. The successors keep
# an explicit gap carrying this explanation.
#
# These are the three where the 2011 name survives on no present-day shape at
# all, so the census row has nowhere to go. A district that merely *lost*
# territory to a new one keeps its name, keeps its shape and keeps its 2011
# row; the new district is in CREATED_AFTER_2011 below.
SUBDIVIDED_SINCE_2011 = {
    "jaintia hills": ["East Jaintia Hills", "West Jaintia Hills"],
    "karbi anglong": ["Karbi Anglong East", "Karbi Anglong West"],
    # Warangal was split six ways in 2016. Two of the successors carry its
    # name and are listed here because they are what the census row would
    # otherwise be matched to; the other four (Jangaon, Jayashankar,
    # Mahabubabad, Mulugu) are named districts of their own and are in
    # CREATED_AFTER_2011. None of the six carries a 2011 figure either way.
    "warangal": ["Warangal (R)", "Warangal (U)"],
}

# The state each present-day state's ground was enumerated under in 2011,
# where that is not the state itself. Only needed to check a predecessor
# against the census's own state column, which still says Andhra Pradesh for
# what is now Telangana.
STATE_IN_2011 = {
    "Telangana": "Andhra Pradesh",
    "Ladakh": "Jammu and Kashmir",
    "Delhi": "NCT of Delhi",
}

# Districts the boundary files draw that the 2011 census never enumerated,
# because they did not exist yet. India has created about a hundred districts
# since 2011 -- Telangana alone replaced ten with thirty-three in 2016 -- and
# the next census, due in 2021, has still not been held, so there is no later
# count to reach for.
#
# Without this table each of them was a blank panel with no reason in it: 92 of
# India's 735 second-level shapes, a seventh of the country, saying nothing at
# all. That is the failure mode this project exists to avoid. A gap has to say
# why it is a gap.
#
# What is deliberately NOT done here is carry the predecessor's figures down.
# A new district is a *part* of an old one, and giving it the old one's
# composition would assert that religion is distributed evenly inside a
# district, which no census measured and which is plainly false where a new
# district was carved along a communal or tribal line. The map's standing rule
# (see the Bahamas' island groupings, and korea_survey.py, which is the one
# stated exception) is that a figure coarser than the shape is not spread
# across the shape's members.
#
# Each entry is (name as the boundary file spells it, year created, the 2011
# districts it was carved out of), grouped by present-day state. The
# predecessors are checked against the census's own district list on every run
# (:func:`check_new_districts`), so a misspelling or a wrong parent stops the
# run rather than shipping as prose nobody re-reads. Sources are the state
# reorganisation notifications as reported by the district administrations
# themselves; the years are the year the district became operational.
CREATED_AFTER_2011: dict[str, tuple[tuple[str, int, tuple[str, ...]], ...]] = {
    "Arunachal Pradesh": (
        ("Kamle", 2017, ("Lower Subansiri", "Upper Subansiri")),
        ("Kra Daadi", 2015, ("Kurung Kumey",)),
        ("Leparada", 2018, ("West Siang",)),
        ("Longding", 2012, ("Tirap",)),
        ("Lower Siang", 2017, ("West Siang", "East Siang")),
        ("Namsai", 2014, ("Lohit",)),
        ("Pakke Kessang", 2018, ("East Kameng",)),
        ("Shi Yomi", 2018, ("West Siang",)),
        ("Siang", 2015, ("West Siang", "East Siang")),
    ),
    "Assam": (
        ("Biswanath", 2015, ("Sonitpur",)),
        ("Charaideo", 2015, ("Sivasagar",)),
        ("Hojai", 2015, ("Nagaon",)),
        ("Majuli", 2016, ("Jorhat",)),
        ("South Salmara-Mankachar", 2016, ("Dhubri",)),
    ),
    "Chhattisgarh": (
        ("Balod", 2012, ("Durg",)),
        ("Baloda Bazar", 2012, ("Raipur",)),
        ("Balrampur", 2012, ("Surguja",)),
        ("Bemetra", 2012, ("Durg",)),
        ("Gariaband", 2012, ("Raipur",)),
        ("Gaurella Pendra Marwahi", 2020, ("Bilaspur",)),
        ("Kondagaon", 2012, ("Bastar",)),
        ("Mungeli", 2012, ("Bilaspur",)),
        ("Sukma", 2012, ("Dakshin Bastar Dantewada",)),
        ("Surajpur", 2012, ("Surguja",)),
    ),
    "Delhi": (
        ("Shahdara", 2012, ("East", "North East")),
        ("South East", 2012, ("South",)),
    ),
    "Gujarat": (
        ("Aravali", 2013, ("Sabar Kantha",)),
        ("Batod", 2013, ("Bhavnagar", "Ahmadabad")),
        ("Chhota Udaipur", 2013, ("Vadodara",)),
        ("Devbhumi Dwarka", 2013, ("Jamnagar",)),
        ("Gir Somnath", 2013, ("Junagadh",)),
        ("Mahisagar", 2013, ("Panch Mahals", "Kheda")),
        ("Morbi", 2013, ("Rajkot", "Jamnagar", "Surendranagar")),
    ),
    "Madhya Pradesh": (
        ("Agar", 2013, ("Shajapur",)),
        ("Niwari", 2018, ("Tikamgarh",)),
    ),
    "Maharashtra": (
        ("Palghar", 2014, ("Thane",)),
    ),
    "Manipur": (
        ("Jiribam", 2016, ("Imphal East",)),
        ("Kakching", 2016, ("Thoubal",)),
        ("Kamjong", 2016, ("Ukhrul",)),
        ("Kangpokpi", 2016, ("Senapati",)),
        ("Noney", 2016, ("Tamenglong",)),
        ("Pherzawl", 2016, ("Churachandpur",)),
        ("Tengnoupal", 2016, ("Chandel",)),
    ),
    "Meghalaya": (
        ("North Garo Hills", 2012, ("East Garo Hills",)),
        ("South West Garo Hills", 2012, ("West Garo Hills",)),
        ("South West Khasi Hills", 2012, ("West Khasi Hills",)),
    ),
    "Mizoram": (
        ("Hnahthial", 2019, ("Lunglei",)),
        ("Khawzawl", 2019, ("Champhai",)),
        ("Saitual", 2019, ("Aizawl",)),
    ),
    "Punjab": (
        ("Fazilka", 2011, ("Firozpur",)),
        ("Pathankot", 2011, ("Gurdaspur",)),
    ),
    "Tamil Nadu": (
        ("Chengalputtu", 2019, ("Kancheepuram",)),
        ("Kallakurichi", 2019, ("Viluppuram",)),
        ("Mayiladuthurai", 2020, ("Nagapattinam",)),
        ("Ranipet", 2019, ("Vellore",)),
        ("Tenkasi", 2019, ("Tirunelveli",)),
        ("Tirupathur", 2019, ("Vellore",)),
    ),
    # Telangana's 2016 reorganisation, which turned ten districts into
    # thirty-three. Every predecessor here is a district the 2011 census
    # enumerated under ANDHRA PRADESH, because Telangana did not exist.
    "Telangana": (
        ("Bhadradri", 2016, ("Khammam",)),
        ("Jagtial", 2016, ("Karimnagar",)),
        ("Jangaon", 2016, ("Warangal",)),
        ("Jayashankar", 2016, ("Warangal",)),
        ("Jogulamba", 2016, ("Mahbubnagar",)),
        ("Kamareddy", 2016, ("Nizamabad",)),
        ("Komaram Bheem", 2016, ("Adilabad",)),
        ("Mahabubabad", 2016, ("Warangal",)),
        ("Mancherial", 2016, ("Adilabad",)),
        ("Medchal", 2016, ("Rangareddy",)),
        ("Mulugu", 2019, ("Warangal",)),
        ("Nagarkurnool", 2016, ("Mahbubnagar",)),
        ("Narayanpet", 2019, ("Mahbubnagar",)),
        ("Nirmal", 2016, ("Adilabad",)),
        ("Peddapalli", 2016, ("Karimnagar",)),
        ("Rajanna Sircilla", 2016, ("Karimnagar",)),
        ("Sangareddy", 2016, ("Medak",)),
        ("Siddipet", 2016, ("Medak",)),
        ("Suryapet", 2016, ("Nalgonda",)),
        ("Vikarabad", 2016, ("Rangareddy",)),
        ("Wanaparthy", 2016, ("Mahbubnagar",)),
        ("Yadadri Bhongiri", 2016, ("Nalgonda",)),
    ),
    "Tripura": (
        ("Gomati", 2012, ("South Tripura",)),
        ("Khowai", 2012, ("West Tripura",)),
        ("Sipahijula", 2012, ("West Tripura",)),
        ("Unokoti", 2012, ("North Tripura",)),
    ),
    # Uttar Pradesh's four are the closest call in this table. Amethi was
    # notified in 2010 and the other three in September 2011, all of them
    # before the census published -- but the census enumerated the district
    # frame as it stood earlier, and its 640 rows contain none of the four. So
    # "created after the census" is the right description of the gap even
    # where the notification predates the publication.
    "Uttar Pradesh": (
        ("Amethi", 2010, ("Sultanpur", "Rae Bareli")),
        ("Hapur", 2011, ("Ghaziabad",)),
        ("Sambhal", 2011, ("Moradabad",)),
        ("Samli", 2011, ("Muzaffarnagar",)),
    ),
    "West Bengal": (
        ("Alipurduar", 2014, ("Jalpaiguri",)),
        ("Jhargram", 2017, ("Paschim Medinipur",)),
        ("Kalimpong", 2017, ("Darjiling",)),
        ("Paschim Barddhaman", 2017, ("Barddhaman",)),
    ),
}

# The window a creation year has to fall in for the entry to be about a
# post-census district at all. The floor is 2010 rather than 2011 because
# Uttar Pradesh notified Amethi in July 2010 and the census still enumerated
# its ground under Sultanpur and Rae Bareli -- the frame the census counted was
# fixed before the district was. The ceiling is a boundary-file fact: CGAZ
# draws India as it stood in the early 2020s, so a district created later has
# no shape here to attach a note to.
EARLIEST_NEW_DISTRICT, LATEST_NEW_DISTRICT = 2010, 2022

# Spellings the boundary file uses that are not the district's usual name.
# Declared as aliases so the join survives geoBoundaries correcting one of
# them, which it has done before.
NEW_DISTRICT_ALIASES = {
    "Batod": "Botad",
    "Bemetra": "Bemetara",
    "Chengalputtu": "Chengalpattu",
    "Sipahijula": "Sepahijala",
    "Unokoti": "Unakoti",
    "Samli": "Shamli",
    "Pakke Kessang": "Pakke-Kessang",
    "Leparada": "Lepa Rada",
    "Aravali": "Aravalli",
    "Devbhumi Dwarka": "Devbhoomi Dwarka",
    "Chhota Udaipur": "Chhota Udepur",
    "Agar": "Agar Malwa",
    "Bhadradri": "Bhadradri Kothagudem",
    "Jayashankar": "Jayashankar Bhupalpally",
    "Jogulamba": "Jogulamba Gadwal",
    "Komaram Bheem": "Kumuram Bheem Asifabad",
    "Medchal": "Medchal-Malkajgiri",
    "Yadadri Bhongiri": "Yadadri Bhuvanagiri",
    "Tirupathur": "Tirupattur",
    "Gaurella Pendra Marwahi": "Gaurela-Pendra-Marwahi",
}

# geoBoundaries draws one more second-level feature in Jammu and Kashmir than
# the state has districts and names it, literally, "DATA NOT AVAILABLE". It is
# not a district and never will carry a figure: it is 268 disjoint fragments
# totalling about 390 square kilometres -- one piece of 216 and 267 with a
# median area of under three hectares -- which is the sliver left over where
# the district polygons do not quite meet. Every one of the state's 22 census
# districts is drawn separately and matched. Saying so is better than leaving a
# shape on the map whose only label is the words "data not available".
BOUNDARY_ARTEFACTS = {
    "DATA NOT AVAILABLE": (
        "Jammu and Kashmir",
        "This is not a district. geoBoundaries carries one second-level "
        "feature in Jammu and Kashmir under this name, made of 268 disjoint "
        "fragments totalling about 390 square kilometres -- the slivers left "
        "between the district polygons where their edges do not meet. All 22 "
        "districts the 2011 census enumerated in the state are drawn "
        "separately and do carry figures."),
}


def cell(row: dict[str, str], key: str) -> int:
    raw = row.get(key)
    if raw in (None, "", "NA", "N/A"):
        return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


def load_csv(url: str, cache: bool = True) -> list[dict[str, str]]:
    text = http_get(url, cache=cache, timeout=300)
    assert isinstance(text, str)
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def validate(rows: list[dict[str, str]]) -> None:
    """Refuse to emit anything unless the extract reproduces the official totals."""
    problems: list[str] = []

    expected, tol = NATIONAL_CONTROLS["districts"]
    if abs(len(rows) - expected) > tol:
        problems.append(f"{len(rows)} districts, expected {expected}")

    total = sum(cell(r, "Population") for r in rows)
    expected, tol = NATIONAL_CONTROLS["population"]
    if abs(total - expected) > tol:
        problems.append(f"population {total:,}, expected {expected:,}")

    for column in RELIGION_COLUMNS:
        control = NATIONAL_CONTROLS.get(column)
        if not control or not total:
            continue
        expected, tol = control
        got = 100.0 * sum(cell(r, column) for r in rows) / total
        if abs(got - expected) > tol:
            problems.append(f"{column} {got:.2f}%, expected {expected:.2f}%")

    if problems:
        raise SystemExit(
            "india_census: the extract does not reproduce the Registrar General's "
            "published Census 2011 totals, so it is not being used:\n  - "
            + "\n  - ".join(problems)
            + f"\nCheck the source ({CSV_URL}) or download the official C-01 "
              f"workbooks from {CATALOG} and re-run with --input.")

    log(f"  validated against published national totals: {len(rows)} districts, "
        f"{total:,} people")


def enumerated(rows: list[dict[str, str]]) -> set[tuple[str, str]]:
    """Every (state, district) the 2011 census actually enumerated, casefolded.

    The census's own spellings, before DISTRICT_ALIASES renames anything to the
    boundary file's: this is what the declarations below are checked against,
    and checking a declaration against a table this module also wrote would
    check nothing.
    """
    return {((row.get("State name") or "").strip().casefold(),
             (row.get("District name") or "").strip().casefold())
            for row in rows if (row.get("District name") or "").strip()}


def check_new_districts(rows: list[dict[str, str]]) -> None:
    """CREATED_AFTER_2011 must be a table of gaps, not a table of mistakes.

    Two ways it could be wrong, and both are worse than the blank it replaces.
    A district declared here that the census *did* enumerate would hide a real
    measurement behind a note saying none exists. A predecessor named here that
    is not a 2011 district of the right state is a claim about where these
    people were counted that nothing supports -- a spelling the census does not
    use, or a parent taken from the wrong state, either of which would ship as
    confident prose that happens to be false.

    So both are arithmetic against the census's own district list, on every
    run, and either stops the run.
    """
    census = enumerated(rows)
    successors = {name for names in SUBDIVIDED_SINCE_2011.values() for name in names}
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()

    for state, entries in CREATED_AFTER_2011.items():
        state_2011 = STATE_IN_2011.get(state, state).casefold()
        for name, year, predecessors in entries:
            key = (state, name)
            if key in seen:
                problems.append(f"{state} / {name} is declared twice")
            seen.add(key)
            if name in successors:
                problems.append(f"{state} / {name} is also declared a successor "
                                f"in SUBDIVIDED_SINCE_2011")
            if (state_2011, name.casefold()) in census:
                problems.append(
                    f"{state} / {name} is declared as created after 2011, but the "
                    f"census enumerated a district of that name -- declaring it a "
                    f"gap would hide a real figure")
            if not predecessors:
                problems.append(f"{state} / {name} names no predecessor")
            for predecessor in predecessors:
                if (state_2011, predecessor.casefold()) not in census:
                    problems.append(
                        f"{state} / {name}: '{predecessor}' is not a 2011 census "
                        f"district of {STATE_IN_2011.get(state, state)}")
            if not EARLIEST_NEW_DISTRICT <= year <= LATEST_NEW_DISTRICT:
                problems.append(f"{state} / {name}: year {year} is outside "
                                f"{EARLIEST_NEW_DISTRICT}-{LATEST_NEW_DISTRICT}, "
                                f"so it is a typo rather than a creation year")

    for name, (state, _) in BOUNDARY_ARTEFACTS.items():
        state_2011 = STATE_IN_2011.get(state, state).casefold()
        if (state_2011, name.casefold()) in census:
            problems.append(f"{state} / {name} is declared a boundary artefact "
                            f"but the census enumerated it")

    if problems:
        raise SystemExit(
            "india_census: the post-2011 district table does not agree with the "
            "census's own district list, so nothing is being emitted:\n  - "
            + "\n  - ".join(problems))


def subdivided_reason(undivided: str) -> str:
    """Why a successor of a district the census never split carries no figure.

    One string, used by this file and by india_language.py, because the two
    emit a record under the same id for the same shape and whichever runs last
    overwrites the other's gap. A gap that has lost its reason on the way
    through is indistinguishable from a blank nobody thought about.
    """
    return (f"The 2011 census reported this area as part of the undivided "
            f"{undivided} district, which has since been subdivided. The census "
            f"never measured the successor districts separately, and splitting "
            f"one figure between them would be an estimate rather than a "
            f"measurement.")


def created_reason(name: str, year: int, predecessors: tuple[str, ...]) -> str:
    """Why a district created after the census carries no figure, and where its
    people were counted instead.

    The last sentence differs by predecessor for a reason the reader can act
    on: where the predecessor is still a district, its 2011 row is on this map
    under that name and covers this ground as well, so the figure is one click
    away. Where the predecessor was itself abolished -- Warangal, Jaintia
    Hills, Karbi Anglong -- the row is on no shape at all, and saying "look at
    the parent" would send the reader somewhere that does not exist.
    """
    orphaned = [p for p in predecessors if p.casefold() in SUBDIVIDED_SINCE_2011]
    listed = " and ".join(predecessors)
    note = (f"{name} did not exist at the 2011 census: it was created in {year}, "
            f"out of {listed}. The census enumerated 640 districts and this is "
            f"not one of them, and India's next census -- due in 2021 -- has not "
            f"been held, so no census figure exists for this district at all. ")
    if orphaned:
        note += (f"{' and '.join(orphaned)} has itself since been subdivided, so "
                 f"the 2011 row covering this ground is on no district on this "
                 f"map either; the state total carries it.")
    else:
        note += (f"The 2011 figures for {listed} are on this map under that name "
                 f"and cover this ground too. They are not split across it here: "
                 f"the census never measured the split, and a share invented for "
                 f"the part would be an estimate wearing a measurement's clothes.")
    return note


def new_districts() -> list[dict[str, Any]]:
    """One explicit gap record per post-2011 district, and one per artefact shape.

    These carry no figures by construction. What they carry is the reason, the
    year and the predecessor, so the panel says why it is empty instead of
    being empty.
    """
    out: list[dict[str, Any]] = []
    for state, entries in CREATED_AFTER_2011.items():
        for name, year, predecessors in entries:
            reason = created_reason(name, year, predecessors)
            alias = NEW_DISTRICT_ALIASES.get(name)
            out.append(record(
                f"IND-NEW-{state.replace(' ', '-')}-{name.replace(' ', '-')}",
                name, level="admin2", parent="IND",
                parent_name=state,
                aliases=[alias] if alias else None,
                population=gap(NOT_AVAILABLE, reason),
                religion=gap(NOT_AVAILABLE, reason),
                language=gap(NOT_AVAILABLE, reason),
                ethnicity=gap(NOT_COLLECTED, "India does not collect ethnicity."),
                sources=[{"field": "note", "name": SOURCE, "url": CATALOG}],
            ))
    for name, (state, reason) in BOUNDARY_ARTEFACTS.items():
        out.append(record(
            f"IND-ARTEFACT-{state.replace(' ', '-')}-{name.replace(' ', '-')}",
            name, level="admin2", parent="IND", parent_name=state,
            population=gap(NOT_AVAILABLE, reason),
            religion=gap(NOT_AVAILABLE, reason),
            language=gap(NOT_AVAILABLE, reason),
            ethnicity=gap(NOT_COLLECTED, "India does not collect ethnicity."),
            sources=[{"field": "note", "name": SOURCE, "url": CATALOG}],
        ))
    return out


def build_record(name: str, counts: collections.Counter, *, level: str,
                 parent: str, entity_id: str, codes: dict[str, Any]) -> dict[str, Any]:
    population = counts["Population"]
    religion_counts = {label: counts[col] for col, label in RELIGION_COLUMNS.items()
                       if counts[col]}
    scheduled_counts = {label: counts[col] for col, label in SCHEDULED_COLUMNS.items()
                        if counts[col]}

    males, females = counts["Male"], counts["Female"]
    sex_ratio = round(1000.0 * females / males) if males else None

    return record(
        entity_id, name, level=level, parent=parent, codes=codes,
        population=(measure(population, year=2011, source=SOURCE)
                    if population else gap(NOT_AVAILABLE)),
        sex_ratio=(measure(sex_ratio, unit="females_per_1000_males",
                           year=2011, source=SOURCE)
                   if sex_ratio else gap(NOT_AVAILABLE)),
        religion=shares(religion_counts, total=population) or gap(NOT_AVAILABLE),
        religion_note=("Census of India 2011 table C-01. India's next census was "
                       "postponed, so these remain the most recent official figures."),
        religion_year=2011,
        scheduled_groups=shares(scheduled_counts, total=population) or gap(NOT_AVAILABLE),
        scheduled_groups_note=(
            "Scheduled Caste and Scheduled Tribe shares (Census 2011). These are "
            "constitutional-schedule classifications used for reservation policy, "
            "not ethnic categories, and the two do not overlap."),
        ethnicity=gap(NOT_COLLECTED,
                      "India does not collect ethnicity. Scheduled Caste / Scheduled "
                      "Tribe status and mother tongue are collected instead."),
        # A placeholder, not a finding: india_language.py reads C-16 for all 35
        # states and overwrites this on every unit the census enumerated. It
        # survives only where that file was not run, so it names the command
        # rather than describing a property of India.
        language=gap(NOT_AVAILABLE,
                     "India does ask mother tongue -- Census 2011 table C-16 -- but "
                     "publishes it as a workbook per state rather than through any "
                     "API. Those workbooks are read by a separate adapter "
                     "(python -m scripts.fetch_census.india_language), which has "
                     "not been run against this unit."),
        sources=[{"field": "population/religion/scheduled groups", "name": SOURCE,
                  "url": CATALOG, "year": 2011,
                  "license": "Government of India open data (GODL-India)",
                  "note": SOURCE_NOTE}],
    )


def districts(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    numeric = list(RELIGION_COLUMNS) + list(SCHEDULED_COLUMNS) + ["Population", "Male", "Female"]

    for row in rows:
        name = (row.get("District name") or "").strip()
        if not name:
            continue
        key = name.lower()
        counts = collections.Counter({col: cell(row, col) for col in numeric})
        code = (row.get("District code") or "").strip()

        if key in SUBDIVIDED_SINCE_2011:
            # One census row, several present-day districts: emit the gap, not a guess.
            # Every field the census would have filled carries the reason, not
            # just religion: a bare gap left on population or language is one
            # that india_language.py's own bare gap can overwrite, and then the
            # shape goes back to saying nothing.
            reason = subdivided_reason(name)
            for successor in SUBDIVIDED_SINCE_2011[key]:
                out.append(record(
                    f"IND-D{code}-{successor}", successor, level="admin2", parent="IND",
                    population=gap(NOT_AVAILABLE, reason),
                    religion=gap(NOT_AVAILABLE, reason),
                    language=gap(NOT_AVAILABLE, reason),
                    ethnicity=gap(NOT_COLLECTED,
                                  "India does not collect ethnicity."),
                    sources=[{"field": "note", "name": SOURCE, "url": CATALOG}],
                ))
            continue

        state = (row.get("State name") or "").strip()
        record_ = build_record(
            DISTRICT_ALIASES.get(key, name), counts,
            level="admin2", parent="IND", entity_id=f"IND-D{code}",
            codes={"census2011_district": code, "state_name": state})
        # District names repeat across states; the state is what disambiguates.
        record_["parent_name"] = STATE_ALIASES.get(
            state.lower(), state.title().replace(" And ", " and ").replace(" Of ", " of "))
        out.append(record_)

    # The shapes the census has no row for at all, each carrying why.
    check_new_districts(rows)
    out.extend(new_districts())
    return out


def states(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """State totals summed from the district rows.

    Plain arithmetic on official counts, not estimation: the sums reproduce the
    published state populations exactly.
    """
    numeric = list(RELIGION_COLUMNS) + list(SCHEDULED_COLUMNS) + ["Population", "Male", "Female"]
    agg: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for row in rows:
        state = (row.get("State name") or "").strip()
        if not state:
            continue
        for col in numeric:
            agg[state][col] += cell(row, col)

    out = []
    for state, counts in sorted(agg.items()):
        # The extract shouts state names; the boundary files use title case.
        name = state.title().replace(" And ", " and ").replace(" Of ", " of ")
        name = STATE_ALIASES.get(state.lower(), name)
        out.append(build_record(
            name, counts, level="admin1", parent="IND",
            entity_id=f"IND-S-{name.replace(' ', '-')}",
            codes={"census2011_state_name": state}))

    for name, reason in FORMED_AFTER_2011.items():
        out.append(record(
            f"IND-S-{name.replace(' ', '-')}", name, level="admin1", parent="IND",
            religion=gap(NOT_AVAILABLE, reason),
            population=gap(NOT_AVAILABLE, reason),
            # Mother tongue too, and for the same reason. C-16 has no row for
            # a state that did not exist, so india_language.py emits nothing
            # here -- which left Telangana the one first-level unit in India
            # whose language panel was blank with nothing in it to say why.
            language=gap(NOT_AVAILABLE, reason),
            ethnicity=gap(NOT_COLLECTED, "India does not collect ethnicity."),
            sources=[{"field": "note", "name": SOURCE, "url": CATALOG}],
        ))
    return out


# ---------------------------------------------------------------------------
# Legacy path: official per-state XLSX workbooks
# ---------------------------------------------------------------------------

def read_workbook(path: Path) -> list[dict[str, Any]]:
    """Read one downloaded C-01 workbook.  Requires ``openpyxl`` for .xlsx."""
    if path.suffix.lower() in {".xlsx", ".xls"}:
        try:
            import openpyxl
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("pip install openpyxl to read censusindia workbooks") from exc
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheet = book[book.sheetnames[0]]
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    else:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            rows = [row for row in csv.reader(fh)]

    header_idx = next((i for i, row in enumerate(rows)
                       if any(isinstance(c, str) and "hindu" in c.lower() for c in row)), None)
    if header_idx is None:
        return []
    header = [str(c or "").strip().lower() for c in rows[header_idx]]
    return [dict(zip(header, row)) for row in rows[header_idx + 1:] if any(row)]


def from_workbooks(folder: Path, level: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    columns = {"hindu": "Hindus", "muslim": "Muslims", "christian": "Christians",
               "sikh": "Sikhs", "buddhist": "Buddhists", "jain": "Jains"}
    for path in sorted(folder.glob("*")):
        if path.suffix.lower() not in {".xlsx", ".xls", ".csv"}:
            continue
        for row in read_workbook(path):
            name = str(row.get("area name") or row.get("name") or "").strip()
            if not name:
                continue
            counts = collections.Counter()
            for header, column in columns.items():
                value = next((v for k, v in row.items() if k.startswith(header)), None)
                if isinstance(value, (int, float)):
                    counts[column] = int(value)
            counts["Population"] = int(row.get("total population") or sum(counts.values()))
            code = str(row.get("state code") or row.get("district code") or name).strip()
            out.append(build_record(
                name.title(), counts,
                level="admin1" if level == "state" else "admin2",
                parent="IND", entity_id=f"IND-{code}",
                codes={"census2011": code}))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="district", choices=["state", "district"])
    ap.add_argument("--csv-url", default=CSV_URL,
                    help="district-level Census 2011 extract to read")
    ap.add_argument("--input", type=Path, default=None,
                    help="directory of official C-01 workbooks; overrides --csv-url")
    ap.add_argument("--list-sources", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if args.list_sources:
        print(f"Census of India 2011 NADA catalogue: {CATALOG}")
        print("  C-01  Population by religious community")
        print("  C-16  Population by mother tongue")
        print(f"District-level extract used by default: {args.csv_url}")
        return 0

    if args.input:
        log(f"india_census: reading workbooks from {args.input}")
        if not args.input.exists():
            log("  no such directory; run with --list-sources for the download URLs")
            return 1
        records = from_workbooks(args.input, args.level)
    else:
        log(f"india_census: Census 2011, level={args.level}")
        rows = load_csv(args.csv_url)
        validate(rows)
        records = states(rows) if args.level == "state" else districts(rows)

    out = args.out or PROCESSED / f"india_{args.level}.json"
    write_json(out, records)
    with_religion = sum(1 for r in records if isinstance(r.get("religion"), list))
    # A gap that names its reason is a result, so it is counted as one. The
    # number that would be alarming is a gap with an empty note, and there is
    # no path through this module that can produce one.
    explained = sum(1 for r in records
                    if not isinstance(r.get("religion"), list)
                    and (r.get("religion") or {}).get("note"))
    log(f"  {len(records)} records, {with_religion} with religion shares, "
        f"{explained} explicit gaps carrying their reason")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
