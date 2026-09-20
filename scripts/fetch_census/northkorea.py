#!/usr/bin/env python3
"""North Korea: the 2008 census's own head count, province by province and
county by county -- and the measurement behind the three declarations.

``NOT_COLLECTED_POLICY["PRK"]`` says that North Korea's census asks nothing
about religion, ethnicity or language. That was an assertion when it was
written; this adapter is the check. The DPR Korea 2008 Population Census was
enumerated from 1 to 15 October 2008 by about 35,000 enumerators, with UNFPA
technical support, and its **National Report** (Central Bureau of Statistics,
Pyongyang, 2009) was published: 278 pages, 53 tables, and all three census
questionnaires printed as annexes. The UN Statistics Division serves a copy,
which is what is read here.

**What the census asks.** Annex 2, the CPF 2 questionnaire, puts exactly one
question on the form about who a person is: ``P7  What is ____'s
nationality?``, answered ``1 Korean`` or ``2 Others``. The rest of Module 2 is
household membership, where a person is registered, relationship to the head
of household, sex and date of birth, and then disability, education, economic
activity, migration and fertility. There is no religion question, no ethnicity
question and no question about mother tongue or language.

**What the report publishes.** The List of Tables runs Table 1 to Table 53 and
is reproduced in ``docs/SOURCES.md``. Table 5, *Population by Nationality, by
5-year Age Group and by Sex*, is the one table that carries P7's answer, and it
is national: 23,349,326 Koreans and **533** people of other nationalities, by
age and by sex, and by nothing else. Not one of the 53 tables crosses religion,
ethnicity or language with anything, because the census never collected them:
searched over the text of all 278 pages for *religio*, *ethnic*, *mother
tongue*, *language*, *church*, *Buddhis*, *Christian*, *Chondo*, *Confucian*
and *faith*, **two pages match**. One is Table 22's definition of literacy,
"the ability of an individual to read and write a simple message in any
language". The other is a line of Table 37's occupation list, "Religious
professionals", 103 people. Neither is a composition, and reading either as one
would put a figure on the map that no census produced.

So the three declarations stand, and ``scripts/common.py`` now says what was
read rather than merely what is believed. Nationality is not written onto the
ethnicity field here: Table 5 has no geography, and the Maldives entry settles
the principle -- a passport is not an ethnic group.

**What is written instead.** Every one of North Korea's 11 first-level and 179
second-level units carried ``not_available`` for population before this, and
the census counts them all. Table 2, *Population by Sex and by Urban-Rural, by
City/District/County and Province* (pages 18-22 of the report), prints Both
Sexes, Male and Female for the country, for each of the ten first-level areas
the DPRK had in 2008, and for every city, district and county inside them. That
is a head count and a sex ratio for all 190 shapes.

**Two geographies, fifteen years apart.** The report's geography is the one of
October 2008; the boundary file draws the one after the 2010 changes, and they
differ in four places. Every difference is settled by summing the report's own
rows over the units the boundary file draws -- never by splitting one:

* **Nampo** is a first-level city in the boundary file and was six units of
  South Phyongan in 2008 (Nampho City, Onchon, Ryonggang, Taean, Kangso and
  Chollima). Nampo is their sum; South Pyongan is its printed total less that
  sum, which is exactly its 21 remaining counties.
* **Kangnam, Junghwa and Sangwon** are North Hwanghae in the boundary file and
  were Pyongyang in 2008. They are moved, and both provinces re-add.
* **Chongjin City** is one shape; the report prints its seven districts and
  marks them "*Part of Chongjin city*". **Hamhung City** is one shape; the
  report prints six districts marked "*part of Hamhung city*" and Hungnam
  beside them, and the seven together are what re-adds to South Hamgyong.
* **Pyongyang** the shape is the city proper: the report's nineteen districts
  less Unjong, which the boundary file draws separately, and less Kangdong,
  which it also draws separately.

Nothing here is an estimate: every figure written is either a row of Table 2 or
a sum of rows of Table 2, and the checks below refuse the run unless those sums
close on the publisher's own totals.

**Self-checks**, each of which refuses rather than writing:

* every row's Male plus Female must equal the Both Sexes printed beside it, and
  Urban plus Rural must equal All Areas, three columns over -- six equations,
  which is also how a row's nine figures are told apart, the report writing its
  thousands separator as a space;
* each of the ten first-level areas must equal the sum of its own county rows;
* the ten must equal the printed DPR Korea row, 23,349,859;
* after the four re-districtings, each of the 11 shapes must equal the sum of
  its children, and the 11 must still come to 23,349,859;
* the counts must be 11 and 179 exactly, and every name must be one this
  reader knows -- a page the text extraction garbles is a refusal, not a
  silent gap.

**What the 23,349,859 is not.** It is the census's *civilian* count: the note
under Table 2 says "Includes all individuals living in private households and
institutional living quarters". The other DPRK file the Statistics Division
serves, the one-page preliminary results of the same census, is what says what
that leaves out -- a civilian sub-total of 23,348,845 against a total of
24,051,218 that "includes population living in military camps", 702,373 apart.
Those people were enumerated on a shorter form (Annex 3, CPF 2B) and the report
allocates them to no province, so no province figure here can be made to
include them. Every row says so.

Usage:
    python -m scripts.fetch_census.northkorea
    python -m scripts.fetch_census.northkorea --probe
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Iterator

from ._shared import (
    PROCESSED, RAW, collection_gap, download, gap, log, measure, record,
    write_json, NOT_AVAILABLE,
)

OUT = "northkorea_county.json"
YEAR = 2008

REPORT = ("https://unstats.un.org/unsd/demographic/sources/census/wphc/"
          "North_Korea/Final%20national%20census%20report.pdf")
SOURCE = ("Central Bureau of Statistics, DPR Korea, 2008 Population Census -- "
          "National Report (Pyongyang, 2009), Table 2")
LICENCE = ("Central Bureau of Statistics, DPR Korea. Official publication; "
           "copy served by the UN Statistics Division.")

# Table 2's own DPR Korea row, which is what every sum here has to reach, so
# a re-read that drifts from it stops.
CIVILIAN_TOTAL = 23_349_859

# Table 1's All Ages row, the whole population the census counted, and the
# only place in the report the figure appears. It is 702,372 above Table 2's,
# and the census's own preliminary results say what the difference is: that
# one-page sheet, the other DPRK file the Statistics Division serves, prints a
# civilian sub-total "living in regular households and in institutional living
# quarters" against a total that "includes population living in military
# camps", 702,373 apart on the manual tallies the report's computerised
# figures replaced.
CENSUS_TOTAL = 24_052_231
IN_CAMPS = CENSUS_TOTAL - CIVILIAN_TOTAL
TABLE_ONE = "Total and Percent Distribution of Population by Sex and Sex-Ratio"
PRELIM = ("https://unstats.un.org/unsd/demographic/sources/census/wphc/"
          "North_Korea/2008_North_Korea_Census.pdf")

# ---------------------------------------------------------------------------
# The geography. The left-hand side of every table below is the report's own
# label, the right-hand side is the name the boundary file draws, and nothing
# is matched on a resemblance -- each of the ten first-level areas closes
# exactly against its county list, which is what makes the four re-districtings
# arithmetic rather than a guess.
# ---------------------------------------------------------------------------

# Report label -> shape name, for the first level.
PROVINCES = {
    "Ryanggang": "Ryanggang",
    "North Hamgyong": "North Hamgyong",
    "South Hamgyong": "South Hamgyong",
    "Kangwon": "Kangwon",
    "Jagang": "Jagang",
    "North Phyongan": "North Pyongan",
    "South Phyongan": "South Pyongan",
    "North Hwanghae": "North Hwanghae",
    "South Hwanghae": "South Hwanghae",
    "Pyongyang": "Pyongyang",
}

# Shape names the report spells differently, first level and second. The
# boundary file's spelling is the name; the report's is an alias, so a reader
# who goes looking for the figure in the report finds the row it came from.
PROVINCE_ALIASES = {
    "North Pyongan": ["North Phyongan"],
    "South Pyongan": ["South Phyongan"],
}

# Report label (within a province) -> shape name. Only the differences: a
# label absent from this table is the shape's name already. Each of these was
# settled by the province's two lists closing on each other, every other name
# matching outright -- not by how alike two words look, which is why the two
# that are arguably the report's own slips (a Cholwon in North Phyongan where
# the county is Cholsan, a second Ryongchon in South Hwanghae where the county
# is Ryongyon) are declared here and not corrected anywhere.
COUNTY_RENAMED = {
    "North Phyongan": {"Cholwon": "Cholsan"},
    "South Phyongan": {"Phyongsong City": "Pyongsong City",
                       "Phyongwon": "Pyongwon",
                       "Nampho City": "Nampo City"},
    "South Hwanghae": {"Jaeryong": "Jaerong",
                       "Phyoksong": "Pyoksong",
                       "Ryongchon": "Ryongyon"},
    "South Hamgyong": {"kowon": "Kowon"},
}

# Report rows that are one shape in the boundary file. The report prints the
# parts and says so itself for the first two; the third is the capital, whose
# districts the boundary file draws as one city beside Unjong and Kangdong.
MERGED = {
    ("North Hamgyong", "Chongjin City"): [
        "Sinam Dist.*", "Chongam Dist.*", "Phohang Dist.*", "Sunam Dist.*",
        "Songphyong Dist.*", "Ranam Dist.*", "Puyun Dist.*"],
    ("South Hamgyong", "Hamhung City"): [
        "Songchongang Dist.*", "Tonghungsan Dist.*", "Hoesang Dist.*",
        "Sapho Dist.*", "Hungdok Dist.*", "Haean Dist.*", "Hungnam"],
    ("Pyongyang", "Pyongyang"): [
        "Central Dist.", "Mangyongdae Dist.", "Sonkyo Dist.",
        "Phyongchon Dist.", "Tongdaewon Dist.", "Ryongsong Dist.",
        "Taesong Dist.", "Moranbong Dist.", "Sosong Dist.",
        "Pothonggang Dist.", "Taedonggang Dist.", "Sadong Dist.",
        "Hyongjesan Dist.", "Sunan Dist.", "Samsok Dist.", "Sungho Dist.",
        "Ryokpho Dist.", "Rakrang Dist."],
}

# Counties the report files under one first-level area and the boundary file
# draws under another: {(report province, report label): shape province}.
MOVED = {
    ("South Phyongan", "Nampho City"): "Nampo",
    ("South Phyongan", "Onchon"): "Nampo",
    ("South Phyongan", "Ryonggang"): "Nampo",
    ("South Phyongan", "Taean"): "Nampo",
    ("South Phyongan", "Kangso"): "Nampo",
    ("South Phyongan", "Chollima"): "Nampo",
    ("Pyongyang", "Kangnam"): "North Hwanghae",
    ("Pyongyang", "Junghwa"): "North Hwanghae",
    ("Pyongyang", "Sangwon"): "North Hwanghae",
}

# What the boundary file draws, and therefore what must come out: 11 shapes at
# the first level and 179 at the second. Written out rather than counted, so a
# county the report drops or this reader mis-files is a refusal naming it.
SHAPE_COUNTIES: dict[str, list[str]] = {
    "Jagang": [
        "Chosan", "Huichon City", "Hwaphyong", "Janggang", "Jasong",
        "Jonchon", "Junggang", "Kanggye City", "Kophung", "Manpho City",
        "Rangrim", "Ryongrim", "Sijung", "Songgan", "Songwon", "Tongsin",
        "Usi", "Wiwon"],
    "Kangwon": [
        "Anbyon", "Changdo", "Cholwon", "Chonnae", "Hoeyang", "Ichon",
        "Kimhwa", "Kosan", "Kosong", "Kumgang", "Munchon City", "Phangyo",
        "Phyonggang", "Popdong", "Sepho", "Thongchon", "Wonsan City"],
    "Nampo": [
        "Chollima", "Kangso", "Nampo City", "Onchon", "Ryonggang", "Taean"],
    "North Hamgyong": [
        "Chongjin City", "Hoeryong City", "Hwadae", "Kilju", "Kim Chaek City",
        "Kyonghung", "Kyongsong", "Kyongwon", "Musan", "Myongchon",
        "Myonggan", "Onsong", "Orang", "Puryong", "Rason City", "Yonsa"],
    "North Hwanghae": [
        "Hwangju", "Jangphung", "Junghwa", "Kaesong City", "Kangnam",
        "Koksan", "Kumchon", "Phyongsan", "Pongsan", "Rinsan", "Sangwon",
        "Sariwon City", "Sinkye", "Sinphyong", "Sohung", "Songrim City",
        "Suan", "Thosan", "Unpha", "Yonsan", "Yonthan"],
    "North Pyongan": [
        "Changsong", "Cholsan", "Chonma", "Hyangsan", "Jongju City", "Kujang",
        "Kusong City", "Kwaksan", "Nyongbyon", "Pakchon", "Phihyon",
        "Pyokdong", "Ryongchon", "Sakju", "Sindo", "Sinuiju City", "Sonchon",
        "Taegwan", "Thaechon", "Tongchang", "Tongrim", "Uiju", "Unjon",
        "Unsan", "Yomju"],
    "Pyongyang": ["Kangdong", "Pyongyang", "Unjong Dist."],
    "Ryanggang": [
        "Hyesan City", "Kabsan", "Kim Hyong Gwon", "Kim Hyong Jik",
        "Kim Jong Suk", "Paekam", "Phungso", "Pochon", "Samjiyon", "Samsu",
        "Taehongdan", "Unhung"],
    "South Hamgyong": [
        "Hamhung City", "Hamju", "Hochon", "Hongwon", "Jangjin", "Jongphyong",
        "Kowon", "Kumho", "Kumya", "Pujon", "Pukchong", "Rakwon", "Riwon",
        "Sinhung", "Sinpho City", "Sudong", "Tanchon City", "Toksong",
        "Yodok", "Yonggwang"],
    "South Hwanghae": [
        "Anak", "Chongdan", "Haeju City", "Jaerong", "Jangyon", "Kangryong",
        "Kwail", "Ongjin", "Paechon", "Pongchon", "Pyoksong", "Ryongyon",
        "Samchon", "Sinchon", "Sinwon", "Songhwa", "Thaethan", "Unchon",
        "Unryul", "Yonan"],
    "South Pyongan": [
        "Anju City", "Chongnam", "Hoechang", "Jungsan", "Kaechon City",
        "Maengsan", "Mundok", "Nyongwon", "Pukchang", "Pyongsong City",
        "Pyongwon", "Sinyang", "Songchon", "Sukchon", "Sunchon City",
        "Taedong", "Taehung", "Tokchon City", "Tukjang", "Unsan", "Yangdok"],
}

# ---------------------------------------------------------------------------
# Notes. The method is in docs/SOURCES.md; a row says what its figure is and
# where it came from, and then only what is peculiar to that row.
# ---------------------------------------------------------------------------

WORDS = {3: "three", 6: "six", 7: "seven", 18: "eighteen"}

POPULATION_NOTE = (
    "The 2008 census count, Table 2 of the Central Bureau of Statistics' "
    "National Report, which counts private households and institutional "
    f"living quarters and comes to {CIVILIAN_TOTAL:,} for the country. The "
    f"report's Table 1 counts {CENSUS_TOTAL:,}; the {IN_CAMPS:,} between them "
    "are the people living in military camps, whom no table of the report "
    "places in a province.")

SEX_RATIO_NOTE = (
    "Females per 1,000 males, from the Male and Female columns of the same "
    "Table 2 row, which add to the total printed beside them. Like the head "
    "count beside it, it leaves out the people in military camps, who are 94% "
    "men by the difference between the report's first two tables, so a "
    "ratio here runs above the census's own.")

MERGED_NOTE = (
    " This shape is {parts} rows of the table added together -- {names} -- "
    "which the report prints apart and the boundary file draws as one.")

MOVED_NOTE = (
    " The report files this county under {was}, which is where it was in "
    "2008; the boundary file draws it in {now}.")

NAMPO_NOTE = (
    " Nampo was not a first-level area in 2008: this is the sum of the six "
    "South Phyongan rows the boundary file draws inside it (Nampho City, "
    "Onchon, Ryonggang, Taean, Kangso and Chollima).")

SPLIT_PARENT_NOTE = (
    " This is the province's printed total less the {n} counties the "
    "boundary file draws outside it ({names}), and it equals the sum of the "
    "counties left.")

GAINED_PARENT_NOTE = (
    " This is the province's printed total plus {names}, which the report "
    "files under Pyongyang and the boundary file draws here.")

PYONGYANG_NOTE = (
    " This shape is the city proper: the report's nineteen districts less "
    "Unjong, which the boundary file draws as a unit of its own.")

REPORT_SPELLS_IT = (
    " The report writes the name {label!r}; the spelling here is the "
    "boundary file's, and the two lists close on each other with every "
    "other county in the province matching outright.")


@dataclass
class County:
    """One shape of the boundary file, and what Table 2 gives it."""

    figures: list[int]
    note: str
    aliases: list[str] = dc_field(default_factory=list)


# ---------------------------------------------------------------------------
# Reading Table 2.
# ---------------------------------------------------------------------------

CAPTION = "Population by Sex and by Urban-Rural"
NEXT_TABLE = "Number of  Localities and Population"

# A label is everything before the row's first digit; no unit in this table
# has a digit in its name. The figures are written with a space for the
# thousands separator, so "192 680   91 420" is two numbers and the text says
# nowhere where one ends -- see split_row.
NUMBERS = re.compile(r"[\d-]")
# The column header is three short lines, and one of them is the word
# "County" alone. Matched loosely it would swallow any row whose name carried
# that word, so the stub header is matched whole and only the phrases that
# cannot be part of a name are matched anywhere in the line.
HEADERS_WHOLE = {"Province and", "City/District/", "County"}
HEADERS_WITHIN = ("All Areas", "Both Sexes", "Census of Population",
                  "Table 2", "Note:")


def table_pages(pages: list[str]) -> list[int]:
    """The pages carrying Table 2, by the caption the report repeats on each."""
    # The caption alone is not enough: the List of Tables prints it too. The
    # column header over the nine figures appears on every page of the table
    # itself and nowhere else.
    found = [n for n, page in enumerate(pages, 1)
             if CAPTION in page and "All Areas" in page
             and NEXT_TABLE not in page]
    if not found:
        raise SystemExit(
            "northkorea: no page of the report carries Table 2's caption "
            f"{CAPTION!r}; the file at {REPORT} is not the National Report, "
            "or its text did not extract")
    return found


def whole_population(pages: list[str]) -> tuple[int, int]:
    """Table 1's All Ages row: the whole population, and its males.

    What every row here says about military camps is arithmetic between the
    report's first two tables, so it is read rather than asserted. Table 1 is
    the only page of the 278 that carries the figure.
    """
    found = [n for n, page in enumerate(pages, 1) if TABLE_ONE in page
             and "All Ages" in page]
    if len(found) != 1:
        raise SystemExit(
            f"northkorea: {len(found)} pages of the report carry Table 1's "
            "All Ages row, and exactly one should")
    line = next((ln for ln in pages[found[0] - 1].splitlines()
                 if ln.strip().startswith("All Ages")), None)
    if line is None:
        raise SystemExit("northkorea: Table 1 has no All Ages row")
    # Three figures, then the percentages, which carry a decimal point and so
    # cannot be mistaken for another group of thousands. The row saying
    # Both Sexes = Male + Female is the check on having read them right.
    tokens, numbers = line.split("All Ages", 1)[1].split(), []
    while tokens and len(numbers) < 3:
        digits, tokens = tokens[0], tokens[1:]
        if not digits.isdigit():
            raise SystemExit(f"northkorea: Table 1's All Ages row begins "
                             f"{line.strip()[:60]!r}, which is not figures")
        while tokens and tokens[0].isdigit() and len(tokens[0]) == 3:
            digits, tokens = digits + tokens[0], tokens[1:]
        numbers.append(int(digits))
    people, males, females = numbers
    if people != males + females:
        raise SystemExit(
            f"northkorea: Table 1's All Ages row reads {people:,} = "
            f"{males:,} + {females:,}, which does not add up")
    log(f"  Table 1: the whole population is {people:,}, "
        f"{people - CIVILIAN_TOTAL:,} above Table 2's {CIVILIAN_TOTAL:,}")
    return people, males


def split_row(tokens: list[str], where: str) -> list[int]:
    """Nine figures out of the tokens of one row, or a refusal.

    Each figure is a leading group of one to three digits followed by groups
    of exactly three, or a dash for zero, and which grouping is meant is not
    in the text. The publisher's own arithmetic decides it: males and females
    add to both sexes in each of the three blocks, and urban and rural add to
    all areas in each of the three columns. Six equations over nine figures
    leave one reading standing, and a row where they leave none or leave two
    is refused with the row in the log rather than read the likelier way.
    """
    def parses(start: int, want: int) -> Iterator[list[int]]:
        if want == 0:
            if start == len(tokens):
                yield []
            return
        if start >= len(tokens):
            return
        head = tokens[start]
        if head == "-":
            for rest in parses(start + 1, want - 1):
                yield [0, *rest]
            return
        if not head.isdigit() or len(head) > 3:
            return
        digits = head
        end = start + 1
        while True:
            for rest in parses(end, want - 1):
                yield [int(digits), *rest]
            if end < len(tokens) and tokens[end].isdigit() and len(tokens[end]) == 3:
                digits += tokens[end]
                end += 1
            else:
                return

    def sound(n: list[int]) -> bool:
        return (n[0] == n[1] + n[2] and n[3] == n[4] + n[5]
                and n[6] == n[7] + n[8] and n[0] == n[3] + n[6]
                and n[1] == n[4] + n[7] and n[2] == n[5] + n[8])

    readings = [n for n in parses(0, 9) if sound(n)]
    if len(readings) != 1:
        raise SystemExit(
            f"northkorea: {where}: {len(readings)} readings of "
            f"{' '.join(tokens)!r} satisfy the row's own arithmetic; a row of "
            "Table 2 must have exactly one")
    return readings[0]


def rows(pages: list[str], numbers: list[int]) -> list[tuple[str, list[int]]]:
    """(label, nine figures) for every row of Table 2, in the report's order."""
    out: list[tuple[str, list[int]]] = []
    for page in numbers:
        pending = ""
        for line in pages[page - 1].splitlines():
            line = line.rstrip()
            # The footnotes matter -- they are what says the district rows
            # belong to Chongjin and to Hamhung -- but they are prose, and
            # left in the pending label they would swallow the name of the
            # province printed on the next line.
            if (not line.strip() or line.strip().startswith("*")
                    or line.strip() in HEADERS_WHOLE
                    or any(h in line for h in HEADERS_WITHIN)):
                pending = ""
                continue
            hit = NUMBERS.search(line)
            if hit is None:
                # A label on a line of its own: the table wraps the long ones
                # ("Songchongang" / "Dist.*") and prints a province's name
                # above its "Total" row.
                pending = f"{pending} {line.strip()}".strip()
                continue
            label = f"{pending} {line[:hit.start()].strip()}".strip()
            pending = ""
            if not label:
                continue          # the printed page number, alone on its line
            figures = line[hit.start():].split()
            if len(figures) < 9:
                continue
            out.append((label, split_row(figures, f"page {page}, {label!r}")))
    return out


def counties(read: list[tuple[str, list[int]]]) -> dict[str, dict[str, list[int]]]:
    """The report's rows as {first-level area: {county: figures}}, checked.

    The report's shape is its own check: a first-level area's name stands on a
    line of its own above a "Total" row, its counties follow, and the next
    name ends it. So the totals are never added up here -- they are read, and
    the counties are required to reach them.
    """
    national: list[int] | None = None
    out: dict[str, dict[str, list[int]]] = {}
    printed: dict[str, list[int]] = {}
    current: str | None = None
    for label, figures in read:
        if label == "DPR Korea":
            national = figures
            continue
        if label.endswith("Total"):
            current = label[: -len("Total")].strip() or current
            if current not in PROVINCES:
                raise SystemExit(
                    f"northkorea: Table 2 has a first-level area "
                    f"{current!r} this reader does not know")
            printed[current] = figures
            out[current] = {}
            continue
        if current is None:
            raise SystemExit(f"northkorea: the row {label!r} comes before any "
                             "first-level area in Table 2")
        if label in out[current]:
            raise SystemExit(f"northkorea: {current} lists {label!r} twice")
        out[current][label] = figures

    if national is None:
        raise SystemExit("northkorea: Table 2 has no DPR Korea row")
    if national[0] != CIVILIAN_TOTAL:
        raise SystemExit(
            f"northkorea: Table 2's DPR Korea row counts {national[0]:,} "
            f"where the report published {CIVILIAN_TOTAL:,}")
    missing = set(PROVINCES) - set(out)
    if missing:
        raise SystemExit(f"northkorea: Table 2 is missing {sorted(missing)}")

    for province, rows_ in out.items():
        summed = [sum(r[i] for r in rows_.values()) for i in range(9)]
        if summed != printed[province]:
            raise SystemExit(
                f"northkorea: {province}'s {len(rows_)} county rows come to "
                f"{summed[0]:,} against the {printed[province][0]:,} printed "
                "on its own Total row")
    both = sum(printed[p][0] for p in out)
    if both != national[0]:
        raise SystemExit(
            f"northkorea: the ten first-level totals come to {both:,} "
            f"against the DPR Korea row's {national[0]:,}")
    log(f"  Table 2: {len(out)} first-level areas, "
        f"{sum(len(v) for v in out.values())} city/district/county rows; "
        f"every area equals its own rows and the ten equal the "
        f"{national[0]:,} printed for DPR Korea")
    return out


# ---------------------------------------------------------------------------
# From the report's geography to the boundary file's.
# ---------------------------------------------------------------------------

def regroup(table: dict[str, dict[str, list[int]]],
            ) -> dict[str, dict[str, County]]:
    """{shape province: {shape county: what is written for it}}."""
    out: dict[str, dict[str, County]] = {shape: {} for shape in SHAPE_COUNTIES}
    for province, rows_ in table.items():
        renamed = COUNTY_RENAMED.get(province, {})
        merged = {part: (shape, parts)
                  for (prov, shape), parts in MERGED.items() if prov == province
                  for part in parts}
        pending: dict[str, list[list[int]]] = {}
        for label, figures in rows_.items():
            if label in merged:
                shape, _parts = merged[label]
                pending.setdefault(shape, []).append(figures)
                continue
            name = renamed.get(label, label)
            where = MOVED.get((province, label), PROVINCES[province])
            note = POPULATION_NOTE
            if (province, label) in MOVED:
                note += MOVED_NOTE.format(was=province, now=where)
            out[where][name] = County(figures, note,
                                      [label] if label != name else [])
        for (prov, shape), parts in MERGED.items():
            if prov != province:
                continue
            got = pending.get(shape, [])
            if len(got) != len(parts):
                raise SystemExit(
                    f"northkorea: {shape} wanted {len(parts)} rows of "
                    f"{province} and Table 2 gave {len(got)}: the report "
                    "renamed or dropped one of "
                    f"{parts}")
            figures = [sum(r[i] for r in got) for i in range(9)]
            note = POPULATION_NOTE + (
                PYONGYANG_NOTE if shape == "Pyongyang" else
                MERGED_NOTE.format(parts=WORDS[len(parts)],
                                   names=", ".join(p.rstrip("*")
                                                   for p in parts)))
            out[PROVINCES[province]][shape] = County(figures, note, [])

    for shape, wanted in SHAPE_COUNTIES.items():
        got = sorted(out[shape])
        if got != sorted(wanted):
            raise SystemExit(
                f"northkorea: {shape} came out as {got}, and the boundary "
                f"file draws {sorted(wanted)}")
    log(f"  regrouped to {len(out)} shapes and "
        f"{sum(len(v) for v in out.values())} counties: Nampo taken out of "
        "South Phyongan, Kangnam/Junghwa/Sangwon moved to North Hwanghae, "
        "Chongjin and Hamhung added up, Pyongyang left as the city")
    return out


def province_note(shape: str) -> str:
    if shape == "Nampo":
        return POPULATION_NOTE + NAMPO_NOTE
    if shape == "South Pyongan":
        return POPULATION_NOTE + SPLIT_PARENT_NOTE.format(
            n="six", names="Nampho City, Onchon, Ryonggang, Taean, Kangso and "
                       "Chollima, which are Nampo")
    if shape == "Pyongyang":
        return POPULATION_NOTE + SPLIT_PARENT_NOTE.format(
            n="three", names="Kangnam, Junghwa and Sangwon, which are North "
                       "Hwanghae")
    if shape == "North Hwanghae":
        return POPULATION_NOTE + GAINED_PARENT_NOTE.format(
            names="Kangnam, Junghwa and Sangwon")
    return POPULATION_NOTE


def sex_ratio(figures: list[int], where: str) -> dict[str, Any]:
    """Females per 1,000 males, the row's own two columns."""
    total, male, female = figures[0], figures[1], figures[2]
    if male + female != total:            # split_row cannot let this through
        raise SystemExit(f"northkorea: {where}: {male:,} + {female:,} is not "
                         f"the {total:,} printed on the row")
    if not male:
        return gap(NOT_AVAILABLE,
                   "Table 2 counts no males in this row, so there is nothing "
                   "to express the females per thousand of.")
    return measure(round(1000.0 * female / male),
                   unit="females_per_1000_males", year=YEAR, source=SOURCE)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def build(shaped: dict[str, dict[str, County]]) -> list[dict[str, Any]]:
    fields = ("religion", "ethnicity", "language")
    declared = {f: collection_gap("PRK", f) for f in fields}
    for field, marker in declared.items():
        if marker is None:
            raise SystemExit(
                f"northkorea: NOT_COLLECTED_POLICY has no {field} entry for "
                "PRK; this adapter writes the country's own declaration and "
                "will not invent one")

    out: list[dict[str, Any]] = []
    for shape in sorted(shaped):
        rows_ = shaped[shape]
        figures = [sum(v.figures[i] for v in rows_.values()) for i in range(9)]
        ratio = sex_ratio(figures, shape)
        out.append(record(
            f"PRK-{slug(shape)}", shape, level="admin1", parent="PRK",
            country="PRK", aliases=PROVINCE_ALIASES.get(shape, []),
            population=measure(figures[0], year=YEAR, source=SOURCE,
                               unit="persons"),
            population_note=province_note(shape),
            sex_ratio=ratio, sex_ratio_note=SEX_RATIO_NOTE,
            sources=cite(), **declared))
        for name in sorted(rows_):
            county = rows_[name]
            note = county.note
            if county.aliases:
                note += REPORT_SPELLS_IT.format(label=county.aliases[0])
            out.append(record(
                f"PRK-{slug(shape)}-{slug(name)}", name, level="admin2",
                parent="PRK", parent_name=shape,
                parent_aliases=PROVINCE_ALIASES.get(shape, []),
                country="PRK", aliases=county.aliases,
                population=measure(county.figures[0], year=YEAR,
                                   source=SOURCE, unit="persons"),
                population_note=note,
                sex_ratio=sex_ratio(county.figures, f"{shape}/{name}"),
                sex_ratio_note=SEX_RATIO_NOTE,
                sources=cite(), **declared))
    return out


def cite() -> list[dict[str, Any]]:
    return [{"field": field, "name": SOURCE, "url": REPORT, "license": LICENCE}
            for field in ("population", "sex_ratio")]


def check(records: list[dict[str, Any]]) -> None:
    """The shapes against the boundary file's counts, and against the report."""
    first = [r for r in records if r["level"] == "admin1"]
    second = [r for r in records if r["level"] == "admin2"]
    if len(first) != 11 or len(second) != 179:
        raise SystemExit(
            f"northkorea: {len(first)} first-level and {len(second)} "
            "second-level records; the boundary file draws 11 and 179")
    by_parent: dict[str, int] = {}
    for row in second:
        by_parent[row["parent_name"]] = (by_parent.get(row["parent_name"], 0)
                                         + row["population"]["value"])
    for row in first:
        if by_parent.get(row["name"]) != row["population"]["value"]:
            raise SystemExit(
                f"northkorea: {row['name']} is written as "
                f"{row['population']['value']:,} and its counties come to "
                f"{by_parent.get(row['name'], 0):,}")
    total = sum(r["population"]["value"] for r in first)
    if total != CIVILIAN_TOTAL:
        raise SystemExit(f"northkorea: the 11 shapes come to {total:,} "
                         f"against Table 2's {CIVILIAN_TOTAL:,}")
    log(f"  check: 11 shapes and 179 counties, each shape the sum of its "
        f"own, all of them {total:,} -- Table 2's own DPR Korea row, and "
        f"{IN_CAMPS:,} short of the {CENSUS_TOTAL:,} Table 1 counts")


def page_texts(path: Path) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    log(f"  {len(reader.pages)} pages")
    return [(page.extract_text() or "") for page in reader.pages]


def run() -> int:
    log(f"northkorea: {SOURCE}")
    pdf = download(REPORT, RAW / "northkorea" / "dprk-2008-census-report.pdf")
    pages = page_texts(pdf)
    numbers = table_pages(pages)
    log(f"  Table 2 on pages {numbers}")
    people, males = whole_population(pages)
    if people != CENSUS_TOTAL:
        raise SystemExit(f"northkorea: Table 1 counts {people:,} where the "
                         f"census published {CENSUS_TOTAL:,}")
    table = counties(rows(pages, numbers))
    civilian_males = sum(f[1] for area in table.values()
                         for f in area.values())
    log(f"  the {IN_CAMPS:,} Table 2 does not place are "
        f"{males - civilian_males:,} men and "
        f"{IN_CAMPS - (males - civilian_males):,} women, which is why a sex "
        "ratio here runs above the census's own")
    records = build(regroup(table))
    check(records)
    for row in records:
        if row["level"] == "admin1":
            log(f"    {row['name']:16} {row['population']['value']:>10,}  "
                f"{len([r for r in records if r.get('parent_name') == row['name']])} counties")
    write_json(PROCESSED / OUT, records)
    log(f"  wrote {len(records)} records to {OUT}")
    return 0


def probe() -> int:
    """What the report says about the three fields. Writes nothing."""
    pdf = download(REPORT, RAW / "northkorea" / "dprk-2008-census-report.pdf")
    pages = page_texts(pdf)
    terms = ("religio", "ethnic", "mother tongue", "language", "church",
             "buddhis", "christian", "chondo", "confucian", "faith",
             "nationality")
    for term in terms:
        hits = [n for n, page in enumerate(pages, 1) if term in page.lower()]
        log(f"  {term!r}: {len(hits)} of {len(pages)} pages {hits[:12]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true",
                    help="count the pages naming each of the three fields, "
                         "and write nothing")
    args = ap.parse_args()
    return probe() if args.probe else run()


if __name__ == "__main__":
    raise SystemExit(main())
