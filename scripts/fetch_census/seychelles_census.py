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

and the last three also for each inhabited island outside Mahé and Praslin.
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

Tables B3.1a and B4.1 put most of the Outer Islands' people in the fourth
column of each -- Gujarati, Hindu -- with the same figure island by island in
both (all 353 on Platte, all 110 on Darros, 707 of 988 in all). That reads as a
coding error, not a count: while the two columns agree so, the Outer Islands'
language and religion, and the other islands' (mostly theirs), are withheld
with the reason.

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
GARBLED_NOTE = ("The census report's tables of first language at home (Table B3.1a) and religion "
                "(Table B4.1) put {n:,} of the Outer Islands' {of:,} people in the fourth column "
                "of each, Gujarati in one and Hindu in the other, with the same figure island by "
                "island in both (all 353 on Platte, all 110 on Darros), which reads as a coding "
                "error rather than a count; {which} shown.")
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


def garbled(table: dict[str, dict[str, Any]], which: str) -> dict[str, Any] | None:
    """Language and religion withheld, with the reason, while the Outer
    Islands' fourth columns (Gujarati, Hindu) hold the same majority of them."""
    outer = table[OUTER]
    n = outer["language"].get(FOURTH[0], 0)
    if n != outer["religion"].get(FOURTH[1], 0) or 2 * n <= outer["religion_of"]:
        return None
    note = GARBLED_NOTE.format(n=n, of=outer["religion_of"], which=which)
    return {"language": gap(NOT_AVAILABLE, note), "religion": gap(NOT_AVAILABLE, note)}


def build(table: dict[str, dict[str, Any]], admin1: list[dict[str, Any]],
          age: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    fields = [("population/sex_ratio", TABLE_24), ("language", "Table B3.1a"),
              ("religion", "Table B4.1")]
    if age:
        fields.insert(1, ("median_age", "Table A2.1"))
    sources = sources_of(*fields)
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
        comp = (garbled(table, "neither is") if k == OUTER else None) or compositions([d])
        out.append(record(
            f"SYC-2022-{k}", shape["name"], level="admin1", parent="SYC", country="SYC",
            match_by="shape_id", shape_id=shape["id"], sources=sources,
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
           isle: dict[str, Any], admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
            out.append(record(
                f"SYC-2022-{k}", shape["name"], level="admin2", parent="SYC", country="SYC",
                match_by="shape_id", shape_id=shape["id"],
                sources=sources_of(("population/sex_ratio", TABLE_24),
                                   ("median_age", "Table A2.1"), ("language", "Table B3.1a"),
                                   ("religion", "Table B4.1")),
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
            out.append(record(
                f"SYC-2022-{k}", shape["name"], level="admin2", parent="SYC", country="SYC",
                match_by="shape_id", shape_id=shape["id"],
                sources=sources_of(("population/sex_ratio/median_age", "Tables A2.1 and A2.2"),
                                   ("language", "Table B3.1a"), ("religion", "Table B4.1")),
                population=measure(row["total"], year=YEAR, source=f"{SOURCE}, Table A2.1"),
                population_note=what,
                sex_ratio=sex_ratio(row["men"], row["total"] - row["men"], year=YEAR,
                                    source=f"{SOURCE}, Tables A2.1 and A2.2"),
                median_age=measure(median(row["groups"]), year=YEAR,
                                   source=f"{SOURCE}, Table A2.1"),
                median_age_note=MEDIAN_NOTE,
                **((garbled(table, "as they are most of these islands' people, neither is")
                    if k == OTHER else None) or compositions([row]))))
        else:
            raise SystemExit(f"seychelles_census: no census figures for {shape['name']!r}")
        seen.add(k)
    if seen != set(GROUPS2) | set(rest):
        raise SystemExit(f"seychelles_census: polygons missing: {set(GROUPS2) | set(rest) - seen}")
    return out


def texts_of(blob: bytes) -> tuple[str, str, str]:
    """The pages of Tables 2.4, B3.1a and B4.1, and those of A2.1 and A2.2."""
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        pages = list(range(30, 45)) + list(range(110, 125))
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
    records = (build(table, units("SYC", "admin1"), age)
               + build2(table, age, island_composition(text), units("SYC", "admin2")))
    for r in records:
        first = {f: r[f][:1] if isinstance(r[f], list) else r[f].get("note", "")[:60]
                 for f in ("language", "religion")}
        log(f"  {r['level']} {r['name']}: {r['population']['value']:,}, ratio "
            f"{r['sex_ratio']['value']}, median {r['median_age']['value']}, "
            f"{first['language']}, {first['religion']}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
