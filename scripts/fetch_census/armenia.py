#!/usr/bin/env python3
"""Armenia's marzes and Yerevan from Armstat's own tables.

Armstat publishes the permanent population at the start of each year by marz,
sex and age -- under one, 1-4, then five-year groups to 85 and over --
recalculated on the base of the 2022 census ("Age and sex distribution of RA
permanent population by Marzes and city Yerevan", armstat.am, nid=969; one
sheet per 1 January). That is each marz's population, men per hundred women
and a median age, the median interpolated within the group holding the middle
person, as Armstat publishes nothing finer by marz.

The map's second level is the raions Armenia had before the 1995 reform into
marzes, and Yerevan. Armstat publishes no table for those raions -- its
censuses and yearly counts go by marz and by community -- so each is written
as a gap that says so, on every field. (Wikidata's figures joined to them by
name are the municipalities formed by consolidation in 2016-2021, another
unit; shared.patch lists them in NOT_THIS_SHAPE.) Yerevan is a marz and a
city at once, drawn at both levels, and its polygon at the second level
takes the city's own row.

Usage:
    python -m scripts.fetch_census.armenia
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .cod_ps_age import grouped_median
from .east_checks import check_median

SITE = PROCESSED.parent.parent / "site" / "data"
OUT = "armenia.json"
AGES = "https://armstat.am/file/doc/99568938.xls"
PAGE = "https://armstat.am/en/?nid=969"
SOURCE = ("Statistical Committee of the Republic of Armenia (Armstat), age and sex "
          "distribution of RA permanent population by marzes and city Yerevan, "
          "as of 1 January {year}")
LICENCE = "Armstat, open publication"
# Armstat's column heading -> the map's first-level unit.
MARZ = {"Yerevan": "Yerevan", "Aragatsotn": "Aragatsotn", "Ararat": "Ararat",
        "Armavir": "Armavir", "Gegharkunik": "Gegharkunik", "Lori": "Lori",
        "Kotayk": "Kotayk", "Shirak": "Shirak", "Syunik": "Syunik",
        "Vayots Dzor": "Vayots Dzor", "Tavush": "Tavush"}
BLOCKS = {"total population": "total", "male": "men", "female": "women"}
# The map's second-level polygons other than Yerevan.
RAION_NOTE = ("The map draws here one of the raions Armenia had before the 1995 reform into "
              "marzes. Armstat publishes its censuses (2011, 2022) and its yearly counts by "
              "marz and by community, and no table for these raions, so no figure describes "
              "this polygon; the marz it lies in has its own, one level up.")
CITY_NOTE = (" Yerevan is a marz and a city at once, which the map draws at both levels; "
             "this is the city's own row.")
FIELDS = ("population", "median_age", "sex_ratio", "ethnicity", "language", "religion")


def second_level(admin2: list[dict[str, Any]], city_id: str, city: dict[str, Any],
                 cites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Yerevan's polygon with the city's values; every raion a gap that says why."""
    out = []
    capitals = [u for u in admin2 if u["name"] == "Yerevan" and u["parent"] == city_id]
    if len(capitals) != 1:
        raise SystemExit(f"armenia: {len(capitals)} second-level polygons named Yerevan "
                         "in the marz")
    for u in admin2:
        if u is capitals[0]:
            values = {k: (v + CITY_NOTE if k.endswith("_note") else v)
                      for k, v in city.items()}
            out.append(record(f"ARM-ARMSTAT-{u['id']}", u["name"], level="admin2",
                              parent="ARM", country="ARM", match_by="shape_id",
                              shape_id=u["id"], sources=cites, **values))
            continue
        why = gap(NOT_AVAILABLE, RAION_NOTE)
        out.append(record(f"ARM-ARMSTAT-{u['id']}", u["name"], level="admin2", parent="ARM",
                          country="ARM", match_by="shape_id", shape_id=u["id"],
                          **{f: why for f in FIELDS}))
    return out


def clean(cell: Any) -> str:
    return " ".join(str(cell if cell is not None else "").split())


def heading(cell: Any) -> str:
    """'Geghar kunik' (a line break in the heading) -> 'Gegharkunik'."""
    text = clean(cell)
    return "Gegharkunik" if text.replace(" ", "").lower() == "gegharkunik" else text


def number(cell: Any) -> float:
    if isinstance(cell, (int, float)):
        return float(cell)
    text = clean(cell).replace(" ", "").replace(",", "")
    if text in ("", "-", "–"):
        return 0.0
    return float(text)


def band(label: Any) -> tuple[int, int | None] | None:
    text = clean(label)
    if re.fullmatch(r"\d+(\.0)?", text):
        n = int(float(text))
        return n, n
    if m := re.fullmatch(r"(\d+)\s*-\s*(\d+)", text):
        return int(m.group(1)), int(m.group(2))
    if m := re.fullmatch(r"(\d+)\s*\+", text):
        return int(m.group(1)), None
    return None


def read_sheet(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """{column heading: {"total"|"men"|"women": {"groups": [...], "all": n}}}."""
    out: dict[str, dict[str, Any]] = {}
    block = None
    columns: list[str] = []
    for row in rows:
        first = [clean(c) for c in row[:2]]
        label = next((c for c in first if c), "")
        low = label.lower()
        if low in BLOCKS and not any(clean(c) for c in row[2:]):
            block = BLOCKS[low]
            continue
        if low == "age":
            columns = [heading(c) for c in row[1:]]
            continue
        if block is None or not columns:
            continue
        if low.startswith("total"):
            for name, cell in zip(columns, row[1:]):
                if name:
                    out.setdefault(name, {}).setdefault(block, {"groups": []})["all"] = number(cell)
            continue
        got = band(row[0])
        if got is None:
            continue
        for name, cell in zip(columns, row[1:]):
            if name:
                out.setdefault(name, {}).setdefault(block, {"groups": []})["groups"].append(
                    (got[0], got[1], number(cell)))
    return out


def checked(table: dict[str, dict[str, Any]], when: str) -> None:
    """Every block's groups make its total, men and women make everyone, and the
    marzes make the republic, or the run stops."""
    for name, blocks in table.items():
        if set(blocks) != {"total", "men", "women"}:
            raise SystemExit(f"armenia: {when}: {name} has blocks {sorted(blocks)}")
        for kind, b in blocks.items():
            made = sum(n for *_, n in b["groups"])
            if abs(made - b["all"]) > 0.5:
                raise SystemExit(f"armenia: {when}: {name} {kind}: groups make {made:,.0f}, "
                                 f"the total {b['all']:,.0f}")
        if abs(blocks["men"]["all"] + blocks["women"]["all"] - blocks["total"]["all"]) > 0.5:
            raise SystemExit(f"armenia: {when}: {name}'s men and women do not make its total")
    republic = table.get("RA")
    if not republic:
        raise SystemExit(f"armenia: {when}: no column for the republic")
    made = sum(b["total"]["all"] for n, b in table.items() if n in MARZ)
    if abs(made - republic["total"]["all"]) > 0.5:
        raise SystemExit(f"armenia: {when}: the marzes make {made:,.0f}, the republic "
                         f"{republic['total']['all']:,.0f}")


def sheet_date(title: str) -> date | None:
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", title.strip())
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    import xlrd

    book = xlrd.open_workbook(file_contents=http_get(AGES, binary=True, timeout=300))
    dated = sorted((d, s) for s in book.sheets() if (d := sheet_date(s.name)))
    if not dated:
        raise SystemExit("armenia: no sheet titled by a 1 January date: "
                         + ", ".join(s.name for s in book.sheets()))
    when, sheet = dated[-1]
    table = read_sheet([sheet.row_values(i) for i in range(sheet.nrows)])
    checked(table, sheet.name)
    if missing := [m for m in MARZ if m not in table]:
        raise SystemExit(f"armenia: {sheet.name} has no column for {missing}")
    log(f"  {sheet.name}: {len(MARZ)} marzes make the republic's "
        f"{table['RA']['total']['all']:,.0f}; every block's groups make its total")
    # The republic's median from the same groups, against Eurostat's (from
    # Armstat's single years), as the marzes' are made the same way. For
    # 1 January 2024 Eurostat's median (33.7) does not agree with its own age
    # groups for that date, which are Armstat's row for row and put the
    # middle person at 39.1; that year is not this sheet's, so it is said here
    # and not checked against.
    check_median("AM", when.year, grouped_median(sorted(table["RA"]["total"]["groups"])),
                 "armenia: the republic")

    admin1 = {u["name"]: u for u in json.loads((SITE / "admin1" / "ARM.units.json").read_text())}
    source = SOURCE.format(year=when.year)
    records = []
    for column, name in MARZ.items():
        u = admin1.get(name)
        if not u:
            raise SystemExit(f"armenia: the map has no first-level unit {name!r}")
        b = table[column]
        men, women = b["men"]["all"], b["women"]["all"]
        median = grouped_median(sorted(b["total"]["groups"]))
        values = {
            "population": measure(int(b["total"]["all"]), year=when.year, source=source),
            "population_note": (f"Armstat's permanent population on 1 January {when.year}, "
                                "recalculated on the base of the 2022 census."),
            "median_age": measure(median, unit="years", year=when.year, source=source),
            "median_age_note": ("Interpolated within the age group holding the middle "
                                "person (under one, 1-4, then five-year groups to 85 and "
                                "over): Armstat publishes nothing finer by marz."),
            "sex_ratio": measure(round(100 * men / women, 1), unit="males_per_100_females",
                                 year=when.year, source=source),
            "sex_ratio_note": f"{int(men):,} men and {int(women):,} women.",
        }
        cites = [{"field": f, "name": source, "url": PAGE, "license": LICENCE,
                  "year": when.year} for f in ("population", "median_age", "sex_ratio")]
        records.append(record(f"ARM-ARMSTAT-{u['id']}", name, level="admin1", parent="ARM",
                              country="ARM", match_by="shape_id", shape_id=u["id"],
                              sources=cites, **values))
        if name == "Yerevan":
            city = (u["id"], values, cites)
        log(f"  {name}: {int(b['total']['all']):,}, median {median}, "
            f"{100 * men / women:.1f} men per 100 women")
    admin2 = json.loads((SITE / "admin2" / "ARM.units.json").read_text())
    second = second_level(admin2, *city)
    records += second
    log(f"  second level: Yerevan's polygon takes the city's row; {len(second) - 1} raions "
        "of before 1995 are written as gaps that say why")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
