"""What the Central American census readers share: tables by area, checked.

Honduras, Nicaragua, Costa Rica and Panama publish their censuses on REDATAM
WebServers, and each reader here asks its server for one question's frequency
table broken by an area (``redatam.Server.frequency``). What comes back is a
list of tables, one an area, and the base's own table with no area after
them. This turns that list into ``{area code: table}`` and refuses anything
that does not add up: a table whose rows do not make its total, an area
printed twice, or areas that do not make the base's total.

The servers differ in how they print an area. Costa Rica's writes the code
again before the name ("AREA # 101", "101 San José"); Panama's writes the
name alone. ``area_name`` takes the code off where it is there.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .redatam import median_age  # noqa: F401 -- readers take it from here with the rest

AGE = re.compile(r"^\s*(\d+)")


def area_name(name: str, code: str | None) -> str:
    """The area's name without its own code, where a server prints it before it.

    Costa Rica's server writes "101 San José" for area 101 and Nicaragua's
    "05-Nueva Segovia" for area 05. Only the area's own code is taken off:
    a name may begin with a number of its own (Panama's corregimiento of
    24 de Diciembre).
    """
    name = (name or "").strip()
    if code and re.match(rf"^{re.escape(code)}(?:\s*-\s*|\s+)(?=\S)", name):
        return re.sub(rf"^{re.escape(code)}(?:\s*-\s*|\s+)", "", name).strip()
    return name


def by_area(found: list[dict], question: str, who: str,
            base_total: int | None = None) -> dict[str, dict[str, Any]]:
    """One question's tables as {area code: table}, after the checks.

    Every table's rows must make its Total; no area may appear twice; the
    base's own table (no area), where printed, must be the areas' sum, as
    must ``base_total`` where given (the question's answers plus those it was
    not put to).
    """
    out: dict[str, dict[str, Any]] = {}
    whole = []
    for table in found:
        if table["total"] is not None and sum(n for _, n in table["rows"]) != table["total"]:
            raise SystemExit(f"{who}: {question}: {table['area'] or 'the base'}'s rows make "
                             f"{sum(n for _, n in table['rows']):,}, not its total "
                             f"{table['total']:,}")
        if not table["area"]:
            whole.append(table)
            continue
        if table["area"] in out:
            raise SystemExit(f"{who}: {question}: area {table['area']} printed twice")
        out[table["area"]] = {**table, "name": area_name(table["name"], table["area"])}
    if not out:
        raise SystemExit(f"{who}: {question}: no area tables came back")
    answered = sum(t["total"] or 0 for t in out.values())
    everyone = answered + sum(t["na"] or 0 for t in out.values())
    if len(whole) > 1 or (whole and whole[0]["total"] != answered):
        raise SystemExit(f"{who}: {question}: the base's own table says "
                         f"{[t['total'] for t in whole]}, the areas make {answered:,}")
    if base_total is not None and everyone != base_total:
        raise SystemExit(f"{who}: {question}: the areas' answers and not-applicables make "
                         f"{everyone:,}, not {base_total:,}")
    return out


def fill_missing(tables: dict[str, dict[str, dict[str, Any]]], who: str, everyone: int,
                 reference: str = "sex") -> dict[str, int]:
    """Give every area a table for every question, and check each makes ``everyone``.

    A processor prints no table for an area where nobody was put the
    question -- Costa Rica's P08, which people, in a district where nobody
    said they are indigenous. That area's table is empty, and everyone there
    is "not applicable". ``reference`` is a question put to everyone (sex),
    whose areas are all the areas there are. Returns how many areas each
    question was missing.
    """
    areas = tables[reference]
    filled = {}
    for question, found in tables.items():
        stray = set(found) - set(areas)
        if stray:
            raise SystemExit(f"{who}: {question}: areas {reference} does not have: "
                             f"{sorted(stray)[:10]}")
        absent = [code for code in areas if code not in found]
        for code in absent:
            found[code] = {"area": code, "name": areas[code]["name"], "title": None,
                           "rows": [], "total": 0, "na": areas[code]["total"]}
        filled[question] = len(absent)
        made = sum((t["total"] or 0) + (t["na"] or 0) for t in found.values())
        if made != everyone:
            short = [f"{code} {areas[code]['name']}: {t['total']}+{t['na']} of "
                     f"{areas[code]['total']}" for code, t in sorted(found.items())
                     if (t["total"] or 0) + (t["na"] or 0) != areas[code]["total"]]
            raise SystemExit(f"{who}: {question}: the areas' answers and not-applicables make "
                             f"{made:,}, not {everyone:,}; {len(short)} areas short of "
                             f"{reference}: {short[:12]}")
    return filled


def translate(rows: list[tuple[str, int]], names: dict[str, str], question: str, who: str,
              known: tuple[str, ...] = ()) -> tuple[Counter, Counter]:
    """(counts under the map's labels, counts of the known non-answers).

    A label that is neither translated nor a known non-answer stops the run:
    a category silently dropped is a share silently inflated.
    """
    unknown = sorted({label for label, _ in rows} - set(names) - set(known))
    if unknown:
        raise SystemExit(f"{who}: {question}: labels this file does not know: {unknown}")
    counts: Counter = Counter()
    left: Counter = Counter()
    for label, n in rows:
        if label in names:
            counts[names[label]] += n
        else:
            left[label] += n
    return counts, left


def single_years(rows: list[tuple[str, int]], who: str,
                 unstated: tuple[str, ...] = ()) -> tuple[Counter, int]:
    """(people by single year of age, people whose age was not stated)."""
    ages: Counter = Counter()
    missing = 0
    for label, n in rows:
        if label in unstated:
            missing += n
            continue
        m = AGE.match(label)
        if not m:
            raise SystemExit(f"{who}: an age label with no number: {label!r}")
        ages[int(m.group(1))] += n
    return ages, missing


def sex_ratio(men: int, women: int) -> int | None:
    """Men per 1,000 women."""
    return round(1000 * men / women) if women else None


def summed(tables: list[dict[str, Any]]) -> dict[str, Any]:
    """Several areas' tables of one question added into one."""
    rows: Counter = Counter()
    order: list[str] = []
    for table in tables:
        for label, n in table["rows"]:
            if label not in rows:
                order.append(label)
            rows[label] += n
    return {"rows": [(label, rows[label]) for label in order],
            "total": sum(t["total"] or 0 for t in tables),
            "na": sum(t["na"] or 0 for t in tables)}


def less(whole: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    """An area's table with one of its parts taken out; refuses a negative count."""
    have = dict(part["rows"])
    rows = []
    for label, n in whole["rows"]:
        left = n - have.pop(label, 0)
        if left < 0:
            raise SystemExit(f"taking a part out leaves {left} under {label!r}")
        rows.append((label, left))
    if any(have.values()):
        raise SystemExit(f"the part has categories its whole does not: {sorted(have)}")
    return {"rows": rows, "total": (whole["total"] or 0) - (part["total"] or 0),
            "na": (whole["na"] or 0) - (part["na"] or 0)}
