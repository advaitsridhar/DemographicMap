#!/usr/bin/env python3
"""Suriname: the 2012 census by ressort, and the 2004 census's religion and language.

All from the General Bureau of Statistics (ABS):

* **2012, ethnic group by ressort** (census8etn.pdf): every ressort of every
  district, its population by the thirteen answers to question 8, and each
  district's total row.
* **2012, age and sex** (Volume I): each district's population by five-year
  age group and sex (Table 10), and each ressort's (Tables 9.1-9.62). The
  sex ratio and the median age (interpolated within the five-year group
  holding the middle person, those of unknown age left out). A ressort's
  population is the ethnic table's, whose ressorts make their district's row;
  Volume I's ressort tables agree with it to within a few people except
  Livorno (9,303 against 8,209; its Paramaribo ressorts make 1,129 more than
  the district), whose ages and sexes are therefore not written.
* **2004, the ressort profile** (census-profile-on-ressort-level.xls, "census
  VII"): each ressort's population by religion, in the six groups the ABS
  tabulates there, and its households by the language most spoken in them.
  The 2012 census publishes neither below the country, so these are the most
  recent figures by ressort; the districts' are their ressorts' sums.

The ressorts are bound to the map's by name within the district, spellings
the sources and the map plainly share written out in ALIASES; a ressort the
map draws under another district binds when its name is the only one of its
kind in both. The map draws no Beekhuizen, Tammenga, Latour or Paramaribo's
Welgelegen, and those four are left out.

Checks, each of which stops the run: every ressort's ethnic groups, ages,
sexes, religions and languages make its totals, its 2012 tables agree with
each other within five people, and the ressorts make their district's row
and the country's.

Usage:
    python -m scripts.fetch_census.suriname_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter, defaultdict
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares,
                      write_json)
from .binding import fold
from .cod_ps_age import grouped_median

OUT = PROCESSED / "suriname_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
ETN = "https://www.statistics-suriname.org/wp-content/uploads/2019/03/census8etn.pdf"
VOL1 = ("https://statistics-suriname.org/wp-content/uploads/2019/05/Publicatie-Census-8-"
        "Volume-1-Demografische-en-Sociale-Karakteristieken-en-Migratie.pdf")
PROFILE = ("https://www.statistics-suriname.org/wp-content/uploads/2019/03/"
           "census-profile-on-ressort-level.xls")
SOURCE_ETN = ("General Bureau of Statistics (ABS) Suriname, Census 2012: population by "
              "ressort and ethnic group (question 8)")
SOURCE_VOL1 = ("General Bureau of Statistics (ABS) Suriname, Census 2012 Volume I, Tables "
               "9.1-9.62: population of the ressorts by age group and sex")
SOURCE_2004 = ("General Bureau of Statistics (ABS) Suriname, Census VII (2004): population "
               "characteristics per ressort")
NATIONAL_2012 = 541_638
SLACK = 5
DISTRICTS = ("Paramaribo", "Wanica", "Nickerie", "Coronie", "Saramacca", "Commewijne",
             "Marowijne", "Para", "Brokopondo", "Sipaliwini")
# The sources' and the map's spellings of one ressort, folded, -> one key.
ALIASES = {
    "centrumparamaribo": "centrum", "centrumbrokopondo": "centrum",
    "brokopondocentrum": "centrum", "welgelegenparbo": "welgelegen",
    "welgelegencoronie": "welgelegen", "paranoord": "noord", "paraoost": "oost",
    "parazuid": "zuid", "marchallkreeek": "marshallkreek", "marchallkreek": "marshallkreek",
    "marechallkreek": "marshallkreek", "wayambo": "wayamboweg", "wayomboweg": "wayamboweg",
    "almaar": "alkmaar", "livornio": "livorno", "pontibuiten": "pontbuiten",
    "wegnaarsee": "wegnaarzee", "sarakreet": "sarakreek", "coeroenie": "coeroeni",
    "oostpolders": "oostelijkepolders", "westpolders": "westelijkepolders",
    "nwamsterdam": "nieuwamsterdam", "moengotapoe": "moengotapoe", "patamaka": "patamacca",
    "moengotapu": "moengotapoe", "kwarasan": "koewarasan",
}
ETHNICITY = ("Indigenous", "Maroon", "Creole", "Afro-Surinamese", "Hindustani", "Javanese",
             "Chinese", "White", "Mixed", "Other", "Not stated", "Not stated")
RELIGION = {"Christianity": "Christianity", "Hinduism": "Hinduism", "Islam": "Islam",
            "Traditional Religion +Others": "Traditional religion and other",
            "No religion": "No religion", "Don't know/No answer": "Not stated"}
LANGUAGE = {"Dutch": "Dutch", "Sranan tongo": "Sranan Tongo", "Sarnami": "Sarnami Hindustani",
            "Javanese": "Javanese", "Arowaks Indigenous languages": "Arawak",
            "Caraib": "Kari'na", "Saramaccaans": "Saramaccan",
            "Aucaans Marron languages": "Ndyuka", "Paramaccaans": "Pamaka",
            "Chinese": "Chinese", "Portugese": "Portuguese", "English": "English",
            "French": "French", "Other": "Other language", "Unknown": "Not stated"}
AGE = re.compile(r"(\d+\s*-\s*\d+|\d+\+|Onbekend|Totaal)\s+(\d+)\s+(\d+)\s+(\d+)")


def key(name: str) -> str:
    folded = fold(re.sub(r"\((.*?)\)", r"\1", name))
    return ALIASES.get(folded, folded)


def present(counts: dict[str, float]) -> list[dict]:
    return shares({k: v for k, v in counts.items() if v})


def near(made: int, printed: int, what: str, share: float = 0.0) -> None:
    """Within SLACK people (or ``share`` of the figure, if larger), logged; else stop."""
    if abs(made - printed) > max(SLACK, share * printed):
        raise SystemExit(f"suriname_census: {what} make {made:,}, printed {printed:,}")
    if made != printed:
        log(f"  {what} make {made:,}, printed {printed:,}")


# -- 2012: ethnic group by ressort -----------------------------------------------------

def ethnic_table(lines: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
    """{district: {ressort key: {"name", "total", "counts"}, "_total": {...}}} from census8etn."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    district = None
    for line in lines:
        text = line.strip()
        if text.title() in DISTRICTS and text.isupper():
            district = text.title()
            out[district] = {}
            continue
        m = re.match(r"^(.+?)\s+((?:[\d,]+\s+){12}[\d,]+)$", text)
        if not m or district is None or m[1].startswith("ressort"):
            continue
        figures = [int(t.replace(",", "")) for t in m[2].split()]
        total, parts = figures[0], figures[1:]
        if sum(parts) != total:
            raise SystemExit(f"suriname_census: ethnic groups of {m[1]} make {sum(parts)} "
                             f"of {total}")
        counts: dict[str, int] = defaultdict(int)
        for label, n in zip(ETHNICITY, parts):
            counts[label] += n
        name = "_total" if m[1] == "Total" else key(m[1])
        out[district][name] = {"name": m[1], "total": total, "counts": dict(counts)}
    if set(out) != set(DISTRICTS):
        raise SystemExit(f"suriname_census: the ethnic table has districts {sorted(out)}")
    national = 0
    for district, rows in out.items():
        whole = rows.pop("_total", None)
        if whole is None:
            raise SystemExit(f"suriname_census: {district} has no total row")
        for label in set(ETHNICITY):
            made = sum(r["counts"][label] for r in rows.values())
            if made != whole["counts"][label]:
                raise SystemExit(f"suriname_census: {district}'s ressorts make {made} {label}, "
                                 f"its row {whole['counts'][label]}")
        rows["_total"] = whole
        national += whole["total"]
    if national != NATIONAL_2012:
        raise SystemExit(f"suriname_census: the districts make {national:,}, not "
                         f"{NATIONAL_2012:,}")
    return out


# -- 2012: age and sex by ressort ------------------------------------------------------

def age_tables(lines: list[str]) -> dict[tuple[str, str], dict[str, Any]]:
    """{(district, ressort key): {"name", "groups", "unknown", "total", "men", "women"}}.

    The volume prints the tables two abreast: "Tabel 9.1: Paramaribo Tabel
    9.2: Paramaribo", then "Ressort Blauwgrond Ressort Rainville", then one
    line an age group holding both tables' rows.
    """
    out: dict[tuple[str, str], dict[str, Any]] = {}
    pair: list[dict[str, Any]] = []
    districts: list[str] = []
    for line in lines:
        text = line.strip()
        titles = re.findall(r"Tabel 9\.\d+:\s*([A-Za-z]+)", text)
        if titles:
            districts = [t.title() for t in titles]
            continue
        if text.startswith("Ressort ") and districts:
            names = [n.strip() for n in re.split(r"\bRessort\b", text) if n.strip()]
            if len(names) != len(districts):
                raise SystemExit(f"suriname_census: {text!r} under {districts}")
            pair = [{"district": d, "name": n, "groups": [], "unknown": 0}
                    for d, n in zip(districts, names)]
            continue
        rows = AGE.findall(text)
        if not rows or not pair:
            continue
        if len(rows) != len(pair):
            raise SystemExit(f"suriname_census: {text!r} has {len(rows)} rows for {len(pair)} "
                             "tables")
        for table, (label, total, men, women) in zip(pair, rows):
            total, men, women = int(total), int(men), int(women)
            if men + women != total:
                raise SystemExit(f"suriname_census: {table['name']} {label}: {men} + {women} "
                                 f"!= {total}")
            if label == "Onbekend":
                table["unknown"] = total
            elif label == "Totaal":
                made = sum(g[2] for g in table["groups"]) + table["unknown"]
                if made != total:
                    raise SystemExit(f"suriname_census: {table['name']}'s ages make {made}, "
                                     f"its total {total}")
                table.update(total=total, men=men, women=women)
                out[(table["district"], key(table["name"]))] = table
            else:
                span = re.match(r"(\d+)\s*(?:-\s*(\d+)|\+)", label)
                high = int(span[2]) if span[2] else None
                table["groups"].append((int(span[1]), high, total))
    return out


AGE10 = re.compile(r"(?:([A-Z][a-z]+)\s+)?(\d+\s*-\s*\d+|\d+\+|Onbekend|Totaal)\s+([\d,]+)\s+"
                   r"([\d,]+)\s+([\d,]+)")


def table_10(lines: list[str]) -> dict[str, dict[str, Any]]:
    """{district: {"groups", "unknown", "total", "men", "women"}} from Volume I, Table 10.

    Two districts abreast, as the ressort tables are; a block's first line
    names both districts before their first age group.
    """
    out: dict[str, dict[str, Any]] = {}
    pair: list[dict[str, Any]] = []
    for line in lines:
        rows = AGE10.findall(line.strip())
        if len(rows) != 2:
            continue
        if rows[0][0] and rows[1][0]:
            pair = [{"district": r[0], "groups": [], "unknown": 0} for r in rows]
        if not pair:
            continue
        for table, (_, label, total, men, women) in zip(pair, rows):
            total, men, women = (int(x.replace(",", "")) for x in (total, men, women))
            if men + women != total:
                raise SystemExit(f"suriname_census: Table 10's {table['district']} {label} "
                                 "does not add up")
            if label == "Onbekend":
                table["unknown"] = total
            elif label == "Totaal":
                made = sum(g[2] for g in table["groups"]) + table["unknown"]
                if made != total:
                    raise SystemExit(f"suriname_census: Table 10's {table['district']} ages "
                                     f"make {made}, its total {total}")
                table.update(total=total, men=men, women=women)
                out[table["district"]] = table
            else:
                span = re.match(r"(\d+)\s*(?:-\s*(\d+)|\+)", label)
                table["groups"].append((int(span[1]), int(span[2]) if span[2] else None, total))
    if set(out) != set(DISTRICTS) or sum(t["total"] for t in out.values()) != NATIONAL_2012:
        raise SystemExit(f"suriname_census: Table 10 has {sorted(out)}, "
                         f"{sum(t['total'] for t in out.values()):,} people")
    return out


# -- 2004: the ressort profile -----------------------------------------------------------

def profile(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """{ressort column name: {"religion": Counter, "language": Counter, "people", "households"}}."""
    header = next((r for r in rows if len(r) > 3 and str(r[1]).strip() == "Variabele"), None)
    if header is None:
        raise SystemExit("suriname_census: the profile has no header row")
    names = [str(c).strip() for c in header[3:] if str(c or "").strip()]
    out = {n: {"religion": Counter(), "language": Counter()} for n in names}
    section = None
    for row in rows:
        first, label = row[0], re.sub(r"\s+", " ", str(row[1] or "")).strip()
        # xlrd reads the section numbers as floats (3.0), a text cell as "3".
        if (isinstance(first, float) and first.is_integer()) or str(first).strip().isdigit():
            section = label
            continue
        values = row[2:3 + len(names)]
        if not label or len(values) < len(names) + 1:
            continue
        try:
            figures = [int(round(float(v))) for v in values]
        except (TypeError, ValueError):
            continue
        if section == "Religion":
            if label == "Total":
                for n, v in zip(names, figures[1:]):
                    out[n]["people"] = v
            elif label in RELIGION:
                for n, v in zip(names, figures[1:]):
                    out[n]["religion"][RELIGION[label]] += v
            else:
                raise SystemExit(f"suriname_census: profile religion {label!r} is not one "
                                 "this reads")
        elif section == "Heads of Households" and label == "Number of Households":
            for n, v in zip(names, figures[1:]):
                out[n]["households"] = v
        elif section and section.startswith("Most Spoken Language"):
            if label not in LANGUAGE:
                raise SystemExit(f"suriname_census: profile language {label!r} is not one "
                                 "this reads")
            for n, v in zip(names, figures[1:]):
                out[n]["language"][LANGUAGE[label]] += v
    for n, unit in out.items():
        if sum(unit["religion"].values()) != unit.get("people"):
            raise SystemExit(f"suriname_census: {n}'s religions make "
                             f"{sum(unit['religion'].values())} of {unit.get('people')}")
        if sum(unit["language"].values()) != unit.get("households"):
            raise SystemExit(f"suriname_census: {n}'s languages make "
                             f"{sum(unit['language'].values())} of {unit.get('households')} "
                             "households")
    return out


# -- binding -----------------------------------------------------------------------------

def bind(ressorts: list[tuple[str, str]], shapes: list[dict], district_of: dict[str, str]
         ) -> tuple[dict[tuple[str, str], dict], list[tuple[str, str]], list[tuple[str, str]]]:
    """({(district, key): shape}, left out, bound across a district line)."""
    by_name: dict[tuple[str, str], list[dict]] = defaultdict(list)
    anywhere: dict[str, list[dict]] = defaultdict(list)
    for shape in shapes:
        by_name[(district_of[shape["parent"]], key(shape["name"]))].append(shape)
        anywhere[key(shape["name"])].append(shape)
    named = Counter(k for _, k in ressorts)
    bound, left, across = {}, [], []
    for district, name in ressorts:
        here = by_name.get((district, name), [])
        if len(here) == 1:
            bound[(district, name)] = here[0]
        elif not here and named[name] == 1 and len(anywhere.get(name, [])) == 1:
            bound[(district, name)] = anywhere[name][0]
            across.append((district, name))
        else:
            left.append((district, name))
    taken = Counter(s["id"] for s in bound.values())
    for k in [k for k, s in bound.items() if taken[s["id"]] > 1]:
        left.append(k)
        del bound[k]
    return bound, sorted(left), across


# -- fetching and writing ------------------------------------------------------------------

def pdf_lines(url: str, first: int = 1, last: int | None = None) -> list[str]:
    import pdfplumber
    out: list[str] = []
    with pdfplumber.open(io.BytesIO(http_get(url, binary=True, cache=False))) as pdf:
        for page in pdf.pages[first - 1:last]:
            out += (page.extract_text() or "").splitlines()
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    ethnic = ethnic_table(pdf_lines(ETN))
    ages = age_tables(pdf_lines(VOL1, 54, 69))
    import xlrd
    book = xlrd.open_workbook(file_contents=http_get(PROFILE, binary=True, cache=False))
    sheet = book.sheet_by_index(0)
    old = profile([sheet.row_values(i) for i in range(sheet.nrows)])

    ressorts = [(d, k) for d, rows in ethnic.items() for k in rows if k != "_total"]
    if set(ressorts) != set(ages):
        raise SystemExit(f"suriname_census: the ethnic and age tables differ: "
                         f"{sorted(set(ressorts) ^ set(ages))}")
    districts = table_10(pdf_lines(VOL1, 70, 72))
    for d in DISTRICTS:
        near(districts[d]["total"], ethnic[d]["_total"]["total"],
             f"{d}'s Table 10 against its ethnic table row")
    # A ressort's population is the ethnic table's, whose ressorts make their
    # district's row. Volume I's ressort tables mostly agree to the person; a
    # few differ (its Paramaribo ressorts make 242,053 against the district's
    # 240,924, Livorno 9,303 against 8,209), and where they differ by more than
    # 1% Volume I's ages and sexes are not taken to describe the ressort.
    agree = set()
    for d, k in ressorts:
        made, printed = ages[(d, k)]["total"], ethnic[d][k]["total"]
        if abs(made - printed) <= max(SLACK, 0.01 * printed):
            agree.add((d, k))
            if made != printed:
                log(f"  {d} {k}: Volume I {made:,}, the ethnic table {printed:,}")
        else:
            log(f"  {d} {k}: Volume I {made:,}, the ethnic table {printed:,}; its ages and "
                "sexes are left out")
    old_by_key: dict[str, list[str]] = defaultdict(list)
    for column in old:
        old_by_key[key(column)].append(column)
    district_2004 = {}
    for d, k in ressorts:
        columns = old_by_key.get(k, [])
        if len(columns) == 1:
            district_2004[(d, k)] = columns[0]
        else:
            # Two columns of one name (Centrum, Welgelegen): the profile names the
            # district in the column, "Brokopondo Centrum", "Welgelegen (Coronie)".
            own = [c for c in columns if fold(d) in fold(c)] or \
                  [c for c in columns if not any(fold(x) in fold(c) for x in DISTRICTS)]
            if len(own) != 1:
                raise SystemExit(f"suriname_census: 2004 column for {d} {k}: {columns}")
            district_2004[(d, k)] = own[0]

    admin1 = json.loads((SITE / "admin1" / "SUR.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "SUR.units.json").read_text())
    district_shape = {d: next(u for u in admin1 if fold(u["name"]) == fold(d)) for d in DISTRICTS}
    district_of = {u["id"]: d for d, u in district_shape.items()}
    bound, left, across = bind(ressorts, admin2, district_of)
    log(f"  {len(ressorts)} ressorts; {len(bound)} bound, {len(across)} across a district "
        f"line: {across}; left out: {left}")
    unbound = [s["name"] for s in admin2 if s["id"] not in {b['id'] for b in bound.values()}]
    if unbound:
        raise SystemExit(f"suriname_census: map ressorts with no census ressort: {unbound}")

    def fields(age, people, eth, rel, lang, households, where) -> dict[str, Any]:
        out: dict[str, Any] = dict(
            population=measure(people, year=2012, source=SOURCE_ETN),
            population_note=f"The 2012 census's de jure population{where}.")
        if age is None:
            why = ("Volume I's age table for the ressort counts a different number of people "
                   "from the census's ressort table (more than 1% apart), so neither its "
                   "ages nor its sexes are taken to be the ressort's.")
            out.update(median_age=gap(NOT_AVAILABLE, why), sex_ratio=gap(NOT_AVAILABLE, why))
        else:
            out.update(
                sex_ratio=measure(round(1000 * age["men"] / age["women"]),
                                  unit="males_per_1000_females", year=2012, source=SOURCE_VOL1),
                sex_ratio_note=f"Men per thousand women, 2012{where}.",
                median_age=measure(grouped_median(sorted(age["groups"], key=lambda g: g[0])),
                                   unit="years", year=2012, source=SOURCE_VOL1),
                median_age_note=("Interpolated within the five-year age group holding the "
                                 f"middle person, 2012{where}; people of unknown age left "
                                 "out."))
        return out | dict(
            ethnicity=present(eth), ethnicity_year=2012,
            ethnicity_note=("Ethnic group (question 8), 2012; \"Weet niet\" and \"Geen "
                            f"antwoord\" are written together as Not stated{where}."),
            religion=present(rel), religion_year=2004,
            religion_note=("Religion in the six groups the 2004 census's ressort profile "
                           f"tabulates{where}; the 2012 census publishes none below the "
                           "country."),
            language=present(lang), language_year=2004,
            language_basis="households by the language most spoken in them",
            language_note=(f"The language most spoken in the household, share of the "
                           f"{households:,} households, 2004{where}; the 2012 census "
                           "publishes none below the country."),
            sources=[{"field": "sex_ratio/median_age", "name": SOURCE_VOL1,
                      "url": VOL1, "year": 2012},
                     {"field": "population/ethnicity", "name": SOURCE_ETN, "url": ETN,
                      "year": 2012},
                     {"field": "religion/language", "name": SOURCE_2004, "url": PROFILE,
                      "year": 2004}])

    records = []
    for d in DISTRICTS:
        mine = [(dd, k) for dd, k in ressorts if dd == d]
        rel, lang, households = Counter(), Counter(), 0
        for r in mine:
            rel.update(old[district_2004[r]]["religion"])
            lang.update(old[district_2004[r]]["language"])
            households += old[district_2004[r]]["households"]
        shape = district_shape[d]
        records.append(record(
            f"SUR-ABS-{fold(d)}", shape["name"], level="admin1", parent="SUR", country="SUR",
            match_by="shape_id", shape_id=shape["id"],
            **fields(districts[d], ethnic[d]["_total"]["total"], ethnic[d]["_total"]["counts"],
                     rel, lang, households, ", the district")))
    for (d, k), shape in bound.items():
        o = old[district_2004[(d, k)]]
        records.append(record(
            f"SUR-ABS-{fold(d)}-{k}", shape["name"], level="admin2", parent="SUR",
            country="SUR", parent_name=district_of[shape["parent"]], match_by="shape_id",
            shape_id=shape["id"],
            **fields(ages[(d, k)] if (d, k) in agree else None, ethnic[d][k]["total"],
                     ethnic[d][k]["counts"], o["religion"], o["language"], o["households"],
                     "")))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(DISTRICTS)} districts, {len(bound)} ressorts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
