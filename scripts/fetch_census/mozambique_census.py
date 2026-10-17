#!/usr/bin/env python3
"""Mozambique -- the 2017 census (IV RGPH) by district and province.

INE published the census's tables as one workbook a table, for each province
and for the country, on its former site (www.ine.gov.mz/iv-rgph-2017/). That
site is gone and its new one does not answer the runner, so the workbooks are
read from the Internet Archive's copies of the same addresses. Three tables
of every province are read, and one of the country:

    Quadro 3   population by five-year age group, district and sex (each
               province's; the country's is by province)
    Quadro 11  population by religion, area of residence, age and sex
    Quadro 22  population aged 5 and over by mother tongue, age and sex

Written: for the districts and cities the map draws, the census's count, the
sex ratio (men per thousand women) and the median age, interpolated within the
age group that holds the middle person; for the provinces the same, with
religion and mother tongue as counts. A district's religion, language and
ethnicity are empty with their reasons: INE publishes religion and mother
tongue by province, and no ethnic group at all. Zambezia's Quadro 3 was never
archived, so its districts carry no census figure here; the province's own
figures come from the country's Quadro 3.

**The units.** The map draws Maputo City and Maputo Province as one first-level
unit, Maputo: its figures are the two added together. A province's Quadro 3
lists its cities ("CIDADE DE PEMBA") and districts ("DISTRITO DE ANCUABE");
each is matched to the polygon of its name within its province, a city also
under its bare name (Maxixe, Nacala). Where one polygon takes both a district
and a city of its name, it gets the two added together and says so. Maputo
City's seven municipal districts are one polygon, Cidade De Maputo, and get
the city's total.

**Checks before anything is written.** Every unit's men and women make its
total, its age groups make it too, and its population of 15 and over is its
age groups from 15; a province's districts and cities make its total, which
is the country's Quadro 3 line for it. A Quadro 11 line's religions and its
unknown make its total, and its total is the province's; a Quadro 22 line's
languages make its total, which is the province's people aged 5 and over.
Every polygon of a province with a Quadro 3 gets one unit or more, and every
unit a polygon.

Usage:
    python -m scripts.fetch_census.mozambique_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .southern_africa_common import fetch, grouped_median, joined, key, sex_ratio, units

BASE = "http://www.ine.gov.mz/iv-rgph-2017/"
SOURCE = "INE Moçambique, IV Recenseamento Geral da População e Habitação 2017"
LICENCE = "Instituto Nacional de Estatística de Moçambique publication (reuse with attribution)"
YEAR = 2017
NATIONAL = 26_899_105
OUT = "mozambique_census.json"

# Each province: its line in the country's Quadro 3, the map's first-level
# unit, and its own tables as (address, Internet Archive capture).
PROVINCES: dict[str, dict[str, Any]] = {
    "NIASSA": {"map": "Niassa",
               "q3": ("niassa/quadro-3-populacao-por-idade-segundo-area-de-residencia-distrito-e-sexo"
                      "-provincia-de-niassa-2017.xlsx", "20191220233923"),
               "q11": ("niassa/quadro-11-populacao-por-religiao-segundo-area-de-residencia-idade-e"
                       "-sexo-provincia-do-niassa-2017.xlsx", "20191114002733"),
               "q22": ("niassa/quadro-22-populacao-de-5-anos-e-mais-por-idade-segundo-area-de"
                       "-residencia-sexo-e-lingua-materna-provincia-do-niassa-2017.xlsx",
                       "20191220234322")},
    "CABO DELGADO": {"map": "Cabo Delgado",
                     "q3": ("cabo-delgado/quadro-3-populacao-por-idade-segundo-area-de-residencia"
                            "-distrito-e-sexo-provincia-de-cabo-delgado-2017.xlsx", "20191114004502"),
                     "q11": ("cabo-delgado/quadro-11-populacao-por-religiao-segundo-area-de"
                             "-residencia-idade-e-sexo-provincia-de-cabo-delgado-2017.xlsx",
                             "20191114004834"),
                     "q22": ("cabo-delgado/quadro-22-populacao-de-5-anos-e-mais-por-idade-segundo"
                             "-area-de-residencia-sexo-e-lingua-materna-provincia-de-cabo-delgado"
                             "-2017.xlsx", "20191114005018")},
    "NAMPULA": {"map": "Nampula",
                "q3": ("nampula/quadro-3-populacao-por-idade-segundo-area-de-residencia-distrito-e"
                       "-sexo-provincia-de-nampula-2017.xlsx", "20191114010934"),
                "q11": ("nampula/quadro-11-populacao-por-religiao-segundo-area-de-residencia-idade"
                        "-e-sexo-provincia-de-nampula-2017.xlsx", "20191114011052"),
                "q22": ("nampula/quadro-22-populacao-de-5-anos-e-mais-por-idade-segundo-area-de"
                        "-residencia-sexo-e-lingua-materna-provincia-de-nampula-2017.xlsx",
                        "20191114013404")},
    "ZAMBÉZIA": {"map": "Zambézia",
                 "q3": None,
                 "q11": ("zambezia/quadro-11-populacao-por-religiao-segundo-area-de-residencia"
                         "-idade-e-sexo-provincia-de-zambezia-2017.xlsx", "20191114013455"),
                 "q22": ("zambezia/quadro-22-populacao-de-5-anos-e-mais-por-idade-segundo-area-de"
                         "-residencia-sexo-e-lingua-materna-provincia-de-zambezia-2017.xlsx",
                         "20191114013816")},
    "TETE": {"map": "Tete",
             "q3": ("tete/quadro-3-populacao-por-idade-segundo-area-de-residencia-distrito-e-sexo"
                    "-provincia-de-tete-2017.xlsx", "20191114015524"),
             "q11": ("tete/quadro-11-populacao-por-religiao-segundo-area-de-residencia-idade-e"
                     "-sexo-provincia-de-tete-2017.xlsx", "20191114015723"),
             "q22": ("tete/quadro-22-populacao-de-5-anos-e-mais-por-idade-segundo-area-de"
                     "-residencia-sexo-e-lingua-materna-tete-2017.xlsx", "20191114015921")},
    "MANICA": {"map": "Manica",
               "q3": ("manica/quadro-3-populacao-por-idade-segundo-area-de-residencia-distrito-e"
                      "-sexo-provincia-de-manica-2017.xlsx", "20191114023411"),
               "q11": ("manica/quadro-11-populacao-por-religiao-segundo-area-de-residencia-idade"
                       "-e-sexo-provincia-de-manica-2017.xlsx", "20191114023623"),
               "q22": ("manica/quadro-22-populacao-de-5-anos-e-mais-por-idade-segundo-area-de"
                       "-residencia-sexo-e-lingua-materna-provincia-de-manica-2017.xlsx",
                       "20191114024417")},
    "SOFALA": {"map": "Sofala",
               "q3": ("sofala/quadro-3-populacao-por-idade-segundo-distrito-area-de-residencia-e"
                      "-sexo-provincia-de-sofala-2017.xlsx", "20191114025715"),
               "q11": ("sofala/quadro-11-populacao-por-religiao-segundo-area-de-residencia-idade"
                       "-e-sexo-provincia-de-sofala-2017.xlsx", "20191114025815"),
               "q22": ("sofala/quadro-22-populacao-de-5-anos-e-mais-por-idade-segundo-area-de"
                       "-residencia-sexo-e-lingua-materna.xlsx", "20191114030145")},
    "INHAMBANE": {"map": "Inhambane",
                  "q3": ("inhambane/quadro-3-populacao-por-idade-segundo-area-de-residencia"
                         "-distrito-e-sexo-provincia-de-inhambane-2017.xlsx", "20191114031532"),
                  "q11": ("inhambane/quadro-11-populacao-por-religiao-segundo-area-de-residencia"
                          "-idade-e-sexo-provincia-de-inhambane-2017.xlsx", "20191114031616"),
                  "q22": ("inhambane/quadro-22-populacao-de-5-anos-e-mais-por-idade-segundo-area"
                          "-de-residencia-sexo-e-lingua-materna-provincia-de-inhambane-2017.xlsx",
                          "20191114032438")},
    "GAZA": {"map": "Gaza",
             "q3": ("gaza/quadro-3-populacao-por-idade-segundo-area-de-residencia-distrito-e-se"
                    ".xlsx", "20200101130915"),
             "q11": ("gaza/quadro-11-populacao-por-religiao-segundo-area-de-residencia-idade-e-s"
                     ".xlsx", "20191114035423"),
             "q22": ("gaza/quadro-22-populacao-de-5-anos-e-mais-por-idade-segundo-area-de"
                     "-residencia-sexo-e-lingua-materna-provincia-gaza-2017.xlsx",
                     "20191114042343")},
    "MAPUTO PROVÍNCIA": {"map": "Maputo",
                         "q3": ("maputo-provincia/quadro-3-populacao-por-idade-segundo-distrito"
                                "-area-de-residencia-e-sexo-maputo-provincia-2017.xlsx",
                                "20191015090808"),
                         "q11": ("maputo-provincia/quadro-11-populacao-por-religiao-segundo-area"
                                 "-de-residencia-idade-e-sexo-maputo-provincia-2017.xlsx",
                                 "20191114043021"),
                         "q22": ("maputo-provincia/quadro-22-populacao-de-5-anos-e-mais-por"
                                 "-idade-segundo-area-de-residencia-sexo-e-lingua-materna-maputo"
                                 "-provincia-2017.xlsx", "20191114045042")},
    "MAPUTO CIDADE": {"map": "Maputo",
                      "q3": ("maputo-cidade/quadro-3-populacao-por-idade-segundo-distrito-e-sexo"
                             "-maputo-cidade-2017.xlsx", "20200101134750"),
                      "q11": ("maputo-cidade/quadro-11-populacao-por-religiao-segundo-idade-e"
                              "-sexo-maputo-cidade-2017.xlsx", "20191114050516"),
                      "q22": ("maputo-cidade/quadro-22-populacao-de-5-anos-e-mais-por-idade"
                              "-segundo-sexo-e-lingua-materna-maputo-cidade-2017.xlsx",
                              "20191114050625")},
}
NATIONAL_Q3 = ("mocambique/populacao/quadro-3-populacao-por-idade-segundo-provincia-area-de"
               "-residencia-e-sexo-mocambique-2017.xlsx", "20200101164030")
# Maputo City is one polygon on the map, which takes the city's whole count.
MAPUTO_CITY = ("MAPUTO CIDADE", "cidadedemaputo")

# Quadro 11's column heads, matched on a part of their reduced text.
RELIGIONS = (("catolic", "Catholic"), ("anglican", "Anglican"), ("islam", "Islam"),
             ("zion", "Zionist churches"), ("evangel", "Evangelical/Pentecostal"),
             ("semreligi", "No religion"), ("outra", "Other religion"))
# Quadro 22's rows, under the names the map's legend knows; the mute and the
# unknown are counted in the total and left out of the shares.
LANGUAGES = {
    "portugues": "Portuguese", "emakhuwa": "Makhuwa", "xichangana": "Changana",
    "cisena": "Sena", "elomwe": "Lomwe", "echuwabo": "Chuwabo", "cinhanja": "Nyanja",
    "cinyanja": "Nyanja", "cindau": "Ndau", "xitswa": "Tswa", "ciyao": "Yao",
    "gitonga": "Gitonga", "cicopi": "Chopi", "xirhonga": "Ronga", "xironga": "Ronga",
    "shimakonde": "Makonde", "kimwani": "Mwani", "ciswahili": "Swahili",
    "kiswahili": "Swahili", "cinyungwe": "Nyungwe", "citewe": "Tewe", "cimanyika": "Manyika",
    "ekoti": "Koti", "emeetto": "Meetto", "echirima": "Chirima", "ecirima": "Chirima",
    "cibarwe": "Barwe", "cinsenga": "Nsenga", "cikunda": "Kunda", "cibalke": "Balke",
    "isizulu": "Zulu", "cizulu": "Zulu", "xiswati": "Swati", "siswati": "Swati",
    "ingles": "English",
}
UNSTATED_LANGUAGES = ("mudo", "desconhecid", "naosabe", "nenhum")

RELIGION_NOTE = ("INE publishes the 2017 census's religion for each province (Quadro 11 of the "
                 "province's census tables), not for its districts.")
LANGUAGE_NOTE = ("INE publishes the 2017 census's mother tongue and home language for each "
                 "province (Quadros 22 and 23 of the province's census tables), not for its "
                 "districts.")
ETHNICITY_NOTE = ("INE's tables of the 2017 census record religion, mother tongue and the "
                  "language spoken at home, and no ethnic group.")
LANGUAGE_BASIS = "mother tongue, population aged 5 and over"


def url_of(path: str) -> str:
    return BASE + path


def cell(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = " ".join(value.split())
        if re.fullmatch(r"\d+", text):
            return int(text)
        return text
    return value


def sheet_rows(blob: bytes) -> list[list[Any]]:
    import openpyxl                                 # noqa: PLC0415
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    return [[cell(v) for v in row] for row in wb.worksheets[0].iter_rows(values_only=True)]


def label(row: list[Any]) -> str:
    return row[0] if row and isinstance(row[0], str) else ""


AGE_HEAD = re.compile(r"^(?:(?P<lo>\d+)\s*-\s*(?P<hi>\d+)|(?P<top>\d+)\s*e\s*\+|(?P<one>\d+))$")


def age_columns(rows: list[list[Any]]) -> dict[int, tuple[int, int | None]]:
    """{column: (lower age, width)} from the head row that lists the age groups."""
    for row in rows[:12]:
        found: dict[int, tuple[int, int | None]] = {}
        for i, v in enumerate(row):
            hit = AGE_HEAD.match(str(v).strip()) if isinstance(v, str) else None
            if not hit:
                continue
            if hit.group("top"):
                found[i] = (int(hit.group("top")), None)
            elif hit.group("lo"):
                found[i] = (int(hit.group("lo")), int(hit.group("hi")) - int(hit.group("lo")) + 1)
            else:
                found[i] = (int(hit.group("one")), 1)
        if len(found) >= 15:
            # A head of "0" may be stored as the number 0.
            for i, v in enumerate(row):
                if v == 0 and not isinstance(v, bool) and i not in found and i < min(found):
                    found[i] = (0, 1)
            return found
    raise SystemExit("mozambique_census: no head row of age groups")


def is_unit(name: str) -> bool:
    return bool(re.match(r"(?i)^(cidade|distrito)\b", name))


def is_total(name: str) -> bool:
    return key(name) == "total"


def read_q3(rows: list[list[Any]], *, by: str) -> dict[str, dict[str, Any]]:
    """{unit label: {"total", "men", "women", "adults", "ages"}}: the T O T A L
    block under "TOTAL" and every unit under its own label. ``by`` is
    "unit" for a province's table (cities and districts) or "province" for the
    country's (its lines are the provinces, written in capitals)."""
    cols = age_columns(rows)
    out: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    for row in rows:
        name = label(row)
        nums = row[1:3]
        if not name or len(nums) < 2 or not all(isinstance(n, int) for n in nums):
            continue
        k = key(name)
        if k in ("homens", "mulheres"):
            if current is not None and k not in current:
                current[k] = row[1]
            continue
        wanted = (is_total(name) or is_unit(name)) if by == "unit" else \
            (is_total(name) or (name.upper() == name and k not in ("urbana", "rural")))
        if not wanted:
            current = None
            continue
        ages = [(lo, width, row[i]) for i, (lo, width) in sorted(cols.items())
                if i < len(row) and isinstance(row[i], int)]
        current = {"total": row[1], "adults": row[2], "ages": ages}
        out.setdefault("TOTAL" if is_total(name) else name, current)
    for name, u in out.items():
        men, women = u.pop("homens", None), u.pop("mulheres", None)
        if men is None or women is None or men + women != u["total"]:
            raise SystemExit(f"mozambique_census: Quadro 3 {name}: {men} men and {women} women "
                             f"against {u['total']:,}")
        u["men"], u["women"] = men, women
        made = sum(n for _, _, n in u["ages"])
        adults = sum(n for lo, _, n in u["ages"] if lo >= 15)
        if made != u["total"] or adults != u["adults"] or len(u["ages"]) != len(cols):
            raise SystemExit(f"mozambique_census: Quadro 3 {name}: age groups make {made:,} "
                             f"({adults:,} aged 15 and over) against {u['total']:,} "
                             f"({u['adults']:,})")
    return out


def check_province(name: str, table: dict[str, dict[str, Any]],
                   national: dict[str, Any]) -> None:
    units_ = [u for n, u in table.items() if n != "TOTAL"]
    total = table.get("TOTAL")
    if not total or not units_:
        raise SystemExit(f"mozambique_census: Quadro 3 of {name} has no total or no units")
    for field in ("total", "men", "women"):
        made = sum(u[field] for u in units_)
        if made != total[field] or total[field] != national[field]:
            raise SystemExit(f"mozambique_census: {name}'s units make {made:,} {field}, its "
                             f"total line {total[field]:,}, the country's table "
                             f"{national[field]:,}")


def header_texts(rows: list[list[Any]], stop: int) -> dict[int, str]:
    """Each column's head, its texts in the rows above ``stop`` joined."""
    heads: dict[int, list[str]] = {}
    for row in rows[1:stop]:
        for i, v in enumerate(row):
            if i and isinstance(v, str) and v.strip():
                heads.setdefault(i, []).append(v)
    return {i: " ".join(parts) for i, parts in heads.items()}


def read_q11(rows: list[list[Any]]) -> dict[str, int]:
    """{religion: count, "TOTAL": n, "UNKNOWN": n} from the first TOTAL line."""
    first = next((i for i, row in enumerate(rows) if is_total(label(row))
                  and isinstance(row[1] if len(row) > 1 else None, int)), None)
    if first is None:
        raise SystemExit("mozambique_census: Quadro 11 has no TOTAL line")
    heads = header_texts(rows, first)
    row = rows[first]
    out: dict[str, int] = {"TOTAL": row[1]}
    for i, text in heads.items():
        k = key(text)
        if i >= len(row) or not isinstance(row[i], int) or i == 1:
            continue
        if "desconhec" in k:
            out["UNKNOWN"] = row[i]
            continue
        for part, name in RELIGIONS:
            if part in k:
                out[name] = out.get(name, 0) + row[i]
                break
    named = sum(v for g, v in out.items() if g not in ("TOTAL", "UNKNOWN"))
    if "UNKNOWN" not in out or named + out["UNKNOWN"] != out["TOTAL"]:
        raise SystemExit(f"mozambique_census: Quadro 11's religions make {named:,} and "
                         f"{out.get('UNKNOWN')} unknown against {out['TOTAL']:,} "
                         f"(heads {list(heads.values())})")
    return out


def read_q22(rows: list[list[Any]]) -> dict[str, int]:
    """{language: count, "TOTAL": n, "UNSTATED": n} from the first block, the
    TOTAL line and the languages under it."""
    out: dict[str, int] = {}
    started = False
    for row in rows:
        name = label(row)
        value = row[1] if len(row) > 1 else None
        if not started:
            if is_total(name) and isinstance(value, int):
                out["TOTAL"], out["UNSTATED"] = value, 0
                started = True
            continue
        k = key(name)
        if not name or k in ("homens", "mulheres", "urbana", "rural", "total") or \
                not isinstance(value, int):
            break
        if any(k.startswith(u) for u in UNSTATED_LANGUAGES):
            out["UNSTATED"] += value
            continue
        if k.startswith("outraslinguasmoc"):
            group = "Other Mozambican languages"
        elif k.startswith("outraslinguasest"):
            group = "Other foreign languages"
        else:
            group = LANGUAGES.get(k)
            if group is None:
                group = name.title()
                log(f"    a language kept as printed: {name!r}")
        out[group] = out.get(group, 0) + value
    if not started:
        raise SystemExit("mozambique_census: Quadro 22 has no TOTAL line")
    made = sum(v for g, v in out.items() if g != "TOTAL")
    if made != out["TOTAL"]:
        raise SystemExit(f"mozambique_census: Quadro 22's languages make {made:,} against "
                         f"{out['TOTAL']:,}")
    return out


def candidates(name: str) -> list[str]:
    """The keys a census unit may be drawn under: a district by its name, a
    city by its full name and its bare one."""
    bare = re.sub(r"(?i)^(cidade|distrito)(\s+municipal)?\s+(de|da|do|das|dos)?\s*", "", name)
    if re.match(r"(?i)^cidade\b", name):
        return [key(name), key(bare)]
    return [key(bare)]


def bind(table: dict[str, dict[str, Any]], shapes: list[dict[str, Any]], province: str
         ) -> dict[str, list[str]]:
    """{polygon id: [census labels]} within one province, by name."""
    names = [n for n in table if n != "TOTAL"]
    by_key = {key(s["name"]): s for s in shapes}
    out: dict[str, list[str]] = {}
    left: list[str] = []
    for name in names:
        hit = next((by_key[c] for c in candidates(name) if c in by_key), None)
        if hit is None:
            left.append(name)
            continue
        out.setdefault(hit["id"], []).append(name)
    if left:
        raise SystemExit(f"mozambique_census: {province}: no polygon for {left}; the map draws "
                         f"{sorted(s['name'] for s in shapes)}")
    return out


def summed(table: dict[str, dict[str, Any]], names: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {f: sum(table[n][f] for n in names) for f in ("total", "men", "women")}
    ages: dict[tuple[int, int | None], int] = {}
    for n in names:
        for lo, width, count in table[n]["ages"]:
            ages[(lo, width)] = ages.get((lo, width), 0) + count
    out["ages"] = [(lo, width, count) for (lo, width), count in ages.items()]
    return out


def place(name: str) -> str:
    """'DISTRITO DE ANCUABE' -> 'the district of Ancuabe'."""
    bare = re.sub(r"(?i)^(cidade|distrito)(\s+municipal)?\s+(de|da|do|das|dos)?\s*", "", name)
    kind = "city" if re.match(r"(?i)^cidade\b", name) else "district"
    return f"the {kind} of {bare.title()}"


def age_fields(data: dict[str, Any], table_no: str) -> dict[str, Any]:
    return {"sex_ratio": sex_ratio(data["men"], data["women"], year=YEAR, source=f"{SOURCE}, "
                                   f"{table_no}"),
            "median_age": measure(grouped_median(data["ages"]), year=YEAR,
                                  source=f"{SOURCE}, {table_no}"),
            "median_age_note": ("Interpolated within the age group that holds the middle "
                                "person, from the 2017 census's counts by age group "
                                f"({table_no}).")}


def build(tables: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    shape_of = {key(s["name"]): s for s in admin1}
    gaps = {"religion": gap(NOT_AVAILABLE, RELIGION_NOTE),
            "language": gap(NOT_AVAILABLE, LANGUAGE_NOTE),
            "ethnicity": gap(NOT_AVAILABLE, ETHNICITY_NOTE)}
    for prov, spec in PROVINCES.items():
        q3 = tables["q3"].get(prov)
        if q3 is None:
            continue
        district_sources = [
            {"field": "population/sex_ratio/median_age",
             "name": f"{SOURCE}, Quadro 3 ({prov.title()})", "url": url_of(spec["q3"][0]),
             "license": LICENCE, "year": YEAR},
            {"field": "religion/language note",
             "name": f"{SOURCE}, Quadros 11 and 22 ({prov.title()})",
             "url": url_of(spec["q11"][0]), "license": LICENCE, "year": YEAR}]
        parent = shape_of.get(key(spec["map"]))
        if parent is None:
            raise SystemExit(f"mozambique_census: the map draws no province {spec['map']!r}")
        shapes = [s for s in admin2 if s.get("parent") == parent["id"]]
        if prov == MAPUTO_CITY[0]:
            city = [s for s in shapes if key(s["name"]) == MAPUTO_CITY[1]]
            if len(city) != 1:
                raise SystemExit("mozambique_census: the map draws no Cidade De Maputo")
            groups = {city[0]["id"]: ["TOTAL"]}
            notes = {city[0]["id"]: "The 2017 census's count for Maputo City, all seven of its "
                                    "municipal districts."}
        else:
            others = [s for s in shapes if key(s["name"]) != MAPUTO_CITY[1]]
            groups = bind(q3, others, prov)
            notes = {}
            for sid, names in groups.items():
                if len(names) == 1:
                    notes[sid] = f"The 2017 census's count for {place(names[0])}."
                else:
                    notes[sid] = (f"The 2017 census's counts for "
                                  f"{joined([place(n) for n in names])} added together: the "
                                  f"map draws them as one.")
        for shape in shapes:
            if shape["id"] not in groups:
                continue
            data = summed(q3, groups[shape["id"]])
            out.append(record(f"MOZ-2017-{key(prov)}-{key(shape['name'])}", shape["name"],
                              level="admin2", parent="MOZ", country="MOZ",
                              match_by="shape_id", shape_id=shape["id"],
                              sources=district_sources,
                              population=measure(data["total"], year=YEAR,
                                                 source=f"{SOURCE}, Quadro 3"),
                              population_note=notes[shape["id"]],
                              **age_fields(data, "Quadro 3"), **gaps))
    national = tables["national"]
    for shape in admin1:
        provs = [p for p, spec in PROVINCES.items() if key(spec["map"]) == key(shape["name"])]
        if not provs:
            raise SystemExit(f"mozambique_census: no census province for {shape['name']!r}")
        data = summed(national, provs)
        religion = {g: sum(tables["q11"][p].get(g, 0) for p in provs)
                    for p0 in provs for g in tables["q11"][p0]}
        language = {g: sum(tables["q22"][p].get(g, 0) for p in provs)
                    for p0 in provs for g in tables["q22"][p0]}
        stated_rel = religion["TOTAL"] - religion["UNKNOWN"]
        stated_lang = language["TOTAL"] - language["UNSTATED"]
        both = len(provs) > 1
        note = (f"The 2017 census's counts for Maputo Province and Maputo City added together: "
                f"the map draws them as one." if both else
                f"The 2017 census's count for the province of {shape['name']}.")
        src = [{"field": "population/sex_ratio/median_age",
                "name": f"{SOURCE}, Quadro 3 (Moçambique)", "url": url_of(NATIONAL_Q3[0]),
                "license": LICENCE, "year": YEAR}] + [
               {"field": field, "name": f"{SOURCE}, {q} ({PROVINCES[p]['map'] if not both else p.title()})",
                "url": url_of(PROVINCES[p][qk][0]), "license": LICENCE, "year": YEAR}
               for p in provs for field, q, qk in (("religion", "Quadro 11", "q11"),
                                                   ("language", "Quadro 22", "q22"))]
        out.append(record(
            f"MOZ-2017-province-{key(shape['name'])}", shape["name"], level="admin1",
            parent="MOZ", country="MOZ", match_by="shape_id", shape_id=shape["id"], sources=src,
            population=measure(data["total"], year=YEAR, source=f"{SOURCE}, Quadro 3"),
            population_note=note, **age_fields(data, "Quadro 3"),
            religion=shares({g: v for g, v in religion.items()
                             if g not in ("TOTAL", "UNKNOWN") and v}, total=stated_rel),
            religion_year=YEAR,
            religion_note=(f"Religion of the {stated_rel:,} people whose religion the 2017 "
                           f"census recorded, of {religion['TOTAL']:,} (Quadro 11)."),
            language=shares({g: v for g, v in language.items()
                             if g not in ("TOTAL", "UNSTATED") and v}, total=stated_lang),
            language_year=YEAR, language_basis=LANGUAGE_BASIS,
            language_note=(f"Mother tongue of the {stated_lang:,} people aged 5 and over whose "
                           f"mother tongue the 2017 census recorded, of {language['TOTAL']:,} "
                           f"aged 5 and over; the mute and those whose mother tongue is "
                           f"unknown are left out, and children under 5 are not asked "
                           f"(Quadro 22)."),
            ethnicity=gap(NOT_AVAILABLE, ETHNICITY_NOTE)))
    return out


def read(path_stamp: tuple[str, str]) -> list[list[Any]]:
    path, stamp = path_stamp
    blob, where = fetch(url_of(path), archive=(stamp, "2019", "2020"), office=False,
                        expect=b"PK")
    log(f"  read {where}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    return sheet_rows(blob)


def parse_all(reader=read) -> dict[str, Any]:
    national = read_q3(reader(NATIONAL_Q3), by="province")
    if national.get("TOTAL", {}).get("total") != NATIONAL:
        raise SystemExit(f"mozambique_census: the country's Quadro 3 gives "
                         f"{national.get('TOTAL', {}).get('total')}, not {NATIONAL:,}")
    provinces = {n: u for n, u in national.items() if n != "TOTAL"}
    if sorted(provinces) != sorted(PROVINCES):
        raise SystemExit(f"mozambique_census: the country's Quadro 3 lists {sorted(provinces)}")
    for field in ("total", "men", "women"):
        if sum(u[field] for u in provinces.values()) != national["TOTAL"][field]:
            raise SystemExit(f"mozambique_census: the provinces do not make the country's {field}")
    tables: dict[str, Any] = {"national": provinces, "q3": {}, "q11": {}, "q22": {}}
    for prov, spec in PROVINCES.items():
        if spec["q3"]:
            q3 = read_q3(reader(spec["q3"]), by="unit")
            check_province(prov, q3, provinces[prov])
            tables["q3"][prov] = q3
        q11 = read_q11(reader(spec["q11"]))
        if q11["TOTAL"] != provinces[prov]["total"]:
            raise SystemExit(f"mozambique_census: {prov}'s Quadro 11 counts {q11['TOTAL']:,}, "
                             f"not {provinces[prov]['total']:,}")
        tables["q11"][prov] = q11
        q22 = read_q22(reader(spec["q22"]))
        five_up = provinces[prov]["total"] - sum(n for lo, _, n in provinces[prov]["ages"] if lo < 5)
        if q22["TOTAL"] != five_up:
            raise SystemExit(f"mozambique_census: {prov}'s Quadro 22 counts {q22['TOTAL']:,} "
                             f"aged 5 and over, not {five_up:,}")
        tables["q22"][prov] = q22
    return tables


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    tables = parse_all()
    records = build(tables, units("MOZ", "admin1"), units("MOZ", "admin2"))
    for r in records:
        top = [(g["group"], g["pct"]) for g in r["religion"][:2]] \
            if isinstance(r["religion"], list) else ""
        log(f"  {r['level']} {r['name']}: {r['population'].get('value')}, ratio "
            f"{r['sex_ratio'].get('value')}, median {r['median_age'].get('value')} {top}; "
            f"{r.get('population_note', '')}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
