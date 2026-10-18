#!/usr/bin/env python3
"""The Gambia -- the seats of local government areas and districts, from English Wikipedia.

Wikidata names the seat of six of the eight local government areas (LGAs)
the map draws and of none of its 48 districts, and the 2013 census's report
on spatial distribution names no headquarters, capital or administrative
centre on any of its 373 pages. English Wikipedia's article on the town of
Kuntaur says it is "the seat of the Kuntaur Local Government Area", and its
article on Nianija district that the district's capital is Chamen. This
reads the article on each unit the map shows no seat for, with
nigeria_capitals' reader: an LGA's through the title in ``TITLES``, a
district's through its Wikidata item or ``TITLES``, and writes the seat
where the article names one, or the reason, citing the revision read.

The five parts Kanifing municipality is drawn as (Bakau, Jeshwang and three
of Serrekunda) are not census districts -- the census counts the
municipality as one -- and are given that reason.

Usage:
    python -m scripts.fetch_census.gambia_capitals
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, record, write_json
from .gambia_census import DIRECTORY, KANIFING_PARTS, LICENCE, SPATIAL, SRC_DIR
from .nigeria_capitals import bind, cite, read_units, unseated

OUT = "gambia_capitals.json"
SRC_SPATIAL = ("Gambia Bureau of Statistics, 2013 Population and Housing Census, Volume 5: "
               "Spatial Distribution")
# (LGA, or "GMB" for an LGA itself, polygon) -> the English article on it.
TITLES: dict[tuple[str, str], str] = {
    ("GMB", "Kuntaur"): "Kuntaur",
    ("GMB", "Kanifing"): "Kanifing",
}


def why(p: dict[str, Any], a: dict[str, Any] | None, quiet: bool
        ) -> tuple[str, list[dict[str, Any]]]:
    unit = "local government area" if p["level"] == "admin1" else "district"
    census = {"field": "capital", "name": SRC_SPATIAL, "url": SPATIAL, "license": LICENCE,
              "year": 2013}
    if a is not None:
        return (f"English Wikipedia's article on {a['title']} names no seat for the {unit}, and "
                "the 2013 census's report on spatial distribution names none.",
                [cite(a), census])
    return (f"English Wikipedia has no article on this {unit}, and the 2013 census's report on "
            "spatial distribution names no seats.", [census])


def kanifing_part(p: dict[str, Any]) -> dict[str, Any]:
    reason = ("The 2013 census counts Kanifing municipality as one district, of which this is "
              "one of the five parts drawn here, so no seat is named for the part.")
    return record(f"GMB-SEAT-{p['id']}", p["name"], level="admin2", parent="GMB",
                  country="GMB", match_by="shape_id", shape_id=p["id"],
                  capital=gap(NOT_AVAILABLE, reason),
                  sources=[{"field": "capital", "name": SRC_DIR, "url": DIRECTORY,
                            "license": LICENCE, "year": 2013}])


def main() -> int:
    argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    records: list[dict[str, Any]] = []
    for level in ("admin1", "admin2"):
        polys = unseated("GMB", level)
        parts = [p for p in polys if level == "admin2" and p["parent"] == "Kanifing"
                 and p["name"] in KANIFING_PARTS]
        polys = [p for p in polys if p not in parts]
        items, got = read_units(polys, TITLES)
        found, said = bind("GMB", polys, items, got, why)
        records += found + [kanifing_part(p) for p in parts]
        for line in said:
            log(f"  {level}: {line}")
        log(f"  {level}: {len(parts)} parts of Kanifing given their reason")
    seated = sum(1 for r in records if isinstance(r["capital"], str))
    log(f"gambia_capitals: {seated} seats written, {len(records) - seated} reasons")
    write_json(PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
