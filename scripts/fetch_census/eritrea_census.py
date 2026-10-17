#!/usr/bin/env python3
"""Eritrea: why the regions and sub-regions carry no median age or sex ratio.

Eritrea has never taken a national census: the country has had none since
independence in 1993, and Ethiopia's 1984 census did not reach most of it. The
nearest measurement is the Eritrea Population and Health Survey 2010, run by the
National Statistics Office with Fafo, whose chapter 2 gives the household
population by age, sex and residence -- for the country, its towns and its
countryside -- and its regional tables are of fertility, mortality and health.
So no figure exists for the ages or sexes of a region (zoba) or sub-region
(subzoba), and every one of them says so. Nothing is read over the network; the
survey's report is cited for the reader.

Usage:
    python -m scripts.fetch_census.eritrea_census
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from ._shared import NOT_AVAILABLE, PROCESSED, gap, log, record, write_json

OUT = "eritrea_census.json"
SITE = PROCESSED.parent.parent / "site" / "data"
SURVEY = ("National Statistics Office (Eritrea) and Fafo, Eritrea Population and Health Survey "
          "2010 (2013)")
URL = "https://www.fafo.no/images/pub/2013/EPHS2010.pdf"
WHY = {
    "admin1": ("Eritrea has never taken a national census. Its 2010 Population and Health "
               "Survey gives the household population's ages and sexes for the country, its "
               "towns and its countryside, not by region, so no figure exists for this "
               "region's median age or sex ratio."),
    "admin2": ("Eritrea has never taken a national census. Its 2010 Population and Health "
               "Survey gives the household population's ages and sexes for the country, its "
               "towns and its countryside, not by region or sub-region, so no figure exists "
               "for this sub-region's median age or sex ratio."),
}


def build(units: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    records = []
    for level, shapes in units.items():
        stated = gap(NOT_AVAILABLE, WHY[level])
        for shape in shapes:
            records.append(record(
                f"ERI-{shape['id']}", shape["name"].strip(), level=level, parent="ERI",
                country="ERI", match_by="shape_id", shape_id=shape["id"],
                median_age=stated, sex_ratio=stated,
                sources=[{"field": "median_age/sex_ratio", "name": SURVEY, "url": URL,
                          "year": 2010, "license": "National Statistics Office publication"}]))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="", help="a label that tells two dispatches apart; ignored")
    ap.parse_args()
    units = {level: json.loads((SITE / level / "ERI.units.json").read_text())
             for level in ("admin1", "admin2")}
    records = build(units)
    write_json(PROCESSED / OUT, records)
    log(f"  {len(units['admin1'])} regions and {len(units['admin2'])} sub-regions say why they "
        "carry no median age or sex ratio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
