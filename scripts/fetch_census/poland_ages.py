#!/usr/bin/env python3
"""Poland: median age, sex ratio and population by powiat, from GUS's BDL.

Statistics Poland's Local Data Bank (Bank Danych Lokalnych) answers a JSON
API, bdl.stat.gov.pl/api/v1, variable by variable. Four variables are read,
for every powiat (unit level 5), every voivodeship (level 2) and the country:

* 746289 -- "Mediana wieku ludności" (subject P3814), GUS's own median age
  of the population, which is written as published;
* 72305, 72300, 72295 -- the population, men and women (subject P2137,
  "Ludność wg grup wieku i płci", the totals), for the sex ratio and the
  population, on 31 December.

GUS publishes the median for exactly these units, so there is nothing to
interpolate. The checks are that men and women make the total in every
unit, that the powiats make each voivodeship and the voivodeships the
country, and that GUS's national median sits within 0.3 years of Eurostat's
for Poland on the next 1 January.

**Names.** BDL names a powiat "Powiat bocheński" or, for a city with powiat
rights, "Powiat m. Kraków"; the census reader (``poland.py``) already turns
those into the boundary file's spellings, with the eleven land powiats
geoBoundaries names after their seat, and the rename of powiat jeleniogórski
to karkonoski in 2021. Each powiat is bound within its voivodeship, read off
the TERYT code inside the BDL unit id.

The Masovian voivodeship has no median on this map because Eurostat splits
it in two at NUTS 2; its GUS figure is written at the first level.

Usage:
    python -m scripts.fetch_census.poland_ages
"""

from __future__ import annotations

import argparse
import time
from typing import Any

from ._shared import PROCESSED, http_json, log, measure, record, write_json
from .central_ages import SEX_RATIO_UNIT, check_sum, eurostat_median, fold, report_unbound, sex_ratio, units
from .poland import VOIVODESHIPS, powiat_names

API = "https://bdl.stat.gov.pl/api/v1/data/by-variable/{var}?format=json&unit-level={level}&page-size=100&page={page}&lang=pl"
PORTAL = "https://bdl.stat.gov.pl/bdl/dane/podgrup/temat"
SOURCE = "Statistics Poland (GUS), Local Data Bank (BDL): median age (P3814) and population by sex (P2137)"
LICENCE = "GUS open data (free reuse with attribution)"
OUT = PROCESSED / "poland_powiat_age.json"
VARIABLES = {"median": 746289, "total": 72305, "men": 72300, "women": 72295}
TERYT = {"02": "DOLNOŚLĄSKIE", "04": "KUJAWSKO-POMORSKIE", "06": "LUBELSKIE", "08": "LUBUSKIE",
         "10": "ŁÓDZKIE", "12": "MAŁOPOLSKIE", "14": "MAZOWIECKIE", "16": "OPOLSKIE",
         "18": "PODKARPACKIE", "20": "PODLASKIE", "22": "POMORSKIE", "24": "ŚLĄSKIE",
         "26": "ŚWIĘTOKRZYSKIE", "28": "WARMIŃSKO-MAZURSKIE", "30": "WIELKOPOLSKIE",
         "32": "ZACHODNIOPOMORSKIE"}
LACKING_ADMIN1 = {"MAZOWIECKIE"}
EXPECTED = 380


def variable(var: int, level: int) -> dict[str, dict[str, Any]]:
    """{unit id: {"name", "values": {year: value}}} for one variable at one level."""
    out: dict[str, dict[str, Any]] = {}
    page = 0
    while True:
        data = http_json(API.format(var=var, level=level, page=page), cache=False, timeout=120)
        for row in data.get("results", []):
            out[row["id"]] = {"name": row["name"],
                              "values": {int(v["year"]): v["val"] for v in row.get("values", [])}}
        if "next" not in (data.get("links") or {}):
            break
        page += 1
        time.sleep(0.6)                   # anonymous BDL use is rate-limited
    return out


def build() -> list[dict[str, Any]]:
    log("poland_ages: BDL variables " + ", ".join(f"{k} {v}" for k, v in VARIABLES.items()))
    data = {level: {k: variable(v, level) for k, v in VARIABLES.items()} for level in (0, 2, 5)}
    # BDL keeps units that no longer exist (a city that was a powiat for a
    # decade) beside the current ones, with no values in recent years. A year
    # is usable when exactly the current division -- 380 powiats, 16
    # voivodeships, the country -- has all four variables in it.
    expected = {0: 1, 2: 16, 5: EXPECTED}
    all_years = sorted({y for byvar in data.values() for units_ in byvar.values()
                        for unit in units_.values() for y in unit["values"]}, reverse=True)
    year, current = None, {}
    for candidate in all_years:
        current = {level: sorted(u for u in data[level]["total"]
                                 if all(candidate in data[level][k].get(u, {}).get("values", {})
                                        for k in VARIABLES))
                   for level in expected}
        counts = {level: len(ids) for level, ids in current.items()}
        log(f"  {candidate}: units with all four variables {counts}")
        if counts == expected:
            year = candidate
            break
    if year is None:
        raise SystemExit("poland_ages: no year in which the current division has all four variables")
    for level in expected:
        for key in VARIABLES:
            data[level][key] = {u: data[level][key][u] for u in current[level]}

    def value(level: int, key: str, unit_id: str) -> float:
        return data[level][key][unit_id]["values"][year]

    for level in (0, 2, 5):
        for unit_id in data[level]["total"]:
            men, women, total = (value(level, k, unit_id) for k in ("men", "women", "total"))
            if abs(men + women - total) > 0.5:
                raise SystemExit(f"poland_ages: {data[level]['total'][unit_id]['name']}: "
                                 f"{men:,.0f} + {women:,.0f} != {total:,.0f}")
    (country,) = data[0]["total"]
    national = value(0, "total", country)
    check_sum((value(5, "total", u) for u in data[5]["total"]), national, "powiats against Poland")
    for voiv_id in data[2]["total"]:
        teryt = voiv_id[2:4]
        check_sum((value(5, "total", u) for u in data[5]["total"] if u[2:4] == teryt),
                  value(2, "total", voiv_id), f"powiats against {TERYT[teryt]}")
    theirs = eurostat_median("PL", year + 1)
    mine = value(0, "median", country)
    if theirs is not None and abs(theirs - mine) > 0.3:
        raise SystemExit(f"poland_ages: GUS's national median {mine} against Eurostat's {theirs}")
    log(f"  GUS national median {mine} ({year}); Eurostat {theirs} (1 January {year + 1})")

    def fields(level: int, unit_id: str, what: str) -> dict[str, Any]:
        men, women = value(level, "men", unit_id), value(level, "women", unit_id)
        return {
            "population": measure(int(value(level, "total", unit_id)), year=year, source=SOURCE),
            "median_age": measure(round(value(level, "median", unit_id), 1), unit="years",
                                  year=year, source=SOURCE),
            "median_age_note": f"GUS's own median age of the {what}'s population, {year} (BDL P3814).",
            "sex_ratio": measure(sex_ratio(men, women), unit=SEX_RATIO_UNIT, year=year, source=SOURCE),
            "sex_ratio_note": (f"Males per 100 females in the {what}'s population on 31 December "
                               f"{year} (BDL P2137)."),
            "sources": [{"field": "population/median_age/sex_ratio", "name": SOURCE, "url": PORTAL,
                         "license": LICENCE, "year": year}],
        }

    shapes = units("POL", "admin2")
    firsts = units("POL", "admin1")
    parents = {u["id"]: u["name"] for u in firsts}
    by_key: dict[str, list[dict[str, Any]]] = {}
    for shape in shapes:
        by_key.setdefault(fold(shape["name"]), []).append(shape)
    records, unbound, used = [], [], set()
    for unit_id, unit in sorted(data[5]["total"].items()):
        voiv = TERYT[unit_id[2:4]]
        raw = unit["name"].replace("Powiat ", "", 1).strip()
        name, aliases = powiat_names(voiv, raw)
        keys = {fold(n) for n in [name, *aliases]}
        hits = [s for k in keys for s in by_key.get(k, [])
                if parents.get(s["parent"]) == VOIVODESHIPS[voiv]]
        if len({h["id"] for h in hits}) != 1 or hits[0]["id"] in used:
            unbound.append(f"{unit['name']} ({voiv}): {[h['name'] for h in hits]}")
            continue
        shape = hits[0]
        used.add(shape["id"])
        records.append(record(
            f"POL-BDL-{unit_id}", name, level="admin2", parent=shape["parent"],
            parent_name=VOIVODESHIPS[voiv], country="POL", codes={"bdl": unit_id},
            aliases=[shape["name"]] if shape["name"] != name else [],
            match_by="shape_id", shape_id=shape["id"], **fields(5, unit_id, "powiat")))
    report_unbound("poland_ages", unbound, [s["name"] for s in shapes if s["id"] not in used])
    if unbound or len(records) != EXPECTED:
        raise SystemExit(f"poland_ages: {len(records)} of {EXPECTED} powiats bound")
    first_by_name = {u["name"]: u for u in firsts}
    for voiv_id in sorted(data[2]["total"]):
        voiv = TERYT[voiv_id[2:4]]
        if voiv not in LACKING_ADMIN1:
            continue
        shape = first_by_name[VOIVODESHIPS[voiv]]
        records.append(record(
            f"POL-BDL-{voiv_id}", shape["name"], level="admin1", parent="POL", country="POL",
            codes={"bdl": voiv_id}, match_by="shape_id", shape_id=shape["id"],
            **fields(2, voiv_id, "voivodeship")))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    records = build()
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
