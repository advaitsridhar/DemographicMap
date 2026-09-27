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
the one written. The districts are read as totals by sex (population and sex
ratio); the single years are read for the country alone, where the median
recomputed from them must land within 0.3 years of both the office's own
national median and Eurostat's.

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
    SEX_RATIO_UNIT, check_national_median, check_sum, fold, report_unbound, sex_ratio, units,
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


# DATAcube's labels where they are not the district's name as written: "Śaľa"
# with an S acute (U+015A) for the S caron of Šaľa.
OFFICE_SPELLINGS = {"Śaľa": "Šaľa"}


def district_name(label: str) -> str:
    """The district's name from an office or boundary-file label.

    DATAcube writes some names with a no-break space ("Dunajská\\xa0Streda"),
    which folds the same but is not the name; spaces are made plain.
    """
    name = " ".join(label.replace("\xa0", " ").replace("District of ", "").split())
    return OFFICE_SPELLINGS.get(name, name)


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
        # Both cubes must hold the year: the median cube (om7005rr) can lag
        # the age cube.
        try:
            cube("om7009rr", f"SK0/{candidate}/{POPULATION}/SPOLU/Spolu")
            if not cube("om7005rr", f"SK0/{candidate}/{MEDIAN}/SPOLU"):
                raise urllib.error.HTTPError("", 404, "no median", None, None)
            return candidate
        except urllib.error.HTTPError as err:
            log(f"  {candidate}: HTTP {err.code}; trying the year before")
        except (ValueError, KeyError) as err:
            log(f"  {candidate}: {type(err).__name__} {err}; trying the year before")
    raise SystemExit(f"slovakia: om7009rr answers for none of {year - 2}..{year}")


def by_sex(rows: list[tuple[dict[str, tuple[str, str]], float]]
           ) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """area -> {"SPOLU"|"1"|"2": count} from om7009rr cells with the age total."""
    out: dict[str, dict[str, float]] = {}
    names: dict[str, str] = {}
    for key, value in rows:
        area, label = key["om7009rr_vuc"]
        if key["om7009rr_vek"][0] != "Spolu":
            continue
        names[area] = label
        out.setdefault(area, {})[key["om7009rr_poh"][0]] = value
    return out, names


def national_ages(rows: list[tuple[dict[str, tuple[str, str]], float]]) -> Counter:
    """{age: count} for both sexes from om7009rr cells of one territory.

    The cube lists single years ("Y37") and open groups ("Y_GE100",
    "Y_GE110") side by side, the lower open group being a subtotal of the
    single years above it. Only the open group that starts where the single
    years stop is a class of its own; the others are left out, and the sum
    against the total (made by the caller) proves it.
    """
    singles: Counter = Counter()
    opens: Counter = Counter()
    for key, value in rows:
        age_code, sex = key["om7009rr_vek"][0], key["om7009rr_poh"][0]
        if age_code == "Spolu" or sex == "SPOLU":
            continue
        if age_code.startswith("Y_GE"):
            opens[int(age_code[4:])] += value
        elif age_code[:1] == "Y" and age_code[1:].isdigit():
            singles[int(age_code[1:])] += value
        else:
            raise SystemExit(f"slovakia: an age code {age_code!r} the reader does not know")
    top = max(singles) + 1
    if top not in opens:
        raise SystemExit(f"slovakia: single years stop at {top - 1} and no open group starts at {top}; "
                         f"open groups {sorted(opens)}")
    singles[top] += opens[top]
    return singles


def build(year: int) -> list[dict[str, Any]]:
    year = latest(year)
    log(f"slovakia: DATAcube om7009rr / om7005rr, 31 December {year}")
    import time
    started = time.monotonic()
    medians = {key["om7005rr_vuc"][0]: value
               for key, value in cube("om7005rr", f"all/{year}/{MEDIAN}/SPOLU")}
    log(f"  om7005rr: {len(medians)} territories in {time.monotonic() - started:.0f} s")
    # The office publishes the median for every district, so the single
    # years are not needed district by district -- and asking for them is
    # what outlasted the runner: batches of territories' 112 ages took more
    # than five minutes a request, one at a time more than the runner's 45.
    # So the districts are read as totals by sex, in one request, and the
    # single years only for the country, where they check the office's median.
    t0 = time.monotonic()
    sexes, names = by_sex(cube("om7009rr", f"all/{year}/{POPULATION}/all/Spolu"))
    log(f"  om7009rr: sex totals for {len(sexes)} territories in {time.monotonic() - t0:.0f} s")
    for area, counts in sexes.items():
        if set(counts) != {"SPOLU", "1", "2"}:
            raise SystemExit(f"slovakia: {area} has sexes {sorted(counts)}")
        if abs(counts["1"] + counts["2"] - counts["SPOLU"]) > 0.5:
            raise SystemExit(f"slovakia: {area}: males {counts['1']:,.0f} + females "
                             f"{counts['2']:,.0f} is not {counts['SPOLU']:,.0f}")
    totals = {area: counts["SPOLU"] for area, counts in sexes.items()}
    district_codes = sorted(c for c in totals if len(c) == 6 and c.startswith("SK0"))
    log(f"  {len(district_codes)} districts, national {totals.get('SK0', 0):,.0f}")
    check_sum((totals[c] for c in district_codes), totals["SK0"], "districts against Slovakia")
    for region in REGIONS:
        check_sum((totals[c] for c in district_codes if c.startswith(region)), totals[region],
                  f"districts against {region}")
    t0 = time.monotonic()
    both = national_ages(cube("om7009rr", f"SK0/{year}/{POPULATION}/all/all"))
    log(f"  om7009rr: the country's single years in {time.monotonic() - t0:.0f} s")
    if abs(sum(both.values()) - totals["SK0"]) > 0.5:
        raise SystemExit(f"slovakia: the country's single years make {sum(both.values()):,.0f}, "
                         f"its total is {totals['SK0']:,.0f}")
    mine = check_national_median(both, "SK", year + 1)
    if abs(mine - medians["SK0"]) > 0.3:
        raise SystemExit(f"slovakia: the national median recomputed as {mine}, om7005rr "
                         f"publishes {medians['SK0']}")
    log(f"  national median: recomputed {mine}, om7005rr {medians['SK0']}")

    bound = bind_districts({c: district_name(names[c]) for c in district_codes})
    source = SOURCE
    records = []
    for code in district_codes:
        shape = bound[code]
        office_median = medians.get(code)
        if office_median is None:
            raise SystemExit(f"slovakia: om7005rr has no median age for {code}")
        males, females = sexes[code]["1"], sexes[code]["2"]
        label = shape["name"]
        name = district_name(names[code])
        records.append(record(
            f"SVK-{code}", name, level="admin2", parent=shape["parent"],
            parent_name=REGIONS[code[:5]], country="SVK", codes={"nuts_lau1": code},
            aliases=[label], match_by="shape_id", shape_id=shape["id"],
            population=measure(int(round(totals[code])), year=year, source=source),
            median_age=measure(round(office_median, 1), unit="years", year=year, source=source),
            median_age_note=(f"The Statistical Office's own median age of the district's "
                             f"permanently living population on 31 December {year} (om7005rr)."),
            sex_ratio=measure(sex_ratio(males, females), unit=SEX_RATIO_UNIT, year=year,
                              source=source),
            sex_ratio_note=(f"Males per 100 females among the district's permanently living "
                            f"population on 31 December {year} (om7009rr, all ages)."),
            sources=[{"field": "population/median_age/sex_ratio", "name": source,
                      "url": PORTAL, "license": LICENCE, "year": year}]))
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
