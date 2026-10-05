#!/usr/bin/env python3
"""Kiribati, 2020 census: every island's count, and its age and sex from SPC's tabulation.

**The count** is the Kiribati National Statistics Office's own: its *Island
Profile* workbook for the 2020 Population and Housing Census
(``island-profile-table-final.xlsx``) gives each of the 24 inhabited islands a
sheet whose "Population (Census)" row holds the 2015 and 2020 counts, and a
summary sheet that lists the same 24 by broad age group. Both must agree, and
they must add up to the 119,438 the census counted. Betio is its own island
there, and South Tarawa is the Teinainano Urban Council without it -- which is
how the map draws them, as "Betio" and "Tarawa Teinainano".

**Age and sex** the Office publishes by island only in its General Report, as
pictures of tables that carry no text. What can be read is the Pacific
Community's tabulation of the same census by island and five-year age group,
which UNFPA and OCHA publish as the Common Operational Dataset for Kiribati
(``cod-ps-kir``, "Baseline used: Kiribati NSO"). It counts 119,940 people, 0.4%
more than the final count, so its medians and sex ratios go to a file of their
own that the build lists as fill-only, and each says how many people it
describes. It folds Betio into South Tarawa and tabulates Betio as the
village "BetioEast", so Betio's figures are that village's and Teinainano's
are South Tarawa's without it.

**Religion, ethnicity and language** the census asked or reported, and the
records say why each is empty: religion is published for the country and
mapped by island without figures; ethnicity is tabulated by island only in
that same picture of a table; language is not tabulated at all.

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
    summarise, unit_record, workbook,
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
ETHNICITY_GAP = (
    "The 2020 census asked ethnicity, and the General Report tabulates it by island (Table "
    "A-3b) only as a picture of the table: the PDF carries no text for its figures, and no "
    "other release prints them.")
LANGUAGE_GAP = (
    "Neither the 2020 census's General Report nor its Census Atlas tabulates language; the "
    "only language item they report is whether people can read and write, in any language.")
AGE_NOTE = (
    "{what}, from the Pacific Community's tabulation of the 2020 census by island, five-year "
    "age group and sex (UNFPA and OCHA's COD-PS for Kiribati), which counts {people:,} "
    "people here against the census's final {final:,}{extra}. The Statistics Office prints "
    "island ages and sexes only as pictures of its tables.")
NO_AGE = (
    "Kanton's {people} people are not in the Pacific Community's tabulation of the 2020 census "
    "by age and sex, and the Statistics Office prints island ages and sexes only as pictures "
    "of its tables.")


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
        "ethnicity": gap(NOT_AVAILABLE, ETHNICITY_GAP),
        "language": gap(NOT_AVAILABLE, LANGUAGE_GAP),
    }


SOURCES = [
    {"field": "population", "name": PROFILE, "url": PROFILE_URL, "year": YEAR,
     "license": LICENCE},
    {"field": "religion/ethnicity/language (why empty)", "name": f"{OFFICE}, 2020 Population "
     "and Housing Census General Report; Kiribati Census Atlas", "url": REPORT_URL,
     "year": YEAR, "license": LICENCE},
]
AGE_SOURCES = [{"field": "median_age/sex_ratio", "name": COD, "url": COD_PAGE, "year": YEAR,
                "license": "Creative Commons Attribution for Intergovernmental Organisations"}]


def build(counts: dict[str, int], cod: dict[str, dict[str, Any]],
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
        census.append(unit_record("KIR", group, unit["name"], unit, "admin1", None, SOURCES,
                                  **census_fields(final, note)))
        ages.append(unit_record("KIR", group, unit["name"], unit, "admin1", None, AGE_SOURCES,
                                **age_fields(group, cod, final)))
    for island, unit in island_units.items():
        note = "The 2020 census count (Island Profile tables)."
        census.append(unit_record("KIR", island, unit["name"], unit, "admin2", None, SOURCES,
                                  **census_fields(counts[island], note)))
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
    log("kiribati_census: 2020 census counts by island; SPC's age and sex tabulation")
    counts = read_profile(workbook(PROFILE_URL))
    cod = read_cod(cod_book())
    census, ages = build(counts, cod, load_units("KIR", "admin1"), load_units("KIR", "admin2"))
    log("  " + summarise(census + ages))
    write_json(PROCESSED / OUT, census)
    write_json(PROCESSED / OUT_AGES, ages)
    log(f"  wrote {len(census)} + {len(ages)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
