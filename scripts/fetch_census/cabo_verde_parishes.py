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

A parish's count is its zones' counts added up. The zone tables count the
people living in private households; those in collective dwellings are
counted only by municipality, and each parish's note says how many that
leaves out in its municipality. A parish that is its municipality's only one
takes the municipality's own count instead (INE's table by municipality),
collective dwellings included. Written for each parish: population and sex
ratio (males per 100 females, among the people in private households),
2010. The workbooks count ages only in three broad groups, so there is no
median age.

**Checks before anything is written.** Every zone's men and women make its
total (the localities listed under a zone do not always make it, and are
only reported, except where a zone was printed in the locality column: when
the localities before it make the zone above and those after it make it, it
is read as the zone it is); every parish is a sheet whose code names its
municipality; INE's 2010 table by municipality (``TOTALS``) gives the
country its 491,683; and each municipality's parishes make the people that
table counts in its private households, to within half a percent
(``SLACK``), any difference stated in the note. Twenty of the 22 close
exactly; Ribeira Grande's parishes make 45 more and Porto Novo's 45 fewer,
the two together exactly, and all 32 make the country's 488,040.
Parishes are matched to the boundary file's within their municipality by
name (``N.S.`` read as Nossa Senhora, "de/da/do" set aside, a sheet name cut
at 31 characters by its beginning); where a municipality has one parish, the
two are the same. Every polygon must get exactly one parish.

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
TOTALS_SOURCE = ("Instituto Nacional de Estatística (INE) Cabo Verde, Recenseamento Geral da "
                 "População e Habitação 2010: resident population by municipality")
LICENCE = "INE Cabo Verde publication (reuse with attribution)"
YEAR = 2010
NATIONAL = 491_683
# How far a municipality's parishes may miss the people its table counts in
# private households (Ribeira Grande's make 18,931 against 18,886).
SLACK = 0.005
SHEET_NAME_LIMIT = 31                # a workbook cuts its sheet names at 31 characters
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
# Parishes whose sheet name is not their name: Santiago's workbook splits
# "Santíssimo Nome de Jesus" across two sheets, "791 - Santissimo Nome" and
# "792 - Jesus São João Baptista"; three sheet names drop a particle
# ("Santo António Pombas", "São Francisco Assis", "São Salvador Mundo"), and
# Mosteiros' parish is printed "Nossa Senhora de Ajuda".
SHEET_NAMES = {791: "Santíssimo Nome de Jesus", 792: "São João Baptista",
               121: "Santo António das Pombas", 321: "São Francisco de Assis",
               771: "São Salvador do Mundo", 811: "Nossa Senhora da Ajuda"}


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


def embedded(places: list[dict[str, Any]], total: Any) -> int | None:
    """Where in a zone's localities a zone of its own was printed: the index
    of a named locality such that those before it make the zone's ``total``
    exactly and those after it make the locality's own total exactly."""
    for cut in range(1, len(places) - 1):
        before = sum(q["total"] for q in places[:cut])
        after = sum(q["total"] for q in places[cut + 1:])
        if places[cut]["name"] and before == total and after == places[cut]["total"]:
            return cut
    return None


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
    places: dict[tuple[str, int], list[dict[str, Any]]] = {}
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
            places.setdefault(zone, []).append(
                {"name": " ".join(str(cells[lugar]).split()), "total": value})
        elif places.get(zone):
            places[zone][-1][sex] = value
    if not zones:
        raise SystemExit(f"cabo_verde_parishes: {where}: no zones")
    for name in list(zones):
        mine = places.get(name, [])
        made = sum(q["total"] for q in mine)
        if not mine or made == zones[name].get("total"):
            continue
        cut = embedded(mine, zones[name].get("total"))
        if cut is None:
            # The localities listed under a zone need not make it; the zones'
            # own totals are what is added, and the parishes they make are
            # checked against INE's table by municipality.
            log(f"    {where}: zone {name[0]}'s localities make {made:,.0f}, "
                f"not {zones[name].get('total'):,.0f}")
            continue
        # A zone printed in the locality column (Santo André's "Jorge Luis",
        # 347 people, among the localities of "Chã de Norte", 241): the
        # localities before it make the zone above, and those after it make
        # it, so it is a zone of its own.
        inner = mine[cut]
        places[name] = mine[:cut]
        new = (inner["name"], sum(1 for n, _ in zones if n == inner["name"]))
        zones[new] = {k: v for k, v in inner.items() if k != "name"}
        places[new] = mine[cut + 1:]
        log(f"    {where}: {inner['name']} ({inner['total']:,.0f}), printed among {name[0]}'s "
            "localities, is a zone of its own: the localities before it make "
            f"{name[0]} and those after it make it")
    for name, row in zones.items():
        if row.get("masculino", 0) + row.get("feminino", 0) != row.get("total"):
            raise SystemExit(f"cabo_verde_parishes: {where}: zone {name[0]}'s men and women do "
                             f"not make its total {row}")
    out = {"total": sum(r["total"] for r in zones.values()),
           "men": sum(r["masculino"] for r in zones.values()),
           "women": sum(r["feminino"] for r in zones.values()), "zones": float(len(zones))}
    if own and own.get("total") != out["total"]:
        raise SystemExit(f"cabo_verde_parishes: {where}: its own total {own} is not its zones' "
                         f"{out['total']:,.0f}")
    return out


def totals(rows: list[list[Any]]) -> dict[str, dict[str, float]]:
    """{INE's municipality name, folded: {"total": its resident population,
    "households": its residents of private households}}, the country among
    them. The table's first column is blank; a row's name is its first
    filled cell."""
    head = next((i for i, r in enumerate(rows[:6])
                 if any(fold(c).startswith("total - populacao residente") for c in r)), None)
    if head is None:
        raise SystemExit("cabo_verde_parishes: the table by municipality has no total column")
    col = next(j for j, c in enumerate(rows[head]) if fold(c).startswith("total - populacao residente"))
    home = next((j for j, c in enumerate(rows[head])
                 if fold(c).startswith("residente nos agregados")), None)
    if home is None:
        raise SystemExit("cabo_verde_parishes: the table by municipality has no column for "
                         "residents of private households")
    out = {}
    for row in rows[head + 1:]:
        cells = list(row) + [""] * (max(col, home) + 1)
        total, households = number(cells[col]), number(cells[home])
        name = next((str(c) for c in cells[:min(col, home)] if str(c).strip()), "")
        if name and number(name) is None and total is not None and households is not None:
            out[fold(name)] = {"total": total, "households": households}
    return out


def read() -> tuple[dict[int, list[dict[str, Any]]], dict[str, dict[str, float]], dict[str, str]]:
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
                # São Vicente's workbook keeps a working sheet beside its
                # parish; a parish missing from its sheets would leave its
                # municipality short, which check() stops on.
                if any(str(c).strip() for r in rows for c in r):
                    log(f"    {island}: sheet {sheet!r} is no parish sheet; not read")
                continue
            code = int(hit.group(1))
            if code // 10 not in MUNICIPALITIES:
                raise SystemExit(f"cabo_verde_parishes: {island}: sheet {sheet!r}: no municipality "
                                 f"{code // 10}")
            counts = parish(rows, f"{island} {sheet}")
            parishes.setdefault(code // 10, []).append({
                "code": code,
                "name": SHEET_NAMES.get(code) or re.sub(r"(?i)^freguesia\s+", "", hit.group(2)),
                # A sheet's name is cut at 31 characters ("112 - Nossa
                # Senhora do Livramen"); bind() then matches its beginning.
                "truncated": len(sheet) >= SHEET_NAME_LIMIT,
                "island": island, "url": url, "island_name": name, **counts})
        time.sleep(2)
    check(parishes, table)
    return parishes, table, urls


def check(parishes: dict[int, list[dict[str, Any]]], table: dict[str, dict[str, float]]) -> None:
    """The table is the census's (the country's 491,683), and each
    municipality's parishes make the people it counts in private households
    to within ``SLACK``: the zone tables count the residents of private
    households (Tarrafal's one parish sheet closes on 18,561, the
    municipality's 18,565 less its 4 in collective dwellings), and they do
    not always close on the table by municipality exactly (Ribeira Grande's
    four parishes make 18,931 against 18,886, Porto Novo's two 17,906
    against 17,951)."""
    if set(parishes) != set(MUNICIPALITIES):
        raise SystemExit(f"cabo_verde_parishes: municipalities with no parish sheet: "
                         f"{sorted(set(MUNICIPALITIES) - set(parishes))}")
    country = table.get("cabo verde") or {}
    wrong = []
    if country.get("total") != NATIONAL:
        wrong.append(f"the table by municipality gives the country {country.get('total')}, "
                     f"not {NATIONAL:,}")
    national = 0.0
    for code, (_, ine) in MUNICIPALITIES.items():
        made = sum(p["total"] for p in parishes[code])
        national += made
        own = table.get(fold(ine))
        if not own:
            wrong.append(f"{ine} is not in the table by municipality")
            continue
        log(f"  {ine}: {len(parishes[code])} parishes make {made:,.0f}; in private households "
            f"{own['households']:,.0f}, all residents {own['total']:,.0f}")
        if abs(made - own["households"]) > SLACK * own["households"]:
            wrong.append(f"{ine}'s parishes make {made:,.0f}, not the {own['households']:,.0f} it "
                         f"counts in private households (all residents {own['total']:,.0f})")
    log(f"  the parishes make {national:,.0f}; in private households "
        f"{country.get('households')}, all residents {country.get('total')}")
    if wrong:
        raise SystemExit("cabo_verde_parishes: " + "; ".join(wrong))


def bind(parishes: dict[int, list[dict[str, Any]]], admin1: list[dict[str, Any]],
         admin2: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{polygon id: parish}: by name within the municipality (a name the
    workbook cut short, by its beginning), or the only parish of a
    municipality with one."""
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
            k = key(shape["name"])
            hits = [p for p in spare if key(p["name"]) == k] or \
                [p for p in spare if p.get("truncated") and k.startswith(key(p["name"]))]
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


def display(p: dict[str, Any], shape: dict[str, Any]) -> str:
    """INE's name for the parish ("N.S." written out); where the workbook cut
    the name short, the boundary file's, its particles in lower case."""
    if p.get("truncated"):
        return re.sub(r"\b(D[aeo]s?)\b", lambda m: m.group(1).lower(), shape["name"])
    hit = re.match(r"N\.\s*S\.\s*(.+)$", p["name"])
    if not hit:
        return p["name"]
    rest = hit.group(1)
    return "Nossa Senhora " + (rest if re.match(r"(?i)d[aeo]s?\s", rest) else "da " + rest)


def note_for(p: dict[str, Any], name: str, parishes: dict[int, list[dict[str, Any]]],
             table: dict[str, dict[str, float]]) -> str:
    municipality, ine = MUNICIPALITIES[p["code"] // 10]
    own = table[fold(ine)]
    mine = parishes[p["code"] // 10]
    made = sum(q["total"] for q in mine)
    if len(mine) == 1 and made == own["households"]:
        # The parish is the whole municipality, whose count INE's table by
        # municipality gives with the people in collective dwellings.
        return (f"The 2010 census's count for the parish of {name}, which is the whole "
                f"municipality of {municipality}.")
    note = (f"The 2010 census's count of the people living in private households in the parish "
            f"of {name}" + (f", its {p['zones']:.0f} zones added up." if p["zones"] > 1 else "."))
    collective = own["total"] - own["households"]
    if collective:
        one = collective == 1
        note += (f" The {collective:,.0f} {'person' if one else 'people'} of {municipality} "
                 f"municipality who lived in collective dwellings {'is' if one else 'are'} "
                 "counted only for the municipality as a whole.")
    gap = made - own["households"]
    if gap:
        whose = "the parish makes" if len(mine) == 1 else f"{municipality}'s {len(mine)} parishes make"
        note += (f" Added up this way, {whose} {made:,.0f}, {abs(gap):,.0f} "
                 f"{'more' if gap > 0 else 'fewer'} than the {own['households']:,.0f} people in "
                 "private households that INE's table by municipality gives.")
    return note


def records_of(parishes: dict[int, list[dict[str, Any]]], table: dict[str, dict[str, float]],
               admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A record for each parish. A parish that is its municipality's only one
    takes the municipality's count, people in collective dwellings included;
    the others take their zones' count of the people in private households.

    No record is written for the municipalities themselves: most carry a
    later count (the 2021 census, for nine of them), which a 2010 figure here
    would stand in front of."""
    bound = bind(parishes, admin1, admin2)
    totals_url = ARCHIVE.format(stamp=TOTALS_STAMP, original=TOTALS_ORIGINAL)
    out = []
    for shape in admin2:
        p = bound[shape["id"]]
        municipality, ine = MUNICIPALITIES[p["code"] // 10]
        own = table[fold(ine)]
        source = SOURCE.format(island=p["island_name"])
        sources = [{"field": "population/sex_ratio", "name": source, "url": p["url"],
                    "page": POPULATION + p["island"], "license": LICENCE, "year": YEAR}]
        population = measure(round(p["total"]), year=YEAR, source=source)
        sex_note = None
        whole = len(parishes[p["code"] // 10]) == 1 and p["total"] == own["households"]
        if whole:
            population = measure(round(own["total"]), year=YEAR, source=TOTALS_SOURCE)
            sources.insert(0, {"field": "population", "name": TOTALS_SOURCE, "url": totals_url,
                               "license": LICENCE, "year": YEAR})
            collective = own["total"] - own["households"]
            if collective:
                sex_note = (f"Men per 100 women among the {own['households']:,.0f} people living "
                            f"in private households; the {collective:,.0f} in collective dwellings "
                            "are not counted by sex in the parish tables.")
        out.append(record(
            f"CPV-2010-{p['code']}", shape["name"], level="admin2", parent="CPV", country="CPV",
            match_by="shape_id", shape_id=shape["id"],
            population=population,
            population_note=note_for(p, display(p, shape), parishes, table),
            sex_ratio=measure(round(100 * p["men"] / p["women"], 1), unit="males_per_100_females",
                              year=YEAR, source=source),
            sex_ratio_note=sex_note,
            sources=sources))
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
    records = records_of(parishes, table, admin1, admin2)
    for r in records:
        ratio = r["sex_ratio"].get("value")
        log(f"  {r['name']}: {r['population']['value']:,}"
            + (f", {ratio} men per 100 women" if ratio is not None else "")
            + f"; {r['population_note']}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
