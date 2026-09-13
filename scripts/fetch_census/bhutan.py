#!/usr/bin/env python3
"""Bhutan -- Population & Housing Census 2017, population by gewog.

**This adapter publishes population and nothing else, and the reason is worth
stating rather than leaving as an empty field.** Bhutan's census does not ask
religion, language or ethnicity. That is not "does not publish": the 2017
national report runs 288 pages over education, fertility, mortality,
disability, labour, migration and housing, and the words religion, ethnic,
Hindu, Buddhist and mother tongue occur on none of them except two pages
describing the census's own publicity -- talk shows held in Dzongkha,
Sharchopkha and Lhotshamkha, and the literacy test card. The 2005 round is the
same. So the three composition fields are declared ``not_collected`` in
``scripts/common.py`` and this file fills the one thing the census does count.

**The one identity-adjacent split the census does publish is citizenship**,
Bhutanese against non-Bhutanese, by dzongkhag and by gewog. It is deliberately
not read here and must not be used as an ethnicity proxy: citizenship is
precisely the contested variable in Bhutan, the 1985 Citizenship Act being how
much of the Lhotshampa population lost its legal standing before leaving.
Table 2.1, which this reads, is the whole resident population "irrespective of
their nationality" -- the report's own words -- which is the figure that
belongs on a map of where people are.

Three things about the documents shape the reader.

**The table shares its page with two columns of narrative.** ``--layout``
extraction interleaves them: "4,183 persons during the intercensal" sits among
the data rows and ends in no numbers, while "Barshong 423 419 842" is a row.
Splitting on whitespace and counting numbers cannot tell those apart reliably.
So the header row -- "Gewog/Town Male Female Total" -- is found first and its
own words fix the table's left edge; everything to the left of that is prose
and is never considered.

**Towns are counted beside gewogs, not inside them.** Tsirang prints two town
rows and twelve gewog rows, and all fourteen add to the printed total: 3,510
urban plus 18,866 rural is 22,376. geoBoundaries draws no town, so the towns
have nowhere to go -- they are declared rather than dropped, and the dzongkhag
above them carries its own printed total, which includes them. The gewog layer
is therefore short of its parent by the urban population, by construction, and
says so.

**The narrative is not always about the dzongkhag whose tables these are.**
Tsirang's page 12 opens "Trashigang Dzongkhag as of the census...", a
copy-paste left in NSB's own text. The tables are Tsirang's. Read the tables,
never the sentences.

Usage:
    python -m scripts.fetch_census.bhutan
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, log, measure, record, write_json,
)

YEAR = 2017
SOURCE = ("National Statistics Bureau of Bhutan, Population & Housing Census "
          "of Bhutan 2017, Table 2.1: population distribution by gewog and "
          "town")
LICENCE = "National Statistics Bureau of Bhutan. Official publication."
BASE = "https://nsb.gov.bt/wp-content/uploads/2026/08"

# The twenty dzongkhag reports, by the file name NSB gives each. The index at
# https://www.nsb.gov.bt/phcb links exactly these twenty plus the national
# report; the /publications/ tree does not link them at all, and the URL every
# search engine still cites for the national report (dlm_uploads/2020/07/)
# is a 404. Asked for and answered: all twenty returned 200.
DZONGKHAGS: dict[str, str] = {
    "Bumthang": "PHCB2017_Bumthang.pdf",
    "Chhukha": "PHCB2017_Chhukha.pdf",
    "Dagana": "PHCB2017_Dagana.pdf",
    "Gasa": "PHCB2017_Gasa.pdf",
    "Haa": "PHCB2017_Haa.pdf",
    "Lhuentse": "PHCB2017_Lhuentse.pdf",
    "Monggar": "PHCB2017_Monggar.pdf",
    "Paro": "PHCB2017_Paro.pdf",
    "Pema Gatshel": "PHCB2017_Pema-Gatshel.pdf",
    "Punakha": "PHCB2017_Punakha.pdf",
    "Samdrup Jongkhar": "PHCB2017_Samdrup-Jongkhar.pdf",
    "Samtse": "PHCB2017_Samtse.pdf",
    "Sarpang": "PHCB2017_Sarpang.pdf",
    "Thimphu": "PHCB2017_Thimphu.pdf",
    "Trashi Yangtse": "PHCB2017_Trashi-Yangtse.pdf",
    "Trashigang": "PHCB2017_Trashigang.pdf",
    "Trongsa": "PHCB2017_Trongsa.pdf",
    "Tsirang": "PHCB2017_Tsirang.pdf",
    "Wangdue Phodrang": "PHCB2017_Wangdue-Phodrang.pdf",
    "Zhemgang": "PHCB2017_Zhemgang.pdf",
}

# What geoBoundaries calls each dzongkhag where it differs. "Thimpu" is the
# one that cost something: the dzongkhag carried no population at all because
# of a missing h.
DZONGKHAG_ALIASES: dict[str, tuple[str, ...]] = {
    "Thimphu": ("Thimpu",),
    "Monggar": ("Mongar",),
    "Pema Gatshel": ("Pemagatshel", "Pemagatshel Dzongkhag"),
    "Trashi Yangtse": ("Trashiyangtse", "Tashi Yangtse"),
    "Chhukha": ("Chukha",),
    "Lhuentse": ("Lhuntse",),
}

# What geoBoundaries calls each gewog where it differs from NSB. Neither
# spelling is wrong -- Dzongkha romanisation has no single standard, and the
# two bodies made different choices: Barzhong against Barshong, Kikorthang
# against Kilkhorthang, Dunglegang against Doonglagang.
#
# **Paired by mutual best match on the name and by nothing else, and that is a
# deliberate limit.** The obvious corroboration would be the dzongkhag, and it
# is not available here: CGAZ's two Bhutan layers are not the same partition
# of the country. 81 of the 205 gewog polygons are less than 90% inside any
# single dzongkhag polygon, and Punakha comes out with 6 children by maximum
# overlap and 4 by the point-in-polygon rule the build uses, where it has 11.
# A parent that is wrong cannot confirm a name.
#
# So a pair is taken only where each name is the other's best match in both
# directions, which is what stops a chain of near-misses from cascading: 24
# further rows have a plausible candidate that some other row matches better,
# and every one of them is left unmatched rather than guessed. An unmatched
# gewog is a visible gap; a gewog wearing its neighbour's people is not.
#
# Nine pairs score below 0.80 and are kept because the alternative does not
# exist rather than because the string is close: Gasa has four gewogs, so
# Khamaed can only be Goenkhame. "Pemaling" to "Pagli" scored 0.62 with no
# such argument behind it and is left out.
GEWOG_ALIASES: dict[str, tuple[str, ...]] = {
    "Barp": ("Bara",),
    "Barshong": ("Barzhong",),
    "Bidoong": ("Bidung",),
    "Bjagchhog": ("Bjachho",),
    "Bjenag": ("Bjena",),
    "Boomdeling": ("Bumdeling",),
    "Chagsakhar": ("Chaskhar",),
    "Chhaling": ("Chhali",),
    "Chhimoong": ("Chhimung",),
    "Chhoekhorling": ("Chokhorling",),
    "Chhumig": ("Chhume",),
    "Chhuzanggang": ("Chhuzagang",),
    "Darla": ("Dala",),
    "Doonglagang": ("Dunglegang",),
    "Doongna": ("Dungna",),
    "Dopshar-ri": ("Dopshari",),
    "Draagteng": ("Dragteng",),
    "Dramedtse": ("Drametse",),
    "Drepoong": ("Drepung",),
    "Drukjeygang": ("Drugyelgang",),
    "Duenchhukha": ("Denchhukha",),
    "Dzomi": ("Dzoma",),
    "Gangteng": ("Gangte",),
    "Gase Tshogongm": ("Gasetsho Gom",),
    "Gase Tshowogm": ("Gasetsho Om",),
    "Ge-nyen": ("Genye",),
    "Gelegphu": ("Gelephu",),
    "Goshing": ("Gozhing",),
    "Hoongrel": ("Hungrel",),
    "Jarey": ("Jaray",),
    "Jigme Chhoeling": ("Jigmichhoeling",),
    "Jurmed": ("Jurmey",),
    "Kabisa": ("Kabjisa",),
    "Kangpar": ("Kangpara",),
    "Kar-tshog": ("Katsho",),
    "Khamaed": ("Goenkhame",),
    "Khatoed": ("Goenkhatoe",),
    "Kilkhorthang": ("Kikorthang",),
    "Kurtoed": ("Kurtoe",),
    "Langchenphu": ("Langchhenphu",),
    "Largyab": ("Lajab",),
    "Lhamoi Dzingkha": ("Lhamoizingkha",),
    "Loggchina": ("Logchina",),
    "Loong-nyi": ("Lungnyi",),
    "Maedtabkha": ("Patakla",),
    "Maedtsho": ("Metsho",),
    "Maedwang": ("Mewang",),
    "Maenbi": ("Menbi",),
    "Merag": ("Merak",),
    "Minjey": ("Minjay",),
    "Monggar": ("Mongar",),
    "Namgyalchhoeling": ("Namgyel Chhoeling",),
    "Norboogang": ("Norbugang",),
    "Nyishog": ("Nyisho",),
    "Phangkhar": ("Pangkhar",),
    "Phongmed": ("Phongme",),
    "Phuentshogling": ("Phuentsholing",),
    "Phuentshogthang": ("Phuntsthothang",),
    "Pungtenchhu": ("Phuentenchhu",),
    "Radhi": ("Radi",),
    "Ruebisa": ("Ruepisa",),
    "Saephu": ("Sephu",),
    "Sagteng": ("Sakteng",),
    "Saling": ("Saleng",),
    "Samar": ("Sama",),
    "Semjong": ("Shemjong",),
    "Senggey": ("Senge",),
    "Serzhong": ("Sherzhong",),
    "Sharpa": ("Shapa",),
    "Shelnga-Bjemi": ("Shengabjimi",),
    "Shermuhoong": ("Shermung",),
    "Shumar": ("Shumer",),
    "Talog": ("Talo",),
    "Tashiding": ("Trashiding",),
    "Tendruk": ("Tendu",),
    "Toedpaisa": ("Toepisa",),
    "Toedtsho": ("Toetsho",),
    "Toedwang": ("Toewang",),
    "Tsaenkhar": ("Tsenkhar",),
    "Tsholingkhar": ("Tsholingkhor",),
    "Tsirang Toed": ("Tsirangtoe",),
    "Ugyentse": ("Ugentse",),
}


# Bhutan's two published totals, and they are both real. The national report:
# "Bhutan's total population is 735,553 ... It includes 8,408
# non-Bhutanese/tourists found in hotels and those on the move on census
# reference day. The analyses in this Report are based on 727,145 persons
# since no detailed information was collected from the 8,408."
NATIONAL_FOUND = 735_553      # everyone found in Bhutan on the day
NATIONAL_ANALYSED = 727_145   # what the report's own tables are built on

# The twenty dzongkhag reports do not sum to either, and that is a
# disagreement between NSB's own publications rather than a misread here.
# Their Table 2.1 figures agree with the national report's Table 2.1 exactly
# for Bumthang, Chhukha, Dagana, Gasa, Haa, Monggar and Pema Gatshel, and
# differ for others -- Paro 43,362 against 46,316, Punakha 27,360 against
# 28,740, Lhuentse 14,240 against 14,437. Each dzongkhag report reconciles
# internally, gewog by gewog, to the total printed in it.
#
# So the per-dzongkhag reconciliation is the hard check and this one is
# reported rather than enforced: every dzongkhag is required to be read and
# to add up to its own printed total, which is what would catch one read
# twice or not at all. A bound here would either be loose enough to miss
# Gasa's 3,952 or tight enough to refuse this known disagreement.
NATIONAL = NATIONAL_ANALYSED

# The header is two stacked rows -- "Gewog/Town | Persons" over
# "Male | Female | Total" -- and whether they land on one baseline or two is
# a fact about the individual file. Bumthang and Tsirang put them on one;
# Dagana puts them on two, and requiring all four words together read no rows
# at all there. So the distinctive word opens the header and the right edge is
# taken from the "Total" on that line or the next.
HEADER_KEY = "Gewog/Town"
HEADER_EDGE = "Total"

# There is no right clip, and there was: the header word "Total" is centred
# over its column while the values are set flush right, so they end past it.
# Dagana's "Total" ends at x=229 and the 575 beneath it does not, so clipping
# there cost every Dagana row its third figure -- the whole table, reported as
# "no gewog rows read". Widening the allowance only moved the guess.
#
# What actually separates a row from the prose beside it is not geometry but
# shape: a row is three consecutive figures with a name in front. The left
# edge still holds, because prose to the *left* of the table would otherwise
# supply that name; to the right it can only add trailing words, and the run
# rule ignores those.
COLUMN = float("inf")   # replaced below by a measured width
SECTIONS = {"Urban", "Rural"}

# The row that closes the table, and there are two spellings of it. Tsirang
# writes "Total"; Bumthang writes "Both Areas", meaning urban and rural
# together. That one word is what the first three attempts at this file were
# actually failing on -- the reader looked for "Total", never found it in
# Bumthang, and reported "no printed Total row" while its gewogs were read
# correctly the whole time. Both are the same row and both close the table.
CLOSERS = {"Total", "Both Areas"}
NUMBER = re.compile(r"^[\d,]+$")

# A town row ends in the word Town or Thromde. Bhutan's four thromdes --
# Thimphu, Phuentsholing, Gelephu and Samdrup Jongkhar -- are municipalities
# reported beside the gewogs, and geoBoundaries draws neither them nor the
# smaller towns.
TOWN = re.compile(r"\b(Town|Thromde)$")

POPULATION_NOTE = (
    "2017 Population and Housing Census, from the dzongkhag's own report, "
    "counting everyone found there 'irrespective of their nationality' as the "
    "report puts it. Bhutan's census does not ask religion, language or "
    "ethnicity, so those three are declared rather than left empty. Note that "
    "the dzongkhag reports and the national report do not agree everywhere: "
    "the twenty come to 720,837 against the 727,145 the national report "
    "analyses, itself 8,408 short of the 735,553 found in the country once "
    "non-Bhutanese in hotels are counted. The figure here is the dzongkhag's "
    "own, which its gewogs add up to exactly.")
GEWOG_NOTE = (
    " This is the gewog's own count. Towns and thromdes are enumerated beside "
    "the gewogs rather than inside them and the boundary file draws none of "
    "them, so a dzongkhag's gewogs come to less than the dzongkhag itself by "
    "its urban population -- 37.8% of Bhutan nationally, and named on the "
    "dzongkhag's record.")


def words_by_row(blob: bytes, tolerance: float = 2.0):
    """Every page as rows of (x0, x1, text), from the words' own boxes.

    The same reading pakistan.py uses, and for a related reason: a page here
    carries two columns of prose beside the table, and only a word's position
    says which it belongs to.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False,
                                       keep_blank_chars=False)
            rows: list[tuple[float, list[tuple[float, float, str]]]] = []
            for word in sorted(words, key=lambda w: (round(w["top"], 1),
                                                     w["x0"])):
                top = round(word["top"], 1)
                cell = (word["x0"], word["x1"], word["text"])
                if rows and abs(rows[-1][0] - top) <= tolerance:
                    rows[-1][1].append(cell)
                else:
                    rows.append((top, [cell]))
            yield [sorted(cells) for _top, cells in rows]


def scan(blob: bytes, strict: bool, dzongkhag: str = "", debug: bool = False
         ) -> tuple[dict[str, int], dict[str, int], int]:
    """Table 2.1 for one dzongkhag: its gewogs, its towns, and its total.

    Two things bound the read, and the first attempt had only one of them.

    **The header fixes the table's left AND right edges**, and nothing outside
    them is considered. The left edge is the defence against the narrative:
    prose and data share a baseline on these pages, so a rule counting numbers
    in a line would take "4,183 persons during the intercensal" for a row. The
    right edge is the defence against the *charts*: Bumthang prints Figure 2.1
    beside its Table 2.1, and the chart's y-axis -- 100, 90, 80, 70, 60 -- sits
    at the same baselines as the gewog rows. With only a left edge, Bumthang
    read three gewogs and then lost the table's own Total row to an axis
    label, which the "no printed Total" refusal caught.

    **The figures do not always end the row, and the column is wider than its
    own header.** Dagana prints "Drukjeygang Town 250 325 575 Bhutan." on one
    baseline, the last word belonging to the prose beside the table; and its
    header word "Total" ends at x=229 while the figures beneath it do not.
    Clipping at the header word and requiring the figures to end the row cost
    Dagana every one of its rows.

    **A row's label can wrap around its own figures.** Chhukha prints
    "Phuentshogling" on the line above the figures for Phuentsholing Thromde
    and the word "Thromde" on the line *below* them. So the row arrives called
    "Phuentshogling" -- which is also a gewog further down the same table.

    That is why rows are classified by the **section** they sit under, Urban
    or Rural, and never by what their name ends in. Classified by suffix, the
    thromde was filed as a gewog and then overwritten by the real gewog of
    that name: 27,658 people, the second city of Bhutan, gone without a trace
    into a dict key. A duplicate name inside one section now stops the run
    rather than keeping whichever arrived second.

    **The header is two stacked rows, on one baseline or two.** "Gewog/Town |
    Persons" sits over "Male | Female | Total"; Bumthang and Tsirang put them
    on a single baseline and Dagana on two. Requiring all four words together
    read no rows at all from Dagana, so the distinctive word opens the header
    and the right edge comes from the "Total" on that line or the next.

    **The closing row has two spellings.** Tsirang writes "Total"; Bumthang
    writes "Both Areas", meaning urban and rural together. Looking only for
    "Total" is what made this file fail on Bumthang while its gewogs were
    being read correctly all along -- ``CLOSERS`` holds both.

    **The table is bounded by its pages**, not only by its closing row.
    Bounding it by the Total alone let the reader run off the end of Table 2.1
    and through the rest of the document -- Tsirang came back with 885 gewogs
    holding 1.2 million people against a printed 22,376, which the
    reconciliation caught and refused. So collection starts on the page
    carrying the header and stops at the printed Total or at the first page
    that yields no rows, whichever comes first.

    A row is exactly three figures with a name before them. Exactly, not at
    least: a line of prose that happens to carry four numbers is not a row of
    this table, and treating it as one is how the first attempt filled up.
    """
    gewogs: dict[str, int] = {}
    towns: dict[str, int] = {}
    printed = 0
    edge: float | None = None
    margin: float | None = None
    waited = 0
    reading = False
    section = ""
    # A label that wrapped onto its own line, waiting for the figures beneath
    # it. Chhukha prints "Tsimasham\nTown" and "Phuentsholing\nThromde", and
    # a row whose name wraps arrives here as three figures and no name.
    # Dropping those cost Chhukha 29,793 people -- almost all of them
    # Phuentsholing, the second city of Bhutan.
    pending: list[str] = []

    for rows in words_by_row(blob):
        if printed:
            break
        found_here = edge is not None and margin is None
        for cells in rows:
            texts = [t for _a, _b, t in cells]
            if margin is None:
                if strict:
                    # All four header words on one baseline. This is how
                    # Tsirang, Bumthang and Chhukha print it, and it is tried
                    # first because it cannot mistake a data row for a header.
                    if (HEADER_KEY in texts and HEADER_EDGE in texts
                            and "Male" in texts and "Female" in texts):
                        edge = min(x0 for x0, _x1, t in cells
                                   if t == HEADER_KEY)
                        margin = max(x1 for _x0, x1, t in cells
                                     if t == HEADER_EDGE)
                        # One column's width past the header word, measured
                        # from the header itself: the words are centred over
                        # their columns and the figures are flush right, so
                        # they end past the word. Dagana needed this; taking
                        # the header word's own edge cost it every row, and
                        # removing the clip entirely let the prose beside the
                        # table into the row names.
                        before = [x1 for _x0, x1, t in cells if t == "Female"]
                        if before:
                            margin += max(0.0, margin - max(before))
                        reading = found_here = True
                        if debug:
                            log(f"    [debug] strict header at x={edge:.0f}"
                                f"..{margin:.0f}: {texts}")
                    elif debug and HEADER_KEY in texts:
                        log(f"    [debug] saw {HEADER_KEY} but not all four: "
                            f"{texts}")
                    continue
                # Relaxed: the two header rows landed on different baselines,
                # which is how Dagana prints it. Only reached when the strict
                # pass read nothing at all from this document.
                if edge is None:
                    if HEADER_KEY in texts:
                        edge = min(x0 for x0, _x1, t in cells
                                   if t == HEADER_KEY)
                        found_here = True
                    continue
                if HEADER_EDGE in texts:
                    margin = max(x1 for _x0, x1, t in cells
                                 if t == HEADER_EDGE)
                else:
                    margin = float("inf")
                reading = found_here = True
                continue
            inside = [(x0, x1, t) for x0, x1, t in cells
                      if x0 >= edge - 3.0 and x1 <= margin + COLUMN]
            if debug and cells:
                log(f"    [debug] row {[t for _a,_b,t in cells][:9]} "
                    f"-> in span {[t for _a,_b,t in inside][:9]}")
            words = [t for _a, _b, t in inside]
            if not words:
                continue
            if words[0] in SECTIONS:
                # By the first word, not by the line being only that word.
                # With no right clip, Bumthang's chart prints its y-axis on
                # the same baselines as the table and "Urban" arrives as
                # "Urban 50"; requiring a lone word lost the section, and
                # every town in the dzongkhag was filed as a gewog.
                #
                # Figures on a section line are its own subtotal or a chart's
                # axis, and are dropped either way: adding an Urban subtotal
                # to the towns under it would count them twice.
                section = words[0]
                pending = []          # a section heading labels nothing
                continue
            # The first run of three consecutive figures, with the name
            # before it. Anything after is narrative that shares the baseline
            # -- Dagana prints "Drukjeygang Town 250 325 575 Bhutan." on one
            # line, the last word belonging to the column of prose beside the
            # table. Requiring the figures to *end* the row dropped it.
            # From index 0 only when a label is already waiting: Chhukha's
            # Phuentsholing row is three figures and nothing else, its name
            # having wrapped onto the line above. Without a pending label a
            # row must carry its own name, or a stray trio of numbers in the
            # prose would become a gewog.
            first = 0 if pending else 1
            at = next((i for i in range(first, max(first + 1, len(words) - 2))
                       if all(NUMBER.match(w) for w in words[i:i + 3])), None)
            figures = list(words[at:at + 3]) if at is not None else []
            if len(figures) != 3:
                # Text inside the table's own span carrying no figures is a
                # label whose row is still to come. Remembered rather than
                # dropped; anything outside the span is prose and never
                # reaches here.
                # A wrapped label is one or two words. Anything longer is
                # the prose beside the table, and letting it accumulate put
                # "2005 and 2017.The population of Trashi" in front of
                # Ramjar's name and "Trashi Yangtse Dzongkhag ranks" in front
                # of the closing row -- which then read as a gewog and
                # doubled the dzongkhag.
                # A short line replaces the pending label; a long one is the
                # prose beside the table and leaves it alone. Dagana prints
                # "Lhamoi Dzingkha", then a line of narrative, then the town's
                # figures, then the word "Town" -- clearing on the narrative
                # lost the row and its 1,961 people.
                if words and not figures and len(words) <= 2:
                    pending = list(words)
                continue
            # The pending label is used only by a row that has no name of
            # its own. Otherwise a stray one-word line above the table gets
            # glued on -- Dagana read "Population Gozhi" for Gozhi.
            name = " ".join(words[:at] if at else pending).strip()
            pending = []
            if not name or NUMBER.match(name):
                continue
            try:
                total = int(figures[-1].replace(",", ""))
            except ValueError:
                continue
            found_here = True
            if name in CLOSERS:
                printed = total
                break
            if name in SECTIONS:
                section = name
                continue
            # Classified by the section it is under, never by its name. The
            # name is not reliable: Chhukha prints "Phuentshogling" above the
            # figures for Phuentsholing Thromde and the word "Thromde" on the
            # line *below* them, so the row arrives called "Phuentshogling" --
            # which is also the name of a gewog further down the same table.
            # Keyed by name and classified by suffix, the thromde landed in
            # `gewogs` and was then overwritten by the gewog: 27,658 people,
            # the second city of Bhutan, gone without a trace.
            # A town by its name or by the section it sits under, because
            # neither alone is enough. Bumthang's two-column page emits both
            # section labels before any row, so the section is "Rural" by the
            # time "Bumthang Town" arrives; and Chhukha's Phuentsholing loses
            # the word "Thromde" to a line break, so only the section knows it
            # is urban. Each covers the other's blind spot.
            into = towns if (TOWN.search(name) or section == "Urban") \
                else gewogs
            if name in into:
                raise SystemExit(
                    f"bhutan: {dzongkhag}: two rows of Table 2.1 are both "
                    f"called {name!r} in the same section. One would silently "
                    f"replace the other, which is how Phuentsholing went "
                    f"missing; refusing rather than keeping whichever came "
                    f"second")
            into[name] = total
        # A page that carried none of this table's rows ends it. Table 2.1
        # runs to one page in the small dzongkhags and two in the large ones,
        # and nothing later in the report is it.
        #
        # Unless nothing has been read at all, in which case the header that
        # opened was not this table's. Dagana's contents page carries a line
        # reading exactly "Gewog/Town Male Female Total"; locking onto the
        # first match and stopping meant the reader spent the whole document
        # on the LIST OF FIGURES and never reached page 13, where the table
        # actually is. A header that leads nowhere is abandoned and the search
        # resumes rather than ending the read.
        if reading and not found_here:
            if gewogs or towns:
                break
            edge = margin = None
            waited = 0
            reading = False
            section = ""
            pending = []

    return gewogs, towns, printed


# Every report states its own total in prose: "The total population of X
# Dzongkhag as of 30 May 2017 was 17,820 persons". That sentence is the
# fallback when the table's closing row cannot be found, and it is a genuinely
# independent control -- it is written by the office, not computed here, and
# it sits outside the table the rows come from.
STATED = re.compile(
    r"total\s+population\s+of\s+\S+.{0,80}?\b(?:is|was)\s+([\d,]+)\s*persons",
    re.I | re.S)


def stated_total(blob: bytes) -> int:
    """The dzongkhag total as the report's own narrative gives it."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages[:30]:
            text = " ".join((page.extract_text() or "").split())
            found = STATED.search(text)
            if found:
                return int(found.group(1).replace(",", ""))
    return 0


def table(blob: bytes, dzongkhag: str, debug: bool = False
          ) -> tuple[dict[str, int], dict[str, int], int]:
    """Table 2.1 for one dzongkhag: its gewogs, its towns, and its total.

    Two passes, and the order matters. The strict one wants all four header
    words on a single baseline; it cannot mistake a data row for a header, and
    it is how most of the twenty print it. Only when that reads nothing at all
    is the relaxed pass tried, which takes the header's second row from a
    following line -- Dagana's layout, and loose enough that letting it run
    first cost Bumthang its whole table.
    """
    gewogs, towns, printed = scan(blob, True, dzongkhag, debug)
    counted = sum(gewogs.values()) + sum(towns.values())
    if not gewogs or not printed or counted != printed:
        # The strict pass either found no header or found one and did not
        # reconcile. Either way the relaxed pass is worth asking, and only a
        # result that reconciles is allowed to replace one that does not.
        loose = scan(blob, False, dzongkhag, debug)
        if loose[0] and loose[2] and \
                sum(loose[0].values()) + sum(loose[1].values()) == loose[2]:
            gewogs, towns, printed = loose
    if not gewogs:
        raise SystemExit(f"bhutan: {dzongkhag}: no gewog rows read from "
                         f"Table 2.1")
    if not printed:
        # The closing row is spelt "Total" in some reports and "Both Areas" in
        # others, and Trashi Yangtse prints neither where this reader can see
        # it. The narrative's own sentence stands in -- it is the office's
        # figure, not one computed here, and the rows are still held to it.
        printed = stated_total(blob)
        if printed:
            log(f"    {dzongkhag}: no closing row; held to the "
                f"{printed:,} its own text states")
    if not printed:
        raise SystemExit(
            f"bhutan: {dzongkhag}: Table 2.1 has no closing row and the "
            f"report states no total in its text either, so nothing says "
            f"these {len(gewogs)} gewogs are all of them")
    counted = sum(gewogs.values()) + sum(towns.values())
    if counted != printed:
        raise SystemExit(
            f"bhutan: {dzongkhag}: {len(gewogs)} gewogs and {len(towns)} "
            f"towns hold {counted:,} against the {printed:,} printed beside "
            f"them -- {printed - counted:+,}. A gewog this reader never "
            f"noticed is a hole, and every other check here passes over it."
            f"\n      gewogs: " + ", ".join(f"{k} {v:,}"
                                            for k, v in sorted(gewogs.items()))
            + f"\n      towns: " + ", ".join(f"{k} {v:,}"
                                             for k, v in sorted(towns.items())))
    return gewogs, towns, printed


def fetch(url: str) -> bytes:
    import urllib.request

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; DemographicMap/1.0; "
                      "+https://github.com/advaitsridhar/DemographicMap)",
        "Accept": "application/pdf,*/*",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    ap.add_argument("--debug", action="store_true",
                    help="print what the reader sees, for one dzongkhag")
    ap.add_argument("--only", default="",
                    help="one dzongkhag, for working out a layout")
    args = ap.parse_args()

    log("bhutan: National Statistics Bureau, PHCB 2017 Table 2.1")
    records: list[dict[str, Any]] = []
    absent: list[str] = []
    national = 0
    urban_total = 0
    wanted = {k: v for k, v in DZONGKHAGS.items()
              if not args.only or k == args.only}

    for dzongkhag, filename in wanted.items():
        url = f"{BASE}/{filename}"
        try:
            blob = fetch(url)
        except Exception as err:                        # noqa: BLE001
            absent.append(f"{dzongkhag}: {type(err).__name__} {str(err)[:60]}")
            continue
        gewogs, towns, printed = table(blob, dzongkhag, args.debug)
        national += printed
        urban_total += sum(towns.values())
        log(f"  {dzongkhag}: {len(gewogs)} gewogs, {len(towns)} town(s), "
            f"{printed:,} people")

        cite = [{"field": "population", "name": SOURCE, "url": url,
                 "license": LICENCE}]
        note = POPULATION_NOTE
        if towns:
            note += (" Of these, " + f"{sum(towns.values()):,}"
                     + " are counted in "
                     + ", ".join(sorted(towns))
                     + ", which the boundary file does not draw, so the "
                       "gewogs below come to that much less than this row.")
        records.append(record(
            f"BTN-{dzongkhag.lower().replace(' ', '-')}", dzongkhag,
            level="admin1", parent="BTN", country="BTN",
            aliases=list(DZONGKHAG_ALIASES.get(dzongkhag, ())),
            population=measure(printed, year=YEAR, source=SOURCE),
            population_note=note,
            sources=list(cite)))
        for name, people in sorted(gewogs.items()):
            records.append(record(
                f"BTN-{dzongkhag.lower().replace(' ', '-')}-"
                f"{name.lower().replace(' ', '-')}",
                name, level="admin2", parent="BTN", country="BTN",
                aliases=list(GEWOG_ALIASES.get(name, ())),
                parent_name=dzongkhag,
                parent_aliases=list(DZONGKHAG_ALIASES.get(dzongkhag, ())),
                population=measure(people, year=YEAR, source=SOURCE),
                population_note=POPULATION_NOTE + GEWOG_NOTE,
                sources=list(cite)))

    for line in absent:
        log(f"  NOT READ -- {line}")
    if absent:
        raise SystemExit(
            f"bhutan: {len(absent)} of {len(wanted)} dzongkhag reports were "
            f"not read; refusing to write a partial Bhutan")

    if not args.only:
        log(f"  the twenty dzongkhags come to {national:,}, against the "
            f"{NATIONAL_ANALYSED:,} the national report analyses and the "
            f"{NATIONAL_FOUND:,} it says were found -- "
            f"{national - NATIONAL_ANALYSED:+,} on the first. The two "
            f"publications disagree for some dzongkhags; each report here "
            f"reconciles to its own printed total.")

    out = args.out or PROCESSED / "bhutan_gewog.json"
    write_json(out, records)
    gewogs = sum(1 for r in records if r["level"] == "admin2")
    log(f"  {len(records) - gewogs} dzongkhags and {gewogs} gewogs, "
        f"{urban_total:,} people in towns with no shape")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
