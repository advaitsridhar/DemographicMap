#!/usr/bin/env python3
"""San Marino, Monaco and Andorra: their statistics offices' own figures for
the castelli, districts and parishes the map draws.

Every one of these units had an encyclopaedia's head count, several of them a
decade old, and nothing else.

* **San Marino** -- the Ufficio Informatica, Tecnologia, Dati e Statistica
  publishes the resident population of each of the nine castelli by sex
  (``popolazione_residente_per_castello.xlsx``: year-ends 2016-2025 and the
  months since). Population and sex ratio at 31 December of the latest year,
  for both of the map's levels (they draw the same nine polygons). Ages are
  published for the Republic only, so no castello has a median age.
* **Monaco** -- Monaco Statistics' register-based 2025 census (report of May
  2026): residents by district (Table 1) and, for the Principality, by sex and
  age group (Table 2). The map's first level is the Principality itself; its
  median age is interpolated within the broad age group holding the middle
  resident (the report's groups are 0-16, 17-24 and then ten years), and
  every record says so. Districts are those of Sovereign Order 4,481 (2013):
  "Ravin de Sainte-Dévote" is part of Les Moneghetti there, while the map
  draws it apart, so Les Moneghetti's figure is written only once the two
  polygons are one unit (``admin2_redrawn.geojson``); until then neither is.
* **Andorra** -- the Departament d'Estadística's population by settlement
  (the Govern's "Població 2010-2025" layer, from the parish censuses), added up
  by parish for the latest year.

Checks, each of which stops the run:

* San Marino: each castello's men and women make its total, and the castelli
  make the Republic's "Totale Generale";
* Monaco: the districts make the Principality's 38,857, and each age group's
  men and women make its total (to within one person: the report prints one
  row a person off);
* Andorra: every settlement names one of the seven parishes, and every parish
  has settlements.

Usage:
    python -m scripts.fetch_census.microstates
"""

from __future__ import annotations

import argparse
import io
import json
import re
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import fold
from .cod_ps_age import grouped_median

OUT = "microstates.json"
SITE = PROCESSED.parent.parent / "site" / "data"
REDRAWN = PROCESSED / "admin2_redrawn.geojson"

# --- San Marino ------------------------------------------------------------

SMR_URL = ("https://www.statistica.sm/pub1/StatisticaSM/dam/jcr:f2871962-4ff6-4672-b42a-"
           "52fb0d539877/popolazione_residente_per_castello.xlsx")
SMR_PAGE = ("https://www.statistica.sm/pub1/StatisticaSM/Dati-statistici/Popolazione/"
            "Struttura-Demografica.html")
SMR_SOURCE = "Ufficio di Statistica della Repubblica di San Marino, popolazione residente per castello"
SMR_NAMES = {"San Marino": "Città di San Marino"}


def cell(value: Any) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def number(value: Any) -> float | None:
    text = cell(value).replace(".", "") if isinstance(value, str) else value
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def san_marino(rows: list[list[Any]]) -> tuple[int, dict[str, dict[str, float]]]:
    """The castelli's men, women and total at the latest year-end."""
    year_row = next((r for r in rows if sum(1 for v in r if re.fullmatch(r"20\d\d", cell(v))) >= 3),
                    None)
    if year_row is None:
        raise SystemExit("microstates: San Marino: no row of years")
    years = {int(cell(v)): j for j, v in enumerate(year_row) if re.fullmatch(r"20\d\d", cell(v))}
    year = max(years)
    col = years[year]
    out: dict[str, dict[str, float]] = {}
    current = None
    for row in rows:
        name, sex = cell(row[0]) if row else "", cell(row[1]) if len(row) > 1 else ""
        if name:
            current = name
        if current is None or sex not in ("M", "F", "Total", "Totale"):
            continue
        value = number(row[col]) if col < len(row) else None
        if value is None:
            continue
        out.setdefault(current, {})["total" if sex.startswith("Total") else sex] = value
    whole = out.pop("Totale Generale", None)
    if whole is None:
        raise SystemExit("microstates: San Marino: no Totale Generale")
    for name, entry in out.items():
        if set(entry) != {"M", "F", "total"} or entry["M"] + entry["F"] != entry["total"]:
            raise SystemExit(f"microstates: San Marino {name}: {entry}")
    for key in ("M", "F", "total"):
        made = sum(e[key] for e in out.values())
        if made != whole[key]:
            raise SystemExit(f"microstates: San Marino: the castelli make {made:,.0f} {key}, "
                             f"the Republic {whole[key]:,.0f}")
    if len(out) != 9:
        raise SystemExit(f"microstates: San Marino: {len(out)} castelli, not 9: {sorted(out)}")
    return year, out


# --- Monaco ----------------------------------------------------------------

MCO_URL = ("https://imsee.mc/en/content/download/310026/file/2025%20Census%20Report.pdf"
           "?inLanguage=eng-GB&version=4")
MCO_PAGE = "https://imsee.mc/en/thematics/population/population-census"
MCO_YEAR = 2025
MCO_SOURCE = "Monaco Statistics (IMSEE), 2025 Population census (register-based), report of May 2026"
MCO_TOTAL = 38857
MCO_DISTRICTS = ["Monte-Carlo", "La Rousse", "La Condamine", "Jardin Exotique", "Les Moneghetti",
                 "Fontvieille", "Larvotto", "Monaco-Ville"]
MCO_DRAWN = {"Les Moneghetti": "Les Monegetti"}
MCO_MERGED = ("Les Monegetti", "Sainte-Dévote")      # drawn apart, one district since 2013
MCO_AGES = [("16 y/o and under", 0, 16), ("17 to 24 y/o", 17, 24), ("25 to 34 y/o", 25, 34),
            ("35 to 44 y/o", 35, 44), ("45 to 54 y/o", 45, 54), ("55 to 64 y/o", 55, 64),
            ("65 to 74 y/o", 65, 74), ("75 y/o and over", 75, None)]
NUM = r"(\d{1,3}(?:,\d{3})*)"


def as_int(text: str) -> int:
    return int(text.replace(",", ""))


def monaco(text: str) -> dict[str, Any]:
    """Table 1 (districts) and Table 2 (age group by sex) off the report's text."""
    districts: dict[str, int] = {}
    for name in MCO_DISTRICTS + ["Total"]:
        m = re.search(rf"(?m)^\s*{re.escape(name)}\s+{NUM}\s+[\d.]+%", text)
        if m:
            districts[name] = as_int(m.group(1))
    missing = [n for n in MCO_DISTRICTS if n not in districts]
    if missing:
        raise SystemExit(f"microstates: Monaco: districts not found in Table 1: {missing}")
    if sum(districts[n] for n in MCO_DISTRICTS) != MCO_TOTAL or districts.get("Total") != MCO_TOTAL:
        raise SystemExit(f"microstates: Monaco: districts make "
                         f"{sum(districts[n] for n in MCO_DISTRICTS):,} against {MCO_TOTAL:,}")
    groups = []
    for label, low, high in MCO_AGES:
        m = re.search(rf"(?m)^\s*{re.escape(label)}\s+{NUM}\s+{NUM}\s+{NUM}\s", text)
        if not m:
            raise SystemExit(f"microstates: Monaco: age group {label!r} not found in Table 2")
        men, women, total = (as_int(g) for g in m.groups())
        if abs(men + women - total) > 1:
            raise SystemExit(f"microstates: Monaco {label}: {men} + {women} is not {total}")
        groups.append((low, high, men, women, total))
    m = re.search(rf"(?m)^\s*Total\s+{NUM}\s+{NUM}\s+{NUM}\s+100%", text)
    if not m:
        raise SystemExit("microstates: Monaco: no Total row in Table 2")
    men, women, total = (as_int(g) for g in m.groups())
    if total != MCO_TOTAL or abs(men + women - total) > 0:
        raise SystemExit(f"microstates: Monaco: Table 2's total {men} + {women} = {total}")
    if abs(sum(g[4] for g in groups) - total) > 1:
        raise SystemExit(f"microstates: Monaco: age groups make {sum(g[4] for g in groups)}")
    median = grouped_median([(low, high, t) for low, high, _, _, t in groups])
    return {"districts": districts, "men": men, "women": women, "median": median}


# --- Andorra ---------------------------------------------------------------

AND_LAYER = ("https://sig.govern.ad/server/rest/services/Hosted/Poblaci%C3%B3_2010_2021/"
             "FeatureServer/0/query?where=1%3D1&outFields=*&returnGeometry=false&f=json")
AND_PAGE = "https://www.estadistica.ad/"
AND_SOURCE = ("Govern d'Andorra, Departament d'Estadística: population by settlement "
              "(Població 2010-2025), added up by parish")
AND_PARISHES = ["Andorra la Vella", "Canillo", "Encamp", "Escaldes-Engordany", "La Massana",
                "Ordino", "Sant Julià de Lòria"]


def andorra(features: list[dict[str, Any]]) -> tuple[int, dict[str, int], int]:
    rows = [f["attributes"] for f in features]
    fields = {k for r in rows for k in r}
    years = sorted(int(k[4:]) for k in fields if re.fullmatch(r"pob_\d{4}", k))
    if not years:
        raise SystemExit(f"microstates: Andorra: no population fields in {sorted(fields)}")
    year = years[-1]
    wanted = {fold(p): p for p in AND_PARISHES}
    out: dict[str, int] = {p: 0 for p in AND_PARISHES}
    for r in rows:
        parish = wanted.get(fold(str(r.get("parroquia") or "")))
        # One spelling in the layer drops a letter ("Sant Julà de Lòria").
        if parish is None and fold(str(r.get("parroquia") or "")).startswith("santjul"):
            parish = "Sant Julià de Lòria"
        if parish is None:
            raise SystemExit(f"microstates: Andorra: settlement {r.get('població')!r} is in "
                             f"parish {r.get('parroquia')!r}")
        out[parish] += int(r.get(f"pob_{year}") or 0)
    empty = [p for p, n in out.items() if n <= 0]
    if empty:
        raise SystemExit(f"microstates: Andorra: parishes with no one: {empty}")
    return year, out, len(rows)


# --- records ---------------------------------------------------------------

def units(iso: str, level: str) -> dict[str, dict[str, Any]]:
    return {fold(u["name"]): u for u in json.loads((SITE / level / f"{iso}.units.json").read_text())}


def merged_in_redraw(ids: list[str]) -> str | None:
    """The id the redraw keeps, if the drawn polygons ``ids`` have been merged."""
    if not REDRAWN.exists():
        return None
    for feature in json.loads(REDRAWN.read_text()).get("features", []):
        props = feature.get("properties") or {}
        if set(ids) <= set(props.get("replaces") or []):
            return props.get("shapeID") or props.get("id")
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    records: list[dict[str, Any]] = []

    # San Marino
    import openpyxl
    blob = http_get(SMR_URL, binary=True, cache=False, timeout=180)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rows = [list(r) for r in book.worksheets[0].iter_rows(values_only=True)]
    year, castelli = san_marino(rows)
    log(f"microstates: San Marino {year}: {sum(e['total'] for e in castelli.values()):,.0f} "
        "residents in 9 castelli")
    for level in ("admin1", "admin2"):
        drawn = units("SMR", level)
        for name, entry in castelli.items():
            shape = drawn.get(fold(SMR_NAMES.get(name, name)))
            if shape is None:
                raise SystemExit(f"microstates: San Marino: no drawn castello {name!r}")
            note = (f"Residents of the castello at 31 December {year}, by sex, from the "
                    "Republic's population register as its statistics office publishes them.")
            records.append(record(
                f"SMR-UDS-{level}-{fold(name)}", shape["name"], level=level, parent="SMR",
                country="SMR", match_by="shape_id", shape_id=shape["id"],
                population=measure(int(entry["total"]), year=year, source=SMR_SOURCE),
                population_note=note,
                sex_ratio=measure(round(1000 * entry["M"] / entry["F"]),
                                  unit="males_per_1000_females", year=year, source=SMR_SOURCE),
                median_age=gap(NOT_AVAILABLE, "San Marino's statistics office publishes ages "
                               "for the Republic only, not by castello."),
                sources=[{"field": "population/sex ratio", "name": SMR_SOURCE, "url": SMR_PAGE,
                          "year": year}]))

    # Monaco
    import pdfplumber
    blob = http_get(MCO_URL, binary=True, cache=False, timeout=180)
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    mco = monaco(text)
    log(f"microstates: Monaco {MCO_YEAR}: {mco['men'] + mco['women']:,} residents, "
        f"{mco['men']:,} men, {mco['women']:,} women, median {mco['median']}")
    principality = next(iter(units("MCO", "admin1").values()))
    records.append(record(
        "MCO-IMSEE-2025", principality["name"], level="admin1", parent="MCO", country="MCO",
        match_by="shape_id", shape_id=principality["id"],
        population=measure(MCO_TOTAL, year=MCO_YEAR, source=MCO_SOURCE),
        sex_ratio=measure(round(1000 * mco["men"] / mco["women"]),
                          unit="males_per_1000_females", year=MCO_YEAR, source=MCO_SOURCE),
        median_age=measure(mco["median"], unit="years", year=MCO_YEAR, source=MCO_SOURCE),
        median_age_note=("Interpolated within the age group holding the middle resident: the "
                         "report publishes residents by sex in eight groups (16 and under, 17 to "
                         "24, then ten-year groups to 75 and over), not by single year. The "
                         "report's mean age is 47.2."),
        sources=[{"field": "population/median age/sex ratio", "name": MCO_SOURCE,
                  "url": MCO_PAGE, "year": MCO_YEAR}]))
    drawn = units("MCO", "admin2")
    keep = merged_in_redraw([drawn[fold(n)]["id"] for n in MCO_MERGED if fold(n) in drawn])
    for name in MCO_DISTRICTS:
        target = MCO_DRAWN.get(name, name)
        shape = drawn.get(fold(target))
        if shape is None:
            raise SystemExit(f"microstates: Monaco: no drawn district {target!r}")
        if target in MCO_MERGED and keep != shape["id"]:
            log(f"  {name}: left out -- the map draws Sainte-Dévote apart from it")
            continue
        records.append(record(
            f"MCO-IMSEE-{fold(name)}", shape["name"], level="admin2", parent="MCO",
            country="MCO", match_by="shape_id", shape_id=shape["id"],
            population=measure(mco["districts"][name], year=MCO_YEAR, source=MCO_SOURCE),
            population_note=("Residents of the district at 31 December 2025, in the districts "
                             "of Sovereign Order 4,481 of 2013."),
            sources=[{"field": "population", "name": MCO_SOURCE, "url": MCO_PAGE,
                      "year": MCO_YEAR}]))

    # Andorra
    from ._shared import http_json
    payload = http_json(AND_LAYER, cache=False, timeout=120)
    year, parishes, settlements = andorra(payload.get("features") or [])
    log(f"microstates: Andorra {year}: {sum(parishes.values()):,} residents in "
        f"{settlements} settlements")
    for level in ("admin1", "admin2"):
        drawn = units("AND", level)
        for parish, people in parishes.items():
            shape = drawn.get(fold(parish))
            if shape is None:
                raise SystemExit(f"microstates: Andorra: no drawn parish {parish!r}")
            records.append(record(
                f"AND-DE-{level}-{fold(parish)}", shape["name"], level=level, parent="AND",
                country="AND", match_by="shape_id", shape_id=shape["id"],
                population=measure(people, year=year, source=AND_SOURCE),
                population_note=(f"The parish's settlements' residents in {year}, added up; "
                                 "the Departament d'Estadística publishes them settlement by "
                                 "settlement."),
                sources=[{"field": "population", "name": AND_SOURCE, "url": AND_PAGE,
                          "year": year}]))
    for r in records:
        pop = r["population"]
        log(f"  {r['country']} {r['level']} {r['name']}: {pop.get('value')}"
            + (f", sex ratio {r['sex_ratio']['value']}" if "value" in r["sex_ratio"] else ""))
    write_json(Path(args.out) if args.out else PROCESSED / OUT, records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
