#!/usr/bin/env python3
"""Chad -- the provinces' 2023 projected population, the departments' 2024 one, and their seats.

* **Provinces.** OCHA's Common Operational Dataset for Chad (cod-ps-tcd) gives
  each of the 23 provinces' projected population for 2023 (tcd_admpop_adm1_2023,
  the national statistics office's projection from the 2009 census). The
  departments' figures are OCHA's for 2021, so without this the provinces
  show their departments' 2021 total, and N'Djamena, whose one department is
  drawn askew of the province (its polygon covers 284 of the province's 378
  km2 and reaches 73 km2 beyond it), an encyclopaedia's figure for 2012.
* **The provinces' ages.** The same table's age groups give OCHA's medians
  (cod_ps_age), and two of its provinces' structures are not their own. Ennedi
  Est and Ennedi Ouest carry one structure, within 0.01 of a point in every
  five-year group, and one proportion of men (1,139 per 1,000 women); and
  Guéra's 10-14 group is 3.6 times its 5-9 group, which no population's ages
  are. Their records say so, and the statement displaces OCHA's figures
  (``displaces_before``). The test is pairwise across the provinces at
  SAME_STRUCTURE points, far below the 0.26 that separates the closest
  distinct pair (Chari-Baguirmi and Hadjer-Lamis), and a cohort more than
  COHORT_JUMP times the one below it among the young.
* **Departments.** OCHA's 2024 table (tchad_populationdutchad_20240102.xlsx,
  Population_Projection_2024) gives every department a projected figure; it
  raises each department's 2021 figure by one proportion (checked here
  against cod_ps_admin2's 2021 rows, and said on each record).
* **Seats.** English Wikipedia's *Departments of Chad* names each
  department's capital; it is written for the department it names, matched by
  name across the country (no two departments share one). A department the
  list names without a seat, and one it does not list, say which.

Usage:
    python -m scripts.fetch_census.chad_departments [--run LABEL]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import fold
from .cod_ps_age import age_columns, age_shares, unit_figures

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import tables  # noqa: E402

DATASET = "https://data.humdata.org/dataset/5e60290d-0a82-48e2-9454-812b01c7d9d4"
ADM1 = DATASET + "/resource/fb3d793e-57c5-4fb9-b361-8d4222fd254e/download/tcd_admpop_adm1_2023.csv"
ADM2_2024 = (DATASET + "/resource/f026a982-b530-4e49-97a3-f54bbc5bad5d/download/"
             "tchad_populationdutchad_20240102.xlsx")
YEAR = 2023
OUT = "chad_departments.json"
SITE = PROCESSED.parent.parent / "site" / "data"
OCHA = "OCHA, Common Operational Dataset -- population statistics (cod-ps-tcd), reference year 2023"
OCHA_URL = "https://data.humdata.org/dataset/cod-ps-tcd"
OCHA_LICENCE = "Creative Commons Attribution for Intergovernmental Organisations (CC BY-IGO)"
WIKI_TITLE = "Departments of Chad"
WIKI_URL = "https://en.wikipedia.org/wiki/Departments_of_Chad"
NATIONAL_MIN = 18_000_000
# Two provinces whose age proportions agree to within this many points in every
# five-year group carry one structure between them; the closest distinct pair
# in OCHA's 2023 table differs by 0.26 somewhere, the copied one by 0.002.
SAME_STRUCTURE = 0.05
# A five-year group under 20 more than this many times the group below it.
COHORT_JUMP = 1.5
# The 2024 table's spellings, where they differ from the polygons' (the table
# cuts the name short).
SPELLED_2024 = {"barhelgazeloues": "Barh-El-Gazel Ouest"}


def key(name: str) -> str:
    """A name folded, 'Bahr' and 'Barh' (both spellings are in use) made one, 'Region' dropped."""
    k = fold(re.sub(r"\(.*?\)", " ", name or ""))
    return k.replace("bahr", "barh").removesuffix("region")


def plain_seat(text: str) -> str:
    """'3=Maro (Tchad)' -> 'Maro'; 'Ngouri (N'Gouri)' -> 'Ngouri'."""
    text = re.sub(r"^\d+=", "", text.strip())
    return re.sub(r"\s*\(.*?\)\s*$", "", text).strip()


def seats(wikitext: str) -> dict[str, str]:
    """Department (key) -> seat, from the article's first table naming both."""
    return listed_seats(wikitext)[0]


def listed_seats(wikitext: str) -> tuple[dict[str, str], set[str]]:
    """Department (key) -> seat, and every department the article's tables list."""
    out: dict[str, str] = {}
    listed: set[str] = set()
    for table in tables(wikitext):
        if not table:
            continue
        head = [fold(c) for c in table[0]]
        dep = next((i for i, c in enumerate(head) if c == "department"), None)
        seat = next((i for i, c in enumerate(head) if c == "capital"), None)
        if dep is None or seat is None:
            continue
        for row in table[1:]:
            if len(row) <= dep:
                continue
            names = [row[dep]] + re.findall(r"\((.*?)\)", row[dep])
            listed |= {key(name) for name in names if key(name)}
            if len(row) <= seat or not plain_seat(row[seat]):
                continue
            for name in names:
                out.setdefault(key(name), plain_seat(row[seat]))
    return out, listed


def structures(adm1: list[dict[str, str]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Province (key) -> the fields to withdraw from OCHA's table and why; and the report."""
    cols = age_columns(list(adm1[0].keys())) if adm1 else None
    if cols is None:
        return {}, ["  ages: the 2023 table has no age groups; nothing tested"]
    figures: dict[str, tuple[str, dict[str, Any]]] = {}
    for row in adm1:
        found, _ = unit_figures(row, cols)
        if found:
            figures[key(row["ADM1_NAME"])] = (row["ADM1_NAME"], found)
    out: dict[str, dict[str, Any]] = {}
    report: list[str] = []
    keys = sorted(figures)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            (na, fa), (nb, fb) = figures[a], figures[b]
            sa, sb = age_shares(fa["groups"]), age_shares(fb["groups"])
            if not sa or not sb or len(sa) != len(sb):
                continue
            gap_ = max(abs(x - y) for x, y in zip(sa, sb))
            if gap_ >= SAME_STRUCTURE:
                if gap_ < 0.3:
                    report.append(f"  ages: {na} and {nb} alike ({gap_:.2f} points at most), "
                                  f"not one structure")
                continue
            same_ratio = abs(fa["ratio"] - fb["ratio"]) <= 2
            report.append(f"  ages: {na} and {nb} share one structure ({gap_:.4f} points at most)"
                          + (f" and one sex ratio ({fa['ratio']})" if same_ratio else ""))
            for k, (own, other) in ((a, (na, nb)), (b, (nb, na))):
                why = (f"OCHA's population table for Chad (reference year {YEAR}) gives "
                       f"{own} and {other} the same age proportions, to within "
                       f"{SAME_STRUCTURE:.2f} of a point in every five-year group")
                out.setdefault(k, {})["median_age"] = (
                    f"{why}: one structure applied to both provinces, so no median age of "
                    f"{own}'s own can be taken from it.")
                if same_ratio:
                    out[k]["sex_ratio"] = (
                        f"{why}, and the same proportion of men ({fa['ratio']:,} per 1,000 "
                        f"women): one structure applied to both provinces, so no sex ratio "
                        f"of {own}'s own can be taken from it.")
    for k, (name, found) in figures.items():
        groups = found["groups"]
        for (lo0, _, n0), (lo1, hi1, n1) in zip(groups, groups[1:]):
            if lo1 < 20 and n0 > 0 and n1 > COHORT_JUMP * n0:
                report.append(f"  ages: {name}'s {lo1}-{hi1} group is {n1 / n0:.1f} times "
                              f"its {lo0}-{lo1 - 1} group")
                out.setdefault(k, {})["median_age"] = (
                    f"OCHA's population table for Chad (reference year {YEAR}) gives {name} "
                    f"{n1:,.0f} people aged {lo1} to {hi1} against {n0:,.0f} aged {lo0} to "
                    f"{lo1 - 1}, {n1 / n0:.1f} times as many, which no population's ages are, "
                    f"so no median age is taken from it.")
                break
    return out, report


def departments_2024(rows: list[list[Any]], previous: dict[str, int], admin2: list[dict[str, Any]]
                     ) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Polygon id -> the 2024 figure and its note; and the report."""
    head = [str(c or "").strip() for c in rows[0]]
    name_col = head.index("ADM2_NAME")
    pop_col = next(i for i, h in enumerate(head) if h.lower().startswith("population_proj"))
    year_found = re.search(r"(20\d\d)", head[pop_col])
    year = int(year_found.group(1)) if year_found else 2024
    polys = {key(u["name"]): u for u in admin2}
    figures: dict[str, tuple[str, int]] = {}
    report: list[str] = []
    for row in rows[1:]:
        name = str(row[name_col] or "").strip() if len(row) > name_col else ""
        value = row[pop_col] if len(row) > pop_col else None
        if not name or not isinstance(value, (int, float)):
            continue
        k = key(SPELLED_2024.get(key(name), name))
        if k not in polys:
            report.append(f"  2024: {name}: no polygon")
            continue
        figures[polys[k]["id"]] = (polys[k]["name"], round(value))
    ratios = {sid: v / previous[k] for sid, (n, v) in figures.items()
              if (k := key(n)) in previous and previous[k]}
    factor = statistics.median(ratios.values()) if ratios else None
    uniform = bool(ratios) and all(abs(r - factor) <= 0.001 for r in ratios.values())
    report.append(f"  2024: {len(figures)} departments; against 2021, x{factor:.4f}"
                  + (" for every one" if uniform else " at the median") if factor else
                  f"  2024: {len(figures)} departments")
    out: dict[str, dict[str, Any]] = {}
    for sid, (name, value) in figures.items():
        note = f"OCHA's projected population of {name} for {year} (cod-ps-tcd)"
        if uniform:
            note += (f", which raises every department's {year - 3} projection by the same "
                     f"proportion ({100 * (factor - 1):.1f}%)")
        out[sid] = {"value": value, "year": year, "note": note + "."}
    return out, report


def build(adm1: list[dict[str, str]], seat_of: dict[str, str], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]], listed: set[str] | None = None,
          counts_2024: dict[str, dict[str, Any]] | None = None
          ) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    records: list[dict[str, Any]] = []
    first = {key(u["name"]): u for u in admin1}
    cite = [{"field": "population", "name": OCHA, "url": OCHA_URL, "year": YEAR,
             "license": OCHA_LICENCE}]
    withdrawn, why = structures(adm1)
    report += why
    total = 0
    for row in adm1:
        poly = first.get(key(row["ADM1_NAME"]))
        people = int(float(row["T_TL"]))
        total += people
        if poly is None:
            raise SystemExit(f"chad_departments: no polygon for province {row['ADM1_NAME']}")
        fields: dict[str, Any] = {}
        for field, note in withdrawn.get(key(row["ADM1_NAME"]), {}).items():
            # The statement displaces OCHA's own figure for the field, which
            # cod_ps_age took from this table.
            fields[field] = {**gap(NOT_AVAILABLE, note), "displaces_before": YEAR + 1}
        sources = cite
        if fields:
            notes = "/".join(f"{f} note" for f in fields)
            sources = [{**cite[0], "field": f"population/{notes}"}]
        records.append(record(
            f"TCD-CODPS2023-{poly['id']}", poly["name"], level="admin1", parent="TCD",
            country="TCD", match_by="shape_id", shape_id=poly["id"], sources=sources,
            population=measure(people, year=YEAR, source=OCHA),
            population_note=(f"The projected population of {poly['name']} for 2023, from OCHA's "
                             f"population statistics for Chad."), **fields))
        report.append(f"  {poly['name']}: {people:,}"
                      + (f" ({', '.join(fields)} withdrawn)" if fields else ""))
    if len(records) != len(admin1) or total < NATIONAL_MIN:
        raise SystemExit(f"chad_departments: {len(records)} provinces making {total:,}")
    report.append(f"  the provinces make {total:,}")
    seat_cite = {"field": "capital", "name": f"English Wikipedia, {WIKI_TITLE}", "url": WIKI_URL,
                 "license": "CC BY-SA 4.0"}
    listed = listed if listed is not None else set(seat_of)
    counts_2024 = counts_2024 or {}
    seated = 0
    for u in admin2:
        extra: dict[str, Any] = {}
        sources: list[dict[str, Any]] = []
        if u["id"] in counts_2024:
            found = counts_2024[u["id"]]
            extra = {"population": measure(found["value"], year=found["year"],
                                           source=OCHA.replace("2023", str(found["year"]))),
                     "population_note": found["note"]}
            sources.append({**cite[0], "name": OCHA.replace("2023", str(found["year"])),
                            "year": found["year"]})
        if key(u["name"]) == "ndjamena":
            # The capital's province is one department, the city itself.
            records.append(record(
                f"TCD-SEAT-{u['id']}", u["name"], level="admin2", parent="TCD", country="TCD",
                match_by="shape_id", shape_id=u["id"], capital="N'Djamena", sources=sources,
                capital_note=("N'Djamena province is a single department, the city of "
                              "N'Djamena, whose seat is the city itself."), **extra))
            seated += 1
            continue
        seat = seat_of.get(key(u["name"]))
        if not seat:
            if key(u["name"]) in listed:
                why_not = ("English Wikipedia's list of Chad's departments and their seats "
                           "(Departments of Chad) names this department but gives no seat for "
                           "it, and no other published list of the departments' seats has been "
                           "found.")
            else:
                why_not = ("English Wikipedia's list of Chad's departments and their seats "
                           "(Departments of Chad) does not include this department, and no "
                           "other published list of the departments' seats has been found.")
            report.append(f"    {u['name']}: no seat named"
                          + ("" if key(u["name"]) in listed else " (not listed)"))
            records.append(record(
                f"TCD-SEAT-{u['id']}", u["name"], level="admin2", parent="TCD", country="TCD",
                match_by="shape_id", shape_id=u["id"], sources=sources,
                capital=gap(NOT_AVAILABLE, why_not), **extra))
            continue
        records.append(record(
            f"TCD-SEAT-{u['id']}", u["name"], level="admin2", parent="TCD", country="TCD",
            match_by="shape_id", shape_id=u["id"], capital=seat,
            sources=[seat_cite] + sources, **extra))
        seated += 1
    report.append(f"  {seated} of {len(admin2)} departments with a seat")
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    import openpyxl                                  # noqa: PLC0415
    from .europe_wiki import fetch as wiki_fetch     # noqa: PLC0415
    text = http_get(ADM1, binary=True, cache=False, timeout=180).decode("utf-8").lstrip("﻿")
    adm1 = list(csv.DictReader(io.StringIO(text)))
    log(f"chad_departments: OCHA's 2023 table, {len(adm1)} provinces")
    wikitext, landed = wiki_fetch(WIKI_TITLE, "en")
    seat_of, listed = listed_seats(wikitext)
    log(f"  {landed}: {len(seat_of)} names with a seat, {len(listed)} listed")
    admin1 = json.loads((SITE / "admin1" / "TCD.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "TCD.units.json").read_text())
    blob = http_get(ADM2_2024, binary=True, cache=False, timeout=180)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rows = [list(r) for r in book.worksheets[0].iter_rows(values_only=True)]
    previous = {key(r["name"]): r["population"]["value"]
                for r in json.loads((PROCESSED / "cod_ps_admin2.json").read_text())
                if str(r.get("id", "")).startswith("TCD-")
                and isinstance(r.get("population"), dict) and "value" in r["population"]}
    counts_2024, why = departments_2024(rows, previous, admin2)
    for line in why:
        log(line)
    records, report = build(adm1, seat_of, admin1, admin2, listed, counts_2024)
    for line in report:
        log(line)
    write_json(PROCESSED / OUT, records)
    log(f"  {len(records)} records written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
