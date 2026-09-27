#!/usr/bin/env python3
"""Switzerland: religion and main language for the districts the map draws, Census 2000.

The Federal Population Census of 5 December 2000 was the last to ask every
resident their religion and their main language; since 2010 both come from
the structural survey, a sample that BFS publishes by canton (and, pooled,
by today's districts) but not by the districts of 2009 that this map draws.
BFS still serves the 2000 census's full tables by commune:

* su-d-vz-REL_HG_2000_1 -- resident population by canton, district and
  commune and by religion (DAM asset 193515);
* su-d-vz-SPRA_HG_2000_1 -- the same by main language (asset 147501).

Each is an .xls whose first column holds the canton, district and commune
labels, indented, a commune written as its BFS number and name; the first
group of columns is the whole population, and later groups repeat the
categories for subpopulations.

**Vintage.** The communes of 2000 are carried to those of 2009 through BFS's
register of commune changes (AGVCH correspondences, 5 December 2000 to 1
January 2009), and summed into the units ``switzerland_ages.drawn_units``
binds to the map: the districts of 2009, Basel-Stadt's three communes, the
two halves of Raron, the Schaffhausen exclave, Appenzell Ausserrhoden whole.
A commune of 2000 that went to communes of 2009 in two units would make both
unwritable; none is expected.

**Checks.** Every commune's categories make its total, the subtotals
(national languages, non-national languages) make their parts, the communes
make the national count (7,288,010), and the drawn units make it too.

Usage:
    python -m scripts.fetch_census.switzerland_census
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, dated, gap, http_get, log, record, shares, write_json
from .central_ages import check_sum, fold
from .switzerland_ages import LAKE, VINTAGE, agvch, drawn_units

CENSUS_DAY = "05-12-2000"
YEAR = 2000
DAM = "https://dam-api.bfs.admin.ch/hub/api/dam/assets/{}/master"
ASSETS = {"religion": 193515, "language": 147501}
PORTAL = "https://www.bfs.admin.ch/asset/de/{}"
SOURCE = ("Federal Statistical Office (BFS/OFS), Eidgenössische Volkszählung 2000, "
          "su-d-vz-REL_HG_2000_1 and su-d-vz-SPRA_HG_2000_1 (by commune)")
LICENCE = "BFS open data (free reuse with attribution)"
OUT = PROCESSED / "switzerland_census.json"
NATIONAL = 7_288_010
WATER = {"Bodensee"}

RELIGION = {
    "Protestantisch": "Protestant", "Römisch-katholisch": "Roman Catholic",
    "Christkatholisch": "Old Catholic", "Christlich-orthodox": "Orthodox",
    "Andere christliche Gemeinschaften": "Other Christian",
    "Jüdische Glaubensgemeinschaft": "Judaism", "Islamische Gemeinschaften": "Islam",
    "Andere Kirchen und Religionsgemeinschaften": "Other religion",
    "Keine Zugehörigkeit": "No religion", "Ohne Angabe": "Not stated",
}
LANGUAGE_SUBTOTALS = {"Landessprachen der Schweiz": ("Deutsch", "Französisch", "Italienisch",
                                                     "Rätoromanisch")}
LANGUAGE = {
    "Deutsch": "German", "Französisch": "French", "Italienisch": "Italian",
    "Rätoromanisch": "Romansh", "Serbisch und Kroatisch": "Serbian and Croatian",
    "Albanisch": "Albanian", "Portugiesisch": "Portuguese", "Spanisch": "Spanish",
    "Englisch": "English", "Türkisch": "Turkish", "Arabisch": "Arabic",
    "Niederländisch": "Dutch", "Tamilisch": "Tamil", "Russisch": "Russian",
    "Kurdisch": "Kurdish", "Polnisch": "Polish", "Ungarisch": "Hungarian",
    "Griechisch": "Greek", "Tschechisch": "Czech", "Slowakisch": "Slovak",
    "Chinesisch": "Chinese", "Japanisch": "Japanese", "Thai": "Thai",
    "Vietnamesisch": "Vietnamese", "Persisch": "Persian", "Mazedonisch": "Macedonian",
    "Skandinavische Sprachen": "Scandinavian languages",
    "Übrige slawische Sprachen": "Other Slavic languages",
    "Übrige Sprachen": "Other languages", "Andere Sprachen": "Other languages",
}
NOTES = {
    "religion": ("Religion, Federal Population Census 2000 (5 December 2000): the whole resident "
                 "population, one answer each; 'Old Catholic' is the Christkatholische Kirche; "
                 "'Not stated' gave no answer. Summed from the census's communes of 2000 into the "
                 "unit as the map draws it (2009), through BFS's register of commune changes. "
                 "Since 2010 religion is asked only in the structural survey, a sample that BFS "
                 "does not publish for these units."),
    "language": ("Main language (Hauptsprache: the language one thinks in and knows best), Federal "
                 "Population Census 2000 (5 December 2000): the whole resident population, one "
                 "language each. Summed from the census's communes of 2000 into the unit as the "
                 "map draws it (2009), through BFS's register of commune changes. Since 2010 "
                 "language is asked only in the structural survey, a sample."),
}


def clean(cell: Any) -> str:
    return " ".join(str(cell or "").split())


def number(cell: Any) -> float:
    if isinstance(cell, (int, float)):
        return float(cell)
    text = clean(cell)
    if text in ("", "-", "–"):
        return 0.0
    return float(text.replace("'", ""))


def read(field: str) -> tuple[dict[str, dict[str, float]], dict[str, float], dict[str, str]]:
    """{commune code: {label: count}} and the national row, from one census workbook."""
    import xlrd
    blob = http_get(DAM.format(ASSETS[field]), binary=True, timeout=300)
    sheet = xlrd.open_workbook(file_contents=blob).sheet_by_index(0)
    rows = [sheet.row_values(i) for i in range(sheet.nrows)]
    first_leaf = "Protestantisch" if field == "religion" else "Deutsch"
    head_at = next(i for i, r in enumerate(rows) if first_leaf in [clean(c) for c in r])
    header = [clean(c) for c in rows[head_at]]
    start = header.index("Total")
    stop = next((j for j in range(start + 1, len(header)) if header[j] == "Total"), len(header))
    columns = {j: header[j] for j in range(start + 1, stop) if header[j]}
    log(f"  {field}: {sheet.nrows} rows; the whole population's columns: {list(columns.values())}")
    known = RELIGION if field == "religion" else {**LANGUAGE, **{k: k for k in LANGUAGE_SUBTOTALS},
                                                  "Nicht-Landessprachen": "Nicht-Landessprachen"}
    unknown = [c for c in columns.values() if c not in known]
    if unknown:
        raise SystemExit(f"switzerland_census: {field} columns this reader does not know: {unknown}")
    communes: dict[str, dict[str, float]] = {}
    names: dict[str, str] = {}
    national: dict[str, float] = {}
    for r in rows[head_at + 1:]:
        label = str(r[0] or "")
        m = re.match(r"^\s*(\d{1,4})\s+(.+?)\s*$", label)
        values = {columns[j]: number(r[j]) for j in columns}
        values["Total"] = number(r[start])
        if clean(label) == "Schweiz":
            national = values
        elif m:
            code = str(int(m.group(1)))
            if code in communes:
                raise SystemExit(f"switzerland_census: commune {code} listed twice")
            communes[code] = values
            names[code] = m.group(2)
    for code, v in communes.items():
        leaves = {k: n for k, n in v.items() if k in (RELIGION if field == "religion" else LANGUAGE)}
        if abs(sum(leaves.values()) - v["Total"]) > 0.5:
            raise SystemExit(f"switzerland_census: {field}: commune {code} {names[code]}: the "
                             f"categories make {sum(leaves.values()):,.0f} of {v['Total']:,.0f}")
        for sub, parts in LANGUAGE_SUBTOTALS.items() if field == "language" else ():
            if abs(v[sub] - sum(v[p] for p in parts)) > 0.5:
                raise SystemExit(f"switzerland_census: commune {code}: {sub} is not its parts")
    return communes, national, names


def build() -> list[dict[str, Any]]:
    log(f"switzerland_census: Census 2000 by commune, carried to the units drawn in {VINTAGE}")
    religion, rel_national, names = read("religion")
    language, lang_national, _ = read("language")
    if set(religion) != set(language):
        raise SystemExit("switzerland_census: the two workbooks list different communes")
    for field, communes, national in (("religion", religion, rel_national),
                                      ("language", language, lang_national)):
        check_sum((v["Total"] for v in communes.values()), NATIONAL, f"{field}: communes against 2000")
        check_sum([national["Total"]], NATIONAL, f"{field}: the workbook's national row")

    rows = agvch(f"correspondances?startPeriod={CENSUS_DAY}&endPeriod={VINTAGE}&includeUnmodified=true")
    terminal_of: dict[str, set[str]] = {}
    register_names: dict[str, str] = {}
    for r in rows:
        initial = str(int(r["InitialCode"]))
        terminal_of.setdefault(initial, set()).add(str(int(r["TerminalCode"])))
        register_names[initial] = r["InitialName"]
    only_census = sorted(set(religion) - set(terminal_of))
    only_register = sorted(c for c in set(terminal_of) - set(religion)
                           if not LAKE.search(register_names[c]))
    log(f"  {len(religion)} communes in the census, {len(terminal_of)} in the register on "
        f"{CENSUS_DAY}; census only {[names[c] for c in only_census]}; register only (not lakes) "
        f"{[register_names[c] for c in only_register]}")
    if only_census or only_register:
        raise SystemExit("switzerland_census: the census's communes are not the register's")

    snapshot = agvch(f"snapshot?date={VINTAGE}")
    bound, unbound, left = drawn_units(snapshot)
    if unbound or set(left) - WATER:
        raise SystemExit(f"switzerland_census: units and polygons do not pair up: {unbound} / {left}")
    unit_of: dict[str, int] = {}
    for i, (_, _, members, _) in enumerate(bound):
        for c in members:
            unit_of[str(int(c))] = i
    sums: dict[int, dict[str, dict[str, float]]] = {}
    torn: set[int] = set()
    for code in religion:
        targets = {unit_of[t] for t in terminal_of[code] if t in unit_of}
        if len(targets) != 1:
            log(f"  {names[code]} ({code}) went to communes of 2009 in {len(targets)} units")
            torn |= targets
            continue
        into = sums.setdefault(targets.pop(), {"religion": {}, "language": {}, "total": {"": 0.0}})
        into["total"][""] += religion[code]["Total"]
        for field, table in (("religion", RELIGION), ("language", LANGUAGE)):
            source = religion[code] if field == "religion" else language[code]
            for german, english in table.items():
                if german in source:
                    into[field][english] = into[field].get(english, 0.0) + source[german]
    check_sum((sums[i]["total"][""] for i in sums), NATIONAL, "drawn units against 2000")

    source = [{"field": "religion/language", "name": SOURCE, "url": PORTAL.format(ASSETS["religion"]),
               "license": LICENCE, "year": YEAR}]
    records = []
    for i, (name, canton, members, shape) in enumerate(bound):
        if i in torn or i not in sums:
            why = ("Not written: a commune of the 2000 census went to communes of 2009 on both "
                   "sides of this unit's boundary, so no census figure covers exactly this polygon.")
            records.append(record(
                f"CHE-VZ2000-{fold(name)}", shape["name"], level="admin2", parent=shape["parent"],
                country="CHE", match_by="shape_id", shape_id=shape["id"],
                religion=gap(NOT_AVAILABLE, why), language=gap(NOT_AVAILABLE, why)))
            continue
        c = sums[i]
        fields: dict[str, Any] = {}
        for field in ("religion", "language"):
            rows_ = shares({k: v for k, v in c[field].items() if v}, total=c["total"][""])
            fields[field] = rows_
            fields[f"{field}_year"] = dated(rows_, YEAR)
            fields[f"{field}_note"] = NOTES[field]
        records.append(record(
            f"CHE-VZ2000-{fold(name)}", shape["name"], level="admin2", parent=shape["parent"],
            country="CHE", codes={"bfs_2009": name}, match_by="shape_id", shape_id=shape["id"],
            sources=source, **fields))
    log(f"  {len(records) - len(torn)} units written, {len(torn)} left out")
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
