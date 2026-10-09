#!/usr/bin/env python3
"""Nauru, 2021 Population and Housing Census: every district's people, age, sex, ethnicity, religion.

Two publications of the Nauru Bureau of Statistics (``stats.gov.nr``):

* **2021 PHC Tables, Volume 1** (workbook). Table G-1 is the population by
  district and sex; M-1 the population aged 15 and over by five-year age
  group and district; I-1 the population by district and ethnicity; H-1 by
  district and citizenship.
* **2021 Population and Household Census, Persons Tabulations** (PDF).
  Table 19 is the religion of the Nauruan (citizen or dual) population by
  district -- 11,215 of the 11,680 counted; the census publishes religion for
  everyone only for the country as a whole (Table G-7).

**Districts.** The census counts 14 districts and, apart, "Location", the
settlement built for the phosphate company's workers, which lies inside
Denigomodu District. The boundary file draws the 14 districts (the same
polygons at both of its levels), so Denigomodu's polygon carries its own
count and Location's together, and its note says so. The census spells one
district Baitsi; the boundary file Baiti.

**Median age.** The census prints the median only for the country (21.6
years, Analytical Report Table 2). A district's is interpolated from its
five-year groups from 15 upward (Table M-1) with everyone under 15 in one
group -- its total less the people aged 15 and over (Table G-1). Where the
under-15s are half the people or more, the median falls inside that group
and is not computed.

**Language.** The census asked whether each person speaks Nauruan, and
publishes the answer by age and citizenship for the whole country (Persons
Tabulations, Table 28), never by district.

**Checks**, each refusing the run: the districts and Location add up to the
11,680 counted, and every district's men and women to its total; each
district's ethnic groups add up to its people; its five-year groups from 15
up to no more than its people; each district's religions add up to its
citizens (Table H-1), and Table 19's districts to the country's 11,215; the
national median computed the same way is within half a year of the 21.6
the Analytical Report prints.

Usage:
    python -m scripts.fetch_census.nauru_census
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, write_json
from .oceania_common import (
    bind_level, check, load_units, median_from_groups, number, population, sex_ratio,
    shares_of, summarise, unit_record, workbook,
)

OUT = "nauru_census.json"
YEAR = 2021
OFFICE = "Nauru Bureau of Statistics"
LICENCE = "None stated -- Nauru Bureau of Statistics publication, cited as such"
TABLES_URL = ("https://stats.gov.nr/download/49/2021/182/"
              "population-housing-census-2021-tables-vol1.xlsx")
PERSONS_URL = "https://stats.gov.nr/download/49/2021/358/person-tables-1-36.pdf"
REPORT_URL = ("https://stats.gov.nr/download/49/2021/359/"
              "nauru-2021-population-and-housing-census-analytical-report.pdf")
TABLES = f"{OFFICE}, 2021 Population and Housing Census Tables, Volume 1"
PERSONS = f"{OFFICE}, 2021 Population and Household Census, Persons Tabulations"

NATIONAL = 11_680
CITIZENS = 11_215
NATIONAL_MEDIAN = 21.6
# The census's districts by number, as it spells them; 15 is Location.
DISTRICTS = {1: "Yaren", 2: "Boe", 3: "Aiwo", 4: "Buada", 5: "Denigomodu", 6: "Nibok",
             7: "Uaboe", 8: "Baitsi", 9: "Ewa", 10: "Anetan", 11: "Anabar", 12: "Ijuw",
             13: "Anibare", 14: "Meneng", 15: "Location"}
LOCATION, HOME = 15, 5
ALIASES = {"Baitsi": "Baiti"}
ETHNIC = {"Kiribati": "I-Kiribati", "Vanuatu": "Ni-Vanuatu"}
# Table 19's columns after its total, in order.
RELIGIONS = ("No religion", "Nauru Congregational Church", "Catholic", "Assemblies of God",
             "Nauru Independent Church", "Pacific Light House", "Seventh-day Adventist",
             "Baptist", "Protestant", "Brethren Church", "Jehovah's Witnesses", "Hinduism",
             "Methodist Church", "Other religion", "Not stated")

CODE = re.compile(r"^\s*(\d{1,2})\s*-\s*([A-Za-z]+)")


def district_of(cell: Any) -> int | None:
    match = CODE.match(str(cell or ""))
    if not match:
        return None
    code = int(match.group(1))
    check(DISTRICTS.get(code, "").lower()[:4] == match.group(2).lower()[:4],
          f"nauru_census: {cell!r} is not district {code}")
    return code


def sheet(book, name: str) -> list[list[Any]]:
    check(name in book.sheetnames, f"nauru_census: the workbook has no sheet {name}")
    return [list(r) for r in book[name].iter_rows(values_only=True)]


def by_district(rows: list[list[Any]], width: int, what: str) -> dict[int, list[float]]:
    """{district: its first ``width`` figures} from rows labelled "N-Name"."""
    out: dict[int, list[float]] = {}
    for row in rows:
        code = district_of(row[0] if row else None)
        if code is None:
            continue
        figures = [number(c) or 0.0 for c in row[1:1 + width]]
        check(code not in out, f"nauru_census: {what} has two rows for district {code}")
        out[code] = figures
    check(set(out) == set(DISTRICTS), f"nauru_census: {what} lacks "
                                      f"{sorted(set(DISTRICTS) - set(out))}")
    return out


def header(rows: list[list[Any]], first: str) -> tuple[int, list[str]]:
    """The row whose second cell is "Total" and third ``first``, and its labels."""
    for i, row in enumerate(rows):
        cells = [str(c).strip() if c is not None else "" for c in row]
        if len(cells) > 2 and cells[1] == "Total" and cells[2].startswith(first):
            return i, cells
    raise SystemExit(f"nauru_census: no header starting {first!r}")


SHEETS = ("G-1", "I-1", "H-1", "M-1", "G-7")
# Table G-7's religions (everyone, whole country) that Table 19 has a column for.
IN_TABLE_19 = {"No Religion", "Nauruan Congregational", "Catholic", "Assemblies of God (AOG)",
               "Nauru Independent", "Pacific Light House", "Seven Day Adventist", "Baptist",
               "Protestant", "Brethren Church", "Jehovah's Witness", "Hinduism",
               "Methodist Church", "Other religion", "Do not wish to answer"}


def folded_churches(rows: list[list[Any]]) -> dict[str, float]:
    """Table G-7's churches that Table 19 has no column for, so counts as 'Other religion'."""
    counts: dict[str, float] = {}
    for row in rows:
        label = str(row[0] or "").strip() if row else ""
        value = number(row[1]) if len(row) > 1 else None
        if label and label != "TOTAL" and value is not None:
            counts[label] = value
    check(sum(counts.values()) == NATIONAL,
          f"nauru_census: Table G-7's religions add up to {sum(counts.values()):,}")
    return {k: v for k, v in counts.items() if k not in IN_TABLE_19 and v}


def read_tables(sheets: dict[str, list[list[Any]]]) -> dict[str, Any]:
    g1 = by_district(sheets["G-1"], 3, "Table G-1")
    total = sum(v[0] for v in g1.values())
    check(total == NATIONAL, f"nauru_census: Table G-1's districts add up to {total:,}")
    for code, (t, m, f) in g1.items():
        check(m + f == t, f"nauru_census: district {code}'s sexes do not make {t}")

    eth_rows = sheets["I-1"]
    _, labels = header(eth_rows, "Nauruan")
    groups = [ETHNIC.get(label, label) for label in labels[2:] if label]
    eth = by_district(eth_rows, 1 + len(groups), "Table I-1")
    for code, row in eth.items():
        check(row[0] == g1[code][0], f"nauru_census: Table I-1 counts district {code} at "
                                     f"{row[0]}, G-1 at {g1[code][0]}")
        check(sum(row[1:]) == row[0], f"nauru_census: district {code}'s ethnic groups add up "
                                      f"to {sum(row[1:])}, not {row[0]}")

    citizens = {code: row[1] for code, row in by_district(sheets["H-1"], 2,
                                                         "Table H-1").items()}
    check(sum(citizens.values()) == CITIZENS, "nauru_census: Table H-1's citizens do not "
                                              f"add up to {CITIZENS:,}")

    age_rows = sheets["M-1"]
    at, cells = header(age_rows, "1-")
    columns = {i: district_of(c) for i, c in enumerate(cells) if district_of(c)}
    check(set(columns.values()) == set(DISTRICTS), "nauru_census: Table M-1's districts")
    ages: dict[int, list[tuple[int, int | None, float]]] = {c: [] for c in DISTRICTS}
    for row in age_rows[at + 1:]:
        label = str(row[0] or "").strip()
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)|(\d+)\s*\+", label)
        if not match:
            continue
        low = int(match.group(1) or match.group(3))
        high = int(match.group(2)) if match.group(2) else None
        for i, code in columns.items():
            ages[code].append((low, high, number(row[i]) or 0.0))
    for code, groups15 in ages.items():
        check(groups15 and groups15[0][0] == 15 and groups15[-1][1] is None,
              f"nauru_census: Table M-1's groups for district {code} run "
              f"{groups15[:1]}..{groups15[-1:]}")
        check(sum(n for *_, n in groups15) <= g1[code][0],
              f"nauru_census: district {code} has more people aged 15+ than people")
    folded = folded_churches(sheets["G-7"])
    log(f"  Tables: {len(g1)} districts adding to {NATIONAL:,}; {len(groups)} ethnic groups; "
        f"Table G-7 churches without a Table 19 column: {folded}")
    return {"people": g1, "ethnic_groups": groups, "ethnicity": eth, "citizens": citizens,
            "ages15": ages, "folded": folded}


def median_of(people: float, groups15: list[tuple[int, int | None, float]]) -> float | None:
    """The median from everyone under 15 as one group and the five-year groups above."""
    under = people - sum(n for *_, n in groups15)
    if under >= people / 2:
        return None
    return median_from_groups([(0, 14, under)] + groups15)


NUMBER = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|-)$")


def religion_panel(lines: list[str]) -> list[str]:
    """Table 19's first panel: the fifteen district rows under the 11,215 citizens' row.

    pypdf gives a page's figures before its title, so the panel is the run of
    district rows that follows a "Total 11,215" row and is itself followed,
    before any other table's title, by Table 19's.
    """
    found = []
    for i, line in enumerate(lines):
        if line.split()[:2] != ["Total", f"{CITIZENS:,}"]:
            continue
        rows = []
        for row in lines[i + 1:]:
            if district_of(row) is None:
                break
            rows.append(row)
        rest = lines[i + 1 + len(rows):]
        title = next((ln for ln in rest if re.match(r"Table \d+\.", ln)), "")
        if [district_of(r) for r in rows] == sorted(DISTRICTS) and title.startswith("Table 19."):
            found.append(rows)
    check(len(found) == 1, f"nauru_census: {len(found)} panels of the citizens' fifteen "
                           f"districts under their {CITIZENS:,} total precede Table 19's title")
    return found[0]


def read_religion(pages: list[str], citizens: dict[int, float]) -> dict[int, dict[str, float]]:
    """{district: {religion: citizens}} from Persons Tabulations Table 19's first panel."""
    lines = [ln.strip() for page in pages for ln in page.splitlines() if ln.strip()]
    out: dict[int, dict[str, float]] = {}
    for line in religion_panel(lines):
        code = district_of(line)
        tokens = line.split()[1:]
        check(len(tokens) == 1 + len(RELIGIONS) and all(NUMBER.match(t) for t in tokens),
              f"nauru_census: Table 19 row {line!r}")
        figures = [0.0 if t == "-" else float(t.replace(",", "")) for t in tokens]
        check(sum(figures[1:]) == figures[0],
              f"nauru_census: Table 19's district {code} adds up to {sum(figures[1:])}, "
              f"not {figures[0]}")
        check(figures[0] == citizens[code],
              f"nauru_census: Table 19 counts district {code}'s citizens at {figures[0]}, "
              f"Table H-1 at {citizens[code]}")
        out[code] = dict(zip(RELIGIONS, figures[1:]))
    check(set(out) == set(DISTRICTS), f"nauru_census: Table 19 lacks "
                                      f"{sorted(set(DISTRICTS) - set(out))}")
    log(f"  Persons Tabulations: Table 19's religion of {CITIZENS:,} citizens by district")
    return out


def merged(code: int, figures: dict[int, Any]) -> Any:
    """A district's figures, Location's added to Denigomodu's."""
    if code != HOME:
        return figures[code]
    a, b = figures[HOME], figures[LOCATION]
    if isinstance(a, dict):
        return {k: a.get(k, 0) + b.get(k, 0) for k in set(a) | set(b)}
    if a and isinstance(a[0], tuple):
        return [(lo, hi, n + m) for (lo, hi, n), (_, _, m) in zip(a, b)]
    return [x + y for x, y in zip(a, b)]


LANGUAGE_GAP = ("The 2021 census asked whether each person speaks Nauruan and publishes the "
                "answer by age and citizenship for the whole country only (Persons "
                "Tabulations, Table 28); it publishes no language by district. The 2011 "
                "census's languages are likewise national (Report, Tables 30-31).")


def fields_for(code: int, tables: dict[str, Any], religion: dict[int, dict[str, float]]
               ) -> dict[str, Any]:
    total, male, female = merged(code, tables["people"])
    groups15 = merged(code, tables["ages15"])
    ethnic = dict(zip(tables["ethnic_groups"], merged(code, tables["ethnicity"])[1:]))
    faith = merged(code, religion)
    citizens = sum(faith.values())
    folded = tables["folded"]
    other = (f" Table 19 has no column for the churches Table G-7 names for the whole "
             f"country's {NATIONAL:,} people as {', '.join(folded)} ({int(sum(folded.values())):,} "
             f"people in all), so their members are in its 'Other religion'."
             if folded else "")
    location = ""
    if code == HOME:
        loc = tables["people"][LOCATION][0]
        location = (f" Denigomodu's polygon holds the district's own {int(total - loc):,} "
                    f"people and the {int(loc):,} of Location, the settlement inside it "
                    f"that the census counts apart.")
    fields: dict[str, Any] = {
        "population": population(total, YEAR, f"{TABLES} (Table G-1)"),
        "sex_ratio": measure(sex_ratio(male, female), unit="males_per_100_females", year=YEAR,
                             source=f"{TABLES} (Table G-1)"),
        "sex_ratio_note": f"Males per 100 females, 2021 census (Table G-1).{location}",
        "ethnicity": shares_of(ethnic, total),
        "ethnicity_year": YEAR,
        "ethnicity_note": (f"Ethnicity, 2021 census (Table I-1): shares of the {int(total):,} "
                           f"people counted here.{location}"),
        "religion": shares_of(faith, citizens),
        "religion_year": YEAR,
        "religion_note": (f"Religion of the Nauruan population -- citizens and dual citizens, "
                          f"{int(citizens):,} of the {int(total):,} people here -- 2021 census "
                          f"(Persons Tabulations, Table 19); the census publishes religion for "
                          f"everyone only for the whole country (Table G-7). 'Not stated' is "
                          f"its 'Do not wish to answer'.{other}{location}"),
        "language": gap(NOT_AVAILABLE, LANGUAGE_GAP),
    }
    if location:
        fields["population_note"] = f"2021 census (Table G-1).{location}"
    median = median_of(total, groups15)
    if median is not None:
        fields["median_age"] = measure(round(median, 1), unit="years", year=YEAR,
                                       source=f"{TABLES} (Tables G-1, M-1)")
        fields["median_age_note"] = (
            "Interpolated from five-year age groups: the census publishes ages by district "
            "only for people aged 15 and over (Table M-1), so everyone under 15 -- the "
            "district's total (Table G-1) less those -- is one group, and the median falls "
            f"above it.{location}")
    else:
        fields["median_age"] = gap(NOT_AVAILABLE, (
            "Half or more of this district's people are under 15, and the census publishes "
            "their ages only as one group here (Tables G-1, M-1), so the median cannot be "
            "placed."))
    return fields


SOURCES = [
    {"field": "population/sex_ratio/ethnicity/median_age", "name": TABLES, "url": TABLES_URL,
     "year": YEAR, "license": LICENCE},
    {"field": "religion", "name": PERSONS, "url": PERSONS_URL, "year": YEAR,
     "license": LICENCE},
]


def build(tables: dict[str, Any], religion: dict[int, dict[str, float]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    people = sum(v[0] for v in tables["people"].values())
    under = people - sum(n for groups in tables["ages15"].values() for *_, n in groups)
    national = [(0, 14, under)] + [
        (lo, hi, sum(tables["ages15"][c][i][2] for c in DISTRICTS))
        for i, (lo, hi, _) in enumerate(tables["ages15"][1])]
    computed = median_from_groups(national)
    check(computed is not None and abs(computed - NATIONAL_MEDIAN) <= 0.5,
          f"nauru_census: the national median from these groups is {computed}, the report's "
          f"{NATIONAL_MEDIAN}")
    log(f"  national median from the same groups: {computed:.1f} (report: {NATIONAL_MEDIAN})")
    records = []
    rows = {DISTRICTS[c]: (DISTRICTS[c], "") for c in DISTRICTS if c != LOCATION}
    codes = {name: c for c, name in DISTRICTS.items()}
    for level, units in (("admin1", admin1), ("admin2", admin2)):
        parents = {u["id"]: u["name"] for u in admin1} if level == "admin2" else {}
        bound = bind_level(rows, units, parents, ALIASES)
        for name, unit in bound.items():
            records.append(unit_record("NRU", name, unit["name"], unit, level, None, SOURCES,
                                       **fields_for(codes[name], tables, religion)))
    return records


def pages_of(url: str) -> list[str]:
    from pypdf import PdfReader  # noqa: PLC0415
    blob = http_get(url, binary=True, timeout=600)
    check(isinstance(blob, bytes) and blob[:5] == b"%PDF-", f"nauru_census: {url} is no PDF")
    return [(page.extract_text() or "") for page in PdfReader(io.BytesIO(blob)).pages]


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("nauru_census: 2021 census tables and persons tabulations")
    book = workbook(TABLES_URL)
    tables = read_tables({name: sheet(book, name) for name in SHEETS})
    religion = read_religion(pages_of(PERSONS_URL), tables["citizens"])
    records = build(tables, religion, load_units("NRU", "admin1"), load_units("NRU", "admin2"))
    log("  " + summarise(records))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
