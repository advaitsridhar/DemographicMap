#!/usr/bin/env python3
"""Median age and sex ratio from OCHA's COD-PS where no Southeast Asian office can be read.

**Why a projection.** Thailand counts its people by age and sex in two places,
and neither answers this map's reader. The Department of Provincial
Administration's register (``stat.bora.dopa.go.th``) has no DNS answer from
the runner, the National Statistical Office's tables (``statbbi.nso.go.th``)
no address, and the government's open-data portal (``data.go.th``) answers
HTTP 403, "Your request has been blocked by our security systems" -- each
recorded in the log of the probe that found it, and none of them evaded. Laos
publishes its 2015 census volume as a PDF with no district ages; Cambodia's
2019 census gives its provinces' ages in reports whose tables are not text.
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
from ._shared import PROCESSED, log, record, write_json
from .cod_ps_age import age_columns, number, tables, unit_figures
from .sea_common import drawn, fold, locate, ratio

OUT = "sea_cod_ps_age.json"
DATASETS = {"THA": "cod-ps-tha", "LAO": "cod-ps-lao", "KHM": "cod-ps-khm"}
LEVELS = {"1": "admin1", "2": "admin2"}
# What each dataset is read for: where nothing official could be read.
WHERE = {"THA": ["admin1", "admin2"], "LAO": ["admin1", "admin2"], "KHM": ["admin1"]}
KIND = re.compile(r"\b(?:province|changwat|khwaeng|khaet)\b", re.I)


def key(name: Any) -> str:
    return fold(KIND.sub(" ", str(name or "")))


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
    for i, row in enumerate(rows):
        name = str(row.get(unit_col) or "").strip()
        parent = key(row.get(parent_col)) if (level == "admin2" and parent_col) else ""
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
        out.append(record(
            f"{iso3}-CODPSAGE-{level}-{fold(unit['name'])}-{unit['id'][-6:]}", unit["name"],
            level=level, parent=iso3, country=iso3, match_by="shape_id", shape_id=unit["id"],
            aliases=[name] if key(name) != key(unit["name"]) else None,
            median_age={"value": figures["median"], "unit": "years", "year": year,
                        "source": source},
            median_age_note=(
                f"Interpolated within the five-year age group that holds the middle person, "
                f"from the age breakdown of OCHA's COD-PS for the country, reference year "
                f"{year}: a projection, not a count, used because the office's own tables "
                f"could not be read.{basis}"),
            sex_ratio={"value": ratio(men, women), "unit": "males_per_100_females",
                       "year": year, "source": source},
            sex_ratio_note=(f"Males per 100 females in OCHA's COD-PS for the country, "
                            f"reference year {year}: a projection, not a count.{basis}"),
            sources=[{"field": "median_age/sex_ratio", "name": source,
                      "url": cod_ps.DATASET_PAGE.format(stub=stub), "year": year,
                      "license": licence}]))
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
