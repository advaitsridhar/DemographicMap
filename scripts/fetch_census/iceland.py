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
year: 1 December 2017, the last count before the 2018 mergers, for every
municipality merged since. One that has not been takes MAN02005's latest year
instead: its number, or where it was renumbered (Hornafjörður, 7708 in
2017) a new number with its name, has a count for 1 January 2018 in today's
division that is its own of a month before, and it took in no other
(``ABSORBED``, ``MERGED_RENUMBERED``: Fjarðabyggð and Skagafjörður took in
neighbours too small to show in the count). Single years
of age, with an "unknown" row that is left out of the median and kept in the
population.

**admin1** -- the eight regions (landshlutar), which have not changed. Table
MAN02005 (current municipalities, 1 January of each year) for the latest year,
summed by the region every municipality's number begins with -- the
statistical numbering Hagstofa gives municipalities: 0 and 1 the capital
region, 2 Suðurnes, 3 the West, 4 the Westfjords, 5 the Northwest, 6 the
Northeast, 7 the East, 8 the South. A municipality renumbered into another
region since 2017 is summed into the region the map draws it in, which is
the one its 2017 number gives. The regions must make the country.

**Religion** is registered for everyone (Registers Iceland's record of
religious and life-stance organisations) and Hagstofa publishes it; whether
below the country is read from its table list, and written only if so.
**Language** and **ethnicity** are the existing policy.

Usage:
    python -m scripts.fetch_census.iceland
"""

from __future__ import annotations

import argparse
import re
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
# Municipalities that kept their number while taking in another after 2017,
# a municipality too small to show in the count (Breiðdalshreppur, 4% of
# Fjarðabyggð). A merger otherwise gets a new number (Suðurnesjabær 2510,
# Múlaþing 7400, Skagafjörður 5716, Húnabyggð 5613), or takes one whose count
# then jumps (the Vesturbyggð of 2024 on Tálknafjarðarhreppur's 4604).
ABSORBED = {"7300": "Fjarðabyggð took in Breiðdalshreppur in 2018"}
# Municipalities that took in a small neighbour under a new number carrying
# their own name, which the name-and-count test below would read as a plain
# renumbering: Akrahreppur (about 200 people) is 5% of Skagafjörður.
MERGED_RENUMBERED = {"5200": "Skagafjörður took in Akrahreppur in 2022, as 5716"}
# Hagstofa's name -> the boundary file's, where they differ by more than
# accents: two municipalities it calls a town (bær) and the office a
# kaupstaður or the reverse, and two names the boundary file cuts off.
ALIASES = {"Hafnarfjarðarkaupstaður": "Hafnarfjarðarbær",
           "Akureyrarbær": "Akureyrarkaupstaður",
           "Sveitarfélagið Hornafjörður": "Sveitarfélagið Hornafjörðu",
           "Sveitarfélagið Skagafjörður": "Sveitarfélagið Skagafjörðu"}


def stem(name: str) -> str:
    """A municipality's name, folded to its first six letters without the
    generic "Sveitarfélagið". MAN02005 answers in ASCII ("Sveitarfelagid
    Hornafjordur") where MAN09000 keeps the Icelandic letters, so ð, þ and æ
    are spelled out before the prefix is taken off."""
    folded = fold(name).replace("ð", "d").replace("þ", "th").replace("æ", "ae")
    return re.sub(r"^sveitarfelagid", "", folded)[:6]


def read(url: str, year: str) -> tuple[dict[str, AgeSex], dict[str, float], dict[str, str]]:
    meta = {v["code"]: v for v in request_json(url, pause=PAUSE)["variables"]}
    muni, age, when, sex = "Sveitarfélag", "Aldur", "Ár", "Kyn"
    # Hagstofa tells a municipality from its successor of the same name by a
    # note on the label -- "Þingeyjarsveit (fyrir 2022)", before 2022 -- which
    # is about the row and not part of the place's name.
    names = {code: re.sub(r"\s*\((?:fyrir|eftir) \d{4}\)\s*$", "", text)
             for code, text in zip(meta[muni]["values"], meta[muni]["valueTexts"])}
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
    # Today's municipalities, which the regions below are summed from, and
    # which also say which 2017 municipalities are unchanged. MAN02005 lays
    # every year out in today's division, so its count for 1 January 2018 is,
    # for an unchanged municipality, its own count of a month before: within
    # 8%, since MAN02005's are recomputed by the method Hagstofa adopted in
    # 2024 (the largest gap is 5%), where a merger adds a whole municipality.
    meta = {v["code"]: v for v in request_json(NOW, pause=PAUSE)["variables"]}
    year = meta["Ár"]["values"][-1]
    now_people, now_totals, now_names = read(NOW, year)
    then = {key["Sveitarfélag"][0]: value for key, value in unstack(request_json(NOW, {"query": [
        {"code": "Sveitarfélag", "selection": {"filter": "all", "values": ["*"]}},
        {"code": "Aldur", "selection": {"filter": "item", "values": ["-1"]}},
        {"code": "Ár", "selection": {"filter": "item", "values": [str(VINTAGE + 1)]}},
        {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
    ], "response": {"format": "json-stat2"}}, pause=PAUSE))}

    def same(c: str, n: str) -> bool:
        return abs(then.get(n, 0) - totals[c]) <= 0.08 * totals[c] + 30

    now_units = sorted(c for c, n in now_totals.items() if c != "9999" and n > 0)
    today: dict[str, str] = {}
    kept_number = []
    for c in units:
        if c in ABSORBED or c in MERGED_RENUMBERED:
            continue
        if c in now_totals:
            # Its own number: the same territory if the count agrees, else
            # the number went to a merger (Tálknafjarðarhreppur's 4604, which
            # the Vesturbyggð of 2024 took).
            if same(c, c):
                today[c] = c
            else:
                kept_number.append(f"{names[c]} {c}: {then.get(c, 0):,.0f} against "
                                   f"{totals[c]:,.0f}")
            continue
        # A new number: renumbered if a number not held in 2017 carries the
        # same name and the same count.
        found = [n for n in now_units if n not in units and stem(now_names[n]) == stem(names[c])
                 and same(c, n)]
        if len(found) == 1:
            today[c] = found[0]
    log(f"  {len(today)} of {len(units)} municipalities are the same territory today; "
        f"renumbered: {sorted(f'{names[c]} {c}->{n}' for c, n in today.items() if n != c)}; "
        f"number taken by a merger: {kept_number}; "
        f"merged: {sorted(names[c] for c in units if c not in today)}")
    drift = sorted((abs(then[n] - totals[c]) / totals[c], names[c]) for c, n in today.items())
    log(f"  1 January {VINTAGE + 1} in today's division against 1 December {VINTAGE}: "
        "largest gaps " + ", ".join(f"{m} {100 * d:.1f}%" for d, m in drift[-5:]))
    # The people of the merged municipalities must be in today's other
    # municipalities, region by region; one that vanished into a municipality
    # counted as unchanged here, or a renumbering across regions not found
    # above, leaves a region short.
    lost: dict[str, float] = defaultdict(float)
    found_in: dict[str, float] = defaultdict(float)
    for c in units:
        if c not in today:
            lost[REGION[c[0]]] += totals[c]
    images = set(today.values())
    for n in now_units:
        if n not in images:
            found_in[REGION[n[0]]] += then.get(n, 0)
    short = {r: (lost[r], found_in[r]) for r in set(lost) | set(found_in)
             if abs(lost[r] - found_in[r]) > 0.05 * lost[r] + 30}
    log("  merged municipalities, 1 December 2017 against today's in 1 January 2018: "
        + ", ".join(f"{r} {lost[r]:,.0f}/{found_in[r]:,.0f}" for r in sorted(lost)))
    if short:
        raise SystemExit(f"iceland: merged municipalities do not make today's: {short}")

    records = []
    date = f"1 December {VINTAGE}"
    for code in units:
        sid = bound.get(code)
        if sid is None:
            continue
        if code in today:
            fields = now_people[today[code]].fields(
                year=int(year), source=f"{SOURCE}, MAN02005", url=NOW_URL,
                date=f"1 January {year}", extra_note=(
                    f" The municipality has not been merged since {VINTAGE}, the division the "
                    "map draws, so this is its latest count."))
            fields["population"]["value"] = int(round(now_totals[today[code]]))
        else:
            fields = people[code].fields(
                year=VINTAGE, source=f"{SOURCE}, MAN09000", url=OLD_URL, date=date,
                extra_note=(f" The municipality as it stood in {VINTAGE}, which is the unit "
                            "the map draws; it has since been merged."))
            fields["population"]["value"] = int(round(totals[code]))
        records.append(record(
            f"ISL-HAG-{VINTAGE}-{code}", names[code], level="admin2", parent="ISL",
            country="ISL", parent_name=REGION[code[0]], codes={"hagstofa": code,
                                                              "vintage": VINTAGE},
            match_by="shape_id", shape_id=sid,
            aliases=[labels[sid]] if labels[sid] != names[code] else [], **fields))

    # The regions, from today's municipalities.
    regions: dict[str, AgeSex] = defaultdict(AgeSex)
    region_total: dict[str, float] = defaultdict(float)
    drawn_in = {n: REGION[c[0]] for c, n in today.items()}
    moved = sorted(f"{now_names[n]} ({drawn_in[n]}, numbered in {REGION[n[0]]})"
                   for n in drawn_in if REGION[n[0]] != drawn_in[n])
    log(f"  summed into the region the map draws them in, not their number's: {moved}")
    for code in now_units:
        region = drawn_in.get(code, REGION[code[0]])
        regions[region] += now_people[code]
        region_total[region] += now_totals[code]
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
