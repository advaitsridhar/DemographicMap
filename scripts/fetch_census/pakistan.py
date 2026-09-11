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

**Islamabad's file is named for being one district, and so is its contents.**
The provinces are filed as ``table_9_<slug>_districts.pdf``; the capital is
``table_9_islamabad.pdf``, without the word, because it has no districts
under it -- it is one. For the same reason its file prints no territory row
above the district, so the one control every province file supplies is not in
it, and ``ONE_DISTRICT`` says which province that is true of rather than
letting a missing row pass anywhere it turns up.

This module asked for the name the scheme implied, got 404 twice, and filed
the capital under "not published" -- where it stayed for two census rounds,
2.3 million people with no religion and no population on the map. A guessed
URL that 404s and a table that was never published are the same observation,
and the only thing that separates them is asking again.

**Azad Jammu and Kashmir and Gilgit-Baltistan are genuinely not published.**
Six filenames were tried for each, the office answered 404 to all twelve, and
their own statistical booklets -- which do carry district tables from this
census -- do not contain the word religion anywhere. They get a record saying
so rather than an empty field, because an empty field reads as a fetch nobody
has run yet.

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
LICENCE = "Pakistan Bureau of Statistics, free reuse with attribution"
YEAR = 2023

# There is no landing page to cite. https://www.pbs.gov.pk/census-2023-tables,
# which this module cited until now and which docs/SOURCES.md still names as
# the way to find these files, answers 404 -- measured three times on the
# runner, along with /census-2023, /census_tables and
# /digital-census/detailed-results. The table files themselves answer 200 and
# are what the figures were read from, so every record now cites the file it
# came from rather than an index that no longer exists.
URL = "https://www.pbs.gov.pk/wp-content/uploads/census_tables/tables/"

PROVINCE_NOTE = (
    "Census 2023 Table 9, the province's own printed row rather than a sum of "
    "the districts below it. The two are the same figure -- the run checks "
    "that every district adds up to this exactly -- but the printed row also "
    "covers the districts geoBoundaries has no shape for, which a sum of what "
    "landed on the map would silently leave out.")

# Islamabad's file has no province row to be the province's own: the territory
# is one district and the table prints that district once. So the figure is
# the district's, and saying "rather than a sum of the districts below it"
# would describe a file this one is not.
TERRITORY_NOTE = (
    "Census 2023 Table 9. Islamabad Capital Territory is a single district, so "
    "the table prints one row for it rather than a territory row above a list "
    "of districts: this figure and the district's inside it are the same "
    "printed row.")

NOTE = ("Census 2023 Table 9. 'Scheduled Castes' is counted separately from "
        "Hindu in this table, as the census does, and Ahmadis are recorded as "
        "a category of their own rather than within Islam. The population is "
        "the table's own TOTAL POPULATION column, which is the denominator "
        "these shares are of.")

BASE = "https://www.pbs.gov.pk/wp-content/uploads/census_tables/tables"

# One file per province, and the slugs are not guessable from the names ("kp",
# but "khyber pakhtunkhwa"), so each province carries the candidates to try and
# the run reports which one answered rather than costing a dispatch per guess.
#
# Islamabad's is the one that was guessed wrong. The four provinces are
# table_9_<slug>_districts.pdf and this module read "districts" as part of the
# scheme, so it asked for table_9_islamabad_districts.pdf, got 404 from that
# and from a second path, and filed the capital under "not published". The
# office writes table_9_islamabad.pdf: the file drops the word because
# Islamabad has no districts under it, being one. Two years of the capital's
# religion sat behind a filename.
#
# The lesson is in what the two 404s could not tell apart, which is the same
# thing probe_links exists for: a guessed URL that 404s and a table that was
# never published are the same observation, and only a third fetch separates
# them. These candidate lists are now what the runner actually measured --
# table_9_islamabad.pdf 200, 36,012 bytes; table_9_ajk.pdf, table_9_gb.pdf,
# table_9_ajk_districts.pdf, table_9_gb_districts.pdf,
# table_9_gilgit_baltistan.pdf and table_9_azad_jammu_kashmir.pdf all 404.
DCR = "https://www.pbs.gov.pk/sites/default/files/population/2023/tables"

# What an absent file means, which is not one question for all seven.
REQUIRED = "required"     # 238 of Pakistan's 241 million; nothing is written without it
PUBLISHED = "published"   # the office publishes it; an absence is a fault to name
APART = "apart"           # enumerated apart from the census proper: not published here

PROVINCES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "kp": ("Khyber Pakhtunkhwa", REQUIRED,
           (f"{BASE}/table_9_kp_districts.pdf",)),
    "punjab": ("Punjab", REQUIRED, (f"{BASE}/table_9_punjab_districts.pdf",
                                    f"{DCR}/punjab/dcr/table_9.pdf")),
    "sindh": ("Sindh", REQUIRED, (f"{BASE}/table_9_sindh_districts.pdf",
                                  f"{DCR}/sindh/dcr/table_9.pdf")),
    "balochistan": ("Balochistan", REQUIRED,
                    (f"{BASE}/table_9_balochistan_districts.pdf",
                     f"{DCR}/balochistan/dcr/table_9.pdf")),
    "ict": ("Islamabad Capital Territory", PUBLISHED,
            (f"{BASE}/table_9_islamabad.pdf",
             f"{BASE}/table_9_islamabad_districts.pdf",
             f"{DCR}/islamabad/dcr/table_9.pdf")),
    "ajk": ("Azad Jammu and Kashmir", APART,
            (f"{BASE}/table_9_ajk.pdf",
             f"{BASE}/table_9_ajk_districts.pdf",
             f"{DCR}/ajk/dcr/table_9.pdf")),
    "gb": ("Gilgit-Baltistan", APART,
           (f"{BASE}/table_9_gb.pdf",
            f"{BASE}/table_9_gb_districts.pdf",
            f"{DCR}/gb/dcr/table_9.pdf")),
}

# What the two territories get instead of figures, and why. Every clause in it
# is something the runner measured rather than something inferred from their
# status:
#
#   * the census-table series carries no file for either, under any of the six
#     names the four provinces and Islamabad are filed under;
#   * their own Planning & Development departments do publish district tables
#     drawn from the 2023 census -- AJK At a Glance 2025 (4.9 MB) and GB At a
#     Glance 2025, both fetched and read -- and neither booklet contains the
#     word religion, tongue, Muslim or Christian anywhere in it;
#   * the 2017 round says the same thing from the other direction: the U.S.
#     Census Bureau's workbook of that census lists both territories and
#     leaves every figure blank.
#
# not_available rather than not_collected, and the difference matters. Pakistan
# does ask religion and mother tongue, and asked them here: the 2023 count
# covered both territories. What is missing is the publication, not the
# question, and not_collected would say the state never asked.
TERRITORY_GAP = (
    "The 7th Population and Housing Census 2023 enumerated Azad Jammu and "
    "Kashmir and Gilgit-Baltistan apart from the census proper -- their people "
    "are outside the 241.5 million Pakistan reports -- and the Bureau of "
    "Statistics publishes no Table 9 (religion) or Table 11 (mother tongue) "
    "for either: the four provinces and Islamabad have both and these two have "
    "neither, at any path the office uses. Their own Planning & Development "
    "departments publish district tables from the same census, and those carry "
    "population without ever naming a religion or a mother tongue. The 2017 "
    "round is no better: its subnational workbook lists both territories and "
    "leaves them blank. The question was asked; the answer is unpublished.")

# Azad Jammu and Kashmir's own government publishes what the Bureau's census
# tables do not. The AJ&K Statistical Year Book 2023 carries two religion
# tables from the 2017 census -- 15.23 for the territory rural and urban, and
# 15.24 by district -- and 15.24 is read here because it is the one that can be
# checked: its ten districts sum to its own territory row, column by column.
#
# This is the territory's Bureau of Statistics reprinting a Pakistan Bureau of
# Statistics census table, which is why the record names the census as its
# source and the yearbook as where it was read. The same standard the
# Wikipedia-transcription route in wiki_census.py is held to, met by a
# government publication rather than by an encyclopaedia.
#
# 2017 and not 2023: the yearbook is dated 2023 and its religion tables cite
# the 2017 census, which is the year the records carry. A publication date is
# not a reference year, and reading the cover instead of the source line is
# how a nineteen-year-old figure gets stamped as current.
AJK_BOOK = ("https://pndajk.gov.pk/uploadfiles/downloads/"
            "AJ&K%20Statistical%20Year%20Book%202023(1).pdf")
AJK_SOURCE = ("Pakistan Bureau of Statistics, Population and Housing Census "
              "2017, Table: District wise Population of AJ&K by Religion, as "
              "printed in the AJ&K Statistical Year Book 2023 (Bureau of "
              "Statistics, P&DD, Azad Government of the State of Jammu & "
              "Kashmir)")
AJK_LICENCE = "Azad Government of the State of Jammu & Kashmir, P&DD"
AJK_YEAR = 2017
AJK_TABLE = re.compile(r"District\s*wise\s*Population\s*of\s*AJ&K\s*by\s*"
                       r"Religion", re.I)
AJK_WHOLE = "AJ&K"
# The printed order, which is not Table 9's: there the total comes first and
# here it comes last. The names are this project's, so that the AJ&K rows and
# the four provinces' land in the same groups -- the yearbook writes
# "Qadiani/Ahmadi" and "Scheduled Caste" for what Table 9 calls Ahmadi and
# Scheduled Castes.
AJK_COLUMNS = ["Muslim", "Hindu", "Christian", "Ahmadi", "Scheduled Castes",
               "Other religion", "TOTAL"]
AJK_DISTRICTS = ("Muzaffarabad", "Neelum", "Jhelum Valley", "Bagh", "Haveli",
                 "Poonch", "Sudhnoti", "Kotli", "Mirpur", "Bhimber")

AJK_NOTE = (
    "Population and Housing Census 2017, as reprinted by the AJ&K Bureau of "
    "Statistics in its Statistical Year Book 2023. Azad Jammu and Kashmir is "
    "enumerated apart from the census proper -- its people are outside the "
    "241.5 million Pakistan reports -- and the Bureau of Statistics publishes "
    "no Table 9 for it, so this comes from the territory's own government "
    "rather than from the same file as the four provinces. The categories are "
    "the census's own: Ahmadis are counted separately from Muslims and "
    "Scheduled Castes separately from Hindus.")
AJK_ONE_SHAPE = (
    "geoBoundaries draws one second-level unit for the whole territory where "
    "the yearbook counts ten districts, so this is the territory's figure on "
    "the territory's shape rather than any one district's.")
AJK_LANGUAGE_GAP = (
    "Mother tongue is the field Azad Jammu and Kashmir still has no source "
    "for. The Bureau of Statistics publishes no Table 11 for it, the U.S. "
    "Census Bureau's workbook of the 2017 census lists the territory and "
    "leaves it blank, and the AJ&K Statistical Year Book 2023 -- which does "
    "print the census's religion table -- contains the word 'tongue' on no "
    "page of it.")

# The name each territory is drawn under, and the second-level units inside it.
# Both lists are geoBoundaries' own spellings, because a declaration that
# reaches no shape declares nothing -- and the districts are what the map
# draws, not what the territory has: geoBoundaries gives Azad Kashmir a single
# second-level unit where its Bureau of Statistics counts ten (Muzaffarabad,
# Neelum, Jhelum Valley, Bagh, Haveli, Poonch, Sudhnoti, Kotli, Mirpur and
# Bhimber), and there is no shape here for those to land on. Gilgit-Baltistan's
# ten are drawn, and are the ten its own booklet names.
TERRITORIES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "ajk": ("Azad Jammu and Kashmir", ("Azad Kashmir",), ("Azad Kashmir",)),
    "gb": ("Gilgit-Baltistan", (),
           ("Astore", "Diamer", "Ghanche", "Ghizer", "Gilgit", "Hunza",
            "Kharmang", "Nagar", "Shigar", "Skardu")),
}

# Islamabad Capital Territory is one district, so its file prints no territory
# row above the districts -- the first ALL SEXES line in it is already inside
# ISLAMABAD DISTRICT. Declared, and only for the provinces where it is true,
# because "the province row is missing" and "the province is one district"
# look identical to a reader that simply falls back to whatever it read. The
# first of those is the Malakand case: Khyber Pakhtunkhwa's 34 districts each
# reconciled perfectly and were 825,377 people short, and the province row was
# the only thing in the file that knew. A province declared here must read
# exactly one district or it is refused.
ONE_DISTRICT = frozenset({"ict"})

# What geoBoundaries calls the same district. Declared rather than derived:
# nothing infers "Nawabshah" from "Shaheed Benazirabad" -- the district was
# renamed and the two share no word -- and a rule loose enough to bridge
# "Killa Abdullah" to "Qilla Abdullah" is loose enough to bridge things that
# are not the same place at all.
ALIASES: dict[str, tuple[str, ...]] = {
    "Batagram": ("Battagram",),
    "Jaffarabad": ("Jafarabad",),
    "Kambar Shahdad Kot": ("Qambar Shahdadkot",),
    "Killa Abdullah": ("Qilla Abdullah",),
    "Killa Saifullah": ("Qilla Saifullah",),
    "Mirpur Khas": ("Mirpurkhas",),
    "Naushahro Feroze": ("Naushehro Feroze",),
    "Shaheed Benazirabad": ("Nawabshah",),
    "Sheikhupura": ("Sheikhpura",),
    "Umer Kot": ("Umerkot",),
    "Vehari": ("Vihari",),
}

# Where the boundary file draws one shape and the census counts several
# districts inside it. Summed, and the note on each says which districts were
# summed, because the alternative is worse in both directions: matching any
# one part to the whole shape puts a fraction of the people on all of them,
# and leaving them unmatched drops Karachi -- twenty million people -- off the
# map without saying so.
#
# Each of these is a division of an older district that geoBoundaries still
# draws whole, so the parts are exactly the shape and nothing else is in it.
MERGED: dict[str, tuple[str, ...]] = {
    "CHITRAL": ("LOWER CHITRAL", "UPPER CHITRAL"),
    "KOHISTAN": ("LOWER KOHISTAN", "UPPER KOHISTAN", "KOLAI PALAS KOHISTAN"),
    "KARACHI": ("KARACHI CENTRAL", "KARACHI EAST", "KARACHI SOUTH",
                "KARACHI WEST", "KORANGI", "MALIR", "KEAMARI"),
}


# Table 9's columns, in the order the numbered header row gives them. Column 1
# is the total, which is the denominator rather than a religion.
COLUMNS = ["TOTAL", "Muslim", "Christian", "Hindu", "Ahmadi",
           "Scheduled Castes", "Sikh", "Parsi", "Other religion"]

# A row of figures belongs to one of these. Only ALL SEXES is read: the others
# are the same people split by sex.
SEXES = ("ALL SEXES", "MALE", "FEMALE", "TRANSGENDER")
LOCALITIES = ("ALL LOCALITIES", "RURAL", "URBAN")

# Not every unit at this level is called a district. Khyber Pakhtunkhwa's
# thirty-sixth is "MALAKAND PROTECTED AREA", and dropping it cost 825,377
# people who went missing without producing a single wrong figure -- which is
# why the run now makes the districts add up to their own province. Anything
# else the office names differently will be caught the same way, by the sum
# rather than by having been guessed at here.
DISTRICT = re.compile(r"^(.+?)\s+(?:DISTRICT|PROTECTED AREA)$")
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


def values(cells: list[Cell], province: str, where: str,
           columns: list[str] = COLUMNS) -> list[int] | None:
    """One row's figures, or None if the row carries none.

    ``columns`` because two tables are read here and they are not the same
    width: the Bureau's Table 9 prints nine cells to a row and the AJ&K
    yearbook's Table 15.24 prints seven. What does not change is that the row
    is counted rather than positioned, and a row of the wrong width is refused.
    """
    figures = printed(cells)
    if not figures:
        return None
    if len(figures) != len(columns):
        # Refused rather than padded or truncated. A row with the wrong
        # number of cells is a row this reader has misread, and guessing
        # which end to trim is how a district ends up with another
        # district's religions while every total still adds up.
        raise SystemExit(
            f"{province}: {where} has {len(figures)} cells where the table "
            f"has {len(columns)}: {figures}")
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


def province_row(slug: str, province: str, found: dict[str, dict[str, int]],
                 whole: list[int]) -> list[int]:
    """The row the districts have to add up to, for a file that prints one.

    Every province file prints its own row above its districts. Islamabad's
    does not, because Islamabad Capital Territory is a single district and the
    table prints that district instead -- there is no second figure to check
    against, and there is nothing missing either.

    Only where that is declared. A file that has lost its province row for any
    other reason keeps the refusal below, because a district this reader never
    noticed produces no wrong figure anywhere and the province row is the only
    thing that catches it. Declaring it costs the check, so the declaration is
    made to pay for itself: the province must read exactly one district, which
    is the thing that made the province row redundant in the first place.
    """
    if whole or slug not in ONE_DISTRICT:
        return whole
    if len(found) != 1:
        raise SystemExit(
            f"{province}: declared as a single district, so its own row is "
            f"that district's -- but the table prints {len(found)}: "
            + ", ".join(sorted(found)))
    only = next(iter(found.values()))
    log("    one district, and it is the territory: the table prints no "
        "separate territory row")
    return [only[column] for column in COLUMNS]


def merge(province: str,
          found: dict[str, dict[str, int]]) -> dict[str, tuple[str, ...]]:
    """Sum the districts that share one boundary shape. Which ones, back."""
    assembled: dict[str, tuple[str, ...]] = {}
    for name, parts in MERGED.items():
        here = [part for part in parts if part in found]
        if not here:
            continue
        if len(here) != len(parts):
            # Partial is the dangerous case: it would put a fraction of the
            # people on the whole shape and look entirely normal.
            raise SystemExit(
                f"{province}: {name} is {', '.join(parts)} and only "
                f"{', '.join(here)} were read")
        if name in found:
            raise SystemExit(
                f"{province}: {name} is both printed in the table and "
                "assembled from its parts here, so it would be counted twice")
        found[name] = {column: sum(found[part][column] for part in parts)
                       for column in COLUMNS}
        for part in parts:
            del found[part]
        assembled[name] = parts
        log(f"    {name} is one shape in the boundaries: summed "
            f"{len(parts)} districts, {found[name]['TOTAL']:,} people")
    return assembled


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


def ajk_table(blob: bytes) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """Table 15.24 of the AJ&K yearbook: ten districts and the territory row.

    Two things make this harder than it looks, and both are about *finding*
    the table rather than reading it.

    A five-hundred-page yearbook says "Muzaffarabad" on a hundred and eleven
    pages, most of them about wheat. A reader that took any row beginning with
    a district name would meet an agriculture table of six columns, refuse it
    for having the wrong width, and stop the run over a vegetable yield. So
    the table is found by its own caption, and only its page is read.

    And a caption that is not there at all is not a misread. The yearbook is
    reissued annually and this table could move or go; if no page carries the
    caption this raises LookupError, which puts Azad Jammu and Kashmir back
    where it was before -- a declared gap saying what is not published -- and
    a caption that *is* there but does not yield ten districts is a misread
    and refuses outright. The two failures must not be one failure.
    """
    for number, rows in enumerate(words_by_row(blob), start=1):
        page = [(" ".join(t for _a, _b, t in cells), cells) for cells in rows]
        if not any(AJK_TABLE.search(line) for line, _cells in page):
            continue
        found: dict[str, dict[str, int]] = {}
        whole: dict[str, int] = {}
        for line, cells in page:
            name = next((d for d in AJK_DISTRICTS
                         if line.startswith(f"{d} ")), None)
            if name is None and not line.startswith(f"{AJK_WHOLE} "):
                continue
            figures = values(cells, "Azad Jammu and Kashmir",
                             name or AJK_WHOLE, AJK_COLUMNS)
            if not figures:
                continue
            if name is None:
                whole = dict(zip(AJK_COLUMNS, figures))
            elif name not in found:
                found[name] = dict(zip(AJK_COLUMNS, figures))
        if len(found) != len(AJK_DISTRICTS) or not whole:
            raise SystemExit(
                f"AJ&K Table 15.24 is on page {number} and this read "
                f"{len(found)} of {len(AJK_DISTRICTS)} districts"
                + ("" if whole else " and no AJ&K row")
                + ": " + ", ".join(sorted(found)))
        log(f"    Table 15.24 on page {number}: {len(found)} districts")
        return found, whole
    raise LookupError("no page carries Table 15.24's caption")


def ajk_check(found: dict[str, dict[str, int]], whole: dict[str, int]) -> None:
    """The controls the page supplies, and the one place it does not add up.

    Column by column, the ten districts sum to the AJ&K row exactly -- all
    seven of them, to the person. That is the control that matters, because a
    district read wrong or missed would move one of those sums.

    Row by row, nine of the ten districts' religions sum to the total printed
    beside them and Poonch's sum to 54 more, which is also the amount by which
    the AJ&K row's own parts exceed its own total. The other religion table in
    the same yearbook, 15.23, splits AJ&K rural and urban and its Muslims come
    to 4,025,683 against 15.24's 4,025,737 -- the same 54. So the yearbook
    disagrees with itself about 54 Muslims in Poonch, out of four million
    people, and says so twice. It is logged rather than silently carried: 54
    is 0.011% of Poonch and moves no share this map prints, but a reader who
    adds the row up deserves to find the discrepancy named rather than to
    discover it.
    """
    for column in AJK_COLUMNS:
        summed = sum(counts[column] for counts in found.values())
        if summed != whole[column]:
            raise SystemExit(
                f"AJ&K: the ten districts hold {summed:,} under {column} "
                f"against the {whole[column]:,} printed for the territory — "
                f"{whole[column] - summed:+,}")
    log(f"    all {len(AJK_COLUMNS)} columns sum to the printed AJ&K row")

    for name, counts in sorted(found.items()):
        total = counts["TOTAL"]
        parts = sum(v for k, v in counts.items() if k != "TOTAL")
        if parts == total:
            continue
        if abs(parts - total) > max(1, 0.001 * total):
            raise SystemExit(
                f"AJ&K: {name}'s religions sum to {parts:,} against a printed "
                f"{total:,}")
        log(f"    {name}: religions sum to {parts - total:+,} against its own "
            f"printed total, which the yearbook's own 15.23 also shows")


def ajk_records(found: dict[str, dict[str, int]],
                whole: dict[str, int]) -> list[dict[str, Any]]:
    """Azad Jammu and Kashmir, and the one second-level shape drawn for it.

    Both from the printed territory row, which the check above has just shown
    equals the ten districts column for column. The districts themselves are
    not published as records: geoBoundaries draws Azad Kashmir as a single
    second-level unit, so ten rows would reach one shape, nine of them would
    lose, and the tenth would put a district's figures on the whole territory
    -- the Karachi failure in reverse and far worse, because it would look
    entirely normal.
    """
    total = whole["TOTAL"]
    parts = {k: v for k, v in whole.items() if k != "TOTAL"}
    cite = [{"field": "population/religion", "name": AJK_SOURCE,
             "url": AJK_BOOK, "license": AJK_LICENCE}]
    return [
        record("PAK-ajk", "Azad Jammu and Kashmir", level="admin1",
               parent="PAK", aliases=["Azad Kashmir"],
               population=measure(total, year=AJK_YEAR, source=AJK_SOURCE),
               religion=shares(parts, total=total) or gap(NOT_AVAILABLE),
               religion_year=AJK_YEAR, religion_note=AJK_NOTE,
               language=gap(NOT_AVAILABLE, AJK_LANGUAGE_GAP),
               sources=list(cite)),
        record("PAK-ajk-azad-kashmir", "Azad Kashmir", level="admin2",
               parent="PAK", parent_name="Azad Jammu and Kashmir",
               parent_aliases=["Azad Kashmir"],
               population=measure(total, year=AJK_YEAR, source=AJK_SOURCE),
               religion=shares(parts, total=total) or gap(NOT_AVAILABLE),
               religion_year=AJK_YEAR,
               religion_note=AJK_NOTE + " " + AJK_ONE_SHAPE,
               language=gap(NOT_AVAILABLE, AJK_LANGUAGE_GAP),
               sources=list(cite)),
    ]


def declared_gaps(absent: dict[str, list[tuple[str, str]]]) -> list[dict[str, Any]]:
    """Records for the territories the census tables do not reach.

    Written from the run's own failed lookups rather than from a list kept
    here, so a territory the office starts publishing loses its declaration by
    the same observation that fills it. The two cannot contradict each other
    because they are the same measurement.

    These carry no figures, which is the point: an empty field on the map
    reads as "not fetched yet", and this is not that. It is a statement about
    what Pakistan publishes, with what was asked and what answered written
    into the note.
    """
    out: list[dict[str, Any]] = []
    for slug, _line in absent[APART]:
        if slug not in TERRITORIES:
            continue
        province, alias, inside = TERRITORIES[slug]
        source = [{"field": "note", "name": SOURCE, "url": URL,
                   "license": LICENCE}]
        out.append(record(
            f"PAK-{slug}", province, level="admin1", parent="PAK",
            aliases=list(alias),
            religion=gap(NOT_AVAILABLE, TERRITORY_GAP),
            language=gap(NOT_AVAILABLE, TERRITORY_GAP), sources=list(source)))
        for name in inside:
            out.append(record(
                f"PAK-{slug}-{name.lower().replace(' ', '-')}", name,
                level="admin2", parent="PAK", parent_name=province,
                parent_aliases=list(alias),
                religion=gap(NOT_AVAILABLE, TERRITORY_GAP),
                language=gap(NOT_AVAILABLE, TERRITORY_GAP),
                sources=list(source)))
    if out:
        log(f"  {len(out)} records declaring what is not published, rather "
            f"than leaving the field empty")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    log("pakistan: Bureau of Statistics, Census 2023 Table 9")
    records: list[dict[str, Any]] = []
    absent: dict[str, list[tuple[str, str]]] = {
        REQUIRED: [], PUBLISHED: [], APART: []}
    for slug, (province, standing, candidates) in PROVINCES.items():
        log(f"  {province}")
        try:
            blob, url = fetch(candidates)
        except LookupError as err:
            # Named, not skipped: a province quietly absent is tens of millions
            # of people quietly absent, and the file naming is the office's own.
            absent[standing].append((slug, f"{province}: {err}"))
            continue
        log(f"    {len(blob):,} bytes from {url}")
        found, whole = districts(blob, province)
        if not found:
            absent[standing].append(
                (slug, f"{province}: fetched but no districts read"))
            continue
        whole = province_row(slug, province, found, whole)
        check(province, found, whole)
        assembled = merge(province, found)

        # The province itself, from its own printed row. Twelve districts have
        # no boundary shape, so anything summed from what joins the map is
        # short by their people -- Sindh by Larkana and Sujawal, 2.6 million.
        # The printed row is not short, and the check above has just proved it
        # equals the districts exactly.
        counts = dict(zip(COLUMNS, whole))
        total = counts["TOTAL"]
        # The file that answered, rather than the series it belongs to: the
        # office's index page for these tables is gone (404), and a citation a
        # reader cannot open is worse than a long one they can.
        cite = [{"field": "population/religion", "name": SOURCE,
                 "url": url, "license": LICENCE}]
        records.append(record(
            f"PAK-{slug}", province, level="admin1", parent="PAK",
            population=measure(total, year=YEAR, source=SOURCE),
            religion=shares({k: v for k, v in counts.items() if k != "TOTAL"},
                            total=total) or gap(NOT_AVAILABLE),
            religion_year=YEAR,
            religion_note=TERRITORY_NOTE if slug in ONE_DISTRICT else PROVINCE_NOTE,
            sources=list(cite)))
        for name, counts in sorted(found.items()):
            total = counts["TOTAL"]
            parts = {k: v for k, v in counts.items() if k != "TOTAL"}
            note = NOTE
            if name in assembled:
                note += (" The boundary file draws one shape here, so this is "
                         + ", ".join(p.title() for p in assembled[name])
                         + " summed.")
            records.append(record(
                f"PAK-{slug}-{name.lower().replace(' ', '-')}",
                name.title(), level="admin2", parent="PAK",
                parent_name=province, aliases=list(ALIASES.get(name.title(), ())),
                population=measure(total, year=YEAR, source=SOURCE),
                religion=shares(parts, total=total) or gap(NOT_AVAILABLE),
                religion_year=YEAR, religion_note=note,
                sources=list(cite)))

    for _slug, line in absent[APART]:
        log(f"  NOT PUBLISHED (enumerated apart from the census proper) "
            f"-- {line}")
    for _slug, line in absent[PUBLISHED]:
        # Not the same sentence as the line above, and the difference is the
        # point: this office does publish this one, so an absence here is this
        # run's problem rather than Pakistan's. Islamabad spent two rounds
        # under the wrong heading because one wording covered both.
        log(f"  NOT READ -- the office publishes this table; the paths asked "
            f"for are stale -- {line}")
    for _slug, line in absent[REQUIRED]:
        log(f"  NOT READ -- {line}")
    if absent[REQUIRED]:
        raise SystemExit(f"{len(absent[REQUIRED])} of Pakistan's four "
                         "provinces were not read; refusing to write a "
                         "partial Pakistan")

    # Azad Jammu and Kashmir, from its own government, where the Bureau's
    # series stops. Only when the Bureau's series did stop: if a Table 9 for
    # the territory ever appears, that is the same office as the four
    # provinces reading the same question, and it wins without a rule needing
    # to be written for it.
    if any(slug == "ajk" for slug, _line in absent[APART]):
        log("  Azad Jammu and Kashmir, from the territory's own yearbook")
        try:
            blob, url = fetch((AJK_BOOK,))
        except LookupError as err:
            log(f"    NOT READ -- {err}")
        else:
            log(f"    {len(blob):,} bytes from {url}")
            try:
                found, whole = ajk_table(blob)
            except LookupError as err:
                # The yearbook is reissued every year. A table that is no
                # longer in it leaves the territory declared rather than
                # stopping the run, which is where it was before this route
                # existed.
                log(f"    NOT READ -- {err}")
            else:
                ajk_check(found, whole)
                records.extend(ajk_records(found, whole))
                absent[APART] = [(slug, line) for slug, line in absent[APART]
                                 if slug != "ajk"]

    records.extend(declared_gaps(absent))
    out = args.out or PROCESSED / "pakistan_district.json"
    write_json(out, records)
    provinces = sum(1 for r in records if r["level"] == "admin1")
    log(f"  {len(records) - provinces} districts and {provinces} provinces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
