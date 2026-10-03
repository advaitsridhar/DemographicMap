#!/usr/bin/env python3
"""Austria: nationality as ethnicity, by Land and political district, 1 January 2026.

Austria's register-based census asks no ethnicity question; the Central
Register of Residents (ZMR) records citizenship. By the owner's decision of 19
September 2026 that count is carried on the ethnicity field under
``ethnicity_basis: "nationality"`` (see ``central_nationality``).

**What is read.** Statistik Austria's table "Bevölkerung am 01.01.2026 nach
Staatsangehörigkeit bzw. Geburtsland und administrativen Gebietseinheiten"
(``Bev_Staatsangeh_Geburtsland_Gebietseinheiten_2026.ods``), sheet
"Staatsangehörigkeit": for Austria, its Länder, NUTS regions, political
districts (Vienna as its 23 Gemeindebezirke) and municipalities, the
population by citizenship in groups, with the largest foreign nationalities
named inside them ("darunter"): Germany; Croatia, Romania and Hungary; Bosnia
and Herzegovina, Serbia, Turkey and Ukraine; and Syria. Those ten, Austrians
among them, are named on the map; every other citizenship, the stateless and
the unknown are "Other nationalities".

**Where.** The Länder are the table's NUTS 2 rows. The districts are its
political districts, which are the 94 the map draws (``austria`` reads the same
division from the register of districts and binds it the same way); Vienna,
one district on the map, is its 23 Gemeindebezirke summed.

**Checks.** Every row's groups are checked against the table's own sums --
Austrians and non-Austrians make the total, EU/EFTA and third countries make
the non-Austrians, the continents make the third countries -- and a named
nationality inside its group may not exceed it; the districts make their
Länder and the Länder Austria.

Usage:
    python -m scripts.fetch_census.austria_nationality
"""

from __future__ import annotations

import argparse
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

from ._shared import PROCESSED, http_get, log, record, write_json
from .austria import LAENDER, REGISTER_ALIASES, VIENNA
from .central_ages import check_sum, fold, units
from .central_nationality import composition, note

URL = "https://www.statistik.at/fileadmin/pages/407/Bev_Staatsangeh_Geburtsland_Gebietseinheiten_2026.ods"
PAGE = ("https://www.statistik.at/statistiken/bevoelkerung-und-soziales/bevoelkerung/"
        "bevoelkerungsstand/bevoelkerung-nach-staatsangehoerigkeit/-geburtsland")
SOURCE = ("Statistik Austria, Bevölkerung am 01.01.2026 nach Staatsangehörigkeit bzw. Geburtsland "
          "und administrativen Gebietseinheiten (Statistik des Bevölkerungsstandes, from the ZMR)")
LICENCE = "CC BY 4.0 (Statistik Austria)"
OUT = PROCESSED / "austria_nationality.json"
YEAR = 2026
SHEET = "Staatsangehörigkeit"
EXPECTED_DISTRICTS = 94
# The sheet's columns, by position: code, name, then the counts.
COLUMNS = ("code", "name", "total", "AT", "foreign", "foreign_pct", "eu_efta", "eu", "eu14", "DE",
           "eu13", "HR", "RO", "HU", "efta", "third", "europe", "BA", "RS", "TR", "UA", "africa",
           "america", "north_america", "latin_america", "asia", "SY", "oceania", "unknown")
NAMED = {"AT": "Austrian", "DE": "German", "HR": "Croatian", "RO": "Romanian", "HU": "Hungarian",
         "BA": "Bosnian and Herzegovinian", "RS": "Serbian", "TR": "Turkish", "UA": "Ukrainian",
         "SY": "Syrian"}
# Each group and the parts that make it.
SUMS = {"total": ("AT", "foreign"), "foreign": ("eu_efta", "third"), "eu_efta": ("eu", "efta"),
        "eu": ("eu14", "eu13"), "third": ("europe", "africa", "america", "asia", "oceania", "unknown"),
        "america": ("north_america", "latin_america")}
# A named nationality and the group it is listed under.
INSIDE = {"DE": "eu14", "HR": "eu13", "RO": "eu13", "HU": "eu13", "BA": "europe", "RS": "europe",
          "TR": "europe", "UA": "europe", "SY": "asia"}


def ods_rows(blob: bytes, sheet: str) -> list[list[str]]:
    """One sheet of an OpenDocument spreadsheet as rows of cell texts, a numeric
    cell as its stored value, repeats expanded except the sheet's padding."""
    ns = {"table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
          "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
          "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0"}
    t, o = "{%s}" % ns["table"], "{%s}" % ns["office"]
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(blob)).read("content.xml"))
    for table in root.iter(f"{t}table"):
        if table.get(f"{t}name") != sheet:
            continue
        rows: list[list[str]] = []
        for row in table.iter(f"{t}table-row"):
            cells: list[str] = []
            for cell in row:
                if cell.tag not in (f"{t}table-cell", f"{t}covered-table-cell"):
                    continue
                kind, value = cell.get(f"{o}value-type"), cell.get(f"{o}value")
                words = " ".join("".join(p.itertext()) for p in cell.iter("{%s}p" % ns["text"]))
                content = value if kind in ("float", "percentage") and value else words
                repeat = int(cell.get(f"{t}number-columns-repeated", "1"))
                cells += [content] * (repeat if repeat <= 50 or content else 0)
            while cells and not cells[-1]:
                cells.pop()
            repeat = int(row.get(f"{t}number-rows-repeated", "1"))
            rows += [cells] * (repeat if repeat <= 50 or cells else 0)
        return rows
    raise SystemExit(f"austria_nationality: the workbook has no sheet {sheet!r}")


def read_rows(rows: list[list[str]]) -> dict[str, dict[str, Any]]:
    """{code: {"name", and every count column}} for the rows that open with a
    code: AT, NUTS codes, three-digit districts and five-digit municipalities."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not row or not re.fullmatch(r"AT\d{0,3}|\d{3}|\d{5}", str(row[0]).strip()):
            continue
        if len(row) < 6:
            raise SystemExit(f"austria_nationality: row {row[:2]} has {len(row)} cells, not "
                             f"{len(COLUMNS)}")
        # A row ending in empty cells is cut short by the sheet; those are zeros,
        # and the sums checked below say so if they were anything else.
        row = list(row) + [""] * (len(COLUMNS) - len(row))
        entry: dict[str, Any] = {"name": str(row[1]).strip()}
        for col, cell in zip(COLUMNS[2:], row[2:len(COLUMNS)]):
            if col == "foreign_pct":
                continue
            text = str(cell).strip().replace(" ", "")
            entry[col] = float(text) if text not in ("", "-") else 0.0
        out[str(row[0]).strip()] = entry
    return out


def check_row(code: str, entry: dict[str, Any]) -> None:
    for whole, parts in SUMS.items():
        made = sum(entry[p] for p in parts)
        if abs(made - entry[whole]) > 0.5:
            raise SystemExit(f"austria_nationality: {code} {entry['name']}: {', '.join(parts)} make "
                             f"{made:,.0f}, {whole} is {entry[whole]:,.0f}")
    for named, group in INSIDE.items():
        if entry[named] > entry[group] + 0.5:
            raise SystemExit(f"austria_nationality: {code}: {named} {entry[named]:,.0f} exceeds "
                             f"its group {group} {entry[group]:,.0f}")


def ethnicity(entry: dict[str, Any], where: str) -> list[dict[str, Any]]:
    counts = {k: entry[k] for k in NAMED}
    counts["__rest__"] = entry["total"] - sum(counts.values())
    return composition(counts, entry["total"], list(NAMED), {**NAMED, "__rest__": None},
                       where=where)


def summed(entries: list[dict[str, Any]], name: str) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name}
    for col in COLUMNS[2:]:
        if col != "foreign_pct":
            out[col] = sum(e[col] for e in entries)
    return out


NOTE = note("Population by citizenship (Staatsangehörigkeit)", "1 January 2026",
            "the Central Register of Residents' record of each resident's citizenship, as "
            "Statistik Austria tabulates it by administrative unit",
            extra=("The table names Austria's largest foreign nationalities inside their groups -- "
                   "German; Croatian, Romanian, Hungarian; Bosnian and Herzegovinian, Serbian, "
                   "Turkish, Ukrainian; Syrian -- and every other citizenship, the stateless and "
                   "the unknown are counted together."))


def build() -> list[dict[str, Any]]:
    log(f"austria_nationality: {URL.rsplit('/', 1)[-1]}, sheet {SHEET!r}")
    table = read_rows(ods_rows(http_get(URL, binary=True, timeout=300), SHEET))
    for code, entry in table.items():
        check_row(code, entry)
    national = table.get("AT")
    if national is None:
        raise SystemExit("austria_nationality: no row for Austria")
    laender = {code: e for code, e in table.items() if re.fullmatch(r"AT\d\d", code)}
    districts = {code: e for code, e in table.items() if re.fullmatch(r"\d{3}", code)}
    check_sum((e["total"] for e in laender.values()), national["total"], "Länder against Austria")
    check_sum((e["total"] for e in districts.values()), national["total"],
              "districts against Austria")
    for digit, land in LAENDER.items():
        nuts = next((e for e in laender.values() if fold(e["name"]) == fold(land)), None)
        if nuts is None:
            raise SystemExit(f"austria_nationality: no NUTS 2 row named {land}")
        check_sum((e["total"] for c, e in districts.items() if c[0] == digit), nuts["total"],
                  f"districts against {land}")

    vienna = [e for c, e in districts.items() if c.startswith("9")]
    if len(vienna) != 23:
        raise SystemExit(f"austria_nationality: Vienna has {len(vienna)} Gemeindebezirke, not 23")
    drawn = {c: e for c, e in districts.items() if not c.startswith("9")}
    drawn["900"] = summed(vienna, VIENNA)

    sources = [{"field": "ethnicity", "name": SOURCE, "url": PAGE, "license": LICENCE, "year": YEAR}]
    fields = {"ethnicity_year": YEAR, "ethnicity_basis": "nationality", "ethnicity_note": NOTE}
    records: list[dict[str, Any]] = []
    firsts = units("AUT", "admin1")
    for code, entry in sorted(laender.items()):
        hits = [u for u in firsts if fold(u["name"]) == fold(entry["name"])]
        if len(hits) != 1:
            raise SystemExit(f"austria_nationality: Land {entry['name']!r} meets {len(hits)} polygons")
        records.append(record(
            f"AUT-{code}-nat", hits[0]["name"], level="admin1", parent="AUT", country="AUT",
            codes={"nuts": code}, match_by="shape_id", shape_id=hits[0]["id"], sources=sources,
            ethnicity=ethnicity(entry, entry["name"]), **fields))

    shapes = units("AUT", "admin2")
    parents = {u["id"]: u["name"] for u in firsts}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for shape in shapes:
        by_name.setdefault(fold(shape["name"]), []).append(shape)
    used, unbound = set(), []
    for code, entry in sorted(drawn.items()):
        name = VIENNA if code == "900" else REGISTER_ALIASES.get(code, entry["name"])
        land = LAENDER[code[0]]
        hits = [h for h in by_name.get(fold(name), []) if parents.get(h["parent"]) == land] \
            or by_name.get(fold(name), [])
        if len(hits) != 1 or hits[0]["id"] in used:
            unbound.append(f"{entry['name']} ({code})")
            continue
        used.add(hits[0]["id"])
        records.append(record(
            f"AUT-PB-{code}-nat", hits[0]["name"], level="admin2", parent=hits[0]["parent"],
            parent_name=land, country="AUT", codes={"statistik_austria_pol_bezirk": code},
            match_by="shape_id", shape_id=hits[0]["id"], sources=sources,
            ethnicity=ethnicity(entry, entry["name"]), **fields))
    left = [s["name"] for s in shapes if s["id"] not in used]
    log(f"  districts: {len(used)} bound; unbound {unbound}; polygons left {left}")
    if unbound or left or len(used) != EXPECTED_DISTRICTS:
        raise SystemExit(f"austria_nationality: {len(used)} districts bound, {EXPECTED_DISTRICTS} "
                         f"expected")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    records = build()
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
