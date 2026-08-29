#!/usr/bin/env python3
"""South Africa -- Census 2022, by province, out of the statistical release.

Statistics South Africa's census portal is a JavaScript shell: fetched, it
returns 57 KB of markup with not one anchor in it, so nothing about what the
census publishes can be learned by following links from the front page. The
release itself sits under the portal's ``/assets/`` path, which the shell does
not affect, and it is a 113-page PDF. Reading it is the whole job.

Four of its tables carry a province in every row, and they are not equally
good, which decides what this adapter claims:

**Table 2.4 publishes population group as counts**, five groups and a total per
province. So ethnicity here is a count, it reconciles, and it can be summed
into a country. **Tables 2.9 and 2.10 publish language and religion as
percentages to one decimal and nothing else.** Those become shares with no
count attached. That is a real loss -- the build refuses to sum a parent from
children that publish shares without counts, so South Africa's own religion and
language stay at the province level -- and the alternative is worse: a count
reconstructed as 24,4% of 12,4 million is out by up to six thousand people and
carries no warning that it was never counted.

**The thousands separator is a space**, so a row of figures arrives as a stream
of digit fragments -- ``2 884 511 3 124 757 84 363`` is nine words for three
numbers -- and where one number ends is not marked. Pakistan's tables posed
this and were solved by measuring the gaps. Here the arithmetic solves it
outright: the row prints five groups and their total, so of the 3,003 ways to
cut sixteen fragments into six numbers, the right one is the one where the
first five add up to the sixth. Every province row has exactly one. The method
needs no coordinates at all, which is what makes it survive Gauteng, whose
coloured column is printed with the space in the wrong place -- ``44 3857`` for
443,857 -- and which no gap rule would have read correctly.

**The national row does not add up.** Reading it the same way yields nothing:
its five groups sum to 61,988,316 against its own printed total of 61,988,314.
Set beside the nine provinces, its Black African and Indian/Asian cells are
each one person high and its other four columns agree exactly. So the provinces
are consistent and the national row is off by two, which is StatsSA's rounding
and not a misreading -- and the run says so rather than quietly widening a
tolerance until the mismatch disappears.

**Population comes from Table 2.2, not from Table 2.4's own total.** Table 2.4
excludes people whose population group was not specified; its Western Cape
total is 7,426,673 where the province has 7,433,019. Shares are of the group
question's own denominator, which is right, but the population field should be
the province's population.

What is deliberately not read: **median age by province**. It exists, in Figure
2.11, as a chart -- the province names survive extraction only as the fragments
``Norther Cape`` and ``KwaZul u Natal``, and ``North`` is a prefix of two
different provinces. Recovering the column order would be a guess, and a wrong
guess gives Limpopo the Western Cape's median age while every figure on the
page stays plausible. An unmatched row is a visible gap; a mis-matched one is
invisible and worse.

Usage:
    python -m scripts.fetch_census.south_africa
"""

from __future__ import annotations

import argparse
import io
import re
from itertools import combinations
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, gap, http_get, log, measure, record, shares,
    write_json,
)

SOURCE = ("Statistics South Africa, Census 2022 Statistical Release P0301.4")
URL = ("https://census.statssa.gov.za/assets/documents/2022/"
       "P03014_Census_2022_Statistical_Release.pdf")
LICENCE = "Statistics South Africa, reuse with acknowledgement of the source"
YEAR = 2022

# How the percentage tables head their columns. Read from the header row rather
# than assumed -- the order is checked against this, not taken from it -- but
# the expansion of each code is a fact about the document that has to be
# declared somewhere.
CODES: tuple[str, ...] = ("WC", "EC", "NC", "FS", "KZN", "NW", "GP", "MP",
                          "LP", "SA")
PROVINCE_BY_CODE: dict[str, str] = {
    "WC": "Western Cape", "EC": "Eastern Cape", "NC": "Northern Cape",
    "FS": "Free State", "KZN": "KwaZulu-Natal", "NW": "North West",
    "GP": "Gauteng", "MP": "Mpumalanga", "LP": "Limpopo",
}
NATIONAL = "South Africa"
PROVINCES: tuple[str, ...] = tuple(PROVINCE_BY_CODE[c] for c in CODES[:-1])

# Table 2.4's columns, in the order it prints them, and the labels this dataset
# carries them under. StatsSA's own wording, because these are the state's
# categories and renaming them would describe a question it did not ask.
GROUPS: tuple[str, ...] = ("Black African", "Coloured", "Indian/Asian",
                           "White", "Other")

# Where a table's printed label is not the name the release itself uses.
#
# The nine Nguni and Sotho names are written with a lower-case prefix
# everywhere in the prose -- "isiZulu remained the most spoken language" -- and
# capitalised in the tables only because they start a line. The capital is
# typesetting, not spelling, and leaving it in makes the province panels
# disagree with the country panel about the name of the same language.
#
# "Sign language" is named in the prose on its own page: "Sign language was
# promulgated as South Africa's 12th official language in July 2023". Left bare
# it would key on itself and merge with any other country's generic
# sign-language row, which is a different language.
LANGUAGE_NAMES: dict[str, str] = {
    "IsiNdebele": "isiNdebele", "IsiXhosa": "isiXhosa", "IsiZulu": "isiZulu",
    "SiSwati": "siSwati",
    "Sign language": "South African Sign Language",
}

# Table 2.10 heads the column "Traditional African"; the prose beneath it calls
# the thing measured "Traditional African religion", which is what the row is.
RELIGION_NAMES: dict[str, str] = {
    "Traditional African": "Traditional African religion",
}

# What the boundary file calls the same province. geoBoundaries' global
# composite spells the Northern Cape "Nothern Cape", a letter short, so the
# census's own spelling does not match it and the province would have joined
# nothing. Declared rather than reached by a looser rule: "Nothern Cape" and
# "Northern Cape" differ by less than "Eastern Cape" and "Western Cape" do, and
# a match loose enough to bridge the first would bridge the second.
ALIASES: dict[str, tuple[str, ...]] = {
    "Northern Cape": ("Nothern Cape",),
}

CAPTIONS = {
    "population": "Table 2.2:",
    "ethnicity": "Table 2.4:",
    "sex_ratio": "Table 2.7:",
    "language": "Table 2.9:",
    "religion": "Table 2.10:",
}

POPULATION_NOTE = (
    "Census 2022 Table 2.2. This is the province's population, not the "
    "denominator of the population-group question below it: Table 2.4 excludes "
    "people whose group was not specified and is 6,346 lower in the Western "
    "Cape.")
ETHNICITY_NOTE = (
    "Census 2022 Table 2.4, as counts. The five groups add up to the province's "
    "own printed total exactly, and the nine provinces add up to the national "
    "row in four of the five groups.")
SHARE_NOTE = (
    "Census 2022 {table}, which publishes this as percentages to one decimal "
    "place and no counts. No count is shown because none was published; "
    "multiplying by the province's population would invent a precision the "
    "census did not report.")
LANGUAGE_NOTE = SHARE_NOTE.format(table="Table 2.9") + (
    " The question is the language spoken most often in the household, and "
    "excludes children under one year old.")
RELIGION_NOTE = SHARE_NOTE.format(table="Table 2.10")

DECIMAL = re.compile(r"^-?\d+,\d+$")
DIGITS = re.compile(r"^\d+$")


# How far a row of published percentages may be from 100 and still be the
# rounding it looks like. Measured: the widest column in either table is
# 100.01 and the narrowest 99.93, against a stated note that "totals may not
# add up to 100 because of smaller figures that do not appear as a result of
# the one decimal place".
PERCENT_SLACK = 0.5

# What the national row of Table 2.4 is allowed to differ from its own five
# cells. Not a tolerance chosen to make a check pass: read against the nine
# provinces, the row is one person high in Black African and one in
# Indian/Asian, and exact in the other four columns.
NATIONAL_SLACK = 2


def flat(text: str) -> str:
    """A name in the form two printings of it can be compared in.

    Table 2.4 sets a long province name over two lines, so "KwaZulu-Natal"
    arrives as "KwaZulu-" above "Natal" and joins up as "KwaZulu- Natal". The
    hyphen and the run of spaces are both artefacts of the layout rather than
    anything about the name.
    """
    return " ".join(text.replace("-", " ").split())


def value(run: list[str]) -> int | None:
    """One number from the fragments it was printed as, or None.

    A leading zero is the tell of a wrong cut: the table prints 4,898,063 as
    "4 898 063", so a run beginning "063" is the tail of a number rather than
    a number, and rejecting it prunes most of the search before the arithmetic
    has to.
    """
    if not run:
        return None
    text = "".join(run)
    if len(text) > 1 and text.startswith("0"):
        return None
    return int(text)


def readings(tokens: list[str], columns: int):
    """Every way the fragments could be that many numbers."""
    if len(tokens) < columns:
        return
    for cuts in combinations(range(1, len(tokens)), columns - 1):
        edges = (0,) + cuts + (len(tokens),)
        found = [value(tokens[a:b]) for a, b in zip(edges, edges[1:])]
        if all(v is not None for v in found):
            yield found


def counted(tokens: list[str], where: str, slack: int = 0) -> list[int]:
    """The one reading of a row whose parts add up to its printed total.

    Refuses on two readings as firmly as on none. A row that can be read two
    ways is a row this method cannot settle, and picking either would put a
    number on the map with nothing behind it.
    """
    good = [found for found in readings(tokens, len(GROUPS) + 1)
            if abs(sum(found[:-1]) - found[-1]) <= slack]
    if len(good) == 1:
        return good[0]
    if not good:
        raise SystemExit(
            f"{where}: no way of cutting {len(tokens)} printed fragments into "
            f"{len(GROUPS) + 1} numbers has the groups adding up to the total: "
            f"{' '.join(tokens)}")
    raise SystemExit(
        f"{where}: {len(good)} different readings of the row all add up, so "
        f"which is the published one cannot be told: {good[:3]}")


def pages(blob: bytes, tolerance: float = 2.0) -> list[list[list[str]]]:
    """The document as pages of rows of words, rebuilt from the coordinates.

    pdfplumber reports every word with its box; a page's words are stored in
    whatever order the file happens to hold them, so rows are assembled from
    where the words sit -- words sharing a baseline to within a couple of
    points, read left to right.
    """
    import pdfplumber

    out: list[list[list[str]]] = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        log(f"  {len(pdf.pages)} pages")
        for page in pdf.pages:
            rows: list[tuple[float, list[tuple[float, str]]]] = []
            for word in sorted(page.extract_words(use_text_flow=False),
                               key=lambda w: (round(w["top"], 1), w["x0"])):
                top = round(word["top"], 1)
                if rows and abs(rows[-1][0] - top) <= tolerance:
                    rows[-1][1].append((word["x0"], word["text"]))
                else:
                    rows.append((top, [(word["x0"], word["text"])]))
            out.append([[text for _x, text in sorted(cells)]
                        for _top, cells in rows])
    return out


def candidates(document: list[list[list[str]]], caption: str):
    """Every place a table's caption appears, with the rows that follow it.

    The caption appears at least twice: over the table, and in the LIST OF
    TABLES, which comes first. The two cannot be told apart by looking at the
    caption row -- the leader of dots that marks a contents entry wraps onto
    the next line for the longer captions, so "Table 2.9:" reads identically in
    both places. So every occurrence is offered and the readers decide, which
    is the same principle as the arithmetic above: verify rather than rely on a
    rule about how the document is laid out.

    The page after is included with each, because a table may continue onto it.
    Nothing is trusted to end where the page does -- each reader stops at the
    row it is looking for and says so if it never arrives.
    """
    for index, rows in enumerate(document):
        for position, row in enumerate(rows):
            if " ".join(row).startswith(caption):
                after = rows[position + 1:]
                if index + 1 < len(document):
                    after = after + document[index + 1]
                yield after


def read(document: list[list[list[str]]], caption: str, parse):
    """The first occurrence of a table that parses as one.

    A reader that accepted the contents entry would be a reader that accepted
    anything, so each of them below is strict about the shape it expects and
    the last complaint is reported when none of them fit.
    """
    problems: list[str] = []
    for rows in candidates(document, caption):
        try:
            return parse(rows)
        except SystemExit as err:
            problems.append(str(err))
    raise SystemExit(problems[-1] if problems
                     else f"{caption} does not appear in {URL}")


def population(rows: list[list[str]]) -> dict[str, int]:
    """Table 2.2: each province's population, and the census before it.

    The row is a name and then four censuses with a percentage change after
    each of the last three, so the percentages -- the only tokens carrying a
    comma -- mark where the counts end. The 2022 figure is the run of digits
    between the second and the third of them, which needs no search: the
    separators are printed.
    """
    found: dict[str, int] = {}
    for row in rows:
        marks = [i for i, t in enumerate(row) if DECIMAL.match(t)]
        if len(marks) != 3:
            continue
        name = " ".join(t for t in row[:marks[0]] if not DIGITS.match(t))
        number = value(row[marks[1] + 1:marks[2]])
        if number is None or (name not in PROVINCES and name != NATIONAL):
            continue
        found[name] = number
        if name == NATIONAL:
            break
    missing = [p for p in PROVINCES if p not in found]
    if missing or NATIONAL not in found:
        raise SystemExit(f"Table 2.2: no population read for "
                         f"{', '.join(missing) or NATIONAL}")
    total = sum(found[p] for p in PROVINCES)
    if total != found[NATIONAL]:
        raise SystemExit(
            f"Table 2.2: the nine provinces come to {total:,} against a "
            f"printed South Africa of {found[NATIONAL]:,}")
    log(f"  Table 2.2: {len(PROVINCES)} provinces, {total:,} people, summing "
        f"to the printed national figure exactly")
    return found


def ethnicity(rows: list[list[str]]) -> dict[str, dict[str, int]]:
    """Table 2.4: population group as counts, for the 2022 block of each row.

    Each province appears four times, once per census; only the 2022 line is
    wanted, and it is the one beginning with that year. The province's name is
    printed beside its block rather than on any one of its rows -- sometimes
    split over two lines, "KwaZulu-" above "Natal" -- so it is collected from
    whatever words appear between one 1996 line and the next, and the block is
    refused unless exactly one province name is found in it.
    """
    found: dict[str, dict[str, int]] = {}
    words: list[str] = []
    for row in rows:
        if not row:
            continue
        if row[0] == "1996":
            words = []
        words.extend(t for t in row if not DIGITS.match(t) and t != "-")
        if row[0] != str(YEAR):
            continue
        name = " ".join(words).strip()
        named = [p for p in PROVINCES + (NATIONAL,) if flat(p) in flat(name)]
        if len(named) != 1:
            raise SystemExit(
                f"Table 2.4: a {YEAR} row sits under {named or 'no province'} "
                f"-- the words around it were {name!r}")
        province = named[0]
        slack = NATIONAL_SLACK if province == NATIONAL else 0
        figures = counted([t for t in row[1:] if DIGITS.match(t)],
                          f"Table 2.4 {province}", slack=slack)
        found[province] = dict(zip(GROUPS + ("Total",), figures))
        if province == NATIONAL:
            break
    missing = [p for p in PROVINCES if p not in found]
    if missing:
        raise SystemExit(f"Table 2.4: no {YEAR} row for {', '.join(missing)}")
    for province in PROVINCES:
        counts = found[province]
        parts = sum(counts[g] for g in GROUPS)
        if parts != counts["Total"]:
            raise SystemExit(f"Table 2.4 {province}: the groups come to "
                             f"{parts:,} against a printed {counts['Total']:,}")
    if NATIONAL in found:
        for column in GROUPS + ("Total",):
            summed = sum(found[p][column] for p in PROVINCES)
            printed = found[NATIONAL][column]
            if summed != printed:
                log(f"  Table 2.4 {column}: the nine provinces come to "
                    f"{summed:,} against a printed South Africa of "
                    f"{printed:,}, a difference of {printed - summed}")
    log(f"  Table 2.4: {len(PROVINCES)} provinces, "
        f"{sum(found[p]['Total'] for p in PROVINCES):,} people classified by "
        f"population group, every province adding up to its own total")
    return found


def percentages(rows: list[list[str]], caption: str, what: str,
                ) -> dict[str, dict[str, float]]:
    """Tables 2.9 and 2.10: a share for every province, one decimal place.

    Both are laid out the same way: a header of province codes, then one row
    per category, then a Total row printing 100,0 in each column. A category
    whose name is too long for the column has it wrapped onto the line above,
    with no figures on that line, so a row carrying no values is held over as
    the front of the next one's name.
    """
    order: list[str] | None = None
    start = 0
    for position, row in enumerate(rows):
        if len(row) >= len(CODES) and tuple(row[-len(CODES):]) == CODES:
            order = list(row[-len(CODES):])
            start = position + 1
            break
    if order is None:
        raise SystemExit(f"{caption} has no header row reading "
                         f"{' '.join(CODES)}")

    found: dict[str, dict[str, float]] = {c: {} for c in CODES}
    pending: list[str] = []
    printed: list[float] | None = None
    for row in rows[start:]:
        values = [t for t in row if DECIMAL.match(t)]
        label = " ".join(pending + [t for t in row if not DECIMAL.match(t)])
        label = " ".join(label.split()).strip()
        if not values:
            # Only a wrapped name is held over. Prose under the table would
            # otherwise accumulate and be prepended to nothing.
            pending = label.split() if label and len(label.split()) <= 4 else []
            continue
        pending = []
        if len(values) != len(CODES):
            raise SystemExit(
                f"{caption}: {label!r} has {len(values)} figures where the "
                f"table has {len(CODES)} columns: {' '.join(row)}")
        numbers = [float(v.replace(",", ".")) for v in values]
        if label.lower() == "total":
            printed = numbers
            break
        if not label:
            raise SystemExit(f"{caption}: a row of figures with no name: "
                             f"{' '.join(row)}")
        for code, number in zip(order, numbers):
            found[code][label] = found[code].get(label, 0.0) + number

    if printed is None:
        raise SystemExit(f"{caption}: the Total row never arrived")
    for code, expected in zip(order, printed):
        summed = sum(found[code].values())
        if abs(summed - expected) > PERCENT_SLACK:
            raise SystemExit(
                f"{caption} {code}: the categories come to {summed:.2f}% "
                f"against a printed {expected:.1f}%")
    counts = {len(found[c]) for c in CODES}
    if len(counts) != 1:
        raise SystemExit(f"{caption}: the provinces have different numbers of "
                         f"categories: {sorted(counts)}")
    log(f"  {caption} {what}: {counts.pop()} categories across "
        f"{len(CODES)} columns, every one summing to its printed total")
    return found


def sex_ratios(rows: list[list[str]]) -> dict[str, float]:
    """Table 2.7: males per 100 females, four censuses, the last of them 2022."""
    found: dict[str, float] = {}
    for row in rows:
        values = [t for t in row if DECIMAL.match(t)]
        name = " ".join(t for t in row if not DECIMAL.match(t))
        if len(values) != 4 or (name not in PROVINCES and name != NATIONAL):
            continue
        found[name] = float(values[-1].replace(",", "."))
        if name == NATIONAL:
            break
    missing = [p for p in PROVINCES if p not in found]
    if missing:
        raise SystemExit(f"Table 2.7: no sex ratio for {', '.join(missing)}")
    log(f"  Table 2.7: sex ratios for {len(PROVINCES)} provinces, "
        f"{min(found.values()):.1f} to {max(found.values()):.1f} males per 100 "
        f"females")
    return found


def composition(row: dict[str, float], names: dict[str, str],
                ) -> list[dict[str, Any]]:
    """Published percentages as this dataset's share rows, with no count.

    shares() takes counts and divides; here there is nothing to divide. The
    percentages are carried across as they were printed, largest first, and a
    row without "count" is a shape the build already understands -- it declines
    to sum a parent from children that publish shares with no counts, which is
    the right answer rather than a silent one.
    """
    # A printed 0,0 is kept. It means "below 0.05%", which is a measurement,
    # and dropping it would make a province look as though the census never
    # offered the category. shares() keeps its zeros for the same reason.
    out = [{"group": names.get(label, label), "pct": round(pct, 2)}
           for label, pct in row.items()]
    out.sort(key=lambda r: r["pct"], reverse=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out")
    args = ap.parse_args()

    log(f"South Africa: {URL}")
    blob = http_get(URL, binary=True)
    log(f"  {len(blob):,} bytes")
    document = pages(blob)

    people = read(document, CAPTIONS["population"], population)
    groups = read(document, CAPTIONS["ethnicity"], ethnicity)
    tongues = read(document, CAPTIONS["language"],
                   lambda rows: percentages(rows, CAPTIONS["language"], "language"))
    beliefs = read(document, CAPTIONS["religion"],
                   lambda rows: percentages(rows, CAPTIONS["religion"], "religion"))
    ratios = read(document, CAPTIONS["sex_ratio"], sex_ratios)

    records: list[dict[str, Any]] = []
    for code in CODES[:-1]:
        name = PROVINCE_BY_CODE[code]
        counts = groups[name]
        records.append(record(
            f"ZAF-{code.lower()}", name, level="admin1", parent="ZAF",
            aliases=list(ALIASES.get(name, ())),
            population=measure(people[name], year=YEAR, source=SOURCE),
            population_note=POPULATION_NOTE,
            sex_ratio=measure(round(ratios[name] * 10),
                              unit="males_per_1000_females",
                              year=YEAR, source=SOURCE),
            ethnicity=shares({g: counts[g] for g in GROUPS},
                             total=counts["Total"]) or gap(NOT_AVAILABLE),
            ethnicity_year=YEAR, ethnicity_note=ETHNICITY_NOTE,
            language=composition(tongues[code], LANGUAGE_NAMES)
            or gap(NOT_AVAILABLE),
            language_year=YEAR, language_note=LANGUAGE_NOTE,
            religion=composition(beliefs[code], RELIGION_NAMES)
            or gap(NOT_AVAILABLE),
            religion_year=YEAR, religion_note=RELIGION_NOTE,
            sources=[{"field": "population/ethnicity/language/religion",
                      "name": SOURCE, "url": URL, "license": LICENCE}]))

    out = args.out or PROCESSED / "south_africa_province.json"
    write_json(out, records)
    log(f"  {len(records)} provinces, {sum(people[p] for p in PROVINCES):,} "
        f"people")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
