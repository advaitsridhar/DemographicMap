#!/usr/bin/env python3
"""Namibia -- the 2023 census by region: count, sex ratio and median age.

The Namibia Statistics Agency's "2023 Population and Housing Census Main
Report" (28 October 2024) prints, for the country and its fourteen regions,

    Table 2.2  population by sex
    Table 2.3  percent distribution by major age group (0-4, 5-14, 15-34,
               35-59, 60+), with the total
    Table 2.4  the youth (15-34) population and its percent distribution by
               five-year group (15-19, 20-24, 25-29, 30-34)

The report's address on the census site no longer answers; the Internet
Archive's copy of it is read.

Written: for the map's thirteen first-level units, the census's count, the
sex ratio (men per thousand women) and the median age. The median is
interpolated within the five-year group that holds the middle person, from
the people under 15 (Table 2.3) and in each five-year youth group (the youth
count of Table 2.4 spread by its percentages); as the shares are printed to a
tenth of a percent, a median can be off by a few hundredths of a year.

**The units.** The map draws the regions as they were before 2013: Kavango is
the census's Kavango East and Kavango West added together, Caprivi is
Zambezi, and Karas is //Kharas.

**Checks before anything is written.** Every region's men and women make its
total; the regions make the census's 3,022,401; each region's age shares make
100 to within their rounding, and its youth count is its 15-34 share of its
total to within the same rounding.

Usage:
    python -m scripts.fetch_census.namibia_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
from itertools import combinations
from typing import Any

from ._shared import PROCESSED, log, measure, record, write_json
from .southern_africa_common import fetch, key, sex_ratio, units

URL = ("https://census.nsanamibia.com/wp-content/uploads/2024/10/"
       "2023-Population-and-Housing-Census-Main-Report-28-Oct-2024.pdf")
ARCHIVE = ("20241104035225", "2024", "2025")
SOURCE = "Namibia Statistics Agency, 2023 Population and Housing Census Main Report"
LICENCE = "Namibia Statistics Agency publication (reuse with attribution)"
YEAR = 2023
NATIONAL = 3_022_401
OUT = "namibia_census.json"
REGIONS = ("//Kharas", "Erongo", "Hardap", "Kavango East", "Kavango West", "Khomas", "Kunene",
           "Ohangwena", "Omaheke", "Omusati", "Oshana", "Oshikoto", "Otjozondjupa", "Zambezi")
# The map's first-level units (reduced) -> the census's regions.
MAP = {"karas": ["//Kharas"], "caprivi": ["Zambezi"], "kavango": ["Kavango East", "Kavango West"]}

DIGITS = r"\d{1,3}(?: \d{3})*"
DEC = r"\d+\.\d"
T22 = re.compile(rf"^(?P<name>[/A-Za-z ]+?) (?P<nums>{DIGITS}(?: {DIGITS})*) (?P<pm>{DEC}) "
                 rf"(?P<pf>{DEC})$")
T23 = re.compile(rf"^(?P<name>[/A-Za-z ]+?) (?P<total>{DIGITS}) (?P<a>{DEC}) (?P<b>{DEC}) "
                 rf"(?P<c>{DEC}) (?P<d>{DEC}) (?P<e>{DEC})$")
T24 = re.compile(rf"^(?P<name>[/A-Za-z ]+?) (?P<youth>{DIGITS}) (?P<a>{DEC}) (?P<b>{DEC}) "
                 rf"(?P<c>{DEC}) (?P<d>{DEC})$")


def number(text: str) -> int:
    return int(text.replace(" ", ""))


def sex_split(nums: str) -> tuple[int, int, int] | None:
    """Total, men and women from their digit groups: the one split whose men
    and women make the total."""
    tokens = nums.split()

    def num(parts: list[str]) -> int | None:
        if not parts or (len(parts) > 1 and (len(parts[0]) > 3
                                             or any(len(p) != 3 for p in parts[1:]))):
            return None
        return int("".join(parts))

    found = []
    for i, j in combinations(range(1, len(tokens)), 2):
        t, m, f = num(tokens[:i]), num(tokens[i:j]), num(tokens[j:])
        if None not in (t, m, f) and m + f == t:
            found.append((t, m, f))
    return found[0] if len(found) == 1 else None


def parse(text: str) -> dict[str, dict[str, Any]]:
    """{region: {"total", "men", "women", "shares": [0-4, 5-14, 15-34, 35-59,
    60+], "youth", "youth_shares": [15-19, 20-24, 25-29, 30-34]}} for the
    country ("Namibia") and the regions, each table's first line for each."""
    names = {key(n): n for n in REGIONS + ("Namibia",)}
    out: dict[str, dict[str, Any]] = {n: {} for n in names.values()}
    for raw in text.splitlines():
        line = " ".join(raw.split())
        for pattern, kind in ((T23, "t23"), (T24, "t24"), (T22, "t22")):
            hit = pattern.match(line)
            if not hit or key(hit.group("name")) not in names:
                continue
            row = out[names[key(hit.group("name"))]]
            if kind == "t22" and "men" not in row:
                split = sex_split(hit.group("nums"))
                if split:
                    row["total"], row["men"], row["women"] = split
            elif kind == "t23" and "shares" not in row:
                row["total23"] = number(hit.group("total"))
                row["shares"] = [float(hit.group(g)) for g in "abcde"]
            elif kind == "t24" and "youth" not in row:
                row["youth"] = number(hit.group("youth"))
                row["youth_shares"] = [float(hit.group(g)) for g in "abcd"]
            break
    check(out)
    return out


def check(table: dict[str, dict[str, Any]]) -> None:
    missing = [(n, f) for n, row in table.items() for f in ("men", "shares", "youth")
               if f not in row]
    if missing:
        raise SystemExit(f"namibia_census: lines not read: {missing}")
    if table["Namibia"]["total"] != NATIONAL:
        raise SystemExit(f"namibia_census: the country is {table['Namibia']['total']:,}")
    for f in ("total", "men", "women"):
        made = sum(table[r][f] for r in REGIONS)
        if made != table["Namibia"][f]:
            raise SystemExit(f"namibia_census: the regions make {made:,} {f}")
    for name, row in table.items():
        if row["total23"] != row["total"] or abs(sum(row["shares"]) - 100) > 0.3 \
                or abs(sum(row["youth_shares"]) - 100) > 0.3:
            raise SystemExit(f"namibia_census: {name}'s age shares do not add up: {row}")
        expected = row["total"] * row["shares"][2] / 100
        if abs(row["youth"] - expected) > 0.0006 * row["total"]:
            raise SystemExit(f"namibia_census: {name}'s youth count {row['youth']:,} is not its "
                             f"15-34 share of {row['total']:,}")


def bands(row: dict[str, Any]) -> list[tuple[int, int | None, float]]:
    """People by age band: under 15, the four five-year youth groups, 35 and
    over (open, never holding the median here)."""
    under15 = row["total"] * (row["shares"][0] + row["shares"][1]) / 100
    youth = [row["youth"] * s / sum(row["youth_shares"]) for s in row["youth_shares"]]
    rest = row["total"] - under15 - sum(youth)
    return ([(0, 15, under15)] + [(15 + 5 * i, 5, n) for i, n in enumerate(youth)]
            + [(35, None, rest)])


def median_of(groups: list[tuple[int, int | None, float]]) -> float:
    total = sum(n for _, _, n in groups)
    half, before = total / 2, 0.0
    for lo, width, n in groups:
        if before + n >= half:
            if width is None or lo == 0:
                raise SystemExit("namibia_census: the median falls outside the youth groups")
            return round(lo + width * (half - before) / n, 1)
        before += n
    raise SystemExit("namibia_census: no median")


def build(table: dict[str, dict[str, Any]], admin1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    used: list[str] = []
    sources = [{"field": "population/sex_ratio/median_age", "name": f"{SOURCE}, Tables 2.2 to 2.4",
                "url": URL, "license": LICENCE, "year": YEAR}]
    for shape in admin1:
        k = key(shape["name"])
        regions = MAP.get(k) or [n for n in REGIONS if key(n) == k]
        if not regions:
            raise SystemExit(f"namibia_census: no census region for {shape['name']!r}")
        used += regions
        rows = [table[r] for r in regions]
        groups: dict[tuple[int, int | None], float] = {}
        for row in rows:
            for lo, width, n in bands(row):
                groups[(lo, width)] = groups.get((lo, width), 0.0) + n
        total = sum(r["total"] for r in rows)
        note = (f"The 2023 census's count for {regions[0]}." if len(regions) == 1 else
                f"The 2023 census's counts for {regions[0]} and {regions[1]} added together: the "
                f"map draws them as one region, as before 2013.")
        if len(regions) == 1 and key(regions[0]) != k:
            note = f"The 2023 census's count for {regions[0]}, drawn here as {shape['name']}."
        out.append(record(
            f"NAM-2023-region-{k}", shape["name"], level="admin1", parent="NAM", country="NAM",
            match_by="shape_id", shape_id=shape["id"], sources=sources,
            population=measure(total, year=YEAR, source=f"{SOURCE}, Table 2.2"),
            population_note=note,
            sex_ratio=sex_ratio(sum(r["men"] for r in rows), sum(r["women"] for r in rows),
                                year=YEAR, source=f"{SOURCE}, Table 2.2"),
            median_age=measure(median_of(sorted(((lo, w, n) for (lo, w), n in groups.items()),
                                                key=lambda g: g[0])),
                               year=YEAR, source=f"{SOURCE}, Tables 2.3 and 2.4"),
            median_age_note=("Interpolated within the five-year age group that holds the middle "
                             "person, from the 2023 census's shares of the people under 15 "
                             "(Table 2.3) and of the youth in each five-year group from 15 to "
                             "34 (Table 2.4).")))
    if sorted(used) != sorted(REGIONS):
        raise SystemExit(f"namibia_census: regions on no polygon or on two: {sorted(used)}")
    return out


def text_of(blob: bytes) -> str:
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages[30:42])


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob, where = fetch(URL, archive=ARCHIVE, office=False, expect=b"%PDF")
    log(f"  read {where}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    table = parse(text_of(blob))
    log(f"  the country's median age: {median_of(bands(table['Namibia']))}")
    records = build(table, units("NAM", "admin1"))
    for r in records:
        log(f"  {r['name']}: {r['population']['value']:,}, ratio {r['sex_ratio']['value']}, "
            f"median {r['median_age']['value']}; {r['population_note']}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
