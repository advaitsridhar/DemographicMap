#!/usr/bin/env python3
"""Honduras's 2013 census by department and municipio, tabulated on INE's REDATAM base.

INE Honduras publishes the XVII Censo de Población y VI de Vivienda 2013 for
on-line tabulation as the REDATAM base CPVHND2013NAC. Its site refuses this
project's reader, and the server that CELADE's directory of REDATAM portals
names first (170.238.108.227) no longer answers; the same base is served at
181.115.7.199, which is where redatam.org's Honduras page sends a reader
today. Its processor runs a Redatam+SP program sent to it; this asks it for
four person questions, each a frequency table broken by department and then
by municipio, and for the crosstab of the two identity questions.

What it writes, for the 18 departments and the 297 municipio polygons:

* **Median age**, interpolated within the single year of age holding the
  middle person, and the **sex ratio** (P03, P02). They replace OCHA's
  projections, which are fill-only. The base prints age 0 under the label
  "edad", its first row; that is read as 0.
* **Ethnicity**, from the census's two identity questions: P05, how everyone
  identifies (indígena, afrohondureño, negro, mestizo, blanco, otro), and
  P06, which people, asked of everyone who answered indígena, afrohondureño
  or negro. The composition is P06's peoples and P05's mestizo, white and
  other. P06's "Otro" -- a people the form does not list -- is split by the
  crosstab of P05 by P06: under indígena it is another indigenous people,
  under afrohondureño or negro (97% of it nationally) an Afro-Honduran or
  Black person of no listed people.

Population is not written. The base holds the 7,657,684 people the census
enumerated; INE's published count, 8,303,771, is that enumeration adjusted
for omission (the base carries the housing adjustment factor, FACTORVI), and
the map's figures are INE's projections for 2024. Shares, medians and ratios
are read from the enumeration.

Religion and language are not written because the 2013 census asked
neither. The base's person entity holds, in order: parentesco, sexo, edad,
registro, P05 auto-identificación, P06 pueblo, the disability questions,
lugar de nacimiento, literacy, schooling, residence five years before,
work, marital status, e-mail and phone, children born and the identity
card -- there is no religion or language variable in it.

**Municipios the boundary file does not draw.** It draws 297 municipios and
Lake Yojoa; the census counts 298. Nueva Frontera, Santa Bárbara (made a
municipio in 1997), has no polygon: its seat, at 15°18′N 88°40′W, lies inside
the one drawn for Macuelizo, which it borders on the south and east. Its
people are counted with Macuelizo's, as that polygon draws them.

Every question's areas must make the base with those it was not put to;
every department's municipios must make the department; P06 must count
exactly those P05 sends to it.

Usage:
    python -m scripts.fetch_census.honduras_census
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from typing import Any

from scripts.probe_redatam import Session

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .binding import bind, fold
from .isthmus import (Patient, by_area, fill_missing, median_age, sex_ratio, single_years,
                      summed, translate)


PORTAL = "http://181.115.7.199/binhnd/RpWebEngine.exe/Portal?BASE=CPVHND2013NAC&lang=esp"
CMDSET = "http://181.115.7.199/binhnd/RpWebStats.exe/CmdSet"
BASE = "CPVHND2013NAC"
OUT = PROCESSED / "honduras_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2013
ENUMERATED = 7_657_684
WHO = "honduras_census"
SOURCE = ("INE Honduras, XVII Censo de Población y VI de Vivienda 2013, tabulated on INE's "
          "REDATAM base CPVHND2013NAC")
QUESTIONS = {"sex": "PERSONA.P02", "age": "PERSONA.P03", "identity": "PERSONA.P05",
             "people": "PERSONA.P06"}
SEXES = {"Hombre": "men", "Mujer": "women"}
ASKED_PEOPLE = ("Indígena", "AfroHondureño", "Negro (a)")
IDENTITY = {"Mestizo (a)": "Mestizo", "Blanco (a)": "White", "Otro": "Other"}
PEOPLES = {
    "Maya -Chortí": "Maya Chortí", "Maya-Chortí": "Maya Chortí", "Lenca": "Lenca",
    "Miskito": "Miskito", "Nahua": "Nahua", "Pech": "Pech", "Tolupán": "Tolupan",
    "Tawahka": "Tawahka", "Garífuna": "Garifuna",
    "Negro de habla inglesa": "English-speaking Black (Honduras)",
}
# P06's "Otro", by the P05 answer that sent a person to P06.
OTHER_PEOPLE = "Otro"
OTHER = {"Indígena": "Other indigenous people",
         "AfroHondureño": "Afro-Honduran or Black (no people listed)",
         "Negro (a)": "Afro-Honduran or Black (no people listed)"}
AGE_ZERO = "edad"
# INE's name -> the boundary file's, where they differ by more than accents.
DEPARTMENTS = {"islasdelabahia": "Bay Islands"}
ALIASES: dict[str, str] = {}
# (department, municipio the boundary file does not draw) -> the one whose polygon holds it.
FOLDED = {("santabarbara", "nuevafrontera"): "macuelizo"}


def fetch(server: Patient, level: str) -> dict[str, dict[str, dict[str, Any]]]:
    """Every question and the crosstab for one level, in one program, checked."""
    found, crossed = server.program(QUESTIONS, areabreak=level,
                                    crosstab=(QUESTIONS["identity"], QUESTIONS["people"]))
    out = {}
    for question, variable in QUESTIONS.items():
        out[question] = by_area(found[question], f"{question} by {level.lower()}", WHO)
        log(f"  {variable} by {level.lower()}: {len(out[question])} areas")
    filled = fill_missing(out, WHO, ENUMERATED)
    log(f"  areas with no table, nobody there having been asked: {filled}; every question's "
        f"answers and not-applicables make the base's {ENUMERATED:,}")
    attach(out, crossed)
    log(f"  the crosstab of P05 by P06 agrees with both questions, in every {level.lower()}")
    return out


def attach(out: dict[str, dict[str, dict[str, Any]]], found: list[dict[str, Any]]) -> None:
    """Put each area's crosstab of P05 by P06 on its P06 table, as "cells".

    Its columns must make P06's counts, and its rows P05's for the answers
    that lead to P06.
    """
    cross: dict[str, dict[str, Any]] = {}
    for table in found:
        if not table["area"]:
            continue
        if table["area"] in cross:
            raise SystemExit(f"{WHO}: crosstab: area {table['area']} printed twice")
        cross[table["area"]] = table
    for code, table in out["people"].items():
        crossed = cross.get(code)
        if crossed is None:
            if table["total"]:
                raise SystemExit(f"{WHO}: {table['name']}: {table['total']:,} answered P06 and "
                                 "the crosstab has no table")
            crossed = {"cells": {}}
        by_column: Counter = Counter()
        for row in crossed["cells"].values():
            by_column.update({c: n for c, n in row.items() if c != "Total"})
        if Counter(dict(table["rows"])) != by_column:
            raise SystemExit(f"{WHO}: {table['name']}: the crosstab's columns are not P06's "
                             f"counts: {dict(by_column)} against {dict(table['rows'])}")
        said = dict(out["identity"][code]["rows"])
        for label, row in crossed["cells"].items():
            if row["Total"] != said.get(label):
                raise SystemExit(f"{WHO}: {table['name']}: the crosstab's {label} row makes "
                                 f"{row['Total']:,}, P05 {said.get(label)}")
        table["cells"] = {label: {c: n for c, n in row.items() if c != "Total"}
                          for label, row in crossed["cells"].items()}


def added(tables: list[dict[str, Any]]) -> dict[str, Any]:
    """P06 tables added, their crosstab cells with them."""
    out = summed(tables)
    cells: dict[str, Counter] = {}
    for table in tables:
        for label, row in table.get("cells", {}).items():
            cells.setdefault(label, Counter()).update(row)
    out["cells"] = {label: dict(row) for label, row in cells.items()}
    return out


def check_unit(unit: dict[str, dict[str, Any]], where: str) -> None:
    people = unit["sex"]["total"]
    for question in QUESTIONS:
        table = unit[question]
        if table["total"] + (table["na"] or 0) != people:
            raise SystemExit(f"{WHO}: {where}: {question} has {table['total']:,} answers and "
                             f"{table['na']} not applicable against {people:,} people")
    said = dict(unit["identity"]["rows"])
    asked = sum(said.get(label, 0) for label in ASKED_PEOPLE)
    if unit["people"]["total"] != asked:
        raise SystemExit(f"{WHO}: {where}: P06 counts {unit['people']['total']:,}, P05 sends "
                         f"{asked:,} to it")


def nest(departments: dict[str, dict], municipios: dict[str, dict]) -> None:
    """Every department's municipios must make it, question by question."""
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


def ages_of(rows: list[tuple[str, int]]) -> Counter:
    """Single years of age; the base's first row, labelled "edad", is age 0."""
    if any(label == AGE_ZERO for label, _ in rows[1:]):
        raise SystemExit(f"{WHO}: {AGE_ZERO!r} is not the first age row")
    rows = [("0" if label == AGE_ZERO else label, n) for label, n in rows]
    years, _ = single_years(rows, WHO)
    return years


def fields(unit: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sexes, _ = translate(unit["sex"]["rows"], SEXES, "sex", WHO)
    identity, _ = translate(unit["identity"]["rows"], IDENTITY, "identity", WHO, ASKED_PEOPLE)
    counts: Counter = Counter(identity)
    for said, row in unit["people"]["cells"].items():
        if said not in OTHER:
            raise SystemExit(f"{WHO}: a crosstab row this file does not know: {said!r}")
        peoples, _ = translate([(c, n) for c, n in row.items() if c != OTHER_PEOPLE], PEOPLES,
                               "people", WHO)
        counts.update(peoples)
        counts[OTHER[said]] += row.get(OTHER_PEOPLE, 0)
    counts = Counter({label: n for label, n in counts.items() if n})
    return {
        "median_age": measure(median_age(ages_of(unit["age"]["rows"])), unit="years", year=YEAR,
                              source=SOURCE),
        "median_age_note": (
            "Interpolated within the single year of age that holds the middle person, from the "
            "2013 census's count of everyone it enumerated by single year of age."),
        "sex_ratio": measure(sex_ratio(sexes["men"], sexes["women"]),
                             unit="males_per_1000_females", year=YEAR, source=SOURCE),
        "ethnicity": shares(counts),
        "ethnicity_year": YEAR,
        "ethnicity_note": (
            "The 2013 census asked everyone how they identify (P05: indigenous, Afro-Honduran, "
            "Black, mestizo, white or other) and asked everyone who answered indigenous, "
            "Afro-Honduran or Black which people they belong to (P06). The peoples here are "
            "P06's answers, and mestizo, white and other P05's. P06's own \"Otro\" is \"Other "
            "indigenous people\" for those who said indigenous and \"Afro-Honduran or Black (no "
            "people listed)\" for those who said Afro-Honduran or Black. Shares are of the "
            f"{unit['sex']['total']:,} people the census enumerated here; INE's published "
            "counts add an adjustment for omission that the tabulation base does not."),
        "sources": [{"field": "median_age/sex_ratio/ethnicity", "name": SOURCE, "url": PORTAL,
                     "year": YEAR}],
    }


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    session = Session()
    session.get(PORTAL)
    server = Patient(CMDSET, BASE, session=session, who=WHO)
    departments = fetch(server, "DEPTO")
    municipios = fetch(server, "MUNIC")
    nest(departments, municipios)

    names = {code: t["name"] for code, t in departments["sex"].items()}
    units: dict[str, dict[str, Any]] = {}
    for code, table in municipios["sex"].items():
        units[code] = {"name": table["name"], "department": code[:2],
                       "tables": {q: municipios[q][code] for q in QUESTIONS}, "parts": []}
    for (dept, gone), into in FOLDED.items():
        found = [c for c, u in units.items()
                 if fold(names[u["department"]]) == dept and fold(u["name"]) == gone]
        target = [c for c, u in units.items()
                  if fold(names[u["department"]]) == dept and fold(u["name"]) == into]
        if len(found) != 1 or len(target) != 1:
            raise SystemExit(f"{WHO}: no single {gone} and {into} in {dept}: {found} {target}")
        part = units.pop(found[0])
        whole = units[target[0]]
        whole["tables"] = {q: (added if q == "people" else summed)(
            [whole["tables"][q], part["tables"][q]]) for q in QUESTIONS}
        whole["parts"].append(part["name"])
        log(f"  {part['name']} ({found[0]}) is counted with {whole['name']}, whose polygon holds it")
    for code, unit in units.items():
        check_unit(unit["tables"], unit["name"])
    for code, name in names.items():
        check_unit({q: departments[q][code] for q in QUESTIONS}, name)
    log(f"  {len(names)} departments and {len(units)} municipios; P06 counts exactly those P05 "
        "sends to it, everywhere")

    admin1 = json.loads((SITE / "admin1" / "HND.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "HND.units.json").read_text())
    parents = {u["id"]: u["name"] for u in admin1}
    shapes1 = {}
    for code, name in names.items():
        wanted = fold(DEPARTMENTS.get(fold(name), name))
        hits = [u for u in admin1 if fold(u["name"]) == wanted]
        if len(hits) != 1:
            raise SystemExit(f"{WHO}: department {name!r} has {len(hits)} polygons")
        shapes1[code] = hits[0]
    bound, missing = bind({code: (u["name"], shapes1[u["department"]]["name"])
                           for code, u in units.items()}, admin2, parents, ALIASES)
    log(f"  {len(bound)} of {len(units)} municipios bound to their polygons; not: {missing}")
    unbound = sorted(s["name"] for s in admin2 if s["id"] not in set(bound.values()))
    log(f"  polygons with no municipio: {unbound}")
    labels = {s["id"]: s["name"] for s in admin2}

    records = []
    for code, unit in sorted(units.items()):
        sid = bound.get(code)
        if sid is None:
            continue
        extra = fields(unit["tables"])
        if unit["parts"]:
            extra["ethnicity_note"] += (
                f" Counted with {', '.join(unit['parts'])}, a municipio since 1997 that the "
                "boundary file draws inside this polygon.")
        records.append(record(
            f"HND-INE-{code}", unit["name"].title(), level="admin2", parent="HND",
            country="HND", parent_name=shapes1[unit["department"]]["name"],
            codes={"ine": code}, match_by="shape_id", shape_id=sid,
            aliases=[labels[sid]] if fold(labels[sid]) != fold(unit["name"]) else [],
            **extra))
    for code, name in sorted(names.items()):
        records.append(record(
            f"HND-INE-{code}", shapes1[code]["name"], level="admin1", parent="HND",
            country="HND", codes={"ine": code}, match_by="shape_id", shape_id=shapes1[code]["id"],
            **fields({q: departments[q][code] for q in QUESTIONS})))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records "
        f"({sum(r['level'] == 'admin2' for r in records)} municipios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
