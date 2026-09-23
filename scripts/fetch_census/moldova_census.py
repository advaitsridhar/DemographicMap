#!/usr/bin/env python3
"""Moldova: religion and mother tongue by district, from the 2024 census's own tables.

The National Bureau of Statistics published the final results of the 2024
Population and Housing Census on ethnocultural characteristics on 20 October
2025, with an annex workbook of tables
(``Anexa_Caracteristici_Etnoculturale_RPL2024.xlsx``, 42 sheets). Two of them
are what this reads, one row per district, municipality and the autonomous
unit of Gagauzia -- the 35 units the census counted:

* 5.29, the population by declared religious affiliation, in persons;
* 5.13, the population by declared mother tongue, in persons.

Until this, Moldova's religion came from the districts' English Wikipedia
articles, which transcribe these same tables as bulleted lists. Two units had
no list -- Balti's article has no religion section, and Briceni's gives 2004
shares beside 2014 counts with the shares left out -- and the lists that were
there carry their editors' slips: Anenii Noi's "Christians" is not the sum of
the lines under it, Dubasari's Orthodox share is "98.%". Read from the table
itself, every unit is the census's own count, and the lists' "Protestant"
comes apart into the Baptists, Pentecostals, Adventists and evangelicals the
census asked about. Language had been read for seven units; the same annex
has it for all 35.

**Layout.** Each sheet has a header of two or three rows over the columns --
the field's name spanning the categories, the categories beneath it, and for
mother tongue a third row splitting "Moldovan or Romanian" into its two
answers -- then a row of column letters (A, B, 1, 2, ...), the national
total, and each development region's row followed by its units. A column's
category is the lowest header cell it has. A column whose category is
"Total" is a sum of others -- the unit's own total, and mother tongue's
"Moldovan or Romanian" -- and is not read as a group; the unit's total is
kept to check the groups against. A unit is a row with a statistical code;
the country and the regions have none. A dash is a zero.

The categories are named in the header rather than declared here, so a
category the bureau adds stops the run with its name rather than vanishing.
Every row's groups must add to its total.

**Bender and Transnistria** are not in these tables: the census was not taken
on the left bank. They keep what moldova_gaps.py reads for them.

Usage:
    python -m scripts.fetch_census.moldova_census
"""

from __future__ import annotations

import argparse
import io
import re
import unicodedata
from pathlib import Path
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, dated, gap, http_get, log, read_json, record, shares, write_json

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = "moldova_census.json"
URL = ("https://statistica.gov.md/files/files/ComPresa/Recensamant/2024/Ro/"
       "Anexa_Caracteristici_Etnoculturale_RPL2024.xlsx")
PAGE = ("https://statistica.gov.md/ro/rezultatele-finale-ale-recensamantului-"
        "populatiei-si-locuintelor-2024-caracteris-10121_62043.html")
SOURCE = ("Biroul Național de Statistică, Recensământul Populației și Locuințelor 2024, "
          "final results: ethnocultural characteristics, annex table {table}")
LICENCE = "Official statistics of the Republic of Moldova (reuse with attribution)"
YEAR = 2024
SHEETS = {"religion": "5.29", "language": "5.13"}
UNITS = 35

# The header's categories, folded, to the names the map already uses for
# Moldova. Matched on the start of the folded label, because the bureau
# writes some at length ("Staroveri (Ortodoxă de rit vechi)") and footnotes
# others with a superscript.
LABELS: dict[str, dict[str, str]] = {
    "religion": {
        "ortodox": "Orthodox",
        "baptist": "Baptist",
        "martorii lui iehova": "Jehovah's Witnesses",
        "penticostal": "Pentecostal",
        "adventist": "Adventist",
        "crestina dupa evanghelie": "Evangelical",
        "staroveri": "Old Believer",
        "islam": "Islam",
        "catolic": "Catholic",
        "alte religii": "Other religion",
        "liber cugetator": "Freethinker",
        "agnostic": "Agnosticism",
        "ateu": "Atheism",
        # Beside agnostics, atheists and freethinkers in the same table, so a
        # fourth answer and not the category the other three sit in -- the
        # name the Europe reader gives the same census answer.
        "fara religie": "Irreligious",
        "nu au declarat": "Not declared",
    },
    "language": {
        "moldoveneasca": "Moldovan",
        "romana": "Romanian",
        "ucraineana": "Ukrainian",
        "rusa": "Russian",
        "gagauza": "Gagauz",
        "bulgara": "Bulgarian",
        "romani": "Romani",
        "alta limba": "Other",
        "nu au declarat": "Not declared",
    },
}

NOTES = {
    "religion": ("Declared religious affiliation, 2024 Population and Housing Census, "
                 "usual residents, free declaration; people who declared none are their "
                 "own group. The census's own table (annex 5.29), in persons; shares "
                 "computed from its counts."),
    "language": ("Declared mother tongue, 2024 Population and Housing Census, usual "
                 "residents, free declaration. Moldovan and Romanian are the two answers "
                 "people gave, counted apart as the census counts them. The census's own "
                 "table (annex 5.13), in persons; shares computed from its counts."),
}


def fold(text: Any) -> str:
    """Lower case, no diacritics, no footnote marks, single spaces."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z ]+", " ", text).split())


def count(cell: Any) -> int:
    """A cell's persons: a number, or the bureau's dash for a zero."""
    if cell is None or (isinstance(cell, str) and cell.strip() in ("-", "–", "")):
        return 0
    if isinstance(cell, (int, float)):
        return int(cell)
    digits = re.sub(r"[\s .,]", "", str(cell))
    if not digits.isdigit():
        raise ValueError(f"not a count: {cell!r}")
    return int(digits)


def columns(rows: list[tuple[Any, ...]]) -> tuple[int, int, dict[int, str], int]:
    """(the first row of data, the code's column, {column: category}, the total's column).

    The header starts at the row holding "Cod statistic" and ends at the row
    of column letters beneath it, A under the code and B under the name. The
    code is not in the sheet's first column: the workbook leaves column A
    empty, so everything is found from where "Cod statistic" is.
    """
    top = code = None
    for i, r in enumerate(rows):
        hit = next((j for j, c in enumerate(r or ()) if fold(c).startswith("cod statistic")), None)
        if hit is not None:
            top, code = i, hit
            break
    if top is None or code is None:
        raise SystemExit("moldova_census: no header row holding 'Cod statistic'")

    def cell(r: tuple[Any, ...], j: int) -> str:
        return str(r[j]).strip() if j < len(r) and r[j] is not None else ""
    letters = next((i for i in range(top + 1, len(rows))
                    if cell(rows[i], code) == "A" and cell(rows[i], code + 1) == "B"), None)
    if letters is None:
        raise SystemExit("moldova_census: no row of column letters under the header")
    width = max(len(r) for r in rows[top:letters])
    labels: dict[int, str] = {}
    for j in range(code + 2, width):
        cells = [rows[i][j] for i in range(top, letters)
                 if j < len(rows[i]) and rows[i][j] not in (None, "")]
        if cells:
            labels[j] = str(cells[-1]).strip()
    totals = [j for j, label in labels.items() if fold(label) == "total"]
    if not totals or totals[0] != min(labels):
        raise SystemExit(f"moldova_census: the first column read is not the total: {labels}")
    total = totals[0]
    return letters + 1, code, {j: s for j, s in labels.items() if j not in totals}, total


def named(field: str, label: str) -> str:
    folded = fold(label)
    for key, name in LABELS[field].items():
        if folded.startswith(key):
            return name
    raise SystemExit(f"moldova_census: {field} category {label!r} has no entry in LABELS")


def units(field: str, rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    """Every row with a statistical code: the unit, its total and its groups."""
    first, at, labels, total_col = columns(rows)
    out = []
    for row in rows[first:]:
        code = str(row[at] or "").strip() if len(row) > at else ""
        if not re.fullmatch(r"\d{6,7}", code):
            continue
        name = str(row[at + 1] or "").strip()
        total = count(row[total_col])
        groups: dict[str, int] = {}
        for j, label in labels.items():
            n = count(row[j] if j < len(row) else None)
            key = named(field, label)
            groups[key] = groups.get(key, 0) + n
        if sum(groups.values()) != total:
            raise SystemExit(f"moldova_census: {field}, {name}: the groups add to "
                             f"{sum(groups.values()):,} against the total {total:,}")
        out.append({"code": code, "name": name, "total": total, "groups": groups})
    return out


# The workbook writes s and t with a cedilla (ş, ţ), the legacy encoding, and
# prefixes the municipalities and the autonomous unit with their status. A
# row bound to a shape names it, so these would become the map's labels:
# "Mun. Chişinău", "UTA Găgăuzia". The map shows the name, in Romanian's own
# letters, and Gagauzia as English writes it.
CEDILLA = str.maketrans("şţŞŢ", "șțȘȚ")
SHOWN = {"Găgăuzia": "Gagauzia"}


def display(name: str) -> str:
    name = re.sub(r"^(Mun\.|UTA)\s+", "", name.strip()).translate(CEDILLA)
    return SHOWN.get(name, name)


def key(name: str) -> str:
    """A unit's name as the boundary file and the workbook can both be folded to."""
    folded = fold(name)
    folded = re.sub(r"^(mun|uta|raionul|r)\s+", "", folded)
    return folded.replace(" ", "")


def shapes() -> dict[str, dict[str, str]]:
    """{level: {folded name: shape id}} for Moldova's polygons."""
    out: dict[str, dict[str, str]] = {}
    for level in ("admin1", "admin2"):
        out[level] = {key(u["name"]): u["id"]
                      for u in read_json(ROOT / "site" / "data" / level / "MDA.json", [])}
    return out


def build(workbook: Any, drawn: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    read = {field: {u["code"]: u for u in units(field, [tuple(r) for r in
                                                         workbook[sheet].iter_rows(values_only=True)])}
            for field, sheet in SHEETS.items()}
    codes = list(read["religion"])
    if sorted(codes) != sorted(read["language"]) or len(codes) != UNITS:
        raise SystemExit(f"moldova_census: expected the same {UNITS} units in both tables, "
                         f"read {len(codes)} and {len(read['language'])}")
    records = []
    for code in codes:
        unit = read["religion"][code]
        fields: dict[str, Any] = {}
        for field in SHEETS:
            row = read[field][code]
            if row["total"] != unit["total"]:
                raise SystemExit(f"moldova_census: {unit['name']} counts {row['total']:,} "
                                 f"for {field} and {unit['total']:,} for religion")
            value = shares({g: n for g, n in row["groups"].items() if n},
                           total=row["total"]) or gap(NOT_AVAILABLE)
            fields[field] = value
            fields[f"{field}_year"] = dated(value, YEAR)
            fields[f"{field}_note"] = NOTES[field]
        k = key(unit["name"])
        for level in ("admin1", "admin2"):
            shape = drawn.get(level, {}).get(k)
            if not shape:
                raise SystemExit(f"moldova_census: {unit['name']!r} is not a {level} shape")
            records.append(record(
                f"MDA-census-{level}-{k}", display(unit["name"]), level=level, parent="MDA",
                country="MDA", shape_id=shape, match_by="shape_id",
                sources=[{"field": field,
                          "name": SOURCE.format(table=SHEETS[field]),
                          "url": URL, "page": PAGE, "year": YEAR, "license": LICENCE}
                         for field in SHEETS],
                **fields))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    import openpyxl
    log("moldova_census: 2024 census, ethnocultural annex")
    blob = http_get(URL, binary=True, timeout=600)
    log(f"  {len(blob):,} bytes")
    workbook = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    records = build(workbook, shapes())
    for r in records:
        if r["level"] == "admin1" and r["name"] in ("Bălți", "Briceni"):
            top = ", ".join(f"{g['group']} {g['pct']}" for g in r["religion"][:4])
            log(f"  {r['name']}: religion {top}")
    log(f"  {len(records)} records, {len(records) // 2} units at two levels")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
