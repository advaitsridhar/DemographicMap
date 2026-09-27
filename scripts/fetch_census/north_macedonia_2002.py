#!/usr/bin/env python3
"""North Macedonia: religion and mother tongue for the five municipalities merged
into Kichevo in 2013, from the 2002 census.

The map draws Kichevo, Drugovo, Oslomej, Vraneshtica and Zajas as they were
before 2013. The 2021 census publishes their age, sex and ethnicity by
settlement, which north_macedonia.py regroups onto the five, but religion and
mother tongue for the merged Kichevo only -- a figure that must not be put on
its pre-merger parts. The last census that published those two questions for
the five as they are drawn is 2002's: Book X of its results (State
Statistical Office, 2004) gives the total population by mother tongue (Table 3)
and by religion (Table 4), by sex, for every municipality of the day and each
of its settlements.

The book is a PDF in the YU-ASCII transliteration of its day (Ki~evo for
Kičevo, Vrane{tica for Vraneštica). A municipality's own row is the first row
of its name in each table, before its settlements -- one of which shares the
name. Checks: the categories add to the total, the sexes to the total, and
each municipality's total is the same in the ethnicity, mother-tongue and
religion tables.

Usage:
    python -m scripts.fetch_census.north_macedonia_2002
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any

from ._shared import PROCESSED, http_get, log, record, shares, write_json
from .balkans_common import check_sum, fold, shapes
from .north_macedonia import OLD_KICHEVO, key

OUT = "north_macedonia_2002.json"
YEAR = 2002
URL = "https://www.stat.gov.mk/Publikacii/knigaX.pdf"
PAGE = "https://www.stat.gov.mk/PrikaziPoslednaPublikacija_en.aspx?id=54"
SOURCE = ("State Statistical Office of the Republic of North Macedonia, Census of Population, "
          "Households and Dwellings 2002, Book X, {table}")
LICENCE = "State Statistical Office of the Republic of North Macedonia (reuse with attribution)"
# The boundary file's name -> the book's (YU-ASCII: ~ is č, { is š).
PDF_NAMES = {"Kichevo": "Ki~evo", "Drugovo": "Drugovo", "Oslomej": "Oslomej",
             "Vraneshtica": "Vrane{tica", "Zajas": "Zajas"}
TABLES = {
    "ethnicity": ("Tabela 2.", None),
    "language": ("Tabela 3.", ["Macedonian", "Albanian", "Turkish", "Romani", "Aromanian",
                               "Serbian", "Bosnian", "Other"]),
    "religion": ("Tabela 4.", ["Orthodox", "Islam", "Catholic", "Protestant", "Other religion"]),
}
TITLES = {"language": "Table 3, total population by mother tongue, by sex",
          "religion": "Table 4, total population by declared religion, by sex"}
NOTES = {
    "language": ("Mother tongue, 2002 census, for the municipality as it was before its 2013 "
                 "merger into Kichevo -- the unit the map draws; the 2021 census publishes mother "
                 "tongue for the merged Kichevo only. The book's Vlach is shown as Aromanian, as "
                 "for the rest of the country."),
    "religion": ("Declared religion, 2002 census, for the municipality as it was before its 2013 "
                 "merger into Kichevo -- the unit the map draws; the 2021 census publishes religion "
                 "for the merged Kichevo only. 'Other religion' is the book's 'others', which it "
                 "does not divide."),
}


def number(token: str) -> int:
    return 0 if token == "-" else int(token)


def sections(pages: list[str]) -> dict[str, list[str]]:
    """{field: the lines of its table}, a table running from the first page
    headed with its title to the page before the next table's."""
    starts = []
    for field, (title, _) in TABLES.items():
        first = next((i for i, text in enumerate(pages) if text.lstrip().startswith(title)), None)
        if first is None:
            raise SystemExit(f"north_macedonia_2002: no page headed {title!r}")
        starts.append((first, field))
    starts.sort()
    out = {}
    for n, (first, field) in enumerate(starts):
        last = starts[n + 1][0] if n + 1 < len(starts) else len(pages)
        out[field] = [line for text in pages[first:last] for line in text.splitlines()]
    return out


def municipality_rows(lines: list[str], name: str) -> tuple[list[int], list[int], list[int]]:
    """The municipality's own row and the men's and women's rows after it."""
    pattern = re.compile(rf"^{re.escape(name)} ((?:\d+|-)(?: (?:\d+|-))*) {re.escape(name)}$")
    for i, line in enumerate(lines):
        m = pattern.match(line.strip())
        if m:
            total = [number(t) for t in m.group(1).split()]
            men = [number(t) for t in lines[i + 1].split()[1:-1]]
            women = [number(t) for t in lines[i + 2].split()[1:-1]]
            return total, men, women
    raise SystemExit(f"north_macedonia_2002: no row for {name}")


def build() -> list[dict[str, Any]]:
    import pdfplumber
    blob = http_get(URL, binary=True, timeout=600)
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    log(f"  knigaX.pdf: {len(blob):,} bytes, {len(pages)} pages")
    tables = sections(pages)
    admin2 = {key(s["name"]): s for s in shapes("MKD", "admin2")}
    records = []
    for name in OLD_KICHEVO:
        shape = admin2.get(key(name))
        if shape is None:
            raise SystemExit(f"north_macedonia_2002: no polygon named {name}")
        pdf_name = PDF_NAMES[name]
        whole = municipality_rows(tables["ethnicity"], pdf_name)[0][0]
        fields: dict[str, Any] = {}
        cites = []
        for field in ("language", "religion"):
            labels = TABLES[field][1]
            total, men, women = municipality_rows(tables[field], pdf_name)
            if len(total) != len(labels) + 1:
                raise SystemExit(f"north_macedonia_2002: {name} {field}: {len(total)} numbers "
                                 f"for {len(labels)} categories and a total")
            check_sum(sum(total[1:]), total[0], f"north_macedonia_2002: {field} of {name}")
            check_sum(men[0] + women[0], total[0], f"north_macedonia_2002: {field} sexes of {name}")
            check_sum(total[0], whole, f"north_macedonia_2002: {field} against ethnicity for {name}")
            counts: dict[str, float] = {}
            for label, n in zip(labels, total[1:]):
                counts[label] = counts.get(label, 0) + n
            fields[field] = shares({k: v for k, v in counts.items() if v}, total=total[0])
            fields[f"{field}_year"] = YEAR
            fields[f"{field}_note"] = NOTES[field]
            cites.append({"field": field, "name": SOURCE.format(table=TITLES[field]), "url": URL,
                          "page": PAGE, "year": YEAR, "license": LICENCE})
        records.append(record(f"MKD-2002-{fold(name)}", shape["name"], level="admin2", parent="MKD",
                              country="MKD", match_by="shape_id", shape_id=shape["id"],
                              sources=cites, **fields))
        log(f"  {name}: {whole:,} in 2002; " + "; ".join(
            f"{f} " + ", ".join(f"{r['group']} {r['pct']}" for r in fields[f][:3])
            for f in ("language", "religion")))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    log("north_macedonia_2002: the 2002 census, Book X, for the five pre-2013 municipalities")
    records = build()
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {OUT}: {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
