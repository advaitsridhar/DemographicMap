#!/usr/bin/env python3
"""Panama: the 2023 census by province, comarca and district.

Panama's 13 provinces and comarcas and 75 districts had a population and
nothing else. INEC's *XII Censo Nacional de Población y VIII de Vivienda 2023*
publishes, as workbooks:

- Resultados finales básicos, cuadro 12: everyone by sex and five-year age
  group, by province and comarca, with INEC's own median age;
- cuadro 11: everyone by sex, by province, district and corregimiento;
- cuadro 20: the indigenous population by the people it belongs to, by
  province and comarca;
- cuadro 32: the Afro-descendant population by the group it names, by
  province, district and corregimiento;
- Volumen II, cuadro 33: the indigenous population by district and
  corregimiento (its "Total" column is everyone, of all ages; the literacy
  columns beside it are those aged 10 and over).

**Median age** is interpolated within the five-year group holding the middle
person; INEC's own median must agree to within two years.

**Ethnicity** is two questions, as in Chile and Argentina: whether a person
is indigenous, and which people; and whether Afro-descendant, and how they
name it. Someone may answer yes to both and INEC publishes no cross of the
two, so both are shown and the remainder is everyone else. Which indigenous
people is published by province only, so a district's indigenous line is one
line.

**Districts drawn before they were split.** The boundary file draws the 75
districts of 2010. Six created since -- Almirante (2015, from Changuinola),
Jirondai and Santa Catalina o Calovébora (2014, from Kankintú and Kusapín),
Omar Torrijos Herrera (2018, from Donoso), Santa Fe in Darién (2021, from
Chepigana) and Tierras Altas (2022, from Bugaba) -- are added back into the
district they were carved from, so the old polygon carries figures for the
whole of it. Taboga's islands are not drawn and are left out.

Usage:
    python -m scripts.fetch_census.panama_census
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from typing import Any

from . import binding
from ._shared import PROCESSED, http_get, log, measure, record, shares, write_json
from .binding import fold
from .cod_ps_age import grouped_median

OUT = "panama_census.json"
YEAR = 2023
BASE = "https://www.inec.gob.pa/archivos/"
FILES = {
    "age": "P07904820231009162521CUADRO 12.xls",
    "sex": "P0705547520251003111538CUADRO 11.xls",
    "peoples": "P0289562520231009163041CUADRO 20.xls",
    "afro": "P0774740120231009163711CUADRO 32.xls",
    "indigenous": "P053342420240206090553Cuadro 33.xls",
}
TABLES = {
    "age": "Resultados finales básicos, cuadro 12",
    "sex": "Resultados finales básicos, cuadro 11",
    "peoples": "Resultados finales básicos, cuadro 20",
    "afro": "Resultados finales básicos, cuadro 32",
    "indigenous": "Volumen II, cuadro 33",
}
SOURCE = "INEC Panamá, XII Censo Nacional de Población y VIII de Vivienda 2023 ({table})"
SITE = PROCESSED.parent.parent / "site" / "data"

# INEC's province or comarca -> the boundary file's.
PROVINCES = {
    "bocasdeltoro": "Provincia de Bocas del Toro", "cocle": "Provincia de Coclé",
    "colon": "Colón Province", "chiriqui": "Provincia de Chiriquí",
    "darien": "Provincia de Darién", "herrera": "Provincia de Herrera",
    "lossantos": "Provincia de Los Santos", "panama": "Provincia de Panamá",
    "panamaoeste": "Provincia de Panamá Oeste", "veraguas": "Provincia de Veraguas",
    "comarcagunayala": "Comarca Guna Yala", "comarcakunayala": "Comarca Guna Yala",
    "comarcaembera": "Comarca Emberá-Wounaan", "comarcaemberawounaan": "Comarca Emberá-Wounaan",
    "comarcangabebugle": "Comarca Ngäbe-Buglé",
}
# (province key, district created since 2010) -> the district it came from.
SPLITS = {
    ("bocasdeltoro", "almirante"): "changuinola",
    ("comarcangabebugle", "jirondai"): "kankintu",
    ("comarcangabebugle", "santacatalinaocalovebora"): "kusapin",
    ("colon", "omartorrijosherrera"): "donoso",
    ("darien", "santafe"): "chepigana",
    ("chiriqui", "tierrasaltas"): "bugaba",
}
# INEC's district name -> the boundary file's, where they differ by more than accents.
ALIASES = {"Guna Yala": "Comarca Kuna Yala", "Kuna Yala": "Comarca Kuna Yala"}
PEOPLES = {
    "Kuna": "Guna", "Guna": "Guna", "Ngäbe": "Ngäbe", "Buglé": "Buglé",
    "Naso Tjërdi": "Naso", "Naso Tjër Di": "Naso", "Naso": "Naso", "Bokota": "Bokota",
    "Emberá": "Embera", "Wounaan": "Wounaan", "Bri Bri": "Bribri", "Bribri": "Bribri",
    "Otro": "Other indigenous people", "Otro grupo": "Other indigenous people",
    "No declarado": "Indigenous (people not stated)",
}
AFRO_COLUMNS = [  # (words INEC's header starts with, the map's label)
    ("afrodescendiente", "Afro-descendant"), ("afropanameno", "Afro-Panamanian"),
    ("moreno", "Moreno"), ("negro", "Black"), ("afrocolonial", "Afro-colonial"),
    ("afroantillano", "Afro-Antillean"), ("otrogrupo", "Afro-descendant (other group)"),
    ("nodeclarado", "Afro-descendant (group not stated)"),
]
INDIGENOUS_DISTRICT = "Indigenous (people not published)"
REST = "Mestizo or white (neither indigenous nor Afro-descendant)"
BAND = re.compile(r"^(\d+)\s*-\s*(\d+)$")
OPEN = re.compile(r"^(\d+) y más$")
UNDER_ONE = "Menores de 1"
UNSTATED = "No declarada"
FOOTNOTE = re.compile(r"\s*\(\d+\)\s*$")


def text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return FOOTNOTE.sub("", "" if value is None else str(value).strip())


def number(value: Any) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(round(value))
    t = str(value or "").strip()
    if t == "-":
        return 0
    try:
        return int(round(float(t)))
    except ValueError:
        return None


def province_key(name: str) -> str:
    return fold(re.sub(r"^provincia de\s+", "", name, flags=re.I))


def rows_of(key: str) -> list[list[Any]]:
    import xlrd
    url = BASE + FILES[key].replace(" ", "%20")
    blob = http_get(url, binary=True, cache=False, timeout=180)
    book = xlrd.open_workbook(file_contents=blob)
    sheet = book.sheet_by_index(0)
    return [sheet.row_values(r) for r in range(sheet.nrows)]


def age_table(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """Cuadro 12: {province: {total, men, women, groups, median}}; "" is the country."""
    units: dict[str, dict[str, Any]] = {}
    current = None
    for row in rows[3:]:
        first, second = text(row[0]), text(row[1])
        figures = [number(c) for c in row[2:5]]
        if first == "Mediana":
            units[current]["median"] = figures[0]
            continue
        if first and figures[0] is not None:
            current = first
        elif second == "TOTAL":
            current = ""
        elif second and current is not None and figures[0] is not None:
            units[current]["groups"][second] = figures
            continue
        else:
            continue
        units[current] = {"total": figures[0], "men": figures[1], "women": figures[2],
                          "groups": {}, "median": None}
    return units


def median_of(groups: dict[str, list[int | None]], what: str) -> float | None:
    bands: list[tuple[int, int | None, int]] = []
    for label, (people, _, _) in groups.items():
        if label == UNSTATED:
            continue
        if label == UNDER_ONE:
            bands.append((0, 0, people))
        elif (m := BAND.match(label)):
            bands.append((int(m.group(1)), int(m.group(2)), people))
        elif (m := OPEN.match(label)):
            bands.append((int(m.group(1)), None, people))
        else:
            raise SystemExit(f"panama_census: {what}: age group {label!r}")
    bands.sort(key=lambda b: b[0])
    expected = 0
    for low, high, _ in bands:
        if low != expected:
            raise SystemExit(f"panama_census: {what}: ages jump from {expected} to {low}")
        expected = (high + 1) if high is not None else None
    return grouped_median(bands)


def peoples_table(rows: list[list[Any]]) -> dict[str, dict[str, int]]:
    """Cuadro 20: {province: {people: count, "": total}}; "" is the country."""
    out: dict[str, dict[str, int]] = {}
    current = None
    for row in rows[3:]:
        first, second = text(row[0]), text(row[1])
        people = number(row[2])
        if first == "Mediana" or people is None:
            continue
        if first:
            current = first
            out.setdefault(current, {})[""] = people
        elif second == "TOTAL":
            current = ""
            out.setdefault(current, {})[""] = people
        elif second and not (second == UNDER_ONE or BAND.match(second) or OPEN.match(second)
                             or second == UNSTATED):
            if current is None:
                raise SystemExit(f"panama_census: cuadro 20: people {second!r} before any province")
            out[current][second] = people
    return out


def district_table(rows: list[list[Any]], columns: list[int]
                   ) -> tuple[dict[str, list[int]], dict[tuple[str, str], list[int]]]:
    """Province and district rows of a province/district/corregimiento table."""
    provinces: dict[str, list[int]] = {}
    districts: dict[tuple[str, str], list[int]] = {}
    current = None
    for row in rows:
        first, second, third = text(row[0]), text(row[1]), text(row[2])
        figures = [number(row[c]) for c in columns]
        if any(f is None for f in figures):
            continue
        if first and first.upper() != "TOTAL":
            current = first
            provinces[current] = figures
        elif second and not third and current is not None and second.upper() != "TOTAL":
            key = (current, second)
            if key in districts:
                raise SystemExit(f"panama_census: two rows for district {second} of {current}")
            districts[key] = figures
    return provinces, districts


def header_column(rows: list[list[Any]], wanted: str, within: int = 6) -> int:
    for row in rows[:within]:
        for index, cell in enumerate(row):
            if text(cell).startswith(wanted):
                return index
    raise SystemExit(f"panama_census: no header {wanted!r}")


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    admin1 = json.loads((SITE / "admin1" / "PAN.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "PAN.units.json").read_text())
    parents = {u["id"]: u["name"] for u in admin1}
    admin1_ids = {u["name"]: u["id"] for u in admin1}
    tables = {key: rows_of(key) for key in FILES}

    # -- provinces: sex, age and INEC's median
    ages = age_table(tables["age"])
    by_province: dict[str, dict[str, Any]] = {}
    worst = 0.0
    for name, unit in ages.items():
        if unit["men"] + unit["women"] != unit["total"]:
            raise SystemExit(f"panama_census: {name or 'the country'}: men and women do not "
                             "make the total")
        if sum(g[0] for g in unit["groups"].values()) != unit["total"]:
            raise SystemExit(f"panama_census: {name or 'the country'}: age groups make "
                             f"{sum(g[0] for g in unit['groups'].values()):,}, not "
                             f"{unit['total']:,}")
        unit["computed"] = median_of(unit["groups"], name or "the country")
        if unit["median"] is not None and unit["computed"] is not None:
            worst = max(worst, abs(unit["computed"] - unit["median"]))
            if abs(unit["computed"] - unit["median"]) > 2.0:
                raise SystemExit(f"panama_census: {name}: median {unit['computed']} against "
                                 f"INEC's {unit['median']}")
        if name:
            by_province[province_key(name)] = {"name": name, **unit}
    log(f"  cuadro 12: {len(by_province)} provinces and comarcas; medians within "
        f"{worst:.1f} years of INEC's")
    unknown = sorted(set(by_province) - set(PROVINCES))
    if unknown:
        raise SystemExit(f"panama_census: provinces with no map name: {unknown}")

    # -- districts: sex (2023 columns), Afro-descendants, indigenous
    sex_rows = tables["sex"]
    year_col = next(i for row in sex_rows[:5] for i, c in enumerate(row) if number(c) == YEAR)
    sex_prov, sex_dist = district_table(sex_rows, [year_col, year_col + 1, year_col + 2])
    afro_rows = tables["afro"]
    afro_header = next(row for row in afro_rows[:6]
                       if fold(text(row[5] if len(row) > 5 else "")).startswith("afro"))
    afro_cols = []
    for index, (start, label) in zip(range(5, 5 + len(AFRO_COLUMNS)), AFRO_COLUMNS):
        heading = fold(text(afro_header[index]))
        if not heading.startswith(start[:6]):
            raise SystemExit(f"panama_census: cuadro 32 column {index} is {afro_header[index]!r}, "
                             f"expected {label}")
        afro_cols.append(index)
    afro_prov, afro_dist = district_table(afro_rows, [3, 4, *afro_cols])
    for where, figures in [*afro_prov.items(), *afro_dist.items()]:
        if sum(figures[2:]) != figures[1]:
            raise SystemExit(f"panama_census: {where}: Afro-descendant groups make "
                             f"{sum(figures[2:]):,}, not {figures[1]:,}")
    ind_prov, ind_dist = district_table(tables["indigenous"], [3])
    peoples = peoples_table(tables["peoples"])

    # Every table must agree on each province, and its districts must make it.
    for key, unit in by_province.items():
        name = unit["name"]
        checks = {
            "cuadro 11 total": (sex_prov.get(name, [None])[0], unit["total"]),
            "cuadro 32 total": (afro_prov.get(name, [None])[0], unit["total"]),
            "cuadro 33 indigenous": ((ind_prov.get(name) or [None])[0],
                                     (peoples.get(name) or {}).get("")),
        }
        for what, (a, b) in checks.items():
            if a is None or b is None or a != b:
                raise SystemExit(f"panama_census: {name}: {what} {a} against {b}")
        for table, dists, width in (("cuadro 11", sex_dist, 3), ("cuadro 32", afro_dist, 10),
                                    ("cuadro 33", ind_dist, 1)):
            rows = [v for (p, _), v in dists.items() if p == name]
            prov = {"cuadro 11": sex_prov, "cuadro 32": afro_prov, "cuadro 33": ind_prov}[table][name]
            for column in range(width):
                if sum(r[column] for r in rows) != prov[column]:
                    listed = ", ".join(f"{d} {v[column]:,}" for (p, d), v in dists.items()
                                       if p == name)
                    raise SystemExit(f"panama_census: {name}: {table} districts make "
                                     f"{sum(r[column] for r in rows):,}, not {prov[column]:,}, "
                                     f"in column {column}: {listed}")
        people_rows = {k: v for k, v in peoples[name].items() if k}
        if sum(people_rows.values()) != peoples[name][""]:
            raise SystemExit(f"panama_census: {name}: peoples make {sum(people_rows.values()):,}, "
                             f"not {peoples[name]['']:,}")
    log("  every table agrees on every province, and each province's districts make it")

    # -- the districts the boundary file draws, with later splits added back
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for (prov, dist), sex in sex_dist.items():
        pkey = province_key(prov)
        target = SPLITS.get((pkey, fold(dist)))
        name = dist
        if target:
            name = next(d for (p, d) in sex_dist if p == prov and fold(d) == target)
            log(f"  {dist} ({prov}) is added to {name}, which the boundary file draws whole")
        unit = merged.setdefault((prov, name), {"parts": [], "sex": [0, 0, 0],
                                                "afro": [0] * 10, "indigenous": 0})
        unit["parts"].append(dist)
        unit["sex"] = [a + b for a, b in zip(unit["sex"], sex)]
        unit["afro"] = [a + b for a, b in zip(unit["afro"], afro_dist[(prov, dist)])]
        unit["indigenous"] += ind_dist[(prov, dist)][0]

    def ethnicity(indigenous: dict[str, int], afro: list[int], total: int, level: str
                  ) -> dict[str, Any]:
        counts = dict(indigenous)
        for (_, label), count in zip(AFRO_COLUMNS, afro[2:]):
            counts[label] = count
        rest = total - sum(indigenous.values()) - afro[1]
        if rest < 0:
            raise SystemExit("panama_census: indigenous and Afro-descendant people exceed the "
                             "population")
        counts[REST] = rest
        which = ("Which people is published for the province only, so the district's "
                 "indigenous population is one line. " if level == "admin2" else "")
        return {"ethnicity": shares(counts), "ethnicity_year": YEAR,
                "ethnicity_note": (
                    "Two questions the 2023 census asked everyone: whether a person is "
                    "indigenous, and which people; and whether Afro-descendant, and which group. "
                    "Someone may answer yes to both, and INEC publishes no cross of the two, so "
                    "the remainder is the population less both counts. " + which +
                    "The census asks nothing about mestizo or white ancestry.")}

    def sources(level: str) -> list[dict[str, Any]]:
        keys = ["age", "peoples", "afro"] if level == "admin1" else ["sex", "indigenous", "afro"]
        return [{"field": key, "name": SOURCE.format(table=TABLES[key]),
                 "url": BASE + FILES[key].replace(" ", "%20"), "year": YEAR} for key in keys]

    records = []
    for key, unit in sorted(by_province.items()):
        map_name = PROVINCES[key]
        source = SOURCE.format(table=TABLES["age"])
        people = {PEOPLES.get(k, k): v for k, v in peoples[unit["name"]].items() if k}
        records.append(record(
            f"PAN-INEC-{key}", unit["name"], level="admin1", parent="PAN", country="PAN",
            match_by="shape_id", shape_id=admin1_ids[map_name],
            population=measure(unit["total"], year=YEAR, source=source),
            median_age=measure(unit["computed"], unit="years", year=YEAR, source=source),
            median_age_note=("Interpolated within the five-year age group that holds the middle "
                             f"person; INEC's own median is {unit['median']}."),
            sex_ratio=measure(round(1000 * unit["men"] / unit["women"]),
                              unit="males_per_1000_females", year=YEAR, source=source),
            **ethnicity(people, afro_prov[unit["name"]], unit["total"], "admin1"),
            sources=sources("admin1")))

    districts = {f"{province_key(p)}:{fold(d)}": (d, PROVINCES[province_key(p)])
                 for (p, d) in merged}
    bound, missing = binding.bind(districts, admin2, parents, ALIASES)
    log(f"  {len(bound)} of {len(districts)} districts bound; not: {missing}")
    drawn = {s["id"]: s for s in admin2}
    unbound = sorted(s["name"] for s in admin2 if s["id"] not in set(bound.values()))
    log(f"  polygons with no district: {unbound}")
    for (prov, dist), unit in sorted(merged.items()):
        code = f"{province_key(prov)}:{fold(dist)}"
        if code not in bound:
            continue
        total, men, women = unit["sex"]
        was = (drawn[bound[code]].get("population") or {}).get("value")
        if was and not 0.5 <= total / was <= 2.0:
            log(f"  check: {dist} has {total:,} people; its polygon carried {was:,}")
        source = SOURCE.format(table=TABLES["sex"])
        parts = unit["parts"]
        records.append(record(
            f"PAN-INEC-{code.replace(':', '-')}", dist, level="admin2", parent="PAN", country="PAN",
            parent_name=PROVINCES[province_key(prov)], match_by="shape_id",
            shape_id=bound[code],
            population=measure(total, year=YEAR, source=source,
                               note=(f"Includes {', '.join(p for p in parts if p != dist)}, "
                                     "created from it since the boundary file was drawn."
                                     if len(parts) > 1 else None)),
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=YEAR, source=source),
            **ethnicity({INDIGENOUS_DISTRICT: unit["indigenous"]}, unit["afro"], total, "admin2"),
            sources=sources("admin2")))
    log(f"  {len(by_province)} provinces and comarcas, "
        f"{sum(1 for r in records if r['level'] == 'admin2')} districts")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
