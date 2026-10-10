#!/usr/bin/env python3
"""Syria's 2004 census by governorate and district: age, sex and nationality.

Syria last counted its people on 22 September 2004. The Central Bureau of
Statistics published the count by governorate, district (mantiqa) and
sub-district (nahiya) in its *2004 Census Population Bulletin -- Man and
Nah* (2006): everyone by sex and five-year age group (Table 2) and by
nationality (Table 3). The US Census Bureau transcribed both, unit by unit,
into its subnational workbook for HDX
(``syria-subnational-boundaries-and-tabular-data``, CC BY), each row keyed
by the OCHA P-code of its unit -- SY0204 is I'zaz district -- and that code
is what binds it here: the map's districts are OCHA's (COD-AB, ``cod-ab-syr``),
so each drawn label is found among OCHA's districts of the same governorate
and its P-code is the census row's. The same workbook relays the Bureau's
estimate of each governorate's people on 1 January 2011 (*Statistical
Abstract 2011*, chapter 2, table 2), the last before the war.

**What is written.**

* Every district (61): its 2004 population, median age and males per
  hundred females, and its people by nationality.
* Every governorate (14): the same median, ratio and nationality, and the
  Bureau's 1 January 2011 estimate as its population -- newer than the
  census and from the same office, where the map's figure was Wikipedia's or
  Wikidata's.

**Nationality is not ethnicity.** The 2004 census asked nationality and no
ethnic question (Syria's census has never asked one; religion was last
asked in 1960). By the owner's decision of 19 September 2026 a state's count
of nationality is carried on the ethnicity field under
``ethnicity_basis: "nationality"``, as Japan's and Korea's are, and each note
says it is citizenship. "Palestinian" here is Palestinian refugees and their
descendants, who are not Syrian citizens.

The citizens' row is written "Syrian citizens", a label that names no
people, and filed as a nationality: Syria's citizens are Arab, Kurd,
Armenian, Assyrian and Turkmen alike, and a row read as "Syrian" would be
coloured Arab, showing Kurdish Afrin and Ain al-Arab as wholly Arab, which
the census never said. The census's "American" and "Australian" groups
stand beside its European, Asian and African ones -- continents, not
countries -- so they are written "Nationalities of the Americas" and
"Oceanian nationalities", which no settler-nation identity can be read
into.

**Language** is in no table the census published (the Bureau's workbook
reproduces age, sex and nationality, and its data dictionary cites no other
table), so every unit says so.

**Quneitra.** The census enumerated the part of Quneitra governorate under
Syrian administration. The boundary file draws the whole governorate,
Golan Heights included, as Syria's Quneitra and Al Fiq districts; the
Heights have been under Israeli administration since 1967 and their people
were not counted by Syria (Israel's Central Bureau of Statistics counts them
in its Golan sub-district, which this map does not place on these shapes).
The two districts' and the governorate's notes say so.

**Checks** (any failure stops the run and nothing is written): every row's
age groups make its total and its sexes make it too; every governorate's
districts make the governorate and the governorates the country, for ages
and for nationality; every nationality row's groups make its own total;
each drawn district is bound to exactly one census row and none twice.

Usage:
    python -m scripts.fetch_census.syria_census
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any

from . import uscb
from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .west_asia_common import (age_groups, bind_by_gazetteer, check, count, gazetteer,
                               hdx_resource, median_age, parents_by_id, report,
                               sex_ratio, units, uscb_table, workbook)

ISO3 = "SYR"
OUT = "syria_census.json"
DATASET = "syria-subnational-boundaries-and-tabular-data"
GAZETTEER = "cod-ab-syr"
YEAR = 2004
EST_YEAR = 2011
CENSUS = ("Central Bureau of Statistics (Syria), 2004 Population and Housing Census, "
          "Census Population Bulletin -- Man and Nah (2006)")
SOURCE = f"{CENSUS}, as the US Census Bureau tabulates it for HDX"
ESTIMATE = ("Central Bureau of Statistics (Syria), Statistical Abstract 2011, chapter 2, "
            "table 2: estimated population on 1 January 2011, as the US Census Bureau "
            "tabulates it for HDX")
URL = f"https://data.humdata.org/dataset/{DATASET}"
LICENCE = "CC BY, published via HDX"
# The citizens' row, the census's own residual, and the share below which a
# group is counted in that residual (one that would read 0.0%).
CITIZENS = "Syrian citizens"
OTHER = "Other nationalities"
SMALL = 0.0005

# The nationality table's groups, by the Bureau's field name -> the label
# the map files them under. The citizens' row names no people (see the
# docstring); "American" and "Australian" are continents' groups in the
# table (the data dictionary's "American, Total." beside "European, Total."
# and "Asian, Total."), not the United States and Australia.
NATIONALITY = {
    "ETH_SYR_B": "Syrian citizens",
    "ETH_PAL_B": "Palestinian",
    "ETH_ARAB_B": "Other Arab nationalities",
    "ETH_EURO_B": "European nationalities",
    "ETH_AFNA_B": "African nationalities (non-Arab)",
    "ETH_ASIA_B": "Asian nationalities",
    "ETH_AUS_B": "Oceanian nationalities",
    "ETH_USA_B": "Nationalities of the Americas",
    "ETH_OTHR_B": "Other nationalities",
}
NAT_TOTAL = "ETH_TPOP_B"
LANGUAGE_WHY = (
    "Syria's 2004 census published no language table: the Central Bureau of Statistics' "
    "results bulletin (Man and Nah, 2006) is reproduced in the US Census Bureau's workbook "
    "as age by sex (Table 2) and nationality (Table 3), and the workbook's data dictionary "
    "cites no other census table; UNdata's census tables reported to the UN Statistics "
    "Division hold no language table for Syria either.")

# The governorate the census could only partly enumerate (see the docstring),
# by OCHA P-code, and its districts.
GOLAN = {"SY14", "SY1400", "SY1402"}
GOLAN_NOTE = (" The census enumerated the part of Quneitra governorate under Syrian "
              "administration; the Golan Heights, which the boundary file draws inside "
              "this unit, have been administered by Israel since 1967 and their people "
              "were not counted by it (Israel's Central Bureau of Statistics counts 56,900 "
              "people in its Golan sub-district at the end of 2023).")


def ages(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each row's total, sexes and age groups, keyed by P-code, every sum checked."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("NSO_CODE") or "").strip()
        if row["_level"] not in (0, 1, 2) or (row["_level"] and not code):
            continue
        total, men, women = (count(row.get(k)) for k in ("BTOTL", "MTOTL", "FTOTL"))
        where = f"{row.get('AREA_NAME')} ({code})"
        check(total is not None and men is not None and women is not None,
              f"syria_census: {where}: no total or sex count")
        groups = age_groups(row, "B")
        # People whose age the census did not record are in the total and in
        # no group; they are left out of the median.
        unstated = count(row.get("B_UNSTATED")) or 0
        check(round(sum(g[2] for g in groups) + unstated) == round(total),
              f"syria_census: {where}: age groups make {sum(g[2] for g in groups):,.0f} "
              f"and {unstated:,.0f} of unstated age, not {total:,.0f}")
        check(round(men + women) == round(total),
              f"syria_census: {where}: men {men:,.0f} and women {women:,.0f} do not "
              f"make {total:,.0f}")
        out[code if row["_level"] else "SY"] = {
            "name": str(row.get("AREA_NAME") or ""), "level": row["_level"],
            "total": total, "men": men, "women": women, "groups": groups,
            "unstated": unstated}
    return out


def nationality(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each row's people by nationality, keyed by P-code, the groups checked."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("NSO_CODE") or "").strip()
        if row["_level"] not in (0, 1, 2) or (row["_level"] and not code):
            continue
        total = count(row.get(NAT_TOTAL))
        counts = {label: count(row.get(name)) for name, label in NATIONALITY.items()}
        where = f"{row.get('AREA_NAME')} ({code})"
        check(total is not None and all(v is not None for v in counts.values()),
              f"syria_census: {where}: a nationality cell is empty")
        check(round(sum(counts.values())) == round(total),
              f"syria_census: {where}: nationalities make {sum(counts.values()):,.0f}, "
              f"not {total:,.0f}")
        out[code if row["_level"] else "SY"] = {"total": total, "counts": counts}
    return out


def estimates(rows: list[dict[str, Any]], aliases: dict[str, str]) -> dict[str, dict[str, Any]]:
    """The Bureau's 1 January 2011 estimate by governorate, sexes checked."""
    def column(prefix: str) -> str:
        found = [n for n, a in aliases.items()
                 if a.lower().startswith(prefix) and "january 2011" in a.lower()]
        check(len(found) == 1, f"syria_census: {len(found)} '{prefix}... January 2011' "
                               f"columns in Population Estimates")
        return found[0]
    both, male, female = column("both sexes"), column("male"), column("female")
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("NSO_CODE") or "").strip()
        if row["_level"] not in (0, 1):
            continue
        total, men, women = count(row.get(both)), count(row.get(male)), count(row.get(female))
        where = f"{row.get('AREA_NAME')} ({code})"
        check(None not in (total, men, women), f"syria_census: {where}: no 2011 estimate")
        check(round(men + women) == round(total),
              f"syria_census: {where}: 2011 men and women do not make {total:,.0f}")
        out[code if row["_level"] else "SY"] = {"total": total, "men": men, "women": women}
    return out


def nests(table: dict[str, dict[str, Any]], what: str) -> None:
    """Districts make their governorate and governorates the country."""
    kids: dict[str, float] = defaultdict(float)
    govs = 0.0
    for code, row in table.items():
        if len(code) == 6:
            kids[code[:4]] += row["total"]
        elif len(code) == 4:
            govs += row["total"]
    for gov, made in kids.items():
        check(round(made) == round(table[gov]["total"]),
              f"syria_census: {what}: {gov}'s districts make {made:,.0f}, "
              f"not {table[gov]['total']:,.0f}")
    check(round(govs) == round(table["SY"]["total"]),
          f"syria_census: {what}: governorates make {govs:,.0f}, "
          f"not {table['SY']['total']:,.0f}")


def folded(counts: dict[str, float], total: float
           ) -> tuple[dict[str, float], list[tuple[str, float]]]:
    """The groups under ``SMALL`` of the people moved into "Other nationalities".

    A district of 172,095 people listed five foreign groups of 1 to 19
    people each, every one a bar reading 0.0%. Each is counted in the
    census's own residual instead, and the note names what went there. The
    citizens' row is never moved.
    """
    out = {k: v for k, v in counts.items() if v}
    moved = sorted(((k, v) for k, v in out.items()
                    if k not in (CITIZENS, OTHER) and total and v / total < SMALL),
                   key=lambda kv: (-kv[1], kv[0]))
    for k, v in moved:
        out[OTHER] = out.get(OTHER, 0) + out.pop(k)
    return out, moved


def nationality_note(code: str, nat: dict[str, Any], age_total: float,
                     moved: list[tuple[str, float]] | None = None) -> str:
    shown = {k for k, v in nat["counts"].items() if v} - {k for k, _v in moved or []}
    note = (f"Nationality, not ethnicity: the 2004 census asked each person's "
            f"nationality and no ethnic question, so the nationality it counts is shown "
            f"here in place of ethnicity, as Japan's and Korea's nationality counts are. "
            f"'Syrian citizens' is every Syrian citizen, of whatever people -- Arab, Kurd, "
            f"Armenian, Assyrian or Turkmen.")
    if "Palestinian" in shown:
        note += (" 'Palestinian' is Palestinian refugees and their descendants, who are not "
                 "Syrian citizens.")
    named = [k for k in ("Nationalities of the Americas", "Oceanian nationalities") if k in shown]
    if named:
        census = {"Nationalities of the Americas": "'American'",
                  "Oceanian nationalities": "'Australian'"}
        many = len(named) > 1
        note += (" " + " and ".join(f"'{k}'" for k in named)
                 + (" are" if many else " is") + " the census's "
                 + " and ".join(census[k] for k in named)
                 + (" groups, which stand" if many else " group, which stands")
                 + " beside its European, Asian and African ones.")
    if moved:
        note += (" Groups of under 0.05% of the people here are counted in 'Other "
                 "nationalities': " + ", ".join(f"{k} ({v:,.0f})" for k, v in moved) + ".")
    note += f" Shares of the {nat['total']:,.0f} people the nationality table counts"
    if round(nat["total"]) != round(age_total):
        note += (f" (the census's age table counts {age_total:,.0f} here; the "
                 f"nationality table, CBS Table 3, is a separate tabulation)")
    return note + "." + (GOLAN_NOTE if code in GOLAN else "")


def build(book: dict[str, list[list[Any]]], gaz: dict[str, list[list[Any]]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          parents: dict[str, str]) -> list[dict[str, Any]]:
    meta = " ".join(str(c) for r in book.get("Metadata", []) for c in r if c)
    check(str(YEAR) in meta, "syria_census: the workbook's metadata never names 2004")
    age_rows, _ = uscb_table(book, "Age-Sex")
    nat_rows, _ = uscb_table(book, "Ethnicity")
    est_rows, est_aliases = uscb_table(book, "Population Estimates")
    age, nat, est = ages(age_rows), nationality(nat_rows), estimates(est_rows, est_aliases)
    nests(age, "ages")
    nests(nat, "nationality")
    govs_2011 = sum(r["total"] for c, r in est.items() if len(c) == 4)
    check(round(govs_2011) == round(est["SY"]["total"]),
          f"syria_census: 2011 governorates make {govs_2011:,.0f}, not {est['SY']['total']:,.0f}")
    log(f"  {sum(1 for c in age if len(c) == 6)} districts, {sum(1 for c in age if len(c) == 4)} "
        f"governorates, {age['SY']['total']:,.0f} people in 2004 "
        f"({est['SY']['total']:,.0f} estimated for 1 January 2011)")
    national = median_age(age["SY"]["groups"], year=YEAR, source=SOURCE)
    log(f"  national median age {national['value'] if national else None}, "
        f"{100 * age['SY']['men'] / age['SY']['women']:.1f} men per 100 women")

    g1, g2 = gazetteer(gaz, 1), gazetteer(gaz, 2)
    bound1, left1, _spare1 = bind_by_gazetteer(admin1, {}, g1, 1)
    bound2, left2, spare2 = bind_by_gazetteer(admin2, parents, g2, 2)
    report("governorates not bound", left1)
    report("districts not bound", left2)
    report("OCHA districts no drawn unit took", spare2)
    rows = []
    sources = [{"field": "population/median_age/sex_ratio/ethnicity", "name": SOURCE,
                "url": URL, "year": YEAR, "license": LICENCE}]
    for level, drawn, bound in (("admin1", admin1, bound1), ("admin2", admin2, bound2)):
        for unit in drawn:
            code = bound.get(unit["id"])
            if code is None:
                continue
            check(code in age and code in nat,
                  f"syria_census: {unit['name']} is OCHA's {code}, which the census "
                  f"tables do not have")
            a, n = age[code], nat[code]
            counts, moved = folded(n["counts"], n["total"])
            golan = GOLAN_NOTE if code in GOLAN else ""
            if level == "admin1":
                check(code in est, f"syria_census: no 2011 estimate for {code}")
                population = measure(est[code]["total"], year=EST_YEAR, source=ESTIMATE)
                population["note"] = (
                    f"The Bureau's estimate for 1 January 2011; the 2004 census counted "
                    f"{a['total']:,.0f}." + golan)
            else:
                population = measure(a["total"], year=YEAR, source=SOURCE)
                population["note"] = "The 2004 census count (22 September 2004)." + golan
            rows.append(record(
                f"SYR-CEN-{code}", unit["name"], level=level, parent=ISO3, country=ISO3,
                parent_name=parents.get(unit["parent"]) if level == "admin2" else None,
                match_by="shape_id", shape_id=unit["id"], codes={"pcode": code},
                aliases=[a["name"].title()] if a["name"].title() != unit["name"] else None,
                population=population,
                median_age=median_age(a["groups"], year=YEAR, source=SOURCE),
                median_age_note=("Interpolated within the five-year age group holding the "
                                 "middle person, from the 2004 census's count of everyone by "
                                 "five-year age group (CBS, Man and Nah, Table 2)."
                                 + (f" The {a['unstated']:,.0f} people whose age was not "
                                    f"stated are left out." if a["unstated"] else "")
                                 + golan),
                sex_ratio=sex_ratio(a["men"], a["women"], year=YEAR, source=SOURCE),
                sex_ratio_note=(f"Males per 100 females in the 2004 census: "
                                f"{a['men']:,.0f} men and {a['women']:,.0f} women." + golan),
                ethnicity=shares(counts, total=n["total"]),
                ethnicity_year=YEAR, ethnicity_basis="nationality",
                ethnicity_note=nationality_note(code, n, a["total"], moved),
                language=gap(NOT_AVAILABLE, LANGUAGE_WHY),
                sources=sources + ([{"field": "population", "name": ESTIMATE, "url": URL,
                                     "year": EST_YEAR, "license": LICENCE}]
                                   if level == "admin1" else [])))
    log(f"  {sum(1 for r in rows if r['level'] == 'admin1')} governorates and "
        f"{sum(1 for r in rows if r['level'] == 'admin2')} districts written")
    return rows


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    book = workbook(uscb.workbook_url(DATASET))
    gaz = workbook(hdx_resource(GAZETTEER, r"\.xlsx$"))
    admin1, admin2 = units(ISO3, "admin1"), units(ISO3, "admin2")
    rows = build(book, gaz, admin1, admin2, parents_by_id(ISO3))
    write_json(PROCESSED / OUT, rows)
    log(f"  wrote {OUT}: {len(rows)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
