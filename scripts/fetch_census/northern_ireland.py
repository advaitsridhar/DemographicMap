#!/usr/bin/env python3
"""Northern Ireland: religion, ethnicity and language by district (Census 2021).

The last of the 43 UK shapes this map could not fill. Scotland's 32 council
areas came from the 2011 key statistics; these are Northern Ireland's 11 local
government districts, and unlike Scotland they come from the *current* census.

NISRA publishes the "Ethnicity, Identity, Language and Religion" release as ten
MS-B workbooks. Three of them are read here and seven are not, and which is
which is the whole of the judgement in this file.

**Read.**

* ``MS-B01`` ethnic group -- thirteen categories, White through Other
  ethnicities, flat and summing exactly to all usual residents.
* ``MS-B12`` main language -- eighteen named languages and Other languages,
  of usual residents aged 3 and over.
* ``MS-B20`` religion in intermediate detail -- thirty-two categories,
  Catholic and Presbyterian down through the Christian Fellowship Church, with
  Muslim, Hindu and Buddhist named separately from Other Religions.

**Not read, and why.**

``MS-B05`` knowledge of Irish, ``MS-B08`` knowledge of Ulster-Scots and
``MS-B14`` proficiency in English are not compositions. They count an ability
-- how many people understand, speak, read or write a language -- and a person
can appear in Irish and Ulster-Scots both, or in neither. B05 goes further and
carries a "Some ability in Irish" column beside the four skill columns it is
the sum of, so adding up that sheet reaches 112% of the people in it. Scotland's
KS206SC mixed the same three kinds of question in one table, and the answer is
the same here: main language is the one that partitions its universe. 12.4% of
Northern Ireland aged 3 and over has some ability in Irish and 0.3% give it as
their main language; only the second is a share of anything.

``MS-B19`` religion is the same question as B20 asked at less detail: eight
categories where B20 has thirty-two, and B20's "Other Christian denominations"
already absorbs the residual, so both sum exactly to the same population. There
is no reason to prefer the coarser one. ``MS-B22`` is Northern Ireland's
religion back to 1861 and has no district breakdown at all.

``MS-B23`` and ``MS-B24`` are the one genuinely tempting exclusion. They report
**religion or religion brought up in** -- Northern Ireland's community
background, the figure most quoted about the place -- and they cover the
districts. They are not read because they answer a different question from the
one every other country's religion field answers, and the two answers are far
apart. A person raised Catholic who now has no religion is Catholic in B23 and
No religion in B20, so Belfast is **43.5% Catholic and 21.7% of no religion**
by B20, and **48.7% Catholic and 11.6% of none** by B23. Reading B23 into a
field labelled "religion" would move five points of Belfast into a church and
halve the share of the city that told the census it has no religion, with
nothing to tell a reader comparing Belfast with Birmingham that the questions
differ. The gap is that this map has no community-background field. That is a
gap worth naming rather than papering over with the nearest number.

Usage:
    python -m scripts.fetch_census.northern_ireland
"""

from __future__ import annotations

import argparse
from typing import Any

import openpyxl

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, gap, leaves, log, measure, record, shares, write_json,
)

HERE = RAW / "northern_ireland"
OUT = "northern_ireland_district.json"
YEAR = 2021
SOURCE = "NISRA Census 2021 (Northern Ireland)"
LICENCE = "Open Government Licence v3.0"
URL = "https://www.nisra.gov.uk/publications/census-2021-main-statistics-for-northern-ireland-phase-1"

# Which workbook and worksheet each field is read from. Seven of the release's
# ten files are absent by the reasoning in the module docstring, and the two
# sheet names differ because NISRA gives a table published for four geographies
# a sheet per geography and a table published only for districts a sheet named
# after itself.
TABLES: dict[str, tuple[str, str, str]] = {
    "religion": ("census2021msb20.xlsx", "MS-B20", "All usual residents"),
    "ethnicity": ("census2021msb01.xlsx", "LGD", "All usual residents"),
    "language": ("census2021msb12.xlsx", "LGD", "All usual residents aged 3 and over"),
}

# Every one of the eleven district names NISRA writes is the name geoBoundaries
# draws, so unlike Scotland's councils this needs no aliases. Kept as a
# measured fact rather than an assumption: the test suite joins the names.
DISTRICT_CODES = "N09"

# B20 writes its categories as "Christian: Baptist" and "Other Religions:
# Muslim", and the detail alone is what a reader wants and what the canonical
# index can fold -- "Christian: Catholic" matches nothing, "Catholic" is
# Christianity. One label cannot survive losing its parent, because on its own
# it does not say which religion it is non-denominational within, so it is
# spelled out rather than left to fold into nothing.
DETAIL_RENAMES = {
    "Non Denominational": "Non-denominational Christian",
}


def read_counts(filename: str, sheet: str) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """The count half of one MS-B worksheet, by district.

    Each sheet holds two tables one above the other: MS-Bxxa counts, then
    MS-Bxxb the same figures as percentages of the area. Reading past the
    boundary would give every district twice, the second time with values
    between 0 and 1, so this stops at the first blank row after the header.

    B20 also carries a Northern Ireland row above the districts, which the
    others do not. Districts are taken by their N09 code rather than by
    position, so a whole-country row is skipped wherever it appears.
    """
    workbook = openpyxl.load_workbook(HERE / filename, read_only=True, data_only=True)
    rows = list(workbook[sheet].iter_rows(values_only=True))
    workbook.close()

    start = next(i for i, row in enumerate(rows) if row and row[0] == "Geography")
    # NISRA breaks a long column heading across lines and marks some with a
    # footnote; both are display, not identity.
    header = [" ".join(str(cell).split()) if cell is not None else ""
              for cell in rows[start]]
    header = [h.split(" [note")[0].strip() for h in header]

    out: dict[str, dict[str, Any]] = {}
    for row in rows[start + 1:]:
        if not row or row[0] is None:
            break
        code = str(row[1] or "")
        if not code.startswith(DISTRICT_CODES):
            continue
        out[str(row[0]).strip()] = {
            "code": code,
            "total": row[2],
            "counts": {header[i]: row[i] for i in range(3, len(header))
                       if isinstance(row[i], (int, float))},
        }
    return header, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    tables = {field: read_counts(filename, sheet)[1]
              for field, (filename, sheet, _) in TABLES.items()}
    districts = sorted(tables["religion"])
    log(f"northern_ireland: {len(districts)} local government districts, Census {YEAR}")

    records: list[dict[str, Any]] = []
    for district in districts:
        fields: dict[str, Any] = {}
        population = None
        for field, (filename, _, universe) in TABLES.items():
            entry = tables[field].get(district)
            if not entry:
                fields[field] = gap(NOT_AVAILABLE)
                continue
            counts = {detail(label): entry["counts"][label]
                      for label in leaves(entry["counts"])}
            total = entry["total"]
            summed = sum(counts.values())
            if total and abs(summed - total) > total * 0.005:
                raise SystemExit(
                    f"northern_ireland: {district} {field} sums to {summed:,.0f} "
                    f"against a published {total:,.0f}; the columns chosen are wrong")
            if field == "religion":
                # Each MS-B table is disclosure-controlled on its own, so the
                # three "All usual residents" totals disagree by a handful of
                # people. Population comes from one named table rather than
                # whichever field happened to be read last.
                population = int(total)
            fields[field] = shares(counts, total=total) or gap(NOT_AVAILABLE)
            fields[f"{field}_note"] = note(field, universe, filename)

        records.append(record(
            f"GBR-{tables['religion'][district]['code']}", district,
            level="admin2", parent="GBR", country="GBR",
            codes={"nisra_code": tables["religion"][district]["code"]},
            population=(measure(population, year=YEAR, source=SOURCE)
                        if population else gap(NOT_AVAILABLE)),
            **fields,
            sources=[{"field": "religion/ethnicity/language", "name": SOURCE,
                      "url": URL, "license": LICENCE}],
        ))
    log(f"  {len(records)} records")
    write_json(args.out or PROCESSED / OUT, records)
    return 0


def detail(label: str) -> str:
    """A category under the name a person would recognise.

    Read after leaves(), never before: the colon is what tells a parent from
    its child, so stripping it first would leave the two indistinguishable.
    """
    if ":" in label:
        label = label.split(":", 1)[1].strip()
    return DETAIL_RENAMES.get(label, label)


def note(field: str, universe: str, filename: str) -> str:
    table = filename.replace("census2021msb", "MS-B").replace(".xlsx", "")
    text = f"{SOURCE}, {table}. Of {universe.lower()}."
    if field == "religion":
        # Said in full because Northern Ireland's most-quoted religion figure is
        # the other one, and a reader who knows that number will otherwise think
        # this table is wrong.
        text += (" The religion a person holds, not the wider 'religion or "
                 "religion brought up in' NISRA also publishes: someone raised "
                 "Catholic who now has none is counted under No religion here.")
    if field == "language":
        text += " Main language, not knowledge of Irish or Ulster-Scots."
    return text


if __name__ == "__main__":
    raise SystemExit(main())
