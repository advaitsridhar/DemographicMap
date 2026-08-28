#!/usr/bin/env python3
"""Pakistan -- 7th Population and Housing Census 2023, religion by district.

The Bureau of Statistics publishes Table 9, *population by sex, religion and
rural/urban*, as one PDF per province. There is no API and no spreadsheet: the
tables exist only as documents, and reading them is the whole job.

Three things about those documents shape this adapter, and each of them was
found by reading the file rather than by assuming.

**The row labels are stored apart from the figures they label.** pypdf returns
a page's strings in the order the file happens to hold them, which here is
every number first and every label afterwards, in a block at the end -- and
that block is not in document order either. Pairing them by position is a
guess, and the table interleaves districts with the tehsils inside them, so a
wrong guess does not look wrong: it puts a tehsil's people on a district and
every total still adds up. pdfplumber reports each word with its box, so the
rows are rebuilt from where the words sit.

**A number can arrive as two words.** Khyber Pakhtunkhwa's 36 Parsis come back
as ``3`` and ``6``; Punjab writes 124,462,897 as ``1`` and ``24,462,897``, and
1,071,693 as ``1`` and ``,071,693``. Splitting a row on whitespace therefore
yields more values than there are columns, and every column after the split
reads one place to the left.

The gaps say which words belong together. Measured in both files, a gap inside
a value is exactly 0 points and a gap between columns is never less than 13,
so the words are rejoined before anything is placed -- which is what makes the
placing unambiguous, because a fragment on its own genuinely is ambiguous: the
leading ``1`` of Punjab's Muslim column sits nearer the total column's centre
than its own.

**The columns are read off the figures, not off the header.** The header's
numbered row looks like the obvious authority and is not one. In Punjab the
numerals are set flush right with their columns, so the ``2`` heading TOTAL
POPULATION ends at x=173 and so does 127,333,305 beneath it; in Khyber
Pakhtunkhwa the same numeral ends at 157 above a column of figures ending at
177. A rule read off either file fits that file and misplaces the other, and
both were tried. The figures agree with each other where the header does not:
they are set flush right, so every value in a column ends at the same x on
every row of every page, and the nine commonest of those are the columns.

**Every area appears three times**, as ALL LOCALITIES, RURAL and URBAN, each
with four rows for the sexes. Only the first line of the first block is the
district: the rest is a breakdown of it, and summing any two of them counts
the same people twice.

Usage:
    python -m scripts.fetch_census.pakistan
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json,
)

SOURCE = "Pakistan Bureau of Statistics, 7th Population and Housing Census 2023, Table 9"
URL = "https://www.pbs.gov.pk/census-2023-tables"
LICENCE = "Pakistan Bureau of Statistics, free reuse with attribution"
YEAR = 2023

BASE = "https://www.pbs.gov.pk/wp-content/uploads/census_tables/tables"

# One file per province, and the office uses two naming schemes at once: the
# four big provinces sit under census_tables with a slug in the filename, while
# the territories appear -- when they appear at all -- under a per-province 2023
# path. The slugs are not guessable from the names ("kp", but "khyber
# pakhtunkhwa"), so each province carries the candidates to try and the run
# reports which one answered rather than costing a dispatch per guess.
#
# required=False for the three territories: Azad Jammu and Kashmir and
# Gilgit-Baltistan are enumerated apart from the census proper, so their
# absence is a fact about what Pakistan publishes rather than a fetch that went
# wrong. The four provinces are 240 of Pakistan's 241 million people, and any
# one of them missing is not a partial result worth shipping.
DCR = "https://www.pbs.gov.pk/sites/default/files/population/2023/tables"

PROVINCES: dict[str, tuple[str, bool, tuple[str, ...]]] = {
    "kp": ("Khyber Pakhtunkhwa", True, (f"{BASE}/table_9_kp_districts.pdf",)),
    "punjab": ("Punjab", True, (f"{BASE}/table_9_punjab_districts.pdf",
                                f"{DCR}/punjab/dcr/table_9.pdf")),
    "sindh": ("Sindh", True, (f"{BASE}/table_9_sindh_districts.pdf",
                              f"{DCR}/sindh/dcr/table_9.pdf")),
    "balochistan": ("Balochistan", True,
                    (f"{BASE}/table_9_balochistan_districts.pdf",
                     f"{DCR}/balochistan/dcr/table_9.pdf")),
    "ict": ("Islamabad Capital Territory", False,
            (f"{BASE}/table_9_islamabad_districts.pdf",
             f"{DCR}/islamabad/dcr/table_9.pdf")),
    "ajk": ("Azad Jammu and Kashmir", False,
            (f"{BASE}/table_9_ajk_districts.pdf",
             f"{DCR}/ajk/dcr/table_9.pdf")),
    "gb": ("Gilgit-Baltistan", False,
           (f"{BASE}/table_9_gb_districts.pdf",
            f"{DCR}/gb/dcr/table_9.pdf")),
}

# Table 9's columns, in the order the numbered header row gives them. Column 1
# is the total, which is the denominator rather than a religion.
COLUMNS = ["TOTAL", "Muslim", "Christian", "Hindu", "Ahmadi",
           "Scheduled Castes", "Sikh", "Parsi", "Other religion"]

# A row of figures belongs to one of these. Only ALL SEXES is read: the others
# are the same people split by sex.
SEXES = ("ALL SEXES", "MALE", "FEMALE", "TRANSGENDER")
LOCALITIES = ("ALL LOCALITIES", "RURAL", "URBAN")

DISTRICT = re.compile(r"^(.+?)\s+DISTRICT$")
NUMBER = re.compile(r"^[\d,]+$")


Cell = tuple[float, float, str]           # (left x, right x, text)


def words_by_row(blob: bytes, tolerance: float = 2.0):
    """Every page as rows of (left x, right x, text), from the words' boxes."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            rows: list[tuple[float, list[Cell]]] = []
            for word in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
                top = round(word["top"], 1)
                cell = (word["x0"], word["x1"], word["text"])
                if rows and abs(rows[-1][0] - top) <= tolerance:
                    rows[-1][1].append(cell)
                else:
                    rows.append((top, [cell]))
            yield [sorted(cells) for _top, cells in rows]


# A gap inside a value against a gap between columns, measured in both
# provinces with probe_pdf --boxes: within a value the gap is exactly 0
# points, between columns it is never less than 13. Four leaves margin on
# both sides, and being wrong either way is caught -- a split value and two
# merged columns both fail to sum to the printed total.
GAP = 4.0

# How far a value's right edge may sit from its column's. These are set flush
# right, so in practice the two are equal; this is for rounding.
NEAR = 3.0

SEXES_START = tuple(sex.split()[0] for sex in SEXES)


def groups(cells: list[Cell]) -> list[tuple[float, int]]:
    """A row's figures, each rejoined from its words, with where it ends.

    Rejoining first is what makes the placing unambiguous. Both provinces
    break a figure across words -- Khyber Pakhtunkhwa's 36 Parsis arrive as
    "3" and "6", Punjab writes 124,462,897 as "1" and "24,462,897" -- and
    placing those fragments one at a time is the question that had no good
    answer: the leading "1" of the Muslim column sits nearer to the total
    column's centre than to its own. Joined, the value ends where its column
    ends, and nothing has to be decided about the fragment at all.

    The digits are concatenated rather than added, so that ",071,693" behind a
    "1" reads as 1,071,693: a leading zero is a place, not a magnitude.
    """
    parts: list[list] = []
    for x0, x1, text in cells:
        if not NUMBER.match(text):            # "-" is the office's zero
            continue
        if parts and x0 - parts[-1][0] <= GAP:
            parts[-1][0] = x1
            parts[-1][1] += text.replace(",", "")
        else:
            parts.append([x1, text.replace(",", "")])
    return [(right, int(digits)) for right, digits in parts]


def figure_row(cells: list[Cell]) -> bool:
    """Whether this row carries figures rather than a heading or a label."""
    return bool(cells) and cells[0][2] in SEXES_START


def column_edges(pages: list[list[list[Cell]]],
                 province: str) -> list[tuple[float, float]]:
    """Where each column ends, learned from the figures themselves.

    Not from the header. Its numbered row looks like the obvious authority and
    is not one: in Punjab the numerals are set flush right with their columns,
    so the "2" heading TOTAL POPULATION ends at 173 and so does 127,333,305
    beneath it -- but in Khyber Pakhtunkhwa the same numeral ends at 157 above
    a column of figures ending at 177. A rule read off either file fits that
    file and misplaces the other, and both were tried.

    The figures agree with each other where the header does not. They are set
    flush right, so every value in a column ends within a point or two of the
    same x, on every row and every page.

    A band rather than a single x, because a column has two families of figure
    in it: the province is written 40,641,120 and its districts 1397587,
    without the separators, and the two end two points apart. Taking the
    middle of the band and allowing a fixed tolerance around it put Abbottabad
    outside its own column, so the band is carried and a figure is asked to
    fall inside it.

    Counted by how often each edge occurs, so that a column mostly filled with
    the office's dash still has hundreds of rows saying where it is.
    """
    tally: dict[int, int] = {}
    for rows in pages:
        for cells in rows:
            if not figure_row(cells):
                continue
            for right, _value in groups(cells):
                tally[round(right)] = tally.get(round(right), 0) + 1

    # Adjacent x are one column's band. Columns sit some forty points apart
    # and a band spans a few, so nothing here can bridge two of them.
    bands: list[list[int]] = []
    for x in sorted(tally):
        if bands and x - bands[-1][-1] <= NEAR:
            bands[-1].append(x)
        else:
            bands.append([x])
    weighed = sorted(((sum(tally[x] for x in band), band) for band in bands),
                     reverse=True)

    if len(weighed) < len(COLUMNS):
        raise SystemExit(
            f"{province}: {len(weighed)} column edges in the figures, wanted "
            f"{len(COLUMNS)} -- the table is not shaped the way this reads it")
    # Anything else that occurs often is a tenth column, and a tenth column
    # means the reading is wrong rather than that one row is odd.
    rest = weighed[len(COLUMNS):]
    if rest and rest[0][0] > weighed[len(COLUMNS) - 1][0] / 10:
        raise SystemExit(
            f"{province}: a tenth column ending near x={rest[0][1][0]} occurs "
            f"{rest[0][0]} times against {weighed[len(COLUMNS) - 1][0]} for "
            "the least common of the nine taken")
    return sorted((float(band[0]), float(band[-1]))
                  for _count, band in weighed[:len(COLUMNS)])


def describe(edges: list[tuple[float, float]]) -> str:
    return ", ".join(f"{lo:.0f}" if lo == hi else f"{lo:.0f}-{hi:.0f}"
                     for lo, hi in edges)


def values(cells: list[Cell], edges: list[tuple[float, float]], province: str,
           where: str) -> list[int] | None:
    """One row's figures, each put in the column it ends inside."""
    out = [0] * len(edges)
    seen = False
    for right, value in groups(cells):
        index = min(range(len(edges)),
                    key=lambda i: abs((edges[i][0] + edges[i][1]) / 2 - right))
        lo, hi = edges[index]
        if not lo - NEAR <= right <= hi + NEAR:
            # Never quietly dropped: a figure that belongs to no column is
            # either a column this reader does not know about or a value that
            # has been torn in half, and both of those are wrong answers
            # rather than missing ones.
            raise SystemExit(
                f"{province}: {where} has a figure of {value:,} ending at "
                f"x={right:.0f}, which is no column of this table -- the "
                f"nearest ends at {lo:.0f}-{hi:.0f}")
        out[index] = value
        seen = True
    return out if seen else None


def districts(blob: bytes, province: str) -> dict[str, dict[str, int]]:
    """{district: {religion: count}} for one province's Table 9.

    Walks the rows in document order. A "X DISTRICT" line opens a district; the
    first ALL SEXES row after it, inside the first ALL LOCALITIES block, is its
    whole population. Everything after that -- the RURAL and URBAN repeats, the
    per-sex rows, and every TEHSIL -- is a breakdown of something already
    counted, so the district closes as soon as its one row is read.
    """
    # Two passes over each page, because where the columns are is a fact
    # about the page and cannot be settled from the row in hand -- and it is
    # a fact about the page rather than about the file: the table sits at its
    # own horizontal offset on every page, so Khyber Pakhtunkhwa's columns end
    # at 177-179 on page 1 and elsewhere twenty points to the left. Learned
    # across the document, the commonest edges were a mixture of offsets that
    # matched no page, and page 1's own figures were refused as belonging to
    # no column.
    found: dict[str, dict[str, int]] = {}
    current: str | None = None
    locality: str | None = None
    skipped_tehsils = 0
    geometries: list[tuple[tuple[float, float], ...]] = []

    for rows in words_by_row(blob):
        edges: list[tuple[float, float]] | None = None
        for cells in rows:
            line = " ".join(t for _a, _b, t in cells)

            match = DISTRICT.match(line)
            if match:
                current, locality = match.group(1).strip(), None
                continue
            if line.endswith("TEHSIL"):
                skipped_tehsils += 1
                current, locality = None, None      # a part, not a unit
                continue
            if line in LOCALITIES:
                locality = line
                continue
            if not current or locality != "ALL LOCALITIES":
                continue
            # The label is two words and the row is a list of words, so
            # comparing the first of them to "ALL SEXES" could never be true:
            # it read "ALL", found it in no list, and skipped every figure in
            # the file while still counting the tehsils it passed over.
            if not line.startswith("ALL SEXES"):
                continue
            if edges is None:
                # Read when the page first has something to place, so a page
                # this reader cannot make sense of is only fatal if a district
                # is actually on it.
                edges = column_edges([rows], province)
                geometries.append(tuple(edges))
            numbers = values(cells, edges, province, current)
            if numbers and current not in found:
                found[current] = dict(zip(COLUMNS, numbers))
            current = None                          # one row per district

    if geometries:
        log(f"    {len(set(geometries))} column layouts over "
            f"{len(geometries)} pages of districts; the first ends at "
            f"{describe(list(geometries[0]))}")
    log(f"    {len(found)} districts, {skipped_tehsils} tehsils passed over")
    return found


def check(province: str, found: dict[str, dict[str, int]]) -> None:
    """Each district's religions must add up to the total printed beside it.

    Table 9 publishes the denominator in its own first column, so this is the
    source's own control rather than one this adapter invents: a column read
    one place to the left still sums to something, but not to that.
    """
    bad = []
    for name, counts in found.items():
        total = counts["TOTAL"]
        parts = sum(v for k, v in counts.items() if k != "TOTAL")
        if not total:
            bad.append(f"{name}: no total")
        elif abs(parts - total) > max(1, 0.001 * total):
            bad.append(f"{name}: religions sum to {parts:,} against a "
                       f"printed {total:,}")
    if bad:
        raise SystemExit(f"{province}: {len(bad)} districts do not reconcile — "
                         + "; ".join(bad[:4]))
    log(f"    every district's religions sum to its own printed total")


def fetch(candidates: tuple[str, ...]) -> tuple[bytes, str]:
    """The first candidate URL that answers, and which one it was.

    The office files the same table under two paths and neither is derivable
    from the province's name, so the run tries each and reports the one that
    worked. Every failure is carried: a province reported missing should name
    what was actually asked for, not just the last thing tried.
    """
    import urllib.request

    failures = []
    for url in candidates:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; DemographicMap/1.0; "
                          "+https://github.com/advaitsridhar/DemographicMap)",
            "Accept": "application/pdf,*/*",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read(), url
        except Exception as err:                      # noqa: BLE001
            failures.append(f"{url.rsplit('/', 1)[-1]}: "
                            f"{type(err).__name__} {str(err)[:50]}")
    raise LookupError("; ".join(failures))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    log("pakistan: Bureau of Statistics, Census 2023 Table 9")
    records: list[dict[str, Any]] = []
    absent: dict[str, list[str]] = {"required": [], "optional": []}
    for slug, (province, required, candidates) in PROVINCES.items():
        log(f"  {province}")
        try:
            blob, url = fetch(candidates)
        except LookupError as err:
            # Named, not skipped: a province quietly absent is tens of millions
            # of people quietly absent, and the file naming is the office's own.
            absent["required" if required else "optional"].append(
                f"{province}: {err}")
            continue
        log(f"    {len(blob):,} bytes from {url}")
        found = districts(blob, province)
        if not found:
            absent["required" if required else "optional"].append(
                f"{province}: fetched but no districts read")
            continue
        check(province, found)
        for name, counts in sorted(found.items()):
            total = counts["TOTAL"]
            parts = {k: v for k, v in counts.items() if k != "TOTAL"}
            records.append(record(
                f"PAK-{slug}-{name.lower().replace(' ', '-')}",
                name.title(), level="admin2", parent="PAK",
                parent_name=province,
                population=measure(total, year=YEAR, source=SOURCE),
                religion=shares(parts, total=total) or gap(NOT_AVAILABLE),
                religion_year=YEAR,
                religion_note=(
                    "Census 2023 Table 9. 'Scheduled Castes' is counted "
                    "separately from Hindu in this table, as the census does, "
                    "and Ahmadis are recorded as a category of their own "
                    "rather than within Islam."),
                sources=[{"field": "population/religion", "name": SOURCE,
                          "url": URL, "license": LICENCE}]))
    for line in absent["optional"]:
        log(f"  NOT READ (territory, enumerated apart) -- {line}")
    for line in absent["required"]:
        log(f"  NOT READ -- {line}")
    if absent["required"]:
        raise SystemExit(f"{len(absent['required'])} of Pakistan's four "
                         "provinces were not read; refusing to write a "
                         "partial Pakistan")
    out = args.out or PROCESSED / "pakistan_district.json"
    write_json(out, records)
    log(f"  {len(records)} districts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
