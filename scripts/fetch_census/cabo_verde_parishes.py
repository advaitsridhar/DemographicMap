#!/usr/bin/env python3
"""Cabo Verde -- the 2010 census (RGPH 2010) by parish.

The map's second level is Cabo Verde's 32 parishes (freguesias), and nothing
read so far gave them a count: Wikidata has one, for São Lourenço. INE Cabo
Verde published the 2010 census's resident population by zone and locality in
one workbook per island, a sheet per parish (``811 - Nossa Senhora de Ajuda``),
each zone with its total, men and women and then each of its localities. Those
workbooks have since left INE's site, whose census service now asks for a
login; the copies read here are the Internet Archive's of INE's own files, as
INE served them in November 2013.

A parish's count is its zones' counts added up. Written for each parish:
population and sex ratio (males per 100 females), 2010. The workbooks count
ages only in three broad groups, so there is no median age.

**Checks before anything is written.** Every zone's men and women make its
total (the localities listed under a zone do not always make it, and are
only reported); every parish is a sheet whose code
names its municipality; each municipality's parishes make the municipality's
resident population in INE's 2010 table by municipality (``TOTALS``), and the
municipalities make the country's 491,683. Parishes are matched to the
boundary file's within their municipality by name (``N.S.`` read as Nossa
Senhora, "de/da/do" set aside); where a municipality has one parish, the two
are the same. Every polygon must get exactly one parish.

Usage:
    python -m scripts.fetch_census.cabo_verde_parishes
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json

ARCHIVE = "https://web.archive.org/web/{stamp}id_/{original}"
POPULATION = "http://www.ine.cv/censo/2010/POPULA%C3%87%C3%83O/"
# Island workbook -> (the island, the Internet Archive's capture of the workbook).
ISLANDS = {
    "Santo%20Ant%C3%A3o.xls": ("Santo Antão", "20131106000623"),
    "S%C3%A3o%20Vicente.xls": ("São Vicente", "20131106000537"),
    "S%C3%A3o%20Nicolau.xls": ("São Nicolau", "20131106000907"),
    "Sal.xls": ("Sal", "20131105235411"), "Boa%20Vista.xls": ("Boa Vista", "20131105235259"),
    "Maio.xls": ("Maio", "20131106000710"), "Santiago.xls": ("Santiago", "20131106001403"),
    "Fogo.xls": ("Fogo", "20131106001925"), "Brava.xls": ("Brava", "20131105235641"),
}
# INE's 2010 table of the resident population by municipality.
TOTALS_ORIGINAL = ("http://www.ine.cv/actualise/dadostat/files/a09f3db2-05b9-434a-96d4-f313812850c9"
                   "distribui%C3%A7%C3%A3o%20da%20popula%C3%A7%C3%A3o%20residente%20-%20rgph%202010.xls")
TOTALS_STAMP = "20121113153850"
SOURCE = ("Instituto Nacional de Estatística (INE) Cabo Verde, Recenseamento Geral da População e "
          "Habitação 2010: resident population by zone and locality, {island}")
LICENCE = "INE Cabo Verde publication (reuse with attribution)"
YEAR = 2010
NATIONAL = 491_683
OUT = "cabo_verde_parishes.json"
SITE = PROCESSED.parent.parent / "site" / "data"

# INE's municipality code -> (the boundary file's name, INE's in the table by
# municipality).
MUNICIPALITIES = {
    11: ("Ribeira Grande", "Ribeira Grande"), 12: ("Paul", "Paul"), 13: ("Porto Novo", "Porto Novo"),
    21: ("São Vicente", "S. Vicente"), 31: ("Ribeira Brava", "Ribeira Brava"),
    32: ("Tarrafal de São Nicolau", "Tarrafal de S. Nicolau"), 41: ("Sal", "Sal"),
    51: ("Boa Vista", "Boavista"), 61: ("Maio", "Maio"), 71: ("Tarrafal", "Tarrafal"),
    72: ("Santa Catarina", "Santa Catarina"), 73: ("Santa Cruz", "Santa Cruz"), 74: ("Praia", "Praia"),
    75: ("São Domingos", "S. Domingos"), 76: ("São Miguel", "Calheta de S. Miguel"),
    77: ("São Salvador do Mundo", "S. Salvador do Mundo"),
    78: ("São Lourenço dos Órgãos", "S. Lourenço dos Órgãos"),
    79: ("Ribeira Grande de Santiago", "Ribeira Grande de Santiago"), 81: ("Mosteiros", "Mosteiros"),
    82: ("São Filipe", "S. Filipe"), 83: ("Santa Catarina do Fogo", "Santa Catarina do Fogo"),
    91: ("Brava", "Brava"),
}
SHEET = re.compile(r"^\s*(\d{3})\s*-\s*(.+?)\s*$")


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).lower().split())


def key(name: str) -> str:
    """A parish name reduced: 'Freguesia N.S. Conceição' and 'Nossa Senhora Da
    Conceicao' -> 'nossasenhoraconceicao'."""
    s = fold(name)
    s = re.sub(r"\bfreguesia\b", " ", s)
    s = re.sub(r"\bn\.?\s*s(?:ra)?\.?\s", "nossa senhora ", s)
    s = re.sub(r"\b(?:de|da|do|das|dos)\b", " ", s)
    return "".join(c for c in s if "a" <= c <= "z")


def number(cell: Any) -> float | None:
    if isinstance(cell, bool) or cell is None:
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    text = re.sub(r"[\s  .]", "", str(cell))
    return float(text) if text.isdigit() else None


def fetch(original: str, stamp: str) -> tuple[bytes, str]:
    url = ARCHIVE.format(stamp=stamp, original=original)
    for wait in (10, 30, 90, None):
        try:
            blob = http_get(url, binary=True, cache=False, timeout=180)
            if blob[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                raise SystemExit(f"cabo_verde_parishes: {url} is not a workbook: {blob[:60]!r}")
            return blob, url
        except SystemExit:
            raise
        except Exception as exc:                    # noqa: BLE001 -- the archive refuses when asked fast
            if wait is None:
                raise
            log(f"    {url}: {exc.__class__.__name__}; again in {wait} s")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def sheets_of(blob: bytes) -> dict[str, list[list[Any]]]:
    import xlrd                                     # noqa: PLC0415
    book = xlrd.open_workbook(file_contents=blob)
    return {sh.name: [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
            for sh in book.sheets()}


def parish(rows: list[list[Any]], where: str) -> dict[str, float]:
    """{"total", "men", "women", "zones"}: a parish sheet's zones added up."""
    head = next((i for i, r in enumerate(rows[:12])
                 if {"zona", "lugar", "sexo"} <= {fold(c) for c in r}), None)
    if head is None:
        raise SystemExit(f"cabo_verde_parishes: {where}: no Zona/Lugar/Sexo header")
    cols = {fold(c): j for j, c in enumerate(rows[head]) if str(c).strip()}
    z, lugar, s = cols["zona"], cols["lugar"], cols["sexo"]
    p = next((j for k, j in cols.items() if k.startswith("populacao")), None)
    if p is None:
        raise SystemExit(f"cabo_verde_parishes: {where}: no 'População residente' column")
    # A zone is keyed by its name and the order it comes in: two zones of one
    # parish can share a name (Nossa Senhora do Rosário has two "Cidade de
    # Ribeira Grande"). Were a zone printed twice instead, the municipality's
    # parishes would overshoot INE's table by municipality, which check() tests.
    zones: dict[tuple[str, int], dict[str, float]] = {}
    places: dict[tuple[str, int], float] = {}
    own: dict[str, float] = {}
    zone: tuple[str, int] | None = None
    level = None
    for row in rows[head + 1:]:
        cells = list(row) + [""] * (max(z, lugar, s, p) + 1)
        if str(cells[z]).strip():
            name = " ".join(str(cells[z]).split())
            zone = (name, sum(1 for n, _ in zones if n == name))
            level = "own" if fold(name).startswith("total") else "zone"
        elif str(cells[lugar]).strip():
            level = "place"
        sex = fold(cells[s])
        value = number(cells[p])
        if zone is None or value is None or sex not in ("total", "masculino", "feminino"):
            continue
        if level == "zone" and sex in zones.get(zone, {}):
            # A second total under a zone with no locality named is a locality
            # whose name cell is blank: its rows count towards the zone's
            # localities, not the zone.
            level = "place"
        if level == "own":
            own[sex] = value
        elif level == "zone":
            zones.setdefault(zone, {})[sex] = value
        elif sex == "total":
            places[zone] = places.get(zone, 0.0) + value
    if not zones:
        raise SystemExit(f"cabo_verde_parishes: {where}: no zones")
    for name, row in zones.items():
        if row.get("masculino", 0) + row.get("feminino", 0) != row.get("total"):
            raise SystemExit(f"cabo_verde_parishes: {where}: zone {name[0]}'s men and women do "
                             f"not make its total {row}")
        # The localities listed under a zone do not always make it (Santo
        # André's "Chã de Norte": 935 listed under a zone of 241), so they are
        # reported, not used: the zones' own totals are what is added, and the
        # parishes they make are checked against INE's table by municipality.
        if name in places and places[name] != row["total"]:
            log(f"    {where}: zone {name[0]}'s localities make {places[name]:,.0f}, "
                f"not {row['total']:,.0f}")
    out = {"total": sum(r["total"] for r in zones.values()),
           "men": sum(r["masculino"] for r in zones.values()),
           "women": sum(r["feminino"] for r in zones.values()), "zones": float(len(zones))}
    if own and own.get("total") != out["total"]:
        raise SystemExit(f"cabo_verde_parishes: {where}: its own total {own} is not its zones' "
                         f"{out['total']:,.0f}")
    return out


def totals(rows: list[list[Any]]) -> dict[str, float]:
    """{INE's municipality name, folded: resident population} and the country."""
    head = next((i for i, r in enumerate(rows[:6])
                 if any(fold(c).startswith("total - populacao residente") for c in r)), None)
    if head is None:
        raise SystemExit("cabo_verde_parishes: the table by municipality has no total column")
    col = next(j for j, c in enumerate(rows[head]) if fold(c).startswith("total - populacao residente"))
    out = {}
    for row in rows[head + 1:]:
        cells = list(row) + [""] * (col + 1)
        value = number(cells[col])
        if str(cells[0]).strip() and value is not None:
            out[fold(cells[0])] = value
    return out


def read() -> tuple[dict[int, list[dict[str, Any]]], dict[str, float], dict[str, str]]:
    """({municipality code: [parish]}, the table by municipality, {island: url})."""
    blob, _ = fetch(TOTALS_ORIGINAL, TOTALS_STAMP)
    table = totals(next(iter(sheets_of(blob).values())))
    parishes: dict[int, list[dict[str, Any]]] = {}
    urls = {}
    for island, (name, stamp) in ISLANDS.items():
        blob, url = fetch(POPULATION + island, stamp)
        urls[island] = url
        for sheet, rows in sheets_of(blob).items():
            hit = SHEET.match(sheet)
            if not hit:
                if any(str(c).strip() for r in rows for c in r):
                    raise SystemExit(f"cabo_verde_parishes: {island}: sheet {sheet!r} is no parish")
                continue
            code = int(hit.group(1))
            if code // 10 not in MUNICIPALITIES:
                raise SystemExit(f"cabo_verde_parishes: {island}: sheet {sheet!r}: no municipality "
                                 f"{code // 10}")
            counts = parish(rows, f"{island} {sheet}")
            parishes.setdefault(code // 10, []).append({
                "code": code, "name": re.sub(r"(?i)^freguesia\s+", "", hit.group(2)),
                "island": island, "url": url, "island_name": name, **counts})
        time.sleep(2)
    check(parishes, table)
    return parishes, table, urls


def check(parishes: dict[int, list[dict[str, Any]]], table: dict[str, float]) -> None:
    if set(parishes) != set(MUNICIPALITIES):
        raise SystemExit(f"cabo_verde_parishes: municipalities with no parish sheet: "
                         f"{sorted(set(MUNICIPALITIES) - set(parishes))}")
    national = 0.0
    for code, (_, ine) in MUNICIPALITIES.items():
        made = sum(p["total"] for p in parishes[code])
        own = table.get(fold(ine))
        if own != made:
            raise SystemExit(f"cabo_verde_parishes: {ine}'s parishes make {made:,.0f}, the table by "
                             f"municipality {own}")
        national += made
    if national != NATIONAL or table.get("cabo verde") != NATIONAL:
        raise SystemExit(f"cabo_verde_parishes: the country is {national:,.0f} (table "
                         f"{table.get('cabo verde')}), not {NATIONAL:,}")


def bind(parishes: dict[int, list[dict[str, Any]]], admin1: list[dict[str, Any]],
         admin2: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{polygon id: parish}: by name within the municipality, or the only
    parish of a municipality with one."""
    code_of = {}
    for shape in admin1:
        hits = [c for c, (name, _) in MUNICIPALITIES.items() if fold(name) == fold(shape["name"])]
        if len(hits) != 1:
            raise SystemExit(f"cabo_verde_parishes: municipality polygon {shape['name']!r}: {hits}")
        code_of[shape["id"]] = hits[0]
    bound: dict[str, dict[str, Any]] = {}
    left = []
    for code in sorted(MUNICIPALITIES):
        shapes = [s for s in admin2 if code_of.get(s["parent"]) == code]
        spare = list(parishes.get(code, []))
        rest = []
        for shape in shapes:
            hits = [p for p in spare if key(p["name"]) == key(shape["name"])]
            if len(hits) == 1:
                bound[shape["id"]] = hits[0]
                spare.remove(hits[0])
            else:
                rest.append(shape)
        if len(rest) == 1 and len(spare) == 1:
            bound[rest[0]["id"]] = spare.pop()
            rest = []
        left += [f"{s['name']!r} ({MUNICIPALITIES[code][0]})" for s in rest]
        left += [f"parish {p['name']!r} ({MUNICIPALITIES[code][0]}) on no polygon" for p in spare]
    if left or len(bound) != len(admin2):
        raise SystemExit(f"cabo_verde_parishes: not bound: {left}")
    return bound


def records_of(parishes: dict[int, list[dict[str, Any]]], admin1: list[dict[str, Any]],
               admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bound = bind(parishes, admin1, admin2)
    out = []
    for shape in admin2:
        p = bound[shape["id"]]
        source = SOURCE.format(island=p["island_name"])
        note = (f"The 2010 census's count for the parish of {p['name']}: its "
                f"{p['zones']:.0f} zones added up.")
        out.append(record(
            f"CPV-2010-{p['code']}", shape["name"], level="admin2", parent="CPV", country="CPV",
            match_by="shape_id", shape_id=shape["id"],
            population=measure(round(p["total"]), year=YEAR, source=source),
            population_note=note,
            sex_ratio=measure(round(100 * p["men"] / p["women"], 1), unit="males_per_100_females",
                              year=YEAR, source=source),
            sources=[{"field": "population/sex_ratio", "name": source, "url": p["url"],
                      "page": POPULATION + p["island"], "license": LICENCE, "year": YEAR}]))
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    parishes, table, _ = read()
    n = sum(len(v) for v in parishes.values())
    log(f"  {n} parishes in {len(parishes)} municipalities, making "
        f"{sum(p['total'] for v in parishes.values() for p in v):,.0f}")
    admin1 = json.loads((SITE / "admin1" / "CPV.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "CPV.units.json").read_text())
    records = records_of(parishes, admin1, admin2)
    for r in records:
        log(f"  {r['name']}: {r['population']['value']:,}, {r['sex_ratio']['value']} men per 100 "
            f"women; {r['population_note']}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
