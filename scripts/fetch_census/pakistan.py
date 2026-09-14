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
    "Azad Jammu and Kashmir has no mother-tongue table from any census: the "
    "Bureau of Statistics publishes no Table 11 for it and the U.S. Census "
    "Bureau's workbook of the 2017 census lists the territory and leaves it "
    "blank. The territory's own AJ&K MICS 2020-21 asks the question -- "
    "Appendix E prints it as HC1B, the mother tongue of the head of the "
    "household -- and publishes no distribution of the answer in 734 pages. "
    "What does exist is Table 15.33 of the AJ&K Statistical Year Book 2023, "
    "'Languages Spoken in AJ&K', a district-wise percentage from the Kashmir "
    "Liberation Cell rather than from a census, and this run could not read "
    "it.")

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

# Table 11's, from the same files' header row. Fifteen tongues where the 2017
# round named nine: Shina, Balti, Mewati, Kalasha and Kohistani were added,
# and that addition is the whole reason this table is read.
#
# The 2017 table reached this map through the U.S. Census Bureau's HDX tables
# and left two districts almost entirely unnamed -- Chitral 93.1% Other,
# Kohistan 91.9% -- because the languages those districts actually speak had
# no column to be counted in. Reading the 2023 table directly puts Kohistani
# on Kohistan and Kalasha on Chitral, and it puts language on the same census
# round as the religion and population already read from Table 9 beside it,
# which the 2017 figures never were.
#
# "KOHIOSTANI" is the office's own spelling in the header; it is not repeated
# here, because what this list names is the group as this map writes it.
TONGUE_COLUMNS = ["TOTAL", "Urdu", "Punjabi", "Sindhi", "Pushto", "Balochi",
                  "Kashmiri", "Saraiki", "Hindko", "Brahvi", "Shina", "Balti",
                  "Mewati", "Kalasha", "Kohistani", "Other language"]

# Filed exactly as Table 9 is, province by province, and Islamabad again
# without the word "districts" -- the same scheme, so the same two paths are
# tried. Gilgit-Baltistan and Azad Jammu and Kashmir answer 404 here as they
# do for Table 9: the Bureau does not publish either table for either
# territory, which is one fact about its coverage rather than two.
TONGUE_FILES: dict[str, tuple[str, ...]] = {
    "kp": (f"{BASE}/table_11_kp_districts.pdf",
           f"{DCR}/kp/dcr/table_11.pdf"),
    "punjab": (f"{BASE}/table_11_punjab_districts.pdf",
               f"{DCR}/punjab/dcr/table_11.pdf"),
    "sindh": (f"{BASE}/table_11_sindh_districts.pdf",
              f"{DCR}/sindh/dcr/table_11.pdf"),
    "balochistan": (f"{BASE}/table_11_balochistan_districts.pdf",
                    f"{DCR}/balochistan/dcr/table_11.pdf"),
    "ict": (f"{BASE}/table_11_islamabad.pdf",
            f"{BASE}/table_11_islamabad_districts.pdf",
            f"{DCR}/islamabad/dcr/table_11.pdf"),
}

TONGUE_SOURCE = ("Pakistan Bureau of Statistics, 7th Population and Housing "
                 "Census 2023, Table 11: population by mother tongue, sex and "
                 "rural/urban")
TONGUE_NOTE = (
    "Census 2023 Table 11. The question is mother tongue -- the language of "
    "the household a person grew up in, rather than the one they speak now. "
    "The form names fifteen tongues and an Other, six more than the 2017 "
    "round, which is what lets Kohistani and Kalasha be counted by name here "
    "at all. The Other is still a real category and still large in places: "
    "Khowar, Burushaski, Torwali, Gujari and Wakhi have no column of their "
    "own and are counted inside it.")

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


def to_hundred(exact: dict[str, float]) -> dict[str, float]:
    """Percentages rounded to a tenth and summing to 100.0 exactly.

    Largest remainder, because the alternative is a composition that adds to
    99.9 or 100.1 through independent roundings and a reader who cannot tell
    that drift from a source that does not partition its population. The
    adjustment goes to the largest share, where a tenth of a point is the
    smallest lie available.

    Three tables here need it -- Gilgit-Baltistan's sects and its languages,
    Azad Kashmir's languages -- and all three are weighted sums rather than
    counts, so ``shares()``, which rounds each row on its own, cannot do it.
    """
    floors = {name: round(value, 1) for name, value in exact.items()}
    drift = round(100.0 - sum(floors.values()), 1)
    if drift:
        biggest = max(floors, key=lambda name: floors[name])
        floors[biggest] = round(floors[biggest] + drift, 1)
    return floors


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


def districts(blob: bytes, province: str,
              columns: list[str] = COLUMNS
              ) -> tuple[dict[str, dict[str, int]], list[int]]:
    """{district: {group: count}} for one province's table, and its own row.

    ``columns`` because the Bureau files two tables of this shape and they are
    not the same width -- Table 9 prints nine cells to a row and Table 11
    sixteen. Everything else about them is identical, down to the tehsils
    interleaved with the districts and the dash written for a zero, so the
    reading is the same reading and the width is the only thing passed in.

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
                    whole.extend(
                        values(cells, province, province, columns) or [])
                continue
            # The label is two words and the row is a list of words, so
            # comparing the first of them to "ALL SEXES" could never be true:
            # it read "ALL", found it in no list, and skipped every figure in
            # the file while still counting the tehsils it passed over.
            if not line.startswith("ALL SEXES"):
                continue
            numbers = values(cells, province, current, columns)
            if numbers and current not in found:
                found[current] = dict(zip(columns, numbers))
            current = None                          # one row per district

    log(f"    {len(found)} districts, {skipped_tehsils} tehsils passed over")
    return found, whole


def check(province: str, found: dict[str, dict[str, int]],
          whole: list[int], parts_are: str = "religions") -> None:
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
            bad.append(f"{name}: {parts_are} sum to {parts:,} against a "
                       f"printed {total:,}")
    if bad:
        raise SystemExit(f"{province}: {len(bad)} districts do not reconcile — "
                         + "; ".join(bad[:4]))
    log(f"    every district's {parts_are} sum to its own printed total")

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
                 whole: list[int],
                 columns: list[str] = COLUMNS) -> list[int]:
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
    return [only[column] for column in columns]


def merge(province: str, found: dict[str, dict[str, int]],
          columns: list[str] = COLUMNS) -> dict[str, tuple[str, ...]]:
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
                       for column in columns}
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
        if not found:
            # The caption also appears in the book's contents, thirteen pages
            # before the table -- a line of text and a page number, no figures
            # under it. The first version of this stopped at the first page
            # carrying the caption and refused the run over the listing. A
            # page with the caption and no district rows at all is a mention
            # of the table; a page with the caption and *some* of them is a
            # misread, and the two are not the same failure.
            log(f"    Table 15.24 named on page {number} with no rows under "
                f"it: the contents, not the table")
            continue
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


# ---------------------------------------------------------------------------
# Azad Jammu and Kashmir's languages: the same yearbook, a different office.
# ---------------------------------------------------------------------------
#
# Table 15.33, *Languages Spoken in AJ&K*, is the only district-level language
# figure this territory has, and finding that out took measuring the three
# routes that do not lead to one:
#
#   * the Bureau of Statistics publishes no Table 11 for AJ&K, under any of
#     the names the four provinces and Islamabad are filed under;
#   * the **AJ&K MICS 2020-21**, the territory's own household survey, *does*
#     ask the question -- Appendix E prints it as HC1B, "What is the mother
#     tongue of the head of the household?", with English, Urdu,
#     Hindko/Pahari/Potohari, Kashmiri, Gojri, Punjabi and an Other -- and its
#     734-page Survey Findings Report publishes no distribution of the answer.
#     The word "Gojri" occurs on eight of those pages and every one of them is
#     a questionnaire. The answers are in the microdata, which lives on
#     mics.unicef.org behind a client check this project does not spoof;
#   * the same yearbook's prose (section 1.9) lists the languages by name and
#     gives no figures at all.
#
# So this table, and it is not a census. Three things about it are stated
# rather than smoothed over, because a reader has to be able to discount it:
#
# **Its source is not a statistical office.** The line under it reads "Kashmir
# Liberation Cell, Muzaffarabad" -- a department of the AJ&K government, and
# not the Bureau of Statistics whose religion table sits nine pages earlier.
# The figures are round to a degree no count is: 50, 95, 63, 35.
#
# **It carries no year.** Table 15.32 above it is captioned "(2018 to 2022)"
# and this one is captioned nothing, so the records it fills carry no
# `language_year`. Dating it 2023 from the cover is precisely the error the
# religion table above documents avoiding.
#
# **Five columns are made to hold eight languages.** The headings are
# Kashmiri, Gojri, Pahari, Shina and Others, and where a district's language
# is none of those the office writes its name inside the cell: Bhimber's Dogri
# is printed under the *Shina* column and its Punjabi under *Others*. Reading
# a column heading as the language would put Dogri speakers under Shina -- a
# wrong row that no total would catch, which is the one failure this module
# exists to refuse. Every cell name is therefore declared in
# ``AJK_TONGUE_NAMES`` below and an unrecognised one stops the run.
AJK_TONGUE_TABLE = re.compile(r"Languages\s*Spoken\s*in\s*AJ&K", re.I)
# The five printed headings, left to right. They are what locates the columns
# on the page; what they mean is ``AJK_TONGUE_NAMES``.
AJK_TONGUE_COLUMNS = ("Kashmiri", "Gojri", "Pahari", "Shina", "Others")
# Every label the table prints, and the group this map files it under. A
# heading with no name written beside the figure means the heading; a name
# written beside the figure means that name.
AJK_TONGUE_NAMES: dict[str, str] = {
    "Kashmiri": "Kashmiri",
    "Gojri": "Gojri",
    # The heading is "Pahari" and Kotli's own cell writes "Pahari Pothwari".
    # This map writes Pahari-Pothwari for both, because "Pahari" alone is also
    # the name of a Tibeto-Burman language of Nepal that this project already
    # carries: one label for two unrelated languages would put four million
    # people in the wrong family and the wrong colour on the map.
    "Pahari": "Pahari-Pothwari",
    "Shina": "Shina",
    "Others": "Other languages",
    # The names printed inside a cell. The first five are what a district
    # calls its own variety of Pahari-Pothwari -- Dhundi-Kairali in Bagh,
    # Chibhali in Haveli, Punchi in Poonch and Sudhnoti, Mirpuri in Mirpur and
    # Bhimber -- and the table files each of them in the Pahari column, which
    # is where they belong and where they stay.
    "Dhundi-Khairali": "Pahari-Pothwari",
    "Chibali": "Pahari-Pothwari",
    "Punchi": "Pahari-Pothwari",
    "Pahari Pothwari": "Pahari-Pothwari",
    "Mirpuri": "Pahari-Pothwari",
    # And the three that are languages in their own right, printed in
    # whichever column had room: Dogri under Shina, Punjabi under Others, and
    # Kundal Shahi -- the Dardic language of two villages in the Neelum valley
    # -- under Others as well.
    "Dogri": "Dogri",
    "Punjabi": "Punjabi",
    "Kundal Shahi": "Kundal Shahi",
}
AJK_TONGUE_SOURCE = ("Kashmir Liberation Cell, Muzaffarabad, Table 15.33 "
                     "'Languages Spoken in AJ&K', as printed in the AJ&K "
                     "Statistical Year Book 2023 (Bureau of Statistics, P&DD, "
                     "Azad Government of the State of Jammu & Kashmir)")
AJK_TONGUE_LICENCE = AJK_LICENCE
# What a composition counts, and what keeps it out of Pakistan's national
# mother tongue: the four provinces and Islamabad answer the census's mother
# tongue question and this answers "what is spoken here".
AJK_TONGUE_BASIS = "languages spoken"
# The most a printed row may fall short of 100 before this is a misreading
# rather than the source's own rounding. Mirpur's row sums to 97 and every
# other row to exactly 100, so five points is wide enough to admit the one
# and narrow enough that a column read into the wrong place -- which moves a
# row by tens -- still stops the run.
AJK_TONGUE_SHORT = 5.0
AJK_TONGUE_NOTE = (
    "Not a census. Azad Jammu and Kashmir is enumerated apart from the census "
    "proper and the Bureau of Statistics publishes no mother-tongue table for "
    "it, so this is Table 15.33 of the AJ&K Statistical Year Book 2023, whose "
    "source line names not the territory's Bureau of Statistics but its "
    "Kashmir Liberation Cell. The table gives a percentage for each of the ten "
    "districts and prints no year; these are those ten rows weighted by their "
    "2017 census populations, which is why the territory's figure agrees with "
    "the districts underneath it. The figures are round -- 50, 95, 63 -- and "
    "the question they answer is which languages are spoken here rather than "
    "the census's mother tongue, which is why they are not added into "
    "Pakistan's national language figure. Pahari-Pothwari is the table's "
    "'Pahari' column together with the local names it prints inside it "
    "(Dhundi-Khairali in Bagh, Chibali in Haveli, Punchi in Poonch and "
    "Sudhnoti, Mirpuri in Mirpur and Bhimber); Dogri and Punjabi are named in "
    "Bhimber's row and Kundal Shahi in Neelum's, each printed under a column "
    "headed for a different language.{short}")
AJK_TONGUE_SHORT_NOTE = (
    " One row does not add up and is not quietly squared: {names}, so the "
    "three points the source leaves unaccounted for are spread across that "
    "district's own languages in proportion rather than across the territory's, "
    "which is where the people they describe live.")

# A share in this table: one, two or three digits and never a thousands
# separator, which is what tells it apart from the marriage counts printed
# above it on the same page.
SHARE = re.compile(r"^\d{1,3}$")


def ajk_tongue_row(cells: list[Cell], centres: list[tuple[float, str]],
                   district: str, limit: float) -> dict[str, float]:
    """One district's row of Table 15.33 as {language: percent}.

    Three kinds of thing are in the row and only one of them is a figure: the
    district's name, five columns of percentages with a dash where a language
    is absent, and -- inside a cell, after its number -- the local name of the
    language that number counts.

    So the numbers are placed by where they sit and named by what follows
    them. ``limit`` is half the narrowest gap between two column centres, so a
    figure nearer to no column than that is a row this reader has misread
    rather than a column it has not been told about.
    """
    slots: list[tuple[float, int, list[str]]] = []
    for x0, x1, text in cells:
        if text == DASH:
            continue                       # the office's "not spoken here"
        if SHARE.match(text):
            slots.append(((x0 + x1) / 2.0, int(text), []))
            continue
        if not slots:
            raise SystemExit(
                f"AJ&K Table 15.33: {district}'s row begins {text!r} before "
                f"any figure, so the district's name has not been read off it")
        slots[-1][2].append(text)

    out: dict[str, float] = {}
    taken: dict[str, int] = {}
    for centre, value, words in slots:
        distance, column = min((abs(x - centre), name) for x, name in centres)
        if distance > limit:
            raise SystemExit(
                f"AJ&K Table 15.33: {district} prints {value} at x={centre:.0f}, "
                f"{distance:.0f} points from the nearest column ({column}); "
                f"the columns are not where this reader thinks they are")
        if column in taken:
            raise SystemExit(
                f"AJ&K Table 15.33: {district} puts {taken[column]} and "
                f"{value} both in the {column} column")
        taken[column] = value
        label = " ".join(words) or column
        group = AJK_TONGUE_NAMES.get(label)
        if group is None:
            raise SystemExit(
                f"AJ&K Table 15.33: {district} names {label!r}, which this "
                f"module has not been told what to do with. A language filed "
                f"under the wrong column heading is invisible, so an "
                f"unrecognised one stops the run rather than being guessed at")
        out[group] = out.get(group, 0.0) + value
    return out


def ajk_tongue_table(blob: bytes) -> dict[str, dict[str, float]]:
    """Table 15.33: ten districts, each as {language: percent}.

    The caption alone does not find it. Table 15.32, *District-wise Number and
    Percentage of Marriages*, is printed on the same page with the same ten
    district names down its left edge, so a reader that took the first row
    beginning "Muzaffarabad" would come away with a marriage count. The rows
    are therefore read only below 15.33's own heading row -- the one carrying
    all five column names -- and only as far as its source line.

    A caption with no heading row under it is the contents listing, thirteen
    pages earlier, and is skipped rather than refused; the same distinction
    ``ajk_table`` draws, for the same reason.
    """
    for number, rows in enumerate(words_by_row(blob), start=1):
        page = [(" ".join(t for _a, _b, t in cells), cells) for cells in rows]
        if not any(AJK_TONGUE_TABLE.search(line) for line, _cells in page):
            continue
        head = next((i for i, (_line, cells) in enumerate(page)
                     if all(name in [t for _a, _b, t in cells]
                            for name in AJK_TONGUE_COLUMNS)), None)
        if head is None:
            log(f"    Table 15.33 named on page {number} with no heading row "
                f"under it: the contents, not the table")
            continue
        centres = [((x0 + x1) / 2.0, text) for x0, x1, text in page[head][1]
                   if text in AJK_TONGUE_COLUMNS]
        gaps = [b[0] - a[0] for a, b in zip(centres, centres[1:])]
        limit = min(gaps) / 2.0
        found: dict[str, dict[str, float]] = {}
        for line, cells in page[head + 1:]:
            if line.startswith("Source:"):
                break
            name = next((d for d in AJK_DISTRICTS
                         if line.startswith(f"{d} ")), None)
            if name is None or name in found:
                continue
            found[name] = ajk_tongue_row(cells[len(name.split()):],
                                         centres, name, limit)
        if len(found) != len(AJK_DISTRICTS):
            raise SystemExit(
                f"AJ&K Table 15.33 is on page {number} and this read "
                f"{len(found)} of {len(AJK_DISTRICTS)} districts: "
                + ", ".join(sorted(found)))
        log(f"    Table 15.33 on page {number}: {len(found)} districts, "
            f"{len(set().union(*found.values()))} languages")
        return found
    raise LookupError("no page carries Table 15.33's caption")


def ajk_tongue_weighted(tongues: dict[str, dict[str, float]],
                        people: dict[str, dict[str, int]],
                        whole: dict[str, int]) -> tuple[dict[str, float], str]:
    """The ten districts' languages weighted into the territory's own row.

    geoBoundaries draws Azad Kashmir as a single second-level unit, so the ten
    rows have nowhere of their own to land -- ``ajk_records`` explains why they
    are not published one per district. What they can do is add up, and the
    populations to add them with are already read: they are the TOTAL column of
    the religion table above, which ``ajk_check`` has just shown sums to the
    territory exactly.

    Largest-remainder rounding, so the published shares come to 100.0 rather
    than to 99.9 through eight independent roundings.

    Returns the shares and the sentence describing any row the source left
    short of 100, which is carried into the note rather than smoothed away.
    """
    missing = sorted(set(tongues) - set(people))
    if missing:
        raise SystemExit(
            "AJ&K: Table 15.33 names districts Table 15.24 does not -- "
            + ", ".join(missing))
    short: list[str] = []
    exact: dict[str, float] = {}
    counted = 0
    for name, shares_of in tongues.items():
        printed_total = sum(shares_of.values())
        if abs(printed_total - 100.0) > AJK_TONGUE_SHORT:
            raise SystemExit(
                f"AJ&K Table 15.33: {name}'s languages sum to "
                f"{printed_total:g}%, too far from 100 to be the source's own "
                f"rounding")
        if printed_total != 100.0:
            short.append(f"{name}'s row sums to {printed_total:g}% rather "
                         f"than 100")
            log(f"    {name}: Table 15.33 sums to {printed_total:g}%, "
                f"rescaled to 100 across its own languages")
        count = people[name]["TOTAL"]
        counted += count
        for group, pct in shares_of.items():
            exact[group] = exact.get(group, 0.0) + count * pct / printed_total
    if counted != whole["TOTAL"]:
        raise SystemExit(
            f"AJ&K: the ten language rows weigh {counted:,} people against "
            f"the {whole['TOTAL']:,} printed for the territory")
    weighted = to_hundred({group: 100.0 * value / counted
                           for group, value in exact.items()})
    return weighted, (AJK_TONGUE_SHORT_NOTE.format(names=" and ".join(short))
                      if short else "")


# Gilgit-Baltistan's religion, which no census publishes and one institute does.
#
# Everything above this is a census table read off a government file. This is
# not: it is PILDAT's, from a background paper on sectarian conflict, and it is
# here because the alternative was a blank on 1.2 million people after every
# official route was measured and found shut -- twelve 404s across two table
# numbers and four spellings, both territories' own At a Glance volumes, and a
# survey that counts respondents rather than people.
#
# Two things make it publishable rather than merely available. The four shares
# sum to 100.00% exactly, which is what a composition has to do and what an
# assembled guess usually does not. And the thing it leaves out is checkable:
# these are shares of a population taken to be entirely Muslim, and the last
# census that counted religion in this territory -- 1941, Jammu & Kashmir --
# put it at 99.7%, so the non-Muslim remainder it ignores is a third of a
# percent rather than something that would change the picture.
#
# What it is not is a census, and the note says so first. It is also
# territory-wide: the ten districts differ sharply -- Skardu and Kharmang are
# heavily Twelver, Hunza and Ghizer heavily Ismaili, Diamer almost entirely
# Sunni -- and the paper gives no district table, so the districts keep their
# declared gaps rather than wearing the territory's average.
GB_SECTS: dict[str, float] = {
    "Twelver Shi'a Islam": 39.85,
    "Sunni Islam": 30.05,
    "Isma'ili Shi'a Islam": 24.0,
    "Nurbakhshia Islam": 6.1,
}
GB_SOURCE = ("PILDAT (Pakistan Institute of Legislative Development and "
             "Transparency), Sectarian Conflict in Gilgit-Baltistan, "
             "background paper, May 2011")
GB_URL = ("https://web.archive.org/web/20130927213540/http://www.pildat.org/"
          "publications/publication/Conflict_Management/"
          "GB-SectarianConflit-BackgroundPaperEng-May2011.pdf")
GB_YEAR = 2011
GB_NOTE = (
    "Not a census. Pakistan's Bureau of Statistics publishes no religion table "
    "for Gilgit-Baltistan at all, so this is PILDAT's estimate of the "
    "territory's sectarian composition, from a 2011 background paper on "
    "sectarian conflict. The four shares are as that paper gives them and sum "
    "to 100%. They describe a population taken to be entirely Muslim, which "
    "the last census to count religion here bears out: the 1941 Census of "
    "India returned 99.7% Muslim across Gilgit Agency, Gilgit Leased, Skardu "
    "and Astore. Gilgit-Baltistan is the only Shia-plurality region of a "
    "Sunni-majority country. Its districts differ sharply from each other and "
    "from this average -- Diamer is Sunni, Hunza and Ghizer Ismaili, Baltistan "
    "overwhelmingly Twelver, Ghanche the centre of the Noorbakhshia order -- "
    "and the same paper's 'Faith Map of Gilgit-Baltistan' gives an area-wise "
    "breakdown, so each of the ten districts carries its own figure rather "
    "than an average.")


# Gilgit-Baltistan's religion by district, on the owner's instruction.
#
# The territory note used to say "no source breaks it down". That was wrong,
# and it was wrong about the paper this file already cites: PILDAT's page 13
# carries a section headed "Faith Map of Gilgit-Baltistan" whose area-wise list
# gives percentages. It is quoted here verbatim rather than paraphrased,
# because every figure below is either one of its lines or is derived from one
# by a rule stated beside it:
#
#     i.   Gilgit is 60 per cent Shia, 40 per cent Sunni;
#     ii.  Hunza 100 per cent Ismaili;
#     iii. Nagar 100 per cent Shia;
#     iv.  Punial 100 per cent Ismaili;
#     v.   Yasin 100 per cent Ismaili;
#     vi.  Ishkoman 100 per cent Ismaili;
#     vii. Gupis 100 per cent Ismaili;
#     viii.Chilas 100 per cent Sunni;
#     ix.  Darel/Tangir 100 per cent Sunni;
#     x.   Astor 90 per cent Sunni, 10 per cent Shia;
#     xi.  Baltistan 96 (or 98) per cent Shia; 2 per cent Noorbakhshi;
#          2 per cent Sunni
#
# Four of those names are not districts. Punial, Yasin, Ishkoman and Gupis are
# the valleys of Ghizer; Chilas and Darel/Tangir are Diamer's. The paper's own
# narrative confirms both roll-ups in so many words -- "Ismailis hold majority
# in Ghizer District", Sunni "possesses 100% population in Diamer District" --
# so the district takes the figure its every named part is given.
#
# "96 (or 98)" is read as 96, the only reading under which the line sums to
# 100. Baltistan in 2011 is today's Skardu, Kharmang and Shigar, the last two
# carved out after this paper was written; they inherit the divisional figure
# the way a post-2011 Indian district inherits its predecessor's shares.
#
# GHANCHE IS THE ONE PLACE THE PAPER CONTRADICTS ITSELF, and it is not a small
# contradiction. The line above puts Noorbakhshia at 2 per cent of Baltistan,
# while the same page says the "Noorbakhshi Community only resides in Skardu
# and Ghanche, they are in majority in the latter". Both cannot hold: Ghanche
# is too large a part of Baltistan for a division that is 2 per cent
# Noorbakhshia to contain a Noorbakhshia-majority district. The 2 per cent is
# what breaks -- Pakistan's Noorbakhshia are usually counted near 6 per cent of
# Gilgit-Baltistan as a whole, which is the figure this file already publishes
# for the territory, and they are concentrated here. So Ghanche takes the
# reported 80 per cent Noorbakhshia and its remainder is split on Baltistan's
# own 96:2 Shia-to-Sunni ratio, which is the only part of that line still
# standing.
#
# What these are NOT is a census. They are a 2011 conflict background paper's
# figures, they are round in a way no measurement is -- four districts at a
# flat 100 per cent, which no district anywhere actually is -- and the paper's
# narrative names minorities in Ghizer that its own 100 per cent leaves no room
# for. Every one of those caveats is in the note that travels with the value,
# and `religion_basis` keeps the whole set out of Pakistan's national figure
# exactly as the territory row is kept out.
GB_DISTRICT_SECTS: dict[str, dict[str, float]] = {
    "Gilgit": {"Twelver Shi'a Islam": 60.0, "Sunni Islam": 40.0},
    "Astore": {"Sunni Islam": 90.0, "Twelver Shi'a Islam": 10.0},
    "Diamer": {"Sunni Islam": 100.0},
    "Nagar": {"Twelver Shi'a Islam": 100.0},
    "Hunza": {"Isma'ili Shi'a Islam": 100.0},
    "Ghizer": {"Isma'ili Shi'a Islam": 100.0},
    "Skardu": {"Twelver Shi'a Islam": 96.0, "Nurbakhshia Islam": 2.0,
               "Sunni Islam": 2.0},
    "Kharmang": {"Twelver Shi'a Islam": 96.0, "Nurbakhshia Islam": 2.0,
                 "Sunni Islam": 2.0},
    "Shigar": {"Twelver Shi'a Islam": 96.0, "Nurbakhshia Islam": 2.0,
               "Sunni Islam": 2.0},
    "Ghanche": {"Nurbakhshia Islam": 80.0, "Twelver Shi'a Islam": 19.6,
                "Sunni Islam": 0.4},
}

# How each district's figure was arrived at, in the district's own words. The
# reader sees this under the composition, so it says where the number came from
# before it says anything else, and it does not hide the places the source
# argues with itself.
GB_DISTRICT_BASIS: dict[str, str] = {
    "Gilgit": "PILDAT gives Gilgit directly: '60 per cent Shia, 40 per cent "
              "Sunni'. Gilgit is where the territory's two largest sects meet "
              "in comparable numbers, which is the paper's explanation for why "
              "its sectarian violence has centred on this district.",
    "Astore": "PILDAT gives Astore directly: '90 per cent Sunni, 10 per cent "
              "Shia'.",
    "Diamer": "PILDAT gives Diamer's two areas, Chilas and Darel/Tangir, as "
              "'100 per cent Sunni' each, and says separately that Sunnis "
              "'possess 100% population in Diamer District'. A flat 100 per "
              "cent is the paper's round figure rather than a count.",
    "Nagar": "PILDAT gives Nagar directly: '100 per cent Shia'. A flat 100 per "
             "cent is the paper's round figure rather than a count.",
    "Hunza": "PILDAT gives Hunza directly: '100 per cent Ismaili', and says "
             "separately that Ismailis hold a majority in the Hunza "
             "sub-division. A flat 100 per cent is the paper's round figure "
             "rather than a count.",
    "Ghizer": "PILDAT gives all four of Ghizer's valleys -- Punial, Yasin, "
              "Ishkoman and Gupis -- as '100 per cent Ismaili', and says "
              "separately that 'Ismailis hold majority in Ghizer District'. "
              "The same page also says Shias are a minority here and that "
              "Sunnis live here, which a flat 100 per cent leaves no room for: "
              "read the figure as an Ismaili district with minorities the "
              "source does not size.",
    "Skardu": "PILDAT gives one figure for Baltistan as a whole -- 96 per cent "
              "Shia, 2 per cent Noorbakhshia, 2 per cent Sunni -- and not one "
              "for Skardu by itself. The paper also places Noorbakhshia and a "
              "minority of Ismailis in Skardu, so the 2 per cent is likely low "
              "and the Ismaili share is missing entirely.",
    "Kharmang": "Kharmang was created in 2015, four years after this paper, "
                "out of Skardu. It carries PILDAT's figure for Baltistan as a "
                "whole -- 96 per cent Shia, 2 per cent Noorbakhshia, 2 per "
                "cent Sunni -- because no source describes it separately.",
    "Shigar": "Shigar was created in 2015, four years after this paper, out of "
              "Skardu. It carries PILDAT's figure for Baltistan as a whole -- "
              "96 per cent Shia, 2 per cent Noorbakhshia, 2 per cent Sunni -- "
              "because no source describes it separately.",
    "Ghanche": "The one district where PILDAT contradicts itself. Its figure "
               "for Baltistan puts Noorbakhshia at 2 per cent, while the same "
               "page says the Noorbakhshia 'only reside in Skardu and Ghanche, "
               "they are in majority in the latter' -- which 2 per cent of the "
               "division cannot produce. The majority statement is the one "
               "kept, at the 80 per cent reported for Ghanche elsewhere, with "
               "the remaining fifth split on Baltistan's own 96:2 "
               "Shia-to-Sunni ratio. Ghanche is the centre of the Noorbakhshia "
               "order, which is why the territory's 6 per cent is concentrated "
               "here rather than spread.",
}
GB_DISTRICT_NOTE = (
    "Not a census, and not a count of people. Pakistan's Bureau of Statistics "
    "publishes no religion table for Gilgit-Baltistan at any level, so this is "
    "PILDAT's 2011 'Faith Map of Gilgit-Baltistan', from a background paper on "
    "sectarian conflict rather than a demographic survey. {basis} These shares "
    "describe a population taken to be entirely Muslim -- the last census to "
    "count religion here, the 1941 Census of India, returned 99.7% Muslim "
    "across Gilgit Agency, Gilgit Leased, Skardu and Astore -- so they "
    "partition the district between sects rather than between religions. They "
    "are not added into Pakistan's national religion figure, which is a census "
    "of a different question.")


def gb_district_religion(name: str) -> dict[str, Any]:
    """The religion fields for one Gilgit-Baltistan district.

    Empty when the district is not in the table, so a district this file has
    no figure for keeps the declared gap rather than being given a blank
    composition, which would be the worse of the two.
    """
    sects = GB_DISTRICT_SECTS.get(name)
    if not sects:
        return {}
    total = round(sum(sects.values()), 2)
    if total != 100.0:
        raise SystemExit(
            f"pakistan: {name}'s sect shares sum to {total}, not 100. These "
            f"are declared rather than read from a table, and one of them is "
            f"arithmetic on a contradiction, so a wrong figure here is a typo "
            f"nothing else would catch")
    return {
        "religion": [{"group": group, "pct": pct}
                     for group, pct in sorted(sects.items(),
                                              key=lambda kv: -kv[1])],
        "religion_year": GB_YEAR,
        "religion_note": GB_DISTRICT_NOTE.format(basis=GB_DISTRICT_BASIS[name]),
        "religion_basis": "sectarian affiliation",
    }


def gb_religion(counts: dict[str, int]) -> dict[str, Any]:
    """The religion fields for Gilgit-Baltistan's territory row.

    Returned as fields rather than as a record of its own, because
    ``declared_gaps`` already writes a record under this id and two records
    for one id is how a value gets quietly replaced by the gap that was meant
    to stand in for it. One id, one record, one place that decides.

    ``counts`` is the census population of each district, where this run read
    it, and it decides which of two figures this row carries. With the
    populations, the row is the ten districts weighted by them, and the
    territory then agrees with the map drawn beneath it. Without them there is
    nothing to weight by, and the row falls back to the paper's own
    territory-wide estimate, which is where it stood before the populations
    were read.
    """
    for label, shares in (("territory-wide", GB_SECTS),
                          *((f"{name}'s", s) for name, s
                            in GB_DISTRICT_SECTS.items())):
        total = round(sum(shares.values()), 2)
        if total != 100.0:
            raise SystemExit(
                f"pakistan: Gilgit-Baltistan's {label} sect shares sum to "
                f"{total}, not 100. A composition that does not partition its "
                f"population is not one, and these are declared rather than "
                f"read, so a wrong figure would be a typo nothing else catches")
    weighted = gb_weighted(counts)
    shares = weighted or GB_SECTS
    total = round(sum(shares.values()), 2)
    if total != 100.0:
        raise SystemExit(
            f"pakistan: Gilgit-Baltistan's published sect shares sum to "
            f"{total}, not 100, after weighting. The rounding that makes the "
            f"four add up has failed, which no other check here would see")
    return {
        "religion": [{"group": name, "pct": pct}
                     for name, pct in sorted(shares.items(),
                                             key=lambda kv: -kv[1])],
        "religion_year": GB_YEAR,
        "religion_note": GB_NOTE + gb_disagreement(weighted),
        "religion_basis": "sectarian affiliation",
    }


# Gilgit-Baltistan's language, from the territory's own survey.
#
# The census routes are shut and stay shut: Table 11 does not exist for this
# territory at any path the Bureau uses, and GB At a Glance 2025 carries
# district tables from the same census with the word "tongue" on no page.
#
# What does exist is the **Gilgit-Baltistan MICS 2024-25**, run by the
# territory's Planning & Development Department with UNICEF and published by
# the department itself. Its Table SR.3.1, *Household composition*, prints the
# distribution of 6,929 households by language of the household head: Shina
# 48.0%, Balti 29.2%, Brushaski 12.3%, Khowar 5.2%, Wakhi 1.0%, Other 4.2%.
# That is the office's own figure for the field, and it is read here.
#
# It was not found earlier because of a spelling. The 2016-17 round's 398-page
# Final Report has no language table at all -- "Burushaski" and "Shina" appear
# on none of its pages -- and this report spells the language **Brushaski**,
# without the u, so a search for the standard spelling found nothing in 731
# pages either. The map writes Burushaski, which is what every other source
# here calls it; ``GB_TONGUE_SPELLING`` is where that is decided rather than
# in a guess at read time.
#
# The Pamir Times figures below are kept as what this field falls back to, and
# they are a different measurement: a newspaper's account of the 2017 round,
# scaled on census population. Where the two disagree the survey's own report
# wins -- most visibly on which language leads, where the article put Balti
# 4,000 households ahead of Shina on figures it rounded to the thousand and
# the office's own table puts Shina eighteen points ahead.
GB_MICS_BOOK = ("https://www.pnd.gog.pk/storage/downloads/"
                "oSrtpZkKNFTPMVipYa8VTI94BZmR2g-metaR0IgTUlDUyAyMDI0LTI1IFN1"
                "cnZleSBGaW5kaW5ncyBSZXBvcnQucGRm-.pdf")
GB_MICS_TABLE = re.compile(r"Table\s*SR\.3\.1\s*:\s*Household\s*composition",
                           re.I)
GB_MICS_HEAD = "Language of household head"
GB_MICS_TOTAL = "Total"
# The survey's own years, taken off the table's caption rather than from the
# file name, so a later round cannot be published under this one's date. The
# stamp is the later of the two: fieldwork that spans a new year is dated by
# where it ended, which is also the only reading that never claims a figure is
# fresher than it is.
GB_MICS_SPAN = re.compile(r"(20\d\d)-(\d\d)\b")
# The report's spelling against this map's. Declared, because a silent rename
# at read time is how two spellings of one language end up as two languages.
GB_MICS_SPELLING = {"Brushaski": "Burushaski", "Other": "Other languages"}
GB_MICS_SOURCE = ("Gilgit-Baltistan Multiple Indicator Cluster Survey 2024-25, "
                  "Table SR.3.1 (Household composition), Planning & "
                  "Development Department, Government of Gilgit-Baltistan, "
                  "with UNICEF")
GB_MICS_LICENCE = ("Government of Gilgit-Baltistan, Planning & Development "
                   "Department")
GB_MICS_NOTE = (
    "A survey, not a census, and households rather than people. Pakistan's "
    "Bureau of Statistics publishes no mother-tongue table for Gilgit-"
    "Baltistan at any path, and the census's own question would not help if it "
    "did: the 2023 form names Shina and Balti but has no column for "
    "Burushaski, Khowar, Wakhi or Domaaki, so a third of the territory would "
    "be counted inside its 'Other'. This is instead the territory's own "
    "Gilgit-Baltistan MICS 2024-25, run by its Planning & Development "
    "Department with UNICEF: Table SR.3.1 distributes {households:,} surveyed "
    "households by the language of the household head. Households and not "
    "persons, which is what language_basis records and what keeps these out of "
    "Pakistan's national mother tongue -- household size varies sharply across "
    "these districts, Diamer's being far larger than Hunza's. The report "
    "spells Burushaski 'Brushaski'; the name here is the one the rest of this "
    "map uses. The same table gives the survey's districts as a separate "
    "distribution rather than crossed with language, so none of the ten "
    "districts carries a language figure of its own.")


# The Pamir Times account of the 2017 round, now the fallback rather than the
# figure. Kept because it is what this field had, because the owner chose it
# over a blank twice, and because a survey report that a run cannot open should
# cost the field's freshness rather than the field.
#
# So this is a newspaper's account of a survey, and the note leads with that.
# What the article gives is three household counts (Balti "over 74,000", Shina
# 70,000, Burushaski 33,512) and three percentages (Khowar 3%, Wakhi 2%, other
# languages including Domaki, Gojri and Urdu 4%). It gives no total, so the
# total is recovered here: the three percentages account for 9%, which makes
# the three counts 91%, and 177,512 / 0.91 is 195,068 households. That single
# division is the only arithmetic done to the article's figures, and it is
# stated because a derived denominator is exactly the kind of step that should
# not be silent.
#
# Three things a reader has to be told, and the note tells them:
#
# *Households, not people.* Every other mother-tongue figure on this map counts
# persons. Household sizes in Gilgit-Baltistan vary by district -- Diamer's are
# markedly larger than Hunza's -- so this is not the same measurement, and
# `language_basis` says so, which is also what keeps it out of Pakistan's
# national language roll-up, exactly as GB's religion is kept out.
#
# *An estimate, twice over.* The article works from GB-MICS 2017, a survey of
# respondents, scaled on 2017 census population by its author.
#
# *Balti leads Shina by four thousand households, on figures the article itself
# rounds.* That is inside its own precision, and most other accounts call Shina
# the territory's largest language. The owner's instruction was to publish the
# article's figures as they stand, so Balti leads here and Gilgit-Baltistan
# takes Balti's colour on the dominant-group map; the note says plainly that
# the top two cannot be separated by this source.
GB_TONGUES: dict[str, float] = {
    # 74,000 / 195,068. Carries the residual, being the least precise figure
    # the article gives ("over 74,000"), so the six shares sum to 100 exactly
    # without any other one being nudged.
    "Balti": 37.93,
    "Shina": 35.89,      # 70,000 / 195,068
    "Burushaski": 17.18,  # 33,512 / 195,068
    "Khowar": 3.0,
    "Wakhi": 2.0,
    "Other languages": 4.0,
}
GB_TONGUE_SOURCE = ("Pamir Times, 'Treading the Sacred Linguistic Landscape "
                    "of Gilgit-Baltistan', 23 December 2023, reporting "
                    "Gilgit-Baltistan MICS 2017 household data")
GB_TONGUE_URL = ("https://pamirtimes.net/2023/12/23/"
                 "treading-the-sacred-linguistic-landscape-of-gilgit-baltistan/")
GB_TONGUE_YEAR = 2017
GB_TONGUE_NOTE = (
    "Not a census, and not a count of people. Pakistan's Bureau of Statistics "
    "publishes no mother-tongue table for Gilgit-Baltistan, and the census's "
    "own question would not help if it did: it names nine languages and an "
    "'Other', and Shina, Balti and Burushaski all fall in the Other. These "
    "shares are households, from a December 2023 Pamir Times article working "
    "from the Gilgit-Baltistan MICS 2017 survey and scaling it on 2017 census "
    "population -- an estimate at two removes, and households rather than "
    "persons, which is why it is not added into Pakistan's national figure. "
    "The article gives three household counts and three percentages but no "
    "total; the total of 195,068 households is derived here by division. "
    "Balti and Shina cannot be separated by this source: it puts them 4,000 "
    "households apart on figures it rounds to the thousand, and other "
    "accounts of the territory call Shina the larger. The territory-wide "
    "figure also hides a sharp geography -- Balti dominates Skardu, Ghanche, "
    "Kharmang and Shigar, Shina dominates Astore, Diamer, Ghizer and Gilgit, "
    "and Burushaski Hunza and Nagar -- and no district table is published, so "
    "none of the ten districts carries this figure.")


COUNT = re.compile(r"^[\d,]+$")
PERCENT = re.compile(r"^\d+(?:\.\d+)?$")


def gb_mics_language(blob: bytes) -> tuple[dict[str, int], int]:
    """Table SR.3.1's language block: {language: households}, and the year.

    The table is a single column of percentages with a stack of row groups
    under it -- sex of household head, age, area, division, district,
    education, household size, and last of all language -- so the block is
    found by its own heading and read until the rows stop looking like it.

    Two controls, and they are the reason this is read rather than copied out
    by hand. The six households counts must add to the *Total* the same page
    prints at the top of the table, which no misread row survives. And the
    weighted counts rather than the printed percentages are what the shares
    are made of, so the composition adds to 100 by construction instead of to
    the 99.9 the printed column comes to.
    """
    for number, rows in enumerate(words_by_row(blob), start=1):
        page = [(" ".join(t for _a, _b, t in cells), cells) for cells in rows]
        caption = next((line for line, _cells in page
                        if GB_MICS_TABLE.search(line)), None)
        if caption is None:
            continue
        whole = 0
        found: dict[str, int] = {}
        reading = False
        for line, _cells in page:
            words = line.split()
            if not reading and words[:1] == [GB_MICS_TOTAL] and len(words) == 4:
                whole = int(words[2].replace(",", ""))
                continue
            if line.strip() == GB_MICS_HEAD:
                reading = True
                continue
            if not reading:
                continue
            # label ... percent weighted unweighted, and anything else is the
            # end of the block: a page footer, or the next table's heading.
            if (len(words) < 4 or not PERCENT.match(words[-3])
                    or not COUNT.match(words[-2]) or not COUNT.match(words[-1])):
                break
            label = " ".join(words[:-3])
            found[GB_MICS_SPELLING.get(label, label)] = int(
                words[-2].replace(",", ""))
        if not found:
            log(f"    Table SR.3.1 named on page {number} with no language "
                f"block under it: the contents, not the table")
            continue
        # Dated only now, and from this page. The caption is in the contents
        # too, and a contents page carries no year -- asking it for one before
        # knowing whether the table is under it would refuse the run over a
        # listing.
        span = GB_MICS_SPAN.search(" ".join(line for line, _c in page))
        if not span:
            raise SystemExit(
                f"pakistan: Table SR.3.1 is on page {number} of the GB MICS "
                f"report and nothing on that page dates it. A survey "
                f"published under the wrong year is a figure that looks "
                f"current and is not")
        year = int(span.group(1)[:2] + span.group(2))
        counted = sum(found.values())
        if not whole or counted != whole:
            raise SystemExit(
                f"pakistan: the GB MICS language rows hold {counted:,} "
                f"households against the {whole:,} the same table prints as "
                f"its total. A row read wrong or missed moves that sum, which "
                f"is the one control this table supplies on itself")
        log(f"    Table SR.3.1 on page {number}: {len(found)} languages over "
            f"{whole:,} households, {year}")
        return found, year
    raise LookupError("no page carries Table SR.3.1's caption")


# What the ten districts are missing, which is not what the territory's note
# says and not what TERRITORY_GAP says either. Written out because "no district
# table" is a conclusion, and the reader is owed the four measurements it rests
# on: the Bureau's series, the census form's own categories, the territory's
# booklet, and the two survey reports.
GB_TONGUE_DISTRICT_GAP = (
    "Gilgit-Baltistan's language is published for the territory and for none "
    "of its ten districts, and every route to a district figure has been "
    "asked. The Bureau of Statistics publishes no Table 11 for this territory "
    "under any of the names the four provinces and Islamabad are filed under. "
    "The census form would not answer it either: the 2023 question names "
    "fifteen tongues including Shina and Balti but has no column for "
    "Burushaski, Khowar, Wakhi or Domaaki, so Hunza, Nagar and much of Ghizer "
    "would be counted inside its 'Other'. Gilgit-Baltistan at a Glance 2025, "
    "which is where this district's population comes from, carries no "
    "language table. And the territory's own household surveys stop at the "
    "territory: the GB MICS 2024-25 report gives language of the household "
    "head and district as two separate distributions rather than one crossed "
    "table, and the 2016-17 round's 398-page final report has no language "
    "table at all. The territory's figure is not spread over the ten because "
    "they differ sharply from it and from each other -- Balti is the language "
    "of Skardu, Ghanche, Kharmang and Shigar, Shina of Astore, Diamer, Ghizer "
    "and Gilgit, Burushaski of Hunza and Nagar -- so an average put on all ten "
    "would be wrong on every one of them.")


def gb_language(households: dict[str, int] | None = None,
                year: int | None = None) -> dict[str, Any]:
    """The language fields for Gilgit-Baltistan's territory row.

    Fields rather than a record, for the reason ``gb_religion`` gives: one id,
    one record, one place that decides.

    The survey's own table when this run could read it, and the Pamir Times
    account of the earlier round when it could not. Both are households rather
    than persons and both say so in ``language_basis``, so the field's meaning
    does not change with which one answered -- only its provenance and its
    date, and the note names both.
    """
    if households:
        whole = sum(households.values())
        spoken_by = to_hundred({name: 100.0 * count / whole
                                for name, count in households.items()})
        return {
            # Shares and no counts. `shares()` would attach the household
            # count to each group, and a count beside a language reads as
            # people everywhere else on this map; these are households.
            "language": [{"group": name, "pct": pct} for name, pct
                         in sorted(spoken_by.items(), key=lambda kv: -kv[1])],
            "language_year": year,
            "language_note": GB_MICS_NOTE.format(households=whole),
            "language_basis": "language of the household head",
        }
    total = round(sum(GB_TONGUES.values()), 2)
    if total != 100.0:
        raise SystemExit(
            f"pakistan: the Gilgit-Baltistan language shares sum to {total}, "
            f"not 100. Three of these six are derived from a household count "
            f"divided by a total the source does not print, so an arithmetic "
            f"slip here would look exactly like a reading of the article")
    return {
        "language": [{"group": name, "pct": pct}
                     for name, pct in sorted(GB_TONGUES.items(),
                                             key=lambda kv: -kv[1])],
        "language_year": GB_TONGUE_YEAR,
        "language_note": GB_TONGUE_NOTE,
        "language_basis": "language of the household",
    }


# Gilgit-Baltistan's population, from the territory's own government, where
# the Bureau's census tables stop.
#
# Until now this territory wore a 2011 Wikidata figure of 1,155,755 and its
# ten districts wore nothing at all. The 2023 census counted them: 1,709,049,
# a third more than the figure on the map. The Bureau publishes no table for
# Gilgit-Baltistan at any path -- Table 9 and Table 11 both answer 404 under
# every name the four provinces and Islamabad are filed under -- but the
# census's own district counts are printed by the territory's Planning &
# Development Department, and reading them there is the whole of this.
#
# *Gilgit-Baltistan at a Glance 2025* is the eighth edition of the Statistical
# & Research Cell's annual compilation. Its page 3 carries "District Wise
# Population and Area of GB": area, the 2017 and 2023 census counts, the
# intercensal growth rate, a 2026 projection and a density, for the ten
# districts and for the territory, over a source line naming the Pakistan
# Bureau of Statistics. So the figures are the census's and the booklet is
# where they are printed, which is the same standing the AJ&K yearbook's
# religion table has above.
#
# Wikipedia's "Gilgit-Baltistan" article transcribes this same table, figure
# for figure, and is not what is read. The territory's own publication is
# preferred for the reason wiki_census.py exists to state: an encyclopaedia's
# copy is worth reading when the office's own is unreachable, and here it is
# not. The article's copy is also harder to read correctly -- its division
# column is merged across rows, so four of its ten districts arrive with the
# division's name in the district's cell.
#
# **Two columns in that row must never be confused, and no figure tells them
# apart.** The 2023 census count and the 2026 projection sit side by side;
# publishing the projection as a census would be invisible, which is the
# failure this module exists to refuse. So the column is not taken by
# position. The growth rate the table prints is recomputed here from the two
# census counts compounded over the six years between the rounds, and a row
# whose printed rate does not come back stops the run. Reading the projection
# as the count, or the 2017 column as the 2023 one, breaks that arithmetic in
# the first row it is tried on; reading them right reproduces all eleven rows
# to within 0.006 of a percentage point.
#
# And the ten districts add up to the territory row printed beneath them, to
# the person -- the same control the AJ&K table is held to, and for the same
# reason: a district this reader never noticed would otherwise cost its people
# silently.
GB_BOOK = ("https://www.pnd.gog.pk/storage/downloads/"
           "AiRIlDEcscWPC1s58oXIgpjlVAS7jd-metaR0IgQVQgR2xhbmNlIDIwMjUuMS5wZGY=-.pdf")
GB_POP_TABLE = re.compile(r"District\s*Wise\s*Population\s*and\s*Area\s*of\s*GB",
                          re.I)
# The territory's own row, which the booklet labels with the initials it uses
# throughout rather than with the territory's name.
GB_POP_WHOLE = "GB"
# The row, left to right. Only 2023 is published from it: 2026 is a projection
# rather than a count, and the other three describe the row rather than being
# it. They are read anyway, because a row of the wrong width is a row this
# reader has misread and counting the cells is what catches that.
GB_POP_COLUMNS = ("Area", "2017", "2023", "Growth rate", "2026", "Density")
GB_POP_COUNT = GB_POP_COLUMNS.index("2023")
GB_POP_EARLIER = GB_POP_COLUMNS.index("2017")
GB_POP_RATE = GB_POP_COLUMNS.index("Growth rate")
# Census to census. Being wrong about this span would show up as every row
# failing the check below rather than as a figure nobody questioned.
GB_POP_SPAN = 2023 - 2017
# Percentage points. The booklet prints its rate to two decimals and the worst
# of the eleven rows comes back 0.006 away, so this is a wide margin around a
# check that either holds everywhere or fails everywhere.
GB_POP_SLACK = 0.05
GB_POP_YEAR = 2023
GB_POP_SOURCE = ("Pakistan Bureau of Statistics, 7th Population and Housing "
                 "Census 2023, District Wise Population and Area of GB, as "
                 "printed in Gilgit-Baltistan at a Glance 2025 (Statistical & "
                 "Research Cell, Planning & Development Department, "
                 "Government of Gilgit-Baltistan)")
GB_POP_LICENCE = ("Government of Gilgit-Baltistan, Planning & Development "
                  "Department")
GB_POP_NOTE = (
    "The 7th Population and Housing Census 2023, read from the territory's "
    "own government rather than from the Bureau of Statistics: Gilgit-"
    "Baltistan is enumerated apart from the census proper -- its people are "
    "outside the 241.5 million Pakistan reports -- and the Bureau publishes "
    "no census table for it at any path, so this count is taken from "
    "Gilgit-Baltistan at a Glance 2025, which prints it over a source line "
    "naming the Bureau. The same table carries a 2026 projection beside the "
    "census column; this is the count and not the projection. {control}")
GB_WHOLE_CONTROL = (
    "The ten districts add up to this figure to the person, which is the one "
    "control the table supplies on itself.")
GB_PART_CONTROL = (
    "This district and the other nine add up to the territory's own printed "
    "row to the person, which is the one control the table supplies on "
    "itself.")
# What the field says when the booklet cannot be read, which is not what an
# empty field says. Named rather than generic: a reader should be able to tell
# "the office publishes nothing" from "the fetch has not been run".
GB_POP_GAP = (
    "The 7th Population and Housing Census 2023 counted Gilgit-Baltistan, and "
    "the Bureau of Statistics publishes no table of the count: Table 9 and "
    "Table 11 answer 404 for this territory under every name the four "
    "provinces and Islamabad are filed under. The route that does publish it "
    "is the territory's own Planning & Development Department, whose "
    "Gilgit-Baltistan at a Glance 2025 prints the census's district counts, "
    "and this run could not read that booklet. The question was asked and "
    "answered; what is missing is a copy of the answer this run could open.")


PERCENTAGE = re.compile(r"^\d+(?:\.\d+)?%$")


def gb_cells(cells: list[Cell]) -> tuple[str, list[str]]:
    """One booklet row as its label and the cells printed after it.

    The same rejoining ``printed`` does, for the same reason and against the
    same measurement: this table splits a figure across words too, and more
    freely than the Bureau's does -- Ghanche's 156,697 arrives as ``156,``,
    ``6``, ``9``, ``7`` and Shigar's density 22 as ``2`` and ``2``. The gap
    inside every one of those is 0 points and the gap between two columns is
    never less than 12, so ``GAP`` separates them here as it does there.

    The growth rate is a cell like any other and is kept as printed, because
    it is the thing the counts are checked against rather than a figure to
    publish. A word arriving after the figures have started means this is not
    a row of this table -- the header's ``Sq.KM 2017 2023 (%) 2026`` is the
    case -- and the row is refused rather than half-read.
    """
    label: list[str] = []
    out: list[list] = []                  # [right edge, text]
    for x0, x1, text in cells:
        if PERCENTAGE.match(text):
            out.append([x1, text])
            continue
        if not NUMBER.match(text):
            if out:
                return "", []
            label.append(text)
            continue
        if out and NUMBER.match(out[-1][1]) and x0 - out[-1][0] <= GAP:
            out[-1][0] = x1
            out[-1][1] += text.replace(",", "")
        else:
            out.append([x1, text.replace(",", "")])
    return " ".join(label), [text for _right, text in out]


def gb_grown(earlier: int, later: int) -> float:
    """The annual rate that takes one census count to the next, as a percent.

    Stated rather than fitted: this is compound growth over the years between
    the two rounds, which is what the booklet's own column turns out to be.
    """
    return ((later / earlier) ** (1.0 / GB_POP_SPAN) - 1.0) * 100.0


def gb_population(blob: bytes) -> dict[str, int]:
    """The 2023 census count for each district and for the territory.

    Keyed by the booklet's own spellings, which are the ten names this file
    already declares for Gilgit-Baltistan, plus ``GB`` for the territory row.

    Raises ``LookupError`` when the booklet carries no such table -- it is
    reissued annually and a table that has moved or gone leaves the territory
    where it was, declared -- and refuses outright when the table is there and
    does not read, which is a different failure and must not be the same one.
    """
    wanted = set(TERRITORIES["gb"][2]) | {GB_POP_WHOLE}
    for number, rows in enumerate(words_by_row(blob), start=1):
        page = [(" ".join(t for _a, _b, t in cells), cells) for cells in rows]
        if not any(GB_POP_TABLE.search(line) for line, _cells in page):
            continue
        found: dict[str, int] = {}
        for _line, cells in page:
            name, printed_cells = gb_cells(cells)
            if name not in wanted or len(printed_cells) != len(GB_POP_COLUMNS):
                continue
            rate = printed_cells[GB_POP_RATE]
            # The shape of the row, not its contents: exactly one cell is a
            # percentage and it is the fourth. A row of six cells that does
            # not sit that way is not a row of this table, and the name check
            # below is what refuses if one of the ten was in it.
            if not PERCENTAGE.match(rate) or not all(
                    cell.isdigit() for index, cell in enumerate(printed_cells)
                    if index != GB_POP_RATE):
                continue
            earlier = int(printed_cells[GB_POP_EARLIER])
            later = int(printed_cells[GB_POP_COUNT])
            # The check that says which column is which. A 2026 projection
            # read as a census, or the 2017 column read as the 2023 one, is
            # invisible in the figure and fails here.
            drift = abs(gb_grown(earlier, later) - float(rate.rstrip("%")))
            if drift > GB_POP_SLACK:
                raise SystemExit(
                    f"pakistan: Gilgit-Baltistan's {name} grows from "
                    f"{earlier:,} to {later:,} at {gb_grown(earlier, later):.2f}% "
                    f"a year over {GB_POP_SPAN} years, against the {rate} the "
                    f"booklet prints beside them. Either these are not the two "
                    f"census columns -- the projection sits beside them -- or "
                    f"the table has changed shape")
            found[name] = later
        whole = found.pop(GB_POP_WHOLE, None)
        if whole is None or sorted(found) != sorted(TERRITORIES["gb"][2]):
            raise SystemExit(
                f"pakistan: page {number} of Gilgit-Baltistan at a Glance "
                f"carries the district population table and this run read "
                f"{sorted(found)} from it"
                + ("" if whole else " and no territory row")
                + f", where the map draws {sorted(TERRITORIES['gb'][2])}")
        summed = sum(found.values())
        if summed != whole:
            raise SystemExit(
                f"pakistan: Gilgit-Baltistan's ten districts sum to "
                f"{summed:,} against the {whole:,} printed for the territory "
                f"beneath them. The table disagrees with itself, or a row was "
                f"read from the wrong column")
        log(f"    {len(found)} districts on page {number}, summing to the "
            f"territory's own printed {whole:,}")
        found[GB_POP_WHOLE] = whole
        return found
    raise LookupError("no page carries 'District Wise Population and Area of GB'")


def gb_weighted(counts: dict[str, int]) -> dict[str, float]:
    """The ten district sect figures, weighted by their census populations.

    This is what the territory row publishes, and the populations are what
    made it possible: before they were read there was no way to add the ten
    districts up, so the territory carried PILDAT's separate territory-wide
    estimate instead and the two were never compared.

    They do not agree. The same paper's area-wise map and its territory-wide
    figure describe different populations, most sharply on the Ismaili share.
    The weighted one is published because it is the only one of the two that
    is consistent with what this map shows underneath it -- a territory whose
    own districts do not add up to it is a contradiction a reader can see and
    cannot resolve. ``GB_DISAGREEMENT`` says the other figure exists and what
    it is, so choosing between them is visible rather than silent.

    Empty when any district's population is missing, because a partial
    weighting is the dangerous kind of wrong: it would quietly reweight the
    territory onto whichever districts happened to be read.

    Largest-remainder rounding, so the four published shares sum to 100.0
    exactly rather than to 99.9 through four independent roundings.
    """
    whole = counts.get(GB_POP_WHOLE)
    if not whole:
        return {}
    people = {name: counts.get(name) for name in GB_DISTRICT_SECTS}
    if not all(people.values()):
        return {}
    counted = sum(people.values())
    if counted != whole:
        raise SystemExit(
            f"pakistan: Gilgit-Baltistan's ten districts hold {counted:,} "
            f"people against the {whole:,} printed for the territory. The "
            f"sect shares are weighted by these, so a territory row that is "
            f"not the sum of its districts would publish a composition of a "
            f"population that does not exist")
    exact: dict[str, float] = {}
    for name, sects in GB_DISTRICT_SECTS.items():
        for sect, pct in sects.items():
            exact[sect] = exact.get(sect, 0.0) + people[name] * pct / 100.0
    return to_hundred({sect: 100.0 * value / whole
                       for sect, value in exact.items()})


def gb_disagreement(weighted: dict[str, float]) -> str:
    """The territory-wide figure that is not published, named where it is due.

    PILDAT gives both, in one paper, and they differ by eight and a half
    points on the Ismaili share. Publishing one and saying nothing about the
    other would hide a disagreement inside the source rather than a
    disagreement between sources, which is the harder kind for a reader to
    find on their own.
    """
    if not weighted:
        return ""
    said = ", ".join(f"{sect} {pct}%" for sect, pct
                     in sorted(GB_SECTS.items(), key=lambda kv: -kv[1]))
    return (" This row is the ten districts' own figures weighted by their "
            "2023 census populations, which is why it agrees with what is "
            "drawn beneath it. The same paper also gives a territory-wide "
            "estimate -- " + said + " -- and the two do not describe the same "
            "population: they are eight and a half points apart on the "
            "Ismaili share. Neither has been adjusted to the other. The "
            "weighted figure is the one published because a territory whose "
            "districts do not add up to it is a contradiction a reader can "
            "see and cannot resolve; the likeliest reading of the gap is that "
            "the faith map's flat 100% for Hunza and Ghizer leaves no room "
            "for the Ismaili minorities the same page's prose puts in Skardu.")


def gb_population_fields(name: str, counts: dict[str, int],
                         control: str) -> dict[str, Any]:
    """The population field for one Gilgit-Baltistan row, or a stated gap.

    A gap and never a bare one: ``record`` defaults an unfilled field to a gap
    with nothing in it, which on the map reads as a fetch nobody has run, and
    that is a different claim from the one this territory has to make.
    """
    count = counts.get(name)
    if count is None:
        return {"population": gap(NOT_AVAILABLE, GB_POP_GAP)}
    return {
        "population": measure(count, year=GB_POP_YEAR, source=GB_POP_SOURCE),
        "population_note": GB_POP_NOTE.format(control=control),
    }


def ajk_records(found: dict[str, dict[str, int]], whole: dict[str, int],
                tongues: dict[str, float] | None = None,
                short: str = "") -> list[dict[str, Any]]:
    """Azad Jammu and Kashmir, and the one second-level shape drawn for it.

    Religion and population from the printed territory row, which the check
    above has just shown equals the ten districts column for column. The
    districts themselves are not published as records: geoBoundaries draws
    Azad Kashmir as a single second-level unit, so ten rows would reach one
    shape, nine of them would lose, and the tenth would put a district's
    figures on the whole territory -- the Karachi failure in reverse and far
    worse, because it would look entirely normal.

    Language is the ten districts of Table 15.33 weighted into one row for the
    same reason and by the same populations. Both rows carry it: they are the
    same territory drawn twice, and an admin2 shape that covers the whole of
    AJ&K has the whole of AJ&K's languages on it.
    """
    total = whole["TOTAL"]
    parts = {k: v for k, v in whole.items() if k != "TOTAL"}
    cite = [{"field": "population/religion", "name": AJK_SOURCE,
             "url": AJK_BOOK, "license": AJK_LICENCE}]
    # Built once and put on both rows. No ``language_year``: Table 15.33
    # prints none, and 2023 is the yearbook's cover rather than the figures'
    # date -- the distinction the religion table above is careful about.
    said: dict[str, Any] = {"language": gap(NOT_AVAILABLE, AJK_LANGUAGE_GAP)}
    if tongues:
        said = {
            "language": [{"group": group, "pct": pct} for group, pct
                         in sorted(tongues.items(), key=lambda kv: -kv[1])],
            "language_note": AJK_TONGUE_NOTE.format(short=short),
            "language_basis": AJK_TONGUE_BASIS,
        }
        cite.append({"field": "language", "name": AJK_TONGUE_SOURCE,
                     "url": AJK_BOOK, "license": AJK_TONGUE_LICENCE})
    return [
        record("PAK-ajk", "Azad Jammu and Kashmir", level="admin1",
               parent="PAK", aliases=["Azad Kashmir"],
               population=measure(total, year=AJK_YEAR, source=AJK_SOURCE),
               religion=shares(parts, total=total) or gap(NOT_AVAILABLE),
               religion_year=AJK_YEAR, religion_note=AJK_NOTE,
               sources=list(cite), **said),
        record("PAK-ajk-azad-kashmir", "Azad Kashmir", level="admin2",
               parent="PAK", parent_name="Azad Jammu and Kashmir",
               parent_aliases=["Azad Kashmir"],
               population=measure(total, year=AJK_YEAR, source=AJK_SOURCE),
               religion=shares(parts, total=total) or gap(NOT_AVAILABLE),
               religion_year=AJK_YEAR,
               religion_note=AJK_NOTE + " " + AJK_ONE_SHAPE,
               sources=list(cite), **said),
    ]


def declared_gaps(absent: dict[str, list[tuple[str, str]]],
                  counts: dict[str, int] | None = None,
                  households: dict[str, int] | None = None,
                  year: int | None = None) -> list[dict[str, Any]]:
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
    counts = counts or {}
    for slug, _line in absent[APART]:
        if slug not in TERRITORIES:
            continue
        province, alias, inside = TERRITORIES[slug]
        source = [{"field": "note", "name": SOURCE, "url": URL,
                   "license": LICENCE}]
        # Gilgit-Baltistan is the one territory with figures from somewhere
        # other than the census -- religion from PILDAT, mother tongue from a
        # newspaper's account of GB-MICS -- so its territory row carries those
        # and the districts below it keep the gap: both estimates are for the
        # whole, and its districts differ sharply from either average.
        #
        # Both fields start as the declared gap and are replaced only where
        # there is something to replace them with. They are built into one
        # dict rather than passed to `record` separately because `**fields`
        # and an explicit keyword for the same field is a TypeError, and the
        # gap is what that keyword used to be.
        fields: dict[str, Any] = {
            "religion": gap(NOT_AVAILABLE, TERRITORY_GAP),
            "language": gap(NOT_AVAILABLE, TERRITORY_GAP),
        }
        if slug == "gb":
            fields.update(gb_religion(counts))
            fields.update(gb_language(households, year))
            fields.update(gb_population_fields(GB_POP_WHOLE, counts,
                                               GB_WHOLE_CONTROL))
            spoke = ({"field": "language", "name": GB_MICS_SOURCE,
                      "url": GB_MICS_BOOK, "license": GB_MICS_LICENCE,
                      "year": year} if households else
                     {"field": "language", "name": GB_TONGUE_SOURCE,
                      "url": GB_TONGUE_URL, "year": GB_TONGUE_YEAR})
            source = list(source) + [
                {"field": "religion", "name": GB_SOURCE, "url": GB_URL,
                 "year": GB_YEAR},
                spoke,
            ]
            if GB_POP_WHOLE in counts:
                source = list(source) + [
                    {"field": "population", "name": GB_POP_SOURCE,
                     "url": GB_BOOK, "license": GB_POP_LICENCE,
                     "year": GB_POP_YEAR}]
        out.append(record(
            f"PAK-{slug}", province, level="admin1", parent="PAK",
            aliases=list(alias),
            sources=list(source), **fields))
        for name in inside:
            # Gilgit-Baltistan's ten have a sect figure of their own and, now,
            # the census count of the people those shares divide; Azad
            # Kashmir's one shape has neither, and keeps the declared gap.
            fields = gb_district_religion(name) if slug == "gb" else {}
            district_source = list(source)
            if fields:
                district_source += [
                    {"field": "religion", "name": GB_SOURCE, "url": GB_URL,
                     "year": GB_YEAR}]
            if slug == "gb":
                fields.update(gb_population_fields(name, counts,
                                                   GB_PART_CONTROL))
                if name in counts:
                    district_source += [
                        {"field": "population", "name": GB_POP_SOURCE,
                         "url": GB_BOOK, "license": GB_POP_LICENCE,
                         "year": GB_POP_YEAR}]
            out.append(record(
                f"PAK-{slug}-{name.lower().replace(' ', '-')}", name,
                level="admin2", parent="PAK", parent_name=province,
                parent_aliases=list(alias),
                religion=fields.pop("religion", None)
                or gap(NOT_AVAILABLE, TERRITORY_GAP),
                # The one field that is a different gap for the two
                # territories. Azad Kashmir's single shape is the territory,
                # so it gets the territory's figure and never reaches here;
                # Gilgit-Baltistan's ten are real districts with no language
                # of their own, and what they are missing is not what the
                # general note describes.
                language=gap(NOT_AVAILABLE,
                             GB_TONGUE_DISTRICT_GAP if slug == "gb"
                             else TERRITORY_GAP),
                sources=district_source, **fields))
    if out:
        log(f"  {len(out)} records declaring what is not published, rather "
            f"than leaving the field empty")
    return out


# The same for religion, and for one district. Table 9's categories are
# Muslim, Christian, Hindu, Ahmadi, Scheduled Castes, Sikh, Parsi and Other,
# and the Kalash faith is not among them -- so the one community in Pakistan
# that practises a religion older than all eight is counted in the eighth
# column, unnamed, in the one district where it lives.
#
# The count is not divided here either, and for a sharper reason than above:
# the census's 4,970 and the community's own size do not agree. Accounts of
# the Kalash put adherents at roughly 3,000 to 4,000, while Table 11 counts
# 5,065 Kalasha speakers in the same district -- the gap between the two being
# Kalash families who have converted and kept the language. Naming the whole
# of Other as Kalash would therefore overstate it by a quarter, and naming
# part of it would mean choosing which estimate to believe.
RELIGION_DISTRICT_NOTES: dict[str, str] = {
    "CHITRAL":
        " The 4,970 people in Other religion here are, in the main, the "
        "Kalash: Pakistan's last community practising the pre-Islamic "
        "religion of the Hindu Kush, in the Bumburet, Rumbur and Birir "
        "valleys. The census form has no category for them. Their own size "
        "is put at roughly 3,000 to 4,000 adherents, against 5,065 Kalasha "
        "speakers counted in this district by Table 11 -- the difference "
        "being families who converted and kept the language -- so the column "
        "is left as the census prints it rather than renamed.",
}


# Chitral's Other, divided. The owner asked for numbers rather than the note
# below, and this is what numbers here can honestly be.
#
# The census prints one figure for the column -- 474,149 people, 92.4% of the
# district -- and no breakdown of it. Khowar has no column on the 2023 form,
# so that one number is very nearly the whole Kho population plus every small
# language of the valleys. What follows names them.
#
# **Khowar is the remainder, not a count, and that is the whole design.** No
# source publishes a Chitral-specific Khowar figure: Ethnologue's 580,000 is
# every Khowar speaker anywhere, which is more people than live in Chitral,
# because Khowar is also spoken in Ghizer, Gupis-Yasin and upper Swat. So the
# minority languages take their published estimates, Khowar takes what is
# left, and every error in those estimates lands on the largest figure where
# it is proportionally smallest. This is the same discipline Gilgit-Baltistan's
# table uses, where Balti carries the residual for being the least precise
# figure its source gives.
#
# It also means **Khowar is overstated**, by the speakers of the languages with
# no published Chitral figure: Wakhi in Broghil and upper Yarkhun, Kyrgyz in
# the same corner, Gujari, Sarikoli. Those are families and hundreds rather
# than thousands, against 442,000, and inventing a number for each to avoid
# saying so would be the worse trade. The note says it instead.
#
# The estimates are of mixed vintage and mostly count speakers rather than
# households or mother-tongue respondents. They are the published figures,
# not adjusted for Chitral's growth since they were made -- adjusting them
# would be a second layer of this project's arithmetic on top of somebody
# else's, and the residual already absorbs whatever they are short by.
CHITRAL_TONGUES: dict[str, int] = {
    "Palula": 10_000,    # Ashret and Biori valleys, Puri in Shishi, Kalkatak
    "Yidgha": 6_150,     # the Lutkoh valley, west of Chitral town
    "Dameli": 5_000,     # the Damel valley
    "Gawar-bati": 4_000, # Arandu, of some 12,000 across the Afghan border
    "Madaklashti": 4_000,  # Badakhshani Persian, in the Shishi valley
    "Kativiri": 3_000,   # "less than 3,000", on the Nuristan border
}
CHITRAL_RESIDUAL = "Khowar"
CHITRAL_SPLIT_NOTE = (
    " **The division of that Other below is not the census's.** The Bureau "
    "prints one figure for the column and no breakdown. Khowar, the language "
    "of the Kho and the valley's lingua franca, has no column on the 2023 "
    "form, so nearly all of the column is Khowar -- and the figure shown for "
    "it here is a remainder rather than a count: the six smaller languages "
    "are set to published speaker estimates of mixed vintage and Khowar takes "
    "what is left of the census's 474,149. Every error in those estimates "
    "therefore lands on Khowar. Khowar is also overstated by the tongues no "
    "source counts separately in this district -- Wakhi in Broghil and upper "
    "Yarkhun, Kyrgyz beside them, Gujari, Sarikoli -- which are families and "
    "hundreds against 442,000. Only the district total, and the Pashto, "
    "Kalasha, Urdu and Kohistani beside it, are counted by the census. "
    "Khyber Pakhtunkhwa's own row above keeps the Other unbroken, because "
    "this estimate was made for this district and not for the province.")


def chitral_split(counts: dict[str, int]) -> dict[str, int]:
    """Chitral's row with its Other column replaced by named languages.

    Takes and returns the table's own counts, so the result is still a row
    that sums to the district's printed total -- the substitution is inside
    the Other column and touches nothing else. ``shares()`` then divides it
    exactly as it divides an unmodified row.

    Refuses rather than clamps if the estimates outgrow the column. A negative
    remainder would mean either the column has shrunk below what the small
    languages are believed to hold or an estimate here has been raised too
    far, and both are things to look at rather than round up to zero.
    """
    bucket = counts["Other language"]
    named = sum(CHITRAL_TONGUES.values())
    if named >= bucket:
        raise SystemExit(
            f"pakistan: Chitral's named minority languages come to {named:,} "
            f"against an Other column of {bucket:,}, so {CHITRAL_RESIDUAL} "
            f"would be {bucket - named:,}. The remainder carries every error "
            f"in those estimates and it has run out of room to.")
    out = {k: v for k, v in counts.items() if k != "Other language"}
    out[CHITRAL_RESIDUAL] = bucket - named
    out.update(CHITRAL_TONGUES)
    if sum(v for k, v in out.items() if k != "TOTAL") != counts["TOTAL"]:
        raise SystemExit(
            "pakistan: Chitral's split no longer sums to its printed total")
    return out


# What the Other is, in the six districts where it is still large enough to
# be the thing a reader asks about. Keyed by the table's own spelling, which
# is what ``found`` is keyed by.
#
# These name the languages; they do not divide the figure between them, and
# the difference is deliberate. The Bureau prints one number for the column
# and no breakdown of it, so any split would be this project's arithmetic
# wearing the census's clothes -- and the figures that would have to drive it
# are survey estimates of mixed vintage that disagree with each other: Dameli
# is "perhaps seventy families" in one account and 5,000 speakers in another,
# an order of magnitude apart. The one authoritative source, SIL's
# Sociolinguistic Survey of Northern Pakistan volume 5, answers 403 to this
# project and is not worked around.
#
# So the column keeps the census's number and the note says what is in it.
# A reader who wants the split can be told it is not published; a reader
# shown a split this file invented cannot tell that it was.
TONGUE_DISTRICT_NOTES: dict[str, str] = {
    "CHITRAL": CHITRAL_SPLIT_NOTE,
    "MANSEHRA":
        " The Other here is largely Gujari, the language of the Gujar "
        "herding communities of the Kaghan valley and the hills above it, "
        "which the census form does not name.",
    "BATAGRAM":
        " The Other here is largely Gujari, which the census form does not "
        "name, alongside the Kohistani spoken across the district's northern "
        "boundary.",
    "QUETTA":
        " The Other here is largely Hazaragi, the Persian variety of "
        "Quetta's Hazara population, which the census form does not name.",
    "RAWALPINDI":
        " The Other here is largely Pothwari, the speech of the Potohar "
        "plateau; the form names Punjabi but not this, and where the line "
        "between the two is drawn is a matter the census leaves to the "
        "person answering.",
    "SWAT":
        " The Other here is largely Torwali in Bahrain and Gawri in the "
        "Kalam valley, with Gujari in the hills -- none of them named on the "
        "census form.",
}


def read_tongues(slug: str, province: str,
                 counted: set[str]) -> tuple[dict[str, dict[str, int]], str]:
    """Table 11 for one province, read the same way Table 9 was.

    ``counted`` is the set of districts Table 9 produced, after merging, and
    it is the control this table is held to. The two tables come out of one
    census and one office, so they should name the same districts; if they do
    not, one of them has been misread, and the failure mode is silent -- a
    district whose language row was never found simply has no language, which
    looks exactly like a district the census did not ask.

    So the sets are compared rather than the rows zipped, and any difference
    in either direction stops the run. Language is added to Pakistan here; it
    is not worth adding it in a way that can quietly go missing.

    A province whose file cannot be fetched returns nothing and says so. That
    is not fatal: religion, population and the province row are already read
    by then, and losing this table should cost the language field rather than
    the country.
    """
    try:
        blob, url = fetch(TONGUE_FILES[slug])
    except LookupError as err:
        log(f"    NO TABLE 11 -- {err}")
        return {}, ""
    log(f"    Table 11: {len(blob):,} bytes from {url}")
    found, whole = districts(blob, province, TONGUE_COLUMNS)
    if not found:
        log("    NO TABLE 11 -- fetched but no districts read")
        return {}, ""
    whole = province_row(slug, province, found, whole, TONGUE_COLUMNS)
    check(province, found, whole, "mother tongues")
    merge(province, found, TONGUE_COLUMNS)
    if set(found) != counted:
        raise SystemExit(
            f"{province}: Table 11 names districts Table 9 does not, or the "
            f"other way about. Only in Table 11: "
            f"{', '.join(sorted(set(found) - counted)) or 'none'}. Only in "
            f"Table 9: {', '.join(sorted(counted - set(found))) or 'none'}")
    log(f"    and its {len(found)} districts are Table 9's districts")
    return found, url


def spoken(counts: dict[str, int], name: str = "") -> dict[str, Any]:
    """One unit's mother-tongue fields, from its row of Table 11.

    ``name`` is the table's spelling of the district, and only so that the
    six districts whose Other is still large can say what is in it. A
    province gets the general note alone: "largely Khowar" is true of Chitral
    and says nothing useful about Khyber Pakhtunkhwa.
    """
    if name == "CHITRAL":
        counts = chitral_split(counts)
    total = counts["TOTAL"]
    parts = {k: v for k, v in counts.items() if k != "TOTAL"}
    return {
        "language": shares(parts, total=total) or gap(NOT_AVAILABLE),
        "language_year": YEAR,
        "language_note": TONGUE_NOTE + TONGUE_DISTRICT_NOTES.get(name, ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    log("pakistan: Bureau of Statistics, Census 2023, Tables 9 and 11")
    records: list[dict[str, Any]] = []
    # Every district name the run actually read, so the notes keyed by name
    # can be held to it below.
    named: set[str] = set()
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
        tongues, tongue_url = read_tongues(slug, province, set(found))
        named.update(found)

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
        if tongue_url:
            cite.append({"field": "language", "name": TONGUE_SOURCE,
                         "url": tongue_url, "license": LICENCE})
        # The province's own Table 11 row, recovered the same way its religion
        # row was: by summing the districts this reader has just proved add up
        # to the printed province total. Summing is safe here and only here,
        # because that equality was checked against the file's own row.
        here = {}
        if tongues:
            here = spoken({column: sum(d[column] for d in tongues.values())
                           for column in TONGUE_COLUMNS})
        records.append(record(
            f"PAK-{slug}", province, level="admin1", parent="PAK",
            population=measure(total, year=YEAR, source=SOURCE),
            religion=shares({k: v for k, v in counts.items() if k != "TOTAL"},
                            total=total) or gap(NOT_AVAILABLE),
            religion_year=YEAR,
            religion_note=TERRITORY_NOTE if slug in ONE_DISTRICT else PROVINCE_NOTE,
            sources=list(cite), **here))
        for name, counts in sorted(found.items()):
            total = counts["TOTAL"]
            parts = {k: v for k, v in counts.items() if k != "TOTAL"}
            note = NOTE + RELIGION_DISTRICT_NOTES.get(name, "")
            if name in assembled:
                note += (" The boundary file draws one shape here, so this is "
                         + ", ".join(p.title() for p in assembled[name])
                         + " summed.")
            said = spoken(tongues[name], name) if name in tongues else {}
            records.append(record(
                f"PAK-{slug}-{name.lower().replace(' ', '-')}",
                name.title(), level="admin2", parent="PAK",
                parent_name=province, aliases=list(ALIASES.get(name.title(), ())),
                population=measure(total, year=YEAR, source=SOURCE),
                religion=shares(parts, total=total) or gap(NOT_AVAILABLE),
                religion_year=YEAR, religion_note=note,
                sources=list(cite), **said))

    # A note keyed to a district that no longer exists reaches nobody, and
    # reaches nobody silently: the district keeps the general note and looks
    # exactly like a district nothing was ever written for. The Bureau
    # renames and splits districts between rounds -- Chitral and Kohistan are
    # each several districts now -- so this is a thing that will happen.
    stale = sorted((set(TONGUE_DISTRICT_NOTES) | set(RELIGION_DISTRICT_NOTES))
                   - named)
    if stale:
        raise SystemExit(
            "pakistan: a note is written for "
            + ", ".join(stale)
            + ", which the tables do not name. Either the district was "
              "renamed or it was split, and in both cases the note now has "
              "to say something about somewhere else.")
    log(f"  {len(TONGUE_DISTRICT_NOTES)} districts say what their Other "
        f"language holds, and {len(RELIGION_DISTRICT_NOTES)} what their "
        f"Other religion does")

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
                # Table 15.33 is in the same book and is a separate finding:
                # the religion table is the census reprinted and this one is
                # the Kashmir Liberation Cell's. A yearbook that drops it
                # should cost the language field and not the territory, so a
                # missing caption leaves the declared gap standing -- while a
                # caption that is there and does not read refuses, which is
                # ajk_tongue_table's decision and not this block's.
                tongues: dict[str, float] = {}
                short = ""
                try:
                    printed_tongues = ajk_tongue_table(blob)
                except LookupError as err:
                    log(f"    NO LANGUAGE TABLE -- {err}")
                else:
                    tongues, short = ajk_tongue_weighted(
                        printed_tongues, found, whole)
                    log("    AJ&K languages: "
                        + ", ".join(f"{g} {p}%" for g, p in
                                    sorted(tongues.items(),
                                           key=lambda kv: -kv[1])))
                records.extend(ajk_records(found, whole, tongues, short))
                absent[APART] = [(slug, line) for slug, line in absent[APART]
                                 if slug != "ajk"]

    # Gilgit-Baltistan, from the territory's own P&DD, where the Bureau's
    # series stops. Only when it does stop, for the reason Azad Kashmir's
    # block gives: a census table for this territory would be the same office
    # reading the same question as the four provinces, and would win without a
    # rule needing to be written for it.
    counts: dict[str, int] = {}
    households: dict[str, int] = {}
    mics_year: int | None = None
    if any(slug == "gb" for slug, _line in absent[APART]):
        log("  Gilgit-Baltistan, from the territory's own At a Glance")
        try:
            blob, url = fetch((GB_BOOK,))
        except LookupError as err:
            log(f"    NOT READ -- {err}")
        else:
            log(f"    {len(blob):,} bytes from {url}")
            try:
                counts = gb_population(blob)
            except LookupError as err:
                # The booklet is reissued every year. A table that is no
                # longer in it leaves the territory's population declared
                # rather than stopping the run -- which is where it was before
                # this route existed. A table that is there and does not read
                # refuses instead, and that is gb_population's decision.
                log(f"    NOT READ -- {err}")

        # And the same department's survey, which is where the language comes
        # from. A separate fetch because it is a separate publication and a
        # separate finding: the booklet has the census's populations and no
        # language, the survey report has language and is not a census. Either
        # can fail without taking the other with it, and the field that fails
        # falls back to what it had -- population to a stated gap, language to
        # the Pamir Times account of the 2017 round.
        log("  Gilgit-Baltistan's language, from the territory's own MICS")
        try:
            blob, url = fetch((GB_MICS_BOOK,))
        except LookupError as err:
            log(f"    NOT READ -- {err}")
        else:
            log(f"    {len(blob):,} bytes from {url}")
            try:
                households, mics_year = gb_mics_language(blob)
            except LookupError as err:
                log(f"    NO LANGUAGE TABLE -- {err}")

    records.extend(declared_gaps(absent, counts, households, mics_year))
    out = args.out or PROCESSED / "pakistan_district.json"
    write_json(out, records)
    provinces = sum(1 for r in records if r["level"] == "admin1")
    log(f"  {len(records) - provinces} districts and {provinces} provinces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
