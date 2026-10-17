#!/usr/bin/env python3
"""Lesotho -- the 2016 census's count of every community council, from its
village list.

The Bureau of Statistics published the 2016 Population and Housing Census
Village List as a workbook: every village under its district, constituency,
community council and enumeration area, with its households, men, women and
total, and a Total line after each enumeration area. The Bureau's own copy is
no longer online; the Internet Archive's copy of the same address is read.

Written: for each council the map draws, the census's count (its villages
added up) and the sex ratio (men per thousand women). Median age, religion,
language and ethnicity are empty with their reason: the village list gives
households, men and women only.

**The units.** The map's second level is Lesotho's community and urban
councils, matched to the village list's councils by name within their
district (``ALIASES`` holds the spellings no reduction joins). A polygon whose
name no council of its district shares gets a stated reason, not a guess.

**Checks before anything is written.** Every village's men and women make its
total; each enumeration area's villages make its Total line; the districts
together make the census's 2,007,201 people to within the people the village
list does not place in a village (institutions), at most ``UNPLACED`` of them.

Usage:
    python -m scripts.fetch_census.lesotho_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import zipfile
from collections import defaultdict
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, write_json
from .southern_africa_common import fetch, key, sex_ratio, units

URL = ("https://www.bos.gov.ls/New%20Folder/Copy%20of%20Demography/"
       "2016%20POPULATION%20CENSUS%20VILLAGE%20LIST.zip")
ARCHIVE = ("20221113190955", "2022", "2023")
SOURCE = "Lesotho Bureau of Statistics, 2016 Population and Housing Census Village List"
LICENCE = "Lesotho Bureau of Statistics publication (reuse with attribution)"
YEAR = 2016
NATIONAL = 2_007_201
UNPLACED = 0.02
OUT = "lesotho_census.json"

# District names: the village list's, reduced -> the map's, reduced.
DISTRICTS = {"bothabothe": "buthabuthedistrict", "berea": "bereadistrict",
             "leribe": "leribedistrict", "mafeteng": "mafetengdistrict",
             "maseru": "maserudistrict", "mohaleshoek": "mohaleshoekdistrict",
             "mokhotlong": "mokhotlongdistrict", "qachasnek": "qachasnekdistrict",
             "quthing": "quthingdistrict", "thabatseka": "thabatsekadistrict"}
# Council names: the map's, reduced (district part dropped) -> the village
# list's, reduced, where the spellings differ.
ALIASES: dict[str, str] = {
    "buthabuthe": "bothabothe",
}

AGE_NOTE = ("The 2016 census's village list gives each village's households, men and women, "
            "not their ages, so no median age is published for this council.")
COMPOSITION_NOTE = ("The 2016 census's village list, the census table that reaches this "
                    "council, gives each village's households, men and women and nothing else.")


def council_key(name: str) -> str:
    """A council's name reduced, its district in brackets and words such as
    'Urban Council' dropped."""
    text = re.sub(r"\(.*?\)", " ", str(name))
    text = re.sub(r"(?i)\b(urban|community|municipal|council|cc|uc)\b", " ", text)
    return key(text)


def rows_of(blob: bytes) -> list[list[Any]]:
    import openpyxl                                 # noqa: PLC0415
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        inner = [n for n in zf.namelist() if n.lower().endswith(".xlsx")]
        if not inner:
            raise SystemExit(f"lesotho_census: the zip holds no workbook: {zf.namelist()}")
        book = zf.read(inner[0])
    wb = openpyxl.load_workbook(io.BytesIO(book), read_only=True, data_only=True)
    return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]


def number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and float(value).is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"\s*\d[\d,]*\s*", value):
        return int(value.replace(",", ""))
    return None


def parse(rows: list[list[Any]]) -> dict[str, Any]:
    """{"councils": {(district, council): {"men", "women", "total", "villages"}},
    "districts": {district: total}} from the village rows."""
    head = next((i for i, r in enumerate(rows) if any(str(v).strip() == "Village Name"
                                                       for v in r if v)), None)
    if head is None:
        raise SystemExit("lesotho_census: no head row naming the Village Name column")
    names = {str(v).strip(): i for i, v in enumerate(rows[head]) if v}
    col = {f: names[h] for f, h in (("district", "District"), ("constituency", "Constituency"),
                                    ("council", "Council"), ("ea", "Enumeration Area Code"),
                                    ("village", "Village Name"))}
    # Households, then Male, Female, Total under Population.
    col["households"] = names["Households"]
    col["men"], col["women"], col["total"] = (names["Population"], names["Population"] + 1,
                                              names["Population"] + 2)
    filled: dict[str, Any] = {}
    councils: dict[tuple[str, str], dict[str, Any]] = {}
    ea_sum: dict[Any, list[int]] = defaultdict(lambda: [0, 0, 0])
    checked = 0
    for r in rows[head + 2:]:
        if not any(v not in (None, "") for v in r):
            continue
        for f in ("district", "constituency", "council", "ea"):
            v = r[col[f]] if col[f] < len(r) else None
            if v not in (None, ""):
                filled[f] = str(v).strip()
        village = r[col["village"]] if col["village"] < len(r) else None
        men, women, total = (number(r[col[f]]) if col[f] < len(r) else None
                             for f in ("men", "women", "total"))
        if village in (None, "") or None in (men, women, total):
            continue
        if men + women != total:
            raise SystemExit(f"lesotho_census: {village}: {men} men and {women} women do not "
                             f"make {total}")
        ea = (filled.get("district"), filled.get("council"), filled.get("ea"))
        if str(village).strip().lower() == "total":
            got = ea_sum.pop(ea, None)
            if got is None or got != [men, women, total]:
                raise SystemExit(f"lesotho_census: enumeration area {ea}: its villages make "
                                 f"{got}, its Total line {[men, women, total]}")
            checked += 1
            continue
        ea_sum[ea] = [a + b for a, b in zip(ea_sum[ea], (men, women, total))]
        c = councils.setdefault((filled["district"], filled["council"]),
                                {"men": 0, "women": 0, "total": 0, "villages": 0})
        c["men"] += men
        c["women"] += women
        c["total"] += total
        c["villages"] += 1
    if ea_sum:
        log(f"  {len(ea_sum)} enumeration areas without a Total line")
    districts: dict[str, int] = defaultdict(int)
    for (d, _), c in councils.items():
        districts[d] += c["total"]
    national = sum(districts.values())
    log(f"  {sum(c['villages'] for c in councils.values()):,} villages in {len(councils)} "
        f"councils; {checked:,} enumeration area totals checked; {national:,} people")
    if not NATIONAL * (1 - UNPLACED) <= national <= NATIONAL * 1.001:
        raise SystemExit(f"lesotho_census: the villages make {national:,}, against the "
                         f"census's {NATIONAL:,}")
    return {"councils": councils, "districts": dict(districts)}


def bind(table: dict[str, Any], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
         ) -> tuple[dict[str, tuple[str, str]], list[dict[str, Any]]]:
    """({polygon id: (district, council)}, the polygons left), by name within
    the district."""
    district_of = {}
    for d in table["districts"]:
        want = DISTRICTS.get(key(d), key(d) + "district")
        hits = [s for s in admin1 if key(s["name"]) == want]
        if len(hits) != 1:
            raise SystemExit(f"lesotho_census: no polygon for the district {d!r}")
        district_of[hits[0]["id"]] = d
    bound: dict[str, tuple[str, str]] = {}
    left: list[dict[str, Any]] = []
    for shape in admin2:
        d = district_of.get(shape.get("parent"))
        want = council_key(shape["name"])
        want = ALIASES.get(want, want)
        hits = [c for c in table["councils"] if c[0] == d and council_key(c[1]) == want]
        if len(hits) == 1:
            bound[shape["id"]] = hits[0]
        else:
            left.append(shape)
    used = list(bound.values())
    if len(set(used)) != len(used):
        raise SystemExit("lesotho_census: one council bound to two polygons")
    spare = sorted(set(table["councils"]) - set(used))
    for d, c in spare:
        log(f"    council on no polygon: {d} / {c} ({table['councils'][(d, c)]['total']:,})")
    for s in left:
        log(f"    polygon with no council: {s['name']} "
            f"(in {district_of.get(s.get('parent'))})")
    return bound, left


SOURCES = [{"field": "population/sex_ratio", "name": SOURCE, "url": URL, "license": LICENCE,
            "year": YEAR}]


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bound, left = bind(table, admin1, admin2)
    gaps = {"median_age": gap(NOT_AVAILABLE, AGE_NOTE),
            "religion": gap(NOT_AVAILABLE, COMPOSITION_NOTE),
            "language": gap(NOT_AVAILABLE, COMPOSITION_NOTE),
            "ethnicity": gap(NOT_AVAILABLE, COMPOSITION_NOTE)}
    out = []
    for shape in admin2:
        if shape["id"] not in bound:
            continue
        d, c = bound[shape["id"]]
        data = table["councils"][(d, c)]
        note = (f"The 2016 census's count for {c} council ({d} district): its "
                f"{data['villages']:,} villages added up.")
        out.append(record(f"LSO-2016-{key(d)}-{key(c)}", shape["name"], level="admin2",
                          parent="LSO", country="LSO", match_by="shape_id",
                          shape_id=shape["id"], sources=SOURCES,
                          population=measure(data["total"], year=YEAR, source=SOURCE),
                          population_note=note,
                          sex_ratio=sex_ratio(data["men"], data["women"], year=YEAR,
                                              source=SOURCE), **gaps))
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob, where = fetch(URL, archive=ARCHIVE, office=False, expect=b"PK")
    log(f"  read {where}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    table = parse(rows_of(blob))
    for d, n in sorted(table["districts"].items()):
        log(f"  district {d}: {n:,}")
    records = build(table, units("LSO", "admin1"), units("LSO", "admin2"))
    log(f"  {len(records)} councils written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
