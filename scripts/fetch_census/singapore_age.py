#!/usr/bin/env python3
"""Singapore: median age and sex ratio by planning area, Census of Population 2020.

The Department of Statistics publishes the census's planning-area tables on
data.gov.sg (``singapore_areas.py`` reads ethnicity, religion and language
from there the same way), among them

    Resident Population by Planning Area/Subzone of Residence, Age Group and
    Sex (Census of Population 2020)            -- d_d95ae740c0f8961a0b10435836660ce0

every planning area and subzone by five-year age group and sex, the counts
rounded to the nearest ten as the census rounds all its small-area figures.
``--fetch`` reads the table into ``data/raw/singapore/`` with
``singapore_areas.fetch_extract``, and the adapter reads that CSV, so what was
served is committed beside the code that read it.

Each planning area's **median age** is interpolated within the five-year
group holding the middle resident (nothing finer is published by area), and
its **sex ratio** is males per 100 females. An area with fewer than
``MIN_RESIDENTS`` residents gets neither: groups rounded to tens say little
about forty people, and several such areas are industrial or military land
with a handful of residents; their records say so. The areas are matched to
the 55 the map draws by name, through ``singapore_areas.AREA_REGION``.

**Checks**, each a refusal: the table's national row is the census's
4,044,210 residents; every area's groups and its sexes make its total within
the rounding (one ten per cell); and the national median from the national
row's groups is within 0.3 years of the 41.5 the census report gives.

Usage:
    python -m scripts.fetch_census.singapore_age --fetch   # on the runner
    python -m scripts.fetch_census.singapore_age
"""

from __future__ import annotations

import argparse
import csv
import re
from typing import Any

from . import singapore_areas as sa
from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, record, write_json
from .sea_common import age_sex, band, drawn, fold, grouped

OUT = "singapore_age.json"
YEAR = 2020
DATASET = "d_d95ae740c0f8961a0b10435836660ce0"
CSV = sa.RAW_DIR / "age_sex_planning_area_census2020.csv"
SOURCE = (f"{sa.CENSUS}: resident population by planning area/subzone of residence, age "
          "group and sex (data.gov.sg)")
NATIONAL = 4_044_210
NATIONAL_MEDIAN = 41.5        # Census of Population 2020, Statistical Release 1
MEDIAN_TOLERANCE = 0.3
MIN_RESIDENTS = 1_000
COLUMN = re.compile(r"^(?P<age>.+?)_(?P<sex>Total|Males|Females)$")
SMALL_NOTE = ("The census counts fewer than {n} residents here ({people:,}, rounded to "
              "the nearest ten in every cell): too few for a median or a ratio worth "
              "printing from groups rounded to tens.")


def columns(header: list[str]) -> tuple[dict[str, str], dict[tuple[int, int | None], dict[str, str]]]:
    totals: dict[str, str] = {}
    groups: dict[tuple[int, int | None], dict[str, str]] = {}
    for name in header:
        m = COLUMN.match(name.strip())
        if not m:
            continue
        label = m.group("age")
        if label == "Total":
            totals[m.group("sex")] = name
            continue
        label = re.sub(r"(\d+)\s*_?\s*and\s*_?\s*over", r"\1 and over", label, flags=re.I)
        label = label.replace("_", "-")
        b = band(label)
        if b is None:
            raise SystemExit(f"singapore_age: an age column the reader does not know: {name!r}")
        groups.setdefault(b, {})[m.group("sex")] = name
    if set(totals) != {"Total", "Males", "Females"} or not groups:
        raise SystemExit(f"singapore_age: no Total/Males/Females columns in {header[:8]}")
    bands = sorted(groups)
    for i, (low, high) in enumerate(bands):
        if low != (0 if i == 0 else bands[i - 1][1] + 1) or (high is None) != (i == len(bands) - 1):
            raise SystemExit(f"singapore_age: the age groups do not run from 0 to an open "
                             f"top: {bands}")
    return totals, groups


def read(path=CSV) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"singapore_age: missing extract {path}; run with --fetch")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    totals, groups = columns(list(rows[0]))
    areas: dict[str, dict[str, Any]] = {}
    national = None
    for row in rows:
        name = (row.get("Number") or "").strip()
        is_total = name.lower() == "total"
        if not is_total and not name.endswith("- Total"):
            continue                       # a subzone; its area's row has it
        unit = {"total": sa.cell(row[totals["Total"]]) or 0,
                "men": sa.cell(row[totals["Males"]]) or 0,
                "women": sa.cell(row[totals["Females"]]) or 0,
                "groups": [(lo, hi, sa.cell(row[cols["Total"]]) or 0)
                           for (lo, hi), cols in sorted(groups.items())]}
        if is_total:
            national = unit
            continue
        areas[name[: -len("- Total")].strip()] = unit
    if national is None or national["total"] != NATIONAL:
        raise SystemExit(f"singapore_age: the national row is "
                         f"{national and national['total']}, not the census's {NATIONAL:,}")
    unknown = sorted(set(areas) - set(sa.AREA_REGION))
    if unknown:
        raise SystemExit(f"singapore_age: areas in no declared region: {unknown}")
    for name, u in areas.items():
        made = sum(n for _, _, n in u["groups"])
        slack = 10 * len(u["groups"])
        if abs(made - u["total"]) > slack or abs(u["men"] + u["women"] - u["total"]) > 20:
            raise SystemExit(f"singapore_age: {name}: groups make {made:,}, sexes "
                             f"{u['men'] + u['women']:,}, against {u['total']:,}")
    median = grouped(national["groups"])
    if median is None or abs(median - NATIONAL_MEDIAN) > MEDIAN_TOLERANCE:
        raise SystemExit(f"singapore_age: the national median from the groups is {median}, "
                         f"against the census's {NATIONAL_MEDIAN}")
    log(f"  {len(areas)} planning areas, each one's groups and sexes making its total within "
        f"the rounding; national median {median} from the groups, the census's "
        f"{NATIONAL_MEDIAN}")
    return areas, national


def build(areas: dict[str, dict[str, Any]], admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {fold(u["name"]): u for u in admin2}
    src = [{"field": "median_age/sex_ratio", "name": SOURCE,
            "url": sa.DATAGOVSG_PAGE.format(id=DATASET), "year": YEAR,
            "license": "Singapore Open Data Licence"}]
    out = []
    for name, u in sorted(areas.items()):
        shape = by_name.get(fold(name))
        if shape is None:
            raise SystemExit(f"singapore_age: no polygon for the planning area {name!r}")
        if u["total"] < MIN_RESIDENTS:
            note = SMALL_NOTE.format(n=MIN_RESIDENTS, people=int(u["total"]))
            fields = {"median_age": gap(NOT_AVAILABLE, note), "sex_ratio": gap(NOT_AVAILABLE, note)}
        else:
            median = grouped(u["groups"])
            whose = f"the 2020 census's count of {name}'s residents"
            fields = age_sex(median=median, men=u["men"], women=u["women"], year=YEAR,
                             source=SOURCE,
                             median_note=(f"Interpolated within the five-year age group that "
                                          f"holds the middle resident, from {whose} by "
                                          f"five-year age group (rounded to tens); nothing "
                                          f"finer is published by planning area."),
                             ratio_note=f"Males per 100 females among {whose}.")
        out.append(record(f"SGP-AGE-{fold(name)}", shape["name"], level="admin2", parent="SGP",
                          country="SGP", match_by="shape_id", shape_id=shape["id"],
                          sources=src, **fields))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="read the table from data.gov.sg first")
    args = ap.parse_args()
    log(f"singapore_age: {SOURCE}")
    if args.fetch:
        sa.fetch_extract(DATASET, CSV)
        with CSV.open(newline="", encoding="utf-8-sig") as handle:
            head = [next(handle) for _ in range(3)]
        log("  " + "  ".join(line.strip()[:400] for line in head))
    areas, _ = read()
    records = build(areas, drawn("SGP", "admin2"))
    aged = [r for r in records if "value" in r["median_age"]]
    log(f"  {len(aged)} of {len(records)} planning areas with a median and a ratio")
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
