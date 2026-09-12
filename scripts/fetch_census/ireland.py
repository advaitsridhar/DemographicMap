#!/usr/bin/env python3
"""Ireland: religion and ethnicity by local electoral area (Census 2022).

Ireland had nothing subnational at all. Its four provinces and 166 local
electoral areas carried no religion, no ethnicity and no language, and the
only Irish figures on this map were the Factbook's national ones.

The CSO does not run PxWeb; it runs **PxStat**, whose API answers RPC-style
method names rather than the folder tree ``probe_pxweb`` walks. What that API
serves is the SAPMAP 2022 series, and the geography it serves it at is the one
this map draws: ``CSO Local Electoral Areas 2022``, 167 categories, which is
166 areas and the State.

* ``SAP2022T2T4LEA22`` religion -- titled, unhelpfully, just "Population".
  Searching table *titles* for "religion" returns nothing; the subject is a
  dimension, not a name. Four categories at this geography: Catholic, Other
  religion, No religion, Not stated. That is coarse, and coarse in a way worth
  stating on every record -- "Other religion" holds the Church of Ireland,
  Presbyterians, Orthodox and Muslims together, so a filter for Christianity
  reads an Irish area at its Catholic share and understates it by however many
  non-Catholic Christians live there. The fuller classification exists for
  counties and provinces; geoBoundaries draws neither at this level, so the
  real choice is four categories across 166 areas or nothing at all.
* ``SAP2022T2T2LEA22`` ethnicity -- eight categories, White Irish through
  Not stated.

**Language is not read, and the reason is the one Northern Ireland's MS-B05
made an hour earlier.** The CSO publishes ``SAP2022T2T5LEA22`` "Speakers of
foreign languages" and ``SAP2022T3T1LEA22`` "Population aged 3 years and over
by Ability to Speak Irish". Neither partitions the population by language. The
first counts only people who speak a foreign language and splits *them* by
which -- English is absent from it entirely, so read as a language field it
would report Ireland as a country where nobody speaks English. The second is
an ability, like Scotland's "can speak Gaelic". So Ireland's language is
declared in NOT_COLLECTED_POLICY with what the census does ask, rather than
filled with the nearest number.

Two things this reader is careful about.

**The totals are named by the source, not guessed.** Every PxStat dataset
carries ``extension.elimination``, which says for each dimension the category
that is its total: ``T`` for Ethnicity, ``IE0`` for the geography. Including a
total row in a composition doubles it, and picking the total out by looking for
the word "Total" is a guess that fails on the first table that spells it
differently.

**"Athlone" is two places.** The town straddles the Shannon, so there are two
Athlone local electoral areas, one each side of a county boundary, and the CSO
tells them apart only by the county it appends. Measured rather than assumed:
ATHLONE LEA-5 lies 100% inside Leinster and ATHLONE LEA-6 99.9% inside
Connacht, so the Westmeath row is the first and the Roscommon row the second.
Each is given its province as a stated parent, which is the mechanism the
matcher already has for exactly this.

Usage:
    python -m scripts.fetch_census.ireland
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, dated, gap, http_json, log, measure, record, shares,
    write_json,
)

BASE = "https://ws.cso.ie/public/api.restful"
OUT = "ireland_lea.json"
YEAR = 2022
SOURCE = "CSO Census 2022 (Ireland), SAPMAP local electoral areas"
LICENCE = "Creative Commons Attribution 4.0"
URL = "https://data.cso.ie/product/c2022p5"

# Matrix codes and the dimension each one's composition lives in. The dimension
# is named rather than positional: PxStat orders a dataset's dimensions however
# it likes, and two of these put the geography first while others put it last.
TABLES: dict[str, tuple[str, str]] = {
    "religion": ("SAP2022T2T4LEA22", "Religion"),
    "ethnicity": ("SAP2022T2T2LEA22", "Ethnicity"),
}

GEOGRAPHY = "CSO Local Electoral Areas 2022"

# The 26 counties and the four provinces, used only where a name is ambiguous.
# Local government split several counties into city and county councils, and
# the CSO writes whichever applies, so both spellings appear.
PROVINCE: dict[str, str] = {
    "Carlow": "Leinster", "Dublin": "Leinster", "Dublin City": "Leinster",
    "Fingal": "Leinster", "South Dublin": "Leinster",
    "Dún Laoghaire-Rathdown": "Leinster", "Dun Laoghaire-Rathdown": "Leinster",
    "Kildare": "Leinster", "Kilkenny": "Leinster", "Laois": "Leinster",
    "Longford": "Leinster", "Louth": "Leinster", "Meath": "Leinster",
    "Offaly": "Leinster", "Westmeath": "Leinster", "Wexford": "Leinster",
    "Wicklow": "Leinster",
    "Clare": "Munster", "Cork": "Munster", "Cork City": "Munster",
    "Kerry": "Munster", "Limerick": "Munster", "Tipperary": "Munster",
    "Waterford": "Munster",
    "Galway": "Connacht", "Galway City": "Connacht", "Leitrim": "Connacht",
    "Mayo": "Connacht", "Roscommon": "Connacht", "Sligo": "Connacht",
    "Cavan": "Ulster", "Donegal": "Ulster", "Monaghan": "Ulster",
}


def read_dataset(matrix: str) -> dict[str, Any]:
    """One PxStat table as JSON-stat 2.0.

    Note which path: the *collection* answers on the bare method name and 500s
    on the JSON-stat-suffixed one, and ReadDataset is the other way round. Both
    were measured; neither is guessable.
    """
    url = f"{BASE}/PxStat.Data.Cube_API.ReadDataset/{matrix}/JSON-stat/2.0/en"
    return http_json(url, timeout=300)


def categories(dataset: dict[str, Any], dim: str) -> dict[str, str]:
    """A dimension's category codes in published order, with their labels."""
    entry = dataset["dimension"][dim]["category"]
    index = entry.get("index")
    labels = entry.get("label") or {}
    if isinstance(index, dict):                 # {code: position}
        codes = [c for c, _ in sorted(index.items(), key=lambda kv: kv[1])]
    elif isinstance(index, list):
        codes = list(index)
    else:                                        # label-only, order as given
        codes = list(labels)
    return {code: labels.get(code, code) for code in codes}


def find_dimension(dataset: dict[str, Any], label: str) -> str:
    """The dimension id whose human label is this, or a readable failure."""
    for dim in dataset["id"]:
        if (dataset["dimension"][dim].get("label") or "").strip().lower() == label.lower():
            return dim
    have = [dataset["dimension"][d].get("label") for d in dataset["id"]]
    raise SystemExit(f"ireland: no dimension labelled {label!r}; the table has {have}")


def reader(dataset: dict[str, Any]):
    """Index into JSON-stat's flat value array by {dimension: category}.

    The array is row-major over ``id``/``size``, and ``value`` may arrive as a
    list or as a sparse object keyed by the flat index -- PxStat sends the
    second for tables with suppressed cells.
    """
    order = list(dataset["id"])
    sizes = list(dataset["size"])
    codes = {dim: list(categories(dataset, dim)) for dim in order}
    strides: list[int] = [1] * len(order)
    for i in range(len(order) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    values = dataset["value"]

    def at(pick: dict[str, str]) -> float | None:
        flat = 0
        for dim, stride in zip(order, strides):
            flat += codes[dim].index(pick[dim]) * stride
        cell = values[flat] if isinstance(values, list) else values.get(str(flat))
        return cell if isinstance(cell, (int, float)) else None

    return at


# What the four-way religion classification costs a reader, said on every
# record rather than left to be inferred from a short list.
NOTES = {
    "religion": (
        "At this geography the CSO publishes religion in four categories only "
        "-- Catholic, Other religion, No religion, Not stated. \u2018Other "
        "religion\u2019 therefore holds the Church of Ireland, Presbyterians, "
        "Orthodox, Muslims and everyone else together, so a filter for "
        "Christianity reads an Irish area at its **Catholic share alone** and "
        "understates it. The fuller classification is published for counties "
        "and provinces, which this map's second-level shapes are not."),
    "ethnicity": (
        "The CSO's eight-category ethnic or cultural background question. "
        "White Irish Traveller is a distinct category here, as it is in "
        "Northern Ireland's census."),
}


def note(field: str) -> str:
    matrix = TABLES[field][0]
    return f"{SOURCE}, {matrix}. Of all usual residents. {NOTES[field]}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    areas: dict[str, str] = {}
    fields: dict[str, dict[str, dict[str, float]]] = {}
    totals: dict[str, dict[str, float]] = {}

    for field, (matrix, subject_label) in TABLES.items():
        log(f"ireland: {field} from {matrix}")
        dataset = read_dataset(matrix)
        elimination = (dataset.get("extension") or {}).get("elimination") or {}
        place = find_dimension(dataset, GEOGRAPHY)
        subject = find_dimension(dataset, subject_label)
        at = reader(dataset)

        subject_codes = categories(dataset, subject)
        total_code = elimination.get(subject)
        if total_code not in subject_codes:
            raise SystemExit(
                f"ireland: {matrix} names no total category for {subject_label}; "
                f"elimination says {total_code!r} and the categories are "
                f"{list(subject_codes)}")

        # Every other dimension is pinned to its own total -- both sexes, all
        # ages, the single statistic -- so what is read is the whole population
        # of the area rather than one slice of it.
        pinned: dict[str, str] = {}
        for dim in dataset["id"]:
            if dim in (place, subject):
                continue
            available = categories(dataset, dim)
            code = elimination.get(dim)
            if code in available:
                pinned[dim] = code
            elif len(available) == 1:
                pinned[dim] = next(iter(available))
            else:
                raise SystemExit(
                    f"ireland: {matrix} dimension {dim} "
                    f"({dataset['dimension'][dim].get('label')}) has "
                    f"{len(available)} categories and no stated total")

        national = elimination.get(place)
        counts: dict[str, dict[str, float]] = {}
        area_totals: dict[str, float] = {}
        for code, label in categories(dataset, place).items():
            if code == national:
                continue
            areas.setdefault(code, label)
            here: dict[str, float] = {}
            for scode, slabel in subject_codes.items():
                if scode == total_code:
                    continue
                value = at({place: code, subject: scode, **pinned})
                if value is not None:
                    here[slabel] = value
            counts[code] = here
            published = at({place: code, subject: total_code, **pinned})
            if published:
                area_totals[code] = published
        fields[field] = counts
        totals[field] = area_totals
        log(f"  {len(counts)} areas, {len(subject_codes) - 1} categories")

    records: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for code, label in areas.items():
        bare, _, county = (part.strip() for part in label.rpartition(","))
        bare = bare or label.strip()
        seen[bare] = seen.get(bare, 0) + 1

    for code, label in areas.items():
        bare, _, county = (part.strip() for part in label.rpartition(","))
        bare = bare or label.strip()
        entry: dict[str, Any] = {}
        population = None
        for field in TABLES:
            counts = fields[field].get(code) or {}
            total = totals[field].get(code)
            summed = sum(counts.values())
            if total and abs(summed - total) > total * 0.005:
                raise SystemExit(
                    f"ireland: {label} {field} sums to {summed:,.0f} against a "
                    f"published {total:,.0f}; the categories chosen are wrong")
            if field == "religion" and total:
                population = int(total)
            entry[field] = shares(counts, total=total) or gap(NOT_AVAILABLE)
            entry[f"{field}_year"] = dated(entry[field], YEAR)
            entry[f"{field}_note"] = note(field)

        # A name shared by two areas cannot identify either. Only Athlone is,
        # and its province is what separates them -- see the module docstring
        # for how that was measured rather than assumed.
        parent = PROVINCE.get(county) if seen[bare] > 1 else None
        records.append(record(
            f"IRL-{code}", bare, level="admin2", parent="IRL", country="IRL",
            parent_name=parent,
            aliases=[label] if county else [],
            codes={"cso_code": code, "county": county} if county else {"cso_code": code},
            population=(measure(population, year=YEAR, source=SOURCE)
                        if population else gap(NOT_AVAILABLE)),
            **entry,
            sources=[{"field": "religion/ethnicity", "name": SOURCE,
                      "url": URL, "license": LICENCE}],
        ))

    ambiguous = sorted(name for name, n in seen.items() if n > 1)
    log(f"  {len(records)} local electoral areas"
        + (f"; names shared by more than one area: {ambiguous}" if ambiguous else ""))
    write_json(args.out or PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
