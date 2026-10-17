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
and ``uganda_counties`` records which units each polygon is the union of
(PLACED) and, for the others, which 2024 units cross the polygon's line
(STRADDLING). A polygon in PLACED takes the sum of its units' figures; every
other one says why it has none. (OCHA's COD-PS table for Uganda is by
district, and its 54 figures that stood on county polygons of the same names
were districts', Mityana's with Busujju in it and Serere's with Kasilo.)

**What is written.** For each region and each placed county: the population
and men per 1,000 women, and the median age, interpolated within the age
group that holds the middle person from the dashboard's groups made disjoint
(0-4, 5-14, 15-17, 18-24, 25-30, 31-59, 60-64, 65-79, 80 and over). The
regions are the sums of their districts: the dashboard draws one county,
Chekwi in Nakapiripirit, without figures, so its counties make 45,826,553
people, while its districts make 45,895,961 of the 45,905,417 the Bureau
announced as the final count.

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


def fields(units: list[dict[str, Any]], note: str) -> dict[str, Any]:
    male = sum(u["male"] for u in units)
    female = sum(u["female"] for u in units)
    total = sum(u["total"] for u in units)
    out: dict[str, Any] = {
        "population": measure(total, year=YEAR, source=SOURCE), "population_note": note,
        "sex_ratio": measure(round(1000 * male / female), unit="males_per_1000_females",
                             year=YEAR, source=SOURCE),
        "sources": [{"field": "population/median_age/sex_ratio", "name": SOURCE, "url": PAGE,
                     "year": YEAR, "license": LICENCE}]}
    if all(u.get("groups") for u in units):
        shape0 = [(a, b) for a, b, _ in units[0]["groups"]]
        groups = [(a, b, sum(u["groups"][i][2] for u in units)) for i, (a, b) in enumerate(shape0)]
        value = grouped_median(groups)
        if value is not None:
            out["median_age"] = measure(value, unit="years", year=YEAR, source=SOURCE)
            out["median_age_note"] = (
                "Interpolated within the age group that holds the middle person, from the 2024 "
                "census's counts in the age groups it publishes for each district and county "
                "(0-4, 5-14, 15-17, 18-24, 25-30, 31-59, 60-64, 65-79, 80 and over)"
                + (", added up over the units the population note names." if len(units) > 1
                   else "."))
    return out


def build(districts: list[dict[str, Any]], units: list[dict[str, Any]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
    from .uganda_counties import PLACED, STRADDLING  # noqa: PLC0415
    by_code = {u["code"]: u for u in units}
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
            **fields(members, f"The 2024 census's counts for the region's {len(members)} "
                              "districts, added up.")))
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
        names = [title(u["name"]) for u in members]
        if len(members) == 1:
            own = labels[sid].lower() in members[0]["name"].lower()
            note = (f"The 2024 census's count for {names[0]}"
                    + ("." if own else ", the area this polygon draws."))
        else:
            note = ("The 2024 census's counts for " + ", ".join(names[:-1]) + " and " + names[-1]
                    + ", added up: the county as drawn here is these units of 2024 together.")
        records.append(record(f"UGA-2024-{sid}", labels[sid], level="admin2", parent="UGA",
                              country="UGA", match_by="shape_id", shape_id=sid,
                              **fields(members, note)))
    for sid, crossing in STRADDLING.items():
        if sid not in labels:
            continue
        if crossing:
            names = [title(n) for n in crossing]
            listed = (names[0] if len(names) == 1 else
                      ", ".join(names[:-1]) + " and " + names[-1])
            why = ("The 2024 census was published for the counties, cities and municipalities "
                   "of 2024, and the county as drawn here is not a whole number of them: "
                   f"{listed} {'crosses' if len(names) == 1 else 'cross'} its line. No count "
                   "is published for the county as drawn.")
        else:
            why = ("The 2024 census counts this ground within a county that is drawn mostly "
                   "outside it; no count is published for this part alone.")
        stated = gap(NOT_AVAILABLE, why)
        records.append(record(f"UGA-2024-{sid}", labels[sid], level="admin2", parent="UGA",
                              country="UGA", match_by="shape_id", shape_id=sid,
                              population=stated, median_age=stated, sex_ratio=stated,
                              sources=[{"field": "population/median_age/sex_ratio",
                                        "name": SOURCE, "url": PAGE, "year": YEAR,
                                        "license": LICENCE}]))
    spare = sorted(u["name"] for u in units if u["code"] not in used)
    report.append(f"2024 units on no written polygon ({len(spare)}): {spare}")
    return records, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--points", action="store_true",
                    help="write points sampled over every 2024 county, for the crosswalk")
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    args = ap.parse_args()
    if args.points:
        return write_points()
    districts, units = read_units()
    log(f"  {len(districts)} districts making {sum(u['total'] for u in districts):,}, "
        f"{sum(1 for u in districts if u.get('groups'))} with their age groups; {len(units)} "
        f"counties, cities and municipalities with figures, making "
        f"{sum(u['total'] for u in units):,}, {sum(1 for u in units if u.get('groups'))} with "
        "their age groups")
    admin1 = json.loads((SITE / "admin1" / "UGA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "UGA.units.json").read_text())
    records, report = build(districts, units, admin1, admin2)
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
