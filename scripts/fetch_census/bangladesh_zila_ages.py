#!/usr/bin/env python3
"""Bangladesh -- every zila's median age, from the 2022 census's Community Series.

The Bureau publishes the 2022 census below the division in its *Community
Series*: one Excel workbook per zila, linked from its census page under
"Population & Housing Census 2022 (District Report & Community Series)"
(``PAGE``, read on 9 October 2026) and kept on the Bureau's own object
storage. Every workbook has the same nineteen sheets, C-01 to C-18 and a page
of SDG indicators, and each sheet runs from the zila down through its city
corporations, upazilas, paurashavas and unions to the mauza and the village.
Two of them are read here:

* **C-01**, households and population: the population in total, its males,
  its females and its hijra (the third gender the census counts apart);
* **C-02**, the population by five-year age group, 0-4 to 80 and over, both
  sexes together.

The median is C-02's, interpolated within the five-year group that holds the
middle person. Single years of age are published only by division (the
National Report's Table P10), so nothing finer exists for a zila; the record's
note says so.

**This replaces the 2011 medians this reader used to write.** The National
Report's age tables are all by division, and the reader had concluded from
them that the 2022 census publishes no age below the division and fell back
to the 2011 census's groups. The Community Series is the 2022 census by zila,
and its figures stand on all sixty-four.

**What is checked before anything is written:**

* in every zila's C-01 the males, females and hijra make the population, and
  C-02's first row is the same zila with the same population, its seventeen
  groups adding up to it;
* the population is the one the district indicators workbook (``bangladesh``,
  ``bangladesh_district.json``) gives the same zila -- two publications of one
  census agreeing to the person -- and the sixty-four make the census's
  165,158,616;
* each division's zilas, summed group by group, are the National Report's
  Table P03 for that division plus the hijra: P03 counts males and females
  only, so every group may exceed P03's by some hijra and none may fall short
  of it, and the excess over all groups is exactly the division's hijra --
  which is what ties a workbook's columns to the ages they are printed under;
* the nation's median from the sixty-four zilas' groups is the one Table
  P03's own national groups give, and it is logged beside the median of
  Table P10's single years, which the grouping cannot reproduce exactly;
* each zila binds to exactly one drawn polygon inside its own division by
  name (the Bureau's 2018 spellings, with ``bangladesh.ALIASES`` for the
  boundary file's older ones), every drawn zila is reached, and the page's
  label for the workbook names the same zila as the workbook's own first row.

Usage:
    python -m scripts.fetch_census.bangladesh_zila_ages
"""

from __future__ import annotations

import argparse
import io
import json
import re
import urllib.error
from typing import Any

from ._shared import PROCESSED, RAW, http_get, log, measure, record, write_json
from .bangladesh import (ALIASES, DIVISION_ALIASES, REPORT, check_ages,
                         check_single_years, laid_out, read_ages,
                         read_single_years)
from .south_asia_common import (bind, fold, load_units, median_grouped,
                                median_single, report_binding, unit_keys)

YEAR = 2022
OUT = "bangladesh_zila_age.json"
PAGE = "https://bbs.gov.bd/pages/static-pages/6922e073933eb65569e27220"
STORE = ("https://objectstorage.ap-dcc-gazipur-1.oraclecloud15.com/n/axvjbnqprylg/"
         "b/V2Ministry/o/office-bbs/{}.xlsx")
SOURCE = ("Bangladesh Bureau of Statistics, Population and Housing Census 2022, "
          "Community Series (zila workbook), Table C-02: population by five-year "
          "age group")
LICENCE = "Bangladesh Bureau of Statistics publication"
# The census's enumerated population, hijra included: the sum of the district
# indicators workbook's sixty-four zilas, which the National Report's
# 165,150,492 males and females plus its hijra make.
NATION_2022 = 165_158_616
# C-02's groups, the last one open.
GROUPS: list[tuple[int, int | None]] = [*((low, low + 4) for low in range(0, 80, 5)),
                                        (80, None)]
LABELS = [f"{low}-{high}" for low, high in GROUPS[:-1]] + ["80+"]
# A heading the Bureau printed wrong in some workbooks and the column it heads:
# Rangamati's and Barishal's C-02 print "50-59" over the group between 50-54
# and 60-64. The position decides what the column is, and the check against
# Table P03 below would fail if the columns were not the ages in that order.
MISPRINTS = {(11, "50-59")}
# The Community Series as the census page lists it: division, the page's label
# for the zila, and the workbook's folder and name on the Bureau's object
# storage, in the page's order (Kushtia's was uploaded again in March 2026). The labels are the page's own, misspellings and all; each must
# name the zila the workbook's first row names (see LABEL_SPELLINGS).
ZILAS: list[tuple[str, str, str]] = [
    ("Barishal", "BARISHAL", "2024/12/c56515ca45314f6586d9d7ffae0e89a7"),
    ("Barishal", "BHOLA", "2024/12/45edbfa4a084468ca52ebc3895b77e8f"),
    ("Barishal", "PIROJPUR", "2024/12/e157dd0ff3ae4cfcb0f8804fec4c3011"),
    ("Barishal", "PATUAKHAL", "2024/12/9b566687c68045ba9dc4a5baf078494b"),
    ("Barishal", "BARGUNA", "2024/12/373ae6014cce4bab852b96c2cddaa21e"),
    ("Barishal", "JHALAKHATI", "2024/12/187d1669b3fe47ca8e0a07e9bada1252"),
    ("Chattogram", "CHATTOGRAM", "2024/12/80e929a76aa14282826502ff159a8aa5"),
    ("Chattogram", "COX'S BAZAR", "2024/12/30dc3493153848f2b825adaeec3fe941"),
    ("Chattogram", "BANDARBAN", "2024/12/7851f407961e43399592b1b6df4534f7"),
    ("Chattogram", "RANGAMATI", "2024/12/0aff8184552d4476b07064b259684f67"),
    ("Chattogram", "NOAKHALI", "2024/12/f2357c3b52ee4ba284f7750301b6ecef"),
    ("Chattogram", "FENI", "2024/12/2b9c505de31e463582957bc16a96ed2f"),
    ("Chattogram", "CUMILLA", "2024/12/4c96db4232fe4ea9b2065c48c992a84d"),
    ("Chattogram", "CHANDPUR", "2024/12/18332832c988417c97370153dc7c5714"),
    ("Chattogram", "BRAHMMANBARIA", "2024/12/a5a9606aa66a48acb6a4eb93d51fab3c"),
    ("Chattogram", "KHAGRACHHARI", "2024/12/c76f262b21804911867771950482c1a8"),
    ("Chattogram", "LAKSHMIPUR", "2024/12/7557ac06285f4bf28273e40f491200cc"),
    ("Dhaka", "DHAKA", "2024/12/b15f7a7f63ff451e86ce7fd7cca9493d"),
    ("Dhaka", "NARAYANGANJ", "2024/12/ecfcd0ae1c0e4702af5d693c64d515d3"),
    ("Dhaka", "GAZIPUR", "2024/12/fa819560a3a243e08b6e715f2572141f"),
    ("Dhaka", "MANIKGANJ", "2024/12/70930e5767e9432b9076e49c4673d10c"),
    ("Dhaka", "NARSINGDI", "2024/12/154c006ad6394203a8f07452f3da6b48"),
    ("Dhaka", "FARIDPUR", "2024/12/b5f5926fea1c462eb5618fdefc2e8142"),
    ("Dhaka", "GOPALGANJ", "2024/12/3ae267c260a447ebb1e7ff20b248b9f4"),
    ("Dhaka", "RAJBARI", "2024/12/2dd354800b8642bd9d2318d6a39095fc"),
    ("Dhaka", "SHARIATPUR", "2024/12/27c3b4972ef746e5a20200951efca45d"),
    ("Dhaka", "KISHOREGANJ", "2024/12/7366f40e63e74ced8e4b231df246e068"),
    ("Dhaka", "MUNSHIGANJ", "2024/12/91d725ef924d4b4f9da8bbef02c3edc7"),
    ("Dhaka", "MADARIPUR", "2024/12/f412eb1018b8493a99dec89cdd9e4df7"),
    ("Dhaka", "TANGAIL", "2024/12/257941ad3e0449a29c02925138ffcef7"),
    ("Mymensingh", "MYMENSINGH", "2024/12/154cbde8cea641cdb85ab83f610b840c"),
    ("Mymensingh", "JAMALPUR", "2024/12/89e86f23804e4e119149f252b777c2d6"),
    ("Mymensingh", "SHERPUR", "2024/12/54153bc4a5094bc495c732fb9d62369e"),
    ("Mymensingh", "NETRAKONA", "2024/12/6e5bb9426ce24d8e99867fe62881edc8"),
    ("Khulna", "KHULNA", "2024/12/63c65a7594254c5fb5dbede282f0e67b"),
    ("Khulna", "BAGERHAT", "2024/12/9d14b0b0151e46b5b1c5c8e8cd3fce77"),
    ("Khulna", "SATKHIRA", "2024/12/4c8712e0f2d145dbabdbfbe95f28088e"),
    ("Khulna", "JHENAIDAH", "2024/12/3f288c3f560f49e5afac32bc0bf5b3df"),
    ("Khulna", "CHUADANGA", "2024/12/08bcfffe4e294e1d87066183002df3b2"),
    ("Khulna", "MAGURA", "2024/12/fde4acaa8d0149c68cb30511f461962f"),
    ("Khulna", "KUSHTIA", "2026/3/bd633dab-40c1-4371-87ea-c43c657040d0"),
    ("Khulna", "MEHERPUR", "2024/12/ff9cd564464a4df69854146475141764"),
    ("Khulna", "JASHORE", "2024/12/fdc7f79d9d064cf6896ad921503496b0"),
    ("Khulna", "NARAIL", "2024/12/fd9eddc198e34c10a62fddd1cb9d6be8"),
    ("Rajshahi", "RAJSHAHI", "2024/12/3c3b94e632604786bfc0b4a3a4872208"),
    ("Rajshahi", "NATORE", "2024/12/e0349f833a4a45baafa46d1bb562b908"),
    ("Rajshahi", "NAOGAON", "2024/12/34e059e2210243cbbbbdd3142b882ba1"),
    ("Rajshahi", "PABNA", "2024/12/0b82f91e54084e6ab16100f6bf808c19"),
    ("Rajshahi", "SIRAJGANJ", "2024/12/b351a354bf3949dab5b3d936c55c60ce"),
    ("Rajshahi", "BOGURA", "2024/12/b63c65a7d6c24ee3b854881f0a8d506d"),
    ("Rajshahi", "CHAPAI NAWABGANJ", "2024/12/9fd9b896e2da4e1b9fc7d163490ba81d"),
    ("Rajshahi", "JOYPURHAT", "2024/12/98d23819d1764f3da7dc257e1f498a34"),
    ("Rangpur", "RANGPUR", "2024/12/0b4cdcd23f0c4291808e8724b113ac67"),
    ("Rangpur", "GAIBANDHA", "2024/12/8515389ccebf4b1ea5c91659426447ad"),
    ("Rangpur", "NILPHAMARI", "2024/12/7fbb45d9940d4cfa9b4a4d9b8bfd34ab"),
    ("Rangpur", "KURIGRAM", "2024/12/ec98c2ca2a5a4af28d3e2e2236880a44"),
    ("Rangpur", "DINAJPUR", "2024/12/795760b6093542289f70a1d9ccc9cbca"),
    ("Rangpur", "THAKURGAON", "2024/12/4de9d3f0253a4529b29f64485b2aa132"),
    ("Rangpur", "LALMONIRHAT", "2024/12/fe276d9063bd494f8d635cf8aa39e825"),
    ("Rangpur", "PANCHAGARH", "2024/12/e3544f24c67145aeaea80921aaef5f1c"),
    ("Sylhet", "SYLHET", "2024/12/3abf605f9ab84a6686ad29688f206160"),
    ("Sylhet", "HABIGANJ", "2024/12/5f57f437a3a343d789a71c659732ceb9"),
    ("Sylhet", "MAULVIBAZAR", "2024/12/15c2523d9c494f65bd1ec18fa602acf4"),
    ("Sylhet", "SUNAMGANJ", "2024/12/952593ea389a4e3ba299fcfa3887c6c2"),
]
# The page's labels that are not the zila's name as the workbook or the
# boundary file spells it: one cut short, two misspelt, one hyphen dropped.
LABEL_SPELLINGS = {
    "PATUAKHAL": "Patuakhali",
    "JHALAKHATI": "Jhalokati",
    "BRAHMMANBARIA": "Brahmanbaria",
    "CHAPAI NAWABGANJ": "Chapainawabganj",
}
# The Bureau's own spellings, as the workbooks' first rows may give them,
# against the boundary file's: bangladesh.ALIASES covers the 2018 renamings,
# and these the rest.
SPELLINGS = {
    "Chapainawabganj": ("Nawabganj", "Chapai Nawabganj", "Chapainababganj"),
    "Chapai Nawabganj": ("Nawabganj", "Chapainawabganj", "Chapainababganj"),
    "Netrokona": ("Netrakona",),
    "Jhalokathi": ("Jhalokati",),
    "Jhalakathi": ("Jhalokati",),
    "Jhalakati": ("Jhalokati",),
    "Brahmanbaria": ("Brahamanbaria",),
}


def names_of(name: str) -> tuple[str, ...]:
    """A zila's name, then every spelling the boundary file may use for it."""
    key = fold(name)
    extra: list[str] = []
    for table in (ALIASES, SPELLINGS):
        for k, v in table.items():
            if fold(k) == key:
                extra.extend(v)
    return (name, *extra)


def division_names(name: str) -> tuple[str, ...]:
    key = fold(name)
    extra = next((v for k, v in DIVISION_ALIASES.items() if fold(k) == key), ())
    return (name, *extra)


# ---------------------------------------------------------------------------
# A workbook's two sheets
# ---------------------------------------------------------------------------

def text(cell: Any) -> str:
    return " ".join(str(cell).split()) if cell is not None else ""


def count(cell: Any, where: str) -> int:
    """A whole, non-negative count, or the run stops."""
    if isinstance(cell, bool) or cell is None or cell == "":
        raise SystemExit(f"bangladesh_zila_ages: {where} is blank")
    if isinstance(cell, float) and not cell.is_integer():
        raise SystemExit(f"bangladesh_zila_ages: {where} is {cell}, not a count")
    try:
        value = int(str(cell).replace(",", "").strip()) if isinstance(cell, str) else int(cell)
    except ValueError as err:
        raise SystemExit(f"bangladesh_zila_ages: {where} is {cell!r}") from err
    if value < 0:
        raise SystemExit(f"bangladesh_zila_ages: {where} is negative")
    return value


def find(rows: list[list[Any]], test, where: str) -> tuple[int, int]:
    """The (row, column) of the first cell passing ``test``."""
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if test(text(cell)):
                return r, c
    raise SystemExit(f"bangladesh_zila_ages: {where}")


def first_row(rows: list[list[Any]], after: int, name_col: int) -> list[Any]:
    """The first row after the column-number row with a name: the zila itself.

    Both sheets print a row of column numbers (1, 2, 3, ...) under their
    headings; the zila's row is the first named one after it.
    """
    for row in rows[after + 1:]:
        cells = [text(c) for c in row]
        if name_col < len(cells) and cells[name_col] and not cells[name_col].isdigit():
            return row
    raise SystemExit("bangladesh_zila_ages: no named row under the headings")


def read_c01(rows: list[list[Any]], where: str) -> dict[str, Any]:
    """C-01's zila row: name, population, males, females, hijra."""
    head, name_col = find(rows, lambda t: t.startswith("Administrative Uni"),
                          f"{where} C-01 has no 'Administrative Unit' heading")
    sub, hijra_col = find(rows[head:head + 3], lambda t: t == "Hijra",
                          f"{where} C-01 has no 'Hijra' heading")
    sub += head
    labels = [text(c) for c in rows[sub]]
    want = {hijra_col - 3: "Total", hijra_col - 2: "Male", hijra_col - 1: "Female"}
    for col, label in want.items():
        if col < 0 or labels[col] != label:
            raise SystemExit(f"bangladesh_zila_ages: {where} C-01 heads column "
                             f"{col} {labels[col] if col >= 0 else None!r}, not {label!r}")
    numbers = next((i for i in range(sub + 1, min(sub + 4, len(rows)))
                    if text(rows[i][name_col]).isdigit()), sub)
    row = first_row(rows, numbers, name_col)
    out = {
        "name": text(row[name_col]),
        "population": count(row[hijra_col - 3], f"{where} C-01 population"),
        "males": count(row[hijra_col - 2], f"{where} C-01 males"),
        "females": count(row[hijra_col - 1], f"{where} C-01 females"),
        "hijra": count(row[hijra_col], f"{where} C-01 hijra"),
    }
    if out["males"] + out["females"] + out["hijra"] != out["population"]:
        raise SystemExit(f"bangladesh_zila_ages: {where} C-01: {out['males']:,} males, "
                         f"{out['females']:,} females and {out['hijra']:,} hijra "
                         f"against a population of {out['population']:,}")
    return out


def read_c02(rows: list[list[Any]], where: str) -> dict[str, Any]:
    """C-02's zila row: name, population and its seventeen age groups."""
    head, name_col = find(rows, lambda t: t.startswith("Administrative Uni"),
                          f"{where} C-02 has no 'Administrative Unit' heading")
    total_col = next((c for c, cell in enumerate(rows[head]) if text(cell) == "Total"), None)
    if total_col is None:
        raise SystemExit(f"bangladesh_zila_ages: {where} C-02 has no 'Total' heading")
    band, first = find(rows[head:head + 3], lambda t: t == "0-4",
                       f"{where} C-02 has no '0-4' heading")
    band += head
    printed = [text(c).replace(" ", "").replace("–", "-")
               for c in rows[band][first:first + len(LABELS)]]
    for i, (label, got) in enumerate(zip(LABELS, printed)):
        if got != label and (i, got) not in MISPRINTS:
            raise SystemExit(f"bangladesh_zila_ages: {where} C-02 heads its age "
                             f"columns {printed}; expected {LABELS}")
    if len(printed) != len(LABELS):
        raise SystemExit(f"bangladesh_zila_ages: {where} C-02 has {len(printed)} age columns")
    if first != total_col + 1:
        raise SystemExit(f"bangladesh_zila_ages: {where} C-02's ages do not follow its Total")
    numbers = next((i for i in range(band + 1, min(band + 4, len(rows)))
                    if text(rows[i][name_col]).isdigit()), band)
    row = first_row(rows, numbers, name_col)
    groups = [count(row[first + i], f"{where} C-02 ages {LABELS[i]}")
              for i in range(len(LABELS))]
    out = {"name": text(row[name_col]),
           "population": count(row[total_col], f"{where} C-02 total"),
           "groups": groups}
    if sum(groups) != out["population"]:
        raise SystemExit(f"bangladesh_zila_ages: {where} C-02: the age groups add up "
                         f"to {sum(groups):,} against a total of {out['population']:,}")
    return out


def read_zila(c01_rows: list[list[Any]], c02_rows: list[list[Any]],
              division: str, label: str, url: str) -> dict[str, Any]:
    """One workbook's zila, the two sheets checked against each other."""
    where = f"{label.title()} ({url.rsplit('/', 1)[-1]})"
    c01, c02 = read_c01(c01_rows, where), read_c02(c02_rows, where)
    if fold(c01["name"]) != fold(c02["name"]):
        raise SystemExit(f"bangladesh_zila_ages: {where}: C-01 is {c01['name']!r} "
                         f"and C-02 {c02['name']!r}")
    if c01["population"] != c02["population"]:
        raise SystemExit(f"bangladesh_zila_ages: {where}: C-01 counts "
                         f"{c01['population']:,} people and C-02 {c02['population']:,}")
    page = {fold(n) for n in names_of(LABEL_SPELLINGS.get(label, label))}
    if not page & {fold(n) for n in names_of(c01["name"])}:
        raise SystemExit(f"bangladesh_zila_ages: the page links {label!r} to a "
                         f"workbook whose zila is {c01['name']!r}")
    return {**c01, "groups": c02["groups"], "division": division, "label": label,
            "url": url}


# ---------------------------------------------------------------------------
# The checks across zilas
# ---------------------------------------------------------------------------

def collapse(p03_groups: list[tuple]) -> list[int]:
    """Table P03's persons in C-02's seventeen groups (80 and over together)."""
    out = [0] * len(GROUPS)
    for low, _high, persons, *_sexes in p03_groups:
        out[min(low // 5, len(GROUPS) - 1)] += persons
    return out


def check_divisions(zilas: list[dict[str, Any]], p03: dict[str, Any]) -> None:
    """Each division's zilas are Table P03's division plus its hijra, by age."""
    bad: list[str] = []
    divisions = sorted({z["division"] for z in zilas})
    if set(divisions) != set(p03) - {"National"}:
        bad.append(f"the workbooks' divisions {divisions} are not Table P03's "
                   f"{sorted(set(p03) - {'National'})}")
    for division in divisions:
        mine = [z for z in zilas if z["division"] == division]
        if division not in p03:
            continue
        summed = [sum(z["groups"][i] for z in mine) for i in range(len(GROUPS))]
        printed = collapse(p03[division]["groups"])
        excess = [s - p for s, p in zip(summed, printed)]
        hijra = sum(z["hijra"] for z in mine)
        short = [f"{LABELS[i]} by {-e:,}" for i, e in enumerate(excess) if e < 0]
        if short:
            bad.append(f"{division}: its zilas fall short of Table P03 at ages "
                       + ", ".join(short))
        if sum(excess) != hijra:
            bad.append(f"{division}: its zilas exceed Table P03 by {sum(excess):,} "
                       f"people, and its hijra are {hijra:,}")
        if p03[division]["total"][0] + hijra != sum(z["population"] for z in mine):
            bad.append(f"{division}: Table P03's {p03[division]['total'][0]:,} males "
                       f"and females and {hijra:,} hijra against its zilas' "
                       f"{sum(z['population'] for z in mine):,}")
    nation = sum(z["population"] for z in zilas)
    if nation != NATION_2022:
        bad.append(f"the zilas add up to {nation:,}, not the census's {NATION_2022:,}")
    if bad:
        raise SystemExit(f"bangladesh_zila_ages: {len(bad)} checks failed -- "
                         + "; ".join(bad[:5]))
    log(f"    {len(zilas)} zilas in {len(divisions)} divisions: each division's zilas "
        "are Table P03's males and females plus their hijra, group by group, and "
        f"the zilas make the census's {NATION_2022:,}")


def median_of(groups: list[int]) -> float | None:
    return median_grouped([(low, high, n) for (low, high), n in zip(GROUPS, groups)])


def check_nation(zilas: list[dict[str, Any]], p03: dict[str, Any],
                 p10: dict[str, Any] | None) -> None:
    """The nation's median from the zilas against the report's own tables."""
    summed = [sum(z["groups"][i] for z in zilas) for i in range(len(GROUPS))]
    ours = median_of(summed)
    grouped = median_of(collapse(p03["National"]["groups"]))
    if ours is None or grouped is None or abs(ours - grouped) > 0.1:
        raise SystemExit(f"bangladesh_zila_ages: the zilas' national median is {ours}, "
                         f"Table P03's groups give {grouped}")
    single = None
    if p10 is not None:
        single = median_single({a: v[0] for a, v in p10["National"]["ages"].items()},
                               open_from=100)
    log(f"    the nation's median from the 64 zilas' groups is {ours}; Table P03's own "
        f"groups give {grouped} and Table P10's single years {single}")


# ---------------------------------------------------------------------------
# Binding and the records
# ---------------------------------------------------------------------------

def district_populations(path=None) -> dict[str, int]:
    """Folded name (and alias) -> the district indicators workbook's population."""
    rows = json.loads((path or PROCESSED / "bangladesh_district.json").read_text("utf-8"))
    out: dict[str, int] = {}
    for row in rows:
        if row.get("level") != "admin2":
            continue
        value = (row.get("population") or {}).get("value")
        for name in (row["name"], *(row.get("aliases") or ())):
            out[fold(name)] = value
    return out


def note(z: dict[str, Any], median: float) -> str:
    return (f"Census 2022, the Bureau's Community Series workbook for {z['name']}, "
            f"Table C-02: the median of {z['population']:,} people ({z['males']:,} "
            f"males, {z['females']:,} females and {z['hijra']:,} hijra), "
            f"interpolated within the five-year age group that holds the middle "
            f"person -- single years of age are published by division only. "
            f"The zila's groups, with the rest of its division's, make the National "
            f"Report's Table P03 plus the hijra P03 leaves out.")


def build(zilas: list[dict[str, Any]], units2: list[dict[str, Any]],
          units1: list[dict[str, Any]], populations: dict[str, int]
          ) -> list[dict[str, Any]]:
    bound1, left1, spare1 = bind({d: division_names(d) for d in
                                  sorted({z["division"] for z in zilas})}, units1)
    report_binding("divisions", bound1, left1, spare1)
    if left1 or spare1:
        raise SystemExit("bangladesh_zila_ages: a division matches no single drawn unit")
    children = {key: {u["id"] for u in units2 if u.get("parent") == unit["id"]}
                for key, unit in bound1.items()}
    by_key = {z["label"]: z for z in zilas}
    bound, left, spare = bind({k: names_of(z["name"]) for k, z in by_key.items()}, units2,
                              parent_of={k: z["division"] for k, z in by_key.items()},
                              parent_units=children)
    report_binding("zilas", bound, left, spare)
    if left or spare:
        raise SystemExit("bangladesh_zila_ages: every zila must bind to one drawn "
                         "polygon and every polygon to one zila")

    records, off = [], []
    for key, unit in sorted(bound.items(), key=lambda kv: kv[1]["name"]):
        z = by_key[key]
        keys = unit_keys(unit) | {fold(n) for n in names_of(z["name"])}
        known = {populations[k] for k in keys if k in populations}
        if known != {z["population"]}:
            off.append(f"{z['name']}: {z['population']:,} in its workbook, "
                       f"{sorted(known) or 'nothing'} in the district indicators")
            continue
        median = median_of(z["groups"])
        if median is None:
            off.append(f"{z['name']}: the middle person is 80 or older")
            continue
        division = next(u for u in units1 if u["id"] == unit["parent"])
        records.append(record(
            f"BGD-AGE2022-{fold(unit['name'])}", unit["name"], level="admin2",
            parent="BGD", country="BGD", match_by="shape_id", shape_id=unit["id"],
            parent_name=division["name"],
            median_age=measure(median, unit="years", year=YEAR, source=SOURCE),
            median_age_note=note(z, median),
            sources=[{"field": "median_age", "name": SOURCE, "url": z["url"],
                      "year": YEAR, "license": LICENCE}]))
    if off:
        raise SystemExit("bangladesh_zila_ages: refused -- " + "; ".join(off))
    return records


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

SHEET_ROWS = 40          # the headings and the zila's own row are near the top


def sheet_key(title: str) -> str:
    """A sheet's name as the workbooks vary it: "C-01", "C01", "C-11 "."""
    return re.sub(r"[^a-z0-9]", "", title.lower())


def sheet_rows(book, name: str, limit: int = SHEET_ROWS) -> list[list[Any]]:
    sheet = next((s for s in book.worksheets if sheet_key(s.title) == sheet_key(name)), None)
    if sheet is None:
        raise SystemExit(f"bangladesh_zila_ages: no sheet {name!r} in "
                         f"{[s.title for s in book.worksheets]}")
    out = []
    for row in sheet.iter_rows(values_only=True):
        out.append(list(row))
        if len(out) >= limit:
            break
    return out


def read_workbook(blob: bytes, division: str, label: str, url: str) -> dict[str, Any]:
    import openpyxl                                 # noqa: PLC0415
    book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    try:
        return read_zila(sheet_rows(book, "C-01"), sheet_rows(book, "C-02"),
                         division, label, url)
    finally:
        book.close()


def report_tables() -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Tables P03 and P10 of the National Report, checked as ``bangladesh`` checks them."""
    blob = http_get(REPORT, binary=True)
    log(f"    {len(blob):,} bytes of National Report from the Bureau's own storage")
    lines = laid_out(blob).splitlines()
    p03 = read_ages(lines)
    check_ages(p03)
    p10 = read_single_years(lines)
    check_single_years(p10, p03)
    said = [" ".join(line.split()) for line in lines if re.search(r"(?i)median age", line)]
    for line in said[:6]:
        log(f"    the report says: {line[:160]}")
    return p03, p10, said


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    log("bangladesh_zila_ages: Census 2022 Community Series, Tables C-01 and C-02 by zila")
    p03, p10, _said = report_tables()
    zilas, refused = [], []
    for division, label, key in ZILAS:
        url = STORE.format(key)
        # Every workbook is read before any is refused, so one run names every
        # problem rather than the first.
        try:
            blob = http_get(url, binary=True, cache_dir=RAW / "bangladesh" / "community")
            zila = read_workbook(blob, division, label, url)
        except urllib.error.HTTPError as err:
            refused.append(f"{label}: {url} answered {err.code}")
            log(f"    {label:<17} REFUSED: {url} answered {err.code}")
            continue
        except SystemExit as err:
            refused.append(str(err))
            log(f"    {label:<17} REFUSED: {err}")
            continue
        log(f"    {label:<17} {zila['name']:<16} {zila['population']:>11,} people, "
            f"{zila['hijra']:>4} hijra, median {median_of(zila['groups'])}")
        zilas.append(zila)
    if refused:
        raise SystemExit(f"bangladesh_zila_ages: {len(refused)} of {len(ZILAS)} workbooks "
                         "refused -- " + "; ".join(refused))
    check_divisions(zilas, p03)
    check_nation(zilas, p03, p10)
    records = build(zilas, load_units("BGD", "admin2"), load_units("BGD", "admin1"),
                    district_populations())
    write_json(args.out or PROCESSED / OUT, records)
    log(f"  {len(records)} zilas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
