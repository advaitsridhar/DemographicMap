#!/usr/bin/env python3
"""Denmark: age, sex and National Church membership for the 98 kommuner and 5 regions.

Statistics Denmark's StatBank (api.statbank.dk) is not PxWeb: ``tableinfo``
describes a table and ``data`` takes a POST naming a value list per variable.
Two tables are read:

* **FOLK1A** -- population on the first day of the quarter by area, sex, single
  year of age (0 to 125) and marital status. The latest quarter gives each
  kommune's and region's population, median age and sex ratio. Marital status
  is pinned to its total.
* **KM6** -- population on 1 January by kommune, sex, five-year age group and
  membership of the National Church (Folkekirken). Summed over age and sex it
  is each kommune's members and non-members.

**Religion.** Denmark's census is compiled from registers and none of them
records belief. The one religious fact the Civil Registration System holds is
membership of the Evangelical Lutheran Church in Denmark, because the church
tax follows it, and Statistics Denmark tabulates it for everyone: every
resident is either a member or not. That is a composition of membership, not
of faith, and the note says so. Non-members are not "no religion": they are
members of every other faith as well as people of none, and no register tells
them apart, so they are one group here, labelled as what it is.

**Language** is recorded nowhere: no Danish register holds a mother tongue and
there is no questionnaire census. **Ethnicity** is the existing policy
(ancestry and citizenship only).

**Binding.** The map draws the 98 kommuner of the 2007 reform, which are the
office's current units, under the five regions. StatBank lists each region and
then its kommuner, so the parent is read from that order. Christiansø, which
belongs to no kommune, is counted in the national total and bound to nothing.

Checks: males and females make each area's published total; single years make
it too; the kommuner make their region and the regions the country; KM6's
members and non-members make KM6's population, which is compared with FOLK1A
on the same date.

Usage:
    python -m scripts.fetch_census.denmark
"""

from __future__ import annotations

import argparse
import csv
import io
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json
from .binding import fold
from .nordic_common import (AgeSex, bind_rows, check_national_median, check_parts,
                            load_units, request,
                            request_json, unplaced)

API = "https://api.statbank.dk/v1"
SOURCE = "Statistics Denmark"
FOLK1A_URL = "https://www.statbank.dk/FOLK1A"
KM6_URL = "https://www.statbank.dk/KM6"
OUT = PROCESSED / "denmark_kommune.json"

# StatBank's English names that the boundary file spells otherwise.
ALIASES = {"Vesthimmerlands": "Vesthimmerland", "Nordfyns": "Nordfyn"}
CHURCH = "Church of Denmark"
# Not "Not a member of the Church of Denmark": the group tree files any label
# containing "Church" under Protestantism, which is the one thing a non-member
# is not. shared.patch proposes a proper entry for this label.
OUTSIDE = "Not a member of the national church"


def info(table: str) -> dict[str, Any]:
    return request_json(f"{API}/tableinfo/{table}?lang=en&format=JSON")


def data(table: str, variables: dict[str, list[str]]) -> list[dict[str, str]]:
    body = request(f"{API}/data", {
        "table": table, "format": "CSV", "lang": "en", "delimiter": "Semicolon",
        "valuePresentation": "Code",
        "variables": [{"code": k, "values": v} for k, v in variables.items()],
    }, accept="text/csv")
    text = body.decode("utf-8-sig", "replace")
    rows = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    if not rows:
        raise SystemExit(f"{table}: empty answer: {text[:300]!r}")
    return rows


def number(text: str) -> float:
    return float(str(text).replace(",", ".")) if str(text).strip() not in ("", "..") else 0.0


def areas(meta: dict[str, Any], var: str) -> tuple[dict[str, str], dict[str, str]]:
    """{code: name} and {kommune code: region code}, from the table's own order."""
    names, region_of = {}, {}
    current = None
    for value in next(v for v in meta["variables"] if v["id"] == var)["values"]:
        code, name = value["id"], value["text"]
        names[code] = name
        if name.startswith("Region "):
            current = code
        elif code != "000" and current:
            region_of[code] = current
    return names, region_of


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    log("denmark: Statistics Denmark FOLK1A and KM6")

    meta = info("FOLK1A")
    quarter = next(v for v in meta["variables"] if v["id"] == "Tid")["values"][-1]["id"]
    names, region_of = areas(meta, "OMRÅDE")
    year = int(quarter[:4])
    date = {"1": "1 January", "2": "1 April", "3": "1 July", "4": "1 October"}[quarter[-1]]
    date = f"{date} {year}"
    rows = data("FOLK1A", {"OMRÅDE": ["*"], "KØN": ["*"], "ALDER": ["*"],
                           "CIVILSTAND": ["TOT"], "Tid": [quarter]})
    log(f"  FOLK1A {quarter}: {len(rows):,} rows")
    people: dict[str, AgeSex] = defaultdict(AgeSex)
    totals: dict[tuple[str, str], float] = {}
    for row in rows:
        area, sex, age = row["OMRÅDE"], row["KØN"], row["ALDER"]
        n = number(row["INDHOLD"])
        if age == "IALT":
            totals[(area, sex)] = n
        elif sex in ("1", "2"):
            people[area].add(int(age), "m" if sex == "1" else "f", n)
    for area, ages in people.items():
        for sex, got in (("1", ages.men), ("2", ages.women), ("TOT", ages.total)):
            if abs(got - totals.get((area, sex), -1)) > 0.5:
                raise SystemExit(f"FOLK1A {area} sex {sex}: single years make {got:,.0f}, "
                                 f"the table's total is {totals.get((area, sex))}")
    national = people["000"].total
    regions = sorted(c for c in names if names[c].startswith("Region "))
    kommuner = sorted(c for c in names if c != "000" and c not in regions)
    check_parts({c: people[c].total for c in regions}, national, "FOLK1A regions -> Denmark", 0)
    for region in regions:
        check_parts({c: people[c].total for c in kommuner if region_of.get(c) == region},
                    people[region].total, f"FOLK1A kommuner -> {names[region]}", 0)
    log(f"  Denmark {date}: {national:,.0f} people, median age {people['000'].median()}")
    # FOLK1A's quarter against Eurostat's 1 January of the same year: half a
    # year's ageing at most, well inside the bound.
    check_national_median("DK", year, people["000"].median(), f"FOLK1A {quarter} ({date})")

    # KM6: members and non-members of the National Church, 1 January.
    km_meta = info("KM6")
    km_year = next(v for v in km_meta["variables"] if v["id"] == "Tid")["values"][-1]["id"]
    km_rows = data("KM6", {"KOMK": ["*"], "KØN": ["*"], "ALDER": ["*"],
                           "FKMED": ["*"], "Tid": [km_year]})
    church: dict[str, dict[str, float]] = defaultdict(lambda: {"F": 0.0, "U": 0.0})
    for row in km_rows:
        church[row["KOMK"]][row["FKMED"]] += number(row["INDHOLD"])
    log(f"  KM6 {km_year}: {len(km_rows):,} rows, {len(church)} areas")
    missing = [c for c in kommuner if c not in church]
    if missing:
        raise SystemExit(f"KM6 has no row for kommuner {missing}")
    # Members and non-members must make the kommune's population on the same
    # day, which FOLK1A's first quarter of that year gives.
    same_day = {row["OMRÅDE"]: number(row["INDHOLD"]) for row in data(
        "FOLK1A", {"OMRÅDE": ["*"], "KØN": ["TOT"], "ALDER": ["IALT"],
                   "CIVILSTAND": ["TOT"], "Tid": [f"{km_year}K1"]})}
    off = [f"{names[c]}: {sum(church[c].values()):,.0f} against {same_day.get(c, 0):,.0f}"
           for c in kommuner if abs(sum(church[c].values()) - same_day.get(c, 0)) > 0.5]
    if off:
        raise SystemExit(f"KM6 members and non-members do not make FOLK1A {km_year}K1 in "
                         f"{len(off)} kommuner: " + "; ".join(off[:5]))
    log(f"    KM6 members and non-members make FOLK1A {km_year}K1 in all {len(kommuner)} kommuner")

    shapes = load_units("DNK", "admin2")
    parent_map = {u["id"]: u["name"] for u in load_units("DNK", "admin1")}
    region_names = {c: names[c].removeprefix("Region ").strip() for c in regions}
    bound, _missing, _left, _pieces = bind_rows(
        "DNK", "admin2",
        {c: (names[c], region_names[region_of[c]]) for c in kommuner}, aliases=ALIASES)
    labels = {s["id"]: s["name"] for s in shapes}
    admin1 = {fold(u["name"]): u for u in load_units("DNK", "admin1")}

    def religion(counts: dict[str, float]) -> dict[str, Any]:
        rows_ = {CHURCH: counts["F"], OUTSIDE: counts["U"]}
        return {
            "religion": shares(rows_),
            "religion_year": int(km_year),
            "religion_basis": "registered membership",
            "religion_note": (
                f"Membership of the Evangelical Lutheran Church in Denmark (Folkekirken) on 1 "
                f"January {km_year}, as the Civil Registration System records it for every "
                f"resident (Statistics Denmark, KM6): {int(counts['F']):,} members and "
                f"{int(counts['U']):,} non-members, who together make the whole population "
                f"on that day (FOLK1A {km_year}K1; the population shown here is of {date} "
                f"{year}). A count of registered membership, not of "
                "belief. Denmark registers no other denomination, so the non-members -- people "
                "of other faiths and of none alike -- are one group."),
        }

    records = []
    for code in kommuner:
        sid = bound.get(code)
        if sid is None:
            continue
        fields = people[code].fields(year=year, source=f"{SOURCE}, FOLK1A", url=FOLK1A_URL,
                                     date=date)
        fields.update(religion(church[code]))
        fields["sources"].append({"field": "religion", "name": f"{SOURCE}, KM6", "url": KM6_URL,
                                  "year": int(km_year)})
        records.append(record(
            f"DNK-DST-{code}", names[code], level="admin2", parent="DNK", country="DNK",
            parent_name=parent_map.get(next(s["parent"] for s in shapes if s["id"] == sid)),
            codes={"dst": code}, match_by="shape_id", shape_id=sid,
            aliases=[labels[sid]] if labels[sid] != names[code] else [], **fields))
    for region in regions:
        shape = admin1.get(fold(region_names[region]))
        if shape is None:
            raise SystemExit(f"denmark: region {names[region]!r} has no polygon")
        fields = people[region].fields(year=year, source=f"{SOURCE}, FOLK1A", url=FOLK1A_URL,
                                       date=date)
        members = {"F": 0.0, "U": 0.0}
        for code in kommuner:
            if region_of.get(code) == region:
                members["F"] += church[code]["F"]
                members["U"] += church[code]["U"]
        fields.update(religion(members))
        fields["sources"].append({"field": "religion", "name": f"{SOURCE}, KM6", "url": KM6_URL,
                                  "year": int(km_year)})
        records.append(record(
            f"DNK-DST-{region}", shape["name"], level="admin1", parent="DNK", country="DNK",
            codes={"dst": region}, match_by="shape_id", shape_id=shape["id"],
            aliases=[names[region]], **fields))
    log(f"  labels the group tree cannot place: {unplaced('religion', [CHURCH, OUTSIDE])}")
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
