#!/usr/bin/env python3
"""Senegal -- the 2023 census (RGPH-5) by region and department.

ANSD's demographic projections workbook for 2023-2050 opens with the census
year itself: for every region and department, the RGPH-5 2023 count of men,
women and everyone, then the projected years. Only the 2023 columns are read.

**Checks before anything is written.** The header names the first columns
RGPH-5 2023; every row's men and women make its total; each region's
departments make the region; the regions make the census's national total,
18,126,390.

**Binding.** The map draws the 45 departments of 2013-2021. Keur Massar
department was made in 2021 from communes of Pikine and Rufisque, whose drawn
outlines are the older ones: the 2023 counts of those three departments do not
describe either polygon, so neither is bound (and the log says so). Every
other department is bound within its region by name; ALIASES holds the
spellings no reduction joins. The regions are bound whole.

Usage:
    python -m scripts.fetch_census.senegal_rgph5
"""

from __future__ import annotations

import argparse
import io
import json
import re
import unicodedata
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json

URL = "https://www.ansd.sn/sites/default/files/2024-11/Projections-demographiques_2023-2050.xlsx"
PAGE = "https://www.ansd.sn/node/13519"
SOURCE = ("Agence Nationale de la Statistique et de la Démographie (ANSD), Cinquième "
          "Recensement Général de la Population et de l'Habitat (RGPH-5) 2023, population by "
          "region and department (Projections démographiques 2023-2050, base year)")
LICENCE = "ANSD publication (reuse with attribution)"
YEAR = 2023
NATIONAL = 18_126_390
OUT = "senegal_rgph5.json"
SITE = PROCESSED.parent.parent / "site" / "data"

# The boundary file's folded label -> the workbook's.
ALIASES = {"medinayoroufoula": "medinayorofoulah", "tivaoune": "tivaouane",
           "niorodurip": "nioro", "birkelane": "mbirkilane", "malemhodar": "malemhoddar"}
# Departments whose drawn outline is not the 2023 department's.
REDRAWN = {"pikine", "rufisque", "keurmassar"}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = re.sub(r"(?i)^\s*(?:region|departement|département)\s+(?:de\s+)?", "",
                  "".join(c for c in text if not unicodedata.combining(c)))
    return "".join(c for c in text.lower() if "a" <= c <= "z")


def key(text: str) -> str:
    k = fold(text)
    return ALIASES.get(k, k)


def number(cell: Any) -> int | None:
    if isinstance(cell, bool) or cell is None:
        return None
    if isinstance(cell, (int, float)):
        return int(round(cell))
    text = re.sub(r"[\s  ]", "", str(cell))
    return int(text) if text.isdigit() else None


def parse(rows: list[list[Any]]) -> dict[str, Any]:
    """{"regions": {key: row}, "departments": {key: row}} from the sheet's rows;
    a department row carries its region's key."""
    if not any("2023" in str(c or "") for row in rows[:3] for c in row[1:3]):
        raise SystemExit("senegal_rgph5: the first columns are not headed RGPH-5 2023")
    out: dict[str, Any] = {"regions": {}, "departments": {}}
    region = None
    for row in rows:
        cells = list(row) + [None] * 4
        name = " ".join(str(cells[0] or "").split())
        men, women, total = number(cells[1]), number(cells[2]), number(cells[3])
        if not name or None in (men, women, total):
            continue
        kind = unicodedata.normalize("NFKD", name.split()[0]).encode("ascii", "ignore").lower()
        if kind not in (b"region", b"departement"):
            continue
        if men + women != total:
            raise SystemExit(f"senegal_rgph5: {name}: {men:,} men and {women:,} women do not "
                             f"make {total:,}")
        entry = {"name": name, "total": total, "men": men, "women": women}
        if kind == b"region":
            region = key(name)
            out["regions"][region] = entry
        else:
            if region is None:
                raise SystemExit(f"senegal_rgph5: {name} comes before any region")
            entry["region"] = region
            out["departments"][key(name)] = entry
    check(out)
    return out


def check(table: dict[str, Any]) -> None:
    made = sum(r["total"] for r in table["regions"].values())
    if made != NATIONAL:
        raise SystemExit(f"senegal_rgph5: the {len(table['regions'])} regions make {made:,}, "
                         f"not {NATIONAL:,}")
    for k, region in table["regions"].items():
        rows = [d for d in table["departments"].values() if d["region"] == k]
        for field in ("total", "men", "women"):
            if sum(d[field] for d in rows) != region[field]:
                raise SystemExit(f"senegal_rgph5: {region['name']}'s {len(rows)} departments do "
                                 f"not make its {field}")


def fields(row: dict[str, Any], note: str) -> dict[str, Any]:
    return {"population": measure(row["total"], year=YEAR, source=SOURCE),
            "population_note": note,
            "sex_ratio": measure(round(1000 * row["men"] / row["women"]),
                                 unit="males_per_1000_females", year=YEAR, source=SOURCE),
            "sources": [{"field": "population/sex_ratio", "name": SOURCE, "url": URL,
                         "page": PAGE, "license": LICENCE, "year": YEAR}]}


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    report: list[str] = []
    region_of: dict[str, str] = {}
    for shape in admin1:
        k = key(shape["name"])
        row = table["regions"].get(k)
        if row is None:
            report.append(f"region polygon {shape['name']!r} ({k}): no RGPH-5 region")
            continue
        region_of[shape["id"]] = k
        records.append(record(f"SEN-RGPH5-{k}", shape["name"], level="admin1", parent="SEN",
                              country="SEN", match_by="shape_id", shape_id=shape["id"],
                              **fields(row, f"The 2023 census (RGPH-5) count for the region of "
                                            f"{shape['name']}.")))
    used: set[str] = set()
    for shape in admin2:
        k = key(shape["name"])
        row = table["departments"].get(k)
        region = region_of.get(shape["parent"])
        if k in REDRAWN:
            report.append(f"{shape['name']!r}: drawn on its outline before Keur Massar was "
                          "made from it; not bound")
            continue
        if row is None or k in used or row["region"] != region:
            report.append(f"{shape['name']!r} ({k}): no RGPH-5 department of that name in "
                          f"its region")
            continue
        used.add(k)
        records.append(record(f"SEN-RGPH5-{k}", shape["name"], level="admin2", parent="SEN",
                              country="SEN", match_by="shape_id", shape_id=shape["id"],
                              **fields(row, f"The 2023 census (RGPH-5) count for the department "
                                            f"of {shape['name']}.")))
    left = [d["name"] for k, d in table["departments"].items() if k not in used]
    report.append(f"RGPH-5 departments not bound: {left}")
    return records, report


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import openpyxl                                 # noqa: PLC0415
    blob = http_get(URL, binary=True, cache=False, timeout=120, aia=True)
    if blob[:2] != b"PK":
        raise SystemExit(f"senegal_rgph5: {URL} is not a workbook: {blob[:80]!r}")
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rows = [list(r) for r in book.worksheets[0].iter_rows(values_only=True)]
    table = parse(rows)
    log(f"  {len(table['regions'])} regions and {len(table['departments'])} departments, "
        f"making {NATIONAL:,}")
    admin1 = json.loads((SITE / "admin1" / "SEN.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "SEN.units.json").read_text())
    records, report = build(table, admin1, admin2)
    for line in report:
        log("  " + line)
    for k in ("medinayorofoulah", "saintlouis", "dagana", "podor", "tivaouane"):
        row = table["departments"].get(k)
        if row:
            log(f"  {row['name']}: {row['total']:,}")
    log(f"  {sum(1 for r in records if r['level'] == 'admin1')} regions and "
        f"{sum(1 for r in records if r['level'] == 'admin2')} of {len(admin2)} departments "
        "bound")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
