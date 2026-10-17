#!/usr/bin/env python3
"""Algeria -- the 2008 census by wilaya: people, median age, sex ratio.

The Office National des Statistiques took the fifth Recensement Général de la
Population et de l'Habitat on 16-30 April 2008 and published its results by
wilaya and commune in its *Collections* series. One table gives the resident
population of every wilaya by five-year age group and sex
(``collections/pop3_national.pdf``: "Population résidente par âge, par sexe et
par wilaya", eight pages, two wilayas side by side). Read here for each of
the 48 wilayas: the count, the median age interpolated within the five-year
group holding the middle person (people whose age was not declared, "ND",
left out of it), and men per 1,000 women.

The office's host sends its certificate without the intermediate above it;
the missing link is fetched from the certificate's own Authority Information
Access address and the chain verified in full (``common.http_get(aia=True)``).
Where that fails, the Internet Archive's capture of the same file is read.

**Checks before anything is written.** Every wilaya's age groups and ND make
its total and its men and women make it too; the 48 wilayas make the national
total the office prints in ``pop4_national.pdf``, 34,080,030; every wilaya is
bound to one polygon, by its code (the map's ISO 3166-2 code is the office's
wilaya number) or, where the map gives none, by name.

The map's second level draws the 48 wilayas a second time, out of register
with the first, so nothing is written there.

Usage:
    python -m scripts.fetch_census.algeria_census
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
from typing import Any

from ._shared import PROCESSED, http_get, log, measure, record, write_json

URL = "https://www.ons.dz/collections/pop3_national.pdf"
ARCHIVED = "https://web.archive.org/web/20111113180443id_/http://www.ons.dz/collections/pop3_national.pdf"
LANDING = "https://www.ons.dz/collections/population.html"
SOURCE = ("Office National des Statistiques (ONS), Recensement Général de la Population et de "
          "l'Habitat 2008, population résidente par âge, par sexe et par wilaya")
LICENCE = "ONS publication (reuse with attribution)"
YEAR = 2008
NATIONAL = 34_080_030
OUT = "algeria_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
# Wilayas the map labels without an ISO 3166-2 code: the office's number ->
# the map's label.
UNCODED = {42: "Tipaza"}
# How far a row's men and women may miss its printed total: the office rounds
# each cell on its own (Chlef's 20-24 row prints 61,818 men, 62,127 women and
# 123,946 in all).
SLACK = 2
HEADER = re.compile(r"([A-Za-zÀ-ÿ'’. -]+?)\s*\(\s*(\d{1,2})\s*\)")
ROW = re.compile(r"(?i)(\d{1,2}\s*-\s*\d{1,2}\s*ans|85\s*ans\s*&\s*\+|ND|Total)"
                 r"\s+(\d[\d ]*?\d|\d)\s+(\d[\d ]*?\d|\d)\s+(\d[\d ]*?\d|\d)(?=\s|$)")


def fold(text: Any) -> str:
    stripped = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in stripped.lower() if c.isalnum() and not unicodedata.combining(c))


def count(text: str) -> int:
    return int(re.sub(r"\s", "", text))


def label_bounds(label: str) -> tuple[int, int | None] | str:
    low = label.lower().replace(" ", "")
    if low in ("nd", "total"):
        return low
    if low.startswith("85"):
        return (85, None)
    m = re.match(r"(\d+)-(\d+)ans", low)
    if not m:
        raise SystemExit(f"algeria_census: an age group reads {label!r}")
    return int(m.group(1)), int(m.group(2))


def parse(pages: list[str]) -> dict[int, dict[str, Any]]:
    """{wilaya number: {"name", "groups": [(lo, hi, total)], "nd", "men", "women", "total"}}.

    Each page holds blocks of two wilayas side by side: a line naming both
    ("Adrar  (1)  Chlef  (2)"), then a row per age group carrying both
    wilayas' men, women and total."""
    out: dict[int, dict[str, Any]] = {}
    current: list[int] = []
    for page in pages:
        for line in page.splitlines():
            heads = HEADER.findall(line)
            if heads and not ROW.search(line):
                current = []
                for name, code in heads:
                    number = int(code)
                    if number in out:
                        raise SystemExit(f"algeria_census: wilaya {number} printed twice")
                    out[number] = {"name": name.strip(), "groups": [], "nd": None,
                                   "men": None, "women": None, "total": None}
                    current.append(number)
                continue
            cells = ROW.findall(line)
            if not cells or not current:
                continue
            if len(cells) != len(current):
                raise SystemExit(f"algeria_census: a row carries {len(cells)} wilayas where "
                                 f"the block names {len(current)}: {line!r}")
            for number, (label, men, women, total) in zip(current, cells):
                unit = out[number]
                m, f, t = count(men), count(women), count(total)
                # The office's cells are rounded one by one: a row's sexes
                # can miss its total by a person or two, never by more.
                if abs(m + f - t) > SLACK:
                    raise SystemExit(f"algeria_census: {unit['name']} {label}: {m:,} men and "
                                     f"{f:,} women do not make {t:,}")
                if m + f != t:
                    unit.setdefault("rounding", []).append(f"{label} {m + f - t:+d}")
                kind = label_bounds(label)
                if kind == "nd":
                    unit["nd"] = t
                elif kind == "total":
                    unit.update(men=m, women=f, total=t)
                else:
                    unit["groups"].append((kind[0], kind[1], t))
    return out


def check(table: dict[int, dict[str, Any]]) -> None:
    if sorted(table) != list(range(1, 49)):
        raise SystemExit(f"algeria_census: the table holds wilayas {sorted(table)}, not 1-48")
    for number, unit in table.items():
        groups = unit["groups"]
        edge = 0
        for low, high, _ in groups:
            if low != edge:
                raise SystemExit(f"algeria_census: {unit['name']}'s age groups break at {low}")
            edge = high + 1 if high is not None else None
        if not groups or groups[-1][1] is not None:
            raise SystemExit(f"algeria_census: {unit['name']} has no open-ended last group")
        made = sum(n for _, _, n in groups) + (unit["nd"] or 0)
        if unit["total"] is None or abs(made - unit["total"]) > SLACK * (len(groups) + 1):
            raise SystemExit(f"algeria_census: {unit['name']}'s groups make {made:,}, not "
                             f"{unit['total']}")
        if made != unit["total"] or unit.get("rounding"):
            log(f"  {unit['name']}: rounding in the office's cells: groups make {made:,} "
                f"against {unit['total']:,}; rows {unit.get('rounding', [])}")
    whole = sum(u["total"] for u in table.values())
    if whole != NATIONAL:
        raise SystemExit(f"algeria_census: the wilayas make {whole:,}, not {NATIONAL:,}")


def grouped_median(groups: list[tuple[int, int | None, int]]) -> float | None:
    base = sum(n for _, _, n in groups)
    half, before = base / 2, 0
    for low, high, people in groups:
        if before + people >= half:
            if high is None or people <= 0:
                return None
            return round(low + (half - before) / people * (high - low + 1), 1)
        before += people
    return None


def bind(table: dict[int, dict[str, Any]], admin1: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    by_code: dict[int, dict[str, Any]] = {}
    for shape in admin1:
        code = str(shape.get("iso_3166_2") or "")
        if m := re.fullmatch(r"DZ-(\d{2})", code):
            if int(m.group(1)) in by_code:
                raise SystemExit(f"algeria_census: two polygons carry {code}")
            by_code[int(m.group(1))] = shape
    labels = {fold(s["name"]): s for s in admin1}
    for number, label in UNCODED.items():
        if number not in by_code and fold(label) in labels:
            by_code[number] = labels[fold(label)]
    missing = [f"{table[n]['name']} ({n})" for n in table if n not in by_code]
    if missing:
        raise SystemExit(f"algeria_census: no polygon for {missing}")
    if len({s["id"] for s in by_code.values()}) != len(table):
        raise SystemExit("algeria_census: two wilayas on one polygon")
    for number, shape in by_code.items():
        ours, theirs = fold(shape["name"]), fold(table[number]["name"])
        if ours[:3] != theirs[:3]:
            log(f"  wilaya {number}: the office's {table[number]['name']!r} on the map's "
                f"{shape['name']!r}")
    return by_code


def build(table: dict[int, dict[str, Any]], admin1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bound = bind(table, admin1)
    records = []
    for number, unit in sorted(table.items()):
        shape = bound[number]
        median = grouped_median(unit["groups"])
        unstated = (f" The age of {unit['nd']:,} people was not declared; they are left out "
                    "of the median." if unit["nd"] else "")
        records.append(record(
            f"DZA-RGPH2008-{number:02d}", shape["name"], level="admin1", parent="DZA",
            country="DZA", match_by="shape_id", shape_id=shape["id"],
            population=measure(unit["total"], year=YEAR, source=SOURCE),
            population_note=(f"The resident population of the wilaya of {unit['name']} at the "
                             f"2008 census, in ordinary and collective households: "
                             f"{unit['men']:,} men and {unit['women']:,} women."),
            median_age=measure(median, unit="years", year=YEAR, source=SOURCE)
            if median is not None else None,
            median_age_note=("Interpolated within the five-year age group that holds the "
                             "middle person, from the 2008 census's count of residents by "
                             f"five-year age group.{unstated}"),
            sex_ratio=measure(round(1000 * unit["men"] / unit["women"]),
                              unit="males_per_1000_females", year=YEAR, source=SOURCE),
            codes={"ons": f"{number:02d}"},
            sources=[{"field": "population/median_age/sex_ratio", "name": SOURCE,
                      "url": LANDING, "year": YEAR, "license": LICENCE}]))
    return records


def fetch() -> tuple[bytes, str]:
    try:
        blob = http_get(URL, binary=True, cache=False, timeout=180, aia=True)
        if blob[:4] == b"%PDF":
            return blob, URL
        log(f"  {URL} answered {blob[:60]!r}; reading the archived copy")
    except Exception as err:                         # noqa: BLE001 -- reported, then the copy
        log(f"  {URL}: {type(err).__name__}: {err}; reading the archived copy")
    blob = http_get(ARCHIVED, binary=True, cache=False, timeout=180)
    if blob[:4] != b"%PDF":
        raise SystemExit(f"algeria_census: neither the office's file nor the archive's copy is a PDF")
    return blob, ARCHIVED


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    import pdfplumber                               # noqa: PLC0415
    blob, via = fetch()
    log(f"  read {via}: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    table = parse(pages)
    check(table)
    for number, unit in sorted(table.items()):
        log(f"  {number:2d} {unit['name']:22} {unit['total']:>10,}  median "
            f"{grouped_median(unit['groups'])}  men/1000 women "
            f"{round(1000 * unit['men'] / unit['women'])}  ND {unit['nd']}")
    admin1 = json.loads((SITE / "admin1" / "DZA.units.json").read_text())
    records = build(table, admin1)
    log(f"  48 wilayas making {NATIONAL:,}; {len(records)} records")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
