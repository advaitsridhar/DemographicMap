#!/usr/bin/env python3
"""Central African Republic -- the 2021 census mapping's count, and 2016 ages.

The map draws the 17 prefectures and 72 sub-prefectures of the 2003 census
(RGPH03), whose religion, language and ethnicity car_prefecture.json already
reads from the U.S. Census Bureau's workbook for the CAR on HDX. The same
workbook carries two more sheets this reads:

* **Population**: the Institut Centrafricain des Statistiques et des Etudes
  Economiques et Sociales (ICASEES), *RGPH-4: Principaux résultats de la
  cartographie 2021* (2022) -- the people counted at the mapping stage of the
  fourth census, by sex, as of 1 March 2021, for 20 prefectures, 79
  sub-prefectures and 181 communes. That is a count by the statistics office,
  newer than OCHA's 2015 projection on the sub-prefectures, and the only sex
  ratio anywhere for the country's units.
* **Age-Sex**: ICASEES, *Annuaire statistique de la République Centrafricaine
  2016* (2018), tables 110-116: the administrative population by prefecture,
  sex and five-year age group at 31 December 2016 -- an estimate, which gives
  the 17 prefectures a median age where nothing else does, provided each
  prefecture has an age structure of its own (tested below).

**2021 onto 2003.** In 2020 three prefectures were made out of old ones
(Mambéré, Lim-Pendé, Ouham-Fafa) and seven sub-prefectures out of old ones.
Communes carry the lineage: each of the 2021 communes is found among the 2003
census's communes of the same name inside the old prefecture it descends from,
and so in its 2003 sub-prefecture -- the polygon. A 2021 commune with no 2003
namesake takes the 2003 sub-prefecture its own 2021 sub-prefecture's other
communes all lie in; where they do not all lie in one, the polygons concerned
get no figure and say why. A 2003 sub-prefecture is the sum of the 2021
communes it holds; the sums are checked against every 2021 sub-prefecture and
prefecture the table prints whole.

Usage:
    python -m scripts.fetch_census.car_census [--dump]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from collections import defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, RAW, gap, http_get, log, measure, record, write_json
from .binding import bind, fold
from .cod_ps_age import grouped_median, same_structure
from .uscb import dataset_url, number, sheet_rows, workbook_url

DATASET = "car-subnational-boundaries-and-tabular-data"
OUT = "car_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
COUNT_YEAR = 2021
AGE_YEAR = 2016
COUNT_SOURCE = ("Institut Centrafricain des Statistiques et des Etudes Economiques et Sociales "
                "(ICASEES), RGPH-4: Principaux résultats de la cartographie 2021 (2022), as "
                "tabulated by the U.S. Census Bureau")
AGE_SOURCE = ("Institut Centrafricain des Statistiques et des Etudes Economiques et Sociales "
              "(ICASEES), Annuaire statistique de la République Centrafricaine 2016 (2018), "
              "tables 110-116, as tabulated by the U.S. Census Bureau")
LICENCE = "CC BY-IGO, published via HDX"

# The 2021 prefectures made in 2020 out of 2003 ones, as their communes show
# (checked on every run: each new prefecture's communes must all be found in
# the one old prefecture named here).
NEW_PREFECTURES = {"mambere": "mamberekadei", "limpende": "ouhampende", "ouhamfafa": "ouham"}

# The 2003 census's sub-prefecture names the boundary file spells otherwise
# (car_prefecture's own list, read off the two sets of leftovers).
SP_ALIASES = {"Aba": "Abba", "Bossemptele": "Bossemtélé", "Nanga-Boguila": "Nagha Boguila",
              "Ndjoukou": "Djoukou"}


def table(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """A USCB sheet as dicts keyed by its field-name row (row 0); row 1 is aliases."""
    names = ["" if v is None else str(v).strip() for v in rows[0]]
    return [{n: v for n, v in zip(names, row) if n} for row in rows[2:]
            if any(v not in (None, "") for v in row)]


def level(row: dict[str, Any]) -> int | None:
    value = number(row.get("ADM_LEVEL"))
    return int(value) if value is not None else None


def text(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def counts_2021(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The Population sheet: {"prefectures": {...}, "sps": {...}, "communes": [...]}."""
    out: dict[str, Any] = {"country": None, "prefectures": {}, "sps": {}, "communes": []}
    for row in rows:
        lvl = level(row)
        figures = tuple(number(row.get(k)) for k in ("POP_BTOTL", "POP_MTOTL", "POP_FTOTL"))
        if any(f is None for f in figures):
            continue
        total, men, women = (int(f) for f in figures)
        unit = {"name": text(row, "AREA_NAME"), "pref": text(row, "ADM1_NAME"),
                "sp": text(row, "ADM2_NAME"), "total": total, "men": men, "women": women}
        if lvl == 0:
            out["country"] = unit
        elif lvl == 1:
            out["prefectures"][fold(unit["name"])] = unit
        elif lvl == 2:
            out["sps"][(fold(unit["pref"]), fold(unit["name"]))] = unit
        elif lvl == 3:
            out["communes"].append(unit)
    return out


def communes_2003(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The 2003-vintage hierarchy, from a 2003 census sheet: prefectures, sps, communes."""
    prefs: dict[str, str] = {}
    sps: dict[tuple[str, str], str] = {}
    communes: list[tuple[str, str, str]] = []
    for row in rows:
        lvl = level(row)
        if lvl == 1:
            prefs[fold(text(row, "AREA_NAME"))] = text(row, "AREA_NAME")
        elif lvl == 2:
            sps[(fold(text(row, "ADM1_NAME")), fold(text(row, "AREA_NAME")))] = text(row, "AREA_NAME")
        elif lvl == 3:
            communes.append((fold(text(row, "ADM1_NAME")), fold(text(row, "ADM2_NAME")),
                             fold(text(row, "AREA_NAME"))))
    return {"prefs": prefs, "sps": sps, "communes": communes}


def crosswalk(c21: dict[str, Any], g03: dict[str, Any]) -> tuple[dict, list[str]]:
    """2003 (pref, sp) -> its 2021 communes, and what could not be placed."""
    old_of = {k: NEW_PREFECTURES.get(k, k) for k in c21["prefectures"]}
    by_name: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for pref, sp, commune in g03["communes"]:
        by_name[(pref, commune)].append((pref, sp))
    placed: dict[int, tuple[str, str]] = {}
    problems: list[str] = []
    for i, unit in enumerate(c21["communes"]):
        old = old_of.get(fold(unit["pref"]))
        hits = by_name.get((old, fold(unit["name"])), [])
        if len(hits) == 1:
            placed[i] = hits[0]
    # A new prefecture's communes must all come from the one old prefecture.
    for new, old in NEW_PREFECTURES.items():
        here = [i for i, u in enumerate(c21["communes"]) if fold(u["pref"]) == new]
        if not here:
            problems.append(f"no 2021 commune under prefecture {new}")
        if not any(i in placed for i in here):
            problems.append(f"none of {new}'s communes found in {old}")
    # A commune with no 2003 namesake: by its 2021 sub-prefecture's others.
    for i, unit in enumerate(c21["communes"]):
        if i in placed:
            continue
        siblings = {placed[j] for j, u in enumerate(c21["communes"])
                    if j in placed and (fold(u["pref"]), fold(u["sp"]))
                    == (fold(unit["pref"]), fold(unit["sp"]))}
        if len(siblings) == 1:
            placed[i] = siblings.pop()
            log(f"    {unit['name']} ({unit['sp']}, {unit['pref']}): no 2003 namesake; "
                f"placed with its sub-prefecture's other communes in {placed[i][1]}")
        else:
            problems.append(f"{unit['name']} ({unit['sp']}, {unit['pref']}): no 2003 namesake, "
                            f"and its sub-prefecture's communes lie in {sorted(siblings) or 'none'}")
    held: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, key in placed.items():
        held[key].append(i)
    return {"held": held, "unplaced": [i for i in range(len(c21["communes"])) if i not in placed]}, problems


def age_table(rows: list[dict[str, Any]]) -> dict[str, list[list[Any]]]:
    """{prefecture (folded): [[low, high, people], ...]} from the Age-Sex sheet."""
    out: dict[str, list[list[Any]]] = {}
    for row in rows:
        if level(row) != 1:
            continue
        groups: list[list[Any]] = []
        for low in range(0, 80, 5):
            cell = number(row.get(f"B{low:02d}{low + 4:02d}"))
            if cell is None:
                break
            groups.append([low, low + 4, cell])
        last = number(row.get("B80PL"))
        if len(groups) != 16 or last is None:
            continue
        groups.append([80, None, last])
        out[fold(text(row, "AREA_NAME"))] = groups
    return out


def build(book_rows: dict[str, list[dict[str, Any]]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]], url: str) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []
    c21 = counts_2021(book_rows["Population"])
    g03 = communes_2003(book_rows["Ethnicity"])
    report.append(f"2021: {len(c21['prefectures'])} prefectures, {len(c21['sps'])} "
                  f"sub-prefectures, {len(c21['communes'])} communes; 2003: {len(g03['prefs'])} "
                  f"prefectures, {len(g03['sps'])} sub-prefectures, {len(g03['communes'])} communes")
    # The table's own consistency: communes make their sub-prefecture, and
    # sub-prefectures their prefecture, wherever both are printed.
    bad = []
    for key, sp in c21["sps"].items():
        parts = [u for u in c21["communes"] if (fold(u["pref"]), fold(u["sp"])) == key]
        if parts and sum(u["total"] for u in parts) != sp["total"]:
            bad.append(f"{sp['name']}: communes {sum(u['total'] for u in parts):,}, "
                       f"printed {sp['total']:,}")
    for key, pref in c21["prefectures"].items():
        parts = [u for (p, _), u in c21["sps"].items() if p == key]
        if parts and sum(u["total"] for u in parts) != pref["total"]:
            bad.append(f"{pref['name']}: sub-prefectures {sum(u['total'] for u in parts):,}, "
                       f"printed {pref['total']:,}")
    for unit in [*c21["sps"].values(), *c21["prefectures"].values(), *c21["communes"]]:
        if unit["men"] + unit["women"] != unit["total"]:
            bad.append(f"{unit['name']}: men and women {unit['men'] + unit['women']:,}, "
                       f"total {unit['total']:,}")
    report += [f"  table: {b}" for b in bad]
    walk, problems = crosswalk(c21, g03)
    report += [f"  crosswalk: {p}" for p in problems]

    # The map's polygons for the 2003 sub-prefectures.
    parents = {u["id"]: u["name"] for u in admin1}
    pref_poly = {fold(u["name"]): u for u in admin1}
    pref_poly.setdefault("ombellampoko", next((u for u in admin1 if fold(u["name"]).startswith(
        "ombellam")), None))
    departments = {}
    for (pref, sp), name in g03["sps"].items():
        poly = pref_poly.get(pref)
        departments[f"{pref}/{sp}"] = (name.title() if name.isupper() else name,
                                       poly["name"] if poly else "")
    aliases = {k.title() if k.isupper() else k: v for k, v in SP_ALIASES.items()}
    bound, missing = bind(departments, admin2, parents,
                          {**aliases, **{k.upper(): v for k, v in SP_ALIASES.items()}})
    report += [f"  not bound to a polygon: {m}" for m in missing]

    records: list[dict[str, Any]] = []
    cite_count = [{"field": "population/sex_ratio", "name": COUNT_SOURCE, "url": url,
                   "year": COUNT_YEAR, "license": LICENCE}]
    shapes2 = {u["id"]: u for u in admin2}
    for code, sid in sorted(bound.items(), key=lambda kv: kv[0]):
        pref, sp = code.split("/")
        shape = shapes2[sid]
        idx = walk["held"].get((pref, sp), [])
        if not idx:
            note = (f"No commune counted at the 2021 census mapping can be placed in "
                    f"{shape['name']} as the 2003 census drew it, so no 2021 count is shown.")
            records.append(record(f"CAF-RGPH4-{sid}", shape["name"], level="admin2",
                                  parent="CAF", country="CAF", match_by="shape_id",
                                  shape_id=sid, population=gap(NOT_AVAILABLE, note),
                                  sex_ratio=gap(NOT_AVAILABLE, note), sources=cite_count))
            report.append(f"  {shape['name']}: no 2021 commune")
            continue
        units = [c21["communes"][i] for i in idx]
        total = sum(u["total"] for u in units)
        men = sum(u["men"] for u in units)
        women = sum(u["women"] for u in units)
        sps21 = sorted({u["sp"] for u in units})
        # The 2021 sub-prefectures this polygon takes, each whole or in part.
        same = (len(sps21) == 1 and fold(sps21[0]) == sp
                and len(idx) == sum(1 for u in c21["communes"] if (fold(u["pref"]),
                                    fold(u["sp"])) == (fold(units[0]["pref"]), fold(units[0]["sp"]))))
        if same:
            note = (f"The people counted in {shape['name']} sub-prefecture at the mapping stage "
                    f"of the fourth general census (RGPH-4), 1 March 2021.")
        else:
            parts = ", ".join(f"{u['name']} ({u['sp']})" for u in units)
            note = (f"The people counted at the mapping stage of the fourth general census "
                    f"(RGPH-4), 1 March 2021, in the communes of {shape['name']} as the 2003 "
                    f"census drew it, added up: {parts}. Sub-prefectures made since 2003 are "
                    f"drawn here inside the ones they were made from.")
        records.append(record(
            f"CAF-RGPH4-{sid}", shape["name"], level="admin2", parent="CAF", country="CAF",
            match_by="shape_id", shape_id=sid,
            population=measure(total, year=COUNT_YEAR, source=COUNT_SOURCE),
            population_note=note,
            sex_ratio=measure(round(1000 * men / women), unit="males_per_1000_females",
                              year=COUNT_YEAR, source=COUNT_SOURCE),
            sex_ratio_note=("Men per 1,000 women counted at the mapping stage of the fourth "
                            "general census (RGPH-4), 1 March 2021."),
            sources=cite_count))
        report.append(f"  {shape['name']}: {total:,} ({len(units)} communes"
                      + ("" if same else f"; 2021 sub-prefectures {', '.join(sps21)}") + ")")

    # Prefectures: the 2021 prefectures each old one became, summed.
    ages = age_table(book_rows["Age-Sex"])
    if ages:
        whole: dict[tuple[int, Any], float] = defaultdict(float)
        for groups in ages.values():
            for low, high, people in groups:
                whole[(low, high)] += people
        national = [[lo, hi, n] for (lo, hi), n in whole.items()]
        copied = [k for k, g in ages.items() if same_structure(g, national)]
        report.append(f"  ages: {len(ages)} prefectures; {len(copied)} carry the national "
                      f"proportions within the copy tolerance: {copied}")
        if len(copied) >= 0.8 * len(ages):
            report.append("  ages: the table gives its prefectures one structure; medians withheld")
            ages = {}
    cite_age = [{"field": "median_age", "name": AGE_SOURCE, "url": url, "year": AGE_YEAR,
                 "license": LICENCE}]
    for old in sorted({NEW_PREFECTURES.get(k, k) for k in c21["prefectures"]}):
        poly = pref_poly.get(old)
        if poly is None:
            report.append(f"  prefecture {old}: no polygon")
            continue
        parts = [u for k, u in c21["prefectures"].items() if NEW_PREFECTURES.get(k, k) == old]
        total = sum(u["total"] for u in parts)
        men = sum(u["men"] for u in parts)
        women = sum(u["women"] for u in parts)
        if len(parts) == 1:
            note = (f"The people counted in {poly['name']} prefecture at the mapping stage of "
                    f"the fourth general census (RGPH-4), 1 March 2021.")
        else:
            names = " and ".join(f"{u['name'].title()} ({u['total']:,})" for u in parts)
            note = (f"The people counted at the mapping stage of the fourth general census "
                    f"(RGPH-4), 1 March 2021, in {names}: the prefecture made in 2020 out of "
                    f"{poly['name']} is drawn here inside it.")
        fields: dict[str, Any] = {
            "population": measure(total, year=COUNT_YEAR, source=COUNT_SOURCE),
            "population_note": note,
            "sex_ratio": measure(round(1000 * men / women), unit="males_per_1000_females",
                                 year=COUNT_YEAR, source=COUNT_SOURCE),
            "sex_ratio_note": ("Men per 1,000 women counted at the mapping stage of the fourth "
                               "general census (RGPH-4), 1 March 2021."),
            "sources": list(cite_count)}
        groups = ages.get(old)
        median = grouped_median([tuple(g) for g in groups]) if groups else None
        if median is not None:
            fields["median_age"] = {"value": median, "unit": "years", "year": AGE_YEAR,
                                    "source": AGE_SOURCE}
            fields["median_age_note"] = (
                "Interpolated within the five-year age group that holds the middle person, "
                "from the statistics office's administrative population by age at 31 December "
                "2016, an estimate rather than a count.")
            fields["sources"] += cite_age
        records.append(record(f"CAF-RGPH4-{poly['id']}", poly["name"], level="admin1",
                              parent="CAF", country="CAF", match_by="shape_id",
                              shape_id=poly["id"], **fields))
        report.append(f"  prefecture {poly['name']}: {total:,}"
                      + (f", median age {median}" if median is not None else ""))
    if c21["country"]:
        report.append(f"  country line {c21['country']['total']:,}; prefectures make "
                      f"{sum(u['total'] for u in c21['prefectures'].values()):,}")
    return records, report


def dump(book_rows: dict[str, list[dict[str, Any]]]) -> None:
    for name in ("Population", "Ethnicity", "Age-Sex"):
        log(f"--- {name}")
        for row in book_rows[name]:
            lvl = level(row)
            figures = " ".join(str(row.get(k, "")) for k in
                               ("POP_BTOTL", "POP_MTOTL", "POP_FTOTL", "BTOTL", "MTOTL", "FTOTL")
                               if k in row)
            log(f"  {lvl} | {text(row, 'ADM1_NAME')} | {text(row, 'ADM2_NAME')} | "
                f"{text(row, 'ADM3_NAME')} | {text(row, 'AREA_NAME')} | {figures}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump", action="store_true", help="print the sheets' rows, write nothing")
    args = ap.parse_args()
    import openpyxl                                  # noqa: PLC0415
    url = workbook_url(DATASET)
    blob = http_get(url, binary=True, cache=False, timeout=300)
    log(f"car_census: {url}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    book_rows = {name: table(sheet_rows(book, name))
                 for name in ("Population", "Ethnicity", "Age-Sex")}
    if args.dump:
        dump(book_rows)
        return 0
    admin1 = json.loads((SITE / "admin1" / "CAF.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "CAF.units.json").read_text())
    records, report = build(book_rows, admin1, admin2, dataset_url(DATASET))
    for line in report:
        log(line)
    log(f"  {sum(r['level'] == 'admin1' for r in records)} prefectures and "
        f"{sum(r['level'] == 'admin2' for r in records)} sub-prefecture polygons written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
