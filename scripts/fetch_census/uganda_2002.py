#!/usr/bin/env python3
"""Uganda: religion from the 2002 census, by region and for the counties that
were a district on their own.

The Uganda Bureau of Statistics took its last census to publish religion below
the country in September 2002: the 2014 census's Main Report gives religion
and ethnicity for the country as a whole only (Tables A8 and A9, by sex and
residence), and so does the 2024 census's Final Report (Volume 1, Tables 3.1
and 3.2). The 2002 census's tabulations, which the Bureau publishes as one
ZIP of PDF tables, give religion by district (Table B7, Annex 2 of the main
report): Catholic, Anglican, Seventh-day Adventist, Pentecostal, Muslim,
other and none, for each of the 56 districts of 2002, under its region, with
each region's total. The Bureau's host fails certificate checks from the
runner, so the Internet Archive's capture is read (its ``id_`` form returns
the original bytes).

**Regions.** The four regions are the same ground in 2002 and today (every
district since has been cut from one of them), and each takes Table B7's total
row for it. Afrobarometer's survey estimates for two of them give way, a
count standing in front of a survey.

**Counties.** The map draws Uganda's counties as they stood around 2002. Ten
of the 2002 districts were a single county -- Kampala, Kiboga, Nakasongola
(Buruli), Bugiri (Bukooli), Busia (Samia-Bugwe), Mayuge (Bunya), Adjumani
(East Moyo), Yumbe (Aringa), Kisoro (Bufumbira) and Kanungu (Kinkiizi) --
which Table 3A, the population by county, shows as a district row followed by
one county row with the same figures. Such a county's religion is its
district's. It is written only where the drawn polygon is known to be that
ground: where the 2024 crosswalk (``uganda_counties.PLACED``) makes the
polygon exactly every county of the 2024 districts it holds, so that the
district of 2002 and the polygon are the same ground counted twice. Yumbe's
Aringa is crossed by 2024 counties (STRADDLING), and says why it has none.

**Checks.** Every Table B7 row's religions make its total; each region's
districts make its total row and the regions the national row (24,433,132,
the table leaving out people enumerated in hotels); Table 3A's men and women
make each row, each district's counties make the district, and the 56
districts make 24,442,084.

``--titles`` and ``--member NAME --pages N`` print what the ZIP's tables hold,
for inspection; nothing is written then.

Usage:
    python -m scripts.fetch_census.uganda_2002
    python -m scripts.fetch_census.uganda_2002 --titles
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from typing import Any

from ._shared import (NOT_AVAILABLE, PROCESSED, dated, gap, http_get, log, record, shares,
                      write_json)
from .binding import fold

ZIP = ("https://web.archive.org/web/20211116120534id_/https://www.ubos.org/wp-content/"
       "uploads/publications/10_20212002_census_tabulations_pdf.zip")
PAGE = "https://www.ubos.org/wp-content/uploads/publications/10_20212002_census_tabulations_pdf.zip"
OUT = "uganda_2002.json"
YEAR = 2002
SITE = PROCESSED.parent.parent / "site" / "data"
POINTS = PROCESSED / "uganda_county_points.json"
B7 = "centableB7.pdf"
T3A = "centable3a.pdf"
NATIONAL_B7 = 24_433_132
NATIONAL_3A = 24_442_084
DISTRICTS = 56
SOURCE = ("Uganda Bureau of Statistics, 2002 Uganda Population and Housing Census, Table B7: "
          "Religion by District")
LICENCE = "Uganda Bureau of Statistics publication (reuse with attribution)"
# Table B7's columns, in order, and the labels the map gives them.
COLUMNS = ("Catholic", "Anglican", "SDA", "Pentecostal", "Moslem", "Other", "None")
LABELS = {"Catholic": "Catholic", "Anglican": "Anglican", "SDA": "Adventist",
          "Pentecostal": "Pentecostal", "Moslem": "Muslim", "Other": "Other religion",
          "None": "No religion"}
REGIONS = {"Central": "Central Region", "Eastern": "Eastern Region",
           "Northern": "Northern Region", "Western": "Western Region"}
# Table 3A's spelling of a district where Table B7's differs.
DISTRICT_ALIASES = {"ssembabule": "sembabule"}
# Table 3A's county row where the drawn polygon is named otherwise.
COUNTY_ALIASES = {"kampalacitycouncil": "kampala"}
OTHER = ("'Other religion' is the census's 'Other': Orthodox, Baha'i, other Christian, "
         "non-Christian and traditional religions.")
LATER = "the 2014 and 2024 censuses published religion for the country as a whole only"

NUMBER = r"\d{1,3}(?:,\d{3})*"
ROW = re.compile(rf"^(?:{NUMBER}\s+){{7}}{NUMBER}$")
SKIP = re.compile(r"^(?:Table B7|District Catholic|2002 Uganda|\d{1,3}$|\*)")


def members(names: tuple[str, ...] | None = None) -> dict[str, bytes]:
    blob = http_get(ZIP, binary=True, cache=False, timeout=600)
    log(f"  read {ZIP}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        return {n.rsplit("/", 1)[-1]: zf.read(n) for n in zf.namelist()
                if n.lower().endswith(".pdf")
                and (names is None or n.rsplit("/", 1)[-1] in names)}


def page_texts(blob: bytes, pages: int | None = None) -> list[str]:
    from pypdf import PdfReader                    # noqa: PLC0415
    reader = PdfReader(io.BytesIO(blob))
    chosen = reader.pages if pages is None else reader.pages[:pages]
    return [(p.extract_text() or "") for p in chosen]


def read_b7(text: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, int]],
                                dict[str, int]]:
    """Table B7 as {district: {"region", "counts"}}, {region: counts} (its total
    rows) and the national row's counts, every figure checked."""
    districts: dict[str, dict[str, Any]] = {}
    regions: dict[str, dict[str, int]] = {}
    national: dict[str, int] = {}
    region, label = None, []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        if ROW.match(line):
            figures = [int(x.replace(",", "")) for x in line.split()]
            counts = dict(zip(COLUMNS, figures[:7]))
            name = " ".join(label)
            label = []
            if sum(counts.values()) != figures[7]:
                raise SystemExit(f"uganda_2002: Table B7, {name or '?'}: the religions make "
                                 f"{sum(counts.values()):,}, not {figures[7]:,}")
            if name == "UGANDA":
                national = counts
            elif name in ("Region", "Regional Total"):
                if region is None or region in regions:
                    raise SystemExit(f"uganda_2002: Table B7: a total row with no region open "
                                     f"({region})")
                regions[region] = counts
            elif region and name:
                districts[name] = {"region": region, "counts": counts}
            else:
                raise SystemExit(f"uganda_2002: Table B7: figures without a district: {line}")
            continue
        if line in REGIONS:
            region, label = line, []
        elif SKIP.match(line):
            label = []
        else:
            label.append(line)
    if len(districts) != DISTRICTS or set(regions) != set(REGIONS):
        raise SystemExit(f"uganda_2002: Table B7: {len(districts)} districts, regions "
                         f"{sorted(regions)}")
    for name, counts in regions.items():
        made = {c: sum(d["counts"][c] for d in districts.values() if d["region"] == name)
                for c in COLUMNS}
        if made != counts:
            raise SystemExit(f"uganda_2002: Table B7: {name}'s districts make {made}, not "
                             f"its total row {counts}")
    made = {c: sum(r[c] for r in regions.values()) for c in COLUMNS}
    if made != national or sum(national.values()) != NATIONAL_B7:
        raise SystemExit(f"uganda_2002: Table B7: the regions make {made}, the national row "
                         f"{national}")
    return districts, regions, national


def read_3a(text: str) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Table 3A as [(district, [its counties])], each row {name, male, female,
    total}: a district row is followed by its counties, whose totals make it."""
    rows = []
    for raw in text.splitlines():
        tokens = raw.split()
        first = next((i for i, t in enumerate(tokens) if re.fullmatch(r"\d+", t)), None)
        if first is None or first == 0:
            continue
        numbers = [int(t) for t in tokens[first:first + 4] if re.fullmatch(r"\d+", t)]
        if len(numbers) < 4:
            continue
        _, male, female, total = numbers
        if male + female != total:
            raise SystemExit(f"uganda_2002: Table 3A: {raw.strip()}: men and women do not "
                             "make the total")
        rows.append({"name": " ".join(tokens[:first]), "male": male, "female": female,
                     "total": total})
    if not rows or rows[0]["name"] != "UGANDA" or rows[0]["total"] != NATIONAL_3A:
        raise SystemExit("uganda_2002: Table 3A does not open with Uganda's 24,442,084")
    out, i = [], 1
    while i < len(rows):
        district, j, made = rows[i], i + 1, 0
        while j < len(rows) and made < district["total"]:
            made += rows[j]["total"]
            j += 1
        if made != district["total"]:
            raise SystemExit(f"uganda_2002: Table 3A: {district['name']}'s counties make "
                             f"{made:,}, not {district['total']:,}")
        out.append((district, rows[i + 1:j]))
        i = j
    if len(out) != DISTRICTS or sum(d["total"] for d, _ in out) != NATIONAL_3A:
        raise SystemExit(f"uganda_2002: Table 3A: {len(out)} districts")
    return out


def whole_districts(codes: list[str], counties: list[dict[str, Any]]) -> bool:
    """Whether the 2024 units placed in a polygon are every county of the 2024
    districts they belong to."""
    placed = set(codes)
    held = {c["district_code"] for c in counties if c["code"] in placed}
    every = {c["code"] for c in counties if c["district_code"] in held}
    return bool(placed) and placed == every


def note_for_region(name: str) -> str:
    return (f"The 2002 census's count of the {name}'s people by religion (Table B7, which "
            f"leaves out people enumerated in hotels); {LATER}. {OTHER}")


def note_for_county(district: str) -> str:
    return (f"The 2002 census's count of {district} District's people by religion, the "
            f"district being this county alone in 2002 (Table B7, which leaves out people "
            f"enumerated in hotels); {LATER}. {OTHER}")


def build(districts: dict[str, dict[str, Any]], regions: dict[str, dict[str, int]],
          table3a: list[tuple[dict[str, Any], list[dict[str, Any]]]],
          admin1: list[dict[str, Any]], admin2: list[dict[str, Any]],
          placed: dict[str, list[str]], straddling: dict[str, list[str]],
          counties: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    source = {"field": "religion", "name": SOURCE, "url": PAGE, "year": YEAR,
              "license": LICENCE}
    records, report = [], []
    shapes1 = {s["name"].strip(): s for s in admin1}
    for short, label in REGIONS.items():
        shape = shapes1.get(label)
        if shape is None:
            raise SystemExit(f"uganda_2002: no polygon for {label}")
        rows = shares({LABELS[c]: n for c, n in regions[short].items()})
        records.append(record(f"UGA-2002-{shape['id']}", label, level="admin1", parent="UGA",
                              country="UGA", match_by="shape_id", shape_id=shape["id"],
                              religion=rows, religion_year=dated(rows, YEAR),
                              religion_note=note_for_region(label), sources=[source]))
    by_fold = {fold(k): k for k in districts}
    for district, its in table3a:
        if len(its) != 1:
            continue
        county = its[0]
        key = by_fold.get(DISTRICT_ALIASES.get(fold(district["name"]), fold(district["name"])))
        if key is None:
            raise SystemExit(f"uganda_2002: {district['name']} is in Table 3A, not Table B7")
        region = shapes1[REGIONS[districts[key]["region"]]]["id"]
        want = COUNTY_ALIASES.get(fold(county["name"]), fold(county["name"]))
        shapes = [s for s in admin2 if fold(s["name"]) == want and s["parent"] == region]
        if len(shapes) != 1:
            raise SystemExit(f"uganda_2002: {len(shapes)} polygons for {county['name']} in "
                             f"{districts[key]['region']}")
        shape = shapes[0]
        title = key.title()
        codes = placed.get(shape["id"])
        if codes and whole_districts(codes, counties):
            got = {c["code"]: c for c in counties if c["code"] in set(codes)}
            rows = shares({LABELS[c]: n for c, n in districts[key]["counts"].items()})
            records.append(record(f"UGA-2002-{shape['id']}", shape["name"].strip(),
                                  level="admin2", parent="UGA", country="UGA",
                                  match_by="shape_id", shape_id=shape["id"], religion=rows,
                                  religion_year=dated(rows, YEAR),
                                  religion_note=note_for_county(title), sources=[source]))
            report.append(f"{shape['name']}: {title} District of 2002 ({county['total']:,} "
                          f"people), the polygon being the 2024 units "
                          f"{sorted(c['name'] for c in got.values())} "
                          f"({sum(c['total'] for c in got.values()):,} in 2024)")
            continue
        why = (f"{title} District, which was this county alone in 2002, has its religion "
               "published in the 2002 census, but the county as drawn here does not keep the "
               "district's lines in the counts taken since, so it is not shown to be the "
               "district's ground and no count is given for it.")
        records.append(record(f"UGA-2002-{shape['id']}", shape["name"].strip(), level="admin2",
                              parent="UGA", country="UGA", match_by="shape_id",
                              shape_id=shape["id"], religion=gap(NOT_AVAILABLE, why),
                              sources=[source]))
        crossing = straddling.get(shape["id"])
        report.append(f"{shape['name']}: {title} District of 2002, not written ("
                      + (f"crossed by {crossing}" if crossing else
                         f"the 2024 units {codes} are not whole districts") + ")")
    return records, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--titles", action="store_true", help="print each table's first lines")
    ap.add_argument("--member", default="", help="print one table's first pages")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--lines", type=int, default=9)
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    args = ap.parse_args()
    if args.titles or args.member:
        tables = members()
        for name in sorted(tables, key=lambda n: (len(n), n)):
            if args.member and name != args.member:
                continue
            texts = page_texts(tables[name], 1 if args.titles else args.pages)
            log(f"== {name}")
            for text in texts:
                lines = [" ".join(x.split()) for x in text.splitlines() if x.strip()]
                for line in lines[:args.lines] if args.titles else lines:
                    log(f"    {line[:200]}")
        return 0
    from .uganda_counties import PLACED, STRADDLING  # noqa: PLC0415
    tables = members((B7, T3A))
    districts, regions, national = read_b7("\n".join(page_texts(tables[B7])))
    table3a = read_3a("\n".join(page_texts(tables[T3A])))
    log(f"  Table B7: {len(districts)} districts in 4 regions making {NATIONAL_B7:,}; Table 3A: "
        f"{len(table3a)} districts, {sum(1 for _, c in table3a if len(c) == 1)} of them one "
        "county")
    admin1 = json.loads((SITE / "admin1" / "UGA.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "UGA.units.json").read_text())
    counties = json.loads(POINTS.read_text())
    records, report = build(districts, regions, table3a, admin1, admin2, PLACED, STRADDLING,
                            counties)
    for line in report:
        log("  " + line)
    for r in records:
        rel = r["religion"]
        log(f"  {r['level']} {r['name']}: "
            + (", ".join(f"{g['group']} {g['pct']}" for g in rel[:4])
               if isinstance(rel, list) else "stated"))
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
