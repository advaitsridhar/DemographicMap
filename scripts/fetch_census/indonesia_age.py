#!/usr/bin/env python3
"""Indonesia: population, median age and sex ratio by province and regency, 2020 census Long Form.

Statistics Indonesia (BPS) answers this project's reader 403 on every host it
owns (docs/SOURCES.md). Its figures reach the map through the US Census
Bureau's "Subnational Population and Housing Data Tables" for Indonesia on
HDX (CC BY), whose workbook carries an ``Age-Sex`` sheet from *The Result of
Long Form Population Census 2020* (BPS, 2023), Table 3.1: everyone by sex
and five-year age group to an open 75+, for the country, the 34 provinces
and every kabupaten and kota (``ADM_LEVEL`` 0, 1 and 2).

**Which year.** The Long Form was BPS's sample-based second stage of the
2020 census, carried out in 2022, and its weights carry BPS's population for
mid-2022: the country's row is 275,773,774, which is BPS's projection for
2022 (275,773.8 thousand), not the census-day count of September 2020
(270,203,917). So 2022 is the year written here, although the Bureau's data
dictionary dates every field to the census day of 15 September 2020; each
record's note says both.

**Binding.** A province binds the map's first-level polygon of its name
(``indonesia.PROVINCES`` holds the Indonesian names and spellings). A
kabupaten binds the polygon of its name inside its province's polygon
(without the word "Kabupaten"; a kota keeps "Kota", as the boundary file
writes it). Four regencies were renamed after the boundary file was drawn,
and one city is spelled apart; they bind by ``RENAMED``, each the same
territory under another name. Every
row binds one polygon and every polygon of the province one row, except the
Thousand Islands (``NO_POLYGON``: the boundary file draws neither them nor any
sea north of Jakarta) and the shapes that are lakes, reservoirs and a forest
(``NOT_REGENCIES``). No regency was split or merged between the boundary
file's units and the census's: Indonesia has had the same 514 kabupaten and
kota since 2014, and the one-to-one binding checks it.

A province's figures are its own row: the province, Jakarta included with the
Thousand Islands it governs (some 28,000 people), whose polygon the map draws
without them.

Median age is interpolated within the five-year group holding the middle
person; the sex ratio is men per 100 women; population is the Long Form's
weighted total for 2022, which is BPS's own figure and replaces an
encyclopaedia's on the map (a newer register count still stands in front of
it, by date).

**Checks**, each a refusal: in every row the age groups make the total for
both sexes and each, and men and women make both sexes in every group; the
regencies make their province's row, group by group and sex by sex; the
provinces make the country's, which must be BPS's 275,773,774.

Usage:
    python -m scripts.fetch_census.indonesia_age
"""

from __future__ import annotations

import argparse
import io
import re
from collections import defaultdict
from typing import Any

from . import indonesia, uscb
from ._shared import (NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, gap, http_get, log, record,
                      write_json)
from .sea_common import age_sex, check_runs, drawn, fold, grouped

OUT = "indonesia_age.json"
DATASET = "indonesia-subnational-population-and-housing-data-tables"
YEAR = 2022
SOURCE = ("BPS-Statistics Indonesia, The Result of Long Form Population Census 2020 (2023), "
          "Table 3.1: Population by Age Group, Urban/Rural Area, and Sex, as the U.S. Census "
          "Bureau tabulates it for HDX")
LICENCE = "CC BY, published via HDX"
NATIONAL = 275_773_774
SEXES = ("B", "M", "F")
GROUP = re.compile(r"^(?P<sex>[BMF])(?P<lo>\d{2})(?:(?P<hi>\d{2})|PL)$")
# Regencies renamed after the boundary file was drawn, or spelled apart, each
# the same territory: the census's name (folded, without "Kabupaten") -> the
# boundary file's. Toba Samosir became Toba in 2020, Mamuju Utara became
# Pasangkayu in 2017 and Maluku Tenggara Barat became Kepulauan Tanimbar in
# 2019; Siau Tagulandang Biaro has been "Kepulauan Siau Tagulandang Biaro"
# since it was formed in 2007, and the boundary file drops the "Kepulauan".
# North Sumatra's city of Padangsidimpuan is "Padang Sidempuan" in the
# Bureau's table, the older spelling of the same name: it was the province's
# only row left without a polygon by name, and its polygon the only one left
# without a row.
RENAMED: dict[str, str] = {
    "toba": "Toba Samosir",
    "pasangkayu": "Mamuju Utara",
    "kepulauantanimbar": "Maluku Tenggara Barat",
    "kepulauansiautagulandangbiaro": "Siau Tagulandang Biaro",
    "kotapadangsidempuan": "Kota Padangsidimpuan",
}
# Rows with no polygon: (province, regency key).
NO_POLYGON = frozenset({("JAKARTA", "kepulauanseribu")})
# Drawn second-level shapes that are lakes, reservoirs and a forest; indonesia.py
# and the build's water declaration say what each is.
NOT_REGENCIES = frozenset({"danau", "danautoba", "hutan", "wadukcirata", "wadungkedungombo"})
# The forest is land, so the build's water declaration does not reach it, and
# indonesia.py says why it has no people or composition but not why it has no
# ages: said here.
FOREST = "hutan"
FOREST_GAP = (
    "This shape is a forest, not a regency, and nobody lives in it: the boundary file draws "
    "it at the same level as Indonesia's regencies and cities, and UN OCHA's population "
    "dataset for the same boundaries names it among the seventeen uninhabited features it "
    "gives no population. With nobody in it there are no ages or sexes to count, and the "
    "2020 census Long Form's table of ages by regency (Table 3.1) has no row for it.")
# Why a regency has no ethnicity, and why one of the few without a religion
# has none: said on every regency this reader binds, and shown only where no
# figure stands (a gap never displaces a value).
ETHNICITY_GAP = (
    "Indonesia's 2010 census asked ethnicity (suku bangsa) and BPS published it by province, "
    "which is what the map's provinces carry; no table of it by regency could be read here: "
    "BPS answers this project's reader HTTP 403 on every bps.go.id host, and its 2010 census "
    "site (sp2010.bps.go.id) serves one identical page at every address. The 2020 census's "
    "tables that reach the regencies -- the Long Form's age, household, language, mortality, "
    "disability and migration tables -- have no ethnicity.")
RELIGION_GAP = (
    "No table of this regency's religion could be read. BPS answers this project's reader "
    "HTTP 403 on every bps.go.id host, and neither the regency's own nor its province's "
    "open-data portal publishes one (docs/SOURCES.md, \"Indonesia: what BPS's refusal left "
    "reachable\", lists the 110 portals tried). The 2020 census's Long Form tables that "
    "reach the regencies have no religion.")
# Why a regency or province has no language, said wherever no composition
# stands: the Long Form's first-language table (indonesia_language) is kinds
# of language, and a survey that fills only if the build reads it.
LANGUAGE_GAP = (
    "No count of this {unit}'s languages could be read. The 2010 census's household language "
    "reaches the map through CLEAR Global's tabulation of its IPUMS sample, for some units "
    "only; BPS answers this project's reader HTTP 403 on every bps.go.id host; and the 2020 "
    "census asked language only in its Long Form, a 2022 sample, which counts the language a "
    "person first learned in four kinds -- Indonesian, a regional language, a foreign language "
    "and sign language (Table 6.3 of its 2023 results) -- and not language by language.")
KIND = re.compile(r"^(?:KABUPATEN|KAB\.?)\s+(?:ADMINISTRASI\s+|ADM\.?\s+)?", re.IGNORECASE)
CITY = re.compile(r"^KOTA\s+(?:ADMINISTRASI\s+|ADM\.?\s+)?", re.IGNORECASE)


def key(name: str) -> str:
    """'KABUPATEN SIMEULUE' -> 'simeulue'; 'KOTA ADMINISTRASI JAKARTA BARAT' -> 'kotajakartabarat'."""
    text = str(name or "").strip()
    if CITY.match(text):
        return "kota" + fold(CITY.sub("", text))
    return fold(KIND.sub("", text))


def count(value: Any, where: str) -> int:
    n = uscb.number(value)
    if n is None or not float(n).is_integer():
        raise SystemExit(f"indonesia_age: {where}: {value!r} is not a count of people")
    return int(n)


def read_rows(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Every row's level, names and {sex: {(lo, hi): count}}, its sums checked."""
    names, _ = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    cols: dict[str, dict[tuple[int, int | None], int]] = {s: {} for s in SEXES}
    for name, i in at.items():
        if m := GROUP.match(name):
            hi = int(m.group("hi")) if m.group("hi") else None
            cols[m.group("sex")][(int(m.group("lo")), hi)] = i
    if any(set(cols[s]) != set(cols["B"]) for s in SEXES) or len(cols["B"]) < 10:
        raise SystemExit(f"indonesia_age: the Age-Sex sheet's groups are not one set per sex: "
                         f"{ {s: len(c) for s, c in cols.items()} }")
    check_runs([(lo, hi, 0) for lo, hi in cols["B"]], "indonesia_age: the Age-Sex sheet")
    out = []
    for row in rows[2:]:
        level = uscb.number(row[at["ADM_LEVEL"]])
        if level is None:
            continue
        level = int(level)
        unit = {"level": level,
                "adm1": str(row[at["ADM1_NAME"]] or "").strip() if level >= 1 else "",
                "adm2": str(row[at["ADM2_NAME"]] or "").strip() if level >= 2 else "",
                "nso": str(row[at["NSO_NAME"]] or "").strip() if "NSO_NAME" in at else "",
                "code": str(row[at["NSO_CODE"]] or "").strip() if "NSO_CODE" in at else ""}
        where = unit["adm2"] or unit["adm1"] or "the country"
        cells = [row[at[t]] for t in ("BTOTL", "MTOTL", "FTOTL")] + [
            row[i] for s in SEXES for i in cols[s].values()]
        if level == 2 and all(c is None or str(c).strip() == "" for c in cells):
            # The Bureau lists Lake Toba among the regencies with every cell
            # blank; a row with no figures at all is carried as such, and
            # build() requires it to be a shape that is no regency.
            unit["groups"] = None
            out.append(unit)
            continue
        unit["groups"] = {s: {b: count(row[i], f"{where} {s}{b}") for b, i in cols[s].items()}
                          for s in SEXES}
        for s, total in (("B", "BTOTL"), ("M", "MTOTL"), ("F", "FTOTL")):
            made = sum(unit["groups"][s].values())
            stated = count(row[at[total]], f"{where} {total}")
            if made != stated:
                raise SystemExit(f"indonesia_age: {where}: the {s} groups make {made:,}, "
                                 f"against {stated:,}")
        g = unit["groups"]
        for b in cols["B"]:
            if g["M"][b] + g["F"][b] != g["B"][b]:
                raise SystemExit(f"indonesia_age: {where} {b}: men and women make "
                                 f"{g['M'][b] + g['F'][b]:,}, against {g['B'][b]:,}")
        out.append(unit)
    return out


def add(units: list[dict[str, Any]]) -> dict[str, dict[tuple[int, int | None], int]]:
    out: dict[str, dict[tuple[int, int | None], int]] = {s: defaultdict(int) for s in SEXES}
    for u in units:
        for s in SEXES:
            for b, v in u["groups"][s].items():
                out[s][b] += v
    return {s: dict(v) for s, v in out.items()}


def check_sums(rows: list[dict[str, Any]]) -> None:
    """Regencies make their province, and provinces the country, group by group."""
    country = [r for r in rows if r["level"] == 0]
    provinces = [r for r in rows if r["level"] == 1]
    regencies = [r for r in rows if r["level"] == 2 and r["groups"] is not None]
    blank = [r["adm2"] for r in rows if r["level"] == 2 and r["groups"] is None]
    strange = [n for n in blank if key(n) not in NOT_REGENCIES]
    if strange or any(r["groups"] is None for r in country + provinces):
        raise SystemExit(f"indonesia_age: rows with no figures that are not water: {strange}")
    if blank:
        log(f"  rows with every cell blank, shapes that are no regency: {', '.join(blank)}")
    if len(country) != 1 or sum(country[0]["groups"]["B"].values()) != NATIONAL:
        raise SystemExit(f"indonesia_age: the country's row is not BPS's {NATIONAL:,}")
    if len(provinces) != len(indonesia.PROVINCES):
        raise SystemExit(f"indonesia_age: {len(provinces)} provinces, against the map's "
                         f"{len(indonesia.PROVINCES)}")
    for whole, parts, what in (
            [(country[0], provinces, "the provinces")]
            + [(p, [r for r in regencies if fold(r["adm1"]) == fold(p["adm1"])],
                f"{p['adm1']}'s regencies") for p in provinces]):
        if not parts or add(parts) != whole["groups"]:
            raise SystemExit(f"indonesia_age: {what} do not make "
                             f"{whole['adm1'] or 'the country'} group by group")
    orphans = [r["adm2"] for r in regencies
               if fold(r["adm1"]) not in {fold(p["adm1"]) for p in provinces}]
    if orphans:
        raise SystemExit(f"indonesia_age: regencies under no province row: {orphans}")
    log(f"  {len(regencies)} regencies make their {len(provinces)} provinces and the provinces "
        f"the country's {NATIONAL:,}, group by group and sex by sex")


def provinces_of(admin1: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """fold(any Indonesian name of a province) -> the map's polygon."""
    by_name = {u["name"]: u for u in admin1}
    out: dict[str, dict[str, Any]] = {}
    for english, (title, aliases) in indonesia.PROVINCES.items():
        if english not in by_name:
            raise SystemExit(f"indonesia_age: no polygon named {english!r}")
        for n in (english, title, *aliases):
            out[fold(n)] = by_name[english]
    return out


def keys_of(row: dict[str, Any]) -> list[str]:
    """The keys a regency row may be found under: its names, renamed where they were."""
    out = []
    for name in (row["adm2"], row["nso"]):
        k = key(name)
        if k:
            out.append(fold(RENAMED[k]) if k in RENAMED else k)
    return out


def bind(rows: list[dict[str, Any]], admin1: list[dict[str, Any]],
         admin2: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Polygon id -> its regency row; and province polygon id -> its province row."""
    provinces = provinces_of(admin1)
    regions: dict[str, dict[str, Any]] = {}
    for r in (r for r in rows if r["level"] == 1):
        poly = provinces.get(fold(r["adm1"]))
        if poly is None or poly["id"] in regions:
            raise SystemExit(f"indonesia_age: the province {r['adm1']!r} binds "
                             f"{'no' if poly is None else 'a second'} polygon")
        regions[poly["id"]] = r
    bound: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    skipped = []
    for pid, prov in regions.items():
        shapes = [s for s in admin2 if s["parent"] == pid and fold(s["name"]) not in NOT_REGENCIES]
        by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for s in shapes:
            by_key[fold(s["name"])].append(s)
        rows_here = [r for r in rows if r["level"] == 2 and r["groups"] is not None
                     and fold(r["adm1"]) == fold(prov["adm1"])]
        left_rows = []
        for r in rows_here:
            if any((prov["adm1"].upper(), k) in NO_POLYGON for k in keys_of(r)):
                skipped.append(r["adm2"])
                continue
            hits = {s["id"]: s for k in keys_of(r) for s in by_key.get(k, [])}
            if len(hits) != 1 or next(iter(hits)) in bound:
                left_rows.append(f"{r['adm2']} [{r['nso']}] ({len(hits)} polygons)")
                continue
            bound[next(iter(hits))] = r
        left_shapes = sorted(s["name"] for s in shapes if s["id"] not in bound)
        if left_rows or left_shapes:
            problems.append(f"{prov['adm1']}: rows {left_rows}; polygons {left_shapes}")
    stray = [s["name"] for s in admin2 if s["parent"] not in regions
             and fold(s["name"]) not in NOT_REGENCIES]
    if stray:
        problems.append(f"polygons under no bound province: {stray}")
    if problems:
        for p in problems:
            log(f"    {p}")
        raise SystemExit(f"indonesia_age: {len(problems)} provinces with rows or polygons "
                         f"left over")
    log(f"  {len(bound)} regencies bound one to one inside their provinces; no polygon for "
        f"{', '.join(skipped)}")
    return bound, regions


def said(whose: str) -> str:
    return (f"BPS's Long Form of the 2020 census, carried out in 2022, for {whose} (Table 3.1 of "
            f"its 2023 results, as the US Census Bureau tabulates it; the Bureau's dictionary "
            f"dates the field to the census day, 15 September 2020, but the weights carry BPS's "
            f"population for 2022)")


def fields(groups: dict[str, dict[tuple[int, int | None], int]], whose: str) -> dict[str, Any]:
    median = grouped([(lo, hi, n) for (lo, hi), n in groups["B"].items()])
    men, women = sum(groups["M"].values()), sum(groups["F"].values())
    if median is None or not women:
        raise SystemExit(f"indonesia_age: {whose}: no median below 75, or no women")
    text = said(whose)
    return age_sex(median=median, men=men, women=women, year=YEAR, source=SOURCE,
                   median_note=(f"Interpolated within the five-year age group that holds the "
                                f"middle person (the finest the table publishes), from {text}."),
                   ratio_note=f"Males per 100 females in {text}.",
                   population=sum(groups["B"].values()),
                   population_note=f"The Long Form's weighted total for 2022: {text}.")


def build(rows: list[dict[str, Any]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    check_sums(rows)
    bound, regions = bind(rows, admin1, admin2)
    cite = {"field": "population/median_age/sex_ratio", "name": SOURCE,
            "url": uscb.dataset_url(DATASET), "year": YEAR, "license": LICENCE}
    shapes = {s["id"]: s for s in admin2}
    out = []
    for sid, r in sorted(bound.items(), key=lambda kv: shapes[kv[0]]["name"]):
        shape = shapes[sid]
        whose = r["nso"].title() if r["nso"] else r["adm2"].title()
        out.append(record(
            f"IDN-LF-{r['code'] or key(r['adm2'])}", shape["name"], level="admin2",
            parent="IDN", country="IDN", match_by="shape_id", shape_id=sid,
            religion=gap(NOT_AVAILABLE, RELIGION_GAP),
            ethnicity=gap(NOT_AVAILABLE, ETHNICITY_GAP),
            language=gap(NOT_AVAILABLE, LANGUAGE_GAP.format(unit="regency")),
            sources=[cite], **fields(r["groups"], whose)))
    for shape in (s for s in admin2 if fold(s["name"]) == FOREST):
        out.append(record(f"IDN-LF-{FOREST}", shape["name"], level="admin2", parent="IDN",
                          country="IDN", match_by="shape_id", shape_id=shape["id"],
                          median_age=gap(NOT_COLLECTED, FOREST_GAP),
                          sex_ratio=gap(NOT_COLLECTED, FOREST_GAP)))
    for pid, prov in sorted(regions.items(), key=lambda kv: kv[1]["adm1"]):
        region = next(u for u in admin1 if u["id"] == pid)
        whose = f"the province of {prov['adm1'].title()}"
        if pid == next(u["id"] for u in admin1 if u["name"] == "Jakarta Special Capital Region"):
            whose += (" (its own row, which counts the Thousand Islands, Kepulauan Seribu, that "
                      "the map does not draw)")
        out.append(record(f"IDN-LF-{prov['code'] or fold(prov['adm1'])}", region["name"],
                          level="admin1", parent="IDN", country="IDN", match_by="shape_id",
                          shape_id=pid, sources=[cite],
                          language=gap(NOT_AVAILABLE, LANGUAGE_GAP.format(unit="province")),
                          **fields(prov["groups"], whose)))
    country = next(r for r in rows if r["level"] == 0)
    national = grouped([(lo, hi, n) for (lo, hi), n in country["groups"]["B"].items()])
    log(f"  the country: median {national}, sex ratio "
        f"{round(100 * sum(country['groups']['M'].values()) / sum(country['groups']['F'].values()), 1)}")
    for level in ("admin1", "admin2"):
        meds = sorted(r["median_age"]["value"] for r in out
                      if r["level"] == level and "value" in r["median_age"])
        rats = sorted(r["sex_ratio"]["value"] for r in out
                      if r["level"] == level and "value" in r["sex_ratio"])
        log(f"  {level}: {len(meds)} units; median {meds[0]}-{meds[-1]}; "
            f"sex ratio {rats[0]}-{rats[-1]}")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import openpyxl
    log(f"indonesia_age: {SOURCE}")
    url = uscb.workbook_url(DATASET)
    log(f"  {url}")
    book = openpyxl.load_workbook(io.BytesIO(http_get(url, binary=True, cache=False)),
                                  read_only=True, data_only=True)
    rows = read_rows(uscb.sheet_rows(book, "Age-Sex"))
    book.close()
    records = build(rows, drawn("IDN", "admin1"), drawn("IDN", "admin2"))
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
