#!/usr/bin/env python3
"""Bangladesh -- every zila's median age, from the 2011 census's age groups.

The 2022 census publishes age for the nation and its eight divisions and for
no smaller unit (``bangladesh.ZILA_AGE_GAP`` lists the tables read). The 2011
census did: its community and zila volumes print the population by five-year
age group and sex for every zila, upazila and union. The U.S. Census Bureau
extracted those tables into one standardised workbook -- HDX dataset
``bangladesh-subnational-boundaries-and-tabular-data``, sheet ``Age-Sex``,
whose data dictionary cites "Bangladesh Population and Housing Census 2011,
2014, Population by 5-Year Age Groups and Sex" (reference day 15 March 2011)
-- and that is what this reads, for the 64 zilas.

So the median here is the 2011 one, and the record says so in its year and its
note: an older census where the newer publishes nothing at that level, as the
brief allows, and never written over a 2022 figure for the same unit (there is
none). It is interpolated within the five-year group that holds the middle
person -- single years are not published by zila -- and refused if that group
is the open "80 and older".

**What is checked before anything is written:**

* in every row the seventeen groups add up to the total, for both sexes, for
  males and for females, and males and females make both sexes;
* the zilas add up to their division and the divisions to the nation, which
  must be the census's enumerated 144,043,697;
* each zila binds to exactly one drawn polygon inside its own division, by
  name (the 2011 BGN spellings folded, with ``bangladesh.ALIASES`` for the
  renamings), and every drawn zila is reached;
* the drawn polygon's 2022 census population must be 0.95 to 1.6 times the
  2011 count -- growth, not a different place: a zila bound to the wrong
  polygon shows up as two unrelated populations.

Usage:
    python -m scripts.fetch_census.bangladesh_zila_ages
"""

from __future__ import annotations

import argparse
import io
from typing import Any

from ._shared import PROCESSED, RAW, http_get, log, measure, record, write_json
from .bangladesh import ALIASES, DIVISION_ALIASES
from .south_asia_common import bind, fold, load_units, median_grouped, report_binding
from .uscb import columns, dataset_url, number, sheet_rows, workbook_url

DATASET = "bangladesh-subnational-boundaries-and-tabular-data"
SHEET = "Age-Sex"
YEAR = 2011
OUT = "bangladesh_zila_age.json"
SOURCE = ("Bangladesh Bureau of Statistics, Population and Housing Census 2011, "
          "population by five-year age group and sex, as extracted by the U.S. "
          "Census Bureau (subnational tabular data for Bangladesh, July 2021)")
LICENCE = "CC BY 4.0 (U.S. Census Bureau, via HDX)"
# The census's enumerated population on 15 March 2011, which the workbook's
# national row and its divisions must make.
NATION_2011 = 144_043_697
# Five-year groups, the last one open; the workbook's column stems.
GROUPS: list[tuple[int, int | None, str]] = [
    *((low, low + 4, f"{low:02d}{low + 4:02d}") for low in range(0, 80, 5)),
    (80, None, "80PL")]
# A drawn zila's 2022 count against its 2011 one. Bangladesh grew 14.7% over
# the eleven years; the widest zila growth is Dhaka's and Gazipur's. Outside
# these bounds the two figures are not one place counted twice.
GROWTH = (0.95, 1.6)
# The six zilas whose BGN romanisation in the workbook and the boundary file's
# spelling differ by more than diacritics, as the first run listed them (the
# other 58 matched outright). Declared, not inferred: "Jaipurhat" and
# "Joypurhat" are one zila, but no rule that bridges them is safe elsewhere.
SPELLINGS_2011 = {
    "Jhalakati": ("Jhalokati",),
    "Khagrachari": ("Khagrachhari",),
    "Kishorganj": ("Kishoreganj",),
    "Shariyatpur": ("Shariatpur",),
    "Jaipurhat": ("Joypurhat",),
    "Nator": ("Natore",),
}


def zila_names(name: str) -> tuple[str, ...]:
    """The 2011 spelling, then the boundary file's names for a renamed zila."""
    key = fold(name)
    extra = next((v for k, v in {**ALIASES, **SPELLINGS_2011}.items() if fold(k) == key), ())
    return (name, *extra)


def division_names(name: str) -> tuple[str, ...]:
    key = fold(name)
    extra = next((v for k, v in DIVISION_ALIASES.items() if fold(k) == key), ())
    return (name, *extra)


def read_rows(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Every area of levels 0-2: its names, its total and its groups by sex."""
    names, _aliases = columns(rows)
    index = {n: i for i, n in enumerate(names)}
    for sex in "BMF":
        for _lo, _hi, stem in GROUPS:
            if f"{sex}{stem}" not in index:
                raise SystemExit(f"bangladesh_zila_ages: no column {sex}{stem} in {SHEET}")
        if f"{sex}TOTL" not in index:
            raise SystemExit(f"bangladesh_zila_ages: no column {sex}TOTL in {SHEET}")
    out = []
    for row in rows[2:]:
        level = number(row[index["ADM_LEVEL"]])
        if level is None or level > 2:
            continue
        area = {
            "level": int(level),
            "name": str(row[index["AREA_NAME"]] or "").strip(),
            "division": str(row[index["ADM1_NAME"]] or "").strip() if level >= 1 else "",
            "code": str(row[index["NSO_CODE"]] or "").strip() if "NSO_CODE" in index else "",
        }
        for sex in "BMF":
            total = number(row[index[f"{sex}TOTL"]])
            counts = [number(row[index[f"{sex}{stem}"]]) for _lo, _hi, stem in GROUPS]
            if total is None or any(c is None for c in counts):
                raise SystemExit(f"bangladesh_zila_ages: {area['name']} has a blank "
                                 f"or negative {sex} cell")
            area[sex] = (int(total), [int(c) for c in counts])
        out.append(area)
    return out


def check_rows(areas: list[dict[str, Any]]) -> None:
    """Groups make totals, sexes make persons, zilas make divisions make the nation."""
    bad = []
    for a in areas:
        for sex in "BMF":
            total, counts = a[sex]
            if sum(counts) != total:
                bad.append(f"{a['name']} {sex}: groups {sum(counts):,} against {total:,}")
        if a["M"][0] + a["F"][0] != a["B"][0]:
            bad.append(f"{a['name']}: {a['M'][0]:,} males + {a['F'][0]:,} females "
                       f"against {a['B'][0]:,}")
    nation = [a for a in areas if a["level"] == 0]
    divisions = [a for a in areas if a["level"] == 1]
    zilas = [a for a in areas if a["level"] == 2]
    if len(nation) != 1 or nation[0]["B"][0] != NATION_2011:
        bad.append(f"the national row is {[n['B'][0] for n in nation]}, not {NATION_2011:,}")
    if len(divisions) != 8 or len(zilas) != 64:
        bad.append(f"{len(divisions)} divisions and {len(zilas)} zilas, not 8 and 64")
    if sum(d["B"][0] for d in divisions) != NATION_2011:
        bad.append(f"the divisions add up to {sum(d['B'][0] for d in divisions):,}")
    for d in divisions:
        for sex in "BMF":
            got = [sum(z[sex][1][i] for z in zilas if fold(z["division"]) == fold(d["name"]))
                   for i in range(len(GROUPS))]
            if got != d[sex][1]:
                bad.append(f"{d['name']} {sex}: its zilas' groups are not its own")
    if bad:
        raise SystemExit(f"bangladesh_zila_ages: {len(bad)} checks failed -- " + "; ".join(bad[:5]))
    log(f"    {len(zilas)} zilas, {len(divisions)} divisions: every row's groups make "
        f"its total by sex, the zilas make their divisions group by group, and the "
        f"divisions make the census's {NATION_2011:,}")


def median_of(area: dict[str, Any]) -> float | None:
    counts = area["B"][1]
    return median_grouped([(lo, hi, n) for (lo, hi, _s), n in zip(GROUPS, counts)])


def build(rows: list[list[Any]], units2: list[dict[str, Any]],
          units1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    areas = read_rows(rows)
    check_rows(areas)
    nation = next(a for a in areas if a["level"] == 0)
    log(f"    the national median from the same groups: {median_of(nation)}")
    divisions = {a["name"]: a for a in areas if a["level"] == 1}
    zilas = [a for a in areas if a["level"] == 2]

    # Divisions first, so each zila is looked for only inside its own.
    bound1, left1, spare1 = bind({d: division_names(d) for d in divisions}, units1)
    report_binding("divisions", bound1, left1, spare1)
    if left1 or spare1:
        raise SystemExit("bangladesh_zila_ages: a division matches no single drawn unit")
    children: dict[str, set[str]] = {}
    for key, unit in bound1.items():
        children[key] = {u["id"] for u in units2 if u.get("parent") == unit["id"]}
    rows_by_key = {f"{z['division']}|{z['name']}": z for z in zilas}
    bound, left, spare = bind(
        {k: zila_names(z["name"]) for k, z in rows_by_key.items()}, units2,
        parent_of={k: z["division"] for k, z in rows_by_key.items()},
        parent_units=children)
    report_binding("zilas", bound, left, spare)
    if left or spare:
        raise SystemExit("bangladesh_zila_ages: every zila must bind to one drawn "
                         "polygon and every polygon to one zila")

    records = []
    off = []
    for key, unit in sorted(bound.items(), key=lambda kv: kv[1]["name"]):
        z = rows_by_key[key]
        drawn = unit.get("population") if isinstance(unit.get("population"), dict) else {}
        now = drawn.get("value")
        if not now or not GROWTH[0] <= now / z["B"][0] <= GROWTH[1]:
            off.append(f"{unit['name']}: 2011 {z['B'][0]:,}, drawn {now}")
            continue
        median = median_of(z)
        if median is None:
            off.append(f"{unit['name']}: the middle person is 80 or older")
            continue
        persons, (males, _m), (females, _f) = z["B"][0], z["M"], z["F"]
        label = unit["name"]
        records.append(record(
            f"BGD-AGE2011-{fold(label)}", label, level="admin2", parent="BGD",
            country="BGD", match_by="shape_id", shape_id=unit["id"],
            parent_name=next(u["name"] for u in units1 if u["id"] == unit["parent"]),
            median_age=measure(median, unit="years", year=YEAR, source=SOURCE),
            median_age_note=(
                f"Census 2011, the last Bangladeshi census to publish age by zila: "
                f"the median of {persons:,} people ({males:,} males, {females:,} "
                f"females) interpolated within the five-year age group that holds "
                f"the middle person, single years not being published by zila. The "
                f"2022 census publishes age for the eight divisions only, so a "
                f"division's 2022 median sits above its zilas' 2011 ones."),
            sources=[{"field": "median_age", "name": SOURCE, "url": dataset_url(DATASET),
                      "year": YEAR, "license": LICENCE}]))
    if off:
        raise SystemExit("bangladesh_zila_ages: refused -- " + "; ".join(off))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    log("bangladesh_zila_ages: Census 2011 five-year age groups by zila (USCB extraction)")
    import openpyxl                                 # noqa: PLC0415
    blob = http_get(workbook_url(DATASET), binary=True, cache_dir=RAW / "uscb")
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rows = sheet_rows(book, SHEET)
    records = build(rows, load_units("BGD", "admin2"), load_units("BGD", "admin1"))
    write_json(args.out or PROCESSED / OUT, records)
    log(f"  {len(records)} zilas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
