#!/usr/bin/env python3
"""Liberia -- district seats, from English Wikipedia's article on each district.

LISGIS's 2022 census results name no district seats, Wikidata names none
for the 136 districts the map draws, and English Wikipedia's list of
Liberia's districts gives their populations and no seats. A few of the
districts' own articles name one: "The administrative seat of the District
is Ziah Town" (Konobo), "Bensonville is the capital" (Careysburg),
"Gbehlay-Geh District is headquartered in Karnplay City". This reads the
article on each district, through its Wikidata item or the title in
``TITLES``, with nigeria_capitals' reader, and writes the seat where the
article names one, or the reason, citing the revision read. An article that
only says a county's capital lies in the district ("Robertsport, the capital
city of Grand Cape Mount County, is located in the district") names no seat
for the district.

Usage:
    python -m scripts.fetch_census.liberia_capitals
"""

from __future__ import annotations

import argparse
from typing import Any, Callable

from ._shared import PROCESSED, log, write_json
from .liberia_census import FINAL, FINAL_CAPTURE, LICENCE, PUBLISHER
from .nigeria_capitals import articles, bind, cite, read_units, unseated

OUT = "liberia_capitals.json"
LISTING = "Districts of Liberia"
SRC_FINAL = f"{PUBLISHER}, 2022 Population and Housing Census, Final Results"
# (county, polygon) -> the English article on the district, where the
# polygon carries no Wikidata item.
TITLES: dict[tuple[str, str], str] = {
    ("Nimba", "Gbehlay-Geh"): "Gbehlageh District",
    ("Nimba", "Sanniquellie Mahn"): "Sanniquellie-Mahn District",
    ("Bong", "Sanoyeah"): "Sanayea District",
    ("Rivercess", "Zarflahn"): "Zartlahn District",
}


def why_for(listing: dict[str, Any] | None
            ) -> Callable[[dict[str, Any], dict[str, Any] | None, bool],
                          tuple[str, list[dict[str, Any]]]]:
    census = {"field": "capital", "name": SRC_FINAL, "url": FINAL, "archived": FINAL_CAPTURE,
              "license": LICENCE, "year": 2022}

    def why(p: dict[str, Any], a: dict[str, Any] | None, quiet: bool
            ) -> tuple[str, list[dict[str, Any]]]:
        if a is not None:
            return (f"English Wikipedia's article on {a['title']} names no seat for the "
                    "district, and LISGIS's 2022 census results name none.", [cite(a), census])
        return ("LISGIS's 2022 census results name no district seats, nor does English "
                "Wikipedia's list of Liberia's districts.",
                [census] + ([cite(listing)] if listing else []))
    return why


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="a label that tells one dispatch from another; not used")
    ap.parse_args()
    polys = unseated("LBR")
    items, got = read_units(polys, TITLES)
    records, said = bind("LBR", polys, items, got, why_for(articles([LISTING]).get(LISTING)))
    for line in said:
        log(f"  {line}")
    seated = sum(1 for r in records if isinstance(r["capital"], str))
    log(f"liberia_capitals: {len(polys)} districts without a seat on the map; {seated} seats "
        f"written, {len(records) - seated} reasons")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
