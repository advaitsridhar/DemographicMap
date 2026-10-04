#!/usr/bin/env python3
"""Tonga, 2021 Census: population, age, sex, religion, ethnic origin and language at home.

Four of the Tonga Statistics Department's General Tables workbooks for the
2021 Census of Population and Housing (``tongastats.gov.to``, "Census Tables"):

* **1 - Population trends**: Table G 1 (population by sex, division and
  district, 2011, 2016 and 2021), G 5 (by five-year age group, down to the
  village) and G 6 (by single year of age and sex, by division);
* **2 - Ethnicity**: Table G 12, ethnic origin by division, district and
  village -- "Ethinicity were multiple selected", the table's own note, so a
  person may be counted under two origins and the shares, each of the total
  population, sum to a little over 100;
* **4 - Religion**: Table G 19, religious affiliation by division and
  district, which excludes visitors and non-residents;
* **10 - Literacy**: Table G 50 (Table G 48 in the printed Volume 1),
  language used at home by division -- the answers to the individual
  questionnaire's ID7.7, "What language does this person speak at home?":
  Tongan language only, Tongan and other language(s), Tongan language is
  not used at home -- for the 89,254 people aged five and over in private
  households.

**Median age** is interpolated within the single year for the five divisions
(G 6) and within the five-year group for the districts (G 5), the finest each
level is published at.

**What the map draws.** Its 21 districts are 21 of the census's 23: Lulunga
(Ha'apai) and Niuatoputapu (Ongo Niua) have no polygon. Its first-level
"Niuas" polygon is Niuafo'ou alone -- the boundary file leaves Niuatoputapu
out -- so that polygon takes Niuafo'ou's own figures, as its district polygon
does, and says so. "'Eua Prope" is the census's 'Eua Motu'a ('Eua Proper).

**Language** is published for the five divisions only. A district's field
says so; so does the Niuas polygon's, because the division's figure is
mostly Niuatoputapu's people and the polygon is Niuafo'ou.

**Checks**, each refusing the run: every row's males and females make its
total; the districts make their division and the divisions make Tonga
(100,179); each age distribution makes its row's total; each religion row's
denominations make its total; each language row's three answers make its
total and the divisions make Tonga's 89,254; every drawn unit is bound once.

Usage:
    python -m scripts.fetch_census.tonga_census
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import PROCESSED, gap, log, measure, write_json, NOT_AVAILABLE
from .binding import fold
from .oceania_common import (
    bind_level, check, load_units, median_from_groups, median_from_single_years,
    number, population, rows_of, sex_ratio, shares_of, summarise,
    unit_record, workbook,
)

YEAR = 2021
OUT = "tonga_census.json"
OFFICE = "Tonga Statistics Department"
SOURCE = f"{OFFICE}, 2021 Census of Population and Housing, General Tables"
BASE = "https://tongastats.gov.to/download/266/general-tables"
URLS = {
    "population": f"{BASE}/8089/1-population-trends.xlsx",
    "ethnicity": f"{BASE}/7660/2-ethnicity.xlsx",
    "religion": f"{BASE}/7664/4-religion.xlsx",
    "literacy": f"{BASE}/7665/10-literacy.xlsx",
}
PAGE = "https://tongastats.gov.to/census-2/population-census-3/census-tables/"
NATIONAL = 100_179

DIVISIONS = ("Tongatapu", "Vava'u", "Ha'apai", "'Eua", "Ongo Niua")
# The census's division name -> the map's first-level label.
DIVISION_ON_MAP = {"Tongatapu": "Tongatapu", "Vava'u": "Vava'u", "Ha'apai": "Ha'apai",
                   "'Eua": "'Eua", "Ongo Niua": "Niuas"}
# Districts the boundary file does not draw: counted in their division only.
UNDRAWN = {"Lulunga", "Niuatoputapu"}
# The census's spelling -> the boundary file's, where they differ by more than
# accents and apostrophes. 'Eua Motu'a is 'Eua Proper.
ALIASES = {"Eua Motu'a": "'Eua Prope", "'Eua Motu'a": "'Eua Prope"}

# G 19's abbreviations, as its own notes spell them out.
RELIGIONS = {
    "FWC": "Free Wesleyan Church", "RC": "Roman Catholic",
    "LDS": "Church of Jesus Christ of Latter-day Saints", "FCOT": "Free Church of Tonga",
    "COT": "Church of Tonga", "AOG": "Assembly of God",
    "TOK": "Tokaikolo Christian Fellowship", "CCOT": "Constitutional Church of Tonga",
    "GOS": "Gospel Church", "AGC": "Anglican", "SDA": "Seventh-day Adventist",
    "MF": "Mo'ui Fo'ou 'ia Kalaisi", "TSA": "Salvation Army",
    "JW": "Jehovah's Witnesses", "OP": "Other Pentecostal", "BF": "Baha'i",
    "BUDH": "Buddhism", "ISL": "Islam", "HND": "Hinduism", "NO REL": "No religion",
    "REF": "Not stated", "OTHER": "Other religion",
}
# G 50's three answers, by the start of the table's own headings. "Tongan
# language is not used at home" is every other language, so it is written as
# "Other languages": a label naming Tongan would be filed under Tongan.
LANGUAGES = (("tongan language only", "Tongan only"),
             ("tongan and other language", "Tongan and other languages"),
             ("tongan language is not used", "Other languages"))
AGED_FIVE_PLUS = 89_254
ETHNIC = {"Tongan": "Tongan", "European": "European", "Fijian": "Fijian",
          "Samoan": "Samoan", "Indian": "Indian", "Chinese": "Chinese",
          "Other Pacific Islander": "Other Pacific Islander", "Other Asian": "Other Asian",
          "Other": "Other"}


def text(cell: Any) -> str:
    return " ".join(str(cell or "").split())


# ---------------------------------------------------------------------------
# G 1: population by sex, division and district
# ---------------------------------------------------------------------------

def read_population(rows: list[list[Any]]) -> tuple[dict[str, dict[str, float]],
                                                     dict[str, list[str]]]:
    """({division or district: {total, male, female}}, {division: [districts]})."""
    out: dict[str, dict[str, float]] = {}
    tree: dict[str, list[str]] = {}
    current = None
    for row in rows[3:]:
        name = text(row[0])
        total, male, female = (number(c) for c in row[1:4])
        if not name or total is None:
            continue
        if name.upper() == "TONGA":
            out["TONGA"] = {"total": total, "male": male, "female": female}
            continue
        if name in ("Urban", "Rural") or name.startswith("Greater"):
            break
        entry = {"total": total, "male": male, "female": female}
        check(male is not None and female is not None and male + female == total,
              f"tonga_census: G 1 {name}: males and females do not make {total}")
        if name in DIVISIONS or fold(name) in {fold(d) for d in DIVISIONS}:
            current = next(d for d in DIVISIONS if fold(d) == fold(name))
            tree[current] = []
            out[current] = entry
        else:
            check(current is not None, f"tonga_census: G 1 district {name} before any division")
            tree[current].append(name)
            out[name] = entry
    check(out.get("TONGA", {}).get("total") == NATIONAL,
          f"tonga_census: G 1 reads Tonga {out.get('TONGA')}, published {NATIONAL:,}")
    check(sum(out[d]["total"] for d in DIVISIONS) == NATIONAL,
          "tonga_census: the divisions do not make Tonga")
    for division, districts in tree.items():
        made = sum(out[d]["total"] for d in districts)
        check(made == out[division]["total"],
              f"tonga_census: {division}'s districts make {made}, not {out[division]['total']}")
    return out, tree


# ---------------------------------------------------------------------------
# G 6: single years by division; G 5: five-year groups by district
# ---------------------------------------------------------------------------

def age_of(label: str) -> tuple[int, bool] | None:
    """('<1' -> 0), ('37' -> 37), ('99+' -> 99, open)."""
    label = label.strip()
    if label.startswith("<"):
        return 0, False
    if label.endswith("+") and label[:-1].isdigit():
        return int(label[:-1]), True
    if label.isdigit():
        return int(label), False
    return None


def division_medians(rows: list[list[Any]], people: dict[str, dict[str, float]]
                     ) -> dict[str, float]:
    """Median age of each division from G 6's single years (its Total columns)."""
    header = [text(c) for c in rows[1]]
    columns = {}
    for i, cell in enumerate(header):
        for division in DIVISIONS + ("TONGA",):
            if fold(cell) == fold(division) or (division == "'Eua" and fold(cell) == "eua"):
                columns[division] = i
    check(set(columns) >= set(DIVISIONS) | {"TONGA"},
          f"tonga_census: G 6 header carries {sorted(columns)}")
    ages: dict[str, dict[int, float]] = {d: {} for d in columns}
    opened = False
    for row in rows[3:]:
        label = text(row[0])
        if label.lower() == "total":
            continue
        parsed = age_of(label)
        if parsed is None:
            continue
        age, is_open = parsed
        for division, i in columns.items():
            ages[division][age] = number(row[i]) or 0.0
        opened = opened or is_open
    check(opened, "tonga_census: G 6 has no open-ended last age")
    out = {}
    for division, dist in ages.items():
        expected = people["TONGA" if division == "TONGA" else division]["total"]
        check(sum(dist.values()) == expected,
              f"tonga_census: G 6 {division}'s ages make {sum(dist.values())}, not {expected}")
        out[division] = median_from_single_years(dist)
    return out


GROUPS = [(0, 4), (5, 9), (10, 14), (15, 19), (20, 24), (25, 29), (30, 34), (35, 39),
          (40, 44), (45, 49), (50, 54), (55, 59), (60, 64), (65, 69), (70, 74), (75, None)]


def find_rows(rows: list[list[Any]], names: list[str], fits) -> dict[str, list[Any]]:
    """Each name's row in a table that lists districts above their villages.

    The first row after the last match whose name is the district's and which
    ``fits`` the district (its total, or its count of origins, against the
    district's people): a village sharing its district's name follows the
    district row, and its total is smaller.
    """
    out: dict[str, list[Any]] = {}
    start = 0
    for name in names:
        for i in range(start, len(rows)):
            row = rows[i]
            if fold(text(row[0])) == fold(name) and fits(name, row):
                out[name] = row
                start = i + 1
                break
        else:
            raise SystemExit(f"tonga_census: no row for {name}")
    return out


def district_medians(rows: list[list[Any]], districts: list[str],
                     people: dict[str, dict[str, float]]) -> dict[str, float]:
    header = [text(c) for c in rows[1]]
    check(header[1].lower() == "total" and header[2].startswith("0-4")
          and header[17].startswith("75"), f"tonga_census: G 5 header is {header[:18]}")
    found = find_rows(rows[3:], districts,
                      lambda name, row: number(row[1]) == people[name]["total"])
    out = {}
    for name, row in found.items():
        counts = [number(c) or 0.0 for c in row[2:18]]
        check(sum(counts) == number(row[1]),
              f"tonga_census: G 5 {name}'s age groups make {sum(counts)}, not {row[1]}")
        out[name] = median_from_groups([(lo, hi, n) for (lo, hi), n in zip(GROUPS, counts)])
    return out


# ---------------------------------------------------------------------------
# G 19: religion; G 12: ethnic origin
# ---------------------------------------------------------------------------

def read_religion(rows: list[list[Any]], names: list[str]) -> dict[str, dict[str, float]]:
    header = [text(c).upper() for c in rows[1]]
    check(header[1] == "TOTAL", f"tonga_census: G 19 header is {header[:3]}")
    codes = header[2:]
    unknown = [c for c in codes if c and c not in RELIGIONS]
    check(not unknown, f"tonga_census: G 19 abbreviations this reader does not know: {unknown}")
    out = {}
    wanted = {fold(n): n for n in names}
    for row in rows[2:]:
        key = wanted.get(fold(text(row[0])))
        if key is None or key in out:
            continue
        total = number(row[1])
        counts: dict[str, float] = {}
        for code, cell in zip(codes, row[2:]):
            if code:
                label = RELIGIONS[code]
                counts[label] = counts.get(label, 0.0) + (number(cell) or 0.0)
        check(total is not None and sum(counts.values()) == total,
              f"tonga_census: G 19 {key}: denominations make {sum(counts.values())}, not {total}")
        out[key] = {"total": total, "counts": counts}
    missing = [n for n in names if n not in out]
    check(not missing, f"tonga_census: G 19 has no row for {missing}")
    return out


def read_ethnicity(rows: list[list[Any]], divisions: list[str], districts: list[str],
                   people: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    header = [text(c) for c in rows[2]]
    labels = []
    for cell in header[1:]:
        if not cell:
            continue
        check(cell in ETHNIC, f"tonga_census: G 12 origin this reader does not know: {cell!r}")
        labels.append(ETHNIC[cell])

    def counts(row: list[Any]) -> dict[str, float] | None:
        values = [number(c) for c in row[1:1 + len(labels)]]
        return None if any(v is None for v in values) else dict(zip(labels, values))

    def fits(name: str, row: list[Any]) -> bool:
        # Multiple selection is rare: about one origin for each person counted
        # (the table may leave out a few visitors), and not many more.
        found, persons = counts(row), people[name]["total"]
        return found is not None and 0.97 * persons <= sum(found.values()) <= 1.1 * persons + 5

    body = rows[3:]
    out = {}
    for division in divisions:
        row = next((r for r in body if fold(text(r[0])) == fold(division)), None)
        check(row is not None and counts(row) is not None,
              f"tonga_census: G 12 has no row for {division}")
        out[division] = counts(row)
    for name, row in find_rows(body, districts, fits).items():
        out[name] = counts(row)
    for name, found in out.items():
        made, persons = sum(found.values()), people[name]["total"]
        check(0.97 * persons <= made <= 1.1 * persons + 5,
              f"tonga_census: G 12 {name}: {made:,.0f} origins for {persons:,.0f} people")
    return out


def read_language(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """{division or "TONGA": {total, counts}} from G 50, language used at home."""
    head = next((i for i, row in enumerate(rows[:8])
                 if any(text(c).lower().startswith(LANGUAGES[0][0]) for c in row)), None)
    check(head is not None, "tonga_census: G 50 has no 'Tongan language only' heading")
    starts = {}
    for i, cell in enumerate(rows[head]):
        for prefix, label in LANGUAGES:
            if text(cell).lower().startswith(prefix):
                starts[label] = i
    check(len(starts) == len(LANGUAGES), f"tonga_census: G 50 headings give {sorted(starts)}")
    wanted = {fold(d): d for d in DIVISIONS + ("TONGA",)}
    out: dict[str, dict[str, Any]] = {}
    for row in rows[head + 1:]:
        key = wanted.get(fold(text(row[0])))
        if key is None or key in out:
            continue
        total, male, female = (number(c) for c in row[1:4])
        counts = {label: number(row[i]) or 0.0 for label, i in starts.items()}
        check(total is not None and sum(counts.values()) == total,
              f"tonga_census: G 50 {key}: the answers make {sum(counts.values())}, not {total}")
        check(male is not None and female is not None and male + female == total,
              f"tonga_census: G 50 {key}: males and females do not make {total}")
        for label, i in starts.items():
            parts = [number(c) or 0.0 for c in row[i + 1:i + 3]]
            check(sum(parts) == counts[label],
                  f"tonga_census: G 50 {key}: {label} by sex does not make {counts[label]}")
        out[key] = {"total": total, "counts": counts}
    missing = [d for d in DIVISIONS + ("TONGA",) if d not in out]
    check(not missing, f"tonga_census: G 50 has no row for {missing}")
    check(out["TONGA"]["total"] == AGED_FIVE_PLUS,
          f"tonga_census: G 50 reads {out['TONGA']['total']:,.0f} people aged 5+, "
          f"published {AGED_FIVE_PLUS:,}")
    check(sum(out[d]["total"] for d in DIVISIONS) == AGED_FIVE_PLUS,
          "tonga_census: G 50's divisions do not make Tonga")
    return out


LANGUAGE_NOTE = (
    "Language used at home, 2021 Census (General Table G 50; Table G 48 in Volume 1), "
    "people aged five and over in private households, answering 'What language does this "
    "person speak at home?' (question ID7.7): Tongan language only, Tongan and other "
    "language(s), or Tongan language is not used at home -- written here as 'Other "
    "languages'.")
DISTRICT_LANGUAGE = gap(NOT_AVAILABLE, (
    "The 2021 Census asks the language used at home (question ID7.7) and tabulates it by "
    "division only (General Table G 50; Volume 1, Table G 48, 'by age, sex and division'); "
    "no table gives it for a district."))


def niuas_language(language: dict[str, dict[str, Any]], people: dict[str, dict[str, float]]
                   ) -> dict[str, Any]:
    return gap(NOT_AVAILABLE, (
        "The census gives language used at home for the Ongo Niua division as a whole "
        f"({language['Ongo Niua']['total']:,.0f} people aged five and over, General Table G "
        "50), and most of the division's people live on Niuatoputapu "
        f"({people['Niuatoputapu']['total']:,.0f} of {people['Ongo Niua']['total']:,.0f}), "
        "which the boundary file does not draw: this polygon is Niuafo'ou alone, and no "
        "table gives Niuafo'ou's own figure."))


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def notes(people_total: float, scope: str) -> dict[str, str]:
    return {
        "median_age_note": (
            f"Interpolated within the {scope} of the age that holds the middle person, from "
            f"the 2021 Census's population by age ({'G 6' if scope == 'single year' else 'G 5'})."),
        "sex_ratio_note": "Males per 100 females, 2021 Census (General Table G 1).",
        "religion_note": (
            "Religious affiliation, 2021 Census (General Table G 19), which excludes visitors "
            "and non-residents; 'Not stated' is those who refused to answer, and 'Other "
            "religion' the minor groups the table does not name."),
        "ethnicity_note": (
            "Ethnic origin -- 'the ethnic group a person belongs to' -- 2021 Census (General "
            "Table G 12), where more than one origin could be selected: each share is the "
            f"percentage of the {people_total:,.0f} people counted here who gave that origin, "
            "so the shares can sum to a little over 100."),
    }


def fields_for(name: str, people: dict[str, float], median: float | None,
               religion: dict[str, Any], ethnicity: dict[str, float], scope: str,
               language: dict[str, Any]) -> dict[str, Any]:
    """A unit's fields; ``language`` is G 50's row for it, or the gap that says why not."""
    text_notes = notes(people["total"], scope)
    return {
        "population": population(people["total"], YEAR, f"{SOURCE} (G 1)"),
        "sex_ratio": measure(sex_ratio(people["male"], people["female"]),
                             unit="males_per_100_females", year=YEAR, source=SOURCE),
        "sex_ratio_note": text_notes["sex_ratio_note"],
        "median_age": (measure(median, unit="years", year=YEAR, source=SOURCE)
                       if median is not None else gap(NOT_AVAILABLE)),
        "median_age_note": text_notes["median_age_note"] if median is not None else None,
        "religion": shares_of(religion["counts"], religion["total"]),
        "religion_year": YEAR,
        "religion_note": text_notes["religion_note"],
        "ethnicity": shares_of(ethnicity, people["total"]),
        "ethnicity_year": YEAR,
        "ethnicity_note": text_notes["ethnicity_note"],
        **({"language": shares_of(language["counts"], language["total"]),
            "language_year": YEAR, "language_note": LANGUAGE_NOTE}
           if "counts" in language else {"language": language}),
    }


SOURCES = [{"field": "population/median_age/sex_ratio/religion/ethnicity/language",
            "name": SOURCE, "url": PAGE, "year": YEAR,
            "license": "None stated -- Tonga Statistics Department publication, cited as such"}]


def build(population_book, ethnicity_book, religion_book, literacy_book,
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    people, tree = read_population(rows_of(population_book, "G 1"))
    districts = [d for ds in tree.values() for d in ds]
    medians = {**division_medians(rows_of(population_book, "G 6"), people),
               **district_medians(rows_of(population_book, "G 5"), districts, people)}
    log(f"  Tonga's median age {medians.get('TONGA')}")
    religion = read_religion(rows_of(religion_book, "G 19"), list(DIVISIONS) + districts)
    ethnicity = read_ethnicity(rows_of(ethnicity_book, "G 12"), list(DIVISIONS), districts,
                               people)
    language = read_language(rows_of(literacy_book, "G 50"))

    parents = {u["id"]: u["name"] for u in admin1}
    division_units = bind_level({d: (DIVISION_ON_MAP[d], "") for d in DIVISIONS}, admin1, {})
    drawn = [d for d in districts if d not in UNDRAWN]
    district_units = bind_level(
        {d: (ALIASES.get(d, d), DIVISION_ON_MAP[next(k for k, v in tree.items() if d in v)])
         for d in drawn}, admin2, parents, ALIASES)

    records = []
    for division, unit in division_units.items():
        # The map's "Niuas" polygon is Niuafo'ou alone, so it takes Niuafo'ou's.
        own = "Niuafo'ou" if division == "Ongo Niua" else division
        scope = "five-year group" if own != division else "single year"
        spoken = language[division] if own == division else niuas_language(language, people)
        fields = fields_for(own, people[own], medians.get(own), religion[own],
                            ethnicity[own], scope, spoken)
        if own != division:
            why = (" The boundary file draws Niuafo'ou alone for the Niuas and leaves "
                   f"Niuatoputapu ({people['Niuatoputapu']['total']:,.0f} people) out, so "
                   "these are Niuafo'ou's own figures, for the island the polygon shows.")
            for key in ("median_age_note", "sex_ratio_note", "religion_note",
                        "ethnicity_note"):
                if fields.get(key):
                    fields[key] += why
        records.append(unit_record("TON", division, unit["name"], unit, "admin1", None,
                                   SOURCES, **fields))
    for district, unit in district_units.items():
        division = next(k for k, v in tree.items() if district in v)
        fields = fields_for(district, people[district], medians.get(district),
                            religion[district], ethnicity[district], "five-year group",
                            DISTRICT_LANGUAGE)
        name = "'Eua Motu'a" if district in ALIASES else unit["name"]
        records.append(unit_record("TON", district, name, unit, "admin2",
                                   DIVISION_ON_MAP[division], SOURCES, **fields))
    for name in sorted(UNDRAWN):
        log(f"  no polygon: {name} ({people[name]['total']:,.0f} people), counted in its "
            "division")
    return records


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("tonga_census: 2021 Census General Tables 1, 2, 4 and 10")
    books = {key: workbook(url) for key, url in URLS.items()}
    records = build(books["population"], books["ethnicity"], books["religion"],
                    books["literacy"], load_units("TON", "admin1"), load_units("TON", "admin2"))
    log(f"  {len(records)} records: {summarise(records)}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
