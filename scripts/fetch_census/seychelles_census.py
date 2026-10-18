#!/usr/bin/env python3
"""Seychelles -- the 2022 Population and Housing Census by district and island.

The National Bureau of Statistics' census report (2022) prints, for the
country, its regions and its districts:

    Table 2.4   population by sex (and the sex ratio, 2022 and 2010)
    Table A2.1  population by five-year age group, both sexes, by region,
                district and island
    Table A2.2  the same for men
    Table B3.1a population aged 3 and over by main first language spoken at home
    Table B4.1  population in all households by religion
    Table A7    the non-Seychellois by nationality, for the census's seven regions

and A2.1, A2.2, B3.1a and B4.1 also for each inhabited island outside Mahé and
Praslin.
The Bureau's download refuses the runner; the Internet Archive's copy of the
report is read. Tables A2.1 and A2.2 are printed rotated, and their text layer
gives each line's name a word or two a line and then its figures one a line:
the total and the 21 age groups (under 1, 1-4, five-year groups to 90-94, 95
and over). The page lists the lines bottom up, the outer islands first.

Written, at the first level: for the map's 26 districts (the 25 of Mahé and
Praslin, La Digue and Inner Islands, and the Outer Islands), the census's
count, the sex ratio (men per thousand women), the median age (interpolated
within the age group that holds the middle person), first language at home and
religion as counts. The census's 27th district, Ile Perseverance (5,410
people), is the reclaimed islands off Victoria, which no polygon of the map
holds; its count is on none.

At the second level the map draws eight larger polygons: six over whole
districts (``GROUPS2``: the four of Central Mahé 1, the four of Central Mahé 2,
East, North and West Mahé, Praslin), the island of La Digue, and the other
islands. A district group gets its districts' figures added together; La Digue
gets the tables' lines for the island, and the other islands their Outer
Islands and La Digue and Inner Islands less the island of La Digue -- count,
sex ratio, median age, first language and religion.

Nationality stands in place of ethnicity, which the census does not record,
where a polygon is one of the seven regions of Table A7: East, North and West
Mahé, Praslin, and La Digue and Inner Islands. The region's Seychellois are its
people (Table B4.1's total) less its non-Seychellois. Every other polygon says
nationality is published by region.

Tables B3.1a and B4.1 put 707 of the Outer Islands' 988 people in the fourth
column of each -- Gujarati, Hindu -- with the same figure island by island in
both (all 353 on Platte, all 110 on Darros); Table A7 counts 707 men there as
non-Seychellois whose nationality is missing; and Tables B3.1b (second
language) and C2.1 (education) give every one of the Outer Islands' people as
missing. While the two fourth columns agree so, the Outer Islands' language,
religion and nationality, and the other islands' language and religion, are
withheld, and the records give those facts as the reason.

**Checks before anything is written.** Every line's men and women make its
total, and its languages and religions make theirs; the districts make the
census's 102,612. Every age line's groups make its total, the men's never
exceed both sexes', and a district's age total is its Table 2.4 total -- but
for La Digue and Inner Islands and the Outer Islands, between which Table 2.4
and the other tables place 87 people (77 men) differently, which the notes
say. The other islands come out negative in no group.

Usage:
    python -m scripts.fetch_census.seychelles_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
from .southern_africa_common import fetch, grouped_median, joined, key, sex_ratio, units

URL = ("https://www.nbs.gov.sc/downloads/1555-seychelles-population-and-housing-census-2022/"
       "viewdocument/1555")
ARCHIVE = ("20240814133631", "2024", "2025")
SOURCE = "National Bureau of Statistics (Seychelles), Population and Housing Census 2022 report"
LICENCE = "National Bureau of Statistics publication (reuse with attribution)"
YEAR = 2022
NATIONAL = 102_612
NATIONAL_MEN = 56_226
OUT = "seychelles_census.json"
DISTRICTS = ("Ile Perseverance", "English River", "Mont Buxton", "Saint Louis", "Bel Air",
             "Mont Fleuri", "Plaisance", "Roche Caiman", "Les Mamelles", "Cascade",
             "Pointe Larue", "Anse Aux Pins", "Au Cap", "Anse Royale", "Takamaka", "Baie Lazare",
             "Anse Boileau", "Grand Anse Mahé", "Port Glaud", "Belombre", "Beau Vallon", "Glacis",
             "Anse Etoile", "Grand Anse Praslin", "Baie Sainte Anne", "La Digue and Inner Islands",
             "Outer Islands")
UNDRAWN = {"ileperseverance"}
# Spellings of the tables, reduced, -> the district's reduced name.
SPELLINGS = {"baiesteanne": "baiesainteanne", "ladigueinnerislands": "ladigueandinnerislands",
             "ladigueandinner": "ladigueandinnerislands"}
# The map's names, reduced, -> the census's, where no prefix joins them.
ALIASES = {"lariviere": "englishriver"}
LANGUAGES = ("Seychellois Creole", "English", "French", "Gujarati", "Hindi", "Tamil",
             "Other languages", None, None, None)                # don't know, refusal, missing
RELIGIONS = ("Catholic", "Anglican", "Islam", "Hindu", "Other Christian", None,
             "Other religion", None)                             # unable to classify, missing

NUM = r"(?:\d{1,3}(?:,\d{3})*|-|\.\.)"             # ".." for not applicable

# Tables A2.1 (both sexes) and A2.2 (men): the PDF's pages, counted from 0.
AGE_PAGES = (88, 89)
AGE_TITLES = ("Table A2.1: Population of Seychelles by age group",
              "Table A2.2: Population of Seychelles by age group")
# (lower bound, width) of each age group of Tables A2.1 and A2.2; 95+ is open.
AGE_GROUPS: list[tuple[int, int | None]] = ([(0, 1), (1, 4)] + [(5 * i, 5) for i in range(1, 19)]
                                            + [(95, None)])
# The two districts between which Table 2.4 and the other tables place some
# islanders differently, and how many people that may be.
MOVED, MOVED_MOST = ("ladigueandinnerislands", "outerislands"), 100
ISLAND = "ladigue"                 # the tables' line for the island of La Digue alone
# The map's second-level polygons (reduced) drawn over whole districts.
GROUPS2 = {"central1mahe": ("Bel Air", "English River", "Mont Buxton", "Saint Louis"),
           "central2mahe": ("Les Mamelles", "Mont Fleuri", "Plaisance", "Roche Caiman"),
           "eastmahe": ("Anse Aux Pins", "Anse Royale", "Au Cap", "Cascade", "Pointe Larue",
                        "Takamaka"),
           "northmahe": ("Anse Etoile", "Beau Vallon", "Belombre", "Glacis"),
           "westmahe": ("Anse Boileau", "Baie Lazare", "Grand Anse Mahé", "Port Glaud"),
           "praslin": ("Grand Anse Praslin", "Baie Sainte Anne")}
OTHER = "otherislands"             # the Outer Islands and the inner islands but La Digue
# Tables B3.1a and B4.1 put most of the Outer Islands' people in the fourth
# column of each (Gujarati, Hindu), with the same figure island by island in
# both (all 353 on Platte, all 110 on Darros): read as a coding error, and the
# Outer Islands' (and so the other islands') language and religion withheld,
# for as long as the two columns agree so.
OUTER, FOURTH = "outerislands", ("Gujarati", "Hindu")
# Table A7: the non-Seychellois by nationality (country), region and sex. Its
# regions come in three blocks of columns, each region as both sexes, men and
# women.
A7_TITLE = "Table A7: Population of Non-Seychellois by nationality"
A7_PAGE = 104                      # counted from 0
A7_BLOCKS = (("TOTAL", "Central", "East-South"), ("West", "North"),
             ("Praslin", "La Digue & Inner Islands", "Outer Islands"))
A7_ROWS = {"india": "Indian nationals", "srilanka": "Sri Lankan nationals",
           "bangladesh": "Bangladeshi nationals", "madagascar": "Malagasy nationals",
           "kenya": "Kenyan nationals", "nepal": "Nepali nationals",
           "philippines": "Filipino nationals", "mauritius": "Mauritian nationals",
           "southafrica": "South African nationals", "indonesia": "Indonesian nationals",
           "other": "Other foreign nationals", "missing": "Nationality not stated"}
NATIONALS = "Seychellois nationals"
# The census's regions and their districts.
REGIONS = {"Central": ("Ile Perseverance", "English River", "Mont Buxton", "Saint Louis",
                       "Bel Air", "Mont Fleuri", "Plaisance", "Roche Caiman", "Les Mamelles"),
           "East-South": ("Cascade", "Pointe Larue", "Anse Aux Pins", "Au Cap", "Anse Royale",
                          "Takamaka"),
           "West": ("Baie Lazare", "Anse Boileau", "Grand Anse Mahé", "Port Glaud"),
           "North": ("Belombre", "Beau Vallon", "Glacis", "Anse Etoile"),
           "Praslin": ("Grand Anse Praslin", "Baie Sainte Anne"),
           "La Digue & Inner Islands": ("La Digue and Inner Islands",),
           "Outer Islands": ("Outer Islands",)}
REGION_NAMES = {"La Digue & Inner Islands": "La Digue and Inner Islands"}
# The map's polygons whose ground is a census region (reduced) -> the region.
REGION_UNITS = {"eastmahe": "East-South", "northmahe": "North", "westmahe": "West",
                "praslin": "Praslin", "ladigueandinnerislands": "La Digue & Inner Islands"}
# Tables whose Outer Islands line gives everyone as missing, which the reason
# for withholding the islands' language and religion quotes: (title, what).
BLANK_TABLES = (("Table B3.1b:", "second language"), ("Table C2.1:", "education"))
MEDIAN_NOTE =("Interpolated within the age group that holds the middle person, from the 2022 "
               "census's population by five-year age group (Table A2.1).")
TABLE_24 = "Table 2.4"
TITLES = {"sexes": "Table 2.4: Sex ratio at national, regional and district levels",
          "languages": "Table B3.1a: Population aged 3 years and over by main first language",
          "religions": "Table B4.1: Population in all households by religion"}


def number(text: str) -> int:
    return 0 if text in ("-", "..") else int(text.replace(",", ""))


def district_key(name: str) -> str:
    k = key(name)
    return SPELLINGS.get(k, k)


def rows_after(text: str, title: str, width: int,
               extra: tuple[str, ...] = ()) -> dict[str, list[int]]:
    """{district key: its figures} from the lines after a table's title whose
    name is a district's (or one of ``extra``) and which carry ``width``
    figures."""
    out: dict[str, list[int]] = {}
    known = {district_key(d) for d in DISTRICTS} | set(extra)
    pattern = re.compile(rf"^(?P<name>[A-Za-zé&' -]+?)((?:\s+{NUM}){{{width}}})(?:\s+\d{{1,3}})?$")
    started = False
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if title in line:
            started = True
            continue
        if not started:
            continue
        if line.startswith("Table ") and title not in line:
            break
        hit = pattern.match(line)
        if hit and district_key(hit.group("name")) in known:
            out.setdefault(district_key(hit.group("name")),
                           [number(t) for t in hit.group(2).split()])
    return out


def composition(name: str, langs: list[int], rels: list[int]) -> dict[str, Any]:
    """A line's languages and religions as counts, each checked against its total."""
    for what, row in (("languages", langs), ("religions", rels)):
        if sum(row[1:]) != row[0]:
            raise SystemExit(f"seychelles_census: {name}'s {what} make {sum(row[1:])}, not "
                             f"{row[0]}")
    return {"language": {g: n for g, n in zip(LANGUAGES, langs[1:]) if g and n},
            "language_of": langs[0],
            "religion": {g: n for g, n in zip(RELIGIONS, rels[1:]) if g and n},
            "religion_of": rels[0]}


def parse(text: str) -> dict[str, dict[str, Any]]:
    """{district key: its count, sexes, languages and religions}, and under
    ``ISLAND`` the island of La Digue's languages and religions."""
    sexes = rows_after(text, TITLES["sexes"], 5)
    langs = rows_after(text, TITLES["languages"], 11, extra=(ISLAND,))
    rels = rows_after(text, TITLES["religions"], 9, extra=(ISLAND,))
    out: dict[str, dict[str, Any]] = {}
    for d in DISTRICTS:
        k = district_key(d)
        if k not in sexes or k not in langs or k not in rels:
            raise SystemExit(f"seychelles_census: {d} missing from a table "
                             f"({k in sexes}, {k in langs}, {k in rels})")
        total, men, women = sexes[k][:3]
        if men + women != total:
            raise SystemExit(f"seychelles_census: {d}: {men} men and {women} women, not {total}")
        out[k] = {"name": d, "total": total, "men": men, "women": women,
                  **composition(d, langs[k], rels[k])}
    made = sum(v["total"] for v in out.values())
    if made != NATIONAL:
        raise SystemExit(f"seychelles_census: the districts make {made:,}, not {NATIONAL:,}")
    return out


def parse_a7(text: str) -> dict[str, dict[str, Any]]:
    """{region: {"total", "men", "women", "rows": {group: both sexes}}} from
    Table A7, every block's countries checked against its Total line and the
    regions against the country's."""
    figures = rf"((?:\s+{NUM}){{6,9}})"
    out: dict[str, dict[str, Any]] = {}
    block: tuple[str, ...] | None = None
    started = False
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if A7_TITLE in line:
            started = True
            continue
        if not started:
            continue
        if line.startswith("Table ") and A7_TITLE not in line:
            break
        heads = [b for b in A7_BLOCKS if line == " ".join(b)]
        if heads:
            block = heads[0]
            continue
        hit = re.fullmatch(rf"(?P<name>[A-Za-z][A-Za-z ]*?){figures}", line)
        if block is None or not hit:
            continue
        values = [number(t) for t in hit.group(2).split()]
        if len(values) != 3 * len(block):
            raise SystemExit(f"seychelles_census: Table A7 line {line!r} has {len(values)} "
                             f"figures for {block}")
        k = key(hit.group("name"))
        for i, region in enumerate(block):
            both, men, women = values[3 * i:3 * i + 3]
            if men + women != both:
                raise SystemExit(f"seychelles_census: Table A7 {region} {k}: {men} men and "
                                 f"{women} women, not {both}")
            unit = out.setdefault(region, {"rows": {}})
            if k == "total":
                unit.update(total=both, men=men, women=women)
            elif k in A7_ROWS:
                unit["rows"][A7_ROWS[k]] = both
                unit.setdefault("row_men", {})[A7_ROWS[k]] = men
            else:
                raise SystemExit(f"seychelles_census: Table A7 row {line!r}")
    regions = [r for b in A7_BLOCKS for r in b if r != "TOTAL"]
    for region in ["TOTAL", *regions]:
        unit = out.get(region)
        if not unit or "total" not in unit or sum(unit["rows"].values()) != unit["total"]:
            raise SystemExit(f"seychelles_census: Table A7's {region} does not add up: {unit}")
    if sum(out[r]["total"] for r in regions) != out["TOTAL"]["total"]:
        raise SystemExit("seychelles_census: Table A7's regions do not make its total")
    return out


def blank_outer(text: str, title: str) -> bool:
    """Whether a table's Outer Islands line gives everyone as missing: its
    total, nothing in any column, the same total in the last."""
    started = False
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if line.startswith(title):
            started = True
            continue
        if started and line.startswith("Table "):
            break
        if started and line.startswith("Outer Islands "):
            cells = line[len("Outer Islands "):].split()
            return (len(cells) > 2 and cells[0] == cells[-1] and cells[0] != "-"
                    and all(c == "-" for c in cells[1:-1]))
    return False


def island_composition(text: str) -> dict[str, Any]:
    """The island of La Digue's languages and religions (Tables B3.1a, B4.1)."""
    langs = rows_after(text, TITLES["languages"], 11, extra=(ISLAND,))
    rels = rows_after(text, TITLES["religions"], 9, extra=(ISLAND,))
    if ISLAND not in langs or ISLAND not in rels:
        raise SystemExit("seychelles_census: no line for the island of La Digue")
    return composition("La Digue", langs[ISLAND], rels[ISLAND])


def age_rows(text: str) -> dict[str, list[list[int]]]:
    """{reduced name: [figures of each line of that name]} from a rotated age
    table: a line's name comes a word or two a line, then its figures one a
    line -- the total and the age groups."""
    figure = re.compile(rf"^{NUM}$")
    out: dict[str, list[list[int]]] = {}
    name: list[str] = []
    figs: list[int] = []

    def close() -> None:
        if name and len(figs) == 1 + len(AGE_GROUPS):
            out.setdefault(district_key(" ".join(name)), []).append(list(figs))

    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        if figure.match(line):
            figs.append(number(line))
            continue
        if figs:
            close()
            name, figs = [], []
        name.append(line)
    close()
    return out


def ages(both_text: str, men_text: str,
         table: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{district key, or ``ISLAND``: {"total", "men", "groups", "moved"}} from
    Tables A2.1 and A2.2, checked against each other and against Table 2.4."""
    for text, title in zip((both_text, men_text), AGE_TITLES):
        if title not in " ".join(text.split()):
            raise SystemExit(f"seychelles_census: no {title!r} on its page")
    both, men = age_rows(both_text), age_rows(men_text)
    out: dict[str, dict[str, Any]] = {}
    for k in [district_key(d) for d in DISTRICTS] + [ISLAND]:
        if len(both.get(k, [])) != 1 or len(men.get(k, [])) != 1:
            raise SystemExit(f"seychelles_census: {k} has {len(both.get(k, []))} line(s) in "
                             f"Table A2.1 and {len(men.get(k, []))} in A2.2")
        b, m = both[k][0], men[k][0]
        if sum(b[1:]) != b[0] or sum(m[1:]) != m[0] or any(x > y for x, y in zip(m, b)):
            raise SystemExit(f"seychelles_census: {k}'s age groups do not add up: {b} {m}")
        out[k] = {"total": b[0], "men": m[0], "groups": b[1:], "moved": 0}
    districts = [district_key(d) for d in DISTRICTS]
    if sum(out[k]["total"] for k in districts) != NATIONAL \
            or sum(out[k]["men"] for k in districts) != NATIONAL_MEN:
        raise SystemExit("seychelles_census: Table A2.1's districts do not make the country")
    for k in districts:
        moved = (out[k]["total"] - table[k]["total"], out[k]["men"] - table[k]["men"])
        if moved != (0, 0) and (k not in MOVED or max(map(abs, moved)) > MOVED_MOST):
            raise SystemExit(f"seychelles_census: {k} is {out[k]['total']:,} ({out[k]['men']:,} "
                             f"men) in Table A2.1 against {table[k]['total']:,} in Table 2.4")
        out[k]["moved"] = moved[0]
    return out


def median(groups: list[int]) -> float | None:
    return grouped_median([(lo, w, n) for (lo, w), n in zip(AGE_GROUPS, groups)])


def moved_note(k: str, table: dict[str, dict[str, Any]], age: dict[str, dict[str, Any]]) -> str:
    if not age[k]["moved"]:
        return MEDIAN_NOTE
    return (f"{MEDIAN_NOTE} That table counts {age[k]['total']:,} people here where Table 2.4 "
            f"counts {table[k]['total']:,}: the two place {abs(age[k]['moved']):,} islanders of "
            f"La Digue and Inner Islands and the Outer Islands differently.")


def sources_of(*fields: tuple[str, str]) -> list[dict[str, Any]]:
    return [{"field": f, "name": f"{SOURCE}, {t}", "url": URL, "license": LICENCE, "year": YEAR}
            for f, t in fields]


def compositions(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Language and religion of lines added together, with their notes."""
    lang: dict[str, int] = {}
    rel: dict[str, int] = {}
    for d in parts:
        for g, n in d["language"].items():
            lang[g] = lang.get(g, 0) + n
        for g, n in d["religion"].items():
            rel[g] = rel.get(g, 0) + n
    stated_l, stated_r = sum(lang.values()), sum(rel.values())
    of_l, of_r = sum(d["language_of"] for d in parts), sum(d["religion_of"] for d in parts)
    return {
        "language": shares(lang, total=stated_l), "language_year": YEAR,
        "language_basis": "main first language spoken at home, population aged 3 and over",
        "language_note": (f"Main first language spoken at home of the {stated_l:,} people aged 3 "
                          f"and over who gave one, of {of_l:,} (Table B3.1a)."),
        "religion": shares(rel, total=stated_r), "religion_year": YEAR,
        "religion_note": (f"Religion of the {stated_r:,} people in households whose religion the "
                          f"census could classify, of {of_r:,} (Table B4.1)."),
    }


def recorded_alike(table: dict[str, dict[str, Any]]) -> int:
    """How many of the Outer Islands' people Tables B3.1a and B4.1 both put in
    their fourth column (Gujarati, Hindu), where that is most of them; else 0."""
    outer = table[OUTER]
    n = outer["language"].get(FOURTH[0], 0)
    if n != outer["religion"].get(FOURTH[1], 0) or 2 * n <= outer["religion_of"]:
        return 0
    return n


def garbled(table: dict[str, dict[str, Any]], evidence: dict[str, Any],
            other: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Language and religion withheld, with the facts as the reason, while the
    Outer Islands' fourth columns (Gujarati, Hindu) hold the same majority of
    them. ``other``: the other islands' line, for that polygon's note."""
    n = recorded_alike(table)
    if not n:
        return None
    outer = table[OUTER]
    alike = (f"the same {n:,} of the Outer Islands' {outer['religion_of']:,} people as "
             f"Gujarati-speaking (Table B3.1a) and as Hindu (Table B4.1), island by island alike "
             f"(all 353 on Platte, all 110 on Darros)")
    more = []
    if evidence.get("a7_missing") == n:
        men = " men" if evidence.get("a7_missing_men") == n else ""
        more.append(f"its table of the non-Seychellois (Table A7) counts {n:,}{men} there whose "
                    f"nationality is missing")
    blank = evidence.get("blank") or []
    if blank:
        tables = joined([t.rstrip(":").replace("Table ", "") for t, _ in blank])
        what = joined([w for _, w in blank])
        more.append(f"its tables of {what} (Table{'s' if len(blank) > 1 else ''} {tables}) "
                    f"give every one of the Outer Islands' people as missing")
    if other is None:
        note = (f"The 2022 census report records {alike}; " + "; ".join(more) + ". With most "
                f"of the islands' answers missing or recorded alike, neither language nor "
                f"religion is shown.") if more else (
                f"The 2022 census report records {alike}. With most of the islands' answers "
                f"recorded alike, neither language nor religion is shown.")
    else:
        unrecorded = other["religion_of"] - sum(other["religion"].values())
        note = (f"These islands' {other['religion_of']:,} people include the Outer Islands' "
                f"{outer['religion_of']:,}, and the 2022 census report records "
                + alike.replace(f" of the Outer Islands' {outer['religion_of']:,} people",
                                " of those")
                + (f"; {more[0]}" if more and more[0].startswith("its table of the non") else "")
                + f"; the religion of {unrecorded:,} more of these islands' people is missing "
                  f"or could not be classified. With most of these islands' answers missing or "
                  f"recorded alike, neither language nor religion is shown.")
    return {"language": gap(NOT_AVAILABLE, note), "religion": gap(NOT_AVAILABLE, note)}


def region_of(k: str) -> str:
    """The census region a district (reduced) is in."""
    for region, districts in REGIONS.items():
        if k in {district_key(d) for d in districts}:
            return region
    raise SystemExit(f"seychelles_census: no region for {k}")


def nationality(region: str, people: int, a7: dict[str, dict[str, Any]] | None,
                where: str) -> dict[str, Any]:
    """A region's people by nationality, in place of ethnicity (Table A7)."""
    if not a7:
        return {}
    unit = a7[region]
    counts = {NATIONALS: people - unit["total"], **unit["rows"]}
    top = sorted(((n, g) for g, n in unit["rows"].items()
                  if n and g not in ("Other foreign nationals", "Nationality not stated")),
                 key=lambda x: (-x[0], x[1]))[:3]
    listed = joined([f"{n:,} {g.replace(' nationals', '')}" for n, g in top])
    return {"ethnicity": shares({g: n for g, n in counts.items() if n}, total=people),
            "ethnicity_year": YEAR, "ethnicity_basis": "nationality",
            "ethnicity_note": (
                f"Nationality, not ethnicity: the 2022 census records no ethnic group, and its "
                f"report counts each region's non-Seychellois by nationality (Table A7). "
                f"{where}: of its {people:,} people (Table B4.1), {unit['total']:,} are "
                f"non-Seychellois, the most of them {listed}; the rest are Seychellois.")}


def no_nationality(k: str, a7: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    """Why a polygon that is not one of Table A7's regions has no nationality."""
    if not a7:
        return {}
    if k == OUTER:
        missing = a7[REGIONS_OF_OUTER]["rows"].get("Nationality not stated", 0)
        note = (f"Nationality, which the 2022 census report gives by region in place of ethnic "
                f"group (Table A7), is not shown: of the {a7[REGIONS_OF_OUTER]['total']:,} "
                f"people it counts as non-Seychellois on the Outer Islands, {missing:,} have "
                f"their nationality missing, the same number its tables of language and "
                f"religion record alike as Gujarati-speaking and Hindu.")
    elif k == OTHER:
        note = ("The 2022 census report gives nationality by region (Table A7), and these "
                "islands are parts of two regions, the Outer Islands and La Digue and Inner "
                "Islands, so no figure is shown for them; it records no ethnic group.")
    elif k == ISLAND:
        note = ("The 2022 census report gives nationality by region (Table A7), for La Digue "
                "and Inner Islands as a whole and not for the island of La Digue alone, and "
                "records no ethnic group.")
    elif k in GROUPS2:
        note = ("The 2022 census report gives nationality by region (Table A7); these "
                "districts are part of the Central region, which takes in districts drawn "
                "elsewhere, so no figure is shown for them, and it records no ethnic group.")
    else:
        note = (f"The 2022 census report gives nationality by region (Table A7: this district "
                f"is in the {REGION_NAMES.get(region_of(k), region_of(k))} region), not by "
                f"district, and records no ethnic group.")
    return {"ethnicity": gap(NOT_AVAILABLE, note)}


REGIONS_OF_OUTER = "Outer Islands"


def build(table: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
          age: dict[str, dict[str, Any]] | None = None,
          a7: dict[str, dict[str, Any]] | None = None,
          evidence: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    fields = [("population/sex_ratio", TABLE_24), ("language", "Table B3.1a"),
              ("religion", "Table B4.1")]
    if age:
        fields.insert(1, ("median_age", "Table A2.1"))
    sources = sources_of(*fields)
    withheld = sources_of(*[f for f in fields if f[0] not in ("language", "religion")],
                          ("language note/religion note",
                           "Tables A7, B3.1a, B3.1b, B4.1 and C2.1"))
    out = []
    used = []
    for shape in admin1:
        want = ALIASES.get(key(shape["name"]), key(shape["name"]))
        hits = [k for k in table if k == want or k.startswith(want)]
        if len(hits) != 1:
            raise SystemExit(f"seychelles_census: {shape['name']!r} is {hits}")
        k = hits[0]
        used.append(k)
        d = table[k]
        extra: dict[str, Any] = {}
        if age:
            extra = {"median_age": measure(median(age[k]["groups"]), year=YEAR,
                                           source=f"{SOURCE}, Table A2.1"),
                     "median_age_note": moved_note(k, table, age)}
        comp = (garbled(table, evidence or {}) if k == OUTER else None) or compositions([d])
        cited = withheld if isinstance(comp.get("language"), dict) else sources
        if k in REGION_UNITS:
            ethnic = nationality(REGION_UNITS[k], d["religion_of"], a7,
                                 f"{shape['name']} is one of the census's regions as well as "
                                 f"a district")
            cited = cited + (sources_of(("ethnicity", "Table A7")) if ethnic else [])
        else:
            ethnic = no_nationality(k, a7)
            cited = cited + (sources_of(("ethnicity note", "Table A7")) if ethnic else [])
        out.append(record(
            f"SYC-2022-{k}", shape["name"], level="admin1", parent="SYC", country="SYC",
            match_by="shape_id", shape_id=shape["id"], sources=cited, **ethnic,
            population=measure(d["total"], year=YEAR, source=f"{SOURCE}, {TABLE_24}"),
            population_note=f"The 2022 census's count for {d['name']}.",
            sex_ratio=sex_ratio(d["men"], d["women"], year=YEAR, source=f"{SOURCE}, {TABLE_24}"),
            **comp, **extra))
    spare = sorted(set(table) - set(used) - UNDRAWN)
    if spare or len(set(used)) != len(used):
        raise SystemExit(f"seychelles_census: districts on no polygon or on two: {spare}")
    return out


def islands(age: dict[str, dict[str, Any]], table: dict[str, dict[str, Any]],
            isle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The island of La Digue, and the other islands (the Outer Islands and La
    Digue and Inner Islands less La Digue): ages, sexes, languages, religions."""
    inner, outer = "ladigueandinnerislands", "outerislands"
    other: dict[str, Any] = {
        "total": age[inner]["total"] + age[outer]["total"] - age[ISLAND]["total"],
        "men": age[inner]["men"] + age[outer]["men"] - age[ISLAND]["men"],
        "groups": [a + b - c for a, b, c in zip(age[inner]["groups"], age[outer]["groups"],
                                                age[ISLAND]["groups"])]}
    for f in ("language", "religion"):
        names = set(table[inner][f]) | set(table[outer][f]) | set(isle[f])
        counts = {g: table[inner][f].get(g, 0) + table[outer][f].get(g, 0) - isle[f].get(g, 0)
                  for g in names}
        other[f] = {g: n for g, n in counts.items() if n}
        other[f + "_of"] = (table[inner][f + "_of"] + table[outer][f + "_of"]
                            - isle[f + "_of"])
        if min(counts.values(), default=0) < 0:
            raise SystemExit(f"seychelles_census: the other islands' {f} comes out negative")
    if min(other["groups"]) < 0 or other["men"] > other["total"]:
        raise SystemExit(f"seychelles_census: the other islands come out negative: {other}")
    return {ISLAND: {**age[ISLAND], **isle}, OTHER: other}


def build2(table: dict[str, dict[str, Any]], age: dict[str, dict[str, Any]],
           isle: dict[str, Any], admin2: list[dict[str, Any]],
           a7: dict[str, dict[str, Any]] | None = None,
           evidence: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    out = []
    seen = set()
    rest = islands(age, table, isle)
    for shape in admin2:
        k = key(shape["name"])
        if k in GROUPS2:
            parts = [table[district_key(n)] for n in GROUPS2[k]]
            groups = [sum(g) for g in zip(*(age[district_key(n)]["groups"] for n in GROUPS2[k]))]
            men, women = sum(d["men"] for d in parts), sum(d["women"] for d in parts)
            total = sum(d["total"] for d in parts)
            if sum(groups) != total:
                raise SystemExit(f"seychelles_census: {shape['name']}'s ages make {sum(groups)}")
            if k in REGION_UNITS and a7:
                region = REGION_UNITS[k]
                if {district_key(n) for n in GROUPS2[k]} != {district_key(n)
                                                             for n in REGIONS[region]}:
                    raise SystemExit(f"seychelles_census: {shape['name']} is not the "
                                     f"{region} region")
                ethnic = nationality(region, sum(d["religion_of"] for d in parts), a7,
                                     f"{shape['name']}, its {len(parts)} districts, is the "
                                     f"census's {REGION_NAMES.get(region, region)} region")
                extra_src = sources_of(("ethnicity", "Table A7")) if ethnic else []
            elif k in REGION_UNITS:
                ethnic, extra_src = {}, []
            else:
                ethnic = no_nationality(k, a7)
                extra_src = sources_of(("ethnicity note", "Table A7")) if ethnic else []
            out.append(record(
                f"SYC-2022-{k}", shape["name"], level="admin2", parent="SYC", country="SYC",
                match_by="shape_id", shape_id=shape["id"], **ethnic,
                sources=sources_of(("population/sex_ratio", TABLE_24),
                                   ("median_age", "Table A2.1"), ("language", "Table B3.1a"),
                                   ("religion", "Table B4.1")) + extra_src,
                population=measure(total, year=YEAR, source=f"{SOURCE}, {TABLE_24}"),
                population_note=(f"The 2022 census's counts for the {len(parts)} districts the map "
                                 f"draws as one added together: {joined(list(GROUPS2[k]))}."),
                sex_ratio=sex_ratio(men, women, year=YEAR, source=f"{SOURCE}, {TABLE_24}"),
                median_age=measure(median(groups), year=YEAR, source=f"{SOURCE}, Table A2.1"),
                median_age_note=MEDIAN_NOTE, **compositions(parts)))
        elif k in rest:
            row = rest[k]
            what = ("The 2022 census's count for the island of La Digue, which Tables A2.1, B3.1a "
                    "and B4.1 give apart from the other islands of its district." if k == ISLAND
                    else "The 2022 census's counts for the Outer Islands and for the inner islands "
                         "other than La Digue added together: the tables' Outer Islands and La "
                         "Digue and Inner Islands, less the island of La Digue, which they give "
                         "apart.")
            comp = (garbled(table, evidence or {}, row) if k == OTHER else None) \
                or compositions([row])
            withheld = isinstance(comp.get("language"), dict)
            ethnic = no_nationality(k, a7)
            out.append(record(
                f"SYC-2022-{k}", shape["name"], level="admin2", parent="SYC", country="SYC",
                match_by="shape_id", shape_id=shape["id"], **ethnic,
                sources=sources_of(("population/sex_ratio/median_age", "Tables A2.1 and A2.2"),
                                   *((("language note/religion note",
                                       "Tables A7, B3.1a, B4.1"),) if withheld else
                                     (("language", "Table B3.1a"), ("religion", "Table B4.1"))))
                + (sources_of(("ethnicity note", "Table A7")) if ethnic else []),
                population=measure(row["total"], year=YEAR, source=f"{SOURCE}, Table A2.1"),
                population_note=what,
                sex_ratio=sex_ratio(row["men"], row["total"] - row["men"], year=YEAR,
                                    source=f"{SOURCE}, Tables A2.1 and A2.2"),
                median_age=measure(median(row["groups"]), year=YEAR,
                                   source=f"{SOURCE}, Table A2.1"),
                median_age_note=MEDIAN_NOTE, **comp))
        else:
            raise SystemExit(f"seychelles_census: no census figures for {shape['name']!r}")
        seen.add(k)
    if seen != set(GROUPS2) | set(rest):
        raise SystemExit(f"seychelles_census: polygons missing: {set(GROUPS2) | set(rest) - seen}")
    return out


def texts_of(blob: bytes) -> tuple[str, str, str]:
    """The pages of Tables 2.4, A7, B3.1a, B3.1b, B4.1 and C2.1, and those of
    A2.1 and A2.2."""
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        pages = list(range(30, 45)) + [A7_PAGE] + list(range(110, 125))
        text = "\n".join(pdf.pages[i].extract_text() or "" for i in pages if i < len(pdf.pages))
        both, men = (pdf.pages[i].extract_text() or "" for i in AGE_PAGES)
    return text, both, men


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob, where = fetch(URL, archive=ARCHIVE, office=False, expect=b"%PDF")
    log(f"  read {where}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    text, both, men = texts_of(blob)
    table = parse(text)
    age = ages(both, men, table)
    log(f"  the country's median age: "
        f"{median([sum(g) for g in zip(*(age[district_key(d)]['groups'] for d in DISTRICTS))])}")
    a7 = parse_a7(text)
    evidence = {"a7_missing": a7["Outer Islands"]["rows"].get("Nationality not stated"),
                "a7_missing_men": a7["Outer Islands"]["row_men"].get("Nationality not stated"),
                "blank": [(t, w) for t, w in BLANK_TABLES if blank_outer(text, t)]}
    log(f"  Table A7: {[(r, u['total']) for r, u in a7.items()]}; Outer Islands' "
        f"evidence: {evidence}")
    records = (build(table, units("SYC", "admin1"), age, a7, evidence)
               + build2(table, age, island_composition(text), units("SYC", "admin2"), a7,
                        evidence))
    for r in records:
        first = {f: r[f][:1] if isinstance(r[f], list) else r[f].get("note", "")[:60]
                 for f in ("language", "religion", "ethnicity")}
        log(f"  {r['level']} {r['name']}: {r['population']['value']:,}, ratio "
            f"{r['sex_ratio']['value']}, median {r['median_age']['value']}, "
            f"{first['language']}, {first['religion']}, {first['ethnicity']}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
