#!/usr/bin/env python3
"""Saudi Arabia's thirteen regions in the 2022 census: people, sex and median age.

The General Authority for Statistics (GASTAT) counted the kingdom on 10 May
2022. Its census portal (portal.saudicensus.sa) does not resolve from the
runner, and GASTAT's own statistics pages link no table files; the census's
count of every region by sex and five-year age group reaches the map through
OCHA's Common Operational Dataset (``cod-ps-sau``, compiled with UNFPA from
GASTAT's census, CC BY-IGO), whose methodology line reads "Census".

**What is written**, for each region: its census population, males per
hundred females, and the median age, interpolated within the five-year group
that holds the middle person.

**Binding.** OCHA names a region by its own romanisation ("Makkah
Al-Mukarramah", "Hail"); the map's labels are the boundary file's
("Makkah Region", "Hayel Region"). A region is bound when the two names
agree once the word "Region" and the article are set aside, or by a declared
alias below; every drawn region must be bound, and none twice.

**Checks** (any failure stops the run and nothing is written): women and men
make every region's total; the age groups make it; the regions make the
kingdom's row.

Usage:
    python -m scripts.fetch_census.saudi_census
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, http_json, log, measure, record,
                      write_json)
from .west_asia_common import HDX_API, check, key, median_age, sex_ratio, units

ISO3 = "SAU"
OUT = "saudi_census.json"
DATASET = "cod-ps-sau"
YEAR = 2022
SOURCE = ("General Authority for Statistics (Saudi Arabia), Census 2022, by region, sex "
          "and five-year age group, as compiled in OCHA's COD-PS (cod-ps-sau)")
URL = f"https://data.humdata.org/dataset/{DATASET}"
LICENCE = "CC BY-IGO, published via HDX"
# OCHA's name -> the boundary file's label, where the two romanisations
# share no spelling once the article and "Region" are set aside.
ALIASES = {
    "hail": "Hayel Region",
    "hayel": "Hayel Region",
    "makkahalmukarramah": "Makkah Region",
    "madinahalmunawwarah": "Al Madinah Region",
    "almadinahalmunawwarah": "Al Madinah Region",
    "jizan": "Jazan Region",
    "albaha": "Al Bahah Region",
    "easternprovince": "Eastern Region",
    "ashsharqiyah": "Eastern Region",
    "alhududashshamaliyah": "Northern Borders Region",
    "alquassim": "Al-Qassim Region",
    "alqasim": "Al-Qassim Region",
}
# The census's count of the kingdom: GASTAT, Saudi Census 2022 results
# (published 31 May 2023), 32,175,224 people. The regions must make it.
NATIONAL = 32_175_224
# The census asks citizenship, which the owner's decision of 19 September 2026
# lets stand on the ethnicity field; GASTAT's table of it by region is out of
# reach, so the field says that rather than "not collected" (shared.patch
# drops the SAU ethnicity policy that said so).
NATIONALITY_WHY = (
    "Saudi Arabia's 2022 census asks citizenship (Saudi or not, and which country), not "
    "ethnicity; citizenship may stand on this field, but no table of it by region could be "
    "read: on 9 October 2026 the census portal's host (portal.saudicensus.sa) did not resolve "
    "from the runner, GASTAT's census page on stats.gov.sa (statistics?index=119025) links no "
    "table file, its content being drawn by script, the Saudi open-data portal "
    "(open.data.gov.sa) did not answer, and OCHA's tables of the census carry region, sex and "
    "age only.")
AGE = re.compile(r"^([TFM])_(\d{1,3})_(\d{1,3})$", re.I)
OPEN = re.compile(r"^([TFM])_(\d{1,3})_?plus$", re.I)
SLACK = 0.001


def plain(name: str) -> str:
    """A region's name without "Region" and the article, folded."""
    text = re.sub(r"\b(region|province|emirate)\b", " ", str(name), flags=re.I)
    return key(text)


def compact(name: str) -> str:
    return re.sub(r"[^a-z]", "", str(name).lower())


def table(package: dict[str, Any]) -> list[dict[str, str]]:
    """The first-level table: the CSV named for adm1."""
    found = [r for r in package.get("resources") or ()
             if re.search(r"adm(?:pop)?_?adm1.*\.csv$|admpop_adm1", str(r.get("name") or ""), re.I)
             and str(r.get("name") or "").lower().endswith(".csv")]
    check(len(found) == 1, f"saudi_census: {len(found)} first-level CSVs in {DATASET}: "
                           + ", ".join(str(r.get("name")) for r in package.get("resources") or ()))
    text = http_get(str(found[0]["url"]), cache=False)
    assert isinstance(text, str)
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(io.StringIO(text.lstrip("﻿")))]


def number(text: str) -> float | None:
    try:
        return float(str(text).replace(",", ""))
    except ValueError:
        return None


def ages(row: dict[str, str]) -> list[tuple[int, int | None, float]]:
    """Both sexes' five-year groups, from 0 without a gap; the last may be open."""
    groups: list[tuple[int, int | None, float]] = []
    for col, cell in row.items():
        closed, opened = AGE.match(col), OPEN.match(col)
        m = closed or opened
        if not m or m.group(1).upper() != "T":
            continue
        people = number(cell)
        check(people is not None, f"saudi_census: {row.get('ADM1_EN')}: no count in {col}")
        if closed:
            groups.append((int(closed.group(2)), int(closed.group(3)), people))
        else:
            groups.append((int(opened.group(2)), None, people))
    groups.sort(key=lambda g: g[0])
    edge = 0
    for low, high, _n in groups:
        check(low == edge, f"saudi_census: {row.get('ADM1_EN')}: age groups break at {edge}")
        edge = high + 1 if high is not None else -1
    check(len(groups) >= 15, f"saudi_census: {row.get('ADM1_EN')}: {len(groups)} age groups")
    return groups


def build(rows: list[dict[str, str]], admin1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    years = {r.get("year") for r in rows}
    check(years == {str(YEAR)}, f"saudi_census: reference years {years}")
    labels = {u["name"]: u for u in admin1}
    by_plain: dict[str, list[str]] = {}
    for label in labels:
        by_plain.setdefault(plain(label), []).append(label)
    out: list[dict[str, Any]] = []
    bound: dict[str, str] = {}
    made = 0.0
    for row in rows:
        name, pcode = row.get("ADM1_EN", ""), row.get("ADM1_PCODE", "")
        women, men, total = (number(row.get(c, "")) for c in ("F_TL", "M_TL", "T_TL"))
        check(None not in (women, men, total), f"saudi_census: {name}: no totals")
        check(abs(women + men - total) <= max(1.0, SLACK * total),
              f"saudi_census: {name}: women {women:,.0f} and men {men:,.0f} do not make "
              f"{total:,.0f}")
        groups = ages(row)
        aged = sum(n for _a, _b, n in groups)
        check(abs(aged - total) <= max(1.0, SLACK * total),
              f"saudi_census: {name}: age groups make {aged:,.0f}, not {total:,.0f}")
        made += total
        label = ALIASES.get(compact(name))
        if label is None:
            hits = by_plain.get(plain(name), [])
            if not hits:
                hits = [lb for p, lbs in by_plain.items() for lb in lbs
                        if p and (p.startswith(plain(name)) or plain(name).startswith(p))]
            check(len(hits) == 1, f"saudi_census: {name} ({pcode}) matches drawn {hits}")
            label = hits[0]
        check(label in labels, f"saudi_census: alias {label} is not drawn")
        check(label not in bound.values(), f"saudi_census: {label} bound twice")
        bound[pcode] = label
        unit = labels[label]
        population = measure(total, year=YEAR, source=SOURCE)
        population["note"] = "The 2022 census count (10 May 2022)."
        out.append(record(
            f"SAU-CEN2022-{pcode}", label, level="admin1", parent=ISO3, country=ISO3,
            match_by="shape_id", shape_id=unit["id"], codes={"pcode": pcode},
            aliases=[name] if name != label else None,
            population=population,
            sex_ratio=sex_ratio(men, women, year=YEAR, source=SOURCE),
            sex_ratio_note=(f"Males per 100 females in the 2022 census: {men:,.0f} men and "
                            f"{women:,.0f} women."),
            median_age=median_age(groups, year=YEAR, source=SOURCE),
            median_age_note=("Interpolated within the five-year age group holding the middle "
                             "person, from the 2022 census's count of the region by five-year "
                             "age group."),
            ethnicity=gap(NOT_AVAILABLE, NATIONALITY_WHY),
            sources=[{"field": "population/median_age/sex_ratio", "name": SOURCE, "url": URL,
                      "year": YEAR, "license": LICENCE}]))
        log(f"    {name} ({pcode}) -> {label}: {total:,.0f}, median "
            f"{out[-1]['median_age']['value']}, {out[-1]['sex_ratio']['value']} M/100F")
    check(len(bound) == len(admin1), f"saudi_census: {len(bound)} of {len(admin1)} regions bound: "
                                     f"{sorted(set(labels) - set(bound.values()))} left")
    check(round(made) == NATIONAL, f"saudi_census: the regions make {made:,.0f}, the census "
                                   f"counted {NATIONAL:,}")
    log(f"  census 2022: {made:,.0f} people in {len(out)} regions")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    package = http_json(f"{HDX_API}/package_show?id={DATASET}", cache=False)["result"]
    method = str(package.get("methodology") or package.get("methodology_other") or "")
    log(f"  {DATASET}: licence {package.get('license_id')}, methodology {method[:80]!r}")
    check(package.get("license_id") in ("cc-by-igo", "cc-by"),
          f"saudi_census: licence {package.get('license_id')}")
    rows = build(table(package), units(ISO3, "admin1"))
    write_json(PROCESSED / OUT, rows)
    log(f"  wrote {OUT} ({len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
