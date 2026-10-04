#!/usr/bin/env python3
"""Mongolia: population, median age and sex ratio for every soum and aimag, from the NSO.

The National Statistics Office's statistical database (data.1212.mn, a
PxWeb API) publishes the resident population of every soum and every
district of Ulaanbaatar each year, from the population register, in two
tables under *Regional development / Population and household*:

* ``DT_NSO_0300_068V2`` -- RESIDENT POPULATION IN MONGOLIA, by sex, by soum
  and district, and by year: men and women;
* ``DT_NSO_0300_067V2`` -- RESIDENT POPULATION IN MONGOLIA, by age group, soum
  and district, and by year: fourteen five-year groups from 0-4 to 65-69 and
  an open 70+.

Both are read for the latest year the office serves (the query asks for the
"top" year rather than naming one), every one of their 369 areas: the
nation, the five regions, the 21 aimags and the capital, 330 soums and
Ulaanbaatar's nine districts.

**What is written.** For every soum and district, and every aimag and the
capital: the population (men and women together), the sex ratio (men per
hundred women) and the median age. The median is **interpolated within the
five-year group** that holds the middle person, because nothing finer is
published below the nation (the single-year table, DT_NSO_0300_001V2, is
national); every note says so. The open 70+ group never holds a median
here, and a unit whose median it would hold is refused.

**Binding.** The office's codes are the hierarchy -- an aimag is three
digits, its soums five digits beginning with them -- and its names are
Cyrillic in the Mongolian tree and romanised in the English one. The aimag
is matched to the drawn first-level unit by its English name; the soum to
the drawn second-level unit inside that aimag by its Cyrillic name, folded
the way ``mongolia.py`` folds the census books' soum names onto the
boundary file's own romanisation ("Баян-Өндөр" and "Bayan-O'ndor" both fold
to *baianondor*). Every one of the 339 drawn soums and districts must be
matched exactly once and every soum the office lists must find its
polygon, or nothing is written. Records are bound by shape id.

**Checks**, each a refusal: in every area the age groups add up to the
total and men and women to the total, and the two tables agree on it; the
soums of every aimag add up to the aimag, and the aimags to the nation.

Usage:
    python -m scripts.fetch_census.mongolia_ages
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, measure, record, write_json
from .east_asia_common import drawn, grouped_median, sex_ratio
from .mongolia import fold, soum_key
from .pxweb import http_json, unstack

OUT = "mongolia_ages.json"
API = "https://data.1212.mn/api/v1/{lang}/NSO/Regional%20development/Population%20and%20household"
SEX_TABLE = "DT_NSO_0300_068V2.px"
AGE_TABLE = "DT_NSO_0300_067V2.px"
PAGE = "https://www.1212.mn/en/statistic/statcate/573051"
NSO = "National Statistics Office of Mongolia"
SEX_SOURCE = (f"{NSO}, RESIDENT POPULATION IN MONGOLIA, by sex, by soum and district "
              "(data.1212.mn, DT_NSO_0300_068V2)")
AGE_SOURCE = (f"{NSO}, RESIDENT POPULATION IN MONGOLIA, by age group, soum and district "
              "(data.1212.mn, DT_NSO_0300_067V2)")
LICENCE = f"Official statistics of the {NSO}, cited as published"

# The variables' codes are the Mongolian words, the same in both trees.
REGION, YEAR_VAR, SEX_VAR, AGE_VAR = "Бүс", "Он", "Хүйс", "Насны бүлэг"
TOTAL = "0"

# An age group's label is "    0-4" ... "    65-69", "    70+", and "Total".
OPEN_TOP = 70


def query(variables: dict[str, list[str] | str]) -> dict[str, Any]:
    """A PxWeb query: "*" for every value, "top" for the latest year."""
    out = []
    for code, values in variables.items():
        if values == "*":
            out.append({"code": code, "selection": {"filter": "all", "values": ["*"]}})
        elif values == "top":
            out.append({"code": code, "selection": {"filter": "top", "values": ["1"]}})
        else:
            out.append({"code": code, "selection": {"filter": "item", "values": values}})
    return {"query": out, "response": {"format": "json-stat2"}}


def group_bounds(label: str) -> tuple[int, int | None] | None:
    """(lower bound, width) of an age group label, None for the total."""
    text = label.strip()
    if text.lower() in ("total", "бүгд", "нийт", "нийт дүн"):
        return None
    if text.endswith("+"):
        return int(text[:-1]), None
    low, high = text.split("-")
    return int(low), int(high) - int(low) + 1


def read_sex(cells: list[tuple[dict[str, tuple[str, str]], float]]
             ) -> tuple[str, dict[str, dict[str, float]]]:
    """(year, {area code: {"total", "men", "women": people}})."""
    out: dict[str, dict[str, float]] = defaultdict(dict)
    years = set()
    for key, value in cells:
        years.add(key[YEAR_VAR][1])
        sex = {"0": "total", "1": "men", "2": "women"}[key[SEX_VAR][0]]
        out[key[REGION][0]][sex] = value
    if len(years) != 1:
        raise SystemExit(f"mongolia_ages: the sex table answered years {sorted(years)}")
    return years.pop(), dict(out)


def read_ages(cells: list[tuple[dict[str, tuple[str, str]], float]]
              ) -> tuple[str, dict[str, dict[str, Any]]]:
    """(year, {area code: {"total": people, "groups": [(lower, width, people)]}})."""
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"groups": []})
    years = set()
    for key, value in cells:
        years.add(key[YEAR_VAR][1])
        bounds = group_bounds(key[AGE_VAR][1])
        area = out[key[REGION][0]]
        if bounds is None:
            area["total"] = value
        else:
            area["groups"].append((bounds[0], bounds[1], value))
    if len(years) != 1:
        raise SystemExit(f"mongolia_ages: the age table answered years {sorted(years)}")
    return years.pop(), dict(out)


def check(sex: dict[str, dict[str, float]], ages: dict[str, dict[str, Any]],
          aimags: dict[str, str], soums: dict[str, str]) -> None:
    """Every area adds up, both tables agree, soums make their aimag and
    aimags the nation."""
    for code, row in sex.items():
        if row.get("men", 0) + row.get("women", 0) != row.get("total"):
            raise SystemExit(f"mongolia_ages: {code}: men and women do not make the total")
        age = ages.get(code)
        if age is None:
            raise SystemExit(f"mongolia_ages: {code} has no row in the age table")
        if sum(n for _, _, n in age["groups"]) != age.get("total"):
            raise SystemExit(f"mongolia_ages: {code}: the age groups do not make the total")
        if age["total"] != row["total"]:
            raise SystemExit(f"mongolia_ages: {code}: the age table counts {age['total']:,.0f}, "
                             f"the sex table {row['total']:,.0f}")
    for aimag in aimags:
        parts = [c for c in soums if c.startswith(aimag)]
        for what in ("total", "men", "women"):
            summed = sum(sex[c][what] for c in parts)
            if summed != sex[aimag][what]:
                raise SystemExit(f"mongolia_ages: {aimags[aimag]}'s soums hold {summed:,.0f} "
                                 f"{what} against its {sex[aimag][what]:,.0f}")
    summed = sum(sex[a]["total"] for a in aimags)
    if summed != sex[TOTAL]["total"]:
        raise SystemExit(f"mongolia_ages: the aimags hold {summed:,.0f}, the nation "
                         f"{sex[TOTAL]['total']:,.0f}")
    log(f"  {len(aimags)} aimags and {len(soums)} soums add up, in both tables; "
        f"{sex[TOTAL]['total']:,.0f} people")


def hierarchy(labels_en: dict[str, str], labels_mn: dict[str, str]
              ) -> tuple[dict[str, str], dict[str, str]]:
    """({aimag code: English name}, {soum code: Cyrillic name}) from the
    region variable's codes: three digits an aimag or the capital, five a
    soum or a district inside the aimag its first three name."""
    aimags = {c: labels_en[c] for c in labels_en if len(c) == 3 and c.isdigit()}
    soums = {c: labels_mn[c] for c in labels_mn if len(c) == 5 and c.isdigit()}
    orphans = [c for c in soums if c[:3] not in aimags]
    if orphans:
        raise SystemExit(f"mongolia_ages: soums under no aimag: {orphans}")
    return aimags, soums


def bind(aimags: dict[str, str], soums: dict[str, str], admin1: list[dict[str, Any]],
         admin2: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]],
                                                dict[str, dict[str, Any]]]:
    """({aimag code: drawn unit}, {soum code: drawn unit}), one to one."""
    by_key = {}
    for unit in admin1:
        key = fold(unit["name"])
        if key in by_key:
            raise SystemExit(f"mongolia_ages: two drawn aimags fold to {key}")
        by_key[key] = unit
    # The office's English names and the boundary file's differ in places
    # ("Khuvsgul" against "Hovsgel", "Bayan-Ulgii" against "Bayan-Ölgii"); the
    # English names mongolia.py keeps for its books close those.
    from .mongolia import AIMAGS
    for drawn_name, (english, _) in AIMAGS.items():
        unit = next((u for u in admin1 if u["name"] == drawn_name), None)
        if unit is not None:
            by_key.setdefault(fold(english), unit)
    aimag_units: dict[str, dict[str, Any]] = {}
    for code, name in aimags.items():
        unit = by_key.get(fold(name))
        if unit is None:
            raise SystemExit(f"mongolia_ages: no drawn aimag for {name!r} ({code})")
        aimag_units[code] = unit
    if len({u["id"] for u in aimag_units.values()}) != len(aimag_units):
        raise SystemExit("mongolia_ages: two aimags bound to one polygon")
    drawn_soums: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for unit in admin2:
        key = soum_key(unit["name"])
        if key in drawn_soums[unit.get("parent")]:
            raise SystemExit(f"mongolia_ages: two drawn soums fold to {key}")
        drawn_soums[unit.get("parent")][key] = unit
    soum_units: dict[str, dict[str, Any]] = {}
    unmatched = []
    for code, name in soums.items():
        parent = aimag_units[code[:3]]["id"]
        unit = drawn_soums[parent].get(soum_key(name))
        if unit is None:
            unmatched.append(f"{name} ({code}, {aimags[code[:3]]})")
            continue
        soum_units[code] = unit
    if unmatched:
        raise SystemExit(f"mongolia_ages: soums with no drawn polygon: {unmatched}")
    ids = [u["id"] for u in soum_units.values()]
    if len(set(ids)) != len(ids):
        raise SystemExit("mongolia_ages: two soums bound to one polygon")
    missing = sorted(u["name"] for u in admin2 if u["id"] not in set(ids))
    if missing:
        raise SystemExit(f"mongolia_ages: drawn soums the office does not list: {missing}")
    return aimag_units, soum_units


def unit_record(unit: dict[str, Any], level: str, parent: str, year: int,
                sex: dict[str, float], age: dict[str, Any], what: str) -> dict[str, Any]:
    median = grouped_median(age["groups"])
    note = (f"{NSO}: the resident population of {what} at the end of {year}, by five-year "
            f"age group (0-4 to 65-69, and 70 and over); the median is interpolated within "
            f"the five-year group that holds the middle person, because the office publishes "
            f"nothing finer below the nation.")
    return record(
        f"MNG-{unit['id']}", unit["name"], level=level, parent=parent, country="MNG",
        match_by="shape_id", shape_id=unit["id"],
        population=measure(int(sex["total"]), year=year, source=SEX_SOURCE),
        median_age=measure(median, unit="years", year=year, source=AGE_SOURCE),
        median_age_note=note,
        sex_ratio=sex_ratio(sex["men"], sex["women"], year=year, source=SEX_SOURCE),
        sex_ratio_note=f"{int(sex['men']):,} men and {int(sex['women']):,} women.",
        sources=[{"field": "population/sex_ratio", "name": SEX_SOURCE, "url": PAGE,
                  "year": year, "license": LICENCE},
                 {"field": "median_age", "name": AGE_SOURCE, "url": PAGE, "year": year,
                  "license": LICENCE}])


def build(sex_payload: dict[str, Any], age_payload: dict[str, Any],
          labels_en: dict[str, str], labels_mn: dict[str, str],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sex_year, sex = read_sex(unstack(sex_payload))
    age_year, ages = read_ages(unstack(age_payload))
    if sex_year != age_year:
        raise SystemExit(f"mongolia_ages: the tables are for {sex_year} and {age_year}")
    year = int(sex_year)
    aimags, soums = hierarchy(labels_en, labels_mn)
    check(sex, ages, aimags, soums)
    aimag_units, soum_units = bind(aimags, soums, admin1, admin2)
    records = []
    for code, unit in sorted(aimag_units.items()):
        records.append(unit_record(unit, "admin1", "MNG", year, sex[code], ages[code],
                                   "this aimag"))
    for code, unit in sorted(soum_units.items()):
        what = "this district" if aimags[code[:3]] == "Ulaanbaatar" else "this soum"
        records.append(unit_record(unit, "admin2", f"MNG-{aimag_units[code[:3]]['id']}",
                                   year, sex[code], ages[code], what))
    medians = [r["median_age"]["value"] for r in records if r["level"] == "admin2"]
    log(f"  {year}: {len(aimag_units)} aimags and {len(soum_units)} soums written; soum "
        f"medians {min(medians):.1f}-{max(medians):.1f}")
    return records


def diagnose(years: int, labels_en: dict[str, str]) -> None:
    """For each of the latest years: every area whose two tables disagree,
    and each aimag's total against its soums' in each table."""
    base = API.format(lang="en")
    # The year variable's codes are blank but for the latest year's in both
    # tables, so "top" is the one selection that reaches more than one.
    top = {"filter": "top", "values": [str(years)]}
    sex = http_json(f"{base}/{SEX_TABLE}", {"query": [
        {"code": SEX_VAR, "selection": {"filter": "item", "values": [TOTAL]}},
        {"code": REGION, "selection": {"filter": "all", "values": ["*"]}},
        {"code": YEAR_VAR, "selection": top}], "response": {"format": "json-stat2"}})
    age = http_json(f"{base}/{AGE_TABLE}", {"query": [
        {"code": AGE_VAR, "selection": {"filter": "all", "values": ["*"]}},
        {"code": REGION, "selection": {"filter": "all", "values": ["*"]}},
        {"code": YEAR_VAR, "selection": top}], "response": {"format": "json-stat2"}})
    totals: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    groups: dict[tuple[str, str], float] = defaultdict(float)
    for key, value in unstack(sex):
        totals[(key[YEAR_VAR][1], key[REGION][0])]["sex"] = value
    for key, value in unstack(age):
        where = (key[YEAR_VAR][1], key[REGION][0])
        if group_bounds(key[AGE_VAR][1]) is None:
            totals[where]["age"] = value
        else:
            groups[where] += value
    for year in sorted({y for y, _ in totals}, reverse=True):
        rows = {c: v for (y, c), v in totals.items() if y == year}
        differ = [c for c, v in rows.items() if v.get("sex") != v.get("age")]
        unsummed = [c for c in rows if rows[c].get("age") is not None
                    and groups[(year, c)] != rows[c]["age"]]
        log(f"  {year}: {len(rows)} areas; the tables disagree on {len(differ)}; the age "
            f"groups miss the age total in {len(unsummed)}")
        for code in sorted(differ, key=lambda c: (len(c), c))[:60]:
            v = rows[code]
            log(f"    {code} {labels_en.get(code, '?')}: sex table {v.get('sex')}, age table "
                f"{v.get('age')}")
        for aimag in sorted(c for c in rows if len(c) == 3):
            for table in ("sex", "age"):
                summed = sum(rows[c].get(table) or 0 for c in rows
                             if len(c) == 5 and c.startswith(aimag))
                if summed != rows[aimag].get(table):
                    log(f"    {aimag} {labels_en.get(aimag)}: {table} table {rows[aimag].get(table)}"
                        f", its soums {summed}")


def labels(lang: str, table: str) -> dict[str, str]:
    meta = http_json(f"{API.format(lang=lang)}/{table}")
    var = next((v for v in meta.get("variables", []) if v.get("code") == REGION), None)
    if var is None:
        raise SystemExit(f"mongolia_ages: {table} ({lang}) has no {REGION} variable")
    return dict(zip(var["values"], var["valueTexts"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diagnose", type=int, metavar="YEARS", default=0,
                    help="print where the two tables disagree over the latest YEARS years "
                         "and stop")
    args = ap.parse_args()
    log(f"mongolia_ages: {SEX_SOURCE}; {AGE_SOURCE}")
    labels_en, labels_mn = labels("en", SEX_TABLE), labels("mn", SEX_TABLE)
    if args.diagnose:
        diagnose(args.diagnose, labels_en)
        return 0
    if labels("mn", AGE_TABLE).keys() != labels_mn.keys():
        raise SystemExit("mongolia_ages: the two tables list different areas")
    base = API.format(lang="en")
    sex_payload = http_json(f"{base}/{SEX_TABLE}",
                            query({SEX_VAR: "*", REGION: "*", YEAR_VAR: "top"}))
    age_payload = http_json(f"{base}/{AGE_TABLE}",
                            query({AGE_VAR: "*", REGION: "*", YEAR_VAR: "top"}))
    records = build(sex_payload, age_payload, labels_en, labels_mn,
                    drawn("MNG", "admin1"), drawn("MNG", "admin2"))
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
