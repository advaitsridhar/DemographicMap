#!/usr/bin/env python3
"""Canada -- Statistics Canada 2021 Census Profile (provinces and census divisions).

StatCan keys census geography by **DGUID** (e.g. ``2021A000224`` for Quebec,
``2021A00033520`` for Toronto CD).  The Census Profile web data service returns
every characteristic for one geography at a time, so this walks the geography
list and pulls the four characteristic blocks the app uses.

Canada's census asks religion only every ten years -- 2021 has it, 2016 does
not -- and reports "visible minority" (a legal category under the Employment
Equity Act) rather than ethnicity, alongside a separate multi-response
"ethnic or cultural origin" question.  Both are labelled as such so they are not
read as equivalent to, say, the UK's ethnic-group question.

Usage:
    python -m scripts.fetch_census.statcan --level province
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, http_json, log, measure, record, shares, write_json,
)

PROFILE = ("https://www12.statcan.gc.ca/rest/census-recensement/CPR2021.json"
           "?lang=E&dguid={dguid}&topic={topic}&notes=0&stat=0")
GEO_LIST = ("https://www12.statcan.gc.ca/rest/census-recensement/CR2021Geo.json"
            "?lang=E&geos={geos}&cpt=00")

TOPICS = {"population": 1, "age_sex": 2, "language": 5, "ethnicity": 9, "religion": 10}
GEOS = {"province": "PR", "census_division": "CD"}

# Standard Geographical Classification province/territory codes. DGUIDs for
# 2021 are deterministic -- "2021A0002" + the two-digit code -- and these codes
# have been stable for decades, so the provinces need no geography-list call
# (which now serves an HTML page instead of JSON; see the first live run).
PROVINCES = {
    "10": "Newfoundland and Labrador", "11": "Prince Edward Island",
    "12": "Nova Scotia", "13": "New Brunswick", "24": "Quebec",
    "35": "Ontario", "46": "Manitoba", "47": "Saskatchewan", "48": "Alberta",
    "59": "British Columbia", "60": "Yukon", "61": "Northwest Territories",
    "62": "Nunavut",
}


def geographies(level: str) -> list[dict[str, Any]]:
    if level == "province":
        return [{"GEO_ID_ID": f"2021A0002{code}", "GEO_NAME_NOM": name}
                for code, name in PROVINCES.items()]
    payload = http_json(GEO_LIST.format(geos=GEOS[level]), timeout=180)
    rows = payload.get("DATA", [])
    cols = [c.upper() for c in payload.get("COLUMNS", [])]
    return [dict(zip(cols, row)) for row in rows]


def profile(dguid: str, topic: str) -> list[dict[str, Any]]:
    payload = http_json(PROFILE.format(dguid=dguid, topic=TOPICS[topic]), timeout=180)
    cols = [c.upper() for c in payload.get("COLUMNS", [])]
    return [dict(zip(cols, row)) for row in payload.get("DATA", [])]


def block(rows: list[dict[str, Any]], *, keep: int = 14) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows:
        label = (row.get("TEXT_NAME_NOM") or "").strip()
        value = row.get("T_DATA_DONNEE")
        if not label or value in (None, "", ".."):
            continue
        try:
            out[label] = float(value)
        except (TypeError, ValueError):
            continue
    return dict(sorted(out.items(), key=lambda kv: kv[1], reverse=True)[:keep])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="province", choices=list(GEOS))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    src = "Statistics Canada, 2021 Census of Population"
    level = "admin1" if args.level == "province" else "admin2"
    records: list[dict[str, Any]] = []
    for geo in geographies(args.level):
        dguid = geo.get("GEO_ID_ID") or geo.get("DGUID")
        name = geo.get("GEO_NAME_NOM") or geo.get("NAME")
        if not dguid:
            continue
        log(f"  {dguid} {name}")
        try:
            religion = block(profile(dguid, "religion"))
            ethnicity = block(profile(dguid, "ethnicity"))
            language = block(profile(dguid, "language"))
        except Exception as exc:
            log(f"    skipped: {exc}")
            continue
        records.append(record(
            f"CAN-{dguid}", name, level=level, parent="CAN",
            codes={"dguid": dguid},
            religion=shares(religion) or gap(NOT_AVAILABLE),
            religion_note="Statistics Canada 2021 religion question (asked once per decade).",
            ethnicity=shares(ethnicity) or gap(NOT_AVAILABLE),
            ethnicity_note=("Statistics Canada reports 'visible minority' (Employment Equity Act "
                            "category) and a separate multi-response ethnic or cultural origin "
                            "question; neither is equivalent to another country's ethnicity."),
            language=shares(language) or gap(NOT_AVAILABLE),
            sources=[{"field": "religion/ethnicity/language", "name": src,
                      "url": PROFILE.format(dguid=dguid, topic=TOPICS["religion"]),
                      "license": "Statistics Canada Open Licence"}],
        ))
    write_json(args.out or PROCESSED / f"canada_{args.level}.json", records)
    log(f"  {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
