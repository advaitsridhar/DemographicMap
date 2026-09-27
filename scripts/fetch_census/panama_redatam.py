#!/usr/bin/env python3
"""Panama's districts: median age from the 2023 census, tabulated on INEC's REDATAM base.

``panama_census.py`` reads INEC's workbooks for the 2023 census, and INEC
publishes no table of age by district, so the 75 districts had a population,
a sex ratio and an ethnicity and no median age. INEC also publishes the
census for on-line tabulation, as the REDATAM base LP2023 ("XII Censo de
Población y VIII de Vivienda de Panamá: Año 2023"), and its processor runs a
Redatam+SP program sent to it. This asks it for everyone by single year of
age (P03_EDAD) and by sex, district by district, and writes the median age,
interpolated within the single year holding the middle person. Those whose
age was not declared are left out of it and counted in the note.

The districts are the ones ``panama_census.py`` writes: the six created since
the boundary file was drawn are added back into the district each came from
(its SPLITS), and each is bound to the polygon that file's record for the
same district is bound to (``data/processed/panama_census.json``), so the two
files reach the same shapes. Every district's count here must equal the
count that file wrote from cuadro 11, and the districts must make INEC's
4,064,780.

The same base answers what the 2023 census did not ask. Its person entity
holds, in order: relationship, sex, age, civil registration, citizenship,
marital status, birthplace, residence before and in 2018, P08 indigenous
group, P09 Afro-descendant group, social security, the disability
questions, ICT use, literacy, schooling, work, income and children born. No
religion, and no language: the report's NOT_COLLECTED_POLICY proposals rest
on that list.

Usage:
    python -m scripts.fetch_census.panama_redatam
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any

from scripts.probe_redatam import Session

from ._shared import PROCESSED, log, measure, record, write_json
from .isthmus import by_area, median_age, single_years, translate
from .panama_census import SPLITS, district_key, province_key
from .redatam import Server

PORTAL = "https://www.inec.gob.pa/panbin/RpWebEngine.exe/Portal?BASE=LP2023&lang=esp"
CMDSET = "https://www.inec.gob.pa/panbin/RpWebStats.exe/CmdSet"
BASE = "LP2023"
OUT = PROCESSED / "panama_redatam.json"
CENSUS = PROCESSED / "panama_census.json"
YEAR = 2023
NATIONAL = 4_064_780
WHO = "panama_redatam"
SOURCE = ("INEC Panamá, XII Censo Nacional de Población y VIII de Vivienda 2023, tabulated on "
          "INEC's REDATAM base LP2023")
UNSTATED = ("No declarada", "No declarado")
SEXES = {"Hombre": "men", "Mujer": "women"}
# The base's spelling -> the workbooks' (panama_census's keys).
SPELLING = {"santacatalinaocalovevora": "santacatalinaocalovebora"}
# Taboga's islands are not drawn, and panama_census.py leaves them out too.
UNDRAWN = {("panama", "taboga")}


def keyed(provinces: dict[str, dict], code: str, name: str) -> tuple[str, str]:
    """(province key, district key) as panama_census.py writes them."""
    prov = provinces.get(code[:2])
    if prov is None:
        raise SystemExit(f"{WHO}: district {code} ({name}) under no province")
    dist = district_key(name)
    return province_key(prov["name"]), SPELLING.get(dist, dist)


def merged(ages: dict[str, dict], sexes: dict[str, dict], provinces: dict[str, dict]
           ) -> dict[tuple[str, str], dict[str, Any]]:
    """The districts the boundary file draws, later splits added back."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for code, table in ages.items():
        prov, dist = keyed(provinces, code, table["name"])
        if (prov, dist) in UNDRAWN:
            log(f"  {table['name']} ({code}) is not drawn and is left out, as panama_census "
                "leaves it")
            continue
        target = SPLITS.get((prov, dist), dist)
        unit = out.setdefault((prov, target), {"ages": Counter(), "unstated": 0, "people": 0,
                                               "parts": []})
        years, unstated = single_years(table["rows"], WHO, UNSTATED)
        unit["ages"].update(years)
        unit["unstated"] += unstated
        unit["people"] += table["total"]
        unit["parts"].append(table["name"])
        if sexes[code]["total"] != table["total"]:
            raise SystemExit(f"{WHO}: {table['name']}: {table['total']:,} by age, "
                             f"{sexes[code]['total']:,} by sex")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    session = Session()
    session.get(PORTAL)
    server = Server(CMDSET, BASE, session=session, who=WHO)
    provinces = by_area(server.frequency("PERSONA.P02_SEXO", areabreak="PROVINCIA"),
                        "sex by province", WHO, NATIONAL)
    sexes = by_area(server.frequency("PERSONA.P02_SEXO", areabreak="DISTRITO"),
                    "sex by district", WHO, NATIONAL)
    ages = by_area(server.frequency("PERSONA.P03_EDAD", areabreak="DISTRITO"),
                   "age by district", WHO, NATIONAL)
    for table in sexes.values():
        translate(table["rows"], SEXES, "sex", WHO)
    log(f"  {len(provinces)} provinces and comarcas, {len(ages)} districts making INEC's "
        f"{NATIONAL:,}")
    units = merged(ages, sexes, provinces)

    census = {r["id"]: r for r in json.loads(CENSUS.read_text()) if r["level"] == "admin2"}
    records = []
    missing = []
    for (prov, dist), unit in sorted(units.items()):
        written = census.get(f"PAN-INEC-{prov}-{dist}")
        if written is None:
            missing.append(f"{prov}:{dist}")
            continue
        counted = (written.get("population") or {}).get("value")
        if counted != unit["people"]:
            raise SystemExit(f"{WHO}: {written['name']}: {unit['people']:,} people here, "
                             f"{counted} in panama_census's cuadro 11")
        note = ("Interpolated within the single year of age that holds the middle person, "
                "from INEC's count of everyone by single year of age in the 2023 census")
        if len(unit["parts"]) > 1:
            note += (f", counting {', '.join(p.title() for p in unit['parts'][1:])} with it as "
                     "the boundary file draws it")
        note += (f"; {unit['unstated']:,} people whose age was not declared are left out."
                 if unit["unstated"] else ".")
        records.append(record(
            f"PAN-INEC-{prov}-{dist}", written["name"], level="admin2", parent="PAN",
            country="PAN", parent_name=written.get("parent_name"), match_by="shape_id",
            shape_id=written["shape_id"],
            median_age=measure(median_age(unit["ages"]), unit="years", year=YEAR, source=SOURCE),
            median_age_note=note,
            sources=[{"field": "median_age", "name": SOURCE, "url": PORTAL, "year": YEAR}]))
    if missing:
        raise SystemExit(f"{WHO}: districts panama_census.py did not write: {missing}")
    if len(records) != len(census):
        raise SystemExit(f"{WHO}: {len(records)} districts here, {len(census)} in panama_census")
    log(f"  {len(records)} districts, each the count panama_census wrote from cuadro 11")
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
