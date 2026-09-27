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
  age, 1 January) for 2017, by the 2017 kommune codes, which KLASS
  (classification 131) lists as valid on 1 January 2017. Median age and sex
  ratio from the single years; population from the same count.
* **admin1** -- 07459 for 2023 by the codes of the three 2020-2023 fylker
  (30, 38, 54), the last year they existed. The other eight fylker did not
  change in 2024 and already carry Eurostat's 2025 figures, so they are not
  written.
* **religion** -- SSB table 12026 (KOSTRA, "church users"), which gives for
  every kommune and fylke the members of the Church of Norway, the members of
  the faith and life-stance communities outside it, and the population. That
  covers everyone: the remainder are members of neither. It is registered
  membership, not belief, and the note says so. SSB publishes the communities
  outside the Church by religion only by fylke, so at kommune level they are
  one group. The year is 2017 for the kommuner (KOSTRA reports each year on
  that year's kommuner) and, for the fylker, 2023 for the three dissolved in
  2024 and the latest year for the eight that were not.

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
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, record, shares, write_json
from .binding import fold
from .nordic_common import (AgeSex, bind_rows, check_parts, load_units, request_json,
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


def religion(counts: dict[str, float], year: int, where: str) -> dict[str, Any] | None:
    church = counts.get("KOSmedlemmerdnk0000")
    other = counts.get("KOSmedltroslivs0000")
    people = counts.get("KOSpersoneralle0000")
    if not church or other is None or not people:
        return None
    if church + other > people:
        raise SystemExit(f"12026 {where} {year}: {church + other:,.0f} members against a "
                         f"population of {people:,.0f}")
    rows = {CHURCH: church, OTHER: other, NONE: people - church - other}
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
            "one group."),
    }


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

    shapes = load_units("NOR", "admin2")
    drawn = {fold(map_name(s)) for s in shapes}
    rows = {}
    for c in kommuner:
        forms = names[c] + [ALIASES[f] for f in names[c] if f in ALIASES]
        rows[c] = (next((f for f in forms if fold(f) in drawn), forms[0]), c[:2])
    bound, _m, _l, _p = bind_rows("NOR", "admin2", rows, shape_name=map_name, aliases=ALIASES)
    labels = {s["id"]: s["name"] for s in shapes}
    church = membership(kommuner, VINTAGE)
    date = f"1 January {VINTAGE}"
    records = []
    no_church = []
    for c in kommuner:
        sid = bound.get(c)
        if sid is None:
            continue
        fields = people[c].fields(year=VINTAGE, source=f"{SOURCE}, table 07459", url=POP_URL,
                                  date=date, extra_note=(
                                      f" The kommune as it stood in {VINTAGE}, which is the "
                                      "unit the map draws."))
        faith = religion(church.get(c, {}), VINTAGE, rows[c][0])
        if faith:
            fields.update(faith)
            fields["sources"].append({"field": "religion", "name": f"{SOURCE}, table 12026",
                                      "url": CHURCH_URL, "year": VINTAGE})
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
        year = FYLKE_YEAR if f in SPLIT_FYLKER else latest
        faith = religion(membership([f"EKA{f}"], year).get(f"EKA{f}", {}), year, forms[0])
        if faith:
            fields.update(faith)
            fields["sources"].append({"field": "religion", "name": f"{SOURCE}, table 12026",
                                      "url": CHURCH_URL, "year": year})
        records.append(record(
            f"NOR-SSB-F{f}", shape["name"], level="admin1", parent="NOR", country="NOR",
            codes={"ssb": f}, match_by="shape_id", shape_id=shape["id"],
            aliases=[n for n in forms if n != shape["name"]], **fields))
    log(f"  labels the group tree cannot place: {unplaced('religion', [CHURCH, OTHER, NONE])}")
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
