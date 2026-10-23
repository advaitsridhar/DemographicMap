#!/usr/bin/env python3
"""Sierra Leone -- each district's capital, from English Wikipedia's *Districts of Sierra Leone*.

Statistics Sierra Leone's 2015 census reports speak of the "district
headquarter towns" without naming them (National Analytical Report, pages 56,
62 and 66). English Wikipedia's *Districts of Sierra Leone* lists the sixteen
districts of 2017 with their capitals. The map draws the fourteen of 2015:
Falaba was made out of Koinadugu, and Karene out of Bombali and Port Loko, in
2017, and those three keep the capitals they had (Kabala, Makeni, Port Loko),
which is what the list names for the districts of those names now. The two
new districts are not drawn and give nothing.

Bonthe is left out: the list names Bonthe town, on Sherbro Island, while
Bonthe District Council sits at Mattru Jong on the mainland, so which town is
the district's seat is not certain. Each record cites the revision read, by
its permanent address and its year.

Usage:
    python -m scripts.fetch_census.sierra_leone_capitals
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, log, record, write_json
from .nigeria_capitals import articles, cite

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from probe_wikitable import tables  # noqa: E402

TITLE = "Districts of Sierra Leone"
URL = "https://en.wikipedia.org/wiki/Districts_of_Sierra_Leone"
SOURCE = f"English Wikipedia, {TITLE}"
LICENCE = "CC BY-SA 4.0"
OUT = "sierra_leone_capitals.json"
SITE = PROCESSED.parent.parent / "site" / "data"
# The list's names -> the map's; None: not drawn (made in 2017), or left out.
NAMES = {"Western Rural": "Western Area Rural", "Western Urban": "Western Area Urban",
         "Falaba": None, "Karene": None, "Bonthe": None}
# The drawn districts the 2017 changes cut parts from.
CUT_IN_2017 = {"Bombali": "Karene District was made in 2017 out of parts of it and of Port Loko",
               "Port Loko": "Karene District was made in 2017 out of parts of it and of Bombali",
               "Koinadugu": "Falaba District was made out of part of it in 2017"}


def capitals(wikitext: str) -> dict[str, str]:
    """{district as the list names it: capital}, from its table with both columns."""
    for table in tables(wikitext):
        head = [c.strip().lower() for c in table[0]] if table else []
        if "district" in head and "capital" in head:
            d, c = head.index("district"), head.index("capital")
            return {row[d].strip(): row[c].strip() for row in table[1:]
                    if len(row) > max(d, c) and row[d].strip() and row[c].strip()}
    raise SystemExit(f"sierra_leone_capitals: {TITLE!r} has no table of districts and capitals")


def bind(listed: dict[str, str], admin2: list[dict[str, Any]],
         source: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """One record per drawn district the list gives a capital, citing ``source``
    (the revision read)."""
    source = source or {"field": "capital", "name": SOURCE, "url": URL, "license": LICENCE}
    drawn = {shape["name"]: shape for shape in admin2}
    if len(listed) != 16:
        raise SystemExit(f"sierra_leone_capitals: the list has {len(listed)} districts, not 16")
    records, used = [], set()
    for name, seat in listed.items():
        target = NAMES.get(name, name)
        if target is None:
            continue
        shape = drawn.get(target)
        if shape is None:
            raise SystemExit(f"sierra_leone_capitals: {name!r} is not drawn")
        used.add(target)
        fields: dict[str, Any] = {"capital": seat}
        if target in CUT_IN_2017:
            fields["capital_note"] = (f"{seat} is the district's capital, as it was before "
                                      f"{CUT_IN_2017[target]}.")
        records.append(record(
            f"SLE-SEAT-{shape['id']}", shape["name"], level="admin2", parent="SLE",
            country="SLE", match_by="shape_id", shape_id=shape["id"],
            sources=[dict(source)], **fields))
    left = sorted(set(drawn) - used - {"Bonthe"})
    if left:
        raise SystemExit(f"sierra_leone_capitals: drawn districts with no capital: {left}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="a label that tells one dispatch from another; not used")
    ap.parse_args()
    article = articles([TITLE]).get(TITLE)
    if not article or not article.get("text"):
        raise SystemExit(f"sierra_leone_capitals: {TITLE!r} returned no wikitext")
    listed = capitals(article["text"])
    log(f"sierra_leone_capitals: {TITLE!r}, revision {article['revid']} of "
        f"{article['timestamp']}: {listed}")
    admin2 = json.loads((SITE / "admin2" / "SLE.units.json").read_text())
    records = bind(listed, admin2, cite(article))
    log(f"  {len(records)} district capitals")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
