#!/usr/bin/env python3
"""Venezuela's 2011 census by state and municipio, tabulated on INE's REDATAM base CPV2011.

INE Venezuela publishes the XIV Censo Nacional de Población y Vivienda 2011
for on-line tabulation as the REDATAM base CPV2011
(redatam.ine.gob.ve/Censo2011), and its processor runs a Redatam+SP program
sent to it. This sends four questions, each a frequency table broken by
municipio, and reads them back:

* SEXO and EDAD, everyone by sex and single year of age: the population,
  the sex ratio, and the median age, interpolated within the single year
  holding the middle person.
* CUALINDIGE, the indigenous people each person belongs to, asked of
  everyone ("¿Pertenece a algún pueblo indígena?", then which), and
  USTEDSEREC, how everyone else sees themselves: negra/negro,
  afrodescendiente, morena/moreno, blanca/blanco or otra. No one who named an
  indigenous people answered the second (a national cross of the two has no
  indigenous row), so together they partition the population, and whoever
  answered neither is one line, "Not stated". The peoples are named as INE's
  own table by state names them, several spellings under one name (Wayuu and
  Guajiro, the Pemón's three peoples), and the states' sums must equal that
  published table people by people.

"Morena/moreno" in Venezuela is the brown, mixed majority -- 51.6% of the
country -- which the Factbook reports as "unspecified Mestizo". It is written
"Moreno (Venezuela)" so it is not read as Panama's Afro-descendant moreno;
its place in the group tree is proposed beside Pardo and Mestizo.

Municipios whose names changed since the boundary file was drawn are bound
by ALIASES (Tinaquillo was Falcón, Angostura was Raúl Leoni, Guajira was
Páez, and so on). Ocumare de la Costa de Oro is not drawn apart: its
territory lies inside the polygon drawn as Mario Briceño Iragorry, so the two
are summed and the note says so. The Zona en Reclamación is not enumerated
by the census and carries that reason. The Dependencias Federales have no
municipio polygon.

Population is written for the municipios (the map's are the same 2011
count); the states keep their newer figures.

Usage:
    python -m scripts.fetch_census.venezuela_redatam --probe munic
    python -m scripts.fetch_census.venezuela_redatam
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from typing import Any

from scripts.probe_redatam import Session, report

from . import venezuela_census
from ._shared import PROCESSED, gap, http_get, log, measure, record, shares, write_json
from .binding import bind, fold
from .redatam import Server, median_age, tables

PORTAL = ("http://redatam.ine.gob.ve/vencgibin/RpWebEngine.exe/PortalAction?&MODE=MAIN"
          "&BASE=CPV2011&MAIN=WebServerMain.inl")
CMDSET = "http://redatam.ine.gob.ve/vencgibin/RpWebEngine.exe/CmdSet"
PAGE = "http://redatam.ine.gob.ve/Censo2011/index.html"
BASE = "CPV2011"
OUT = PROCESSED / "venezuela_redatam.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2011
NATIONAL = 27_227_930
SOURCE = ("INE Venezuela, XIV Censo Nacional de Población y Vivienda 2011, tabulated on "
          "INE's REDATAM base CPV2011")
QUESTIONS = {"sex": "SEXO", "age": "EDAD", "peoples": "CUALINDIGE", "identity": "USTEDSEREC"}
# The processor prints those a question was not put to, and those it was put
# to who gave no answer, as rows of their own after the Total.
NOT_ASKED = re.compile(r"^(?:NSA|Ignorado)\b")
SEXES = {"hombre": "men", "mujer": "women"}
IDENTITY = {"Negra / Negro": "Black", "Afrodescendiente": "Afro-descendant",
            "Morena / Moreno": "Moreno (Venezuela)", "Blanca / Blanco": "White",
            "Otra": "Other"}
NOT_STATED = "Not stated"
# CUALINDIGE's categories -> the names INE's table by state gives them
# (venezuela_census.py writes that table): several spellings of one people
# are one name there, and are one here.
PEOPLES = {
    "Añú": "Añú (Paraujano)", "Paraujano": "Añú (Paraujano)",
    "Akawayo": "Akawayo", "Kapón": "Akawayo", "Baniva": "Baniva", "Baré": "Baré",
    "Barí": "Barí (Venezuela)", "Chaima": "Chaima",
    "Eñepa": "E'ñepá (Panare)", "Panare": "E'ñepá (Panare)",
    "Guajibo": "Jivi (Guajibo)", "Amorúa": "Jivi (Guajibo)", "Sikwani": "Jivi (Guajibo)",
    "Jiwi": "Jivi (Guajibo)", "Hoti": "Jodi", "Jodi": "Jodi", "Kariña": "Kariña",
    "Mapoyo": "Mapoyo (Wanai)", "Wanai": "Mapoyo (Wanai)",
    "Ñengatú": "Yeral (Ñengatú)", "Yeral": "Yeral (Ñengatú)",
    "Pemón": "Pemón", "Arekuna": "Pemón", "Kamarakoto": "Pemón", "Taurepán": "Pemón",
    "Chase": "Piapoco", "Piapoko": "Piapoco", "Piaroa": "Piaroa", "Wótüja": "Piaroa",
    "Mako": "Mako", "Puinave": "Puinave", "Pumé": "Pumé (Yaruro)", "Yaruro": "Pumé (Yaruro)",
    "Kuiva": "Kuiva", "Cuiba": "Kuiva", "Sanema": "Sanemá", "Sanüma": "Sanemá", "Sapé": "Sapé",
    "Arutani": "Arutani (Uruak)", "Uruak": "Arutani (Uruak)", "Warao": "Warao",
    "Warekena": "Warekena", "Guajiro": "Wayuu", "Wayuu": "Wayuu",
    "Yanomami": "Yanomami", "Shiriana": "Yanomami", "Yavarana": "Yavarana",
    "Makiritare": "Ye'kwana", "Yekwana": "Ye'kwana", "Yukpa": "Yukpa",
    "Japreria": "Japreria", "Kubeo": "Kubeo", "Guanano": "Guanano", "Makushi": "Makushi",
    "Matako": "Matako", "Tukano": "Tukano", "Wapishana": "Wapishana",
    "Curripaco": "Kurripako", "Kurripako": "Kurripako", "Sáliva": "Sáliva",
    "Guaiquerí": "Waikerí", "Waikerí": "Waikerí", "Caquetío": "Kaketío", "Kaketío": "Kaketío",
    "Ayaman": "Ayaman", "Timotocuica": "Timote (Timotocuica)",
    "Timote": "Timote (Timotocuica)", "Gayón": "Gayón", "Inga": "Inga", "Kechwa": "Kechwa",
    "Píritu": "Píritu", "Jirajara": "Jirajara", "Cumanagoto": "Kumanagoto",
    "Kumanagoto": "Kumanagoto", "Arawako": "Arawak", "Lokono": "Arawak",
    "Tunebo": "Tunebo",
    "No declarado": "Indigenous (people not stated)", "Otro": "Other indigenous people",
}
# INE's state names -> the map's.
STATES = {"Vargas": "La Guaira", "Dependencias federales": "Dependencias Federales"}
# INE's municipio names -> the boundary file's: renamed since, or spelled
# otherwise there.
ALIASES = {
    "Sir Artur Mc Gregor": "Sir Arthur Mac Gregor",
    "Turístico Diego Bautista Urbaneja": "Diego Bautista Urbanejo",
    "Bolivariano Angostura": "Raúl Leoni", "Tinaquillo": "Falcón",
    "Ezequiel Zamora": "San Carlos", "Pedro Zaraza": "Zaraza",
    "Antonio Rómulo Acosta": "Antonio Rómulo Costa", "Panamericano": "Panamericanp",
    "Jesús María Semprún": "Jesús María Semprum", "Indígena Bolivariano Guajira": "Páez",
}
# A municipio the boundary file does not draw apart -> the one whose polygon
# holds it, and why.
CONTAINED = {
    "0518": ("0508", "Ocumare de la Costa de Oro, which the boundary file does not draw: its "
                     "coast lies inside this polygon, which reaches from the Valle de Aragua "
                     "to the sea"),
}
UNCOUNTED = {("Bolívar", "Zona en Reclamación"): (
    "The Guayana Esequiba, which Venezuela claims and Guyana administers: Venezuela's census "
    "counts no one there.")}

PROBES = {
    "munic": """RUNDEF Job
    SELECTION ALL

TABLE T1
    AS FREQUENCY
    OF PERSONA.SEXO
    AREABREAK MUNICIPI
""",
    "indigena": """RUNDEF Job
    SELECTION ALL

TABLE T1
    AS FREQUENCY
    OF PERSONA.INDIGENA

TABLE T2
    AS CROSSTABS
    OF PERSONA.INDIGENA BY PERSONA.USTEDSEREC
""",
}


def split_rows(table: dict, what: str) -> tuple[list[tuple[str, int]], int]:
    """(the answers, those not asked or not answering), checked against the Total."""
    answers = [(k, n) for k, n in table["rows"] if not NOT_ASKED.match(k)]
    rest = sum(n for k, n in table["rows"] if NOT_ASKED.match(k)) + (table["na"] or 0)
    if sum(n for _, n in answers) != table["total"]:
        raise SystemExit(f"venezuela_redatam: {what}: {table['name']}'s answers do not make "
                         "its Total")
    return answers, rest


def translate(rows: list[tuple[str, int]], names: dict[str, str], what: str) -> Counter:
    out: Counter = Counter()
    for label, n in rows:
        if label not in names:
            raise SystemExit(f"venezuela_redatam: {what}: {label!r} is not a category this "
                             "file knows")
        out[names[label]] += n
    return out


def municipio_counts(by_question: dict[str, list[dict]]) -> dict[str, dict[str, Any]]:
    """Municipio code -> its state, name and counts, every table checked."""
    units: dict[str, dict[str, Any]] = {}
    for question, found in by_question.items():
        whole = [t for t in found if not t["area"]]
        areas = [t for t in found if t["area"]]
        if len(whole) != 1 or whole[0]["total"] != sum(t["total"] for t in areas):
            raise SystemExit(f"venezuela_redatam: {question}: the whole base's table is not "
                             "the municipios' sum")
        for table in areas:
            code = table["area"]
            if not re.fullmatch(r"\d{4}", code):
                raise SystemExit(f"venezuela_redatam: {question}: {code!r} is no municipio")
            state, _, name = table["name"].partition(", ")
            unit = units.setdefault(code, {"state": STATES.get(state, state), "name": name})
            if question in unit:
                raise SystemExit(f"venezuela_redatam: {question}: {code} twice")
            unit[question] = table
    for code, unit in units.items():
        missing = [q for q in QUESTIONS if q not in unit]
        if missing:
            raise SystemExit(f"venezuela_redatam: {code} has no {missing} table")
        sexes, rest = split_rows(unit["sex"], "sex")
        people = unit["sex"]["total"]
        if rest:
            raise SystemExit(f"venezuela_redatam: {unit['name']} has people with no sex")
        unit["people"] = people
        unit["sexes"] = translate([(fold(k), n) for k, n in sexes], SEXES, "sex")
        ages: Counter = Counter()
        for label, n in split_rows(unit["age"], "age")[0]:
            if not label.isdigit():
                raise SystemExit(f"venezuela_redatam: an age label {label!r}")
            ages[int(label)] += n
        if sum(ages.values()) != people:
            raise SystemExit(f"venezuela_redatam: {unit['name']}'s ages do not make it")
        unit["ages"] = ages
        peoples, not_indigenous = split_rows(unit["peoples"], "peoples")
        identity, unasked = split_rows(unit["identity"], "identity")
        unit["peoples_"] = translate(peoples, PEOPLES, "peoples")
        unit["identity_"] = translate(identity, IDENTITY, "identity")
        indigenous = sum(unit["peoples_"].values())
        if indigenous + not_indigenous != people or unit["identity"]["total"] + unasked != people:
            raise SystemExit(f"venezuela_redatam: {unit['name']}'s questions do not make its "
                             f"{people:,} people")
        if unasked < indigenous:
            raise SystemExit(f"venezuela_redatam: {unit['name']}: more indigenous people than "
                             "people the identity question was not put to")
        unit["not_stated"] = unasked - indigenous
    national = sum(u["people"] for u in units.values())
    if national != NATIONAL:
        raise SystemExit(f"venezuela_redatam: the municipios make {national:,}, not INE's "
                         f"{NATIONAL:,}")
    log(f"  {len(units)} municipios making INE's {NATIONAL:,}; every question making each")
    return units


def summed(parts: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"people": sum(p["people"] for p in parts),
                           "not_stated": sum(p["not_stated"] for p in parts)}
    for key in ("sexes", "ages", "peoples_", "identity_"):
        total: Counter = Counter()
        for part in parts:
            total.update(part[key])
        out[key] = total
    return out


def check_states(units: dict[str, dict[str, Any]], published: dict[str, tuple]) -> None:
    """Each state's peoples, summed from its municipios, must be INE's table by state."""
    by_state: dict[str, Counter] = {}
    for unit in units.values():
        by_state.setdefault(venezuela_census.state_key(unit["state"]), Counter()).update(
            unit["peoples_"])
    for key, counts in by_state.items():
        name, total, table = published.get(key, (key, 0, Counter()))
        mine = {k: v for k, v in counts.items() if v}
        theirs = {k: v for k, v in table.items() if v}
        if mine != theirs:
            diff = {k: (mine.get(k, 0), theirs.get(k, 0)) for k in set(mine) | set(theirs)
                    if mine.get(k, 0) != theirs.get(k, 0)}
            raise SystemExit(f"venezuela_redatam: {name}'s peoples differ from INE's table by "
                             f"state: {diff}")
    log(f"  every state's peoples equal INE's published table by state, people by people")


def fields(unit: dict[str, Any], level: str) -> dict[str, Any]:
    sexes = unit["sexes"]
    counts = Counter(unit["peoples_"]) + Counter(unit["identity_"])
    if unit["not_stated"]:
        counts[NOT_STATED] = unit["not_stated"]
    indigenous = sum(unit["peoples_"].values())
    out = {
        "median_age": measure(median_age(unit["ages"]), unit="years", year=YEAR, source=SOURCE),
        "median_age_note": (
            "Interpolated within the single year of age that holds the middle person, from "
            "the 2011 census's count of everyone by single year of age."),
        "sex_ratio": measure(round(1000 * sexes["men"] / sexes["women"]),
                             unit="males_per_1000_females", year=YEAR, source=SOURCE),
        "ethnicity": shares(dict(counts)),
        "ethnicity_year": YEAR,
        "ethnicity_note": (
            "Two questions of the 2011 census. Everyone was asked whether they belong to an "
            f"indigenous people, and which: {indigenous:,} of the {unit['people']:,} people here "
            "do, and each people is its own line, under the name INE's table by state gives "
            "it. Everyone else was asked whether they see themselves as negra/negro, "
            "afrodescendiente, morena/moreno, blanca/blanco or otra; in Venezuela moreno is "
            "the brown, mixed majority, which the Factbook reports as mestizo. "
            + (f"{unit['not_stated']:,} answered neither and are 'Not stated'."
               if unit["not_stated"] else "")),
    }
    if level == "admin2":
        out["population"] = measure(unit["people"], year=YEAR, source=SOURCE)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", choices=sorted(PROBES))
    ap.add_argument("--limit", type=int, default=20000)
    args = ap.parse_args()
    session = Session()
    session.get(PORTAL)
    server = Server(CMDSET, BASE, session=session, who="venezuela_redatam")
    if args.probe:
        for page in server.output(PROBES[args.probe]):
            report(CMDSET, page, args.limit)
            for t in tables(page):
                print(f"  table: area={t['area']} name={t['name']!r} title={t['title']!r} "
                      f"total={t['total']} na={t['na']} rows={t['rows'][:30]}")
        return 0

    found = {}
    for question, variable in QUESTIONS.items():
        found[question] = server.frequency(f"PERSONA.{variable}", areabreak="MUNICIPI")
        log(f"  {variable}: {len(found[question])} tables")
    units = municipio_counts(found)

    import xlrd
    book = xlrd.open_workbook(file_contents=http_get(venezuela_census.PEOPLES_URL, binary=True,
                                                     cache=False))
    sheet = book.sheet_by_index(0)
    published, _ = venezuela_census.peoples_table(
        [sheet.row_values(r) for r in range(sheet.nrows)])
    check_states(units, published)

    admin1 = json.loads((SITE / "admin1" / "VEN.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "VEN.units.json").read_text())
    parents = {u["id"]: u["name"] for u in admin1}
    first = {fold(u["name"]): u for u in admin1}
    shape_of = {(parents[s["parent"]], s["name"]): s for s in admin2}

    groups: dict[str, list[str]] = {}
    for code in sorted(units):
        target = CONTAINED.get(code, (code, None))[0]
        groups.setdefault(target, []).append(code)
    set_aside = set(UNCOUNTED)
    shapes = [s for s in admin2 if (parents[s["parent"]], s["name"]) not in set_aside]
    municipios = {code: (units[code]["name"], units[code]["state"]) for code in groups}
    # An alias is tried within the municipio's own state first, so Cojedes's
    # Ezequiel Zamora finds San Carlos there while Barinas's and Monagas's
    # find their own Ezequiel Zamora.
    bound, missing = bind(municipios, shapes, parents, ALIASES)
    log(f"  {len(bound)} of {len(groups)} municipios bound; not: {missing}")
    unexpected = [m for m in missing if not m.startswith("Dependencias federales")]
    if unexpected:
        raise SystemExit(f"venezuela_redatam: municipios with no polygon: {unexpected}")
    empty = sorted(s["name"] for s in shapes if s["id"] not in set(bound.values()))
    if empty:
        raise SystemExit(f"venezuela_redatam: polygons with no municipio: {empty}")

    drawn = {s["id"]: s for s in admin2}
    records: list[dict[str, Any]] = []
    for target, codes in sorted(groups.items()):
        if target not in bound:
            continue
        unit = summed([units[c] for c in codes])
        shape = drawn[bound[target]]
        name = units[target]["name"]
        values = fields(unit, "admin2")
        added = [CONTAINED[c][1] for c in codes if c != target]
        if added:
            values["population"]["note"] = "Includes " + "; ".join(added) + "."
        records.append(record(
            f"VEN-INE-{target}", name, level="admin2", parent="VEN", country="VEN",
            parent_name=units[target]["state"], codes={"ine": target},
            match_by="shape_id", shape_id=shape["id"],
            aliases=[shape["name"]] if fold(shape["name"]) != fold(name) else [],
            **values,
            sources=[{"field": "population/median age/sex ratio/ethnicity", "name": SOURCE,
                      "url": PAGE, "year": YEAR}]))
    for (state, name), why in UNCOUNTED.items():
        shape = shape_of[(state, name)]
        records.append(record(
            f"VEN-INE-{fold(state)}-{fold(name)}", name, level="admin2", parent="VEN",
            country="VEN", parent_name=state, match_by="shape_id", shape_id=shape["id"],
            population=gap("not_available", why), median_age=gap("not_available", why),
            sex_ratio=gap("not_available", why), ethnicity=gap("not_available", why),
            sources=[{"field": "note", "name": SOURCE, "url": PAGE, "year": YEAR}]))

    states: dict[str, list[dict[str, Any]]] = {}
    for unit in units.values():
        states.setdefault(unit["state"], []).append(unit)
    for state, parts in sorted(states.items()):
        shape = first.get(fold(state))
        if shape is None:
            raise SystemExit(f"venezuela_redatam: state {state!r} has no polygon")
        records.append(record(
            f"VEN-INE-{fold(state)}", shape["name"], level="admin1", parent="VEN",
            country="VEN", match_by="shape_id", shape_id=shape["id"],
            **fields(summed(parts), "admin1"),
            sources=[{"field": "median age/sex ratio/ethnicity", "name": SOURCE, "url": PAGE,
                      "year": YEAR}]))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {sum(r['level'] == 'admin1' for r in records)} states, "
        f"{sum(r['level'] == 'admin2' for r in records)} municipios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
