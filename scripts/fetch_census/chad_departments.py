#!/usr/bin/env python3
"""Chad -- the provinces' 2023 projected population and the departments' seats.

* **Provinces.** OCHA's Common Operational Dataset for Chad (cod-ps-tcd) gives
  each of the 23 provinces' projected population for 2023 (tcd_admpop_adm1_2023,
  the national statistics office's projection from the 2009 census). The
  departments' figures are OCHA's for 2021, so without this the provinces
  show their departments' 2021 total, and N'Djamena, whose one department is
  drawn askew of the province (its polygon covers 284 of the province's 378
  km2 and reaches 73 km2 beyond it), an encyclopaedia's figure for 2012.
* **Seats.** English Wikipedia's *Departments of Chad* names each
  department's capital; it is written for the department it names, matched by
  name across the country (no two departments share one).

Usage:
    python -m scripts.fetch_census.chad_departments [--run LABEL]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json
from .binding import fold

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import tables  # noqa: E402

DATASET = "https://data.humdata.org/dataset/5e60290d-0a82-48e2-9454-812b01c7d9d4"
ADM1 = DATASET + "/resource/fb3d793e-57c5-4fb9-b361-8d4222fd254e/download/tcd_admpop_adm1_2023.csv"
YEAR = 2023
OUT = "chad_departments.json"
SITE = PROCESSED.parent.parent / "site" / "data"
OCHA = "OCHA, Common Operational Dataset -- population statistics (cod-ps-tcd), reference year 2023"
OCHA_URL = "https://data.humdata.org/dataset/cod-ps-tcd"
OCHA_LICENCE = "Creative Commons Attribution for Intergovernmental Organisations (CC BY-IGO)"
WIKI_TITLE = "Departments of Chad"
WIKI_URL = "https://en.wikipedia.org/wiki/Departments_of_Chad"
NATIONAL_MIN = 18_000_000


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
    out: dict[str, str] = {}
    for table in tables(wikitext):
        if not table:
            continue
        head = [fold(c) for c in table[0]]
        dep = next((i for i, c in enumerate(head) if c == "department"), None)
        seat = next((i for i, c in enumerate(head) if c == "capital"), None)
        if dep is None or seat is None:
            continue
        for row in table[1:]:
            if len(row) <= max(dep, seat) or not plain_seat(row[seat]):
                continue
            names = [row[dep]] + re.findall(r"\((.*?)\)", row[dep])
            for name in names:
                out.setdefault(key(name), plain_seat(row[seat]))
    return out


def build(adm1: list[dict[str, str]], seat_of: dict[str, str], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    records: list[dict[str, Any]] = []
    first = {key(u["name"]): u for u in admin1}
    cite = [{"field": "population", "name": OCHA, "url": OCHA_URL, "year": YEAR,
             "license": OCHA_LICENCE}]
    total = 0
    for row in adm1:
        poly = first.get(key(row["ADM1_NAME"]))
        people = int(float(row["T_TL"]))
        total += people
        if poly is None:
            raise SystemExit(f"chad_departments: no polygon for province {row['ADM1_NAME']}")
        records.append(record(
            f"TCD-CODPS2023-{poly['id']}", poly["name"], level="admin1", parent="TCD",
            country="TCD", match_by="shape_id", shape_id=poly["id"], sources=cite,
            population=measure(people, year=YEAR, source=OCHA),
            population_note=(f"The projected population of {poly['name']} for 2023, from OCHA's "
                             f"population statistics for Chad.")))
        report.append(f"  {poly['name']}: {people:,}")
    if len(records) != len(admin1) or total < NATIONAL_MIN:
        raise SystemExit(f"chad_departments: {len(records)} provinces making {total:,}")
    report.append(f"  the provinces make {total:,}")
    seat_cite = {"field": "capital", "name": f"English Wikipedia, {WIKI_TITLE}", "url": WIKI_URL,
                 "license": "CC BY-SA 4.0"}
    seated = 0
    for u in admin2:
        if key(u["name"]) == "ndjamena":
            # The capital's province is one department, the city itself.
            records.append(record(
                f"TCD-SEAT-{u['id']}", u["name"], level="admin2", parent="TCD", country="TCD",
                match_by="shape_id", shape_id=u["id"], capital="N'Djamena",
                capital_note=("N'Djamena province is a single department, the city of "
                              "N'Djamena, whose seat is the city itself.")))
            seated += 1
            continue
        seat = seat_of.get(key(u["name"]))
        if not seat:
            report.append(f"    {u['name']}: no seat named")
            continue
        records.append(record(
            f"TCD-SEAT-{u['id']}", u["name"], level="admin2", parent="TCD", country="TCD",
            match_by="shape_id", shape_id=u["id"], capital=seat, sources=[seat_cite]))
        seated += 1
    report.append(f"  {seated} of {len(admin2)} departments with a seat")
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    from .europe_wiki import fetch as wiki_fetch     # noqa: PLC0415
    text = http_get(ADM1, binary=True, cache=False, timeout=180).decode("utf-8").lstrip("﻿")
    adm1 = list(csv.DictReader(io.StringIO(text)))
    log(f"chad_departments: OCHA's 2023 table, {len(adm1)} provinces")
    wikitext, landed = wiki_fetch(WIKI_TITLE, "en")
    seat_of = seats(wikitext)
    log(f"  {landed}: {len(seat_of)} names with a seat")
    admin1 = json.loads((SITE / "admin1" / "TCD.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "TCD.units.json").read_text())
    records, report = build(adm1, seat_of, admin1, admin2)
    for line in report:
        log(line)
    write_json(PROCESSED / OUT, records)
    log(f"  {len(records)} records written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
