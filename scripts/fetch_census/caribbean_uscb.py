#!/usr/bin/env python3
"""Ages and sexes from the US Census Bureau's Caribbean workbooks: Dominica and The Bahamas.

The Bureau's "Subnational Population and Housing Data Tables" on HDX (read for
compositions by ``uscb.py``) carry an Age-Sex sheet: everyone by sex and
five-year age group, with a column of people whose age was not stated.
``uscb_age_sex.py`` reads the same sheet for the Dominican Republic and
refuses a row whose age groups do not make its total -- right there, where
nobody's age is unstated, and wrong here, where some are. This reader counts
the unstated column into the total and leaves it out of the median.

* **Dominica**, the 2011 Population and Housing Census, Table 1.3 (population
  by age group, sex and parish), for its ten parishes: population, median age
  and sex ratio. The same table is printed in the Central Statistical
  Office's census report, and the parishes must make its 69,325.
* **The Bahamas**, the 2010 Census of Population and Housing, Tables 4.0-4.19
  (population by sex and age), by island: median age and sex ratio for the
  twelve islands the map draws as one district each. Four islands are drawn
  as several districts (Abaco, Andros, Eleuthera, Grand Bahama) and two
  census areas each cover two districts ("Exuma and Cays" is Exuma and Black
  Point, "San Salvador and Rum Cay" is two districts too); those get no
  figure, because an island's median age is not any one of its districts'.
  No population is written: the map's are the 2022 census's where it has them.

Median age is interpolated within the five-year group that holds the middle
person. Every row's groups and unstated make its total, its sexes make it
too, and the units make the country's row.

Usage:
    python -m scripts.fetch_census.caribbean_uscb --country DMA
    python -m scripts.fetch_census.caribbean_uscb            # both
"""

from __future__ import annotations

import argparse
import io
import json
import re
from dataclasses import dataclass
from typing import Any

from . import uscb
from ._shared import PROCESSED, http_get, log, measure, record, write_json
from .binding import fold
from .cod_ps_age import grouped_median

SITE = PROCESSED.parent.parent / "site" / "data"
GROUP = re.compile(r"^([BMF])(\d{2})(\d{2})$")
OPEN = re.compile(r"^([BMF])(\d{2})PL$")


@dataclass(frozen=True)
class Country:
    iso3: str
    dataset: str
    year: int
    census: str
    level: int                     # the Bureau's ADM_LEVEL read
    national: int                  # the country's published count, which the units make
    out: str
    population: bool               # write the population too
    # The Bureau's name -> the map's first-level unit, for the units that are one.
    units: tuple[tuple[str, str], ...] = ()
    # Bureau areas deliberately not written, with why.
    skip: tuple[tuple[str, str], ...] = ()


BAHAMAS_SPLIT = ("the map draws this census island as several districts, and an island's "
                 "median age and sex ratio are not any one district's")
COUNTRIES = {
    "DMA": Country(
        iso3="DMA", dataset="dominica-subnational-boundaries-and-tabular-data", year=2011,
        census=("Central Statistical Office of Dominica, 2011 Population and Housing Census, "
                "Table 1.3: Population by Age Group, Sex and Parish"),
        level=1, national=69_325, out="dominica_census.json", population=True),
    "BHS": Country(
        iso3="BHS", dataset="the-bahamas-subnational-boundaries-and-tabular-data", year=2010,
        census=("Department of Statistics of The Bahamas, 2010 Census of Population and "
                "Housing, Tables 4.0-4.19: Total Population by Sex and Age"),
        level=1, national=351_461, out="bahamas_age_sex.json", population=False,
        units=(("NEW PROVIDENCE", "New Providence"), ("ACKLINS", "Acklins"),
               ("BERRY ISLANDS", "Berry Islands"), ("BIMINI", "Biminis"),
               ("CAT ISLAND", "Cat Island"), ("CROOKED ISLAND AND LONG CAY", "Crooked Island"),
               ("HARBOUR ISLAND", "Harbour Island"), ("INAGUA", "Inagua"),
               ("LONG ISLAND", "Long Island"), ("MAYAGUANA", "Mayaguana"),
               ("RAGGED ISLAND", "Ragged Island"), ("SPANISH WELLS", "Spanish Wells")),
        skip=(("GRAND BAHAMA", BAHAMAS_SPLIT), ("ABACO", BAHAMAS_SPLIT),
              ("ANDROS", BAHAMAS_SPLIT), ("ELEUTHERA", BAHAMAS_SPLIT),
              ("EXUMA AND CAYS", "the census counts Exuma and Black Point together, and the "
                                 "map draws them as two districts"),
              ("SAN SALVADOR AND RUM CAY", "the census counts San Salvador and Rum Cay "
                                           "together, and the map draws them as two "
                                           "districts"))),
}


def number(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        raise SystemExit(f"caribbean_uscb: {value!r} is not a count")


def figures(row: list[Any], at: dict[str, int], where: str) -> dict[str, Any]:
    """One row's median age, men, women and total, after its sums are checked.

    The age groups and the unstated column must make the total, for both
    sexes and each; the sexes must make it too. The median is of the people
    whose age is known.
    """
    groups: dict[str, list[tuple[int, int | None, int]]] = {"B": [], "M": [], "F": []}
    for name, i in at.items():
        closed, open_ = GROUP.match(name), OPEN.match(name)
        if closed:
            sex, low, high = closed.groups()
            groups[sex].append((int(low), int(high), number(row[i])))
        elif open_:
            sex, low = open_.groups()
            groups[sex].append((int(low), None, number(row[i])))
    out = {}
    for sex, total_col in (("B", "BTOTL"), ("M", "MTOTL"), ("F", "FTOTL")):
        total = number(row[at[total_col]])
        unstated = number(row[at[f"{sex}_UNSTATED"]]) if f"{sex}_UNSTATED" in at else 0
        made = sum(g[2] for g in groups[sex]) + unstated
        if not groups[sex] or made != total:
            raise SystemExit(f"caribbean_uscb: {where}: {sex} age groups and unstated make "
                             f"{made:,}, against a total of {total:,}")
        out[sex] = total
    if out["M"] + out["F"] != out["B"]:
        raise SystemExit(f"caribbean_uscb: {where}: men {out['M']:,} and women {out['F']:,} "
                         f"do not make {out['B']:,}")
    both = sorted(groups["B"], key=lambda g: g[0])
    unstated = number(row[at["B_UNSTATED"]]) if "B_UNSTATED" in at else 0
    return {"median": grouped_median(both), "men": out["M"], "women": out["F"],
            "total": out["B"], "unstated": unstated}


def read(country: Country, rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """{area name: figures} at the country's level, checked against the country's row."""
    names, _ = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    units, whole = {}, None
    for row in rows[2:]:
        level = number(row[at["ADM_LEVEL"]])
        name = str(row[at["AREA_NAME"]] or "").strip()
        if level == 0:
            whole = figures(row, at, name)
        elif level == country.level:
            units[name] = figures(row, at, name)
    if whole is None or whole["total"] != country.national:
        raise SystemExit(f"caribbean_uscb: {country.iso3}'s own row is "
                         f"{whole and whole['total']}, not the published {country.national:,}")
    made = sum(u["total"] for u in units.values())
    if made != whole["total"]:
        raise SystemExit(f"caribbean_uscb: {country.iso3}'s areas make {made:,} of "
                         f"{whole['total']:,}")
    log(f"  {country.iso3}: {len(units)} areas making {made:,}, every row's ages and sexes "
        "making its total")
    return units


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--country", choices=sorted(COUNTRIES), action="append")
    args = ap.parse_args()
    import openpyxl
    for iso3 in args.country or sorted(COUNTRIES):
        country = COUNTRIES[iso3]
        blob = http_get(uscb.workbook_url(country.dataset), binary=True, cache=False)
        book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
        meta = " ".join(str(c) for r in uscb.sheet_rows(book, "Metadata") for c in r if c)
        if str(country.year) not in meta:
            raise SystemExit(f"caribbean_uscb: {iso3}'s workbook never names {country.year}")
        units = read(country, uscb.sheet_rows(book, "Age-Sex"))
        admin1 = json.loads((SITE / "admin1" / f"{iso3}.units.json").read_text())
        shapes = {fold(u["name"]): u for u in admin1}
        chosen = dict(country.units) or {name: name.title() for name in units}
        skip = dict(country.skip)
        unknown = sorted(set(units) - set(chosen) - set(skip))
        if unknown:
            raise SystemExit(f"caribbean_uscb: {iso3}: areas neither bound nor skipped: {unknown}")
        source = f"{country.census}, as the US Census Bureau tabulates it for HDX"
        records = []
        for area, ours in sorted(chosen.items()):
            shape = shapes.get(fold(ours))
            if shape is None or area not in units:
                raise SystemExit(f"caribbean_uscb: {iso3}: {area} -> {ours} has no polygon "
                                 "or no row")
            u = units[area]
            fields: dict[str, Any] = {
                "median_age": measure(u["median"], unit="years", year=country.year,
                                      source=source),
                "median_age_note": (
                    "Interpolated within the five-year age group holding the middle person, "
                    f"from the {country.year} census's count by sex and five-year age group"
                    + (f"; {u['unstated']:,} people of unstated age are left out of it"
                       if u["unstated"] else "") + "."),
                "sex_ratio": measure(round(1000 * u["men"] / u["women"]),
                                     unit="males_per_1000_females", year=country.year,
                                     source=source),
                "sources": [{"field": "median_age/sex_ratio" + ("/population"
                                                                 if country.population else ""),
                             "name": source, "url": uscb.dataset_url(country.dataset),
                             "year": country.year, "license": "CC BY-IGO, published via HDX"}],
            }
            if country.population:
                fields["population"] = measure(u["total"], year=country.year, source=source)
                fields["population_note"] = (f"Everyone counted in the {country.year} census, "
                                             "people of unstated age included.")
            records.append(record(
                f"{iso3}-USCB-AGE-{fold(area)}", shape["name"], level="admin1", parent=iso3,
                country=iso3, match_by="shape_id", shape_id=shape["id"],
                aliases=[area.title()] if area.title() != shape["name"] else [], **fields))
        for area, why in sorted(skip.items()):
            log(f"  {iso3}: {area} not written: {why}")
        write_json(PROCESSED / country.out, records)
        log(f"  wrote {country.out}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
