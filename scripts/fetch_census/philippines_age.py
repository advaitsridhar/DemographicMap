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
then ``Total_MF`` and each age from ``Under 1`` up to an open top class (80+),
for both sexes, then the same for males (``_M``) and females (``_F``). This
reads every barangay, adds them up by municipality and province, and gives
each province:

* **median age**, interpolated within the single year of age that holds the
  middle person (``redatam.median_age``), the top class open;
* **sex ratio**, males per 100 females;
* **population**, the census count -- the provinces' figures on the map are
  COD-PS projections for 2022, and the four Metro Manila districts other than
  Manila's and Cotabato City had none.

**What a province is here.** The boundary file draws the Philippines'
provinces at its second level, with every highly urbanized city inside the
province around it, Metro Manila as four numbered districts, and the cities of
Isabela and Cotabato on their own. The PSA's table is keyed nearly the same
way -- its province column writes the four districts and the city of Isabela
with a "(Not a Province)" suffix, taken off before matching, and gives a
renamed province's old name in brackets ("DAVAO DE ORO (COMPOSTELA VALLEY)",
"SAMAR (WESTERN SAMAR)"), so a name is tried whole, before the bracket and
inside it. A province of the table that binds to no polygon refuses the run,
unless it is one of ``NO_POLYGON``; a name that binds two polygons does too.

**Three polygons are not what their names say**, measured on the map's own
tiles: the boundary file draws no Sultan Kudarat, its "Maguindanao" is nearly
twice Maguindanao's area and runs south over Sultan Kudarat's, and its
"Cotabato" covers two thirds of the province. Those two polygons get no
figure (``EXCLUDE``), and the census's Sultan Kudarat and the Bangsamoro
region's "Interim Province" -- the 63 barangays of Cotabato that joined it in
2019 -- are counted nowhere but the national check. Cotabato City, which the
boundary file draws on its own, is taken out of whichever province the table
files it under (``CITIES``).

**Regions** are the first level, and the boundary file's regions are not
quite the PSA's of 2020 (it files Cotabato City under Soccsksargen, which the
city left for the Bangsamoro region in 2019). So a region's figures here are
the sum of the provinces the map draws inside that region's polygon, which
is what the polygon holds; the note says so. A region with any of its drawn
provinces unbound or excluded is not written.

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
BRACKET = re.compile(r"^(?P<before>.*?)\s*\((?P<inside>[^)]*)\)\s*$")
# The PSA's province name -> the boundary file's, where they differ by more
# than case, accents, the suffix and a name in brackets.
ALIASES = {"Davao de Oro": "Compostela Valley"}
# Polygons that are not the province of their name, and are left without a
# figure. Measured on the map's own tiles (site/tiles/admin2.pmtiles, zoom 8):
# the boundary file draws no Sultan Kudarat, and its "Maguindanao" spans
# 9,144 km2 south to 6.12 N and east to 125.1 E -- Maguindanao itself is some
# 4,900 km2 and ends near 6.6 N, Sultan Kudarat's 5,300 km2 lie south of it --
# while its "Cotabato" covers 5,899 km2 of the province's 9,008. Either
# province's count would be the wrong people on those shapes.
EXCLUDE = {
    "Maguindanao": ("the boundary file's polygon takes in Sultan Kudarat, which it does not "
                    "draw, and more (9,144 km2 against Maguindanao's ~4,900)"),
    "Cotabato": ("the boundary file's polygon covers some 5,900 km2 of the province's "
                 "9,008; the rest lies inside its 'Maguindanao'"),
}
# Provinces of the census that the boundary file draws no polygon for: their
# people are counted in the national check and written nowhere.
NO_POLYGON = {"Sultan Kudarat", "Interim Province"}
# Cities the boundary file draws apart from the province the PSA files them
# under: the polygon's name -> the municipality as the table may name it.
CITIES = {"Cotabato City": ("Cotabato City", "City of Cotabato")}
SEXES = ("MF", "M", "F")
HEADER = re.compile(r"^(?P<age>.+?)_(?P<sex>MF|M|F)$")


def columns(header: list[Any]) -> dict[str, Any]:
    """Where each figure is: totals and every age, by sex; the label columns."""
    names = [str(h or "").strip() for h in header]
    at = {n.lower(): i for i, n in enumerate(names) if n}
    for need in ("region", "province", "mun", "bgy"):
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
    return {"region": at["region"], "province": at["province"], "municipality": at["mun"],
            "barangay": at["bgy"], "totals": totals, "ages": ages, "top": bands[-1][0]}


def number(cell: Any) -> int:
    if cell in (None, "", "-"):
        return 0
    value = float(str(cell).replace(",", ""))
    if value != int(value) or value < 0:
        raise SystemExit(f"philippines_age: {cell!r} is not a count of people")
    return int(value)


def province_key(name: Any) -> str:
    return SUFFIX.sub("", " ".join(str(name or "").split()))


def names_of(key: str) -> list[str]:
    """A province key's candidate names: whole, before its bracket, inside it."""
    out = [key, ALIASES.get(key, key)]
    if m := BRACKET.match(key):
        out += [m.group("before"), m.group("inside")]
    return [n for n in dict.fromkeys(out) if n]


def aggregate(rows: Iterable[list[Any]], cols: dict[str, Any]) -> dict[tuple[str, str], Any]:
    """Every barangay checked and added into its municipality:
    {(province, municipality): unit}."""
    units: dict[tuple[str, str], dict[str, Any]] = {}
    bad: list[str] = []
    seen = 0
    for row in rows:
        if not row or row[cols["province"]] in (None, ""):
            continue
        seen += 1
        region = " ".join(str(row[cols["region"]]).split())
        prov = province_key(row[cols["province"]])
        mun = " ".join(str(row[cols["municipality"]] or "").split())
        unit = units.setdefault((prov, mun), {
            "region": region, "province": prov, "municipality": mun, "barangays": 0,
            "ages": {s: Counter() for s in SEXES}, "totals": Counter()})
        unit["barangays"] += 1
        totals = {s: number(row[cols["totals"][s]]) for s in SEXES}
        for sex in SEXES:
            ages = {b[0]: number(row[i]) for b, i in cols["ages"][sex].items()}
            if sum(ages.values()) != totals[sex]:
                bad.append(f"{prov} / {mun} / {row[cols['barangay']]}: {sex} ages make "
                           f"{sum(ages.values()):,}, not {totals[sex]:,}")
            unit["ages"][sex].update(ages)
            unit["totals"][sex] += totals[sex]
        if totals["M"] + totals["F"] != totals["MF"]:
            bad.append(f"{prov} / {mun} / {row[cols['barangay']]}: {totals['M']:,} males and "
                       f"{totals['F']:,} females make {totals['M'] + totals['F']:,}, "
                       f"not {totals['MF']:,}")
    if bad:
        raise SystemExit(f"philippines_age: {len(bad)} barangay rows fail their own sums, "
                         "e.g. " + "; ".join(bad[:5]))
    log(f"  {seen:,} barangays in {len(units):,} cities and municipalities of "
        f"{len({k[0] for k in units})} provinces, every one making its own totals")
    return units


def merge(parts: list[dict[str, Any]]) -> dict[str, Any]:
    ages = {s: Counter() for s in SEXES}
    for p in parts:
        for sex in SEXES:
            ages[sex].update(p["ages"][sex])
    return {"ages": ages, "barangays": sum(p["barangays"] for p in parts),
            "municipalities": [p["municipality"] for p in parts]}


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


def places(units: dict[tuple[str, str], dict[str, Any]], shapes: list[dict[str, Any]]
           ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Each polygon's census figures: {shape id: merged unit}, and what was left out.

    A city of ``CITIES`` goes to its own polygon whatever province files it; a
    province goes to the one polygon one of its names folds to; a polygon of
    ``EXCLUDE`` takes nothing, and a province of ``NO_POLYGON`` goes nowhere.
    """
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in shapes:
        by_name[fold(s["name"])].append(s)
    cities = {fold(m): poly for poly, ms in CITIES.items() for m in ms}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    left: dict[str, str] = {}
    provinces = sorted({k[0] for k in units})
    for prov in provinces:
        muns = [u for k, u in units.items() if k[0] == prov]
        rest = []
        for u in muns:
            poly = cities.get(fold(u["municipality"]))
            if poly:
                hits = by_name.get(fold(poly), [])
                if len(hits) != 1:
                    raise SystemExit(f"philippines_age: {len(hits)} polygons named {poly}")
                groups[hits[0]["id"]].append(u)
                log(f"  {u['municipality']} ({sum(u['ages']['MF'].values()):,}) taken out of "
                    f"{prov} for the polygon {poly}")
            else:
                rest.append(u)
        if not rest:
            continue
        hits = {s["id"]: s for n in names_of(prov) for s in by_name.get(fold(n), [])}
        if len(hits) > 1:
            raise SystemExit(f"philippines_age: {prov!r} names {len(hits)} polygons: "
                             f"{sorted(s['name'] for s in hits.values())}")
        if not hits:
            if any(fold(n) in {fold(x) for x in NO_POLYGON} for n in names_of(prov)):
                left[prov] = "the boundary file draws no polygon for it"
                continue
            raise SystemExit(f"philippines_age: {prov!r} binds to no polygon")
        shape = next(iter(hits.values()))
        if shape["name"] in EXCLUDE:
            left[prov] = f"its polygon {shape['name']!r} is left out: {EXCLUDE[shape['name']]}"
            continue
        if groups.get(shape["id"]) and any(g["province"] != prov for g in groups[shape["id"]]):
            raise SystemExit(f"philippines_age: {shape['name']!r} bound by two provinces")
        groups[shape["id"]].extend(rest)
    out = {sid: merge(parts) for sid, parts in groups.items()}
    for sid, parts in groups.items():
        out[sid]["provinces"] = sorted({p["province"] for p in parts})
    return out, left


def figures(ages: dict[str, Counter], top: int, where: str) -> tuple[float, int, int, int]:
    median = single_median(ages["MF"])
    if median is None or median >= top:
        raise SystemExit(f"philippines_age: {where}: no median below the open {top}+ class")
    return median, sum(ages["M"].values()), sum(ages["F"].values()), sum(ages["MF"].values())


def build(units: dict[tuple[str, str], dict[str, Any]], top: int,
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    figs, left = places(units, admin2)
    names2 = {s["id"]: s["name"] for s in admin2}
    unbound = sorted(s["name"] for s in admin2 if s["id"] not in figs)
    log(f"  {len(figs)} polygons with a count; polygons without: {unbound or '-'}; "
        f"census provinces written nowhere: " + ("; ".join(f"{k} ({v})" for k, v in
                                                        sorted(left.items())) or "-"))
    records: list[dict[str, Any]] = []
    for sid, f in sorted(figs.items(), key=lambda kv: names2[kv[0]]):
        name = names2[sid]
        median, men, women, total = figures(f["ages"], top, name)
        if name in CITIES:
            whose = (f"the 2020 Census of Population and Housing's count of everyone in "
                     f"{f['municipalities'][0]} ({f['barangays']:,} barangays)")
        else:
            whose = (f"the 2020 Census of Population and Housing's count of everyone in the "
                     f"{f['barangays']:,} barangays the PSA tabulates under "
                     f"{' and '.join(f['provinces'])}")
        records.append(record(
            f"PHL-CPH2020-{fold(name)}", name, level="admin2", parent="PHL",
            country="PHL", match_by="shape_id", shape_id=sid,
            aliases=[p for p in f["provinces"] if fold(p) != fold(name)],
            sources=[{"field": "population/median_age/sex_ratio", "name": SOURCE,
                      "url": PAGE, "year": YEAR, "license": LICENCE}],
            **age_sex(median=median, men=men, women=women, year=YEAR, source=SOURCE,
                      population=total,
                      median_note=(f"Interpolated within the single year of age that "
                                   f"holds the middle person, from {whose}, by single "
                                   f"year of age to an open {top}+."),
                      ratio_note=f"Males per 100 females in {whose}.",
                      population_note=f"The census count of {YEAR}: {whose}."),
        ))
    for region in admin1:
        kids = [s for s in admin2 if s["parent"] == region["id"]]
        missing = [s["name"] for s in kids if s["id"] not in figs]
        if not kids or missing:
            log(f"  {region['name']}: not written; its drawn provinces "
                f"{missing or '(none)'} have no count")
            continue
        ages = {s: Counter() for s in SEXES}
        for s in kids:
            for sex in SEXES:
                ages[sex].update(figs[s["id"]]["ages"][sex])
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
