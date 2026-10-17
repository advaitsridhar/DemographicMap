#!/usr/bin/env python3
"""Equatorial Guinea -- the 2015 census by province and district, as INEGE publishes it.

The Instituto Nacional de Estadística de Guinea Ecuatorial (INEGE) prints the
IV Censo General de Población y Vivienda (IV CGPV, 2015) in its *Anuario
Estadístico de Guinea Ecuatorial 2020*:

* Tabla 20 -- the population of each province at each census (1983, 1994,
  2001, 2015);
* Tabla 21 -- each province's people by sex, nationality and zone, as shares;
* Tabla 23 -- the population of each of the 18 districts, with the shares of
  nationals and foreigners and of urban and rural residents.

INEGE's site answers an automated client with a challenge page, so the copy
the Internet Archive kept in May 2025 is read.

What this writes:

* the seven provinces: the 2015 count, the sex ratio (from the shares of men
  and women, which the yearbook prints to one decimal) and nationality --
  Equatorial Guinean nationals against foreign nationals -- on the ethnicity
  field (``ethnicity_basis`` "nationality"; the census tables publish no
  ethnic group);
* the districts of the provinces whose polygons are exactly their districts
  (Annobón, Bioko Norte, Bioko Sur): the count and nationality;
* every other polygon: why the district's count is not shown on it. The map
  draws the four mainland provinces as 18 polygons against their 13
  districts, the extra ones municipalities drawn apart from the district each
  belongs to, so a polygon named after a district may not be the whole of it.

**Checks**, each of which stops the run: the provinces make the national
total; each province's districts make the province; the shares of men and
women, and of nationals and foreigners, make 100.

Usage:
    python -m scripts.fetch_census.equatorial_guinea_census [--run LABEL]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, write_json

ORIGINAL = "https://inege.org/wp-content/uploads/2019/02/Anuario-Estadi%CC%81stico-de-G.E.-2020.pdf"
URL = "https://web.archive.org/web/20250530165942id_/" + ORIGINAL
YEAR = 2015
OUT = "equatorial_guinea_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
SOURCE = ("Instituto Nacional de Estadística de Guinea Ecuatorial (INEGE), IV Censo General de "
          "Población y Vivienda 2015, as published in the Anuario Estadístico de Guinea "
          "Ecuatorial 2020")
LICENCE = "Official statistics of the Republic of Equatorial Guinea (INEGE), as the Internet Archive keeps it"
NATIONAL = 1_225_377

# The census's provinces and districts (the yearbook's Tabla 3 and Tabla 23).
DISTRICTS: dict[str, tuple[str, ...]] = {
    "Annobón": ("Annobón",),
    "Bioko Norte": ("Malabo", "Baney"),
    "Bioko Sur": ("Luba", "Riaba"),
    "Centro Sur": ("Evinayong", "Niefang", "Acurenam"),
    "Kie Ntem": ("Ebibeyin", "Nsok Nsomo", "Micomiseng"),
    "Litoral": ("Bata", "Mbini", "Cogo"),
    "Wele Nzas": ("Mongomo", "Añisok", "Aconibe", "Nsork"),
}
# The map's spellings of census districts, where they differ by more than accents.
DRAWN_AS = {"ebebiyin": "Ebibeyin", "nsocnsomo": "Nsok Nsomo", "anisoc": "Añisok"}
NUMBER = re.compile(r"^\d{1,3}(?:\.\d{3})*$")
SHARE = re.compile(r"^(?:\d+(?:,\d+)?|-)$")

NATIONALS, FOREIGNERS = "Equatorial Guinean nationals", "Foreign nationals"
SPELLED = {"Kie Ntem": "Kié-Ntem", "Wele Nzas": "Wele-Nzas"}
WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def words(n: int) -> str:
    return WORDS[n] if 0 <= n < len(WORDS) else f"{n:,}"
AGE_GAP = ("INEGE publishes the 2015 census's ages for the whole country only (the yearbook's "
           "population pyramid), not by province or district, so no median age is shown.")
SEX_GAP = ("INEGE publishes the 2015 census's shares of men and women by province, not by "
           "district, so no sex ratio is shown for the district.")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text.lower() if c.isalnum())
    return text.replace("province", "")


def number(token: str) -> int:
    return int(token.replace(".", ""))


def share(token: str) -> float:
    return 0.0 if token == "-" else float(token.replace(",", "."))


def blocks_after(pages: list[str], title: str) -> list[list[str]]:
    """For each place a table's title is printed, the lines from it to the next
    "Fuente" line; the list of tables at the front prints the title too."""
    out = []
    for page in pages:
        lines = page.splitlines()
        for start, line in enumerate(lines):
            if title not in line:
                continue
            block = []
            for nxt in lines[start + 1:]:
                if nxt.strip().startswith("Fuente"):
                    break
                block.append(nxt)
            out.append(block)
    return out


def lines_after(pages: list[str], title: str) -> list[str]:
    """The first block after the title, for printing when nothing adds up."""
    blocks = blocks_after(pages, title)
    return max(blocks, key=len) if blocks else []


def split_row(line: str, kinds: str) -> tuple[str, list[Any]] | None:
    """(name, values) for a line ending in values of the given kinds ('n' a count,
    's' a share), read from the right."""
    tokens = line.split()
    if len(tokens) <= len(kinds):
        return None
    values: list[Any] = []
    for kind, token in zip(reversed(kinds), reversed(tokens)):
        if kind == "n" and NUMBER.match(token):
            values.insert(0, number(token))
        elif kind == "s" and SHARE.match(token):
            values.insert(0, share(token))
        else:
            return None
    name = " ".join(tokens[:len(tokens) - len(kinds)])
    return (name, values) if name and not any(ch.isdigit() for ch in name) else None


def table(blocks: list[list[str]], kinds: str) -> dict[str, list[Any]]:
    """The rows of the block under a title that reads as the table: the most rows."""
    best: dict[str, list[Any]] = {}
    for lines in blocks:
        out: dict[str, list[Any]] = {}
        for line in lines:
            row = split_row(line, kinds)
            if row:
                out.setdefault(fold(row[0]), row[1])
        if len(out) > len(best):
            best = out
    return best


def read(pages: list[str]) -> tuple[dict[str, Any], list[str]]:
    counts = table(blocks_after(pages, "Tabla 20:"), "nnnn")
    shares_ = table(blocks_after(pages, "Tabla 21:"), "ssssss")
    districts = table(blocks_after(pages, "Tabla 23:"), "nsssss")
    problems: list[str] = []
    provinces: dict[str, dict[str, Any]] = {}
    for province, members in DISTRICTS.items():
        key = fold(province)
        if key not in counts or key not in shares_:
            problems.append(f"{province}: not read in Tabla 20 or 21")
            continue
        total = counts[key][-1]
        men, women, nat, foreign = shares_[key][:4]
        if abs(men + women - 100) > 0.11 or abs(nat + foreign - 100) > 0.11:
            problems.append(f"{province}: shares {men} + {women}, {nat} + {foreign}")
        units = {}
        for d in members:
            row = districts.get(fold(d))
            if row is None:
                problems.append(f"{province}: district {d} not read in Tabla 23")
                continue
            if abs(row[2] + row[3] - 100) > 0.11:
                problems.append(f"{d}: nationality shares {row[2]} + {row[3]}")
            units[d] = {"total": row[0], "nationals": row[2], "foreigners": row[3]}
        made = sum(u["total"] for u in units.values())
        if made != total:
            problems.append(f"{province}: districts make {made:,}, the province {total:,}")
        provinces[province] = {"total": total, "men": men, "women": women, "nationals": nat,
                               "foreigners": foreign, "districts": units}
    whole = sum(p["total"] for p in provinces.values())
    if whole != NATIONAL:
        problems.append(f"provinces make {whole:,}, not {NATIONAL:,}")
    national_row = districts.get(fold("Guinea Ecuatorial"))
    if national_row and national_row[0] != NATIONAL:
        problems.append(f"Tabla 23's national line is {national_row[0]:,}")
    return provinces, problems


def nationality(nat: float, foreign: float, where: str) -> dict[str, Any]:
    return {"ethnicity": [{"group": NATIONALS, "pct": nat}, {"group": FOREIGNERS, "pct": foreign}],
            "ethnicity_year": YEAR, "ethnicity_basis": "nationality",
            "ethnicity_note": (f"Nationality, not ethnicity: the 2015 census's published tables "
                               f"give the shares of Equatorial Guinean nationals and of foreign "
                               f"nationals among {where}'s people, and no ethnic group, so "
                               f"nationality is shown in place of ethnicity.")}


def build(provinces: dict[str, Any], admin1: list[dict[str, Any]], admin2: list[dict[str, Any]]
          ) -> tuple[list[dict[str, Any]], list[str]]:
    cite = [{"field": "population/sex_ratio/ethnicity",
             "name": SOURCE + ", Tablas 20, 21 and 23", "url": URL, "year": YEAR,
             "license": LICENCE}]
    first = {fold(u["name"]): u for u in admin1}
    records: list[dict[str, Any]] = []
    report: list[str] = []
    for province, p in provinces.items():
        shown = SPELLED.get(province, province)
        poly = first.get(fold(province))
        if poly is None:
            raise SystemExit(f"equatorial_guinea_census: no first-level polygon for {province}")
        records.append(record(
            f"GNQ-CGPV2015-{poly['id']}", poly["name"], level="admin1", parent="GNQ",
            country="GNQ", match_by="shape_id", shape_id=poly["id"], sources=cite,
            population=measure(p["total"], year=YEAR, source=SOURCE),
            population_note=f"The population of {shown} province at the 2015 census.",
            sex_ratio=measure(round(1000 * p["men"] / p["women"]), unit="males_per_1000_females",
                              year=YEAR, source=SOURCE),
            sex_ratio_note=(f"Men per 1,000 women, from the 2015 census's shares of men "
                            f"({p['men']:.1f}%) and women ({p['women']:.1f}%), which INEGE "
                            f"prints to one decimal place."),
            median_age=gap(NOT_AVAILABLE, AGE_GAP),
            **nationality(p["nationals"], p["foreigners"], f"{shown} province")))
        report.append(f"  {province}: {p['total']:,}; men {p['men']}%; nationals {p['nationals']}%")
        polys = [u for u in admin2 if u["parent"] == poly["id"]]
        named = {}
        for u in polys:
            key = fold(u["name"])
            census = DRAWN_AS.get(key) or next((d for d in p["districts"] if fold(d) == key), None)
            named[u["id"]] = census
        exact = (len(polys) == len(p["districts"])
                 and sorted(n for n in named.values() if n) == sorted(p["districts"]))
        apart = sorted(u["name"].title() for u in polys if not named[u["id"]])
        for u in sorted(polys, key=lambda u: u["name"]):
            census = named[u["id"]]
            sid = u["id"]
            label = u["name"].title()
            if exact:
                d = p["districts"][census]
                sexes: dict[str, Any] = {"sex_ratio": gap(NOT_AVAILABLE, SEX_GAP)}
                if len(p["districts"]) == 1:
                    # The district is the whole province: the province's shares are its own.
                    sexes = {"sex_ratio": measure(round(1000 * p["men"] / p["women"]),
                                                  unit="males_per_1000_females", year=YEAR,
                                                  source=SOURCE),
                             "sex_ratio_note": (f"Men per 1,000 women, from the 2015 census's "
                                                f"shares of men ({p['men']:.1f}%) and women "
                                                f"({p['women']:.1f}%) in {shown} province, of "
                                                f"which {census} district is the whole.")}
                records.append(record(
                    f"GNQ-CGPV2015-{sid}", u["name"], level="admin2", parent="GNQ",
                    country="GNQ", match_by="shape_id", shape_id=sid, sources=cite,
                    population=measure(d["total"], year=YEAR, source=SOURCE),
                    population_note=f"The population of {census} district at the 2015 census.",
                    median_age=gap(NOT_AVAILABLE, AGE_GAP), **sexes,
                    **nationality(d["nationals"], d["foreigners"], f"{census} district")))
                report.append(f"    {u['name']}: {d['total']:,} ({census})")
                continue
            listed = ", ".join(p["districts"])
            if census:
                others = (apart[0] if len(apart) == 1
                          else ", ".join(apart[:-1]) + " and " + apart[-1])
                one = len(apart) == 1
                why = (f"The 2015 census counts {census} district as "
                       f"{p['districts'][census]['total']:,} people. The map draws {shown} as "
                       f"{words(len(polys))} polygons against the census's "
                       f"{words(len(p['districts']))} districts ({listed}): {others} "
                       f"{'is a municipality' if one else 'are municipalities'} drawn apart from "
                       f"the district {'it belongs' if one else 'each belongs'} to, so this "
                       f"polygon may not be the whole of {census} district, and the district's "
                       f"count is not shown on it.")
            else:
                why = (f"The 2015 census publishes counts by district, and {label} is not one: it "
                       f"is a municipality within one of {shown}'s {words(len(p['districts']))} "
                       f"districts ({listed}), whose counts include it, and no count of {label} "
                       f"alone is published.")
            population = {**gap(NOT_AVAILABLE, why), "displaces_before": YEAR}
            records.append(record(
                f"GNQ-CGPV2015-{sid}", u["name"], level="admin2", parent="GNQ", country="GNQ",
                match_by="shape_id", shape_id=sid, sources=cite, population=population,
                sex_ratio=gap(NOT_AVAILABLE, SEX_GAP), median_age=gap(NOT_AVAILABLE, AGE_GAP)))
            report.append(f"    {u['name']}: not shown ({census or 'not a district'})")
    return records, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", help="a label that tells one dispatch from another; not used")
    parser.parse_args()
    import pdfplumber                               # noqa: PLC0415
    blob = http_get(URL, binary=True, cache=False, timeout=600)
    log(f"equatorial_guinea_census: {len(blob):,} bytes, sha256 {hashlib.sha256(blob).hexdigest()}")
    if not blob.startswith(b"%PDF"):
        raise SystemExit("equatorial_guinea_census: the archived copy is not a PDF")
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        pages = [(pdf.pages[i].extract_text() or "") for i in range(55, min(75, len(pdf.pages)))]
    provinces, problems = read(pages)
    for p in problems:
        log(f"  check: {p}")
    if problems:
        for title in ("Tabla 20:", "Tabla 21:", "Tabla 23:"):
            for line in lines_after(pages, title)[:30]:
                log(f"    | {line}")
        raise SystemExit("equatorial_guinea_census: the tables do not add up as read")
    admin1 = json.loads((SITE / "admin1" / "GNQ.units.json").read_text())
    admin2 = json.loads((SITE / "admin2" / "GNQ.units.json").read_text())
    records, report = build(provinces, admin1, admin2)
    for line in report:
        log(line)
    write_json(PROCESSED / OUT, records)
    log(f"  {sum(r['level'] == 'admin1' for r in records)} provinces and "
        f"{sum(r['level'] == 'admin2' for r in records)} district polygons written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
