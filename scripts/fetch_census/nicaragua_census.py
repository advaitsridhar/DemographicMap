#!/usr/bin/env python3
"""Nicaragua's 2005 census by department and municipio, tabulated on INIDE's REDATAM base.

INIDE publishes the VIII Censo de Población y IV de Vivienda 2005 for on-line
tabulation as the REDATAM base VIVPOB05 (dictionary CENSONI). Its processor
runs a Redatam+SP program sent to it; this sends one a level, asking for
five person questions broken by department and then by municipio.

What it writes, for the 17 departments and autonomous regions and the 153
municipios:

* **Median age**, interpolated within the single year of age holding the
  middle person, and the **sex ratio** (P03, P02). They replace OCHA's
  projections, which are fill-only.
* **Religion** (P13, "¿A qué religión pertenece?"), asked of everyone aged 5
  and over -- its "No Aplica" is exactly the census's children under 5.
* **Ethnicity**: P06, whether a person considers themselves to belong to an
  indigenous people, asked of everyone, and P07, which of the listed
  indigenous peoples or ethnic communities -- the Caribbean coast's Creole
  and mestizo communities among them -- asked of those who said yes. The
  composition is P07's answers and P06's "no" as "Not indigenous"; P06's
  "No declarado" is left out and counted in the note, and P07's "No sabe"
  and "Ignorado" are one line, "Indigenous (people not stated)".
* **Population**, the 2005 count. The map's municipios mostly carry OCHA's
  2020 figures, which are newer and stand; ten have none, and this fills
  them.

Language is not written. The census asked it only as P08, "¿Habla la lengua
o idioma del pueblo indígena o comunidad étnica a la que pertenece?", and
only of the members of the seven Caribbean-coast peoples and communities
(Rama, Garífuna, Mayangna, Miskitu, Ulwa, Creole and the coast's mestizos:
the question's 270,870 answers are exactly theirs). Whether some people
speak their people's language is not a composition of what anybody speaks,
and the rest of the country was not asked.

Every question's areas must make the census's 5,142,098 people with those it
was not put to; every department's municipios must make it; P07 must count
exactly those P06 says are indigenous.

Usage:
    python -m scripts.fetch_census.nicaragua_census
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from typing import Any

from scripts.probe_redatam import Session

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .binding import bind, fold
from .isthmus import (Patient, by_area, fill_missing, median_age, sex_ratio, single_years,
                      summed, translate)

PORTAL = "http://redatam.inide.gob.ni/redbin/RpWebEngine.exe/Portal?BASE=VIVPOB05&lang=esp"
CMDSET = "http://redatam.inide.gob.ni/redbin/RpWebStats.exe/CmdSet"
BASE = "VIVPOB05"
OUT = PROCESSED / "nicaragua_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2005
NATIONAL = 5_142_098
WHO = "nicaragua_census"
SOURCE = ("INIDE, VIII Censo de Población y IV de Vivienda 2005, tabulated on INIDE's REDATAM "
          "base VIVPOB05")
QUESTIONS = {"sex": "PERS05.P02", "age": "PERS05.P03", "indigenous": "PERS05.P06",
             "people": "PERS05.P07", "religion": "PERS05.P13"}
SEXES = {"Hombres": "men", "Mujeres": "women", "Hombre": "men", "Mujer": "women"}
YES, NO, UNDECLARED = "Si", "No", "No declarado"
NOT_INDIGENOUS = "Not indigenous"
PEOPLES = {
    "Rama": "Rama", "Garífuna": "Garifuna", "Mayagna-Sumu": "Mayangna", "Miskitu": "Miskito",
    "Ulwa": "Ulwa", "Creole(Kriol)": "Creole",
    "Mestizo de la costa del caribe": "Mestizo of the Caribbean Coast",
    "Xiu-Sutiaba": "Xiu-Sutiaba", "Nahoas-Nicarao": "Nahoa-Nicarao",
    "Chorotega-Nahua-Mange": "Chorotega-Nahua-Mange",
    "Cacaopera-Matagalpa": "Cacaopera-Matagalpa",
    "Otro": "Other indigenous people or ethnic community",
    "No sabe": "Indigenous (people not stated)", "Ignorado": "Indigenous (people not stated)",
}
RELIGION = {
    "Católica": "Catholic", "Evangélica": "Evangelical", "Morava": "Moravian Church",
    "Testigo de Jehová": "Jehovah's Witnesses", "Judaísmo": "Judaism", "Musulmán": "Islam",
    "Otra": "Other religion", "Ninguna": "No religion",
}
# INIDE's department code -> the boundary file's first-level name, where a name
# does not reach it.
REGIONS = {"91": "North Caribbean Coast Autonomous Region",
           "93": "South Atlantic Autonomous Region"}
# The boundary file's municipio names wear "Municipio X", "Municipio de X" or
# "X (Municipio)" -- and twice "Muncipio".
WRAPPER = re.compile(r"^(?:Municipio|Muncipio)\s+(?:de\s+)?|\s*\((?:Municipio|Muncipio)\)\s*$")
DEPT_WRAPPER = re.compile(r"\s*\((?:Departamento|Departemento)\)\s*$")
# INIDE's municipio name -> the boundary file's (unwrapped), where they differ
# by more than accents.
ALIASES = {"Ciudad Darío": "Ciudad Darco", "Dipilto": "Dipilito", "El Jícaro": "El Jacaro",
           "Mozonte": "Monzonte", "El Tortuguero": "El Tortugero",
           "Desembocadura de Río Grande": "Desembocadura de Cruz Río Grande",
           "La Desembocadura de la Cruz de Río Grande": "Desembocadura de Cruz Río Grande",
           "Waspam": "Waspán"}


def fetch(server: Patient, level: str) -> dict[str, dict[str, dict[str, Any]]]:
    found, _ = server.program(QUESTIONS, areabreak=level)
    out = {}
    for question, variable in QUESTIONS.items():
        out[question] = by_area(found[question], f"{question} by {level.lower()}", WHO)
        log(f"  {variable} by {level.lower()}: {len(out[question])} areas")
    filled = fill_missing(out, WHO, NATIONAL)
    log(f"  areas with no table, nobody there having been asked: {filled}; every question's "
        f"answers and not-applicables make {NATIONAL:,}")
    return out


def check_unit(unit: dict[str, dict[str, Any]], where: str) -> None:
    people = unit["sex"]["total"]
    for question in QUESTIONS:
        table = unit[question]
        if table["total"] + (table["na"] or 0) != people:
            raise SystemExit(f"{WHO}: {where}: {question} has {table['total']:,} answers and "
                             f"{table['na']} not applicable against {people:,} people")
    said = dict(unit["indigenous"]["rows"])
    if unit["people"]["total"] != said.get(YES, 0):
        raise SystemExit(f"{WHO}: {where}: P07 counts {unit['people']['total']:,}, P06 "
                         f"{said.get(YES, 0):,} indigenous")
    ages, _ = single_years(unit["age"]["rows"], WHO)
    under5 = sum(n for years, n in ages.items() if years < 5)
    if (unit["religion"]["na"] or 0) != under5:
        raise SystemExit(f"{WHO}: {where}: P13's not-applicable {unit['religion']['na']} is not "
                         f"the {under5:,} children under 5")


def nest(departments: dict[str, dict], municipios: dict[str, dict]) -> None:
    for question in QUESTIONS:
        inside: dict[str, list[dict]] = defaultdict(list)
        for code, table in municipios[question].items():
            inside[code[:2]].append(table)
        for code, table in departments[question].items():
            parts = summed(inside.get(code, []))
            if Counter(dict(parts["rows"])) != Counter(dict(table["rows"])) \
                    or parts["total"] != table["total"]:
                raise SystemExit(f"{WHO}: {question}: department {code} ({table['name']}) is "
                                 f"not the sum of its {len(inside.get(code, []))} municipios")
        stray = set(inside) - set(departments[question])
        if stray:
            raise SystemExit(f"{WHO}: {question}: municipios under no department: {sorted(stray)}")
    log("  every department is the sum of its municipios, for every question")


def fields(unit: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sexes, _ = translate(unit["sex"]["rows"], SEXES, "sex", WHO)
    ages, _ = single_years(unit["age"]["rows"], WHO)
    said, _ = translate(unit["indigenous"]["rows"], {NO: NOT_INDIGENOUS}, "P06", WHO,
                        (YES, UNDECLARED))
    peoples, _ = translate(unit["people"]["rows"], PEOPLES, "P07", WHO)
    religion, _ = translate(unit["religion"]["rows"], RELIGION, "P13", WHO)
    undeclared = dict(unit["indigenous"]["rows"]).get(UNDECLARED, 0)
    people = unit["sex"]["total"]
    return {
        "population": measure(people, year=YEAR, source=SOURCE),
        "median_age": measure(median_age(ages), unit="years", year=YEAR, source=SOURCE),
        "median_age_note": (
            "Interpolated within the single year of age that holds the middle person, from "
            "INIDE's count of everyone by single year of age in the 2005 census."),
        "sex_ratio": measure(sex_ratio(sexes["men"], sexes["women"]),
                             unit="males_per_1000_females", year=YEAR, source=SOURCE),
        "religion": shares(religion),
        "religion_year": YEAR,
        "religion_note": (
            "The religion each person belongs to (P13 of the 2005 census), asked of everyone "
            f"aged 5 and over: the {sum(religion.values()):,} people of that age counted here."),
        "ethnicity": shares({**peoples, **said}),
        "ethnicity_year": YEAR,
        "ethnicity_note": (
            "Two questions of the 2005 census, put to everyone: whether a person considers "
            "themselves to belong to an indigenous people (P06) and, if so, which of the listed "
            "indigenous peoples or ethnic communities (P07) -- the Caribbean coast's Creole and "
            "mestizo communities among them. \"Not indigenous\" is everyone who said no to "
            "P06; \"Indigenous (people not stated)\" those who said yes and did not know or did "
            f"not say which. Of the {people:,} people counted here, {undeclared:,} did not "
            "answer P06 and are left out of the shares."),
        "sources": [{"field": "population/median_age/sex_ratio/religion/ethnicity",
                     "name": SOURCE, "url": PORTAL, "year": YEAR}],
    }


def unwrapped(name: str) -> str:
    return WRAPPER.sub("", name).strip()


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    session = Session()
    session.get(PORTAL)
    server = Patient(CMDSET, BASE, session=session, who=WHO)
    departments = fetch(server, "DEP05")
    municipios = fetch(server, "MUN05")
    nest(departments, municipios)
    names = {code: t["name"] for code, t in departments["sex"].items()}
    for code, name in names.items():
        check_unit({q: departments[q][code] for q in QUESTIONS}, name)
    for code, table in municipios["sex"].items():
        check_unit({q: municipios[q][code] for q in QUESTIONS}, table["name"])
    log(f"  {len(names)} departments and {len(municipios['sex'])} municipios; P07 counts "
        "exactly those P06 calls indigenous, and P13 everyone but the under-5s, everywhere")

    admin1 = json.loads((SITE / "admin1" / "NIC.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "NIC.units.json").read_text())
    parents = {u["id"]: u["name"] for u in admin1}
    shapes1 = {}
    for code, name in names.items():
        wanted = fold(REGIONS.get(code, name))
        hits = [u for u in admin1 if fold(DEPT_WRAPPER.sub("", u["name"])) == wanted]
        if len(hits) != 1:
            raise SystemExit(f"{WHO}: department {name!r} has {len(hits)} polygons")
        shapes1[code] = hits[0]
    shapes = [{**s, "name": unwrapped(s["name"])} for s in admin2]
    bound, missing = bind({code: (t["name"], shapes1[code[:2]]["name"])
                           for code, t in municipios["sex"].items()}, shapes, parents, ALIASES)
    log(f"  {len(bound)} of {len(municipios['sex'])} municipios bound to their polygons; "
        f"not: {missing}")
    unbound = sorted(s["name"] for s in admin2 if s["id"] not in set(bound.values()))
    log(f"  polygons with no municipio: {unbound}")
    labels = {s["id"]: s["name"] for s in admin2}

    records = []
    for code, table in sorted(municipios["sex"].items()):
        sid = bound.get(code)
        if sid is None:
            continue
        records.append(record(
            f"NIC-INIDE-{code}", table["name"], level="admin2", parent="NIC", country="NIC",
            parent_name=shapes1[code[:2]]["name"], codes={"inide": code},
            match_by="shape_id", shape_id=sid, aliases=[labels[sid]],
            **fields({q: municipios[q][code] for q in QUESTIONS})))
    for code, name in sorted(names.items()):
        records.append(record(
            f"NIC-INIDE-{code}", name, level="admin1", parent="NIC", country="NIC",
            codes={"inide": code}, match_by="shape_id", shape_id=shapes1[code]["id"],
            aliases=[shapes1[code]["name"]],
            **fields({q: departments[q][code] for q in QUESTIONS})))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records "
        f"({sum(r['level'] == 'admin2' for r in records)} municipios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
