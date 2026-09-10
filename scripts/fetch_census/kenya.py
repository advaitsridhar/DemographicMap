#!/usr/bin/env python3
"""Kenya: religion by county, from the 2019 census (KNBS Volume IV, Table 2.30).

Kenya's 47 counties were filled by Afrobarometer -- a survey of some 2,400
people -- because that was what this project could reach. The 2019 Population
and Housing Census counted religion for every one of 47.2 million residents and
published it by county, and a census beats a survey wherever both exist. So this
replaces it, and because it replaces figures already on the map, the repository
owner reviews the change before it ships.

**Where the file comes from, and why not from KNBS.** The Bureau's own site
fails TLS verification on a clean client (``unable to get local issuer
certificate`` -- an incomplete chain on their side), and this project never
turns verification off. The same table is mirrored on openAFRICA, Code for
Africa's open-data portal, as a CSV last modified in March 2020; that copy was
requested on a runner and its header row read before this was written:

    County, Total, Catholic, Protestant, Evangelical Churches,
    African Instituted Churches, Orthodox, Other Christian, Islam, Hindu,
    Traditionists, Other Religion, No religion /Atheists, Don't Know, Not Stated

One national row (KENYA) precedes 47 upper-case counties. The thirteen
categories are read as published and each county is checked against its own
Total; a county that misses by more than half a percent refuses the run.

**One name.** KNBS writes THARAKA-NITHI, the county's name; geoBoundaries draws
it as "Tharaka". The record keeps the official name and carries the boundary
file's as an alias, which is how the matcher is told they are the same place.

Nothing exists below county: Volume IV does not break religion down by
sub-county, so the 290 second-level shapes stay as they are.

Usage:
    python -m scripts.fetch_census.kenya
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares, write_json,
)

OUT = "kenya_county.json"
YEAR = 2019
SOURCE = "KNBS, 2019 Kenya Population and Housing Census, Volume IV Table 2.30 (via openAFRICA)"
LICENCE = "Open Data (openAFRICA mirror of a KNBS publication)"
URL = ("https://open.africa/dataset/9b94fe50-9d75-4b92-be00-6354c6e6cc88/resource/"
       "2b2a7b48-ff46-4aa1-91c8-94b2c91e568b/download/"
       "distribution-of-population-by-religious-affiliation-and-county-2019-census-volume-iv.csv")
PAGE = "https://open.africa/dataset/2019-kenya-population-and-housing-census"

# The boundary file's spelling where it differs from the county's own name.
ALIASES = {"Tharaka-Nithi": ["Tharaka"]}

# Source labels that a reader would not recognise as written.
RELABEL = {
    "No religion /Atheists": "No religion",
    "Traditionists": "Traditional religion",
    "Don't Know": "Don't know",
}


def title(name: str) -> str:
    """KNBS shouts; the map does not. 'TAITA/TAVETA' -> 'Taita/Taveta'.

    str.title() capitalises after an apostrophe too, and MURANG'A came out as
    Murang'A; the letter after an apostrophe stays lower.
    """
    return re.sub(r"'([A-Z])", lambda m: "'" + m.group(1).lower(), name.title())


def count(cell: str) -> int:
    return int((cell or "0").replace(",", "").strip() or 0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    log("kenya: religion by county, KNBS 2019 Volume IV via openAFRICA")
    text = http_get(URL, timeout=180)
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", "replace")
    rows = list(csv.reader(io.StringIO(text)))
    header = [h.strip() for h in rows[0]]
    if header[:2] != ["County", "Total"]:
        raise SystemExit(f"kenya: unexpected header {header[:4]}; the file changed shape")
    categories = header[2:]

    records: list[dict[str, Any]] = []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        raw = row[0].strip()
        if raw.upper() == "KENYA":
            continue                                   # the national row
        total = count(row[1])
        counts = {RELABEL.get(cat, cat): count(cell) for cat, cell in zip(categories, row[2:])}
        summed = sum(counts.values())
        if total and abs(summed - total) > total * 0.005:
            raise SystemExit(f"kenya: {raw} sums to {summed:,} against a published "
                             f"{total:,}; the columns chosen are wrong")
        name = title(raw)
        records.append(record(
            f"KEN-{name.replace(' ', '_').replace('/', '_')}", name,
            level="admin1", parent="KEN", country="KEN",
            aliases=ALIASES.get(name, []),
            population=measure(total, year=YEAR, source=SOURCE) if total else gap(NOT_AVAILABLE),
            religion=shares(counts, total=total) or gap(NOT_AVAILABLE),
            religion_note=(f"{SOURCE}. A census count of all residents, replacing the "
                           f"Afrobarometer survey estimate this county carried before. "
                           f"'Protestant' and 'Evangelical Churches' are KNBS's own "
                           f"separate categories and are kept apart."),
            sources=[{"field": "religion", "name": SOURCE, "url": PAGE, "license": LICENCE}],
        ))
    log(f"  {len(records)} counties")
    if len(records) != 47:
        raise SystemExit(f"kenya: expected 47 counties, read {len(records)}")
    write_json(args.out or PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
