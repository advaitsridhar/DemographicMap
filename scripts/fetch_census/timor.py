#!/usr/bin/env python3
"""Timor-Leste: mother tongue and religion by municipality, from the census.

Timor-Leste's statistics office -- the Direção-Geral de Estatística, since
2022 the Instituto Nacional de Estatística de Timor-Leste (INETL, I.P.) --
publishes at ``inetl-ip.gov.tl``, which answers a plain client. ``statistics
.gov.tl``, the host the older literature cites, no longer resolves at all.

Three of its files are read here, and they are not all from one census:

* **Mother tongue by municipality**, Census 2015 Volume 2 priority table 12
  (``4_2015-V2-Language.xls``, sheet ``2.12``): 38 mother tongues down the
  side, the country and its 13 municipalities across the top. Every
  municipality's tongues add to its own population exactly, so in 2015 the
  question took one answer per person and the table is a partition.
* **Religion by municipality**, Census 2015 Volume 2 priority table 11
  (``3_2015-V2-Nationality-Citizenship-Religion.xls``, sheet ``2.11``): the
  country, urban, rural and each municipality, each with a male and a female
  row beneath it, against seven religions. Same 1,179,654 base as the
  language table.
* **Population**, Census **2022** main report basic table 4.01
  (``Chapter-4-TLPHC-Census-report-Basic-tables.xlsx``, sheet ``4.01``):
  three label columns -- municipality, administrative post, suco -- and the
  2022 count beside them. This is the only one of the three that reaches
  below the municipality.

**Why the compositions are 2015 and the population is 2022.** The 2022 census
asked both questions -- its questionnaire, reproduced as Annex III of the main
report, puts religion at E57 and "Mother tongues: what languages did <Name>
learn as a child?" at E58 -- and published neither by municipality. The main
report's basic table 4.07 gives religion by age and sex for the country only,
and no basic table gives mother tongue at all. So the newest published
composition for any Timorese municipality is the 2015 one, and every
composition here carries 2015 as its year.

**Ethnicity is not written, and not merely missing.** The 2022 questionnaire's
person module runs from E1 to E77 without an ethnicity, race or tribe
question: marital status, parents, birth registration, place of birth,
migration, citizenship, literacy, education, labour, religion, mother tongue,
disability, fertility, birth attendance. The declaration lives in
``NOT_COLLECTED_POLICY["TLS"]``, so the country row and all 78 units below it
say the same thing.

**Atauro.** The 2022 census counts 14 municipalities: Atauro, an island that
was an administrative post of Dili, became a municipality in its own right in
2022. The boundary file draws the 13 of 2015, Atauro inside Dili, so the 2022
population written on Dili is Dili's plus Atauro's -- a sum of two published
counts over a partition the census itself states, not an apportionment. The
2015 compositions need no such treatment: in 2015 Atauro was part of Dili and
its people are in Dili's column already.

**The 65 administrative posts** get the 2022 population and a stated gap for
each composition: no published table crosses religion or mother tongue with
anything below the municipality, in either census round. INETL's own REDATAM
dashboard, which would tabulate the microdata to any geography, is served from
a bare address (``http://20.6.104.113/redatam/``) that timed out on the
runner.

Usage:
    python -m scripts.fetch_census.timor
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from typing import Any

from ._shared import (
    NOT_AVAILABLE, PROCESSED, RAW, collection_gap, download, gap, log, measure,
    record, write_json,
)

OUT = "timor.json"
COMPOSITION_YEAR = 2015
POPULATION_YEAR = 2022

BASE = "https://inetl-ip.gov.tl/wp-content/uploads"
LANGUAGE_XLS = f"{BASE}/2023/03/4_2015-V2-Language.xls"
RELIGION_XLS = f"{BASE}/2023/03/3_2015-V2-Nationality-Citizenship-Religion.xls"
POPULATION_XLSX = f"{BASE}/2023/05/Chapter-4-TLPHC-Census-report-Basic-tables.xlsx"
LANGUAGE_SHEET = "2.12"
RELIGION_SHEET = "2.11"
POPULATION_SHEET = "4.01"

LANGUAGE_PAGE = ("https://inetl-ip.gov.tl/2023/03/09/"
                 "census-2015-priority-table-population-by-language/")
RELIGION_PAGE = ("https://inetl-ip.gov.tl/2023/03/09/"
                 "census-2015-priority-table-population-by-nationality-"
                 "citizenship-and-religion/")
POPULATION_PAGE = ("https://inetl-ip.gov.tl/2023/05/18/"
                   "table-main-report-timor-leste-population-and-housing-census-2022/")

OFFICE = ("Instituto Nacional de Estatística de Timor-Leste (INETL, I.P.), "
          "formerly the Direção-Geral de Estatística")
CENSUS_2015 = f"Population and Housing Census 2015, {OFFICE}"
CENSUS_2022 = f"Population and Housing Census 2022, {OFFICE}"
LANGUAGE_SOURCE = (f"{CENSUS_2015}, Volume 2 priority table 12: population by "
                   "mother tongue and municipality")
RELIGION_SOURCE = (f"{CENSUS_2015}, Volume 2 priority table 11: population by "
                   "municipality, urban/rural location, sex and religion")
POPULATION_SOURCE = (f"{CENSUS_2022} Main Report, basic table 4.01: population by "
                     "municipality, administrative post, suco and urban/rural "
                     "location, sex")
LICENCE = "Official statistics of INETL, I.P., cited as published"

# The 13 first-level shapes, spelled as the boundary file and this project's
# other Timor-Leste text spell them, with every spelling the workbooks or the
# literature use beside them. Declared, never guessed: the two 2015 workbooks
# disagree with each other about accents ("Lautem" against "LAUTÉM") and the
# exclave is written five different ways between Portuguese, Tetum and English.
# Capital names -- Maliana, Suai, Same, Lospalos -- are deliberately not
# aliases: they are also administrative posts, and an alias that names a
# smaller place inside the unit is how a first-level row lands on a
# second-level shape.
MUNICIPALITIES: dict[str, list[str]] = {
    "Aileu": [],
    "Ainaro": [],
    "Baucau": ["Baukau"],
    "Bobonaro": [],
    "Cova Lima": ["Covalima", "Kovalima", "Cova-Lima"],
    "Dili": ["Díli", "Dili Municipality"],
    "Ermera": [],
    "Lautém": ["Lautem", "Lautén"],
    "Liquiçá": ["Liquica", "Liquiça", "Likisá", "Likisa"],
    "Manatuto": [],
    "Manufahi": [],
    "Oecusse": ["Oecussi", "Oekusi", "Oe-Cusse", "Oé-Cusse", "Oé-Cusse Ambeno",
                "Oecusse Ambeno", "Oecusse-Ambeno", "Ambeno",
                "SAR of Oecusse", "Special Administrative Region of Oe-Cusse Ambeno",
                "RAEOA", "Região Administrativa Especial de Oé-Cusse Ambeno"],
    "Viqueque": [],
}
# The fourteenth municipality of 2022, which the boundary file has no shape
# for: Atauro was an administrative post of Dili until 2022 and the shapes
# are the older set. Its 2022 population is summed into Dili's; see the
# module docstring.
ATAURO = "Atauro"
ATAURO_PARENT = "Dili"

# The religion columns of table 11, mapped to the labels the group tree
# places. A column is recognised by what its heading starts with once folded,
# not by the whole string: the sheet writes the second one across a line break
# as "Protestantism/ Evangelicalism", and a reader keyed on the exact text
# would break on a re-release that closed the space. "Traditional" is the
# census's own word for what its 2022 questionnaire calls an indigenous
# religion.
RELIGIONS: tuple[tuple[str, str], ...] = (
    ("catholicism", "Catholic"),
    ("protestantism", "Protestant/Evangelical"),
    ("islam", "Muslim"),
    ("buddhism", "Buddhism"),
    ("hinduism", "Hinduism"),
    ("traditional", "Traditional religion"),
    ("other", "Other religion"),
)
RELIGION_LABELS = [label for _prefix, label in RELIGIONS]
# Table 11 has no "no religion" and no "not stated" column: in 2015 those
# answers are inside "Other", which is why "Other" is published as a religion
# rather than as a residual.

# The mother-tongue rows of table 12 that this reader renames. Every other row
# label is written as the census writes it; the typographic apostrophe is
# normalised to a plain one so "Waima'a" is one label across the project, and
# the census's "Indonesian" and "Chinese" keep the census's own wording.
LANGUAGE_RENAMES: dict[str, str] = {"Other": "Other language"}

# What the workbooks call the country, in each of its spellings.
COUNTRY_LABELS = {"timorleste", "timor"}
# Rows of table 11 that are a breakdown of the row above rather than a unit.
RELIGION_BREAKDOWN = {"male", "female", "urban", "rural"}

# The office's own published national figures, for the check. The 2022 main
# report states that in 2015 Catholicism "was reported for 97.6" percent of the
# population; the language shares are the fifteen the map's own country row
# carries, which are these counts over this base.
NATIONAL_BASE = 1_179_654
NATIONAL_CATHOLIC_PCT = 97.6
NATIONAL_LANGUAGE_PCT = {
    "Tetun Prasa": 30.6, "Mambai": 16.6, "Makasai": 10.5, "Tetun Terik": 6.1,
    "Baikenu": 5.9, "Kemak": 5.8, "Bunak": 5.5, "Tokodede": 4.0,
    "Fataluku": 3.5, "Waima'a": 1.8, "Galoli": 1.4, "Naueti": 1.4,
    "Idate": 1.2, "Midiki": 1.2,
}
SHARE_TOLERANCE = 0.06      # one rounding step on a share printed to a tenth
NATIONAL_POPULATION_2022 = 1_341_737

MIN_PCT = 0.05              # below this a group is not worth a row of its own


def fold(text: str) -> str:
    """A label reduced to its letters: what two spellings of one name agree on.

    Diacritics go, case goes, punctuation goes, and so do digits -- the
    religion sheet writes the exclave "SAR1 OF OECUSSE", the 1 being a
    footnote marker and not part of the name.
    """
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return "".join(c for c in text if c.isalpha())


MUNICIPALITY_KEYS = {fold(key): name
                     for name, others in MUNICIPALITIES.items()
                     for key in [name, *others]}
MUNICIPALITY_KEYS[fold("SAR1 of Oecusse")] = "Oecusse"
ATAURO_KEY = fold(ATAURO)


def tidy(text: Any) -> str:
    """A cell as one line of text, with the census's curly apostrophe
    flattened so "Waima’a" and "Waima'a" are one label."""
    if text is None:
        return ""
    return " ".join(str(text).replace("’", "'").split())


def at(row: list[Any], index: int) -> Any:
    """``row[index]``, or None where the row stops short of it.

    A sheet's rows are not all the same length -- the footnote under table 12
    is one cell wide against the table's seventeen -- and a reader that indexes
    blind fails on the footnote rather than skipping it.
    """
    return row[index] if 0 <= index < len(row) else None


def number(value: Any) -> float | None:
    """A cell as a count, or None where it holds no number."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace(" ", "").strip()
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return None
    return float(text)


# ---------------------------------------------------------------------------
# Reading the three sheets
# ---------------------------------------------------------------------------

def xls_grid(path, sheet_name: str) -> list[list[Any]]:
    import xlrd
    book = xlrd.open_workbook(str(path))
    names = book.sheet_names()
    if sheet_name not in names:
        raise SystemExit(f"timor: {path.name} has no sheet {sheet_name!r}; it has {names}")
    sheet = book.sheet_by_name(sheet_name)
    return [[sheet.cell_value(r, c) for c in range(sheet.ncols)]
            for r in range(sheet.nrows)]


def xlsx_grid(path, sheet_name: str) -> list[list[Any]]:
    import openpyxl
    book = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    if sheet_name not in book.sheetnames:
        raise SystemExit(f"timor: {path.name} has no sheet {sheet_name!r}; "
                         f"it has {book.sheetnames}")
    grid = [list(row) for row in book[sheet_name].iter_rows(values_only=True)]
    book.close()
    return grid


def read_language(grid: list[list[Any]]) -> tuple[dict[str, dict[str, float]],
                                                  dict[str, float], str]:
    """Table 12 -> {municipality: {mother tongue: count}}, the table's own
    total for each municipality, and the table's title.

    The header row is the one that names the municipalities; which column is
    which is read from it rather than assumed, because a column order is the
    kind of thing a re-release changes silently. The row labelled with the
    country is the table's own totals row and is kept for the check, not
    written.
    """
    title = tidy(at(grid[0], 0)) if grid else ""
    columns: dict[int, str] = {}
    header = -1
    for index, row in enumerate(grid[:8]):
        found = {i: MUNICIPALITY_KEYS[fold(tidy(cell))]
                 for i, cell in enumerate(row)
                 if fold(tidy(cell)) in MUNICIPALITY_KEYS}
        if len(found) >= len(MUNICIPALITIES):
            columns, header = found, index
            break
    missing = sorted(set(MUNICIPALITIES) - set(columns.values()))
    if missing:
        raise SystemExit(f"timor: sheet {LANGUAGE_SHEET} names no column for {missing}; "
                         "a spelling the reader does not know must be declared in "
                         "MUNICIPALITIES before the table can be read")

    counts: dict[str, dict[str, float]] = {name: {} for name in MUNICIPALITIES}
    totals: dict[str, float] = {}
    for row in grid[header + 1:]:
        label = tidy(at(row, 0))
        # A row whose label carries no letter at all is the sheet's column
        # numbering -- "-1.0", "-2.0", ... -- and every one of its cells is a
        # number, so nothing else here would tell it from a row of figures.
        if not label or not any(c.isalpha() for c in label):
            continue
        key = fold(label)
        values = {name: number(at(row, i)) for i, name in columns.items()}
        if any(v is None for v in values.values()):
            continue                      # a footnote or a spacer, not a row of figures
        if key in COUNTRY_LABELS:
            if totals:
                raise SystemExit(f"timor: sheet {LANGUAGE_SHEET} has two country rows")
            totals = {name: float(v) for name, v in values.items()}
            continue
        name = LANGUAGE_RENAMES.get(label, label)
        for municipality, value in values.items():
            if name in counts[municipality]:
                raise SystemExit(f"timor: sheet {LANGUAGE_SHEET} prints {name!r} twice")
            counts[municipality][name] = float(value)
    if not totals:
        raise SystemExit(f"timor: sheet {LANGUAGE_SHEET} has no country row to check against")
    return counts, totals, title


def read_religion(grid: list[list[Any]]) -> tuple[dict[str, dict[str, float]],
                                                  dict[str, float],
                                                  dict[str, float], str]:
    """Table 11 -> {municipality: {religion: count}}, each municipality's own
    printed total, the country row, and the table's title.

    The sheet stacks units: the country, urban and rural, then each
    municipality, each followed by a male and a female row. A row is a unit
    when its label is a name this reader knows; "Male", "Female", "Urban" and
    "Rural" are a breakdown of whatever came above and are skipped.
    """
    title = tidy(at(grid[0], 0)) if grid else ""
    columns: dict[int, str] = {}
    header = -1
    for index, row in enumerate(grid[:8]):
        found: dict[int, str] = {}
        for i, cell in enumerate(row):
            key = fold(tidy(cell))
            label = next((name for prefix, name in RELIGIONS
                          if key.startswith(prefix)), None)
            if label and label not in found.values():
                found[i] = label
        if len(found) == len(RELIGIONS):
            columns, header = found, index
            break
    if not columns:
        seen = sorted({tidy(c) for row in grid[:8] for c in row if tidy(c)})
        raise SystemExit(f"timor: sheet {RELIGION_SHEET} has no row naming all "
                         f"{len(RELIGIONS)} religion columns; its first rows hold {seen}")
    # The Total column is headed a row above the religions -- the sheet stacks
    # "Municipality ... | Total | Religion" over the seven names -- so it is
    # looked for across the head of the sheet and not in the religion row.
    total_column = next(
        (i for row in grid[:header + 1] for i, cell in enumerate(row)
         if tidy(cell).lower() == "total" and i not in columns), None)
    if total_column is None:
        raise SystemExit(f"timor: sheet {RELIGION_SHEET} names no Total column in the "
                         f"{header + 1} rows above and including its religion header")

    counts: dict[str, dict[str, float]] = {}
    totals: dict[str, float] = {}
    country: dict[str, float] = {}
    for row in grid[header + 1:]:
        label = tidy(at(row, 0))
        if not label or not any(c.isalpha() for c in label):
            continue                      # the sheet's column numbering
        if label.lower() in RELIGION_BREAKDOWN:
            continue
        key = fold(label)
        values = {name: number(at(row, i)) for i, name in columns.items()}
        printed = number(at(row, total_column))
        if printed is None or any(v is None for v in values.values()):
            continue                      # a footnote row
        if key in COUNTRY_LABELS:
            if country:
                raise SystemExit(f"timor: sheet {RELIGION_SHEET} has two country rows")
            country = {**{n: float(v) for n, v in values.items()}, "Total": printed}
            continue
        if key not in MUNICIPALITY_KEYS:
            log(f"    sheet {RELIGION_SHEET}: {label!r} is a row this reader does not "
                "name; read and checked, not written")
            continue
        name = MUNICIPALITY_KEYS[key]
        if name in counts:
            raise SystemExit(f"timor: sheet {RELIGION_SHEET} prints {name!r} twice")
        counts[name] = {n: float(v) for n, v in values.items()}
        totals[name] = printed
    missing = sorted(set(MUNICIPALITIES) - set(counts))
    if missing:
        raise SystemExit(f"timor: sheet {RELIGION_SHEET} has no row for {missing}")
    if not country:
        raise SystemExit(f"timor: sheet {RELIGION_SHEET} has no country row to check against")
    return counts, totals, country, title


def read_population(grid: list[list[Any]]) -> tuple[dict[str, float],
                                                    list[tuple[str, str, float]],
                                                    float, str]:
    """Table 4.01 -> the 2022 population of each municipality, of each
    administrative post with the municipality it is in, and the country's.

    The sheet gives each level a label column of its own -- municipality in
    the first, administrative post in the second, suco in the third -- so a
    row's level is read from which column holds its name and never from
    indentation or from a name list.
    """
    title = tidy(at(grid[0], 0)) if grid else ""
    total_column = None
    for row in grid[:8]:
        labels = [tidy(c).lower() for c in row]
        if labels[:3] == ["", "", ""] and "total" in labels:
            total_column = labels.index("total")
            break
    if total_column is None:
        raise SystemExit(f"timor: sheet {POPULATION_SHEET} header names no Total column")

    municipalities: dict[str, float] = {}
    posts: list[tuple[str, str, float]] = []
    country = 0.0
    current = ""
    for row in grid:
        first, second, third = (tidy(at(row, 0)), tidy(at(row, 1)),
                                tidy(at(row, 2)))
        value = number(at(row, total_column))
        if value is None:
            continue
        if third:
            continue                      # a suco; the map draws no shape for one
        if second:
            if not current:
                raise SystemExit(f"timor: sheet {POPULATION_SHEET} prints the "
                                 f"administrative post {second!r} before any municipality")
            posts.append((second, current, value))
            continue
        if not first:
            continue
        key = fold(first)
        if key in COUNTRY_LABELS:
            country = value
            continue
        if key == ATAURO_KEY:
            current = ATAURO
        elif key in MUNICIPALITY_KEYS:
            current = MUNICIPALITY_KEYS[key]
        else:
            raise SystemExit(f"timor: sheet {POPULATION_SHEET} names a municipality this "
                             f"reader does not know: {first!r}")
        if current in municipalities:
            raise SystemExit(f"timor: sheet {POPULATION_SHEET} prints {current!r} twice")
        municipalities[current] = value
    if not country:
        raise SystemExit(f"timor: sheet {POPULATION_SHEET} has no country row")
    return municipalities, posts, country, title


# ---------------------------------------------------------------------------
# The checks, every one of which refuses the run
# ---------------------------------------------------------------------------

def check_language(counts, totals) -> None:
    for name, tongues in counts.items():
        added = sum(tongues.values())
        if abs(added - totals[name]) > 0.5:
            raise SystemExit(f"timor: {name}'s {len(tongues)} mother tongues add to "
                             f"{added:,.0f} and the table's own total for it is "
                             f"{totals[name]:,.0f} ({added - totals[name]:+,.0f})")
    log(f"  mother tongue: {len(counts)} municipalities, "
        f"{len(next(iter(counts.values())))} tongues each, every one adding to the "
        "table's own municipal total to the person")


def check_religion(counts, totals, country) -> None:
    for name, faiths in counts.items():
        added = sum(faiths.values())
        if abs(added - totals[name]) > 0.5:
            raise SystemExit(f"timor: {name}'s religions add to {added:,.0f} and the "
                             f"table's own total for it is {totals[name]:,.0f} "
                             f"({added - totals[name]:+,.0f})")
    for label in RELIGION_LABELS:
        summed = sum(f[label] for f in counts.values())
        if abs(summed - country[label]) > 0.5:
            raise SystemExit(f"timor: the municipalities' {label} adds to {summed:,.0f} "
                             f"against the country row's {country[label]:,.0f}")
    summed = sum(totals.values())
    if abs(summed - country["Total"]) > 0.5:
        raise SystemExit(f"timor: the municipalities add to {summed:,.0f} people against "
                         f"the country row's {country['Total']:,.0f}")
    log(f"  religion: {len(counts)} municipalities adding to {summed:,.0f}, the "
        "country row to the person, and every religion column likewise")


def check_bases(language_totals, religion_totals) -> None:
    for name in MUNICIPALITIES:
        if abs(language_totals[name] - religion_totals[name]) > 0.5:
            raise SystemExit(f"timor: {name} is {language_totals[name]:,.0f} people in the "
                             f"mother-tongue table and {religion_totals[name]:,.0f} in the "
                             "religion table; the two 2015 tables are not the same universe")
    base = sum(language_totals.values())
    if abs(base - NATIONAL_BASE) > 0.5:
        raise SystemExit(f"timor: the 2015 tables cover {base:,.0f} people, where this "
                         f"reader was written against {NATIONAL_BASE:,}; the release has "
                         "changed and the notes' arithmetic with it")
    log(f"  both 2015 tables count the same {base:,.0f} people, municipality by "
        "municipality")


def check_published(language_counts, religion_country, population_country) -> None:
    """Against the office's own published national figures.

    Three of them, and they are the point of this function: the checks above
    only say that each sheet is internally consistent, which a sheet of the
    wrong year would also be.

    The 2022 main report says Catholicism was reported for 97.6 percent of the
    population in 2015. The fifteen-entry language list the map's country row
    already carries -- Tetun Prasa 30.6, Mambai 16.6, and so on -- is this
    table's national column over this base, which is the whole reason the
    country row and these municipalities can sit beside each other. And the
    2022 census counted 1,341,737 people.
    """
    base = religion_country["Total"]
    catholic = 100.0 * religion_country["Catholic"] / base
    if abs(catholic - NATIONAL_CATHOLIC_PCT) > SHARE_TOLERANCE:
        raise SystemExit(f"timor: the religion table makes Catholicism {catholic:.2f}% of "
                         f"the country, against the {NATIONAL_CATHOLIC_PCT}% the 2022 main "
                         "report reports for 2015")
    wrong = []
    for tongue, published in NATIONAL_LANGUAGE_PCT.items():
        counted = sum(m.get(tongue, 0.0) for m in language_counts.values())
        share = 100.0 * counted / base
        if abs(share - published) > SHARE_TOLERANCE:
            wrong.append(f"{tongue}: {share:.2f}% read, {published}% published")
    if wrong:
        raise SystemExit("timor: the mother-tongue table does not reproduce the national "
                         "shares this map's country row carries -- " + "; ".join(wrong))
    if abs(population_country - NATIONAL_POPULATION_2022) > 0.5:
        raise SystemExit(f"timor: the 2022 table's country row is {population_country:,.0f}, "
                         f"where the census published {NATIONAL_POPULATION_2022:,}")
    log(f"  national check: Catholicism {catholic:.2f}% against a published {NATIONAL_CATHOLIC_PCT}%, "
        f"all {len(NATIONAL_LANGUAGE_PCT)} of the country row's named mother tongues "
        f"reproduced to within a rounding step, and the 2022 table's country row the "
        f"published {NATIONAL_POPULATION_2022:,}")


def check_population(municipalities, posts, country) -> None:
    summed = sum(municipalities.values())
    if abs(summed - country) > 0.5:
        raise SystemExit(f"timor: the 2022 municipalities add to {summed:,.0f} against the "
                         f"sheet's own country row of {country:,.0f}")
    for name, total in municipalities.items():
        mine = sum(v for _post, parent, v in posts if parent == name)
        if abs(mine - total) > 0.5:
            raise SystemExit(f"timor: {name}'s administrative posts add to {mine:,.0f} "
                             f"against its own row of {total:,.0f}")
    log(f"  population 2022: {len(municipalities)} municipalities adding to "
        f"{summed:,.0f}, the published national figure, and {len(posts)} "
        "administrative posts each adding to the municipality they are in")


# ---------------------------------------------------------------------------
# Building the records
# ---------------------------------------------------------------------------

def composition(counts: dict[str, float], total: float) -> list[dict[str, Any]]:
    """Counts -> the map's rows, largest first, name breaking a tie.

    A group under 0.05% of the unit is dropped rather than folded into a
    residual: these tables already print an "Other" of their own, and a second
    residual beside it would be two rows meaning different things. What is
    dropped is said in the note.
    """
    rows = [{"group": g, "pct": round(100.0 * c / total, 1), "count": int(c)}
            for g, c in counts.items()
            if c and 100.0 * c / total >= MIN_PCT]
    rows.sort(key=lambda r: (-r["pct"], r["group"]))
    return rows


def dropped(counts: dict[str, float], total: float) -> int:
    return sum(1 for c in counts.values() if c and 100.0 * c / total < MIN_PCT)


def language_note(name: str, counts, total: float) -> str:
    small = dropped(counts, total)
    named = len([c for c in counts.values() if c])
    text = (f"Mother tongue as the 2015 census counted it for this municipality, from "
            f"table 12 of the census's own Volume 2 priority tables: {total:,.0f} people, "
            f"one tongue each, the municipality's rows adding to that figure exactly. ")
    if small:
        text += (f"{named} of the census's 38 tongues were spoken here and "
                 f"{small} of them by under 0.05% of the municipality, which are counted "
                 "in the base and not shown. ")
    text += ("The 2022 census asked the question again -- and allowed two answers rather "
             "than one -- but has published no table of it below the country.")
    return text


def religion_note(name: str, total: float) -> str:
    return (f"Religion as the 2015 census counted it for this municipality, from table 11 "
            f"of the census's own Volume 2 priority tables: {total:,.0f} people, the same "
            f"base as the mother-tongue table beside it. 'Other religion' is the census's "
            f"own residual column and holds the answers it did not name, no religion among "
            f"them, there being no separate column for those. The 2022 census asked "
            f"religion again and published it for the country only.")


def population_note(name: str) -> str:
    if name != ATAURO_PARENT:
        return (f"The 2022 census's count for the municipality, from basic table 4.01 of "
                f"the main report. The compositions above it are from the 2015 census, "
                f"which counted a smaller population.")
    return ("The 2022 census's count for Dili and for Atauro added together, from basic "
            "table 4.01 of the main report. Atauro was an administrative post of Dili "
            "until 2022, when it became the fourteenth municipality; the boundary file "
            "draws the thirteen of 2015, so the two published counts are summed back "
            "into the shape that contains them both.")


POST_LANGUAGE_GAP = (
    "No census publishes mother tongue below the municipality for Timor-Leste. The 2015 "
    "round tabulated it by municipality (Volume 2 table 12) and no further down; the 2022 "
    "round asked the question and has published no table of it at any level. INETL's "
    "REDATAM dashboard, which tabulates the microdata to any geography, is served from a "
    "bare address that did not answer.")
POST_RELIGION_GAP = (
    "No census publishes religion below the municipality for Timor-Leste. The 2015 round "
    "tabulated it by municipality, urban/rural location and sex (Volume 2 table 11); the "
    "2022 round's main report gives it for the country by age and sex only (basic table "
    "4.07). INETL's REDATAM dashboard, which tabulates the microdata to any geography, is "
    "served from a bare address that did not answer.")


def build(language, language_totals, religion, religion_totals,
          population, posts) -> list[dict[str, Any]]:
    from common import slugify

    rows: list[dict[str, Any]] = []
    for name in MUNICIPALITIES:
        total = language_totals[name]
        people = population.get(name, 0.0)
        if name == ATAURO_PARENT:
            people += population.get(ATAURO, 0.0)
        rows.append(record(
            f"TLS-{slugify(name)}", name, level="admin1", parent="TLS", country="TLS",
            aliases=list(MUNICIPALITIES[name]),
            population=measure(int(people), year=POPULATION_YEAR, source=POPULATION_SOURCE,
                               note=population_note(name)) if people else None,
            language=composition(language[name], total),
            language_year=COMPOSITION_YEAR,
            language_note=language_note(name, language[name], total),
            religion=composition(religion[name], religion_totals[name]),
            religion_year=COMPOSITION_YEAR,
            religion_note=religion_note(name, religion_totals[name]),
            ethnicity=collection_gap("TLS", "ethnicity"),
            sources=[
                {"field": "language", "name": LANGUAGE_SOURCE, "url": LANGUAGE_PAGE,
                 "year": COMPOSITION_YEAR, "license": LICENCE},
                {"field": "religion", "name": RELIGION_SOURCE, "url": RELIGION_PAGE,
                 "year": COMPOSITION_YEAR, "license": LICENCE},
                {"field": "population", "name": POPULATION_SOURCE, "url": POPULATION_PAGE,
                 "year": POPULATION_YEAR, "license": LICENCE},
            ],
        ))

    for post, parent, people in posts:
        # Atauro's post sits under Dili, which is the municipality the
        # boundary file puts it in; see the module docstring.
        shape_parent = ATAURO_PARENT if parent == ATAURO else parent
        rows.append(record(
            f"TLS-P-{slugify(shape_parent)}-{slugify(post)}", post,
            level="admin2", parent="TLS", country="TLS",
            parent_name=shape_parent,
            parent_aliases=list(MUNICIPALITIES.get(shape_parent, [])),
            codes={"municipality": shape_parent,
                   "census_municipality_2022": parent},
            population=measure(int(people), year=POPULATION_YEAR, source=POPULATION_SOURCE,
                               note="The 2022 census's count for the administrative post, "
                                    "from basic table 4.01 of the main report."),
            language=gap(NOT_AVAILABLE, POST_LANGUAGE_GAP),
            religion=gap(NOT_AVAILABLE, POST_RELIGION_GAP),
            ethnicity=collection_gap("TLS", "ethnicity"),
            sources=[{"field": "population", "name": POPULATION_SOURCE,
                      "url": POPULATION_PAGE, "year": POPULATION_YEAR, "license": LICENCE}],
        ))
    return rows


def run() -> int:
    log(f"timor: {LANGUAGE_SOURCE}")
    language_file = download(LANGUAGE_XLS, RAW / "timor" / LANGUAGE_XLS.rsplit("/", 1)[-1])
    religion_file = download(RELIGION_XLS, RAW / "timor" / RELIGION_XLS.rsplit("/", 1)[-1])
    population_file = download(POPULATION_XLSX,
                               RAW / "timor" / POPULATION_XLSX.rsplit("/", 1)[-1])

    language, language_totals, language_title = read_language(
        xls_grid(language_file, LANGUAGE_SHEET))
    religion, religion_totals, religion_country, religion_title = read_religion(
        xls_grid(religion_file, RELIGION_SHEET))
    population, posts, country_2022, population_title = read_population(
        xlsx_grid(population_file, POPULATION_SHEET))
    log(f"  sheet {LANGUAGE_SHEET}: {language_title!r}")
    log(f"  sheet {RELIGION_SHEET}: {religion_title!r}")
    log(f"  sheet {POPULATION_SHEET}: {population_title!r}")
    tongues = sorted(next(iter(language.values())))
    log(f"  {len(tongues)} mother tongues: {tongues}")

    check_language(language, language_totals)
    check_religion(religion, religion_totals, religion_country)
    check_bases(language_totals, religion_totals)
    check_published(language, religion_country, country_2022)
    check_population(population, posts, country_2022)

    rows = build(language, language_totals, religion, religion_totals, population, posts)
    for row in rows:
        if row["level"] != "admin1":
            continue
        top = ", ".join(f"{g['group']} {g['pct']}" for g in row["language"][:3])
        faith = row["religion"][0]
        log(f"    {row['name']:10} {row['population']['value']:>8,}  "
            f"{faith['group']} {faith['pct']}  |  {top}")
    write_json(PROCESSED / OUT, rows)
    admin1 = sum(1 for r in rows if r["level"] == "admin1")
    log(f"  wrote {admin1} municipalities and {len(rows) - admin1} administrative "
        f"posts to {OUT}")
    return 0


# ---------------------------------------------------------------------------
# --probe: the 2015 and the 2022 lists of administrative posts, side by side.
# Writes nothing. It exists because the two censuses do not name the same
# units: 2022 lists 67 posts where 2015 listed 65, and which two are new --
# and which older post each was cut out of -- is a question about sucos that
# only these two tables can answer.
# ---------------------------------------------------------------------------

DISTRIBUTION_XLS = f"{BASE}/2023/03/1_2015-V2-Population-Household-Distribution.xls"
DISTRIBUTION_PAGE = ("https://inetl-ip.gov.tl/2023/03/09/population-distribution-by-"
                     "administrative-area-volume-2-population-and-household-distribution/")


def units_2015(path) -> dict[str, dict[str, list[str]]]:
    """{municipality: {administrative post: [suco, ...]}} as the 2015 volume
    lists them, from whichever of its sheets carries the three levels.

    The 2015 workbook indents rather than using a column per level, so a row's
    level is read from how deep its label is: this is reconnaissance and is
    never used to write a figure.
    """
    import xlrd
    book = xlrd.open_workbook(str(path))
    out: dict[str, dict[str, list[str]]] = {}
    for sheet in book.sheets():
        grid = [[sheet.cell_value(r, c) for c in range(sheet.ncols)]
                for r in range(sheet.nrows)]
        found: dict[str, dict[str, list[str]]] = {}
        municipality = post = ""
        for row in grid:
            raw = str(at(row, 0) or "")
            label = tidy(raw)
            if not label or not any(c.isalpha() for c in label):
                continue
            depth = len(raw) - len(raw.lstrip())
            key = fold(label)
            if key in COUNTRY_LABELS:
                continue
            if key in MUNICIPALITY_KEYS and depth == 0:
                municipality = MUNICIPALITY_KEYS[key]
                found.setdefault(municipality, {})
                post = ""
            elif municipality and depth and depth <= 3:
                post = label
                found[municipality].setdefault(post, [])
            elif municipality and post and depth > 3:
                found[municipality][post].append(label)
        posts = sum(len(v) for v in found.values())
        log(f"  sheet {sheet.name!r}: {len(found)} municipalities, {posts} posts")
        if posts > sum(len(v) for v in out.values()):
            out = found
    return out


def probe() -> int:
    log("== the 2015 volume's administrative areas")
    old = units_2015(download(DISTRIBUTION_XLS,
                              RAW / "timor" / DISTRIBUTION_XLS.rsplit("/", 1)[-1]))
    log("== the 2022 main report's basic table 4.01")
    grid = xlsx_grid(download(POPULATION_XLSX,
                              RAW / "timor" / POPULATION_XLSX.rsplit("/", 1)[-1]),
                     POPULATION_SHEET)
    new: dict[str, dict[str, list[str]]] = {}
    municipality = post = ""
    for row in grid:
        first, second, third = tidy(at(row, 0)), tidy(at(row, 1)), tidy(at(row, 2))
        if first and fold(first) not in COUNTRY_LABELS:
            municipality = first
            new.setdefault(municipality, {})
            post = ""
        elif second and municipality:
            post = second
            new[municipality].setdefault(post, [])
        elif third and municipality and post:
            new[municipality][post].append(third)
    for name, posts in new.items():
        log(f"  {name}: {len(posts)} posts -- {sorted(posts)}")

    log("== what changed between them")
    old_posts = {fold(p): (m, p, sucos) for m, ps in old.items() for p, sucos in ps.items()}
    new_posts = {fold(p): (m, p, sucos) for m, ps in new.items() for p, sucos in ps.items()}
    log(f"  2015: {len(old_posts)} posts; 2022: {len(new_posts)} posts")
    for key, (m, p, sucos) in sorted(new_posts.items()):
        if key in old_posts:
            continue
        log(f"  new in 2022: {p!r} in {m}, {len(sucos)} sucos: {sorted(sucos)}")
        for okey, (om, op, osucos) in sorted(old_posts.items()):
            shared = sorted(set(map(fold, sucos)) & set(map(fold, osucos)))
            if shared:
                log(f"      {len(shared)} of them were in 2015's {op!r} ({om}), "
                    f"which had {len(osucos)}")
    for key, (m, p, sucos) in sorted(old_posts.items()):
        if key not in new_posts:
            log(f"  gone from 2022: {p!r} in {m}, {len(sucos)} sucos in 2015")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true",
                    help="print the 2015 and 2022 lists of administrative posts "
                         "and what changed between them; writes nothing")
    args = ap.parse_args()
    return probe() if args.probe else run()


if __name__ == "__main__":
    raise SystemExit(main())
