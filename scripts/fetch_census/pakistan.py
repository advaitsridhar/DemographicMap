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

**A number can arrive as several words.** Khyber Pakhtunkhwa's 36 Parsis come
back as ``3`` and ``6``; Punjab writes 124,462,897 as ``1`` and ``24,462,897``,
and 1,071,693 as ``1`` and ``,071,693``. Splitting a row on whitespace
therefore yields more values than there are columns, and every column after
the split reads one place to the left.

The gaps say which words belong together. Measured in both files, a gap inside
a value is exactly 0 points and a gap between columns is never less than 13,
so the words are rejoined before anything else happens.

**Where the columns are is not a fact this document has.** Three rules were
tried on position and each fitted the file it was read off. The header's
numerals are set flush right with their columns in Punjab -- the ``2`` heading
TOTAL POPULATION ends at x=173 and so does 127,333,305 beneath it -- and
twenty points to their left in Khyber Pakhtunkhwa. The figures themselves are
flush right, but the table sits at its own horizontal offset on every page.
And within a single page: page 2 of Khyber Pakhtunkhwa carries two offsets at
once, 37 rows at one and 12 at the other.

What the table does print, every time, is nine cells to a row with nothing
left out -- the office writes a dash where a religion is absent rather than
leaving the cell empty. So the cells are counted, dash included, and a row
that does not have nine of them is refused rather than trimmed to fit.

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
# both sides, and being wrong either way is caught -- two columns merged and
# one value torn in half both change how many cells the row has.
GAP = 4.0

DASH = "-"                                # the office's zero


def printed(cells: list[Cell]) -> list[int]:
    """A row's cells as the table prints them, in order.

    The words are rejoined by the gaps between them, and the office's dash is
    a cell like any other. Together those two make counting sound, which it
    was not before: splitting the row on whitespace yielded ten values where
    nine were expected, because a figure can arrive as several words --
    Khyber Pakhtunkhwa's 36 Parsis as "3" and "6", Punjab's 124,462,897 as
    "1" and "24,462,897", its 1,071,693 as "1" and ",071,693".

    Position is deliberately not used. Three rules were tried on it and each
    fitted the file it was read off: the header's numerals are flush right
    with their columns in Punjab and twenty points left of them in Khyber
    Pakhtunkhwa; the figures are flush right, but the table sits at its own
    offset on each page; and even within one page, page 2 of Khyber
    Pakhtunkhwa carries two offsets at once, 37 rows at one and 12 at the
    other. There is no fact about where a column is that holds across this
    document. There is a fact about what the table prints: nine cells to a
    row, every time, with nothing left out.

    The digits are concatenated rather than added, so that ",071,693" behind
    a "1" reads as 1,071,693: a leading zero is a place, not a magnitude.
    """
    out: list[list] = []                  # [right edge, digits or None]
    for x0, x1, text in cells:
        if text == DASH:
            out.append([x1, None])
            continue
        if not NUMBER.match(text):        # a row label
            continue
        if out and out[-1][1] is not None and x0 - out[-1][0] <= GAP:
            out[-1][0] = x1
            out[-1][1] += text.replace(",", "")
        else:
            out.append([x1, text.replace(",", "")])
    return [0 if digits is None else int(digits) for _right, digits in out]


def values(cells: list[Cell], province: str, where: str) -> list[int] | None:
    """One row's figures, or None if the row carries none."""
    figures = printed(cells)
    if not figures:
        return None
    if len(figures) != len(COLUMNS):
        # Refused rather than padded or truncated. A row with the wrong
        # number of cells is a row this reader has misread, and guessing
        # which end to trim is how a district ends up with another
        # district's religions while every total still adds up.
        raise SystemExit(
            f"{province}: {where} has {len(figures)} cells where the table "
            f"has {len(COLUMNS)}: {figures}")
    return figures


def districts(blob: bytes,
              province: str) -> tuple[dict[str, dict[str, int]], list[int]]:
    """{district: {religion: count}} for one province's Table 9, and its own.

    The province's own row is the first ALL SEXES line in the file, before any
    district heading, and it is worth keeping: it is the file's own statement
    of what its districts ought to add up to.

    Walks the rows in document order. A "X DISTRICT" line opens a district; the
    first ALL SEXES row after it, inside the first ALL LOCALITIES block, is its
    whole population. Everything after that -- the RURAL and URBAN repeats, the
    per-sex rows, and every TEHSIL -- is a breakdown of something already
    counted, so the district closes as soon as its one row is read.
    """
    found: dict[str, dict[str, int]] = {}
    whole: list[int] = []
    current: str | None = None
    locality: str | None = None
    skipped_tehsils = 0

    for rows in words_by_row(blob):
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
            if locality != "ALL LOCALITIES":
                continue
            if not current:
                # Before the first district heading, and only then, this is
                # the province's own row.
                if not found and not whole and line.startswith("ALL SEXES"):
                    whole.extend(values(cells, province, province) or [])
                continue
            # The label is two words and the row is a list of words, so
            # comparing the first of them to "ALL SEXES" could never be true:
            # it read "ALL", found it in no list, and skipped every figure in
            # the file while still counting the tehsils it passed over.
            if not line.startswith("ALL SEXES"):
                continue
            numbers = values(cells, province, current)
            if numbers and current not in found:
                found[current] = dict(zip(COLUMNS, numbers))
            current = None                          # one row per district

    log(f"    {len(found)} districts, {skipped_tehsils} tehsils passed over")
    return found, whole


def check(province: str, found: dict[str, dict[str, int]],
          whole: list[int]) -> None:
    """Two controls the file supplies itself, neither of them invented here.

    Each district's religions must add up to the total printed beside it: a
    column read one place to the left still sums to something, but not to
    that.

    And the districts must add up to the province printed above them. That
    one matters more, because a district this reader never noticed is not a
    wrong number anywhere -- it is a hole, and every other check passes over
    it in silence. Khyber Pakhtunkhwa read 34 districts that each reconciled
    perfectly and were 825,377 people short of their own province.
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
    log("    every district's religions sum to its own printed total")

    if not whole:
        raise SystemExit(
            f"{province}: no province row, so nothing says whether these "
            f"{len(found)} districts are all of them")
    counted = sum(counts["TOTAL"] for counts in found.values())
    if counted != whole[0]:
        raise SystemExit(
            f"{province}: {len(found)} districts hold {counted:,} people "
            f"against the {whole[0]:,} printed for the province — "
            f"{whole[0] - counted:+,}. Read: "
            + ", ".join(sorted(found)))
    log(f"    and the {len(found)} districts add up to the province")


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
        found, whole = districts(blob, province)
        if not found:
            absent["required" if required else "optional"].append(
                f"{province}: fetched but no districts read")
            continue
        check(province, found, whole)
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
