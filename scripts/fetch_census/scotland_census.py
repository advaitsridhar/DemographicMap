#!/usr/bin/env python3
"""Scotland: religion, ethnicity and language by council area (Census 2011).

The 43 UK shapes this map could not fill were Scotland's 32 council areas and
Northern Ireland's 11 districts, and Scotland was recorded here as blocked: the
2022 census is published through National Records of Scotland' flexible table
builder, and the only file that release links is a bulletin's chart data.

That block stands for **2022**. It does not stand for 2011, whose Key
Statistics were published as ordinary CSVs, one row per council area:

* ``KS209SCb`` religion -- eleven categories, Church of Scotland through
  Religion not stated
* ``KS201SC``  ethnic group
* ``KS206SC``  language

So Scotland is filled from a census fourteen years older than England and
Wales', and the year is stamped on every figure rather than smoothed over. A
reader comparing Glasgow with Manchester is comparing 2011 with 2021, and the
map should say so.

Two things this reader is careful about.

**Ethnicity nests, and the nesting double-counts.** ``KS201SC`` carries six
top-level groups that sum exactly to the population, and eighteen detail
columns beneath them that sum to the same total again -- "White" and "White:
Scottish" are the same people counted twice. The detail is the better answer
because "White" alone tells a reader nothing about a country where the split
between Scottish, Other British, Polish and Irish is the interesting part, so
this reads the **leaves**: a group's detail where it has any, the group itself
where it has none.

**Language asks three different questions**, and only one of them is a
composition. Proficiency in spoken English splits the whole population three
ways; "Can speak Gaelic" and "Can speak Scots" are single counts of an ability,
not shares of anything. What this reads is *language used at home*, whose six
columns sum exactly to the universe -- and that universe is people aged 3 and
over, which is smaller than the population the other two tables use.

Usage:
    python -m scripts.fetch_census.scotland_census
"""

from __future__ import annotations

import argparse
import csv
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, gap, leaves, log, measure, record, shares, write_json,
)

HERE = RAW / "scotland"
OUT = "scotland_council.json"
YEAR = 2011
SOURCE = "Scotland's Census 2011, National Records of Scotland"

# National Records of Scotland writes a council's name one way and the boundary
# file writes it another. Neither is wrong -- "Edinburgh, City of" is how a
# sorted list reads, "Na h-Eileanan Siar" is the Gaelic the council itself uses
# -- so this is a source-side alias rather than a correction, the same shape as
# the Rhondda Cynon Taf declaration in uk_nomis.
COUNCIL_ALIASES = {
    "Edinburgh, City of": "City of Edinburgh",
    "Eilean Siar": "Na h-Eileanan Siar",
}

TABLES = {
    "religion": ("KS209SCb_religion.csv", "All people"),
    "ethnicity": ("KS201SC_ethnicity.csv", "All people"),
    "language": ("KS206SC_language.csv", "All people aged 3 and over"),
}

# Only this block of KS206SC is a composition; the others are a different
# question about the same people.
LANGUAGE_BLOCK = "Language other than English used at home"


def read_table(filename: str) -> tuple[list[str], dict[str, list[str]]]:
    rows = list(csv.reader((HERE / filename).open(encoding="utf-8-sig")))
    header = [h.strip() for h in rows[0]]
    body = {r[0].strip(): r for r in rows[1:] if r and r[0].strip()}
    return header, body


def count(value: str) -> int:
    """NRS writes a suppressed or zero cell as a dash."""
    value = (value or "").strip().replace(",", "")
    return 0 if value in ("", "-") else int(value)


def leaf_columns(header: list[str]) -> list[int]:
    """The data columns that partition the population exactly once.

    The rule is _shared.leaves(); what this adds is the first two columns,
    which are the council's name and its published total rather than a group.
    """
    keep = set(leaves(header[2:]))
    return [i for i, h in enumerate(header) if i > 1 and h.strip() in keep]


def label(header: str) -> str:
    """Read a leaf under the name a person would recognise."""
    if ":" not in header:
        return header.strip()
    parent, detail = (part.strip() for part in header.split(":", 1))
    # "Asian, Asian Scottish or Asian British: Pakistani, Pakistani Scottish or
    # Pakistani British" is one group with a very long name; the detail alone
    # is what the reader wants, and it already carries its own qualifiers.
    return detail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    tables = {field: read_table(name) for field, (name, _) in TABLES.items()}
    councils = [c for c in tables["religion"][1] if c != "Scotland"]
    log(f"scotland_census: {len(councils)} council areas, Census {YEAR}")

    records: list[dict[str, Any]] = []
    for council in councils:
        fields: dict[str, Any] = {}
        population = None
        for field, (header, body) in tables.items():
            row = body.get(council)
            if not row:
                fields[field] = gap(NOT_AVAILABLE)
                continue
            total = count(row[1])
            if field == "religion":
                population = total
            if field == "language":
                cols = [i for i, h in enumerate(header) if h.startswith(LANGUAGE_BLOCK)]
            else:
                cols = leaf_columns(header)
            counts = {label(header[i]): count(row[i]) for i in cols}
            summed = sum(counts.values())
            if total and abs(summed - total) > total * 0.005:
                raise SystemExit(
                    f"scotland_census: {council} {field} sums to {summed:,} "
                    f"against a published {total:,}; the columns chosen are wrong")
            rows = shares(counts, total=total)
            fields[field] = rows or gap(NOT_AVAILABLE)
            fields[f"{field}_note"] = (
                f"{SOURCE}. England and Wales are read from the 2021 census, so a "
                f"comparison across the border spans ten years."
                + (" Of people aged 3 and over." if field == "language" else ""))

        name = COUNCIL_ALIASES.get(council, council)
        records.append(record(
            f"GBR-SCO-{name.replace(' ', '_')}", name, level="admin2", parent="GBR",
            country="GBR",
            population=(measure(population, year=YEAR, source=SOURCE)
                        if population else gap(NOT_AVAILABLE)),
            **fields,
            sources=[{"field": "religion/ethnicity/language", "name": SOURCE,
                      "url": "https://www.scotlandscensus.gov.uk/",
                      "license": "Open Government Licence v3.0"}],
        ))
    log(f"  {len(records)} records")
    write_json(args.out or PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
