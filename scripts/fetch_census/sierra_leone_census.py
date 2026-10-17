#!/usr/bin/env python3
"""Sierra Leone -- the 2015 Population and Housing Census, by region and district.

The map draws Sierra Leone as the 2015 census counted it: four regions
(Eastern, Northern, Southern, and Western Area) and fourteen districts. The
North West Province and the Falaba and Karene districts were made in 2017 out
of the Northern Province and three of its districts, after the census, and the
boundary file does not draw them; every figure here is for the census's own
units, which are the polygons.

Statistics Sierra Leone published the census's analysis in October 2017, and
UNFPA's Sierra Leone office keeps the reports. Two of them are read:

* the **National Analytical Report**: Table A3.1, the population by region,
  district and sex (2015 columns); Table 3.12, the median age of each region
  and district, as the office computed it; and Table 3.23, the three most
  common main languages of each region's and district's household population
  with the share of everyone else.
* the **Thematic Report on Population Structure and Population
  Distribution**: Table 5.2, ethnic composition, fifteen groups and the
  non-Sierra Leoneans, and Table 5.3, the religious affiliation of the
  household population, both by region and district.

The thematic report's own sex ratios (its Table 5.1) are not used: several of
them contradict the counts of men and women in the analytical report (it
prints Bombali at 98.7 men per 100 women where its counts give 95.7, and
Moyamba at 98.7 where they give 93.2), and the analytical report's Table 3.16
agrees with the counts. The ratio is taken from the counts.

**Checks before anything is written.** Every unit is read from every table.
Men and women make each total; the districts make their regions and the
regions make Sierra Leone, 7,092,113. Each row's age shares, religious shares,
and language shares with their remainder make 100 (within rounding); the
ethnic shares make at least 99 and at most 100.5, the rest being the people the
table does not place in a group.

Usage:
    python -m scripts.fetch_census.sierra_leone_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json

NAR = ("https://sierraleone.unfpa.org/sites/default/files/pub-pdf/"
       "National%20Analytical%20Report.pdf")
THEMATIC = ("https://sierraleone.unfpa.org/sites/default/files/pub-pdf/"
            "Population%20structure%20Report_1.pdf")
PUBLISHER = "Statistics Sierra Leone, 2015 Population and Housing Census"
SRC_POP = f"{PUBLISHER}, National Analytical Report (2017), Table A3.1"
SRC_AGE = f"{PUBLISHER}, National Analytical Report (2017), Table 3.12"
SRC_LANG = f"{PUBLISHER}, National Analytical Report (2017), Table 3.23"
SRC_ETH = (f"{PUBLISHER}, Thematic Report on Population Structure and Population "
           "Distribution (2017), Table 5.2")
SRC_REL = (f"{PUBLISHER}, Thematic Report on Population Structure and Population "
           "Distribution (2017), Table 5.3")
LICENCE = ("Statistics Sierra Leone: may be freely quoted or reproduced, in part or in full, "
           "provided that the source is acknowledged")
YEAR = 2015
NATIONAL = (7_092_113, 3_490_978, 3_601_135)
OUT = "sierra_leone_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
UNIT = "males_per_100_females"

REGIONS = {"Eastern": ("Kailahun", "Kenema", "Kono"),
           "Northern": ("Bombali", "Kambia", "Koinadugu", "Port Loko", "Tonkolili"),
           "Southern": ("Bo", "Bonthe", "Moyamba", "Pujehun"),
           "Western": ("Western Area Rural", "Western Area Urban")}
DISTRICTS = tuple(d for ds in REGIONS.values() for d in ds)
NATION = ("Sierra Leone", "Total country", "Total")
# The census's region names -> the boundary file's.
DRAWN_REGION = {"Eastern": "Eastern", "Northern": "Northern", "Southern": "Southern",
                "Western": "Western Area"}
ETHNIC_1 = ("Krio", "Mende", "Temne", "Limba", "Kono", "Koranko", "Fullah", "Susu")
ETHNIC_2 = ("Kissi", "Loko", "Madingo", "Sherbro", "Yalunka", "Krim", "Vai",
            "Non-Sierra Leonean")
RELIGIONS = ("Christianity", "Islam", "Baha'i", "Traditional", "Other", "No religion")
# Table 3.23 prints Pujehun's third language as "Time": Temne, the only
# language of the table so spelled otherwise.
LANGUAGE_SPELLING = {"Time": "Temne"}

NUM = r"-?\d[\d,]*(?:\.\d+)?"


def number(text: str) -> float:
    return float(text.replace(",", ""))


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def pages_of(blob: bytes) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob))
    return [(page.extract_text() or "") for page in reader.pages]


def joined_lines(text: str) -> list[str]:
    """The page's lines, with a unit name the table breaks over two lines put
    back together ("Western Area" / "Rural 67,106 ..." or "Western" / "Area
    Rural 3.4 ...")."""
    out: list[str] = []
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        if out and out[-1] in ("Western", "Western Area") and re.match(r"^(Area|Rural|Urban)\b",
                                                                    line):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return out


def unit_of(label: str) -> str | None:
    """The census unit a row's label names, or None."""
    label = " ".join(label.split())
    if label in NATION:
        return "Sierra Leone"
    if label in ("Western", "Western Area"):
        return "Western"
    if label in REGIONS or label in DISTRICTS:
        return label
    return None


def numeric_rows(text: str, count: int) -> dict[str, list[float]]:
    """{unit: its figures} for the lines of a page that are a unit's name and
    exactly ``count`` figures."""
    row = re.compile(rf"^(?P<name>[A-Za-z][A-Za-z .]*?)\s+"
                     rf"(?P<nums>{NUM}(?:\s+{NUM}){{{count - 1}}})$")
    out: dict[str, list[float]] = {}
    for line in joined_lines(text):
        m = row.match(line)
        if not m:
            continue
        unit = unit_of(m.group("name"))
        if unit and unit not in out:
            out[unit] = [number(x) for x in m.group("nums").split()]
    return out


def page_with(pages: list[str], *needles: str, start: int = 0) -> list[int]:
    """The indices of the pages that carry every needle."""
    return [i for i, text in enumerate(pages) if i >= start
            and all(n.lower() in " ".join(text.split()).lower() for n in needles)]


def every_unit(table: dict[str, Any], what: str) -> None:
    want = {"Sierra Leone", *REGIONS, *DISTRICTS}
    missing = sorted(want - set(table))
    if missing:
        raise SystemExit(f"sierra_leone_census: {what}: no row for {missing}")


def read_population(pages: list[str]) -> dict[str, tuple[int, int, int]]:
    """Table A3.1's 2015 columns: {unit: (total, men, women)}."""
    hits = page_with(pages, "Table A3.1", "Total population by region, district and sex")
    for i in hits:
        rows = numeric_rows(pages[i], 7)
        if len(rows) >= 19:
            out = {u: (int(v[4]), int(v[5]), int(v[6])) for u, v in rows.items()}
            every_unit(out, "Table A3.1")
            return out
    raise SystemExit(f"sierra_leone_census: Table A3.1 not found (pages {hits})")


def read_median(pages: list[str]) -> dict[str, float]:
    """Table 3.12's median ages: {unit: median}."""
    hits = page_with(pages, "Table 3.12", "median age")
    for i in hits:
        rows = numeric_rows(pages[i], 7)
        if len(rows) >= 19:
            out = {}
            for u, v in rows.items():
                if abs(sum(v[:5]) - 100) > 0.25 or abs(v[5] - 100) > 0.05:
                    raise SystemExit(f"sierra_leone_census: Table 3.12: {u}'s age shares make "
                                     f"{sum(v[:5]):.1f}")
                out[u] = v[6]
            every_unit(out, "Table 3.12")
            return out
    raise SystemExit(f"sierra_leone_census: Table 3.12 not found (pages {hits})")


LANG_ROW = re.compile(rf"^(?P<name>[A-Za-z][A-Za-z ]*?)\s+(?P<l1>[A-Z][a-z]+)\s+(?P<p1>{NUM})\s+"
                      rf"(?P<l2>[A-Z][a-z]+)\s+(?P<p2>{NUM})\s+(?P<l3>[A-Z][a-z]+)\s+(?P<p3>{NUM})"
                      rf"\s+(?P<other>{NUM})\s+(?P<total>{NUM})$")


def read_language(pages: list[str]) -> dict[str, dict[str, float]]:
    """Table 3.23: {unit: {language: share, "Other": share}}."""
    hits = page_with(pages, "Table 3.23", "most common main language")
    for i in hits:
        out: dict[str, dict[str, float]] = {}
        for line in joined_lines(pages[i]):
            m = LANG_ROW.match(line)
            if not m:
                continue
            unit = unit_of(m.group("name"))
            if not unit or unit in out:
                continue
            shares = {}
            for n in (1, 2, 3):
                lang = LANGUAGE_SPELLING.get(m.group(f"l{n}"), m.group(f"l{n}"))
                shares[lang] = number(m.group(f"p{n}"))
            shares["Other"] = number(m.group("other"))
            # Each share is rounded on its own: the Southern Region's make 99.5.
            made = sum(shares.values())
            if abs(made - number(m.group("total"))) > 0.6:
                raise SystemExit(f"sierra_leone_census: Table 3.23: {unit}'s shares make "
                                 f"{made:.1f}")
            if abs(made - 100) > 0.25:
                log(f"  Table 3.23: {unit}'s shares make {made:.1f}, as printed")
            out[unit] = shares
        if len(out) >= 19:
            every_unit(out, "Table 3.23")
            return out
    raise SystemExit(f"sierra_leone_census: Table 3.23 not found (pages {hits})")


def read_ethnicity(pages: list[str]) -> dict[str, dict[str, float]]:
    """Table 5.2, both halves: {unit: {group: share}}."""
    first, second = {}, {}
    for i in page_with(pages, "Table 5.2", "Ethnic composition"):
        text = " ".join(pages[i].split())
        rows = numeric_rows(pages[i], 8)
        if "Kissi Loko" in text:
            second.update(rows)
        elif "Krio Mende" in text:
            first.update(rows)
    every_unit(first, "Table 5.2")
    every_unit(second, "Table 5.2 (continued)")
    out = {}
    for unit in first:
        shares = dict(zip(ETHNIC_1, first[unit])) | dict(zip(ETHNIC_2, second[unit]))
        made = sum(shares.values())
        if not 99.0 <= made <= 100.5:
            raise SystemExit(f"sierra_leone_census: Table 5.2: {unit}'s groups make {made:.1f}")
        out[unit] = shares
    return out


def read_religion(pages: list[str]) -> dict[str, dict[str, float]]:
    """Table 5.3 (it continues over a page): {unit: {religion: share}}."""
    rows: dict[str, list[float]] = {}
    for i in page_with(pages, "Table 5.3", "Religious composition"):
        for unit, v in numeric_rows(pages[i], 6).items():
            rows.setdefault(unit, v)
    every_unit(rows, "Table 5.3")
    out = {}
    for unit, v in rows.items():
        # Sierra Leone's own row makes 100.5 (Baha'i 0.5 where no region
        # reaches 0.2); it is not written, and only logged.
        if abs(sum(v) - 100) > 0.3:
            if unit == "Sierra Leone":
                log(f"  Table 5.3: Sierra Leone's religions make {sum(v):.1f}, as printed")
            else:
                raise SystemExit(f"sierra_leone_census: Table 5.3: {unit}'s religions make "
                                 f"{sum(v):.1f}")
        out[unit] = dict(zip(RELIGIONS, v))
    return out


def check_population(pop: dict[str, tuple[int, int, int]]) -> None:
    for unit, (t, m, f) in pop.items():
        if m + f != t:
            raise SystemExit(f"sierra_leone_census: {unit}: men and women make {m + f:,}, "
                             f"not {t:,}")
    if pop["Sierra Leone"] != NATIONAL:
        raise SystemExit(f"sierra_leone_census: Sierra Leone is {pop['Sierra Leone']}")
    for col in range(3):
        if sum(pop[r][col] for r in REGIONS) != pop["Sierra Leone"][col]:
            raise SystemExit("sierra_leone_census: the regions do not make Sierra Leone")
        for region, districts in REGIONS.items():
            if sum(pop[d][col] for d in districts) != pop[region][col]:
                raise SystemExit(f"sierra_leone_census: {region}'s districts do not make it")


def shares_list(shares: dict[str, float]) -> list[dict[str, Any]]:
    out = [{"group": g, "pct": round(p, 1)} for g, p in shares.items() if p > 0]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out


def fields(unit: str, label: str, tables: dict[str, Any]) -> dict[str, Any]:
    t, m, f = tables["population"][unit]
    return {
        "population": measure(t, year=YEAR, source=SRC_POP),
        "population_note": f"The 2015 census's count for {label}.",
        "sex_ratio": measure(round(100 * m / f, 1), unit=UNIT, year=YEAR, source=SRC_POP),
        "median_age": measure(tables["median"][unit], unit="years", year=YEAR, source=SRC_AGE),
        "median_age_note": "Statistics Sierra Leone's own median age, from the 2015 census.",
        "religion": shares_list(tables["religion"][unit]),
        "religion_year": YEAR,
        "religion_note": ("Religious affiliation of the household population as the 2015 "
                          "census counts it."),
        "ethnicity": shares_list(tables["ethnicity"][unit]),
        "ethnicity_year": YEAR,
        "ethnicity_note": ("Ethnic group as the 2015 census counts it, with the people who are "
                           "not Sierra Leoneans shown apart. The shares are of the whole "
                           "population, and the table places a few tenths of a per cent in no "
                           "group."),
        "language": shares_list(tables["language"][unit]),
        "language_year": YEAR,
        "language_note": ("Main language of the household population as the 2015 census "
                          "counts it: the census publishes the three most common for each "
                          "region and district, and everyone else together."),
        "sources": [
            {"field": "population/sex_ratio", "name": SRC_POP, "url": NAR, "license": LICENCE,
             "year": YEAR},
            {"field": "median_age", "name": SRC_AGE, "url": NAR, "license": LICENCE,
             "year": YEAR},
            {"field": "language", "name": SRC_LANG, "url": NAR, "license": LICENCE,
             "year": YEAR},
            {"field": "ethnicity", "name": SRC_ETH, "url": THEMATIC, "license": LICENCE,
             "year": YEAR},
            {"field": "religion", "name": SRC_REL, "url": THEMATIC, "license": LICENCE,
             "year": YEAR},
        ],
    }


def build(tables: dict[str, Any], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> list[dict[str, Any]]:
    """One record per polygon, each bound by its own name to one census unit."""
    region_of = {DRAWN_REGION[r]: r for r in REGIONS}
    drawn1 = {s["name"]: s for s in admin1}
    if sorted(drawn1) != sorted(region_of):
        raise SystemExit(f"sierra_leone_census: region polygons {sorted(drawn1)}")
    drawn2 = {s["name"]: s for s in admin2}
    if sorted(drawn2) != sorted(DISTRICTS):
        raise SystemExit(f"sierra_leone_census: district polygons {sorted(drawn2)}")
    records = []
    for region, districts in REGIONS.items():
        shape = drawn1[DRAWN_REGION[region]]
        for d in districts:
            if drawn2[d]["parent"] != shape["id"]:
                raise SystemExit(f"sierra_leone_census: {d} is not drawn in {shape['name']}")
        label = "the Western Area" if region == "Western" else f"the {region} Region"
        records.append(record(
            f"SLE-2015-region-{region.lower()}", shape["name"], level="admin1", parent="SLE",
            country="SLE", match_by="shape_id", shape_id=shape["id"],
            **fields(region, label, tables)))
    for d in DISTRICTS:
        shape = drawn2[d]
        records.append(record(
            f"SLE-2015-{d.lower().replace(' ', '-')}", shape["name"], level="admin2",
            parent="SLE", country="SLE", match_by="shape_id", shape_id=shape["id"],
            **fields(d, d if d.startswith("Western") else f"{d} District", tables)))
    return records


def read() -> dict[str, Any]:
    nar = http_get(NAR, binary=True, timeout=300)
    thematic = http_get(THEMATIC, binary=True, timeout=300)
    assert isinstance(nar, bytes) and isinstance(thematic, bytes)
    log(f"  National Analytical Report: {len(nar):,} bytes, sha256 {digest(nar)}")
    log(f"  Thematic report: {len(thematic):,} bytes, sha256 {digest(thematic)}")
    p_nar, p_them = pages_of(nar), pages_of(thematic)
    tables = {"population": read_population(p_nar), "median": read_median(p_nar),
              "language": read_language(p_nar), "ethnicity": read_ethnicity(p_them),
              "religion": read_religion(p_them)}
    check_population(tables["population"])
    return tables


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    tables = read()
    for unit in ("Sierra Leone", *REGIONS, *DISTRICTS):
        t, m, f = tables["population"][unit]
        log(f"  {unit}: {t:,} ({m:,} men, {f:,} women), median {tables['median'][unit]}, "
            f"languages {tables['language'][unit]}, religion "
            f"{dict(list(tables['religion'][unit].items())[:2])}, ethnic groups "
            f"{sum(tables['ethnicity'][unit].values()):.1f}%")
    admin1 = json.loads((SITE / "admin1" / "SLE.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "SLE.units.json").read_text())
    records = build(tables, admin1, admin2)
    log(f"  {len(records)} records written")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
