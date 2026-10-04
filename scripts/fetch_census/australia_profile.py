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

**The states' own tables.** The LGA tables file Christmas Island and the Cocos
(Keeling) Islands under Western Australia (their LGA codes begin with 5), while
the ASGS main structure, and the map, put them in Other Territories. The map's
state figures were the LGA tables added up, so Other Territories showed 2,505
people for its 4,788 and none of the Indian Ocean Territories' religion or
language. This file writes each state's own count (G01) and its own religion
(G14) and language (G13) from the SA2+ tables, which count the main structure.

**Two LGAs' language.** G13's finer listing does not add up for East Arnhem
and West Daly, so the map had no language there; the coarse partition the
table does add up at -- English only, Australian Indigenous languages, every
other language, not stated -- is written for an LGA only where the map has
none.

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
    "G13": "General Community Profile G13, Language used at home by proficiency in "
           "spoken English by sex",
    "G14": "General Community Profile G14, Religious affiliation by sex",
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
    # G13 SEXP.LANP.ENGLP.REGION.REGION_TYPE.STATE: persons, and only the
    # total, English only, all other languages, Australian Indigenous
    # languages and not stated -- the coarse partition (see coarse_language).
    ("G13", "LGA"): "3._T+1+O_T+8+_N._T...",
    ("G01", "SA2"): "1+2+3.P_1..AUS+STE.",
    ("G02", "SA2"): "1..AUS+STE.",
    ("G08", "SA2"): "._T..AUS+STE.",
    # G14 RELP.SEXP.REGION.REGION_TYPE.STATE, and G13 as above, for the states.
    ("G14", "SA2"): ".3..AUS+STE.",
    ("G13", "SA2"): "3.._T..AUS+STE.",
}
SEX = {"1": "male", "2": "female", "3": "persons"}

# Published national figures (2021 Census QuickStats, Australia): the control
# that the right slice of the right table was read.
NATIONAL = {"persons": 25_422_788, "male": 12_545_154, "female": 12_877_634,
            "median_age": 38, "English": 33.0, "Australian": 29.9,
            "Christianity": 43.9, "English only": 72.0}

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

# The Indian Ocean Territories' LGAs carry Western Australian codes -- the LGA
# structure files them under Western Australia, whose laws apply there -- but
# the ASGS main structure, whose states and territories the SA2+ tables count,
# puts them in Other Territories, and so does the map. Measured: Western
# Australia's 5xxxx LGAs make 2,662,304 people against the state's own
# 2,660,026, and Other Territories' 9xxxx LGAs 2,505 against its 4,788; these
# two, 1,692 and 593 people, are the difference.
STATE_OF = {"51710": "9",   # Christmas Island
            "51860": "9"}   # Cocos (Keeling) Islands


def state_of(code: str) -> str:
    """The state or territory an LGA code belongs to in the main structure."""
    return STATE_OF.get(code, code[:1])


def load_units(level: str) -> list[dict[str, Any]]:
    from common import as_drawn
    return as_drawn(json.loads((SITE / level / "AUS.units.json").read_text()))


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


RELIGION_NOTE = (f"ABS {YEAR} religious affiliation; the question is voluntary and 'not "
                 "stated' is retained as its own category. The state's own table (G14), "
                 "which counts the territories the map draws with it.")
LANGUAGE_NOTE = (f"ABS {YEAR} language used at home (G13), one answer per person, at the "
                 "outermost level of the ABS classification; 'not stated' is retained as "
                 "its own category. The state's own table, which counts the territories "
                 "the map draws with it.")


def state_compositions(religion_rows: list[tuple[dict[str, str], float]],
                       language_rows: list[tuple[dict[str, str], float]]
                       ) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """Religion and language shares for Australia and its states (G14, G13).

    The ABS's own state tables, read the way ``abs`` reads its LGA tables --
    its outermost level of each classification, checked against the table's
    own total -- because the map's states are the main structure's: the LGA
    tables file the Indian Ocean Territories under Western Australia.
    """
    from .abs import LANGUAGE_LABELS, group_by_region
    religion, _ = group_by_region(religion_rows, "RELP", "REGION")
    language, _ = group_by_region(language_rows, "LANP", "REGION", strict=True)
    rel = {code: shares({k: v for k, v in parts.items() if not k.lower().startswith("total")})
           for code, parts in religion.items()}
    lan = {code: shares({LANGUAGE_LABELS.get(k, k): v for k, v in parts.items()
                         if not k.lower().startswith("total")})
           for code, parts in language.items()}
    for field, table, label in (("religion", rel, "Christianity"),
                                ("language", lan, "English only")):
        share = next((r["pct"] for r in table.get("AUS", []) if r["group"] == label), None)
        log(f"  Australia {label} {share}% (published {NATIONAL[label]}%)")
        if share is None or abs(share - NATIONAL[label]) > 0.2:
            raise SystemExit(f"australia_profile: Australia's {field} has {label} at {share}%, "
                             f"published {NATIONAL[label]}%")
    return rel, lan


# The coarse partition of G13 for an LGA where the finer listing does not add
# up: "Speaks English only", the Australian Indigenous languages, the rest of
# "uses another language", and "not stated".
COARSE = {"_T": "total", "1": "English only", "O_T": "other", "8": "indigenous",
          "_N": "Not stated"}


def coarse_language(rows: Iterable[tuple[dict[str, str], float]]
                    ) -> dict[str, dict[str, float]]:
    """{region: {label: persons}}, a partition checked against G13's own total.

    "Australian Indigenous Languages" is part of "Other Languages Total" by
    definition (an Indigenous language is a language other than English), so
    the remainder of the second after the first is every other language.
    """
    cells: dict[str, dict[str, float]] = defaultdict(dict)
    for labels, value in rows:
        key = COARSE.get(labels.get("LANP_CODE", ""))
        if key and labels.get("ENGLP_CODE", "_T") == "_T":
            cells[labels["REGION_CODE"]][key] = value
    out = {}
    for region, c in cells.items():
        if set(c) != set(COARSE.values()):
            continue
        made = c["English only"] + c["other"] + c["Not stated"]
        if abs(made - c["total"]) > tolerance(c["total"]):
            raise SystemExit(f"australia_profile: G13 region {region}: English only, other "
                             f"languages and not stated make {made:,.0f}, not {c['total']:,.0f}")
        if c["indigenous"] > c["other"] + tolerance(c["total"]):
            raise SystemExit(f"australia_profile: G13 region {region}: Indigenous languages "
                             f"{c['indigenous']:,.0f} exceed all other languages {c['other']:,.0f}")
        out[region] = {"English only": c["English only"],
                       "Australian Indigenous Languages": c["indigenous"],
                       "Other languages": max(0.0, c["other"] - c["indigenous"]),
                       "Not stated": c["Not stated"]}
    return out


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
                    if is_lga(code) and state_of(code) == state)
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
            raise SystemExit(f"australia_profile: {level} unit {unit['name']!r} carries "
                             "no ASGS code")
        if code in out:
            raise SystemExit(f"australia_profile: two {level} units carry ASGS code {code}")
        if level == "admin2":
            parent = parents.get(unit.get("parent"))
            state = str((parent or {}).get("codes", {}).get("asgs") or "")
            if state != state_of(code):
                raise SystemExit(
                    f"australia_profile: {unit['name']!r} carries LGA {code}, which is in state "
                    f"{state_of(code)}, but the boundary file puts it in "
                    f"{(parent or {}).get('name')!r} (state {state or '?'})")
        out[code] = unit
    return out


def unit_record(code: str, name: str, unit: dict[str, Any], level: str, *,
                people: dict[str, float], median: float | None,
                ancestry: tuple[dict[str, float], float] | None,
                parent_name: str | None, extra: dict[str, Any] | None = None,
                extra_tables: tuple[str, ...] = ()) -> dict[str, Any]:
    ratio = round(100.0 * people["male"] / people["female"], 1)
    fields: dict[str, Any] = {
        "sex_ratio": measure(ratio, unit="males_per_100_females", year=YEAR, source=SOURCE),
        "sex_ratio_note": (
            f"Males per 100 females among the {people['persons']:,.0f} people counted in the "
            f"2021 Census at their usual address here ({people['male']:,.0f} males, "
            f"{people['female']:,.0f} females; ABS G01)."),
    }
    # A state's own head count: the map's came from adding up the LGA tables,
    # which put the Indian Ocean Territories' 2,285 people in Western Australia.
    if level == "admin1":
        fields["population"] = measure(int(round(people["persons"])), year=YEAR,
                                       source=f"{SOURCE} (G01)")
    fields.update(extra or {})
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
    tables = (["G01"] + (["G02"] if median is not None else [])
              + (["G08"] if ancestry else []) + list(extra_tables))
    written = [f for f in ("population", "median_age", "sex_ratio", "religion", "language",
                           "ethnicity") if f in fields]
    return record(
        f"AUS-PROFILE-{code}", name, level=level, parent="AUS", country="AUS",
        parent_name=parent_name, match_by="shape_id", shape_id=unit["id"],
        codes={"asgs": code, "asgs_level": "LGA" if level == "admin2" else "STE"},
        sources=[{"field": "/".join(written), "name": f"{SOURCE}: "
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
    religion_top, language_top = state_compositions(tables[("G14", "SA2")],
                                                    tables[("G13", "SA2")])
    coarse = coarse_language(tables[("G13", "LGA")])

    parents = {u["id"]: u for u in admin1}
    states_drawn = bind(admin1, "admin1", {})
    lgas_drawn = bind(admin2, "admin2", parents)

    records: list[dict[str, Any]] = []
    for code, unit in sorted(states_drawn.items()):
        if code not in people_top:
            raise SystemExit(f"australia_profile: no G01 row for state {code} ({unit['name']})")
        if not religion_top.get(code) or not language_top.get(code):
            raise SystemExit(f"australia_profile: no religion or language for state {code}")
        extra = {"religion": religion_top[code], "religion_year": YEAR,
                 "religion_note": RELIGION_NOTE, "language": language_top[code],
                 "language_year": YEAR, "language_note": LANGUAGE_NOTE}
        records.append(unit_record(code, names.get(code, unit["name"]), unit, "admin1",
                                   people=people_top[code], median=median_top.get(code),
                                   ancestry=ancestry_top.get(code), parent_name=None,
                                   extra=extra, extra_tables=("G13", "G14")))
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
        extra, extra_tables = {}, ()
        # Only where the map has no language: the LGA table's finer listing
        # is what abs.py writes everywhere it adds up.
        if not isinstance(unit.get("language"), list) and coarse.get(code):
            parts = coarse[code]
            extra = {"language": shares(parts), "language_year": YEAR,
                     "language_note": (
                         f"ABS {YEAR} language used at home (G13), one answer per person, at "
                         "the coarsest level the table adds up at here: English only, the "
                         "Australian Indigenous languages, every other language, and not "
                         "stated. The finer listing does not partition this area -- its "
                         "'Other' count is smaller than the Indigenous languages it holds "
                         "elsewhere -- so the languages besides English and the Indigenous "
                         "ones are given as the remainder of 'uses another language'.")}
            extra_tables = ("G13",)
            log(f"  {unit['name']} ({code}): language from G13's coarse partition "
                f"{ {k: int(v) for k, v in parts.items()} }")
        records.append(unit_record(code, names.get(code, unit["name"]), unit, "admin2",
                                   people=people_lga[code], median=median_lga.get(code),
                                   ancestry=ancestry_lga.get(code), parent_name=state,
                                   extra=extra, extra_tables=extra_tables))
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
    log("australia_profile: ABS 2021 Census G01, G02, G08, G13 and G14")
    tables = {key: fetch(key[1], key[0]) for key in KEYS}
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
