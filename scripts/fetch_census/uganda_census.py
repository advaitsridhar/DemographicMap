#!/usr/bin/env python3
"""Uganda: the 2024 census by county, on the counties the map draws.

The Uganda Bureau of Statistics publishes the National Population and Housing
Census 2024 down to the parish through the dissemination dashboard on
statistics.ubos.org/nphc, whose JSON interface answers by level (district,
county, subcounty, parish): the population by sex, and the population in a set
of age groups (0-4, 0-17, 6-12, 13-18, 14-64, 15 and over, 18-30, 15-24, 18
and over, 60 and over, 65 and over, 80 and over). The host sends its leaf
certificate without the intermediate above it, so it is reached with the
missing link completed from the certificate's own AIA record (``aia``), still
fully verified.

**The map's counties are not the census's.** The boundary file draws 151
second-level polygons in Uganda: the counties as they stood around 2002, with
a few municipalities, where the 2024 census counts some 310 counties, cities
and municipalities, many of them cut from the older counties since (Kyadondo
into Kira and Nansana, Busiro into Entebbe and Makindye-Ssabagabo...). The
dashboard publishes each 2024 unit's outline with its figures, so which 2024
units make each polygon is measured rather than guessed: ``--points`` writes
points sampled evenly over every 2024 unit (``uganda_county_points.json``),
and ``uganda_counties`` (written by ``uganda_crosswalk``, whose docstring has
the rules) records which units each polygon is the union of (PLACED), which
polygons are whole units and sub-counties together (SETTLED: the 2024
sub-counties of the sub-county profile tables, ``--subcounty-table``, placed
by OCHA's sub-county outlines of 2020, ``--subcounty-points``), and, for the
others, which 2024 units cross the polygon's line (STRADDLING). A polygon in
PLACED or SETTLED takes the sum of its units' figures; every other one says
why it has none. (OCHA's COD-PS table for Uganda is by district, and its 54
figures that stood on county polygons of the same names were districts',
Mityana's with Busujju in it and Serere's with Kasilo.)

**What is written.** For each region and each placed county: the population
and men per 1,000 women, and the median age, interpolated within the age
group that holds the middle person, from the dashboard's overlapping groups
(0-4, 0-17, 15 and over, 15-24, 18-30, 18 and over, 60 and over, 65 and over,
80 and over) differenced into disjoint ones (0-4, 5-14, 15-17, 18-24, 25-30,
31-59, 60-64, 65-79, 80 and over). A sex ratio far from the country's (below
850 or above 1,150) says it is the census's own figure, which its dashboard
and its sub-county profile tables both give. The
regions are the sums of their districts: the dashboard draws one county,
Chekwi in Nakapiripirit, without figures, so its counties make 45,826,553
people, while its districts make 45,895,961 of the 45,905,417 the Bureau
announced as the final count. Every county also says why it has no religion or
ethnicity, and every region why it has no ethnicity (``composition``): the
2024 Final Report publishes both for the country only (Volume 1, Tables 3.1
and 3.2), as the 2014 Main Report did, and the 2002 census religion by
district, which ``uganda_2002`` writes where it stands on the drawn ground.

**Checks.** Each unit's sexes make its total and its age groups make it too;
the districts make the country's total within a tenth of a percent, and each
district's counties make the district but where one is drawn without figures.

Usage:
    python -m scripts.fetch_census.uganda_census --points
    python -m scripts.fetch_census.uganda_census
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .cod_ps_age import grouped_median

API = "https://statistics.ubos.org/nphc/api"
PAGE = "https://statistics.ubos.org/nphc/"
POINTS = "uganda_county_points.json"
# Points sampled per 2024 county, at the least.
SAMPLES = 60


def count(value: Any) -> int | None:
    """The dashboard writes counts as numbers in one table and strings in another."""
    if value in (None, ""):
        return None
    try:
        return int(round(float(str(value).replace(",", ""))))
    except ValueError:
        return None


def fetch_json(url: str) -> Any:
    body = http_get(url, cache=False, timeout=300, aia=True)
    text = body if isinstance(body, str) else body.decode("utf-8", "replace")
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise SystemExit(f"uganda_census: {url} answered no JSON: {text[:200]!r}")
    return json.loads(text[start:])


def sample(geometry: dict[str, Any], wanted: int) -> tuple[list[list[float]], float]:
    """Points on a regular grid over the polygon, about ``wanted`` of them, and its area in km2."""
    from shapely.geometry import Point, shape     # noqa: PLC0415
    poly = shape(geometry)
    if not poly.is_valid:
        poly = poly.buffer(0)
    west, south, east, north = poly.bounds
    lat = (south + north) / 2
    km_x = 111.32 * math.cos(math.radians(lat))
    area = poly.area * km_x * 110.57
    step = math.sqrt(poly.area / max(wanted, 1)) or 0.01
    points: list[list[float]] = []
    while True:
        points = []
        y = south + step / 2
        while y < north:
            x = west + step / 2
            while x < east:
                if poly.contains(Point(x, y)):
                    points.append([round(x, 5), round(y, 5)])
                x += step
            y += step
        if len(points) >= wanted or step < 1e-4:
            break
        step /= 1.4
    rep = poly.representative_point()
    points.append([round(rep.x, 5), round(rep.y, 5)])
    return points, round(area, 1)


def hdx_features(dataset: str, level: int) -> list[dict[str, Any]]:
    """The features of one level of an HDX Common Operational Dataset of boundaries.

    The geojson archive holds one file per level, named for it ("ken_admin2",
    "eth_admbnda_adm3_..."); the one whose name carries the level is read.
    """
    import io                                       # noqa: PLC0415
    import re                                       # noqa: PLC0415
    import zipfile                                  # noqa: PLC0415

    from .uscb import package                       # noqa: PLC0415
    resources = [r for r in package(dataset).get("resources", [])
                 if str(r.get("name") or r.get("url") or "").lower().endswith("geojson.zip")]
    if not resources:
        raise SystemExit(f"uganda_census: {dataset} has no geojson archive")
    url = resources[0]["url"]
    blob = http_get(url, binary=True, cache=False, timeout=900)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = [n for n in zf.namelist()
                 if re.search(rf"adm(?:in)?_?{level}(?!\d)", n.lower())
                 and n.lower().endswith(("json", "geojson"))]
        log(f"  {url}: {len(blob):,} bytes; members {zf.namelist()}; level {level}: {names}")
        if len(names) != 1:
            raise SystemExit(f"uganda_census: {len(names)} files for level {level} in {url}")
        data = json.loads(zf.read(names[0]).decode("utf-8-sig"))
    return data.get("features") or []


def write_cod_points(dataset: str, level: int, out: str, wanted: int = 40) -> int:
    """Points sampled over every unit of one COD level, with the unit's names and codes."""
    rows = []
    for feature in hdx_features(dataset, level):
        props = feature.get("properties") or {}
        keep = {k: v for k, v in props.items()
                if any(w in k.lower() for w in ("name", "pcode", "code")) and v not in (None, "")}
        if not feature.get("geometry"):
            continue
        points, area = sample(feature["geometry"], wanted)
        rows.append({"props": keep, "area_km2": area, "points": points})
    log(f"  {dataset} level {level}: {len(rows)} units, "
        f"{sum(len(r['points']) for r in rows):,} points")
    write_json(PROCESSED / out, rows)
    return 0


# The 2024 census's sub-county profile tables (October 2025): every district,
# county, sub-county and parish with its men, women and total (Table 1) and its
# people in the dashboard's age groups (Table 3). The Bureau's host fails
# certificate checks from the runner, so the Internet Archive's capture is read.
WORKBOOK_PAGE = ("https://www.ubos.org/wp-content/uploads/2025/10/"
                 "NPHC-2024-Subcounty-Profiles-Excel-Tables.xlsx")
WORKBOOK = f"https://web.archive.org/web/20251008162910id_/{WORKBOOK_PAGE}"
WORKBOOK_SOURCE = ("Uganda Bureau of Statistics, National Population and Housing Census 2024, "
                   "Sub-county Profiles, Tables 1 and 3 (population by sex and by age group)")
SUBCOUNTY_TABLE = "uganda_subcounties.json"
SUBCOUNTY_POINTS = "uganda_subcounty_points.json"
# Table 3's age-group headings -> the dashboard's keys for the same groups.
WORKBOOK_AGES = {"0 - 4": "age_0_4", "0 - 17": "age_0_17", "15+": "age_15_plus",
                 "15 - 24": "age_15_24", "18 - 30": "age_18_30", "18+": "age_18_plus",
                 "60+": "age_60_plus", "65+": "age_65_plus", "80+": "age_80_plus"}
# A row's level in the workbook is its first cell's indent.
LEVELS = {0: "district", 1: "county", 2: "subcounty", 3: "parish"}


def workbook_rows(table1: list[tuple[str, int, list[Any]]],
                  table3: list[tuple[str, int, list[Any]]]) -> list[dict[str, Any]]:
    """The workbook's districts, counties and sub-counties, each with its district
    and county, men, women, total and age groups, every sum checked: each
    unit's sexes make its total, its age groups make it (``age_groups``), and
    each county's sub-counties, each district's counties and each sub-county's
    parishes make it. Rows come as (label, indent, cells) per table, aligned."""
    head = next((i for i, (label, _, _) in enumerate(table3) if label.upper() == "PARISH"), None)
    if head is None:
        raise SystemExit("uganda_census: Table 3 has no PARISH heading row")
    columns = {" ".join(str(c or "").split()): i for i, c in enumerate(table3[head][2])}
    missing = [k for k in WORKBOOK_AGES if k not in columns]
    if missing:
        raise SystemExit(f"uganda_census: Table 3 has no column {missing}: {sorted(columns)}")
    out: list[dict[str, Any]] = []
    district = county = subcounty = None
    for (label, indent, cells), (label3, _, cells3) in zip(table1, table3):
        if indent not in LEVELS or len(cells) < 4 or count(cells[3]) is None \
                or label.upper() in ("DISTRICT", "COUNTY", "SUBCOUNTY", "PARISH"):
            continue
        # The tables' titles differ; their rows of figures must not.
        if label != label3:
            raise SystemExit(f"uganda_census: Tables 1 and 3 part at {label!r} / {label3!r}")
        male, female, total = (count(c) for c in cells[1:4])
        if None in (male, female) or male + female != total:
            raise SystemExit(f"uganda_census: workbook {label}: {male} men and {female} women "
                             f"against {total}")
        level = LEVELS[indent]
        if level == "district" and label.lower() == "national":
            # The country's row, a check on the districts'.
            if total != NATIONAL:
                raise SystemExit(f"uganda_census: the workbook's national row is {total:,}")
            continue
        ages = {key: count(cells3[columns[head_]]) for head_, key in WORKBOOK_AGES.items()}
        row = {"level": level, "name": label, "male": male, "female": female, "total": total,
               "ages": ages}
        if level == "district":
            district, county, subcounty = row, None, None
        elif level == "county":
            if district is None:
                raise SystemExit(f"uganda_census: workbook county {label} before any district")
            county, subcounty = row, None
            row["district"] = district["name"]
        elif level == "subcounty":
            if county is None:
                raise SystemExit(f"uganda_census: workbook sub-county {label} outside a county")
            subcounty = row
            row.update(district=district["name"], county=county["name"])
        else:
            if subcounty is None:
                raise SystemExit(f"uganda_census: workbook parish {label} outside a sub-county")
            subcounty.setdefault("_parishes", 0)
            subcounty["_parishes"] += total
            continue
        out.append(row)
    problems = []
    for parent_level, child_level, key in (("district", "county", "district"),
                                           ("county", "subcounty", "county")):
        for parent in (r for r in out if r["level"] == parent_level):
            kids = [r for r in out if r["level"] == child_level and r[key] == parent["name"]
                    and (parent_level == "district" or r["district"] == parent["district"])]
            made = sum(k["total"] for k in kids)
            if not kids and parent_level == "district":
                # Apaa, the ground Adjumani and Amuru both claim, is counted as a
                # district row of its own with nothing below it.
                log(f"  workbook: {parent['name']} ({parent['total']:,}) has no county rows")
                continue
            if made != parent["total"]:
                problems.append(f"{parent['name']}: its {child_level} rows make {made:,} of "
                                f"{parent['total']:,}")
    for row in out:
        if row["level"] == "subcounty" and row.pop("_parishes", row["total"]) != row["total"]:
            problems.append(f"{row['name']} ({row['county']}): its parishes do not make it")
        try:
            row["groups"] = age_groups(row["total"], row["ages"], row["name"])
        except ValueError as err:
            row["groups"] = None
            log(f"  workbook ages not read: {err}")
    if problems:
        raise SystemExit("uganda_census: workbook sums: " + "; ".join(problems[:20]))
    return out


def read_workbook() -> list[dict[str, Any]]:
    import io                                       # noqa: PLC0415

    import openpyxl                                 # noqa: PLC0415
    blob = http_get(WORKBOOK, binary=True, cache=False, timeout=900)
    log(f"  read {WORKBOOK}: {len(blob):,} bytes")
    # Not read-only: a row's level is its first cell's indent.
    book = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)

    def rows(title: str) -> list[tuple[str, int, list[Any]]]:
        out = []
        for r in book[title].iter_rows():
            first = r[0]
            indent = int((first.alignment.indent if first.alignment else 0) or 0)
            out.append((" ".join(str(first.value or "").split()), indent,
                        [c.value for c in r]))
        return out

    return workbook_rows(rows("Table1"), rows("Table3"))


def write_subcounty_table() -> int:
    rows = read_workbook()
    by_level = {lv: [r for r in rows if r["level"] == lv] for lv in ("district", "county",
                                                                     "subcounty")}
    made = sum(r["total"] for r in by_level["district"])
    log(f"  {len(by_level['district'])} districts making {made:,}, "
        f"{len(by_level['county'])} counties, {len(by_level['subcounty'])} sub-counties "
        f"({sum(1 for r in by_level['subcounty'] if r['groups'])} with their age groups)")
    if abs(made - NATIONAL) > NATIONAL * SLACK:
        raise SystemExit(f"uganda_census: the workbook's districts make {made:,}")
    write_json(PROCESSED / SUBCOUNTY_TABLE, [{k: v for k, v in r.items() if k != "groups"}
                                            for r in rows])
    return 0


def write_points() -> int:
    data = fetch_json(f"{API}/get_geospatial_data.php?level=county")
    features = (data.get("geojson") or data).get("features") or []
    out = []
    for feature in features:
        props = feature.get("properties") or {}
        pop = props.get("population_data") or {}
        points, area = sample(feature["geometry"], SAMPLES)
        out.append({"code": str(pop.get("code") or ""), "name": props.get("County"),
                    "district_code": str(props.get("DCode") or pop.get("district_code") or ""),
                    "region_code": str(props.get("RCode") or ""),
                    "male": count(pop.get("male_popn")), "female": count(pop.get("female_popn")),
                    "total": count(pop.get("total_popn")), "area_km2": area, "points": points})
    log(f"  {len(out)} counties, {sum(len(c['points']) for c in out):,} points, "
        f"{sum(c['total'] or 0 for c in out):,} people")
    write_json(PROCESSED / POINTS, out)
    return 0


OUT = "uganda_census.json"
YEAR = 2024
# The 2024 census's final count of everyone enumerated, and how far the
# dashboard's districts may fall from it (they make 45,895,961).
NATIONAL = 45_905_417
SLACK = 0.001
SITE = PROCESSED.parent.parent / "site" / "data"
SOURCE = ("Uganda Bureau of Statistics, National Population and Housing Census 2024, county "
          "statistics (population by sex and by age group), from the Bureau's census "
          "dissemination dashboard")
LICENCE = "Uganda Bureau of Statistics publication (reuse with attribution)"
# What the censuses publish on religion and ethnicity, said on every county and
# on the regions' ethnicity: the 2024 Final Report gives both for the country
# only (Volume 1, Tables 3.1 and 3.2), as the 2014 Main Report did (Tables A8
# and A9, by sex and residence), and the 2002 census religion by district,
# which uganda_2002.py writes for the regions and for the counties that were a
# district on their own.
REPORT = ("Uganda Bureau of Statistics, National Population and Housing Census 2024, Final "
          "Report, Volume 1 (Main), Tables 3.1 and 3.2")
REPORT_URL = ("https://www.ubos.org/wp-content/uploads/2024/12/"
              "National-Population-and-Housing-Census-2024-Final-Report-Volume-1-Main.pdf")
RELIGION = ("Uganda's 2024 and 2014 censuses published religion for the country as a whole "
            "only, and its 2002 census by district, not by county, so no count is given for "
            "this county.")
# The polygons of the ten counties that were a district on their own in 2002,
# whose religion uganda_2002.py writes, or why not: this file states none for
# them.
COUNTIES_OF_2002_DISTRICTS = frozenset({
    "Kampala", "Kiboga", "Buruli", "Bukooli", "Samia-Bugwe", "Bunya", "East Moyo", "Aringa",
    "Bufumbira", "Kinkiizi"})
# A sex ratio outside this band says it is the census's own figure.
ODD_RATIO = (850, 1150)
# The Kalangala islands' counties, which counted far more men than women in
# 2002 too (Table 3A: Bujumba 10,198 men and 7,137 women, Kyamuswa 10,651 and
# 6,780).
ISLANDS_2002 = {"BUJUMBA COUNTY": (10_198, 7_137), "KYAMUSWA COUNTY": (10_651, 6_780)}
ETHNICITY = ("Uganda's 2024 and 2014 censuses published ethnicity for the country as a whole "
             "only, so no count is given for this {unit}.")
# The Bureau's region codes -> the map's first-level polygons.
REGION_NAMES = {"1": "Central Region", "2": "Eastern Region", "3": "Northern Region",
                "4": "Western Region"}
AGE_KEYS = ("age_0_4", "age_0_17", "age_15_plus", "age_15_24", "age_18_30", "age_18_plus",
            "age_60_plus", "age_65_plus", "age_80_plus")


def age_groups(total: int, ages: dict[str, int], where: str) -> list[tuple[int, int | None, int]]:
    """The dashboard's overlapping age groups made disjoint, checked against the total."""
    a = {k: count(ages.get(k)) for k in AGE_KEYS}
    if any(v is None for v in a.values()):
        raise ValueError(f"{where}: an age group is missing: {a}")
    under15 = total - a["age_15_plus"]
    groups = [
        (0, 4, a["age_0_4"]),
        (5, 14, under15 - a["age_0_4"]),
        (15, 17, a["age_0_17"] - under15),
        (18, 24, a["age_15_24"] - (a["age_0_17"] - under15)),
        (25, 30, a["age_18_30"] - (a["age_15_24"] - (a["age_0_17"] - under15))),
        (31, 59, total - a["age_60_plus"] - a["age_0_17"] - a["age_18_30"]),
        (60, 64, a["age_60_plus"] - a["age_65_plus"]),
        (65, 79, a["age_65_plus"] - a["age_80_plus"]),
        (80, None, a["age_80_plus"]),
    ]
    if a["age_0_17"] + a["age_18_plus"] != total:
        raise ValueError(f"{where}: under-18s and adults make "
                         f"{a['age_0_17'] + a['age_18_plus']:,}, not {total:,}")
    if any(n < 0 for _, _, n in groups) or sum(n for _, _, n in groups) != total:
        raise ValueError(f"{where}: age groups {groups} do not make {total:,}")
    return groups


def layer(level: str) -> dict[str, dict[str, Any]]:
    """The dashboard's units at one level, from its map layer, which carries each unit's
    figures: {code: {code, name, district, region, male, female, total}}. A unit drawn
    twice (Rubaga division has a sliver of 0.1 km2 besides its outline) is one unit
    when its figures agree; a unit drawn without figures is logged and left out."""
    data = fetch_json(f"{API}/get_geospatial_data.php?level={level}")
    units: dict[str, dict[str, Any]] = {}
    for feature in (data.get("geojson") or data).get("features") or []:
        pop = (feature.get("properties") or {}).get("population_data") or {}
        code = str(pop.get("code") or "")
        male, female, total = (count(pop.get(k)) for k in ("male_popn", "female_popn",
                                                            "total_popn"))
        if not code or (male, female, total) == (None, None, None):
            log(f"  {level} drawn without figures: {pop.get('name') or feature['properties']}")
            continue
        if None in (male, female, total) or male + female != total:
            raise SystemExit(f"uganda_census: {pop.get('name')}: {male} men and {female} women "
                             f"against {total}")
        unit = {"code": code, "name": pop.get("name"),
                "district": str(pop.get("district_code") or code),
                "region": str(pop.get("region_code") or ""),
                "male": male, "female": female, "total": total}
        seen = units.get(code)
        if seen is not None:
            if [seen[k] for k in ("male", "female", "total")] != [male, female, total]:
                raise SystemExit(f"uganda_census: {level} {code} drawn twice with two counts")
            continue
        units[code] = unit
    return units


def add_ages(units: dict[str, dict[str, Any]], level: int) -> None:
    """Each unit's age groups from its profile (level 1 a district, 2 a county)."""
    for code, unit in sorted(units.items()):
        profile = fetch_json(f"{API}/get_profile_data.php?level={level}&location_code={code}"
                             "&format=detailed")
        tables = (profile.get("data") or {}).values()
        found = [t for t in tables if str(t.get("table_name")) == "Age Groups"]
        records = found[0].get("records") if found else []
        try:
            if len(records) != 1:
                raise ValueError(f"{unit['name']}: {len(records)} age records")
            unit["groups"] = age_groups(unit["total"], records[0], unit["name"])
        except ValueError as err:
            unit["groups"] = None
            log(f"  ages not read: {err}")


def read_units() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Every 2024 district, and every county, city division and municipality: codes,
    names, sexes, age groups. The districts must make the census's count, and each
    district's counties must make the district, but where a county of it is drawn
    without figures (Chekwi, in Nakapiripirit)."""
    districts = layer("district")
    counties = layer("county")
    made = sum(u["total"] for u in districts.values())
    # The dashboard's districts make 9,456 fewer people than the final count the
    # Bureau announced: a gap this small is logged, a larger one is a misread.
    if abs(made - NATIONAL) > NATIONAL * SLACK:
        raise SystemExit(f"uganda_census: the districts make {made:,}, not the census's "
                         f"{NATIONAL:,}")
    log(f"  the districts make {made:,} of the census's {NATIONAL:,}")
    for code, district in sorted(districts.items()):
        inside = [c for c in counties.values() if c["district"] == code]
        got = sum(c["total"] for c in inside)
        if got != district["total"]:
            log(f"  {district['name']}: its {len(inside)} counties with figures make {got:,} of "
                f"its {district['total']:,}")
    add_ages(districts, 1)
    add_ages(counties, 2)
    return list(districts.values()), list(counties.values())


def title(name: str) -> str:
    text = " ".join(str(name).split()).title()
    return text.replace(" - ", "-")


def fields(units: list[dict[str, Any]], note: str, source: str = SOURCE,
           page: str = PAGE) -> dict[str, Any]:
    male = sum(u["male"] for u in units)
    female = sum(u["female"] for u in units)
    total = sum(u["total"] for u in units)
    ratio = round(1000 * male / female)
    out: dict[str, Any] = {
        "population": measure(total, year=YEAR, source=source), "population_note": note,
        "sex_ratio": measure(ratio, unit="males_per_1000_females", year=YEAR, source=source),
        "sources": [{"field": "population/median_age/sex_ratio", "name": source, "url": page,
                     "year": YEAR, "license": LICENCE}]}
    if not ODD_RATIO[0] <= ratio <= ODD_RATIO[1]:
        out["sex_ratio_note"] = (
            f"The census's own figures, {male:,} men and {female:,} women, which its "
            "dashboard and its sub-county profile tables both give; the country counted 946 "
            "men per 1,000 women.")
        islands = [ISLANDS_2002[u["name"]] for u in units if u.get("name") in ISLANDS_2002]
        if islands:
            men, women = (sum(x) for x in zip(*islands))
            out["sex_ratio_note"] += (f" Kalangala's islands counted far more men than women "
                                      f"in 2002 too ({men:,} men and {women:,} women here).")
    if all(u.get("groups") for u in units):
        shape0 = [(a, b) for a, b, _ in units[0]["groups"]]
        groups = [(a, b, sum(u["groups"][i][2] for u in units)) for i, (a, b) in enumerate(shape0)]
        value = grouped_median(groups)
        if value is not None:
            out["median_age"] = measure(value, unit="years", year=YEAR, source=SOURCE)
            out["median_age_note"] = (
                "Interpolated within the age group that holds the middle person, from the 2024 "
                "census's counts in the overlapping age groups it publishes (0-4, 0-17, 15 "
                "and over, 15-24, 18-30, 18 and over, 60 and over, 65 and over, 80 and over), "
                "differenced into disjoint ones (0-4, 5-14, 15-17, 18-24, 25-30, 31-59, "
                "60-64, 65-79, 80 and over)"
                + (", added up over the units the population note names." if len(units) > 1
                   else "."))
    return out


def composition(unit: str, religion: bool = True) -> dict[str, Any]:
    """The religion and ethnicity a census does not publish for the unit, with the
    report that says so, cited for the notes: a county gets both, a region its
    ethnicity (its religion is the 2002 census's, in uganda_2002.json), and a
    county that was a district of its own in 2002 its ethnicity alone
    (uganda_2002.json gives its religion, or why not)."""
    out: dict[str, Any] = {"ethnicity": gap(NOT_AVAILABLE, ETHNICITY.format(unit=unit))}
    fields_ = ["ethnicity note"]
    if unit == "county" and religion:
        out["religion"] = gap(NOT_AVAILABLE, RELIGION)
        fields_.insert(0, "religion note")
    out["sources"] = [{"field": "/".join(fields_), "name": REPORT, "url": REPORT_URL,
                       "year": YEAR, "license": LICENCE}]
    return out


def with_composition(extra: dict[str, Any], unit: str, label: str = "") -> dict[str, Any]:
    stated = composition(unit, religion=label not in COUNTIES_OF_2002_DISTRICTS)
    return {**extra, **{k: v for k, v in stated.items() if k != "sources"},
            "sources": list(extra.get("sources") or []) + stated["sources"]}


def listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def named(members: list[dict[str, Any]], district_names: dict[str, str]) -> list[str]:
    """The units' names, each with its district where two share a name (two
    counties of 2024 are both called Bukoto)."""
    names = [title(u["name"]) for u in members]
    out = []
    for name, u in zip(names, members):
        district = district_names.get(u.get("district", ""))
        if names.count(name) > 1 and district:
            name = f"{name} ({district} District)"
        out.append(name)
    return out


def build(districts: list[dict[str, Any]], units: list[dict[str, Any]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          subcounties: list[dict[str, Any]] | None = None
          ) -> tuple[list[dict[str, Any]], list[str]]:
    from .uganda_counties import PLACED, SETTLED, STRADDLING  # noqa: PLC0415
    by_code = {u["code"]: u for u in units}
    district_names = {u["code"]: title(u["name"]) for u in districts}
    rows = {(r["district"], r["county"], r["name"]): r for r in (subcounties or [])
            if r["level"] == "subcounty"}
    records, report = [], []
    regions = {s["name"].strip(): s for s in admin1}
    for code, label in REGION_NAMES.items():
        members = [u for u in districts if u["region"] == code]
        shape = regions.get(label)
        if not members or shape is None:
            raise SystemExit(f"uganda_census: region {code} ({label}): {len(members)} districts, "
                             f"polygon {bool(shape)}")
        records.append(record(
            f"UGA-2024-{shape['id']}", shape["name"].strip(), level="admin1", parent="UGA",
            country="UGA", match_by="shape_id", shape_id=shape["id"],
            **with_composition(fields(members, f"The 2024 census's counts for the region's "
                                               f"{len(members)} districts, added up."),
                               "region")))
    labels = {s["id"]: s["name"].strip() for s in admin2}
    used: dict[str, str] = {}
    for sid, codes in PLACED.items():
        missing = [c for c in codes if c not in by_code]
        if missing or sid not in labels:
            report.append(f"{labels.get(sid, sid)}: units {missing} not in the census; not "
                          "written")
            continue
        for c in codes:
            if c in used:
                raise SystemExit(f"uganda_census: {c} placed in both {used[c]} and {sid}")
            used[c] = sid
        members = [by_code[c] for c in codes]
        names = named(members, district_names)
        if len(members) == 1:
            own = labels[sid].lower() in members[0]["name"].lower()
            note = (f"The 2024 census's count for {names[0]}"
                    + ("." if own else ", which is the county drawn here."))
        else:
            note = ("The 2024 census's counts for " + ", ".join(names[:-1]) + " and " + names[-1]
                    + ", added up: the county as drawn here is these units of 2024 together.")
        records.append(record(f"UGA-2024-{sid}", labels[sid], level="admin2", parent="UGA",
                              country="UGA", match_by="shape_id", shape_id=sid,
                              **with_composition(fields(members, note), "county",
                                                 labels[sid])))
    for sid, entry in SETTLED.items():
        missing = [c for c in entry["counties"] if c not in by_code]
        parts = [rows.get(tuple(k)) for k in entry["subcounties"]]
        if missing or None in parts or sid not in labels:
            report.append(f"{labels.get(sid, sid)}: units {missing} or sub-counties "
                          f"{[k for k, p in zip(entry['subcounties'], parts) if p is None]} "
                          "not in the census; not written")
            continue
        for c in entry["counties"]:
            if c in used:
                raise SystemExit(f"uganda_census: {c} placed in both {used[c]} and {sid}")
            used[c] = sid
        whole = [by_code[c] for c in entry["counties"]]
        groups = [{**p, "groups": age_groups(p["total"], p["ages"], p["name"])} for p in parts]
        by_county: dict[str, list[str]] = {}
        for p in parts:
            by_county.setdefault(title(p["county"]), []).append(title(p["name"]))
        pieces = named(whole, district_names) + [
            f"{listed(subs)}, {'a sub-county' if len(subs) == 1 else 'sub-counties'} of "
            f"{county}" for county, subs in by_county.items()]
        note = ("The 2024 census's counts for " + listed(pieces) + ", added up: the county as "
                "drawn here is these units of 2024 together.")
        extra = fields(whole + groups, note)
        if parts:
            extra["sources"].append({"field": "population/median_age/sex_ratio",
                                     "name": WORKBOOK_SOURCE, "url": WORKBOOK_PAGE,
                                     "year": YEAR, "license": LICENCE})
        records.append(record(f"UGA-2024-{sid}", labels[sid], level="admin2", parent="UGA",
                              country="UGA", match_by="shape_id", shape_id=sid,
                              **with_composition(extra, "county", labels[sid])))
    for sid, crossing in STRADDLING.items():
        if sid not in labels:
            continue
        if crossing:
            names = [title(n) for n in crossing]
            why = ("The 2024 census was published for the counties, cities and municipalities "
                   "of 2024 and for their sub-counties, and the county as drawn here is a whole "
                   f"number of neither: {listed(names)} "
                   f"{'crosses' if len(names) == 1 else 'cross'} its line, and "
                   f"{'its' if len(names) == 1 else 'their'} sub-counties cannot all be shown "
                   "to lie on one side of it or the other (the census publishes no sub-county "
                   "outlines, and OCHA's of 2020 lack those made since or cross the line "
                   "too). No count is published for the county as drawn.")
        else:
            why = ("The 2024 census counts this ground within a county that is drawn mostly "
                   "outside it; no count is published for this part alone.")
        stated = gap(NOT_AVAILABLE, why)
        records.append(record(f"UGA-2024-{sid}", labels[sid], level="admin2", parent="UGA",
                              country="UGA", match_by="shape_id", shape_id=sid,
                              **with_composition(
                                  {"population": stated, "median_age": stated,
                                   "sex_ratio": stated,
                                   "sources": [{"field": "population note/median_age note/"
                                                         "sex_ratio note",
                                                "name": SOURCE, "url": PAGE, "year": YEAR,
                                                "license": LICENCE}]}, "county",
                                  labels[sid])))
    spare = sorted(u["name"] for u in units if u["code"] not in used)
    report.append(f"2024 units on no written polygon ({len(spare)}): {spare}")
    return records, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--points", action="store_true",
                    help="write points sampled over every 2024 county, for the crosswalk")
    ap.add_argument("--subcounty-points", action="store_true",
                    help="write points sampled over OCHA's sub-county outlines (cod-ab-uga)")
    ap.add_argument("--subcounty-table", action="store_true",
                    help="write the 2024 sub-county profile tables' figures")
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    args = ap.parse_args()
    if args.points:
        return write_points()
    if args.subcounty_points:
        return write_cod_points("cod-ab-uga", 4, SUBCOUNTY_POINTS, 30)
    if args.subcounty_table:
        return write_subcounty_table()
    districts, units = read_units()
    log(f"  {len(districts)} districts making {sum(u['total'] for u in districts):,}, "
        f"{sum(1 for u in districts if u.get('groups'))} with their age groups; {len(units)} "
        f"counties, cities and municipalities with figures, making "
        f"{sum(u['total'] for u in units):,}, {sum(1 for u in units if u.get('groups'))} with "
        "their age groups")
    admin1 = json.loads((SITE / "admin1" / "UGA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "UGA.units.json").read_text())
    subcounties = json.loads((PROCESSED / SUBCOUNTY_TABLE).read_text())
    records, report = build(districts, units, admin1, admin2, subcounties)
    for line in report:
        log("  " + line)
    for r in records:
        pop = r["population"]
        log(f"  {r['level']} {r['name']}: "
            + (f"{pop['value']:,}, median {(r.get('median_age') or {}).get('value')}, "
               f"sex ratio {r['sex_ratio']['value']}" if "value" in pop else "stated"))
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
