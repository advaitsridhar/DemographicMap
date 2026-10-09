#!/usr/bin/env python3
"""Median age and sex ratio from OCHA's COD-PS where no Southeast Asian office can be read.

**Why a projection.** Thailand counts its people by age and sex in two places,
and neither can be retrieved. The Department of Provincial Administration's
register (``stat.bora.dopa.go.th``) does not resolve, the National Statistical
Office's tables (``statbbi.nso.go.th``) have no address, and the government's
open-data portal (``data.go.th``) answers HTTP 403, "Your request has been
blocked by our security systems" -- each recorded in the log of the probe that
found it (the register's again in fa71356, with ``www.dopa.go.th`` answering
403 and ``catalog.dopa.go.th`` timing out), and none of them evaded. Laos
publishes its 2015 census volume as a PDF with no district ages; Cambodia's
2019 census gives its provinces' ages only in three broad groups (the final
report's Table PT 02: 0-14, 15-59 and 60 and over, too coarse for a median),
single years only for the country (priority table A1), and its provincial
reports' tables are not text.
What remains for all three is OCHA's Common Operational Dataset of population
statistics (COD-PS), which splits every unit by sex and five-year age group:

* ``cod-ps-tha`` (UNFPA, CC BY-IGO), reference year 2023: "Projections from
  2017 to 2022 by the United States Bureau of the Census", for the 77
  provinces and 928 districts -- the same table the map's district
  populations already come from;
* ``cod-ps-lao`` (UNFPA, CC BY-IGO), reference year 2024, method "Census",
  for the 18 provinces and 148 districts;
* ``cod-ps-khm`` (UNFPA, CC BY-IGO), reference year 2024, for the 25
  provinces (it has no district ages).

So every figure here is a projection, and this file is for the build's
FILL_ONLY list: it fills a median or a ratio no census or register gave, and
never replaces one. Each record says which dataset, which year and what the
dataset says its method was.

**The figures.** ``cod_ps_age.unit_figures`` reads a row: its groups must run
from 0 without a gap to an open top group, add up to the total (allowing a
column of unstated age), and its women and men must make it; the median is
interpolated within the five-year group holding the middle person and is
refused if that is the open one. The sex ratio here is males per 100 females,
to one decimal, as every other Southeast Asian reader writes it.

**Which polygon.** A row is bound to the map's unit of the same name (folded,
"Province" dropped) under the drawn parent of its own first-level name; where
the name is the only one of its kind in the country, outright. Where two
polygons share a name (Thailand has eight such pairs), the drawn parent must
also be where the polygon lies on the map's own admin1 tiles. Rows and
polygons left over are logged, never guessed.

Usage:
    python -m scripts.fetch_census.sea_cod_ps_age [--only THA,LAO,KHM]
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from typing import Any

from . import cod_ps
from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, record, write_json
from .cod_ps_age import age_columns, number, tables, unit_figures
from .sea_common import drawn, fold, locate, ratio

OUT = "sea_cod_ps_age.json"
DATASETS = {"THA": "cod-ps-tha", "LAO": "cod-ps-lao", "KHM": "cod-ps-khm"}
LEVELS = {"1": "admin1", "2": "admin2"}
# What each dataset is read for: where nothing official could be read.
WHERE = {"THA": ["admin1", "admin2"], "LAO": ["admin1", "admin2"], "KHM": ["admin1"]}
KIND = re.compile(r"\b(?:province|changwat|khwaeng|khaet)\b", re.I)


# The dataset's spelling -> the boundary file's, where the two romanise one
# province's name differently (Laos's provinces, three of Cambodia's). Applied
# to a first-level row's name and to the parent a district row names, never to
# a district's own name.
SPELLINGS = {
    ("LAO", "Bolikhamxai"): "Bolikhamsai", ("LAO", "Champasack"): "Champasak",
    ("LAO", "Khammouan"): "Khammouane", ("LAO", "Louangnamtha"): "Luang Namtha",
    ("LAO", "Louangphabang"): "Luang Prabang", ("LAO", "Oudomxai"): "Oudomxay",
    ("LAO", "Sekong"): "Xekong", ("LAO", "Xaignabouly"): "Xaignabouli",
    ("LAO", "Xaisomboon"): "Xaisomboun", ("LAO", "Xiengkhouang"): "Xiangkhouang",
    ("KHM", "Banteay Meanchey"): "Bantey Meanchey", ("KHM", "Ratanak Kiri"): "Ratanakiri",
    ("KHM", "Tboung Khmum"): "Tbong Khmum",
}
# Rows two districts share a romanised name with: Phra Nakhon Si Ayutthaya's
# Bang Sai (บางไทร, TH1404) and Bang Sai (บางซ้าย, TH1413), "Bang Sai (1)" and
# "(2)" in the dataset and both plain "Bang Sai" in the boundary file. Each is
# placed by its district office -- บางไทร's on the Chao Phraya at 14.20N
# 100.48E, บางซ้าย's by the Suphan Buri line at 14.33N 100.32E -- on the
# map's own admin2 tiles; the two polygons' extents do not overlap in
# longitude (100.41-100.58 and 100.23-100.37), so neither seat can fall in
# the other.
SEATS = {("THA", "TH1404"): (100.48, 14.20), ("THA", "TH1413"): (100.32, 14.33)}
TWIN_MARK = re.compile(r"\s*\(\d\)\s*$")
# Below 80 or above 160 males per 100 females, a whole district's figure is
# more likely the projection's arithmetic than a place, and the unit is left
# out. The bounds drop Ratchaburi's Ban Kha (48) and Suan Phueng (77), the
# district Ban Kha was cut from in 2007, and keep the island and naval
# districts of Thailand's east coast (up to 137) and Laos's Longcheng (142).
RATIO_BOUNDS = (80.0, 160.0)
# Why the office's own figures are not read instead, said on a unit the
# bounds leave out (docs/SOURCES.md and this reader's report have the runs).
UNREAD = {
    "THA": ("Thailand's own figures could not be retrieved: the Department of Provincial "
            "Administration's register statistics (stat.bora.dopa.go.th) do not resolve, "
            "and the National Statistical Office's hosts and the government's open-data "
            "portal answer HTTP 418 or 403 to automated requests."),
    "LAO": ("The Lao Statistics Bureau's 2015 census volume tabulates no district's ages."),
    "KHM": ("The National Institute of Statistics publishes no district's ages from the "
            "2019 census."),
}
# Why a projection rather than the office's own ages, said on every median:
# by country, or by country and level where the two differ.
WHY_PROJECTION = {
    "KHM": ("used because the 2019 census tabulates a province's ages only in three broad "
            "groups -- 0-14, 15-59 and 60 and over (final report, Table PT 02), too coarse "
            "for a median -- and single years of age only for the whole country (priority "
            "table A1)"),
    "THA": ("used because Thailand's own count of each district's people by age -- the "
            "Department of Provincial Administration's population register -- could not be "
            "retrieved: its statistics host does not resolve, and the government's "
            "open-data portal and the National Statistical Office's census hosts answer "
            "HTTP 403 or 418 to automated requests"),
    "LAO": ("used because the Lao Statistics Bureau publishes no district's ages from the "
            "2015 census: its results volume crosses age with the province at most"),
}
WHY_DEFAULT = "used because no table of the office's own gives these ages"
# A ratio this far from even, for a whole district or province, is said to be
# one on its record with the counts it rests on (Thailand's Ko Kut 137.4 and
# Khao Saming 136.8, Laos's Longcheng 142.5); inside RATIO_BOUNDS it stands.
UNUSUAL_RATIO = (85.0, 115.0)


# Why Thailand's districts (and its provinces' languages) carry no composition,
# said on the units this reader already binds. Measured on the 2000 census's
# provincial tables, the one census whose district tables an archive keeps:
# Ranong's workbook (tables 1-4 and the key indicators) gives a district its
# people by sex, household type and age group only, and the province its
# religion and minority languages only as shares among its key indicators.
RANONG_2000 = ("web.archive.org/web/20110615044445/http://web.nso.go.th/pop2000/finalrep/"
               "tables/ranong/ranong1.xls")
COMPOSITION_GAPS: dict[tuple[str, str], dict[str, str]] = {
    ("THA", "admin2"): {
        "religion": (
            "Thailand's censuses publish religion by province, not by district. The 2000 "
            "census's provincial final reports give a district (amphoe) only its population by "
            "sex, household type and five-year age group (tables 1 and 2) and put religion only "
            f"among the province's key indicators (Ranong's tables, {RANONG_2000}); the "
            "National Statistical Office's later census hosts refuse automated requests."),
        "language": (
            "Thailand's 2000 census asked the language spoken at home, and its provincial final "
            "reports give only the province's largest minority languages, as shares among its "
            "key indicators (Ranong: Malay 0.5%, Burmese and Mon 7.0%); no table gives a "
            f"district's languages (Ranong's tables, {RANONG_2000}). The National Statistical "
            "Office's later census hosts refuse automated requests."),
        "ethnicity": (
            "Thailand's census does not ask ethnicity; it asks nationality, religion and the "
            "language spoken at home, and the 2000 census published those for the province "
            "only (key indicators of each provincial final report; a district gets its people "
            f"by sex, household type and age: Ranong's tables, {RANONG_2000})."),
    },
    ("THA", "admin1"): {
        "language": (
            "Thailand's 2000 census asked the language spoken at home, but each province's final "
            "report gives only its largest minority languages, as shares among the key "
            "indicators (Ranong: Malay 0.5%, Burmese and Mon 7.0% in 2000), never the whole "
            "distribution, so no province has a language composition that adds up "
            f"({RANONG_2000}). The National Statistical Office's later census hosts refuse "
            "automated requests."),
    },
}


def why_projection(iso3: str, level: str) -> str:
    return WHY_PROJECTION.get((iso3, level)) or WHY_PROJECTION.get(iso3) or WHY_DEFAULT


def unusual_ratio(men: float, women: float, level: str) -> str:
    """A sentence for a ratio far from even, with the counts it rests on; else nothing."""
    value = ratio(men, women)
    if UNUSUAL_RATIO[0] <= value <= UNUSUAL_RATIO[1]:
        return ""
    unit = "district" if level == "admin2" else "province"
    return (f" An unusual ratio for a whole {unit}: the projection counts {round(men):,} "
            f"males against {round(women):,} females here, and the dataset gives no reason.")


def composition_gaps(iso3: str, level: str) -> dict[str, Any]:
    return {field: gap(NOT_AVAILABLE, note)
            for field, note in COMPOSITION_GAPS.get((iso3, level), {}).items()}


def key(name: Any) -> str:
    return fold(KIND.sub(" ", str(name or "")))


def spelled(iso3: str, name: Any) -> str:
    text = str(name or "").strip()
    return SPELLINGS.get((iso3, text), text)


def newest_tables(package: dict[str, Any]) -> dict[str, tuple[int, dict[str, Any], dict[str, Any]]]:
    """COD level ("1", "2") -> (year, table, age columns), the newest of each."""
    newest: dict[str, tuple[int, dict[str, Any], dict[str, Any]]] = {}
    for table in tables(package):
        cols = age_columns(table["columns"])
        if cols is None or table["level"] not in LEVELS:
            continue
        year = (cod_ps.reference_year(table["columns"],
                                      [{k: str(v) for k, v in r.items()} for r in table["rows"]],
                                      table["label"])
                or cod_ps.dataset_year(package))
        if year is None:
            log(f"    refused {table['label']}: no reference year")
            continue
        if table["level"] not in newest or year > newest[table["level"]][0]:
            newest[table["level"]] = (year, table, cols)
    return newest


def binder(iso3: str, level: str) -> tuple[dict[tuple[str, str], list[dict[str, Any]]],
                                         dict[str, list[dict[str, Any]]], dict[str, str]]:
    """The drawn units by (parent key, name key) and by name key alone, and
    admin1 id -> key."""
    units = drawn(iso3, level)
    parents = {u["id"]: key(u["name"]) for u in drawn(iso3, "admin1")} if level == "admin2" else {}
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for u in units:
        names = {key(u["name"]), *(key(a) for a in (u.get("aliases") or []))}
        for n in names:
            by_pair[(parents.get(u.get("parent"), ""), n)].append(u)
            by_name[n].append(u)
    return by_pair, by_name, parents


def bind_rows(iso3: str, level: str, rows: list[dict[str, Any]], unit_col: str,
              parent_col: str | None) -> tuple[dict[int, dict[str, Any]], list[str], list[str]]:
    """Row index -> drawn unit; and what was left on each side."""
    by_pair, by_name, parents = binder(iso3, level)
    shared = {n for n, us in by_name.items() if len({u["id"] for u in us}) > 1}
    where: dict[str, str | None] = {}
    if level == "admin2" and shared:
        twins = {u["id"]: tuple(u["point"]) for n in shared for u in by_name[n] if u.get("point")}
        where = locate(twins, "admin1", iso3)
    bound: dict[int, dict[str, Any]] = {}
    taken: set[str] = set()
    left: list[str] = []
    pcode_col = next((c for c in (rows[0] if rows else {})
                      if re.fullmatch(r"(?i)adm(?:in)?_?(\d)_?pcode", c)
                      and re.fullmatch(r"(?i)adm(?:in)?_?(\d)_?pcode", c).group(1) == level[-1]),
                     None)
    seated = {k[1]: v for k, v in SEATS.items() if k[0] == iso3}
    seats_at = locate(dict(seated), level, iso3) if seated and pcode_col else {}
    units_by_id = {u["id"]: u for u in drawn(iso3, level)}
    for i, row in enumerate(rows):
        # The spellings are the provinces': a district may carry its
        # province's name in the dataset's own spelling, as Champasack does.
        name = (spelled(iso3, row.get(unit_col)) if level == "admin1"
                else str(row.get(unit_col) or "").strip())
        parent = (key(spelled(iso3, row.get(parent_col)))
                  if (level == "admin2" and parent_col) else "")
        pcode = str(row.get(pcode_col) or "").strip() if pcode_col else ""
        if pcode in seated:
            sid = seats_at.get(pcode)
            unit = units_by_id.get(sid) if sid else None
            if (unit is None or key(unit["name"]) != key(TWIN_MARK.sub("", name))
                    or unit["id"] in taken):
                left.append(f"{name} ({pcode}): its seat finds no polygon of its name")
                continue
            log(f"    {name} ({pcode}) placed by its seat on {unit['name']} ({unit['id']})")
            taken.add(unit["id"])
            bound[i] = unit
            continue
        hits = {u["id"]: u for u in by_pair.get((parent, key(name)), [])}
        if not hits and len({u["id"] for u in by_name.get(key(name), [])}) == 1:
            hits = {u["id"]: u for u in by_name[key(name)]}
        if len(hits) != 1:
            left.append(f"{name} ({row.get(parent_col) if parent_col else '-'}): "
                        f"{len(hits)} polygons")
            continue
        unit = next(iter(hits.values()))
        if key(name) in shared and level == "admin2":
            # A shared name: the parent the boundary file gives must be where
            # the polygon lies.
            if parents.get(where.get(unit["id"])) != parents.get(unit.get("parent")):
                left.append(f"{name}: its polygon lies outside its drawn parent")
                continue
        if unit["id"] in taken:
            left.append(f"{name}: its polygon is another row's")
            continue
        taken.add(unit["id"])
        bound[i] = unit
    unbound = sorted(u["name"] for u in drawn(iso3, level) if u["id"] not in taken)
    return bound, left, unbound


def level_records(iso3: str, stub: str, licence: str, cod_level: str, year: int,
                  table: dict[str, Any], cols: dict[str, Any]) -> list[dict[str, Any]]:
    """One table's units, bound and checked."""
    level = LEVELS[cod_level]
    unit_col = cod_ps.name_column(table["columns"], cod_level)
    parent_col = cod_ps.name_column(table["columns"], "1") if cod_level == "2" else None
    if unit_col is None:
        log(f"    refused {table['label']}: no name column")
        return []
    method = table.get("method") or ""
    source = (f"OCHA, Common Operational Dataset -- population statistics ({stub}), "
              f"reference year {year}")
    basis = f" The dataset gives its method as \"{method[:200].rstrip()}\"." if method else ""
    rows = table["rows"]
    bound, left, unbound = bind_rows(iso3, level, rows, unit_col, parent_col)
    out: list[dict[str, Any]] = []
    refused = 0
    for i, unit in sorted(bound.items(), key=lambda kv: kv[1]["name"]):
        row = rows[i]
        figures, why = unit_figures(row, cols)
        if figures is None:
            refused += 1
            log(f"    left out {row.get(unit_col)}: {why}")
            continue
        women = number(row.get(cols["totals"]["F"]))
        men = number(row.get(cols["totals"]["M"]))
        name = str(row.get(unit_col)).strip()
        if not RATIO_BOUNDS[0] <= ratio(men, women) <= RATIO_BOUNDS[1]:
            # A projection's arithmetic, not a place: Ratchaburi's Ban Kha
            # comes out at 48 men to 100 women. The unit is left out whole,
            # its median being read from the same row, and says why.
            refused += 1
            log(f"    left out {name}: {ratio(men, women)} males per 100 females is outside "
                f"{RATIO_BOUNDS}, implausible for a whole district or province")
            why = (f"OCHA's COD-PS for the country (reference year {year}) is the only "
                   f"age-and-sex table this map could read here, and its row for {name} "
                   f"gives {ratio(men, women)} males per 100 females -- implausible for a "
                   f"whole {'district' if level == 'admin2' else 'province'}, so the "
                   f"projection's age breakdown is not used either. "
                   + UNREAD.get(iso3, ""))
            out.append(record(
                f"{iso3}-CODPSAGE-{level}-{fold(unit['name'])}-{unit['id'][-6:]}",
                unit["name"], level=level, parent=iso3, country=iso3, match_by="shape_id",
                shape_id=unit["id"], aliases=[name] if key(name) != key(unit["name"]) else None,
                median_age=gap(NOT_AVAILABLE, why), sex_ratio=gap(NOT_AVAILABLE, why),
                **composition_gaps(iso3, level)))
            continue
        # The twins placed by their seats are the two polygons the dataset's
        # population reached nowhere else (its own reader matches by name), so
        # their head count is written with them, from the same row.
        pcode_col = next((c for c in row if re.fullmatch(r"(?i)adm(?:in)?_?2_?pcode", c)), None)
        twin = level == "admin2" and (iso3, str(row.get(pcode_col) or "").strip()) in SEATS
        total = (number(row.get(cols["totals"]["T"])) if "T" in cols["totals"]
                 else (women or 0) + (men or 0))
        out.append(record(
            f"{iso3}-CODPSAGE-{level}-{fold(unit['name'])}-{unit['id'][-6:]}", unit["name"],
            level=level, parent=iso3, country=iso3, match_by="shape_id", shape_id=unit["id"],
            aliases=[name] if key(name) != key(unit["name"]) else None,
            population=({"value": int(round(total)), "year": year, "source": source}
                        if twin and total else None),
            population_note=(f"OCHA's COD-PS for the country, reference year {year}: a "
                             f"projection, as every other district's head count here is; this "
                             f"one shares its romanised name with another district of its "
                             f"province and was placed by its district office.{basis}"
                             if twin and total else None),
            median_age={"value": figures["median"], "unit": "years", "year": year,
                        "source": source},
            median_age_note=(
                f"Interpolated within the five-year age group that holds the middle person, "
                f"from the age breakdown of OCHA's COD-PS for the country, reference year "
                f"{year}: a projection, not a count, {why_projection(iso3, level)}.{basis}"),
            sex_ratio={"value": ratio(men, women), "unit": "males_per_100_females",
                       "year": year, "source": source},
            sex_ratio_note=(f"Males per 100 females in OCHA's COD-PS for the country, "
                            f"reference year {year}: a projection, not a count."
                            f"{unusual_ratio(men, women, level)}{basis}"),
            sources=[{"field": ("population/median_age/sex_ratio" if twin
                                else "median_age/sex_ratio"), "name": source,
                      "url": cod_ps.DATASET_PAGE.format(stub=stub), "year": year,
                      "license": licence}],
            **composition_gaps(iso3, level)))
    log(f"  {iso3} {level}: {len(out)} units from {table['label']} ({year}); {refused} "
        f"refused by the checks; rows on no polygon ({len(left)}): {'; '.join(left[:40])}; "
        f"polygons with no row ({len(unbound)}): {', '.join(unbound[:40])}")
    return out


def country_records(iso3: str, levels: set[str]) -> list[dict[str, Any]]:
    stub = DATASETS[iso3]
    package = cod_ps.get("package_show", id=stub)
    if not cod_ps.is_usable(package):
        log(f"  {stub}: refused, licence {cod_ps.licence(package)}")
        return []
    out: list[dict[str, Any]] = []
    for cod_level, (year, table, cols) in sorted(newest_tables(package).items()):
        if LEVELS[cod_level] in levels:
            out += level_records(iso3, stub, cod_ps.licence(package), cod_level, year, table,
                                 cols)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=";".join(f"{c}:{'+'.join(v)}" for c, v in WHERE.items()),
                    help="countries and levels, e.g. 'THA:admin1+admin2;KHM:admin1'")
    args = ap.parse_args()
    records: list[dict[str, Any]] = []
    for item in [x.strip() for x in args.only.split(";") if x.strip()]:
        iso3, _, levels = item.partition(":")
        iso3 = iso3.strip().upper()
        wanted = set(levels.replace("+", ",").split(",")) - {""} or set(LEVELS.values())
        log(f"sea_cod_ps_age: {iso3} from {DATASETS[iso3]}, {sorted(wanted)}")
        records += country_records(iso3, wanted)
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
