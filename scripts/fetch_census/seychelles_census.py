#!/usr/bin/env python3
"""Seychelles -- the 2022 Population and Housing Census by district.

The National Bureau of Statistics' census report (2022) prints, for the
country, its regions and its districts:

    Table 2.4   population by sex (and the sex ratio, 2022 and 2010)
    Table B3.1a population aged 3 and over by main first language spoken at home
    Table B4.1  population in all households by religion

The Bureau's download refuses the runner; the Internet Archive's copy of the
report is read.

Written: for the map's 26 districts (the 25 of Mahé and Praslin, La Digue and
Inner Islands, and the Outer Islands), the census's count, the sex ratio (men
per thousand women), first language at home and religion as counts. The
census's 27th district, Ile Perseverance (5,410 people), is the reclaimed
islands off Victoria, which no polygon of the map holds; its count is on none.

**Checks before anything is written.** Every line's men and women make its
total, and its languages and religions make theirs; the districts make the
census's 102,612.

Usage:
    python -m scripts.fetch_census.seychelles_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
from typing import Any

from ._shared import PROCESSED, log, measure, record, shares, write_json
from .southern_africa_common import fetch, key, sex_ratio, units

URL = ("https://www.nbs.gov.sc/downloads/1555-seychelles-population-and-housing-census-2022/"
       "viewdocument/1555")
ARCHIVE = ("20240814133631", "2024", "2025")
SOURCE = "National Bureau of Statistics (Seychelles), Population and Housing Census 2022 report"
LICENCE = "National Bureau of Statistics publication (reuse with attribution)"
YEAR = 2022
NATIONAL = 102_612
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


def number(text: str) -> int:
    return 0 if text in ("-", "..") else int(text.replace(",", ""))


def district_key(name: str) -> str:
    k = key(name)
    return SPELLINGS.get(k, k)


def rows_after(text: str, title: str, width: int) -> dict[str, list[int]]:
    """{district key: its figures} from the lines after a table's title whose
    name is a district's and which carry ``width`` figures."""
    out: dict[str, list[int]] = {}
    known = {district_key(d) for d in DISTRICTS}
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


def parse(text: str) -> dict[str, dict[str, Any]]:
    sexes = rows_after(text, "Table 2.4: Sex ratio at national, regional and district levels", 5)
    langs = rows_after(text, "Table B3.1a: Population aged 3 years and over by main first language",
                       11)
    rels = rows_after(text, "Table B4.1: Population in all households by religion", 9)
    out: dict[str, dict[str, Any]] = {}
    for d in DISTRICTS:
        k = district_key(d)
        if k not in sexes or k not in langs or k not in rels:
            raise SystemExit(f"seychelles_census: {d} missing from a table "
                             f"({k in sexes}, {k in langs}, {k in rels})")
        total, men, women = sexes[k][:3]
        if men + women != total:
            raise SystemExit(f"seychelles_census: {d}: {men} men and {women} women, not {total}")
        for what, row, labels in (("languages", langs[k], LANGUAGES),
                                  ("religions", rels[k], RELIGIONS)):
            if sum(row[1:]) != row[0]:
                raise SystemExit(f"seychelles_census: {d}'s {what} make {sum(row[1:])}, not "
                                 f"{row[0]}")
        lang = {g: n for g, n in zip(LANGUAGES, langs[k][1:]) if g and n}
        rel = {g: n for g, n in zip(RELIGIONS, rels[k][1:]) if g and n}
        out[k] = {"name": d, "total": total, "men": men, "women": women,
                  "language": lang, "language_of": langs[k][0], "religion": rel,
                  "religion_of": rels[k][0]}
    made = sum(v["total"] for v in out.values())
    if made != NATIONAL:
        raise SystemExit(f"seychelles_census: the districts make {made:,}, not {NATIONAL:,}")
    return out


def build(table: dict[str, dict[str, Any]], admin1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources = [{"field": "population/sex_ratio", "name": f"{SOURCE}, Table 2.4", "url": URL,
                "license": LICENCE, "year": YEAR},
               {"field": "language", "name": f"{SOURCE}, Table B3.1a", "url": URL,
                "license": LICENCE, "year": YEAR},
               {"field": "religion", "name": f"{SOURCE}, Table B4.1", "url": URL,
                "license": LICENCE, "year": YEAR}]
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
        stated_l = sum(d["language"].values())
        stated_r = sum(d["religion"].values())
        out.append(record(
            f"SYC-2022-{k}", shape["name"], level="admin1", parent="SYC", country="SYC",
            match_by="shape_id", shape_id=shape["id"], sources=sources,
            population=measure(d["total"], year=YEAR, source=f"{SOURCE}, Table 2.4"),
            population_note=f"The 2022 census's count for {d['name']}.",
            sex_ratio=sex_ratio(d["men"], d["women"], year=YEAR, source=f"{SOURCE}, Table 2.4"),
            language=shares(d["language"], total=stated_l), language_year=YEAR,
            language_basis="main first language spoken at home, population aged 3 and over",
            language_note=(f"Main first language spoken at home of the {stated_l:,} people aged 3 "
                           f"and over who gave one, of {d['language_of']:,} (Table B3.1a)."),
            religion=shares(d["religion"], total=stated_r), religion_year=YEAR,
            religion_note=(f"Religion of the {stated_r:,} people in households whose religion "
                           f"the census could classify, of {d['religion_of']:,} (Table B4.1).")))
    spare = sorted(set(table) - set(used) - UNDRAWN)
    if spare or len(set(used)) != len(used):
        raise SystemExit(f"seychelles_census: districts on no polygon or on two: {spare}")
    return out


def text_of(blob: bytes) -> str:
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        pages = list(range(30, 45)) + list(range(110, 125))
        return "\n".join(pdf.pages[i].extract_text() or "" for i in pages if i < len(pdf.pages))


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob, where = fetch(URL, archive=ARCHIVE, office=False, expect=b"%PDF")
    log(f"  read {where}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    table = parse(text_of(blob))
    records = build(table, units("SYC", "admin1"))
    for r in records:
        log(f"  {r['name']}: {r['population']['value']:,}, ratio {r['sex_ratio']['value']}, "
            f"{r['language'][:1]}, {r['religion'][:1]}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
