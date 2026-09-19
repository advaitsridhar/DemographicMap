#!/usr/bin/env python3
"""Singapore -- ethnicity, religion and language by planning area and region.

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
cell is read as missing, an explicit "-" as nil. An area whose own total is
suppressed gets a record all the same, because the boundary file draws it: the
record says that no count is published and why, and carries no figure.

The religion and language releases cover 30 planning areas and bucket the rest
into "Others"; that bucket corresponds to no shape and is not joined to one,
but its size is read, because it is the honest measure of what the 25 areas
outside the release hold between them.

**The five regions are summed from their areas.** SingStat's annual series
(``singstat.py``) gives each region a population and no composition, and the
build's own roll-up refuses to sum the areas because the uninhabited ones carry
no figures and a sum over part of a territory is refused on principle. Here the
partition is known: the URA's Master Plan says which areas make each region,
the boundary file's geometry places the 55 shapes the same way, and the area
totals reconcile with the national row, so an area with no published count
holds nobody the survey counted. Each region's figure is a sum of the published
area rows, and its note names what was summed and what the release left out.

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

# The URA's five planning regions and the 55 planning areas each contains, as
# the Master Plan draws them and as the boundary file's geometry places the
# second-level shapes. Declared rather than inferred so that an area the
# extracts spell differently is refused instead of quietly left out of a sum.
REGIONS: dict[str, tuple[str, ...]] = {
    "Central Region": (
        "Bishan", "Bukit Merah", "Bukit Timah", "Downtown Core", "Geylang",
        "Kallang", "Marina East", "Marina South", "Marine Parade", "Museum",
        "Newton", "Novena", "Orchard", "Outram", "Queenstown", "River Valley",
        "Rochor", "Singapore River", "Southern Islands", "Straits View",
        "Tanglin", "Toa Payoh"),
    "East Region": (
        "Bedok", "Changi", "Changi Bay", "Pasir Ris", "Paya Lebar", "Tampines"),
    "North Region": (
        "Central Water Catchment", "Lim Chu Kang", "Mandai", "Sembawang",
        "Simpang", "Sungei Kadut", "Woodlands", "Yishun"),
    "North-East Region": (
        "Ang Mo Kio", "Hougang", "North-Eastern Islands", "Punggol", "Seletar",
        "Sengkang", "Serangoon"),
    "West Region": (
        "Boon Lay", "Bukit Batok", "Bukit Panjang", "Choa Chu Kang", "Clementi",
        "Jurong East", "Jurong West", "Pioneer", "Tengah", "Tuas",
        "Western Islands", "Western Water Catchment"),
}
AREA_REGION = {area: region for region, areas in REGIONS.items() for area in areas}

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
# How far the area rows may fall short of the national row, together, before
# the regions are refused: past this the areas do not partition the country
# and no region can be known complete. Within it, a shortfall beyond the
# rounding tolerance is written into each region's note in one sentence.
PARTITION_LIMIT = 0.01

YEAR = {"ethnicity": 2015, "religion": 2020, "language": 2020}
SOURCE = {"ethnicity": GHS, "religion": CENSUS, "language": CENSUS}

# What each figure is, in one sentence, for the area rows.
NOTES = {
    "ethnicity": ("General Household Survey 2015, all residents. CMIO records "
                  "one administrative race per person, taken from the father's."),
    "religion": ("Census 2020, residents aged 15 and over -- shares of adults, "
                 "not of the whole population."),
    "language": ("Census 2020, the language most often spoken at home by "
                 "residents aged 5 and over -- one language per person, in a "
                 "widely bilingual country."),
}
# The same, for a region summed from its areas.
BASIS = {
    "ethnicity": "residents",
    "religion": "residents aged 15 and over, so shares of adults",
    "language": "residents aged 5 and over, the language most often spoken at home",
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


class Table:
    """One extract: counts by area, each area's own total, the national row,
    and the size of the "Others" row where the release has one."""

    def __init__(self) -> None:
        self.counts: dict[str, dict[str, float]] = {}
        self.totals: dict[str, float] = {}
        self.national: float | None = None
        self.others: float | None = None

    def listed(self, name: str) -> bool:
        """The release gives this area a row with a count of its own."""
        return name in self.totals


def read(path: Path, columns: dict[str, str], *, areas_only: bool) -> Table:
    if not path.exists():
        raise SystemExit(f"missing extract: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    missing = [c for c in columns if rows and c not in rows[0]]
    if missing:
        raise SystemExit(f"{path.name}: expected columns absent: {missing}\n"
                         f"  found: {sorted(rows[0])}")

    table = Table()
    for row in rows:
        name = (row.get("Number") or "").strip()
        if not name:
            continue
        total_cell = row.get("Total") or row.get("Total_Total")
        if name.lower() in SKIP:
            if name.lower() == "total":
                table.national = cell(total_cell)
            else:
                table.others = cell(total_cell)
            continue
        # The 2015 extract interleaves subzones; only the "X- Total" rows are
        # planning areas, and everything below them is a subdivision of one.
        if areas_only:
            if not name.endswith("- Total"):
                continue
            name = name[: -len("- Total")].strip()

        total = cell(total_cell)
        if not total:
            continue                      # suppressed or genuinely unpopulated
        table.totals[name] = total
        table.counts[name] = {label: value for column, label in columns.items()
                              if (value := cell(row.get(column))) is not None}

    unknown = sorted(set(table.totals) - set(AREA_REGION))
    if unknown:
        raise SystemExit(f"{path.name}: areas in no declared region: {unknown}. "
                         f"A renamed or new planning area must be placed in "
                         f"REGIONS before it can be summed into one.")
    return table


def check(kind: str, table: Table) -> None:
    """The national headline, then every area against its own total."""
    expected = CONTROLS[kind]
    national = table.national
    if national is None or abs(national - expected) > TOLERANCE[kind]:
        raise SystemExit(f"{kind}: extract totals {national}, published {expected:,}")

    drift = []
    for name, parts in table.counts.items():
        if not parts:
            # Every category suppressed while the row total survives. Lim Chu
            # Kang, Pioneer and Tuas are industrial and military areas with
            # fewer than a hundred residents each, so the survey withholds the
            # breakdown. There is nothing to reconcile, and nothing to publish.
            continue
        summed = sum(parts.values())
        if abs(summed - table.totals[name]) > TOLERANCE[kind]:
            drift.append(f"{name}: parts sum to {summed:,.0f}, "
                         f"the row's own total is {table.totals[name]:,.0f}")
    if drift:
        raise SystemExit(f"{kind}: categories do not reconcile with their row "
                         f"totals -- refusing to emit:\n  " + "\n  ".join(drift[:10]))
    suppressed = [n for n, parts in table.counts.items() if not parts]
    log(f"  {kind}: {len(table.counts) - len(suppressed)} planning areas reconcile, "
        f"national total {national:,.0f}"
        + (f"; breakdown suppressed for {', '.join(sorted(suppressed))}"
           if suppressed else ""))


def partition_gap(kind: str, table: Table) -> float:
    """What the area rows (and the Others row) fall short of the national row by.

    This is what makes a region sum complete: if the listed areas account for
    everyone the release counted, an area with no row holds nobody it counted,
    and each region's listed areas are all of that region there is to sum.
    Past PARTITION_LIMIT the areas do not partition the country and the regions
    are refused; within it, a gap beyond the rounding tolerance is said in the
    note rather than hidden or refused over.
    """
    national = table.national or 0.0
    accounted = sum(table.totals.values()) + (table.others or 0.0)
    gap_ = national - accounted
    if abs(gap_) > PARTITION_LIMIT * national:
        raise SystemExit(
            f"{kind}: the area rows account for {accounted:,.0f} of the national "
            f"{national:,.0f}; short by {gap_:,.0f}, so the areas do not partition "
            f"the country and no region can be summed from them")
    return gap_


def area_fields(name: str, kind: str, table: Table, ghs: Table) -> dict[str, Any]:
    """The field, its note and year for one area -- a composition or a stated gap."""
    field: dict[str, Any] = {}
    parts = table.counts.get(name)
    if parts:
        field[kind] = shares(parts, total=table.totals[name])
        field[f"{kind}_note"] = NOTES[kind]
        field[f"{kind}_year"] = YEAR[kind]
        return field
    if table.listed(name):
        # A count but no breakdown: the cell is too small to publish.
        field[kind] = gap(
            NOT_AVAILABLE,
            f"The {YEAR[kind]} {'survey' if kind == 'ethnicity' else 'census'} "
            f"counted {table.totals[name]:,.0f} residents here, too few for the "
            f"Department of Statistics to publish a breakdown without "
            f"identifying people.")
        return field
    if kind != "ethnicity" and ghs.listed(name):
        # Populated, and outside the 30 areas the 2020 release lists: its
        # people are inside the release's Others row, which no shape draws.
        n_others = len([a for a in AREA_REGION if not table.listed(a)])
        field[kind] = gap(
            NOT_AVAILABLE,
            f"Census 2020 publishes {kind} for the 30 largest planning areas "
            f"only; this one ({ghs.totals[name]:,.0f} residents in 2015) is among "
            f"the {n_others} it folds into an 'Others' row"
            + (f" of {table.others:,.0f} {BASIS[kind].split(',')[0]}."
               if table.others else "."))
        return field
    # No count anywhere: uninhabited, or too few residents to report.
    field[kind] = gap(NOT_AVAILABLE, UNCOUNTED)
    return field


UNCOUNTED = ("No resident count is published for this area: the General "
             "Household Survey 2015 marks it 'na' and the Census 2020 planning-area "
             "tables do not list it, which is how the Department of Statistics "
             "writes an area with nobody living in it, or too few to report.")


def area_rows(tables: dict[str, Table]) -> list[dict[str, Any]]:
    ghs = tables["ethnicity"]
    out = []
    for name in sorted(AREA_REGION):
        fields: dict[str, Any] = {}
        for kind, table in tables.items():
            fields.update(area_fields(name, kind, table, ghs))
        # The 2015 survey counts every resident, so its total doubles as the
        # only population figure available at this geography -- and it survives
        # even where the ethnic breakdown beneath it does not.
        if ghs.listed(name):
            fields["population"] = measure(int(ghs.totals[name]), year=2015,
                                           source=GHS, unit="residents")
        else:
            fields["population"] = gap(NOT_AVAILABLE, UNCOUNTED)
        out.append(record(
            f"SGP-A-{name.replace(' ', '-')}", name, level="admin2", parent="SGP",
            codes={"planning_area": name, "planning_region": AREA_REGION[name]},
            sources=[{"field": "ethnicity/population", "name": GHS, "url": PORTAL,
                      "year": 2015},
                     {"field": "religion/language", "name": CENSUS, "url": PORTAL,
                      "year": 2020}],
            **fields))
    return out


def names(items: list[str]) -> str:
    items = sorted(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def share_text(part: float, whole: float) -> str:
    """A share to one decimal, or 'under 0.1%' rather than a misleading 0.0%."""
    pct = 100.0 * part / whole if whole else 0.0
    return f"{pct:.1f}%" if pct >= 0.05 else "under 0.1%"


def region_field(region: str, kind: str, table: Table, ghs: Table,
                 short: float) -> dict[str, Any]:
    """One region's composition summed from its areas' published rows, with a
    note that says what was summed and what the release left out."""
    areas = REGIONS[region]
    summed = [a for a in areas if table.counts.get(a)]
    withheld = [a for a in areas if table.listed(a) and not table.counts.get(a)]
    unlisted = [a for a in areas if not table.listed(a)]
    if not summed:
        return {kind: gap(NOT_AVAILABLE, f"No planning area of this region "
                                         f"has a published {kind} row.")}

    counts: dict[str, float] = {}
    for area in summed:
        for group, value in table.counts[area].items():
            counts[group] = counts.get(group, 0.0) + value
    # The base is the areas' own totals, not the sum of their parts: a
    # suppressed cell (Museum's Malays) is still people in the region.
    base = sum(table.totals[a] for a in summed + withheld)

    sentences = [
        f"Summed from the {SOURCE[kind].split(',')[0]} rows of the "
        f"{len(summed)} planning areas it lists for this region: "
        f"{base:,.0f} {BASIS[kind]}."]
    # What the sum leaves out, and how much of the region that is. Two
    # different things: an area the survey counted and folded into 'Others',
    # and an area with no count at all.
    folded = [a for a in unlisted if ghs.listed(a)] if kind != "ethnicity" else []
    empty = [a for a in unlisted if a not in folded]
    if withheld:
        sentences.append(
            f"{names(withheld)} ({sum(table.totals[a] for a in withheld):,.0f} "
            f"residents{' together' if len(withheld) > 1 else ''}) "
            f"{'has' if len(withheld) == 1 else 'have'} a "
            f"count but no published breakdown, so {'it is' if len(withheld) == 1 else 'they are'} "
            f"in the base and in no group.")
    if folded:
        held = sum(ghs.totals[a] for a in folded)
        region_2015 = sum(ghs.totals[a] for a in areas if ghs.listed(a))
        sentences.append(
            f"The census folds {names(folded)} into an 'Others' row that cannot "
            f"be split by region, so {'it is' if len(folded) == 1 else 'they are'} "
            f"not included: {held:,.0f} residents in 2015, "
            f"{share_text(held, region_2015)} of the region.")
    if empty:
        sentences.append(f"{names(empty)} {'has' if len(empty) == 1 else 'have'} "
                         f"no published residents.")
    if abs(short) > TOLERANCE[kind]:
        sentences.append(f"Nationally the area rows fall {short:,.0f} short of "
                         f"the published total, which is unexplained.")
    return {kind: shares(counts, total=base),
            f"{kind}_note": " ".join(sentences),
            f"{kind}_year": YEAR[kind]}


def region_rows(tables: dict[str, Table], short: dict[str, float]
                ) -> list[dict[str, Any]]:
    ghs = tables["ethnicity"]
    out = []
    for region in sorted(REGIONS):
        fields: dict[str, Any] = {}
        for kind, table in tables.items():
            fields.update(region_field(region, kind, table, ghs, short[kind]))
        # No population: SingStat's own series (singstat.py) publishes one for
        # each region, and a 2015 survey base beside it would read as a rival.
        out.append(record(
            f"SGP-R-{region.replace(' ', '-')}", region, level="admin1", parent="SGP",
            codes={"planning_region": region},
            sources=[{"field": "ethnicity", "name": GHS, "url": PORTAL, "year": 2015,
                      "note": "Summed from the planning-area rows."},
                     {"field": "religion/language", "name": CENSUS, "url": PORTAL,
                      "year": 2020, "note": "Summed from the planning-area rows."}],
            **fields))
    return out


def build() -> list[dict[str, Any]]:
    tables = {
        "ethnicity": read(ETHNICITY_CSV, ETHNIC_COLUMNS, areas_only=True),
        "religion": read(RELIGION_CSV, RELIGION_COLUMNS, areas_only=False),
        "language": read(LANGUAGE_CSV, LANGUAGE_COLUMNS, areas_only=False),
    }
    short = {}
    for kind, table in tables.items():
        check(kind, table)
        short[kind] = partition_gap(kind, table)
        log(f"  {kind}: {len(table.totals)} areas"
            + (f" and an Others row of {table.others:,.0f}" if table.others else "")
            + f" account for the national row to within {short[kind]:,.0f}")
    return area_rows(tables) + region_rows(tables, short)


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    rows = build()
    areas = [r for r in rows if r["level"] == "admin2"]
    regions = [r for r in rows if r["level"] == "admin1"]
    with_religion = sum(1 for r in areas if isinstance(r.get("religion"), list))
    with_ethnicity = sum(1 for r in areas if isinstance(r.get("ethnicity"), list))
    log(f"  {len(areas)} planning areas, {with_ethnicity} with ethnicity, "
        f"{with_religion} with religion and language; {len(regions)} regions "
        f"summed from them")
    write_json(PROCESSED / "singapore_planning_area.json", rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
