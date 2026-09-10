#!/usr/bin/env python3
"""Malaysia: ethnicity by state and administrative district, from OpenDOSM.

The Department of Statistics Malaysia publishes its population series as open
CSV on OpenDOSM, and two of those tables carry ethnicity: ``population_state``
(sixteen states and federal territories, yearly from 1970) and
``population_district`` (the administrative districts, yearly from 2020). Both
were requested on a runner and their header rows read before this was written:

    state,date,sex,age,ethnicity,population
    state,district,date,sex,age,ethnicity,population

Population is in thousands with one decimal. The ethnicity dimension has an
``overall`` row and six categories: ``bumi_malay``, ``bumi_other``, ``chinese``,
``indian``, ``other_citizen`` and ``other_noncitizen``. The last is a
citizenship category rather than an ethnic one, and it stays: DOSM publishes it
in the same dimension, and a district like Tawau or Sandakan is a fifth
non-citizen, so a chart that dropped the row would put those people into every
other bar. The note on each record says what the row is.

**What these figures are.** The 2020 point is the Population and Housing
Census 2020's reference year and the later ones are DOSM's annual estimates
carried forward from it. This adapter reads the latest date the file holds,
records that year, and calls the figures what OpenDOSM calls them -- population
estimates -- rather than a census count. Malaysia's districts carried nothing
before this, so an estimate from the national office is the first figure, not
a replacement.

**Names.** DOSM writes the state as it is in Malay (Melaka, Pulau Pinang,
W.P. Kuala Lumpur); the boundary file has the English exonym (Malacca, Penang,
Kuala Lumpur). The record keeps DOSM's name and carries the boundary file's as
an alias. Districts are matched within their state, since the CSV names it.

Usage:
    python -m scripts.fetch_census.malaysia --level both
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

STATE_URL = "https://storage.dosm.gov.my/population/population_state.csv"
DISTRICT_URL = "https://storage.dosm.gov.my/population/population_district.csv"
PAGES = {
    "state": "https://open.dosm.gov.my/data-catalogue/population_state",
    "district": "https://open.dosm.gov.my/data-catalogue/population_district",
}
SOURCE = "Department of Statistics Malaysia, OpenDOSM population estimates by ethnicity"
LICENCE = "Creative Commons Attribution 4.0 (OpenDOSM)"

LABELS = {
    "bumi_malay": "Malay",
    "bumi_other": "Other Bumiputera",
    "chinese": "Chinese",
    "indian": "Indian",
    "other_citizen": "Other (Malaysian citizen)",
    "other_noncitizen": "Non-Malaysian citizen",
}
NOTE = ("DOSM's ethnicity dimension includes non-citizens as a category of the "
        "resident population and it is kept as one; the other five are Malaysian "
        "citizens. 'Other Bumiputera' is DOSM's own group for the indigenous "
        "peoples of Sabah, Sarawak and the peninsula other than Malays.")

# The boundary file's English name where DOSM's differs from it.
STATE_ALIASES = {
    "Melaka": ["Malacca"],
    "Pulau Pinang": ["Penang"],
    "W.P. Kuala Lumpur": ["Kuala Lumpur"],
    "W.P. Labuan": ["Labuan"],
    "W.P. Putrajaya": ["Putrajaya"],
}
# geoBoundaries' spelling of a district where it is not DOSM's. Each is the
# same place under an older or alternative name; none is a guess at a
# different one.
DISTRICT_ALIASES = {
    "Hulu Langat": ["Ulu Langat"],
    "Hulu Selangor": ["Ulu Selangor"],
    "Kulai": ["Kulaijaya"],
    "Tangkak": ["Ledang"],
    "Nabawan": ["Nabawan / Persiangan"],
}


def read_csv(url: str) -> list[dict[str, str]]:
    text = http_get(url, timeout=300)
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(text)))


def thousands(cell: str) -> int:
    return int(round(float(cell) * 1000))


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def compositions(rows: list[dict[str, str]], keys: tuple[str, ...]
                 ) -> tuple[str, dict[tuple[str, ...], dict[str, int]]]:
    """Per place, the latest year's ethnicity counts (both sexes, all ages).

    Returns the date read and ``{place_key: {"__total__": n, label: n, ...}}``.
    """
    wanted = [r for r in rows if r["sex"] == "both" and r["age"] == "overall"]
    latest = max(r["date"] for r in wanted if r["ethnicity"] != "overall")
    out: dict[tuple[str, ...], dict[str, int]] = {}
    for r in wanted:
        if r["date"] != latest:
            continue
        place = tuple(r[k] for k in keys)
        eth = r["ethnicity"]
        label = "__total__" if eth == "overall" else LABELS.get(eth)
        if label is None:
            raise SystemExit(f"malaysia: unknown ethnicity category {eth!r}; DOSM changed the file")
        out.setdefault(place, {})[label] = thousands(r["population"])
    return latest, out


def check(name: str, counts: dict[str, int]) -> int:
    total = counts.get("__total__", 0)
    summed = sum(v for k, v in counts.items() if k != "__total__")
    # Each category is rounded to the nearest hundred, so six of them can miss
    # the published total by a few hundred; a real miss is a wrong column.
    if total and abs(summed - total) > max(600, total * 0.01):
        raise SystemExit(f"malaysia: {name} sums to {summed:,} against {total:,}")
    return total


def build_states() -> list[dict[str, Any]]:
    date, comps = compositions(read_csv(STATE_URL), ("state",))
    year = int(date[:4])
    log(f"  states: {len(comps)} at {date}")
    records = []
    for (state,), counts in sorted(comps.items()):
        total = check(state, counts)
        records.append(record(
            f"MYS-{slug(state)}", state, level="admin1", parent="MYS", country="MYS",
            aliases=STATE_ALIASES.get(state, []),
            population=measure(total, year=year, source=SOURCE) if total else gap(NOT_AVAILABLE),
            ethnicity=shares({k: v for k, v in counts.items() if k != "__total__"}, total=total)
            or gap(NOT_AVAILABLE),
            ethnicity_note=NOTE,
            sources=[{"field": "population/ethnicity", "name": f"{SOURCE} ({year})",
                      "url": PAGES["state"], "license": LICENCE}],
        ))
    if len(records) != 16:
        raise SystemExit(f"malaysia: expected 16 states, read {len(records)}")
    return records


def build_districts() -> list[dict[str, Any]]:
    date, comps = compositions(read_csv(DISTRICT_URL), ("state", "district"))
    year = int(date[:4])
    log(f"  districts: {len(comps)} at {date}")
    records = []
    for (state, district), counts in sorted(comps.items()):
        total = check(f"{state}/{district}", counts)
        records.append(record(
            f"MYS-{slug(state)}-{slug(district)}", district, level="admin2",
            parent=f"MYS-{slug(state)}", parent_name=state, country="MYS",
            aliases=DISTRICT_ALIASES.get(district, []),
            population=measure(total, year=year, source=SOURCE) if total else gap(NOT_AVAILABLE),
            ethnicity=shares({k: v for k, v in counts.items() if k != "__total__"}, total=total)
            or gap(NOT_AVAILABLE),
            ethnicity_note=NOTE,
            sources=[{"field": "population/ethnicity", "name": f"{SOURCE} ({year})",
                      "url": PAGES["district"], "license": LICENCE}],
        ))
    if not 150 <= len(records) <= 170:
        raise SystemExit(f"malaysia: expected about 160 districts, read {len(records)}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="both", choices=["state", "district", "both"])
    args = ap.parse_args()
    log("malaysia: ethnicity by state and district, OpenDOSM")
    if args.level in ("state", "both"):
        write_json(PROCESSED / "malaysia_state.json", build_states())
    if args.level in ("district", "both"):
        write_json(PROCESSED / "malaysia_district.json", build_districts())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
