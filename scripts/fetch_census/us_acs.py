#!/usr/bin/env python3
"""United States -- Census Bureau ACS 5-year API (states and counties).

Race/ethnicity comes from **B03002** (Hispanic or Latino origin by race), not
B02001, because only B03002 makes the Hispanic-origin question orthogonal to
race the way the published "White, non-Hispanic" figures do.  Language uses
**C16001** (the collapsed version of B16001, which is far smaller over 3,143
counties).  Median age and sex ratio come from the **DP05** profile.

Religion is *not* in the census: the US census has been barred from asking a
mandatory religion question since 1976 (13 U.S.C. 221(c)).  The county-level
substitute is the 2020 U.S. Religion Census (ASARB, distributed by ARDA), which
counts *adherents reported by 372 religious bodies* -- 161,224,088 people, about
48.6% of the 2020 population -- and is therefore not comparable with the
self-identification percentages used everywhere else in this dataset.  It is
loaded separately by ``--religion-file`` and always labelled as adherence.

An API key is optional below 500 calls/day; set ``CENSUS_API_KEY`` to lift that.

Usage:
    python -m scripts.fetch_census.us_acs --level county --year 2022
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, gap, http_json, log, measure,
    record, shares, write_json,
)

BASE = "https://api.census.gov/data/{year}/acs/acs5"

# B03002 lines that partition the population exactly once.
RACE_LINES = {
    "B03002_003E": "White (non-Hispanic)",
    "B03002_004E": "Black or African American (non-Hispanic)",
    "B03002_005E": "American Indian and Alaska Native (non-Hispanic)",
    "B03002_006E": "Asian (non-Hispanic)",
    "B03002_007E": "Native Hawaiian and Other Pacific Islander (non-Hispanic)",
    "B03002_008E": "Some other race (non-Hispanic)",
    "B03002_009E": "Two or more races (non-Hispanic)",
    "B03002_012E": "Hispanic or Latino (any race)",
}
RACE_TOTAL = "B03002_001E"

LANGUAGE_LINES = {
    "C16001_002E": "English only",
    "C16001_003E": "Spanish",
    "C16001_006E": "French, Haitian, or Cajun",
    "C16001_009E": "German or other West Germanic",
    "C16001_012E": "Russian, Polish, or other Slavic",
    "C16001_015E": "Other Indo-European",
    "C16001_018E": "Korean",
    "C16001_021E": "Chinese (incl. Mandarin, Cantonese)",
    "C16001_024E": "Vietnamese",
    "C16001_027E": "Tagalog (incl. Filipino)",
    "C16001_030E": "Other Asian and Pacific Island",
    "C16001_033E": "Arabic",
    "C16001_036E": "Other and unspecified",
}
LANGUAGE_TOTAL = "C16001_001E"

PROFILE_LINES = {"DP05_0018E": "median_age", "DP05_0004E": "sex_ratio_m_per_100f"}


def query(year: int, get: list[str], geo: str, key: str | None) -> list[dict[str, str]]:
    params = [f"get=NAME,{','.join(get)}", f"for={geo}"]
    if key:
        params.append(f"key={key}")
    url = f"{BASE.format(year=year)}?" + "&".join(params)
    rows = http_json(url, timeout=180)
    header, *body = rows
    return [dict(zip(header, row)) for row in body]


def as_float(value: str | None) -> float | None:
    """ACS uses negative sentinels (-666666666) for suppressed cells."""
    if value in (None, "", "null"):
        return None
    try:
        num = float(value)
    except ValueError:
        return None
    return None if num <= -666666 else num


def geoid(row: dict[str, str], level: str) -> str:
    return row["state"] + (row.get("county", "") if level == "county" else "")


def fetch(level: str, year: int, key: str | None) -> list[dict[str, Any]]:
    geo = "county:*" if level == "county" else "state:*"
    src = f"U.S. Census Bureau, ACS {year} 5-year estimates"

    race = query(year, [RACE_TOTAL, *RACE_LINES], geo, key)
    lang = {geoid(r, level): r for r in query(year, [LANGUAGE_TOTAL, *LANGUAGE_LINES], geo, key)}
    prof = {geoid(r, level): r for r in query(year, list(PROFILE_LINES), geo, key)}

    out: list[dict[str, Any]] = []
    for row in race:
        gid = geoid(row, level)
        total = as_float(row.get(RACE_TOTAL))
        counts = {label: as_float(row.get(code)) for code, label in RACE_LINES.items()}
        counts = {k: v for k, v in counts.items() if v is not None}

        lrow = lang.get(gid, {})
        lcounts = {label: as_float(lrow.get(code)) for code, label in LANGUAGE_LINES.items()}
        lcounts = {k: v for k, v in lcounts.items() if v}

        prow = prof.get(gid, {})
        median = as_float(prow.get("DP05_0018E"))
        ratio = as_float(prow.get("DP05_0004E"))

        out.append(record(
            f"USA-{gid}",
            row["NAME"],
            level="admin1" if level == "state" else "admin2",
            parent="USA" if level == "state" else f"USA-{row['state']}",
            codes={"geoid": gid, "fips_state": row["state"],
                   "fips_county": row.get("county")},
            population=measure(int(total), year=year, source=src) if total else gap(NOT_AVAILABLE),
            median_age=measure(median, unit="years", year=year, source=src) if median else gap(NOT_AVAILABLE),
            sex_ratio=(measure(round(ratio * 10), unit="males_per_1000_females",
                               year=year, source=src) if ratio else gap(NOT_AVAILABLE)),
            ethnicity=shares(counts, total=total) or gap(NOT_AVAILABLE),
            ethnicity_note=("US Census race and Hispanic-origin categories (ACS table B03002). "
                            "Not comparable with other countries' ethnicity classifications."),
            language=shares(lcounts, total=as_float(lrow.get(LANGUAGE_TOTAL))) or gap(NOT_AVAILABLE),
            language_note="Language spoken at home, population 5 years and over (ACS table C16001).",
            religion=gap(NOT_COLLECTED,
                         "The U.S. census may not ask a mandatory religion question "
                         "(13 U.S.C. 221(c)). Use --religion-file to attach the 2020 "
                         "U.S. Religion Census adherence estimates instead."),
            sources=[{"field": "ethnicity/language/population", "name": src,
                      "url": BASE.format(year=year), "license": "Public domain (U.S. Government work)"}],
        ))
    return out


def attach_religion(records: list[dict[str, Any]], path: Path) -> None:
    """Merge a 2020 U.S. Religion Census county extract (ARDA dataset RCMSCY20).

    Expects a CSV with ``FIPS``, ``GRPNAME`` and ``ADHERENT`` columns -- the
    layout of the ASARB "Group Detail Data by County" release.
    """
    import csv
    from collections import defaultdict

    by_fips: dict[str, dict[str, float]] = defaultdict(dict)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            fips = (row.get("FIPS") or row.get("fips") or "").zfill(5)
            group = row.get("GRPNAME") or row.get("grpname")
            adherents = row.get("ADHERENT") or row.get("adherent")
            if not (fips and group and adherents):
                continue
            try:
                by_fips[fips][group] = by_fips[fips].get(group, 0.0) + float(adherents)
            except ValueError:
                continue

    for rec in records:
        fips = rec.get("codes", {}).get("geoid", "")
        groups = by_fips.get(fips)
        if not groups:
            continue
        top = dict(sorted(groups.items(), key=lambda kv: kv[1], reverse=True)[:12])
        pop = rec["population"].get("value") if isinstance(rec["population"], dict) else None
        rec["religion"] = shares(top, total=pop)
        rec["religion_basis"] = "adherents"
        rec["religion_note"] = (
            "2020 U.S. Religion Census (ASARB/ARDA): adherents reported by participating "
            "religious bodies, expressed as a share of total population. This is NOT "
            "self-identification and does not sum to 100% -- the 2020 collection covered "
            "about 48.6% of the population.")
        rec["sources"].append({"field": "religion", "name": "2020 U.S. Religion Census (ASARB)",
                               "url": "https://www.usreligioncensus.org/",
                               "license": "See ARDA terms of use"})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="county", choices=["state", "county"])
    ap.add_argument("--year", type=int, default=2022)
    ap.add_argument("--religion-file", type=Path, default=None,
                    help="2020 U.S. Religion Census county CSV (ARDA RCMSCY20)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    key = os.environ.get("CENSUS_API_KEY")
    log(f"us_acs: ACS {args.year} 5-year, level={args.level}"
        + ("" if key else " (no CENSUS_API_KEY set; limited to 500 calls/day)"))
    records = fetch(args.level, args.year, key)
    if args.religion_file:
        attach_religion(records, args.religion_file)
    out = args.out or PROCESSED / f"us_{args.level}.json"
    write_json(out, records)
    log(f"  {len(records)} {args.level} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
