#!/usr/bin/env python3
"""Iceland: the 2013-2018 municipalities and the eight regions, from Statistics Iceland.

**What the map draws.** The admin2 layer is Iceland's municipalities between
two mergers: Álftanes has already joined Garðabær (1 January 2013), while
Sandgerði and Garður (merged into Suðurnesjabær in June 2018), Breiðdalshreppur
(into Fjarðabyggð, June 2018) and the four that formed Múlaþing in 2020 are
still their own. Seventy-four municipalities in all; the layer draws 73, with
no polygon for Vestmannaeyjar. Hagstofa's current tables are laid out in
today's 62 municipalities, which is the wrong vintage for every merged one.

**admin2** -- table MAN09000 ("Population by municipality, age and sex 1
December 1997-2022"), which keeps every year in the municipalities of that
year. The figures are for 1 December 2017, the last count before the 2018
mergers. Single years of age 0-110, with an "unknown" row that is left out of
the median and kept in the population.

**admin1** -- the eight regions (landshlutar), which have not changed. Table
MAN02005 (current municipalities, 1 January of each year) for the latest year,
summed by the region every municipality's number begins with -- the
statistical numbering Hagstofa gives municipalities: 0 and 1 the capital
region, 2 Suðurnes, 3 the West, 4 the Westfjords, 5 the Northwest, 6 the
Northeast, 7 the East, 8 the South. The regions must make the country.

**Religion** is registered for everyone (Registers Iceland's record of
religious and life-stance organisations) and Hagstofa publishes it; whether
below the country is read from its table list, and written only if so.
**Language** and **ethnicity** are the existing policy.

Usage:
    python -m scripts.fetch_census.iceland
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from ._shared import PROCESSED, log, record, write_json
from .binding import fold
from .nordic_common import AgeSex, bind_rows, check_parts, load_units, request_json
from .pxweb import unstack

BASE = "https://px.hagstofa.is/pxen/api/v1/en/Ibuar/mannfjoldi/2_byggdir"
OLD = f"{BASE}/x_eldraefni/MAN09000.px"
NOW = f"{BASE}/sveitarfelog/MAN02005.px"
SOURCE = "Statistics Iceland"
OLD_URL = ("https://px.hagstofa.is/pxen/pxweb/en/Ibuar/Ibuar__mannfjoldi__2_byggdir__"
           "x_eldraefni/MAN09000.px")
NOW_URL = ("https://px.hagstofa.is/pxen/pxweb/en/Ibuar/Ibuar__mannfjoldi__2_byggdir__"
           "sveitarfelog/MAN02005.px")
OUT = PROCESSED / "iceland_municipality.json"
PAUSE = 6.0                          # Hagstofa answers 429 to a brisker pace
VINTAGE = 2017

REGION = {"0": "Capital Region", "1": "Capital Region", "2": "Southern Peninsula",
          "3": "Western Region", "4": "Westfjords", "5": "Northwestern Region",
          "6": "Northeastern Region", "7": "Eastern Region", "8": "Southern Region"}
# Hagstofa's name -> the boundary file's, where they differ by more than
# accents: two municipalities it calls a town (bær) and the office a
# kaupstaður or the reverse, and two names the boundary file cuts off.
ALIASES = {"Hafnarfjarðarkaupstaður": "Hafnarfjarðarbær",
           "Akureyrarbær": "Akureyrarkaupstaður",
           "Sveitarfélagið Hornafjörður": "Sveitarfélagið Hornafjörðu",
           "Sveitarfélagið Skagafjörður": "Sveitarfélagið Skagafjörðu"}


def read(url: str, year: str) -> tuple[dict[str, AgeSex], dict[str, float], dict[str, str]]:
    meta = {v["code"]: v for v in request_json(url, pause=PAUSE)["variables"]}
    muni, age, when, sex = "Sveitarfélag", "Aldur", "Ár", "Kyn"
    names = dict(zip(meta[muni]["values"], meta[muni]["valueTexts"]))
    body = request_json(url, {"query": [
        {"code": muni, "selection": {"filter": "all", "values": ["*"]}},
        {"code": age, "selection": {"filter": "all", "values": ["*"]}},
        {"code": when, "selection": {"filter": "item", "values": [year]}},
        {"code": sex, "selection": {"filter": "all", "values": ["*"]}},
    ], "response": {"format": "json-stat2"}}, pause=PAUSE)
    people: dict[str, AgeSex] = defaultdict(AgeSex)
    totals: dict[str, float] = defaultdict(float)
    # Beside males and females: people of unknown age (MAN09000's "150") and,
    # since 2021, a third registered sex ("Non-binary/Other"). Both are in the
    # total; neither can be placed in a median or a ratio of men to women.
    aside: dict[str, float] = defaultdict(float)
    for key, value in unstack(body):
        code, a, s = key[muni][0], key[age][0], key[sex][0]
        if a == "-1":
            if s == "0":
                totals[code] = value
            elif s not in ("1", "2"):
                aside[code] += value
        elif a == "150":
            if s in ("1", "2"):
                aside[code] += value
        elif s in ("1", "2"):
            people[code].add(int(a), "m" if s == "1" else "f", value)
    for code, got in people.items():
        if abs(got.total + aside[code] - totals.get(code, 0)) > 0.5:
            raise SystemExit(f"{url.rsplit('/', 1)[-1]} {year} {code}: ages make "
                             f"{got.total:,.0f} and {aside[code]:,.0f} are set aside, "
                             f"against a total of {totals.get(code, 0):,.0f}")
    return people, totals, names


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    log(f"iceland: Hagstofa MAN09000 ({VINTAGE}) and MAN02005 (latest)")
    people, totals, names = read(OLD, str(VINTAGE))
    units = sorted(c for c, n in totals.items() if c != "9999" and n > 0)
    check_parts({c: totals[c] for c in units}, totals["9999"],
                f"MAN09000 {VINTAGE}: municipalities -> Iceland", 0)
    log(f"  {len(units)} municipalities on 1 December {VINTAGE}")
    shapes = load_units("ISL", "admin2")
    labels = {s["id"]: s["name"] for s in shapes}
    bound, _m, _l, _p = bind_rows("ISL", "admin2",
                                  {c: (names[c], REGION[c[0]]) for c in units}, aliases=ALIASES)
    records = []
    date = f"1 December {VINTAGE}"
    for code in units:
        sid = bound.get(code)
        if sid is None:
            continue
        fields = people[code].fields(
            year=VINTAGE, source=f"{SOURCE}, MAN09000", url=OLD_URL, date=date,
            extra_note=(" The municipality as it stood in 2017, before the mergers of 2018, "
                        "which is the unit the map draws."))
        fields["population"]["value"] = int(round(totals[code]))
        records.append(record(
            f"ISL-HAG-{VINTAGE}-{code}", names[code], level="admin2", parent="ISL",
            country="ISL", parent_name=REGION[code[0]], codes={"hagstofa": code,
                                                              "vintage": VINTAGE},
            match_by="shape_id", shape_id=sid,
            aliases=[labels[sid]] if labels[sid] != names[code] else [], **fields))

    # The regions, from today's municipalities.
    meta = {v["code"]: v for v in request_json(NOW, pause=PAUSE)["variables"]}
    year = meta["Ár"]["values"][-1]
    now_people, now_totals, now_names = read(NOW, year)
    now_units = sorted(c for c, n in now_totals.items() if c != "9999" and n > 0)
    regions: dict[str, AgeSex] = defaultdict(AgeSex)
    region_total: dict[str, float] = defaultdict(float)
    for code in now_units:
        regions[REGION[code[0]]] += now_people[code]
        region_total[REGION[code[0]]] += now_totals[code]
    check_parts(dict(region_total), now_totals["9999"], f"MAN02005 {year}: regions -> Iceland", 0)
    admin1 = {fold(u["name"]): u for u in load_units("ISL", "admin1")}
    for region, ages in sorted(regions.items()):
        shape = admin1.get(fold(region))
        if shape is None:
            raise SystemExit(f"iceland: region {region!r} has no polygon")
        fields = ages.fields(year=int(year), source=f"{SOURCE}, MAN02005", url=NOW_URL,
                             date=f"1 January {year}", extra_note=(
                                 " Summed from the region's municipalities, which Hagstofa "
                                 "numbers by region."))
        fields["population"]["value"] = int(round(region_total[region]))
        records.append(record(
            f"ISL-HAG-{fold(region)}", shape["name"], level="admin1", parent="ISL",
            country="ISL", match_by="shape_id", shape_id=shape["id"], **fields))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
