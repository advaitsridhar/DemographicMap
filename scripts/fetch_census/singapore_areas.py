#!/usr/bin/env python3
"""Singapore -- ethnicity, religion and language by planning area.

The planning-area tables come out of the census and general household survey
releases rather than the SingStat Table Builder API that ``singstat.py`` uses,
so they live as CSV extracts in ``data/raw/singapore/``:

* ethnic group, General Household Survey 2015, by planning area and subzone;
* religion, Census 2020, residents aged 15 and over;
* language most frequently spoken at home, Census 2020, residents aged 5 and over.

**Three different bases, and they are not interchangeable.** Ethnicity is every
resident in 2015; religion is residents aged 15 and over in 2020; language is
residents aged 5 and over in 2020. Each field therefore carries its own year and
its own note saying whose shares these are. Presenting them as one profile of
one population would be wrong in three directions at once, and the totals make
that visible: 3.90m, 3.46m and 3.60m for what is nominally the same country.

**"na" is not zero.** The survey suppresses small cells, and several planning
areas are industrial or military with almost nobody living in them. A suppressed
cell is read as missing, an explicit "-" as nil, and an area whose own total is
suppressed produces no record at all rather than a row of zeroes.

The religion and language releases cover 30 planning areas and bucket the rest
into "Others"; that bucket is deliberately dropped, since it corresponds to no
shape on the map.

Usage:
    python -m scripts.fetch_census.singapore_areas
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, gap, log, measure, record, shares, write_json,
)

RAW_DIR = RAW / "singapore"
ETHNICITY_CSV = RAW_DIR / "ethnicity_planning_area_ghs2015.csv"
RELIGION_CSV = RAW_DIR / "religion_planning_area_census2020.csv"
LANGUAGE_CSV = RAW_DIR / "language_planning_area_census2020.csv"

DOS = "Singapore Department of Statistics"
GHS = f"General Household Survey 2015, {DOS}"
CENSUS = f"Census of Population 2020, {DOS}"
PORTAL = "https://www.singstat.gov.sg/publications/reference/cop2020/cop2020-sr1"

# Rows that are not places.
SKIP = {"total", "others"}

# CSV column -> display label. Trailing digits are the source's footnote markers.
ETHNIC_COLUMNS = {"Chinese_Total": "Chinese", "Malays_Total": "Malay",
                  "Indians_Total": "Indian", "Others_Total": "Other"}
RELIGION_COLUMNS = {
    "Buddhism": "Buddhist", "Taoism1": "Taoist", "Islam": "Muslim",
    "Hinduism": "Hindu", "Sikhism": "Sikh",
    "Christianity_Catholic": "Catholic",
    "Christianity_OtherChristians": "Other Christian",
    "OtherReligions": "Other religion", "NoReligion": "No religion",
}
# The six top-level languages are mutually exclusive and exhaustive; Indian
# languages are split because Tamil is one of Singapore's four official ones and
# folding it into a regional bucket loses the thing worth seeing.
LANGUAGE_COLUMNS = {
    "English_Total": "English", "Mandarin_Total1": "Mandarin",
    "ChineseDialects_Total1": "Chinese dialects", "Malay_Total1": "Malay",
    "IndianLanguages_Tamil_Total1": "Tamil",
    "IndianLanguages_OtherIndianLanguages_Total1": "Other Indian languages",
    "OtherLanguages_Total1": "Other languages",
}

# The national row of each extract, as published. A file that does not reproduce
# its own headline total is not the table it claims to be.
CONTROLS = {"ethnicity": 3_902_690, "religion": 3_459_093, "language": 3_596_284}
# Ethnicity is rounded to the nearest 10 by the survey, so its parts drift from
# the total; the census counts are exact bar a unit of rounding in the release.
TOLERANCE = {"ethnicity": 60, "religion": 2, "language": 2}

NOTES = {
    "ethnicity": ("General Household Survey 2015. Singapore's CMIO classification "
                  "records a single race per person, taken from the father's; it is "
                  "an administrative category rather than a self-described one."),
    "religion": ("Census 2020, residents aged 15 and over -- not the whole "
                 "population, so these are shares of adults."),
    "language": ("Census 2020: the language most frequently spoken at home, among "
                 "residents aged 5 and over. It is the single most-used language, "
                 "not everything a person speaks -- Singapore is widely bilingual, "
                 "and the same census records second languages separately."),
}


def cell(value: str | None) -> float | None:
    """A count, or None where the release suppressed or omitted it.

    "na" is a suppressed small cell and "-" is a true nil. Reading either as
    zero would turn "we are not telling you" into "there is nobody here", which
    in a country with industrial and military planning areas is a difference
    that matters.
    """
    text = (value or "").strip()
    if text in ("", "na", "n.a.", "-"):
        return 0.0 if text == "-" else None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def read(path: Path, columns: dict[str, str], *, areas_only: bool
         ) -> tuple[dict[str, dict[str, float]], dict[str, float], float | None]:
    """(counts by area, area totals, the national total)."""
    if not path.exists():
        raise SystemExit(f"missing extract: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    missing = [c for c in columns if rows and c not in rows[0]]
    if missing:
        raise SystemExit(f"{path.name}: expected columns absent: {missing}\n"
                         f"  found: {sorted(rows[0])}")

    counts: dict[str, dict[str, float]] = {}
    totals: dict[str, float] = {}
    national: float | None = None

    for row in rows:
        name = (row.get("Number") or "").strip()
        if not name:
            continue
        if name.lower() in SKIP:
            if name.lower() == "total":
                national = cell(row.get("Total") or row.get("Total_Total"))
            continue
        # The 2015 extract interleaves subzones; only the "X- Total" rows are
        # planning areas, and everything below them is a subdivision of one.
        if areas_only:
            if not name.endswith("- Total"):
                continue
            name = name[: -len("- Total")].strip()

        total = cell(row.get("Total") or row.get("Total_Total"))
        if not total:
            continue                      # suppressed or genuinely unpopulated
        totals[name] = total
        counts[name] = {label: value for column, label in columns.items()
                        if (value := cell(row.get(column))) is not None}
    return counts, totals, national


def check(kind: str, counts: dict[str, dict[str, float]], totals: dict[str, float],
          national: float | None) -> None:
    """The national headline, then every area against its own total."""
    expected = CONTROLS[kind]
    if national is None or abs(national - expected) > TOLERANCE[kind]:
        raise SystemExit(f"{kind}: extract totals {national}, published {expected:,}")

    drift = []
    for name, parts in counts.items():
        if not parts:
            # Every category suppressed while the row total survives. Lim Chu
            # Kang, Pioneer and Tuas are industrial and military areas with
            # fewer than a hundred residents each, so the survey withholds the
            # breakdown. There is nothing to reconcile, and nothing to publish.
            continue
        summed = sum(parts.values())
        if abs(summed - totals[name]) > TOLERANCE[kind]:
            drift.append(f"{name}: parts sum to {summed:,.0f}, "
                         f"the row's own total is {totals[name]:,.0f}")
    if drift:
        raise SystemExit(f"{kind}: categories do not reconcile with their row "
                         f"totals -- refusing to emit:\n  " + "\n  ".join(drift[:10]))
    suppressed = [n for n, parts in counts.items() if not parts]
    log(f"  {kind}: {len(counts) - len(suppressed)} planning areas reconcile, "
        f"national total {national:,.0f}"
        + (f"; breakdown suppressed for {', '.join(sorted(suppressed))}"
           if suppressed else ""))


def build() -> list[dict[str, Any]]:
    ethnicity, eth_totals, eth_national = read(ETHNICITY_CSV, ETHNIC_COLUMNS,
                                               areas_only=True)
    religion, rel_totals, rel_national = read(RELIGION_CSV, RELIGION_COLUMNS,
                                              areas_only=False)
    language, lang_totals, lang_national = read(LANGUAGE_CSV, LANGUAGE_COLUMNS,
                                                areas_only=False)
    check("ethnicity", ethnicity, eth_totals, eth_national)
    check("religion", religion, rel_totals, rel_national)
    check("language", language, lang_totals, lang_national)

    out = []
    for name in sorted(set(ethnicity) | set(religion) | set(language)):
        fields: dict[str, Any] = {}
        if ethnicity.get(name):
            fields["ethnicity"] = shares(ethnicity[name], total=eth_totals[name])
            fields["ethnicity_note"] = NOTES["ethnicity"]
            fields["ethnicity_year"] = 2015
        elif name in ethnicity:
            fields["ethnicity"] = gap(
                NOT_AVAILABLE,
                f"The 2015 survey published a resident count for this area "
                f"({eth_totals[name]:,.0f}) but suppressed the ethnic breakdown, as "
                f"it does for cells too small to report without identifying people.")
        # The 2015 survey counts every resident, so its total doubles as the
        # only population figure available at this geography -- and it survives
        # even where the ethnic breakdown beneath it does not.
        if name in ethnicity:
            fields["population"] = measure(int(eth_totals[name]), year=2015,
                                           source=GHS, unit="residents")
        if name in religion:
            fields["religion"] = shares(religion[name], total=rel_totals[name])
            fields["religion_note"] = NOTES["religion"]
            fields["religion_year"] = 2020
        else:
            fields["religion"] = gap(NOT_AVAILABLE,
                                     "The Census 2020 religion release covers 30 "
                                     "planning areas and groups the remainder into "
                                     "an 'Others' bucket that matches no single area.")
        if name in language:
            fields["language"] = shares(language[name], total=lang_totals[name])
            fields["language_note"] = NOTES["language"]
            fields["language_year"] = 2020
        else:
            fields["language"] = gap(NOT_AVAILABLE,
                                     "The Census 2020 language release covers 30 "
                                     "planning areas and groups the remainder into "
                                     "an 'Others' bucket that matches no single area.")

        out.append(record(
            f"SGP-A-{name.replace(' ', '-')}", name, level="admin2", parent="SGP",
            codes={"planning_area": name},
            sources=[{"field": "ethnicity", "name": GHS, "url": PORTAL, "year": 2015},
                     {"field": "religion/language", "name": CENSUS, "url": PORTAL,
                      "year": 2020}],
            **fields))
    return out


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    rows = build()
    with_religion = sum(1 for r in rows if isinstance(r.get("religion"), list))
    log(f"  {len(rows)} planning areas, {with_religion} with religion and language")
    write_json(PROCESSED / "singapore_planning_area.json", rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
