#!/usr/bin/env python3
"""Central African Republic -- the 2021 census mapping's count, and 2016 ages.

The map draws the 17 prefectures and 72 sub-prefectures of the 2003 census
(RGPH03), whose religion, language and ethnicity car_prefecture.json reads.
Their populations were OCHA's 2015 projection (69 of 72), and nothing gave a
median age or a sex ratio at either level.

**Population, 2021.** The Institut Centrafricain des Statistiques et des
Etudes Economiques et Sociales (ICASEES) counted the population at the mapping
stage of the fourth census (RGPH-4 cartography, reference date 1 March 2021)
and published it by commune of the 2020 division, as the U.S. Census Bureau's
workbook for the CAR tabulates it (sheet ``Population``: 20 prefectures, 79
sub-prefectures, 181 communes). The polygons are the 2003 division's, so each
2021 commune is found among the 2003 communes of the same name inside the
prefecture it descends from (Mambéré, Lim-Pendé and Ouham-Fafa were made out
of Mambéré-Kadéï, Ouham-Pendé and Ouham in 2020), a commune with no 2003
namesake goes with its 2021 sub-prefecture's other communes, and Bégoua --
made a sub-prefecture of Bangui in 2020, with no 2003 namesake and no
siblings -- goes to Bimbo, whose 2003 polygon surrounds Bangui and holds it.
A polygon takes the sum of its communes, a prefecture the sum of its polygons.

OCHA's edition of the same table (``icasees_cartocensitaire2021_formatocha_
public_V2.xlsx`` in cod-ps-caf) assigns the count to the 2003 communes itself
(sheet ``PrevCommune``), and the two assignments are compared polygon by
polygon on every run. They differ only where OCHA files a commune under a
namesake in another prefecture -- the town of Nola (Sangha-Mbaéré) under
Lobaye's commune of Nola -- and any other difference stops the run.

**No sex ratio from it.** The mapping table splits every unit's count into
men and women in one fixed proportion (49 to 51 to the person, urban and rural
alike), so it describes no unit's sexes; the run checks that this is still so
and says it on every record.

**Prefectures' ages and sexes, 2016.** ICASEES's *Annuaire statistique de la
République Centrafricaine 2016* (2018), tables 110-116, gives the
administrative population of each of the 17 prefectures by sex and five-year
age group at 31 December 2016 -- an estimate, not a count -- as the Census
Bureau's workbook tabulates it (sheet ``Age-Sex``). A median is taken by
interpolation within the five-year group holding the middle person, and only
for a prefecture whose age proportions are its own: one that shares them with
the country or with another prefecture to within COPY_TOLERANCE points in
every group is left out (cod_ps_age's test).

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

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, http_json, log, measure, record, write_json
from .binding import bind, fold
from .cod_ps_age import COPY_TOLERANCE, grouped_median, same_structure
from .uscb import dataset_url, number, sheet_rows, workbook_url

USCB_DATASET = "car-subnational-boundaries-and-tabular-data"
OCHA_DATASET = "cod-ps-caf"
HDX_API = "https://data.humdata.org/api/3/action"
OUT = "car_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
COUNT_YEAR = 2021
AGE_YEAR = 2016
COUNT_SOURCE = ("Institut Centrafricain des Statistiques et des Etudes Economiques et Sociales "
                "(ICASEES), RGPH-4: Principaux résultats de la cartographie 2021 (2022), "
                "population by commune, as OCHA publishes it")
COUNT_SOURCE_USCB = ("Institut Centrafricain des Statistiques et des Etudes Economiques et "
                     "Sociales (ICASEES), RGPH-4: Principaux résultats de la cartographie 2021 "
                     "(2022), population by prefecture, sub-prefecture and commune, as tabulated "
                     "by the U.S. Census Bureau")
AGE_SOURCE = ("Institut Centrafricain des Statistiques et des Etudes Economiques et Sociales "
              "(ICASEES), Annuaire statistique de la République Centrafricaine 2016 (2018), "
              "tables 110-116, as tabulated by the U.S. Census Bureau")
LICENCE = "CC BY-IGO, published via HDX"

# The 2021 prefectures made in 2020 out of 2003 ones (checked on every run).
NEW_PREFECTURES = {"mambere": "mamberekadei", "limpende": "ouhampende", "ouhamfafa": "ouham"}
# A 2021 commune with no 2003 namesake and no siblings to place it by, and the
# 2003 sub-prefecture whose polygon holds it: Bégoua, 12 km north of Bangui's
# centre, inside the 3,037 km2 polygon drawn as Bimbo, which surrounds the
# 71 km2 city (measured on the CGAZ polygons).
PLACED = {("bangui", "begoua"): ("ombellampoko", "bimbo")}

# Sub-prefecture names the boundary file spells otherwise, as the 2003 census
# writes them (car_prefecture's list) and as OCHA's table does -- Djemah,
# Dede-Makouba, and Bantangafo, a doubled letter. Keyed by the folded name.
SP_ALIASES = {fold(k): v for k, v in {
    "Aba": "Abba", "Bossemptele": "Bossemtélé", "Nanga-Boguila": "Nagha Boguila",
    "Ndjoukou": "Djoukou", "Djemah": "Djéma", "Dede-Makouba": "Dédé-Mokouba",
    "Bantangafo": "Batangafo"}.items()}


def spelled(name: str) -> str:
    """A sub-prefecture's name as the boundary file writes it."""
    return SP_ALIASES.get(fold(name), name)


# A polygon whose whole count is a figure the table also prints for another
# unit, so it cannot be taken for this ground's own: Dédé-Mokouba's one
# commune, Haute-Kadéi, has exactly Mobaye commune's 23,708 (Basse-Kotto), in
# both the Census Bureau's tabulation and OCHA's.
SUSPECT = {fold("Dédé-Mokouba"): (
    "The 2021 census mapping's table gives Haute-Kadéi, this sub-prefecture's one commune, "
    "exactly the count it gives Mobaye commune in Basse-Kotto (23,708 people), so the figure "
    "cannot be taken for this sub-prefecture's own and none is shown.")}

# The fixed proportion of men in every unit of the mapping table, and how far
# a unit may sit from it (rounding of whole people) before the table is taken
# to describe sexes after all.
FIXED_MALE_SHARE = 0.49
FIXED_SLACK = 0.0005

SEX_GAP = ("The 2021 census mapping's table splits every unit's count into men and women in "
           "one fixed proportion (49 to 51), so it gives no sex ratio of this sub-prefecture's "
           "own; the statistics office's 2016 estimates by sex stop at the prefecture.")
AGE_GAP = ("The statistics office's 2016 estimates by age stop at the 17 prefectures and its "
           "2021 mapping counts carry no ages, so no median age is published for the "
           "sub-prefecture.")
SEAT_GAP = ("No published list of the sub-prefectures' seats has been found, so none is "
            "shown; the census tables name the sub-prefectures and their communes, not their "
            "seats.")


def table(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """A USCB sheet as dicts keyed by its field-name row (row 0); row 1 is aliases."""
    names = ["" if v is None else str(v).strip() for v in rows[0]]
    return [{n: v for n, v in zip(names, row) if n} for row in rows[2:]
            if any(v not in (None, "") for v in row)]


def plain(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """An OCHA sheet: one header row."""
    names = ["" if v is None else str(v).strip() for v in rows[0]]
    return [{n: v for n, v in zip(names, row) if n} for row in rows[1:]
            if any(v not in (None, "") for v in row)]


def level(row: dict[str, Any]) -> int | None:
    value = number(row.get("ADM_LEVEL"))
    return int(value) if value is not None else None


def text(row: dict[str, Any], key: str) -> str:
    return " ".join(str(row.get(key) or "").split())


def prev_communes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OCHA's PrevCommune sheet: the 2021 count on each 2003 commune."""
    out = []
    for row in rows:
        total = number(row.get("T_TL"))
        if total is None or not text(row, "Pcode3"):
            continue
        out.append({"pref_code": text(row, "Pcode1"), "pref": text(row, "PrevPréfecture"),
                    "sp_code": text(row, "Pcode2"), "sp": text(row, "PrevSous-préfecture"),
                    "code": text(row, "Pcode3"), "name": text(row, "PrevCommune"),
                    "total": int(round(total)),
                    "men": number(row.get("M_TL")) or 0.0, "women": number(row.get("F_TL")) or 0.0})
    return out


def counts_2021(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The USCB Population sheet: the same count on the 2021 frame."""
    out: dict[str, Any] = {"country": None, "prefectures": {}, "sps": {}, "communes": []}
    for row in rows:
        figures = tuple(number(row.get(k)) for k in ("POP_BTOTL", "POP_MTOTL", "POP_FTOTL"))
        if any(f is None for f in figures):
            continue
        total, men, women = (int(f) for f in figures)
        unit = {"name": text(row, "AREA_NAME"), "pref": text(row, "ADM1_NAME"),
                "sp": text(row, "ADM2_NAME"), "total": total, "men": men, "women": women}
        lvl = level(row)
        if lvl == 0:
            out["country"] = unit
        elif lvl == 1:
            out["prefectures"][fold(unit["name"])] = unit
        elif lvl == 2:
            out["sps"][(fold(unit["pref"]), fold(unit["name"]))] = unit
        elif lvl == 3:
            out["communes"].append(unit)
    return out


def communes_2003(rows: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """(prefecture, sub-prefecture, commune), folded, from a 2003-vintage sheet."""
    return [(fold(text(r, "ADM1_NAME")), fold(text(r, "ADM2_NAME")), fold(text(r, "AREA_NAME")))
            for r in rows if level(r) == 3]


def own_crosswalk(c21: dict[str, Any], g03: list[tuple[str, str, str]]
                  ) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], list[str]]:
    """2003 (pref, sp) -> the 2021 communes it holds, by commune names; and what failed."""
    by_name: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    anywhere: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for pref, sp, commune in g03:
        by_name[(pref, commune)].append((pref, sp))
        anywhere[commune].append((pref, sp))
    placed: dict[int, tuple[str, str]] = {}
    for i, unit in enumerate(c21["communes"]):
        pref, name = fold(unit["pref"]), fold(unit["name"])
        if (pref, name) in PLACED:
            placed[i] = PLACED[(pref, name)]
            continue
        hits = by_name.get((NEW_PREFECTURES.get(pref, pref), name), [])
        if len(hits) != 1:
            hits = anywhere.get(name, []) if not hits else hits
        if len(hits) == 1:
            placed[i] = hits[0]
    problems: list[str] = []
    for i, unit in enumerate(c21["communes"]):
        if i in placed or not unit["total"]:
            continue
        key = (fold(unit["pref"]), fold(unit["sp"]))
        siblings = {placed[j] for j, u in enumerate(c21["communes"])
                    if j in placed and (fold(u["pref"]), fold(u["sp"])) == key}
        if len(siblings) == 1:
            placed[i] = siblings.pop()
        else:
            problems.append(f"{unit['name']} ({unit['sp']}, {unit['pref']}): no 2003 namesake "
                            f"and no one place for its siblings")
    held: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for i, key in sorted(placed.items()):
        held[key].append(c21["communes"][i])
    return dict(held), problems


def fixed_split(c21: dict[str, Any]) -> int:
    """How many units of the mapping table depart from the fixed 49:51 split."""
    off = 0
    for unit in [*c21["prefectures"].values(), *c21["sps"].values(), *c21["communes"]]:
        if unit["total"] and abs(unit["men"] / unit["total"] - FIXED_MALE_SHARE) > max(
                FIXED_SLACK, 1.5 / unit["total"]):
            off += 1
    return off


def age_table(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{prefecture (folded): {"groups": [[low, high, people]...], "men", "women"}}."""
    out: dict[str, dict[str, Any]] = {}
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
        men, women, total = (number(row.get(k)) for k in ("MTOTL", "FTOTL", "BTOTL"))
        if len(groups) != 16 or last is None or not men or not women or not total:
            continue
        groups.append([80, None, last])
        out[fold(text(row, "AREA_NAME"))] = {"name": text(row, "AREA_NAME"), "groups": groups,
                                             "men": men, "women": women, "total": total}
    return out


def own_structures(ages: dict[str, dict[str, Any]]) -> tuple[set[str], list[str]]:
    """The prefectures whose age proportions are their own, and the report."""
    whole: dict[tuple[int, Any], float] = defaultdict(float)
    for entry in ages.values():
        for low, high, people in entry["groups"]:
            whole[(low, high)] += people
    national = [[lo, hi, n] for (lo, hi), n in whole.items()]
    report: list[str] = []
    copied: set[str] = set()
    keys = sorted(ages)
    for k in keys:
        if same_structure(ages[k]["groups"], national):
            copied.add(k)
            report.append(f"  ages: {ages[k]['name']} carries the national proportions")
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if same_structure(ages[a]["groups"], ages[b]["groups"]):
                copied |= {a, b}
                report.append(f"  ages: {ages[a]['name']} and {ages[b]['name']} share one "
                              f"structure (within {COPY_TOLERANCE} points)")
    return set(keys) - copied, report


def ocha_workbook_url() -> str:
    body = http_json(f"{HDX_API}/package_show?id={OCHA_DATASET}")
    found = [r for r in body["result"].get("resources", [])
             if "cartocensitaire" in str(r.get("name") or "").lower()]
    if not found:
        raise SystemExit(f"car_census: {OCHA_DATASET} no longer carries the 2021 mapping table")
    return found[0]["url"]


def build(prev: list[dict[str, Any]], c21: dict[str, Any], g03: list[tuple[str, str, str]],
          ages: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]], ocha_url: str, uscb_url: str
          ) -> tuple[list[dict[str, Any]], list[str]]:
    report: list[str] = []

    def fail(message: str) -> None:
        """Stop, after printing what was found: the log is how a refusal is read."""
        for line in report:
            log(line)
        raise SystemExit(f"car_census: {message}")

    country = c21["country"]["total"] if c21.get("country") else None
    made = sum(c["total"] for c in prev)
    report.append(f"PrevCommune: {len(prev)} communes of the 2003 frame, {made:,} people; "
                  f"the national line {country:,}" if country else f"PrevCommune: {made:,}")
    if country is not None and made != country:
        fail(f"the 2003-frame communes make {made:,}, the country {country:,}")
    off = fixed_split(c21)
    units = len(c21["prefectures"]) + len(c21["sps"]) + len(c21["communes"])
    report.append(f"mapping table: {off} of {units} units depart from the fixed "
                  f"{FIXED_MALE_SHARE:.0%} share of men")
    if off > 0.05 * units:
        fail("the mapping table now gives units their own sexes; read its sex ratios instead "
             "of withholding them")
    # Duplicate figures, named for anyone reading the run.
    seen: dict[int, list[str]] = defaultdict(list)
    for c in prev:
        if c["total"] >= 1000:
            seen[c["total"]].append(f"{c['name']} ({c['sp']})")
    for total, names in sorted(seen.items()):
        if len(names) > 1:
            report.append(f"  the same count, {total:,}, for {' and '.join(names)}")

    # The assignment by commune names, from the Census Bureau's 2021 frame.
    placement, problems = own_crosswalk(c21, g03)
    report += [f"  crosswalk: {p}" for p in problems]
    if problems:
        fail(f"{len(problems)} communes of 2021 could not be placed on the 2003 frame")
    parents = {u["id"]: u["name"] for u in admin1}
    pref_poly = {fold(u["name"]): u for u in admin1}
    bangui1 = pref_poly.get("bangui")
    bangui2 = next((u for u in admin2 if bangui1 and u["parent"] == bangui1["id"]), None)

    def parent_name(pref: str) -> str:
        return pref_poly[fold(pref)]["name"] if fold(pref) in pref_poly else ""

    departments = {f"{p}/{s}": (spelled(s), parent_name(p)) for (p, s) in placement
                   if p != "bangui"}
    bound, missing = bind(departments, admin2, parents)
    report += [f"  not bound to a polygon: {m}" for m in missing]
    if missing:
        fail("sub-prefectures left without a polygon: " + ", ".join(missing))
    if bangui2:
        bound["bangui/bangui"] = bangui2["id"]
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key, sid in bound.items():
        groups[sid].append(tuple(key.split("/")))
    names_by_sid: dict[str, set[str]] = defaultdict(set)
    for pref, sp, commune in g03:
        if f"{pref}/{sp}" in bound:
            names_by_sid[bound[f"{pref}/{sp}"]].add(commune)

    # OCHA's own assignment of the same count to the 2003 communes, as a check.
    by_sp: dict[str, dict[str, Any]] = {}
    for c in prev:
        entry = by_sp.setdefault(c["sp_code"], {"name": c["sp"], "pref": c["pref"], "total": 0})
        entry["total"] += c["total"]
    ocha_departments = {code: (spelled(e["name"]), parent_name(e["pref"]))
                        for code, e in by_sp.items() if fold(e["pref"]) != "bangui"}
    ocha_bound, ocha_missing = bind(ocha_departments, admin2, parents)
    report += [f"  OCHA's table, not bound to a polygon: {m}" for m in ocha_missing]
    ocha_by_poly: dict[str, int] = defaultdict(int)
    for code, sid in ocha_bound.items():
        ocha_by_poly[sid] += by_sp[code]["total"]
    if bangui2:
        ocha_by_poly[bangui2["id"]] = sum(e["total"] for e in by_sp.values()
                                          if fold(e["pref"]) == "bangui")
    shapes2 = {u["id"]: u for u in admin2}
    totals = {sid: sum(u["total"] for key in keys for u in placement[key])
              for sid, keys in groups.items()}
    diff = {sid: ocha_by_poly.get(sid, 0) - totals[sid] for sid in totals
            if ocha_by_poly.get(sid, 0) != totals[sid]}
    unexplained = []
    for sid, d in diff.items():
        if d > 0:
            continue
        # OCHA lacks -d here: a commune of that count, filed by OCHA under a
        # polygon that has a commune of the same name and exactly d too many.
        found = None
        for key in groups[sid]:
            for u in placement[key]:
                if u["total"] != -d:
                    continue
                for other, e in diff.items():
                    if e == -d and fold(u["name"]) in names_by_sid.get(other, set()):
                        found = (u, other)
        if found:
            u, other = found
            report.append(f"  OCHA's table files {u['name'].title()} ({shapes2[sid]['name']}, "
                          f"{u['total']:,}) under {shapes2[other]['name']}'s commune of the same "
                          f"name; the names place it here")
        else:
            unexplained.append(sid)
    unexplained += [sid for sid, d in diff.items() if d > 0 and not any(
        e == -d for e in diff.values())]
    for sid in unexplained:
        report.append(f"  disagreement: {shapes2[sid]['name']}: OCHA's 2003 communes "
                      f"{ocha_by_poly.get(sid, 0):,}, the 2021 communes by name {totals[sid]:,}")
    if unexplained:
        fail(f"OCHA's assignment and the commune names disagree on {len(unexplained)} polygons "
             f"for no reason found")

    cite_count = [{"field": "population", "name": COUNT_SOURCE,
                   "url": f"https://data.humdata.org/dataset/{OCHA_DATASET}", "year": COUNT_YEAR,
                   "license": LICENCE},
                  {"field": "population", "name": COUNT_SOURCE_USCB,
                   "url": dataset_url(USCB_DATASET), "year": COUNT_YEAR, "license": LICENCE}]
    records: list[dict[str, Any]] = []
    pref_totals: dict[str, int] = defaultdict(int)
    for sid, keys in sorted(groups.items()):
        shape = shapes2[sid]
        units = [u for key in keys for u in placement[key]]
        total = totals[sid]
        pref_totals[keys[0][0]] += total
        sps21 = sorted({u["sp"].title() for u in units})
        whole = (len(sps21) == 1 and fold(sps21[0]) == keys[0][1]
                 and len(units) == sum(1 for u in c21["communes"]
                                       if fold(u["sp"]) == keys[0][1]
                                       and fold(u["pref"]) == fold(units[0]["pref"])))
        suspect = SUSPECT.get(fold(shape["name"]))
        if suspect:
            pop = gap(NOT_AVAILABLE, suspect)
            note = None
        elif not total:
            pop = gap(NOT_AVAILABLE, f"The 2021 census mapping counted no one in the communes "
                                     f"of {shape['name']}.")
            note = None
        else:
            pop = measure(total, year=COUNT_YEAR, source=COUNT_SOURCE_USCB)
            if whole:
                note = (f"The people counted in {shape['name']} at the mapping stage of the "
                        f"fourth general census (RGPH-4), 1 March 2021.")
            else:
                listed = ", ".join(f"{u['name'].title()} {u['total']:,}" for u in units)
                note = (f"The people counted at the mapping stage of the fourth general census "
                        f"(RGPH-4), 1 March 2021, on {shape['name']}'s ground as the 2003 census "
                        f"drew it, its communes added up ({listed})"
                        + (f"; since 2020 this ground is the sub-prefectures of "
                           f"{' and '.join(sps21)}." if len(sps21) > 1 else "."))
        records.append(record(
            f"CAF-RGPH4-{sid}", shape["name"], level="admin2", parent="CAF", country="CAF",
            match_by="shape_id", shape_id=sid, population=pop,
            **({"population_note": note} if note else {}),
            sex_ratio=gap(NOT_AVAILABLE, SEX_GAP), median_age=gap(NOT_AVAILABLE, AGE_GAP),
            capital=gap(NOT_AVAILABLE, SEAT_GAP), sources=cite_count))
        report.append(f"  {shape['name']}: {total:,} ({len(units)} communes of 2021"
                      + ("" if whole else f"; 2021 sub-prefectures {', '.join(sps21)}") + ")"
                      + (" -- withheld" if suspect else ""))


    own, why = own_structures(ages)
    report += why
    cite_age = [{"field": "median_age/sex_ratio", "name": AGE_SOURCE,
                 "url": dataset_url(USCB_DATASET), "year": AGE_YEAR, "license": LICENCE}]
    for key, poly in sorted(pref_poly.items()):
        total = pref_totals.get(key)
        if not total:
            report.append(f"  prefecture {poly['name']}: no 2021 count")
            continue
        fields: dict[str, Any] = {
            "population": measure(total, year=COUNT_YEAR, source=COUNT_SOURCE_USCB),
            "population_note": (f"The people counted in {poly['name']} at the mapping stage of "
                                f"the fourth general census (RGPH-4), 1 March 2021, on its ground "
                                f"as the 2003 census drew it: the sum of its sub-prefectures."),
            "sources": list(cite_count)}
        entry = ages.get(key)
        if entry:
            fields["sex_ratio"] = measure(round(1000 * entry["men"] / entry["women"]),
                                          unit="males_per_1000_females", year=AGE_YEAR,
                                          source=AGE_SOURCE)
            fields["sex_ratio_note"] = ("Men per 1,000 women in the statistics office's "
                                        "administrative population at 31 December 2016, an "
                                        "estimate rather than a count.")
            median = grouped_median([tuple(g) for g in entry["groups"]]) if key in own else None
            if median is not None:
                fields["median_age"] = {"value": median, "unit": "years", "year": AGE_YEAR,
                                        "source": AGE_SOURCE}
                fields["median_age_note"] = (
                    "Interpolated within the five-year age group that holds the middle person, "
                    "from the statistics office's administrative population by age at 31 "
                    "December 2016, an estimate rather than a count.")
            else:
                fields["median_age"] = gap(NOT_AVAILABLE, (
                    "The statistics office's 2016 estimates give this prefecture the same age "
                    "proportions as another prefecture or the country, so no median age of its "
                    "own can be taken from them."))
            fields["sources"] += cite_age
        records.append(record(f"CAF-RGPH4-{poly['id']}", poly["name"], level="admin1",
                              parent="CAF", country="CAF", match_by="shape_id",
                              shape_id=poly["id"], **fields))
        report.append(f"  prefecture {poly['name']}: {total:,}"
                      + (f"; 2016: {entry['men'] / entry['women'] * 1000:.0f} men per 1,000 "
                         f"women, median {fields['median_age'].get('value')}" if entry else ""))
    return records, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump", action="store_true", help="print the OCHA sheet's rows, write nothing")
    ap.add_argument("--run", help="a label that tells one dispatch from another; not used")
    args = ap.parse_args()
    import openpyxl                                  # noqa: PLC0415
    ocha_url = ocha_workbook_url()
    blob = http_get(ocha_url, binary=True, cache=False, timeout=300)
    log(f"car_census: {ocha_url}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    prev = prev_communes(plain(sheet_rows(book, "PrevCommune")))
    uscb_url = workbook_url(USCB_DATASET)
    ublob = http_get(uscb_url, binary=True, cache=False, timeout=300)
    log(f"car_census: {uscb_url}: {len(ublob):,} bytes, sha256 {hashlib.sha256(ublob).hexdigest()}")
    ubook = openpyxl.load_workbook(io.BytesIO(ublob), read_only=True, data_only=True)
    c21 = counts_2021(table(sheet_rows(ubook, "Population")))
    g03 = communes_2003(table(sheet_rows(ubook, "Ethnicity")))
    ages = age_table(table(sheet_rows(ubook, "Age-Sex")))
    if args.dump:
        for c in prev:
            log(f"  {c['pref_code']} {c['pref']} | {c['sp_code']} {c['sp']} | {c['code']} "
                f"{c['name']} | {c['total']}")
        for k, e in ages.items():
            log(f"  {e['name']}: {e['groups']}")
        return 0
    admin1 = json.loads((SITE / "admin1" / "CAF.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "CAF.units.json").read_text())
    records, report = build(prev, c21, g03, ages, admin1, admin2, ocha_url, uscb_url)
    for line in report:
        log(line)
    log(f"  {sum(r['level'] == 'admin1' for r in records)} prefectures and "
        f"{sum(r['level'] == 'admin2' for r in records)} sub-prefecture polygons written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
