#!/usr/bin/env python3
"""Vanuatu, 2020 Census: population, age, sex, religion, ethnic origin and first language.

One publication of the Vanuatu National Statistics Office: **2020 National
Population and Housing Census, Basic Tables, Volume 1 (Version 2)**, a
384-page PDF whose tables run by "region" -- Vanuatu, urban and rural, the
two towns, the six provinces and their 64 rural area councils:

* **Table 1.1**: total population by sex (all households, private and
  institutional), the count and the sex ratio;
* **Table 2.1**: total population by five-year age group, to an open 70+,
  for the median age;
* **Table 3.1**: population in private households by ethnic origin;
* **Table 3.5**: population in private households by religion;
* **Table 6.16**: the first language learned to speak, and **Table 6.17**
  for the number of people aged three and over in private households it is
  a share of.

**Language is a part of the people.** The census asked everyone aged three
and over whether they can speak one of the islands' own languages, and asked
the language they learned first only of those who can: "92.2% of the
population answered that they can speak an indigenous language ... The 2020
census then asked these people an additional question about the language in
which they were raised" (Analytical Report, Volume 2, p. 82). So Table 6.16
counts 239,839 of the 269,287 people aged three and over, and in Port Vila
fewer than eight in ten. Each language here is a share of everyone aged
three and over (Table 6.17's total), not of the people the table counts, so
a council's shares add up to the part of its people the question reached and
the rest -- whose first language was not asked, Bislama, English or French
for most of them -- stay unassigned rather than being spread over the
answers. Table 6.17 prints the two towns' rows under each other's names (its
"Port Vila" has 15,978 people aged three and over, fewer than the 34,802 who
speak a vernacular there, and its "Luganville" 44,856 of a town of 17,407);
read the other way round both fit, and the reader takes them so only when
both fail as printed and both fit exchanged. Table 6.16's second panel has
no row for Aneityum: its first panel's row is there, read in order under a
name the column leaves out, and the second panel's figures are Tafea's less
its other councils', which with the row's own English and French have to
make the row's total or nothing is written (``completed_panels``).

**How the PDF reads.** pypdf gives each page's text with the rows intact:
a region's name and then its figures ("Torres 1,190 597 593 ..."), with
"-" for nothing. A table too wide for one page continues on the next as a
second panel, and there pypdf gives the column of region names first and
the rows of figures after it, in the same order; the reader pairs them and
refuses a panel whose names and rows do not come out the same length. Some
pages also carry a neighbouring table's rows as text under its own title,
so every row is filed under the table title that last preceded it.

**What the map draws.** The boundary file has 58 of the 66 area councils:
Torres, Mota and Merelava (Torba) and North Tongoa, Tongariki, Makimae,
Nguna and Emau (Shefa) have no polygon, and their islands lie outside every
drawn one. They are counted in their provinces. A province's figures are its
rural row plus its town -- Port Vila is in Shefa and Luganville in Sanma,
which the tables print under "Urban".

**Checks**, each refusing the run: Vanuatu is 300,019 people, 293,963 in
private households; every row's males and females make its total; the area
councils make their province and the provinces and towns make Vanuatu;
each row's age groups, origins, denominations and languages make its total;
the private-household totals of Tables 3.1 and 3.5 are Table 1.1's; every
drawn unit is bound once. The office weights every enumeration area by a
correction factor and rounds the result, so a row may differ from the sum
of its cells by a person or two: the tolerances allow for that and no more.

Usage:
    python -m scripts.fetch_census.vanuatu_census
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, write_json
from .oceania_common import (
    bind_level, check, load_units, median_from_groups, population, published_median,
    sex_ratio, shares_of, summarise, unit_record,
)

YEAR = 2020
OUT = "vanuatu_census.json"
OFFICE = "Vanuatu National Statistics Office"
SOURCE = (f"{OFFICE}, 2020 National Population and Housing Census, Basic Tables "
          "Volume 1 (Version 2)")
URL = ("https://vbos.gov.vu/images/Public_Documents/Census_Surveys/Census/2020/Basic_Tables/"
       "2020NPHC_Volume_1_-_Version_2.pdf")
NATIONAL = 300_019
PRIVATE = 293_963
# The office's own medians, from single years of age: the Analytical Report,
# Volume 2, Table 4, 2020 rows (report pp. 12-13), read off the rendered pages,
# which have no text layer. Its provinces are their rural parts -- Sanma
# without Luganville and Shefa without Port Vila: their sex ratios (107, 101)
# are the rural rows' of Volume 1's key indicators, and Shefa's 22.2 sits
# inside the rural 22-and-over there and below Port Vila's 24-and-over, so the
# province with its town would be older -- and for the four provinces with no
# town it is the province's own.
REPORT = f"{OFFICE}, 2020 National Population and Housing Census, Analytical Report Volume 2"
REPORT_URL = ("https://vbos.gov.vu/images/Public_Documents/Census_Surveys/Census/2020/"
              "2020_Vanuatu_National_Population_and_Housing_Census_-_Analytical_report_"
              "Volume_2.pdf")
TABLE_4 = {"VANUATU": 20.9, "TORBA": 19.9, "SANMA": 19.8, "PENAMA": 18.6, "MALAMPA": 20.8,
           "SHEFA": 22.2, "TAFEA": 17.4}
# How far Table 2.1's five-year groups may put a rural province from Table 4's
# single-year median and still be the same people: interpolating within a
# five-year group in a population this young runs high, by up to 0.6 years
# here (Penama, Tafea).
GROUPED_SLACK = 1.0

# How many figures a row carries in each of a table's panels.
WIDTHS = {"1.1": (12,), "2.1": (9, 7), "3.1": (9,), "3.5": (9, 6), "6.16": (9, 7),
          "6.17": (12,)}

PROVINCES = ("TORBA", "SANMA", "PENAMA", "MALAMPA", "SHEFA", "TAFEA")
# The towns the tables print under "Urban", and the province each is in.
TOWNS = {"Port Vila": "SHEFA", "Luganville": "SANMA"}
NOT_COUNCILS = {"VANUATU", "URBAN", "RURAL", *PROVINCES}
# Area councils the boundary file does not draw.
UNDRAWN = {"Torres", "Mota", "Merelava", "North Tongoa", "Tongariki", "Makimae", "Nguna",
           "Emau"}
# The census's name for a province -> the boundary file's.
PROVINCE_ON_MAP = {"TORBA": "Torba", "SANMA": "Sanma", "PENAMA": "Penama",
                   "MALAMPA": "Malampa", "SHEFA": "Shefa Province", "TAFEA": "Tafea"}

AGE_GROUPS = [(0, 4), (5, 9), (10, 14), (15, 19), (20, 24), (25, 29), (30, 34), (35, 39),
              (40, 44), (45, 49), (50, 54), (55, 59), (60, 64), (65, 69), (70, None)]
# Table 3.5's denominations in its column order, the second panel's after
# the first's, as the census names them.
RELIGIONS = ("Presbyterian", "Seventh-day Adventist", "Catholic", "Anglican",
             "Churches of Christ", "Assemblies of God",
             "Neil Thomas Ministries (Inner Life Ministry)", "Customary beliefs",
             "Apostolic", "Church of Jesus Christ of Latter-day Saints", "Other churches",
             "No religion", "Refused to answer", "Not stated")
# Table 3.1's origins; "Ni-Vanuatu only" is written "Ni-Vanuatu".
ORIGINS = ("Ni-Vanuatu", "Part Ni-Vanuatu", "European", "Asian", "Other Melanesian",
           "Polynesian", "Micronesian", "Others")
# Table 6.16: English, French (first panel), Bislama, the vernaculars and
# not stated (second). "Indigenous (Vernacular)" in the census's words.
VERNACULAR = "Vanuatu vernacular languages"

AGED_THREE_PLUS = 269_287

NUMBER = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d+|-)$")
TITLE = re.compile(r"Table\s*:?\s*(\d+(?:\.\d+)+)")


def figures(tokens: list[str]) -> list[float]:
    return [0.0 if t == "-" else float(t.replace(",", "")) for t in tokens]


# ---------------------------------------------------------------------------
# Reading the PDF's text
# ---------------------------------------------------------------------------

def read_table(pages: list[str], table: str, order: list[str] | None = None
               ) -> dict[str, dict[int, list[float]]]:
    """{region: {panel width: figures}} for one table.

    ``order`` is the regions in the order every table prints them (Table
    1.1's); None reads them from the rows themselves (Table 1.1, which gives
    the list the others are read by). A panel that prints its names apart from
    its figures is read in that order from the first name it lists, because
    the column of names can drop one -- Table 6.16's Shefa and Tafea panel
    lists 29 names over 30 rows of figures, Aneityum's name missing -- while
    the rows keep their places. Every row read that way still has to make its
    region's total with the other panel, which a row read against the wrong
    region does not.
    """
    widths = WIDTHS[table]
    names = set(order) if order is not None else None
    rows: dict[str, dict[int, list[float]]] = {}

    def put(name: str, values: list[float]) -> None:
        have = rows.setdefault(name, {})
        width = len(values)
        if width in have:
            check(have[width] == values,
                  f"vanuatu_census: Table {table} prints {name} twice with different figures")
        else:
            have[width] = values

    for page in pages:
        current = None
        block: list[str] = []
        numbers: list[list[str]] = []
        after_name = False

        def close() -> None:
            if block and numbers and order is not None:
                start = order.index(block[0])
                run = order[start:start + len(numbers)]
                check(len(run) == len(numbers) and set(block) <= set(run)
                      and block == [n for n in run if n in block],
                      f"vanuatu_census: Table {table}: a panel lists {block[0]}..{block[-1]} "
                      f"({len(block)} names) over {len(numbers)} rows of figures")
                if len(block) != len(numbers):
                    log(f"  Table {table}: a panel lists {len(block)} names over "
                        f"{len(numbers)} rows; read in order from {block[0]}, missing "
                        f"{[n for n in run if n not in block]}")
                for name, tokens in zip(run, numbers):
                    put(name, figures(tokens))
            block.clear()
            numbers.clear()

        for raw in page.splitlines():
            line = " ".join(raw.split())
            titles = TITLE.findall(line)
            if titles:
                close()
                after_name = False
                current = titles[-1]
                continue
            if current != table or not line:
                continue
            if names is not None and line in names:
                if not after_name:
                    close()
                block.append(line)
                after_name = True
                continue
            after_name = False
            tokens = line.split()
            if all(NUMBER.match(t) for t in tokens):
                if len(tokens) in widths and block:
                    numbers.append(tokens)
                continue
            for width in widths:
                if len(tokens) <= width or not all(NUMBER.match(t) for t in tokens[-width:]):
                    continue
                name = " ".join(tokens[:-width])
                if (name in names) if names is not None else name[:1].isalpha():
                    put(name, figures(tokens[-width:]))
                    break
        close()
    return rows


def panels(rows: dict[str, dict[int, list[float]]], table: str, names: list[str],
           may_lack: frozenset[str] = frozenset()) -> dict[str, list[float]]:
    """Each region's figures, its panels joined in order.

    A region missing a panel stops the run, unless it is in ``may_lack``:
    then it is left out, and the log says so.
    """
    out = {}
    for name in names:
        have = rows.get(name, {})
        missing = [w for w in WIDTHS[table] if w not in have]
        if missing and name in may_lack:
            log(f"  Table {table} has no {missing}-figure row for {name}: left out")
            continue
        check(not missing, f"vanuatu_census: Table {table} has no {missing}-figure row "
                           f"for {name}")
        out[name] = [v for w in WIDTHS[table] for v in have[w]]
    return out


# ---------------------------------------------------------------------------
# The tables
# ---------------------------------------------------------------------------

def read_population(pages: list[str]) -> tuple[dict[str, dict[str, float]], list[str],
                                               dict[str, list[str]]]:
    """({region: {total, male, female, private}}, regions in order, {province: councils})."""
    rows = read_table(pages, "1.1")
    order = list(rows)
    check(order[:5] == ["VANUATU", "URBAN", "Port Vila", "Luganville", "RURAL"],
          f"vanuatu_census: Table 1.1 opens with {order[:5]}")
    people = {}
    for name, values in panels(rows, "1.1", order).items():
        total, male, female, _, private = values[:5]
        check(abs(male + female - total) <= 2,
              f"vanuatu_census: Table 1.1 {name}: {male:,.0f} males and {female:,.0f} "
              f"females for {total:,.0f}")
        people[name] = {"total": total, "male": male, "female": female, "private": private}
    check(people["VANUATU"]["total"] == NATIONAL and people["VANUATU"]["private"] == PRIVATE,
          f"vanuatu_census: Table 1.1 reads Vanuatu {people['VANUATU']}")
    councils: dict[str, list[str]] = {}
    province = None
    for name in order[5:]:
        if name in PROVINCES:
            province = name
            councils[province] = []
        else:
            check(province is not None, f"vanuatu_census: {name} before any province")
            councils[province].append(name)
    check(set(councils) == set(PROVINCES), f"vanuatu_census: provinces read {sorted(councils)}")
    for province, names in councils.items():
        for key in ("total", "private"):
            made = sum(people[c][key] for c in names)
            check(abs(made - people[province][key]) <= len(names),
                  f"vanuatu_census: {province}'s councils make {made:,.0f}, not "
                  f"{people[province][key]:,.0f} ({key})")
    made = sum(people[p]["total"] for p in PROVINCES) + sum(people[t]["total"] for t in TOWNS)
    check(abs(made - NATIONAL) <= 8, f"vanuatu_census: provinces and towns make {made:,.0f}")
    return people, order, councils


def read_ages(pages: list[str], order: list[str], people: dict[str, dict[str, float]]
              ) -> dict[str, list[float]]:
    out = {}
    for name, values in panels(read_table(pages, "2.1", order), "2.1", order).items():
        total, groups = values[0], values[1:]
        check(len(groups) == len(AGE_GROUPS), f"vanuatu_census: Table 2.1 {name}: "
                                              f"{len(groups)} age groups")
        check(abs(sum(groups) - total) <= 8 and abs(total - people[name]["total"]) <= 2,
              f"vanuatu_census: Table 2.1 {name}: groups make {sum(groups):,.0f}, total "
              f"{total:,.0f}, Table 1.1 {people[name]['total']:,.0f}")
        out[name] = groups
    return out


def read_composition(pages: list[str], table: str, labels: tuple[str, ...], order: list[str],
                     people: dict[str, dict[str, float]]) -> dict[str, dict[str, Any]]:
    """Table 3.1 or 3.5: {region: {total, counts}} for people in private households."""
    out = {}
    for name, values in panels(read_table(pages, table, order), table, order).items():
        total, cells = values[0], values[1:]
        check(len(cells) == len(labels), f"vanuatu_census: Table {table} {name}: "
                                         f"{len(cells)} columns for {len(labels)}")
        check(abs(sum(cells) - total) <= 8,
              f"vanuatu_census: Table {table} {name}: cells make {sum(cells):,.0f}, not "
              f"{total:,.0f}")
        check(abs(total - people[name]["private"]) <= 2,
              f"vanuatu_census: Table {table} {name}: {total:,.0f} in private households, "
              f"Table 1.1 {people[name]['private']:,.0f}")
        out[name] = {"total": total, "counts": dict(zip(labels, cells))}
    return out


def aged_three_plus(pages: list[str], order: list[str], people: dict[str, dict[str, float]]
                    ) -> dict[str, float]:
    """Table 6.17's total for each region: everyone aged 3+ in private households."""
    out = {}
    for name, values in panels(read_table(pages, "6.17", order), "6.17", order).items():
        for first in (0, 4, 8):
            check(abs(sum(values[first + 1:first + 4]) - values[first]) <= 2,
                  f"vanuatu_census: Table 6.17 {name}: answers do not make a total")
        check(abs(values[4] + values[8] - values[0]) <= 2,
              f"vanuatu_census: Table 6.17 {name}: males and females do not make a total")
        out[name] = values[0]
    check(out["VANUATU"] == AGED_THREE_PLUS,
          f"vanuatu_census: Table 6.17 reads {out['VANUATU']:,.0f} aged 3+")
    return out


def settle_towns(aged: dict[str, float], spoken: dict[str, dict[str, Any]],
                 people: dict[str, dict[str, float]]) -> list[str]:
    """Check every region's 3+ count fits; exchange the towns' if only that fits.

    A region's people aged three and over are no fewer than those of them who
    speak a vernacular (Table 6.16) and no more than its people in private
    households (Table 1.1). Returns the regions exchanged, for the notes.
    """
    def fits(name: str, value: float) -> bool:
        return name not in spoken or spoken[name]["total"] <= value <= people[name]["private"]

    a, b = TOWNS
    swapped: list[str] = []
    if not fits(a, aged[a]) and not fits(b, aged[b]) and fits(a, aged[b]) and fits(b, aged[a]):
        log(f"  Table 6.17 prints {a}'s and {b}'s rows under each other's names: exchanged")
        aged[a], aged[b] = aged[b], aged[a]
        swapped = [a, b]
    bad = [n for n in aged if not fits(n, aged[n])]
    check(not bad, f"vanuatu_census: Table 6.17's people aged 3+ do not fit for {bad}")
    return swapped


def completed_panels(rows: dict[str, dict[int, list[float]]], full: dict[str, list[float]],
                     by_province: dict[str, list[str]]) -> dict[str, tuple[list[float], str]]:
    """A council's Table 6.16 row whose second panel the page does not print,
    completed from its province's row less its other councils', with the
    province it came from.

    Table 6.16's Shefa and Tafea page prints its first panel -- the total,
    English and French -- for every council, Aneityum's figures sitting
    under a name the column leaves out, and ends its second panel -- Bislama,
    the vernaculars and not stated -- at Futuna, one short. The province's own
    row and every other council's are in the same table, so the missing
    figures are their difference, and the council's own first-panel total is
    the test of it: the five languages have to make it.
    """
    first, second = WIDTHS["6.16"]
    out: dict[str, tuple[list[float], str]] = {}
    for province, names in (by_province or {}).items():
        lacking = [n for n in names if n not in full
                   and first in rows.get(n, {}) and second not in rows.get(n, {})]
        if len(lacking) != 1 or province not in full:
            continue
        name = lacking[0]
        others = [n for n in names if n != name]
        if any(n not in full for n in others):
            continue
        left = [full[province][first + i] - sum(full[n][first + i] for n in others)
                for i in range(second)]
        check(min(left) >= 0, f"vanuatu_census: Table 6.16 {province} less its other councils "
                              f"leaves {left} for {name}")
        out[name] = (rows[name][first] + left, province)
    return out


def read_language(pages: list[str], order: list[str], people: dict[str, dict[str, float]],
                  by_province: dict[str, list[str]] | None = None
                  ) -> dict[str, dict[str, Any]]:
    """Table 6.16: {region: {total, counts}}, first language learned to speak (3+).

    ``total`` is the people the table counts -- those aged three and over who
    can speak a vernacular -- and is replaced by everyone aged three and over
    once Table 6.17 is read. A council whose second panel the page leaves out
    is completed from its province's row (``completed_panels``), and says so.
    """
    out = {}
    councils = frozenset(order) - NOT_COUNCILS - set(TOWNS)
    rows = read_table(pages, "6.16", order)
    full = panels(rows, "6.16", order, may_lack=councils)
    completed = completed_panels(rows, full, by_province or {})
    for name, (values, province) in completed.items():
        log(f"  Table 6.16 {name}: its second panel completed from {province} less its "
            f"other councils")
    for name, (values, province) in list(completed.items()):
        made = values[3] + values[6] + values[9] + values[12] + values[15]
        sexes = all(abs(values[i + 1] + values[i + 2] - values[i]) <= 2 for i in (0, 3, 6, 9, 12))
        if abs(made - values[0]) > 5 or not sexes or values[0] > people[name]["private"]:
            log(f"  Table 6.16 {name}: the completed row does not make its own total "
                f"({made:,.0f} against {values[0]:,.0f}), so no language is written")
            del completed[name]
    for name, values in {**full, **{n: v for n, (v, _) in completed.items()}}.items():
        total = values[0]
        counts = {"English": values[3], "French": values[6], "Bislama": values[9],
                  VERNACULAR: values[12], "Not stated": values[15]}
        for first in (0, 3, 6, 9, 12):
            check(abs(values[first + 1] + values[first + 2] - values[first]) <= 2,
                  f"vanuatu_census: Table 6.16 {name}: males and females do not make a total")
        check(abs(sum(counts.values()) - total) <= 5,
              f"vanuatu_census: Table 6.16 {name}: languages make {sum(counts.values()):,.0f}"
              f", not {total:,.0f}")
        check(total <= people[name]["private"],
              f"vanuatu_census: Table 6.16 {name}: {total:,.0f} aged 3+ of "
              f"{people[name]['private']:,.0f} in private households")
        out[name] = {"total": total, "counts": counts}
        if name in completed:
            out[name]["completed_from"] = completed[name][1]
    return out


# ---------------------------------------------------------------------------
# Provinces: the rural row and the town
# ---------------------------------------------------------------------------

def with_town(province: str, table: dict[str, Any]) -> Any:
    """A province's row with its town's added, for a table of counts or of groups."""
    towns = [t for t, p in TOWNS.items() if p == province]
    row = table[province]
    if not towns:
        return row
    if isinstance(row, (int, float)):
        return row + sum(table[t] for t in towns)
    if isinstance(row, list):
        return [a + sum(table[t][i] for t in towns) for i, a in enumerate(row)]
    if "counts" in row:
        return {"total": row["total"] + sum(table[t]["total"] for t in towns),
                "counts": {k: v + sum(table[t]["counts"][k] for t in towns)
                           for k, v in row["counts"].items()}}
    return {k: v + sum(table[t][k] for t in towns) for k, v in row.items()}


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

NOTES = {
    "population_note": "Total population, all households, 2020 Census (Table 1.1).",
    "sex_ratio_note": "Males per 100 females, 2020 Census (Table 1.1).",
    "median_age_note": (
        "Interpolated within the five-year age group that holds the middle person, from the "
        "2020 Census's population by five-year age group to an open 70 and over (Table "
        "2.1)."),
    "religion_note": (
        "Religion of the population in private households, 2020 Census (Table 3.5), in the "
        "census's own denominations; 'Customary beliefs' is kastom, the island's own "
        "religion."),
    "ethnicity_note": (
        "Ethnic origin of the population in private households, 2020 Census (Table 3.1); "
        "'Ni-Vanuatu' is the census's 'Ni-Vanuatu only'."),
}


def language_note(asked: float, aged: float, swapped: bool) -> str:
    note = (
        "First language learned to speak, 2020 Census (Table 6.16), which the census asked "
        "only of the people who can speak one of the islands' own languages: "
        f"{asked:,.0f} of the {aged:,.0f} people aged three and over in private households "
        "here (Table 6.17). Each share is of all of them, so the shares add up to the "
        f"{100 * asked / aged:.1f}% the question reached; the first language of the rest, who "
        "speak no vernacular, was not asked. 'Vanuatu vernacular languages' is the census's "
        "'Indigenous (Vernacular)': the islands' own languages, every one of them Oceanic.")
    if swapped:
        note += (" Table 6.17 prints Port Vila's and Luganville's rows under each other's "
                 "names; read as printed, neither fits the town, and exchanged both do.")
    return note


ANEITYUM_LANGUAGE = (
    "Table 6.16's second panel -- Bislama, the vernaculars and not stated -- has no row for "
    "this council: the page for Shefa and Tafea ends its list at Futuna, so no first "
    "language can be given here.")


def completed_note(language: dict[str, Any]) -> str:
    """What a council whose row the page cut short carries, and how it was made."""
    province = language.get("completed_from")
    if not province:
        return ""
    counts = language["counts"]
    return (f" The page prints this council's total, English and French but not its "
            f"Bislama, vernacular and not-stated figures, which are "
            f"{PROVINCE_ON_MAP[province]}'s less its other councils' in the same table: "
            f"{counts['Bislama']:,.0f}, {counts[VERNACULAR]:,.0f} and "
            f"{counts['Not stated']:,.0f}. With the council's own English "
            f"({counts['English']:,.0f}) and French ({counts['French']:,.0f}) they make "
            f"the {language['total']:,.0f} people its row counts.")


def fields_for(people: dict[str, float], groups: list[float], religion: dict[str, Any],
               ethnicity: dict[str, Any], language: dict[str, Any] | None,
               aged: float | None = None, swapped: bool = False) -> dict[str, Any]:
    median = median_from_groups([(lo, hi, n) for (lo, hi), n in zip(AGE_GROUPS, groups)])
    spoken: dict[str, Any] = (
        {"language": shares_of(language["counts"], aged), "language_year": YEAR,
         "language_note": language_note(language["total"], aged, swapped)
                          + completed_note(language)}
        if language is not None and aged
        else {"language": gap(NOT_AVAILABLE, ANEITYUM_LANGUAGE)})
    return {
        "population": population(people["total"], YEAR, f"{SOURCE} (Table 1.1)"),
        "sex_ratio": measure(sex_ratio(people["male"], people["female"]),
                             unit="males_per_100_females", year=YEAR, source=SOURCE),
        "median_age": (measure(median, unit="years", year=YEAR, source=SOURCE)
                       if median is not None else None),
        "religion": shares_of(religion["counts"], religion["total"]),
        "religion_year": YEAR,
        "ethnicity": shares_of(ethnicity["counts"], ethnicity["total"]),
        "ethnicity_year": YEAR,
        **spoken,
        **NOTES,
    }


SOURCES = [{"field": "population/median_age/sex_ratio/religion/ethnicity/language",
            "name": SOURCE, "url": URL, "year": YEAR,
            "license": "None stated -- Vanuatu National Statistics Office publication, cited "
                       "as such"},
           {"field": "median_age (Torba, Penama, Malampa, Tafea; a control elsewhere)",
            "name": f"{REPORT}, Table 4", "url": REPORT_URL, "year": YEAR,
            "license": "None stated -- Vanuatu National Statistics Office publication, cited "
                       "as such"}]


def province_median(province: str, towns: list[str], grouped: dict[str, float | None],
                    note: str) -> dict[str, Any]:
    """The office's own median for a province with no town; with a town, a word on it."""
    if towns:
        return {"median_age_note": note + (
            f" The office's own median, from single years, is {TABLE_4[province]} for the "
            f"province without {towns[0]} (Analytical Report, Volume 2, Table 4); it prints "
            "none for the province with its town.")}
    return {
        "median_age": measure(TABLE_4[province], unit="years", year=YEAR,
                              source=f"{REPORT} (Table 4)"),
        "median_age_note": (
            "The office's own median age, from single years of age (Analytical Report, "
            f"Volume 2, Table 4). Table 2.1's five-year groups give {grouped[province]}."),
    }


def build(pages: list[str], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> list[dict[str, Any]]:
    people, order, councils = read_population(pages)
    ages = read_ages(pages, order, people)
    ethnicity = read_composition(pages, "3.1", ORIGINS, order, people)
    religion = read_composition(pages, "3.5", RELIGIONS, order, people)
    language = read_language(pages, order, people, councils)
    aged = aged_three_plus(pages, order, people)
    swapped = settle_towns(aged, language, people)
    grouped = {row: median_from_groups([(lo, hi, n) for (lo, hi), n in zip(AGE_GROUPS, ages[row])])
               for row in TABLE_4}
    log("  Vanuatu's median age from Table 2.1: "
        + published_median(grouped["VANUATU"], TABLE_4["VANUATU"], "vanuatu_census: Vanuatu")
        + f"; Table 6.16 counts {language['VANUATU']['total']:,.0f} people aged 3+ of "
        f"{people['VANUATU']['private']:,.0f} in private households")
    for province in PROVINCES:
        check(grouped[province] is not None
              and abs(grouped[province] - TABLE_4[province]) <= GROUPED_SLACK,
              f"vanuatu_census: rural {province}'s five-year groups give a median of "
              f"{grouped[province]}, the Analytical Report's Table 4 {TABLE_4[province]}")
    log("  rural provinces' medians, Table 2.1's five-year groups against Table 4: "
        + ", ".join(f"{p} {grouped[p]} ({TABLE_4[p]})" for p in PROVINCES))

    parents = {u["id"]: u["name"] for u in admin1}
    province_units = bind_level({p: (PROVINCE_ON_MAP[p], "") for p in PROVINCES}, admin1, {})
    province_of = {c: p for p, cs in councils.items() for c in cs} | dict(TOWNS)
    drawn = [c for c in province_of if c not in UNDRAWN]
    council_units = bind_level({c: (c, PROVINCE_ON_MAP[province_of[c]]) for c in drawn},
                               admin2, parents)

    records = []
    for province, unit in province_units.items():
        towns = [t for t, p in TOWNS.items() if p == province]
        fields = fields_for(with_town(province, people), with_town(province, ages),
                            with_town(province, religion), with_town(province, ethnicity),
                            with_town(province, language), with_town(province, aged),
                            swapped=bool(set(towns) & set(swapped)))
        fields.update(province_median(province, towns, grouped, fields["median_age_note"]))
        if towns:
            fields["population_note"] += (f" The province's rural councils and {towns[0]}, "
                                          "which the tables print under 'Urban'.")
        records.append(unit_record("VUT", province, unit["name"], unit, "admin1", None,
                                   SOURCES, **fields))
    for council, unit in council_units.items():
        fields = fields_for(people[council], ages[council], religion[council],
                            ethnicity[council], language.get(council), aged.get(council),
                            swapped=council in swapped)
        records.append(unit_record("VUT", council, council, unit, "admin2",
                                   PROVINCE_ON_MAP[province_of[council]], SOURCES, **fields))
    for name in sorted(UNDRAWN):
        log(f"  no polygon: {name} ({people[name]['total']:,.0f} people), counted in its "
            "province")
    return records


def page_texts(blob: bytes) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob))
    return [(page.extract_text() or "") for page in reader.pages]


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("vanuatu_census: 2020 Census Basic Tables, Volume 1")
    blob = http_get(URL, binary=True, timeout=600)
    assert isinstance(blob, bytes)
    check(blob[:5] == b"%PDF-", f"vanuatu_census: {URL} is not a PDF ({blob[:40]!r})")
    pages = page_texts(blob)
    log(f"  {len(blob):,} bytes, {len(pages)} pages")
    records = build(pages, load_units("VUT", "admin1"), load_units("VUT", "admin2"))
    log(f"  {len(records)} records: {summarise(records)}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
