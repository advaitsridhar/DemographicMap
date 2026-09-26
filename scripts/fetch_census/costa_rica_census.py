#!/usr/bin/env python3
"""Costa Rica's 2011 census by province and canton, tabulated on INEC's REDATAM base.

INEC publishes the X Censo Nacional de Población y VI de Vivienda 2011 for
on-line tabulation as the REDATAM base "2011", and its statistical processor
runs a Redatam+SP program sent to it. This asks it for five of the person
questions, each a frequency table broken first by canton and then by
district, and reads the tables back.

What it writes, for the 83 cantons the map draws and the 7 provinces:

* **Median age**, interpolated within the single year of age holding the
  middle person, and the **sex ratio** (EDAD, SEXO), from everyone counted.
  They replace OCHA's projections, which are fill-only.
* **Ethnicity**, from the census's two identity questions, put to everyone:
  P07, whether a person considers themselves indigenous, and P08, which
  people; and P10, the ethnic-racial self-identification of everyone who
  said no to P07. Together they are one composition of the population: the
  indigenous by people, then Black or Afro-descendant, mulatto, Chinese,
  white or mestizo, other and none. P10's "Ignorado" is left out of the
  shares and counted in the note.
* **Population**, the 2011 count, written for the cantons only: the map's
  are newer, from 2021, and the build keeps them; it fills the one canton
  that has none. The provinces carry a 2022 figure and are left alone.

Religion is not written because the 2011 census did not ask it, and
language because it asked only the indigenous whether they speak an
indigenous language (P09, whose "No Aplica" is everyone P07 did not count
as indigenous) -- see the NOT_COLLECTED_POLICY proposal this file's report
carries. The base's person entity holds, in order, parentesco, sexo, edad,
nacimiento, lugar de nacimiento, llegada a Costa Rica, P07-P10, seguro
social, the disability questions, education, ICT use, residence five years
before, marital status, occupation, industry, place of work and children
born; there is no religion variable in it.

**Cantons drawn since 2011.** The boundary file draws Río Cuarto, made a
canton in 2017 out of Grecia's district of the same name (Ley 9440), and
Puerto Jiménez, made one in 2022 out of Golfito's second district. Both are
that district as the census counted it, and Grecia and Golfito are drawn
without them, so they are written without them. Monteverde, a canton since
2021 and a district of Puntarenas in 2011, is not drawn apart: the
Puntarenas polygon carries it, as the 2011 canton did.

Every question's areas must make the census's published 4,301,712 people
with those it was not put to; every canton's districts must make the canton;
P08 must count exactly those P07 counts as indigenous, and P10 everyone
else.

Usage:
    python -m scripts.fetch_census.costa_rica_census
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from typing import Any

from scripts.probe_redatam import Session

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .binding import bind, fold
from .isthmus import by_area, less, median_age, sex_ratio, single_years, summed, translate
from .redatam import Server

PORTAL = "http://sistemas.inec.cr:8080/bininecmm/RpWebEngine.exe/Portal?BASE=2011&lang=esp"
CMDSET = "http://sistemas.inec.cr:8080/bininecmm/RpWebStats.exe/CmdSet"
BASE = "2011"
OUT = PROCESSED / "costa_rica_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2011
NATIONAL = 4_301_712
WHO = "costa_rica_census"
SOURCE = ("INEC Costa Rica, X Censo Nacional de Población y VI de Vivienda 2011, tabulated "
          "on INEC's REDATAM base 2011")
QUESTIONS = {"sex": "POBLACIO.SEXO", "age": "POBLACIO.EDAD", "indigenous": "POBLACIO.CONSIND",
             "people": "POBLACIO.PUEBLOIN", "ethnic": "POBLACIO.ETNIA"}
LEVELS = ("CANTON", "DISTRITO")
SEXES = {"Hombre": "men", "Mujer": "women"}
YES_NO = {"Sí": "yes", "No": "no"}
PEOPLES = {
    "Bribrí": "Bribri", "Brunca o Boruca": "Brunca (Boruca)", "Cabécar": "Cabécar",
    "Chorotega": "Chorotega", "Huetar": "Huetar", "Maleku o Guatuso": "Maleku",
    "Ngöbe o Guaymí": "Ngäbe", "Teribe o Térraba": "Teribe",
    "De otro país": "Indigenous (people of another country)",
    "Ningún pueblo": "Indigenous (no people named)",
}
ETHNIC = {
    "Negro(a) o afrodescendiente": "Black or Afro-descendant", "Mulato(a)": "Mulatto",
    "Chino(a)": "Chinese", "Blanco(a) o mestizo(a)": "White or Mestizo", "Otro": "Other",
    "Ninguna": "No ethnic group",
}
UNKNOWN = "Ignorado"
# (canton, district) -> the canton made of that district since 2011.
SPLITS = {("grecia", "riocuarto"): "Río Cuarto", ("golfito", "puertojimenez"): "Puerto Jiménez"}
# INEC's 2011 canton name -> the boundary file's, where they differ by more than accents.
ALIASES = {"Palmares": "Palmeras", "Aguirre": "Quepos", "Valverde Vega": "Sarchi",
           "León Cortés": "Leon Cortes Castro", "León Cortés Castro": "Leon Cortes Castro",
           "Vásquez de Coronado": "Vazquez de Coronado", "Coronado": "Vazquez de Coronado"}


def fetch(server: Server, level: str) -> dict[str, dict[str, dict[str, Any]]]:
    """{question: {area code: table}} for every area of one level, checked."""
    out = {}
    for question, variable in QUESTIONS.items():
        found = server.frequency(variable, areabreak=level)
        out[question] = by_area(found, f"{question} by {level.lower()}", WHO, NATIONAL)
        log(f"  {variable} by {level.lower()}: {len(out[question])} areas")
    return out


def check_unit(unit: dict[str, dict[str, Any]], where: str) -> None:
    """Every question counts the unit's people, and the identity questions nest."""
    people = unit["sex"]["total"]
    for question in QUESTIONS:
        table = unit[question]
        if table["total"] + (table["na"] or 0) != people:
            raise SystemExit(f"{WHO}: {where}: {question} has {table['total']:,} answers and "
                             f"{table['na']} not applicable against {people:,} people")
    said = dict(unit["indigenous"]["rows"])
    if unit["people"]["total"] != said.get("Sí", 0):
        raise SystemExit(f"{WHO}: {where}: P08 counts {unit['people']['total']:,}, P07 "
                         f"{said.get('Sí', 0):,} indigenous")
    if unit["ethnic"]["total"] != said.get("No", 0):
        raise SystemExit(f"{WHO}: {where}: P10 counts {unit['ethnic']['total']:,}, P07 "
                         f"{said.get('No', 0):,} not indigenous")


def nest(cantons: dict[str, dict], districts: dict[str, dict]) -> None:
    """Every canton's districts must make the canton, question by question."""
    width = {len(code) for question in QUESTIONS for code in cantons[question]}
    if len(width) != 1:
        raise SystemExit(f"{WHO}: canton codes of lengths {sorted(width)}")
    size = width.pop()
    for question in QUESTIONS:
        inside: dict[str, list[dict]] = defaultdict(list)
        for code, table in districts[question].items():
            inside[code[:size]].append(table)
        for code, table in cantons[question].items():
            parts = summed(inside.get(code, []))
            if Counter(dict(parts["rows"])) != Counter(dict(table["rows"])) \
                    or parts["total"] != table["total"]:
                raise SystemExit(f"{WHO}: {question}: canton {code} ({table['name']}) is not "
                                 f"the sum of its {len(inside.get(code, []))} districts")
        stray = set(inside) - set(cantons[question])
        if stray:
            raise SystemExit(f"{WHO}: {question}: districts under no canton: {sorted(stray)}")
    log("  every canton is the sum of its districts, for every question")


def fields(unit: dict[str, dict[str, Any]], level: str) -> dict[str, Any]:
    sexes, _ = translate(unit["sex"]["rows"], SEXES, "sex", WHO)
    ages, unstated = single_years(unit["age"]["rows"], WHO)
    if unstated:
        raise SystemExit(f"{WHO}: {unstated} ages not stated; EDAD has no such category")
    peoples, _ = translate(unit["people"]["rows"], PEOPLES, "people", WHO)
    ethnic, left = translate(unit["ethnic"]["rows"], ETHNIC, "ethnic", WHO, (UNKNOWN,))
    counts = {**peoples, **ethnic}
    people = unit["sex"]["total"]
    out: dict[str, Any] = {
        "median_age": measure(median_age(ages), unit="years", year=YEAR, source=SOURCE),
        "median_age_note": (
            "Interpolated within the single year of age that holds the middle person, from "
            "INEC's count of everyone by single year of age in the 2011 census."),
        "sex_ratio": measure(sex_ratio(sexes["men"], sexes["women"]),
                             unit="males_per_1000_females", year=YEAR, source=SOURCE),
        "ethnicity": shares(counts),
        "ethnicity_year": YEAR,
        "ethnicity_note": (
            "The 2011 census asked everyone whether they consider themselves indigenous (P07) "
            "and, if so, which people they belong to (P08) -- the indigenous lines here, "
            "including those of a people from another country and those who named none; "
            "everyone else was asked their ethnic-racial self-identification (P10), which "
            f"makes the other lines. Of the {people:,} people counted, "
            f"{left[UNKNOWN]:,} answered P10 \"Ignorado\" and are left out of the shares."),
        "sources": [{"field": "median_age/sex_ratio/ethnicity"
                     + ("/population" if level == "admin2" else ""),
                     "name": SOURCE, "url": PORTAL, "year": YEAR}],
    }
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    session = Session()
    session.get(PORTAL)
    server = Server(CMDSET, BASE, session=session, who=WHO)
    cantons = fetch(server, "CANTON")
    districts = fetch(server, "DISTRITO")
    nest(cantons, districts)

    def unit_of(tables: dict[str, dict[str, dict]], code: str) -> dict[str, dict]:
        return {q: tables[q][code] for q in QUESTIONS}

    units: dict[str, dict[str, Any]] = {}
    for code in cantons["sex"]:
        units[code] = {"name": cantons["sex"][code]["name"], "province": code[0],
                       "tables": unit_of(cantons, code), "parts": []}
    size = len(next(iter(cantons["sex"])))
    for (canton, district), new_name in SPLITS.items():
        hits = [c for c, u in units.items() if fold(u["name"]) == canton]
        inside = [d for d, t in districts["sex"].items()
                  if hits and d[:size] == hits[0] and fold(t["name"]) == district]
        if len(hits) != 1 or len(inside) != 1:
            raise SystemExit(f"{WHO}: no single district {district} in canton {canton}: "
                             f"{hits} {inside}")
        whole, code = units[hits[0]], inside[0]
        part = unit_of(districts, code)
        whole["tables"] = {q: less(whole["tables"][q], part[q]) for q in QUESTIONS}
        whole["parts"].append(new_name)
        units[code] = {"name": new_name, "province": code[0], "tables": part,
                       "made_from": whole["name"], "parts": []}
        log(f"  {new_name} is district {code} of {whole['name']}, which is written without it")
    for code, unit in units.items():
        check_unit(unit["tables"], unit["name"])
    total = sum(u["tables"]["sex"]["total"] for u in units.values())
    if total != NATIONAL:
        raise SystemExit(f"{WHO}: the units make {total:,}, not {NATIONAL:,}")
    log(f"  {len(units)} units making INEC's {NATIONAL:,}; every question counts each unit's "
        "people, and P08 and P10 split P07 exactly")

    admin1 = json.loads((SITE / "admin1" / "CRI.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "CRI.units.json").read_text())
    parents = {u["id"]: u["name"] for u in admin1}
    provinces = {}
    for code, table in by_area(server.frequency("POBLACIO.SEXO", areabreak="PROVINCI"),
                               "sex by province", WHO, NATIONAL).items():
        shape = [u for u in admin1 if fold(u["name"]) in (fold(table["name"]),
                                                           fold(f"Provincia {table['name']}"))]
        if len(shape) != 1:
            raise SystemExit(f"{WHO}: province {table['name']!r} has {len(shape)} polygons")
        provinces[code] = (table["name"], shape[0], table["total"])
    bound, missing = bind({code: (u["name"], provinces[u["province"]][1]["name"])
                           for code, u in units.items()}, admin2, parents, ALIASES)
    log(f"  {len(bound)} of {len(units)} cantons bound to their polygons; not: {missing}")
    unbound = sorted(s["name"] for s in admin2 if s["id"] not in set(bound.values()))
    log(f"  polygons with no canton: {unbound}")
    labels = {s["id"]: s["name"] for s in admin2}

    records = []
    by_province: dict[str, list[dict]] = defaultdict(list)
    for code, unit in sorted(units.items()):
        by_province[unit["province"]].append(unit["tables"])
        sid = bound.get(code)
        if sid is None:
            continue
        people = unit["tables"]["sex"]["total"]
        note = None
        if unit.get("made_from"):
            note = (f"The district of {unit['name']} of {unit['made_from']} as the 2011 census "
                    "counted it; it has been a canton of its own since.")
        elif unit["parts"]:
            note = (f"Without {', '.join(unit['parts'])}, a district of it in 2011 and a canton "
                    "of its own since, which the boundary file draws apart.")
        records.append(record(
            f"CRI-INEC-{code}", unit["name"], level="admin2", parent="CRI", country="CRI",
            parent_name=provinces[unit["province"]][1]["name"], codes={"inec": code},
            match_by="shape_id", shape_id=sid,
            aliases=[labels[sid]] if labels[sid] != unit["name"] else [],
            population=measure(people, year=YEAR, source=SOURCE, note=note),
            **fields(unit["tables"], "admin2")))
    for code, (name, shape, people) in sorted(provinces.items()):
        tables = {q: summed([t[q] for t in by_province[code]]) for q in QUESTIONS}
        if tables["sex"]["total"] != people:
            raise SystemExit(f"{WHO}: {name}'s cantons make {tables['sex']['total']:,}, the "
                             f"province {people:,}")
        records.append(record(f"CRI-INEC-{code}", name, level="admin1", parent="CRI",
                              country="CRI", match_by="shape_id", shape_id=shape["id"],
                              **fields(tables, "admin1")))
    log("  every province's cantons make the province")
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records "
        f"({sum(r['level'] == 'admin2' for r in records)} cantons)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
