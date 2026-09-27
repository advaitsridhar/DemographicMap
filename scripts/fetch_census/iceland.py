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
year. A municipality merged since 2017 takes its own last count there: 1
December 2017 for those merged in 2018 (Sandgerði, Garður, Breiðdalshreppur
and Fjarðabyggð, which took Breiðdalshreppur in), 2019 for the four that
formed Múlaþing in 2020, 2021 for those merged in 2022, and 2022 -- the
table's last year -- for those merged after it (Tálknafjörður and Vesturbyggð
in 2024). Which year that is is read from the table itself (``last_counts``):
a municipality's number stops, or the number is kept by one that took others
in (``ABSORBED``), and the people who vanish with the numbers that stop must
reappear in the region's new numbers, year by year, or the run stops. One
that has not been merged at all takes MAN02005's latest year instead: its
number, or where it was renumbered (Hornafjörður, 7708 in 2017) a new number
with its name, has a count for 1 January 2018 in today's division that is its
own of a month before, and it took in no other (``ABSORBED``,
``MERGED_RENUMBERED``: Fjarðabyggð, Skagafjörður and Stykkishólmur took in
neighbours too small to show in the count). Single years of age, with an
"unknown" row that is left out of the median and kept in the population.

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
from .nordic_common import (AgeSex, bind_rows, check_national_median, check_parts,
                            load_units, request_json)
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
PAUSE = 12.0                         # Hagstofa answers 429 to a brisker pace
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
# ...and the year each did, which is when its own territory ended.
ABSORBED_IN = {"7300": 2018}
# Municipalities that took in a small neighbour under a new number carrying
# their own name, which the name-and-count test below would read as a plain
# renumbering: Akrahreppur (about 200 people) is 5% of Skagafjörður, and
# Helgafellssveit (59) 5% of Stykkishólmur. The regional check below is what
# finds them: their people are missing from the region's merged total.
MERGED_RENUMBERED = {"5200": "Skagafjörður took in Akrahreppur in 2022, as 5716",
                     "3711": "Stykkishólmsbær took in Helgafellssveit in 2022, as 3716"}
# A municipality whose count today is not its people's usual home, and why.
EVACUATED = {"2300": (
    " Grindavík was evacuated on 10 November 2023, when the volcanic unrest on the "
    "Reykjanes peninsula began, and most of its residents have since registered a home "
    "elsewhere: {now:,} people were registered here on 1 January {year} against {then:,} on "
    "1 January 2023, so the age and sex figures are of the few who remain.")}
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


def yearly_totals(url: str, years: list[str]) -> dict[int, dict[str, float]]:
    """{year: {municipality: total}} from one query of a MAN table's totals."""
    body = request_json(url, {"query": [
        {"code": "Sveitarfélag", "selection": {"filter": "all", "values": ["*"]}},
        {"code": "Aldur", "selection": {"filter": "item", "values": ["-1"]}},
        {"code": "Ár", "selection": {"filter": "item", "values": years}},
        {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
    ], "response": {"format": "json-stat2"}}, pause=PAUSE)
    out: dict[int, dict[str, float]] = defaultdict(dict)
    for key, value in unstack(body):
        out[int(key["Ár"][0])][key["Sveitarfélag"][0]] = value
    return out


def last_counts(units: list[str], series: dict[int, dict[str, float]], names: dict[str, str],
                first: int = VINTAGE) -> dict[str, tuple[int, str]]:
    """Each 2017 municipality -> (the last year it stood whole, its number then).

    MAN09000 lays each year out in that year's municipalities. Year by year, a
    number that stops is either renumbered -- one new number with the same
    name and the same count takes it over -- or merged; a number kept by a
    municipality that took others in (``ABSORBED_IN``) ends that
    municipality's own territory too. The people of the numbers that stop by
    merger must reappear, region by region, in the new numbers and in what the
    absorbers gained, or the run stops: an unlisted absorber would leave its
    region short.
    """
    alive = set(units)
    current = {c: c for c in units}
    last = {c: (first, c) for c in units}
    for year in sorted(y for y in series if y > first):
        prev, now = series[year - 1], series[year]
        stopped = {k for k, v in prev.items() if v > 0 and now.get(k, 0) <= 0 and k != "9999"}
        started = {k for k, v in now.items() if v > 0 and prev.get(k, 0) <= 0 and k != "9999"}
        renumbered = {}
        for old in stopped - set(MERGED_RENUMBERED):
            twins = [new for new in started if stem(names.get(new, "")) == stem(names[old])
                     and abs(now[new] - prev[old]) <= 0.08 * prev[old] + 30]
            if len(twins) == 1:
                renumbered[old] = twins[0]
        absorbers = {c for c, y in ABSORBED_IN.items() if y == year}
        lost: dict[str, float] = defaultdict(float)
        found: dict[str, float] = defaultdict(float)
        slack: dict[str, float] = defaultdict(float)
        for old in stopped - set(renumbered):
            lost[REGION[old[0]]] += prev[old]
        for new in started - set(renumbered.values()):
            found[REGION[new[0]]] += now[new]
        for code in absorbers:
            found[REGION[code[0]]] += now.get(code, 0) - prev.get(code, 0)
            # an absorber's own year of births, deaths and moves
            slack[REGION[code[0]]] += 0.03 * prev.get(code, 0)
        short = {r: (lost[r], found[r]) for r in set(lost) | set(found)
                 if abs(lost[r] - found[r]) > 0.05 * lost[r] + 30 + slack[r]}
        if short:
            # Name the continuing numbers whose change comes closest to each
            # shortfall: an absorber not yet listed in ABSORBED_IN.
            hint = {}
            for r, (a, b) in short.items():
                kept = [k for k in now if k in prev and k not in stopped and k != "9999"
                        and REGION[k[0]] == r and prev[k] > 0]
                kept.sort(key=lambda k: abs((now[k] - prev[k]) - (a - b)))
                hint[r] = [f"{names.get(k, k)} {k} {prev[k]:,.0f}->{now[k]:,.0f}" for k in kept[:3]]
            raise SystemExit(f"MAN09000 {year}: the numbers that stopped "
                             f"{sorted(f'{names.get(k, k)} {k}' for k in stopped)} do not "
                             f"reappear in their region's new ones: {short}; closest "
                             f"continuing numbers: {hint}")
        for c in sorted(alive):
            code = current[c]
            if code in renumbered:
                current[c] = renumbered[code]
                last[c] = (year, current[c])
            elif code in stopped or code in absorbers:
                alive.discard(c)
            elif now.get(code, 0) > 0:
                last[c] = (year, code)
            else:
                alive.discard(c)
    return last


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
    check_national_median("IS", int(year), now_people["9999"].median(), f"MAN02005 {year}")
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

    # A merged municipality's last count of its own: the last 1 December
    # MAN09000 has it whole, in that year's division.
    old_meta = {v["code"]: v for v in request_json(OLD, pause=PAUSE)["variables"]}
    old_years = [y for y in old_meta["Ár"]["values"] if int(y) >= VINTAGE]
    series = yearly_totals(OLD, old_years)
    merged = sorted(c for c in units if c not in today)
    lasts = last_counts(merged, series, names)
    by_year: dict[int, tuple[dict[str, AgeSex], dict[str, float]]] = {
        VINTAGE: (people, totals)}
    for y in sorted({y for y, _ in lasts.values()} - {VINTAGE}):
        got, got_totals, _ = read(OLD, str(y))
        by_year[y] = (got, got_totals)
    log("  merged municipalities' last own count (1 December): "
        + "; ".join(f"{names[c]} {y}" + (f" as {n}" if n != c else "")
                    for c, (y, n) in sorted(lasts.items(), key=lambda kv: kv[1][0])))
    last_year = max(int(y) for y in old_years)
    # Grindavík was evacuated on 10 November 2023 and most of its people have
    # registered elsewhere since: its count today is a quarter of 2023's,
    # which is what the note must say rather than leave to look like an error.
    before = {key["Sveitarfélag"][0]: value for key, value in unstack(request_json(NOW, {
        "query": [
            {"code": "Sveitarfélag", "selection": {"filter": "item", "values": list(EVACUATED)}},
            {"code": "Aldur", "selection": {"filter": "item", "values": ["-1"]}},
            {"code": "Ár", "selection": {"filter": "item", "values": ["2023"]}},
            {"code": "Kyn", "selection": {"filter": "item", "values": ["0"]}},
        ], "response": {"format": "json-stat2"}}, pause=PAUSE))}

    records = []
    for code in units:
        sid = bound.get(code)
        if sid is None:
            continue
        if code in today:
            n = today[code]
            note = (f" The municipality has not been merged since {VINTAGE}, the division the "
                    "map draws, so this is its latest count.")
            if code in EVACUATED and before.get(n):
                note += EVACUATED[code].format(now=int(round(now_totals[n])), year=year,
                                               then=int(round(before[n])))
            fields = now_people[n].fields(
                year=int(year), source=f"{SOURCE}, MAN02005", url=NOW_URL,
                date=f"1 January {year}", extra_note=note)
            fields["population"]["value"] = int(round(now_totals[n]))
        else:
            y, n = lasts[code]
            got, got_totals = by_year[y]
            if got_totals.get(n, 0) <= 0:
                raise SystemExit(f"MAN09000 {y}: no count for {names[code]} ({n})")
            fields = got[n].fields(
                year=y, source=f"{SOURCE}, MAN09000", url=OLD_URL, date=f"1 December {y}",
                extra_note=(
                    f" The municipality as the map draws it (the division of {VINTAGE}), at its "
                    + ("last count before it was merged." if y < last_year else
                       f"last count in this table, which ends in {last_year}; it was merged "
                       "later.")
                    + (f" {ABSORBED[code]}, so its own territory ends in {VINTAGE}."
                       if code in ABSORBED else "")))
            fields["population"]["value"] = int(round(got_totals[n]))
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
        # A municipality renumbered into another region since 2017 is summed
        # where the map draws it, and the note says which way it went.
        came = sorted(now_names[n] for n in drawn_in
                      if drawn_in[n] == region and REGION[n[0]] != region)
        went = sorted(f"{now_names[n]} (drawn in the {drawn_in[n]})" for n in drawn_in
                      if REGION[n[0]] == region and drawn_in[n] != region)
        fields = ages.fields(year=int(year), source=f"{SOURCE}, MAN02005", url=NOW_URL,
                             date=f"1 January {year}", extra_note=(
                                 " Summed from the municipalities the map draws in the region."
                                 + (f" That includes {', '.join(came)}, which Hagstofa has "
                                    "numbered in another region since it was renumbered."
                                    if came else "")
                                 + (f" It leaves out {', '.join(went)}, which Hagstofa now "
                                    "numbers here." if went else "")))
        fields["population"]["value"] = int(round(region_total[region]))
        records.append(record(
            f"ISL-HAG-{fold(region)}", shape["name"], level="admin1", parent="ISL",
            country="ISL", match_by="shape_id", shape_id=shape["id"], **fields))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
