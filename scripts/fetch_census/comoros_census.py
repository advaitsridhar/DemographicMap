#!/usr/bin/env python3
"""Comoros -- the 2017 census (RGPH 2017) by island and prefecture.

INSEED's "Rapport des résultats globaux du RGPH 2017" closes with Tableau A.2,
the population of every island, prefecture and commune, men and women. A line
reads

    Préfecture de FOMBONI 30 835 15 979 14 856

-- total, men and women, each written with a space between its thousands (a
six-figure total sometimes without one). The three are told apart by the one
split of the digit groups whose men and women make the total.

Written: the census's count and sex ratio (men per thousand women) of the
three islands and of the prefectures the map draws. The map draws Anjouan's
six prefectures as five polygons -- Moya's ground is inside Sima's (the town
of Moya falls in that polygon) -- and Grande Comore's Mitsamiouli and Mboudé
as one, so those polygons get the two prefectures added together, and say so.
The map's Kartala is the 5.5 km2 crater of Mount Karthala, which no
prefecture of the census is: it gets a stated reason. Median age, religion,
language and ethnicity are empty with their reasons.

**Checks before anything is written.** Every line's men and women make its
total; each prefecture's communes make it; each island's prefectures make it;
the islands make the census's 758,316.

Usage:
    python -m scripts.fetch_census.comoros_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
from itertools import combinations
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, write_json
from .southern_africa_common import fetch, joined, key, sex_ratio, units

URL = "https://www.nada.inseed-comores.org/index.php/catalog/8/download/70"
SOURCE = ("INSEED Comores, Recensement Général de la Population et de l'Habitat 2017, "
          "Rapport des résultats globaux, Tableau A.2")
LICENCE = "INSEED Comores publication (reuse with attribution)"
YEAR = 2017
NATIONAL = 758_316
OUT = "comoros_census.json"
TITLE = "Tableau A.2"

# The census's islands -> the map's first-level units.
ISLANDS = {"mwali": "Moheli", "ndzuwani": "Anjouan", "ngazidja": "Grande Comore"}
ISLAND_NAMES = {"mwali": "Mwali (Mohéli)", "ndzuwani": "Ndzuwani (Anjouan)",
                "ngazidja": "Ngazidja (Grande Comore)"}
# The map's polygon (reduced) -> the census prefectures it holds, where they
# are not one for one by name.
POLYGONS = {"nioumachioi": ["NIOUMACHOUA"], "sima": ["SIMA", "MOYA"],
            "mitsamioulimboude": ["MITSAMIOULI", "MBOUDE"]}
NO_PREFECTURE = {"kartala": (
    "No prefecture of the 2017 census is drawn here: the polygon is the crater of Mount "
    "Karthala (5.5 km2), and INSEED's Tableau A.2 lists Grande Comore's nine prefectures, all "
    "drawn on other polygons.")}

AGE_NOTE = ("INSEED's reports of the 2017 census give the median age for the whole country "
            "(19.4 years) and for its urban and rural areas, not for each island or "
            "prefecture.")
COMPOSITION_NOTE = ("INSEED's reports of the 2017 census publish no religion, language or "
                    "ethnic group by island or prefecture.")

NUMBERS = re.compile(r"^(?P<name>.*?[A-Za-zé])\s+(?P<nums>\d+(?: \d{3})*(?: \d+(?: \d{3})*)*)$")


def splits(tokens: list[str]) -> list[tuple[int, int, int]]:
    """Every reading of the digit groups as total, men and women whose men and
    women make the total."""

    def number(parts: list[str]) -> int | None:
        if not parts:
            return None
        if len(parts) > 1 and (len(parts[0]) > 3 or any(len(p) != 3 for p in parts[1:])):
            return None
        return int("".join(parts))

    out = []
    for i, j in combinations(range(1, len(tokens)), 2):
        t, m, f = number(tokens[:i]), number(tokens[i:j]), number(tokens[j:])
        if None not in (t, m, f) and m + f == t:
            out.append((t, m, f))
    return out


def parse(text: str) -> dict[str, Any]:
    """{"national": row, "islands": {key: row}, "prefectures": {name: row}}."""
    out: dict[str, Any] = {"national": None, "islands": {}, "prefectures": {}}
    island = prefecture = None
    started = False
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if TITLE in line:
            started = True
            continue
        if not started:
            continue
        hit = NUMBERS.match(line)
        if not hit:
            continue
        options = splits(hit.group("nums").split())
        if len(options) != 1:
            raise SystemExit(f"comoros_census: {line!r} reads as {options}")
        total, men, women = options[0]
        name = hit.group("name").strip()
        row = {"name": name, "total": total, "men": men, "women": women, "communes": []}
        upper = name.upper()
        if upper.startswith("UNION DES COMORES"):
            out["national"] = row
        elif key(re.sub(r"(?i)^ile de\s+", "", name)) in ISLANDS:
            island = key(re.sub(r"(?i)^ile de\s+", "", name))
            out["islands"][island] = {**row, "prefectures": []}
            prefecture = None
        elif upper.startswith("PRÉFECTURE DE") or upper.startswith("PREFECTURE DE"):
            if island is None:
                raise SystemExit(f"comoros_census: {name} comes before any island")
            prefecture = re.sub(r"(?i)^pr[ée]fecture de\s+", "", name).strip()
            row["island"] = island
            out["prefectures"][prefecture] = row
            out["islands"][island]["prefectures"].append(prefecture)
        elif upper.startswith("COMMUNE DE"):
            if prefecture is None:
                raise SystemExit(f"comoros_census: {name} comes before any prefecture")
            out["prefectures"][prefecture]["communes"].append(row)
    check(out)
    return out


def check(table: dict[str, Any]) -> None:
    national = table["national"]
    if national is None or national["total"] != NATIONAL:
        raise SystemExit(f"comoros_census: the country's line is {national}, not {NATIONAL:,}")
    if sorted(table["islands"]) != sorted(ISLANDS):
        raise SystemExit(f"comoros_census: the islands read are {sorted(table['islands'])}")
    for field in ("total", "men", "women"):
        if sum(i[field] for i in table["islands"].values()) != national[field]:
            raise SystemExit(f"comoros_census: the islands do not make the country's {field}")
        for k, isl in table["islands"].items():
            made = sum(table["prefectures"][p][field] for p in isl["prefectures"])
            if made != isl[field]:
                raise SystemExit(f"comoros_census: {isl['name']}'s prefectures make {made:,} "
                                 f"{field}, not {isl[field]:,}")
        for name, p in table["prefectures"].items():
            made = sum(c[field] for c in p["communes"])
            if p["communes"] and made != p[field]:
                raise SystemExit(f"comoros_census: {name}'s communes make {made:,} {field}, "
                                 f"not {p[field]:,}")
    log(f"  {len(table['islands'])} islands, {len(table['prefectures'])} prefectures, "
        f"{sum(len(p['communes']) for p in table['prefectures'].values())} communes")


SOURCES = [{"field": "population/sex_ratio", "name": SOURCE, "url": URL, "license": LICENCE,
            "year": YEAR}]


def fields(rows: list[dict[str, Any]], note: str) -> dict[str, Any]:
    total = sum(r["total"] for r in rows)
    men = sum(r["men"] for r in rows)
    women = sum(r["women"] for r in rows)
    return {"population": measure(total, year=YEAR, source=SOURCE), "population_note": note,
            "sex_ratio": sex_ratio(men, women, year=YEAR, source=SOURCE),
            "median_age": gap(NOT_AVAILABLE, AGE_NOTE),
            "religion": gap(NOT_AVAILABLE, COMPOSITION_NOTE),
            "language": gap(NOT_AVAILABLE, COMPOSITION_NOTE),
            "ethnicity": gap(NOT_AVAILABLE, COMPOSITION_NOTE)}


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    by_name = {key(n): n for n in table["prefectures"]}
    used: list[str] = []
    for shape in admin2:
        k = key(shape["name"])
        if k in NO_PREFECTURE:
            out.append(record(f"COM-2017-{k}", shape["name"], level="admin2", parent="COM",
                              country="COM", match_by="shape_id", shape_id=shape["id"],
                              sources=SOURCES,
                              population=gap(NOT_AVAILABLE, NO_PREFECTURE[k]),
                              sex_ratio=gap(NOT_AVAILABLE, NO_PREFECTURE[k])))
            continue
        names = POLYGONS.get(k) or ([by_name[k]] if k in by_name else [])
        if not names or any(n not in table["prefectures"] for n in names):
            raise SystemExit(f"comoros_census: no prefecture for the polygon {shape['name']!r}")
        used += names
        titled = [n.title() for n in names]
        note = (f"The 2017 census's count for the prefecture of {titled[0]}." if len(names) == 1
                else f"The 2017 census's counts for the prefectures of {joined(titled)} added "
                     f"together: the map draws them as one.")
        out.append(record(f"COM-2017-{k}", shape["name"], level="admin2", parent="COM",
                          country="COM", match_by="shape_id", shape_id=shape["id"],
                          sources=SOURCES,
                          **fields([table["prefectures"][n] for n in names], note)))
    spare = sorted(set(table["prefectures"]) - set(used))
    if spare or len(used) != len(set(used)):
        raise SystemExit(f"comoros_census: prefectures on no polygon or on two: {spare}")
    for k, isl in table["islands"].items():
        shape = next((s for s in admin1 if key(s["name"]) == key(ISLANDS[k])), None)
        if shape is None:
            raise SystemExit(f"comoros_census: the map draws no {ISLANDS[k]}")
        out.append(record(f"COM-2017-island-{k}", shape["name"], level="admin1", parent="COM",
                          country="COM", match_by="shape_id", shape_id=shape["id"],
                          sources=SOURCES,
                          **fields([isl], f"The 2017 census's count for the island of "
                                          f"{ISLAND_NAMES[k]}.")))
    return out


def text_of(blob: bytes) -> str:
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages[-6:])


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob, where = fetch(URL, archive=("2024", "2025"), expect=b"%PDF")
    log(f"  read {where}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    table = parse(text_of(blob))
    records = build(table, units("COM", "admin1"), units("COM", "admin2"))
    for r in records:
        log(f"  {r['level']} {r['name']}: {r['population'].get('value')}, ratio "
            f"{r['sex_ratio'].get('value')}; {r.get('population_note', '')}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
