#!/usr/bin/env python3
"""Slovakia: population, median age and sex ratio by okres, from ŠÚ SR's DATAcube.

The Statistical Office of the Slovak Republic publishes its demographic
tables as JSON-stat cubes (data.statistics.sk, API v2). Two are read:

* ``om7009rr`` -- "Age Structure - SR-Area-Reg-District, U-R": the permanently
  living population on 31 December by sex and single year of age (0 to 109,
  then 110 and over), for the country, its regions and its 79 districts;
* ``om7005rr`` -- "Indices of the Age Structure": among them the office's own
  median age (IN010088) for the same districts.

The office publishes the median for exactly these units, so its figure is
the one written; the median recomputed from the single years is only a check
on the reading (the two must agree to within half a year). The sex ratio and
the population are summed from the single years.

**Names.** geoBoundaries' Slovak districts are English ("District of X") and
many lost their diacritics in a way no folding undoes -- "District of Kolice
I" is Košice I, "Pilina" is Žilina, "Tarnovica" Žarnovica, "Liptovsk"
Liptovský Mikuláš. So every map name is declared against the office's name
in ``MAP_NAMES`` below, each checked against the region the boundary file
files it under, and anything unbound on either side stops the run. The
record carries the office's name, which the build puts on the polygon, and
keeps the boundary file's spelling as an alias.

Usage:
    python -m scripts.fetch_census.slovakia [--year 2025]
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Any

from ._shared import PROCESSED, http_json, log, measure, record, write_json
from .central_ages import (
    age_sex_fields, check_national_median, check_sum, fold, report_unbound, units,
)
from .pxweb import unstack

API = "https://data.statistics.sk/api/v2/dataset/{cube}/{path}?lang=en&type=json"
PORTAL = "https://data.statistics.sk/"
SOURCE = ("Statistical Office of the Slovak Republic, DATAcube om7009rr (age structure) and "
          "om7005rr (indices of the age structure)")
LICENCE = "Statistical Office of the SR open data (free reuse with attribution)"
OUT = PROCESSED / "slovakia_okres.json"
POPULATION = "IN010053"          # permanently living population on 31 December
MEDIAN = "IN010088"              # median age (year)
REGIONS = {"SK010": "Region of Bratislava", "SK021": "Region of Trnava",
           "SK022": "Region of Trenčín", "SK023": "Region of Nitra",
           "SK031": "Region of Žilina", "SK032": "Region of Banská Bystrica",
           "SK041": "Region of Prešov", "SK042": "Region of Košice"}

# The boundary file's name -> the district's Slovak name, where folding the
# two does not already make them equal. Declared, not guessed: several are
# too far gone for any similarity rule to be trusted with them.
MAP_NAMES = {
    "District of Banskk vtiavnica": "Banská Štiavnica",
    "District of Bansks Bystrica": "Banská Bystrica",
    "District of Bonovce nad Bebra*": "Bánovce nad Bebravou",
    "District of Dolne Kub": "Dolný Kubín",
    "District of Dunajskn Streda": "Dunajská Streda",
    "District of Gala": "Šaľa",
    "District of Giar nad Hronom": "Žiar nad Hronom",
    "District of Humennn": "Humenné",
    "District of Kermarok": "Kežmarok",
    "District of Kolice I": "Košice I",
    "District of Kolice II": "Košice II",
    "District of Kolice III": "Košice III",
    "District of Kolice IV": "Košice IV",
    "District of Komprno": "Komárno",
    "District of Kovice - okolie": "Košice - okolie",
    "District of Kysucki Novi Mesto": "Kysucké Nové Mesto",
    "District of Liptovsk": "Liptovský Mikuláš",
    "District of Nova Mesto nad Va*": "Nové Mesto nad Váhom",
    "District of Nova Zkmky": "Nové Zámky",
    "District of Numestovo": "Námestovo",
    "District of Partizonske": "Partizánske",
    "District of Piertany": "Piešťany",
    "District of Pilina": "Žilina",
    "District of Poltcr": "Poltár",
    "District of Povacskn Bystrica": "Považská Bystrica",
    "District of Prchov": "Púchov",
    "District of Predov": "Prešov",
    "District of Revnca": "Revúca",
    "District of Rimavsk": "Rimavská Sobota",
    "District of Ronnava": "Rožňava",
    "District of Ruromberok": "Ružomberok",
    "District of Spieskn Novo Ves": "Spišská Nová Ves",
    "District of Stark Lubovna": "Stará Ľubovňa",
    "District of Svidnsk": "Svidník",
    "District of Tarnovica": "Žarnovica",
    "District of Trebi ov": "Trebišov",
    "District of Trencon": "Trenčín",
    "District of Tvrdo": "Tvrdošín",
    "District of Velka Krta": "Veľký Krtíš",
    "District of Zlatc Moravce": "Zlaté Moravce",
}
EXPECTED = 79


def cube(name: str, path: str) -> list[tuple[dict[str, tuple[str, str]], float]]:
    payload = http_json(API.format(cube=name, path=path), timeout=300)
    return unstack(payload)


def district_name(label: str) -> str:
    return label.replace("District of ", "").strip()


def bind_districts(office: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Office code -> the map's polygon, by declared or folded name within the region."""
    shapes = units("SVK", "admin2")
    regions = {u["id"]: u["name"] for u in units("SVK", "admin1")}
    by_key: dict[str, list[dict[str, Any]]] = {}
    for shape in shapes:
        proper = MAP_NAMES.get(shape["name"], district_name(shape["name"]))
        by_key.setdefault(fold(proper), []).append(shape)
    bound, unbound, used = {}, [], set()
    for code, name in sorted(office.items()):
        region = REGIONS[code[:5]]
        hits = [s for s in by_key.get(fold(name), []) if regions.get(s["parent"]) == region]
        if len(hits) != 1 or hits[0]["id"] in used:
            unbound.append(f"{name} ({code})")
            continue
        bound[code] = hits[0]
        used.add(hits[0]["id"])
    report_unbound("slovakia", unbound, [s["name"] for s in shapes if s["id"] not in used])
    if unbound or len(bound) != EXPECTED:
        raise SystemExit(f"slovakia: {len(bound)} of {EXPECTED} districts bound")
    return bound


def latest(year: int) -> int:
    """The latest year up to ``year`` the age cube answers for.

    DATAcube answers 400 for a year it does not hold yet, which is how the
    first run met 2025 in April 2026.
    """
    import urllib.error
    for candidate in range(year, year - 3, -1):
        try:
            cube("om7009rr", f"SK0/{candidate}/{POPULATION}/SPOLU/Spolu")
            return candidate
        except urllib.error.HTTPError as err:
            log(f"  {candidate}: HTTP {err.code}; trying the year before")
    raise SystemExit(f"slovakia: om7009rr answers for none of {year - 2}..{year}")


def build(year: int) -> list[dict[str, Any]]:
    year = latest(year)
    log(f"slovakia: DATAcube om7009rr / om7005rr, 31 December {year}")
    males: dict[str, Counter] = {}
    females: dict[str, Counter] = {}
    totals: dict[str, float] = {}
    names: dict[str, str] = {}
    # The cube refuses (400) a request for every territory and every age at
    # once, so it is asked one territory at a time, the territories being the
    # ones its sister cube lists.
    medians = {key["om7005rr_vuc"][0]: value
               for key, value in cube("om7005rr", f"all/{year}/{MEDIAN}/SPOLU")}
    rows = []
    for area in sorted(medians):
        rows += cube("om7009rr", f"{area}/{year}/{POPULATION}/all/all")
    for key, value in rows:
        area, area_label = key["om7009rr_vuc"]
        sex = key["om7009rr_poh"][0]
        age_code = key["om7009rr_vek"][0]
        names[area] = area_label
        if age_code == "Spolu":
            if sex == "SPOLU":
                totals[area] = value
            continue
        if sex == "SPOLU":
            continue
        age = 110 if age_code == "Y_GE110" else int(age_code[1:])
        (males if sex == "1" else females).setdefault(area, Counter())[age] += value
    if not totals:
        raise SystemExit(f"slovakia: om7009rr has no figures for {year}")
    district_codes = sorted(c for c in totals if len(c) == 6 and c.startswith("SK0"))
    log(f"  {len(district_codes)} districts, national {totals.get('SK0', 0):,.0f}")
    check_sum((totals[c] for c in district_codes), totals["SK0"], "districts against Slovakia")
    for region in REGIONS:
        check_sum((totals[c] for c in district_codes if c.startswith(region)), totals[region],
                  f"districts against {region}")
    both = Counter(males["SK0"])
    both.update(females["SK0"])
    check_national_median(both, "SK", year + 1)

    bound = bind_districts({c: district_name(names[c]) for c in district_codes})
    source = SOURCE
    records = []
    for code in district_codes:
        shape = bound[code]
        office_median = medians.get(code)
        if office_median is None:
            raise SystemExit(f"slovakia: om7005rr has no median age for {code}")
        fields = age_sex_fields(
            males[code], females[code], year=year, source=source, total=totals[code],
            median_note=(f"The Statistical Office's own median age of the district's permanently "
                         f"living population on 31 December {year} (om7005rr)."),
            ratio_note=(f"Males per 100 females among the district's permanently living "
                        f"population on 31 December {year}, from its single years of age "
                        f"(om7009rr)."))
        mine = fields["median_age"]["value"]
        if abs(mine - office_median) > 0.6:
            raise SystemExit(f"slovakia: {names[code]} median recomputed as {mine}, the office "
                             f"publishes {office_median}")
        fields["median_age"] = measure(round(office_median, 1), unit="years", year=year,
                                       source=source)
        label = shape["name"]
        name = district_name(names[code])
        records.append(record(
            f"SVK-{code}", name, level="admin2", parent=shape["parent"],
            parent_name=REGIONS[code[:5]], country="SVK", codes={"nuts_lau1": code},
            aliases=[label], match_by="shape_id", shape_id=shape["id"],
            sources=[{"field": "population/median_age/sex_ratio", "name": source,
                      "url": PORTAL, "license": LICENCE, "year": year}],
            **fields))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, default=2025)
    args = ap.parse_args()
    records = build(args.year)
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
