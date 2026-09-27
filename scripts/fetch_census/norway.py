#!/usr/bin/env python3
"""Norway: the 2017 kommuner and the 2020-2023 fylker, from Statistics Norway.

**What the map draws.** The admin2 layer is Norway's kommuner as they stood in
2017: Sandefjord already holds Andebu and Stokke (merged 1 January 2017), while
Nøtterøy and Tjøme, Hof, Lardal, Rissa and Leksvik are still their own
(merged 1 January 2018) -- 426 kommuner in all. The layer has 424 polygons:
five of them are small pieces of Frogn, Horten, Malvik and Nome drawn beside
the kommune itself, and a few small island kommuner have no polygon; the run
log names both. The admin1 layer is the eleven fylker of 2020-2023, three of
which (Viken, Vestfold og Telemark, Troms og Finnmark) were split again on 1
January 2024 and so have no current figure at all.

So every figure here is for those units' own vintage:

* **admin2** -- SSB table 07459 (population by region, sex and single year of
  age, 1 January). A kommune that no merger or split has touched since 2017
  -- KLASS's list of changes shows only renumberings for it, one old code to
  one new -- takes the latest year under its current number. One that was
  merged or split takes its last count whole: 1 January of the year before
  the change, under the number it had then (``lineage``) -- 2017 for the
  mergers of 2018 (Hof, Lardal, Nøtterøy, Tjøme, Rissa, Leksvik and the
  kommuner they joined), 2019 for those of 2020, 2023 for the splits of 2024.
  Median age and sex ratio from the single years; population from the same
  count.
* **admin1** -- 07459 for 2023 by the codes of the three 2020-2023 fylker
  (30, 38, 54), the last year they existed. The other eight fylker did not
  change in 2024 -- no kommune has changed its fylke digits since 2023 in
  KLASS's list of changes, which is checked -- and take 07459's latest year.
* **religion** -- SSB table 12026 (KOSTRA, "church users"), which gives for
  every kommune and fylke the members of the Church of Norway, the members of
  the faith and life-stance communities outside it, and the population. That
  covers everyone: the remainder are members of neither. It is registered
  membership, not belief, and the note says so. SSB publishes the communities
  outside the Church by religion only by fylke, so at kommune level they are
  one group. KOSTRA reports each year on that year's kommuner, so a kommune
  takes the latest year that still counts the communities outside the Church,
  or its own last whole year if that is earlier. SSB places the Church's
  members by parish, and its note on 12026 says Frøyland and Orstad parish
  spans Klepp and Time, so the split between those two "may be uncertain":
  their figures bear it out (Klepp 0.6% in no community in 2020, Time 30.5%)
  and are not given (``SPLIT_PARISH``); a remainder under 3% anywhere else
  would be left out the same way. Members outside the Church are counted
  where the state grant is paid for them (SSB's note on 08531). For
  the fylker, 2023 for the three dissolved in
  2024 and, for the eight that were not, the latest year in which KOSTRA
  still counts the communities outside the Church (it leaves them at 0 in its
  most recent years, which is a gap and not a count of none). A fylke is the sum of
  its kommuner that year: KOSTRA's own fylke rows leave the communities
  outside the Church at 0. For a fylke, SSB table 08531 (closed series,
  2010-2020) splits the communities outside the Church by religion --
  Buddhism, Islam, Christian communities, other religions, life-stance
  communities -- and its total must equal the kommuner's sum before it is
  used.

**Language** is recorded by no Norwegian register or census, and ethnicity is
the existing policy (immigrant background only).

Checks: single years make each kommune's published total; the kommuner make
the country; members of the Church and of other communities never exceed the
population they are a share of.

Usage:
    python -m scripts.fetch_census.norway
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, record, shares, write_json
from .binding import fold
from .nordic_common import (AgeSex, bind_rows, check_national_median, check_parts,
                            load_units, request_json,
                            unplaced)
from .pxweb import unstack

SSB = "https://data.ssb.no/api/v0/en/table"
KLASS = "https://data.ssb.no/api/klass/v1/classifications/131/codesAt.json?date={date}"
SOURCE = "Statistics Norway (SSB)"
POP_URL = "https://www.ssb.no/en/statbank/table/07459"
CHURCH_URL = "https://www.ssb.no/en/statbank/table/12026"
OUT = PROCESSED / "norway_kommune.json"

VINTAGE = 2017                 # the kommuner the map draws
FYLKE_YEAR = 2023              # the last year the 2020-2023 fylker existed
SPLIT_FYLKER = ("30", "38", "54")
FYLKER = ("03", "11", "15", "18", "30", "34", "38", "42", "46", "50", "54")

CHURCH = "Church of Norway"
# Neither of these names a religion, and the group tree is asked (shared.patch)
# to file both with the answers that do not: one welds together every faith
# and life stance outside the Church, the other everyone registered in none.
OTHER = "Member of another faith or life-stance community"
NONE = "Not a member of a registered faith or life-stance community"

# The boundary file names these kommuner by their official Sami (or Kven) name
# alone, where KLASS may list only the Norwegian one.
ALIASES = {"Tysfjord": "Divtasvuodna", "Fauske": "Fuossko", "Hamarøy": "Hábmer",
           "Røyrvik": "Raarvihke", "Snåsa": "Snåase", "Porsanger": "Porsáŋgu",
           "Tana": "Deatnu", "Nesseby": "Unjárga", "Karasjok": "Kárášjohka",
           "Kautokeino": "Guovdageaidnu", "Lavangen": "Loabák", "Storfjord": "Omasvuotna"}

# The boundary file tags each name with its language and a number:
# '"Evje og Hornnes" nor', 'Guovdageaidnu sme 1', 'Kåfjord nor 2'.
TAG = re.compile(r"\s+(?:nor|nno|nob|sme|smj|sma|fkv)(?:\s+\d+)?$")


def map_name(shape: dict[str, Any]) -> str:
    return TAG.sub("", shape["name"]).strip().strip('"').strip()


def office_names(label: str) -> list[str]:
    """'Kautokeino - Guovdageaidnu' -> both forms; a '(2017-2019)' span is dropped.

    A county qualifier -- 'Våler (Østfold)' -- is kept on the first form and
    offered bare as well: the boundary file writes plain 'Våler' twice, and
    the kommune's county code is what tells the two apart when binding.
    """
    label = re.sub(r"\s*\((?:-?\d{4}(?:-\d{4})?-?)\)\s*$", "", label).strip()
    forms = [part.strip() for part in label.split(" - ") if part.strip()]
    bare = [re.sub(r"\s*\([^()]*\)\s*$", "", f).strip() for f in forms]
    return list(dict.fromkeys(forms + [b for b in bare if b]))


def query(table: str, selections: dict[str, list[str]]) -> dict[str, Any]:
    return request_json(f"{SSB}/{table}", {
        "query": [{"code": k, "selection": {"filter": "item", "values": v}}
                  for k, v in selections.items()],
        "response": {"format": "json-stat2"}})


def ages_by_region(codes: list[str], year: int) -> tuple[dict[str, AgeSex], dict[str, float]]:
    meta = {v["code"]: v for v in request_json(f"{SSB}/07459")["variables"]}
    ages = meta["Alder"]["values"]
    body = query("07459", {"Region": codes, "Kjonn": ["1", "2"], "Alder": ages,
                           "ContentsCode": ["Personer1"], "Tid": [str(year)]})
    people: dict[str, AgeSex] = defaultdict(AgeSex)
    for key, value in unstack(body):
        age = key["Alder"][0]
        people[key["Region"][0]].add(int(age.rstrip("+")), "m" if key["Kjonn"][0] == "1" else "f",
                                     value)
    totals = {key["Region"][0]: value for key, value in unstack(query(
        "07459", {"Region": codes, "ContentsCode": ["Personer1"], "Tid": [str(year)]}))}
    for code, got in people.items():
        if abs(got.total - totals.get(code, -1)) > 0.5:
            raise SystemExit(f"07459 {year} {code}: single years make {got.total:,.0f}, the "
                             f"table's total is {totals.get(code)}")
    return people, totals


def membership(codes: list[str], year: int) -> dict[str, dict[str, float]]:
    body = query("12026", {"KOKkommuneregion0000": codes,
                           "ContentsCode": ["KOSmedlemmerdnk0000", "KOSmedltroslivs0000",
                                            "KOSpersoneralle0000"],
                           "Tid": [str(year)]})
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for key, value in unstack(body):
        out[key["KOKkommuneregion0000"][0]][key["ContentsCode"][0]] = value
    return out


# How SSB places the two counts, in its own notes. The Church's members are
# placed by their parish (sokn): 12026's note says that "Frøyland and Orstad
# parish spans the municipalities of Klepp and Time. Consequently, figures on
# the distribution of members between these municipalities may be uncertain"
# -- and in 2020 Klepp's read 86.4% in the Church and 0.6% in no community,
# Time's 59.5% and 30.5%, against 75% and 13% for both in 2016. The members
# outside the Church are those "for whom government subsidy is received"
# (08531's note), which is what KOSTRA's kommune rows sum to.
PLACEMENT_NOTE = (" SSB places the Church's members by their parish, and counts members of "
                  "the communities outside it only where the state grant is paid for them.")
SPLIT_PARISH = {"1120": "Klepp", "1121": "Time"}
SPLIT_PARISH_NOTE = (
    "Not given: SSB places the Church of Norway's members by parish, and notes on table 12026 "
    "that 'Frøyland and Orstad parish spans the municipalities of Klepp and Time. Consequently, "
    "figures on the distribution of members between these municipalities may be uncertain and "
    "should be interpreted with caution.' The figures bear it out: in 2020 Klepp's read 86.4% "
    "in the Church and 0.6% in no registered community, Time's 59.5% and 30.5%.")
# The remainder -- people in no registered community -- is at least 5.7% in
# every kommune but Klepp. One below 3% is a placement across a kommune
# boundary rather than a count, and is not published.
NONE_FLOOR = 0.03


def religion(counts: dict[str, float], year: int, where: str) -> dict[str, Any] | None:
    church = counts.get("KOSmedlemmerdnk0000")
    other = counts.get("KOSmedltroslivs0000")
    people = counts.get("KOSpersoneralle0000")
    if not church or other is None or not people:
        return None
    if other == 0 and people > 5000:
        log(f"  12026 {where} {year}: no members outside the Church among {people:,.0f} "
            "people -- not published rather than none; left out")
        return None
    if church + other > people:
        raise SystemExit(f"12026 {where} {year}: {church + other:,.0f} members against a "
                         f"population of {people:,.0f}")
    none = people - church - other
    if none < NONE_FLOOR * people:
        log(f"  12026 {where} {year}: {none:,.0f} of {people:,.0f} people in no registered "
            f"community ({100 * none / people:.1f}%), under the {100 * NONE_FLOOR:.0f}% floor; "
            "left out as a placement across a boundary")
        return None
    rows = {CHURCH: church, OTHER: other, NONE: none}
    return {
        "religion": shares(rows, total=people),
        "religion_year": year,
        "religion_basis": "registered membership",
        "religion_note": (
            f"Registered membership at the end of {year} (SSB table 12026, KOSTRA): "
            f"{int(church):,} members of the Church of Norway and {int(other):,} members of "
            f"faith and life-stance communities outside it, of a population of {int(people):,}; "
            "the rest belong to neither. A count of membership, not of belief. SSB publishes "
            "the communities outside the Church by religion only by fylke, so here they are "
            "one group." + PLACEMENT_NOTE),
    }


# SSB 08531's religions and life stances outside the Church of Norway, by
# fylke, 2010-2020 (a closed series). "Christianity" there is every Christian
# community outside the Church -- Catholic above all, Pentecostal, Orthodox
# and the free churches together -- so its label says so; "Philosophy" is the
# life-stance communities, the Humanist Association above all.
KINDS = {"200": "Buddhism", "400": "Islam",
         "600": "Christian communities outside the Church of Norway",
         "902": "Other religion", "900": "Humanist and other life-stance communities"}
FAITHS_URL = "https://www.ssb.no/en/statbank/table/08531"


def faith_by_fylke() -> dict[tuple[str, int], dict[str, float]]:
    """(fylke, year) -> members outside the Church by religion or life stance."""
    meta = {v["code"]: v for v in request_json(f"{SSB}/08531")["variables"]}
    body = query("08531", {"Region": list(FYLKER), "ReligionLivs": ["999", *KINDS],
                           "ContentsCode": ["Medlemmer"], "Tid": meta["Tid"]["values"]})
    out: dict[tuple[str, int], dict[str, float]] = defaultdict(dict)
    for key, value in unstack(body):
        out[(key["Region"][0], int(key["Tid"][0]))][key["ReligionLivs"][0]] = value
    # A cell with no total (Oslo's in 2010 reads 0 beside 108,734 by
    # religion) is not used; every one that is used must make its total.
    used = {k: v for k, v in out.items() if v.get("999")}
    for (f, year), kinds in used.items():
        parts = sum(v for k, v in kinds.items() if k != "999")
        if abs(parts - kinds["999"]) > 0.5:
            raise SystemExit(f"08531 {f} {year}: religions make {parts:,.0f} of "
                             f"{kinds['999']:,.0f}")
    return used


def religion_by_kind(counts: dict[str, float], kinds: dict[str, float], year: int,
                     where: str) -> dict[str, Any]:
    """A fylke's membership with the communities outside the Church by religion.

    08531 counts the same register as KOSTRA's summed kommuner, and must agree
    with it before one is split by the other."""
    church = counts["KOSmedlemmerdnk0000"]
    other = counts["KOSmedltroslivs0000"]
    people = counts["KOSpersoneralle0000"]
    if abs(kinds["999"] - other) > 0.5:
        raise SystemExit(f"08531 {where} {year}: {kinds['999']:,.0f} members outside the "
                         f"Church against KOSTRA's {other:,.0f}")
    rows = {CHURCH: church, NONE: people - church - other}
    rows.update({KINDS[k]: v for k, v in kinds.items() if k in KINDS})
    return {
        "religion": shares(rows, total=people),
        "religion_note": (
            f"Registered membership at the end of {year}: {int(church):,} members of the "
            f"Church of Norway (SSB table 12026, KOSTRA, summed over the fylke's kommuner) and "
            f"{int(other):,} members of faith and life-stance communities outside it, by "
            f"religion (SSB table 08531), of a population of {int(people):,}; the rest belong "
            "to neither. A count of membership, not of belief." + PLACEMENT_NOTE),
    }


CHANGES = ("https://data.ssb.no/api/klass/v1/classifications/131/changes.json"
           "?from={start}&to={end}")


Lineage = tuple[list[tuple[str, str]], str | None]


def lineage(codes: list[str], start: str, end: str) -> dict[str, Lineage]:
    """2017 code -> ([(date, code), ...], the date its territory ended or None).

    KLASS lists each change as an old code and a new one. A renumbering --
    every kommune in 2020 and again in 2024, when the fylker were redrawn --
    is one old code to one new code on that date, and the kommune goes on
    under the new one. A merger is several old codes to one new one, a split
    one old code to several: the territory of every kommune in either ends on
    that date, and so does that of a kommune that kept its number while others
    were merged into it.
    """
    body = request_json(CHANGES.format(start=start, end=end))
    events: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for change in body.get("codeChanges", []):
        events[change["changeOccurred"]].append((change["oldCode"], change["newCode"]))
    current = {c: c for c in codes}
    history: dict[str, list[tuple[str, str]]] = {c: [("", c)] for c in codes}
    ended: dict[str, str | None] = {c: None for c in codes}
    for when in sorted(events):
        forward: dict[str, set[str]] = defaultdict(set)
        backward: dict[str, set[str]] = defaultdict(set)
        for old, new in events[when]:
            forward[old].add(new)
            backward[new].add(old)
        # A kommune that kept its number while others merged into it is not
        # listed itself, as Stavanger (1103) when Finnøy and Rennesøy joined
        # it in 2020: its number is a new code held before the change.
        kept = {new for new in backward if new not in forward and new in current.values()}
        for origin, code in list(current.items()):
            if code not in forward:
                if code in kept:
                    del current[origin]
                    ended[origin] = when
                continue
            news = forward[code]
            new = next(iter(news))
            if len(news) == 1 and len(backward[new]) == 1 and new not in kept:
                current[origin] = new
                history[origin].append((when, new))
            else:
                del current[origin]
                ended[origin] = when
    return {c: (history[c], ended[c]) for c in codes}


def code_on(history: list[tuple[str, str]], date: str) -> str:
    """The kommune's number on ``date`` (ISO), changes of that day included."""
    return [code for when, code in history if when <= date][-1]


def last_whole_year(ended: str) -> int:
    """The last 1 January a kommune whose territory ended on ``ended`` was whole:
    a change on 1 January is already in that day's count."""
    year = int(ended[:4])
    return year - 1 if ended[5:] == "01-01" else year


def successors(codes: list[str], start: str, end: str) -> dict[str, str]:
    """2017 code -> its code on ``end``, for every kommune whose territory the
    changes between the two dates left whole."""
    return {c: hist[-1][1] for c, (hist, ended) in lineage(codes, start, end).items()
            if ended is None}


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    log(f"norway: SSB 07459 and 12026 for the {VINTAGE} kommuner")
    klass = request_json(KLASS.format(date=f"{VINTAGE}-01-01"))["codes"]
    names = {c["code"]: office_names(c["name"]) for c in klass}
    codes = sorted(names)
    people, totals = ages_by_region(codes + ["0"], VINTAGE)
    kommuner = [c for c in codes if c in people and people[c].total > 0]
    dropped = [f"{c} {names[c][0]}" for c in codes if c not in kommuner]
    log(f"  KLASS {VINTAGE}: {len(codes)} codes, {len(kommuner)} with people"
        + (f"; none for {dropped}" if dropped else ""))
    check_parts({c: people[c].total for c in kommuner}, people["0"].total,
                f"07459 {VINTAGE}: kommuner -> Norway", 0)
    log(f"  Norway 1 January {VINTAGE}: {people['0'].total:,.0f} people, median age "
        f"{people['0'].median()}")
    check_national_median("NO", VINTAGE, people["0"].median(), f"07459 {VINTAGE}")

    shapes = load_units("NOR", "admin2")
    drawn = {fold(map_name(s)) for s in shapes}
    rows = {}
    for c in kommuner:
        forms = names[c] + [ALIASES[f] for f in names[c] if f in ALIASES]
        rows[c] = (next((f for f in forms if fold(f) in drawn), forms[0]), c[:2])
    bound, _m, _l, _p = bind_rows("NOR", "admin2", rows, shape_name=map_name, aliases=ALIASES)
    labels = {s["id"]: s["name"] for s in shapes}
    church = membership(kommuner, VINTAGE)

    # A kommune no merger or split has touched since 2017 is the same
    # territory today, under whatever number the fylke reforms gave it, and
    # takes today's count. One merged or split since takes its last count
    # whole: the last 1 January before the change, under the number it had
    # then (Klæbu was 1662 in 2017 and 5030 in 2019, its last year before it
    # joined Trondheim). Membership likewise: KOSTRA's latest year that still
    # counts the communities outside the Church, or the kommune's last whole
    # year if that is earlier.
    meta = {v["code"]: v for v in request_json(f"{SSB}/07459")["variables"]}
    now = int(meta["Tid"]["values"][-1])
    # KLASS leaves out changes on the end date itself: the day after
    # 1 January gives the division of 1 January of that year.
    lines = lineage(kommuner, f"{VINTAGE}-01-02", f"{now}-01-02")
    last = {c: (now if ended is None else last_whole_year(ended)) for c, (_h, ended)
            in lines.items()}
    pop_code = {c: code_on(lines[c][0], f"{last[c]}-01-01") for c in kommuner}
    by_year: dict[int, dict[str, AgeSex]] = {VINTAGE: people}
    for year in sorted(set(last.values()) - {VINTAGE}):
        by_year[year], _ = ages_by_region(sorted({pop_code[c] for c in kommuner
                                                  if last[c] == year}), year)
    log(f"  {sum(e is None for _h, e in lines.values())} of {len(kommuner)} kommuner unchanged "
        f"since {VINTAGE} (1 January {now}); the rest at their last whole year: "
        + ", ".join(f"{y}: {n}" for y, n in sorted(
            Counter(last[c] for c in kommuner if lines[c][1] is not None).items())))
    kostra_years = [int(y) for y in
                    {v["code"]: v for v in request_json(f"{SSB}/12026")["variables"]}
                    ["Tid"]["values"]]
    church_year = None
    for year in sorted(kostra_years, reverse=True):
        if year <= VINTAGE:
            break
        alive = sorted({code_on(lines[c][0], f"{year}-12-31") for c in kommuner
                        if last[c] >= year})
        counts = membership(alive, year)
        if sum(c.get("KOSmedltroslivs0000", 0) for c in counts.values()) > 0:
            church_year = year
            break
    faith_year = {c: min(last[c], church_year or VINTAGE) for c in kommuner}
    faith_code = {c: code_on(lines[c][0], f"{faith_year[c]}-12-31") for c in kommuner}
    faiths: dict[int, dict[str, dict[str, float]]] = {VINTAGE: church}
    for year in sorted(set(faith_year.values()) - {VINTAGE}):
        faiths[year] = membership(sorted({faith_code[c] for c in kommuner
                                          if faith_year[c] == year}), year)
    log(f"  membership: KOSTRA's latest year counting the communities outside the Church is "
        f"{church_year}; kommuner by year: "
        + ", ".join(f"{y}: {n}" for y, n in sorted(Counter(faith_year.values()).items())))
    records = []
    no_church = []
    for c in kommuner:
        sid = bound.get(c)
        if sid is None:
            continue
        hist, ended = lines[c]
        year = last[c]
        ages = by_year[year].get(pop_code[c])
        if ages is None or ages.total <= 0:
            raise SystemExit(f"07459 {year}: no count for {rows[c][0]} ({pop_code[c]})")
        if ended is None:
            note = (f" The kommune (number {pop_code[c]} today) has not been merged or split "
                    f"since {VINTAGE}, the year the map draws, so this is its latest count.")
        else:
            note = (f" The kommune as the map draws it (its {VINTAGE} territory), at its last "
                    f"count before it was merged or split on {ended}"
                    + (f", when its number was {pop_code[c]}." if pop_code[c] != c else "."))
        fields = ages.fields(year=year, source=f"{SOURCE}, table 07459", url=POP_URL,
                             date=f"1 January {year}", extra_note=note)
        fy = faith_year[c]
        if c in SPLIT_PARISH:
            faith = None
            fields["religion"] = gap(NOT_AVAILABLE, SPLIT_PARISH_NOTE)
            log(f"  12026 {rows[c][0]}: withheld -- a parish spans it and its neighbour")
        else:
            faith = religion(faiths[fy].get(faith_code[c], {}), fy, rows[c][0])
            if not faith and fy != VINTAGE:
                fy = VINTAGE
                faith = religion(church.get(c, {}), VINTAGE, rows[c][0])
        if faith:
            fields.update(faith)
            fields["sources"].append({"field": "religion", "name": f"{SOURCE}, table 12026",
                                      "url": CHURCH_URL, "year": fy})
        else:
            no_church.append(rows[c][0])
        records.append(record(
            f"NOR-SSB-{VINTAGE}-{c}", rows[c][0], level="admin2", parent="NOR", country="NOR",
            codes={"ssb": c, "vintage": VINTAGE}, match_by="shape_id", shape_id=sid,
            aliases=sorted({labels[sid], *names[c]} - {rows[c][0]}), **fields))
    if no_church:
        log(f"  no membership figures for {len(no_church)}: {no_church}")

    # The fylker.
    admin1 = {fold(u["name"]): u for u in load_units("NOR", "admin1")}
    meta = {v["code"]: v for v in request_json(f"{SSB}/07459")["variables"]}
    region_names = dict(zip(meta["Region"]["values"], meta["Region"]["valueTexts"]))
    fylke_people, _ = ages_by_region(list(SPLIT_FYLKER), FYLKE_YEAR)
    kostra_meta = {v["code"]: v for v in request_json(f"{SSB}/12026")["variables"]}
    latest = int(kostra_meta["Tid"]["values"][-1])
    structure: dict[int, list[str]] = {}

    def kommuner_in(year: int) -> list[str]:
        if year not in structure:
            structure[year] = [c["code"] for c in request_json(
                KLASS.format(date=f"{year}-01-01"))["codes"] if c["code"] != "9999"]
        return structure[year]

    # The eight fylker the 2024 reform left alone are the same territory
    # today: no kommune has crossed into or out of one since its last year
    # beside the three that were split -- KLASS lists every change of number
    # since, and a change that keeps a kommune inside its fylke keeps the
    # fylke's first two digits (Ålesund's split from Haram in 2024 did). Such
    # a fylke takes today's count, the newest there is. The three dissolved in
    # 2024 keep 2023's.
    moves = request_json(CHANGES.format(start=f"{FYLKE_YEAR}-01-02", end=f"{now}-01-02"))
    crossed = {code[:2] for change in moves.get("codeChanges", [])
               if change["oldCode"][:2] != change["newCode"][:2]
               for code in (change["oldCode"], change["newCode"])}
    kept = [f for f in FYLKER if f not in SPLIT_FYLKER and f not in crossed]
    changed = [f for f in FYLKER if f not in SPLIT_FYLKER and f not in kept]
    if changed:
        log(f"  fylker a kommune has crossed since {FYLKE_YEAR}, left to Eurostat: {changed}")
    kept_people, _ = ages_by_region(kept, now)
    empty = [f for f in kept if kept_people[f].total <= 0]
    if empty:
        raise SystemExit(f"07459 {now}: no people for the fylker {empty}")
    faiths = faith_by_fylke()
    for f in FYLKER:
        forms = office_names(region_names.get(f, f))
        shape = next((admin1[fold(n)] for n in forms if fold(n) in admin1), None)
        if shape is None:
            raise SystemExit(f"norway: fylke {f} {forms} has no polygon")
        fields: dict[str, Any] = {"sources": []}
        if f in SPLIT_FYLKER:
            fields = fylke_people[f].fields(
                year=FYLKE_YEAR, source=f"{SOURCE}, table 07459", url=POP_URL,
                date=f"1 January {FYLKE_YEAR}", extra_note=(
                    f" {forms[0]} existed from 2020 to 2023; this is its last count."))
        elif f in kept:
            fields = kept_people[f].fields(
                year=now, source=f"{SOURCE}, table 07459", url=POP_URL,
                date=f"1 January {now}", extra_note=(
                    f" The fylke has kept its kommuner since {FYLKE_YEAR}, the last year of "
                    "the division the map draws, so this is its latest count."))
        # KOSTRA's own fylke rows carry no figure for the communities outside
        # the Church (they read 0 -- Oslo's fylke row against 140,631 in Oslo
        # kommune), so a fylke is the sum of its kommuner in that year. The
        # latest years leave that figure at 0 for the kommuner too, so a fylke
        # that still exists takes the latest year that has it.
        faith, year = None, None
        # A fylke of 2020-2023 is the same territory in each of those years.
        for year in (range(FYLKE_YEAR, 2019, -1) if f in SPLIT_FYLKER
                     else range(latest, 2019, -1)):
            parts = [c for c in kommuner_in(year) if c[:2] == f]
            summed: dict[str, float] = defaultdict(float)
            for counts in membership(parts, year).values():
                for key, value in counts.items():
                    summed[key] += value
            faith = religion(summed, year, forms[0])
            if faith:
                break
        if faith:
            fields.update(faith)
            fields["sources"].append({"field": "religion", "name": f"{SOURCE}, table 12026",
                                      "url": CHURCH_URL, "year": year})
            if (f, year) in faiths:
                fields.update(religion_by_kind(summed, faiths[(f, year)], year, forms[0]))
                fields["sources"].append({"field": "religion", "name": f"{SOURCE}, table 08531",
                                          "url": FAITHS_URL, "year": year})
        records.append(record(
            f"NOR-SSB-F{f}", shape["name"], level="admin1", parent="NOR", country="NOR",
            codes={"ssb": f}, match_by="shape_id", shape_id=shape["id"],
            aliases=[n for n in forms if n != shape["name"]], **fields))
    log("  labels the group tree cannot place: "
        f"{unplaced('religion', [CHURCH, OTHER, NONE, *KINDS.values()])}")
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
