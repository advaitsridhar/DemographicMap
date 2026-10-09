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

**Age, sex and ethnicity by island** the Office publishes in its General
Report, whose tables are pictures with no text layer. Three are transcribed
here from the rendered pages: Table G-2 (p. 18), each island's people by sex;
Table A-10a (p. 40), each island's broad age groups and median age; Table
A-3b (p. 26), each island's ethnicity. Each must add up across its columns and
down to its divisions and the country, and give every island the count the
Island Profile gives it -- four readings of one number, two of them from
different pages. A printed median that its own age groups contradict (on the
wrong side of 15, against the share of the island under 15) is not used, and
the record says so: Banaba's.

**The island groups' medians** have no table: the Office's medians are by
island and division, and the map's first level is the three island groups.
Those two (Gilbert, Line) come from the Pacific Community's tabulation of the
same census by island and five-year age group, which UNFPA and OCHA publish as
the Common Operational Dataset for Kiribati (``cod-ps-kir``, "Baseline used:
Kiribati NSO"). It counts 119,940 people, 0.4% more than the final count, so
its medians and sex ratios go to a file of their own that the build lists as
fill-only, behind the Office's figures wherever those exist; each says how
many people it describes. It folds Betio into South Tarawa and tabulates Betio
as the village "BetioEast", so Betio's figures are that village's and
Teinainano's are South Tarawa's without it.

**Religion and language** the records say why are empty: religion is
published for the country and mapped by island without figures; language is
not tabulated at all.

**What the map draws.** 23 islands at the second level (Makin, 1,914 people,
has no polygon) and the three island groups at the first: Gilbert (with
Banaba), Line and Phoenix, whose only inhabited island is Kanton.

Usage:
    python -m scripts.fetch_census.kiribati_census
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, write_json
from .oceania_common import (
    bind_level, check, load_units, median_from_groups, number, population, rows_of, sex_ratio,
    shares_of, summarise, transcription, unit_record, workbook,
)

OUT = "kiribati_census.json"
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
GROUPS = {"Gilbert Islands": [k for k in ISLANDS if k not in ("Teraina", "Tabuaeran",
                                                              "Kiritimati", "Kanton")] + ["Makin"],
          "Line Islands": ["Teraina", "Tabuaeran", "Kiritimati"],
          "Phoenix Islands": ["Kanton"]}
# The summary sheet's own spellings, for the cross-check.
SUMMARY_NAMES = {"North Tarawa": "NTarawa", "South Tarawa": "STarawa", "Teraina": "Teeraina"}

REPORT = f"{OFFICE}, 2020 Population and Housing Census General Report"
# The island as the map draws it (or, for Makin, names it) -> its line in the
# General Report's tables.
REPORT_ROWS = {**{i: i for i in ISLANDS}, "Makin": "Makin", "Tarawa Ieta": "North Tarawa",
               "Tarawa Teinainano": "South Tarawa", "Tabiteuea North": "North Tabiteuea",
               "Tabiteuea South": "South Tabiteuea", "Teraina": "Teeraina"}
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
    medians: dict[str, float] = {}
    for label, row in a10.items():
        broad = row["0-14"] + row["15-49"] + row["50-64"] + row["65+"]
        check(broad == row["Total"] and row["0-4"] <= row["0-14"],
              f"kiribati_census: Table A-10a's age groups for {label} make {broad:,.0f}, not "
              f"{row['Total']:,.0f}")
        check(g2[label]["Total"] == row["Total"] == a3[label]["Total"],
              f"kiribati_census: {label} is {g2[label]['Total']:,.0f} in Table G-2, "
              f"{row['Total']:,.0f} in A-10a and {a3[label]['Total']:,.0f} in A-3b")
        # Fewer than half under 15 puts the median at 15 or over, and the other way round.
        if (row["0-14"] < row["Total"] / 2) == (row["Median"] >= 15):
            medians[label] = row["Median"]
    for island, label in REPORT_ROWS.items():
        check(g2[label]["Total"] == counts[island],
              f"kiribati_census: {island} is {counts[island]:,} in the Island Profile and "
              f"{g2[label]['Total']:,.0f} in Table G-2")
    contradicted = sorted(set(a10) - set(medians))
    log(f"  General Report: Tables G-2, A-10a, A-3b for {len(REPORT_ROWS)} islands, adding up "
        f"and agreeing with the Island Profile; medians its own age groups contradict: "
        f"{contradicted}")
    return {"g2": g2, "a10": a10, "a3": a3, "medians": medians}


MEDIAN_CONTRADICTED = (
    "The General Report prints {island}'s median age as {median} (Table A-10a), and the same "
    "table counts {young:,.0f} of its {people:,.0f} people under 15 -- {side} half -- which "
    "puts the median {where} 15; the printed figure is not used.")


def report_fields(labels: list[str], report: dict[str, Any], where: str) -> dict[str, Any]:
    """Sex and ethnicity of the islands named, added up, and one island's median."""
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
    if len(labels) == 1:
        label, row = labels[0], report["a10"][labels[0]]
        if label in report["medians"]:
            fields["median_age"] = measure(row["Median"], unit="years", year=YEAR,
                                           source=f"{REPORT} (Table A-10a)")
            fields["median_age_note"] = (f"Median age of the people of {where} as the 2020 "
                                         f"census's General Report prints it (Table A-10a).")
        else:
            young = row["0-14"] < row["Total"] / 2
            fields["median_age"] = gap(NOT_AVAILABLE, MEDIAN_CONTRADICTED.format(
                island=where, median=row["Median"], young=row["0-14"], people=row["Total"],
                side="fewer than" if young else "more than",
                where="at or over" if young else "under"))
    return fields


# ---------------------------------------------------------------------------
# SPC's age and sex table
# ---------------------------------------------------------------------------

def age_table(rows: list[list[Any]], name_col: str) -> dict[str, dict[str, Any]]:
    """{unit: {male, female, groups}} from one sheet of SPC's island table."""
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
        groups, males, females = [], 0, 0
        for low, high in closed:
            m = int(number(cells[index[f"M_{low:02d}_{high:02d}"]]) or 0)
            f = int(number(cells[index[f"F_{low:02d}_{high:02d}"]]) or 0)
            groups.append((low, high, m + f))
            males, females = males + m, females + f
        m = int(number(cells[index[opens["M"]]]) or 0)
        f = int(number(cells[index[opens["F"]]]) or 0)
        groups.append((top[0], None, m + f))
        males, females = males + m, females + f
        out[name] = {"male": males, "female": females, "groups": groups,
                     "printed": (number(cells[index["M_TL"]]), number(cells[index["F_TL"]]))}
    return out


def checked(unit: dict[str, Any], name: str) -> dict[str, Any]:
    """A row whose age groups make the totals it prints, or the run stops."""
    printed = unit["printed"]
    check(printed == (unit["male"], unit["female"]),
          f"kiribati_census: {name}'s groups make {unit['male']} males and {unit['female']} "
          f"females; its totals say {printed}")
    return unit


def minus(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {"male": a["male"] - b["male"], "female": a["female"] - b["female"],
            "groups": [(lo, hi, n - m) for (lo, hi, n), (_, _, m) in zip(a["groups"], b["groups"])]}


def read_cod(book) -> dict[str, dict[str, Any]]:
    """SPC's figures for the drawn islands and the three island groups."""
    groups = age_table(rows_of(book, "kir_admpop_adm1_2020"), "ADM1_EN")
    islands = age_table(rows_of(book, "kir_admpop_adm2_2020"), "ADM2_EN")
    villages = age_table(rows_of(book, "kir_admpop_adm3_2020"), "ADM3_EN")
    out: dict[str, dict[str, Any]] = {}
    for island, (_, row) in ISLANDS.items():
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
    return out


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

RELIGION_GAP = (
    "The 2020 census asked religion, and the Statistics Office publishes it for the country "
    "(General Report, Table G-3: 58.9% Catholic, 21.2% Kiribati Uniting Church, 8.4% "
    "Kiribati Protestant Church) and by island only as a map in its Census Atlas (Map 18), "
    "which prints no figures.")
LANGUAGE_GAP = (
    "Neither the 2020 census's General Report nor its Census Atlas tabulates language; the "
    "only language item they report is whether people can read and write, in any language.")
AGE_NOTE = (
    "{what}, from the Pacific Community's tabulation of the 2020 census by island, five-year "
    "age group and sex (UNFPA and OCHA's COD-PS for Kiribati), which counts {people:,} "
    "people here against the census's final {final:,}{extra}. The Statistics Office's own "
    "General Report prints medians by island and division, not by island group.")
NO_AGE = (
    "Kanton's {people} people are not in the Pacific Community's tabulation of the 2020 census "
    "by age and sex; the Statistics Office's General Report gives Kanton's own (Tables G-2 "
    "and A-10a), which the census file carries.")


def age_fields(unit: str, cod: dict[str, Any], final: int) -> dict[str, Any]:
    figures = cod.get(unit)
    if not figures or not figures["male"] + figures["female"]:
        why = NO_AGE.format(people=final)
        return {"median_age": gap(NOT_AVAILABLE, why), "sex_ratio": gap(NOT_AVAILABLE, why)}
    people = figures["male"] + figures["female"]
    extra = (" -- its village 'BetioEast'" if unit == "Betio" else
             " -- South Tarawa without Betio" if unit == "Tarawa Teinainano" else "")
    source = f"{COD}, {YEAR}"
    return {
        "median_age": measure(median_from_groups(figures["groups"]), unit="years", year=YEAR,
                              source=source),
        "median_age_note": AGE_NOTE.format(what="Interpolated within the five-year age group "
                                                "that holds the middle person", people=people,
                                           final=final, extra=extra),
        "sex_ratio": measure(sex_ratio(figures["male"], figures["female"]),
                             unit="males_per_100_females", year=YEAR, source=source),
        "sex_ratio_note": AGE_NOTE.format(what="Males per 100 females", people=people,
                                          final=final, extra=extra),
    }


def census_fields(final: int, note: str) -> dict[str, Any]:
    return {
        "population": population(final, YEAR, PROFILE),
        "population_note": note,
        "religion": gap(NOT_AVAILABLE, RELIGION_GAP),
        "language": gap(NOT_AVAILABLE, LANGUAGE_GAP),
    }


SOURCES = [
    {"field": "population", "name": PROFILE, "url": PROFILE_URL, "year": YEAR,
     "license": LICENCE},
    {"field": "median_age/sex_ratio/ethnicity", "name": REPORT, "url": REPORT_URL,
     "year": YEAR, "license": LICENCE},
    {"field": "religion/language (why empty)", "name": f"{REPORT}; Kiribati Census Atlas",
     "url": ATLAS_URL, "year": YEAR, "license": LICENCE},
]
AGE_SOURCES = [{"field": "median_age/sex_ratio", "name": COD, "url": COD_PAGE, "year": YEAR,
                "license": "Creative Commons Attribution for Intergovernmental Organisations"}]


def build(counts: dict[str, int], cod: dict[str, dict[str, Any]], report: dict[str, Any],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    group_units = bind_level({g: (g, "") for g in GROUPS}, admin1, {})
    parents = {u["id"]: u["name"] for u in admin1}
    island_units = bind_level({i: (i, "") for i in ISLANDS}, admin2, parents)
    census, ages = [], []
    for group, unit in group_units.items():
        final = sum(counts[i] for i in GROUPS[group])
        note = (f"The census counts of its islands added up: {', '.join(GROUPS[group])}."
                if len(GROUPS[group]) > 1 else "Kanton, the group's one inhabited island.")
        labels = [REPORT_ROWS[i] for i in GROUPS[group]]
        census.append(unit_record("KIR", group, unit["name"], unit, "admin1", None, SOURCES,
                                  **census_fields(final, note),
                                  **report_fields(labels, report, group)))
        ages.append(unit_record("KIR", group, unit["name"], unit, "admin1", None, AGE_SOURCES,
                                **age_fields(group, cod, final)))
    for island, unit in island_units.items():
        note = "The 2020 census count (Island Profile tables)."
        census.append(unit_record("KIR", island, unit["name"], unit, "admin2", None, SOURCES,
                                  **census_fields(counts[island], note),
                                  **report_fields([REPORT_ROWS[island]], report, island)))
        ages.append(unit_record("KIR", island, unit["name"], unit, "admin2", None, AGE_SOURCES,
                                **age_fields(island, cod, counts[island])))
    log(f"  no polygon: Makin ({counts['Makin']:,} people), counted in the Gilbert Islands")
    return census, ages


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
    cod = read_cod(cod_book())
    census, ages = build(counts, cod, report, load_units("KIR", "admin1"),
                         load_units("KIR", "admin2"))
    log("  " + summarise(census + ages))
    write_json(PROCESSED / OUT, census)
    write_json(PROCESSED / OUT_AGES, ages)
    log(f"  wrote {len(census)} + {len(ages)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
