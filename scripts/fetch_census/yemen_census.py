#!/usr/bin/env python3
"""Yemen's districts and governorates: the 2004 census and the CSO's projections by age.

Yemen last counted its people on 16 December 2004. The Central Statistical
Organization's results -- population by sex for every governorate and
district (Population, Housing and Establishment Census 2004, published 2007),
and nationality by governorate (Table 25) -- and its *2016 Population
Projections by Governorate & District, Sex & Age Disaggregated* (for 2016 and
2017) are both in the US Census Bureau's subnational workbook for HDX
(``yemen-subnational-boundaries-and-tabular-data``, CC BY), each row keyed by
the CSO's own four-digit district code (1101 is Ibb's Al Qafr).

**Binding.** The map's districts are OCHA's (COD-AB, ``cod-ab-yem``), whose
P-codes are the CSO's codes with "YE" in front: a drawn label is found among
OCHA's districts of the same governorate, and its P-code is the census row's.
A drawn governorate is the governorate code its bound districts share.

**What is written.**

* Every bound district: its 2004 population and males per hundred females
  from the census, and -- where the CSO projected the district's own ages --
  its median age in the 2017 projection.
* Every governorate: the same, plus its people by nationality (Yemeni
  citizens and foreign nationals) in 2004. The citizens' row is written
  "Yemeni citizens", a label that names no people and is filed as a
  nationality: Yemen's citizens include the Mehri of al-Mahrah and the
  Soqotri, peoples of their own languages, and a row read as "Yemeni" would
  colour al-Mahrah wholly Arab, which the census never said.
* Every unit, census-bound or not: why it carries no religion or language.
  The census tables the Census Bureau reproduces -- dwellings, households,
  nationality (Table 25), orphanhood (31), disability (35), computer and
  internet use (23-24) -- include neither.

**A projection is not a count, and a copy is not a projection.** The CSO's
district projections may give every district of a governorate the
governorate's own age structure, which would make a district median a
governorate figure written onto its children. So the reader measures it: a
governorate whose districts' age shares all sit within ``SAME_SHAPE`` of the
governorate's own gives its districts no median, and the log says which.
The median is written fill-only (``yemen_census_age.json``), so a census
median for the same unit would always win.

**Checks** (any failure stops the run and nothing is written): districts make
their governorate and governorates the country, for the census population and
for the projection; men and women make every total; age groups make every
projected total; every drawn unit is bound to one census row and none twice.

Usage:
    python -m scripts.fetch_census.yemen_census
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any

from . import uscb
from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .west_asia_common import (age_groups, bind_by_gazetteer, check, count, gazetteer,
                               hdx_resource, infer_parents, key, median_age, parents_by_id,
                               report, sex_ratio, units, uscb_table, workbook)

ISO3 = "YEM"
OUT = "yemen_census.json"
OUT_AGE = "yemen_census_age.json"
DATASET = "yemen-subnational-boundaries-and-tabular-data"
GAZETTEER = "cod-ab-yem"
YEAR = 2004
PROJECTION_YEAR = 2017
SUFFIX = "_7"            # the workbook's columns for the 2017 projection
CENSUS = ("Central Statistical Organization (Yemen), Population, Housing and Establishment "
          "Census 2004 (published 2007)")
SOURCE = f"{CENSUS}, as the US Census Bureau tabulates it for HDX"
PROJECTION = ("Central Statistical Organization (Yemen), 2016 Population Projections by "
              "Governorate & District, Sex & Age Disaggregated (2017 column), as the US Census "
              "Bureau tabulates it for HDX")
URL = f"https://data.humdata.org/dataset/{DATASET}"
LICENCE = "CC BY, published via HDX"
DECISION = "19 September 2026"
# A projection's cells are fractional people; its sums are checked to this.
SLACK = 0.5
# Two age structures are one when no five-year group's share differs by more.
SAME_SHAPE = 0.0005
# The nationality table and the population table count a governorate within
# this share of each other, or its nationality is not written.
NAT_TOLERANCE = 0.005
# The census's governorates whose own row counts ground the Bureau files under
# another code: Hadramawt's 2004 row (19) counts the two Socotra districts the
# Bureau files under Socotra (32), made a governorate in 2013.
COUNTS_ALSO = {"19": ("32",)}
# Census districts whose ground the boundary file draws as two polygons in two
# governorates: OCHA cut the parts of Hamdan (2301) and of Sanhan wa Bani
# Bahlul (2305) nearest the capital into "Sana'a City Outskirts - <district>"
# units under Amanat al-Asimah (13), with codes the census does not have,
# leaving the rest of each district in Sana'a governorate (23). The census
# counts each district whole, so neither polygon's figure is known, and
# neither is either governorate's. Which outskirts unit is which district is
# read from its label, and every code the census lacks must be one of them.
SPLIT = ("2301", "2305")
SPLIT_GOVERNORATES = {"13", "23"}
CITIZENS = "Yemeni citizens"
# What the census published, measured on the Bureau's workbook: its sheets
# and the census tables its data dictionary cites.
PUBLISHED = ("the US Census Bureau's workbook of the census reproduces its tables on "
             "dwellings and households, nationality (Table 25), orphanhood (Table 31), "
             "disability (Table 35) and computer and internet use (Tables 23-24), and its data "
             "dictionary cites no other census table; UNdata's census tables reported to the "
             "UN Statistics Division hold none for Yemen either")
RELIGION_WHY = f"Yemen's 2004 census published no religion table: {PUBLISHED}."
LANGUAGE_WHY = f"Yemen's 2004 census published no language table: {PUBLISHED}."
# Nationality is the census's Table 25, "Total Resident Population by
# Nationality, Gender and Governorates" (the workbook's data dictionary, probe
# d19e048): a governorate table, so no district has it; and a governorate
# drawn as the sum of its districts is not the row's ground.
DISTRICT_NATIONALITY_WHY = (
    "The 2004 census's nationality table (Table 25, resident population by nationality, "
    "gender and governorate) is published by governorate only, as the US Census Bureau's "
    "workbook reproduces it, so no district's split of Yemeni and foreign nationals is "
    "known.")
SUMMED_NATIONALITY_WHY = (
    "The 2004 census publishes nationality (Table 25) for its own governorate rows only, and "
    "this governorate is drawn as the sum of its census districts, not as the census's row "
    "(which also counts ground the map draws in another governorate), so no nationality "
    "split is this shape's.")


def code_of(row: dict[str, Any]) -> str:
    return str(row.get("NSO_CODE") or "").strip() if row["_level"] else "YE"


def census(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """2004 population, sexes and nationality, by CSO code; sexes checked."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["_level"] not in (0, 1, 2):
            continue
        code = code_of(row)
        total, men, women = (count(row.get(k)) for k in ("POP_TPOP", "POP_MPOP", "POP_FPOP"))
        where = f"{row.get('AREA_NAME')} ({code})"
        if (total, men, women) == (None, None, None):
            # A unit made after 2004 -- Socotra governorate, split from
            # Hadramawt in 2013 -- has no census row of its own.
            log(f"    {where}: no 2004 count (a unit made since)")
            continue
        check(None not in (total, men, women), f"yemen_census: {where}: no census count")
        check(round(men + women) == round(total),
              f"yemen_census: {where}: men and women do not make {total:,.0f}")
        yemeni = next((count(v) for k, v in row.items()
                       if isinstance(k, str) and k.replace(" ", "") == "NAT_YEM_B"), None)
        foreign = count(row.get("NAT_NYEM_B"))
        out[code] = {"name": str(row.get("AREA_NAME") or ""), "total": total, "men": men,
                     "women": women, "yemeni": yemeni, "foreign": foreign}
    return out


def projection(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The 2017 projection by CSO code: total, sexes and age groups, sums checked."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["_level"] not in (0, 1, 2):
            continue
        code = code_of(row)
        total, men, women = (count(row.get(k + SUFFIX)) for k in ("BTOTL", "MTOTL", "FTOTL"))
        where = f"{row.get('AREA_NAME')} ({code})"
        check(None not in (total, men, women), f"yemen_census: {where}: no 2017 projection")
        groups = age_groups(row, "B", SUFFIX)
        check(abs(sum(g[2] for g in groups) - total) <= SLACK * len(groups),
              f"yemen_census: {where}: projected age groups make "
              f"{sum(g[2] for g in groups):,.1f}, not {total:,.1f}")
        check(abs(men + women - total) <= SLACK * 2,
              f"yemen_census: {where}: projected sexes do not make {total:,.1f}")
        out[code] = {"total": total, "groups": groups, "name": str(row.get("AREA_NAME") or "")}
    return out


def nests(table: dict[str, dict[str, Any]], what: str, slack: float = 0.0,
          also: dict[str, tuple[str, ...]] | None = None) -> None:
    """Districts make their governorate and governorates the country.

    ``also`` names, for a governorate whose own row counts ground the table
    files under another code, the codes whose districts its row includes.
    """
    also = also or {}
    kids: dict[str, float] = defaultdict(float)
    govs = 0.0
    for code, row in table.items():
        if len(code) == 4:
            kids[code[:2]] += row["total"]
        elif len(code) == 2 and code != "YE":
            govs += row["total"]
    for gov, extra in also.items():
        for other in extra:
            if other in kids:
                kids[gov] += kids.pop(other)
    for gov, made in kids.items():
        check(gov in table, f"yemen_census: {what}: districts of governorate {gov}, "
                            f"which has no row of its own")
        check(abs(made - table[gov]["total"]) <= max(1.0, slack * table[gov]["total"]),
              f"yemen_census: {what}: governorate {gov}'s districts make {made:,.1f}, "
              f"not {table[gov]['total']:,.1f}")
    check(abs(govs - table["YE"]["total"]) <= max(1.0, slack * table["YE"]["total"]),
          f"yemen_census: {what}: governorates make {govs:,.1f}, not {table['YE']['total']:,.1f}")


def shape(groups: list[tuple[int, int | None, float]]) -> list[float]:
    total = sum(g[2] for g in groups) or 1.0
    return [g[2] / total for g in groups]


def copied_governorates(proj: dict[str, dict[str, Any]]) -> set[str]:
    """Governorates whose districts' projected ages are the governorate's own, scaled."""
    out = set()
    by_gov: dict[str, list[str]] = defaultdict(list)
    for code in proj:
        if len(code) == 4:
            by_gov[code[:2]].append(code)
    for gov, codes in sorted(by_gov.items()):
        mine = shape(proj[gov]["groups"])
        worst = max(max(abs(a - b) for a, b in zip(shape(proj[c]["groups"]), mine))
                    for c in codes)
        if worst <= SAME_SHAPE:
            out.add(gov)
        log(f"    governorate {gov}: {len(codes)} districts, largest age-share departure "
            f"from the governorate's {worst:.4f}{' -- a copy' if gov in out else ''}")
    return out


def build(book: dict[str, list[list[Any]]], gaz: dict[str, list[list[Any]]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          parents: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    meta = " ".join(str(c) for r in book.get("Metadata", []) for c in r if c)
    check("2004" in meta, "yemen_census: the workbook's metadata never names 2004")
    cen = census(uscb_table(book, "Census Population")[0])
    proj = projection(uscb_table(book, "Age-Sex Estimates")[0])
    nests(cen, "census", also=COUNTS_ALSO)
    nests(proj, "projection", slack=0.0005)
    # A governorate as the map draws it is the sum of the census districts
    # filed under its code: for Hadramawt that leaves out Socotra, which its
    # 2004 row counts. Its nationality, published only for the row, is kept
    # only where the row and the sum are the same ground.
    sums: dict[str, dict[str, float]] = defaultdict(lambda: {"total": 0.0, "men": 0.0,
                                                             "women": 0.0})
    for code, row in cen.items():
        if len(code) == 4:
            for k in ("total", "men", "women"):
                sums[code[:2]][k] += row[k]
    for gov, made in sums.items():
        row = cen.get(gov)
        same = row is not None and round(row["total"]) == round(made["total"])
        cen[gov] = {"name": row["name"] if row else proj.get(gov, {}).get("name", gov), **made,
                    "yemeni": row["yemeni"] if same else None,
                    "foreign": row["foreign"] if same else None,
                    "note": None if same else (
                        f" The sum of the {sum(1 for c in cen if len(c) == 4 and c[:2] == gov)} "
                        f"census districts the governorate is drawn with"
                        + (f"; the census's own row for it, {row['total']:,.0f}, also counts "
                           f"ground drawn in another governorate." if row else
                           "; the governorate was made after the census.")
                        + " Its nationality, published only for the census's row, is not "
                          "written.")}
        if not same:
            log(f"    governorate {gov}: drawn as the sum of its districts, "
                f"{made['total']:,.0f}" + (f" (the census row counts {row['total']:,.0f})"
                                            if row else " (no census row)"))
    log(f"  census: {sum(1 for c in cen if len(c) == 4)} districts, "
        f"{sum(1 for c in cen if len(c) == 2 and c != 'YE')} governorates, "
        f"{cen['YE']['total']:,.0f} people")
    national = median_age(proj["YE"]["groups"], year=PROJECTION_YEAR, source=PROJECTION)
    log(f"  projected national median age for 2017: {national['value'] if national else None}")
    copies = copied_governorates(proj)

    g2 = gazetteer(gaz, 2)
    # The boundary file's governorates are "Hajjah Governorate", "Hadhramaut";
    # OCHA's "Hajjah", "Hadramawt": paired by the districts they share.
    aliases = infer_parents(admin2, parents, g2, 2)
    log(f"  governorates paired with OCHA's: {len(aliases)} of {len(admin1)}")
    bound2, left2, spare2 = bind_by_gazetteer(admin2, parents, g2, 2, parent_alias=aliases)
    report("districts not bound", left2)
    report("OCHA districts no drawn unit took", spare2)
    codes2 = {sid: (p[2:] if p.upper().startswith("YE") else p) for sid, p in bound2.items()}
    missing = sorted(f"{c}" for c in codes2.values() if c not in cen)
    report("bound districts the census has no row for", missing)
    labels = {u["id"]: u["name"] for u in admin2}
    for code in SPLIT:
        check(code in cen, f"yemen_census: the split district {code} has no census row")
    # An outskirts unit is the split district its label names; a bound code
    # the census lacks that is no outskirts unit stops the run.
    outskirts: dict[str, str] = {}
    for sid, code in sorted(codes2.items()):
        if code in cen:
            continue
        # "Sana'a City Outskirts - Hamdan": the district is named after the dash.
        tail = key(labels[sid].rsplit("-", 1)[-1])
        named = [d for d in SPLIT if tail.startswith(key(cen[d]["name"]))]
        check(code[:2] in SPLIT_GOVERNORATES and len(named) == 1,
              f"yemen_census: {labels[sid]} ({code}) has no census row and names "
              f"{len(named)} of the split districts {SPLIT}")
        outskirts[code] = named[0]
        log(f"    {labels[sid]} ({code}): the outskirts part of "
            f"{cen[named[0]]['name']} ({named[0]})")
    check(sorted(outskirts.values()) == sorted(SPLIT),
          f"yemen_census: outskirts units {outskirts} do not pair with the split "
          f"districts {SPLIT}")
    # The code is the binding; the names are a check on it. A drawn label
    # and the Bureau's romanisation of the same code that share no spelling
    # are listed for a person to read.
    differ = [f"{labels[sid]} = {cen[c]['name']} ({c})" for sid, c in sorted(codes2.items())
              if c in cen and key(labels[sid]) != key(cen[c]["name"])
              and key(labels[sid])[:4] != key(cen[c]["name"])[:4]]
    report("bound by code, spelt differently", differ, limit=80)
    # A drawn governorate is the governorate code its bound districts share.
    gov_of: dict[str, set[str]] = defaultdict(set)
    for unit in admin2:
        if unit["id"] in codes2:
            gov_of[unit["parent"]].add(codes2[unit["id"]][:2])
    codes1 = {}
    for unit in admin1:
        found = gov_of.get(unit["id"], set())
        if len(found) == 1:
            codes1[unit["id"]] = next(iter(found))
        else:
            log(f"    governorate {unit['name']}: its districts point to {sorted(found)}")

    rows, age_rows = [], []
    sources = [{"field": "population/sex_ratio", "name": SOURCE, "url": URL, "year": YEAR,
                "license": LICENCE}]
    drawn_as = {code: labels[sid] for sid, code in codes2.items()}
    for level, drawn, codes in (("admin1", admin1, codes1), ("admin2", admin2, codes2)):
        for unit in drawn:
            code = codes.get(unit["id"])
            why = None
            if level == "admin2" and code in SPLIT:
                why = (f"The 2004 census counts {unit['name']} district whole "
                       f"({cen[code]['total']:,.0f} people); the boundary file draws the part "
                       f"of it nearest Sana'a apart, under Amanat al-Asimah, so the district's "
                       f"figures are not this shape's and the part's are not published.")
            elif level == "admin2" and code in outskirts:
                why = (f"Part of {drawn_as.get(outskirts[code], outskirts[code])} district, "
                       f"which the 2004 census counts whole with the rest of the district "
                       f"(drawn in Sana'a governorate); nothing counts this part alone.")
            elif level == "admin1" and code in SPLIT_GOVERNORATES:
                why = ("The boundary file draws the Sana'a City outskirts of Hamdan and of "
                       "Sanhan wa Bani Bahlul in Amanat al-Asimah, while the 2004 census and "
                       "the CSO's projections count both districts whole in Sana'a "
                       "governorate, so neither governorate's figures are this shape's.")
            if why:
                rows.append(record(
                    f"YEM-CEN-{code}-{unit['id'][-6:]}", unit["name"], level=level,
                    parent=ISO3, country=ISO3, match_by="shape_id", shape_id=unit["id"],
                    parent_name=parents.get(unit["parent"]) if level == "admin2" else None,
                    population=gap(NOT_AVAILABLE, why), sex_ratio=gap(NOT_AVAILABLE, why),
                    median_age=gap(NOT_AVAILABLE, why), ethnicity=gap(NOT_AVAILABLE, why),
                    religion=gap(NOT_AVAILABLE, RELIGION_WHY),
                    language=gap(NOT_AVAILABLE, LANGUAGE_WHY)))
                continue
            if code is None or code not in cen:
                # No census row of its own, but the census's tables still say
                # what they never asked anywhere.
                rows.append(record(
                    f"YEM-CEN-unbound-{unit['id'][-8:]}", unit["name"], level=level,
                    parent=ISO3, country=ISO3, match_by="shape_id", shape_id=unit["id"],
                    parent_name=parents.get(unit["parent"]) if level == "admin2" else None,
                    religion=gap(NOT_AVAILABLE, RELIGION_WHY),
                    language=gap(NOT_AVAILABLE, LANGUAGE_WHY)))
                continue
            c = cen[code]
            population = measure(c["total"], year=YEAR, source=SOURCE)
            population["note"] = "The 2004 census count (16 December 2004)." + (c.get("note") or "")
            fields: dict[str, Any] = {}
            if level == "admin1" and c["yemeni"] is not None and c["foreign"] is not None:
                made = c["yemeni"] + c["foreign"]
                if abs(made - c["total"]) <= NAT_TOLERANCE * c["total"]:
                    fields = {
                        "ethnicity": shares({CITIZENS: c["yemeni"],
                                             "Foreign nationals": c["foreign"]}),
                        "ethnicity_year": YEAR, "ethnicity_basis": "nationality",
                        "ethnicity_note": (
                            f"Nationality, not ethnicity: the 2004 census (Table 25) counts "
                            f"Yemeni nationals and others, and Yemen's census asks no ethnic "
                            f"question. Carried on this field under the owner's decision of "
                            f"{DECISION}. 'Yemeni citizens' is every Yemeni national, of "
                            f"whatever people -- Arab, Mehri, Soqotri or another. Shares of the "
                            f"{made:,.0f} people the nationality table counts (the population "
                            f"table counts {c['total']:,.0f})."),
                    }
                else:
                    log(f"    {unit['name']}: nationality makes {made:,.0f} against "
                        f"{c['total']:,.0f}; not written")
                    fields = {"ethnicity": gap(NOT_AVAILABLE, (
                        f"The 2004 census's nationality table (Table 25) counts {made:,.0f} "
                        f"people here and its population table {c['total']:,.0f}, more than "
                        f"{NAT_TOLERANCE:.1%} apart, so its shares are not written."))}
            elif level == "admin1":
                fields = {"ethnicity": gap(NOT_AVAILABLE, SUMMED_NATIONALITY_WHY)}
            else:
                fields = {"ethnicity": gap(NOT_AVAILABLE, DISTRICT_NATIONALITY_WHY)}
            rows.append(record(
                f"YEM-CEN-{code}", unit["name"], level=level, parent=ISO3, country=ISO3,
                parent_name=parents.get(unit["parent"]) if level == "admin2" else None,
                match_by="shape_id", shape_id=unit["id"], codes={"cso": code},
                aliases=[c["name"].title()] if c["name"].title() != unit["name"] else None,
                population=population,
                sex_ratio=sex_ratio(c["men"], c["women"], year=YEAR, source=SOURCE),
                sex_ratio_note=(f"Males per 100 females in the 2004 census: {c['men']:,.0f} "
                                f"men and {c['women']:,.0f} women."),
                religion=gap(NOT_AVAILABLE, RELIGION_WHY),
                language=gap(NOT_AVAILABLE, LANGUAGE_WHY),
                sources=sources + ([{"field": "ethnicity", "name": SOURCE, "url": URL,
                                     "year": YEAR, "license": LICENCE}]
                                   if isinstance(fields.get("ethnicity"), list) else []),
                **fields))
            p = proj.get(code)
            if p is None or (level == "admin2" and code[:2] in copies):
                continue
            age_rows.append(record(
                f"YEM-PROJ-{code}", unit["name"], level=level, parent=ISO3, country=ISO3,
                parent_name=parents.get(unit["parent"]) if level == "admin2" else None,
                match_by="shape_id", shape_id=unit["id"], codes={"cso": code},
                median_age=median_age(p["groups"], year=PROJECTION_YEAR, source=PROJECTION),
                median_age_note=(
                    "Interpolated within the five-year age group holding the middle person, "
                    "from the CSO's projection of this unit's population by five-year age "
                    "group for 2017 -- a projection from the 2004 census, not a count, made "
                    "before the war's displacement."),
                sources=[{"field": "median_age", "name": PROJECTION, "url": URL,
                          "year": PROJECTION_YEAR, "license": LICENCE}]))
    log(f"  census: {sum(1 for r in rows if r['level'] == 'admin1')} governorates and "
        f"{sum(1 for r in rows if r['level'] == 'admin2')} districts; projection medians: "
        f"{sum(1 for r in age_rows if r['level'] == 'admin1')} governorates and "
        f"{sum(1 for r in age_rows if r['level'] == 'admin2')} districts")
    return rows, age_rows


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    book = workbook(uscb.workbook_url(DATASET))
    gaz = workbook(hdx_resource(GAZETTEER, r"\.xlsx$"))
    rows, age_rows = build(book, gaz, units(ISO3, "admin1"), units(ISO3, "admin2"),
                           parents_by_id(ISO3))
    write_json(PROCESSED / OUT, rows)
    write_json(PROCESSED / OUT_AGE, age_rows)
    log(f"  wrote {OUT} ({len(rows)}) and {OUT_AGE} ({len(age_rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
