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
prefecture of the census is: it gets a stated reason. Median age and religion
are empty with their reasons.

The same report gives two compositions by island, which the islands carry:
Tableau 3, the foreign residents by nationality (grouped by region of the
world), shown as nationality in place of ethnicity -- the island's Comorian
nationals are its residents less its foreigners -- and Tableau 4, how many of
each island's residents speak each of six languages, several answers
allowed, shown as the share of the residents who speak each, which add up to
more than 100. Neither table is published by prefecture, and the prefectures
say so.

**Checks before anything is written.** Every line's men and women make its
total; each prefecture's communes make it; each island's prefectures make it;
the islands make the census's 758,316. In Tableaux 3 and 4 each line's three
islands make its total (two of Tableau 4's lines miss it by one person), the
regions make each island's foreigners, and the country's shares of French and
Arabic speakers are the report's own 33.6% and 6.6%.

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

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json
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
RELIGION_NOTE = ("INSEED's reports of the 2017 census publish no religion for the islands or "
                 "the prefectures.")
PREFECTURE_LANGUAGE_NOTE = ("INSEED's 2017 census report counts the speakers of each language by "
                            "island (Tableau 4), not by prefecture.")
PREFECTURE_ETHNICITY_NOTE = ("INSEED's 2017 census report records no ethnic group, and gives the "
                             "residents' nationality by island (Tableau 3), not by prefecture.")

# Tableaux 3 and 4 of the same report: their pages (counted from 0), titles and
# island columns in the order printed.
TABLE_PAGES = range(15, 35)
TABLE3, TABLE4 = "Tableau 3", "Tableau 4"
COLUMNS = ("mwali", "ndzuwani", "ngazidja")
TABLES_SOURCE = ("INSEED Comores, Recensement Général de la Population et de l'Habitat 2017, "
                 "Rapport des résultats globaux, Tableaux 3 and 4")
# Tableau 3's regions of nationality, reduced -> how a note names them.
REGIONS = {"afriqueaustrale": "southern Africa", "afriquecentrale": "central Africa",
           "afriquedelest": "eastern Africa", "afriquedelouest": "western Africa",
           "afriquedunord": "northern Africa", "ameriquedunord": "North America",
           "ameriquedusud": "South America", "asie": "Asia", "europe": "Europe",
           "moyenprocheorient": "the Middle East", "oceanindien": "the Indian Ocean",
           "oceanie": "Oceania"}
ALL_FOREIGN = "ensembledesetrangers"
NATIONALS, FOREIGNERS = "Comorian nationals", "Foreign nationals"
# Tableau 4's languages, reduced -> their names.
LANGUAGES = {"shicomor": "Comorian", "francais": "French", "arabe": "Arabic",
             "anglais": "English", "malgache": "Malagasy", "swahili": "Swahili"}
LANGUAGE_BASIS = "languages spoken (multi-response)"
# The report's own shares of the country's residents who speak French and Arabic.
SPOKEN_SHARES = {"French": 33.6, "Arabic": 6.6}
# How far a line's three islands may miss its total (Tableau 4's Shicomor and
# Français lines miss by one person).
SLACK = 2

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


def readings(tokens: list[str], total_first: bool) -> list[tuple[int, ...]]:
    """Every reading of the digit groups as three islands and their total (first
    or last) whose islands make the total to within ``SLACK``."""

    def number(parts: list[str]) -> int | None:
        if not parts or (len(parts) > 1 and (len(parts[0]) > 3
                                             or any(len(p) != 3 for p in parts[1:]))):
            return None
        return int("".join(parts))

    out = []
    for i, j, k in combinations(range(1, len(tokens)), 3):
        nums = [number(tokens[:i]), number(tokens[i:j]), number(tokens[j:k]), number(tokens[k:])]
        if None in nums:
            continue
        total, parts = (nums[0], nums[1:]) if total_first else (nums[3], nums[:3])
        if abs(sum(parts) - total) <= SLACK:
            out.append((*parts, total))
    return out


def table_lines(text: str, title: str) -> list[str]:
    """The lines of a table, from its title to its source line."""
    out: list[str] = []
    started = False
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not started:
            started = (line.startswith(title + " ") or line.startswith(title + ":")) \
                and "...." not in line
            continue
        if line.startswith("Source"):
            break
        out.append(line)
    if not started:
        raise SystemExit(f"comoros_census: no {title}")
    return out


def one_reading(line: str, tokens: list[str], total_first: bool) -> tuple[int, ...]:
    found = readings(tokens, total_first)
    if len(found) != 1:
        raise SystemExit(f"comoros_census: {line!r} reads as {found}")
    *parts, total = found[0]
    if sum(parts) != total:
        log(f"  {line!r}: the islands make {sum(parts):,}, the total is {total:,}")
    return found[0]


def nationalities(text: str) -> dict[str, dict[str, int]]:
    """{island: {region of nationality (reduced): foreign residents}}, with the
    island's foreigners under ``ALL_FOREIGN`` (Tableau 3), checked."""
    out: dict[str, dict[str, int]] = {c: {} for c in COLUMNS}
    for line in table_lines(text, TABLE3):
        tokens = line.split()
        if len(tokens) < 9 or not all(re.fullmatch(r"\d+,\d", t) for t in tokens[-4:]):
            continue
        first = next((i for i, t in enumerate(tokens) if t[0].isdigit()), None)
        name = key(" ".join(tokens[:first]))
        if first is None or (name not in REGIONS and name != ALL_FOREIGN):
            continue
        got = one_reading(line, tokens[first:-4], total_first=False)
        for c, n in zip(COLUMNS, got[:3]):
            out[c][name] = n
    for c, rows in out.items():
        regions = sum(n for r, n in rows.items() if r != ALL_FOREIGN)
        if ALL_FOREIGN not in rows or regions != rows[ALL_FOREIGN]:
            raise SystemExit(f"comoros_census: {c}'s foreigners by region make {regions:,}, "
                             f"not {rows.get(ALL_FOREIGN)}")
    return out


def speakers(text: str) -> dict[str, dict[str, int]]:
    """{island: {language: residents who speak it}} (Tableau 4), checked."""
    out: dict[str, dict[str, int]] = {c: {} for c in COLUMNS}
    for line in table_lines(text, TABLE4):
        hit = re.fullmatch(r"(?P<name>[^\d ]+) (?P<nums>\d+(?: \d+)*)", line)
        if not hit or key(hit.group("name")) not in LANGUAGES:
            continue
        got = one_reading(line, hit.group("nums").split(), total_first=True)
        for c, n in zip(COLUMNS, got[:3]):
            out[c][LANGUAGES[key(hit.group("name"))]] = n
    missing = [lang for lang in LANGUAGES.values() if any(lang not in out[c] for c in COLUMNS)]
    if missing:
        raise SystemExit(f"comoros_census: Tableau 4 lacks {missing}")
    return out


def compositions(text: str, table: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{island: its nationality and languages spoken, as record fields}."""
    nats, langs = nationalities(text), speakers(text)
    national = table["national"]["total"]
    for lang, want in SPOKEN_SHARES.items():
        got = round(100 * sum(langs[c][lang] for c in COLUMNS) / national, 1)
        if got != want:
            raise SystemExit(f"comoros_census: {lang} comes to {got}% of the country, where "
                             f"the report says {want}%")
    out: dict[str, dict[str, Any]] = {}
    for c in COLUMNS:
        total = table["islands"][c]["total"]
        foreign = nats[c][ALL_FOREIGN]
        regions = sorted(((n, r) for r, n in nats[c].items() if r != ALL_FOREIGN and n),
                         key=lambda x: (-x[0], x[1]))
        listed = joined([f"{n:,} from {REGIONS[r]}" for n, r in regions])
        out[c] = {
            "ethnicity": shares({NATIONALS: total - foreign, FOREIGNERS: foreign}, total=total),
            "ethnicity_year": YEAR, "ethnicity_basis": "nationality",
            "ethnicity_note": (
                f"Nationality, not ethnicity: INSEED's 2017 census report counts each island's "
                f"foreign residents by the region of the world of their nationality (Tableau 3) "
                f"and records no ethnic group, so nationality is shown in its place. Of the "
                f"island's {total:,} residents, {foreign:,} are foreign nationals ({listed}); "
                f"the rest are Comorian nationals. A person with more than one nationality is "
                f"counted under the nationality of origin."),
            "language": shares(langs[c], total=total), "language_year": YEAR,
            "language_basis": LANGUAGE_BASIS,
            "language_note": (
                f"Which languages the island's residents speak, as the 2017 census counted "
                f"them, several answers allowed: each share is the percentage of the island's "
                f"{total:,} residents who speak the language, so the shares add up to more "
                f"than 100 (Tableau 4). The report gives no table of the one language each "
                f"person speaks most."),
        }
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
ISLAND_SOURCES = SOURCES + [{"field": "ethnicity/language", "name": TABLES_SOURCE, "url": URL,
                             "license": LICENCE, "year": YEAR}]
PREFECTURE_SOURCES = SOURCES + [{"field": "language note/ethnicity note", "name": TABLES_SOURCE,
                                 "url": URL, "license": LICENCE, "year": YEAR}]


def fields(rows: list[dict[str, Any]], note: str,
           composition: dict[str, Any] | None = None) -> dict[str, Any]:
    """Count, sex ratio and the stated reasons; an island's compositions where
    given, a prefecture's reasons otherwise."""
    total = sum(r["total"] for r in rows)
    men = sum(r["men"] for r in rows)
    women = sum(r["women"] for r in rows)
    return {"population": measure(total, year=YEAR, source=SOURCE), "population_note": note,
            "sex_ratio": sex_ratio(men, women, year=YEAR, source=SOURCE),
            "median_age": gap(NOT_AVAILABLE, AGE_NOTE),
            "religion": gap(NOT_AVAILABLE, RELIGION_NOTE),
            **(composition or {"language": gap(NOT_AVAILABLE, PREFECTURE_LANGUAGE_NOTE),
                               "ethnicity": gap(NOT_AVAILABLE, PREFECTURE_ETHNICITY_NOTE)})}


def build(table: dict[str, Any], admin1: list[dict[str, Any]],
          admin2: list[dict[str, Any]],
          islands: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
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
                          sources=PREFECTURE_SOURCES,
                          **fields([table["prefectures"][n] for n in names], note)))
    spare = sorted(set(table["prefectures"]) - set(used))
    if spare or len(used) != len(set(used)):
        raise SystemExit(f"comoros_census: prefectures on no polygon or on two: {spare}")
    for k, isl in table["islands"].items():
        shape = next((s for s in admin1 if key(s["name"]) == key(ISLANDS[k])), None)
        if shape is None:
            raise SystemExit(f"comoros_census: the map draws no {ISLANDS[k]}")
        composition = (islands or {}).get(k)
        out.append(record(f"COM-2017-island-{k}", shape["name"], level="admin1", parent="COM",
                          country="COM", match_by="shape_id", shape_id=shape["id"],
                          sources=ISLAND_SOURCES if composition else PREFECTURE_SOURCES,
                          **fields([isl], f"The 2017 census's count for the island of "
                                          f"{ISLAND_NAMES[k]}.", composition)))
    return out


def text_of(blob: bytes) -> tuple[str, str]:
    """The text of the report's last six pages (Tableau A.2) and of the pages
    that hold Tableaux 3 and 4."""
    import pdfplumber                               # noqa: PLC0415
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        last = "\n".join(page.extract_text() or "" for page in pdf.pages[-6:])
        tables = "\n".join(pdf.pages[i].extract_text() or "" for i in TABLE_PAGES
                           if i < len(pdf.pages))
    return last, tables


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    blob, where = fetch(URL, archive=("2024", "2025"), expect=b"%PDF")
    log(f"  read {where}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    last, tables = text_of(blob)
    table = parse(last)
    islands = compositions(tables, table)
    for k, comp in islands.items():
        log(f"  {k}: {[(g['group'], g['pct']) for g in comp['ethnicity']]}, "
            f"{[(g['group'], g['pct']) for g in comp['language']]}")
    records = build(table, units("COM", "admin1"), units("COM", "admin2"), islands)
    for r in records:
        log(f"  {r['level']} {r['name']}: {r['population'].get('value')}, ratio "
            f"{r['sex_ratio'].get('value')}; {r.get('population_note', '')}")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
