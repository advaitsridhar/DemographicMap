#!/usr/bin/env python3
"""United Kingdom -- ONS Census 2021 via the Nomis API (local authorities).

Nomis serves the 2021 census topic summaries as machine-readable datasets:

* ``NM_2041_1`` = TS021 Ethnic group
* ``NM_2049_1`` = TS030 Religion
* ``NM_2020_1`` = TS007A Age by five-year band (used for median age)

Coverage caveat that the app displays: the 2021 census covers England and
Wales.  Scotland ran its census in **2022** (National Records of Scotland) and
Northern Ireland in 2021 through NISRA, so UK-wide comparisons mix reference
dates; those two countries have adapters of their own, ``scotland_census`` and
``northern_ireland``.  Religion is a *voluntary* question in England and Wales
-- about 6% of people left it blank -- so shares are of all usual residents
including non-responders, matching the ONS's own published percentages.

**TS021 is published at two levels in one response** -- five broad groups and
the nineteen columns of detail beneath them, each level summing to the
population -- and reading both counted every person twice. Only the leaves are
kept, by the rule all three UK adapters share in ``_shared.leaves``. TS030 is
unaffected: religion nests at one level.

Usage:
    python -m scripts.fetch_census.uk_nomis --level district
    python -m scripts.fetch_census.uk_nomis --level county
"""

from __future__ import annotations

import argparse
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, dated, gap, http_json, leaves, log, measure, record,
    shares, write_json,
)

YEAR = 2021        # England and Wales; Scotland ran 2022 and has its own adapter
BASE = "https://www.nomisweb.co.uk/api/v01/dataset"
DATASETS: dict[str, tuple[str, str, str | None]] = {
    "ethnicity": ("NM_2041_1", "TS021 Ethnic group", "c2021_eth_20"),
    "religion": ("NM_2049_1", "TS030 Religion", "c2021_religion_10"),
    # The category dimension's name is read off the answer (None), not
    # written here: it is the one key of each observation that is a census
    # classification.
    "language": ("NM_2043_1", "TS024 Main language (detailed)", None),
}
# TYPE154 = 2021 local authority districts; TYPE499 = regions; TYPE480 = countries.
DEFAULT_GEOGRAPHY = "TYPE154"
# The most cells Nomis returns an anonymous caller in one answer.
PAGE_CELLS = 25000

# Two geographies, because one is not enough to cover the shapes that exist.
#
# Nomis publishes the census for districts (TYPE154) and for counties
# (TYPE155), and geoBoundaries' UK ADM2 needs both: it draws unitary
# authorities, metropolitan and London boroughs, Scottish councils and Northern
# Irish districts -- but for shire England it draws the *county*. Read at
# districts alone, 150 of 331 rows are ONS "E07" codes with no shape of their
# own, while the counties above them have a shape and no row.
#
# Asked for rather than summed. Ukraine's oblasts are built by adding up
# rayons because nothing else was published; here the county figures are
# published, by the same office, from the same census, and a total that was
# counted beats one that was reconstructed.
LEVELS: dict[str, tuple[str, str]] = {
    "district": ("TYPE154", "uk_lad.json"),
    "county": ("TYPE155", "uk_county.json"),
    # England and Wales themselves, the map's first level. Asked for rather
    # than rolled up: the Isles of Scilly are drawn under the United Kingdom
    # rather than under England, so England's second-level shapes are one
    # short of the country, and the office publishes the country's figure.
    "nation": ("TYPE499", "uk_nation.json"),
}


# Two shapes geoBoundaries draws that no single Nomis row reaches, for two
# quite different reasons. Both leave England and Wales one child short of a
# complete set, and the roll-up fills a parent only from a complete set -- so
# between them these two rows are why the England and Wales admin1 records
# carry no composition at all.

SOURCE_RESPELLINGS = {
    # The council spells itself Rhondda Cynon Taf, and so does the boundary
    # file; Nomis writes Taff. Note which side is wrong: this is the mirror of
    # MISSPELLED in scripts/common.py, where geoBoundaries carries the bad name
    # and every correct source needs an alias to reach the shape. Here the
    # shape is right, so declaring it there would rewrite a correct Welsh name
    # into ONS's spelling and the map would start labelling it "Taff". The
    # correction belongs on the source side, which is this file.
    "Rhondda Cynon Taff": "Rhondda Cynon Taf",
}

# Northamptonshire was abolished in April 2021 and replaced by two unitary
# authorities. ONS publishes the 2021 census on the successor geography;
# geoBoundaries still draws the county, so one shape faces two rows.
#
# Summed, and legitimately so. The two unitaries partition the old county
# exactly -- no remainder, no overlap -- and 359,523 + 425,723 = 785,246 is the
# census figure for that area, so this is a complete set rather than a sample
# of one. Every category is added as a *count* and the percentages are then
# recomputed by shares(), which is not the same thing as averaging two
# percentages and would give a different answer for two areas of unequal size.
# Ukraine's oblasts are built this way for the same reason.
MERGED_AUTHORITIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "E06000061+E06000062": ("Northamptonshire", ("E06000061", "E06000062")),
}


def reconcile(table: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Apply the two declarations above to one fetched table."""
    for entry in table.values():
        entry["name"] = SOURCE_RESPELLINGS.get(entry["name"], entry["name"])
    for code, (name, parts) in MERGED_AUTHORITIES.items():
        present = [table[p] for p in parts if p in table]
        if len(present) != len(parts):
            # A partial merge would publish a county's name over a fraction of
            # its people, which is worse than leaving the shape empty.
            if present:
                log(f"  merge {name}: {len(present)} of {len(parts)} parts, skipped")
            continue
        counts: dict[str, float] = {}
        for entry in present:
            for label, value in entry["counts"].items():
                counts[label] = counts.get(label, 0.0) + value
        totals = [e["total"] for e in present]
        table[code] = {"name": name, "counts": counts,
                       "total": sum(totals) if all(t is not None for t in totals) else None}
        for part in parts:
            table.pop(part, None)
    return table


def fetch_table(dataset: str, cell: str | None, geography: str) -> dict[str, dict[str, Any]]:
    # No `select=`: that parameter switches Nomis to a flat column format and
    # empties the nested "obs" list this parser reads.  Leaving the category
    # dimension unspecified returns every category, totals included, which is
    # exactly what shares() needs.
    url = f"{BASE}/{dataset}.data.json?geography={geography}&measures=20100"
    # Nomis answers an anonymous caller at most 25,000 cells at a time, and
    # TS024's 94 languages by 330 districts is 31,020: read whole, the answer
    # stopped at the 235th district and the other 95 had no language at all.
    # So the table is read a page at a time until a page comes back empty. Not
    # until one comes back short: a page can be cut below 25,000 cells, and
    # stopping there left 95 districts with no language at all.
    observations: list[dict[str, Any]] = []
    while True:
        page = http_json(f"{url}&RecordOffset={len(observations)}", timeout=300)
        rows = page.get("obs", [])
        if not rows:
            break
        if observations and rows[0] == observations[0]:
            raise SystemExit(f"uk_nomis: {dataset}: Nomis ignored the record offset and "
                             "answered the first page again")
        observations.extend(rows)
    if len(observations) > PAGE_CELLS:
        log(f"  {dataset}: {len(observations):,} cells, read in pages")
    out: dict[str, dict[str, Any]] = {}
    for obs in observations:
        if cell is None:
            cells = [k for k in obs if k.startswith("c2021")]
            if len(cells) != 1:
                raise SystemExit(f"uk_nomis: {dataset}: no single census classification "
                                 f"among {sorted(obs)}")
            cell = cells[0]
            log(f"  {dataset}: categories are {cell}")
        code = obs["geography"]["geogcode"]
        name = obs["geography"]["description"]
        label = obs[cell]["description"]
        value = obs.get("obs_value", {}).get("value")
        if value is None:
            continue
        entry = out.setdefault(code, {"name": name, "counts": {}, "total": None})
        if label.lower().startswith("total"):
            entry["total"] = float(value)
        else:
            entry["counts"][label] = float(value)
    # TS021 is published at two levels at once and TS030 at one, so this is a
    # no-op for religion and removes five rows per district for ethnicity.
    # Without it every England and Wales record summed to 200%: Bradford
    # carried "White" 61.1% beside "White: English, Welsh, Scottish, Northern
    # Irish or British" 56.7%, which is the same people twice, and the group
    # filter counted them as two unrelated groups because neither label is in
    # the canonical index.
    for entry in out.values():
        keep = set(leaves(entry["counts"]))
        entry["counts"] = {k: v for k, v in entry["counts"].items() if k in keep}
    return out


def check_complete(tables: dict[str, dict[str, dict[str, Any]]]) -> None:
    """Every area with figures in one table has them in all three.

    A read cut short leaves the last areas of one table empty while the other
    tables have them, and the run used to write those areas with a gap marker.
    """
    filled = {field: {code for code, entry in table.items() if entry.get("counts")}
              for field, table in tables.items()}
    every = set().union(*filled.values())
    short = {field: sorted(every - codes) for field, codes in filled.items() if every - codes}
    if short:
        raise SystemExit("uk_nomis: a table was read short -- areas missing from "
                         + "; ".join(f"{field}: {len(codes)} ({', '.join(codes[:5])} ...)"
                                     for field, codes in short.items()))


def list_datasets(match: str) -> int:
    """Every dataset Nomis serves, filtered by name.

    Nomis is run for the ONS but is not only the ONS: it is the UK's shared
    labour-market and census warehouse, and which offices' tables reach it is
    not something the ONS pages say. That matters because the 43 UK shapes this
    map cannot fill are Scottish council areas and Northern Irish districts,
    whose censuses were run by NRS and NISRA -- and their own portals answer a
    JavaScript shell to a program, with the PxStat and SPARQL endpoints their
    platforms usually expose returning 404 or closing the connection.

    So before crawling two more sites, ask the warehouse this project already
    talks to whether it has them. One call lists everything it serves.
    """
    url = f"{BASE}/def.sdmx.json"
    log(f"uk_nomis: datasets matching {match!r}")
    try:
        payload = http_json(url, timeout=180)
    except Exception as err:                        # noqa: BLE001 -- reported
        log(f"  {type(err).__name__}: {err}")
        return 1
    lists = (payload.get("structure", {}).get("keyfamilies", {})
             .get("keyfamily", []))
    needle = match.lower()
    shown = 0
    for family in lists:
        name = ((family.get("name") or [{}])[0] or {}).get("value", "") \
            if isinstance(family.get("name"), list) else \
            (family.get("name") or {}).get("value", "")
        if needle and needle not in name.lower():
            continue
        log(f"  {str(family.get('id','?')):<14} {name[:120]}")
        shown += 1
    log(f"  {shown} of {len(lists)} datasets matched")
    return 0


def list_geographies() -> int:
    """Which geographies Nomis publishes TS030 for.

    150 of the 331 rows this adapter writes reach no shape, and every one of
    them is an ONS "E07" -- a non-metropolitan district sitting inside a
    county. geoBoundaries' UK ADM2 is a mixed geography: unitary authorities,
    metropolitan and London boroughs, Scottish councils and Northern Irish
    districts, but for shire England the *county*, not the districts below it.
    So those 150 rows have no shape of their own and their county has no row.

    Ukraine's oblasts were built by summing rayons and that is one way out.
    Asking Nomis for the county geography instead is a better one, if it has
    it: the same table, the geography the boundary file actually draws, and no
    figure reconstructed from parts. Whether it has it is not guessable -- the
    file names TYPE154, TYPE499 and TYPE480 and says nothing about counties --
    so this asks.
    """
    url = (f"{BASE}/{DATASETS['religion'][0]}/geography/"
           f"TYPE.def.sdmx.json")
    log(f"uk_nomis: geography types for {DATASETS['religion'][0]}")
    try:
        payload = http_json(url, timeout=120)
    except Exception as err:                        # noqa: BLE001 -- reported
        log(f"  {type(err).__name__}: {err}")
        return 1
    codes = (payload.get("structure", {}).get("codelists", {})
             .get("codelist", []))
    shown = 0
    for codelist in codes:
        for code in codelist.get("code", []):
            name = (code.get("description", {}) or {}).get("value", "")
            log(f"  {str(code.get('value','?')):<12} {name}")
            shown += 1
    if not shown:
        log(f"  nothing listed; raw: {str(payload)[:400]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", default="district", choices=list(LEVELS),
                    help="district (TYPE154) or county (TYPE155)")
    ap.add_argument("--geography", default=None,
                    help="a Nomis geography type, overriding --level")
    ap.add_argument("--datasets", default=None, metavar="TEXT",
                    help="list Nomis datasets whose name contains TEXT, and stop")
    ap.add_argument("--geographies", action="store_true",
                    help="list the geography types this dataset is published "
                         "for, and stop")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    tables: dict[str, dict[str, dict[str, Any]]] = {}
    if args.datasets is not None:
        return list_datasets(args.datasets)
    if args.geographies:
        return list_geographies()

    geography, filename = LEVELS[args.level]
    geography = args.geography or geography
    log(f"uk_nomis: {args.level} ({geography})")
    for field, (dataset, label, cell) in DATASETS.items():
        log(f"uk_nomis: {label} ({dataset})")
        tables[field] = reconcile(fetch_table(dataset, cell, geography))

    # Nomis lists Scotland and Northern Ireland among the countries and has
    # nothing for them: the 2021 census it serves is England and Wales'.
    codes = sorted(c for c in set().union(*(set(t) for t in tables.values()))
                   if any(tables[f].get(c, {}).get("counts") for f in tables))
    if args.level == "nation":
        # TYPE499 also holds England and Wales together (K04000001), which is
        # no shape; left in, its name reached England's by containment.
        codes = [c for c in codes if c[:3] in ("E92", "W92")]
    check_totals(tables)
    check_complete(tables)
    src = f"ONS Census {YEAR} (England and Wales) via Nomis"
    level = "admin1" if args.level == "nation" else "admin2"
    records: list[dict[str, Any]] = []
    for code in codes:
        eth = tables["ethnicity"].get(code, {})
        rel = tables["religion"].get(code, {})
        lang = tables["language"].get(code, {})
        name = eth.get("name") or rel.get("name") or code
        total = eth.get("total") or rel.get("total")
        merged = MERGED_AUTHORITIES.get(code)
        eth_rows = to_tenths(shares(eth.get("counts", {}), total=eth.get("total")),
                             eth.get("total"))
        rel_rows = to_tenths(shares(rel.get("counts", {}), total=rel.get("total")),
                             rel.get("total"))
        lang_rows = to_tenths(shares(language_counts(lang.get("counts", {}), code),
                                     total=lang.get("total")), lang.get("total"))
        records.append(record(
            f"GBR-{code}", name, level=level, parent="GBR",
            # A merged row is not a published unit, so it does not claim a
            # single ONS code -- it names the codes it was added up from.
            codes={"ons_codes": list(merged[1])} if merged else {"ons_code": code},
            population=measure(int(total), year=YEAR, source=src) if total else gap(NOT_AVAILABLE),
            ethnicity=eth_rows or gap(NOT_AVAILABLE),
            ethnicity_year=dated(eth_rows, YEAR),
            ethnicity_note=f"ONS {YEAR} ethnic group classification (TS021), England and Wales.",
            religion=rel_rows or gap(NOT_AVAILABLE),
            religion_year=dated(rel_rows, YEAR),
            religion_note=(f"ONS {YEAR} religion question (TS030) is voluntary; 'Not answered' is "
                           "reported as its own category rather than excluded."),
            language=lang_rows or gap(NOT_AVAILABLE),
            language_year=dated(lang_rows, YEAR),
            language_note=language_note(code),
            sources=[{"field": "ethnicity/religion/language", "name": src,
                      "url": f"{BASE}/{DATASETS['ethnicity'][0]}.data.json",
                      "license": "Open Government Licence v3.0"}],
        ))
    unplaced = unplaced_languages(records)
    if unplaced:
        log(f"  language labels the group tree does not place: {unplaced}")
    write_json(args.out or PROCESSED / filename, records)
    log(f"  {len(records)} records")
    log(f"  {len(records)} {'nation' if level == 'admin1' else 'local authority'} records")
    return 0


def to_tenths(rows: list[dict[str, Any]], total: float | None) -> list[dict[str, Any]]:
    """Re-round shares to one decimal by largest remainder.

    TS024 has some ninety languages, and in most districts sixty or seventy of
    them are each well under 0.05% -- a dozen Latvian speakers in Hartlepool.
    Rounded one by one they all print as 0.0, and the column added to 99.2 to
    99.5 where the counts add to the district's total exactly: 96 council
    areas drew a "not accounted for" sliver the census does not have.

    Largest remainder keeps every share within a tenth of its exact value and
    makes the tenths add to what the counts add to -- 100.0 when they are the
    whole universe, and a real shortfall, if a table ever had one, is kept
    (the target is the counts' own sum, not 100). Counts are untouched.
    """
    if not rows or not total:
        return rows
    exact = [1000.0 * row["count"] / total for row in rows]
    floors = [int(e) for e in exact]
    target = round(1000.0 * sum(row["count"] for row in rows) / total)
    order = sorted(range(len(rows)), key=lambda i: (-(exact[i] - floors[i]), rows[i]["group"]))
    for i in order[:max(0, target - sum(floors))]:
        floors[i] += 1
    out = [dict(row, pct=floors[i] / 10) for i, row in enumerate(rows)]
    out.sort(key=lambda r: (-r["pct"], r["group"]))
    return out


def check_totals(tables: dict[str, dict[str, dict[str, Any]]]) -> None:
    """Every composition's categories must make its published total.

    Ethnicity and language are read at their leaves, religion at its one
    level; a set that misses or doubles a group stops the run here rather
    than reaching the map as 93% or 200% of an area.
    """
    for field, table in tables.items():
        for code, entry in table.items():
            total, made = entry.get("total"), sum(entry.get("counts", {}).values())
            if total and abs(made - total) > 0.005 * total:
                raise SystemExit(f"uk_nomis: {entry['name']} ({code}) {field}: categories make "
                                 f"{made:,.0f} against the published {total:,.0f}")


# TS024's leaves under the names the rest of this map uses. "Other European
# language (EU): Polish" is Polish; a residual inside a family ("Any other
# South Asian language") keeps its family, which is all it says. Several
# residuals of one kind become one label and their counts are added.
LANGUAGE_RESPELLINGS = {
    "Gaelic (Irish)": "Irish",
    "Gaelic (Scottish)": "Scottish Gaelic",
    "Gaelic (Not otherwise specified)": "Gaelic (not otherwise specified)",
    "Nepalese": "Nepali",
    "English-based Caribbean Creole": "Caribbean Creole",
    "All other Chinese": "Other Chinese",
    "Any other European language (EU)": "Other European language",
    "Any other Eastern European language (non EU)": "Other European language",
    "Northern European language (non EU)": "Other European language",
    "Any other Nigerian language": "Other African language",
    "Any other West African language": "Other African language",
    # ONS's "Other language: North or South American language" is the
    # Americas' indigenous languages (Quechua, Guarani, Nahuatl and the rest).
    "North or South American language": "Indigenous American languages",
}


def language_label(label: str, code: str) -> str:
    if label.startswith("English (English or Welsh in Wales)"):
        # In Wales the question offered "English or Welsh" as one answer, so
        # the two are not separable there; in England it is English.
        return "English or Welsh" if code.startswith("W") else "English"
    if label.startswith("Welsh or Cymraeg"):
        return "Welsh"
    detail = label.split(":", 1)[1].strip() if ":" in label else label.strip()
    detail = LANGUAGE_RESPELLINGS.get(detail, detail)
    if detail.startswith("Any other ") or detail.startswith("All other "):
        detail = "Other " + detail.split(" ", 2)[2]
    return detail


def language_counts(counts: dict[str, float], code: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for label, value in counts.items():
        key = language_label(label, code)
        out[key] = out.get(key, 0.0) + value
    return out


def language_note(code: str) -> str:
    note = (f"ONS {YEAR} main language (TS024, detailed), of usual residents aged 3 and "
            "over: the one language each person names as their main one.")
    if code.startswith("W"):
        note += (" In Wales the answer 'English or Welsh' was one box, so the census does "
                 "not separate the two there; Welsh ability is a separate question.")
    return note


def unplaced_languages(records: list[dict[str, Any]]) -> list[str]:
    try:
        import group_tree                              # scripts/ is on the path
    except Exception:                                  # noqa: BLE001 -- a check only
        return []
    labels = {g["group"] for r in records if isinstance(r.get("language"), list)
              for g in r["language"]}
    return sorted(label for label in labels if group_tree.parent_of("language", label) is None)


if __name__ == "__main__":
    raise SystemExit(main())
