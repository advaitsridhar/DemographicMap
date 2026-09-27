#!/usr/bin/env python3
"""Median age, sex ratio and population for the three Spanish and Italian
second-level shapes Eurostat's NUTS-3 figures cannot reach.

* **Las Palmas and Santa Cruz de Tenerife.** Since the 2016 NUTS revision
  Eurostat divides the Canary Islands by island (ES703-ES709), not by
  province, so neither province has a NUTS-3 figure of its own. Las Palmas was
  left empty, and Santa Cruz de Tenerife was worse than empty: the island
  region "Tenerife" (ES709) reached it by name containment, so the province
  wore one island's 966,469 people and that island's median age. INE's
  Estadística Continua de Población publishes both provinces by sex and
  single year of age (table 69792); they are read for the latest 1 January
  and bound to the two polygons by id.
* **Trentino-Alto Adige/Südtirol.** The map draws Italy's regions at its
  second level, and this region alone is two NUTS-2 regions -- the
  autonomous provinces of Bolzano (ITH1) and Trento (ITH2) -- with no NUTS
  unit of its own, so Eurostat's median never reached it. Eurostat's
  ``demo_r_d2jan`` carries ISTAT's population by sex and single year of age
  for both provinces; they are added age by age and sex by sex.

Checks, each of which stops the run:

* every place's single years make its all-ages count for each sex, and its
  two sexes make its total;
* Spain's 52 provinces make the Total Nacional of the same table and date;
* the two Italian provinces' totals are Eurostat's own for each.

Usage:
    python -m scripts.fetch_census.spain_italy_age
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from typing import Any

from ._shared import PROCESSED, http_json, log, measure, record, write_json
from .eurostat import unpack
from .redatam import median_age

OUT = "spain_italy_age.json"
SITE = PROCESSED.parent.parent / "site" / "data"
INE_TABLE = "69792"
INE_DATA = f"https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{INE_TABLE}?nult=4&tip=AM"
INE_VALUES = f"https://servicios.ine.es/wstempus/js/ES/VALORES_GRUPOSTABLA/{INE_TABLE}/145746"
INE_PAGE = f"https://www.ine.es/jaxiT3/Tabla.htm?t={INE_TABLE}"
INE_SOURCE = "INE, Estadística Continua de Población (table 69792)"
CANARY = {"35": "Palmas, Las", "38": "Santa Cruz de Tenerife"}   # INE code -> drawn name

EUROSTAT = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_r_d2jan"
            "?format=JSON&lang=EN&unit=NR&geo=ITH1&geo=ITH2&sex=M&sex=F&sex=T"
            "&lastTimePeriod=1")
EUROSTAT_SOURCE = "ISTAT, population on 1 January by sex and single year of age (Eurostat demo_r_d2jan)"
TRENTINO = "Trentino-Alto Adige"


def meta(series: dict[str, Any], variable: str) -> dict[str, Any]:
    for item in series.get("MetaData") or []:
        if item.get("T3_Variable") == variable:
            return item
    return {}


def ine_series() -> list[dict[str, Any]]:
    """Every series of table 69792, asked for one province at a time.

    The whole table in one request is refused (INE answers an error object
    rather than the series), so each of the 52 provinces and the national
    total is asked for on its own, by the value ids the table itself lists.
    """
    values = http_json(INE_VALUES, cache=False, timeout=300)
    series: list[dict[str, Any]] = []
    for value in values:
        payload = http_json(f"{INE_DATA}&tv={value['FK_Variable']}:{value['Id']}",
                            cache=False, timeout=300)
        if not isinstance(payload, list):
            raise SystemExit(f"spain_italy_age: INE answered {str(payload)[:200]} for "
                             f"{value.get('Nombre')}")
        series.extend(payload)
    log(f"  INE table {INE_TABLE}: {len(values)} places, {len(series)} series")
    return series


def spain() -> tuple[dict[str, dict[str, Any]], int]:
    """INE code -> {men, women, ages}, for the Canary provinces, at the latest 1 January."""
    payload = ine_series()
    # sex, age (None for all ages), province code, date -> value
    cells: dict[tuple[str, int | None, str, str], float] = {}
    dates: set[str] = set()
    for series in payload:
        sex = meta(series, "Sexo").get("Nombre")
        province = (meta(series, "Provincias").get("Codigo")
                    or ("00" if meta(series, "Total Nacional") or
                        "Total Nacional" in series.get("Nombre", "") else None))
        simple = meta(series, "Valores simples de edad")
        if simple:
            code = simple.get("Codigo") or ""
            match = re.match(r"^Y(\d+)$", code) or re.match(r"^(\d+)", simple.get("Nombre", ""))
            if not match:
                raise SystemExit(f"spain_italy_age: an age INE calls {simple}")
            age: int | None = int(match.group(1))
        elif meta(series, "Totales de edad"):
            age = None
        else:
            continue
        if sex not in ("Total", "Hombres", "Mujeres") or province is None:
            continue
        for point in series.get("Data") or []:
            date = point["Fecha"][:10]
            if point.get("Valor") is None:
                continue
            dates.add(date)
            cells[(sex, age, province, date)] = float(point["Valor"])
    januaries = sorted(d for d in dates if d[5:10] == "01-01")
    if not januaries:
        raise SystemExit(f"spain_italy_age: INE table {INE_TABLE} has no 1 January among {dates}")
    date = januaries[-1]
    provinces = sorted({p for (_, _, p, d) in cells if d == date and p != "00"})
    if len(provinces) != 52:
        raise SystemExit(f"spain_italy_age: {len(provinces)} provinces on {date}, not 52")
    for sex in ("Total", "Hombres", "Mujeres"):
        made = sum(cells.get((sex, None, p, date), 0.0) for p in provinces)
        whole = cells.get((sex, None, "00", date))
        if whole is None or made != whole:
            raise SystemExit(f"spain_italy_age: the provinces' {sex} make {made:,.0f}, the "
                             f"Total Nacional {whole}")
    out: dict[str, dict[str, Any]] = {}
    for code in CANARY:
        entry: dict[str, Any] = {}
        for sex, key in (("Hombres", "men"), ("Mujeres", "women")):
            ages = Counter({a: v for (s, a, p, d), v in cells.items()
                            if s == sex and p == code and d == date and a is not None})
            whole = cells.get((sex, None, code, date))
            if whole is None or sum(ages.values()) != whole:
                raise SystemExit(f"spain_italy_age: {CANARY[code]} {sex}: single years make "
                                 f"{sum(ages.values()):,.0f} against {whole}")
            entry[key] = whole
            entry[f"{key}_ages"] = ages
        total = cells.get(("Total", None, code, date))
        if total != entry["men"] + entry["women"]:
            raise SystemExit(f"spain_italy_age: {CANARY[code]}: men and women do not make "
                             f"{total}")
        entry["ages"] = entry.pop("men_ages") + entry.pop("women_ages")
        out[code] = entry
        log(f"  {CANARY[code]} on {date}: {total:,.0f} people, median "
            f"{median_age(entry['ages'])}")
    return out, int(date[:4])


def italy() -> tuple[dict[str, Any], int]:
    payload = http_json(EUROSTAT, cache=False, timeout=300)
    dims = payload["id"]
    at = {d: dims.index(d) for d in ("sex", "age", "geo", "time")}
    values = unpack(payload)
    years = {k[at["time"]] for k in values}
    if len(years) != 1:
        raise SystemExit(f"spain_italy_age: Eurostat answered for {sorted(years)}")
    year = int(next(iter(years))[:4])
    by: dict[tuple[str, str], Counter] = defaultdict(Counter)
    totals: dict[tuple[str, str], float] = {}
    for key, value in values.items():
        sex, age, geo = key[at["sex"]], key[at["age"]], key[at["geo"]]
        if age == "TOTAL":
            totals[(geo, sex)] = value
        elif age == "Y_LT1":
            by[(geo, sex)][0] += value
        elif age == "Y_OPEN":
            by[(geo, sex)][100] += value
        elif re.match(r"^Y\d+$", age):
            by[(geo, sex)][int(age[1:])] += value
        elif age == "UNK" and value:
            raise SystemExit(f"spain_italy_age: {geo} {sex}: {value:,.0f} of unknown age")
    for geo in ("ITH1", "ITH2"):
        for sex in ("M", "F"):
            if sum(by[(geo, sex)].values()) != totals.get((geo, sex)):
                raise SystemExit(f"spain_italy_age: {geo} {sex}: single years make "
                                 f"{sum(by[(geo, sex)].values()):,.0f} against "
                                 f"{totals.get((geo, sex))}")
        if totals[(geo, "M")] + totals[(geo, "F")] != totals.get((geo, "T")):
            raise SystemExit(f"spain_italy_age: {geo}: men and women do not make its total")
    entry = {"men": totals[("ITH1", "M")] + totals[("ITH2", "M")],
             "women": totals[("ITH1", "F")] + totals[("ITH2", "F")],
             "ages": sum((by[(g, s)] for g in ("ITH1", "ITH2") for s in ("M", "F")), Counter())}
    log(f"  {TRENTINO} {year}: {entry['men'] + entry['women']:,.0f} people "
        f"(Bolzano {totals[('ITH1', 'T')]:,.0f}, Trento {totals[('ITH2', 'T')]:,.0f}), median "
        f"{median_age(entry['ages'])}")
    return entry, year


def fields(entry: dict[str, Any], year: int, source: str, url: str, note: str,
           population: bool = True) -> dict[str, Any]:
    out = {
        "median_age": measure(median_age(entry["ages"]), unit="years", year=year,
                              source=source),
        "median_age_note": ("Interpolated within the single year of age holding the middle "
                            "person. " + note),
        "sex_ratio": measure(round(1000 * entry["men"] / entry["women"]),
                             unit="males_per_1000_females", year=year, source=source),
        "sources": [{"field": "population/median age/sex ratio" if population
                     else "median age/sex ratio", "name": source, "url": url, "year": year}],
    }
    if population:
        out["population"] = measure(int(entry["men"] + entry["women"]), year=year,
                                    source=source)
        out["population_note"] = note
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    records: list[dict[str, Any]] = []
    esp = {u["name"]: u for u in json.loads((SITE / "admin2" / "ESP.units.json").read_text())}
    canary, year = spain()
    for code, name in CANARY.items():
        shape = esp.get(name)
        if shape is None:
            raise SystemExit(f"spain_italy_age: no drawn province {name!r}")
        records.append(record(
            f"ESP-INE-{code}", name, level="admin2", parent="ESP", country="ESP",
            match_by="shape_id", shape_id=shape["id"], codes={"ine_province": code},
            **fields(canary[code], year, INE_SOURCE, INE_PAGE,
                     f"The province's residents on 1 January {year}, by sex and single year "
                     "of age (INE's Estadística Continua de Población). Eurostat divides the "
                     "Canary Islands by island, so no NUTS region is this province.")))
    ita = {u["name"]: u for u in json.loads((SITE / "admin2" / "ITA.units.json").read_text())}
    shape = ita.get(TRENTINO)
    if shape is None:
        raise SystemExit(f"spain_italy_age: no drawn region {TRENTINO!r}")
    entry, year = italy()
    records.append(record(
        "ITA-ISTAT-TAA", TRENTINO, level="admin2", parent="ITA", country="ITA",
        match_by="shape_id", shape_id=shape["id"], codes={"nuts": ["ITH1", "ITH2"]},
        **fields(entry, year, EUROSTAT_SOURCE, EUROSTAT.split("?")[0],
                 f"The residents of the autonomous provinces of Bolzano/Bozen (ITH1) and "
                 f"Trento (ITH2) on 1 January {year}, added age by age: the region is two "
                 "NUTS-2 regions and has no NUTS figure of its own.")))
    write_json(args.out or PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
