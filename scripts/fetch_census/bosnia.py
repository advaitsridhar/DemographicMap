#!/usr/bin/env python3
"""Bosnia and Herzegovina: ethnicity, religion and mother tongue, Popis 2013.

Nothing was recorded for Bosnia's three entities or its ten cantons. The
Agency for Statistics published the 2013 census in books, and Book 2
(*Ethnicity/national affiliation, religion and mother tongue*) is on
``popis.gov.ba`` as workbooks, one per table, in three scripts; the Bosnian
(``BOS``) set is read because its files were the ones measured. Three tables
share one layout and carry every territory this map has a shape for:

    T2  Population by ethnicity/national affiliation and sex
    T5  Population by religion and sex
    T6  Population by mother tongue and sex

Each is ``Level | Area | Sex | Total | <categories...>`` under a bilingual
header (Bosnian row, then an English row that starts "Level"), then three
rows per territory (Total, Male, Female). Level 0 is the country, level 1 the
two entities and Brčko District, level 2 the ten cantons of the Federation.
The Area cell holds the Bosnian name over the English one; the Bosnian name
is what the territory is matched by, since that line is never cut short.

**What the shapes are.** geoBoundaries draws three first-level units -- the
Federation, Republika Srpska, Brčko District -- and twelve second-level ones:
the ten cantons, plus Republika Srpska and Brčko again, because neither is
divided into cantons. So the entity rows are published at both levels and
the canton rows under the Federation. Republika Srpska's own institute
published a different reading of the same count; the figures here are the
Agency's, the ones the state adopted.

**One merge, stated.** The religion table has a column "Islamska" (Islam)
and, apart from it, "Muslimanska" (Muslim), the answer as some people wrote
it. This project's canonical index folds both into Islam, and its guard
refuses a record that lists a group beside its own parent, so the two are
summed here into one "Islam" and the record's note says so. Every other
column is carried as printed, including the ethnonyms some people gave as
their religion ("Bosniak", "Croat", "Bosnian", "Serbian"), which are labelled
"written as religion" so the map does not read them as denominations, and
"Orthodox" given as an ethnicity, labelled the same way in reverse. A row
whose categories do not add to its Total refuses the run.

Usage:
    python -m scripts.fetch_census.bosnia
"""

from __future__ import annotations

import argparse
import io
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, dated, gap, http_get, log, measure, record, shares,
    write_json,
)

OUT = {"admin1": "bosnia_entity.json", "admin2": "bosnia_canton.json"}
YEAR = 2013
BASE = "https://www.popis.gov.ba/popis2013/doc/Knjiga2/BOS/"
TABLES = {"ethnicity": "K2_T2_B.xlsx", "religion": "K2_T5_B.xlsx", "language": "K2_T6_B.xlsx"}
PAGE = "https://www.popis.gov.ba/popis2013/knjige.php?id=2"
SOURCE = ("Agency for Statistics of Bosnia and Herzegovina, Census of Population, "
          "Households and Dwellings 2013, Book 2 (ethnicity, religion, mother tongue)")
LICENCE = "Official statistics publication, Agency for Statistics of Bosnia and Herzegovina"
EXPECTED = {"admin1": 3, "admin2": 12}

# The Bosnian line of the Area cell -> the boundary file's name, and the
# aliases the file uses elsewhere.
ENTITIES = {
    "FEDERACIJA BOSNE I HERCEGOVINE": ("Federation of Bosnia and Herzegovina", []),
    "REPUBLIKA SRPSKA": ("Republika Srpska", []),
    "BRČKO DISTRIKT BOSNE I HERCEGOVINE": ("Brčko District", ["Brcko District"]),
}
CANTONS = {
    "UNSKO-SANSKI KANTON": "Una-Sana Canton",
    "POSAVSKI KANTON": "Posavina Canton",
    "TUZLANSKI KANTON": "Tuzla Canton",
    "ZENIČKO-DOBOJSKI KANTON": "Zenica-Doboj Canton",
    "BOSANSKO-PODRINJSKI KANTON": "Bosnian-Podrinje Canton Goražde",
    "SREDNJOBOSANSKI KANTON": "Central Bosnia Canton",
    "HERCEGOVAČKO-NERETVANSKI KANTON": "Herzegovina-Neretva Canton",
    "ZAPADNOHERCEGOVAČKI KANTON": "West Herzegovina Canton",
    "KANTON SARAJEVO": "Sarajevo Canton",
    "KANTON 10": "Canton 10",
}
FEDERATION = "FEDERACIJA BOSNE I HERCEGOVINE"

# English header label -> the label shown. Anything not listed is shown as
# printed. Adjective forms for peoples, the house style for ethnicity.
LABELS = {
    "ethnicity": {
        "Serb": "Serbian", "Croat": "Croatian", "Turk": "Turkish",
        "Slovenian": "Slovene", "Orthodox": "Orthodox (written as ethnicity)",
        "Others": "Other", "Undeclared": "Not declared",
    },
    "religion": {
        "Islam": "Islam", "Muslim": "Islam",              # summed, see above
        "Bosniak": "Bosniak (written as religion)",
        "Croat": "Croat (written as religion)",
        "Bosnian": "Bosnian (written as religion)",
        "Serbian": "Serbian (written as religion)",
        "Romani": "Romani (written as religion)",
        "Others": "Other", "Undeclared": "Not declared",
    },
    "language": {"Others": "Other", "Undeclared": "Not declared"},
}
NOTES = {
    "religion": ("'Islam' is the bureau's 'Islamska' and 'Muslimanska' columns summed: "
                 "both are Islam and the map cannot list a group beside its parent. "
                 "Ethnonyms given as a religion are kept and marked."),
    "ethnicity": "As printed by the bureau; 'Orthodox' given as an ethnicity is kept and marked.",
    "language": "Mother tongue as printed by the bureau.",
}


def count(cell: Any) -> int:
    if cell is None or cell == "-":
        return 0
    if isinstance(cell, (int, float)):
        return int(cell)
    return int(str(cell).replace(",", "").replace(".", "").strip() or 0)


def parse_table(rows: list[tuple[Any, ...]]) -> tuple[list[str], list[dict[str, Any]]]:
    """(category labels, one dict per territory) from a K2 table's rows.

    The header is the row whose first cell is "Level"; its categories start
    in the fifth column. A territory is a row whose Level is 0, 1 or 2 and
    whose Sex cell begins "Ukupno" (the Total row of its three).
    """
    labels: list[str] | None = None
    units: list[dict[str, Any]] = []
    for row in rows:
        first = str(row[0]).strip() if row and row[0] is not None else ""
        if first == "Level":
            labels = [str(c).replace("\n", " ").strip() for c in row[4:] if c is not None]
            continue
        if labels is None or first not in ("0", "1", "2"):
            continue
        area, sex = str(row[1] or ""), str(row[2] or "")
        if not sex.startswith("Ukupno"):
            continue
        native = area.split("\n")[0].strip().upper()
        counts = {lab: count(c) for lab, c in zip(labels, row[4:])}
        units.append({"level": int(first), "native": native,
                      "english": " ".join(area.split("\n")[1:]).strip(),
                      "total": count(row[3]), "counts": counts})
    if labels is None:
        raise SystemExit("bosnia: no header row starting 'Level'; the table changed shape")
    return labels, units


def bars(field: str, unit: dict[str, Any]) -> Any:
    groups: dict[str, int] = {}
    for label, n in unit["counts"].items():
        shown = LABELS[field].get(label, label)
        groups[shown] = groups.get(shown, 0) + n
    total = unit["total"]
    summed = sum(groups.values())
    if abs(summed - total) > max(0.005 * total, 5):
        raise SystemExit(f"bosnia: {unit['native']} {field} sums to {summed:,} against "
                         f"the total {total:,}")
    return shares({k: v for k, v in groups.items() if v}, total=total) or gap(NOT_AVAILABLE)


def read(field: str) -> dict[str, dict[str, Any]]:
    import openpyxl
    url = BASE + TABLES[field]
    blob = http_get(url, binary=True, timeout=300)
    log(f"  {TABLES[field]} ({field}): {len(blob):,} bytes")
    workbook = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    labels, units = parse_table([tuple(r) for r in sheet.iter_rows(values_only=True)])
    log(f"    {len(labels)} categories: {labels}")
    log(f"    {len(units)} territories: " + ", ".join(u["native"] for u in units))
    return {u["native"]: u for u in units}


def build(tables: dict[str, dict[str, dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Records per level from {field: {native name: unit}}."""
    names = sorted(set().union(*(set(t) for t in tables.values())))
    for field, t in tables.items():
        if sorted(t) != names:
            raise SystemExit(f"bosnia: {field} lists different territories: "
                             f"{sorted(set(names) ^ set(t))}")
    out: dict[str, list[dict[str, Any]]] = {"admin1": [], "admin2": []}
    fed_id = f"BIH-{slug(ENTITIES[FEDERATION][0])}"
    for native in names:
        units = {field: tables[field][native] for field in tables}
        level = next(iter(units.values()))["level"]
        if level == 0:
            continue
        if level == 1 and native in ENTITIES:
            shown, aliases = ENTITIES[native]
            parent, parent_name = "BIH", None
            entity_id = f"BIH-{slug(shown)}"
            levels = ["admin1", "admin2"]           # RS and Brčko are their own admin2
            if native == FEDERATION:
                levels = ["admin1"]
        elif level == 2 and native in CANTONS:
            shown, aliases = CANTONS[native], []
            parent, parent_name = fed_id, ENTITIES[FEDERATION][0]
            entity_id = f"{fed_id}-{slug(shown)}"
            levels = ["admin2"]
        else:
            raise SystemExit(f"bosnia: territory {native!r} (level {level}) is not one "
                             f"this adapter knows; add it to ENTITIES or CANTONS")
        fields = {field: bars(field, unit) for field, unit in units.items()}
        fields.update({f"{field}_year": dated(fields[field], YEAR) for field in units})
        fields.update({f"{field}_note": f"{SOURCE}. {NOTES[field]}" for field in units})
        total = next(iter(units.values()))["total"]
        english = next(iter(units.values()))["english"]
        for lvl in levels:
            rid = entity_id if lvl == "admin1" or level == 2 else f"{entity_id}-as-admin2"
            out[lvl].append(record(
                rid, shown, level=lvl, country="BIH", aliases=aliases + ([english] if english else []),
                parent=(entity_id if lvl == "admin2" and level == 1 else parent),
                parent_name=(shown if lvl == "admin2" and level == 1 else parent_name),
                population=measure(total, year=YEAR, source=SOURCE),
                sources=[{"field": "population/ethnicity/religion/language", "name": SOURCE,
                          "url": PAGE, "license": LICENCE}],
                **fields,
            ))
    return out


def slug(text: str) -> str:
    from common import slugify
    return slugify(text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("bosnia: Popis 2013, Book 2, entities and cantons")
    tables = {field: read(field) for field in TABLES}
    out = build(tables)
    for level, records in out.items():
        log(f"  {level}: {len(records)} records")
        if len(records) != EXPECTED[level]:
            raise SystemExit(f"bosnia: expected {EXPECTED[level]} {level} records, "
                             f"built {len(records)}")
        write_json(PROCESSED / OUT[level], records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
