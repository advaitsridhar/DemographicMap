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
as ``3`` and ``6`` with a gap between them, because the digits are set wide
enough that the extractor calls them separate words. Splitting a row on
whitespace therefore yields ten values where nine are expected, and every
column after the split reads one place to the left. The header carries a
numbered row -- ``1 2 3 4 5 6 7 8 9 10`` -- so each column has a published x
position, and a value is assigned to the column it sits under rather than to
the place it happens to fall in a list.

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


HEADINGS = len(COLUMNS) + 1               # the figures, plus the label column

# A word may end a whisker past its column's right edge. Points, not columns:
# wide enough for rounding, far narrower than the gap between two columns.
SLACK = 1.5


def numbered(cells: list[Cell]) -> list[float] | None:
    """The right edge of each column, from a row that counts 1, 2, … 10.

    Counted rather than compared word for word, because the header is subject
    to the same splitting as the figures below it: Punjab's reads

        1 2 3 4 5 6 7 8 9 1 0

    -- eleven words for ten columns, the last two being one "10" set wide
    enough that the extractor calls them separate words. Matching the list of
    words against ["1", … "10"] therefore found Khyber Pakhtunkhwa's header
    and refused Punjab's, which is 128 million people.

    So the digits are accumulated until they read as the number being looked
    for, and the column ends where the last word of that number ends.
    """
    spans: list[float] = []
    wanted, digits = 1, ""
    for _x0, x1, text in cells:
        if wanted > HEADINGS:
            break
        if not text.isdigit():
            return None
        digits += text
        if digits == str(wanted):
            spans.append(x1)
            wanted, digits = wanted + 1, ""
        elif not str(wanted).startswith(digits):
            return None
    return spans if wanted > HEADINGS else None


def column_edges(rows, near: list[str] | None = None) -> list[float] | None:
    """Where every column ends, the label column included at the front.

    The numerals are right-aligned with the columns they head, which is what
    makes them usable: the "2" heading TOTAL POPULATION ends at 173 and so
    does 127,333,305 beneath it; the "3" heading MUSLIM ends at 221 and so
    does 124,462,897. A figure therefore belongs to the first column whose
    right edge is at or after the figure's own.

    Measured rather than assumed, and the first two guesses were both wrong.
    Reading nine anchors off the front of a list of ten put the row label
    where TOTAL POPULATION should have been and shifted every figure one place
    left. Then matching each word to the nearest column centre read Khyber
    Pakhtunkhwa correctly and put Punjab's totals out by a factor of ten:
    Punjab writes 124,462,897 as "1" and "24,462,897", and that leading "1"
    sits at 186-190 -- clear of TOTAL's right edge at 173, so unambiguously in
    the MUSLIM column, but nearer to TOTAL's centre than to MUSLIM's. Right
    edges say which column a figure is in; centres say which one it is nearest
    to, and for a column of right-aligned numbers those are different
    questions.
    """
    for cells in rows:
        spans = numbered(cells)
        if spans:
            return spans
        # A row that starts to count and then does not match is the thing
        # worth seeing when this fails, so it is carried out to the error
        # rather than costing a separate run to go and look at the page.
        if near is not None and [t for _a, _b, t in cells][:2] == ["1", "2"]:
            near.append(" ".join(t for _a, _b, t in cells[:16]))
    return None


def column_of(x1: float, edges: list[float]) -> int | None:
    """The column a word ends inside, or None if it ends past the last one."""
    for index, edge in enumerate(edges):
        if x1 <= edge + SLACK:
            return index
    return None


def values(cells: list[Cell], edges: list[float]) -> list[int] | None:
    """One row's figures, each put in the column it ends inside."""
    out = [0] * (len(edges) - 1)
    seen = [False] * (len(edges) - 1)
    for _x0, x1, text in cells:
        if text == "-":                       # the office's zero
            continue
        if not NUMBER.match(text):
            continue
        column = column_of(x1, edges)
        # Column 0 is AREA/SEX, the row label: nothing that lands there is a
        # figure, and dropping it is also what stops a figure being assigned
        # to it. None is a word ending past the last column, which is not one
        # of these tables' figures either.
        if not column:
            continue
        index = column - 1
        # Shifted by the width of what follows rather than by its magnitude:
        # Punjab writes 1,071,693 as "1" and ",071,693", and a leading zero
        # read as a magnitude loses a place.
        digits = text.replace(",", "")
        out[index] = out[index] * 10 ** len(digits) + int(digits) if seen[index] \
            else int(digits)
        seen[index] = True
    return out if any(seen) else None


def districts(blob: bytes, province: str) -> dict[str, dict[str, int]]:
    """{district: {religion: count}} for one province's Table 9.

    Walks the rows in document order. A "X DISTRICT" line opens a district; the
    first ALL SEXES row after it, inside the first ALL LOCALITIES block, is its
    whole population. Everything after that -- the RURAL and URBAN repeats, the
    per-sex rows, and every TEHSIL -- is a breakdown of something already
    counted, so the district closes as soon as its one row is read.
    """
    found: dict[str, dict[str, int]] = {}
    edges: list[float] | None = None
    current: str | None = None
    locality: str | None = None
    skipped_tehsils = 0
    near: list[str] = []

    for cells in words_by_row(blob):
        edges = edges or column_edges(cells, near)
        for row in cells:
            text = [t for _a, _b, t in row]
            line = " ".join(text)

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
            # comparing text[0] to "ALL SEXES" could never be true: it read
            # "ALL", found it in no list, and skipped every figure in the file
            # while still counting the tehsils it passed over.
            if not line.startswith("ALL SEXES"):
                continue
            if edges is None:
                raise SystemExit(
                    f"{province}: no numbered header row, so no column "
                    "positions -- every figure would be placed by counting "
                    "rather than by where it sits. Rows that begin to count: "
                    + ("; ".join(repr(n) for n in near[:3]) if near
                       else "none at all"))
            numbers = values(row, edges)
            if numbers and current not in found:
                found[current] = dict(zip(COLUMNS, numbers))
            current = None                          # one row per district
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
