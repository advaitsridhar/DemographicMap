#!/usr/bin/env python3
"""United Kingdom -- median age, sex ratio and population from the mid-year
estimates, for every drawn local authority and the four nations.

The census tables the UK adapters read (``uk_nomis``, ``scotland_census``,
``northern_ireland``) carry compositions and a head count, and not one age:
114 of the 216 second-level shapes and three of the four nations had no median
age or sex ratio at all, and Scotland's councils had the 2011 census's head
count. The offices' mid-year population estimates close all three at once.

Nomis serves them as ``NM_2002_1`` -- "Population estimates - local authority
based by single year of age" -- for the whole UK in one table: the ONS's for
England and Wales, and National Records of Scotland's and NISRA's for their
councils and districts. Every person by sex and by single year of age from 0
to 89, with 90 and over as one open class.

**Which geography.** geoBoundaries' second level is mixed: unitary
authorities, metropolitan and London boroughs, Welsh principal areas,
Scottish councils and Northern Irish districts -- and, for shire England, the
*county*. Nomis' ``TYPE423`` ("local authorities: county / unitary (as of April
2023)") is exactly that mix, so no district is summed into a county here;
each county's figure is the one the office publishes for it.

**Two drawn counties no longer exist**, and both are exactly partitioned by
their successors, so the successors' single years are added together for the
old shape, age by age and sex by sex, before the median is taken:

* Cumbria (abolished April 2023) = Cumberland + Westmorland and Furness;
* Northamptonshire (abolished April 2021) = North + West Northamptonshire.

North Yorkshire and Somerset became unitary in April 2023 on the counties'
own boundaries, so their unitary figures are the drawn counties' figures.

**Which year.** The latest Nomis serves for each place: mid-2025 for England,
Wales and Scotland, and for Northern Ireland, whose 2025 cells are still empty,
mid-2024. Each record says its own year.

Median age is interpolated within the single year holding the middle person
(``redatam.median_age``), with 90+ as the open top class. Sex ratio is males
per 1,000 females, the unit every other age-sex reader on this map writes.

**A figure far from the census year's is shown with its series.** Where a
place's latest estimate is more than a quarter above or a fifth below its own
mid-2021 estimate, the note gives the office's series year by year, so a
reader sees the change is the office's and not a different place: the City of
London is the case, 8,689 at mid-2021 and 15,631 at mid-2025 in the ONS's
own estimates.

Checks, each of which stops the run:

* every place's single years add to its all-ages count, for each sex, and its
  two sexes add to its total;
* each nation's places add to the nation's own published count;
* every drawn shape is bound one-to-one, and every Nomis row reaches a shape
  or is one of the four successor authorities above.

Usage:
    python -m scripts.fetch_census.uk_mye
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections import Counter
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json
from .binding import fold
from .redatam import median_age

BASE = "https://www.nomisweb.co.uk/api/v01/dataset/NM_2002_1.data.csv"
PAGE = "https://www.nomisweb.co.uk/datasets/pestsyoala"
OUT = "uk_mye.json"
SITE = PROCESSED.parent.parent / "site" / "data"
LICENCE = "Open Government Licence v3.0"

# The Nomis geography types read: the drawn mix, and the four nations.
LOCAL = "TYPE423"
NATIONS = "TYPE499"
NATION_OF = {"E": "England", "W": "Wales", "S": "Scotland", "N": "Northern Ireland"}
OFFICE = {
    "E": "Office for National Statistics", "W": "Office for National Statistics",
    "S": "National Records of Scotland",
    "N": "Northern Ireland Statistics and Research Agency",
}

# Drawn shape -> the successor authorities that partition it exactly.
SUCCESSORS: dict[str, tuple[str, ...]] = {
    "Cumbria": ("E06000063", "E06000064"),
    "Northamptonshire": ("E06000061", "E06000062"),
}

# A latest estimate outside this ratio to the place's mid-2021 estimate has its
# series written into the note.
SERIES_BAND = (0.8, 1.25)

# Nomis' spelling -> the boundary file's, where they differ beyond case.
RESPELLINGS: dict[str, str] = {}

AGE = re.compile(r"^Age (\d+)$")
OPEN = re.compile(r"^Aged (\d+)\+$")
# All ages, then 0 to 89 and 90+ (Nomis codes 101 to 191), listed rather than
# written as a range so the request says exactly what it asks for.
AGES = ",".join(["200"] + [str(c) for c in range(101, 192)])


def fetch(geography: str, date: str, gender: int) -> list[dict[str, str]]:
    """One sex's single years for one geography type, as Nomis' CSV rows.

    One sex per request keeps each answer under Nomis' 25,000-cell ceiling for
    an anonymous caller: about 220 places by 92 ages.
    """
    url = (f"{BASE}?geography={geography}&date={date}&gender={gender}"
           f"&c_age={AGES}&measures=20100"
           f"&select=date_name,geography_code,geography_name,c_age_name,obs_value")
    text = http_get(url, cache=False, timeout=300)
    assert isinstance(text, str)
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def read_series(geography: str) -> dict[str, dict[int, int]]:
    """code -> {year: all persons} for the five latest years (one small request)."""
    dates = ",".join(["latestMINUS4", "latestMINUS3", "latestMINUS2", "latestMINUS1", "latest"])
    url = (f"{BASE}?geography={geography}&date={dates}&gender=0&c_age=200&measures=20100"
           f"&select=date_name,geography_code,obs_value")
    text = http_get(url, cache=False, timeout=300)
    assert isinstance(text, str)
    out: dict[str, dict[int, int]] = {}
    for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        value = (row.get("OBS_VALUE") or "").strip()
        if value:
            out.setdefault(row["GEOGRAPHY_CODE"], {})[int(row["DATE_NAME"][:4])] = int(float(value))
    return out


def series_note(name: str, office: str, years: dict[int, int], year: int) -> str:
    """The office's series, when the figure shown is far from the census year's."""
    base = years.get(2021)
    latest = years.get(year)
    if not base or not latest or SERIES_BAND[0] <= latest / base <= SERIES_BAND[1]:
        return ""
    shown = ", ".join(f"{years[y]:,} ({y})" for y in sorted(years) if y <= year)
    return (f" The {office} estimates {name} at {shown}: {latest / base:.2f} times its "
            "mid-2021 figure, in the office's own series for the same area, not a change "
            "of boundary.")


def tabulate(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """code -> {name, year, all ages, Counter of single years}."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = (row.get("OBS_VALUE") or "").strip()
        if value == "":
            continue
        code = row["GEOGRAPHY_CODE"]
        entry = out.setdefault(code, {"name": row["GEOGRAPHY_NAME"],
                                      "year": int(row["DATE_NAME"][:4]),
                                      "all": None, "ages": Counter()})
        label = row["C_AGE_NAME"].strip()
        count = int(float(value))
        if label == "All Ages":
            entry["all"] = count
        elif (m := AGE.match(label)):
            entry["ages"][int(m.group(1))] += count
        elif (m := OPEN.match(label)):
            entry["ages"][int(m.group(1))] += count
        else:
            raise SystemExit(f"uk_mye: an age Nomis calls {label!r}, which is neither a "
                             "single year nor the open top class")
    return out


def read(geography: str) -> dict[str, dict[str, Any]]:
    """code -> {name, year, men, women, ages by sex}, latest year with figures.

    Read for the latest date and then the one before it, and each place takes
    the latest in which both its sexes have figures: Northern Ireland's 2025
    cells are published empty while the rest of the UK's are filled.
    """
    places: dict[str, dict[str, Any]] = {}
    for date in ("latest", "latestMINUS1"):
        men, women = tabulate(fetch(geography, date, 1)), tabulate(fetch(geography, date, 2))
        for code in sorted(set(men) & set(women)):
            if code in places:
                continue
            m, f = men[code], women[code]
            for sex, entry in (("male", m), ("female", f)):
                made = sum(entry["ages"].values())
                if entry["all"] is None or made != entry["all"]:
                    raise SystemExit(f"uk_mye: {entry['name']} ({code}) {sex}: single years "
                                     f"make {made:,} against all ages {entry['all']}")
                if max(entry["ages"]) != 90 or len(entry["ages"]) != 91:
                    raise SystemExit(f"uk_mye: {entry['name']} ({code}) {sex}: ages "
                                     f"{min(entry['ages'])}-{max(entry['ages'])}, "
                                     f"{len(entry['ages'])} of them, not 0-89 and 90+")
            if m["year"] != f["year"]:
                raise SystemExit(f"uk_mye: {code}: men for {m['year']}, women for {f['year']}")
            places[code] = {"name": m["name"], "year": m["year"], "men": m["all"],
                            "women": f["all"], "male": m["ages"], "female": f["ages"]}
        log(f"  {geography} {date}: {len(places)} places with both sexes so far")
    return places


def total_check(places: dict[str, dict[str, Any]], nations: dict[str, dict[str, Any]]) -> None:
    """Each nation's places must add to the nation's own count, year by year."""
    for code, nation in nations.items():
        letter = code[0]
        parts = [p for c, p in places.items() if c[0] == letter]
        years = {p["year"] for p in parts}
        if years != {nation["year"]}:
            raise SystemExit(f"uk_mye: {nation['name']} is for {nation['year']}, its places "
                             f"for {sorted(years)}")
        made = sum(p["men"] + p["women"] for p in parts)
        whole = nation["men"] + nation["women"]
        if made != whole:
            raise SystemExit(f"uk_mye: {nation['name']}'s {len(parts)} places make {made:,} "
                             f"against its own {whole:,}")
        log(f"  {nation['name']} {nation['year']}: {len(parts)} places make {whole:,}, "
            "its own count")


def combine(parts: list[dict[str, Any]], name: str) -> dict[str, Any]:
    years = {p["year"] for p in parts}
    if len(years) != 1:
        raise SystemExit(f"uk_mye: {name}'s successors are for different years {years}")
    return {"name": name, "year": years.pop(),
            "men": sum(p["men"] for p in parts), "women": sum(p["women"] for p in parts),
            "male": sum((p["male"] for p in parts), Counter()),
            "female": sum((p["female"] for p in parts), Counter()),
            "from": [p["name"] for p in parts]}


def fields(place: dict[str, Any], code: str, extra: str = "") -> dict[str, Any]:
    office = OFFICE[code[0]]
    year = place["year"]
    source = f"{office}, mid-{year} population estimates (Nomis NM_2002_1)"
    ages = place["male"] + place["female"]
    whole = place["men"] + place["women"]
    joined = place.get("from")
    note = (f"Everyone estimated to be usually resident at 30 June {year}, "
            f"by sex and single year of age (0 to 89, and 90 and over)"
            + (f", of {' and '.join(joined)} added together: the two unitary "
               f"authorities that replaced {place['name']} and together cover it exactly."
               if joined else "."))
    return {
        "population": measure(whole, year=year, source=source),
        "population_note": note + extra,
        "median_age": measure(median_age(ages), unit="years", year=year, source=source),
        "median_age_note": ("Interpolated within the single year of age holding the middle "
                            "person. " + note),
        "sex_ratio": measure(round(1000 * place["men"] / place["women"]),
                             unit="males_per_1000_females", year=year, source=source),
        "sources": [{"field": "population/median age/sex ratio", "name": source,
                     "url": PAGE, "year": year, "license": LICENCE}],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    log("uk_mye: local authorities (county / unitary, April 2023)")
    places = read(LOCAL)
    log("uk_mye: the four nations")
    # TYPE499 also lists the UK, Great Britain and England and Wales.
    nations = {c: p for c, p in read(NATIONS).items() if c[1:3] == "92"}
    if sorted(c[0] for c in nations) != sorted(NATION_OF):
        raise SystemExit(f"uk_mye: nations read: {sorted(nations)}")
    total_check(places, nations)

    admin1 = json.loads((SITE / "admin1" / "GBR.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "GBR.units.json").read_text())

    # The successors become the drawn county they partition.
    drawn: dict[str, tuple[str, dict[str, Any]]] = {}
    used: set[str] = set()
    for name, codes in SUCCESSORS.items():
        missing = [c for c in codes if c not in places]
        if missing:
            raise SystemExit(f"uk_mye: {name}'s successors {missing} are not in the table")
        drawn[fold(name)] = ("+".join(codes), combine([places[c] for c in codes], name))
        used.update(codes)
    for code, place in places.items():
        if code in used:
            continue
        key = fold(RESPELLINGS.get(place["name"], place["name"]))
        if key in drawn:
            raise SystemExit(f"uk_mye: two places named {place['name']}")
        drawn[key] = (code, place)

    history = read_series(LOCAL)
    records: list[dict[str, Any]] = []
    shapes = {fold(s["name"]): s for s in admin2}
    if len(shapes) != len(admin2):
        raise SystemExit("uk_mye: two drawn shapes share a name")
    unbound_rows = sorted(p["name"] for k, (_, p) in drawn.items() if k not in shapes)
    unbound_shapes = sorted(s["name"] for k, s in shapes.items() if k not in drawn)
    if unbound_rows or unbound_shapes:
        raise SystemExit(f"uk_mye: Nomis rows with no shape {unbound_rows}; "
                         f"shapes with no row {unbound_shapes}")
    for key, shape in sorted(shapes.items()):
        code, place = drawn[key]
        years: dict[int, int] = {}
        for part in code.split("+"):
            for y, n in history.get(part, {}).items():
                years[y] = years.get(y, 0) + n
        if years.get(place["year"]) not in (None, place["men"] + place["women"]):
            raise SystemExit(f"uk_mye: {place['name']}: the series gives "
                             f"{years.get(place['year']):,} for {place['year']}, the single "
                             f"years {place['men'] + place['women']:,}")
        extra = series_note(place["name"], OFFICE[code[0]], years, place["year"])
        if extra:
            log(f"  {place['name']}:{extra}")
        records.append(record(
            f"GBR-MYE-{code}", shape["name"], level="admin2", parent="GBR", country="GBR",
            match_by="shape_id", shape_id=shape["id"],
            codes={"gss_codes": code.split("+")} if "+" in code else {"gss_code": code},
            **fields(place, code.split("+")[0], extra)))
    nations_by_name = {fold(NATION_OF[c[0]]): (c, p) for c, p in nations.items()}
    for shape in admin1:
        hit = nations_by_name.get(fold(shape["name"]))
        if hit is None:
            raise SystemExit(f"uk_mye: first-level shape {shape['name']} is not a nation")
        code, place = hit
        records.append(record(
            f"GBR-MYE-{code}", shape["name"], level="admin1", parent="GBR", country="GBR",
            match_by="shape_id", shape_id=shape["id"], codes={"gss_code": code},
            **fields(place, code)))
    years = Counter(r["population"]["year"] for r in records)
    log(f"  {len(records)} records ({len(admin2)} local authorities, {len(admin1)} nations); "
        f"years {dict(years)}")
    for r in records:
        if r["level"] == "admin1":
            log(f"  {r['name']}: {r['population']['value']:,}, median "
                f"{r['median_age']['value']}, {r['sex_ratio']['value']} men per 1,000 women")
    write_json(args.out or PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
