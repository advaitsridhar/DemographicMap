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

# One file per province. The slugs are the office's own and are not guessable
# from the province names -- "kp" but "khyber pakhtunkhwa", "ict" for the
# capital territory -- so a 404 here is reported by name rather than skipped,
# because a province quietly missing is 40 million people quietly missing.
PROVINCES = {
    "kp": "Khyber Pakhtunkhwa",
    "punjab": "Punjab",
    "sindh": "Sindh",
    "balochistan": "Balochistan",
    "ict": "Islamabad Capital Territory",
    "ajk": "Azad Jammu and Kashmir",
    "gb": "Gilgit-Baltistan",
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


def words_by_row(blob: bytes, tolerance: float = 2.0):
    """Every page as rows of (x, text), rebuilt from the words' positions."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            rows: list[tuple[float, list[tuple[float, str]]]] = []
            for word in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
                top = round(word["top"], 1)
                if rows and abs(rows[-1][0] - top) <= tolerance:
                    rows[-1][1].append((word["x0"], word["text"]))
                else:
                    rows.append((top, [(word["x0"], word["text"])]))
            yield [sorted(cells) for _top, cells in rows]


def column_anchors(rows) -> list[float] | None:
    """The x of each numbered column heading, from the header's own "1 2 3 …".

    Read rather than assumed: the anchors are what makes a value that arrived
    as two words land in one column instead of shifting every column after it.
    """
    for cells in rows:
        text = [t for _x, t in cells]
        if text[:3] == ["1", "2", "3"] and len(text) >= len(COLUMNS):
            return [x for x, _t in cells][:len(COLUMNS)]
    return None


def values(cells, anchors: list[float]) -> list[int] | None:
    """One row's figures, each put under the column it sits beneath."""
    out = [0] * len(anchors)
    seen = [False] * len(anchors)
    for x, text in cells:
        if text == "-":                       # the office's zero
            continue
        if not NUMBER.match(text):
            continue
        # Nearest anchor at or before this word, so a value split across two
        # words lands twice in the same column and is joined, not shifted.
        index = min(range(len(anchors)), key=lambda i: abs(anchors[i] - x))
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
    anchors: list[float] | None = None
    current: str | None = None
    locality: str | None = None
    skipped_tehsils = 0

    for cells in words_by_row(blob):
        anchors = anchors or column_anchors(cells)
        for row in cells:
            text = [t for _x, t in row]
            line = " ".join(text)

            match = DISTRICT.match(line)
            if match:
                current, locality = match.group(1).strip(), None
                continue
            if line.endswith("TEHSIL"):
                if current:
                    skipped_tehsils += 1
                current, locality = None, None      # a part, not a unit
                continue
            if line in LOCALITIES:
                locality = line
                continue
            if not current or locality != "ALL LOCALITIES":
                continue
            if not text or text[0] not in SEXES:
                continue
            if text[0] != "ALL SEXES":
                continue
            if anchors is None:
                raise SystemExit(
                    f"{province}: no numbered header row, so no column "
                    "positions -- every figure would be placed by counting "
                    "rather than by where it sits")
            numbers = values(row, anchors)
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


def main() -> int:
    import urllib.request

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    log("pakistan: Bureau of Statistics, Census 2023 Table 9")
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for slug, province in PROVINCES.items():
        url = f"{BASE}/table_9_{slug}_districts.pdf"
        log(f"  {province}")
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; DemographicMap/1.0; "
                          "+https://github.com/advaitsridhar/DemographicMap)",
            "Accept": "application/pdf,*/*",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                blob = resp.read()
        except Exception as err:                      # noqa: BLE001
            # Named, not skipped: a province quietly absent is tens of millions
            # of people quietly absent, and the file naming is the office's own.
            missing.append(f"{province} ({url.rsplit('/', 1)[-1]}): "
                           f"{type(err).__name__} {str(err)[:60]}")
            continue
        log(f"    {len(blob):,} bytes")
        found = districts(blob, province)
        if not found:
            missing.append(f"{province}: fetched but no districts read")
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
    for line in missing:
        log(f"  NOT READ -- {line}")
    if missing:
        raise SystemExit(f"{len(missing)} of {len(PROVINCES)} provinces were "
                         "not read; refusing to write a partial Pakistan")
    out = args.out or PROCESSED / "pakistan_district.json"
    write_json(out, records)
    log(f"  {len(records)} districts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
