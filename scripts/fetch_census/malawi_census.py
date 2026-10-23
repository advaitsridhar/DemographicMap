#!/usr/bin/env python3
"""Malawi -- the 2018 Population and Housing Census by district and region.

The National Statistical Office publishes the census's tables as workbooks:
Series A, Population Tables, and Series E, Social Tables. Four are read here.

    A1  population by sex for the country, the three regions and the 32
        districts and cities, 2018 (and 2008)
    A6  population by age group, region and district (under 1, 1-4, five-year
        groups to 85-89, 90 and over)
    E4  Malawian population by tribe, region and district
    E5  population by religious denomination, region and district

Written: for the 28 districts the map draws, the sex ratio (men per thousand
women), the median age (interpolated within the age group that holds the
middle person), religion and tribe as counts; for the three regions the same.
Each district's population is the census's count too, though the map shows
the National Statistical Office's later projection where there is one: the
newer figure stands. Language is empty with its reason: the census's social
tables give tribe and religion by district, and no language.

**The units.** The census lists Malawi's four cities -- Mzuzu, Lilongwe, Zomba
and Blantyre -- beside the districts they lie in, and the map draws each city
within its district: Mzimba, Lilongwe, Zomba and Blantyre are the census's
district and city added together, and say so.

**Checks before anything is written.** In A1 each line's men and women make
its total, each region's districts and cities make the region and the regions
make the country's 17,563,749. Every district's A6 age groups make its A1
total; every E5 line's denominations make its total, which is its A1 total;
every E4 line's tribes make its total, which is no more than its A1 total
(Table E4 counts Malawians only).

Usage:
    python -m scripts.fetch_census.malawi_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .southern_africa_common import fetch, grouped_median, key, sex_ratio, units

SERIES_A = "https://cms.nsomalawi.mw/api/download/277/Series-A.-Population-Tables.xlsx"
SERIES_E = "https://cms.nsomalawi.mw/api/download/281/Series-E.-Social-Tables.xlsx"
SOURCE_A = ("National Statistical Office of Malawi, 2018 Malawi Population and Housing Census, "
            "Series A: Population Tables (Tables A1 and A6)")
SOURCE_E = ("National Statistical Office of Malawi, 2018 Malawi Population and Housing Census, "
            "Series E: Social Tables (Tables E4 and E5)")
LICENCE = "National Statistical Office of Malawi publication (reuse with attribution)"
YEAR = 2018
NATIONAL = 17_563_749
OUT = "malawi_census.json"
REGIONS = ("Northern", "Central", "Southern")

# The cities the census lists beside the district each lies in.
CITIES = {"Mzuzu City": "Mzimba", "Lilongwe City": "Lilongwe", "Zomba City": "Zomba",
          "Blantyre City": "Blantyre"}
# Spellings of the census's own tables that differ from Table A1's.
SPELLINGS = {"nklhotakota": "nkhotakota"}

# Table E5's column heads, under the names the map's legend knows.
DENOMINATIONS = {
    "catholic": "Catholic",
    "ccap": "Church of Central Africa Presbyterian",
    "seventhdayadventistbaptistapostolic": "Seventh Day Adventist/Baptist/Apostolic",
    "anglican": "Anglican",
    "pentecostal": "Pentecostal",
    "otherchristiandenomination": "Other Christian denominations",
    "otherchristiandenominations": "Other Christian denominations",
    "islam": "Islam",
    "traditional": "Traditional",
    "otherdenomination": "Other denomination",
    "otherdenominations": "Other denomination",
    "noreligion": "No religion",
}
TRIBES = ("Chewa", "Tumbuka", "Lomwe", "Tonga", "Yao", "Sena", "Nkhonde", "Ngoni", "Lambya",
          "Sukwa", "Mang'anja", "Nyanja", "Other")

LANGUAGE_NOTE = ("The National Statistical Office's tables of the 2018 census give tribe and "
                 "religious denomination by district (Series E, Social Tables) and no language "
                 "spoken, so no census figure for language is shown here.")
RELIGION_NOTE = ("Religious denomination of everyone the 2018 census counted, as counts "
                 "(National Statistical Office, Series E, Table E5).")


def cell(value: Any) -> Any:
    if isinstance(value, str):
        text = " ".join(value.split())
        if text in ("-", "–"):
            return 0
        if re.fullmatch(r"\d[\d,]*", text):
            return int(text.replace(",", ""))
        return text
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def sheet(blob: bytes, name: str) -> list[list[Any]]:
    import openpyxl                                 # noqa: PLC0415
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    wanted = [ws for ws in wb.worksheets if ws.title.strip() == name]
    if not wanted:
        raise SystemExit(f"malawi_census: no sheet {name!r} in {[ws.title for ws in wb.worksheets]}")
    return [[cell(v) for v in row] for row in wanted[0].iter_rows(values_only=True)]


def label(row: list[Any]) -> str:
    return str(row[0]).strip() if row and isinstance(row[0], str) else ""


def area(name: str) -> str:
    k = key(name)
    return SPELLINGS.get(k, k)


def read_a1(rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """{area key: {"name", "total", "men", "women"}} for the country, regions,
    districts and cities, 2018."""
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = label(row)
        nums = row[1:4]
        if not name or not all(isinstance(n, int) for n in nums):
            continue
        total, men, women = nums
        if men + women != total:
            raise SystemExit(f"malawi_census: A1 {name}: {men:,} men and {women:,} women do not "
                             f"make {total:,}")
        out.setdefault(area(name), {"name": name, "total": total, "men": men, "women": women})
    return out


def check_a1(a1: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """{region: its districts and cities}, from the order of Table A1, checked
    to make the region and the regions to make the country."""
    country = a1.get("malawi")
    if not country or country["total"] != NATIONAL:
        raise SystemExit(f"malawi_census: A1 gives Malawi {country and country['total']}, "
                         f"not {NATIONAL:,}")
    names = list(a1)
    members: dict[str, list[str]] = {}
    for i, region in enumerate(REGIONS):
        start = names.index(key(region))
        stop = names.index(key(REGIONS[i + 1])) if i + 1 < len(REGIONS) else len(names)
        members[region] = names[start + 1:stop]
        for field in ("total", "men", "women"):
            made = sum(a1[k][field] for k in members[region])
            if made != a1[key(region)][field]:
                raise SystemExit(f"malawi_census: A1 {region}'s {len(members[region])} districts "
                                 f"and cities make {made:,} {field}, not "
                                 f"{a1[key(region)][field]:,}")
    for field in ("total", "men", "women"):
        made = sum(a1[key(r)][field] for r in REGIONS)
        if made != country[field]:
            raise SystemExit(f"malawi_census: A1's regions make {made:,} {field}")
    return members


AGE = re.compile(r"^(?:(?P<lt>Less than 1)|(?P<lo>\d+)\s*-\s*(?P<hi>\d+)|(?P<top>\d+)\s*\+)")


def age_group(text: str) -> tuple[int, int | None] | None:
    hit = AGE.match(text)
    if not hit:
        return None
    if hit.group("lt"):
        return 0, 1
    if hit.group("top"):
        return int(hit.group("top")), None
    lo, hi = int(hit.group("lo")), int(hit.group("hi"))
    return lo, hi - lo + 1


def read_a6(rows: list[list[Any]]) -> dict[str, list[tuple[int, int | None, int]]]:
    """{area key: [(lower age, width, people)]} from each region's first block
    (both sexes): a head row naming the region's total and its districts, a
    Total row, then the age groups."""
    out: dict[str, list[tuple[int, int | None, int]]] = {}
    heads: dict[int, str] | None = None
    for row in rows:
        name = label(row)
        texts = [v for v in row[1:] if isinstance(v, str)]
        if not name and texts and any(t.endswith(" Total") for t in texts):
            heads = {i: area(v[:-len(" Total")] if v.endswith(" Total") else v)
                     for i, v in enumerate(row) if i and isinstance(v, str) and v}
            if any(k in out for k in heads.values()):
                heads = None                        # a later block: men or women only
            else:
                for k in heads.values():
                    out[k] = []
            continue
        if heads is None:
            continue
        if not name:
            if not any(isinstance(v, int) for v in row):
                heads = None
            continue
        group = age_group(name)
        if group is None:
            continue
        for i, k in heads.items():
            if isinstance(row[i] if i < len(row) else None, int):
                out[k].append((group[0], group[1], row[i]))
    return out


def read_table(rows: list[list[Any]], names: dict[str, str]) -> dict[str, dict[str, int]]:
    """{area key: {group: count, "TOTAL": n}} for the first block of a table
    whose head row names its columns (Total, then the groups)."""
    out: dict[str, dict[str, int]] = {}
    cols: dict[int, str] | None = None
    for row in rows:
        name = label(row)
        texts = [(i, v) for i, v in enumerate(row) if i and isinstance(v, str) and v.strip()]
        if cols is None:
            found = {i: names.get(key(v)) for i, v in texts}
            if texts and texts[0][1].strip().lower() == "total" and \
                    sum(1 for v in found.values() if v) >= len(set(names.values())) // 2:
                # A head the names above do not know is kept as the table
                # prints it, so the line still adds up.
                cols = {i: found[i] or " ".join(v.split()) for i, v in texts}
                cols[texts[0][0]] = "TOTAL"
                unknown = [v for i, v in texts[1:] if not found[i]]
                if unknown:
                    log(f"    heads kept as printed: {unknown}")
            continue
        if name.lower().startswith(("males", "females")):
            break
        if not name or not isinstance(row[1] if len(row) > 1 else None, int):
            continue
        values = {g: (row[i] if i < len(row) and isinstance(row[i], int) else 0)
                  for i, g in cols.items()}
        out.setdefault(area(name), values)
    if cols is None:
        raise SystemExit("malawi_census: no head row naming the table's columns")
    return out


def check_table(table: dict[str, dict[str, int]], a1: dict[str, dict[str, Any]], what: str,
                *, whole: bool) -> None:
    for k, values in table.items():
        parts = sum(v for g, v in values.items() if g != "TOTAL")
        if parts != values["TOTAL"]:
            raise SystemExit(f"malawi_census: {what} {k}: the groups make {parts:,}, "
                             f"not {values['TOTAL']:,}")
        if k not in a1:
            raise SystemExit(f"malawi_census: {what} names {k!r}, which A1 does not")
        if (values["TOTAL"] != a1[k]["total"]) if whole else (values["TOTAL"] > a1[k]["total"]):
            raise SystemExit(f"malawi_census: {what} {k}: {values['TOTAL']:,} against A1's "
                             f"{a1[k]['total']:,}")
    missing = [a1[k]["name"] for k in a1 if k not in table]
    if missing:
        raise SystemExit(f"malawi_census: {what} lacks {missing}")


def parse(blob_a: bytes, blob_e: bytes) -> dict[str, Any]:
    a1 = read_a1(sheet(blob_a, "A1"))
    members = check_a1(a1)
    ages = read_a6(sheet(blob_a, "A6"))
    for k, row in a1.items():
        if k == "malawi":
            continue
        made = sum(n for _, _, n in ages.get(k, []))
        if made != row["total"]:
            raise SystemExit(f"malawi_census: A6 {row['name']}: the age groups make {made:,}, "
                             f"not {row['total']:,}")
    tribes = read_table(sheet(blob_e, "E4"), {key(t): t for t in TRIBES})
    check_table(tribes, a1, "E4", whole=False)
    religions = read_table(sheet(blob_e, "E5"), DENOMINATIONS)
    check_table(religions, a1, "E5", whole=True)
    return {"a1": a1, "members": members, "ages": ages, "tribes": tribes,
            "religions": religions}


def summed(table: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    """The census's figures for one or more areas added together."""
    out: dict[str, Any] = {f: sum(table["a1"][k][f] for k in keys)
                           for f in ("total", "men", "women")}
    ages: dict[tuple[int, int | None], int] = {}
    for k in keys:
        for lo, width, n in table["ages"][k]:
            ages[(lo, width)] = ages.get((lo, width), 0) + n
    out["ages"] = [(lo, width, n) for (lo, width), n in ages.items()]
    for field in ("tribes", "religions"):
        merged: dict[str, int] = {}
        for k in keys:
            for g, n in table[field][k].items():
                merged[g] = merged.get(g, 0) + n
        out[field] = merged
    return out


SOURCES = [{"field": "population/sex_ratio/median_age", "name": SOURCE_A, "url": SERIES_A,
            "license": LICENCE, "year": YEAR},
           {"field": "religion/ethnicity", "name": SOURCE_E, "url": SERIES_E,
            "license": LICENCE, "year": YEAR}]


def fields(data: dict[str, Any], note: str) -> dict[str, Any]:
    religions = {g: n for g, n in data["religions"].items() if g != "TOTAL" and n}
    tribes = {g: n for g, n in data["tribes"].items() if g != "TOTAL" and n}
    malawians = data["tribes"]["TOTAL"]
    return {
        "population": measure(data["total"], year=YEAR, source=SOURCE_A),
        "population_note": note,
        "sex_ratio": sex_ratio(data["men"], data["women"], year=YEAR, source=SOURCE_A),
        "median_age": measure(grouped_median(data["ages"]), year=YEAR, source=SOURCE_A),
        "median_age_note": ("Interpolated within the age group that holds the middle person, "
                            "from the 2018 census's counts by age group (Table A6)."),
        "religion": shares(religions, total=data["religions"]["TOTAL"]),
        "religion_year": YEAR,
        "religion_note": RELIGION_NOTE,
        "ethnicity": shares(tribes, total=malawians),
        "ethnicity_year": YEAR,
        "ethnicity_note": (f"Tribe of the {malawians:,} Malawians the 2018 census counted here "
                           f"(Table E4 counts Malawian citizens only), of {data['total']:,} "
                           f"people."),
        "language": gap(NOT_AVAILABLE, LANGUAGE_NOTE),
    }


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    a1 = table["a1"]
    out: list[dict[str, Any]] = []
    region_of_shape = {s["id"]: key(re.sub(r"(?i)\s+region$", "", s["name"])) for s in admin1}
    used: set[str] = set()
    for shape in admin2:
        k = key(shape["name"])
        if k not in a1 or k in [key(r) for r in REGIONS] + ["malawi"]:
            raise SystemExit(f"malawi_census: no census district for {shape['name']!r}")
        region = next(r for r, ks in table["members"].items() if k in ks)
        if key(region) != region_of_shape.get(shape.get("parent")):
            raise SystemExit(f"malawi_census: {shape['name']} lies in the census's {region} "
                             f"region and not in the map's")
        keys = [k] + [key(c) for c, d in CITIES.items() if key(d) == k]
        used.update(keys)
        names = [a1[x]["name"] for x in keys]
        note = (f"The 2018 census's count for {names[0]} District"
                + (f" and {names[1]}, which lies within it." if len(names) > 1 else "."))
        out.append(record(f"MWI-2018-{k}", shape["name"], level="admin2", parent="MWI",
                          country="MWI", match_by="shape_id", shape_id=shape["id"],
                          sources=SOURCES, **fields(summed(table, keys), note)))
    spare = [a1[k]["name"] for ks in table["members"].values() for k in ks if k not in used]
    if spare:
        raise SystemExit(f"malawi_census: census districts on no polygon: {spare}")
    for shape in admin1:
        k = region_of_shape[shape["id"]]
        if k not in [key(r) for r in REGIONS]:
            raise SystemExit(f"malawi_census: no census region for {shape['name']!r}")
        values = fields(summed(table, [k]), "")
        # The region's population is its districts' sum, as the map adds them.
        for drop in ("population", "population_note"):
            values.pop(drop)
        out.append(record(f"MWI-2018-region-{k}", shape["name"], level="admin1", parent="MWI",
                          country="MWI", match_by="shape_id", shape_id=shape["id"],
                          sources=SOURCES, **values))
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blobs = []
    for url in (SERIES_A, SERIES_E):
        blob, where = fetch(url, archive=("2024", "2025"), expect=b"PK")
        log(f"  read {where}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
        blobs.append(blob)
    table = parse(*blobs)
    records = build(table, units("MWI", "admin1"), units("MWI", "admin2"))
    for r in records:
        top = (r["religion"][0]["group"], r["ethnicity"][0]["group"]) \
            if isinstance(r["religion"], list) else None
        log(f"  {r['level']} {r['name']}: pop {r['population'].get('value')}, "
            f"median {r['median_age'].get('value')}, ratio {r['sex_ratio'].get('value')}, {top}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
