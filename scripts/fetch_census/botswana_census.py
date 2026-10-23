#!/usr/bin/env python3
"""Botswana -- the 2022 Population and Housing Census by district.

Statistics Botswana's "Population and Housing Census 2022 Analytical Report
Volume 1" prints, in its Appendix Table 3, the population of the 28 census
districts by sex. The Bureau's site refuses the runner; the Internet Archive's
copy of the report is read.

Written: the census's count and sex ratio (men per thousand women) for the
map's ten districts, each the census districts and towns that lie in it added
up (``DISTRICTS``), and for the four second-level polygons that are census
districts or sums of them: Chobe, Kgatleng, Ghanzi (Ghanzi and the Central
Kalahari Game Reserve, CKGR) and Masungu (North East and Francistown). The
map's other second-level polygons are the sub-districts of an older division,
whose lines are not the census districts' (Central's eight, Kgalagadi's
three, Kweneng's two, Southern's four, South-East's two, and Ngamiland East
and West, which split the census's Delta between them): they say so.

**Checks before anything is written.** Every line's men and women make its
total; the 28 census districts make the census's 2,359,609; every census
district is in exactly one of the map's districts.

Usage:
    python -m scripts.fetch_census.botswana_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, write_json
from .southern_africa_common import fetch, joined, key, sex_ratio, units

URL = ("https://www.statsbots.org.bw/sites/default/files/publications/"
       "Botswana%20Population%20%26%20Housing%20Census%202022%20Analytical%20Report%20Volume%201.pdf")
ARCHIVE = ("20260106063554", "2025", "2026")
SOURCE = ("Statistics Botswana, Population and Housing Census 2022 Analytical Report Volume 1, "
          "Appendix Table 3")
LICENCE = "Statistics Botswana publication (reuse with attribution)"
YEAR = 2022
NATIONAL = 2_359_609
OUT = "botswana_census.json"
TITLE = "Table 3: Population Distribution by Census District and Sex 2022"

# The map's districts (reduced) -> the census districts and towns in them.
DISTRICTS = {
    "centraldistrict": ["Central Serowe /Palapye", "Central Mahalapye", "Central Bobonong",
                        "Central Boteti", "Central Tutume", "Selibe Phikwe", "Orapa", "Sowa"],
    "chobedistrict": ["Chobe"],
    "ghanzidistrict": ["Ghanzi", "CKGR"],
    "kgalagadidistrict": ["Kgalagadi South", "Kgalagadi North"],
    "kgatlengdistrict": ["Kgatleng (Wards)"],
    "kwenengdistrict": ["Kweneng East", "Kweneng West"],
    "northeastdistrict": ["North East", "Francistown"],
    "northwestdistrict": ["Ngamiland East", "Ngamiland West", "Delta"],
    "southeastdistrict": ["South East", "Gaborone", "Lobatse"],
    "southerndistrict": ["Southern", "Barolong", "Ngwaketse West", "Jwaneng"],
}
# The map's second-level polygons that are census districts or their sums.
POLYGONS = {"chobe": ["Chobe"], "kgatleng": ["Kgatleng (Wards)"], "ghanzi": ["Ghanzi", "CKGR"],
            "masungu": ["North East", "Francistown"]}
OLDER = ("The 2022 census counts Botswana by 28 census districts (Statistics Botswana, Analytical "
         "Report Volume 1, Appendix Table 3); this polygon is a sub-district of an older division "
         "whose lines are not theirs, so no census count is shown for it.")
LINE = re.compile(r"^(?P<name>[A-Za-z][A-Za-z /()]*?)\s+(?P<t>\d{1,3}(?:,\d{3})*)\s+"
                  r"(?P<m>\d{1,3}(?:,\d{3})*)\s+(?P<f>\d{1,3}(?:,\d{3})*)\s+(?P<r>\d+\.\d)$")


def number(text: str) -> int:
    return int(text.replace(",", ""))


def parse(text: str) -> dict[str, dict[str, int]]:
    """{census district: {"total", "men", "women"}} and "Total"."""
    out: dict[str, dict[str, int]] = {}
    started = False
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if TITLE in line:
            started = True
            continue
        if not started:
            continue
        hit = LINE.match(line)
        if not hit:
            if out.get("Total"):
                break
            continue
        t, m, f = (number(hit.group(g)) for g in "tmf")
        if m + f != t:
            raise SystemExit(f"botswana_census: {line!r}: men and women do not make the total")
        out[hit.group("name").strip()] = {"total": t, "men": m, "women": f}
    if out.get("Total", {}).get("total") != NATIONAL:
        raise SystemExit(f"botswana_census: the table's total is {out.get('Total')}")
    names = [n for n in out if n != "Total"]
    placed = [n for v in DISTRICTS.values() for n in v]
    if sorted(names) != sorted(placed):
        raise SystemExit(f"botswana_census: the census districts {sorted(names)} are not those "
                         f"placed {sorted(placed)}")
    for f in ("total", "men", "women"):
        if sum(out[n][f] for n in names) != out["Total"][f]:
            raise SystemExit(f"botswana_census: the districts do not make the total {f}")
    return out


def fields(table: dict[str, dict[str, int]], names: list[str]) -> dict[str, Any]:
    t = sum(table[n]["total"] for n in names)
    m = sum(table[n]["men"] for n in names)
    f = sum(table[n]["women"] for n in names)
    label = joined([n.replace(" (Wards)", "").replace(" /", "/") for n in names])
    note = (f"The 2022 census's count for {label}." if len(names) == 1 else
            f"The 2022 census's counts for {label} added together.")
    return {"population": measure(t, year=YEAR, source=SOURCE), "population_note": note,
            "sex_ratio": sex_ratio(m, f, year=YEAR, source=SOURCE)}


def build(table: dict[str, dict[str, int]], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources = [{"field": "population/sex_ratio", "name": SOURCE, "url": URL,
                "license": LICENCE, "year": YEAR}]
    out = []
    for shape in admin1:
        names = DISTRICTS.get(key(shape["name"]))
        if not names:
            raise SystemExit(f"botswana_census: no census districts for {shape['name']!r}")
        out.append(record(f"BWA-2022-{key(shape['name'])}", shape["name"], level="admin1",
                          parent="BWA", country="BWA", match_by="shape_id",
                          shape_id=shape["id"], sources=sources, **fields(table, names)))
    for shape in admin2:
        names = POLYGONS.get(key(shape["name"]))
        if names:
            values = fields(table, names)
        else:
            values = {"population": gap(NOT_AVAILABLE, OLDER), "sex_ratio": gap(NOT_AVAILABLE,
                                                                                 OLDER)}
        out.append(record(f"BWA-2022-sub-{key(shape['name'])}", shape["name"], level="admin2",
                          parent="BWA", country="BWA", match_by="shape_id",
                          shape_id=shape["id"], sources=sources, **values))
    return out


def text_of(blob: bytes) -> str:
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages[30:45])


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob, where = fetch(URL, archive=ARCHIVE, office=False, expect=b"%PDF")
    log(f"  read {where}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    table = parse(text_of(blob))
    records = build(table, units("BWA", "admin1"), units("BWA", "admin2"))
    for r in records:
        log(f"  {r['level']} {r['name']}: {r['population'].get('value')}; "
            f"{r.get('population_note') or r['population'].get('note', '')[:60]}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
