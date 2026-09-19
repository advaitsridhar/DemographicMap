#!/usr/bin/env python3
"""Malaysia: religion by state and administrative district, MyCensus 2020.

The Department of Statistics Malaysia asked religion in the Population and
Housing Census 2020 and published the answer by state in the census's Key
Findings, but OpenDOSM's data catalogue carries no religion table: its
``population_*`` files have sex, age and ethnicity and nothing else. Where the
census's religion does reach the open store is DOSM's own Kawasanku dashboard
("my area"), built, in its own words, on MyCensus 2020, which draws a religion
bar for the country, the 16 states and 160 administrative districts from one
parquet file its metadata names (``data-gov-my/datagovmy-meta``,
``dashboards/kawasanku_admin.json``):

    https://storage.dosm.gov.my/dashboards/kawasanku_admin_barmeter.parquet
    area_type | area | chart | variable | value

The religion chart has six variables -- ``muslim``, ``buddhist``,
``christian``, ``hindu``, ``other``, ``atheist`` -- and ``value`` is an
unrounded percentage; the six sum to 100 for every area. Read on a runner
before this was written, the state rows agree to the decimal with the census
table DOSM published for the states (Johor 59.7 / 28.7 / 3.0 / 7.1, Sarawak
34.2 / 12.8 / 50.1 ...), which is how the file is known to be the 2020 census
and not the dashboard's later population estimates.

**Counts.** The dashboard publishes shares, not heads. The census's own count
tables exist only inside PDF reports, so the counts here are DOSM's unrounded
shares applied to each area's 2020 population from OpenDOSM's
``population_state`` / ``population_district`` files -- the 2020 point of
those series is the census's reference year -- and rounded. The note on every
record says so. They are as good as the shares, which is to one decimal of a
percent, and they are never presented as a count DOSM printed.

**Categories.** The census questionnaire's answers were Islam, Buddhism,
Christianity, Hinduism, other religions, no religion and unknown; the
dashboard has six, so the unknowns are not separated from the last two. They
are carried under DOSM's six labels and the note says what is pooled.

**Self-checks.** The country row must match the figures DOSM announced with
the Key Findings (Islam 63.5, Buddhism 18.7, Christianity 9.1, Hinduism 6.1,
the rest 2.7) within half a point; the states, weighted by population, must
reproduce the country row; and a state's districts, weighted, must reproduce
the state. Any of these missing is a SystemExit, because a dashboard file can
be re-based on a later estimate without changing its name.

Usage:
    python -m scripts.fetch_census.malaysia_religion
    python -m scripts.fetch_census.malaysia_religion --probe
"""

from __future__ import annotations

import argparse
import io
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, dated, gap, http_get, log, record, shares, write_json,
)
from .malaysia import (
    DISTRICT_ALIASES, DISTRICT_URL, STATE_ALIASES, STATE_URL, read_csv, slug, thousands,
)

BARMETER = "https://storage.dosm.gov.my/dashboards/kawasanku_admin_barmeter.parquet"
CALLOUT = "https://storage.dosm.gov.my/dashboards/kawasanku_admin_barmeter_callout.parquet"
PAGE = "https://open.dosm.gov.my/dashboard/kawasanku"
KEY_FINDINGS = ("https://www.dosm.gov.my/portal-main/release-content/"
                "key-findings-population-and-housing-census-of-malaysia-2020")
SOURCE = ("Department of Statistics Malaysia, Population and Housing Census 2020, "
          "religion by area as published in the Kawasanku dashboard")
LICENCE = "Creative Commons Attribution 4.0 (OpenDOSM)"
YEAR = 2020

LABELS = {
    "muslim": "Islam",
    "buddhist": "Buddhism",
    "christian": "Christianity",
    "hindu": "Hinduism",
    "other": "Other religions",
    "atheist": "No religion",
}
NOTE = ("Shares are the 2020 census's, as DOSM publishes them for each area in "
        "its Kawasanku dashboard; the counts are those unrounded shares applied "
        "to the area's 2020 census population (OpenDOSM population series) and "
        "rounded, since DOSM's count tables are printed only in PDF reports. "
        "The dashboard carries six categories where the census asked seven: "
        "answers of 'unknown' are not separated from 'Other religions' and "
        "'No religion'.")

# What DOSM announced with the Key Findings of the 2020 census (press
# statement, 14 February 2022): the four named religions, and 2.7% for all
# other answers together. The country row of the dashboard file must
# reproduce these, or the file is not the census.
PUBLISHED_NATIONAL = {"Islam": 63.5, "Buddhism": 18.7, "Christianity": 9.1, "Hinduism": 6.1}
PUBLISHED_REST = 2.7
TOLERANCE = 0.5
# The three federal territories are one district each in the population file
# and appear once, as states, in the dashboard; nothing else may be left over.
TERRITORIES = 3


def read_parquet(url: str) -> Any:
    import pyarrow.parquet as pq  # noqa: PLC0415
    blob = http_get(url, binary=True, timeout=300)
    return pq.read_table(io.BytesIO(blob)).to_pandas()


def religion_shares(rows: list[tuple[str, str, str, str, float]]
                    ) -> dict[tuple[str, str], dict[str, float]]:
    """``(area_type, area, chart, variable, value)`` rows -> per-area shares.

    Returns ``{(area_type, area): {label: pct}}`` for the religion chart only,
    refusing a variable the labels do not name and a composition that does not
    sum to 100: the file is a dashboard's, and either drift means DOSM changed
    what the chart shows.
    """
    out: dict[tuple[str, str], dict[str, float]] = {}
    for area_type, area, chart, variable, value in rows:
        if chart != "religion":
            continue
        label = LABELS.get(variable)
        if label is None:
            raise SystemExit(f"malaysia_religion: unknown religion variable {variable!r}; "
                             "DOSM changed the dashboard file")
        out.setdefault((area_type, area), {})[label] = float(value)
    for key, comp in out.items():
        total = sum(comp.values())
        if abs(total - 100.0) > 0.3:
            raise SystemExit(f"malaysia_religion: {key[1]} sums to {total:.2f}, not 100")
        if len(comp) != len(LABELS):
            raise SystemExit(f"malaysia_religion: {key[1]} has {len(comp)} categories, "
                             f"not {len(LABELS)}")
    return out


def check_national(country: dict[str, float]) -> None:
    """The country row against the figures DOSM announced."""
    for label, published in PUBLISHED_NATIONAL.items():
        got = country.get(label, 0.0)
        if abs(got - published) > TOLERANCE:
            raise SystemExit(f"malaysia_religion: national {label} {got:.2f}% is not DOSM's "
                             f"published {published}%; the file is not the 2020 census")
    rest = country.get("Other religions", 0.0) + country.get("No religion", 0.0)
    if abs(rest - PUBLISHED_REST) > TOLERANCE:
        raise SystemExit(f"malaysia_religion: national other+none {rest:.2f}% is not "
                         f"DOSM's published {PUBLISHED_REST}%")
    log("  national row matches DOSM's published 2020 figures: "
        + ", ".join(f"{k} {country.get(k, 0.0):.1f}" for k in LABELS.values()))


def check_parts(name: str, whole: dict[str, float], parts: dict[str, dict[str, float]],
                weights: dict[str, float]) -> None:
    """Parts, weighted by population, must reproduce the whole within half a point."""
    total = sum(weights[p] for p in parts)
    if not total:
        raise SystemExit(f"malaysia_religion: {name} has no weighted parts")
    for label in LABELS.values():
        summed = sum(parts[p].get(label, 0.0) * weights[p] for p in parts) / total
        if abs(summed - whole.get(label, 0.0)) > TOLERANCE:
            raise SystemExit(f"malaysia_religion: {name}: parts give {label} {summed:.2f}% "
                             f"against the whole's {whole.get(label, 0.0):.2f}%")


def population_2020(rows: list[dict[str, str]], keys: tuple[str, ...]
                    ) -> dict[tuple[str, ...], int]:
    """The 2020 (census reference year) population per place, both sexes, all ages."""
    out: dict[tuple[str, ...], int] = {}
    for r in rows:
        if (r["sex"], r["age"], r["ethnicity"]) != ("both", "overall", "overall"):
            continue
        if not r["date"].startswith(f"{YEAR}-"):
            continue
        out[tuple(r[k] for k in keys)] = thousands(r["population"])
    if not out:
        raise SystemExit(f"malaysia_religion: no {YEAR} rows in the population file")
    return out


def counts(comp: dict[str, float], population: int) -> dict[str, int]:
    return {label: int(round(pct / 100.0 * population)) for label, pct in comp.items()}


def place_districts(districts: dict[str, dict[str, float]],
                    district_pop: dict[tuple[str, ...], int],
                    ) -> tuple[dict[str, dict[str, dict[str, float]]], list[str]]:
    """The dashboard names a district without its state; the population file
    names both, and is the map. A district name the file lists under two
    states could not be told apart in the dashboard and is refused rather
    than guessed. Returns ``{state: {district: comp}}`` and the unplaced."""
    by_district: dict[str, list[str]] = {}
    for state, district in district_pop:
        by_district.setdefault(district, []).append(state)
    placed: dict[str, dict[str, dict[str, float]]] = {}
    unmatched: list[str] = []
    for district, comp in districts.items():
        homes = by_district.get(district, [])
        if len(homes) == 1:
            placed.setdefault(homes[0], {})[district] = comp
        elif len(homes) > 1:
            raise SystemExit(f"malaysia_religion: district {district!r} exists in {homes}")
        else:
            unmatched.append(district)
    return placed, sorted(unmatched)


def build_record(entity_id: str, name: str, *, level: str, parent: str,
                 parent_name: str | None, aliases: list[str], comp: dict[str, float],
                 population: int) -> dict[str, Any]:
    rows = shares(counts(comp, population), total=population)
    fields: dict[str, Any] = dict(
        aliases=aliases, country="MYS",
        religion=rows or gap(NOT_AVAILABLE),
        religion_year=dated(rows, YEAR),
        religion_note=NOTE,
        sources=[{"field": "religion", "name": f"{SOURCE} ({YEAR})", "url": PAGE,
                  "license": LICENCE},
                 {"field": "religion", "name": "DOSM, Key Findings of the Population and "
                  "Housing Census of Malaysia 2020 (the national figures the file is "
                  "checked against)", "url": KEY_FINDINGS, "license": LICENCE}],
    )
    if parent_name:
        fields["parent_name"] = parent_name
    return record(entity_id, name, level=level, parent=parent, **fields)


def build() -> list[dict[str, Any]]:
    df = read_parquet(BARMETER)
    rows = list(df[["area_type", "area", "chart", "variable", "value"]]
                .itertuples(index=False, name=None))
    comps = religion_shares(rows)
    country = [c for (t, _a), c in comps.items() if t == "country"]
    if len(country) != 1:
        raise SystemExit(f"malaysia_religion: expected one country row, read {len(country)}")
    check_national(country[0])

    state_pop = population_2020(read_csv(STATE_URL), ("state",))
    district_pop = population_2020(read_csv(DISTRICT_URL), ("state", "district"))
    states = {a: c for (t, a), c in comps.items() if t == "state"}
    districts = {a: c for (t, a), c in comps.items() if t == "district"}
    log(f"  dashboard: {len(states)} states, {len(districts)} districts; population base "
        f"{YEAR}: {len(state_pop)} states, {len(district_pop)} districts")

    missing = sorted(set(states) - {s for (s,) in state_pop})
    if missing or len(states) != 16:
        raise SystemExit(f"malaysia_religion: states without a population base: {missing}; "
                         f"{len(states)} states read")
    check_parts("Malaysia", country[0], states, {s: state_pop[(s,)] for s in states})
    log("  the 16 states, weighted, reproduce the national row")

    placed, unmatched = place_districts(districts, district_pop)
    log(f"  districts matched to a state: {sum(len(v) for v in placed.values())}; "
        f"unmatched: {unmatched}")
    if len(unmatched) > TERRITORIES:
        raise SystemExit(f"malaysia_religion: {len(unmatched)} districts are not in the "
                         f"population file: {unmatched}")

    records = []
    for state in sorted(states):
        records.append(build_record(
            f"MYS-{slug(state)}", state, level="admin1", parent="MYS", parent_name=None,
            aliases=STATE_ALIASES.get(state, []), comp=states[state],
            population=state_pop[(state,)]))
    checked = 0
    for state, members in sorted(placed.items()):
        weights = {d: district_pop[(state, d)] for d in members}
        check_parts(state, states[state], members, weights)
        checked += 1
        for district in sorted(members):
            records.append(build_record(
                f"MYS-{slug(state)}-{slug(district)}", district, level="admin2",
                parent=f"MYS-{slug(state)}", parent_name=state,
                aliases=DISTRICT_ALIASES.get(district, []), comp=members[district],
                population=weights[district]))
    log(f"  districts of {checked} states, weighted, reproduce their state")
    if not 150 <= len(records) - 16 <= 170:
        raise SystemExit(f"malaysia_religion: expected about 160 districts, "
                         f"wrote {len(records) - 16}")
    return records


def probe() -> int:
    for url in (BARMETER, CALLOUT):
        log(f"== {url}")
        df = read_parquet(url)
        log(f"   shape {df.shape}; columns {list(df.columns)}")
        for col in ("area_type", "chart", "variable"):
            if col in df.columns:
                log(f"   {col}: {sorted(map(str, df[col].dropna().unique()))}")
        sub = df[df["area_type"].astype(str) == "country"]
        for _, r in sub.iterrows():
            log("   " + " | ".join(f"{k}={r[k]}" for k in df.columns))
        di = df[df["area_type"].astype(str) == "district"]
        log(f"   district areas: {sorted(di['area'].astype(str).unique())}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="print what the dashboard files hold, and write nothing")
    args = ap.parse_args()
    if args.probe:
        return probe()
    log("malaysia_religion: religion by state and district, MyCensus 2020 via Kawasanku")
    records = build()
    write_json(PROCESSED / "malaysia_religion.json", records)
    log(f"  wrote {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
