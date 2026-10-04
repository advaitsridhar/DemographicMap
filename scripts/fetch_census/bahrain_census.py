#!/usr/bin/env python3
"""Bahrain's four governorates in the 2020 census: people, sex and nationality.

The Information & eGovernment Authority publishes the 2020 census's tables on
the kingdom's open-data portal (data.gov.bh, OpenDataSoft). Three are read:

* *Population by Governorate, Nationality Groups and Sex - Census 2020* --
  every governorate's people by sex in eight nationality groups (Bahraini,
  GCC, other Arab, Asian, African, European, North American, other). This is
  what is written.
* *Population by Governorate, Nationality and Sex - Census 2020* -- the same
  people as Bahraini and non-Bahraini, a second tabulation the first must
  agree with, governorate by governorate.
* *Population by Age Groups, Nationality and Sex - Census 2020* -- the whole
  kingdom by age, whose total the four governorates must make.

**What is written**, for each governorate: its 2020 census population, males
per hundred females, and its people by nationality group on the ethnicity
field (``ethnicity_basis`` "nationality"; the census asks no ethnic question,
and nationality is what it counts -- the owner's decision of 19 September
2026). The map draws the four governorates at both levels under one id, and
the build copies a first-level figure onto its second-level twin.

**What is not, and why.** The portal publishes age groups and religion for
the whole kingdom only (by nationality and sex), so a governorate's median
age and religion are not published; each says so.

**Checks** (any failure stops the run and nothing is written): every
governorate has every group of both sexes once; the two tabulations agree
on every governorate's Bahrainis and non-Bahrainis by sex; the governorates
make the kingdom's total in the age table; every drawn governorate is bound
to one census governorate and none twice.

Usage:
    python -m scripts.fetch_census.bahrain_census
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .west_asia_common import check, key, ods_records, sex_ratio, units

ISO3 = "BHR"
OUT = "bahrain_census.json"
BASE = "https://www.data.gov.bh"
GROUPS = "population-by-governorate-nationality-groups-and-sex-census-2020"
TOTALS = "population-by-governorate-nationality-and-sex-census-2020"
AGES = "population-by-age-groups-nationality-and-sex-census-2020"
RELIGION = "population-by-religion-nationality-and-sex-census-2020"
YEAR = 2020
SOURCE = ("Information & eGovernment Authority (Bahrain), Census 2020: Population by "
          "Governorate, Nationality Groups and Sex")
URL = f"{BASE}/explore/dataset/{GROUPS}/"
LICENCE = "Bahrain Open Data Portal terms (open government data)"
DECISION = "19 September 2026"
GOVERNORATES = ("Capital", "Muharraq", "Northern", "Southern")
SEXES = ("Male", "Female")
# The census's nationality groups, as the map writes them. GCC nationals are
# the other five Gulf states' citizens; the portal's Arabic is "دول مجلس التعاون".
LABELS = {
    "Bahraini": "Bahraini",
    "Gulf Co-operative Countries": "GCC nationals",
    "Other Arabs": "Other Arab nationalities",
    "Asian": "Asian nationalities",
    "African": "African nationalities",
    "European": "European nationalities",
    "North American": "North American nationalities",
    "Others": "Other nationalities",
}


def cells(rows: list[dict[str, Any]], what: str, fields: tuple[str, str, str]
          ) -> dict[tuple[str, str, str], float]:
    """(place, category, sex) -> people, every cell once, from the named fields."""
    check(bool(rows), f"bahrain_census: {what}: no records")
    for name in fields + ("population",):
        check(name in rows[0], f"bahrain_census: {what}: no field {name!r} in {sorted(rows[0])}")
    out: dict[tuple[str, str, str], float] = {}
    for row in rows:
        where = tuple(str(row[f]).strip() for f in fields)
        check(where not in out, f"bahrain_census: {what}: {where} twice")
        value = row["population"]
        check(isinstance(value, (int, float)) and not isinstance(value, bool),
              f"bahrain_census: {what}: {where}: {value!r}")
        out[where] = float(value)
    return out


def build(groups_rows: list[dict[str, Any]], totals_rows: list[dict[str, Any]],
          ages_rows: list[dict[str, Any]], admin1: list[dict[str, Any]]
          ) -> list[dict[str, Any]]:
    groups = cells(groups_rows, GROUPS, ("governorate", "nationality_groups", "sex"))
    check({g for g, _n, _s in groups} == set(GOVERNORATES),
          f"bahrain_census: governorates {sorted({g for g, _n, _s in groups})}")
    check({n for _g, n, _s in groups} == set(LABELS),
          f"bahrain_census: nationality groups {sorted({n for _g, n, _s in groups})}")
    check({s for _g, _n, s in groups} == set(SEXES),
          f"bahrain_census: sexes {sorted({s for _g, _n, s in groups})}")
    check(len(groups) == len(GOVERNORATES) * len(LABELS) * len(SEXES),
          f"bahrain_census: {len(groups)} cells, not "
          f"{len(GOVERNORATES) * len(LABELS) * len(SEXES)}")
    # The second tabulation: Bahraini and non-Bahraini, by governorate and sex.
    totals = cells(totals_rows, TOTALS, ("governorate", "nationality", "sex"))
    check(len(totals) == len(GOVERNORATES) * 2 * len(SEXES),
          f"bahrain_census: {TOTALS}: {len(totals)} cells")
    for gov in GOVERNORATES:
        for sex in SEXES:
            own = groups[(gov, "Bahraini", sex)]
            others = sum(v for (g, n, s), v in groups.items()
                         if g == gov and s == sex and n != "Bahraini")
            check(totals.get((gov, "Bahraini", sex)) == own,
                  f"bahrain_census: {gov} {sex} Bahraini: {own:,.0f} against "
                  f"{totals.get((gov, 'Bahraini', sex))} in {TOTALS}")
            check(totals.get((gov, "Non-Bahraini", sex)) == others,
                  f"bahrain_census: {gov} {sex} non-Bahraini: {others:,.0f} against "
                  f"{totals.get((gov, 'Non-Bahraini', sex))} in {TOTALS}")
    # The kingdom by age: a third tabulation the governorates must make.
    ages = cells(ages_rows, AGES, ("age_groups", "nationality", "sex"))
    kingdom = sum(ages.values())
    made = sum(groups.values())
    check(round(made) == round(kingdom),
          f"bahrain_census: governorates make {made:,.0f}, the age table {kingdom:,.0f}")
    log(f"  census 2020: {made:,.0f} people in {len(GOVERNORATES)} governorates")

    rows: list[dict[str, Any]] = []
    by_key = {key(g): g for g in GOVERNORATES}
    bound: dict[str, str] = {}
    for unit in admin1:
        label = unit["name"].replace("Governorate", "").strip()
        gov = by_key.get(key(label))
        check(gov is not None, f"bahrain_census: no census governorate for {unit['name']}")
        check(gov not in bound.values(), f"bahrain_census: {gov} bound twice")
        bound[unit["id"]] = gov
    check(len(bound) == len(GOVERNORATES), f"bahrain_census: {len(bound)} governorates drawn")
    source = [{"field": "population/sex_ratio/ethnicity", "name": SOURCE, "url": URL,
               "year": YEAR, "license": LICENCE}]
    no_age = gap(NOT_AVAILABLE, (
        "Bahrain's 2020 census publishes people by age group for the whole kingdom only "
        f"(data.gov.bh: {AGES}); by governorate it publishes only those aged 15 and over, "
        "by sex and marital status, from which no median of everyone can be taken."))
    no_religion = gap(NOT_AVAILABLE, (
        "Bahrain's 2020 census counts religion, but publishes it for the whole kingdom "
        f"only, by nationality and sex (data.gov.bh: {RELIGION}), not by governorate."))
    for unit in admin1:
        gov = bound[unit["id"]]
        mine = {(n, s): v for (g, n, s), v in groups.items() if g == gov}
        men = sum(v for (_n, s), v in mine.items() if s == "Male")
        women = sum(v for (_n, s), v in mine.items() if s == "Female")
        by_group: dict[str, float] = defaultdict(float)
        for (n, _s), v in mine.items():
            by_group[LABELS[n]] += v
        total = men + women
        population = measure(total, year=YEAR, source=SOURCE)
        population["note"] = (f"The 2020 census count: {men:,.0f} men and {women:,.0f} "
                              f"women.")
        rows.append(record(
            f"BHR-CEN2020-{gov}", unit["name"], level="admin1", parent=ISO3, country=ISO3,
            match_by="shape_id", shape_id=unit["id"],
            aliases=[f"{gov} Governorate"] if f"{gov} Governorate" != unit["name"] else None,
            population=population,
            sex_ratio=sex_ratio(men, women, year=YEAR, source=SOURCE),
            sex_ratio_note=f"Males per 100 females in the 2020 census: {men:,.0f} men and "
                           f"{women:,.0f} women.",
            ethnicity=shares(dict(by_group), total=total),
            ethnicity_year=YEAR, ethnicity_basis="nationality",
            ethnicity_note=(
                "Nationality, not ethnicity: the 2020 census counts each person's "
                "nationality in eight groups and asks no ethnic question. Carried on this "
                f"field under the owner's decision of {DECISION}. GCC nationals are "
                "citizens of the other Gulf Cooperation Council states; the Arab, Asian, "
                "African, European and North American groups are other countries' "
                "nationals by region."),
            median_age=no_age, religion=no_religion,
            sources=source))
    return rows


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    rows = build(ods_records(BASE, GROUPS), ods_records(BASE, TOTALS),
                 ods_records(BASE, AGES), units(ISO3, "admin1"))
    write_json(PROCESSED / OUT, rows)
    log(f"  wrote {OUT} ({len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
