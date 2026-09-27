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

**Language is read as the census asks it.** Census 2022 asked everyone aged 3
and over "Do you speak a language other than English or Irish at home?" and,
if so, which. ``SAP2022T2T5LEA22`` "Speakers of foreign languages" gives, for
each area, those who do -- Polish, Spanish and French by name, every other
language (and a language left unnamed) as Other -- and ``SAP2022T3T1LEA22``
gives the area's population aged 3 and over. Everyone aged 3 and over who does
not speak another language at home is "English or Irish only", so the five
rows partition the population aged 3 and over, the way Wales's "English or
Welsh" does in the ONS table. An earlier version of this reader declared the
field not collected, because the foreign-language table alone leaves English
out; with the complement it does not, and the owner's direction is to fill a
field from what the census does measure. The census asks Irish as an ability
("Can you speak Irish?"), not as a home language, so English and Irish are not
told apart.

**The provinces are the census's, not the outlines'.** The four provinces'
religion, ethnicity and home language are written to ``ireland_province.json``,
each the sum of its local electoral areas' counts, and an area's province is
the one its county is in (the CSO appends the county to every area's name).
Left to the build, the provinces would be summed from the areas drawn inside
their outlines -- and the boundary file draws the Newport (Tipperary) area,
which is in Munster, inside Connacht's outline: measured on the CGAZ polygons,
99.5% of it lies in the Connacht polygon. The provinces' notes say so.

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
PROVINCE_OUT = "ireland_province.json"
SITE = PROCESSED.parent.parent / "site" / "data"
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

# Home language: speakers of a language other than English or Irish, and the
# population aged 3 and over they are a part of.
LANGUAGE_TABLE = ("SAP2022T2T5LEA22", "Language")
AGED_3_TABLE = ("SAP2022T3T1LEA22", "Ability to Speak Irish")
LANGUAGE_LABELS = {"Polish": "Polish", "Spanish": "Spanish", "French": "French",
                   "Other (incl. not stated)": "Other language"}
ENGLISH_OR_IRISH = "English or Irish only"
LANGUAGE_NOTE = (
    f"{SOURCE}, SAP2022T2T5LEA22 and SAP2022T3T1LEA22. Of usual residents aged 3 and over: "
    "the census asks \u2018Do you speak a language other than English or Irish at home?\u2019 "
    "and which. At local electoral area the CSO names Polish, Spanish and French and pools "
    "every other language, with speakers who did not name theirs, as Other language. Everyone "
    "else aged 3 and over is \u2018English or Irish only\u2019: those who said they speak no "
    "other language at home, and also those who did not answer the question, whom the CSO "
    "does not publish apart at this geography (its table has no not-stated row for the "
    "question itself), so the category is an upper bound. The census asks Irish as an "
    "ability, not as a home language, so English and Irish are not told apart.")

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


def read_table(matrix: str, subject_label: str) -> tuple[dict[str, str], dict[str, dict[str, float]]]:
    """One table read whole: area code -> {category label: value}, totals included."""
    dataset = read_dataset(matrix)
    elimination = (dataset.get("extension") or {}).get("elimination") or {}
    place = find_dimension(dataset, GEOGRAPHY)
    subject = find_dimension(dataset, subject_label)
    at = reader(dataset)
    pinned = {dim: (elimination.get(dim) if elimination.get(dim) in categories(dataset, dim)
                    else next(iter(categories(dataset, dim))))
              for dim in dataset["id"] if dim not in (place, subject)}
    for dim, code in pinned.items():
        if len(categories(dataset, dim)) > 1 and elimination.get(dim) != code:
            raise SystemExit(f"ireland: {matrix} dimension {dim} has no stated total")
    total = elimination.get(subject)
    names: dict[str, str] = {}
    out: dict[str, dict[str, float]] = {}
    for code, label in categories(dataset, place).items():
        if code == elimination.get(place):
            continue
        names[code] = label
        row = {}
        for scode, slabel in categories(dataset, subject).items():
            value = at({place: code, subject: scode, **pinned})
            if value is not None:
                row["Total" if scode == total else slabel] = value
        out[code] = row
    return names, out


def home_language(speakers: dict[str, float], aged_3: float, label: str) -> dict[str, float]:
    """The five rows that partition an area's population aged 3 and over."""
    total = speakers.get("Total")
    named = {k: v for k, v in speakers.items() if k != "Total"}
    unknown = sorted(set(named) - set(LANGUAGE_LABELS))
    if unknown:
        raise SystemExit(f"ireland: {label}: languages not declared: {unknown}")
    if total is None or abs(sum(named.values()) - total) > 0.5:
        raise SystemExit(f"ireland: {label}: the languages make {sum(named.values()):,.0f} "
                         f"against {total} speakers")
    if total > aged_3:
        raise SystemExit(f"ireland: {label}: {total:,.0f} speakers of another language "
                         f"against {aged_3:,.0f} people aged 3 and over")
    out = {LANGUAGE_LABELS[k]: v for k, v in named.items()}
    out[ENGLISH_OR_IRISH] = aged_3 - total
    return out


# The CSO names some councils apart from their county ("Cork County", "Galway
# County") and some together ("Limerick City and County"); each is filed under
# the county PROVINCE knows.
COUNTY_ALIASES = {
    "Dun Laoghaire-Rathdown": "Dún Laoghaire-Rathdown",
    "Cork City and Cork County": "Cork",
    "Cork County": "Cork",
    "Galway County": "Galway",
    "Limerick City and County": "Limerick",
    "Waterford City and County": "Waterford",
}


def province_of(label: str) -> str:
    """The province of an area the CSO labels "Name, County"."""
    county = label.rpartition(",")[2].strip()
    province = PROVINCE.get(COUNTY_ALIASES.get(county, county))
    if province is None:
        raise SystemExit(f"ireland: {label}: no province for county {county!r}")
    return province


def drawn_elsewhere(labels: dict[str, str], units2: list[dict[str, Any]],
                    units1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Areas the boundary file draws inside another province's outline.

    Each area is found on the map by the label the last build gave it as an
    alias ("Newport, Tipperary"); an area not found that way is skipped, since
    this only describes the map and decides nothing.
    """
    province = {u["id"]: u["name"] for u in units1}
    by_alias = {}
    for unit in units2:
        for alias in unit.get("aliases") or []:
            by_alias[alias] = unit
    out = []
    for code, label in sorted(labels.items()):
        unit = by_alias.get(label)
        if unit is None:
            continue
        drawn = province.get(unit.get("parent"))
        own = province_of(label)
        if drawn and drawn != own:
            out.append({"code": code, "label": label, "own": own, "drawn": drawn,
                        "shape": unit["id"]})
    return out


def outline_note(province: str, elsewhere: list[dict[str, Any]],
                 people: dict[str, float] | None = None) -> str:
    """What a province's outline on the map holds that its census figures do not."""
    parts = []
    for e in elsewhere:
        bare, _, county = (part.strip() for part in e["label"].rpartition(","))
        count = f", {people[e['code']]:,.0f} people" if people and e["code"] in people else ""
        area = f"the {bare} local electoral area ({county}{count})"
        if e["own"] == province:
            parts.append(f"The boundary file draws {area} inside {e['drawn']}'s outline; the "
                         f"census counts it in {province}, and so do these figures.")
        elif e["drawn"] == province:
            parts.append(f"The boundary file draws {area}, which the census counts in "
                         f"{e['own']}, inside this province's outline; these figures leave "
                         "it out.")
    return (" " + " ".join(parts)) if parts else ""


def province_records(areas: dict[str, str], fields: dict[str, dict[str, dict[str, float]]],
                     totals: dict[str, dict[str, float]], language: dict[str, dict[str, float]],
                     elsewhere: list[dict[str, Any]], units1: list[dict[str, Any]]
                     ) -> list[dict[str, Any]]:
    """The four provinces, each its own areas' counts added (areas by county)."""
    shapes = {u["name"]: u for u in units1}
    members: dict[str, list[str]] = {}
    for code, label in areas.items():
        members.setdefault(province_of(label), []).append(code)
    if sorted(members) != sorted(shapes):
        raise SystemExit(f"ireland: provinces {sorted(members)} against drawn {sorted(shapes)}")
    people = {code: totals["religion"].get(code) for code in areas}
    out = []
    state = {field: 0.0 for field in TABLES}
    for province, codes in sorted(members.items()):
        entry: dict[str, Any] = {}
        for field in TABLES:
            counts: dict[str, float] = {}
            for code in codes:
                for label, value in fields[field][code].items():
                    counts[label] = counts.get(label, 0.0) + value
            total = sum(totals[field].get(code) or sum(fields[field][code].values())
                        for code in codes)
            if abs(sum(counts.values()) - total) > total * 0.005:
                raise SystemExit(f"ireland: {province} {field}: categories make "
                                 f"{sum(counts.values()):,.0f} against {total:,.0f}")
            state[field] += total
            rows = shares(counts, total=total)
            entry[field] = rows
            entry[f"{field}_year"] = dated(rows, YEAR)
            entry[f"{field}_note"] = (PROVINCE_NOTES[field] + f" {province}: its {len(codes)} "
                                      "local electoral areas added together, each in the "
                                      "province of its county."
                                      + outline_note(province, elsewhere, people))
        spoken: dict[str, float] = {}
        for code in codes:
            for label, value in language[code].items():
                spoken[label] = spoken.get(label, 0.0) + value
        rows = shares(spoken, total=sum(spoken.values()))
        entry["language"] = rows
        entry["language_year"] = dated(rows, YEAR)
        entry["language_note"] = (LANGUAGE_NOTE + f" {province}: its {len(codes)} local "
                                  "electoral areas added together, each in the province of its "
                                  "county." + outline_note(province, elsewhere, people))
        shape = shapes[province]
        out.append(record(
            f"IRL-PROV-{province}", shape["name"], level="admin1", parent="IRL", country="IRL",
            match_by="shape_id", shape_id=shape["id"], **entry,
            sources=[{"field": "religion/ethnicity/language", "name": SOURCE, "url": URL,
                      "license": LICENCE}]))
    whole = {field: sum(totals[field].get(code) or sum(fields[field][code].values())
                        for code in areas) for field in TABLES}
    if any(abs(state[f] - whole[f]) > 0.5 for f in TABLES):
        raise SystemExit(f"ireland: the provinces make {state} against the areas' {whole}")
    return out


# The provinces' notes: the same census tables, added up.
PROVINCE_NOTES = {
    "religion": (
        f"{SOURCE}, SAP2022T2T4LEA22, of all usual residents, in the four categories the CSO "
        "publishes for local electoral areas -- Catholic, Other religion, No religion, Not "
        "stated -- so \u2018Other religion\u2019 holds the Church of Ireland, Presbyterians, "
        "Orthodox, Muslims and everyone else together, and a filter for Christianity reads a "
        "province at its **Catholic share alone**. (The CSO publishes a fuller classification "
        "for counties and provinces; these figures are the areas' four categories added.)"),
    "ethnicity": f"{SOURCE}, SAP2022T2T2LEA22. Of all usual residents. " + NOTES["ethnicity"],
}


def note(field: str) -> str:
    matrix = TABLES[field][0]
    return f"{SOURCE}, {matrix}. Of all usual residents. {NOTES[field]}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    ap.add_argument("--inspect", default=None, metavar="MATRIX",
                    help="print a PxStat table's dimensions and categories, and stop")
    args = ap.parse_args()

    if args.inspect:
        dataset = read_dataset(args.inspect)
        elimination = (dataset.get("extension") or {}).get("elimination") or {}
        for dim in dataset["id"]:
            cats = categories(dataset, dim)
            log(f"{dim} ({dataset['dimension'][dim].get('label')}): {len(cats)} categories, "
                f"total {elimination.get(dim)!r}")
            for code, label in list(cats.items())[:60]:
                log(f"    {code}: {label}")
        return 0

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

    log(f"ireland: language from {LANGUAGE_TABLE[0]} and {AGED_3_TABLE[0]}")
    _, speakers = read_table(*LANGUAGE_TABLE)
    _, aged_3 = read_table(*AGED_3_TABLE)
    if set(speakers) != set(areas) or set(aged_3) != set(areas):
        raise SystemExit("ireland: the language tables do not cover the same areas")
    language: dict[str, dict[str, float]] = {}
    for code in areas:
        language[code] = home_language(speakers[code], aged_3[code]["Total"], areas[code])
    for key in list(LANGUAGE_LABELS.values()) + [ENGLISH_OR_IRISH]:
        log(f"  {key}: {sum(language[c][key] for c in areas):,.0f}")

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

        spoken = shares(language[code], total=sum(language[code].values()))
        entry["language"] = spoken or gap(NOT_AVAILABLE)
        entry["language_year"] = dated(spoken, YEAR)
        entry["language_note"] = LANGUAGE_NOTE

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
            sources=[{"field": "religion/ethnicity/language", "name": SOURCE,
                      "url": URL, "license": LICENCE}],
        ))

    ambiguous = sorted(name for name, n in seen.items() if n > 1)
    log(f"  {len(records)} local electoral areas"
        + (f"; names shared by more than one area: {ambiguous}" if ambiguous else ""))
    write_json(args.out or PROCESSED / OUT, records)

    import json
    units1 = json.loads((SITE / "admin1" / "IRL.units.json").read_text())
    units2 = json.loads((SITE / "admin2" / "IRL.units.json").read_text())
    elsewhere = drawn_elsewhere(areas, units2, units1)
    for e in elsewhere:
        log(f"  {e['label']} ({e['shape']}): the census's {e['own']}, drawn inside {e['drawn']}")
    provinces = province_records(areas, fields, totals, language, elsewhere, units1)
    for r in provinces:
        log(f"  {r['name']}: religion {r['religion'][0]['group']} {r['religion'][0]['pct']}%, "
            f"language {r['language'][0]['group']} {r['language'][0]['pct']}%")
    write_json(PROCESSED / PROVINCE_OUT, provinces)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
