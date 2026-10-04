#!/usr/bin/env python3
"""Australia, 2021 Census: median age, sex ratio and ancestry, states and LGAs.

Three tables of the ABS's 2021 General Community Profile, read through the ABS
Data API (SDMX) for the 547 local government areas the map draws at its second
level and the nine states and territories at its first:

* **G02 Selected medians and averages** -- "Median age of persons", the ABS's
  own median for exactly the unit (``C21_G02_LGA``; the states and the country
  from ``C21_G02_SA2``, whose regions run from SA2 up through the states to
  Australia). The ABS publishes it in whole years, and it is written as
  published rather than recomputed.
* **G01 Selected person characteristics by sex** -- total persons, males and
  females: the sex ratio (males per 100 females), and the persons every
  ancestry share is taken of.
* **G08 Ancestry by country of birth of parents** -- read in its "Total
  responses" column (``BPPP=_T``), which is each ancestry's count of the people
  who named it; the table's own total row (``ANCP=_T``) counts persons. Up to
  two ancestries are recorded for each person, so the ancestries are responses,
  and each share is the percentage of the unit's people who reported that
  ancestry: they sum to about 130%, as the ABS's own QuickStats present them
  ("English 33.0%, Australian 29.9% ...").

**Ancestry on the ethnicity field.** The census asks no ethnicity question as
such; ancestry is the question it asks instead, and the ABS codes the answers
to its Australian Standard Classification of Cultural and Ethnic Groups. By the
owner's decision of 19 September 2026 the ethnicity field may carry what the
state counts in place of ethnicity, under an ``ethnicity_basis`` naming it, and
this file writes ancestry there (basis "ancestry (multi-response)"), the same
measure the country's own Factbook row reports.

**Binding** is by the ASGS code each drawn unit already carries (``codes.asgs``,
the LGA 2021 code at the second level and the state code at the first), written
as shape ids. A unit whose code's state is not the state the boundary file puts
the unit in stops the run; so does a code the tables do not know.

**Checks**, each of which refuses the run rather than writing:

* Australia's persons, males and females are the published 25,422,788,
  12,545,154 and 12,877,634; its median age is the published 38;
* every unit's males and females make its persons, within the ABS's
  perturbation of small cells;
* every state's LGAs (the "no usual address" and "migratory" codes among them)
  make the state, and the states make Australia;
* each unit's ancestry responses come to between one and two for every person
  G08 counts there, and G08's persons are G01's;
* Australia's English and Australian ancestry shares are the published 33.0%
  and 29.9%.

Usage:
    python -m scripts.fetch_census.australia_profile
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .abs import sdmx, unpack

YEAR = 2021
OUT = "australia_profile.json"
SITE = Path(__file__).resolve().parents[2] / "site" / "data"
AGENCY = "ABS"
VERSION = "1.0.0"
SOURCE = "Australian Bureau of Statistics, Census of Population and Housing 2021"
TABLES = {
    "G01": "General Community Profile G01, Selected person characteristics by sex",
    "G02": "General Community Profile G02, Selected medians and averages",
    "G08": "General Community Profile G08, Ancestry by country of birth of parents",
}
API_PAGE = "https://data.api.abs.gov.au/"
LICENCE = "CC BY 4.0"

# SDMX keys, dimension by dimension in each dataflow's own order (read off the
# dataflows' structures): G01 SEXP.PCHAR.REGION.REGION_TYPE.STATE, G02
# MEDAVG.REGION.REGION_TYPE.STATE, G08 ANCP.BPPP.REGION.REGION_TYPE.STATE. The
# SA2+ flows are asked for their national and state rows only.
KEYS = {
    ("G01", "LGA"): "1+2+3.P_1...",
    ("G02", "LGA"): "1...",
    ("G08", "LGA"): "._T...",
    ("G01", "SA2"): "1+2+3.P_1..AUS+STE.",
    ("G02", "SA2"): "1..AUS+STE.",
    ("G08", "SA2"): "._T..AUS+STE.",
}
SEX = {"1": "male", "2": "female", "3": "persons"}

# Published national figures (2021 Census QuickStats, Australia): the control
# that the right slice of the right table was read.
NATIONAL = {"persons": 25_422_788, "male": 12_545_154, "female": 12_877_634,
            "median_age": 38, "English": 33.0, "Australian": 29.9}

# The ABS perturbs every cell to protect confidentiality, by an absolute
# number of people, so two tables' counts for one place differ by a few.
def tolerance(total: float) -> float:
    return max(30.0, 0.005 * total)


# G08's ancestry labels, as the map writes them: the residuals in the words
# the other census rows use.
ANCESTRY_LABELS = {"Other": "Other", "Not stated": "Not stated"}

# Pseudo-areas of every state's LGA list that the map draws no polygon for:
# people with no usual address, and the migratory, offshore and shipping
# population. Their counts belong to the state and to nothing smaller.
UNDRAWN_SUFFIXES = ("9499", "9799")


def load_units(level: str) -> list[dict[str, Any]]:
    from common import as_drawn
    return as_drawn(json.loads((SITE / level / "AUS.units.json").read_text()))


def by_region(rows: Iterable[tuple[dict[str, str], float]]
              ) -> dict[str, list[tuple[dict[str, str], float]]]:
    out: dict[str, list[tuple[dict[str, str], float]]] = defaultdict(list)
    for labels, value in rows:
        code = labels.get("REGION_CODE")
        if code:
            out[code].append((labels, value))
    return out


def names_of(rows: Iterable[tuple[dict[str, str], float]]) -> dict[str, str]:
    return {labels["REGION_CODE"]: labels.get("REGION", labels["REGION_CODE"])
            for labels, _ in rows if labels.get("REGION_CODE")}


def persons(rows: Iterable[tuple[dict[str, str], float]]) -> dict[str, dict[str, float]]:
    """{region: {"persons", "male", "female"}} from G01's total-persons row."""
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for labels, value in rows:
        if labels.get("PCHAR_CODE") != "P_1":
            continue
        sex = SEX.get(labels.get("SEXP_CODE", ""))
        if sex:
            out[labels["REGION_CODE"]][sex] = value
    for region, counts in out.items():
        if set(counts) != {"persons", "male", "female"}:
            raise SystemExit(f"australia_profile: G01 region {region} has only {sorted(counts)}")
        gap = abs(counts["male"] + counts["female"] - counts["persons"])
        if gap > tolerance(counts["persons"]):
            raise SystemExit(f"australia_profile: G01 region {region}: males "
                             f"{counts['male']:,.0f} and females {counts['female']:,.0f} "
                             f"do not make {counts['persons']:,.0f}")
    return dict(out)


def medians(rows: Iterable[tuple[dict[str, str], float]]) -> dict[str, float]:
    out = {}
    for labels, value in rows:
        if labels.get("MEDAVG_CODE") == "1":
            out[labels["REGION_CODE"]] = value
    return out


def ancestries(rows: Iterable[tuple[dict[str, str], float]]
               ) -> dict[str, tuple[dict[str, float], float]]:
    """{region: ({ancestry: responses}, persons)} from G08's total column.

    The table's own total row (``ANCP=_T``) counts persons, not responses --
    Albury's is 56,093, its population -- and the ancestries above it count
    responses, up to two a person. So the responses must come to between one
    and two for every person the total counts, and that total is what each
    share is taken of, as QuickStats takes it.
    """
    counts: dict[str, dict[str, float]] = defaultdict(dict)
    totals: dict[str, float] = {}
    for labels, value in rows:
        if labels.get("BPPP_CODE") != "_T":
            continue
        code, label = labels.get("ANCP_CODE"), labels.get("ANCP", "")
        if code == "_T":
            totals[labels["REGION_CODE"]] = value
        elif code:
            label = ANCESTRY_LABELS.get(label, label)
            counts[labels["REGION_CODE"]][label] = value
    out = {}
    for region, parts in counts.items():
        people = totals.get(region)
        if people is None:
            raise SystemExit(f"australia_profile: G08 region {region} has no total")
        responses, slack = sum(parts.values()), tolerance(people)
        if not people - slack <= responses <= 2 * people + slack:
            raise SystemExit(f"australia_profile: G08 region {region}: {responses:,.0f} "
                             f"ancestry responses for {people:,.0f} people; the census "
                             "records one or two for each person")
        out[region] = (parts, people)
    return out


def ancestry_shares(parts: dict[str, float], people: float) -> list[dict[str, Any]]:
    """Each ancestry as the percentage of the unit's people who reported it."""
    rows = [{"group": k, "pct": round(100.0 * v / people, 1), "count": int(round(v))}
            for k, v in parts.items() if v > 0]
    rows.sort(key=lambda r: (-r["pct"], r["group"]))
    return rows


def check_national(people: dict[str, dict[str, float]], median: dict[str, float],
                   ancestry: dict[str, tuple[dict[str, float], float]]) -> None:
    nation = people.get("AUS")
    if not nation:
        raise SystemExit("australia_profile: G01 has no row for Australia")
    for key in ("persons", "male", "female"):
        if abs(nation[key] - NATIONAL[key]) > 5:
            raise SystemExit(f"australia_profile: Australia's {key} read {nation[key]:,.0f}, "
                             f"published {NATIONAL[key]:,}")
    if median.get("AUS") != NATIONAL["median_age"]:
        raise SystemExit(f"australia_profile: Australia's median age read {median.get('AUS')}, "
                         f"published {NATIONAL['median_age']}")
    parts, counted = ancestry["AUS"]
    for label in ("English", "Australian"):
        share = round(100.0 * parts.get(label, 0) / counted, 1)
        log(f"  Australia {label} ancestry {share}% (published {NATIONAL[label]}%)")
        if abs(share - NATIONAL[label]) > 0.15:
            raise SystemExit(f"australia_profile: Australia's {label} ancestry is {share}%, "
                             f"published {NATIONAL[label]}%")


def is_lga(code: str) -> bool:
    """An LGA code, as against the state and national rows some flows carry."""
    return len(code) == 5 and code.isdigit()


def check_parts(people: dict[str, dict[str, float]], lga_people: dict[str, dict[str, float]],
                states: Iterable[str]) -> None:
    """Every state's LGAs make the state, and the states make Australia."""
    for state in states:
        own = people[state]["persons"]
        parts = sum(v["persons"] for code, v in lga_people.items()
                    if is_lga(code) and code[:1] == state)
        log(f"  state {state}: LGAs sum to {parts:,.0f}, the state's own {own:,.0f}")
        if abs(parts - own) > max(200.0, 0.002 * own):
            raise SystemExit(f"australia_profile: state {state}'s LGAs make {parts:,.0f}, "
                             f"not its {own:,.0f}")
    whole = sum(people[s]["persons"] for s in states)
    if abs(whole - people["AUS"]["persons"]) > 200:
        raise SystemExit(f"australia_profile: the states make {whole:,.0f}, not Australia's "
                         f"{people['AUS']['persons']:,.0f}")


def bind(units: list[dict[str, Any]], level: str, parents: dict[str, dict[str, Any]]
         ) -> dict[str, dict[str, Any]]:
    """{ASGS code: unit} for one level, checked one to one and state by state."""
    out: dict[str, dict[str, Any]] = {}
    for unit in units:
        code = str((unit.get("codes") or {}).get("asgs") or "")
        if not code:
            raise SystemExit(f"australia_profile: {level} unit {unit['name']!r} carries no ASGS code")
        if code in out:
            raise SystemExit(f"australia_profile: two {level} units carry ASGS code {code}")
        if level == "admin2":
            parent = parents.get(unit.get("parent"))
            state = str((parent or {}).get("codes", {}).get("asgs") or "")
            if state != code[:1]:
                raise SystemExit(
                    f"australia_profile: {unit['name']!r} carries LGA {code}, which is in state "
                    f"{code[:1]}, but the boundary file puts it in "
                    f"{(parent or {}).get('name')!r} (state {state or '?'})")
        out[code] = unit
    return out


def unit_record(code: str, name: str, unit: dict[str, Any], level: str, *,
                people: dict[str, float], median: float | None,
                ancestry: tuple[dict[str, float], float] | None,
                parent_name: str | None) -> dict[str, Any]:
    ratio = round(100.0 * people["male"] / people["female"], 1)
    fields: dict[str, Any] = {
        "sex_ratio": measure(ratio, unit="males_per_100_females", year=YEAR, source=SOURCE),
        "sex_ratio_note": (
            f"Males per 100 females among the {people['persons']:,.0f} people counted in the "
            f"2021 Census at their usual address here ({people['male']:,.0f} males, "
            f"{people['female']:,.0f} females; ABS G01)."),
    }
    if median is not None:
        median = int(median) if float(median).is_integer() else median
        fields["median_age"] = measure(median, unit="years", year=YEAR, source=SOURCE)
        fields["median_age_note"] = (
            "The ABS's own median age of persons for this area (2021 Census, G02), "
            "published in whole years; the census counts people at their usual address.")
    if ancestry is not None:
        parts, counted = ancestry
        responses = sum(parts.values())
        if abs(counted - people["persons"]) > tolerance(people["persons"]):
            raise SystemExit(f"australia_profile: {name} ({code}): G08 counts {counted:,.0f} "
                             f"people, G01 {people['persons']:,.0f}")
        fields["ethnicity"] = ancestry_shares(parts, counted)
        fields["ethnicity_year"] = YEAR
        fields["ethnicity_basis"] = "ancestry (multi-response)"
        fields["ethnicity_note"] = (
            "Ancestry, which is what Australia's census asks in place of an ethnicity question "
            "('What is the person's ancestry?'), coded by the ABS to its Standard "
            "Classification of Cultural and Ethnic Groups; recorded on the ethnicity field by "
            "the owner's decision of 19 September 2026. Up to two ancestries are recorded for "
            f"each person, so the {responses:,.0f} responses here exceed the "
            f"{counted:,.0f} people and each share is the percentage of the people "
            "who reported that ancestry: the shares sum to more than 100, as in the ABS's own "
            "QuickStats. G08 names 30 ancestries; every other one is in 'Other', and 'Not "
            "stated' is people who gave none. ABS 2021 Census, G08 (total responses).")
    tables = ["G01"] + (["G02"] if median is not None else []) + (["G08"] if ancestry else [])
    return record(
        f"AUS-PROFILE-{code}", name, level=level, parent="AUS", country="AUS",
        parent_name=parent_name, match_by="shape_id", shape_id=unit["id"],
        codes={"asgs": code, "asgs_level": "LGA" if level == "admin2" else "STE"},
        sources=[{"field": "median_age/sex_ratio/ethnicity", "name": f"{SOURCE}: "
                  + "; ".join(TABLES[t] for t in tables), "url": API_PAGE, "year": YEAR,
                  "license": LICENCE}],
        **fields)


def build(tables: dict[tuple[str, str], list[tuple[dict[str, str], float]]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    people_lga = persons(tables[("G01", "LGA")])
    people_top = persons(tables[("G01", "SA2")])
    median_lga = medians(tables[("G02", "LGA")])
    median_top = medians(tables[("G02", "SA2")])
    ancestry_lga = ancestries(tables[("G08", "LGA")])
    ancestry_top = ancestries(tables[("G08", "SA2")])
    names = {**names_of(tables[("G01", "LGA")]), **names_of(tables[("G01", "SA2")])}

    check_national(people_top, median_top, ancestry_top)
    states = sorted(code for code in people_top if code != "AUS" and len(code) == 1)
    if states != [str(i) for i in range(1, 10)]:
        raise SystemExit(f"australia_profile: states read {states}, expected 1-9")
    check_parts(people_top, people_lga, states)

    parents = {u["id"]: u for u in admin1}
    states_drawn = bind(admin1, "admin1", {})
    lgas_drawn = bind(admin2, "admin2", parents)

    records: list[dict[str, Any]] = []
    for code, unit in sorted(states_drawn.items()):
        if code not in people_top:
            raise SystemExit(f"australia_profile: no G01 row for state {code} ({unit['name']})")
        records.append(unit_record(code, names.get(code, unit["name"]), unit, "admin1",
                                   people=people_top[code], median=median_top.get(code),
                                   ancestry=ancestry_top.get(code), parent_name=None))
    unbound: list[str] = []
    for code in sorted(people_lga):
        unit = lgas_drawn.get(code)
        if unit is None:
            if is_lga(code):
                unbound.append(code)
            continue
        own = (unit.get("population") or {}).get("value")
        if own and abs(own - people_lga[code]["persons"]) > tolerance(own):
            raise SystemExit(f"australia_profile: {unit['name']} ({code}): G01 counts "
                             f"{people_lga[code]['persons']:,.0f}, the map shows {own:,}")
        state = parents.get(unit.get("parent"), {}).get("name")
        records.append(unit_record(code, names.get(code, unit["name"]), unit, "admin2",
                                   people=people_lga[code], median=median_lga.get(code),
                                   ancestry=ancestry_lga.get(code), parent_name=state))
    missing = sorted(set(lgas_drawn) - set(people_lga))
    if missing:
        raise SystemExit(f"australia_profile: drawn LGAs the tables do not have: {missing}")
    for code in unbound:
        log(f"  no polygon, counted in its state only: {names.get(code, code)} ({code}, "
            f"{people_lga[code]['persons']:,.0f} people)")
    stray = [code for code in unbound if not code.endswith(UNDRAWN_SUFFIXES)]
    log(f"  {len(unbound)} LGA codes have no polygon; {len(stray)} of them are not a "
        f"no-usual-address or migratory code: {stray}")
    return records


def fetch(region: str, table: str) -> list[tuple[dict[str, str], float]]:
    flow = (AGENCY, f"C21_{table}_{region}", VERSION)
    rows = unpack(sdmx(flow, KEYS[(table, region)]))
    log(f"  {flow[1]} [{KEYS[(table, region)]}]: {len(rows):,} observations")
    return rows


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log("australia_profile: ABS 2021 Census G01, G02 and G08")
    tables = {(t, r): fetch(r, t) for t in ("G01", "G02", "G08") for r in ("LGA", "SA2")}
    records = build(tables, load_units("admin1"), load_units("admin2"))
    levels = defaultdict(int)
    for rec in records:
        levels[rec["level"]] += 1
    log(f"  {dict(levels)} records; median age on "
        f"{sum(1 for r in records if r.get('median_age'))}, ancestry on "
        f"{sum(1 for r in records if isinstance(r.get('ethnicity'), list))}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
