#!/usr/bin/env python3
"""Turkey's districts by sex and five-year age group, from TÜİK's register.

TÜİK counts the population every year from its address-based register
(Adrese Dayalı Nüfus Kayıt Sistemi, ADNKS), by province, district, sex and
age; its own database (MEDAS) and data portal are an interactive application
and a single-page app that a script cannot read. OCHA's Common Operational
Dataset for Türkiye (cod-ps-tur, "Türkiye İstatistik Kurumu Başkanlığı
(TÜİK)" as its source) relays the register's 2022 figures as tables: every
district's women and men and their five-year age groups to 90 and over. That
is each district's men per hundred women and a median age, interpolated
within the five-year group holding the middle person -- the finest grouping
published for a district -- and its count.

**Universe.** The register counts the resident population; Syrians under
temporary protection are not in it (OCHA's caveat: the workbook tables them
apart, and they are not read here).

**Binding.** Each district row is joined to the map's polygon of the same
name within the same province, one to one, by shape id; every row and every
polygon left over is logged. The map draws 972 districts.

**Checks.** Every district's women and men make its total and its age groups
make it too; each province's districts make the province's own row; the
provinces make the country's; and the country's median, from the same
groups, is held against Eurostat's for 1 January 2023 (the register counts
the population on 31 December 2022).

The file is fill-only: these are the register's counts as OCHA tabulates
them, and a figure read from TÜİK's own tables would stand before them.

Usage:
    python -m scripts.fetch_census.turkey_districts
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from collections import defaultdict
from typing import Any

from ._shared import PROCESSED, log, measure, record, write_json
from . import cod_ps, cod_ps_age
from .east_checks import check_median

OUT = "turkey_districts.json"
STUB = "cod-ps-tur"
SITE = PROCESSED.parent.parent / "site" / "data"
SOURCE = ("Turkish Statistical Institute (TÜİK), address-based population register "
          "(ADNKS) 2022, by district, sex and five-year age group, as OCHA's Common "
          "Operational Dataset for Türkiye ({stub}) relays it")
YEAR = 2022
# Polygons the boundary file names otherwise than the register, each read off
# the register's own row: (province, the map's name) -> the register's name.
ALIASES: dict[tuple[str, str], str] = {
    # Gökçeada, whose Greek name the boundary file gives it.
    ("canakkale", "imbros"): "gokceada",
}
# How far a district's men and women may sit from its total, and the
# districts from their province: the register's counts are exact, so this is
# rounding in the tables' own arithmetic and nothing more.
SLACK = 2


def fold(name: str) -> str:
    """A Turkish name for matching: dotless i, accents and spaces gone."""
    text = str(name or "").replace("ı", "i").replace("İ", "I")
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def columns_of(table: dict[str, Any], *names: str) -> str:
    for name in names:
        hit = next((c for c in table["columns"] if c.strip().upper() == name), None)
        if hit:
            return hit
    raise SystemExit(f"turkey_districts: {table['label']} has none of {names}")


def figures(row: dict[str, Any], cols: dict[str, Any], where: str) -> dict[str, Any]:
    """Count, sexes, median and ratio of one row, or a stop."""
    got, why = cod_ps_age.unit_figures(row, cols)
    if got is None:
        raise SystemExit(f"turkey_districts: {where}: {why}")
    women = cod_ps_age.number(row.get(cols["totals"]["F"]))
    men = cod_ps_age.number(row.get(cols["totals"]["M"]))
    total = cod_ps_age.number(row.get(cols["totals"].get("T"))) if "T" in cols["totals"] \
        else women + men
    if abs(women + men - total) > SLACK or abs(got["aged"] + got["unstated"] - total) > SLACK:
        raise SystemExit(f"turkey_districts: {where}: women {women:,.0f} and men "
                         f"{men:,.0f}, ages {got['aged']:,.0f}, against {total:,.0f}")
    return {"total": total, "women": women, "men": men, "median": got["median"],
            "groups": age_groups(row, cols)}


def age_groups(row: dict[str, Any], cols: dict[str, Any]) -> list[tuple[int, int | None, float]]:
    out = []
    for low, high in sorted(cols["groups"][cols["sexes"][0]]):
        out.append((low, high, sum(cod_ps_age.number(row.get(cols["groups"][s][(low, high)]))
                                   for s in cols["sexes"])))
    low, _ = cols["opens"][cols["sexes"][0]]
    out.append((low, None, sum(cod_ps_age.number(row.get(cols["opens"][s][1]))
                              for s in cols["sexes"])))
    return out


def bind(rows: list[dict[str, Any]], admin1: list[dict[str, Any]],
         admin2: list[dict[str, Any]]) -> tuple[dict[str, str], list[str], list[str]]:
    """{row pcode: shape id}, and the rows and polygons left over."""
    province = {u["id"]: fold(u["name"]) for u in admin1}
    shapes: dict[tuple[str, str], list[str]] = defaultdict(list)
    for u in admin2:
        key = (province.get(u["parent"], ""), fold(u["name"]))
        shapes[(key[0], ALIASES.get(key, key[1]))].append(u["id"])
    out: dict[str, str] = {}
    left_rows = []
    for row in rows:
        key = (fold(row["province"]), fold(row["name"]))
        hits = shapes.get(key, [])
        if len(hits) == 1 and hits[0] not in out.values():
            out[row["pcode"]] = hits[0]
        else:
            left_rows.append(f"{row['name']} ({row['province']}): {len(hits)} polygons")
    taken = set(out.values())
    left_shapes = sorted(f"{u['name']} ({u['parent']})" for u in admin2 if u["id"] not in taken)
    return out, left_rows, left_shapes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    package = cod_ps.get("package_show", id=STUB)
    if not cod_ps.is_usable(package):
        raise SystemExit(f"turkey_districts: {STUB}'s licence is {cod_ps.licence(package)}")
    by_level: dict[str, dict[str, Any]] = {}
    for table in cod_ps_age.tables(package):
        cols = cod_ps_age.age_columns(table["columns"])
        if cols is not None and table["label"].lower().endswith(".csv"):
            by_level[table["level"]] = {**table, "cols": cols}
    if not {"1", "2"} <= set(by_level):
        raise SystemExit(f"turkey_districts: tables by level {sorted(by_level)}, "
                         "not the provinces and districts")
    log(f"  {STUB}: " + ", ".join(f"level {k}: {v['label']} ({len(v['rows'])} rows)"
                                  for k, v in sorted(by_level.items())))

    # Provinces, and the country as their sum.
    t1 = by_level["1"]
    p_name = columns_of(t1, "ADM1_EN", "ADM1_TR")
    provinces = {}
    for row in t1["rows"]:
        provinces[str(row[p_name]).strip()] = figures(row, t1["cols"], str(row[p_name]))
    # Districts.
    t2 = by_level["2"]
    d_name, d_prov = columns_of(t2, "ADM2_EN", "ADM2_TR"), columns_of(t2, "ADM1_EN", "ADM1_TR")
    d_code = columns_of(t2, "ADM2_PCODE")
    rows = []
    made: dict[str, float] = defaultdict(float)
    for row in t2["rows"]:
        name, prov = str(row[d_name]).strip(), str(row[d_prov]).strip()
        f = figures(row, t2["cols"], f"{name} ({prov})")
        rows.append({"name": name, "province": prov, "pcode": str(row[d_code]).strip(), **f})
        made[prov] += f["total"]
    for prov, fig in provinces.items():
        if abs(made.get(prov, 0) - fig["total"]) > SLACK:
            raise SystemExit(f"turkey_districts: {prov}'s districts make {made.get(prov, 0):,.0f}, "
                             f"the province {fig['total']:,.0f}")
    country = sum(f["total"] for f in provinces.values())
    log(f"  {len(rows)} districts make their {len(provinces)} provinces, and these the "
        f"country's {country:,.0f}; every row's sexes and age groups make its total")
    whole: dict[tuple[int, int | None], float] = defaultdict(float)
    for f in provinces.values():
        for low, high, n in f["groups"]:
            whole[(low, high)] += n
    groups = sorted(((lo, hi, n) for (lo, hi), n in whole.items()),
                    key=lambda g: (g[1] is None, g[0]))
    check_median("TR", YEAR + 1, cod_ps_age.grouped_median(groups),
                 "turkey_districts: the country (the register on 31 December 2022)")

    admin1 = json.loads((SITE / "admin1" / "TUR.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "TUR.units.json").read_text())
    shape_of, left_rows, left_shapes = bind(rows, admin1, admin2)
    log(f"  {len(shape_of)} of {len(rows)} districts bound to the map's {len(admin2)} "
        f"polygons; rows left: {left_rows}; polygons left: {left_shapes}")
    source = SOURCE.format(stub=STUB)
    page = cod_ps.DATASET_PAGE.format(stub=STUB)
    universe = (" The register's resident population; Syrians under temporary protection "
                "are not in it.")
    records = []
    for row in rows:
        sid = shape_of.get(row["pcode"])
        if not sid:
            continue
        records.append(record(
            f"TUR-ADNKS-{row['pcode']}", row["name"], level="admin2", parent="TUR",
            country="TUR", match_by="shape_id", shape_id=sid,
            population=measure(int(row["total"]), year=YEAR, source=source),
            population_note=("TÜİK's address-based register for 31 December 2022, as OCHA's "
                             "COD-PS tabulates it." + universe),
            median_age=measure(row["median"], unit="years", year=YEAR, source=source),
            median_age_note=("Interpolated within the five-year age group holding the middle "
                             "person, the finest grouping published for a district (to 90 "
                             "and over)." + universe),
            sex_ratio=measure(round(100 * row["men"] / row["women"], 1),
                              unit="males_per_100_females", year=YEAR, source=source),
            sex_ratio_note=(f"{int(row['men']):,} men and {int(row['women']):,} women in the "
                            "register." + universe),
            sources=[{"field": f, "name": source, "url": page,
                      "license": cod_ps.licence(package), "year": YEAR}
                     for f in ("population", "median_age", "sex_ratio")]))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
