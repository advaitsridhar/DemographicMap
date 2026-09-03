#!/usr/bin/env python3
"""Census tables the US Census Bureau standardises for countries that publish
theirs as documents.

The Bureau prepares "Subnational Population and Housing Census Tables" for
USAID's humanitarian bureau: a national census, extracted into one workbook per
country, with a schema that does not vary. Every sheet begins with the same
geography columns -- ``AREA_NAME``, ``ADM1_NAME``, ``ADM2_NAME``, ``ADM_LEVEL``
-- and then a block of value columns for one topic. So a single reader serves
every country in the series, which is why this is not two adapters:

* **Philippines**, 2020 Census of Population and Housing (Philippine Statistics
  Authority): religion and ethnicity for the country, 17 regions, and the
  provinces and highly urbanized cities beneath them.
* **Ethiopia**, 2007 Population and Housing Census (Central Statistical
  Agency): religion, ethnicity and language. 2007 because that is the last
  census Ethiopia completed -- the 2017 round was postponed and never held --
  so every record here carries that year rather than the year of the file.

Two things about the schema decide how this reads:

**The header is two rows deep.** Row 1 holds field names (``RLG_ORDX_B``) and
row 2 the aliases a person would recognise ("Orthodox, both sexes"). The names
are stable across countries and the aliases are what belongs on the map, so
both are read and the group label comes from the alias.

**Which columns are groups is a fact about the sheet, not a list to hardcode.**
The Philippine religion sheet names 128 individual denominations; Ethiopia's
names six. Hardcoding either would break on the other and, worse, would go
stale silently when the Bureau revises a workbook. So the group columns are
whatever is left after the geography columns and the denominator, and the run
prints how many it found. A column added upstream shows up in the log as a
count that moved, not as a figure that quietly changed.

**Sex is a check, not a dimension.** Ethiopia reports every religion three
times -- both sexes, females, males. Only the both-sexes column is a value
here; the other two are used to verify it, because a file whose sexes do not
add up is a file this reader has misunderstood.

Usage:
    python -m scripts.fetch_census.uscb --country PHL
    python -m scripts.fetch_census.uscb            # every country configured
"""

from __future__ import annotations

import argparse
import io
from dataclasses import dataclass, field as dc_field
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, gap, http_get, log, measure, record, shares,
    write_json,
)

# The columns every sheet in the series begins with, whatever its topic. Listed
# rather than detected: they are the schema, and a value column that happened
# to be named like one of them would be a silent loss.
GEOGRAPHY = {
    "AREA_NAME", "GEO_CONCAT", "GEO_MATCH", "CNTRY_NAME",
    "ADM1_NAME", "ADM2_NAME", "ADM3_NAME", "ADM4_NAME",
    "ADM_LEVEL", "USCBCMNT", "GENC_CODE", "FIPS_CODE",
    "NSO_CODE", "NSO_NAME",
}

# How far a group total may sit from the sheet's own denominator and still be
# rounding rather than a misreading. The Bureau publishes whole people, so the
# only slack wanted is for a published figure that does not add up -- and where
# that happens the run says so by name instead of absorbing it.
TOLERANCE = 0.005


@dataclass(frozen=True)
class Topic:
    """One sheet of a workbook, and the field it fills on this map."""
    sheet: str
    field: str
    prefix: str


@dataclass(frozen=True)
class Country:
    iso3: str
    name: str
    year: int
    source: str
    licence: str
    url: str
    workbook: str
    out: str
    # Which ADM_LEVEL becomes which layer of this map. The Bureau's levels are
    # the country's own, so this is a fact per country: the Philippines' first
    # order is its 17 regions and its second the provinces, while Ethiopia's
    # first order is its regions and its second the zones.
    levels: dict[int, str]
    topics: tuple[Topic, ...]
    note: str
    aliases: dict[str, tuple[str, ...]] = dc_field(default_factory=dict)


HDX = "https://data.humdata.org/dataset"

PHILIPPINES = Country(
    iso3="PHL",
    name="Philippines",
    year=2020,
    source=("Philippine Statistics Authority, 2020 Census of Population and "
            "Housing, prepared as subnational tables by the U.S. Census Bureau"),
    licence="CC BY-IGO, published via HDX",
    url=f"{HDX}/philippines-subnational-population-statistics",
    workbook=(f"{HDX}/809dfb22-77f4-482c-8560-79b07d20fc15/resource/"
              "5acff37e-0c02-4d89-bbd2-1825ee98916c/download/"
              "philippines_uscb_202402.xlsx"),
    out="philippines_province.json",
    levels={1: "admin1", 2: "admin2"},
    topics=(Topic("Religion", "religion", "RLG_"),
            Topic("Ethnicity", "ethnicity", "ETH_")),
    note=("2020 Census of Population and Housing. The census records religious "
          "affiliation as the individual church or denomination a person names, "
          "so the groups here are as published rather than collapsed into "
          "traditions -- the alternative would decide, on this map's authority "
          "rather than the census's, which churches count as one religion."),
)

ETHIOPIA = Country(
    iso3="ETH",
    name="Ethiopia",
    year=2007,
    source=("Central Statistical Agency of Ethiopia, 2007 Population and "
            "Housing Census, prepared as subnational tables by the U.S. Census "
            "Bureau"),
    licence="CC BY-IGO, published via HDX",
    url=f"{HDX}/ethiopia-subnational-population-statistics",
    workbook=(f"{HDX}/5438946a-51b7-44d6-9b76-aeafdb4dc4d3/resource/"
              "f112d5fa-d90e-4352-b0c1-54cffbbad62d/download/"
              "ethiopia_uscb_202308.xlsx"),
    out="ethiopia_region.json",
    levels={1: "admin1", 2: "admin2"},
    topics=(Topic("Religion", "religion", "RLG_"),
            Topic("Ethnicity", "ethnicity", "ETH_"),
            Topic("Language", "language", "LNG_")),
    note=("2007 Population and Housing Census -- the last census Ethiopia has "
          "completed. The 2017 round was postponed and never held, so this is "
          "the most recent measurement in existence, not the most recent "
          "available to this project. Read it as a description of 2007."),
)

COUNTRIES: dict[str, Country] = {c.iso3: c for c in (PHILIPPINES, ETHIOPIA)}


def sheet_rows(book, name: str) -> list[list[Any]]:
    """One sheet as rows, matched on a stripped name.

    Published workbooks put stray whitespace in sheet names often enough that
    an exact lookup is a bug waiting for the next file: Bangladesh's religion
    sheet begins with a space.
    """
    wanted = name.strip().lower()
    for actual in book.sheetnames:
        if actual.strip().lower() == wanted:
            return [list(row) for row in
                    book[actual].iter_rows(values_only=True)]
    raise SystemExit(f"no sheet named {name!r}; the workbook has "
                     f"{', '.join(book.sheetnames)}")


def columns(rows: list[list[Any]]) -> tuple[list[str], list[str]]:
    """The two header rows: field names, and the aliases people read."""
    if len(rows) < 3:
        raise SystemExit("sheet has no data under its two header rows")
    names = ["" if v is None else str(v).strip() for v in rows[0]]
    aliases = ["" if v is None else str(v).strip() for v in rows[1]]
    return names, aliases


def sexed(names: list[str], prefix: str) -> bool:
    """Does this sheet report every group three times, by sex?

    Ethiopia does and the Philippines does not, and the difference is visible
    in the column names rather than declared per country -- a stem that carries
    all three of _B, _F and _M is a sexed sheet.
    """
    stems = {n[:-2] for n in names if n.startswith(prefix) and n.endswith("_B")}
    if not stems:
        return False
    return all(f"{s}_F" in names and f"{s}_M" in names for s in stems)


def denominator(names: list[str], aliases: list[str], prefix: str) -> int | None:
    """The column holding everyone the question was asked of, if there is one.

    Found by its alias rather than its name: the Philippines calls it
    ``RLG_HPOP`` / "Household population" and Indonesia's language sheet
    ``LNG_BTOTL`` / "Total population", and inventing a rule that spans both
    from the names alone would be guessing. Ethiopia publishes no such column
    at all, and returning None says so rather than picking a group at random.
    """
    for index, (name, alias) in enumerate(zip(names, aliases)):
        if not name.startswith(prefix):
            continue
        if "population" in alias.lower():
            return index
    return None


def groups(names: list[str], aliases: list[str], prefix: str,
           total: int | None, by_sex: bool) -> dict[int, str]:
    """Column index -> the label to publish, for every group column."""
    out: dict[int, str] = {}
    for index, (name, alias) in enumerate(zip(names, aliases)):
        if index == total or not name.startswith(prefix):
            continue
        if name in GEOGRAPHY or not alias:
            continue
        if by_sex:
            if not name.endswith("_B"):
                continue
            # "Orthodox, both sexes" is the column; "Orthodox" is the group.
            alias = alias.rsplit(",", 1)[0].strip()
        out[index] = alias
    return out


def number(value: Any) -> float | None:
    """A cell as a count of people, or None where the file has none.

    The workbooks write -999 where a figure is unavailable, which is not
    documented in their metadata and is easy to read straight through: it is a
    number, and openpyxl hands it over as one. Four Ethiopian areas carry it
    across all six religions, and taking it at face value would have put a
    negative population on the map.

    Rejected as "not a count" rather than as "-999 specifically", because the
    reason is the stronger one: no census reports a negative number of people,
    so any negative is a marker of some kind whatever its value, and a sentinel
    the Bureau changes to -998 tomorrow would still be caught.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    if isinstance(value, str):
        text = value.replace(",", "").strip()
        if text.replace(".", "", 1).isdigit():
            return float(text)
    return None


def check_sexes(rows: list[list[Any]], names: list[str], prefix: str,
                where: str) -> None:
    """Females plus males must be the both-sexes figure, on every row.

    This is the whole reason the sex columns are read at all. They are not a
    dimension this map shows; they are two independent statements about the
    same population, and a file where they disagree is a file this reader has
    misunderstood.
    """
    index = {name: i for i, name in enumerate(names)}
    stems = sorted({n[:-2] for n in names
                    if n.startswith(prefix) and n.endswith("_B")})
    off: list[tuple[float, str]] = []
    cells = 0
    for row in rows[2:]:
        where_row = str(row[index["AREA_NAME"]] or "?").strip()
        for stem in stems:
            both = number(row[index[f"{stem}_B"]])
            female = number(row[index[f"{stem}_F"]])
            male = number(row[index[f"{stem}_M"]])
            if both is None or female is None or male is None:
                continue
            cells += 1
            gap_ = (female + male) - both
            if abs(gap_) > 0.5:
                off.append((abs(gap_),
                            f"{where_row} {stem}: {female:,.0f} + {male:,.0f} "
                            f"= {female + male:,.0f} against {both:,.0f} "
                            f"(out by {gap_:+,.0f})"))
    if off:
        off.sort(reverse=True)
        log(f"    {len(off)} of {cells} cells do not reconcile by sex; "
            f"the largest:")
        for _size, line in off[:8]:
            log(f"      {line}")
        raise SystemExit(f"{where}: {len(off)} of {cells} cells where females "
                         f"plus males do not equal the both-sexes figure")
    log(f"    {len(stems)} groups reconcile by sex across {cells} cells")


def area(row: list[Any], names: list[str]) -> tuple[int | None, str, str]:
    """A row's level, its own name, and its parent's."""
    index = {name: i for i, name in enumerate(names)}
    level = number(row[index["ADM_LEVEL"]])
    name = str(row[index["AREA_NAME"]] or "").strip()
    parent = ""
    if level == 2 and "ADM1_NAME" in index:
        parent = str(row[index["ADM1_NAME"]] or "").strip()
    return (int(level) if level is not None else None, name, parent)


def read(book, country: Country, topic: Topic) -> dict[str, dict[str, Any]]:
    """One topic's sheet as {area name: {level, parent, counts, total}}."""
    rows = sheet_rows(book, topic.sheet)
    names, aliases = columns(rows)
    by_sex = sexed(names, topic.prefix)
    total = denominator(names, aliases, topic.prefix)
    found = groups(names, aliases, topic.prefix, total, by_sex)
    if not found:
        raise SystemExit(f"{country.iso3} {topic.sheet}: no column starts with "
                         f"{topic.prefix!r}")
    log(f"  {topic.sheet}: {len(rows) - 2} rows, {len(found)} groups"
        + (", by sex" if by_sex else "")
        + (f", denominator {aliases[total]!r}" if total is not None
           else ", no published denominator"))
    if by_sex:
        check_sexes(rows, names, topic.prefix, f"{country.iso3} {topic.sheet}")

    out: dict[str, dict[str, Any]] = {}
    skipped = 0
    for row in rows[2:]:
        level, name, parent = area(row, names)
        if level not in country.levels or not name or name.upper() == "NO NAME":
            # "NO NAME" is the workbook's own placeholder for an area it could
            # not label. It is not a place, and giving it a record would put an
            # unnamed shape on the map with figures attached.
            skipped += 1
            continue
        counts = {label: value for index, label in found.items()
                  if (value := number(row[index])) is not None and value > 0}
        if not counts:
            continue
        published = number(row[total]) if total is not None else None
        out[name] = {"level": level, "parent": parent, "counts": counts,
                     "published": published, "summed": sum(counts.values())}
    if skipped:
        log(f"    {skipped} rows skipped: another level, or no area name")
    return out


def check_total(country: Country, topic: Topic,
                areas: dict[str, dict[str, Any]]) -> None:
    """Where the sheet publishes a denominator, the groups must reach it."""
    checked = off = 0
    for name, row in areas.items():
        if row["published"] is None or row["published"] <= 0:
            continue
        checked += 1
        if abs(row["summed"] - row["published"]) / row["published"] > TOLERANCE:
            off += 1
            if off <= 3:
                log(f"    {name}: groups come to {row['summed']:,.0f} against "
                    f"a published {row['published']:,.0f}")
    if off:
        raise SystemExit(f"{country.iso3} {topic.sheet}: {off} of {checked} "
                         f"areas do not reach their own published total")
    if checked:
        log(f"    every one of {checked} areas reaches its published total")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", action="append",
                    choices=sorted(COUNTRIES) + ["all"], default=None)
    ap.add_argument("--out")
    args = ap.parse_args()

    import openpyxl

    wanted = [c for c in (args.country or ["all"])]
    chosen = (sorted(COUNTRIES) if "all" in wanted else wanted)

    for iso3 in chosen:
        country = COUNTRIES[iso3]
        log(f"{country.name}: {country.workbook}")
        blob = http_get(country.workbook, binary=True,
                        cache_dir=RAW / "uscb")
        log(f"  {len(blob):,} bytes")
        book = openpyxl.load_workbook(io.BytesIO(blob), read_only=True,
                                      data_only=True)

        fields: dict[str, dict[str, dict[str, Any]]] = {}
        for topic in country.topics:
            areas = read(book, country, topic)
            check_total(country, topic, areas)
            fields[topic.field] = areas
        book.close()

        every = sorted({name for areas in fields.values() for name in areas})
        records: list[dict[str, Any]] = []
        for name in every:
            any_row = next(a[name] for a in fields.values() if name in a)
            level = country.levels[any_row["level"]]
            values: dict[str, Any] = {}
            for topic in country.topics:
                row = fields[topic.field].get(name)
                if not row:
                    continue
                values[topic.field] = shares(
                    row["counts"], total=row["published"] or row["summed"]
                ) or gap(NOT_AVAILABLE)
                values[f"{topic.field}_year"] = country.year
                values[f"{topic.field}_note"] = country.note
            slug = name.lower().replace(" ", "-").replace("/", "-")
            records.append(record(
                f"{iso3}-{slug}", name.title(), level=level, parent=iso3,
                parent_name=any_row["parent"].title() or None,
                aliases=list(country.aliases.get(name, ())),
                sources=[{"field": "/".join(t.field for t in country.topics),
                          "name": country.source, "url": country.url,
                          "license": country.licence}],
                **values))

        out = args.out or PROCESSED / country.out
        write_json(out, records)
        counts = {lvl: sum(1 for r in records if r["level"] == lvl)
                  for lvl in sorted(country.levels.values())}
        log(f"  {len(records)} areas: "
            + ", ".join(f"{n} {lvl}" for lvl, n in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
