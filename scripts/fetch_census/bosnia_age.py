#!/usr/bin/env python3
"""Bosnia and Herzegovina: median age and sex ratio, Popis 2013.

The Agency for Statistics published the 2013 census's final results
("Rezultati popisa") as workbooks on popis.gov.ba. Two give age and sex:

* FR_T1 -- the population by single year of age and sex, for the country, the
  two entities and Brčko District;
* FR_T2 -- by five-year age group and sex, for every entity, canton and
  municipality.

The entities and Brčko -- the map's first level, and Republika Srpska and
Brčko again at the second -- take the median from single years; the ten
cantons from their five-year groups, interpolated within the group that holds
the middle person (the agency publishes nothing finer by canton). Sex ratio is
males per 100 females. The Agency's figures are the ones the state adopted;
Republika Srpska's institute published a different reading of the same count.

Usage:
    python -m scripts.fetch_census.bosnia_age
"""

from __future__ import annotations

import argparse
import io
import re
from collections import Counter
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json
from .balkans_common import check_sum, fold, grouped_median, median_age, shapes
from .bosnia import CANTONS, ENTITIES

OUT = "bosnia_age.json"
YEAR = 2013
BASE = "https://www.popis.gov.ba/popis2013/doc/RezultatiPopisa/BOS/"
SINGLE, GROUPED = BASE + "FR_T1_B.xlsx", BASE + "FR_T2_B.xlsx"
PAGE = "https://www.popis.gov.ba/popis2013/knjige.php?id=1"
SOURCE = ("Agency for Statistics of Bosnia and Herzegovina, Census of Population, Households "
          "and Dwellings 2013, final results, table {table}")
LICENCE = "Official statistics publication, Agency for Statistics of Bosnia and Herzegovina"
NATIONAL = 3_531_159


def rows_of(url: str) -> list[tuple[Any, ...]]:
    import openpyxl
    blob = http_get(url, binary=True, timeout=300)
    log(f"  {url.rsplit('/', 1)[-1]}: {len(blob):,} bytes")
    return [tuple(r) for r in openpyxl.load_workbook(io.BytesIO(blob), read_only=True,
                                                     data_only=True).worksheets[0].iter_rows(values_only=True)]


def text(cell: Any) -> str:
    return " ".join(str(cell if cell is not None else "").split())


def number(cell: Any) -> float:
    if isinstance(cell, (int, float)):
        return float(cell)
    t = text(cell)
    if t in ("", "-"):
        return 0.0
    return float(t.replace(".", "").replace(",", ""))


def area_key(name: str) -> str | None:
    """'federacija', 'srpska', 'brcko', or a canton's Bosnian name, folded."""
    f = fold(name)
    if f.startswith("bosnaihercegovina"):
        return "bih"
    for bosnian in list(ENTITIES) + list(CANTONS):
        if f.startswith(fold(bosnian)[:14]):
            return bosnian
    if f.startswith("federacija"):
        return "FEDERACIJA BOSNE I HERCEGOVINE"
    if f.startswith("brcko"):
        return "BRČKO DISTRIKT BOSNE I HERCEGOVINE"
    return None


def single_years(rows: list[tuple[Any, ...]]) -> dict[str, dict[str, Any]]:
    """Table FR_T1: {area: {"ages": Counter, "men", "women", "total"}}."""
    head = next(i for i, r in enumerate(rows) if text(r[0]).lower().startswith("starost"))
    areas: dict[int, str] = {}
    for j, c in enumerate(rows[head]):
        k = area_key(text(c)) if j else None
        if k:
            areas[j] = k
    out = {k: {"ages": Counter(), "men": 0.0, "women": 0.0, "total": 0.0} for k in areas.values()}
    unknown = Counter()
    for r in rows[head + 1:]:
        label = text(r[0])
        m = re.match(r"^(\d+)", label)
        # The English header row and blank rows are not ages.
        if label.lower().startswith("age") or not any(isinstance(c, (int, float)) for c in r[1:]):
            continue
        for j, k in areas.items():
            total, men, women = number(r[j]), number(r[j + 1]), number(r[j + 2])
            if label.lower().startswith(("ukupno", "total")):
                out[k]["total"] = total
                continue
            if not label:
                continue
            if m:
                out[k]["ages"][int(m.group(1))] += total
                out[k]["men"] += men
                out[k]["women"] += women
                check_sum(men + women, total, f"bosnia_age: sexes at age {label} in {k}")
            else:
                unknown[k] += total
                out[k]["men"] += men
                out[k]["women"] += women
    for k, unit in out.items():
        if unit["total"]:
            check_sum(sum(unit["ages"].values()) + unknown[k], unit["total"], f"bosnia_age: ages of {k}")
        else:
            unit["total"] = sum(unit["ages"].values()) + unknown[k]
        if unknown[k]:
            log(f"  {k}: {unknown[k]:,.0f} of unknown age, left out of the median")
    return out


def five_years(rows: list[tuple[Any, ...]]) -> dict[str, dict[str, Any]]:
    """Table FR_T2: {area: {"groups", "men", "women", "total"}} for the entities and cantons."""
    head = next(i for i, r in enumerate(rows) if any(text(c) == "0-4" for c in r))
    bands = []
    for j, c in enumerate(rows[head]):
        label = text(c)
        m, top = re.match(r"^(\d+)-(\d+)$", label), re.match(r"^(\d+)\s*(\+|i više|and over)", label)
        if m:
            bands.append((j, float(m.group(1)), float(int(m.group(2)) - int(m.group(1)) + 1)))
        elif top:
            bands.append((j, float(top.group(1)), None))
    out: dict[str, dict[str, Any]] = {}
    current = None
    for r in rows[head + 1:]:
        name, sex = text(r[0]), text(r[1]).lower()
        if name:
            current = area_key(name)
        if current is None or current in out and out[current].get("done"):
            continue
        unit = out.setdefault(current, {"groups": [], "men": None, "women": None, "total": None})
        if sex.startswith("ukupno"):
            unit["total"] = number(r[2])
            unit["groups"] = [(lo, w, number(r[j])) for j, lo, w in bands]
        elif sex.startswith("mu"):
            unit["men"] = number(r[2])
        elif sex.startswith("ž") or sex.startswith("z"):
            unit["women"] = number(r[2])
            unit["done"] = True
    return out


def build() -> list[dict[str, Any]]:
    single = single_years(rows_of(SINGLE))
    grouped = five_years(rows_of(GROUPED))
    check_sum(single["bih"]["total"], NATIONAL, "bosnia_age: the country")
    entities = [k for k in ENTITIES]
    check_sum(sum(single[k]["total"] for k in entities), NATIONAL, "bosnia_age: entities")
    for k in list(CANTONS):
        unit = grouped.get(k)
        if not unit or None in (unit["men"], unit["women"], unit["total"]):
            raise SystemExit(f"bosnia_age: FR_T2 has no full rows for {k}")
        check_sum(sum(n for _, _, n in unit["groups"]), unit["total"], f"bosnia_age: groups of {k}")
        check_sum(unit["men"] + unit["women"], unit["total"], f"bosnia_age: sexes of {k}")
    check_sum(sum(grouped[k]["total"] for k in CANTONS), single["FEDERACIJA BOSNE I HERCEGOVINE"]["total"],
              "bosnia_age: cantons against the Federation")
    log(f"  country: {NATIONAL:,}, median {median_age(single['bih']['ages'])} from single years")

    admin1 = {s["name"]: s for s in shapes("BIH", "admin1")}
    admin2 = {fold(s["name"]): s for s in shapes("BIH", "admin2")}
    records = []

    def rec(level: str, shape: dict[str, Any], median: float, men: float, women: float,
            table: str, note: str) -> dict[str, Any]:
        src = SOURCE.format(table=table)
        return record(f"BIH-2013-age-{level}-{fold(shape['name'])}", shape["name"], level=level,
                      parent="BIH", country="BIH", match_by="shape_id", shape_id=shape["id"],
                      median_age=measure(median, unit="years", year=YEAR, source=src),
                      median_age_note=note,
                      sex_ratio=measure(round(100 * men / women, 1), unit="males_per_100_females",
                                        year=YEAR, source=src),
                      sources=[{"field": "median_age/sex_ratio", "name": src,
                                "url": SINGLE if table == "FR_T1" else GROUPED, "page": PAGE,
                                "year": YEAR, "license": LICENCE}])

    one = ("Interpolated within the single year of age that holds the middle person, from the "
           "census's population by single year of age and sex (FR_T1).")
    five = ("Interpolated within the five-year age group that holds the middle person, from the "
            "census's population by age group and sex (FR_T2): the agency publishes nothing finer "
            "by canton.")
    for bosnian, (english, aliases) in ENTITIES.items():
        unit = single[bosnian]
        median = median_age(unit["ages"])
        records.append(rec("admin1", admin1[english], median, unit["men"], unit["women"], "FR_T1", one))
        for name in [english] + aliases:
            shape = admin2.get(fold(name))
            if shape:
                records.append(rec("admin2", shape, median, unit["men"], unit["women"], "FR_T1", one))
                break
        log(f"  {english}: median {median}")
    for bosnian, english in CANTONS.items():
        unit = grouped[bosnian]
        shape = admin2.get(fold(english))
        if shape is None:
            raise SystemExit(f"bosnia_age: no polygon named {english}")
        median = grouped_median(unit["groups"])
        records.append(rec("admin2", shape, median, unit["men"], unit["women"], "FR_T2", five))
        log(f"  {english}: median {median}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("bosnia_age: Popis 2013, age and sex")
    records = build()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
