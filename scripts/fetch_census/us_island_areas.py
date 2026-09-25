#!/usr/bin/env python3
"""United States: the four Island Areas, from the 2020 census.

The American Community Survey, which ``us_acs.py`` reads for every state,
county and Puerto Rico, is not conducted in Guam, the U.S. Virgin Islands,
American Samoa or the Northern Mariana Islands. Their one official source is
the 2020 census itself, whose Demographic and Housing Characteristics files
for the Island Areas (``dhcgu``, ``dhcvi``, ``dhcas``, ``dhcmp`` on
api.census.gov) are read here, for each territory and each of its districts:

* population, P1_001N;
* median age, P9_001N;
* sex ratio, men per 1,000 women, from P8's male and female totals;
* ethnicity from P3, the race question as each territory's form asks it:
  Guam's and the Northern Marianas' name Chamorro, Carolinian, Chuukese,
  Filipino and the rest, the Virgin Islands' name the Caribbean peoples,
  American Samoa's Samoan and Tongan. Every single-race line with no finer
  line under it is a group, and two or more races is one more; together they
  partition the total, which is checked.

The labels are read from each file's own variable list, so each territory's
categories come from its own table and none is hardcoded.

Checked before anything is written: every composition sums to its P1 total,
and each territory's districts sum to it in population and in every race line.

Usage:
    python -m scripts.fetch_census.us_island_areas        # runner, needs CENSUS_API_KEY
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, write_json
from .us_acs import as_float, bind_by_fips, query

YEAR = 2020
BASE = "https://api.census.gov/data/2020/dec/{dataset}"
LICENSE = "Public domain (U.S. Census Bureau)"
SOURCE = "U.S. Census Bureau, 2020 Census, Demographic and Housing Characteristics for the Island Areas"
# The dataset for each territory, its FIPS code, and its name on the map.
AREAS = {
    "dhcgu": ("66", "Guam"),
    "dhcvi": ("78", "United States Virgin Islands"),
    "dhcas": ("60", "American Samoa"),
    "dhcmp": ("69", "Commonwealth of the Northern Mariana Islands"),
}
# The Bureau names a district "St. Croix Island" or "Manu'a District"; the
# map calls them "St. Croix" and "Manu'a".
SUFFIX = re.compile(r"\s+(Island|District|Municipality)$")
NOTE = ("The 2020 census's race question as {area}'s form asks it; the American "
        "Community Survey, which gives the rest of the United States its figures, "
        "is not conducted here. Each person of one race is shown under the most "
        "detailed group the table names, and people of two or more races as one "
        "group. Not comparable with other countries' ethnicity classifications.")


def paths(dataset: str, group: str) -> dict[str, list[str]]:
    """Each count variable of a table, as the path of its label."""
    text = http_get(f"{BASE.format(dataset=dataset)}/groups/{group}.json", timeout=120)
    variables = json.loads(text)["variables"]
    out = {}
    for code, meta in variables.items():
        if not re.fullmatch(rf"{group}_\d+N", code):
            continue
        out[code] = [p.strip().rstrip(":") for p in meta["label"].split("!!") if p.strip()]
    if not out:
        raise SystemExit(f"us_island_areas: {dataset} {group} has no count variables")
    return out


def race_lines(dataset: str) -> tuple[str, dict[str, str]]:
    """(the total's variable, {variable: group}) for the partition of P3."""
    table = paths(dataset, "P3")
    total = next(code for code, path in table.items() if path == ["Total"])
    single = {code: path for code, path in table.items()
              if path[:2] == ["Total", "One Race"] and len(path) > 2}
    leaves = {code: path[-1] for code, path in single.items()
              if not any(other[:len(path)] == path and len(other) > len(path)
                         for other in single.values())}
    several = [code for code, path in table.items() if path == ["Total", "Two or More Races"]]
    if len(several) != 1:
        raise SystemExit(f"us_island_areas: {dataset} P3 has {len(several)} two-or-more lines")
    names = list(leaves.values())
    if len(set(names)) != len(names):
        raise SystemExit(f"us_island_areas: {dataset} P3 repeats a group name: {sorted(names)}")
    return total, {**leaves, several[0]: "Two or more races"}


def sex_lines(dataset: str) -> tuple[str, str]:
    table = paths(dataset, "P8")
    male = [c for c, p in table.items() if p == ["Total", "Male"]]
    female = [c for c, p in table.items() if p == ["Total", "Female"]]
    if len(male) != 1 or len(female) != 1:
        raise SystemExit(f"us_island_areas: {dataset} P8 has {male} male, {female} female totals")
    return male[0], female[0]


def median_line(dataset: str) -> str:
    """P9's median for both sexes together, found by its label."""
    table = paths(dataset, "P9")
    both = [c for c, p in table.items() if len(p) == 2 and p[0].startswith("Median age")
            and p[1] in ("Total", "Both sexes")]
    if len(both) != 1:
        raise SystemExit(f"us_island_areas: {dataset} P9 labels: {sorted(table.items())}")
    return both[0]


def rows(dataset: str, geo: str, key: str | None, get: list[str]) -> list[dict[str, str]]:
    # The API takes at most fifty variables a request.
    out: dict[str, dict[str, str]] = {}
    for i in range(0, len(get), 45):
        for row in query(YEAR, get[i:i + 45], geo, key, base=BASE.format(dataset=dataset)):
            gid = row["state"] + row.get("county", "")
            out.setdefault(gid, {}).update(row)
    return list(out.values())


def figures(row: dict[str, str], total: str, race: dict[str, str],
            sex: tuple[str, str], age: str, area: str) -> dict[str, Any]:
    people = as_float(row.get("P1_001N"))
    counts = {label: as_float(row.get(code)) or 0.0 for code, label in race.items()}
    if people is None or as_float(row.get(total)) != people or round(sum(counts.values())) != people:
        raise SystemExit(f"us_island_areas: {row['NAME']}: P1 {people}, P3 total "
                         f"{row.get(total)}, P3 lines sum to {sum(counts.values()):,.0f}")
    median = as_float(row.get(age))
    men, women = (as_float(row.get(code)) for code in sex)
    out: dict[str, Any] = {
        "population": measure(int(people), year=YEAR, source=SOURCE),
        "median_age": (measure(median, unit="years", year=YEAR, source=SOURCE)
                       if median is not None and people else gap(NOT_AVAILABLE)),
        "sex_ratio": (measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE)
                      if men is not None and women else gap(NOT_AVAILABLE)),
    }
    if people:
        # A basis of its own, so the country's sum -- the ACS's race and
        # Hispanic-origin categories -- leaves these out and names them rather
        # than listing Chamorro at 0.0% beside "White (non-Hispanic)".
        out.update(ethnicity=shares({k: v for k, v in counts.items() if v}, total=people),
                   ethnicity_year=YEAR, ethnicity_note=NOTE.format(area=area),
                   ethnicity_basis="race, as the Island Areas' census asks it")
    return out


def main() -> int:
    key = os.environ.get("CENSUS_API_KEY")
    records: list[dict[str, Any]] = []
    for dataset, (fips, area) in AREAS.items():
        total, race = race_lines(dataset)
        sex = sex_lines(dataset)
        age = median_line(dataset)
        get = ["P1_001N", age, *sex, total, *race]
        whole = rows(dataset, f"state:{fips}", key, get)
        parts = rows(dataset, "county:*", key, get)
        if len(whole) != 1 or not parts:
            raise SystemExit(f"us_island_areas: {dataset}: {len(whole)} territory rows, "
                             f"{len(parts)} districts")
        whole = whole[0]
        for code in ["P1_001N", total, *race]:
            summed = sum(as_float(p.get(code)) or 0.0 for p in parts)
            if summed != (as_float(whole.get(code)) or 0.0):
                raise SystemExit(f"us_island_areas: {area}'s districts sum to {summed:,.0f} "
                                 f"in {code}, the territory to {whole.get(code)}")
        cite = [{"field": "population/median age/sex ratio/ethnicity", "name": SOURCE,
                 "url": BASE.format(dataset=dataset), "license": LICENSE}]
        records.append(record(f"USA-{fips}", area, level="admin1", parent="USA", country="USA",
                              codes={"geoid": fips, "fips_state": fips},
                              sources=cite, **figures(whole, total, race, sex, age, area)))
        for part in parts:
            gid = part["state"] + part["county"]
            name = SUFFIX.sub("", part["NAME"].split(",")[0].strip())
            records.append(record(
                f"USA-{gid}", name, level="admin2", parent=f"USA-{fips}", country="USA",
                parent_name=area, codes={"geoid": gid, "fips_state": fips,
                                         "fips_county": part["county"]},
                sources=cite, **figures(part, total, race, sex, age, area)))
        people = int(as_float(whole["P1_001N"]) or 0)
        top = sorted(race, key=lambda code: -(as_float(whole.get(code)) or 0))[:4]
        log(f"  {area}: {people:,} people in {len(parts)} districts; median age "
            f"{whole.get(age)}; largest groups {', '.join(race[c] for c in top)}")
    bound = bind_by_fips(records)
    log(f"  {len(records)} records, {bound} districts pinned to their polygon by FIPS code")
    write_json(PROCESSED / "us_island_areas.json", records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
