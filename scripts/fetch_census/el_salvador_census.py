#!/usr/bin/env python3
"""El Salvador's 2024 census by department and district, from the BCR's tables.

The Banco Central de Reserva's Oficina Nacional de Estadística y Censos took
the VII Censo de Población y VI de Vivienda in May and June 2024 and
publishes its tables as workbooks behind its geoportal, one row a
department, municipio and district. The 2024 territorial reform made the old
262 municipios the districts of 44 new municipios; the boundary file draws
the 262, so the district is the second level here, and the department the
first.

Read from four of those workbooks:

* TAB_POB_1: everyone by single year of age and sex. **Population**, the
  **median age** (interpolated within the single year holding the middle
  person) and the **sex ratio**.
* TAB_ETNIA_1: everyone who identifies with an indigenous people, by the
  people named -- Lenca, Nahua Pipil, Kakawira (Cacaopera), Maya Chortí,
  Maya Poqomam, Xinca, Mixe, Alagüilac, Mangue, another, or not known.
* TAB_ETNIA_2: the same question's yes, no and don't know, which is how many
  it was put to.
* TAB_ETNIA_3: whether a person identifies as Afro-descendant, yes, no and
  don't know, put to the same people.

**Ethnicity** is those two questions, as Panama's and Chile's are: the
indigenous by people, the Afro-descendant, and everyone else who answered as
one remaining line. Someone may answer yes to both and the BCR publishes no
cross of the two, so the remainder is those who answered the indigenous
question less both counts; it is labelled as Panama's and Chile's are. Where
the two overlap past the population, the composition is the indigenous
question's alone. Those who did not know whether they are indigenous are
left out of the shares and counted in the note.

Religion is not written: the 2024 census did not ask it. Language is not
either: the census asks everyone aged 3 and over whether they speak a
second language and which (TAB_IDIO_1 and TAB_IDIO_2), and no first or main
language, so there is no composition of what anybody speaks.

Every district's single years must make its total and its men and women
it; the peoples must make the indigenous question's yes; both identity
questions must count the same people, no more than live there; districts
must make their departments and the departments the BCR's 6,029,976.

Usage:
    python -m scripts.fetch_census.el_salvador_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter, defaultdict
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, shares, write_json
from .binding import bind, fold
from .isthmus import median_age, sex_ratio

BASE = "https://censo2024.bcr.gob.sv/wp-content/uploads/tablas-geoportal/2025/"
FILES = {"population": "TAB_POB_1.xlsx", "peoples": "TAB_ETNIA_1.xlsx",
         "indigenous": "TAB_ETNIA_2.xlsx", "afro": "TAB_ETNIA_3.xlsx"}
PAGE = "https://poblacion.bcr.gob.sv/pages/teg-base-de-datos-y-tabulados"
OUT = PROCESSED / "el_salvador_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2024
NATIONAL = 6_029_976
WHO = "el_salvador_census"
SOURCE = ("BCR, Oficina Nacional de Estadística y Censos, VII Censo de Población y VI de "
          "Vivienda 2024 ({table})")
PEOPLES = {
    "lenca": "Lenca", "nahuapipil": "Nahua-Pipil", "kakawiracacaopera": "Kakawira (Cacaopera)",
    "mayaschorti": "Maya Chortí", "mayaspocomames": "Poqomam Maya", "xinca": "Xinca",
    "mixe": "Mixe", "alaguilac": "Alagüilac", "mangue": "Mangue",
    "otro": "Other indigenous people", "nosabenoresponde": "Indigenous (people not stated)",
}
AFRO = "Afro-descendant"
REST = "Mestizo or white (neither indigenous nor Afro-descendant)"
NOT_INDIGENOUS = "Not indigenous"
CODE = re.compile(r"^\s*(\d+)\s*-\s*(.*?)\s*$")
NUMBERED = re.compile(r"^\s*\d+\.\s*")
# The BCR's district name -> the boundary file's, where they differ by more
# than accents: the boundary file's own misspellings among them.
ALIASES: dict[str, str] = {}
# Polygons smaller than this in both directions (degrees), which share their
# name with a real polygon of the same department, are slivers of it.
SLIVER = 0.002


def number(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(round(value))
    text = str(value).strip().replace(",", "")
    if not re.fullmatch(r"-?\d+(\.0+)?", text):
        raise SystemExit(f"{WHO}: {value!r} is not a count")
    return int(float(text))


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def rows_of(key: str) -> list[list[Any]]:
    import openpyxl
    blob = http_get(BASE + FILES[key], binary=True, cache=False, timeout=300)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    sheet = book[book.sheetnames[0]]
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def layout(rows: list[list[Any]], what: str) -> tuple[int, dict[str, int], list[tuple[str, int]],
                                                      str]:
    """(first data row, {place column: index}, [(category, column)], title).

    The header row names the place columns; the categories sit in it or in
    the row below, a category's name over its first column where the row
    below splits it by sex.
    """
    for h, row in enumerate(rows[:12]):
        names = [fold(text(c)) for c in row]
        if "departamentoderesidencia" in names:
            break
    else:
        raise SystemExit(f"{WHO}: {what}: no header row")
    title = " ".join(text(c) for row in rows[:h] for c in row if text(c) and text(c) != "#VALUE!")
    places = {key: names.index(f"{key}deresidencia")
              for key in ("departamento", "municipio", "distrito")}
    age = places["distrito"] + 1
    places["age"] = age
    top, below = rows[h], rows[h + 1]
    columns: list[tuple[str, int]] = []
    current = ""
    for j in range(age + 1, max(len(top), len(below))):
        head = text(top[j]) if j < len(top) else ""
        sub = text(below[j]) if j < len(below) else ""
        if head:
            current = head
        if not (head or sub):
            continue
        columns.append((f"{current}|{sub}" if sub else current, j))
    start = h + 2
    while start < len(rows) and not text(rows[start][places["departamento"]]):
        start += 1
    return start, places, columns, title


# (department, municipio, district) codes -> their names, as the tables first print them.
NAMES: dict[tuple[str, str, str], tuple[str, str, str]] = {}
# The code given a "No Especificado" row: people the tables place in a
# department, or the country, and no further.
UNSPECIFIED = "ne"


def coded(labels: tuple[str, ...]) -> tuple[str, ...]:
    """A place by its codes, "" for a TOTAL: the tables do not agree on the
    spacing around a code's dash ("02- Cuscatlán Sur", "02 - Cuscatlán Sur")."""
    out = []
    for label in labels:
        if label.upper() == "TOTAL":
            out.append("")
            continue
        if fold(label).startswith("noespecificado"):
            out.append(UNSPECIFIED)
            continue
        m = CODE.match(label)
        if not m:
            raise SystemExit(f"{WHO}: a place with no code: {label!r}")
        out.append(m.group(1).zfill(2))
    return tuple(out)


def read(key: str, ages: bool = False) -> tuple[dict[tuple[str, str, str], dict], str]:
    """{(department, municipio, district) codes: {age or "": {column: count}}}, title.

    Only the rows whose age is TOTAL are kept unless ``ages``.
    """
    rows = rows_of(key)
    start, places, columns, title = layout(rows, key)
    out: dict[tuple[str, str, str], dict] = {}
    for row in rows[start:]:
        if len(row) <= places["age"] or not text(row[places["departamento"]]):
            continue
        labels = tuple(text(row[places[k]]) for k in ("departamento", "municipio", "distrito"))
        if not CODE.match(labels[0]) and not fold(labels[0]).startswith("noespecificado"):
            # A footnote under the table ("Fuente: Banco Central de Reserva").
            if any(text(row[j]) for _, j in columns if j < len(row)):
                raise SystemExit(f"{WHO}: {key}: a row with figures and no place: {labels}")
            continue
        place = coded(labels)
        NAMES.setdefault(place, tuple(CODE.match(x).group(2) if CODE.match(x) else x
                                      for x in labels))
        age = text(row[places["age"]])
        if age.upper() != "TOTAL" and not ages:
            continue
        figures = {label: number(row[j] if j < len(row) else None) for label, j in columns}
        unit = out.setdefault(place, {})
        key_age = "" if age.upper() == "TOTAL" else age
        if key_age in unit:
            raise SystemExit(f"{WHO}: {key}: {place} age {age!r} twice")
        unit[key_age] = figures
    log(f"  {FILES[key]}: {title!r}; {len(out)} places; columns {[c for c, _ in columns]}")
    return out, title


def level_of(place: tuple[str, str, str]) -> str:
    dept, mun, dist = place
    if dept == "00":
        return "country"
    if not mun:
        return "department"
    if not dist:
        return "municipio"
    return "district"


def population(tables: dict[tuple[str, str, str], dict]) -> dict[tuple, dict[str, Any]]:
    """Each place's people, men, women and single years, checked."""
    out = {}
    for place, by_age in tables.items():
        total = by_age.get("")
        if total is None:
            raise SystemExit(f"{WHO}: TAB_POB_1: {place} has no TOTAL row")
        people, men, women = (total[c] for c in sorted(total, key=lambda c: (
            0 if c == "Total" else 1 if "hombre" in fold(c) else 2)))
        if men + women != people:
            raise SystemExit(f"{WHO}: {place}: {men:,} men and {women:,} women make not {people:,}")
        years: Counter = Counter()
        for age, figures in by_age.items():
            if not age:
                continue
            m = re.match(r"^(\d+)", age)
            if not m:
                raise SystemExit(f"{WHO}: {place}: age {age!r}")
            years[int(m.group(1))] += figures["Total"]
        if sum(years.values()) != people:
            raise SystemExit(f"{WHO}: {place}: single years make {sum(years.values()):,}, not "
                             f"{people:,}")
        out[place] = {"people": people, "men": men, "women": women, "ages": years}
    return out


ANSWERS = {"si": "yes", "no": "no", "nosabenoresponde": "unknown"}


def answer_of(column: str) -> str:
    """Yes, no or unknown, wherever the column's header puts it: TAB_ETNIA_2
    names the question over its three answers, TAB_ETNIA_3 puts each answer
    over its men and women."""
    for part in column.split("|"):
        found = ANSWERS.get(fold(NUMBERED.sub("", part)))
        if found:
            return found
    raise SystemExit(f"{WHO}: an answer this file does not know: {column!r}")


def identity(peoples: dict, indigenous: dict, afro: dict) -> dict[tuple, dict[str, Any]]:
    """Each place's indigenous by people, and both questions' yes, no and not known."""
    out = {}
    stray = peoples.keys() - indigenous.keys()
    if stray or indigenous.keys() != afro.keys():
        raise SystemExit(f"{WHO}: the identity tables' places differ: "
                         f"{sorted(stray | (indigenous.keys() ^ afro.keys()))[:6]}")
    for place in indigenous:
        named: Counter = Counter()
        total = None
        # TAB_ETNIA_1 prints no row for a place where nobody said yes.
        for column, n in (peoples[place][""] if place in peoples else {}).items():
            head = fold(NUMBERED.sub("", column.split("|")[0]))
            if head == "totalindigenas":
                total = n
                continue
            if head not in PEOPLES:
                raise SystemExit(f"{WHO}: TAB_ETNIA_1: a people this file does not know: "
                                 f"{column!r}")
            named[PEOPLES[head]] += n
        answers = {}
        for key, table in (("indigenous", indigenous), ("afro", afro)):
            counts: Counter = Counter()
            for column, n in table[place][""].items():
                counts[answer_of(column)] += n
            if set(counts) != {"yes", "no", "unknown"}:
                raise SystemExit(f"{WHO}: {key}: columns {sorted(counts)}")
            answers[key] = counts
        if total is not None and total != sum(named.values()):
            raise SystemExit(f"{WHO}: {place}: the peoples make {sum(named.values()):,}, the "
                             f"table's total {total:,}")
        if sum(named.values()) != answers["indigenous"]["yes"]:
            raise SystemExit(f"{WHO}: {place}: the peoples make {sum(named.values()):,}, the "
                             f"question's yes {answers['indigenous']['yes']:,}")
        if sum(answers["indigenous"].values()) != sum(answers["afro"].values()):
            raise SystemExit(f"{WHO}: {place}: the two questions were put to "
                             f"{sum(answers['indigenous'].values()):,} and "
                             f"{sum(answers['afro'].values()):,}")
        out[place] = {"peoples": named, **answers}
    return out


def nest(units: dict[tuple, dict[str, Any]], what: str, fields_: tuple[str, ...]) -> None:
    """Districts make their departments, departments the country."""
    by_dept: dict[str, Counter] = defaultdict(Counter)
    country: Counter = Counter()
    for place, unit in units.items():
        level = level_of(place)
        flat = Counter({f: unit[f] for f in fields_})
        if level == "district":
            by_dept[place[0]].update(flat)
        elif level == "department":
            country.update(flat)
    for place, unit in units.items():
        level = level_of(place)
        want = {f: unit[f] for f in fields_}
        if level == "department" and Counter(want) != by_dept[place[0]]:
            raise SystemExit(f"{WHO}: {what}: {place[0]}'s districts make "
                             f"{dict(by_dept[place[0]])}, not {want}")
        if level == "country" and Counter(want) != country:
            raise SystemExit(f"{WHO}: {what}: the departments make {dict(country)}, not {want}")


def ethnicity(unit: dict[str, Any], people: int) -> dict[str, Any]:
    indigenous, afro = unit["indigenous"], unit["afro"]
    asked = sum(indigenous.values())
    if asked > people:
        raise SystemExit(f"{WHO}: the identity questions were put to {asked:,} of {people:,}")
    answered = asked - indigenous["unknown"]
    named = {label: n for label, n in unit["peoples"].items() if n}
    rest = answered - indigenous["yes"] - afro["yes"]
    tail = (f" The two questions were put to {asked:,} of the {people:,} people counted here; "
            f"{indigenous['unknown']:,} did not know or did not say whether they are indigenous "
            "and are left out of the shares.")
    if rest < 0:
        counts = {**named, NOT_INDIGENOUS: answered - indigenous["yes"]}
        return {"ethnicity": shares(counts), "ethnicity_year": YEAR,
                "ethnicity_note": (
                    "Whether each person identifies with an indigenous people, and which. The "
                    f"census also asked whether a person is Afro-descendant, and {afro['yes']:,} "
                    "said so; with the indigenous that is more than everyone who answered, so "
                    "some answered yes to both, and the BCR publishes no cross of the two. The "
                    "remainder is everyone not indigenous." + tail)}
    counts = {**named, AFRO: afro["yes"], REST: rest}
    return {"ethnicity": shares(counts), "ethnicity_year": YEAR,
            "ethnicity_note": (
                "Two questions the 2024 census put to everyone in a household: whether a person "
                "identifies with an indigenous people, and which; and whether they identify as "
                "Afro-descendant. Someone may answer yes to both, and the BCR publishes no cross "
                "of the two, so the remainder is those who answered less both counts. The "
                "census asks nothing about mestizo or white ancestry." + tail)}


def fields(pop: dict[str, Any], ident: dict[str, Any], level: str) -> dict[str, Any]:
    source = SOURCE.format(table="TAB_POB_1")
    return {
        "population": measure(pop["people"], year=YEAR, source=source),
        "median_age": measure(median_age(pop["ages"]), unit="years", year=YEAR, source=source),
        "median_age_note": ("Interpolated within the single year of age that holds the middle "
                            "person, from the 2024 census's count of everyone by single year "
                            "of age."),
        "sex_ratio": measure(sex_ratio(pop["men"], pop["women"]),
                             unit="males_per_1000_females", year=YEAR, source=source),
        **ethnicity(ident, pop["people"]),
        "sources": [
            {"field": "population/median_age/sex_ratio", "name": source,
             "url": BASE + FILES["population"], "year": YEAR},
            {"field": "ethnicity",
             "name": SOURCE.format(table="TAB_ETNIA_1, TAB_ETNIA_2 and TAB_ETNIA_3"),
             "url": PAGE, "year": YEAR},
        ],
    }


def slivers(shapes: list[dict[str, Any]]) -> set[str]:
    """Polygons too small to be a district that share a real one's name and department."""
    named: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for s in shapes:
        named[(s["parent"], fold(s["name"]))].append(s)
    out = set()
    for group in named.values():
        if len(group) < 2:
            continue
        small = [s for s in group if s["bbox"][2] - s["bbox"][0] < SLIVER
                 and s["bbox"][3] - s["bbox"][1] < SLIVER]
        if len(small) == len(group) - 1:
            out.update(s["id"] for s in small)
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    pop_rows, _ = read("population", ages=True)
    peoples, _ = read("peoples")
    indigenous, _ = read("indigenous")
    afro, afro_title = read("afro")
    if "afro" not in fold(afro_title):
        raise SystemExit(f"{WHO}: TAB_ETNIA_3 is {afro_title!r}, not the Afro-descendant table")
    pop = population(pop_rows)
    nest(pop, "population", ("people", "men", "women"))
    national = [u for p, u in pop.items() if level_of(p) == "country"]
    if len(national) != 1 or national[0]["people"] != NATIONAL:
        raise SystemExit(f"{WHO}: the country's row is {[u['people'] for u in national]}, not "
                         f"{NATIONAL:,}")
    ident = identity(peoples, indigenous, afro)
    flat = {p: {"yes": u["indigenous"]["yes"], "no": u["indigenous"]["no"],
                "unknown": u["indigenous"]["unknown"], "afro": u["afro"]["yes"]}
            for p, u in ident.items()}
    nest(flat, "identity", ("yes", "no", "unknown", "afro"))
    if set(ident) != set(pop):
        raise SystemExit(f"{WHO}: the identity tables' places are not the population table's: "
                         f"{[(p, NAMES.get(p)) for p in sorted(set(ident) ^ set(pop))[:8]]}")
    log(f"  every district's ages, sexes and identity answers checked; districts make their "
        f"departments and the departments the BCR's {NATIONAL:,}")

    admin1 = json.loads((SITE / "admin1" / "SLV.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "SLV.units.json").read_text())
    parents = {u["id"]: u["name"] for u in admin1}
    departments = {}
    for place in pop:
        if level_of(place) != "department":
            continue
        if place[0] == UNSPECIFIED:
            log(f"  {pop[place]['people']:,} people counted in no department")
            continue
        code, name = place[0], NAMES[place][0]
        hits = [u for u in admin1 if fold(re.sub(r"^Departamento de\s+", "", u["name"]))
                == fold(name)]
        if len(hits) != 1:
            raise SystemExit(f"{WHO}: department {name!r} has {len(hits)} polygons")
        departments[code] = (place, name, hits[0])
    districts = {}
    for place in pop:
        if level_of(place) != "district":
            continue
        if UNSPECIFIED in place:
            log(f"  {pop[place]['people']:,} people counted in {NAMES[place]} have no district "
                "to bind to")
            continue
        key = place[0] + place[2]
        if key in districts:
            raise SystemExit(f"{WHO}: district code {key} twice: {NAMES[place]}, "
                             f"{NAMES[districts[key][0]]}")
        districts[key] = (place, NAMES[place][2])
    thin = slivers(admin2)
    log(f"  slivers left out of the binding: {sorted(s['name'] for s in admin2 if s['id'] in thin)}")
    shapes = [s for s in admin2 if s["id"] not in thin]
    bound, missing = bind({key: (name, departments[key[:2]][2]["name"])
                           for key, (_, name) in districts.items()}, shapes, parents, ALIASES)
    log(f"  {len(bound)} of {len(districts)} districts bound to their polygons; not: {missing}")
    unbound = sorted(s["name"] for s in admin2 if s["id"] not in set(bound.values()))
    log(f"  polygons with no district: {unbound}")
    labels = {s["id"]: s["name"] for s in admin2}

    records = []
    for key, (place, name) in sorted(districts.items()):
        sid = bound.get(key)
        if sid is None:
            continue
        records.append(record(
            f"SLV-BCR-{key}", name, level="admin2", parent="SLV", country="SLV",
            parent_name=departments[key[:2]][2]["name"], codes={"bcr": key},
            match_by="shape_id", shape_id=sid,
            aliases=[labels[sid]] if fold(labels[sid]) != fold(name) else [],
            **fields(pop[place], ident[place], "admin2")))
    for code, (place, name, shape) in sorted(departments.items()):
        records.append(record(
            f"SLV-BCR-{code}", name, level="admin1", parent="SLV", country="SLV",
            codes={"bcr": code}, match_by="shape_id", shape_id=shape["id"],
            aliases=[shape["name"]], **fields(pop[place], ident[place], "admin1")))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records "
        f"({sum(r['level'] == 'admin2' for r in records)} districts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
