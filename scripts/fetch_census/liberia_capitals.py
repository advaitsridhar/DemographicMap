#!/usr/bin/env python3
"""Liberia -- district seats, from English Wikipedia's article on each district.

LISGIS's 2022 census results name no district seats, Wikidata names none
for the 136 districts the map draws, and English Wikipedia's list of
Liberia's districts gives their populations and no seats. A few of the
districts' own articles name one: "The administrative seat of the District
is Ziah Town" (Konobo), "Bensonville is the capital" (Careysburg). This
reads the article on each district, through its Wikidata item or the title
in ``TITLES``, with nigeria_capitals' reader, and writes the seat where the
article names one, or the reason, citing the revision read. An article that
only says a county's capital lies in the district ("Robertsport, the capital
city of Grand Cape Mount County, is located in the district") names no seat
for the district.

Usage:
    python -m scripts.fetch_census.liberia_capitals
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import PROCESSED, log, write_json
from .liberia_census import FINAL, FINAL_CAPTURE, LICENCE, PUBLISHER
from .nigeria_capitals import bind, cite, read_units, unseated

OUT = "liberia_capitals.json"
SRC_FINAL = f"{PUBLISHER}, 2022 Population and Housing Census, Final Results"
# (county, polygon) -> the English article on the district.
TITLES: dict[tuple[str, str], str] = {}


def why(p: dict[str, Any], a: dict[str, Any] | None, quiet: bool
        ) -> tuple[str, list[dict[str, Any]]]:
    census = {"field": "capital", "name": SRC_FINAL, "url": FINAL, "archived": FINAL_CAPTURE,
              "license": LICENCE, "year": 2022}
    if a is not None:
        return (f"English Wikipedia's article on {a['title']} names no seat for the district, "
                "and LISGIS's 2022 census results name none.", [cite(a), census])
    return ("English Wikipedia has no article on this district, and LISGIS's 2022 census "
            "results name no district seats.", [census])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="a label that tells one dispatch from another; not used")
    ap.parse_args()
    polys = unseated("LBR")
    items, got = read_units(polys, TITLES)
    records, said = bind("LBR", polys, items, got, why)
    for line in said:
        log(f"  {line}")
    seated = sum(1 for r in records if isinstance(r["capital"], str))
    log(f"liberia_capitals: {len(polys)} districts without a seat on the map; {seated} seats "
        f"written, {len(records) - seated} reasons")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
