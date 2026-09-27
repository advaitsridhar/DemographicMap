#!/usr/bin/env python3
"""Czechia: population, median age and sex ratio by okres, from ČSÚ open data.

ČSÚ publishes "Obyvatelstvo podle jednotek věku a pohlaví" (dataset 130181)
once a year as a long CSV: the population on 31 December by sex and single
year of age for the country, the cohesion regions, the kraje, the 77 okresy
and the ORP districts, each row saying which (``uzemi_cis`` 97, 99, 100, 101,
65). The okresy (101) are read; the kraje (100) and the country (97) are the
checks.

The okres names and the boundary file's English spellings for the city
districts ("Prague-East", "Brno-City") are the ones the census reader
(``czechia.py``) already declares, and each okres is bound within the kraj
that reader files it under.

Usage:
    python -m scripts.fetch_census.czechia_ages [--year 2024]
"""

from __future__ import annotations

import argparse
import csv
import io
from collections import Counter
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json
from .central_ages import (
    age_sex_fields, check_national_median, check_sum, fold, report_unbound, units,
)
from .czechia import KRAJ_OF, OKRES_ALIASES

FILES = {
    2024: "https://csu.gov.cz/docs/107508/825ad7ae-f155-50e1-7d9f-1706bd7ce4c2/130181-25data2024.csv",
    2023: "https://csu.gov.cz/docs/107508/bc8f2d41-4d3a-a8f4-02fa-800d9cd27266/130181-24data2023.csv",
}
PAGE = "https://data.gov.cz/ (ČSÚ dataset 130181, Obyvatelstvo podle jednotek věku a pohlaví)"
SOURCE = "Czech Statistical Office (ČSÚ), Obyvatelstvo podle jednotek věku a pohlaví, {year} (130181)"
LICENCE = "ČSÚ open data (free reuse with attribution)"
OUT = PROCESSED / "czechia_okres_age.json"
PRAGUE = {"Praha", "Hlavní město Praha"}
EXPECTED = 77


def read(year: int) -> dict[tuple[str, str], dict[str, Any]]:
    """{(uzemi_cis, name): {"total", "m": Counter, "f": Counter}}."""
    blob = http_get(FILES[year], binary=True, timeout=600)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    periods = set()
    for row in csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))):
        periods.add(row["obdobi"])
        key = (row["uzemi_cis"], row["uzemi_txt"].strip())
        unit = out.setdefault(key, {"total": None, "m": Counter(), "f": Counter()})
        value = int(float(row["hodnota"]))
        age, sex = row["vek_txt"].strip(), row["pohlavi_kod"].strip()
        if not age:
            if not sex:
                unit["total"] = value
            continue
        if not sex:
            continue
        years = int("".join(ch for ch in age if ch.isdigit()))
        unit["m" if sex == "1" else "f"][years] += value
    if periods != {f"{year}-12-31"}:
        raise SystemExit(f"czechia_ages: the file holds {sorted(periods)}, not 31 December {year}")
    return out


def build(year: int) -> list[dict[str, Any]]:
    log(f"czechia_ages: ČSÚ 130181, 31 December {year}")
    table = read(year)
    okresy = {name: u for (cis, name), u in table.items() if cis == "101"}
    kraje = {name: u for (cis, name), u in table.items() if cis == "100"}
    country = next(u for (cis, _), u in table.items() if cis == "97")
    log(f"  {len(okresy)} okresy, {len(kraje)} kraje, Czechia {country['total']:,}")
    for name, unit in [*okresy.items(), ("Česko", country)]:
        made = sum(unit["m"].values()) + sum(unit["f"].values())
        if made != unit["total"]:
            raise SystemExit(f"czechia_ages: {name}: men and women by age make {made:,}, "
                             f"the total is {unit['total']:,}")
    check_sum((u["total"] for u in okresy.values()), country["total"], "okresy against Czechia")
    for kraj in sorted({KRAJ_OF[o if o not in PRAGUE else "Praha"] for o in okresy}):
        parts = [u["total"] for o, u in okresy.items()
                 if KRAJ_OF[o if o not in PRAGUE else "Praha"] == kraj]
        check_sum(parts, kraje[kraj]["total"], f"okresy against {kraj}")
    both = Counter(country["m"])
    both.update(country["f"])
    check_national_median(both, "CZ", year + 1)

    shapes = units("CZE", "admin2")
    parents = {u["id"]: u["name"] for u in units("CZE", "admin1")}
    by_key: dict[str, list[dict[str, Any]]] = {}
    for shape in shapes:
        by_key.setdefault(fold(shape["name"]), []).append(shape)
    records, unbound, used = [], [], set()
    source = SOURCE.format(year=year)
    for name, unit in sorted(okresy.items()):
        office = "Praha" if name in PRAGUE else name
        kraj = KRAJ_OF.get(office)
        drawn = (OKRES_ALIASES.get(office) or [office])[0]
        hits = [s for s in by_key.get(fold(drawn), []) if parents.get(s["parent"]) == kraj]
        if len(hits) != 1 or hits[0]["id"] in used:
            unbound.append(f"{name} ({kraj})")
            continue
        shape = hits[0]
        used.add(shape["id"])
        fields = age_sex_fields(
            unit["m"], unit["f"], year=year, source=source, total=unit["total"],
            median_note=(f"Interpolated within the single year of age that holds the middle "
                         f"person, from ČSÚ's count of the okres's population on 31 December "
                         f"{year} by sex and single year of age."),
            ratio_note=f"Males per 100 females in the okres's population on 31 December {year}.")
        records.append(record(
            f"CZE-OKRES-{fold(office)}", office, level="admin2", parent=shape["parent"],
            parent_name=kraj, country="CZE", aliases=[shape["name"]] if shape["name"] != office else [],
            match_by="shape_id", shape_id=shape["id"],
            sources=[{"field": "population/median_age/sex_ratio", "name": source, "url": FILES[year],
                      "license": LICENCE, "year": year}],
            **fields))
    report_unbound("czechia_ages", unbound, [s["name"] for s in shapes if s["id"] not in used])
    if unbound or len(records) != EXPECTED:
        raise SystemExit(f"czechia_ages: {len(records)} of {EXPECTED} okresy bound")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, default=2024, choices=sorted(FILES))
    args = ap.parse_args()
    records = build(args.year)
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
