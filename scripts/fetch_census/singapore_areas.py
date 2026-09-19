#!/usr/bin/env python3
"""Singapore -- ethnicity, religion and language by planning area and region.

The Department of Statistics publishes the census's planning-area tables on
**data.gov.sg**, whose datastore serves them as rows to anyone; its own site,
``singstat.gov.sg``, answers an automated reader 403, and the Table Builder API
that ``singstat.py`` uses carries nothing below the five planning regions.
``--fetch`` reads each table into a CSV in ``data/raw/singapore/`` and the
adapter reads the CSVs, so a build without network still runs and what was
served is committed beside the code that read it:

* ethnic group, Census 2020, by planning area and subzone -- all 55 areas;
* religion, Census 2020, residents aged 15 and over -- 30 areas;
* language most frequently spoken at home, Census 2020, aged 5 and over -- 30;
* religion and language, Census 2010 -- 35 areas each, five of which the 2020
  release folds away.

**Three different bases, and they are not interchangeable.** Ethnicity is every
resident; religion is residents aged 15 and over; language is residents aged 5
and over. Each field carries its own note saying whose shares these are, and
the totals make the difference visible: 4.04m, 3.46m and 3.60m for what is
nominally the same country.

**"-" is not zero.** The census prints "-" for nil or negligible and the survey
marks a suppressed cell "na"; several planning areas are industrial or military
with almost nobody living in them. An area whose every group is "-" while its
own total survives -- Boon Lay's 40 residents, Tengah's 10 -- has a count and a
withheld breakdown, not forty people of no race. An area whose total itself is
"-" gets a record all the same, because the boundary file draws it: the record
says that no count is published and why, and carries no figure.

The 2020 religion and language releases cover 30 planning areas and bucket the
rest into "Others"; that bucket corresponds to no shape and is not joined to
one, but its size is read, because it is the honest measure of what the areas
outside the release hold between them. Five of those areas -- Changi, Mandai,
Newton, Rochor, Singapore River -- had a row of their own in the 2010 census,
and a decade-old count of a place is a count, stamped 2010, where the newer
release gives nothing at all.

**The five regions are summed from their areas.** SingStat's annual series
(``singstat.py``) gives each region a population and no composition, and the
build's own roll-up refuses to sum the areas because the uninhabited ones carry
no figures and a sum over part of a territory is refused on principle. Here the
partition is known: the URA's Master Plan says which areas make each region,
the boundary file's geometry places the 55 shapes the same way, and the area
totals reconcile with the national row, so an area with no published count
holds nobody the census counted. Each region's figure is a sum of the published
area rows -- the 2020 ones only, so a region is one census -- and its note
names what was summed and what the release left out.

Usage:
    python -m scripts.fetch_census.singapore_areas
    python -m scripts.fetch_census.singapore_areas --fetch-only
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, gap, log, measure, record, shares, write_json,
)
from common import http_get  # noqa: E402

RAW_DIR = RAW / "singapore"
ETHNICITY_CSV = RAW_DIR / "ethnicity_planning_area_census2020.csv"
RELIGION_CSV = RAW_DIR / "religion_planning_area_census2020.csv"
LANGUAGE_CSV = RAW_DIR / "language_planning_area_census2020.csv"
RELIGION_2010_CSV = RAW_DIR / "religion_planning_area_census2010.csv"
LANGUAGE_2010_CSV = RAW_DIR / "language_planning_area_census2010.csv"

# The three fields the map carries, and for two of them the older census
# table that lists a few areas the 2020 release folds into "Others".
MAIN = ("ethnicity", "religion", "language")
FALLBACK = {"religion": "religion_2010", "language": "language_2010"}

# Where the extracts come from. singstat.gov.sg answers an automated reader
# 403, but the Department publishes the same census tables on data.gov.sg,
# whose datastore serves them as rows without a key. ``--fetch`` reads each
# table listed here into its CSV, paging 500 rows at a time, and the CSV is
# what the adapter reads afterwards -- so a build without network still runs,
# and what was read is committed beside the code that read it.
DATAGOVSG = "https://data.gov.sg/api/action/datastore_search"
DATAGOVSG_PAGE = "https://data.gov.sg/datasets/{id}/view"
DATASETS: dict[str, tuple[str, Path]] = {
    # Resident Population by Planning Area/Subzone of Residence, Ethnic Group
    # and Sex (Census of Population 2020): every area and subzone.
    "ethnicity": ("d_e7ae90176a68945837ad67892b898466",
                  RAW_DIR / "ethnicity_planning_area_census2020.csv"),
    # Resident Population Aged 15 Years and Over by Planning Area of Residence
    # and Religion (Census of Population 2020).
    "religion": ("d_a58564fbed922609a0f79af96069dd9b", RELIGION_CSV),
    # Resident Population Aged 5 Years and Over by Planning Area of Residence
    # and Language Most / Second Most Frequently Spoken at Home (Census 2020).
    "language": ("d_21f546492a87dec38391fc72eb4c7890", LANGUAGE_CSV),
    # The 2010 census's religion and language tables by planning area list a
    # few more areas than the 2020 release does (37 rows against 32), so they
    # are fetched beside it to see which, and whether an area the 2020 release
    # folds into "Others" had a row of its own a decade earlier.
    "religion_2010": ("d_d4be7f8ba23ba93e5d59564d1dfb5eaa", RELIGION_2010_CSV),
    "language_2010": ("d_c3ed3269adea97f53092d70c4d6d9682", LANGUAGE_2010_CSV),
}
# The key data.gov.sg issues, under whichever name the workflow stores it. The
# datastore answers without one; it is sent when present and never printed.
KEY_VARS = ("DEMOGRAPHICMAP", "DATA_GOV_SG_KEY", "DATAGOVSG_API_KEY",
            "DATA_GOV_SG_API_KEY", "DATAGOVSG_KEY", "DATA_GOV_SG_TOKEN")

DOS = "Singapore Department of Statistics"
CENSUS = f"Census of Population 2020, {DOS}"
CENSUS_2010 = f"Census of Population 2010, {DOS}"
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
# The 2010 table prints the same columns without the footnote marker.
RELIGION_2010_COLUMNS = {("Taoism" if c == "Taoism1" else c): label
                         for c, label in RELIGION_COLUMNS.items()}
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
LANGUAGE_2010_COLUMNS = {
    "English": "English", "Mandarin": "Mandarin", "ChineseDialects": "Chinese dialects",
    "Malay": "Malay", "Tamil": "Tamil", "OtherIndianLanguages": "Other Indian languages",
    "Others": "Other languages",
}

# The national row of each extract, as published. A file that does not reproduce
# its own headline total is not the table it claims to be.
CONTROLS = {"ethnicity": 4_044_210, "religion": 3_459_093, "language": 3_596_284,
            "religion_2010": 3_105_748, "language_2010": 3_399_054}
# The census rounds its planning-area and subzone counts to the nearest 10, so
# an area's parts drift from its total; the religion and language counts are
# exact bar a unit of rounding in the release.
TOLERANCE = {"ethnicity": 60, "religion": 2, "language": 2,
             "religion_2010": 10, "language_2010": 10}
# How far the area rows may fall short of the national row, together, before
# the regions are refused: past this the areas do not partition the country
# and no region can be known complete. Within it, a shortfall beyond the
# rounding tolerance is written into each region's note in one sentence.
PARTITION_LIMIT = 0.01

YEAR = {"ethnicity": 2020, "religion": 2020, "language": 2020,
        "religion_2010": 2010, "language_2010": 2010}
SOURCE = {"ethnicity": CENSUS, "religion": CENSUS, "language": CENSUS,
          "religion_2010": CENSUS_2010, "language_2010": CENSUS_2010}

# What each figure is, in one sentence, for the area rows.
NOTES = {
    "ethnicity": ("Census 2020, all residents. CMIO records one administrative "
                  "race per person, taken from the father's."),
    "religion": ("Census 2020, residents aged 15 and over -- shares of adults, "
                 "not of the whole population."),
    "language": ("Census 2020, the language most often spoken at home by "
                 "residents aged 5 and over -- one language per person, in a "
                 "widely bilingual country."),
    "religion_2010": ("Census 2010, residents aged 15 and over -- shares of "
                      "adults. The 2020 release folds this area into its "
                      "'Others' row, so the last census that listed it is used."),
    "language_2010": ("Census 2010, the language most often spoken at home by "
                      "residents aged 5 and over. The 2020 release folds this "
                      "area into its 'Others' row, so the last census that "
                      "listed it is used."),
}
# The same, for a region summed from its areas.
BASIS = {
    "ethnicity": "residents",
    "religion": "residents aged 15 and over, so shares of adults",
    "language": "residents aged 5 and over, the language most often spoken at home",
}


def fetch_extract(dataset_id: str, path: Path) -> int:
    """Read one datastore table into a CSV, every row, columns as served."""
    key = next((os.environ[name] for name in KEY_VARS if os.environ.get(name)), None)
    headers = {"x-api-key": key} if key else None
    page, offset, fields, records = 500, 0, None, []
    while True:
        url = f"{DATAGOVSG}?resource_id={dataset_id}&limit={page}&offset={offset}"
        body = http_get(url, cache=False, headers=headers)
        payload = json.loads(body)
        if not payload.get("success"):
            raise SystemExit(f"data.gov.sg refused {dataset_id}: {str(payload)[:200]}")
        result = payload["result"]
        if fields is None:
            fields = [f["id"] for f in result.get("fields", []) if f.get("id") != "_id"]
        batch = result.get("records") or []
        records.extend(batch)
        if len(batch) < page or len(records) >= int(result.get("total") or 0):
            break
        offset += page
    if not fields or not records:
        raise SystemExit(f"data.gov.sg served no rows for {dataset_id}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    log(f"  {path.name}: {len(records)} rows, {len(fields)} columns, from "
        f"data.gov.sg {dataset_id}")
    return len(records)


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
        # The ethnic-group table interleaves subzones; only the "X- Total"
        # rows are planning areas, and everything below one is part of it.
        if areas_only:
            if not name.endswith("- Total"):
                continue
            name = name[: -len("- Total")].strip()

        total = cell(total_cell)
        if not total:
            continue                      # suppressed or genuinely unpopulated
        table.totals[name] = total
        parts = {label: value for column, label in columns.items()
                 if (value := cell(row.get(column))) is not None}
        # The census prints "-" for nil or negligible. Where an area has a
        # total and every group is "-" -- Boon Lay's 40 residents, Tengah's
        # 10 -- that is a breakdown withheld, not forty people of no race,
        # and the area keeps its count and no composition.
        if parts and not any(parts.values()):
            parts = {}
        table.counts[name] = parts

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


def area_fields(name: str, kind: str, tables: dict[str, Table]) -> dict[str, Any]:
    """The field, its note and year for one area -- a composition or a stated gap."""
    table, people = tables[kind], tables["ethnicity"]
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
            f"The {YEAR[kind]} census counted {table.totals[name]:,.0f} residents "
            f"here, too few for the Department of Statistics to publish a "
            f"breakdown without identifying people.")
        return field
    if kind != "ethnicity":
        # Outside the 30 areas the 2020 release lists. The 2010 census listed
        # five more (Changi, Mandai, Newton, Rochor, Singapore River), and a
        # decade-old count of an area is a count, dated, where the newer
        # release gives nothing at all.
        older = tables.get(FALLBACK[kind])
        if older is not None and older.counts.get(name):
            back = FALLBACK[kind]
            field[kind] = shares(older.counts[name], total=older.totals[name])
            field[f"{kind}_note"] = NOTES[back]
            field[f"{kind}_year"] = YEAR[back]
            return field
        if people.listed(name):
            # Populated, and in no release's own row: its people are inside
            # the 2020 release's Others row, which no shape draws.
            n_others = len([a for a in AREA_REGION if not table.listed(a)])
            field[kind] = gap(
                NOT_AVAILABLE,
                f"Census 2020 publishes {kind} for the 30 largest planning areas "
                f"only; this one ({people.totals[name]:,.0f} residents in 2020) is "
                f"among the {n_others} it folds into an 'Others' row"
                + (f" of {table.others:,.0f} {BASIS[kind].split(',')[0]}."
                   if table.others else ".")
                + " No earlier census listed it either.")
            return field
    # No count anywhere: uninhabited, or too few residents to report.
    field[kind] = gap(NOT_AVAILABLE, UNCOUNTED)
    return field


UNCOUNTED = ("No resident count is published for this area: the Census 2020 "
             "planning-area table marks it '-' (nil or negligible) and the "
             "religion and language tables do not list it, which is how the "
             "Department of Statistics writes an area with nobody living in it, "
             "or too few to report.")


def area_rows(tables: dict[str, Table]) -> list[dict[str, Any]]:
    people = tables["ethnicity"]
    out = []
    for name in sorted(AREA_REGION):
        fields: dict[str, Any] = {}
        for kind in MAIN:
            fields.update(area_fields(name, kind, tables))
        # The census's ethnic-group table counts every resident, so its total
        # doubles as the population at this geography -- and it survives even
        # where the breakdown beneath it does not.
        if people.listed(name):
            fields["population"] = measure(int(people.totals[name]), year=2020,
                                           source=CENSUS, unit="residents")
        else:
            fields["population"] = gap(NOT_AVAILABLE, UNCOUNTED)
        sources = [{"field": "ethnicity/population", "name": CENSUS,
                    "url": DATAGOVSG_PAGE.format(id=DATASETS["ethnicity"][0]),
                    "year": 2020},
                   {"field": "religion/language", "name": CENSUS,
                    "url": DATAGOVSG_PAGE.format(id=DATASETS["religion"][0]),
                    "year": 2020}]
        if any(fields.get(f"{kind}_year") == 2010 for kind in FALLBACK):
            sources.append({"field": "religion/language", "name": CENSUS_2010,
                            "url": DATAGOVSG_PAGE.format(id=DATASETS["religion_2010"][0]),
                            "year": 2010})
        out.append(record(
            f"SGP-A-{name.replace(' ', '-')}", name, level="admin2", parent="SGP",
            codes={"planning_area": name, "planning_region": AREA_REGION[name]},
            sources=sources, **fields))
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


def region_field(region: str, kind: str, table: Table, people: Table,
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
    folded = [a for a in unlisted if people.listed(a)] if kind != "ethnicity" else []
    empty = [a for a in unlisted if a not in folded]
    if withheld:
        sentences.append(
            f"{names(withheld)} ({sum(table.totals[a] for a in withheld):,.0f} "
            f"residents{' together' if len(withheld) > 1 else ''}) "
            f"{'has' if len(withheld) == 1 else 'have'} a "
            f"count but no published breakdown, so {'it is' if len(withheld) == 1 else 'they are'} "
            f"in the base and in no group.")
    if folded:
        held = sum(people.totals[a] for a in folded)
        region_people = sum(people.totals[a] for a in areas if people.listed(a))
        sentences.append(
            f"The census folds {names(folded)} into an 'Others' row that cannot "
            f"be split by region, so {'it is' if len(folded) == 1 else 'they are'} "
            f"not included: {held:,.0f} residents in 2020, "
            f"{share_text(held, region_people)} of the region.")
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
    people = tables["ethnicity"]
    out = []
    for region in sorted(REGIONS):
        fields: dict[str, Any] = {}
        for kind in MAIN:
            fields.update(region_field(region, kind, tables[kind], people, short[kind]))
        # No population: SingStat's own series (singstat.py) publishes one for
        # each region, and a census base beside it would read as a rival.
        out.append(record(
            f"SGP-R-{region.replace(' ', '-')}", region, level="admin1", parent="SGP",
            codes={"planning_region": region},
            sources=[{"field": "ethnicity/religion/language", "name": CENSUS,
                      "url": PORTAL, "year": 2020,
                      "note": "Summed from the planning-area rows."}],
            **fields))
    return out


def build() -> list[dict[str, Any]]:
    tables = {
        "ethnicity": read(ETHNICITY_CSV, ETHNIC_COLUMNS, areas_only=True),
        "religion": read(RELIGION_CSV, RELIGION_COLUMNS, areas_only=False),
        "language": read(LANGUAGE_CSV, LANGUAGE_COLUMNS, areas_only=False),
        "religion_2010": read(RELIGION_2010_CSV, RELIGION_2010_COLUMNS, areas_only=False),
        "language_2010": read(LANGUAGE_2010_CSV, LANGUAGE_2010_COLUMNS, areas_only=False),
    }
    short = {}
    for kind, table in tables.items():
        check(kind, table)
        if kind not in MAIN:
            continue                      # the 2010 tables fill areas, not regions
        short[kind] = partition_gap(kind, table)
        log(f"  {kind}: {len(table.totals)} areas"
            + (f" and an Others row of {table.others:,.0f}" if table.others else "")
            + f" account for the national row to within {short[kind]:,.0f}")
    return area_rows(tables) + region_rows(tables, short)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true",
                    help="read the census tables from data.gov.sg into the "
                         "extracts first (needs network)")
    ap.add_argument("--fetch-only", action="store_true",
                    help="fetch the extracts and stop, so what was served is "
                         "committed before the adapter is pointed at it")
    args = ap.parse_args()
    if args.fetch or args.fetch_only:
        for kind, (dataset_id, path) in DATASETS.items():
            log(f"{kind}: fetching")
            fetch_extract(dataset_id, path)
        if args.fetch_only:
            return 0
    rows = build()
    areas = [r for r in rows if r["level"] == "admin2"]
    regions = [r for r in rows if r["level"] == "admin1"]
    with_religion = sum(1 for r in areas if isinstance(r.get("religion"), list))
    from_2010 = sum(1 for r in areas if r.get("religion_year") == 2010)
    with_ethnicity = sum(1 for r in areas if isinstance(r.get("ethnicity"), list))
    log(f"  {len(areas)} planning areas, {with_ethnicity} with ethnicity, "
        f"{with_religion} with religion and language ({from_2010} of them from "
        f"the 2010 census); {len(regions)} regions summed from them")
    write_json(PROCESSED / "singapore_planning_area.json", rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
