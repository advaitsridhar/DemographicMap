#!/usr/bin/env python3
"""Kenya: the 2019 census's head count, sex ratio and median age by county and constituency.

The Kenya National Bureau of Statistics published the 2019 Kenya Population and
Housing Census in four volumes, and Code for Africa's openAFRICA portal holds
the Bureau's tables from them as CSV (KNBS's own site fails TLS verification on
a clean client). Three are read here:

* Volume I, *Distribution of Population by Sex and County*: everyone counted,
  by sex (male, female, intersex), for the country and the 47 counties.
* Volume III, *Distribution of Population by Age, Sex, County and Sub-County*:
  everyone by single year of age (to 99, then 100 and over, and "not stated")
  and by sex, for every county ("ALL") and every sub-county.
* Volume II, *Distribution of Population by Sex and Sub County*, as a check on
  the sub-county totals.

**Counties.** Population is Volume I's count of everyone, intersex persons
included; the sex ratio is men per 1,000 women; the median age is interpolated
within the single year of age that holds the middle person, leaving out the
ages not stated. The map carried the county totals of Volume IV's religion
table until now, which count a little fewer people than Volume I.

**Constituencies.** The map's second level is the 290 constituencies; the
census tabulates its 340-odd sub-counties, and the two are not the same units
everywhere. A constituency is written only where its census figures are
established: where the sub-counties a county's constituencies are made of are
known (CROSSWALK, from the sub-counties' outlines against the constituencies'),
or, failing that, where every constituency of the county is a sub-county of
the same name and those sub-counties make the county. Every other constituency
gets a gap that says why.

**Checks.** Every row's single years make its total and its sexes make it too;
each county's sub-counties make the county; Volume III's county totals are
Volume I's without the intersex persons.

Usage:
    python -m scripts.fetch_census.kenya_census --points
    python -m scripts.fetch_census.kenya_census
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import fold
from .cod_ps_age import grouped_median

OUT = "kenya_census.json"
YEAR = 2019
SITE = PROCESSED.parent.parent / "site" / "data"
PAGE = "https://open.africa/dataset/2019-kenya-population-and-housing-census"
BASE = "https://open.africa/dataset/9b94fe50-9d75-4b92-be00-6354c6e6cc88/resource/"
VOL1 = BASE + ("384b93cf-ede0-4e05-9f36-a8e8e09b21a7/download/"
               "kenya-population-by-sex-and-county.csv")
VOL3 = BASE + ("b7edfdb4-2a07-4332-8796-2f00968aff0e/download/"
               "distribution-of-population-by-age-sex-county-and-sub-county-kenya-2019-census-"
               "volume-iii.csv")
VOL2 = BASE + ("ddddbe91-b5fa-4449-a50d-846401e701c4/download/"
               "distribution-of-population-by-sex-and-sub-county-2019-census-volume-ii.csv")
SOURCE1 = ("Kenya National Bureau of Statistics, 2019 Kenya Population and Housing Census, "
           "Volume I: Population by County and Sub-County, distribution of population by sex "
           "and county")
SOURCE3 = ("Kenya National Bureau of Statistics, 2019 Kenya Population and Housing Census, "
           "Volume III: Distribution of Population by Age and Sex, by county and sub-county")
LICENCE = "Creative Commons Attribution (openAFRICA copy of a KNBS publication)"
NATIONAL = 47_564_296
POINTS = "kenya_subcounty_points.json"
COD_AB = "cod-ab-ken"
# Share of a county's people the matched sub-counties must make before its
# constituencies are taken to be its sub-counties (forest and park rows of a
# few hundred people are the rest).
PARTITION = 0.995

# The map's county label where it is not the census's name folded.
COUNTY_ALIASES = {"tharakanithi": "Tharaka", "taitataveta": "Taita Taveta"}
# Constituencies made of census sub-counties, by county, from the sub-counties'
# outlines in OCHA's boundary dataset against the map's constituency polygons
# (``--points``): {county fold: {constituency label: [sub-county folds]}}.
CROSSWALK: dict[str, dict[str, list[str]]] = {}


def number(cell: Any) -> int:
    """A count; KNBS writes none as "-" and, in Volume III, as "_"."""
    text = str(cell or "").replace(",", "").strip()
    return int(float(text)) if text not in ("", "-", "_") else 0


def read_vol1(text: str) -> dict[str, dict[str, int]]:
    """{county fold: {male, female, intersex, total}} from Volume I's sex table."""
    out: dict[str, dict[str, int]] = {}
    rows = list(csv.reader(io.StringIO(text)))
    start = next((i for i, r in enumerate(rows) if r and r[0].strip().lower() == "name"), None)
    if start is None:
        raise SystemExit("kenya_census: Volume I's table has no 'name' header row")
    for row in rows[start + 1:]:
        if not row or not row[0].strip():
            continue
        male, female, inter, total = (number(c) for c in row[1:5])
        if male + female + inter != total:
            raise SystemExit(f"kenya_census: {row[0]}: its sexes make {male + female + inter:,}, "
                             f"not {total:,}")
        out[fold(row[0])] = {"name": row[0].strip(), "male": male, "female": female,
                             "intersex": inter, "total": total}
    national = out.pop("kenya", None)
    if not national or national["total"] != NATIONAL:
        raise SystemExit(f"kenya_census: Volume I's Kenya row is not {NATIONAL:,}")
    if sum(c["total"] for c in out.values()) != NATIONAL or len(out) != 47:
        raise SystemExit(f"kenya_census: {len(out)} counties making "
                         f"{sum(c['total'] for c in out.values()):,}")
    return out


AGE = re.compile(r"^\d{1,2}$")


def read_vol3(text: str) -> dict[str, dict[str, Any]]:
    """{county fold: {"all": unit, "subs": {sub-county fold: unit}}}, each unit's single
    years, sexes and total checked."""
    rows = list(csv.reader(io.StringIO(text)))
    header = [h.strip().lower() for h in rows[0]]
    if header[:6] != ["county", "sub-county", "age", "male", "female", "total"]:
        raise SystemExit(f"kenya_census: Volume III's header is {header[:6]}")
    units: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows[1:]:
        if len(row) < 6 or not row[0].strip():
            continue
        # A sub-county name with a comma in it, unquoted, spills into the next
        # column: the last three cells are always the counts and the one
        # before them the age.
        county, age = row[0].strip(), row[-4].strip()
        sub = ",".join(row[1:-4]).strip()
        unit = units.setdefault((county, sub), {"county": county, "name": sub, "ages": {},
                                                "unstated": 0, "total": None, "bad": []})
        try:
            male, female, total = (number(c) for c in row[-3:])
        except ValueError:
            # A cell a spreadsheet turned into a date ("15-Aug"): the unit fails
            # its sums below and is left out, never read with the row missing.
            unit["bad"].append(f"age {age}: {row[-3:]}")
            continue
        if male + female != total:
            unit["bad"].append(f"age {age}: sexes make {male + female:,}, not {total:,}")
            continue
        if age.lower() == "total":
            unit.update(total=total, male=male, female=female)
        elif AGE.match(age):
            unit["ages"][int(age)] = total
        elif age.replace(" ", "") == "100+":
            unit["ages"][100] = total
        elif age.lower() == "not stated":
            unit["unstated"] = total
        # Five-year rows ("0 - 4", "10 -14") repeat the single years and are left.
    out: dict[str, dict[str, Any]] = {}
    for (county, sub), unit in units.items():
        made = sum(unit["ages"].values()) + unit["unstated"]
        entry = out.setdefault(fold(county), {"name": county, "all": None, "subs": {},
                                              "unread": []})
        if (unit["bad"] or unit["total"] is None or made != unit["total"]
                or len(unit["ages"]) != 101):
            # Its count still stands where Volume II gives it; its ages do not.
            entry["unread"].append(f"{sub}: {len(unit['ages'])} single years making {made:,} "
                                   f"against {unit['total']}; {unit['bad'][:3]}")
            unit["ages_ok"] = False
        else:
            unit["ages_ok"] = True
        if sub.upper() == "ALL":
            entry["all"] = unit
        else:
            entry["subs"][fold(sub)] = unit
    for key, entry in out.items():
        if entry["all"] is None or entry["all"]["total"] is None:
            raise SystemExit(f"kenya_census: {entry['name']} has no county total")
        made = sum(u["total"] or 0 for u in entry["subs"].values())
        if made != entry["all"]["total"]:
            raise SystemExit(f"kenya_census: {entry['name']}'s sub-counties make {made:,}, "
                             f"not {entry['all']['total']:,}")
    return out


def median(units: list[dict[str, Any]]) -> float | None:
    """The median of several units' single years added together, ages not stated left out."""
    groups = [(a, a, sum(u["ages"][a] for u in units)) for a in range(100)]
    groups.append((100, None, sum(u["ages"][100] for u in units)))
    return grouped_median(groups)


def age_fields(units: list[dict[str, Any]], of: str) -> dict[str, Any]:
    if not all(u.get("ages_ok") for u in units):
        return {}
    value = median(units)
    if value is None:
        return {}
    unstated = sum(u["unstated"] for u in units)
    return {"median_age": measure(value, unit="years", year=YEAR, source=SOURCE3),
            "median_age_note": (
                "Interpolated within the single year of age that holds the middle person, "
                f"from the 2019 census's count of everyone by single year of age{of}"
                + (f", leaving out the {unstated:,} whose age was not stated." if unstated
                   else "."))}


def county_records(vol1: dict[str, dict[str, int]], vol3: dict[str, dict[str, Any]],
                   admin1: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    shapes = {fold(s["name"]): s for s in admin1}
    # Volume III writes "NAIROBI CITY" where Volume I writes "Nairobi".
    by_name = {re.sub(r"city$", "", k): v for k, v in vol3.items()}
    records, shape_of = [], {}
    for key, row in sorted(vol1.items()):
        label = COUNTY_ALIASES.get(key)
        shape = shapes.get(fold(label)) if label else shapes.get(key)
        ages = vol3.get(key) or by_name.get(key)
        if shape is None or ages is None:
            raise SystemExit(f"kenya_census: county {row['name']}: polygon {bool(shape)}, "
                             f"age table {bool(ages)}")
        if ages["all"]["total"] != row["male"] + row["female"]:
            raise SystemExit(f"kenya_census: {row['name']}: Volume III counts "
                             f"{ages['all']['total']:,}, Volume I {row['male'] + row['female']:,} "
                             "men and women")
        shape_of[shape["id"]] = key
        note = (f"The 2019 census's count of everyone in the county, {row['intersex']:,} "
                "intersex persons included." if row["intersex"] else
                "The 2019 census's count of everyone in the county.")
        records.append(record(
            f"KEN-2019-{shape['id']}", shape["name"], level="admin1", parent="KEN",
            country="KEN", match_by="shape_id", shape_id=shape["id"],
            population=measure(row["total"], year=YEAR, source=SOURCE1),
            population_note=note,
            sex_ratio=measure(round(1000 * row["male"] / row["female"]),
                              unit="males_per_1000_females", year=YEAR, source=SOURCE1),
            **age_fields([ages["all"]], ""),
            sources=[{"field": "population/sex_ratio", "name": SOURCE1, "url": PAGE,
                      "year": YEAR, "license": LICENCE},
                     {"field": "median_age", "name": SOURCE3, "url": PAGE, "year": YEAR,
                      "license": LICENCE}]))
        ages["key"] = key
    return records, shape_of


def constituency_plans(vol3: dict[str, dict[str, Any]], admin2: list[dict[str, Any]],
                       shape_of: dict[str, str]) -> tuple[dict[str, list[str]], list[str]]:
    """{constituency shape id: [sub-county folds]} for the constituencies whose census
    figures are established, and a report of each county's outcome."""
    plans: dict[str, list[str]] = {}
    report: list[str] = []
    under: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shape in admin2:
        under[shape["parent"]].append(shape)
    for parent, shapes in sorted(under.items(), key=lambda kv: shape_of.get(kv[0], "")):
        key = shape_of.get(parent)
        if key is None:
            report.append(f"{len(shapes)} constituencies under no county polygon")
            continue
        entry = next((e for e in vol3.values() if e.get("key") == key), None)
        subs = entry["subs"]
        crosswalk = CROSSWALK.get(key)
        if crosswalk:
            taken = {s: crosswalk.get(s["name"].strip()) for s in shapes}
            if all(taken.values()) and all(k in subs for ks in taken.values() for k in ks):
                for s, ks in taken.items():
                    plans[s["id"]] = ks
                report.append(f"{entry['name']}: {len(shapes)} constituencies from the "
                              "crosswalk")
                continue
            report.append(f"{entry['name']}: crosswalk incomplete {taken}")
        names = {s["id"]: fold(s["name"]) for s in shapes}
        if all(n in subs for n in names.values()):
            made = sum(subs[n]["total"] for n in names.values())
            if made >= PARTITION * entry["all"]["total"]:
                for sid, n in names.items():
                    plans[sid] = [n]
                report.append(f"{entry['name']}: {len(shapes)} constituencies are its "
                              f"sub-counties of the same names ({made:,} of "
                              f"{entry['all']['total']:,})")
                continue
        report.append(f"{entry['name']}: {len(shapes)} constituencies, {len(subs)} sub-counties "
                      f"({sorted(subs)}); not written")
    return plans, report


def constituency_records(vol3: dict[str, dict[str, Any]], admin2: list[dict[str, Any]],
                         shape_of: dict[str, str], plans: dict[str, list[str]]
                         ) -> list[dict[str, Any]]:
    by_key = {e["key"]: e for e in vol3.values() if e.get("key")}
    records = []
    for shape in admin2:
        key = shape_of.get(shape["parent"])
        if key is None:
            continue
        entry = by_key[key]
        county = entry["name"].title()
        taken = plans.get(shape["id"])
        if not taken:
            why = (f"The 2019 census was published by sub-county, and {county}'s "
                   f"{len(entry['subs'])} sub-counties are not its constituencies, so no count is "
                   "published for this constituency.")
            stated = gap(NOT_AVAILABLE, why)
            records.append(record(f"KEN-2019-{shape['id']}", shape["name"], level="admin2",
                                  parent="KEN", country="KEN", match_by="shape_id",
                                  shape_id=shape["id"], population=stated, median_age=stated,
                                  sex_ratio=stated,
                                  sources=[{"field": "population/median_age/sex_ratio",
                                            "name": SOURCE3, "url": PAGE, "year": YEAR,
                                            "license": LICENCE}]))
            continue
        units = [entry["subs"][k] for k in taken]
        total = sum(u["total"] for u in units)
        male, female = sum(u["male"] for u in units), sum(u["female"] for u in units)
        names = [u["name"].title() for u in units]
        if len(units) == 1:
            note = f"The 2019 census's count for {names[0]} sub-county."
            of = ""
        else:
            note = ("The 2019 census's counts for the sub-counties of "
                    + ", ".join(names[:-1]) + " and " + names[-1]
                    + ", added up: the constituency is the sub-counties together.")
            of = ", of its sub-counties together"
        records.append(record(
            f"KEN-2019-{shape['id']}", shape["name"], level="admin2", parent="KEN",
            country="KEN", match_by="shape_id", shape_id=shape["id"],
            population=measure(total, year=YEAR, source=SOURCE3), population_note=note,
            sex_ratio=measure(round(1000 * male / female), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE3),
            **age_fields(units, of),
            sources=[{"field": "population/median_age/sex_ratio", "name": SOURCE3, "url": PAGE,
                      "year": YEAR, "license": LICENCE}]))
    return records


def fetch(url: str) -> str:
    body = http_get(url, cache=False, timeout=300)
    text = body if isinstance(body, str) else body.decode("utf-8-sig", "replace")
    log(f"  read {url}: {len(text):,} characters, sha256 "
        f"{hashlib.sha256(text.encode()).hexdigest()}")
    return text.lstrip("﻿")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--points", action="store_true",
                    help="write points sampled over OCHA's sub-county outlines, for CROSSWALK")
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    args = ap.parse_args()
    if args.points:
        from .uganda_census import write_cod_points  # noqa: PLC0415
        return write_cod_points(COD_AB, 2, POINTS)
    vol1 = read_vol1(fetch(VOL1))
    vol3 = read_vol3(fetch(VOL3))
    log(f"  Volume I: 47 counties making {NATIONAL:,}; Volume III: {len(vol3)} counties and "
        f"{sum(len(e['subs']) for e in vol3.values())} sub-counties, every row checked")
    for entry in vol3.values():
        for line in entry["unread"]:
            log(f"  ages not read for {entry['name']}, {line}")
    admin1 = json.loads((SITE / "admin1" / "KEN.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "KEN.units.json").read_text())
    records, shape_of = county_records(vol1, vol3, admin1)
    plans, report = constituency_plans(vol3, admin2, shape_of)
    for line in report:
        log("  " + line)
    records += constituency_records(vol3, admin2, shape_of, plans)
    written = [r for r in records if r["level"] == "admin2" and "value" in r["population"]]
    log(f"  {sum(1 for r in records if r['level'] == 'admin1')} counties and {len(written)} of "
        f"{len(admin2)} constituencies with figures")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
