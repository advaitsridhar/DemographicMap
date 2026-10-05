#!/usr/bin/env python3
"""Timor-Leste: median age and sex ratio by municipality and administrative post, 2022.

The 2022 Population and Housing Census's main report publishes its basic
tables as one workbook (``timor.py`` reads its table 4.01 for the posts'
populations):

    https://inetl-ip.gov.tl/wp-content/uploads/2023/05/Chapter-4-TLPHC-Census-report-Basic-tables.xlsx

* **Table 4.05** -- population by urban/rural location, single year of age
  (and five-year groups), municipality and sex: the country and its fourteen
  municipalities across the top, Total / Male / Female under each, and the
  ages down the side in three blocks, total, urban and rural. The total
  block's single years give each municipality's **median age**, interpolated
  within the year holding the middle person, and its males and females the
  **sex ratio**.
* **Table 4.01** -- population by municipality, administrative post and suco,
  by sex: the posts' males and females give each post's **sex ratio**. No
  table of the 2022 census, and none of 2015's, gives a post's ages finer than
  0-14 / 15-64 / 65+ (2015 Volume 2, table 2.6), so the posts get no median
  and their records say why.

**Two divisions differ from the boundary file's.** The map draws the thirteen
municipalities and 65 posts of before 2022. Atauro became the fourteenth
municipality in 2022: its people are added into Dili's polygon, which holds
them (as ``timor.py`` does for the population). Ermera's Hatulia became
Hatulia A and Hatulia B, whose sucos are the old post's; and Lautém's Lore,
the sucos Lore I and Lore II, was cut out of Lospalos. The polygons "Hatolia"
and "Lospalos" therefore take the two 2022 posts each now holds, added
together, with their population; every other post is matched by name (and by
``timor.POST_ALIASES``'s declared spellings) to exactly one drawn polygon.

**Checks**, each a refusal: in table 4.05 every single year's males and
females make its total (one cell printed "-" in a row whose other two figures
show people -- Atauro's men of 83: total 11, women 9 -- is read as the
difference and logged), every municipality's single years make its total for
both sexes and each, and its males and females its total;
the fourteen make the country; in table 4.01 every post's males and females
make its total and every municipality's posts make it; and every census post
is used exactly once.

Usage:
    python -m scripts.fetch_census.timor_age
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from typing import Any

from . import timor
from ._shared import NOT_AVAILABLE, PROCESSED, RAW, download, gap, log, record, write_json
from .sea_common import age_sex, drawn, fold, single_median

OUT = "timor_age.json"
YEAR = 2022
SOURCE_AGE = (f"{timor.CENSUS_2022}, Main Report basic table 4.05: population by urban/rural "
              "location, age, municipality and sex")
SOURCE_POST = timor.POPULATION_SOURCE
# The polygons that hold more than one 2022 post: polygon -> the posts.
JOINED = {"Hatolia": ["Hatulia A", "Hatulia B"], "Lospalos": ["Lospalos", "Lore"]}
JOINED_NOTE = {
    "Hatolia": ("The boundary file draws Ermera's Hatulia as it was before the 2022 census "
                "divided it into Hatulia A and Hatulia B, whose sucos are the old post's; "
                "the two posts' counts are added together for it."),
    "Lospalos": ("The boundary file draws Lautém's Lospalos as it was before Lore -- the "
                 "sucos Lore I and Lore II -- became a post of its own in the 2022 census; "
                 "the two posts' counts are added together for it."),
}
POST_AGE_GAP = ("No census of Timor-Leste publishes ages by administrative post finer than "
                "three broad groups: the 2022 main report's basic table 4.05 gives single "
                "years by municipality only, and the 2015 round's Volume 2 gives the posts "
                "0-14, 15-64 and 65+ (table 2.6), too coarse for a median.")


def header_columns(grid: list[list[Any]], first: str = "timorleste"
                   ) -> tuple[int, dict[str, dict[str, int]]]:
    """Table 4.05's unit row: {unit: {"T": col, "M": col, "F": col}}."""
    for r, row in enumerate(grid[:12]):
        keys = [fold(timor.tidy(c)) for c in row]
        if first in keys and "aileu" in keys:
            sexes = [fold(timor.tidy(c)) for c in grid[r + 1]]
            out: dict[str, dict[str, int]] = {}
            for c, key in enumerate(keys):
                if not key:
                    continue
                trio = sexes[c:c + 3]
                if trio != ["total", "male", "female"]:
                    raise SystemExit(f"timor_age: under {key!r} the sexes read {trio}")
                out[key] = {"T": c, "M": c + 1, "F": c + 2}
            return r, out
    raise SystemExit("timor_age: table 4.05 has no row naming the municipalities")


def read_ages(grid: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """Each unit of table 4.05's total block: single years by sex, and totals."""
    head, cols = header_columns(grid)
    units = {k: {"ages": {s: Counter() for s in "TMF"}, "total": {}} for k in cols}
    block = 0
    top = None
    repaired: list[str] = []
    for row in grid[head + 2:]:
        label = timor.tidy(timor.at(row, 0))
        if not label:
            continue
        if fold(label) in ("total", "urban", "rural"):
            block += 1
            if block > 1:
                break
            for k, c in cols.items():
                units[k]["total"] = {s: timor.number(timor.at(row, c[s])) or 0 for s in "TMF"}
            continue
        if block != 1:
            continue                     # the column-number row above the first block
        text = label.replace(".0", "") if re.fullmatch(r"\d+\.0", label) else label
        single = re.fullmatch(r"\d{1,3}", text)
        opened = re.fullmatch(r"(\d{1,3})\s*\+", text)
        if not (single or opened):
            continue                     # a five-year group: the single years make it
        age = int((single or opened).group(1) if opened else text)
        if opened:
            top = age
        for k, c in cols.items():
            cells = {s: timor.number(timor.at(row, c[s])) for s in "TMF"}
            got = {s: cells[s] or 0 for s in "TMF"}
            if got["M"] + got["F"] != got["T"]:
                # A cell printed "-" in a row whose other two figures show
                # people -- Atauro's men of 83: total 11, "-", women 9 -- is
                # the difference of the two; anything else refuses. The
                # unit's totals, checked below, confirm the reading.
                blank = [s for s in "TMF" if cells[s] is None]
                if len(blank) != 1:
                    raise SystemExit(f"timor_age: {k} age {text}: {got['M']:,.0f} males and "
                                     f"{got['F']:,.0f} females against {got['T']:,.0f}")
                s = blank[0]
                got[s] = (got["M"] + got["F"] if s == "T"
                          else got["T"] - got["F"] if s == "M" else got["T"] - got["M"])
                if got[s] <= 0:
                    raise SystemExit(f"timor_age: {k} age {text}: the '-' cannot be read")
                repaired.append(f"{k} {s} at {text}: '-' read as {got[s]:,.0f}")
            for s in "TMF":
                units[k]["ages"][s][age] += got[s]
    if top is None:
        raise SystemExit("timor_age: table 4.05 has no open top age class")
    if repaired:
        log("  table 4.05 cells printed '-' where their row's other figures show people, read "
            "as the difference: " + "; ".join(repaired))
    for k, u in units.items():
        for s in "TMF":
            made = sum(u["ages"][s].values())
            if made != u["total"].get(s):
                raise SystemExit(f"timor_age: {k} {s}: single years make {made:,.0f}, "
                                 f"against its total {u['total'].get(s)}")
        if u["total"]["M"] + u["total"]["F"] != u["total"]["T"]:
            raise SystemExit(f"timor_age: {k}: males and females do not make its total")
        u["top"] = top
    country = units.pop("timorleste")
    made = sum(u["total"]["T"] for u in units.values())
    if made != country["total"]["T"] or len(units) != 14:
        raise SystemExit(f"timor_age: {len(units)} municipalities make {made:,.0f}, against "
                         f"the country's {country['total']['T']:,.0f}")
    median = single_median(country["ages"]["T"])
    log(f"  table 4.05: 14 municipalities, single years to {top}+, making the country's "
        f"{made:,.0f}; national median {median}")
    return units


def read_posts(grid: list[list[Any]]) -> dict[str, dict[str, float]]:
    """Table 4.01: each post's total, males and females, keyed by folded name."""
    tcol = None
    for row in grid[:8]:
        labels = [fold(timor.tidy(c)) for c in row]
        if labels[3:6] == ["total", "male", "female"]:
            tcol = 3
            break
    if tcol is None:
        raise SystemExit("timor_age: table 4.01 has no Total / Male / Female header at column 4")
    posts: dict[str, dict[str, float]] = {}
    municipality = None
    by_municipality: Counter = Counter()
    municipal_total: dict[str, float] = {}
    for row in grid:
        first, second, third = (timor.tidy(timor.at(row, i)) for i in range(3))
        t, m, f = (timor.number(timor.at(row, tcol + i)) for i in range(3))
        if t is None or third:
            continue
        if m is None or f is None or m + f != t:
            raise SystemExit(f"timor_age: 4.01 {first or second}: {m} and {f} do not make {t}")
        if first and fold(first) not in timor.COUNTRY_LABELS:
            municipality = first
            municipal_total[municipality] = t
        elif second:
            key = fold(second)
            if key in posts:
                raise SystemExit(f"timor_age: 4.01 names the post {second!r} twice")
            posts[key] = {"name": second, "municipality": municipality, "T": t, "M": m, "F": f}
            by_municipality[municipality] += t
    for mun, total in municipal_total.items():
        if by_municipality[mun] != total:
            raise SystemExit(f"timor_age: {mun}'s posts make {by_municipality[mun]:,.0f}, "
                             f"against its {total:,.0f}")
    log(f"  table 4.01: {len(posts)} posts in {len(municipal_total)} municipalities, each "
        "municipality's posts making it")
    return posts


def municipality_records(units: dict[str, dict[str, Any]], admin1: list[dict[str, Any]]
                         ) -> list[dict[str, Any]]:
    out = []
    for shape in admin1:
        name = timor.MUNICIPALITY_KEYS.get(fold(shape["name"]))
        if name is None:
            raise SystemExit(f"timor_age: the polygon {shape['name']!r} is no municipality")
        keys = [k for k in units if timor.MUNICIPALITY_KEYS.get(k) == name]
        if name == timor.ATAURO_PARENT:
            keys.append(timor.ATAURO_KEY)
        if not keys or any(k not in units for k in keys):
            raise SystemExit(f"timor_age: no table 4.05 column for {shape['name']!r}")
        ages = {s: Counter() for s in "TMF"}
        for k in keys:
            for s in "TMF":
                ages[s].update(units[k]["ages"][s])
        top = units[keys[0]]["top"]
        median = single_median(ages["T"])
        if median is None or median >= top:
            raise SystemExit(f"timor_age: {name}: no median below the open {top}+ class")
        whose = ("the 2022 census's count of everyone in Dili and Atauro, which the "
                 "boundary file draws as one municipality (Atauro was Dili's until 2022)"
                 if len(keys) > 1 else f"the 2022 census's count of everyone in {name}")
        out.append(record(
            f"TLS-AGE-{fold(name)}", shape["name"], level="admin1", parent="TLS",
            country="TLS", match_by="shape_id", shape_id=shape["id"],
            sources=[{"field": "median_age/sex_ratio", "name": SOURCE_AGE,
                      "url": timor.POPULATION_PAGE, "year": YEAR, "license": timor.LICENCE}],
            **age_sex(median=median, men=sum(ages["M"].values()),
                      women=sum(ages["F"].values()), year=YEAR, source=SOURCE_AGE,
                      median_note=(f"Interpolated within the single year of age that holds "
                                   f"the middle person, from {whose}, by single year of age "
                                   f"to an open {top}+ (basic table 4.05)."),
                      ratio_note=f"Males per 100 females in {whose} (basic table 4.05)."),
        ))
    return out


def post_records(posts: dict[str, dict[str, float]], admin2: list[dict[str, Any]]
                 ) -> list[dict[str, Any]]:
    aliases = {fold(a): k for k, al in timor.POST_ALIASES.items() for a in [k, *al]}
    used: dict[str, str] = {}
    out = []
    for shape in admin2:
        name = shape["name"]
        wanted = JOINED.get(name) or [aliases.get(fold(name), name)]
        parts = []
        for w in wanted:
            p = posts.get(fold(w))
            if p is None:
                raise SystemExit(f"timor_age: no 2022 post {w!r} for the polygon {name!r}")
            if fold(w) in used:
                raise SystemExit(f"timor_age: post {w!r} bound to {used[fold(w)]!r} and {name!r}")
            used[fold(w)] = name
            parts.append(p)
        men, women, total = (sum(p[s] for p in parts) for s in "MFT")
        joined = name in JOINED
        whose = (f"the 2022 census's count of {' and '.join(p['name'] for p in parts)} "
                 f"together" if joined else f"the 2022 census's count of {parts[0]['name']}")
        fields = age_sex(median=None, men=men, women=women, year=YEAR, source=SOURCE_POST,
                         median_note="", ratio_note=f"Males per 100 females in {whose} "
                                                    f"(basic table 4.01).",
                         population=int(total) if joined else None,
                         population_note=(JOINED_NOTE[name] if joined else None))
        # Religion and mother tongue say why they are empty on every post,
        # in timor.py's words: its own reader reaches 64 of the 65 polygons
        # by name and leaves Hatolia, two posts since 2022, with a note about
        # joining instead.
        out.append(record(
            f"TLS-AGE-P-{fold(name)}", name, level="admin2", parent="TLS", country="TLS",
            match_by="shape_id", shape_id=shape["id"],
            median_age=gap(NOT_AVAILABLE, POST_AGE_GAP),
            religion=gap(NOT_AVAILABLE, timor.POST_RELIGION_GAP),
            language=gap(NOT_AVAILABLE, timor.POST_LANGUAGE_GAP),
            sources=[{"field": "sex_ratio" + ("/population" if joined else ""),
                      "name": SOURCE_POST, "url": timor.POPULATION_PAGE, "year": YEAR,
                      "license": timor.LICENCE}],
            **fields))
    left = sorted(p["name"] for k, p in posts.items() if k not in used)
    if left:
        raise SystemExit(f"timor_age: 2022 posts on no polygon: {left}")
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    log(f"timor_age: {SOURCE_AGE}")
    path = download(timor.POPULATION_XLSX,
                    RAW / "timor" / timor.POPULATION_XLSX.rsplit("/", 1)[-1])
    units = read_ages(timor.xlsx_grid(path, "4.05"))
    posts = read_posts(timor.xlsx_grid(path, timor.POPULATION_SHEET))
    records = (municipality_records(units, drawn("TLS", "admin1"))
               + post_records(posts, drawn("TLS", "admin2")))
    for level in ("admin1", "admin2"):
        rs = [r for r in records if r["level"] == level]
        meds = sorted(r["median_age"]["value"] for r in rs if "value" in r["median_age"])
        rats = sorted(r["sex_ratio"]["value"] for r in rs)
        log(f"  {level}: {len(rs)} units; median {meds[:1]}..{meds[-1:]}; "
            f"sex ratio {rats[0]}-{rats[-1]}")
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
