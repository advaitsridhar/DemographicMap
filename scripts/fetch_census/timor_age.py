#!/usr/bin/env python3
"""Timor-Leste: median age and sex ratio by municipality and administrative post, 2022 and 2015.

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
  table of the 2022 census gives a post's ages finer than 0-14 / 15-64 / 65+.

The posts' **median age** is the 2015 census's, from its Volume 2 workbook
(``2_2015-V2-Population-by-Age-Sex.xls``): table 6 gives every post under 15,
15-64 and 65 and over, and table 7 the school ages 3-5, 6-11, 12-14, 15-17,
18-21, 22-24 and 25-29, each by sex. Together they make ten groups -- 0-2
(table 6's under-15 less table 7's 3-14), table 7's seven, 30-64 and 65+ --
none wider than six years below 30; the median, near 19 in 2015, is
interpolated within the three- or four-year group holding the middle person,
and a post whose middle person is 30 or older (where only 30-64 is published)
keeps a stated gap. The method is checked where the volume also gives single
years (table 5 for the country, 5.1a-m for each municipality): the groups'
median must sit within half a year of the single years'. The boundary file
draws the 65 posts of 2015, so no post needs joining for this.

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
from ._shared import (NOT_AVAILABLE, PROCESSED, RAW, download, gap, log, measure, record,
                      write_json)
from .sea_common import age_sex, band, drawn, fold, grouped, single_median

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

# The 2015 round's Volume 2 workbook of ages. Its table 6 (sheet 2.6) gives
# every municipality and administrative post under 15, 15-64 and 65 and over
# (and 17-60 and 60 and over), and its table 7 (sheet 2.7) the school ages
# 3-5, 6-11, 12-14, 15-17, 18-21, 22-24 and 25-29, each by sex. Together they
# split a post's people into ten groups none wider than six years below 30:
# 0-2 (table 6's under-15 less table 7's 3-14), table 7's seven, 30-64 (table
# 6's 15-64 less table 7's 15-29) and 65 and over. Timor-Leste's median age
# was some 19 years in 2015, so a post's middle person falls in a group of
# three or four years -- fine enough to interpolate, where 15-64 alone is not.
# The boundary file draws the 65 posts of 2015, so these bind without the
# 2022 joins.
AGE_2015_XLS = f"{timor.BASE}/2023/03/2_2015-V2-Population-by-Age-Sex.xls"
YEAR_2015 = 2015
SOURCE_AGE_2015 = (f"{timor.CENSUS_2015}, Volume 2 tables 6 and 7: population by "
                   "municipality, administrative post, sex and age group (under 15, 15-64, "
                   "65 and over; and the school ages 3-5 to 25-29)")
SIX = [(0, 14), (15, 64), (65, None), (17, 60), (60, None)]
SEVEN = [(3, 5), (6, 11), (12, 14), (15, 17), (18, 21), (22, 24), (25, 29)]
# The 2015 volume's spelling of a post the boundary file spells otherwise, on
# top of timor.POST_ALIASES: Ermera's "Hatulia" is the drawn "Hatolia", the
# one post of 2015 whose name the two write apart (2015 had no Hatulia A/B).
POST_ALIASES_2015 = {"Hatolia": ["Hatulia"]}
# How far the median from these groups may sit from the one interpolated in
# single years, for the country and each municipality, where the volume gives
# single years (tables 5 and 5.1a-m): beyond it the groups are being misread.
GROUPED_TOLERANCE = 0.5


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


def table_rows(grid: list[list[Any]], bands: list[tuple[int, int | None]], where: str
               ) -> list[tuple[str, dict[str, dict[tuple[int, int | None], float]]]]:
    """Each named row of a 2015 table: {sex: {band: count}}, in the sheet's order.

    The header row is found by its labels, which must be ``bands`` three
    times over -- Total, Male, Female -- or the sheet has changed and the
    run refuses.
    """
    width = 3 * len(bands)
    head = None
    for r, row in enumerate(grid[:12]):
        if [band(timor.tidy(timor.at(row, 1 + i))) for i in range(width)] == bands * 3:
            head = r
            break
    if head is None:
        raise SystemExit(f"timor_age: {where}: no header row of {bands} for three sexes")
    out = []
    for row in grid[head + 1:]:
        name = timor.tidy(timor.at(row, 0))
        if not name or re.fullmatch(r"\d+(?:\.0)?", name):
            continue                     # blank, or the column-number row
        cells = [timor.number(timor.at(row, 1 + i)) for i in range(width)]
        if all(c is None for c in cells):
            continue                     # the footnote under the table
        if any(c is None for c in cells):
            raise SystemExit(f"timor_age: {where}: {name}: blank cells")
        n = len(bands)
        groups = {s: dict(zip(bands, cells[k * n:(k + 1) * n])) for k, s in enumerate("TMF")}
        for b in bands:
            if groups["M"][b] + groups["F"][b] != groups["T"][b]:
                raise SystemExit(f"timor_age: {where}: {name} {b}: males and females do not "
                                 f"make the total")
        out.append((name, groups))
    return out


def kind_of(name: str) -> str:
    if timor.fold(name) in timor.COUNTRY_LABELS:
        return "country"
    if name.isupper() and timor.fold(name) in timor.MUNICIPALITY_KEYS:
        return "municipality"
    return "post"


def ten_groups(six: dict[tuple, float], seven: dict[tuple, float], where: str
               ) -> list[tuple[int, int | None, float]]:
    """One sex's ten age groups, from table 6's broad groups and table 7's school ages."""
    young = six[(0, 14)] - seven[(3, 5)] - seven[(6, 11)] - seven[(12, 14)]
    middle = six[(15, 64)] - sum(seven[b] for b in SEVEN[3:])
    if young < 0 or middle < 0:
        raise SystemExit(f"timor_age: {where}: table 7's ages exceed table 6's groups "
                         f"(0-2 {young:,.0f}, 30-64 {middle:,.0f})")
    return ([(0, 2, young)] + [(lo, hi, seven[(lo, hi)]) for lo, hi in SEVEN]
            + [(30, 64, middle), (65, None, six[(65, None)])])


def fine_median(groups: list[tuple[int, int | None, float]]) -> float | None:
    """The median from the ten groups, or None where it falls in the 35-year 30-64."""
    total = sum(n for _, _, n in groups)
    below_30 = sum(n for _, hi, n in groups if hi is not None and hi <= 29)
    if below_30 < total / 2:
        return None
    return grouped(groups)


def read_2015_groups(grid6: list[list[Any]], grid7: list[list[Any]]
                     ) -> dict[str, dict[str, Any]]:
    """Every 2015 unit's ten groups by sex, keyed by kind and folded name, sums checked."""
    six = table_rows(grid6, SIX, "2015 table 6")
    seven = table_rows(grid7, SEVEN, "2015 table 7")
    if [n for n, _ in six] != [n for n, _ in seven]:
        raise SystemExit("timor_age: 2015 tables 6 and 7 do not list the same units in the "
                         "same order")
    units: dict[str, dict[str, Any]] = {}
    municipality = None
    order = []
    for (name, g6), (_, g7) in zip(six, seven):
        kind = kind_of(name)
        if kind == "municipality":
            municipality = timor.MUNICIPALITY_KEYS[timor.fold(name)]
        key = (kind, municipality if kind == "post" else None, timor.fold(name))
        if key in units:
            raise SystemExit(f"timor_age: 2015 tables name {name!r} twice")
        units[key] = {"name": name, "kind": kind, "municipality": municipality,
                      "six": g6, "seven": g7,
                      "groups": {s: ten_groups(g6[s], g7[s], f"2015 {name} {s}")
                                 for s in "TMF"}}
        order.append(key)
    # Posts make their municipality and municipalities the country, in every
    # band of both tables and for each sex.
    country = [k for k in order if k[0] == "country"]
    if len(country) != 1:
        raise SystemExit("timor_age: 2015 tables have no single country row")
    munis = [k for k in order if k[0] == "municipality"]
    for whole, parts in ([(country[0], munis)]
                         + [(m, [k for k in order if k[0] == "post"
                                 and k[1] == units[m]["municipality"]]) for m in munis]):
        if not parts:
            raise SystemExit(f"timor_age: 2015 {units[whole]['name']} has no units under it")
        for table in ("six", "seven"):
            for s in "TMF":
                for b, v in units[whole][table][s].items():
                    made = sum(units[p][table][s][b] for p in parts)
                    if made != v:
                        raise SystemExit(f"timor_age: 2015 {units[whole]['name']} {table} "
                                         f"{s} {b}: its parts make {made:,.0f}, against "
                                         f"{v:,.0f}")
    posts = sum(1 for k in order if k[0] == "post")
    log(f"  2015 tables 6 and 7: {posts} posts in {len(munis)} municipalities, posts making "
        f"their municipality and municipalities the country in every group and sex")
    return units


def read_2015_single(grid: list[list[Any]], where: str) -> tuple[Counter, float]:
    """A 2015 table 5 sheet: both sexes by single year (to an open 85+) and its total."""
    ages: Counter = Counter()
    total = None
    for row in grid:
        label = timor.tidy(timor.at(row, 0))
        value = timor.number(timor.at(row, 1))
        if value is None or not label:
            continue
        text = label[:-2] if re.fullmatch(r"\d+\.0", label) else label
        if fold(text) in ("total", "timorleste") and total is None:
            total = value
        elif fold(text) == "under1":
            ages[0] += value
        elif re.fullmatch(r"\d{1,3}", text):
            ages[int(text)] += value
        elif m := re.fullmatch(r"(\d{1,3})\s*\+", text):
            ages[int(m.group(1))] += value
    if total is None or sum(ages.values()) != total:
        raise SystemExit(f"timor_age: {where}: single years make {sum(ages.values()):,.0f}, "
                         f"against its total {total}")
    return ages, total


def check_2015_groups(units: dict[tuple, dict[str, Any]], singles: dict[str, Counter]) -> None:
    """The ten groups' median against the single years', where the volume has both."""
    widest = (0.0, "")
    for key, u in units.items():
        if u["kind"] == "post":
            continue
        who = "country" if u["kind"] == "country" else u["municipality"]
        if who not in singles:
            raise SystemExit(f"timor_age: no 2015 single years for {who}")
        ages = singles[who]
        if abs(sum(ages.values()) - sum(n for _, _, n in u["groups"]["T"])) > 0.5:
            raise SystemExit(f"timor_age: 2015 {who}: tables 5 and 6 count different people")
        exact = single_median(ages)
        rough = fine_median(u["groups"]["T"])
        if exact is None or rough is None or abs(exact - rough) > GROUPED_TOLERANCE:
            raise SystemExit(f"timor_age: 2015 {who}: the groups' median {rough} against the "
                             f"single years' {exact}")
        widest = max(widest, (round(abs(exact - rough), 2), f"{who} {rough} against {exact}"))
    log(f"  2015 groups' medians against single years', country and 13 municipalities: widest "
        f"gap {widest[0]} years ({widest[1]})")


def read_2015_workbook(path) -> tuple[dict[tuple, dict[str, Any]], dict[str, Counter]]:
    """Tables 6 and 7, checked, and table 5's single years for the country and each
    municipality (sheets 2.5 and 2.5.1a-m, the municipality read off each title)."""
    import xlrd
    book = xlrd.open_workbook(str(path))

    def grid(name: str) -> list[list[Any]]:
        sheet = book.sheet_by_name(name)
        return [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]

    units = read_2015_groups(grid("2.6"), grid("2.7"))
    singles: dict[str, Counter] = {"country": read_2015_single(grid("2.5"), "2015 table 5")[0]}
    for name in book.sheet_names():
        if not re.fullmatch(r"2,?\.5\.1[a-m]", name):
            continue
        rows = grid(name)
        title = timor.fold(timor.tidy(timor.at(rows[0], 0)) if rows else "")
        found = {mun for key, mun in timor.MUNICIPALITY_KEYS.items() if key in title}
        if len(found) != 1:
            raise SystemExit(f"timor_age: 2015 sheet {name!r}: its title names {found or 'no'} "
                             f"municipality")
        mun = found.pop()
        if mun in singles:
            raise SystemExit(f"timor_age: two 2015 sheets for {mun}")
        singles[mun] = read_2015_single(rows, f"2015 sheet {name}")[0]
    if len(singles) != 14:
        raise SystemExit(f"timor_age: 2015 single years for {len(singles) - 1} municipalities")
    check_2015_groups(units, singles)
    return units, singles


def post_medians_2015(units: dict[tuple, dict[str, Any]], admin2: list[dict[str, Any]]
                      ) -> dict[str, dict[str, Any]]:
    """Drawn post name -> its 2015 median age fields, or the reason it has none."""
    aliases = {timor.fold(a): k for k, al in {**timor.POST_ALIASES, **POST_ALIASES_2015}.items()
               for a in [k, *al]}
    posts = {}
    for key, u in units.items():
        if u["kind"] != "post":
            continue
        canon = aliases.get(key[2], key[2])
        if canon in posts:
            raise SystemExit(f"timor_age: two 2015 posts read as {canon!r}")
        posts[canon] = u
    out: dict[str, dict[str, Any]] = {}
    for shape in admin2:
        canon = aliases.get(timor.fold(shape["name"]), timor.fold(shape["name"]))
        u = posts.pop(canon, None)
        if u is None:
            raise SystemExit(f"timor_age: no 2015 post for the polygon {shape['name']!r}")
        median = fine_median(u["groups"]["T"])
        people = sum(n for _, _, n in u["groups"]["T"])
        whose = (f"the 2015 census's count of {u['name']} ({u['municipality']}, {people:,.0f} "
                 f"people)")
        if median is None:
            out[shape["name"]] = {"median_age": gap(NOT_AVAILABLE, (
                f"Fewer than half of {whose} are under 30, and above 29 the 2015 volume gives a "
                f"post's ages only as 30-64, too wide to interpolate a median in; no census "
                f"publishes a post's ages finer (the 2022 main report gives single years by "
                f"municipality only)."))}
            continue
        out[shape["name"]] = {
            "median_age": measure(median, unit="years", year=YEAR_2015, source=SOURCE_AGE_2015),
            "median_age_note": (
                f"Interpolated within the age group that holds the middle person, from {whose} "
                f"in ten groups: under 3, 3-5, 6-11, 12-14, 15-17, 18-21, 22-24, 25-29, 30-64 "
                f"and 65 and over. The 2015 volume's table 7 gives the school ages; under 3 is "
                f"table 6's under-15 less table 7's 3-14, and 30-64 its 15-64 less 15-29. The "
                f"boundary file draws the 65 posts of 2015, so the post is the polygon. The 2022 "
                f"census publishes a post's ages only as 0-14, 15-64 and 65 and over."),
        }
    if posts:
        raise SystemExit(f"timor_age: 2015 posts on no polygon: "
                         f"{sorted(u['name'] for u in posts.values())}")
    meds = sorted(f["median_age"]["value"] for f in out.values() if "value" in f["median_age"])
    log(f"  2015 posts: {len(meds)} of {len(out)} with a median below 30 to interpolate "
        f"({meds[0]}-{meds[-1]})")
    return out


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


def post_records(posts: dict[str, dict[str, float]], admin2: list[dict[str, Any]],
                 medians: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    aliases = {fold(a): k for k, al in timor.POST_ALIASES.items() for a in [k, *al]}
    medians = medians or {}
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
        # The median is the 2015 census's, where its groups reach one (the
        # sex ratio and population stay the 2022 count's).
        age = medians.get(name) or {"median_age": gap(NOT_AVAILABLE, POST_AGE_GAP)}
        sources = [{"field": "sex_ratio" + ("/population" if joined else ""),
                    "name": SOURCE_POST, "url": timor.POPULATION_PAGE, "year": YEAR,
                    "license": timor.LICENCE}]
        if "value" in age["median_age"]:
            sources.append({"field": "median_age", "name": SOURCE_AGE_2015, "url": AGE_2015_XLS,
                            "year": YEAR_2015, "license": timor.LICENCE})
        # Religion and mother tongue say why they are empty on every post,
        # in timor.py's words: its own reader reaches 64 of the 65 polygons
        # by name and leaves Hatolia, two posts since 2022, with a note about
        # joining instead.
        out.append(record(
            f"TLS-AGE-P-{fold(name)}", name, level="admin2", parent="TLS", country="TLS",
            match_by="shape_id", shape_id=shape["id"],
            religion=gap(NOT_AVAILABLE, timor.POST_RELIGION_GAP),
            language=gap(NOT_AVAILABLE, timor.POST_LANGUAGE_GAP),
            sources=sources, **fields, **age))
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
    log(f"  {SOURCE_AGE_2015}")
    path_2015 = download(AGE_2015_XLS, RAW / "timor" / AGE_2015_XLS.rsplit("/", 1)[-1])
    groups_2015, _ = read_2015_workbook(path_2015)
    admin2 = drawn("TLS", "admin2")
    medians = post_medians_2015(groups_2015, admin2)
    records = (municipality_records(units, drawn("TLS", "admin1"))
               + post_records(posts, admin2, medians))
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
