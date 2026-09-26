#!/usr/bin/env python3
"""Belize: the 2022 census by district, from SIB's General Characteristics workbook.

The Statistical Institute of Belize publishes the 2022 Population and Housing
Census's first tables as one workbook, *Census2022_GeneralCharacteristics*:

* Table 5, population by major administrative area and sex (2010 and 2022);
* Table 6, population by district and five-year age group;
* Table 7, the population aged four and over by languages spoken and district;
* Table 8, population by ethnicity, district and sex;
* Table 9, population by religion, district and sex.

SIB's figures are weighted -- the census was adjusted for households it could
not reach -- so every cell is a decimal ("45310.2"), and a cell under ten is
printed "<10" rather than as a number. What this writes, for the six
districts: the population and sex ratio (Table 5), the median age,
interpolated within the five-year group holding the middle person (Table 6),
ethnicity (Table 8), religion (Table 9), and languages spoken (Table 7).

Languages spoken is a question with more than one answer per person, and SIB
publishes it that way: a row for everyone who speaks English, another for
everyone who speaks Spanish, and so on. The shares are of the district's
whole population and do not sum to 100; ``language_basis`` and the note say
so. A child under four was not asked.

Checks, each of which stops the run: every district's ethnic groups and its
religions make its population, within the cells SIB suppressed; its age
groups make it too; its sexes make it; the districts make the national
397,483; and the national rows of each table make the national column.

The 31 electoral divisions the map draws below the districts are not a
geography SIB tabulates, and every one says so.

Usage:
    python -m scripts.fetch_census.belize_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, write_json
from .binding import fold
from .cod_ps_age import grouped_median

OUT = PROCESSED / "belize_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2022
URL = "https://sib.org.bz/wp-content/uploads/Census2022_GeneralCharacteristics.xlsx"
PAGE = "https://sib.org.bz/census/2022-census/"
SOURCE = ("Statistical Institute of Belize, 2022 Population and Housing Census: General "
          "Characteristics tables")
# SIB answers 406 Not Acceptable to a User-Agent ending "python-urllib"; this is
# the project's own name, as probe_redatam.py sends it.
HEADERS = {"User-Agent": "DemographicMap/1.0 (+https://github.com/advaitsridhar/DemographicMap)",
           "Accept": "*/*"}
NATIONAL = 397_483
DISTRICTS = ("Corozal", "Orange Walk", "Belize", "Cayo", "Stann Creek", "Toledo")
SUPPRESSED = "<10"

ETHNICITY = {
    "Mestizo/Hispanic/Latino": "Mestizo", "Creole": "Creole", "Maya Ketchi": "Maya Ketchi",
    "Garifuna": "Garifuna", "Mennonite": "Mennonite", "Maya Mopan": "Maya Mopan",
    "East Indian": "East Indian", "Chinese": "Chinese", "Caucasian/White": "White",
    "Maya Yucatec": "Maya Yucatec", "Indian": "Indian", "Other": "Other",
    "Don't Know/Not Stated": "Not stated",
}
RELIGION = {
    "Roman Catholic": "Roman Catholic", "Pentecostal": "Pentecostal",
    "Seventh Day Adventist": "Seventh-day Adventist", "Anglican": "Anglican",
    "Mennonite": "Mennonite", "Baptist": "Baptist", "Methodist": "Methodist",
    "Nazarene": "Church of the Nazarene", "Jehovah's Witness": "Jehovah's Witnesses",
    "Other": "Other religion", "None": "No religion",
    "Don't Know/Not Stated": "Not stated",
}
LANGUAGE = {
    "Speaks English": "English", "Speaks Spanish": "Spanish", "Speaks Creole": "Belizean Creole",
    "Speaks Maya Ketchi": "Q'eqchi'", "Speaks Maya Mopan": "Mopan Maya",
    "Speaks German": "German", "Speaks Garifuna": "Garifuna", "Speaks Other": "Other language",
    "Speaks Maya Yucatec": "Yucatec Maya", "Speaks Chinese": "Chinese",
    "Speaks Hindi": "Hindi", "Cannot Speak": None,
}
LANGUAGE_BASIS = "languages spoken, more than one per person; share of the whole population"


def cell(value: Any) -> float | None:
    """A weighted count, 0 for an empty cell, None for one SIB suppressed."""
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == SUPPRESSED:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        raise SystemExit(f"belize_census: {value!r} is not a count")


def text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def district_columns(rows: list[list[Any]]) -> dict[str, int]:
    """{district or "Total": the column of its Total} from a by-district table's two header rows.

    The first header row names each district over three columns (Total, Male,
    Female); the second says which is which.
    """
    top = next(i for i, r in enumerate(rows) if any(text(c) == "Corozal" for c in r))
    names, kinds = rows[top], rows[top + 1]
    out, current = {}, None
    for i, value in enumerate(names):
        if text(value):
            current = text(value)
        if current and text(kinds[i] if i < len(kinds) else "") == "Total" and current not in out:
            out[current] = i
    wanted = {"Total", *DISTRICTS}
    if set(out) != wanted:
        raise SystemExit(f"belize_census: the table's districts are {sorted(out)}")
    return out


def by_district(rows: list[list[Any]], labels: dict[str, str | None],
                what: str) -> tuple[dict[str, dict[str, float]], dict[str, int], dict[str, float]]:
    """({district: {label: count}}, {district: suppressed cells}, {district: printed total}).

    A row whose first cell is not in ``labels`` stops the run, so a category
    SIB adds is named rather than dropped. A label mapped to None is read and
    left out of the composition (it is a row the question's own universe
    holds but that names no language).
    """
    cols = district_columns(rows)
    counts = {d: {} for d in cols}
    hidden = {d: 0 for d in cols}
    totals: dict[str, float] = {}
    started = False
    for row in rows:
        label = text(row[1] if len(row) > 1 else "")
        if label in ("Ethnicity", "Religion", "Language"):
            started = True
            continue
        if not started or not label or label.startswith("Source"):
            continue
        if label == "Total":
            totals = {d: cell(row[i]) for d, i in cols.items()}
            continue
        if label not in labels:
            raise SystemExit(f"belize_census: {what} row {label!r} is not one this reads")
        for d, i in cols.items():
            value = cell(row[i] if i < len(row) else None)
            if value is None:
                hidden[d] += 1
                value = 0.0
            if labels[label] is not None:
                counts[d][labels[label]] = counts[d].get(labels[label], 0.0) + value
    return counts, hidden, totals


def check_partition(counts: dict[str, dict[str, float]], hidden: dict[str, int],
                    population: dict[str, float], what: str) -> None:
    """Every district's categories make its population, within what SIB hid."""
    for district, groups in counts.items():
        made, whole = sum(groups.values()), population[district]
        slack = 10 * hidden[district] + 1
        if abs(made - whole) > slack:
            raise SystemExit(f"belize_census: {district}'s {what} make {made:,.1f} of "
                             f"{whole:,.1f}")


def sexes(rows: list[list[Any]]) -> dict[str, tuple[float, float, float]]:
    """{area: (total, males, females)} for 2022 from Table 5."""
    head = next(i for i, r in enumerate(rows) if any("Census 2022" in text(c) for c in r))
    start = next(j for j, c in enumerate(rows[head]) if "Census 2022" in text(c))
    out = {}
    for row in rows[head + 2:]:
        name = text(row[1] if len(row) > 1 else "")
        if not name or name.startswith("Source"):
            continue
        total, men, women = (cell(row[start + k]) for k in range(3))
        if abs(men + women - total) > 1:
            raise SystemExit(f"belize_census: {name}'s sexes make {men + women:,.1f} of {total:,.1f}")
        out[name] = (total, men, women)
    return out


AGE = re.compile(r"^(\d+)\s*-\s*(\d+)$")


def ages(rows: list[list[Any]]) -> dict[str, list[tuple[int, int | None, float]]]:
    """{district: [(low, high, people)]} for 2022 from Table 6, checked against its Total."""
    head = next(i for i, r in enumerate(rows) if any("Census" in text(c) and "2022" in text(c)
                                                     for c in r))
    col = next(j for j, c in enumerate(rows[head]) if "2022" in text(c))
    out: dict[str, list[tuple[int, int | None, float]]] = {}
    totals: dict[str, float] = {}
    current = None
    for row in rows[head + 1:]:
        name, group = text(row[1] if len(row) > 1 else ""), text(row[2] if len(row) > 2 else "")
        if name.startswith("Source"):
            break
        if name:
            current = name
            out[current] = []
        if not current or not group:
            continue
        value = cell(row[col])
        if group == "Total":
            totals[current] = value
        elif group == "Less than 1":
            out[current].append((0, 0, value))
        elif group.endswith("+"):
            out[current].append((int(group[:-1]), None, value))
        elif AGE.match(group):
            low, high = AGE.match(group).groups()
            out[current].append((int(low), int(high), value))
        else:
            raise SystemExit(f"belize_census: age group {group!r}")
    for district, groups in out.items():
        if abs(sum(g[2] for g in groups) - totals[district]) > 1:
            raise SystemExit(f"belize_census: {district}'s age groups make "
                             f"{sum(g[2] for g in groups):,.1f} of {totals[district]:,.1f}")
    return out


def sheet(book, name: str) -> list[list[Any]]:
    return [list(r) for r in book[name].iter_rows(values_only=True)]


def read() -> dict[str, dict[str, Any]]:
    import openpyxl
    blob = http_get(URL, binary=True, cache=False, headers=HEADERS)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    people = sexes(sheet(book, "Sex_Ratio"))
    if round(people["National"][0]) != NATIONAL:
        raise SystemExit(f"belize_census: the national population is {people['National'][0]:,.1f}")
    if abs(sum(people[d][0] for d in DISTRICTS) - NATIONAL) > 1:
        raise SystemExit("belize_census: the districts do not make the national population")
    groups = ages(sheet(book, "Age_Groups"))
    ethnicity, e_hidden, e_totals = by_district(sheet(book, "Ethnicity_by_District"), ETHNICITY,
                                                "ethnicity")
    religion, r_hidden, r_totals = by_district(sheet(book, "Religion_by_District"), RELIGION,
                                               "religion")
    languages, _l_hidden, _ = by_district(sheet(book, "Languages_Spoken"), LANGUAGE, "language")
    population = {d: people[d][0] for d in DISTRICTS} | {"Total": people["National"][0]}
    for totals, what in ((e_totals, "ethnicity"), (r_totals, "religion")):
        for d, value in totals.items():
            if abs(value - population[d]) > 1:
                raise SystemExit(f"belize_census: the {what} table's {d} is {value:,.1f}, "
                                 f"Table 5's {population[d]:,.1f}")
    check_partition(ethnicity, e_hidden, population, "ethnic groups")
    check_partition(religion, r_hidden, population, "religions")
    out = {}
    for d in DISTRICTS:
        if abs(sum(g[2] for g in groups[d]) - population[d]) > 1:
            raise SystemExit(f"belize_census: {d}'s age groups do not make its population")
        out[d] = {"population": population[d], "men": people[d][1], "women": people[d][2],
                  "median": grouped_median(groups[d]), "ethnicity": ethnicity[d],
                  "ethnicity_hidden": e_hidden[d], "religion": religion[d],
                  "religion_hidden": r_hidden[d], "languages": languages[d]}
    log(f"  {len(out)} districts making {sum(population[d] for d in DISTRICTS):,.0f}; ethnicity, "
        "religion, ages and sexes each make every district")
    return out


def whole(counts: dict[str, float]) -> dict[str, int]:
    """Weighted counts as the whole people shares() counts."""
    return {k: int(round(v)) for k, v in counts.items() if round(v) > 0}


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    districts = read()
    admin1 = json.loads((SITE / "admin1" / "BLZ.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "BLZ.units.json").read_text())
    shapes = {fold(u["name"]): u for u in admin1}
    cite = [{"field": f, "name": SOURCE, "url": URL, "year": YEAR}
            for f in ("population", "median_age/sex_ratio", "ethnicity", "religion", "language")]
    records = []
    for name, d in districts.items():
        shape = shapes.get(fold(name))
        if shape is None:
            raise SystemExit(f"belize_census: district {name!r} has no polygon")
        pop = round(d["population"])
        records.append(record(
            f"BLZ-SIB-{fold(name)}", shape["name"], level="admin1", parent="BLZ", country="BLZ",
            match_by="shape_id", shape_id=shape["id"],
            population=measure(pop, year=YEAR, source=SOURCE),
            population_note="SIB's weighted 2022 census count for the district (Table 5).",
            median_age=measure(d["median"], unit="years", year=YEAR, source=SOURCE),
            median_age_note=("Interpolated within the five-year age group holding the middle "
                             "person, from Table 6's 2022 counts by district."),
            sex_ratio=measure(round(1000 * d["men"] / d["women"]), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE),
            ethnicity=shares(whole(d["ethnicity"])), ethnicity_year=YEAR,
            ethnicity_note=("The 2022 census's ethnicity question, everyone counted (Table 8). "
                            "SIB's figures are weighted and rounded here to whole people"
                            + (f"; {d['ethnicity_hidden']} cell(s) SIB printed as under ten "
                               "are left out" if d["ethnicity_hidden"] else "") + "."),
            religion=shares(whole(d["religion"])), religion_year=YEAR,
            religion_note=("The 2022 census's religion question, everyone counted (Table 9), "
                           "SIB's own categories; \"None\" is written as No religion"
                           + (f"; {d['religion_hidden']} cell(s) SIB printed as under ten are "
                              "left out" if d["religion_hidden"] else "") + "."),
            language=shares(whole(d["languages"]), total=d["population"]), language_year=YEAR,
            language_basis=LANGUAGE_BASIS,
            language_note=("Languages spoken, asked of everyone aged four and over, who could "
                           "name several (Table 7). Each share is the part of the district's "
                           "whole population that speaks the language, so the shares sum to "
                           "more than 100; children under four are in the base and were not "
                           "asked, and people who cannot speak are not shown."),
            sources=cite))
    why = ("SIB tabulates the 2022 census by district, by urban and rural area and by city, "
           "town and village, and publishes nothing by electoral division; a village cannot be "
           "placed in a division from anything the census publishes, so the divisions carry the "
           "districts' figures and none of their own.")
    for shape in admin2:
        records.append(record(
            f"BLZ-SIB-division-{shape['id']}", shape["name"], level="admin2", parent="BLZ",
            country="BLZ", match_by="shape_id", shape_id=shape["id"],
            **{f: gap(NOT_AVAILABLE, why) for f in ("population", "median_age", "sex_ratio",
                                                    "religion", "language", "ethnicity")}))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records ({len(districts)} districts, "
        f"{len(admin2)} electoral divisions with the reason they have no figures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
