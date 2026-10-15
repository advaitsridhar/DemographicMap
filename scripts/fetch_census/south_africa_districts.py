#!/usr/bin/env python3
"""South Africa -- Census 2022 by district and metropolitan municipality.

Statistics South Africa's census portal (census.statssa.gov.za) is a script
that draws every figure it shows from a public JSON service, and the same
service answers a plain request: the provinces, each province's district and
metropolitan municipalities, and for each of those the census's counts by sex.
The province totals in south_africa.py come from the census's statistical
release; these are the same census's counts one level down.

Written for each of the 52 districts and metros: population (the men and women
counted, added together) and sex ratio (males per 100 females), Census 2022.

**The ground.** Census 2022 counts the districts as they have stood since the
boundary changes of 2016. The boundary file's districts are those too, though
some keep older names (``ALIASES``: Cacadu for Sarah Baartman, Eden for Garden
Route, Sisonke for Harry Gwala, Uthungulu for King Cetshwayo): its Mangaung,
about 9,900 km², includes Naledi, merged into the metro in 2016, and its
Alfred Nzo, about 10,800 km², includes Mbizana and Ntabankulu, moved to it in
2011.

**Checks before anything is written.** Each district's men and women make the
service's own total for it, and its share of men is the one the service
prints; each province's districts make the province's total from the same
service; the provinces make the census's 62,027,503. Districts are matched to
the boundary file's within their province, by name, and every polygon must
get exactly one district and every district one polygon.

Usage:
    python -m scripts.fetch_census.south_africa_districts
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from typing import Any

from ._shared import PROCESSED, http_json, log, measure, record, write_json

API = "https://disseminationapi-a2f6fff8f7a3f3ff.z01.azurefd.net/api/"
PAGE = "https://census.statssa.gov.za/"
SOURCE = "Statistics South Africa, Census 2022, census dissemination service: population by sex"
LICENCE = "Statistics South Africa, reuse with acknowledgement of the source"
YEAR = 2022
CENSUS = 1                           # the service's time series: 1 is Census 2022
PROVINCE, DISTRICT = 2, 5            # the service's geography levels
NATIONAL = 62_027_503
SLACK = 3                            # people a separately rounded count may miss by
OUT = "south_africa_districts.json"
SITE = PROCESSED.parent.parent / "site" / "data"

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
    for wait in (5, 20, 60, None):
        try:
            return http_json(API + path, cache=False, timeout=120)
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


def read() -> dict[str, Any]:
    """{"provinces": {name: {"id", "total"}}, "districts": [{code, name, province,
    men, women}]}, checked."""
    provinces: dict[str, dict[str, Any]] = {}
    districts: list[dict[str, Any]] = []
    for p in get("Provinces/getAll/"):
        name = " ".join(str(p["provinceDesc"]).split())
        total = indicators(PROVINCE, p["provinceId"]).get("Total population")
        provinces[name] = {"id": p["provinceId"], "total": total}
        for d in get(f"Districts/listByProvince/{p['provinceId']}"):
            code = d["districtMdbc"]
            men, women = by_sex(code)
            own = indicators(DISTRICT, code)
            total = own.get("Total population")
            # The census's counts are weighted and each is rounded on its own,
            # so men and women can miss the total by a person or two (Alfred
            # Nzo: 439,455 and 497,006 against 936,462). More is a misreading.
            if not isinstance(total, (int, float)) or abs(men + women - total) > SLACK:
                raise SystemExit(f"south_africa_districts: {d['districtName']}: {men:,} men and "
                                 f"{women:,} women against a total of {total}")
            if abs(100 * men / (men + women) - float(own.get("Male") or 0)) > 0.06:
                raise SystemExit(f"south_africa_districts: {d['districtName']}: the first count "
                                 f"by sex is not the men's ({own.get('Male')}% men)")
            districts.append({"code": code, "name": " ".join(str(d["districtName"]).split()),
                              "province": name, "men": men, "women": women, "total": int(total)})
            time.sleep(0.2)
    check(provinces, districts)
    return {"provinces": provinces, "districts": districts}


def check(provinces: dict[str, dict[str, Any]], districts: list[dict[str, Any]]) -> None:
    """The provinces make the country and each province's districts make it,
    to the rounding of separately rounded counts (``SLACK`` a unit)."""
    national = sum(p["total"] or 0 for p in provinces.values())
    if abs(national - NATIONAL) > SLACK * len(provinces):
        raise SystemExit(f"south_africa_districts: the provinces make {national:,}, "
                         f"not {NATIONAL:,}")
    for name, p in provinces.items():
        mine = [d for d in districts if d["province"] == name]
        made = sum(d["total"] for d in mine)
        if not mine or abs(made - p["total"]) > SLACK * len(mine):
            raise SystemExit(f"south_africa_districts: {name}'s districts make {made:,}, "
                             f"not {p['total']:,}")
        if made != p["total"]:
            log(f"  {name}: its {len(mine)} districts make {made:,} against {p['total']:,}")


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
        out.append(record(
            f"ZAF-2022-{d['code']}", shape["name"], level="admin2", parent="ZAF", country="ZAF",
            match_by="shape_id", shape_id=shape["id"],
            population=measure(d["total"], year=YEAR, source=SOURCE),
            population_note=note,
            sex_ratio=measure(round(100 * d["men"] / d["women"], 1), unit="males_per_100_females",
                              year=YEAR, source=SOURCE),
            sources=[{"field": "population/sex_ratio", "name": SOURCE,
                      "url": API + f"DsSexes/listDsByParams/{CENSUS}/{DISTRICT}/{d['code']}",
                      "page": PAGE, "license": LICENCE, "year": YEAR}]))
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
        log(f"  {r['name']}: {r['population']['value']:,}, {r['sex_ratio']['value']} men per "
            f"100 women; {r['population_note']}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
