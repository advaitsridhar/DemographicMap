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

**Median age and sex ratio** come from the same two files, at the same date as
the ethnicity: the ``age`` dimension splits everyone into five-year groups up to
an open ``85+`` (OpenDOSM publishes nothing finer by state or district), and
the ``sex`` dimension into male and female. The median is interpolated within
the five-year group that holds the middle person; the ratio is males per 100
females. Each cell is rounded to the nearest hundred people, so a district's
groups are checked against its own total within that rounding, its sexes the
same way, and the districts of each state against the state file's figure for
the same date. Every record says the figures are DOSM's estimates for that
year, carried forward from the 2020 census, not a count.

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
    NOT_AVAILABLE, PROCESSED, dated, gap, http_get, log, measure, record, shares,
    write_json,
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
    # DOSM abbreviates Seberang Perai, the mainland half of Penang.
    "Sp Selatan": ["Seberang Perai Selatan"],
    "Sp Tengah": ["Seberang Perai Tengah"],
    "Sp Utara": ["Seberang Perai Utara"],
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


AGE_GROUP = re.compile(r"^(\d{1,2})-(\d{1,2})$")
AGE_OPEN = re.compile(r"^(\d{1,2})\+$")
# The groups the files carried when this was written: 0-4 ... 80-84, 85+.
EXPECTED_GROUPS = 18


def age_band(label: str) -> tuple[int, int | None] | None:
    if m := AGE_GROUP.match(label):
        return int(m.group(1)), int(m.group(2))
    if m := AGE_OPEN.match(label):
        return int(m.group(1)), None
    return None


def grouped_median(groups: list[tuple[int, int | None, float]]) -> float | None:
    """The median of (from, to, people) five-year groups; None if in the open one."""
    total = sum(n for _, _, n in groups)
    if total <= 0:
        return None
    half, before = total / 2, 0.0
    for low, high, n in sorted(groups, key=lambda g: g[0]):
        if before + n >= half and n > 0:
            if high is None:
                return None
            return round(low + (half - before) / n * (high - low + 1), 1)
        before += n
    return None


def ages(rows: list[dict[str, str]], keys: tuple[str, ...], date: str
         ) -> dict[tuple[str, ...], dict[str, Any]]:
    """Per place at ``date``: everyone by five-year group, and men and women.

    Both sexes and all ethnicities (``overall``) for the groups; all ages for
    the sexes. A label the reader does not know refuses the run, and so does a
    run of groups that does not start at 0 and climb without a gap to an open
    top group.
    """
    out: dict[tuple[str, ...], dict[str, Any]] = {}
    for r in rows:
        if r["date"] != date or r["ethnicity"] != "overall":
            continue
        place = tuple(r[k] for k in keys)
        unit = out.setdefault(place, {"groups": {}, "sex": {}})
        if r["age"] == "overall":
            if r["sex"] in ("male", "female"):
                unit["sex"][r["sex"]] = thousands(r["population"])
            elif r["sex"] != "both":
                raise SystemExit(f"malaysia: unknown sex category {r['sex']!r}")
            continue
        if r["sex"] != "both":
            continue
        band = age_band(r["age"])
        if band is None:
            raise SystemExit(f"malaysia: unknown age group {r['age']!r}; DOSM changed the file")
        unit["groups"][band] = thousands(r["population"])
    for place, unit in out.items():
        bands = sorted(unit["groups"])
        edge = 0
        for low, high in bands:
            if low != edge:
                raise SystemExit(f"malaysia: {place}: age groups jump to {low} at {edge}")
            edge = (high + 1) if high is not None else -1
        if edge != -1 or len(bands) != EXPECTED_GROUPS:
            raise SystemExit(f"malaysia: {place}: {len(bands)} age groups, not "
                             f"{EXPECTED_GROUPS} ending in an open one")
    return out


def age_fields(name: str, unit: dict[str, Any] | None, year: int, total: int
               ) -> dict[str, Any]:
    """median_age, sex_ratio and their notes for one place, after its checks."""
    if not unit or not total:
        return {}
    groups = [(low, high, n) for (low, high), n in unit["groups"].items()]
    aged = sum(n for _, _, n in groups)
    # 18 groups, each rounded to the nearest hundred people.
    if abs(aged - total) > max(1000, 0.01 * total):
        raise SystemExit(f"malaysia: {name}: age groups make {aged:,}, not {total:,}")
    men, women = unit["sex"].get("male"), unit["sex"].get("female")
    if not men or not women:
        raise SystemExit(f"malaysia: {name}: no male or female total")
    if abs(men + women - total) > max(200, 0.005 * total):
        raise SystemExit(f"malaysia: {name}: men {men:,} and women {women:,} "
                         f"make {men + women:,}, not {total:,}")
    median = grouped_median(groups)
    if median is None:
        raise SystemExit(f"malaysia: {name}: the middle person is in the open 85+ group")
    basis = (f"DOSM's population estimate for {year}, carried forward from the 2020 "
             f"census (OpenDOSM), not a count")
    return {
        "median_age": measure(median, unit="years", year=year, source=SOURCE),
        "median_age_note": (f"Interpolated within the five-year age group that holds "
                            f"the middle person, from {basis}. OpenDOSM publishes ages "
                            f"in five-year groups to an open 85+ and nothing finer at "
                            f"this level, each cell rounded to the nearest hundred."),
        "sex_ratio": measure(round(100 * men / women, 1), unit="males_per_100_females",
                             year=year, source=SOURCE),
        "sex_ratio_note": (f"Males per 100 females in {basis}; non-citizens are part "
                           f"of the resident population DOSM estimates."),
    }


def check_against_states(comps: dict[tuple[str, ...], dict[str, int]],
                         state_rows: list[dict[str, str]], date: str) -> None:
    """Each state's districts against the state file's own figure for that date."""
    states = {r["state"]: thousands(r["population"]) for r in state_rows
              if r["date"] == date and r["sex"] == "both" and r["age"] == "overall"
              and r["ethnicity"] == "overall"}
    if not states:
        raise SystemExit(f"malaysia: the state file has no figures for {date}")
    summed: dict[str, int] = {}
    for (state, _), counts in comps.items():
        summed[state] = summed.get(state, 0) + counts.get("__total__", 0)
    for state, total in sorted(summed.items()):
        own = states.get(state)
        if own is None:
            raise SystemExit(f"malaysia: districts of {state!r}, which the state file lacks")
        # A hundred people of rounding per district.
        if abs(total - own) > max(2000, 0.01 * own):
            raise SystemExit(f"malaysia: {state}'s districts make {total:,}, "
                             f"against its {own:,} for {date}")
    log(f"  {len(summed)} states' districts each make the state's own figure for {date}")


def build_states(rows: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    rows = rows if rows is not None else read_csv(STATE_URL)
    date, comps = compositions(rows, ("state",))
    year = int(date[:4])
    log(f"  states: {len(comps)} at {date}")
    by_age = ages(rows, ("state",), date)
    records = []
    for (state,), counts in sorted(comps.items()):
        total = check(state, counts)
        bars = shares({k: v for k, v in counts.items() if k != "__total__"}, total=total)
        records.append(record(
            f"MYS-{slug(state)}", state, level="admin1", parent="MYS", country="MYS",
            aliases=STATE_ALIASES.get(state, []),
            population=measure(total, year=year, source=SOURCE) if total else gap(NOT_AVAILABLE),
            ethnicity=bars or gap(NOT_AVAILABLE),
            ethnicity_year=dated(bars, year),
            ethnicity_note=NOTE,
            sources=[{"field": "population/ethnicity/median age/sex ratio",
                      "name": f"{SOURCE} ({year})",
                      "url": PAGES["state"], "license": LICENCE}],
            **age_fields(state, by_age.get((state,)), year, total),
        ))
    if len(records) != 16:
        raise SystemExit(f"malaysia: expected 16 states, read {len(records)}")
    return records


def build_districts(rows: list[dict[str, str]] | None = None,
                    state_rows: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    rows = rows if rows is not None else read_csv(DISTRICT_URL)
    date, comps = compositions(rows, ("state", "district"))
    year = int(date[:4])
    log(f"  districts: {len(comps)} at {date}")
    by_age = ages(rows, ("state", "district"), date)
    check_against_states(comps, state_rows if state_rows is not None
                         else read_csv(STATE_URL), date)
    records = []
    for (state, district), counts in sorted(comps.items()):
        total = check(f"{state}/{district}", counts)
        bars = shares({k: v for k, v in counts.items() if k != "__total__"}, total=total)
        records.append(record(
            f"MYS-{slug(state)}-{slug(district)}", district, level="admin2",
            parent=f"MYS-{slug(state)}", parent_name=state, country="MYS",
            aliases=DISTRICT_ALIASES.get(district, []),
            population=measure(total, year=year, source=SOURCE) if total else gap(NOT_AVAILABLE),
            ethnicity=bars or gap(NOT_AVAILABLE),
            ethnicity_year=dated(bars, year),
            ethnicity_note=NOTE,
            sources=[{"field": "population/ethnicity/median age/sex ratio",
                      "name": f"{SOURCE} ({year})",
                      "url": PAGES["district"], "license": LICENCE}],
            **age_fields(f"{state}/{district}", by_age.get((state, district)), year, total),
        ))
    if not 150 <= len(records) <= 170:
        raise SystemExit(f"malaysia: expected about 160 districts, read {len(records)}")
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="both", choices=["state", "district", "both"])
    args = ap.parse_args()
    log("malaysia: ethnicity, median age and sex ratio by state and district, OpenDOSM")
    state_rows = read_csv(STATE_URL)
    written = []
    if args.level in ("state", "both"):
        written.append(("malaysia_state.json", build_states(state_rows)))
    if args.level in ("district", "both"):
        written.append(("malaysia_district.json",
                        build_districts(read_csv(DISTRICT_URL), state_rows)))
    for name, records in written:
        aged = [r for r in records if isinstance(r.get("median_age"), dict)
                and r["median_age"].get("value") is not None]
        medians = sorted(r["median_age"]["value"] for r in aged)
        ratios = sorted(r["sex_ratio"]["value"] for r in aged)
        log(f"  {name}: {len(aged)} of {len(records)} with a median age "
            f"({medians[0]}-{medians[-1]}) and a sex ratio ({ratios[0]}-{ratios[-1]})")
        write_json(PROCESSED / name, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
