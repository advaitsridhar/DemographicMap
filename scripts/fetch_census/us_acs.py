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
self-identification percentages used everywhere else in this dataset.

That study is copyright ASARB, all rights reserved, and the OSF deposit behind
its DOI records no licence, so the figures are not committed here and no
scheduled refresh fetches them.  ``--religion-file`` reads a copy the operator
supplies, and what it produces is always labelled as adherence.

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
    NOT_AVAILABLE, NOT_COLLECTED, PROCESSED, gap, http_get, http_json, log,
    measure, record, shares, write_json,
)

BASE = "https://api.census.gov/data/{year}/acs/acs5"
# DP* variables are served by the data-profile endpoint, not the detailed
# tables -- asking acs/acs5 for DP05_0018E gets a plain-text error, not JSON.
BASE_PROFILE = "https://api.census.gov/data/{year}/acs/acs5/profile"

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


def query(year: int, get: list[str], geo: str, key: str | None,
          base: str = BASE) -> list[dict[str, str]]:
    params = [f"get=NAME,{','.join(get)}", f"for={geo}"]
    if key:
        params.append(f"key={key}")
    url = f"{base.format(year=year)}?" + "&".join(params)
    text = http_get(url, timeout=180)
    assert isinstance(text, str)
    # The Census API used to allow 500 anonymous calls a day; it now returns a
    # "Missing Key" HTML page with HTTP 200 when no key is sent. Turn that into
    # an instruction instead of a JSON traceback.
    if "Missing Key" in text[:400]:
        raise SystemExit(
            "us_acs: api.census.gov now requires an API key for every request. "
            "Request a free key at https://api.census.gov/data/key_signup.html "
            "and set it as the CENSUS_API_KEY environment variable (in CI: a "
            "repository secret of the same name).")
    import json as _json
    rows = _json.loads(text.lstrip("\ufeff"))
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
    prof = {geoid(r, level): r
            for r in query(year, list(PROFILE_LINES), geo, key, base=BASE_PROFILE)}

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

        # ACS names a county "Autauga County, Alabama". The state half is what
        # separates the thirty-one counties called Washington from each other, so
        # it is passed through for matching rather than thrown away.
        name = row["NAME"]
        state_name = name.split(",")[-1].strip() if level == "county" and "," in name else None

        out.append(record(
            f"USA-{gid}",
            name,
            level="admin1" if level == "state" else "admin2",
            parent="USA" if level == "state" else f"USA-{row['state']}",
            parent_name=state_name,
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
                         "(13 U.S.C. 221(c)), so no government figures exist at any "
                         "level. The gap is filled privately: the 2020 U.S. Religion "
                         "Census (ASARB, doi:10.17605/OSF.IO/ET2A5) counts adherents "
                         "reported by 372 religious bodies, reaching about 48.6% of "
                         "the population. That study is copyright, all rights "
                         "reserved, and states no redistribution licence, so this map "
                         "cites it rather than carrying it."),
            sources=[{"field": "ethnicity/language/population", "name": src,
                      "url": BASE.format(year=year), "license": "Public domain (U.S. Government work)"}],
        ))
    return out


# The county sheet carries a national block keyed FIPS = "Total": a full copy of
# the country's figures sitting in among the 3,141 counties. Summing the column
# without excluding it doubles the United States -- 322,019,032 adherents, 97%
# of the population, against a true 161,009,516.
#
# Nothing internal to the table catches that. Every county's own shares stay
# correct and still add up, exactly as they did for the ABS "Christianity Total"
# rows and the India C-16 group codes. It is only visible against a total the
# per-county rows did not produce, which is why that block is read and used as
# the control rather than skipped and forgotten.
NATIONAL_BLOCK = "total"
COUNTY_SHEET = "2020 Group by County"
MAX_GROUPS = 12


def read_group_detail(path: Path) -> tuple[dict[str, dict[str, float]],
                                           dict[str, float], float]:
    """Adherents by county and group, plus county populations and the control.

    Handles the ASARB workbook directly (.xlsx, sheet "2020 Group by County")
    and a CSV export of the same sheet. Returns per-county group counts, the
    2020 population the file itself implies for each county, and the national
    total carried by the FIPS = "Total" row.
    """
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheet = book[COUNTY_SHEET] if COUNTY_SHEET in book.sheetnames else book.worksheets[0]
        rows = sheet.iter_rows(values_only=True)
        header = [str(c or "") for c in next(rows)]
        records = (dict(zip(header, r)) for r in rows)
    else:
        import csv
        records = csv.DictReader(path.open(newline="", encoding="utf-8-sig"))

    def field(row: dict, *names: str) -> Any:
        for name in names:
            for key in row:
                if key and key.strip().lower() == name:
                    return row[key]
        return None

    counties: dict[str, dict[str, float]] = {}
    populations: dict[str, float] = {}
    national = 0.0
    for row in records:
        fips = str(field(row, "fips") or "").strip()
        if not fips:
            continue
        try:
            adherents = float(field(row, "adherents", "adherent"))
        except (TypeError, ValueError):
            continue          # blank means not reported, which is not zero

        # Before anything else: the national row names no group, so a reader
        # that requires one skips it silently and loses the only figure the
        # county rows can be checked against.
        if fips.lower() == NATIONAL_BLOCK:
            national += adherents
            continue

        group = str(field(row, "group name", "grpname") or "").strip()
        if not group:
            continue
        fips = fips.zfill(5)
        counties.setdefault(fips, {})[group] = adherents
        # The file prints each count as a share of its county's population, so
        # the denominator it used can be recovered rather than assumed. Taking
        # it from the file keeps the shares equal to the published ones; the
        # ACS population on the record is a different year and would not.
        if fips not in populations:
            try:
                share = float(field(row, "adherents as % of total population"))
            except (TypeError, ValueError):
                share = 0.0
            if share > 0:
                populations[fips] = adherents / share
    return counties, populations, national


def check_national(counties: dict[str, dict[str, float]], national: float) -> None:
    """The counties must add up to the national block, or the read is wrong.

    This is the check that catches reading the national block as a county. It
    compares against a figure the per-county rows did not produce, so unlike a
    shares-add-to-100% test it cannot be satisfied by double counting.
    """
    if not national:
        raise SystemExit(
            f"no national block (FIPS {NATIONAL_BLOCK!r}) in the group detail file. "
            "Either the layout changed or it was filtered out -- without it the "
            "county figures have nothing independent to reconcile against, and a "
            "doubled country reads as a valid table.")
    total = sum(sum(g.values()) for g in counties.values())
    control = national
    drift = abs(total - control) / control if control else 1.0
    print(f"  counties {total:,.0f} vs national block {control:,.0f} "
          f"({drift:.4%} apart, {len(counties)} counties)")
    if drift > 0.005:
        raise SystemExit(f"county adherents are {drift:.2%} from the national block")


def attach_religion(records: list[dict[str, Any]], path: Path) -> None:
    """Merge a 2020 U.S. Religion Census county extract (ASARB / ARDA RCMSCY20).

    Opt-in, and it stays opt-in: the study is copyright ASARB, all rights
    reserved, and the OSF deposit behind its DOI records no licence at all. The
    repository therefore ships this reader and not the figures. Supplying the
    workbook -- and publishing what comes out of it -- is the operator's call
    against their own copy, not something a scheduled refresh does by itself.
    """
    counties, populations, national = read_group_detail(path)
    check_national(counties, national)

    matched = 0
    for rec in records:
        fips = rec.get("codes", {}).get("geoid", "")
        groups = counties.get(fips)
        if not groups:
            continue
        matched += 1
        top = dict(sorted(groups.items(), key=lambda kv: kv[1], reverse=True)[:MAX_GROUPS])
        pop = populations.get(fips)
        if not pop:
            continue
        rec["religion"] = shares(top, total=pop)
        rec["religion_basis"] = "adherents"
        rec["religion_note"] = (
            "2020 U.S. Religion Census (ASARB): adherents reported by participating "
            "religious bodies, as a share of the 2020 census population. This is not "
            "self-identification and does not sum to 100% -- the study reached about "
            "48.6% of the population nationally, and the remainder is uncounted "
            "rather than unaffiliated. Not comparable with the census religion "
            "figures used for other countries.")
        rec["sources"].append({"field": "religion", "name": "2020 U.S. Religion Census (ASARB)",
                               "url": "https://www.usreligioncensus.org/",
                               "license": "Copyright ASARB, all rights reserved; "
                                          "no redistribution licence stated"})
    print(f"  religion attached to {matched} of {len(records)} records")


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
        + ("" if key else " (no CENSUS_API_KEY set; the API now rejects keyless requests)"))
    records = fetch(args.level, args.year, key)
    if args.religion_file:
        attach_religion(records, args.religion_file)
    out = args.out or PROCESSED / f"us_{args.level}.json"
    write_json(out, records)
    log(f"  {len(records)} {args.level} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
