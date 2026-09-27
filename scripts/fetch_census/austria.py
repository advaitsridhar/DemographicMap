#!/usr/bin/env python3
"""Austria: population, median age and sex ratio by politischer Bezirk.

Statistik Austria's open data portal publishes the population on 1 January
of every year since 2002 as one long CSV, ``OGD_bevstandjbab2002_BevStand_
<year>``: one row per year, sex, municipality and single year of age (0 to
99, then 100 and over), the municipalities in the boundaries of the year
published. The dataset's own title for its geography says what it is for --
"Gemeinde (Vergröberung über Politischen Bezirk)" -- and a municipality's
five-digit code opens with its district's three, so the districts are sums of
municipalities with nothing to join. Vienna's 23 Gemeindebezirke (901 to 923)
are one district on this map, "Wien(Stadt)", and are summed as such.

**Vintage.** The map draws 94 districts: the Styrian mergers of 2012 and 2013
(Bruck-Mürzzuschlag, Murtal, Hartberg-Fürstenfeld, Südoststeiermark) have
happened, and Wien-Umgebung, dissolved on 1 January 2017, is not drawn. That
is the division Statistik Austria still publishes in its register of
political districts (``polbezirke.csv``), so the current year's figures fit
every polygon. The names come from that register and are bound to the map's
by name, one to one, or the run stops.

**Checks.** Men and women make every district; the districts make each Land
and the country; and the country's median recomputed from the same single
years lands within 0.3 years of Eurostat's for Austria on the same date.

Religion, language and ethnicity are not here: the register-based census
asks none of them (see NOT_COLLECTED_POLICY for AUT).

Usage:
    python -m scripts.fetch_census.austria [--year 2026]
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from collections import Counter
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json
from .central_ages import (
    age_sex_fields, check_national_median, check_sum, fold, report_unbound, units,
)

PORTAL = "https://data.statistik.gv.at/web/meta.jsp?dataset=OGD_bevstandjbab2002_BevStand_{year}"
DATA = "https://data.statistik.gv.at/data/OGD_bevstandjbab2002_BevStand_{year}{part}.csv"
REGISTER = "https://www.statistik.at/verzeichnis/reglisten/polbezirke.csv"
SOURCE = ("Statistik Austria, Bevölkerung zu Jahresbeginn nach Alter, Geschlecht und "
          "Gemeinde (OGD_bevstandjbab2002_BevStand_{year})")
LICENCE = "CC BY 4.0 (Statistik Austria open data)"
OUT = PROCESSED / "austria_bezirk.json"
VIENNA = "Wien(Stadt)"
LAENDER = {"1": "Burgenland", "2": "Kärnten", "3": "Niederösterreich", "4": "Oberösterreich",
           "5": "Salzburg", "6": "Steiermark", "7": "Tirol", "8": "Vorarlberg", "9": "Wien"}
EXPECTED = 94


def table(year: int, part: str = "") -> list[dict[str, str]]:
    blob = http_get(DATA.format(year=year, part=part), binary=True, timeout=600)
    return list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig")), delimiter=";"))


def ages_of(year: int) -> dict[str, int]:
    """GALTEJ112 code -> the single year it stands for; the last is the open top."""
    out: dict[str, int] = {}
    for row in table(year, "_C-GALTEJ112-0"):
        m = re.match(r"(\d+)", row["name"])
        if not m:
            raise SystemExit(f"austria: an age label with no number: {row['name']!r}")
        out[row["code"]] = int(m.group(1))
    if sorted(out.values()) != list(range(101)):
        raise SystemExit(f"austria: ages run {min(out.values())}..{max(out.values())} "
                         f"in {len(out)} classes, not 0..100+")
    return out


def districts() -> dict[str, str]:
    """Political district code -> name, from Statistik Austria's register."""
    blob = http_get(REGISTER, binary=True)
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = blob.decode("cp1252")
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if "Kennziffer pol. Bezirk" in line)
    out = {}
    for row in csv.reader(lines[start + 1:], delimiter=";"):
        if len(row) >= 4 and row[2].strip().isdigit():
            out[row[2].strip()] = row[3].strip()
    return out


def build(year: int) -> list[dict[str, Any]]:
    log(f"austria: population on 1 January {year} by municipality, sex and single year of age")
    age = ages_of(year)
    names = districts()
    source = SOURCE.format(year=year)
    males: dict[str, Counter] = {}
    females: dict[str, Counter] = {}
    rows = table(year)
    seen_years = set()
    for row in rows:
        seen_years.add(row["C-A10-0"])
        commune = row["C-GRGEMAKT-0"].split("-")[-1]
        code = commune[:3]
        key = VIENNA if code.startswith("9") else code
        sex = row["C-C11-0"]
        target = males if sex == "C11-1" else females if sex == "C11-2" else None
        if target is None:
            raise SystemExit(f"austria: a sex code this reader does not know: {sex!r}")
        target.setdefault(key, Counter())[age[row["C-GALTEJ112-0"]]] += int(row["F-ISIS-1"])
    if seen_years != {f"A10-{year}"}:
        raise SystemExit(f"austria: the file holds {sorted(seen_years)}, not {year} alone")
    national_m = sum((c for c in males.values()), Counter())
    national_f = sum((c for c in females.values()), Counter())
    national = sum(national_m.values()) + sum(national_f.values())
    log(f"  {len(rows):,} rows, {len(males)} districts, {national:,} people")

    # Each Land is its districts; the country is its Laender.
    by_land: dict[str, float] = {}
    for key in males:
        land = "9" if key == VIENNA else key[0]
        by_land[land] = by_land.get(land, 0) + sum(males[key].values()) + sum(females[key].values())
    check_sum(by_land.values(), national, "Laender against Austria")
    both = Counter(national_m)
    both.update(national_f)
    check_national_median(both, "AT", year)

    shapes = units("AUT", "admin2")
    parents = {u["id"]: u["name"] for u in units("AUT", "admin1")}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for shape in shapes:
        by_name.setdefault(fold(shape["name"]), []).append(shape)
    records, unbound, used = [], [], set()
    for key in sorted(males):
        name = VIENNA if key == VIENNA else names.get(key)
        if name is None:
            raise SystemExit(f"austria: district {key} is not in Statistik Austria's register")
        hits = by_name.get(fold(name), [])
        land = LAENDER["9" if key == VIENNA else key[0]]
        hits = [h for h in hits if parents.get(h["parent"]) == land] or hits
        if len(hits) != 1 or hits[0]["id"] in used:
            unbound.append(f"{name} ({key})")
            continue
        shape = hits[0]
        used.add(shape["id"])
        fields = age_sex_fields(
            males[key], females[key], year=year, source=source,
            median_note=(f"Interpolated within the single year of age that holds the middle "
                         f"person, from Statistik Austria's count of the district's residents on "
                         f"1 January {year} by single year of age (0 to 99, then 100 and over), "
                         f"summed from its municipalities."
                         + (" Vienna's 23 Gemeindebezirke are summed as the one district the "
                            "map draws." if key == VIENNA else "")),
            ratio_note=f"Males per 100 females among the district's residents on 1 January {year}.")
        records.append(record(
            f"AUT-PB-{'900' if key == VIENNA else key}", shape["name"], level="admin2",
            parent=shape["parent"], parent_name=land, country="AUT",
            codes={"statistik_austria_pol_bezirk": "900" if key == VIENNA else key},
            match_by="shape_id", shape_id=shape["id"],
            sources=[{"field": "population/median_age/sex_ratio", "name": source,
                      "url": PORTAL.format(year=year), "license": LICENCE, "year": year}],
            **fields))
    report_unbound("austria", unbound, [s["name"] for s in shapes if s["id"] not in used])
    if unbound or len(records) != EXPECTED:
        raise SystemExit(f"austria: {len(records)} districts bound, {EXPECTED} expected")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, default=2026)
    args = ap.parse_args()
    records = build(args.year)
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
