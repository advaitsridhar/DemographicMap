#!/usr/bin/env python3
"""Venezuela: the 2011 census's indigenous population by state and people.

Venezuela's states had no ethnicity at all, and the country none either: the
Factbook names its groups without shares. INE's *XIV Censo Nacional de
Población y Vivienda 2011* asked everyone whether they belong to an indigenous
people, and which, and publishes the answer by state and people ("Población
indígena por sexo, según entidad federal y pueblo"). Its other identity
question -- whether a person considers themselves moreno, white, Black,
Afro-descendant or other -- is not published by state, so the shares are the
indigenous question's own: each people, and everyone else as "Not indigenous".
The note says so.

The population each state's shares are of is INE's 2011 enumeration by
parroquia ("Población empadronada por sexo, según entidad federal, municipio
y parroquia"), summed to the state. Every state's peoples must make its
indigenous total, and the states must make the national one, in both tables.

Usage:
    python -m scripts.fetch_census.venezuela_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter
from typing import Any

from ._shared import PROCESSED, http_get, log, record, shares, write_json
from .binding import fold

OUT = "venezuela_census.json"
YEAR = 2011
SITE = PROCESSED.parent.parent / "site" / "data"
PEOPLES_URL = "https://ine.gob.ve/wp-content/uploads/2026/04/Pueblos-Indigenas-Censo-2011.xls"
POPULATION_URL = "https://ine.gob.ve/wp-content/uploads/2026/04/Poblacion-Sexo-Censo-2011.xlsx"
SOURCE = ("INE Venezuela, XIV Censo Nacional de Población y Vivienda 2011: población "
          "indígena por entidad federal y pueblo; población empadronada por parroquia")
NOT_INDIGENOUS = "Not indigenous"

# INE's names for a people, where it prints several, to the one this map
# uses, the others in brackets. A label not here is written as INE prints it,
# "A/B" as "A (B)" -- unless it reads as an answer rather than a people, which
# stops the run (RESIDUAL).
PEOPLES = {
    "Añú/Paraujano": "Añú (Paraujano)", "E'ñepá/Panare": "E'ñepá (Panare)",
    "Jivi/Guajibo/Sikwani/Amorúa": "Jivi (Guajibo)", "Yeral/Ñengatú": "Yeral (Ñengatú)",
    "Pemón (Arekuna, Kamarakoto, Taurepán)": "Pemón",
    "Piapoko/Chase": "Piapoco", "Yaruro/Pumé": "Pumé (Yaruro)",
    "Arutani/Uruak": "Arutani (Uruak)", "Wayuu/Guajiro": "Wayuu",
    "Yanomami/Shiriana": "Yanomami", "Yekwana": "Ye'kwana",
    # The Barí of the Sierra de Perijá, written with the country because the
    # patterns read Barí as South Sudan's Bari.
    "Barí": "Barí (Venezuela)",
}
RESIDUAL = re.compile(r"otro|no (?:especific|declar|sabe)|ignorad|sin (?:especific|inform)",
                      re.I)
# Every row of the table is within a state's indigenous total, so an answer
# row is an indigenous person: one who named no people, or one INE does not
# list by name.
UNSTATED = re.compile(r"^(?:no (?:declarad|especificad)|sin (?:especificar|información))", re.I)
OTHER = re.compile(r"^otros?\b", re.I)
# INE's names for a state -> the map's.
STATES = {"Vargas": "La Guaira", "Bolivariano de Miranda": "Miranda"}


def number(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(".", "").replace(",", "")
    if text in ("-", "--"):
        return 0
    return int(text) if text.isdigit() else None


def state_key(name: str) -> str:
    name = re.sub(r"^(?:Estado|Entidad)\s+", "", str(name).strip())
    return fold(STATES.get(name, name))


def people_name(label: str) -> str:
    label = re.sub(r"\s+", " ", label).strip()
    if label in PEOPLES:
        return PEOPLES[label]
    if UNSTATED.match(label):
        return "Indigenous (people not stated)"
    if OTHER.match(label):
        return "Other indigenous people"
    if RESIDUAL.search(label):
        raise SystemExit(f"venezuela_census: {label!r} reads as an answer, not a people; "
                         "say what it is in PEOPLES")
    first, *rest = label.split("/")
    return f"{first} ({', '.join(rest)})" if rest else first


def peoples_table(rows: list[list[Any]]) -> tuple[dict[str, tuple[str, int, Counter]], int]:
    """{state key: (name, indigenous total, people -> count)}, and the national total.

    A state row has its name in the second column and its total in the
    fourth; its peoples follow, named in the third.
    """
    states: dict[str, tuple[str, int, Counter]] = {}
    national = None
    current = None
    for row in rows:
        cells = [str(c).strip() if c is not None else "" for c in row] + [""] * 4
        total = number(row[3] if len(row) > 3 else None)
        if cells[2] == "Total" and not cells[1]:
            national = total
        elif cells[1] and total is not None:
            current = state_key(cells[1])
            states[current] = (re.sub(r"^Estado\s+", "", cells[1]), total, Counter())
        elif cells[2] and total is not None and current:
            states[current][2][people_name(cells[2])] += total
    if national is None:
        raise SystemExit("venezuela_census: the peoples table has no national total")
    for key, (name, total, peoples) in states.items():
        if sum(peoples.values()) != total:
            raise SystemExit(f"venezuela_census: {name}'s peoples make "
                             f"{sum(peoples.values()):,}, and its total is {total:,}")
    if sum(t for _, t, _ in states.values()) != national:
        raise SystemExit("venezuela_census: the states' indigenous totals do not make the "
                         "national one")
    return states, national


def population_table(rows: list[list[Any]]) -> tuple[dict[str, int], int]:
    """{state key: people enumerated}, summed from the parroquias, and the national total."""
    header = next(i for i, r in enumerate(rows)
                  if any(str(c or "").strip() == "Código UBIGEO" for c in r))
    head = [str(c or "").strip() for c in rows[header]]
    entity = head.index("Entidad Federal")
    parish = head.index("Parroquia")
    # The count's column is headed "Total", on the header row or the one below it.
    total_col = next((i for i in range(parish + 1, len(head)) if head[i] == "Total"), None)
    if total_col is None:
        below = [str(c or "").strip() for c in rows[header + 1]]
        total_col = next(i for i in range(parish + 1, len(below)) if below[i] == "Total")
    states: Counter = Counter()
    national = None
    for row in rows[header + 1:]:
        cells = [str(c or "").strip() for c in row] + [""] * (total_col + 1)
        value = number(row[total_col] if len(row) > total_col else None)
        if re.fullmatch(r"\d{6}", cells[1]) and value is not None:
            states[state_key(cells[entity])] += value
        elif cells[parish] == "Total" and value is not None and national is None:
            national = value
    if national is None or sum(states.values()) != national:
        raise SystemExit(f"venezuela_census: the parroquias make {sum(states.values()):,}, "
                         f"and the table's total is {national}")
    return dict(states), national


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    import openpyxl
    import xlrd
    book = xlrd.open_workbook(file_contents=http_get(PEOPLES_URL, binary=True, cache=False))
    sheet = book.sheet_by_index(0)
    peoples, indigenous = peoples_table([sheet.row_values(r) for r in range(sheet.nrows)])
    wb = openpyxl.load_workbook(io.BytesIO(http_get(POPULATION_URL, binary=True, cache=False)),
                                read_only=True, data_only=True)
    population, national = population_table(
        [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)])
    log(f"  {indigenous:,} indigenous people of {national:,} enumerated, in "
        f"{len(peoples)} states of {len(population)}")

    admin1 = json.loads((SITE / "admin1" / "VEN.units.json").read_text())
    shapes = {fold(u["name"]): u for u in admin1}
    records = []
    for key, people in sorted(population.items()):
        shape = shapes.get(key)
        if shape is None:
            raise SystemExit(f"venezuela_census: state {key!r} has no polygon")
        name, total, counts = peoples.get(key, (shape["name"], 0, Counter()))
        if total > people:
            raise SystemExit(f"venezuela_census: {name} has more indigenous people than "
                             "people")
        counts = Counter(counts)
        counts[NOT_INDIGENOUS] = people - total
        records.append(record(
            f"VEN-INE-{key}", shape["name"], level="admin1", parent="VEN", country="VEN",
            match_by="shape_id", shape_id=shape["id"],
            ethnicity=shares(counts), ethnicity_year=YEAR,
            ethnicity_note=(
                "Whether a person belongs to an indigenous people, and which: the 2011 "
                f"census asked everyone, and {total:,} of the {people:,} people enumerated "
                "here said they do. Its other identity question (moreno, white, Black, "
                "Afro-descendant or other) is not published by state, so everyone else is "
                "one line."),
            sources=[{"field": "ethnicity", "name": SOURCE, "url": PEOPLES_URL, "year": YEAR}]))
    missing = sorted(set(peoples) - set(population))
    if missing:
        raise SystemExit(f"venezuela_census: peoples for states with no population: {missing}")
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} states")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
