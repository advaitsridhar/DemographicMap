#!/usr/bin/env python3
"""Saint Vincent and the Grenadines: the 2012 and 2023 censuses, summed into parishes.

The Statistical Office tabulates both censuses by its thirteen census
divisions (Kingstown, Suburbs of Kingstown, Calliaqua, ... Southern
Grenadines); the map draws the six parishes. Nothing the office publishes is
by parish, but the US Census Bureau's HDX workbook of the 2012 census gives
every enumeration district (221 of them, some of the office's 333 joined) with
the parish it lies in, as the office's own geography records it. So:

* **2012, by parish**: the workbook's enumeration districts summed by their
  PARISH column -- sex and five-year age group (sheet Age-Sex), and ethnicity
  and religion (sheet Ethnicity and Religion). Every district's age groups,
  sexes, ethnic groups and religions make its total; the districts make their
  census division's row and the country's, 109,188.
* **2023, by parish where the divisions allow it**: Table 2-6 of the 2023
  census report, the household population of each census division by major
  ethnic group. A division whose enumeration districts all lie in one parish
  belongs to that parish; a parish made wholly of such divisions takes the
  2023 population and ethnicity, summed. A division split between parishes
  gives none, and its parishes keep 2012's.

Median age is interpolated within the five-year group holding the middle
person; the sex ratio is men per thousand women; both 2012.

Neither census's tables have a language: the 2012 REDATAM base's dictionary
(SVG2012) holds no language variable, and the 2023 report tabulates none.

Usage:
    python -m scripts.fetch_census.vincent_census
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter, defaultdict
from typing import Any

from . import uscb
from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, write_json
from .binding import fold
from .caribbean_uscb import GROUP, OPEN, number
from .cod_ps_age import grouped_median

OUT = PROCESSED / "vincent_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
DATASET = "saint-vincent-and-the-grenadines-subnational-boundaries-and-tabular-data"
REPORT = "https://stats.gov.vc/wp-content/uploads/2026/05/SVG-2023-Census-Report.pdf"
SOURCE_2012 = ("Statistical Office of Saint Vincent and the Grenadines, 2012 Population and "
               "Housing Census, by enumeration district with its parish, as the US Census "
               "Bureau tabulates it for HDX")
SOURCE_2023 = ("Statistical Office of Saint Vincent and the Grenadines, Population and Housing "
               "Census 2023 report, Table 2-6: Total Household Population by Census Division "
               "and Major Ethnic Group")
NATIONAL_2012 = 109_188
HOUSEHOLD_2023 = 108_764
DIVISIONS = ("Kingstown", "Suburbs of Kingstown", "Calliaqua", "Marriaqua", "Bridgetown",
             "Colonarie", "Georgetown", "Sandy Bay", "Layou", "Barrouallie", "Chateaubelair",
             "Northern Grenadines", "Southern Grenadines")
ETHNIC_2023 = ("African descent", "Indigenous", "White", "East Indian", "Mixed", "Portuguese",
               "Other", "Not stated")
ETHNIC_2012 = {"ETH_BLK": "African descent", "ETH_INDG": "Indigenous", "ETH_WHT": "White",
               "ETH_EIND": "East Indian", "ETH_MIX": "Mixed", "ETH_POR": "Portuguese",
               "ETH_OTHR": "Other"}
RELIGION_2012 = {
    "RLG_ANG": "Anglican", "RLG_EVC": "Evangelical", "RLG_MTH": "Methodist",
    "RLG_PTC": "Pentecostal", "RLG_PBT": "Presbyterian", "RLG_RMC": "Roman Catholic",
    "RLG_SALV": "Salvation Army", "RLG_SDA": "Seventh-day Adventist",
    "RLG_JVW": "Jehovah's Witnesses", "RLG_BPT": "Baptist", "RLG_HIN": "Hindu",
    "RLG_MOR": "Mormon", "RLG_MSL": "Muslim", "RLG_RASTA": "Rastafarian",
    "RLG_TRAD": "Traditional religion", "RLG_WORL": "No religion",
    "RLG_OTHR": "Other religion", "RLG_NSTA": "Not stated",
}
LANGUAGE_GAP = ("The 2012 census asks no language question -- its REDATAM base's dictionary "
                "(SVG2012) holds no language variable -- and the 2023 report tabulates none.")
NUMBER = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+)$")


def text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


# -- 2012: the workbook ---------------------------------------------------------

def districts(rows: list[list[Any]], sheet: str) -> tuple[dict[str, int], list[dict[str, Any]],
                                                        dict[str, Any]]:
    """(column index, enumeration district rows, the country's row) of one sheet."""
    names, _ = uscb.columns(rows)
    at = {n: i for i, n in enumerate(names) if n}
    eds, country, divisions = [], None, {}
    for row in rows[2:]:
        level = number(row[at["ADM_LEVEL"]])
        if level == 0:
            country = row
        elif level == 1:
            divisions[fold(text(row[at["AREA_NAME"]]))] = row
        elif level == 2:
            eds.append({"name": text(row[at["AREA_NAME"]]),
                        "division": text(row[at["ADM1_NAME"]]),
                        "parish": text(row[at["PARISH"]]), "row": row})
    if country is None or not eds:
        raise SystemExit(f"vincent_census: sheet {sheet} has no country row or no districts")
    return at, eds, {"country": country, "divisions": divisions}


def check_parts(at: dict[str, int], eds: list[dict], whole: dict[str, Any], column: str,
                sheet: str) -> None:
    """The districts make their division's row, and the divisions the country's."""
    by_division = Counter()
    for ed in eds:
        by_division[fold(ed["division"])] += number(ed["row"][at[column]])
    for key, row in whole["divisions"].items():
        if by_division.get(key) != number(row[at[column]]):
            raise SystemExit(f"vincent_census: {sheet}: {key}'s districts make "
                             f"{by_division.get(key)}, its row {number(row[at[column]])}")
    total = number(whole["country"][at[column]])
    if sum(by_division.values()) != total or total != NATIONAL_2012:
        raise SystemExit(f"vincent_census: {sheet}: the districts make "
                         f"{sum(by_division.values()):,}; the country row is {total:,}")


def ages_by_parish(rows: list[list[Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, set]]:
    """({parish: {groups, men, women, total}}, {division: its parishes}) from Age-Sex."""
    at, eds, whole = districts(rows, "Age-Sex")
    check_parts(at, eds, whole, "BTOTL", "Age-Sex")
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"groups": Counter(), "men": 0,
                                                          "women": 0, "total": 0})
    spread: dict[str, set] = defaultdict(set)
    for ed in eds:
        row, unit = ed["row"], out[ed["parish"]]
        if not ed["parish"]:
            raise SystemExit(f"vincent_census: district {ed['name']} names no parish")
        spread[fold(ed["division"])].add(ed["parish"])
        made = 0
        for name, i in at.items():
            closed, open_ = GROUP.match(name), OPEN.match(name)
            match = closed or open_
            if not match or match.group(1) != "B":
                continue
            low = int(match.group(2))
            high = int(closed.group(3)) if closed else None
            unit["groups"][(low, high)] += number(row[i])
            made += number(row[i])
        total, men, women = (number(row[at[c]]) for c in ("BTOTL", "MTOTL", "FTOTL"))
        unstated = number(row[at["B_UNSTATED"]]) if "B_UNSTATED" in at else 0
        if made + unstated != total or men + women != total:
            raise SystemExit(f"vincent_census: {ed['name']}: ages make {made + unstated:,} and "
                             f"sexes {men + women:,} of {total:,}")
        unit["men"] += men
        unit["women"] += women
        unit["total"] += total
    return dict(out), dict(spread)


def compositions_by_parish(rows: list[list[Any]]) -> dict[str, dict[str, Counter]]:
    """{parish: {"ethnicity": Counter, "religion": Counter, "total": n}} from the sheet."""
    at, eds, whole = districts(rows, "Ethnicity and Religion")
    check_parts(at, eds, whole, "ETH_TPOP", "Ethnicity and Religion")
    for column in list(ETHNIC_2012) + list(RELIGION_2012):
        if column not in at:
            raise SystemExit(f"vincent_census: the workbook has no column {column}")
    known = set(ETHNIC_2012) | set(RELIGION_2012)
    extra = [n for n in at if n.startswith(("ETH_", "RLG_")) and n not in known | {"ETH_TPOP"}]
    if extra:
        raise SystemExit(f"vincent_census: columns this does not read: {extra}")
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"ethnicity": Counter(),
                                                          "religion": Counter(), "total": 0})
    for ed in eds:
        row, unit = ed["row"], out[ed["parish"]]
        total = number(row[at["ETH_TPOP"]])
        for what, labels in (("ethnicity", ETHNIC_2012), ("religion", RELIGION_2012)):
            counts = {label: number(row[at[c]]) for c, label in labels.items()}
            if sum(counts.values()) != total:
                raise SystemExit(f"vincent_census: {ed['name']}'s {what} make "
                                 f"{sum(counts.values()):,} of {total:,}")
            unit[what].update(counts)
        unit["total"] += total
    return dict(out)


# -- 2023: the report -----------------------------------------------------------

def division_of(words: str) -> str | None:
    """The census division a row's gathered words end with, the longest name first."""
    for name in sorted(DIVISIONS + ("Total",), key=len, reverse=True):
        if fold(words).endswith(fold(name)):
            return name
    return None


def table_2_6(lines: list[str]) -> dict[str, dict[str, int]]:
    """{division: {group: people, "_total": n}} from Table 2-6, after its checks.

    A division's name can wrap onto the line above its figures ("Suburbs of" /
    "Kingstown 14,057 ..."), so the words since the last row are gathered and
    the row is the division they end with.
    """
    out: dict[str, dict[str, int]] = {}
    words: list[str] = []
    for line in lines:
        tokens = line.split()
        if len(tokens) > 9 and all(NUMBER.match(t) for t in tokens[-9:]):
            label = " ".join(words + tokens[:-9])
            words = []
            name = division_of(label)
            if name is None:
                raise SystemExit(f"vincent_census: Table 2-6 row {label!r} is no division")
            numbers = [int(t.replace(",", "")) for t in tokens[-9:]]
            if sum(numbers[:8]) != numbers[8]:
                raise SystemExit(f"vincent_census: Table 2-6's {name} makes "
                                 f"{sum(numbers[:8]):,} of {numbers[8]:,}")
            out[name] = dict(zip(ETHNIC_2023, numbers[:8])) | {"_total": numbers[8]}
            if name == "Total":
                break
        elif tokens:
            words += tokens
    total = out.pop("Total", None)
    if total is None or total["_total"] != HOUSEHOLD_2023 or set(out) != set(DIVISIONS):
        raise SystemExit(f"vincent_census: Table 2-6 has {sorted(out)} and total "
                         f"{total and total['_total']}")
    for group in ETHNIC_2023 + ("_total",):
        if sum(d[group] for d in out.values()) != total[group]:
            raise SystemExit(f"vincent_census: Table 2-6's divisions do not make its "
                             f"{group} total")
    return out


def report_table() -> list[str]:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(http_get(REPORT, binary=True, cache=False))) as pdf:
        for page in pdf.pages:
            lines = (page.extract_text() or "").splitlines()
            # The list of tables names it too, with a dotted leader to its page.
            start = next((i for i, l in enumerate(lines)
                          if l.startswith("Table 2-6 Total Household Population by Census")
                          and not re.search(r"\.{4,}", l)), None)
            if start is not None and any(re.match(r"^Kingstown [\d,]+ ", l)
                                         for l in lines[start + 1:]):
                return lines[start + 1:]
    raise SystemExit("vincent_census: the 2023 report has no Table 2-6")


# -- writing ----------------------------------------------------------------------

def parishes_2023(spread: dict[str, set], divisions: dict[str, dict[str, int]]
                  ) -> dict[str, dict[str, int]]:
    """{parish: 2023 counts} for the parishes made wholly of undivided divisions."""
    whole: dict[str, dict[str, int]] = defaultdict(Counter)
    split = set()
    for name, counts in divisions.items():
        parishes = spread.get(fold(name), set())
        if len(parishes) != 1:
            split |= parishes
            log(f"  2023: {name} spans {sorted(parishes)}; its figures go to no parish")
            continue
        whole[next(iter(parishes))].update(counts)
    return {p: dict(c) for p, c in whole.items() if p not in split}


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    import openpyxl
    blob = http_get(uscb.workbook_url(DATASET), binary=True, cache=False)
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    meta = " ".join(str(c) for r in uscb.sheet_rows(book, "Data Dictionary") for c in r if c)
    if "2012 Population and Housing Census" not in meta:
        raise SystemExit("vincent_census: the workbook never names the 2012 census")
    ages, spread = ages_by_parish(uscb.sheet_rows(book, "Age-Sex"))
    comps = compositions_by_parish(uscb.sheet_rows(book, "Ethnicity and Religion"))
    for division, parishes in sorted(spread.items()):
        log(f"  2012: {division}'s enumeration districts lie in {sorted(parishes)}")
    divisions = table_2_6(report_table())
    recent = parishes_2023(spread, divisions)

    admin1 = json.loads((SITE / "admin1" / "VCT.units.json").read_text())
    shapes = {fold(u["name"]): u for u in admin1}
    if set(ages) != set(comps) or {fold(p) for p in ages} != set(shapes):
        raise SystemExit(f"vincent_census: parishes {sorted(ages)} against the map's "
                         f"{sorted(u['name'] for u in admin1)}")
    records = []
    for parish in sorted(ages):
        shape = shapes[fold(parish)]
        a, c = ages[parish], comps[parish]
        if a["total"] != c["total"]:
            raise SystemExit(f"vincent_census: {parish}: {a['total']:,} by age, "
                             f"{c['total']:,} by ethnicity")
        groups = sorted(((lo, hi, n) for (lo, hi), n in a["groups"].items()),
                        key=lambda g: g[0])
        new = recent.get(parish)
        fields: dict[str, Any] = {}
        if new:
            fields.update(
                population=measure(new["_total"], year=2023, source=SOURCE_2023),
                population_note=("The 2023 census's household population of the census "
                                 "divisions that make the parish."),
                ethnicity=shares({g: new[g] for g in ETHNIC_2023}), ethnicity_year=2023,
                ethnicity_note=("Major ethnic group, 2023 household population, summed from "
                                "the census divisions that make the parish (Table 2-6)."))
        else:
            fields.update(
                population=measure(a["total"], year=2012, source=SOURCE_2012),
                population_note=("The 2012 census's population of the enumeration districts "
                                 "in the parish; a 2023 census division is split between it "
                                 "and a neighbour, so no 2023 figure is summed for it."),
                ethnicity=shares(dict(c["ethnicity"])), ethnicity_year=2012,
                ethnicity_note="Ethnic group, 2012, summed from the enumeration districts.")
        records.append(record(
            f"VCT-SO-{fold(parish)}", shape["name"], level="admin1", parent="VCT",
            country="VCT", match_by="shape_id", shape_id=shape["id"],
            median_age=measure(grouped_median(groups), unit="years", year=2012,
                               source=SOURCE_2012),
            median_age_note=("Interpolated within the five-year age group holding the middle "
                             "person, 2012, summed from the enumeration districts."),
            sex_ratio=measure(round(1000 * a["men"] / a["women"]),
                              unit="males_per_1000_females", year=2012, source=SOURCE_2012),
            sex_ratio_note="Men per thousand women, 2012.",
            religion=shares(dict(c["religion"])), religion_year=2012,
            religion_note=("Religion, 2012, summed from the enumeration districts; \"Without "
                           "religion\" is written as No religion."),
            language=gap(NOT_AVAILABLE, LANGUAGE_GAP),
            sources=[{"field": "median_age/sex_ratio/religion"
                               + ("" if new else "/population/ethnicity"),
                      "name": SOURCE_2012, "url": uscb.dataset_url(DATASET), "year": 2012,
                      "license": "CC BY-IGO, published via HDX"}]
            + ([{"field": "population/ethnicity", "name": SOURCE_2023, "url": REPORT,
                 "year": 2023}] if new else []),
            **fields))
    write_json(OUT, records)
    log(f"  wrote {OUT.name}: {len(records)} parishes, {len(recent)} with 2023 figures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
