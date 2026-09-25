#!/usr/bin/env python3
"""Mexico: median age for every municipio, as INEGI publishes it (2020 census).

ITER, which ``mexico.py`` reads, carries each municipio's men and women but
only broad age bands (0-2, 3-5, ... 18-24, 60+), and the median of a Mexican
municipio falls in the 25-59 gap between them -- it cannot be computed from
ITER. INEGI publishes it instead: each state's basic-questionnaire workbook,
``cpv2020_b_<state>_01_poblacion.xlsx``, has a sheet "Población 4" --
"Población total, edad mediana, relación hombres-mujeres ... por municipio" --
giving every municipio's median age in whole years, as INEGI quotes it.

The 32 workbooks are read against themselves and against the census before
anything is written:

* each is the state its name says -- every row's "Entidad federativa" code is
  the one expected for that file;
* each state's municipios add up, men and women, to the state's own row;
* the 32 states add up to INEGI's national men and women (``mexico.NATIONAL``);
* every state's median lies within the range of its municipios', as a median
  of the whole must.

Records carry the same ids, names and parents as ``mexico.py``'s, so they join
the same polygons.

Usage:
    python -m scripts.fetch_census.mexico_age        # runner
"""
from __future__ import annotations

import io
import re
from typing import Any

from ._shared import PROCESSED, RAW, http_get, log, measure, record, write_json
from .mexico import LICENSE, NATIONAL, STATE_ALIASES

YEAR = 2020
BASE = "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/tabulados/"
SOURCE = ("INEGI, Censo de Población y Vivienda 2020, tabulados del cuestionario "
          "básico (Población 4: edad mediana por municipio)")
SHEET = "04"

# INEGI's file abbreviation for each state, by its two-digit code.
STATES = {
    "01": "ags", "02": "bc", "03": "bcs", "04": "camp", "05": "coah", "06": "col",
    "07": "chis", "08": "chih", "09": "cdmx", "10": "dgo", "11": "gto", "12": "gro",
    "13": "hgo", "14": "jal", "15": "mex", "16": "mich", "17": "mor", "18": "nay",
    "19": "nl", "20": "oax", "21": "pue", "22": "qro", "23": "qroo", "24": "slp",
    "25": "sin", "26": "son", "27": "tab", "28": "tamps", "29": "tlax", "30": "ver",
    "31": "yuc", "32": "zac",
}
CODED = re.compile(r"^(\d{2,3})\s+(.+)$")


def number(cell: Any) -> float | None:
    if isinstance(cell, (int, float)):
        return float(cell)
    try:
        return float(str(cell).replace(" ", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def read_state(code: str, abbr: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(the state's own row, its municipios' rows) from sheet 04."""
    import openpyxl
    url = f"{BASE}cpv2020_b_{abbr}_01_poblacion.xlsx"
    blob = http_get(url, binary=True, cache_dir=RAW / "mexico_age", timeout=180)
    if not blob.startswith(b"PK"):
        raise SystemExit(f"mexico_age: {url} is not a workbook: {blob[:120]!r}")
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    state, municipios = None, []
    for row in wb[SHEET].iter_rows(values_only=True):
        if not row or not row[0]:
            continue
        ent = CODED.match(str(row[0]).strip())
        if not ent:
            continue
        if ent.group(1) != code:
            raise SystemExit(f"mexico_age: {url} has a row for state {row[0]!r}, not {code}")
        unit = str(row[1] or "").strip()
        entry = {"state": ent.group(2).strip(), "total": number(row[2]),
                 "men": number(row[3]), "women": number(row[4]), "median": number(row[5]),
                 "url": url}
        if unit == "Total":
            state = entry
            continue
        mun = CODED.match(unit)
        if not mun:
            raise SystemExit(f"mexico_age: {url}: unreadable municipio cell {unit!r}")
        municipios.append({**entry, "code": f"{code}{mun.group(1).zfill(3)}",
                           "name": mun.group(2).strip()})
    if state is None or not municipios:
        raise SystemExit(f"mexico_age: {url}: {len(municipios)} municipios and "
                         f"{'a' if state else 'no'} state row")
    return state, municipios


def main() -> int:
    records: list[dict[str, Any]] = []
    men = women = 0.0
    for code, abbr in STATES.items():
        state, municipios = read_state(code, abbr)
        for part in ("men", "women"):
            summed = sum(m[part] or 0 for m in municipios)
            if abs(summed - (state[part] or 0)) > 0.5:
                raise SystemExit(f"mexico_age: {state['state']}: municipios' {part} sum to "
                                 f"{summed:,.0f}, the state row says {state[part]:,.0f}")
        medians = [m["median"] for m in municipios if m["median"] is not None]
        if state["median"] is None or not min(medians) <= state["median"] <= max(medians):
            raise SystemExit(f"mexico_age: {state['state']}: state median {state['median']} "
                             f"outside its municipios' {min(medians)}-{max(medians)}")
        men += state["men"] or 0
        women += state["women"] or 0
        log(f"  {code} {state['state']}: {len(municipios)} municipios, median {state['median']:g} "
            f"({min(medians):g}-{max(medians):g})")
        for m in municipios:
            if m["median"] is None:
                continue
            records.append(record(
                f"MEX-{m['code']}", m["name"], level="admin2", parent=f"MEX-{code}",
                country="MEX", parent_name=m["state"],
                parent_aliases=STATE_ALIASES.get(m["state"]),
                codes={"inegi": m["code"]},
                median_age=measure(m["median"], unit="years", year=YEAR, source=SOURCE),
                sources=[{"field": "median age", "name": SOURCE, "url": m["url"],
                          "license": LICENSE}],
            ))
    if round(men) != NATIONAL["POBMAS"] or round(women) != NATIONAL["POBFEM"]:
        raise SystemExit(f"mexico_age: the states hold {men:,.0f} men and {women:,.0f} women, "
                         f"not the census's {NATIONAL['POBMAS']:,} and {NATIONAL['POBFEM']:,}")
    log(f"  {len(records)} municipios with a median age; {men:,.0f} men, {women:,.0f} women")
    write_json(PROCESSED / "mexico_municipality_age.json", records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
