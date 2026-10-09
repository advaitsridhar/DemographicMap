#!/usr/bin/env python3
"""Qatar's eight municipalities in the 2020 census: people, sex and median age.

The Planning and Statistics Authority publishes, on the national open-data
portal (data.gov.qa, OpenDataSoft), the population of every municipality by
sex and age group -- *Males Population by Municipality and Age Groups -
December 2020* and its *Females* twin. Despite the title, each holds a row
for every year from 2014 to 2023; the 2020 rows are the census of December
2020 (the census night the portal's household tables are tabulated for),
and those are what is read.

**What is written**, for each municipality: its 2020 census population, males
per hundred females, and the median age, interpolated within the age group
that holds the middle person (single years below five, then five-year groups).

**What is not, and why.** The portal publishes no municipality's people by
nationality (Qatari or not), religion or language: its 2020 census tables
give municipalities by sex, age and household type, and the nationality
tables in its catalogue are vital statistics (births, deaths, marriages).
Each municipality says so on those three fields.

**The zones** (the map's second level) are written as gaps, each saying why.
The portal's only table of people by zone gives every zone the same count in
each year from 2015 to 2019, and those counts make no census's total (2010,
2015 or 2020), so they can be neither dated nor checked; it also holds no
zone's people by sex, age, nationality, religion or language. The zone table
is read on every run and its total measured: should it ever make a census's
count, the run stops, for the zones to be bound instead.

**Binding.** The portal spells three municipalities its own way ("AL Khor",
"Al Dayyan", "Umm Salal"); those are declared below against the boundary
file's labels, the rest agree once folded. Every drawn municipality must be
bound, and none twice.

**Checks** (any failure stops the run and nothing is written): each
municipality has one count per age group and sex, running from 0 without a
gap; the municipalities make the census's national count.

Usage:
    python -m scripts.fetch_census.qatar_census
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, write_json
from .west_asia_common import check, key, median_age, ods_records, sex_ratio, units

ISO3 = "QAT"
OUT = "qatar_census.json"
BASE = "https://www.data.gov.qa"
MALES = "males-population-by-municipality-and-age-groups-december-2020"
FEMALES = "females-population-by-municipality-and-age-groups-december-2020"
YEAR = 2020
# The 2020 census's count of the whole country (Planning and Statistics
# Authority, Census 2020 results): the municipalities must make it.
NATIONAL = 2_846_118
# Above this many men per woman a municipality's ratio is explained in its
# note as the census's count (Al Sheehaniya's is over eleven).
SKEWED = 3
SOURCE = ("Planning and Statistics Authority (Qatar), Census 2020: population by "
          "municipality, sex and age group")
URL = f"{BASE}/explore/dataset/{MALES}/"
LICENCE = "Qatar Open Data Portal terms (open government data)"
# The portal's spelling -> the boundary file's label.
ALIASES = {
    "AL Khor": "Al Khor and Al Thakhira",
    "Al Khor": "Al Khor and Al Thakhira",
    "Al Dayyan": "Al Daayen",
    "Umm Salal": "Umm Slal",
}
# What the portal does not publish by municipality, as its catalogue showed
# on 4 and 9 October 2026 (searches for population, census, religion and
# nationality; probes c500305, ecba12f and 431d457): no table of people by
# nationality, religion or language for a municipality. Its nationality
# tables are of births, deaths and marriages, and its "Population and Labour
# Force by Municipality" counts people by labour-force status only.
CATALOGUE = ("Qatar's open-data portal (data.gov.qa), where the Planning and Statistics "
             "Authority publishes the 2020 census by municipality, gives municipalities' "
             "people by sex, age and household type only")
NATIONALITY_WHY = (f"{CATALOGUE}; it publishes no municipality's people by nationality "
                   "(Qatari or not), whose tables there are of births, deaths and marriages.")
RELIGION_WHY = f"{CATALOGUE}; it publishes no table of religion by municipality."
LANGUAGE_WHY = f"{CATALOGUE}; it publishes no table of language by municipality."
# The portal's only table of people by zone (probe ecba12f lists it; its 552
# rows were read on 9 October 2026): 92 zones a year, 2014-2019.
ZONES = "population-area-and-population-density-per-square-kilometers-by-zone"
ZONES_TITLE = "Population, Area and Population Density Per Square Kilometers By Zone"
# Each census's count of the whole country (Planning and Statistics Authority):
# a zone table that made one of them could be dated and bound.
CENSUSES = {2010: 1_699_435, 2015: 2_404_776, 2020: NATIONAL}
ZONE_CATALOGUE = ("Qatar's open-data portal (data.gov.qa), where the Planning and Statistics "
                  "Authority publishes its tables, counts zones' people alone, beside each "
                  "zone's area, and municipalities' people by sex, age and household type")
ZONE_AGE_WHY = f"{ZONE_CATALOGUE}: no zone's people are published by sex or age."
ZONE_NATIONALITY_WHY = (f"{ZONE_CATALOGUE}: no zone's people are published by nationality "
                        "(Qatari or not).")
ZONE_RELIGION_WHY = f"{ZONE_CATALOGUE}: no zone's religion is published."
ZONE_LANGUAGE_WHY = f"{ZONE_CATALOGUE}: no zone's language is published."
CLOSED = re.compile(r"^(\d+)\s*-\s*(\d+)$")
SINGLE = re.compile(r"^(\d+)$")
OPEN = re.compile(r"^(\d+)\s*(?:\+|and\s+over|or\s+more)$", re.I)


def band(label: str) -> tuple[int, int | None]:
    text = str(label).strip()
    if m := CLOSED.match(text):
        return int(m.group(1)), int(m.group(2))
    if m := SINGLE.match(text):
        return int(m.group(1)), int(m.group(1))
    if m := OPEN.match(text):
        return int(m.group(1)), None
    raise SystemExit(f"qatar_census: age group {label!r}")


def counts(rows: list[dict[str, Any]], what: str) -> dict[str, dict[tuple[int, int | None], float]]:
    """municipality -> (from, to) -> people, for the census year only."""
    out: dict[str, dict[tuple[int, int | None], float]] = defaultdict(dict)
    years = set()
    for row in rows:
        year = str(row.get("years") or row.get("year") or "")[:4]
        years.add(year)
        if year != str(YEAR):
            continue
        where = str(row.get("municipality") or "").strip()
        group = band(row.get("age_groups_in_years"))
        check(group not in out[where], f"qatar_census: {what}: {where} {group} twice")
        value = row.get("value")
        check(isinstance(value, (int, float)), f"qatar_census: {what}: {where} {group}: {value!r}")
        out[where][group] = float(value)
    check(str(YEAR) in years, f"qatar_census: {what}: no {YEAR} rows (years {sorted(years)})")
    return out


def contiguous(groups: list[tuple[int, int | None, float]], where: str) -> None:
    edge = 0
    for low, high, _n in groups:
        check(low == edge, f"qatar_census: {where}: age groups break at {edge}")
        edge = high + 1 if high is not None else -1
    check(groups and groups[-1][1] is None, f"qatar_census: {where}: no open last age group")


def build(male_rows: list[dict[str, Any]], female_rows: list[dict[str, Any]],
          admin1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    men_by, women_by = counts(male_rows, MALES), counts(female_rows, FEMALES)
    check(set(men_by) == set(women_by), f"qatar_census: municipalities differ: "
                                        f"{sorted(set(men_by) ^ set(women_by))}")
    labels = {u["name"]: u for u in admin1}
    by_key = {key(lb): lb for lb in labels}
    out: list[dict[str, Any]] = []
    bound: set[str] = set()
    made = 0.0
    all_men = sum(sum(v.values()) for v in men_by.values())
    all_women = sum(sum(v.values()) for v in women_by.values())
    for where in sorted(men_by):
        check(set(men_by[where]) == set(women_by[where]),
              f"qatar_census: {where}: the sexes' age groups differ")
        both = sorted((lo, hi, men_by[where][(lo, hi)] + women_by[where][(lo, hi)])
                      for lo, hi in men_by[where])
        contiguous(both, where)
        men, women = sum(men_by[where].values()), sum(women_by[where].values())
        total = men + women
        made += total
        label = ALIASES.get(where) or by_key.get(key(where))
        check(label in labels, f"qatar_census: no drawn municipality for {where!r}")
        check(label not in bound, f"qatar_census: {label} bound twice")
        bound.add(label)
        population = measure(total, year=YEAR, source=SOURCE)
        population["note"] = (f"The 2020 census count: {men:,.0f} men and {women:,.0f} "
                              f"women.")
        rec = record(
            f"QAT-CEN2020-{key(label)}", label, level="admin1", parent=ISO3, country=ISO3,
            match_by="shape_id", shape_id=labels[label]["id"],
            aliases=[where] if where != label else None,
            population=population,
            sex_ratio=sex_ratio(men, women, year=YEAR, source=SOURCE),
            sex_ratio_note=(f"Males per 100 females in the 2020 census: {men:,.0f} men and "
                            f"{women:,.0f} women."
                            + (f" A ratio this high is the census's count, not an error: "
                               f"Qatar's 2020 census counts {all_men:,.0f} men and "
                               f"{all_women:,.0f} women in all "
                               f"({100 * all_men / all_women:.0f} men to every hundred "
                               f"women)."
                               if women and men > SKEWED * women else "")),
            median_age=median_age(both, year=YEAR, source=SOURCE),
            median_age_note=("Interpolated within the age group holding the middle person, "
                             "from the 2020 census's count of the municipality by age group "
                             "(single years under five, five-year groups above)."),
            religion=gap(NOT_AVAILABLE, RELIGION_WHY),
            ethnicity=gap(NOT_AVAILABLE, NATIONALITY_WHY),
            language=gap(NOT_AVAILABLE, LANGUAGE_WHY),
            sources=[{"field": "population/median_age/sex_ratio", "name": SOURCE, "url": URL,
                      "year": YEAR, "license": LICENCE}])
        out.append(rec)
        log(f"    {where} -> {label}: {total:,.0f}, median {rec['median_age']['value']}, "
            f"{rec['sex_ratio']['value']} M/100F")
    check(bound == set(labels), f"qatar_census: drawn but not in the table: "
                                f"{sorted(set(labels) - bound)}")
    check(round(made) == NATIONAL, f"qatar_census: the municipalities make {made:,.0f}, the "
                                   f"census counted {NATIONAL:,}")
    log(f"  census 2020: {made:,.0f} people in {len(out)} municipalities")
    return out


def zone_order(zone: str) -> tuple[int, str]:
    return (int(zone), "") if zone.isdigit() else (10 ** 6, zone)


def zone_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """What the zone table holds for its latest year: the years that repeat
    that year's counts, their total and the zones given no count. A total that
    makes a census's count stops the run: the zones could then be bound."""
    by_year: dict[str, dict[str, Any]] = defaultdict(dict)
    for r in rows:
        by_year[str(r.get("year"))][str(r.get("number_of_zone"))] = r.get("population")
    check(by_year, f"qatar_census: {ZONES} is empty")
    latest = max(by_year)
    same = sorted(y for y, counts in by_year.items() if counts == by_year[latest])
    total = round(sum(v for v in by_year[latest].values() if v is not None))
    missing = sorted((z for z, v in by_year[latest].items() if v is None), key=zone_order)
    for year, count in CENSUSES.items():
        check(total != count, f"qatar_census: the zone table's {latest} counts make "
                              f"{total:,}, the {year} census's count: bind the zones")
    return {"years": same, "total": total, "missing": missing, "zones": len(by_year[latest])}


def zone_why(table: dict[str, Any]) -> str:
    years, missing = table["years"], table["missing"]
    when = (f"the same count for every year from {years[0]} to {years[-1]}" if len(years) > 1
            else f"its count for {years[0]}")
    censuses = ", ".join(f"{n:,} in the {y} census" for y, n in sorted(CENSUSES.items()))
    gaps = ""
    if missing:
        listed = (", ".join(missing[:-1]) + " and " + missing[-1]) if len(missing) > 1 \
            else missing[0]
        gaps = f", and none for zone{'s' if len(missing) > 1 else ''} {listed}"
    return (f"The Planning and Statistics Authority's only table of people by zone, on "
            f"Qatar's open-data portal (data.gov.qa, '{ZONES_TITLE}'), gives each zone "
            f"{when}: {table['total']:,} people in all, which is no census's count ("
            f"{censuses}){gaps}. A table that makes no census's count can be neither dated "
            f"nor checked, so no zone's figure is written.")


def zones(rows: list[dict[str, Any]], admin2: list[dict[str, Any]],
          admin1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every drawn zone, with why each of its fields is empty."""
    table = zone_table(rows)
    why = zone_why(table)
    parents = {u["id"]: u["name"] for u in admin1}
    out = [record(
        f"QAT-ZONE-{unit['name']}-{unit['id'][-6:]}", unit["name"], level="admin2",
        parent=ISO3, country=ISO3, parent_name=parents.get(unit.get("parent")),
        match_by="shape_id", shape_id=unit["id"],
        population=gap(NOT_AVAILABLE, why),
        median_age=gap(NOT_AVAILABLE, ZONE_AGE_WHY),
        sex_ratio=gap(NOT_AVAILABLE, ZONE_AGE_WHY),
        religion=gap(NOT_AVAILABLE, ZONE_RELIGION_WHY),
        ethnicity=gap(NOT_AVAILABLE, ZONE_NATIONALITY_WHY),
        language=gap(NOT_AVAILABLE, ZONE_LANGUAGE_WHY)) for unit in admin2]
    log(f"  zone table: {table['zones']} zones, {table['total']:,} people in "
        f"{'-'.join(table['years'][::max(1, len(table['years']) - 1)])}, no count for "
        f"{len(table['missing'])}; {len(out)} drawn zones written as gaps")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    admin1 = units(ISO3, "admin1")
    rows = build(ods_records(BASE, MALES), ods_records(BASE, FEMALES), admin1)
    rows += zones(ods_records(BASE, ZONES), units(ISO3, "admin2"), admin1)
    write_json(PROCESSED / OUT, rows)
    log(f"  wrote {OUT} ({len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
