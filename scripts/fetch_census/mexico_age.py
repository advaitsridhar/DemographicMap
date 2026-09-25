#!/usr/bin/env python3
"""Mexico: median age for every state and municipio, as INEGI publishes it (2020 census).

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
* each state's total is ITER's for that state (``mexico_state.json``), and the
  32 states add up to INEGI's national men and women (``mexico.NATIONAL``);
* every state's median lies within the range of its municipios', as a median
  of the whole must.

The states' medians come from the national workbook,
``cpv2020_b_eum_01_poblacion.xlsx``, sheet 04, which lists all 32 -- Oaxaca's
among them. Each row is identified by its population, which must be ITER's for
exactly one state, and where a state's own workbook was read its median must
be the same.

Records carry the same ids, names and parents as ``mexico.py``'s, so they join
the same polygons.

Usage:
    python -m scripts.fetch_census.mexico_age        # runner
"""
from __future__ import annotations

import io
import re
from collections import defaultdict
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, read_json, record, write_json,
)
from .mexico import LICENSE, NATIONAL, STATE_ALIASES

YEAR = 2020
BASE = "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/tabulados/"
SOURCE = ("INEGI, Censo de Población y Vivienda 2020, tabulados del cuestionario "
          "básico (Población 4: edad mediana por municipio)")
SHEET = "04"

# INEGI's file abbreviation for each state, by its two-digit code. Its
# naming is not one scheme -- "cam", "coa", "chs" and "cdmx" answer, "camp"
# and "chis" do not -- so a state lists the spellings INEGI uses in its other
# files, tried in turn; a wrong one answers with an HTML page, and the right one must still
# be that state's workbook, row by row.
STATES = {
    "01": ("ags",), "02": ("bc",), "03": ("bcs",), "04": ("cam",),
    "05": ("coa",), "06": ("col",), "07": ("chs",), "08": ("chh", "chih", "chi"),
    "09": ("cdmx",), "10": ("dgo", "dur"), "11": ("gto", "gua"), "12": ("gro", "gue"),
    "13": ("hgo", "hid"), "14": ("jal",), "15": ("mex", "em", "edomex", "emex"),
    "16": ("mich", "mic"), "17": ("mor",), "18": ("nay",), "19": ("nl", "nle"),
    "20": ("oax",), "21": ("pue",), "22": ("qro", "que", "qto"), "23": ("qroo",),
    "24": ("slp",), "25": ("sin",), "26": ("son",), "27": ("tab",),
    "28": ("tamps", "tam", "tams"), "29": ("tlax", "tla"), "30": ("ver", "vz"),
    "31": ("yuc",), "32": ("zac",),
}
# Oaxaca's workbook answers at none of its spellings -- "oax", "oaxaca", as
# .xls, .zip or a first part -- with the HTML page INEGI serves for a
# missing file (September 2026). Its 570 municipios keep a gap that says so; any
# other state without a workbook stops the run.
UNPUBLISHED = {"20": ("INEGI's Oaxaca workbook (cpv2020_b_oax_01_poblacion.xlsx) is not "
                      "at the address the other 31 states' are published at, so its "
                      "municipios' median ages are not read")}
CODED = re.compile(r"^(\d{2,3})\s+(.+)$")


def number(cell: Any) -> float | None:
    if isinstance(cell, (int, float)):
        return float(cell)
    try:
        return float(str(cell).replace(" ", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def workbook(abbrs: tuple[str, ...]) -> tuple[str, bytes]:
    for abbr in abbrs:
        url = f"{BASE}cpv2020_b_{abbr}_01_poblacion.xlsx"
        try:
            blob = http_get(url, binary=True, cache=False, timeout=180)
        except RuntimeError as exc:
            log(f"  {url}: {exc}")
            continue
        # INEGI answers a wrong path with HTTP 200 and an HTML page.
        if blob.startswith(b"PK"):
            return url, blob
        log(f"  {url}: not a workbook")
    raise LookupError(abbrs)


def read_state(code: str, abbrs: tuple[str, ...]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(the state's own row, its municipios' rows) from sheet 04."""
    import openpyxl
    url, blob = workbook(abbrs)
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


def state_medians(iter_totals: dict[str, float | None]) -> dict[str, tuple[str, float, str]]:
    """{state code: (name, median, url)} from the national workbook's sheet 04."""
    import openpyxl
    url, blob = workbook(("eum",))
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    by_total = {total: code for code, total in iter_totals.items() if total}
    out: dict[str, tuple[str, float, str]] = {}
    for row in wb[SHEET].iter_rows(values_only=True):
        if not row or not row[0] or len(row) < 5:
            continue
        name, total, median = str(row[0]).strip(), number(row[1]), number(row[4])
        if total is None or median is None or name.startswith("Estados Unidos"):
            continue
        code = by_total.get(total)
        if code is None or code in out:
            raise SystemExit(f"mexico_age: national workbook row {name!r} ({total}) is not "
                             "exactly one state's ITER population")
        out[code] = (name, median, url)
    if len(out) != 32:
        raise SystemExit(f"mexico_age: national workbook gives {len(out)} states' medians")
    return out


def main() -> int:
    records: list[dict[str, Any]] = []
    men = women = 0.0
    missing, seen = [], set()
    stated: dict[str, float] = {}
    # ITER's state totals, which each workbook's own state row must repeat.
    iter_totals = {r["id"][4:6]: (r.get("population") or {}).get("value")
                   for r in read_json(PROCESSED / "mexico_state.json", [])}
    municipios_of, iter_by_id = defaultdict(list), {}
    for r in read_json(PROCESSED / "mexico_municipality.json", []):
        municipios_of[r["parent"][4:6]].append(r)
        iter_by_id[r["id"]] = r
    for code, abbrs in STATES.items():
        try:
            state, municipios = read_state(code, abbrs)
        except LookupError:
            if code in UNPUBLISHED:
                for m in municipios_of[code]:
                    records.append(record(
                        m["id"], m["name"], level="admin2", parent=m["parent"], country="MEX",
                        parent_name=m.get("parent_name"), parent_aliases=m.get("parent_aliases"),
                        codes=m.get("codes"),
                        median_age=gap(NOT_AVAILABLE, UNPUBLISHED[code] + ".")))
                log(f"  {code}: no workbook; {len(municipios_of[code])} municipios keep a gap")
            else:
                missing.append(f"{code} {abbrs}")
            continue
        if iter_totals.get(code) != state["total"]:
            raise SystemExit(f"mexico_age: {state['state']} counts {state['total']:,.0f} people, "
                             f"ITER {iter_totals.get(code)}")
        for part in ("men", "women"):
            summed = sum(m[part] or 0 for m in municipios)
            if abs(summed - (state[part] or 0)) > 0.5:
                raise SystemExit(f"mexico_age: {state['state']}: municipios' {part} sum to "
                                 f"{summed:,.0f}, the state row says {state[part]:,.0f}")
        medians = [m["median"] for m in municipios if m["median"] is not None]
        if state["median"] is None or not min(medians) <= state["median"] <= max(medians):
            raise SystemExit(f"mexico_age: {state['state']}: state median {state['median']} "
                             f"outside its municipios' {min(medians)}-{max(medians)}")
        seen.add(code)
        stated[code] = state["median"]
        men += state["men"] or 0
        women += state["women"] or 0
        log(f"  {code} {state['state']}: {len(municipios)} municipios, median {state['median']:g} "
            f"({min(medians):g}-{max(medians):g})")
        for m in municipios:
            if m["median"] is None:
                continue
            # ITER's spelling where it has the code, so this row finds the
            # polygon mexico.py's row for the same municipio found.
            known = iter_by_id.get(f"MEX-{m['code']}") or {}
            records.append(record(
                f"MEX-{m['code']}", known.get("name") or m["name"], level="admin2",
                parent=f"MEX-{code}", country="MEX", parent_name=known.get("parent_name") or m["state"],
                parent_aliases=STATE_ALIASES.get(m["state"]),
                codes={"inegi": m["code"]},
                median_age=measure(m["median"], unit="years", year=YEAR, source=SOURCE),
                sources=[{"field": "median age", "name": SOURCE, "url": m["url"],
                          "license": LICENSE}],
            ))
    if missing:
        raise SystemExit(f"mexico_age: no workbook for {', '.join(missing)}")
    read_all = not any(code in UNPUBLISHED and code not in seen for code in STATES)
    if read_all and (round(men) != NATIONAL["POBMAS"] or round(women) != NATIONAL["POBFEM"]):
        raise SystemExit(f"mexico_age: the states hold {men:,.0f} men and {women:,.0f} women, "
                         f"not the census's {NATIONAL['POBMAS']:,} and {NATIONAL['POBFEM']:,}")
    iter_states = {r["id"][4:6]: r for r in read_json(PROCESSED / "mexico_state.json", [])}
    for code, (name, median, url) in sorted(state_medians(iter_totals).items()):
        if code in stated and stated[code] != median:
            raise SystemExit(f"mexico_age: {name}'s median is {median} in the national "
                             f"workbook and {stated[code]} in its own")
        records.append(record(
            f"MEX-{code}000", (iter_states.get(code) or {}).get("name") or name,
            level="admin1", parent="MEX", country="MEX", codes={"inegi": f"{code}000"},
            median_age=measure(median, unit="years", year=YEAR, source=SOURCE),
            sources=[{"field": "median age", "name": SOURCE, "url": url, "license": LICENSE}],
        ))
    unknown = sum(1 for r in records if r["id"] not in iter_by_id and r["level"] == "admin2")
    log(f"  {len(records)} municipios ({unknown} not in ITER); {men:,.0f} men, {women:,.0f} women")
    write_json(PROCESSED / "mexico_municipality_age.json", records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
