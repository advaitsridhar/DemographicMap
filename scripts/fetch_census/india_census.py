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
95 extra shapes are not a join that failed. They are districts the census never
counted, and no later count exists to fill them. They are declared in
``CREATED_AFTER_2011`` with the year and the district they were carved from, so
the panel says which measurement covers their ground instead of showing an
unexplained blank. Nothing is carried down into them: a new district is a
*part* of an old one, and giving it the old one's composition would assert an
even spread inside a district that nobody measured.

**And the district that keeps the name is a part of it too.** That is the half
this file had wrong for longer than the other. When Jagtial, Peddapalli and
Rajanna Sircilla were carved out of Karimnagar in 2016, the shape still called
Karimnagar kept its name and lost three quarters of its ground -- and kept the
undivided district's 3,776,269 people, on a shape that holds about a quarter of
them. A blank beside it said honestly that no figure existed for Jagtial; the
number next to it said, with a source and a year, something that was not about
the shape it sat on. 75 districts across 16 states were in that position,
carrying 172 million people's worth of 2011 figures between them.
``LOST_TERRITORY_SINCE_2011`` declares every one, with the share of its 2011
ground the shape still covers, and every one carries its census figure together
with a sentence saying what that figure is for.

Blanking them was tried first and was the wrong call. The number is the
Registrar General's, it is for a district of this name, and deleting it cost
the map 172 million people's worth of coverage to fix a problem that was never
that the figure is wrong -- only that it was silently about more ground than
the shape covers. The cure for silent is a sentence, which is the trade this
project makes everywhere else: a country roll-up that names the divisions it
leaves out, a summed parent that names the figure it displaced. It is a better
trade here than most, because the *shares* survive a boundary change far better
than the counts do. Religion does not reorganise itself along a new district
line, so the choropleth -- which shades by share -- is close to right, and it
is the head count in the panel that covers more ground than the shape does.
The note says so, on every field the census row filled.

What *would* fill all of them is a level down, and the route is real enough to
be worth stating precisely. C-01 **is** published to sub-district: the official
per-state workbook for Andhra Pradesh carries 1,128 tehsil rows beside its 23
district rows, and they sum to the district totals exactly. C-16 is published
the same way. What does not exist is the other half of the join -- a mapping
from 2011 sub-districts to present-day districts. The census does not publish
one, and the 2016 reorganisation did not merely reallocate mandals but split
some of them, so even a hand-built mapping would not be a partition. Writing
one out would be inventing the very thing the sub-district tables were supposed
to supply, so it is not done here.

**"Other religions" is the census's residual and it is not small everywhere.**
C-01 publishes six named religions, "Other religions and persuasions" and
"Religion not stated", and nothing beneath them. Nationally that residual is
7,937,734 people, 0.66%; in Arunachal Pradesh it is 362,553 people, 26.2% of
the state, and calling a quarter of a state "other religions" is not a
description of it. The Registrar General does publish the break-up -- table
**C-01 Appendix**, *Details of religious community shown under 'Other
religions and persuasions' in main table C-01* -- and at ``--level state`` it
is read here, so Donyi-Polo, Sarna, Sanamahi, Khasi and the rest appear as
themselves.

The Appendix is published **for India and the states and nothing finer**. Its
sheet has a district column and it reads zero on every row, which
:func:`read_appendix` checks rather than assumes, and refuses on if it ever
does not. So there is no district-level figure for any of these religions in
any Indian census publication; a state's districts keep C-01's undivided
residual, and the note on the state record says why.

Mother tongue (table C-16) is a separate publication and is not in this
extract; ``india_language.py`` reads it from the official workbooks.

Usage:
    python -m scripts.fetch_census.india_census --level district
    python -m scripts.fetch_census.india_census --level state
    python -m scripts.fetch_census.india_census --level state --no-appendix
    python -m scripts.fetch_census.india_census --input data/raw/india   # XLSX
"""

from __future__ import annotations

import argparse
import collections
import csv
import difflib
import io
import urllib.parse
from pathlib import Path
from typing import Any, NamedTuple

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

# States that did not exist at the 2011 census, whose territory is nonetheless
# a whole number of districts the census *did* enumerate.
#
# This is the one place where a figure nobody published may honestly be
# assembled, and it is worth being exact about why. Telangana was formed in
# 2014 out of ten districts of Andhra Pradesh; the census enumerated all ten
# separately, and ten disjoint measurements that exhaust a territory sum to a
# measurement of that territory. Nothing is apportioned, nothing is estimated,
# and the residual state is the same arithmetic run the other way. The
# alternative -- the gap this replaced -- said "no census figure exists for
# Telangana as such", which was true of the *published tables* and false of the
# *census*: every person in Telangana was counted in 2011, in one of these ten
# rows.
#
# Each entry names the districts on both sides and the published totals both
# sides must reproduce **to the person**; ``check_splits`` refuses to emit
# anything if they do not. The district codes are carried as well as the names
# because the C-16 mother-tongue workbooks key on the code and the C-01 extract
# on the name, and a split that is right in one table and wrong in the other is
# exactly the failure neither file could see on its own.
class StateSplit(NamedTuple):
    parent: str                    # the state the 2011 census enumerated
    state_code: str                # its census state code, as C-16 writes it
    year: int                      # when the new state came into being
    districts: tuple[str, ...]     # the 2011 districts that became the new state
    codes: tuple[int, ...]         # ... and their census district codes
    population: int                # published 2011 population of the new state
    residual: int                  # ... and of what was left of the old one
    caveat: str                    # what the new state's sum does not cover
    residual_caveat: str           # ... and the same fact from the other side


SPLIT_STATES: dict[str, StateSplit] = {
    # Andhra Pradesh's ten Telangana districts. 532-541 in the census's own
    # numbering, contiguous, and 542-554 are the thirteen that stayed.
    #
    # The caveat is a real one and is stated on the record rather than rounded
    # away. Seven mandals of Khammam district -- Burgampahad, Chintur,
    # Kukunoor, Kunavaram, Vararamachandrapuram, Velairpadu and part of
    # Bhadrachalam -- were moved to Andhra Pradesh by the Andhra Pradesh
    # Reorganisation (Amendment) Ordinance of 29 May 2014, four days before
    # Telangana came into being, to put the Polavaram project on one side of
    # the border. They are inside the ten districts and outside the present-day
    # state, which is why the Registrar General's figure for present-day
    # Telangana is 35,003,674 and the ten districts hold 190,304 more. Those
    # six whole mandals hold 208,421 people between them in the official C-01
    # sub-district table, so the transferred part is most but not all of them
    # -- which is precisely why this is not subtracted here: whole-mandal
    # arithmetic would give 34,985,557, a number no one published and 18,117
    # people away from the one they did.
    "Telangana": StateSplit(
        parent="Andhra Pradesh", state_code="28", year=2014,
        districts=("Adilabad", "Nizamabad", "Karimnagar", "Medak", "Hyderabad",
                   "Rangareddy", "Mahbubnagar", "Nalgonda", "Warangal", "Khammam"),
        codes=tuple(range(532, 542)),
        population=35_193_978, residual=49_386_799,
        caveat=("The seven mandals of Khammam district that were moved to "
                "Andhra Pradesh in 2014 for the Polavaram project are inside "
                "these ten districts and outside the present-day state, so "
                "this figure is 190,304 people -- 0.5% -- above the "
                "35,003,674 the Registrar General gives for Telangana as it "
                "now stands. The census published no sub-district religion "
                "figure for the part of Bhadrachalam that stayed, so "
                "subtracting the mandals whole would trade a stated 0.5% for "
                "an unstated one."),
        residual_caveat=(
            "The seven mandals of Khammam district that came here from "
            "Telangana in 2014 for the Polavaram project are outside these "
            "thirteen districts and inside the present-day state, so this "
            "figure is 190,304 people -- 0.4% -- below the 49,577,103 the "
            "Registrar General gives for Andhra Pradesh as it now stands."),
    ),
    # Ladakh's two districts. The union territory was carved out of Jammu and
    # Kashmir in 2019 along the boundary of Leh and Kargil, which the census
    # enumerated separately, so the same arithmetic applies.
    "Ladakh": StateSplit(
        parent="Jammu and Kashmir", state_code="01", year=2019,
        districts=("Leh(Ladakh)", "Kargil"), codes=(3, 4),
        population=274_289, residual=12_267_013,
        caveat="", residual_caveat="",
    ),
}

# 2011 districts that have since been subdivided, so one census row covers
# several present-day boundary units. Their figures are deliberately NOT
# spread across the successors: the census never measured those areas
# separately, and inventing a split would be fabrication. The successors keep
# an explicit gap carrying this explanation.
#
# These are the three where the 2011 name survives on no present-day shape at
# all, so the census row has nowhere to go. A district that merely *lost*
# territory to a new one keeps its name and keeps its shape -- and used to keep
# its 2011 row as well, which was the same error in a quieter form and is now
# ``LOST_TERRITORY_SINCE_2011`` below.
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

# The other half of the 2016-and-friends reorganisations, and the half this
# file used to get wrong.
#
# When a new district is carved out, the district that keeps the name keeps its
# shape too -- a smaller one. Its 2011 census row did not shrink with it. So
# modern Karimnagar, 2,132 km2 of the 9,103 km2 the census measured under that
# name, was wearing all 3,776,269 of the undivided district's people, three
# quarters of whom now live in Jagtial, Peddapalli and Rajanna Sircilla. That
# is the mis-match this project exists to prevent, and it is worse than the
# blank beside it: Jagtial's panel said plainly that no figure exists for it,
# while Karimnagar's showed a number with a source and a year that was not
# about the shape it sat on.
#
# The rule is now symmetric with SUBDIVIDED_SINCE_2011, as it should always
# have been. The census measured *undivided* Karimnagar. Modern Karimnagar and
# Jagtial are both fragments of that measurement, and the only difference
# between them is which fragment kept the name. Neither carries the figure; the
# state total does, and the note says so.
#
# **Why not keep the ones that barely changed?** Because the measurement here
# is of territory and the error is in people, and the two do not track each
# other. Rangareddy kept 52% of its ground and lost Medchal-Malkajgiri, a small
# dense suburb of Hyderabad holding nearly half its people; Upper Subansiri
# kept 90% of its ground and the part it lost is high Himalaya with almost
# nobody in it. An area threshold set anywhere between them would be a guess
# dressed as a tolerance. What area *can* answer is the binary question -- did
# this district lose territory or not -- and the measurement is unambiguous
# about that: every district here retained between 18% and 90% of its 2011
# extent, and every other Indian district retained all of it. There is nothing
# in between to draw a line through.
#
# Each entry is (district as the 2011 census spells it, percentage of its 2011
# extent the present-day shape still covers), grouped by present-day state, and
# the comment gives the 2011 population, the two areas and the districts that
# took the difference. The shares are measured from the CGAZ boundary files
# this map draws with -- shape area against the area of that shape plus every
# shape CREATED_AFTER_2011 declares was carved out of it -- so they carry
# CGAZ's simplification with them and are quoted to the percent, not finer.
# Which districts appear here is NOT a judgement: it is derived from
# CREATED_AFTER_2011 and checked against it on every run
# (:func:`check_lost_territory`), so a predecessor added there without a
# measurement here, or measured here without being declared there, stops the
# run.
LOST_TERRITORY_SINCE_2011: dict[str, tuple[tuple[str, int], ...]] = {
    "Arunachal Pradesh": (
        ("East Kameng", 68),  #     78,690 in 6,582 km2 -> now 4,457 km2; lost to Pakke Kessang
        ("East Siang", 63),  #     99,214 in 3,763 km2 -> now 2,389 km2; lost to Lower Siang, Siang
        ("Kurung Kumey", 70),  #     92,076 in 6,587 km2 -> now 4,589 km2; lost to Kra Daadi
        ("Lohit", 69),  #    145,726 in 4,087 km2 -> now 2,806 km2; lost to Namsai
        ("Lower Subansiri", 65),  #     83,030 in 2,077 km2 -> now 1,358 km2; lost to Kamle
        ("Tirap", 59),  #    111,975 in 2,052 km2 -> now 1,203 km2; lost to Longding
        ("Upper Subansiri", 90),  #     83,448 in 6,945 km2 -> now 6,226 km2; lost to Kamle
        ("West Siang", 29),  #    112,274 in 7,834 km2 -> now 2,255 km2; lost to Leparada, Lower Siang, Shi Yomi, Siang
    ),
    "Assam": (
        ("Dhubri", 71),  #  1,949,258 in 2,498 km2 -> now 1,779 km2; lost to South Salmara-Mankachar
        ("Jorhat", 60),  #  1,092,256 in 3,150 km2 -> now 1,899 km2; lost to Majuli
        ("Nagaon", 63),  #  2,823,768 in 3,967 km2 -> now 2,510 km2; lost to Hojai
        ("Sivasagar", 59),  #  1,151,050 in 2,578 km2 -> now 1,527 km2; lost to Charaideo
        ("Sonitpur", 66),  #  1,924,110 in 5,278 km2 -> now 3,483 km2; lost to Biswanath
    ),
    "Chhattisgarh": (
        ("Bastar", 50),  #  1,413,199 in 10,408 km2 -> now 5,218 km2; lost to Kondagaon
        ("Bilaspur", 48),  #  2,663,629 in 8,803 km2 -> now 4,259 km2; lost to Gaurella Pendra Marwahi, Mungeli
        ("Dakshin Bastar Dantewada", 34),  #    533,638 in 8,545 km2 -> now 2,873 km2; lost to Sukma
        ("Durg", 27),  #  3,343,872 in 8,331 km2 -> now 2,281 km2; lost to Balod, Bemetra
        ("Raipur", 25),  #  4,063,872 in 11,746 km2 -> now 2,883 km2; lost to Baloda Bazar, Gariaband
        ("Surguja", 31),  #  2,359,886 in 15,755 km2 -> now 4,897 km2; lost to Balrampur, Surajpur
    ),
    "Delhi": (
        ("East", 84),  #  1,709,346 in 80 km2 -> now 67 km2; lost to Shahdara
        ("North East", 75),  #  2,241,624 in 52 km2 -> now 39 km2; lost to Shahdara
        ("South", 59),  #  2,731,929 in 257 km2 -> now 151 km2; lost to South East
    ),
    "Gujarat": (
        ("Ahmadabad", 84),  #  7,214,225 in 8,345 km2 -> now 7,028 km2; lost to Batod
        ("Bhavnagar", 83),  #  2,880,365 in 7,964 km2 -> now 6,648 km2; lost to Batod
        ("Jamnagar", 52),  #  2,160,119 in 12,097 km2 -> now 6,275 km2; lost to Devbhumi Dwarka, Morbi
        ("Junagadh", 57),  #  2,743,082 in 8,843 km2 -> now 5,071 km2; lost to Gir Somnath
        ("Kheda", 73),  #  2,299,885 in 4,657 km2 -> now 3,404 km2; lost to Mahisagar
        ("Panch Mahals", 73),  #  2,390,776 in 4,584 km2 -> now 3,331 km2; lost to Mahisagar
        ("Rajkot", 83),  #  3,804,558 in 9,272 km2 -> now 7,657 km2; lost to Morbi
        ("Sabar Kantha", 56),  #  2,428,589 in 7,441 km2 -> now 4,170 km2; lost to Aravali
        ("Surendranagar", 85),  #  1,756,268 in 10,840 km2 -> now 9,224 km2; lost to Morbi
        ("Vadodara", 54),  #  4,165,626 in 7,618 km2 -> now 4,142 km2; lost to Chhota Udaipur
    ),
    "Madhya Pradesh": (
        ("Shajapur", 56),  #  1,512,681 in 6,221 km2 -> now 3,459 km2; lost to Agar
        ("Tikamgarh", 74),  #  1,445,166 in 5,008 km2 -> now 3,711 km2; lost to Niwari
    ),
    "Maharashtra": (
        ("Thane", 44),  # 11,060,148 in 9,416 km2 -> now 4,146 km2; lost to Palghar
    ),
    "Manipur": (
        ("Chandel", 65),  #    144,182 in 3,276 km2 -> now 2,125 km2; lost to Tengnoupal
        ("Churachandpur", 52),  #    274,143 in 4,851 km2 -> now 2,517 km2; lost to Pherzawl
        ("Imphal East", 71),  #    456,113 in 504 km2 -> now 358 km2; lost to Jiribam
        ("Senapati", 49),  #    479,148 in 3,589 km2 -> now 1,746 km2; lost to Kangpokpi
        ("Tamenglong", 73),  #    140,651 in 4,044 km2 -> now 2,944 km2; lost to Noney
        ("Thoubal", 58),  #    422,168 in 644 km2 -> now 370 km2; lost to Kakching
        ("Ukhrul", 49),  #    183,998 in 4,532 km2 -> now 2,220 km2; lost to Kamjong
    ),
    "Meghalaya": (
        ("East Garo Hills", 63),  #    317,917 in 2,813 km2 -> now 1,764 km2; lost to North Garo Hills
        ("West Garo Hills", 83),  #    643,291 in 3,474 km2 -> now 2,883 km2; lost to South West Garo Hills
        ("West Khasi Hills", 74),  #    383,461 in 5,183 km2 -> now 3,837 km2; lost to South West Khasi Hills
    ),
    "Mizoram": (
        ("Aizawl", 66),  #    400,309 in 3,984 km2 -> now 2,621 km2; lost to Saitual
        ("Champhai", 58),  #    125,745 in 2,611 km2 -> now 1,519 km2; lost to Khawzawl
        ("Lunglei", 81),  #    161,428 in 4,412 km2 -> now 3,565 km2; lost to Hnahthial
    ),
    "Punjab": (
        ("Firozpur", 40),  #  2,029,074 in 5,411 km2 -> now 2,148 km2; lost to Fazilka
        ("Gurdaspur", 72),  #  2,298,323 in 3,636 km2 -> now 2,628 km2; lost to Pathankot
    ),
    "Tamil Nadu": (
        ("Kancheepuram", 61),  #  3,998,252 in 4,474 km2 -> now 2,725 km2; lost to Chengalputtu
        ("Nagapattinam", 53),  #  1,616,450 in 2,509 km2 -> now 1,341 km2; lost to Mayiladuthurai
        ("Tirunelveli", 57),  #  3,077,233 in 6,674 km2 -> now 3,793 km2; lost to Tenkasi
        ("Vellore", 35),  #  3,936,331 in 6,088 km2 -> now 2,156 km2; lost to Ranipet, Tirupathur
        ("Viluppuram", 55),  #  3,458,873 in 7,236 km2 -> now 3,991 km2; lost to Kallakurichi
    ),
    "Telangana": (
        ("Adilabad", 25),  #  2,741,239 in 16,087 km2 -> now 4,083 km2; lost to Komaram Bheem, Mancherial, Nirmal
        ("Karimnagar", 23),  #  3,776,269 in 9,103 km2 -> now 2,132 km2; lost to Jagtial, Peddapalli, Rajanna Sircilla
        ("Khammam", 30),  #  2,797,370 in 15,667 km2 -> now 4,681 km2; lost to Bhadradri
        ("Mahbubnagar", 18),  #  4,053,028 in 16,144 km2 -> now 2,850 km2; lost to Jogulamba, Nagarkurnool, Narayanpet, Wanaparthy
        ("Medak", 26),  #  3,033,288 in 10,954 km2 -> now 2,817 km2; lost to Sangareddy, Siddipet
        ("Nalgonda", 51),  #  3,488,809 in 14,128 km2 -> now 7,203 km2; lost to Suryapet, Yadadri Bhongiri
        ("Nizamabad", 55),  #  2,551,335 in 7,926 km2 -> now 4,324 km2; lost to Kamareddy
        ("Rangareddy", 52),  #  5,296,741 in 9,779 km2 -> now 5,092 km2; lost to Medchal, Vikarabad
    ),
    "Tripura": (
        ("North Tripura", 67),  #    693,947 in 2,006 km2 -> now 1,353 km2; lost to Unokoti
        ("South Tripura", 48),  #    876,001 in 3,095 km2 -> now 1,478 km2; lost to Gomati
        ("West Tripura", 31),  #  1,725,739 in 3,068 km2 -> now 946 km2; lost to Khowai, Sipahijula
    ),
    "Uttar Pradesh": (
        ("Ghaziabad", 47),  #  4,681,645 in 2,028 km2 -> now 961 km2; lost to Hapur
        ("Moradabad", 49),  #  4,772,006 in 4,796 km2 -> now 2,331 km2; lost to Sambhal
        ("Muzaffarnagar", 67),  #  4,143,512 in 4,080 km2 -> now 2,742 km2; lost to Samli
        ("Rae Bareli", 75),  #  3,405,559 in 5,271 km2 -> now 3,959 km2; lost to Amethi
        ("Sultanpur", 65),  #  3,797,117 in 3,778 km2 -> now 2,466 km2; lost to Amethi
    ),
    "West Bengal": (
        ("Barddhaman", 77),  #  7,717,563 in 7,034 km2 -> now 5,396 km2; lost to Paschim Barddhaman
        ("Darjiling", 68),  #  1,846,823 in 3,475 km2 -> now 2,373 km2; lost to Kalimpong
        ("Jalpaiguri", 55),  #  3,872,846 in 6,191 km2 -> now 3,398 km2; lost to Alipurduar
        ("Paschim Medinipur", 67),  #  5,913,457 in 9,380 km2 -> now 6,285 km2; lost to Jhargram
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

    The last sentence used to send the reader to the predecessor: "the 2011
    figures for Karimnagar are on this map under that name and cover this
    ground too". They were, and it was the bug -- the shape called Karimnagar
    is a quarter of the district the census measured, and pointing at it as
    though it were the whole was how the mis-match got its confident tone.
    Neither fragment carries the figure now, so the sentence names where it
    actually is: the state.
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
        many = len(predecessors) > 1
        note += (f"The 2011 row that counted these people covers the undivided "
                 f"{listed}, and no district on this map carries it: the shape "
                 f"that still bears {'those names is' if many else 'that name is'} "
                 f"only the part left after this district was carved out, and "
                 f"giving a fragment the whole district's figure is the error "
                 f"this gap exists to avoid. The state total carries it.")
    return note


def lost_territory_reason(name: str, share: int,
                          successors: tuple[tuple[str, int], ...]) -> str:
    """What a district the census enumerated before its split is a figure for.

    The figure exists, is official, and has this district's name on it. What it
    does not have is this district's *shape*: the census measured the ground
    before the split and the boundary file draws it after, so the row counts
    people who now live in the districts named here too.

    This file blanked these for one revision, treating the shape as a fragment
    like its siblings. The owner asked for the figures back, and on reflection
    that is the better answer: the danger was never that the number is wrong
    but that it is silently about somewhere else, and the cure for silent is a
    sentence, not a deletion. It is the trade this project makes everywhere --
    a partial country roll-up naming what it leaves out, a summed parent naming
    the figure it displaced -- and it is a better one here too, because the
    *shares* survive the boundary change far better than the counts do.
    Religion does not reorganise itself along a new district line, so the
    choropleth, which shades by share, is close to right; it is the head count
    in the panel that is for more ground than the shape covers.

    So the note says which districts were carved out and when, what fraction of
    the census's ground is left, and, where most of the people have gone, that
    the count is mostly of somewhere else.
    """
    names = [child for child, _ in successors]
    years = sorted({year for _, year in successors})
    listed = (", ".join(names[:-1]) + " and " + names[-1]
              if len(names) > 1 else names[0])
    when = (f" ({years[0]})" if len(years) == 1
            else " (" + " and ".join(str(y) for y in years) + ")")
    many = len(names) > 1
    note = (f"This figure is for {name} as the 2011 census measured it, before "
            f"{listed}{when} {'were' if many else 'was'} carved out of it. The "
            f"shape drawn here keeps about {share}% of the ground that row "
            f"counted")
    note += (", so most of the people in it now live outside this boundary. "
             if share < 50 else ", and the rest is now in those districts. ")
    note += ("The census never measured the parts separately, so the shares "
             "are the undivided district's and the counts are its whole "
             "population -- read the percentages as describing this area and "
             "the head counts as covering more of it than the map shows.")
    return note


def lost_territory() -> dict[tuple[str, str], tuple[int, tuple[tuple[str, int], ...]]]:
    """(2011 state, 2011 district) -> (retained share, successors with years).

    Keyed by the state the *census* named, because that is the only thing a
    district row carries: Adilabad's row says Andhra Pradesh, and the table
    above is written under Telangana because that is where the shape is now.
    """
    out: dict[tuple[str, str], tuple[int, tuple[tuple[str, int], ...]]] = {}
    for state, entries in LOST_TERRITORY_SINCE_2011.items():
        state_2011 = STATE_IN_2011.get(state, state)
        for name, share in entries:
            successors = tuple(
                (child, year)
                for child, year, predecessors in CREATED_AFTER_2011.get(state, ())
                if any(p.casefold() == name.casefold() for p in predecessors))
            out[(state_2011.casefold(), name.casefold())] = (share, successors)
    return out


def check_lost_territory(rows: list[dict[str, str]]) -> None:
    """The shrunken-district table must be CREATED_AFTER_2011 read backwards.

    Three ways it could be wrong. A district listed here that lost nothing
    would put a caveat on a sound figure, telling a reader to discount
    something they need not. A district that *did* lose territory and is
    missing from here shows a figure for people who no longer live in it and
    says nothing about that, which is the bug this table exists to fix and the
    one that cannot be seen on the map. And a name the census never enumerated
    is a claim about a place that is not checked anywhere else.

    So the set of districts here is required to be exactly the set of
    predecessors CREATED_AFTER_2011 names, less the three whose name survives
    on no shape at all (those are SUBDIVIDED_SINCE_2011's job), and every one
    of them is required to be a real 2011 district of the state the table files
    it under. Derived and declared have to agree or nothing is emitted.
    """
    census = enumerated(rows)
    problems: list[str] = []

    declared: set[tuple[str, str]] = set()
    for state, entries in LOST_TERRITORY_SINCE_2011.items():
        state_2011 = STATE_IN_2011.get(state, state)
        for name, share in entries:
            key = (state, name)
            if key in declared:
                problems.append(f"{state} / {name} is declared twice")
            declared.add(key)
            if (state_2011.casefold(), name.casefold()) not in census:
                problems.append(
                    f"{state} / {name} is declared to have lost territory, but "
                    f"the census enumerated no district of that name in "
                    f"{state_2011}")
            if not 0 < share < 100:
                problems.append(
                    f"{state} / {name}: a retained share of {share}% is not a "
                    f"share of a district that lost some of its ground")

    derived = {(state, predecessor)
               for state, entries in CREATED_AFTER_2011.items()
               for _, _, predecessors in entries
               for predecessor in predecessors
               if predecessor.casefold() not in SUBDIVIDED_SINCE_2011}
    for state, name in sorted(derived - declared):
        problems.append(
            f"{state} / {name} had a district carved out of it after 2011 but "
            f"is not in LOST_TERRITORY_SINCE_2011, so its shape would keep the "
            f"undivided district's figure")
    for state, name in sorted(declared - derived):
        problems.append(
            f"{state} / {name} is in LOST_TERRITORY_SINCE_2011 but no district "
            f"in CREATED_AFTER_2011 was carved out of it")

    if problems:
        raise SystemExit(
            "india_census: the shrunken-district table does not agree with the "
            "post-2011 district table, so nothing is being emitted:\n  - "
            + "\n  - ".join(problems))


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
    check_lost_territory(rows)
    shrunken = lost_territory()

    for row in rows:
        name = (row.get("District name") or "").strip()
        if not name:
            continue
        key = name.lower()
        counts = collections.Counter({col: cell(row, col) for col in numeric})
        code = (row.get("District code") or "").strip()
        state = (row.get("State name") or "").strip()
        parent_name = STATE_ALIASES.get(
            state.lower(), state.title().replace(" And ", " and ").replace(" Of ", " of "))

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

        record_ = build_record(
            DISTRICT_ALIASES.get(key, name), counts,
            level="admin2", parent="IND", entity_id=f"IND-D{code}",
            codes={"census2011_district": code, "state_name": state})
        # District names repeat across states; the state is what disambiguates.
        record_["parent_name"] = parent_name
        # A district that has since been carved up keeps its figure and says
        # so. The shape is a fragment of the ground this row measured, which
        # is a fact about the figure rather than a reason to withhold it: the
        # note goes on every field the row filled, because a reader looking at
        # the head count needs it as much as one looking at the shares -- more,
        # since the shares survive a boundary change and the counts do not.
        shrink = shrunken.get((state.casefold(), key))
        if shrink:
            caveat = lost_territory_reason(DISTRICT_ALIASES.get(key, name),
                                           *shrink)
            for field in ("population", "sex_ratio", "religion",
                          "scheduled_groups", "language"):
                note = record_.get(f"{field}_note")
                record_[f"{field}_note"] = f"{note} {caveat}" if note else caveat
            record_["lost_territory_pct"] = 100 - shrink[0]
        out.append(record_)

    # The shapes the census has no row for at all, each carrying why.
    check_new_districts(rows)
    out.extend(new_districts())
    return out


# ---------------------------------------------------------------------------
# C-01 Appendix: what is inside "Other religions and persuasions"
# ---------------------------------------------------------------------------
#
# C-01 stops at eight categories, one of which is a residual, and in four
# states that residual is the third or fourth largest answer there is --
# ahead of every religion except two or three of the six the form names.
# Summed from the extract this file already reads: Arunachal Pradesh 26.2%
# (362,553 of 1,383,727), Jharkhand 12.8% (4,235,786), Meghalaya 8.7%
# (258,271), Manipur 8.2% (233,767). Calling a quarter of a state "other
# religions" is not a description of it.
#
# The Appendix is the table that says what is in there: scores of named
# religions, almost all of them Adivasi, and no other census on earth names
# them. It is published for **India and the states and nothing finer** -- the
# sheet has a district column and it reads 000 on every row, which this reader
# checks rather than assumes -- so a district-level share for Donyi-Polo or
# Sarna does not exist anywhere, and the note on every record says so.

APPENDIX_FILE = "DDW00C-01 Appendix MDDS.xlsx"
# quote() rather than a literal %20: the file name has two spaces in it and the
# URL has to carry them encoded, which is not something to leave to whoever
# types the command next.
APPENDIX_URL = (f"{CATALOG}/11398/download/14511/"
                + urllib.parse.quote(APPENDIX_FILE))
APPENDIX_SOURCE = (
    "Census of India 2011, table C-01 Appendix, details of religious community "
    "shown under 'Other religions and persuasions' in main table C-01 "
    "(Registrar General & Census Commissioner)")

# The sheet's header, in the order it writes it. Compared with whitespace
# collapsed, because the first cell is written "Table  Name" with two spaces.
# A column that moved and was read anyway is the failure this project cannot
# see, so the header is checked before a single figure is taken.
APPENDIX_HEADER = ("Table Name", "State Code", "Distt. Code", "Area Name",
                   "Religion Code", "Religious Community",
                   "Total/ Rural/ Urban", "Persons", "Males", "Females")
(APX_TABLE, APX_STATE, APX_DISTRICT, APX_AREA, APX_CODE, APX_NAME,
 APX_SPLIT, APX_PERSONS, APX_MALES, APX_FEMALES) = range(len(APPENDIX_HEADER))

# The bucket's own row, repeated once inside every state block. It is the
# parent and not a member of itself, and it is recognised by this code rather
# than by its label: C-01 writes "Other religions and persuasions" and this
# table writes "Other Religions and Persuasions", so matching on the name
# quietly fails to recognise the parent and adds the whole bucket a second
# time as though it were one more religion.
APPENDIX_PARENT = "700000"

# Below this share of the state a named religion is folded into the remainder
# rather than listed. The same floor india_language.py uses, for the same
# reason: a state's tail of religions that round to 0.0% is payload rather than
# information. The tail is summed and shown, never dropped.
ORP_MIN_PCT = 0.1
ORP_MAX_GROUPS = 12

# What is left of the bucket once the named religions above the floor are
# taken out. It is two things at once and the label has to cover both: the
# small ones this reader folded, and the ones the Appendix itself does not
# name -- its rows do not account for the whole of the parent row above them,
# which is a property of the published table and not of this reader. Kept
# distinct from C-01's "Other religions", which is the whole bucket.
ORP_REMAINDER = "Other religions (not separately named)"


def _text(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split())


def _code(value: Any, width: int) -> str:
    """A code as text, zero-padded, whatever type the cell happens to hold.

    The same code is text in one census workbook and a number in another, so
    India's own row arrives as "00" from one file and "0" from the other. Read
    without normalising, it becomes a 36th state and every figure in the table
    is counted twice.
    """
    text = _text(value)
    return text.zfill(width) if text.isdigit() else text


def _count(value: Any, area: str, label: str, column: str) -> int:
    """A figure from a count column, or a refusal naming the cell.

    An office marks a suppressed or absent cell with a dash or an asterisk far
    more often than with a blank, and int("-") is an unhandled traceback that
    says nothing about which row it came from. This says which row.
    """
    if value is None or _text(value) == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        raise SystemExit(
            f"C-01 Appendix: {area} / {label} has {value!r} in the {column} "
            f"column, which is not a count. Nothing is being emitted.") from None


def read_appendix(blob: bytes) -> dict[str, dict[str, Any]]:
    """state code -> {name, bucket, counts}, from DDW00C-01 Appendix.

    ``bucket`` is the parent row -- the unit's whole "Other religions and
    persuasions" figure -- and ``counts`` the named religions inside it. Only
    the Total rows are read; Rural and Urban are the same people split, and
    that is checked rather than trusted.
    """
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - environment problem
        raise SystemExit("pip install openpyxl to read the C-01 Appendix") from exc

    sheet = openpyxl.load_workbook(io.BytesIO(blob), read_only=True,
                                   data_only=True).worksheets[0]
    rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    header = next((i for i, row in enumerate(rows)
                   if _text(row[APX_STATE] if len(row) > APX_STATE else None)
                   == "State Code"), None)
    if header is None:
        raise SystemExit(
            f"C-01 Appendix: no header row in {APPENDIX_FILE}; the first rows "
            f"are {[[_text(c) for c in r] for r in rows[:3]]}")
    got = tuple(_text(cell) for cell in rows[header][:len(APPENDIX_HEADER)])
    if got != APPENDIX_HEADER:
        raise SystemExit(
            "C-01 Appendix: the columns are not where this reader expects "
            f"them, so nothing is being read.\n  expected {APPENDIX_HEADER}\n"
            f"  got      {got}")

    units: dict[str, dict[str, Any]] = {}
    splits: dict[tuple[str, str], dict[str, int]] = collections.defaultdict(dict)
    problems: list[str] = []
    for row in rows[header + 1:]:
        code = _text(row[APX_CODE]) if len(row) >= len(APPENDIX_HEADER) else ""
        if len(code) != 6 or not code.isdigit():
            # Blank rows, and the row of column numbers the sheet puts under
            # the header: its religion-code cell holds "5", which is a digit
            # and is not a religion code. Six is the width the table uses.
            continue
        state = _code(row[APX_STATE], 2)
        district = _code(row[APX_DISTRICT], 3)
        if district != "000":
            # The one thing that would overturn "state level only". If it ever
            # happens this reader is wrong about the table, not merely
            # incomplete, so it stops instead of emitting a note that says no
            # district figure exists while the file in front of it has one.
            raise SystemExit(
                f"C-01 Appendix: {_text(row[APX_AREA])} carries district code "
                f"{district}, so this table is not state-level after all and "
                f"the reader and its note both need rewriting.")
        code = _text(row[APX_CODE])
        label = _text(row[APX_NAME])
        split = _text(row[APX_SPLIT])
        persons = _count(row[APX_PERSONS], _text(row[APX_AREA]), label, "Persons")
        males = _count(row[APX_MALES], _text(row[APX_AREA]), label, "Males")
        females = _count(row[APX_FEMALES], _text(row[APX_AREA]), label, "Females")
        if males + females != persons:
            problems.append(f"{_text(row[APX_AREA])} {label} {split}: "
                            f"{males:,} males + {females:,} females "
                            f"is not {persons:,} persons")
        splits[(state, code)][split] = persons
        if split != "Total":
            continue
        unit = units.setdefault(state, {"name": _text(row[APX_AREA]),
                                        "bucket": 0,
                                        "counts": collections.Counter()})
        if code == APPENDIX_PARENT:
            unit["bucket"] = persons
        else:
            unit["counts"][label] = persons

    for (state, code), parts in splits.items():
        total, rural, urban = (parts.get("Total"), parts.get("Rural"),
                               parts.get("Urban"))
        if total is None or rural is None or urban is None:
            problems.append(f"state {state} religion {code}: expected Total, "
                            f"Rural and Urban rows, got {sorted(parts)}")
        elif rural + urban != total:
            problems.append(f"state {state} religion {code}: rural {rural:,} + "
                            f"urban {urban:,} is not total {total:,}")
    if problems:
        raise SystemExit("C-01 Appendix: the sheet does not add up, so it is "
                         "not being used:\n  - " + "\n  - ".join(problems[:10]))
    return units


def check_appendix(units: dict[str, dict[str, Any]],
                   buckets: dict[str, int]) -> None:
    """The Appendix must fit inside the bucket C-01 already measured.

    Three separate arithmetic checks, none of which the Appendix can satisfy on
    its own -- which is the point. A table checked only against itself will
    pass while being read twice over.

    * every unit's named religions must sum to no *more* than its own parent
      row. Less is expected and is not an error: the Appendix names a religion
      only where it has a hundred adherents nationally, so a remainder is part
      of the table's design;
    * the India row must equal the 35 states summed, religion by religion.
      This is what catches India being read as a 36th state, which is exactly
      what happens when a code arrives as "0" instead of "00";
    * every state's parent row must equal the "Other religions and
      persuasions" column ``india_census`` already has from C-01 -- a figure
      this table did not produce, in a file it was not published in.
    """
    problems: list[str] = []
    india = units.get("00")
    if not india:
        raise SystemExit("C-01 Appendix: no India row (state code 00), so the "
                         "national totals cannot be checked.")

    summed: collections.Counter = collections.Counter()
    for state, unit in units.items():
        if state == "00":
            continue
        summed.update(unit["counts"])
        named = sum(unit["counts"].values())
        if named > unit["bucket"]:
            problems.append(
                f"{unit['name']}: named religions sum to {named:,}, more than "
                f"the {unit['bucket']:,} in its own 'Other religions and "
                f"persuasions' row")
        expected = buckets.get(state_key(unit["name"]))
        if expected is None:
            # The normalised key and the nearest C-01 keys, not just "no
            # match". The first version of this said only that the name was
            # not found, and the cause -- a "State - " level marker on every
            # row of the Appendix and on none of C-01's -- took a person
            # spotting the prefix by eye. Two keys side by side would have
            # said it: 'state jammu and kashmir' against 'jammu and kashmir'.
            key = state_key(unit["name"])
            near = difflib.get_close_matches(key, sorted(buckets), n=3, cutoff=0.0)
            problems.append(
                f"{unit['name']}: no state of that name in the C-01 extract, "
                f"so its bucket cannot be checked. It normalises to {key!r}; "
                f"the nearest of the {len(buckets)} C-01 keys are "
                + ", ".join(repr(n) for n in near))
        elif expected != unit["bucket"]:
            problems.append(
                f"{unit['name']}: 'Other religions and persuasions' is "
                f"{unit['bucket']:,} here and {expected:,} in C-01")

    for label, total in sorted(india["counts"].items()):
        if summed.get(label, 0) != total:
            problems.append(f"{label}: India row says {total:,}, the states sum "
                            f"to {summed.get(label, 0):,}")
    if problems:
        raise SystemExit("C-01 Appendix: it does not agree with C-01, so it is "
                         "not being used:\n  - " + "\n  - ".join(problems[:10]))
    log(f"  C-01 Appendix: {len(units) - 1} states, "
        f"{len(india['counts'])} named religions, "
        f"{sum(india['counts'].values()):,} of the {india['bucket']:,} people "
        f"in 'Other religions and persuasions'")


# The words a DDW table puts in front of an area name to say which level the
# row is at: "State - JAMMU & KASHMIR", "District - Garhwa". The India row
# carries no marker at all, which is why a sample of that row alone does not
# show the pattern.
#
# Matched against this list rather than by stripping whatever precedes the
# first " - ", because a dash with spaces around it also occurs *inside* real
# names -- "Janjgir - Champa" and "Baloda Bazar - Bhatapara" are districts --
# and a general strip would turn Janjgir-Champa into Champa. The level words
# are a closed set the census defines; the names are not.
LEVEL_MARKERS = ("country", "india", "state", "union territory", "ut",
                 "district", "distt", "sub-district", "sub district",
                 "subdistrict", "tehsil", "taluk", "town", "city")


def state_key(name: str) -> str:
    """A state name reduced to what the two census tables agree on.

    They do not agree on much. C-01's extract shouts "JAMMU AND KASHMIR" and
    the Appendix writes "State - JAMMU & KASHMIR": a level marker, an ampersand
    and a case difference between two tables of the same census. One of them
    still says Orissa. Every state has to match or :func:`check_appendix`
    refuses -- 35 of 35 is the test, so a normalisation that quietly fails on
    one state fails the run rather than dropping that state's detail.

    Matching on a code would be better than matching on a rendering, and it is
    not available: **the district extract this file reads carries no state
    code**. Its geography columns are "District code", "State name" and
    "District name", and the district code runs 1-640 across the country
    rather than being composed from a state code, so there is nothing to join
    on but the name. The Appendix does carry a two-digit state code; the 35
    official per-state C-01 workbooks would too, and reading those instead
    would retire this function.
    """
    text = _text(name).casefold().replace("&", "and")
    head, sep, tail = text.partition(" - ")
    if sep and head.strip() in LEVEL_MARKERS:
        text = tail
    text = "".join(c for c in text if c.isalnum() or c == " ")
    text = " ".join(text.split())
    return STATE_ALIASES.get(text, text).casefold()


def named_residual(counts: collections.Counter, bucket: int, population: int
                   ) -> dict[str, int]:
    """The Appendix's religions for one state, largest first, with a remainder.

    The remainder is what makes this safe to substitute for C-01's single
    "Other religions" row: named plus remainder is the bucket exactly, so the
    eight columns still partition the state and the shares still cover
    everyone enumerated.
    """
    kept: dict[str, int] = {}
    for label, value in sorted(counts.items(), key=lambda kv: -kv[1]):
        if len(kept) < ORP_MAX_GROUPS and 100.0 * value / population >= ORP_MIN_PCT:
            kept[label] = value
    remainder = bucket - sum(kept.values())
    if remainder > 0:
        kept[ORP_REMAINDER] = remainder
    return kept


def religion_with_detail(counts: collections.Counter, unit: dict[str, Any]
                         ) -> list[dict[str, Any]]:
    """C-01's eight columns, with its residual replaced by what is inside it.

    The substitution has one invariant and it is checked here rather than
    trusted: the groups must still sum to the population the state enumerated.
    Australia's religion figures were silently doubled by a table read at two
    levels at once and the shares still added to 100%, so adding to 100% is not
    the test -- adding to a total the religion table did not produce is.
    """
    population = counts["Population"]
    religion_counts = {label: counts[column]
                       for column, label in RELIGION_COLUMNS.items()
                       if counts[column] and column != "Others_Religions"}
    religion_counts.update(named_residual(unit["counts"], unit["bucket"], population))
    got = sum(religion_counts.values())
    if got != population:
        raise SystemExit(
            f"C-01 Appendix: substituting the break-up of 'Other religions and "
            f"persuasions' in {unit['name']} leaves {got:,} people against an "
            f"enumerated {population:,}. The Appendix's bucket is "
            f"{unit['bucket']:,} and C-01's is "
            f"{counts['Others_Religions']:,}; nothing is being emitted.")
    return shares(religion_counts, total=population)


def residual_note(kept: dict[str, int], counts: collections.Counter,
                  bucket: int, population: int) -> str:
    """What the reader needs to know about a share that came from the Appendix.

    It leads with the magnitude and not with the name. A group nobody has heard
    of, listed without a figure beside it, reads as something the map invented;
    the same group with "324,742 people, 23.5% of the state" beside it reads as
    a measurement, which is what it is.
    """
    named = [label for label in kept if label != ORP_REMAINDER]
    largest = max((kept[label] for label in named), default=0)
    leader = next((label for label in named if kept[label] == largest), "")
    note = (f"Census 2011 table C-01 reports {bucket:,} people here -- "
            f"{100.0 * bucket / population:.1f}% of the state -- as one "
            f"residual, 'Other religions and persuasions'. The religions "
            f"standing in its place come from table C-01 Appendix, which names "
            f"what is inside it. ")
    if leader:
        note += (f"The largest here is {leader}: {largest:,} people, "
                 f"{100.0 * largest / population:.1f}% of the state and "
                 f"{100.0 * largest / bucket:.0f}% of the residual. ")
    note += ("Named plus remainder is C-01's figure exactly, so nobody is "
             "counted twice and nobody is dropped. ")
    if len(counts) > len(named):
        note += (f"The Appendix names {len(counts)} religions in this state; "
                 f"the {len(counts) - len(named)} smallest are summed into "
                 f"'{ORP_REMAINDER}' rather than listed, along with the "
                 f"people the Appendix itself leaves unnamed: its rows do not "
                 f"account for the whole of the residual. ")
    note += ("The Registrar General publishes this Appendix for India and the "
             "states only; its district column reads zero on every row. So "
             "there is no district-level figure for any of these religions in "
             "any Indian census publication, and this state's districts show "
             "the undivided 'Other religions' instead.")
    return note


def load_appendix(url: str = APPENDIX_URL) -> bytes:
    """The Appendix workbook, over a connection that is fully verified.

    censusindia.gov.in serves its leaf certificate without the intermediate
    above it, which urllib reports as *unable to get local issuer certificate*.
    ``aia=True`` fetches that intermediate from the certificate's own Authority
    Information Access extension and verifies against it plus the public roots;
    nothing is skipped. See scripts/probe_tls.py.
    """
    blob = http_get(url, binary=True, timeout=300, aia=True)
    assert isinstance(blob, bytes)
    return blob


def states(rows: list[dict[str, str]],
           appendix: dict[str, dict[str, Any]] | None = None
           ) -> list[dict[str, Any]]:
    """State totals summed from the district rows.

    Plain arithmetic on official counts, not estimation: the sums reproduce the
    published state populations exactly.

    With ``appendix``, C-01's single "Other religions" row is replaced by the
    religions the Appendix names inside it plus a labelled remainder. That is a
    substitution and not an addition: the two together are the bucket exactly,
    so the composition still adds to the state's population.
    """
    numeric = list(RELIGION_COLUMNS) + list(SCHEDULED_COLUMNS) + ["Population", "Male", "Female"]
    agg: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for row in rows:
        state = (row.get("State name") or "").strip()
        if not state:
            continue
        for col in numeric:
            agg[state][col] += cell(row, col)

    # Before anything is split. The Appendix is published against the 2011
    # states, so its bucket has to be checked against the 2011 aggregates --
    # after the split there is no "Andhra Pradesh" for it to match.
    if appendix is not None:
        check_appendix(appendix, {state_key(state): counts["Others_Religions"]
                                  for state, counts in agg.items()})
    detail = {state_key(unit["name"]): unit
              for code, unit in (appendix or {}).items() if code != "00"}

    pieces = split_states(rows, agg, numeric)

    out = []
    for state, whole in sorted(agg.items()):
        # The extract shouts state names; the boundary files use title case.
        plain = state.title().replace(" And ", " and ").replace(" Of ", " of ")
        plain = STATE_ALIASES.get(state.lower(), plain)
        for name, counts, split_prose in pieces.get(state, [(plain, whole, "")]):
            record_ = build_record(
                name, counts, level="admin1", parent="IND",
                entity_id=f"IND-S-{name.replace(' ', '-')}",
                codes={"census2011_state_name": state})
            unit = detail.get(state_key(state)) if not split_prose else None
            if unit and unit["counts"] and isinstance(record_["religion"], list):
                record_["religion"] = religion_with_detail(counts, unit)
                record_["religion_note"] = (
                    record_["religion_note"] + " "
                    + residual_note(named_residual(unit["counts"], unit["bucket"],
                                                   counts["Population"]),
                                    unit["counts"], unit["bucket"],
                                    counts["Population"]))
                record_["sources"].append(
                    {"field": "religion", "name": APPENDIX_SOURCE,
                     "url": APPENDIX_URL, "year": 2011,
                     "license": "Government of India open data (GODL-India)",
                     "note": "Published for India and the states only; the table's "
                             "district column is zero on every row."})
            if split_prose:
                for field in ("population", "religion", "scheduled_groups",
                              "sex_ratio", "language"):
                    record_[f"{field}_note"] = (
                        (record_.get(f"{field}_note", "") + " " + split_prose).strip())
            out.append(record_)
    return out


def split_note(new_state: str, split: StateSplit, *, residual: bool,
               total: int, undivided: int, kept: int) -> str:
    """What a summed state has to say about itself on the record.

    The codebase's convention for a figure nobody published is a ``_note`` on
    the field saying where it came from -- ``roll_up_field`` writes one, and so
    does ``us_prri``'s ``aggregate_note``. This is the same promise: name the
    arithmetic, name what went into it, and give the reader the number to check
    it against.
    """
    members = (", ".join(split.districts[:-1]) + " and " + split.districts[-1]
               if len(split.districts) > 1 else split.districts[0])
    if residual:
        note = (f"Summed from the {kept} districts of {split.parent} that "
                f"stayed in it when {new_state} was separated in "
                f"{split.year}. The 2011 "
                f"census enumerated {split.parent} whole -- {undivided:,} "
                f"people -- and this record covers only what was left of it: "
                f"{total:,}. Nothing is apportioned. The split ran along "
                f"district boundaries the census had already measured on both "
                f"sides, so this is that census's own figures added up, not an "
                f"estimate of a share.")
    else:
        note = (f"Summed from the {len(split.districts)} districts of "
                f"{split.parent} that became {new_state}: {members}. The 2011 "
                f"census enumerated all {len(split.districts)} separately and "
                f"they exhaust the territory, so their total -- {total:,} "
                f"people -- is that census's figure for this state rather than "
                f"an estimate of one. The Registrar General published no row "
                f"under this name because the state did not exist when the "
                f"tables were drawn up.")
    caveat = split.residual_caveat if residual else split.caveat
    if caveat:
        note += " " + caveat
    note += (" Table C-01 Appendix, which names the religions inside 'Other "
             "religions and persuasions', is published against the states of "
             "2011 and has no row for this one, so the residual stays whole "
             "here where those states show its break-up.")
    return note


def split_states(rows: list[dict[str, str]],
                 agg: dict[str, collections.Counter],
                 numeric: list[str],
                 ) -> dict[str, list[tuple[str, collections.Counter, str]]]:
    """Turn each 2011 state that has since been divided into its present-day parts.

    Every check here is arithmetic against a figure this function did not
    produce, because a sum can only be checked by something outside it:

    * the districts named in the split must all be districts the census
      enumerated in the parent state, and their codes must be the codes the
      census gave them -- name and code are two independent handles on the same
      row and the C-01 extract and the C-16 workbooks key on different ones;
    * the two halves must add back to the parent's own enumerated total in
      every column, which catches a district counted twice or dropped;
    * each half's population must equal the published figure in the table
      above, to the person.

    Any of them failing stops the run. A state figure assembled out of
    districts is a claim nobody else has made in print, and the only thing that
    makes it safe is that it is checkable.
    """
    problems: list[str] = []
    out: dict[str, list[tuple[str, collections.Counter, str]]] = {}
    by_parent: dict[str, list[tuple[str, StateSplit]]] = collections.defaultdict(list)
    for new_state, split in SPLIT_STATES.items():
        by_parent[state_key(split.parent)].append((new_state, split))
        if STATE_IN_2011.get(new_state) != split.parent:
            problems.append(
                f"{new_state} is split from {split.parent} here and "
                f"{STATE_IN_2011.get(new_state)!r} in STATE_IN_2011")

    for parent_raw, counts in agg.items():
        splits = by_parent.get(state_key(parent_raw))
        if not splits:
            continue
        parent = parent_raw.title().replace(" And ", " and ").replace(" Of ", " of ")
        parent = STATE_ALIASES.get(parent_raw.lower(), parent)
        claimed: dict[str, str] = {}
        parts: list[tuple[str, collections.Counter, str]] = []
        for new_state, split in splits:
            for district in split.districts:
                if district.casefold() in claimed:
                    problems.append(f"{district} is claimed by both "
                                    f"{claimed[district.casefold()]} and {new_state}")
                claimed[district.casefold()] = new_state
        residual_counts: collections.Counter = collections.Counter()
        member_counts: dict[str, collections.Counter] = {
            new_state: collections.Counter() for new_state, _ in splits}
        seen: dict[str, str] = {}
        for row in rows:
            if (row.get("State name") or "").strip() != parent_raw:
                continue
            name = (row.get("District name") or "").strip()
            owner = claimed.get(name.casefold())
            seen[name.casefold()] = (row.get("District code") or "").strip()
            target = member_counts[owner] if owner else residual_counts
            for col in numeric:
                target[col] += cell(row, col)
        for new_state, split in splits:
            for district, code in zip(split.districts, split.codes):
                got = seen.get(district.casefold())
                if got is None:
                    problems.append(
                        f"{new_state}: the census enumerated no district called "
                        f"{district!r} in {parent}")
                elif got.lstrip("0") != str(code):
                    problems.append(
                        f"{new_state}: {district} is district {got} in the "
                        f"extract and {code} in SPLIT_STATES")
            got = member_counts[new_state]["Population"]
            if got != split.population:
                problems.append(
                    f"{new_state}: its {len(split.districts)} districts sum to "
                    f"{got:,} people against a published {split.population:,}")
            parts.append((new_state, member_counts[new_state],
                          split_note(new_state, split, residual=False,
                                     total=member_counts[new_state]["Population"],
                                     undivided=counts["Population"],
                                     kept=0)))
        for col in numeric:
            total = residual_counts[col] + sum(c[col] for c in member_counts.values())
            if total != counts[col]:
                problems.append(
                    f"{parent}: the parts sum to {total:,} in column {col} "
                    f"against {counts[col]:,} for the undivided state")
        only = splits[0][1]
        if len(splits) > 1:
            # ``residual`` is one number and means "what is left after this
            # split", so two splits of one state make it ambiguous. Refusing is
            # the honest response; quietly skipping the check would leave the
            # residual as the only figure here nothing is measured against.
            problems.append(
                f"{parent} is split {len(splits)} ways ("
                + ", ".join(name for name, _ in splits)
                + "), and each split declares its own residual, so there is no "
                  "single published figure to check the remainder against")
        elif residual_counts["Population"] != only.residual:
            problems.append(
                f"{parent}: what is left after {splits[0][0]} is "
                f"{residual_counts['Population']:,} people against a published "
                f"{only.residual:,}")
        kept = len(seen) - sum(len(s.districts) for _, s in splits)
        parts.append((parent, residual_counts,
                      split_note(splits[0][0], only, residual=True,
                                 total=residual_counts["Population"],
                                 undivided=counts["Population"], kept=kept)))
        out[parent_raw] = parts

    if problems:
        raise SystemExit(
            "india_census: the state splits do not reproduce the census's own "
            "figures, so nothing is being emitted:\n  - "
            + "\n  - ".join(problems))
    for parent_raw, parts in out.items():
        log("  split " + parent_raw.title() + ": "
            + ", ".join(f"{name} {c['Population']:,}" for name, c, _ in parts))
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
    ap.add_argument("--appendix-url", default=APPENDIX_URL,
                    help="C-01 Appendix workbook, the break-up of 'Other "
                         "religions and persuasions'")
    ap.add_argument("--no-appendix", action="store_true",
                    help="skip the Appendix and leave C-01's residual whole")
    args = ap.parse_args()

    if args.list_sources:
        print(f"Census of India 2011 NADA catalogue: {CATALOG}")
        print("  C-01  Population by religious community")
        print("  C-01 Appendix  the religions inside 'Other religions and")
        print("                 persuasions', India and states only:")
        print(f"                 {APPENDIX_URL}")
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
        if args.level != "state":
            records = districts(rows)
        else:
            # Only at state level, because that is the only level the Appendix
            # is published at. Asking for it while building districts would
            # download a file with nothing in it for them.
            #
            # A source that cannot be reached and a source that does not add up
            # are different failures and get different answers. Unreachable is
            # a normal condition -- censusindia is slow and sometimes down --
            # and it costs the detail, not the state figures, so it is reported
            # and the run continues with C-01's residual whole. Anything the
            # reader or the checks refuse is not caught here: that is the file
            # disagreeing with the census, and nothing should be emitted.
            appendix = None
            if not args.no_appendix:
                log(f"  C-01 Appendix: {args.appendix_url}")
                try:
                    blob = load_appendix(args.appendix_url)
                except Exception as err:              # noqa: BLE001 - reported
                    log(f"  unreachable ({type(err).__name__}: {err}); the "
                        f"break-up of 'Other religions and persuasions' is not "
                        f"in this run and the residual stays whole")
                else:
                    appendix = read_appendix(blob)
            records = states(rows, appendix)

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
    # The labels the Appendix put on the map, printed because they are what
    # the group tree has to place: a religion surfaced here and left
    # unclassified is drawn in the reserved "not yet classified" colour, and
    # the only way to know which ones those are is to see the list.
    surfaced = sorted({row["group"] for r in records
                       if isinstance(r.get("religion"), list)
                       for row in r["religion"]}
                      - set(RELIGION_COLUMNS.values()))
    if surfaced:
        log(f"  groups beyond C-01's eight columns ({len(surfaced)}): "
            + ", ".join(surfaced))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
