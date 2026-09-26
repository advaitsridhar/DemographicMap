#!/usr/bin/env python3
"""Haiti's departments and arrondissements: IHSI's 2015 estimates, and UNFPA's 2024 ages.

Haiti has counted itself once this century, in the 2003 RGPH (IVe Recensement
Général de la Population et de l'Habitat); the fifth census has not been
held. Its 10 departments had no median age or sex ratio and its 42
arrondissements carried nothing but three populations. Two official tables
fill what can be filled, into two files because they are two kinds of figure:

* ``haiti_census.json`` -- IHSI's *Population totale, population de 18 ans
  et plus, ménages et densités estimés en 2015*, IHSI's last estimate for
  every department, arrondissement, commune and section communale, by sex.
  It is read from the US Census Bureau's workbook for Haiti on HDX, which
  carries it whole (IHSI's site now serves only a script-built page, and its
  PDF, captured by the Internet Archive, is the same table): population and
  sex ratio for the departments and arrondissements. Checks: every row's sexes
  make its total, the communes make their arrondissement, the arrondissements
  their department and the departments IHSI's 10,911,819.
* ``haiti_cod_ps_age.json`` -- median age from UNFPA's 2024 Common
  Operational Dataset (cod-ps-hti), a cohort-component projection from the
  2003 census for the 10 departments and 140 communes by sex and five-year
  age group. A projection, so a fill-only file like cod_ps_age.json, which
  could not bind Haiti's tables by name: its communes are summed here into
  their arrondissements. The commune -> arrondissement key is IHSI's own,
  from the 2015 estimates' hierarchy, and it must agree with the grouping
  of the P-codes (HTdda...): every arrondissement's communes one P-code
  prefix, and every prefix one arrondissement.

What the 2003 census asked and did not: it asked religion and IHSI
tabulates it for the whole country only (the religion volume it planned by
department is not published); it asked no ethnicity and no language -- see
NOT_COLLECTED_POLICY. Those three carry the reason on every unit here.

Usage:
    python -m scripts.fetch_census.haiti_census
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections import defaultdict
from typing import Any

from . import uscb
from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json
from .binding import bind, fold
from .cod_ps_age import age_columns, unit_figures

OUT = "haiti_census.json"
OUT_AGES = "haiti_cod_ps_age.json"
SITE = PROCESSED.parent.parent / "site" / "data"
DATASET = "haiti-subnational-population-and-housing-data-tables-with-administrative-boundaries"
COD_PS = "cod-ps-hti"
YEAR = 2015
NATIONAL = 10_911_819
SOURCE = ("IHSI, Population totale, population de 18 ans et plus, ménages et densités "
          "estimés en 2015 (March 2015), as the US Census Bureau tabulates it for HDX")
IHSI_PDF = ("http://web.archive.org/web/2016id_/http://www.ihsi.ht/pdf/projection/"
            "Estimat_PopTotal_18ans_Menag2015.pdf")
AGES_SOURCE = ("UNFPA, Haiti Common Operational Dataset on Population Statistics (COD-PS), "
               "2024: projection from the 2003 census by sex and five-year age group")
# IHSI's names for a department -> the boundary file's, with the word
# "département" taken off both.
DEPARTMENTS = {"GRAND'ANSE": "Grande-Anse"}
# IHSI's names for an arrondissement (as written here, in title case) -> the
# boundary file's, without "Arrondissement de".
ARRONDISSEMENTS: dict[str, str] = {}
# UNFPA's names for a commune -> IHSI's, where they differ by more than case
# and accents; each is the one commune of its department left on either side.
COMMUNES = {"Chamsolme": "Chansolme", "Cornillon / Grand Bois": "Cornillon",
            "La Vallée": "La Vallée de Jacmel"}
RELIGION_GAP = (
    "Haiti's 2003 census asked each person's religion, and IHSI publishes the answer for the "
    "whole country only (Tableau 206 of its RGPH 2003 results: aucune religion, catholique, "
    "adventiste, témoin de Jéhovah, baptiste, méthodiste, épiscopale, pentecôtiste, "
    "vaudouisant, musulman, mormon, autre). The volume by department its census plan "
    "announced (Volume 2, Tome 7, La religion) is not online, and neither the US Census "
    "Bureau's workbook for Haiti nor OCHA's COD-PS carries the question, so no figure below "
    "the country has been published to read.")


def number(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(round(float(str(value).replace(",", ""))))
    except ValueError:
        return None


def plain(name: str) -> str:
    """A department's or arrondissement's name without the word for what it is."""
    text = re.sub(r"[’`]", "'", str(name or "")).strip()
    text = re.sub(r"^(?:Département|Departement|Arrondissement)\s+"
                  r"(?:de la |de l'|des |du |de |d')?", "", text, flags=re.I)
    text = re.sub(r"\s+Department$", "", text, flags=re.I)
    return text.strip()


def estimates(rows: list[list[Any]]) -> dict[str, Any]:
    """The 2015 estimates' hierarchy: departments, arrondissements, communes, all checked."""
    names, _ = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    units: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows[2:]:
        level = number(row[at["ADM_LEVEL"]])
        if level is None:
            continue
        total, men, women = (number(row[at[k]]) for k in ("POP_BTOTL", "POP_MTOTL",
                                                             "POP_FTOTL"))
        where = str(row[at["AREA_NAME"]])
        if total is None or men is None or women is None or men + women != total:
            raise SystemExit(f"haiti_census: {where}: {men} men and {women} women do not "
                             f"make {total}")
        units[level].append({
            "name": str(row[at["AREA_NAME"]] or "").strip(),
            "code": str(row[at["GEO_MATCH"]]).strip(),
            "department": str(row[at["ADM1_NAME"]] or "").strip(),
            "arrondissement": str(row[at["ADM2_NAME"]] or "").strip(),
            "commune": str(row[at["ADM3_NAME"]] or "").strip(),
            "total": total, "men": men, "women": women})
    for child, parent in ((3, 2), (2, 1), (1, 0)):
        for up in units[parent]:
            # The country's code is HTI_GEO1_00, and its departments'
            # HTI_GEO1_01 to _10: they sit beside it, not under it.
            kids = [u for u in units[child]
                    if parent == 0 or u["code"].startswith(up["code"] + "_")]
            made = [sum(k[f] for k in kids) for f in ("total", "men", "women")]
            if made != [up["total"], up["men"], up["women"]]:
                raise SystemExit(f"haiti_census: {up['name']}'s {len(kids)} parts make {made}, "
                                 f"not {[up['total'], up['men'], up['women']]}")
    if units[0][0]["total"] != NATIONAL or len(units[1]) != 10 or len(units[2]) != 42:
        raise SystemExit(f"haiti_census: {len(units[1])} departments and {len(units[2])} "
                         f"arrondissements making {units[0][0]['total']:,}; IHSI published 10, "
                         f"42 and {NATIONAL:,}")
    log(f"  2015 estimates: 10 departments, 42 arrondissements and {len(units[3])} communes "
        f"making IHSI's {NATIONAL:,}; every row's sexes, and every level's parts, making it")
    return units


def cod_ps_rows(name: str) -> tuple[list[str], list[dict[str, str]]]:
    package = uscb.package(COD_PS)
    found = [r for r in package.get("resources", []) if (r.get("name") or "").lower() == name]
    if len(found) != 1:
        raise SystemExit(f"haiti_census: {COD_PS} has {len(found)} resources named {name}")
    body = http_get(found[0]["url"], binary=True, cache=False).decode("utf-8-sig", "replace")
    reader = csv.DictReader(io.StringIO(body))
    return list(reader.fieldnames or []), list(reader)


def summed(rows: list[dict[str, str]], columns: list[str]) -> dict[str, float]:
    return {c: sum(number(r.get(c)) or 0 for r in rows) for c in columns
            if re.match(r"^[TFM]_", c)}


def arrondissement_ages(units: dict[int, list[dict[str, Any]]]
                        ) -> tuple[dict[str, dict[str, float]], list[str], dict[str, str]]:
    """UNFPA's communes summed into IHSI's arrondissements: {USCB code: summed row}.

    Also returns the columns, and each arrondissement's P-code prefix.
    """
    columns, rows = cod_ps_rows("hti_admpop_adm2_2024.csv")
    communes = {(fold(u["department"]), fold(u["name"])): u for u in units[3]}
    arr_of = {u["code"]: u for u in units[2]}
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    prefix_of: dict[str, set[str]] = defaultdict(set)
    unmatched: list[str] = []
    taken: set[int] = set()
    for row in rows:
        department = DEPARTMENT_OF_PCODE.get(row["ADM1_PCODE"])
        key = (fold(department or ""), fold(COMMUNES.get(row["ADM2_FR"], row["ADM2_FR"])))
        commune = communes.get(key) or communes.get((key[0], fold(row["ADM2_EN"])))
        if commune is None:
            unmatched.append(f"{row['ADM2_FR']} ({row['ADM1_FR']})")
            continue
        if id(commune) in taken:
            raise SystemExit(f"haiti_census: two of UNFPA's communes are IHSI's {commune['name']}")
        taken.add(id(commune))
        arrondissement = commune["code"].rsplit("_", 1)[0]
        groups[arrondissement].append(row)
        prefix_of[arrondissement].add(row["ADM2_PCODE"][:5])
    if unmatched:
        left = sorted(f"{u['name']} ({u['department']})" for u in units[3]
                      if id(u) not in taken)
        raise SystemExit(f"haiti_census: UNFPA's communes with no IHSI commune: {unmatched}; "
                         f"IHSI's left: {left}")
    split = {arr_of[a]["name"]: sorted(p) for a, p in prefix_of.items() if len(p) != 1}
    owners: dict[str, list[str]] = defaultdict(list)
    for a, p in prefix_of.items():
        owners[next(iter(p))].append(arr_of[a]["name"])
    shared = {p: a for p, a in owners.items() if len(a) != 1}
    if split or shared or set(groups) != set(arr_of):
        raise SystemExit(f"haiti_census: IHSI's arrondissements and UNFPA's P-codes disagree: "
                         f"split {split}, shared {shared}, without communes "
                         f"{sorted(set(arr_of) - set(groups))}")
    log(f"  UNFPA 2024: {len(rows)} communes in IHSI's 42 arrondissements, each "
        "arrondissement one P-code prefix")
    return ({a: summed(r, columns) for a, r in groups.items()}, columns,
            {a: next(iter(p)) for a, p in prefix_of.items()})


# UNFPA's P-codes for the departments, checked against IHSI's names below.
DEPARTMENT_OF_PCODE = {"HT01": "OUEST", "HT02": "SUD-EST", "HT03": "NORD", "HT04": "NORD-EST",
                       "HT05": "ARTIBONITE", "HT06": "CENTRE", "HT07": "SUD",
                       "HT08": "GRAND'ANSE", "HT09": "NORD-OUEST", "HT10": "NIPPES"}


def department_ages(units: dict[int, list[dict[str, Any]]]
                    ) -> tuple[dict[str, dict[str, float]], list[str]]:
    columns, rows = cod_ps_rows("hti_admpop_adm1_2024.csv")
    out = {}
    names = {fold(u["department"]) for u in units[1]}
    for row in rows:
        department = DEPARTMENT_OF_PCODE.get(row["ADM1_PCODE"])
        if department is None or fold(department) not in names:
            raise SystemExit(f"haiti_census: UNFPA's department {row['ADM1_PCODE']} "
                             f"({row['ADM1_FR']}) is not IHSI's")
        if fold(plain(row["ADM1_FR"])) not in (fold(department),
                                               fold(DEPARTMENTS.get(department, department))):
            raise SystemExit(f"haiti_census: {row['ADM1_PCODE']} is {row['ADM1_FR']}, not "
                             f"{department}")
        out[fold(department)] = summed([row], columns)
    return out, columns


def median_fields(row: dict[str, float], columns: list[str], where: str) -> dict[str, Any]:
    cols = age_columns(columns)
    if cols is None:
        raise SystemExit("haiti_census: UNFPA's table has no age groups from 0 to an open group")
    figures, why = unit_figures(row, cols)
    if figures is None:
        raise SystemExit(f"haiti_census: {where}: {why}")
    return {
        "median_age": measure(figures["median"], unit="years", year=2024, source=AGES_SOURCE),
        "median_age_note": (
            "Interpolated within the five-year age group that holds the middle person, from "
            "UNFPA's 2024 projection of the population by sex and age group (COD-PS), which "
            "carries the 2003 census forward with fertility, mortality and migration; Haiti "
            "has held no census since 2003."),
    }


def gaps() -> dict[str, Any]:
    return {"religion": gap(NOT_AVAILABLE, RELIGION_GAP)}


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(http_get(uscb.workbook_url(DATASET), binary=True,
                                                      cache=False)),
                                  read_only=True, data_only=True)
    units = estimates(uscb.sheet_rows(book, "Population Estimates"))
    dept_rows, dept_columns = department_ages(units)
    arr_rows, arr_columns, prefixes = arrondissement_ages(units)

    admin1 = json.loads((SITE / "admin1" / "HTI.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "HTI.units.json").read_text())
    first = {fold(plain(u["name"])): u for u in admin1}
    parents = {u["id"]: u["name"] for u in admin1}

    def shape_of(department: str) -> dict[str, Any]:
        shape = first.get(fold(DEPARTMENTS.get(department, department)))
        if shape is None:
            raise SystemExit(f"haiti_census: department {department!r} has no polygon")
        return shape

    source = [{"field": "population/sex ratio", "name": SOURCE,
               "url": uscb.dataset_url(DATASET), "year": YEAR, "license": "CC BY, via HDX"},
              {"field": "population/sex ratio", "name": "IHSI, the same estimates as published",
               "url": IHSI_PDF, "year": YEAR}]
    age_source = [{"field": "median age", "name": AGES_SOURCE,
                   "url": uscb.dataset_url(COD_PS), "year": 2024,
                   "license": "CC BY-IGO, via HDX"}]

    def figures(u: dict[str, Any]) -> dict[str, Any]:
        return {"population": measure(u["total"], unit="people", year=YEAR, source=SOURCE),
                "sex_ratio": measure(round(1000 * u["men"] / u["women"]),
                                     unit="males_per_1000_females", year=YEAR, source=SOURCE)}

    records, ages = [], []
    for u in units[1]:
        shape = shape_of(u["department"])
        common = dict(level="admin1", parent="HTI", country="HTI", match_by="shape_id",
                      shape_id=shape["id"])
        records.append(record(f"HTI-IHSI-{fold(u['department'])}", shape["name"], **common,
                              **figures(u), **gaps(), sources=source))
        ages.append(record(f"HTI-UNFPA-{fold(u['department'])}", shape["name"], **common,
                           **median_fields(dept_rows[fold(u["department"])], dept_columns,
                                           u["department"]), sources=age_source))

    offices = {u["code"]: (plain(u["name"]).title(), shape_of(u["department"])["name"])
               for u in units[2]}
    shapes = [{**s, "name": plain(s["name"])} for s in admin2]
    bound, missing = bind(offices, shapes, parents, ARRONDISSEMENTS)
    log(f"  {len(bound)} arrondissements bound to their polygons; {len(missing)} not: "
        + "; ".join(missing))
    labels = {s["id"]: s["name"] for s in admin2}
    log(f"  polygons with no arrondissement: "
        f"{sorted(labels[s['id']] for s in admin2 if s['id'] not in set(bound.values()))}")
    for u in units[2]:
        sid = bound.get(u["code"])
        if sid is None:
            continue
        arr = u["code"]
        common = dict(level="admin2", parent="HTI", country="HTI",
                      parent_name=offices[u["code"]][1], match_by="shape_id", shape_id=sid)
        records.append(record(f"HTI-IHSI-{u['code']}", labels[sid], **common, **figures(u),
                              **gaps(), sources=source))
        ages.append(record(f"HTI-UNFPA-{u['code']}", labels[sid], **common,
                           codes={"pcode_prefix": prefixes[arr]},
                           **median_fields(arr_rows[arr], arr_columns, u["name"]),
                           sources=age_source))
    write_json(PROCESSED / OUT, records)
    write_json(PROCESSED / OUT_AGES, ages)
    log(f"  wrote {OUT}: {len(records)} records; {OUT_AGES}: {len(ages)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
