#!/usr/bin/env python3
"""South Africa -- Census 2022 by district and metropolitan municipality.

Statistics South Africa's census portal (census.statssa.gov.za) is a script
that draws every figure it shows from a public JSON service, and the same
service answers a plain request: the provinces, each province's district and
metropolitan municipalities, and for each of those the census's counts by sex,
by population group and by five-year age group and sex. The province totals in
south_africa.py come from the census's statistical release; these are the same
census's counts one level down.

Written for each of the 52 districts and metros: population and sex ratio
(males per 100 females); population group as counts (the five groups the
census asks, on the ethnicity field); median age, interpolated within the
five-year age group that holds the middle person. For each of the nine
provinces: the median age the same way (the release prints it only as a
chart, see south_africa.py). Religion and language say why they are empty:
the census asked both and Statistics South Africa publishes them by province
only -- the statistical release's Tables 2.9 and 2.10, and the provincial
profiles (Report 03-01-7x), whose religion table is the province's and which
print no language table -- and the service carries neither.

**Which group is which.** The service's rows name their population group and
age group by number only (the descriptions come back null). The numbering is
the census's own order, and it is checked rather than assumed: groups 1 to 3
must make the share of children under 15 and groups 14 to 18 the share aged 65
and over that the service's own district summary (DsMains) prints, to a tenth
of a percent; the Western Cape's largest group must be number 2 (Coloured) and
KwaZulu-Natal's share of number 3 (Indian/Asian) the largest of any province.

**The ground.** Census 2022 counts the districts as they have stood since the
boundary changes of 2016. The boundary file's districts are those too, though
some keep older names (``ALIASES``: Cacadu for Sarah Baartman, Eden for Garden
Route, Sisonke for Harry Gwala, Uthungulu for King Cetshwayo): its Mangaung,
about 9,900 km², includes Naledi, merged into the metro in 2016, and its
Alfred Nzo, about 10,800 km², includes Mbizana and Ntabankulu, moved to it in
2011.

**Checks before anything is written.** Each district's population is the
service's own total for it; its counts by sex, which give the ratio, fall
short of that total by no more than half a percent (the City of Cape Town's
by 2,533 of 4,772,846), and its share of men is the one the service prints.
Each province's districts make the province's total from the same service,
to a hundredth of a percent (Limpopo's five make 6,572,665 against 6,572,721:
each count is weighted and rounded on its own); the provinces make the
census's 62,027,503, to the same rounding. A district's population groups and
age groups make its total less the people whose group or age was not given,
never more and never short by more than ``UNSTATED`` of it; each province's
districts make its groups and ages to the same rounding. Districts are matched
to the boundary file's within their province, by name, and every polygon must
get exactly one district and every district one polygon.

Usage:
    python -m scripts.fetch_census.south_africa_districts
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_json, log, measure, record, write_json

API = "https://disseminationapi-a2f6fff8f7a3f3ff.z01.azurefd.net/api/"
PAGE = "https://census.statssa.gov.za/"
SOURCE = "Statistics South Africa, Census 2022, census dissemination service: population by sex"
GROUP_SOURCE = ("Statistics South Africa, Census 2022, census dissemination service: "
                "population by population group")
AGE_SOURCE = ("Statistics South Africa, Census 2022, census dissemination service: "
              "population by five-year age group and sex")
RELEASE = ("https://census.statssa.gov.za/assets/documents/2022/"
           "P03014_Census_2022_Statistical_Release.pdf")
LICENCE = "Statistics South Africa, reuse with acknowledgement of the source"
YEAR = 2022
CENSUS = 1                           # the service's time series: 1 is Census 2022
PROVINCE, DISTRICT = 2, 5            # the service's geography levels
NATIONAL = 62_027_503
SLACK = 3                            # people a separately rounded count may miss by
SEX_SHORT = 0.005                    # how far short of the total the counts by sex may fall
# How far a province's districts may miss its total: each count is weighted and
# rounded on its own (Limpopo's five districts make 6,572,665 against 6,572,721).
ROUNDING = 0.0001
# How far a district's population groups or age groups may fall short of its
# total: the people whose group or age the census did not record.
UNSTATED = 0.01
OUT = "south_africa_districts.json"
SITE = PROCESSED.parent.parent / "site" / "data"

# The census's five population groups, in the service's numbering (checked in
# check_numbering), under the release's own names (south_africa.GROUPS).
GROUPS = {1: "Black African", 2: "Coloured", 3: "Indian/Asian", 4: "White", 5: "Other"}
# The service's eighteen age groups: 0-4, 5-9, ... 80-84 and 85 and over.
AGE_GROUPS = {i: (5 * (i - 1), 5 if i < 18 else None) for i in range(1, 19)}

RELIGION_NOTE = (
    "Census 2022 asked religious affiliation, and Statistics South Africa publishes the "
    "answers by province only (Census 2022 Statistical Release P0301.4, Table 2.10, and "
    "each province's Census 2022 provincial profile), so no figure is published for this "
    "district.")
LANGUAGE_NOTE = (
    "Census 2022 asked the language spoken most often in the household, and Statistics "
    "South Africa publishes the answers by province only (Census 2022 Statistical Release "
    "P0301.4, Table 2.9), so no figure is published for this district.")

# The boundary file's reduced name -> the census's, where the district has
# been renamed since the boundary file was drawn.
ALIASES = {"cacadu": "sarahbaartman", "eden": "gardenroute", "sisonke": "harrygwala",
           "uthungulu": "kingcetshwayo"}


def key(name: str) -> str:
    """A name reduced to its letters, without 'District/Metropolitan Municipality'."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"\b(?:district|metropolitan|local)?\s*municipality\b", " ", s)
    return "".join(c for c in s if "a" <= c <= "z")


def get(path: str) -> Any:
    """One answer of the service. Its SHA-256 goes to the log, so the run's
    record says what the service answered."""
    for wait in (5, 20, 60, None):
        try:
            got = http_json(API + path, cache=False, timeout=120)
            body = json.dumps(got, sort_keys=True, ensure_ascii=False).encode("utf-8")
            log(f"    read {path}: answer sha256 {hashlib.sha256(body).hexdigest()}")
            return got
        except Exception as exc:                    # noqa: BLE001 -- network, 5xx
            if wait is None:
                raise
            log(f"    {path}: {exc.__class__.__name__}; again in {wait} s")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def indicators(level: int, value: Any) -> dict[str, float]:
    """{'Total population': n, 'Male': %, ...} for one area."""
    rows = get(f"KeyIndicators/listKeyIndicators/{CENSUS}/{level}/{value}")
    return {r["rankingDesc"]: r["valueCurrent"] for r in rows}


def by_sex(value: str) -> tuple[int, int]:
    """(men, women) counted in one district."""
    rows = get(f"DsSexes/listDsByParams/{CENSUS}/{DISTRICT}/{value}")
    got = {r["sexId"]: r["counts"] for r in rows if r.get("timeSeriesId") == CENSUS}
    if set(got) != {1, 2}:
        raise SystemExit(f"south_africa_districts: {value}: counts by sex {rows!r}")
    return int(got[1]), int(got[2])


def by_group(level: int, value: Any) -> dict[int, int]:
    """{population group number: people} in one area."""
    rows = get(f"DsPopulationGroups/listDsByParams/{CENSUS}/{level}/{value}")
    got = {int(r["populationGroupId"]): int(r["counts"] or 0) for r in rows
           if r.get("timeSeriesId") == CENSUS}
    if set(got) != set(GROUPS):
        raise SystemExit(f"south_africa_districts: {value}: population groups {sorted(got)}")
    return got


def by_age(level: int, value: Any) -> dict[int, tuple[int, int]]:
    """{age group number: (men, women)} in one area."""
    rows = get(f"DsAgeGroups/listDsByParams/{CENSUS}/{level}/{value}")
    got = {int(r["ageGroupId"]): (int(r["countsMales"] or 0), int(r["countsFemales"] or 0))
           for r in rows if r.get("timeSeriesId") == CENSUS}
    if set(got) != set(AGE_GROUPS):
        raise SystemExit(f"south_africa_districts: {value}: age groups {sorted(got)}")
    return got


def summary(level: int, value: Any) -> dict[str, Any]:
    """The service's own summary of an area (DsMains): its shares of children
    and of the old, against which the age groups' numbering is checked."""
    rows = get(f"DsMains/listDsByParams/{CENSUS}/{level}/{value}")
    # A list of one row for a district, the row itself for a province.
    if isinstance(rows, dict):
        return rows
    return rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}


def median_of(ages: dict[int, tuple[int, int]]) -> float | None:
    """The median age, interpolated within the five-year group that holds it."""
    people = [(AGE_GROUPS[i][0], AGE_GROUPS[i][1], sum(ages[i])) for i in sorted(ages)]
    total = sum(n for _, _, n in people)
    if total <= 0:
        return None
    half, before = total / 2, 0.0
    for low, width, n in people:
        if n > 0 and before + n >= half:
            if width is None:
                raise SystemExit("south_africa_districts: the median falls in the open "
                                 "top age group")
            return round(low + width * (half - before) / n, 1)
        before += n
    return None


def check_parts(name: str, total: int, parts: int, what: str) -> None:
    """A district's groups or ages make its total less the unstated, never more."""
    if parts > total + SLACK or parts < total * (1 - UNSTATED):
        raise SystemExit(f"south_africa_districts: {name}: its {what} make {parts:,} "
                         f"against a total of {total:,}")


def check_numbering(name: str, ages: dict[int, tuple[int, int]], main: dict[str, Any]) -> None:
    """Groups 1-3 are the children under 15 and 14-18 the people of 65 and over,
    as the service's own summary of the same area says."""
    total = sum(sum(v) for v in ages.values())
    if not total or not main:
        return
    young = 100 * sum(sum(ages[i]) for i in (1, 2, 3)) / total
    old = 100 * sum(sum(ages[i]) for i in range(14, 19)) / total
    for share, field in ((young, "ageYoungPeople0to14Percentage"),
                         (old, "ageElderly65PlusPercentage")):
        printed = main.get(field)
        if isinstance(printed, (int, float)) and abs(share - printed) > 0.15:
            raise SystemExit(f"south_africa_districts: {name}: the age groups give "
                             f"{share:.1f}% where the service prints {field} {printed}")


def check_groups(provinces: dict[str, dict[str, Any]]) -> None:
    """Group 2 is the Western Cape's largest and group 3 is KwaZulu-Natal's
    largest share of any province: the numbering is the census's."""
    shares = {name: {g: n / sum(p["groups"].values()) for g, n in p["groups"].items()}
              for name, p in provinces.items() if p.get("groups")}
    if not shares:
        return
    west = shares.get("Western Cape")
    if west and max(west, key=west.get) != 2:
        raise SystemExit("south_africa_districts: the Western Cape's largest population "
                         "group is not number 2 (Coloured)")
    if "KwaZulu-Natal" in shares and \
            max(shares, key=lambda p: shares[p][3]) != "KwaZulu-Natal":
        raise SystemExit("south_africa_districts: KwaZulu-Natal's Indian/Asian share is not "
                         "the largest of any province")


def read() -> dict[str, Any]:
    """{"provinces": {name: {"id", "total", "groups", "ages"}}, "districts":
    [{code, name, province, men, women, total, groups, ages}]}, checked."""
    provinces: dict[str, dict[str, Any]] = {}
    districts: list[dict[str, Any]] = []
    for p in get("Provinces/getAll/"):
        name = " ".join(str(p["provinceDesc"]).split())
        total = indicators(PROVINCE, p["provinceId"]).get("Total population")
        groups = by_group(PROVINCE, p["provinceId"])
        ages = by_age(PROVINCE, p["provinceId"])
        check_numbering(name, ages, summary(PROVINCE, p["provinceId"]))
        provinces[name] = {"id": p["provinceId"], "total": total, "groups": groups,
                           "ages": ages}
        for d in get(f"Districts/listByProvince/{p['provinceId']}"):
            code = d["districtMdbc"]
            label = " ".join(str(d["districtName"]).split())
            men, women = by_sex(code)
            own = indicators(DISTRICT, code)
            total = own.get("Total population")
            # The service's counts by sex fall a little short of its totals --
            # Alfred Nzo's by one person, the City of Cape Town's by 2,533 of
            # 4,772,846 -- so the population is the service's total and the
            # counts by sex give only the ratio. A gap past SEX_SHORT is a
            # misreading, not that.
            if (not isinstance(total, (int, float)) or men + women > total + SLACK
                    or men + women < total * (1 - SEX_SHORT)):
                raise SystemExit(f"south_africa_districts: {label}: {men:,} men and "
                                 f"{women:,} women against a total of {total}")
            if men + women != total:
                log(f"  {label}: men and women {men + women:,}, total {total:,}")
            if abs(100 * men / (men + women) - float(own.get("Male") or 0)) > 0.06:
                raise SystemExit(f"south_africa_districts: {label}: the first count "
                                 f"by sex is not the men's ({own.get('Male')}% men)")
            groups = by_group(DISTRICT, code)
            ages = by_age(DISTRICT, code)
            check_parts(label, int(total), sum(groups.values()), "population groups")
            check_parts(label, int(total), sum(sum(v) for v in ages.values()), "age groups")
            check_numbering(label, ages, summary(DISTRICT, code))
            districts.append({"code": code, "name": label, "province": name, "men": men,
                              "women": women, "total": int(total), "groups": groups,
                              "ages": ages})
            time.sleep(0.2)
    check(provinces, districts)
    check_groups(provinces)
    return {"provinces": provinces, "districts": districts}


def check(provinces: dict[str, dict[str, Any]], districts: list[dict[str, Any]]) -> None:
    """The provinces make the country and each province's districts make it,
    to the rounding of separately rounded counts (``SLACK`` people a district,
    or ``ROUNDING`` of the total, whichever is more) -- its head count, and
    where both are given its population groups and age groups too."""
    national = sum(p["total"] or 0 for p in provinces.values())
    if abs(national - NATIONAL) > ROUNDING * NATIONAL:
        raise SystemExit(f"south_africa_districts: the provinces make {national:,}, "
                         f"not {NATIONAL:,}")
    for name, p in provinces.items():
        mine = [d for d in districts if d["province"] == name]
        made = sum(d["total"] for d in mine)
        allowed = max(SLACK * len(mine), ROUNDING * p["total"])
        if not mine or abs(made - p["total"]) > allowed:
            raise SystemExit(f"south_africa_districts: {name}'s districts make {made:,}, "
                             f"not {p['total']:,}")
        if made != p["total"]:
            log(f"  {name}: its {len(mine)} districts make {made:,} against {p['total']:,}")
        if p.get("groups") and all(d.get("groups") for d in mine):
            for g in GROUPS:
                got = sum(d["groups"][g] for d in mine)
                if abs(got - p["groups"][g]) > allowed:
                    raise SystemExit(f"south_africa_districts: {name}'s districts make "
                                     f"{got:,} {GROUPS[g]}, not {p['groups'][g]:,}")
        if p.get("ages") and all(d.get("ages") for d in mine):
            for a in AGE_GROUPS:
                got = sum(sum(d["ages"][a]) for d in mine)
                if abs(got - sum(p["ages"][a])) > allowed:
                    raise SystemExit(f"south_africa_districts: {name}'s districts make "
                                     f"{got:,} in age group {a}, not {sum(p['ages'][a]):,}")


def bind(districts: list[dict[str, Any]], admin1: list[dict[str, Any]],
         admin2: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{polygon id: district}: by name within the province; a name that is a
    beginning of the other's ("Bojanala", "Bojanala Platinum") joins when it
    is the only one that does."""
    province_of = {s["id"]: s["name"] for s in admin1}
    pool: dict[str, list[dict[str, Any]]] = {}
    for d in districts:
        pool.setdefault(d["province"], []).append(d)
    if sorted(pool) != sorted(province_of.values()):
        raise SystemExit(f"south_africa_districts: provinces {sorted(pool)} against the map's "
                         f"{sorted(province_of.values())}")
    bound: dict[str, dict[str, Any]] = {}
    taken: set[str] = set()
    left = []
    for shape in admin2:
        here = [d for d in pool[province_of[shape["parent"]]] if d["code"] not in taken]
        k = key(shape["name"])
        k = ALIASES.get(k, k)
        hits = [d for d in here if key(d["name"]) == k] or \
            [d for d in here if key(d["name"]).startswith(k) or k.startswith(key(d["name"]))]
        if len(hits) != 1:
            left.append(f"{shape['name']!r}: {[d['name'] for d in hits]}")
            continue
        bound[shape["id"]] = hits[0]
        taken.add(hits[0]["code"])
    spare = [d["name"] for d in districts if d["code"] not in taken]
    if left or spare:
        raise SystemExit(f"south_africa_districts: polygons not bound {left}; districts on no "
                         f"polygon {spare}")
    return bound


def group_fields(d: dict[str, Any]) -> dict[str, Any]:
    """Population group as counts, and what the shares are of."""
    counts = {GROUPS[g]: n for g, n in d["groups"].items()}
    base = sum(counts.values())
    rows = [{"group": g, "pct": round(100 * n / base, 1), "count": n} for g, n in counts.items()]
    rows.sort(key=lambda r: (-r["pct"], r["group"]))
    unstated = d["total"] - base
    note = (f"Census 2022 population group, as counts: the {base:,} people whose group the "
            f"census recorded")
    note += (f", of the {d['total']:,} it counts here." if unstated > 0 else ".")
    return {"ethnicity": rows, "ethnicity_year": YEAR, "ethnicity_note": note}


def age_fields(ages: dict[int, tuple[int, int]]) -> dict[str, Any]:
    median = median_of(ages)
    if median is None:
        return {}
    return {"median_age": measure(median, unit="years", year=YEAR, source=AGE_SOURCE),
            "median_age_note": ("Interpolated within the five-year age group that holds the "
                                "middle person, from Census 2022's counts by age group and "
                                "sex.")}


def sources_of(code: str, level: int, fields: str) -> list[dict[str, Any]]:
    return [{"field": fields, "name": GROUP_SOURCE if "ethnicity" in fields else AGE_SOURCE,
             "url": API + (f"DsPopulationGroups/listDsByParams/{CENSUS}/{level}/{code}"
                           if "ethnicity" in fields else
                           f"DsAgeGroups/listDsByParams/{CENSUS}/{level}/{code}"),
             "page": PAGE, "license": LICENCE, "year": YEAR}]


def records_of(table: dict[str, Any], admin1: list[dict[str, Any]],
               admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bound = bind(table["districts"], admin1, admin2)
    out = []
    for shape in admin2:
        d = bound[shape["id"]]
        note = f"Census 2022's count for {d['name']}"
        if key(d["name"]) != key(shape["name"]):
            note += f" (the boundary file's {shape['name']!r})"
        note += "."
        extra: dict[str, Any] = {}
        sources = [{"field": "population/sex_ratio", "name": SOURCE,
                    "url": API + f"DsSexes/listDsByParams/{CENSUS}/{DISTRICT}/{d['code']}",
                    "page": PAGE, "license": LICENCE, "year": YEAR}]
        if d.get("groups"):
            extra.update(group_fields(d))
            sources += sources_of(d["code"], DISTRICT, "ethnicity")
        if d.get("ages"):
            extra.update(age_fields(d["ages"]))
            sources += sources_of(d["code"], DISTRICT, "median_age")
        if d.get("groups") or d.get("ages"):
            extra["religion"] = gap(NOT_AVAILABLE, RELIGION_NOTE)
            extra["language"] = gap(NOT_AVAILABLE, LANGUAGE_NOTE)
            sources.append({"field": "religion/language note",
                            "name": "Statistics South Africa, Census 2022 Statistical Release "
                                    "P0301.4", "url": RELEASE, "license": LICENCE,
                            "year": YEAR})
        out.append(record(
            f"ZAF-2022-{d['code']}", shape["name"], level="admin2", parent="ZAF", country="ZAF",
            match_by="shape_id", shape_id=shape["id"],
            population=measure(d["total"], year=YEAR, source=SOURCE),
            population_note=note,
            sex_ratio=measure(round(100 * d["men"] / d["women"], 1), unit="males_per_100_females",
                              year=YEAR, source=SOURCE),
            sources=sources, **extra))
    by_name = {key(s["name"]): s for s in admin1}
    for name, p in sorted((table.get("provinces") or {}).items()):
        shape = by_name.get(key(name))
        if shape is None or not p.get("ages"):
            continue
        fields = age_fields(p["ages"])
        if not fields:
            continue
        out.append(record(
            f"ZAF-2022-province-{p['id']}", shape["name"], level="admin1", parent="ZAF",
            country="ZAF", match_by="shape_id", shape_id=shape["id"],
            sources=sources_of(str(p["id"]), PROVINCE, "median_age"), **fields))
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    table = read()
    log(f"  {len(table['provinces'])} provinces and {len(table['districts'])} districts, "
        f"making {sum(p['total'] for p in table['provinces'].values()):,}")
    admin1 = json.loads((SITE / "admin1" / "ZAF.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "ZAF.units.json").read_text())
    records = records_of(table, admin1, admin2)
    for r in records:
        if r["level"] == "admin1":
            log(f"  {r['name']}: median age {r['median_age']['value']}")
            continue
        groups = ", ".join(f"{g['group']} {g['pct']}" for g in r.get("ethnicity") or [])
        median = (r.get("median_age") or {}).get("value")
        log(f"  {r['name']}: {r['population']['value']:,}, {r['sex_ratio']['value']} men per "
            f"100 women, median age {median}; {groups}; {r['population_note']}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
