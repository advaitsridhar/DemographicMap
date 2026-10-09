#!/usr/bin/env python3
"""Bhutan -- Population & Housing Census 2017, population by gewog.

**This adapter publishes a head count, a sex ratio, a median age and
citizenship and nothing else, and the reason is worth stating rather than
leaving as an empty field.** The median comes from the same reports' annex: Table A2.6's
single years for the dzongkhag, Table A2.7's five-year groups for each gewog,
both held to Table 2.1 (see "Median age" below). Bhutan's
census does not ask religion, language or ethnicity. That is not "does not
publish": the 2017 national report runs 288 pages over education, fertility,
mortality, disability, labour, migration and housing, and the words religion,
ethnic, Hindu, Buddhist and mother tongue occur on none of them except two
pages describing the census's own publicity -- talk shows held in Dzongkha,
Sharchopkha and Lhotshamkha, and the literacy test card. The twenty dzongkhag
volumes, 1,510 pages read as one sweep, carry one hit apiece and it is the
same sentence every time: the definition of literacy, "the ability to read and
write a short text in Dzongkha, English, Lhotshamkha, or any other language".
The 2005 round is the same. So the three composition fields are declared
``not_collected`` in ``scripts/common.py`` and this file fills what the census
does count.

**The one identity count the census does publish is citizenship**, the
Bhutanese against everyone else, by dzongkhag and by gewog: each report's
Table 2.2 counts the Bhutanese in the same rows in which Table 2.1 counts
everyone found "irrespective of their nationality" -- the report's own words.
Since the map owner's decision of 19 September 2026 that a census's count of
nationality or citizenship may stand on the ethnicity field, under an
``ethnicity_basis`` that names it, Table 2.2 is read and written there, basis
"citizenship" (see "Citizenship" below). It is a count of citizenship and not
an ethnic composition, and every note says so. Table 2.1 stays the
population: everyone found, which is the figure that belongs on a map of
where people are.

**The sex ratio comes from the same three columns.** Table 2.1 prints Male,
Female and Total for every gewog, every town and the dzongkhag itself, and the
reader has always parsed all three and kept the last. The ratio is derived as
females per 1,000 males, the convention the rest of South Asia is published in
here, and it is derived only where the publisher's own two columns add up to
the total printed beside them. Where they do not, the row keeps its printed
head count -- that figure is the office's -- and publishes no ratio at all,
naming the disagreement in its gap. A ratio computed from figures NSB itself
does not add up would be a number this map invented, and it would be
indistinguishable on the page from one the census measured.

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

**A gewog reaches its polygon by where it is, not by what it is called.**
geoBoundaries draws 205 Bhutanese gewogs and the census publishes 205, but
the two disagree about the names of thirty of them -- and not as spellings.
The boundary file labels Samtse's Tashicholing "Sipsu" and its Norgaygang
"Bara", Sarpang's Samtenling "Bhur", Tsirang's Patshaling "Beteni": the
Nepali-origin names southern Bhutan carried before the renamings. No
romanisation rule crosses that, and the one thing worse than leaving those
thirty shapes empty is filling them from a resemblance. So they are paired by
a reference point -- Wikidata's own point for the gewog the census names,
falling inside the polygon the boundary file draws, with Wikidata's dzongkhag
for it agreeing with the census's. See ``GEWOG_BY_POINT``, which also records
the two pairs the old name-matching got wrong.

Usage:
    python -m scripts.fetch_census.bhutan
"""

from __future__ import annotations

import argparse
import io
import re
from typing import Any, NamedTuple

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, log, measure, record, shares, write_json,
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
# overlap and 4 by the point-in-polygon rule the build used then, where it has
# 11. A parent that is wrong cannot confirm a name.
#
# **Two of these pairs were wrong, and the limit is why.** A name matched
# without a place behind it can land anywhere, and twice it did: Punakha's
# Barp was aliased to a shape called "Bara" that sits 96% inside Samtse, and
# Chhukha's Maedtabkha to "Patakla", 60% inside Tsirang. Both have been
# removed; both gewogs are now bound by GEWOG_BY_POINT below, and the two
# shapes turn out to be Samtse's Norgaygang and Tsirang's Sergithang, which
# had no figures at all while two other dzongkhags' people sat on them. The
# refusals in this table held up better than its acceptances: "Pemaling" to
# "Pagli" scored 0.62 and was left out, and Pemaling is Biru -- Pagli is
# Phuentshogpelri.
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
    "Maedtsho": ("Metsho",),
    "Maedwang": ("Mewang",),
    "Maenbi": ("Menbi",),
    "Merag": ("Merak",),
    "Minjey": ("Minjay",),
    "Monggar": ("Mongar",),
    "Namgyalchhoeling": ("Namgyel Chhoeling",),
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

# The gewogs the boundary file draws under a name that is not a spelling of
# the census's at all, paired by where they are rather than by what they are
# called. Every one of these is a *place*, not a string: Samtse's Tashicholing
# is drawn as "Sipsu", its Norgaygang as "Bara", Sarpang's Samtenling as
# "Bhur", Tsirang's Patshaling as "Beteni". No romanisation rule reaches any
# of those, and no rule should -- they are the Nepali-origin names the
# southern dzongkhags carried before the renamings of the 1950s to 1990s and
# the 1996-97 romanisation standardisation, and CGAZ still labels the polygons
# with them.
#
# **The evidence is a reference point inside a polygon, and it is checked two
# ways.** Wikidata carries Bhutan's gewogs with P131 (the dzongkhag) and P625
# (a point); `data/processed/bhutan_wikidata_gewog.json` holds 240 of them,
# 166 with a point. A pair is taken only where the point of the gewog *the
# census names* falls inside the polygon *the boundary file draws*, AND
# Wikidata's dzongkhag for that gewog is the dzongkhag the census printed it
# under. Two independent statements about the same ground, neither of them a
# string comparison.
#
# The method was measured before it was trusted: of the 102 gewogs that carry
# a point and whose name the boundary file already matched, 98 have their
# point inside their own polygon. The four that do not are on borders. That is
# the same reading Nepal's district bindings rest on, and for the same reason
# -- a polygon is identified by what is inside it, not by what it is labelled.
#
# Corroborated a third time by the list of gewogs each dzongkhag has: the
# Wikipedia article *Gewogs of Bhutan* prints all 205 with their Dzongkha, and
# each pair below is one gewog of the dzongkhag the census printed it under.
# The Dzongkha settles several that look like different words in Latin script:
# the census's Karna is བཀར་ན་ (Kana), its Maedtabkha is སྨད་བཏབ་ཁ་ (Metakha),
# its Darkarla is དར་དཀར་ལ་ (Dagala), its Nagya is ན་རྒྱ་ (Naja).
#
# Keyed by (gewog, dzongkhag) because two of Bhutan's gewog names are not
# unique: an alias keyed on the name alone is what put both Norboogangs on one
# shape and lost both. Those four rows are in SHAPE_BOUND instead.
GEWOG_BY_POINT: dict[tuple[str, str], tuple[str, ...]] = {
    ("Maedtabkha", "Chhukha"): ("Metap",),
    ("Karmaling", "Dagana"): ("Deorali",),
    ("Karna", "Dagana"): ("Kalidzingkha",),
    ("Khebisa", "Dagana"): ("Khipisa",),
    ("Sangbay", "Haa"): ("Sombey",),
    ("Dokar", "Paro"): ("Doga",),
    ("Nagya", "Paro"): ("Naja",),
    ("Dungmaed", "Pema Gatshel"): ("Dungmin",),
    ("Barp", "Punakha"): ("Bapisa",),
    ("Orong", "Samdrup Jongkhar"): ("Jangchhubling",),
    ("Doomtoed", "Samtse"): ("Dungtoe",),
    ("Dophuchen", "Samtse"): ("Dorokha",),
    ("Norgaygang", "Samtse"): ("Bara",),
    ("Pemaling", "Samtse"): ("Biru",),
    ("Phuentshogpelri", "Samtse"): ("Pagli",),
    ("Sang-Ngag-", "Samtse"): ("Chargharay",),
    ("Tashichhoeling", "Samtse"): ("Sipsu",),
    ("Chhudzom", "Sarpang"): ("Doban",),
    ("Samtenling", "Sarpang"): ("Bhur",),
    ("Tareythang", "Sarpang"): ("Taklai",),
    ("Darkarla", "Thimphu"): ("Dagala",),
    ("Tongmajangsa", "Trashi Yangtse"): ("Tomzhangtshen",),
    ("Yangtse", "Trashi Yangtse"): ("Trashiyangtse",),
    ("Patshaling", "Tsirang"): ("Beteni",),
    ("Sergithang", "Tsirang"): ("Patakla",),
    ("Darkar", "Wangdue Phodrang"): ("Daga",),
}

# The six of those the point could not settle, and what settles them instead.
# Six gewogs have no P625 on Wikidata, so the pairing rests on the two lists
# closing: the dzongkhag's gewogs as the article prints them and as the census
# prints them agree name for name except at one place each, every other shape
# in the dzongkhag is claimed, and the remainder is forced. Trashi Yangtse is
# the one with two left over, and the boundary file's own labelling separates
# them: "Tomzhangtshen" is the article's Tomzhang (སྟོང་མི་གཞང་ས་, the census's
# Tongmajangsa), leaving the polygon labelled with the dzongkhag's own name,
# "Trashiyangtse", as the gewog of Yangtse that holds its seat.
BY_CLOSURE: frozenset[tuple[str, str]] = frozenset({
    ("Nagya", "Paro"),
    ("Doomtoed", "Samtse"),
    ("Darkarla", "Thimphu"),
    ("Tongmajangsa", "Trashi Yangtse"),
    ("Yangtse", "Trashi Yangtse"),
    ("Darkar", "Wangdue Phodrang"),
})

# Gewogs bound to one polygon by that polygon's id, because their name cannot
# do it. Bhutan has two gewogs called Gakiling -- one in Haa, one in Sarpang
# -- and two called Norbugang, in Pema Gatshel and in Samtse. A name-keyed
# match cannot tell them apart: country-wide it is ambiguous, and the build
# refuses both rows rather than letting one wear the other's people, which is
# why all four shapes were empty. Which polygon is which is settled the same
# way as GEWOG_BY_POINT -- Wikidata's Gakiling [Haa] point falls in the
# polygon labelled "Gakiling" and its Gakiling [Sarpang] point in the one
# labelled "Hiley"; Norbugang [Pema Gatshel] in "Norbugang" and Norbugang
# [Samtse] in "Chengmari", the name Samtse's gewog carried before it was
# renamed.
SHAPE_BOUND: dict[tuple[str, str], str] = {
    ("Gakiling", "Haa"): "84629894B40252407393905",          # "Gakiling"
    ("Gakiling", "Sarpang"): "84629894B8166759987677",       # "Hiley"
    ("Norboogang", "Pema Gatshel"): "84629894B84199937092772",  # "Norbugang"
    ("Norboogang", "Samtse"): "84629894B7629980605125",      # "Chengmari"
}

# What the boundary file calls each bound shape, for the note that says so.
# A reader who looks the shape up will find the other name on it, and an
# unexplained disagreement is its own kind of error.
SHAPE_LABELS: dict[str, str] = {
    "84629894B40252407393905": "Gakiling",
    "84629894B8166759987677": "Hiley",
    "84629894B84199937092772": "Norbugang",
    "84629894B7629980605125": "Chengmari",
}


# Bhutan's two published totals, and they are both real. The national report:
# "Bhutan's total population is 735,553 ... It includes 8,408
# non-Bhutanese/tourists found in hotels and those on the move on census
# reference day. The analyses in this Report are based on 727,145 persons
# since no detailed information was collected from the 8,408."
NATIONAL_FOUND = 735_553      # everyone found in Bhutan on the day
NATIONAL_ANALYSED = 727_145   # what the report's own tables are built on

# The same table's national row, male and female, as the national report
# prints it: "Bhutan 380,453 52.3 346,692 47.7 727,145". It is the control the
# twenty dzongkhag volumes are reported against below, not a figure written
# onto any record here -- the country's own row on this map comes from the
# Factbook, and these two are what the census itself counted.
NATIONAL_MALE = 380_453
NATIONAL_FEMALE = 346_692

# The twenty dzongkhag reports' Table 2.1 totals are the national report's
# 727,145 between them, and their sexes its 380,453 and 346,692. This file
# once read them 6,308 short and put it down to a disagreement between NSB's
# publications: Paro 43,362 against the national 46,316, Punakha 27,360
# against 28,740, Lhuentse 14,240 against 14,437, Trashigang 43,741 against
# 45,518. There was none. Those four were the *Bhutanese* populations of
# their Table 2.2, read in place of a Table 2.1 whose header this reader did
# not recognise (see :func:`table`); Paro's own Table 2.1 prints 46,316.
#
# Each dzongkhag report reconciles internally, gewog by gewog, to the total
# printed in it, which is the hard check per report; the national sum is
# checked once all twenty are read (see main).
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
    "ethnicity: religion and language are declared rather than left empty, "
    "and the ethnicity field carries citizenship, the one count of identity "
    "the census publishes. The twenty dzongkhag reports come to the 727,145 "
    "people the national report analyses, which leaves out the 8,408 "
    "non-Bhutanese and tourists found in hotels or on the move on census "
    "night, of whom no details were taken (735,553 in all). The figure here "
    "is the dzongkhag's own, which its gewogs and towns add up to exactly.")
SEX_RATIO_NOTE = (
    "Females per 1,000 males, derived from the Male and Female columns of the "
    "same Table 2.1 row as the population beside it. Beside sex, the one "
    "count of identity the census publishes is citizenship, which is on the "
    "ethnicity field.")
# What is written in place of a ratio where the publisher's own halves do not
# reach the total it prints next to them. The figures go in the note, because
# "not available" without them reads as "nobody fetched this", and what
# actually happened is that the source contradicted itself on this one row.
SEX_RATIO_REFUSED = (
    "Table 2.1 prints {male:,} males and {female:,} females against a total "
    "of {total:,} for this row -- {diff:+,} -- so the two halves are not the "
    "whole that is published beside them. The head count is the report's own "
    "and stands; a ratio derived from figures the census does not itself add "
    "up would be this map's arithmetic, not Bhutan's measurement.")
# The two ways a gewog reaches a polygon the boundary file labels differently,
# said on the record itself. In the southern dzongkhags the label is usually
# the Nepali-origin name the place carried before the renamings; elsewhere it
# is another romanisation of the same word. Either way the name is not what
# made the join, and the note says what did.
RENAMED_NOTE = (
    " The boundary file draws this gewog as {label}. The polygon was "
    "identified by this gewog's own reference point falling inside it and by "
    "Wikidata placing that gewog in this dzongkhag, not by either spelling.")
CLOSURE_NOTE = (
    " The boundary file draws this gewog as {label}. This gewog has no "
    "reference point to place it with, so the polygon was identified by "
    "elimination: every other gewog of {dzongkhag} is matched, and this is "
    "the one polygon and the one gewog left.")
GEWOG_NOTE = (
    " This is the gewog's own count. Towns and thromdes are enumerated beside "
    "the gewogs rather than inside them and the boundary file draws none of "
    "them, so a dzongkhag's gewogs come to less than the dzongkhag itself by "
    "its urban population -- 37.8% of Bhutan nationally, and named on the "
    "dzongkhag's record.")


class Read(NamedTuple):
    """One report's Table 2.1: its rows, their sexes, and its printed total.

    The sexes are kept in their own mapping rather than beside each total,
    because the names are not unique across the two: Chhukha has a gewog and a
    thromde both called Phuentshogling, and one dictionary keyed by name would
    have the thromde's men standing in for the gewog's. ``towns`` gets no
    entry here at all -- no shape is drawn for a town, so no record is built
    for one, and a ratio computed for a row that reaches no map is a figure
    with nowhere to be wrong in public.
    """

    gewogs: dict[str, int]
    towns: dict[str, int]
    printed: int
    sexes: dict[str, tuple[int, int]]
    printed_sexes: tuple[int, int] | None


def sex_ratio(male: int, female: int, total: int, where: str) -> dict[str, Any]:
    """Females per 1,000 males for one row, or a gap saying why not.

    The check is the publisher's own arithmetic: Male plus Female must be the
    Total printed on that row. Where it is, the ratio is the census's; where
    it is not, there is no honest ratio to take -- either a figure was misread
    here or the table disagrees with itself, and neither is a thing to divide.
    """
    if male + female != total:
        log(f"    {where}: no sex ratio -- Table 2.1 prints {male:,} + "
            f"{female:,} = {male + female:,} against the {total:,} on the "
            f"same row ({male + female - total:+,})")
        return gap(NOT_AVAILABLE, SEX_RATIO_REFUSED.format(
            male=male, female=female, total=total,
            diff=male + female - total))
    if not male:
        log(f"    {where}: no sex ratio -- no males on the row, so females "
            f"per 1,000 males has no denominator")
        return gap(NOT_AVAILABLE,
                   "Table 2.1 counts no males in this row, so there is "
                   "nothing to express the females per thousand of.")
    return measure(round(1000.0 * female / male),
                   unit="females_per_1000_males", year=YEAR, source=SOURCE)


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


def header_variants(cells, broken_key: float | None
                    ) -> tuple[list[tuple[float, float, str]], float | None]:
    """A header line with its first word put back to ``HEADER_KEY``.

    The reports set that word four ways, and only a line read under its
    table's title is rewritten (see :func:`scan`):

    * "Gewog/Town" -- most of them; left as it is.
    * "Gewog /Town" -- Punakha's Table 2.1, two words with a space before the
      slash; joined.
    * "Name" -- Paro's and Lhuentse's Table 2.1; taken as the key only where
      the same line carries Male, Female and Total, so a line of prose that
      says "name" is never a header.
    * "Gewog/" on a line of its own and "Town Male Female ..." on the next --
      Bumthang's Table 2.2; ``broken_key`` carries the first word's left edge
      from one line to the next.

    Returns the line and the ``broken_key`` for the line after it.
    """
    out = list(cells)
    texts = [t for _a, _b, t in out]
    start, end = HEADER_KEY.split("/")
    joined = []
    i = 0
    while i < len(out):
        x0, x1, t = out[i]
        if (t == start and i + 1 < len(out) and out[i + 1][2] == "/" + end):
            joined.append((x0, out[i + 1][1], HEADER_KEY))
            i += 2
            continue
        joined.append((x0, x1, t))
        i += 1
    out = joined
    texts = [t for _a, _b, t in out]
    if (HEADER_KEY not in texts and "Name" in texts and HEADER_EDGE in texts
            and "Male" in texts and "Female" in texts):
        out = [(x0, x1, HEADER_KEY if t == "Name" else t) for x0, x1, t in out]
    if broken_key is not None and end in texts and HEADER_KEY not in texts:
        out = [(min(x0, broken_key), x1, HEADER_KEY) if t == end else (x0, x1, t)
               for x0, x1, t in out]
    texts = [t for _a, _b, t in out]
    following = (min(x0 for x0, _x1, t in out if t == start + "/")
                 if start + "/" in texts else None)
    return out, following


def scan(blob: bytes, strict: bool, dzongkhag: str = "", debug: bool = False,
         title: tuple[str, ...] | None = None, slack: float = 3.0) -> Read:
    """Table 2.1 for one dzongkhag: its gewogs, its towns, and its total.

    With ``title``, the same reading of a later table set out the same way --
    Table 2.2, the Bhutanese population by gewog and town -- whose header is
    looked for only below a line carrying all of ``title``'s words on the same
    page. The contents page carries the title too, with no table under it, and
    Table 2.1's own header comes before Table 2.2's: without the page rule the
    first header after the contents entry would be Table 2.1's.

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

    Two things only Table 2.2 has needed, and only there are they allowed:

    * **Its header word can break at the slash.** Bumthang's Table 2.2 sets
      "Gewog/" on a line of its own and "Town Male Female Total ..." on the
      next, so neither line carries "Gewog/Town" and the table was "not found
      under its title". A "Gewog/" line followed by a line holding "Town" and
      the other header words is the same header, its left edge the leftmost of
      the two words.
    * **Its labels can start left of its header word.** Gasa's Table 2.2
      centres "Gewog/Town" at x=71 over labels set from x=61, and the left
      edge, three points short of the header word, cut every label off its
      figures -- "Gasa Town" read as "Town", "Both Areas" as "Areas", and the
      table as 5,173 people with no closing row. ``slack`` is how far left of
      the header word a label may start; :func:`citizens` widens it only when
      the ordinary read does not reconcile, and every check after it still
      applies.
    """
    gewogs: dict[str, int] = {}
    towns: dict[str, int] = {}
    sexes: dict[str, tuple[int, int]] = {}
    printed = 0
    printed_sexes: tuple[int, int] | None = None
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
    # Under a title only: where "Gewog/" stood alone on the line just read,
    # its left edge, waiting for the line that finishes the header (Bumthang).
    broken_key: float | None = None

    for rows in words_by_row(blob):
        if printed:
            break
        found_here = edge is not None and margin is None
        titled = title is None or margin is not None
        for cells in rows:
            texts = [t for _a, _b, t in cells]
            if not titled:
                # Bumthang prints "Table 2.2:", the others "Table 2.2".
                bare = {t.strip(".:,;") for t in texts}
                titled = all(word in bare for word in title or ())
                continue
            if margin is None:
                # Under a title only (Table 2.2, and Table 2.1 read under its
                # own), the header word as the reports actually set it:
                if title is not None:
                    cells, broken_key = header_variants(cells, broken_key)
                    texts = [t for _a, _b, t in cells]
                key_here = HEADER_KEY in texts
                if strict:
                    # All four header words on one baseline. This is how
                    # Tsirang, Bumthang and Chhukha print it, and it is tried
                    # first because it cannot mistake a data row for a header.
                    if (key_here and HEADER_EDGE in texts
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
                      if x0 >= edge - slack and x1 <= margin + COLUMN]
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
            own = list(words[:at]) if at else []
            if pending and own and TOWN.fullmatch(" ".join(own)):
                # Except a town whose name wrapped above its own word "Town":
                # Gasa's Table 2.2 sets each town's name on one line and
                # "Town" beside the figures on the next, and two rows both
                # called "Town" stopped the run.
                own = pending + own
            name = " ".join(own if at else pending).strip()
            pending = []
            if not name or NUMBER.match(name):
                continue
            try:
                # All three, where only the last used to be kept. The first
                # two are the sex split of the same people, printed on the
                # same row by the same office, and they are what the sex
                # ratio is derived from; NUMBER has already matched each.
                male, female, total = (int(f.replace(",", ""))
                                       for f in figures)
            except ValueError:
                continue
            found_here = True
            if name in CLOSERS:
                printed = total
                printed_sexes = (male, female)
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
            if name in into and into is towns and title is not None:
                # Table 2.2's towns reach no shape and are held only through
                # its closing row, so a second town row whose name this
                # reader could not put together (Gasa's) is kept apart, never
                # dropped. Table 2.1, and every gewog, still refuses below.
                name = f"{name} ({sum(1 for k in towns if k.startswith(name)) + 1})"
            if name in into:
                raise SystemExit(
                    f"bhutan: {dzongkhag}: two rows of Table 2.1 are both "
                    f"called {name!r} in the same section. One would silently "
                    f"replace the other, which is how Phuentsholing went "
                    f"missing; refusing rather than keeping whichever came "
                    f"second")
            into[name] = total
            if into is gewogs:
                sexes[name] = (male, female)
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

    return Read(gewogs, towns, printed, sexes, printed_sexes)


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


def reconciles(read: Read) -> bool:
    """Rows read, a closing row read, and the rows making the closing row."""
    counted = sum(read.gewogs.values()) + sum(read.towns.values())
    return bool(read.gewogs) and bool(read.printed) and counted == read.printed


# Table 2.1's title as the reports print it: "Table 2.1 Population
# Distribution by Gewog/Town and Sex, Paro 2017", and variants of the words
# after the number. The number is the part all twenty share.
TABLE_TITLE = ("2.1",)


def table(blob: bytes, dzongkhag: str, debug: bool = False) -> Read:
    """Table 2.1 for one dzongkhag: its gewogs, its towns, and its total.

    Two passes, and the order matters. The strict one wants all four header
    words on a single baseline; it cannot mistake a data row for a header, and
    it is how most of the twenty print it. Only when that reads nothing at all
    is the relaxed pass tried, which takes the header's second row from a
    following line -- Dagana's layout, and loose enough that letting it run
    first cost Bumthang its whole table.

    **Both passes are first made under the table's own title**, and that is
    the half this file had wrong for longest. Read without it, the reader
    took the first header it could recognise, and in four reports that was
    not Table 2.1's: Paro and Lhuentse head the column "Name", Punakha writes
    "Gewog /Town" with a space, and Trashigang sets "Male Female Total" a line
    below its "Gewog/Town". The first header the reader knew was then Table
    2.2's, four pages on -- the *Bhutanese* population by gewog -- which
    reconciles to its own closing row like any other table and was taken for
    Table 2.1. Those four dzongkhags were short of their own reports by 6,308
    people, every non-Bhutanese counted in them, on the map and in their sex
    ratios, and the shortfall was put down to a disagreement between the
    reports and the national volume that does not exist: Paro's Table 2.1
    prints 46,316, as the national report does. So the header is now looked
    for only on a page carrying "2.1" in a line above it, the header words as
    those reports set them are understood there (:func:`header_variants`),
    and the ungated read is kept only as a fallback that is refused if what
    it read is Table 2.2.
    """
    read: Read | None = None
    for strict in (True, False):
        candidate = scan(blob, strict, dzongkhag, debug, title=TABLE_TITLE)
        if candidate.gewogs and (reconciles(candidate) or not candidate.printed):
            if read is None or reconciles(candidate):
                read = candidate
            if reconciles(candidate):
                break
    if read is None:
        read = scan(blob, True, dzongkhag, debug)
        if not reconciles(read):
            # The strict pass either found no header or found one and did not
            # reconcile. Either way the relaxed pass is worth asking, and only
            # a result that reconciles is allowed to replace one that does not.
            loose = scan(blob, False, dzongkhag, debug)
            if reconciles(loose):
                read = loose
        # Read without its title, the table could be Table 2.2, which is
        # laid out the same way and reconciles the same way: refused if so.
        for strict in (True, False):
            other = scan(blob, strict, dzongkhag, False, title=CITIZEN_TITLE)
            if reconciles(other) and other.gewogs == read.gewogs:
                raise SystemExit(
                    f"bhutan: {dzongkhag}: the table read as Table 2.1 is "
                    f"Table 2.2, the Bhutanese population, row for row; "
                    f"Table 2.1's own header was not found under its title")
    if not read.gewogs:
        raise SystemExit(f"bhutan: {dzongkhag}: no gewog rows read from "
                         f"Table 2.1")
    if not read.printed:
        # The closing row is spelt "Total" in some reports and "Both Areas" in
        # others, and Trashi Yangtse prints neither where this reader can see
        # it. The narrative's own sentence stands in -- it is the office's
        # figure, not one computed here, and the rows are still held to it.
        #
        # It stands in for the head count only. That sentence gives no split
        # by sex, so a report reached this way has no dzongkhag-level ratio,
        # and `printed_sexes` stays None rather than being reconstructed from
        # the rows: the gewogs are short of the dzongkhag by its towns, and a
        # ratio built from them would be the rural one wearing the whole
        # dzongkhag's name.
        printed = stated_total(blob)
        if printed:
            log(f"    {dzongkhag}: no closing row; held to the "
                f"{printed:,} its own text states")
            read = read._replace(printed=printed)
    if not read.printed:
        raise SystemExit(
            f"bhutan: {dzongkhag}: Table 2.1 has no closing row and the "
            f"report states no total in its text either, so nothing says "
            f"these {len(read.gewogs)} gewogs are all of them")
    gewogs, towns, printed = read.gewogs, read.towns, read.printed
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
    return read


# ---------------------------------------------------------------------------
# Citizenship: Table 2.2
# ---------------------------------------------------------------------------
#
# Every dzongkhag report follows Table 2.1 with Table 2.2, "Distribution of
# Bhutanese Population by Sex and Gewog/Town": the same rows -- the towns
# under Urban, the gewogs under Rural, "Both Areas" closing -- counting the
# Bhutanese citizens among them, beside percentages and a sex ratio. Table 2.1
# counts everyone found "irrespective of their nationality", so each row of
# Table 2.1 less the same row of Table 2.2 is the people there who are not
# Bhutanese, which the report's text states for the dzongkhag ("The total
# number of non-Bhutanese population in Tsirang Dzongkhag is 862 persons":
# 22,376 less 21,514).
#
# The map's owner decided on 19 September 2026 that a census's count of
# nationality or citizenship may stand on the ethnicity field, under an
# ``ethnicity_basis`` naming it, where the census asks no ethnicity. Bhutan's
# asks none, and its citizenship is written here, basis "citizenship", with a
# note that says what it is and is not.
CITIZEN_TITLE = ("2.2", "Bhutanese")
# How far left of the header word "Gewog/Town" a Table 2.2 label may start,
# when the ordinary three points do not reconcile: Gasa sets its labels ten
# points left of the word (x=61 against 71). Twelve takes them and stops well
# short of the gutter between the page's two columns of prose.
LABEL_SLACK = 12.0
CITIZEN_SOURCE = ("National Statistics Bureau of Bhutan, Population & Housing "
                  "Census of Bhutan 2017, Tables 2.1 and 2.2: population and "
                  "Bhutanese population by gewog and town")
CITIZEN_NOTE = (
    "Citizenship, not ethnicity: Bhutan's census does not ask ethnicity. Of "
    "the {everyone:,} people Table 2.1 of the dzongkhag's 2017 report counts "
    "here, {bhutanese:,} are Bhutanese (its Table 2.2) and {others:,} are not "
    "-- Table 2.1 counts everyone found on census day whatever their "
    "nationality, so the difference between the two tables is everyone else. "
    "Written by the map owner's decision of 19 September 2026 that a census's "
    "count of citizenship may stand on this field under its basis.")


def citizens(blob: bytes, dzongkhag: str, read: Read, debug: bool = False
             ) -> tuple[Read | None, str]:
    """Table 2.2, held row by row to Table 2.1, or None and the reason.

    Read the way Table 2.1 is -- the strict header first, the relaxed one
    only where that reads nothing that reconciles -- and kept only where it
    reconciles to its own closing row, names exactly Table 2.1's gewogs and
    towns, and counts no more Bhutanese in any row than Table 2.1 counts
    people. A report this cannot read loses its citizenship, not the run.
    """
    def whole(table22: Read) -> bool:
        counted = sum(table22.gewogs.values()) + sum(table22.towns.values())
        return bool(table22.gewogs) and bool(table22.printed) \
            and counted == table22.printed

    def attempt(strict: bool, slack: float = 3.0) -> Read | str:
        # scan's refusals are written for Table 2.1, where they must stop
        # the run; here they cost the dzongkhag its citizenship and are kept
        # as the reason.
        try:
            return scan(blob, strict, dzongkhag, debug, title=CITIZEN_TITLE,
                        slack=slack)
        except SystemExit as stop:
            return str(stop).replace("Table 2.1", "Table 2.2")

    found = attempt(True)
    # The ordinary read first; then the relaxed header; then each again with
    # labels allowed to start a little left of the header word (Gasa). Only a
    # read that reconciles to its own closing row replaces the first.
    for strict, slack in ((False, 3.0), (True, LABEL_SLACK), (False, LABEL_SLACK)):
        if not isinstance(found, str) and whole(found):
            break
        other = attempt(strict, slack)
        if not isinstance(other, str) and whole(other):
            found = other
    if isinstance(found, str):
        return None, found.removeprefix(f"bhutan: {dzongkhag}: ")
    if not found.gewogs:
        return None, "Table 2.2 was not found under its title"
    counted = sum(found.gewogs.values()) + sum(found.towns.values())
    if not found.printed or counted != found.printed:
        return None, (f"Table 2.2's rows come to {counted:,} against the "
                      f"{found.printed:,} it prints beside them")
    # A gewog's name that wrapped onto a second line can arrive cut short in
    # one table and whole in the other: Samtse's Table 2.1 reads
    # "Sang-Ngag-" (the key the bindings above use) and its Table 2.2
    # "Sang-Ngag-Chhoeling". One that begins the other, where exactly one
    # does, is the same gewog, under Table 2.1's spelling.
    for name in sorted(set(found.gewogs) - set(read.gewogs)):
        stem = name.rstrip("-")
        partners = [other for other in set(read.gewogs) - set(found.gewogs)
                    if min(len(stem), len(other.rstrip("-"))) >= 4
                    and (other.startswith(stem) or stem.startswith(other.rstrip("-")))]
        if len(partners) == 1:
            found.gewogs[partners[0]] = found.gewogs.pop(name)
    # The gewogs must be Table 2.1's own, name for name. The towns reach no
    # shape and are held only through the closing row above: a town whose
    # label wraps differently in the two tables is not a reason to lose the
    # dzongkhag's gewogs.
    if set(found.gewogs) != set(read.gewogs):
        return None, (f"Table 2.2 does not name Table 2.1's gewogs: "
                      f"{sorted(set(read.gewogs) ^ set(found.gewogs))}")
    over = sorted(name for name, n in found.gewogs.items() if n > read.gewogs[name])
    if over or found.printed > read.printed:
        return None, (f"Table 2.2 counts more Bhutanese than Table 2.1 counts "
                      f"people in {over or ['the dzongkhag']}")
    # The same total in both is not a dzongkhag with no one but Bhutanese in
    # it: it is one table read twice. That is what this reader once did with
    # Lhuentse, Paro, Punakha and Trashigang, taking their Table 2.2 for
    # Table 2.1 (see :func:`table`); should it happen again, the dzongkhag
    # loses its citizenship rather than gaining a false 100% Bhutanese.
    if found.printed == read.printed:
        return None, (f"Table 2.2 prints the same total as Table 2.1, "
                      f"{found.printed:,} people, so the report gives no count of "
                      f"the non-Bhutanese here")
    return found, ""


def citizenship(bhutanese: int, everyone: int) -> dict[str, Any]:
    """The ethnicity fields for one row: Bhutanese and everyone else."""
    others = everyone - bhutanese
    counts = {label: n for label, n in (("Bhutanese", bhutanese),
                                        ("Non-Bhutanese", others)) if n}
    return {"ethnicity": shares(counts, total=everyone), "ethnicity_year": YEAR,
            "ethnicity_basis": "citizenship",
            "ethnicity_note": CITIZEN_NOTE.format(everyone=everyone,
                                                  bhutanese=bhutanese,
                                                  others=others)}


def citizen_cite(url: str) -> list[dict[str, Any]]:
    return [{"field": "ethnicity", "name": CITIZEN_SOURCE, "url": url,
             "license": LICENCE}]


# ---------------------------------------------------------------------------
# Median age: the annex's Tables A2.6 and A2.7
# ---------------------------------------------------------------------------
#
# Every dzongkhag report's annex prints two age tables from the same census:
#
# * **Table A2.6, population by age, sex and area** -- each single year from
#   0 to the oldest person, urban, rural and both areas, then "All Ages". The
#   dzongkhag's median is interpolated within the year holding the middle
#   person of both areas together.
# * **Table A2.7, population by age, sex, chiwog and gewog/town** -- under each
#   gewog's name its chiwogs, each a persons row and Male and Female rows,
#   in five-year groups to "75+", then the gewog's "All Chiwogs" rows. The
#   gewog's median is interpolated within the five-year group holding the
#   middle person: the census publishes nothing finer for a gewog.
#
# Both are held to Table 2.1, typeset apart from them: A2.6's All Ages to the
# dzongkhag's printed total, and each gewog's All Chiwogs to its Table 2.1
# row, persons, males and females.
#
# **The reports do not typeset these tables alike**, and the reader follows
# what each one prints rather than one house style:
#
# * Most print A2.7 on its side. The PDF's text then comes out a column at a
#   time, each word's letters reversed -- "latoT" over the figures, "47-07"
#   for 70-74, "sgowihC llA" for All Chiwogs -- so a page whose title reads
#   "7.2A" is read as the table it is: the age groups run down the page, each
#   persons, Male and Female series is a column, and a gewog's name stands in
#   capitals in a column of its own before its chiwogs. A gewog's All Chiwogs
#   column belongs to the nearest name to its left, or, where the page opens
#   in the middle of a gewog, to the last name of the page before. A name
#   printed in capitals that Table 2.1 does not know -- a town's -- closes the
#   gewog before it, so a block is never handed to the wrong gewog.
# * A2.6 leaves a cell blank here and there where it means 0 (Gasa's age 51
#   has no urban males), and Monggar sets two of its All Ages figures a
#   little below the rest of the row. Figures are placed under the header's
#   nine columns by their right edges, and a blank is counted 0 only where
#   the urban, rural and both-areas columns then still add up.
# * Chhukha's A2.6 prints a handful of rows, all of them past 80, whose male
#   and female figures do not make the total beside them, while every column
#   still adds up across the areas and down to All Ages. The median reads the
#   totals; the note says how many rows those are.
# * A2.6's All Ages must be the report's Table 2.1 total, and each gewog's
#   All Chiwogs its Table 2.1 row, persons, males and females, exactly. (An
#   allowance once let four reports' A2.6 and A2.7 exceed a Table 2.1 that
#   was short of them; that Table 2.1 was the reports' Table 2.2, misread --
#   see :func:`table` -- and the allowance has gone with the misreading.)
#
# A check that fails costs that unit its median, never the run: the record
# says why in place of a figure, and the log lists every one.
AGE_SINGLE = "Table A2.6"
AGE_GEWOG = "Table A2.7"
AGE_SOURCE = ("National Statistics Bureau of Bhutan, Population & Housing Census "
              "of Bhutan 2017, Tables A2.6 (population by age, sex and area) and "
              "A2.7 (population by age, sex, chiwog and gewog/town)")
GEWOG_GROUPS: list[tuple[int, int | None]] = [
    *((low, low + 4) for low in range(0, 75, 5)), (75, None)]
LATER_TABLE = re.compile(r"Table A(?:2\.(?:[89]|1\d)|[3-9]\.)")
DIGIT = re.compile(r"\d")
AGE_HEADER = ["Age", "Male", "Female", "Total", "Male", "Female", "Total",
              "Male", "Female", "Total"]
# Words of the running header and footer, printed upright on a page whose
# table is on its side: never a gewog's name, however they read backwards.
PAGE_FURNITURE = {"ANNEX", "2:", "Statistical", "Tables", "STATISTICAL", "TABLES",
                  "2017", "POPULATION", "AND", "HOUSING", "CENSUS", "OF", "BHUTAN",
                  "(PHCB)"}
SLOT_TOLERANCE = 14.0      # points between a figure's right edge and its column's
COLUMN_TOLERANCE = 3.0     # points between two figures of one column on its side


def fold(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def figures_of(words: list[str]) -> list[int] | None:
    """Every word a figure, or None: a data row has nothing else after its label."""
    if not words or not all(NUMBER.match(w) for w in words):
        return None
    return [int(w.replace(",", "")) for w in words]


def place(cells, slots: list[float]) -> list[int] | None:
    """Figures put under the header's columns by their right edges; a blank is 0.

    None where a figure falls under no column, or two under one -- a row this
    cannot place is not guessed at.
    """
    out: list[int | None] = [None] * len(slots)
    for _x0, x1, word in cells:
        if not NUMBER.match(word):
            return None
        at = min(range(len(slots)), key=lambda k: abs(slots[k] - x1))
        if abs(slots[at] - x1) > SLOT_TOLERANCE or out[at] is not None:
            return None
        out[at] = int(word.replace(",", ""))
    return [0 if v is None else v for v in out]


def group_index(label: str) -> int | None:
    """0..15 for "0-4" .. "75+", 16 for "Total"; None for anything else."""
    if label == "Total":
        return len(GEWOG_GROUPS)
    if label == "75+":
        return len(GEWOG_GROUPS) - 1
    match = re.fullmatch(r"(\d{1,2})-(\d{1,2})", label)
    if match and int(match[2]) == int(match[1]) + 4 and int(match[1]) % 5 == 0:
        index = int(match[1]) // 5
        return index if index < len(GEWOG_GROUPS) - 1 else None
    return None


def is_rotated_a27(rows) -> bool:
    """A page of Table A2.7 printed on its side: its title reads backwards."""
    return any(text[::-1].rstrip(":") == "A2.7" for cells in rows
               for _a, _b, text in cells)


def is_numberish(word: str) -> bool:
    """A figure as the PDF gives it on a page on its side: reversed, or a dash."""
    return bool(NUMBER.match(word[::-1])) or word in ("-", "–")


def value_of(word: str) -> int:
    return 0 if word in ("-", "–") else int(word[::-1].replace(",", ""))


def is_heading(word: str) -> bool:
    """A gewog's or town's name: capitals only, whatever punctuation is in it."""
    letters = [c for c in word if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


def rotated_page(rows, names: dict[str, str], carried: Any
                 ) -> tuple[dict[str, list[dict[str, list[int]]]], Any, list[str]]:
    """The gewogs whose All Chiwogs columns stand on one page printed on its side.

    ``carried`` is the gewog the page before ended under (a name, None for a
    heading Table 2.1 does not know, or the empty string for none yet).
    Returns, for each gewog read here, every All Chiwogs block found under its
    name (more than one only where a heading went unrecognised; the checks
    against Table 2.1 choose), the gewog the page ends under, and what was
    not understood.

    An age group's label and its figures can come out a line apart, and a
    row's figures in two lines. A line of figures and nothing else is joined
    to the age row beside it, but only where every figure stands under one of
    the Total row's columns and none collides with a figure the row has.
    """
    problems: list[str] = []
    kinds: list[list[Any]] = []          # per row: [kind, payload]
    for cells in rows:
        words = [t for _a, _b, t in cells]
        if any(w in PAGE_FURNITURE for w in words):
            kinds.append(["skip", None])
            continue
        found = None
        for k, (x0, _x1, word) in enumerate(cells):
            index = group_index(word[::-1])
            if index is None:
                continue
            rest = cells[k + 1:]
            if all(is_numberish(t) for _a, _b, t in rest):
                found = (index, x0, list(rest))
                break
        if found:
            kinds.append(["age", found])
        elif cells and all(is_numberish(t) for _a, _b, t in cells):
            kinds.append(["figures", list(cells)])
        else:
            kinds.append(["labels", cells])

    def neighbours(at: int):
        for near in (at - 1, at + 1, at - 2, at + 2):
            if 0 <= near < len(kinds):
                yield near

    total = len(GEWOG_GROUPS)
    total_rows = [k for k, (kind, p) in enumerate(kinds) if kind == "age" and p[0] == total]
    if len(total_rows) != 1:
        if any(kind == "age" for kind, _p in kinds):
            problems.append(f"{len(total_rows)} Total rows on a page of the table")
        return {}, carried, problems
    at_total = total_rows[0]
    if not kinds[at_total][1][2]:
        # The Total row's figures a line away from its label.
        for near in neighbours(at_total):
            kind, payload = kinds[near]
            if kind == "figures" and min(c[0] for c in payload) > kinds[at_total][1][1]:
                kinds[at_total][1][2].extend(payload)
                kinds[near] = ["joined", None]
                break
    columns = sorted(c[0] for c in kinds[at_total][1][2])
    if not columns:
        problems.append("a Total row with no figures")
        return {}, carried, problems

    def column_at(x0: float) -> int | None:
        near = min(range(len(columns)), key=lambda c: abs(columns[c] - x0))
        return near if abs(columns[near] - x0) <= COLUMN_TOLERANCE else None

    for at, (kind, payload) in enumerate(kinds):
        if kind != "figures" or any(column_at(c[0]) is None for c in payload):
            continue
        for near in neighbours(at):
            if kinds[near][0] != "age":
                continue
            _index, label_x, cells = kinds[near][1]
            mine = {column_at(c[0]) for c in cells}
            if min(c[0] for c in payload) > label_x and not (
                    {column_at(c[0]) for c in payload} & mine):
                cells.extend(payload)
                kinds[at] = ["joined", None]
                break
    series: dict[int, list[tuple[float, int]]] = {}
    labels: list[tuple[float, str, int]] = []
    for at, (kind, payload) in enumerate(kinds):
        if kind == "age":
            index, _label_x, cells = payload
            if index in series:
                problems.append(f"age group {index} printed twice")
                return {}, carried, problems
            series[index] = [(x0, value_of(t)) for x0, _x1, t in cells]
        elif kind in ("labels", "figures"):
            labels += [(x0, word[::-1], at) for x0, _x1, word in payload]
    if set(series) != set(range(total + 1)):
        problems.append(f"age groups {sorted(series)} on a page of the table")
        return {}, carried, problems
    table: dict[int, list[int | None]] = {}    # column -> its 17 figures
    for index, cells in series.items():
        for x0, value in cells:
            near = column_at(x0)
            if near is None:
                problems.append(f"a figure at x={x0:.0f} under no column")
                return {}, carried, problems
            column = table.setdefault(near, [None] * (total + 1))
            if column[index] is not None:
                problems.append(f"two figures for age group {index} at x={x0:.0f}")
                return {}, carried, problems
            column[index] = value
    filled = {c: [0 if v is None else v for v in values] for c, values in table.items()}

    # Names in capitals in a column with no figures: the gewogs' and towns'.
    heads: dict[float, list[tuple[int, str]]] = {}
    for x0, word, at in labels:
        if column_at(x0) is None and is_heading(word):
            key = next((k for k in heads if abs(k - x0) <= 1.5), x0)
            heads.setdefault(key, []).append((at, word))
    headings: list[tuple[float, Any, str]] = []
    for x0, parts in sorted(heads.items()):
        upward = " ".join(w for _at, w in sorted(parts, reverse=True))
        downward = " ".join(w for _at, w in sorted(parts))
        name = names.get(fold(upward)) or names.get(fold(downward))
        headings.append((x0, name, upward))
    # A column labelled "All" is a gewog's All Chiwogs, or a town's All
    # Local Areas; the word "Chiwogs" beside it is sometimes lost.
    alls = sorted({column_at(x0) for x0, word, _at in labels
                   if word == "All" and column_at(x0) is not None})
    found: dict[str, list[dict[str, list[int]]]] = {}
    for col in alls:
        if any(word in ("Local", "Areas") and column_at(x0) == col
               for x0, word, _at in labels):
            continue
        left = [h for h in headings if h[0] < columns[col]]
        owner = left[-1][1] if left else carried
        if col + 2 >= len(columns):
            problems.append("an All Chiwogs column with no Male and Female beside it")
            continue
        sexes = {word for x0, word, _at in labels
                 if column_at(x0) in (col + 1, col + 2)}
        if sexes and not {"Male", "Female"} <= sexes:
            problems.append(f"the columns after All Chiwogs are labelled {sorted(sexes)}")
            continue
        block = {"persons": filled.get(col), "male": filled.get(col + 1),
                 "female": filled.get(col + 2)}
        if not owner:
            # Kept, nameless: Table 2.1's own totals may still say whose it is.
            heading = left[-1][2] if left else "no heading"
            problems.append(f"an All Chiwogs column under {heading!r}")
            found.setdefault("", []).append(block)
            continue
        found.setdefault(owner, []).append(block)
    # A heading Table 2.1 does not name -- a town's -- is only a problem where
    # it owns an All Chiwogs column, and that is reported above.
    ending = headings[-1][1] if headings else carried
    return found, ending, problems


def annex_ages(pages, gewog_names) -> dict[str, Any]:
    """Tables A2.6 and A2.7 of one dzongkhag report.

    Returns {"single": {age: (urban m, f, t, rural m, f, t, both m, f, t)},
    "all_ages": (...) or None, "gewogs": {name: {"persons": [...],
    "male": [...], "female": [...]}}, "placed": [ages read by placement],
    "rotated": pages read on their side, "problems": [...]} -- each gewog's
    lists the sixteen groups and then the total, under Table 2.1's spelling of
    the gewog's name.
    """
    names = {fold(n): n for n in gewog_names}
    single: dict[int, tuple[int, ...]] = {}
    all_ages: tuple[int, ...] | None = None
    gewogs: dict[str, dict[str, list[int]]] = {}
    placed: list[int] = []
    problems: list[str] = []
    alternates: dict[str, list[dict[str, list[int]]]] = {}
    nameless: list[dict[str, list[int]]] = []
    rotated = 0
    mode: str | None = None
    current: str | None = None
    pending: str | None = None              # the gewog whose Male/Female rows follow
    slots: list[float] | None = None
    carried: Any = ""
    partial_all = None                      # an All Ages row missing figures
    orphan = None                           # the row before: figures and nothing else
    for rows in pages:
        if is_rotated_a27(rows):
            rotated += 1
            mode = "rotated"
            found, carried, trouble = rotated_page(rows, names, carried)
            problems += [f"Table A2.7 on its side: {p}" for p in trouble]
            for name, blocks in found.items():
                for block in blocks:
                    if not name:
                        nameless.append(block)
                    elif name in gewogs:
                        problems.append(f"Table A2.7 on its side: more than one All "
                                        f"Chiwogs block under {name}; Table 2.1 "
                                        "decides which")
                        alternates.setdefault(name, []).append(block)
                    else:
                        gewogs[name] = block
            continue
        if mode == "rotated":
            mode = None
        for cells in rows:
            words = [t for _a, _b, t in cells]
            line = " ".join(words)
            if AGE_SINGLE in line:
                mode = "single"
                continue
            if AGE_GEWOG in line:
                # The title is printed again at the top of every page the
                # table runs onto, and a gewog's chiwogs run across pages:
                # Bumthang's Ura starts on one page and has its All Chiwogs
                # rows on the next. Only the first title opens the table;
                # a repeat keeps the gewog it interrupts.
                if mode != "gewog":
                    mode, current, pending = "gewog", None, None
                continue
            if LATER_TABLE.search(line):
                mode = None
                continue
            if mode == "single":
                if words == AGE_HEADER:
                    slots = [x1 for _x0, x1, _t in cells[1:]]
                    continue
                # Figures and nothing else, the first of them under a figure
                # column: an age row's label is a figure too, under Age.
                is_orphan = bool(figures_of(words)) and bool(slots) and min(
                    abs(s - cells[0][1]) for s in slots) <= SLOT_TOLERANCE
                if words[:2] == ["All", "Ages"]:
                    found = figures_of(words[2:])
                    if found and len(found) == 9:
                        all_ages = tuple(found)
                    elif orphan is not None and slots:
                        merged = place(sorted([*cells[2:], *orphan], key=lambda c: c[1]),
                                       slots)
                        all_ages = tuple(merged) if merged else all_ages
                    else:
                        partial_all = cells[2:]
                    orphan = None
                    continue
                if partial_all is not None and is_orphan and slots:
                    merged = place(sorted([*partial_all, *cells], key=lambda c: c[1]),
                                   slots)
                    all_ages = tuple(merged) if merged else all_ages
                    partial_all = None
                    continue
                orphan = cells if is_orphan else None
                if re.fullmatch(r"\d{1,3}", words[0]) and len(words) > 1:
                    found = figures_of(words[1:])
                    if found and len(found) != 9 and slots:
                        found = place(cells[1:], slots)
                        if found:
                            placed.append(int(words[0]))
                    if found and len(found) == 9:
                        age = int(words[0])
                        if age in single:
                            problems.append(f"Table A2.6 prints age {age} twice")
                        single[age] = tuple(found)
                continue
            if mode != "gewog":
                continue
            if not DIGIT.search(line) and fold(line) in names:
                current, pending = names[fold(line)], None
                continue
            if not DIGIT.search(line) and line.isupper():
                # A town's heading, or any other the census prints in
                # capitals: whatever follows is not the last gewog's.
                current, pending = None, None
                continue
            if words[:2] == ["All", "Chiwogs"] and current:
                found = figures_of(words[2:])
                if not found or len(found) != len(GEWOG_GROUPS) + 1:
                    problems.append(f"Table A2.7 {current}'s All Chiwogs row has {found}")
                    current = None
                    continue
                if current in gewogs:
                    problems.append(f"Table A2.7 prints {current} twice")
                    continue
                gewogs[current] = {"persons": found}
                pending = current
                continue
            if pending and words[0] in ("Male", "Female"):
                found = figures_of(words[1:])
                if not found or len(found) != len(GEWOG_GROUPS) + 1:
                    problems.append(f"Table A2.7 {pending}'s {words[0]} row has {found}")
                    pending = None
                    continue
                gewogs[pending][words[0].lower()] = found
                if words[0] == "Female":
                    pending = None
    return {"single": single, "all_ages": all_ages, "gewogs": gewogs,
            "alternates": alternates, "nameless": nameless, "placed": placed,
            "rotated": rotated, "problems": problems}


def single_outcome(dzongkhag: str, annex: dict[str, Any], read: "Read"
                   ) -> tuple[str | None, str]:
    """Table A2.6 against itself and Table 2.1: (reason it fails, note to add)."""
    single, all_ages = annex["single"], annex["all_ages"]
    if all_ages is None or not single:
        return ("this reader found no All Ages row or no single years in the "
                "report's Table A2.6", "")
    missing = sorted(set(range(0, max(single) + 1)) - set(single))
    if missing:
        return (f"Table A2.6 as read has no row for age(s) "
                f"{', '.join(map(str, missing))}", "")
    short: list[int] = []
    for age, row in sorted(single.items()):
        for i in range(3):
            if row[i] + row[3 + i] != row[6 + i]:
                return (f"Table A2.6's urban and rural figures for age {age} do not "
                        "make its both-areas figure", "")
        if any(row[s] + row[s + 1] != row[s + 2] for s in (0, 3, 6)):
            short.append(age)
    for i in range(9):
        summed = sum(row[i] for row in single.values())
        if summed != all_ages[i]:
            return (f"Table A2.6's single years add up to {summed:,} in its column "
                    f"{i + 1}, against the {all_ages[i]:,} its All Ages row prints", "")
    note = ""
    if short:
        note += (f" In {len(short)} of the table's rows (ages "
                 f"{', '.join(map(str, short))}) the male and female figures do "
                 "not make the total printed beside them, while every column adds "
                 "up across the areas and down to All Ages; the median reads the "
                 "totals.")
    if all_ages[8] != read.printed:
        return (f"Table A2.6 counts {all_ages[8]:,} people and the report's "
                f"Table 2.1 {read.printed:,}", "")
    return None, note


def gewog_outcome(name: str, rows: dict[str, list[int]] | None, read: "Read"
                  ) -> str | None:
    """A gewog's All Chiwogs block against itself and its Table 2.1 row."""
    if rows is None:
        return ("this reader found no All Chiwogs block under the gewog's name in "
                "the report's Table A2.7")
    if any(rows.get(k) is None for k in ("persons", "male", "female")):
        return "Table A2.7 as read lacks the gewog's persons, male or female figures"
    for label, values in rows.items():
        if sum(values[:-1]) != values[-1]:
            return (f"Table A2.7's {label} age groups for the gewog add up to "
                    f"{sum(values[:-1]):,}, against the {values[-1]:,} it prints as "
                    "their total")
    for i, n in enumerate(rows["persons"]):
        if rows["male"][i] + rows["female"][i] != n:
            return ("Table A2.7's male and female figures for the gewog do not "
                    "make its persons in every age group")
    got = (rows["persons"][-1], rows["male"][-1], rows["female"][-1])
    want = (read.gewogs[name], *read.sexes[name])
    if got == want:
        return None
    if got[0] != want[0]:
        return (f"Table A2.7 counts {got[0]:,} people in the gewog and Table 2.1 "
                f"{want[0]:,}")
    return (f"Table A2.7 counts {got[1]:,} males and {got[2]:,} females in the gewog, "
            f"Table 2.1 {want[1]:,} and {want[2]:,}")


def choose_gewog(name: str, annex: dict[str, Any], read: "Read"
                 ) -> tuple[dict[str, list[int]] | None, str | None, str]:
    """The gewog's block that passes every check: (block, reason, note).

    More than one block stands under a name only where a heading on a page
    printed on its side went unrecognised; the one whose totals and sexes are
    the gewog's Table 2.1 row is the gewog's, and if none is, none is used.
    """
    blocks = [annex["gewogs"].get(name), *annex.get("alternates", {}).get(name, [])]
    reason = None
    # A block found under no name Table 2.1 knows -- its heading spelt
    # otherwise ("GASE TSHOGOM" for Gase Tshogongm), or lost -- is this
    # gewog's only where its persons, males and females are exactly this
    # gewog's Table 2.1 row, and no other unclaimed block's are.
    pool = [*annex.get("nameless", []),
            *(b for other, bs in annex.get("alternates", {}).items()
              if other != name for b in bs)]
    want = (read.gewogs[name], *read.sexes[name])
    exact = [b for b in pool if b.get("persons") and b.get("male") and b.get("female")
             and (b["persons"][-1], b["male"][-1], b["female"][-1]) == want]
    for block in [*blocks, *(exact if len(exact) == 1 else [])]:
        why = gewog_outcome(name, block, read)
        if why is None:
            return block, None, ""
        reason = reason or why
    return None, reason, ""


def annex_debug(pages, gewog_names, *, limit: int = 90) -> list[str]:
    """What the annex reader sees, for working out a report's layout.

    Every annex title line and the rows just after it; in Table A2.6 every
    row that is not an age row of nine figures adding up; in Table A2.7
    every row with no figure in it (the headings, marked where Table 2.1
    knows the name) and every row opening "All" or "Total". A page printed
    on its side shows its labels, read the right way round. Words carry
    their left edge, so a figure printed apart from its row shows.
    """
    names = {fold(n): n for n in gewog_names}
    out: list[str] = []
    mode: str | None = None
    after_title = 0
    carried: Any = ""
    for number, rows in enumerate(pages, 1):
        if is_rotated_a27(rows):
            found, carried, trouble = rotated_page(rows, names, carried)
            out.append(f"p{number} ON ITS SIDE: "
                       f"{sorted((n, len(b)) for n, b in found.items())}; ends under "
                       f"{carried!r}; {trouble}")
            # The names in capitals, and where All Chiwogs stands.
            marks = [f"{t[::-1]}@{a:.0f}" for cells in rows for a, _b, t in cells
                     if is_heading(t[::-1]) or t[::-1] in ("All", "Chiwogs")]
            out.append(f"p{number}   names " + " ".join(marks)[:400])
            continue
        for cells in rows:
            if len(out) >= limit:
                return out
            words = [t for _a, _b, t in cells]
            line = " ".join(words)
            placed = " ".join(f"{t}@{a:.0f}" for a, _b, t in cells)
            if re.search(r"Table A\s?\d", line):
                mode = ("single" if AGE_SINGLE in line
                        else "gewog" if AGE_GEWOG in line else None)
                out.append(f"p{number} TITLE {line[:160]}")
                after_title = 5 if mode else 0
                continue
            if mode is None:
                continue
            if after_title:
                out.append(f"p{number}   + {placed[:260]}")
                after_title -= 1
                continue
            if mode == "single":
                found = figures_of(words[1:])
                good = (re.fullmatch(r"\d{1,3}", words[0]) and found
                        and len(found) == 9
                        and all(found[s] + found[s + 1] == found[s + 2]
                                for s in (0, 3, 6)))
                if not good:
                    out.append(f"p{number}   A2.6? {placed[:260]}")
                continue
            if not DIGIT.search(line):
                known = "  [Table 2.1 name]" if fold(line) in names else ""
                out.append(f"p{number}   HEAD {line[:80]}{known}")
            elif words[0] in ("All", "Total", "TOTAL", "ALL"):
                out.append(f"p{number}   ROW {placed[:200]}")
    return out


def dzongkhag_median(annex: dict[str, Any], note: str = "") -> dict[str, Any]:
    from .south_asia_common import median_single

    people = annex["all_ages"][8]
    median = median_single({age: row[8] for age, row in annex["single"].items()})
    if median is None:
        return {}
    return {
        "median_age": measure(median, unit="years", year=YEAR, source=AGE_SOURCE),
        "median_age_note": (
            f"2017 census, Table A2.6: the median of the single years of age of "
            f"all {people:,} people in the dzongkhag, towns included, "
            "interpolated within the year that holds the middle person." + note),
    }


def gewog_median(rows: dict[str, list[int]], note: str = "") -> dict[str, Any]:
    from .south_asia_common import median_grouped

    groups = [(low, high, n) for (low, high), n in zip(GEWOG_GROUPS, rows["persons"])]
    median = median_grouped(groups)
    if median is None:
        return {}
    return {
        "median_age": measure(median, unit="years", year=YEAR, source=AGE_SOURCE),
        "median_age_note": (
            f"2017 census, Table A2.7: the median of the gewog's "
            f"{rows['persons'][-1]:,} people, interpolated within the five-year "
            "group that holds the middle person; the census publishes nothing "
            "finer for a gewog. As with the head count, the gewog's own people, "
            "towns apart." + note),
    }


def age_gap(reason: str) -> dict[str, Any]:
    """A median this run declined, with the reason in place of the figure."""
    return {"median_age": gap(NOT_AVAILABLE, (
        "2017 census: the report's annex has the age table, but " + reason
        + "; a median from figures that do not reconcile would be this map's "
          "arithmetic rather than the census's."))}


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
    ap.add_argument("--annex-debug", default="",
                    help="comma-separated dzongkhags (dots for spaces): print "
                         "what the annex age reader sees, and write nothing")
    args = ap.parse_args()

    if args.annex_debug:
        for dzongkhag in args.annex_debug.replace(".", " ").split(","):
            blob = fetch(f"{BASE}/{DZONGKHAGS[dzongkhag]}")
            read = table(blob, dzongkhag, False)
            log(f"== {dzongkhag}: Table 2.1 has {len(read.gewogs)} gewogs, "
                f"printed total {read.printed:,}")
            for line in annex_debug(words_by_row(blob), read.gewogs):
                log("  " + line)
            annex = annex_ages(words_by_row(blob), read.gewogs)
            for name, rows in sorted(annex["gewogs"].items()):
                why = gewog_outcome(name, rows, read)
                log(f"  -- {name}: {why or 'reads'}")
                for label, values in rows.items():
                    log(f"     {label:8} {values}  groups sum {sum(values[:-1]):,}")
                if all(rows.get(k) for k in ("persons", "male", "female")):
                    off = [i for i in range(len(GEWOG_GROUPS) + 1)
                           if rows["male"][i] + rows["female"][i] != rows["persons"][i]]
                    log(f"     male + female != persons at {off}")
        return 0

    log("bhutan: National Statistics Bureau, PHCB 2017 Table 2.1")
    records: list[dict[str, Any]] = []
    absent: list[str] = []
    refused: list[str] = []
    national = 0
    males = females = 0
    urban_total = 0
    wanted = {k: v for k, v in DZONGKHAGS.items()
              if not args.only or k == args.only}

    # Two passes: every report is read first, because one check on a report's
    # A2.6 needs all twenty of them (see "Median age" above).
    reports = []
    for dzongkhag, filename in wanted.items():
        url = f"{BASE}/{filename}"
        try:
            blob = fetch(url)
        except Exception as err:                        # noqa: BLE001
            absent.append(f"{dzongkhag}: {type(err).__name__} {str(err)[:60]}")
            continue
        read = table(blob, dzongkhag, args.debug)
        annex = annex_ages(words_by_row(blob), read.gewogs)
        citizen, why = citizens(blob, dzongkhag, read, args.debug)
        reports.append((dzongkhag, url, read, annex, citizen, why))
    totals_a26 = [annex["all_ages"][8] if annex["all_ages"] else None
                  for _d, _u, _r, annex, _c, _w in reports]
    national_a26 = (sum(totals_a26) if len(reports) == len(DZONGKHAGS)
                    and None not in totals_a26 else None)
    log("  the twenty reports' Table A2.6 totals come to "
        + (f"{national_a26:,}" if national_a26 is not None else "no whole figure")
        + f", against the national report's {NATIONAL_ANALYSED:,}")
    declined: list[str] = []
    medians = {"dzongkhag": 0, "gewog": 0, "gewogs": 0}
    bhutanese_total = 0
    no_citizenship: list[str] = []

    for dzongkhag, url, read, annex, citizen, why in reports:
        gewogs, towns, printed = read.gewogs, read.towns, read.printed
        national += printed
        urban_total += sum(towns.values())
        log(f"  {dzongkhag}: {len(gewogs)} gewogs, {len(towns)} town(s), "
            f"{printed:,} people")
        if citizen is None:
            no_citizenship.append(f"{dzongkhag}: {why}")
            gap_note = (f"Citizenship is not written for {dzongkhag}: {why}, so "
                        f"the report's count of Bhutanese by gewog could not be "
                        f"held to its Table 2.1. Bhutan's census does not ask "
                        f"ethnicity.")
            dzongkhag_eth: dict[str, Any] = {"ethnicity": gap(NOT_AVAILABLE, gap_note)}
        else:
            bhutanese_total += citizen.printed
            log(f"    Table 2.2: {citizen.printed:,} Bhutanese of {printed:,} -- "
                f"{printed - citizen.printed:,} non-Bhutanese")
            dzongkhag_eth = citizenship(citizen.printed, printed)
        reason, extra = single_outcome(dzongkhag, annex, read)
        if reason:
            declined.append(f"{dzongkhag}: {reason}")
            dzongkhag_age = age_gap(reason)
        else:
            dzongkhag_age = dzongkhag_median(annex, extra)
            medians["dzongkhag"] += 1
        chosen = {name: choose_gewog(name, annex, read) for name in gewogs}
        outcomes = {name: why for name, (_block, why, _note) in chosen.items()}
        for name, why in sorted(outcomes.items()):
            if why:
                declined.append(f"{dzongkhag}/{name}: {why}")
        read_ok = sum(1 for why in outcomes.values() if not why)
        medians["gewog"] += read_ok
        medians["gewogs"] += len(gewogs)
        log("    Tables A2.6 and A2.7"
            + (f" ({annex['rotated']} page(s) of A2.7 on their side)"
               if annex["rotated"] else "")
            + f": the dzongkhag's median {'declined' if reason else 'read'}; "
            f"{read_ok} of {len(gewogs)} gewogs' medians read"
            + (f"; ages placed under their columns: {annex['placed']}"
               if annex["placed"] else ""))
        for problem in annex["problems"]:
            log(f"      {problem}")

        # A citation only beside a median: one beside its gap would say a
        # source stands behind a figure nobody published.
        def age_cite(fields: dict[str, Any]) -> list[dict[str, Any]]:
            if "value" not in (fields.get("median_age") or {}):
                return []
            return [{"field": "median_age", "name": AGE_SOURCE, "url": url,
                     "license": LICENCE}]

        # The sex ratio is read from the same table and the same row as the
        # population, so it is cited the same way and separately: a reader
        # asking where a figure came from asks it of one field at a time. And
        # only where there is a figure: a ratio this adapter refused because
        # the row did not add up is a gap, and a citation beside a gap tells
        # the reader a source stands behind a number nobody published.
        def cite(ratio: dict[str, Any]) -> list[dict[str, Any]]:
            fields = ["population"] + (["sex_ratio"] if "value" in ratio else [])
            return [{"field": field, "name": SOURCE, "url": url,
                     "license": LICENCE} for field in fields]
        note = POPULATION_NOTE
        if towns:
            note += (" Of these, " + f"{sum(towns.values()):,}"
                     + " are counted in "
                     + ", ".join(sorted(towns))
                     + ", which the boundary file does not draw, so the "
                       "gewogs below come to that much less than this row.")
        if read.printed_sexes:
            male, female = read.printed_sexes
            ratio = sex_ratio(male, female, printed, dzongkhag)
            # Counted into the national tally whether or not the ratio was
            # taken: these are the office's own two columns, and the tally is
            # a check on the reading rather than a figure anyone is shown.
            males += male
            females += female
            if "value" not in ratio:
                refused.append(dzongkhag)
        else:
            # Only reachable where the closing row was never found and the
            # total came from the report's own sentence, which counts persons
            # and does not split them.
            ratio = gap(NOT_AVAILABLE,
                        "Table 2.1 in this report has no closing row this "
                        "reader can see; the total beside it is the one the "
                        "report's own text states, and that sentence gives "
                        "no split between males and females.")
            log(f"    {dzongkhag}: no sex ratio -- the total came from the "
                f"report's text, which gives no split by sex")
            refused.append(dzongkhag)
        records.append(record(
            f"BTN-{dzongkhag.lower().replace(' ', '-')}", dzongkhag,
            level="admin1", parent="BTN", country="BTN",
            aliases=list(DZONGKHAG_ALIASES.get(dzongkhag, ())),
            population=measure(printed, year=YEAR, source=SOURCE),
            population_note=note,
            sex_ratio=ratio,
            sex_ratio_note=SEX_RATIO_NOTE if "value" in ratio else None,
            sources=cite(ratio) + age_cite(dzongkhag_age)
            + (citizen_cite(url) if citizen is not None else []),
            **dzongkhag_age, **dzongkhag_eth))
        for name, people in sorted(gewogs.items()):
            male, female = read.sexes[name]
            ratio = sex_ratio(male, female, people, f"{dzongkhag}/{name}")
            if "value" not in ratio:
                refused.append(f"{dzongkhag}/{name}")
            block, why, gewog_note = chosen[name]
            gewog_age = age_gap(why) if why else gewog_median(block, gewog_note)
            where = (name, dzongkhag)
            bound = SHAPE_BOUND.get(where)
            note = POPULATION_NOTE + GEWOG_NOTE
            if bound:
                note += RENAMED_NOTE.format(label=SHAPE_LABELS[bound])
                log(f"    {dzongkhag}/{name} -> shape {bound} "
                    f"(labelled {SHAPE_LABELS[bound]!r})")
            elif where in GEWOG_BY_POINT:
                label = GEWOG_BY_POINT[where][0]
                template = (CLOSURE_NOTE if where in BY_CLOSURE
                            else RENAMED_NOTE)
                note += template.format(label=label, dzongkhag=dzongkhag)
                log(f"    {dzongkhag}/{name} -> labelled {label!r}"
                    + ("  (by the two lists closing, not by a point)"
                       if where in BY_CLOSURE else ""))
            records.append(record(
                f"BTN-{dzongkhag.lower().replace(' ', '-')}-"
                f"{name.lower().replace(' ', '-')}",
                name, level="admin2", parent="BTN", country="BTN",
                aliases=list(GEWOG_ALIASES.get(name, ()))
                + list(GEWOG_BY_POINT.get(where, ())),
                parent_name=dzongkhag,
                parent_aliases=list(DZONGKHAG_ALIASES.get(dzongkhag, ())),
                shape_id=bound,
                match_by="shape_id" if bound else None,
                population=measure(people, year=YEAR, source=SOURCE),
                population_note=note,
                sex_ratio=ratio,
                sex_ratio_note=SEX_RATIO_NOTE if "value" in ratio else None,
                sources=cite(ratio) + age_cite(gewog_age)
                + (citizen_cite(url) if citizen is not None else []),
                **gewog_age,
                **(citizenship(citizen.gewogs[name], people) if citizen is not None
                   else {"ethnicity": dzongkhag_eth["ethnicity"]})))

    for line in no_citizenship:
        log(f"  CITIZENSHIP NOT READ -- {line}")
    log(f"  Table 2.2 read for {len(reports) - len(no_citizenship)} of {len(reports)} "
        f"dzongkhags: {bhutanese_total:,} Bhutanese")
    for line in declined:
        log(f"  MEDIAN DECLINED -- {line}")
    log(f"  medians read: {medians['dzongkhag']} of {len(reports)} dzongkhags and "
        f"{medians['gewog']} of {medians['gewogs']} gewogs; each one declined "
        "says why in its record")
    if reports and not medians["gewog"]:
        raise SystemExit("bhutan: not one gewog's median was read; the annex "
                         "reader has lost the tables, not the census its figures")
    for line in absent:
        log(f"  NOT READ -- {line}")
    if absent:
        raise SystemExit(
            f"bhutan: {len(absent)} of {len(wanted)} dzongkhag reports were "
            f"not read; refusing to write a partial Bhutan")

    if not args.only:
        # A binding is a claim about a specific gewog of a specific dzongkhag,
        # so a key naming a pair this census does not print is a mistake and
        # not a near miss -- the same rule build_entities keeps for a shape id
        # it cannot find. Silently, it would mean a gewog the tables think is
        # handled and which is in fact reaching no shape at all.
        read_pairs = {(r["name"], r.get("parent_name")) for r in records
                      if r["level"] == "admin2"}
        stale = sorted((set(GEWOG_BY_POINT) | set(SHAPE_BOUND)) - read_pairs)
        if stale:
            raise SystemExit(
                "bhutan: these bindings name a gewog and dzongkhag the "
                "census does not print together: "
                + "; ".join(f"{n} ({d})" for n, d in stale))

    if not args.only:
        log(f"  the twenty dzongkhags come to {national:,}, against the "
            f"{NATIONAL_ANALYSED:,} the national report analyses and the "
            f"{NATIONAL_FOUND:,} it says were found once the "
            f"{NATIONAL_FOUND - NATIONAL_ANALYSED:,} non-Bhutanese and "
            f"tourists in hotels, of whom no details were taken, are added")
        # Held to the national report's own figures, and enforced: the twenty
        # Table 2.1s make the national 727,145, and a sum that does not is a
        # report misread -- which is how four dzongkhags once came to be
        # carried at their Bhutanese population alone (see table()). The
        # sexes catch the other kind of error, a column read one place to the
        # left, which would put them out while every total still added up.
        if national != NATIONAL_ANALYSED:
            raise SystemExit(
                f"bhutan: the twenty reports' Table 2.1 totals come to "
                f"{national:,}, not the national report's "
                f"{NATIONAL_ANALYSED:,}: a report has been misread")
        log(f"  their sexes come to {males:,} male and {females:,} female, "
            f"against the {NATIONAL_MALE:,} and {NATIONAL_FEMALE:,} the "
            f"national report prints for the country -- "
            f"{males - NATIONAL_MALE:+,} and {females - NATIONAL_FEMALE:+,}.")
        if all(r.printed_sexes for _d, _u, r, _a, _c, _w in reports) and \
                (males, females) != (NATIONAL_MALE, NATIONAL_FEMALE):
            raise SystemExit(
                f"bhutan: the twenty reports' Table 2.1 sexes come to "
                f"{males:,} and {females:,}, not the national report's "
                f"{NATIONAL_MALE:,} and {NATIONAL_FEMALE:,}")
        if refused:
            log(f"  {len(refused)} row(s) publish no sex ratio because the "
                f"published halves do not reach the published total: "
                + ", ".join(refused))

    out = args.out or PROCESSED / "bhutan_gewog.json"
    write_json(out, records)
    gewogs = sum(1 for r in records if r["level"] == "admin2")
    log(f"  {len(records) - gewogs} dzongkhags and {gewogs} gewogs, "
        f"{urban_total:,} people in towns with no shape")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
