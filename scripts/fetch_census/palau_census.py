#!/usr/bin/env python3
"""Palau, 2020 Census of Population and Housing: the sixteen states and Koror's hamlets.

The Office of Planning and Statistics published the census's tables in
*2020 Census of Population and Housing of the Republic of Palau, Volume I:
Basic Tables* (August 2022), on palaugov.pw and read here through the
Internet Archive's copy. Its table pages are scanned images with no text
layer -- a text reader finds nothing on them but the page number -- so the
six tables used were read from the rendered pages and are transcribed below,
as cfps_survey does for a table nothing can parse:

* Table 6 (p. 15): age by five-year group, the median, and women and men, by
  state of usual residence;
* Table 10 (p. 19): ethnicity and religion by state of usual residence;
* Table 16 (p. 25): whether each person speaks Palauan, by state;
* Tables 23, 27 and 33 (pp. 33, 37, 43): the same three for the twelve
  hamlets of Koror ("village residence in Koror") and its Rock Islands.

**Checks**, each refusing the run, so that a figure misread off a page cannot
pass: every transcribed row adds up across its columns to its printed total,
and every column down its rows to its printed population; each column's
women and men -- printed apart, men on the line the table labels "15 years
and over", which holds them all -- make its people; each printed median is
within a tenth of a year (the two roundings apart) of the median interpolated
from the transcribed five-year groups, for the places of 20 people or more;
Koror's hamlet tables add up, line by line, to Koror's column of the state
tables; and the states
agree with the one machine-readable copy of the count, the population series
of the Office's National Summary Data Page (an SDMX file on palaugov.pw):
every state the same, and its Koror, 11,400, Table 6's 11,199 usual residents
with the 173 people counted whose usual residence was outside Palau and the
28 whose residence was unknown.

**Language.** The census asked whether each person speaks Palauan. "Palauan"
here is everyone who does, alone or with another language; "Other languages"
everyone who speaks another language and not Palauan. Table 16's lines on
which other language is spoken add up to 12,399 -- the number who speak
Palauan -- so they do not describe the people who do not, and are not used.

**Medians.** Table 6's, which its own five-year groups reproduce. The
summary Table 1 prints lower ones (36.3 for the country against Table 6's
37.9) that Table 6's own age groups do not give.

**Hamlets outside Koror.** The census tabulates nothing below the state
except Koror's villages -- Volume I's list of tables and the summary tables
go no further, as in 2015 -- so the boundary file's other 64 hamlets carry
that reason, and their states' figures are on the states.

Usage:
    python -m scripts.fetch_census.palau_census
"""

from __future__ import annotations

import argparse
import gzip
import re
import xml.etree.ElementTree as ET
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, write_json
from .oceania_common import (
    bind_level, check, load_units, median_from_groups, population, sex_ratio, shares_of,
    summarise, unit_record,
)

OUT = "palau_census.json"
YEAR = 2020
OFFICE = "Republic of Palau, Office of Planning and Statistics"
VOLUME = (f"{OFFICE}, 2020 Census of Population and Housing, Volume I: Basic Tables "
          f"(August 2022)")
VOLUME_URL = ("http://web.archive.org/web/20230102070720/https://www.palaugov.pw/wp-content/"
              "uploads/2022/09/2020-Census-of-Population-and-Housing.pdf")
NSDP = f"{OFFICE}, National Summary Data Page: population (SDMX)"
NSDP_URLS = (
    "https://www.palaugov.pw/wp-content/uploads/Palau-Population.xml",
    "http://web.archive.org/web/20230325163450id_/"
    "https://www.palaugov.pw/wp-content/uploads/Palau-Population.xml",
)
LICENCE = "None stated -- Government of Palau publication, cited as such"

STATES = ("Kayangel", "Ngarchelong", "Ngaraard", "Ngiwal", "Melekeok", "Ngchesar", "Airai",
          "Aimeliik", "Ngatpang", "Ngardmau", "Ngeremlengui", "Angaur", "Peleliu", "Koror",
          "Sonsorol", "Hatohobei")
STATE_COLUMNS = ("Total", *STATES, "Outside of Palau", "Unknown")
HAMLETS = ("Dngeronger", "Idid", "Iyebukel", "Ikelau", "Madalaii", "Meketii", "Meyuns",
           "Ngerbeched", "Ngerchemai", "Ngerkebesang", "Ngerkesowaol", "Ngermid",
           "Rock Islands")
HAMLET_COLUMNS = ("Total", *HAMLETS)
# The census's spellings of three Koror hamlets, and the boundary file's.
ALIASES = {"Dngeronger": "Dngronger", "Idid": "Idid 03", "Madalaii": "Medalaii"}
# The Data Page's state codes (series PLW_LP_<code>_PE_NUM).
NSDP_CODES = {"KYGL": "Kayangel", "NGLNG": "Ngarchelong", "NGAD": "Ngaraard",
              "NGWL": "Ngiwal", "MLKK": "Melekeok", "NGSR": "Ngchesar", "ARI": "Airai",
              "AMK": "Aimeliik", "NGPG": "Ngatpang", "NGDAU": "Ngardmau",
              "NGLUI": "Ngeremlengui", "AGR": "Angaur", "PLLIU": "Peleliu", "KROR": "Koror",
              "SSORL": "Sonsorol", "HBI": "Hatohobei"}

AGE_GROUPS = (("Under 5 years", 0, 4), ("5 to 9 years", 5, 9), ("10 to 14 years", 10, 14),
              ("15 to 19 years", 15, 19), ("20 to 24 years", 20, 24),
              ("25 to 29 years", 25, 29), ("30 to 34 years", 30, 34),
              ("35 to 39 years", 35, 39), ("40 to 44 years", 40, 44),
              ("45 to 49 years", 45, 49), ("50 to 54 years", 50, 54),
              ("55 to 59 years", 55, 59), ("60 to 64 years", 60, 64),
              ("65 to 69 years", 65, 69), ("70 to 74 years", 70, 74),
              ("75 to 79 years", 75, 79), ("80 to 84 years", 80, 84),
              ("85 years and over", 85, None))
ETHNIC = {"Palauan": "Palauan", "Carolinian": "Carolinian", "Asian": "Asian",
          "Caucasian": "Caucasian", "Black": "Black", "Other": "Other ethnicity",
          "Not stated": "Not stated"}
RELIGION = {"Catholic": "Catholic", "Evangelical": "Evangelical",
            "Seven Day Adventist": "Seventh-day Adventist", "Assembly of God": "Assemblies of God",
            "Baptist": "Baptist", "Muslim": "Muslim",
            "Mormons": "Church of Jesus Christ of Latter-day Saints", "Modekngei": "Modekngei",
            "Other": "Other religion"}
SPEAKS = ("Yes, Palauan only", "Yes, Palauan and another language", "No, another language")
MEDIAN_SLACK = 0.15  # a tenth, and the two roundings to one decimal
MEDIAN_FLOOR = 20

# The tables as printed, one line each: the row's label, then its figures in
# the order of the columns ("-" is none). States: Total, the sixteen states
# north to south, Outside of Palau, Unknown. The labels are the tables' own but
# for women and men, called Female and Male here: Table 6 prints them as
# "Female" and "Male 15 years & over", Table 23 as "Females" and "Males 15
# years and over", and both men's lines hold every age (with the women they
# make each column's people).
TABLE_6 = """
All Persons | 17,614 41 384 396 312 318 319 2,529 363 289 238 349 114 470 11,199 53 39 173 28
Under 5 years | 1,013 4 19 21 21 15 18 136 24 16 21 26 7 27 638 6 6 3 5
5 to 9 years | 1,164 4 39 30 22 23 28 176 17 17 21 30 7 32 704 6 4 2 2
10 to 14 years | 1,202 2 29 37 28 19 27 180 31 17 18 27 10 36 722 12 6 - 1
15 to 19 years | 1,043 - 27 28 24 15 19 166 21 23 13 21 6 17 634 1 - 27 1
20 to 24 years | 897 2 19 21 12 12 20 111 21 14 13 18 4 15 587 4 2 22 -
25 to 29 years | 1,336 4 21 20 16 19 12 174 29 18 12 22 2 35 921 3 1 25 2
30 to 34 years | 1,360 1 25 11 12 23 14 197 21 20 15 18 2 25 941 3 2 28 2
35 to 39 years | 1,369 3 21 15 17 26 15 185 21 15 14 29 1 27 953 3 4 19 1
40 to 44 years | 1,432 - 12 18 18 28 17 204 20 20 10 26 10 38 997 - 2 10 2
45 to 49 years | 1,445 3 24 24 31 34 26 220 42 24 19 21 11 36 910 2 3 11 4
50 to 54 years | 1,377 4 22 36 25 26 34 203 31 25 16 16 15 40 867 7 3 6 1
55 to 59 years | 1,265 4 31 36 28 24 21 210 25 24 27 31 13 40 741 2 1 5 2
60 to 64 years | 1,040 - 25 38 22 23 19 142 20 24 15 31 13 36 620 2 1 6 3
65 to 69 years | 757 2 38 29 18 14 17 114 15 15 10 12 5 27 431 2 2 6 -
70 to 74 years | 438 4 16 16 10 7 14 53 13 5 5 10 5 15 262 - 1 1 1
75 to 79 years | 253 3 3 8 6 3 7 35 10 6 6 4 2 15 142 - 1 1 1
80 to 84 years | 126 1 7 6 1 3 6 11 1 6 2 3 - 5 74 - - - -
85 years and over | 97 - 6 2 1 4 5 12 1 - 1 4 1 4 55 - - 1 -
Median | 37.9 45.8 38.1 44.2 41.1 41.3 41.9 38.4 39.2 41.1 37.1 37.2 48.6 42.8 37.4 21.9 31.3 31.3 40.0
Female | 8,120 19 179 205 154 149 160 1,100 165 121 107 154 54 227 5,218 22 15 56 15
Male | 9,494 22 205 191 158 169 159 1,429 198 168 131 195 60 243 5,981 31 24 117 13
"""
TABLE_10_ETHNICITY = """
All Persons | 17,614 41 384 396 312 318 319 2,529 363 289 238 349 114 470 11,199 53 39 173 28
Palauan | 12,436 37 342 368 282 260 283 1,934 285 217 228 323 106 402 7,249 42 38 17 23
Carolinian | 220 - 6 5 1 - 3 12 6 - 1 5 - 1 141 9 - 30 -
Asian | 4,660 4 33 10 15 43 27 549 68 71 9 18 8 66 3,622 2 1 110 4
Caucasian | 150 - 2 10 4 1 3 26 3 1 - 1 - - 87 - - 12 -
Black | 20 - - 3 - - - 4 1 - - 1 - - 10 - - 1 -
Other | 123 - 1 - 10 14 3 4 - - - 1 - 1 85 - - 3 1
Not stated | 5 - - - - - - - - - - - - - 5 - - - -
"""
TABLE_10_RELIGION = """
All Persons | 17,614 41 384 396 312 318 319 2,529 363 289 238 349 114 470 11,199 53 39 173 28
Catholic | 8,173 12 35 166 116 147 61 1,084 121 64 53 77 73 135 5,861 51 37 69 11
Evangelical | 4,621 9 211 203 176 128 221 573 113 65 130 183 26 248 2,306 1 1 15 12
Seven Day Adventist | 936 - 2 3 3 7 19 309 55 27 - 23 1 18 464 - - 2 3
Assembly of God | 147 - 8 6 1 - 2 29 3 - 1 1 - - 93 - - 3 -
Baptist | 85 - 1 - - - 1 14 - - 1 - 1 - 63 - - 4 -
Muslim | 672 - 14 8 5 21 13 115 12 13 4 6 1 24 426 - - 10 -
Mormons | 186 - 3 1 - 5 - 23 - - - 2 - - 152 - - - -
Modekngei | 867 19 79 2 5 3 - 125 14 114 3 39 2 34 428 - - - -
Other | 1,927 1 31 7 6 7 2 257 45 6 46 18 10 11 1,406 1 1 70 2
"""
TABLE_16 = """
All Persons | 17,614 41 384 396 312 318 319 2,529 363 289 238 349 114 470 11,199 53 39 173 28
Yes, Palauan only | 7,205 13 143 170 159 171 185 1,073 151 182 173 125 61 220 4,320 13 23 12 11
Yes, Palauan and another language | 5,194 23 200 204 125 92 108 839 140 37 50 207 44 183 2,868 38 15 10 11
No, another language | 5,215 5 41 22 28 55 26 617 72 70 15 17 9 67 4,011 2 1 151 6
"""
# Koror's hamlets: Total, then the twelve villages and the Rock Islands.
TABLE_23 = """
All Persons | 11,199 491 537 640 511 2,284 637 938 1,404 1,376 693 639 1,045 4
Under 5 years | 638 33 30 29 27 96 28 49 101 80 63 51 51 -
5 to 9 years | 704 25 24 44 20 123 45 78 81 105 47 47 64 1
10 to 14 years | 722 26 40 46 16 106 33 61 103 111 67 48 64 1
15 to 19 years | 634 20 35 55 18 101 23 47 114 81 54 36 50 -
20 to 24 years | 587 25 32 26 28 113 35 47 82 68 45 28 58 -
25 to 29 years | 921 44 34 34 56 262 45 65 94 104 40 50 93 -
30 to 34 years | 941 56 46 36 42 250 65 70 96 72 54 48 106 -
35 to 39 years | 953 38 43 61 55 246 55 73 98 95 46 44 99 -
40 to 44 years | 997 36 48 48 58 223 61 79 105 122 57 59 101 -
45 to 49 years | 910 45 40 46 44 199 62 72 109 119 52 35 85 2
50 to 54 years | 867 38 37 61 46 170 43 70 121 109 34 54 84 -
55 to 59 years | 741 26 38 65 32 131 47 67 97 91 39 54 54 -
60 to 64 years | 620 26 42 32 31 101 41 69 68 82 40 34 54 -
65 to 69 years | 431 30 15 28 20 68 24 37 57 63 26 21 42 -
70 to 74 years | 262 11 16 12 9 48 11 34 31 28 18 14 30 -
75 to 79 years | 142 4 9 8 2 25 12 11 24 26 6 9 6 -
80 to 84 years | 74 1 2 4 3 17 5 7 11 16 3 3 2 -
85 years and over | 55 7 6 5 4 5 2 2 12 4 2 4 2 -
Median | 37.4 37.2 38.2 39.1 39.4 36.8 39.0 38.6 36.6 38.5 32.8 36.3 36.8 30.0
Female | 5,218 220 265 324 225 976 296 452 688 649 347 330 444 2
Male | 5,981 271 272 316 286 1,308 341 486 716 727 346 309 601 2
"""
TABLE_27_ETHNICITY = """
All Persons | 11,199 491 537 640 511 2,284 637 938 1,404 1,376 693 639 1,045 4
Palauan | 7,249 262 377 447 198 1,007 350 695 1,107 1,061 600 487 655 3
Carolinian | 141 6 11 10 1 20 6 3 31 29 17 1 6 -
Asian | 3,622 204 138 180 307 1,225 273 211 240 276 73 134 361 -
Caucasian | 87 2 4 1 4 19 6 8 13 6 2 10 12 -
Black | 10 - - - - 1 1 - 1 1 - 5 1 -
Other | 85 17 7 2 1 12 1 16 12 3 1 2 10 1
Not stated | 5 - - - - - - 5 - - - - - -
"""
TABLE_27_RELIGION = """
All Persons | 11,199 491 537 640 511 2,284 637 938 1,404 1,376 693 639 1,045 4
Catholic | 5,861 212 313 372 290 1,224 306 450 797 587 491 334 485 -
Evangelical | 2,306 101 134 152 99 329 140 189 319 462 64 146 171 -
Seven Day Adventist | 464 22 13 9 32 131 21 34 49 53 8 23 65 4
Assembly of God | 93 2 5 3 2 16 11 2 14 21 5 5 7 -
Baptist | 63 1 - 3 3 18 1 5 16 5 1 5 5 -
Muslim | 426 45 33 10 27 84 52 14 24 38 7 30 62 -
Mormons | 152 1 3 - 4 14 10 17 23 24 37 12 7 -
Modekngei | 428 21 11 20 1 62 18 136 47 44 20 23 25 -
Other | 1,406 86 25 71 53 406 78 91 115 142 60 61 218 -
"""
TABLE_33 = """
All Persons | 11,199 491 537 640 511 2,284 637 938 1,404 1,376 693 639 1,045 4
Yes, Palauan only | 4,320 164 191 251 143 467 182 481 799 600 316 278 448 -
Yes, Palauan and another language | 2,868 98 200 194 57 511 164 204 305 455 289 184 203 4
No, another language | 4,011 229 146 195 311 1,306 291 253 300 321 88 177 394 -
"""

FIGURE = re.compile(r"^(?:\d{1,3}(?:,\d{3})*(?:\.\d)?|-)$")


def parse(text: str, columns: tuple[str, ...], table: str) -> dict[str, dict[str, float]]:
    """{line label: {column: figure}} from a transcription, each line adding up."""
    rows: dict[str, dict[str, float]] = {}
    for line in text.strip().splitlines():
        label, _, figures = (part.strip() for part in line.partition("|"))
        cells = figures.split()
        check(len(cells) == len(columns) and all(FIGURE.match(c) for c in cells),
              f"palau_census: Table {table}'s {label!r} has {len(cells)} figures for "
              f"{len(columns)} columns")
        check(label not in rows, f"palau_census: Table {table} has two {label!r} lines")
        row = dict(zip(columns, (0.0 if c == "-" else float(c.replace(",", ""))
                                 for c in cells)))
        if label != "Median":
            parts = sum(v for k, v in row.items() if k != "Total")
            check(parts == row["Total"], f"palau_census: Table {table}'s {label!r} adds up "
                                         f"to {parts:,.0f} across, not {row['Total']:,.0f}")
        rows[label] = row
    return rows


def adds_down(rows: dict[str, dict[str, float]], labels: list[str], table: str) -> None:
    """Each column's lines make its printed population."""
    for column, people in rows["All Persons"].items():
        parts = sum(rows[label][column] for label in labels)
        check(parts == people, f"palau_census: Table {table}'s {column} adds up to "
                               f"{parts:,.0f}, not {people:,.0f}")


def read_ages(text: str, columns: tuple[str, ...], table: str) -> dict[str, dict[str, float]]:
    rows = parse(text, columns, table)
    adds_down(rows, [label for label, *_ in AGE_GROUPS], table)
    for column, people in rows["All Persons"].items():
        check(rows["Female"][column] + rows["Male"][column] == people,
              f"palau_census: Table {table}'s {column} has {rows['Female'][column]:,.0f} women "
              f"and {rows['Male'][column]:,.0f} men, not {people:,.0f} people")
        if people < MEDIAN_FLOOR:
            continue
        groups = [(low, high, rows[label][column]) for label, low, high in AGE_GROUPS]
        computed = median_from_groups(groups)
        printed = rows["Median"][column]
        check(computed is not None and abs(computed - printed) <= MEDIAN_SLACK,
              f"palau_census: Table {table} prints {column}'s median as {printed}, its "
              f"five-year groups give {computed}")
    return rows


def read_composition(text: str, columns: tuple[str, ...], labels: dict[str, str] | tuple,
                     table: str) -> dict[str, dict[str, float]]:
    rows = parse(text, columns, table)
    check(set(rows) - {"All Persons"} == set(labels),
          f"palau_census: Table {table}'s lines are {sorted(rows)}")
    adds_down(rows, list(labels), table)
    return rows


def read_tables() -> dict[str, dict[str, dict[str, float]]]:
    tables = {
        "6": read_ages(TABLE_6, STATE_COLUMNS, "6"),
        "10e": read_composition(TABLE_10_ETHNICITY, STATE_COLUMNS, ETHNIC, "10"),
        "10r": read_composition(TABLE_10_RELIGION, STATE_COLUMNS, RELIGION, "10"),
        "16": read_composition(TABLE_16, STATE_COLUMNS, SPEAKS, "16"),
        "23": read_ages(TABLE_23, HAMLET_COLUMNS, "23"),
        "27e": read_composition(TABLE_27_ETHNICITY, HAMLET_COLUMNS, ETHNIC, "27"),
        "27r": read_composition(TABLE_27_RELIGION, HAMLET_COLUMNS, RELIGION, "27"),
        "33": read_composition(TABLE_33, HAMLET_COLUMNS, SPEAKS, "33"),
    }
    for state, hamlet in (("6", "23"), ("10e", "27e"), ("10r", "27r"), ("16", "33")):
        for label, row in tables[hamlet].items():
            check(row["Total"] == tables[state][label]["Koror"],
                  f"palau_census: Koror's hamlets give {label!r} {row['Total']:,.0f}, the "
                  f"state table {tables[state][label]['Koror']:,.0f}")
    people = {s: tables["6"]["All Persons"][s] for s in STATES}
    for key in ("10e", "10r", "16"):
        check(all(tables[key]["All Persons"][s] == people[s] for s in STATES),
              "palau_census: the state tables count different people")
    log(f"  Volume I: Tables 6, 10, 16 for {len(STATES)} states and Tables 23, 27, 33 for "
        f"{len(HAMLETS)} places in Koror, each adding up")
    return tables


def read_nsdp(text: str) -> dict[str, int]:
    """{state or "Palau": 2020 population} from the Data Page's SDMX series."""
    root = ET.fromstring(text)
    out: dict[str, int] = {}
    for series in root.iter():
        if not series.tag.endswith("Series"):
            continue
        indicator = series.get("INDICATOR", "")
        match = re.fullmatch(r"PLW_LP_([A-Z]+)_PE_NUM", indicator)
        name = (NSDP_CODES.get(match.group(1)) if match
                else "Palau" if indicator == "LP_PE_NUM" else None)
        for obs in series:
            if name and obs.get("TIME_PERIOD") == str(YEAR):
                out[name] = int(float(obs.get("OBS_VALUE", "nan")))
    check(set(out) == {*STATES, "Palau"},
          f"palau_census: the Data Page's 2020 series cover {sorted(out)}")
    return out


def agrees_with_nsdp(nsdp: dict[str, int], tables: dict[str, Any]) -> None:
    ages = tables["6"]
    check(nsdp["Palau"] == ages["All Persons"]["Total"],
          f"palau_census: the Data Page counts {nsdp['Palau']:,}, Table 6 "
          f"{ages['All Persons']['Total']:,.0f}")
    for state in STATES:
        expected = ages["All Persons"][state]
        if state == "Koror":
            expected += ages["All Persons"]["Outside of Palau"] + ages["All Persons"]["Unknown"]
        check(nsdp[state] == expected, f"palau_census: the Data Page counts {state} at "
                                       f"{nsdp[state]:,}, Table 6 gives {expected:,.0f}")
    log(f"  Data Page: {nsdp['Palau']:,} people; every state as in Table 6, Koror with the "
        f"people from outside Palau or of unknown residence")


def nsdp_text() -> str:
    for url in NSDP_URLS:
        try:
            blob = http_get(url, binary=True, timeout=120, retries=2)
        except Exception as exc:  # noqa: BLE001 - the next copy is tried
            log(f"  {url}: {type(exc).__name__}")
            continue
        assert isinstance(blob, bytes)
        if blob[:2] == b"\x1f\x8b":
            blob = gzip.decompress(blob)
        text = blob.decode("utf-8", "replace")
        if "StructureSpecificData" in text[:2000]:
            log(f"  {url}: {len(blob):,} bytes")
            return text
        log(f"  {url}: not the data file ({text[:80]!r})")
    raise SystemExit("palau_census: no copy of the National Summary Data Page answered")


def fields_for(column: str, ages: dict[str, Any], ethnic: dict[str, Any],
               faith: dict[str, Any], speech: dict[str, Any], numbers: tuple[str, str, str],
               where: str) -> dict[str, Any]:
    """One place's fields from its column of the age, ethnicity/religion and language tables."""
    t_age, t_comp, t_lang = numbers
    total = ages["All Persons"][column]
    female = ages["Female"][column]
    only, both, other = (speech[label][column] for label in SPEAKS)
    out: dict[str, Any] = {
        "population": population(total, YEAR, f"{VOLUME} (Table {t_age})"),
        "sex_ratio": measure(sex_ratio(total - female, female), unit="males_per_100_females",
                             year=YEAR, source=f"{VOLUME} (Table {t_age})"),
        "sex_ratio_note": f"Males per 100 females among {where}'s usual residents, 2020 "
                          f"census (Table {t_age}).",
        "ethnicity": shares_of({ETHNIC[k]: ethnic[k][column] for k in ETHNIC}, total),
        "ethnicity_year": YEAR,
        "ethnicity_note": (f"Ethnicity of {where}'s usual residents, 2020 census (Table "
                           f"{t_comp}), in the census's own groups; it does not divide "
                           f"'Asian' further at this level."),
        "religion": shares_of({RELIGION[k]: faith[k][column] for k in RELIGION}, total),
        "religion_year": YEAR,
        "religion_note": (f"Religion of {where}'s usual residents, 2020 census (Table "
                          f"{t_comp}). 'Other religion' is the census's 'Other'; the table "
                          f"has no line for no religion."),
        "language": shares_of({"Palauan": only + both, "Other languages": other}, total),
        "language_year": YEAR,
        "language_note": (f"Whether each of {where}'s usual residents speaks Palauan, 2020 "
                          f"census (Table {t_lang}): 'Palauan' is the {only:,.0f} who speak "
                          f"Palauan only and the {both:,.0f} who speak it and another "
                          f"language; 'Other languages' the {other:,.0f} who speak another "
                          f"language and not Palauan. The table's lines on which other "
                          f"language is spoken add up to the number who speak Palauan, not "
                          f"to those who do not, so which languages the rest speak is not "
                          f"known here."),
    }
    out["median_age"] = measure(ages["Median"][column], unit="years", year=YEAR,
                                source=f"{VOLUME} (Table {t_age})")
    out["median_age_note"] = (
        f"Median age of {where}'s usual residents as Table {t_age} of the 2020 census prints "
        f"it" + ("." if total >= MEDIAN_FLOOR else
                 f", for {total:,.0f} people.") +
        " The volume's summary Table 1 prints lower medians (36.3 for the country, against "
        "Table 6's 37.9) that Table 6's age groups do not give.")
    return out


def koror_note(ages: dict[str, Any]) -> str:
    row = ages["All Persons"]
    away, unknown = row["Outside of Palau"], row["Unknown"]
    return (f"Usual residents of Koror, 2020 census (Table 6). The Office's National Summary "
            f"Data Page counts Koror at {row['Koror'] + away + unknown:,.0f}: it adds the "
            f"{away:,.0f} people counted whose usual residence was outside Palau and the "
            f"{unknown:,.0f} whose residence was unknown, whom Table 6 places in no state.")


HAMLET_GAP = ("The 2020 census tabulates nothing below the state except the villages of "
              "Koror: Volume I's tables by place are by state of usual residence, by state of "
              "legal residence and by village of residence in Koror (Tables 23-39), and the "
              "summary Tables 1-3 list 'Hamlets in Koror' only, as the 2015 census's did. "
              "{state}'s own figures are on the state.")

SOURCES = [
    {"field": "population/median_age/sex_ratio/ethnicity/religion/language", "name": VOLUME,
     "url": VOLUME_URL, "year": YEAR, "license": LICENCE},
    {"field": "population (check)", "name": NSDP, "url": NSDP_URLS[0], "year": YEAR,
     "license": LICENCE},
]


def build(tables: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    states = bind_level({s: (s, "") for s in STATES}, admin1, {})
    for state, unit in states.items():
        fields = fields_for(state, tables["6"], tables["10e"], tables["10r"], tables["16"],
                            ("6", "10", "16"), state)
        if state == "Koror":
            fields["population_note"] = koror_note(tables["6"])
        records.append(unit_record("PLW", state, unit["name"], unit, "admin1", None, SOURCES,
                                   **fields))
    parents = {u["id"]: u["name"] for u in admin1}
    in_koror = [u for u in admin2 if parents.get(u.get("parent")) == "Koror"]
    hamlets = bind_level({h: (h, "Koror") for h in HAMLETS}, in_koror, parents, ALIASES)
    for hamlet, unit in hamlets.items():
        fields = fields_for(hamlet, tables["23"], tables["27e"], tables["27r"], tables["33"],
                            ("23", "27", "33"), hamlet)
        records.append(unit_record("PLW", f"Koror-{hamlet}", unit["name"], unit, "admin2",
                                   "Koror", SOURCES, **fields))
    for unit in admin2:
        state = parents.get(unit.get("parent"))
        if unit in in_koror:
            continue
        check(state in STATES, f"palau_census: hamlet {unit['name']} lies in no state")
        reason = HAMLET_GAP.format(state=state)
        records.append(unit_record(
            "PLW", f"{state}-{unit['name']}-{unit['id'][-6:]}", unit["name"], unit, "admin2",
            state, SOURCES[:1],
            **{f: gap(NOT_AVAILABLE, reason) for f in ("population", "median_age", "sex_ratio",
                                                       "religion", "language", "ethnicity")}))
    return records


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("palau_census: 2020 census, Volume I (transcribed) and the National Summary Data Page")
    tables = read_tables()
    agrees_with_nsdp(read_nsdp(nsdp_text()), tables)
    records = build(tables, load_units("PLW", "admin1"), load_units("PLW", "admin2"))
    log("  " + summarise(records))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
