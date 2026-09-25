#!/usr/bin/env python3
"""Iran: language by province and shahrestan, from the Atlas of the Languages
of Iran's settlement files.

**What ALI is, and what it is not.** The Atlas of the Languages of Iran is a
research atlas edited by Erik Anonby, Mortaza Taheri-Ardali et al. and
published by the Geomatics and Cartographic Research Centre at Carleton
University. Province by province, a named author or team records, for each
settlement, which languages are spoken there and in what proportion --
"Central Kurdish 100%", "Turkic 80%; Southern Kurdish 20%". Those proportions
are **field estimates by a linguist**, not answers anybody was asked. Iran's
census does not ask language at all, which is what ``NOT_COLLECTED_POLICY``
says in common.py and which stays true whatever this file writes. So every
record here is an ``estimate`` -- a gap that carries a figure -- and the note
on each one says in as many words that nothing was counted.

Each province is a **separately authored, separately dated module**. The
twelve read here run from 2015 to 2024, so a reader looking at Hormozgān is
looking at a picture ten years older than Khuzestān's. One date across the
twelve would hide that, and there is no date for "ALI" as a whole: the year,
the authors and the URL travel with the province, from
``data/raw/iran/ali_citations.json``. The row-level
``language_distribution_source`` -- "Masoud Mohammadirad, field notes 2015" --
is the evidence for that row and is named in the note beside the module's own
year, because publication and fieldwork are different events and Kordestān's
are a year apart.

**More provinces are coming.** Iran has 31; twelve are here. Nothing in this
module is a list of twelve: it globs ``Language_Distribution_*.csv`` in
``data/raw/iran`` and takes the province from the file's own
``province_roman`` column, so a thirteenth file is read by dropping it in that
directory and adding its citation to the JSON beside it. A file whose
province matches no boundary shape, or whose province has no citation, is
skipped with the reason logged -- never guessed at.

**The licence row.** Row 1 of every file fills ``Attribution`` and nothing
else, with the string in ``LICENCE`` below. It is carried verbatim onto every
record's source entry and is reproduced in docs/SOURCES.md. A file whose first
row is not that string is not read: the licence is the condition of use, and a
file that does not state it is not the file this module was written for.

**The nesting rule, measured rather than assumed.** One table holds six kinds
of row -- a province row, shahrestan rows, bakhsh rows, city rows, dehestan
rows and settlement rows -- distinguished by which name columns are filled,
and they are *nested*, not siblings. Adding every row in Kordestān's file
gives 6,476,710 people in a province of 1,493,645: the province row, the
shahrestan rows and the bakhsh rows each account for the whole province again
(1,493,645 apiece), and the dehestan rows account for its rural half a second
time.

Measured across the nine files that fill their name columns (12,852 rows):
every one of the 11,900 rows carrying a ``language_distribution_estimate`` is
a settlement row or a city row, and not one of the 948 province, shahrestan,
bakhsh or dehestan rows carries one. So the rule this module uses is:

    **a row contributes if and only if it carries a language estimate.**

It needs no name columns, which matters, because three of the twelve files
(Khuzestān, Lorestān, Kohgiluyeh va Boyer Ahmad) and part of a fourth
(Gilān) arrive with every column from ``shahrestan_roman`` down left blank.
The rule reaches their settlements as well; what it cannot do there is say
which shahrestan a settlement is in, so those provinces get a province record
and no county records at all. A weaker rule was tried first and rejected --
"a row with coordinates, a local name or a language" -- because it swept in 20
dehestan rows carrying a local name of their own, 248,696 people who are
already counted in the settlements below them.

**The weighting rule, and what is lost to it.** A composition of a province is
its settlements' compositions weighted by how many people live in each, and
the file gives two census columns, 2011 and 2016, either of which may be
blank. The rule is: **weight by ``population_2016_census`` where there is one,
by ``population_2011_census`` otherwise.** It was tested rather than assumed.
Only Gilān's module carries 2016 figures at all (2,411 rows of 18,343), so the
two vintages meet in one province, and there the choice is immaterial and the
fallback is what reaches the most people: weighting Gilān on 2011 alone moves
no group by more than 0.4 points and covers 1,814,553 people, on 2016 alone
1,820,106, and on the rule as written 1,850,164.

A settlement with a language and **no population in either year** cannot be
weighted, and this module does not invent a weight for it: it is excluded, and
the unit's note says how many were excluded. 2,809 of the 21,152 language rows
are in that position. Their own share of the population is unmeasurable -- the
figure that would measure it is the one that is missing -- so what the note
reports instead is the coverage the weighted rows do reach.

**Coverage, and when a unit is a gap instead of a number.** For each unit the
weighted population is compared with the unit's own total, which is taken, in
this order: the file's own aggregate row for that unit (the province row, or
the shahrestan row); failing that, the population this map already holds for
the shape, which is Wikidata's 2016 figure; failing that, the sum of the
unit's own settlement and city rows -- which agrees with the aggregate row
within 2% in 83 of the 91 shahrestans that have both, and which is last
because in a file with no name columns it can only reach the rows already in
the numerator. A unit with no total at all gets no record: a composition
whose coverage cannot be measured is a claim about a population nobody has
counted.

Below ``MIN_COVERAGE`` the unit is left empty and the reason is logged. The
threshold sits in an empty band: measured, ten of the twelve provinces come
out between 98.6% and 101.3%, Gilān at 73.1% (the city of Rasht, a quarter of
the province, publishes an estimate that sums to 90% and is refused below),
and Kermānshāh at 18.6%, its module covering five of the province's fourteen
shahrestans. Nothing lands between 18.6% and 73.1%.

**Refusing a share string.** ``language_distribution_estimate`` parses as
``<language> <number>%`` joined by semicolons, and 21,137 of the 21,152 rows
parse and sum to exactly 100. The rest are not guessed at. Seven sum to
between 100.001 and 100.5 -- a 0.04% Armenian presence added on top of a
partition that already came to 100 -- and are accepted and normalised; eight
sum to between 80 and 110 and are refused outright, with the row's population
counted against the unit's coverage so that the refusal is visible rather than
silently absorbed. ``uninhabited 100%`` is not a language and is excluded the
same way: 338 rows, all in Gilān.

**What the shares can no longer show.** Rounding a unit's composition to one
decimal is this map's convention, and the atlas records some languages in one
settlement and at a share of a percent of it. Judeo-Hamadāni is 0.001% of the
city of Hamadān, which is five people and 0.0003% of the province;
Judeo-Borujerdi 0.01% of Vuriyerd; Jidi 0.005% of the city of Esfahān, 0.002%
of the province; Neo-Mandaic 0.0085% of Ahwāz, 0.002% of Khuzestān. Every one
of them is far below the 0.05% a unit-level share has to reach to print as
anything but 0.0%, so none of them appears in these provincial figures. They
are in the atlas's settlement files, which is where a reader who wants them
should look. That is a property of rolling a composition up, not a judgement
about the languages.

Usage:
    python -m scripts.fetch_census.iran_ali            # write the file
    python -m scripts.fetch_census.iran_ali --describe # measure, write nothing
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from ._shared import PROCESSED, RAW, log, record, write_json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import DERIVED, MODELLED, estimate, read_json, slugify  # noqa: E402
from common import shard_name  # noqa: E402

ISO3 = "IRN"
OUT = "iran_ali_language.json"
SOURCE_DIR = RAW / "iran"
FILE_GLOB = "Language_Distribution_*.csv"
CITATIONS = "ali_citations.json"

# Verbatim from row 1 of every file. Not paraphrased, not shortened: it is the
# condition the data is published under and the only thing on the record that
# states it.
LICENCE = ("(c) Atlas of the Languages of Iran (ALI) and Contributors, "
           "2015-present. Data are available under a CC BY (Attribution Only) "
           "licence.")
SERIES = "Atlas of the Languages of Iran (ALI)"
SERIES_EDITORS = "Erik Anonby, Mortaza Taheri-Ardali, et al."
PUBLISHER = ("Ottawa: GCRC (Geomatics and Cartographic Research Centre), "
             "Carleton University")

# The columns this module needs. A file without all of them is a different
# export and is not read; clear_global.py recognises its publisher's files the
# same way, by header rather than by name.
REQUIRED = ("Attribution", "province_roman", "shahrestan_roman", "bakhsh_roman",
            "city_roman", "dehestan_roman", "settlement_roman",
            "population_2011_census", "population_2016_census",
            "language_distribution_estimate", "language_distribution_source")

# How far a settlement's shares may be from 100 before the row is refused.
# 21,137 of 21,152 rows sum to exactly 100; the ones this tolerance admits are
# a rounding-scale language written on top of a partition that already closed
# (100.0085, 100.5), and they are renormalised. The eight it refuses are 80,
# 85, 90, 90, 90, 90.01, 105 and 110, which are not rounding.
SHARE_TOLERANCE = 0.5
# A group below this prints as 0.0% and is dropped from the unit's shares.
MIN_PCT = 0.05
# What share of a unit's people the weighted settlements must reach before the
# unit gets a figure rather than a stated gap. See the docstring: measured,
# nothing falls between 18.6% and 74.6%.
MIN_COVERAGE = 0.60
# And what it takes for a unit's figure to be a derivation rather than a
# model: every language row weighted, no row refused, the unit's own total row
# to measure against, and effectively all of it covered. Short of that,
# something about the unit was assumed and the status says so.
FULL_COVERAGE = 0.99
# A unit's shares, after rounding and after dropping what rounds to nothing,
# must still be a partition.
SUM_TOLERANCE = 0.5

# "Central Kurdish 100%", "Tehrāni type Persian 1%", "Rāji  80%" (the file
# does write a double space). Anchored at both ends so that a string this
# module does not understand fails rather than half-parses.
SHARE = re.compile(r"^(?P<name>.+?)\s+(?P<pct>\d+(?:\.\d+)?)\s*%$")
# Not a language: a settlement the atlas records as having no inhabitants.
UNINHABITED = "uninhabited"
# The year inside a field-note citation: "Mehdi Fattahi, field notes 2017".
FIELD_YEAR = re.compile(r"\b(19\d\d|20[0-2]\d)\b")
# How far the fieldwork may predate the module before the note says so, and
# how much of a unit's population has to be behind that older fieldwork for
# it to be worth saying. Kermānshāh's module is dated 2022 and every row in it
# cites field notes of 2017; a reader comparing it with Khuzestān's 2024
# should not have to find that out from the raw file.
STALE_YEARS = 3
STALE_SHARE = 0.10

# Iran's provinces as ALI romanises them against the names the boundary file
# draws. Only the four that do not survive ``fold`` are listed: reconciling a
# romanisation is a decision about which place is which, so it is written down
# where it can be read and checked, and never inferred from how alike two
# strings look. A new province file whose name folds to a shape's name needs
# no entry here; one that does not is skipped and named in the log.
PROVINCE_ALIASES: dict[str, str] = {
    "Esfahān": "Isfahan",
    "Kordestān": "Kurdistan",
    "Chahār Mahāl va Bakhtiāri": "Chaharmahal and Bakhtiari",
    "Kohgiluyeh va Boyer Ahmad": "Kohgiluyeh and Boyer-Ahmad",
}

# The same, one level down: ALI's shahrestan spelling against the boundary
# file's, for the 22 of 101 that ``fold`` does not carry across. Most are the
# same name written differently -- "Qorveh"/"Ghorveh", "Dayyer"/"Deyr",
# "Bashkard"/"Bashagard" -- and nine are Esfahān's, where the boundary file
# writes the Persian "o" as "and". Keyed by the province's *shape* name, so a
# spelling that means one county in one province cannot reach another.
SHAHRESTAN_ALIASES: dict[str, dict[str, str]] = {
    "Bushehr": {"Dayyer": "Deyr"},
    "Chaharmahal and Bakhtiari": {"Shahr-e Kord": "Sharekurd"},
    "Gilan": {"Tavālesh": "Talesh",
              "Āstāneh-ye Ashrafiyyeh": "Astan-e-Ashrafieh"},
    "Hamadan": {"Hamadān": "Hamedan", "Kabudrāhang": "Kabutarahang"},
    "Hormozgan": {"Bandar Abbās": "Bandar-e-Abbas",
                  "Bandar Lengeh": "Bandar-e-Lengeh",
                  "Bashkard": "Bashagard"},
    "Isfahan": {"Borkhār": "Barkhar",
                # The boundary file draws two shapes here, "Isfahan" and
                # "Isfahan County". They are not duplicates: "Isfahan" is a
                # 0.2-degree polygon over the city and "Isfahan County" is the
                # 1.7-degree one around it. The shahrestan is the county, and
                # the city polygon is left empty rather than given a figure
                # for the countryside around it.
                "Esfahān": "Isfahan County",
                "Falāvarjān": "Falaverjan",
                "Khomeyni Shahr": "Khomeini Shahr",
                "Khur o Biābānak": "Khur and Biabanak",
                "Shahrezā": "Sahreza",
                "Shāhin Shahr o Meymeh": "Shahin Shahr and Meymeh",
                "Tirān o Karvan": "Tiran and Karvan",
                "Ārān o Bidgol": "Aran and Bidgol"},
    "Kurdistan": {"Divān Darreh": "Divandareh", "Qorveh": "Ghorveh"},
}

# Shahrestans ALI publishes that this map has no single shape for. Declared,
# rather than left to fail quietly, because each is a fact about the boundary
# file worth keeping; an undeclared one is logged as something to look at.
SHAHRESTAN_NO_SHAPE: dict[str, dict[str, str]] = {
    "Hormozgan": {
        "Abu Musā": "geoBoundaries draws no second-level shape for the island; "
                    "Hormozgan's twelve do not include it.",
    },
    "Ilam": {
        "Shirvān va Chardāvol": "the boundary file draws Chardavol and Sirvan "
                                "as two counties where ALI writes one, and "
                                "there is no figure for either apart.",
    },
}

FIELD = "language"
LEVELS = ("province", "shahrestan", "bakhsh", "city", "dehestan", "settlement")


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def fold(text: str) -> str:
    """A name reduced to the letters two romanisations agree on.

    Diacritics only: "Kordestān" and "Kordestan" are one name written twice,
    and folding them together is transliteration rather than guesswork. What
    this deliberately does *not* do is bridge "Qorveh" to "Ghorveh" or
    "Kordestān" to "Kurdistan" -- those are different letters, and deciding
    they are the same place is a judgement, which belongs in the alias tables
    above where it can be read.
    """
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\b(county|shahrestan)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def number(text: str | None) -> int | None:
    text = (text or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def source_files(directory: Path) -> list[Path]:
    return sorted(directory.glob(FILE_GLOB))


def read_file(path: Path) -> tuple[list[dict[str, str]], str]:
    """One province's rows, and the licence its first row states.

    The licence row fills ``Attribution`` and nothing else, and it is row 1 of
    every file. Returning it rather than assuming it is what lets a file that
    does not carry the licence be refused instead of read.
    """
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return [], ""
    missing = [c for c in REQUIRED if c not in rows[0]]
    if missing:
        raise ValueError(f"not an ALI language-distribution export; "
                         f"it has no {', '.join(missing)}")
    head = rows[0]
    others = [v for k, v in head.items() if k != "Attribution" and (v or "").strip()]
    if others:
        raise ValueError("row 1 is not the licence row: it fills other columns")
    return rows[1:], (head.get("Attribution") or "").strip()


def province_of(rows: list[dict[str, str]]) -> tuple[str, str]:
    """The province the file describes, from its own column and not its name.

    The filenames carry the day the owner exported them, which is not a fact
    about the data; the province column is.
    """
    roman = {(r.get("province_roman") or "").strip() for r in rows} - {""}
    persian = {(r.get("province_Persian") or "").strip() for r in rows} - {""}
    if len(roman) != 1:
        raise ValueError(f"expected one province per file, found {sorted(roman)}")
    return roman.pop(), (persian.pop() if len(persian) == 1 else "")


# ---------------------------------------------------------------------------
# One settlement's shares
# ---------------------------------------------------------------------------

def parse_shares(text: str) -> tuple[dict[str, float], str]:
    """``"Turkic 80%; Southern Kurdish 20%"`` -> {Turkic: 80, ...}, or a reason.

    Two refusals and they are different findings. A string that does not parse
    is one this module does not understand; a string that parses and does not
    add to 100 is one whose author left part of the settlement unaccounted
    for. Neither is guessed at -- normalising 80% up to 100% would invent a
    fifth of a village -- and the caller counts the population of both against
    the unit's coverage, so that a refusal shows up as a smaller claim rather
    than as nothing at all.
    """
    parts = [p.strip() for p in (text or "").split(";") if p.strip()]
    if not parts:
        return {}, "the row carries no estimate"
    shares: dict[str, float] = {}
    for part in parts:
        found = SHARE.match(part)
        if not found:
            return {}, f"{part!r} is not '<language> <number>%'"
        name = " ".join(found.group("name").split())
        shares[name] = shares.get(name, 0.0) + float(found.group("pct"))
    total = sum(shares.values())
    if abs(total - 100.0) > SHARE_TOLERANCE:
        return {}, (f"its shares add to {total:g}%, not to 100 "
                    f"(tolerance {SHARE_TOLERANCE}%)")
    return shares, ""


def weight_of(row: dict[str, str]) -> tuple[int | None, int | None]:
    """The population to weight a settlement by, and the year it describes.

    2016 where the file prints one, 2011 otherwise. See the docstring for the
    measurement behind that order.
    """
    recent = number(row.get("population_2016_census"))
    if recent is not None:
        return recent, 2016
    older = number(row.get("population_2011_census"))
    if older is not None:
        return older, 2011
    return None, None


def has_language(row: dict[str, str]) -> bool:
    """The nesting rule, in one predicate. See the module docstring."""
    return bool((row.get("language_distribution_estimate") or "").strip())


def is_province_total(row: dict[str, str]) -> bool:
    """The atlas's own entry for the province as a whole.

    Recognised by its place id and not by being the largest row. Ten of the
    twelve files carry one, with an id ending in four zeroes -- 1120000 for
    Kordestān, 1060000 for Khuzestān, 50000 for Kermānshāh -- and in the three
    files that leave the name columns blank it is the only thing that tells a
    province row from the shahrestan row printed directly under it. Taking the
    largest population instead put Kohgiluyeh va Boyer Ahmad's biggest county,
    299,885 people, on the province: a denominator two and a half times too
    small, and a coverage of 236%. That file simply has no province row, which
    is a fact about the file and is handled by ``Unit.total``.
    """
    if any((row.get(f"{level}_roman") or "").strip() for level in LEVELS[1:]):
        return False
    return (row.get("ALI_unique_ID_place") or "").strip().endswith("0000")


def is_place_row(row: dict[str, str]) -> bool:
    """A settlement or a town, by its name columns -- the *structural* leaf.

    Only used for the fallback denominator, and only in files that fill their
    name columns. The composition itself never asks this question, because
    four of the twelve files cannot answer it.
    """
    return bool((row.get("settlement_roman") or "").strip()
                or (row.get("city_roman") or "").strip())


# ---------------------------------------------------------------------------
# One unit's composition
# ---------------------------------------------------------------------------

class Unit:
    """Everything measured about one province or one shahrestan."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.spellings: set[str] = set()
        self.weighted: dict[str, float] = defaultdict(float)
        self.population = 0            # people behind the composition
        self.rows = 0                  # settlements carrying a language
        self.unweighted = 0            # ... of those, with no population
        self.refused: list[tuple[str, int, str]] = []   # (place, people, why)
        self.uninhabited = 0
        self.uninhabited_population = 0
        self.sources: dict[str, int] = defaultdict(int)
        # Which year the rows say the fieldwork happened in, weighted by the
        # people behind them. The module's year is when it was published; a
        # row's is when somebody stood in the village.
        self.field_years: dict[int, int] = defaultdict(int)
        self.years: set[int] = set()   # which census column supplied a weight
        self.own_total: int = 0        # the file's own aggregate row
        self.place_total: int = 0      # the sum of its settlement and city rows

    def add(self, row: dict[str, str], place: str) -> None:
        self.rows += 1
        weight, year = weight_of(row)
        text = (row.get("language_distribution_estimate") or "").strip()
        if UNINHABITED in text.lower():
            self.uninhabited += 1
            self.uninhabited_population += weight or 0
            return
        shares, why = parse_shares(text)
        if why:
            self.refused.append((place, weight or 0, why))
            return
        if weight is None:
            self.unweighted += 1
            return
        if weight <= 0:
            return
        self.population += weight
        if year:
            self.years.add(year)
        # One row may cite two field sources, joined by a semicolon the same
        # way the shares are -- "Masoud Mohammadirad, field notes 2015; Erik
        # Anonby, field notes 2014". Counting the compound string as one
        # citation printed Mohammadirad twice in Kordestān's note, because the
        # joined form and the plain form are different strings.
        for cited in (row.get("language_distribution_source") or "").split(";"):
            cited = " ".join(cited.split())
            if not cited:
                continue
            self.sources[cited] += 1
            for found in FIELD_YEAR.findall(cited):
                self.field_years[int(found)] += weight
        total = sum(shares.values())
        for language, pct in shares.items():
            self.weighted[language] += weight * pct / total

    def total(self, shape_population: int | None = None) -> tuple[int, str]:
        """The unit's population, and which of the three sources gave it.

        The atlas's own total for the unit first, because it is the same
        source and the same census year as the weights. Then the population
        this map already holds for the shape, which is independent evidence
        and is what Kohgiluyeh va Boyer Ahmad and Hamadān need -- neither
        file carries a province row. The atlas's own settlements last: in a
        file that fills its name columns that sum is a real denominator,
        counting settlements with a population and no language, but in one
        that does not it can only reach the rows already in the numerator,
        and a coverage of 100% that was arithmetically bound to happen is
        not a measurement. It is still better than no figure at all, and the
        note says which of the three this unit used.
        """
        if self.own_total:
            return self.own_total, "own"
        if shape_population:
            return int(shape_population), "shape"
        if self.place_total:
            return self.place_total, "places"
        return 0, "none"

    def shares(self) -> list[dict[str, Any]]:
        if not self.population:
            return []
        rows = [{"group": language, "pct": round(100.0 * value / self.population, 1)}
                for language, value in self.weighted.items()]
        rows = [r for r in rows if r["pct"] >= MIN_PCT]
        rows.sort(key=lambda r: (-r["pct"], r["group"]))
        return rows


def collect(rows: list[dict[str, str]]) -> tuple[Unit, dict[str, Unit], list[str]]:
    """The province and its shahrestans, from one file's rows.

    Shahrestans are keyed on the folded name because a file may spell one unit
    two ways -- Gilān writes "Rudsar" on 357 rows and "Rud Sar" on the town's
    own row, and keeping them apart left the county reading 73.6% covered when
    it is 99.4%.
    """
    province = Unit("")
    counties: dict[str, Unit] = {}
    variants: list[str] = []

    for row in rows:
        county_name = (row.get("shahrestan_roman") or "").strip()
        key = fold(county_name)
        county = None
        if key:
            county = counties.get(key)
            if county is None:
                county = counties[key] = Unit(county_name)
            county.spellings.add(county_name)

        if has_language(row):
            place = ((row.get("city_roman") or "").strip()
                     or (row.get("settlement_roman") or "").strip()
                     or (row.get("local_name") or "").strip()
                     or (row.get("ALI_unique_ID_place") or "").strip()
                     or "an unnamed place")
            province.add(row, place)
            if county is not None:
                county.add(row, place)
            continue

        # An aggregate row. Which unit's total it is depends on how deep its
        # name columns go, and it is taken as a total for that unit only.
        weight, _ = weight_of(row)
        if weight is None:
            continue
        if not county_name:
            if is_province_total(row):
                province.own_total = max(province.own_total, weight)
            continue
        if not (row.get("bakhsh_roman") or "").strip():
            county.own_total = max(county.own_total, weight)

    for row in rows:
        if has_language(row) or not is_place_row(row):
            continue
        weight, _ = weight_of(row)
        if weight is None:
            continue
        # A settlement or town with a population and no language: it is not in
        # the composition and it is in the denominator, which is what makes an
        # unsurveyed corner of a county show up as coverage rather than vanish.
        province.place_total += weight
        key = fold((row.get("shahrestan_roman") or "").strip())
        if key in counties:
            counties[key].place_total += weight

    for row in rows:
        if not has_language(row):
            continue
        weight, _ = weight_of(row)
        if weight is None:
            continue
        province.place_total += weight
        key = fold((row.get("shahrestan_roman") or "").strip())
        if key in counties:
            counties[key].place_total += weight

    for county in counties.values():
        if len(county.spellings) > 1:
            variants.append(f"{county.name}: {', '.join(sorted(county.spellings))}")
    return province, counties, variants


# ---------------------------------------------------------------------------
# The map's own shapes
# ---------------------------------------------------------------------------

def shapes(level: str) -> list[dict[str, Any]]:
    root = Path(__file__).resolve().parent.parent.parent / "site" / "data"
    return read_json(root / level / shard_name(ISO3), []) or []


def province_shape(roman: str, by_name: dict[str, dict[str, Any]]
                   ) -> dict[str, Any] | None:
    """The first-level shape a file's province column names, or None.

    Folding first and the alias table second, so that the table holds only the
    decisions a reader would want to check.
    """
    named = PROVINCE_ALIASES.get(roman)
    if named:
        return by_name.get(fold(named))
    return by_name.get(fold(roman))


def county_shape(province_name: str, roman: str,
                 by_name: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    named = SHAHRESTAN_ALIASES.get(province_name, {}).get(roman)
    if named:
        return by_name.get(fold(named))
    return by_name.get(fold(roman))


# ---------------------------------------------------------------------------
# Writing one record
# ---------------------------------------------------------------------------

def citation(entry: dict[str, Any]) -> str:
    return (f"{entry['authors']} ({entry['year']}). {entry['title']}. "
            f"In {SERIES_EDITORS} (eds.), {SERIES}. {PUBLISHER}.")


def field_sources(unit: Unit, limit: int = 6) -> str:
    """The row-level field-note citations behind one unit, most rows first."""
    ordered = sorted(unit.sources.items(), key=lambda kv: (-kv[1], kv[0]))
    named = "; ".join(name for name, _ in ordered[:limit])
    if len(ordered) > limit:
        named += f"; and {len(ordered) - limit} other field sources"
    return named


def fieldwork_clause(unit: Unit, module_year: int) -> str:
    """Said only when the fieldwork is materially older than the module.

    Publication and fieldwork are different events, and the distance between
    them is not the same in every province: Kordestān's module is a year after
    its field notes, Kermānshāh's five years after, and there the whole
    province is behind that gap. A reader comparing two provinces is entitled
    to that before they compare them.
    """
    if not unit.field_years:
        return ""
    behind = sum(people for year, people in unit.field_years.items()
                 if year <= module_year - STALE_YEARS)
    weighed = sum(unit.field_years.values())
    if not weighed or behind / weighed < STALE_SHARE:
        return ""
    years = sorted(y for y in unit.field_years if y <= module_year)
    span = (f"{years[0]}" if years[0] == years[-1] else f"{years[0]}-{years[-1]}")
    return (f"The module is dated {module_year}, but the fieldwork behind it is "
            f"older: the rows cite field notes of {span}, and "
            f"{behind / weighed * 100:.0f}% of the people weighted here sit "
            f"behind notes taken {STALE_YEARS} or more years before the module "
            f"was published.")


def method_note(unit: Unit, label: str, entry: dict[str, Any], total: int,
                basis: str, coverage: float) -> str:
    """What the panel prints. It has to say that nothing was counted here."""
    where = {"own": f"the atlas's own total for {label}",
             "places": f"the settlements and towns the atlas lists in {label}",
             "shape": "the population this map holds for the shape"}[basis]
    weights = ("the 2016 census population where the atlas prints one and the "
               "2011 census population otherwise"
               if unit.years == {2011, 2016} else
               f"the {sorted(unit.years)[0]} census population" if unit.years
               else "the census populations the atlas prints")
    text = [
        f"Nothing was read for {label} itself. This is the population-weighted "
        f"sum of the language estimates the Atlas of the Languages of Iran "
        f"publishes for {unit.rows - unit.uninhabited:,} settlements and towns "
        f"inside it, each weighted by {weights}. Those weighted places hold "
        f"{unit.population:,} people, {coverage * 100:.1f}% of the "
        f"{total:,} that {where} accounts for.",
    ]
    if coverage > 1.0 + SUM_TOLERANCE / 100.0:
        text.append(
            f"The weighted settlements hold {unit.population - total:,} people "
            f"more than that total, {coverage * 100 - 100:.1f}% of it: the "
            f"atlas's settlement populations and the total it prints for the "
            f"unit do not quite agree, and neither has been adjusted to the "
            f"other.")
    if unit.unweighted:
        text.append(
            f"{unit.unweighted:,} further "
            f"{'settlement carries' if unit.unweighted == 1 else 'settlements carry'} "
            f"a language and no population in either census year; there is no "
            f"weight to give them and none was invented, so they are excluded.")
    if unit.refused:
        worst = sorted(unit.refused, key=lambda r: -r[1])[:3]
        named = "; ".join(f"{place} ({people:,} people): {why}"
                          for place, people, why in worst)
        text.append(
            f"{len(unit.refused)} settlement "
            f"{'estimate' if len(unit.refused) == 1 else 'estimates'} could not "
            f"be read as shares and {'was' if len(unit.refused) == 1 else 'were'} "
            f"refused rather than guessed at -- {named}"
            f"{f'; and {len(unit.refused) - 3} more' if len(unit.refused) > 3 else ''}.")
    if unit.uninhabited:
        text.append(
            f"{unit.uninhabited:,} places the atlas records as uninhabited "
            f"carry no language and are excluded.")
    text.append(
        f"ALI is a research atlas of field estimates, not a census: Iran's "
        f"census does not ask language, so no census supports these shares and "
        f"none contradicts them. The module is {entry['authors']} "
        f"({entry['year']}), and the rows themselves cite {field_sources(unit)}.")
    stale = fieldwork_clause(unit, int(entry["year"]))
    if stale:
        text.append(stale)
    return " ".join(text)


def unit_record(unit: Unit, shape: dict[str, Any], entry: dict[str, Any],
                level: str, parent: str, parent_name: str | None,
                roman: str, total: int, basis: str) -> dict[str, Any] | None:
    """One unit's record, or None with the reason logged."""
    label = shape["name"]
    rows = unit.shares()
    if not rows:
        log(f"    {label}: no weighted settlement carries a language; "
            f"nothing written")
        return None
    summed = sum(r["pct"] for r in rows)
    if abs(summed - 100.0) > SUM_TOLERANCE:
        log(f"    {label}: its shares add to {summed:.1f} and are not written")
        return None
    coverage = unit.population / total if total else 0.0

    # Derived or modelled, decided per unit and by measurement. A derivation
    # is arithmetic on published figures and nothing else: every settlement
    # weighted, nothing refused, and the weighted settlements accounting for
    # effectively the whole unit measured against a denominator that could
    # have come out larger. Anything short of that rests on the assumption
    # that what was left out resembles what was read, which is a model.
    #
    # "places" counts as such a denominator and "shape" does not, which is a
    # change from the first version of this rule. The place total is built in
    # two passes and the first one adds settlements that have a population and
    # no language at all -- so an unsurveyed corner of a unit lands in the
    # denominator and pulls coverage below 100%. A unit that still reaches
    # 100% has been measured, not defined into it: Bahar's 71 settlements all
    # carry both a population and a language, and had any one of them carried
    # only a population the coverage would have said so. Requiring the atlas's
    # own aggregate row instead called that a model, which understated the one
    # unit in Iran where the atlas is demonstrably complete.
    #
    # "shape" stays a model because its denominator is a different source and
    # a different vintage -- this map's Wikidata population against the
    # atlas's census weights -- so agreement between them is a coincidence of
    # two sources rather than arithmetic within one.
    full = (basis in ("own", "places") and coverage >= FULL_COVERAGE
            and not unit.unweighted and not unit.refused)
    status = DERIVED if full else MODELLED
    method = ("population-weighted sum of every published ALI settlement "
              "estimate in the unit"
              if full else
              "population-weighted sum of the published ALI settlement "
              "estimates in the unit that carry a population")

    value = estimate(
        status, rows, method=method,
        inputs=[f"ali-{slugify(entry['title'])}-{entry['year']}"],
        note=method_note(unit, label, entry, total, basis, coverage))
    # The year the panel prints for this figure: the module's, not the
    # export's and not the other eleven provinces'.
    value["year"] = entry["year"]
    value["coverage_pct"] = round(coverage * 100, 1)
    value["settlements"] = unit.rows - unit.uninhabited
    value["settlements_unweighted"] = unit.unweighted
    value["settlements_refused"] = len(unit.refused)

    aliases = sorted({roman, *unit.spellings} - {label})
    entity_id = (f"{ISO3}-ALI-{slugify(label)}" if level == "admin1"
                 else f"{ISO3}-ALI-{slugify(parent_name or '')}-{slugify(label)}")
    fields: dict[str, Any] = {FIELD: value, "country": ISO3, "aliases": aliases}
    if parent_name:
        fields["parent_name"] = parent_name
    return record(
        entity_id, label, level=level, parent=parent,
        sources=[{"field": FIELD, "name": citation(entry), "url": entry["url"],
                  "year": entry["year"], "license": LICENCE}],
        **fields)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def citations(directory: Path) -> dict[str, dict[str, Any]]:
    payload = read_json(directory / CITATIONS, {}) or {}
    return {entry["csv_province_roman"]: entry
            for entry in payload.get("provinces", [])}


def build(directory: Path = SOURCE_DIR
          ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every record the files in ``directory`` support, and what was measured."""
    cited = citations(directory)
    admin1 = {fold(s["name"]): s for s in shapes("admin1")}
    admin1_by_id = {s["id"]: s for s in shapes("admin1")}
    admin2: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for shape in shapes("admin2"):
        parent = admin1_by_id.get(shape.get("parent", ""), {}).get("name", "")
        admin2[parent][fold(shape["name"])] = shape

    records: list[dict[str, Any]] = []
    tally: dict[str, Any] = {"files": [], "provinces": 0, "counties": 0,
                             "unmatched": [], "gaps": [], "licences": set()}
    files = source_files(directory)
    log(f"iran_ali: {len(files)} province file(s) in {directory}")
    if not files:
        return records, tally

    for path in files:
        try:
            rows, licence = read_file(path)
            roman, persian = province_of(rows)
        except ValueError as err:
            log(f"  {path.name}: refused -- {err}")
            continue
        tally["licences"].add(licence)
        if licence != LICENCE:
            log(f"  {path.name}: refused -- its first row does not carry the "
                f"licence this module was written for: {licence!r}")
            continue
        shape = province_shape(roman, admin1)
        entry = cited.get(roman)
        log(f"  {path.name}: {len(rows):,} rows, province {roman} ({persian})")
        if shape is None:
            log(f"    refused: no first-level shape is named {roman}; add it "
                f"to PROVINCE_ALIASES with the boundary file's own spelling")
            tally["unmatched"].append(roman)
            continue
        if entry is None:
            log(f"    refused: {CITATIONS} carries no citation for {roman}, "
                f"and a record nobody can cite is not written")
            tally["unmatched"].append(roman)
            continue

        province, counties, variants = collect(rows)
        for line in variants:
            log(f"    one county spelled two ways, read as one: {line}")
        leaves = province.rows
        log(f"    {leaves:,} rows carry a language estimate; "
            f"{province.unweighted:,} of them no population in either year; "
            f"{len(province.refused)} refused; "
            f"{province.uninhabited} uninhabited")

        held = shape.get("population")
        total, basis = province.total(
            held.get("value") if isinstance(held, dict) else None)
        coverage = province.population / total if total else 0.0
        if not total:
            log(f"    {shape['name']}: no total to measure coverage against; "
                f"nothing written")
            tally["gaps"].append((shape["name"], "no population to measure "
                                                 "the composition against"))
        elif coverage < MIN_COVERAGE:
            reason = (f"the atlas's settlements cover {coverage * 100:.1f}% of "
                      f"the province's {total:,} people")
            log(f"    {shape['name']}: {reason}; below "
                f"{MIN_COVERAGE * 100:.0f}%, so no figure is written")
            tally["gaps"].append((shape["name"], reason))
        else:
            built = unit_record(province, shape, entry, "admin1", ISO3, None,
                                roman, total, basis)
            if built:
                records.append(built)
                tally["provinces"] += 1
                top = built[FIELD]["estimate"][0]
                log(f"    {shape['name']}: {coverage * 100:.1f}% covered, "
                    f"{built[FIELD]['status']}, largest group "
                    f"{top['group']} {top['pct']}%")

        parent_id = f"{ISO3}-ALI-{slugify(shape['name'])}"
        known = admin2.get(shape["name"], {})
        for county in sorted(counties.values(), key=lambda u: u.name):
            if not county.rows:
                continue
            declared = SHAHRESTAN_NO_SHAPE.get(shape["name"], {}).get(county.name)
            county_of = county_shape(shape["name"], county.name, known)
            if county_of is None:
                tally["unmatched"].append(f"{shape['name']}/{county.name}")
                log(f"    {county.name}: no second-level shape -- "
                    f"{declared or 'undeclared; look at it'}")
                continue
            held = county_of.get("population")
            total, basis = county.total(
                held.get("value") if isinstance(held, dict) else None)
            if not total:
                tally["gaps"].append((county_of["name"],
                                      "no population to measure it against"))
                log(f"    {county_of['name']}: no total to measure coverage "
                    f"against; nothing written")
                continue
            coverage = county.population / total
            if coverage < MIN_COVERAGE:
                reason = (f"the atlas's settlements cover {coverage * 100:.1f}% "
                          f"of the county's {total:,} people")
                tally["gaps"].append((county_of["name"], reason))
                log(f"    {county_of['name']}: {reason}; nothing written")
                continue
            built = unit_record(county, county_of, entry, "admin2", parent_id,
                                shape["name"], county.name, total, basis)
            if built:
                records.append(built)
                tally["counties"] += 1
        tally["files"].append({"file": path.name, "province": roman,
                               "rows": len(rows), "language_rows": leaves})
    return records, tally


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(SOURCE_DIR),
                    help="where the province CSVs are")
    ap.add_argument("--describe", action="store_true",
                    help="measure the files and write nothing")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    records, tally = build(Path(args.dir))
    log(f"  {tally['provinces']} province(s) and {tally['counties']} "
        f"shahrestan(s) written; {len(tally['gaps'])} unit(s) left as a stated "
        f"gap; {len(tally['unmatched'])} name(s) matched no shape")
    for name, reason in tally["gaps"]:
        log(f"    gap: {name} -- {reason}")
    if args.describe:
        log("  --describe: nothing written")
        return 0
    if not records:
        raise SystemExit("iran_ali: nothing usable was read; writing nothing")
    write_json(Path(args.out) if args.out else PROCESSED / OUT, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
