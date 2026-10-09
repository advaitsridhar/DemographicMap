#!/usr/bin/env python3
"""Pakistan -- Census 2023 Tables 4 and 10: age, sex and nationality by district.

``pakistan.py`` reads Table 9 (religion) and Table 11 (mother tongue). Two
more of the Bureau's district tables answer three of the map's empty fields
for every district of the four provinces and Islamabad:

* **Table 4, population by single year age, sex and rural/urban.** Each
  district prints an ALL AGES row, then "BELOW 1", "01" ... "74" and
  "75 & ABOVE", with the five-year groups interleaved, for all sexes, male,
  female and transgender. The median age is interpolated within the single
  year that holds the middle person; the sex ratio is males per hundred
  females from the ALL AGES row. Transgender persons are counted in the
  total and in neither sex, and the note says how many.
* **Table 10, population by nationality, age group, sex and rural/urban.**
  Pakistani, Afghani, Bangali, Chinese and Others, by district. The census
  asks no ethnicity question; by the owner's decision of 19 September 2026 a
  state's count of nationality is carried on the ethnicity field under
  ``ethnicity_basis: "nationality"``, the way Japan's and Korea's are. The
  Bureau's own report says the nationality question "can be called and
  understood as citizenship ... and not as ethnicity", and the note repeats
  it.

The two tables are typeset separately and print the same district totals, so
each is the other's control: a district's Table 10 nationalities must add up
to its Table 4 ALL AGES to the person. Inside Table 4 the single years must
add up to the ALL AGES row for persons, males and females, every five-year
row must equal the single years under it, and the provinces must add up to
the totals ``pakistan.py`` printed from Table 9.

**The districts are the boundary file's.** The polygons are older than the
census's districts, and ``pakistan.MERGED`` says which census districts make
up one drawn shape -- Karachi's seven, Chitral's two, and the twelve shapes
drawn as they were before a district was carved out of them (Sheikhupura
with Nankana Sahib, Larkana inside "Qambar Shahdadkot", and the rest). The
single years are summed before the median is taken, never the medians.
Each record is bound to its shape by id, read from the map's own units.

Azad Jammu and Kashmir and Gilgit-Baltistan are outside these tables: the
Bureau publishes Table 4 and Table 10 for neither, as it publishes Table 9
and Table 11 for neither. ``pakistan.py`` gives their records the reason.

Usage:
    python -m scripts.fetch_census.pakistan_census_tables
    python -m scripts.fetch_census.pakistan_census_tables --only ict
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from typing import Any

from ._shared import PROCESSED, log, measure, read_json, record, shares, write_json
from .pakistan import (
    ALIASES, BASE, DCR, DISTRICT, LICENCE, MERGED, MERGED_WHY, YEAR, Cell,
    fetch, printed, words_by_row,
)
from .south_asia_common import (
    agree, bind, load_units, males_per_100, median_single, report_binding,
)

AGE_SOURCE = ("Pakistan Bureau of Statistics, 7th Population and Housing "
              "Census 2023, Table 4: population by single year age, sex and "
              "rural/urban")
NATIONALITY_SOURCE = ("Pakistan Bureau of Statistics, 7th Population and "
                      "Housing Census 2023, Table 10: population by "
                      "nationality, age group, sex and rural/urban")

# The four provinces and the capital, with the census's own name for each and
# the paths the Bureau files the two tables under. The province files carry
# "_districts"; Islamabad's does not, being one district.
PROVINCES: dict[str, tuple[str, str]] = {
    "punjab": ("Punjab", "punjab"),
    "kp": ("Khyber Pakhtunkhwa", "kp"),
    "sindh": ("Sindh", "sindh"),
    "balochistan": ("Balochistan", "balochistan"),
    "ict": ("Islamabad Capital Territory", "islamabad"),
}


def candidates(table: int, slug: str) -> tuple[str, ...]:
    if slug == "ict":
        return (f"{BASE}/table_{table}_islamabad.pdf",
                f"{BASE}/table_{table}_islamabad_districts.pdf",
                f"{DCR}/islamabad/dcr/table_{table}.pdf")
    return (f"{BASE}/table_{table}_{slug}_districts.pdf",
            f"{DCR}/{PROVINCES[slug][1]}/dcr/table_{table}.pdf")


# Islamabad's tables head their one block with the territory's name rather
# than "X DISTRICT"; Table 9 calls the district ISLAMABAD, and so does this.
TERRITORY_HEADING = re.compile(r"^ISLAMABAD(?: CAPITAL TERRITORY| DISTRICT)?$")

# A Table 4 row label, longest first: the label is the row's leftmost words,
# and how many words it has is how many cells to set aside before the figures.
AGE_LABEL = re.compile(r"^(?:ALL AGES|BELOW 1|(\d{1,3}) -- (\d{1,3})|"
                       r"(\d{1,3}) & ABOVE|(\d{1,3}))(?=\s|$)")
OPEN_FROM = 75

NATIONALITIES = ("PAKISTANI", "AFGHANI", "BANGALI", "CHINESE", "OTHERS")
# Each answer is written as the nationality it is, in the form the group tree
# keeps for passports ("Afghan national", as iran_census writes Iran's
# citizenship counts): the bare words "Afghan", "Chinese" and "Bangali" are
# peoples in the tree -- Iranian, Han, Indo-Aryan -- and Table 10 answers a
# question about citizenship, not descent. "Afghani" is the currency's name,
# Afghan the people's. "Bangali" keeps the census's own word: it is the Urdu
# name of the Bengali people, not of a state, and nothing the Bureau publishes
# says that the people it counts under it -- 23,850 of them in Karachi, where
# Bengalis long settled in Pakistan live -- hold Bangladesh's citizenship
# rather than none. "Pakistani" is the home row, a nationality in the tree
# already.
NATIONALITY_LABELS = {
    "PAKISTANI": "Pakistani",
    "AFGHANI": "Afghan national",
    "BANGALI": "Bangali national",
    "CHINESE": "Chinese national",
    "OTHERS": "Other nationalities",
}


# ---------------------------------------------------------------------------
# Reading the tables
# ---------------------------------------------------------------------------

def line_of(cells: list[Cell]) -> str:
    return " ".join(text for _a, _b, text in cells)


def heading(line: str, slug: str) -> str | None:
    """The census district a heading line opens, or None if it is not one."""
    if slug == "ict" and TERRITORY_HEADING.match(line):
        return "ISLAMABAD"
    match = DISTRICT.match(line)
    return match.group(1).strip() if match else None


def letters(text: str) -> Counter:
    return Counter(ch for ch in text.upper() if "A" <= ch <= "Z")


def overdrawn_heading(line: str, ghost: str | None,
                      expected: set[str] | None) -> str | None:
    """A district heading drawn over the page's leftover first heading.

    Punjab's Table 4 carries its first district's heading, "ATTOCK DISTRICT",
    at the top of every page, under whatever the page prints there. Where a
    district's block starts at the top of a page its own heading is drawn on
    top of it, and the two come out interleaved letter by letter: Gujranwala's
    reads "GUAJRTATONWCKA LDAIS DTIRSITCRTICT". The district is the one whose
    "<NAME> DISTRICT" supplies exactly the letters left once the leftover
    heading's are taken away -- every letter accounted for, and only one
    district of those Table 10 names fitting.
    """
    if not ghost or not expected or any(ch.isdigit() for ch in line):
        return None
    have, under = letters(line), letters(ghost)
    if under - have:
        return None                        # the leftover heading is not all there
    left = have - under
    if not left:
        return None
    found = [name for name in expected if letters(f"{name} DISTRICT") == left]
    return found[0] if len(found) == 1 else None


def is_subunit(line: str) -> bool:
    """A tehsil's, taluka's or sub-division's heading: a breakdown, not a unit."""
    return bool(re.search(r"\b(?:TEHSIL|TALUKA|SUB[- ]DIVISION|SUB[- ]TEHSIL|"
                          r"CANTONMENT|CANTT|AGENCY)$", line))


def is_column_numbers(line: str) -> bool:
    """The header's numbered row, "1 2 3 ... 13", repeated on every page.

    It would otherwise read as age 1 with twelve figures after it.
    """
    tokens = line.split()
    return len(tokens) >= 5 and tokens == [str(i) for i in range(1, len(tokens) + 1)]


def labelled(cells: list[Cell]) -> tuple[re.Match | None, list[int]]:
    """A row's label and its figures, the label's words set aside first."""
    line = line_of(cells)
    if is_column_numbers(line):
        return None, []
    match = AGE_LABEL.match(line)
    if not match:
        return None, []
    words = len(match.group(0).split())
    return match, printed(cells[words:])


def sexes(figures: list[int], where: str) -> tuple[int, int, int]:
    """(persons, males, females) of ALL LOCALITIES, checked against each other.

    The table prints persons, males, females and transgender for all
    localities, then the same for rural and for urban, and writes a dash for a
    zero -- but leaves the transgender cell blank on some rows rather than
    dashing it. So the first three cells are read and the transgender count
    is what is left of persons once the sexes are taken away: never negative,
    and equal to the fourth cell where the row prints all twelve.
    """
    if len(figures) < 3:
        raise SystemExit(f"pakistan: {where} has {len(figures)} figures: {figures}")
    persons, males, females = figures[:3]
    rest = persons - males - females
    if rest < 0 or rest > max(5, 0.01 * persons):
        raise SystemExit(
            f"pakistan: {where} reads {persons:,} persons, {males:,} males and "
            f"{females:,} females -- the sexes do not fit inside the total, so "
            f"a cell has been read from the wrong column: {figures}")
    if len(figures) == 12 and figures[3] != rest:
        raise SystemExit(
            f"pakistan: {where} prints {figures[3]:,} transgender persons where "
            f"persons less males and females is {rest:,}: {figures}")
    return persons, males, females


def read_ages(blob: bytes, slug: str,
              expected: set[str] | None = None) -> dict[str, dict[str, Any]]:
    return ages_from_pages(words_by_row(blob), slug, expected)


def ages_from_pages(pages, slug: str,
                    expected: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """Table 4 for one province: {district: {"ages": {sex: Counter}, ...}}.

    A district's block runs from its heading to its "75 & ABOVE" row. Rows
    outside a district's block -- the tehsils' and talukas' breakdowns that
    follow it -- are not read, and a district heading arriving before the
    block it interrupts has closed is refused rather than half-read.

    ``expected`` is the districts Table 10 names, which is what lets a
    heading drawn over the page's leftover first heading be read at all
    (:func:`overdrawn_heading`).
    """
    out: dict[str, dict[str, Any]] = {}
    current: str | None = None
    block: dict[str, Any] | None = None
    ghost: str | None = None               # the document's first heading
    # Where the label column ends: the left edge of the first figure in the
    # district's ALL AGES row, which is always the block's first row. A word
    # left of it is a label word; right of it, a figure.
    edge: float | None = None
    # A label whose figures were set a few points lower than it, on a line of
    # their own. On the first row of a continuation page the repeated district
    # heading is drawn over the row, and Attock's age 57 comes out as "57"
    # beside the mangled heading and "1 4,540 7,605 6,935 -" on the next line.
    pending: re.Match | None = None
    for rows in pages:
        for cells in rows:
            line = line_of(cells)
            name = heading(line, slug)
            if name and ghost is None:
                ghost = line
            if not name:
                name = overdrawn_heading(line, ghost, expected)
            if name:
                if name == current:
                    continue                   # the heading repeated on a new page
                if block is not None:
                    raise SystemExit(f"pakistan: Table 4 {current} is interrupted "
                                     f"by {name} before its 75 & ABOVE row")
                if name in out:
                    raise SystemExit(f"pakistan: Table 4 prints {name} twice")
                current = name
                block = {"total": None, "ages": {"T": Counter(), "M": Counter(),
                                                  "F": Counter()},
                         "groups": {}}
                edge, pending = None, None
                continue
            if is_subunit(line):
                if block is not None:
                    raise SystemExit(f"pakistan: Table 4 {current} is interrupted "
                                     f"by '{line}' before its 75 & ABOVE row")
                continue
            if block is None or is_column_numbers(line):
                continue
            if edge is None:
                match, figures = labelled(cells)
                if match is None or match.group(0) != "ALL AGES" or not figures:
                    continue
                words = len(match.group(0).split())
                edge = cells[words][0] - 1.0
            else:
                label_words = [c for c in cells if c[0] < edge]
                data = [c for c in cells if c[0] >= edge]
                match = AGE_LABEL.fullmatch(line_of(label_words)) if label_words else None
                figures = printed(data)
                if label_words and match is None:
                    continue                   # a header or a mangled line
                if match is not None and not figures:
                    pending = match            # its figures are on the next line
                    continue
                if match is None:
                    if pending is None or not figures:
                        continue
                    match, pending = pending, None
                else:
                    pending = None
            where = f"Table 4 {current} '{match.group(0)}'"
            persons, males, females = sexes(figures, where)
            label = match.group(0)
            if label == "ALL AGES":
                block["total"] = (persons, males, females)
                continue
            if label == "BELOW 1":
                age = 0
            elif match.group(1) is not None:
                block["groups"][(int(match.group(1)), int(match.group(2)))] = persons
                continue
            elif match.group(3) is not None:
                age = int(match.group(3))
                if age != OPEN_FROM:
                    raise SystemExit(f"pakistan: {where}: the open group starts at "
                                     f"{age}, not {OPEN_FROM}")
            else:
                age = int(match.group(4))
            for sex, n in zip("TMF", (persons, males, females)):
                if age in block["ages"][sex]:
                    raise SystemExit(f"pakistan: {where} prints age {age} twice")
                block["ages"][sex][age] = n
            if age == OPEN_FROM:
                out[current] = block
                block, current = None, None
    if block is not None:
        raise SystemExit(f"pakistan: Table 4 ends inside {current}'s block")
    return out


def check_ages(name: str, block: dict[str, Any]) -> None:
    """The table's own sums: single years to totals, years to their groups."""
    if block["total"] is None:
        raise SystemExit(f"pakistan: Table 4 {name} has no ALL AGES row")
    ages = block["ages"]
    expected = set(range(0, OPEN_FROM + 1))
    if set(ages["T"]) != expected:
        missing = sorted(expected - set(ages["T"]))
        raise SystemExit(f"pakistan: Table 4 {name} is missing ages {missing}")
    for sex, total in zip("TMF", block["total"]):
        agree(f"pakistan: Table 4 {name} {sex} single years",
              sum(ages[sex].values()), total)
    for (low, high), n in block["groups"].items():
        agree(f"pakistan: Table 4 {name} ages {low}-{high}",
              sum(ages["T"][a] for a in range(low, high + 1)), n)


def read_nationality(blob: bytes, slug: str) -> dict[str, dict[str, int]]:
    return nationality_from_pages(words_by_row(blob), slug)


def nationality_from_pages(pages, slug: str) -> dict[str, dict[str, int]]:
    """Table 10 for one province: {district: {nationality: persons}}.

    Each district prints its ALL SEXES block first, and the first ALL AGES
    row of it is the district's whole population by nationality; the five
    nationalities of all localities come first on the row.
    """
    out: dict[str, dict[str, int]] = {}
    current: str | None = None
    for rows in pages:
        for cells in rows:
            line = line_of(cells)
            name = heading(line, slug)
            if name:
                current = name if name not in out else None
                continue
            if is_subunit(line):
                current = None
                continue
            if current is None or not line.startswith("ALL AGES"):
                continue
            figures = printed(cells[2:])
            if len(figures) < len(NATIONALITIES):
                raise SystemExit(f"pakistan: Table 10 {current} ALL AGES has "
                                 f"{len(figures)} figures: {figures}")
            out[current] = dict(zip(NATIONALITIES, figures[:len(NATIONALITIES)]))
            current = None
    return out


def merge_parts(found: dict[str, Any], combine) -> dict[str, tuple[str, ...]]:
    """Sum the census districts one drawn shape holds, as pakistan.merge does."""
    assembled: dict[str, tuple[str, ...]] = {}
    for name, parts in MERGED.items():
        here = [p for p in parts if p in found]
        if not here:
            continue
        if len(here) != len(parts):
            raise SystemExit(f"pakistan: {name} is {', '.join(parts)} and only "
                             f"{', '.join(here)} were read")
        merged = combine([found[p] for p in parts])
        for part in parts:
            del found[part]
        found[name] = merged
        assembled[name] = parts
    return assembled


def combine_ages(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    out = {"total": tuple(sum(b["total"][i] for b in blocks) for i in range(3)),
           "ages": {sex: Counter() for sex in "TMF"}, "groups": {}}
    for block in blocks:
        for sex in "TMF":
            out["ages"][sex].update(block["ages"][sex])
    return out


def combine_counts(rows: list[dict[str, int]]) -> dict[str, int]:
    out: Counter = Counter()
    for row in rows:
        out.update(row)
    return dict(out)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def age_fields(block: dict[str, Any], url: str, extra: str = "") -> dict[str, Any]:
    persons, males, females = block["total"]
    median = median_single(dict(block["ages"]["T"]), open_from=OPEN_FROM)
    ratio = males_per_100(males, females)
    other = persons - males - females
    fields: dict[str, Any] = {"sources": [
        {"field": "median_age/sex_ratio", "name": AGE_SOURCE, "url": url,
         "year": YEAR, "license": LICENCE}]}
    if median is not None:
        fields["median_age"] = measure(median, unit="years", year=YEAR,
                                       source=AGE_SOURCE)
        fields["median_age_note"] = (
            "Census 2023 Table 4: the median of the single years of age of all "
            f"{persons:,} people, interpolated within the year that holds the "
            "middle person (75 and over is the open top group)." + extra)
    if ratio is not None:
        fields["sex_ratio"] = measure(ratio, unit="males_per_100_females",
                                      year=YEAR, source=AGE_SOURCE)
        fields["sex_ratio_note"] = (
            f"Census 2023 Table 4: {males:,} males against {females:,} females."
            + (f" The {other:,} transgender persons the census counted are in "
               "the population and in neither figure." if other else "")
            + extra)
    return fields


def nationality_fields(counts: dict[str, int], persons: int, url: str,
                       extra: str = "") -> dict[str, Any]:
    labelled_counts = {NATIONALITY_LABELS[k]: v for k, v in counts.items() if v}
    foreign = persons - counts.get("PAKISTANI", 0)
    return {
        "ethnicity": shares(labelled_counts, total=persons),
        "ethnicity_year": YEAR,
        "ethnicity_basis": "nationality",
        "ethnicity_note": (
            "Nationality, not ethnicity: Census 2023 Table 10 counts everyone "
            "enumerated by nationality -- Pakistani, Afghani, Bangali, Chinese "
            "and others; 'Bangali' is kept as printed, the census not saying "
            "whose citizenship those it counts under it hold -- and the Bureau's own "
            "National Census Report says the question \"can be called and "
            "understood as citizenship, or more generally as subject or "
            "belonging to a sovereign state, and not as ethnicity\". The census "
            f"asks no ethnicity question. {foreign:,} of the {persons:,} people "
            "counted here are not Pakistani nationals." + extra),
        "sources": [{"field": "ethnicity", "name": NATIONALITY_SOURCE,
                     "url": url, "year": YEAR, "license": LICENCE}],
    }


def province_parent_units(units1: list[dict[str, Any]],
                          units2: list[dict[str, Any]]) -> dict[str, set[str]]:
    """{province name: ids of the second-level units drawn inside it}."""
    names = {u["id"]: u.get("site_name") or u.get("name") for u in units1}
    out: dict[str, set[str]] = {}
    for unit in units2:
        out.setdefault(names.get(unit.get("parent"), ""), set()).add(unit["id"])
    return out


def build(only: set[str] | None = None) -> tuple[list[dict[str, Any]],
                                                 list[dict[str, Any]]]:
    units1 = load_units("PAK", "admin1")
    units2 = load_units("PAK", "admin2")
    inside = province_parent_units(units1, units2)
    table9 = {(r["level"], r["name"]): r for r in read_json(
        PROCESSED / "pakistan_district.json", []) or []}
    ages_out: list[dict[str, Any]] = []
    nat_out: list[dict[str, Any]] = []
    nation: list[dict[str, Any]] = []
    for slug, (province, _path) in PROVINCES.items():
        if only and slug not in only:
            continue
        log(f"  {province}")
        blob10, url10 = fetch(candidates(10, slug))
        log(f"    Table 10: {len(blob10):,} bytes from {url10}")
        nationality = read_nationality(blob10, slug)
        blob4, url4 = fetch(candidates(4, slug))
        log(f"    Table 4: {len(blob4):,} bytes from {url4}")
        ages = read_ages(blob4, slug, set(nationality))
        if set(ages) != set(nationality):
            raise SystemExit(
                f"pakistan: {province}: Table 4 and Table 10 name different "
                f"districts. Only in 4: {sorted(set(ages) - set(nationality))}; "
                f"only in 10: {sorted(set(nationality) - set(ages))}")
        for name, block in ages.items():
            check_ages(name, block)
            agree(f"pakistan: {name} Table 10 against Table 4",
                  sum(nationality[name].values()), block["total"][0])
        log(f"    {len(ages)} districts; single years, five-year groups and "
            "nationalities all reconcile")
        # The province from its districts, before they are merged into shapes:
        # checked against the total pakistan.py printed from Table 9.
        whole = combine_ages(list(ages.values()))
        nation.append(whole)
        whole_nat = combine_counts(list(nationality.values()))
        printed9 = table9.get(("admin1", province))
        if printed9 and isinstance(printed9.get("population"), dict):
            agree(f"pakistan: {province}'s districts against its Table 9 row",
                  whole["total"][0], printed9["population"]["value"])
        assembled = merge_parts(ages, combine_ages)
        merge_parts(nationality, combine_counts)
        province_unit = [u for u in units1 if (u.get("site_name") or u["name"]) == province]
        if len(province_unit) == 1:
            fields_a = age_fields(whole, url4)
            fields_n = nationality_fields(whole_nat, whole["total"][0], url10)
            ages_out.append(record(
                f"PAK-AGE-{slug}", province, level="admin1", parent="PAK",
                country="PAK", match_by="shape_id", shape_id=province_unit[0]["id"],
                **fields_a))
            nat_out.append(record(
                f"PAK-NAT-{slug}", province, level="admin1", parent="PAK",
                country="PAK", match_by="shape_id", shape_id=province_unit[0]["id"],
                **fields_n))
        else:
            log(f"    ! {province}: {len(province_unit)} first-level units carry the name")
        rows = {}
        for name in ages:
            title = name.title()
            names = [title, *ALIASES.get(title, ())]
            if slug == "ict":
                names += ["Islamabad Capital Territory", "Islamabad"]
            rows[name] = tuple(names)
        parent_of = {name: province for name in rows}
        bound, left, _spare = bind(rows, units2, parent_of=parent_of,
                                   parent_units=inside)
        spare = [u for u in units2 if u["id"] in inside.get(province, set())
                 and u["id"] not in {b["id"] for b in bound.values()}]
        report_binding(province, bound, left, spare)
        for name, unit in sorted(bound.items()):
            extra = ""
            if name in assembled:
                why = MERGED_WHY.get(name, "the boundary file draws them as one shape")
                extra = (" The shape is " + " and ".join(p.title() for p in assembled[name])
                         + f" summed, single year by single year: {why}.")
            ages_out.append(record(
                f"PAK-AGE-{slug}-{name.lower().replace(' ', '-')}", name.title(),
                level="admin2", parent="PAK", parent_name=province, country="PAK",
                match_by="shape_id", shape_id=unit["id"],
                **age_fields(ages[name], url4, extra)))
            nat_out.append(record(
                f"PAK-NAT-{slug}-{name.lower().replace(' ', '-')}", name.title(),
                level="admin2", parent="PAK", parent_name=province, country="PAK",
                match_by="shape_id", shape_id=unit["id"],
                **nationality_fields(nationality[name], ages[name]["total"][0],
                                     url10, extra)))
        if left:
            raise SystemExit(f"pakistan: {province}: no single drawn shape for "
                             f"{', '.join(sorted(left))}; refusing to leave "
                             "them off the map silently")
    # The nation's median from the same single years, for the record: the
    # Bureau's Table 4 prints counts and no median, and no national median of
    # its own was found to hold this to (the National Census Report at
    # /sites/default/files/population/2023/national_report.pdf answered 404 on
    # 9 October 2026). Logged with the districts' range, so an outlier --
    # Kohistan's 11.9, Zhob's 12.2 -- is read against the whole.
    if nation and not only:
        whole = combine_ages(nation)
        medians = sorted((r["median_age"]["value"], r["name"]) for r in ages_out
                         if r["level"] == "admin2" and "value" in (r.get("median_age") or {}))
        log(f"  the four provinces and Islamabad: {whole['total'][0]:,} people, median age "
            f"{median_single(dict(whole['ages']['T']), open_from=OPEN_FROM)}; districts from "
            + ", ".join(f"{n} {v}" for v, n in medians[:3]) + " to "
            + ", ".join(f"{n} {v}" for v, n in medians[-3:]))
    return ages_out, nat_out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated province slugs")
    args = ap.parse_args()
    only = {s for s in args.only.split(",") if s} or None
    log("pakistan_census_tables: Census 2023 Tables 4 and 10")
    ages, nationality = build(only)
    suffix = "" if not only else "_" + "_".join(sorted(only))
    write_json(PROCESSED / f"pakistan_age{suffix}.json", ages)
    write_json(PROCESSED / f"pakistan_nationality{suffix}.json", nationality)
    if not only:
        # A whole run supersedes the trial runs of single provinces, whose
        # files no build reads; leaving them would be litter that looks like
        # data.
        for stale in [*PROCESSED.glob("pakistan_age_*.json"),
                      *PROCESSED.glob("pakistan_nationality_*.json")]:
            stale.unlink()
            log(f"  removed the trial file {stale.name}")
    log(f"  {len(ages)} age records, {len(nationality)} nationality records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
