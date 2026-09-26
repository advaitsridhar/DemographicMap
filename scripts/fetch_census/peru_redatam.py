#!/usr/bin/env python3
"""Peru's 2017 census by province, tabulated on INEI's REDATAM WebServer.

INEI publishes the 2017 census (Censos Nacionales 2017: XII de Población, VII
de Vivienda y III de Comunidades Indígenas) for on-line tabulation as the
public base CPV2017DI, and its "Procesador Estadístico En-línea" runs a
Redatam+SP program sent to it. This sends one program a question, each a
frequency table broken by province, and reads the tables back.

What it writes, for Peru's 196 provinces and its 26 first-level units:

* Median age, interpolated within the single year holding the middle person,
  and the sex ratio, from everyone counted (C5P41, C5P2).
* Ethnicity (provinces and first level): C5P25, "Por sus costumbres y sus
  antepasados usted se considera", put to everyone aged 12 and over, in
  INEI's own eleven categories. "No sabe / No responde" is left out of the
  shares and counted in the note.
* Religion and mother tongue (provinces): C5P26, the religion professed by
  those aged 12 and over, and C5P11, the language a person learned to speak
  in, asked of those aged 3 and over. The first level keeps the Perfil
  Sociodemográfico's department tables (peru.py), which are the same count.

Population goes to a file of its own, ``peru_redatam_population.json``, which
the build reads as fill-only: the map's province figures are newer than 2017,
and the census count stands only where a province has none.

Every label is translated by the tables here, and one this file does not know
stops the run. Every province must have all five tables; each question's
total and its "No Aplica" must make the province's population; and the
provinces must make INEI's published national count, 29,381,884.

``--probe NAME`` sends one of the programs in PROBES and prints what comes
back -- the page's text, frames, links and forms, and the tables parsed from
it -- so an output's shape is read before a parser relies on it.

Usage:
    python -m scripts.fetch_census.peru_redatam --probe labels
    python -m scripts.fetch_census.peru_redatam
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse

from collections import Counter
from typing import Any

from scripts.probe_redatam import Session, attrs, report

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .binding import bind, fold
from .redatam import Server, median_age, tables  # noqa: F401 -- tables: tests read it here

PORTAL = "https://censos2017.inei.gob.pe/bininei/RpWebEngine.exe/Portal?BASE=CPV2017DI&lang=esp"
CMDSET = "https://censos2017.inei.gob.pe/bininei/RpWebStats.exe/CmdSet"
OUT = PROCESSED / "peru_redatam.json"
POPULATION_OUT = PROCESSED / "peru_redatam_population.json"
SITE = PROCESSED.parent.parent / "site" / "data"
YEAR = 2017
NATIONAL = 29_381_884
SOURCE = ("INEI, Censos Nacionales 2017: XII de Población, VII de Vivienda y III de "
          "Comunidades Indígenas, tabulated on INEI's REDATAM base CPV2017DI")
PAGE = "https://censos2017.inei.gob.pe/pubinei/index.asp"
QUESTIONS = {"sex": "C5P2", "age": "C5P41", "ethnicity": "C5P25", "religion": "C5P26",
             "language": "C5P11"}
UNANSWERED = "No sabe / No responde"
SILENT = "No escucha, ni habla"
SEXES = {"Hombre": "men", "Mujer": "women"}
ETHNICITY = {
    "Quechua": "Quechua", "Aimara": "Aymara",
    "Nativo o indígena de la amazonía": "Amazonian indigenous",
    "Parte de otro pueblo indígena u originario": "Other indigenous people",
    "Negro, moreno, zambo, mulato / pueblo afroperuano o afrodescendiente": "Afro-Peruvian",
    "Blanco": "White", "Mestizo": "Mestizo", "Otro": "Other",
    "Nikkei": "Nikkei (Japanese Peruvian)", "Tusán": "Tusán (Chinese Peruvian)",
}
# The same four names the department tables carry (peru.py) where the two
# agree, and the four churches INEI counts apart from "Otra" by their own.
RELIGION = {
    "Católica": "Catholic", "Evangélica": "Evangelical", "Otra": "Other religion",
    "Ninguna": "No religion", "Cristiano": "Christian (non-denominational)",
    "Adventista": "Seventh-day Adventist", "Testigo de Jehová": "Jehovah's Witnesses",
    "Mormones": "Latter-day Saints",
}
# English names for Spanish and the foreign languages; Peru's own by the names
# its census prints, one where it prints two.
LANGUAGE = {
    "Castellano": "Spanish", "Quechua": "Quechua", "Aimara": "Aymara",
    "Ashaninka": "Ashaninka", "Awajún / Aguaruna": "Awajún", "Shipibo - Konibo": "Shipibo-Konibo",
    "Shawi/Chayahuita": "Shawi", "Matsigenka/Machiguenga": "Matsigenka", "Achuar": "Achuar",
    "Otra lengua nativa u originaria": "Other indigenous language",
    "Portugués": "Portuguese", "Otra lengua extranjera": "Other foreign language",
    "Lengua de señas peruanas": "Peruvian Sign Language",
    "Wampis": "Wampis", "Kichwa": "Kichwa", "Nomatsigenga": "Nomatsigenga", "Tikuna": "Tikuna",
    "Urarina": "Urarina", "Yine": "Yine", "Yanesha": "Yanesha", "Kandozi-Chapra": "Kandozi-Chapra",
    "Kakataibo": "Kakataibo", "Matses": "Matses", "Kukama kukamiria": "Kukama-Kukamiria",
    "Yagua": "Yagua", "Secoya": "Secoya", "Harakbut": "Harakbut", "Yaminahua": "Yaminahua",
    "Jaqaru": "Jaqaru", "Murui-Muinani": "Murui-Muinani", "Kakinte": "Kakinte",
    "Amahuaca": "Amahuaca", "Arabela": "Arabela", "Nahua": "Nahua (Peru)",
    "Ese Eja": "Ese Eja", "Capanahua": "Capanahua", "Maijuna": "Maijuna", "Ocaina": "Ocaina",
    "Sharanahua": "Sharanahua", "Cauqui": "Cauqui", "Shiwilu": "Shiwilu",
    "Cashinahua": "Cashinahua", "Isconahua": "Isconahua", "Omagua": "Omagua",
}
# INEI's department names -> the map's first-level unit; Lima's province and
# the rest of the department are two units there.
DEPARTMENT = {"Callao": "El Callao", "Provincia Constitucional del Callao": "El Callao",
              "Áncash": "Ancash",
              # INEI's area label for La Libertad's provinces drops an i.
              "La Lbertad": "La Libertad"}
# INEI's province names -> the boundary file's, where they differ by more than
# accents. Callao's area is labelled with the province's full title alone.
PROVINCE = {"Provincia Constitucional del Callao": "Callao", "Nazca": "Nasca"}
LIMA_METRO, LIMA_METRO_UNIT = "1501", "Municipalidad Metropolitana de Lima"
AGE = re.compile(r"(\d+)")
# "Amazonas, provincia: Chachapoyas", and for Madre de Dios "Madre de Dios
# prov. de Tambopata".
PLACE = re.compile(r"^(.*?)(?:,\s*provincia:|\s+prov\.\s+de)\s*(.*)$")

PROBES = {
    # Religion (question 26, asked of those aged 12 and over), by department:
    # 25 small tables, enough to see how the output is laid out.
    "religion-dept": """RUNDEF Job
    SELECTION ALL

TABLE TABLE1
    AS FREQUENCY
    OF POBLACIO.C5P26
    AREABREAK DEPARTAM
""",
    # Every question's categories, nationally: the labels to translate.
    "labels": """RUNDEF Job
    SELECTION ALL

TABLE T1
    AS FREQUENCY
    OF POBLACIO.C5P2

TABLE T2
    AS FREQUENCY
    OF POBLACIO.C5P25

TABLE T3
    AS FREQUENCY
    OF POBLACIO.C5P25MC

TABLE T4
    AS FREQUENCY
    OF POBLACIO.C5P11

TABLE T5
    AS FREQUENCY
    OF POBLACIO.C5P26
""",
    # Single years of age for one small department's provinces: the shape of
    # a table whose category labels are numbers.
    "age-prov": """RUNDEF Job
    SELECTION ALL

TABLE TABLE1
    AS FREQUENCY
    OF POBLACIO.C5P41
    AREABREAK PROVINCI
""",
    # The same as a crosstab against the province code, the other way the
    # program could be written.
    "sex-prov-cross": """RUNDEF Job
    SELECTION ALL

DEFINE POBLACIO.PROV
    AS PROVINCI.CCPP
    TYPE STRING

TABLE TABLE1
    AS CROSSTABS
    OF POBLACIO.PROV BY POBLACIO.C5P2
""",
}


def run(session: Session, program: str) -> str:
    """The page the processor answers a program with, error pages included."""
    return Server(CMDSET, "CPV2017DI", session=session, who="peru_redatam").run(program)


def program(variable: str) -> str:
    return (f"RUNDEF Job\n    SELECTION ALL\n\nTABLE TABLE1\n    AS FREQUENCY\n"
            f"    OF POBLACIO.{variable}\n    AREABREAK PROVINCI\n")


def fetch(session: Session, variable: str) -> list[dict]:
    """One question's frequency table for every province, from the output frame."""
    out = Server(CMDSET, "CPV2017DI", session=session, who="peru_redatam").frequency(
        f"POBLACIO.{variable}", areabreak="PROVINCI")
    log(f"  {variable}: {len(out)} tables")
    return out


def translate(rows: list[tuple[str, int]], names: dict[str, str], question: str,
              known: tuple[str, ...] = ()) -> tuple[Counter, Counter]:
    """(translated counts, counts of the known non-answers), refusing unknown labels."""
    unknown = sorted({label for label, _ in rows} - set(names) - set(known))
    if unknown:
        raise SystemExit(f"peru_redatam: {question}: labels this file does not know: {unknown}")
    counts: Counter = Counter()
    left: Counter = Counter()
    for label, n in rows:
        if label in names:
            counts[names[label]] += n
        else:
            left[label] += n
    return counts, left


def collect(by_question: dict[str, list[dict]]) -> dict[str, dict[str, Any]]:
    """Province code -> its names and every question's counts, after the checks."""
    units: dict[str, dict[str, Any]] = {}
    for question, found in by_question.items():
        # After the provinces the processor prints the whole base's table with
        # no area row: the country, which is a check here, not a unit.
        whole = [t for t in found if not t["area"]]
        if len(whole) > 1 or (whole and whole[0]["total"] != sum(
                t["total"] for t in found if t["area"])):
            raise SystemExit(f"peru_redatam: {question}: the tables with no area are "
                             f"{[t['total'] for t in whole]}, not the provinces' sum")
        for table in found:
            code = table["area"]
            if not code:
                continue
            if len(code) != 4:
                raise SystemExit(f"peru_redatam: {question}: {code!r} is not a province code "
                                 f"({table['name']!r})")
            match = PLACE.match(table["name"])
            dept, prov = (match.group(1), match.group(2)) if match else (table["name"],
                                                                          table["name"])
            unit = units.setdefault(code, {"department": dept.strip(), "name": prov.strip()})
            if question in unit:
                raise SystemExit(f"peru_redatam: {question}: province {code} twice")
            unit[question] = table
    for code, unit in units.items():
        missing = [q for q in QUESTIONS if q not in unit]
        if missing:
            raise SystemExit(f"peru_redatam: province {code} ({unit['name']}) has no "
                             f"{missing} table")
        people = unit["sex"]["total"]
        for q in QUESTIONS:
            table = unit[q]
            if sum(n for _, n in table["rows"]) != table["total"]:
                raise SystemExit(f"peru_redatam: {q}: {unit['name']}'s rows do not make its total")
            if table["total"] + (table["na"] or 0) != people:
                raise SystemExit(f"peru_redatam: {q}: {unit['name']} has {table['total']:,} "
                                 f"answers and {table['na']} not applicable against "
                                 f"{people:,} people")
    national = sum(u["sex"]["total"] for u in units.values())
    if national != NATIONAL or len(units) != 196:
        raise SystemExit(f"peru_redatam: {len(units)} provinces making {national:,} people; "
                         f"INEI published 196 and {NATIONAL:,}")
    log(f"  196 provinces making INEI's {NATIONAL:,}, every question's total and "
        "'No Aplica' making each province")
    return units


def fields(unit: dict[str, Any], level: str) -> dict[str, Any]:
    """The written fields for one province, or for a first-level unit summed from them."""
    sexes, _ = translate(unit["sex"]["rows"], SEXES, "sex")
    ages = Counter()
    for label, n in unit["age"]["rows"]:
        years = AGE.search(label)
        if not years:
            raise SystemExit(f"peru_redatam: an age label with no number: {label!r}")
        ages[int(years.group(1))] += n
    people = sum(ages.values())
    eth, eth_left = translate(unit["ethnicity"]["rows"], ETHNICITY, "ethnicity", (UNANSWERED,))
    out: dict[str, Any] = {
        "median_age": measure(median_age(ages), unit="years", year=YEAR, source=SOURCE),
        "median_age_note": (
            "Interpolated within the single year of age that holds the middle person, from "
            "INEI's count of everyone by single year of age in the 2017 census; INEI "
            "tabulates the ages, not the median."),
        "sex_ratio": (measure(round(1000 * sexes["men"] / sexes["women"]),
                              unit="males_per_1000_females", year=YEAR, source=SOURCE)
                      if sexes["women"] else None),
        "ethnicity": shares(eth),
        "ethnicity_year": YEAR,
        "ethnicity_note": (
            "Question 25 of the 2017 census, put to everyone aged 12 and over: \"Por sus "
            "costumbres y sus antepasados, usted se considera\", in INEI's own categories. "
            f"Of the {sum(eth.values()) + sum(eth_left.values()):,} people aged 12 and over "
            f"counted here, {sum(eth_left.values()):,} said they did not know or gave no answer "
            "and are left out of the shares."),
        "sources": [{"field": "median age/sex ratio/ethnicity"
                     + ("/religion/language" if level == "admin2" else ""),
                     "name": SOURCE, "url": PAGE, "year": YEAR}],
    }
    if level == "admin2":
        religion, _ = translate(unit["religion"]["rows"], RELIGION, "religion")
        language, lang_left = translate(unit["language"]["rows"], LANGUAGE, "language",
                                        (UNANSWERED, SILENT))
        out.update({
            "religion": shares(religion),
            "religion_year": YEAR,
            "religion_note": (
                "The religion professed by everyone aged 12 and over (question 26 of the 2017 "
                f"census): the {sum(religion.values()):,} people of that age counted here."),
            "language": shares(language),
            "language_year": YEAR,
            "language_note": (
                "The language each person learned to speak in childhood, asked of everyone "
                f"aged 3 and over in the 2017 census: {sum(language.values()):,} of them here, "
                f"leaving out {lang_left[UNANSWERED]:,} who did not know or gave no answer and "
                f"{lang_left[SILENT]:,} who neither hear nor speak."),
        })
    return out


def summed(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Several provinces' tables added into one unit's."""
    out: dict[str, Any] = {}
    for q in QUESTIONS:
        rows: Counter = Counter()
        order: list[str] = []
        for part in parts:
            for label, n in part[q]["rows"]:
                if label not in rows:
                    order.append(label)
                rows[label] += n
        out[q] = {"rows": [(label, rows[label]) for label in order],
                  "total": sum(p[q]["total"] for p in parts)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", choices=sorted(PROBES))
    ap.add_argument("--limit", type=int, default=6000)
    ap.add_argument("--raw", type=int, default=0,
                    help="also print this many characters of each followed page's HTML")
    args = ap.parse_args()
    session = Session()
    session.get(PORTAL)
    if args.probe:
        page = run(session, PROBES[args.probe])
        print(f"program {args.probe}: {len(page):,} characters back")
        links = report(CMDSET, page, args.limit)
        links += [("frame", urllib.parse.urljoin(CMDSET, attrs(t)["src"]))
                  for t in re.findall(r"(?is)<i?frame\b[^>]*>", page) if attrs(t).get("src")]
        for label, url in links:
            if any(k in url for k in ("Tempo", ".xls", ".htm", "Text?")) \
                    and not url.lower().endswith((".xlsx", ".pdf")) and "reporte." not in url:
                print(f"follow: {label!r} -> {url}")
                body = session.get(url)
                report(url, body, args.limit)
                if args.raw:
                    print(body[:args.raw])
                for table in tables(body)[:40]:
                    print(f"  table {table['area']} {table['name']!r} of {table['title']!r}: "
                          f"total {table['total']}, not applicable {table['na']}")
                    for label_, n in table["rows"][:60]:
                        print(f"    {label_!r}: {n}")
        return 0
    units = collect({q: fetch(session, v) for q, v in QUESTIONS.items()})

    admin1 = json.loads((SITE / "admin1" / "PER.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "PER.units.json").read_text())
    parents = {u["id"]: u["name"] for u in admin1}
    first = {fold(u["name"]): u for u in admin1}

    def unit_of(code: str) -> str:
        if code == LIMA_METRO:
            return LIMA_METRO_UNIT
        dept = units[code]["department"]
        return DEPARTMENT.get(dept, dept)

    bound, missing = bind({c: (u["name"], unit_of(c)) for c, u in units.items()}, admin2, parents,
                          PROVINCE)
    log(f"  {len(bound)} provinces bound to their polygons; {len(missing)} not: "
        + "; ".join(missing))
    labels = {s["id"]: s["name"] for s in admin2}
    unbound = sorted(s["name"] for s in admin2 if s["id"] not in set(bound.values()))
    log(f"  polygons with no province: {unbound}")

    records = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for code, unit in sorted(units.items()):
        groups.setdefault(unit_of(code), []).append(unit)
        sid = bound.get(code)
        if sid is None:
            continue
        label = labels[sid]
        records.append(record(f"PER-INEI-{code}", unit["name"], level="admin2", parent="PER",
                              country="PER", parent_name=unit_of(code), codes={"ubigeo": code},
                              match_by="shape_id", shape_id=sid,
                              aliases=[label] if label != unit["name"] else [],
                              **fields(unit, "admin2")))
    for name, parts in sorted(groups.items()):
        shape = first.get(fold(name))
        if shape is None:
            raise SystemExit(f"peru_redatam: first-level unit {name!r} has no polygon")
        records.append(record(f"PER-INEI-{fold(name)}", shape["name"], level="admin1",
                              parent="PER", country="PER", match_by="shape_id",
                              shape_id=shape["id"], **fields(summed(parts), "admin1")))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} records")
    counted = [record(f"PER-INEI-POP-{code}", unit["name"], level="admin2", parent="PER",
                      country="PER", parent_name=unit_of(code), codes={"ubigeo": code},
                      match_by="shape_id", shape_id=bound[code],
                      aliases=[labels[bound[code]]] if labels[bound[code]] != unit["name"] else [],
                      population=measure(unit["sex"]["total"], year=YEAR, source=SOURCE),
                      population_note=(
                          "Everyone counted in the province by the 2017 census. It stands only "
                          "where the map has no newer figure for the province."),
                      sources=[{"field": "population", "name": SOURCE, "url": PAGE,
                                "year": YEAR}])
               for code, unit in sorted(units.items()) if code in bound]
    write_json(POPULATION_OUT, counted)
    log(f"  wrote {POPULATION_OUT.name}: {len(counted)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
