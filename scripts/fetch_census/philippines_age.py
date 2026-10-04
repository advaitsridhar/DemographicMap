#!/usr/bin/env python3
"""Philippines: median age, sex ratio and population by province and region, 2020 census.

The Philippine Statistics Authority's 2020 Census of Population and Housing
counted everyone by single year of age and sex, and the PSA's table of that
count for every one of the country's 42,000-odd barangays is published on HDX
by OCHA Philippines, under CC BY, with the barangay codes of the COD
administrative boundaries:

    Total Population by Single-Year Age, Sex, Region, Province,
    City/Municipality and Barangay (admin 4) Census 2020
    https://data.humdata.org/dataset/popn-single-year-age-sex-and-barangay-census-2020

One workbook, one sheet (``Brgy_adm4``): six label columns -- region,
province, city or municipality, barangay, and the new and old PSGC codes --
then ``Total_MF`` and each age from ``Under 1`` up to an open top class, for
both sexes, then the same for males (``_M``) and females (``_F``). This reads
every barangay, adds them up by province, and gives each province:

* **median age**, interpolated within the single year of age that holds the
  middle person (``redatam.median_age``), the top class open;
* **sex ratio**, males per 100 females;
* **population**, the census count, for the provinces whose figure on the map
  is a projection (COD-PS 2022) or missing -- the four Metro Manila districts
  other than Manila's, and Cotabato City, had none.

**What a province is here.** The boundary file draws the Philippines'
provinces at its second level, with every highly urbanized city inside the
province around it, Metro Manila as four numbered districts, and the cities of
Isabela and Cotabato on their own. The PSA's table is keyed the same way -- the
dataset says so ("consistent with [Philippines - Subnational Administrative
Boundaries]"), and its province column writes the four districts and the two
cities with a "(Not a Province)" suffix, which is taken off before matching.
Davao de Oro is the 2019 name of the province the boundary file still calls
Compostela Valley, and is declared as such. A province of the table that binds
to no polygon, or a polygon left without a province, is reported; a province
key that binds twice refuses the run.

**Regions** are the first level, and the boundary file's regions are not
quite the PSA's of 2020 (it files Cotabato City under Soccsksargen, which the
city left for the Bangsamoro region in 2019). So a region's figures here are
the sum of the provinces the map draws inside that region's polygon, which
is what the polygon holds; the note says so. A region with any of its drawn
provinces unbound is not written.

**Checks**, each a refusal: every barangay's ages make its own total for both
sexes and for each, and its males and females make its total; the country's
barangays make the PSA's proclaimed 2020 population (109,035,343, which also
counts some 2,000 Filipinos in the country's embassies, consulates and
missions abroad -- the barangays must come within 0.01% of it); and the
national median recomputed from the same counts is within 0.3 years of the
25.3 the PSA published.

Usage:
    python -m scripts.fetch_census.philippines_age
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from typing import Any, Iterable

from ._shared import PROCESSED, RAW, download, http_json, log, record, write_json
from .sea_common import age_sex, band, drawn, fold, single_median

OUT = "philippines_age.json"
YEAR = 2020
DATASET = "popn-single-year-age-sex-and-barangay-census-2020"
PAGE = f"https://data.humdata.org/dataset/{DATASET}"
SOURCE = ("Philippine Statistics Authority, 2020 Census of Population and Housing: total "
          "population by single-year age, sex, region, province, city/municipality and "
          "barangay (published on HDX by OCHA Philippines)")
LICENCE = "CC BY (Creative Commons Attribution International), per the HDX dataset"
NATIONAL = 109_035_343          # the 2020 CPH as proclaimed, embassies included
NATIONAL_TOLERANCE = 0.0001
NATIONAL_MEDIAN = 25.3          # PSA, 2020 CPH: median age
MEDIAN_TOLERANCE = 0.3
SUFFIX = re.compile(r"\s*\(\s*not a province\s*\)\s*$", re.IGNORECASE)
# The PSA's province name -> the boundary file's, where they differ by more
# than case, accents and the suffix.
ALIASES = {"Davao de Oro": "Compostela Valley"}
SEXES = ("MF", "M", "F")
HEADER = re.compile(r"^(?P<age>.+?)_(?P<sex>MF|M|F)$")


def columns(header: list[Any]) -> dict[str, Any]:
    """Where each figure is: totals and every age, by sex; the label columns."""
    names = [str(h or "").strip() for h in header]
    at = {n.lower(): i for i, n in enumerate(names) if n}
    for need in ("region", "province", "bgy"):
        if need not in at:
            raise SystemExit(f"philippines_age: no {need!r} column in {names[:10]}")
    totals: dict[str, int] = {}
    ages: dict[str, dict[tuple[int, int | None], int]] = {s: {} for s in SEXES}
    for i, name in enumerate(names):
        m = HEADER.match(name)
        if not m:
            continue
        sex = m.group("sex")
        if m.group("age").strip().lower() == "total":
            totals[sex] = i
            continue
        b = band(m.group("age"))
        if b is None:
            raise SystemExit(f"philippines_age: an age column the reader does not know: "
                             f"{name!r}")
        if b in ages[sex]:
            raise SystemExit(f"philippines_age: two columns for age {b} ({sex})")
        ages[sex][b] = i
    if set(totals) != set(SEXES):
        raise SystemExit(f"philippines_age: totals found for {sorted(totals)}, not MF, M and F")
    bands = sorted(ages["MF"])
    if not bands or bands != sorted(ages["M"]) or bands != sorted(ages["F"]):
        raise SystemExit("philippines_age: the sexes do not share one set of ages")
    for k, (low, high) in enumerate(bands):
        last = k == len(bands) - 1
        if low != (0 if k == 0 else bands[k - 1][1] + 1) or (high is None) != last:
            raise SystemExit(f"philippines_age: ages are not single years from 0 to an open "
                             f"top class: {bands[:3]} ... {bands[-3:]}")
        if not last and high != low:
            raise SystemExit(f"philippines_age: {low}-{high} is not a single year")
    return {"region": at["region"], "province": at["province"], "barangay": at["bgy"],
            "totals": totals, "ages": ages, "top": bands[-1][0]}


def number(cell: Any) -> int:
    if cell in (None, "", "-"):
        return 0
    value = float(str(cell).replace(",", ""))
    if value != int(value) or value < 0:
        raise SystemExit(f"philippines_age: {cell!r} is not a count of people")
    return int(value)


def province_key(name: Any) -> str:
    return SUFFIX.sub("", " ".join(str(name or "").split()))


def aggregate(rows: Iterable[list[Any]], cols: dict[str, Any]) -> dict[str, Any]:
    """Every barangay checked and added into its province: {(region, province): unit}."""
    units: dict[tuple[str, str], dict[str, Any]] = {}
    bad: list[str] = []
    seen = 0
    for row in rows:
        if not row or row[cols["province"]] in (None, ""):
            continue
        seen += 1
        region = " ".join(str(row[cols["region"]]).split())
        prov = province_key(row[cols["province"]])
        unit = units.setdefault((region, prov), {
            "region": region, "province": prov, "barangays": 0,
            "ages": {s: Counter() for s in SEXES}, "totals": Counter()})
        unit["barangays"] += 1
        totals = {s: number(row[cols["totals"][s]]) for s in SEXES}
        for sex in SEXES:
            ages = {b[0]: number(row[i]) for b, i in cols["ages"][sex].items()}
            if sum(ages.values()) != totals[sex]:
                bad.append(f"{prov} / {row[cols['barangay']]}: {sex} ages make "
                           f"{sum(ages.values()):,}, not {totals[sex]:,}")
            unit["ages"][sex].update(ages)
            unit["totals"][sex] += totals[sex]
        if totals["M"] + totals["F"] != totals["MF"]:
            bad.append(f"{prov} / {row[cols['barangay']]}: {totals['M']:,} males and "
                       f"{totals['F']:,} females make {totals['M'] + totals['F']:,}, "
                       f"not {totals['MF']:,}")
    if bad:
        raise SystemExit(f"philippines_age: {len(bad)} barangay rows fail their own sums, "
                         "e.g. " + "; ".join(bad[:5]))
    log(f"  {seen:,} barangays in {len(units)} provinces, every one making its own totals")
    return units


def check_national(units: dict[Any, dict[str, Any]], top: int) -> Counter:
    ages = Counter()
    for u in units.values():
        ages.update(u["ages"]["MF"])
    total = sum(ages.values())
    if abs(total - NATIONAL) > NATIONAL_TOLERANCE * NATIONAL:
        raise SystemExit(f"philippines_age: the barangays make {total:,}, against the "
                         f"proclaimed {NATIONAL:,}")
    median = single_median(ages)
    if median is None or abs(median - NATIONAL_MEDIAN) > MEDIAN_TOLERANCE:
        raise SystemExit(f"philippines_age: national median {median} against the PSA's "
                         f"{NATIONAL_MEDIAN}")
    log(f"  the barangays make {total:,} ({total - NATIONAL:+,} on the proclaimed "
        f"{NATIONAL:,}); national median {median} against the PSA's {NATIONAL_MEDIAN}; "
        f"top class {top}+")
    return ages


def bind(provinces: list[str], shapes: list[dict[str, Any]]
         ) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    """Province key -> polygon, by folded name or declared alias; one to one."""
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in shapes:
        by_name[fold(s["name"])].append(s)
    bound: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    unbound: list[str] = []
    for prov in provinces:
        hits = by_name.get(fold(ALIASES.get(prov, prov)), [])
        if len(hits) > 1:
            raise SystemExit(f"philippines_age: {prov!r} names {len(hits)} polygons")
        if not hits:
            unbound.append(prov)
            continue
        if hits[0]["id"] in used:
            raise SystemExit(f"philippines_age: {hits[0]['name']!r} bound twice")
        used.add(hits[0]["id"])
        bound[prov] = hits[0]
    left = sorted(s["name"] for s in shapes if s["id"] not in used)
    return bound, unbound, left


def figures(ages: dict[str, Counter], top: int, where: str) -> tuple[float, int, int, int]:
    median = single_median(ages["MF"])
    if median is None or median >= top:
        raise SystemExit(f"philippines_age: {where}: no median below the open {top}+ class")
    return median, sum(ages["M"].values()), sum(ages["F"].values()), sum(ages["MF"].values())


def build(units: dict[Any, dict[str, Any]], top: int, admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_province: dict[str, dict[str, Any]] = {}
    for u in units.values():
        if u["province"] in by_province:
            raise SystemExit(f"philippines_age: {u['province']!r} is filed under two regions")
        by_province[u["province"]] = u
    bound, unbound, left = bind(sorted(by_province), admin2)
    log(f"  {len(bound)} provinces bound to their polygons; not bound: {unbound or '-'}; "
        f"polygons with no province: {left or '-'}")
    if unbound:
        raise SystemExit(f"philippines_age: provinces with no polygon: {unbound}")
    records: list[dict[str, Any]] = []
    shape_ages: dict[str, dict[str, Counter]] = {}
    for prov, shape in sorted(bound.items()):
        u = by_province[prov]
        median, men, women, total = figures(u["ages"], top, prov)
        shape_ages[shape["id"]] = u["ages"]
        whose = (f"the 2020 Census of Population and Housing's count of everyone in the "
                 f"{u['barangays']:,} barangays the PSA tabulates under {prov}")
        records.append(record(
            f"PHL-CPH2020-{fold(prov)}", shape["name"], level="admin2", parent="PHL",
            country="PHL", match_by="shape_id", shape_id=shape["id"],
            aliases=[prov] if fold(prov) != fold(shape["name"]) else [],
            sources=[{"field": "population/median_age/sex_ratio", "name": SOURCE,
                      "url": PAGE, "year": YEAR, "license": LICENCE}],
            **age_sex(median=median, men=men, women=women, year=YEAR, source=SOURCE,
                      population=total,
                      median_note=(f"Interpolated within the single year of age that "
                                   f"holds the middle person, from {whose}, by single "
                                   f"year of age to an open {top}+."),
                      ratio_note=f"Males per 100 females in {whose}.",
                      population_note=(f"The census count of {YEAR}: {whose}.")),
        ))
    names2 = {s["id"]: s["name"] for s in admin2}
    for region in admin1:
        kids = [s for s in admin2 if s["parent"] == region["id"]]
        missing = [s["name"] for s in kids if s["id"] not in shape_ages]
        if not kids or missing:
            log(f"  {region['name']}: not written; its drawn provinces "
                f"{missing or '(none)'} have no count")
            continue
        ages = {s: Counter() for s in SEXES}
        for s in kids:
            for sex in SEXES:
                ages[sex].update(shape_ages[s["id"]][sex])
        median, men, women, total = figures(ages, top, region["name"])
        parts = ", ".join(sorted(names2[s["id"]] for s in kids))
        whose = (f"the 2020 Census of Population and Housing's count of everyone in the "
                 f"{len(kids)} provinces the map draws inside this region ({parts})")
        records.append(record(
            f"PHL-CPH2020-R-{fold(region['name'])}", region["name"], level="admin1",
            parent="PHL", country="PHL", match_by="shape_id", shape_id=region["id"],
            sources=[{"field": "median_age/sex_ratio", "name": SOURCE, "url": PAGE,
                      "year": YEAR, "license": LICENCE}],
            **age_sex(median=median, men=men, women=women, year=YEAR, source=SOURCE,
                      median_note=(f"Interpolated within the single year of age that "
                                   f"holds the middle person, from {whose}, by single "
                                   f"year of age to an open {top}+."),
                      ratio_note=f"Males per 100 females in {whose}."),
        ))
    return records


def resource_url() -> tuple[str, str]:
    package = http_json(f"https://data.humdata.org/api/3/action/package_show?id={DATASET}",
                        cache=False)["result"]
    found = [r for r in package.get("resources") or ()
             if str(r.get("name") or "").lower().endswith(".xlsx")]
    if len(found) != 1:
        raise SystemExit(f"philippines_age: {len(found)} workbooks in {DATASET}")
    return str(found[0]["url"]), str(found[0]["name"])


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log(f"philippines_age: {SOURCE}")
    url, name = resource_url()
    path = download(url, RAW / "philippines" / name)
    import openpyxl
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = book["Brgy_adm4"] if "Brgy_adm4" in book.sheetnames else book.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    cols = columns(list(next(rows)))
    units = aggregate((list(r) for r in rows), cols)
    check_national(units, cols["top"])
    records = build(units, cols["top"], drawn("PHL", "admin1"), drawn("PHL", "admin2"))
    for level in ("admin1", "admin2"):
        rs = [r for r in records if r["level"] == level]
        meds = sorted(r["median_age"]["value"] for r in rs)
        rats = sorted(r["sex_ratio"]["value"] for r in rs)
        log(f"  {level}: {len(rs)} units; median {meds[0]}-{meds[-1]}; "
            f"sex ratio {rats[0]}-{rats[-1]}")
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
