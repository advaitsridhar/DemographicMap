#!/usr/bin/env python3
"""Tuvalu: the 2022 census's islands, and the 2017 census's villages and faiths.

Two publications of the Central Statistics Division (``stats.gov.tv``):

* **Tuvalu 2022 Census on Population and Housing, Analytical Report**
  (March 2025, 65 pp): Table 3 gives each island's resident population at
  the 2002-2022 censuses, Table 6 each island's broad age groups, sex ratio
  and median age in 2022, in whole numbers. Religion and ethnicity are in it
  only as national figures (Figures 5 and 6).
* **2017 Census tables** (a workbook of 56 person and 20 household tables):
  Table 2 is the population of every village by sex, Table 13 the resident
  population by ethnicity and Table 14 by religious denomination, each by
  island of usual residence -- the latest census to publish either below
  the country.

**What the map draws.** Three islands -- Nui, Nukufetau and Vaitupu -- at the
first level, and six of their villages at the second: Alamoni on Nui, Aulotu
on Nukufetau, and Matagi, Motufoua, Saniuta and Temotu on Vaitupu (Nanumea
has a village called Matagi too; the polygon is Vaitupu's). An island
carries its 2022 count, sex ratio and median age and its 2017 religion and
ethnicity; a village its 2017 count and sex ratio, the only figures the
census gives a village. Motufoua is the national secondary boarding school,
which is why its 326 people are two-thirds female.

**Checks**, each refusing the run: Table 6's three age groups make each
island's 2022 population and that number is in the island's Table 3 row;
the nine islands make Tuvalu's 10,632; every village row's sexes make its
total and an island's villages make the island; Tables 13 and 14 give each
island one total, the same in both, made exactly by its groups.

Usage:
    python -m scripts.fetch_census.tuvalu_census
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, write_json
from .oceania_common import (
    bind_level, check, load_units, number, population, rows_of, sex_ratio, shares_of,
    summarise, unit_record, workbook,
)

OUT = "tuvalu_census.json"
OFFICE = "Central Statistics Division, Government of Tuvalu"
REPORT_URL = ("https://stats.gov.tv/download/85/population-and-housing-census/1836/"
              "tuvalu_2022_census_report.pdf")
TABLES_URL = ("https://stats.gov.tv/download/85/population-and-housing-census/905/"
              "2017-census-tables-2.xlsx")
REPORT = f"{OFFICE}, Tuvalu 2022 Census on Population and Housing: Analytical Report"
TABLES = f"{OFFICE}, 2017 Population and Housing Mini-Census tables"
LICENCE = "None stated -- Central Statistics Division publication, cited as such"

ISLANDS = ("Funafuti", "Nanumea", "Nanumaga", "Niutao", "Nui", "Vaitupu", "Nukufetau",
           "Nukulaelae", "Niulakita")
DRAWN_ISLANDS = ("Nui", "Nukufetau", "Vaitupu")
DRAWN_VILLAGES = {("Nui", "Alamoni"), ("Nukufetau", "Aulotu"), ("Vaitupu", "Matagi"),
                  ("Vaitupu", "Motufoua"), ("Vaitupu", "Saniuta"), ("Vaitupu", "Temotu")}
NATIONAL_2022 = 10_632

RELIGIONS = {"EKT": "Church of Tuvalu", "SDA": "Seventh-day Adventist",
             "Jehovah's Witness": "Jehovah's Witnesses", "Bahaii": "Bahá'í",
             "Brethren": "Brethren", "AOG": "Assemblies of God", "Catholic": "Roman Catholic",
             "LDS": "Church of Jesus Christ of Latter-day Saints", "Other": "Other religion",
             "None": "No religion", "Refused": "Refused to answer"}
ETHNIC = {"Tuvaluan": "Tuvaluan", "Tuvaluan / I-Kiribati": "Tuvaluan and I-Kiribati",
          "Tuvaluan / Other": "Tuvaluan and other", "Other": "Other ethnicity"}


def text(cell: Any) -> str:
    return "" if cell is None else str(cell).strip()


# ---------------------------------------------------------------------------
# The 2022 report
# ---------------------------------------------------------------------------

def section(lines: list[str], start: str, stop: str) -> list[str]:
    at = next((i for i, ln in enumerate(lines) if ln.startswith(start) and "...." not in ln),
              None)
    check(at is not None, f"tuvalu_census: the report has no {start!r}")
    end = next((i for i in range(at + 1, len(lines)) if lines[i].startswith(stop)), len(lines))
    return lines[at:end]


def read_report(pages: list[str]) -> dict[str, dict[str, int]]:
    """{island: {population, sex_ratio, median}} from Tables 3 and 6, 2022."""
    lines = [" ".join(ln.split()) for page in pages for ln in page.splitlines() if ln.strip()]
    table_3 = section(lines, "Table 3.", "Table 4.")
    table_6 = section(lines, "Table 6.", "For the country as a whole")
    out: dict[str, dict[str, int]] = {}
    for line in table_6:
        name = next((i for i in ISLANDS + ("Total",) if line.startswith(i + " ")), None)
        if name is None:
            continue
        figures = line[len(name):].split()
        if len(figures) != 8 or not all(re.fullmatch(r"\d{1,3}(?:,\d{3})*", f)
                                        for f in figures):
            continue
        young, working, old, _dependency, ratio, median, _m, _f = (
            int(f.replace(",", "")) for f in figures)
        out[name] = {"population": young + working + old, "sex_ratio": ratio,
                     "median": median}
    check(set(out) == set(ISLANDS) | {"Total"},
          f"tuvalu_census: Table 6 gives {sorted(out)}")
    total = out.pop("Total")["population"]
    check(total == NATIONAL_2022 == sum(i["population"] for i in out.values()),
          f"tuvalu_census: Table 6's islands make {sum(i['population'] for i in out.values())}"
          f" and its total {total}, not {NATIONAL_2022:,}")
    for name in DRAWN_ISLANDS:
        row = next((ln for ln in table_3 if ln.startswith(name + " ")), "")
        check(f"{out[name]['population']:,}" in row.split(),
              f"tuvalu_census: Table 3's row for {name} ({row!r}) does not count Table 6's "
              f"{out[name]['population']:,}")
    log(f"  2022 report: nine islands making {NATIONAL_2022:,}; Table 3 agrees for "
        f"{', '.join(DRAWN_ISLANDS)}")
    return out


# ---------------------------------------------------------------------------
# The 2017 tables
# ---------------------------------------------------------------------------

def read_villages(rows: list[list[Any]]) -> dict[tuple[str, str], tuple[int, int, int]]:
    """{(island, village): (people, males, females)} resident in Tuvalu, Table 2."""
    out: dict[tuple[str, str], tuple[int, int, int]] = {}
    islands: dict[str, tuple[int, int, int]] = {}
    island = None
    for row in rows:
        label = "" if not row or row[0] is None else str(row[0])
        name = label.strip()
        if len(row) < 7 or number(row[4]) is None:
            continue
        resident = tuple(int(number(row[i]) or 0) for i in (4, 5, 6))
        if name in ISLANDS and not label.startswith(" "):
            island = name
            islands[name] = resident
        elif island and label.startswith(" ") and name:
            out[(island, name)] = resident
    check(set(islands) == set(ISLANDS), f"tuvalu_census: Table 2 gives islands {sorted(islands)}")
    for (isl, village), (t, m, f) in out.items():
        check(m + f == t, f"tuvalu_census: {village}, {isl}: {m} + {f} != {t}")
    for isl, (t, _m, _f) in islands.items():
        summed = sum(v[0] for (i, _), v in out.items() if i == isl)
        check(summed == t, f"tuvalu_census: {isl}'s villages make {summed}, not {t}")
    missing = sorted(DRAWN_VILLAGES - set(out))
    check(not missing, f"tuvalu_census: Table 2 has no {missing}")
    return out


def read_by_island(rows: list[list[Any]], labels: dict[str, str], table: str
                   ) -> dict[str, dict[str, int]]:
    """{island: {group: people}} from the island blocks' Total rows of Table 13 or 14."""
    header = next((r for r in rows if len(r) > 4 and text(r[1]) == "Total"), None)
    check(header is not None, f"tuvalu_census: {table} has no header row")
    groups = [(text(header[i]), i) for i in range(4, len(header), 3) if text(header[i])]
    check({g for g, _ in groups} == set(labels),
          f"tuvalu_census: {table}'s groups are {[g for g, _ in groups]}")
    out: dict[str, dict[str, int]] = {}
    island = None
    for row in rows:
        name = text(row[0]) if row else ""
        if name in ISLANDS or name == "Tuvalu":
            island = name
            continue
        if name == "Total" and island and island not in out:
            total = int(number(row[1]) or 0)
            counts = {labels[g]: int(number(row[i]) or 0) for g, i in groups}
            check(sum(counts.values()) == total,
                  f"tuvalu_census: {table}, {island}: groups make {sum(counts.values())}, "
                  f"not {total}")
            out[island] = counts
    check(set(out) >= set(DRAWN_ISLANDS), f"tuvalu_census: {table} gives {sorted(out)}")
    return out


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

LANGUAGE_GAP = (
    "Neither Tuvalu census publishes a language composition: the 2017 tables (56 person "
    "and 20 household tables) have no language table, and the 2022 report's only language "
    "figure is the language people can read and write in (Table 10), for the country as a "
    "whole.")
VILLAGE_GAPS = {
    "median_age": "The 2017 census gives ages by island, not by village (Tables 4-6), and the "
                  "2022 report by island only.",
    "religion": "The 2017 census gives religion by island (Table 14), not by village; the 2022 "
                "report gives it for the country only.",
    "ethnicity": "The 2017 census gives ethnicity by island (Table 13), not by village; the "
                 "2022 report gives it for the country only.",
}
COMPOSITION_NOTE = (
    "{what} of the island's usual residents at the 2017 census (Table {table}), the latest "
    "by island: the 2022 report gives it for the country only. The 2017 tables count "
    "{people:,} usual residents here, who include people away on census night.")


def island_fields(name: str, report: dict[str, dict[str, int]],
                  faith: dict[str, dict[str, int]], ethnic: dict[str, dict[str, int]]
                  ) -> dict[str, Any]:
    figures = report[name]
    residents = sum(faith[name].values())
    return {
        "population": population(figures["population"], 2022, f"{REPORT} (Table 3)"),
        "sex_ratio": measure(figures["sex_ratio"], unit="males_per_100_females", year=2022,
                             source=f"{REPORT} (Table 6)"),
        "sex_ratio_note": "Males per 100 females, 2022 census (Table 6), in whole numbers.",
        "median_age": measure(figures["median"], unit="years", year=2022,
                              source=f"{REPORT} (Table 6)"),
        "median_age_note": "Median age, 2022 census (Table 6), in whole years.",
        "religion": shares_of(faith[name], residents),
        "religion_year": 2017,
        "religion_note": COMPOSITION_NOTE.format(what="Religion", table=14, people=residents),
        "ethnicity": shares_of(ethnic[name], residents),
        "ethnicity_year": 2017,
        "ethnicity_note": COMPOSITION_NOTE.format(what="Ethnicity", table=13,
                                                  people=residents),
        "language": gap(NOT_AVAILABLE, LANGUAGE_GAP),
    }


def village_fields(people: tuple[int, int, int]) -> dict[str, Any]:
    total, male, female = people
    return {
        "population": population(total, 2017, f"{TABLES} (Table 2)"),
        "population_note": ("People living in Tuvalu enumerated in the village at the 2017 "
                            "census (Table 2); the 2022 census publishes no village counts."),
        "sex_ratio": measure(sex_ratio(male, female), unit="males_per_100_females", year=2017,
                             source=f"{TABLES} (Table 2)"),
        "sex_ratio_note": "Males per 100 females, 2017 census (Table 2).",
        "median_age": gap(NOT_AVAILABLE, VILLAGE_GAPS["median_age"]),
        "religion": gap(NOT_AVAILABLE, VILLAGE_GAPS["religion"]),
        "ethnicity": gap(NOT_AVAILABLE, VILLAGE_GAPS["ethnicity"]),
        "language": gap(NOT_AVAILABLE, LANGUAGE_GAP),
    }


SOURCES = [
    {"field": "population/sex_ratio/median_age (islands)", "name": REPORT, "url": REPORT_URL,
     "year": 2022, "license": LICENCE},
    {"field": "religion/ethnicity (islands); population/sex_ratio (villages)", "name": TABLES,
     "url": TABLES_URL, "year": 2017, "license": LICENCE},
]


def build(report: dict[str, dict[str, int]], villages: dict[tuple[str, str], tuple[int, ...]],
          faith: dict[str, dict[str, int]], ethnic: dict[str, dict[str, int]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    check(set(faith) == set(ethnic) and all(sum(faith[i].values()) == sum(ethnic[i].values())
                                           for i in faith),
          "tuvalu_census: Tables 13 and 14 count different residents")
    island_units = bind_level({i: (i, "") for i in DRAWN_ISLANDS}, admin1, {})
    parents = {u["id"]: u["name"] for u in admin1}
    village_units = bind_level({f"{i}|{v}": (v, i) for i, v in DRAWN_VILLAGES}, admin2, parents)
    records = [unit_record("TUV", island, unit["name"], unit, "admin1", None, SOURCES,
                           **island_fields(island, report, faith, ethnic))
               for island, unit in island_units.items()]
    for key, unit in village_units.items():
        island, village = key.split("|")
        records.append(unit_record("TUV", key, unit["name"], unit, "admin2", island, SOURCES,
                                   **village_fields(villages[(island, village)])))
    return records


def report_pages() -> list[str]:
    from pypdf import PdfReader  # noqa: PLC0415
    blob = http_get(REPORT_URL, binary=True, timeout=600)
    check(isinstance(blob, bytes) and blob[:5] == b"%PDF-", "tuvalu_census: the report is no PDF")
    return [(page.extract_text() or "") for page in PdfReader(io.BytesIO(blob)).pages]


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("tuvalu_census: 2022 report (islands) and 2017 tables (villages, faiths)")
    report = read_report(report_pages())
    book = workbook(TABLES_URL)
    villages = read_villages(rows_of(book, "2"))
    ethnic = read_by_island(rows_of(book, "13"), ETHNIC, "Table 13")
    faith = read_by_island(rows_of(book, "14"), RELIGIONS, "Table 14")
    records = build(report, villages, faith, ethnic, load_units("TUV", "admin1"),
                    load_units("TUV", "admin2"))
    log("  " + summarise(records))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
