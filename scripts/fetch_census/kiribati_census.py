#!/usr/bin/env python3
"""Kiribati, 2020 census: every island's count, age, sex and ethnicity.

**The count** is the Kiribati National Statistics Office's own: its *Island
Profile* workbook for the 2020 Population and Housing Census
(``island-profile-table-final.xlsx``) gives each of the 24 inhabited islands a
sheet whose "Population (Census)" row holds the 2015 and 2020 counts, and a
summary sheet that lists the same 24 by broad age group. Both must agree, and
they must add up to the 119,438 the census counted. Betio is its own island
there, and South Tarawa is the Teinainano Urban Council without it -- which is
how the map draws them, as "Betio" and "Tarawa Teinainano".

**Sex and ethnicity by island** the Office publishes in its General Report,
whose tables are pictures with no text layer. Three are transcribed here from
the rendered pages: Table G-2 (p. 18), each island's people by sex; Table
A-10a (p. 40), each island's broad age groups and median age; Table A-3b
(p. 26), each island's ethnicity. Each must add up across its columns and down
to its divisions and the country, and give every island the count the Island
Profile gives it -- four readings of one number, two of them from different
pages.

**The median ages are not Table A-10a's.** That column contradicts the
census's own ages. It prints the country at 20.4, where the Office's Census
Atlas (2022, Table 2) prints 22.9 -- males 21.8, females 24.0 -- and it runs
below what the same census's five-year groups give on nearly every island, by
up to six years: Butaritari 16.8 against 21.7, with 41% of its people under
15. Banaba's 13.8 even sits on the wrong side of 15 for its own age groups.
So every island's and island group's median here comes from one source, the
Pacific Community's tabulation of the same census by island, five-year age
group and sex, which UNFPA and OCHA publish as the Common Operational Dataset
for Kiribati (``cod-ps-kir``, "Baseline used: Kiribati NSO"), interpolated
within the group that holds the middle person. The run refuses unless that
tabulation's country medians -- everyone, males, females -- are each within
0.3 years of the Atlas's. It counts 119,940 people, 0.4% more than the final
count, and each record says how many people its median describes. It folds
Betio into South Tarawa and tabulates Betio as the village "BetioEast", so
Betio's median is that village's and Teinainano's South Tarawa's without it.
Kanton, 41 people, is not in it, and Kanton and the Phoenix Islands say why
they have no median. The printed figure is quoted on every island's record.

**Religion by island is the 2015 census's.** The 2020 census publishes
religion for the country (General Report, Table G-3) and maps it by island in
its Census Atlas (Map 18) without printing a figure. The census before it
tabulated it by island: the 2015 *Volume 1: Management Report and Basic
Tables*, Table 6 (pp. 56-59), "Population by island, sex and religion", 14
columns from Roman Catholic to Other, with Betio apart from the rest of South
Tarawa -- the two polygons the map draws -- and Makin, Banaba and Kanton on
lines of their own. Its text layer reads, so it is parsed, not transcribed,
and refused unless every line's sexes make its total, every line's religions
make it too, the islands make each of the country's columns, the country is
the 110,136 the census counted, and each island's total is its 2015
population in the same volume's Table 1a (where South Tarawa still includes
Betio). Its "Te Ran" and "All Nation" columns -- 86 and 141 people in the
country -- name bodies whose tradition the volume does not state, so they are
counted with its "Other", and the note names them. The table has one column
for the Kiribati Protestant Church, "KPC"; the 2020 census lists the Kiribati
Uniting Church and the KPC apart, so the record says that too.

**Language** the records say why is empty: no census tabulates it -- the
2020 General Report and Atlas report only whether people can read and write,
as the 2015 volume (Table 15) and the 2010 tables (Table 16, literacy) do.

**What the map draws.** 23 islands at the second level (Makin, 1,914 people,
has no polygon) and three polygons at the first, labelled with the island
groups but not drawn as the census groups them: the one labelled the Phoenix
Islands also draws North and South Tarawa (Betio included) and Banaba, which
are Gilbert islands, and the one labelled the Gilbert Islands draws the rest
of that group (``DRAWN_GROUPS``). Each first-level record is the census
counts of the islands its polygon draws, named for them -- "Gilbert Islands
except Tarawa and Banaba", "Line Islands", "Tarawa, Banaba and the Phoenix
Islands" -- so a figure never stands for ground its polygon does not draw;
the run stops if the map's island parents ever disagree with that table.

Usage:
    python -m scripts.fetch_census.kiribati_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, write_json
from .oceania_common import (
    FIGURE, bind_level, check, load_units, median_from_groups, number, population, rows_of,
    sex_ratio, shares_of, summarise, transcription, unit_record, withhold_small, workbook,
)

OUT = "kiribati_census.json"
# The fill-only file SPC's medians used to go to; they are this file's now, and
# a run removes it so the build reads one source for Kiribati's ages.
OUT_AGES = "kiribati_codps_age.json"
YEAR = 2020
OFFICE = "Kiribati National Statistics Office"
PROFILE_URL = ("https://nso.gov.ki/download/146/2020-census/1931/"
               "island-profile-table-final.xlsx")
PROFILE = f"{OFFICE}, 2020 Population and Housing Census, Island Profile tables"
REPORT_URL = ("https://nso.gov.ki/download/146/2020-census/1965/"
              "population-and-housing-census-report-2020.pdf")
ATLAS_URL = "https://nso.gov.ki/download/117/other-reports/2022/kiribati-census-atlas-2022.pdf"
COD_PACKAGE = "https://data.humdata.org/api/3/action/package_show?id=cod-ps-kir"
COD_PAGE = "https://data.humdata.org/dataset/cod-ps-kir"
COD_FILE = "kir_admpop_2020.xlsx"
COD = ("Pacific Community (SPC) tabulation of the 2020 census by island, five-year age group "
       "and sex (UNFPA / OCHA COD-PS for Kiribati)")
LICENCE = "None stated -- Kiribati National Statistics Office publication, cited as such"
NATIONAL = 119_438
# The Office's own country medians for 2020: the Kiribati Census Atlas (2022),
# Table 2 "Key population statistics" and its key-indicators box. SPC's
# five-year groups must reproduce each within MEDIAN_SLACK years.
ATLAS = f"{OFFICE}, Kiribati Census Atlas 2022 (Table 2, Key population statistics)"
ATLAS_MEDIANS = {"everyone": 22.9, "males": 21.8, "females": 24.0}
MEDIAN_SLACK = 0.3
# Table A-10a's own figure for the country, quoted against the Atlas's.
A10A_NATIONAL = 20.4

# The 2015 census's religion by island (Volume 1, Table 6).
RELIGION_URL = ("https://nso.gov.ki/download/91/2015-census/1054/"
                "population-census-2015-report-volume-1-final.pdf")
RELIGION_REPORT = (f"{OFFICE}, 2015 Population and Housing Census, Volume 1: Management "
                   f"Report and Basic Tables (September 2016)")
RELIGION_YEAR = 2015
NATIONAL_2015 = 110_136
# The table's titles, and not the contents page's line for it, which runs on to
# its page number.
T6_TITLE = re.compile(r"^Table 6(?: cont)?: Population by island, sex and religion"
                      r"(?:: | - census )2015$")
T1A_TITLE = re.compile(r"^Table 1a: Population and No of Households by Island: 2010, 2015\s*$")
# Table 6's heading, every page of it, as its text layer reads it.
T6_HEADER = ("Total Total Roman Catholic KPC Seventh Day Adventist Church Of God Latter Day "
             "Saints Assembly of God Bahai Jehova's Witness (Te Koaua) Islam Four Square Te Ran "
             "All Nation No religion Other")
# Its columns after the Total, in order, and the name each is written under:
# the two bodies whose tradition the volume does not say go with its "Other".
T6_COLUMNS = (
    ("Roman Catholic", "Roman Catholic"),
    ("KPC", "Kiribati Protestant Church"),
    ("Seventh Day Adventist", "Seventh-day Adventist"),
    ("Church Of God", "Church of God"),
    ("Latter Day Saints", "Church of Jesus Christ of Latter-day Saints"),
    ("Assembly of God", "Assemblies of God"),
    ("Bahai", "Baha'i"),
    ("Jehova's Witness (Te Koaua)", "Jehovah's Witnesses"),
    ("Islam", "Islam"),
    ("Four Square", "Foursquare Church"),
    ("Te Ran", "Other religion"),
    ("All Nation", "Other religion"),
    ("No religion", "No religion"),
    ("Other", "Other religion"),
)
FOLDED = ("Te Ran", "All Nation")
# Table 6's island lines (Table 1a's too, but for Betio, which 1a counts in STarawa).
T6_ISLANDS = ("Banaba", "Makin", "Butaritari", "Marakei", "Abaiang", "NTarawa", "STarawa",
              "Betio", "Maiana", "Abemama", "Kuria", "Aranuka", "Nonouti", "NTabiteuea",
              "STabiteuea", "Beru", "Nikunau", "Onotoa", "Tamana", "Arorae", "Teeraina",
              "Tabuaeran", "Kiritimati", "Kanton")
SEXES = ("Total", "Male", "Female")

# The island as the map draws it -> its sheet in the profile workbook, and its
# row in SPC's island table ("" where SPC does not tabulate it as an island).
ISLANDS: dict[str, tuple[str, str]] = {
    "Banaba": ("Banaba", "Banaba"),
    "Butaritari": ("Butaritari", "Butaritari"),
    "Marakei": ("Marakei", "Marakei"),
    "Abaiang": ("Abaiang", "Abaiang"),
    "Tarawa Ieta": ("North Tarawa", "North Tarawa"),
    "Tarawa Teinainano": ("South Tarawa", ""),
    "Betio": ("Betio", ""),
    "Maiana": ("Maiana", "Maiana"),
    "Abemama": ("Abemama", "Abemama"),
    "Kuria": ("Kuria", "Kuria"),
    "Aranuka": ("Aranuka", "Aranuka"),
    "Nonouti": ("Nonouti", "Nonouti"),
    "Tabiteuea North": ("NTabiteuea", "North Tabiteuea"),
    "Tabiteuea South": ("STabiteuea", "South Tabiteuea"),
    "Beru": ("Beru", "Beru"),
    "Nikunau": ("Nikunau", "Nikunau"),
    "Onotoa": ("Onotoa", "Onotoa"),
    "Tamana": ("Tamana", "Tamana"),
    "Arorae": ("Arorae", "Arorae"),
    "Teraina": ("Teraina", "Teeraina"),
    "Tabuaeran": ("Tabuaeran", "Tabuaeran"),
    "Kiritimati": ("Kiritimati", "Kiritimati"),
    "Kanton": ("Kanton", ""),
}
UNDRAWN = {"Makin": ("Makin", "Makin")}
# The census's island groups.
GROUPS = {"Gilbert Islands": [k for k in ISLANDS if k not in ("Teraina", "Tabuaeran",
                                                              "Kiritimati", "Kanton")] + ["Makin"],
          "Line Islands": ["Teraina", "Tabuaeran", "Kiritimati"],
          "Phoenix Islands": ["Kanton"]}

# The island groups as the boundary file draws them, which is not as the census
# groups them. Its first-level polygon labelled "Phoenix Islands" is 22 parts:
# seven at Kanton, one at Banaba and fourteen at Tarawa (measured on
# geoBoundariesCGAZ_ADM1); Betio, Tarawa Teinainano, Tarawa Ieta and Banaba
# lie 92-99% inside it, and the polygon labelled "Gilbert Islands" draws the
# group's other islands. A figure goes on the ground its polygon draws, so each
# first-level record is the census counts of the islands drawn inside it,
# named for what that is: {boundary label: (name, islands, what it is)}. Makin
# (1,914 people) is drawn at neither level and is counted where its group's
# other northern islands are. ``drawn_groups`` checks this against the parents
# the map gives the island polygons and stops the run if they disagree.
DRAWN_GROUPS: dict[str, tuple[str, list[str], str]] = {
    "Gilbert Islands": (
        "Gilbert Islands except Tarawa and Banaba",
        [k for k in GROUPS["Gilbert Islands"]
         if k not in ("Tarawa Ieta", "Tarawa Teinainano", "Betio", "Banaba")],
        "The boundary file draws North and South Tarawa (Betio included) and Banaba inside the "
        "polygon it labels the Phoenix Islands, not in this one, so this is the Gilbert group "
        "without them: the census counts of the islands this polygon draws, added up, and of "
        "Makin, which no polygon draws."),
    "Line Islands": ("Line Islands", list(GROUPS["Line Islands"]), ""),
    "Phoenix Islands": (
        "Tarawa, Banaba and the Phoenix Islands",
        ["Tarawa Ieta", "Tarawa Teinainano", "Betio", "Banaba", "Kanton"],
        "The boundary file's polygon labelled the Phoenix Islands also draws North and South "
        "Tarawa (Betio included) and Banaba, which belong to the Gilbert group, so this is the "
        "census counts of every island it draws, added up: Kanton, the Phoenix group's one "
        "inhabited island, and those four."),
}
# The summary sheet's own spellings, for the cross-check.
SUMMARY_NAMES = {"North Tarawa": "NTarawa", "South Tarawa": "STarawa", "Teraina": "Teeraina"}

REPORT = f"{OFFICE}, 2020 Population and Housing Census General Report"
# The island as the map draws it (or, for Makin, names it) -> its line in the
# General Report's tables.
REPORT_ROWS = {**{i: i for i in ISLANDS}, "Makin": "Makin", "Tarawa Ieta": "North Tarawa",
               "Tarawa Teinainano": "South Tarawa", "Tabiteuea North": "North Tabiteuea",
               "Tabiteuea South": "South Tabiteuea", "Teraina": "Teeraina"}
# The island as the map draws it (or, for Makin, names it) -> its line in the
# 2015 volume's Table 6.
T6_ROWS = {**{i: i for i in ISLANDS}, "Makin": "Makin", "Tarawa Ieta": "NTarawa",
           "Tarawa Teinainano": "STarawa", "Tabiteuea North": "NTabiteuea",
           "Tabiteuea South": "STabiteuea", "Teraina": "Teeraina"}
DIVISIONS = {
    "South Tarawa Division": ["South Tarawa", "Betio"],
    "Northern Division": ["Makin", "Butaritari", "Marakei", "Abaiang", "North Tarawa"],
    "Central Division": ["Banaba", "Maiana", "Abemama", "Kuria", "Aranuka"],
    "Southern Division": ["Nonouti", "North Tabiteuea", "South Tabiteuea", "Beru", "Nikunau",
                          "Onotoa", "Tamana", "Arorae"],
    "Line Islands & Phoenix Division": ["Teeraina", "Tabuaeran", "Kiritimati", "Kanton"],
}
# The General Report's tables, as transcribed from its rendered pages, one
# line each: the line's label, then its figures in the table's column order
# ("-" is none). The country's line is called Kiribati here, and each
# division's carries "Division", which the report prints for all but South
# Tarawa's.
G2_COLUMNS = ("Total", "Male", "Female")
G2 = """
Kiribati | 119,438 58,904 60,534
South Tarawa Division | 63,072 30,281 32,791
South Tarawa | 44,643 21,302 23,341
Betio | 18,429 8,979 9,450
Northern Division | 20,735 10,359 10,376
Makin | 1,914 968 946
Butaritari | 3,250 1,626 1,624
Marakei | 2,738 1,350 1,388
Abaiang | 5,815 2,972 2,843
North Tarawa | 7,018 3,443 3,575
Central Division | 8,344 4,219 4,125
Banaba | 333 183 150
Maiana | 2,345 1,193 1,152
Abemama | 3,255 1,614 1,641
Kuria | 1,190 605 585
Aranuka | 1,221 624 597
Southern Division | 15,994 8,134 7,860
Nonouti | 2,749 1,415 1,334
North Tabiteuea | 4,181 2,081 2,100
South Tabiteuea | 1,356 674 682
Beru | 2,214 1,117 1,097
Nikunau | 2,055 1,089 966
Onotoa | 1,417 732 685
Tamana | 1,028 514 514
Arorae | 994 512 482
Line Islands & Phoenix Division | 11,293 5,911 5,382
Teeraina | 1,893 994 899
Tabuaeran | 1,990 1,060 930
Kiritimati | 7,369 3,837 3,532
Kanton | 41 20 21
"""
A10A_COLUMNS = ("Total", "0-4", "0-14", "15-49", "50-64", "65+", "Median")
A10A = """
Kiribati | 119,438 15,325 42,920 59,538 12,399 4,581 20.4
South Tarawa Division | 63,072 8,288 21,645 32,938 6,224 2,265 21.1
South Tarawa | 44,643 5,823 15,271 23,258 4,454 1,660 21.2
Betio | 18,429 2,465 6,374 9,680 1,770 605 20.8
Northern Division | 20,735 2,655 8,025 9,858 2,047 805 18.6
Makin | 1,914 239 827 825 172 90 15.4
Butaritari | 3,250 448 1,328 1,421 358 143 16.8
Marakei | 2,738 347 1,125 1,212 279 122 17
Abaiang | 5,815 720 2,172 2,856 568 219 19.6
North Tarawa | 7,018 901 2,573 3,544 670 231 19.8
Central Division | 8,344 1,026 3,048 3,982 955 359 20.4
Banaba | 333 57 150 133 40 10 13.8
Maiana | 2,345 265 860 1,089 297 99 20.8
Abemama | 3,255 388 1,084 1,699 328 144 22.2
Kuria | 1,190 168 479 528 131 52 17.1
Aranuka | 1,221 148 475 533 159 54 19
Southern Division | 15,994 1,868 5,781 7,364 2,028 821 21.1
Nonouti | 2,749 325 1,010 1,274 327 138 20.5
North Tabiteuea | 4,181 539 1,616 1,985 432 148 18.6
South Tabiteuea | 1,356 178 523 598 165 70 18.9
Beru | 2,214 216 708 1,041 339 126 24.8
Nikunau | 2,055 253 802 932 228 93 18.7
Onotoa | 1,417 163 480 640 209 88 23
Tamana | 1,028 100 322 450 166 90 26
Arorae | 994 94 320 444 162 68 25.2
Line Islands & Phoenix Division | 11,293 1,488 4,421 5,396 1,145 331 18.1
Teeraina | 1,893 266 784 884 178 47 16.2
Tabuaeran | 1,990 254 818 906 201 65 16.9
Kiritimati | 7,369 964 2,802 3,588 760 219 18.9
Kanton | 41 4 17 18 6 - 17.9
"""
A3B_COLUMNS = ("Total", "I-Kiribati", "Kiribati/Mix", "Tuvaluan", "Chinese", "Australian",
               "New Zealander", "Fijian", "Solomon Islander", "Other Pacific Islander", "Asian",
               "European", "USA", "Other ethnicity")
A3B = """
Kiribati | 119,438 114,316 4,491 292 72 12 6 40 39 59 50 30 8 23
South Tarawa Division | 63,072 59,642 3,029 199 59 8 4 29 24 39 12 16 1 10
South Tarawa | 44,643 42,296 2,035 152 50 5 3 26 16 35 6 12 1 6
Betio | 18,429 17,346 994 47 9 3 1 3 8 4 6 4 0 4
Northern Division | 20,735 20,433 264 10 4 1 1 3 6 3 - 2 - 8
Makin | 1,914 1,907 6 - - - 1 - - - - - - -
Butaritari | 3,250 3,187 57 2 - - - - 3 1 - - - -
Marakei | 2,738 2,733 5 - - - - - - - - - - -
Abaiang | 5,815 5,680 124 3 2 - - 3 1 1 - 1 - -
North Tarawa | 7,018 6,926 72 5 2 1 - - 2 1 - 1 - 8
Central Division | 8,344 8,198 129 6 2 - - 1 3 4 1 - - -
Banaba | 333 317 15 1 - - - - - - - - - -
Maiana | 2,345 2,321 22 1 - - - - - - 1 - - -
Abemama | 3,255 3,243 5 1 1 - - 1 3 1 - - - -
Kuria | 1,190 1,109 79 1 - - - - - 1 - - - -
Aranuka | 1,221 1,208 8 2 1 - - - - 2 - - - -
Southern Division | 15,994 15,610 356 18 - 2 - 3 2 1 - - - 2
Nonouti | 2,749 2,674 65 7 - - - 2 1 - - - - -
North Tabiteuea | 4,181 4,016 153 7 - 1 - 1 - 1 - - - 2
South Tabiteuea | 1,356 1,348 7 1 - - - - - - - - - -
Beru | 2,214 2,205 9 - - - - - - - - - - -
Nikunau | 2,055 1,943 109 2 - - - - 1 - - - - -
Onotoa | 1,417 1,413 3 1 - - - - - - - - - -
Tamana | 1,028 1,020 7 - - 1 - - - - - - - -
Arorae | 994 991 3 - - - - - - - - - - -
Line Islands & Phoenix Division | 11,293 10,433 713 59 7 1 1 4 4 12 37 12 7 3
Teeraina | 1,893 1,875 13 3 2 - - - - - - - - -
Tabuaeran | 1,990 1,945 38 4 2 - - - - - - 1 - -
Kiritimati | 7,369 6,572 662 52 3 1 1 4 4 12 37 11 7 3
Kanton | 41 41 - - - - - - - - - - - -
"""
# Table A-3b's groups in the map's words: its "Kiribati/Mix" and "USA".
ETHNIC = {"Kiribati/Mix": "I-Kiribati/mixed", "USA": "American"}

AGE = re.compile(r"^([MFT])_(\d{2})_(\d{2})$")
OPEN = re.compile(r"^([MFT])_(\d{2})plus$", re.I)


# ---------------------------------------------------------------------------
# The Office's counts
# ---------------------------------------------------------------------------

def sheet_count(rows: list[list[Any]], sheet: str) -> int:
    """The 2020 "Population (Census)" figure on one island's profile sheet."""
    header = next((r for r in rows if r and "2020" in [str(c).strip() for c in r if c]), None)
    check(header is not None, f"kiribati_census: sheet {sheet!r} has no 2020 column")
    col = [str(c).strip() if c is not None else "" for c in header].index("2020")
    row = next((r for r in rows if r and str(r[0] or "").startswith("Population (Census)")),
               None)
    check(row is not None and len(row) > col and number(row[col]) is not None,
          f"kiribati_census: sheet {sheet!r} has no 2020 census count")
    return int(number(row[col]))


def summary_counts(rows: list[list[Any]]) -> dict[str, int]:
    """{name: total} from the summary sheet's island block (name, five age groups, total)."""
    out: dict[str, int] = {}
    for row in rows:
        cells = list(row) + [None] * 16
        name = str(cells[9] or "").strip()
        figures = [number(c) for c in cells[10:16]]
        if not name or any(f is None for f in figures):
            continue
        if abs(sum(figures[:5]) - figures[5]) < 0.5 and name not in out:
            out[name] = int(figures[5])
    return out


def read_profile(book) -> dict[str, int]:
    counts: dict[str, int] = {}
    names = {s.strip(): s for s in book.sheetnames}
    for island, (sheet, _) in list(ISLANDS.items()) + list(UNDRAWN.items()):
        check(sheet in names, f"kiribati_census: the workbook has no sheet for {sheet}")
        counts[island] = sheet_count(rows_of(book, names[sheet]), sheet)
    summary = summary_counts(rows_of(book, "Check"))
    for island, (sheet, _) in list(ISLANDS.items()) + list(UNDRAWN.items()):
        listed = summary.get(SUMMARY_NAMES.get(sheet, sheet))
        check(listed == counts[island],
              f"kiribati_census: {island} is {counts[island]:,} on its sheet and {listed} in "
              f"the summary")
    check(sum(counts.values()) == NATIONAL == summary.get("Total"),
          f"kiribati_census: the islands add up to {sum(counts.values()):,}, not {NATIONAL:,}")
    log(f"  Island Profile: 24 islands adding to {NATIONAL:,}, each sheet agreeing with the "
        f"summary")
    return counts


# ---------------------------------------------------------------------------
# The General Report's tables, transcribed
# ---------------------------------------------------------------------------

def adds_to_divisions(rows: dict[str, dict[str, float]], columns: tuple[str, ...],
                      what: str) -> None:
    """Each division's line is its islands', and the country's its divisions'."""
    for column in columns:
        for division, members in DIVISIONS.items():
            parts = sum(rows[m][column] for m in members)
            check(parts == rows[division][column],
                  f"kiribati_census: {what} gives {division} {rows[division][column]:,.0f} "
                  f"{column}, its islands {parts:,.0f}")
        parts = sum(rows[d][column] for d in DIVISIONS)
        check(parts == rows["Kiribati"][column],
              f"kiribati_census: {what}'s divisions make {parts:,.0f} {column}, not "
              f"{rows['Kiribati'][column]:,.0f}")


def read_report(counts: dict[str, int]) -> dict[str, Any]:
    """Tables G-2, A-10a and A-3b, checked against each other and the Island Profile."""
    g2 = transcription(G2, G2_COLUMNS, "kiribati_census: Table G-2")
    a10 = transcription(A10A, A10A_COLUMNS, "kiribati_census: Table A-10a", adds_up=False)
    a3 = transcription(A3B, A3B_COLUMNS, "kiribati_census: Table A-3b")
    adds_to_divisions(g2, G2_COLUMNS, "Table G-2")
    adds_to_divisions(a10, A10A_COLUMNS[:-1], "Table A-10a")
    adds_to_divisions(a3, A3B_COLUMNS, "Table A-3b")
    check(set(g2) == set(a10) == set(a3), "kiribati_census: the three tables list different "
                                          "lines")
    check(a10["Kiribati"]["Median"] == A10A_NATIONAL,
          f"kiribati_census: Table A-10a's country median reads {a10['Kiribati']['Median']}")
    wrong_side: set[str] = set()
    for label, row in a10.items():
        broad = row["0-14"] + row["15-49"] + row["50-64"] + row["65+"]
        check(broad == row["Total"] and row["0-4"] <= row["0-14"],
              f"kiribati_census: Table A-10a's age groups for {label} make {broad:,.0f}, not "
              f"{row['Total']:,.0f}")
        check(g2[label]["Total"] == row["Total"] == a3[label]["Total"],
              f"kiribati_census: {label} is {g2[label]['Total']:,.0f} in Table G-2, "
              f"{row['Total']:,.0f} in A-10a and {a3[label]['Total']:,.0f} in A-3b")
        # Fewer than half under 15 puts the median at 15 or over, and the other way round.
        if (row["0-14"] < row["Total"] / 2) != (row["Median"] >= 15):
            wrong_side.add(label)
    for island, label in REPORT_ROWS.items():
        check(g2[label]["Total"] == counts[island],
              f"kiribati_census: {island} is {counts[island]:,} in the Island Profile and "
              f"{g2[label]['Total']:,.0f} in Table G-2")
    log(f"  General Report: Tables G-2, A-10a, A-3b for {len(REPORT_ROWS)} islands, adding up "
        f"and agreeing with the Island Profile; A-10a medians on the wrong side of 15 for "
        f"their own age groups: {sorted(wrong_side)}")
    return {"g2": g2, "a10": a10, "a3": a3, "wrong_side": wrong_side}


# ---------------------------------------------------------------------------
# The 2015 volume's religion by island
# ---------------------------------------------------------------------------

def plain(text: str) -> str:
    return " ".join(text.replace("’", "'").split())


def figures_of(line: str) -> tuple[str, list[str]] | None:
    """(first word, the figures after it) when every word after the first is a figure."""
    first, _, rest = line.strip().partition(" ")
    cells = rest.split()
    if cells and all(FIGURE.match(c) for c in cells):
        return first, cells
    return None


def as_int(cell: str) -> int:
    return 0 if cell == "-" else int(cell.replace(",", ""))


def read_table6(pages: list[str]) -> dict[str, dict[str, list[int]]]:
    """{line: {"Total"/"Male"/"Female": [total, 14 religions]}}, the country as "Kiribati".

    Each page of the table is read from its title on, its heading checked word
    for word, and up to the next table's title, which the last page carries.
    """
    rows: dict[str, dict[str, list[int]]] = {}
    pages_read = 0
    for page in pages:
        lines = page.splitlines()
        starts = [i for i, line in enumerate(lines) if T6_TITLE.match(line.strip())]
        if not starts:
            continue
        pages_read += 1
        current = None if rows else "Kiribati"
        heading: list[str] = []
        reading_heading = True
        for line in lines[starts[-1] + 1:]:
            stripped = line.strip()
            if re.match(r"^Table \d", stripped):
                break
            row = figures_of(stripped)
            if row and row[0] in SEXES:
                reading_heading = False
                sex, cells = row
                check(len(cells) == 1 + len(T6_COLUMNS),
                      f"kiribati_census: Table 6's {current} {sex} line has {len(cells)} "
                      f"figures for {1 + len(T6_COLUMNS)} columns: {stripped!r}")
                check(current is not None, f"kiribati_census: Table 6 has figures before "
                                           f"an island on a continued page: {stripped!r}")
                check(sex not in rows.setdefault(current, {}),
                      f"kiribati_census: Table 6 gives {current} two {sex} lines")
                rows[current][sex] = [as_int(c) for c in cells]
            elif stripped in T6_ISLANDS:
                reading_heading = False
                check(stripped not in rows, f"kiribati_census: Table 6 lists {stripped} twice")
                current = stripped
            elif reading_heading and stripped:
                heading.append(stripped)
        check(plain(" ".join(heading)) == T6_HEADER,
              f"kiribati_census: a page of Table 6 is headed {plain(' '.join(heading))!r}")
    check(pages_read >= 1, "kiribati_census: the 2015 volume has no Table 6")
    check(set(rows) == {"Kiribati", *T6_ISLANDS},
          f"kiribati_census: Table 6 lists {sorted(set(rows) ^ {'Kiribati', *T6_ISLANDS})} "
          f"against its 24 islands and the country")
    for name, sexes in rows.items():
        check(set(sexes) == set(SEXES), f"kiribati_census: Table 6 gives {name} {sorted(sexes)}")
        for sex, cells in sexes.items():
            check(sum(cells[1:]) == cells[0],
                  f"kiribati_census: Table 6's religions for {name} ({sex}) make "
                  f"{sum(cells[1:]):,}, not {cells[0]:,}")
        check([m + f for m, f in zip(sexes["Male"], sexes["Female"])] == sexes["Total"],
              f"kiribati_census: Table 6's males and females for {name} do not make its total")
    for i in range(1 + len(T6_COLUMNS)):
        made = sum(rows[island]["Total"][i] for island in T6_ISLANDS)
        check(made == rows["Kiribati"]["Total"][i],
              f"kiribati_census: Table 6's islands make {made:,} in column {i}, the country "
              f"{rows['Kiribati']['Total'][i]:,}")
    check(rows["Kiribati"]["Total"][0] == NATIONAL_2015,
          f"kiribati_census: Table 6 counts {rows['Kiribati']['Total'][0]:,} people, not "
          f"{NATIONAL_2015:,}")
    return rows


def read_table1a(pages: list[str]) -> dict[str, int]:
    """{line: 2015 population} from Table 1a, whose STarawa still holds Betio."""
    best: dict[str, int] = {}
    for page in pages:
        lines = page.splitlines()
        if not any(T1A_TITLE.match(line.strip()) for line in lines):
            continue
        found = {}
        for line in lines:
            row = figures_of(line)
            if row and (row[0] in T6_ISLANDS or row[0] == "Total") and len(row[1]) == 4:
                found[row[0]] = as_int(row[1][2])
        if len(found) > len(best):
            best = found
    expected = {"Total", *T6_ISLANDS} - {"Betio"}
    check(set(best) == expected, f"kiribati_census: Table 1a lists "
                                 f"{sorted(set(best) ^ expected)} against its islands")
    return best


def read_religion(pages: list[str]) -> dict[str, dict[str, list[int]]]:
    """Table 6, checked against Table 1a's island populations of the same census."""
    table6, table1a = read_table6(pages), read_table1a(pages)
    for island in T6_ISLANDS:
        if island == "Betio":
            continue
        made = table6[island]["Total"][0] + (table6["Betio"]["Total"][0]
                                             if island == "STarawa" else 0)
        check(made == table1a[island],
              f"kiribati_census: Table 6 counts {made:,} on {island}"
              f"{' with Betio' if island == 'STarawa' else ''}, Table 1a {table1a[island]:,}")
    check(table1a["Total"] == NATIONAL_2015,
          f"kiribati_census: Table 1a counts {table1a['Total']:,} people in 2015")
    log(f"  2015 volume: Table 6's 24 islands make every column of the country's "
        f"{NATIONAL_2015:,}, and each is its Table 1a population")
    return table6


KPC_NOTE = (" The table has one column for the Kiribati Protestant Church ('KPC'); the 2020 "
            "census lists the Kiribati Uniting Church and the KPC apart (21.2% and 8.4% of the "
            "country), so the 2015 'KPC' share is to be read against their sum.")


def religion_fields(labels: list[str], table6: dict[str, dict[str, list[int]]],
                    where: str) -> dict[str, Any]:
    """The 2015 religion of the Table 6 lines named, added up."""
    totals = [sum(table6[label]["Total"][i] for label in labels)
              for i in range(1 + len(T6_COLUMNS))]
    counts: dict[str, float] = {}
    folded = {}
    for (printed, name), count in zip(T6_COLUMNS, totals[1:]):
        counts[name] = counts.get(name, 0) + count
        if printed in FOLDED and count:
            folded[printed] = count
    added = (f" The islands added up: {', '.join(labels)}." if len(labels) > 1 else "")
    fold_note = ""
    if folded:
        fold_note = (" Counted with the table's 'Other': "
                     + " and ".join(f"{n:,} answering '{p}'" for p, n in folded.items())
                     + (", bodies" if len(folded) > 1 else ", a body")
                     + " whose tradition the volume does not state.")
    return {
        "religion": shares_of(counts, totals[0]),
        "religion_year": RELIGION_YEAR,
        "religion_note": (
            f"Religion of the {totals[0]:,} people of {where} at the 2015 census (Volume 1, "
            f"Table 6, by island), the latest count of it below the country: the 2020 census "
            f"publishes religion for the country (General Report, Table G-3) and maps it by "
            f"island without figures (Census Atlas, Map 18).{added}{fold_note}{KPC_NOTE}"),
    }


def report_fields(labels: list[str], report: dict[str, Any], where: str) -> dict[str, Any]:
    """Sex and ethnicity of the islands named, added up."""
    g2, a3 = report["g2"], report["a3"]
    male = sum(g2[label]["Male"] for label in labels)
    female = sum(g2[label]["Female"] for label in labels)
    people = male + female
    ethnic = {ETHNIC.get(c, c): sum(a3[label][c] for label in labels) for c in A3B_COLUMNS[1:]}
    added = (f" The islands added up: {', '.join(labels)}." if len(labels) > 1 else "")
    fields: dict[str, Any] = {
        "sex_ratio": measure(sex_ratio(male, female), unit="males_per_100_females", year=YEAR,
                             source=f"{REPORT} (Table G-2)"),
        "sex_ratio_note": (f"Males per 100 females, 2020 census (General Report, Table G-2: "
                           f"{male:,.0f} males, {female:,.0f} females).{added}"),
        "ethnicity": shares_of(ethnic, people),
        "ethnicity_year": YEAR,
        "ethnicity_note": (f"Ethnicity, 2020 census (General Report, Table A-3b, which the "
                           f"report prints as a picture of the table; transcribed). "
                           f"'I-Kiribati/mixed' is the table's 'Kiribati/Mix' and 'American' "
                           f"its 'USA'.{added}"),
    }
    return fields


# ---------------------------------------------------------------------------
# SPC's age and sex table
# ---------------------------------------------------------------------------

def age_table(rows: list[list[Any]], name_col: str) -> dict[str, dict[str, Any]]:
    """{unit: {male, female, groups, males, females}} from one sheet of SPC's island table.

    ``groups`` is everyone's (low, high, people) by five-year group, the last
    open; ``males`` and ``females`` the same for each sex.
    """
    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    closed = sorted({(int(m.group(2)), int(m.group(3))) for c in header if (m := AGE.match(c))})
    top = sorted({int(m.group(2)) for c in header if (m := OPEN.match(c))})
    check(len(top) == 1 and closed[0][0] == 0
          and all(b[0] == a[1] + 1 for a, b in zip(closed, closed[1:]))
          and closed[-1][1] + 1 == top[0],
          f"kiribati_census: SPC's age groups {closed} + {top} do not run without a gap")
    index = {c: i for i, c in enumerate(header)}
    opens = {m.group(1): c for c in header if (m := OPEN.match(c))}
    out: dict[str, dict[str, Any]] = {}
    for row in rows[1:]:
        cells = list(row) + [None] * len(header)
        name = str(cells[index[name_col]] or "").strip()
        if not name:
            continue
        groups, by_male, by_female, males, females = [], [], [], 0, 0
        for low, high in closed:
            m = int(number(cells[index[f"M_{low:02d}_{high:02d}"]]) or 0)
            f = int(number(cells[index[f"F_{low:02d}_{high:02d}"]]) or 0)
            groups.append((low, high, m + f))
            by_male.append((low, high, m))
            by_female.append((low, high, f))
            males, females = males + m, females + f
        m = int(number(cells[index[opens["M"]]]) or 0)
        f = int(number(cells[index[opens["F"]]]) or 0)
        groups.append((top[0], None, m + f))
        by_male.append((top[0], None, m))
        by_female.append((top[0], None, f))
        males, females = males + m, females + f
        out[name] = {"male": males, "female": females, "groups": groups,
                     "males": by_male, "females": by_female,
                     "printed": (number(cells[index["M_TL"]]), number(cells[index["F_TL"]]))}
    return out


def checked(unit: dict[str, Any], name: str) -> dict[str, Any]:
    """A row whose age groups make the totals it prints, or the run stops."""
    printed = unit["printed"]
    check(printed == (unit["male"], unit["female"]),
          f"kiribati_census: {name}'s groups make {unit['male']} males and {unit['female']} "
          f"females; its totals say {printed}")
    return unit


def combine(parts: list[dict[str, Any]], sign: list[int]) -> dict[str, Any]:
    """Rows added (sign 1) or taken away (sign -1), group by group and sex by sex."""
    def add(key: str) -> list[tuple[int, int | None, int]]:
        bands = parts[0][key]
        return [(lo, hi, sum(s * p[key][i][2] for p, s in zip(parts, sign)))
                for i, (lo, hi, _) in enumerate(bands)]
    return {"male": sum(s * p["male"] for p, s in zip(parts, sign)),
            "female": sum(s * p["female"] for p, s in zip(parts, sign)),
            "groups": add("groups"), "males": add("males"), "females": add("females")}


def minus(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return combine([a, b], [1, -1])


def read_cod(book) -> dict[str, dict[str, Any]]:
    """SPC's figures for the drawn islands, the island groups and the country.

    The country ("Kiribati") is the island groups' rows added up; each drawn
    island is its own row, but for Betio (SPC's village "BetioEast") and
    Tarawa Teinainano (South Tarawa without it).
    """
    groups = age_table(rows_of(book, "kir_admpop_adm1_2020"), "ADM1_EN")
    islands = age_table(rows_of(book, "kir_admpop_adm2_2020"), "ADM2_EN")
    villages = age_table(rows_of(book, "kir_admpop_adm3_2020"), "ADM3_EN")
    out: dict[str, dict[str, Any]] = {}
    for island, (_, row) in list(ISLANDS.items()) + list(UNDRAWN.items()):
        if row:
            check(row in islands, f"kiribati_census: SPC has no island {row!r}")
            out[island] = checked(islands[row], row)
    check(islands.get("Betio", {}).get("male", 0) == 0,
          "kiribati_census: SPC now tabulates Betio as an island; read it from there")
    betio = checked(villages["BetioEast"], "BetioEast")
    out["Betio"] = betio
    out["Tarawa Teinainano"] = minus(checked(islands["South Tarawa"], "South Tarawa"), betio)
    for name in ("Gilbert Islands", "Line Islands"):
        out[name] = checked(groups[name], name)
    rows = [checked(row, name) for name, row in groups.items()]
    out["Kiribati"] = combine(rows, [1] * len(rows))
    return out


def check_national(cod: dict[str, dict[str, Any]]) -> dict[str, float]:
    """SPC's country medians, each within MEDIAN_SLACK of the Office's Census Atlas.

    This is what licenses SPC's groups as the census's ages: the Office's own
    published medians for the country -- everyone, males and females -- come
    out of them. Table A-10a's country figure does not.
    """
    nation = cod["Kiribati"]
    got = {"everyone": median_from_groups(nation["groups"]),
           "males": median_from_groups(nation["males"]),
           "females": median_from_groups(nation["females"])}
    for who, published in ATLAS_MEDIANS.items():
        check(got[who] is not None and abs(got[who] - published) <= MEDIAN_SLACK,
              f"kiribati_census: SPC's groups give the country's {who} a median of {got[who]}, "
              f"the Census Atlas {published}")
    log(f"  SPC's country medians {got} against the Census Atlas's {ATLAS_MEDIANS} "
        f"({nation['male'] + nation['female']:,} people); Table A-10a prints {A10A_NATIONAL}")
    return got


def compare_medians(report: dict[str, Any], cod: dict[str, dict[str, Any]]
                    ) -> dict[str, Any]:
    """Each island's Table A-10a median beside SPC's for the same island.

    Measured, not assumed: how many islands the printed column puts more than a
    year away from the census's own age groups, and how far at most.
    """
    pairs: dict[str, tuple[float, float]] = {}
    for island, label in REPORT_ROWS.items():
        if island in cod:
            pairs[island] = (report["a10"][label]["Median"],
                             median_from_groups(cod[island]["groups"]))
    apart = {i: p - s for i, (p, s) in pairs.items() if abs(p - s) > 1.0}
    lowest = min(apart.values(), default=0.0)
    log(f"  Table A-10a against SPC's groups: {len(apart)} of {len(pairs)} islands more than a "
        f"year apart, the printed figure lower on {sum(d < 0 for d in apart.values())}, by up "
        f"to {abs(lowest):.1f} years: " + ", ".join(f"{i} {p} v {s}" for i, (p, s) in
                                                     sorted(pairs.items())))
    return {"pairs": pairs, "apart": len(apart), "islands": len(pairs),
            "most": round(max((abs(d) for d in apart.values()), default=0.0), 1)}


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

LANGUAGE_GAP = (
    "No Kiribati census tabulates language. The 2020 census's General Report and Census Atlas "
    "report only whether people can read and write, in any language; the 2015 census's "
    "Volume 1 likewise has literacy (Table 15) and no language table, and the 2010 census's "
    "tables give literacy (Table 16) and none either.")
MEDIAN_NOTE = (
    "Median age interpolated within the five-year age group that holds the middle person, "
    "from the Pacific Community's tabulation of the 2020 census by island, five-year age "
    "group and sex (UNFPA and OCHA's COD-PS for Kiribati, \"Baseline used: Kiribati NSO\"), "
    "which counts {people:,} people here against the census's final {final:,}{extra}. The "
    "same tabulation gives the country a median of {national}, and the Statistics Office's "
    "own Census Atlas prints {atlas}.{printed}")
PRINTED = (
    " The General Report prints {median} for {island} (Table A-10a), a column not used here: "
    "it puts the country at {a10_nation} against the Atlas's {atlas}, and {apart} of its "
    "{islands} islands more than a year from what the census's own five-year groups give, "
    "by up to {most} years.")
WRONG_SIDE = (
    " Its own age groups contradict it besides: {young:,.0f} of the island's {people:,.0f} "
    "people are under 15, {side} half, which puts the median {where} 15.")
GROUP_PRINTED = (
    " The General Report prints medians by island and division, not by island group, and its "
    "island figures (Table A-10a) are not used, for the reason each island's record gives.")
NO_MEDIAN = (
    "Kanton's {people} people are not in the Pacific Community's tabulation of the 2020 "
    "census by age, the source of every other island's median here. The General Report "
    "prints {median} for Kanton (Table A-10a), a column not used for any island: it puts the "
    "country at {a10_nation} against the {atlas} of the Office's own Census Atlas, and "
    "{apart} of its {islands} islands more than a year from what the census's own five-year "
    "groups give, by up to {most} years.")


def median_fields(unit: str, where: str, label: str | None, cod: dict[str, Any],
                  report: dict[str, Any], compared: dict[str, Any], final: int
                  ) -> dict[str, Any]:
    """SPC's median for one island or island group, or why there is none.

    ``label`` is the island's line in the General Report, None for an island
    group (which the report does not tabulate).
    """
    context = {"a10_nation": A10A_NATIONAL, "atlas": ATLAS_MEDIANS["everyone"],
               "apart": compared["apart"], "islands": compared["islands"],
               "most": compared["most"]}
    figures = cod.get(unit)
    if not figures or not figures["male"] + figures["female"]:
        printed = report["a10"]["Kanton"]["Median"]
        return {"median_age": gap(NOT_AVAILABLE, NO_MEDIAN.format(people=final, median=printed,
                                                                  **context))}
    if label is None:
        printed = GROUP_PRINTED
    else:
        row = report["a10"][label]
        printed = PRINTED.format(median=row["Median"], island=where, **context)
        if label in report["wrong_side"]:
            young = row["0-14"] < row["Total"] / 2
            printed += WRONG_SIDE.format(young=row["0-14"], people=row["Total"],
                                         side="fewer than" if young else "more than",
                                         where="at or over" if young else "under")
    extra = (" -- its village 'BetioEast'" if unit == "Betio" else
             " -- South Tarawa without Betio" if unit == "Tarawa Teinainano" else "")
    national = median_from_groups(cod["Kiribati"]["groups"])
    return {
        "median_age": measure(median_from_groups(figures["groups"]), unit="years", year=YEAR,
                              source=f"{COD}, {YEAR}"),
        "median_age_note": MEDIAN_NOTE.format(
            people=figures["male"] + figures["female"], final=final, extra=extra,
            national=national, atlas=ATLAS_MEDIANS["everyone"], printed=printed),
    }


def census_fields(final: int, note: str) -> dict[str, Any]:
    return {
        "population": population(final, YEAR, PROFILE),
        "population_note": note,
        "language": gap(NOT_AVAILABLE, LANGUAGE_GAP),
    }


def sources(with_median: bool) -> list[dict[str, Any]]:
    """The record's citations, SPC's only where the record carries its median."""
    out = [
        {"field": "population", "name": PROFILE, "url": PROFILE_URL, "year": YEAR,
         "license": LICENCE},
        {"field": "sex_ratio/ethnicity", "name": REPORT, "url": REPORT_URL, "year": YEAR,
         "license": LICENCE},
        {"field": "religion", "name": f"{RELIGION_REPORT}, Table 6: Population by island, sex "
                                      f"and religion", "url": RELIGION_URL,
         "year": RELIGION_YEAR, "license": LICENCE},
        {"field": "language (why empty)", "name": f"{REPORT}; Kiribati Census Atlas",
         "url": ATLAS_URL, "year": YEAR, "license": LICENCE},
    ]
    if with_median:
        out.insert(2, {"field": "median_age", "name": COD, "url": COD_PAGE, "year": YEAR,
                       "license": "Creative Commons Attribution for Intergovernmental "
                                  "Organisations"})
    return out


def small(fields: dict[str, Any], labels: list[str], report: dict[str, Any]) -> dict[str, Any]:
    """Withhold what Kanton's 41 people cannot carry, from Table G-2's sexes."""
    male = sum(report["g2"][label]["Male"] for label in labels)
    female = sum(report["g2"][label]["Female"] for label in labels)
    return withhold_small(fields, male + female, male, female)


def drawn_groups(island_units: dict[str, dict[str, Any]],
                 group_units: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """{boundary label: the drawn islands the map puts under that polygon}, which
    must be ``DRAWN_GROUPS``' islands (Makin aside, which no polygon draws): the
    parents the build gave the island polygons, by where most of each lies."""
    by_shape = {unit["id"]: label for label, unit in group_units.items()}
    out: dict[str, list[str]] = {label: [] for label in group_units}
    for island, unit in island_units.items():
        label = by_shape.get(unit.get("parent"))
        check(label is not None, f"kiribati_census: {island} is drawn under no island group "
                                 f"({unit.get('parent')})")
        out[label].append(island)
    for label, (_, islands, _) in DRAWN_GROUPS.items():
        expected = sorted(i for i in islands if i in ISLANDS)
        check(sorted(out.get(label, [])) == expected,
              f"kiribati_census: the map draws {sorted(out.get(label, []))} under the polygon "
              f"labelled {label}, where DRAWN_GROUPS has {expected}; measure the boundary file "
              "again")
    return out


def build(counts: dict[str, int], cod: dict[str, dict[str, Any]], report: dict[str, Any],
          table6: dict[str, dict[str, list[int]]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> list[dict[str, Any]]:
    group_units = bind_level({g: (g, "") for g in GROUPS}, admin1, {})
    parents = {u["id"]: u["name"] for u in admin1}
    island_units = bind_level({i: (i, "") for i in ISLANDS}, admin2, parents)
    drawn_groups(island_units, group_units)
    check(set(T6_ROWS.values()) == set(T6_ISLANDS),
          "kiribati_census: the drawn islands and Makin are not Table 6's 24 lines")
    check(sorted(i for _, islands, _ in DRAWN_GROUPS.values() for i in islands)
          == sorted(i for islands in GROUPS.values() for i in islands),
          "kiribati_census: DRAWN_GROUPS does not hold every island once")
    compared = compare_medians(report, cod)
    census = []
    for label, unit in group_units.items():
        name, islands, why = DRAWN_GROUPS[label]
        final = sum(counts[i] for i in islands)
        whole = sorted(islands) == sorted(GROUPS.get(label, []))
        note = (f"{why} " if why else "") + (
            f"The census counts of its islands added up: {', '.join(islands)}."
            if len(islands) > 1 else "Kanton, the group's one inhabited island.")
        if not whole and label in GROUPS:
            group = sum(counts[i] for i in GROUPS[label])
            note += f" The {label.replace(' Islands', '')} group as a whole counted {group:,}."
        labels = [REPORT_ROWS[i] for i in islands]
        # SPC tabulates the group the census groups it; a polygon that draws
        # another set of islands takes the sum of those islands' rows.
        ages = dict(cod)
        if not whole:
            parts = [cod[i] for i in islands if i in cod]
            ages[name] = combine(parts, [1] * len(parts))
        median = median_fields(label if whole else name, name, None, ages, report, compared,
                               final)
        fields = small({**census_fields(final, note), **median,
                        **report_fields(labels, report, name),
                        **religion_fields([T6_ROWS[i] for i in islands], table6, name)},
                       labels, report)
        census.append(unit_record("KIR", label, name, unit, "admin1", None,
                                  sources("median_age_note" in median), **fields))
    for island, unit in island_units.items():
        note = "The 2020 census count (Island Profile tables)."
        median = median_fields(island, island, REPORT_ROWS[island], cod, report, compared,
                               counts[island])
        fields = small({**census_fields(counts[island], note), **median,
                        **report_fields([REPORT_ROWS[island]], report, island),
                        **religion_fields([T6_ROWS[island]], table6, island)},
                       [REPORT_ROWS[island]], report)
        census.append(unit_record("KIR", island, unit["name"], unit, "admin2", None,
                                  sources("median_age_note" in median), **fields))
    log(f"  no polygon: Makin ({counts['Makin']:,} people), counted in the Gilbert Islands")
    return census


def pdf_pages(url: str) -> list[str]:
    from pypdf import PdfReader  # noqa: PLC0415
    blob = http_get(url, binary=True, timeout=600, headers={"Accept": "application/pdf,*/*"})
    check(isinstance(blob, bytes) and blob[:5] == b"%PDF-", f"kiribati_census: {url} is no PDF")
    return [(page.extract_text() or "") for page in PdfReader(io.BytesIO(blob)).pages]


def cod_book():
    package = json.loads(http_get(COD_PACKAGE, cache=False))["result"]
    url = next((r["url"] for r in package.get("resources", [])
                if str(r.get("name", "")).lower() == COD_FILE), None)
    check(url is not None, f"kiribati_census: {COD_PACKAGE} lists no {COD_FILE}")
    return workbook(url)


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("kiribati_census: 2020 census counts, the General Report's island tables, and SPC's "
        "age and sex tabulation")
    counts = read_profile(workbook(PROFILE_URL))
    report = read_report(counts)
    table6 = read_religion(pdf_pages(RELIGION_URL))
    cod = read_cod(cod_book())
    check_national(cod)
    census = build(counts, cod, report, table6, load_units("KIR", "admin1"),
                   load_units("KIR", "admin2"))
    log("  " + summarise(census))
    write_json(PROCESSED / OUT, census)
    log(f"  wrote {len(census)} records")
    stale = PROCESSED / OUT_AGES
    if stale.exists():
        stale.unlink()
        log(f"  removed {OUT_AGES}: SPC's medians are this file's now")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
