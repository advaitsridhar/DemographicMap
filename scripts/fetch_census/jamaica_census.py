#!/usr/bin/env python3
"""Jamaica: the 2022 census's population by parish and by community.

STATIN's 2022 Population and Housing Census publishes, as a page of its own,
"Population and Dwelling counts by Community": every community of every
parish with its people and its dwellings, each parish closed by a subtotal
row ("- Kingston Communities"). A second page, "Population Change by Parish",
gives the parishes' 2022 and 2011 counts and the national total, 2,774,538 --
with Kingston and St. Andrew as one line, the way STATIN reports the
Kingston Metropolitan Area.

What this writes:

* **The 14 parishes**: their 2022 population, from the subtotal rows. Every
  parish's communities must make its subtotal, the subtotals must make the
  parish page's figure (Kingston and St. Andrew together), and the parishes
  must make the national count.
* **The communities**: the 2022 population of each community the map draws
  under the same name in the same parish. The map's 827 community outlines
  are an older drawing than the 2022 list: STATIN has since split some
  communities at the Kingston and St. Andrew line ("Allman Town Part 1",
  "Part 2"), joined others ("Bloxborough/Bito", "Hughenden/Arlene Gardens"),
  and renamed a few. A figure is bound only where the name is the same place:
  the same name within the parish, a spelling the two lists plainly share
  (ALIASES), or one of the five communities the boundary file files under a
  neighbouring parish (ELSEWHERE), each checked against its own outline's
  position. Everything else is left out and every unbound polygon says so.

Nothing else is published below the parish. Median age, sex ratio, religion
and ethnic origin are tabulated by parish (and ages by STATIN's 261 "special
areas", which are not the map's communities), so the communities carry those
as gaps that say so.

Usage:
    python -m scripts.fetch_census.jamaica_census
"""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import fold

OUT = PROCESSED / "jamaica_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2022
COMMUNITIES_URL = ("https://statinja.gov.jm/PopCensus/Census2022/"
                   "Population%20and%20Dwelling%20counts%20by%20Community.aspx")
PARISHES_URL = ("https://statinja.gov.jm/PopCensus/Census2022/"
                "Population%20Change%20by%20Parish.aspx")
SOURCE = ("Statistical Institute of Jamaica (STATIN), 2022 Population and Housing Census: "
          "Population and Dwelling counts by Community")
PARISH_SOURCE = ("Statistical Institute of Jamaica (STATIN), 2022 Population and Housing "
                 "Census: Population and Dwelling counts by Community (parish subtotals), "
                 "checked against Population Change by Parish")
NATIONAL = 2_774_538
HEADER = ["Parish", "Community", "Total Population", "Number of Dwellings"]
SUBTOTAL = re.compile(r"^-\s*(.+?)\s+Communities$")

# STATIN's spelling -> the boundary file's, within the same parish, where the
# two plainly name one place: an abbreviation (Mt.), a letter dropped or
# doubled, Garden for Gardens, words in another order. A name that differs by
# a word that could be a different place ("Cooreville" and "Cooreville
# Gardens", "Pear Tree River" and "Pear Tree") is not here.
ALIASES: dict[tuple[str, str], str] = {
    ("St. Andrew", "Majesty Gardens"): "Majestic Gardens",
    ("St. Andrew", "Maverley"): "Marverley",
    ("St.Thomas", "Spring Gardens"): "Spring Garden",
    ("St.Thomas", "Wheelersfield"): "Wheelerfield",
    ("Portland", "Kensignton"): "Kensington",
    ("St. Mary", "Epsom"): "Epson",
    ("St. Ann", "Content Gardens"): "Content Garden",
    ("St. Ann", "Higgins Land"): "Higgin Land",
    ("St. Ann", "Lime Tree Garden"): "Lime Tree Gardens",
    ("St. Ann", "McNie"): "Macknie",
    ("Trelawny", "Samuel Prospect"): "Samuels Prospect",
    ("St. James", "Flanker"): "Flankers",
    ("St. James", "Mt. Carey"): "Mount Carey",
    ("St. James", "Mt. Horeb"): "Mount Horeb",
    ("St. James", "Mt. Salem"): "Mount Salem",
    ("St. James", "Rosemount Gardens"): "Rose Mount Garden",
    ("St. James", "Vaughansfield"): "Vaughnsfield",
    ("Westmoreland", "Cornwall Mountain"): "Cornwall Mountian",
    ("Westmoreland", "Fort William"): "Fort Williams",
    ("Westmoreland", "Lennox Bigwoods"): "Lenox Bigwoods",
    ("Westmoreland", "Savanna-la-mar Business District"): "Savannah-la-mar Business Dist.",
    ("Westmoreland", "Sheffield"): "Shefield",
    ("Westmoreland", "Three Miles River"): "Three Mile River",
    ("St. Elizabeth", "Barbury Hall"): "Barbary Hall",
    ("St. Elizabeth", "Warminster"): "Warminister",
    ("Manchester", "Waltham"): "Watham",
}

# Communities the boundary file draws under a neighbouring parish. Each name
# is the only polygon of that name on the island, and its outline's centre
# lies inside the bounding box of the parish STATIN counts it in -- measured
# on the map's own units, which is what `elsewhere_checked` re-measures on
# every run. Aenon Town, Crofts Hill, Freetown and Sandy Bay are Clarendon's,
# filed under St. Ann and St. Catherine; Kilmarnock is Westmoreland's, filed
# under St. Elizabeth and spelt "Kilmarnoch". Two are not here. Silent Hill:
# STATIN counts one in Manchester and a "Silent Hill/Moravia" in Clarendon,
# and the one outline of the name lies between them. Port Royal: STATIN counts
# it in Kingston, and the map's Kingston stops short of the Palisadoes, so the
# outline's centre is outside the parish it is counted in -- the test this
# list rests on fails, and the figure is left out rather than excused.
ELSEWHERE: dict[tuple[str, str], tuple[str, str]] = {
    ("Clarendon", "Aenon Town"): ("Saint Ann", "Aenon Town"),
    ("Clarendon", "Crofts Hill"): ("Saint Catherine", "Crofts Hill"),
    ("Clarendon", "Freetown"): ("Saint Catherine", "Freetown"),
    ("Clarendon", "Sandy Bay"): ("Saint Catherine", "Sandy Bay"),
    ("Westmoreland", "Kilmarnock"): ("Saint Elizabeth", "Kilmarnoch"),
}

# Rows left out although a polygon carries their name: STATIN lists a second
# community of nearly the same name in the parish ("Labryinth", 759 people,
# beside "Labyrinth", 1,200), so which of the two the one outline is cannot be
# told.
AMBIGUOUS = {("St. Mary", "Labyrinth")}


def parish_key(name: str) -> str:
    """STATIN's "St. Andrew", "St.Thomas" and the map's "Saint Andrew" as one key."""
    return fold(re.sub(r"^St\.?\s*", "Saint ", str(name).strip()))


def number(text: str) -> int:
    digits = re.sub(r"[,\s]", "", text)
    if not digits.isdigit():
        raise SystemExit(f"jamaica_census: {text!r} is not a count")
    return int(digits)


def table_rows(page: str) -> list[list[str]]:
    """Every row of the page's tables, as the text of its cells."""
    rows = []
    for tr in re.findall(r"(?is)<tr\b.*?</tr>", page):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", c))).strip()
                 for c in re.findall(r"(?is)<t[dh]\b.*?</t[dh]>", tr)]
        if any(cells):
            rows.append(cells)
    return rows


# How far STATIN's own sums may disagree, in people. The community table's
# rows do not quite make its parish subtotals -- Kingston's make 89,187 against
# a subtotal of 89,186, St. James's 188,650 against 188,656 -- and the parish
# page's thirteen lines make 2,774,537 against its Total of 2,774,538. The
# largest gap measured is six people in a parish; a misread row is thousands.
SLACK = 10


def communities(rows: list[list[str]]) -> dict[str, dict[str, Any]]:
    """{parish key: {"label", "total", "communities": [(name, people)]}}.

    STATIN writes a parish two ways in one table ("St. Elizabeth",
    "St.Elizabeth"), so rows are gathered by parish_key. Refuses a table whose
    header is not the one this reads, and a parish whose communities are more
    than SLACK from its subtotal.
    """
    if not rows or rows[0] != HEADER:
        raise SystemExit(f"jamaica_census: the community table's header is "
                         f"{rows[0] if rows else None}, not {HEADER}")
    parishes: dict[str, dict[str, Any]] = {}
    for cells in rows[1:]:
        if len(cells) != 4:
            raise SystemExit(f"jamaica_census: a row of {len(cells)} cells: {cells}")
        parish, name, people, _dwellings = cells
        entry = parishes.setdefault(parish_key(parish),
                                    {"label": parish, "total": None, "communities": []})
        sub = SUBTOTAL.match(name)
        if sub:
            if parish_key(sub.group(1)) != parish_key(parish):
                raise SystemExit(f"jamaica_census: {parish}'s subtotal is labelled {name!r}")
            entry["label"], entry["total"] = parish, number(people)
        else:
            entry["communities"].append((name, number(people)))
    for entry in parishes.values():
        made = sum(n for _, n in entry["communities"])
        if entry["total"] is None or abs(made - entry["total"]) > SLACK:
            raise SystemExit(f"jamaica_census: {entry['label']}'s communities make {made:,}, "
                             f"and its subtotal is {entry['total']}")
        if made != entry["total"]:
            log(f"  {entry['label']}: communities make {made:,} against a subtotal of "
                f"{entry['total']:,}")
    return parishes


def parish_page(rows: list[list[str]]) -> tuple[dict[str, int], int]:
    """{parish key, or keys joined by " & ": 2022 count}, and the page's national total."""
    head = rows[0]
    if not head or head[0] != "Parish" or not head[1].startswith("Total Population 2022"):
        raise SystemExit(f"jamaica_census: the parish page's header is {head}")
    out, national = {}, None
    for cells in rows[1:]:
        if cells[0] == "Total":
            national = number(cells[1])
        else:
            out[" & ".join(parish_key(p) for p in cells[0].split("&"))] = number(cells[1])
    if national is None or abs(sum(out.values()) - national) > SLACK:
        raise SystemExit(f"jamaica_census: the parishes make {sum(out.values()):,}, and the "
                         f"page's total is {national}")
    return out, national


def check_parishes(table: dict[str, dict[str, Any]], page: dict[str, int], national: int) -> None:
    """The community table's subtotals against the parish page, and both against the count."""
    if national != NATIONAL:
        raise SystemExit(f"jamaica_census: the parish page's total is {national:,}, not "
                         f"STATIN's published {NATIONAL:,}")
    totals = {key: e["total"] for key, e in table.items()}
    for key, value in page.items():
        made = sum(totals.get(p, 0) for p in key.split(" & "))
        if made != value:
            raise SystemExit(f"jamaica_census: {key}'s subtotals make {made:,}; the parish "
                             f"page gives {value:,}")
    if len(totals) != 14 or abs(sum(totals.values()) - national) > SLACK:
        raise SystemExit(f"jamaica_census: {len(totals)} parish subtotals make "
                         f"{sum(totals.values()):,}, against the national {national:,}")


def elsewhere_checked(shape: dict[str, Any], parish: dict[str, Any]) -> bool:
    """Whether a polygon filed under another parish lies within the counting one's box."""
    x, y = shape["point"]
    west, south, east, north = parish["bbox"]
    return west <= x <= east and south <= y <= north


def bind(table: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
         admin2: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], dict[str, Any]], list[str]]:
    """{(parish, community): polygon} and the rows left out, with why."""
    first = {fold(u["name"]): u for u in admin1}
    named: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    names = {u["id"]: u["name"] for u in admin1}
    for shape in admin2:
        named[(fold(names.get(shape["parent"], "")), fold(shape["name"]))].append(shape)
        by_name[fold(shape["name"])].append(shape)
    bound: dict[tuple[str, str], dict[str, Any]] = {}
    left: list[str] = []
    aliases = {(parish_key(p), n): v for (p, n), v in ALIASES.items()}
    elsewhere = {(parish_key(p), n): v for (p, n), v in ELSEWHERE.items()}
    ambiguous = {(parish_key(p), n) for p, n in AMBIGUOUS}
    for home, entry in table.items():
        parish = entry["label"]
        if home not in first:
            raise SystemExit(f"jamaica_census: parish {parish!r} has no polygon")
        for name, _people in entry["communities"]:
            key = (parish, name)
            if (home, name) in ambiguous:
                left.append(f"{parish}: {name} (a second community of nearly the same name)")
                continue
            if (home, name) in elsewhere:
                other, theirs = elsewhere[(home, name)]
                hits = by_name[fold(theirs)]
                hits = [s for s in hits if fold(names.get(s["parent"], "")) == fold(other)]
                if len(hits) != 1 or not elsewhere_checked(hits[0], first[home]):
                    raise SystemExit(f"jamaica_census: {name} is no longer one polygon under "
                                     f"{other} lying within {parish}")
                bound[key] = hits[0]
                continue
            theirs = aliases.get((home, name), name)
            hits = named.get((home, fold(theirs)), [])
            if len(hits) == 1:
                bound[key] = hits[0]
            else:
                left.append(f"{parish}: {name} ({len(hits)} polygons of that name in the parish)")
    taken: dict[str, tuple[str, str]] = {}
    for key, shape in bound.items():
        if shape["id"] in taken:
            raise SystemExit(f"jamaica_census: {key} and {taken[shape['id']]} both reach "
                             f"{shape['name']}")
        taken[shape["id"]] = key
    return bound, left


COMPOSITION_GAP = ("STATIN tabulates this by parish only: the 2011 census's ethnic origin and "
                   "religion tables, and its ages, stop at the parish (ages also by 261 "
                   "\"special areas\", which are not the map's communities), and the 2022 "
                   "census's community table counts people and dwellings and nothing else.")


USCB_DATASET = "jamaica-subnational-boundaries-and-tabular-data"


def community_key(name: Any) -> str:
    """A community's name as one key whether written "St. Paul's" or "Saint Pauls"."""
    text = re.sub(r"\bSt\.?\s*(?=[A-Z])", "Saint ", str(name or "").strip(), flags=re.I)
    text = re.sub(r"\bMt\.?\s*(?=[A-Z])", "Mount ", text, flags=re.I)
    return fold(text)


# How far a community's 2022 count may sit from STATIN's 2012 estimate for the
# community of the same name before the name is taken to cover different
# ground. Measured on the 623 bound communities the 2012 list names: half lie
# within 0.85 and 1.15 of their 2012 figure and nine in ten within 0.62 and
# 1.60, while the parishes grew by 0.4% to 5.5%. Outside a factor of two the
# name has been redrawn -- "Samuel Prospect" counts 749 people in 2022 where
# the community of that name held 4,677 in 2012 -- or has taken in new estates
# (Rose Hall, 253 to 2,194), and either way the figure is not the outline's.
DRIFT = 2.0


def earlier() -> dict[tuple[str, str], int]:
    """{(parish key, community key): STATIN's mid-2012 estimate} from the poverty map.

    The US Census Bureau's Jamaica workbook carries STATIN's community poverty
    map (Mapping Poverty Indicators, 2019) with each community's estimated
    population in July 2012, on the 2011 census's community list, which the
    2022 list mostly keeps. Beside a 2022 count it says whether a community of
    the same name is still the same ground.
    """
    import io

    import openpyxl

    from . import uscb
    blob = http_get(uscb.workbook_url(USCB_DATASET), binary=True, cache=False)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rows = uscb.sheet_rows(book, "Poverty")
    names, aliases = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names)}
    column = next((i for i, a in enumerate(aliases) if a.lower() == "population estimate"), None)
    if column is None:
        raise SystemExit("jamaica_census: the poverty sheet has no population estimate column")
    out = {}
    for row in rows[2:]:
        if str(row[at["ADM_LEVEL"]]).strip() not in ("2", "2.0"):
            continue
        key = (parish_key(str(row[at["ADM1_NAME"]]).title()),
               community_key(str(row[at["ADM2_NAME"]]).title()))
        value = row[column]
        # The sheet writes -999 where it has no estimate.
        if value not in (None, "") and float(value) > 0:
            out[key] = int(round(float(value)))
    log(f"  {len(out)} communities in the 2012 poverty map's population estimates")
    return out


def earlier_figure(before: dict[tuple[str, str], int], parish: str, name: str,
                   shape: dict[str, Any]) -> int | None:
    return (before.get((parish_key(parish), community_key(name)))
            or before.get((parish_key(parish), community_key(shape["name"]))))


def steady(bound: dict[tuple[str, str], dict[str, Any]], people: dict[tuple[str, str], int],
           before: dict[tuple[str, str], int]) -> tuple[dict[tuple[str, str], dict[str, Any]],
                                                         list[str]]:
    """The bindings whose 2022 count is within DRIFT of the 2012 estimate, and the rest.

    The 2012 figure is looked up under STATIN's name and, failing that, under
    the outline's: "Samuel Prospect" is "Samuels Prospect" in the 2012 list,
    and 4,677 people there against 749 in 2022 is what shows the two are no
    longer one place. A community the 2012 list names neither way has nothing
    to be measured against and is kept: the name is the whole of the evidence.
    """
    kept, dropped = {}, []
    for (parish, name), shape in bound.items():
        then = earlier_figure(before, parish, name, shape)
        now = people[(parish, name)]
        if then and not (1 / DRIFT <= now / then <= DRIFT):
            dropped.append(f"{parish}: {name} ({now:,} in 2022 against {then:,} in 2012)")
        else:
            kept[(parish, name)] = shape
    return kept, dropped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true",
                    help="print each bound community's 2022 count beside its 2012 estimate "
                         "and write nothing")
    args = ap.parse_args()
    table = communities(table_rows(http_get(COMMUNITIES_URL, cache=False)))
    page, national = parish_page(table_rows(http_get(PARISHES_URL, cache=False)))
    check_parishes(table, page, national)
    log(f"  {sum(len(e['communities']) for e in table.values())} communities in "
        f"{len(table)} parishes, making {national:,}")

    admin1 = json.loads((SITE / "admin1" / "JAM.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "JAM.units.json").read_text())
    bound, left = bind(table, admin1, admin2)
    log(f"  {len(bound)} communities bound to their polygons by name; {len(left)} left out:")
    for line in left:
        log(f"    {line}")
    people = {(e["label"], n): v for e in table.values() for n, v in e["communities"]}
    before = earlier()
    if args.probe:
        for (parish, name), shape in sorted(bound.items()):
            then = earlier_figure(before, parish, name, shape)
            ratio = f"{people[(parish, name)] / then:.2f}" if then else "-"
            log(f"    CMP {parish} | {name} | {shape['name']} | {people[(parish, name)]} | "
                f"{then} | {ratio}")
        return 0
    named = bound
    bound, drifted = steady(bound, people, before)
    moved = {shape["id"]: (key, earlier_figure(before, key[0], key[1], shape))
             for key, shape in named.items() if key not in bound}
    log(f"  {len(drifted)} more left out, their 2022 count more than {DRIFT:g} times "
        "from or less than half the 2012 estimate for the same name:")
    for line in drifted:
        log(f"    {line}")
    first = {fold(u["name"]): u for u in admin1}
    records = []
    for home, entry in sorted(table.items()):
        shape = first[home]
        records.append(record(
            f"JAM-STATIN-{home}", shape["name"], level="admin1", parent="JAM",
            country="JAM", match_by="shape_id", shape_id=shape["id"],
            population=measure(entry["total"], year=YEAR, source=PARISH_SOURCE),
            population_note=("Everyone counted in the parish by the 2022 census: the "
                             "subtotal of STATIN's community table, which is also the "
                             "parish's line on its Population Change by Parish page."),
            sources=[{"field": "population", "name": PARISH_SOURCE, "url": COMMUNITIES_URL,
                      "year": YEAR}]))
    reached = set()
    for key, shape in sorted(bound.items(), key=lambda kv: kv[1]["id"]):
        parish, name = key
        reached.add(shape["id"])
        records.append(record(
            f"JAM-STATIN-{parish_key(parish)}-{fold(name)}", shape["name"], level="admin2",
            parent="JAM", country="JAM", parent_name=first[parish_key(parish)]["name"],
            match_by="shape_id", shape_id=shape["id"],
            aliases=[name] if name != shape["name"] else [],
            population=measure(people[key], year=YEAR, source=SOURCE),
            population_note=(f"Everyone STATIN's 2022 census counted in the community of "
                             f"{name}, {parish}."),
            median_age=gap(NOT_AVAILABLE, COMPOSITION_GAP),
            sex_ratio=gap(NOT_AVAILABLE, COMPOSITION_GAP),
            religion=gap(NOT_AVAILABLE, COMPOSITION_GAP),
            ethnicity=gap(NOT_AVAILABLE, COMPOSITION_GAP),
            sources=[{"field": "population", "name": SOURCE, "url": COMMUNITIES_URL,
                      "year": YEAR}]))
    names = {u["id"]: u["name"] for u in admin1}
    unreached = [s for s in admin2 if s["id"] not in reached]
    for shape in unreached:
        if shape["id"] in moved:
            (parish, name), then = moved[shape["id"]]
            why = (f"STATIN's 2022 census counts {people[(parish, name)]:,} people in "
                   f"{name}, {parish}, against its 2012 estimate of {then:,} for the "
                   f"community of that name: more than {DRIFT:g} times apart, so the name "
                   "no longer describes the same ground and the count is left off.")
        else:
            why = ("STATIN's 2022 community table has no community that is this outline: the "
                   "2022 list splits, joins or renames the community the map draws here (the "
                   "map's outlines are an older drawing), so no count is put on it rather "
                   "than one for other ground.")
        records.append(record(
            f"JAM-STATIN-unbound-{shape['id']}", shape["name"], level="admin2", parent="JAM",
            country="JAM", parent_name=names.get(shape["parent"]), match_by="shape_id",
            shape_id=shape["id"],
            population=gap(NOT_AVAILABLE, why),
            median_age=gap(NOT_AVAILABLE, COMPOSITION_GAP),
            sex_ratio=gap(NOT_AVAILABLE, COMPOSITION_GAP),
            religion=gap(NOT_AVAILABLE, COMPOSITION_GAP),
            ethnicity=gap(NOT_AVAILABLE, COMPOSITION_GAP)))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records ({len(table)} parishes, {len(bound)} "
        f"communities with a count, {len(unreached)} polygons with the reason they have none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
