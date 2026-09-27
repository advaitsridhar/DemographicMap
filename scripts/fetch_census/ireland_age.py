#!/usr/bin/env python3
"""Ireland: median age and sex ratio, by province and local electoral area
(Census 2022).

``ireland`` reads the Census 2022 compositions for the 166 local electoral
areas and leaves age and sex aside; every Irish shape on the map had neither
figure. Two CSO PxStat tables supply them, each at the finest age it is
published at for its geography:

* ``FY006B`` "Population" by sex, **single year of age** and county and city
  -- the provinces are whole counties, so each province's median is taken
  from single years, and its count is the counties' sum.
* ``SAP2022T1T1ALEA22`` "Population" by sex and **five-year age group** and
  local electoral area -- the only age table the CSO publishes for these
  areas. Each area's median is interpolated within the five-year group that
  holds its middle person, and every record says so.

Sex ratio is males per 1,000 females, the unit every other age-sex reader on
this map writes.

The areas are written under the names ``ireland`` writes them, so the two
files land on the same polygons by the same match -- including the two
Athlone areas, told apart by their province.

Checks, each of which stops the run:

* every area's and county's age groups make its published total, for each
  sex, and its two sexes make its both-sexes total;
* the counties of each province add to the province's areas, and all of them
  to the State's own published count;
* the State's median recomputed from its single years is within 0.3 years of
  the CSO's published figure (38.8 in Census 2022).

Usage:
    python -m scripts.fetch_census.ireland_age
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from typing import Any

from ._shared import PROCESSED, log, measure, record, write_json
from .cod_ps_age import grouped_median
from .ireland import (
    COUNTY_ALIASES, LICENCE, PROVINCE, SITE, categories, drawn_elsewhere, find_dimension,
    outline_note, read_dataset, reader,
)
from .redatam import median_age

OUT = "ireland_age.json"
YEAR = 2022
LEA_TABLE = "SAP2022T1T1ALEA22"
COUNTY_TABLE = "FY006B"
URL = "https://data.cso.ie/"
# The CSO's national median age for Census 2022, as its Profile 1 release
# states it ("the median age of the population was 38.8 years").
PUBLISHED_MEDIAN = 38.8

# FY006B names some units that are not a county's whole: Dublin's four
# councils and the city and county councils of Cork and Galway are listed
# separately, and so is each "County" total above some of them. Only the
# units in PROVINCE (ireland's list of councils) are read, and each once, under
# ireland's COUNTY_ALIASES.


def band(label: str) -> tuple[int, int | None]:
    """"Age 20-24" -> (20, 24); "Age 85 and over" / "Age 85+" -> (85, None)."""
    text = label.replace("Age", "").strip()
    if (m := re.match(r"^(\d+)\s*-\s*(\d+)$", text)):
        return int(m.group(1)), int(m.group(2))
    if (m := re.match(r"^(\d+)\s*(\+|years and over|and over)", text)):
        return int(m.group(1)), None
    raise SystemExit(f"ireland_age: an age group the CSO calls {label!r}")


def single_year(label: str) -> int:
    """"Under 1 year" -> 0, "7 years" -> 7, "100 years and over" -> 100."""
    text = label.strip().lower()
    if text.startswith("under 1"):
        return 0
    if (m := re.match(r"^(\d+)\s*years?", text)):
        return int(m.group(1))
    raise SystemExit(f"ireland_age: a single year of age the CSO calls {label!r}")


def pinned_reader(matrix: str, place_label: str, age_label: str):
    """(dataset, place dim, age dim, sex dim, at, pinned, elimination)."""
    dataset = read_dataset(matrix)
    elimination = (dataset.get("extension") or {}).get("elimination") or {}
    place = find_dimension(dataset, place_label)
    age = find_dimension(dataset, age_label)
    sex = find_dimension(dataset, "Sex")
    pinned: dict[str, str] = {}
    for dim in dataset["id"]:
        if dim in (place, age, sex):
            continue
        available = categories(dataset, dim)
        if len(available) == 1:
            pinned[dim] = next(iter(available))
        elif str(YEAR) in available and "year" in (dataset["dimension"][dim].get("label")
                                                   or "").lower():
            # FY006B carries 2011 and 2016 beside 2022; the census read is 2022.
            pinned[dim] = str(YEAR)
        elif elimination.get(dim) in available:
            pinned[dim] = elimination[dim]
        else:
            raise SystemExit(f"ireland_age: {matrix} dimension {dim} has {len(available)} "
                             "categories and no stated total")
    return dataset, place, age, sex, reader(dataset), pinned, elimination


def sexes(dataset: dict[str, Any], sex: str) -> dict[str, str]:
    """'M', 'F', 'B' -> the table's own codes, by label."""
    out: dict[str, str] = {}
    for code, label in categories(dataset, sex).items():
        low = label.lower()
        key = "B" if "both" in low else "F" if "female" in low else "M" if "male" in low else None
        if key:
            out[key] = code
    if sorted(out) != ["B", "F", "M"]:
        raise SystemExit(f"ireland_age: sexes are {categories(dataset, sex)}")
    return out


def read_leas() -> dict[str, dict[str, Any]]:
    dataset, place, age, sex, at, pinned, elimination = pinned_reader(
        LEA_TABLE, "CSO Local Electoral Areas 2022", "Age")
    sx = sexes(dataset, sex)
    total_age = elimination.get(age)
    ages = {c: band(l) for c, l in categories(dataset, age).items() if c != total_age}
    out: dict[str, dict[str, Any]] = {}
    for code, label in categories(dataset, place).items():
        if code == elimination.get(place):
            continue
        entry: dict[str, Any] = {"label": label}
        for key, scode in sx.items():
            groups = [(lo, hi, at({place: code, age: a, sex: scode, **pinned}) or 0)
                      for a, (lo, hi) in sorted(ages.items(), key=lambda kv: kv[1][0])]
            whole = at({place: code, age: total_age, sex: scode, **pinned})
            if whole is None or sum(g[2] for g in groups) != whole:
                raise SystemExit(f"ireland_age: {label} ({key}): age groups make "
                                 f"{sum(g[2] for g in groups):,.0f} against {whole}")
            entry[key] = {"groups": groups, "total": whole}
        if entry["M"]["total"] + entry["F"]["total"] != entry["B"]["total"]:
            raise SystemExit(f"ireland_age: {label}: males and females do not make both sexes")
        out[code] = entry
    state = elimination.get(place)
    out["_state"] = {"total": at({place: state, age: total_age, sex: sx["B"], **pinned})}
    log(f"  {LEA_TABLE}: {len(out) - 1} areas, {len(ages)} age groups")
    return out


def read_counties() -> dict[str, dict[str, Any]]:
    dataset, place, age, sex, at, pinned, elimination = pinned_reader(
        COUNTY_TABLE, "County and City", "Single Year of Age")
    sx = sexes(dataset, sex)
    total_age = elimination.get(age)
    ages = {c: single_year(l) for c, l in categories(dataset, age).items() if c != total_age}
    out: dict[str, dict[str, Any]] = {}
    for code, label in categories(dataset, place).items():
        name = COUNTY_ALIASES.get(label.strip(), label.strip())
        is_state = code == elimination.get(place)
        if not is_state and name not in PROVINCE:
            raise SystemExit(f"ireland_age: {COUNTY_TABLE} council {label!r} has no province")
        entry: dict[str, Any] = {"label": label, "province": None if is_state else PROVINCE[name]}
        for key, scode in sx.items():
            years = Counter({y: at({place: code, age: a, sex: scode, **pinned}) or 0
                             for a, y in ages.items()})
            whole = at({place: code, age: total_age, sex: scode, **pinned})
            if whole is None or sum(years.values()) != whole:
                raise SystemExit(f"ireland_age: {label} ({key}): single years make "
                                 f"{sum(years.values()):,.0f} against {whole}")
            entry[key] = {"years": years, "total": whole}
        out["_state" if is_state else name] = entry
    log(f"  {COUNTY_TABLE}: {len(out) - 1} councils, {len(ages)} single years")
    return out


def area_median(entry: dict[str, Any]) -> float | None:
    """An area's median age, interpolated within its five-year group, both sexes."""
    groups = [(lo, hi, m + f) for (lo, hi, m), (_, _, f)
              in zip(entry["M"]["groups"], entry["F"]["groups"])]
    return grouped_median(groups)


def province_years(parts: list[dict[str, Any]]) -> Counter:
    """A province's single years of age: its councils' men and women added."""
    return sum((c["M"]["years"] + c["F"]["years"] for c in parts), Counter())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    leas = read_leas()
    counties = read_counties()
    state_leas = leas.pop("_state")["total"]
    state = counties.pop("_state")
    if state["B"]["total"] != state_leas:
        raise SystemExit(f"ireland_age: the State is {state['B']['total']:,.0f} by county and "
                         f"{state_leas:,.0f} by area")
    if sum(c["B"]["total"] for c in counties.values()) != state["B"]["total"]:
        raise SystemExit("ireland_age: the councils read do not make the State")
    if sum(e["B"]["total"] for e in leas.values()) != state_leas:
        raise SystemExit("ireland_age: the areas do not make the State")
    national = median_age(state["M"]["years"] + state["F"]["years"])
    if national is None or abs(national - PUBLISHED_MEDIAN) > 0.3:
        raise SystemExit(f"ireland_age: the State's median from single years is {national}, "
                         f"the CSO publishes {PUBLISHED_MEDIAN}")
    log(f"  the State: {state['B']['total']:,.0f} people, median {national} "
        f"(published {PUBLISHED_MEDIAN})")

    source_lea = f"CSO Census {YEAR} (Ireland), {LEA_TABLE}, by sex and five-year age group"
    source_county = f"CSO Census {YEAR} (Ireland), {COUNTY_TABLE}, by sex and single year of age"
    records: list[dict[str, Any]] = []

    # Areas: named as ireland names them, so both files meet on one polygon.
    bare_count = Counter(e["label"].rpartition(",")[0].strip() or e["label"].strip()
                         for e in leas.values())
    by_province: Counter = Counter()
    for code, entry in leas.items():
        label = entry["label"]
        bare, _, county = (part.strip() for part in label.rpartition(","))
        bare = bare or label.strip()
        province = PROVINCE.get(COUNTY_ALIASES.get(county, county))
        if province is None:
            raise SystemExit(f"ireland_age: {label}: no province for county {county!r}")
        by_province[province] += entry["B"]["total"]
        median = area_median(entry)
        men, women = entry["M"]["total"], entry["F"]["total"]
        records.append(record(
            f"IRL-AGE-{code}", bare, level="admin2", parent="IRL", country="IRL",
            parent_name=province if bare_count[bare] > 1 else None,
            aliases=[label] if county else [],
            codes={"cso_code": code, "county": county},
            median_age=measure(median, unit="years", year=YEAR, source=source_lea),
            median_age_note=("Interpolated within the five-year age group that holds the "
                             "middle person: the CSO publishes this area's ages in five-year "
                             "groups only (single years are published by county)."),
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=source_lea),
            sources=[{"field": "median age/sex ratio", "name": source_lea, "url": URL,
                      "year": YEAR, "license": LICENCE}]))

    # Where the boundary file draws an area inside another province's outline
    # (Newport, Tipperary, inside Connacht), the province's figure and the
    # areas drawn inside its outline disagree; its note says why.
    import json
    elsewhere = drawn_elsewhere({c: e["label"] for c, e in leas.items()},
                                json.loads((SITE / "admin2" / "IRL.units.json").read_text()),
                                json.loads((SITE / "admin1" / "IRL.units.json").read_text()))
    people = {c: e["B"]["total"] for c, e in leas.items()}

    # Provinces: the councils' single years added together.
    for province in ("Connacht", "Leinster", "Munster", "Ulster"):
        parts = [c for c in counties.values() if c["province"] == province]
        men = sum(c["M"]["total"] for c in parts)
        women = sum(c["F"]["total"] for c in parts)
        if men + women != by_province[province]:
            raise SystemExit(f"ireland_age: {province} is {men + women:,.0f} by council and "
                             f"{by_province[province]:,.0f} by area")
        years = province_years(parts)
        label = province if province != "Ulster" else "Ulster (part of)"
        records.append(record(
            f"IRL-AGE-{province}", province, level="admin1", parent="IRL", country="IRL",
            population=measure(int(men + women), year=YEAR, source=source_county),
            population_note=(f"{label}: the usually resident population of its "
                             f"{len(parts)} councils' areas, Census {YEAR}."
                             + outline_note(province, elsewhere, people)),
            median_age=measure(median_age(years), unit="years", year=YEAR,
                               source=source_county),
            median_age_note=("Interpolated within the single year of age holding the middle "
                             f"person, from the {len(parts)} councils' single years added "
                             "together."),
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=source_county),
            sources=[{"field": "population/median age/sex ratio", "name": source_county,
                      "url": URL, "year": YEAR, "license": LICENCE}]))
        log(f"  {province}: {len(parts)} councils, {men + women:,.0f} people, median "
            f"{records[-1]['median_age']['value']}")
    write_json(args.out or PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
